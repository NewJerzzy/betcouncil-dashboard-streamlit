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


def _build_idx_to_name(array: list) -> dict:
    """_N key -> real field name, built once from the flat array. Safe
    by construction: a '_N' key literally means 'the field name is
    arr[N]', so this direct mapping is always correct regardless of
    what else arr[N] might also represent as data elsewhere."""
    return {i: v for i, v in enumerate(array) if isinstance(v, str)}


def _resolve_refs(obj, array: list, idx_to_name: dict, depth=0, max_depth=15):
    """
    DK's compression scheme changed fundamentally (confirmed via live
    re-test 2026-07-25, previous version of this function assumed
    literal string keys like "dkId" and a single-key {"_N": val}
    reference-marker pattern -- both wrong now). Current real format:
    EVERY dict key is a "_N" reference where array[N] is the real field
    name, and EVERY dict value is an index into array needing exactly
    one dereference. Only recurses further into the dereferenced result
    if it's itself a container (dict/list) -- a literal scalar found
    nested inside an already-resolved list (e.g. a real comp-ID number)
    is left alone, not treated as a further reference to chase.
    """
    if depth > max_depth:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith("_") and k[1:].isdigit():
                real_key = idx_to_name.get(int(k[1:]), k)
            else:
                real_key = k
            deref = array[v] if isinstance(v, int) and 0 <= v < len(array) else v
            if isinstance(deref, (dict, list)):
                out[real_key] = _resolve_refs(deref, array, idx_to_name, depth + 1, max_depth)
            else:
                out[real_key] = deref
        return out
    if isinstance(obj, list):
        return [_resolve_refs(v, array, idx_to_name, depth + 1, max_depth) if isinstance(v, dict) else v
                for v in obj]
    return obj


def _build_lookup_tables(array: list, idx_to_name: dict) -> tuple:
    """
    Scan the flat array for player-ID dicts (Shape B: has the compressed
    key for "dkId") and market-type dicts (Shape D: has the compressed
    key for "pickSixMarketId" + "name"), building dkId->name and
    marketId->stat_name lookups. Player names (Shape A) and player IDs
    (Shape B) are confirmed to be SEPARATE dict shapes in the real data
    -- this builds a dkId->name correlation from whatever fields are
    actually present once each candidate dict is fully resolved, logging
    via debug if either lookup ends up empty so a further schema
    mismatch is visible rather than silently producing "Unknown Player".
    """
    dkid_key = idx_to_name and next((k for k, v in idx_to_name.items() if v == "dkId"), None)
    market_id_key = next((k for k, v in idx_to_name.items() if v == "pickSixMarketId"), None)
    name_key = next((k for k, v in idx_to_name.items() if v == "name"), None)
    fullname_key = next((k for k, v in idx_to_name.items() if v == "fullName"), None)

    player_names, stat_names = {}, {}
    for item in array:
        if not isinstance(item, dict):
            continue
        if dkid_key is not None and f"_{dkid_key}" in item:
            resolved = _resolve_refs(item, array, idx_to_name)
            dk_id = resolved.get("dkId")
            name = resolved.get("fullName") or resolved.get("name")
            if dk_id and name:
                player_names[dk_id] = name
        if market_id_key is not None and f"_{market_id_key}" in item:
            resolved = _resolve_refs(item, array, idx_to_name)
            mkt_id, label = resolved.get("pickSixMarketId"), resolved.get("name")
            if mkt_id and label:
                stat_names[mkt_id] = label
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

    idx_to_name = _build_idx_to_name(array)
    player_names, stat_names = _build_lookup_tables(array, idx_to_name)
    pickable_id_key = next((k for k, v in idx_to_name.items() if v == "pickableId"), None)

    if sport == "MLB":
        DEBUG_LOG.append({"sport": sport, "array_len": len(array),
                           "player_names_found": len(player_names), "stat_names_found": len(stat_names),
                           "pickable_id_key_found": pickable_id_key is not None})
        if not player_names or not stat_names or pickable_id_key is None:
            # Capture real samples to fix field names precisely instead of
            # guessing again -- using the confirmed-correct compressed-key
            # detection this time, not a literal string check.
            dkid_key = next((k for k, v in idx_to_name.items() if v == "dkId"), None)
            dkid_samples = ([item for item in array if isinstance(item, dict) and f"_{dkid_key}" in item][:3]
                             if dkid_key is not None else [])
            DEBUG_LOG.append({"sport": sport, "dkid_key": dkid_key, "dkid_samples": dkid_samples,
                               "pickable_id_key": pickable_id_key,
                               "note": "player_names may still be empty if names truly aren't co-located "
                                       "with dkId in any single dict -- see dkid_samples for what's actually there"})

    if pickable_id_key is None:
        return []

    normalized = []
    pickable_key_str = f"_{pickable_id_key}"
    for item in array:
        if not isinstance(item, dict) or pickable_key_str not in item:
            continue
        resolved = _resolve_refs(item, array, idx_to_name)
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
