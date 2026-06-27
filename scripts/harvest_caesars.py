#!/usr/bin/env python3
"""Caesars token harvester — dismiss OneTrust overlay before login."""
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
    if "americanwagering.com" not in request.url: return
    try:
        hdrs = request.all_headers()
    except Exception: return
    auth = hdrs.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) < 60: return
    harvested["bearer_jwt"]  = auth[len("Bearer "):]
    harvested["waf_token"]   = hdrs.get("x-aws-waf-token", "")
    harvested["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _done["flag"] = True
    log(f"✅ Bearer captured len={len(harvested['bearer_jwt'])} url={request.url[:80]}")

def snap(page, label):
    try:
        page.screenshot(path=f"/tmp/caesars_{label}.png")
        txt = page.inner_text("body")[:200].replace("\n", " ")
        log(f"[{label}] {page.url[:70]} | {txt[:150]}")
    except Exception as e:
        log(f"snap {label}: {e}")

def dismiss_onetrust(page):
    """Force-remove OneTrust overlay and accept cookies via JS."""
    try:
        page.evaluate("""
            () => {
                // Remove the blocking overlay
                const overlay = document.querySelector('.onetrust-pc-dark-filter');
                if (overlay) overlay.remove();
                // Remove the entire consent SDK
                const sdk = document.getElementById('onetrust-consent-sdk');
                if (sdk) sdk.remove();
                // Also try clicking accept button if it exists
                const accept = document.getElementById('onetrust-accept-btn-handler');
                if (accept) accept.click();
                // Set consent cookies so it doesn't re-appear
                document.cookie = 'OptanonAlertBoxClosed=' + new Date().toISOString();
                document.cookie = 'OptanonConsent=isGpcEnabled=0&datestamp=' + new Date().toISOString();
            }
        """)
        log("OneTrust overlay dismissed")
        time.sleep(0.5)
    except Exception as e:
        log(f"OneTrust dismiss: {e}")

def js_click(page, text_options):
    """Click element containing any of the given texts via JS."""
    texts_js = json.dumps(text_options)
    result = page.evaluate(f"""
        () => {{
            const texts = {texts_js};
            const els = [...document.querySelectorAll('button, a, [role="button"], div[class*="login"], span[class*="login"]')];
            for (const t of texts) {{
                const target = els.find(e => e.textContent.trim().toUpperCase().includes(t.toUpperCase()));
                if (target) {{ target.click(); return target.textContent.trim(); }}
            }}
            return null;
        }}
    """)
    return result

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
    # Pre-set OneTrust consent cookies so overlay never appears
    ctx.add_cookies([
        {"name": "OptanonAlertBoxClosed", "value": "2026-01-01T00:00:00.000Z",
         "domain": ".caesars.com", "path": "/"},
        {"name": "OptanonConsent", "value": "isGpcEnabled=0&datestamp=2026-01-01",
         "domain": ".caesars.com", "path": "/"},
    ])

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
    time.sleep(2)

    # 2. Nuke OneTrust overlay immediately
    dismiss_onetrust(page)
    time.sleep(1)
    snap(page, "01_landing")

    # 3. Click LOG IN using JS (bypass pointer-event issues entirely)
    result = js_click(page, ["LOG IN", "Log In", "Login", "Sign In", "SIGN IN"])
    log(f"Login click result: {result}")
    time.sleep(3)
    dismiss_onetrust(page)  # dismiss again in case it re-appeared after click
    snap(page, "02_after_login_click")

    # 4. Fill email
    time.sleep(1)
    email_filled = False
    for sel in ["input[type='email']", "input[name='email']", "input[name='username']",
                 "input[placeholder*='email' i]", "#email", "#username"]:
        try:
            inp = page.wait_for_selector(sel, timeout=5000, state="visible")
            if inp:
                inp.click()
                time.sleep(0.3)
                inp.fill(EMAIL)
                log(f"Filled email: {sel}")
                email_filled = True
                break
        except Exception: pass

    if not email_filled:
        log("WARNING: Could not find email field")

    time.sleep(0.5)

    # 5. Fill password
    pw_filled = False
    for sel in ["input[type='password']", "input[name='password']", "#password"]:
        try:
            inp = page.wait_for_selector(sel, timeout=5000, state="visible")
            if inp:
                inp.click()
                time.sleep(0.3)
                inp.fill(PASSWORD)
                log(f"Filled password: {sel}")
                pw_filled = True
                break
        except Exception: pass

    if not pw_filled:
        log("WARNING: Could not find password field")

    time.sleep(0.5)
    snap(page, "03_form_filled")

    # 6. Submit — use JS click to bypass any overlay
    submit_result = page.evaluate("""
        () => {
            // Try submit button first
            const submit = document.querySelector('button[type="submit"]');
            if (submit) { submit.click(); return 'submit-button'; }
            // Try any button with login text
            const btns = [...document.querySelectorAll('button')];
            const login_btn = btns.find(b =>
                b.textContent.trim().toUpperCase().match(/^(LOG IN|LOGIN|SIGN IN|CONTINUE)$/)
            );
            if (login_btn) { login_btn.click(); return login_btn.textContent.trim(); }
            return null;
        }
    """)
    log(f"Submit result: {submit_result}")

    log("Waiting 25s for post-login XHRs...")
    time.sleep(25)
    snap(page, "04_post_login")
    log(f"URL after login: {page.url}")

    # 7. If not captured, try navigating to force auth XHRs
    if not _done["flag"]:
        log("Token not yet captured — trying sports page to trigger auth XHRs...")
        try:
            page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet#type=SPORT&id=Baseball",
                      wait_until="domcontentloaded", timeout=20_000)
        except Exception as e:
            log(f"sports nav: {e}")
        time.sleep(8)
        snap(page, "05_sports")

    # 8. Poll remainder
    deadline = time.time() + MAX_WAIT
    while not _done["flag"] and time.time() < deadline:
        time.sleep(1)

    snap(page, "06_final")
    ctx.close()
    browser.close()

if not harvested.get("bearer_jwt"):
    die(f"No token after {MAX_WAIT}s")

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
