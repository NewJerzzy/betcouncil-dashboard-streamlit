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


def _extract_stream_payload(html: str) -> list:
    """
    Pick6 (React Router v7) streams its full loader data directly into
    the initial HTML via:
        window.__reactRouterContext.streamController.enqueue("[ ...escaped JSON... ]")
    Confirmed 2026-07-16 (via cross-check against Replit's report, plus
    independent evidence: raw HTML body size — 851KB captured here vs.
    "858 KB" reported — is a close match). This is NOT a normal
    __NEXT_DATA__/embedded-JSON-object pattern (that first attempt at
    this script assumed the wrong SSR mechanism and found nothing) — the
    payload here is a JS string literal argument to .enqueue(), so it
    needs to be extracted and un-escaped as a string before json.loads,
    not parsed as an inline object.

    Returns the flat array (~3000+ elements) as-is, unresolved — see
    _resolve_refs() for turning "_N"-style references into their real
    values.
    """
    m = re.search(
        r'streamController\.enqueue\(\s*"((?:[^"\\]|\\.)*)"\s*\)',
        html, re.DOTALL,
    )
    if not m:
        return []
    raw_str = m.group(1)
    try:
        # The captured text is itself a JS string literal (escaped) —
        # decoding it as a JSON string turns \" \\ \n etc. back into
        # real characters, giving us the actual JSON array text.
        unescaped = json.loads('"' + raw_str + '"')
        return json.loads(unescaped)
    except (json.JSONDecodeError, ValueError) as e:
        DEBUG_LOG.append({"note": f"stream payload found but failed to parse: {e}",
                           "raw_len": len(raw_str), "raw_snippet": raw_str[:500]})
        return []


def _resolve_refs(obj, array: list, depth=0, max_depth=20):
    """
    Recursively resolve "_N"-style reference dicts (single key matching
    `_\\d+`) into the value at that index of the flat array. Exact
    reference format wasn't independently verified before this first
    deploy — this handles the single-key `{"_N": true/anything}` shape
    Replit described; if the real shape differs, resolution will just
    no-op on unmatched dicts rather than crash, and self-diagnostics
    will show a low apply rate so the mismatch is visible.
    """
    if depth > max_depth:
        return obj
    if isinstance(obj, dict):
        if len(obj) == 1:
            (k, _v), = obj.items()
            if isinstance(k, str) and re.fullmatch(r"_\d+", k):
                idx = int(k[1:])
                if 0 <= idx < len(array):
                    return _resolve_refs(array[idx], array, depth + 1, max_depth)
        return {k: _resolve_refs(v, array, depth + 1, max_depth) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_refs(v, array, depth + 1, max_depth) for v in obj]
    return obj


def _build_lookup_tables(array: list) -> tuple:
    """
    Scan the flat array for player-profile dicts (has dkId + a name-like
    field) and stat-type dicts (has an id matching a market's
    pickSixMarketId + a name/label field), building dkId->name and
    marketId->stat_name lookups. Exact field names for these two
    weren't given directly — best-effort scan, logged via debug if
    either lookup ends up empty so a schema mismatch is visible rather
    than silently producing "Unknown Player" for everything.
    """
    player_names, stat_names = {}, {}
    for item in array:
        if not isinstance(item, dict):
            continue
        if "dkId" in item:
            name = (item.get("displayName") or item.get("fullName") or
                    item.get("name") or
                    (f"{item.get('firstName','')} {item.get('lastName','')}".strip()))
            if name:
                player_names[item["dkId"]] = name
        for id_key in ("pickSixMarketId", "marketId", "id"):
            if id_key in item and isinstance(item.get(id_key), int):
                label = item.get("marketName") or item.get("statName") or item.get("name") or item.get("label")
                if label and id_key != "id":  # "id" is too generic/ambiguous to trust alone
                    stat_names[item[id_key]] = label
    return player_names, stat_names


def fetch_sport_props(sport: str) -> list:
    url = f"{BASE_URL}?sport={sport}"
    r = requests.get(url, headers=HEADERS, timeout=25)
    DEBUG_LOG.append({"sport": sport, "url": url, "status": r.status_code,
                       "body_len": len(r.text)})
    if r.status_code != 200:
        return []

    array = _extract_stream_payload(r.text)
    if not array:
        DEBUG_LOG.append({"sport": sport, "note": "no streamController.enqueue payload found or failed to parse"})
        return []

    player_names, stat_names = _build_lookup_tables(array)
    if sport == "MLB":
        DEBUG_LOG.append({"sport": sport, "array_len": len(array),
                           "player_names_found": len(player_names), "stat_names_found": len(stat_names)})
        if not player_names or not stat_names:
            # Capture real samples to fix field names precisely instead of
            # guessing again — first few dicts containing "dkId" (should be
            # player-profile-like), and first few small dicts with an
            # integer id-ish field (candidate stat-type lookups).
            dkid_samples = [item for item in array if isinstance(item, dict) and "dkId" in item][:3]
            small_int_id_samples = [
                item for item in array
                if isinstance(item, dict) and 1 <= len(item) <= 4
                and any(isinstance(v, int) for v in item.values())
            ][:5]
            DEBUG_LOG.append({"sport": sport, "dkid_samples": dkid_samples,
                               "small_int_id_samples": small_int_id_samples})

    normalized = []
    for item in array:
        if not isinstance(item, dict) or "pickableId" not in item:
            continue
        resolved = _resolve_refs(item, array)
        entities = resolved.get("entities", [])
        dk_id = entities[0].get("dkId") if entities and isinstance(entities[0], dict) else None
        player = player_names.get(dk_id, f"dkId_{dk_id}" if dk_id else None)

        for market in resolved.get("activePickableMarkets", []):
            if not isinstance(market, dict):
                continue
            line = market.get("targetValue")
            market_id = market.get("pickSixMarketId")
            stat_name = stat_names.get(market_id, f"market_{market_id}" if market_id else None)
            for sel in market.get("activeSelections", []):
                if not isinstance(sel, dict):
                    continue
                if not player or line is None:
                    continue
                normalized.append({
                    "player": player, "stat_name": stat_name, "line": line,
                    "multiplier": sel.get("standingsMultiplier"), "sport": sport,
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
