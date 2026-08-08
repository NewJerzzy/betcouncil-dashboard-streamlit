"""
Shared, cross-script request-budget tracker for odds-api.io.

Confirmed real root cause (2026-08-08): 3 independent scripts (bet365/
bovada/fanduel props) each had their OWN local per-run request cap
(15/10/10), but zero coordination against the account's real shared
100-requests/hour limit. Worst case: 3 scripts x 4 runs/hour each =
up to 140 requests/hour combined, well over the real 100/hour cap --
exactly matching the account notification ("28 rate limit hits in the
last hour"). This tracks actual usage across all 3 scripts in one
shared Gist counter (atomic via the real distributed lock) so they
collectively respect the true account-wide budget instead of each
independently assuming they have the full 100 to themselves.
"""
import json
import time
import requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BUDGET_FILE = "betcouncil_oddsapiio_budget.json"
HOURLY_SAFE_LIMIT = 85  # real cap is 100/hour; leaves margin for other callers/clock skew


def reserve_budget(github_token: str, holder: str, n_requests: int, acquire_lock, release_lock) -> bool:
    """
    Atomically checks and reserves `n_requests` against the shared
    hourly budget. Returns True if reserved (caller may proceed),
    False if the shared budget doesn't have room (caller should skip
    this run cleanly).
    """
    lock_token = acquire_lock(GIST_ID, github_token, "oddsapiio_budget", holder=holder)
    if not lock_token:
        print(f"[budget] Could not acquire budget lock -- skipping this run to avoid overrun")
        return False
    try:
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if BUDGET_FILE in r_files:
                existing = requests.get(r_files[BUDGET_FILE]["raw_url"], timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            print(f"[budget] Could not read existing budget, starting fresh: {e}")
            existing = {}

        current_hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        if existing.get("hour") != current_hour:
            existing = {"hour": current_hour, "used": 0, "log": []}

        used = existing.get("used", 0)
        if used + n_requests > HOURLY_SAFE_LIMIT:
            print(f"[budget] Shared odds-api.io budget would exceed {HOURLY_SAFE_LIMIT}/hour "
                  f"(used={used}, requesting={n_requests}) -- skipping this run cleanly")
            return False

        existing["used"] = used + n_requests
        existing.setdefault("log", []).append({"holder": holder, "reserved": n_requests,
                                                  "at": datetime.now(timezone.utc).isoformat()})
        existing["log"] = existing["log"][-20:]

        body = json.dumps({"files": {BUDGET_FILE: {"content": json.dumps(existing)}}})
        for attempt in range(3):
            resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
                                   headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                                   data=body, timeout=20)
            if resp.status_code in (200, 201):
                return True
            time.sleep(3 * (attempt + 1))
        print("[budget] Could not persist budget reservation -- proceeding cautiously anyway")
        return True
    finally:
        release_lock(GIST_ID, github_token, "oddsapiio_budget", lock_token)
