"""
dimers_refresh.py — Dimers.com game-line picks via Stats Insider's backend (public, no auth)
================================================================================

Dimers.com's "Best Bets"/"Best Props" pages visually gate everything past
the first ~3 picks behind a "Dimers Pro" blur overlay. Investigated
(2026-07) whether that gating is enforced server-side or just a frontend
display trick — it's the latter. Dimers is an Angular SSR app; the full
pick set (43 games / 120 picks in the sample checked) is already baked
into the page's embedded transfer-state on a clean, cookie-less request.
The underlying data comes from Stats Insider (statsinsider.com.au) —
a confirmed sibling property under the same parent, Cipher Sports
Technology Group — via their levy-edge API:

    GET https://levy-edge.statsinsider.com.au/matches/upcoming/ids
        ?dates=true&Sport={sports}&days={days}
        -> upcoming games + SIMatchID per game

    GET https://levy-edge.statsinsider.com.au/match/{SIMatchID}
        -> full BettingData (edges, odds, model win probabilities per
           market) + MatchData (teams, date, sport) for that game

Neither endpoint needs a session cookie or auth — same as the page
itself. This script was NOT verified by direct testing before first
deploy (the discovery came from a separate investigation, not a live
test from this environment) — it logs full request/response diagnostics
to the Gist on every run specifically so a schema mismatch shows up
immediately instead of silently failing, same approach used for
favoredprops_refresh.py's first (broken) version.

Pushes to betcouncil_dimers_{SPORT}.json — game-line comparison data
(edges/odds/model win% per market), same category as BettingPros/Covers
in the New Bettor "How This Compares" panel, not a props source like
FavoredProps/DK.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://levy-edge.statsinsider.com.au"
SPORTS = ["NBA", "MLB", "NFL", "NHL", "WNBA"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://www.dimers.com/",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_upcoming_match_ids() -> list:
    url = f"{BASE_URL}/matches/upcoming/ids"
    params = {"dates": "true", "Sport": ",".join(SPORTS), "days": 3}
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    DEBUG_LOG.append({"endpoint": "matches/upcoming/ids", "url": r.url, "status": r.status_code,
                       "body_snippet": r.text[:1500]})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    data = r.json()

    # Defensive parsing — exact shape wasn't verified live before this
    # first deploy. Handle a few plausible shapes: a flat list of match
    # dicts, or a dict keyed by sport with a list of matches each.
    match_ids = []
    if isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and m.get("SIMatchID"):
                match_ids.append(m)
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                for m in val:
                    if isinstance(m, dict) and m.get("SIMatchID"):
                        m.setdefault("Sport", key)
                        match_ids.append(m)
    return match_ids


def fetch_match_data(sim_match_id: str) -> dict | None:
    url = f"{BASE_URL}/match/{sim_match_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    ok = r.status_code == 200
    DEBUG_LOG.append({"endpoint": f"match/{sim_match_id}", "url": r.url, "status": r.status_code,
                       "body_snippet": r.text[:1500] if ok else r.text[:300]})
    if not ok:
        return None
    try:
        return r.json()
    except Exception:
        return None


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(3):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 2:
            # 403/429 = secondary rate limit (many workflows sharing one
            # GITHUB_TOKEN can burst-trigger this when GitHub bunches
            # scheduled cron runs near the top of the hour). 409 = another
            # workflow wrote to this same shared Gist at the same instant
            # (confirmed real: multiple unrelated scripts on tight cron
            # schedules collide on this exact shared resource). True
            # exponential backoff + random jitter -- without jitter, every
            # script that collided at T+0 would all retry at the identical
            # T+10 and just collide again.
            base_wait = 10 * (2 ** attempt)  # 10, 20
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/3)")
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
    files_payload = {}
    by_sport: dict = {s: [] for s in SPORTS}

    try:
        match_stubs = fetch_upcoming_match_ids()
    except Exception as e:
        log(f"FATAL: matches/upcoming/ids error — {e}")
        files_payload["betcouncil_dimers_debug.json"] = {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG}, indent=2)
        }
        push_files(files_payload, github_token)
        return 1

    log(f"Found {len(match_stubs)} upcoming matches")
    # Cap total per-match calls to stay well within a reasonable run time
    # and avoid hammering someone else's API on a first-deploy script.
    for stub in match_stubs[:120]:
        sim_id = stub.get("SIMatchID")
        sport = str(stub.get("Sport", "")).upper()
        if sport not in by_sport:
            continue
        match_data = fetch_match_data(sim_id)
        if not match_data:
            continue
        betting = match_data.get("BettingData", match_data.get("bettingData", {}))
        match_meta = match_data.get("MatchData", match_data.get("matchData", {}))
        if not betting:
            continue
        by_sport[sport].append({
            "sim_match_id": sim_id,
            "match": match_meta,
            "betting": betting,
        })

    for sport, records in by_sport.items():
        if not records:
            log(f"  {sport}: 0 matches with betting data")
            continue
        log(f"  {sport}: {len(records)} matches captured")
        files_payload[f"betcouncil_dimers_{sport}.json"] = {
            "content": json.dumps({
                "source": "dimers_statsinsider", "sport": sport,
                "captured_at": now_iso, "matches": records,
            })
        }

    files_payload["betcouncil_dimers_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:30]}, indent=2)
    }

    if not any(k != "betcouncil_dimers_debug.json" for k in files_payload):
        log("No sport data captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
