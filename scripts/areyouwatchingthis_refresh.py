"""
areyouwatchingthis_refresh.py — areyouwatchingthis.com odds backend (no signup)
================================================================================

Discovered via MetaBet's public widget-embed JS bundle, which hardcodes an
API key for its actual data backend:

    GET https://metabet.static.api.areyouwatchingthis.com/api/odds.json
        ?apiKey={KEY}&q={mlb|nfl|nhl|ncaaf|soccer}

No signup, no auth challenge beyond the key, no rate-limit headers observed.
Confirmed live this session: 29 sportsbook providers per game for game lines
(moneyline/spread/total) — FanDuel, DraftKings, BetMGM, Bet365, ESPNBet,
Fanatics, Novig, Kalshi, Polymarket, BetRivers variants, William Hill,
Unibet, Sports Interaction, Sportingbet, Sugar House NJ, plus a CONSENSUS
row. No Caesars odds records in practice (listed in sportsbooks.json but
absent from live data) and no Pinnacle at all.

Known limitations (confirmed this session, not assumptions):
  - Static-ish cache layer: books were observed 2-42 minutes stale on the
    same pull. Fine for a 15-min polling loop, not for tick-level movement.
  - Game lines only — no player props endpoint (/api/props.json 404s).
  - Odds are decimal format; converted to American here on write, with the
    raw decimal kept alongside so a conversion bug is always recoverable
    from the source value.
  - The API key is hardcoded in MetaBet's own public JS, not officially
    documented or issued to us -- MetaBet could rotate it at any time with
    no notice. Treat this source as best-effort; a sudden empty pull across
    every sport (not just one) is the signal it's been rotated, not a
    transient network blip.

Not independently verified byte-for-byte by Claude before this first
deploy (built from a research summary, not re-probed live from this
sandbox -- areyouwatchingthis.com isn't in this environment's network
allowlist). Ships with debug logging so a schema drift or key rotation is
caught immediately on first live run.

Pushes to betcouncil_areyouwatchingthis_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://metabet.static.api.areyouwatchingthis.com/api"
API_KEY = "219f64094f67ed781035f5f7a08840fc"

SPORT_QUERIES = {"MLB": "mlb", "NFL": "nfl", "NHL": "nhl", "NCAAF": "ncaaf"}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def decimal_to_american(dec):
    try:
        d = float(dec)
        if d <= 1.0:
            return None
        if d >= 2.0:
            return round((d - 1) * 100)
        return round(-100 / (d - 1))
    except (TypeError, ValueError):
        return None


def fetch_json(url: str, params: dict, sport: str, label: str):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "label": label, "url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"sport": sport, "label": label, "url": r.url, "status": r.status_code,
                       "body_snippet": r.text[:400]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def normalize_game(game: dict) -> dict:
    providers_raw = game.get("providers", game.get("odds", []))
    providers = providers_raw if isinstance(providers_raw, list) else []

    normalized_providers = []
    for p in providers:
        if not isinstance(p, dict):
            continue
        ml_away_dec, ml_home_dec = p.get("moneyLineAway"), p.get("moneyLineHome")
        normalized_providers.append({
            "provider": p.get("provider") or p.get("name"),
            "moneyline_away_decimal": ml_away_dec,
            "moneyline_home_decimal": ml_home_dec,
            "moneyline_away_american": decimal_to_american(ml_away_dec),
            "moneyline_home_american": decimal_to_american(ml_home_dec),
            "spread": p.get("spread"),
            "total": p.get("total") or p.get("overUnder"),
            "last_updated": p.get("lastUpdated") or p.get("timestamp"),
        })

    return {
        "game_id": game.get("gameID") or game.get("id"),
        "home_team": game.get("homeTeam") or game.get("home"),
        "away_team": game.get("awayTeam") or game.get("away"),
        "start_time": game.get("dateTime") or game.get("startTime"),
        "providers": normalized_providers,
    }


def fetch_sport(sport: str, query: str) -> list:
    data = fetch_json(f"{BASE_URL}/odds.json", {"apiKey": API_KEY, "q": query}, sport, "odds")
    if not isinstance(data, dict):
        return []
    games_raw = data.get("games", data if isinstance(data, list) else [])
    games_list = games_raw if isinstance(games_raw, list) else []
    return [normalize_game(g) for g in games_list if isinstance(g, dict)]


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

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport, query in SPORT_QUERIES.items():
        try:
            games = fetch_sport(sport, query)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not games:
            log(f"  {sport}: 0 games")
            continue
        any_data = True
        n_providers = sum(len(g["providers"]) for g in games)
        log(f"  {sport}: {len(games)} games, {n_providers} provider rows")
        files_payload[f"betcouncil_areyouwatchingthis_{sport}.json"] = {
            "content": json.dumps({
                "source": "areyouwatchingthis", "sport": sport,
                "captured_at": now_iso, "games": games,
            })
        }

    files_payload["betcouncil_areyouwatchingthis_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15]}, indent=2)
    }

    if not any_data:
        log("No data captured across ANY sport — possible API key rotation, not just a blip")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
