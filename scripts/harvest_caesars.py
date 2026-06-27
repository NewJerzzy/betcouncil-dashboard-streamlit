#!/usr/bin/env python3
"""Caesars harvester — use real Playwright pointer events for React SPA."""
import os, sys, json, time, urllib.request, traceback
from datetime import datetime, timezone

EMAIL      = os.environ.get("CAESARS_EMAIL", "").strip()
PASSWORD   = os.environ.get("CAESARS_PASSWORD", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
STATE      = os.environ.get("CAESARS_STATE", "az").strip().lower()

log_lines = []
def log(msg): print(f"[harvest_caesars] {msg}", flush=True); log_lines.append(msg)
def push_gist(files):
    payload = json.dumps({"files": {k: {"content": v} for k, v in files.items()}}).encode()
    req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
        data=payload, method="PATCH",
        headers={"Authorization": f"token {GIST_TOKEN}",
                 "Accept": "application/vnd.github.v3+json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        log(f"Gist push HTTP {r.status}")

if not EMAIL or not PASSWORD or not GIST_TOKEN:
    log("Missing env vars"); sys.exit(1)

from playwright.sync_api import sync_playwright

harvested = {}
_done = {"flag": False}

def _on_request(request):
    if _done["flag"]: return
    if "americanwagering.com" not in request.url: return
    try: hdrs = request.all_headers()
    except: return
    auth = hdrs.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) < 60: return
    harvested["bearer_jwt"]  = auth[len("Bearer "):]
    harvested["waf_token"]   = hdrs.get("x-aws-waf-token", "")
    harvested["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _done["flag"] = True
    log(f"BEARER CAPTURED len={len(harvested['bearer_jwt'])}")

success = False
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,800"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/New_York",
        )
        ctx.add_cookies([
            {"name": "OptanonAlertBoxClosed", "value": "2026-01-01T00:00:00.000Z",
             "domain": ".caesars.com", "path": "/"},
            {"name": "OptanonConsent",
             "value": "isGpcEnabled=0&datestamp=2026-01-01&version=202301.2.0&isIABGlobal=false&hosts=&consentId=x&interactionCount=1&landingPath=NotLandingPage&groups=C0001:1,C0002:1,C0003:1,C0004:1",
             "domain": ".caesars.com", "path": "/"},
        ])
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
        """)
        page = ctx.new_page()
        page.on("request", _on_request)

        log(f"Navigating to Caesars {STATE}...")
        try:
            page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet",
                      wait_until="networkidle", timeout=45000)
        except Exception as e:
            log(f"goto: {e}")
        time.sleep(2)

        # Aggressively remove ALL OneTrust elements
        page.evaluate("""() => {
            document.querySelectorAll('[id*="onetrust"],[class*="onetrust"],[id*="ot-"],[class*="ot-"]')
                .forEach(e => e.remove());
            // Remove any fixed/absolute overlay
            document.querySelectorAll('div').forEach(e => {
                const s = window.getComputedStyle(e);
                if ((s.position === 'fixed' || s.position === 'absolute') &&
                    parseFloat(s.zIndex) > 1000 && s.display !== 'none') {
                    e.remove();
                }
            });
        }""")
        time.sleep(0.5)
        log("OneTrust nuked")

        # Use Playwright locator to find and click LOG IN button
        # The button text is exactly "LOG IN"
        try:
            login_btn = page.get_by_text("LOG IN", exact=True).first
            login_btn.wait_for(state="visible", timeout=5000)
            log(f"Found LOG IN button, clicking with real pointer event...")
            login_btn.click(force=True)  # force bypasses interceptor checks
            log("LOG IN clicked")
        except Exception as e:
            log(f"get_by_text LOG IN failed: {e}")
            # Fallback: find by class pattern from DOM dump
            try:
                btns = page.locator('button:has-text("LOG IN")')
                count = btns.count()
                log(f"Found {count} buttons with LOG IN text")
                if count > 0:
                    btns.first.click(force=True)
                    log("Clicked first LOG IN button")
            except Exception as e2:
                log(f"locator fallback: {e2}")

        time.sleep(3)

        # Check if drawer opened
        drawer_open = page.evaluate("""() => {
            const drawers = [...document.querySelectorAll('[class*="drawer"],[class*="Drawer"]')];
            return drawers.map(d => ({cls: d.className, visible: d.getBoundingClientRect().height > 0}));
        }""")
        log(f"Drawer state: {json.dumps(drawer_open)}")

        # Look for login form inputs
        inputs_now = page.evaluate("""() =>
            [...document.querySelectorAll('input')].map(i => ({
                type: i.type, name: i.name, id: i.id, ph: i.placeholder,
                vis: i.getBoundingClientRect().height > 0
            }))
        """)
        log(f"Inputs after click: {json.dumps(inputs_now)}")

        # Wait for email field to appear (drawer animation)
        email_sel = None
        for sel in ["input[type='email']", "input[name='email']",
                     "input[name='username']", "input[placeholder*='email' i]",
                     "input[placeholder*='Email' i]"]:
            try:
                el = page.wait_for_selector(sel, timeout=8000, state="visible")
                if el:
                    email_sel = sel
                    log(f"Email field appeared: {sel}")
                    break
            except: pass

        if not email_sel:
            log("ERROR: Login drawer did not open — no email field found")
            # Try clicking LOG IN one more time with mouse.click at coordinates
            try:
                box = page.get_by_text("LOG IN", exact=True).first.bounding_box()
                if box:
                    log(f"LOG IN bounding box: {box}")
                    page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                    log("Clicked via mouse.click coordinates")
                    time.sleep(3)
                    for sel in ["input[type='email']", "input[name='email']", "input[name='username']"]:
                        try:
                            el = page.wait_for_selector(sel, timeout=6000, state="visible")
                            if el: email_sel = sel; log(f"Email field (retry): {sel}"); break
                        except: pass
            except Exception as e:
                log(f"mouse.click fallback: {e}")

        if email_sel:
            page.fill(email_sel, EMAIL)
            log("Filled email")
            time.sleep(0.3)

            for sel in ["input[type='password']", "input[name='password']", "#password"]:
                try:
                    el = page.wait_for_selector(sel, timeout=5000, state="visible")
                    if el:
                        page.fill(sel, PASSWORD)
                        log(f"Filled password: {sel}")
                        break
                except: pass

            time.sleep(0.3)

            # Submit with real Playwright click on submit button
            try:
                submit = page.locator("button[type='submit']").first
                submit.click(force=True)
                log("Clicked submit button")
            except Exception as e:
                log(f"submit click: {e}")
                page.keyboard.press("Enter")
                log("Pressed Enter")

            log("Waiting 25s for auth XHRs...")
            time.sleep(25)
            log(f"URL after login: {page.url}")
            logged_in_text = page.evaluate("""() => ({
                hasLogIn: document.body.innerText.includes('LOG IN'),
                hasBalance: document.body.innerText.includes('BALANCE') ||
                            document.body.innerText.includes('Deposit') ||
                            document.body.innerText.includes('MY BETS'),
                snip: document.body.innerText.substring(0, 200)
            })""")
            log(f"Post-login state: {json.dumps(logged_in_text)}")

        # Poll for token
        deadline = time.time() + 60
        while not _done["flag"] and time.time() < deadline:
            time.sleep(1)

        if _done["flag"]:
            success = True

        ctx.close()
        browser.close()

except Exception as e:
    log(f"EXCEPTION: {traceback.format_exc()}")

finally:
    diag = "\n".join(log_lines)
    files = {"betcouncil_caesars_diag.txt": diag}
    if success and harvested.get("bearer_jwt"):
        files["betcouncil_caesars_tokens.json"] = json.dumps(harvested, indent=2)
    try:
        push_gist(files)
    except Exception as e:
        log(f"Final gist push failed: {e}")

sys.exit(0 if success else 1)
