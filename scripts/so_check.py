import json, os, sys, requests, time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    for ep in ("/predictions", "/arbitrage", "/opportunities", "/sure-bets", "/surebets", "/sure_bets", "/arbs"):
        t0 = time.time()
        try:
            r = requests.get(f"https://api.betslib.com{ep}",
                              params={"date_filter": "upcoming", "limit": 20, "page": 1, "sort_by": "commence_time", "sort_dir": "asc"},
                              headers={"Accept": "application/json", "Origin": "https://signalodds.com", "Referer": "https://signalodds.com/", "x-client-source": "web"},
                              timeout=15)
            result[ep] = {"status": r.status_code, "elapsed": round(time.time()-t0, 2), "sample": r.text[:300]}
        except Exception as e:
            result[ep] = {"error": str(e)[:200], "elapsed": round(time.time()-t0, 2)}

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps({"note":"TEMP signalodds endpoints","result":result}, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
