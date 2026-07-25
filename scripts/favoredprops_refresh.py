"""
favoredprops_refresh.py — FavoredProps props scraper (public API, no auth)
================================================================================

Runs on GitHub Actions on a schedule. FavoredProps.com exposes two
unauthenticated Next.js API routes (confirmed live 2026-07 via direct
endpoint discovery):

    GET /api/dfs?league={league}&app=all      -> PP/Underdog-style ranked
                                                   picks with hit rates
    GET /api/sportsbook?leagues={league}       -> multi-book player props
                                                   with hit rates

Raw shape (confirmed 2026-07 via live sample, NOT a flat "props" list —
first version of this script assumed that and silently produced zero
records for every league until this fix):

    dfs:        {"results": {league: {app: {payout_tier: [meta, rec, rec, ...]}}}}
    sportsbook: {"results": {league: [meta, rec, rec, ...]}}

Where `meta` is always the first list element ({"time_utc","props",
"props_total"}) and every record after it uses FavoredProps' own
Title-Case field names (Name, Stat Type, Bet, AVG Odds, L10 Hit Rate,
etc). This script flattens and remaps both into the flat lowercase
{"props": [...]} shape BetCouncil's fetch_favoredprops_from_gist() and
get_favoredprops_match() (fetchers.py) already expect — no changes
needed on that side, just correct data going in.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://www.favoredprops.com"

# Lowercase league codes as FavoredProps' own API expects them.
# Uppercased for the Gist filename to match BetCouncil's sport-name
# convention (betcouncil_favoredprops_dfs_MLB.json, etc).
LEAGUES = ["mlb", "nba", "nhl", "wnba", "nfl", "cbb", "cfb"]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# Collects per-request status/error info so it can be pushed to the Gist
# as a debug file even on failure — GitHub Actions log access requires
# following a redirect to Azure blob storage that isn't reachable from
# every environment used to maintain this script, so self-reporting into
# the Gist (already readable everywhere else in this project) is the
# reliable way to diagnose a failed run after the fact.
DEBUG_LOG: list = []

# FavoredProps' raw Title-Case field -> BetCouncil's expected lowercase
# key (matches what fetchers.py's get_favoredprops_match() and every UI
# consumer already read). Keys not in this map are dropped, not passed
# through raw — keeps the Gist payload to only what's actually used.
FIELD_MAP = {
    "FP ID": "fp_id", "Name": "player", "Position": "position",
    "Team": "team", "VS": "opp", "Site": "site", "DFS": "dfs_app",
    "Stat Type": "stat_type", "Bet": "bet", "Line": "line",
    "AVG Odds": "avg_odds", "AVG Pr": "avg_pr", "AVG Vig": "avg_vig",
    "N": "n_books", "Low": "low_odds", "High": "high_odds", "Books": "books",
    "L5 Avg": "l5_avg", "L10 Avg": "l10_avg", "Szn Avg": "szn_avg", "H2H Avg": "h2h_avg",
    "L5 Hit Rate": "l5_hit_rate", "L10 Hit Rate": "l10_hit_rate",
    "SZN Hit Rate": "szn_hit_rate", "H2H Hit Rate": "h2h_hit_rate",
    "H2H Percent": "h2h_pct", "Start Time": "start_time", "Last Updated": "last_updated",
}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _remap(raw: dict) -> dict:
    return {FIELD_MAP[k]: v for k, v in raw.items() if k in FIELD_MAP}


def _flatten_meta_prefixed_list(raw_list: list) -> list:
    """Every results[league] (sportsbook) or results[league][app][tier]
    (dfs) list starts with a {"time_utc","props","props_total"} metadata
    entry, then the real records. Skip the metadata, remap the rest."""
    if not raw_list:
        return []
    records = raw_list[1:] if isinstance(raw_list[0], dict) and "props_total" in raw_list[0] else raw_list
    return [_remap(r) for r in records if isinstance(r, dict)]




def fetch_dfs(league: str) -> dict | None:
    try:
        r = requests.get(f"{BASE_URL}/api/dfs", params={"league": league, "app": "all"},
                          headers=HEADERS, timeout=30)
        snippet_len = 300
        DEBUG_LOG.append({"endpoint": f"dfs/{league}", "url": r.url, "status": r.status_code,
                           "body_snippet": r.text[:snippet_len]})
        if r.status_code != 200:
            log(f"  dfs/{league}: HTTP {r.status_code} — {r.text[:200]}")
            return None
        data = r.json()
        league_block = data.get("results", {}).get(league, {})
        if not isinstance(league_block, dict):
            return None
        props = []
        for app_name, tiers in league_block.items():
            if not isinstance(tiers, dict):
                continue
            for tier_name, raw_list in tiers.items():
                remapped = _flatten_meta_prefixed_list(raw_list)
                for rec in remapped:
                    rec["dfs_app"] = rec.get("dfs_app") or app_name
                    rec["payout_tier"] = tier_name
                props.extend(remapped)
        if not props:
            return None
        return {"props": props, "apps": data.get("metadata", {}).get("apps_included", ["PP", "UD"])}
    except Exception as e:
        DEBUG_LOG.append({"endpoint": f"dfs/{league}", "error": str(e)[:300]})
        log(f"  dfs/{league}: error — {e}")
        return None


def fetch_sportsbook(league: str) -> dict | None:
    try:
        r = requests.get(f"{BASE_URL}/api/sportsbook", params={"leagues": league},
                          headers=HEADERS, timeout=30)
        snippet_len = 300
        DEBUG_LOG.append({"endpoint": f"sportsbook/{league}", "url": r.url, "status": r.status_code,
                           "body_snippet": r.text[:snippet_len]})
        if r.status_code != 200:
            log(f"  sportsbook/{league}: HTTP {r.status_code} — {r.text[:200]}")
            return None
        data = r.json()
        raw_list = data.get("results", {}).get(league, [])
        props = _flatten_meta_prefixed_list(raw_list)
        if not props:
            return None
        return {"props": props}
    except Exception as e:
        DEBUG_LOG.append({"endpoint": f"sportsbook/{league}", "error": str(e)[:300]})
        log(f"  sportsbook/{league}: error — {e}")
        return None


def push_files(files_payload: dict) -> int:
    github_token = os.environ["GITHUB_TOKEN"]
    if not _rate_limit_ok(github_token):
        return 0
    for attempt in range(6):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={"files": files_payload},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (409, 403, 429) and attempt < 5:
            base_wait = min((attempt + 1) * 8, 60)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist {resp.status_code} (conflict or rate limit) — retrying in {wait:.1f}s (attempt {attempt+1}/6)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget for this shared token before
    doing any writes. With ~30 scripts sharing one token/Gist, the hourly
    5000-request budget can run dry during a busy stretch (confirmed real:
    2026-07-25 06:17-06:40 UTC, 403 'API rate limit exceeded for user ID').
    When that happens, skip this run cleanly (exit 0) instead of burning
    retries against an already-exhausted budget and getting flagged as a
    failure -- the next scheduled run picks the data back up once the
    hourly window resets."""
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} requests left this hour) -- skipping this run cleanly, next scheduled run will pick it up")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) -- proceeding anyway")
    return True


def main() -> int:
    if not os.environ.get("GITHUB_TOKEN"):
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    total_props = 0

    for league in LEAGUES:
        sport_key = league.upper()

        dfs_result = fetch_dfs(league)
        if dfs_result:
            n = len(dfs_result["props"])
            total_props += n
            log(f"  dfs/{league}: {n} props")
            files_payload[f"betcouncil_favoredprops_dfs_{sport_key}.json"] = {
                "content": json.dumps({
                    "source": "favoredprops_dfs", "league": sport_key,
                    "captured_at": now_iso, "apps": dfs_result.get("apps", ["PP", "UD"]),
                    "props": dfs_result["props"],
                })
            }

        sb_result = fetch_sportsbook(league)
        if sb_result:
            n = len(sb_result["props"])
            total_props += n
            log(f"  sportsbook/{league}: {n} props")
            files_payload[f"betcouncil_favoredprops_sportsbook_{sport_key}.json"] = {
                "content": json.dumps({
                    "source": "favoredprops_sportsbook", "league": sport_key,
                    "captured_at": now_iso, "props": sb_result["props"],
                })
            }

    if not files_payload:
        # Every league came back empty/failed — genuinely fatal, don't
        # push nothing and call it success. A single empty league (e.g.
        # NFL in July) is fine and expected; all of them empty means the
        # API itself is down or changed shape.
        log("FATAL: zero leagues returned data — API may be down or changed")
        files_payload["betcouncil_favoredprops_debug.json"] = {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG}, indent=2)
        }
        push_files(files_payload)
        return 1

    log(f"Total: {total_props} props across {len(files_payload)} files")
    files_payload["betcouncil_favoredprops_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG}, indent=2)
    }
    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files to Gist")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
