import json, os, sys, requests
from datetime import date, timedelta

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    end = date.today()
    start = end - timedelta(days=10)
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=147&startDate={start}&endDate={end}"
    r = requests.get(url, timeout=15)
    data = r.json()
    dates = data.get("dates", [])
    result = {"status": r.status_code, "num_dates": len(dates)}
    games = []
    for d in dates:
        for g in d.get("games", []):
            if g.get("status", {}).get("statusCode") == "F":
                games.append({
                    "date": d.get("date"),
                    "home": g.get("teams", {}).get("home", {}).get("team", {}).get("name"),
                    "away": g.get("teams", {}).get("away", {}).get("team", {}).get("name"),
                    "home_score": g.get("teams", {}).get("home", {}).get("score"),
                    "away_score": g.get("teams", {}).get("away", {}).get("score"),
                })
    result["games"] = games
    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note":"TEMP mlb schedule range","result":result})}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
