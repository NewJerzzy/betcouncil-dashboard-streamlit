import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}

    # Test 1: standard request, no cache headers
    try:
        r1 = requests.get("https://theoddsgap.com/api/dfs-edges", timeout=20)
        d1 = r1.json()
        results["no_headers"] = {
            "status": r1.status_code,
            "generated_at": d1.get("generated_at"),
            "num_edges": len(d1.get("edges", [])),
            "sample_event": d1.get("edges", [{}])[0].get("event") if d1.get("edges") else None,
            "sample_commence": d1.get("edges", [{}])[0].get("commence_time") if d1.get("edges") else None,
        }
    except Exception as e:
        results["no_headers"] = {"error": str(e)[:300]}

    # Test 2: with Cache-Control/Pragma no-cache headers
    try:
        headers = {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        r2 = requests.get("https://theoddsgap.com/api/dfs-edges", headers=headers, timeout=20)
        d2 = r2.json()
        results["with_nocache_headers"] = {
            "status": r2.status_code,
            "generated_at": d2.get("generated_at"),
            "num_edges": len(d2.get("edges", [])),
            "sample_event": d2.get("edges", [{}])[0].get("event") if d2.get("edges") else None,
            "sample_commence": d2.get("edges", [{}])[0].get("commence_time") if d2.get("edges") else None,
        }
    except Exception as e:
        results["with_nocache_headers"] = {"error": str(e)[:300]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP oddsgap cache header test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
