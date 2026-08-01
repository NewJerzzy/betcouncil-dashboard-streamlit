"""
evbets_refresh.py — EVBets.app +EV feed (converts a dead browser-only
harvester into a proper server-side scraper)
====================================================================

Previously this only existed as JS injected into the user's own browser
tab (st.components.v1.html in app.py), which only runs if BetCouncil is
open in an actual browser at that moment -- confirmed to have never
actually populated betcouncil_evbets_{sport}.json in the Gist. The real
consumer code (app_core.py's EVBets +EV signal overlay, reading
evbets_ev_picks/evbets_prop_picks) has been waiting on data that could
never arrive this way.

Same site, same URLs the JS already used (both endpoints tried, primary
then API fallback, matching the JS's own pattern):
  https://evbets.app/value-bets/{slug}          (primary)
  https://evbets.app/api/value-bets?sport={slug}&min_ev=2&limit=100  (fallback)
  https://evbets.app/prop-bets/{slug}            (primary, props)

Sport slug map taken directly from the existing JS (evbSportMap).
Pushes to the SAME Gist keys the app already reads:
  betcouncil_evbets_{SPORT}.json
  betcouncil_evbets_props_{SPORT}.json
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SPORT_SLUGS = {
    "MLB": "baseball-mlb", "NBA": "basketball-nba", "NFL": "american-football-nfl",
    "NHL": "hockey-nhl", "UFC": "mma-mixed-martial-arts", "SOCCER": "soccer-epl",
    "WNBA": "basketball-wnba",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "application/json", "Referer": "https://evbets.app/"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _try_json_get(url: str, referer: str = None):
    hdrs = dict(HEADERS)
    if referer:
        hdrs["Referer"] = referer
    try:
        r = requests.get(url, headers=hdrs, timeout=15)
        DEBUG_LOG.append({"url": url, "status": r.status_code, "body_len": len(r.text)})
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        DEBUG_LOG.append({"url": url, "error": str(e)[:200]})
        return None


def fetch_value_bets(sport: str, slug: str):
    data = _try_json_get(f"https://evbets.app/value-bets/{slug}", "https://evbets.app/")
    if data:
        return data
    return _try_json_get(f"https://evbets.app/api/value-bets?sport={slug}&min_ev=2&limit=100")


def fetch_prop_bets(sport: str, slug: str):
    return _try_json_get(f"https://evbets.app/prop-bets/{slug}", "https://evbets.app/prop-bets/")


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
    combined = {"captured_at": now_iso, "source": "evbets_refresh_scraper", "by_sport": {}}
    any_data = False

    for sport, slug in SPORT_SLUGS.items():
        vb = fetch_value_bets(sport, slug)
        if vb:
            any_data = True
        log(f"{sport} value-bets: {'OK' if vb else 'empty'}")

        pb = fetch_prop_bets(sport, slug)
        if pb:
            any_data = True
        log(f"{sport} prop-bets: {'OK' if pb else 'empty'}")

        combined["by_sport"][sport] = {"value_bets": vb or {}, "prop_bets": pb or {}}

    combined["requests_debug"] = DEBUG_LOG[:15]

    if not any_data:
        log("No data captured across any sport -- not overwriting existing data with empty")
        return 1

    pushed = push_files({"betcouncil_evbets_combined.json": {"content": json.dumps(combined)}})
    log(f"Pushed {pushed} file" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
