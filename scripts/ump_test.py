import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Referer": "https://umpscorecards.com/"}
    try:
        r = requests.get("https://umpscorecards.com/api/games", headers=headers, timeout=60)
        result["status"] = r.status_code
        result["len"] = len(r.text)
        data = r.json()
        rows = data.get("rows", data) if isinstance(data, dict) else data
        result["is_dict"] = isinstance(data, dict)
        result["top_level_keys"] = list(data.keys()) if isinstance(data, dict) else "N/A (list)"
        result["num_rows"] = len(rows) if isinstance(rows, list) else "N/A"
        if isinstance(rows, list) and rows:
            result["sample_row_0"] = rows[0]
            result["sample_row_keys"] = list(rows[0].keys())
            # find a row for Mike Muchlinski specifically (the cited example)
            muchlinski_rows = [row for row in rows if "muchlinski" in str(row.get("umpire","")).lower()]
            result["muchlinski_sample_count"] = len(muchlinski_rows)
            if muchlinski_rows:
                result["muchlinski_sample"] = muchlinski_rows[:3]
    except Exception as e:
        result["error"] = str(e)[:500]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP umpscorecards games structure", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
