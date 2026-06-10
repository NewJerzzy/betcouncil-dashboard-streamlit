from curl_cffi import requests as cf
import json
s = cf.Session(impersonate="chrome124")

print("=== DraftKings — parsing test ===")
r = s.get("https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets",
    params={"isBatchable":"false","templateVars":"42648",
            "eventsQuery":"$filter=leagueId eq '42648' AND clientMetadata/Subcategories/any(s: s/Id eq '16477')",
            "marketsQuery":"$filter=clientMetadata/subCategoryId eq '16477' AND tags/all(t: t ne 'SportcastBetBuilder')",
            "include":"Events","entity":"events"}, timeout=15)

if r.status_code == 200:
    d = r.json()
    markets = d.get("markets", [])
    selections = d.get("selections", [])
    print(f"Markets: {len(markets)} | Selections: {len(selections)}")
    
    # Show first 3 markets
    for m in markets[:3]:
        print(f"  Market: {m.get('name','')} | ID: {m.get('id','')}")
    
    # Show first 5 selections
    for sel in selections[:5]:
        print(f"  Sel: label={sel.get('label','')} | marketId={sel.get('marketId','')} | odds={sel.get('displayOdds',{})}")
        print(f"       participants={sel.get('participants',[])} | points={sel.get('points','')} | handicap={sel.get('handicap','')}")
    
    # Try to parse props
    props = []
    mkt_map = {m.get("id"): m.get("name","") for m in markets}
    
    for sel in selections:
        mid = sel.get("marketId")
        mname = mkt_map.get(mid, "")
        label = sel.get("label", "")
        odds = sel.get("displayOdds", {}).get("american", "")
        points = sel.get("points")
        handicap = sel.get("handicap")
        line = points if points is not None else handicap
        
        # Get player from participants
        participants = sel.get("participants", [])
        player = ""
        if participants:
            player = participants[0].get("name", "") if isinstance(participants[0], dict) else str(participants[0])
        
        # If no participant, try label
        if not player:
            player = label
            if " Over " in player:
                player = player.split(" Over ")[0].strip()
            elif " Under " in player:
                player = player.split(" Under ")[0].strip()
        
        side = "OVER"
        if "under" in label.lower(): side = "UNDER"
        elif "over" in label.lower(): side = "OVER"
        
        if player and line is not None:
            props.append(f"{player} | {mname} | {line} | {side} | {odds}")
    
    print(f"\nParsed {len(props)} props:")
    for p in props[:10]:
        print(f"  {p}")

print()
print("=== FanDuel — try event-page directly ===")
# Try a direct event page instead of content-managed-page
r2 = s.get("https://api.sportsbook.fanduel.com/sbapi/event-page",
    params={"_ak":"FhMFpcPWXMeyZxOx","eventId":"35701926","tab":"player-props"},
    headers={"Origin":"https://az.sportsbook.fanduel.com",
             "Referer":"https://az.sportsbook.fanduel.com/",
             "x-application":"FhMFpcPWXMeyZxOx"}, timeout=15)
print(f"Event-page: {r2.status_code} | Size: {len(r2.text)}")
if r2.status_code == 200:
    d2 = r2.json()
    att = d2.get("attachments",{})
    print(f"Markets: {len(att.get('markets',{}))} | Selections: {len(att.get('selections',{}))}")

# Try navigation to get today events
r2b = s.get("https://api.sportsbook.fanduel.com/sbapi/navigation",
    params={"_ak":"FhMFpcPWXMeyZxOx"},
    headers={"Origin":"https://az.sportsbook.fanduel.com",
             "Referer":"https://az.sportsbook.fanduel.com/",
             "x-application":"FhMFpcPWXMeyZxOx"}, timeout=15)
print(f"Navigation: {r2b.status_code}")

print()
print("=== BetMGM — try with player-props filter ===")
r3 = s.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixtures",
    params={"x-bwin-accessid":"N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5",
            "lang":"en-us","country":"US","userCountry":"US",
            "subdivision":"US-AZ","offerMapping":"Filtered",
            "offerCategories":"player-props","sportIds":"7",
            "state":"Latest","take":"5","sortBy":"StartDate"}, timeout=15)
print(f"Fixtures (player-props): {r3.status_code} | Size: {len(r3.text)}")
if r3.status_code == 200:
    d3 = r3.json()
    fx = d3.get("fixtures",[])
    print(f"Fixtures: {len(fx)}")
    if fx:
        f0 = fx[0]
        print(f"Keys: {list(f0.keys())[:8]}")
        games = f0.get("games",[])
        print(f"Games: {len(games)}")
        if games:
            g0 = games[0]
            print(f"Game name: {g0.get('name',{}).get('value','')}")
            results = g0.get("results",[])
            print(f"Results: {len(results)}")
            if results:
                r0 = results[0]
                print(f"First result: name={r0.get('name',{}).get('value','')} attr={r0.get('attr','')} odds={r0.get('price',{}).get('americanOdds','')}")
