import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SPORT_PATHS = {
    "MLB": "baseball/mlb", "NBA": "basketball/nba", "NFL": "football/nfl",
    "NHL": "hockey/nhl", "WNBA": "basketball/wnba",
}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{SPORT_PATHS['MLB']}/teams", timeout=15)
    teams = r.json().get("sports",[{}])[0].get("leagues",[{}])[0].get("teams",[])
    sample = teams[0]["team"]
    result = {"full_sample": sample, "num_teams": len(teams)}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP espn full team shape", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
