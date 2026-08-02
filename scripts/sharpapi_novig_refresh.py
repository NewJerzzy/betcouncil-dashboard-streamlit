"""
sharpapi_novig_refresh.py — Novig odds via SharpAPI (api.sharpapi.io)
======================================================================

Novig itself has no public developer API (confirmed live 2026-07-26 by a
live-network session: their GraphQL endpoint leaks schema + old/settled
data without auth, but real-time pricing fields are null without a real
Auth0 session token that expires in ~24h -- same fragile pattern already
abandoned for Caesars). SharpAPI is a legitimate third-party odds
aggregator with its own real, documented, free-tier API (12 req/min, no
card) that normalizes Novig alongside 30+ other books -- this is the
sanctioned path, not a Novig scrape.

Auth: X-API-Key header. Free tier confirmed to cover /odds, /events,
/sports, /leagues, /sportsbooks (paid-only: /opportunities/*, /splits,
/stream). This script only touches free-tier endpoints.

Field names below are what SharpAPI's docs describe -- not yet
live-verified against a real response, so parsed defensively (matches
several plausible key names per field) the same way other first-deploy
scripts here have been; the first live run's debug output will show the
real shape if any guesses are wrong, same process as Kalshi and Signal
Odds earlier this session.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.sharpapi.io/api/v1"
SPORTS = ["baseball_mlb", "americanfootball_nfl"]

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _fetch_novig_odds(api_key: str, sport: str | None = None) -> list | None:
    params = {"sportsbook": "novig"}
    if sport:
        params["sport"] = sport
    try:
        r = requests.get(
            f"{BASE_URL}/odds",
            params=params,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=20,
        )
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "error": str(e)[:300]})
        log(f"  {sport or 'all'}: error — {e}")
        return None

    DEBUG_LOG.append({"sport": sport, "status": r.status_code, "body_snippet": r.text[:3000]})

    if r.status_code == 401:
        log(f"  {sport or 'all'}: HTTP 401 — API key rejected (may be stale/regenerated)")
        return None
    if r.status_code == 429:
        log(f"  {sport or 'all'}: HTTP 429 — rate limited (free tier is 12 req/min)")
        return None
    if r.status_code != 200:
        log(f"  {sport or 'all'}: HTTP {r.status_code} — {r.text[:200]}")
        return None

    try:
        data = r.json()
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "json_error": str(e)[:300]})
        return None

    # Tolerate a few plausible envelope shapes rather than hard-assuming one
    rows = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("data", "odds", "results", "events"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    if rows is None:
        DEBUG_LOG.append({"sport": sport, "note": "unrecognized_shape",
                           "top_level_keys": list(data.keys()) if isinstance(data, dict) else str(type(data))})
        return None

    if rows:
        DEBUG_LOG.append({"sport": sport, "note": "sample_row_full",
                           "sample": json.dumps(rows[0], indent=2)[:4000]})
    return rows


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
    api_key = os.environ.get("SHARPAPI_KEY")
    if not github_token or not api_key:
        log("FATAL: GITHUB_TOKEN or SHARPAPI_KEY not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    dry_run = "--dry-run" in sys.argv

    all_rows = []
    log("Fetching Novig odds (no sport filter, whatever's live right now)...")
    rows = _fetch_novig_odds(api_key)
    if rows is not None:
        all_rows.extend(rows)
        log(f"  {len(rows)} rows")
    else:
        log("  unfiltered call failed, trying per-sport as fallback...")
        for sport in SPORTS:
            log(f"Fetching Novig odds for {sport}...")
            rows = _fetch_novig_odds(api_key, sport)
            if rows:
                all_rows.extend(rows)
                log(f"  {sport}: {len(rows)} rows")

    log(f"Total: {len(all_rows)} rows")

    if not all_rows:
        any_200 = any(r.get("status") == 200 for r in DEBUG_LOG)
        log("No Novig data captured this run" + (" (all calls succeeded, just empty)" if any_200 else " (calls failed)"))
        if not dry_run:
            push_files({
                "betcouncil_sharpapi_novig_debug.json": {
                    "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
                }
            }, github_token)
        return 0 if any_200 else 1

    if dry_run:
        log("--dry-run: skipping Gist push")
        return 0

    files_payload = {
        "betcouncil_sharpapi_novig.json": {
            "content": json.dumps({"source": "sharpapi_novig", "captured_at": now_iso, "rows": all_rows})
        },
        "betcouncil_sharpapi_novig_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
        },
    }
    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
