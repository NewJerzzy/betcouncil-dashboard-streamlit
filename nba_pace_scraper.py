"""
nba_pace_scraper.py — NBA team pace from stats.nba.com.

Rather than scrape the rendered nba.com/stats/teams/advanced React page
(fragile — table class names and column positions change with frontend
rebuilds), this hits the actual underlying JSON API that page calls:
stats.nba.com/stats/leaguedashteamstats?MeasureType=Advanced&...

This is the real, well-documented API surface (same one the nba_api open
source package wraps) and returns PACE by field NAME in the response
headers, not by fragile column position — more robust than the column[17]
approach, same underlying data.

stats.nba.com requires specific headers or it 403s — included below
(this is a genuine technical requirement of the site, not a workaround
of any stated restriction; there is no anti-scraping ToS statement on
stats.nba.com equivalent to FanGraphs').

Public API
----------
fetch_team_pace(season=None) -> dict {team_name: pace}
classify_pace_tier(team_name, pace_data=None) -> "TOP5"|"BOTTOM5"|"MID"
"""
import requests
from datetime import date

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Accept": "application/json",
}

_CACHE = {}


def _current_season_str() -> str:
    """NBA season format e.g. '2025-26' — derived from today's date."""
    today = date.today()
    year = today.year if today.month >= 10 else today.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def fetch_team_pace(season: str = None) -> dict:
    """Returns {team_name: pace_value} for all 30 teams, current season by default."""
    season = season or _current_season_str()
    if season in _CACHE:
        return _CACHE[season]

    url = "https://stats.nba.com/stats/leaguedashteamstats"
    params = {
        "MeasureType": "Advanced",
        "PerMode": "PerGame",
        "Season": season,
        "SeasonType": "Regular Season",
        "LeagueID": "00",
        "Conference": "", "Division": "", "GameScope": "", "GameSegment": "",
        "LastNGames": "0", "Location": "", "Month": "0", "OpponentTeamID": "0",
        "Outcome": "", "PaceAdjust": "N", "Period": "0", "PlusMinus": "N",
        "Rank": "N", "SeasonSegment": "", "ShotClockRange": "", "VsConference": "",
        "VsDivision": "", "TeamID": "0",
    }
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=20)
        if resp.status_code != 200:
            print(f"[WARN] nba_pace_scraper: HTTP {resp.status_code}")
            return {}
        data = resp.json()
        result_set = data.get("resultSets", [{}])[0]
        headers = result_set.get("headers", [])
        rows = result_set.get("rowSet", [])
        if "PACE" not in headers or "TEAM_NAME" not in headers:
            return {}

        pace_idx = headers.index("PACE")
        name_idx = headers.index("TEAM_NAME")
        pace_data = {row[name_idx]: row[pace_idx] for row in rows}
        _CACHE[season] = pace_data
        return pace_data
    except Exception as e:
        print(f"[WARN] fetch_team_pace: {e}")
        return {}


def classify_pace_tier(team_name: str, pace_data: dict = None) -> str:
    """Same logic as nba_pace_mismatch.py's tier classifier, sourced from real API data."""
    pace_data = pace_data if pace_data is not None else fetch_team_pace()
    if not pace_data or team_name not in pace_data:
        return "UNKNOWN"
    ranked = sorted(pace_data.items(), key=lambda kv: kv[1], reverse=True)
    names = [n for n, _ in ranked]
    idx = names.index(team_name)
    if idx < 5:
        return "TOP5"
    if idx >= len(names) - 5:
        return "BOTTOM5"
    return "MID"
