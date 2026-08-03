import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    tests = [("mlb", "nyy"), ("nba", "lal"), ("nfl", "dal"), ("nhl", "tor"), ("wnba", "lva")]
    results = {}
    for sport, abbr in tests:
        url = f"https://a.espncdn.com/i/teamlogos/{sport}/500/{abbr}.png"
        try:
            r = requests.get(url, timeout=10)
            results[f"{sport}/{abbr}"] = {"status": r.status_code, "content_type": r.headers.get("Content-Type"), "len": len(r.content)}
        except Exception as e:
            results[f"{sport}/{abbr}"] = {"error": str(e)[:200]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP espn logo test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
