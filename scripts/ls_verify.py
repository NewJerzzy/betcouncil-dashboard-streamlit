import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    results = {}
    for param_name in ["dfsSlateId", "slateId", "DfsSlateId", "id"]:
        url = f"https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSalariesV5?site=1&sport=3&periodId=2804&{param_name}=37738"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            d = r.json()
            scj = json.loads(d.get("SalaryContainerJson", "{}") or "{}")
            sal = scj.get("Salaries", [])
            results[param_name] = {"num_salaries": len(sal), "is_truncated": scj.get("IsTruncated")}
        except Exception as e:
            results[param_name] = {"error": str(e)[:200]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP linestar Id param test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
