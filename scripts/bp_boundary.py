import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    result = {}
    r = requests.get("https://www.bettingpros.com/mlb/props/", headers=headers, timeout=20)
    html = r.text

    script_blocks = re.findall(r'<script([^>]*)>(.*?)</script>', html, re.DOTALL)
    target = None
    for attrs, content in script_blocks:
        if '"projection"' in content and '"bet_rating"' in content:
            target = (attrs, content)
            break

    if target:
        attrs, content = target
        result["script_attrs"] = attrs
        result["content_len"] = len(content)
        result["content_start"] = content[:300]
        result["content_end"] = content[-300:]
        # try to find a clean JSON parse by looking for common wrapper patterns
        # e.g. window.__X__ = {...};  or  self.__next_f.push([1,"..."])
        eq_idx = content.find('=')
        result["around_first_eq"] = content[max(0,eq_idx-50):eq_idx+200]

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
