"""
pick6_refresh.py — DraftKings Pick6 props scraper (public SSR embedded JSON, no auth)
================================================================================

DraftKings Pick6 embeds its full prop board directly in the page's
server-rendered HTML (confirmed live 2026-07-16 via direct fetch —
real current games and props present with no login, e.g. today's
actual MLB slate). This matches fetch_pick6_props_from_gist()'s
existing docstring in fetchers.py, which already describes this same
approach — that reader function and its expected filename
(pick6_props_live.json) predate this script.

Context: an external investigation (Replit) ran an equivalent scraper
once, by hand, producing 101 real props pushed directly to
pick6_props_live.json — confirmed genuinely fresh when checked
independently. But no script or workflow for it was ever committed to
this repo, so that data would have gone stale with nothing to refresh
it. This is the actual committed, scheduled replacement.

Exact JSON structure wasn't independently confirmed byte-for-byte
before this first deploy (confirmed real DATA is present via a fetch
that renders to text, but the underlying raw HTML/JSON shape wasn't
directly inspected) — ships with self-diagnostic logging so a
structure mismatch is caught immediately rather than silently
producing nothing, same precaution used for every first-deploy
harvester this session.

Pushes to pick6_props_live.json (existing filename/schema — no changes
needed to fetch_pick6_props_from_gist on the read side).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://pick6.draftkings.com/"
SPORTS = ["MLB", "NBA", "NFL", "NHL", "WNBA", "SOCCER", "UFC", "PGA+TOUR", "NASCAR"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _extract_next_data(html: str) -> dict:
    """
    Next.js apps embed their SSR page-data payload in a
    <script id="__NEXT_DATA__" type="application/json">{...}</script>
    tag. Regex-extract rather than full HTML parsing since we only need
    this one script tag's contents.
    """
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _find_any_json_scripts(html: str) -> list:
    """
    Fallback survey when __NEXT_DATA__ isn't present: find every
    <script> tag that looks like it might hold embedded JSON (has an
    id/type suggesting data, or a large inline blob), so the debug
    output shows what's actually on the page instead of guessing blind
    a second time.
    """
    candidates = []
    for m in re.finditer(r'<script([^>]*)>(.*?)</script>', html, re.DOTALL):
        attrs, body = m.group(1), m.group(2).strip()
        if len(body) < 200:
            continue
        looks_jsonish = body.startswith("{") or body.startswith("[")
        has_data_hint = any(h in attrs.lower() for h in ["json", "data", "state", "__"])
        if looks_jsonish or has_data_hint:
            candidates.append({
                "attrs": attrs.strip()[:200],
                "body_len": len(body),
                "body_snippet": body[:400],
            })
    return candidates[:8]


def _find_props_list(obj, depth=0, max_depth=12):
    """
    Walk the Next.js data tree looking for a list of dicts that look
    like prop entries (has a player name + a numeric line/target value)
    — structure-agnostic since the exact nesting path wasn't verified
    before this first deploy.
    """
    if depth > max_depth:
        return None
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        sample = obj[0]
        keys_lower = {k.lower() for k in sample.keys()}
        if ({"player", "playername", "firstname"} & keys_lower) and \
           ({"line", "targetvalue", "statvalue"} & keys_lower):
            return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = _find_props_list(v, depth + 1, max_depth)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_props_list(item, depth + 1, max_depth)
            if found:
                return found
    return None


def fetch_sport_props(sport: str) -> list:
    url = f"{BASE_URL}?sport={sport}"
    r = requests.get(url, headers=HEADERS, timeout=25)
    DEBUG_LOG.append({"sport": sport, "url": url, "status": r.status_code,
                       "body_len": len(r.text)})
    if r.status_code != 200:
        return []

    next_data = _extract_next_data(r.text)
    if not next_data:
        entry = {"sport": sport, "note": "no __NEXT_DATA__ script tag found"}
        if sport == "MLB":
            entry["json_script_survey"] = _find_any_json_scripts(r.text)
            entry["html_head_snippet"] = r.text[:1500]
        DEBUG_LOG.append(entry)
        return []

    props_list = _find_props_list(next_data)
    if not props_list:
        DEBUG_LOG.append({"sport": sport, "note": "__NEXT_DATA__ found but no matching props list inside it",
                           "top_level_keys": list(next_data.keys())[:20]})
        return []

    normalized = []
    for p in props_list:
        player = p.get("player") or p.get("playerName") or p.get("firstName", "") + " " + p.get("lastName", "")
        stat_name = p.get("stat_name") or p.get("statName") or p.get("marketName") or p.get("category")
        line = p.get("line") or p.get("targetValue") or p.get("statValue")
        multiplier = p.get("multiplier") or p.get("standingsMultiplier")
        if not player or line is None:
            continue
        normalized.append({
            "player": str(player).strip(), "stat_name": stat_name,
            "line": line, "multiplier": multiplier, "sport": sport,
        })
    return normalized


def push_to_gist(props: list, github_token: str) -> bool:
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": "pick6_ssr_scraper",
        "props": props,
    }
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": {"pick6_props_live.json": {"content": json.dumps(payload)}}},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return True
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return False


def push_debug(github_token: str) -> None:
    try:
        requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": {"betcouncil_pick6_debug.json": {
                "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                        "requests": DEBUG_LOG[:20]}, indent=2)
            }}},
            timeout=30,
        )
    except Exception:
        pass


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    all_props = []
    for sport in SPORTS:
        try:
            props = fetch_sport_props(sport)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if props:
            log(f"  {sport}: {len(props)} props")
            all_props.extend(props)
        else:
            log(f"  {sport}: 0 props")

    push_debug(github_token)

    if not all_props:
        log("No props captured across any sport — pushing debug log only, not overwriting existing data with empty")
        return 1

    ok = push_to_gist(all_props, github_token)
    log(f"Pushed {len(all_props)} total props" if ok else "Push FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
