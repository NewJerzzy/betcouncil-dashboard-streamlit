"""
mlb_starter_bullpen_split.py — F5 vs full-game bet signal.

Uses statsapi.mlb.com (official MLB API, no ToS restriction — unlike
FanGraphs, which explicitly disallows scraping/API access). Classifies
each pitcher on a team's active roster as starter or reliever using the
real `gamesStarted` field already used elsewhere in fetchers.py, then
computes an innings-weighted team ERA for each bucket.

Logic (matches the real, verifiable signal you confirmed manually):
  - Elite starters + bad bullpen  -> bet F5, fade full game
  - Bad starters + elite bullpen  -> fade F5, bet full game
  - Both similar                  -> no edge from this signal

Public API
----------
team_starter_bullpen_split(team_id, season=None) -> dict
    {starter_era, bullpen_era, gap, signal, note}
"""
import requests
from datetime import date

LEAGUE_AVG_ERA = 4.20
_STARTER_MIN_GS_RATIO = 0.5  # a pitcher counts as a "starter" if >=50% of appearances were starts

_TEAM_ID_CACHE = {}


def _get_mlb_team_id(team_name: str) -> int:
    """Resolve a team name to its MLB Stats API team_id (real, confirmed endpoint)."""
    if not _TEAM_ID_CACHE:
        try:
            resp = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1", timeout=10)
            if resp.status_code == 200:
                for t in resp.json().get("teams", []):
                    _TEAM_ID_CACHE[t.get("name", "").lower()] = t.get("id")
        except Exception:
            pass

    key = team_name.lower().strip()
    if key in _TEAM_ID_CACHE:
        return _TEAM_ID_CACHE[key]
    for name, tid in _TEAM_ID_CACHE.items():
        if key in name or name in key:
            return tid
    return None


def _fetch_active_pitchers(team_id: int) -> list:
    """Real endpoint, same pattern already used in fetchers.py for rosters."""
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return []
    roster = resp.json().get("roster", [])
    return [p for p in roster if p.get("position", {}).get("abbreviation") == "P"]


def _fetch_pitcher_season_stats(pitcher_id: int, season: int) -> dict:
    """Real endpoint/fields, same as fetch_mlb_rolling_averages() in fetchers.py."""
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats"
        f"?stats=season&group=pitching&season={season}"
    )
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return {}
    splits = resp.json().get("stats", [{}])[0].get("splits", [])
    if not splits:
        return {}
    return splits[0].get("stat", {})


def team_starter_bullpen_split(team_id: int, season: int = None) -> dict:
    """
    Computes innings-weighted starter ERA vs bullpen ERA for a team using
    only real, confirmed MLB Stats API fields (gamesStarted, era,
    inningsPitched, gamesPlayed).
    """
    season = season or date.today().year
    pitchers = _fetch_active_pitchers(team_id)
    if not pitchers:
        return {}

    starter_ip, starter_er = 0.0, 0.0
    bullpen_ip, bullpen_er = 0.0, 0.0

    for p in pitchers:
        pid = p.get("person", {}).get("id")
        if not pid:
            continue
        stat = _fetch_pitcher_season_stats(pid, season)
        if not stat:
            continue

        games = float(stat.get("gamesPlayed", 0) or 0)
        starts = float(stat.get("gamesStarted", 0) or 0)
        ip_str = stat.get("inningsPitched", "0.0")
        try:
            # MLB innings-pitched strings use .1/.2 for partial innings
            whole, _, frac = str(ip_str).partition(".")
            ip = float(whole) + (float(frac) / 3 if frac else 0.0)
        except ValueError:
            ip = 0.0
        era = float(stat.get("era", LEAGUE_AVG_ERA) or LEAGUE_AVG_ERA)
        er = era * ip / 9.0  # back out earned runs from ERA and IP

        if games > 0 and (starts / games) >= _STARTER_MIN_GS_RATIO:
            starter_ip += ip
            starter_er += er
        else:
            bullpen_ip += ip
            bullpen_er += er

    if starter_ip < 20 or bullpen_ip < 20:  # sample-size guard
        return {}

    starter_era = round(starter_er * 9 / starter_ip, 2)
    bullpen_era = round(bullpen_er * 9 / bullpen_ip, 2)
    gap = round(bullpen_era - starter_era, 2)  # positive = bullpen worse than starters

    if gap >= 0.75:
        signal, note = "FADE_FULL_GAME", "Elite starters, weak bullpen — bet F5, fade full game"
    elif gap <= -0.75:
        signal, note = "BET_FULL_GAME", "Weak starters, elite bullpen — fade F5, bet full game"
    elif abs(gap) >= 0.35:
        signal, note = "SLIGHT_LEAN", "Moderate starter/bullpen gap — mild directional value"
    else:
        signal, note = "NEUTRAL", "Starter and bullpen quality in line — no signal from this split"

    return {
        "starter_era": starter_era,
        "bullpen_era": bullpen_era,
        "gap": gap,
        "signal": signal,
        "note": note,
    }


def team_starter_bullpen_split_by_name(team_name: str, season: int = None) -> dict:
    """Convenience wrapper: resolve team name to team_id, then compute the split."""
    team_id = _get_mlb_team_id(team_name)
    if not team_id:
        return {}
    result = team_starter_bullpen_split(team_id, season)
    if result:
        result["team"] = team_name
    return result
