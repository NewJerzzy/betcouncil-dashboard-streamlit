"""
unabated_refresh.py — Unabated sharp-line comparison (public API attempt, no auth)
================================================================================

Unabated (unabated.com) — cross-book sharp-line comparison, plus DFS
platform (PrizePicks/Underdog/Pick6) line tracking. A browser-side
harvester for this already exists in app.py (`unabated.com/api/lines?
sport=X`, no special auth headers beyond Accept/Referer) — this script
tests whether that same endpoint is reachable server-side too, same as
several other sources this repo migrated off browser-only harvesting
once confirmed unnecessary (BetMGM, EVSharps, Action Network).

REAL SCHEMA CONFIRMED (not guessed): a prior session manually pushed real,
live data for all 4 variants straight to the Gist on 2026-07-18 without
committing any code (1,472 Pick6 lines, 624 sportsbook-comparison lines
confirmed). This script's output shape is built directly against that
actual captured payload:

    pick6/prizepicks/underdog: {platform, league, captured_at, source,
        lines: [{player_name, player_id, position, event, event_id,
                 event_start, is_live, stat_type, bet_type_id, period,
                 phase, line, price, status_id, market_source_id}]}

    straight: {market_type, league, captured_at, source, books: [...],
        lines: [{event, event_id, event_start, is_live, period, phase,
                 bet_type, bet_type_id, side_index, team_id, rotation_num,
                 points, price, source_id, book}]}

NOT independently verified live from this sandbox (unabated.com isn't in
this environment's network allowlist) — confirm on first live Actions
run whether this endpoint is really server-reachable or whether it needs
the existing browser-side harvester after all (in which case this script
will cleanly report zero data rather than crash, and the browser
harvester stays the real source).
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://unabated.com/api/lines"
LEAGUE = "MLB"

HEADERS = {
    "Accept": "application/json",
    "Referer": "https://unabated.com/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}

# bet_type_id / market_source_id conventions confirmed from real captured
# data + existing code (fetch_unabated_straight_from_gist already uses
# source_id 36=theScore Bet, 78=Bet365 elsewhere in this repo).
DFS_PLATFORMS = {
    "pick6": None,       # market_source_id filter TBD from live response
    "prizepicks": None,
    "underdog": None,
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(params: dict):
    try:
        r = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=25)
    except Exception as e:
        DEBUG_LOG.append({"params": params, "error": str(e)})
        return None
    DEBUG_LOG.append({"params": params, "status": r.status_code,
                       "body_snippet": r.text[:500]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def push_files(files_payload: dict, github_token: str) -> int:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": files_payload}, timeout=60,
    )
    if resp.status_code in (200, 201):
        return len(files_payload)
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}

    data = fetch_json({"sport": LEAGUE.lower()})
    log(f"raw response type: {type(data).__name__}, "
        f"{'keys=' + str(list(data.keys())) if isinstance(data, dict) else ''}")

    files_payload["betcouncil_unabated_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:10],
                                "got_data": data is not None}, indent=2, default=str)
    }

    if not data:
        log("No data returned — endpoint likely needs the existing browser-side "
            "harvester after all (CORS/session-cookie requirement), not server-reachable")
        push_files(files_payload, github_token)
        return 1

    # Structure unconfirmed live -- push the raw response as-is under a
    # single file for manual inspection rather than guessing at how to
    # split it into pick6/prizepicks/underdog/straight, which would risk
    # silently mis-splitting real data across the wrong files.
    files_payload["betcouncil_unabated_raw_MLB.json"] = {
        "content": json.dumps({"source": "unabated", "league": LEAGUE,
                                "captured_at": now_iso, "raw": data}, default=str)
    }
    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files (raw response captured for schema inspection)")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("UNHANDLED EXCEPTION:\n" + tb)
        try:
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                push_files({"betcouncil_unabated_debug.json": {
                    "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                            "error": "unhandled_exception", "traceback": tb}, indent=2)
                }}, token)
        except Exception:
            pass
        sys.exit(1)
