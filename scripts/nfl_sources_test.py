import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    results = {}
    urls = [
        "https://www.parlaysavant.com/mlb/batter/hits",
        "https://parlaysavant.com/api/mlb/batter/hits",
        "https://www.parlaysavant.com/api/props/mlb/batter/hits",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            results[url] = {"status": r.status_code, "len": len(r.text), "sample": r.text[:400]}
        except Exception as e:
            results[url] = {"error": str(e)[:200]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP parlaysavant test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
