#!/usr/bin/env python3
"""Caesars harvester — dismiss location modal, then login."""
import os, sys, json, time, urllib.request, traceback
from datetime import datetime, timezone

EMAIL      = os.environ.get("CAESARS_EMAIL", "").strip()
PASSWORD   = os.environ.get("CAESARS_PASSWORD", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
DIAG_GIST  = "15138e8f9de33d0922bf5ac2469385c3"
STATE      = os.environ.get("CAESARS_STATE", "az").strip().lower()

log_lines = []
def log(msg): print(f"[harvest_caesars] {msg}", flush=True); log_lines.append(msg)
def push_diag(content):
    payload = json.dumps({"files": {"caesars_diag.txt": {"content": content}}}).encode()
    req = urllib.request.Request(f"https://api.github.com/gists/{DIAG_GIST}",
        data=payload, method="PATCH",
        headers={"Authorization": f"token {GIST_TOKEN}",
                 "Accept": "application/vnd.github.v3+json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        log(f"Diag push HTTP {r.status}")

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
        browser = pw.chromium.launch(headless=False,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox","--disable-dev-shm-usage","--window-size=1280,900"])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/Phoenix",
            geolocation={"latitude": 33.4484, "longitude": -112.0740},
            permissions=["geolocation"],
        )
        ctx.add_cookies([
            {"name": "OptanonAlertBoxClosed","value": "2026-01-01T00:00:00.000Z","domain": ".caesars.com","path": "/"},
            {"name": "OptanonConsent","value": "isGpcEnabled=0&datestamp=2026-01-01&version=202301.2.0&isIABGlobal=false&hosts=&consentId=x&interactionCount=1&landingPath=NotLandingPage&groups=C0001:1,C0002:1,C0003:1,C0004:1","domain": ".caesars.com","path": "/"},
            # Pre-set AZ location cookie
            {"name": "userLocation","value": "az","domain": ".caesars.com","path": "/"},
            {"name": "selectedState","value": "az","domain": ".caesars.com","path": "/"},
        ])
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};")
        page = ctx.new_page()
        page.on("request", _on_request)

        log(f"Navigating state={STATE}")
        try:
            page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet",
                      wait_until="networkidle", timeout=45000)
        except Exception as e: log(f"goto: {e}")
        time.sleep(3)

        # 1. Kill OneTrust
        page.evaluate("document.querySelectorAll('[id*=\"onetrust\"],[class*=\"onetrust\"]').forEach(e=>e.remove())")
        time.sleep(0.5)

        # 2. Dismiss location modal — close button or X
        log("Checking for location modal...")
        for sel in [
            "button.CloseButton",
            "[aria-label='close']",
            "[aria-label='Close']",
            "button:has-text('×')",
            ".change-location-drawer-container button.CloseButton",
            "[class*='close']",
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    log(f"Dismissed modal via: {sel}")
                    time.sleep(1)
                    break
            except: pass

        # Also try pressing Escape
        page.keyboard.press("Escape")
        time.sleep(1)

        # Log what's visible
        visible_text = page.inner_text("body")[:300]
        log(f"Page text: {visible_text[:200]}")

        # 3. Click LOG IN
        try:
            btn = page.get_by_text("LOG IN", exact=True).first
            box = btn.bounding_box()
            log(f"LOG IN box: {box}")
            page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            log("Clicked LOG IN")
        except Exception as e:
            log(f"LOG IN click: {e}")
        time.sleep(4)

        # 4. Fill credentials
        email_sel = None
        for sel in ["input[type='email']","input[name='email']","input[name='username']"]:
            try:
                el = page.wait_for_selector(sel, timeout=8000, state="visible")
                if el: email_sel = sel; log(f"Email: {sel}"); break
            except: pass

        if not email_sel:
            log("NO EMAIL FIELD")
            # Dump all drawers
            info = page.evaluate("""() => {
                const drawers = [...document.querySelectorAll('[class*="Drawer"],[class*="drawer"]')]
                    .filter(d => d.getBoundingClientRect().height > 50)
                    .map(d => ({cls: d.className.substring(0,80), h: d.getBoundingClientRect().height,
                                overlay: d.className.includes('closed')}));
                return drawers;
            }""")
            log(f"Drawers: {json.dumps(info)}")
        else:
            page.fill(email_sel, EMAIL)
            log("Filled email")
            time.sleep(0.3)

            for sel in ["input[type='password']","input[name='password']"]:
                try:
                    el = page.wait_for_selector(sel, timeout=5000, state="visible")
                    if el: page.fill(sel, PASSWORD); log(f"Filled pw: {sel}"); break
                except: pass
            time.sleep(0.5)

            # Find submit button in the same drawer as the password field
            submit_info = page.evaluate("""() => {
                const pw = document.querySelector('input[type="password"]');
                if (!pw) return {result: 'no-pw'};
                // Find visible buttons near the pw field
                const allBtns = [...document.querySelectorAll('button')]
                    .filter(b => {
                        const r = b.getBoundingClientRect();
                        return r.height > 0 && r.width > 50;
                    })
                    .map(b => ({
                        text: b.textContent.trim().substring(0,40),
                        type: b.type,
                        x: Math.round(b.getBoundingClientRect().x),
                        y: Math.round(b.getBoundingClientRect().y),
                        h: Math.round(b.getBoundingClientRect().height),
                        w: Math.round(b.getBoundingClientRect().width),
                        disabled: b.disabled
                    }));
                return {buttons: allBtns};
            }""")
            log(f"Visible buttons after fill: {json.dumps(submit_info)}")

            # Click submit — find button with LOG IN text or type=submit near the form
            clicked = page.evaluate("""() => {
                const btns = [...document.querySelectorAll('button')]
                    .filter(b => b.getBoundingClientRect().height > 0 && b.getBoundingClientRect().width > 50);
                // Priority: button saying LOG IN that's not at y<30 (not the header button)
                const loginBtn = btns.find(b =>
                    b.textContent.trim().toUpperCase() === 'LOG IN' &&
                    b.getBoundingClientRect().y > 100
                );
                if (loginBtn) { loginBtn.click(); return 'login-btn:' + loginBtn.textContent.trim(); }
                // type=submit
                const sub = btns.find(b => b.type === 'submit' && !b.disabled);
                if (sub) { sub.click(); return 'submit:' + sub.textContent.trim(); }
                return 'none';
            }""")
            log(f"Submit click: {clicked}")

            # Also try clicking via Playwright locator targeting button below y=100
            try:
                submit_btn = page.locator("button").filter(has_text="LOG IN").nth(1)
                if submit_btn.count() > 0:
                    submit_btn.click(force=True)
                    log("Playwright click on second LOG IN button")
            except: pass

            time.sleep(25)
            state_info = page.evaluate("""() => ({
                hasLogIn: document.body.innerText.includes('LOG IN'),
                hasBalance: document.body.innerText.includes('BALANCE') || document.body.innerText.includes('MY BETS') || document.body.innerText.includes('Deposit'),
                url: window.location.href,
                snip: document.body.innerText.substring(0,200)
            })""")
            log(f"POST-SUBMIT: {json.dumps(state_info)}")

        deadline = time.time() + 60
        while not _done["flag"] and time.time() < deadline:
            time.sleep(1)
        if _done["flag"]: success = True

        ctx.close()
        browser.close()

except Exception as e:
    log(f"EXCEPTION: {traceback.format_exc()}")

finally:
    diag = "\n".join(log_lines)
    try: push_diag(diag)
    except Exception as e: print(f"diag push: {e}")
    if success and harvested.get("bearer_jwt"):
        payload = json.dumps({"files": {"betcouncil_caesars_tokens.json": {
            "content": json.dumps(harvested, indent=2)}}}).encode()
        req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
            data=payload, method="PATCH",
            headers={"Authorization": f"token {GIST_TOKEN}",
                     "Accept": "application/vnd.github.v3+json",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            log(f"Tokens push HTTP {r.status}")

sys.exit(0 if success else 1)
