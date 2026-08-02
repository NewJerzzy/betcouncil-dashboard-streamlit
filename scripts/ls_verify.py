import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    results = {}
    # MLB, default periodId first
    for sport_id, pid, label in [(3, 2804, "mlb_default"), (12, 1165, "wnba"), (8, 502, "mma")]:
        url = f"https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSalariesV5?site=1&sport={sport_id}&periodId={pid}"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            results[label] = {"status": r.status_code, "len": len(r.text), "sample": r.text[:1000]}
        except Exception as e:
            results[label] = {"error": str(e)[:300]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP linestar new endpoint verify", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
