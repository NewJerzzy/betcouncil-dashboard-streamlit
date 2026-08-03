import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    tests = [("wnba", x) for x in ["lv", "las", "vegas", "lvacs"]]
    results = {}
    for sport, abbr in tests:
        url = f"https://a.espncdn.com/i/teamlogos/{sport}/500/{abbr}.png"
        try:
            r = requests.get(url, timeout=10)
            results[f"{sport}/{abbr}"] = {"status": r.status_code, "len": len(r.content)}
        except Exception as e:
            results[f"{sport}/{abbr}"] = {"error": str(e)[:200]}
    # Also try ESPN's teams API to get real abbreviations
    try:
        r2 = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams", timeout=10)
        teams = r2.json().get("sports",[{}])[0].get("leagues",[{}])[0].get("teams",[])
        results["wnba_teams_sample"] = [{"abbr": t["team"].get("abbreviation"), "logo": t["team"].get("logos",[{}])[0].get("href")} for t in teams[:3]]
    except Exception as e:
        results["wnba_teams_error"] = str(e)[:300]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP wnba logo test2", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
