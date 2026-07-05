"""
nba_pace_mismatch.py — Pace mismatch scorer for NBA totals.

Consumes NBA pace data captured by the browser-side harvester
(window._nbaPace, scraped from nba.com/stats/teams/advanced, table class
Crom_table__PJugT, PACE column) and pushed to the shared Gist — same
pattern as every other browser harvester in this repo (Caesars, FanDuel,
Scanbet, etc.). This module does not scrape anything itself; it reads
whatever the browser harvester already pushed.

Logic: pace isn't just additive for totals — which team is favored
determines who controls tempo. A fast team that's favored dictates pace
(their up-tempo style prevails more often) more than a fast team that's
an underdog (they're often forced to play the favorite's tempo). This
module surfaces the mismatch AND which side likely controls tempo, not
just "both teams are fast, bet the over."

Public API
----------
load_pace_data() -> dict {team_name: pace_value}
classify_pace_tier(team_name, pace_data=None) -> "TOP5" | "BOTTOM5" | "MID"
score_pace_mismatch(home_team, away_team, favored_side=None, pace_data=None) -> dict
"""
from market_microstructure import _read_gist_file

_GIST_FILENAME = "betcouncil_nba_pace.json"


def load_pace_data() -> dict:
    """
    Read the browser-harvested pace table from Gist. Returns
    {team_name: pace_value}, or {} if the harvester hasn't run yet
    (cold start — same as any other browser harvester before first run).
    """
    data = _read_gist_file(_GIST_FILENAME)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        # tolerate a list-of-rows shape too: [{"team": ..., "pace": ...}, ...]
        return {row.get("team"): row.get("pace") for row in data if row.get("team")}
    return {}


def classify_pace_tier(team_name: str, pace_data: dict = None) -> str:
    """Return TOP5 / BOTTOM5 / MID based on current league pace ranking."""
    pace_data = pace_data if pace_data is not None else load_pace_data()
    if not pace_data or team_name not in pace_data:
        return "UNKNOWN"

    ranked = sorted(pace_data.items(), key=lambda kv: kv[1], reverse=True)
    ranked_names = [name for name, _ in ranked]
    idx = ranked_names.index(team_name)

    if idx < 5:
        return "TOP5"
    if idx >= len(ranked_names) - 5:
        return "BOTTOM5"
    return "MID"


def score_pace_mismatch(home_team: str, away_team: str, favored_side: str = None,
                         pace_data: dict = None) -> dict:
    """
    favored_side: "HOME" or "AWAY" if known (e.g. from your existing
    moneyline favorite detection) — sharpens the total-direction call.
    If not provided, still returns the raw mismatch without a directional lean.
    """
    pace_data = pace_data if pace_data is not None else load_pace_data()
    if not pace_data:
        return {}

    home_tier = classify_pace_tier(home_team, pace_data)
    away_tier = classify_pace_tier(away_team, pace_data)
    home_pace = pace_data.get(home_team)
    away_pace = pace_data.get(away_team)

    if home_pace is None or away_pace is None:
        return {}

    is_mismatch = {"TOP5", "BOTTOM5"} == {home_tier, away_tier}
    if not is_mismatch:
        return {
            "home_tier": home_tier, "away_tier": away_tier,
            "home_pace": home_pace, "away_pace": away_pace,
            "is_mismatch": False,
            "note": "No top5-vs-bottom5 pace mismatch this matchup",
        }

    fast_team = home_team if home_tier == "TOP5" else away_team
    slow_team = away_team if home_tier == "TOP5" else home_team

    lean = None
    note = f"Pace mismatch: {fast_team} (fast) vs {slow_team} (slow)"
    if favored_side:
        favored_team = home_team if favored_side.upper() == "HOME" else away_team
        if favored_team == fast_team:
            lean = "OVER"
            note += " — fast team favored, they dictate tempo → lean OVER"
        else:
            lean = "UNDER"
            note += " — slow team favored, they dictate tempo → lean UNDER"

    return {
        "home_tier": home_tier, "away_tier": away_tier,
        "home_pace": home_pace, "away_pace": away_pace,
        "is_mismatch": True,
        "fast_team": fast_team, "slow_team": slow_team,
        "total_lean": lean,
        "note": note,
    }
