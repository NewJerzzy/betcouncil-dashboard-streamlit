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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSalariesV5"

# sport_id -> (display name, a recently-confirmed-live periodId to try first;
# real periodId changes daily/per-slate, so we also try to discover the
# current one from the same response if this guess is stale)
SPORTS = {
    3:  ("MLB",  2804),
    12: ("WNBA", 1165),
    8:  ("MMA",  502),
    1:  ("NFL",  403),
    2:  ("NBA",  2608),
    6:  ("NHL",  2646),
    5:  ("PGA",  515),
    11: ("CFL",  285),
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "application/json"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _discover_period_id(sport_id: int, seed_period_id: int) -> int | None:
    """
    Discover today's real periodId for this sport. periodId=0 and small
    arbitrary guesses (e.g. 1) do NOT work -- confirmed live, they return
    a totally empty null response shell with no Periods list to read.
    What DOES work: call with a REAL, recently-known-valid periodId (even
    if it's gone stale by a few days), and the response's own "Periods"
    list always has today's real, current period first (Periods[0]["Id"]).
    seed_period_id needs occasional manual updating as it drifts further
    from real (period IDs appear to be daily-incrementing counters) --
    same maintenance category as a session cookie going stale, not a code
    bug. Confirmed live 2026-08-02 with seed=2804 (real that day).
    """
    try:
        r = requests.get(BASE_URL, params={"site": 1, "sport": sport_id, "periodId": seed_period_id},
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


def fetch_sport(sport_id: int, sport_name: str, seed_period_id: int) -> list:
    period_id = _discover_period_id(sport_id, seed_period_id)
    if not period_id:
        DEBUG_LOG.append({"sport": sport_name, "note": "could not discover periodId (seed may be too stale), skipping"})
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
    """
    Merges all 18 per-sport salary files into ONE combined file, using
    the real distributed lock. Confirmed real bug: individual files were
    intermittently missing after all 6 retries (~150s wasted per run),
    the same reliability issue fixed for other sources this session.
    """
    github_token = os.environ["GITHUB_TOKEN"]
    if not _rate_limit_ok(github_token):
        return 0
    SHARED_FILE = "betcouncil_linestar_salaries_combined.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_linestar_salaries_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

    lock_token = acquire_lock(GIST_ID, github_token, "linestar_salaries_combined", holder="linestar_salaries")
    if not lock_token:
        log("Could not acquire linestar_salaries_combined lock -- skipping this run to avoid a collision")
        return 0
    try:
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                existing = requests.get(r_files[SHARED_FILE]["raw_url"], timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        existing.update(merged)
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        for attempt in range(4):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    return len(merged)
                if attempt < 3:
                    time.sleep(5)
                    continue
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 3:
                wait = (attempt + 1) * 8 + random.uniform(0, 5)
                log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0
        return 0
    finally:
        release_lock(GIST_ID, github_token, "linestar_salaries_combined", lock_token)


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport_id, (sport_name, seed_period_id) in SPORTS.items():
        players = fetch_sport(sport_id, sport_name, seed_period_id)
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
    try:
        sys.exit(main())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("UNHANDLED EXCEPTION:\n" + tb)
        try:
            _tok = os.environ.get("GITHUB_TOKEN")
            _r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {_tok}", "Accept": "application/vnd.github+json"}, timeout=15)
            _files = _r.json().get("files", {})
            _existing = {}
            if "betcouncil_linestar_salaries_combined.json" in _files:
                _existing = requests.get(_files["betcouncil_linestar_salaries_combined.json"]["raw_url"], timeout=15).json()
            _existing["_crash_note"] = tb
            requests.patch(f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {_tok}", "Accept": "application/vnd.github+json"},
                json={"files": {"betcouncil_linestar_salaries_combined.json": {"content": json.dumps(_existing)}}}, timeout=20)
        except Exception:
            pass
        sys.exit(1)
