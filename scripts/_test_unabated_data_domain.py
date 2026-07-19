"""Quick diagnostic: test data.unabated.com/market/mlb/props/odds claim
before trusting it, separate from the already-working production script
targeting api-k.unabated.com. Not a production scraper."""
import json, os, sys
from datetime import datetime, timezone
import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {
    "Accept": "application/json",
    "Referer": "https://unabated.com/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}
    for name, url in [
        ("bettype", "https://data.unabated.com/bettype"),
        ("props_odds", "https://data.unabated.com/market/mlb/props/odds"),
        ("props_people", "https://data.unabated.com/market/mlb/props/people"),
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            body_sample = None
            try:
                j = r.json()
                body_sample = json.dumps(j, default=str)[:2000]
            except Exception:
                body_sample = r.text[:500]
            results[name] = {"url": url, "status": r.status_code,
                              "content_type": r.headers.get("content-type",""),
                              "size": len(r.content), "body_sample": body_sample}
        except Exception as e:
            results[name] = {"url": url, "error": str(e)}

    payload = {"betcouncil_unabated_data_domain_test.json": {
        "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                "results": results}, indent=2, default=str)
    }}
    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
                           headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                           json={"files": payload}, timeout=30)
    print("push status:", resp.status_code)
    for k, v in results.items():
        print(k, "->", v.get("status"), v.get("size"))

if __name__ == "__main__":
    main()
