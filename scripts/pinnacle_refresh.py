"""
pinnacle_refresh.py — Pinnacle's public API (no auth, no WAF)
================================================================================

Pinnacle is widely considered the sharpest book in the world -- highest
limits, smallest margins, mostly professional bettors -- so their line is
effectively the market consensus at open. Most retail books look at
Pinnacle before posting their own number.

Confirmed live and fully public:
    GET https://guest.api.arcadia.pinnacle.com/0.1/leagues/{leagueId}/matchups
    GET https://guest.api.arcadia.pinnacle.com/0.1/leagues/{leagueId}/markets/straight

No auth, no WAF, no TLS fingerprinting confirmed in prior research. Matchups
gives game metadata (teams, start time); markets/straight gives ML/spread/
total prices keyed by matchupId, with version numbers so line movement is
detectable across polls.

Not independently verified byte-for-byte by Claude before this first deploy
(built from prior research findings, not re-probed live from this sandbox --
guest.api.arcadia.pinnacle.com isn't in this environment's network
allowlist). Ships with debug logging so a schema drift or block is caught
immediately on first live run rather than silently producing nothing.

Pushes to betcouncil_pinnacle_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://guest.api.arcadia.pinnacle.com/0.1"

# League IDs confirmed via prior research probe.
LEAGUES = {
    "MLB":  246,
    "NBA":  487,
    "WNBA": 578,
    "NFL":  889,
    "NCAAF": 880,
    "NCAAB": 493,
    "MLS":  2663,
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str, sport: str, label: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "label": label, "url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"sport": sport, "label": label, "url": url, "status": r.status_code,
                       "body_snippet": r.text[:400]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def normalize(sport: str, league_id: int) -> list:
    matchups = fetch_json(f"{BASE_URL}/leagues/{league_id}/matchups", sport, "matchups")
    if not isinstance(matchups, list) or not matchups:
        return []
    markets = fetch_json(f"{BASE_URL}/leagues/{league_id}/markets/straight", sport, "markets")
    if not isinstance(markets, list):
        markets = []

    # /matchups returns mostly prop "specials" (player props, exact scores,
    # etc.), each carrying a "parent" object that IS the real 2-team game --
    # confirmed live: top-level entries have alignment="neutral" always (even
    # for actual games), while parent.participants correctly has
    # alignment="home"/"away". Build the real game list from deduped
    # parents rather than the top-level entries themselves.
    real_games: dict = {}
    for m in matchups:
        if not isinstance(m, dict):
            continue
        parent = m.get("parent")
        # A genuine top-level game (not wrapped as someone's "parent") has
        # no parent of its own and exactly 2 participants with real
        # alignment -- handle both shapes.
        candidates = []
        if parent and isinstance(parent, dict):
            candidates.append(parent)
        elif m.get("participants") and all(
            p.get("alignment") in ("home", "away") for p in m.get("participants", [])
        ) and len(m.get("participants", [])) == 2:
            candidates.append(m)

        for g in candidates:
            gid = g.get("id")
            if gid is None or gid in real_games:
                continue
            participants = g.get("participants", [])
            home = next((p for p in participants if p.get("alignment") == "home"), {})
            away = next((p for p in participants if p.get("alignment") == "away"), {})
            real_games[gid] = {
                "sport": sport,
                "matchup_id": gid,
                "start_time": g.get("startTime"),
                "home_team": home.get("name"),
                "away_team": away.get("name"),
                "is_live": g.get("isLive"),
                "markets": [],
            }

    markets_by_matchup: dict = {}
    for mkt in markets:
        if not isinstance(mkt, dict):
            continue
        mid = mkt.get("matchupId")
        markets_by_matchup.setdefault(mid, []).append(mkt)

    for gid, game in real_games.items():
        game["markets"] = markets_by_matchup.get(gid, [])

    return list(real_games.values())


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


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport, league_id in LEAGUES.items():
        try:
            games = normalize(sport, league_id)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not games:
            log(f"  {sport}: 0 games")
            continue
        any_data = True
        log(f"  {sport}: {len(games)} matchups")
        files_payload[f"betcouncil_pinnacle_{sport}.json"] = {
            "content": json.dumps({
                "source": "pinnacle", "sport": sport,
                "captured_at": now_iso, "games": games,
            })
        }

    files_payload["betcouncil_pinnacle_debug.json"] = {
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
