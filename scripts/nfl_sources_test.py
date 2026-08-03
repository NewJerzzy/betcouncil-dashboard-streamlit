import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    result = {}
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/dal/statistics", headers=headers, timeout=15)
        data = r.json()
        cats = data.get("results", {}).get("stats", {}).get("categories", [])
        result["category_names"] = [c.get("name") for c in cats]
        def_cat = next((c for c in cats if c.get("name") == "defensive"), None)
        if def_cat:
            result["defensive_stats_sample"] = [s.get("name") + "=" + str(s.get("perGameValue")) for s in def_cat.get("stats", [])[:10]]
    except Exception as e:
        result["error"] = str(e)[:400]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP nfl defensive cat test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
