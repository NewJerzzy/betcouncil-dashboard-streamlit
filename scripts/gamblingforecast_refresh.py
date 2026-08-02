"""
gamblingforecast_refresh.py — GamblingForecast GraphQL API (public, no auth)
==============================================================================

POST https://api.gamblingforecast.com/graphql/ — fully open introspection,
all data queries work with zero credentials (confirmed live this session).

Two of the five available queries are wired here:
  - playerProps(league: "MLB" | "NBA" | "NFL") -- their model's projected
    value vs the book's line, pre-sorted by edge (projDiff). A second,
    independent model's opinion -- same category as SignalOdds/Pinnacle/
    Circa already weighted into BetCouncil's sharp-consensus ensemble.
  - baseballMatchupStats (no args) -- batter-vs-this-specific-pitcher
    history (H/HR/RBI/AVG/OPS) for today's MLB games. Confirmed nothing
    else in this codebase covers this specific matchup angle (checked
    2026-07-31) -- Baseball Savant/TeamRankings/ESPN cover general and
    situational stats, not batter-vs-this-pitcher history.

Deliberately NOT wired:
  - playerStats -- just DK odds vs PrizePicks line side-by-side for the
    same prop; BetCouncil already computes this exact comparison natively
    with its own real book/PrizePicks data, so it's not new information.
  - hotStreaks / dynamicModelData -- both take an undocumented configName
    argument and returned empty across every guessed value; not usable.

Schema field names within each returned type were only described, not
given exactly, so this introspects PlayerProp and BaseballMatchupStat
(or whatever GraphQL actually names those types) live on each run and
builds the field-selection query from that, rather than hardcoding a
guess that could silently omit or misname a field.
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://api.gamblingforecast.com/graphql/"
LEAGUES = ["MLB", "NBA", "NFL"]

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"),
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _gql(query: str, variables: dict = None, timeout: int = 20):
    resp = requests.post(
        API_URL, headers=HEADERS,
        json={"query": query, "variables": variables or {}},
        timeout=timeout,
    )
    DEBUG_LOG.append({"query_snippet": query[:120], "variables": variables,
                       "status": resp.status_code, "body_len": len(resp.text)})
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        DEBUG_LOG.append({"note": "graphql_errors", "errors": data["errors"][:3]})
    return data.get("data") or {}


def _introspect_scalar_fields(query_field: str) -> list:
    """
    Find the GraphQL type returned by a root query field, then return the
    names of its scalar (non-object, non-list-of-object) fields -- enough
    to build a flat SELECT-everything-simple query without guessing names.
    """
    schema_q = """
    query IntrospectQuery {
      __schema { queryType { fields {
        name
        type { name kind ofType { name kind ofType { name kind } } }
      } } }
    }
    """
    data = _gql(schema_q)
    fields = (data.get("__schema", {}).get("queryType", {}) or {}).get("fields", []) or []
    target = next((f for f in fields if f.get("name") == query_field), None)
    if not target:
        DEBUG_LOG.append({"note": "query_field_not_found", "field": query_field})
        return []

    def _unwrap(t):
        while t and t.get("kind") in ("NON_NULL", "LIST"):
            t = t.get("ofType") or {}
        return t

    return_type = _unwrap(target.get("type") or {})
    type_name = return_type.get("name")
    if not type_name:
        return []

    type_q = """
    query IntrospectType($name: String!) {
      __type(name: $name) { fields {
        name
        type { name kind ofType { name kind } }
      } }
    }
    """
    tdata = _gql(type_q, {"name": type_name})
    tfields = (tdata.get("__type") or {}).get("fields") or []
    scalar_names = []
    for f in tfields:
        ft = f.get("type") or {}
        while ft.get("kind") in ("NON_NULL", "LIST") and ft.get("ofType"):
            ft = ft["ofType"]
        if ft.get("kind") in ("SCALAR", "ENUM"):
            scalar_names.append(f["name"])
    return scalar_names


def fetch_player_props(league: str) -> list:
    fields = _introspect_scalar_fields("playerProps")
    if not fields:
        log(f"playerProps: introspection found no scalar fields, skipping {league}")
        return []
    field_block = "\n".join(fields)
    query = f"""
    query PlayerProps($league: String!) {{
      playerProps(league: $league) {{
        {field_block}
      }}
    }}
    """
    try:
        data = _gql(query, {"league": league})
        rows = data.get("playerProps") or []
        log(f"playerProps({league}): {len(rows)} rows")
        return rows
    except Exception as e:
        log(f"playerProps({league}): error — {e}")
        return []


def fetch_baseball_matchup_stats() -> list:
    fields = _introspect_scalar_fields("baseballMatchupStats")
    if not fields:
        log("baseballMatchupStats: introspection found no scalar fields, skipping")
        return []
    field_block = "\n".join(fields)
    query = f"""
    query BaseballMatchupStats {{
      baseballMatchupStats {{
        {field_block}
      }}
    }}
    """
    try:
        data = _gql(query)
        rows = data.get("baseballMatchupStats") or []
        log(f"baseballMatchupStats: {len(rows)} rows")
        return rows
    except Exception as e:
        log(f"baseballMatchupStats: error — {e}")
        return []


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} left) -- skipping this run cleanly")
            return False
    except Exception as e:
        log(f"rate_limit check failed (continuing anyway): {e}")
    return True


def push_files(files_payload: dict) -> int:
    github_token = os.environ["GITHUB_TOKEN"]
    if not _rate_limit_ok(github_token):
        return 0
    for attempt in range(6):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 4:
                wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                time.sleep(wait)
                continue
            if missing:
                log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                return len(files_payload) - len(missing)
            return len(files_payload)
        if resp.status_code in (409, 403, 429) and attempt < 5:
            base_wait = min((attempt + 1) * 8, 60)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist {resp.status_code} — retrying in {wait:.1f}s (attempt {attempt+1}/6)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def push_debug(github_token: str) -> None:
    try:
        requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": {"betcouncil_gamblingforecast_debug.json": {
                "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                        "requests": DEBUG_LOG[:20]}, indent=2)}}},
            timeout=15,
        )
    except Exception:
        pass


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for league in LEAGUES:
        rows = fetch_player_props(league)
        if rows:
            any_data = True
        files_payload[f"betcouncil_gamblingforecast_props_{league}.json"] = {
            "content": json.dumps({"captured_at": now_iso, "league": league,
                                    "source": "gamblingforecast_graphql", "props": rows})
        }

    matchup_rows = fetch_baseball_matchup_stats()
    if matchup_rows:
        any_data = True
    files_payload["betcouncil_gamblingforecast_mlb_matchups.json"] = {
        "content": json.dumps({"captured_at": now_iso,
                                "source": "gamblingforecast_graphql", "matchups": matchup_rows})
    }

    push_debug(github_token)

    if not any_data:
        log("No data captured across any query — pushing debug only, not overwriting existing data with empty")
        return 1

    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
