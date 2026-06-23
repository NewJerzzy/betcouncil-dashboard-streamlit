"""
betonline_props_scraper.py
==========================
BetOnline player props scraper.

Uses Playwright to:
1. Load BetOnline MLB page (gets session cookies + CF clearance)
2. Intercept the get-contests-by-contest-type2 response (player props)
3. Intercept get-event responses (game info + additional markets)
4. Parse and return props in BetCouncil format

Key endpoints discovered:
  POST api-offering.betonline.ag/api/offering/Sports/offering-by-league
       → game lines (spread, ML, total)
  POST api-offering.betonline.ag/api/offering/Sports/get-contests-by-contest-type2
       → player props ("Gunnar Henderson 2+ Hits" etc)
  POST api-offering.betonline.ag/api/offering/Sports/get-contests
       → featured SGP parlays
  POST api-offering.betonline.ag/api/offering/sports/get-event
       → single game detail + pitcher info

All endpoints require browser session (Cloudflare). No plain requests.

Usage:
    python betonline_props_scraper.py --sport MLB --out bol_props.json
    python betonline_props_scraper.py --sport MLB --max-games 5

Integration:
    from betonline_props_scraper import scrape_betonline_all
    props, lines = scrape_betonline_all("MLB")
"""

import asyncio
import json
import re
import sys
import time
import argparse
from datetime import datetime

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# ── Sport/league mappings ─────────────────────────────────────────────────────
SPORT_CONFIG = {
    "MLB": {
        "sport":  "baseball",
        "league": "mlb",
        "url":    "https://www.betonline.ag/sportsbook/baseball/mlb",
        "leagues": ["mlb", "adj-run-line", "alt-run-line", "r+h+e", "mlb-series"],
    },
    "NBA": {
        "sport":  "basketball",
        "league": "nba",
        "url":    "https://www.betonline.ag/sportsbook/basketball/nba",
        "leagues": ["nba", "nba-props"],
    },
    "NFL": {
        "sport":  "football",
        "league": "nfl",
        "url":    "https://www.betonline.ag/sportsbook/football/nfl",
        "leagues": ["nfl", "nfl-props"],
    },
    "NHL": {
        "sport":  "hockey",
        "league": "nhl",
        "url":    "https://www.betonline.ag/sportsbook/hockey/nhl",
        "leagues": ["nhl"],
    },
}

# Props we care about per sport
PROP_LEAGUES = {
    "MLB": ["mlb-player-props", "mlb-batter-props", "mlb-pitcher-props"],
}


# ── Parser: game lines from offering-by-league ────────────────────────────────

def parse_game_lines(data: dict, sport: str) -> list:
    """Extract game lines from offering-by-league response."""
    lines = []
    go = data.get("GameOffering", {})
    games_desc = go.get("GamesDescription", []) or []

    for gd in games_desc:
        game = gd.get("Game", {})
        if not game:
            continue

        game_id   = game.get("GameId", "")
        away_team = game.get("AwayTeam", "")
        home_team = game.get("HomeTeam", "")
        away_pitcher = game.get("AwayPitcher", "")
        home_pitcher = game.get("HomePitcher", "")
        game_time = game.get("WagerCutOff", "")
        sc_fixture = game.get("SportCastFixtureId", "")

        def get_ml(line_obj):
            if not isinstance(line_obj, dict):
                return None
            ml = line_obj.get("MoneyLine", {})
            return ml.get("Line") if isinstance(ml, dict) else None

        def get_spread(line_obj):
            if not isinstance(line_obj, dict):
                return None
            sl = line_obj.get("SpreadLine", {})
            if isinstance(sl, dict):
                return sl.get("Point"), sl.get("Line")
            return None, None

        def get_total(line_obj, game_obj=None):
            if not isinstance(line_obj, dict):
                return None, None, None
            tl = line_obj.get("TotalLine") or {}
            # BetOnline sometimes puts TotalLine at game level, not under HomeLine/AwayLine
            if not tl and isinstance(game_obj, dict):
                tl = game_obj.get("TotalLine") or {}
            if isinstance(tl, dict) and tl:
                pt = tl.get("Point")
                ov = tl.get("Over", {}).get("Line") if isinstance(tl.get("Over"), dict) else None
                un = tl.get("Under", {}).get("Line") if isinstance(tl.get("Under"), dict) else None
                return pt, ov, un
            return None, None, None

        away_line = game.get("AwayLine", {})
        home_line = game.get("HomeLine", {})

        away_ml = get_ml(away_line)
        home_ml = get_ml(home_line)
        away_spr, away_spr_odds = get_spread(away_line)
        home_spr, home_spr_odds = get_spread(home_line)
        total_pt, total_over, total_under = get_total(home_line, game)

        # Team totals
        away_tt = away_line.get("TeamTotalLine", {}) if isinstance(away_line, dict) else {}
        home_tt = home_line.get("TeamTotalLine", {}) if isinstance(home_line, dict) else {}

        lines.append({
            "GameId":           game_id,
            "SportCastId":      sc_fixture,
            "Sport":            sport,
            "AwayTeam":         away_team,
            "HomeTeam":         home_team,
            "AwayPitcher":      away_pitcher,
            "HomePitcher":      home_pitcher,
            "GameTime":         game_time,
            "AwayML":           away_ml,
            "HomeML":           home_ml,
            "AwaySpr":          away_spr,
            "HomeSpr":          home_spr,
            "AwaySprOdds":      away_spr_odds,
            "HomeSprOdds":      home_spr_odds,
            "Total":            total_pt,
            "OverOdds":         total_over,
            "UnderOdds":        total_under,
            "AwayTeamTotal":    away_tt.get("Point") if isinstance(away_tt, dict) else None,
            "HomeTeamTotal":    home_tt.get("Point") if isinstance(home_tt, dict) else None,
            "AdditionalMarkets": game.get("AdditionalMarketCount", 0),
            "Book":             "BetOnline",
            "source":           "BOL_lines",
        })

    return lines


# ── Parser: player props from get-contests-by-contest-type2 ──────────────────

def _parse_name_prop(name: str) -> tuple:
    """
    Parse prop name like 'Gunnar Henderson 2+ Hits' into (player, prop_type, line, direction).
    Returns (player, prop, line, direction)
    """
    # Patterns: "Name N+ Stat", "Name Over/Under N Stat"
    player = prop = direction = ""
    line = None

    # "Name N+ Stat" pattern
    m = re.match(r'^(.+?)\s+(\d+(?:\.\d+)?)\+\s+(.+)$', name)
    if m:
        player    = m.group(1).strip()
        line      = float(m.group(2))
        prop      = m.group(3).strip()
        direction = "over"
        return player, prop, line, direction

    # "Name Over/Under N Stat" pattern
    m = re.match(r'^(.+?)\s+(Over|Under)\s+(\d+(?:\.\d+)?)\s+(.+)$', name, re.I)
    if m:
        player    = m.group(1).strip()
        direction = m.group(2).lower()
        line      = float(m.group(3))
        prop      = m.group(4).strip()
        return player, prop, line, direction

    # "Name to Stat" pattern (anytime scorer, first goal, etc.)
    m = re.match(r'^(.+?)\s+to\s+(.+)$', name, re.I)
    if m:
        player = m.group(1).strip()
        prop   = "to " + m.group(2).strip()
        return player, prop, None, "yes"

    # Fallback: whole name is the prop
    return "", name, None, ""


def parse_player_props(data: dict, sport: str) -> list:
    """Extract player props from get-contests-by-contest-type2 or get-contests."""
    props = []
    co = data.get("ContestOfferings", {})
    if not co:
        return props

    contest_type = co.get("ContestType", "")
    contest_id   = co.get("ContestTypeID", 0)
    date_groups  = co.get("DateGroup", []) or []

    for dg in date_groups:
        date_str = dg.get("Date", "")
        for desc_grp in (dg.get("DescriptionGroup") or []):
            game_desc = desc_grp.get("Description", "")  # "[mlb] Baltimore @ LA Angels"
            # Extract teams from description
            teams_match = re.search(r'\[(\w+)\]\s+(.+?)\s+@\s+(.+)', game_desc, re.I)
            sport_tag = teams_match.group(1).upper() if teams_match else sport
            away_team = teams_match.group(2).strip() if teams_match else ""
            home_team = teams_match.group(3).strip() if teams_match else ""

            for time_grp in (desc_grp.get("TimeGroup") or []):
                game_time = time_grp.get("Time", "")
                ce = time_grp.get("ContestExtended", {})
                for cgl in (ce.get("ContestGroupLine") or []):
                    for contestant in (cgl.get("Contestants") or []):
                        name     = contestant.get("Name", "")
                        rot      = contestant.get("RotationNumber", "")
                        cid      = contestant.get("ID", "")
                        line_obj = contestant.get("Line", {})
                        ml_obj   = line_obj.get("MoneyLine", {}) if isinstance(line_obj, dict) else {}
                        ml_line  = ml_obj.get("Line", 0) if isinstance(ml_obj, dict) else 0

                        if not name or ml_line == 0:
                            continue

                        player, prop_type, prop_line, direction = _parse_name_prop(name)

                        props.append({
                            "Player":      player or name,
                            "Prop":        prop_type or name,
                            "Line":        prop_line,
                            "Over":        ml_line if direction in ("over", "yes", "") else None,
                            "Under":       ml_line if direction == "under" else None,
                            "Direction":   direction,
                            "AwayTeam":    away_team,
                            "HomeTeam":    home_team,
                            "GameTime":    f"{date_str} {game_time}",
                            "RotationNum": rot,
                            "ContestID":   cid,
                            "ContestType": contest_type,
                            "ContestTypeID": contest_id,
                            "Sport":       sport_tag,
                            "Book":        "BetOnline",
                            "RawName":     name,
                            "source":      "BOL_props",
                        })

    return props


# ── Main Playwright scraper ───────────────────────────────────────────────────

async def _scrape_async(sport: str = "MLB", max_wait: int = 25) -> tuple:
    """
    Returns (props, lines) tuple.
    props = list of player prop dicts
    lines = list of game line dicts
    """
    if not HAS_PLAYWRIGHT:
        print("  [BOL] playwright not installed", file=sys.stderr)
        return [], []

    cfg = SPORT_CONFIG.get(sport.upper(), SPORT_CONFIG["MLB"])
    all_props = []
    all_lines = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = await context.new_page()

        async def on_response(response):
            url = response.url
            if "api-offering.betonline.ag" not in url:
                return
            try:
                body = await response.body()
                data = json.loads(body)
            except Exception:
                return

            if "offering-by-league" in url:
                lines = parse_game_lines(data, sport)
                if lines:
                    all_lines.extend(lines)
                    print(f"    Lines: +{len(lines)} games", file=sys.stderr)

            elif "get-contests-by-contest-type2" in url or "get-contests" in url:
                props = parse_player_props(data, sport)
                if props:
                    all_props.extend(props)
                    print(f"    Props: +{len(props)} from {url.split('/')[-1]}", file=sys.stderr)

        page.on("response", on_response)

        print(f"  [BOL] Loading {cfg['url']}", file=sys.stderr)
        await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # Dismiss popup
        for sel in [
            "button:has-text('Got It')",
            "button:has-text('GOT IT')",
            ".driver-popover-next-btn",
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

        # Wait for initial page load + line data
        print(f"  [BOL] Page loaded, waiting 8s for line data...", file=sys.stderr)
        await asyncio.sleep(8)

        # Build game URLs from lines we already scraped (GameId field)
        # Only use games with AdditionalMarkets > 0 (confirmed to have props)
        seen_ids = set()
        game_links = []
        for g in all_lines:
            gid = g.get("GameId")
            extra = g.get("AdditionalMarkets", 0)
            if gid and extra > 0 and gid not in seen_ids:
                seen_ids.add(gid)
                game_links.append(
                    f"https://www.betonline.ag/sportsbook/baseball/mlb/{gid}"
                )

        # Fallback: extract from page DOM if no lines with AdditionalMarkets
        if not game_links:
            raw = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(h => /\/sportsbook\/[a-z]+\/[a-z]+\/\d{8,}/.test(h))
                    .slice(0, 6)
            """)
            game_links = raw

        print(f"  [BOL] Found {len(game_links)} game links, navigating...", file=sys.stderr)

        for i, link in enumerate(game_links[:4]):
            try:
                print(f"  [BOL] Game {i+1}/{min(4, len(game_links))}: {link}", file=sys.stderr)
                await page.goto(link, wait_until="domcontentloaded", timeout=20000)
                # ── Click the player-props / "All Wagers" tab ────────────────
                # BetOnline is an Angular SPA — tabs are NOT always <button>.
                # They can be <li>, <a>, <div>, or even <span> elements.
                # Three escalating strategies so this survives DOM changes.

                await asyncio.sleep(2)  # Let Angular render tabs
                clicked = False

                # Strategy 1: Playwright get_by_text — type-agnostic, most reliable
                for label in ["All Wagers", "More Wagers", "Player Props",
                               "Additional Markets", "All Markets", "Props"]:
                    try:
                        loc = page.get_by_text(label, exact=True).first
                        if await loc.is_visible(timeout=2000):
                            await loc.click()
                            await asyncio.sleep(4)
                            clicked = True
                            print(f"    [BOL] Clicked '{label}' tab (get_by_text)", file=sys.stderr)
                            break
                    except Exception:
                        pass

                if not clicked:
                    # Strategy 2: CSS selectors covering div/li/a/button/span
                    # BetOnline game-page tabs commonly use non-button elements
                    more_wagers_selectors = [
                        "a:has-text('All Wagers')",
                        "li:has-text('All Wagers')",
                        "div:has-text('All Wagers')",
                        "a:has-text('More Wagers')",
                        "li:has-text('More Wagers')",
                        "div:has-text('More Wagers')",
                        "a:has-text('Player Props')",
                        "li:has-text('Player Props')",
                        "div:has-text('Player Props')",
                        "button:has-text('All Wagers')",
                        "button:has-text('Player Props')",
                        "span:has-text('All Wagers')",
                        "[class*='tab']:has-text('Wagers')",
                        "[class*='tab']:has-text('Props')",
                        "[class*='contest-type']",
                        "[class*='market-type']",
                        "[class*='wager-type']",
                    ]
                    for selector in more_wagers_selectors:
                        try:
                            button = await page.wait_for_selector(selector, timeout=2000)
                            if button and await button.is_visible():
                                await button.click()
                                await asyncio.sleep(4)
                                clicked = True
                                print(f"    [BOL] Clicked via CSS: {selector}", file=sys.stderr)
                                break
                        except Exception:
                            continue

                if not clicked:
                    # Strategy 3: JS evaluation — walk every leaf element, click first match
                    result = await page.evaluate("""
                        () => {
                            const targets = [
                                'All Wagers', 'More Wagers', 'Player Props',
                                'Additional Markets', 'All Markets', 'Props'
                            ];
                            const all = [...document.querySelectorAll('*')];
                            for (const txt of targets) {
                                const el = all.find(e =>
                                    e.children.length === 0 &&
                                    e.textContent.trim() === txt &&
                                    e.offsetParent !== null
                                );
                                if (el) { el.click(); return txt; }
                            }
                            return null;
                        }
                    """)
                    if result:
                        await asyncio.sleep(4)
                        clicked = True
                        print(f"    [BOL] JS-clicked '{result}'", file=sys.stderr)

                if not clicked:
                    print(f"    [BOL] No wagers tab found on {link} — waiting for any props", file=sys.stderr)

                await asyncio.sleep(4)  # Wait for API response regardless

                # Dismiss any popups
                for sel in ["button:has-text('Got It')", "button:has-text('GOT IT')",
                            ".driver-popover-next-btn"]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1000):
                            await btn.click()
                    except Exception:
                        pass
            except Exception as e:
                print(f"    Error: {e}", file=sys.stderr)

        print(f"  [BOL] Done. Props: {len(all_props)} Lines: {len(all_lines)}", file=sys.stderr)
        await browser.close()

    return all_props, all_lines


def scrape_betonline_all(sport: str = "MLB", max_wait: int = 25) -> tuple:
    """
    Synchronous wrapper. Returns (props, lines).
    Call from betcouncil_auto_scraper.py:
        from betonline_props_scraper import scrape_betonline_all
        props, lines = scrape_betonline_all("MLB")
    """
    return asyncio.run(_scrape_async(sport, max_wait))


def scrape_betonline_props(sport: str = "MLB") -> list:
    """Returns only props (for drop-in replacement in BetCouncil scraper pool)."""
    props, _ = scrape_betonline_all(sport)
    return props


def scrape_betonline_lines(sport: str = "MLB") -> list:
    """Returns only game lines."""
    _, lines = scrape_betonline_all(sport)
    return lines


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",    default="MLB")
    parser.add_argument("--wait",     type=int, default=25)
    parser.add_argument("--out",      help="Output JSON file")
    parser.add_argument("--props-only", action="store_true")
    parser.add_argument("--lines-only", action="store_true")
    args = parser.parse_args()

    print(f"\n[BOL Scraper] {args.sport} | {datetime.now().strftime('%H:%M:%S')}")
    props, lines = scrape_betonline_all(args.sport, args.wait)

    print(f"\n=== RESULTS ===")
    print(f"Props: {len(props)}")
    print(f"Lines: {len(lines)}")

    if props:
        print("\nSample props (first 10):")
        for p in props[:10]:
            player = p.get("Player", "?")
            prop   = p.get("Prop", "?")
            line   = p.get("Line", "?")
            over   = p.get("Over", "?")
            game   = f"{p.get('AwayTeam','')} @ {p.get('HomeTeam','')}"
            print(f"  {player:25} {prop:20} {line} | +{over} | {game}")

    if lines:
        print("\nSample lines (first 5):")
        for g in lines[:5]:
            print(f"  {g['AwayTeam']:25} @ {g['HomeTeam']:25} | ML: {g['AwayML']}/{g['HomeML']} | Total: {g['Total']}")

    output = {
        "sport":     args.sport,
        "timestamp": datetime.now().isoformat(),
        "props":     props if not args.lines_only else [],
        "lines":     lines if not args.props_only else [],
    }

    if args.out:
        with open(args.out, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nSaved to {args.out}")
    else:
        print(json.dumps(output, indent=2))
