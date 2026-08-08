import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    try:
        r = requests.get("https://www.bettingpros.com/mlb/props/", headers=headers, timeout=20, allow_redirects=True)
        result["site_status"] = r.status_code
        html = r.text
        result["site_len"] = len(html)
        # look for api key patterns
        keys = re.findall(r'["\']?[xX]-?[aA]pi-?[kK]ey["\']?\s*[:=]\s*["\']([a-zA-Z0-9\-_.]{10,})["\']', html)
        result["found_api_keys"] = list(set(keys))[:5]
        # look for api.bettingpros.com references with any query params
        api_refs = re.findall(r'api\.bettingpros\.com[^\s"\'<>]*', html)
        result["api_refs"] = list(set(api_refs))[:10]
    except Exception as e:
        result["site_error"] = str(e)[:300]

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
