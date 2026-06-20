#!/usr/bin/env python3
"""
BetOnline Scraper
=================
Run on YOUR machine — uses api-offering.betonline.ag
Found via DevTools on betonline.ag/sportsbook

Usage:
  python3 betonline_scraper.py --sport NBA
  python3 betonline_scraper.py --sport MLB
  python3 betonline_scraper.py --all --no-push

Requirements: pip install requests
"""

import requests, json, time, argparse, base64
from datetime import datetime, date

# ── CONFIG ──────────────────────────────────────────────────
GITHUB_TOKEN = "YOUR_GITHUB_TOKEN_HERE"
GIST_ID      = "YOUR_GIST_ID_HERE"
GIST_FILE    = "betonline_props.json"

BASE_URL = "https://api-offering.betonline.ag/api/offering/sports"

HEADERS = {
    "Accept":          "application/json, text/plain",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type":    "application/json-patch+json",
    "gsetting":        "bolnasite",
    "Origin":          "https://www.betonline.ag",
    "Referer":         "https://www.betonline.ag/",
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3.1 Safari/605.1.15",
    "utc-offset":      "420",
}

MENU_HEADERS = {**HEADERS,
    "Content-Type": "application/json",
    "gsetting":     "bolsassite",
}

SPORT_MAP = {
    "NBA":  ("basketball", "nba"),
    "MLB":  ("baseball",   "mlb"),
    "NHL":  ("hockey",     "nhl"),
    "WNBA": ("basketball", "wnba"),
    "NFL":  ("football",   "nfl"),
}

# Props that are always OVER only
ALWAYS_OVER = {"home runs", "pitcher wins", "wins", "saves"}

def get_game_lines(sport="NBA"):
    """Get game lines (Spread/ML/Total) for a sport.

    CONFIRMED 2026-06-20 via real captured response body (not a guess): the live
    endpoint is POST api-offering.betonline.ag/api/offering/Sports/offering-by-league
    (note capital S in "Sports" — the old get-linked-events/get-event endpoints this
    file previously guessed at used lowercase "sports" and were never confirmed
    against a real response).

    Confirmed real response schema:
      GameOffering.GamesDescription[] -- list of {GameDate, Game: {...}}
      Game.GameId, AwayTeam, HomeTeam, AwayPitcher/HomePitcher (MLB), GameDateTime
      Game.AwayLine / Game.HomeLine -- each has SpreadLine, MoneyLine, TotalLine
        SpreadLine: {Point, Line}  -- Point is the spread number, Line is American odds
        MoneyLine: {Line}          -- Line is American odds directly
      Game.TotalLine.TotalLine.{Over,Under}.{Point,Line} -- total/over-under

    NOT confirmed: the exact POST request body this endpoint expects (only the
    response was captured, not request headers/payload). The body below is a
    best-effort guess based on the existing menu-discovery pattern in this file
    (sport/league key naming) and has NOT been verified — if this returns a 4xx,
    that's the next thing to check via a full Copy-as-cURL capture of this exact
    request, not the response parsing below, which IS verified against real data.

    NOTE: this endpoint returns GAME LINES only (Spread/ML/Total). Player props are
    not present in this response — Game.AdditionalMarketCount in the real capture
    (typically 5) implies they're a separate per-game request, not yet captured.
    get_props_for_game() below remains unconfirmed/guesswork until that capture
    happens.
    """
    sport_key, league_key = SPORT_MAP.get(sport, ("basketball", "nba"))
    games = []

    try:
        r = requests.post(
            "https://api-offering.betonline.ag/api/offering/Sports/offering-by-league",
            headers=HEADERS,
            json={"sport": sport_key, "league": league_key},
            timeout=10
        )
        if r.status_code != 200:
            print(f"  offering-by-league error: {r.status_code}")
            return []

        data = r.json()
        offering = data.get("GameOffering", {}) if isinstance(data, dict) else {}
        games_desc = offering.get("GamesDescription", []) or []

        for gd in games_desc:
            g = gd.get("Game", {})
            if not g:
                continue

            def _ml(line_block):
                ml = (line_block or {}).get("MoneyLine", {}) or {}
                v = ml.get("Line")
                return v if v not in (None, 0) else None

            def _spread(line_block):
                sp = (line_block or {}).get("SpreadLine", {}) or {}
                pt, ln = sp.get("Point"), sp.get("Line")
                if pt in (None, 0) and ln in (None, 0):
                    return None, None
                return pt, ln

            away_line = g.get("AwayLine", {})
            home_line = g.get("HomeLine", {})
            total_block = (g.get("TotalLine", {}) or {}).get("TotalLine", {}) or {}

            away_spread_pt, away_spread_ln = _spread(away_line)
            home_spread_pt, home_spread_ln = _spread(home_line)

            games.append({
                "GameId":      g.get("GameId"),
                "AwayTeam":    g.get("AwayTeam", ""),
                "HomeTeam":    g.get("HomeTeam", ""),
                "AwayPitcher": g.get("AwayPitcher", ""),
                "HomePitcher": g.get("HomePitcher", ""),
                "WagerCutOff": g.get("WagerCutOff", ""),
                "AwaySpreadPoint": away_spread_pt, "AwaySpreadOdds": away_spread_ln,
                "HomeSpreadPoint": home_spread_pt, "HomeSpreadOdds": home_spread_ln,
                "AwayML": _ml(away_line), "HomeML": _ml(home_line),
                "TotalPoint": total_block.get("Point"),
                "TotalOverOdds":  (total_block.get("Over", {}) or {}).get("Line"),
                "TotalUnderOdds": (total_block.get("Under", {}) or {}).get("Line"),
                "Book": "BetOnline", "Sport": sport, "source": "betonline_api",
            })

        print(f"  Found {len(games)} games with lines for {sport}")
        return games

    except Exception as e:
        print(f"  offering-by-league error: {e}")
        return []


def get_game_ids(sport="NBA"):
    """Get today's game IDs from BetOnline menu.

    UNCONFIRMED — kept as a fallback for player-prop discovery (get_props_for_game
    still needs real game IDs to query, until that endpoint is itself confirmed).
    Prefer get_game_lines() above for game-line data; its schema is verified.
    """
    sport_key, league_key = SPORT_MAP.get(sport, ("basketball","nba"))
    try:
        r = requests.post(
            "https://api-offering.betonline.ag/api/offering/Sports/get-menu",
            headers=MENU_HEADERS,
            data="{}",
            timeout=10
        )
        if r.status_code != 200:
            print(f"  Menu error: {r.status_code}")
            return []

        data = r.json()
        today = date.today().isoformat()
        game_ids = []

        # Navigate menu structure to find today's games
        sports = data if isinstance(data, list) else data.get("sports", data.get("items", []))
        for sp in sports:
            sp_name = str(sp.get("name","") or sp.get("sport","")).lower()
            if sport_key not in sp_name:
                continue
            leagues = sp.get("leagues", sp.get("children", []))
            for lg in leagues:
                lg_name = str(lg.get("name","") or lg.get("league","")).lower()
                if league_key not in lg_name:
                    continue
                events = lg.get("events", lg.get("games", lg.get("children", [])))
                for ev in events:
                    ev_date = str(ev.get("date","") or ev.get("startDate","") or ev.get("gameDate",""))
                    gid = ev.get("gameID") or ev.get("id") or ev.get("eventId")
                    if gid and today in ev_date:
                        game_ids.append({
                            "gameID": gid,
                            "matchup": ev.get("name","") or ev.get("description",""),
                            "sport": sport,
                            "league": league_key,
                        })

        print(f"  Found {len(game_ids)} games today for {sport}")
        return game_ids

    except Exception as e:
        print(f"  Menu error: {e}")
        return []


def get_props_for_game(game_id, sport="NBA"):
    """Get player props for a specific game."""
    sport_key, league_key = SPORT_MAP.get(sport, ("basketball","nba"))
    props = []

    try:
        r = requests.post(
            f"{BASE_URL}/get-linked-events",
            headers=HEADERS,
            json={
                "sport":        sport_key,
                "league":       league_key,
                "gameID":       game_id,
                "scheduleText": None,
            },
            timeout=10
        )
        if r.status_code != 200:
            return props

        data = r.json()

        # Parse response — structure may vary
        events = data if isinstance(data, list) else data.get("events", data.get("markets", [data]))

        for event in events:
            markets = event.get("markets", event.get("props", event.get("playerProps", [])))
            if not markets and isinstance(event, dict):
                # Try top-level keys
                for key in ["playerProps", "props", "lines", "offerings"]:
                    if key in event:
                        markets = event[key]
                        break

            for market in (markets or []):
                market_name = (market.get("name","") or
                               market.get("description","") or
                               market.get("marketName","")).strip()

                participants = (market.get("participants","") or
                                market.get("outcomes","") or
                                market.get("selections","") or [])

                if isinstance(participants, dict):
                    participants = list(participants.values())

                for part in participants:
                    player   = (part.get("name","") or
                                part.get("player","") or
                                part.get("description","")).strip()
                    line     = part.get("line") or part.get("handicap") or part.get("points")
                    over_ml  = part.get("overOdds") or part.get("over") or part.get("price")
                    under_ml = part.get("underOdds") or part.get("under")
                    side     = str(part.get("side","") or part.get("type","")).upper()

                    if not player or line is None:
                        continue

                    # Skip UNDER on always-OVER markets
                    if market_name.lower() in ALWAYS_OVER and side == "UNDER":
                        continue

                    props.append({
                        "Player":    player,
                        "Prop":      market_name,
                        "Line":      float(str(line).replace("+","")),
                        "Side":      side or "OVER",
                        "OverOdds":  str(over_ml) if over_ml else "—",
                        "UnderOdds": str(under_ml) if under_ml else "—",
                        "Book":      "BetOnline",
                        "Sport":     sport,
                        "source":    "betonline_api",
                    })

    except Exception as e:
        print(f"    Props error game {game_id}: {e}")

    return props


def get_event_details(game_id, sport="NBA"):
    """Alternative endpoint — get-event for full market list."""
    sport_key, league_key = SPORT_MAP.get(sport, ("basketball","nba"))
    try:
        r = requests.post(
            f"{BASE_URL}/get-event",
            headers=HEADERS,
            json={
                "sport":  sport_key,
                "league": league_key,
                "gameID": game_id,
            },
            timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"    get-event error: {e}")
    return None


def push_to_gist(props, lines, sport):
    """Push props and game lines to GitHub Gist for BetCouncil to read."""
    if not GITHUB_TOKEN or GITHUB_TOKEN == "YOUR_GITHUB_TOKEN_HERE":
        print("  ⚠️  Fill in GITHUB_TOKEN before pushing")
        return False

    payload = {
        "sport":      sport,
        "date":       date.today().isoformat(),
        "timestamp":  datetime.now().isoformat(),
        "prop_count": len(props),
        "line_count": len(lines),
        "book":       "BetOnline",
        "props":      props,
        "lines":      lines,
    }

    r = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2)}}},
        timeout=10
    )
    if r.status_code == 200:
        print(f"  ✅ Pushed {len(props)} props + {len(lines)} game lines to Gist")
        return True
    else:
        print(f"  ❌ Gist push failed: {r.status_code}")
        return False


def scrape(sport="NBA", no_push=False):
    print(f"\n{'='*50}")
    print(f"BetOnline {sport} | {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}")

    # Game lines — CONFIRMED endpoint/schema (see get_game_lines docstring)
    lines = get_game_lines(sport)
    for l in lines[:5]:
        print(f"  {l['AwayTeam']:25} @ {l['HomeTeam']:25} "
              f"ML {l['AwayML']}/{l['HomeML']}  Total {l['TotalPoint']}")

    # Player props — UNCONFIRMED, best-effort only (see get_game_ids/
    # get_props_for_game docstrings). Kept separate from the confirmed lines
    # above so a prop-fetch failure never hides working game-line data.
    games = get_game_ids(sport)
    all_props = []
    if games:
        for game in games:
            gid     = game["gameID"]
            matchup = game.get("matchup", str(gid))
            print(f"\n  Game: {matchup} ({gid})")
            props = get_props_for_game(gid, sport)
            print(f"    Props: {len(props)} (unconfirmed endpoint)")
            all_props.extend(props)
            time.sleep(0.5)
    else:
        print("  No games from menu — player props unavailable this run "
              "(menu endpoint itself is unconfirmed; game lines above are unaffected)")

    print(f"\nTotal: {len(lines)} games with lines, {len(all_props)} props")

    if not no_push and (lines or all_props):
        push_to_gist(all_props, lines, sport)

    return lines, all_props


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",   default="NBA", choices=["NBA","MLB","NHL","WNBA","NFL"])
    parser.add_argument("--all",     action="store_true")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    sports = ["NBA","MLB","NHL","WNBA"] if args.all else [args.sport]
    for s in sports:
        scrape(s, no_push=args.no_push)
