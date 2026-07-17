"""
props_source_discovery.py — probe candidate player-props sources (no auth)
================================================================================

One-off discovery script, not scheduled. Tests several candidate leads in
one run and dumps everything to Gist for inspection:

1. oddsjam.com/api/v2/positive-ev — the in-app browser harvester (app.py)
   hits this with no key from the main domain; api.oddsjam.com (the
   documented developer API) requires ODDSJAM_KEY. Testing whether the
   main-domain path actually works from a plain datacenter request or
   needs browser cookies/WAF-passing headers.
2. propswap.com/api/listings — same question for the browser harvester's
   PropSwap target.
3. Action Network — actionnetwork_refresh.py already covers
   /web/v1/scoreboard/{league} (game odds). Probing a spread of plausible
   player-props/markets paths on the same api.actionnetwork.com host,
   since the existing integration doesn't have props and the mobile app
   likely calls something adjacent.
4. OddsShopper — unknown surface entirely. Fetch the homepage HTML, look
   for Next.js/webpack chunk paths the way the MetaBet discovery worked,
   and grep any fetched JS for embedded API keys/hosts.

Not a production scraper. Findings only -- decide what's actually worth
building into a real scheduled script from what comes back here.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GIST_FILE = "betcouncil_props_source_discovery.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}

findings: dict = {"oddsjam": [], "propswap": [], "action_network_probes": [], "oddsshopper": []}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def probe(url: str, params: dict = None, referer: str = None):
    hdrs = dict(HEADERS)
    if referer:
        hdrs["Referer"] = referer
    try:
        r = requests.get(url, params=params, headers=hdrs, timeout=15)
        return {"url": r.url, "status": r.status_code, "body_snippet": r.text[:500],
                "content_type": r.headers.get("content-type", "")}
    except Exception as e:
        return {"url": url, "error": str(e)}


def run_oddsjam():
    log("Probing OddsJam...")
    for sport in ["mlb", "nba", "nfl"]:
        findings["oddsjam"].append(
            probe("https://oddsjam.com/api/v2/positive-ev",
                  {"sport": sport, "sportsbook": "pinnacle"},
                  referer="https://oddsjam.com/"))


def run_propswap():
    log("Probing PropSwap...")
    for sport in ["mlb", "nba", "nfl"]:
        findings["propswap"].append(
            probe("https://www.propswap.com/api/listings",
                  {"sport": sport, "status": "active", "limit": 20},
                  referer="https://www.propswap.com/"))


def run_action_network_probes():
    log("Probing Action Network for a props-specific endpoint...")
    candidates = [
        ("https://api.actionnetwork.com/web/v2/scoreboard/mlb", {"period": "game"}),
        ("https://api.actionnetwork.com/web/v1/props/mlb", {}),
        ("https://api.actionnetwork.com/web/v1/scoreboard/mlb", {"period": "player_props"}),
        ("https://api.actionnetwork.com/web/v1/markets/mlb", {}),
        ("https://api.actionnetwork.com/web/v2/props/mlb", {}),
        ("https://api.actionnetwork.com/web/v1/games/mlb", {}),
    ]
    for url, params in candidates:
        findings["action_network_probes"].append(probe(url, params, referer="https://www.actionnetwork.com/"))


def run_oddsshopper():
    log("Probing OddsShopper homepage + bundle...")
    home = probe("https://www.oddsshopper.com/")
    findings["oddsshopper"].append({"step": "homepage", **home})

    html = home.get("body_snippet", "")
    # homepage snippet is capped at 500 chars above for the summary log --
    # do a full separate fetch here since we need the whole HTML to find
    # chunk paths, not just the first 500 chars.
    try:
        full = requests.get("https://www.oddsshopper.com/", headers=HEADERS, timeout=15)
        html = full.text
    except Exception as e:
        findings["oddsshopper"].append({"step": "full_homepage_fetch_error", "error": str(e)})
        return

    chunk_paths = re.findall(r'/_next/static/chunks/[^"\'\s]*\.js', html)
    api_key_like = re.findall(r'["\']([A-Za-z0-9_\-]{20,50})["\']', html)
    findings["oddsshopper"].append({
        "step": "homepage_scan",
        "n_chunks_found": len(chunk_paths),
        "sample_chunks": chunk_paths[:5],
        "n_key_like_strings": len(api_key_like),
    })

    for path in chunk_paths[:5]:
        chunk_url = f"https://www.oddsshopper.com{path}" if path.startswith("/") else path
        try:
            r = requests.get(chunk_url, headers=HEADERS, timeout=15)
            keys_in_chunk = re.findall(r'apiKey["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-]{15,60})["\']', r.text, re.I)
            hosts_in_chunk = re.findall(r'https?://[a-zA-Z0-9.\-]*api[a-zA-Z0-9.\-]*', r.text)
            findings["oddsshopper"].append({
                "step": "chunk_scan", "chunk": path, "status": r.status_code,
                "keys_found": keys_in_chunk[:5],
                "api_hosts_found": list(set(hosts_in_chunk))[:10],
            })
        except Exception as e:
            findings["oddsshopper"].append({"step": "chunk_scan_error", "chunk": path, "error": str(e)})


def push_to_gist(payload: dict, github_token: str) -> bool:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2, default=str)}}},
        timeout=30,
    )
    return resp.status_code in (200, 201)


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    for fn in (run_oddsjam, run_propswap, run_action_network_probes, run_oddsshopper):
        try:
            fn()
        except Exception as e:
            log(f"{fn.__name__} crashed: {e}")

    findings["captured_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ok = push_to_gist(findings, github_token)
    log(f"Pushed: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
