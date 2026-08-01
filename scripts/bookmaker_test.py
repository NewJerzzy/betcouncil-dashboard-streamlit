import json, os, sys, re, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://lines.bookmaker.eu/en/sports/baseball/", headers=HEADERS, timeout=15)
    text = r.text
    idx = text.find("oddsTable")
    snippet = text[idx:idx+3000] if idx > 0 else "not found"

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP bookmaker table structure", "snippet": snippet}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
