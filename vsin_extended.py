# vsin_extended.py
# Scrapers for:
#   1. Makinen Daily Ratings       — data.vsin.com/mlb/daily-power-ratings/
#   2. Team Summary ATS/ML Trends  — data.vsin.com/mlb/analysis/team-summary/
#   3. DK Handle Splits            — data.vsin.com/betting-splits/?source=DK&view=topspreadhandle

import json
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher

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

MAKINEN_URLS = {
    "MLB": "https://data.vsin.com/mlb/daily-power-ratings/",
    "NBA": "https://data.vsin.com/nba/daily-power-ratings/",
    "NFL": "https://data.vsin.com/nfl/weekly-power-ratings/",
}

TEAM_SUMMARY_URLS = {
    "MLB":    "https://data.vsin.com/mlb/analysis/team-summary/",
    "MLB_F5": "https://data.vsin.com/mlb/analysis/team-summary/?view=f5",
}

DK_SPLITS_URLS = {
    "spread_handle": "https://data.vsin.com/betting-splits/?source=DK&view=topspreadhandle",
    "spread_bets":   "https://data.vsin.com/betting-splits/?source=DK&view=topspreadbets",
    "ml_handle":     "https://data.vsin.com/betting-splits/?source=DK&view=topmoneylinehandle",
    "ml_bets":       "https://data.vsin.com/betting-splits/?source=DK&view=topmoneylinebets",
    "total_handle":  "https://data.vsin.com/betting-splits/?source=DK&view=toptotalhandle",
    "total_bets":    "https://data.vsin.com/betting-splits/?source=DK&view=toptotalbets",
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
        if x is None:
            return None
        s = str(x).strip().replace("\u2212", "-").replace("+", "").replace("½", ".5")
        if s in {"", "-", "N/A", "NA", "None", "PK"}:
            return None
        return float(s)
    except Exception:
        return None

def _to_int(x):
    try:
        if x is None:
            return None
        s = str(x).strip().replace("\u2212", "-").replace(",", "").replace(" ", "")
        if s in {"", "-", "N/A", "NA"}:
            return None
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

def _dollars(x):
    """Parse profit strings like '+$1,081' or '$-760'"""
    try:
        if x is None:
            return None
        s = str(x).replace("$", "").replace(",", "").replace(" ", "").strip()
        if s in {"", "-", "N/A"}:
            return None
        return float(s)
    except Exception:
        return None

def _roi(x):
    """Parse ROI strings like '+10.2%' or '-8.3%'"""
    try:
        if x is None:
            return None
        s = str(x).replace("%", "").replace("+", "").strip()
        if s in {"", "-", "N/A"}:
            return None
        return float(s)
    except Exception:
        return None

def _record(x):
    """Parse '39-38' into (wins, losses)"""
    try:
        if not x:
            return None, None
        parts = str(x).split("-")
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
        return None, None
    except Exception:
        return None, None

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
# 1. Makinen Daily Ratings parser
#
# Page structure (from live HTML):
#   Each matchup = card block containing:
#     - Game header: "[Away] at [Home]  TIME  ML  O/U"
#     - Sub-header row: "[Away]  ML_away  total | [Home]"  
#     - Data grid with labels: Streak, Score Proj, Eff Line, Team Rtg, Eff Runs, Starter, Bullpen
#     - Two value columns: away_value | home_value
#
# We parse by finding all anchor pairs with /mlb/teams/ hrefs,
# then extracting the structured text block between them.
# ---------------------------------------------------------------------------

_TEAM_RE = re.compile(r"/(?:mlb|nfl|nba|nhl)/teams/", re.I)
_TIME_RE  = re.compile(r"(\d+:\d+\s*[AP]M\s*ET)", re.I)
_ML_RE    = re.compile(r"([+-]?\d{3,4})")
_TOTAL_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")

def parse_makinen(html: str, sport: str = "MLB") -> list:
    """
    Parses Makinen daily ratings page — plain text layout, not a table.
    Per game block structure:
      Away at Home / TIME / ML O/U / away_ml / total / home_ml
      Streak v1 v2 / Score Proj v1 v2 / Eff Line val ml
      Team Rtg v1 v2 / Eff Runs v1 v2 / Starter v1 v2 / Bullpen v1 v2
    """
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]

    games = []
    date_str = datetime.now().strftime("%Y%m%d")

    def to_f(x):
        try:
            return float(str(x).replace("+", "").replace("\u2212", "-")) if x else None
        except Exception:
            return None

    def to_i(x):
        try:
            return int(float(str(x).replace(",", "").strip())) if x else None
        except Exception:
            return None

    def get_pair(label, block):
        for k, ln in enumerate(block):
            if ln.strip().lower() == label.lower():
                vals = []
                j = k + 1
                while j < len(block) and len(vals) < 2:
                    v = block[j].strip()
                    if v and v.lower() not in {label.lower(), "ml", "o/u"}:
                        vals.append(v)
                    j += 1
                return (vals[0] if vals else None), (vals[1] if len(vals) > 1 else None)
        return None, None

    i = 0
    while i < len(lines):
        # Game header can be:
        #   "Yankees at Tigers" (single line), OR
        #   "Yankees" / "at" / "Tigers" (three separate lines)
        away_team = home_team = None

        if lines[i].lower() == "at" and i >= 1 and i + 1 < len(lines):
            # Three-line format: prev=away, curr="at", next=home
            away_team = lines[i-1].strip()
            home_team = lines[i+1].strip()
            # Validate — should look like team names, not nav/label text
            skip_words = {"ml", "o/u", "streak", "bullpen", "starter", "search", "subscribe", "sports", "nfl", "nba", "mlb", "nhl"}
            if away_team.lower() in skip_words or home_team.lower() in skip_words:
                i += 1
                continue
            if len(away_team) < 2 or len(home_team) < 2:
                i += 1
                continue
            # Block starts after home_team line
            block_start = i + 2
        elif " at " in lines[i] and i + 2 < len(lines):
            parts = lines[i].split(" at ", 1)
            away_team = parts[0].strip()
            home_team = parts[1].strip()
            if len(away_team) < 2 or len(home_team) < 2:
                i += 1
                continue
            block_start = i + 1
        
        if away_team and home_team:

            block = []
            j = block_start
            while j < len(lines):
                # Stop at next "at" separator (three-line format)
                if lines[j].lower() == "at" and j > block_start + 3:
                    break
                # Stop at next single-line "X at Y" format
                if " at " in lines[j] and j > block_start + 3:
                    break
                block.append(lines[j])
                j += 1

            block_str = " ".join(block)

            game = {
                "game_id": f"mak_{sport.lower()}_{away_team.replace(' ','_')}_{home_team.replace(' ','_')}_{date_str}",
                "sport": sport, "away_team": away_team, "home_team": home_team,
                "game_time": None, "ml_away": None, "ml_home": None, "total": None,
                "away_streak": None, "home_streak": None,
                "away_score_proj": None, "home_score_proj": None, "projected_total": None,
                "eff_line": None, "eff_line_dir": None, "eff_ml": None,
                "away_team_rtg": None, "home_team_rtg": None,
                "away_eff_runs": None, "home_eff_runs": None,
                "away_starter_rtg": None, "home_starter_rtg": None,
                "away_bullpen_rtg": None, "home_bullpen_rtg": None,
                "makinen_favorite": "pick", "source": "VSiN_Makinen",
            }

            tm = _TIME_RE.search(block_str)
            if tm:
                game["game_time"] = tm.group(1)

            ml_vals = re.findall(r"[+-]\d{3,4}", block_str)
            if ml_vals:
                game["ml_away"] = to_i(ml_vals[0])
            if len(ml_vals) > 1:
                game["ml_home"] = to_i(ml_vals[1])

            split_parts = re.split(r"[+-]\d{3,4}", block_str)
            if len(split_parts) > 1:
                for tc in re.findall(r"\b(\d+\.?\d*)\b", split_parts[1]):
                    v = float(tc)
                    if 4 < v < 25:
                        game["total"] = v
                        break

            s1, s2 = get_pair("Streak", block)
            game["away_streak"] = s1
            game["home_streak"] = s2

            p1, p2 = get_pair("Score Proj", block)
            game["away_score_proj"] = to_f(p1)
            game["home_score_proj"] = to_f(p2)
            if game["away_score_proj"] and game["home_score_proj"]:
                game["projected_total"] = round(game["away_score_proj"] + game["home_score_proj"], 2)

            for k, ln in enumerate(block):
                if ln.strip() == "Eff Line":
                    el_raw = block[k+1].strip() if k+1 < len(block) else None
                    el_ml  = block[k+2].strip() if k+2 < len(block) else None
                    if el_raw:
                        m2 = re.match(r"([\d.]+)(OV|UN|ov|un)?", el_raw, re.I)
                        if m2:
                            game["eff_line"] = float(m2.group(1))
                            game["eff_line_dir"] = m2.group(2).upper() if m2.group(2) else None
                    game["eff_ml"] = to_i(el_ml)
                    break

            r1, r2 = get_pair("Team Rtg", block)
            game["away_team_rtg"] = to_f(r1)
            game["home_team_rtg"] = to_f(r2)

            e1, e2 = get_pair("Eff Runs", block)
            game["away_eff_runs"] = to_f(e1)
            game["home_eff_runs"] = to_f(e2)

            sp1, sp2 = get_pair("Starter", block)
            game["away_starter_rtg"] = to_f(sp1)
            game["home_starter_rtg"] = to_f(sp2)

            bp1, bp2 = get_pair("Bullpen", block)
            game["away_bullpen_rtg"] = to_f(bp1)
            game["home_bullpen_rtg"] = to_f(bp2)

            ar, hr = game["away_team_rtg"], game["home_team_rtg"]
            if ar is not None and hr is not None:
                game["makinen_favorite"] = "home" if hr > ar else "away" if ar > hr else "pick"

            games.append(game)
            i = j
            continue
        else:
            i += 1
            continue
        i += 1

    return games

# ---------------------------------------------------------------------------
# 2. Team Summary ATS/ML/OU Trends
#
# Table columns (from live HTML):
# TEAM | G | RF | RA | REC | $PROFIT | ROI | REC | $PROFIT | ROI | Ov/Un | $PROFIT | ROI | $PROFIT | ROI
# idx:   0    1    2    3     4         5     6     7         8     9       10        11    12        13
#
# Section order: ML Results | Run Line Results | O/U Results | Combined
# ---------------------------------------------------------------------------

def parse_team_summary(html: str, sport: str = "MLB") -> list:
    """
    Returns list of dicts, one per team:
    {
        team, games_played, runs_for, runs_against,
        ml_record, ml_wins, ml_losses,
        ml_profit, ml_roi,
        rl_record, rl_wins, rl_losses,
        rl_profit, rl_roi,
        ou_record, ou_overs, ou_unders,
        ou_profit, ou_roi,
        combined_profit, combined_roi,
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
        if not cells or len(cells) < 10:
            continue

        # Skip header rows
        if cells[0].upper() in {"TEAM", "ALL GAMES", ""}:
            continue

        # Must have a team link
        links = tr.find_all("a", href=_TEAM_RE)
        if not links:
            continue

        team_name = _clean(links[0].get_text())

        # cells layout:
        # 0=team  1=G  2=RF  3=RA
        # 4=ML_rec  5=ML_profit  6=ML_roi
        # 7=RL_rec  8=RL_profit  9=RL_roi
        # 10=OU_rec  11=OU_profit  12=OU_roi
        # 13=combined_profit  14=combined_roi

        ml_w, ml_l   = _record(cells[4]  if len(cells) > 4  else None)
        rl_w, rl_l   = _record(cells[7]  if len(cells) > 7  else None)
        ou_raw       = cells[10] if len(cells) > 10 else None

        # O/U record format: "31-40-6" (over-under-push)
        ou_o = ou_u = ou_p = None
        if ou_raw:
            parts = ou_raw.split("-")
            if len(parts) >= 2:
                ou_o = int(parts[0]) if parts[0].isdigit() else None
                ou_u = int(parts[1]) if parts[1].isdigit() else None
                ou_p = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        teams.append({
            "team":             team_name,
            "sport":            sport,
            "games_played":     _to_int(cells[1]  if len(cells) > 1  else None),
            "runs_for_avg":     _to_float(cells[2] if len(cells) > 2 else None),
            "runs_against_avg": _to_float(cells[3] if len(cells) > 3 else None),
            # ML
            "ml_record":        cells[4]  if len(cells) > 4  else None,
            "ml_wins":          ml_w,
            "ml_losses":        ml_l,
            "ml_profit":        _dollars(cells[5]  if len(cells) > 5  else None),
            "ml_roi_pct":       _roi(cells[6]      if len(cells) > 6  else None),
            # Run Line (ATS)
            "rl_record":        cells[7]  if len(cells) > 7  else None,
            "rl_wins":          rl_w,
            "rl_losses":        rl_l,
            "rl_profit":        _dollars(cells[8]  if len(cells) > 8  else None),
            "rl_roi_pct":       _roi(cells[9]      if len(cells) > 9  else None),
            # Over/Under
            "ou_record":        ou_raw,
            "ou_overs":         ou_o,
            "ou_unders":        ou_u,
            "ou_pushes":        ou_p,
            "ou_profit":        _dollars(cells[11] if len(cells) > 11 else None),
            "ou_roi_pct":       _roi(cells[12]     if len(cells) > 12 else None),
            # Combined
            "combined_profit":  _dollars(cells[13] if len(cells) > 13 else None),
            "combined_roi_pct": _roi(cells[14]     if len(cells) > 14 else None),
            "source":           "VSiN_TeamSummary",
        })

    return teams


# ---------------------------------------------------------------------------
# 3. DK Handle Splits  (same structure as base splits — just different URL)
# Reuses the exact same parser from vsin_scraper.py
# ---------------------------------------------------------------------------

def parse_dk_splits(html: str) -> list:
    """Same column structure as betting-splits main page."""
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    games = []
    date_str = datetime.now().strftime("%Y%m%d")

    for table in tables:
        data_rows = []
        for tr in table.find_all("tr"):
            links = tr.find_all("a", href=re.compile(r"/(?:mlb|nfl|nba|nhl|wnba)/teams/", re.I))
            if not links:
                continue
            cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
            team_name = _clean(links[0].get_text())
            href = links[0].get("href", "")
            sm = re.search(r"/(mlb|nfl|nba|nhl|wnba)/", href, re.I)
            sport = sm.group(1).upper() if sm else "UNKNOWN"
            data_rows.append((team_name, sport, cells))

        i = 0
        while i + 1 < len(data_rows):
            away_name, _, away_cells = data_rows[i]
            home_name, home_sport, home_cells = data_rows[i + 1]

            def gc(cells, idx):
                real = idx + 2
                return cells[real] if real < len(cells) else None

            games.append({
                "game_id":               f"dk_{home_sport.lower()}_{away_name.replace(' ','_')}_{home_name.replace(' ','_')}_{date_str}",
                "sport":                 home_sport,
                "home_team":             home_name,
                "away_team":             away_name,
                "current_spread_home":   _to_float(gc(home_cells, 0)),
                "spread_handle_pct_home": _pct(gc(home_cells, 1)),
                "spread_bet_pct_home":   _pct(gc(home_cells, 2)),
                "total":                 _to_float(gc(home_cells, 3)),
                "total_over_handle_pct": _pct(gc(home_cells, 4)),
                "total_over_bet_pct":    _pct(gc(home_cells, 5)),
                "current_ml_home":       _to_int(gc(home_cells, 6)),
                "ml_handle_pct_home":    _pct(gc(home_cells, 7)),
                "ml_bet_pct_home":       _pct(gc(home_cells, 8)),
                "source":                "VSiN_DK",
            })
            i += 2

    return games


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

class VSiNExtended:

    def scrape_makinen(self, sport: str = "MLB") -> list:
        sport = sport.upper()
        url = MAKINEN_URLS.get(sport)
        if not url:
            return []
        try:
            html = _fetch_html(url)
            return parse_makinen(html, sport)
        except Exception as e:
            print(f"[VSiN Makinen] error: {e}")
            return []

    def scrape_team_summary(self, sport: str = "MLB", f5: bool = False) -> list:
        key = "MLB_F5" if (sport.upper() == "MLB" and f5) else sport.upper()
        url = TEAM_SUMMARY_URLS.get(key)
        if not url:
            return []
        try:
            html = _fetch_html(url)
            return parse_team_summary(html, sport.upper())
        except Exception as e:
            print(f"[VSiN TeamSummary] error: {e}")
            return []

    def scrape_dk_splits(self, view: str = "spread_handle") -> list:
        url = DK_SPLITS_URLS.get(view)
        if not url:
            print(f"Unknown view '{view}'. Options: {list(DK_SPLITS_URLS.keys())}")
            return []
        try:
            html = _fetch_html(url)
            return parse_dk_splits(html)
        except Exception as e:
            print(f"[VSiN DK Splits] error: {e}")
            return []


# ---------------------------------------------------------------------------
# BetCouncil signal helpers
# ---------------------------------------------------------------------------

def makinen_vs_book(makinen_game: dict, book_total: float) -> dict:
    """
    Compare Makinen's projected total vs book total.
    Returns edge signal for O/U.
    """
    proj = makinen_game.get("projected_total")
    if proj is None or book_total is None:
        return {"total_edge": None, "total_direction": None, "total_gap": None}

    gap = round(proj - book_total, 2)
    direction = "over" if gap > 0 else "under" if gap < 0 else "none"
    return {
        "total_edge": abs(gap),
        "total_direction": direction,
        "total_gap": gap,
    }

def team_trend_signal(team_stats: dict) -> dict:
    """
    Convert team summary stats into BetCouncil signal inputs.
    Returns hot/cold ATS and O/U trend flags.
    """
    ml_roi  = team_stats.get("ml_roi_pct")
    rl_roi  = team_stats.get("rl_roi_pct")
    ou_roi  = team_stats.get("ou_roi_pct")
    ou_o    = team_stats.get("ou_overs")
    ou_u    = team_stats.get("ou_unders")

    ou_lean = None
    if ou_o and ou_u:
        total_ou = ou_o + ou_u
        if total_ou > 0:
            over_rate = ou_o / total_ou
            if over_rate >= 0.58:
                ou_lean = "over"
            elif over_rate <= 0.42:
                ou_lean = "under"

    return {
        "team":          team_stats.get("team"),
        "ml_roi_pct":    ml_roi,
        "rl_roi_pct":    rl_roi,
        "ou_roi_pct":    ou_roi,
        "ou_lean":       ou_lean,
        "ats_hot":       rl_roi is not None and rl_roi >= 8.0,
        "ats_cold":      rl_roi is not None and rl_roi <= -12.0,
        "ml_value":      ml_roi is not None and ml_roi >= 5.0,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ext = VSiNExtended()

    print("=== Makinen Ratings (MLB) ===")
    mak = ext.scrape_makinen("MLB")
    print(f"Games parsed: {len(mak)}")
    if mak:
        print(json.dumps(mak[0], indent=2))

    print("\n=== Team Summary (MLB) ===")
    teams = ext.scrape_team_summary("MLB")
    print(f"Teams parsed: {len(teams)}")
    if teams:
        print(json.dumps(teams[0], indent=2))
        # Show ATS hot/cold
        signals = [team_trend_signal(t) for t in teams]
        hot  = [s["team"] for s in signals if s["ats_hot"]]
        cold = [s["team"] for s in signals if s["ats_cold"]]
        over_lean  = [s["team"] for s in signals if s["ou_lean"] == "over"]
        under_lean = [s["team"] for s in signals if s["ou_lean"] == "under"]
        print(f"\nATS Hot  (+8% ROI): {hot}")
        print(f"ATS Cold (-12% ROI): {cold}")
        print(f"Over lean  (58%+): {over_lean}")
        print(f"Under lean (42%-): {under_lean}")

    print("\n=== DK Handle Splits ===")
    dk = ext.scrape_dk_splits("spread_handle")
    print(f"Games parsed: {len(dk)}")
    if dk:
        print(json.dumps(dk[0], indent=2))
