"""
theoddsgap.com dfs-edges — PrizePicks/Underdog/DK Pick6/Betr pick'em
lines graded against real sportsbook market lines, with an estimated
win% per pick.

Confirmed live 2026-08-04 via GH Actions (both with and without Cache-
Control/Pragma no-cache headers returned identical fresh data,
generated_at matching the actual request time -- the earlier "stale"
result was specific to a different fetch path, not a real requirement
of this endpoint from a normal server). GET https://theoddsgap.com/api/dfs-edges,
no params, no auth.

Real fields confirmed via live capture: app, app_key, app_line,
commence_time, event, kind ("goblin"/"demon"/"alt"/"std"), link,
market, market_label, market_line, mult (DK Pick6/Underdog only),
mult_under (Underdog only), player, side, sport, win_pct.

NOTE: the original spec described a "thin" (low book coverage) flag --
not present anywhere in the real live response captured. Not built;
would be guessing at a field that doesn't exist.

Only keeps the "edges" array (has a real win_pct). Skips "unrated"
(win_pct: null -- not actually an edge assessment, just an unrated
listing) to keep payload size down and match what's actually useful
for board matching.

Pushes merged into betcouncil_evbets_combined.json under a
"theoddsgap_edges" key.
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://theoddsgap.com/api/dfs-edges"
SHARED_FILE = "betcouncil_theoddsgap_edges_feed.json"
MERGE_KEY = "theoddsgap_edges"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def log(msg: str):
    print(f"[theoddsgap_edges] {msg}", flush=True)


def fetch_edges() -> list:
    r = requests.get(API_URL, headers=HEADERS, timeout=25)
    if r.status_code != 200:
        log(f"HTTP {r.status_code}")
        return []
    data = r.json()
    edges = data.get("edges", [])
    log(f"Fetched {len(edges)} rated edges (generated_at={data.get('generated_at')})")
    return edges


def normalize_edge(e: dict) -> dict:
    out = {
        "app": e.get("app", ""),
        "app_key": e.get("app_key", ""),
        "app_line": e.get("app_line"),
        "market_line": e.get("market_line"),
        "market": e.get("market", ""),
        "market_label": e.get("market_label", ""),
        "player": e.get("player", ""),
        "side": e.get("side", ""),
        "kind": e.get("kind", ""),
        "win_pct": e.get("win_pct"),
        "event": e.get("event", ""),
        "sport": str(e.get("sport", "")).upper(),
        "commence_time": e.get("commence_time", ""),
        "link": e.get("link", ""),
    }
    if "mult" in e:
        out["mult"] = e["mult"]
    if "mult_under" in e:
        out["mult_under"] = e["mult_under"]
    return out


def push_files(merged_payload: dict, github_token: str) -> int:
    """Same proven read-modify-write-with-verification pattern used
    across every other script sharing this file."""
    for outer_attempt in range(3):
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                raw_url = r_files[SHARED_FILE]["raw_url"]
                existing = requests.get(raw_url, timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        pre_write_keys = set(existing.keys())
        existing[MERGE_KEY] = merged_payload
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        write_ok = False
        for attempt in range(5):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    write_ok = True
                    break
                if attempt < 4:
                    wait = min((attempt + 1) * 5, 30)
                    log(f"Push returned 200 but {SHARED_FILE} missing from response -- retrying in {wait}s")
                    time.sleep(wait)
                    continue
                log(f"Push returned 200 but {SHARED_FILE} still missing after retries -- treating as failed")
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 4:
                base_wait = min(10 * (2 ** attempt), 90)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0

        if not write_ok:
            return 0

        try:
            time.sleep(2)
            r2 = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                               headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                               timeout=15)
            raw_url2 = r2.json().get("files", {}).get(SHARED_FILE, {}).get("raw_url")
            post_write = requests.get(raw_url2, timeout=15).json() if raw_url2 else {}
            post_write_keys = set(post_write.keys())
            lost_keys = pre_write_keys - post_write_keys - {MERGE_KEY}
            if MERGE_KEY in post_write_keys and not lost_keys:
                return 1
            log(f"Post-write verification found lost keys {lost_keys} or missing own key -- retrying full cycle (outer attempt {outer_attempt+1}/3)")
        except Exception as e:
            log(f"Post-write verification failed to check: {e} -- treating write as successful anyway")
            return 1

    log("Gave up after 3 full read-modify-write cycles -- concurrent writers kept colliding")
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    import atexit
    _lock_token = acquire_lock(GIST_ID, github_token, "theoddsgap_edges_feed", holder="theoddsgap_edges", max_attempts=7)
    if not _lock_token:
        log("Could not acquire theoddsgap_edges_feed lock after retries -- skipping this run to avoid a collision")
        return 1
    atexit.register(lambda: release_lock(GIST_ID, github_token, "theoddsgap_edges_feed", _lock_token))

    try:
        raw_edges = fetch_edges()
    except Exception as e:
        log(f"FATAL: fetch error — {e}")
        return 1

    if not raw_edges:
        log("FATAL: zero edges returned")
        return 1

    normalized = [normalize_edge(e) for e in raw_edges]
    by_app = {}
    for e in normalized:
        by_app.setdefault(e["app"], 0)
        by_app[e["app"]] += 1
    for app, count in by_app.items():
        log(f"  {app}: {count}")

    merged_payload = {
        "source": "theoddsgap",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "edges": normalized,
    }

    pushed = push_files(merged_payload, github_token)
    log(f"Pushed {len(normalized)} edges: {'ok' if pushed else 'FAILED'}")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
