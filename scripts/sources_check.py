import json, os, sys, requests
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def age_min(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 60, 1)
    except Exception:
        return None

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}

    # betql
    try:
        r = requests.get("https://api.github.com/gists/" + GIST_ID,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        files = r.json()["files"]

        # BetQL - own file
        bql_name = "betcouncil_betql_MLB.json"
        if bql_name in files:
            d = requests.get(files[bql_name]["raw_url"]).json()
            result["betql"] = {"age_min": age_min(d.get("captured_at")), "num_games": len(d.get("games", []))}
        else:
            result["betql"] = "FILE MISSING"

        # Pickswise - own file
        pw_name = "betcouncil_pickswise_MLB.json"
        if pw_name in files:
            d = requests.get(files[pw_name]["raw_url"]).json()
            result["pickswise"] = {"age_min": age_min(d.get("captured_at")), "raw_keys": list(d.keys())}
        else:
            result["pickswise"] = "FILE MISSING"

        # WiseGuyTeam - sharp_feeds.json merged
        sf_name = "betcouncil_sharp_feeds.json"
        if sf_name in files:
            d = requests.get(files[sf_name]["raw_url"]).json()
            wgt = d.get("wiseguyteam", {}).get("MLB", {})
            result["wiseguyteam"] = {"age_min": age_min(wgt.get("captured_at")), "num_games": len(wgt.get("games", []))}
        else:
            result["wiseguyteam"] = "FILE MISSING"

        # GameLinePicks - market_feeds.json merged
        mf_name = "betcouncil_market_feeds.json"
        if mf_name in files:
            d = requests.get(files[mf_name]["raw_url"]).json()
            glp = d.get("gamelinepicks", {})
            picks = glp.get("picks", [])
            mlb_picks = [p for p in picks if p.get("sport","").upper() == "MLB"]
            result["gamelinepicks"] = {"age_min": age_min(glp.get("captured_at")), "num_mlb_picks": len(mlb_picks)}
        else:
            result["gamelinepicks"] = "FILE MISSING"

        # SignalOdds predictions - live API, not gist
        try:
            r2 = requests.get("https://api.betslib.com/predictions?date_filter=upcoming&limit=20&page=1&sort_by=commence_time&sort_dir=asc&sport=baseball",
                headers={"Accept":"application/json","Origin":"https://signalodds.com","Referer":"https://signalodds.com/","x-client-source":"web"}, timeout=15)
            d2 = r2.json()
            items = d2.get("data", {}).get("items", []) if isinstance(d2.get("data"), dict) else d2.get("data", [])
            result["signalodds"] = {"status": r2.status_code, "num_items": len(items) if isinstance(items, list) else "N/A"}
        except Exception as e:
            result["signalodds"] = {"error": str(e)[:200]}

    except Exception as e:
        result["error"] = str(e)[:300]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP predictions sources check", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
