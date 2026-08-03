import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://signalodds.com",
        "Referer": "https://signalodds.com/",
        "x-client-source": "web",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    url = "https://api.betslib.com/predictions?date_filter=upcoming&limit=20&page=1&sort_by=commence_time&sort_dir=asc&sport=tennis"
    r = requests.get(url, headers=headers, timeout=15)
    result = {"status": r.status_code, "len": len(r.text), "sample": r.text[:1500]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP tennis wiring test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
