import json, os, sys, re, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://pick6.draftkings.com/?sport=MLB", headers=HEADERS, timeout=15)
    text = r.text
    # search broadly for any pickGroupId-like pattern
    patterns_found = {}
    for pat_name, pat in [
        ("pickGroupId_colon", r'"pickGroupId"\s*:\s*"?(\d+)"?'),
        ("pickGroupId_camel", r'pickGroupId["\']?[:=]\s*["\']?(\d+)'),
        ("pick_group_id_snake", r'pick_group_id["\']?[:=]\s*["\']?(\d+)'),
        ("pickGroups_array", r'"pickGroups"\s*:\s*\[([^\]]{0,200})'),
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        patterns_found[pat_name] = m.group(1) if m else None
    # also grep raw for "pickGroup" substring context
    idx = text.lower().find("pickgroupid")
    context = text[max(0,idx-100):idx+300] if idx > 0 else "not found in raw text"

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({
            "note": "TEMP pick6 pickGroupId pattern search",
            "status": r.status_code, "len": len(text),
            "patterns_found": patterns_found, "context": context,
        }, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
