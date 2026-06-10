from curl_cffi import requests as cf
import json
s = cf.Session(impersonate="chrome124")

print("=== DraftKings (FIXED PARSER) ===")
r = s.get("https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets",
    params={"isBatchable":"false","templateVars":"42648",
            "eventsQuery":"$filter=leagueId eq '42648' AND clientMetadata/Subcategories/any(s: s/Id eq '16477')",
            "marketsQuery":"$filter=clientMetadata/subCategoryId eq '16477' AND tags/all(t: t ne 'SportcastBetBuilder')",
            "include":"Events","entity":"events"}, timeout=15)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    markets = d.get("markets", [])
    selections = d.get("selections", [])
    print(f"Markets: {len(markets)} | Selections: {len(selections)}")

    # Build selection lookup by marketId
    sel_by_mkt = {}
    for sel in selections:
        mid = sel.get("marketId")
        if mid:
            sel_by_mkt.setdefault(mid, []).append(sel)

    props = []
    for mkt in markets:
        mkt_name = mkt.get("name", "")
        mkt_id = mkt.get("id")
        for sel in sel_by_mkt.get(mkt_id, []):
            label = sel.get("label", "")
            odds = sel.get("displayOdds", {}).get("american", "")
            # participants has player info
            parts = sel.get("participants", [])
            player = ""
            if parts:
                player = parts[0].get("name", "")
            if not player:
                player = label

            # Parse Over/Under
            side = "OVER"
            if "Under" in label:
                side = "UNDER"
                player = label.replace("Under", "").strip()
            elif "Over" in label:
                player = label.replace("Over", "").strip()

            # Get line from market or selection
            line = sel.get("points") or sel.get("line")
            if line is None:
                # Try to extract from label
                import re
                m = re.search(r"([\d.]+)", label)
                if m:
                    line = float(m.group(1))

            if player and line is not None:
                props.append(f"{player:30} {mkt_name:25} {line:6} {side:5} {odds}")

    print(f"Props found: {len(props)}")
    for p in props[:10]:
        print(f"  {p}")

print()
print("=== BetMGM (fixture-offers) ===")
r1 = s.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixtures",
    params={"x-bwin-accessid":"N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5",
            "lang":"en-us","country":"US","userCountry":"US",
            "subdivision":"US-AZ","sportIds":"7","state":"Latest","take":"10"}, timeout=15)
print(f"Fixtures: {r1.status_code}")
if r1.status_code == 200:
    fx = r1.json().get("fixtures", [])
    print(f"Count: {len(fx)}")
    for f in fx[:3]:
        fid = f.get("id")
        fname = f.get("name", {}).get("value", "") if isinstance(f.get("name"), dict) else f.get("name","")
        games = f.get("games", [])
        print(f"  ID: {fid} | Name: {fname} | Games: {len(games)}")
        print(f"  Keys: {list(f.keys())[:10]}")
        # Try fixture-offers for this fixture
        if fid:
            r2 = s.get("https://www.az.betmgm.com/cds-api/bettingoffer/fixture-offers",
                params={"x-bwin-accessid":"N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5",
                        "lang":"en-us","country":"US","userCountry":"US",
                        "subdivision":"US-AZ","fixtureIds":fid,"offerMapping":"Filtered"},
                timeout=10)
            print(f"  fixture-offers: {r2.status_code} | Size: {len(r2.text)}")
            if r2.status_code == 200:
                d2 = r2.json()
                fxo = d2.get("fixtures", [d2]) if isinstance(d2, dict) else d2
                for fxd in fxo[:1]:
                    fo_games = fxd.get("games", [])
                    print(f"  Games in offers: {len(fo_games)}")
                    for g in fo_games[:3]:
                        gname = g.get("name", {}).get("value", "")
                        results = g.get("results", [])
                        print(f"    {gname}: {len(results)} results")
                        for res in results[:2]:
                            rname = res.get("name", {}).get("value", "")
                            attr = res.get("attr", "")
                            odds = res.get("price", {}).get("americanOdds", "")
                            print(f"      {rname} | line={attr} | odds={odds}")

print()
print("=== FanDuel (try event-page directly) ===")
# Try getting events list first
r5 = s.get("https://api.sportsbook.fanduel.com/sbapi/content-managed-page",
    params={"page":"SPORT","eventTypeId":"7522","_ak":"FhMFpcPWXMeyZxOx","timezone":"America/Phoenix"},
    headers={"Origin":"https://az.sportsbook.fanduel.com",
             "Referer":"https://az.sportsbook.fanduel.com/",
             "x-application":"FhMFpcPWXMeyZxOx"}, timeout=15)
print(f"Content-managed: {r5.status_code}")
if r5.status_code != 200:
    # Try without timezone
    r5b = s.get("https://api.sportsbook.fanduel.com/sbapi/content-managed-page",
        params={"page":"SPORT","eventTypeId":"7522","_ak":"FhMFpcPWXMeyZxOx"},
        headers={"Origin":"https://az.sportsbook.fanduel.com",
                 "Referer":"https://az.sportsbook.fanduel.com/",
                 "x-application":"FhMFpcPWXMeyZxOx"}, timeout=15)
    print(f"Without timezone: {r5b.status_code}")
    # Try the event-page for known game
    r5c = s.get("https://api.sportsbook.fanduel.com/sbapi/event-page",
        params={"_ak":"FhMFpcPWXMeyZxOx","eventId":"35701926","tab":"player-props"},
        headers={"Origin":"https://az.sportsbook.fanduel.com",
                 "Referer":"https://az.sportsbook.fanduel.com/",
                 "x-application":"FhMFpcPWXMeyZxOx"}, timeout=15)
    print(f"Event-page direct: {r5c.status_code} | Size: {len(r5c.text)}")
    if r5c.status_code == 200:
        d5 = r5c.json()
        att = d5.get("attachments", {})
        print(f"Markets: {len(att.get('markets',{}))}")
