#!/usr/bin/env python3
"""
scripts/fetch_prizepicks_daily.py
──────────────────────────────────
Fetch PrizePicks projections for all active sports and push to GitHub Gist
as betcouncil_prizepicks_{SPORT}.json files.

Run manually:
    GITHUB_TOKEN=ghp_... GITHUB_GIST_ID=... python scripts/fetch_prizepicks_daily.py

Or schedule via GitHub Actions / cron / Task Scheduler (runs daily at 9am ET).
PrizePicks API is public — no account or auth token needed for the fetch itself.
"""

import os, json, sys, time, datetime
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests"); sys.exit(1)

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_GIST_ID= os.environ.get("GITHUB_GIST_ID", "7e52e1c2c2054847c7c4663a157386c5")

LEAGUE_IDS = {"NBA":4, "MLB":5, "NHL":3, "NFL":7, "WNBA":8}

HEADERS = {
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":           "application/json",
    "Accept-Language":  "en-US,en;q=0.9",
    "Origin":           "https://app.prizepicks.com",
    "Referer":          "https://app.prizepicks.com/",
}

def fetch_sport(sport: str, league_id: int) -> Optional[dict]:
    """Try multiple PrizePicks CDN/API endpoints."""
    urls = [
        "https://static.prizepicks.com/projections.json",
        f"https://api.prizepicks.com/projections?league_id={league_id}&per_page=250&single_stat=true",
        f"https://partner-api.prizepicks.com/projections?per_page=1000&league_id={league_id}",
        f"https://api.prizepicks.com/projections?league_id={league_id}&per_page=250",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", []) if isinstance(data, dict) else data
                if items:
                    print(f"  [{sport}] {len(items)} projections from {url[:60]}")
                    return data
        except Exception as e:
            print(f"  [{sport}] {url[:50]} failed: {e}")
    return None

def push_to_gist(sport: str, data: dict) -> bool:
    """Push sport-specific data to Gist as betcouncil_prizepicks_{sport}.json."""
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        print("ERROR: GITHUB_TOKEN or GITHUB_GIST_ID not set"); return False
    filename = f"betcouncil_prizepicks_{sport}.json"
    payload  = json.dumps({
        "data":      data,
        "sport":     sport,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "source":    "fetch_prizepicks_daily",
    }, separators=(",", ":"))
    r = requests.patch(
        f"https://api.github.com/gists/{GITHUB_GIST_ID}",
        headers={"Authorization": f"token {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"},
        json={"files": {filename: {"content": payload}}},
        timeout=15,
    )
    if r.status_code == 200:
        print(f"  [{sport}] ✅ pushed to Gist as {filename}")
        return True
    else:
        print(f"  [{sport}] ❌ Gist push failed: {r.status_code} {r.text[:100]}")
        return False

def main():
    print(f"BetCouncil PrizePicks Daily Fetch — {datetime.date.today()}")
    if not GITHUB_TOKEN:
        print("WARNING: GITHUB_TOKEN not set. Set env var to push to Gist.")
    successes = 0
    for sport, league_id in LEAGUE_IDS.items():
        print(f"Fetching {sport}...")
        data = fetch_sport(sport, league_id)
        if data:
            if GITHUB_TOKEN:
                if push_to_gist(sport, data): successes += 1
            else:
                items = data.get("data", []) if isinstance(data, dict) else data
                print(f"  [{sport}] {len(items)} props fetched (not pushed — no token)")
                successes += 1
        else:
            print(f"  [{sport}] ❌ No data fetched")
        time.sleep(1)  # be polite
    print(f"\nDone: {successes}/{len(LEAGUE_IDS)} sports updated.")
    print("Run this script daily (or use the Tampermonkey script for automatic updates).")

if __name__ == "__main__":
    main()
