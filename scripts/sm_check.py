import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    for url in [
        "https://api.smarkets.com/v3/events/?type=sport&state=upcoming",
        "https://api.smarkets.com/v3/sports/",
    ]:
        try:
            r = requests.get(url, timeout=15)
            result[url] = {"status": r.status_code, "sample": r.text[:600]}
        except Exception as e:
            result[url] = {"error": str(e)[:300]}

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note":"TEMP smarkets check","result":result}, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
