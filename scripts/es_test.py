import json, os, sys, requests
GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get("https://theedgesniper.com/", headers=headers, timeout=20)
    result = {"status": r.status_code, "len": len(r.text), "has_cf": "challenges.cloudflare.com" in r.text or "Just a moment" in r.text}
    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note":"TEMP es","result":result})}}})
    print(resp.status_code)
if __name__ == "__main__": sys.exit(main())
