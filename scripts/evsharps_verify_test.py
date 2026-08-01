import json, os, sys, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}
    base = "https://api-production-3a3b.up.railway.app"
    # Deliberately NO Authorization header at all
    headers_no_auth = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    for path in ["/api/ev", "/api/mlb"]:
        try:
            r = requests.get(base + path, headers=headers_no_auth, timeout=20)
            results[path] = {"status": r.status_code, "len": len(r.text), "sample": r.text[:1200]}
        except Exception as e:
            results[path] = {"error": str(e)[:300]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP evsharps no-auth verify", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
