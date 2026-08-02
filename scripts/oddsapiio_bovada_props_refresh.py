"""
oddsapiio_bovada_props_refresh.py — Bovada MLB player props via Odds-API.io

================================================================================
Confirmed live this session (separate account/key from the Bet365+FanDuel
one, since odds-api.io's free tier caps at 2 bookmakers per key):
  - 18/18 real MLB events returned with Bovada odds
  - Player props come back in the exact same /odds/multi call as game
    lines -- no separate request needed, same pattern as FanDuel/Bet365
  - Catch-all "Player Props" market (same as FanDuel, not named per-stat
    like Bet365), with an IDENTICAL "Player (Stat)" label format:
        {"label": "Lars Nootbaar (Hits, Runs and RBIs)", "hdp": 1.5,
         "over": "2.100", "under": "1.690"}
        {"label": "Randy Dobnak (Pitcher Strikeouts)", "hdp": 3.5,
         "over": "2.300", "under": "1.588"}
    -- meaning the same label-parsing logic already built and verified
    for FanDuel works here unchanged.
  - Bonus confirmed detail: Spread and Totals markets return 7 entries
    each (alternate lines), not just 1 like Bet365 -- this script still
    only takes the first (main) line for game-line context, matching the
    existing pattern; alternates aren't captured here.
  - Props are game-selective (day-of only) -- confirmed same constraint
    as FanDuel/Bet365.

Uses its own account/key (ODDS_API_IO_KEY_BOVADA) -- separate from
ODDS_API_IO_KEY (Bet365 + FanDuel), since the free tier caps each key at
2 bookmakers. Runs at :10/:25/:40/:55 -- offset from both the Bet365
(:00/:15/:30/:45) and FanDuel props (:05/:20/:35/:50) schedules, though
since this uses a different account entirely, there's no shared budget
to protect here (unlike those two, which share one key).

Pushes to betcouncil_oddsapiio_bovada_props_{sport}.json, in the same
{Player, Prop, Line, OverOdds, UnderOdds, Book, Sport, source} shape
used by the existing fetch_bovada_props, for drop-in compatibility.
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
BOOKMAKER = "Bovada"

SPORT_LEAGUES = {
    "MLB": ("baseball", "usa-mlb"),
    "NFL": ("american-football", "usa-nfl"),
    "NBA": ("basketball", "usa-nba"),
    "NHL": ("ice-hockey", "usa-nhl"),  # confirmed via odds-api.io's own /sports
                                        # endpoint after "hockey" and "nhl" both 400'd
}

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
    """'Lars Nootbaar (Hits, Runs and RBIs)' -> ('Lars Nootbaar', 'Hits, Runs and RBIs').
    Confirmed identical format to FanDuel via live test."""
    if not label or "(" not in label or not label.endswith(")"):
        return label or "", ""
    idx = label.rfind("(")
    player = label[:idx].strip()
    stat = label[idx + 1:-1].strip()
    return player, stat


def fetch_sport_props(sport: str, api_key: str) -> list:
    slug, league = SPORT_LEAGUES[sport]
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
            bv_markets = (game_odds.get("bookmakers") or {}).get(BOOKMAKER, [])
            if not bv_markets:
                continue
            for market in bv_markets:
                market_name = market.get("name", "")
                # Real confirmed market name is "Player Props" (a
                # catch-all, same as FanDuel), handled generically in
                # case that varies by sport.
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
                        "Book": "Bovada", "Sport": sport, "source": "odds-api.io",
                    })
    return props


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
    api_key = os.environ.get("ODDS_API_IO_KEY_BOVADA")
    if not github_token or not api_key:
        log("FATAL: GITHUB_TOKEN or ODDS_API_IO_KEY_BOVADA not set")
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
        log(f"{sport}: {len(props)} Bovada props, {_request_count[0]} requests used so far")
        if props:
            any_data = True
            files_payload[f"betcouncil_oddsapiio_bovada_props_{sport}.json"] = {
                "content": json.dumps({
                    "source": "odds-api.io", "bookmaker": "Bovada",
                    "sport": sport, "captured_at": now_iso, "props": props,
                })
            }

    files_payload["betcouncil_oddsapiio_bovada_props_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests_used": _request_count[0],
                                "requests": DEBUG_LOG[:30]}, indent=2)
    }

    if not any_data:
        # Was: unconditional "return 1" here -- treated a genuinely empty
        # result (all API calls succeeded, Bovada just hasn't posted player
        # props for these games yet) the same as a real failure. Confirmed
        # live 2026-07-25/26: 3 straight runs failed this way with every
        # single request returning a valid 200 -- moneylines/events present,
        # zero player-prop markets in the response at that hour. That's a
        # normal "nothing to report yet" outcome, not a break.
        any_200 = any(r.get("status") == 200 for r in DEBUG_LOG)
        if any_200:
            log("No Bovada player props currently posted (all API calls succeeded) — not treating as a failure")
            push_files(files_payload, github_token)
            return 0
        log("No Bovada props captured this run — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files, {_request_count[0]} API requests used")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
