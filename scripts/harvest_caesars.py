#!/usr/bin/env python3
"""Caesars harvester — write full diagnostic to Gist for remote reading."""
import os, sys, json, time, urllib.request
from datetime import datetime, timezone

EMAIL      = os.environ.get("CAESARS_EMAIL", "").strip()
PASSWORD   = os.environ.get("CAESARS_PASSWORD", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
STATE      = os.environ.get("CAESARS_STATE", "az").strip().lower()

def log(msg): print(f"[harvest_caesars] {msg}", flush=True)
def die(msg): log(f"FATAL: {msg}"); sys.exit(1)

if not EMAIL: die("CAESARS_EMAIL not set")
if not PASSWORD: die("CAESARS_PASSWORD not set")
if not GIST_TOKEN: die("GIST_TOKEN not set")

from playwright.sync_api import sync_playwright

diag_lines = []
def dlog(msg):
    log(msg)
    diag_lines.append(msg)

def push_diag():
    content = "\n".join(diag_lines)
    payload = json.dumps({"files": {"caesars_diag.txt": {"content": content}}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=payload, method="PATCH",
        headers={"Authorization": f"token {GIST_TOKEN}",
                 "Accept": "application/vnd.github.v3+json",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        log(f"Diag pushed HTTP {r.status}")

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
    dlog(f"BEARER CAPTURED len={len(harvested['bearer_jwt'])}")

dlog(f"Starting state={STATE}")

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
        {"name": "OptanonAlertBoxClosed", "value": "2026-01-01T00:00:00.000Z", "domain": ".caesars.com", "path": "/"},
        {"name": "OptanonConsent", "value": "isGpcEnabled=0&datestamp=2026-01-01", "domain": ".caesars.com", "path": "/"},
    ])
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = ctx.new_page()
    page.on("request", _on_request)

    try:
        page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet", wait_until="networkidle", timeout=45000)
    except Exception as e:
        dlog(f"goto: {e}")
    time.sleep(2)

    # Kill OneTrust
    page.evaluate("() => { const s=document.getElementById('onetrust-consent-sdk'); if(s) s.remove(); }")
    time.sleep(0.5)

    # Dump ALL buttons before login click
    info = page.evaluate("""() => {
        const btns = [...document.querySelectorAll('button, a[href], [role="button"]')]
            .filter(e => e.offsetParent !== null)
            .map(e => ({tag: e.tagName, text: e.textContent.trim().substring(0,40),
                        type: e.type||'', id: e.id, cls: e.className.substring(0,60)}));
        const inputs = [...document.querySelectorAll('input')]
            .map(e => ({type: e.type, name: e.name, id: e.id, placeholder: e.placeholder,
                        visible: e.offsetParent !== null}));
        return {buttons: btns, inputs};
    }""")
    dlog(f"PRE-CLICK BUTTONS: {json.dumps(info['buttons'], indent=2)}")
    dlog(f"PRE-CLICK INPUTS: {json.dumps(info['inputs'], indent=2)}")

    # Click LOG IN
    page.evaluate("""() => {
        const els = [...document.querySelectorAll('button, a, [role="button"]')];
        const t = els.find(e => e.textContent.trim().toUpperCase().includes('LOG IN'));
        if (t) t.click();
    }""")
    time.sleep(3)
    page.evaluate("() => { const s=document.getElementById('onetrust-consent-sdk'); if(s) s.remove(); }")

    # Dump after login click
    info2 = page.evaluate("""() => {
        const btns = [...document.querySelectorAll('button, [role="button"]')]
            .filter(e => e.offsetParent !== null)
            .map(e => ({tag: e.tagName, text: e.textContent.trim().substring(0,40),
                        type: e.type||'', id: e.id, cls: e.className.substring(0,60)}));
        const inputs = [...document.querySelectorAll('input')]
            .filter(e => e.offsetParent !== null)
            .map(e => ({type: e.type, name: e.name, id: e.id, placeholder: e.placeholder}));
        const modals = [...document.querySelectorAll('[role="dialog"],[class*="modal"],[class*="drawer"],[class*="login"],[class*="Login"],[class*="auth"],[class*="Auth"]')]
            .filter(e => e.offsetParent !== null)
            .map(e => ({tag: e.tagName, id: e.id, cls: e.className.substring(0,80)}));
        return {buttons: btns, inputs, modals};
    }""")
    dlog(f"POST-CLICK BUTTONS: {json.dumps(info2['buttons'], indent=2)}")
    dlog(f"POST-CLICK INPUTS: {json.dumps(info2['inputs'], indent=2)}")
    dlog(f"POST-CLICK MODALS: {json.dumps(info2['modals'], indent=2)}")

    # Fill and submit
    for sel in ["input[type='email']", "input[name='email']", "input[name='username']", "#email"]:
        try:
            inp = page.wait_for_selector(sel, timeout=5000, state="visible")
            if inp: inp.fill(EMAIL); dlog(f"Filled email: {sel}"); break
        except: pass

    for sel in ["input[type='password']", "#password"]:
        try:
            inp = page.wait_for_selector(sel, timeout=5000, state="visible")
            if inp: inp.fill(PASSWORD); dlog(f"Filled pw: {sel}"); break
        except: pass

    time.sleep(0.5)

    # Submit — try multiple approaches
    # 1. button[type=submit]
    submit_info = page.evaluate("""() => {
        const submit = document.querySelector('button[type="submit"]');
        if (submit) { submit.click(); return 'clicked type=submit: ' + submit.textContent.trim(); }
        // Find button near password input
        const pw = document.querySelector('input[type="password"]');
        if (pw) {
            const form = pw.closest('form');
            if (form) {
                const btn = form.querySelector('button');
                if (btn) { btn.click(); return 'clicked form button: ' + btn.textContent.trim(); }
            }
        }
        return 'no submit found';
    }""")
    dlog(f"Submit attempt: {submit_info}")
    time.sleep(20)

    info3 = page.evaluate("""() => ({
        url: window.location.href,
        hasLogIn: document.body.innerText.includes('LOG IN'),
        loggedIn: document.body.innerText.includes('MY BETS') || document.body.innerText.includes('DEPOSIT') || document.body.innerText.includes('Balance'),
        bodyText: document.body.innerText.substring(0, 300)
    })""")
    dlog(f"POST-SUBMIT state: {json.dumps(info3, indent=2)}")

    deadline = time.time() + 60
    while not _done["flag"] and time.time() < deadline:
        time.sleep(1)

    ctx.close()
    browser.close()

push_diag()

if not harvested.get("bearer_jwt"):
    die("No token captured")

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
with urllib.request.urlopen(req, timeout=15) as r:
    log(f"Tokens pushed HTTP {r.status}")
