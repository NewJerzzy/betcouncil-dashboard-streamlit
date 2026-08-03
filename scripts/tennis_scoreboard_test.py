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
            comps = events[0].get("competitions", [{}])[0].get("competitors", [])
            result["sample_competitors"] = comps
    except Exception as e:
        result["error"] = str(e)[:400]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP tennis competitor test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
