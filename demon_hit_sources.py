"""Reuse existing provider connections, without mixing averages and game logs."""
from datetime import date
import re

import streamlit as st

from demon_hit_analysis import assess_hits


_BASKETBALL = {
    "pts": ("pts",), "points": ("pts",), "reb": ("reb",), "rebounds": ("reb",),
    "ast": ("ast",), "assists": ("ast",), "pra": ("pts", "reb", "ast"),
    "ptsrebast": ("pts", "reb", "ast"), "pointsreboundsassists": ("pts", "reb", "ast"),
    "ptsreb": ("pts", "reb"), "pointsrebounds": ("pts", "reb"),
    "ptsast": ("pts", "ast"), "pointsassists": ("pts", "ast"),
    "rebast": ("reb", "ast"), "reboundsassists": ("reb", "ast"),
    "3pm": ("fg3m",), "3ptm": ("fg3m",), "3pointersmade": ("fg3m",),
    "3ptmade": ("fg3m",), "threes": ("fg3m",), "stl": ("stl",),
    "steals": ("stl",), "blk": ("blk",), "blocks": ("blk",),
    "turnovers": ("turnover",), "to": ("turnover",),
}
_NHL = {"pts": ("PTS",), "points": ("PTS",), "goals": ("G",), "g": ("G",),
        "assists": ("A",), "a": ("A",), "sog": ("SOG",), "shotsongoal": ("SOG",)}
_MLB = {"hits": ("H",), "h": ("H",), "hr": ("HR",), "homeruns": ("HR",),
        "rbi": ("RBI",), "rbis": ("RBI",), "runs": ("R",), "r": ("R",),
        "walks": ("BB",), "bb": ("BB",), "hitsrunsrbis": ("H", "R", "RBI")}


@st.cache_data(ttl=1800, show_spinner=False)
def _logs_for_player(_core, player, sport, day):
    from demon_nfl_logs import fetch_nfl_logs
    if sport == "NBA":
        return _core.fetch_player_game_logs(player, last_n=30)
    if sport == "WNBA":
        return _core.fetch_wnba_player_game_logs(player, last_n=100)
    if sport == "NHL":
        return _core.fetch_nhl_player_game_logs(player, last_n=100)
    if sport == "MLB":
        return _core.fetch_mlb_player_game_logs(player, last_n=100)
    return fetch_nfl_logs(_core, player, date.fromisoformat(day).year)


def assess_player(core, player, stat, line, sport, side="OVER"):
    """Fetch only for supported stat/league combinations; report failures openly."""
    from demon_nfl_logs import NFL_STATS

    normalized = re.sub(r"[^a-z0-9]", "", stat.lower())
    mapping = _BASKETBALL if sport in ("NBA", "WNBA") else (
        _NHL if sport == "NHL" else _MLB if sport == "MLB" else NFL_STATS if sport == "NFL" else {}
    )
    keys = mapping.get(normalized)
    if not keys:
        result = assess_hits([], line, "_value", side=side)
        result["warnings"] = ["This sport/stat has no verified game-log mapping; left ungraded."]
        return result
    try:
        logs = _logs_for_player(core, player, sport, date.today().isoformat())
        prepared = []
        for original in logs or []:
            row = dict(original)
            # Existing WNBA logs use uppercase box-score keys.
            if sport == "WNBA":
                row.update({key.lower(): value for key, value in original.items()})
            if all(row.get(key) is not None for key in keys):
                try:
                    row["_value"] = sum(float(row[key]) for key in keys)
                except (ValueError, TypeError):
                    continue
                prepared.append(row)
        opportunity = {"NBA": "min", "WNBA": "min", "NHL": "TOI", "MLB": "PA"}.get(sport)
        return assess_hits(prepared, line, "_value", side=side, opportunity_key=opportunity)
    except Exception as exc:
        result = assess_hits([], line, "_value", side=side)
        result["warnings"] = [f"Game-log lookup failed ({type(exc).__name__}); left ungraded."]
        return result
