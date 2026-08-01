import json, os, sys, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}

    # DK salaries
    try:
        r = requests.get("https://www.draftkings.com/lobby/getcontests?sport=NBA",
                          headers={**HEADERS, "Referer": "https://www.draftkings.com/"}, timeout=10)
        results["dk_salaries"] = {"status": r.status_code, "len": len(r.text)}
    except Exception as e:
        results["dk_salaries"] = {"error": str(e)[:200]}

    # StatMuse
    try:
        r = requests.get("https://www.statmuse.com/mlb/ask/aaron-judge-home-runs-2026",
                          headers=HEADERS, timeout=10)
        results["statmuse"] = {"status": r.status_code, "len": len(r.text)}
    except Exception as e:
        results["statmuse"] = {"error": str(e)[:200]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP final audit test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
