#!/usr/bin/env python3
"""
Caesars token harvester — cookie injection approach.
Injects real browser cookies from env vars, navigates to sportsbook,
intercepts americanwagering.com XHR Bearer token.
No login automation needed.
"""
import os, sys, json, time, urllib.request, traceback
from datetime import datetime, timezone

GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
GIST_ID    = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5").strip()
DIAG_GIST  = "15138e8f9de33d0922bf5ac2469385c3"
STATE      = os.environ.get("CAESARS_STATE", "az").strip().lower()
# Cookie values from env
WAF_TOKEN  = os.environ.get("CAESARS_WAF_TOKEN", "").strip()
BCNCTKN    = os.environ.get("CAESARS_BCNCTKN", "").strip()

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

if not GIST_TOKEN: log("Missing GIST_TOKEN"); sys.exit(1)
if not WAF_TOKEN:  log("Missing CAESARS_WAF_TOKEN"); sys.exit(1)
if not BCNCTKN:    log("Missing CAESARS_BCNCTKN"); sys.exit(1)

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
        )

        # Inject all real session cookies
        cookies = [
            {"name": "aws-waf-token",  "value": WAF_TOKEN,
             "domain": ".sportsbook.caesars.com", "path": "/"},
            {"name": "_bcnctkn",       "value": BCNCTKN,
             "domain": ".caesars.com", "path": "/"},
            {"name": "OptanonAlertBoxClosed", "value": "2026-06-27T19:46:40.350Z",
             "domain": ".caesars.com", "path": "/"},
            {"name": "OptanonConsent",
             "value": "isGpcEnabled=0&datestamp=2026-01-01&version=202406.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=x&interactionCount=2&groups=C0001:1,C0003:1,C0002:1,C0004:1",
             "domain": ".caesars.com", "path": "/"},
        ]
        ctx.add_cookies(cookies)
        log(f"Injected {len(cookies)} cookies")

        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};")
        page = ctx.new_page()
        page.on("request", _on_request)

        log(f"Navigating state={STATE}")
        try:
            page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet",
                      wait_until="networkidle", timeout=45000)
        except Exception as e: log(f"goto: {e}")
        time.sleep(5)

        # Check login state
        body_text = page.inner_text("body")[:400]
        log(f"Body: {body_text[:300]}")
        is_logged_in = "LOG IN" not in body_text or "BALANCE" in body_text or "MY BETS" in body_text or "Deposit" in body_text
        log(f"Logged in: {is_logged_in}")

        if not is_logged_in:
            log("Not logged in — cookies may have expired")
            # Try navigating to a protected page to trigger auth XHR anyway
            try:
                page.goto(f"https://sportsbook.caesars.com/us/{STATE}/bet#type=SCHEDULE&subtab=Batter+Props",
                          wait_until="domcontentloaded", timeout=20000)
            except Exception as e: log(f"props nav: {e}")
            time.sleep(5)

        # Poll for Bearer token from XHRs
        deadline = time.time() + 60
        while not _done["flag"] and time.time() < deadline:
            time.sleep(1)

        if _done["flag"]:
            success = True
        else:
            log("No Bearer token — checking if already in headers of initial XHRs")
            # The initial page load may have already fired auth XHRs before we set up listener
            # Try clicking something to trigger more XHRs
            try:
                page.click("text=Baseball", timeout=5000)
                time.sleep(5)
            except: pass
            deadline2 = time.time() + 30
            while not _done["flag"] and time.time() < deadline2:
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
