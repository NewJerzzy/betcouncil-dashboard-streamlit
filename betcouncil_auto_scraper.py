#!/usr/bin/env python3
"""
BetCouncil Auto Scraper
=======================
Runs on your PC/Mac automatically.
Logs into MyBookie + PrizePicks, scrapes props, pushes to Gist.
Zero manual steps after setup.

SETUP (one time only):
1. Install Python: python.org/downloads
2. Install requirements:
   pip install requests curl_cffi

3. Create config file (same folder as this script):
   config.json
   {
     "github_token": "YOUR_GITHUB_TOKEN_HERE",
     "gist_id":      "YOUR_GIST_ID_HERE",
     "mybookie": {
       "username": "YOUR_MYBOOKIE_USERNAME",
       "password": "YOUR_MYBOOKIE_PASSWORD"
     },
     "prizepicks": {
       "enabled": true
     }
   }

4. Test it:
   python betcouncil_auto_scraper.py --sport NBA --no-push

5. Schedule it (runs every 3 hours automatically):
   WINDOWS:
     schtasks /create /tn "BetCouncil" /tr "python C:\\path\\to\\betcouncil_auto_scraper.py --all" /sc hourly /mo 3
   MAC:
     crontab -e
     Add: 0 */3 * * * python3 /path/to/betcouncil_auto_scraper.py --all

Usage:
  python betcouncil_auto_scraper.py --sport NBA
  python betcouncil_auto_scraper.py --sport MLB
  python betcouncil_auto_scraper.py --all
  python betcouncil_auto_scraper.py --all --no-push
"""

import requests
import json
import time
import argparse
import os
import sys
from datetime import datetime, date
from pathlib import Path

# ── Load config ──────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
COOKIE_FILE = SCRIPT_DIR / ".mybookie_session.json"  # auto-saved, don't edit

def load_config():
    if not CONFIG_FILE.exists():
        print("❌ config.json not found. Create it first — see instructions at top of script.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_cookies(cookies):
    with open(COOKIE_FILE, 'w') as f:
        json.dump({"cookies": cookies, "saved_at": datetime.now().isoformat()}, f)

def load_cookies():
    if not COOKIE_FILE.exists():
        return None
    with open(COOKIE_FILE) as f:
        data = json.load(f)
    # Check if cookie is still fresh (under 20 hours)
    from datetime import datetime
    saved_at = datetime.fromisoformat(data["saved_at"])
    age_hours = (datetime.now() - saved_at).total_seconds() / 3600
    if age_hours > 20:
        print("  Session expired — will re-login")
        return None
    return data["cookies"]

# ── Sport config ─────────────────────────────────────────────
SPORT_MAP = {
    "NBA":  {"sport": "basketball", "league": "nba",  "pp_league": "NBA"},
    "MLB":  {"sport": "baseball",   "league": "mlb",  "pp_league": "MLB"},
    "NHL":  {"sport": "hockey",     "league": "nhl",  "pp_league": "NHL"},
    "WNBA": {"sport": "basketball", "league": "wnba", "pp_league": "WNBA"},
    "NFL":  {"sport": "football",   "league": "nfl",  "pp_league": "NFL"},
}

ALWAYS_OVER = {"home runs", "pitcher wins", "wins", "saves", "first basket", "blowout"}

BROWSER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# ── MyBookie Auto Login ───────────────────────────────────────
def mybookie_login(username, password):
    """
    Logs into MyBookie automatically.
    Returns session cookies dict or None on failure.
    """
    print("\n  Logging into MyBookie...")
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    try:
        # Step 1: Load mybookie.ag to get initial cookies (cf_bm, websession etc)
        r = session.get("https://mybookie.ag/login", timeout=15)
        print(f"  Login page: {r.status_code}")

        # Step 1b: Load engine.mybookie.ag to get XSRF token
        r_eng = session.get("https://engine.mybookie.ag/login", timeout=15,
                            headers={**BROWSER_HEADERS,
                                     "Referer": "https://mybookie.ag/",
                                     "Origin":  "https://mybookie.ag"})
        print(f"  Engine login page: {r_eng.status_code}")

        from urllib.parse import unquote
        csrf_token = session.cookies.get("XSRF-TOKEN", "")
        if csrf_token:
            csrf_token = unquote(csrf_token)
            try:
                import base64 as _b64, json as _json
                parts = csrf_token.split('.')
                if len(parts) == 3:
                    padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    decoded = _json.loads(_b64.b64decode(padded))
                    csrf_value = decoded.get("value", csrf_token)
                else:
                    csrf_value = csrf_token
            except:
                csrf_value = csrf_token
        else:
            csrf_value = csrf_token = ""

        # Step 2: POST login credentials
        login_headers = {
            **BROWSER_HEADERS,
            "Content-Type":  "application/json",
            "Origin":        "https://mybookie.ag",
            "Referer":       "https://mybookie.ag/login",
            "X-CSRF-TOKEN":  csrf_value,
            "X-XSRF-TOKEN":  csrf_token,
        }
        login_data = {
            "username": username,
            "password": password,
            "remember": True,
        }
        # Confirmed login endpoint from DevTools: engine.mybookie.ag/login
        # Try form POST first (matches the HTML form action), then JSON
        login_attempts = [
            ("form", "https://engine.mybookie.ag/login",
             {"Content-Type":"application/x-www-form-urlencoded",
              "Origin":"https://mybookie.ag",
              "Referer":"https://mybookie.ag/login"}),
            ("json", "https://engine.mybookie.ag/login",
             {"Content-Type":"application/json",
              "Origin":"https://mybookie.ag",
              "Referer":"https://mybookie.ag/login"}),
            ("json", "https://engine.mybookie.ag/api/auth/login",
             {"Content-Type":"application/json",
              "Origin":"https://engine.mybookie.ag",
              "Referer":"https://engine.mybookie.ag/login"}),
            ("json", "https://engine.mybookie.ag/user/login",
             {"Content-Type":"application/json",
              "Origin":"https://engine.mybookie.ag",
              "Referer":"https://engine.mybookie.ag/login"}),
        ]
        for fmt, ep, extra_h in login_attempts:
            try:
                h = {**login_headers, **extra_h,
                     "X-CSRF-TOKEN": csrf_value,
                     "X-XSRF-TOKEN": csrf_token}
                if fmt == "form":
                    payload = {"username": username, "password": password,
                               "remember": "on", "_token": csrf_value}
                    r2 = session.post(ep, data=payload, headers=h,
                                      timeout=15, allow_redirects=True)
                else:
                    r2 = session.post(ep, json=login_data, headers=h,
                                      timeout=15, allow_redirects=True)
                print(f"  Login {ep[-40:]}: {r2.status_code}")
                if r2.status_code in (200, 201, 302):
                    cookies = dict(session.cookies)
                    if any(k in cookies for k in
                           ["gamingstation_session","XSRF-TOKEN","cf_clearance",
                            "auth","session","cust_s_a"]):
                        save_cookies(cookies)
                        print(f"  ✅ Login successful via {ep}")
                        return cookies
                    else:
                        print(f"  Cookies: {list(cookies.keys())}")
            except Exception as _le:
                print(f"  {ep[-40:]}: {_le}")
        print(f"  ❌ All login endpoints failed")
        return None

    except Exception as e:
        print(f"  ❌ Login error: {e}")
        return None

def get_mybookie_session(cfg):
    """Get valid session — use cached or re-login."""
    # Try cached cookies first
    cached = load_cookies()
    if cached:
        print("  Using cached session")
        return cached

    # Re-login
    mb_cfg = cfg.get("mybookie", {})
    username = mb_cfg.get("username","")
    password = mb_cfg.get("password","")

    if not username or not password:
        print("  ❌ MyBookie username/password not in config.json")
        return None

    return mybookie_login(username, password)

# ── MyBookie Scraper ──────────────────────────────────────────
def scrape_mybookie(sport, cookies):
    """Scrape props from MyBookie using session cookies."""
    cfg_s  = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props  = []
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

    headers = {
        **BROWSER_HEADERS,
        "Cookie":   cookie_str,
        "Referer":  "https://engine.mybookie.ag/",
        "Origin":   "https://engine.mybookie.ag",
    }

    print(f"\n  MyBookie {sport}:")

    # Step 1: Get today's games
    try:
        r = requests.get(
            f"https://engine.mybookie.ag/sports_api/leagues-lines",
            params={"sport": cfg_s["sport"], "league": cfg_s["league"]},
            headers=headers,
            timeout=15
        )
        print(f"    leagues-lines: {r.status_code}")

        if r.status_code == 401:
            print("    Session expired — clearing cache")
            COOKIE_FILE.unlink(missing_ok=True)
            return props, True  # Signal re-login needed

        if r.status_code != 200:
            return props, False

        today  = date.today().isoformat()
        data   = r.json()
        items  = data if isinstance(data, list) else data.get("data", data.get("games", []))
        games  = []
        for item in items:
            gid = item.get("gameID") or item.get("id") or item.get("gi")
            d   = str(item.get("date","") or item.get("startDate","") or "")
            if gid and today in d:
                games.append(gid)

        print(f"    Games today: {len(games)}")

        # Step 2: Get props per game
        for gid in games[:10]:
            rp = requests.get(
                f"https://engine.mybookie.ag/sports_api/props-market-list",
                params={"gameID": gid, "isLive": "false"},
                headers=headers,
                timeout=15
            )
            if rp.status_code == 200:
                game_props = parse_mybookie_props(rp.json(), sport)
                props.extend(game_props)
                print(f"    Game {gid}: {len(game_props)} props")
            time.sleep(0.5)

    except Exception as e:
        print(f"    Error: {e}")

    return props, False

def parse_mybookie_props(data, sport):
    props  = []
    items  = data if isinstance(data, list) else data.get("data", data.get("markets", [data]))
    for market in items:
        mname = (market.get("name","") or market.get("marketName","") or "").strip()
        sels  = market.get("selections","") or market.get("outcomes","") or market.get("players","") or []
        if isinstance(sels, dict):
            sels = list(sels.values())
        for sel in sels:
            player = (sel.get("name","") or sel.get("player","") or sel.get("playerName","")).strip()
            line   = sel.get("line") or sel.get("handicap") or sel.get("points")
            over   = sel.get("overOdds") or sel.get("over") or sel.get("priceOver")
            under  = sel.get("underOdds") or sel.get("under") or sel.get("priceUnder")
            side   = str(sel.get("side","") or sel.get("type","OVER")).upper()
            if not player or line is None:
                continue
            if mname.lower() in ALWAYS_OVER and side == "UNDER":
                continue
            props.append({
                "Player":    player,
                "Prop":      mname,
                "Line":      float(str(line).replace("+","")),
                "Side":      side or "OVER",
                "OverOdds":  str(over) if over else "—",
                "UnderOdds": str(under) if under else "—",
                "Book":      "MyBookie",
                "Sport":     sport,
                "source":    "mybookie_auto",
            })
    return props

# ── PrizePicks Scraper ────────────────────────────────────────
def scrape_prizepicks(sport):
    """
    Scrape PrizePicks directly — no login needed.
    Uses curl_cffi for Cloudflare bypass.
    Falls back to requests if curl_cffi not installed.
    """
    print(f"\n  PrizePicks {sport}:")
    cfg_s  = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props  = []

    try:
        from curl_cffi import requests as cf_requests
        session = cf_requests.Session(impersonate="chrome124")
        print("  Using curl_cffi (Cloudflare bypass)")
    except ImportError:
        import requests as session
        print("  Using requests (install curl_cffi for better success rate)")

    try:
        url = "https://partner-api.prizepicks.com/projections"
        params = {
            "league_id":     get_pp_league_id(cfg_s["pp_league"]),
            "per_page":      250,
            "single_stat":   "true",
            "game_mode":     "pickem",
        }
        headers = {
            **BROWSER_HEADERS,
            "Referer": "https://app.prizepicks.com/",
            "Origin":  "https://app.prizepicks.com",
        }
        r = session.get(url, params=params, headers=headers, timeout=20)
        print(f"    Status: {r.status_code}")

        if r.status_code == 200:
            data       = r.json()
            included   = {item["id"]: item for item in data.get("included", []) if item.get("type") == "new_player"}
            projections= data.get("data", [])

            for proj in projections:
                attrs    = proj.get("attributes", {})
                rels     = proj.get("relationships", {})
                player_rel = rels.get("new_player", {}).get("data", {})
                player_data= included.get(player_rel.get("id",""), {})
                player_name= player_data.get("attributes", {}).get("name","") or attrs.get("description","")
                stat_type  = attrs.get("stat_type","")
                line       = attrs.get("line_score")
                if not player_name or line is None:
                    continue
                props.append({
                    "Player":    player_name,
                    "Prop":      stat_type,
                    "Line":      float(line),
                    "Side":      "OVER",
                    "OverOdds":  "—",
                    "UnderOdds": "—",
                    "Book":      "PrizePicks",
                    "Sport":     sport,
                    "source":    "prizepicks_auto",
                })
            print(f"    Props: {len(props)}")
        else:
            print(f"    Failed: {r.text[:80]}")

    except Exception as e:
        print(f"    Error: {e}")

    return props

def get_pp_league_id(league):
    league_ids = {
        "NBA": 7, "MLB": 2, "NHL": 12, "NFL": 1,
        "WNBA": 28, "Soccer": 14, "UFC": 9,
    }
    return league_ids.get(league, 7)

# ── BetOnline Scraper ─────────────────────────────────────────
def scrape_betonline(sport):
    """Scrape BetOnline — no login needed."""
    cfg_s = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props = []
    print(f"\n  BetOnline {sport}:")

    headers = {
        **BROWSER_HEADERS,
        "Content-Type": "application/json-patch+json",
        "gsetting":     "bolnasite",
        "Origin":       "https://www.betonline.ag",
        "Referer":      "https://www.betonline.ag/",
    }
    menu_headers = {**headers, "Content-Type": "application/json", "gsetting": "bolsassite"}

    try:
        # Get today's games
        r = requests.post(
            "https://api-offering.betonline.ag/api/offering/Sports/get-menu",
            headers=menu_headers, json={}, timeout=10
        )
        print(f"    Menu: {r.status_code}")

        if r.status_code == 200:
            today  = date.today().isoformat()
            data   = r.json()
            game_ids = extract_bo_games(data, cfg_s, today)
            print(f"    Games today: {len(game_ids)}")

            for gid in game_ids[:8]:
                rp = requests.post(
                    "https://api-offering.betonline.ag/api/offering/sports/get-linked-events",
                    headers=headers,
                    json={"sport": cfg_s["sport"], "league": cfg_s["league"],
                          "gameID": gid, "scheduleText": None},
                    timeout=10
                )
                if rp.status_code == 200:
                    game_props = parse_bo_props(rp.json(), sport)
                    props.extend(game_props)
                    print(f"    Game {gid}: {len(game_props)} props")
                time.sleep(0.4)

    except Exception as e:
        print(f"    Error: {e}")

    return props

def extract_bo_games(data, cfg, today):
    ids = []
    items = data if isinstance(data, list) else []
    if not items:
        for v in (data.values() if isinstance(data, dict) else []):
            if isinstance(v, list):
                items.extend(v)
    for item in items:
        gid = item.get("gameID") or item.get("id") or item.get("eventId")
        d   = str(item.get("startDate","") or item.get("date","") or "")
        if gid and today in d:
            ids.append(gid)
    return ids

def parse_bo_props(data, sport):
    props  = []
    events = data if isinstance(data, list) else data.get("events", [data])
    for event in events:
        for key in ["markets","props","playerProps","offerings"]:
            markets = event.get(key, [])
            if markets:
                break
        for market in (markets if isinstance(markets, list) else []):
            mname = (market.get("name","") or market.get("description","")).strip()
            parts = market.get("participants","") or market.get("outcomes","") or []
            if isinstance(parts, dict):
                parts = list(parts.values())
            for part in parts:
                player = (part.get("name","") or part.get("player","")).strip()
                line   = part.get("line") or part.get("handicap") or part.get("points")
                over   = part.get("overOdds") or part.get("over")
                under  = part.get("underOdds") or part.get("under")
                side   = str(part.get("side","OVER")).upper()
                if not player or line is None:
                    continue
                if mname.lower() in ALWAYS_OVER and side == "UNDER":
                    continue
                props.append({
                    "Player":    player,
                    "Prop":      mname,
                    "Line":      float(str(line).replace("+","")),
                    "Side":      side or "OVER",
                    "OverOdds":  str(over) if over else "—",
                    "UnderOdds": str(under) if under else "—",
                    "Book":      "BetOnline",
                    "Sport":     sport,
                    "source":    "betonline_auto",
                })
    return props

# ── Gist Push ─────────────────────────────────────────────────
def push_to_gist(all_props, token, gist_id, sport):
    if not token or not gist_id:
        print("❌ No GitHub token/Gist ID configured")
        return False

    books   = list({p["Book"] for p in all_props})
    payload = {
        "sport":      sport,
        "date":       date.today().isoformat(),
        "timestamp":  datetime.now().isoformat(),
        "prop_count": len(all_props),
        "books":      books,
        "props":      all_props,
    }

    r = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {"auto_scraped_props.json": {"content": json.dumps(payload, indent=2)}}},
        timeout=15
    )
    if r.status_code == 200:
        print(f"\n✅ Pushed {len(all_props)} props to Gist")
        print(f"   Books: {', '.join(books)}")
        return True
    else:
        print(f"\n❌ Gist push failed: {r.status_code}")
        return False

# ── Main ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="BetCouncil Auto Scraper")
    parser.add_argument("--sport",    default="NBA", choices=["NBA","MLB","NHL","WNBA","NFL"])
    parser.add_argument("--all",      action="store_true", help="All sports")
    parser.add_argument("--no-push",  action="store_true", help="Test — don't push to Gist")
    parser.add_argument("--mybookie", action="store_true", help="MyBookie only")
    parser.add_argument("--prizepicks",action="store_true",help="PrizePicks only")
    parser.add_argument("--betonline",action="store_true", help="BetOnline only")
    args = parser.parse_args()

    cfg    = load_config()
    token  = cfg.get("github_token","")
    gist   = cfg.get("gist_id","")
    sports = ["NBA","MLB","NHL","WNBA"] if args.all else [args.sport]

    # Determine which sources to use
    use_mb = args.mybookie or (not args.prizepicks and not args.betonline)
    use_pp = args.prizepicks or (not args.mybookie and not args.betonline)
    use_bo = args.betonline or (not args.mybookie and not args.prizepicks)

    # Get MyBookie session once (reused across sports)
    mb_cookies = None
    if use_mb and cfg.get("mybookie",{}).get("username"):
        mb_cookies = get_mybookie_session(cfg)
        if not mb_cookies:
            print("⚠️  MyBookie login failed — skipping MyBookie")

    for sport in sports:
        print(f"\n{'='*50}")
        print(f"BetCouncil Auto Scraper | {sport} | {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*50}")

        all_props = []

        # PrizePicks
        if use_pp and cfg.get("prizepicks",{}).get("enabled", True):
            pp_props = scrape_prizepicks(sport)
            all_props.extend(pp_props)
            print(f"  PrizePicks: {len(pp_props)} props")

        # BetOnline
        if use_bo:
            bo_props = scrape_betonline(sport)
            all_props.extend(bo_props)
            print(f"  BetOnline: {len(bo_props)} props")

        # MyBookie
        if use_mb and mb_cookies:
            mb_props, needs_relogin = scrape_mybookie(sport, mb_cookies)
            if needs_relogin:
                # Re-login and retry
                print("  Re-logging in...")
                mb_cookies = mybookie_login(
                    cfg["mybookie"]["username"],
                    cfg["mybookie"]["password"]
                )
                if mb_cookies:
                    mb_props, _ = scrape_mybookie(sport, mb_cookies)
            all_props.extend(mb_props)
            print(f"  MyBookie: {len(mb_props)} props")

        print(f"\nTotal: {len(all_props)} props")

        # Show sample
        for p in all_props[:5]:
            print(f"  {p['Book']:12} {p['Player']:25} {p['Prop']:20} {p['Line']}")

        # Push to Gist
        if not args.no_push and all_props:
            push_to_gist(all_props, token, gist, sport)
        elif args.no_push:
            print("\nTest mode — not pushing")

        if len(sports) > 1:
            time.sleep(2)

    print("\n✅ Done")

if __name__ == "__main__":
    main()
