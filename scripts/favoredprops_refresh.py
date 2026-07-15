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

Both return {"props": [...]} already in the shape BetCouncil's
fetch_favoredprops_from_gist() expects — no reshaping needed, just pass
the response straight through with a captured_at/source wrapper and push
to the shared Gist as betcouncil_favoredprops_{kind}_{SPORT}.json.

No other code changes are needed for this script to light up the New
Bettor "How This Compares" panel, Slip Analyzer, and Player Lookup —
fetch_favoredprops_from_gist() and get_favoredprops_match() in
fetchers.py already read these exact filenames.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

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


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_dfs(league: str) -> dict | None:
    try:
        r = requests.get(f"{BASE_URL}/api/dfs", params={"league": league, "app": "all"},
                          headers=HEADERS, timeout=30)
        DEBUG_LOG.append({"endpoint": f"dfs/{league}", "url": r.url, "status": r.status_code,
                           "body_snippet": r.text[:300]})
        if r.status_code != 200:
            log(f"  dfs/{league}: HTTP {r.status_code} — {r.text[:200]}")
            return None
        data = r.json()
        props = data.get("props", data if isinstance(data, list) else [])
        if not props:
            return None
        return {"props": props, "apps": data.get("apps", ["PP", "UD"])} if isinstance(data, dict) else {"props": props}
    except Exception as e:
        DEBUG_LOG.append({"endpoint": f"dfs/{league}", "error": str(e)[:300]})
        log(f"  dfs/{league}: error — {e}")
        return None


def fetch_sportsbook(league: str) -> dict | None:
    try:
        r = requests.get(f"{BASE_URL}/api/sportsbook", params={"leagues": league},
                          headers=HEADERS, timeout=30)
        DEBUG_LOG.append({"endpoint": f"sportsbook/{league}", "url": r.url, "status": r.status_code,
                           "body_snippet": r.text[:300]})
        if r.status_code != 200:
            log(f"  sportsbook/{league}: HTTP {r.status_code} — {r.text[:200]}")
            return None
        data = r.json()
        props = data.get("props", data if isinstance(data, list) else [])
        if not props:
            return None
        return {"props": props}
    except Exception as e:
        DEBUG_LOG.append({"endpoint": f"sportsbook/{league}", "error": str(e)[:300]})
        log(f"  sportsbook/{league}: error — {e}")
        return None


def push_files(files_payload: dict) -> int:
    github_token = os.environ["GITHUB_TOKEN"]
    for attempt in range(4):
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
        if resp.status_code == 409 and attempt < 3:
            wait = (attempt + 1) * 8
            log(f"Gist 409 conflict (concurrent write) — retrying in {wait}s (attempt {attempt+1}/4)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


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
