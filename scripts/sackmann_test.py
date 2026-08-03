import json, os, sys, requests, traceback, csv, io
from collections import defaultdict

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://stats.tennismylife.org/data"
YEARS = [2025, 2026]
STAT_COLS = ["ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "SvGms", "bpSaved", "bpFaced"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BetCouncilResearch/1.0)"}

def fetch_csv_rows(tour, year):
    url = f"{BASE_URL}/{year}.csv"
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        return []
    reader = csv.DictReader(io.StringIO(r.text))
    return list(reader)

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    try:
        rows = fetch_csv_rows("ATP", 2026)
        result["num_rows_2026"] = len(rows)
        if rows:
            result["real_columns"] = list(rows[0].keys())
            result["sample_row"] = rows[0]
    except Exception as e:
        result["error"] = str(e)
        result["trace"] = traceback.format_exc()[:1500]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP sackmann csv columns", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
