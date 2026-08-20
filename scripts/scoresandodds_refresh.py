"""
scoresandodds_refresh.py — multi-book odds comparison via Action Network's public Lambda (no auth)
================================================================================

ScoresAndOdds.com is Action Network-owned (same infrastructure as
SportsInsights/RotoGrinders), server-rendered by a plain Apache stack —
not a modern SPA framework. The page embeds data-event="mlb/{eventId}"
attributes on custom elements; a vanilla JS file reads them and calls a
shared AWS API Gateway Lambda with zero auth:

    GET https://rga51lus77.execute-api.us-east-1.amazonaws.com/prod/market-comparison
        ?event=mlb%2F{eventId}&market={moneyline|spread|total}

Confirmed live 2026-07-16/17 — cross-validated event ID 90482950 (Mets @
Phillies) against 4 other independently-verified sources this session
(MyBookie, Dimers, VegasInsider, Sports Insights all resolved the same
game). The same Lambda endpoint, called with only ?sport=mlb (no event
ID, no market), was found earlier (RotoGrinders investigation) to return
sportsbook metadata only and crash on a bare event ID — that's a
different, incomplete parameter combination, not a contradiction: this
script always sends both `event` and `market` together, matching the
call pattern confirmed working.

Full multi-book comparison — 11 real books per game (betmgm, draftkings,
caesars, fanduel, hardrock, fanatics, bet365, riverscasino, sleeper,
underdog, prizepicks) confirmed with no paywall on any field. This is
exactly the shape build_game_line_consensus() needs — a genuine
multi-book blend source, not just one more comparison chip.

Event IDs are discovered by parsing data-event attributes off the
public /mlb/odds page HTML (same event ID system as Sports Insights,
per the investigation — reusing that source's EventId values directly
would also work, but this scrapes independently so it doesn't depend on
that other harvester having run first).

Pushes to betcouncil_scoresandodds_{SPORT}.json.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
import random
import time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
ODDS_PAGE_URL = "https://www.scoresandodds.com/{sport_path}/odds"
LAMBDA_URL = "https://rga51lus77.execute-api.us-east-1.amazonaws.com/prod/market-comparison"
SPORT_PATHS = {"MLB": "mlb", "NBA": "nba", "NFL": "nfl", "NHL": "nhl", "WNBA": "wnba"}
MARKETS = ["moneyline", "spread", "total"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/html",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def discover_event_ids(sport_path: str) -> list:
    url = ODDS_PAGE_URL.format(sport_path=sport_path)
    r = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            DEBUG_LOG.append({"step": "discover", "url": url, "status": r.status_code,
                               "body_len": len(r.text), "attempt": attempt + 1})
            if r.status_code == 200:
                break
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return []
        except requests.exceptions.RequestException as e:
            DEBUG_LOG.append({"step": "discover", "url": url, "status": "exception",
                               "body_snippet": str(e)[:300], "attempt": attempt + 1})
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return []
    if r is None or r.status_code != 200:
        return []
    return sorted(set(re.findall(rf'data-event="({sport_path}/\d+)"', r.text)))


def fetch_market(event_key: str, market: str) -> dict:
    params = {"event": event_key, "market": market}
    r = None
    for attempt in range(2):
        try:
            r = requests.get(LAMBDA_URL, params=params, headers=HEADERS, timeout=15)
            DEBUG_LOG.append({"step": "fetch_market", "event": event_key, "market": market,
                               "status": r.status_code, "body_snippet": r.text[:400],
                               "attempt": attempt + 1})
            if r.status_code == 200:
                break
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 1:
                time.sleep(1.5)
                continue
            return {}
        except requests.exceptions.RequestException as e:
            DEBUG_LOG.append({"step": "fetch_market", "event": event_key, "market": market,
                               "status": "exception", "body_snippet": str(e)[:300],
                               "attempt": attempt + 1})
            if attempt < 1:
                time.sleep(1.5)
                continue
            return {}
    if r is None or r.status_code != 200:
        return {}
    try:
        return r.json()
    except json.JSONDecodeError:
        return {}


def normalize_game(event_key: str, moneyline: dict, spread: dict, total: dict) -> dict:
    event_meta = moneyline.get("event") or spread.get("event") or total.get("event") or {}
    home, away = event_meta.get("home", {}), event_meta.get("away", {})

    def _market_row(data, kind):
        rows = data.get("markets", [])
        if not rows:
            return {}
        m = rows[0]
        row = {
            "value": m.get("value"), "favorite": m.get("favorite"),
            "away": m.get("away") if kind != "total" else m.get("under"),
            "home": m.get("home") if kind != "total" else m.get("over"),
            "comparison": m.get("comparison", {}),
        }
        return row

    return {
        "event_key": event_key,
        "home_team": home.get("key"), "away_team": away.get("key"),
        "home_score": home.get("score"), "away_score": away.get("score"),
        "moneyline": _market_row(moneyline, "moneyline"),
        "spread": _market_row(spread, "spread"),
        "total": _market_row(total, "total"),
    }


def fetch_sport_games(sport: str, sport_path: str) -> list:
    try:
        event_keys = discover_event_ids(sport_path)
    except Exception as e:
        log(f"  {sport}: discovery error — {e}")
        return []
    if not event_keys:
        return []

    games = []
    for event_key in event_keys[:40]:  # reasonable cap per run
        try:
            ml = fetch_market(event_key, "moneyline")
            sp = fetch_market(event_key, "spread")
            to = fetch_market(event_key, "total")
        except Exception as e:
            log(f"  {sport}/{event_key}: fetch error — {e}")
            continue
        if not (ml or sp or to):
            continue
        games.append(normalize_game(event_key, ml, sp, to))
    return games


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

    for sport, sport_path in SPORT_PATHS.items():
        games = fetch_sport_games(sport, sport_path)
        if not games:
            log(f"  {sport}: 0 games")
            continue
        any_data = True
        log(f"  {sport}: {len(games)} games")
        files_payload[f"betcouncil_scoresandodds_{sport}.json"] = {
            "content": json.dumps({
                "source": "scoresandodds", "sport": sport,
                "captured_at": now_iso, "games": games,
            })
        }

    files_payload["betcouncil_scoresandodds_debug.json"] = {
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
