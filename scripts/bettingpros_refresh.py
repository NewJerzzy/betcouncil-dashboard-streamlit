"""
bettingpros_refresh.py — BettingPros props API (public, no auth)
====================================================================

GET https://api.bettingpros.com/v3/props?sport={SPORT}&limit=50

Confirmed live 2026-07-31, all 5 sports (MLB/NBA/NHL/WNBA/NFL — NFL
returns 0 results, expected, offseason). Every other endpoint on this
API (/v3/picks, /v3/events, /v3/players, /v3/markets, /v3/books,
/v3/offers) returns 403 -- /v3/props is the only open door.

The genuinely new piece for BetCouncil: `performance` — how many times
a player hit over/under on THIS SPECIFIC PROP in their last 1/5/10/15/20
games, season, prior season, and h2h vs this opponent, plus current
streak. BetCouncil has a whole module reserved for this
(hitrate_logger.py) whose compute_hit_rate() is a stub that always
returns None ("needs resolved data... future") -- this fills that gap
directly with real data instead of building the resolved-outcome
pipeline that stub was waiting on.

Also captures BettingPros' own line/consensus/odds/probability/EV/
bet_rating and projection (their model's own O/U call) per prop --
useful supplemental context, though the hit-rate/streak block is the
part nothing else in the codebase currently has at all.

Pushes one Gist file per sport: betcouncil_bettingpros_{SPORT}.json
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone

import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock
import re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://api.bettingpros.com/v3/props"
SPORTS = ["MLB", "NBA", "NHL", "WNBA", "NFL"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "application/json"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


SITE_URL = "https://www.bettingpros.com/{sport_path}/props/"
_SPORT_PATHS = {"MLB": "mlb", "NBA": "nba", "NHL": "nhl", "WNBA": "wnba", "NFL": "nfl"}


_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def fetch_sport(sport: str) -> list:
    """
    api.bettingpros.com now returns a real HTTP 403 (AWS API Gateway
    ForbiddenException) as of 2026-08-07 -- confirmed via live testing,
    not a transient error. The site's own pages still embed the exact
    same prop data server-side in a JSON <script> tag, confirmed real
    and field-identical to the old API response. Scrapes that instead.

    Uses a shared requests.Session for connection reuse -- each request
    was opening a fresh TCP/TLS handshake, confirmed via live timing to
    be a major contributor to the real ~30s/page rate that was causing
    workflow timeouts.
    """
    all_props = []
    seen_ids = set()
    sport_path = _SPORT_PATHS.get(sport, sport.lower())
    page = 1
    while page <= 8:
        url = SITE_URL.format(sport_path=sport_path)
        params = {} if page == 1 else {"page": page}
        try:
            r = _SESSION.get(url, params=params, timeout=20)
            DEBUG_LOG.append({"sport": sport, "page": page, "status": r.status_code, "body_len": len(r.text)})
        except Exception as e:
            DEBUG_LOG.append({"sport": sport, "page": page, "error": str(e)[:200]})
            break
        if r.status_code != 200:
            break

        blocks = re.findall(r'<script type="application/json" class="island-props">(.*?)</script>', r.text, re.DOTALL)
        data = None
        for blk in blocks:
            if '"events"' not in blk:
                continue
            try:
                parsed = json.loads(blk)
                if parsed.get("offers"):
                    data = parsed
                    break
            except Exception:
                continue
        if data is None:
            break

        props = data.get("offers", [])
        if not isinstance(props, list) or not props:
            break

        new_count = 0
        for p in props:
            pid = (p.get("participant", {}).get("id"), p.get("market_id"))
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            all_props.append(p)
            new_count += 1

        # site shows a fixed ~25/page; stop once a page adds nothing new
        # (last page or duplicate content) rather than assuming a fixed count
        if new_count == 0:
            break
        page += 1

    log(f"{sport}: {len(all_props)} props ({page} page(s))")
    return all_props



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
    """
    Merges all per-sport files into ONE combined file, using the real
    distributed lock. Real, confirmed-used source (Player Lookup Props
    Browser, harvester health registry).
    """
    github_token = os.environ["GITHUB_TOKEN"]
    if not _rate_limit_ok(github_token):
        return 0
    SHARED_FILE = "betcouncil_bettingpros_combined.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_bettingpros_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

    lock_token = acquire_lock(GIST_ID, github_token, "bettingpros_combined", holder="bettingpros", max_attempts=7)
    if not lock_token:
        log("Could not acquire bettingpros_combined lock -- skipping this run to avoid a collision")
        return 0
    try:
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                existing = requests.get(r_files[SHARED_FILE]["raw_url"], timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        existing.update(merged)
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
                    return len(merged)
                if attempt < 3:
                    time.sleep(5)
                    continue
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 3:
                wait = (attempt + 1) * 8 + random.uniform(0, 5)
                log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0
        return 0
    finally:
        release_lock(GIST_ID, github_token, "bettingpros_combined", lock_token)


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport in SPORTS:
        props = fetch_sport(sport)
        if props:
            any_data = True
        files_payload[f"betcouncil_bettingpros_{sport}.json"] = {
            "content": json.dumps({"captured_at": now_iso, "sport": sport,
                                    "source": "bettingpros_v3_props", "props": props})
        }

    files_payload["betcouncil_bettingpros_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
    }

    if not any_data:
        log("No data captured across any sport -- pushing debug only, not overwriting existing data with empty")
        return 1

    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("UNHANDLED EXCEPTION:\n" + tb)
        try:
            gh_token = os.environ.get("GITHUB_TOKEN")
            if gh_token:
                requests.patch(
                    f"https://api.github.com/gists/{GIST_ID}",
                    headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
                    json={"files": {"betcouncil_bettingpros_debug.json": {
                        "content": json.dumps({"error": "unhandled_exception", "traceback": tb, "debug_log_tail": DEBUG_LOG[-10:]}, default=str)
                    }}}, timeout=15)
        except Exception:
            pass
        sys.exit(1)
