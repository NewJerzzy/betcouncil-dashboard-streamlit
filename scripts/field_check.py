import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    r = requests.get("https://api.github.com/gists/" + GIST_ID,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    files = r.json()["files"]

    pw_name = "betcouncil_pickswise_MLB.json"
    if pw_name in files:
        d = requests.get(files[pw_name]["raw_url"]).json()
        games = d.get("games", [])
        result["pickswise_num_games"] = len(games)
        result["pickswise_sample"] = games[0] if games else None
        result["pickswise_pick_side_populated"] = sum(1 for g in games if g.get("pick_side"))

    sf_name = "betcouncil_sharp_feeds.json"
    if sf_name in files:
        d = requests.get(files[sf_name]["raw_url"]).json()
        wgt = d.get("wiseguyteam", {}).get("MLB", {})
        games = wgt.get("games", [])
        result["wgt_num_games"] = len(games)
        result["wgt_sample"] = games[0] if games else None
        result["wgt_has_sharp_true_count"] = sum(1 for g in games if g.get("has_sharp"))

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note": "TEMP field check", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
