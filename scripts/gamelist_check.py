import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    r = requests.get("https://api.github.com/gists/" + GIST_ID,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    files = r.json()["files"]

    sf_name = "betcouncil_sharp_feeds.json"
    d = requests.get(files[sf_name]["raw_url"]).json()
    wgt = d.get("wiseguyteam", {}).get("MLB", {})
    games = wgt.get("games", [])
    result["wgt_all_games"] = [f"{g.get('away_team','')} @ {g.get('home_team','')}" for g in games]

    pw_name = "betcouncil_pickswise_MLB.json"
    d2 = requests.get(files[pw_name]["raw_url"]).json()
    pgames = d2.get("games", [])
    result["pw_games_with_pick"] = [f"{g.get('away_team_long','')} @ {g.get('home_team_long','')}" for g in pgames if g.get("pick_side")]
    result["pw_all_games"] = [f"{g.get('away_team_long','')} @ {g.get('home_team_long','')} (sport={g.get('sport')})" for g in pgames]

    bql_name = "betcouncil_betql_MLB.json"
    d3 = requests.get(files[bql_name]["raw_url"]).json()
    bgames = d3.get("games", [])
    result["betql_sample_games"] = [f"{g.get('away_team','')} @ {g.get('home_team','')}" for g in bgames[:10]]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP game lists check", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
