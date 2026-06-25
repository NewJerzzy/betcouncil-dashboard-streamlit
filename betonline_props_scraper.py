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
import os
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
# PROP_LEAGUES: league-page slugs that fire get-contests-by-contest-type2 on load.
# The mlb-player-props / mlb-batter-props / mlb-pitcher-props slugs returned
# 404 — BOL does not expose those as standalone pages.  Left empty so Strategy
# A is a clean no-op until correct slugs are confirmed via bol_api_urls.json.
PROP_LEAGUES = {
    "MLB": [],               # BOL MLB player prop pages return 404 — slugs TBD
    "NBA": [],               # BOL NBA player prop pages — slugs TBD
    "NFL": [],  # Slugs TBD — UNVERIFIED (do not navigate until confirmed).
                # Plausible candidates: nfl-player-props, nfl-passing-props,
                # nfl-rushing-props, nfl-receiving-props.  BOL NFL prop pages
                # may 404 exactly like the MLB slugs did.  Verify via
                # bol_api_urls.json or a live nav test before populating.
    "NHL": [],
}

# ── NFL prop slug prober ───────────────────────────────────────────────────────
# PROP_LEAGUES["NFL"] is empty until slugs are confirmed live.  These are the
# plausible candidates based on BOL URL patterns.  _get_confirmed_prop_slugs()
# probes each one with a lightweight HEAD request and caches confirmed slugs for
# 24 h so the Playwright session only navigates to URLs that actually resolve.
_NFL_PROP_SLUG_CANDIDATES = [
    "nfl-player-props",
    "nfl-passing-props",
    "nfl-rushing-props",
    "nfl-receiving-props",
]

_BOL_SLUG_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".cache", "bol_confirmed_slugs.json"
)
_BOL_SLUG_CACHE_TTL_H = 24  # hours


def _probe_bol_slug(slug: str, sport_path: str) -> bool:
    """Return True if the BOL page for this slug responds with HTTP 200.

    Uses a plain GET (not Playwright) so this is fast and non-blocking.
    A 404 means the slug doesn't exist on BOL; anything else (200, 30x)
    is treated as present.
    """
    url = f"https://www.betonline.ag/sportsbook/{sport_path}/{slug}"
    try:
        import requests as _req
        resp = _req.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
            allow_redirects=True,
        )
        return resp.status_code != 404
    except Exception:
        return False


def _get_confirmed_prop_slugs(sport: str, cfg: dict) -> list:
    """Probe candidate slugs and return those that actually resolve on BOL.

    Results are cached to disk for _BOL_SLUG_CACHE_TTL_H hours so the
    prober only fires once per day rather than on every scrape run.
    """
    sport = sport.upper()
    # Fast path: PROP_LEAGUES already populated (manually confirmed slugs)
    if PROP_LEAGUES.get(sport):
        return PROP_LEAGUES[sport]

    candidates = _NFL_PROP_SLUG_CANDIDATES if sport == "NFL" else []
    if not candidates:
        return []

    # Check disk cache
    try:
        os.makedirs(os.path.dirname(_BOL_SLUG_CACHE_PATH), exist_ok=True)
        if os.path.exists(_BOL_SLUG_CACHE_PATH):
            age_h = (time.time() - os.path.getmtime(_BOL_SLUG_CACHE_PATH)) / 3600
            if age_h < _BOL_SLUG_CACHE_TTL_H:
                with open(_BOL_SLUG_CACHE_PATH) as _f:
                    cached = json.load(_f)
                if sport in cached:
                    confirmed = cached[sport]
                    print(
                        f"  [BOL] Slug cache hit: {confirmed} (age {age_h:.1f}h)",
                        file=sys.stderr,
                    )
                    return confirmed
    except Exception:
        pass

    sport_path = cfg.get("sport", sport.lower())
    print(
        f"  [BOL] Probing {len(candidates)} {sport} slug candidates...",
        file=sys.stderr,
    )
    confirmed = [s for s in candidates if _probe_bol_slug(s, sport_path)]
    print(f"  [BOL] Confirmed slugs: {confirmed}", file=sys.stderr)

    # Write cache
    try:
        existing = {}
        if os.path.exists(_BOL_SLUG_CACHE_PATH):
            with open(_BOL_SLUG_CACHE_PATH) as _f:
                existing = json.load(_f)
        existing[sport] = confirmed
        with open(_BOL_SLUG_CACHE_PATH, "w") as _f:
            json.dump(existing, _f)
    except Exception:
        pass

    return confirmed


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
    # ── Try top-level ContestOfferings first, then bare top level ─────────────
    co = data.get("ContestOfferings", {})
    if not co:
        # Some responses omit the wrapper — treat the root dict as ContestOfferings
        co = data if isinstance(data, dict) else {}
    if not co:
        return props

    contest_type = co.get("ContestType", "")
    contest_id   = co.get("ContestTypeID", 0)
    date_groups  = co.get("DateGroup", []) or []

    if not date_groups:
        # Alternate key spellings seen in the wild
        date_groups = (
            co.get("DateGroups") or
            co.get("dateGroup") or
            co.get("Games") or
            []
        )

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

    # ── Fallback 2: Contests → Contest → Contestants path ─────────────────────
    # Some get-contests responses use this flatter structure instead of the
    # DateGroup → DescriptionGroup → TimeGroup → ContestExtended → ... chain.
    # Guarded by `if not props` so the primary path always takes precedence.
    if not props:
        _contests_node = co.get("Contests") or {}
        if isinstance(_contests_node, dict):
            _contests_list = _contests_node.get("Contest") or []
        elif isinstance(_contests_node, list):
            _contests_list = _contests_node
        else:
            _contests_list = []
        for _contest in _contests_list:
            _c_date  = _contest.get("Date", "")
            _c_time  = _contest.get("Time", "")
            _c_desc  = _contest.get("Description", "") or _contest.get("Name", "")
            _c_type  = _contest.get("ContestType", contest_type)
            _c_tid   = _contest.get("ContestTypeID", contest_id)
            _teams_m = re.search(r'\[(\w+)\]\s+(.+?)\s+@\s+(.+)', _c_desc, re.I)
            _sport_tag2 = _teams_m.group(1).upper() if _teams_m else sport
            _away_team2 = _teams_m.group(2).strip() if _teams_m else ""
            _home_team2 = _teams_m.group(3).strip() if _teams_m else ""
            for contestant in (_contest.get("Contestants") or []):
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
                    "Player":        player or name,
                    "Prop":          prop_type or name,
                    "Line":          prop_line,
                    "Over":          ml_line if direction in ("over", "yes", "") else None,
                    "Under":         ml_line if direction == "under" else None,
                    "Direction":     direction,
                    "AwayTeam":      _away_team2,
                    "HomeTeam":      _home_team2,
                    "GameTime":      f"{_c_date} {_c_time}",
                    "RotationNum":   rot,
                    "ContestID":     cid,
                    "ContestType":   _c_type,
                    "ContestTypeID": _c_tid,
                    "Sport":         _sport_tag2,
                    "Book":          "BetOnline",
                    "RawName":       name,
                    "source":        "BOL_props",
                })

    # ── Fallback 3: alternate top-level shapes ─────────────────────────────────
    # Handles: {"data": [...]}, {"Offerings": [...]}, or a raw list at the root.
    if not props:
        _alt_lists = []
        if isinstance(data, list):
            _alt_lists.append(data)
        elif isinstance(data, dict):
            for _ak in ("data", "Offerings", "offerings", "Results", "results",
                        "Items", "items", "PropOfferings", "PlayerProps"):
                _av = data.get(_ak)
                if isinstance(_av, list) and _av:
                    _alt_lists.append(_av)
                    break
        for _alt_list in _alt_lists:
            for _item in _alt_list:
                if not isinstance(_item, dict):
                    continue
                _name = (_item.get("Name") or _item.get("name") or
                         _item.get("Description") or _item.get("description") or "")
                _ml   = (_item.get("MoneyLine") or _item.get("moneyLine") or
                         _item.get("Odds") or _item.get("odds") or 0)
                if isinstance(_ml, dict):
                    _ml = _ml.get("Line") or _ml.get("line") or 0
                if not _name or not _ml:
                    continue
                _pplayer, _pprop, _ppline, _pdir = _parse_name_prop(str(_name))
                props.append({
                    "Player":        _pplayer or str(_name),
                    "Prop":          _pprop or str(_name),
                    "Line":          _ppline,
                    "Over":          _ml if _pdir in ("over", "yes", "") else None,
                    "Under":         _ml if _pdir == "under" else None,
                    "Direction":     _pdir,
                    "AwayTeam":      _item.get("AwayTeam", ""),
                    "HomeTeam":      _item.get("HomeTeam", ""),
                    "GameTime":      _item.get("GameTime", ""),
                    "RotationNum":   _item.get("RotationNumber", ""),
                    "ContestID":     _item.get("ID", ""),
                    "ContestType":   "",
                    "ContestTypeID": 0,
                    "Sport":         sport,
                    "Book":          "BetOnline",
                    "RawName":       str(_name),
                    "source":        "BOL_props",
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

        # Accumulate ALL api-offering URLs + captured request details.
        _api_urls_seen = []
        _captured_headers = {}   # headers from offering-by-league, reused for direct calls
        _offering_body = {}      # parsed POST body of offering-by-league (league/sport etc.)

        async def on_request(request):
            """Capture request bodies and headers from BOL API calls."""
            url = request.url
            if "api-offering.betonline.ag" not in url:
                return
            try:
                raw_headers = request.headers
                post_data   = request.post_data or ""
                _api_urls_seen.append({
                    "direction": "request",
                    "url":       url,
                    "method":    request.method,
                    "body":      post_data[:500],   # first 500 chars
                    "headers":   {k: v for k, v in raw_headers.items()
                                  if k.lower() not in ("cookie",)},  # omit cookies
                })
                # Keep a copy of offering-by-league headers for direct API calls
                if "offering-by-league" in url and not _captured_headers:
                    _captured_headers.update(raw_headers)
                    print(f"    [BOL] Captured {len(raw_headers)} headers from offering-by-league", file=sys.stderr)
                    try:
                        _offering_body.update(json.loads(post_data) if post_data else {})
                    except Exception:
                        pass
            except Exception:
                pass

        async def on_response(response):
            url = response.url
            if "api-offering.betonline.ag" not in url:
                return
            try:
                body = await response.body()
                data = json.loads(body)
            except Exception:
                return
            # ── Record every BOL API response ────────────────────────────────
            _api_urls_seen.append({
                "direction": "response",
                "url":       url,
                "method":    response.request.method,
                "status":    response.status,
                "bytes":     len(body),
                "top_keys":  list(data.keys()) if isinstance(data, dict) else str(type(data)),
            })

            if "offering-by-league" in url:
                lines = parse_game_lines(data, sport)
                if lines:
                    all_lines.extend(lines)
                    print(f"    Lines: +{len(lines)} games", file=sys.stderr)

            elif any(k in url for k in ["get-contests", "get-event",
                                         "additional-market", "player-prop"]):
                # ── Save first contest-like response for diagnostics ─────────
                _raw_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "bol_contest_raw.json"
                )
                if not os.path.exists(_raw_path):
                    try:
                        import json as _json
                        with open(_raw_path, "w") as _rf:
                            _json.dump({"url": url, "data": data}, _rf, indent=2)
                        print(f"    [BOL] Raw contest dump → {_raw_path}", file=sys.stderr)
                    except Exception:
                        pass
                # ── Try to parse props ───────────────────────────────────────
                props = parse_player_props(data, sport)
                if props:
                    all_props.extend(props)
                    print(f"    Props: +{len(props)} from {url.split('/')[-1]}", file=sys.stderr)
                else:
                    top_keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
                    print(f"    [BOL] contest endpoint hit, parse empty — keys: {top_keys}", file=sys.stderr)

        page.on("request",  on_request)
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

        # ── Strategy A: Direct authenticated API fetch ──────────────────────
        # Use page.request.post() which inherits the browser's Cloudflare-
        # cleared cookies.  Try the known contest endpoint with several body
        # formats, iterating over every SportCastId captured from game lines.
        #
        # Strategy A: direct authenticated POST to the contest/props endpoints.
        # page.request.post() inherits the browser's Cloudflare cookies automatically;
        # we do NOT pass explicit headers= so the browser context handles auth.
        #
        # Two endpoint variants tried:
        #   URL1: get-contests-by-contest-type2  (per-game player props)
        #   URL2: get-contests                   (league-wide props, no fixture id needed)
        #
        # Body formats tried per-game (in order):
        #   F1: {sportcastFixtureId, contestTypeId: 5}   ← most likely correct
        #   F2: {SportcastFixtureId, contestTypeId: 5}   ← alternate casing
        #   F3: {sportcastFixtureId}                     ← no contestTypeId
        #   F4: {SportcastFixtureId}                     ← no contestTypeId, uppercase
        #   F5: {Id}                                     ← fallback
        #   F6: {sportcastId, contestTypeId: 5}
        #   F7: {fixtureId, contestTypeId: 1}
        #
        # League-level formats (not per-game) also tried if _offering_body available.
        _CONTEST_URL  = "https://api-offering.betonline.ag/api/offering/Sports/get-contests-by-contest-type2"
        _CONTEST_URL2 = "https://api-offering.betonline.ag/api/offering/Sports/get-contests"

        # Collect SportCastIds (non-null) from captured lines
        _sc_ids = list({
            g["SportCastId"] for g in all_lines
            if g.get("SportCastId") and g.get("AdditionalMarkets", 0) > 0
        })
        if not _sc_ids:
            _sc_ids = list({g["SportCastId"] for g in all_lines if g.get("SportCastId")})

        print(f"  [BOL] Strategy A — direct fetch for {len(_sc_ids)} SportCastIds", file=sys.stderr)

        # ── Helper: attempt one POST and parse props ─────────────────────────
        _raw_dump_written = False

        async def _try_post(endpoint_url, body_dict):
            """POST body_dict to endpoint_url; return (props_list, raw_data, status)."""
            nonlocal _raw_dump_written
            try:
                _resp = await page.request.post(
                    endpoint_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept":       "application/json, text/plain, */*",
                        "Referer":      "https://www.betonline.ag/",
                    },
                    data=json.dumps(body_dict),
                )
                _status = _resp.status
                _rbody  = await _resp.body()
                try:
                    _rdata = json.loads(_rbody)
                except Exception:
                    return [], None, _status
                _top = list(_rdata.keys()) if isinstance(_rdata, dict) else type(_rdata).__name__
                print(
                    f"    [BOL] POST {endpoint_url.split('/')[-1]} "
                    f"body={list(body_dict.keys())} → {_status} keys={_top}",
                    file=sys.stderr,
                )
                _api_urls_seen.append({
                    "direction": "direct_fetch",
                    "url":       endpoint_url,
                    "body_fmt":  list(body_dict.keys()),
                    "status":    _status,
                    "top_keys":  _top,
                })
                if _status != 200:
                    return [], None, _status
                # Always dump first 200 response for diagnostics
                if not _raw_dump_written:
                    _rp = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "bol_contest_raw.json",
                    )
                    try:
                        with open(_rp, "w") as _rf:
                            json.dump({"url": endpoint_url, "body": body_dict, "data": _rdata}, _rf, indent=2)
                        _raw_dump_written = True
                        print(f"    [BOL] Raw dump → {_rp}", file=sys.stderr)
                    except Exception:
                        pass
                _props = parse_player_props(_rdata, sport)
                if not _props:
                    # Log first 300 chars of response to help diagnose shape
                    _preview = json.dumps(_rdata)[:300] if isinstance(_rdata, dict) else str(_rdata)[:300]
                    print(f"    [BOL] parse empty — preview: {_preview}", file=sys.stderr)
                return _props, _rdata, _status
            except Exception as _fe:
                print(f"    [BOL] POST error ({list(body_dict.keys())}): {_fe}", file=sys.stderr)
                return [], None, 0

        # ── Per-game formats ─────────────────────────────────────────────────
        for _sc_id in _sc_ids[:4]:   # cap at 4 to avoid long runs
            if all_props:
                break
            _per_game_fmts = [
                {"sportcastFixtureId": _sc_id, "contestTypeId": 5},
                {"SportcastFixtureId": _sc_id, "contestTypeId": 5},
                {"sportcastFixtureId": _sc_id},
                {"SportcastFixtureId": _sc_id},
                {"Id": _sc_id},
                {"sportcastId": _sc_id, "contestTypeId": 5},
                {"fixtureId": _sc_id, "contestTypeId": 1},
            ]
            for _fmt in _per_game_fmts:
                _pp, _rd, _st = await _try_post(_CONTEST_URL, _fmt)
                if _pp:
                    all_props.extend(_pp)
                    print(f"    [BOL] ✓ {len(_pp)} props (sc={_sc_id}, fmt={list(_fmt.keys())})", file=sys.stderr)
                    break
                # If response had the right envelope but parse was empty, stop trying fmts
                if _rd and isinstance(_rd, dict) and (_rd.get("ContestOfferings") or _rd.get("Contests")):
                    break

        # ── League-level formats (no SportCastId) ────────────────────────────
        # Use LeagueId/SportId captured from the offering-by-league request body.
        if not all_props and _offering_body:
            _league_id = _offering_body.get("leagueId") or _offering_body.get("LeagueId")
            _sport_id  = _offering_body.get("sportId")  or _offering_body.get("SportId")
            print(f"  [BOL] Strategy A (league-level) leagueId={_league_id} sportId={_sport_id}", file=sys.stderr)
            _league_fmts = []
            if _league_id:
                _league_fmts += [
                    {"leagueId": _league_id, "contestTypeId": 5},
                    {"leagueId": _league_id, "sportId": _sport_id, "contestTypeId": 5},
                    {"leagueId": _league_id},
                ]
            if _sport_id:
                _league_fmts += [{"sportId": _sport_id, "contestTypeId": 5}]
            for _lfmt in _league_fmts:
                if all_props:
                    break
                for _url in [_CONTEST_URL, _CONTEST_URL2]:
                    _pp, _, _ = await _try_post(_url, _lfmt)
                    if _pp:
                        all_props.extend(_pp)
                        print(f"    [BOL] ✓ {len(_pp)} props via league-level ({list(_lfmt.keys())})", file=sys.stderr)
                        break

        # ── get-contests (league-wide, no fixture id) ────────────────────────
        if not all_props:
            _fallback_fmts = [
                {"contestTypeId": 5},
                {"contestTypeId": 1},
                {},
            ]
            for _ff in _fallback_fmts:
                if all_props:
                    break
                _pp, _, _ = await _try_post(_CONTEST_URL2, _ff)
                if _pp:
                    all_props.extend(_pp)
                    print(f"    [BOL] ✓ {len(_pp)} props via get-contests ({list(_ff.keys())})", file=sys.stderr)

        # Use confirmed slugs: manually set in PROP_LEAGUES, or probed live from candidates
        prop_league_slugs = _get_confirmed_prop_slugs(sport, cfg)
        if prop_league_slugs:
            print(f"  [BOL] Strategy A.2 — {len(prop_league_slugs)} confirmed props-league pages", file=sys.stderr)
            for _slug in prop_league_slugs:
                _prop_url = f"https://www.betonline.ag/sportsbook/{cfg['sport']}/{_slug}"
                print(f"  [BOL]   → {_prop_url}", file=sys.stderr)
                try:
                    await page.goto(_prop_url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(5)
                    for _sel in ["button:has-text('Got It')", "button:has-text('GOT IT')",
                                 ".driver-popover-next-btn"]:
                        try:
                            _btn = page.locator(_sel).first
                            if await _btn.is_visible(timeout=1000):
                                await _btn.click()
                        except Exception:
                            pass
                    await asyncio.sleep(4)
                except Exception as _e:
                    print(f"    [BOL] Props-league error: {_e}", file=sys.stderr)

        # ── Strategy B: Browser-native API capture via page.expect_response() ─
        # Only runs if Strategy A yielded nothing.
        #
        # B1: click "More Wagers"/"All Wagers" ON THE MAIN PAGE — no URL
        #     format guessing, just interact with elements already visible.
        # B2: extract ACTUAL <a> hrefs from the DOM (not constructed from
        #     GameId, which doesn't map to BOL's URL slugs), navigate those,
        #     and wait for the props API call to fire.
        #
        # Both paths use page.expect_response() so we deterministically
        # capture the API response rather than hoping on_response fires.
        if not all_props:
            print(f"  [BOL] Strategy B: browser-native capture...", file=sys.stderr)

            # Ensure we're on the main league page (Strategy A.2 may have navigated away)
            if cfg["url"] not in page.url:
                print(f"  [BOL] B: re-navigating to {cfg['url']}", file=sys.stderr)
                await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)
                for _sel in ["button:has-text('Got It')", "button:has-text('GOT IT')",
                             ".driver-popover-next-btn"]:
                    try:
                        _btn = page.locator(_sel).first
                        if await _btn.is_visible(timeout=1000):
                            await _btn.click()
                    except Exception:
                        pass
                await asyncio.sleep(3)

            def _is_props_response(r):
                u = r.url
                return ("api-offering.betonline.ag" in u and
                        any(k in u for k in ["get-contests", "get-event",
                                             "additional-market", "player-prop"]))

            async def _capture_and_parse(resp_awaitable):
                try:
                    _r = await resp_awaitable
                    _b = await _r.body()
                    _d = json.loads(_b)
                    _pp = parse_player_props(_d, sport)
                    _top = list(_d.keys()) if isinstance(_d, dict) else type(_d).__name__
                    print(f"    [BOL] captured {_r.url.split('/')[-1]} "
                          f"status={_r.status} keys={_top} props={len(_pp)}", file=sys.stderr)
                    # Dump first contest capture for diagnostics
                    _rp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bol_contest_raw.json")
                    if not os.path.exists(_rp):
                        try:
                            with open(_rp, "w") as _rf:
                                json.dump({"url": _r.url, "data": _d}, _rf, indent=2)
                            print(f"    [BOL] Raw dump → {_rp}", file=sys.stderr)
                        except Exception:
                            pass
                    return _pp
                except Exception as _ce:
                    print(f"    [BOL] capture error: {type(_ce).__name__}: {_ce}", file=sys.stderr)
                    return []

            # ── B1: click visible "More Wagers"/"All Wagers" on main page ────
            _b1_labels = ["More Wagers", "All Wagers", "Player Props",
                          "Props", "Additional Markets"]
            for _label in _b1_labels:
                if all_props:
                    break
                try:
                    _locs = page.get_by_text(_label, exact=False)
                    _n = await _locs.count()
                    if _n == 0:
                        continue
                    print(f"  [BOL] B1: {_n} '{_label}' elements on main page", file=sys.stderr)
                    for _li in range(min(_n, 4)):
                        try:
                            async with page.expect_response(_is_props_response, timeout=8000) as _ri:
                                await _locs.nth(_li).click()
                            _pp = await _capture_and_parse(_ri.value)
                            if _pp:
                                all_props.extend(_pp)
                                print(f"    [BOL] B1 '{_label}'[{_li}] → {len(_pp)} props ✓", file=sys.stderr)
                                break
                        except Exception as _be:
                            print(f"    [BOL] B1 '{_label}'[{_li}]: {type(_be).__name__}: {str(_be)[:80]}", file=sys.stderr)
                        if all_props:
                            break
                except Exception:
                    pass

            # ── B2: DOM-extracted actual game hrefs → navigate + capture ──────
            if not all_props:
                _actual_hrefs = await page.evaluate(r"""
                    () => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(h => h.includes('/sportsbook/') && !h.endsWith('/sportsbook/'))
                        .filter((v, i, a) => a.indexOf(v) === i)
                        .slice(0, 10)
                """)
                print(f"  [BOL] B2: {len(_actual_hrefs)} unique hrefs from DOM", file=sys.stderr)
                for _href in _actual_hrefs[:5]:
                    if all_props:
                        break
                    try:
                        print(f"  [BOL] B2 nav → {_href}", file=sys.stderr)
                        async with page.expect_response(_is_props_response, timeout=15000) as _ri:
                            await page.goto(_href, wait_until="domcontentloaded", timeout=20000)
                            await asyncio.sleep(3)
                            for _lab in ["All Wagers", "More Wagers", "Player Props", "Props"]:
                                try:
                                    _loc = page.get_by_text(_lab, exact=False).first
                                    if await _loc.is_visible(timeout=1500):
                                        await _loc.click()
                                        print(f"    [BOL] B2 clicked '{_lab}'", file=sys.stderr)
                                        break
                                except Exception:
                                    pass
                            await asyncio.sleep(3)
                        _pp = await _capture_and_parse(_ri.value)
                        if _pp:
                            all_props.extend(_pp)
                            print(f"    [BOL] B2 {_href} → {len(_pp)} props ✓", file=sys.stderr)
                    except Exception as _be:
                        print(f"    [BOL] B2 {_href}: {type(_be).__name__}: {str(_be)[:100]}", file=sys.stderr)

        else:
            print(f"  [BOL] Strategy A captured {len(all_props)} props — skipping Strategy B", file=sys.stderr)

        # ── Dump all captured API URLs for diagnostics ──────────────────────
        _urls_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "bol_api_urls.json"
        )
        try:
            import json as _json2
            with open(_urls_path, "w") as _uf:
                _json2.dump(_api_urls_seen, _uf, indent=2)
            print(f"  [BOL] API URL dump → {_urls_path} ({len(_api_urls_seen)} calls)", file=sys.stderr)
        except Exception as _ue:
            print(f"  [BOL] Could not write URL dump: {_ue}", file=sys.stderr)

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
