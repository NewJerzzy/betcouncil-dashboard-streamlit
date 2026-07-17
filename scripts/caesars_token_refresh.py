"""
caesars_token_refresh.py — automated Caesars login + Bearer/WAF token harvest
================================================================================

Replaces the manual "open DevTools, copy the Bearer + x-aws-waf-token headers
by hand" refresh cycle with a scheduled headless Playwright run. Logs into
the Caesars account with credentials from env (GitHub Actions secrets),
captures the two auth headers Caesars injects client-side on every call to
api.americanwagering.com, and pushes them to the same Gist file the app
already reads from.

WHY THIS EXISTS AS ITS OWN SCRIPT rather than living in fetchers.py: fetchers.py
imports streamlit at module level, which this cron job has no reason to carry.
Self-contained, same pattern as scripts/mybookie_refresh.py and friends.

Gist file: betcouncil_caesars_tokens.json
  IMPORTANT: the pre-existing harvest_caesars_tokens() in fetchers.py wrote to
  a *different* filename ("caesars_tokens.json") than every reader
  (_get_caesars_tokens, fetch_caesars_waf_from_gist, the curl_cffi Caesars
  props fetcher in betcouncil_auto_scraper.py) expects
  ("betcouncil_caesars_tokens.json") -- that mismatch is fixed in this script
  and in fetchers.py itself (harvest_caesars_tokens now writes to the correct
  key too), so both the old manual path and this new automated path land in
  the same place the consumers actually look.

Payload shape matches what _get_caesars_tokens() reads directly (flat dict,
no wrapper): {"bearer_jwt": "...", "waf_token": "...", "captured_at": "..."}

Cadence: run at least once within every ~24h window (the JWT's expiry) --
see .github/workflows/caesars_token_refresh.yml for the actual schedule.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GIST_FILE = "betcouncil_caesars_tokens.json"
LOGIN_URL = "https://sportsbook.caesars.com/us/az/bet#login"
MAX_WAIT_SECONDS = 90


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def push_to_gist(payload: dict, github_token: str) -> bool:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2)}}},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return True
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return False


def harvest(email: str, password: str) -> dict:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    harvested: dict = {}
    stop = {"done": False}

    def on_request(request):
        if stop["done"] or "americanwagering.com" not in request.url:
            return
        try:
            hdrs = request.all_headers()
        except Exception:
            return
        auth = hdrs.get("authorization", "")
        if not auth.startswith("Bearer ") or len(auth) < 60:
            return
        harvested["bearer_jwt"] = auth[len("Bearer "):]
        harvested["waf_token"] = hdrs.get("x-aws-waf-token", "")
        harvested["captured_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        stop["done"] = True

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ],
        )
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"),
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1280, "height": 720},
        )
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)
        page = ctx.new_page()
        page.on("request", on_request)

        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(3)
            try:
                page.click("button:has-text('LOG IN')", timeout=5_000)
                time.sleep(2)
            except Exception:
                pass  # login modal may already be open from the #login URL fragment

            page.wait_for_selector(
                'input[type="email"], input[name="username"], input[placeholder*="email" i]',
                timeout=10_000,
            )
            page.fill('input[type="email"], input[name="username"], input[placeholder*="email" i]', email)
            time.sleep(0.5)
            page.fill('input[type="password"]', password)
            time.sleep(0.5)
            page.click('button[type="submit"], button:has-text("LOG IN"), button:has-text("Sign In")')
            log(f"Post-login URL: {page.url}")
        except PWTimeout:
            log("Login flow timed out at some step — request listener stays active, still polling")
        except Exception as e:
            log(f"Login flow error: {e} — request listener stays active, still polling")

        # After login, browse into the sportsbook itself -- the auth headers
        # get attached to the odds/props API calls that fire once a sport
        # page loads, not necessarily on the login page itself.
        try:
            page.goto("https://sportsbook.caesars.com/us/az/bet/baseball/mlb",
                       wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass

        deadline = time.time() + MAX_WAIT_SECONDS
        while not stop["done"] and time.time() < deadline:
            time.sleep(1)

        ctx.close()
        browser.close()

    return harvested


def main() -> int:
    email = os.environ.get("CAESARS_EMAIL", "")
    password = os.environ.get("CAESARS_PASSWORD", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")

    if not email or not password:
        log("FATAL: CAESARS_EMAIL / CAESARS_PASSWORD not set")
        return 1
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    harvested = harvest(email, password)
    if not harvested.get("bearer_jwt"):
        log(f"No Bearer token captured after {MAX_WAIT_SECONDS}s — "
            "login may have failed or Caesars changed its login form/selectors")
        return 1

    log(f"Captured token (len={len(harvested['bearer_jwt'])}), "
        f"waf_token={'present' if harvested.get('waf_token') else 'MISSING'}")

    if push_to_gist(harvested, github_token):
        log(f"Pushed to {GIST_FILE}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
