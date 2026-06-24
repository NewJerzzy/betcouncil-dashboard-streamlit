# vsin_scraper.py
import json
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
try:
    from team_canon import merge_by_canon, canon
    _USE_CANON = True
except ImportError:
    _USE_CANON = False

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

BASE_URLS = {
    "MLB": "https://data.vsin.com/vegas-odds-linetracker/?sportid=mlb",
    "NFL": "https://data.vsin.com/vegas-odds-linetracker/?sportid=nfl",
    "NBA": "https://data.vsin.com/vegas-odds-linetracker/?sportid=nba",
    "NHL": "https://data.vsin.com/vegas-odds-linetracker/?sportid=nhl",
}
SPLITS_URL = "https://data.vsin.com/betting-splits/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://data.vsin.com/",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _sim(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _clean(a).lower(), _clean(b).lower()).ratio()

def _to_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip().replace("\u2212", "-").replace("\u2014", "-").replace("+", "")
        s = s.replace("\u00bd", ".5").replace("½", ".5")
        if s in {"", "-", "N/A", "NA", "None", "PK"}:
            return None
        return float(s)
    except Exception:
        return None

def _to_int(x):
    try:
        if x is None:
            return None
        s = str(x).strip().replace("\u2212", "-").replace("\u2014", "-")
        s = s.replace(",", "").replace(" ", "")
        if s in {"", "-", "N/A", "NA", "None"}:
            return None
        # preserve sign for moneylines
        return int(float(s))
    except Exception:
        return None

def _pct(x):
    try:
        if x is None:
            return None
        s = str(x).replace("%", "").replace("\u25b2", "").replace("\u25bc", "").strip()
        if s in {"", "-", "N/A"}:
            return None
        return float(s)
    except Exception:
        return None

def _make_session():
    if cloudscraper is not None:
        s = cloudscraper.create_scraper()
    else:
        s = requests.Session()
    s.headers.update(HEADERS)
    return s

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _fetch_playwright(url):
    if sync_playwright is None:
        raise RuntimeError("playwright not installed")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="en-US")
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(10)
        html = page.content()
        context.close()
        browser.close()
        return html

def _fetch_html(url):
    session = _make_session()
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 403:
            return _fetch_playwright(url)
        r.raise_for_status()
        return r.text
    except PermissionError:
        return _fetch_playwright(url)
    except Exception:
        return _fetch_playwright(url)

# ---------------------------------------------------------------------------
# RLM detection
# ---------------------------------------------------------------------------

def detect_rlm(game: dict) -> dict:
    """
    Reverse Line Movement detection.
    Uses spread_bet_pct_home (ticket %) or ml_bet_pct_home as the public proxy.
    RLM fires when the line moves against where 55%+ of the public is leaning.
    """
    public_home = game.get("spread_bet_pct_home")
    if public_home is None:
        public_home = game.get("ml_bet_pct_home")
    if public_home is None:
        return {"rlm_detected": False, "rlm_direction": None,
                "rlm_strength": None, "public_pct_vs_line": 0.0}

    opening = game.get("opening_spread_home")
    current = game.get("current_spread_home")

    if opening is None or current is None:
        return {"rlm_detected": False, "rlm_direction": None,
                "rlm_strength": None, "public_pct_vs_line": float(public_home)}

    # Line moved against the public-favored side
    moved_against_home = (
        (public_home >= 55 and current > opening) or
        (public_home <= 45 and current < opening)
    )

    if not moved_against_home:
        return {"rlm_detected": False, "rlm_direction": None,
                "rlm_strength": None, "public_pct_vs_line": float(public_home)}

    if public_home >= 70 or public_home <= 30:
        strength = "strong"
    elif public_home >= 60 or public_home <= 40:
        strength = "moderate"
    else:
        strength = "weak"

    direction = "away" if public_home >= 55 else "home"

    return {
        "rlm_detected": True,
        "rlm_direction": direction,
        "rlm_strength": strength,
        "public_pct_vs_line": float(public_home),
    }

# ---------------------------------------------------------------------------
# Line tracker parser
#
# Real HTML structure (from live page):
#   Each matchup block = 3 rows:
#     Row 0: OPEN row  — "▶ 6:10 PM ET ET OPEN | spr ml tot | spr ml tot ..."
#     Row 1: Team A    — "[Team Name] | spr ml tot | spr ml tot ..."
#     Row 2: Team B    — "[Team Name] | spr ml tot | spr ml tot ..."
#
#   Columns per book group: SPR, ML, TOT  (repeated for each book)
#   Books in order: Circa, Boomers, BetMGM, Caesars, Westgate, Stations, South Point, Wynn
#
#   We take the FIRST book's columns (Circa) for opening + current lines.
#   Opening line is in the OPEN row, current is in Team rows.
# ---------------------------------------------------------------------------

_TEAM_LINK_RE = re.compile(r"/(?:mlb|nfl|nba|nhl)/teams/", re.I)
_TIME_RE = re.compile(r"(\d+:\d+\s*[AP]M\s*ET)", re.I)

def _parse_open_row(cells):
    """
    Extract opening (spread, ml, total) from OPEN row.
    Cell layout: [0]=time+OPEN, [1]=SPR('-1.5 +130'), [2]=ML('-125'), [3]=TOT('8'), ...
    First book = Circa = cells 1,2,3.
    SPR cell contains 'spread rl_price' — take first token only.
    """
    try:
        if len(cells) < 4:
            return None, None, None
        spr = float(cells[1].split()[0].replace('+', '')) if cells[1].split() else None
        ml  = int(re.sub(r'[^0-9+-]', '', cells[2].split()[0])) if cells[2].split() else None
        tot = float(cells[3].split()[0]) if cells[3].split() else None
        return spr, ml, tot
    except Exception:
        return None, None, None


def _parse_team_row(cells):
    """
    Extract current (spread, ml, total) from team row.
    Cell layout: [0]=team_name, [1]=SPR('-1.5 +125'), [2]=ML('-127 ▼'), [3]=TOT('8.5 o -115'), ...
    First book = Circa = cells 1,2,3.
    """
    try:
        if len(cells) < 4:
            return None, None, None
        spr = float(cells[1].split()[0].replace('+', '')) if cells[1].split() else None
        ml  = int(re.sub(r'[^0-9+-]', '', cells[2].split()[0])) if cells[2].split() else None
        tot = float(cells[3].split()[0]) if cells[3].split() else None
        return spr, ml, tot
    except Exception:
        return None, None, None


def _parse_lines_html(html: str, sport: str) -> list:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")

    games = []
    tables = soup.find_all("table")
    if not tables:
        return []

    # The line tracker has one main table
    table = tables[0]
    rows = table.find_all("tr")

    i = 0
    while i < len(rows):
        cells = [_clean(td.get_text(" ", strip=True)) for td in rows[i].find_all(["td", "th"])]
        if not cells:
            i += 1
            continue

        # Detect OPEN row by presence of time pattern
        first_cell = cells[0] if cells else ""
        time_match = _TIME_RE.search(first_cell)

        if time_match and "OPEN" in first_cell.upper():
            game_time_str = time_match.group(1).strip()
            # Opening line = first book cols (offset 1 = SPR, 2 = ML, 3 = TOT)
            open_spr, open_ml, open_tot = _parse_open_row(cells)

            # Next two rows are the two teams
            team_rows = []
            j = i + 1
            while j < len(rows) and len(team_rows) < 2:
                tr = rows[j]
                # Team rows have an anchor tag with /teams/ in href
                links = tr.find_all("a", href=_TEAM_LINK_RE)
                if links:
                    tcells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
                    team_name = _clean(links[0].get_text())
                    team_rows.append((team_name, tcells))
                j += 1

            if len(team_rows) == 2:
                away_name, away_cells = team_rows[0]
                home_name, home_cells = team_rows[1]

                # Current line for home and away teams (first book = Circa)
                cur_spr_home, cur_ml_home, cur_tot = _parse_team_row(home_cells)
                cur_spr_away, cur_ml_away, _       = _parse_team_row(away_cells)

                # Opening spread from OPEN row is away-team perspective; negate for home
                open_spr_home = -open_spr if open_spr is not None else None

                date_str = datetime.now().strftime("%Y%m%d")
                game_id = f"{sport.lower()}_{away_name.replace(' ', '_')}_{home_name.replace(' ', '_')}_{date_str}"

                games.append({
                    "game_id": game_id,
                    "sport": sport,
                    "home_team": home_name,
                    "away_team": away_name,
                    "game_time": game_time_str,
                    "opening_spread_home": open_spr_home,
                    "current_spread_home": cur_spr_home,
                    "opening_ml_home": open_ml,
                    "current_ml_home": cur_ml_home,
                    "total": cur_tot if cur_tot else open_tot,
                    "spread_bet_pct_home": None,
                    "spread_handle_pct_home": None,
                    "ml_bet_pct_home": None,
                    "ml_handle_pct_home": None,
                    "total_over_bet_pct": None,
                    "total_over_handle_pct": None,
                    "source": "VSiN",
                })
                i = j
                continue
        i += 1

    return games

# ---------------------------------------------------------------------------
# Betting splits parser
#
# Real HTML structure (from live page):
#   Table header: About | Spread SPR | Handle HND | Bets BET | Total TOT | Handle HND | Bets BET | Money ML | Handle HND | Bets BET
#   Each pair of rows = one game (team A on row, team B on next row)
#   Each team row: [icon] | [Team Name link] | SPR_line | SPR_hnd% | SPR_bet% | TOT_line | TOT_hnd% | TOT_bet% | ML_line | ML_hnd% | ML_bet%
#
#   Column indices (0-based, after stripping icon cell):
#     0: team name
#     1: spread line  (e.g. "-1.5")
#     2: spread handle %
#     3: spread bet %
#     4: total line
#     5: total handle %
#     6: total bet %
#     7: moneyline
#     8: ml handle %
#     9: ml bet %
# ---------------------------------------------------------------------------

def _parse_splits_html(html: str) -> list:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return []

    games = []
    date_str = datetime.now().strftime("%Y%m%d")

    for table in tables:
        rows = table.find_all("tr")
        # Skip header row(s)
        data_rows = []
        for tr in rows:
            links = tr.find_all("a", href=re.compile(r"/(?:mlb|nfl|nba|nhl|wnba)/teams/", re.I))
            if links:
                cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
                team_name = _clean(links[0].get_text())
                # detect sport from link href
                href = links[0].get("href", "")
                sport_match = re.search(r"/(mlb|nfl|nba|nhl|wnba)/", href, re.I)
                sport = sport_match.group(1).upper() if sport_match else "UNKNOWN"
                data_rows.append((team_name, sport, cells))

        # Pair up rows into games
        i = 0
        while i + 1 < len(data_rows):
            away_name, away_sport, away_cells = data_rows[i]
            home_name, home_sport, home_cells = data_rows[i + 1]

            def get_col(cells, idx):
                # cells[0] is usually icon/number, cells[1] is team name
                # actual data starts at index 2
                real_idx = idx + 2
                return cells[real_idx] if real_idx < len(cells) else None

            game_id = f"split_{away_sport.lower()}_{away_name.replace(' ', '_')}_{home_name.replace(' ', '_')}_{date_str}"

            games.append({
                "game_id": game_id,
                "sport": home_sport,
                "home_team": home_name,
                "away_team": away_name,
                "game_time": _now_iso(),
                "opening_spread_home": None,
                "current_spread_home": _to_float(get_col(home_cells, 0)),
                "opening_ml_home": None,
                "current_ml_home": _to_int(get_col(home_cells, 6)),
                "total": _to_float(get_col(home_cells, 3)),
                # home team splits
                "spread_handle_pct_home": _pct(get_col(home_cells, 1)),
                "spread_bet_pct_home":    _pct(get_col(home_cells, 2)),
                "total_over_handle_pct":  _pct(get_col(home_cells, 4)),
                "total_over_bet_pct":     _pct(get_col(home_cells, 5)),
                "ml_handle_pct_home":     _pct(get_col(home_cells, 7)),
                "ml_bet_pct_home":        _pct(get_col(home_cells, 8)),
                "source": "VSiN",
            })
            i += 2

    return games

# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class VSiNScraper:

    def scrape_lines(self, sport: str) -> list:
        sport = sport.upper()
        if sport not in BASE_URLS:
            return []
        try:
            html = _fetch_html(BASE_URLS[sport])
            return _parse_lines_html(html, sport)
        except Exception as e:
            print(f"[VSiN] scrape_lines({sport}) error: {e}")
            return []

    def scrape_splits(self, sport: str = "MLB") -> list:
        try:
            url = SPLITS_URL
            if sport.upper() == "NFL":
                url = SPLITS_URL  # same page, filtered by section
            html = _fetch_html(url)
            all_splits = _parse_splits_html(html)
            # filter to requested sport
            return [g for g in all_splits if g["sport"] == sport.upper()]
        except Exception as e:
            print(f"[VSiN] scrape_splits({sport}) error: {e}")
            return []

    def scrape_all_splits(self) -> list:
        """Return splits for all sports on the page."""
        try:
            html = _fetch_html(SPLITS_URL)
            return _parse_splits_html(html)
        except Exception as e:
            print(f"[VSiN] scrape_all_splits error: {e}")
            return []


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge_lines_and_splits(lines: list, splits: list) -> list:
    """Join line tracker data with betting splits using canonical team name matching."""
    if _USE_CANON:
        # Use canonical merge (declansx pattern) — handles abbreviations, affixes, sport scope
        sport = lines[0].get("sport", "MLB") if lines else "MLB"
        merged = merge_by_canon(
            lines, splits,
            sport=sport,
            fields_to_merge=[
                "spread_bet_pct_home", "spread_handle_pct_home",
                "ml_bet_pct_home", "ml_handle_pct_home",
                "total_over_bet_pct", "total_over_handle_pct",
            ],
        )
    else:
        # Fallback: original SequenceMatcher merge
        used = set()
        merged = []
        for lg in lines:
            best_i = None
            best_score = 0.0
            for i, sg in enumerate(splits):
                if i in used:
                    continue
                score = max(
                    _sim(lg.get("home_team"), sg.get("home_team")),
                    _sim(lg.get("away_team"), sg.get("away_team")),
                )
                if score > best_score:
                    best_score = score
                    best_i = i
            game = dict(lg)
            if best_i is not None and best_score >= 0.65:
                used.add(best_i)
                sg = splits[best_i]
                for k in ["spread_bet_pct_home","spread_handle_pct_home",
                          "ml_bet_pct_home","ml_handle_pct_home",
                          "total_over_bet_pct","total_over_handle_pct"]:
                    if game.get(k) is None:
                        game[k] = sg.get(k)
            merged.append(game)

    # Attach RLM signal to every merged game
    for game in merged:
        game["rlm"] = detect_rlm(game)

    return merged


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    s = VSiNScraper()
    print("Fetching MLB lines...")
    lines = s.scrape_lines("MLB")
    print(f"  Got {len(lines)} games")

    print("Fetching MLB splits...")
    splits = s.scrape_splits("MLB")
    print(f"  Got {len(splits)} split records")

    merged = merge_lines_and_splits(lines, splits)
    print(f"\nMerged sample (first 3):\n")
    print(json.dumps(merged[:3], indent=2))

    rlm_games = [g for g in merged if g.get("rlm", {}).get("rlm_detected")]
    print(f"\nRLM detected on {len(rlm_games)} games:")
    for g in rlm_games:
        print(f"  {g['away_team']} @ {g['home_team']} — {g['rlm']['rlm_strength']} RLM toward {g['rlm']['rlm_direction']}")
