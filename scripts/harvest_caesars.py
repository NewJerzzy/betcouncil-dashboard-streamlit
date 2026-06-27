#!/usr/bin/env python3
"""Caesars harvester — dump modal HTML to diagnose submit failure."""
import os, sys, json, time, urllib.request
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
    log(f"✅ Bearer captured len={len(harvested['bearer_jwt'])}")

def snap(page, label):
    try:
        page.screenshot(path=f"/tmp/caesars_{label}.png")
        log(f"[{label}] {page.url[:70]}")
    except Exception as e:
        log(f"snap {label}: {e}")

def dump_modal(page):
    """Dump all buttons and inputs visible in the page."""
    try:
        info = page.evaluate("""
            () => {
                const inputs = [...document.querySelectorAll('input')].map(i => ({
                    type: i.type, name: i.name, id: i.id,
                    placeholder: i.placeholder, visible: i.offsetParent !== null
                }));
                const buttons = [...document.querySelectorAll('button, [role="button"]')].map(b => ({
                    text: b.textContent.trim().substring(0, 50),
                    type: b.type, id: b.id,
                    class: b.className.substring(0, 80),
                    visible: b.offsetParent !== null,
                    disabled: b.disabled
                })).filter(b => b.visible);
                // Also get any dialog/modal elements
                const dialogs = [...document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="drawer"], [class*="login"]')].map(d => ({
                    tag: d.tagName,
                    id: d.id,
                    class: d.className.substring(0, 100),
                    visible: d.offsetParent !== null
                })).filter(d => d.visible);
                return {inputs, buttons, dialogs};
            }
        """)
        log(f"INPUTS: {json.dumps(info['inputs'], indent=2)}")
        log(f"VISIBLE BUTTONS: {json.dumps(info['buttons'], indent=2)}")
        log(f"DIALOGS/MODALS: {json.dumps(info['dialogs'], indent=2)}")
    except Exception as e:
        log(f"dump_modal: {e}")

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
    ctx.add_cookies([
        {"name": "OptanonAlertBoxClosed", "value": "2026-01-01T00:00:00.000Z",
         "domain": ".caesars.com", "path": "/"},
        {"name": "OptanonConsent", "value": "isGpcEnabled=0&datestamp=2026-01-01",
         "domain": ".caesars.com", "path": "/"},
    ])
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = {runtime: {}};
    """)
    page = ctx.new_page()
    page.on("request", _on_request)

    # Navigate
    try:
        page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet",
                  wait_until="networkidle", timeout=45_000)
    except Exception as e:
        log(f"goto: {e}")
    time.sleep(2)

    # Kill OneTrust
    page.evaluate("""
        () => {
            ['#onetrust-consent-sdk', '.onetrust-pc-dark-filter'].forEach(s => {
                const el = document.querySelector(s); if (el) el.remove();
            });
        }
    """)
    time.sleep(0.5)
    log("=== BEFORE LOGIN CLICK ===")
    dump_modal(page)

    # Click LOG IN
    page.evaluate("""
        () => {
            const els = [...document.querySelectorAll('button, a, [role="button"]')];
            const t = els.find(e => e.textContent.trim().toUpperCase().includes('LOG IN'));
            if (t) t.click();
        }
    """)
    time.sleep(3)
    snap(page, "01_after_login_click")

    log("=== AFTER LOGIN CLICK — looking for modal ===")
    dump_modal(page)

    # Fill credentials
    for sel in ["input[type='email']", "input[name='email']", "input[name='username']", "#email"]:
        try:
            inp = page.wait_for_selector(sel, timeout=5000, state="visible")
            if inp: inp.fill(EMAIL); log(f"Filled email: {sel}"); break
        except: pass

    for sel in ["input[type='password']", "input[name='password']", "#password"]:
        try:
            inp = page.wait_for_selector(sel, timeout=5000, state="visible")
            if inp: inp.fill(PASSWORD); log(f"Filled password: {sel}"); break
        except: pass

    time.sleep(0.5)
    log("=== AFTER FILLING CREDENTIALS ===")
    dump_modal(page)
    snap(page, "02_form_filled")

    # Press Enter as submit (most reliable)
    try:
        page.keyboard.press("Enter")
        log("Pressed Enter to submit")
    except Exception as e:
        log(f"Enter: {e}")

    time.sleep(20)
    snap(page, "03_post_submit")
    log("=== AFTER SUBMIT ===")
    dump_modal(page)
    log(f"URL: {page.url}")
    log(f"Page has LOG IN: {'LOG IN' in page.inner_text('body')}")

    # Poll
    deadline = time.time() + MAX_WAIT
    while not _done["flag"] and time.time() < deadline:
        time.sleep(1)

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
with urllib.request.urlopen(req, timeout=15) as resp:
    log(f"✅ Gist updated HTTP {resp.status}")
