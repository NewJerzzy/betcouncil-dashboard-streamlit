import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    gh_token = os.environ.get("GITHUB_TOKEN")
    pp_cookie = os.environ.get("PP_COOKIE_TEST", "")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://parlayplay.io",
        "Referer": "https://parlayplay.io/",
        "x-csrftoken": "1",
        "x-parlay-request": "1",
        "Cookie": pp_cookie,
    }
    r = requests.get("https://parlayplay.io/api/v1/crossgame/offering/", headers=headers, timeout=15)
    result = {"status": r.status_code, "len": len(r.text), "sample": r.text[:500]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP parlayplay live test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
