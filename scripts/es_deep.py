import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    result = {}
    r = requests.get("https://theedgesniper.com/", headers=headers, timeout=20)
    html = r.text
    result["status"] = r.status_code
    result["has_next_data"] = "__NEXT_DATA__" in html
    result["has_api_ref"] = bool(re.findall(r'"/api/[a-zA-Z0-9_\-/]+"', html))
    result["api_paths"] = list(set(re.findall(r'"(/api/[a-zA-Z0-9_\-/]+)"', html)))[:20]
    idx = html.find("__NEXT_DATA__")
    if idx > -1:
        result["next_data_sample"] = html[idx:idx+2000]
    # also try common API guesses
    for path in ["/api/picks", "/api/picks/free", "/api/free-picks", "/api/edges", "/api/predictions"]:
        try:
            r2 = requests.get(f"https://theedgesniper.com{path}", headers=headers, timeout=10)
            result[f"try_{path}"] = {"status": r2.status_code, "len": len(r2.text)}
        except Exception as e:
            result[f"try_{path}"] = {"error": str(e)[:100]}

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note":"TEMP es deep","result":result}, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
