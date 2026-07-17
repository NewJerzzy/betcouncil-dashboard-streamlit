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

import base64
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GIST_FILE = "betcouncil_caesars_tokens.json"
DEBUG_GIST_FILE = "betcouncil_caesars_debug.json"
LOGIN_URL = "https://sportsbook.caesars.com/us/az/bet#login"
MAX_WAIT_SECONDS = 90


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def push_to_gist(payload: dict, github_token: str, filename: str = GIST_FILE) -> bool:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": {filename: {"content": json.dumps(payload, indent=2)}}},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return True
    log(f"Gist push failed ({filename}): {resp.status_code} {resp.text[:300]}")
    return False


def push_debug(page, steps: list, github_token: str, button_inventory=None) -> None:
    """Dump current URL, a targeted HTML snapshot, a full button inventory,
    and a full-page screenshot to Gist. Exists because this sandbox's network
    allowlist can't reach GitHub Actions' log-storage host
    (results-receiver.actions.githubusercontent.com), so raw run logs aren't
    fetchable here -- this is the diagnostic channel that IS reachable (plain
    Gist API, same host used for everything else)."""
    debug = {"captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "steps": steps, "button_inventory": button_inventory or []}
    try:
        debug["current_url"] = page.url
    except Exception as e:
        debug["current_url"] = f"<error: {e}>"
    try:
        # Prefer the modal/dialog markup over page.content()[:N] -- the
        # first run's head-heavy page meant a flat truncation never reached
        # the login form at all. Fall back to the plain truncation if no
        # dialog-like container is found.
        modal_html = page.eval_on_selector_all(
            "dialog, [role='dialog'], [class*='Modal' i], [class*='modal' i]",
            "els => els.map(e => e.outerHTML).join('\\n---\\n')",
        )
        debug["modal_html"] = (modal_html or "")[:20000]
        debug["html_snippet"] = page.content()[:8000]
    except Exception as e:
        debug["modal_html"] = f"<error: {e}>"
        debug["html_snippet"] = f"<error: {e}>"
    try:
        png_bytes = page.screenshot(full_page=False, timeout=10_000)
        debug["screenshot_b64_png"] = base64.b64encode(png_bytes).decode("ascii")
    except Exception as e:
        debug["screenshot_b64_png"] = f"<error: {e}>"
    if not push_to_gist(debug, github_token, DEBUG_GIST_FILE):
        log("Debug dump push also failed")
    else:
        log(f"Debug dump pushed to {DEBUG_GIST_FILE} ({len(debug.get('modal_html',''))} char modal HTML, "
            f"{'screenshot ok' if not str(debug['screenshot_b64_png']).startswith('<error') else 'screenshot FAILED'})")


def harvest(email: str, password: str, github_token: str) -> dict:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    harvested: dict = {}
    stop = {"done": False}
    steps: list = []

    def note(step_name, ok, detail=""):
        steps.append({"step": step_name, "ok": ok, "detail": str(detail)[:300]})
        log(f"  [{'OK' if ok else 'FAIL'}] {step_name}" + (f" — {detail}" if detail else ""))

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
            note("goto login page", True, page.url)
        except Exception as e:
            note("goto login page", False, e)

        time.sleep(3)

        # Dismiss a cookie-consent banner if one is covering the form —
        # common cause of "click"/"fill" landing on the wrong element.
        for sel in ["button:has-text('Accept')", "button:has-text('Accept All')",
                    "#onetrust-accept-btn-handler", "button:has-text('I Accept')"]:
            try:
                page.click(sel, timeout=2_000)
                note(f"dismiss consent banner ({sel})", True)
                time.sleep(1)
                break
            except Exception:
                continue

        try:
            page.click("button:has-text('LOG IN')", timeout=5_000)
            note("click LOG IN", True)
            time.sleep(2)
        except Exception as e:
            note("click LOG IN", False, e)
            # login modal may already be open from the #login URL fragment —
            # not fatal on its own, keep going

        try:
            page.wait_for_selector(
                'input[type="email"], input[name="username"], input[placeholder*="email" i]',
                timeout=10_000,
            )
            note("email field appeared", True)
        except Exception as e:
            note("email field appeared", False, e)

        try:
            page.fill('input[type="email"], input[name="username"], input[placeholder*="email" i]', email)
            note("fill email", True)
        except Exception as e:
            note("fill email", False, e)
        time.sleep(0.5)

        try:
            page.fill('input[type="password"]', password)
            note("fill password", True)
        except Exception as e:
            note("fill password", False, e)
        time.sleep(0.5)

        # Diagnostic only: inventory every button on the page right before
        # attempting submit. The first run showed the generic submit selector
        # resolving to the *outer nav* "Log In" button (data-qa=
        # "login-cta-log-in-btn", the one that opens the modal) rather than
        # the modal's actual submit control -- this snapshot is how we find
        # the real one instead of guessing again.
        button_inventory = []
        try:
            button_inventory = page.eval_on_selector_all(
                "button",
                """els => els.map(e => ({
                    text: (e.innerText || '').trim().slice(0, 40),
                    dataQa: e.getAttribute('data-qa') || '',
                    type: e.getAttribute('type') || '',
                    ariaLabel: e.getAttribute('aria-label') || '',
                    visible: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)
                }))""",
            )
        except Exception as e:
            note("button inventory", False, e)

        # Strategy 1: Enter key in the password field -- submits most login
        # forms without needing to disambiguate which button is "the" submit
        # button, sidestepping the exact problem the first run hit.
        try:
            page.focus('input[type="password"]')
            page.keyboard.press("Enter")
            note("submit via Enter key", True)
        except Exception as e:
            note("submit via Enter key", False, e)

        time.sleep(3)

        # Strategy 2 (only if Enter didn't do it): click a button that looks
        # like a real submit control, explicitly excluding the nav button
        # that opens the modal (the one the first run's generic selector
        # mis-clicked).
        if not stop["done"]:
            try:
                # Confirmed via button-inventory dump (2026-07-17): the modal's
                # real submit control is data-qa="login-form-cta-log-in-button"
                # -- distinct from the outer nav button data-qa=
                # "login-cta-log-in-btn" that opens the modal in the first
                # place (same visible text "LOG IN", which is what fooled the
                # original :has-text() selector into matching the wrong one).
                btn_state = {}
                try:
                    btn_state = page.eval_on_selector(
                        '[data-qa="login-form-cta-log-in-button"]',
                        """e => {
                            const r = e.getBoundingClientRect();
                            const cs = getComputedStyle(e);
                            return {disabled: e.disabled, ariaDisabled: e.getAttribute('aria-disabled'),
                                    width: r.width, height: r.height,
                                    visibility: cs.visibility, display: cs.display,
                                    pointerEvents: cs.pointerEvents, opacity: cs.opacity};
                        }""",
                    )
                except Exception as e:
                    btn_state = {"eval_error": str(e)}
                note("submit button state before click", True, btn_state)

                page.click('[data-qa="login-form-cta-log-in-button"]', timeout=8_000)
                note("submit via login-form-cta-log-in-button", True)
            except Exception as e:
                note("submit via login-form-cta-log-in-button", False, e)
                # Diagnostic-only forced click: bypasses Playwright's
                # actionability wait (visible/stable/receives-events/enabled)
                # to tell "obscured by an overlay" apart from "genuinely
                # disabled" -- if this also produces no token, the button
                # itself isn't the blocker.
                try:
                    page.click('[data-qa="login-form-cta-log-in-button"]', timeout=5_000, force=True)
                    note("forced click (diagnostic)", True)
                except Exception as e2:
                    note("forced click (diagnostic)", False, e2)

        time.sleep(3)
        note("post-submit state", True, page.url)

        # Check specifically for an MFA challenge -- the DOM inventory showed
        # multifactor-authentication-{change-method,code-entry}-drawer
        # containers present (closed) even before login; a first-time
        # automated login from a new environment is a plausible trigger for
        # one to open, and if so, this is a hard stop no selector fix solves
        # -- it needs a human to read a code off email/SMS.
        try:
            mfa_state = page.eval_on_selector_all(
                "[class*='multifactor-authentication' i]",
                "els => els.map(e => e.className)",
            )
            mfa_open = [c for c in mfa_state if "closed" not in c]
            if mfa_open:
                note("MFA challenge detected", False, mfa_open)
            else:
                note("MFA challenge check", True, "none open")
        except Exception as e:
            note("MFA challenge check", False, e)

        # After login, browse into the sportsbook itself -- the auth headers
        # get attached to the odds/props API calls that fire once a sport
        # page loads, not necessarily on the login page itself.
        try:
            page.goto("https://sportsbook.caesars.com/us/az/bet/baseball/mlb",
                       wait_until="domcontentloaded", timeout=30_000)
            note("goto MLB odds page", True, page.url)
        except Exception as e:
            note("goto MLB odds page", False, e)

        deadline = time.time() + MAX_WAIT_SECONDS
        while not stop["done"] and time.time() < deadline:
            time.sleep(1)
        note("token capture", stop["done"])

        if not stop["done"]:
            push_debug(page, steps, github_token, button_inventory)

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

    harvested = harvest(email, password, github_token)
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
