#!/usr/bin/env python3
"""Caesars token harvester — fixed login selectors based on actual page text."""
import os, sys, json, time, urllib.request, urllib.error
from datetime import datetime, timezone

EMAIL      = os.environ.get("CAESARS_EMAIL", "").strip()
PASSWORD   = os.environ.get("CAESARS_PASSWORD", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
STATE      = os.environ.get("CAESARS_STATE", "az").strip().lower()
MAX_WAIT   = int(os.environ.get("CAESARS_MAX_WAIT", "90"))

def log(msg): print(f"[harvest_caesars] {msg}", flush=True)
def die(msg): log(f"FATAL: {msg}"); sys.exit(1)

if not EMAIL:      die("CAESARS_EMAIL not set")
if not PASSWORD:   die("CAESARS_PASSWORD not set")
if not GIST_TOKEN: die("GIST_TOKEN not set")

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    die("playwright not installed")

try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    log("playwright-stealth not available")
    HAS_STEALTH = False

harvested = {}
_done = {"flag": False}

def _on_request(request):
    if _done["flag"]: return
    url = request.url
    if "americanwagering.com" not in url: return
    try:
        hdrs = request.all_headers()
    except Exception: return
    auth = hdrs.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) < 60: return
    harvested["bearer_jwt"]  = auth[len("Bearer "):]
    harvested["waf_token"]   = hdrs.get("x-aws-waf-token", "")
    harvested["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _done["flag"] = True
    log(f"✅ Bearer captured (len={len(harvested['bearer_jwt'])}, url={url[:80]})")

def snap(page, label):
    try:
        page.screenshot(path=f"/tmp/caesars_{label}.png")
        txt = page.inner_text("body")[:300].replace("\n", " ")
        log(f"[{label}] url={page.url[:80]} text={txt[:200]}")
    except Exception as e:
        log(f"snap failed ({label}): {e}")

log(f"Starting — state={STATE}")

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled",
              "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,800"],
    )
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        locale="en-US", timezone_id="America/New_York",
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = {runtime: {}};
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    """)
    page = ctx.new_page()
    if HAS_STEALTH: stealth_sync(page)
    page.on("request", _on_request)

    # 1. Navigate
    log(f"Navigating → https://sportsbook.caesars.com/us/{STATE}/bet")
    try:
        page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet",
                  wait_until="networkidle", timeout=45_000)
    except Exception as e:
        log(f"goto: {e}")
    time.sleep(3)
    snap(page, "01_landing")

    # 2. Dismiss banners
    for sel in ["button:has-text('Accept')", "button:has-text('OK')",
                 "[aria-label='close']", "button:has-text('No thanks')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible(): btn.click(); time.sleep(0.5)
        except Exception: pass

    # 3. Click LOG IN — actual text from page is "LOG IN" all caps
    login_clicked = False
    # Try text-exact match first, then broader selectors
    for sel in [
        "text='LOG IN'",
        "text='Log In'",
        "text='Login'",
        "button:has-text('LOG IN')",
        "a:has-text('LOG IN')",
        "[data-testid='login-button']",
        "[data-qa='login-button']",
        "button:has-text('Log In')",
        "a:has-text('Log In')",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                log(f"Clicked login: {sel}")
                login_clicked = True
                time.sleep(3)
                break
        except Exception as e:
            log(f"selector {sel} failed: {e}")

    if not login_clicked:
        # Last resort: find by evaluating all buttons/links for LOG IN text
        log("Trying JS click fallback...")
        try:
            page.evaluate("""
                () => {
                    const els = [...document.querySelectorAll('button, a, [role="button"]')];
                    const target = els.find(e => e.textContent.trim().toUpperCase().includes('LOG IN') ||
                                                 e.textContent.trim().toUpperCase().includes('LOGIN') ||
                                                 e.textContent.trim().toUpperCase() === 'SIGN IN');
                    if (target) { target.click(); return target.textContent; }
                    return null;
                }
            """)
            log("JS click executed")
            time.sleep(3)
        except Exception as e:
            log(f"JS click failed: {e}")

    snap(page, "02_after_login_click")

    # 4. Fill credentials — wait for form to appear
    time.sleep(2)
    log("Looking for email/username field...")
    for sel in ["input[type='email']", "input[name='email']", "input[name='username']",
                 "input[placeholder*='email' i]", "input[placeholder*='username' i]",
                 "#email", "#username", "[data-qa='email-input']", "[data-testid='email']"]:
        try:
            inp = page.wait_for_selector(sel, timeout=3000, state="visible")
            if inp:
                inp.fill(EMAIL)
                log(f"Filled email: {sel}")
                break
        except Exception: pass

    time.sleep(0.5)

    for sel in ["input[type='password']", "input[name='password']", "#password",
                 "[data-qa='password-input']", "[data-testid='password']"]:
        try:
            inp = page.wait_for_selector(sel, timeout=3000, state="visible")
            if inp:
                inp.fill(PASSWORD)
                log(f"Filled password: {sel}")
                break
        except Exception: pass

    time.sleep(0.5)
    snap(page, "03_form_filled")

    # Submit
    for sel in ["button[type='submit']", "button:has-text('LOG IN')",
                 "button:has-text('Log In')", "button:has-text('Login')",
                 "button:has-text('Sign In')", "button:has-text('Continue')",
                 "[data-qa='submit-button']"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                log(f"Submitted: {sel}")
                break
        except Exception: pass

    log("Waiting 20s for post-login XHRs...")
    time.sleep(20)
    snap(page, "04_post_login")
    log(f"URL: {page.url}")

    # 5. If not captured yet, navigate to props to force more XHRs
    if not _done["flag"]:
        props_url = f"https://sportsbook.caesars.com/us/{STATE}/bet#type=SCHEDULE&subtab=Batter+Props"
        log(f"Navigating to props: {props_url}")
        try:
            page.goto(props_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            log(f"Props nav: {e}")
        time.sleep(5)
        snap(page, "05_props")

    # 6. Poll remainder
    deadline = time.time() + MAX_WAIT
    while not _done["flag"] and time.time() < deadline:
        time.sleep(1)

    snap(page, "06_final")
    ctx.close()
    browser.close()

if not harvested.get("bearer_jwt"):
    die(f"No token after {MAX_WAIT}s — login likely still failing, check screenshots")

log("Pushing to Gist...")
payload = json.dumps({"files": {"caesars_tokens.json": {
    "content": json.dumps(harvested, indent=2)
}}}).encode()
req = urllib.request.Request(
    f"https://api.github.com/gists/{GIST_ID}",
    data=payload, method="PATCH",
    headers={"Authorization": f"token {GIST_TOKEN}",
             "Accept": "application/vnd.github.v3+json",
             "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        log(f"✅ Gist updated HTTP {resp.status} — captured_at={harvested['captured_at']}")
except Exception as e:
    die(f"Gist PATCH: {e}")
