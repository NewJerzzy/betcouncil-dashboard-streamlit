"""
validate_calibration.py — Backtest-the-backtest for calibrate_tier_thresholds().

Pulls the real resolved-bet history from the BetCouncil Gist and runs it
through the current SEM-gated / recency-weighted / Bayesian-shrunk
calibration logic in bc_utils.py, per sport. Prints exactly what the model
decided and why (gate width, calibration error, backtest ROI note) so a
human can sanity-check the logic against real outcomes without having to
wait for a live board load or dig through session_state.

Usage:
    python3 validate_calibration.py [gist_id]

If gist_id is omitted, defaults to the BetCouncil production Gist ID.
Requires GITHUB_TOKEN in the environment to read the Gist (falls back to
an unauthenticated request, which works for public gists but is rate-limited).
"""
import json
import os
import sys
import urllib.request

import bc_utils

DEFAULT_GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HISTORY_FILENAME = "betcouncil_history.json"


def _fetch_gist_file(gist_id, filename, token=None):
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(f"https://api.github.com/gists/{gist_id}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        gist = json.loads(r.read())
    f = gist.get("files", {}).get(filename, {})
    if not f:
        raise RuntimeError(f"{filename} not found in gist {gist_id}")
    content = f.get("content", "")
    if (not content or f.get("truncated")) and f.get("raw_url"):
        raw_req = urllib.request.Request(f["raw_url"], headers=headers)
        with urllib.request.urlopen(raw_req, timeout=20) as rr:
            content = rr.read().decode("utf-8")
    return json.loads(content or "[]")


def main():
    gist_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GIST_ID
    token = os.environ.get("GITHUB_TOKEN", "")

    history = _fetch_gist_file(gist_id, HISTORY_FILENAME, token)
    print(f"Loaded {len(history)} resolved-bet records from {HISTORY_FILENAME}\n")

    sports = sorted({r.get("sport", "") for r in history if r.get("sport")})
    for sport in sports:
        print("=" * 20, sport, "=" * 20)
        result = bc_utils.calibrate_tier_thresholds([], history, sport)
        print(f"calibrated={result.get('_calibrated')}  n_records={result.get('_n_records')}")
        for tier, note in (result.get("_log") or {}).items():
            print(f"  {tier}: {note}")
        thresholds = {k: v for k, v in result.items() if k in ("SOVEREIGN", "ELITE", "APPROVED", "LEAN")}
        print(f"  thresholds: {thresholds}\n")

    print("Notes:")
    print("- 'insufficient data to backtest' means fewer than 5 qualifying bets on")
    print("  either side of the threshold move — common while manually-logged bets")
    print("  still carry edge=0 placeholder values instead of the model's real edge.")
    print("- A tier reporting 'eff_n < 15' means recency-weighted sample is too thin")
    print("  to trust yet, NOT that the tier has zero bets — check n_raw in the")
    print("  per-tier log line above if the eff_n figure looks surprising.")


if __name__ == "__main__":
    main()
