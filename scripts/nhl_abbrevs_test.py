import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    try:
        r = requests.get("https://api.nhle.com/stats/rest/en/team", timeout=15)
        data = r.json()
        teams = data.get("data", [])
        result["num_teams"] = len(teams)
        result["sample"] = teams[:3]
        result["all_triCodes"] = sorted([t.get("triCode") for t in teams if t.get("triCode")])
    except Exception as e:
        result["error"] = str(e)[:400]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP nhl abbrevs test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
