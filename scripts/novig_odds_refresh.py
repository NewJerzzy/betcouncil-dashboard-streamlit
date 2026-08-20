"""
novig_odds_refresh.py — Novig exchange odds via The Odds API (dedicated key)
================================================================================

Uses a SEPARATE Odds API account/key (ODDS_API_KEY_NOVIG) from the one
already used for MLB player props (ODDS_API_KEY) -- a completely separate
500-credit/month budget, not shared with existing usage. Confirmed live
against The Odds API's own official bookmaker list (docs.the-odds-api.com/
sports-odds-data/bookmaker-apis.html) before building: Novig is listed
under "US Exchanges" (region key us_ex, bookmaker key novig) with no
"paid subscriptions only" note, unlike several others on that same list.

Uses the main /sports/{sport}/odds endpoint (all of today's games in ONE
call), not the per-event props endpoint the other script needs -- Novig
here is game-level (moneyline/spread/total), not player props, so this is
far cheaper: bookmakers=novig with 3 markets costs ~3 credits per call
regardless of how many games are in the slate (specifying 1-10
bookmakers via `bookmakers=` counts as 1 region-equivalent per The Odds
API's own pricing rule), vs ~8-26 credits PER EVENT for props.

Not independently verified byte-for-byte before this first deploy (this
sandbox can't reach api.the-odds-api.com -- not in the network allowlist).
Ships with debug logging of the real x-requests-remaining header so
actual credit burn is visible from day one, and the response shape is
parsed defensively with a debug dump of the first real event if anything
doesn't match, same process as every other first-deploy script this
session.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import random
import time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.the-odds-api.com/v4"
# Real fix (2026-08-20): ODDS_API_KEY_NOVIG confirmed missing from
# Secrets, causing a 100% failure rate every run. Falls back to the
# existing, working ODDS_API_KEY (same provider) if the dedicated key
# isn't set. A dedicated key still takes priority if added later.
API_KEY = os.environ.get("ODDS_API_KEY_NOVIG") or os.environ.get("ODDS_API_KEY", "")

SPORT_KEYS = {"MLB": "baseball_mlb", "NFL": "americanfootball_nfl"}
MARKETS = "h2h,spreads,totals"

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_novig_odds(sport_key: str) -> list | None:
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    try:
        r = requests.get(
            url,
            params={
                "apiKey": API_KEY,
                "bookmakers": "novig",
                "markets": MARKETS,
                "oddsFormat": "american",
                "dateFormat": "iso",
            },
            timeout=20,
        )
    except Exception as e:
        DEBUG_LOG.append({"sport": sport_key, "error": str(e)[:300]})
        log(f"  {sport_key}: error — {e}")
        return None

    _remaining = r.headers.get("x-requests-remaining")
    _used = r.headers.get("x-requests-used")
    DEBUG_LOG.append({
        "sport": sport_key, "status": r.status_code,
        "x_requests_remaining": _remaining, "x_requests_used": _used,
        "body_snippet": r.text[:3000],
    })
    log(f"  {sport_key}: HTTP {r.status_code}, credits remaining={_remaining}, used={_used}")

    if r.status_code == 401:
        log(f"  {sport_key}: 401 — API key rejected")
        return None
    if r.status_code == 422:
        log(f"  {sport_key}: 422 — likely invalid market/bookmaker param, see debug body")
        return None
    if r.status_code != 200:
        log(f"  {sport_key}: HTTP {r.status_code} — {r.text[:200]}")
        return None

    try:
        events = r.json()
    except Exception as e:
        DEBUG_LOG.append({"sport": sport_key, "json_error": str(e)[:300]})
        return None

    if not isinstance(events, list):
        DEBUG_LOG.append({"sport": sport_key, "note": "unrecognized_shape",
                           "top_level_type": str(type(events))})
        return None

    if events:
        DEBUG_LOG.append({"sport": sport_key, "note": "sample_event_full",
                           "sample": json.dumps(events[0], indent=2)[:4000]})

    return events


def _normalize_event(ev: dict, sport: str) -> dict:
    novig_book = next((b for b in ev.get("bookmakers", []) if b.get("key") == "novig"), None)
    markets_out = {}
    if novig_book:
        for m in novig_book.get("markets", []):
            markets_out[m.get("key", "")] = [
                {"name": o.get("name"), "price": o.get("price"), "point": o.get("point")}
                for o in m.get("outcomes", [])
            ]
    return {
        "sport": sport,
        "event_id": ev.get("id"),
        "home_team": ev.get("home_team"),
        "away_team": ev.get("away_team"),
        "commence_time": ev.get("commence_time"),
        "novig_markets": markets_out,
        "novig_last_update": novig_book.get("last_update") if novig_book else None,
    }


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} left this hour) -- skipping cleanly")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) -- proceeding anyway")
    return True


def push_files(files_payload: dict, github_token: str) -> int:
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
        if resp.status_code in (409, 403, 429) and attempt < 5:
            base_wait = min((attempt + 1) * 8, 60)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist {resp.status_code} — retrying in {wait:.1f}s (attempt {attempt+1}/6)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token or not API_KEY:
        log("FATAL: GITHUB_TOKEN or ODDS_API_KEY_NOVIG not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    dry_run = "--dry-run" in sys.argv

    all_events = []
    for sport, sport_key in SPORT_KEYS.items():
        log(f"Fetching Novig odds for {sport}...")
        events = fetch_novig_odds(sport_key)
        if events is None:
            log(f"  {sport}: failed, skipping")
            continue
        log(f"  {sport}: {len(events)} events")
        all_events.extend(_normalize_event(e, sport) for e in events)

    log(f"Total: {len(all_events)} events across {len(SPORT_KEYS)} sports")

    if not all_events:
        any_200 = any(r.get("status") == 200 for r in DEBUG_LOG)
        log("No Novig events captured" + (" (calls succeeded, just empty right now)" if any_200 else " (calls failed)"))
        if not dry_run:
            push_files({
                "betcouncil_novig_odds_debug.json": {
                    "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
                }
            }, github_token)
        return 0 if any_200 else 1

    if dry_run:
        log("--dry-run: skipping Gist push")
        return 0

    files_payload = {
        "betcouncil_novig_odds.json": {
            "content": json.dumps({"source": "novig_via_odds_api", "captured_at": now_iso, "events": all_events})
        },
        "betcouncil_novig_odds_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
        },
    }
    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
