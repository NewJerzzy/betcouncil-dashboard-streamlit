"""
unabated_refresh.py — Unabated sharp-line comparison (public API, no auth)
================================================================================

Unabated (unabated.com) — cross-book sharp-line comparison, plus DFS
platform (PrizePicks/Underdog/Pick6) line tracking.

First attempt at unabated.com/api/lines (the existing browser-harvester's
endpoint) was confirmed dead server-side — returns a generic Next.js 404
HTML page, not JSON (verified via a live GitHub Actions run 2026-07-18).

Second attempt, base https://data.unabated.com, per a secondary session's
claim — NOT yet independently verified from this sandbox (data.unabated.com
isn't in the network allowlist), being tested live via Actions before
trusting it, same standard applied to every claimed endpoint in this repo
(a prior Smarkets claim from the same kind of source turned out to be
exactly right after verification; treat this the same way — test, don't
assume either way):

    GET /market/{sport}/props/odds     — prop lines (mlb/nfl/wnba/nhl/nba/pga/ufc/cbb/cfb)
    GET /market/{sport}/straight/odds  — game lines w/ no-vig (Bet365/Caesars/TheScoreUS)
    GET /players/{sport}               — player name + ID map
    GET /bet-types                     — bet type ID -> name map

Required headers per the claim: standard browser User-Agent + Referer
https://unabated.com/ — no auth token claimed.

REAL SCHEMA CONFIRMED for the payload shape (not guessed): a prior
session manually pushed real, live data for all 4 platform variants
straight to the Gist on 2026-07-18 without committing any code (1,472
Pick6 lines, 624 sportsbook-comparison lines independently confirmed by
inspecting that pushed data directly). This script's output shape is
built against that actual captured payload:

    pick6/prizepicks/underdog: {platform, league, captured_at, source,
        lines: [{player_name, player_id, position, event, event_id,
                 event_start, is_live, stat_type, bet_type_id, period,
                 phase, line, price, status_id, market_source_id}]}

    straight: {market_type, league, captured_at, source, books: [...],
        lines: [{event, event_id, event_start, is_live, period, phase,
                 bet_type, bet_type_id, side_index, team_id, rotation_num,
                 points, price, source_id, book}]}

market_source_id / source_id conventions already established elsewhere
in this repo: 36=theScore Bet, 78=Bet365. Platform split (which
market_source_id maps to PrizePicks/Underdog/Pick6) not yet confirmed —
first live run dumps the raw response so this can be mapped correctly
rather than guessed.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://data.unabated.com"
LEAGUE = "mlb"

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


def fetch_json(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
    except Exception as e:
        DEBUG_LOG.append({"url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"url": url, "status": r.status_code, "body_snippet": r.text[:500]})
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
    any_data = False

    props_resp = fetch_json(f"{BASE_URL}/market/{LEAGUE}/props/odds")
    log(f"props response type: {type(props_resp).__name__}, "
        f"{'keys=' + str(list(props_resp.keys())) if isinstance(props_resp, dict) else ''}")

    straight_resp = fetch_json(f"{BASE_URL}/market/{LEAGUE}/straight/odds")
    log(f"straight response type: {type(straight_resp).__name__}, "
        f"{'keys=' + str(list(straight_resp.keys())) if isinstance(straight_resp, dict) else ''}")

    files_payload["betcouncil_unabated_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:10],
                                "props_got_data": props_resp is not None,
                                "straight_got_data": straight_resp is not None}, indent=2, default=str)
    }

    if not props_resp and not straight_resp:
        log("No data returned from either endpoint — see debug log")
        push_files(files_payload, github_token)
        return 1

    # Structure unconfirmed live -- push raw responses as-is for manual
    # inspection rather than guessing at the platform split (which
    # market_source_id is PrizePicks vs Underdog vs Pick6) blind.
    if props_resp:
        any_data = True
        files_payload[f"betcouncil_unabated_props_raw_{LEAGUE}.json"] = {
            "content": json.dumps({"source": "unabated", "league": LEAGUE,
                                    "captured_at": now_iso, "raw": props_resp}, default=str)
        }
    if straight_resp:
        any_data = True
        files_payload[f"betcouncil_unabated_straight_raw_{LEAGUE}.json"] = {
            "content": json.dumps({"source": "unabated", "league": LEAGUE,
                                    "captured_at": now_iso, "raw": straight_resp}, default=str)
        }

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files (raw responses captured for schema inspection)")
    return 0 if pushed > 0 and any_data else 1


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
