import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}
    for abbr in ["UTA", "ARI", "TOR", "VGK", "SEA"]:
        try:
            r = requests.get(f"https://api-web.nhle.com/v1/roster/{abbr}/current", timeout=10)
            data = r.json() if r.status_code == 200 else {}
            forwards = data.get("forwards", [])
            results[abbr] = {"status": r.status_code, "num_forwards": len(forwards)}
        except Exception as e:
            results[abbr] = {"error": str(e)[:200]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP nhl roster fmt test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
