import json, os, sys, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def log(m):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {m}", flush=True)

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}

    # 1. Get homepage, find pickGroupId
    r = requests.get("https://pick6.draftkings.com/?sport=MLB", headers=HEADERS, timeout=15)
    results["homepage_status"] = r.status_code
    import re
    m = re.search(r'pickGroupId["\']?\s*[:=]\s*["\']?(\d+)', r.text)
    results["found_pickgroupid"] = m.group(1) if m else None
    log(f"homepage: {r.status_code}, pickGroupId found: {results['found_pickgroupid']}")

    pgid = results["found_pickgroupid"] or "151460"
    for cat in [1, 5, 10]:
        url = f"https://pick6.draftkings.com/resources/pickCardsByCategory/{pgid}/{cat}"
        try:
            rr = requests.get(url, headers=HEADERS, timeout=15)
            results[f"cat_{cat}_status"] = rr.status_code
            results[f"cat_{cat}_len"] = len(rr.text)
            if rr.status_code == 200:
                try:
                    data = rr.json()
                    results[f"cat_{cat}_keys"] = list(data.keys()) if isinstance(data, dict) else f"list len {len(data)}"
                    results[f"cat_{cat}_sample"] = json.dumps(data)[:1500]
                except Exception as je:
                    results[f"cat_{cat}_json_error"] = str(je)
                    results[f"cat_{cat}_snippet"] = rr.text[:500]
        except Exception as e:
            results[f"cat_{cat}_error"] = str(e)
        log(f"category {cat}: {results.get(f'cat_{cat}_status')}")

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP pick6 endpoint test", "results": results}, default=str)}}},
    )
    log(f"push: {resp.status_code}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
