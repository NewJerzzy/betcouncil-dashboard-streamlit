"""
bobbys_bets_props_refresh.py — Bobby's Bets full props board
====================================================================

Confirmed live 2026-08-01/02: app.bobbysbets.com, real nginx/Ubuntu
serving a clean JSON API, no auth, no Cloudflare.

This covers the ONE piece deliberately left out of the live in-app
fetchers (fetch_bobbys_bets_picks/briefing/scoreboard/weather/
best_prices, all already wired) -- /api/{sport}/props, confirmed 5.2MB
for MLB alone. Too large to fetch live on every board load (would slow
every single board load down for every user), so this runs on a
schedule instead and pushes a trimmed, board-relevant subset to the
Gist -- same reasoning already applied elsewhere in this codebase
(BettingPros props, GamblingForecast) for any large per-sport payload.

Trims each prop down to the fields BetCouncil's own board actually
uses (player/stat/line/side/odds/hit-rates/streak/DK ids) and drops
the large last5/10/20_values arrays and headshot URLs, which cuts the
real payload roughly in half while keeping everything genuinely useful.
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SPORTS = ["mlb", "nba", "wnba", "nfl", "nhl"]
BASE_URL = "https://app.bobbysbets.com"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "application/json"}

TRIM_FIELDS = [
    "player_name", "player_id", "player_team", "player_position",
    "opponent_team", "home_team", "stat_category", "line", "label",
    "odds_american", "odds_decimal", "hit_rate_l5", "hit_rate_l10",
    "hit_rate_l15", "hit_rate_l20", "hit_rate_season", "hit_rate_all",
    "avg_stat_l10", "current_streak", "ev", "is_model_pick",
    "ml_probability", "dk_event_id", "dk_outcome_id", "game_date",
    "game_time", "is_pitcher_prop", "week",
]

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_sport_props(sport: str) -> list:
    try:
        r = requests.get(f"{BASE_URL}/api/{sport}/props", headers=HEADERS, timeout=30)
        DEBUG_LOG.append({"sport": sport, "status": r.status_code, "bytes": len(r.content)})
        if r.status_code != 200:
            return []
        data = r.json()
        props = data.get("props", []) if isinstance(data, dict) else data
        if not isinstance(props, list):
            return []
        trimmed = [{k: p.get(k) for k in TRIM_FIELDS if k in p} for p in props]
        log(f"{sport}: {len(trimmed)} props ({len(r.content):,} bytes raw)")
        return trimmed
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "error": str(e)[:200]})
        log(f"{sport}: error — {e}")
        return []


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} left) -- skipping this run cleanly")
            return False
    except Exception as e:
        log(f"rate_limit check failed (continuing anyway): {e}")
    return True


def push_files(files_payload: dict) -> int:
    github_token = os.environ["GITHUB_TOKEN"]
    if not _rate_limit_ok(github_token):
        return 0
    for attempt in range(6):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            # 200 doesn't guarantee content actually landed -- confirmed
            # real this session on 6 other scripts. Verify before trusting.
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 5:
                wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                time.sleep(wait)
                continue
            if missing:
                log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                return len(files_payload) - len(missing)
            return len(files_payload)
        if resp.status_code in (409, 403, 429) and attempt < 5:
            base_wait = min((attempt + 1) * 8, 60)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/6)")
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
    files_payload = {}
    any_data = False

    for sport in SPORTS:
        props = fetch_sport_props(sport)
        if props:
            any_data = True
        files_payload[f"betcouncil_bobbysbets_props_{sport}.json"] = {
            "content": json.dumps({"captured_at": now_iso, "sport": sport,
                                    "source": "bobbysbets_props", "props": props})
        }

    files_payload["betcouncil_bobbysbets_props_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15]}, indent=2)
    }

    if not any_data:
        log("No props captured across any sport -- pushing debug only, not overwriting existing data with empty")
        push_files({"betcouncil_bobbysbets_props_debug.json": files_payload["betcouncil_bobbysbets_props_debug.json"]})
        return 1

    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
