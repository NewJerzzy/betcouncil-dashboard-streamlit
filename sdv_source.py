"""
BetCouncil sportsdataverse integration — sdv_source.py

Wraps the sportsdataverse package (ESPN + nflverse + MLB Stats API/Statcast +
NHL API/EDGE + NBA stats) as cached, safe-fallback fetch functions usable
across every sport the model covers. Import via:

    from sdv_source import *

All functions:
  - return polars/pandas DataFrames converted to list-of-dict (JSON-safe,
    consistent with the rest of the fetchers.py / bc_utils.py data shape)
  - never raise: on any failure they log via _logger and return [] / {}
  - are wrapped in @st.cache_data so repeated calls in a Streamlit rerun
    don't re-hit ESPN/nflverse/MLB/NHL endpoints
"""
import logging
_logger = logging.getLogger("betcouncil")

import streamlit as st

try:
    import sportsdataverse.nfl as _sdv_nfl
    import sportsdataverse.nba as _sdv_nba
    import sportsdataverse.mlb as _sdv_mlb
    import sportsdataverse.nhl as _sdv_nhl
    import sportsdataverse.wnba as _sdv_wnba
    _SDV_AVAILABLE = True
except ImportError as _e:
    _logger.warning(f"[sdv_source] sportsdataverse not installed: {_e}")
    _SDV_AVAILABLE = False


def _to_records(df):
    """Normalize a polars/pandas DataFrame (or None) to list[dict]."""
    if df is None:
        return []
    try:
        if hasattr(df, "to_dicts"):  # polars
            return df.to_dicts()
        if hasattr(df, "to_dict"):   # pandas
            return df.to_dict(orient="records")
    except Exception as e:
        _logger.warning(f"[sdv_source] _to_records failed: {e}")
    return []


def _safe_call(fn, *args, **kwargs):
    if not _SDV_AVAILABLE:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        _logger.warning(f"[sdv_source] {getattr(fn, '__name__', fn)} failed: {e}")
        return None


# =============================================================================
# NFL
# =============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def sdv_nfl_injuries(season: int):
    """Structured NFL injury report — feeds injury_performance.json signal."""
    df = _safe_call(_sdv_nfl.load_nfl_injuries, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=86400, show_spinner=False)
def sdv_nfl_rosters(season: int):
    """Full team rosters — seeds the NFL player database build."""
    df = _safe_call(_sdv_nfl.load_nfl_rosters, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=86400, show_spinner=False)
def sdv_nfl_players():
    """Master player table (IDs, names, positions, crosswalk) — NFL player DB."""
    df = _safe_call(_sdv_nfl.load_nfl_players)
    return _to_records(df)


@st.cache_data(ttl=86400, show_spinner=False)
def sdv_nfl_player_stats(season: int, season_type: str = "REG"):
    """Weekly/season player stat lines — feeds WMA / rolling-average signals."""
    df = _safe_call(_sdv_nfl.load_nfl_player_stats, seasons=[season], seasontypes=[season_type])
    return _to_records(df)


@st.cache_data(ttl=86400, show_spinner=False)
def sdv_nfl_combine():
    """Combine measurables — supplemental NFL player DB fields."""
    df = _safe_call(_sdv_nfl.load_nfl_combine)
    return _to_records(df)


@st.cache_data(ttl=3600, show_spinner=False)
def sdv_nfl_snap_counts(season: int):
    """Snap counts — usage-rate input for prop signals."""
    df = _safe_call(_sdv_nfl.load_nfl_snap_counts, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=1800, show_spinner=False)
def sdv_nfl_scoreboard_espn(dates: str):
    """Live/near-live ESPN scoreboard fallback (works even when nflverse is
    unreachable, since it hits ESPN directly rather than raw.githubusercontent.com)."""
    df = _safe_call(_sdv_nfl.espn_nfl_scoreboard, dates=dates)
    return _to_records(df)


# =============================================================================
# NBA
# =============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def sdv_nba_rosters(season: int):
    df = _safe_call(_sdv_nba.load_nba_rosters, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=3600, show_spinner=False)
def sdv_nba_player_boxscore(game_id: str):
    df = _safe_call(_sdv_nba.load_nba_player_boxscore, game_id=game_id)
    return _to_records(df)


@st.cache_data(ttl=86400, show_spinner=False)
def sdv_nba_player_season_stats(season: int):
    """Season-level per-player stats — feeds player prop rolling averages."""
    df = _safe_call(_sdv_nba.load_nba_player_season_stats, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=1800, show_spinner=False)
def sdv_nba_scoreboard_espn(dates: str):
    df = _safe_call(_sdv_nba.espn_nba_scoreboard, dates=dates)
    return _to_records(df)


# =============================================================================
# MLB (incl. Statcast — the deepest surface in the package)
# =============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def sdv_mlb_rosters(season: int):
    df = _safe_call(_sdv_mlb.load_mlb_rosters, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=3600, show_spinner=False)
def sdv_mlb_statcast_player(player_id: int, season: int):
    """Per-player Statcast pitch-level data — hardens fetch_mlb_rolling_averages."""
    df = _safe_call(_sdv_mlb.mlb_statcast_player, player_id=player_id, season=season)
    return _to_records(df)


@st.cache_data(ttl=3600, show_spinner=False)
def sdv_mlb_statcast_leaderboard_exit_velocity_barrels(season: int):
    """Exit velocity / barrel-rate leaderboard — power-signal input."""
    df = _safe_call(_sdv_mlb.mlb_statcast_leaderboard_exit_velocity_barrels, season=season)
    return _to_records(df)


@st.cache_data(ttl=1800, show_spinner=False)
def sdv_mlb_scoreboard_espn(dates: str):
    df = _safe_call(_sdv_mlb.espn_mlb_scoreboard, dates=dates)
    return _to_records(df)


# =============================================================================
# NHL (incl. NHL EDGE player-tracking)
# =============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def sdv_nhl_rosters(season: int):
    df = _safe_call(_sdv_nhl.load_nhl_rosters, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=3600, show_spinner=False)
def sdv_nhl_skater_boxscores(season: int):
    df = _safe_call(_sdv_nhl.load_nhl_skater_boxscores, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=3600, show_spinner=False)
def sdv_nhl_edge_skater_landing(player_id: int, season: int):
    """NHL EDGE tracking data (skating speed/distance) — no equivalent elsewhere in stack."""
    data = _safe_call(_sdv_nhl.nhl_edge_skater_landing, player_id=player_id, season=season)
    return data if data is not None else {}


@st.cache_data(ttl=1800, show_spinner=False)
def sdv_nhl_scoreboard_espn(dates: str):
    df = _safe_call(_sdv_nhl.espn_nhl_scoreboard, dates=dates)
    return _to_records(df)


# =============================================================================
# WNBA
# =============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def sdv_wnba_rosters(season: int):
    df = _safe_call(_sdv_wnba.load_wnba_rosters, seasons=[season])
    return _to_records(df)


@st.cache_data(ttl=86400, show_spinner=False)
def sdv_wnba_player_season_stats(season: int):
    df = _safe_call(_sdv_wnba.load_wnba_player_season_stats, seasons=[season])
    return _to_records(df)


# =============================================================================
# Sidebar freshness indicator helper (matches existing 25-source pattern)
# =============================================================================

def sdv_source_status() -> dict:
    """Returns availability status for the sidebar freshness indicator,
    consistent with the existing 6-tier / 25-source harvester status pattern."""
    return {
        "name": "SportsDataverse",
        "available": _SDV_AVAILABLE,
        "covers": ["NFL", "NBA", "MLB", "NHL", "WNBA"],
        "type": "stats/players/injuries (NOT odds)",
    }
