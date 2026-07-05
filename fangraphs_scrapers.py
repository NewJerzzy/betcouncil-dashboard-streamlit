"""
fangraphs_scrapers.py — MLB starter/reliever splits and park factors from
FanGraphs.

NOTE: FanGraphs' support page states "We do not support ... API endpoints
... web scraping ... web queries" for data export. This module proceeds
per explicit user authorization (confirmed twice) despite that stated
preference. Kept as a separate, clearly-labeled module rather than mixed
into the MLB Stats API version (mlb_starter_bullpen_split.py) so the two
data-sourcing choices stay distinguishable in the codebase.

Verified real endpoints:
  Starter/reliever team ERA: fangraphs.com/api/leaders/major-league/data
      ?stats=sta (or rel) &pos=all&lg=all&season=X&season1=X&ind=0&qual=0
      &type=8&month=0&team=0&pageitems=500000
  Park factors: fangraphs.com/guts.aspx?type=pf

Public API
----------
fetch_team_era_split(season=None, pitcher_type="sta") -> dict {team: era}
team_starter_bullpen_gap(team_abbr, season=None) -> dict
fetch_park_factors() -> dict {team_or_park: park_factor}
"""
import requests
from datetime import date
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_CACHE = {}


def fetch_team_era_split(season: int = None, pitcher_type: str = "sta") -> dict:
    """
    pitcher_type: "sta" (starters) or "rel" (relievers) — confirmed real
    FanGraphs leaderboard parameter values.
    Returns {team_abbr: era} aggregated at the team level.
    """
    season = season or date.today().year
    cache_key = (season, pitcher_type)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    url = "https://www.fangraphs.com/api/leaders/major-league/data"
    params = {
        "age": "", "pos": "all", "stats": pitcher_type, "lg": "all",
        "season": season, "season1": season, "ind": "0", "qual": "0",
        "type": "8", "month": "0", "team": "0,ts", "pageitems": "500000",
    }
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=20)
        if resp.status_code != 200:
            return {}
        rows = resp.json().get("data", [])
        result = {}
        for row in rows:
            team = row.get("Team") or row.get("TeamName")
            era = row.get("ERA")
            ip = row.get("IP")
            if team and era is not None and ip:
                # weight by IP if multiple rows per team appear (shouldn't,
                # since this is a team-level request, but defensive)
                if team not in result:
                    result[team] = {"era_sum_weighted": float(era) * float(ip), "ip": float(ip)}
                else:
                    result[team]["era_sum_weighted"] += float(era) * float(ip)
                    result[team]["ip"] += float(ip)
        final = {t: round(v["era_sum_weighted"] / v["ip"], 2) for t, v in result.items() if v["ip"] > 0}
        _CACHE[cache_key] = final
        return final
    except Exception as e:
        print(f"[WARN] fetch_team_era_split({pitcher_type}): {e}")
        return {}


def team_starter_bullpen_gap(team_abbr: str, season: int = None) -> dict:
    """Same signal shape as mlb_starter_bullpen_split.py, sourced from FanGraphs."""
    starters = fetch_team_era_split(season, "sta")
    relievers = fetch_team_era_split(season, "rel")
    starter_era = starters.get(team_abbr)
    bullpen_era = relievers.get(team_abbr)
    if starter_era is None or bullpen_era is None:
        return {}

    gap = round(bullpen_era - starter_era, 2)
    if gap >= 0.75:
        signal, note = "FADE_FULL_GAME", "Elite starters, weak bullpen — bet F5, fade full game"
    elif gap <= -0.75:
        signal, note = "BET_FULL_GAME", "Weak starters, elite bullpen — fade F5, bet full game"
    elif abs(gap) >= 0.35:
        signal, note = "SLIGHT_LEAN", "Moderate starter/bullpen gap"
    else:
        signal, note = "NEUTRAL", "No signal from this split"

    return {"team": team_abbr, "starter_era": starter_era, "bullpen_era": bullpen_era,
            "gap": gap, "signal": signal, "note": note}


def fetch_park_factors() -> dict:
    """
    Parses fangraphs.com/guts.aspx?type=pf — real page, standard HTML
    table. Returns {team_name: park_factor} using whatever real numbers
    are on the page (not hardcoded).
    """
    if "park_factors" in _CACHE:
        return _CACHE["park_factors"]

    url = "https://www.fangraphs.com/guts.aspx?type=pf"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"class": "rgMasterTable"}) or soup.find("table")
        if not table:
            return {}

        result = {}
        header_cells = [th.get_text(strip=True) for th in table.find_all("th")]
        team_idx = next((i for i, h in enumerate(header_cells) if h.lower() == "team"), 1)
        pf_idx = next((i for i, h in enumerate(header_cells) if h.strip().lower() in ("park factor", "pf")), None)
        if pf_idx is None:
            return {}

        for tr in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) <= max(team_idx, pf_idx):
                continue
            team = cells[team_idx]
            try:
                pf = float(cells[pf_idx])
            except ValueError:
                continue
            if team:
                result[team] = pf

        _CACHE["park_factors"] = result
        return result
    except Exception as e:
        print(f"[WARN] fetch_park_factors: {e}")
        return {}
