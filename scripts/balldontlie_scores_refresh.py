"""
balldontlie_scores_refresh.py — BallDontLie live scores (MLB/NFL/WNBA/NHL)
================================================================================
Real, confirmed via official docs (mlb.balldontlie.io) before writing this:
- Endpoint: GET https://api.balldontlie.io/{sport}/v1/games
- Games endpoint is Free-tier accessible on ALL plans (confirmed via the
  real account-tier table on their docs page)
- Real response includes home_team_data/away_team_data with hits, runs,
  errors, inning_scores -- genuine live score detail, not just a final score
- Lineups specifically require a paid tier (confirmed "No" on Free in the
  same docs table) -- this script does NOT attempt lineups, scores only

Real account confirmed (user's own dashboard, not assumed): every sport
shows FREE tier active, including MLB, NFL, WNBA, NHL.

Rate limit: 5 req/min on Free tier -- this script checks 4 sports per run,
well within that limit for a single run (not continuous polling).
"""

import json
import os
import sys
from datetime import date, datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BDL_KEY = os.environ.get("BALLSDONTLIE_API_KEY", "")

SPORTS = {"mlb": "MLB", "nfl": "NFL", "wnba": "WNBA", "nhl": "NHL"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def push_files(files_payload: dict, github_token: str) -> int:
    import time, random
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
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
        if resp.status_code in (403, 429, 409) and attempt < 4:
            wait = min(10 * (2 ** attempt), 90) + random.uniform(0, 5)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s")
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
    if not BDL_KEY:
        log("FATAL: BALLSDONTLIE_API_KEY not set")
        return 1

    today_str = date.today().strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_real_data = False

    for slug, display in SPORTS.items():
        url = f"https://api.balldontlie.io/{slug}/v1/games?dates[]={today_str}"
        try:
            r = requests.get(url, headers={"Authorization": BDL_KEY}, timeout=15)
            DEBUG_LOG.append({"sport": display, "status": r.status_code, "bytes": len(r.text)})
            if r.status_code != 200:
                log(f"{display}: HTTP {r.status_code}")
                continue
            games = r.json().get("data", [])
            log(f"{display}: {len(games)} games")
            if games:
                any_real_data = True
            files_payload[f"betcouncil_bdl_scores_{display}.json"] = {
                "content": json.dumps({
                    "source": "balldontlie", "sport": display,
                    "captured_at": now_iso, "games": games,
                }, indent=2)
            }
        except Exception as e:
            log(f"{display}: error {e}")
            DEBUG_LOG.append({"sport": display, "error": str(e)[:200]})

    files_payload["betcouncil_bdl_scores_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG}, indent=2)
    }

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files, any_real_data={any_real_data}")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
