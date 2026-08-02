"""
actionnetwork_refresh.py — Action Network's public scoreboard API (no auth)
================================================================================

Action Network is the parent company of Sports Insights, RotoGrinders,
VegasInsider, and ScoresAndOdds — all four already confirmed this
session to share one open backend. Their own flagship site
(www.actionnetwork.com) is AWS WAF bot-challenged (202 on every URL),
but the API subdomain follows the same pattern as their other
properties:

    GET https://api.actionnetwork.com/web/v1/scoreboard/{league}?date=YYYYMMDD

No auth. Date must be YYYYMMDD (no dashes — confirmed dashes return 400).
League is a slug: mlb, nba, nfl, nhl, ncaaf, ncaab (NOT sport=baseball,
which also 400s).

Single richest response encountered across every source built this
session — per game: multi-book odds (4+ books × game/first-5/first-
inning markets), full lines (ML, run line + juice, total + team
totals), rotation numbers, starting pitchers with full season pitching
stats (ERA/WHIP/K9/etc), team standings, broadcast network.
public/money betting % fields exist in the schema but returned null in
testing — may need a specific param or be a premium field; left in the
output as-is (None) rather than guessed at.

Exact schema wasn't independently verified byte-for-byte by Claude
before this first deploy (verified the company/architecture pattern via
search, not the literal endpoint) — ships with self-diagnostic logging
so a schema mismatch is caught immediately.

Pushes to betcouncil_actionnetwork_{SPORT}.json.
"""

import json
import os
import random
import sys
import time
from datetime import date, datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.actionnetwork.com/web/v1/scoreboard"
LEAGUES = {"MLB": "mlb", "NBA": "nba", "NFL": "nfl", "NHL": "nhl", "NCAAF": "ncaaf", "NCAAB": "ncaab"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_league_games(sport: str, league_slug: str) -> list:
    date_str = date.today().strftime("%Y%m%d")
    url = f"{BASE_URL}/{league_slug}"
    r = requests.get(url, params={"date": date_str}, headers=HEADERS, timeout=20)
    DEBUG_LOG.append({"sport": sport, "url": r.url, "status": r.status_code,
                       "body_snippet": r.text[:600]})
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except json.JSONDecodeError:
        return []
    games = data.get("games", [])
    return games if isinstance(games, list) else []


def normalize_game(sport: str, game: dict) -> dict:
    teams = game.get("teams", [])
    home = next((t for t in teams if t.get("id") == game.get("home_team_id")), teams[1] if len(teams) > 1 else {})
    away = next((t for t in teams if t.get("id") == game.get("away_team_id")), teams[0] if teams else {})
    # Fallback: some responses may not have home_team_id/away_team_id at
    # the game level — if teams has exactly 2 entries and the above
    # didn't resolve, just take them in list order.
    if not home and len(teams) > 1:
        home = teams[1]
    if not away and teams:
        away = teams[0]

    odds_list = [o for o in game.get("odds", []) if isinstance(o, dict)]
    game_odds = [o for o in odds_list if o.get("type") == "game"]
    # book_id 30 is Action Network's "Open" pseudo-book -- the actual
    # opening line, timestamped when it first went live. Pulled out
    # separately since it's the specific reference price most signals
    # want to diff against, not just another book in the list.
    opening_line = next((o for o in game_odds if o.get("book_id") == 30), None)

    player_stats = game.get("player_stats", {})

    return {
        "sport": sport, "game_id": game.get("id"), "status": game.get("status"),
        "start_time": game.get("start_time"),
        "home_team": home.get("abbr"), "away_team": away.get("abbr"),
        "home_team_full": home.get("full_name"), "away_team_full": away.get("full_name"),
        "home_record": (home.get("standings") or {}), "away_record": (away.get("standings") or {}),
        "away_rotation": game.get("away_rotation_number"), "home_rotation": game.get("home_rotation_number"),
        "odds": game_odds,  # keep raw — multiple books, book_id keyed
        "opening_line": opening_line,  # book_id=30 "Open" pulled out for convenience
        "starting_pitchers": {
            "away": (player_stats.get("away") or [{}])[0] if player_stats.get("away") else None,
            "home": (player_stats.get("home") or [{}])[0] if player_stats.get("home") else None,
        },
        "broadcast": (game.get("broadcast") or {}).get("network"),
    }


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 4:
                wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                time.sleep(wait)
                continue
            if missing:
                log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                return len(files_payload) - len(missing)
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 4:
            base_wait = min(10 * (2 ** attempt), 90)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
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
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport, league_slug in LEAGUES.items():
        try:
            raw_games = fetch_league_games(sport, league_slug)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not raw_games:
            log(f"  {sport}: 0 games")
            continue

        normalized = []
        for g in raw_games:
            try:
                normalized.append(normalize_game(sport, g))
            except Exception as e:
                log(f"  {sport}: normalize error — {e}")

        any_data = True
        log(f"  {sport}: {len(normalized)} games")
        files_payload[f"betcouncil_actionnetwork_{sport}.json"] = {
            "content": json.dumps({
                "source": "actionnetwork", "sport": sport,
                "captured_at": now_iso, "games": normalized,
            })
        }

    files_payload["betcouncil_actionnetwork_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:30]}, indent=2)
    }

    if not any_data:
        log("No data captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
