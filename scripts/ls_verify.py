import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    for param_name in ["dfsSlateId", "DfsSlateId", "slateId"]:
        url = f"https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSalariesV5?site=1&sport=3&periodId=2804&{param_name}=151563"
        r = requests.get(url, headers=headers, timeout=15)
        d = r.json()
        own = d.get("Ownership", {})
        sal = own.get("Salaries", []) if isinstance(own, dict) else []
        result = {"param": param_name, "status": r.status_code, "num_salaries": len(sal),
                  "sample": sal[0] if sal else None}
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": f"TEMP linestar slate test {param_name}", "result": result}, default=str)}}},
        )
        print(param_name, "->", len(sal), "push:", resp.status_code)
        if len(sal) > 100:
            break
    return 0

if __name__ == "__main__":
    sys.exit(main())
