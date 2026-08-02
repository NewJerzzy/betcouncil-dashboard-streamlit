"""
kambi_refresh.py — Kambi's public offering API via BetRivers (no auth)
================================================================================

Kambi is a B2B sportsbook platform. In the US it currently powers BetRivers
(Rush Street Interactive) across 7 states -- all state operators return
identical data, so they're used here as fallbacks of each other, not
separate sources. Kambi does NOT power FanDuel/DraftKings/BetMGM/Caesars/
ESPN Bet -- this is BetRivers-quality data specifically, not a universal
aggregator, but it's a genuinely open, deep player-prop source (475+ props
per MLB game in prior research).

Confirmed live and fully public (via BetRivers' own JS bundle):
    GET https://eu.offering-api.kambicdn.com/offering/v2018/{operator}/
        event/group/{groupId}.json?lang=en_US&market=US&onlyAvailable=true
    GET https://eu.offering-api.kambicdn.com/offering/v2018/{operator}/
        betoffer/event/{eventId}.json?lang=en_US&market=US&onlyAvailable=true

lang=en_US and market=US are both required -- confirmed in prior research
that omitting either 400s. Odds are European decimal x1000 (1940 = 1.940 =
-106 American); lines are x1000 too (3500 = 3.5). Left in raw decimal form
here -- conversion happens on read, not on write, so the raw source value
is always recoverable if the conversion has a bug.

Not independently verified byte-for-byte by Claude before this first deploy
(built from prior research findings, not re-probed live from this sandbox --
kambicdn.com isn't in this environment's network allowlist). Ships with
debug logging so a schema drift or block is caught immediately on first
live run rather than silently producing nothing.

Pushes to betcouncil_kambi_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://eu.offering-api.kambicdn.com/offering/v2018"

# All 7 return identical data -- tried in order, first success wins.
OPERATORS = ["rsiusnj", "rsiuspa", "rsiusco", "rsiusin", "rsiusoh", "rsiusia", "rsiusva"]

# Group IDs confirmed via prior research probe.
GROUPS = {
    "MLB":  1000093616,
    "NBA":  1000093652,
    "WNBA": 1000174277,
    "NFL":  1000093656,
    "NCAAF": 1000093655,
    "NHL":  1000093657,
    "MLS":  1000095063,
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# Cap events per sport per run -- betoffer is a per-event fetch, and a full
# NFL/NCAAF slate could mean dozens of round trips otherwise.
MAX_EVENTS_PER_SPORT = 20

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str, params: dict, sport: str, label: str):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "label": label, "url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"sport": sport, "label": label, "url": r.url, "status": r.status_code,
                       "body_snippet": r.text[:400]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def fetch_events(operator: str, group_id: int, sport: str) -> list:
    data = fetch_json(
        f"{BASE_URL}/{operator}/event/group/{group_id}.json",
        {"lang": "en_US", "market": "US", "onlyAvailable": "true", "limit": 50},
        sport, f"events[{operator}]",
    )
    if not isinstance(data, dict):
        return []
    events = data.get("events", [])
    return events if isinstance(events, list) else []


def fetch_bet_offers(operator: str, event_id, sport: str) -> list:
    data = fetch_json(
        f"{BASE_URL}/{operator}/betoffer/event/{event_id}.json",
        {"lang": "en_US", "market": "US", "onlyAvailable": "true"},
        sport, f"betoffer[{operator}:{event_id}]",
    )
    if not isinstance(data, dict):
        return []
    offers = data.get("betOffers", [])
    return offers if isinstance(offers, list) else []


def normalize(sport: str, group_id: int) -> tuple:
    """Returns (games, operator_used) -- tries operators in order until one works."""
    for operator in OPERATORS:
        events = fetch_events(operator, group_id, sport)
        if events:
            games = []
            for ev in events[:MAX_EVENTS_PER_SPORT]:
                if not isinstance(ev, dict):
                    continue
                event_info = ev.get("event", ev)  # some Kambi responses nest under "event"
                event_id = event_info.get("id")
                if not event_id:
                    continue
                offers = fetch_bet_offers(operator, event_id, sport)
                games.append({
                    "sport": sport,
                    "event_id": event_id,
                    "start_time": event_info.get("start"),
                    "home_team": event_info.get("homeName"),
                    "away_team": event_info.get("awayName"),
                    "bet_offers": offers,  # raw -- ML/spread/total/props, odds x1000 decimal
                })
            return games, operator
    return [], None


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            # A 200 doesn't guarantee the content actually landed -- confirmed
            # this session on multiple other scripts (200 every time, file
            # silently absent/unchanged). Verify each file is actually
            # present in the response's own returned file list.
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
            # 403/429 = secondary rate limit (many workflows sharing one
            # GITHUB_TOKEN can burst-trigger this when GitHub bunches
            # scheduled cron runs near the top of the hour). 409 = another
            # workflow wrote to this same shared Gist at the same instant
            # (confirmed real: multiple unrelated scripts on tight cron
            # schedules collide on this exact shared resource). True
            # exponential backoff + random jitter -- without jitter, every
            # script that collided at T+0 would all retry at the identical
            # T+10 and just collide again.
            base_wait = min(10 * (2 ** attempt), 90)  # 10, 20
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

    for sport, group_id in GROUPS.items():
        try:
            games, operator = normalize(sport, group_id)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not games:
            log(f"  {sport}: 0 games (all operators failed)")
            continue
        any_data = True
        log(f"  {sport}: {len(games)} games via {operator}")
        files_payload[f"betcouncil_kambi_{sport}.json"] = {
            "content": json.dumps({
                "source": "kambi_betrivers", "sport": sport, "operator": operator,
                "captured_at": now_iso, "games": games,
            })
        }

    files_payload["betcouncil_kambi_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
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
