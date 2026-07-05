"""
monthly_park_factors.py — Monthly MLB park factors, computed from real
game-level data via the official MLB Stats API (no FanGraphs dependency,
no ToS conflict).

Endpoint (confirmed real, single call covers an entire season):
    statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=...&endDate=...
        &hydrate=linescore,venue&gameType=R

Confirmed real fields used: dates[].games[].teams.home.score,
teams.away.score, venue.name, gameDate, status.abstractGameState
(only "Final" games are counted).

Method: for each (venue, month), average total runs per game. Compare to
the league-wide average total runs per game for that same month (removes
month-to-month seasonal scoring drift — April is colder/lower-scoring
league-wide than July, so comparing a park's April to the SAME month's
league average isolates the park's own effect rather than the season's
general scoring trend). Park factor = venue_month_avg / league_month_avg.

This computes the actual numbers rather than reusing DeepSeek's invented
0.95/1.35 Coors figures — output reflects whatever the real data shows.

Public API
----------
compute_monthly_park_factors(season=None) -> dict
    {venue_name: {month: park_factor}}
get_park_factor(venue_name, month, season=None) -> float or None
"""
import requests
from datetime import date
from collections import defaultdict

_CACHE = {}  # season -> {venue: {month: factor}}


def _fetch_season_schedule(season: int) -> list:
    """One call covers the whole regular season — confirmed real pattern."""
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&startDate={season}-03-01&endDate={season}-11-15"
        "&hydrate=linescore,venue&gameType=R"
    )
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        return []
    return resp.json().get("dates", [])


def compute_monthly_park_factors(season: int = None) -> dict:
    """
    Returns {venue_name: {month_int: park_factor}}. park_factor > 1.0 means
    that park plays hitter-friendly relative to league average that month;
    < 1.0 means pitcher-friendly. Computed fresh from real completed games,
    not hardcoded.
    """
    season = season or date.today().year
    if season in _CACHE:
        return _CACHE[season]

    dates = _fetch_season_schedule(season)
    if not dates:
        return {}

    # venue_month_runs[venue][month] = [total_runs, game_count]
    venue_month_runs = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    league_month_runs = defaultdict(lambda: [0, 0])  # month -> [total_runs, game_count]

    for d in dates:
        for g in d.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            home_score = g.get("teams", {}).get("home", {}).get("score")
            away_score = g.get("teams", {}).get("away", {}).get("score")
            venue = g.get("venue", {}).get("name")
            game_date = g.get("gameDate", "")
            if home_score is None or away_score is None or not venue or not game_date:
                continue

            try:
                month = int(game_date[5:7])
            except (ValueError, IndexError):
                continue

            total_runs = home_score + away_score
            venue_month_runs[venue][month][0] += total_runs
            venue_month_runs[venue][month][1] += 1
            league_month_runs[month][0] += total_runs
            league_month_runs[month][1] += 1

    league_month_avg = {
        m: (runs / games) for m, (runs, games) in league_month_runs.items() if games > 0
    }

    result = {}
    for venue, month_data in venue_month_runs.items():
        result[venue] = {}
        for month, (runs, games) in month_data.items():
            if games < 3 or month not in league_month_avg or league_month_avg[month] == 0:
                continue  # sample-size guard
            venue_avg = runs / games
            result[venue][month] = round(venue_avg / league_month_avg[month], 3)

    _CACHE[season] = result
    return result


def get_park_factor(venue_name: str, month: int, season: int = None) -> float:
    """Convenience lookup. Returns None if insufficient data for that venue/month."""
    factors = compute_monthly_park_factors(season)
    venue_data = factors.get(venue_name)
    if not venue_data:
        # fuzzy fallback: substring match on venue name
        for v, data in factors.items():
            if venue_name.lower() in v.lower() or v.lower() in venue_name.lower():
                venue_data = data
                break
    return (venue_data or {}).get(month)
