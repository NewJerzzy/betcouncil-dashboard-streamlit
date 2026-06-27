#!/usr/bin/env python3
"""Caesars harvester — handle MFA and TOS after login."""
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

def snap_state(page, label):
    info = page.evaluate("""() => ({
        url: window.location.href,
        bodySnip: document.body.innerText.substring(0, 400),
        visInputs: [...document.querySelectorAll('input')]
            .filter(i => i.getBoundingClientRect().height > 0)
            .map(i => ({type: i.type, name: i.name, ph: i.placeholder})),
        visBtns: [...document.querySelectorAll('button')]
            .filter(b => {
                const r = b.getBoundingClientRect();
                return r.height > 20 && r.width > 40 && r.y > 50;
            })
            .map(b => ({text: b.textContent.trim().substring(0,40),
                        type: b.type, y: Math.round(b.getBoundingClientRect().y),
                        disabled: b.disabled}))
    })""")
    log(f"[{label}] url={info['url'][:60]}")
    log(f"[{label}] body={info['bodySnip'][:200]}")
    log(f"[{label}] inputs={json.dumps(info['visInputs'])}")
    log(f"[{label}] buttons={json.dumps(info['visBtns'])}")
    return info

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
            {"name": "OptanonConsent","value": "isGpcEnabled=0&datestamp=2026-01-01&version=202301.2.0&interactionCount=1&groups=C0001:1,C0002:1,C0003:1,C0004:1","domain": ".caesars.com","path": "/"},
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
        page.evaluate("document.querySelectorAll('[id*=\"onetrust\"],[class*=\"onetrust\"]').forEach(e=>e.remove())")
        time.sleep(0.5)
        snap_state(page, "01_landing")

        # Dismiss any modal/location overlay first
        for sel in ["button.CloseButton","[aria-label='Close']","[aria-label='close']"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(); log(f"Dismissed: {sel}"); time.sleep(1); break
            except: pass
        page.keyboard.press("Escape")
        time.sleep(1)

        # Click LOG IN (header button at y≈18)
        try:
            btn = page.get_by_text("LOG IN", exact=True).first
            box = btn.bounding_box()
            log(f"LOG IN box: {box}")
            page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            log("Clicked LOG IN")
        except Exception as e: log(f"LOG IN: {e}")
        time.sleep(4)
        snap_state(page, "02_after_login_click")

        # Fill email
        for sel in ["input[type='email']","input[name='email']","input[name='username']"]:
            try:
                el = page.wait_for_selector(sel, timeout=8000, state="visible")
                if el: page.fill(sel, EMAIL); log(f"email: {sel}"); break
            except: pass

        # Fill password
        for sel in ["input[type='password']","input[name='password']"]:
            try:
                el = page.wait_for_selector(sel, timeout=5000, state="visible")
                if el: page.fill(sel, PASSWORD); log(f"pw: {sel}"); break
            except: pass
        time.sleep(0.5)

        snap_state(page, "03_after_fill")

        # Click the submit LOG IN button — must be below y=100 (not header)
        clicked = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')]
                .filter(b => {
                    const r = b.getBoundingClientRect();
                    return r.height > 20 && r.width > 40 && r.y > 80;
                });
            // Find LOG IN button below header
            const login = btns.find(b => b.textContent.trim().toUpperCase() === 'LOG IN');
            if (login) { login.click(); return 'login@y=' + Math.round(login.getBoundingClientRect().y); }
            // Any submit
            const sub = btns.find(b => b.type === 'submit' && !b.disabled);
            if (sub) { sub.click(); return 'submit:' + sub.textContent.trim(); }
            return 'none:' + btns.map(b=>b.textContent.trim().substring(0,20)).join('|');
        }""")
        log(f"Submit: {clicked}")
        time.sleep(10)
        snap_state(page, "04_after_submit_10s")

        # Handle post-login states
        for attempt in range(6):
            time.sleep(5)
            state = page.evaluate("""() => ({
                hasLogIn: document.body.innerText.includes('LOG IN'),
                hasMFA: document.body.innerText.includes('verification') ||
                        document.body.innerText.includes('code') ||
                        document.body.innerText.includes('authenticat'),
                hasTOS: document.body.innerText.includes('Terms') ||
                        document.body.innerText.includes('Accept'),
                hasBalance: document.body.innerText.includes('BALANCE') ||
                            document.body.innerText.includes('MY BETS') ||
                            document.body.innerText.includes('Deposit'),
                bodySnip: document.body.innerText.substring(0,300),
                visInputs: [...document.querySelectorAll('input')]
                    .filter(i => i.getBoundingClientRect().height > 0)
                    .map(i => ({type: i.type, name: i.name, ph: i.placeholder, val: i.value.substring(0,5)})),
                visBtns: [...document.querySelectorAll('button')]
                    .filter(b => {
                        const r = b.getBoundingClientRect();
                        return r.height > 20 && r.width > 40 && r.y > 50;
                    })
                    .map(b => ({text: b.textContent.trim().substring(0,40), y: Math.round(b.getBoundingClientRect().y)}))
            })""")
            log(f"[poll-{attempt}] logIn={state['hasLogIn']} MFA={state['hasMFA']} TOS={state['hasTOS']} balance={state['hasBalance']}")
            log(f"[poll-{attempt}] body={state['bodySnip'][:200]}")
            log(f"[poll-{attempt}] inputs={json.dumps(state['visInputs'])}")
            log(f"[poll-{attempt}] buttons={json.dumps(state['visBtns'])}")

            if state['hasTOS']:
                # Accept TOS
                accepted = page.evaluate("""() => {
                    const btns = [...document.querySelectorAll('button')]
                        .filter(b => b.getBoundingClientRect().height > 0);
                    const accept = btns.find(b => /accept|agree|confirm|continue/i.test(b.textContent));
                    if (accept) { accept.click(); return 'accepted:' + accept.textContent.trim(); }
                    return 'no-accept-btn';
                }""")
                log(f"TOS: {accepted}")

            if state['hasBalance'] or _done["flag"]:
                log("LOGGED IN!")
                break

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
