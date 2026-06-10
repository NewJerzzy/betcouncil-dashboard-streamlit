#!/usr/bin/env python3
"""
BetCouncil Auto Scraper v2.0
=============================
Full multi-book scraper using Playwright browser automation.
Handles Cloudflare automatically on all regulated US books.

BOOKS COVERED:
  DFS:        PrizePicks, Underdog, Sleeper
  US Sharp:   DraftKings, FanDuel, BetMGM, Caesars
  Offshore:   Bovada, MyBookie, BetOnline (no login needed)

SETUP (one time):
  pip install requests curl_cffi playwright
  playwright install chromium

CREATE config.json (same folder as this script):
{
  "github_token": "YOUR_GITHUB_TOKEN",
  "gist_id":      "YOUR_GIST_ID",
  "prizepicks":   {"enabled": true},
  "underdog":     {"enabled": true},
  "sleeper":      {"enabled": true},
  "betonline":    {"enabled": true},
  "bovada":       {"enabled": true},
  "parlayplay":   {"session_cookie": "YOUR_PARLAYPLAY_SESSIONID"},
  "draftkings":   {"username": "YOUR_DK_EMAIL",    "password": "YOUR_DK_PASSWORD"},
  "dk_pick6":     {"enabled": true},  # uses same DK credentials as above
  "fanduel":      {"username": "YOUR_FD_EMAIL",    "password": "YOUR_FD_PASSWORD"},
  "betmgm":       {"username": "YOUR_MGM_EMAIL",   "password": "YOUR_MGM_PASSWORD"},
  "caesars":      {"username": "YOUR_CZR_EMAIL",   "password": "YOUR_CZR_PASSWORD"},
  "mybookie":     {"username": "YOUR_MB_USERNAME", "password": "YOUR_MB_PASSWORD"}
}

USAGE:
  python betcouncil_auto_scraper.py --all
  python betcouncil_auto_scraper.py --sport NBA
  python betcouncil_auto_scraper.py --all --no-push
  python betcouncil_auto_scraper.py --books dk,fd,mgm
"""

import requests
import json
import time
import argparse
import os
import sys
from datetime import datetime, date
from pathlib import Path

# ── Config ───────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
SESSION_DIR = SCRIPT_DIR / ".sessions"
SESSION_DIR.mkdir(exist_ok=True)

def load_config():
    if not CONFIG_FILE.exists():
        print("❌ config.json not found.")
        print("   Create it with your credentials — see instructions at top of script.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_session(book, cookies):
    path = SESSION_DIR / f"{book}_session.json"
    with open(path, 'w') as f:
        json.dump({"cookies": cookies, "saved_at": datetime.now().isoformat()}, f)

def load_session(book, max_hours=20):
    path = SESSION_DIR / f"{book}_session.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    age = (datetime.now() - datetime.fromisoformat(data["saved_at"])).total_seconds() / 3600
    if age > max_hours:
        return None
    return data["cookies"]

# ── Constants ─────────────────────────────────────────────────
SPORT_MAP = {
    "NBA":  {"sport": "basketball", "league": "nba",  "pp_id": 7,  "ud_sport": "NBA"},
    "MLB":  {"sport": "baseball",   "league": "mlb",  "pp_id": 2,  "ud_sport": "MLB"},
    "NHL":  {"sport": "hockey",     "league": "nhl",  "pp_id": 12, "ud_sport": "NHL"},
    "WNBA": {"sport": "basketball", "league": "wnba", "pp_id": 28, "ud_sport": "WNBA"},
    "NFL":  {"sport": "football",   "league": "nfl",  "pp_id": 1,  "ud_sport": "NFL"},
}

ALWAYS_OVER = {"home runs","pitcher wins","wins","saves","first basket","blowout"}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ── Playwright Login Helper ───────────────────────────────────
def playwright_login(book, login_url, username, password,
                     user_selector, pass_selector, submit_selector,
                     success_url_pattern, extra_steps=None):
    """
    Generic Playwright login for any book.
    Returns cookies dict or None.
    """
    # Check cached session first
    cached = load_session(book)
    if cached:
        print(f"  Using cached {book} session")
        return cached

    print(f"\n  Logging into {book} (browser)...")
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            # Mask automation
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            """)
            page = ctx.new_page()

            print(f"  Loading {login_url}...")
            page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # Wait for form to appear then fill
            try:
                page.wait_for_selector(user_selector, timeout=15000)
            except:
                # Try clicking login button first if form not visible
                for btn in ["button:has-text('Log in')", "button:has-text('Sign in')",
                            "a:has-text('Log in')", "[data-testid='login']"]:
                    try:
                        page.click(btn, timeout=3000)
                        time.sleep(1)
                        break
                    except:
                        continue
            page.fill(user_selector, username)
            time.sleep(0.5)
            page.fill(pass_selector, password)
            time.sleep(0.5)

            # Extra steps before submit (e.g. close popups)
            if extra_steps:
                extra_steps(page)

            # Submit
            page.click(submit_selector)
            print(f"  Submitted login...")

            # Wait for page to settle after login
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                time.sleep(2)
                print(f"  Post-login URL: {page.url}")
                if success_url_pattern in page.url or "login" not in page.url:
                    print(f"  ✅ Login successful")
                else:
                    print(f"  ⚠️  May not be logged in — URL: {page.url}")
            except Exception as _we:
                print(f"  URL after submit: {page.url}")

            time.sleep(2)
            cookies = {c["name"]: c["value"] for c in ctx.cookies()}
            browser.close()

            if cookies:
                save_session(book, cookies)
                print(f"  Session saved ({len(cookies)} cookies)")
                return cookies
            return None

    except ImportError:
        print("  ❌ Playwright not installed.")
        print("  Run: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        print(f"  ❌ {book} login error: {e}")
        return None

# ── Book-specific login functions ─────────────────────────────
def login_draftkings(cfg):
    return playwright_login(
        book="draftkings",
        login_url="https://myaccount.draftkings.com/auth/login?intendedSiteExp=US-SB",
        username=cfg["username"],
        password=cfg["password"],
        user_selector="#login-username-input",
        pass_selector="#login-password-input",
        submit_selector='button[type="submit"]',
        success_url_pattern="draftkings.com",
    )

def login_fanduel(cfg):
    # FanDuel requires state selection before login
    cached = load_session("fanduel")
    if cached:
        print("  Using cached fanduel session")
        return cached
    print("\n  Logging into fanduel (browser)...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":800})
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()

            import time as _t
            # Go directly to Arizona FanDuel (bypass state selector)
            page.goto("https://az.sportsbook.fanduel.com/", wait_until="domcontentloaded", timeout=45000)
            _t.sleep(3)
            print(f"  FD URL: {page.url}")

            # Step 3: Click Login
            try:
                page.click("button:has-text('Log In'), a:has-text('Log In')", timeout=5000)
                _t.sleep(2)
            except:
                pass

            # Step 4: Fill credentials
            try:
                page.wait_for_selector('input[type="email"], input[name="email"]', timeout=10000)
                page.fill('input[type="email"], input[name="email"]', cfg["username"])
                _t.sleep(0.5)
                page.fill('input[type="password"]', cfg["password"])
                _t.sleep(0.5)
                page.click('button[type="submit"]')
                _t.sleep(3)
                print(f"  Post-login URL: {page.url}")
            except Exception as e:
                print(f"  Login form error: {e}")

            cookies = {c["name"]:c["value"] for c in ctx.cookies()}
            browser.close()
            if cookies:
                save_session("fanduel", cookies)
                print(f"  ✅ FanDuel session saved")
                return cookies
    except Exception as e:
        print(f"  ❌ fanduel login error: {e}")
    return None

def login_betmgm(cfg):
    cached = load_session("betmgm")
    if cached:
        print("  Using cached betmgm session")
        return cached
    print("\n  Logging into betmgm (browser)...")
    try:
        from playwright.sync_api import sync_playwright
        import time as _t
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":800})
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()

            # Use Arizona state URL
            page.goto("https://www.az.betmgm.com/en/sports", wait_until="domcontentloaded", timeout=45000)
            _t.sleep(3)

            # Click login
            for sel in ["button:has-text('Log In')", "a:has-text('Log In')", "[data-test='login-btn']"]:
                try:
                    page.click(sel, timeout=3000)
                    _t.sleep(2)
                    break
                except:
                    continue

            # Fill credentials
            try:
                page.wait_for_selector('input[type="email"], input[name="username"], input[name="email"]', timeout=10000)
                page.fill('input[type="email"], input[name="username"], input[name="email"]', cfg["username"])
                _t.sleep(0.5)
                page.fill('input[type="password"]', cfg["password"])
                _t.sleep(0.5)
                page.click('button[type="submit"], ms-primary-button')
                _t.sleep(3)
                print(f"  Post-login URL: {page.url}")
            except Exception as e:
                print(f"  Form error: {e}")

            cookies = {c["name"]:c["value"] for c in ctx.cookies()}
            browser.close()
            if cookies:
                save_session("betmgm", cookies)
                print(f"  ✅ BetMGM session saved")
                return cookies
    except Exception as e:
        print(f"  ❌ betmgm login error: {e}")
    return None

def login_caesars(cfg):
    cached = load_session("caesars")
    if cached:
        print("  Using cached caesars session")
        return cached
    print("\n  Logging into caesars (browser)...")
    try:
        from playwright.sync_api import sync_playwright
        import time as _t
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":800})
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()

            page.goto("https://sportsbook.caesars.com/us/az/bet#login", wait_until="domcontentloaded", timeout=45000)
            _t.sleep(3)

            # Click LOG IN button to open modal
            try:
                page.click("button:has-text('LOG IN')", timeout=5000)
                _t.sleep(2)
            except:
                pass

            # Fill credentials in modal
            try:
                page.wait_for_selector('input[type="email"], input[name="username"], input[placeholder*="email" i]', timeout=10000)
                page.fill('input[type="email"], input[name="username"], input[placeholder*="email" i]', cfg["username"])
                _t.sleep(0.5)
                page.fill('input[type="password"]', cfg["password"])
                _t.sleep(0.5)
                page.click('button[type="submit"], button:has-text("LOG IN"), button:has-text("Sign In")')
                _t.sleep(3)
                print(f"  Post-login URL: {page.url}")
            except Exception as e:
                print(f"  Form error: {e}")

            cookies = {c["name"]:c["value"] for c in ctx.cookies()}
            browser.close()
            if cookies:
                save_session("caesars", cookies)
                print(f"  ✅ Caesars session saved")
                return cookies
    except Exception as e:
        print(f"  ❌ caesars login error: {e}")
    return None

def login_mybookie(cfg):
    cached = load_session("mybookie")
    if cached:
        print("  Using cached mybookie session")
        return cached
    print("\n  Logging into mybookie (browser)...")
    try:
        from playwright.sync_api import sync_playwright
        import time as _t
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":800})
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()
            page.goto("https://mybookie.ag/login", wait_until="domcontentloaded", timeout=45000)
            _t.sleep(3)
            # Use confirmed selectors from diagnostic
            # Clear fields first then fill
            page.click("#user")
            page.fill("#user", "")
            page.type("#user", cfg["username"], delay=50)
            _t.sleep(0.5)
            page.click("#pass")
            page.fill("#pass", "")
            page.type("#pass", cfg["password"], delay=50)
            _t.sleep(0.5)
            # Click the Login submit button
            page.click('button[type="submit"]:has-text("Login")')
            _t.sleep(3)
            # Handle "confirm I'm human" popup
            _t.sleep(2)
            human_selectors = [
                'button:has-text("Human")',
                'button:has-text("Human")',
                'button:has-text("Confirm")',
                'button:has-text("Continue")',
                'button:has-text("Verify")',
                'button:has-text("I Agree")',
                'button:has-text("OK")',
                'input[type="submit"]',
                '[class*="human"]',
                '[class*="verify"]',
                '[class*="confirm"]',
                '[id*="human"]',
                '[id*="verify"]',
            ]
            for sel in human_selectors:
                try:
                    if page.is_visible(sel, timeout=1500):
                        page.click(sel)
                        print(f"  ✅ Clicked human verification: {sel}")
                        _t.sleep(2)
                        break
                except:
                    continue

            # If still on login page try clicking any visible button
            if "login" in page.url.lower():
                try:
                    # Find all buttons and click first non-nav one
                    btns = page.query_selector_all("button:visible")
                    for btn in btns:
                        txt = (btn.inner_text() or "").strip().lower()
                        if any(w in txt for w in ["human","confirm","verify","continue","ok","agree"]):
                            btn.click()
                            print(f"  ✅ Clicked: {txt}")
                            _t.sleep(2)
                            break
                except:
                    pass
            _t.sleep(3)
            print(f"  Post-login URL: {page.url}")
            cookies = {c["name"]:c["value"] for c in ctx.cookies()}
            browser.close()
            # Check if login succeeded — URL should change away from /login
            if "login" not in page.url or any(k in cookies for k in ["cust_s_a","gamingstation_session"]):
                save_session("mybookie", cookies)
                print(f"  ✅ MyBookie login successful")
                return cookies
            else:
                print(f"  ❌ MyBookie login failed — still on login page")
                return None
    except Exception as e:
        print(f"  ❌ mybookie login error: {e}")
        return None

def login_underdog(cfg):
    return playwright_login(
        book="underdog",
        login_url="https://underdogfantasy.com/login",
        username=cfg.get("username",""),
        password=cfg.get("password",""),
        user_selector='input[type="email"], input[name="email"]',
        pass_selector='input[type="password"]',
        submit_selector='button[type="submit"], button:has-text("Log In")',
        success_url_pattern="underdogfantasy.com",
    )

# ── Prop Scrapers ─────────────────────────────────────────────
def scrape_prizepicks(sport):
    """PrizePicks — no login, curl_cffi bypass."""
    print(f"\n  PrizePicks {sport}:")
    cfg_s = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props = []
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        session = requests
    try:
        r = session.get(
            "https://partner-api.prizepicks.com/projections",
            params={"league_id": cfg_s["pp_id"], "per_page": 250,
                    "single_stat": "true", "game_mode": "pickem"},
            headers={"User-Agent": UA, "Referer": "https://app.prizepicks.com/",
                     "Origin": "https://app.prizepicks.com"},
            timeout=20
        )
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data     = r.json()
            included = {i["id"]: i for i in data.get("included",[]) if i.get("type")=="new_player"}
            for proj in data.get("data",[]):
                attrs  = proj.get("attributes",{})
                pid    = proj.get("relationships",{}).get("new_player",{}).get("data",{}).get("id","")
                pname  = included.get(pid,{}).get("attributes",{}).get("name","") or attrs.get("description","")
                stat   = attrs.get("stat_type","")
                line   = attrs.get("line_score")
                if pname and line is not None:
                    props.append({"Player":pname,"Prop":stat,"Line":float(line),
                                  "Side":"OVER","OverOdds":"—","UnderOdds":"—",
                                  "Book":"PrizePicks","Sport":sport,"source":"prizepicks_auto"})
            print(f"    Props: {len(props)}")
    except Exception as e:
        print(f"    Error: {e}")
    return props

def scrape_underdog(sport):
    """Underdog — direct API, no login needed."""
    print(f"\n  Underdog {sport}:")
    cfg_s = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props = []
    try:
        r = requests.get(
            "https://api.underdogfantasy.com/v1/over_under_lines",
            headers={"User-Agent": UA, "Referer": "https://underdogfantasy.com/"},
            timeout=15
        )
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data    = r.json()
            # Build player lookup
            players = {}
            for p in data.get("players", data.get("included", [])):
                if isinstance(p, dict):
                    pid = p.get("id","")
                    fn  = p.get("first_name","") or p.get("attributes",{}).get("first_name","")
                    ln  = p.get("last_name","")  or p.get("attributes",{}).get("last_name","")
                    players[pid] = f"{fn} {ln}".strip()

            # Confirmed structure: over_under_lines + players
            lines   = data.get("over_under_lines", [])
            players = {}
            for p in data.get("players", []):
                pid  = p.get("id","")
                name = (p.get("display_name","") or
                        f"{p.get('first_name','')} {p.get('last_name','')}".strip())
                if pid:
                    players[pid] = name

            for line in lines:
                # over_under_lines structure:
                # {id, stat_value, stat_line, appearance_id}
                # appearance links to appearances array
                stat  = line.get("stat_value","")
                val   = line.get("stat_line") or line.get("over_under","")
                # Underdog confirmed structure from debug:
                # line keys: id, line_type, live_event, live_event_stat
                # live_event_stat = dict OR None
                # appearance_id = empty string (not used)
                live_stat  = line.get("live_event_stat") or {}
                live_event = line.get("live_event") or {}
                stat       = line.get("stat_value","") or line.get("stat","")
                val        = line.get("stat_line") or line.get("over_under")

                # Get player name from live_event_stat
                pname = ""
                if isinstance(live_stat, dict):
                    pname = (live_stat.get("player_name","") or
                             live_stat.get("display_name","") or
                             live_stat.get("name","") or
                             live_stat.get("full_name",""))
                    if not stat:
                        stat = (live_stat.get("type","") or
                                live_stat.get("stat_type","") or
                                live_stat.get("category",""))

                # Fallback to live_event for player
                if not pname and isinstance(live_event, dict):
                    pname = (live_event.get("player_name","") or
                             live_event.get("name","") or
                             live_event.get("title",""))

                # Sport filter
                if isinstance(live_event, dict):
                    sport_key = (live_event.get("sport_id","") or
                                 live_event.get("sport","") or
                                 live_event.get("league","") or "").upper()
                    if sport and sport_key and sport[:3] not in sport_key and sport_key not in sport:
                        continue

                if pname and val is not None:
                    props.append({
                        "Player": pname, "Prop": stat,
                        "Line": float(str(val).replace("+","")),
                        "Side": "OVER", "OverOdds": "—", "UnderOdds": "—",
                        "Book": "Underdog", "Sport": sport,
                        "source": "underdog_auto"
                    })
            print(f"    Props: {len(props)}")
            if not props and lines:
                # Show first line structure for debugging
                sample = lines[0] if lines else {}
                print(f"    Lines: {len(lines)} | Sample keys: {list(sample.keys())[:8]}")
                # Show first appearance
                apps = data.get("appearances",[])
                if apps:
                    print(f"    Appearances: {len(apps)} | Sample: {list(apps[0].keys())[:6]}")
                # Show first player
                if players:
                    pid = list(players.keys())[0]
                    print(f"    Players: {len(players)} | Sample ID type: {type(pid).__name__} val: {pid}")
                    if sample:
                        print(f"    Line appearance_id type: {type(sample.get('appearance_id','')).__name__} val: {sample.get('appearance_id','')}")
    except Exception as e:
        print(f"    Error: {e}")
    return props

def scrape_sleeper(sport):
    """Sleeper — direct API, no login needed."""
    print(f"\n  Sleeper {sport}:")
    props = []
    sport_map = {"NBA":"nba","MLB":"mlb","NFL":"nfl","NHL":"nhl","WNBA":"wnba"}
    sl_sport = sport_map.get(sport,"nba")
    try:
        # Try multiple Sleeper endpoints
        sleeper_urls = [
            f"https://api.sleeper.com/lines/v1/{sl_sport}",
            f"https://api.sleeper.com/v1/lines/{sl_sport}",
            f"https://api.sleeper.app/lines/v1/{sl_sport}",
            f"https://api.sleeper.app/v1/lines/{sl_sport}",
        ]
        r = None
        for su in sleeper_urls:
            try:
                _r = requests.get(su, headers={"User-Agent": UA,
                    "Accept": "application/json"}, timeout=10)
                if _r.status_code == 200:
                    r = _r
                    print(f"    Endpoint: {su[-40:]}")
                    break
                print(f"    {_r.status_code} {su[-40:]}")
            except:
                pass
        if not r:
            print(f"    All Sleeper endpoints failed")
            return props
        r.status_code  # will be 200 if we got here
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("lines", data.get("props",[]))
            for item in items:
                pname = item.get("player_name","") or item.get("name","")
                stat  = item.get("stat","") or item.get("prop","")
                line  = item.get("line") or item.get("value")
                if pname and line is not None:
                    props.append({"Player":pname,"Prop":stat,"Line":float(str(line).replace("+","")),
                                  "Side":"OVER","OverOdds":"—","UnderOdds":"—",
                                  "Book":"Sleeper","Sport":sport,"source":"sleeper_auto"})
            print(f"    Props: {len(props)}")
    except Exception as e:
        print(f"    Error: {e}")
    return props

def scrape_bovada_lines(sport):
    """Bovada game lines — direct, no login."""
    print(f"\n  Bovada {sport} (game lines):")
    sport_map = {"NBA":"basketball/nba","MLB":"baseball/mlb",
                 "NHL":"hockey/nhl","NFL":"football/nfl","WNBA":"basketball/wnba"}
    sp = sport_map.get(sport,"basketball/nba")
    lines = []
    try:
        r = requests.get(
            f"https://www.bovada.lv/services/sports/event/coupon/events/A/description/{sp}",
            params={"lang":"en","eventsLimit":"50","preMatchOnly":"true"},
            headers={"User-Agent": UA, "Referer": "https://www.bovada.lv/"},
            timeout=10
        )
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            for event in data:
                for ev in event.get("events",[]):
                    matchup = ev.get("description","")
                    for comp in ev.get("displayGroups",[]):
                        for mkt in comp.get("markets",[]):
                            desc = mkt.get("description","").lower()
                            if not any(x in desc for x in ["moneyline","spread","total"]):
                                continue
                            for out in mkt.get("outcomes",[]):
                                price = out.get("price",{})
                                lines.append({
                                    "matchup":  matchup,
                                    "market":   mkt.get("description",""),
                                    "outcome":  out.get("description",""),
                                    "american": price.get("american",""),
                                    "handicap": price.get("handicap",""),
                                    "Book":     "Bovada",
                                    "Sport":    sport,
                                    "source":   "bovada_auto",
                                })
            print(f"    Lines: {len(lines)}")
    except Exception as e:
        print(f"    Error: {e}")
    return lines

def scrape_betonline(sport):
    """BetOnline — no login needed."""
    print(f"\n  BetOnline {sport}:")
    cfg_s = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props = []
    headers = {"User-Agent": UA, "Content-Type": "application/json-patch+json",
               "gsetting": "bolnasite", "Origin": "https://www.betonline.ag",
               "Referer": "https://www.betonline.ag/"}
    try:
        # Get menu
        # Try GET first, then POST
        rm = None
        for method, data in [("GET", None), ("POST", {})]:
            try:
                if method == "GET":
                    _rm = requests.get(
                        "https://api-offering.betonline.ag/api/offering/Sports/get-menu",
                        headers={**headers,"Content-Type":"application/json","gsetting":"bolsassite"},
                        timeout=10
                    )
                else:
                    _rm = requests.post(
                        "https://api-offering.betonline.ag/api/offering/Sports/get-menu",
                        headers={**headers,"Content-Type":"application/json","gsetting":"bolsassite"},
                        json=data, timeout=10
                    )
                print(f"    Menu ({method}): {_rm.status_code}")
                if _rm.status_code == 200:
                    rm = _rm
                    break
            except Exception as _be:
                print(f"    Menu error: {_be}")
        if not rm or rm.status_code != 200:
            print(f"    BetOnline menu unavailable")
            return props
        if rm.status_code == 200:
            today = date.today().isoformat()
            data  = rm.json()
            gids  = []
            items = data if isinstance(data,list) else []
            if not items:
                for v in (data.values() if isinstance(data,dict) else []):
                    if isinstance(v,list): items.extend(v)
            for item in items:
                gid = item.get("gameID") or item.get("id")
                d   = str(item.get("startDate","") or item.get("date","") or "")
                if gid and today in d:
                    gids.append(gid)
            print(f"    Games today: {len(gids)}")
            for gid in gids[:8]:
                rp = requests.post(
                    "https://api-offering.betonline.ag/api/offering/sports/get-linked-events",
                    headers=headers,
                    json={"sport":cfg_s["sport"],"league":cfg_s["league"],
                          "gameID":gid,"scheduleText":None},
                    timeout=10
                )
                if rp.status_code == 200:
                    evts = rp.json()
                    evts = evts if isinstance(evts,list) else evts.get("events",[evts])
                    for ev in evts:
                        for key in ["markets","props","playerProps","offerings"]:
                            mkts = ev.get(key,[])
                            if mkts: break
                        for mkt in (mkts if isinstance(mkts,list) else []):
                            mname = (mkt.get("name","") or mkt.get("description","")).strip()
                            parts = mkt.get("participants","") or mkt.get("outcomes","") or []
                            if isinstance(parts,dict): parts=list(parts.values())
                            for part in parts:
                                player = (part.get("name","") or part.get("player","")).strip()
                                line   = part.get("line") or part.get("handicap")
                                over   = part.get("overOdds") or part.get("over")
                                under  = part.get("underOdds") or part.get("under")
                                side   = str(part.get("side","OVER")).upper()
                                if not player or line is None: continue
                                if mname.lower() in ALWAYS_OVER and side=="UNDER": continue
                                props.append({"Player":player,"Prop":mname,
                                    "Line":float(str(line).replace("+","")),
                                    "Side":side or "OVER",
                                    "OverOdds":str(over) if over else "—",
                                    "UnderOdds":str(under) if under else "—",
                                    "Book":"BetOnline","Sport":sport,"source":"betonline_auto"})
                time.sleep(0.4)
    except Exception as e:
        print(f"    Error: {e}")
    print(f"    Props: {len(props)}")
    return props

def scrape_mybookie(sport, cookies):
    """MyBookie props using session cookies."""
    print(f"\n  MyBookie {sport}:")
    cfg_s  = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props  = []
    cookie_str = "; ".join(f"{k}={v}" for k,v in cookies.items())
    headers = {
        "User-Agent": UA,
        "Cookie": cookie_str,
        "Referer":  "https://engine.mybookie.ag/sports/nba",
        "Origin":   "https://engine.mybookie.ag",
        "Accept":   "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        # CSRF tokens from session
        "X-CSRF-TOKEN":  cookies.get("XSRF-TOKEN",""),
        "X-XSRF-TOKEN":  cookies.get("XSRF-TOKEN",""),
    }
    try:
        r = requests.get(
            "https://engine.mybookie.ag/sports_api/leagues-lines",
            params={"sport":cfg_s["sport"],"league":cfg_s["league"]},
            headers=headers, timeout=15
        )
        print(f"    leagues-lines: {r.status_code}")
        if r.status_code in (401, 403):
            SESSION_DIR.joinpath("mybookie_session.json").unlink(missing_ok=True)
            print(f"    Session cleared — will re-login next run")
            return props, True
        if r.status_code != 200:
            return props, False
        today = date.today().isoformat()
        data  = r.json()
        items = data if isinstance(data,list) else data.get("data",data.get("games",[]))
        games = [item.get("gameID") or item.get("id") for item in items
                 if today in str(item.get("date","") or item.get("startDate","") or "")]
        games = [g for g in games if g]
        print(f"    Games: {len(games)}")
        for gid in games[:10]:
            rp = requests.get(
                "https://engine.mybookie.ag/sports_api/props-market-list",
                params={"gameID":gid,"isLive":"false"},
                headers=headers, timeout=15
            )
            if rp.status_code == 200:
                data2  = rp.json()
                mkts   = data2 if isinstance(data2,list) else data2.get("data",data2.get("markets",[data2]))
                for mkt in mkts:
                    mname = (mkt.get("name","") or mkt.get("marketName","")).strip()
                    sels  = mkt.get("selections","") or mkt.get("outcomes","") or []
                    if isinstance(sels,dict): sels=list(sels.values())
                    for sel in sels:
                        player = (sel.get("name","") or sel.get("player","") or sel.get("playerName","")).strip()
                        line   = sel.get("line") or sel.get("handicap") or sel.get("points")
                        over   = sel.get("overOdds") or sel.get("over")
                        under  = sel.get("underOdds") or sel.get("under")
                        side   = str(sel.get("side","OVER")).upper()
                        if not player or line is None: continue
                        if mname.lower() in ALWAYS_OVER and side=="UNDER": continue
                        props.append({"Player":player,"Prop":mname,
                            "Line":float(str(line).replace("+","")),
                            "Side":side or "OVER","OverOdds":str(over) if over else "—",
                            "UnderOdds":str(under) if under else "—",
                            "Book":"MyBookie","Sport":sport,"source":"mybookie_auto"})
            time.sleep(0.4)
    except Exception as e:
        print(f"    Error: {e}")
    print(f"    Props: {len(props)}")
    return props, False

def scrape_with_playwright(book, sport, cookies, prop_url, prop_selector_fn):
    """
    Generic Playwright scraper for regulated US books.
    Navigates to props page and extracts data via network interception.
    """
    print(f"\n  {book} {sport} (browser):")
    props = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":800})
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

            # Restore session cookies
            if cookies:
                ctx.add_cookies([
                    {"name":k,"value":v,"domain":prop_url.split("/")[2],"path":"/"}
                    for k,v in cookies.items()
                ])

            # Intercept API responses
            captured = []
            def handle_response(response):
                try:
                    if response.status == 200:
                        ct = response.headers.get("content-type","")
                        if "json" in ct:
                            size = int(response.headers.get("content-length",0) or 0)
                            # Capture any JSON response > 1KB (small = tracking/config)
                            url  = response.url
                            skip = any(x in url for x in
                                       ["analytics","tracking","telemetry","beacon",
                                        "nr-data","newrelic","google","facebook",
                                        "favicon","font","icon","svg","png","jpg",
                                        "ads","pixel","segment","mixpanel"])
                            if not skip:
                                try:
                                    data = response.json()
                                    # Only keep if it has useful data
                                    if isinstance(data, (dict, list)) and data:
                                        captured.append((url, data))
                                except:
                                    pass
                except:
                    pass

            page = ctx.new_page()
            page.on("response", handle_response)
            page.goto(prop_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
            # Also scroll to trigger lazy-loaded content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            browser.close()

            # Parse captured responses
            print(f"    Captured {len(captured)} API responses")
            for url, data in captured:
                parsed = prop_selector_fn(data, sport, book)
                if parsed:
                    print(f"    ✅ {len(parsed)} props from {url[-50:]}")
                else:
                    # Show structure of unparsed response for debugging
                    if isinstance(data, dict):
                        keys = list(data.keys())[:8]
                        print(f"    ⚠️  0 props | keys: {keys} | {url[-40:]}")
                    elif isinstance(data, list) and data:
                        first = data[0]
                        if isinstance(first, dict):
                            print(f"    ⚠️  0 props | list[{len(data)}] keys: {list(first.keys())[:6]} | {url[-40:]}")
                props.extend(parsed)

            print(f"    Total props: {len(props)}")

    except ImportError:
        print("  ❌ Playwright not installed: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"    Error: {e}")
    return props

def parse_dk_response(data, sport, book):
    """Parse DraftKings API response for props."""
    props = []
    try:
        # Format 1: REST format with sports/leagues/events/markets/selections
        markets   = data.get("markets", [])
        selections= data.get("selections", [])

        if markets and selections:
            # Build market lookup
            mkt_map = {m.get("marketId"): m for m in markets}
            # Build selection lookup by marketId
            sel_map = {}
            for sel in selections:
                mid = sel.get("marketId")
                if mid:
                    sel_map.setdefault(mid, []).append(sel)

            for mkt in markets:
                mid    = mkt.get("marketId")
                mname  = mkt.get("name","")
                # Only player props markets
                if not any(x in mname.lower() for x in
                           ["point","rebound","assist","steal","block","three",
                            "pra","strikeout","hit","home run","goal","shot",
                            "save","yard","reception","touchdown","pass","rush"]):
                    continue
                for sel in sel_map.get(mid, []):
                    player = sel.get("name","") or sel.get("label","")
                    line   = sel.get("line") or sel.get("handicap") or mkt.get("line")
                    odds   = sel.get("displayOdds",{}).get("american","—") or sel.get("oddsAmerican","—")
                    side   = ("OVER" if "over" in (sel.get("name","") or "").lower()
                              else "UNDER" if "under" in (sel.get("name","") or "").lower()
                              else "OVER")
                    player = player.replace(" Over","").replace(" Under","").strip()
                    if player and line is not None:
                        props.append({
                            "Player": player, "Prop": mname,
                            "Line": float(str(line).replace("+","")),
                            "Side": side,
                            "OverOdds": odds if side=="OVER" else "—",
                            "UnderOdds": odds if side=="UNDER" else "—",
                            "Book": book, "Sport": sport,
                            "source": f"{book.lower()}_auto"
                        })

        # Format 2: eventGroup structure
        if not props:
            categories = data.get("eventGroup",{}).get("offerCategories",[])
            for cat in categories:
                for sub in cat.get("offerSubcategoryDescriptors",[]):
                    for offer_list in sub.get("offerSubcategory",{}).get("offers",[]):
                        for offer in offer_list:
                            player = offer.get("playerName","") or offer.get("label","")
                            line   = offer.get("line")
                            for out in offer.get("outcomes",[]):
                                side = out.get("label","OVER").upper()
                                odds = out.get("oddsAmerican","—")
                                if player and line is not None:
                                    props.append({
                                        "Player": player, "Prop": cat.get("name",""),
                                        "Line": float(line), "Side": side,
                                        "OverOdds": odds if side=="OVER" else "—",
                                        "UnderOdds": odds if side=="UNDER" else "—",
                                        "Book": book, "Sport": sport,
                                        "source": f"{book.lower()}_auto"
                                    })
    except Exception as e:
        pass
    return props

def parse_fd_response(data, sport, book):
    """Parse FanDuel API response for props."""
    props = []
    try:
        markets = data.get("result",{}).get("markets",[])
        for mkt in markets:
            mname = mkt.get("marketName","")
            if not any(kw in mname.lower() for kw in
                       ["points","rebounds","assists","strikeout","home run",
                        "hits","goals","shots","yards","reception","pra"]):
                continue
            for runner in mkt.get("runners",[]):
                player = runner.get("runnerName","").replace(" Over","").replace(" Under","").strip()
                handicap = runner.get("handicap")
                odds = runner.get("winRunnerOdds",{}).get("americanDisplayOdds",{}).get("americanOdds","—")
                side = "OVER" if "over" in runner.get("runnerName","").lower() else "UNDER"
                if player and handicap is not None:
                    props.append({
                        "Player": player, "Prop": mname,
                        "Line": float(handicap), "Side": side,
                        "OverOdds": odds if side=="OVER" else "—",
                        "UnderOdds": odds if side=="UNDER" else "—",
                        "Book": book, "Sport": sport,
                        "source": f"{book.lower()}_auto"
                    })
    except Exception as e:
        pass
    return props

def parse_generic_response(data, sport, book):
    """Generic parser for BetMGM/Caesars responses."""
    props = []
    try:
        items = data if isinstance(data,list) else data.get("data",data.get("markets",[data]))
        for item in items:
            mname = (item.get("name","") or item.get("marketName","") or item.get("description","")).strip()
            sels  = item.get("selections","") or item.get("outcomes","") or item.get("players","") or []
            if isinstance(sels,dict): sels=list(sels.values())
            for sel in sels:
                player = (sel.get("name","") or sel.get("player","") or sel.get("description","")).strip()
                line   = sel.get("line") or sel.get("handicap") or sel.get("attr")
                odds_d = sel.get("odds") or sel.get("price") or 2.0
                over   = sel.get("overOdds") or sel.get("over") or ""
                under  = sel.get("underOdds") or sel.get("under") or ""
                side   = str(sel.get("side","") or sel.get("type","OVER")).upper()
                if not player or line is None: continue
                if mname.lower() in ALWAYS_OVER and side=="UNDER": continue
                try:
                    if not over and odds_d:
                        d = float(odds_d)
                        american = f"+{int((d-1)*100)}" if d>=2 else f"{int(-100/(d-1))}"
                        over = american
                except: pass
                props.append({
                    "Player": player, "Prop": mname,
                    "Line": float(str(line).replace("+","")),
                    "Side": side or "OVER",
                    "OverOdds": str(over) if over else "—",
                    "UnderOdds": str(under) if under else "—",
                    "Book": book, "Sport": sport,
                    "source": f"{book.lower()}_auto"
                })
    except: pass
    return props

def scrape_dk_pick6(sport, cookies):
    """
    DraftKings Pick6 DFS props.
    Uses Playwright to navigate pick6.draftkings.com
    and intercept the projections API.
    Requires DraftKings login (same credentials as sportsbook).
    """
    print(f"\n  DraftKings Pick6 {sport}:")
    props = []

    sport_map = {
        "NBA":  "basketball",
        "MLB":  "baseball",
        "NHL":  "hockey",
        "NFL":  "football",
        "WNBA": "basketball",
    }
    sp = sport_map.get(sport, "basketball")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )

            # Restore DK sportsbook cookies — shared auth
            if cookies:
                for name, value in cookies.items():
                    try:
                        ctx.add_cookies([{
                            "name": name, "value": value,
                            "domain": ".draftkings.com", "path": "/"
                        }])
                    except:
                        pass

            # Intercept Pick6 API responses
            captured = []
            def on_response(response):
                try:
                    url = response.url
                    if any(x in url for x in
                           ["pick6","projection","lineup","player-prop",
                            "draftable","contest","entry"]):
                        if response.status == 200:
                            ct = response.headers.get("content-type","")
                            if "json" in ct:
                                try:
                                    captured.append((url, response.json()))
                                except:
                                    pass
                except:
                    pass

            page = ctx.new_page()
            page.on("response", on_response)

            # Navigate to Pick6
            print(f"    Loading pick6.draftkings.com...")
            page.goto(
                f"https://pick6.draftkings.com/draft/new-lineup/{sp}",
                wait_until="domcontentloaded",
                timeout=45000
            )
            time.sleep(5)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # Also try the lobby
            try:
                page.goto(
                    "https://pick6.draftkings.com/",
                    wait_until="domcontentloaded",
                    timeout=20000
                )
                time.sleep(3)
            except:
                pass

            browser.close()

            print(f"    Captured {len(captured)} API responses")
            for url, data in captured:
                parsed = parse_pick6_response(data, sport)
                if parsed:
                    print(f"    ✅ {len(parsed)} props from {url[-50:]}")
                props.extend(parsed)

    except ImportError:
        print("    ❌ Playwright not installed")
    except Exception as e:
        print(f"    Error: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for p in props:
        key = f"{p['Player']}_{p['Prop']}_{p['Line']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    print(f"    Pick6 props: {len(unique)}")
    return unique


def parse_pick6_response(data, sport):
    """Parse DraftKings Pick6 API response."""
    props = []
    try:
        # Pick6 structure varies — try multiple formats
        # Format 1: draftables list
        draftables = data.get("draftables", [])
        for player in draftables:
            pname = (player.get("displayName","") or
                     f"{player.get('firstName','')} {player.get('lastName','')}".strip())
            for stat in player.get("draftStatAttributes", []):
                stat_name = stat.get("label","") or stat.get("id","")
                line      = stat.get("value") or stat.get("projectedValue")
                if pname and line is not None:
                    props.append({
                        "Player":    pname,
                        "Prop":      stat_name,
                        "Line":      float(str(line).replace("+","")),
                        "Side":      "OVER",
                        "OverOdds":  "—",
                        "UnderOdds": "—",
                        "Book":      "DK Pick6",
                        "Sport":     sport,
                        "source":    "dk_pick6_auto",
                    })

        # Format 2: projections list
        projections = data.get("projections", data.get("playerProjections", []))
        for proj in projections:
            pname = (proj.get("playerName","") or proj.get("name","") or
                     f"{proj.get('firstName','')} {proj.get('lastName','')}".strip())
            for stat_key in ["points","rebounds","assists","pra","threes",
                             "steals","blocks","strikeouts","hits","homeRuns",
                             "goals","saves","shots"]:
                val = proj.get(stat_key) or proj.get(f"projected_{stat_key}")
                if val and pname:
                    stat_label = {
                        "points":"Points","rebounds":"Rebounds",
                        "assists":"Assists","pra":"Pts+Rebs+Asts",
                        "threes":"3-Pointers","steals":"Steals",
                        "blocks":"Blocks","strikeouts":"Strikeouts",
                        "hits":"Hits","homeRuns":"Home Runs",
                        "goals":"Goals","saves":"Saves","shots":"Shots"
                    }.get(stat_key, stat_key.title())
                    props.append({
                        "Player":    pname,
                        "Prop":      stat_label,
                        "Line":      float(val),
                        "Side":      "OVER",
                        "OverOdds":  "—",
                        "UnderOdds": "—",
                        "Book":      "DK Pick6",
                        "Sport":     sport,
                        "source":    "dk_pick6_auto",
                    })

        # Format 3: entries/contests with player lines
        entries = data.get("entries", data.get("contests", []))
        for entry in entries:
            for pick in entry.get("picks", entry.get("playerPicks", [])):
                pname = pick.get("playerName","") or pick.get("name","")
                stat  = pick.get("statType","") or pick.get("stat","")
                line  = pick.get("statLine") or pick.get("line") or pick.get("projectedValue")
                if pname and line is not None:
                    props.append({
                        "Player":    pname,
                        "Prop":      stat,
                        "Line":      float(str(line).replace("+","")),
                        "Side":      "OVER",
                        "OverOdds":  "—",
                        "UnderOdds": "—",
                        "Book":      "DK Pick6",
                        "Sport":     sport,
                        "source":    "dk_pick6_auto",
                    })

    except Exception as e:
        pass
    return props


def scrape_parlayplay(sport):
    """ParlayPlay props — uses session cookie from config.json."""
    print(f"\n  ParlayPlay {sport}:")
    props = []
    cfg_s = SPORT_MAP.get(sport, SPORT_MAP["NBA"])

    try:
        # Read session cookie from config
        cfg = load_config()
        pp_session = cfg.get("parlayplay", {}).get("session_cookie", "")
        if not pp_session:
            print("    No session_cookie in config.json parlayplay section")
            return props

        league_map = {"NBA": "nba", "MLB": "mlb", "NHL": "nhl", "WNBA": "wnba", "NFL": "nfl"}
        league = league_map.get(sport, "nba")

        headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://parlayplay.io/",
            "Origin": "https://parlayplay.io",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "x-parlayplay-native-platform": "web",
            "x-parlayplay-platform": "web",
            "x-requested-with": "XMLHttpRequest",
            "Cookie": f"sessionid={pp_session}",
        }

        r = requests.get(
            f"https://parlayplay.io/api/v1/crossgame/offering/",
            params={"league": league},
            headers=headers,
            timeout=15
        )
        print(f"    Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            games = data.get("games", data.get("offerings", data.get("data", [])))
            if isinstance(games, dict):
                games = list(games.values())

            for game in games:
                game_props = game.get("props", game.get("offerings", game.get("lines", [])))
                if isinstance(game_props, dict):
                    game_props = list(game_props.values())

                for prop in game_props:
                    player = (prop.get("playerName", "") or
                              prop.get("player_name", "") or
                              prop.get("name", "")).strip()
                    stat   = (prop.get("statName", "") or
                              prop.get("stat_name", "") or
                              prop.get("stat", "")).strip()
                    line   = prop.get("line") or prop.get("selectionPoints") or prop.get("value")

                    if not player or line is None:
                        # Try nested structure
                        for lv in prop.get("lineValues", prop.get("line_values", [])):
                            line = lv.get("selectionPoints") or lv.get("line")
                            if line is not None:
                                break

                    if player and line is not None:
                        props.append({
                            "Player": player,
                            "Prop": stat,
                            "Line": float(str(line).replace("+", "")),
                            "Side": "OVER",
                            "OverOdds": "—",
                            "UnderOdds": "—",
                            "Book": "ParlayPlay",
                            "Sport": sport,
                            "source": "parlayplay_auto",
                        })

            print(f"    Props: {len(props)}")
        elif r.status_code == 403:
            print(f"    403 — session cookie may be expired. Update parlayplay.session_cookie in config.json")
        else:
            print(f"    Error: {r.text[:100]}")

    except Exception as e:
        print(f"    Error: {e}")

    return props


def scrape_draftkings_curlffi(sport):
    """DraftKings props via curl_cffi — bypasses SSL fingerprinting."""
    print(f"\n  DraftKings {sport} (curl_cffi):")
    props = []

    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        print("    curl_cffi not installed")
        return props

    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Origin": "https://sportsbook.draftkings.com",
        "Referer": "https://sportsbook.draftkings.com/",
    }

    league_map = {
        "NBA": "42648", "MLB": "84240", "NHL": "42133",
        "WNBA": "92483", "NFL": "88670775",
    }
    lid = league_map.get(sport, "42648")
    sid = "16477"

    try:
        url = "https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets"
        params = {
            "isBatchable": "false",
            "templateVars": lid,
            "eventsQuery": f"$filter=leagueId eq \'{lid}\' AND clientMetadata/Subcategories/any(s: s/Id eq \'{sid}\')",
            "marketsQuery": f"$filter=clientMetadata/subCategoryId eq \'{sid}\' AND tags/all(t: t ne \'SportcastBetBuilder\')",
            "include": "Events",
            "entity": "events",
        }

        r = session.get(url, params=params, headers=headers, timeout=15)
        print(f"    Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            print(f"    Keys: {list(data.keys())[:10]}")
            markets = data.get("markets", [])
            selections = data.get("selections", [])
            # Also try nested structures
            if not markets:
                for key in data:
                    val = data[key]
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        subkeys = list(val[0].keys())[:6]
                        print(f"    {key}: list[{len(val)}] keys={subkeys}")
            print(f"    Markets: {len(markets)} | Selections: {len(selections)}")
            sel_by_mkt = {}
            for sel in selections:
                mid = sel.get("marketId")
                if mid:
                    sel_by_mkt.setdefault(mid, []).append(sel)

            for mkt in markets:
                mname = mkt.get("name", "")
                mid = mkt.get("marketId")
                if not any(kw in mname.lower() for kw in
                           ["point","rebound","assist","steal","block","three",
                            "strikeout","hit","home run","goal","shot","yard",
                            "touchdown","pass","rush","pra","fantasy"]):
                    continue
                for sel in sel_by_mkt.get(mid, []):
                    label = sel.get("label", "")
                    # Get player name from participants array
                    parts = sel.get("participants", [])
                    player = parts[0].get("name","") if parts else ""
                    if not player:
                        player = label
                    line = sel.get("points") or sel.get("line") or sel.get("handicap")
                    odds_am = sel.get("displayOdds",{}).get("american","—")
                    # Parse Over/Under from label
                    if "Under" in label:
                        sd = "UNDER"
                        if not player or player == label:
                            player = label.replace("Under","").strip()
                    elif "Over" in label:
                        sd = "OVER"
                        if not player or player == label:
                            player = label.replace("Over","").strip()
                    else:
                        sd = "OVER"
                    # Extract line from label if not in fields
                    if line is None:
                        import re as _re
                        _lm = _re.search(r"([\d.]+)", label)
                        if _lm:
                            try: line = float(_lm.group(1))
                            except: pass
                    if player and line is not None:
                        props.append({
                            "Player": player, "Prop": mname,
                            "Line": float(str(line).replace("+","")),
                            "Side": sd,
                            "OverOdds": str(odds_am) if sd == "OVER" else "—",
                            "UnderOdds": str(odds_am) if sd == "UNDER" else "—",
                            "Book": "DraftKings", "Sport": sport,
                            "source": "draftkings_curlffi",
                        })
            print(f"    Props: {len(props)}")
        else:
            print(f"    Error: {r.text[:100]}")
    except Exception as e:
        print(f"    Error: {e}")

    return props


def scrape_caesars_curlffi(sport):
    """Caesars props via curl_cffi + api.americanwagering.com."""
    print(f"\n  Caesars {sport} (curl_cffi):")
    props = []
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        print("    curl_cffi not installed")
        return props

    headers = {"User-Agent": UA, "Accept": "application/json",
               "Origin": "https://sportsbook.caesars.com", "Referer": "https://sportsbook.caesars.com/"}
    sport_map = {"NBA": "basketball", "MLB": "baseball", "NHL": "icehockey",
                 "WNBA": "basketball", "NFL": "americanfootball"}
    czr_sport = sport_map.get(sport, "basketball")
    base = f"https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/{czr_sport}"

    try:
        r1 = session.get(f"{base}/competitions", headers=headers, timeout=15)
        print(f"    Competitions: {r1.status_code}")
        if r1.status_code == 403:
            # Try the player-props endpoint directly
            print(f"    Trying direct player-props endpoint...")
            r1b = session.get(
                f"https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/{czr_sport}/player-props",
                headers=headers, timeout=15
            )
            print(f"    Direct player-props: {r1b.status_code}")
            if r1b.status_code == 200:
                data = r1b.json()
                print(f"    Keys: {list(data.keys())[:8] if isinstance(data, dict) else f'list[{len(data)}]'}")
        if r1.status_code != 200: return props

        comps = r1.json() if isinstance(r1.json(), list) else r1.json().get("competitions", [])
        targets = {"NBA": "nba", "MLB": "mlb", "NHL": "nhl", "WNBA": "wnba", "NFL": "nfl"}
        comp_id = None
        for c in comps:
            if targets.get(sport, "nba") in c.get("name", "").lower():
                comp_id = c.get("id"); break
        if not comp_id and comps:
            comp_id = comps[0].get("id")
        if not comp_id: return props

        r2 = session.get(f"{base}/competitions/{comp_id}/tabs/SCHEDULE%7CPlayer%20Props",
            headers=headers, timeout=15)
        print(f"    Props: {r2.status_code}")
        if r2.status_code == 200:
            data = r2.json()
            events = data.get("events", [])
            if not events:
                events = data.get("competitions", [{}])[0].get("events", []) if data.get("competitions") else []
            for ev in events:
                for mkt in ev.get("markets", []):
                    mname = mkt.get("name", "")
                    for sel in mkt.get("selections", []):
                        fname = sel.get("name", "")
                        odds_a = sel.get("price", {}).get("a") or sel.get("price", {}).get("american")
                        hcap = sel.get("points") or sel.get("handicap") or sel.get("line")
                        player, sd = fname, "OVER"
                        if " Over " in fname: player, sd = fname.split(" Over ")[0].strip(), "OVER"
                        elif " Under " in fname: player, sd = fname.split(" Under ")[0].strip(), "UNDER"
                        if not player or hcap is None: continue
                        try: lf = float(str(hcap).replace("+",""))
                        except: continue
                        od = "—"
                        if odds_a is not None:
                            od = f"{'+' if float(odds_a)>0 else ''}{int(float(odds_a))}"
                        props.append({"Player": player, "Prop": mname, "Line": lf, "Side": sd,
                            "OverOdds": od if sd=="OVER" else "—", "UnderOdds": od if sd=="UNDER" else "—",
                            "Book": "Caesars", "Sport": sport, "source": "caesars_curlffi"})
        print(f"    Props: {len(props)}")
    except Exception as e:
        print(f"    Error: {e}")
    return props


def scrape_betmgm_curlffi(sport):
    """BetMGM props via curl_cffi."""
    print(f"\n  BetMGM {sport} (curl_cffi):")
    props = []
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        print("    curl_cffi not installed")
        return props

    MGM_KEY = "N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5"
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Origin": "https://www.az.betmgm.com", "Referer": "https://www.az.betmgm.com/"}
    sport_ids = {"NBA": 7, "MLB": 23, "NHL": 19, "WNBA": 7, "NFL": 11}
    sid = sport_ids.get(sport, 7)

    try:
        r1 = session.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixtures",
            params={"x-bwin-accessid": MGM_KEY, "lang": "en-us", "country": "US",
                    "userCountry": "US", "subdivision": "US-AZ", "offerMapping": "Filtered",
                    "sportIds": sid, "fixtureTypes": "Standard", "state": "Latest",
                    "skip": 0, "take": 30, "sortBy": "StartDate"},
            headers=headers, timeout=15)
        print(f"    Fixtures: {r1.status_code}")
        if r1.status_code != 200:
            print(f"    Response: {r1.text[:100]}")
            return props

        _mgm_fixtures = r1.json().get("fixtures", [])
        print(f"    Found {len(_mgm_fixtures)} fixtures")
        if _mgm_fixtures:
            _f0 = _mgm_fixtures[0]
            print(f"    First fixture keys: {list(_f0.keys())[:8]}")
            _f0_games = _f0.get("games", [])
            print(f"    First fixture games: {len(_f0_games)}")
            if _f0_games:
                print(f"    First game: {_f0_games[0].get('name',{}).get('value','')}")
        for fix in _mgm_fixtures[:8]:
            fix_id = fix.get("id")
            fix_name = fix.get("name",{}).get("value","") if isinstance(fix.get("name"),dict) else str(fix.get("name",""))
            if not fix_id: continue
            # Skip futures/specials — only want today's games
            if any(skip in fix_name.lower() for skip in ["futures","special","season","championship","mvp","award","2026/27","2027"]):
                continue
            print(f"    Fixture: {fix_name}")

            r2 = session.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixture-offers",
                params={"x-bwin-accessid": MGM_KEY, "lang": "en-us", "country": "US",
                        "userCountry": "US", "subdivision": "US-AZ",
                        "fixtureIds": fix_id, "gameIds": ",".join(game_ids[:10]),
                        "offerMapping": "Filtered"},
                headers=headers, timeout=10)
            if r2.status_code != 200: continue

            _mgm_resp = r2.json()
            _mgm_fxs = _mgm_resp.get("fixtures", [_mgm_resp]) if isinstance(_mgm_resp, dict) else _mgm_resp
            for fd in _mgm_fxs:
                # Check both games and optionMarkets
                all_markets = fd.get("games", []) + fd.get("optionMarkets", [])
                for game in all_markets:
                    mname = game.get("name", {}).get("value", "") if isinstance(game.get("name"), dict) else str(game.get("name",""))
                    results = game.get("results", game.get("options", []))
                    for res in results:
                        fname = res.get("name", {}).get("value", "") if isinstance(res.get("name"), dict) else str(res.get("name",""))
                        price = res.get("price", {})
                        odds  = price.get("americanOdds") or price.get("americanOdds")
                        attr  = res.get("attr", "") or res.get("handicap", "")
                        player, sd = fname, "OVER"
                        if " Over " in fname:
                            player, sd = fname.split(" Over ")[0].strip(), "OVER"
                        elif " Under " in fname:
                            player, sd = fname.split(" Under ")[0].strip(), "UNDER"
                        if not player or not attr: continue
                        try: line_f = float(str(attr).replace("+",""))
                        except: continue
                        od = f"{'+' if odds > 0 else ''}{int(odds)}" if odds else "—"
                        props.append({"Player": player, "Prop": mname,
                            "Line": line_f, "Side": sd,
                            "OverOdds": od if sd == "OVER" else "—",
                            "UnderOdds": od if sd == "UNDER" else "—",
                            "Book": "BetMGM", "Sport": sport, "source": "betmgm_curlffi"})
            time.sleep(0.3)
        print(f"    Props: {len(props)}")
    except Exception as e:
        print(f"    Error: {e}")
    return props


def scrape_fanduel_curlffi(sport):
    """FanDuel props via curl_cffi — bypasses SSL fingerprinting."""
    print(f"\n  FanDuel {sport} (curl_cffi):")
    props = []

    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        print("    curl_cffi not installed — pip install curl_cffi")
        return props

    FD_KEY = "FhMFpcPWXMeyZxOx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://az.sportsbook.fanduel.com",
        "Referer": "https://az.sportsbook.fanduel.com/",
        "x-application": FD_KEY,
    }

    event_type_map = {"NBA": 7522, "MLB": 6, "NHL": 7524, "WNBA": 614, "NFL": 63747}
    etid = event_type_map.get(sport, 7522)

    try:
        # Step 1: Get today's events
        r1 = session.get(
            f"https://api.sportsbook.fanduel.com/sbapi/content-managed-page",
            params={"page": "SPORT", "eventTypeId": etid, "_ak": FD_KEY, "timezone": "America/Phoenix"},
            headers=headers,
            timeout=15
        )
        print(f"    Events: {r1.status_code}")

        if r1.status_code != 200:
            print(f"    Response: {r1.text[:100]}")
            return props

        data = r1.json()

        # Extract event IDs
        attachments = data.get("attachments", {})
        events = attachments.get("events", {})
        markets = attachments.get("markets", {})
        selections_map = attachments.get("selections", {})

        print(f"    Events: {len(events)} | Markets: {len(markets)} | Selections: {len(selections_map)}")

        # Parse markets and selections from attachments
        for mkt_id, mkt in markets.items():
            mkt_name = mkt.get("marketName", "")
            mkt_type = mkt.get("marketType", "")

            # Only player props
            if not any(kw in mkt_name.lower() for kw in
                       ["point", "rebound", "assist", "steal", "block", "three",
                        "strikeout", "hit", "home run", "rbi", "bases",
                        "goal", "shot", "save", "yard", "reception",
                        "touchdown", "pass", "rush", "pra", "fantasy",
                        "pts", "reb", "ast"]):
                continue

            runners = mkt.get("runners", [])
            for runner in runners:
                sel_id = str(runner.get("selectionId", ""))
                handicap = runner.get("handicap")
                player_name = runner.get("runnerName", "")

                # Clean player name
                if " Over " in player_name:
                    player_name = player_name.split(" Over ")[0].strip()
                    side = "OVER"
                elif " Under " in player_name:
                    player_name = player_name.split(" Under ")[0].strip()
                    side = "UNDER"
                else:
                    side = "OVER"

                # Get odds from selection details
                odds = "—"
                sel_detail = selections_map.get(sel_id, {})
                if sel_detail:
                    win_odds = sel_detail.get("winRunnerOdds", {})
                    american = win_odds.get("americanDisplayOdds", {}).get("americanOdds")
                    if american is not None:
                        odds = f"{'+' if american > 0 else ''}{int(american)}"

                if not player_name or handicap is None:
                    continue

                props.append({
                    "Player": player_name,
                    "Prop": mkt_name,
                    "Line": float(handicap),
                    "Side": side,
                    "OverOdds": odds if side == "OVER" else "—",
                    "UnderOdds": odds if side == "UNDER" else "—",
                    "Book": "FanDuel",
                    "Sport": sport,
                    "source": "fanduel_curlffi",
                })

        # If attachments didn't have enough data, try per-event
        if not props:
            event_ids = list(events.keys())[:5]
            print(f"    Trying per-event for {len(event_ids)} events...")
            for eid in event_ids:
                r2 = session.get(
                    f"https://api.sportsbook.fanduel.com/sbapi/event-page",
                    params={"_ak": FD_KEY, "eventId": eid,
                            "tab": "player-props", "useQuickBets": "true"},
                    headers=headers,
                    timeout=10
                )
                if r2.status_code == 200:
                    ev_data = r2.json()
                    ev_attach = ev_data.get("attachments", {})
                    ev_markets = ev_attach.get("markets", {})
                    ev_sels = ev_attach.get("selections", {})

                    for mid, m in ev_markets.items():
                        m_name = m.get("marketName", "")
                        if not any(kw in m_name.lower() for kw in
                                   ["point", "rebound", "assist", "strikeout",
                                    "hit", "home run", "goal", "shot", "yard",
                                    "touchdown", "pass", "rush"]):
                            continue
                        for rn in m.get("runners", []):
                            rn_name = rn.get("runnerName", "")
                            hcap = rn.get("handicap")
                            sid = str(rn.get("selectionId", ""))
                            if " Over " in rn_name:
                                pn = rn_name.split(" Over ")[0].strip()
                                sd = "OVER"
                            elif " Under " in rn_name:
                                pn = rn_name.split(" Under ")[0].strip()
                                sd = "UNDER"
                            else:
                                pn = rn_name
                                sd = "OVER"
                            od = "—"
                            sd_det = ev_sels.get(sid, {})
                            if sd_det:
                                am = sd_det.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                                if am is not None:
                                    od = f"{'+' if am > 0 else ''}{int(am)}"
                            if pn and hcap is not None:
                                props.append({
                                    "Player": pn, "Prop": m_name,
                                    "Line": float(hcap), "Side": sd,
                                    "OverOdds": od if sd == "OVER" else "—",
                                    "UnderOdds": od if sd == "UNDER" else "—",
                                    "Book": "FanDuel", "Sport": sport,
                                    "source": "fanduel_curlffi",
                                })
                time.sleep(0.3)

    except Exception as e:
        print(f"    Error: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for p in props:
        key = f"{p['Player']}_{p['Prop']}_{p['Line']}_{p['Side']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    print(f"    FanDuel props: {len(unique)}")
    return unique


# ── Direct API scrapers (no Playwright needed) ────────────────

def scrape_dk_api(sport, cookies):
    """DraftKings direct API — uses session cookies."""
    print(f"\n  DraftKings {sport} (API):")
    props = []
    cookie_str = "; ".join(f"{k}={v}" for k,v in cookies.items())
    headers = {
        "User-Agent": UA,
        "Cookie": cookie_str,
        "Accept": "application/json",
        "Referer": "https://sportsbook.draftkings.com/",
        "Origin":  "https://sportsbook.draftkings.com",
    }
    sport_ids = {"NBA":42648,"MLB":84240,"NHL":42133,"WNBA":42648,"NFL":88670775}
    sid = sport_ids.get(sport, 42648)
    try:
        # Get today's events
        r = requests.get(
            f"https://sportsbook.draftkings.com/sites/US-AZ-SB/api/v5/eventgroups/{sid}",
            params={"format":"json","include":"participants+groups+subgroups"},
            headers=headers, timeout=15
        )
        print(f"    Events: {r.status_code}")
        if r.status_code == 200:
            data   = r.json()
            events = data.get("eventGroup",{}).get("events",[])
            print(f"    Found {len(events)} events")
            for ev in events[:5]:
                eid = ev.get("eventId","")
                if not eid:
                    continue
                # Get player props for this event
                rp = requests.get(
                    f"https://sportsbook.draftkings.com/sites/US-AZ-SB/api/v5/eventgroups/{sid}/categories/player-props/events/{eid}",
                    headers=headers, timeout=10
                )
                if rp.status_code == 200:
                    pdata = rp.json()
                    parsed = parse_dk_response(pdata, sport, "DraftKings")
                    props.extend(parsed)
                time.sleep(0.3)
    except Exception as e:
        print(f"    Error: {e}")
    print(f"    Props: {len(props)}")
    return props


def scrape_fd_api(sport, cookies):
    """FanDuel direct API."""
    print(f"\n  FanDuel {sport} (API):")
    props = []
    cookie_str = "; ".join(f"{k}={v}" for k,v in cookies.items())
    headers = {
        "User-Agent": UA,
        "Cookie": cookie_str,
        "Accept": "application/json",
        "Referer": "https://az.sportsbook.fanduel.com/",
        "x-api-key": "FhMFpcPWXMeyZxOx",
    }
    event_type_map = {"NBA":7522,"MLB":1,"NHL":4,"WNBA":614,"NFL":5}
    etid = event_type_map.get(sport, 7522)
    try:
        r = requests.get(
            f"https://sbapi.fanduel.com/api/content-managed-page",
            params={"page":"SPORT","eventTypeId":etid,"_ak":"FhMFpcPWXMeyZxOx","timezone":"America/Phoenix"},
            headers=headers, timeout=15
        )
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data   = r.json()
            events = data.get("result",{}).get("events",[])
            print(f"    Events: {len(events)}")
            for ev in events[:5]:
                eid = ev.get("eventId")
                if not eid:
                    continue
                rp = requests.get(
                    f"https://sbapi.fanduel.com/api/event-page",
                    params={"eventId":eid,"_ak":"FhMFpcPWXMeyZxOx"},
                    headers=headers, timeout=10
                )
                if rp.status_code == 200:
                    parsed = parse_fd_response(rp.json(), sport, "FanDuel")
                    props.extend(parsed)
                time.sleep(0.3)
        else:
            print(f"    Response: {r.text[:100]}")
    except Exception as e:
        print(f"    Error: {e}")
    print(f"    Props: {len(props)}")
    return props


def scrape_mgm_api(sport, cookies):
    """BetMGM direct API using CDS endpoints."""
    print(f"\n  BetMGM {sport} (API):")
    props = []
    cookie_str = "; ".join(f"{k}={v}" for k,v in cookies.items())
    headers = {
        "User-Agent": UA,
        "Cookie": cookie_str,
        "Accept": "application/json",
        "Referer": "https://www.az.betmgm.com/",
        "x-bwin-accessid": "NDBlOWQ5YjgtMjk3ZS00MTI0LTg3YmMtZDA3ZGVlMWM4MjYw",
    }
    sport_ids = {"NBA":7,"MLB":23,"NHL":19,"WNBA":7,"NFL":11}
    sid = sport_ids.get(sport, 7)
    try:
        r = requests.get(
            "https://cds-api.betmgm.com/bettingoffer/fixtures",
            params={
                "x-bwin-accessid": "NDBlOWQ5YjgtMjk3ZS00MTI0LTg3YmMtZDA3ZGVlMWM4MjYw",
                "lang": "en-us", "country": "US", "userCountry": "US",
                "subdivision": "US-AZ", "offer-category": "player-props",
                "sportId": sid, "fixtureTypes": "Standard",
                "state": "Latest", "skip": 0, "take": 50, "sortBy": "StartDate"
            },
            headers=headers, timeout=15
        )
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            fixtures = data.get("fixtures",[])
            print(f"    Fixtures: {len(fixtures)}")
            for fix in fixtures:
                for game in fix.get("games",[]):
                    mname = game.get("name",{}).get("value","")
                    for result in game.get("results",[]):
                        player = result.get("name",{}).get("value","")
                        odds_d = result.get("odds", 2.0)
                        attr   = result.get("attr","")
                        side   = "OVER" if "over" in player.lower() else "UNDER"
                        player = player.replace(" Over","").replace(" Under","").strip()
                        if not player or not attr:
                            continue
                        try:
                            american = f"+{int((float(odds_d)-1)*100)}" if float(odds_d)>=2 else f"{int(-100/(float(odds_d)-1))}"
                        except:
                            american = "—"
                        props.append({
                            "Player": player, "Prop": mname,
                            "Line": float(str(attr).replace("+","")),
                            "Side": side,
                            "OverOdds": american if side=="OVER" else "—",
                            "UnderOdds": american if side=="UNDER" else "—",
                            "Book": "BetMGM", "Sport": sport,
                            "source": "betmgm_api"
                        })
        else:
            print(f"    Response: {r.text[:100]}")
    except Exception as e:
        print(f"    Error: {e}")
    print(f"    Props: {len(props)}")
    return props


def scrape_czr_api(sport, cookies):
    """Caesars direct API."""
    print(f"\n  Caesars {sport} (API):")
    props = []
    cookie_str = "; ".join(f"{k}={v}" for k,v in cookies.items())
    headers = {
        "User-Agent": UA,
        "Cookie": cookie_str,
        "Accept": "application/json",
        "Referer": "https://sportsbook.caesars.com/us/az/bet",
    }
    sport_ids = {"NBA":"basketball","MLB":"baseball","NHL":"icehockey","WNBA":"basketball","NFL":"americanfootball"}
    sp = sport_ids.get(sport, "basketball")
    try:
        # Get player props events
        r = requests.get(
            f"https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/{sp}/player-props",
            headers=headers, timeout=15
        )
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data,list) else data.get("playerProps", data.get("events",[]))
            print(f"    Items: {len(items)}")
            for item in items:
                mname   = item.get("marketName","") or item.get("name","")
                player  = item.get("playerName","") or item.get("player","")
                line    = item.get("line") or item.get("handicap")
                over_ml = item.get("overOdds","—")
                under_ml= item.get("underOdds","—")
                if player and line is not None:
                    props.append({
                        "Player": player, "Prop": mname,
                        "Line": float(str(line).replace("+","")),
                        "Side": "OVER",
                        "OverOdds": str(over_ml), "UnderOdds": str(under_ml),
                        "Book": "Caesars", "Sport": sport,
                        "source": "caesars_api"
                    })
        else:
            print(f"    Response: {r.text[:100]}")
    except Exception as e:
        print(f"    Error: {e}")
    print(f"    Props: {len(props)}")
    return props


# ── Gist Push ─────────────────────────────────────────────────
def push_to_gist(all_props, all_lines, token, gist_id):
    if not token or not gist_id:
        print("❌ No GitHub token/Gist ID")
        return False
    books   = list({p["Book"] for p in all_props + all_lines})
    # Trim to stay under GitHub Gist 1MB limit
    max_props = 2500
    if len(all_props) > max_props:
        # Keep proportional mix of sports
        from collections import defaultdict
        sport_props = defaultdict(list)
        for p in all_props:
            sport_props[p.get("Sport","NBA")].append(p)
        trimmed = []
        per_sport = max_props // max(len(sport_props), 1)
        for sp_list in sport_props.values():
            trimmed.extend(sp_list[:per_sport])
        all_props = trimmed[:max_props]

    payload = {
        "date":        date.today().isoformat(),
        "timestamp":   datetime.now().isoformat(),
        "prop_count":  len(all_props),
        "line_count":  len(all_lines),
        "books":       books,
        "props":       all_props,
        "lines":       all_lines[:1000],  # cap lines too
    }

    # Verify size before pushing
    import json as _json
    payload_str = _json.dumps(payload)
    if len(payload_str) > 900000:
        payload["props"] = all_props[:1500]
        payload["lines"] = all_lines[:500]
        payload_str = _json.dumps(payload)
        print(f"  ⚠️  Trimmed to fit Gist limit: {len(payload['props'])} props")

    r = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {"auto_scraped_props.json": {
            "content": json.dumps(payload, indent=2)
        }}},
        timeout=15
    )
    if r.status_code == 200:
        print(f"\n✅ Pushed to Gist: {len(all_props)} props + {len(all_lines)} lines")
        print(f"   Books: {', '.join(books)}")
        return True
    print(f"\n❌ Gist push failed: {r.status_code}")
    return False

# ── Main ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="BetCouncil Auto Scraper v2.0")
    parser.add_argument("--sport",   default="NBA")
    parser.add_argument("--all",     action="store_true")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--books",   default="", help="Comma-separated: dk,fd,mgm,czr,mb,bo,pp,ud,sl,bov")
    args = parser.parse_args()

    cfg    = load_config()
    token  = cfg.get("github_token","")
    gist   = cfg.get("gist_id","")
    sports = ["NBA","MLB","NHL","WNBA"] if args.all else [args.sport]

    # Determine which books to scrape
    book_filter = [b.strip().lower() for b in args.books.split(",")] if args.books else []
    def use(book): return not book_filter or book in book_filter

    # Login to regulated books once (session reused across sports)
    sessions = {}
    login_map = {
        "draftkings": ("dk",  login_draftkings),
        "fanduel":    ("fd",  login_fanduel),
        "betmgm":     ("mgm", login_betmgm),
        "caesars":    ("czr", login_caesars),
        "mybookie":   ("mb",  login_mybookie),
    }
    for book, (short, login_fn) in login_map.items():
        book_cfg = cfg.get(book,{})
        if book_cfg.get("username") and (use(short) or use(book)):
            print(f"\nAuthenticating {book}...")
            cookies = login_fn(book_cfg)
            if cookies:
                sessions[book] = cookies

    # Scrape each sport
    all_props = []
    all_lines = []

    for sport in sports:
        print(f"\n{'='*50}")
        print(f"BetCouncil Scraper | {sport} | {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*50}")

        # No-login sources
        if use("pp") and cfg.get("prizepicks",{}).get("enabled",True):
            all_props += scrape_prizepicks(sport)

        if use("ud") and cfg.get("underdog",{}).get("enabled",True):
            all_props += scrape_underdog(sport)

        if use("sl") and cfg.get("sleeper",{}).get("enabled",True):
            all_props += scrape_sleeper(sport)

        if use("bo") and cfg.get("betonline",{}).get("enabled",True):
            all_props += scrape_betonline(sport)

        if use("bov") and cfg.get("bovada",{}).get("enabled",True):
            all_lines += scrape_bovada_lines(sport)

        # ParlayPlay (uses session cookie from config.json)
        if (use("pp_play") or use("parlayplay")) and cfg.get("parlayplay",{}).get("session_cookie"):
            pp_play_props = scrape_parlayplay(sport)
            all_props += pp_play_props

        # Browser-based sources
        sport_map_dk = {"NBA":"nba","MLB":"mlb","NHL":"nhl","WNBA":"wnba","NFL":"nfl"}

        if use("dk") or use("draftkings"):
            dk_props = scrape_draftkings_curlffi(sport)
            all_props += dk_props

        # DraftKings Pick6 — DFS props (separate from sportsbook)
        if "draftkings" in sessions and (use("dk") or use("pick6") or use("draftkings")):
            pick6_props = scrape_dk_pick6(sport, sessions["draftkings"])
            all_props += pick6_props

        if use("fd") or use("fanduel"):
            fd_props = scrape_fanduel_curlffi(sport)
            all_props += fd_props

        if use("mgm") or use("betmgm"):
            mgm_props = scrape_betmgm_curlffi(sport)
            all_props += mgm_props

        if use("czr") or use("caesars"):
            czr_props = scrape_caesars_curlffi(sport)
            all_props += czr_props

        if (use("mb") or use("mybookie")):
            mb_cfg = cfg.get("mybookie", {})
            # Use manual cookie if provided (most reliable)
            manual_cookie = mb_cfg.get("session_cookie","")
            if manual_cookie:
                mb_cookies = {"manual": manual_cookie}
                # Convert string cookie to dict
                mb_cookies = {}
                for part in manual_cookie.split(";"):
                    if "=" in part:
                        k, v = part.strip().split("=", 1)
                        mb_cookies[k.strip()] = v.strip()
                mb_props, _ = scrape_mybookie(sport, mb_cookies)
                all_props += mb_props
            elif "mybookie" in sessions:
                mb_props, needs_relogin = scrape_mybookie(sport, sessions["mybookie"])
                if needs_relogin:
                    new_cookies = login_mybookie(mb_cfg)
                    if new_cookies:
                        sessions["mybookie"] = new_cookies
                        mb_props, _ = scrape_mybookie(sport, new_cookies)
                all_props += mb_props

        time.sleep(1)

    # Summary
    print(f"\n{'='*50}")
    print(f"TOTAL: {len(all_props)} props + {len(all_lines)} lines")
    books_found = {p["Book"] for p in all_props + all_lines}
    for book in sorted(books_found):
        count = len([x for x in all_props+all_lines if x.get("Book")==book])
        print(f"  {book:15} {count}")

    # Sample
    print("\nSample props:")
    for p in all_props[:5]:
        print(f"  {p['Book']:12} {p['Player']:25} {p['Prop']:20} {p['Line']}")

    # Push
    if not args.no_push and (all_props or all_lines):
        push_to_gist(all_props, all_lines, token, gist)
    elif args.no_push:
        print("\nTest mode — not pushing")

    print("\n✅ Done")

if __name__ == "__main__":
    main()
