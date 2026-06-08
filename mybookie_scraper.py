#!/usr/bin/env python3
"""
MyBookie Scraper
================
Uses engine.mybookie.ag/sports_api/ endpoints discovered via DevTools.
Requires session cookies from your logged-in MyBookie session.

HOW TO UPDATE COOKIES (every 24-48 hours):
1. Log into mybookie.ag
2. Open DevTools → Network → XHR/Fetch
3. Click any request to engine.mybookie.ag
4. Copy the full Cookie header value
5. Paste it below as SESSION_COOKIE

Usage:
  python3 mybookie_scraper.py --sport NBA --no-push
  python3 mybookie_scraper.py --sport MLB
  python3 mybookie_scraper.py --all

Requirements: pip install requests
"""

import requests, json, time, argparse
from datetime import datetime, date

# ── CONFIG ──────────────────────────────────────────────────
GITHUB_TOKEN = "YOUR_GITHUB_TOKEN_HERE"
GIST_ID      = "YOUR_GIST_ID_HERE"
GIST_FILE    = "mybookie_props.json"

# Paste your full Cookie header value here (update every 24-48 hours)
SESSION_COOKIE = "PASTE_YOUR_COOKIE_HERE"

# These stay constant
CSRF_TOKEN  = "jWztcbtoo4x7a6XtQSalmlAdPeBWapyz2JMNvcDk"
XSRF_TOKEN  = "eyJpdiI6InUrWmRFM3RSNTlMbEJDbjA2SkNoNVE9PSIsInZhbHVlIjoiZHYyQnpnNk9Kbi9kVUUxYmlOeXJlNEQ5eEl3bnVpNnRnMVVnRGUwUEF5WUczZEVYcjVQdVhHN2xZcm9MRjBlZ0pDYy9QT1hrOW0zcEFaZjRGcldQVGhRMHBISmZUQThpZ1k5R1ZFQ20rT0dqUjhvTmFTOTJUa1F6dE9ka09hSUUiLCJtYWMiOiJlYWQwYmUyYTRhNjJhZmExYzVhMjRmYjAzNmUwMTU1NGU3YjQ1YzBjM2Q2MTM1YzRkMWI1YmRiZGIyNDMzNTRiIiwidGFnIjoiIn0="

ENGINE_BASE = "https://engine.mybookie.ag/sports_api"
DST_BASE    = "https://bv2-us.digitalsportstech.com/api"

SPORT_MAP = {
    "NBA":  {"sport": "basketball", "league": "nba",      "lineSportId": 13},
    "MLB":  {"sport": "baseball",   "league": "mlb",      "lineSportId": 5},
    "NHL":  {"sport": "hockey",     "league": "nhl",      "lineSportId": 4},
    "WNBA": {"sport": "basketball", "league": "wnba",     "lineSportId": 13},
    "NFL":  {"sport": "football",   "league": "nfl",      "lineSportId": 1},
}

ALWAYS_OVER = {"home runs", "pitcher wins", "wins", "saves", "first basket", "blowout"}

def get_headers(with_auth=True):
    h = {
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3.1 Safari/605.1.15",
        "Referer":         "https://engine.mybookie.ag/",
        "Origin":          "https://engine.mybookie.ag",
    }
    if with_auth:
        h["Cookie"]        = SESSION_COOKIE
        h["X-CSRF-TOKEN"]  = CSRF_TOKEN
        h["X-XSRF-TOKEN"]  = XSRF_TOKEN
    return h

def get_games(sport="NBA"):
    """Get today's game IDs from MyBookie leagues-lines endpoint."""
    cfg = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    try:
        r = requests.get(
            f"{ENGINE_BASE}/leagues-lines",
            params={"sport": cfg["sport"], "league": cfg["league"]},
            headers=get_headers(),
            timeout=10
        )
        print(f"  leagues-lines: {r.status_code}")
        if r.status_code != 200:
            return []

        data = r.json()
        today = date.today().isoformat()
        games = []

        # Parse games structure
        items = data if isinstance(data, list) else data.get("data", data.get("games", []))
        for item in items:
            gid  = item.get("gameID") or item.get("id") or item.get("gi")
            date_str = str(item.get("date","") or item.get("startDate","") or item.get("gameDate",""))
            name = item.get("name","") or item.get("description","") or item.get("teams","")
            if gid and today in date_str:
                games.append({"gameID": gid, "name": name, "sport": sport})

        print(f"  Found {len(games)} games today")
        return games

    except Exception as e:
        print(f"  leagues-lines error: {e}")
        return []

def get_game_lines(sport="NBA"):
    """Get game lines (ML/spread/total) — no auth needed via DST."""
    cfg   = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    lines = []
    try:
        # Get today's games from DST (no auth)
        r = requests.get(
            f"{DST_BASE}/games",
            params={"sb": "mybookie", "sport": cfg["sport"], "league": cfg["league"]},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Origin": "https://troya.xyz",
                "Referer": "https://troya.xyz/",
            },
            timeout=10
        )
        print(f"  DST games: {r.status_code}")
        if r.status_code == 200:
            print(f"  DST data: {r.text[:200]}")
    except Exception as e:
        print(f"  DST error: {e}")
    return lines

def get_props(game_id, sport="NBA"):
    """Get player props using props-market-list endpoint."""
    props = []
    try:
        r = requests.get(
            f"{ENGINE_BASE}/props-market-list",
            params={"gameID": game_id, "isLive": "false"},
            headers=get_headers(),
            timeout=10
        )
        print(f"    props-market-list ({game_id}): {r.status_code} | {len(r.text)} chars")

        if r.status_code != 200:
            return props

        data = r.json()
        print(f"    Preview: {str(data)[:200]}")

        # Parse props structure
        markets = data if isinstance(data, list) else data.get("data", data.get("markets", [data]))

        for market in markets:
            market_name = (market.get("name","") or
                          market.get("marketName","") or
                          market.get("description","")).strip()

            selections = (market.get("selections","") or
                         market.get("outcomes","") or
                         market.get("players","") or [])

            if isinstance(selections, dict):
                selections = list(selections.values())

            for sel in selections:
                player   = (sel.get("name","") or sel.get("player","") or
                           sel.get("description","")).strip()
                line     = sel.get("line") or sel.get("handicap") or sel.get("points")
                over_ml  = sel.get("overOdds") or sel.get("over") or sel.get("priceOver")
                under_ml = sel.get("underOdds") or sel.get("under") or sel.get("priceUnder")
                side     = str(sel.get("side","") or sel.get("type","OVER")).upper()

                if not player or line is None:
                    continue

                if market_name.lower() in ALWAYS_OVER and side == "UNDER":
                    continue

                props.append({
                    "Player":    player,
                    "Prop":      market_name,
                    "Line":      float(str(line).replace("+","")),
                    "Side":      side or "OVER",
                    "OverOdds":  str(over_ml) if over_ml else "—",
                    "UnderOdds": str(under_ml) if under_ml else "—",
                    "Book":      "MyBookie",
                    "Sport":     sport,
                    "source":    "mybookie_api",
                })

    except Exception as e:
        print(f"    Props error: {e}")

    return props

def get_search_props(sport="NBA"):
    """Alternative: search-props endpoint returns all props for a sport."""
    cfg = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props = []
    try:
        r = requests.get(
            f"{ENGINE_BASE}/search-props",
            params={"sport": cfg["sport"], "league": cfg["league"]},
            headers=get_headers(),
            timeout=15
        )
        print(f"  search-props: {r.status_code} | {len(r.text)} chars")
        if r.status_code == 200:
            print(f"  Preview: {r.text[:300]}")
            data = r.json()
            # Parse if it returns data
            items = data if isinstance(data, list) else data.get("data", [])
            for item in items:
                player   = item.get("playerName","") or item.get("name","")
                prop     = item.get("marketName","") or item.get("stat","")
                line     = item.get("line") or item.get("handicap")
                over_ml  = item.get("overOdds") or item.get("over")
                under_ml = item.get("underOdds") or item.get("under")
                if player and line:
                    props.append({
                        "Player":   player,
                        "Prop":     prop,
                        "Line":     float(str(line).replace("+","")),
                        "Side":     "OVER",
                        "OverOdds": str(over_ml) if over_ml else "—",
                        "Book":     "MyBookie",
                        "Sport":    sport,
                        "source":   "mybookie_search",
                    })
    except Exception as e:
        print(f"  search-props error: {e}")
    return props

def push_to_gist(props, sport):
    if not GITHUB_TOKEN or GITHUB_TOKEN == "YOUR_GITHUB_TOKEN_HERE":
        print("  ⚠️  Fill in GITHUB_TOKEN")
        return False
    payload = {
        "sport": sport, "date": date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "prop_count": len(props), "book": "MyBookie", "props": props,
    }
    r = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2)}}},
        timeout=10
    )
    if r.status_code == 200:
        print(f"  ✅ Pushed {len(props)} props")
        return True
    print(f"  ❌ Gist push failed: {r.status_code}")
    return False

def scrape(sport="NBA", no_push=False):
    print(f"\n{'='*50}")
    print(f"MyBookie {sport} | {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}")

    if SESSION_COOKIE == "PASTE_YOUR_COOKIE_HERE":
        print("❌ Fill in SESSION_COOKIE first")
        return []

    all_props = []

    # Try search-props first (all props in one call)
    print("\nTrying search-props (bulk)...")
    all_props = get_search_props(sport)

    if not all_props:
        # Fallback: get game IDs then props per game
        print("\nFalling back to per-game props...")
        games = get_games(sport)
        for game in games:
            gid = game["gameID"]
            print(f"\n  Game: {game.get('name', gid)}")
            props = get_props(gid, sport)
            print(f"  Props: {len(props)}")
            all_props.extend(props)
            time.sleep(0.5)

    print(f"\nTotal: {len(all_props)} props")
    for p in all_props[:5]:
        print(f"  {p['Player']:25} {p['Prop']:20} {p['Line']} {p['Side']}")

    if not no_push and all_props:
        push_to_gist(all_props, sport)

    return all_props

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",   default="NBA")
    parser.add_argument("--all",     action="store_true")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()
    sports = ["NBA","MLB","NHL","WNBA"] if args.all else [args.sport]
    for s in sports:
        scrape(s, no_push=args.no_push)
