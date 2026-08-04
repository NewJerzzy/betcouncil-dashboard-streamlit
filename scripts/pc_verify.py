import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get("https://propcruncher.com/props/best-plays", headers=headers, timeout=20)
        result["status"] = r.status_code
        result["len"] = len(r.text)
        result["has_frederick_freeman"] = "Frederick Freeman" in r.text
        result["has_json_ld"] = 'application/ld+json' in r.text
        # find all JSON-LD script blocks
        matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
        result["num_json_ld_blocks"] = len(matches)
        if matches:
            for i, m in enumerate(matches):
                try:
                    parsed = json.loads(m)
                    result[f"json_ld_{i}_type"] = parsed.get("@type", "?")
                    if parsed.get("@type") == "ItemList":
                        items = parsed.get("itemListElement", [])
                        result[f"json_ld_{i}_num_items"] = len(items)
                        result[f"json_ld_{i}_sample"] = items[:3]
                except Exception as e:
                    result[f"json_ld_{i}_parse_error"] = str(e)[:200]
        if r.status_code != 200:
            result["sample_403_body"] = r.text[:500]
    except Exception as e:
        result["error"] = str(e)[:300]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP propcruncher exact-headers verify", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
