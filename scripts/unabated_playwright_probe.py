"""
unabated_playwright_probe.py — real browser network capture to find Unabated's actual API
================================================================================

Two prior attempts (unabated.com/api/lines, data.unabated.com/market/{sport}/
props/odds) both returned a generic Next.js 404 page server-side — meaning
the real data loads client-side after JS hydration, and no amount of URL
guessing will find it without watching what a real browser actually
requests. This uses headless Chromium (Playwright, same proven pattern as
fetch_mybookie_lines in fetchers.py) to load unabated.com's MLB odds page
for real and record every XHR/fetch response that comes back as JSON,
rather than guessing another URL.

This is a DIAGNOSTIC, not a production scraper — it dumps everything it
sees to the debug Gist file for inspection. Once the real endpoint is
identified from that dump, a proper scraper gets built against it directly
(likely back to a simple requests-based script once the real URL/headers
are known, same as every other source in this repo — Playwright is only
needed to discover the URL, not necessarily to run on a schedule).
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def push_files(files_payload: dict, github_token: str) -> int:
    import time
    for attempt in range(3):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=60,
        )
        if resp.status_code in (200, 201):
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 2:
                wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                time.sleep(wait)
                continue
            if missing:
                log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                return len(files_payload) - len(missing)
            return len(files_payload)
        if resp.status_code == 409 and attempt < 2:
            time.sleep((attempt + 1) * 4)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeout
    except ImportError:
        log("playwright not installed")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    captured_responses = []

    def on_response(response):
        url = response.url
        # Skip obvious static assets / analytics noise
        if any(x in url for x in [".js", ".css", ".png", ".svg", ".woff",
                                    "google", "gtm", "analytics", "sentry",
                                    "facebook", "hotjar", "segment"]):
            return
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            status = response.status
            body_preview = None
            try:
                body = response.json()
                body_preview = json.dumps(body, default=str)[:1500]
            except Exception:
                body_preview = "<could not parse as json>"
            captured_responses.append({
                "url": url, "status": status,
                "request_headers": dict(response.request.headers),
                "body_preview": body_preview,
            })
        except Exception as e:
            captured_responses.append({"url": url, "capture_error": str(e)})

    try:
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                "--window-size=1280,800",
            ]
            browser = pw.chromium.launch(headless=True, args=launch_args)
            ctx = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                locale="en-US", timezone_id="America/New_York",
                viewport={"width": 1280, "height": 800},
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)
            page = ctx.new_page()
            page.on("response", on_response)

            for target_url in [
                "https://unabated.com/mlb/odds",
                "https://unabated.com/mlb",
                "https://unabated.com/",
            ]:
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_timeout(8000)  # let XHRs fire after hydration
                    log(f"visited {target_url}, {len(captured_responses)} JSON responses so far")
                    if captured_responses:
                        break  # found something, no need to try the other URLs
                except PWTimeout:
                    log(f"timeout on {target_url}")
                except Exception as e:
                    log(f"error on {target_url}: {e}")

            browser.close()
    except Exception as e:
        log(f"Playwright launch/run error: {e}")
        push_files({"betcouncil_unabated_playwright_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "error": str(e),
                                    "responses_before_error": captured_responses}, indent=2, default=str)
        }}, github_token)
        return 1

    log(f"Total JSON responses captured: {len(captured_responses)}")
    files_payload = {
        "betcouncil_unabated_playwright_debug.json": {
            "content": json.dumps({
                "captured_at": now_iso,
                "total_json_responses": len(captured_responses),
                "responses": captured_responses[:30],
            }, indent=2, default=str)
        }
    }
    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if captured_responses else 1


if __name__ == "__main__":
    sys.exit(main())
