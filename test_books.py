from curl_cffi import requests as cf
s = cf.Session(impersonate="chrome124")

print("=== DraftKings ===")
r = s.get("https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets",
    params={"isBatchable":"false","templateVars":"42648",
            "eventsQuery":"$filter=leagueId eq '42648' AND clientMetadata/Subcategories/any(s: s/Id eq '16477')",
            "marketsQuery":"$filter=clientMetadata/subCategoryId eq '16477' AND tags/all(t: t ne 'SportcastBetBuilder')",
            "include":"Events","entity":"events"}, timeout=15)
print(f"Status: {r.status_code} | Size: {len(r.text)}")
if r.status_code == 200:
    d = r.json()
    print(f"Keys: {list(d.keys())[:8]}")
    for k,v in d.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items")
            if v and isinstance(v[0], dict):
                print(f"    Sample keys: {list(v[0].keys())[:6]}")
else:
    print(f"Error: {r.text[:200]}")

print()
print("=== FanDuel ===")
r2 = s.get("https://api.sportsbook.fanduel.com/sbapi/content-managed-page",
    params={"page":"SPORT","eventTypeId":"7522","_ak":"FhMFpcPWXMeyZxOx"},
    headers={"Origin":"https://az.sportsbook.fanduel.com",
             "Referer":"https://az.sportsbook.fanduel.com/",
             "x-application":"FhMFpcPWXMeyZxOx"}, timeout=15)
print(f"Status: {r2.status_code} | Size: {len(r2.text)}")
if r2.status_code == 200:
    d2 = r2.json()
    att = d2.get("attachments",{})
    print(f"Events: {len(att.get('events',{}))} | Markets: {len(att.get('markets',{}))}")
else:
    print(f"Error: {r2.text[:200]}")

print()
print("=== BetMGM ===")
r3 = s.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixtures",
    params={"x-bwin-accessid":"N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5",
            "lang":"en-us","country":"US","userCountry":"US",
            "subdivision":"US-AZ","sportIds":"7","state":"Latest","take":"5"}, timeout=15)
print(f"Status: {r3.status_code} | Size: {len(r3.text)}")
if r3.status_code == 200:
    d3 = r3.json()
    fx = d3.get("fixtures",[])
    print(f"Fixtures: {len(fx)}")
    if fx:
        g = fx[0].get("games",[])
        print(f"First fixture games: {len(g)}")
        for gg in g[:3]:
            print(f"  {gg.get('name',{}).get('value','')}")
else:
    print(f"Error: {r3.text[:200]}")

print()
print("=== Caesars ===")
r4 = s.get("https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/basketball/competitions", timeout=15)
print(f"Status: {r4.status_code} | Size: {len(r4.text)}")
if r4.status_code == 200:
    print(f"Data: {r4.text[:300]}")
else:
    print(f"Error: {r4.text[:200]}")
