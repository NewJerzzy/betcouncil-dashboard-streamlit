"""
pick6_refresh.py — DraftKings Pick6 props scraper
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
SSO_LOGIN_URL = "https://sso.draftkings.com/api/authentication/v1/login"


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


def _resolve_value(v, array: list, idx_to_name: dict, depth=0, max_depth=15):
    """
    Fully dereference a single value. Confirmed via a second live
    re-test (2026-07-25) that the previous version of this resolver had
    a second, deeper indirection bug: after one dereference, a LIST
    result (e.g. entities: [1831]) is NOT already-resolved data -- its
    own elements are themselves indices needing one more hop to become
    real dicts (entities: [1831] -> array[1831] -> the real player dict).
    Only trusts that second hop if it yields a genuine dict (a real
    object reference) -- if array[element] is anything else (None, a
    scalar), the original int was literal data (e.g. a real comp-ID
    number, confirmed via compIds: [400] staying [400], not becoming
    array[400]) and is kept as-is rather than replaced with a wrong value.
    """
    if depth > max_depth:
        return v
    if isinstance(v, int) and 0 <= v < len(array):
        v = array[v]
    if isinstance(v, list):
        out = []
        for item in v:
            if isinstance(item, int) and 0 <= item < len(array):
                deref = array[item]
                if isinstance(deref, dict):
                    out.append(_resolve_dict(deref, array, idx_to_name, depth + 1, max_depth))
                else:
                    out.append(item)
            elif isinstance(item, dict):
                out.append(_resolve_dict(item, array, idx_to_name, depth + 1, max_depth))
            else:
                out.append(item)
        return out
    if isinstance(v, dict):
        return _resolve_dict(v, array, idx_to_name, depth + 1, max_depth)
    return v


def _resolve_dict(d: dict, array: list, idx_to_name: dict, depth=0, max_depth=15):
    if depth > max_depth:
        return d
    out = {}
    for k, v in d.items():
        if isinstance(k, str) and k.startswith("_") and k[1:].isdigit():
            real_key = idx_to_name.get(int(k[1:]), k)
        else:
            real_key = k
        out[real_key] = _resolve_value(v, array, idx_to_name, depth + 1, max_depth)
    return out


def _resolve_refs(obj, array: list, idx_to_name: dict, depth=0, max_depth=15):
    """Entry point -- dispatches to _resolve_dict/_resolve_value so both
    a top-level dict and a top-level list are handled correctly."""
    if isinstance(obj, dict):
        return _resolve_dict(obj, array, idx_to_name, depth, max_depth)
    return _resolve_value(obj, array, idx_to_name, depth, max_depth)


def _load_player_names_from_gist(github_token: str) -> dict:
    """
    Read the player name map pushed by the Tampermonkey harvester
    (betcouncil_player_names.json in the gist).
    Returns {dkId(int): name(str)} or {} if the file doesn't exist yet.
    """
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}",
                     "Accept": "application/vnd.github+json"},
            timeout=(5, 10),
        )
        if not resp.ok:
            return {}
        files = resp.json().get("files", {})
        names_file = files.get("betcouncil_player_names.json", {})
        raw_url = names_file.get("raw_url", "")
        if not raw_url:
            return {}
        content_resp = requests.get(raw_url, timeout=(5, 10))
        if not content_resp.ok:
            return {}
        data = content_resp.json()
        raw_names = data.get("names", data if isinstance(data, dict) else {})
        # Keys may be strings from JSON; convert to int for lookup
        result = {}
        for k, v in raw_names.items():
            try:
                result[int(k)] = v
            except (ValueError, TypeError):
                pass
        DEBUG_LOG.append({"note": "gist_player_names_loaded", "count": len(result)})
        return result
    except Exception as ex:
        DEBUG_LOG.append({"note": "gist_player_names_error", "error": str(ex)[:120]})
        return {}


def _load_dk_credentials(github_token: str) -> tuple[str, str]:
    """
    Read DK credentials from the gist (betcouncil_cfg.json) when env vars
    DK_EMAIL / DK_PASSWORD are not set in the workflow environment.
    Returns (email, password) or ("", "") on any failure.
    """
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}",
                     "Accept": "application/vnd.github+json"},
            timeout=(5, 10),
        )
        if not resp.ok:
            return "", ""
        files = resp.json().get("files", {})
        cfg_file = files.get("betcouncil_cfg.json", {})
        raw_url = cfg_file.get("raw_url", "")
        if not raw_url:
            return "", ""
        cfg_resp = requests.get(raw_url, timeout=(5, 10))
        if not cfg_resp.ok:
            return "", ""
        import base64
        cfg = cfg_resp.json()
        email = base64.b64decode(cfg.get("dk_e", "")).decode()
        password = base64.b64decode(cfg.get("dk_p", "")).decode()
        return email, password
    except Exception as ex:
        DEBUG_LOG.append({"note": "cfg_load_error", "error": str(ex)[:120]})
        return "", ""


def _dk_login(email: str, password: str) -> requests.Session | None:
    """
    Log in to DraftKings SSO and return an authenticated session.
    Returns None if login fails so callers can gracefully degrade.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        resp = session.post(
            SSO_LOGIN_URL,
            json={"login": email, "password": password, "rememberMe": False},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=(8, 20),
        )
        cookie_names = list(session.cookies.keys())
        DEBUG_LOG.append({"note": "dk_login", "status": resp.status_code,
                           "cookies": cookie_names})
        if resp.ok or cookie_names:
            return session
        log(f"DK login failed: HTTP {resp.status_code}")
        return None
    except Exception as ex:
        DEBUG_LOG.append({"note": "dk_login_exception", "error": str(ex)[:120]})
        return None


def _fetch_player_names_auth(session: requests.Session, sport: str) -> dict:
    """
    Use an authenticated DK session to build dkId->displayName.
    Tries several endpoints; returns {} if none work.
    """
    dk_sport = {"SOCCER": "SOC", "UFC": "MMA", "PGA+TOUR": "GOLF",
                "NASCAR": "NAS"}.get(sport, sport)
    name_map: dict = {}
    endpoints = [
        f"https://api.draftkings.com/players/v1/players?sport={dk_sport}&format=json&pageSize=1000",
        f"https://api.draftkings.com/pick6/v1/pickables?sport={dk_sport}&format=json",
        f"https://api.draftkings.com/pick6/v2/pickables?sport={dk_sport}&format=json",
        f"https://api.draftkings.com/pick6/v1/entities?sport={dk_sport}&format=json",
    ]
    for url in endpoints:
        try:
            r = session.get(url, timeout=(6, 15))
            # Log the first endpoint attempt per sport so we can diagnose
            if not any(e.get("note") == f"dk_auth_probe_{sport}" for e in DEBUG_LOG):
                DEBUG_LOG.append({"note": f"dk_auth_probe_{sport}", "url": url,
                                   "status": r.status_code, "snippet": r.text[:300]})
            if not r.ok:
                continue
            d = r.json()
            players = (d.get("players") or d.get("draftables") or d.get("pickables") or
                       d.get("entities") or d.get("data") or
                       (d if isinstance(d, list) else []))
            for p in (players if isinstance(players, list) else []):
                pid = (p.get("dkId") or p.get("playerId") or
                       p.get("draftableId") or p.get("id"))
                name = (p.get("displayName") or p.get("fullName") or p.get("name") or
                        p.get("shortName") or
                        " ".join(filter(None, [p.get("firstName"), p.get("lastName")])) or None)
                if pid and name:
                    name_map[int(pid)] = name
            if name_map:
                DEBUG_LOG.append({"note": "dk_auth_names_ok", "sport": sport,
                                   "count": len(name_map), "source": url})
                return name_map
        except Exception:
            continue
    if not name_map:
        DEBUG_LOG.append({"note": "dk_auth_names_failed", "sport": sport})
    return name_map


def _build_lookup_tables(array: list, idx_to_name: dict) -> tuple:
    """
    Scan the flat array for:
    - dkId-carrying dicts → dkId->name lookup (NOTE: confirmed 2026-07-29 that
      the Pick6 SSR stream does NOT include player display names; they are loaded
      client-side via XHR after hydration. player_names will always be empty from
      this source alone. dkId_ placeholder names are used as a fallback.)
    - market dicts → pickSixMarketId->stat_name lookup (this DOES work from SSR)
    """
    dkid_key = idx_to_name and next((k for k, v in idx_to_name.items() if v == "dkId"), None)
    market_id_key = next((k for k, v in idx_to_name.items() if v == "pickSixMarketId"), None)

    player_names, stat_names = {}, {}
    for item in array:
        if not isinstance(item, dict):
            continue
        if dkid_key is not None and f"_{dkid_key}" in item:
            resolved = _resolve_refs(item, array, idx_to_name)
            dk_id = resolved.get("dkId")
            name = resolved.get("displayName") or resolved.get("fullName") or resolved.get("name")
            if dk_id and name:
                player_names[dk_id] = name
        if market_id_key is not None and f"_{market_id_key}" in item:
            resolved = _resolve_refs(item, array, idx_to_name)
            mkt_id, label = resolved.get("pickSixMarketId"), resolved.get("name")
            if mkt_id and label:
                stat_names[mkt_id] = label
    return player_names, stat_names


def fetch_sport_props(sport: str, session: requests.Session | None = None,
                      harvested_names: dict | None = None) -> list:
    url = f"{BASE_URL}?sport={sport}"
    fetcher = session if session is not None else requests
    r = fetcher.get(url, headers=HEADERS, timeout=(8, 20))
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
    # Merge in harvested names from Tampermonkey gist file (higher priority than SSR)
    if harvested_names:
        player_names = {**harvested_names, **player_names}  # SSR wins on conflict (unlikely)
    # If still no names and we have an auth session, try DK API (best-effort)
    if not player_names and session is not None:
        player_names = _fetch_player_names_auth(session, sport)
    pickable_id_key = next((k for k, v in idx_to_name.items() if v == "pickableId"), None)

    DEBUG_LOG.append({"sport": sport, "array_len": len(array),
                       "player_names_found": len(player_names), "stat_names_found": len(stat_names),
                       "pickable_id_key_found": pickable_id_key is not None})

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
        json={"files": {"betcouncil_pick6_props.json": {"content": json.dumps(payload)}}},
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

    # Attempt authenticated DK session — degrades gracefully to anonymous if credentials absent/fail
    dk_email = os.environ.get("DK_EMAIL", "")
    dk_password = os.environ.get("DK_PASSWORD", "")
    if not (dk_email and dk_password):
        log("DK_EMAIL/DK_PASSWORD env vars not set — loading credentials from gist…")
        dk_email, dk_password = _load_dk_credentials(github_token)
    dk_session: requests.Session | None = None
    if dk_email and dk_password:
        log("Logging in to DraftKings for authenticated player name resolution…")
        dk_session = _dk_login(dk_email, dk_password)
        if dk_session:
            log("DK login OK — will use authenticated session for player names")
        else:
            log("DK login failed — continuing without auth (names will be dkId_ placeholders)")
    else:
        log("No DK credentials available — running unauthenticated")

    # Load harvested player names from Tampermonkey gist file (populated by browser script)
    log("Loading harvested player names from gist…")
    harvested_names = _load_player_names_from_gist(github_token)
    log(f"  {len(harvested_names)} player names loaded from gist")

    all_props = []
    for sport in SPORTS:
        try:
            props = fetch_sport_props(sport, session=dk_session, harvested_names=harvested_names)
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
