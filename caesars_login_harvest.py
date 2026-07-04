"""
caesars_login_harvest.py — run this LOCALLY (not on Streamlit Cloud) whenever
the Caesars JWT expires (~24h) and fetch_caesars_direct() starts returning
empty/401s.

WHAT THIS DOES
--------------
1. Opens a real, visible Chromium window pointed at sportsbook.caesars.com.
2. Waits for YOU to log into your Caesars account in that window.
3. As soon as your login triggers a real API call, captures the Bearer JWT
   + AWS WAF token Caesars generates for that session.
4. Pushes both to the same GitHub Gist BetCouncil already reads from
   ("caesars_tokens.json") — no copy-paste into Streamlit secrets needed.
5. Streamlit Cloud picks up the fresh token automatically on its next
   fetch_caesars_direct() call (it already reads from this Gist key first,
   see fetchers.py load_from_gist("caesars_tokens", None)).

HOW TO USE
----------
    pip install playwright requests
    playwright install chromium
    python caesars_login_harvest.py

Then just log into Caesars normally in the window that opens. The script
exits on its own once it captures a valid token (or after ~3 minutes if you
haven't logged in yet — just re-run it when you're ready).

WHY THIS IS SEPARATE FROM harvest_caesars_tokens() IN fetchers.py
------------------------------------------------------------------
fetchers.py's harvest_caesars_tokens() ASSUMES a Caesars session is already
logged in on the machine running it — it has no login step of its own,
because Streamlit Cloud has no display for you to log in on. This script
is the missing piece: it's the thing you actually run locally, gives you a
real window to log into, and reuses the exact same capture + Gist-push
logic so the two stay in sync.

RISK NOTE (carried over from fetchers.py's own comment — read it):
This uses YOUR real logged-in Caesars account session, not an anonymous
API key. The JWT's "sub" claim ties every automated request back to your
account. That's a deliberate tradeoff already made elsewhere in this repo,
not something new introduced here — but it's worth remembering each time
you run this.
"""
import json
import os
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PWTimeout
except ImportError:
    print("Missing dependency: pip install playwright && playwright install chromium")
    sys.exit(1)


# ── Config — reads from environment variables, falls back to the values ────
# already used elsewhere in this repo (config.py) so this script stays in
# sync without needing its own separate secrets file.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_GIST_ID = os.environ.get("GITHUB_GIST_ID", "7e52e1c2c2054847c7c4663a157386c5")
CAESARS_URL = os.environ.get("CAESARS_URL", "https://sportsbook.caesars.com/us/az/bet")
MAX_WAIT_SECONDS = int(os.environ.get("CAESARS_LOGIN_MAX_WAIT", "180"))  # 3 min to log in


def harvest_and_push() -> dict:
    if not GITHUB_TOKEN:
        print(
            "WARNING: GITHUB_TOKEN not set in environment. The token will be "
            "captured and printed below, but NOT pushed to the Gist "
            "automatically. Set GITHUB_TOKEN as an environment variable to "
            "enable the automatic push.\n"
        )

    harvested: dict = {}
    stop = {"done": False}

    def on_request(request):
        if stop["done"]:
            return
        if "americanwagering.com" not in request.url:
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
        harvested["captured_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        stop["done"] = True
        print("\n✅ Token captured! (You can keep browsing or close the window.)\n")

    with sync_playwright() as pw:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,900",
        ]
        browser = pw.chromium.launch(headless=False, args=launch_args)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1280, "height": 900},
        )
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        page = ctx.new_page()
        page.on("request", on_request)

        print(f"Opening {CAESARS_URL} ...")
        print(">>> Log into your Caesars account in the window that just opened. <<<")
        print(f"Waiting up to {MAX_WAIT_SECONDS}s for login...\n")

        try:
            page.goto(CAESARS_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            print(f"(Navigation warning, continuing anyway: {e})")

        deadline = time.time() + MAX_WAIT_SECONDS
        while not stop["done"] and time.time() < deadline:
            remaining = int(deadline - time.time())
            print(f"\rWaiting for login... {remaining}s remaining  ", end="", flush=True)
            time.sleep(1)
        print()

        ctx.close()
        browser.close()

    if not harvested.get("bearer_jwt"):
        print(
            "\n❌ No token captured. Either you didn't log in within the time "
            "window, or Caesars changed something. Re-run the script and log "
            "in a bit faster, or increase CAESARS_LOGIN_MAX_WAIT."
        )
        return {}

    print(f"Captured at: {harvested['captured_at']}")
    print(f"Bearer JWT (first 40 chars): {harvested['bearer_jwt'][:40]}...")
    print(f"WAF token present: {bool(harvested.get('waf_token'))}")

    if GITHUB_TOKEN:
        try:
            resp = requests.patch(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"files": {"caesars_tokens.json": {"content": json.dumps(harvested, indent=2)}}},
                timeout=10,
            )
            if resp.status_code < 300:
                print("\n✅ Pushed to Gist — BetCouncil will pick this up automatically.")
            else:
                print(f"\n❌ Gist push failed: HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"\n❌ Gist push failed: {e}")
    else:
        print("\nGITHUB_TOKEN not set — paste this into Streamlit secrets manually instead:")
        print(json.dumps(harvested, indent=2))

    return harvested


if __name__ == "__main__":
    harvest_and_push()
