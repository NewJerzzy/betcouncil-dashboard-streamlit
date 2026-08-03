import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard", timeout=15)
        data = r.json()
        events = data.get("events", [])
        result["num_events"] = len(events)
        if events:
            result["event0_keys"] = list(events[0].keys())
            result["event0_name"] = events[0].get("name")
            comp0 = events[0].get("competitions", [{}])[0]
            result["comp0_keys"] = list(comp0.keys())
            result["comp0_full"] = comp0
    except Exception as e:
        result["error"] = str(e)[:400]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note": "TEMP tennis full comp test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
