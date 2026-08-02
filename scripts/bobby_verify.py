import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    results = {}
    for path in ["/api/mlb/picks", "/api/slate/counts", "/api/mlb/props"]:
        try:
            r = requests.get(f"https://app.bobbysbets.com{path}", headers=headers, timeout=15)
            results[path] = {"status": r.status_code, "len": len(r.text), "sample": r.text[:800]}
        except Exception as e:
            results[path] = {"error": str(e)[:300]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP bobbysbets verify", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
