#!/usr/bin/env python3
"""
Caesars Sportsbook token harvester — standalone GitHub Actions script.

Logs into sportsbook.caesars.com with credential env vars, intercepts the
first outgoing XHR to api.americanwagering.com that carries the Bearer JWT
and x-aws-waf-token, then pushes them to the shared Gist so Streamlit Cloud
picks them up on the next scrape cycle.

Gist key written: caesars_tokens.json
  {"bearer_jwt": "...", "waf_token": "...", "captured_at": "..."}

Required env vars:
  CAESARS_EMAIL      — account email
  CAESARS_PASSWORD   — account password
  GIST_TOKEN         — GitHub PAT with gist scope
  GIST_ID            — Gist ID (7e52e1c2c2054847c7c4663a157386c5)

Optional env vars:
  CAESARS_STATE      — two-letter state code (default: az)
  CAESARS_MAX_WAIT   — seconds to wait for token after login (default: 90)
"""

import os, sys, json, time, urllib.request, urllib.error
from datetime import datetime, timezone

# ── Config from environment ───────────────────────────────────────────────────
EMAIL    = os.environ.get("CAESARS_EMAIL", "").strip()
PASSWORD = os.environ.get("CAESARS_PASSWORD", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
STATE      = os.environ.get("CAESARS_STATE", "az").strip().lower()
MAX_WAIT   = int(os.environ.get("CAESARS_MAX_WAIT", "90"))

def log(msg):
    print(f"[harvest_caesars] {msg}", flush=True)

def die(msg):
    log(f"FATAL: {msg}")
    sys.exit(1)

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if not EMAIL:    die("CAESARS_EMAIL is not set")
if not PASSWORD: die("CAESARS_PASSWORD is not set")
if not GIST_TOKEN: die("GIST_TOKEN is not set")

# ── Playwright import ─────────────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    die("playwright not installed — pip install playwright && playwright install chromium")

try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    log("playwright-stealth not available — running without it")
    HAS_STEALTH = False

# ── Harvester ─────────────────────────────────────────────────────────────────
harvested: dict = {}
_done = {"flag": False}

def _on_request(request):
    if _done["flag"]:
        return
    if "americanwagering.com" not in request.url:
        return
    try:
        hdrs = request.all_headers()
    except Exception:
        return
    auth = hdrs.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) < 60:
        return
    harvested["bearer_jwt"]  = auth[len("Bearer "):]
    harvested["waf_token"]   = hdrs.get("x-aws-waf-token", "")
    harvested["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _done["flag"] = True
    log(f"✅ Bearer token captured (len={len(harvested['bearer_jwt'])}, "
        f"waf={'yes' if harvested['waf_token'] else 'no'})")

log(f"Starting — state={STATE}, max_wait={MAX_WAIT}s")

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,   # xvfb provides virtual display on Actions runners
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
    if HAS_STEALTH:
        stealth_sync(page)

    page.on("request", _on_request)

    # ── 1. Land on the sportsbook ─────────────────────────────────────────────
    url = f"https://sportsbook.caesars.com/us/{STATE}/bet"
    log(f"Navigating → {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except PWTimeout:
        log("domcontentloaded timed out — page may still be loading, continuing")
    except Exception as e:
        log(f"goto raised: {e}")

    time.sleep(3)

    # ── 2. Dismiss geo/cookie banners if present ──────────────────────────────
    for sel in [
        "button:has-text('Accept')",
        "button:has-text('OK')",
        "[aria-label='close']",
        "button:has-text('No thanks')",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(1)
        except Exception:
            pass

    # ── 3. Log in if not already authenticated ────────────────────────────────
    # Check if already logged in by looking for a logged-in indicator
    logged_in = False
    for indicator in ["[data-testid='account-balance']", ".account-balance",
                       "text=My Account", "text=BALANCE"]:
        try:
            if page.query_selector(indicator):
                logged_in = True
                log("Already logged in — skipping login flow")
                break
        except Exception:
            pass

    if not logged_in:
        log("Not logged in — attempting credential login")
        # Click the Sign In / Log In button
        signed_in = False
        for sel in [
            "button:has-text('Sign in')",
            "button:has-text('Log in')",
            "a:has-text('Sign in')",
            "[data-testid='login-button']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(2)
                    signed_in = True
                    log(f"Clicked login trigger: {sel}")
                    break
            except Exception:
                pass

        # Fill email
        for sel in ["input[type='email']", "input[name='email']",
                     "input[placeholder*='email' i]", "#email"]:
            try:
                inp = page.query_selector(sel)
                if inp and inp.is_visible():
                    inp.fill(EMAIL)
                    log("Filled email field")
                    break
            except Exception:
                pass

        time.sleep(0.5)

        # Fill password
        for sel in ["input[type='password']", "input[name='password']",
                     "#password"]:
            try:
                inp = page.query_selector(sel)
                if inp and inp.is_visible():
                    inp.fill(PASSWORD)
                    log("Filled password field")
                    break
            except Exception:
                pass

        time.sleep(0.5)

        # Submit
        for sel in [
            "button[type='submit']",
            "button:has-text('Log in')",
            "button:has-text('Sign in')",
            "button:has-text('Continue')",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    log(f"Clicked submit: {sel}")
                    break
            except Exception:
                pass

        log("Waiting up to 15s for post-login navigation…")
        time.sleep(15)

    # ── 4. Navigate to props page to trigger americanwagering.com XHRs ────────
    if not _done["flag"]:
        props_url = (
            f"https://sportsbook.caesars.com/us/{STATE}/bet"
            "#type=SCHEDULE&subtab=Batter+Props"
        )
        log(f"Navigating to props tab → {props_url}")
        try:
            page.goto(props_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            log(f"Props nav raised (non-fatal): {e}")

    # ── 5. Poll until token captured or timeout ───────────────────────────────
    deadline = time.time() + MAX_WAIT
    while not _done["flag"] and time.time() < deadline:
        time.sleep(1)

    ctx.close()
    browser.close()

# ── Validate ──────────────────────────────────────────────────────────────────
if not harvested.get("bearer_jwt"):
    die(
        f"No Bearer token captured after {MAX_WAIT}s. "
        "Check that login succeeded (no 2FA / state-lock) and "
        "that americanwagering.com XHRs fired."
    )

# ── Push to Gist ──────────────────────────────────────────────────────────────
log("Pushing caesars_tokens.json to Gist…")
payload = json.dumps({
    "files": {
        "caesars_tokens.json": {
            "content": json.dumps(harvested, indent=2)
        }
    }
}).encode()

req = urllib.request.Request(
    f"https://api.github.com/gists/{GIST_ID}",
    data=payload,
    method="PATCH",
    headers={
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    },
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status in (200, 201):
            log(f"✅ Gist updated (HTTP {resp.status}) — "
                f"bearer_jwt len={len(harvested['bearer_jwt'])}, "
                f"captured_at={harvested['captured_at']}")
        else:
            die(f"Gist PATCH returned HTTP {resp.status}")
except urllib.error.HTTPError as e:
    die(f"Gist PATCH failed: HTTP {e.code} — {e.read().decode()[:200]}")
except Exception as e:
    die(f"Gist PATCH failed: {e}")
