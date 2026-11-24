"""One-off: can GitHub Actions reach the four expert feeds, and what do they return?"""
import json, os, re, requests
H = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
out = {}
def get(u, **kw):
    try:
        r = requests.get(u, headers=kw.pop("headers", H), timeout=40, **kw)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)
c, b = get("https://www.sportsline.com/sportsline-web/service/v1/mobile/insiderPicks?max=100&offset=0")
try:
    d = json.loads(b); rows = d.get("insiderPicks", [])
    out["sportsline"] = {"status": c, "livePicks": d.get("livePicks"), "rows": len(rows), "sample": rows[:1]}
except Exception:
    out["sportsline"] = {"status": c, "body": b[:300]}
c, b = get("https://api.nflpickwatch.com/v1/general/metadata")
try:
    d = json.loads(b); cur = d["timeframes"]["nfl"]["current"]; out["pickwatch_meta"] = {"status": c, "current": cur}
    s, w, ph = cur["season_id"], cur["week_id"], cur["week_type_id"]
    c2, b2 = get(f"https://api.nflpickwatch.com/v1/general/games/{s}/{w}/nfl/{ph}?region_id=1")
    g = json.loads(b2); out["pickwatch_games"] = {"status": c2, "n": len(g), "sample": g[:1]}
    c3, b3 = get(f"https://api.nflpickwatch.com/v1/general/profile/picks/nfl/pete-prisco/{s}/{w}?types=%5B%22ats%22%5D&teams=%5B%5D")
    p = json.loads(b3); out["pickwatch_card"] = {"status": c3, "n": len(p.get("picks", [])), "sample": p.get("picks", [])[:2]}
except Exception as e:
    out["pickwatch_meta"] = {"status": c, "err": str(e)[:200], "body": b[:200]}
c, b = get("https://vsin.com/wp-json/wp/v2/posts?search=best%20bets&per_page=5&_fields=id,date_gmt,link,title,author")
out["vsin"] = {"status": c, "sample": b[:500]}
c, b = get("https://terminal.fantasylabs.com/picklabs?site=prizepicks&view=experts", headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"})
out["fantasylabs"] = {"status": c, "bytes": len(b), "has_experts": '"experts":' in b.replace('\\"', '"')}
txt = json.dumps(out, indent=1, default=str)
print(txt[:5000])
r = requests.patch("https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
    headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", "")},
    json={"files": {"betcouncil_expert_sources_probe.json": {"content": txt}}}, timeout=30)
print("gist", r.status_code)
