# vsin_picks_and_ratings.py
# Parsers for:
#   1. Makinen Power Ratings  — data.vsin.com/mlb/power-ratings/
#   2. VSiN Pro Picks         — data.vsin.com/propicks/active/
#                              data.vsin.com/propicks/eventdate/

import json
import re
import time
from datetime import datetime, timezone

import requests

try:
    import cloudscraper
except Exception:
    cloudscraper = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://data.vsin.com/",
}

POWER_RATINGS_URLS = {
    "MLB": "https://data.vsin.com/mlb/power-ratings/",
    "NBA": "https://data.vsin.com/nba/power-ratings/",
    "NFL": "https://data.vsin.com/nfl/power-ratings/",
}

PROPICKS_URLS = {
    "active":  "https://data.vsin.com/propicks/active/",
    "today":   "https://data.vsin.com/propicks/eventdate/",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _to_float(x):
    try:
        s = str(x).strip().replace("+", "").replace("\u2212", "-")
        return float(s) if s not in {"", "-", "N/A"} else None
    except Exception:
        return None

def _to_int(x):
    try:
        s = str(x).strip().replace("+", "").replace("\u2212", "-").replace(",", "")
        return int(float(s)) if s not in {"", "-", "N/A"} else None
    except Exception:
        return None

_TEAM_RE = re.compile(r"/(?:mlb|nfl|nba|nhl)/teams/", re.I)

def _make_session():
    if cloudscraper is not None:
        s = cloudscraper.create_scraper()
    else:
        s = requests.Session()
    s.headers.update(HEADERS)
    return s

def _fetch_playwright(url):
    if sync_playwright is None:
        raise RuntimeError("playwright not installed")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(user_agent=HEADERS["User-Agent"], locale="en-US")
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(8)
        html = page.content()
        ctx.close()
        browser.close()
        return html

def _fetch_html(url):
    session = _make_session()
    try:
        r = session.get(url, timeout=30)
        if r.status_code == 403:
            return _fetch_playwright(url)
        r.raise_for_status()
        return r.text
    except Exception:
        return _fetch_playwright(url)

# ---------------------------------------------------------------------------
# 1. Makinen Power Ratings
#
# Table columns (from live HTML):
# Team | League | PR | Rank | ER | Rank | SPPR | Rank | BPPR | Rank
# idx:   0        1     2     3    4     5      6      7      8     9
#
# PR   = Power Rating (overall)
# ER   = Effective Runs Rating
# SPPR = Starting Pitcher Power Rating
# BPPR = Bullpen Power Rating
# All have a Rank column immediately after
# ---------------------------------------------------------------------------

def parse_power_ratings(html: str, sport: str = "MLB") -> list:
    """
    Returns list of dicts, one per team, sorted by PR rank:
    {
        team, sport, league,
        power_rating, pr_rank,
        eff_runs, er_rank,
        starter_rating, sp_rank,
        bullpen_rating, bp_rank,
        composite_rank,  # average of all 4 ranks — lower = better overall
        source
    }
    """
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return []

    teams = []
    table = tables[0]

    for tr in table.find_all("tr"):
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if not cells or len(cells) < 8:
            continue

        links = tr.find_all("a", href=_TEAM_RE)
        if not links:
            continue

        team_name = _clean(links[0].get_text())

        # Column map:
        # 0=team 1=league 2=PR 3=PR_rank 4=ER 5=ER_rank 6=SPPR 7=SPPR_rank 8=BPPR 9=BPPR_rank
        pr      = _to_int(cells[2]   if len(cells) > 2 else None)
        pr_rank = _to_int(cells[3]   if len(cells) > 3 else None)
        er      = _to_float(cells[4] if len(cells) > 4 else None)
        er_rank = _to_int(cells[5]   if len(cells) > 5 else None)
        sp      = _to_float(cells[6] if len(cells) > 6 else None)
        sp_rank = _to_int(cells[7]   if len(cells) > 7 else None)
        bp      = _to_float(cells[8] if len(cells) > 8 else None)
        bp_rank = _to_int(cells[9]   if len(cells) > 9 else None)

        # Composite rank = average of all 4 ranks (lower = better)
        ranks = [r for r in [pr_rank, er_rank, sp_rank, bp_rank] if r is not None]
        composite = round(sum(ranks) / len(ranks), 1) if ranks else None

        teams.append({
            "team":           team_name,
            "sport":          sport,
            "league":         _clean(cells[1] if len(cells) > 1 else ""),
            "power_rating":   pr,
            "pr_rank":        pr_rank,
            "eff_runs":       er,
            "er_rank":        er_rank,
            "starter_rating": sp,
            "sp_rank":        sp_rank,
            "bullpen_rating": bp,
            "bp_rank":        bp_rank,
            "composite_rank": composite,
            "source":         "VSiN_PowerRatings",
        })

    # Sort by composite rank ascending (best teams first)
    teams.sort(key=lambda x: x["composite_rank"] if x["composite_rank"] else 999)
    return teams


# ---------------------------------------------------------------------------
# 2. VSiN Pro Picks
#
# Row structure (from live HTML) — each pick = 2 table rows:
#   Row A: sport_tag | expert_name - source - datetime | "Player" tag | book tag
#   Row B: result_tag | date_link - pick_description_with_link
#
# Pick description examples:
#   "Run Line - Phillies (-1) (-122) vs Mets [ 2 units ]"
#   "Max Muncy (Dodgers) OVER 1.5 [ Total Bases ] (+125)"
#   "Gerrit Cole (Yankees) OVER 5.5 [ Strikeouts ] (-114) [ 1.5 units ]"
#   "Red Sox at Mariners - UNDER (7) (-146)"
#
# Result tag examples: "6 - 2 WIN", "19 LOSS", "4 WIN", "-" (pending)
# ---------------------------------------------------------------------------

_RESULT_RE   = re.compile(r"(\d+)\s*-\s*(\d+)\s*(WIN|LOSS|PUSH)|(\d+)\s+(WIN|LOSS|PUSH)", re.I)
_ODDS_RE     = re.compile(r"\(([+-]\d+)\)")
_UNITS_RE    = re.compile(r"\[\s*([\d.]+)\s*units?\s*\]", re.I)
_LINE_RE     = re.compile(r"\(\s*([-+]?\d+(?:\.\d+)?)\s*\)")
_OVER_RE     = re.compile(r"(OVER|UNDER)\s+([\d.]+)", re.I)
_SPORT_RE    = re.compile(r"/propicks/sport/\?sportid=(\w+)", re.I)
_DATE_RE     = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME_RE     = re.compile(r"(\d+:\d+\s*[AP]M\s*ET)", re.I)
_EXPERT_RE   = re.compile(r"/propicks/vsinexpert/\?.*?vsinexpertid=(\d+)", re.I)

def _parse_result(text: str) -> tuple:
    """Returns (result, record_w, record_l) or (None, None, None)"""
    m = _RESULT_RE.search(text)
    if not m:
        return None, None, None
    if m.group(1):  # "W-L WIN/LOSS" format
        return m.group(3).upper(), int(m.group(1)), int(m.group(2))
    else:           # "N WIN/LOSS" format
        return m.group(5).upper(), None, None

def _parse_pick_text(text: str) -> dict:
    """Extract structured fields from pick description text."""
    pick = {
        "pick_text":    _clean(text),
        "player":       None,
        "team":         None,
        "bet_type":     None,   # "ML", "spread", "total", "prop"
        "direction":    None,   # "over"/"under"/"home"/"away"
        "line":         None,
        "odds":         None,
        "units":        None,
        "prop_stat":    None,
    }

    # Units
    um = _UNITS_RE.search(text)
    if um:
        pick["units"] = float(um.group(1))

    # Odds — last parenthetical number that looks like odds (+/-3 digits)
    odds_matches = _ODDS_RE.findall(text)
    if odds_matches:
        pick["odds"] = _to_int(odds_matches[-1])

    # Over/Under props
    oum = _OVER_RE.search(text)
    if oum:
        pick["direction"] = oum.group(1).lower()
        pick["line"] = float(oum.group(2))
        pick["bet_type"] = "total" if "UNDER" in text.upper() or "OVER" in text.upper() else "prop"

    # Prop stat in brackets [ Total Bases ] [ Strikeouts ] etc
    stat_m = re.search(r"\[\s*([A-Za-z+/ ]+?)\s*\]", text)
    if stat_m:
        stat = _clean(stat_m.group(1))
        if not re.match(r"[\d.]+\s*units?", stat, re.I):
            pick["prop_stat"] = stat
            pick["bet_type"] = "prop"

    # Player prop: "Name (Team) OVER/UNDER"
    player_m = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z'-]+)+)\s+\(([^)]+)\)", text)
    if player_m:
        pick["player"] = _clean(player_m.group(1))
        pick["team"]   = _clean(player_m.group(2))
        if not pick["bet_type"]:
            pick["bet_type"] = "prop"

    # Run Line / Spread
    if "run line" in text.lower() or "rl" in text.lower()[:10]:
        pick["bet_type"] = "spread"
    elif "ml" in text.lower()[:5] or re.search(r"\bML\b", text):
        pick["bet_type"] = "ML"

    # Game total: "UNDER (7)" or "OVER 8.5"
    if re.search(r"(OVER|UNDER)\s*\(?\d+(?:\.\d+)?\)?", text, re.I) and not pick["player"]:
        pick["bet_type"] = "total"

    return pick


def parse_propicks(html: str, sport_filter: str = None) -> list:
    """
    Returns list of pick dicts:
    {
        sport, expert_name, expert_id, source_show,
        pick_date, game_time, game_id,
        result, record_w, record_l,
        is_player_prop, is_pending,
        book,
        pick_text, player, team, bet_type,
        direction, line, odds, units, prop_stat,
        scraped_at, source
    }
    """
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    picks = []

    for table in tables:
        rows = table.find_all("tr")
        i = 0
        while i < len(rows) - 1:
            row_a = rows[i]
            row_b = rows[i + 1]

            cells_a = [_clean(td.get_text(" ", strip=True)) for td in row_a.find_all(["td", "th"])]
            cells_b = [_clean(td.get_text(" ", strip=True)) for td in row_b.find_all(["td", "th"])]

            if not cells_a or not cells_b:
                i += 1
                continue

            # Row A should have a sport link and expert link
            sport_links  = row_a.find_all("a", href=_SPORT_RE)
            expert_links = row_a.find_all("a", href=_EXPERT_RE)

            if not sport_links or not expert_links:
                i += 1
                continue

            # Sport
            sport_href = sport_links[0].get("href", "")
            sm = _SPORT_RE.search(sport_href)
            sport = sm.group(1).upper() if sm else "UNKNOWN"

            # Filter by sport if requested
            if sport_filter and sport != sport_filter.upper():
                i += 2
                continue

            # Expert
            expert_href = expert_links[0].get("href", "")
            em = _EXPERT_RE.search(expert_href)
            expert_id   = em.group(1) if em else None
            expert_text = _clean(expert_links[0].get_text())

            # Parse "Expert Name - Show Name - YYYY-MM-DD @ HH:MM TZ" from cells_a[1]
            expert_cell = cells_a[1] if len(cells_a) > 1 else ""
            expert_parts = expert_cell.split(" - ")
            expert_name = _clean(expert_parts[0]) if expert_parts else expert_text
            source_show = _clean(expert_parts[1]) if len(expert_parts) > 1 else None
            posted_date = None
            dm = _DATE_RE.search(expert_cell)
            if dm:
                posted_date = dm.group(0)

            # Is player prop / book tags from row A
            is_player = "Player" in " ".join(cells_a)
            book = None
            for cell in cells_a:
                if cell.upper() in {"DK", "FD", "MGM", "BET365", "CAESARS", "FANATICS", "ESPN"}:
                    book = cell.upper()

            # Row B: result tag | date link | pick description
            result_cell = cells_b[0] if cells_b else ""
            result, rec_w, rec_l = _parse_result(result_cell)
            is_pending = result is None and result_cell in {"", "-"}

            # Pick description — last cell of row B usually has the link + text
            pick_cell = cells_b[-1] if cells_b else ""

            # Game time
            game_time = None
            tm = _TIME_RE.search(pick_cell)
            if tm:
                game_time = tm.group(1)

            # Game ID from link
            game_id = None
            game_links = row_b.find_all("a", href=re.compile(r"/propicks/game/\?gameid="))
            if game_links:
                ghref = game_links[0].get("href", "")
                gm = re.search(r"gameid=([^&]+)", ghref)
                if gm:
                    game_id = gm.group(1)

            # Pick date from row B date link
            pick_date = None
            date_links = row_b.find_all("a", href=re.compile(r"/propicks/eventdate/\?eventdate="))
            if date_links:
                dhref = date_links[0].get("href", "")
                ddm = re.search(r"eventdate=(\d{4}-\d{2}-\d{2})", dhref)
                if ddm:
                    pick_date = ddm.group(1)

            parsed = _parse_pick_text(pick_cell)

            picks.append({
                "sport":         sport,
                "expert_name":   expert_name,
                "expert_id":     expert_id,
                "source_show":   source_show,
                "posted_date":   posted_date,
                "pick_date":     pick_date,
                "game_time":     game_time,
                "game_id":       game_id,
                "result":        result,
                "record_w":      rec_w,
                "record_l":      rec_l,
                "is_player_prop": is_player,
                "is_pending":    is_pending,
                "book":          book,
                **parsed,
                "scraped_at":    _now_iso(),
                "source":        "VSiN_ProPicks",
            })

            i += 2  # each pick = 2 rows

    return picks


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

class VSiNPicksAndRatings:

    def scrape_power_ratings(self, sport: str = "MLB") -> list:
        sport = sport.upper()
        url = POWER_RATINGS_URLS.get(sport)
        if not url:
            return []
        try:
            html = _fetch_html(url)
            return parse_power_ratings(html, sport)
        except Exception as e:
            print(f"[VSiN PowerRatings] error: {e}")
            return []

    def scrape_picks(self, mode: str = "today", sport_filter: str = None) -> list:
        url = PROPICKS_URLS.get(mode, PROPICKS_URLS["today"])
        try:
            html = _fetch_html(url)
            return parse_propicks(html, sport_filter)
        except Exception as e:
            print(f"[VSiN ProPicks] error: {e}")
            return []


# ---------------------------------------------------------------------------
# BetCouncil signal helpers
# ---------------------------------------------------------------------------

def power_ratings_lookup(ratings: list) -> dict:
    """
    Build a fast lookup dict: team_name -> rating dict.
    Use for quick access during game scoring.
    """
    return {r["team"]: r for r in ratings}


def picks_consensus(picks: list, sport: str = "MLB") -> dict:
    """
    Summarize today's VSiN pro picks for a sport into a consensus signal.
    Returns per-game pick counts and expert agreement.
    """
    sport_picks = [p for p in picks if p["sport"] == sport.upper() and p["is_pending"]]
    game_map = {}

    for p in sport_picks:
        gid = p.get("game_id") or p.get("pick_text", "")[:40]
        if gid not in game_map:
            game_map[gid] = {
                "game_id":    gid,
                "game_time":  p.get("game_time"),
                "pick_count": 0,
                "experts":    [],
                "directions": [],
                "avg_odds":   [],
                "total_units": 0.0,
            }
        g = game_map[gid]
        g["pick_count"] += 1
        g["experts"].append(p.get("expert_name"))
        if p.get("direction"):
            g["directions"].append(p["direction"])
        if p.get("odds"):
            g["avg_odds"].append(p["odds"])
        g["total_units"] += p.get("units") or 1.0

    # Compute consensus direction per game
    for gid, g in game_map.items():
        dirs = g["directions"]
        if dirs:
            from collections import Counter
            top = Counter(dirs).most_common(1)[0]
            g["consensus_direction"] = top[0]
            g["consensus_pct"] = round(top[1] / len(dirs) * 100, 1)
        else:
            g["consensus_direction"] = None
            g["consensus_pct"] = None
        g["avg_odds"] = round(sum(g["avg_odds"]) / len(g["avg_odds"])) if g["avg_odds"] else None

    return game_map


def expert_record_filter(picks: list, min_win_pct: float = 0.55) -> list:
    """
    Filter picks to only those from experts with a tracked winning record
    on this page (record_w / (record_w + record_l) >= min_win_pct).
    Only applies to picks that have a record attached.
    """
    filtered = []
    for p in picks:
        w, l = p.get("record_w"), p.get("record_l")
        if w is not None and l is not None:
            total = w + l
            if total > 0 and (w / total) >= min_win_pct:
                filtered.append(p)
        else:
            # No record shown — include by default (pending or no history)
            filtered.append(p)
    return filtered


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scraper = VSiNPicksAndRatings()

    print("=== Makinen Power Ratings (MLB) ===")
    ratings = scraper.scrape_power_ratings("MLB")
    print(f"Teams parsed: {len(ratings)}")
    if ratings:
        print("Top 5 by composite rank:")
        for r in ratings[:5]:
            print(f"  #{r['composite_rank']} {r['team']} — PR:{r['power_rating']} ER:{r['eff_runs']} SP:{r['starter_rating']} BP:{r['bullpen_rating']}")

    print("\n=== VSiN Pro Picks (today, MLB only) ===")
    picks = scraper.scrape_picks(mode="today", sport_filter="MLB")
    print(f"Picks parsed: {len(picks)}")
    if picks:
        print(json.dumps(picks[0], indent=2))

    print("\n=== Consensus by game ===")
    consensus = picks_consensus(picks, "MLB")
    for gid, g in consensus.items():
        print(f"  {g['game_time']} | {g['pick_count']} picks | {g['consensus_direction']} {g['consensus_pct']}% | {g['total_units']} units")
