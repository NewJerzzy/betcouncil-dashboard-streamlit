"""
draftedge_refresh.py — DraftEdge props scraper (public SSR JSON, no auth)
================================================================================

DraftEdge.com's props pages server-render a `phpPropData` variable directly
into the page HTML — no login required despite the "premium-odds-container"
CSS class name (that's just a class name, not a paywall gate; the prop data
itself is fully in the public payload). The same data is also available as
direct JSON:

    GET https://draftedge.com/api/{sport}/{sport}props.json

Confirmed sports: nba, mlb (both live). nfl/nhl return 404 in their
off-season and will populate once those seasons start.

MLB data is the rich one — projections, L5/L15/L30 hit rates, opposing
pitcher ERA/WHIP/K9, weather (temp/wind/humidity), DFS salary, injury
designation, game spread/total, all bundled per player/prop.

Unlike weather/park-factors (BetCouncil already has its own live pipelines
for both — LineStar+NWS/wttr.in for weather, FanGraphs for park factors),
this is being added as comparison/cross-check context, same tier as
FavoredProps — NOT a new signal input. Display-only until backtested.

Pushes to betcouncil_draftedge_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import random
import time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://draftedge.com"
SPORTS = ["nba", "mlb", "nfl", "nhl", "cfb"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_props(sport: str) -> list:
    url = f"{BASE_URL}/api/{sport}/{sport}props.json"
    r = requests.get(url, headers=HEADERS, timeout=30)
    DEBUG_LOG.append({"endpoint": f"{sport}props.json", "url": url, "status": r.status_code,
                       "body_snippet": r.text[:1200]})
    if r.status_code == 404:
        return []  # off-season, not an error
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    data = r.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("props", "data", "players"):
            if isinstance(data.get(key), list):
                return data[key]
        # MLB's actual shape (confirmed 2026-07): a dict keyed directly by
        # numeric player ID, no wrapper key at all — e.g.
        # {"99189541": {"Player": "Akil Baddoo", ...}, "...": {...}}.
        # Treat the dict's values as the record list in that case.
        values = [v for v in data.values() if isinstance(v, dict)]
        if values:
            return values
    return []


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

    for sport in SPORTS:
        try:
            props = fetch_props(sport)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not props:
            log(f"  {sport}: 0 props (likely off-season)")
            continue
        any_data = True
        log(f"  {sport}: {len(props)} props")
        files_payload[f"betcouncil_draftedge_{sport.upper()}.json"] = {
            "content": json.dumps({
                "source": "draftedge", "sport": sport.upper(),
                "captured_at": now_iso, "props": props,
            })
        }

    files_payload["betcouncil_draftedge_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
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
