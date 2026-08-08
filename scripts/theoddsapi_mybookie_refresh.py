"""
theoddsapi_mybookie_refresh.py — MyBookie game lines via The Odds API
(the-odds-api.com -- a separate company from odds-api.io, despite the
similar name).

================================================================================
Confirmed live this session: 18/18 real MLB games returned with
`mybookieag` odds, at a real cost of 3 credits for the FULL slate (not
per-game) -- confirmed via the `x-requests-last` response header.
Real response shape (American odds already, no conversion needed):
    {"key": "mybookieag", "title": "MyBookie.ag", "markets": [
        {"key": "h2h", "outcomes": [
            {"name": "Tampa Bay Rays", "price": 355},
            {"name": "Toronto Blue Jays", "price": -430}]},
        {"key": "spreads", "outcomes": [
            {"name": "Tampa Bay Rays", "price": -250, "point": 1.5},
            {"name": "Toronto Blue Jays", "price": 190, "point": -1.5}]},
        {"key": "totals", "outcomes": [
            {"name": "Over", "price": -143, "point": 4.5},
            {"name": "Under", "price": 120, "point": 4.5}]}
    ]}

Player props confirmed NOT available for MyBookie on this provider --
checked directly against real pending games; the 6 books that do return
props here are fanduel/draftkings/bovada/betmgm/betonlineag/betrivers,
MyBookie isn't among them. This script is game lines only, by design,
not an oversight.

Uses its own dedicated key (ODDS_API_KEY_MYBOOKIE, a separate testing
account) -- NOT the production ODDS_API_KEY, which already powers the
existing pitcher-strikeouts/HR/hits/total-bases props scraper and must
not be touched by this script.

Pushes to betcouncil_theoddsapi_mybookie_{sport}.json.
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.the-odds-api.com/v4"
BOOKMAKER = "mybookieag"

SPORT_KEYS = {
    "MLB": "baseball_mlb",
    # NFL/NBA/NHL use The Odds API's standard documented sport keys --
    # only MLB has been live-verified on this specific account so far.
    # Not expected to be risky if wrong (a bad key just 404s/returns
    # empty for that sport, not a crash), but worth live-testing before
    # assuming these are definitely populated with real MyBookie data.
    "NFL": "americanfootball_nfl",
    "NBA": "basketball_nba",
    "NHL": "icehockey_nhl",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BetCouncilResearch/1.0)"}
DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_sport_lines(sport: str, api_key: str) -> list:
    sport_key = SPORT_KEYS.get(sport)
    if not sport_key:
        return []
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key, "regions": "us", "markets": "h2h,spreads,totals",
        "bookmakers": BOOKMAKER, "oddsFormat": "american",
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "error": str(e)})
        return []
    DEBUG_LOG.append({
        "sport": sport, "status": r.status_code, "bytes": len(r.content),
        "requests_used": r.headers.get("x-requests-last"),
        "requests_remaining": r.headers.get("x-requests-remaining"),
        "body_snippet": r.text[:400],
    })
    if r.status_code != 200:
        return []
    try:
        events = r.json()
    except json.JSONDecodeError:
        return []

    games = []
    for event in events:
        home_team = event.get("home_team", "")
        away_team = event.get("away_team", "")
        bm = next((b for b in event.get("bookmakers", []) if b.get("key") == BOOKMAKER), None)
        if not bm:
            continue
        by_market = {m.get("key"): m.get("outcomes", []) for m in bm.get("markets", [])}
        h2h = by_market.get("h2h", [])
        spreads = by_market.get("spreads", [])
        totals = by_market.get("totals", [])

        def _find(outcomes, name):
            return next((o for o in outcomes if o.get("name") == name), {})

        home_ml = _find(h2h, home_team)
        away_ml = _find(h2h, away_team)
        home_spread = _find(spreads, home_team)
        over = _find(totals, "Over")
        under = _find(totals, "Under")

        if not (home_ml or home_spread or over):
            continue
        games.append({
            "event_id": event.get("id"),
            "home_team": home_team, "away_team": away_team,
            "home_ml": home_ml.get("price"), "away_ml": away_ml.get("price"),
            "spread_hdp": home_spread.get("point"),
            "spread_home_odds": home_spread.get("price"),
            "spread_away_odds": _find(spreads, away_team).get("price"),
            "total_hdp": over.get("point"),
            "over_odds": over.get("price"), "under_odds": under.get("price"),
        })
    return games


def push_files(files_payload: dict, github_token: str) -> int:
    """
    Merges into the shared evbets_combined.json using the real
    distributed lock (gist_lock.py) -- the earlier read-verify-retry
    mitigation reduced collisions but was confirmed insufficient under
    real concurrent load; the lock actually eliminates them (verified
    via timing proof earlier this session).
    """
    SHARED_FILE = "betcouncil_evbets_combined.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_theoddsapi_mybookie_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

    lock_token = acquire_lock(GIST_ID, github_token, "evbets_combined", holder="theoddsapi_mybookie")
    if not lock_token:
        log("Could not acquire evbets_combined lock -- skipping this run to avoid a collision")
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
        existing["theoddsapi_mybookie"] = merged
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
                    return len(files_payload)
                if attempt < 3:
                    time.sleep(5)
                    continue
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 3:
                wait = min((attempt + 1) * 8, 30)
                log(f"Gist {resp.status_code} -- retrying in {wait}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0
        return 0
    finally:
        release_lock(GIST_ID, github_token, "evbets_combined", lock_token)


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
    api_key = os.environ.get("ODDS_API_KEY_MYBOOKIE")
    if not github_token or not api_key:
        log("FATAL: GITHUB_TOKEN or ODDS_API_KEY_MYBOOKIE not set")
        return 1

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport in SPORT_KEYS:
        try:
            games = fetch_sport_lines(sport, api_key)
        except Exception as e:
            log(f"{sport}: error — {e}")
            games = []
        log(f"{sport}: {len(games)} MyBookie games")
        if games:
            any_data = True
            files_payload[f"betcouncil_theoddsapi_mybookie_{sport}.json"] = {
                "content": json.dumps({
                    "source": "the-odds-api.com", "bookmaker": "MyBookie",
                    "sport": sport, "captured_at": now_iso, "games": games,
                })
            }

    files_payload["betcouncil_theoddsapi_mybookie_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:10]}, indent=2)
    }

    if not any_data:
        log("No MyBookie games captured this run — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
