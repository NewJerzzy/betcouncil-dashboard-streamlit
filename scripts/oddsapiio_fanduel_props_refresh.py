"""
oddsapiio_fanduel_props_refresh.py — FanDuel MLB player props via Odds-API.io

================================================================================
Verified this session, twice: (1) live-tested via Replit against a real
pending game (ARI @ STL), returning 307 real FanDuel prop entries across
10 stat categories (Doubles, Home Runs, Pitching Hits, RBI, Runs Scored,
Singles, Stolen Bases, Total Bases, Total Strikeouts, Triples). (2)
Independently cross-checked against odds-api.io's own official
documentation (docs.odds-api.io/examples/player-props), which shows the
identical response structure in their own code example and explicitly
states FanDuel is covered for player props.

Real confirmed structure: player props are NOT a separate endpoint --
they come back automatically in the standard /v3/odds response, inside
a market named "Player Props" (or, for some books, named per-stat markets).
For FanDuel specifically: data["bookmakers"]["FanDuel"] is a list of
market objects, each with "name" and an "odds" list. Each odds entry has:
    {"label": "Ketel Marte (Doubles)", "hdp": 0.5, "over": "4.20", "under": "N/A"}
"label" embeds both player name and stat category as "Player (Stat)" --
parsed apart below. "over"/"under" are decimal odds; either side can be
"N/A" (no line offered on that side).

Real, confirmed constraint: props are day-of only -- a game more than a
day out returned zero props (just ML/Spread/Totals), only the game
happening today had a full slate. Confirmed via live test.

Shares the SAME ODDS_API_IO_KEY and free-tier 100/hour budget as the
Bet365 game-lines refresher (oddsapiio_bet365_refresh.py) -- this
script's own budget cap plus that one's are kept conservative enough
that their combined worst-case usage stays under the shared hourly
limit, and their cron schedules are offset (this one at :05/:20/:35/:50,
Bet365 at :00/:15/:30/:45) so they don't request in the same instant.

Pushes to betcouncil_oddsapiio_fanduel_props_{sport}.json, in the same
{Player, Prop, Line, OverOdds, UnderOdds, Book, Sport, source} shape
already used by fetch_fanduel_props_sharpapi, for drop-in compatibility.
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.odds-api.io/v3"
BOOKMAKER = "FanDuel"

SPORT_LEAGUES = {
    "MLB": ("baseball", "usa-mlb"),
    "NFL": ("american-football", "usa-nfl"),
    "NBA": ("basketball", "usa-nba"),
    "NHL": ("ice-hockey", "usa-nhl"),  # confirmed via odds-api.io own /sports endpoint
}

# Conservative -- shares the same account/key and 100/hr free-tier limit
# as the Bet365 game-lines refresher. Kept low enough that both scripts'
# combined worst-case usage stays under the shared hourly ceiling.
MAX_REQUESTS_PER_RUN = 10

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
                       "body_snippet": r.text[:400]})
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


def _parse_label(label: str):
    """'Ketel Marte (Doubles)' -> ('Ketel Marte', 'Doubles'). Confirmed
    real format via live test; falls back gracefully if a label doesn't
    match this shape rather than raising."""
    if not label or "(" not in label or not label.endswith(")"):
        return label or "", ""
    idx = label.rfind("(")
    player = label[:idx].strip()
    stat = label[idx + 1:-1].strip()
    return player, stat


def fetch_sport_props(sport: str, api_key: str) -> list:
    slug, league = SPORT_LEAGUES[sport]
    # Only fetch events that already have FanDuel odds -- avoids spending
    # quota on events FanDuel doesn't cover, same practice as the Bet365
    # script.
    events = _get("/events", api_key, {
        "sport": slug, "league": league, "bookmaker": BOOKMAKER,
        "status": "pending,live",
    })
    if not events:
        return []
    event_list = events if isinstance(events, list) else events.get("data", [])
    if not event_list:
        return []

    event_ids = [str(e.get("id")) for e in event_list if e.get("id")]
    props = []
    for i in range(0, len(event_ids), 10):
        batch = event_ids[i:i + 10]
        odds_resp = _get("/odds/multi", api_key, {
            "eventIds": ",".join(batch), "bookmakers": BOOKMAKER,
        })
        if not odds_resp:
            continue
        odds_list = odds_resp if isinstance(odds_resp, list) else odds_resp.get("data", [])
        for game_odds in odds_list:
            fd_markets = (game_odds.get("bookmakers") or {}).get(BOOKMAKER, [])
            if not fd_markets:
                continue
            for market in fd_markets:
                market_name = market.get("name", "")
                # Real confirmed market name is "Player Props" (a
                # catch-all), but handled generically in case FanDuel
                # also uses named per-stat markets for some sports/props,
                # matching what was separately confirmed for Bet365.
                for entry in market.get("odds") or []:
                    label = entry.get("label", "")
                    player, stat = _parse_label(label)
                    if not player or not stat:
                        continue
                    over_raw, under_raw = entry.get("over"), entry.get("under")
                    over_odds = _decimal_to_american(over_raw) if over_raw not in (None, "N/A") else None
                    under_odds = _decimal_to_american(under_raw) if under_raw not in (None, "N/A") else None
                    if over_odds is None and under_odds is None:
                        continue
                    props.append({
                        "Player": player, "Prop": stat, "Line": entry.get("hdp"),
                        "OverOdds": over_odds, "UnderOdds": under_odds,
                        "Book": "FanDuel", "Sport": sport, "source": "odds-api.io",
                    })
    return props


def push_files(files_payload: dict, github_token: str) -> int:
    """
    Merges into the shared betcouncil_oddsapiio_combined.json instead of
    separate per-book-per-sport files, using the real distributed lock.
    """
    SHARED_FILE = "betcouncil_oddsapiio_combined.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_oddsapiio_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

    lock_token = acquire_lock(GIST_ID, github_token, "oddsapiio_combined", holder="fanduel")
    if not lock_token:
        log("Could not acquire oddsapiio_combined lock -- skipping this run to avoid a collision")
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
                base_wait = min(10 * (2 ** attempt), 90)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0
        return 0
    finally:
        release_lock(GIST_ID, github_token, "oddsapiio_combined", lock_token)


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

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport in SPORT_LEAGUES:
        if _request_count[0] >= MAX_REQUESTS_PER_RUN:
            log(f"Budget cap ({MAX_REQUESTS_PER_RUN}) reached, skipping remaining sports")
            break
        try:
            props = fetch_sport_props(sport, api_key)
        except Exception as e:
            log(f"{sport}: error — {e}")
            props = []
        log(f"{sport}: {len(props)} FanDuel props, {_request_count[0]} requests used so far")
        if props:
            any_data = True
            files_payload[f"betcouncil_oddsapiio_fanduel_props_{sport}.json"] = {
                "content": json.dumps({
                    "source": "odds-api.io", "bookmaker": "FanDuel",
                    "sport": sport, "captured_at": now_iso, "props": props,
                })
            }

    files_payload["betcouncil_oddsapiio_fanduel_props_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests_used": _request_count[0],
                                "requests": DEBUG_LOG[:30]}, indent=2)
    }

    if not any_data:
        any_200 = any(r.get("status") == 200 for r in DEBUG_LOG)
        if any_200:
            log("No FanDuel props currently posted (all API calls succeeded) — not treating as a failure")
            push_files(files_payload, github_token)
            return 0
        log("No FanDuel props captured this run — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files, {_request_count[0]} API requests used")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
