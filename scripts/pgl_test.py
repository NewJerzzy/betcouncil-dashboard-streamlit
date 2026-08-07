import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://statsapi.mlb.com/api/v1/people/search", params={"names": "Zack Wheeler"}, timeout=15)
    people = r.json().get("people", [])
    result = {"search_status": r.status_code, "num_people": len(people)}
    if people:
        pid = people[0]["id"]
        r2 = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",
                           params={"stats": "gameLog", "group": "pitching", "season": 2026}, timeout=15)
        d = r2.json()
        splits = d.get("stats", [{}])[0].get("splits", [])
        result["gamelog_status"] = r2.status_code
        result["num_starts"] = len(splits)
        if splits:
            result["sample"] = splits[0].get("stat", {})
            result["sample_date"] = splits[0].get("date")
    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note":"TEMP pitcher gamelog","result":result}, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
