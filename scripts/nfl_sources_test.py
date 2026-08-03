import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    result = {}
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/dal/statistics", headers=headers, timeout=15)
        data = r.json()
        cats = data.get("results", {}).get("stats", {}).get("categories", [])
        for c in cats:
            names = [s.get("name") for s in c.get("stats", [])]
            yard_related = [n for n in names if n and "yard" in n.lower()]
            if yard_related:
                result[c.get("name")] = yard_related
    except Exception as e:
        result["error"] = str(e)[:400]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP nfl yard fields search", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
