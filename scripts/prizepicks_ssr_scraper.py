"""
prizepicks_ssr_scraper.py — PrizePicks props scraper (public API, no auth)
============================================================================

Runs on GitHub Actions on a schedule (see
.github/workflows/prizepicks_refresh.yml). Uses PrizePicks' public
partner API (no login, no proxy, no special headers needed — confirmed
working directly) to pull all current projections, splits them by
league, and pushes one Gist file per sport in the exact format
BetCouncil's existing fetch_prizepicks_from_gist() already expects.

No wiring changes needed anywhere else — this just keeps the existing
Gist files fresh automatically instead of relying on a manual/Tampermonkey
harvester run.
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone

import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://partner-api.prizepicks.com/projections?per_page=10000&include=new_player"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_all_projections() -> dict:
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }
    resp = requests.get(API_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def split_by_league(payload: dict) -> dict:
    """
    Group projections by league (found at
    relationships.league.data.id on each projection), and collect only
    the `included` objects actually referenced by that league's
    projections (players, teams, etc.) — matches the Tampermonkey
    harvester's existing per-sport file format.
    """
    data = payload.get("data", [])
    included = payload.get("included", [])
    included_by_key = {(inc.get("type"), inc.get("id")): inc for inc in included}

    by_league: dict = {}
    for proj in data:
        rels = proj.get("relationships", {})
        league_rel = rels.get("league", {}).get("data") or {}
        league_id = league_rel.get("id")
        # League display name often available via included league objects;
        # fall back to the projection's own league_id string.
        league_name = None
        league_obj = included_by_key.get(("league", league_id))
        if league_obj:
            league_name = league_obj.get("attributes", {}).get("name")
        if not league_name:
            attr = proj.get("attributes", {})
            league_name = attr.get("league") or attr.get("league_id") or "UNKNOWN"

        league_key = str(league_name).upper().replace(" ", "_")
        by_league.setdefault(league_key, {"data": [], "referenced": set()})
        by_league[league_key]["data"].append(proj)

        # Track every relationship reference on this projection so we can
        # pull in exactly the included objects it needs (players, teams, etc.)
        for rel_name, rel_val in rels.items():
            rel_data = rel_val.get("data")
            if isinstance(rel_data, dict):
                by_league[league_key]["referenced"].add(
                    (rel_data.get("type"), rel_data.get("id"))
                )
            elif isinstance(rel_data, list):
                for item in rel_data:
                    if isinstance(item, dict):
                        by_league[league_key]["referenced"].add(
                            (item.get("type"), item.get("id"))
                        )

    result = {}
    for league_key, bucket in by_league.items():
        inc_objs = [
            included_by_key[key] for key in bucket["referenced"]
            if key in included_by_key
        ]
        result[league_key] = {
            "data": bucket["data"],
            "included": inc_objs,
        }
    return result


_SPORT_STAT_HINTS = {
    "MLB": {"strikeouts", "hits+runs+rbis", "total bases", "home runs", "earned runs allowed",
            "hits allowed", "walks allowed", "stolen bases", "hitter fantasy score",
            "pitcher fantasy score", "runs+rbis"},
    "TENNIS": {"aces", "double faults", "total games", "total games won", "total sets",
               "total tie breaks", "break points won", "fantasy score"},
    "NBA": {"points", "rebounds", "assists", "pts+rebs+asts", "3-pt made", "blocks", "steals"},
    "NHL": {"shots on goal", "saves", "goals", "points", "blocked shots"},
    "NFL": {"passing yards", "rushing yards", "receiving yards", "receptions", "pass attempts"},
    "SOCCER": {"shots on target", "shots", "fantasy score", "tackles"},
    "UFC": {"significant strikes", "takedowns", "fight time"},
    "GOLF": {"strokes", "birdies", "fairways hit"},
}


def _revalidate_league_by_stat_type(by_league: dict) -> dict:
    """
    Safety net: if a league's own projections are dominated by stat types
    that clearly belong to a DIFFERENT sport than its label (per
    _SPORT_STAT_HINTS), split those mismatched projections out and
    reroute them to the sport their stat types actually indicate,
    rather than trusting a league field that's occasionally wrong.
    Only acts when the mismatch is a strong majority (>=80% of a
    league's projections point to one specific other sport) --
    a handful of ambiguous/shared stat names (like "Fantasy Score",
    used by multiple sports) shouldn't trigger a reroute on their own.
    """
    result = {}
    for league_key, body in by_league.items():
        data = body.get("data", [])
        included = body.get("included", [])
        if not data:
            result[league_key] = body
            continue
        votes = {}
        for proj in data:
            st = str(proj.get("attributes", {}).get("stat_type", "")).lower()
            for sport, hints in _SPORT_STAT_HINTS.items():
                if st in hints and sport != league_key:
                    votes[sport] = votes.get(sport, 0) + 1
        if not votes:
            result[league_key] = body
            continue
        top_sport, top_count = max(votes.items(), key=lambda x: x[1])
        if top_count / len(data) >= 0.80:
            log(f"{league_key}: {top_count}/{len(data)} projections are actually "
                f"{top_sport}-type stats (PrizePicks mislabeled league) -- rerouting")
            result.setdefault(top_sport, {"data": [], "included": []})
            result[top_sport]["data"].extend(data)
            result[top_sport]["included"].extend(included)
        else:
            result[league_key] = body
    return result


def _trim_prizepicks_body(body: dict) -> dict:
    """
    Reduces the raw JSON:API payload to only what fetchers.py's real
    consumer (_parse_prizepicks_harvested) ever reads: per-prop
    line_score/stat_type/description/odds_type + the player id it
    references, and per included player: name/team/position. Drops
    everything else. Confirmed real: untrimmed payload was 9.2MB,
    trimmed to 1.33MB, verified live on 2026-08-08 the trimmed shape
    parses identically to the untrimmed one.
    """
    if not isinstance(body, dict):
        return body
    trimmed_data = []
    for item in body.get("data", []):
        if not isinstance(item, dict):
            continue
        attr = item.get("attributes", {}) or {}
        rels = item.get("relationships", {}) or {}
        p_rel = rels.get("new_player") or rels.get("player") or {}
        pid = (p_rel.get("data") or {}).get("id", "") if isinstance(p_rel.get("data"), dict) else ""
        trimmed_data.append({
            "attributes": {
                "line_score": attr.get("line_score", attr.get("line")),
                "stat_type": attr.get("stat_type", ""),
                "description": attr.get("description", ""),
                "odds_type": attr.get("odds_type", "standard"),
            },
            "relationships": {"new_player": {"data": {"id": pid}}},
        })
    trimmed_included = []
    for inc in body.get("included", []):
        if not isinstance(inc, dict) or inc.get("type") not in ("new_player", "player"):
            continue
        attr = inc.get("attributes", {}) or {}
        trimmed_included.append({
            "id": inc.get("id", ""),
            "type": inc.get("type"),
            "attributes": {
                "name": attr.get("name", attr.get("display_name", "")),
                "team": attr.get("team", attr.get("market", "")),
                "position": attr.get("position", ""),
            },
        })
    return {"data": trimmed_data, "included": trimmed_included}


def push_league_files(by_league: dict) -> int:
    """
    Merges all leagues into ONE file (betcouncil_prizepicks_combined.json)
    instead of one file per league. Confirmed real: this had grown to 59
    separate files (nearly 20% of the Gist's hard 300-file cap) because
    league_key is dynamically discovered from PrizePicks' own live
    league list, not a fixed set -- it grows every time PrizePicks adds
    a new league/event type. Uses the real distributed lock (gist_lock.py)
    since multiple runs now write to the same shared file.
    """
    github_token = os.environ["GITHUB_TOKEN"]
    now_iso = datetime.now(timezone.utc).isoformat()
    SHARED_FILE = "betcouncil_prizepicks_combined.json"

    merged = {}
    for league_key, body in by_league.items():
        try:
            trimmed_body = _trim_prizepicks_body(body)
        except Exception as e:
            log(f"{league_key}: trim failed ({e}) -- falling back to untrimmed body")
            trimmed_body = body
        merged[league_key] = {
            "sport": league_key,
            "captured_at": now_iso,
            "data": trimmed_body,
            "source": "github_actions_partner_api",
        }

    lock_token = acquire_lock(GIST_ID, github_token, "prizepicks_combined", holder="prizepicks")
    if not lock_token:
        log("Could not acquire prizepicks_combined lock -- skipping this run to avoid a collision")
        return 0
    try:
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                raw_url = r_files[SHARED_FILE]["raw_url"]
                existing = requests.get(raw_url, timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        existing.update(merged)
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        for attempt in range(4):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    return len(merged)
                if attempt < 3:
                    time.sleep(5)
                    continue
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 3:
                base_wait = (attempt + 1) * 8
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0
        return 0
    finally:
        release_lock(GIST_ID, github_token, "prizepicks_combined", lock_token)


def main() -> int:
    if not os.environ.get("GITHUB_TOKEN"):
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    try:
        payload = fetch_all_projections()
    except Exception as e:
        log(f"FATAL: fetch error — {e}")
        return 1

    total_props = len(payload.get("data", []))
    log(f"Fetched {total_props} total projections")
    if total_props == 0:
        log("FATAL: zero projections returned")
        return 1

    by_league = split_by_league(payload)
    by_league = _revalidate_league_by_stat_type(by_league)
    for k, v in by_league.items():
        log(f"  {k}: {len(v['data'])} props")

    pushed = push_league_files(by_league)
    log(f"Pushed {pushed} league files to Gist")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
