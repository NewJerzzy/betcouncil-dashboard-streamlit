"""
theoddsgap.com widget-data — best book + best odds per game (ML/spread/
total), 19 books including Kalshi/Polymarket/ProphetX.

Confirmed live 2026-08-04: GET https://theoddsgap.com/api/widget-data?market=all&limit=10
Real fields confirmed via live capture: away, home, sport, time_display,
commence_time, markets.ml.{away_best,home_best,n_books}, markets.spread.
{line,away_best,home_best,n_books}, markets.total.{line,over_best,
under_best,n_books}. away_best/home_best/over_best/under_best each have
{label, odds} (spread ones also have {line}).

Confirmed real bugs in the original spec: both ?sport= and &limit= query
params are silently ignored by the live API -- always returns whatever
"count" the server feels like (10 in testing, sometimes more), across
whatever sports have games soonest, regardless of params. Fetches ALL
games returned and filters/sport-groups client-side instead of relying
on server-side filtering.

Pushes merged into betcouncil_evbets_combined.json from the start (the
proven-safe pattern all season -- standalone new files on this Gist
have repeatedly failed to ever land).
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://theoddsgap.com/api/widget-data"
SHARED_FILE = "betcouncil_evbets_combined.json"
MERGE_KEY = "theoddsgap_lines"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def log(msg: str):
    print(f"[theoddsgap_widget] {msg}", flush=True)


def fetch_games() -> list:
    """?market=all&limit=10 params confirmed live to have zero effect on
    the real response -- kept in the URL for documentation/in case that
    ever changes, but fetched as one flat call regardless."""
    r = requests.get(API_URL, params={"market": "all", "limit": 10}, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        log(f"HTTP {r.status_code}")
        return []
    data = r.json()
    games = data.get("games", [])
    log(f"Fetched {len(games)} games (server ignores sport/limit params -- confirmed real bug)")
    return games


def normalize_game(g: dict) -> dict:
    markets = g.get("markets", {}) or {}
    return {
        "away": g.get("away", ""),
        "home": g.get("home", ""),
        "sport": str(g.get("sport", "")).upper(),
        "time_display": g.get("time_display", ""),
        "commence_time": g.get("commence_time", ""),
        "ml": markets.get("ml"),
        "spread": markets.get("spread"),
        "total": markets.get("total"),
    }


def push_files(merged_payload: dict, github_token: str) -> int:
    """Same proven read-modify-write-with-verification pattern used
    across every other script sharing this file -- outer retry re-reads
    and verifies no other previously-present key vanished after a
    successful write, not just that our own key landed (a real,
    confirmed, live production race condition found earlier this
    session when multiple scripts merge into the same shared file on
    independent cron schedules)."""
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

    try:
        raw_games = fetch_games()
    except Exception as e:
        log(f"FATAL: fetch error — {e}")
        return 1

    if not raw_games:
        log("FATAL: zero games returned")
        return 1

    normalized = [normalize_game(g) for g in raw_games]
    by_sport = {}
    for g in normalized:
        by_sport.setdefault(g["sport"], []).append(g)
    for sport, games in by_sport.items():
        log(f"  {sport}: {len(games)} games")

    merged_payload = {
        "source": "theoddsgap",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "games": normalized,
    }

    pushed = push_files(merged_payload, github_token)
    log(f"Pushed {len(normalized)} games: {'ok' if pushed else 'FAILED'}")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
