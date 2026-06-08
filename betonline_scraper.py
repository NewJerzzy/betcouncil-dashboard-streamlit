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

def get_game_ids(sport="NBA"):
    """Get today's game IDs from BetOnline menu."""
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


def push_to_gist(props, sport):
    """Push props to GitHub Gist for BetCouncil to read."""
    if not GITHUB_TOKEN or GITHUB_TOKEN == "YOUR_GITHUB_TOKEN_HERE":
        print("  ⚠️  Fill in GITHUB_TOKEN before pushing")
        return False

    payload = {
        "sport":      sport,
        "date":       date.today().isoformat(),
        "timestamp":  datetime.now().isoformat(),
        "prop_count": len(props),
        "book":       "BetOnline",
        "props":      props,
    }

    r = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2)}}},
        timeout=10
    )
    if r.status_code == 200:
        print(f"  ✅ Pushed {len(props)} props to Gist")
        return True
    else:
        print(f"  ❌ Gist push failed: {r.status_code}")
        return False


def scrape(sport="NBA", no_push=False):
    print(f"\n{'='*50}")
    print(f"BetOnline {sport} | {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}")

    # Get game IDs
    games = get_game_ids(sport)

    if not games:
        # Fallback: try known game ID format
        print("  No games from menu — trying get-event directly")
        # Try today's games via alternate endpoint
        r = requests.post(
            f"{BASE_URL}/get-event",
            headers=HEADERS,
            json={"sport": SPORT_MAP[sport][0], "league": SPORT_MAP[sport][1]},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            print(f"  get-event returned: {len(str(data)):,} chars")
            print(f"  Preview: {str(data)[:200]}")
        return []

    all_props = []
    for game in games:
        gid     = game["gameID"]
        matchup = game.get("matchup", str(gid))
        print(f"\n  Game: {matchup} ({gid})")

        # Try get-linked-events first
        props = get_props_for_game(gid, sport)

        # If empty, try get-event
        if not props:
            ev_data = get_event_details(gid, sport)
            if ev_data:
                print(f"    get-event returned data — parsing...")
                print(f"    Preview: {str(ev_data)[:150]}")

        print(f"    Props: {len(props)}")
        all_props.extend(props)
        time.sleep(0.5)

    print(f"\nTotal: {len(all_props)} props")

    # Show sample
    for p in all_props[:5]:
        print(f"  {p['Player']:25} {p['Prop']:20} {p['Line']} {p['Side']}")

    if not no_push and all_props:
        push_to_gist(all_props, sport)

    return all_props


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",   default="NBA", choices=["NBA","MLB","NHL","WNBA","NFL"])
    parser.add_argument("--all",     action="store_true")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    sports = ["NBA","MLB","NHL","WNBA"] if args.all else [args.sport]
    for s in sports:
        scrape(s, no_push=args.no_push)
