#!/usr/bin/env python3
"""Caesars harvester — real Playwright clicks, diagnostic to public gist."""
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

def push_gist(gist_id, files):
    payload = json.dumps({"files": {k: {"content": v} for k, v in files.items()}}).encode()
    req = urllib.request.Request(f"https://api.github.com/gists/{gist_id}",
        data=payload, method="PATCH",
        headers={"Authorization": f"token {GIST_TOKEN}",
                 "Accept": "application/vnd.github.v3+json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        log(f"Gist {gist_id[:8]} push HTTP {r.status}")

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

        log(f"Navigating state={STATE}")
        try:
            page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet",
                      wait_until="networkidle", timeout=45000)
        except Exception as e:
            log(f"goto: {e}")
        time.sleep(2)

        # Nuke OneTrust
        page.evaluate("""() => {
            document.querySelectorAll('[id*="onetrust"],[class*="onetrust"]').forEach(e=>e.remove());
        }""")
        time.sleep(0.5)

        # Use Playwright locator with real pointer events
        try:
            btn = page.get_by_text("LOG IN", exact=True).first
            box = btn.bounding_box()
            log(f"LOG IN bounding_box: {box}")
            if box:
                page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                log("Clicked LOG IN via mouse")
            else:
                btn.click(force=True)
                log("Clicked LOG IN via force click")
        except Exception as e:
            log(f"LOG IN click error: {e}")

        time.sleep(4)

        # Log drawer state
        drawers = page.evaluate("""() =>
            [...document.querySelectorAll('[class*="drawer"],[class*="Drawer"]')]
            .map(e => ({cls: e.className.substring(0,60), h: e.getBoundingClientRect().height}))
        """)
        log(f"Drawers: {json.dumps(drawers)}")

        # Wait for email input
        email_sel = None
        for sel in ["input[type='email']","input[name='email']",
                     "input[name='username']","input[placeholder*='email' i]",
                     "input[placeholder*='Email' i]","input[placeholder*='username' i]"]:
            try:
                el = page.wait_for_selector(sel, timeout=8000, state="visible")
                if el: email_sel = sel; log(f"Email field: {sel}"); break
            except: pass

        if not email_sel:
            log("NO EMAIL FIELD — drawer not open")
            # Log all visible inputs
            all_inputs = page.evaluate("""() =>
                [...document.querySelectorAll('input')]
                .map(i => ({t:i.type,n:i.name,id:i.id,ph:i.placeholder,h:i.getBoundingClientRect().height}))
            """)
            log(f"All inputs: {json.dumps(all_inputs)}")
        else:
            page.fill(email_sel, EMAIL)
            log("Filled email")
            time.sleep(0.3)
            for sel in ["input[type='password']","input[name='password']","#password"]:
                try:
                    el = page.wait_for_selector(sel, timeout=5000, state="visible")
                    if el:
                        page.fill(sel, PASSWORD)
                        log(f"Filled password: {sel}")
                        break
                except: pass
            time.sleep(0.3)

            # Submit
            try:
                page.locator("button[type='submit']").first.click(force=True)
                log("Clicked submit")
            except:
                page.keyboard.press("Enter")
                log("Pressed Enter")

            time.sleep(25)
            state_info = page.evaluate("""() => ({
                hasLogIn: document.body.innerText.includes('LOG IN'),
                hasBalance: document.body.innerText.includes('BALANCE') || document.body.innerText.includes('MY BETS'),
                snip: document.body.innerText.substring(0,150)
            })""")
            log(f"Post-login: {json.dumps(state_info)}")

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
    try:
        push_gist(DIAG_GIST, {"caesars_diag.txt": diag})
    except Exception as e:
        print(f"diag push failed: {e}")
    if success and harvested.get("bearer_jwt"):
        try:
            push_gist(GIST_ID, {"betcouncil_caesars_tokens.json": json.dumps(harvested, indent=2)})
        except Exception as e:
            print(f"token push failed: {e}")

sys.exit(0 if success else 1)
