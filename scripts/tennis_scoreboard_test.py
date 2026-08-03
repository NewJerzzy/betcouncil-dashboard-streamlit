import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard", timeout=15)
        data = r.json()
        events = data.get("events", [])
        if events:
            groupings = events[0].get("groupings", [])
            result["num_groupings"] = len(groupings)
            if groupings:
                result["grouping0_keys"] = list(groupings[0].keys())
                comps = groupings[0].get("competitions", [])
                result["num_comps_in_grouping0"] = len(comps)
                if comps:
                    result["comp0_full"] = comps[0]
    except Exception as e:
        result["error"] = str(e)[:400]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note": "TEMP tennis groupings test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
