"""
thescore_query_discovery.py — capture the live, schema-compatible GraphQL
query for theScore's CompetitionPageSectionLinesTabNode operation
================================================================================

WHY: scrape_thescore_curlffi() (betcouncil_auto_scraper.py) sends a persisted-
query GET using the hash the live frontend bundle maps to this operationName
-- confirmed correct via bundle-scraping self-heal. The server still rejects
it with real GraphQL schema errors ("Cannot query field 'abbreviation' on
type 'Team'", etc.), meaning the *query document* registered server-side for
that hash is stale, not the hash itself. Bundle-scraping can't fix this --
the actual current query text only exists inside a real Apollo Client
running in a browser.

TECHNIQUE (per Gemini's suggested "invalid hash trigger"): Apollo Client's
automatic persisted-query support reacts to a PersistedQueryNotFound error by
automatically re-sending the SAME query as a full POST body (query text +
variables, no hash) on the very next attempt. So: intercept the real request
this page already makes, corrupt its sha256Hash to something bogus, let it
hit the server, and capture whatever Apollo Client sends next -- that
retry IS the current, schema-compatible query document, straight from the
production frontend's own Apollo cache, not reconstructed or guessed.

This is read-only against theScore -- no login, no state changes, just
watching normal anonymous page-load traffic with one request's hash swapped.

Output: pushes the captured POST body (full query + variables), plus every
intercepted request/response around it, to Gist as
betcouncil_thescore_query_discovery.json for inspection.
"""

import base64
import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GIST_FILE = "betcouncil_thescore_query_discovery.json"
TARGET_OPERATION = "CompetitionPageSectionLinesTabNode"
MLB_PAGE_URL = "https://sportsbook.thescore.bet/"
MAX_WAIT_SECONDS = 45


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def push_to_gist(payload: dict, github_token: str) -> bool:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2, default=str)}}},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return True
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return False


def run() -> dict:
    from playwright.sync_api import sync_playwright

    findings = {
        "target_requests_seen": [],   # every request whose operationName matches, before/after mangling
        "retry_post_bodies": [],      # any POST to a graphql endpoint we capture after the mangled request
        "hash_mangled": False,
        "all_graphql_like_requests": [],  # broader net: anything with graphql/persisted_quer in the URL
        "all_request_hosts": {},          # host -> count, so we can see what actually loaded
    }
    state = {"mangled_once": False}

    def on_request(request):
        url = request.url
        try:
            host = url.split("/")[2]
        except Exception:
            host = "?"
        findings["all_request_hosts"][host] = findings["all_request_hosts"].get(host, 0) + 1
        if "graphql" in url.lower() or "persisted_quer" in url.lower():
            findings["all_graphql_like_requests"].append(
                {"method": request.method, "url": url[:250]})
        if "persisted_quer" in url and TARGET_OPERATION in url:
            findings["target_requests_seen"].append({
                "method": request.method, "url": url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            })
        # Any plain POST to something graphql-shaped, with a body containing
        # our target operation name -- this is what we're actually after.
        if request.method == "POST" and "graphql" in url.lower():
            try:
                post_data = request.post_data or ""
            except Exception:
                post_data = ""
            if TARGET_OPERATION in post_data:
                findings["retry_post_bodies"].append({
                    "url": url,
                    "post_data": post_data[:20000],
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                })
                log(f"Captured a graphql POST containing {TARGET_OPERATION} ({len(post_data)} chars)")

    def route_handler(route, request):
        url = request.url
        if (not state["mangled_once"] and "persisted_quer" in url
                and TARGET_OPERATION in url and "sha256Hash" in url):
            import re as _re
            mangled = _re.sub(
                r'("sha256Hash"\s*:\s*")[a-f0-9]{64}(")',
                r'\g<1>0000000000000000000000000000000000000000000000000000000000000000\g<2>',
                url,
            )
            # extensions is usually URL-encoded JSON in a query param -- handle
            # the plain-hash-in-path form too (persisted_queries/<hash>)
            mangled = _re.sub(
                r'(/persisted_queries/)[a-f0-9]{64}',
                r'\g<1>0000000000000000000000000000000000000000000000000000000000000000',
                mangled,
            )
            if mangled != url:
                state["mangled_once"] = True
                findings["hash_mangled"] = True
                log(f"Mangling hash in request: {url[:120]}...")
                route.continue_(url=mangled)
                return
        route.continue_()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        page.on("request", on_request)
        page.route("**/*", route_handler)

        try:
            page.goto(MLB_PAGE_URL, wait_until="networkidle", timeout=40_000)
        except Exception as e:
            log(f"Homepage load: {e}")

        # Dismiss cookie banner if present -- otherwise it can overlay nav links
        for sel in ["#onetrust-accept-btn-handler", "button:has-text('Accept')"]:
            try:
                page.click(sel, timeout=3_000)
                break
            except Exception:
                continue

        # Click into MLB via the real nav UI instead of guessing a URL path --
        # the first run showed /us/az/bet/baseball/mlb is a 404 on the live
        # site, which is why zero target requests ever fired.
        try:
            page.click("text=MLB", timeout=10_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception as e:
            log(f"Click MLB nav: {e}")

        import time
        deadline = time.time() + MAX_WAIT_SECONDS
        while time.time() < deadline and not findings["retry_post_bodies"]:
            time.sleep(1)

        try:
            findings["final_url"] = page.url
        except Exception as e:
            findings["final_url"] = f"<error: {e}>"
        try:
            findings["page_text"] = page.inner_text("body")[:3000]
        except Exception as e:
            findings["page_text"] = f"<error: {e}>"
        try:
            findings["screenshot_b64_png"] = base64.b64encode(
                page.screenshot(full_page=False, timeout=10_000)).decode("ascii")
        except Exception as e:
            findings["screenshot_b64_png"] = f"<error: {e}>"

        ctx.close()
        browser.close()

    return findings


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    findings = run()
    findings["captured_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    log(f"final_url: {findings.get('final_url')}")
    log(f"request hosts: {findings.get('all_request_hosts')}")
    log(f"graphql-like requests seen: {len(findings.get('all_graphql_like_requests', []))}")
    for r in findings.get("all_graphql_like_requests", [])[:10]:
        log(f"  {r['method']} {r['url']}")
    log(f"target_requests_seen: {len(findings['target_requests_seen'])}")
    log(f"retry_post_bodies captured: {len(findings['retry_post_bodies'])}")
    log(f"hash_mangled: {findings['hash_mangled']}")

    push_to_gist(findings, github_token)
    log(f"Pushed findings to {GIST_FILE}")
    return 0 if findings["retry_post_bodies"] else 1


if __name__ == "__main__":
    sys.exit(main())
