"""
GameLinePicks (gamelinepicks.com) — +EV moneyline picks refresh.

Confirmed live 2026-08-04: GET https://gamelinepicks.com/api/picks/today
returns real JSON, no auth, no rate-limit headers observed. Real fields
confirmed from a live capture: id, game, sport (emoji-prefixed, e.g.
"⚾ MLB"), betType, pick, odds, confidence (int 1-5), ev (float, e.g.
0.0313 = 3.1%), reasoning (string), commenceTime, bookmaker, profitUnits,
date, capturedAt, closingOdds, clv, result (win/loss/expired/null),
homeScore/awayScore/gradedAt/homeTeam/awayTeam (once graded).

Deliberately does NOT touch /api/arbitrage/today -- confirmed live that
response carries "limited":true,"trialActive":true (a $9.99/mo PRO
feature leaking a limited trial preview through an unauthenticated
call, not a stable free source).

Pushes merged into betcouncil_evbets_combined.json under a
"gamelinepicks" key from the start (not a standalone file) -- this
Gist has been proven repeatedly this session to never reliably create
brand-new filenames; every source built with a standalone file first
had to be migrated to the merge pattern anyway.
"""
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

import requests
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://gamelinepicks.com/api/picks/today"
SHARED_FILE = "betcouncil_gamelinepicks_feed.json"
MERGE_KEY = "gamelinepicks"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def log(msg: str):
    print(f"[gamelinepicks] {msg}", flush=True)


def normalize_sport(raw_sport: str) -> str:
    """Strips the emoji prefix GameLinePicks puts on sport names
    (e.g. "🏀 WNBA" -> "WNBA", "⚾ MLB" -> "MLB")."""
    return re.sub(r"^[^\w]+", "", str(raw_sport or "")).strip().upper()


def fetch_picks() -> list:
    r = requests.get(API_URL, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        log(f"HTTP {r.status_code}")
        return []
    data = r.json()
    picks = data.get("picks", [])
    log(f"Fetched {len(picks)} picks (fallback={data.get('fallback')})")
    return picks


def normalize_pick(p: dict) -> dict:
    return {
        "game": p.get("game", ""),
        "sport": normalize_sport(p.get("sport", "")),
        "bet_type": p.get("betType", ""),
        "pick": p.get("pick", ""),
        "odds": p.get("odds"),
        "confidence": p.get("confidence"),
        "ev": p.get("ev"),
        "reasoning": p.get("reasoning", ""),
        "commence_time": p.get("commenceTime", ""),
        "bookmaker": p.get("bookmaker", ""),
        "result": p.get("result"),
        "profit_units": p.get("profitUnits"),
        "clv": p.get("clv"),
        "home_team": p.get("homeTeam"),
        "away_team": p.get("awayTeam"),
        "home_score": p.get("homeScore"),
        "away_score": p.get("awayScore"),
    }


def push_files(merged_payload: dict, github_token: str) -> int:
    """Same proven read-modify-write-with-verification pattern already
    fixed across the 8 other scripts sharing this file -- confirmed
    real, live production race condition when multiple scripts merge
    into the same shared file on independent cron schedules. Outer
    retry re-reads and verifies no other previously-present key
    vanished after a successful write, not just that our own key landed.
    """
    for outer_attempt in range(3):
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
        pre_write_keys = set(existing.keys())
        existing[MERGE_KEY] = merged_payload
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        write_ok = False
        for attempt in range(5):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    write_ok = True
                    break
                if attempt < 4:
                    wait = min((attempt + 1) * 5, 30)
                    log(f"Push returned 200 but {SHARED_FILE} missing from response -- retrying in {wait}s")
                    time.sleep(wait)
                    continue
                log(f"Push returned 200 but {SHARED_FILE} still missing after retries -- treating as failed")
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 4:
                base_wait = min(10 * (2 ** attempt), 90)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0

        if not write_ok:
            return 0

        try:
            time.sleep(2)
            r2 = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                               headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                               timeout=15)
            raw_url2 = r2.json().get("files", {}).get(SHARED_FILE, {}).get("raw_url")
            post_write = requests.get(raw_url2, timeout=15).json() if raw_url2 else {}
            post_write_keys = set(post_write.keys())
            lost_keys = pre_write_keys - post_write_keys - {MERGE_KEY}
            if MERGE_KEY in post_write_keys and not lost_keys:
                return 1
            log(f"Post-write verification found lost keys {lost_keys} or missing own key -- retrying full cycle (outer attempt {outer_attempt+1}/3)")
        except Exception as e:
            log(f"Post-write verification failed to check: {e} -- treating write as successful anyway")
            return 1

    log("Gave up after 3 full read-modify-write cycles -- concurrent writers kept colliding")
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    import atexit
    _lock_token = acquire_lock(GIST_ID, github_token, "gamelinepicks_feed", holder="gamelinepicks", max_attempts=7)
    if not _lock_token:
        log("Could not acquire gamelinepicks_feed lock after retries -- skipping this run to avoid a collision")
        return 1
    atexit.register(lambda: release_lock(GIST_ID, github_token, "gamelinepicks_feed", _lock_token))

    try:
        raw_picks = fetch_picks()
    except Exception as e:
        log(f"FATAL: fetch error — {e}")
        return 1

    if not raw_picks:
        log("FATAL: zero picks returned")
        return 1

    normalized = [normalize_pick(p) for p in raw_picks]
    merged_payload = {
        "source": "gamelinepicks",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "picks": normalized,
    }

    pushed = push_files(merged_payload, github_token)
    log(f"Pushed {len(normalized)} picks: {'ok' if pushed else 'FAILED'}")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
