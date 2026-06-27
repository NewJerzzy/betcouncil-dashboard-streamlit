#!/usr/bin/env python3
"""Caesars harvester — find submit button inside login drawer."""
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
            locale="en-US", timezone_id="America/New_York",
        )
        ctx.add_cookies([
            {"name": "OptanonAlertBoxClosed","value": "2026-01-01T00:00:00.000Z","domain": ".caesars.com","path": "/"},
            {"name": "OptanonConsent","value": "isGpcEnabled=0&datestamp=2026-01-01&version=202301.2.0&isIABGlobal=false&hosts=&consentId=x&interactionCount=1&landingPath=NotLandingPage&groups=C0001:1,C0002:1,C0003:1,C0004:1","domain": ".caesars.com","path": "/"},
        ])
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};")
        page = ctx.new_page()
        page.on("request", _on_request)

        try:
            page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet", wait_until="networkidle", timeout=45000)
        except Exception as e: log(f"goto: {e}")
        time.sleep(2)
        page.evaluate("document.querySelectorAll('[id*=\"onetrust\"],[class*=\"onetrust\"]').forEach(e=>e.remove())")
        time.sleep(0.5)

        # Click LOG IN with real mouse
        btn = page.get_by_text("LOG IN", exact=True).first
        box = btn.bounding_box()
        log(f"LOG IN box: {box}")
        page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
        time.sleep(4)

        # Fill email
        for sel in ["input[type='email']","input[name='email']","input[name='username']"]:
            try:
                el = page.wait_for_selector(sel, timeout=8000, state="visible")
                if el: page.fill(sel, EMAIL); log(f"email: {sel}"); break
            except: pass

        time.sleep(0.3)

        # Fill password
        for sel in ["input[type='password']","input[name='password']"]:
            try:
                el = page.wait_for_selector(sel, timeout=5000, state="visible")
                if el: page.fill(sel, PASSWORD); log(f"pw: {sel}"); break
            except: pass

        time.sleep(0.5)

        # Dump ALL buttons in the drawer after filling credentials
        drawer_btns = page.evaluate("""() => {
            // Find the open/visible drawer
            const drawers = [...document.querySelectorAll('[class*="Drawer"],[class*="drawer"]')]
                .filter(d => {
                    const r = d.getBoundingClientRect();
                    return r.height > 100 && r.width > 100;
                });
            const result = [];
            for (const drawer of drawers) {
                const btns = [...drawer.querySelectorAll('button,[role="button"]')]
                    .map(b => ({
                        text: b.textContent.trim().substring(0,50),
                        type: b.type||'',
                        id: b.id,
                        cls: b.className.substring(0,80),
                        disabled: b.disabled,
                        h: b.getBoundingClientRect().height,
                        w: b.getBoundingClientRect().width,
                        x: Math.round(b.getBoundingClientRect().x),
                        y: Math.round(b.getBoundingClientRect().y),
                    }));
                result.push({drawer_cls: drawer.className.substring(0,60), buttons: btns});
            }
            return result;
        }""")
        log(f"DRAWER BUTTONS: {json.dumps(drawer_btns, indent=2)}")

        # Find the login submit button — look for button inside the drawer with pw field
        submit_result = page.evaluate("""() => {
            const pw = document.querySelector('input[type="password"]');
            if (!pw) return 'no-pw-field';
            // Walk up to find containing drawer
            let el = pw;
            while (el && el !== document.body) {
                if (el.className && el.className.includes('Drawer')) break;
                el = el.parentElement;
            }
            if (!el || el === document.body) {
                // Try finding any visible submit button
                const allBtns = [...document.querySelectorAll('button[type="submit"],button')]
                    .filter(b => {
                        const r = b.getBoundingClientRect();
                        return r.height > 0 && r.width > 0;
                    });
                // Find one that says LOG IN or SIGN IN or CONTINUE or LOGIN
                const loginBtn = allBtns.find(b =>
                    /^(LOG IN|LOGIN|SIGN IN|CONTINUE|SUBMIT)$/i.test(b.textContent.trim())
                );
                if (loginBtn) { loginBtn.click(); return 'clicked-' + loginBtn.textContent.trim(); }
                // Just click the last visible submit
                const submits = allBtns.filter(b => b.type === 'submit');
                if (submits.length) { submits[submits.length-1].click(); return 'clicked-last-submit:' + submits[submits.length-1].textContent.trim(); }
                return 'no-submit-found';
            }
            const btns = [...el.querySelectorAll('button')].filter(b => b.getBoundingClientRect().height > 0);
            const sub = btns.find(b => b.type === 'submit' || /^(LOG IN|LOGIN|CONTINUE|SIGN IN)$/i.test(b.textContent.trim()));
            if (sub) { sub.click(); return 'drawer-submit:' + sub.textContent.trim(); }
            if (btns.length) { btns[btns.length-1].click(); return 'drawer-last-btn:' + btns[btns.length-1].textContent.trim(); }
            return 'drawer-no-buttons';
        }""")
        log(f"Submit: {submit_result}")

        time.sleep(25)

        state = page.evaluate("""() => ({
            hasLogIn: document.body.innerText.includes('LOG IN'),
            hasBalance: document.body.innerText.includes('BALANCE') || document.body.innerText.includes('MY BETS') || document.body.innerText.includes('Deposit'),
            url: window.location.href,
            snip: document.body.innerText.substring(0,200)
        })""")
        log(f"POST-SUBMIT: {json.dumps(state)}")

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
