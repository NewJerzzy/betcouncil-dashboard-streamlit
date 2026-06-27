#!/usr/bin/env python3
"""Caesars harvester — always push diagnostic to Gist even on failure."""
import os, sys, json, time, urllib.request, traceback
from datetime import datetime, timezone

EMAIL      = os.environ.get("CAESARS_EMAIL", "").strip()
PASSWORD   = os.environ.get("CAESARS_PASSWORD", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
STATE      = os.environ.get("CAESARS_STATE", "az").strip().lower()

log_lines = []
def log(msg):
    print(f"[harvest_caesars] {msg}", flush=True)
    log_lines.append(msg)

def push_gist(files_dict):
    payload = json.dumps({"files": {k: {"content": v} for k, v in files_dict.items()}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=payload, method="PATCH",
        headers={"Authorization": f"token {GIST_TOKEN}",
                 "Accept": "application/vnd.github.v3+json",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        log(f"Gist push HTTP {r.status}")

if not EMAIL or not PASSWORD or not GIST_TOKEN:
    log("Missing env vars"); sys.exit(1)

from playwright.sync_api import sync_playwright

harvested = {}
_done = {"flag": False}
dom_snapshots = {}

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

def dom_dump(page, label):
    try:
        info = page.evaluate("""() => {
            const vis_btns = [...document.querySelectorAll('button,[role="button"],a')]
                .filter(e => {
                    const r = e.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && r.top < window.innerHeight;
                })
                .slice(0, 30)
                .map(e => e.tagName + '|' + (e.type||'') + '|' + e.textContent.trim().substring(0,30) + '|id=' + e.id);
            const vis_inputs = [...document.querySelectorAll('input')]
                .filter(e => e.getBoundingClientRect().height > 0)
                .map(e => 'type=' + e.type + ' name=' + e.name + ' id=' + e.id + ' ph=' + e.placeholder);
            const dialogs = [...document.querySelectorAll('[role="dialog"],[class*="Modal"],[class*="modal"],[class*="Drawer"],[class*="drawer"]')]
                .filter(e => e.getBoundingClientRect().height > 0)
                .map(e => e.tagName + '#' + e.id + '.' + e.className.substring(0,50));
            return {
                url: window.location.href,
                title: document.title,
                buttons: vis_btns,
                inputs: vis_inputs,
                dialogs: dialogs,
                bodySnip: document.body.innerText.substring(0, 200)
            };
        }""")
        dom_snapshots[label] = info
        log(f"DOM[{label}] url={info['url'][:60]}")
        log(f"DOM[{label}] inputs={info['inputs']}")
        log(f"DOM[{label}] dialogs={info['dialogs']}")
        log(f"DOM[{label}] buttons_count={len(info['buttons'])}")
        for b in info['buttons'][:15]:
            log(f"  btn: {b}")
    except Exception as e:
        log(f"dom_dump {label}: {e}")

log(f"Starting state={STATE}")
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
            {"name": "OptanonAlertBoxClosed", "value": "2026-01-01T00:00:00.000Z", "domain": ".caesars.com", "path": "/"},
            {"name": "OptanonConsent", "value": "isGpcEnabled=0&datestamp=2026-01-01", "domain": ".caesars.com", "path": "/"},
        ])
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.new_page()
        page.on("request", _on_request)

        try:
            page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet", wait_until="networkidle", timeout=45000)
        except Exception as e:
            log(f"goto: {e}")
        time.sleep(2)
        page.evaluate("() => { const s=document.getElementById('onetrust-consent-sdk'); if(s) s.remove(); }")

        dom_dump(page, "1_before_login_click")

        # Click LOG IN
        clicked = page.evaluate("""() => {
            const all = [...document.querySelectorAll('*')];
            const t = all.find(e => {
                const txt = e.textContent.trim().toUpperCase();
                const r = e.getBoundingClientRect();
                return (txt === 'LOG IN' || txt === 'LOGIN') && r.height > 0 && r.width > 0;
            });
            if (t) { t.click(); return t.tagName + ' ' + t.textContent.trim(); }
            return null;
        }""")
        log(f"Login click: {clicked}")
        time.sleep(4)
        page.evaluate("() => { const s=document.getElementById('onetrust-consent-sdk'); if(s) s.remove(); }")

        dom_dump(page, "2_after_login_click")

        # Fill email
        for sel in ["input[type='email']","input[name='email']","input[name='username']","#email"]:
            try:
                el = page.wait_for_selector(sel, timeout=4000, state="visible")
                if el: el.fill(EMAIL); log(f"email filled via {sel}"); break
            except: pass

        # Fill password
        for sel in ["input[type='password']","input[name='password']","#password"]:
            try:
                el = page.wait_for_selector(sel, timeout=4000, state="visible")
                if el: el.fill(PASSWORD); log(f"pw filled via {sel}"); break
            except: pass

        dom_dump(page, "3_after_fill")

        # Submit
        sub = page.evaluate("""() => {
            // Try type=submit
            const s = document.querySelector('button[type="submit"]');
            if (s && s.getBoundingClientRect().height > 0) { s.click(); return 'type=submit:' + s.textContent.trim(); }
            // Try form containing password
            const pw = document.querySelector('input[type="password"]');
            if (pw) {
                const form = pw.closest('form');
                if (form) {
                    const b = form.querySelector('button');
                    if (b) { b.click(); return 'form-btn:' + b.textContent.trim(); }
                    form.submit();
                    return 'form.submit()';
                }
            }
            // Press Enter on password field
            const pw2 = document.querySelector('input[type="password"]');
            if (pw2) {
                pw2.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter',keyCode:13,bubbles:true}));
                pw2.dispatchEvent(new KeyboardEvent('keyup',  {key:'Enter',keyCode:13,bubbles:true}));
                return 'enter-keyevent';
            }
            return 'no-submit-found';
        }""")
        log(f"Submit: {sub}")
        time.sleep(25)

        dom_dump(page, "4_after_submit")

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
    # Always push diagnostic
    diag = "\n".join(log_lines)
    diag += "\n\nDOM SNAPSHOTS:\n" + json.dumps(dom_snapshots, indent=2)
    files = {"caesars_diag.txt": diag}
    if success and harvested.get("bearer_jwt"):
        files["betcouncil_caesars_tokens.json"] = json.dumps(harvested, indent=2)
    try:
        push_gist(files)
    except Exception as e:
        log(f"Final push failed: {e}")

if not success:
    sys.exit(1)
