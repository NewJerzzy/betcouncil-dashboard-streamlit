import json, os, sys, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://lines.bookmaker.eu/en/sports/baseball/", headers=HEADERS, timeout=15)
    result = {"status": r.status_code, "len": len(r.text), "has_oddsTable": "oddsTable" in r.text,
               "snippet": r.text[:1500]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP bookmaker.eu no-cookie test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
