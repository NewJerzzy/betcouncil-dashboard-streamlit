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
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# Global session for connection pooling
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
import time
import argparse
import os
import sys
from datetime import datetime, date
from pathlib import Path

# Windows redirects stdout/stderr through the system codepage (cp1252) instead
# of UTF-8 when output isn't a real console (e.g. `> output.txt`, or piped).
# This script prints emoji (✅❌⚠️) throughout for status — under cp1252 those
# raise UnicodeEncodeError and crash the run, but ONLY when redirected, which
# is exactly when you need the output most for debugging. Force UTF-8 so any
# print() anywhere in this file is safe regardless of how it's invoked.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

# Active months per sport (1=Jan … 12=Dec). Sports outside these months are
# automatically skipped when --all is used, to avoid wasting scrape budget
# on dead markets. Update here when seasons shift.
SEASON_ACTIVE_MONTHS = {
    "NBA":  [10, 11, 12, 1, 2, 3, 4, 5, 6],   # Oct–Jun  (off-season: Jul–Sep)
    "NHL":  [10, 11, 12, 1, 2, 3, 4, 5, 6],   # Oct–Jun  (off-season: Jul–Sep)
    "NFL":  [9, 10, 11, 12, 1, 2, 3],          # Sep–Mar  (off-season: Apr–Aug)
    "MLB":  [3, 4, 5, 6, 7, 8, 9, 10],         # Mar–Oct
    "WNBA": [5, 6, 7, 8, 9, 10],               # May–Oct
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
            except Exception:
                # Try clicking login button first if form not visible
                for btn in ["button:has-text('Log in')", "button:has-text('Sign in')",
                            "a:has-text('Log in')", "[data-testid='login']"]:
                    try:
                        page.click(btn, timeout=3000)
                        time.sleep(1)
                        break
                    except Exception:
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
            except Exception:
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
                except Exception:
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
            except Exception:
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
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
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
                except Exception:
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
                except Exception as _e:
                    pass  # TODO: log _e
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
    """PrizePicks — no login, curl_cffi bypass. Loops all sports when ALL is passed."""
    print(f"\n  PrizePicks {sport}:")
    sports_to_fetch = list(SPORT_MAP.keys()) if sport == "ALL" else [sport]
    props = []
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        session = requests
    for sp in sports_to_fetch:
        cfg_s = SPORT_MAP.get(sp, SPORT_MAP["NBA"])
        try:
            r = session.get(
                "https://partner-api.prizepicks.com/projections",
                params={"league_id": cfg_s["pp_id"], "per_page": 250,
                        "single_stat": "true", "game_mode": "pickem"},
                headers={"User-Agent": UA, "Referer": "https://app.prizepicks.com/",
                         "Origin": "https://app.prizepicks.com"},
                timeout=20
            )
            print(f"    [{sp}] Status: {r.status_code}")
            if r.status_code == 200:
                data     = r.json()
                included = {i["id"]: i for i in data.get("included",[]) if i.get("type")=="new_player"}
                before   = len(props)
                for proj in data.get("data",[]):
                    attrs  = proj.get("attributes",{})
                    pid    = proj.get("relationships",{}).get("new_player",{}).get("data",{}).get("id","")
                    pname  = included.get(pid,{}).get("attributes",{}).get("name","") or attrs.get("description","")
                    stat   = attrs.get("stat_type","")
                    line   = attrs.get("line_score")
                    if pname and line is not None:
                        props.append({"Player":pname,"Prop":stat,"Line":float(line),
                                      "Side":"OVER","OverOdds":"—","UnderOdds":"—",
                                      "Book":"PrizePicks","Sport":sp,"source":"prizepicks_auto"})
                print(f"    [{sp}] Props: {len(props) - before}")
        except Exception as e:
            print(f"    [{sp}] Error: {e}")
    print(f"    Total Props: {len(props)}")
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

            # Build appearances lookup
            appearances = {}
            for _a in data.get("appearances", []):
                _aid = str(_a.get("id", ""))
                if _aid:
                    appearances[_aid] = _a
            print(f"    Players: {len(players)} | Appearances: {len(appearances)}")

            # Debug: dump ALL keys and values to find the player link
            if lines:
                _l0 = lines[0]
                print(f"    ALL line keys: {list(_l0.keys())}")
                # Show non-null/non-empty values
                for _k, _v in _l0.items():
                    if _v and _k not in ("contract_terms_url","contract_url"):
                        _vs = str(_v)[:80]
                        print(f"      {_k}: {_vs}")
                # Also show first appearance
                if list(appearances.values()):
                    _a0 = list(appearances.values())[0]
                    print(f"    ALL appearance keys: {list(_a0.keys())}")
                # Also show first player
                _p0_id = list(players.keys())[0] if players else ""
                if _p0_id:
                    print(f"    Player sample: id={_p0_id} name={players[_p0_id]}")

            for line in lines:
                if line.get("status") != "active":
                    continue

                # CONFIRMED PATH: over_under → appearance_stat → appearance_id
                ou = line.get("over_under") or {}
                app_stat = ou.get("appearance_stat") or {} if isinstance(ou, dict) else {}
                stat_value = line.get("stat_value")
                stat_type = ""
                pname = ""

                if isinstance(app_stat, dict):
                    _ou_aid = str(app_stat.get("appearance_id", ""))
                    stat_type = app_stat.get("display_stat", "") or app_stat.get("stat_type", "")

                    # Chain: appearance_id → appearances → player_id → players
                    if _ou_aid and _ou_aid in appearances:
                        _app = appearances[_ou_aid]
                        _pid = str(_app.get("player_id", ""))
                        if _pid and _pid in players:
                            pname = players[_pid]

                # Fallback: live_event_stat
                if not pname:
                    live_stat = line.get("live_event_stat") or {}
                    if isinstance(live_stat, dict):
                        pname = (live_stat.get("player_name","") or
                                 live_stat.get("display_name","") or
                                 live_stat.get("full_name",""))
                        if not stat_type:
                            stat_type = live_stat.get("stat_type","") or live_stat.get("type","")

                # Fallback: options selection_header
                if not pname:
                    _opts = line.get("options", [])
                    if _opts:
                        pname = _opts[0].get("selection_header","") or _opts[0].get("choice_display_name_shorter","")

                # Get odds from options
                over_odds = "—"
                under_odds = "—"
                for _opt in line.get("options", []):
                    _choice = (_opt.get("choice","") or _opt.get("choice_display","")).lower()
                    _price = _opt.get("american_price","—")
                    if "higher" in _choice or "over" in _choice or "more" in _choice:
                        over_odds = str(_price)
                    elif "lower" in _choice or "under" in _choice or "less" in _choice:
                        under_odds = str(_price)

                # Sport filter removed from inline loop (was breaking appearance_id lookup)
                # Filtering happens after collection below

                if pname and stat_value is not None:
                    props.append({
                        "Player": pname, "Prop": stat_type,
                        "Line": float(str(stat_value).replace("+","")),
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
                    print(f"    Players: {len(players)} | Sample ID type: {type(pid).__name__} stat_value: {pid}")
                    if sample:
                        print(f"    Line appearance_id type: {type(sample.get('appearance_id','')).__name__} stat_value: {sample.get('appearance_id','')}")
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
            except Exception:
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
        from curl_cffi import requests as cf
        _bov_session = cf.Session(impersonate="chrome124")
        r = _bov_session.get(
            f"https://www.bovada.lv/services/sports/event/coupon/events/A/description/{sp}",
            params={"lang":"en","eventsLimit":"50","preMatchOnly":"true"},
            headers={"User-Agent": UA, "Referer": "https://www.bovada.lv/"},
            timeout=15
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
    """MyBookie props using session cookies. Uses curl_cffi (Chrome TLS
    impersonation) rather than plain requests — confirmed 2026-06-21 that a
    genuinely fresh, valid session cookie (including cf_clearance) still got
    403'd via plain requests. Cloudflare binds cf_clearance validity to the
    TLS fingerprint it was issued under; plain Python requests has a
    different handshake signature than a real browser, so even a correct
    cookie value gets rejected. Same fix already proven working elsewhere in
    this file for Caesars/BetRivers."""
    print(f"\n  MyBookie {sport}:")
    cfg_s  = SPORT_MAP.get(sport, SPORT_MAP["NBA"])
    props  = []
    cookie_str = "; ".join(f"{k}={v}" for k,v in cookies.items())
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
        from curl_cffi import requests as cf
        r = cf.get(
            "https://engine.mybookie.ag/sports_api/leagues-lines",
            params={"sport":cfg_s["sport"],"league":cfg_s["league"]},
            headers=headers, impersonate="chrome124", timeout=15
        )
        print(f"    leagues-lines: {r.status_code}")
        if r.status_code in (401, 403):
            SESSION_DIR.joinpath("mybookie_session.json").unlink(missing_ok=True)
            print(f"    Session expired (403) — attempting auto-refresh via browser...")
            _mb_cfg = load_config().get("mybookie", {})
            new_cookies = login_mybookie(_mb_cfg)
            if new_cookies:
                # Update config.json session_cookie with fresh values
                try:
                    _cfg_path = Path(__file__).parent / "config.json"
                    if _cfg_path.exists():
                        import json as _json
                        _full_cfg = _json.loads(_cfg_path.read_text())
                        _full_cfg.setdefault("mybookie", {})["session_cookie"] = "; ".join(
                            f"{k}={v}" for k,v in new_cookies.items()
                        )
                        _cfg_path.write_text(_json.dumps(_full_cfg, indent=2))
                        print(f"    ✅ config.json updated with fresh MyBookie cookies")
                except Exception as _ce:
                    print(f"    ⚠️  Could not update config.json: {_ce}")
                # Retry with new cookies
                new_cookie_str = "; ".join(f"{k}={v}" for k,v in new_cookies.items())
                headers["Cookie"] = new_cookie_str
                r = cf.get(
                    "https://engine.mybookie.ag/sports_api/leagues-lines",
                    params={"sport":cfg_s["sport"],"league":cfg_s["league"]},
                    headers=headers, impersonate="chrome124", timeout=15
                )
                if r.status_code in (401, 403):
                    print(f"    ❌ Still 403 after re-login — cf_clearance may need manual refresh")
                    print(f"    👉 Re-run the DevTools cookie grab from mybookie.ag and update config.json")
                    return props, True
                cookies = new_cookies
            else:
                print(f"    ❌ Auto re-login failed — manual cookie refresh required")
                print(f"    👉 Open mybookie.ag in Chrome → DevTools → Application → Cookies → copy cf_clearance + gamingstation_session into config.json")
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
            rp = cf.get(
                "https://engine.mybookie.ag/sports_api/props-market-list",
                params={"gameID":gid,"isLive":"false"},
                headers=headers, impersonate="chrome124", timeout=15
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
                                except Exception:
                                    pass
                except Exception as _e:
                    pass  # TODO: log _e

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
                except Exception: pass
                props.append({
                    "Player": player, "Prop": mname,
                    "Line": float(str(line).replace("+","")),
                    "Side": side or "OVER",
                    "OverOdds": str(over) if over else "—",
                    "UnderOdds": str(under) if under else "—",
                    "Book": book, "Sport": sport,
                    "source": f"{book.lower()}_auto"
                })
    except Exception: pass
    return props

def scrape_dk_pick6(sport, cookies=None):
    """
    DraftKings Pick6 DFS props via curl_cffi — no login, no Playwright.
    Hits the public projections API directly.
    """
    print(f"\n  DraftKings Pick6 {sport}:")
    props = []

    sport_map = {
        "NBA":  "NBA",
        "MLB":  "MLB",
        "NHL":  "NHL",
        "NFL":  "NFL",
        "WNBA": "WNBA",
    }
    sp = sport_map.get(sport, sport)

    endpoints = [
        f"https://pick6.draftkings.com/api/v1/players?sport={sp}",
        f"https://pick6.draftkings.com/api/v1/lineup/{sp}",
        f"https://pick6.draftkings.com/api/v1/projections?sport={sp}",
        f"https://pick6.draftkings.com/api/v2/players?sport={sp}&includeProjections=true",
    ]

    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
        headers = {
            "User-Agent": UA,
            "Referer":    "https://pick6.draftkings.com/",
            "Origin":     "https://pick6.draftkings.com",
            "Accept":     "application/json, text/plain, */*",
        }

        for url in endpoints:
            try:
                r = session.get(url, headers=headers, timeout=15)
                print(f"    {url[-55:]}: {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    parsed = parse_pick6_response(data, sport)
                    if parsed:
                        print(f"    ✅ {len(parsed)} props")
                        props.extend(parsed)
                        break  # got data, stop trying endpoints
            except Exception as _e:
                continue

    except ImportError:
        print("    curl_cffi not installed — pip install curl_cffi")
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
                        "Prop":      stat_type,
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
                            "Prop": stat_type,
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


def scrape_betr(sport):
    """Betr Picks via GraphQL — no auth needed."""
    print(f"\n  Betr {sport} (GraphQL):")
    props = []
    league_map = {"NBA": "NBA", "MLB": "MLB", "NHL": "NHL", "WNBA": "WNBA", "NFL": "NFL"}
    league = league_map.get(sport)
    if not league:
        return props

    query = """query LeagueUpcomingEvents($league: League!) {
      getUpcomingEventsV2(league: $league) {
        name sport league
        ... on TeamVersusEvent {
          teams { name players { firstName lastName position
            projections { name label value currentValue type
              allowedOptions { outcome marketOptionId }
            }
          }}
        }
        ... on IndividualVersusEvent {
          players { firstName lastName position
            projections { name label value currentValue type
              allowedOptions { outcome marketOptionId }
            }
          }
        }
      }
    }"""

    try:
        import requests as req
        r = req.post("https://api.fantasy.betr.app/graphql",
            json={"operationName": "LeagueUpcomingEvents", "query": query, "variables": {"league": league}},
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": UA}, timeout=12)
        print(f"    Status: {r.status_code}")
        if r.status_code != 200:
            return props

        events = r.json().get("data", {}).get("getUpcomingEventsV2", []) or []
        print(f"    Events: {len(events)}")

        for event in events:
            matchup = event.get("name", "")
            players_list = []
            for team in (event.get("teams") or []):
                if team and team.get("players"):
                    players_list.extend(team["players"])
            if event.get("players"):
                players_list.extend(event["players"])

            for player in players_list:
                if not player:
                    continue
                full_name = f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
                for proj in (player.get("projections") or []):
                    if not proj:
                        continue
                    line = proj.get("currentValue") or proj.get("value") or 0
                    prop_name = proj.get("label") or proj.get("name") or ""
                    props.append({
                        "Player": full_name, "Prop": prop_name,
                        "Line": float(line) if line else 0.0,
                        "Side": "OVER", "OverOdds": "—", "UnderOdds": "—",
                        "Book": "Betr", "Sport": sport,
                        "source": "betr_graphql",
                    })

        print(f"    Props: {len(props)}")
    except Exception as e:
        print(f"    Error: {e}")
    return props


NOVIG_QUERY = """query EventMarkets_Query($eventId: uuid, $marketVisibleWhere: market_bool_exp) @cached(ttl: 5) {
  event(where: {id: {_eq: $eventId}}) {
    id type league scheduled_start status
    markets(where: $marketVisibleWhere) {
      id strike type description status volume
      player { id full_name __typename }
      outcomes { id index description available altAvailable __typename }
      __typename
    }
    __typename
  }
}"""

def scrape_novig(sport):
    """Novig props via GraphQL + live event ticker. No auth needed."""
    print(f"\n  Novig {sport} (GraphQL):")
    props = []
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        session = requests

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://novig.com",
        "Referer": "https://novig.com/",
        "User-Agent": UA,
    }

    league_map = {"NBA": "NBA", "MLB": "MLB", "NHL": "NHL", "WNBA": "WNBA", "NFL": "NFL"}
    target_league = league_map.get(sport, "NBA")

    try:
        # Step 1: Get all events from ticker
        r1 = session.get(
            "https://api.novig.us/nbx/v1/live-event-ticker",
            params={"liveLeagues": "NFL,NBA,MLB,NHL,NCAAF,NCAAB,WNBA"},
            headers=headers, timeout=15
        )
        print(f"    Ticker: {r1.status_code}")
        if r1.status_code != 200:
            return props

        ticker = r1.json()
        all_events = ticker.get("liveEvents", []) + ticker.get("upcomingEvents", [])
        sport_events = [e for e in all_events if e.get("league") == target_league]
        print(f"    {target_league} events: {len(sport_events)}")

        # Step 2: Get props for each event via GraphQL
        for ev in sport_events[:10]:
            eid = ev.get("id")
            if not eid:
                continue

            payload = {
                "operationName": "EventMarkets_Query",
                "variables": {
                    "eventId": eid,
                    "marketVisibleWhere": {
                        "_and": [
                            {"status": {"_eq": "OPEN"}},
                            {"_or": [
                                {"is_consensus": {"_eq": True}},
                                {"outcomes": {"available": {"_is_null": False}}}
                            ]}
                        ]
                    }
                },
                "query": NOVIG_QUERY
            }

            r2 = session.post(
                "https://api.novig.us/v1/graphql",
                json=payload, headers=headers, timeout=15
            )
            if r2.status_code != 200:
                continue

            data = r2.json()
            events = data.get("data", {}).get("event", [])

            for event in events:
                for mkt in event.get("markets", []):
                    player_data = mkt.get("player")
                    if not player_data:
                        continue  # Skip game lines, only want player props

                    player_name = player_data.get("full_name", "")
                    prop_type = mkt.get("type", "")
                    strike = mkt.get("strike")
                    outcomes = mkt.get("outcomes", [])

                    if not player_name or strike is None:
                        continue

                    # Parse Over/Under from outcomes
                    # available = implied probability (not American odds)
                    over_prob, under_prob = None, None
                    for oc in outcomes:
                        desc = oc.get("description", "")
                        avail = oc.get("available") or oc.get("altAvailable")
                        if "Over" in desc:
                            over_prob = avail
                        elif "Under" in desc:
                            under_prob = avail

                    # Convert implied prob to American odds
                    def prob_to_american(p):
                        if p is None or p <= 0 or p >= 1:
                            return "\u2014"
                        if p >= 0.5:
                            return f"{int(-100 * p / (1 - p))}"
                        else:
                            return f"+{int(100 * (1 - p) / p)}"

                    over_odds = prob_to_american(over_prob)
                    under_odds = prob_to_american(under_prob)

                    # Map prop type to readable name
                    prop_name_map = {
                        "POINTS": "Points", "REBOUNDS": "Rebounds", "ASSISTS": "Assists",
                        "POINTS_REBOUNDS_ASSISTS": "Pts+Rebs+Asts",
                        "POINTS_REBOUNDS": "Pts+Rebs", "POINTS_ASSISTS": "Pts+Asts",
                        "REBOUNDS_ASSISTS": "Rebs+Asts",
                        "THREES": "3-Pt Made", "STEALS": "Steals", "BLOCKS": "Blocks",
                        "TURNOVERS": "Turnovers", "FANTASY": "Fantasy Score",
                        "STRIKEOUTS": "Strikeouts", "HITS_ALLOWED": "Hits Allowed",
                        "EARNED_RUNS": "Earned Runs", "TOTAL_BASES": "Total Bases",
                        "HITS": "Hits", "RUNS": "Runs", "RBIS": "RBIs",
                        "HOME_RUNS": "Home Runs", "STOLEN_BASES": "Stolen Bases",
                        "GOALS": "Goals", "SHOTS": "Shots", "SAVES": "Saves",
                        "PASSING_YARDS": "Pass Yds", "RUSHING_YARDS": "Rush Yds",
                        "RECEIVING_YARDS": "Rec Yds", "TOUCHDOWNS": "TDs",
                    }
                    prop_name = prop_name_map.get(prop_type, prop_type.replace("_", " ").title())

                    props.append({
                        "Player": player_name, "Prop": prop_name,
                        "Line": float(strike), "Side": "OVER",
                        "OverOdds": over_odds, "UnderOdds": under_odds,
                        "Book": "Novig", "Sport": sport,
                        "source": "novig_graphql",
                    })

            time.sleep(0.5)

        print(f"    Props: {len(props)}")
    except Exception as e:
        print(f"    Error: {e}")

    return props


def scrape_betrivers_curlffi(sport):
    """BetRivers props via Kambi API — no auth needed."""
    print(f"\n  BetRivers {sport} (curl_cffi):")
    props = []
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        print("    curl_cffi not installed")
        return props

    headers = {"User-Agent": UA, "Accept": "application/json",
               "Origin": "https://az.betrivers.com", "Referer": "https://az.betrivers.com/"}
    sport_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "ice_hockey/nhl",
                 "WNBA": "basketball/wnba", "NFL": "american_football/nfl"}
    kambi_sport = sport_map.get(sport, "basketball/nba")

    try:
        import random as _rand
        for _br_attempt in range(3):
            r1 = session.get(
                f"https://eu-offering-api.kambicdn.com/offering/v2/rvn/listView/{kambi_sport}/all/all.json",
                params={"lang": "en_US", "market": "US-AZ"},
                headers=headers, timeout=15)
            print(f"    Events: {r1.status_code}")
            if r1.status_code == 429:
                _wait = ((_br_attempt + 1) * 8) + _rand.uniform(2, 5)
                print(f"    Rate limited — waiting {_wait:.0f}s...")
                time.sleep(_wait)
                continue
            break
        if r1.status_code != 200: return props

        events = r1.json().get("events", [])
        print(f"    Found {len(events)} events")

        for ev in events[:10]:
            ev_id = ev.get("event", {}).get("id")
            if not ev_id: continue

            r2 = session.get("https://az.betrivers.com/api/service/sportsbook/offering/playerprops",
                params={"groupId": ev_id, "pageNr": 1, "pageSize": 200, "cageCode": 602},
                headers=headers, timeout=10)
            if r2.status_code != 200: continue

            items = r2.json().get("items", r2.json().get("offerings", []))
            if isinstance(items, dict): items = list(items.values())

            for item in items:
                criterion = item.get("criterion", {})
                prop_label = criterion.get("label", "")
                for oc in item.get("outcomes", []):
                    player = oc.get("participantName", "") or oc.get("label", "")
                    odds_am = oc.get("americanOdds") or oc.get("oddsAmerican")
                    line = oc.get("line") or oc.get("handicap") or oc.get("overUnder")
                    sd = "UNDER" if "UNDER" in (oc.get("type","") or "").upper() else "OVER"
                    if not player or line is None: continue
                    try: lf = float(str(line).replace("+",""))
                    except Exception: continue
                    od = f"{'+' if float(odds_am)>0 else ''}{int(float(odds_am))}" if odds_am else "—"
                    props.append({"Player": player, "Prop": prop_label, "Line": lf, "Side": sd,
                        "OverOdds": od if sd=="OVER" else "—", "UnderOdds": od if sd=="UNDER" else "—",
                        "Book": "BetRivers", "Sport": sport, "source": "betrivers_curlffi"})
            time.sleep(random.uniform(8, 15))
        print(f"    Props: {len(props)}")
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
        "NBA":  {"lid": "42648",    "sid": "16477"},
        "MLB":  {"lid": "84240",    "sid": "17319"},
        "NHL":  {"lid": "42133",    "sid": "11601"},
        "WNBA": {"lid": "92483",    "sid": "11839"},
        "NFL":  {"lid": "88670775", "sid": "10015"},
    }
    cfg_dk = league_map.get(sport, league_map["NBA"])
    lid = cfg_dk["lid"]
    sid = cfg_dk["sid"]

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
                mid = mkt.get("id") or mkt.get("marketId")
                # DK subcategory already filters to player props — no keyword filter needed
                for sel in sel_by_mkt.get(mid, []):
                    label = sel.get("label", "")
                    # Get player name from participants array
                    parts = sel.get("participants", [])
                    player = parts[0].get("name","") if parts else ""
                    if not player:
                        player = label
                    odds_am = sel.get("displayOdds",{}).get("american","—")
                    # Extract line from label (DK puts it in "Over 18.0" format)
                    import re as _re
                    line = sel.get("points") or sel.get("line")
                    if line is None:
                        _lm = _re.search(r"(\d+\.?\d*)", label)
                        if _lm:
                            line = float(_lm.group(1))
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
                            except Exception: pass
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


def load_caesars_tokens_from_gist(token, gist_id):
    """Read the Caesars bearer_jwt/waf_token pushed by caesars-harvester-cdp.js.
    This standalone script previously only ever wrote to the Gist (props
    push), never read from it — that's the actual gap that left this
    function's auth headers empty even after the harvester started working
    in app.py, since that fix never touched this separate code path."""
    if not token or not gist_id:
        return None
    try:
        r = requests.get(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
            timeout=10
        )
        if r.status_code != 200:
            return None
        files = r.json().get("files", {})
        file_data = files.get("betcouncil_caesars_tokens.json", {})
        content = (file_data.get("content") or "").strip()
        if not content:
            # Same cross-file truncation issue fixed in app.py's load_from_gist
            # on 2026-06-21 — fall back to raw_url if bulk content is empty.
            raw_url = file_data.get("raw_url", "")
            if not raw_url:
                return None
            raw_resp = requests.get(raw_url, headers={"Authorization": f"token {token}"}, timeout=15)
            if raw_resp.status_code != 200:
                return None
            content = raw_resp.text.strip()
            if not content:
                return None
        return json.loads(content)
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def scrape_caesars_curlffi(sport, token="", gist_id=""):
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

    czr_tokens = load_caesars_tokens_from_gist(token, gist_id)
    if czr_tokens and czr_tokens.get("bearer_jwt"):
        headers["authorization"] = f"Bearer {czr_tokens['bearer_jwt']}"
        headers["sessionid"] = czr_tokens["bearer_jwt"]
        if czr_tokens.get("waf_token"):
            headers["x-aws-waf-token"] = czr_tokens["waf_token"]
        print("    Using harvested Caesars session token from Gist")
    else:
        print("    No Caesars token in Gist — run caesars-harvester-cdp.js first")

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
                        except Exception: continue
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


def scrape_betrivers_curlffi(sport):
    """BetRivers props via Kambi API + curl_cffi."""
    print(f"\n  BetRivers {sport} (curl_cffi):")
    props = []
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        print("    curl_cffi not installed")
        return props

    headers = {"User-Agent": UA, "Accept": "application/json",
               "Origin": "https://az.betrivers.com", "Referer": "https://az.betrivers.com/"}
    sport_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "ice_hockey/nhl",
                 "WNBA": "basketball/wnba", "NFL": "american_football/nfl"}
    kambi_sport = sport_map.get(sport, "basketball/nba")

    try:
        r1 = None
        for attempt in range(3):
            r1 = session.get(
                f"https://eu-offering-api.kambicdn.com/offering/v2/rvn/listView/{kambi_sport}/all/all/matches.json",
                params={"lang": "en_US", "market": "US-AZ"}, headers=headers, timeout=15)
            if r1.status_code != 429:
                break
            # 429s observed specifically on WNBA when --all scrapes NBA/MLB/NHL/
            # WNBA back-to-back with no delay between sports — all four hit this
            # same Kambi host in quick succession, and by WNBA's turn (last in
            # the list) the cumulative request rate trips the limit. Retrying
            # with backoff is more robust than reordering sports or adding a
            # blind static delay, since it self-corrects regardless of which
            # sport happens to be last or how many books run before it.
            wait_s = 5 * (attempt + 1)
            print(f"    Events: 429, retrying in {wait_s}s (attempt {attempt + 1}/3)...")
            time.sleep(wait_s)
        print(f"    Events: {r1.status_code}")
        if r1.status_code != 200: return props

        events = r1.json().get("events", [])
        print(f"    Found {len(events)} events")
        for ev in events[:8]:
            ev_id = ev.get("event", {}).get("id")
            if not ev_id: continue
            r2 = session.get("https://az.betrivers.com/api/service/sportsbook/offering/playerprops",
                params={"groupId": ev_id, "pageNr": 1, "pageSize": 200, "cageCode": 602},
                headers=headers, timeout=10)
            if r2.status_code != 200: continue
            items = r2.json().get("items", r2.json().get("offerings", []))
            if isinstance(items, dict): items = list(items.values())
            for item in items:
                player = (item.get("participant", {}).get("name", "") or item.get("playerName", "") or item.get("name", ""))
                mname = item.get("criterion", {}).get("label", "") or item.get("marketName", "")
                for oc in item.get("outcomes", item.get("betOffers", [])):
                    label = oc.get("label", "") or oc.get("type", "")
                    line = oc.get("line") or oc.get("overUnderLine") or oc.get("handicap")
                    odds_am = oc.get("oddsAmerican") or oc.get("americanOdds")
                    if line is not None:
                        lf = float(str(line).replace("+",""))
                        if lf > 100: lf = lf / 1000
                    else: continue
                    sd = "UNDER" if "under" in label.lower() else "OVER"
                    od = "\u2014"
                    if odds_am is not None: od = f"{'+' if int(odds_am)>0 else ''}{int(odds_am)}"
                    if player:
                        props.append({"Player": player, "Prop": mname, "Line": lf, "Side": sd,
                            "OverOdds": od if sd=="OVER" else "\u2014",
                            "UnderOdds": od if sd=="UNDER" else "\u2014",
                            "Book": "BetRivers", "Sport": sport, "source": "betrivers_curlffi"})
            time.sleep(0.3)
        print(f"    Props: {len(props)}")
    except Exception as e:
        print(f"    Error: {e}")
    return props



def _mgm_odds(odds):
    if odds is None:
        return "—"
    try:
        o = float(odds)
        return f"+{int(o)}" if o > 0 else str(int(o))
    except Exception:
        return "—"

def scrape_betmgm_curlffi(sport):
    """BetMGM props via fixture-offers with gameIds from fixtures list."""
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

    US_TEAMS = {"knicks","spurs","celtics","lakers","warriors","heat","bucks","nets",
        "suns","mavericks","nuggets","clippers","pacers","76ers","cavaliers","hawks",
        "bulls","grizzlies","pelicans","rockets","thunder","timberwolves","blazers",
        "kings","raptors","wizards","pistons","hornets","magic","jazz",
        "yankees","red sox","mets","dodgers","cubs","astros","braves","padres",
        "phillies","orioles","rays","guardians","twins","mariners","tigers",
        "diamondbacks","marlins","reds","brewers","royals","pirates","rockies",
        "cardinals","giants","angels","athletics","nationals","rangers","white sox",
        "bruins","maple leafs","avalanche","oilers","panthers","hurricanes",
        "stars","lightning","devils","islanders","penguins","capitals","predators",
        "aces","storm","liberty","fever","sky","sun","mystics","dream","mercury",
        "sparks","lynx","wings","valkyries","fire"}

    try:
        # Step 1: Get fixtures with their game IDs
        r1 = session.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixtures",
            params={"x-bwin-accessid": MGM_KEY, "lang": "en-us", "country": "US",
                    "userCountry": "US", "subdivision": "US-AZ", "offerMapping": "Filtered",
                    "sportIds": sid, "fixtureTypes": "Standard", "state": "Latest",
                    "skip": 0, "take": 30, "sortBy": "StartDate"},
            headers=headers, timeout=15)
        print(f"    Fixtures: {r1.status_code}")
        if r1.status_code != 200:
            return props

        fixtures = r1.json().get("fixtures", [])
        us_fixtures = [f for f in fixtures if any(t in str(
            f.get("name",{}).get("value","") if isinstance(f.get("name"),dict) else f.get("name","")
        ).lower() for t in US_TEAMS)]
        print(f"    Total: {len(fixtures)} | US: {len(us_fixtures)}")

        # Step 2: For each US fixture, get game IDs then fetch fixture-offers WITH gameIds
        for fix in us_fixtures[:8]:
            fix_id = fix.get("id")
            if not fix_id:
                continue

            # Get game IDs from the fixture's optionMarkets and games
            game_ids = []
            for g in fix.get("games", []):
                gid = g.get("id")
                if gid:
                    game_ids.append(str(gid))
            for om in fix.get("optionMarkets", []):
                omid = om.get("id")
                if omid:
                    game_ids.append(str(omid))

            fname = fix.get("name",{}).get("value","") if isinstance(fix.get("name"),dict) else fix.get("name","")
            print(f"    {fname}: {len(game_ids)} gameIds")

            if not game_ids:
                continue

            # Hit fixture-offers WITH gameIds
            r2 = session.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixture-offers",
                params={"x-bwin-accessid": MGM_KEY, "lang": "en-us", "country": "US",
                        "userCountry": "US", "subdivision": "US-AZ",
                        "fixtureIds": fix_id,
                        "gameIds": ",".join(game_ids[:20]),
                        "offerMapping": "Filtered"},
                headers=headers, timeout=10)

            if r2.status_code != 200:
                print(f"      offers: {r2.status_code}")
                continue

            data = r2.json()
            print(f"      offers: {r2.status_code} ({len(r2.text)} bytes)")

            # Navigate: fixtureOffers (fixture-offers response) or fixture/fixtures
            fx_list = []
            if "fixtureOffers" in data:
                # fixtureOffers is the actual data — may be list of game groups
                fo = data["fixtureOffers"]
                if isinstance(fo, list):
                    fx_list = fo
                elif isinstance(fo, dict):
                    fx_list = [fo]
                print(f"      fixtureOffers: {len(fx_list)} items")
                if fx_list:
                    _fo0 = fx_list[0]
                    print(f"      fo[0] keys: {list(_fo0.keys())[:10]}")
                    if isinstance(_fo0, dict):
                        for _fk, _fv in _fo0.items():
                            if isinstance(_fv, list) and _fv:
                                print(f"        {_fk}: list[{len(_fv)}]")
                                if isinstance(_fv[0], dict):
                                    print(f"          [0] keys: {list(_fv[0].keys())[:8]}")
                                    # Show first item name/value
                                    _n = _fv[0].get("name", "")
                                    if isinstance(_n, dict):
                                        _n = _n.get("value", "")
                                    if _n:
                                        print(f"          [0] name: {_n}")
                            elif isinstance(_fv, dict):
                                print(f"        {_fk}: dict keys={list(_fv.keys())[:6]}")
            elif "fixture" in data and isinstance(data["fixture"], dict):
                fx_list = [data["fixture"]]
            elif "fixtures" in data:
                fx_list = data["fixtures"]
            else:
                fx_list = [data]

            # Debug: show structure
            if fx_list:
                _fd0 = fx_list[0]
                print(f"      fx keys: {list(_fd0.keys())[:10]}")
                _g = _fd0.get("games", [])
                _om = _fd0.get("optionMarkets", [])
                print(f"      games: {len(_g)} | optionMarkets: {len(_om)}")
                if _g:
                    _g0 = _g[0]
                    _gname = _g0.get("name", "")
                    if isinstance(_gname, dict):
                        _gname = _gname.get("value", "")
                    _gres = _g0.get("results", [])
                    print(f"      game[0]: {_gname} | results: {len(_gres)}")
                    if _gres:
                        _r0 = _gres[0]
                        _rname = _r0.get("name", "")
                        if isinstance(_rname, dict):
                            _rname = _rname.get("value", "")
                        print(f"        result: {_rname} | attr: {_r0.get('attr','')} | odds: {_r0.get('americanOdds','')}")
                if _om:
                    _om0 = _om[0]
                    _omname = _om0.get("name", "")
                    if isinstance(_omname, dict):
                        _omname = _omname.get("value", "")
                    _omopts = _om0.get("options", [])
                    print(f"      optMkt[0]: {_omname} | options: {len(_omopts)}")
                    if _omopts:
                        _oo0 = _omopts[0]
                        _ooname = _oo0.get("name", "")
                        if isinstance(_ooname, dict):
                            _ooname = _ooname.get("value", "")
                        print(f"        opt: {_ooname} | attr: {_oo0.get('attr','')} | price: {_oo0.get('price',{}).get('americanOdds','')}")
            for fd in fx_list:
                for game in fd.get("games", []):
                    gn = game.get("name", {}).get("value", "") if isinstance(game.get("name"), dict) else game.get("name", "")
                    gn_upper = gn.upper()
                    SKIP = {"MONEYLINE","MONEY LINE","MATCH RESULT","DRAW NO BET"}
                    if any(s in gn_upper for s in SKIP):
                        continue
                    for res in game.get("results", []):
                        rn = res.get("name", {}).get("value", "") if isinstance(res.get("name"), dict) else res.get("name", "")
                        odds = res.get("americanOdds") or res.get("price", {}).get("americanOdds")
                        attr = res.get("attr", "")
                        pn, sd = rn, "OVER"
                        if " Over " in rn: pn, sd = rn.split(" Over ")[0].strip(), "OVER"
                        elif " Under " in rn: pn, sd = rn.split(" Under ")[0].strip(), "UNDER"
                        pl = res.get("player", {})
                        if isinstance(pl, dict) and pl.get("fullName"):
                            pn = pl["fullName"]
                        if not pn or not attr: continue
                        try: lf = float(str(attr).replace("+",""))
                        except Exception: continue
                        od = _mgm_odds(odds)
                        props.append({"Player": pn, "Prop": gn, "Line": lf, "Side": sd,
                            "OverOdds": od if sd=="OVER" else "\u2014",
                            "UnderOdds": od if sd=="UNDER" else "\u2014",
                            "Book": "BetMGM", "Sport": sport, "source": "betmgm_curlffi"})

                for mkt in fd.get("optionMarkets", []):
                    mn = mkt.get("name", {}).get("value", "") if isinstance(mkt.get("name"), dict) else mkt.get("name", "")
                    mn_upper = mn.upper()
                    SKIP2 = {"MONEYLINE","MONEY LINE","MATCH RESULT","DRAW NO BET","SPREAD"}
                    if any(s in mn_upper for s in SKIP2):
                        continue
                    for opt in mkt.get("options", []):
                        on = opt.get("name", {}).get("value", "") if isinstance(opt.get("name"), dict) else opt.get("name", "")
                        odds = opt.get("price", {}).get("americanOdds")
                        attr = opt.get("attr", "")
                        pn, sd = on, "OVER"
                        if " Over " in on: pn, sd = on.split(" Over ")[0].strip(), "OVER"
                        elif " Under " in on: pn, sd = on.split(" Under ")[0].strip(), "UNDER"
                        if not pn or not attr: continue
                        try: lf = float(str(attr).replace("+",""))
                        except Exception: continue
                        od = _mgm_odds(odds)
                        props.append({"Player": pn, "Prop": mn, "Line": lf, "Side": sd,
                            "OverOdds": od if sd=="OVER" else "\u2014",
                            "UnderOdds": od if sd=="UNDER" else "\u2014",
                            "Book": "BetMGM", "Sport": sport, "source": "betmgm_curlffi"})

            time.sleep(0.5)

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
                        except Exception:
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

def generate_brief_text(all_props, all_lines, sport=None):
    from datetime import date, datetime
    today = date.today().strftime('%A, %B %d, %Y')
    now   = datetime.now().strftime('%H:%M')
    sport = sport or 'MULTI'
    out   = []
    out.append('=== BETCOUNCIL GEM BRIEF ===')
    out.append(f'Sport: {sport}')
    out.append(f'Date: {today}')
    out.append(f'Generated: {now} (auto-scraper)')
    out.append('')

    def _edge_val(p):
        try: return float(str(p.get('Edge', p.get('edge', 0))).replace('%',''))
        except: return 0.0

    top = sorted(all_props, key=_edge_val, reverse=True)[:15]
    if top:
        out.append('=== TOP PROPS (MODE A READY) ===')
        for p in top:
            player  = p.get('Player',   p.get('player',   'Unknown'))
            stat    = p.get('Prop',     p.get('stat',     p.get('Stat', '')))
            side    = p.get('Side',     p.get('side',     ''))
            line    = p.get('Line',     p.get('line',     ''))
            book    = p.get('Book',     p.get('book',     p.get('source', '')))
            odds    = p.get('Odds',     p.get('odds',     ''))
            edge    = p.get('EdgePct',  p.get('edge_pct', f'{_edge_val(p):.1f}%'))
            prob    = p.get('Prob',     p.get('fair_prob',''))
            tier    = p.get('Tier',     p.get('tier',     ''))
            avg     = p.get('Avg',      p.get('avg',      ''))
            std_dev = p.get('StdDev',   p.get('std_dev',  ''))
            injury  = p.get('Injury',   p.get('injury',   ''))
            pin     = p.get('PinnacleProb', p.get('ConsensusProb', ''))
            sigs    = p.get('SignalCount',  p.get('signal_count',  ''))
            opp_def = p.get('OppDef',       p.get('opp_def',       ''))
            rest    = p.get('RestFlag',      p.get('rest_flag',     ''))
            log     = p.get('RecentLog',     p.get('recent_log',    ''))
            try:    prob_str = f"{float(prob):.1%}"
            except: prob_str = str(prob)
            try:    avg_str = f"{float(avg):.1f}"
            except: avg_str = str(avg)
            parts = [f"{(tier+': ') if tier else ""}{player} {side} {line} {stat}"]
            if book:    parts.append(f'@{book}{odds}')
            if avg_str: parts.append(f'Avg:{avg_str}')
            if std_dev: parts.append(f'σ:{std_dev}')
            if edge:    parts.append(f'Edge:{edge}')
            if prob_str:parts.append(f'Prob:{prob_str}')
            if pin:     parts.append(f'Pin:{pin}')
            if sigs:    parts.append(f'[{sigs}/7 signals]')
            if opp_def: parts.append(f'OppDef:{opp_def}')
            if rest:    parts.append(f'[{rest}]')
            if log:     parts.append(f'L5:{log}')
            if injury:  parts.append(f'⚠️ {injury}')
            out.append(' | '.join(parts))
        out.append('')

    if all_lines:
        out.append('=== GAME LINES ===')
        for g in all_lines[:10]:
            matchup = g.get('matchup', g.get('Matchup', ''))
            spread  = g.get('spread',  g.get('Spread',  ''))
            total   = g.get('total',   g.get('Total',   ''))
            gbook   = g.get('book',    g.get('Book',    ''))
            if matchup:
                out.append(f'{matchup} | Spread:{spread} Total:{total} @{gbook}')
        out.append('')

    injuries = {p.get('Player', p.get('player','')): p.get('Injury', p.get('injury',''))
                for p in all_props if p.get('Injury') or p.get('injury')}
    if injuries:
        out.append('=== INJURY FLAGS ===')
        for pl, st in injuries.items():
            out.append(f'{pl}: {st}')
        out.append('')

    out.append(f'Props: {len(all_props)} total | Lines: {len(all_lines)} games')
    out.append('=== END BRIEF — PASTE INTO GEM ===')
    return chr(10).join(out)

def push_to_gist(all_props, all_lines, token, gist_id):
    if not token or not gist_id:
        print("❌ No GitHub token/Gist ID")
        return False
    books   = list({p.get("Book", p.get("book", p.get("source", "Unknown"))) for p in all_props + all_lines})
    # Trim to stay under GitHub Gist 1MB limit
    max_props = 15000
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

    # Verify size before pushing — GitHub Gist file limit is ~1MB
    # Strip placeholder fields that waste bytes and are never used by app.py
    for _p in all_props:
        _p.pop("OverOdds", None)
        _p.pop("UnderOdds", None)
    payload_str = _json.dumps(payload)
    if len(payload_str) > 980000:
        payload["props"] = all_props[:15000]
        payload["lines"] = all_lines[:1000]
        payload_str = _json.dumps(payload)
    if len(payload_str) > 980000:
        payload["props"] = all_props[:10000]
        payload_str = _json.dumps(payload)
        print(f"  ⚠️  Trimmed to fit Gist limit: {len(payload['props'])} props")

    brief_text = generate_brief_text(all_props, all_lines)
    r = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {
            "auto_scraped_props.json": {
                "content": json.dumps(payload, indent=2)
            },
            "betcouncil_daily_brief.txt": {
                "content": brief_text
            }
        }},
        timeout=15
    )
    if r.status_code == 200:
        print(f"\n✅ Pushed to Gist: {len(all_props)} props + {len(all_lines)} lines")
        print(f"   Books: {', '.join(books)}")
        print(f"   📋 Brief pushed → betcouncil_daily_brief.txt")
        return True
    print(f"\n❌ Gist push failed: {r.status_code}")
    return False


# ── BetOnline Player Props (Playwright + sportcast API) ────────
# Resolution 2026-06-22: headed Chromium + --disable-blink-features=
# AutomationControlled + navigator.webdriver evasion bypasses bot
# detection. SPORTCAST_KEY is a global site constant embedded in raw
# HTML (confirmed via cloudscraper), fixtureId comes from the SGP
# iframe src rendered by headed Playwright. All downstream calls
# (getmarketsV2, Initialize, RequestBetPriceUI) hit plain requests —
# no browser needed after fixtureId is harvested.
#
# www.betonline.ag is Cloudflare-protected (confirmed via 403 testing —
# see BETONLINE_BASE comment in app.py), so the per-game "Key" that
# unlocks bl.widget-prod.sportcast.app/public/RequestBetPriceUI can't be
# pulled with plain requests. A real headless browser solves Cloudflare
# automatically, same as login_fanduel()/login_betmgm() above — no
# CF-specific code needed here, Playwright just handles it.
#
# Confirmed via live DevTools 2026-06-21: the key lives in the static
# rendered DOM, in <iframe id="SGP-EventView" src="https://bl.widget-prod
# .sportcast.app/markets?key=...&fixtureId=...">, inside the
# "panel-row eventView-sgp" SGP panel on every game page. It's the same
# key across reloads/different players (confirmed stable, not a
# short-lived token like Caesars' WAF token) — so this only needs to run
# once per game per day, not on a tight refresh loop.
#
# Game IDs come from the existing offering-by-league endpoint (no CF
# block, already used by scrape_betonline() above and
# fetch_betonline_lines() in app.py) — this also tests, for free, whether
# that GameId equals the fixtureId in the harvested iframe src.

# RESOLVED 2026-06-22 — headed Chromium with AutomationControlled disabled
# and navigator.webdriver patched renders the SGP iframe correctly.
# SPORTCAST_KEY is global (confirmed: same value across all game pages,
# embedded as SPORTCAST_KEY in the raw HTML config block). fixtureId comes
# from iframe#SGP-EventView src. All downstream sportcast calls use plain
# requests — no browser needed after fixtureId is in hand.
# ═══════════════════════════════════════════════════════════════

BETONLINE_GAME_URL = "https://www.betonline.ag/sportsbook/{sport_path}/{league_path}/game/{game_id}"
SPORTCAST_BASE = "https://bl.widget-prod.sportcast.app/public"
# Global BetOnline sportcast key — confirmed 2026-06-22 to be a static
# site-wide constant embedded in every game page's raw HTML config block
# (SPORTCAST_KEY field). Same value across all games, all sports. Extract
# fresh via cloudscraper if it ever changes (see _get_bo_sportcast_key).
_BO_SPORTCAST_KEY_CACHE = {"key": None, "fetched_at": 0}


def _get_bo_sportcast_key():
    """Return SPORTCAST_KEY, fetching fresh via cloudscraper if cache is stale (>6h)."""
    import time as _t
    if _BO_SPORTCAST_KEY_CACHE["key"] and _t.time() - _BO_SPORTCAST_KEY_CACHE["fetched_at"] < 21600:
        return _BO_SPORTCAST_KEY_CACHE["key"]
    try:
        import cloudscraper, re as _re
        scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        r = scraper.get("https://www.betonline.ag/sportsbook/baseball/mlb", timeout=20)
        m = _re.search(r'"SPORTCAST_KEY"\s*:\s*"([^"]+)"', r.text)
        if m:
            _BO_SPORTCAST_KEY_CACHE["key"] = m.group(1)
            _BO_SPORTCAST_KEY_CACHE["fetched_at"] = _t.time()
            return _BO_SPORTCAST_KEY_CACHE["key"]
    except Exception:
        pass
    # Hardcoded fallback — update if sportcast key ever rotates
    return "0f833f77-d3e2-476b-8484-141fccb8d8de"


def _bo_sportcast_headers(key, fixture_id):
    return {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": UA,
        "Referer": f"https://bl.widget-prod.sportcast.app/markets?key={key}&fixtureId={fixture_id}&odds=AmericanPrice&brand=betonline",
    }


def fetch_bo_markets(fixture_id, key):
    """Return list of all markets for this fixture from getmarketsV2 (marketLabel=0)."""
    try:
        r = requests.get(
            f"{SPORTCAST_BASE}/getmarketsV2/",
            params={"key": key, "fixtureId": fixture_id, "culture": "en-GB",
                    "returnFilters": "true", "marketLabel": 0},
            headers=_bo_sportcast_headers(key, fixture_id), timeout=12
        )
        if r.status_code != 200:
            return []
        data = r.json()
        return (data or {}).get("PayLoad") or []
    except Exception:
        return []


def fetch_bo_market_selections(fixture_id, key, market_id):
    """Return selections for a specific market (getmarketsV2 with marketLabel=market_id)."""
    try:
        r = requests.get(
            f"{SPORTCAST_BASE}/getmarketsV2/",
            params={"key": key, "fixtureId": fixture_id, "culture": "en-GB",
                    "returnFilters": "true", "marketLabel": market_id},
            headers=_bo_sportcast_headers(key, fixture_id), timeout=12
        )
        if r.status_code != 200:
            return []
        data = r.json()
        payload = (data or {}).get("PayLoad") or []
        # Debug: print raw structure
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                for k, v in first.items():
                    if isinstance(v, list) and v:
                        inner = v[0]
                        print(f"        .{k}[0] keys={list(inner.keys()) if isinstance(inner, dict) else type(inner).__name__}")
        # Selections live in Filter.Items, not Selections/BetSelections
        for market in (payload if isinstance(payload, list) else []):
            items = (market.get("Filter") or {}).get("Items") or []
            if items:
                return items
        return []
    except Exception as e:
        return []


def fetch_bo_initialize(fixture_id, key):
    """Fetch Initialize endpoint — returns full fixture data including selections."""
    try:
        r = requests.get(
            f"{SPORTCAST_BASE}/Initialize",
            params={"key": key, "fixtureId": fixture_id, "isConsumerId": "false"},
            headers=_bo_sportcast_headers(key, fixture_id), timeout=15
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def get_betonline_game_ids(sport="MLB"):
    """Today's BetOnline GameIds for a sport, via the un-blocked offering-by-league endpoint."""
    info = SPORT_MAP.get(sport, SPORT_MAP["MLB"])
    sport_path, league_path = info["sport"], info["league"]
    payload = {
        "Sport": sport_path, "League": league_path, "ScheduleText": None,
        "filterTime": 0, "type": "prematch",
        "sport": sport_path.capitalize(), "league": league_path,
    }
    headers = {
        "User-Agent": UA, "Accept": "application/json, text/plain",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json-patch+json",
        "gsetting": "bolnasite",
        "utc-offset": "420",
        "Origin": "https://www.betonline.ag", "Referer": "https://www.betonline.ag/",
    }
    try:
        r = requests.post("https://api-offering.betonline.ag/api/offering/Sports/offering-by-league",
                           headers=headers, json=payload, timeout=12)
        if r.status_code != 200:
            print(f"  ❌ offering-by-league returned status {r.status_code}: {r.text[:200]}")
            return []
        data = r.json()
        games_desc = ((data or {}).get("GameOffering", {}) or {}).get("GamesDescription", []) or []
        if not games_desc:
            print(f"  ⚠️  offering-by-league returned 200 but no games. "
                  f"Top-level keys: {list((data or {}).keys())}")
            return []
        out = []
        for gd in games_desc:
            g = gd.get("Game", {}) or {}
            gid = g.get("GameId")
            if gid:
                out.append({"game_id": gid, "home": g.get("HomeTeam",""), "away": g.get("AwayTeam","")})
        if not out:
            sample = games_desc[0]
            sample_game = sample.get("Game", {}) if isinstance(sample, dict) else None
            print(f"  ⚠️  Got {len(games_desc)} game entries but extracted 0 GameIds. "
                  f"Entry-level keys: {list(sample.keys()) if isinstance(sample, dict) else type(sample)}. "
                  f"'Game' sub-dict keys: {list(sample_game.keys()) if isinstance(sample_game, dict) else 'NO Game KEY'}")
        return out
    except Exception as e:
        print(f"  ❌ get_betonline_game_ids error: {e}")
        return []


def harvest_betonline_fixture_ids(sport="MLB", max_games=15):
    """
    Visit each BetOnline game page with a headed stealth Chromium browser,
    extract fixtureId from the SGP iframe src.

    Uses headed mode (headless=False) + --disable-blink-features=
    AutomationControlled + navigator.webdriver patch — confirmed working
    2026-06-22. SPORTCAST_KEY is global so we don't need it per game.

    Returns list of:
      {game_id, home, away, fixture_id, harvested_at}
    """
    info = SPORT_MAP.get(sport, SPORT_MAP["MLB"])
    games = get_betonline_game_ids(sport)[:max_games]
    if not games:
        print(f"  No BetOnline games found for {sport}")
        return []

    results = []
    try:
        from playwright.sync_api import sync_playwright
        from urllib.parse import urlparse, parse_qs
        import time as _t

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 800},
            )
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()

            for g in games:
                url = BETONLINE_GAME_URL.format(
                    sport_path=info["sport"], league_path=info["league"],
                    game_id=g["game_id"]
                )
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    iframe_el = page.wait_for_selector("iframe#SGP-EventView", timeout=30000)
                    src = iframe_el.get_attribute("src") or ""
                    qs = parse_qs(urlparse(src).query)
                    fixture_id = (qs.get("fixtureId") or [None])[0]
                    if fixture_id:
                        results.append({
                            "game_id":      g["game_id"],
                            "home":         g["home"],
                            "away":         g["away"],
                            "fixture_id":   fixture_id,
                            "harvested_at": datetime.now().isoformat(),
                        })
                        print(f"  ✅ {g['away']} @ {g['home']}: fixtureId={fixture_id}")
                    else:
                        print(f"  ⚠️  {g['away']} @ {g['home']}: iframe found but no fixtureId in src")
                except Exception as e:
                    print(f"  ⚠️  {g['away']} @ {g['home']}: {str(e)[:120]}")
                _t.sleep(1.0)

            browser.close()
    except ImportError:
        print("  ❌ Playwright not installed. Run: pip install playwright && python -m playwright install chromium")
    except Exception as e:
        print(f"  ❌ harvest_betonline_fixture_ids error: {e}")

    return results


def scrape_betonline_props(sport="MLB", max_games=15):
    """
    Full BetOnline player prop pipeline:
      1. Headed Playwright → fixtureId per game
      2. Plain requests → getmarketsV2 → player market list
      3. Plain requests → Initialize → selections + entity IDs
      4. Plain requests → RequestBetPriceUI → price per selection
    Returns list of prop dicts in standard BetCouncil format.
    """
    print(f"\n  Harvesting BetOnline fixtureIds for {sport}...")
    game_fixtures = harvest_betonline_fixture_ids(sport, max_games)
    if not game_fixtures:
        print(f"  No fixtureIds harvested for {sport}")
        return []

    key = _get_bo_sportcast_key()
    props = []
    sport_code = {"MLB": 9}.get(sport)

    for gf in game_fixtures:
        fixture_id = gf["fixture_id"]
        home, away = gf["home"], gf["away"]
        print(f"\n  {away} @ {home} (fixtureId={fixture_id})")

        # Get all markets
        markets = fetch_bo_markets(fixture_id, key)
        player_markets = [m for m in markets if m.get("IsPlayerMarket")]
        print(f"    {len(player_markets)} player markets found")

        # Get Initialize data — contains selections per market
        init_data = fetch_bo_initialize(fixture_id, key)
        if init_data:
            pl = init_data.get("PayLoad") or {}
            if isinstance(pl, dict):
                for k, v in pl.items():
                    if isinstance(v, list):
                        print(f"      .{k}: list[{len(v)}]", end="")
                        if v and isinstance(v[0], dict):
                            print(f" first keys={list(v[0].keys())[:8]}")
                        else:
                            print()
            elif isinstance(pl, list):
                if pl and isinstance(pl[0], dict):
                    print(f"      first keys={list(pl[0].keys())[:8]}")
        init_payload = (init_data or {}).get("PayLoad") or {}

        for market in player_markets:
            if market.get("LabelId") == 226:  # Batter Props: 3-level hierarchy, skip for now
                continue
            market_id = market.get("Id")
            market_name = market.get("Label", "")
            market_label_id = market.get("LabelId")
            if not market_id:
                continue

            # Get selections for this market
            selections = fetch_bo_market_selections(fixture_id, key, market_label_id or market_id)
            if not selections:
                # Try to find selections in Initialize payload
                init_markets = init_payload.get("Markets") or []
                for im in init_markets:
                    if im.get("Id") == market_id or im.get("LabelId") == market_label_id:
                        selections = im.get("Selections") or im.get("BetSelections") or []
                        break

            if not selections:
                print(f"    ⚠️  No selections for {market_name}")
                continue

            print(f"    {market_name}: {len(selections)} selections")

            for sel in selections:
                sel_id = sel.get("Id")
                # Value is "Kerry Carpenter (DET)" — strip team suffix
                raw_name = sel.get("Value") or sel.get("Name") or sel.get("Label", "")
                sel_name = raw_name.split(" (")[0].strip() if " (" in raw_name else raw_name
                entity_id = sel.get("EntityId")
                global_id_long = sel.get("GlobalIdLong")
                global_id_short = sel.get("GlobalIdShort")
                if not sel_id or not sport_code:
                    continue

                # Price via RequestBetPriceUI
                import random as _r, string as _s
                op_id = ''.join(_r.choices(_s.ascii_letters + _s.digits, k=8))
                req_id = ''.join(_r.choices(_s.ascii_letters + _s.digits, k=6))
                payload = {
                    "FixtureId": int(fixture_id),
                    "Key": key,
                    "Sport": sport_code,
                    "MarketDetails": [{
                        "MarketId": market_id,
                        "MarketName": market.get("UntranslatedLabel", market_name),
                        "MarketLabelId": market_label_id,
                        "AllowOrCombo": False,
                        "BetSelections": [{
                            "Id": sel_id,
                            "Selection": sel.get("Value", sel_name),
                            "EntityId": entity_id,
                            "GlobalIdLong": global_id_long,
                            "GlobalIdShort": global_id_short,
                        }],
                    }],
                    "ReturnBetSlip": False,
                    "ReturnValidationMatrix": False,
                    "Culture": "en-GB",
                    "ReturnAllTranslations": False,
                    "ReturnMarkets": False,
                }
                price_headers = {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Referer": f"https://bl.widget-prod.sportcast.app/markets?key={key}&fixtureId={fixture_id}&odds=AmericanPrice&brand=betonline",
                    "http-loader": "false",
                    "request-id": f"|{op_id}.{req_id}",
                    "sc-fixtureid": str(fixture_id),
                    "sc-sportid": {"MLB": "Baseball"}.get(sport, sport),
                    "User-Agent": UA,
                }
                try:
                    pr = requests.post(
                        "https://bl.widget-prod.sportcast.app/public/RequestBetPriceUI",
                        headers=price_headers, json=payload, timeout=10
                    )
                    if pr.status_code != 200:
                        continue
                    pd_ = pr.json()
                    pl = (pd_ or {}).get("PayLoad") or {}
                    price = pl.get("Price")
                    if price in (None, "Infinity", 0, "0"):
                        continue
                    details = pl.get("PriceDetails") or {}
                    american = details.get("AmericanPrice")
                    if not american:
                        continue
                    props.append({
                        "book":        "BetOnline",
                        "sport":       sport,
                        "home":        home,
                        "away":        away,
                        "player":      sel_name,
                        "market":      market_name,
                        "line":        None,
                        "over_odds":   american if american > 0 else None,
                        "under_odds":  american if american < 0 else None,
                        "american_odds": american,
                        "fixture_id":  fixture_id,
                        "market_id":   market_id,
                        "selection_id": sel_id,
                    })
                except Exception as _pe:
                    continue

    print(f"\n  BetOnline props total: {len(props)}")
    return props


def push_betonline_props(props_data, token, gist_id):
    """Push scraped BetOnline props to Gist (betonline_props.json)."""
    if not token or not gist_id or not props_data:
        return False
    payload = {
        "scraped_at": datetime.now().isoformat(),
        "props": props_data,
    }
    r = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        json={"files": {"betonline_props.json": {"content": json.dumps(payload, indent=2)}}},
        timeout=15
    )
    if r.status_code == 200:
        print(f"\n✅ Pushed {len(props_data)} BetOnline props to Gist")
        return True
    print(f"\n❌ BetOnline props Gist push failed: {r.status_code}")
    return False


# ── Main ──────────────────────────────────────────────────────
# ── VSiN Intelligence Layer ───────────────────────────────────────────────────
# Scrapes VSiN data.vsin.com for:
#   - Vegas line tracker (8 books, opening+current lines, RLM detection)
#   - Betting splits (handle % + bet % for spread/ML/total)
#   - Makinen daily ratings (score proj, eff runs, starter/bullpen grade)
#   - Team summary (season ATS/ML/OU ROI per team)
#   - DK handle splits (DraftKings-sourced, sorted by handle)
#   - Makinen power ratings (all 30 teams ranked PR/ER/SP/BP)

def fetch_vsin_intelligence(sport="MLB", token=None, gist_id=None):
    """
    Run all VSiN scrapers in parallel and push results to Gist.
    Returns unified vsin_data dict.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    try:
        from vsin_scraper import VSiNScraper, merge_lines_and_splits
    except ImportError:
        print("    VSiN: vsin_scraper.py not found — skipping")
        return {}

    try:
        from vsin_extended import VSiNExtended, team_trend_signal
    except ImportError:
        print("    VSiN: vsin_extended.py not found — skipping extended")
        VSiNExtended = None

    try:
        from vsin_picks_and_ratings import VSiNPicksAndRatings, power_ratings_lookup
    except ImportError:
        print("    VSiN: vsin_picks_and_ratings.py not found — skipping ratings")
        VSiNPicksAndRatings = None

    print(f"\n    VSiN Intelligence | {sport} | {datetime.now().strftime('%H:%M:%S')}")

    vsin_data = {
        "sport":         sport,
        "timestamp":     datetime.now().isoformat(),
        "lines":         [],
        "splits":        [],
        "merged":        [],
        "makinen":       [],
        "team_summary":  [],
        "dk_splits":     [],
        "power_ratings": [],
        "rlm_alerts":    [],
        "ats_signals":   {},
    }

    # --- Parallel fetch ---
    def _fetch_lines():
        try:
            s = VSiNScraper()
            lines = s.scrape_lines(sport)
            print(f"      Lines: {len(lines)} games")
            return lines
        except Exception as e:
            print(f"      Lines error: {e}")
            return []

    def _fetch_splits():
        try:
            s = VSiNScraper()
            splits = s.scrape_splits(sport)
            print(f"      Splits: {len(splits)} records")
            return splits
        except Exception as e:
            print(f"      Splits error: {e}")
            return []

    def _fetch_makinen():
        if VSiNExtended is None:
            return []
        try:
            ext = VSiNExtended()
            mak = ext.scrape_makinen(sport)
            print(f"      Makinen: {len(mak)} games")
            return mak
        except Exception as e:
            print(f"      Makinen error: {e}")
            return []

    def _fetch_team_summary():
        if VSiNExtended is None:
            return []
        try:
            ext = VSiNExtended()
            ts = ext.scrape_team_summary(sport)
            print(f"      Team summary: {len(ts)} teams")
            return ts
        except Exception as e:
            print(f"      Team summary error: {e}")
            return []

    def _fetch_dk_splits():
        if VSiNExtended is None:
            return []
        try:
            ext = VSiNExtended()
            dk = ext.scrape_dk_splits("spread_handle")
            print(f"      DK splits: {len(dk)} games")
            return dk
        except Exception as e:
            print(f"      DK splits error: {e}")
            return []

    def _fetch_power_ratings():
        if VSiNPicksAndRatings is None:
            return []
        try:
            pr = VSiNPicksAndRatings()
            ratings = pr.scrape_power_ratings(sport)
            print(f"      Power ratings: {len(ratings)} teams")
            return ratings
        except Exception as e:
            print(f"      Power ratings error: {e}")
            return []

    tasks = {
        "lines":         _fetch_lines,
        "splits":        _fetch_splits,
        "makinen":       _fetch_makinen,
        "team_summary":  _fetch_team_summary,
        "dk_splits":     _fetch_dk_splits,
        "power_ratings": _fetch_power_ratings,
    }

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                vsin_data[key] = future.result() or []
            except Exception as e:
                print(f"      VSiN {key} error: {e}")

    # --- Merge lines + splits ---
    if vsin_data["lines"] and vsin_data["splits"]:
        vsin_data["merged"] = merge_lines_and_splits(
            vsin_data["lines"], vsin_data["splits"]
        )
    else:
        vsin_data["merged"] = vsin_data["lines"]

    # --- Extract RLM alerts ---
    vsin_data["rlm_alerts"] = [
        g for g in vsin_data["merged"]
        if g.get("rlm", {}).get("rlm_detected")
    ]
    if vsin_data["rlm_alerts"]:
        print(f"      ⚡ RLM detected: {len(vsin_data['rlm_alerts'])} games")
        for g in vsin_data["rlm_alerts"]:
            rlm = g["rlm"]
            print(f"        {g['away_team']} @ {g['home_team']} — "
                  f"{rlm['rlm_strength']} toward {rlm['rlm_direction']} "
                  f"({rlm['public_pct_vs_line']}% public)")

    # --- ATS signals from team summary ---
    if vsin_data["team_summary"] and VSiNExtended:
        signals = [team_trend_signal(t) for t in vsin_data["team_summary"]]
        vsin_data["ats_signals"] = {
            "ats_hot":    [s["team"] for s in signals if s["ats_hot"]],
            "ats_cold":   [s["team"] for s in signals if s["ats_cold"]],
            "over_lean":  [s["team"] for s in signals if s["ou_lean"] == "over"],
            "under_lean": [s["team"] for s in signals if s["ou_lean"] == "under"],
        }

    # --- Push to Gist ---
    if token and gist_id:
        _push_vsin_to_gist(vsin_data, token, gist_id)

    print(f"    VSiN: {len(vsin_data['merged'])} merged games, "
          f"{len(vsin_data['rlm_alerts'])} RLM alerts, "
          f"{len(vsin_data['power_ratings'])} teams rated")

    return vsin_data


def _push_vsin_to_gist(vsin_data, token, gist_id):
    """Push VSiN intelligence to dedicated Gist key: vsin_intelligence.json"""
    try:
        payload_str = json.dumps(vsin_data, indent=2)
        # Trim if over 900KB
        if len(payload_str) > 900000:
            vsin_data["makinen"] = vsin_data["makinen"][:20]
            vsin_data["merged"]  = vsin_data["merged"][:50]
            payload_str = json.dumps(vsin_data, indent=2)

        r = requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"files": {"vsin_intelligence.json": {"content": payload_str}}},
            timeout=15,
        )
        if r.status_code == 200:
            print(f"    ✅ VSiN pushed to Gist ({len(payload_str)//1024}KB)")
        else:
            print(f"    ❌ VSiN Gist push failed: {r.status_code}")
    except Exception as e:
        print(f"    ❌ VSiN Gist push error: {e}")



def main():
    parser = argparse.ArgumentParser(description="BetCouncil Auto Scraper v2.0")
    parser.add_argument("--sport",   default="NBA")
    parser.add_argument("--all",     action="store_true")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--books",   default="", help="Comma-separated: dk,fd,mgm,czr,mb,bo,pp,ud,sl,bov")
    parser.add_argument("--betonline-props", action="store_true",
                         help="Harvest BetOnline player-prop widget keys (Cloudflare-gated, needs real browser) and exit")
    parser.add_argument("--max-games", type=int, default=15, help="Max games to harvest per sport (--betonline-props only)")
    args = parser.parse_args()

    cfg    = load_config()
    token  = cfg.get("github_token","")
    gist   = cfg.get("gist_id","")
    sports = ["NBA","MLB","NHL","WNBA","NFL"] if args.all else [args.sport]

    # Season gate — skip off-season sports when --all is used
    if args.all:
        cur_month = datetime.now().month
        in_season = [s for s in sports if cur_month in SEASON_ACTIVE_MONTHS.get(s, list(range(1,13)))]
        shelved   = [s for s in sports if s not in in_season]
        if shelved:
            print(f"\n⏸  Off-season — shelving: {', '.join(shelved)} (month {cur_month})")
        sports = in_season

    if args.betonline_props:
        _bol_props, _bol_lines = [], []
        for sp in sports:
            print(f"\n{'='*50}\nScraping BetOnline props: {sp}\n{'='*50}")
            try:
                from betonline_props_scraper import scrape_betonline_all
                sp_props, sp_lines = scrape_betonline_all(sp)
                _bol_props.extend(sp_props)
                _bol_lines.extend(sp_lines)
                print(f"  {sp}: {len(sp_props)} props, {len(sp_lines)} lines")
            except Exception as _e:
                print(f"  {sp}: error — {_e}")
        print(f"\nTotal: {len(_bol_props)} props, {len(_bol_lines)} lines")
        if (_bol_props or _bol_lines) and not args.no_push:
            push_to_gist(_bol_props, _bol_lines, token, gist)
        elif _bol_props:
            print(json.dumps(_bol_props[:5], indent=2))
        return

    # Determine which books to scrape
    book_filter = [b.strip().lower() for b in args.books.split(",")] if args.books else []
    def use(book): return not book_filter or book in book_filter

    # Login to regulated books once (session reused across sports)
    sessions = {}
    login_map = {
        # "draftkings": ("dk",  login_draftkings),  # Not needed — curl_cffi works without auth
        # "fanduel":    ("fd",  login_fanduel),  # WAF blocks curl_cffi anyway
        # "betmgm":     ("mgm", login_betmgm),  # curl_cffi works without auth
        # "caesars":    ("czr", login_caesars),  # WAF blocks anyway
        "mybookie":   ("mb",  login_mybookie),
    }
    for book, (short, login_fn) in login_map.items():
        # Skip MyBookie Playwright login if session_cookie provided
        if book == "mybookie" and cfg.get("mybookie", {}).get("session_cookie"):
            print(f"\nUsing MyBookie session cookie from config (skipping browser login)")
            mb_cookie_str = cfg["mybookie"]["session_cookie"]
            mb_cookies = {}
            for part in mb_cookie_str.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    mb_cookies[k.strip()] = v.strip()
            sessions["mybookie"] = mb_cookies
            continue
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
        # --- PARALLEL BOOK FETCHING (PrizePicks, Underdog, Novig, Betr, DK) ---
        _parallel_books = {}
        if use("pp") and cfg.get("prizepicks",{}).get("enabled",True):
            _parallel_books["PrizePicks"] = scrape_prizepicks
        if use("ud") and cfg.get("underdog",{}).get("enabled",True):
            _parallel_books["Underdog"] = scrape_underdog
        if use("novig") or use("nv"):
            _parallel_books["Novig"] = scrape_novig
        if use("betr") or use("bt"):
            _parallel_books["Betr"] = scrape_betr
        if use("dk") or use("draftkings"):
            _parallel_books["DraftKings"] = scrape_draftkings_curlffi
        if _parallel_books:
            _par_results = fetch_books_parallel(sport, _parallel_books)
            all_props += _par_results

        # DraftKings Pick6 — DFS props (no login needed, curl_cffi)
        if use("dk") or use("pick6") or use("draftkings"):
            pick6_props = scrape_dk_pick6(sport)
            all_props += pick6_props

        # ParlayPlay — session cookie from config.json
        if use("parlayplay") or use("pp2") or args.all:
            pp2_props = scrape_parlayplay(sport)
            all_props += pp2_props

        if use("fd") or use("fanduel"):
            try:
                fd_props = scrape_fanduel_curlffi(sport)
                all_props += fd_props
            except Exception:
                print("    FanDuel: WAF blocked, skipping")

        if use("mgm") or use("betmgm"):
            mgm_props = scrape_betmgm_curlffi(sport)
            all_props += mgm_props

        if use("czr") or use("caesars"):
            try:
                czr_props = scrape_caesars_curlffi(sport, token, gist)
                all_props += czr_props
            except Exception:
                print("    Caesars: WAF blocked, skipping")

        if use("br") or use("betrivers"):
            br_props = scrape_betrivers_curlffi(sport)
            all_props += br_props

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

        # BetOnline props + lines — Playwright headed browser (Cloudflare bypass)
        # Opt-in only: requires --books bo or --books bol or --books betonline
        if "bo" in book_filter or "bol" in book_filter or "betonline" in book_filter:
            print(f"\n  BetOnline {sport} (Playwright):")
            try:
                from betonline_props_scraper import scrape_betonline_all
                bol_props, bol_lines = scrape_betonline_all(sport)
                all_props += bol_props
                all_lines += bol_lines
                print(f"    {len(bol_props)} props, {len(bol_lines)} lines")
            except Exception as _bol_e:
                print(f"    BetOnline error — {_bol_e}")

        time.sleep(1)

    # Summary
    print(f"\n{'='*50}")
    print(f"TOTAL: {len(all_props)} props + {len(all_lines)} lines")
    books_found = {p.get("Book", p.get("book", p.get("source", "Unknown"))) for p in all_props + all_lines}
    for book in sorted(books_found):
        count = len([x for x in all_props+all_lines if x.get("Book")==book])
        print(f"  {book:15} {count}")

    # Sample
    print("\nSample props:")
    for p in all_props[:5]:
        print(f"  {p.get('Book',p.get('book','?')):12} {p.get('Player','?'):25} {p.get('Prop','?'):20} {p.get('Line','?')}")

    # Push props
    if not args.no_push and (all_props or all_lines):
        push_to_gist(all_props, all_lines, token, gist)
    elif args.no_push:
        print("\nTest mode — not pushing")

    # VSiN Intelligence Layer
    print("\n── VSiN Intelligence ──")
    for sport in sports:
        fetch_vsin_intelligence(
            sport=sport,
            token=token if not args.no_push else None,
            gist_id=gist if not args.no_push else None,
        )

    print("\n✅ Done")


# ── EV API (20+ Books) ───────────────────────────────────────
# Module-level cache: fetch once per scraper run, reuse across all sport loops
_EV_API_CACHE = {"data": None, "ts": 0}
_EV_API_TTL = 120  # seconds


def fetch_ev_api(sport=None):
    """
    Fetch EV Sharps API data (module-level cached, max 1 fetch per 2 min).
    20+ books: DK, FD, HR, BetMGM, Caesars, ESPN, Circa, Pinnacle, Kalshi, Polymarket
    All sports: MLB, NBA, NFL
    ⚠️ UNSECURED: This API is currently public but unintended.
    Could be locked down at any time.
    """
    import time as _time
    now = _time.time()
    if _EV_API_CACHE["data"] is not None and (now - _EV_API_CACHE["ts"]) < _EV_API_TTL:
        print("    EV API: using cached data")
        return _EV_API_CACHE["data"]

    url = "https://api-production-3a3b.up.railway.app/api/ev"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            _EV_API_CACHE["data"] = data
            _EV_API_CACHE["ts"] = now
            print(f"    EV API: {len(data.get('data', []))} props fetched")
            return data
        else:
            print(f"    EV API: error {response.status_code}")
            return {"data": [], "games": [], "updated": {}}
    except requests.exceptions.Timeout:
        print("    EV API: timeout")
        return {"data": [], "games": [], "updated": {}}
    except Exception as e:
        print(f"    EV API: {e}")
        return {"data": [], "games": [], "updated": {}}


def _infer_sport_from_ev_item(item):
    """Infer sport from EV API item (no 'sport' field in response)."""
    prop = item.get("prop", "").lower()
    if prop in ("hr",):
        return "mlb"
    if prop in ("td", "rush_yards", "rec_yards", "receptions"):
        return "nfl"
    if prop in ("pts", "reb", "ast", "3pm", "stl", "blk"):
        return "nba"
    if prop in ("goals", "shots", "saves"):
        return "nhl"
    # Fallback: check game string for known team abbreviations (MLB default)
    return "mlb"


def _parse_ev_odds(raw):
    """
    Parse EV API bookOdds value into (over_odds, under_odds).
    Values are strings like '325', '+320', or '300/-595' (over/under split).
    Returns (str|None, str|None).
    """
    if raw is None:
        return None, None
    raw = str(raw).strip()
    if "/" in raw:
        parts = raw.split("/", 1)
        return parts[0].strip() or None, parts[1].strip() or None
    return raw or None, None


def extract_ev_props(ev_data, book_key="hr", sport_filter=None):
    """
    Extract props from EV API, mapped to BetCouncil format.
    book_key options: 'hr', 'dk', 'fd', 'mgm', 'cz', 'espn', 'circa', 'pn', 'bv'
    sport_filter: 'mlb', 'nba', 'nfl', 'nhl' or None for all
    """
    props = []
    for item in ev_data.get("data", []):
        if book_key not in item.get("bookOdds", {}):
            continue
        try:
            inferred_sport = _infer_sport_from_ev_item(item)
            if sport_filter and inferred_sport != sport_filter.lower():
                continue

            # FIX: bookOdds values are strings ("325") or "over/under" strings ("300/-595")
            # NOT dicts — the old book_odds.get("odds") was always raising AttributeError
            o_odds, u_odds = _parse_ev_odds(item["bookOdds"][book_key])

            # FIX: "line" in EV API = American odds integer for the best book
            # The actual stat threshold is in "handicap" (e.g. "0.5" for HR props)
            stat_line = item.get("handicap")
            try:
                stat_line = float(stat_line) if stat_line is not None else None
            except (ValueError, TypeError):
                stat_line = None

            prop = {
                "player": item.get("player", "Unknown"),
                "team": item.get("team", ""),
                "prop": item.get("prop", ""),
                "line": stat_line,          # stat threshold (e.g. 0.5 HRs)
                "o": o_odds,                # over American odds string
                "u": u_odds,                # under American odds string (or None)
                "book": f"EV_{book_key}",
                "sport": inferred_sport,
                "game": item.get("game", ""),
                "opp": item.get("opp", ""),
                "ev": item.get("ev"),
                "kelly": item.get("kelly"),
                "fair_value": item.get("fairVal"),
                "implied": item.get("implied"),
                "_source": "EV API",
                "_link": item.get("links", {}).get(book_key) if isinstance(item.get("links"), dict) else None,
                "_statcast": item.get("savant", {}),
                "_hit_rates": item.get("hitRates", {}),
                "_pitcher": item.get("pitcherData", {}),
                "_batter_percs": item.get("batter_percs", {}),
                "_stadium_rank": item.get("stadiumRank"),
                "_under": item.get("under", False),
            }
            props.append(prop)
        except Exception as e:
            print(f"    EV API: skipped item ({e})")
            continue

    if props:
        print(f"    EV API ({book_key}): {len(props)} props extracted")
    else:
        print(f"    EV API ({book_key}): 0 props — check book_key or API response")
    return props


def fetch_books_parallel(sport, book_fns):
    """Run multiple book scrapers in parallel. EV API fetched once at module level."""
    all_props = []

    # Fetch EV API once (cached) BEFORE the thread pool so it's not called per-sport
    ev_raw = fetch_ev_api()
    if ev_raw and ev_raw.get("data"):
        ev_props = extract_ev_props(ev_raw, book_key="hr", sport_filter=sport)
        if ev_props:
            all_props.extend(ev_props)
            print(f"    EV API: {len(ev_props)} Hard Rock props added for {sport}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fn, sport): name for name, fn in book_fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                if result:
                    all_props.extend(result)
            except Exception as e:
                print(f"    {name}: parallel fetch error: {e}")
    return all_props


if __name__ == "__main__":
    main()
