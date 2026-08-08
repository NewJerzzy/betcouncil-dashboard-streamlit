import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://www.bettingpros.com/mlb/props/", headers=HEADERS, timeout=20)
    html = r.text
    result = {"status": r.status_code, "len": len(html)}

    blocks = re.findall(r'<script type="application/json" class="island-props">(.*?)</script>', html, re.DOTALL)
    result["num_blocks"] = len(blocks)
    result["block_lens"] = [len(b) for b in blocks]
    result["blocks_with_events"] = sum(1 for b in blocks if '"events"' in b)

    for i, blk in enumerate(blocks):
        if '"events"' not in blk:
            continue
        try:
            parsed = json.loads(blk)
            result[f"block_{i}_parse_ok"] = True
            result[f"block_{i}_keys"] = list(parsed.keys())
            result[f"block_{i}_has_props_key"] = "props" in parsed
            result[f"block_{i}_props_len"] = len(parsed.get("props", []))
        except Exception as e:
            result[f"block_{i}_parse_error"] = str(e)[:300]
        break

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
