import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    results = {}
    # ESPN standings - check for O/U or ATS splits
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/standings", headers=headers, timeout=15)
        data = r.json()
        s = json.dumps(data)
        results["espn_standings_has_ou"] = "overUnder" in s or "atsWins" in s or "ATS" in s
        results["espn_standings_sample_keys"] = list(data.keys())
    except Exception as e:
        results["espn_standings_error"] = str(e)[:300]

    # covers.com ATS page
    try:
        r2 = requests.get("https://www.covers.com/sport/football/nfl/teams", headers=headers, timeout=15)
        results["covers_status"] = r2.status_code
        results["covers_has_ats"] = "against the spread" in r2.text.lower() or "ats" in r2.text.lower()
    except Exception as e:
        results["covers_error"] = str(e)[:300]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP ats source test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
