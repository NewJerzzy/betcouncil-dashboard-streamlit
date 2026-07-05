"""
teamrankings_situational.py — Free, unlimited situational trend scraper.

Replaces the KillerSports 10-searches/day limit. Endpoint URLs and table
columns below were verified against live TeamRankings.com pages before
writing this (not guessed):

  https://www.teamrankings.com/{sport}/trends/{trend_type}/?sc={filter}
  Table columns confirmed live: Team | <Record col> | <Pct col> | MOV | +/-
  e.g. NFL ats_trends?sc=is_home returned:
       Team | ATS Record | Cover % | MOV | ATS +/-

Only trend_type + filter combinations actually confirmed to return a page
are included in TEAMRANKINGS_ENDPOINTS / TEAMRANKINGS_FILTERS below. If you
need a combination not listed, verify it against the live site before
adding it — DeepSeek's original endpoint names (overs_unders_trends/,
day_night_trends/, bullpen_trends/) do NOT exist and were fabricated.

Public API
----------
scrape_trend(sport, trend_type, filter_code) -> list[dict]
    Raw rows: {team, record, pct, mov, plus_minus}

fetch_situational_signals(sport, max_filters=6) -> list[dict]
    Scored + sorted signals across a rotation of filters, z-score gated.
"""
import math
import time
import os

import requests
from bs4 import BeautifulSoup

try:
    from fetchers import CACHE_DIR, _safe_load_pkl, _safe_save_pkl
except ImportError:
    CACHE_DIR = "/tmp"
    _safe_load_pkl = lambda p: None
    _safe_save_pkl = lambda p, d: None

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# Verified live: base trend-type pages that exist per sport.
TEAMRANKINGS_ENDPOINTS = {
    "NFL": ["ats_trends", "ou_trends", "win_trends"],
    "NBA": ["ats_trends", "ou_trends", "win_trends"],
    "MLB": ["win_trends", "ou_trends", "ats_trends"],
    "NHL": ["win_trends", "ou_trends", "ats_trends"],
}

# Verified live: ?sc= filter codes confirmed to return real filtered pages
# (is_home, is_away, is_home_fav, is_away_fav, is_away_dog, is_after_loss,
# one_day_off all confirmed via live search-result URLs).
TEAMRANKINGS_FILTERS = [
    "all_games",
    "is_home",
    "is_away",
    "is_home_fav",
    "is_away_fav",
    "is_away_dog",
    "is_after_loss",
    "one_day_off",
    "is_division",  # verified live: teamrankings.com/nfl/trend/ats_trends/is_division
]

_SPORT_SLUG = {"NFL": "nfl", "NBA": "nba", "MLB": "mlb", "NHL": "nhl"}


def scrape_trend(sport: str, trend_type: str, filter_code: str = "all_games") -> list:
    """
    Scrape one TeamRankings trend page. Returns list of
    {team, record, pct, mov, plus_minus} using whatever the actual table
    headers are (labels vary: 'ATS Record'/'Record', 'Cover %'/'Win %').
    Cached 6 hours (these situational splits don't change intra-day).
    """
    slug = _SPORT_SLUG.get(sport.upper())
    if not slug or trend_type not in TEAMRANKINGS_ENDPOINTS.get(sport.upper(), []):
        return []

    cache_key = f"tr_{slug}_{trend_type}_{filter_code}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    url = f"https://www.teamrankings.com/{slug}/trends/{trend_type}/"
    params = {} if filter_code == "all_games" else {"sc": filter_code}

    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if table is None:
            return []

        rows = []
        header_cells = [th.get_text(strip=True) for th in table.find_all("th")]
        for tr in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) < 3:
                continue
            row = dict(zip(header_cells, cells)) if header_cells else {}
            team = row.get("Team") or (cells[0] if cells else "")
            record = None
            pct = None
            for k, v in row.items():
                if "Record" in k:
                    record = v
                if "%" in k:
                    pct = v
            if not team or not record:
                continue
            rows.append({
                "team": team,
                "record": record,
                "pct": pct,
                "mov": row.get("MOV"),
                "plus_minus": next((v for k, v in row.items() if "+/-" in k), None),
                "trend_type": trend_type,
                "filter": filter_code,
            })

        if rows:
            try:
                _safe_save_pkl(cache_path, rows)
            except Exception:
                pass
        return rows
    except Exception as e:
        print(f"[WARN] scrape_trend({sport},{trend_type},{filter_code}): {e}")
        return []


def _z_score(record: str) -> dict:
    """
    Statistical significance of a W-L(-T) record vs a 50% baseline.
    Returns {n, win_rate, z, score, confidence}.
    """
    try:
        parts = [int(p) for p in record.split("-")]
        wins = parts[0]
        losses = parts[1]
        n = wins + losses
    except Exception:
        return {"n": 0, "win_rate": 0.0, "z": 0.0, "score": 0, "confidence": "invalid"}

    if n < 10:
        return {"n": n, "win_rate": 0.0, "z": 0.0, "score": 0, "confidence": "sample too small"}

    win_rate = wins / n
    z = (win_rate - 0.5) / math.sqrt(0.25 / n)

    score = 0
    confidence = "not significant"
    if abs(z) > 3.0 and n > 50:
        score, confidence = 10, "elite (99.9%+)"
    elif abs(z) > 2.58:
        score, confidence = 7, "99%"
    elif abs(z) > 1.96:
        score, confidence = 5, "95%"
    elif abs(z) > 1.64:
        score, confidence = 3, "90%"

    return {"n": n, "win_rate": round(win_rate, 3), "z": round(z, 2), "score": score, "confidence": confidence}


def fetch_situational_signals(sport: str, max_filters: int = 6) -> list:
    """
    Pull a rotation of trend_type x filter combos for a sport, score each
    row's record for statistical significance, and return only signals
    that clear the 90%+ confidence bar (score > 0), sorted by score desc.
    """
    sport = sport.upper()
    trend_types = TEAMRANKINGS_ENDPOINTS.get(sport, [])
    filters = TEAMRANKINGS_FILTERS[:max_filters]

    signals = []
    for trend_type in trend_types:
        for filter_code in filters:
            rows = scrape_trend(sport, trend_type, filter_code)
            for row in rows:
                z = _z_score(row["record"])
                if z["score"] <= 0:
                    continue
                signals.append({
                    "team": row["team"],
                    "trend_type": trend_type,
                    "filter": filter_code,
                    "record": row["record"],
                    "win_rate": z["win_rate"],
                    "n_games": z["n"],
                    "z_score": z["z"],
                    "confidence": z["confidence"],
                    "score": z["score"],
                    "signal": "LEAN_OVER" if z["win_rate"] > 0.5 else "LEAN_UNDER",
                })

    signals.sort(key=lambda x: x["score"], reverse=True)
    return signals
