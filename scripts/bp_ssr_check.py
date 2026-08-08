import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    result = {}
    for url in ["https://www.bettingpros.com/mlb/props/", "https://www.bettingpros.com/mlb/picks/prop-bets/"]:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            html = r.text
            result[url] = {
                "status": r.status_code,
                "len": len(html),
                "has_vb_table": "vb-table" in html,
                "has_player_name_pattern": bool(re.search(r'"player"|"line"|"projection"', html)),
                "has_next_data": "__NEXT_DATA__" in html,
                "has_json_ld": "application/ld+json" in html,
            }
        except Exception as e:
            result[url] = {"error": str(e)[:300]}

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
