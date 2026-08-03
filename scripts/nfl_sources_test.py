import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # ESPN injuries endpoint
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/dal/injuries", headers=headers, timeout=15)
        results["espn_injuries"] = {"status": r.status_code, "sample": r.text[:800]}
    except Exception as e:
        results["espn_injuries"] = {"error": str(e)[:300]}

    # ESPN team stats (defense) endpoint
    try:
        r2 = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/dal/statistics", headers=headers, timeout=15)
        results["espn_team_stats"] = {"status": r2.status_code, "sample": r2.text[:800]}
    except Exception as e:
        results["espn_team_stats"] = {"error": str(e)[:300]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP nfl sources test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
