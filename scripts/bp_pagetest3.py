import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def get_props(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code != 200:
        return None, r.status_code, 0
    blocks = re.findall(r'<script type="application/json" class="island-props">(.*?)</script>', r.text, re.DOTALL)
    if not blocks:
        return None, "no_blocks", 0
    # pick the largest block (the real data island, not the empty placeholders)
    best = max(blocks, key=len)
    try:
        data = json.loads(best)
        return data, r.status_code, len(blocks)
    except Exception as e:
        return None, f"parse_error: {e}", len(blocks)

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    for label, url in [
        ("page1", "https://www.bettingpros.com/mlb/props/"),
        ("page2", "https://www.bettingpros.com/mlb/props/?page=2"),
        ("page3", "https://www.bettingpros.com/mlb/props/?page=3"),
        ("page10", "https://www.bettingpros.com/mlb/props/?page=10"),
    ]:
        data, status, num_blocks = get_props(url)
        if data:
            props = data.get("props", [])
            result[label] = {"status": status, "num_blocks": num_blocks, "num_props": len(props)}
            if props:
                result[label]["sample_names"] = [p.get("participant", {}).get("name") for p in props[:5]]
        else:
            result[label] = {"status": status, "num_blocks": num_blocks, "error": True}

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_zz_bp_temp_debug_9f8e7d.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
