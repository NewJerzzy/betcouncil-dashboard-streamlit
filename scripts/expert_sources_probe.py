import json, os, re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "text/html,application/json"}
out = {}
try:
    r = requests.get("https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/", headers=H, timeout=30)
    out["dk"] = {"status": r.status_code, "len": len(r.text), "tables": r.text.count("<table"), "rows": r.text.count("<tr"), "head": r.text[:300] if r.status_code != 200 else ""}
    m = re.search(r"<table.*?</table>", r.text, re.S)
    out["dk"]["table_head"] = m.group(0)[:900] if m else None
except Exception as e:
    out["dk"] = {"err": str(e)[:200]}
try:
    r = requests.get("https://www.bettingpros.com/nba/props/", headers=H, timeout=30)
    blocks = re.findall(r'<script type="application/json" class="island-props">(.*?)</script>', r.text, re.S)
    info = {"status": r.status_code, "blocks": len(blocks)}
    for b in blocks:
        if '"offers"' in b:
            d = json.loads(b); info["keys"] = list(d)[:30]
            for k, v in d.items():
                if k in ("markets", "market", "market_names", "stats") or "market" in k.lower():
                    info[k] = json.dumps(v)[:1200]
            o = d["offers"][0]; info["offer_keys"] = list(o); info["offer_market"] = {k: o[k] for k in o if "market" in k.lower() or "stat" in k.lower()}
            info["page_filters"] = {k: json.dumps(v)[:300] for k, v in d.items() if k not in ("offers", "events")}
            break
    out["bettingpros"] = info
except Exception as e:
    out["bettingpros"] = {"err": str(e)[:300]}
txt = json.dumps(out, indent=1, default=str)
print(txt[:6000])
requests.patch("https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
    headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", "")},
    json={"files": {"betcouncil_expert_sources_probe.json": {"content": txt}}}, timeout=30)
