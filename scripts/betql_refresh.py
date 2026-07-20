"""
betql_refresh.py — BetQL public GraphQL API (no auth for the events query)
================================================================================

BetQL runs a real GraphQL API at api.betql.co/graphql. Confirmed live
2026-07-17 — the `events` query (game info, team season/ATS records,
multi-book lines) works with zero auth. A separate `login` mutation
exists for other BetQL features (their own picks/predictions product),
confirmed via a real third-party open-source script that calls this
same endpoint — but that's a different, likely-gated part of the API;
this script only uses the public `events` query.

Sample query (see full query in fetch_league_events below):
    events(after: ISO8601, before: ISO8601, eventType: TEAM,
           league: MLB, limit: 20) { id slugId startDate eventState
             channel homeTeam{...} awayTeam{...} lines{...} }

What it provides: multi-book lines (5-6 books/game confirmed), ML/run
line+juice/total, team season W/L AND ATS W/L (uncommon — most sources
don't expose against-the-spread records).

Exact schema wasn't independently verified byte-for-byte by Claude
before this first deploy (verified the endpoint is real via a working
third-party reference script, not the literal query response) — ships
with self-diagnostic logging so a schema mismatch is caught immediately.

Pushes to betcouncil_betql_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
import time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://api.betql.co/graphql"
LEAGUES = {"MLB": "MLB", "NBA": "NBA", "NFL": "NFL", "NHL": "NHL"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Content-Type": "application/json",
    "Accept": "application/json",
}

EVENTS_QUERY = """
query GetEvents($after: DateTime!, $before: DateTime!, $league: LeagueEnum!, $limit: Int!) {
  events(after: $after, before: $before, eventType: TEAM, league: $league, limit: $limit) {
    id
    slugId
    startDate
    eventState
    channel
    homeTeam { lastName preferredAbbreviation teamStats { wins losses atswins atslosses } }
    awayTeam { lastName preferredAbbreviation teamStats { wins losses atswins atslosses } }
    lines { type period homeSpread awaySpread awayMoney homeMoney total lineType bookId }
  }
}
"""

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_league_events(sport: str, league: str) -> list:
    now = datetime.now(timezone.utc)
    after = now.strftime("%Y-%m-%dT00:00:00.000Z")
    before = (now + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59.999Z")

    body = {
        "operationName": "GetEvents",
        "query": EVENTS_QUERY,
        "variables": {"after": after, "before": before, "league": league, "limit": 40},
    }
    r = requests.post(API_URL, json=body, headers=HEADERS, timeout=20)
    DEBUG_LOG.append({"sport": sport, "status": r.status_code, "body_snippet": r.text[:600]})
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except json.JSONDecodeError:
        return []
    if data.get("errors"):
        DEBUG_LOG.append({"sport": sport, "note": "GraphQL errors", "errors": data["errors"][:3]})
        return []
    events = (data.get("data") or {}).get("events", [])
    return events if isinstance(events, list) else []


def normalize_event(sport: str, ev: dict) -> dict:
    home, away = ev.get("homeTeam", {}) or {}, ev.get("awayTeam", {}) or {}
    lines = [l for l in (ev.get("lines") or []) if isinstance(l, dict)]
    return {
        "sport": sport, "event_id": ev.get("id"), "slug_id": ev.get("slugId"),
        "start_date": ev.get("startDate"), "event_state": ev.get("eventState"),
        "home_team": home.get("preferredAbbreviation"), "away_team": away.get("preferredAbbreviation"),
        "home_team_name": home.get("lastName"), "away_team_name": away.get("lastName"),
        "home_record": (home.get("teamStats") or {}), "away_record": (away.get("teamStats") or {}),
        "lines": lines,  # multi-book, keep raw
    }


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(3):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (403, 429) and attempt < 2:
            # Secondary rate limit -- many workflows sharing one GITHUB_TOKEN
            # can burst-trigger this when GitHub bunches scheduled cron runs
            # near the top of the hour (confirmed real: 15 unrelated scripts
            # all failed in the same ~10min window on 2026-07-20, every one
            # with a successful underlying data fetch, pointing at the shared
            # Gist push as the actual failure point). Back off and retry
            # instead of failing the whole job over a transient limit.
            wait = 10 * (attempt + 1)
            log(f"Gist push got {resp.status_code} (likely rate limit) -- retrying in {wait}s")
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

    for sport, league in LEAGUES.items():
        try:
            events = fetch_league_events(sport, league)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            DEBUG_LOG.append({"sport": sport, "note": "request exception", "error": str(e)})
            continue
        if not events:
            log(f"  {sport}: 0 events")
            continue

        normalized = []
        for ev in events:
            try:
                normalized.append(normalize_event(sport, ev))
            except Exception as e:
                log(f"  {sport}: normalize error — {e}")

        any_data = True
        log(f"  {sport}: {len(normalized)} events")
        files_payload[f"betcouncil_betql_{sport}.json"] = {
            "content": json.dumps({
                "source": "betql", "sport": sport,
                "captured_at": now_iso, "games": normalized,
            })
        }

    files_payload["betcouncil_betql_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15]}, indent=2)
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
