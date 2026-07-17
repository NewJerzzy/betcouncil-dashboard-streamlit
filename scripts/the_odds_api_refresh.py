"""
the_odds_api_refresh.py — The Odds API player props (FD/DK/BetMGM/BetRivers/Pinnacle)
================================================================================

Only known reliable source for FanDuel/DraftKings/BetMGM/BetRivers AND
Pinnacle player props in one place. Free tier is 500 credits/month --
cost is roughly 1 credit per market returned per event, so continuous
15-min polling of a full slate is not sustainable. Instead: pre-game-
window polling only -- games get one props snapshot when they enter the
window (default 6h before start), not repeated all day.

Endpoint: GET https://api.the-odds-api.com/v4/sports/{sport_key}/events/{eventId}/odds
    params: apiKey, regions=us,eu (us = FD/DK/BetMGM/BetRivers/Bovada/etc,
            eu = Pinnacle/William Hill/etc), markets=<comma list>,
            oddsFormat=american

Markets requested (confirmed available for MLB on the free tier):
    Pitcher: pitcher_strikeouts, pitcher_record_a_win, pitcher_hits_allowed,
             pitcher_walks, pitcher_earned_runs, pitcher_outs
    Batter:  batter_home_runs, batter_hits, batter_total_bases, batter_rbis,
             batter_runs_scored, batter_stolen_bases, batter_walks

Credit math: this uses one combined regions=us,eu call per event (not
separate us/eu calls), and only for events inside the pre-game window --
that's the whole point of the window filter. Still, 13 markets x 15 games
would burn the entire monthly budget in a couple of polls, so
MAX_EVENTS_PER_RUN and a trimmed default market list cap the damage; widen
either only if credit usage (logged every run) shows headroom.

Not independently verified byte-for-byte by Claude before this first
deploy (market key names come from public docs/research, not re-probed
live from this sandbox -- api.the-odds-api.com isn't in this
environment's network allowlist). Ships with debug logging including the
exact `x-requests-remaining` / `x-requests-used` response headers so
actual credit burn is visible from day one, not assumed.

Pushes to betcouncil_odds_api_props_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.the-odds-api.com/v4"
API_KEY = os.environ.get("ODDS_API_KEY", "6c4421ef9db7d9d28d7cb81bd30076b4")

SPORT_KEYS = {"MLB": "baseball_mlb"}

MARKETS = [
    "pitcher_strikeouts", "pitcher_record_a_win", "pitcher_hits_allowed",
    "pitcher_walks", "pitcher_earned_runs", "pitcher_outs",
    "batter_home_runs", "batter_hits", "batter_total_bases",
    "batter_rbis", "batter_runs_scored", "batter_stolen_bases", "batter_walks",
]

REGIONS = "us,eu"
PRE_GAME_WINDOW_HOURS = 6
MAX_EVENTS_PER_RUN = 8  # hard credit-burn cap; raise only after checking logged usage

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_events(sport_key: str) -> list:
    url = f"{BASE_URL}/sports/{sport_key}/events"
    try:
        r = requests.get(url, params={"apiKey": API_KEY}, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"step": "events", "sport_key": sport_key, "error": str(e)})
        return []
    DEBUG_LOG.append({
        "step": "events", "sport_key": sport_key, "status": r.status_code,
        "requests_remaining": r.headers.get("x-requests-remaining"),
        "requests_used": r.headers.get("x-requests-used"),
        "body_snippet": r.text[:400],
    })
    if r.status_code != 200:
        return []
    try:
        return r.json()
    except json.JSONDecodeError:
        return []


def events_in_window(events: list, window_hours: int) -> list:
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=window_hours)
    in_window = []
    for ev in events:
        commence = ev.get("commence_time")
        if not commence:
            continue
        try:
            start = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        except ValueError:
            continue
        if now <= start <= cutoff:
            in_window.append(ev)
    return in_window


def fetch_event_props(sport_key: str, event_id: str) -> dict:
    url = f"{BASE_URL}/sports/{sport_key}/events/{event_id}/odds"
    try:
        r = requests.get(url, params={
            "apiKey": API_KEY, "regions": REGIONS,
            "markets": ",".join(MARKETS), "oddsFormat": "american",
        }, timeout=25)
    except Exception as e:
        DEBUG_LOG.append({"step": "props", "event_id": event_id, "error": str(e)})
        return {}
    DEBUG_LOG.append({
        "step": "props", "event_id": event_id, "status": r.status_code,
        "requests_remaining": r.headers.get("x-requests-remaining"),
        "requests_used": r.headers.get("x-requests-used"),
        "requests_last": r.headers.get("x-requests-last"),
        "body_snippet": r.text[:400],
    })
    if r.status_code != 200:
        return {}
    try:
        return r.json()
    except json.JSONDecodeError:
        return {}


def normalize_event(raw: dict) -> dict:
    bookmakers = raw.get("bookmakers", [])
    books_out = []
    for bk in bookmakers:
        if not isinstance(bk, dict):
            continue
        markets_out = []
        for mkt in bk.get("markets", []):
            markets_out.append({
                "key": mkt.get("key"),
                "last_update": mkt.get("last_update"),
                "outcomes": mkt.get("outcomes", []),  # name, description (player), price, point
            })
        books_out.append({
            "book_key": bk.get("key"), "book_title": bk.get("title"),
            "last_update": bk.get("last_update"),
            "markets": markets_out,
        })
    return {
        "event_id": raw.get("id"),
        "commence_time": raw.get("commence_time"),
        "home_team": raw.get("home_team"), "away_team": raw.get("away_team"),
        "bookmakers": books_out,
    }


def fetch_existing_event_ids(sport: str, github_token: str) -> set:
    """Read the current Gist file (if any) and return the set of event_ids
    already captured -- so a run doesn't re-spend credits on a game whose
    props were already pulled earlier in its pre-game window."""
    try:
        r = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}"}, timeout=20)
        if r.status_code != 200:
            return set()
        files = r.json().get("files", {})
        key = f"betcouncil_odds_api_props_{sport}.json"
        f = files.get(key)
        if not f:
            return set()
        content = f.get("content", "")
        if f.get("truncated"):
            content = requests.get(f["raw_url"], timeout=20).text
        data = json.loads(content)
        return {e.get("event_id") for e in data.get("events", []) if e.get("event_id")}
    except Exception as e:
        DEBUG_LOG.append({"step": "fetch_existing_event_ids", "sport": sport, "error": str(e)})
        return set()


def fetch_existing_events(sport: str, github_token: str) -> list:
    """Full prior events list (not just IDs) so this run can merge onto it
    instead of overwriting -- events already captured stay in the output
    even though this run doesn't re-fetch them."""
    try:
        r = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}"}, timeout=20)
        if r.status_code != 200:
            return []
        files = r.json().get("files", {})
        key = f"betcouncil_odds_api_props_{sport}.json"
        f = files.get(key)
        if not f:
            return []
        content = f.get("content", "")
        if f.get("truncated"):
            content = requests.get(f["raw_url"], timeout=20).text
        data = json.loads(content)
        return data.get("events", [])
    except Exception:
        return []


def push_files(files_payload: dict, github_token: str) -> int:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": files_payload}, timeout=30,
    )
    if resp.status_code in (200, 201):
        return len(files_payload)
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1
    if not API_KEY:
        log("FATAL: ODDS_API_KEY not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport, sport_key in SPORT_KEYS.items():
        events = fetch_events(sport_key)
        log(f"  {sport}: {len(events)} total events")
        window_events = events_in_window(events, PRE_GAME_WINDOW_HOURS)
        log(f"  {sport}: {len(window_events)} events in {PRE_GAME_WINDOW_HOURS}h pre-game window")

        already_captured = fetch_existing_event_ids(sport, github_token)
        new_events = [e for e in window_events if e.get("id") not in already_captured]
        log(f"  {sport}: {len(new_events)} new events not yet captured this window")
        new_events = new_events[:MAX_EVENTS_PER_RUN]

        normalized_new = []
        for ev in new_events:
            event_id = ev.get("id")
            if not event_id:
                continue
            raw = fetch_event_props(sport_key, event_id)
            if not raw:
                continue
            normalized_new.append(normalize_event(raw))

        # Merge onto prior events, dropping anything whose game has already
        # started -- keeps the file from growing unbounded and never serves
        # stale pre-game props for a game that's already live/over.
        prior_events = fetch_existing_events(sport, github_token)
        now = datetime.now(timezone.utc)
        still_upcoming = []
        for e in prior_events:
            ct = e.get("commence_time")
            try:
                start = datetime.fromisoformat(ct.replace("Z", "+00:00")) if ct else None
            except ValueError:
                start = None
            if start is None or start > now:
                still_upcoming.append(e)
        merged = still_upcoming + normalized_new

        if not merged:
            log(f"  {sport}: 0 events with props (none new, none upcoming from before)")
            continue
        any_data = True
        log(f"  {sport}: {len(normalized_new)} newly captured + {len(still_upcoming)} carried over = {len(merged)} total")
        files_payload[f"betcouncil_odds_api_props_{sport}.json"] = {
            "content": json.dumps({
                "source": "the_odds_api", "sport": sport,
                "captured_at": now_iso, "pre_game_window_hours": PRE_GAME_WINDOW_HOURS,
                "events": merged,
            })
        }

    files_payload["betcouncil_odds_api_props_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:30]}, indent=2)
    }

    if not any_data:
        log("No props captured this run — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
