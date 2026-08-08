import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    result = {}
    r = requests.get("https://www.bettingpros.com/mlb/props/", headers=headers, timeout=20)
    html = r.text

    # Look for a JS state blob (window.__INITIAL_STATE__, __NUXT__, etc)
    for marker in ["__INITIAL_STATE__", "__NUXT__", "__APOLLO_STATE__", "window.__data", "__PRELOADED_STATE__"]:
        idx = html.find(marker)
        result[f"has_{marker}"] = idx > -1
        if idx > -1:
            result[f"sample_{marker}"] = html[idx:idx+800]

    # JSON-LD blocks
    ld_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    result["num_ld_blocks"] = len(ld_blocks)
    for i, blk in enumerate(ld_blocks[:3]):
        try:
            parsed = json.loads(blk)
            result[f"ld_{i}_type"] = parsed.get("@type", "?") if isinstance(parsed, dict) else str(type(parsed))
            result[f"ld_{i}_sample"] = json.dumps(parsed)[:1500]
        except Exception as e:
            result[f"ld_{i}_error"] = str(e)[:200]

    # Also search for a props-shaped script tag more generally
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    prop_scripts = [s for s in script_blocks if '"line"' in s and '"player"' in s]
    result["num_prop_shaped_scripts"] = len(prop_scripts)
    if prop_scripts:
        result["prop_script_sample"] = prop_scripts[0][:2000]

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
