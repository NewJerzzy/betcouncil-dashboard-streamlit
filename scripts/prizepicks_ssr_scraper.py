"""
prizepicks_ssr_scraper.py — PrizePicks props scraper (public API, no auth)
============================================================================

Runs on GitHub Actions on a schedule (see
.github/workflows/prizepicks_refresh.yml). Uses PrizePicks' public
partner API (no login, no proxy, no special headers needed — confirmed
working directly) to pull all current projections, splits them by
league, and pushes one Gist file per sport in the exact format
BetCouncil's existing fetch_prizepicks_from_gist() already expects.

No wiring changes needed anywhere else — this just keeps the existing
Gist files fresh automatically instead of relying on a manual/Tampermonkey
harvester run.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://partner-api.prizepicks.com/projections?per_page=10000&include=new_player"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_all_projections() -> dict:
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }
    resp = requests.get(API_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def split_by_league(payload: dict) -> dict:
    """
    Group projections by league (found at
    relationships.league.data.id on each projection), and collect only
    the `included` objects actually referenced by that league's
    projections (players, teams, etc.) — matches the Tampermonkey
    harvester's existing per-sport file format.
    """
    data = payload.get("data", [])
    included = payload.get("included", [])
    included_by_key = {(inc.get("type"), inc.get("id")): inc for inc in included}

    by_league: dict = {}
    for proj in data:
        rels = proj.get("relationships", {})
        league_rel = rels.get("league", {}).get("data") or {}
        league_id = league_rel.get("id")
        # League display name often available via included league objects;
        # fall back to the projection's own league_id string.
        league_name = None
        league_obj = included_by_key.get(("league", league_id))
        if league_obj:
            league_name = league_obj.get("attributes", {}).get("name")
        if not league_name:
            attr = proj.get("attributes", {})
            league_name = attr.get("league") or attr.get("league_id") or "UNKNOWN"

        league_key = str(league_name).upper().replace(" ", "_")
        by_league.setdefault(league_key, {"data": [], "referenced": set()})
        by_league[league_key]["data"].append(proj)

        # Track every relationship reference on this projection so we can
        # pull in exactly the included objects it needs (players, teams, etc.)
        for rel_name, rel_val in rels.items():
            rel_data = rel_val.get("data")
            if isinstance(rel_data, dict):
                by_league[league_key]["referenced"].add(
                    (rel_data.get("type"), rel_data.get("id"))
                )
            elif isinstance(rel_data, list):
                for item in rel_data:
                    if isinstance(item, dict):
                        by_league[league_key]["referenced"].add(
                            (item.get("type"), item.get("id"))
                        )

    result = {}
    for league_key, bucket in by_league.items():
        inc_objs = [
            included_by_key[key] for key in bucket["referenced"]
            if key in included_by_key
        ]
        result[league_key] = {
            "data": bucket["data"],
            "included": inc_objs,
        }
    return result


def push_league_files(by_league: dict) -> int:
    import time
    import random
    github_token = os.environ["GITHUB_TOKEN"]
    files_payload = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for league_key, body in by_league.items():
        filename = f"betcouncil_prizepicks_{league_key}.json"
        wrapper = {
            "sport": league_key,
            "captured_at": now_iso,
            "data": body,
            "source": "github_actions_partner_api",
        }
        files_payload[filename] = {"content": json.dumps(wrapper)}

    for attempt in range(4):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={"files": files_payload},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code == 409 and attempt < 3:
            base_wait = (attempt + 1) * 8
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist 409 conflict (concurrent write) — retrying in {wait:.1f}s (attempt {attempt+1}/4)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    if not os.environ.get("GITHUB_TOKEN"):
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    try:
        payload = fetch_all_projections()
    except Exception as e:
        log(f"FATAL: fetch error — {e}")
        return 1

    total_props = len(payload.get("data", []))
    log(f"Fetched {total_props} total projections")
    if total_props == 0:
        log("FATAL: zero projections returned")
        return 1

    by_league = split_by_league(payload)
    for k, v in by_league.items():
        log(f"  {k}: {len(v['data'])} props")

    pushed = push_league_files(by_league)
    log(f"Pushed {pushed} league files to Gist")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
