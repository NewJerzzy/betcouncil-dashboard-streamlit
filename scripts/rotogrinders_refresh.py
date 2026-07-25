"""
rotogrinders_refresh.py — RotoGrinders lineup confirmation + DFS projections (public JSON, no auth)
================================================================================

RotoGrinders is a traditional server-rendered site (no Next.js/React
Router/Nuxt — investigated 2026-07-16). Its lineups pages have a public
JSON twin at the same URL with ".json" appended:

    GET https://rotogrinders.com/lineups/{sport}.json
    GET https://rotogrinders.com/lineups/{sport}.json?site={dfs_site}

No auth, no cookies. This is a soft-gated product — RotoGrinders' real
prop-picks tools (is_rg_props etc.) are fully paywalled with zero free
preview, but the *lineups* endpoint itself is genuinely open and gives:
confirmed/unconfirmed starting lineup status, batting order, DFS salary,
and "pfpts" (RotoGrinders' own projected DFS fantasy points, scaled per
site — e.g. same player shows different pfpts for draftkings vs
fanduel scoring).

This is NOT prop-pick data — it's lineup-confirmation + DFS-projection
context, same category as LineStar/Situational Splits, not a
comparison-source pick like FavoredProps/Dimers. Belongs in Player
Lookup as context, not the New Bettor "How This Compares" panel.

Exact field names/response shape weren't independently verified before
this first deploy (verified the site and general product shape via
search, but couldn't directly fetch the specific .json endpoint through
available tools) — ships with self-diagnostic logging so a schema
mismatch is caught immediately.

Pushes to betcouncil_rotogrinders_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://rotogrinders.com"
# nba/nhl confirmed off-season per the investigation; mlb/nfl are the
# live ones right now. pga returned an error per the investigation, left
# out. Re-add nba/nhl once those seasons start.
SPORTS = ["mlb", "nfl"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_sport_lineups(sport: str) -> list:
    url = f"{BASE_URL}/lineups/{sport}.json"
    r = requests.get(url, headers=HEADERS, timeout=20)
    DEBUG_LOG.append({"sport": sport, "url": url, "status": r.status_code,
                       "body_snippet": r.text[:800]})
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except json.JSONDecodeError:
        return []

    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in ("data", "players", "lineups"):
            if isinstance(data.get(key), list):
                records = data[key]
                break
        else:
            records = []
    else:
        records = []

    normalized = []
    for rec in records:
        if not isinstance(rec, dict) or not rec.get("player"):
            continue
        normalized.append({
            "player": rec.get("player"), "team": rec.get("team"), "opp": rec.get("opp"),
            "status": rec.get("status"),  # "C" confirmed, "B" unconfirmed (per investigation)
            "position": rec.get("pos"), "batting_order": rec.get("order"),
            "salary": rec.get("salary"), "pfpts": rec.get("pfpts"),
            "date_unix": rec.get("date"), "sport": sport.upper(),
        })
    return normalized


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
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

    for sport in SPORTS:
        try:
            records = fetch_sport_lineups(sport)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not records:
            log(f"  {sport}: 0 records")
            continue
        any_data = True
        log(f"  {sport}: {len(records)} records")
        files_payload[f"betcouncil_rotogrinders_{sport.upper()}.json"] = {
            "content": json.dumps({
                "source": "rotogrinders_lineups", "sport": sport.upper(),
                "captured_at": now_iso, "records": records,
            })
        }

    files_payload["betcouncil_rotogrinders_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:10]}, indent=2)
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
