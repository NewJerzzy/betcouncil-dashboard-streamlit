import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    try:
        r = requests.get("https://statsapi.mlb.com/api/v1/people/search",
                          params={"names": "Aaron Judge"}, timeout=15)
        result["search"] = r.json()
        pid = result["search"]["people"][0]["id"]
        r2 = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",
                           params={"stats": "season", "group": "hitting", "season": 2026}, timeout=15)
        result["stats"] = r2.json()
    except Exception as e:
        result["error"] = str(e)[:500]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP mlb stats test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
