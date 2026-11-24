"""One-off: do our OddsPapi / Odds-API.io keys return settlements and closing lines?"""
import json, os, requests
from datetime import datetime, timezone, timedelta
out = {"started": datetime.now(timezone.utc).isoformat(), "oddspapi": {}, "oddsapiio": {}}
OP = os.environ.get("ODDSPAPI_KEY", "")
OA = os.environ.get("ODDS_API_IO_KEY", "")
out["keys_present"] = {"ODDSPAPI_KEY": bool(OP), "ODDS_API_IO_KEY": bool(OA)}

def get(url, **kw):
    try:
        r = requests.get(url, timeout=30, **kw)
        try: body = r.json()
        except Exception: body = r.text[:300]
        return r.status_code, body
    except Exception as e:
        return 0, str(e)[:200]

def trunc(b, n=600):
    s = json.dumps(b, default=str)
    return s[:n]

# ---- OddsPapi ----
if OP:
    base = "https://api.oddspapi.io/v4"
    c, b = get(f"{base}/tournaments", params={"sportId": 1, "apiKey": OP})
    out["oddspapi"]["tournaments"] = {"status": c, "sample": trunc(b, 400)}
    tid = None
    if c == 200 and isinstance(b, list):
        for t in b:
            nm = json.dumps(t).lower()
            if "nfl" in nm and "preseason" not in nm:
                tid = t.get("tournamentId") or t.get("id"); out["oddspapi"]["nfl_tournament"] = t; break
    if tid:
        now = datetime.now(timezone.utc)
        for path in ("fixtures",):
            c, b = get(f"{base}/{path}", params={"tournamentId": tid, "from": (now - timedelta(days=10)).strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d"), "apiKey": OP})
            out["oddspapi"][path] = {"status": c, "sample": trunc(b, 600)}
            fid = None
            if c == 200:
                items = b if isinstance(b, list) else (b.get("data") if isinstance(b, dict) else [])
                for f in items or []:
                    if isinstance(f, dict) and (f.get("fixtureId") or f.get("id")):
                        fid = f.get("fixtureId") or f.get("id"); break
            if fid:
                out["oddspapi"]["fixture_used"] = fid
                c, b = get(f"{base}/settlements", params={"fixtureId": fid, "apiKey": OP})
                out["oddspapi"]["settlements"] = {"status": c, "n_markets": len((b or {}).get("markets", {})) if isinstance(b, dict) else None, "sample": trunc(b, 700)}
                c, b = get(f"{base}/historical-odds", params={"fixtureId": fid, "bookmakers": "pinnacle", "apiKey": OP})
                out["oddspapi"]["historical_odds"] = {"status": c, "sample": trunc(b, 700)}
                c, b = get(f"{base}/scores", params={"fixtureId": fid, "apiKey": OP})
                out["oddspapi"]["scores"] = {"status": c, "sample": trunc(b, 500)}
# ---- Odds-API.io ----
if OA:
    base = "https://api.odds-api.io/v3"
    c, b = get(f"{base}/leagues", params={"sport": "american-football", "apiKey": OA})
    out["oddsapiio"]["leagues"] = {"status": c, "sample": trunc(b, 500)}
    slug = None
    if c == 200 and isinstance(b, list):
        for l in b:
            if "nfl" in json.dumps(l).lower() and "preseason" not in json.dumps(l).lower():
                slug = l.get("slug"); break
    out["oddsapiio"]["nfl_slug"] = slug
    if slug:
        now = datetime.now(timezone.utc)
        c, b = get(f"{base}/historical/events", params={"apiKey": OA, "sport": "american-football", "league": slug,
            "from": (now - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z"), "to": now.strftime("%Y-%m-%dT00:00:00Z")})
        out["oddsapiio"]["events"] = {"status": c, "n": len(b) if isinstance(b, list) else None, "sample": trunc(b, 700)}
        if c == 200 and isinstance(b, list) and b:
            ev = b[0]
            out["oddsapiio"]["event_used"] = {k: ev.get(k) for k in ("id", "home", "away", "date", "status", "scores")}
            c, b2 = get(f"{base}/bookmakers", params={"apiKey": OA})
            out["oddsapiio"]["bookmakers_list_sample"] = {"status": c, "sample": trunc(b2, 500)}
            c, b3 = get(f"{base}/historical/odds", params={"apiKey": OA, "eventId": ev["id"], "bookmakers": "Pinnacle,DraftKings,FanDuel", "markets": "ML,Spread,Totals"})
            out["oddsapiio"]["historical_odds"] = {"status": c, "sample": trunc(b3, 1800)}
txt = json.dumps(out, indent=1, default=str)
print(txt[:6000])
r = requests.patch("https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
    headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", "")},
    json={"files": {"betcouncil_settlement_probe.json": {"content": txt}}}, timeout=30)
print("gist", r.status_code)
