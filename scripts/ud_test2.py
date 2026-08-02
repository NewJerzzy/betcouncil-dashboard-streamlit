import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
               "Accept": "application/json"}
    result = {}
    try:
        r = requests.get("https://api.underdogfantasy.com/beta/v6/over_under_lines", headers=headers, timeout=30)
        result = {"status": r.status_code, "len": len(r.text), "sample": r.text[:500]}
    except Exception as e:
        result = {"error": str(e)}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_underdog_uniquetest_zzz.json": {"content": json.dumps({"note": "TEMP underdog direct test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code, resp.text[:300])
    return 0

if __name__ == "__main__":
    sys.exit(main())
