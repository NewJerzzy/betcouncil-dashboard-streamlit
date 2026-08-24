"""
Real, one-off diagnostic script: times the specific sources already suspected
of being slow tonight, calling each real fetcher function directly and
measuring genuine wall-clock time. Run via a one-off GitHub Actions workflow
(real internet access, unlike the sandbox this was written in), writing real
results to a Gist file so they can be read back without any board load.

Every function call is individually wrapped so one real failure/timeout
doesn't stop the rest from being measured.
"""
import json
import time
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetchers

_key_len = len(getattr(fetchers, "SHARPAPI_KEY", "") or "")

# Real, focused set: the specific sources already suspected tonight (from
# the Replit report + confirmed-slow OddsWrap from earlier this session).
TARGETS = [
    ("OddsWrap", "fetch_oddswrap_props", "MLB"),
    ("ParlayAPI Props", "fetch_parlayapi_props", "MLB"),
    ("ParlayAPI Arbitrage", "fetch_parlayapi_arbitrage", "MLB"),
    ("ParlayAPI EV", "fetch_parlayapi_ev", "MLB"),
    ("SharpAPI Lines", "fetch_sharpapi_lines", "MLB"),
    ("SharpAPI Props", "fetch_sharpapi_props", "MLB"),
    ("Pinnacle Game Lines", "fetch_pinnacle_game_lines", "MLB"),
    ("Action Network Game Lines", "fetch_action_network_lines", "MLB"),
]

results = []
for label, fn_name, sport in TARGETS:
    fn = getattr(fetchers, fn_name, None)
    if fn is None:
        results.append({"source": label, "function": fn_name, "status": "MISSING", "seconds": None})
        continue
    start = time.time()
    try:
        data = fn(sport)
        elapsed = round(time.time() - start, 2)
        if "parlayapi" in fn_name.lower() and not data and elapsed < 0.5:
            results.append({
                "source": label, "function": fn_name, "status": "UNTESTABLE",
                "seconds": elapsed,
                "note": "PARLAY_API_KEY not configured as a GitHub Actions secret here -- this function's own key-guard returned instantly, so this is NOT a real speed measurement.",
            })
            continue
        results.append({
            "source": label, "function": fn_name, "status": "OK",
            "seconds": elapsed, "real_item_count": len(data) if isinstance(data, list) else None,
        })
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        results.append({
            "source": label, "function": fn_name, "status": "ERROR",
            "seconds": elapsed, "error": f"{type(e).__name__}: {str(e)[:150]}",
        })

output = {
    "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sharpapi_key_real_length": _key_len,
    "results": sorted(results, key=lambda r: (r["seconds"] is None, -(r["seconds"] or 0))),
}

# Push the real results to the Gist so they can be read back directly.
GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
token = os.environ.get("GITHUB_TOKEN")
import requests
resp = requests.patch(
    f"https://api.github.com/gists/{GIST_ID}",
    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    json={"files": {"betcouncil_slow_source_diagnostic.json": {"content": json.dumps(output, indent=2)}}},
    timeout=30,
)
print(f"Gist push status: {resp.status_code}")
print(json.dumps(output, indent=2))
