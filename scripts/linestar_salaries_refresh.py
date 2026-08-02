"""
linestar_salaries_refresh.py — LineStar DFS salaries/projections
====================================================================

GET https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSalariesV5?site=1&sport={id}&periodId={pid}

Confirmed live 2026-08-02 via GH Actions workflow_dispatch: no auth,
real 200s across MLB/WNBA/MMA. Real player data lives NESTED inside a
JSON-encoded string field (SalaryContainerJson), not the top-level
"Salaries" key (which is always empty) -- confirmed by direct testing.

KNOWN LIMITATION, not yet solved: the response is capped at ~36 players
regardless of sport (IsTruncated: true, TruncatedSalaryCount showing
1000+ available). The response includes slate metadata (both an "Id"
and a "DfsSlateId" field per slate) that looks like it should unlock
the full player pool via an additional query param, but none of
dfsSlateId/slateId/DfsSlateId/id (tried with both the Id and
DfsSlateId values) changed the result -- still capped, still
truncated. If a future session finds the real parameter, this script
should be extended; for now it ships the real ~36 players it can
reliably get rather than nothing.

Per-player fields (confirmed real): Name, POS, SAL (DK salary), PP
(LineStar's own projection), AggProj (consensus projection), Ceil,
Floor, Stars (0-5 rating), OppRank, Notes (injury/news), AlertScore,
PTEAM/HTEAM/OTEAM, GT (game time), DGID (DraftKings player ID).

Sport IDs confirmed live 2026-08-02: MLB=3, WNBA=12, MMA=8. NFL(1)/
NBA(2)/NHL(6) were off-season/pre-season at test time -- included
below anyway since periods change; a genuinely off-season sport just
returns an empty/near-empty real result, same as every other source
in this codebase that handles off-season sports.
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSalariesV5"

# sport_id -> (display name, a recently-confirmed-live periodId to try first;
# real periodId changes daily/per-slate, so we also try to discover the
# current one from the same response if this guess is stale)
SPORTS = {
    3:  "MLB",
    12: "WNBA",
    8:  "MMA",
    1:  "NFL",
    2:  "NBA",
    6:  "NHL",
    5:  "PGA",
    11: "CFL",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "application/json"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _discover_period_id(sport_id: int) -> int | None:
    """
    Discover today's real periodId for this sport. periodId=0 does NOT
    work as a "give me current" signal (confirmed live -- it just echoes
    back 0). What DOES work: call with ANY periodId (even stale/wrong),
    and the response's own "Periods" list always has today's real,
    current period first (Periods[0]["Id"]), regardless of what period
    was requested. Confirmed live 2026-08-02.
    """
    try:
        r = requests.get(BASE_URL, params={"site": 1, "sport": sport_id, "periodId": 1},
                          headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        periods = data.get("Periods", [])
        if periods and isinstance(periods, list):
            return int(periods[0].get("Id"))
        return None
    except Exception:
        return None


def fetch_sport(sport_id: int, sport_name: str) -> list:
    period_id = _discover_period_id(sport_id)
    if not period_id:
        DEBUG_LOG.append({"sport": sport_name, "note": "could not discover periodId, skipping"})
        return []

    try:
        r = requests.get(BASE_URL, params={"site": 1, "sport": sport_id, "periodId": period_id},
                          headers=HEADERS, timeout=20)
        DEBUG_LOG.append({"sport": sport_name, "period_id": period_id, "status": r.status_code})
        if r.status_code != 200:
            return []
        data = r.json()
        scj_raw = data.get("SalaryContainerJson")
        if not scj_raw:
            return []
        scj = json.loads(scj_raw)
        salaries = scj.get("Salaries", [])
        if not isinstance(salaries, list):
            return []

        players = []
        for p in salaries:
            players.append({
                "name": p.get("Name"), "pos": p.get("POS"), "salary": p.get("SAL"),
                "projection": p.get("PP"), "agg_projection": p.get("AggProj"),
                "ceiling": p.get("Ceil"), "floor": p.get("Floor"), "stars": p.get("Stars"),
                "opp_rank": p.get("OppRank"), "notes": p.get("Notes"),
                "alert_score": p.get("AlertScore"), "team": p.get("PTEAM"),
                "home_team": p.get("HTEAM"), "away_team": p.get("OTEAM"),
                "game_time": p.get("GT"), "dk_player_id": p.get("DGID"),
            })
        log(f"{sport_name}: {len(players)} players (truncated={scj.get('IsTruncated')}, "
            f"total available={scj.get('TruncatedSalaryCount')})")
        return players
    except Exception as e:
        DEBUG_LOG.append({"sport": sport_name, "error": str(e)[:200]})
        log(f"{sport_name}: error — {e}")
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
            if missing and attempt < 5:
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
            log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/6)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport_id, sport_name in SPORTS.items():
        players = fetch_sport(sport_id, sport_name)
        if players:
            any_data = True
        files_payload[f"betcouncil_linestar_salaries_{sport_name}.json"] = {
            "content": json.dumps({"captured_at": now_iso, "sport": sport_name,
                                    "source": "linestar_salaries_v5", "players": players})
        }

    files_payload["betcouncil_linestar_salaries_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
    }

    if not any_data:
        log("No players captured across any sport -- pushing debug only, not overwriting existing data with empty")
        push_files({"betcouncil_linestar_salaries_debug.json": files_payload["betcouncil_linestar_salaries_debug.json"]})
        return 1

    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
