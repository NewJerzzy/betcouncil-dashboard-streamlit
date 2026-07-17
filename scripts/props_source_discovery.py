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

    # Direct comparison: does period=player_props actually change the
    # response shape vs period=game, or is the param silently ignored?
    try:
        game_r = requests.get("https://api.actionnetwork.com/web/v1/scoreboard/mlb",
                               params={"period": "game"}, headers=HEADERS, timeout=15)
        props_r = requests.get("https://api.actionnetwork.com/web/v1/scoreboard/mlb",
                                params={"period": "player_props"}, headers=HEADERS, timeout=15)
        game_data = json.loads(game_r.text) if game_r.status_code == 200 else {}
        props_data = json.loads(props_r.text) if props_r.status_code == 200 else {}
        game_games = game_data.get("games", [])
        props_games = props_data.get("games", [])
        game_keys = set(game_games[0].keys()) if game_games else set()
        props_keys = set(props_games[0].keys()) if props_games else set()

        # The existing scraper filters odds to type=="game" specifically --
        # implying other type values exist in the same array. Check what's
        # actually in there across both period variants.
        def odds_types(games):
            types = set()
            for g in games:
                for o in (g.get("odds") or []):
                    if isinstance(o, dict):
                        types.add(o.get("type"))
            return types

        findings["action_network_probes"].append({
            "step": "period_param_comparison",
            "game_len": len(game_r.text), "props_len": len(props_r.text),
            "n_games_game_period": len(game_games), "n_games_props_period": len(props_games),
            "game_first_game_keys": sorted(game_keys),
            "props_first_game_keys": sorted(props_keys),
            "keys_differ": game_keys != props_keys,
            "odds_types_in_game_period": sorted(str(t) for t in odds_types(game_games)),
            "odds_types_in_props_period": sorted(str(t) for t in odds_types(props_games)),
        })

        # If a non-"game" type exists, dump one full example so field names
        # are visible without guessing.
        for g in props_games:
            for o in (g.get("odds") or []):
                if isinstance(o, dict) and o.get("type") != "game":
                    findings["action_network_probes"].append({
                        "step": "non_game_odds_sample", "sample": o,
                    })
                    break
            else:
                continue
            break
    except Exception as e:
        findings["action_network_probes"].append({"step": "period_param_comparison_error", "error": str(e)})


def run_oddsshopper():
    log("Probing OddsShopper homepage + bundle...")
    try:
        _run_oddsshopper_inner()
    except Exception as e:
        import traceback
        findings["oddsshopper"].append({"step": "FATAL_EXCEPTION", "error": str(e),
                                          "traceback": traceback.format_exc()})


def _run_oddsshopper_inner():
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

    # Guessed sub-page paths above may be wrong -- extract real internal
    # links from the homepage's own <a href> / Next.js <Link> targets
    # rather than continuing to guess blind.
    real_links = sorted(set(re.findall(r'href="(/[a-zA-Z0-9\-/]+)"', html)))
    findings["oddsshopper"].append({"step": "real_links_found", "links": real_links[:30]})

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

    # Homepage-only chunks are generic Next.js framework code (webpack,
    # polyfills, main-app shell) -- route-specific data-fetching logic
    # loads on demand when visiting an actual props page, not on "/".
    # Fetch a real MLB props sub-page and repeat the chunk scan there.
    # Try real links found on the homepage that look like odds/props
    # pages, since the guessed paths above all 404'd. Prioritize
    # expert-picks/free pages specifically -- those are the actual props
    # display, not blog articles that happen to mention "bet" or "mlb".
    priority = [l for l in real_links if l.startswith("/odds/shop/")]
    other_plausible = [l for l in real_links if any(
        kw in l.lower() for kw in ("liveodds", "expert-picks/free")) and l not in priority]
    findings["oddsshopper"].append({"step": "filtered_lists_debug",
                                      "priority": priority, "other_plausible": other_plausible})
    for sub_path in (priority + other_plausible)[:6]:
        sub_url = f"https://www.oddsshopper.com{sub_path}"
        try:
            r = requests.get(sub_url, headers=HEADERS, timeout=15)
        except Exception as e:
            findings["oddsshopper"].append({"step": "subpage_fetch_error", "path": sub_path, "error": str(e)})
            continue
        findings["oddsshopper"].append({"step": "subpage", "path": sub_path, "status": r.status_code,
                                          "body_len": len(r.text)})
        if r.status_code != 200:
            continue

        # Check for Next.js __NEXT_DATA__ -- SSR pages often pre-render
        # initial props server-side into this script tag, which would
        # contain real odds data directly without needing to reverse a
        # runtime XHR call.
        next_data_match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if next_data_match:
            try:
                next_data = json.loads(next_data_match.group(1))
                page_props = (next_data.get("props", {}) or {}).get("pageProps", {})
                findings["oddsshopper"].append({
                    "step": "next_data_found", "path": sub_path,
                    "top_level_keys": list(next_data.keys()),
                    "page_props_keys": list(page_props.keys()) if isinstance(page_props, dict) else None,
                    "page_props_sample": json.dumps(page_props, default=str)[:2000],
                })
            except Exception as e:
                findings["oddsshopper"].append({"step": "next_data_parse_error", "path": sub_path, "error": str(e)})
        else:
            findings["oddsshopper"].append({"step": "no_next_data_found", "path": sub_path})
        sub_chunks = re.findall(r'/_next/static/chunks/[^"\'\s]*\.js', r.text)
        new_chunks = [c for c in sub_chunks if c not in chunk_paths]
        findings["oddsshopper"].append({"step": "subpage_new_chunks", "path": sub_path,
                                          "new_chunks": new_chunks[:8]})
        for chunk in new_chunks[:6]:
            chunk_url = f"https://www.oddsshopper.com{chunk}"
            try:
                cr = requests.get(chunk_url, headers=HEADERS, timeout=15)
                keys_in_chunk = re.findall(r'apiKey["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-]{15,60})["\']', cr.text, re.I)
                hosts_in_chunk = re.findall(r'https?://[a-zA-Z0-9.\-]*(?:api|odds)[a-zA-Z0-9.\-]*', cr.text, re.I)
                findings["oddsshopper"].append({
                    "step": "subpage_chunk_scan", "path": sub_path, "chunk": chunk, "status": cr.status_code,
                    "keys_found": keys_in_chunk[:5],
                    "api_hosts_found": list(set(hosts_in_chunk))[:10],
                })
            except Exception as e:
                findings["oddsshopper"].append({"step": "subpage_chunk_scan_error", "chunk": chunk, "error": str(e)})


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
