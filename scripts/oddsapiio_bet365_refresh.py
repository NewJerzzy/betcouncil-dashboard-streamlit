"""
oddsapiio_bet365_refresh.py — Bet365 game lines (moneyline, spread, totals)
via Odds-API.io.

================================================================================
Verified live this session (via Replit, using the real ODDS_API_IO_KEY
secret) against a real MLB game (Padres @ Braves):
  - Base URL: https://api.odds-api.io/v3 (cross-checked independently
    against odds-api-io's own official Python/Node SDK repos on GitHub --
    not just the live-test report)
  - Auth: ?apiKey=KEY query param (also confirmed in the vendor's own
    "Best Practices" docs example code)
  - Real response shape confirmed for all three markets on a Bet365 line:
        ML:      {"home": "1.44", "away": "2.85"}
        Spread:  {"hdp": -1.5, "home": "1.90", "away": "1.90"}
        Totals:  {"hdp": 8, "over": "1.90", "under": "1.90"}
    (decimal/European odds, not American -- converted below)
  - /v3/odds/multi batches up to 10 events into ONE request (confirmed
    both by the live test and the vendor's own best-practices example
    code) -- a full ~15-game MLB day fits in 2 requests
  - Free tier: 100 req/hour, confirmed live. Also independently confirmed
    via the vendor's official Node SDK README: free tier is additionally
    capped at 2 bookmakers selected at once -- not a problem here since
    only Bet365 (1 bookmaker) is ever requested.
  - events endpoint supports filtering to only events that already have a
    given bookmaker's odds (bookmaker=Bet365) -- used here so bandwidth/
    quota isn't spent on events Bet365 doesn't even cover.

REPLACES the previous fetch_bet365_game_lines() FALLBACK path (Kambi),
which was already flagged in that function's own docstring as very
likely non-functional (Bet365 isn't a known Kambi platform customer).
Sits as a NEW PRIMARY alongside the existing Unabated source, which only
provided partial (moneyline/match-result) coverage for Bet365 -- this
adds the previously-missing spread and totals markets.

Hard daily request budget: given the free tier's 100/hour limit and that
this workflow runs every 15 min (96 runs/day), a conservative per-run cap
keeps this well inside budget even with other consumers of the same key
in mind later.
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.odds-api.io/v3"
BOOKMAKER = "Bet365"

# Sport slug -> (odds-api.io sport slug, league filter). Only MLB confirmed
# live and in-season this session; others added but gracefully no-op if
# empty/out of season (same pattern as every other harvester this session).
SPORT_LEAGUES = {
    "MLB": ("baseball", "usa-mlb"),
    "NFL": ("american-football", "usa-nfl"),
    "NBA": ("basketball", "usa-nba"),
    "NHL": ("hockey", "usa-nhl"),
}

# Hard per-run request budget -- confirmed free tier is 100/hour; this
# workflow runs every 15 min (4x/hour), so capping well under 25/run
# leaves real headroom rather than running the account right to the edge.
MAX_REQUESTS_PER_RUN = 15

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BetCouncilResearch/1.0)"}
DEBUG_LOG: list = []
_request_count = [0]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _get(path: str, api_key: str, params: dict):
    if _request_count[0] >= MAX_REQUESTS_PER_RUN:
        DEBUG_LOG.append({"path": path, "skipped": "budget cap reached this run"})
        return None
    q = dict(params)
    q["apiKey"] = api_key
    _request_count[0] += 1
    try:
        r = requests.get(f"{BASE_URL}{path}", params=q, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"path": path, "params": {k: v for k, v in params.items()}, "error": str(e)})
        return None
    DEBUG_LOG.append({"path": path, "params": {k: v for k, v in params.items()},
                       "status": r.status_code, "bytes": len(r.content),
                       "body_snippet": r.text[:1800]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def _decimal_to_american(dec_str) -> int:
    try:
        dec = float(dec_str)
    except (TypeError, ValueError):
        return 0
    if dec <= 1.0:
        return 0
    if dec >= 2.0:
        return round((dec - 1) * 100)
    return round(-100 / (dec - 1))


_GAME_LINE_MARKETS = {"ML", "Spread", "Totals"}


def _parse_bet365_prop_player(label: str) -> str:
    """Bet365's prop label format is 'Player (AltLineNum) (Line)' --
    different from FanDuel's cleaner 'Player (Stat)' (confirmed via live
    test: 'Nolan Arenado (1) (0.5)'). The stat comes from the market name
    instead (e.g. 'Home Runs O/U'), not the label -- only the player name
    is extracted here, everything before the first '('."""
    if not label:
        return ""
    idx = label.find("(")
    return (label[:idx] if idx != -1 else label).strip()


def _market_name_to_stat(market_name: str) -> str:
    """'Home Runs O/U' -> 'Home Runs', 'Pitcher Strikeouts O/U' -> 'Pitcher Strikeouts'."""
    return market_name.replace(" O/U", "").strip()


def fetch_sport(sport: str, api_key: str) -> tuple:
    slug, league = SPORT_LEAGUES[sport]
    # Only fetch events that already have Bet365 odds -- vendor's own
    # documented best practice, avoids spending quota on events Bet365
    # doesn't cover at all.
    events = _get("/events", api_key, {
        "sport": slug, "league": league, "bookmaker": BOOKMAKER,
        "status": "pending,live",
    })
    if not events:
        return [], []
    event_list = events if isinstance(events, list) else events.get("data", [])
    if not event_list:
        return [], []

    games = []
    props = []
    # Batch up to 10 events per /odds/multi call -- confirmed live this
    # session (3 events = 1 request), matches the vendor's own
    # best-practices example exactly.
    event_ids = [str(e.get("id") or e.get("eventId")) for e in event_list if e.get("id") or e.get("eventId")]
    for i in range(0, len(event_ids), 10):
        batch = event_ids[i:i + 10]
        odds_resp = _get("/odds/multi", api_key, {
            "eventIds": ",".join(batch), "bookmakers": BOOKMAKER,
        })
        if not odds_resp:
            continue
        odds_list = odds_resp if isinstance(odds_resp, list) else odds_resp.get("data", [])
        for game_odds in odds_list:
            bet365_markets = (game_odds.get("bookmakers") or {}).get(BOOKMAKER, [])
            if not bet365_markets:
                continue
            # Real confirmed shape: a LIST of {"name": "ML"|"Spread"|"Totals"|...,
            # "odds": [{...}]} -- not a flat dict as first assumed.
            by_market = {}
            for m in bet365_markets:
                name = m.get("name")
                odds_entries = m.get("odds") or []
                if name and odds_entries:
                    by_market[name] = odds_entries[0]
                    # Props markets (anything not a known game-line market)
                    # have MANY odds entries -- one per player -- not just
                    # the first. Confirmed live: 'Home Runs O/U' returned
                    # 53 entries, 'Pitcher Strikeouts O/U' returned 18.
                    if name not in _GAME_LINE_MARKETS and len(odds_entries) > 0:
                        stat = _market_name_to_stat(name)
                        for entry in odds_entries:
                            player = _parse_bet365_prop_player(entry.get("label", ""))
                            if not player:
                                continue
                            props.append({
                                "Player": player, "Prop": stat, "Line": entry.get("hdp"),
                                "OverOdds": _decimal_to_american(entry.get("over")) if entry.get("over") not in (None, "N/A") else None,
                                "UnderOdds": _decimal_to_american(entry.get("under")) if entry.get("under") not in (None, "N/A") else None,
                                "Book": "Bet365", "Sport": sport, "source": "odds-api.io",
                            })

            ml = by_market.get("ML", {})
            spread = by_market.get("Spread", {})
            totals = by_market.get("Totals", {})
            if not (ml or spread or totals):
                continue
            games.append({
                "event_id": game_odds.get("id"),
                "home_team": game_odds.get("home"),
                "away_team": game_odds.get("away"),
                "home_ml": _decimal_to_american(ml.get("home")) if ml else None,
                "away_ml": _decimal_to_american(ml.get("away")) if ml else None,
                "spread_hdp": spread.get("hdp") if spread else None,
                "spread_home_odds": _decimal_to_american(spread.get("home")) if spread else None,
                "spread_away_odds": _decimal_to_american(spread.get("away")) if spread else None,
                "total_hdp": totals.get("hdp") if totals else None,
                "over_odds": _decimal_to_american(totals.get("over")) if totals else None,
                "under_odds": _decimal_to_american(totals.get("under")) if totals else None,
            })
    return games, props


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
    api_key = os.environ.get("ODDS_API_IO_KEY")
    if not github_token or not api_key:
        log("FATAL: GITHUB_TOKEN or ODDS_API_IO_KEY not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport in SPORT_LEAGUES:
        if _request_count[0] >= MAX_REQUESTS_PER_RUN:
            log(f"Budget cap ({MAX_REQUESTS_PER_RUN} requests) reached, skipping remaining sports")
            break
        try:
            games, props = fetch_sport(sport, api_key)
        except Exception as e:
            log(f"{sport}: error — {e}")
            games, props = [], []
        log(f"{sport}: {len(games)} Bet365 games, {len(props)} Bet365 props, {_request_count[0]} requests used so far")
        if games:
            any_data = True
            files_payload[f"betcouncil_oddsapiio_bet365_{sport}.json"] = {
                "content": json.dumps({
                    "source": "odds-api.io", "bookmaker": "Bet365",
                    "sport": sport, "captured_at": now_iso, "games": games,
                })
            }
        if props:
            any_data = True
            files_payload[f"betcouncil_oddsapiio_bet365_props_{sport}.json"] = {
                "content": json.dumps({
                    "source": "odds-api.io", "bookmaker": "Bet365",
                    "sport": sport, "captured_at": now_iso, "props": props,
                })
            }

    files_payload["betcouncil_oddsapiio_bet365_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests_used": _request_count[0],
                                "requests": DEBUG_LOG[:30]}, indent=2)
    }

    if not any_data:
        log("No Bet365 games captured this run — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files, {_request_count[0]} API requests used")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
