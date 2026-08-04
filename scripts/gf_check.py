import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://api.github.com/gists/" + GIST_ID,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    files = r.json()["files"]
    result = {}
    fname = "betcouncil_gamblingforecast_props_MLB.json"
    if fname in files:
        d = requests.get(files[fname]["raw_url"]).json()
        props = d.get("props", [])
        result["num_props"] = len(props)
        result["sample"] = props[:3] if props else None
    else:
        result["error"] = "file missing"

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP gf props check", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
