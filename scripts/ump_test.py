import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Referer": "https://umpscorecards.com/"}
    # Try common filter param names to get a smaller response
    urls_to_try = [
        "https://umpscorecards.com/api/games?team=NYY",
        "https://umpscorecards.com/api/games?home_team=NYY",
        "https://umpscorecards.com/api/games?limit=5",
        "https://umpscorecards.com/api/games?page=1&per_page=5",
    ]
    for url in urls_to_try:
        try:
            r = requests.get(url, headers=headers, timeout=30)
            result[url] = {"status": r.status_code, "len": len(r.text)}
            if len(r.text) < 500000:  # only try to parse if reasonably small
                data = r.json()
                rows = data.get("rows", data) if isinstance(data, dict) else data
                if isinstance(rows, list) and rows:
                    result[url]["num_rows"] = len(rows)
                    result[url]["sample_row_0"] = rows[0]
        except Exception as e:
            result[url] = {"error": str(e)[:200]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note": "TEMP ump games filtered test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
