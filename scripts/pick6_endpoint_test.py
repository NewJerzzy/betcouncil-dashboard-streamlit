import json, os, sys, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def log(m):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {m}", flush=True)

def main():
    token = os.environ.get("GITHUB_TOKEN")
    r = requests.get("https://pick6.draftkings.com/resources/pickCardsByCategory/151460/1", headers=HEADERS, timeout=15)
    data = r.json()
    entity_map = data.get("entityInfoByDkId", {})
    log(f"entityInfoByDkId has {len(entity_map)} entries")
    sample_items = list(entity_map.items())[:5]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({
            "note": "TEMP pick6 entityInfoByDkId check",
            "count": len(entity_map),
            "samples": sample_items,
        }, default=str)}}},
    )
    log(f"push: {resp.status_code}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
