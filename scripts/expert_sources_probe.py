import json, os, re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "text/html,application/json"}
out = {}
r = requests.get("https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/", headers=H, timeout=30)
rows = re.findall(r"<tr.*?</tr>", r.text, re.S)[1:5]
out["dk_rows"] = [[re.sub(r"<[^>]+>|\s+", " ", c).strip() for c in re.findall(r"<td.*?</td>", x, re.S)] for x in rows]
tests = {}
try:
    from curl_cffi import requests as cc
    for imp in ("chrome124", "chrome110", "safari17_0"):
        try:
            rr = cc.get("https://api.nflpickwatch.com/v1/general/metadata", impersonate=imp, timeout=30,
                        headers={"Accept": "application/json", "Origin": "https://nflpickwatch.com", "Referer": "https://nflpickwatch.com/"})
            tests[imp] = {"status": rr.status_code, "head": rr.text[:120]}
        except Exception as e:
            tests[imp] = {"err": str(e)[:120]}
except Exception as e:
    tests["import"] = str(e)[:150]
rr = requests.get("https://api.nflpickwatch.com/v1/general/metadata", timeout=30,
                  headers={"Accept": "application/json", "Origin": "https://nflpickwatch.com", "Referer": "https://nflpickwatch.com/", "User-Agent": H["User-Agent"]})
tests["requests+origin"] = {"status": rr.status_code, "head": rr.text[:120]}
out["pickwatch"] = tests
out["bp_markets"] = {}
for sp in ("nba", "nfl", "nhl"):
    try:
        rb = requests.get(f"https://www.bettingpros.com/{sp}/props/", headers=H, timeout=30)
        for b in re.findall(r'<script type="application/json" class="island-props">(.*?)</script>', rb.text, re.S):
            if '"offers"' in b:
                d = json.loads(b)
                out["bp_markets"][sp] = {str(m["id"]): (m.get("meta", {}).get("short_label") or m.get("slug")) for m in (d.get("markets", []) + d.get("marketsData", []))}
                break
    except Exception as e:
        out["bp_markets"][sp] = str(e)[:100]
txt = json.dumps(out, indent=1, default=str)
print(txt[:6000])
requests.patch("https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
    headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", "")},
    json={"files": {"betcouncil_expert_sources_probe.json": {"content": txt}}}, timeout=30)
