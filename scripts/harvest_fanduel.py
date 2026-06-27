#!/usr/bin/env python3
"""
FanDuel PerimeterX token harvester — standalone GitHub Actions script.

Logs into sportsbook.fanduel.com with credential env vars, navigates to
an active sport page, and intercepts the x-px-context header from outgoing
XHRs to smp.*.sportsbook.fanduel.com (the pricing API domain that carries
the PX token). Pushes the captured token to the shared Gist.

Gist key written: fanduel_tokens.json
  {"px_context": "...", "captured_at": "..."}

Forensic note (2026-06-21): the x-px-context token held ONE value across
15+ pricing requests over a 90-second window, contradicting the "expires
in minutes" assumption. True lifespan is unconfirmed; freshness window in
_get_fanduel_px_context is set to 20 min (cautious). Running every 18h is
well within that window if the assumption holds.

IMPORTANT: GitHub Actions runners use datacenter IPs. PerimeterX v3 flags
these aggressively. xvfb + playwright-stealth + webdriver masking is the
best available mitigation without a residential proxy. If the token is
captured but rejected by FanDuel's API, a residential proxy relay may be
needed (update fetch_fanduel_direct to route through it).

Required env vars:
  FANDUEL_EMAIL      — account email
  FANDUEL_PASSWORD   — account password
  GIST_TOKEN         — GitHub PAT with gist scope
  GIST_ID            — Gist ID (7e52e1c2c2054847c7c4663a157386c5)

Optional env vars:
  FANDUEL_STATE      — two-letter state code (default: az)
  FANDUEL_MAX_WAIT   — seconds to wait for PX token after login (default: 60)
"""

import os, sys, json, time, urllib.request, urllib.error
from datetime import datetime, timezone

# ── Config from environment ───────────────────────────────────────────────────
EMAIL    = os.environ.get("FANDUEL_EMAIL", "").strip()
PASSWORD = os.environ.get("FANDUEL_PASSWORD", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
STATE      = os.environ.get("FANDUEL_STATE", "az").strip().lower()
MAX_WAIT   = int(os.environ.get("FANDUEL_MAX_WAIT", "60"))

def log(msg):
    print(f"[harvest_fanduel] {msg}", flush=True)

def die(msg):
    log(f"FATAL: {msg}")
    sys.exit(1)

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if not EMAIL:      die("FANDUEL_EMAIL is not set")
if not PASSWORD:   die("FANDUEL_PASSWORD is not set")
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

# FanDuel pricing API domains that carry x-px-context
_FD_API_DOMAINS = (
    f"smp.{STATE}.sportsbook.fanduel.com",
    "sportsbook.fanduel.com/api",
    "api.fanduel.com",
)

def _on_request(request):
    if _done["flag"]:
        return
    url = request.url
    if not any(d in url for d in _FD_API_DOMAINS):
        return
    try:
        hdrs = request.all_headers()
    except Exception:
        return
    px = hdrs.get("x-px-context", "")
    if not px or len(px) < 20:
        return
    harvested["px_context"]  = px
    harvested["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _done["flag"] = True
    log(f"✅ x-px-context captured (len={len(px)}) from {url[:80]}")

log(f"Starting — state={STATE}, max_wait={MAX_WAIT}s")

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,   # xvfb provides virtual display on Actions runners
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1280,800",
            # Additional flags to reduce bot-signal surface
            "--disable-infobars",
            "--disable-extensions",
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
        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
        Object.defineProperty(screen, 'colorDepth', {get: () => 24});
    """)

    page = ctx.new_page()
    if HAS_STEALTH:
        stealth_sync(page)

    page.on("request", _on_request)

    # ── 1. Land on FanDuel sportsbook ─────────────────────────────────────────
    url = "https://sportsbook.fanduel.com"
    log(f"Navigating → {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except PWTimeout:
        log("domcontentloaded timed out — continuing")
    except Exception as e:
        log(f"goto raised: {e}")

    time.sleep(4)

    # ── 2. Dismiss banners / location popups ──────────────────────────────────
    for sel in [
        "button:has-text('Accept All')",
        "button:has-text('Accept')",
        "button:has-text('Allow')",
        "button:has-text('Not Now')",
        "[aria-label='Close']",
        "[data-testid='close-button']",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(1)
        except Exception:
            pass

    # ── 3. Log in if not already authenticated ────────────────────────────────
    logged_in = False
    for indicator in [
        "[data-testid='account-menu']",
        "button:has-text('My Account')",
        "text=Deposit",
        "[aria-label='My Account']",
    ]:
        try:
            if page.query_selector(indicator):
                logged_in = True
                log("Already logged in — skipping login flow")
                break
        except Exception:
            pass

    if not logged_in:
        log("Not logged in — attempting credential login")

        # Click Log In button on the nav bar
        for sel in [
            "button:has-text('Log In')",
            "a:has-text('Log In')",
            "[data-testid='login-button']",
            "button:has-text('Sign in')",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(2)
                    log(f"Clicked login trigger: {sel}")
                    break
            except Exception:
                pass

        # Email field
        for sel in ["input[type='email']", "input[name='email']",
                     "input[placeholder*='email' i]", "#email"]:
            try:
                inp = page.query_selector(sel)
                if inp and inp.is_visible():
                    inp.fill(EMAIL)
                    log("Filled email")
                    break
            except Exception:
                pass

        time.sleep(0.5)

        # Password field
        for sel in ["input[type='password']", "input[name='password']", "#password"]:
            try:
                inp = page.query_selector(sel)
                if inp and inp.is_visible():
                    inp.fill(PASSWORD)
                    log("Filled password")
                    break
            except Exception:
                pass

        time.sleep(0.5)

        # Submit
        for sel in [
            "button[type='submit']",
            "button:has-text('Log In')",
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

        log("Waiting 15s for post-login navigation…")
        time.sleep(15)

    # ── 4. Navigate to MLB page to trigger pricing API XHRs ──────────────────
    # The pricing domain (smp.{state}.sportsbook.fanduel.com) fires when a
    # live odds page renders. MLB or NBA pages reliably trigger it.
    if not _done["flag"]:
        sport_url = "https://sportsbook.fanduel.com/baseball/mlb"
        log(f"Navigating to sport page → {sport_url}")
        try:
            page.goto(sport_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            log(f"Sport page nav raised (non-fatal): {e}")
        time.sleep(5)

    # ── 5. Try NBA as well if still no token ─────────────────────────────────
    if not _done["flag"]:
        try:
            page.goto("https://sportsbook.fanduel.com/basketball/nba",
                      wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            pass
        time.sleep(5)

    # ── 6. Poll until token captured or timeout ───────────────────────────────
    deadline = time.time() + MAX_WAIT
    while not _done["flag"] and time.time() < deadline:
        time.sleep(1)

    ctx.close()
    browser.close()

# ── Validate ──────────────────────────────────────────────────────────────────
if not harvested.get("px_context"):
    die(
        f"No x-px-context token captured after {MAX_WAIT}s. "
        "GitHub Actions datacenter IPs may be flagged by PerimeterX — "
        "check the Actions log for PerimeterX challenge pages or bot blocks. "
        "A residential proxy (FANDUEL_PROXY env var) may be required."
    )

# ── Push to Gist ──────────────────────────────────────────────────────────────
log("Pushing fanduel_tokens.json to Gist…")
payload = json.dumps({
    "files": {
        "fanduel_tokens.json": {
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
                f"px_context len={len(harvested['px_context'])}, "
                f"captured_at={harvested['captured_at']}")
        else:
            die(f"Gist PATCH returned HTTP {resp.status}")
except urllib.error.HTTPError as e:
    die(f"Gist PATCH failed: HTTP {e.code} — {e.read().decode()[:200]}")
except Exception as e:
    die(f"Gist PATCH failed: {e}")
