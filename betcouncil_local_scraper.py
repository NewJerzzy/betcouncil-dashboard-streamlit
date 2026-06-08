#!/usr/bin/env python3
"""
BetCouncil Local Scraper
========================
Run this on YOUR machine (not Streamlit Cloud).
Your home IP is residential — DK/FD/BetMGM won't block it.

Scrapes: DraftKings, FanDuel, BetMGM player props
Pushes:  to GitHub Gist → BetCouncil reads it automatically

Usage:
  python3 betcouncil_local_scraper.py --sport NBA
  python3 betcouncil_local_scraper.py --sport MLB
  python3 betcouncil_local_scraper.py --all

Requirements:
  pip install requests

Schedule (optional):
  Mac: crontab -e → add: */30 * * * * python3 /path/to/script.py --all
  Win: Task Scheduler → run every 30 minutes
"""

import requests
import json
import time
import argparse
import base64
from datetime import datetime, date

# ── CONFIG ──────────────────────────────────────────────────
GITHUB_TOKEN = "YOUR_GITHUB_TOKEN_HERE"  # paste your token from Streamlit secrets
GIST_ID      = "YOUR_GIST_ID_HERE"       # paste your Gist ID from Streamlit secrets
GIST_FILE    = "local_book_props.json"   # new file in existing Gist

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ── SPORT MAPS ───────────────────────────────────────────────
DK_CATEGORY_MAP = {
    "NBA": {"sportId": 42648, "subcategoryIds": [743, 1000, 1001, 1002]},
    "MLB": {"sportId": 84240, "subcategoryIds": [1188, 1189, 1190, 1191]},
    "NHL": {"sportId": 42133, "subcategoryIds": [1210, 1211]},
    "WNBA": {"sportId": 42648, "subcategoryIds": [743]},
}

FD_MARKET_MAP = {
    "NBA": {"eventTypeId": 7522, "marketTypeIds": [1,...,100]},
    "MLB": {"eventTypeId": 1,    "marketTypeIds": [1,...,100]},
}

# ── HELPERS ──────────────────────────────────────────────────
def normalize_name(name):
    import unicodedata, re
    name = str(name or "").strip()
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9 ]", "", name.lower())
    name = re.sub(r"\s+", " ", name).strip()
    return name

def fractional_to_american(num, den):
    """Convert fractional odds to American."""
    try:
        ratio = float(num) / float(den)
        if ratio >= 1:
            return f"+{int(ratio * 100)}"
        else:
            return f"{int(-100 / ratio)}"
    except:
        return "—"

def decimal_to_american(decimal):
    """Convert decimal odds to American."""
    try:
        d = float(decimal)
        if d >= 2.0:
            return f"+{int((d - 1) * 100)}"
        else:
            return f"{int(-100 / (d - 1))}"
    except:
        return "—"

# ── DRAFTKINGS SCRAPER ───────────────────────────────────────
def scrape_draftkings(sport="NBA"):
    """
    DraftKings has public sportsbook endpoints.
    No auth required from residential IPs.
    """
    print(f"\nScraping DraftKings {sport}...")
    props = []

    sport_cfg = DK_CATEGORY_MAP.get(sport, {})
    sport_id  = sport_cfg.get("sportId")
    if not sport_id:
        print(f"  ❌ Sport {sport} not configured")
        return props

    # Step 1: Get today's events
    events_url = f"https://sportsbook.draftkings.com/sites/US-NJ-SB/api/v5/eventgroups/{sport_id}/categories/all"
    headers = {**HEADERS, "Referer": "https://sportsbook.draftkings.com/"}

    try:
        r = requests.get(events_url, headers=headers, timeout=10)
        print(f"  Events: {r.status_code}")
        if r.status_code != 200:
            # Try alternate endpoint
            alt_url = f"https://sportsbook-nash.draftkings.com/api/sports/v1/sports/{sport_id}/events"
            r = requests.get(alt_url, headers=headers, timeout=10)
            print(f"  Alt events: {r.status_code}")
            if r.status_code != 200:
                return props

        data = r.json()
        events = data.get("eventGroup", {}).get("events", [])
        if not events:
            # Try different structure
            events = data.get("events", [])

        today = date.today().isoformat()
        today_events = [
            e for e in events
            if e.get("startDate", "")[:10] == today
        ]
        print(f"  Found {len(today_events)} events today")

        # Step 2: Get props for each event
        for event in today_events[:8]:
            event_id = event.get("eventId") or event.get("id")
            if not event_id:
                continue

            # Try player props subcategory
            props_url = (
                f"https://sportsbook.draftkings.com/sites/US-NJ-SB/api/v5/eventgroups/{sport_id}"
                f"/categories/player-props/events/{event_id}"
            )
            try:
                rp = requests.get(props_url, headers=headers, timeout=10)
                if rp.status_code != 200:
                    continue

                pdata    = rp.json()
                markets  = pdata.get("eventGroup", {}).get("offerCategories", [])

                for cat in markets:
                    cat_name = cat.get("name", "")
                    for subcat in cat.get("offerSubcategoryDescriptors", []):
                        for offer in subcat.get("offerSubcategory", {}).get("offers", []):
                            for o in offer:
                                player   = o.get("playerName") or o.get("label", "")
                                line     = o.get("line")
                                outcomes = o.get("outcomes", [])
                                if not player or line is None:
                                    continue
                                over_odds  = next((x.get("oddsAmerican","—") for x in outcomes if x.get("label","").upper()=="OVER"), "—")
                                under_odds = next((x.get("oddsAmerican","—") for x in outcomes if x.get("label","").upper()=="UNDER"), "—")
                                props.append({
                                    "Player":     player,
                                    "Prop":       cat_name,
                                    "Line":       float(line),
                                    "Side":       "OVER",
                                    "OverOdds":   over_odds,
                                    "UnderOdds":  under_odds,
                                    "Book":       "DraftKings",
                                    "Sport":      sport,
                                    "source":     "local_dk",
                                })
                time.sleep(0.5)
            except Exception as e:
                print(f"  Props err for {event_id}: {e}")
                continue

    except Exception as e:
        print(f"  DK Error: {e}")

    print(f"  ✅ {len(props)} DraftKings props")
    return props


# ── FANDUEL SCRAPER ──────────────────────────────────────────
def scrape_fanduel(sport="NBA"):
    """
    FanDuel has a public API with _ak (access key) that works
    from residential IPs.
    """
    print(f"\nScraping FanDuel {sport}...")
    props = []

    event_type_map = {
        "NBA":  7522,
        "MLB":  1,
        "NHL":  4,
        "WNBA": 614,
    }
    event_type_id = event_type_map.get(sport)
    if not event_type_id:
        return props

    headers = {
        **HEADERS,
        "Referer": "https://sportsbook.fanduel.com/",
        "Origin":  "https://sportsbook.fanduel.com",
    }

    # FanDuel API with access key
    url = (
        f"https://sbapi.fanduel.com/api/content-managed-page"
        f"?page=SPORT&eventTypeId={event_type_id}"
        f"&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"
    )

    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"  FD Status: {r.status_code}")
        if r.status_code != 200:
            return props

        data   = r.json()
        events = data.get("result", {}).get("events", [])
        today  = date.today().isoformat()

        for event in events:
            if event.get("openDate","")[:10] != today:
                continue
            event_id = event.get("eventId")
            if not event_id:
                continue

            # Get player props for this event
            props_url = (
                f"https://sbapi.fanduel.com/api/event-page"
                f"?eventId={event_id}&_ak=FhMFpcPWXMeyZxOx"
            )
            try:
                rp = requests.get(props_url, headers=headers, timeout=10)
                if rp.status_code != 200:
                    continue

                pdata   = rp.json()
                markets = pdata.get("result", {}).get("markets", [])

                for market in markets:
                    market_name = market.get("marketName","")
                    if not any(kw in market_name.lower() for kw in
                               ["points","rebounds","assists","strikeout","hits","home run",
                                "goals","shots","yards","receptions","pra","blocks","steals"]):
                        continue

                    runners = market.get("runners", [])
                    for runner in runners:
                        player     = runner.get("runnerName","")
                        handicap   = runner.get("handicap")
                        win_run_to = runner.get("winRunnerOdds",{})
                        odds       = win_run_to.get("americanDisplayOdds",{}).get("americanOdds","—")
                        side       = "OVER" if "over" in runner.get("runnerName","").lower() else "UNDER"

                        if not player or handicap is None:
                            continue

                        props.append({
                            "Player":    player.replace(" Over","").replace(" Under","").strip(),
                            "Prop":      market_name,
                            "Line":      float(handicap),
                            "Side":      side,
                            "OverOdds":  odds if side == "OVER" else "—",
                            "UnderOdds": odds if side == "UNDER" else "—",
                            "Book":      "FanDuel",
                            "Sport":     sport,
                            "source":    "local_fd",
                        })
                time.sleep(0.5)
            except Exception as e:
                continue

    except Exception as e:
        print(f"  FD Error: {e}")

    print(f"  ✅ {len(props)} FanDuel props")
    return props


# ── BETMGM SCRAPER ───────────────────────────────────────────
def scrape_betmgm(sport="NBA"):
    """
    BetMGM uses CDS API with access ID.
    """
    print(f"\nScraping BetMGM {sport}...")
    props = []

    sport_id_map = {
        "NBA":  23,
        "MLB":  5,
        "NHL":  19,
        "WNBA": 23,
    }
    sport_id = sport_id_map.get(sport)
    if not sport_id:
        return props

    headers = {
        **HEADERS,
        "Referer": "https://sports.betmgm.com/",
        "x-bwin-accessid": "NDBlOWQ5YjgtMjk3ZS00MTI0LTg3YmMtZDA3ZGVlMWM4MjYw",
    }

    url = (
        f"https://cds-api.betmgm.com/bettingoffer/fixtures"
        f"?x-bwin-accessid=NDBlOWQ5YjgtMjk3ZS00MTI0LTg3YmMtZDA3ZGVlMWM4MjYw"
        f"&lang=en-us&country=US&userCountry=US&subdivision=US-NJ"
        f"&offer-category=player-props&sportId={sport_id}"
        f"&fixtureTypes=Standard&state=Latest&skip=0&take=100&sortBy=StartDate"
    )

    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"  MGM Status: {r.status_code}")
        if r.status_code != 200:
            return props

        data     = r.json()
        fixtures = data.get("fixtures", [])
        today    = date.today().isoformat()

        for fix in fixtures:
            if fix.get("startDate","")[:10] != today:
                continue
            for game in fix.get("games", []):
                market_name = game.get("name", {}).get("value","")
                for result in game.get("results", []):
                    player  = result.get("name",{}).get("value","")
                    odds_d  = result.get("odds", 0)
                    line    = result.get("attr")
                    side    = "OVER" if "over" in player.lower() or "over" in market_name.lower() else "UNDER"

                    if not player or not line:
                        continue

                    try:
                        american = decimal_to_american(odds_d)
                    except:
                        american = "—"

                    props.append({
                        "Player":   player.replace(" Over","").replace(" Under","").strip(),
                        "Prop":     market_name,
                        "Line":     float(str(line).replace("+","")),
                        "Side":     side,
                        "OverOdds": american if side == "OVER" else "—",
                        "Book":     "BetMGM",
                        "Sport":    sport,
                        "source":   "local_mgm",
                    })

    except Exception as e:
        print(f"  MGM Error: {e}")

    print(f"  ✅ {len(props)} BetMGM props")
    return props


# ── GIST PUSH ────────────────────────────────────────────────
def push_to_gist(all_props, sport):
    """Push scraped props to GitHub Gist for BetCouncil to read."""
    if not GITHUB_TOKEN or not GIST_ID:
        print("❌ No GitHub token/Gist configured")
        return False

    payload = {
        "sport":      sport,
        "timestamp":  datetime.now().isoformat(),
        "date":       date.today().isoformat(),
        "prop_count": len(all_props),
        "props":      all_props,
        "books":      list({p["Book"] for p in all_props}),
    }

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Update the Gist file
    r = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers=headers,
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2)}}},
        timeout=10
    )

    if r.status_code == 200:
        print(f"\n✅ Pushed {len(all_props)} props to Gist ({sport})")
        print(f"   Books: {payload['books']}")
        return True
    else:
        print(f"\n❌ Gist push failed: {r.status_code} {r.text[:100]}")
        return False


# ── MAIN ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="BetCouncil Local Book Scraper")
    parser.add_argument("--sport",  default="NBA", choices=["NBA","MLB","NHL","WNBA","NFL"])
    parser.add_argument("--all",    action="store_true", help="Scrape all sports")
    parser.add_argument("--dk",     action="store_true", help="DraftKings only")
    parser.add_argument("--fd",     action="store_true", help="FanDuel only")
    parser.add_argument("--mgm",    action="store_true", help="BetMGM only")
    parser.add_argument("--no-push",action="store_true", help="Don't push to Gist (test mode)")
    args = parser.parse_args()

    sports = ["NBA","MLB","NHL","WNBA"] if args.all else [args.sport]

    for sport in sports:
        print(f"\n{'='*50}")
        print(f"Sport: {sport} | {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*50}")

        all_props = []

        if args.fd:
            all_props += scrape_fanduel(sport)
        elif args.dk:
            all_props += scrape_draftkings(sport)
        elif args.mgm:
            all_props += scrape_betmgm(sport)
        else:
            # Scrape all three
            all_props += scrape_draftkings(sport)
            time.sleep(1)
            all_props += scrape_fanduel(sport)
            time.sleep(1)
            all_props += scrape_betmgm(sport)

        print(f"\nTotal: {len(all_props)} props from {len({p['Book'] for p in all_props})} books")

        if not args.no_push and all_props:
            push_to_gist(all_props, sport)
        elif args.no_push:
            print("\nTest mode — not pushing to Gist")
            # Show sample
            for p in all_props[:5]:
                print(f"  {p['Book']:12} {p['Player']:25} {p['Prop']:20} {p['Line']}")

if __name__ == "__main__":
    main()
