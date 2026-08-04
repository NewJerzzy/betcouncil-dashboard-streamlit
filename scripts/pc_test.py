import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    result = {}
    try:
        r = requests.get("https://propcruncher.com/props/best-plays", headers=headers, timeout=20)
        result["status"] = r.status_code
        result["len"] = len(r.text)
        result["has_frederick_freeman"] = "Frederick Freeman" in r.text
        result["has_best_play_score_data"] = "Hits" in r.text and "0.5" in r.text
        # check for __NEXT_DATA__ (Next.js embeds real data server-side even in a "CSR" app)
        result["has_next_data_script"] = "__NEXT_DATA__" in r.text
        idx = r.text.find("__NEXT_DATA__")
        if idx > -1:
            result["next_data_sample"] = r.text[idx:idx+500]
        result["sample_html"] = r.text[:1000]
    except Exception as e:
        result["error"] = str(e)[:300]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP propcruncher plain-fetch test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
