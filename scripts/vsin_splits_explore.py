"""
vsin_splits_explore.py — DIAGNOSTIC ONLY, not a production scraper yet
========================================================================
data.vsin.com is not reachable from the sandbox this was built in, so
the real URL/HTML structure for VSIN's betting-splits (tickets% vs
money%/handle%) page couldn't be verified directly the way every other
scraper in this repo was. This script tries several plausible URL
patterns on the real site (GitHub Actions runners have full internet
access) and logs status codes + raw body snippets for each, so the
actual structure can be inspected before writing a real parser --
same "introspect first" discipline as gamblingforecast_refresh.py,
applied to a REST/HTML site instead of a GraphQL schema.

This intentionally does NOT push structured betting-splits data yet --
only exploratory debug output. A real parser should be written once
the actual page structure is confirmed from this output.
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "text/html,application/json"}

CANDIDATE_URLS = [
    "https://data.vsin.com/betting-splits/",
    "https://data.vsin.com/mlb-betting-splits/",
    "https://data.vsin.com/nfl-betting-splits/",
    "https://data.vsin.com/betting-splits/?sportid=mlb",
    "https://www.vsin.com/betting-splits/mlb/",
    "https://www.vsin.com/mlb/betting-splits/",
    "https://data.vsin.com/apps/consensus/",
    "https://data.vsin.com/api/consensus/mlb/",
]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    results = []
    for url in CANDIDATE_URLS:
        entry = {"url": url}
        try:
            r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            entry["status"] = r.status_code
            entry["final_url"] = r.url
            entry["body_len"] = len(r.text)
            # Look for telltale signs of real betting-splits content
            lower = r.text.lower()
            entry["mentions_handle"] = "handle" in lower
            entry["mentions_tickets"] = "ticket" in lower
            entry["mentions_bets_pct"] = "bets %" in lower or "bets%" in lower
            entry["snippet"] = r.text[:800]
            log(f"{url} -> {r.status_code}, {len(r.text)} bytes, "
                f"handle={entry['mentions_handle']} tickets={entry['mentions_tickets']}")
        except Exception as e:
            entry["error"] = str(e)[:300]
            log(f"{url} -> ERROR: {e}")
        results.append(entry)

    try:
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": {"betcouncil_gamblingforecast_debug.json": {
                "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                        "note": "TEMPORARY: this is vsin_splits_explore.py diagnostic output, not gamblingforecast -- repurposing this slot because the gist is at its 300-file cap and can't create new files",
                                        "results": results}, indent=2)}}},
            timeout=30,
        )
        log(f"Debug push: {resp.status_code}")
    except Exception as e:
        log(f"Debug push failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
