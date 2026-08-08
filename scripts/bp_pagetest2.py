import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    result = {}
    r = requests.get("https://www.bettingpros.com/mlb/props/?page=2", headers=headers, timeout=20)
    html = r.text
    result["status"] = r.status_code
    result["len"] = len(html)
    result["has_island_props_text"] = "island-props" in html
    idx = html.find("island-props")
    if idx > -1:
        result["context"] = html[max(0,idx-100):idx+300]
    else:
        # try without page param check
        r2 = requests.get("https://www.bettingpros.com/mlb/props/", headers=headers, timeout=20)
        result["no_param_has_island"] = "island-props" in r2.text
        result["no_param_len"] = len(r2.text)

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
