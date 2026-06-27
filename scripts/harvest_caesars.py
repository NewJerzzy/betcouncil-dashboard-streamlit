#!/usr/bin/env python3
"""
Caesars token harvester — with screenshot diagnostics.
"""
import os, sys, json, time, urllib.request, urllib.error, base64
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

def push_screenshot(page, label, gist_token, gist_id):
    """Upload a screenshot as a Gist file for diagnosis."""
    try:
        img = page.screenshot(full_page=False)
        b64 = base64.b64encode(img).decode()
        # Save locally so Actions artifact can pick it up
        fname = f"/tmp/caesars_{label}.png"
        with open(fname, "wb") as f:
            f.write(img)
        log(f"Screenshot saved: {fname}")
        # Also push page HTML for text diagnosis
        html_fname = f"/tmp/caesars_{label}.html"
        with open(html_fname, "w") as f:
            f.write(page.content())
        log(f"HTML saved: {html_fname}")
        # Log visible text
        try:
            body_text = page.inner_text("body")[:1000]
            log(f"Page text ({label}): {body_text[:500]}")
        except Exception:
            pass
    except Exception as e:
        log(f"Screenshot failed ({label}): {e}")

def _on_request(request):
    if _done["flag"]: return
    url = request.url
    # Log ALL XHR/fetch requests for diagnosis
    if any(x in url for x in ["americanwagering", "caesars", "api.", "wagering"]):
        log(f"XHR: {request.method} {url[:120]}")
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
    log(f"✅ Bearer captured (len={len(harvested['bearer_jwt'])})")

log(f"Starting — state={STATE}")

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1280,800",
        ],
    )
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
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
    url = f"https://sportsbook.caesars.com/us/{STATE}/bet"
    log(f"Navigating → {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except Exception as e:
        log(f"goto: {e}")
    time.sleep(4)
    push_screenshot(page, "01_landing", GIST_TOKEN, GIST_ID)

    # 2. Dismiss banners
    for sel in ["button:has-text('Accept')", "button:has-text('OK')",
                 "[aria-label='close']", "button:has-text('No thanks')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible(): btn.click(); time.sleep(1)
        except Exception: pass

    # 3. Check login state
    logged_in = False
    for indicator in ["[data-testid='account-balance']", ".account-balance",
                       "text=My Account", "text=BALANCE", "text=Deposit"]:
        try:
            if page.query_selector(indicator):
                logged_in = True
                log(f"Already logged in (found: {indicator})")
                break
        except Exception: pass

    if not logged_in:
        log("Attempting login...")
        # Find and click login button
        for sel in ["button:has-text('Sign in')", "button:has-text('Log in')",
                     "a:has-text('Sign in')", "[data-testid='login-button']",
                     "button:has-text('Login')"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click(); time.sleep(2)
                    log(f"Clicked: {sel}"); break
            except Exception: pass

        push_screenshot(page, "02_after_login_click", GIST_TOKEN, GIST_ID)

        # Email
        for sel in ["input[type='email']", "input[name='email']",
                     "input[placeholder*='email' i]", "#email", "input[name='username']"]:
            try:
                inp = page.query_selector(sel)
                if inp and inp.is_visible():
                    inp.fill(EMAIL); log(f"Filled email ({sel})"); break
            except Exception: pass

        time.sleep(0.5)

        # Password
        for sel in ["input[type='password']", "input[name='password']", "#password"]:
            try:
                inp = page.query_selector(sel)
                if inp and inp.is_visible():
                    inp.fill(PASSWORD); log(f"Filled password ({sel})"); break
            except Exception: pass

        time.sleep(0.5)

        # Submit
        for sel in ["button[type='submit']", "button:has-text('Log in')",
                     "button:has-text('Sign in')", "button:has-text('Continue')",
                     "button:has-text('Login')"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click(); log(f"Submitted ({sel})"); break
            except Exception: pass

        time.sleep(15)
        push_screenshot(page, "03_post_login", GIST_TOKEN, GIST_ID)
        log(f"Current URL after login: {page.url}")

    # 4. Navigate to props to trigger XHRs
    if not _done["flag"]:
        props_url = f"https://sportsbook.caesars.com/us/{STATE}/bet#type=SCHEDULE&subtab=Batter+Props"
        log(f"Props nav → {props_url}")
        try:
            page.goto(props_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            log(f"Props nav: {e}")
        time.sleep(5)
        push_screenshot(page, "04_props_page", GIST_TOKEN, GIST_ID)
        log(f"URL after props nav: {page.url}")

    # 5. Poll
    deadline = time.time() + MAX_WAIT
    while not _done["flag"] and time.time() < deadline:
        time.sleep(1)

    push_screenshot(page, "05_final", GIST_TOKEN, GIST_ID)
    ctx.close()
    browser.close()

if not harvested.get("bearer_jwt"):
    die(f"No token after {MAX_WAIT}s — check screenshots in /tmp/caesars_*.png")

# Push to Gist
log("Pushing to Gist...")
payload = json.dumps({"files": {"caesars_tokens.json": {
    "content": json.dumps(harvested, indent=2)
}}}).encode()
req = urllib.request.Request(
    f"https://api.github.com/gists/{GIST_ID}",
    data=payload, method="PATCH",
    headers={
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    },
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        log(f"✅ Gist updated (HTTP {resp.status})")
except Exception as e:
    die(f"Gist PATCH failed: {e}")
