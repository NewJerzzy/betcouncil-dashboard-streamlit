import json, os, sys, re, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    results = {}

    # Test old approach: HTML scrape
    try:
        r = requests.get("https://www.linestarapp.com/Projections/MLB/Site/DraftKings/", headers=headers, timeout=20)
        m = re.search(r"LineStar\.PeriodId\s*=\s*(\d+)", r.text)
        results["html_scrape"] = {"status": r.status_code, "len": len(r.text), "period_id_found": m.group(1) if m else None}
    except Exception as e:
        results["html_scrape"] = {"error": str(e)[:200]}

    # Test new approach: GetSlates
    try:
        r2 = requests.get("https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetSlates?sport=3",
                           headers={**headers, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}, timeout=20)
        results["get_slates"] = {"status": r2.status_code, "len": len(r2.text), "sample": r2.text[:500]}
    except Exception as e:
        results["get_slates"] = {"error": str(e)[:200]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP linestar periodid test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
