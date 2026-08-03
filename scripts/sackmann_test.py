import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}
    for year in [2026, 2025]:
        url = f"https://stats.tennismylife.org/data/{year}.csv"
        try:
            r = requests.get(url, timeout=15)
            results[str(year)] = {"status": r.status_code, "len": len(r.text), "sample": r.text[:300]}
        except Exception as e:
            results[str(year)] = {"error": str(e)[:300]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP sackmann test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
