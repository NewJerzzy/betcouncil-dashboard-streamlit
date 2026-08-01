import json, os, sys, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    base = "https://api-production-3a3b.up.railway.app"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    r = requests.get(base + "/api/ev", headers=headers, timeout=20)
    data = r.json()
    result = {"status": r.status_code, "top_keys": list(data.keys())}
    for k in data.keys():
        v = data[k]
        if isinstance(v, list):
            result[f"{k}_type"] = f"list len {len(v)}"
            if v:
                result[f"{k}_sample"] = v[0]
        elif isinstance(v, dict):
            result[f"{k}_type"] = f"dict keys {list(v.keys())[:5]}"

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP evsharps ev full structure", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
