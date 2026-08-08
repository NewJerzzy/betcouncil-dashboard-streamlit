import json, os, sys, requests, re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    result = {}
    r = requests.get("https://www.bettingpros.com/mlb/props/", headers=headers, timeout=20)
    html = r.text
    result["status"] = r.status_code
    result["len"] = len(html)

    # find the full script block containing "events" and search within it for props-shaped data
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    events_script = next((s for s in script_blocks if '"events"' in s and '"pitchers"' in s), None)
    if events_script:
        result["events_script_len"] = len(events_script)
        # look for prop-specific keys within this or other scripts
        for marker in ['"projection"', '"bet_rating"', '"over"', '"line":', '"odds"', 'best_bets', 'propBets', 'props_data']:
            result[f"has_{marker}"] = marker in events_script

    # search ALL scripts for anything with "projection" or "bet_rating"
    prop_data_scripts = [s for s in script_blocks if '"projection"' in s or '"bet_rating"' in s]
    result["num_scripts_with_projection_or_rating"] = len(prop_data_scripts)
    if prop_data_scripts:
        # find a slice around the first "projection" occurrence
        s = prop_data_scripts[0]
        idx = s.find('"projection"')
        if idx == -1:
            idx = s.find('"bet_rating"')
        result["prop_sample"] = s[max(0,idx-500):idx+2000]

    # Also check script tag ids/types to understand the page's JS framework
    script_tags = re.findall(r'<script([^>]*)>', html)
    result["script_tag_attrs_sample"] = list(set(script_tags))[:15]

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
