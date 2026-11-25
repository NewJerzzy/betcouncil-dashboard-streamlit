import json, os, requests
H = {"Accept": "application/json", "Origin": "https://nflpickwatch.com", "Referer": "https://nflpickwatch.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
A = "https://api.nflpickwatch.com/v1/general"
out = {}
m = requests.get(f"{A}/metadata", headers=H, timeout=30).json()
cur = m["timeframes"]["nfl"]["current"]; out["current"] = cur
s, w, ph = cur["season_id"], cur["week_id"], cur["week_type_id"]
games = requests.get(f"{A}/games/{s}/{w}/nfl/{ph}?region_id=1", headers=H, timeout=30).json()
out["games"] = [{k: g.get(k) for k in ("id", "home_team_id", "road_team_id", "kickoff", "kicked_off", "spread", "home_spread", "line")} for g in games[:6]]
out["game_keys"] = list(games[0])
cat = requests.get(f"{A}/experts-list", headers=H, timeout=30).json()
out["catalog_n"] = len(cat); out["catalog_sample"] = cat[:2]
ex = ["pete-prisco","tyler-sullivan","dave-richard","jared-dubin","john-breech","brad-gagnon","brent-sobleski","gary-davenport","bill-bender","vinnie-iyer","chris-simms","frank-schwab","gennaro-filice","jarrett-bell","sam-farmer"]
out["card_n"] = {}; out["card"] = []
for e in ex:
    try:
        c = requests.get(f"{A}/profile/picks/nfl/{e}/{s}/{w}", params={"types": '["ats"]', "teams": "[]"}, headers=H, timeout=30).json()
        pk = c.get("picks", [])
        out["card_n"][e] = [len(pk), sum(1 for x in pk if x.get("pick") in ("_locked","locked"))]
        out["card"] += [x for x in pk if x.get("pick") not in ("_locked","locked")][:2]
    except Exception as ee:
        out["card_n"][e] = str(ee)[:60]
out["games_spread"] = [{k: g.get(k) for k in ("home_team_id","road_team_id","home_team_spread","road_team_spread","over_under")} for g in games[:4]]
out["team_sample"] = (m.get("teams", {}).get("nfl", {}).get("selectTeams") or [])[:2]
txt = json.dumps(out, indent=1, default=str)
print(txt[:6000])
requests.patch("https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
    headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", "")},
    json={"files": {"betcouncil_expert_sources_probe.json": {"content": txt}}}, timeout=30)
