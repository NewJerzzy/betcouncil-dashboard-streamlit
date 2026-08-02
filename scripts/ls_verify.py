import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    url = "https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSalariesV5?site=1&sport=3&periodId=2804"
    r = requests.get(url, headers=headers, timeout=15)
    d = r.json()
    result = {"top_keys": list(d.keys())}
    sal = d.get("Salaries", [])
    result["num_salaries"] = len(sal)
    if sal:
        result["sample_player"] = sal[0]
    own = d.get("Ownership", {})
    result["ownership_keys"] = list(own.keys()) if isinstance(own, dict) else str(type(own))
    slates = own.get("Slates") if isinstance(own, dict) else None
    result["slates_sample"] = slates[:3] if isinstance(slates, list) else slates

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP linestar salaries+slates", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
