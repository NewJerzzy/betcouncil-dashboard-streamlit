"""
thescore_boxscores_refresh.py — theScore public API: MLB pitcher box lines
================================================================================

Extension of the already-vetted, already-live api.thescore.com integration
(thescore_scores_refresh.py, confirmed live this session, general
sports/scores app API -- not the GeoComply-gated sportsbook.thescore.bet
product). Covers endpoints that script doesn't touch: per-pitcher box
line and pitch-mix, reported live-verified by an external session (not
independently re-probed live by Claude from this sandbox -- api.thescore.com
isn't in this environment's network allowlist, same caveat as the existing
scores refresh script):

    GET https://api.thescore.com/mlb/events?day=YYYY-MM-DD
        -> today's games with event status + team objects

    GET https://api.thescore.com/mlb/events/{id}
        -> starting pitchers (season ERA/WHIP/pitch mix), box_score_uri

    GET https://api.thescore.com/mlb/box_scores/{id}
        -> per-pitcher box line: pitch count, K, BB, ERA, WHIP, H, HR
           allowed, ground/fly ball split, pitch-type velocity breakdown
           (FB/CRV/CH/etc.)

Reported NOT present (confirmed 404/null by the same external probe):
individual batter game stats per game, odds/timestamped_odds fields
(already covered separately by thescore_scores_refresh.py's own event
endpoint, unrelated to box scores), weather sub-URI.

Value proposition (deliberately modest -- most of this overlaps existing
sources): the post-game per-pitcher pitch-mix/box-line split is the one
piece not already covered by Baseball Savant or MLB Stats API, useful as
a box-score enrichment rather than a primary new signal.

Ships with the same debug logging as the existing scores script, so any
schema drift or unexpected shape is caught immediately on first live run
rather than silently producing empty/wrong data.

Pushes to betcouncil_thescore_boxscores_MLB.json.
"""

import json
import os
import sys
import random
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.thescore.com"
MAX_GAMES = 20  # cap per run -- box score + event detail is 2 calls per game

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str, label: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"label": label, "url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"label": label, "url": url, "status": r.status_code,
                       "body_snippet": r.text[:400]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def fetch_todays_events() -> list:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = fetch_json(f"{BASE_URL}/mlb/events?day={day}", "events_by_day")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("events", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def extract_pitcher_lines(box_score: dict) -> list:
    """
    Defensive extraction -- the exact nesting of pitcher box lines within
    the box_score payload wasn't independently confirmed by Claude, so
    this tries a few plausible shapes rather than assuming one. Any
    genuinely new/different shape gets caught in DEBUG_LOG's raw response
    snippet for the next round of fixes, same pattern as the existing
    scores script.
    """
    if not isinstance(box_score, dict):
        return []
    for key in ("pitching", "pitchers", "pitching_stats"):
        val = box_score.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            # e.g. {"home": [...], "away": [...]}
            combined = []
            for side in ("home", "away"):
                if isinstance(val.get(side), list):
                    combined.extend(val[side])
            if combined:
                return combined
    return []


def normalize() -> list:
    events = fetch_todays_events()
    if not events:
        return []

    games = []
    for ev in events[:MAX_GAMES]:
        if not isinstance(ev, dict):
            continue
        api_uri = ev.get("api_uri")
        event_id = ev.get("id") or (api_uri.rsplit("/", 1)[-1] if api_uri else None)
        if not event_id:
            continue

        detail = fetch_json(f"{BASE_URL}/mlb/events/{event_id}", f"event[{event_id}]")
        if not isinstance(detail, dict):
            continue

        box_score = fetch_json(f"{BASE_URL}/mlb/box_scores/{event_id}", f"box_score[{event_id}]")
        pitcher_lines = extract_pitcher_lines(box_score) if box_score else []

        games.append({
            "event_id": event_id,
            "home_team": (detail.get("home_team") or {}).get("name") or ev.get("home_team"),
            "away_team": (detail.get("away_team") or {}).get("name") or ev.get("away_team"),
            "game_date": detail.get("game_date") or ev.get("game_date"),
            "status": ev.get("status") or detail.get("status"),
            "starting_pitchers": detail.get("starting_pitchers") or detail.get("probable_pitchers"),
            "pitcher_box_lines": pitcher_lines,
        })
    return games


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(3):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 2:
            # Same shared-Gist collision risk as every other script writing
            # here -- real exponential backoff + jitter, not a fixed retry.
            base_wait = 10 * (2 ** attempt)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/3)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        games = normalize()
    except Exception as e:
        log(f"error — {e}")
        games = []

    files_payload = {
        "betcouncil_thescore_boxscores_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:25]}, indent=2)
        }
    }

    if not games:
        log("No games/box scores captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    log(f"MLB: {len(games)} games, {sum(len(g['pitcher_box_lines']) for g in games)} pitcher lines total")
    files_payload["betcouncil_thescore_boxscores_MLB.json"] = {
        "content": json.dumps({
            "source": "thescore_public_api", "sport": "MLB",
            "captured_at": now_iso, "games": games,
        })
    }

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
