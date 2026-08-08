import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://www.bettingpros.com/mlb/props/", headers=HEADERS, timeout=20)
    html = r.text
    blocks = re.findall(r'<script type="application/json" class="island-props">(.*?)</script>', html, re.DOTALL)
    result = {}
    for blk in blocks:
        if '"events"' not in blk:
            continue
        parsed = json.loads(blk)
        offers = parsed.get("offers", [])
        result["num_offers"] = len(offers)
        result["pagination"] = parsed.get("pagination")
        if offers:
            result["sample_offer"] = offers[0]
        break

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
