"""
sportsinsights_refresh.py — Sports Insights public betting trends (public JSON, no auth)
================================================================================

Sports Insights' free ticket-percentage data (confirmed 2026-07-17 via
investigation, cross-checked against their own marketing copy which
explicitly calls out "money percentages" as the premium unlock — that
detail matches exactly what this endpoint returns: PercentSpread/OU/ML
populated, MoneyPercentSpread/OU/ML always 0).

The WordPress site embeds an AngularJS SPA that looks like it needs auth
(sportsinsights.actionnetwork.com returns 401) but the actual backend is
a separate, genuinely unauthenticated subdomain:

    GET https://account.sportsinsights.com/wp/api/trends/events/sport/{sportId}

No headers, cookies, or tokens required.

Sport IDs: 1=NFL, 2=NBA, 3=MLB, 4=NHL, 5=Tennis, 10=Women's Tennis.

Returns a rolling window (today + ~10-11 days forward) — future-dated
games show 0% across the board until betting opens, so this filters to
TotalBets > 0 to skip the zero-shells.

This is public betting % (ticket count), same category as Covers/
VegasInsider — comparison/context data, not a signal, not wired into
edge computation.

Pushes to betcouncil_sportsinsights_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://account.sportsinsights.com/wp/api/trends/events/sport"
SPORT_IDS = {"NFL": 1, "NBA": 2, "MLB": 3, "NHL": 4, "TENNIS": 5, "WTENNIS": 10}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_sport_trends(sport: str, sport_id: int) -> list:
    url = f"{BASE_URL}/{sport_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    DEBUG_LOG.append({"sport": sport, "url": url, "status": r.status_code,
                       "body_snippet": r.text[:600]})
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    normalized = []
    for game in data:
        if not isinstance(game, dict):
            continue
        if not game.get("TotalBets"):
            continue  # forward-dated zero-shell, skip
        normalized.append({
            "event_id": game.get("EventId"),
            "home_team": game.get("HomeTeam"), "away_team": game.get("VisitorTeam"),
            "home_abv": game.get("HomeTeamShort"), "away_abv": game.get("VisitorTeamShort"),
            "total_bets": game.get("TotalBets"),
            "home_pct_spread": game.get("PercentSpread"), "home_pct_ou": game.get("PercentOU"),
            "home_pct_ml": game.get("PercentML"),
            "event_date": game.get("EventDate"), "home_favored": game.get("HomeFavored"),
            "sport": sport,
        })
    return normalized


def push_files(files_payload: dict, github_token: str) -> int:
    """
    Merges into the shared evbets_combined.json.

    UPDATED (2026-08-03): confirmed a real, live production data-loss
    race -- multiple scripts merge into the same shared file on
    independent cron schedules, and a full read-modify-write cycle
    means one script's write can silently clobber another's just-
    written key if their timing overlaps (confirmed happening for
    real: wagerbird/sportsinsights/unabated all independently observed
    missing after other scripts' writes landed in between). Added an
    outer retry: after a successful write, re-read and verify no
    previously-present key vanished (not just that OUR key landed) --
    if one did, redo the entire read-modify-write cycle from a fresh
    read, up to 3 times total.
    """
    SHARED_FILE = "betcouncil_market_feeds.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_sportsinsights_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

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
        existing["sportsinsights"] = merged
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

        # Verify no previously-present key vanished (a concurrent writer's
        # stale read clobbering our just-written state).
        try:
            time.sleep(2)
            r2 = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                               headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                               timeout=15)
            raw_url2 = r2.json().get("files", {}).get(SHARED_FILE, {}).get("raw_url")
            post_write = requests.get(raw_url2, timeout=15).json() if raw_url2 else {}
            post_write_keys = set(post_write.keys())
            lost_keys = pre_write_keys - post_write_keys - {"sportsinsights"}
            if "sportsinsights" in post_write_keys and not lost_keys:
                return len(files_payload)
            log(f"Post-write verification found lost keys {lost_keys} or missing own key -- retrying full cycle (outer attempt {outer_attempt+1}/3)")
        except Exception as e:
            log(f"Post-write verification failed to check: {e} -- treating write as successful anyway")
            return len(files_payload)

    log("Gave up after 3 full read-modify-write cycles -- concurrent writers kept colliding")
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

    import atexit
    _lock_token = acquire_lock(GIST_ID, github_token, "market_feeds", holder="sportsinsights")
    if not _lock_token:
        log("Could not acquire market_feeds lock after retries -- skipping this run to avoid a collision")
        return 1
    atexit.register(lambda: release_lock(GIST_ID, github_token, "market_feeds", _lock_token))

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport, sport_id in SPORT_IDS.items():
        try:
            records = fetch_sport_trends(sport, sport_id)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not records:
            log(f"  {sport}: 0 real games (off-season or no betting open yet)")
            continue
        any_data = True
        log(f"  {sport}: {len(records)} games with real ticket data")
        files_payload[f"betcouncil_sportsinsights_{sport}.json"] = {
            "content": json.dumps({
                "source": "sportsinsights", "sport": sport,
                "captured_at": now_iso, "games": records,
            })
        }

    files_payload["betcouncil_sportsinsights_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:10]}, indent=2)
    }

    if not any_data:
        log("No sport data captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
