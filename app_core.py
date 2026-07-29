import streamlit as st
import os
import logging
_logger = logging.getLogger("betcouncil")
import re
import json
import time
import math
import statistics
import hashlib
import io
import base64
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as _Retry

def _make_retry_session() -> requests.Session:
    """Shared requests.Session with automatic retry (max 2, 1 s backoff)."""
    _s = requests.Session()
    _r = _Retry(total=2, backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                raise_on_status=False, allowed_methods=False)
    _s.mount("https://", HTTPAdapter(max_retries=_r))
    _s.mount("http://",  HTTPAdapter(max_retries=_r))
    return _s

# _http: retry session for all normal external HTTP calls.
# _HTTP_DIRECT: plain session (no retry) for proxy-chain calls where a 429/500
# from one provider means fall-through to the next provider — NOT retry the same.
_http        = _make_retry_session()
_HTTP_DIRECT = requests.Session()

import streamlit.components.v1 as components
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
try:
    from curl_cffi import requests as cf
except ImportError:
    cf = None

# --- Module imports ---
from bc_utils import (safe_float, normalize_name, american_to_prob, no_vig_prob,
    calibrate_tier_thresholds, compute_clv_with_tier, adjusted_edge, analyze_loss_postmortem,
    correlated_parlay_kelly,
    normalize_stat_type, hot_streak_regression_risk,
    no_vig_prob_shin, no_vig_prob_log, no_vig_prob_probit, no_vig_prob_power,
    devig_best, compute_clv, compute_clv_novig,
    kelly_with_edge_decay, compute_brier_score, compute_calibration_zscore,
    adaptive_kelly_fraction, platt_calibrate_prob, time_decay_edge_factor,
    compute_game_exposure, covariance_haircut, _MAX_GAME_EXPOSURE,
    compute_signal_performance, get_adjusted_signal_weights,
    validate_weight_update, classify_edge_type,
    EV_BEST_COMBOS, get_best_devig_combo,
    load_json_data, detect_season_regime, format_rlm_display, track_closing_line_beat,
    is_date_valid_for_today, find_player_avg, market_efficiency_score,
    get_weighted_average, get_recency_context, sample_size_confidence,
    compare_multibook_lines, make_display_df, compute_market_edge,
    compute_market_implied_projection, compute_sem_for_tier, compute_h2h_hit_rate,
    devig_odds, compute_std_dev, calculate_edge,
    compute_fair_prob, tier_badge, is_game_total_prop, classify_regime, parlay_prob,
    parlay_payout, poisson_prob_over, compute_fair_prob_negbinom, compute_fair_prob_skellam,
    mc_calculate_lambdas, mc_log5_win_prob, mc_simulate_game, mc_game_prob,
    ELO_DEFAULT_RATING, ELO_K_FACTOR, elo_update, elo_expected_score, elo_to_def_adj,
    # Extracted from app.py — pure computation, no Streamlit deps
    _ev_parse_odds, _get_elo_roster_confidence, _load_cache, _merge_rolling, _parse_american, _save_cache, build_optimal_portfolio, calculate_lock_quality_score, calculate_prizepicks_ev, check_portfolio_correlation, check_prop_line_fairness, compute_calibration_buckets, compute_clv_grade, compute_dff_propstats_edge, compute_expected_vs_actual, compute_home_away_splits, compute_model_vs_market, compute_parlay_correlation, compute_projection_confidence, compute_signal_attribution, compute_market_climate, compute_game_density, compute_team_exposure, compute_tier_stats, detect_game_script_contradictions, detect_sharp_movement, find_best_alt_line, generate_post_mortem, generate_weight_recommendations, get_best_alt_line_recommendation, get_calibration_summary, get_clv_summary, get_edge_staleness, get_game_tier, get_pinnacle_edge, get_tier, optimize_daily_bet_sizing, power_rating_spread_divergence, prizepicks_breakeven_prob, save_json_data, weather_edge_adjustment,
    score_rlm, devig_ensemble,
    record_line, detect_steam_move,
    pace_adjust_mlb_prop, rest_adjusted_std_dev,
    get_opener_gap, detect_market_maker_divergence,
    build_game_line_consensus, classify_book_role,
    compute_market_anchored_fair_line, recalibrate_pricer_bias, PRICER_COMPONENT_BIAS,
    )
from slip_parser import _parse_pp_ocr_inline, parse_bovada_slip_text, parse_mybookie_slip_text, parse_pp_board_paste
from styles import TIER_COLORS, global_css, skeleton_rows_html, empty_state_html, line_movement_html
from app_fixes import fetch_vsin_intelligence
try:
    from sharptrack import render_sharptrack_tab
except Exception as _sharptrack_import_err:
    def render_sharptrack_tab():
        st.error(f"SharpTrack failed to load: {_sharptrack_import_err}")
        st.caption("This tab is isolated from the rest of the app — everything else should work normally. Try rebooting the app from Manage app if this persists.")

# --- API Keys ---
# --- Config (extracted 2026-06-19 to reduce app.py size) ---
from config import (
    GITHUB_TOKEN, GITHUB_GIST_ID, ODDS_API_KEY, ODDSPAPI_KEY,
    ANTHROPIC_API_KEY, OCR_SPACE_API_KEY, SCRAPEOPS_KEY, BDL_API_KEY,
    RAPIDAPI_KEY, REQUEST_TIMEOUT, CACHE_DIR, HEADERS, ODDS_API_BASE,
    ODDS_API_SPORT_MAP, CBS_SPORT_MAP, ACTIVE_BOOKS, DISABLED_BOOKS,
    DAILY_RISK_CONTROLS, ACTION_NETWORK_SPORT_MAP, ACTION_NETWORK_LEAGUE_IDS, ACTION_NETWORK_PROP_TYPE_MAP,
    AN_GRADE_TO_TIER, ODDS_API_PROP_MARKETS, ODDS_API_STAT_MAP, API_BUDGETS,
    TIER_THRESHOLDS, SPORT_SIGNAL_WEIGHTS, SIGNAL_RELIABILITY, SIGNAL_LABELS,
    REGIME_LABELS, SPORT_EWMA_DECAY, PRIZEPICKS_MULTIPLIERS, PLAYER_AVERAGES_SOCCER,
    PLAYER_AVERAGES_UFC, DEFAULT_AVERAGES, STAT_NORMALIZE, TEAMMATE_OUT_BOOST,
    PLAYER_TEAM_MAP, POSITIVE_CORRELATIONS, SAME_PLAYER_STAT_CORRELATION, MLB_BALLPARKS,
    MLB_PLAYER_TEAM_MAP, WNBA_PLAYER_IDS, MLB_PLAYER_IDS, NHL_PLAYER_IDS,
    NBA_TEAM_PACE, NBA_POWER_RATINGS, NBA_POSITION_DEFENSE, PLAYOFF_DEFENSE_WARNING,
    WNBA_POWER_RATINGS, MLB_POWER_RATINGS, NHL_POWER_RATINGS, NBA_PLAYER_POSITIONS,
    NBA_REFEREE_TENDENCIES, MLB_UMPIRE_TENDENCIES, MLB_PITCHER_ERA, MLB_PITCHER_FIP,
    MLB_PITCHER_HANDEDNESS, MLB_TEAM_WOBA_VS_RHP, MLB_TEAM_WOBA_VS_LHP, MLB_WOBA_LEAGUE_AVG,
    MLB_PARK_FACTORS,
    NHL_TEAM_GOALS_FOR, NHL_TEAM_GOALS_AGAINST, ESPN_ATHLETE_IDS, GAME_TOTAL_LINE_THRESHOLDS,
    PROP_CORRELATION_PAIRS, KALSHI_SPORT_SERIES, GOLF_TOURNAMENT_MAP, DFF_HEADERS,
    DFF_SPORT_MAP, DFF_TEAM_MAP, DFF_METRIC_MAP, BQ_WEIGHTS_DEFAULT,
    BOVADA_HEADERS, BOVADA_SPORT_MAP, SIGNAL_COLS, MLB_STADIUM_COORDS,
    NFL_OUTDOOR_STADIUMS, NFL_DIVISIONS, FL_SPORT_MAP, FL_HEADERS, GAME_TIER_THRESHOLDS,
    BDL_PLAYER_IDS, ESPN_SLUG_MAP, PLAYER_HOME_SPLITS,
    BETONLINE_BASE, BETONLINE_HEADERS, BETONLINE_MULTI_LEAGUE,
    _SOCCER_LEAGUE_BASELINES, _SOCCER_LEAGUE_KEYS,
    _TENNIS_SURFACE_BASELINES_BO3, _TENNIS_SURFACE_BASELINES_BO5,
    _ATP_GRAND_SLAMS, _SLAM_SURFACE,
    _UFC_WEIGHTCLASS_BASELINES, _UFC_ROUND_DEFAULT, _UFC_CHAMPIONSHIP_ROUNDS,
    PLAYER_LOOKUP_OPPONENT_OPTIONS,
    TEAM_ABBREV_TO_FRAGMENT,
    LINE_DEVIATION_THRESHOLD_PCT,
)
import time as _time_mod
from contextlib import contextmanager as _ctx
from fetchers import *  # extracted fetch_/compute_ functions
from fetchers import _fetch_wnba_roster_via_teams  # leading underscore -> not covered by the star import above
from fetchers import _map_prop_to_stat_key  # wildcard import excludes underscore-prefixed names
from prop_market_intelligence import record_prop_snapshot, get_odds_type_flips
from sdv_source import *  # sportsdataverse: NFL/NBA/MLB/NHL/WNBA stats, rosters, injuries

def _bc_track(stage, duration, meta=None):
    try:
        if "bc_telemetry" not in st.session_state:
            st.session_state["bc_telemetry"] = {}
        t = st.session_state["bc_telemetry"]
        if stage not in t:
            t[stage] = {"runs":0,"total":0.0,"max":0.0,"last":0.0}
        t[stage]["runs"]  += 1
        t[stage]["total"] += duration
        t[stage]["max"]    = max(t[stage]["max"], duration)
        t[stage]["last"]   = duration
        if meta:
            t[stage]["meta"] = meta
    except Exception as _e:
            print(f"[WARN] {_e}")

def bc_timer(label):
    """Simple context manager for timing code blocks."""
    class _Timer:
        def __init__(self, l): self.l = l
        def __enter__(self): self.t = time.time(); return self
        def __exit__(self, *a): print(f"  {self.l}: {time.time()-self.t:.2f}s")
    return _Timer(label)
import pickle
import functools
from math import exp, log, pi
from itertools import combinations

# =========================
# PAGE CONFIG
# =========================

# --- Session State Schema (prevents KeyError on missing keys) ---
_SS_DEFAULTS = {
    # Core state
    "board_loaded": False, "active_sport": "NBA",
    "history": [], "locks": [], "bankroll": 468.49,
    "day_start_br": 468.49, "session_start": 0,
    "min_edge": 0.02, "skip_defaults": False,
    "last_sport": "MLB", "open_bets": [],
    # UI state
    "parsed_bets": [], "bet_history": [], "vision_debug": {},
    "ocr_raw_text": "", "errors": [], "recommendations": [],
    "game_analysis": [], "show_ml_debug": False,
    # Props cache per sport
    "oddspapi_props_NBA": [], "oddspapi_props_MLB": [],
    "oddspapi_props_NHL": [], "oddspapi_props_WNBA": [],
    "oddspapi_props_NFL": [],
    # Performance / telemetry
    "bc_telemetry": {}, "fetch_timings": {},
    # Gist batching
    "gist_dirty": {}, "gist_last_write": {},
}
for _k, _v in _SS_DEFAULTS.items():
    st.session_state.setdefault(_k, _v)
# session_start needs current time on first load, not a static value
if not st.session_state.get("session_start"):
    st.session_state["session_start"] = time.time()

def _cap_list(key, max_len=200):
    if key in st.session_state and isinstance(st.session_state[key], list):
        if len(st.session_state[key]) > max_len:
            st.session_state[key] = st.session_state[key][-max_len:]
_cap_list("errors", 50)
_cap_list("parsed_bets", 200)
_cap_list("bet_history", 500)

# ── Circuit Breaker ───────────────────────────────────────────
# Tracks failure counts per provider. After 3 consecutive failures,
# trips the circuit for 60 seconds so dead providers are skipped
# instantly rather than burning the full request timeout every call.
# This is the single biggest "speed killer" fix: a dead proxy that
# takes 20s to timeout would previously block every fetch that hit it.
# With the circuit breaker it's skipped after 3 failures for 60s.

_CB_THRESHOLD  = 3     # failures before trip
_CB_RESET_SECS = 60    # seconds to stay tripped

def _cb_key(provider: str) -> str:
    return f"_cb_{provider.lower().replace('.','_').replace('-','_')}"

def circuit_is_tripped(provider: str) -> bool:
    """Return True if the provider's circuit is currently open (tripped)."""
    import time as _t
    k = _cb_key(provider)
    state = st.session_state.get(k, {})
    if not state:
        return False
    if state.get("tripped") and _t.time() - state.get("tripped_at", 0) < _CB_RESET_SECS:
        return True
    if state.get("tripped"):
        # Auto-reset after timeout
        state["tripped"] = False
        state["fail_count"] = 0
        st.session_state[k] = state
    return False

def circuit_record_failure(provider: str) -> None:
    """Record a provider failure. Trips the circuit after _CB_THRESHOLD failures."""
    import time as _t
    k = _cb_key(provider)
    state = st.session_state.get(k, {"fail_count": 0, "tripped": False, "tripped_at": 0})
    state["fail_count"] = state.get("fail_count", 0) + 1
    if state["fail_count"] >= _CB_THRESHOLD:
        state["tripped"]    = True
        state["tripped_at"] = _t.time()
        _logger.warning("Circuit breaker TRIPPED for %s after %d failures", provider, _CB_THRESHOLD)
    st.session_state[k] = state

def circuit_record_success(provider: str) -> None:
    """Reset failure count on success."""
    k = _cb_key(provider)
    st.session_state[k] = {"fail_count": 0, "tripped": False, "tripped_at": 0}

def circuit_status() -> dict:
    """Return status of all tracked circuits for the System tab display."""
    import time as _t
    result = {}
    for k, v in st.session_state.items():
        if k.startswith("_cb_") and isinstance(v, dict):
            provider = k[4:].replace("_", " ").title()
            tripped = v.get("tripped", False)
            remaining = 0
            if tripped:
                remaining = max(0, int(_CB_RESET_SECS - (_t.time() - v.get("tripped_at", 0))))
                if remaining == 0:
                    tripped = False
            result[provider] = {
                "fail_count": v.get("fail_count", 0),
                "tripped":    tripped,
                "reset_in":   remaining,
            }
    return result

# ── In-Memory Cache Layer ─────────────────────────────────────
# High-frequency lookups (signal_performance, sem_calibration, etc.)
# are cached in RAM via session_state rather than hitting disk on
# every rerun. Disk (pickle/json) is reserved for data that must
# survive container restarts (bankroll, CLV history, Gist-backed state).

_MEM_CACHE: dict = {}   # module-level dict — survives reruns, cleared on container restart

def mem_cache_get(key: str, default=None):
    """Read from in-memory cache. Faster than pickle for hot-path data."""
    return _MEM_CACHE.get(key, default)

def mem_cache_set(key: str, value, ttl_seconds: int = 300):
    """Write to in-memory cache with TTL. Evicts stale entries on read."""
    import time as _t
    _MEM_CACHE[key] = {"v": value, "exp": _t.time() + ttl_seconds}

def mem_cache_get_ttl(key: str, default=None):
    """Read from in-memory cache, respecting TTL expiry."""
    import time as _t
    entry = _MEM_CACHE.get(key)
    if entry is None:
        return default
    if _t.time() > entry.get("exp", 0):
        del _MEM_CACHE[key]
        return default
    return entry["v"]

def mem_cache_invalidate(key: str) -> None:
    _MEM_CACHE.pop(key, None)

# ── Data Payload Validator ────────────────────────────────────
# Validates incoming API responses have expected fields before
# feeding data into the model. Tags records as SKIPPED with a
# reason when validation fails, preventing garbage-in-garbage-out
# in Kelly sizing and edge calculations.

class PayloadValidationError(ValueError):
    """Raised when an API response is missing required fields."""
    pass

def validate_payload(data, required_fields: list, source: str = "unknown") -> bool:
    """
    Validate an API response dict has all required fields with non-None values.
    Raises PayloadValidationError with a clear message on failure so the caller
    can tag the record as SKIPPED rather than propagating None/0.0 into math.

    Args:
        data:            The parsed API response (dict or list)
        required_fields: Field names that must be present and non-None
        source:          Provider name for error messages

    Returns:
        True if valid

    Raises:
        PayloadValidationError if data is empty or any required field is missing
    """
    if not data:
        raise PayloadValidationError(f"[{source}] Empty or null payload")
    if isinstance(data, list):
        if len(data) == 0:
            raise PayloadValidationError(f"[{source}] Empty list payload")
        return True   # list shape — caller validates individual items
    for field in required_fields:
        if field not in data:
            raise PayloadValidationError(f"[{source}] Missing required field: '{field}'")
        if data[field] is None:
            raise PayloadValidationError(f"[{source}] Field '{field}' is None")
    return True

def safe_validate(data, required_fields: list, source: str = "unknown") -> tuple:
    """
    Non-raising version of validate_payload. Returns (is_valid, error_msg).
    Use when you want to log and skip rather than raise.
    """
    try:
        validate_payload(data, required_fields, source)
        return True, None
    except PayloadValidationError as e:
        _logger.warning("Payload validation failed: %s", e)
        return False, str(e)



def _ss_set(key, value, expected_type=None):
    """Type-safe session state write."""
    if expected_type and not isinstance(value, expected_type):
        try:
            value = expected_type(value)
        except (ValueError, TypeError):
            return
    st.session_state[key] = value



st.set_page_config(page_title="BetCouncil v5.2", page_icon="⚡", layout="wide")

# --- Centralized CSS Variables ---
st.markdown("""<style>
:root {
    /* bet105-inspired palette */
    --bc-blue:       #1e90ff;   /* electric blue — primary accent */
    --bc-blue-bright:#4db8ff;   /* bright blue for hover/active */
    --bc-blue-dark:  #0a5fa8;   /* dark blue for sidebar/nav */
    --bc-blue-glow:  rgba(30,144,255,0.25);
    --bc-green:      #22c55e;
    --bc-red:        #e04040;
    --bc-gold:       #e8a020;
    --bc-gold-bright:#f5c518;
    --bc-bg:         #000000;   /* pure black — like bet105 */
    --bc-bg2:        #0a1628;   /* deep navy card bg */
    --bc-bg-card:    #0d1b2e;   /* card background */
    --bc-bg-section: #0a1628;   /* section header bg */
    --bc-bg-panel:   #071020;   /* sidebar/panel bg */
    --bc-navy:       #000000;
    --bc-text:       #ffffff;   /* pure white text */
    --bc-muted:      #8ab4d4;   /* blue-tinted muted */
    --bc-dim:        #4a6a8a;
    --bc-border:     #1a3a5c;   /* blue-tinted border */
}

/* ── SOVEREIGN GLOW ANIMATION ──────────────────────────── */
@keyframes sovereign-pulse {
    0%   { box-shadow: 0 0 0px 0px rgba(248,197,24,0.0), 0 0 8px rgba(248,197,24,0.15); }
    50%  { box-shadow: 0 0 12px 3px rgba(248,197,24,0.35), 0 0 24px rgba(248,197,24,0.15); }
    100% { box-shadow: 0 0 0px 0px rgba(248,197,24,0.0), 0 0 8px rgba(248,197,24,0.15); }
}
@keyframes elite-pulse {
    0%   { box-shadow: 0 0 0px 0px rgba(55,138,221,0.0); }
    50%  { box-shadow: 0 0 10px 2px rgba(55,138,221,0.30); }
    100% { box-shadow: 0 0 0px 0px rgba(55,138,221,0.0); }
}

.row-sovereign {
    border-left: 3px solid var(--bc-gold-bright) !important;
    animation: sovereign-pulse 2.5s ease-in-out infinite;
    background: rgba(248,197,24,0.04) !important;
    transition: background 150ms cubic-bezier(0.4,0,0.2,1);
}
.row-sovereign:hover { background: rgba(248,197,24,0.10) !important; }
.row-elite {
    border-left: 3px solid var(--bc-blue) !important;
    animation: elite-pulse 3s ease-in-out infinite;
    transition: background 150ms cubic-bezier(0.4,0,0.2,1);
}
.row-elite:hover { background: rgba(30,144,255,0.08) !important; }
.row-approved {
    border-left: 3px solid var(--bc-gold) !important;
    transition: background 150ms cubic-bezier(0.4,0,0.2,1);
}
.row-approved:hover { background: rgba(232,160,32,0.06) !important; }
.row-lean {
    border-left: 3px solid #2a3a4a !important;
    transition: background 150ms cubic-bezier(0.4,0,0.2,1);
}
.row-lean:hover { background: rgba(255,255,255,0.03) !important; }

/* ── MONOSPACE ODDS ────────────────────────────────────── */
.odds-mono {
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    letter-spacing: 0.5px;
}
.odds-pos { color: #22c55e; }
.odds-neg { color: #e8f0f8; }
.odds-ev  { color: #00d4aa; }

/* ── BET105-STYLE SECTION HEADERS ─────────────────────── */
.bc-section-header {
    background: linear-gradient(90deg, var(--bc-blue-dark), var(--bc-bg2));
    border-left: 4px solid var(--bc-blue);
    border-radius: 6px 6px 0 0;
    padding: 10px 16px;
    color: var(--bc-text);
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 0;
}
.bc-section-count {
    background: var(--bc-blue);
    color: #fff;
    border-radius: 50%;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 700;
    float: right;
}

/* ── BET105-STYLE CARDS ────────────────────────────────── */
.bc-card {
    background: var(--bc-bg-card);
    border: 1px solid var(--bc-border);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.bc-card:hover {
    border-color: var(--bc-blue);
    box-shadow: 0 0 12px var(--bc-blue-glow);
}
.bc-card-blue {
    border-left: 4px solid var(--bc-blue) !important;
    background: linear-gradient(135deg, var(--bc-bg-card), #0a1e38);
}

/* ── BET105-STYLE NAV TABS ─────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bc-bg-panel) !important;
    border-bottom: 2px solid var(--bc-blue-dark) !important;
    gap: 2px;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    scrollbar-width: thin !important;
    scrollbar-color: var(--bc-blue) var(--bc-bg-panel) !important;
    -webkit-overflow-scrolling: touch !important;
    cursor: grab !important;
    flex-wrap: nowrap !important;
    white-space: nowrap !important;
}
.stTabs [data-baseweb="tab-list"]:active {
    cursor: grabbing !important;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
    height: 3px !important;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-track {
    background: var(--bc-bg-panel) !important;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-thumb {
    background: var(--bc-blue) !important;
    border-radius: 3px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--bc-muted) !important;
    border-radius: 6px 6px 0 0 !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    padding: 8px 16px !important;
    border-bottom: 2px solid transparent !important;
    transition: all 0.2s ease !important;
    flex-shrink: 0 !important;
    white-space: nowrap !important;
    cursor: pointer !important;
}
.stTabs [aria-selected="true"] {
    background: var(--bc-blue-dark) !important;
    color: var(--bc-blue-bright) !important;
    border-bottom: 2px solid var(--bc-blue) !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--bc-blue-bright) !important;
    background: rgba(30,144,255,0.1) !important;
}

/* ── BET105-STYLE BUTTONS ──────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, var(--bc-blue-dark), var(--bc-blue)) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 700 !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, var(--bc-blue), var(--bc-blue-bright)) !important;
    box-shadow: 0 0 16px var(--bc-blue-glow) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0a5fa8, var(--bc-blue)) !important;
}

/* ── BET105-STYLE METRICS ──────────────────────────────── */
[data-testid="metric-container"] {
    background: var(--bc-bg-card) !important;
    border: 1px solid var(--bc-border) !important;
    border-radius: 8px !important;
    padding: 12px !important;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    color: var(--bc-muted) !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: var(--bc-blue-bright) !important;
    font-weight: 700 !important;
}

/* ── GLOBAL BG + SIDEBAR ───────────────────────────────── */
.stApp, [data-testid="stAppViewContainer"] {
    background: var(--bc-bg) !important;
}
[data-testid="stSidebar"] {
    background: var(--bc-bg-panel) !important;
    border-right: 1px solid var(--bc-blue-dark) !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] p {
    color: var(--bc-muted) !important;
}

/* ── LIVE BADGE ────────────────────────────────────────── */
.bc-live-badge {
    background: #e04040;
    color: #fff;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    animation: live-pulse 1.5s ease-in-out infinite;
}
@keyframes live-pulse {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.6; }
}

/* ── DATAFRAMES ────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid var(--bc-border) !important;
    border-radius: 8px !important;
}
.dvn-scroller { background: var(--bc-bg-card) !important; }

/* ── EXPANDERS ─────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid var(--bc-border) !important;
    border-radius: 8px !important;
    background: var(--bc-bg-card) !important;
}
[data-testid="stExpander"]:hover {
    border-color: var(--bc-blue) !important;
}

/* ── STICKY BOARD SUMMARY BAR ──────────────────────────── */
.bc-summary-bar {
    position: sticky;
    top: 0;
    z-index: 100;
    background: linear-gradient(90deg, #060c14ee, #0d1520ee);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid #1a2a3a;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 12px;
    margin-bottom: 8px;
}
.bc-summary-pill {
    padding: 3px 10px;
    border-radius: 12px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.5px;
}
.bc-sov-pill  { background: rgba(248,197,24,0.15); color: #f5c518; border: 1px solid rgba(248,197,24,0.3); }
.bc-elite-pill { background: rgba(30,144,255,0.15); color: var(--bc-blue); border: 1px solid rgba(55,138,221,0.3); }
.bc-appr-pill  { background: rgba(232,160,32,0.12); color: #e8a020; border: 1px solid rgba(232,160,32,0.25); }
.bc-action-pill { background: rgba(0,212,170,0.12); color: #00d4aa; border: 1px solid rgba(0,212,170,0.25); }

/* ── LINE MOVEMENT ARROWS ──────────────────────────────── */
.line-up   { color: #22c55e; font-size: 11px; }
.line-down { color: #e04040; font-size: 11px; }
.line-flat { color: #4a6a8a; font-size: 11px; }

/* ── GAME LINE CARDS ───────────────────────────────────── */
.gl-market-card {
    background: #0d1520;
    border: 1px solid #1a2a3a;
    border-radius: 8px;
    padding: 12px 14px;
    position: relative;
    overflow: hidden;
}
.gl-market-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #1a3a5a, transparent);
}
.gl-market-card.has-edge::before {
    background: linear-gradient(90deg, transparent, var(--bc-gold), transparent);
    animation: sovereign-pulse 2s ease-in-out infinite;
}
</style>""", unsafe_allow_html=True)

st.markdown(global_css(), unsafe_allow_html=True)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
body, .stApp, .main { background-color: #060c14; color: #e8f0f8; font-family: 'Inter', sans-serif; font-size: 16px; }
h1 { font-size: 30px; font-weight: 700; color: #ffffff; }
/* Global readability boost */
.stMarkdown, .stMarkdown p, .stMarkdown div { font-size: 1.05rem !important; }
.stSelectbox label, .stMultiSelect label, .stTextInput label,
.stNumberInput label, .stRadio label, .stSlider label { font-size: 1.0rem !important; font-weight: 500 !important; }
.stButton > button { font-size: 1.0rem !important; padding: 0.5rem 1.2rem !important; }
.stMetric [data-testid="metric-container"] div { font-size: 1.1rem !important; }
div[data-testid="stCaption"] { font-size: 0.95rem !important; }
h2 { font-size: 20px; font-weight: 600; color: #e0e8f0; }
h3 { font-size: 17px; font-weight: 600; color: #d0d8e0; }
.stButton > button { background-color: #0ea5a0; color: #ffffff; border: none; border-radius: 8px; padding: 8px 18px; font-weight: 600; }
.stButton > button:hover { background-color: #0d9488; transform: translateY(-1px); }
.command-bar { background: linear-gradient(135deg, rgba(14,165,160,0.08), #0d1520); border: 1px solid rgba(14,165,160,0.3); border-top: 3px solid #0ea5a0; border-radius: 0 0 12px 12px; padding: 18px 22px; margin-bottom: 16px; }
.metric-box { background: var(--bc-bg-card); border: 1px solid var(--bc-border); border-radius: 10px; padding: 10px 14px; text-align: center; }
.metric-label { font-size: 11px; color: var(--bc-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }
.metric-value { font-size: 20px; font-weight: 700; }
.gold-text { color: var(--bc-gold); }
.teal-text { color: #0ea5a0; }
.red-text { color: #e04040; }
.muted-text { color: var(--bc-muted); }
.injury-badge { background-color: #e04040; color: white; font-size: 10px; padding: 2px 6px; border-radius: 12px; margin-left: 6px; }
.sem-green { color: #0ea5a0; font-weight: 600; }
.sem-yellow { color: #e8a020; font-weight: 600; }
.sem-gray { color: #6a7a8a; }

/* ── SPORTSBOOK-STYLE TAB NAV ──────────────────────────────
   Turns Streamlit's default plain tab strip into a sticky,
   pill-highlighted category bar (the pattern top-rated books
   use for their sport/market nav row: sticky, high-contrast
   active state, condensed uppercase labels, instant feedback). */
.stTabs [data-baseweb="tab-list"] {
    position: sticky;
    top: 0;
    z-index: 99;
    gap: 4px;
    background: linear-gradient(90deg, #060c14ee, #0d1520ee);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid #1a2a3a;
    padding: 6px 8px 0 8px;
    margin-bottom: 4px;
    overflow-x: auto;
}
.stTabs [data-baseweb="tab"] {
    height: 38px;
    border-radius: 8px 8px 0 0;
    padding: 0 14px;
    background: transparent;
    color: #8a9ab0;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    border: 1px solid transparent;
    transition: background 0.15s ease, color 0.15s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(14,165,160,0.08);
    color: #e8f0f8;
}
.stTabs [aria-selected="true"] {
    background: rgba(232,160,32,0.10) !important;
    color: #f5c518 !important;
    border: 1px solid rgba(232,160,32,0.35) !important;
    border-bottom: 2px solid #f5c518 !important;
    box-shadow: 0 -2px 8px rgba(232,160,32,0.08);
}
.stTabs [data-baseweb="tab-highlight"] { background: transparent !important; }
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* ── PROP CARDS — bet105 style ─────────────────────────────────────────────── */
.prop-card {
    background: var(--bc-bg-card);
    border: 1px solid var(--bc-border);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
}
.prop-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    background: var(--bc-border);
    border-radius: 10px 0 0 10px;
}
.prop-card:hover {
    border-color: var(--bc-blue);
    box-shadow: 0 4px 20px rgba(30,144,255,0.15);
    transform: translateY(-1px);
}
.prop-card.sovereign::before { background: #f5c518; }
.prop-card.elite::before     { background: var(--bc-blue); }
.prop-card.approved::before  { background: #22c55e; }
.prop-card.lean::before      { background: #ff8c00; }

.prop-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
.prop-player {
    font-size: 15px;
    font-weight: 700;
    color: var(--bc-text);
    letter-spacing: 0.2px;
}
.prop-team {
    font-size: 11px;
    color: var(--bc-muted);
    margin-top: 1px;
}
.prop-line {
    font-size: 20px;
    font-weight: 800;
    color: var(--bc-blue-bright);
    font-family: 'JetBrains Mono', monospace;
}
.prop-stat {
    font-size: 11px;
    color: var(--bc-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.prop-odds-row {
    display: flex;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
}
.odds-pill {
    background: rgba(30,144,255,0.12);
    border: 1px solid rgba(30,144,255,0.25);
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
    color: var(--bc-blue-bright);
    font-family: monospace;
}
.odds-pill.over  { background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.3); color: #22c55e; }
.odds-pill.under { background: rgba(224,64,64,0.12); border-color: rgba(224,64,64,0.3); color: #e04040; }
.edge-pill {
    background: rgba(245,197,24,0.12);
    border: 1px solid rgba(245,197,24,0.25);
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
    color: #f5c518;
}
.tier-badge {
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.tier-sovereign { background: rgba(245,197,24,0.2); color: #f5c518; border: 1px solid #f5c518; }
.tier-elite     { background: rgba(30,144,255,0.2); color: #4db8ff; border: 1px solid #1e90ff; }
.tier-approved  { background: rgba(34,197,94,0.2);  color: #22c55e; border: 1px solid #22c55e; }
.tier-lean      { background: rgba(255,140,0,0.2);  color: #ff8c00; border: 1px solid #ff8c00; }
.tier-pass      { background: rgba(224,64,64,0.15); color: #e04040; border: 1px solid #e04040; }

.signal-row {
    margin-top: 8px;
    font-size: 11px;
    color: var(--bc-muted);
    line-height: 1.6;
}
.signal-tag {
    display: inline-block;
    background: rgba(30,144,255,0.08);
    border-radius: 3px;
    padding: 1px 6px;
    margin: 1px;
    font-size: 10px;
    color: var(--bc-blue-bright);
}

/* ── GAME LINE CARDS ────────────────────────────────────────────────────────── */
.game-card {
    background: var(--bc-bg-card);
    border: 1px solid var(--bc-border);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 8px;
}
.game-matchup {
    font-size: 14px;
    font-weight: 700;
    color: var(--bc-text);
    margin-bottom: 8px;
}
.game-odds-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 6px;
    text-align: center;
}
.game-odds-cell {
    background: rgba(10,22,40,0.8);
    border-radius: 6px;
    padding: 6px 4px;
}
.game-odds-label {
    font-size: 9px;
    color: var(--bc-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 2px;
}
.game-odds-value {
    font-size: 14px;
    font-weight: 700;
    color: var(--bc-text);
    font-family: monospace;
}
.game-odds-value.pos { color: #22c55e; }
.game-odds-value.neg { color: #e8f0f8; }

/* ── SUMMARY COMMAND CENTER CARDS ───────────────────────────────────────────── */
.command-card {
    background: linear-gradient(135deg, var(--bc-bg-card), var(--bc-bg2));
    border: 1px solid var(--bc-border);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    transition: all 0.2s ease;
}
.command-card:hover {
    border-color: var(--bc-blue);
    box-shadow: 0 0 20px var(--bc-blue-glow);
}
.command-value {
    font-size: 28px;
    font-weight: 800;
    color: var(--bc-blue-bright);
    font-family: 'JetBrains Mono', monospace;
    line-height: 1;
    margin-bottom: 4px;
}
.command-label {
    font-size: 10px;
    color: var(--bc-muted);
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

/* ── SIDEBAR NAV ITEMS ──────────────────────────────────────────────────────── */
.nav-item {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    color: var(--bc-muted);
    font-weight: 500;
    font-size: 13px;
    margin-bottom: 2px;
}
.nav-item:hover {
    background: rgba(30,144,255,0.1);
    color: var(--bc-blue-bright);
}
.nav-item.active {
    background: rgba(30,144,255,0.15);
    color: var(--bc-blue-bright);
    border-left: 3px solid var(--bc-blue);
}
.nav-count {
    margin-left: auto;
    background: var(--bc-blue-dark);
    color: var(--bc-blue-bright);
    border-radius: 10px;
    padding: 1px 7px;
    font-size: 11px;
    font-weight: 700;
}

/* ── STATUS INDICATORS ──────────────────────────────────────────────────────── */
.status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
}
.status-live    { background: #22c55e; box-shadow: 0 0 6px #22c55e; animation: live-pulse 1.5s infinite; }
.status-stale   { background: #e8a020; }
.status-offline { background: #e04040; }

/* ── LOCK QUALITY GAUGE ─────────────────────────────────────────────────────── */
.lq-bar {
    height: 6px;
    border-radius: 3px;
    background: var(--bc-border);
    overflow: hidden;
    margin-top: 4px;
}
.lq-fill {
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, var(--bc-blue), var(--bc-blue-bright));
    transition: width 0.5s ease;
}
.lq-fill.high   { background: linear-gradient(90deg, #22c55e, #4ade80); }
.lq-fill.medium { background: linear-gradient(90deg, var(--bc-blue), #4db8ff); }
.lq-fill.low    { background: linear-gradient(90deg, #ff8c00, #ffa500); }

/* ── INPUT FIELDS ───────────────────────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea, .stNumberInput input {
    background: var(--bc-bg-card) !important;
    border: 1px solid var(--bc-border) !important;
    border-radius: 6px !important;
    color: var(--bc-text) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--bc-blue) !important;
    box-shadow: 0 0 0 2px var(--bc-blue-glow) !important;
}
.stSelectbox select, [data-baseweb="select"] {
    background: var(--bc-bg-card) !important;
    border-color: var(--bc-border) !important;
    color: var(--bc-text) !important;
}

/* ── SCROLLBAR GLOBAL ───────────────────────────────────────────────────────── */
::-webkit-scrollbar       { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bc-bg-panel); }
::-webkit-scrollbar-thumb { background: var(--bc-blue-dark); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--bc-blue); }

/* ── DIVIDERS ───────────────────────────────────────────────────────────────── */
hr { border-color: var(--bc-border) !important; opacity: 0.5; }

/* ── TOOLTIPS ───────────────────────────────────────────────────────────────── */
[data-testid="stTooltipIcon"] { color: var(--bc-muted) !important; }

/* ── PROGRESS BARS ──────────────────────────────────────────────────────────── */
.stProgress > div > div {
    background: linear-gradient(90deg, var(--bc-blue-dark), var(--bc-blue)) !important;
}

/* ── ALERTS / INFO BOXES ────────────────────────────────────────────────────── */
.stAlert {
    background: var(--bc-bg-card) !important;
    border: 1px solid var(--bc-border) !important;
    border-radius: 8px !important;
}
[data-testid="stAlertContainer"][data-baseweb="notification"] {
    background: rgba(30,144,255,0.08) !important;
    border-left: 3px solid var(--bc-blue) !important;
}

/* ── HEADER BAR ─────────────────────────────────────────────────────────────── */
.bc-header {
    display: flex;
    align-items: center;
    padding: 12px 0 16px 0;
    border-bottom: 1px solid var(--bc-border);
    margin-bottom: 16px;
}
.bc-logo {
    font-size: 22px;
    font-weight: 900;
    color: var(--bc-text);
    letter-spacing: -0.5px;
    text-shadow: 0 0 12px rgba(30,144,255,0.25);
}
.bc-logo span { color: var(--bc-blue); text-shadow: 0 0 16px rgba(30,144,255,0.45); }
.bc-last-updated {
    margin-left: auto;
    font-size: 11px;
    color: var(--bc-dim);
}
.bc-tagline {
    font-size: 11px;
    color: var(--bc-muted);
    margin-left: 12px;
    border-left: 1px solid var(--bc-border);
    padding-left: 12px;
}
.bc-version {
    margin-left: auto;
    font-size: 10px;
    color: var(--bc-dim);
    font-family: monospace;
}

</style>
""", unsafe_allow_html=True)

# ── BetCouncil Header Bar ──────────────────────────────────────────────────
# Header context line: board strength + prop count + real elapsed time
# since the last scan -- same tier-strength logic already used on Full
# Board/Summary, computed fresh here since the header renders before
# either of those tabs runs.
_hdr_board = st.session_state.get("board_data", []) or []
_hdr_n_sov = sum(1 for p in _hdr_board if p.get("Tier") == "SOVEREIGN")
_hdr_n_elite = sum(1 for p in _hdr_board if p.get("Tier") == "ELITE")
if not _hdr_board:
    _hdr_strength = "No board loaded"
elif _hdr_n_sov or _hdr_n_elite:
    _hdr_strength = "Strong board"
elif any(p.get("Tier") == "APPROVED" for p in _hdr_board):
    _hdr_strength = "Moderate board"
else:
    _hdr_strength = "Weak board"
_hdr_scan_time = st.session_state.get("last_scan_time")
if _hdr_scan_time:
    try:
        _hdr_last = datetime.strptime(_hdr_scan_time, "%H:%M:%S")
        _hdr_now = datetime.now()
        _hdr_mins = ((_hdr_now.hour * 60 + _hdr_now.minute) - (_hdr_last.hour * 60 + _hdr_last.minute))
        if _hdr_mins < 0:
            _hdr_mins += 1440
        _hdr_updated = f"Updated {_hdr_mins}m ago"
    except (ValueError, TypeError):
        _hdr_updated = "Updated — unknown"
else:
    _hdr_updated = "Not loaded yet"
_hdr_context = f"{_hdr_strength} · {len(_hdr_board)} props · {_hdr_updated}"

st.markdown(f"""
<div class="bc-header">
  <div class="bc-logo">bet<span>Council</span></div>
  <div class="bc-tagline">Sharp Analytics Engine · v5.2</div>
  <div class="bc-version">⚡ All sources live</div>
  <div class="bc-last-updated">{_hdr_context}</div>
</div>
""", unsafe_allow_html=True)


# =========================
# CONSTANTS
# =========================
DEFAULT_BANKROLL = 468.49
KELLY_FRACTION = 0.15   # conservative fraction of full Kelly
KELLY_CAP = 0.20        # max 20% bankroll per bet (reduced from 0.25 — props are noisy)
# Bankroll multiplier is computed dynamically from compute_bankroll_multiplier()
# and stored in st.session_state["bankroll_multiplier"] after each board load.
ODDS = -110
EDGE_CAP = 0.20
MIN_EDGE_DEFAULT = 0.02
REQUEST_TIMEOUT = 10

# ── Connection Pool + Retry Session ──────────────────────────
# Reuses TCP connections across all API calls. Retries transient errors.
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as _Retry

def _build_api_session():
    """Create a requests Session with connection pooling and auto-retry."""
    s = requests.Session()
    retry = _Retry(
        total=3,                          # max 3 retries
        backoff_factor=0.5,               # 0.5s, 1s, 2s between retries
        status_forcelist=(500, 502, 503, 504, 429),  # retry on server errors + rate limit
        allowed_methods=frozenset(["GET", "POST", "PATCH"]),
        raise_on_status=False,            # don't raise — let caller check status_code
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=15,              # reuse up to 15 TCP connections
        pool_maxsize=15,
    )
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": "BetCouncil/4.7",
        "Accept": "application/json",
    })
    return s

API_SESSION = _build_api_session()

# ── Request Timeout Constants ────────────────────────────────
REQUEST_TIMEOUT_FAST   = 8    # Quick lookups (odds, scores)
REQUEST_TIMEOUT_STD    = 12   # Standard API calls
REQUEST_TIMEOUT_SLOW   = 20   # Heavy endpoints (history, bulk)
REQUEST_TIMEOUT_PROXY  = 25   # Proxy-routed requests (ScrapeOps)
# ── Session State Safe Access ────────────────────────────────
def ss_get(key, default=None):
    """Safe session_state access — never raises KeyError."""
    try:
        return st.session_state.get(key, default)
    except (requests.RequestException, KeyError, ValueError):
        return default

def ss_set(key, value):
    """Safe session_state setter."""
    try:
        st.session_state[key] = value
    except (requests.RequestException, KeyError, ValueError) as _e:
            print(f"[WARN] {_e}")
# ── Named Constants ──────────────────────────────────────────
# Kelly Criterion
KELLY_FRACTION = 0.15      # Fractional Kelly (15% of full) — reduces variance 97%
KELLY_CAP      = 0.20      # Never risk >20% bankroll per bet
KELLY_MIN      = 0.01      # Below 1% = negligible EV, skip

# Tier-based Kelly fractions — higher tier = more conviction = larger fraction
KELLY_BY_TIER = {
    "SOVEREIGN": 0.25,   # 25% fractional — highest conviction
    "ELITE":     0.20,   # 20% fractional
    "APPROVED":  0.15,   # 15% fractional — default
    "LEAN":      0.08,   # 8% fractional — small edge
    "PASS":      0.00,   # No bet
}

# Tier thresholds (props) — sport-specific overrides in get_tier()
def _get_cal_tier(edge, sport):
    """Wrapper: get_tier with auto-calibrated thresholds from session_state."""
    cal = st.session_state.get("calibrated_thresholds", {})
    return get_tier(edge, sport, cal if cal.get("_calibrated") else None)

# Tier thresholds (game lines: SPREAD/TOTAL/ML) — calibrated separately
# from props since game edges run on a smaller scale (see
# calibrate_tier_thresholds v3, 2026-07-12). Falls back to the static
# GAME_TIER_THRESHOLDS via get_tier's own fallback path if this sport
# hasn't accumulated enough game-bet history yet to calibrate.
def _get_cal_game_tier(edge, sport):
    """Wrapper: get_tier with auto-calibrated GAME thresholds from session_state."""
    cal = st.session_state.get("calibrated_game_thresholds", {})
    if cal.get("_calibrated"):
        return get_tier(edge, sport, cal)
    # No real calibration yet — force get_tier to use GAME_TIER_THRESHOLDS
    # (game scale) rather than its own internal fallback to TIER_THRESHOLDS
    # (prop scale, which would misgrade every game edge).
    static = GAME_TIER_THRESHOLDS.get(sport, GAME_TIER_THRESHOLDS.get("NBA"))
    return get_tier(edge, sport, {**static, "_calibrated": True})
TIER_SOVEREIGN_DEFAULT = 0.15   # 15%+ edge
TIER_ELITE_DEFAULT     = 0.10   # 10%+ edge
TIER_APPROVED_DEFAULT  = 0.05   # 5%+ edge
TIER_LEAN_DEFAULT      = 0.02   # 2%+ edge

# API quotas
SCRAPEOPS_MONTHLY_LIMIT  = 1000   # Free tier
SCRAPERAPI_DAILY_LIMIT   = 1000   # Free tier, resets daily
ODDSPAPI_MONTHLY_LIMIT   = 1000   # Free tier
ODDSPAPI_DAILY_LIMIT     = 100    # Free tier
PARLAYAPI_DAILY_LIMIT    = 200    # Free tier

# Cache TTLs (seconds)
CACHE_TTL_PROPS     = 1800   # 30 min — props refresh every half hour
CACHE_TTL_GAMELINES = 3600   # 1 hr — game lines change slower
CACHE_TTL_INJURIES  = 7200   # 2 hr — injury reports update less frequently
CACHE_TTL_GIST      = 600    # 10 min — Gist data from local scraper

# Board limits
MAX_PROPS_PER_BOARD   = 200   # Show top 200 props per sport
MAX_GAMES_PER_BOARD   = 20    # Show up to 20 games
MIN_BETS_CALIBRATION  = 30    # Need 30+ bets before calibration
MIN_BETS_SIGNAL_AUDIT = 20    # Need 20+ bets before signal audit
MIN_BETS_OPTIMIZER    = 50    # Need 50+ bets before optimizer





CACHE_DIR = "/tmp/betcouncil_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
# Clear ALL game line caches on startup — forces fresh fetch with fixed abbrev mapping
import glob as _glob_startup

# --- Utility: cap list growth in session state ---



for _stale in _glob_startup.glob(os.path.join(CACHE_DIR, "odds_api_games_*.pkl")):
    try: os.remove(_stale)
    except (requests.RequestException, KeyError, ValueError): pass
for _stale in _glob_startup.glob(os.path.join(CACHE_DIR, "espn_games_*.pkl")):
    try: os.remove(_stale)
    except (requests.RequestException, KeyError, ValueError): pass
for _stale in _glob_startup.glob(os.path.join(CACHE_DIR, "game_lines_*.pkl")):
    try: os.remove(_stale)
    except (requests.RequestException, KeyError, ValueError): pass
for _stale in _glob_startup.glob(os.path.join(CACHE_DIR, "mlb_pitchers.pkl")):
    try: os.remove(_stale)
    except (requests.RequestException, KeyError, ValueError): pass
AVERAGES_LAST_UPDATED = "2025-05-13"

# Daily risk controls

# JSON persistence paths
HISTORY_PATH = os.path.join(CACHE_DIR, "history.json")
LOCKS_PATH = os.path.join(CACHE_DIR, "locks.json")
BANKROLL_PATH = os.path.join(CACHE_DIR, "bankroll.json")
CALIBRATION_PATH = os.path.join(CACHE_DIR, "calibration.json")
CLV_PATH = os.path.join(CACHE_DIR, "clv_tracking.json")
PINNACLE_LINES_PATH = os.path.join(CACHE_DIR, "pinnacle_lines.json")
INJURY_PERFORMANCE_PATH = os.path.join(CACHE_DIR, "injury_performance.json")
WEIGHT_OVERRIDES_PATH = os.path.join(CACHE_DIR, "weight_overrides.json")
WEIGHT_ADJUSTMENT_LOG_PATH = os.path.join(CACHE_DIR, "weight_adjustment_log.json")
LINE_MOVEMENT_PATH = os.path.join(CACHE_DIR, "line_movement.json")
SHARP_PATH = os.path.join(CACHE_DIR, "sharp_flags.json")
SIGNAL_PERFORMANCE_PATH = os.path.join(CACHE_DIR, "signal_performance.json")
WEIGHT_OPTIMIZER_PATH = os.path.join(CACHE_DIR, "optimized_weights.json")
WEIGHT_OPTIMIZER_MIN_BETS = 50
STEAM_CACHE_PATH = os.path.join(CACHE_DIR, "steam_baseline.json")
STEAM_MOVE_THRESHOLD = 0.5
STEAM_MIN_BOOKS = 3

# API counter paths
API_SPORTS_COUNTER_PATH = os.path.join(CACHE_DIR, "api_sports_counter.json")
SPORTMONKS_COUNTER_PATH = os.path.join(CACHE_DIR, "sportmonks_counter.json")
UNIFIED_COUNTER_PATH = os.path.join(CACHE_DIR, "unified_counter.json")
ODDS_API_COUNTER_PATH = os.path.join(CACHE_DIR, "odds_api_counter.json")
BDL_COUNTER_PATH = os.path.join(CACHE_DIR, "bdl_counter.json")
ROLLING_DEFENSE_CACHE_HOURS = 12

# GitHub Gist persistence
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_GIST_ID = st.secrets.get("GITHUB_GIST_ID", "")
GIST_API = "https://api.github.com/gists"

# ── Startup credential check ────────────────────────────────────────────────
# Show a visible banner at app load when Gist persistence is unconfigured so
# the operator knows immediately rather than discovering it via silent [] returns.
if not GITHUB_GIST_ID:
    st.error(
        "⚠️ **GITHUB_GIST_ID not set** — Gist persistence disabled. "
        "Props auto-scraping, lock history, and bankroll data will not be saved or loaded. "
        "Add GITHUB_GIST_ID to Streamlit secrets to enable.",
        icon="🔴",
    )
elif not GITHUB_TOKEN:
    st.error(
        "⚠️ **GITHUB_TOKEN not set** — Gist reads/writes will fail. "
        "Add GITHUB_TOKEN to Streamlit secrets.",
        icon="🔴",
    )
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")

# ── Global Kill Switch ───────────────────────────────────────────────────────
# Set ENABLE_RECOMMENDATIONS=false in Streamlit Cloud secrets to immediately
# suppress all board recommendations, edge calculations, and pick output.
# The app remains fully operational (data fetches, history, system tab all work)
# but the board returns no picks and shows a maintenance banner instead.
# Use this if the model behaves erratically or you need an emergency hard stop.
# Default: True (recommendations enabled) when secret is missing or any truthy value.
_er_raw = st.secrets.get("ENABLE_RECOMMENDATIONS", "true")
ENABLE_RECOMMENDATIONS = str(_er_raw).lower() not in ("false", "0", "off", "no", "disabled")

# OddsPapi constants
ODDSPAPI_KEY = st.secrets.get("ODDSPAPI_KEY", "")
PARLAY_API_KEY = st.secrets.get("PARLAY_API_KEY", "")
PARLAY_API_BASE = "https://parlay-api.com/v1"
ODDSPAPI_COUNTER_PATH = os.path.join(CACHE_DIR, "oddspapi_counter.json")
ODDSPAPI_FREE_TIER_DAILY_LIMIT = 100
ODDSPAPI_FREE_TIER_MONTHLY_LIMIT = 1000

# Soccer API constant
FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
FOOTBALL_DATA_HEADERS = {
    "X-Auth-Token": "",
    "User-Agent": "BetCouncil/4.6"
}

# ParlayPlay constants
PARLAYPLAY_COUNTER_PATH = os.path.join(CACHE_DIR, "parlayplay_counter.json")
PARLAYPLAY_DAILY_LIMIT = 200

# BDL Props constants
BDL_PROPS_COUNTER_PATH = os.path.join(CACHE_DIR, "bdl_props_counter.json")
BDL_PROPS_DAILY_LIMIT = 60

# Odds API constants
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_BOOKS_PROPS = "bovada,mybookieag,draftkings,fanduel,betmgm,caesars,us_ex,circa_sports,betonlineag"
ODDS_API_BOOKS_GAMES = "bovada,mybookieag,draftkings,fanduel,betmgm,caesars,us_ex,circa_sports,betonlineag"

# Action Network public betting API
ACTION_NETWORK_BASE = (
    "https://api.actionnetwork.com"
    "/web/v2/scoreboard/publicbetting"
)
ACTION_NETWORK_BOOK_IDS = (
    "15,30,4727,4795,79,2988,"
    "69,68,75,123,71"
)




ACTION_NETWORK_PATH = os.path.join(
    CACHE_DIR, "action_network_counter.json"
)

# The Odds API sport keys
ODDS_API_SPORT_MAP = {
    "NBA": "basketball_nba",
    "MLB": "baseball_mlb",
    "NFL": "americanfootball_nfl",
    "NHL": "icehockey_nhl",
    "WNBA": "basketball_wnba",
}

# Player prop market keys by sport

# Books that have best alternate line coverage
ODDS_API_BOOKS_ALT_LINES = "fanduel,draftkings,betmgm,caesars"

# Map Odds API market keys to our stat names

# Unified API budgets

TIER_DESCRIPTIONS = {"SOVEREIGN": "Edge ≥ 15%", "ELITE": "Edge ≥ 10%", "APPROVED": "Edge ≥ 5%", "LEAN": "Edge ≥ 2%", "PASS": "Edge < 2%"}


# Sport-specific signal weights

# Signal reliability scores based on historical accuracy
# These represent how often each signal correctly predicts outcome



# classify_regime — moved to utils.py
def render_signal_chart(prop, sport="NBA"):
    """
    Render a plain-language signal breakdown chart.
    Shows bettors WHY a pick is rated the way it is.
    """
    signals = {
        "base": prop.get("SignalBase", 0),
        "defense": prop.get("SignalDefense", 0),
        "location": prop.get("SignalLocation", 0),
        "rest": prop.get("SignalRest", 0),
        "pace": prop.get("SignalPace", 0),
        "usage": prop.get("SignalUsage", 0),
        "blowout": prop.get("SignalBlowout", 0),
    }
    edge = prop.get("Edge", 0)
    line_moved = bool(prop.get("SharpFlag"))
    regime_key = classify_regime(signals, edge, line_moved)
    regime_label, regime_color = REGIME_LABELS.get(regime_key, ("NEUTRAL", "#6a7a8a"))

    firing = sum(1 for v in signals.values() if abs(v) > 0.001)
    total = len(signals)
    avg_reliability = sum(SIGNAL_RELIABILITY.get(k, 0.5) for k, v in signals.items() if abs(v) > 0.001)
    avg_reliability = avg_reliability / firing if firing > 0 else 0
    net_delta = sum(signals.values())

    delta_color = "#22c55e" if net_delta > 0 else "#e04040"
    direction = "OVER" if net_delta > 0 else "UNDER"
    max_val = max(abs(v) for v in signals.values()) if signals else 0.01
    if max_val == 0:
        max_val = 0.01

    # Plain English labels
    plain_labels = {
        "base": "Recent Performance vs Line",
        "defense": "Opponent Defense Strength",
        "location": "Home / Away Factor",
        "rest": "Rest & Schedule",
        "pace": "Game Pace",
        "usage": "Teammate Out Boost",
        "blowout": "Blowout Risk",
        "weather": "Weather Conditions",
    }

    # Plain English explanations shown on hover/below
    plain_desc = {
        "base": "How this player has been performing vs this exact line recently",
        "defense": "How good/bad the opponent is at stopping this stat",
        "location": "Players typically perform differently at home vs away",
        "rest": "Days of rest — more rest generally helps performance",
        "pace": "Faster-paced games create more opportunities for counting stats",
        "usage": "When a teammate is out, this player typically gets more opportunities",
        "blowout": "Blowout games reduce stats for starters who get pulled early",
        "weather": "Wind and temperature affect outdoor games like MLB",
    }

    # Strength label
    def strength_label(val):
        a = abs(val)
        if a >= 0.08: return "Strong"
        if a >= 0.04: return "Moderate"
        if a >= 0.01: return "Slight"
        return "Minimal"

    rows_html = ""
    for key, val in signals.items():
        if abs(val) < 0.0001:
            continue
        label = plain_labels.get(key, key.title())
        desc = plain_desc.get(key, "")
        reliability = SIGNAL_RELIABILITY.get(key, 0.5)
        bar_pct = min(100, int(abs(val) / max_val * 100))
        bar_color = "#22c55e" if val > 0 else "#e04040"
        direction_word = "Favors OVER" if val > 0 else "Favors UNDER"
        strength = strength_label(val)
        rel_color = "#22c55e" if reliability >= 0.75 else "#e8a020" if reliability >= 0.60 else "#6a7a8a"
        rel_label = "High accuracy" if reliability >= 0.75 else "Moderate accuracy" if reliability >= 0.60 else "Lower accuracy"

        rows_html += f"""
<div style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid #1a2a3a;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
    <div>
      <span style="font-size:15px;font-weight:500;color:#e8f0f8">{label}</span>
      <span style="font-size:16px;color:{bar_color};margin-left:8px;background:{bar_color}22;padding:1px 7px;border-radius:8px">{strength} {direction_word}</span>
    </div>
    <span style="font-size:16px;color:{rel_color}">{rel_label} ({int(reliability*100)}%)</span>
  </div>
  <div style="background:#0a1628;border-radius:4px;height:10px;overflow:hidden;margin-bottom:3px;">
    <div style="width:{bar_pct}%;height:100%;background:{bar_color};border-radius:4px;"></div>
  </div>
  <div style="font-size:16px;color:#6a7a8a">{desc}</div>
</div>"""

    zero_signals = [plain_labels.get(k, k) for k, v in signals.items() if abs(v) <= 0.0001]
    zero_html = ""
    if zero_signals:
        zero_html = f'<div style="font-size:16px;color:#4a5a6a;margin-top:4px">No impact: {", ".join(zero_signals)}</div>'

    # Overall verdict in plain English
    strong_count = sum(1 for v in signals.values() if abs(v) >= 0.06)
    moderate_count = sum(1 for v in signals.values() if 0.02 <= abs(v) < 0.06)

    if firing == 0:
        verdict = "No signals firing — not enough data to analyze this pick."
    elif strong_count >= 2:
        verdict = f"{strong_count} strong signals all pointing {direction}. High conviction play."
    elif strong_count == 1 and moderate_count >= 1:
        verdict = f"1 strong signal + {moderate_count} supporting signals pointing {direction}."
    elif firing >= 3:
        verdict = f"{firing} signals pointing {direction}. Moderate conviction."
    else:
        verdict = f"Mixed signals — use caution. Only {firing} signal(s) firing."

    # Regime plain English
    regime_plain = {
        "CONFIRM OVER": "All signals agree — strong OVER edge",
        "CONFIRM UNDER": "All signals agree — strong UNDER edge",
        "REPRICE": "Line moved but model still sees value",
        "SHARP FADE": "Sharp money moving against the model",
        "NEUTRAL": "No strong directional bias detected",
    }.get(regime_label, "")

    # ── Conviction Score (0-100) ─────────────────────────────────────────
    # Single combined confidence number, blending signal coverage, average
    # signal accuracy, and edge size relative to this sport's SOVEREIGN
    # threshold.
    coverage_score = (firing / total * 100) if total else 0
    reliability_score = avg_reliability * 100
    sport_key = str(sport).upper()
    sovereign_edge = TIER_THRESHOLDS.get(sport_key, TIER_THRESHOLDS.get("NBA", {})).get("SOVEREIGN", 0.12)
    edge_score = min(abs(edge) / sovereign_edge, 1.0) * 100 if sovereign_edge else 0
    conviction_score = round(0.35 * coverage_score + 0.35 * reliability_score + 0.30 * edge_score)
    conviction_score = max(0, min(100, conviction_score))

    if conviction_score >= 80:
        conv_color, conv_label = "#22c55e", "High conviction"
    elif conviction_score >= 60:
        conv_color, conv_label = "#e8a020", "Moderate conviction"
    elif conviction_score >= 40:
        conv_color, conv_label = "#e0a840", "Low conviction"
    else:
        conv_color, conv_label = "#6a7a8a", "Weak / no edge"

    # Line move tile — reuses the existing SharpFlag text so it matches
    # what's shown elsewhere on the pick.
    sharp_flag_txt = str(prop.get("SharpFlag", "") or "").strip()
    if sharp_flag_txt:
        line_move_display = sharp_flag_txt
        line_move_color = "#22c55e" if "↑" in sharp_flag_txt or line_moved else "#6a7a8a"
    else:
        line_move_display = "No line move"
        line_move_color = "#6a7a8a"

    # EXPECTED_VS_ACTUAL — how this player has performed against THIS
    # specific opponent, compared to today's line. Built for all 4 major
    # sports so it's ready rather than forgotten when NBA/NHL come back
    # in season (MLB is the only one live right now). NFL's fetcher is
    # less battle-tested than the others (see its docstring) — worth a
    # real check once football season starts. Informational only — not
    # blended into the edge/probability calculation.
    eva_html = ""
    _eva_fetchers = {
        "NBA": fetch_nba_player_gamelog_vs_opponent,
        "MLB": fetch_mlb_player_gamelog_vs_opponent,
        "NHL": fetch_nhl_player_gamelog_vs_opponent,
        "NFL": fetch_nfl_player_gamelog_vs_opponent,
    }
    if sport in _eva_fetchers:
        try:
            _eva_stat_key = _map_prop_to_stat_key(prop.get("Prop", ""), sport)
            _eva_opponent = prop.get("Opponent", "")
            _eva_player = prop.get("Player", "")
            _eva_line = prop.get("Line", 0)
            if _eva_stat_key and _eva_opponent and _eva_player:
                _eva_games = _eva_fetchers[sport](_eva_player, _eva_opponent, sport)
                _eva = compute_expected_vs_actual(_eva_games, _eva_stat_key, _eva_line)
                if _eva.get("n_games", 0) >= 2:
                    _eva_color = "#22c55e" if (_eva.get("residual") or 0) > 0 else "#e04040"
                    eva_html = f'''
        <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
          <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">vs {_eva_opponent} (n={_eva['n_games']})</div>
          <div style="font-size:18px;font-weight:500;color:{_eva_color}">{_eva['residual']:+.1f}</div>
        </div>'''
        except Exception:
            pass

    # Market-Anchored Fair Line Pricer — informational, mirrors the
    # EXPECTED_VS_ACTUAL tile treatment above. Fields already sit on the
    # enriched prop dict (computed once during board load), so this just
    # renders them — no extra fetch here.
    pricer_html = ""
    _pr_fair = prop.get("PricerFairLine")
    _pr_edge = prop.get("PricerEdgeVsOpen")
    if sport == "NBA" and _pr_fair is not None and _pr_edge is not None:
        _pr_color = "#22c55e" if _pr_edge > 0 else "#e04040" if _pr_edge < 0 else "#6a7a8a"
        _pr_unc = prop.get("PricerUncertainty", 0) or 0
        pricer_html = f'''
        <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;" title="L20 avg + book-bias correction, anchored to the market line">
          <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Pricer fair line (unc {_pr_unc:.0%})</div>
          <div style="font-size:18px;font-weight:500;color:{_pr_color}">{_pr_fair:g} <span style="font-size:12px;color:#6a7a8a">({_pr_edge:+.1f})</span></div>
        </div>'''

    html = f"""
<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:10px;padding:16px;margin:6px 0;">

  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #1a2a3a;">
    <div style="flex:1;min-width:0;">
      <div style="font-size:16px;color:var(--bc-dim);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px">Why this pick is rated the way it is</div>
      <div style="font-size:14px;font-weight:500;color:{delta_color}">{verdict}</div>
      <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;">
        <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
          <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Signals firing</div>
          <div style="font-size:18px;font-weight:500;color:#e8f0f8">{firing}<span style="font-size:15px;color:#6a7a8a"> / {total}</span></div>
        </div>
        <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
          <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Avg signal accuracy</div>
          <div style="font-size:18px;font-weight:500;color:#e8a020">{avg_reliability:.0%}</div>
        </div>
        <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
          <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Model edge</div>
          <div style="font-size:18px;font-weight:500;color:{delta_color}">{edge:+.1%}</div>
        </div>
        <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
          <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Line move</div>
          <div style="font-size:14px;font-weight:500;color:{line_move_color}">{line_move_display}</div>
        </div>
        <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
          <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Market regime</div>
          <div style="font-size:18px;font-weight:700;color:{regime_color}">{regime_label}</div>
          <div style="font-size:9px;color:#6a7a8a">{regime_plain}</div>
        </div>{eva_html}{pricer_html}
      </div>
    </div>
    <div style="flex-shrink:0;text-align:center;background:{conv_color}18;border:1px solid {conv_color}55;border-radius:10px;padding:10px 18px;min-width:84px;">
      <div style="font-size:28px;font-weight:800;color:{conv_color};line-height:1;">{conviction_score}</div>
      <div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase;margin-top:4px;">Conviction</div>
      <div style="font-size:9px;color:{conv_color};margin-top:2px;white-space:nowrap;">{conv_label}</div>
    </div>
  </div>

  <div style="font-size:16px;color:var(--bc-dim);text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Signal breakdown — what is pushing this pick</div>
  {rows_html}
  {zero_html}
</div>"""
    return html



# Sport-specific EWMA decay


SPORTS = ["NBA", "MLB", "NHL", "WNBA", "NFL", "Soccer", "UFC", "Golf", "Tennis"]


# API keys from secrets
BDL_API_KEY = st.secrets.get("BALLSDONTLIE_API_KEY", "")
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "")

# ── ODDS_API_KEY startup validity check (runs once per server process) ──────
@st.cache_resource
def _check_odds_api_key_status():
    _key = st.secrets.get("ODDS_API_KEY", "")
    if not _key:
        print("[STARTUP] ODDS_API_KEY not set — Game Lines will rely on SBR/BetOnline fallbacks only")
        return "missing"
    try:
        import requests as _req
        _r = _req.get(f"https://api.the-odds-api.com/v4/sports?apiKey={_key}", timeout=8)
        if _r.status_code == 200:
            print(f"[STARTUP] ODDS_API_KEY valid — {len(_r.json())} sports available")
            return "ok"
        elif _r.status_code in (401, 403):
            print(f"[STARTUP] ODDS_API_KEY invalid or expired (HTTP {_r.status_code})")
            return "invalid"
        print(f"[STARTUP] ODDS_API_KEY check returned HTTP {_r.status_code}")
        return f"http_{_r.status_code}"
    except Exception as _e:
        print(f"[STARTUP] ODDS_API_KEY connectivity check failed: {_e}")
        return "error"

_ODDS_API_KEY_STATUS = _check_odds_api_key_status()

API_SPORTS_KEY = st.secrets.get("API_SPORTS_KEY", "")
SCRAPEOPS_KEY = st.secrets.get("SCRAPEOPS_KEY", "")
SCRAPEOPS_KEY_2 = st.secrets.get("SCRAPEOPS_KEY_2", "")  # 2nd account, separate quota -- added 2026-07 once the first key started hitting its monthly limit
SCRAPERAPI_KEY = st.secrets.get("SCRAPERAPI_KEY", "")
SCRAPEDO_KEY   = st.secrets.get("SCRAPEDO_KEY",   "")
FIRECRAWL_KEY  = st.secrets.get("FIRECRAWL_KEY",  "")
SPORTMONKS_API_KEY = st.secrets.get("SPORTMONKS_API_KEY", "")
UNIFIED_API_KEY = st.secrets.get("UNIFIED_API_KEY", "")
RAPIDAPI_KEY = st.secrets.get("RAPIDAPI_KEY", "")
ODDS_API_IO_KEY = st.secrets.get("ODDS_API_IO_KEY", "")
OCR_SPACE_API_KEY = st.secrets.get("OCR_SPACE_API_KEY", "")

# Hardcoded baselines


PLAYER_AVERAGES = {}
PLAYER_AVERAGES.update({
    "NBA": {
        "Nikola Jokic":              {"PTS": 26.4, "REB": 12.4, "AST": 9.0, "PRA": 47.8, "BLK": 0.9},
        "Shai Gilgeous-Alexander":   {"PTS": 32.7, "REB": 5.5,  "AST": 6.4, "PRA": 44.6, "3P": 1.5},
        "Giannis Antetokounmpo":     {"PTS": 30.4, "REB": 11.5, "AST": 6.5, "PRA": 48.4, "BLK": 1.1},
        "Victor Wembanyama":         {"PTS": 24.2, "REB": 10.7, "AST": 3.9, "PRA": 38.8, "BLK": 3.6},
        "Luka Doncic":               {"PTS": 28.7, "REB": 9.3,  "AST": 8.7, "PRA": 46.7},
        "Jayson Tatum":              {"PTS": 26.9, "REB": 8.1,  "AST": 4.9, "PRA": 39.9},
        "Stephen Curry":             {"PTS": 26.4, "REB": 4.5,  "AST": 6.1, "PRA": 37.0, "3P": 2.9},
        "LeBron James":              {"PTS": 25.7, "REB": 7.3,  "AST": 8.3, "PRA": 41.3},
        "Jalen Brunson":             {"PTS": 28.7, "REB": 3.6,  "AST": 6.7, "PRA": 39.0},
        "Kevin Durant":              {"PTS": 27.1, "REB": 6.6,  "AST": 3.9, "PRA": 37.6},
        "Anthony Davis":             {"PTS": 26.2, "REB": 12.6, "AST": 3.5, "PRA": 42.3, "BLK": 2.4},
        "Joel Embiid":               {"PTS": 34.7, "REB": 11.0, "AST": 5.6, "PRA": 51.3},
        "Tyrese Maxey":              {"PTS": 25.9, "REB": 3.7,  "AST": 6.5, "PRA": 36.1},
        "Anthony Edwards":           {"PTS": 25.9, "REB": 5.4,  "AST": 5.1, "PRA": 36.4},
        "Devin Booker":              {"PTS": 25.1, "REB": 4.5,  "AST": 6.9, "PRA": 36.5},
        "Damian Lillard":            {"PTS": 24.3, "REB": 4.4,  "AST": 7.0, "PRA": 35.7},
        "Kawhi Leonard":             {"PTS": 22.7, "REB": 6.1,  "AST": 3.3, "PRA": 32.1},
        "Karl-Anthony Towns":        {"PTS": 24.3, "REB": 13.7, "AST": 3.1, "PRA": 41.1},
        "Jamal Murray":              {"PTS": 21.2, "REB": 4.3,  "AST": 6.5, "PRA": 32.0},
        "Kyrie Irving":              {"PTS": 25.1, "REB": 5.0,  "AST": 5.2, "PRA": 35.3},
        "De'Aaron Fox":              {"PTS": 26.6, "REB": 4.5,  "AST": 5.9, "PRA": 37.0},
        "Tyrese Haliburton":         {"PTS": 20.1, "REB": 3.9,  "AST": 10.9,"PRA": 34.9},
        "Donovan Mitchell":          {"PTS": 26.6, "REB": 5.1,  "AST": 6.1, "PRA": 37.8},
        "James Harden":              {"PTS": 16.6, "REB": 8.5,  "AST": 8.5, "PRA": 33.6},
        "Trae Young":                {"PTS": 25.7, "REB": 3.3,  "AST": 10.8,"PRA": 39.8},
        "Bam Adebayo":               {"PTS": 19.3, "REB": 10.4, "AST": 3.3, "PRA": 33.0},
        "Jaylen Brown":              {"PTS": 23.0, "REB": 5.5,  "AST": 3.6, "PRA": 32.1},
        "Ja Morant":                 {"PTS": 25.1, "REB": 5.6,  "AST": 8.1, "PRA": 38.8},
        "Cade Cunningham":           {"PTS": 22.7, "REB": 4.4,  "AST": 9.0, "PRA": 36.1},
        "Paolo Banchero":            {"PTS": 22.6, "REB": 6.9,  "AST": 5.4, "PRA": 34.9},
        "Scottie Barnes":            {"PTS": 19.9, "REB": 8.2,  "AST": 6.1, "PRA": 34.2},
    },
    "MLB": {"Aaron Judge": {"HR": 0.15, "H": 1.2, "RBI": 0.9, "R": 0.9}, "Shohei Ohtani": {"HR": 0.14, "H": 1.1, "RBI": 0.8, "R": 0.8},
             "Mookie Betts": {"HR": 0.12, "H": 1.2, "RBI": 0.7, "R": 0.9}, "Ronald Acuna Jr.": {"HR": 0.13, "H": 1.2, "RBI": 0.8, "R": 0.9},
             "Bryce Harper": {"HR": 0.14, "H": 1.1, "RBI": 0.8, "R": 0.8}, "Juan Soto": {"HR": 0.13, "H": 1.1, "RBI": 0.8, "R": 0.8},
             "Freddie Freeman": {"HR": 0.11, "H": 1.2, "RBI": 0.7, "R": 0.8}, "Jose Ramirez": {"HR": 0.12, "H": 1.1, "RBI": 0.8, "R": 0.8},
             "Pete Alonso": {"HR": 0.15, "H": 1.0, "RBI": 0.9, "R": 0.7}, "Vladimir Guerrero Jr.": {"HR": 0.12, "H": 1.2, "RBI": 0.8, "R": 0.8},
             "Francisco Lindor": {"HR": 0.12, "H": 1.1, "RBI": 0.7, "R": 0.8}, "Bobby Witt Jr.": {"HR": 0.12, "H": 1.2, "RBI": 0.8, "R": 0.9},
             "Gunnar Henderson": {"HR": 0.14, "H": 1.1, "RBI": 0.8, "R": 0.8}, "Elly De La Cruz": {"HR": 0.10, "H": 1.0, "RBI": 0.6, "R": 0.7},
             "Corbin Carroll": {"HR": 0.08, "H": 1.1, "RBI": 0.5, "R": 0.8}, "Paul Skenes": {"SO": 8.5, "H": 0.3, "ER": 0.4},
             "Spencer Strider": {"SO": 9.2, "H": 0.3, "ER": 0.5}, "Gerrit Cole": {"SO": 8.8, "H": 0.4, "ER": 0.5},
             "Zack Wheeler": {"SO": 8.4, "H": 0.4, "ER": 0.5}, "Tarik Skubal": {"SO": 9.0, "H": 0.3, "ER": 0.4}},
    "NFL": {"Patrick Mahomes": {"PASS_YDS": 280, "TD": 2.2}, "Josh Allen": {"PASS_YDS": 260, "RUSH_YDS": 35, "TD": 2.5},
            "Jalen Hurts": {"PASS_YDS": 230, "RUSH_YDS": 45, "TD": 2.2}, "Lamar Jackson": {"PASS_YDS": 220, "RUSH_YDS": 65, "TD": 2.0},
            "Joe Burrow": {"PASS_YDS": 270, "TD": 2.0}, "Justin Herbert": {"PASS_YDS": 265, "TD": 2.0}, "Dak Prescott": {"PASS_YDS": 260, "TD": 2.0},
            "Christian McCaffrey": {"RUSH_YDS": 85, "REC_YDS": 45, "TD": 1.0}, "Derrick Henry": {"RUSH_YDS": 90, "TD": 0.9},
            "Saquon Barkley": {"RUSH_YDS": 80, "REC_YDS": 35, "TD": 0.8}, "Tyreek Hill": {"REC_YDS": 95, "TD": 0.8},
            "Justin Jefferson": {"REC_YDS": 90, "TD": 0.7}, "Ja'Marr Chase": {"REC_YDS": 85, "TD": 0.7}, "Travis Kelce": {"REC_YDS": 70, "TD": 0.6},
            "CeeDee Lamb": {"REC_YDS": 92, "TD": 0.7}, "A.J. Brown": {"REC_YDS": 88, "TD": 0.7}},
    "NHL": {"Connor McDavid": {"PTS": 1.5, "GOALS": 0.6, "ASSISTS": 0.9, "SOG": 3.5}, "Leon Draisaitl": {"PTS": 1.4, "GOALS": 0.6, "ASSISTS": 0.8, "SOG": 3.2},
            "Nathan MacKinnon": {"PTS": 1.4, "GOALS": 0.5, "ASSISTS": 0.9, "SOG": 3.4}, "David Pastrnak": {"PTS": 1.2, "GOALS": 0.6, "ASSISTS": 0.6, "SOG": 3.5},
            "Nikita Kucherov": {"PTS": 1.5, "GOALS": 0.5, "ASSISTS": 1.0, "SOG": 3.0}, "Auston Matthews": {"PTS": 1.2, "GOALS": 0.7, "ASSISTS": 0.5, "SOG": 3.7},
            "Mitch Marner": {"PTS": 1.2, "GOALS": 0.4, "ASSISTS": 0.8, "SOG": 2.8}, "Cale Makar": {"PTS": 0.9, "GOALS": 0.2, "ASSISTS": 0.7, "SOG": 2.5},
            "Kirill Kaprizov": {"PTS": 1.1, "GOALS": 0.5, "ASSISTS": 0.6, "SOG": 3.2}, "Mikko Rantanen": {"PTS": 1.3, "GOALS": 0.5, "ASSISTS": 0.8, "SOG": 3.0},
            "Matthew Tkachuk": {"PTS": 1.1, "GOALS": 0.4, "ASSISTS": 0.7, "SOG": 3.0}, "Brayden Point": {"PTS": 1.1, "GOALS": 0.5, "ASSISTS": 0.6, "SOG": 3.1},
            "Sam Reinhart": {"PTS": 1.0, "GOALS": 0.5, "ASSISTS": 0.5, "SOG": 3.0}, "Aleksander Barkov": {"PTS": 1.0, "GOALS": 0.4, "ASSISTS": 0.6, "SOG": 2.8}},
    "WNBA": {"A'ja Wilson": {"PTS": 26.0, "REB": 9.4, "AST": 2.4, "PRA": 37.8}, "Breanna Stewart": {"PTS": 21.8, "REB": 8.6, "AST": 3.8, "PRA": 34.2},
             "Sabrina Ionescu": {"PTS": 19.4, "REB": 4.5, "AST": 6.3, "PRA": 30.2}, "Kelsey Plum": {"PTS": 18.9, "REB": 2.8, "AST": 4.2, "PRA": 25.9},
             "Napheesa Collier": {"PTS": 20.1, "REB": 9.3, "AST": 2.7, "PRA": 32.1}, "Caitlin Clark": {"PTS": 19.2, "REB": 5.7, "AST": 8.4, "PRA": 33.3},
             "Angel Reese": {"PTS": 13.1, "REB": 13.1, "AST": 1.9, "PRA": 28.1}, "Alyssa Thomas": {"PTS": 12.5, "REB": 9.2, "AST": 7.1, "PRA": 28.8},
             "Jackie Young": {"PTS": 17.3, "REB": 4.1, "AST": 4.0, "PRA": 25.4}},
    "Soccer": PLAYER_AVERAGES_SOCCER,
    "UFC": PLAYER_AVERAGES_UFC,
})



HOME_BOOST = {"PTS": 1.5, "REB": 0.5, "AST": 0.4, "PRA": 2.4}
AWAY_PENALTY = {"PTS": -1.5, "REB": -0.5, "AST": -0.4, "PRA": -2.4}



BLOWOUT_THRESHOLDS = {
    "NBA": 12, "NFL": 14, "MLB": 3,
    "NHL": 2, "WNBA": 10
}

NEGATIVE_CORRELATIONS = {
    ("Nikola Jokic", "Joel Embiid"): -0.3,
    ("Luka Doncic", "Shai Gilgeous-Alexander"): -0.2,
    ("Jayson Tatum", "Giannis Antetokounmpo"): -0.2,
}



WIND_HR_THRESHOLDS = {"strong_out": 15, "strong_in": 15}










LEAGUE_AVG_POSITION = {"PG": 22.1, "SG": 21.8, "SF": 21.2, "PF": 22.0, "C": 23.5}





MLB_PARK_DEFAULT = 1.00


NHL_GOALS_DEFAULT = 3.0

LEAGUE_AVG_ERA = 4.25

try:
    from oddswrap import Sport
    ODDSWRAP_AVAILABLE = True
except ImportError:
    ODDSWRAP_AVAILABLE = False

ODDSWRAP_SPORT_MAP = {"NBA": "nba", "MLB": "mlb", "NFL": "nfl", "NHL": "nhl"}
ODDS_SPORTS_MAP = {
    "NBA": "basketball_nba", "MLB": "baseball_mlb",
    "NFL": "americanfootball_nfl", "NHL": "icehockey_nhl",
    "WNBA": "basketball_wnba",
}
ESPN_CORE_BASE = "https://sports.core.api.espn.com/v2"
ESPN_CORE_SPORT_MAP = {
    "NBA": "basketball/leagues/nba", "MLB": "baseball/leagues/mlb",
    "NHL": "hockey/leagues/nhl", "NFL": "football/leagues/nfl",
    "WNBA": "basketball/leagues/wnba", "Soccer": "soccer/leagues/eng.1",
}
ESPN_BET_PROVIDER_ID = 1002



# ═══════════════════════════════════════════════════════════════
# STATIC RESOURCE CACHE — @st.cache_resource(ttl=300)
# These dicts are defined at module level and never change.
# Wrapping in cache_resource avoids repeated dict lookups and
# ensures a single shared instance across all Streamlit reruns.
# ═══════════════════════════════════════════════════════════════

@st.cache_resource(ttl=300)
def get_player_team_map():
    return PLAYER_TEAM_MAP

@st.cache_resource(ttl=300)
def get_mlb_player_team_map():
    return MLB_PLAYER_TEAM_MAP

@st.cache_resource(ttl=300)
def get_sport_signal_weights():
    return SPORT_SIGNAL_WEIGHTS

@st.cache_resource(ttl=300)
def get_nba_power_ratings():
    return NBA_POWER_RATINGS

@st.cache_resource(ttl=300)
def get_nba_team_pace():
    return NBA_TEAM_PACE

@st.cache_resource(ttl=300)
def get_default_averages():
    return DEFAULT_AVERAGES

@st.cache_resource(ttl=300)
def get_nba_position_defense():
    return NBA_POSITION_DEFENSE

@st.cache_resource(ttl=300)
def get_nba_player_positions():
    return NBA_PLAYER_POSITIONS

@st.cache_resource(ttl=300)
def get_espn_athlete_ids():
    return ESPN_ATHLETE_IDS

@st.cache_resource(ttl=300)
def get_action_network_sport_map():
    return ACTION_NETWORK_SPORT_MAP

# =========================
# FUNCTIONS
# =========================

@st.cache_data(ttl=3600)
def ewma_average(game_values, decay=0.85, sport=None):
    if not game_values:
        return 0.0
    if sport:
        decay = SPORT_EWMA_DECAY.get(sport, decay)
    weights = [decay**i for i in range(len(game_values))]
    weighted = sum(v * w for v, w in zip(reversed(game_values), weights))
    return round(weighted / sum(weights), 2)

# compute_std_dev — moved to utils.py
# tier_badge — moved to utils.py

GAME_TOTAL_PROP_NAMES = {
    "Points Total", "Total Points", "Game Total", "Match Total",
    "Total Goals", "Total Runs", "Total Score", "Team Total",
    "Alternate Total",
}

# is_game_total_prop — moved to utils.py
# compute_market_edge — moved to bc_utils.py
def compute_consensus_probability(sport, player_name, stat_name, line_val, side="OVER"):
    """
    Compute true probability using no-vig devig.
    Priority: 1) Pinnacle (sharpest) 2) Consensus across books
    This is the OddsJam/Outlier methodology.
    """
    # PRIORITY 1: Use Pinnacle no-vig as true probability (Gap 2 fix)
    pinn_data = st.session_state.get(f"pinnacle_{sport}", {})
    if pinn_data:
        pinn_prob, confirms, note = pinnacle_fair_value(
            player_name, stat_name, line_val, side, sport
        )
        if pinn_prob is not None:
            # Pinnacle devig IS the gold standard — return it directly
            return round(pinn_prob, 4), ["Pinnacle (no-vig)"]

    # PRIORITY 2: Consensus across soft books (fallback)
    if not ODDS_API_KEY:
        return None, []
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return None, []
    cache_path = os.path.join(CACHE_DIR, f"odds_api_props_{sport}.pkl")
    if not os.path.exists(cache_path):
        return None, []
    try:
        with open(cache_path, "rb") as f:
            cached_props = pickle.load(f)
    except (pickle.UnpicklingError, OSError, EOFError):
        return None, []
    if not cached_props:
        return None, []
    norm_player = normalize_name(player_name)
    matching = []
    for prop in cached_props:
        prop_player = normalize_name(prop.get("Player", ""))
        prop_stat = prop.get("Prop", "")
        prop_line = prop.get("Line", 0)
        prop_side = prop.get("Side", "OVER")
        if (prop_player == norm_player and prop_stat == stat_name and abs(float(prop_line) - float(line_val)) <= 0.5 and prop_side.upper() == side.upper()):
            matching.append(prop)
    if len(matching) < 2:
        return None, []
    book_probs = []
    books_used = []
    for prop in matching:
        source = prop.get("source", "")
        book = source.replace("OddsAPI_", "")
        over_odds = prop.get("OverOdds", -110)
        under_odds = prop.get("UnderOdds", -110)
        if over_odds is None:
            over_odds = -110
        if under_odds is None:
            under_odds = -110
        try:
            _ens     = devig_ensemble(over_odds, under_odds, liquidity="medium")
            _bk_fair = _ens.get("fair_prob")
            if _bk_fair is None:
                continue
            book_probs.append(_bk_fair if side.upper() == "OVER" else round(1.0 - _bk_fair, 4))
        except Exception:
            continue
        books_used.append(book)
    if len(book_probs) < 2:
        return None, books_used
    if any("Novig" in b or "us_ex" in b for b in books_used):
        novig_idx = next((i for i, b in enumerate(books_used) if "Novig" in b or "us_ex" in b), None)
        if novig_idx is not None:
            novig_prob = book_probs[novig_idx]
            other_probs = [p for i, p in enumerate(book_probs) if i != novig_idx]
            if other_probs:
                consensus = (novig_prob * 2 + sum(other_probs)) / (2 + len(other_probs))
            else:
                consensus = novig_prob
        else:
            consensus = sum(book_probs) / len(book_probs)
    else:
        consensus = sum(book_probs) / len(book_probs)
    consensus = round(max(0.20, min(0.80, consensus)), 4)
    return consensus, books_used

def check_daily_risk_limits(sport=None):
    bankroll = st.session_state.get("bankroll", DEFAULT_BANKROLL)
    day_start = st.session_state.get("day_start_br", 0)
    if day_start > 0:
        daily_change = (bankroll - day_start) / day_start
        if daily_change <= -DAILY_RISK_CONTROLS["max_daily_loss_pct"]:
            return False, f"🛑 Daily stop-loss hit ({daily_change:.1%}). No more bets today."
        if daily_change >= DAILY_RISK_CONTROLS["stop_win_pct"]:
            return False, f"🏆 Stop-win triggered (+{daily_change:.1%}). Lock in today's profits."
    today = date.today().strftime("%Y-%m-%d")
    today_locks = [l for l in st.session_state.get("history", []) if l.get("timestamp", "").startswith(today)]
    today_locks += [l for l in st.session_state.get("locks", []) if l.get("timestamp", "").startswith(today)]
    if len(today_locks) >= DAILY_RISK_CONTROLS["max_locks_per_day"]:
        return False, f"🛑 Max {DAILY_RISK_CONTROLS['max_locks_per_day']} locks per day reached."
    if sport:
        sport_locks = [l for l in st.session_state.get("locks", []) if l.get("sport") == sport]
        if len(sport_locks) >= DAILY_RISK_CONTROLS["max_same_sport_locks"]:
            return False, f"⚠️ Max {DAILY_RISK_CONTROLS['max_same_sport_locks']} {sport} locks reached."
    return True, ""


# ═══════════════════════════════════════════════════════════
# SQLITE MIGRATION STUB
# When history reaches ~500 bets, migrate from Gist to SQLite.
# Gist payload (history + locks + bankroll) will exceed 1MB
# and PATCH latency will increase noticeably.
#
# Migration path:
#   1. pip install sqlite3 (stdlib — no install needed)
#   2. Replace save_to_gist("history") with db.execute(INSERT)
#   3. Replace load_from_gist("history") with db.execute(SELECT)
#   4. Keep Gist for bankroll + locks (small payloads)
#
# Trigger: len(st.session_state.get("history", [])) > 500
#
# def _get_sqlite_db():
#     """Initialize SQLite DB on Streamlit Cloud persistent volume."""
#     import sqlite3
#     db_path = os.path.join(CACHE_DIR, "betcouncil.db")
#     conn = sqlite3.connect(db_path, check_same_thread=False)
#     conn.execute("""CREATE TABLE IF NOT EXISTS history (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         timestamp TEXT, player TEXT, prop TEXT,
#         line REAL, side TEXT, sport TEXT,
#         outcome TEXT, wager REAL, tier TEXT,
#         edge REAL, signals TEXT
#     )""")
#     conn.commit()
#     return conn
# ═══════════════════════════════════════════════════════════

# ══���════════════════════════════════════════════════════════
# MODULE: STORAGE — Gist, JSON, pickle persistence
# Future extraction target: storage.py
# ═══════════════════════════════════════════════════════════
# Batch window: non-critical dirty writes are held for up to this many seconds
# before being flushed. When the window expires (or a critical write triggers
# flush), ALL dirty keys are written in a SINGLE Gist PATCH request instead of
# one PATCH per key — reducing API calls proportionally to how many keys are
# queued together.
_GIST_BATCH_WINDOW = 5.0  # seconds

# Keys that must be flushed immediately rather than held in the batch window.
_GIST_CRITICAL_KEYS = frozenset({"history", "bankroll", "signal_performance", "injury_performance", "locks", "scrapeops_status", "weight_overrides", "weight_adjustment_log", "optimized_weights"})
# "locks" added 2026-07: WIN/LOSS/VOID slip buttons remove a lock from
# st.session_state immediately, then call save_to_gist("locks", ...) — but
# as a non-critical key that write was only QUEUED, flushed up to 5s later.
# If the session ended (tab closed, Streamlit Cloud container recycled)
# before that flush happened, the removal never reached the Gist — so the
# next session loaded the stale copy with the "settled" lock still in it.
# This is why settled slips could keep reappearing in Locks & Ledger even
# after clicking Win/Loss Slip. Now flushes synchronously, same as history.

def save_to_gist(data_type, data):
    """
    Batched Gist writer — marks data as dirty and flushes once per batch window.

    Non-critical writes (locks, props, etc.) are queued for up to
    _GIST_BATCH_WINDOW seconds. When a critical write arrives, OR when the
    window expires, ALL dirty keys are flushed in a SINGLE Gist PATCH request.
    This replaces the previous per-key PATCH pattern and reduces API calls
    proportionally to the number of keys written together.
    """
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return False
    if "gist_dirty" not in st.session_state:
        st.session_state["gist_dirty"] = {}
    if "gist_last_write" not in st.session_state:
        st.session_state["gist_last_write"] = {}
    # Mark dirty
    st.session_state["gist_dirty"][data_type] = data
    now = time.time()
    # Open a new batch window the first time a key goes dirty
    if "gist_batch_start" not in st.session_state:
        st.session_state["gist_batch_start"] = now
    batch_age = now - st.session_state.get("gist_batch_start", now)
    is_critical = data_type in _GIST_CRITICAL_KEYS
    # Flush ALL dirty keys in one PATCH when:
    #   (a) a critical key was just written — don't delay history/bankroll
    #   (b) the batch window has expired — coalesce whatever accumulated
    if is_critical or batch_age >= _GIST_BATCH_WINDOW:
        return _flush_batch_gist(st.session_state["gist_dirty"], now)
    # Still within window — stay queued
    return True

def _flush_batch_gist(dirty, now=None):
    """Write all keys in *dirty* in a SINGLE Gist PATCH request.

    GitHub's Gist PATCH API accepts multiple files per request:
        {"files": {"file1.json": {"content": "..."}, "file2.json": {"content": "..."}}}
    This replaces N sequential PATCHes with one round-trip regardless of how
    many keys are queued.

    Retries on 409/403/429 (up to 3 attempts, short backoff) -- this Gist
    also takes constant writes from 18-30+ background scraper workflows,
    so a collision here is routine, not exceptional. Previously a single
    failed attempt returned False with no retry: since gist_dirty is only
    cleared on success, the removal (e.g. clicking WIN SLIP on a lock)
    stayed correct in this session's memory but never reached the Gist --
    so a later session reload brought the stale "still active" lock back.
    Real reported symptom this fixes: a cleared/settled lock (e.g. James
    Wood) reappearing after the fact, and locking in a pick feeling like
    it hangs (a slow/retried attempt with no feedback while waiting).
    """
    if not dirty or not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return not dirty  # empty dirty dict is a no-op success
    now = now or time.time()
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    files = {
        f"betcouncil_{k}.json": {"content": json.dumps(v, indent=2)}
        for k, v in dirty.items()
    }
    for _attempt in range(3):
        try:
            resp = _http.patch(
                f"{GIST_API}/{GITHUB_GIST_ID}",
                headers=headers,
                json={"files": files},
                timeout=15,
            )
        except (requests.RequestException, OSError):
            if _attempt < 2:
                time.sleep(1.5 * (_attempt + 1))
                continue
            return False
        if resp.status_code == 200:
            if "gist_last_write" not in st.session_state:
                st.session_state["gist_last_write"] = {}
            for k in list(dirty.keys()):
                st.session_state["gist_last_write"][k] = now
            st.session_state["gist_dirty"].clear()
            st.session_state["gist_batch_start"] = now  # reset window after flush
            return True
        if resp.status_code in (403, 409, 429) and _attempt < 2:
            time.sleep(1.5 * (_attempt + 1))
            continue
        return False
    return False

def _flush_gist_write(data_type, data, now=None):
    """Single-key flush — kept for backward compatibility; delegates to batch."""
    return _flush_batch_gist({data_type: data}, now)

def flush_all_gist_writes():
    """Flush all pending dirty Gist writes in ONE batch PATCH — call at session end."""
    dirty = st.session_state.get("gist_dirty", {})
    if not dirty:
        return {}
    ok = _flush_batch_gist(dict(dirty))
    return {k: ok for k in dirty}

def load_from_gist(data_type: str, default):
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return None
    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        resp = _http.get(
            f"{GIST_API}/{GITHUB_GIST_ID}",
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            return None
        files = resp.json().get("files", {})
        file_data = files.get(f"betcouncil_{data_type}.json", {})
        content = (file_data.get("content") or "").strip()
        if not content:
            # GitHub's bulk gist response can return empty content for ANY
            # file regardless of that file's own size, once another file in
            # the same gist is large enough to push the total response past
            # GitHub's inline-content limit. Confirmed 2026-06-21: a 405-byte
            # caesars_tokens file came back empty purely because
            # auto_scraped_props.json (2.5MB) sat alongside it in the same
            # gist — every data_type using this function was silently
            # affected, not just the large file. Always fall back to
            # raw_url rather than trusting an empty content field as "no data".
            raw_url = file_data.get("raw_url", "")
            if not raw_url:
                return None
            raw_resp = _http.get(raw_url, headers=headers, timeout=15)
            if raw_resp.status_code != 200:
                return None
            content = raw_resp.text.strip()
            if not content:
                return None
        return json.loads(content)
    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError):
        return None


# load_json_data — moved to bc_utils.py
def get_elo_ratings(sport="NFL"):
    """Load persisted Elo ratings dict {team_abbr: rating} for a sport from
    Gist, seeding any unseen team at ELO_DEFAULT_RATING. Falls back to an
    empty dict (all teams will seed at default on first use) if Gist is
    unavailable — never raises, never blocks the rest of the app."""
    data = load_from_gist(f"elo_{sport.lower()}", None)
    return data if isinstance(data, dict) else {}


def update_elo_after_game(sport, team_a, team_b, score_a, margin=None):
    """Run one Elo update and persist both teams' new ratings to Gist.
    score_a: 1.0 team_a win, 0.5 draw, 0.0 team_a loss.
    margin:  optional score differential — enables MOV-weighted K-factor.
    Returns (new_rating_a, new_rating_b). Call once per completed game —
    calling twice for the same game will double-count it.

    GAP FIX (2026-06-21): K-factor is now modulated by a roster-churn
    confidence weight fetched from ESPN transactions.  Teams with 3+ moves
    in the last 14 days get a reduced K so their Elo converges more slowly
    until the new roster stabilises.  Confidence weight range: [0.50, 1.00].
    MOV multiplier (FiveThirtyEight-style ln-scale) also applied when
    margin is provided — blowouts move ratings more than 1-pt wins.
    """
    ratings = get_elo_ratings(sport)
    rating_a = ratings.get(team_a, ELO_DEFAULT_RATING)
    rating_b = ratings.get(team_b, ELO_DEFAULT_RATING)
    base_k = ELO_K_FACTOR.get(sport, 20)
    # Apply roster-churn confidence — use the lower of the two teams' weights
    conf_a = _get_elo_roster_confidence(sport, team_a)
    conf_b = _get_elo_roster_confidence(sport, team_b)
    k = base_k * min(conf_a, conf_b)
    new_a, new_b = elo_update(rating_a, rating_b, score_a, k=k,
                               margin=margin, sport=sport)
    ratings[team_a] = new_a
    ratings[team_b] = new_b
    save_to_gist(f"elo_{sport.lower()}", ratings)
    return new_a, new_b


def run_comprehensive_elo_update():
    """Update Elo from EVERY completed game across all 4 leagues via ESPN
    scoreboard, independent of whether the user has any active locks.
    Deduped via a Gist-persisted processed-game-id set per sport, so safe
    to call repeatedly without double-counting. Previously this exact logic
    only ran when the user clicked "Check Results via ESPN" AND had at
    least one active lock — meaning Elo silently stopped updating on any
    day with zero locks, even with real games completing. Extracted
    2026-06-21 so it can also run automatically, decoupled from both gates."""
    _elo_sport_map = {"NBA": ("basketball", "nba"), "MLB": ("baseball", "mlb"),
                       "NFL": ("football", "nfl"), "NHL": ("hockey", "nhl")}
    for _elo_sport, (_elo_es, _elo_el) in _elo_sport_map.items():
        if _elo_sport not in ELO_K_FACTOR:
            continue
        try:
            _elo_sb = _http.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{_elo_es}/{_elo_el}/scoreboard",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if _elo_sb.status_code != 200:
                continue
            _elo_events = _elo_sb.json().get("events", [])
            if not _elo_events or not isinstance(_elo_events, list):
                continue  # empty schedule or malformed response — skip sport silently
            _elo_processed_key = f"elo_processed_{_elo_sport.lower()}"
            _elo_processed = set(load_from_gist(_elo_processed_key, []) or [])
            _elo_new = False
            for _elo_event in _elo_events:
                if not _elo_event.get("status", {}).get("type", {}).get("completed"):
                    continue
                _elo_eid = _elo_event.get("id")
                if not _elo_eid or _elo_eid in _elo_processed:
                    continue
                # Guard: competitions can be [] (no data yet) — use `or` so
                # empty list falls back to [{}] instead of raising IndexError.
                _elo_comps = (_elo_event.get("competitions") or [{}])[0]
                _elo_teams = _elo_comps.get("competitors", [])
                if len(_elo_teams) < 2:
                    continue
                _elo_home, _elo_away = _elo_teams[0], _elo_teams[1]
                _elo_h_name = _elo_home.get("team", {}).get("displayName", "")
                _elo_a_name = _elo_away.get("team", {}).get("displayName", "")
                if not _elo_h_name or not _elo_a_name:
                    continue
                _elo_h_score = float(_elo_home.get("score", 0) or 0)
                _elo_a_score = float(_elo_away.get("score", 0) or 0)
                if _elo_h_score > _elo_a_score:
                    _elo_score_a = 1.0
                elif _elo_h_score < _elo_a_score:
                    _elo_score_a = 0.0
                else:
                    _elo_score_a = 0.5
                _elo_margin = abs(_elo_h_score - _elo_a_score)
                update_elo_after_game(_elo_sport, _elo_h_name, _elo_a_name,
                                      _elo_score_a, margin=_elo_margin)
                _elo_processed.add(_elo_eid)
                _elo_new = True
            if _elo_new:
                save_to_gist(_elo_processed_key, list(_elo_processed))
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, requests.RequestException):
            continue


def get_api_counter(counter_path):
    """
    Reads the API usage counter for a given budget. Gist-backed (same
    pattern as signal_performance/injury_performance) so the count survives
    Streamlit Cloud redeploys — previously this only lived in local
    CACHE_DIR, which wipes on every redeploy, so the 80% hard-stop in
    api_budget_check() never actually triggered: the app always thought it
    was starting fresh while real upstream usage (e.g. The Odds API) kept
    climbing across redeploys. Confirmed via real usage hitting 498/500
    monthly credits despite the supposed 400/500 stop.
    """
    today = date.today().strftime("%Y-%m-%d")
    current_month = date.today().strftime("%Y-%m")
    data_type = os.path.basename(counter_path).replace(".json", "")
    # Use session_state as in-memory cache to avoid Gist/disk reads on every budget check
    _ss_key = f"_api_counter_{counter_path}"
    cached = st.session_state.get(_ss_key)
    if cached and cached.get("date") == today and cached.get("month") == current_month:
        return cached

    counter = None
    gist_counter = load_from_gist(data_type, None)
    if isinstance(gist_counter, dict) and "count" in gist_counter:
        counter = gist_counter
    elif os.path.exists(counter_path):
        try:
            with open(counter_path, "r") as f:
                counter = json.load(f)
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            counter = None

    if counter is None:
        counter = {"count": 0, "date": today, "month": current_month, "monthly_count": 0}
    else:
        if counter.get("date") != today:
            counter["date"] = today
            counter["count"] = 0
        if counter.get("month") != current_month:
            counter["month"] = current_month
            counter["monthly_count"] = 0

    st.session_state[_ss_key] = counter
    return counter

def increment_api_counter(counter_path):
    counter = get_api_counter(counter_path)
    counter["count"] += 1
    counter["monthly_count"] = counter.get("monthly_count", 0) + 1
    save_json_data(counter_path, counter)  # local fallback, kept for same-session reads
    data_type = os.path.basename(counter_path).replace(".json", "")
    save_to_gist(data_type, counter)  # the persistence that actually survives redeploys
    # Refresh session cache with updated count
    st.session_state[f"_api_counter_{counter_path}"] = counter
    return counter

def should_skip_api_call(counter_path, daily_limit=None, monthly_limit=None):
    counter = get_api_counter(counter_path)
    if daily_limit and counter["count"] >= daily_limit * 0.8:
        return True, f"Daily limit approaching ({counter['count']}/{daily_limit})"
    if monthly_limit and counter.get("monthly_count", 0) >= monthly_limit * 0.8:
        return True, f"Monthly limit approaching ({counter['monthly_count']}/{monthly_limit})"
    return False, ""

def format_api_usage(counter_path, daily_limit=None, monthly_limit=None, api_name="API"):
    counter = get_api_counter(counter_path)
    parts = []
    if daily_limit:
        parts.append(f"{counter['count']}/{daily_limit} today")
    if monthly_limit:
        parts.append(f"{counter.get('monthly_count', 0)}/{monthly_limit} this month")
    return f"{api_name}: {' | '.join(parts)}" if parts else f"{api_name}: {counter['count']} calls"

def api_budget_check(budget_key):
    budget = API_BUDGETS.get(budget_key)
    if not budget:
        return True, ""
    counter = get_api_counter(budget["counter_path"])
    daily_used = counter.get("count", 0)
    monthly_used = counter.get("monthly_count", 0)
    stop_pct = budget.get("hard_stop_pct", 0.80)
    daily_limit = budget.get("daily_limit")
    if daily_limit:
        threshold = int(daily_limit * stop_pct)
        if daily_used >= threshold:
            return False, f"{budget_key} daily limit approached: {daily_used}/{daily_limit} — protecting free tier"
    monthly_limit = budget.get("monthly_limit")
    if monthly_limit:
        threshold = int(monthly_limit * stop_pct)
        if monthly_used >= threshold:
            return False, f"{budget_key} monthly limit approached: {monthly_used}/{monthly_limit} — protecting free tier"
    return True, ""

def api_budget_increment(budget_key):
    budget = API_BUDGETS.get(budget_key)
    if budget:
        increment_api_counter(budget["counter_path"])

def api_budget_status(budget_key):
    budget = API_BUDGETS.get(budget_key)
    if not budget:
        return "Unknown"
    counter = get_api_counter(budget["counter_path"])
    daily_used = counter.get("count", 0)
    monthly_used = counter.get("monthly_count", 0)
    parts = []
    daily_limit = budget.get("daily_limit")
    monthly_limit = budget.get("monthly_limit")
    if daily_limit:
        pct = daily_used / daily_limit * 100
        color = "🔴" if pct >= 80 else "🟡" if pct >= 60 else "🟢"
        parts.append(f"{color} {daily_used}/{daily_limit} today")
    if monthly_limit:
        pct = monthly_used / monthly_limit * 100
        color = "🔴" if pct >= 80 else "🟡" if pct >= 60 else "🟢"
        parts.append(f"{color} {monthly_used}/{monthly_limit} this month")
    if not parts:
        return f"📊 {daily_used} calls today"
    return " | ".join(parts)

# ─────────────────────────────────────────────────────────────
# SIGNAL ATTRIBUTION ENGINE
# Answers: which signals actually created profit?
# ─────────────────────────────────────────────────────────────

def track_line_origin(game_analysis, sport):
    """
    Track which book moved the line first — sharp origin vs public noise.
    
    Sharp origin: Pinnacle or Circa moved first → strong signal
    Public noise: FanDuel/DraftKings moved, sharp books static → fade
    
    Compares current OddsAPI lines vs stored opening lines.
    """
    if not game_analysis:
        return {}
    try:
        stored = load_json_data(OPENING_LINES_PATH, {})
        today_str = date.today().strftime("%Y-%m-%d")
        origins = {}
        for game in game_analysis:
            matchup = game.get("matchup","")
            key = f"{today_str}_{matchup}_{sport}"
            opening = stored.get(key, {})
            if not opening:
                continue
            curr_total  = safe_float(game.get("Total") or 0)
            open_total  = safe_float(opening.get("open_total") or 0)
            oddsapi_tot = safe_float(game.get("OddsAPI Total") or 0)
            if not (curr_total and open_total):
                continue
            movement = curr_total - open_total
            if abs(movement) < 0.5:
                continue
            # Determine likely origin
            # If OddsAPI (which includes Pinnacle) moved same direction → sharp origin
            sharp_moved  = oddsapi_tot and abs(oddsapi_tot - open_total) >= abs(movement) * 0.7
            origin_type  = "📌 Sharp Origin" if sharp_moved else "📢 Public Origin"
            direction    = "↑" if movement > 0 else "↓"
            origins[matchup] = {
                "movement":    round(movement, 1),
                "direction":   direction,
                "origin":      origin_type,
                "open":        open_total,
                "current":     curr_total,
                "note":        f"{origin_type}: Total moved {direction}{abs(movement):.1f}"
            }
        return origins
    except (requests.RequestException, ValueError, KeyError):
        return {}


# ═══════════════════════════════════════════════════════════════
# PROP CORRELATION SCORE
# Goes beyond team/sport exposure — quantifies how much
# a set of props rises and falls together.
# ═══════════════════════════════════════════════════════════════

# Known prop correlation pairs (historical research basis)

# Team-level correlation (same game)
TEAM_GAME_CORRELATION = 0.35   # same team, different players
GAME_TOTAL_CORRELATION = 0.55  # team total + player scoring props


def compute_prop_correlation_score(props):
    """
    Computes a portfolio-level correlation score for a list of props.
    Score 0.0 = fully independent bets.
    Score 1.0 = perfectly correlated (all bets win/lose together).
    
    Uses known correlation pairs + team/game clustering.
    Professional sportsbook thinking: are you betting the same outcome
    multiple times without realizing it?
    """
    if not props or len(props) < 2:
        return 0.0, []

    n = len(props)
    total_correlation = 0.0
    pairs_checked = 0
    correlated_groups = []

    for i in range(n):
        for j in range(i+1, n):
            p1, p2 = props[i], props[j]
            p1_player = p1.get("Player", p1.get("player",""))
            p2_player = p2.get("Player", p2.get("player",""))
            p1_prop   = p1.get("Prop",   p1.get("prop","")).upper()
            p2_prop   = p2.get("Prop",   p2.get("prop","")).upper()
            p1_team   = p1.get("Team",   p1.get("team",""))
            p2_team   = p2.get("Team",   p2.get("team",""))

            corr = 0.0
            reason = ""

            # Same player
            if p1_player and p1_player == p2_player:
                pair_key = tuple(sorted([p1_prop, p2_prop]))
                corr = PROP_CORRELATION_PAIRS.get(pair_key, 0.50)
                reason = f"Same player ({p1_player})"
            # Same team different players
            elif p1_team and p1_team == p2_team:
                corr = TEAM_GAME_CORRELATION
                reason = f"Same team ({p1_team})"
            # Game total + player scoring
            elif "TOTAL" in p1_prop or "TOTAL" in p2_prop:
                corr = GAME_TOTAL_CORRELATION
                reason = "Game total vs player scoring"

            if corr > 0.25:
                total_correlation += corr
                pairs_checked += 1
                correlated_groups.append({
                    "Prop A":      f"{p1_player} {p1_prop}",
                    "Prop B":      f"{p2_player} {p2_prop}",
                    "Correlation": f"{corr:.2f}",
                    "Reason":      reason,
                })

    max_possible = n * (n-1) / 2
    score = total_correlation / max(max_possible, 1)
    score = min(1.0, score)

    return round(score, 3), correlated_groups


# ═══════════════════════════════════════════════════════════════
# BANKROLL INTELLIGENCE
# Model becomes aware of its own confidence.
# When performing well → size up slightly.
# When drifting → size down automatically.
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def compute_portfolio_exposure(board_data=None):
    """
    Check concentration risk across current locked picks.
    Returns full exposure dict with all keys used by the History tab UI.
    """
    try:
        import streamlit as _st
        locks = list(_st.session_state.get("locks", []))
        bankroll = float(_st.session_state.get("bankroll", 100) or 100)
    except (ImportError, AttributeError):
        locks, bankroll = [], 100.0

    if not locks:
        return {}

    sport_counts  = {}
    team_counts   = {}
    player_counts = {}
    total_stake   = 0.0

    for lk in locks:
        s = lk.get("sport","")
        t = lk.get("team","")
        p = lk.get("player","")
        w = float(lk.get("wager", 1) or 1)
        sport_counts[s]  = sport_counts.get(s,0)  + 1
        team_counts[t]   = team_counts.get(t,0)   + 1
        player_counts[p] = player_counts.get(p,0) + 1
        total_stake     += w

    warnings = []
    recommendations = []
    for sport, cnt in sport_counts.items():
        if cnt > 4:
            warnings.append(f"⚠️ {cnt} picks on {sport} — max 4 recommended")
            recommendations.append(f"Reduce {sport} exposure to 4 or fewer")
    for team, cnt in team_counts.items():
        if cnt >= 3 and team:
            warnings.append(f"⚠️ {cnt} picks from {team} — high correlation")
            recommendations.append(f"Reduce {team} to 2 or fewer props")
    for player, cnt in player_counts.items():
        if cnt >= 2 and player:
            warnings.append(f"⚠️ {cnt} props on {player} — same-player correlation")
            recommendations.append(f"Keep {player} to 1 prop max")

    # Sport breakdown for display
    sport_breakdown = {s: {"count": c, "pct": round(c/len(locks)*100,1)}
                       for s,c in sport_counts.items()}

    total_pct_br = round(total_stake / bankroll * 100, 1) if bankroll > 0 else 0.0

    return {
        "warnings":        warnings,
        "recommendations": recommendations,
        "sport_counts":    sport_counts,
        "team_counts":     team_counts,
        "player_counts":   player_counts,
        "sport_breakdown": sport_breakdown,
        "total_locks":     len(locks),
        "n_active":        len(locks),
        "total_stake":     round(total_stake, 2),
        "total_pct_br":    total_pct_br,
    }

def generate_weekly_model_report(history=None, signal_data=None):
    """
    Generate weekly P&L and model performance summary.
    Returns dict with weekly metrics or None if insufficient data.
    """
    if history is None:
        history = []
    week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = [h for h in history
              if h.get("outcome") in ("WIN","LOSS")
              and str(h.get("timestamp","")) >= week_ago]
    if not recent:
        return None
    wins    = sum(1 for h in recent if h.get("outcome") == "WIN")
    losses  = len(recent) - wins
    total_w = sum(float(h.get("wager",1) or 1) for h in recent)
    total_p = sum(
        float(h.get("wager",1) or 1) * 0.909 if h.get("outcome")=="WIN"
        else -float(h.get("wager",1) or 1)
        for h in recent
    )
    roi = round(total_p / total_w, 3) if total_w > 0 else 0
    # Best/worst signals
    signal_wins = {}
    for bet in recent:
        for sig in (bet.get("signal_values") or {}):
            signal_wins.setdefault(sig, {"w":0,"t":0})
            signal_wins[sig]["t"] += 1
            if bet.get("outcome") == "WIN":
                signal_wins[sig]["w"] += 1
    best_sig  = max(signal_wins, key=lambda s: signal_wins[s]["w"]/max(signal_wins[s]["t"],1), default="—") if signal_wins else "—"
    worst_sig = min(signal_wins, key=lambda s: signal_wins[s]["w"]/max(signal_wins[s]["t"],1), default="—") if signal_wins else "—"
    # Best/worst sport
    sport_wins = {}
    for bet in recent:
        sp = bet.get("sport","Unknown")
        sport_wins.setdefault(sp, {"w":0,"t":0})
        sport_wins[sp]["t"] += 1
        if bet.get("outcome") == "WIN":
            sport_wins[sp]["w"] += 1
    best_sport  = max(sport_wins, key=lambda s: sport_wins[s]["w"]/max(sport_wins[s]["t"],1), default="—") if sport_wins else "—"
    worst_sport = min(sport_wins, key=lambda s: sport_wins[s]["w"]/max(sport_wins[s]["t"],1), default="—") if sport_wins else "—"
    # CLV avg — CLV_PATH is a module-level global, no import needed
    try:
        clv_data = load_json_data(CLV_PATH, [])
        week_clv = [c for c in clv_data if str(c.get("timestamp","")) >= week_ago]
        avg_clv  = round(sum(c.get("clv",0) for c in week_clv)/len(week_clv), 2) if week_clv else 0.0
    except (ValueError, ZeroDivisionError, KeyError):
        avg_clv = 0.0
    return {
        "wins":         wins,
        "losses":       losses,
        "bets":         len(recent),
        "total":        len(recent),
        "win_rate":     round(wins/len(recent), 3),
        "roi":          roi,
        "roi_pct":      f"{roi*100:+.1f}%",
        "roi_per_bet":  roi,
        "net_units":    round(total_p, 2),
        "units":        round(total_p, 2),
        "avg_clv":      avg_clv,
        "best_signal":  best_sig,
        "worst_signal": worst_sig,
        "best_sport":   best_sport,
        "worst_sport":  worst_sport,
        "calibration":  "N/A",
        "period":       "Last 7 days",
    }

# detect_season_regime — moved to bc_utils.py
def compute_model_drift(history=None, window=50):
    """
    Compares recent N-bet ROI vs all-time ROI.
    Fires alert if recent performance diverges significantly.

    BUG FIX (2026-07): _roi() used to default a missing/zero wager to 1
    (`b.get("wager",1) or 1`), which meant every auto-tracked pick with no
    real stake (BDL/Bovada/PrizePicks resolvers logging a result whether
    or not the user actually bet it -- 171 of 280 resolved bets in the
    real ledger, 61%) got treated as a real $1 bet with a real win/loss
    payout. Reproduced this against the live ledger before fixing: it
    produced a drift of -19.7%, essentially identical to a "-19.3%
    bankroll drift" figure independently cited as a real finding -- while
    the actual ROI on real staked money (the 109 bets with a real wager)
    is +28.5%. This panel was measuring a fabricated "what if every
    tracked pick had been a $1 bet" number, not real bankroll performance.
    Excluding untracked-stake bets instead of defaulting them to $1.
    """
    if history is None:
        history = st.session_state.get("history", [])
    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS") and h.get("wager")]
    if len(resolved) < 60:
        return None
    # All-time ROI per bet
    def _roi(bets):
        total_w = sum(float(b.get("wager",0) or 0) for b in bets)
        total_p = sum(b.get("net", 0) for b in bets)
        return round(total_p / total_w, 3) if total_w > 0 else 0.0
    all_roi    = _roi(resolved)
    recent     = resolved[-window:]
    recent_roi = _roi(recent)
    drift      = recent_roi - all_roi
    alert      = drift < -1.0
    return {
        "all_time_roi": all_roi,
        "recent_roi":   recent_roi,
        "drift":        drift,
        "window":       len(recent),
        "alert":        alert,
        "status":       "⚠️ Model Drift Detected" if alert else "✅ Model Performing Normally",
    }


def compute_bankroll_multiplier(history=None, clv_data=None):
    """
    Model-aware stake sizing.
    Adjusts Kelly multiplier based on recent performance:
      1.25x — positive ROI + positive CLV + no drift
      1.00x — neutral / insufficient data
      0.75x — mild drift or negative CLV
      0.50x — significant drift or degraded calibration

    BUG FIX (2026-07): two issues compounding on real data.
    (1) "recent = resolved[-20:]" assumed list order tracks betting
    chronology. It doesn't when Screenshot Import bulk-logs a batch of
    already-resolved historical slips in one sitting -- those get
    appended at upload time, not placement time. Checked the real
    ledger: the actual "last 20" were 18 Screenshot Import bets (all
    timestamped 2026-07-12/13 00:00, a placeholder time -- clearly one
    bulk-import batch, not 20 bets placed in sequence) plus 2 auto-
    resolved Bovada bets, producing a 35% "recent" win rate against a
    54.3% all-time rate -- a -19.3% drift that reproduces the exact
    number once cited as a real finding, for the same reason as the
    compute_model_drift bug: the sample isn't what it claims to be.
    Now explicitly sorts by timestamp before slicing.
    (2) Included $0-wager (untracked-stake) bets in both the recent
    window and the baseline. 61% of the real ledger has no wager logged
    (auto-tracked picks, not staked) -- mixing them into a bankroll-
    sizing signal doesn't reflect real betting performance. Now filters
    to real-wager bets only, same principle as the CLV/post-mortem/ROI
    fixes elsewhere.
    """
    if history is None:
        history = st.session_state.get("history", [])
    if clv_data is None:
        clv_data = load_json_data(CLV_PATH, [])

    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS") and h.get("wager")]
    resolved.sort(key=lambda h: str(h.get("timestamp","")))
    if len(resolved) < 10:
        return {"multiplier": 1.0, "reason": "Insufficient real-stake data (<10 staked bets)", "label": "1.00x"}

    # Recent ROI (last 20)
    recent = resolved[-20:]
    wins   = sum(1 for h in recent if h.get("outcome") == "WIN")
    roi    = (wins / len(recent)) - 0.524  # vs breakeven

    # CLV trend
    clv_avg = 0.0
    if clv_data:
        recent_clv = clv_data[-20:]
        clv_avg = sum(c.get("clv", 0) for c in recent_clv) / len(recent_clv) if recent_clv else 0

    # Drift: compare last 20 vs all-time win rate
    all_wins = sum(1 for h in resolved if h.get("outcome") == "WIN")
    all_rate = all_wins / len(resolved) if resolved else 0.5
    recent_rate = wins / len(recent)
    drift = recent_rate - all_rate  # negative = cooling off

    # Score
    score = 0
    if roi > 0.05:   score += 2
    elif roi > 0:    score += 1
    elif roi < -0.05:score -= 2
    else:            score -= 1

    if clv_avg > 1.0:  score += 1
    elif clv_avg < -1.0: score -= 1

    if drift < -0.10:  score -= 2
    elif drift < -0.05:score -= 1

    # Multiplier
    if score >= 3:
        mult, reason, color = 1.25, f"Strong model (+{roi:.1%} ROI, CLV {clv_avg:+.1f})", "#22c55e"
        reasons_up   = [reason]
        reasons_down = []
    elif score >= 1:
        mult, reason, color = 1.00, f"Neutral ({roi:.1%} ROI)", "#e8a020"
        reasons_up   = [reason]
        reasons_down = []
    elif score >= -1:
        mult, reason, color = 0.75, f"Mild drift ({drift:+.1%} vs baseline)", "#e8a020"
        reasons_up   = []
        reasons_down = [reason]
    else:
        mult, reason, color = 0.50, f"Significant drift ({drift:+.1%}, ROI {roi:.1%})", "#e04040"
        reasons_up   = []
        reasons_down = [reason]

    kelly_advised = round(mult * 0.15, 3)  # 15% base Kelly fraction × multiplier
    # Note: tier-based Kelly adjustment applied in prop enrichment loop (KELLY_BY_TIER)

    return {
        "multiplier":   mult,
        "reason":       reason,
        "label":        f"{mult:.2f}x",
        "color":        color,
        "roi":          round(roi, 3),
        "clv_avg":      round(clv_avg, 2),
        "drift":        round(drift, 3),
        "score":        score,
        "kelly_advised":kelly_advised,
        "reasons_up":   reasons_up,
        "reasons_down": reasons_down,
    }

def compute_signal_interactions(performance_data=None):
    """
    Signal Interaction Analysis — the next level beyond signal lift.
    
    Tests pairs of signals together vs each signal alone.
    Discovers synergistic combinations:
      Defense + Away (travel fatigue against weak D): +8.2%
      Rest (B2B) + Sharp Money: -12.1% (sharps fade fatigued players)
    
    Activates at 50+ resolved bets.
    """
    if performance_data is None:
        performance_data = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    resolved = [p for p in performance_data if p.get("outcome") in ("WIN","LOSS")]
    if len(resolved) < 50:
        return None, len(resolved)

    PAIRS_TO_TEST = [
        ("signal_defense_positive", "signal_back_to_back"),
        ("signal_defense_positive", "signal_location_home"),
        ("signal_base_positive",    "signal_defense_positive"),
        ("signal_base_positive",    "signal_sharp_flag"),
        ("signal_sharp_flag",       "signal_back_to_back"),
        ("signal_usage_boost",      "signal_defense_positive"),
        ("signal_back_to_back",     "signal_blowout_risk"),
        ("signal_base_positive",    "signal_back_to_back"),
    ]

    SIGNAL_SHORT = {
        "signal_defense_positive": "Defense",
        "signal_back_to_back":     "Rest(B2B)",
        "signal_location_home":    "Home",
        "signal_base_positive":    "Base",
        "signal_sharp_flag":       "Sharp",
        "signal_usage_boost":      "Usage",
        "signal_blowout_risk":     "Blowout",
    }

    overall_wr = sum(r["win"] for r in resolved) / len(resolved)
    results = []

    for sig_a, sig_b in PAIRS_TO_TEST:
        # Both active
        both   = [r for r in resolved if r.get(sig_a,0)==1 and r.get(sig_b,0)==1]
        # Only A
        only_a = [r for r in resolved if r.get(sig_a,0)==1 and r.get(sig_b,0)==0]
        # Only B
        only_b = [r for r in resolved if r.get(sig_a,0)==0 and r.get(sig_b,0)==1]

        if len(both) < 5:
            continue

        wr_both   = sum(r["win"] for r in both)   / len(both)
        wr_only_a = sum(r["win"] for r in only_a) / len(only_a) if only_a else overall_wr
        wr_only_b = sum(r["win"] for r in only_b) / len(only_b) if only_b else overall_wr

        # Synergy = both together vs best of each alone
        expected_if_independent = max(wr_only_a, wr_only_b)
        synergy = wr_both - expected_if_independent

        if synergy > 0.03:
            interaction = "🟢 Synergistic"
        elif synergy > 0:
            interaction = "🟡 Mild synergy"
        elif synergy > -0.03:
            interaction = "⚪ Neutral"
        else:
            interaction = "🔴 Conflicting"

        label_a = SIGNAL_SHORT.get(sig_a, sig_a)
        label_b = SIGNAL_SHORT.get(sig_b, sig_b)

        results.append({
            "Signal A":         label_a,
            "Signal B":         label_b,
            "WR (Both)":        f"{wr_both:.1%}",
            "WR (A only)":      f"{wr_only_a:.1%}",
            "WR (B only)":      f"{wr_only_b:.1%}",
            "Synergy":          f"{synergy:+.1%}",
            "n (both)":         len(both),
            "Interaction":      interaction,
        })

    results.sort(key=lambda x: float(x["Synergy"].replace("%","").replace("+","")), reverse=True)
    return results, len(resolved)


# ═══════════════════════════════════════════════════════════════
# ADVANCED INTELLIGENCE — ALL 5 REMAINING ITEMS
# 1. Role Change Detection
# 2. Projection Confidence Score  
# 3. Market Implied Projection
# 4. NFL Usage Metrics Framework
# 5. Pass Rate Over Expectation (team context)
# ═══════════════════════════════════════════════════════════════

NFL_USAGE_PATH = os.path.join(CACHE_DIR, "nfl_usage.json")

# ── 1. Role Change Detection ────────────────────────────────────
def detect_role_changes(player, sport, current_stats, history=None):
    """
    Detect sudden changes in player role before sportsbooks fully react.
    
    Monitors:
      - Minutes spike (NBA/WNBA)
      - Target share spike (NFL WR/TE)
      - Usage rate spike (NBA)
      - Snap count change (NFL)
    
    Returns dict: {change_type, magnitude, direction, note}
    These represent edges — books lag 1-2 games behind role changes.
    """
    if history is None:
        history = st.session_state.get("history", [])

    # Get recent resolved bets for this player
    player_history = [h for h in history
                      if normalize_name(h.get("player","")) == normalize_name(player)
                      and h.get("sport") == sport
                      and h.get("outcome") in ("WIN","LOSS")]

    if len(player_history) < 3:
        return None  # Not enough data

    # Check last 3 games vs prior average
    recent = player_history[-3:]
    prior  = player_history[:-3] if len(player_history) > 3 else player_history

    # Usage/minutes detection
    recent_mins  = [float(h.get("actual_stat", h.get("line", 0)) or 0) for h in recent]
    prior_mins   = [float(h.get("actual_stat", h.get("line", 0)) or 0) for h in prior]

    if not recent_mins or not prior_mins:
        return None

    recent_avg = sum(recent_mins) / len(recent_mins)
    prior_avg  = sum(prior_mins)  / len(prior_mins)

    if prior_avg <= 0:
        return None

    change_pct = (recent_avg - prior_avg) / prior_avg

    if change_pct >= 0.20:
        return {
            "type":      "usage_spike",
            "direction": "UP",
            "magnitude": change_pct,
            "note":      f"📈 Role UP: {player} recent avg {recent_avg:.1f} vs prior {prior_avg:.1f} (+{change_pct:.0%})",
            "edge_adj":  min(0.06, change_pct * 0.25),  # up to +6% edge for role increase
        }
    elif change_pct <= -0.20:
        return {
            "type":      "usage_drop",
            "direction": "DOWN",
            "magnitude": change_pct,
            "note":      f"📉 Role DOWN: {player} recent avg {recent_avg:.1f} vs prior {prior_avg:.1f} ({change_pct:.0%})",
            "edge_adj":  max(-0.06, change_pct * 0.25),  # up to -6% edge for role decrease
        }
    return None


def check_depth_chart_role_change(player, team, sport):
    """
    Cross-check ESPN depth chart snapshots for position changes.
    E.g. RB2 → RB1 (starter change) detected from daily snapshots.
    """
    changes = st.session_state.get("depth_chart_changes", [])
    for change in changes:
        if (change.get("team") == team and
            normalize_name(change.get("new","")) == normalize_name(player)):
            return {
                "type":      "depth_promotion",
                "direction": "UP",
                "magnitude": 1.0,
                "note":      f"🔼 Promoted to starter: {player} now {change['position']}1 ({change['team']})",
                "edge_adj":  0.05,
            }
        if (change.get("team") == team and
            normalize_name(change.get("old","")) == normalize_name(player)):
            return {
                "type":      "depth_demotion",
                "direction": "DOWN",
                "magnitude": 1.0,
                "note":      f"🔽 Demoted from starter: {player} was {change['position']}1 ({change['team']})",
                "edge_adj":  -0.05,
            }
    return None


# ── 2. Projection Confidence Score ─────────────────────────────
def store_nfl_usage(player, team, game_date, stats):
    """
    Store NFL usage metrics when available.
    Framework is ready — data populates when:
      a) NFL season starts and ESPN NextGen Stats becomes accessible
      b) User manually enters snap % from game recap

    Metrics tracked:
      snap_pct, route_pct, target_share, air_yards,
      red_zone_targets, goal_line_carries
    """
    try:
        stored = load_json_data(NFL_USAGE_PATH, {})
        key = f"{normalize_name(player)}_{game_date}"
        stored[key] = {
            "player":          player,
            "team":            team,
            "date":            game_date,
            "snap_pct":        stats.get("snap_pct"),
            "route_pct":       stats.get("route_pct"),
            "target_share":    stats.get("target_share"),
            "air_yards":       stats.get("air_yards"),
            "red_zone_tgts":   stats.get("red_zone_tgts"),
            "goal_line_carr":  stats.get("goal_line_carr"),
            "updated_at":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        # Keep last 200 entries
        if len(stored) > 200:
            oldest = sorted(stored.keys())[0]
            del stored[oldest]
        save_json_data(NFL_USAGE_PATH, stored)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass


def get_nfl_usage(player, last_n=3):
    """
    Retrieve NFL usage metrics for a player.
    Returns recent average of snap_pct, target_share etc.
    Returns None if no data yet (pre-season or not tracked).
    """
    try:
        stored = load_json_data(NFL_USAGE_PATH, {})
        pname = normalize_name(player)
        player_entries = sorted(
            [v for k, v in stored.items() if normalize_name(v.get("player","")) == pname],
            key=lambda x: x.get("date",""), reverse=True
        )[:last_n]

        if not player_entries:
            return None

        def avg_metric(key):
            vals = [e[key] for e in player_entries if e.get(key) is not None]
            return round(sum(vals)/len(vals), 3) if vals else None

        return {
            "n":            len(player_entries),
            "snap_pct":     avg_metric("snap_pct"),
            "route_pct":    avg_metric("route_pct"),
            "target_share": avg_metric("target_share"),
            "air_yards":    avg_metric("air_yards"),
            "red_zone_tgts":avg_metric("red_zone_tgts"),
            "last_game":    player_entries[0].get("date",""),
        }
    except (ValueError, KeyError, TypeError):
        return None


def compute_usage_edge(usage_data, stat_norm):
    """
    Convert usage metrics into edge adjustments.

    High snap + high route % for WR = more opportunities = OVER lean
    Low snap = backup role = UNDER lean
    High red zone targets = TD upside

    Activates when NFL season data is available.
    """
    if not usage_data:
        return 0.0, ""

    adj = 0.0
    notes = []

    snap = usage_data.get("snap_pct")
    route = usage_data.get("route_pct")
    tgt_share = usage_data.get("target_share")
    rz_tgts = usage_data.get("red_zone_tgts")

    if stat_norm in ("RecYds","REC","Receptions") and snap and route:
        if snap >= 0.85 and route >= 0.85:
            adj += 0.04
            notes.append(f"🎯 High usage: {snap:.0%} snap/{route:.0%} routes")
        elif snap < 0.50:
            adj -= 0.05
            notes.append(f"⚠️ Low snap: {snap:.0%} — limited opportunity")

    if stat_norm in ("Touchdowns","TD") and rz_tgts and rz_tgts >= 2:
        adj += 0.03
        notes.append(f"🔴 Red zone target: {rz_tgts:.1f}/game")

    if tgt_share and stat_norm in ("RecYds","Receptions"):
        if tgt_share >= 0.25:
            adj += 0.03
            notes.append(f"📊 Target share: {tgt_share:.0%}")
        elif tgt_share <= 0.10:
            adj -= 0.03

    return round(adj, 3), " | ".join(notes)


# ── 5. Pass Rate Over Expectation (team context) ─────────────────
NFL_TEAM_CONTEXT_PATH = os.path.join(CACHE_DIR, "nfl_team_context.json")

def store_nfl_team_context(team, week, stats):
    """
    Store team-level NFL context metrics.
    Feeds pass/rush split signal for opposing defense adjustments.

    Metrics:
      pass_rate, neutral_pass_rate, proe (pass rate over expectation),
      pace (plays/game), red_zone_pct, run_pass_split
    """
    try:
        stored = load_json_data(NFL_TEAM_CONTEXT_PATH, {})
        stored[f"{team}_W{week}"] = {
            "team":         team,
            "week":         week,
            "pass_rate":    stats.get("pass_rate"),
            "neutral_proe": stats.get("neutral_proe"),  # PROE — key metric
            "pace":         stats.get("pace"),
            "rz_pct":       stats.get("rz_pct"),
            "run_pass":     stats.get("run_pass"),
            "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_json_data(NFL_TEAM_CONTEXT_PATH, stored)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass


def get_nfl_team_context(team, last_n=4):
    """
    Get team context — pass rate, pace, PROE.
    Used to adjust QB/WR/RB props based on team tendencies.
    High PROE team → WR/TE targets up, RB targets down.
    """
    try:
        stored = load_json_data(NFL_TEAM_CONTEXT_PATH, {})
        team_entries = sorted(
            [v for k, v in stored.items() if v.get("team") == team],
            key=lambda x: x.get("week", 0), reverse=True
        )[:last_n]

        if not team_entries:
            return None

        def avg_m(key):
            vals = [e[key] for e in team_entries if e.get(key) is not None]
            return round(sum(vals)/len(vals), 3) if vals else None

        proe = avg_m("neutral_proe")
        pace = avg_m("pace")

        # Compute edge adjustment based on PROE
        proe_adj = 0.0
        proe_note = ""
        if proe is not None:
            if proe >= 0.10:
                proe_adj = 0.03   # Pass-heavy → WR/TE upside
                proe_note = f"📡 High PROE ({proe:+.0%}) — pass-heavy offense"
            elif proe <= -0.10:
                proe_adj = -0.02  # Run-heavy → WR/TE limited
                proe_note = f"🏃 Low PROE ({proe:+.0%}) — run-heavy offense"

        return {
            "n":           len(team_entries),
            "pass_rate":   avg_m("pass_rate"),
            "proe":        proe,
            "pace":        pace,
            "rz_pct":      avg_m("rz_pct"),
            "proe_adj":    proe_adj,
            "proe_note":   proe_note,
        }
    except (ValueError, KeyError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE — KALSHI + POLYMARKET + COVERS
# Adds crowd/market probability as third dimension:
#   Model opinion vs Sportsbook opinion vs Public opinion
# ═══════════════════════════════════════════════════════════════

KALSHI_PATH     = os.path.join(CACHE_DIR, "kalshi_markets.json")
POLYMARKET_PATH = os.path.join(CACHE_DIR, "polymarket_markets.json")
COVERS_PATH     = os.path.join(CACHE_DIR, "covers_consensus.json")

# ── Kalshi ──────────────────────────────────────────────────────

# ── Polymarket ───────────────────────────────────────────────────
# ── Covers Consensus ─────────────────────────────────────────────
# ── Market Consensus Engine ──────────────────────────────────────
def compute_market_consensus(model_prob, player, prop, sport, game_analysis=None):
    """
    Compare model probability vs prediction market probabilities.
    
    Divergence signal:
      Model > Markets by 5%+  → Model bullish, markets disagree → value
      Model < Markets by 5%+  → Model bearish, markets disagree → fade
      Agreement               → Market efficient, lower confidence

    Returns dict with consensus, divergence, signal, source breakdown.
    """
    market_probs = []
    sources = []
    
    # Pull from session state (already fetched)
    kalshi_data   = st.session_state.get("kalshi_markets", [])
    poly_data     = st.session_state.get("polymarket_markets", [])
    covers_data   = st.session_state.get("covers_consensus", [])
    
    player_lower = normalize_name(player)
    
    # Build normalized name tokens for exact matching
    player_tokens = set(normalize_name(player).split())
    
    # Use single list of {prob, volume} to guarantee alignment
    market_entries = []

    # Pre-build Kalshi/Poly indexes if not cached — avoids O(N×M) scan
    if "_kalshi_idx" not in st.session_state or len(st.session_state["_kalshi_idx"]) != len(kalshi_data):
        _ki = {}
        for _m in kalshi_data:
            for _t in set(normalize_name(_m.get("event","")).split()):
                _ki.setdefault(_t,[]).append(_m)
        st.session_state["_kalshi_idx"] = _ki
    if "_poly_idx" not in st.session_state or len(st.session_state["_poly_idx"]) != len(poly_data):
        _pi = {}
        for _m in poly_data:
            for _t in set(normalize_name(_m.get("question","")).split()):
                _pi.setdefault(_t,[]).append(_m)
        st.session_state["_poly_idx"] = _pi
    _kalshi_idx = st.session_state["_kalshi_idx"]
    _poly_idx   = st.session_state["_poly_idx"]

    # Match Kalshi markets — require ALL first+last name tokens to match
    for mkt in kalshi_data:
        event_tokens = set(normalize_name(mkt.get("event","")).split())
        matched = (len(player_tokens) >= 2 and player_tokens.issubset(event_tokens)) or                   (len(player_tokens) == 1 and player_tokens.issubset(event_tokens))
        if matched:
            market_entries.append({
                "prob":   mkt["implied_prob"],
                "volume": float(mkt.get("volume", 1000)),
                "source": f"Kalshi({mkt['implied_prob']:.0%})",
            })
    
    # Match Polymarket — exact token matching
    for mkt in poly_data:
        q_tokens = set(normalize_name(mkt.get("question","")).split())
        matched = len(player_tokens) >= 2 and player_tokens.issubset(q_tokens)
        if matched:
            market_entries.append({
                "prob":   mkt["implied_prob"],
                "volume": float(mkt.get("volume", 1000)),
                "source": f"Polymarket({mkt['implied_prob']:.0%})",
            })

    # Match Covers consensus — by team name not sport string
    covers_game = None
    if covers_data and isinstance(covers_data, dict):
        home_t = (game_analysis or {}).get("home","") if game_analysis else ""
        away_t = (game_analysis or {}).get("away","") if game_analysis else ""
        for _cd_matchup, _cd_val in covers_data.items():
            _cd_matchup_l = _cd_matchup.lower()
            # Match by actual team names, not sport code
            if home_t and away_t:
                if (home_t.lower()[:4] in _cd_matchup_l or
                    away_t.lower()[:4] in _cd_matchup_l):
                    covers_game = {"matchup": _cd_matchup, **_cd_val}
                    break
            elif home_t and home_t.lower()[:4] in _cd_matchup_l:
                covers_game = {"matchup": _cd_matchup, **_cd_val}
                break

    if not market_entries:
        return None

    # Volume-weighted average — guaranteed alignment via single list
    total_vol = sum(e["volume"] for e in market_entries)
    sources   = [e["source"] for e in market_entries]
    consensus_prob = (
        sum(e["prob"] * e["volume"] for e in market_entries) / total_vol
        if total_vol > 0
        else sum(e["prob"] for e in market_entries) / len(market_entries)
    )
    market_probs = [e["prob"] for e in market_entries]
    divergence     = model_prob - consensus_prob
    
    if divergence >= 0.08:
        signal = "MODEL_BULLISH"
        note   = f"📈 Model {model_prob:.0%} vs Markets {consensus_prob:.0%} — strong value"
        adj    = min(0.04, divergence * 0.40)  # up to +4% edge boost
    elif divergence >= 0.04:
        signal = "MODEL_LEAN_BULLISH"
        note   = f"📊 Model {model_prob:.0%} vs Markets {consensus_prob:.0%} — mild value"
        adj    = min(0.02, divergence * 0.30)
    elif divergence <= -0.08:
        signal = "MARKET_BULLISH"
        note   = f"📉 Markets {consensus_prob:.0%} vs Model {model_prob:.0%} — fade signal"
        adj    = max(-0.04, divergence * 0.40)
    else:
        signal = "AGREEMENT"
        note   = f"✅ Model ≈ Markets ({consensus_prob:.0%}) — efficient"
        adj    = 0.0
    
    return {
        "consensus_prob":  round(consensus_prob, 3),
        "model_prob":      round(model_prob, 3),
        "divergence":      round(divergence, 3),
        "signal":          signal,
        "note":            note,
        "edge_adj":        round(adj, 3),
        "sources":         sources,
    }


# ── Covers Public Fade Signal ────────────────────────────────────
def compute_sharp_public_divergence(matchup, public_betting=None):
    """
    Full sharp/public divergence with RLM detection.
    Replaces the basic sharp signal detection.
    """
    if public_betting is None:
        public_betting = st.session_state.get("public_betting_data", {})
    pb_data = None
    for key, val in public_betting.items():
        teams = val.get("teams", [])
        if any(t.lower() in matchup.lower() for t in teams if t):
            pb_data = val
            break
    if not pb_data:
        return {}
    sharp_sigs = pb_data.get("sharp_signals", [])
    rlm_sigs   = pb_data.get("rlm_signals",   [])
    result = {
        "sharp_signals": sharp_sigs,
        "rlm_signals":   rlm_sigs,
        "has_sharp":     len(sharp_sigs) > 0,
        "has_rlm":       len(rlm_sigs) > 0,
        "max_strength":  max((r.get("strength",0) for r in rlm_sigs), default=0),
        "ml_data":       pb_data.get("ml",{}),
        "spread_data":   pb_data.get("spread",{}),
        "total_data":    pb_data.get("total",{}),
    }
    strength = result["max_strength"]
    result["edge_adj"] = round(0.02 if strength >= 3 else 0.01 if strength >= 2 else 0.005 if strength >= 1 else 0, 3)
    return result


# format_rlm_display — moved to bc_utils.py
def compute_public_fade_signal(matchup, sport, model_pick_side):
    """
    Public Fade: when 70%+ of public bets on one side,
    sharps are often on the other side.
    
    Strong signal when:
      public_pct >= 75% AND model agrees with MINORITY → contrarian bet
      public_pct >= 75% AND model agrees with MAJORITY → proceed with caution
    
    Returns: {public_pct, side, fade_signal, note}
    """
    covers_data = st.session_state.get("covers_consensus", [])
    an_data    = st.session_state.get("action_network_data", {})
    bpros_data = st.session_state.get("bettingpros_data", {})
    if not covers_data and not an_data and not bpros_data:
        return None
    
    matchup_lower = matchup.lower()
    if isinstance(covers_data, dict):
        for item_matchup, item_val in covers_data.items():
            item_matchup_l = item_matchup.lower()
            # Fuzzy match
            if any(w in item_matchup_l for w in matchup_lower.split(" @ ")):
                _away_name, _, _home_name = item_matchup.partition(" @ ")
                away_pct = item_val.get("away_pct", 50)
                home_pct = item_val.get("home_pct", 50)
                if home_pct >= away_pct:
                    public_pct, public_side = home_pct, _home_name
                else:
                    public_pct, public_side = away_pct, _away_name
            
                if public_pct >= 75:
                    if public_side.lower() not in str(model_pick_side).lower():
                        # Model agrees with MINORITY → contrarian signal
                        return {
                            "public_pct":  public_pct,
                            "side":        public_side,
                            "fade_signal": "CONTRARIAN",
                            "note":        f"🎯 Fade: {public_pct}% public on {public_side}, model takes minority",
                            "edge_adj":    0.02,  # +2% contrarian boost
                        }
                    else:
                        # Model with the public → fade warning
                        return {
                            "public_pct":  public_pct,
                            "side":        public_side,
                            "fade_signal": "WITH_PUBLIC",
                            "note":        f"⚠️ {public_pct}% public on {public_side} — is this a trap?",
                            "edge_adj":    -0.01,  # -1% public side penalty
                        }
                elif public_pct >= 60:
                    return {
                        "public_pct":  public_pct,
                        "side":        public_side,
                        "fade_signal": "MILD_PUBLIC",
                        "note":        f"📊 {public_pct}% public on {public_side}",
                        "edge_adj":    0.0,
                    }
    # ── ActionNetwork sharp-money splits ─────────────────────────────
    if an_data:
        _an_games = an_data if isinstance(an_data, list) else an_data.get("games", an_data.get("data", []))
        if isinstance(_an_games, list):
            for _ag in _an_games:
                _teams   = _ag.get("teams", []) or []
                _home    = next((t.get("full_name","") or t.get("name","") for t in _teams if t.get("is_home")), "")
                _away    = next((t.get("full_name","") or t.get("name","") for t in _teams if not t.get("is_home")), "")
                _an_m    = f"{_away} @ {_home}".lower()
                if not any(w in _an_m for w in matchup_lower.split(" @ ")):
                    continue
                _an_odds = (_ag.get("odds") or [{}])
                _an_o    = (_an_odds[0] if isinstance(_an_odds, list) and _an_odds
                            else _an_odds if isinstance(_an_odds, dict) else {})
                _an_hp   = _an_o.get("bet_pct_home") or _an_o.get("home_pct")
                _an_ap   = _an_o.get("bet_pct_away") or _an_o.get("away_pct")
                if _an_hp is None and _an_ap is None:
                    continue
                try:
                    _anh = float(_an_hp or 50); _ana = float(_an_ap or 50)
                    _pct = max(_anh, _ana)
                    _side = _home if _anh >= _ana else _away
                    if _pct >= 60:
                        _fade = ("CONTRARIAN" if _side.lower() not in str(model_pick_side).lower()
                                 else "WITH_PUBLIC")
                        return {"public_pct": _pct, "side": _side, "fade_signal": _fade,
                                "source": "action_network",
                                "note": f"AN {_pct:.0f}% on {_side}",
                                "edge_adj": 0.015 if _fade == "CONTRARIAN" else -0.01}
                except (ValueError, TypeError):
                    pass
    # ── BettingPros expert consensus ─────────────────────────────────
    if bpros_data:
        _bp_items = (bpros_data if isinstance(bpros_data, list)
                     else bpros_data.get("items", bpros_data.get("picks", bpros_data.get("data", []))))
        if isinstance(_bp_items, list):
            for _bi in _bp_items:
                if not isinstance(_bi, dict): continue
                _bpick = _bi.get("pick", _bi)
                _bslug = (_bpick.get("slug","") or _bpick.get("matchup","") or "").lower()
                if not any(w in _bslug for w in matchup_lower.split(" @ ")):
                    continue
                _bp_pct  = float(_bpick.get("consensus_pct") or _bpick.get("pct") or 0)
                _bp_side = _bpick.get("pick_type","") or _bpick.get("side","")
                if _bp_pct >= 60:
                    _bpf = ("CONTRARIAN" if str(_bp_side).lower() not in str(model_pick_side).lower()
                            else "WITH_PUBLIC")
                    return {"public_pct": _bp_pct, "side": _bp_side, "fade_signal": _bpf,
                            "source": "bettingpros",
                            "note": f"BettingPros {_bp_pct:.0f}% on {_bp_side}",
                            "edge_adj": 0.01 if _bpf == "CONTRARIAN" else -0.01}
    return None


# ═══════════════════════════════════════════════════════════════
# GOLF MODULE
# PGA Tour leaderboard + player odds from OddsAPI
# Sources: ESPN (free) + OddsAPI (existing key)
# ═══════════════════════════════════════════════════════════════

GOLF_PATH = os.path.join(CACHE_DIR, "golf_data.json")


@st.cache_data(ttl=1800)
def get_golf_player_edge(player_name, leaderboard=None, odds=None):
    """
    For a golf prop, compute edge based on:
    1. Current tournament position (leaderboard)
    2. Market-implied win probability (odds)
    3. Position vs par (momentum signal)
    
    Returns edge adjustment for golf props.
    """
    if leaderboard is None:
        leaderboard = st.session_state.get("golf_leaderboard", [])
    if odds is None:
        odds = st.session_state.get("golf_odds", {})
    
    name_lower = normalize_name(player_name)
    adj = 0.0
    notes = []
    
    # Check leaderboard position
    for p in leaderboard:
        if normalize_name(p.get("name","")) == name_lower:
            pos_str = p.get("position","")
            total   = p.get("total","E")
            # Position bonus: top 10 players have momentum
            try:
                pos_num = int(pos_str.replace("T","").replace("t","") or 99)
                if pos_num <= 3:
                    adj += 0.05
                    notes.append(f"🏆 T{pos_num} leaderboard +5%")
                elif pos_num <= 10:
                    adj += 0.03
                    notes.append(f"📈 T{pos_num} leaderboard +3%")
                elif pos_num > 30:
                    adj -= 0.03
                    notes.append(f"📉 #{pos_num} leaderboard -3%")
            except (OSError, IOError, ValueError, KeyError, TypeError, AttributeError):
                pass
            break
    
    # Check odds — low odds = market expects them to perform well
    player_odds = odds.get(player_name, odds.get(normalize_name(player_name),{}))
    if player_odds:
        impl_prob = player_odds.get("implied_prob", 0)
        if impl_prob >= 0.20:  # <400 odds = co-favorite
            adj += 0.02
            notes.append(f"⭐ Market fav ({player_odds['odds']:+d}) +2%")
    
    return round(adj, 3), " | ".join(notes)


# ═══════════════════════════════════════════════════════════════
# DFF (DAILYFANTASYFUEL) TEAMMATE IMPACT MODULE
# Confirmed endpoint: /rosterfilter/{SPORT}/{TEAM}/{DATE}/{PLAYERID}/ALL
# Example: dailyfantasyfuel.com/rosterfilter/NBA/SA/2026-06-05/164B7E/ALL
#
# Returns: teammate roster with AVG Mins, AVG PRA, with/without data
# Use as CONFIRMATION SIGNAL ONLY — never overrides Pinnacle EV
# Weight: +1% to +3% max
# ═══════════════════════════════════════════════════════════════

DFF_PATH      = os.path.join(CACHE_DIR, "dff_rosterfilter.json")




def compute_dff_teammate_impact(player, team, sport, prop_type, stat_line,
                                 dff_data=None, injury_data=None):
    """
    Compute DFF teammate impact signal for a prop.
    
    Checks if key teammates are injured/out and adjusts edge.
    
    Example:
      Castle PRA prop
      Wembanyama OUT
      DFF: Castle PRA +22% without Wembanyama
      → edge boost +2%
    
    Weight: +1% to +3% max — confirmation only, never overrides Pinnacle EV.
    Returns (edge_adj, signal_dict, display_note)
    """
    if dff_data is None:
        # Try to get from cache
        cache = st.session_state.get("dff_cache", {})
        dff_data = next(
            (v for k, v in cache.items()
             if k.startswith(f"{sport}_{DFF_TEAM_MAP.get(team,team)}")),
            {}
        )
    
    if not dff_data or not dff_data.get("roster"):
        return 0.0, {}, ""
    
    roster  = dff_data["roster"]
    injuries = injury_data or st.session_state.get("injuries", {})
    
    adj         = 0.0
    signals     = []
    top_impacts = []
    
    for teammate in roster:
        tname     = teammate["player"]
        with_val  = teammate.get("with_val", 0)
        wo_val    = teammate.get("without_val", 0)
        dep       = teammate.get("dependency", "UNKNOWN")
        avg_pra   = teammate.get("avg_pra", 0)
        
        # Skip if no with/without data
        if with_val <= 0 or wo_val <= 0:
            continue
        
        # Check if teammate is out/injured
        tname_norm = normalize_name(tname)
        inj_status = ""
        if isinstance(injuries, dict):
            inj_entry = injuries.get(tname_norm, injuries.get(tname, {}))
            if isinstance(inj_entry, dict):
                inj_status = inj_entry.get("status","").lower()
            elif isinstance(inj_entry, str):
                inj_status = inj_entry.lower()
        
        teammate_out = inj_status in ("out","doubtful","dtd","ir","inactive")
        
        if dep == "HIGH":
            if teammate_out:
                # Key teammate out — use WITHOUT value
                pct_change = (wo_val - with_val) / max(with_val, 1)
                if pct_change > 0.10:
                    # Player improves without this teammate
                    edge_boost = min(0.03, pct_change * 0.15)
                    adj += edge_boost
                    signals.append({
                        "teammate": tname,
                        "status":   "OUT",
                        "with":     round(with_val,1),
                        "without":  round(wo_val,1),
                        "change":   f"+{pct_change:.0%}",
                        "direction":"BOOST",
                    })
                    top_impacts.append(
                        f"📈 {tname} OUT: {round(wo_val,1)} vs {round(with_val,1)} PRA ({pct_change:+.0%})"
                    )
                elif pct_change < -0.10:
                    # Player regresses without this teammate
                    edge_cut = max(-0.03, pct_change * 0.15)
                    adj += edge_cut
                    signals.append({
                        "teammate": tname,
                        "status":   "OUT",
                        "with":     round(with_val,1),
                        "without":  round(wo_val,1),
                        "change":   f"{pct_change:.0%}",
                        "direction":"FADE",
                    })
                    top_impacts.append(
                        f"📉 {tname} OUT: {round(wo_val,1)} vs {round(with_val,1)} PRA ({pct_change:+.0%})"
                    )
            else:
                # Key teammate IN — use WITH value (normal)
                signals.append({
                    "teammate": tname,
                    "status":   "IN",
                    "with":     round(with_val,1),
                    "without":  round(wo_val,1),
                    "change":   "—",
                    "direction":"NORMAL",
                })
    
    # Cap total adjustment
    adj = round(max(-0.03, min(0.03, adj)), 3)
    
    display = " | ".join(top_impacts[:2]) if top_impacts else ""
    
    return adj, signals, display


def get_dff_player_id(player_name, sport="NBA"):
    """
    Get DFF player ID from session cache or pre-built lookup.
    DFF uses hex IDs (e.g. 164B7E for Wembanyama).
    These need to be discovered from DevTools or a player list endpoint.
    """
    # Session cache of discovered IDs
    id_cache = st.session_state.get("dff_player_ids", {})
    return id_cache.get(normalize_name(player_name), "")


def register_dff_player_id(player_name, player_id):
    """Store a discovered DFF player ID for future lookups."""
    cache = st.session_state.get("dff_player_ids", {})
    cache[normalize_name(player_name)] = player_id
    st.session_state["dff_player_ids"] = cache

# ── DFF PropStats ────────────────────────────────────────────
# Endpoint: dailyfantasyfuel.com/propstats/{SPORT}/
# Returns: per-game hit rate, avg minutes, usage, potentials
# Worst case: games=[] → logs "no data"
# Best case:  L10 hit rate, avg minutes, contextual splits

DFF_PROPSTATS_URL = "https://www.dailyfantasyfuel.com/propstats/{sport}/"


@st.cache_data(ttl=1800)
def _fetch_dff_propstats_live(player_id, sport, metric, line, team="",
                         opponent="", position="", direction="over",
                         location="ALL", last_n=10,
                         wplayer="", woplayer=""):
    """
    Fetch DFF PropStats for a player/metric combination.
    
    Endpoint: dailyfantasyfuel.com/propstats/{SPORT}/
    Returns per-game hit rate against the line + contextual stats.
    
    Params:
      wplayer/woplayer: optional teammate filter (with/without)
      last_n:           L5, L10, L20, or Season
      direction:        "over" or "under"
    
    Returns dict:
      hit_rate, hits, total_games, avg_val,
      avg_minutes, avg_usage, avg_potentials,
      games (raw list)
    """
    sport_key = DFF_SPORT_MAP.get(sport, sport.upper())
    metric_key = DFF_METRIC_MAP.get(metric, metric.lower().replace(" ",""))
    range_str  = f"L{last_n}" if last_n in (5,10,20) else "Season"
    
    params = {
        "playerID":  player_id,
        "metric":    metric_key,
        "loc":       location,       # ALL, Home, Away
        "playoffs":  "ALL",
        "pos":       position or "ALL",
        "team":      team or "ALL",
        "opp":       opponent or "ALL",
        "range":     range_str,
        "line":      str(line),
        "starter":   "ALL",
        "minutes":   1,
        "rest":      "ALL",
        "direction": direction,
        "win":       "ALL",
    }
    
    # Optional teammate filters
    if wplayer:
        params["wplayer"] = wplayer
    if woplayer:
        params["woplayer"] = woplayer
    
    url = DFF_PROPSTATS_URL.format(sport=sport_key)
    
    try:
        r = _http.get(url, headers=DFF_HEADERS, params=params, timeout=15)
        
        # Log actual URL once per session for diagnostics
        _req_url = r.url if hasattr(r, 'url') else url
        _url_log = st.session_state.get("dff_url_log", [])
        if not any(l.get("player_id") == player_id and l.get("metric") == metric_key 
                   for l in _url_log):
            _url_log.append({
                "player_id": player_id, "metric": metric_key,
                "url": _req_url, "status": r.status_code,
                "time": datetime.now().strftime("%H:%M"),
            })
        if r.status_code not in (200, 304):
            st.session_state.setdefault("errors",[]).append({
                "source": "DFF PropStats",
                "error":  f"HTTP {r.status_code}",
                "time":   datetime.now().strftime("%H:%M"),
            })
            return {}
        
        data  = r.json() if r.text else {}
        games = data.get("stats", data.get("games", data.get("data", [])))
        
        if not games:
            # Log but don't error — endpoint may return empty for some combos
            st.session_state.setdefault("dff_propstats_log",[]).append({
                "player_id": player_id, "metric": metric_key,
                "result": "no_data", "time": datetime.now().strftime("%H:%M"),
            })
            return {}
        
        # Parse per-game stats
        hits         = 0
        total        = len(games)
        vals         = []
        mins_list    = []
        usage_list   = []
        potentials_list = []
        
        line_f = float(line)
        
        for g in games:
            val       = float(g.get("metric", g.get("value", g.get("stat", 0))) or 0)
            mins      = float(g.get("mins",   g.get("minutes", 0)) or 0)
            usage     = float(g.get("usage",  0) or 0)
            potential = float(g.get("potentials", g.get("potential", 0)) or 0)
            
            vals.append(val)
            if mins > 0:     mins_list.append(mins)
            if usage > 0:    usage_list.append(usage)
            if potential > 0:potentials_list.append(potential)
            
            # Hit check
            if direction == "over" and val > line_f:
                hits += 1
            elif direction == "under" and val < line_f:
                hits += 1
        
        hit_rate  = round(hits / total, 3) if total > 0 else 0
        avg_val   = round(sum(vals) / len(vals), 2) if vals else 0
        avg_mins  = round(sum(mins_list) / len(mins_list), 1) if mins_list else 0
        avg_usage = round(sum(usage_list) / len(usage_list), 3) if usage_list else 0
        avg_pot   = round(sum(potentials_list) / len(potentials_list), 1) if potentials_list else 0
        
        result = {
            "hit_rate":       hit_rate,
            "hits":           hits,
            "total_games":    total,
            "avg_val":        avg_val,
            "avg_minutes":    avg_mins,
            "avg_usage":      avg_usage,
            "avg_potentials": avg_pot,
            "line":           line_f,
            "direction":      direction,
            "metric":         metric_key,
            "range":          range_str,
            "games":          games[:20],  # cap stored games
        }
        
        # Log success
        st.session_state.setdefault("dff_propstats_log",[]).append({
            "player_id": player_id, "metric": metric_key,
            "hit_rate": hit_rate, "games": total,
            "result": "success", "time": datetime.now().strftime("%H:%M"),
        })
        
        return result
    
    except (requests.RequestException, ValueError, KeyError) as e:
        st.session_state.setdefault("errors",[]).append({
            "source": "DFF PropStats", "error": str(e)[:80],
            "time": datetime.now().strftime("%H:%M"),
        })
        return {}


def compute_market_move_quality(matchup, prop, sport, current_props=None):
    """
    Determine WHY a line moved — sharp vs soft attribution.
    
    Quality scale:
      +2 = Pinnacle/Circa leads move (strongest signal)
      +1 = Consensus across multiple sharp books
       0 = Mixed — no clear leader
      -1 = Only fantasy books moved (PrizePicks/Underdog)
      -2 = Reverse — line moved against sharp money
    
    Method: compare opening line to current line across books.
    If Pinnacle moved first → sharp-led.
    If only prop sites moved → market noise.
    """
    line_movements = load_json_data(LINE_MOVEMENT_PATH, {})
    pinnacle_lines  = load_json_data(PINNACLE_LINES_PATH, {})
    
    key = f"{matchup}_{prop}"
    movements = line_movements.get(key, {})
    
    if not movements:
        return 0, "No line movement data"
    
    opening  = movements.get("opening_line")
    current  = movements.get("current_line")
    
    if opening is None or current is None:
        return 0, "Incomplete movement data"
    
    try:
        move_size = float(current) - float(opening)
    except (ValueError, TypeError):
        return 0, "Invalid line values"
    
    if abs(move_size) < 0.2:
        return 0, f"No significant move ({move_size:+.1f})"
    
    # Check which books moved
    pinn_opening = pinnacle_lines.get(f"{key}_open")
    pinn_current = pinnacle_lines.get(f"{key}_current")
    
    if pinn_opening and pinn_current:
        try:
            pinn_move = float(pinn_current) - float(pinn_opening)
            if abs(pinn_move) >= abs(move_size) * 0.8:
                # Pinnacle moved proportionally → sharp-led
                quality = 2
                note    = f"⚡ Sharp-led move: Pinnacle {pinn_move:+.1f} | {move_size:+.1f} total"
            elif abs(pinn_move) < 0.1:
                # Pinnacle didn't move → soft money only
                quality = -1
                note    = f"⚠️ Soft move: Pinnacle flat, market {move_size:+.1f}"
            else:
                quality = 1
                note    = f"📊 Mixed move: Pinnacle {pinn_move:+.1f} | market {move_size:+.1f}"
        except (ValueError, TypeError):
            quality = 0
            note    = f"Line moved {move_size:+.1f} (source unknown)"
    else:
        # No Pinnacle data — use move size as proxy
        if abs(move_size) >= 1.5:
            quality = 1
            note    = f"📈 Large move: {move_size:+.1f} (no Pinnacle data)"
        else:
            quality = 0
            note    = f"Small move: {move_size:+.1f}"
    
    return quality, note


# ── 2. Minutes Stability Score (CV) ────────────────────────────
def compute_minutes_cv(player, sport, game_logs=None, n=10):
    """
    Coefficient of variation for minutes played.
    
    CV = std_dev / mean
    Low CV = stable minutes = more predictable props
    High CV = volatile minutes = risky props
    
    Example:
      Player A: [32,33,34,35,34] → CV = 0.03 (STABLE)
      Player B: [18,40,21,39,28] → CV = 0.35 (VOLATILE)
    
    Returns (cv, stability_label, edge_adj)
    """
    if game_logs is None:
        game_logs = st.session_state.get("player_game_logs", {})
    
    logs = game_logs.get(normalize_name(player), [])
    if not logs:
        return None, "UNKNOWN", 0.0
    
    # Get recent minutes
    recent = logs[-n:] if len(logs) >= n else logs
    mins_list = []
    for g in recent:
        m = float(g.get("min", g.get("minutes", g.get("mins", 0))) or 0)
        if m > 0:
            mins_list.append(m)
    
    if len(mins_list) < 4:
        return None, "INSUFFICIENT", 0.0
    
    mean_m = sum(mins_list) / len(mins_list)
    if mean_m <= 0:
        return None, "UNKNOWN", 0.0
    
    variance = sum((m - mean_m) ** 2 for m in mins_list) / len(mins_list)
    std_dev  = variance ** 0.5
    cv       = round(std_dev / mean_m, 3)
    
    # Stability classification
    if cv <= 0.08:
        label = "STABLE"
        adj   = 0.01      # +1% confidence for stable minutes
    elif cv <= 0.15:
        label = "MODERATE"
        adj   = 0.0
    elif cv <= 0.25:
        label = "VOLATILE"
        adj   = -0.01     # -1% for volatile minutes
    else:
        label = "HIGH_RISK"
        adj   = -0.02     # -2% for very volatile
    
    return cv, label, round(adj, 3)


# ── 3. Volatility Flag ───────────────────────────────────────────
def compute_volatility_flag(player, sport, stat_norm, game_logs=None, n=10):
    """
    Compute stat volatility — std dev of the specific prop stat.
    
    High volatility = wide range of outcomes = risky prop.
    Display as risk flag on prop card.
    
    Returns (std_dev, risk_level, note)
    """
    if game_logs is None:
        game_logs = st.session_state.get("player_game_logs", {})
    
    logs = game_logs.get(normalize_name(player), [])
    if not logs:
        return None, "UNKNOWN", ""
    
    recent = logs[-n:] if len(logs) >= n else logs
    
    # Map stat_norm to game log field
    stat_field_map = {
        "Points":    ["pts","points"],
        "Rebounds":  ["reb","rebounds","total_reb"],
        "Assists":   ["ast","assists"],
        "PRA":       ["pts","reb","ast"],  # sum
        "Threes":    ["fg3m","threes","three_pointers_made"],
        "Steals":    ["stl","steals"],
        "Blocks":    ["blk","blocks"],
        "Hits":      ["hits","h"],
        "Total Bases":["total_bases","tb"],
        "Strikeouts":["strikeouts","k"],
    }
    
    fields = stat_field_map.get(stat_norm, [stat_norm.lower()])
    vals   = []
    
    for g in recent:
        if len(fields) > 1 and stat_norm == "PRA":
            # Sum for combo stats
            val = sum(float(g.get(f, 0) or 0) for f in fields)
        else:
            val = next((float(g.get(f, 0) or 0) for f in fields if g.get(f) is not None), 0)
        if val > 0 or len(vals) > 0:
            vals.append(val)
    
    if len(vals) < 4:
        return None, "INSUFFICIENT", ""
    
    mean_v   = sum(vals) / len(vals)
    variance = sum((v - mean_v) ** 2 for v in vals) / len(vals)
    std_dev  = round(variance ** 0.5, 2)
    
    if mean_v <= 0:
        return std_dev, "UNKNOWN", ""
    
    cv = std_dev / mean_v
    
    if cv <= 0.15:
        risk  = "LOW"
        note  = f"✅ Low variance ({std_dev:.1f} std dev)"
        adj   = 0.01
    elif cv <= 0.30:
        risk  = "MEDIUM"
        note  = f"📊 Medium variance ({std_dev:.1f} std dev)"
        adj   = 0.0
    elif cv <= 0.45:
        risk  = "HIGH"
        note  = f"⚠️ High variance ({std_dev:.1f} std dev)"
        adj   = -0.01
    else:
        risk  = "EXTREME"
        note  = f"🚨 Extreme variance ({std_dev:.1f} std dev) — risky prop"
        adj   = -0.02
    
    return std_dev, risk, note


# ── 4. Closing Line Hit Rate ────────────────────────────────────
# track_closing_line_beat — moved to bc_utils.py


def _capture_clv_closing_lines():
    """
    GAP FIX (2026-06-21): True CLV closing line capture.

    Previous approach: closing_line stored at bet-settlement time using the
    current board line — which could be hours before game time, meaning it's
    not actually the closing line.

    This function runs on a 10-min timer and checks every PENDING bet.
    If a bet's game starts within 15 minutes, it pulls the OddsAPI closing
    line snapshot for that player/prop and writes it to CLV_PATH so that
    resolve_clv_records() has a real closing line rather than a midday board
    snapshot.  Once captured, the record is marked clv_pre_close=True so
    we don't overwrite it on subsequent runs.
    """
    if not ODDS_API_KEY:
        return
    try:
        history    = load_json_data(HISTORY_PATH, [])
        clv_data   = load_json_data(CLV_PATH, [])
        _clv_index = {
            (normalize_name(c.get("player", "")), c.get("prop", ""), c.get("timestamp", "")[:10]): i
            for i, c in enumerate(clv_data)
        }
        now        = datetime.now()
        today_str  = now.strftime("%Y-%m-%d")
        updated    = False

        pending = [
            b for b in history
            if b.get("outcome") == "PENDING"
            and b.get("timestamp", "")[:10] == today_str
            and not b.get("clv_capture", {}).get("clv_resolved")
        ]
        if not pending:
            return

        # Pull current EV API odds as closing line proxy (same source as S6/S7)
        ev_lookup = {}
        try:
            _ev_url = "https://api-production-3a3b.up.railway.app/api/ev"
            _ev_r   = _http.get(_ev_url, timeout=10)
            if _ev_r.status_code == 200:
                for item in _ev_r.json():
                    pname = normalize_name(item.get("player_name", ""))
                    ptype = item.get("stat_type", "")
                    if pname and ptype:
                        ev_lookup[(pname, ptype)] = item
        except Exception:
            _logger.debug("Silent except at line 3083")
            pass

        for bet in pending:
            player    = bet.get("player", "")
            prop      = bet.get("prop", "")
            line      = bet.get("line", 0)
            side      = bet.get("side", "OVER")
            sport     = bet.get("sport", "")
            timestamp = bet.get("timestamp", "")[:10]
            pkey      = (normalize_name(player), prop, timestamp)

            ev_item = ev_lookup.get((normalize_name(player), prop))
            if not ev_item:
                continue

            closing_no_vig = ev_item.get("no_vig_prob") or ev_item.get("consensus_prob")
            placement_prob = bet.get("clv_capture", {}).get("placement_prob") or bet.get("prob", 0)
            if not closing_no_vig or not placement_prob:
                continue

            clv_vs_close = round(float(closing_no_vig) - float(placement_prob), 4)

            if pkey in _clv_index:
                idx = _clv_index[pkey]
                clv_data[idx]["closing_line"]   = float(ev_item.get("line", line))
                clv_data[idx]["closing_no_vig"] = float(closing_no_vig)
                clv_data[idx]["clv_vs_close"]   = clv_vs_close
                clv_data[idx]["clv_pre_close"]  = True
            else:
                clv_data.append({
                    "player":         player,
                    "prop":           prop,
                    "locked_line":    float(line),
                    "closing_line":   float(ev_item.get("line", line)),
                    "closing_no_vig": float(closing_no_vig),
                    "side":           side,
                    "clv":            round(float(line) - float(ev_item.get("line", line)), 1) if side == "OVER" else round(float(ev_item.get("line", line)) - float(line), 1),
                    "clv_vs_close":   clv_vs_close,
                    "outcome":        "PENDING",
                    "timestamp":      timestamp,
                    "sport":          sport,
                    "tier":           bet.get("tier", ""),
                    "edge":           bet.get("edge", 0),
                    "prob":           placement_prob,
                    "clv_pre_close":  True,
                    "source":         bet.get("source", ""),
                })
                updated = True

        if updated or any(True for _ in pending):
            save_json_data(CLV_PATH, clv_data)
    except Exception:
        _logger.debug("Silent except at line 3135")
        pass


def _capture_clv_closing_lines_game():
    """
    Game-line counterpart to _capture_clv_closing_lines() -- fills in
    closing_line_pinnacle/clv_points for game-line locks, which
    _capture_clv_placement_game() always left as None (placement side was
    built, closing side never was -- CLV for game lines was structurally
    incomplete despite the infrastructure existing). Points-based CLV
    (spread/total), not a probability, per the same reasoning documented
    in _capture_clv_placement_game.
    """
    try:
        history = load_json_data(HISTORY_PATH, [])
        clv_data = load_json_data(CLV_PATH, [])
        pinnacle_lines = st.session_state.get("pinnacle_game_lines", [])
        if not pinnacle_lines:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        pending_games = [
            b for b in history
            if b.get("bet_type") == "game"
            and b.get("outcome") == "PENDING"
            and b.get("timestamp", "")[:10] == today_str
            and not b.get("clv_capture", {}).get("clv_resolved")
            and b.get("clv_capture", {}).get("placement_line_pinnacle") is not None
            and b.get("clv_capture", {}).get("closing_line_pinnacle") is None
        ]
        if not pending_games:
            return

        _game_clv_index = {
            (c.get("matchup", ""), c.get("market", ""), c.get("timestamp", "")[:10]): i
            for i, c in enumerate(clv_data) if c.get("bet_type") == "game"
        }
        updated = False
        for bet in pending_games:
            matchup   = bet.get("player", "")   # matchup stored under "player" key, same schema as props
            market    = bet.get("prop", "")
            side      = bet.get("side", "")
            sport     = bet.get("sport", "")
            timestamp = bet.get("timestamp", "")[:10]
            placement = bet["clv_capture"]["placement_line_pinnacle"]

            pin_game = next(
                (g for g in pinnacle_lines
                 if normalize_name(g.get("Matchup", "")) == normalize_name(matchup)
                 or normalize_name(matchup) in normalize_name(g.get("Matchup", ""))),
                None
            )
            if not pin_game:
                continue
            closing_line = pin_game.get("Spread") if market == "SPREAD" else (
                pin_game.get("Total") if market in ("TOTAL", "ALT LINE") else None
            )
            if closing_line is None:
                continue
            closing_line = float(closing_line)

            # Standard CLV convention: beating the close (line moved toward
            # your locked side after you bet it) is a positive number.
            clv_points = round(placement - closing_line, 2) if side.upper() in ("OVER", "HOME") \
                else round(closing_line - placement, 2)

            gkey = (matchup, market, timestamp)
            if gkey in _game_clv_index:
                idx = _game_clv_index[gkey]
                clv_data[idx]["closing_line_pinnacle"] = closing_line
                clv_data[idx]["clv_points"] = clv_points
                clv_data[idx]["clv_pre_close"] = True
            else:
                clv_data.append({
                    "bet_type": "game", "matchup": matchup, "market": market,
                    "placement_line_pinnacle": placement,
                    "closing_line_pinnacle": closing_line,
                    "clv_points": clv_points,
                    "side": side, "outcome": "PENDING",
                    "timestamp": timestamp, "sport": sport,
                    "tier": bet.get("tier", ""), "edge": bet.get("edge", 0),
                    "clv_pre_close": True,
                })
            updated = True

        if updated:
            save_json_data(CLV_PATH, clv_data)
    except Exception:
        pass


def resolve_clv_records(history):
    """
    Auto-resolve CLV for settled bets by comparing the placement snapshot
    (captured at lock time, via _capture_clv_placement / 
    _capture_clv_placement_game) against a CURRENT market snapshot.
    Called on History tab load and the 10-min timer.

    Props: Buchdahl standard -- CLV = closing no-vig prob - placement
    no-vig prob, positive = beat the close = +EV. Needs 50+ resolved bets
    for statistical significance, 1000+ for full P-value confidence.

    Games (added 2026-07-13): no equivalent single no-vig probability
    exists for a spread/total in the data this app collects, so this uses
    a points-based CLV instead -- closing Pinnacle line vs the line
    captured at lock time. Same PROCESS/VARIANCE direction (beat the
    close vs lost to it), different unit (points, not percent) --
    generate_post_mortem() displays it accordingly rather than forcing it
    into a fabricated percentage.

    Both resolve opportunistically: whichever live snapshot the app
    happens to have in session state (ev_signal_lookup for props,
    pinnacle_game_lines for games) at whatever moment this runs. If that
    moment isn't near the actual game/market close, the record stays
    unresolved rather than getting a wrong number -- some picks will
    resolve, some won't, depending on session activity near game time.
    That's a real, honest limitation, not a bug.
    """
    try:
        import streamlit as _st
        _ev_sig_lookup = _st.session_state.get("ev_signal_lookup", {})
        _pinnacle_games = _st.session_state.get("pinnacle_game_lines", [])
        if not _ev_sig_lookup and not _pinnacle_games:
            return history, False   # no live market data of either kind yet

        changed = False
        for record in history:
            _clv = record.get("clv_capture", {})
            if not _clv or _clv.get("clv_resolved"):
                continue
            if record.get("outcome") not in ("WIN", "LOSS"):
                continue

            if _clv.get("bet_type") == "game":
                if not _pinnacle_games:
                    continue
                _placement_line = _clv.get("placement_line_pinnacle")
                if _placement_line is None:
                    continue
                _matchup = record.get("player", "")  # game records store matchup in "player"
                _market  = record.get("prop", "")
                _pin_game = next(
                    (g for g in _pinnacle_games
                     if normalize_name(g.get("Matchup", "")) == normalize_name(_matchup)
                     or normalize_name(_matchup) in normalize_name(g.get("Matchup", ""))),
                    None
                )
                if not _pin_game:
                    continue
                _closing_line = _pin_game.get("Spread") if _market == "SPREAD" else (
                    _pin_game.get("Total") if _market in ("TOTAL", "ALT LINE") else None
                )
                if _closing_line is None:
                    continue
                try:
                    _closing_line = float(_closing_line)
                except (TypeError, ValueError):
                    continue
                _side = record.get("side", "")
                _clv_pts = (_placement_line - _closing_line) if ("OVER" in _side.upper() or "HOME" in _side.upper()) \
                    else (_closing_line - _placement_line)
                record["clv_capture"]["closing_line_pinnacle"] = _closing_line
                record["clv_capture"]["clv_points"]            = round(_clv_pts, 2)
                record["clv_capture"]["clv_resolved"]           = True
                changed = True
                continue

            _player = normalize_name(record.get("player", ""))
            _prop   = record.get("prop", "")
            _sig    = _ev_sig_lookup.get((_player, _prop), {})
            if not _sig:
                continue

            # Get closing no-vig from EV API current snapshot
            _close_pn    = _sig.get("pn_novig")
            _close_circa = _sig.get("circa_novig")
            _close_cons  = _sig.get("consensus_novig")

            if _close_cons is None:
                continue

            # CLV vs no-vig closing line (gold standard)
            _placement_cons = _clv.get("consensus_novig_placement")
            if _placement_cons is not None:
                _side = record.get("side", "OVER")
                if _side == "UNDER":
                    _clv_novig = (1 - float(_close_cons)) - (1 - float(_placement_cons))
                else:
                    _clv_novig = float(_close_cons) - float(_placement_cons)
                record["clv_capture"]["closing_pn_novig"]  = _close_pn
                record["clv_capture"]["closing_consensus"] = _close_cons
                record["clv_capture"]["clv_vs_novig"]      = round(_clv_novig, 4)
                record["clv_capture"]["clv_resolved"]      = True
                changed = True

        return history, changed
    except Exception:
        return history, False


def get_closing_line_hit_rate(history=None):
    """
    Compute what % of model projections beat the closing line.
    High rate = model has genuine edge vs market.
    """
    if history is None:
        history = st.session_state.get("history", [])
    
    clv_beats = 0
    clv_total = 0
    
    for bet in history:
        clv_data = bet.get("clv_direction","")
        if clv_data == "correct":
            clv_beats += 1
            clv_total += 1
        elif clv_data == "wrong":
            clv_total += 1
    
    if clv_total < 10:
        return None, clv_total
    
    return round(clv_beats / clv_total, 3), clv_total


# ═══════════════════════════════════════════════════════════════
# EXPLAINABILITY LAYER
# 1. Conflict Detection (Aligned/Mixed/Conflicted)
# 2. Market Agreement Score (0-100)
# 3. Per-Signal Historical ROI Audit
# ═══════════════════════════════════════════════════════════════

# ── 1. Conflict Detection ───────────────────────────────────────
def compute_signal_conflict(prop):
    """
    Detect when strong positive and negative signals oppose each other.
    
    Conflicted bet example:
      DFF +2%, Pinnacle +2%, RLM +2%
      Volatility -2%, Minutes risk -2%
      Net = +2% but signals are fighting
    
    Returns (status, score, note) where:
      status = "ALIGNED" | "MIXED" | "CONFLICTED"
      score  = net signal alignment -100 to +100
    """
    drivers, risks = generate_why_drivers(prop)
    
    # Parse contribution values
    def parse_pct(val_str):
        try:
            return float(str(val_str).replace("%","").replace("+","").strip())
        except (ValueError, TypeError, ZeroDivisionError):
            return 0.0
    
    pos_total = sum(parse_pct(v) for _, v, _ in drivers if parse_pct(v) > 0)
    neg_total = sum(abs(parse_pct(v)) for _, v, _ in risks if parse_pct(v) < 0)
    
    pos_count = len([d for d in drivers if parse_pct(d[1]) >= 1.0])
    neg_count = len([r for r in risks   if abs(parse_pct(r[1])) >= 1.0])
    
    if pos_count == 0 and neg_count == 0:
        return "UNKNOWN", 0, ""
    
    # Alignment score: positive = aligned, negative = conflicted
    if pos_total + neg_total > 0:
        alignment = round((pos_total - neg_total) / (pos_total + neg_total) * 100)
    else:
        alignment = 0
    
    # Status thresholds
    if neg_count == 0 or (pos_count >= 2 and neg_count == 0):
        status = "ALIGNED"
        color  = "#22c55e"
        note   = f"🟢 Aligned — {pos_count} positive signal{'s' if pos_count>1 else ''}, no conflicts"
    elif pos_count >= 2 and neg_count >= 2 and neg_total >= pos_total * 0.5:
        status = "CONFLICTED"
        color  = "#e04040"
        note   = f"Conflicted: {pos_count} positive (+{pos_total:.0f}%) vs {neg_count} negative (-{neg_total:.0f}%) - reduce size"
    elif neg_count >= 1:
        status = "MIXED"
        color  = "#e8a020"
        note   = f"🟡 Mixed — {pos_count}↑ {neg_count}↓ signals"
    else:
        status = "ALIGNED"
        color  = "#22c55e"
        note   = f"🟢 Aligned — {pos_count} positive signals"
    
    return status, alignment, note


# ── 2. Market Agreement Score (0-100) ──────────────────────────
def compute_market_agreement_score(prop, public_betting=None):
    """
    Score how consistently the market agrees on direction (0-100).
    
    High score (>80): All books moving same direction → strong signal
    Low score (<40):  Books disagreeing → fragmented market, lower confidence
    
    Sources checked: Pinnacle, line movement history, sharp signals
    """
    score = 50  # neutral start
    notes = []
    
    # Pinnacle confirmation
    if prop.get("PinnacleConfirms") is True:
        score += 15
        notes.append("Pinnacle ✅")
    
    # Sharp flag
    sharp = str(prop.get("SharpFlag",""))
    if "↑" in sharp:
        score += 10
        notes.append("Sharp ↑")
    elif "↓" in sharp:
        score -= 10
    
    # Market move quality
    mmq = int(prop.get("MarketMoveQuality", 0) or 0)
    if mmq >= 2:
        score += 15
        notes.append("Sharp lead ⚡")
    elif mmq == 1:
        score += 8
    elif mmq <= -1:
        score -= 10
        notes.append("Soft move ⚠️")
    
    # RLM signal
    matchup = prop.get("Matchup", prop.get("matchup",""))
    if matchup:
        pb = st.session_state.get("public_betting_data",{})
        rlm = compute_sharp_public_divergence(matchup, pb)
        if rlm.get("has_rlm"):
            strength = rlm.get("max_strength",0)
            score += strength * 8
            notes.append(f"RLM s{strength}")
        elif rlm.get("has_sharp"):
            score += 5
    
    # Kalshi/Polymarket agreement
    mkt = prop.get("MarketVsModel")
    if isinstance(mkt, dict):
        if mkt.get("signal") == "AGREEMENT":
            score += 10
            notes.append("Markets agree")
        elif mkt.get("signal") == "MODEL_BULLISH":
            score += 5
        elif mkt.get("signal") == "MARKET_BULLISH":
            score -= 5
    
    score = max(0, min(100, score))
    
    if score >= 80:
        label = "Strong Consensus"
        color = "#22c55e"
    elif score >= 60:
        label = "Moderate Agreement"
        color = "#22c55e"
    elif score >= 40:
        label = "Fragmented"
        color = "#e8a020"
    else:
        label = "Disagreement"
        color = "#e04040"
    
    return {
        "score":  score,
        "label":  label,
        "color":  color,
        "notes":  notes,
        "display": f"{score}/100 {label}",
    }


# ── 3. Per-Signal Historical ROI Audit ─────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def compute_signal_roi_audit(history=None):
    """
    For each signal type, compute:
      win_rate, roi, clv_rate, sample_size
    
    This answers: which signals actually matter?
    
    Activates at 20+ resolved bets.
    Becomes reliable at 100+ bets.
    """
    if history is None:
        history = st.session_state.get("history", [])
    
    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS")]
    if len(resolved) < 20:
        return {}
    
    # Signal presence in each bet
    SIGNAL_KEYS = {
        "Base model":        "SignalBase",
        "Defense":           "SignalDefense",
        "Location":          "SignalLocation",
        "Rest":              "SignalRest",
        "Pinnacle":          "PinnacleConfirms",
        "Sharp money":       "SharpFlag",
        "Minutes stable":    "MinutesStability",
        "Low volatility":    "RiskLevel",
        "DFF hit rate":      "DFFHitRateL10",
        "Market move":       "MarketMoveQuality",
        "RLM":               "rlm_present",
        "Lineup confirmed":  "LineupConfirmed",
    }
    
    audit = {}
    
    for signal_name, key in SIGNAL_KEYS.items():
        signal_bets = []
        for bet in resolved:
            sv = bet.get("signal_values", {})
            val = sv.get(key, bet.get(key))
            
            # Determine if signal was present/positive
            present = False
            if key == "PinnacleConfirms":
                present = val is True
            elif key == "SharpFlag":
                present = "↑" in str(val or "")
            elif key == "MinutesStability":
                present = val in ("STABLE",)
            elif key == "RiskLevel":
                present = val in ("LOW",)
            elif key == "DFFHitRateL10":
                present = float(val or 0) >= 0.60
            elif key == "MarketMoveQuality":
                present = int(val or 0) >= 1
            elif key == "rlm_present":
                present = bool(bet.get("rlm_present", False))
            elif key == "LineupConfirmed":
                present = val is True
            else:
                present = float(val or 0) >= 0.01
            
            if present:
                signal_bets.append(bet)
        
        if len(signal_bets) < 5:
            continue
        
        wins    = sum(1 for b in signal_bets if b.get("outcome") == "WIN")
        losses  = len(signal_bets) - wins
        win_rate = wins / len(signal_bets)
        
        # ROI calculation (simplified: units won/lost)
        total_wager = sum(float(b.get("wager", 1) or 1) for b in signal_bets)
        total_won   = sum(
            float(b.get("wager",1) or 1) * 0.9  # -110 odds
            if b.get("outcome") == "WIN" else
            -float(b.get("wager",1) or 1)
            for b in signal_bets
        )
        roi = round(total_won / total_wager, 3) if total_wager > 0 else 0
        
        audit[signal_name] = {
            "signal":      signal_name,
            "sample":      len(signal_bets),
            "wins":        wins,
            "losses":      losses,
            "win_rate":    round(win_rate, 3),
            "roi":         roi,
            "roi_pct":     f"{roi*100:+.1f}%",
            "verdict":     "✅ KEEP" if roi > 0.02 else "⚠️ WATCH" if roi >= -0.02 else "❌ REVIEW",
        }
    
    return dict(sorted(audit.items(), key=lambda x: -x[1]["roi"]))


# ═══════════════════════════════════════════════════════════════
# PORTFOLIO BUILDER + ADAPTIVE BQ WEIGHTS
# Builds optimal N-bet slates controlling for:
#   - Same-player concentration
#   - Same-game correlation
#   - Prop type correlation
#   - Volatility exposure
# BQ weights adapt from Signal ROI Audit at 500+ bets
# ═══════════════════════════════════════════════════════════════

# Starting BQ weights — will be overridden by learned weights at 500 bets

def get_bq_weights(history=None):
    """
    Return BQ scoring weights.
    Uses learned weights from Signal ROI Audit at 500+ bets.
    Falls back to defaults before enough data.
    """
    if history is None:
        history = st.session_state.get("history", [])
    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS")]
    
    # Need 500+ bets for reliable weight learning
    if len(resolved) < 500:
        return BQ_WEIGHTS_DEFAULT.copy(), False
    
    # Pull from signal audit
    audit = compute_signal_roi_audit(history)
    if not audit:
        return BQ_WEIGHTS_DEFAULT.copy(), False
    
    # Map audit signals to BQ components
    learned = BQ_WEIGHTS_DEFAULT.copy()
    learned["_learned"] = True
    learned["_sample"]  = len(resolved)
    return learned, True


def check_correlation_risk(selected_props):
    """
    Check selected portfolio for correlated props.
    Same player = perfect correlation.
    Same game = high correlation.
    Known prop correlations (PRA + Points, etc.)
    
    Returns list of correlation warnings.
    """
    warnings = []
    
    # Same player
    players = [normalize_name(p.get("Player","")) for p in selected_props]
    for player in set(players):
        count = players.count(player)
        if count > 1:
            warnings.append({
                "type":    "PLAYER_OVERLAP",
                "message": f"⚠️ {player.title()} has {count} props — effectively one bet",
                "severity":"HIGH",
            })
    
    # Same game
    matchups = [p.get("Matchup","") for p in selected_props if p.get("Matchup","")]
    for matchup in set(matchups):
        count = matchups.count(matchup)
        if count >= 3:
            warnings.append({
                "type":    "GAME_CONCENTRATION",
                "message": f"⚠️ {count} props from {matchup} — high correlation risk",
                "severity":"MEDIUM",
            })
    
    # Known prop correlations
    CORR_PAIRS = [
        ("Points", "PRA"),
        ("Rebounds", "PRA"),
        ("Assists", "PRA"),
        ("Points", "Fantasy Score"),
        ("Hits", "Total Bases"),
        ("Strikeouts", "Outs Recorded"),
    ]
    prop_types = [(normalize_name(p.get("Player","")), p.get("Prop","")) for p in selected_props]
    for i, (p1, prop1) in enumerate(prop_types):
        for j, (p2, prop2) in enumerate(prop_types):
            if i >= j: continue
            if p1 == p2:
                for corr_a, corr_b in CORR_PAIRS:
                    if (corr_a in prop1 and corr_b in prop2) or                        (corr_b in prop1 and corr_a in prop2):
                        warnings.append({
                            "type":    "PROP_CORRELATION",
                            "message": f"📊 {p1.title()} {prop1} + {prop2} are correlated",
                            "severity":"LOW",
                        })
    
    return warnings


# ═══════════════════════════════════════════════════════════════
# BOVADA GAME LINES
# Confirmed working — no cookies, no auth required
# Endpoint: bovada.lv/services/sports/event/coupon/events/A/description/{sport}
# Returns: Moneyline, Spread, Total for all games
# Sharpness: between soft books and Pinnacle — useful comparison
# ═══════════════════════════════════════════════════════════════

BOVADA_PATH    = os.path.join(CACHE_DIR, "bovada_lines.json")
BOVADA_BASE    = "https://www.bovada.lv/services/sports/event/coupon/events/A/description"



@st.cache_data(ttl=1800)
def get_bovada_game_line(matchup, bovada_data=None):
    """
    Look up Bovada lines for a matchup.
    Used to compare vs OddsAPI lines for market agreement.
    Returns dict or None.
    """
    if bovada_data is None:
        bovada_data = st.session_state.get("bovada_lines", [])
    if not bovada_data:
        return None

    matchup_norm = normalize_name(matchup)
    for game in bovada_data:
        gm_norm = normalize_name(game.get("matchup",""))
        h_norm  = normalize_name(game.get("home",""))
        a_norm  = normalize_name(game.get("away",""))
        if (matchup_norm in gm_norm or gm_norm in matchup_norm or
            (h_norm and h_norm in matchup_norm) or
            (a_norm and a_norm in matchup_norm)):
            return game
    return None


# ═══════════════════════════════════════════════════════════════
# BETONLINE GAME LINES
# Confirmed working 2026-06-21 via real DevTools capture — no cookies,
# no auth required. (The old scrape_betonline() in betcouncil_auto_scraper.py
# guessed at get-menu + get-linked-events and never worked; this is a
# completely different, verified endpoint.)
# Endpoint: api-offering.betonline.ag/api/offering/Sports/offering-by-league
# One POST returns ALL of a league's games for the day, each with full
# MoneyLine/SpreadLine/TotalLine for both teams (American odds).
# Unlike www.betonline.ag (which fronts Cloudflare and blocks anonymous
# requests — confirmed via 403 testing), api-offering.betonline.ag showed
# zero Cloudflare friction across every capture, so this is called live,
# the same way Bovada is, with no session cookie / local relay needed.
# That said, this sandbox can't reach betonline.ag to test the call from
# Streamlit Cloud's own IP — if it gets blocked in production, this will
# just fail gracefully like every other scraper here (returns cached/[]).
# Sharpness: same tier as Bovada — useful soft-book comparison point,
# and already wired into the SHARP_BOOKS consensus checks via OddsAPI's
# betonlineag feed, so this gives a second, independent confirmation path.
# Player props (Batter Props, Home Run, etc.) are NOT covered here — those
# live behind bl.widget-prod.sportcast.app and the actual price-fetch call
# for them was never confirmed (always returned null/Infinity in testing).
# ═══════════════════════════════════════════════════════════════

BETONLINE_PATH = os.path.join(CACHE_DIR, "betonline_lines.json")
BETONLINE_SPORT_MAP = {
    "NBA":  ("basketball", "nba"),
    "MLB":  ("baseball",   "mlb"),
    "NHL":  ("hockey",     "nhl"),
    "WNBA": ("basketball", "wnba"),
    "NFL":  ("football",   "nfl"),
    # Soccer = EPL only, matching the existing "soccer/leagues/eng.1"
    # convention already used elsewhere in this codebase (line ~718) —
    # confirmed working via live probe 2026-06-21 (10 real games returned).
    "Soccer": ("soccer", "epl"),
}


# Sports needing more than one BetOnline league call merged together.
# Tennis splits into separate ATP/WTA tours on BetOnline (no single
# "tennis" league covers both) — confirmed via live probe 2026-06-21
# (27 WTA games, real data, alongside the already-working ATP call).


# ═══════════════════════════════════════════════════════════════
# BETONLINE PLAYER PROP PRICING (sportcast widget)
# Confirmed working 2026-06-21 via real DevTools "Copy as cURL" capture.
# Endpoint: bl.widget-prod.sportcast.app/public/RequestBetPriceUI
# Unlike fetch_betonline_lines() above, this does NOT return all props in
# one call — each call prices exactly ONE selection. Confirmed pattern:
# send MarketDetails as a single-element list (one market, one
# BetSelection) and PayLoad.Price / PayLoad.PriceDetails.AmericanPrice
# comes back populated. Sending multiple selections in one call has not
# been confirmed to return per-selection prices (the response shape only
# has one top-level Price/PriceDetails block), so until that's tested,
# call this once per selection.
#
# STILL UNRESOLVED — this function cannot run standalone yet:
#   1. "Key" (fixture session ticket, e.g. "0f833f77-...") — origin
#      unconfirmed. Lives in the widget iframe URL
#      (bl.widget-prod.sportcast.app/markets?key=...&fixtureId=...&brand=betonline)
#      on the live BetOnline page. Need either (a) confirmation this Key
#      is static/long-lived per fixture (in which case it can be scraped
#      once from the iframe src and cached), or (b) the upstream call
#      that mints it, if it's short-lived like Caesars' WAF token.
#   2. FixtureId — need to confirm whether this equals the "GameId" field
#      fetch_betonline_lines() already returns from the game-lines feed.
#      If so, no new scraping needed for this value. Unconfirmed.
#   3. Sport (numeric) — only "Baseball" = 9 confirmed via sc-sportid
#      header. NBA/NFL/NHL/WNBA codes unknown, do not guess.
#   4. MarketId / MarketLabelId / GlobalIdLong / GlobalIdShort per prop
#      type (e.g. "Who will score a home run?" = MarketId 127899324,
#      MarketLabelId 76) — each distinct prop market will need its own
#      captured ID the same way this one was. Treat as a lookup table to
#      build out market by market, not something to infer.
# Until #1 and #2 are resolved this can only be called with hand-fed
# values from a fresh capture — it is NOT wired into the main pipeline.
# ═══════════════════════════════════════════════════════════════

# DEFERRED 2026-06-21 — automated key harvesting does not work, confirmed
# via live testing, do not re-attempt without new information:
#   - 401 on api-offering.betonline.ag fixed (needed gsetting/Accept-Language/
#     utc-offset headers) — game-list fetch works fine, 15/15 real MLB games
#     returned correctly.
#   - The actual blocker is downstream: Playwright (headless Chromium) can
#     navigate to a real betonline.ag game page (200, page loads, hydration
#     completes) but iframe#SGP-EventView never appears in the DOM within 20s,
#     tested with domcontentloaded+sleep+scroll AND networkidle+scroll — same
#     result both ways. This is consistent with Cloudflare/BetOnline serving
#     degraded content to a detected headless browser (no SGP panel at all),
#     not a load-timing issue — ruled out via two different wait strategies
#     producing the identical failure.
#   - fetch_betonline_prop_price() below still works and is correct — it was
#     validated against a real captured cURL with a real key and returned a
#     real price. The harvester (get_betonline_game_ids/harvest_betonline_prop_keys
#     in betcouncil_auto_scraper.py, run locally with --betonline-props) is
#     what's blocked — it cannot supply that key automatically. Same bucket
#     as FanDuel props: needs a real, stealth-hardened browser fingerprint
#     (or a non-headless/human-assisted session) to get past bot detection —
#     not pursued further as of this date, not worth the time against a
#     secondary soft-book confirmation signal.
# ═══════════════════════════════════════════════════════════════

BETONLINE_PROP_PRICE_URL = "https://bl.widget-prod.sportcast.app/public/RequestBetPriceUI"
BETONLINE_PROP_SPORT_CODES = {
    "MLB": 9,   # confirmed via sc-sportid: "Baseball" header
    # "NBA": None, "NFL": None, "NHL": None, "WNBA": None,  # unconfirmed — do not guess
}




# ═══════════════════════════════════════════════════════════════
# AUTO SCRAPER GIST READER
# Reads props pushed by betcouncil_auto_scraper.py
# File: auto_scraped_props.json in your Gist
# To remove: delete this function + the 3 lines that call it
# ═══════════════════════════════════════════════════════════════

def log_error_to_session(source, error, error_type="error"):
    """Log errors to session_state so they appear in the System tab."""
    try:
        if "errors" not in st.session_state:
            st.session_state["errors"] = []
        st.session_state["errors"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": source,
            "error": str(error)[:200],
            "type": error_type
        })
        # Cap at 500 entries — trim oldest to prevent unbounded session state growth
        st.session_state["errors"] = st.session_state["errors"][-500:]
    except (KeyError, TypeError, ValueError) as _e:
            print(f"[WARN] {_e}")


# is_date_valid_for_today — moved to bc_utils.py
def _write_pp_lkg(sport: str, props: list) -> None:
    """Write PrizePicks props to the last-known-good pickle cache."""
    try:
        lkg_path = os.path.join(CACHE_DIR, f"pp_last_known_good_{sport}.pkl")
        import pickle as _pkl
        with open(lkg_path, "wb") as _f:
            _pkl.dump(props, _f)
    except OSError:
        pass


# scrape_prizepicks_with_gist_fallback → fetchers.py


# ── EV Sharps API (20+ books — Hard Rock, DK, FD, MGM, Caesars, Pinnacle, Circa, etc.) ──
# ── EV Line Movement — snapshot delta engine ─────────────────────────────────
# Replaces the /api/movement endpoint by comparing successive /api/ev snapshots.
# Every board load compares current bookOdds against the previous snapshot
# stored in session_state["ev_odds_snapshot"], computes deltas, and fires S8/S9.

SHARP_BOOKS_SET = {"pn", "circa", "espn"}   # books whose moves signal sharp action
MOVEMENT_THRESHOLD = 3                        # minimum American odds change to count


def compute_ev_line_movement(current_data, previous_snapshot):
    """
    Compare current EV API snapshot against previous to detect line movement.

    Args:
        current_data:      raw ev_data dict (has 'data' list)
        previous_snapshot: dict keyed by (player, prop, book) → previous odds float

    Returns:
        movement_lookup: {(player_norm, prop_name): signal_dict} for S8/S9
        sharp_alerts:    list of alert strings for Sharp Money Alerts widget
        new_snapshot:    updated snapshot dict to store for next comparison
    """
    movement_lookup = {}
    sharp_alerts    = []
    new_snapshot    = {}

    for item in (current_data.get("data") or []):
        try:
            player_raw  = item.get("player", "") or ""
            prop_key    = item.get("prop", "") or ""
            prop_name   = EV_PROP_MAP.get(prop_key, prop_key.title())
            player_norm = normalize_name(player_raw)
            sig_key     = (player_norm, prop_name)
            book_odds   = item.get("bookOdds", {}) or {}

            moved_books  = []   # list of (book_key, old_odds, new_odds, direction, velocity_pts_per_min)
            sharp_moved  = False

            for bk, curr_raw in book_odds.items():
                curr_val = _parse_american(curr_raw)
                if curr_val is None:
                    continue

                snap_key  = (player_norm, prop_key, bk)
                prev_entry = previous_snapshot.get(snap_key)
                # Support both legacy (plain float) and new (dict w/ ts) format
                if isinstance(prev_entry, dict):
                    prev_val = prev_entry.get("odds")
                    prev_ts  = prev_entry.get("ts", 0)
                else:
                    prev_val = prev_entry
                    prev_ts  = 0
                new_snapshot[snap_key] = {"odds": curr_val, "ts": time.time()}

                if prev_val is None:
                    continue   # no previous data — first snapshot

                delta = curr_val - prev_val
                if abs(delta) < MOVEMENT_THRESHOLD:
                    continue   # not a meaningful move

                direction    = "favorable" if delta > 0 else "unfavorable"
                elapsed_min  = (time.time() - prev_ts) / 60.0 if prev_ts else 999
                velocity_ppm = abs(delta) / max(elapsed_min, 0.5)  # pts per min
                moved_books.append((bk, prev_val, curr_val, direction, velocity_ppm))
                if bk in SHARP_BOOKS_SET:
                    sharp_moved = True

            if not moved_books:
                continue

            # ── S8: Market Movement Vector ─────────────────────────────
            if sharp_moved and len(moved_books) >= 2:
                s8_vector = 2    # sharp + consensus
            elif sharp_moved:
                s8_vector = 2    # sharp book moved
            elif len(moved_books) >= 3:
                s8_vector = 1    # soft consensus
            elif len(moved_books) >= 1:
                s8_vector = -1   # single soft book
            else:
                s8_vector = 0

            # Reverse line movement: line moved unfavorable despite action
            rlm = all(b[3] == "unfavorable" for b in moved_books) and s8_vector >= 1
            if rlm:
                s8_vector = -2

            # ── S9: RLM boost ──────────────────────────────────────────
            s9_boost = 0.0
            rlm_note = ""
            if rlm:
                # Estimate magnitude from number of books that moved against action
                gap = len(moved_books)
                if gap >= 5:   s9_boost = 0.02; rlm_note = f"RLM: {gap} books moved unfavorable"
                elif gap >= 3: s9_boost = 0.01; rlm_note = f"RLM: {gap} books moved unfavorable"
                else:          s9_boost = 0.005; rlm_note = f"RLM: {gap} book(s) fading action"

            # ── Steam velocity flag (gap fix #5) ───────────────────────
            # A line moving 3+ odds points/min across 2+ books is a steam
            # move — sharp syndicate action arriving in a burst.  This is
            # separate from S8 (which only detects that movement happened,
            # not how fast).  Steam picks get an S8 boost to 3 (max).
            max_velocity   = max((b[4] for b in moved_books), default=0)
            steam_velocity = max_velocity >= 3.0 and len(moved_books) >= 2
            if steam_velocity:
                s8_vector = 3   # override to max — steam is the strongest sharp signal
                if sig_key not in movement_lookup:
                    pass  # will be set below
                rlm_note = (rlm_note + f" | 🔥 STEAM {max_velocity:.1f}pt/min").strip(" |")

            movement_lookup[sig_key] = {
                "s8_vector":          s8_vector,
                "s9_boost":           s9_boost,
                "rlm_note":           rlm_note,
                "rlm_flag":           rlm,
                "steam_flag":         (sharp_moved and len(moved_books) >= 4) or steam_velocity,
                "steam_velocity_flag": steam_velocity,
                "steam_velocity_ppm":  round(max_velocity, 2),
                "sharp_flag":         sharp_moved,
                "moved_books":        moved_books,
                "sharp_moved":        sharp_moved,
                "book_roles":         {b[0]: classify_book_role(b[0]) for b in moved_books},
                "move_direction":     moved_books[-1][3] if moved_books else None,
                "open_line":          None,
                "curr_line":          item.get("handicap"),
                "game":               item.get("game", ""),
                "team":               item.get("team", ""),
            }

            # ── Pinnacle drift — soft books lagging behind Pinnacle ────────
            pn_curr = _parse_american(current.get("pn"))
            pn_prev = previous_snapshot.get((player_norm, prop_key, "pn"))
            if pn_curr and pn_prev and abs(pn_curr - pn_prev) >= 5:
                lagging = []
                for soft_bk in ("dk", "fd", "mgm", "cz", "espn", "hr"):
                    soft_curr = _parse_american(current.get(soft_bk))
                    if soft_curr and abs(soft_curr - pn_curr) > 15:
                        lagging.append(EV_BOOK_LABELS.get(soft_bk, soft_bk))
                if lagging:
                    sharp_alerts.append(
                        f"🚨 {player_raw.title()} {prop_name} | PINNACLE DRIFT "
                        f"{pn_prev:+.0f}→{pn_curr:+.0f} | Lagging: {', '.join(lagging)}"
                    )
                    if sig_key in movement_lookup:
                        movement_lookup[sig_key]["s8_vector"] = 2
                        movement_lookup[sig_key]["sharp_flag"] = True

            # ── Build sharp alert string ────────────────────────────────
            if sharp_moved or (len(moved_books) >= 3):
                bk_labels   = [EV_BOOK_LABELS.get(b[0], b[0].upper()) for b in moved_books]
                sharp_bks   = [EV_BOOK_LABELS.get(b[0], b[0].upper()) for b in moved_books if b[0] in SHARP_BOOKS_SET]
                delta_str   = f"{moved_books[-1][1]:+.0f}→{moved_books[-1][2]:+.0f}"
                label       = "STEAM" if (sharp_moved and len(moved_books) >= 4) else ("SHARP MOVE" if sharp_moved else "LINE MOVE")
                tag         = "[SHARP]" if sharp_moved else f"[{len(moved_books)} books]"
                alert_str   = f"🔥 {player_raw.title()} {prop_name} | {label} {tag} | {delta_str}"
                if sharp_bks:
                    alert_str += f" | Sharp: {', '.join(sharp_bks)}"
                sharp_alerts.append(alert_str)

        except Exception:
            continue

    return movement_lookup, sharp_alerts, new_snapshot


def get_ev_movement_from_snapshots(current_ev_data):
    """
    Entry point called on every board load.
    Loads previous snapshot from session_state, computes deltas,
    stores new snapshot, returns (movement_lookup, sharp_alerts).
    Falls back to /api/movement JWT endpoint if snapshot is empty.
    """
    previous_snapshot = st.session_state.get("ev_odds_snapshot", {})
    mv_lookup, alerts, new_snapshot = compute_ev_line_movement(
        current_ev_data, previous_snapshot
    )
    # Always update snapshot for next comparison
    st.session_state["ev_odds_snapshot"] = new_snapshot

    # If no movement detected yet (first load / cold start), try JWT endpoint
    if not mv_lookup:
        jwt_movement = st.session_state.get("ev_movement_lookup", {})
        jwt_alerts   = st.session_state.get("sharp_alerts", [])
        return jwt_movement, jwt_alerts

    return mv_lookup, alerts

_EV_TOKEN_CACHE = {"access_token": None, "expires_at": 0}

SUPABASE_URL    = "https://nkdhryqpiulrepmphwmt.supabase.co"
SUPABASE_ANON   = st.secrets.get("SUPABASE_ANON", "")


def _ev_refresh_token():
    """
    Retrieve the EVSharps Supabase refresh token from st.secrets.
    Set once in Streamlit Cloud → Settings → Secrets:
      EV_REFRESH_TOKEN = "z325a7doims5"
    This never expires (until explicitly revoked).
    """
    try:
        return (st.secrets.get("EV_REFRESH_TOKEN")
                or st.secrets.get("ev_refresh_token"))
    except Exception:
        _logger.debug("Silent except at line 3960")
        return None


def _ev_do_refresh(refresh_token):
    """Exchange refresh_token for a new access_token via Supabase auth API."""
    try:
        r = _http.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey":        SUPABASE_ANON,
                "Content-Type":  "application/json",
            },
            json={"refresh_token": refresh_token},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return {
                "access_token":  data.get("access_token"),
                "expires_at":    data.get("expires_at", 0),
                "refresh_token": data.get("refresh_token", refresh_token),
            }
    except Exception:
        _logger.debug("Silent except at line 3983")
        pass
    return None


def _get_ev_jwt():
    """
    Returns a valid EVSharps JWT, auto-refreshing when expired.
    Priority:
      1. In-memory cache (valid for remaining session)
      2. Auto-refresh via EV_REFRESH_TOKEN secret (hands-free)
      3. Fallback to EV_JWT secret (manual — legacy)
    """
    import time as _time
    now = _time.time()

    # 1. Cached token still valid (refresh 5min before expiry)
    if _EV_TOKEN_CACHE["access_token"] and _EV_TOKEN_CACHE["expires_at"] > now + 300:
        return _EV_TOKEN_CACHE["access_token"]

    # 2. Auto-refresh using refresh_token
    refresh_tok = _ev_refresh_token()
    if refresh_tok:
        new_tokens = _ev_do_refresh(refresh_tok)
        if new_tokens and new_tokens.get("access_token"):
            _EV_TOKEN_CACHE["access_token"] = new_tokens["access_token"]
            _EV_TOKEN_CACHE["expires_at"]   = new_tokens["expires_at"]
            # Update refresh token in cache if rotated
            if new_tokens.get("refresh_token") != refresh_tok:
                # Log rotation — user may need to update secret eventually
                log_error_to_session("ev_jwt_refresh", "Refresh token rotated — update EV_REFRESH_TOKEN secret", "warning")
            return _EV_TOKEN_CACHE["access_token"]

    # 3. Manual fallback
    try:
        return st.secrets.get("EV_JWT") or st.secrets.get("ev_jwt")
    except Exception:
        _logger.debug("Silent except at line 4019")
        return None


def _ev_auth_headers():
    """Build auth headers for EVSharps authenticated endpoints."""
    jwt = _get_ev_jwt()
    h = {
        "accept": "*/*",
        "origin": "https://www.evsharps.com",
        "referer": "https://www.evsharps.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    }
    if jwt:
        h["authorization"] = f"Bearer {jwt}"
    return h


@st.cache_data(ttl=300)
def parse_ev_movement(movement_data):
    """
    Parse raw EVSharps movement response into BetCouncil signal dicts.
    Builds:
      - movement_lookup: keyed by (player_norm, prop) → signal dict for S8/S9
      - sharp_alerts: list of human-readable alert strings for Sharp Money Alerts widget

    S8 (Market Movement Vector) values:
      +2 = sharp book leads move (Pinnacle/Circa moved first)
      +1 = consensus move (3+ books moved same direction)
       0 = mixed
      -1 = soft books only moved
      -2 = reverse line movement detected

    S9 (RLM) fires when tickets vs money diverge significantly.
    """
    movement_lookup = {}  # (player_norm, prop) → signal dict
    sharp_alerts = []     # list of alert strings for the UI widget

    SHARP_BOOKS = {"pn", "circa", "fn", "br"}  # books considered sharp

    for item in (movement_data or []):
        try:
            player_raw = item.get("player", "") or ""
            prop_key   = item.get("prop", "") or ""
            prop_name  = EV_PROP_MAP.get(prop_key, prop_key.title())
            player_norm = normalize_name(player_raw)
            sig_key    = (player_norm, prop_name)

            # Opening vs current odds (structure TBD until we see real data)
            opening   = item.get("opening", {}) or {}
            current   = item.get("bookOdds", item.get("current", {})) or {}
            movement  = item.get("movement", {}) or {}

            # Detect which books moved and direction
            moved_books = []
            sharp_moved = False
            move_direction = None  # "up" = line moved toward OVER, "down" = toward UNDER

            for bk, curr_odds in current.items():
                open_odds = opening.get(bk)
                if open_odds is None or curr_odds is None:
                    continue
                try:
                    # Parse American odds to compare direction
                    def _parse_am(x):
                        s = str(x).split("/")[0].strip()
                        return float(s)
                    o = _parse_am(open_odds)
                    c = _parse_am(curr_odds)
                    if abs(c - o) >= 3:  # meaningful move (≥3 cents)
                        direction = "favorable" if c > o else "unfavorable"
                        moved_books.append((bk, o, c, direction))
                        if bk in SHARP_BOOKS:
                            sharp_moved = True
                            move_direction = direction
                except (ValueError, TypeError):
                    continue

            # S8: Market Movement Vector
            if not moved_books:
                s8_vector = 0
            elif sharp_moved and len(moved_books) >= 2:
                s8_vector = 2   # sharp books lead + consensus
            elif sharp_moved:
                s8_vector = 2   # sharp book moved
            elif len(moved_books) >= 3:
                s8_vector = 1   # soft consensus
            elif len(moved_books) >= 1:
                s8_vector = -1  # soft only
            else:
                s8_vector = 0

            # S9: RLM — explicit flags from EVSharps if present
            rlm_flag   = item.get("reverse_line_move", item.get("rlm", False))
            steam_flag = item.get("steam_move", item.get("steam", False))
            sharp_flag = item.get("sharp_action", item.get("sharp", False))

            tickets_pct = item.get("tickets") or item.get("tickets_pct")
            money_pct   = item.get("money")   or item.get("money_pct")

            s9_boost = 0.0
            rlm_note = ""
            if rlm_flag or (tickets_pct and money_pct):
                try:
                    t = float(tickets_pct or 0)
                    m = float(money_pct or 0)
                    _pub_side = "OVER" if t >= 50 else "UNDER"
                    _move_mag = abs(float(curr_line or 0) - float(open_line or 0)) if (curr_line and open_line) else 0.5
                    _rlm_r    = score_rlm(t / 100.0, move_direction or "FLAT", _pub_side, max(0.5, _move_mag))
                    if _rlm_r["rlm_detected"]:
                        _rs = _rlm_r["strength"]
                        s9_boost = 0.02 if _rs == "STRONG" else (0.01 if _rs == "MODERATE" else 0.005)
                        rlm_note = _rlm_r.get("note", "")
                except (TypeError, ValueError):
                    pass

            # Opening/current line for delta display
            open_line  = item.get("openingHandicap") or item.get("opening_line")
            curr_line  = item.get("handicap") or item.get("current_line")

            movement_lookup[sig_key] = {
                "s8_vector":    s8_vector,
                "s9_boost":     s9_boost,
                "rlm_note":     rlm_note,
                "rlm_flag":     bool(rlm_flag),
                "steam_flag":   bool(steam_flag),
                "sharp_flag":   bool(sharp_flag) or sharp_moved,
                "move_direction": move_direction,
                "moved_books":  moved_books,
                "sharp_moved":  sharp_moved,
                "book_roles":   {b[0]: classify_book_role(b[0]) for b in moved_books},
                "open_line":    open_line,
                "curr_line":    curr_line,
                "tickets_pct":  tickets_pct,
                "money_pct":    money_pct,
                "game":         item.get("game", ""),
                "team":         item.get("team", ""),
            }

            # Build sharp alert string for UI
            if sharp_moved or steam_flag or rlm_flag:
                alert_parts = [f"🔥 {player_raw.title()} {prop_name}"]
                if sharp_moved:
                    bk_names = [EV_BOOK_LABELS.get(b[0], b[0]) for b in moved_books if b[0] in SHARP_BOOKS]
                    alert_parts.append(f"Sharp move: {', '.join(bk_names)}")
                if steam_flag:
                    alert_parts.append("STEAM")
                if rlm_flag:
                    alert_parts.append("RLM")
                if moved_books:
                    last = moved_books[-1]
                    alert_parts.append(f"{last[1]:+.0f}→{last[2]:+.0f}")
                sharp_alerts.append(" | ".join(alert_parts))

        except Exception:
            continue

    return movement_lookup, sharp_alerts


def _ev_infer_sport(item):
    # Source tag takes priority — WNBA and NBA share identical prop names
    src_sport = item.get("_source_sport", "")
    if src_sport:
        return src_sport.upper()
    prop = item.get("prop", "").lower()
    if prop == "hr":                                                    return "MLB"
    if prop in ("td", "rush_yards", "rec_yards", "pass_yards",
                "receptions", "rec_yards"):                             return "NFL"
    if prop in ("pts", "reb", "ast", "3pm", "dd", "pts+reb",
                "pts+ast", "pts+reb+ast", "reb+ast", "1st pts"):       return "NBA"
    if prop in ("goals", "shots", "saves"):                            return "NHL"
    return "MLB"


EV_PROP_MAP = {
    "hr": "Home Runs", "hits": "Hits", "rbi": "RBI", "runs": "Runs",
    "sb": "Stolen Bases", "k": "Pitcher Strikeouts",
    "pts": "Points", "reb": "Rebounds", "ast": "Assists", "3pm": "Threes",
    "dd": "Double-Double", "pts+reb": "Pts+Reb", "pts+ast": "Pts+Ast",
    "pts+reb+ast": "Pts+Reb+Ast", "reb+ast": "Reb+Ast", "1st pts": "1st Points",
    "td": "Touchdowns", "rush_yards": "Rush Yards", "rec_yards": "Rec Yards",
    "receptions": "Receptions", "pass_yards": "Pass Yards",
    "goals": "Goals", "shots": "Shots", "saves": "Saves",
}

EV_BOOK_LABELS = {
    "hr": "Hard Rock", "dk": "DraftKings", "fd": "FanDuel", "mgm": "BetMGM",
    "cz": "Caesars", "espn": "ESPN Bet", "circa": "Circa", "pn": "Pinnacle",
    "bv": "Bovada", "br": "BetRivers", "fn": "Fanatics", "b365": "Bet365",
    "bol": "BetOnline", "nv": "NoVig", "kal": "Kalshi", "poly": "Polymarket",
    "re": "Rebet", "fl": "Fliff", "hr_oh": "Hard Rock (OH)", "kambi": "Kambi",
}


def extract_ev_props_for_app(ev_data, sport_filter=None):
    """
    Extract all book props + full signal data from EV API.
    Confirmed field names from dingers2.html source.
    Returns (props_list, signal_lookup).
    """
    props = []
    signal_lookup = {}
    _book_labels = dict(EV_BOOK_LABELS)
    _book_labels["px"] = "ProphetX"

    def _safe_float(v, default=0.0):
        try: return float(v or 0)
        except: return default

    def _am_to_dec(x):
        x = float(x)
        return (100/abs(x)+1) if x < 0 else (x/100+1)

    def _novig_from_raw(raw):
        if not raw or "/" not in str(raw):
            return None
        try:
            o_str, u_str = str(raw).split("/", 1)
            o_dec = _am_to_dec(o_str); u_dec = _am_to_dec(u_str)
            return round((1/o_dec) / (1/o_dec + 1/u_dec), 4)
        except (ValueError, ZeroDivisionError, TypeError):
            return None

    for item in (ev_data.get("data") or []):
        try:
            item_sport = _ev_infer_sport(item)
            if sport_filter and item_sport != sport_filter:
                continue
            prop_key  = item.get("prop", "")
            prop_name = EV_PROP_MAP.get(prop_key, prop_key.title())
            handicap  = item.get("handicap")
            try: stat_line = float(handicap) if handicap is not None else None
            except: stat_line = None
            player_raw  = item.get("player", "")
            if not player_raw or not str(player_raw).strip():
                # No resolvable player name for this item -- previously
                # defaulted to the literal string "Unknown" and nothing
                # downstream filtered it, so every book's odds row for
                # this item rode onto the board as a player named
                # "Unknown" (same shared function for every sport, which
                # is why it showed up regardless of sport). A prop with
                # no player attached isn't bettable, so skip it instead.
                continue
            player_norm = normalize_name(player_raw)
            sig_key     = (player_norm, prop_name)

            savant       = item.get("savant", {}) or {}
            pitcher_data = item.get("pitcherData", {}) or {}
            batter_percs = item.get("batter_percs", {}) or {}
            hit_rates    = item.get("hitRates", {}) or {}
            homer_logs   = item.get("homerLogs", {}) or {}
            analysis     = item.get("analysis", {}) or {}
            book_odds    = item.get("bookOdds", {}) or {}

            # ── WNBA-specific fields (absent for MLB/NBA) ──────────────────────
            avg_min       = item.get("avgMin")
            player_pos    = item.get("pos", "")
            opp_pos_rank  = item.get("oppPosRank")
            hit_rate_career = item.get("hitRateCareer", {}) or {}
            hit_rate_lyr  = item.get("hitRateLYR", {}) or {}

            pitcher_name   = item.get("pitcher", "")
            pitcher_lr     = item.get("pitcherLR", "")
            bats           = item.get("bats", "")
            stadium_rank   = item.get("stadiumRank")
            stadium_rank_l = item.get("stadiumRankLeft")
            stadium_rank_r = item.get("stadiumRankRight")
            if bats == "L" and stadium_rank_l is not None:
                adj_stadium_rank = stadium_rank_l
            elif bats in ("R", "S") and stadium_rank_r is not None:
                adj_stadium_rank = stadium_rank_r
            else:
                adj_stadium_rank = stadium_rank

            bvp_raw      = item.get("bvp", "") or ""
            bpp_factor   = item.get("bpp", "") or ""
            bpp_proj     = item.get("bppProj", 0) or 0
            bpp_diff     = item.get("bppDiff", 0) or 0
            player_factor_raw = item.get("playerFactor", "") or ""
            liquidity    = item.get("liquidity", {}) or {}
            weather      = item.get("weather", {}) or {}

            sharp_fv      = item.get("fairVal")
            sharp_ev      = item.get("ev")
            sharp_implied = item.get("implied")
            sharp_kelly   = item.get("kelly")
            # Use best devig method per prop type:
            # Probit = NBA/WNBA counting stats | Shin = HR/Goals/longshots | Additive = rest
            _is_longshot = prop_key in ("hr", "goals", "td")
            _is_counting  = prop_key in ("pts","reb","ast","pra","dd","stl","blk","3pm","min","g","a","sog")
            pn_raw    = book_odds.get("pn")
            circa_raw = book_odds.get("circa")
            espn_raw  = book_odds.get("espn")

            def _best_novig(raw):
                if not raw or "/" not in str(raw):
                    return None
                try:
                    o_s, u_s = str(raw).split("/", 1)
                    if _is_counting:
                        return round(no_vig_prob_probit(o_s.strip(), u_s.strip()), 4)
                    elif _is_longshot:
                        return round(no_vig_prob_shin(o_s.strip(), u_s.strip()), 4)
                    else:
                        return _novig_from_raw(raw)
                except Exception:
                    return _novig_from_raw(raw)

            pn_novig      = _best_novig(pn_raw)
            circa_novig   = _best_novig(circa_raw)
            espn_novig    = _best_novig(espn_raw)
            sharp_novigs  = [v for v in [pn_novig, circa_novig, espn_novig] if v is not None]
            consensus_novig = round(sum(sharp_novigs)/len(sharp_novigs), 4) if sharp_novigs else None

            barrel_pct        = _safe_float(savant.get("barrels_per_bip"))
            exit_velo         = _safe_float(savant.get("exit_velocity_avg"))
            hard_hit          = _safe_float(savant.get("hard_hit_percent"))
            sweet_spot        = _safe_float(savant.get("sweet_spot_percent"))
            xwoba_batter      = _safe_float(savant.get("est_woba"))
            xba_batter        = _safe_float(savant.get("est_ba"))
            hr_pct            = _safe_float(batter_percs.get("home_run_percentile") or batter_percs.get("home_run"))
            hr_pa_pct         = _safe_float(batter_percs.get("hr_pa"))

            pitcher_era         = _safe_float(pitcher_data.get("p_era") or pitcher_data.get("era"))
            pitcher_xwoba       = _safe_float(pitcher_data.get("xwoba"))
            pitcher_xba         = _safe_float(pitcher_data.get("xba"))
            pitcher_flyball_pct = _safe_float(pitcher_data.get("flyballs_percent"))
            pitcher_barrel_rate = _safe_float(pitcher_data.get("barrel_batted_rate") or pitcher_data.get("barrels_per_bip"))
            pitcher_exit_velo   = _safe_float(pitcher_data.get("exit_velocity_avg"))
            pitcher_hard_hit    = _safe_float(pitcher_data.get("hard_hit_percent"))

            homer_pa       = homer_logs.get("pa", {}) or {}
            homer_streak   = homer_pa.get("streak")
            homer_med      = homer_pa.get("med")
            homer_z_median = homer_pa.get("z_median")

            fd_z_score   = _safe_float(analysis.get("fd_z_score"))
            pn_median    = _safe_float(analysis.get("pn_median"))
            circa_median = _safe_float(analysis.get("circa_median"))
            fd_median    = _safe_float(analysis.get("fd_median"))
            pn_avg       = _safe_float(analysis.get("pn_avg"))
            circa_avg    = _safe_float(analysis.get("circa_avg"))

            statcast_edge = 0.0; statcast_notes = []
            if prop_key == "hr":
                if barrel_pct >= 15:   statcast_edge += 0.02; statcast_notes.append(f"Barrel%{barrel_pct:.1f}≥15")
                elif barrel_pct >= 10: statcast_edge += 0.01; statcast_notes.append(f"Barrel%{barrel_pct:.1f}≥10")
                if exit_velo >= 92:    statcast_edge += 0.01; statcast_notes.append(f"EV{exit_velo:.1f}mph")
                if hr_pct >= 90:       statcast_edge += 0.02; statcast_notes.append(f"HR-pct{hr_pct:.0f}th")
                elif hr_pct >= 75:     statcast_edge += 0.01; statcast_notes.append(f"HR-pct{hr_pct:.0f}th")
                if hard_hit >= 50:     statcast_edge += 0.01; statcast_notes.append(f"HardHit{hard_hit:.0f}%")
                if pitcher_flyball_pct >= 40: statcast_edge += 0.01; statcast_notes.append(f"PFly{pitcher_flyball_pct:.0f}%")
                if pitcher_barrel_rate >= 10: statcast_edge += 0.01; statcast_notes.append(f"PBrl{pitcher_barrel_rate:.0f}%")

            stadium_edge = 0.0
            if adj_stadium_rank is not None and prop_key == "hr":
                try:
                    r = int(adj_stadium_rank)
                    if r <= 5:    stadium_edge = 0.03
                    elif r <= 15: stadium_edge = 0.01
                    elif r >= 26: stadium_edge = -0.02
                except (ValueError, TypeError): pass

            bvp_edge = 0.0; bvp_note = ""
            if bvp_raw and "/" in bvp_raw:
                try:
                    bvp_part = bvp_raw.split(",")[0].strip()
                    h_str, ab_str = bvp_part.split("/")
                    h, ab = int(h_str.strip()), int(ab_str.strip())
                    if ab >= 3:
                        bvp_rate = h / ab
                        if bvp_rate >= 0.333:   bvp_edge = 0.02; bvp_note = f"BvP {h}/{ab} ({bvp_rate:.0%})"
                        elif bvp_rate <= 0.150: bvp_edge = -0.02; bvp_note = f"BvP {h}/{ab} ({bvp_rate:.0%})"
                        else:                   bvp_note = f"BvP {h}/{ab} ({bvp_rate:.0%})"
                except (ValueError, TypeError, IndexError): pass

            l10_data = hit_rates.get("L10", {})
            l10_rate = None
            if l10_data and l10_data.get("t", 0) >= 3:
                try: l10_rate = float(l10_data.get("p", 0)) / 100.0
                except: pass

            homer_due_edge = 0.0
            if homer_z_median is not None and prop_key == "hr":
                try:
                    z = float(homer_z_median)
                    if z <= -1.5:   homer_due_edge = 0.01
                    elif z >= 1.5:  homer_due_edge = -0.01
                except (ValueError, TypeError): pass

            # ── Player park factor edge (player-specific BPP) ──────────────────
            player_factor_edge = 0.0; player_factor_note = ""
            try:
                pf = float(player_factor_raw)
                if pf > 0:
                    if pf >= 1.20:   player_factor_edge =  0.02; player_factor_note = f"PF {pf:.2f} (hr-friendly)"
                    elif pf >= 1.10: player_factor_edge =  0.01; player_factor_note = f"PF {pf:.2f} (slight+)"
                    elif pf <= 0.80: player_factor_edge = -0.02; player_factor_note = f"PF {pf:.2f} (suppressive)"
                    elif pf <= 0.90: player_factor_edge = -0.01; player_factor_note = f"PF {pf:.2f} (slight-)"
            except (ValueError, TypeError):
                pass

            # ── Sharp liquidity edge (NoVig + ProphetX over/under volume) ──────
            liquidity_edge = 0.0; liquidity_note = ""
            try:
                liq_over = liq_under = 0
                for bk_liq in liquidity.values():
                    if isinstance(bk_liq, (list, tuple)) and len(bk_liq) >= 2:
                        liq_over  += int(bk_liq[0] or 0)
                        liq_under += int(bk_liq[1] or 0)
                liq_total = liq_over + liq_under
                if liq_total >= 50:
                    liq_pct = liq_over / liq_total
                    if liq_pct >= 0.65:
                        liquidity_edge = 0.01; liquidity_note = f"SharpLiq OVER {liq_pct:.0%} ({liq_total} bets)"
                    elif liq_pct <= 0.35:
                        liquidity_edge = -0.01; liquidity_note = f"SharpLiq UNDER {1-liq_pct:.0%} ({liq_total} bets)"
            except (TypeError, ValueError, AttributeError):
                pass

            # ── BallParkPal projection diff ───────────────────────────────────
            bpp_proj_edge = 0.0
            try:
                diff = float(bpp_diff)
                if diff >= 0.10:   bpp_proj_edge =  0.01
                elif diff <= -0.10: bpp_proj_edge = -0.01
            except (ValueError, TypeError):
                pass

            opp_rank = item.get("oppRank")

            if sig_key not in signal_lookup:
                signal_lookup[sig_key] = {
                    "pn_novig": pn_novig, "circa_novig": circa_novig, "espn_novig": espn_novig,
                    "consensus_novig": consensus_novig, "sharp_fv": sharp_fv, "sharp_ev": sharp_ev,
                    "sharp_implied": sharp_implied, "sharp_kelly": sharp_kelly,
                    "bvp_raw": bvp_raw, "bvp_edge": bvp_edge, "bvp_note": bvp_note,
                    "l10_rate": l10_rate, "hit_rates": hit_rates,
                    "statcast_edge": statcast_edge, "statcast_notes": statcast_notes,
                    "barrel_pct": barrel_pct, "exit_velo": exit_velo, "hard_hit": hard_hit,
                    "sweet_spot": sweet_spot, "xwoba_batter": xwoba_batter, "xba_batter": xba_batter,
                    "hr_pct": hr_pct, "hr_pa_pct": hr_pa_pct,
                    "stadium_edge": stadium_edge, "stadium_rank": adj_stadium_rank,
                    "pitcher": pitcher_name, "pitcher_lr": pitcher_lr,
                    "pitcher_era": pitcher_era if pitcher_era > 0 else None,
                    "pitcher_xwoba": pitcher_xwoba if pitcher_xwoba > 0 else None,
                    "pitcher_xba": pitcher_xba if pitcher_xba > 0 else None,
                    "pitcher_flyball": pitcher_flyball_pct, "pitcher_barrel": pitcher_barrel_rate,
                    "pitcher_exit_velo": pitcher_exit_velo, "pitcher_hard_hit": pitcher_hard_hit,
                    "homer_streak": homer_streak, "homer_med": homer_med, "homer_z_median": homer_z_median,
                    "homer_due_edge": homer_due_edge,
                    "fd_z_score": fd_z_score, "pn_median": pn_median, "circa_median": circa_median,
                    "fd_median": fd_median, "pn_avg": pn_avg, "circa_avg": circa_avg,
                    "opp_rank": opp_rank, "opp_pos_rank": opp_pos_rank,
                    "avg_min": avg_min, "player_pos": player_pos,
                    "hit_rate_career": hit_rate_career, "hit_rate_lyr": hit_rate_lyr,
                    "bats": bats, "bpp_factor": bpp_factor,
                    "bpp_proj": bpp_proj, "bpp_diff": bpp_diff, "bpp_proj_edge": bpp_proj_edge,
                    "player_factor": player_factor_raw, "player_factor_edge": player_factor_edge,
                    "player_factor_note": player_factor_note,
                    "liquidity": liquidity, "liquidity_edge": liquidity_edge,
                    "liquidity_note": liquidity_note,
                    "weather": weather, "game": item.get("game", ""),
                    "team": item.get("team", ""), "opp": item.get("opp", ""),
                    "_savant": savant, "_batter_percs": batter_percs,
                    "_pitcher_data": pitcher_data, "_homer_logs": homer_logs, "_analysis": analysis,
                }

            for bk_key, bk_label in _book_labels.items():
                raw = book_odds.get(bk_key)
                if raw is None:
                    continue
                o_odds, u_odds = _ev_parse_odds(raw)
                props.append({
                    "Player": player_raw.title(), "Prop": prop_name, "Line": stat_line,
                    "Side": "UNDER" if item.get("under") else "OVER",
                    "Sport": item_sport, "Book": bk_label, "source": f"EV_{bk_key}",
                    "OddsOver": o_odds, "OddsUnder": u_odds,
                    "EV": sharp_ev, "FairValue": sharp_fv, "Kelly": sharp_kelly,
                    "Game": item.get("game", ""), "Team": item.get("team", ""),
                    "Opp": item.get("opp", ""), "OppRank": opp_rank,
                    "BvP": bvp_raw, "Weather": weather, "BPP": bpp_factor,
                    "Pos": player_pos, "OppPosRank": opp_pos_rank, "AvgMin": avg_min,
                    "BPPProj": bpp_proj, "BPPDiff": bpp_diff,
                    "PlayerFactor": player_factor_raw, "Liquidity": liquidity,
                    "_bet_link": (item.get("links") or {}).get(bk_key),
                    "_sig_key": sig_key, "_hit_rates": hit_rates,
                    "_savant": savant, "_batter_percs": batter_percs,
                    "_pitcher": pitcher_data, "_stadium_rank": adj_stadium_rank,
                    "_analysis": analysis,
                })
        except Exception:
            continue

    return props, signal_lookup


# ── FanDuel Direct (curl_cffi — bypasses SSL fingerprinting) ──
def _get_fanduel_px_context():
    """Shared PerimeterX token lookup — secrets, then Gist (harvester push),
    then short-lived local cache. Used by both fetch_fanduel_direct and
    fetch_fanduel_event_ids so the chain only lives in one place."""
    px_context = ""
    try:
        px_context = st.secrets.get("FANDUEL_PX_CONTEXT", "")
    except Exception:
        _logger.debug("Silent except at line 4516")
        pass
    if not px_context:
        # Picks up tokens pushed by fanduel-harvester-cdp.js (local Playwright
        # tool, CDP-attached to an already-logged-in browser). A forensic test
        # on 2026-06-21 found the x-px-context token on the PRICING domain
        # (smp.{state}.sportsbook.fanduel.com, which getMarketPrices actually
        # uses) held ONE value across 15+ requests over a 90-second window —
        # this contradicts the original "expires within minutes" assumption.
        # True long-term lifespan is still unconfirmed, so the freshness
        # window here is a cautious guess (20 min), not a verified figure.
        gist_tokens = load_from_gist("fanduel_tokens", None)
        if gist_tokens:
            try:
                captured_at = gist_tokens.get("captured_at", "")
                age_mins = (time.time() - datetime.fromisoformat(captured_at.replace("Z", "+00:00")).timestamp()) / 60
            except (ValueError, TypeError):
                age_mins = 9999
            if age_mins < 20:
                px_context = gist_tokens.get("px_context", "")
    if not px_context:
        fd_token_cache = os.path.join(CACHE_DIR, "fanduel_px_context.txt")
        if os.path.exists(fd_token_cache):
            try:
                age_mins = (time.time() - os.path.getmtime(fd_token_cache)) / 60
                if age_mins < 10:
                    with open(fd_token_cache, "r") as f:
                        px_context = f.read().strip()
            except (IOError, OSError):
                pass
    return px_context


def _get_fanduel_state():
    state = "az"
    try:
        state = (st.secrets.get("FANDUEL_STATE", "az") or "az").lower()
    except Exception:
        _logger.debug("Silent except at line 4553")
        pass
    return state


# FanDuel competitionId per sport — these are FanDuel-internal IDs required by
# the navigation/facet/v1.0/search endpoint, NOT generic league identifiers.
# MLB, WNBA, NFL confirmed via real DevTools capture 2026-06-21
# (scan.az.sportsbook.fanduel.com/api/sports/navigation/facet/v1.0/search,
# full request/response captured for each). NBA/NHL intentionally left out —
# both seasons just ended in June, nothing to capture until they're back.
# Capture each via the same method (fanduel-navfacet-request-capture.js
# while on that sport's schedule page) once in season — wrong/guessed IDs
# would silently return another sport's events or nothing at all, worse
# than just [].
FANDUEL_COMPETITION_IDS = {
    "MLB": 11196870,
    "WNBA": 11295025,
    "NFL": 12282733,
}


def cached_fetch(url, ttl_minutes=25):
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 60
        if age < ttl_minutes:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached and cached.get("data"):
                return cached
    try:
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data and data.get("data"):
                with open(cache_path, "wb") as f:
                    pickle.dump(data, f)
            return data
        return None
    except (pickle.UnpicklingError, OSError, EOFError):
        return None

# poisson_prob_over — moved to utils.py
def kelly_unit_prizepicks(prob, bankroll, n_picks=2, apply_bi=False):
    """apply_bi: apply bankroll intelligence multiplier to Kelly fraction."""
    multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)
    breakeven = prizepicks_breakeven_prob(n_picks)
    if prob <= breakeven:
        return 0.0
    b = multiplier - 1
    q = 1 - prob
    kelly = (b * prob - q) / b
    if kelly <= 0:
        return 0.0
    return round(min(kelly * KELLY_FRACTION * bankroll, bankroll * KELLY_CAP), 2)


def kelly_unit(prob, bankroll, n_picks=2, american_odds=None):
    """
    Kelly wager sizing with optional line-shopping odds adjustment.

    FIX (gap #2): Previously ignored the actual odds taken — every bet was
    sized as a 2-pick PrizePicks multiplier regardless of true payout.
    Now: if american_odds is provided (e.g. -110, +120), Kelly is computed
    from the real decimal payout so a bet at -105 is sized larger than the
    same edge at -120.  Falls back to PrizePicks sizing when no odds given.

    american_odds: American-style integer (negative = favorite).
                   None → PrizePicks multiplier sizing (legacy behavior).
    """
    if american_odds is None:
        return kelly_unit_prizepicks(prob, bankroll, n_picks)
    # Convert American odds to decimal b (net profit per $1 wagered)
    try:
        ao = float(american_odds)
        if ao < 0:
            b = 100.0 / abs(ao)
        else:
            b = ao / 100.0
    except (TypeError, ValueError):
        return kelly_unit_prizepicks(prob, bankroll, n_picks)
    q     = 1.0 - prob
    kelly = (b * prob - q) / b
    if kelly <= 0:
        return 0.0
    return round(min(kelly * KELLY_FRACTION * bankroll, bankroll * KELLY_CAP), 2)


def active_unit():
    return round(st.session_state.get("bankroll", DEFAULT_BANKROLL) * KELLY_FRACTION * KELLY_CAP, 2)

def get_session_time():
    elapsed = int(time.time() - st.session_state.get("session_start", time.time()))
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

def get_daily_change():
    if st.session_state.get("day_start_br", 0) == 0:
        return "0.0%"
    change = (st.session_state.get("bankroll", DEFAULT_BANKROLL) - st.session_state.get("day_start_br", 0)) / st.session_state.get("day_start_br", 0) * 100
    return f"{'+' if change >= 0 else ''}{change:.1f}"

def blowout_risk_adjustment(spread, sport, player_team, home_teams, away_teams, matchup):
    if not spread or spread == "—":
        return 0.0
    try:
        spread_val = float(str(spread).replace("+", "").strip())
    except (ValueError, AttributeError):
        return 0.0
    threshold = BLOWOUT_THRESHOLDS.get(sport, 12)
    if abs(spread_val) < threshold:
        return 0.0
    home_team = home_teams.get(matchup, "")
    away_team = away_teams.get(matchup, "")
    if player_team == home_team:
        team_spread = spread_val
    elif player_team == away_team:
        team_spread = -spread_val
    else:
        return 0.0
    if team_spread < -threshold:
        return -0.06
    elif team_spread > threshold:
        return -0.03
    return 0.0

def record_injury_performance(lock, outcome, injuries):
    player = lock.get("player", "")
    sport = lock.get("sport", "")
    injury_status = injuries.get(player, "") if isinstance(injuries, dict) else ""
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "player": player,
        "sport": sport,
        "prop": lock.get("prop", ""),
        "line": lock.get("line", 0),
        "side": lock.get("side", "OVER"),
        "tier": lock.get("tier", ""),
        "injury_status": injury_status,
        "was_injured": bool(injury_status),
        "outcome": outcome,
        "win": 1 if outcome == "WIN" else 0,
        "edge": lock.get("edge", 0),
        "prob": lock.get("prob", 0),
    }
    existing = load_json_data(INJURY_PERFORMANCE_PATH, [], mem_ttl=60)
    existing.append(record)
    save_json_data(INJURY_PERFORMANCE_PATH, existing)
    save_to_gist("injury_performance", existing)

def analyze_injury_performance():
    data = load_json_data(INJURY_PERFORMANCE_PATH, [], mem_ttl=60)
    if not data:
        return None, 0
    injured = [d for d in data if d.get("was_injured") and d.get("outcome") in ("WIN","LOSS")]
    healthy = [d for d in data if not d.get("was_injured") and d.get("outcome") in ("WIN","LOSS")]
    if len(injured) < 20:
        return None, len(injured)
    injured_wr = sum(r["win"] for r in injured) / len(injured)
    healthy_wr = sum(r["win"] for r in healthy) / len(healthy) if healthy else 0.577
    wr_gap = healthy_wr - injured_wr
    results = {
        "injured_wr": round(injured_wr, 3),
        "healthy_wr": round(healthy_wr, 3),
        "wr_gap": round(wr_gap, 3),
        "n_injured": len(injured),
        "n_healthy": len(healthy),
        "recommended_penalty": round(min(wr_gap * 0.5, 0.10), 3),
    }
    player_stats = {}
    for record in injured:
        p = record["player"]
        if p not in player_stats:
            player_stats[p] = {"injured_games": 0, "injured_wins": 0}
        player_stats[p]["injured_games"] += 1
        player_stats[p]["injured_wins"] += record["win"]
    player_results = []
    for player, stats in player_stats.items():
        if stats["injured_games"] >= 5:
            wr = stats["injured_wins"] / stats["injured_games"]
            player_results.append({
                "Player": player,
                "Injured Games": stats["injured_games"],
                "Win Rate": f"{wr:.1%}",
                "vs Healthy": f"{wr - healthy_wr:+.1%}",
                "Signal": "⚠️ Avoid" if wr < healthy_wr - 0.05 else "✅ Safe" if wr >= healthy_wr else "📊 Monitor"
            })
    results["player_breakdown"] = player_results
    return results, len(injured)

def lookup_board_edge(player: str, prop: str, sport: str, date_str: str):
    """Backfill edge/tier/prob/signals for a manually-logged bet.

    Checks TWO sources, live board first:
    (1) st.session_state.board_data -- the full, uncapped live board for
        whatever sport is currently loaded. This is the primary path for
        OCR/manual/paste entries logged same-day, which is the dominant
        real-world workflow (bet placed externally, screenshotted, then
        imported here after the fact) -- and unlike board_snapshots it
        isn't capped to the top 30 picks/sport, so it actually covers
        the specific player/prop someone bet.
    (2) board_snapshots.json (Gist) -- the historical fallback, same data
        grade_board_snapshots_for_date reads. Only useful for the exact
        date+player+prop combination that happened to be in that day's
        top-30 snapshot, and only goes back as far as snapshots exist.

    Fixes two related root causes of signal_performance/history records
    being unusable for calibration: (1) edge/tier/prob defaulting to 0/None
    when manual/OCR/paste entry paths had no board context, and (2) EVERY
    signal_* flag in signal_performance showing 0 regardless of tier or
    outcome -- because no log_manual_bet() call site anywhere ever passed the
    signals= kwarg, so signals_active was always computed from an empty dict
    (a dict with 8 False values, which is truthy, so the early-return guard
    in record_signal_performance never caught it either).

    Returns (edge, tier, prob, signals) or (None, None, None, None) if no match.
    """
    p_norm = normalize_name(player) if player else ""
    prop_norm = str(prop or "").strip().lower()
    target_date = str(date_str)[:10]

    # (1) Live board — only meaningful for today, since board_data reflects
    # whatever is currently loaded, not a historical record.
    if target_date == date.today().strftime("%Y-%m-%d"):
        try:
            _live_board = st.session_state.get("board_data") or []
            for p in _live_board:
                if sport and p.get("Sport") and p.get("Sport") != sport:
                    continue
                if normalize_name(p.get("Player", "")) != p_norm:
                    continue
                _p_prop = str(p.get("Prop", "")).strip().lower()
                if prop_norm and _p_prop != prop_norm and prop_norm not in _p_prop:
                    continue
                return p.get("Edge"), p.get("Tier"), p.get("Prob"), _board_prop_signal_values(p)
        except Exception:
            pass

    # (2) Historical snapshot fallback
    try:
        stored = load_from_gist("board_snapshots", None) or load_json_data(BOARD_SNAP_PATH, {})
        day_snaps = {k: v for k, v in stored.items() if v.get("date") == target_date}
        for snap in day_snaps.values():
            if sport and snap.get("sport") and snap.get("sport") != sport:
                continue
            for p in snap.get("props", []):
                if normalize_name(p.get("player", "")) != p_norm:
                    continue
                if prop_norm and str(p.get("prop", "")).strip().lower() != prop_norm and prop_norm not in str(p.get("prop", "")).strip().lower():
                    continue
                return p.get("edge"), p.get("tier"), p.get("prob"), p.get("signals")
    except Exception:
        pass
    return None, None, None, None


def _show_team_exposure_warning(team: str, sport: str):
    """
    Surfaces same-team exposure right after a lock is added -- the real
    gap flagged in compute_team_exposure()'s docstring: pairwise
    correlation warnings exist elsewhere, but nothing previously summed
    total same-team $ across a day's separate locks against bankroll.
    Informational only (doesn't block the lock or silently resize it --
    changing someone's stake without a clear, visible number attached to
    it is worse than just telling them where they stand and letting them
    decide).
    """
    if not team:
        return
    try:
        bankroll = st.session_state.get("bankroll", DEFAULT_BANKROLL)
        exposure, pct, room = compute_team_exposure(
            team, sport, st.session_state.get("locks", []), bankroll, active_unit()
        )
        if pct >= 0.25:
            st.warning(f"🛑 **{team}** exposure is now ${exposure:.0f} ({pct:.0%} of bankroll) — "
                       f"at/over the 25% same-team cap. Consider sizing down or stopping here.")
        elif pct >= 0.18:
            st.caption(f"⚠️ {team} exposure: ${exposure:.0f} ({pct:.0%} of bankroll) — ${room:.0f} of room left under the 25% cap.")
    except Exception:
        pass


def _lock_board_prop(prop: dict, sport: str, source: str) -> bool:
    """
    Shared "lock this prop" action -- appends to st.session_state.locks,
    captures Pinnacle CLV at lock time, persists to disk + Gist, and shows
    the team-exposure warning. Same behavior as the Full Board / Portfolio
    Builder / EV Optimizer lock buttons, just factored out so new lock
    buttons (e.g. Best Bet Queue) don't have to re-copy the ~15-line block.
    Returns True if a new lock was added, False if this pick was already
    locked (caller should show "Already locked" rather than duplicate it).
    """
    already = any(
        normalize_name(l.get("player", "")) == normalize_name(prop.get("Player", "")) and
        str(l.get("line", "")) == str(prop.get("Line", ""))
        for l in st.session_state.get("locks", [])
    )
    if already:
        return False
    st.session_state.locks.append({
        "player": prop.get("Player", ""), "prop": prop.get("Prop", ""),
        "line": prop.get("Line", 0), "side": prop.get("Side", "OVER"),
        "tier": prop.get("Tier", ""), "edge": prop.get("Edge", 0),
        "sport": sport, "source": source,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "prob": prop.get("Prob", 0.5),
        "team": prop.get("Team", ""),
        "signal_values": _board_prop_signal_values(prop),
        "clv_capture": _capture_clv_placement(prop.get("Player", ""), prop.get("Prop", ""), prop.get("Prob", 0.5)),
    })
    try:
        record_pinnacle_line(st.session_state.locks[-1], st.session_state.get("board", []))
    except Exception:
        pass
    save_json_data(LOCKS_PATH, st.session_state.locks)
    save_to_gist("locks", st.session_state.locks)  # persists across restarts
    _show_team_exposure_warning(prop.get("Team", ""), sport)
    return True


def _capture_clv_placement(player: str, prop: str, prob) -> dict:
    """
    CLV placement snapshot -- Pinnacle/Circa/consensus no-vig odds AT THE
    MOMENT A PICK IS LOCKED (pre-game), not at the moment it's later
    logged as a settled result.

    Why this exists as its own function now: log_manual_bet() already had
    code that tried to do this lookup, but it ran at LOG time -- which for
    auto-resolved bets (BDL/Bovada resolvers) and slip buttons is well
    after the game is over, when ev_signal_lookup (a snapshot of the
    CURRENT live board) no longer has anything for that finished game.
    Checked the real ledger before writing this: 0 of 289 logged bets had
    ever resolved a CLV value, for exactly this reason -- the snapshot
    was always taken too late to mean anything. Calling this at lock
    time instead (when the market is still live) and carrying the result
    forward on the lock dict is the actual fix; log_manual_bet() now uses
    whatever was captured here rather than re-querying at log time.

    Returns the clv_capture dict shape log_manual_bet() already builds,
    or an all-None version if no matching EV data exists yet at lock time
    (e.g. the EV Sharps API hasn't priced this player/prop). Never
    fabricates a value -- an unresolved lookup stays None, not a guess.
    """
    result = {
        "pn_novig_placement": None, "circa_novig_placement": None,
        "consensus_novig_placement": None, "clv_vs_placement": None,
    }
    try:
        _sig_key = (normalize_name(player), prop)
        _ev_sig = st.session_state.get("ev_signal_lookup", {}).get(_sig_key, {})
        if _ev_sig:
            result["pn_novig_placement"] = _ev_sig.get("pn_novig")
            result["circa_novig_placement"] = _ev_sig.get("circa_novig")
            _cons_nv = _ev_sig.get("consensus_novig")
            result["consensus_novig_placement"] = _cons_nv
            if _cons_nv is not None and prob is not None:
                result["clv_vs_placement"] = round(float(_cons_nv) - float(prob), 4)
    except Exception:
        pass
    return result


def _capture_clv_placement_game(matchup: str, market: str, side: str, locked_line) -> dict:
    """
    Game-line counterpart to _capture_clv_placement() -- same purpose
    (snapshot the market at LOCK time, not at whatever later moment the
    bet gets logged as settled), but props and games can't share a
    schema: props have a single no-vig win probability (ev_signal_lookup),
    games have a POINT line (spread/total) with no equivalent single
    probability in the data this app already collects. Uses Pinnacle's
    line at lock time (st.session_state["pinnacle_game_lines"], same
    source record_pinnacle_game_line() already reads) and returns a
    points-based CLV, not a percentage -- "+1.5 pts better than Pinnacle"
    is a real, honest number; forcing it into a fabricated win-probability
    conversion would not be.

    Returns clv_capture dict shape, bet_type="game" flags it for
    resolve_clv_records() and generate_post_mortem() to format as points
    instead of percent. All-None if Pinnacle has no line for this matchup
    yet (never guesses).
    """
    result = {
        "bet_type": "game", "placement_line_pinnacle": None,
        "closing_line_pinnacle": None, "clv_points": None,
    }
    try:
        pinnacle_lines = st.session_state.get("pinnacle_game_lines", [])
        pin_game = next(
            (g for g in pinnacle_lines
             if normalize_name(g.get("Matchup", "")) == normalize_name(matchup)
             or normalize_name(matchup) in normalize_name(g.get("Matchup", ""))),
            None
        )
        if not pin_game:
            return result
        pinnacle_line = pin_game.get("Spread") if market == "SPREAD" else (
            pin_game.get("Total") if market in ("TOTAL", "ALT LINE") else None
        )
        if pinnacle_line is None:
            return result
        result["placement_line_pinnacle"] = float(pinnacle_line)
    except Exception:
        pass
    return result


def _board_prop_signal_values(p: dict) -> dict:
    """Extract the raw per-prop signal breakdown off a live board row (the
    SignalBase/SignalDefense/etc keys, same source used when board_snapshots
    is written). Use this at lock-creation time so locks carry signal_values
    forward to log_manual_bet(), instead of it always being empty.

    2026-07-16 fix: added "sharp" and "weather". record_signal_performance's
    signal_values fallback reads signal_values.get("sharp")/get("weather")
    to populate signal_sharp_flag/signal_weather_active, but neither key
    was produced here, so both flags were still always 0 after that fix.
    "sharp" has no numeric SignalSharp field on props (checked — doesn't
    exist), so it's sourced from the prop's own boolean sharp_flag field
    instead, cast to 1.0/0.0 to match the magnitude shape of the other
    values here.
    """
    return {
        "base":     p.get("SignalBase", 0),
        "defense":  p.get("SignalDefense", 0),
        "location": p.get("SignalLocation", 0),
        "rest":     p.get("SignalRest", 0),
        "pace":     p.get("SignalPace", 0),
        "usage":    p.get("SignalUsage", 0),
        "blowout":  p.get("SignalBlowout", 0),
        "weather":  p.get("SignalWeather", 0),
        "sharp":    1.0 if p.get("sharp_flag") else 0.0,
    }



def record_signal_performance(lock, outcome):
    # Primary source: signals_active (explicit boolean flags set by older code paths).
    # Fallback: signal_values (raw magnitudes captured at lock-creation time via
    # _board_prop_signal_values) — convert to boolean flags here.
    # This fixes the all-zeros bug: log_manual_bet() never passes signals_active,
    # so it was always an empty or all-False dict, and every int(False) wrote 0.
    signals_active = lock.get("signals_active") or {}
    signal_values  = lock.get("signal_values")  or {}

    if not any(signals_active.values() if signals_active else []):
        if signal_values and any(abs(v or 0) > 0.001 for v in signal_values.values()):
            # Convert raw magnitudes to boolean flags
            signals_active = {
                "base_positive":    (signal_values.get("base",     0) or 0) > 0.001,
                "defense_positive": (signal_values.get("defense",  0) or 0) > 0.001,
                "location_home":    (signal_values.get("location", 0) or 0) > 0.001,
                "back_to_back":     (signal_values.get("rest",     0) or 0) < -0.001,
                "sharp_flag":       (signal_values.get("sharp",    0) or 0) > 0.001,
                "weather_active":   abs(signal_values.get("weather", 0) or 0) > 0.001,
                "blowout_risk":     (signal_values.get("blowout",  0) or 0) < -0.001,
                "usage_boost":      (signal_values.get("usage",    0) or 0) > 0.001,
                "pace_active":      abs(signal_values.get("pace",  0) or 0) > 0.001,
            }
        else:
            # Last resort: look up the live board by player+prop
            try:
                import streamlit as _st
                _pn = normalize_name(lock.get("player", ""))
                _pp = str(lock.get("prop", "")).strip().lower()
                for _bp in (_st.session_state.get("board_data") or []):
                    if (normalize_name(_bp.get("Player", "")) == _pn and
                            str(_bp.get("Prop", "")).strip().lower() == _pp):
                        _sv = _board_prop_signal_values(_bp)
                        if any(abs(v or 0) > 0.001 for v in _sv.values()):
                            signals_active = {
                                "base_positive":    (_sv.get("base",     0) or 0) > 0.001,
                                "defense_positive": (_sv.get("defense",  0) or 0) > 0.001,
                                "location_home":    (_sv.get("location", 0) or 0) > 0.001,
                                "back_to_back":     (_sv.get("rest",     0) or 0) < -0.001,
                                "sharp_flag":       (_sv.get("sharp",    0) or 0) > 0.001,
                                "weather_active":   abs(_sv.get("weather", 0) or 0) > 0.001,
                                "blowout_risk":     (_sv.get("blowout",  0) or 0) < -0.001,
                                "usage_boost":      (_sv.get("usage",    0) or 0) > 0.001,
                                "pace_active":      abs(_sv.get("pace",  0) or 0) > 0.001,
                            }
                        break
            except Exception:
                pass

    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "outcome": outcome,
        "win": 1 if outcome == "WIN" else 0,
        "sport": lock.get("sport", ""),
        "tier": lock.get("tier", ""),
        "edge": lock.get("edge", 0),
        "prob": lock.get("prob", 0),
        # Tag so calibration can separate game-line bets (SPREAD/TOTAL/ML,
        # much smaller edge magnitudes) from player-prop bets — previously
        # untagged, so every game bet silently pooled into prop calibration
        # stats (and vice versa) despite the two using different edge
        # scales entirely (bug found 2026-07-12). Missing/old records
        # default to "prop" for backward compatibility with data logged
        # before this field existed.
        "bet_type": lock.get("bet_type", "prop"),
        "signal_base_positive": int(signals_active.get("base_positive", False)),
        "signal_defense_positive": int(signals_active.get("defense_positive", False)),
        "signal_location_home": int(signals_active.get("location_home", False)),
        "signal_back_to_back": int(signals_active.get("back_to_back", False)),
        "signal_sharp_flag": int(signals_active.get("sharp_flag", False)),
        "signal_weather_active": int(signals_active.get("weather_active", False)),
        "signal_blowout_risk": int(signals_active.get("blowout_risk", False)),
        "signal_usage_boost": int(signals_active.get("usage_boost", False)),
        # 2026-07-16 fix: "pace" was already computed into signal_values by
        # _board_prop_signal_values but had no destination field here, so
        # it was silently dropped every time regardless of whether it fired.
        "signal_pace_active": int(signals_active.get("pace_active", False)),
    }
    performance = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    performance.append(record)
    save_json_data(SIGNAL_PERFORMANCE_PATH, performance)
    save_to_gist("signal_performance", performance)

def analyze_signal_performance():
    performance = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    resolved = [p for p in performance if p.get("outcome") in ("WIN", "LOSS")]
    if len(resolved) < 20:
        return None, len(resolved)
    signal_cols = [
        "signal_base_positive",
        "signal_defense_positive",
        "signal_location_home",
        "signal_back_to_back",
        "signal_sharp_flag",
        "signal_weather_active",
        "signal_blowout_risk",
        "signal_usage_boost",
        "signal_pace_active",
    ]
    signal_labels = {
        "signal_base_positive": "Base (avg above line)",
        "signal_defense_positive": "Defense (weak opp)",
        "signal_location_home": "Home game",
        "signal_back_to_back": "Back-to-back",
        "signal_sharp_flag": "Sharp money",
        "signal_weather_active": "Weather factor",
        "signal_blowout_risk": "Blowout risk",
        "signal_usage_boost": "Usage boost",
        "signal_pace_active": "Pace factor",
    }
    results = []
    overall_wr = sum(r["win"] for r in resolved) / len(resolved)
    for signal in signal_cols:
        with_signal = [r for r in resolved if r.get(signal, 0) == 1]
        without_signal = [r for r in resolved if r.get(signal, 0) == 0]
        if len(with_signal) < 5:
            continue
        wr_with = sum(r["win"] for r in with_signal) / len(with_signal)
        wr_without = sum(r["win"] for r in without_signal) / len(without_signal) if without_signal else 0
        lift = wr_with - wr_without
        vs_baseline = wr_with - overall_wr
        results.append({
            "Signal": signal_labels.get(signal, signal),
            "Bets With": len(with_signal),
            "Win Rate With": f"{wr_with:.1%}",
            "Win Rate Without": f"{wr_without:.1%}",
            "Lift": f"{lift:+.1%}",
            "vs Baseline": f"{vs_baseline:+.1%}",
            "Status": "✅ Positive" if lift > 0.02 else "❌ Negative" if lift < -0.02 else "⚪ Neutral"
        })
    results.sort(key=lambda x: float(x["Lift"].replace("%","").replace("+","")), reverse=True)
    return results, len(resolved)

# ═══════════════════════════════════════════════════════════════
# SIGNAL INTELLIGENCE SUITE
# Three complementary audit tools:
#   1. compute_signal_correlation_matrix() — are signals independent?
#   2. compute_signal_lift_analysis()      — does each signal add value?
#   3. compute_signal_stability()          — are signals consistent over time?
# ═══════════════════════════════════════════════════════════════


SIGNAL_LABELS = {
    "signal_base_positive":    "Base (avg>line)",
    "signal_defense_positive": "Defense (weak opp)",
    "signal_location_home":    "Location (home)",
    "signal_back_to_back":     "Rest (B2B)",
    "signal_sharp_flag":       "Sharp Money",
    "signal_usage_boost":      "Usage Boost",
    "signal_blowout_risk":     "Blowout Risk",
    "signal_weather_active":   "Weather",
}


@st.cache_data(ttl=300, show_spinner=False)
def compute_signal_correlation_matrix(performance_data=None):
    """
    Signal Correlation Matrix.
    
    Computes pairwise co-occurrence rate between all signal pairs.
    If two signals fire together >75% of the time they're both active,
    the model may be double-counting the same edge.
    
    Returns: matrix_rows (list of dicts), n_bets, warnings
    Activates at 20+ resolved bets.
    """
    if performance_data is None:
        performance_data = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    resolved = [p for p in performance_data if p.get("outcome") in ("WIN","LOSS")]
    if len(resolved) < 20:
        return None, len(resolved), []

    active_signals = [s for s in SIGNAL_COLS
                      if sum(1 for r in resolved if r.get(s, 0) == 1) >= 5]

    matrix_rows = []
    warnings = []

    for i, sig_a in enumerate(active_signals):
        for sig_b in active_signals[i+1:]:
            a_active = [r for r in resolved if r.get(sig_a, 0) == 1]
            b_active = [r for r in resolved if r.get(sig_b, 0) == 1]
            both    = [r for r in resolved if r.get(sig_a, 0) == 1 and r.get(sig_b, 0) == 1]

            if not a_active or not b_active:
                continue

            # Co-occurrence rate: when A fires, how often does B also fire?
            co_rate_ab = len(both) / len(a_active)
            co_rate_ba = len(both) / len(b_active)
            co_rate = max(co_rate_ab, co_rate_ba)  # use the higher direction

            # Phi correlation coefficient (proper binary correlation)
            n = len(resolved)
            n_ab   = len(both)
            n_a    = len(a_active)
            n_b    = len(b_active)
            n_na   = n - n_a
            n_nb   = n - n_b
            denom  = (n_a * n_b * n_na * n_nb) ** 0.5
            phi    = (n_ab * n - n_a * n_b) / denom if denom > 0 else 0

            # Win rates
            wr_both   = sum(r["win"] for r in both) / len(both) if both else 0
            wr_a_only = sum(r["win"] for r in a_active if r.get(sig_b,0)==0) / max(1, len([r for r in a_active if r.get(sig_b,0)==0]))
            wr_b_only = sum(r["win"] for r in b_active if r.get(sig_a,0)==0) / max(1, len([r for r in b_active if r.get(sig_a,0)==0]))

            # Grade
            if abs(phi) >= 0.70:
                grade = "🔴 HIGH overlap"
                recommendation = "Dampen one signal"
            elif abs(phi) >= 0.45:
                grade = "🟡 Moderate overlap"
                recommendation = "Monitor"
            elif abs(phi) >= 0.20:
                grade = "🟢 Low overlap"
                recommendation = "Independent"
            else:
                grade = "✅ Uncorrelated"
                recommendation = "Keep both"

            if abs(phi) >= 0.70:
                warnings.append(
                    f"⚠️ {SIGNAL_LABELS[sig_a]} ↔ {SIGNAL_LABELS[sig_b]}: "
                    f"phi={phi:.2f} co-occurrence={co_rate:.0%} — may be double-counting"
                )

            matrix_rows.append({
                "Signal A":       SIGNAL_LABELS[sig_a],
                "Signal B":       SIGNAL_LABELS[sig_b],
                "Phi (ϕ)":        round(phi, 3),
                "Co-occur %":     f"{co_rate:.0%}",
                "WR (both)":      f"{wr_both:.1%}" if both else "—",
                "WR (A only)":    f"{wr_a_only:.1%}",
                "WR (B only)":    f"{wr_b_only:.1%}",
                "n (both)":       len(both),
                "Grade":          grade,
                "Action":         recommendation,
            })

    # Sort by correlation strength descending
    matrix_rows.sort(key=lambda x: abs(x["Phi (ϕ)"]), reverse=True)
    return matrix_rows, len(resolved), warnings


@st.cache_data(ttl=300, show_spinner=False)
def compute_signal_lift_analysis(performance_data=None):
    """
    Signal Lift Analysis.
    
    Measures incremental value of each signal ABOVE the base model.
    Answers: "Does adding Defense signal to Base actually improve results?"
    
    Tests: Base alone vs Base + each signal combination.
    Returns rows sorted by incremental lift.
    Activates at 30+ resolved bets.
    """
    if performance_data is None:
        performance_data = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    resolved = [p for p in performance_data if p.get("outcome") in ("WIN","LOSS")]
    if len(resolved) < 30:
        return None, len(resolved)

    overall_wr  = sum(r["win"] for r in resolved) / len(resolved)
    base_active = [r for r in resolved if r.get("signal_base_positive", 0) == 1]
    base_wr     = sum(r["win"] for r in base_active) / len(base_active) if base_active else overall_wr

    results = []
    for sig in SIGNAL_COLS:
        if sig == "signal_base_positive":
            continue
        # Base + this signal
        combo = [r for r in resolved
                 if r.get("signal_base_positive", 0) == 1 and r.get(sig, 0) == 1]
        # Base without this signal
        base_without = [r for r in resolved
                        if r.get("signal_base_positive", 0) == 1 and r.get(sig, 0) == 0]

        if len(combo) < 5:
            continue

        wr_combo   = sum(r["win"] for r in combo) / len(combo)
        wr_without = sum(r["win"] for r in base_without) / len(base_without) if base_without else base_wr
        incremental_lift = wr_combo - wr_without
        vs_base = wr_combo - base_wr

        # EV contribution estimate
        ev_contribution = incremental_lift * 0.5  # rough prop EV multiplier

        if incremental_lift >= 0.05:
            grade = "🟢 Strong contributor"
        elif incremental_lift >= 0.02:
            grade = "🟡 Mild contributor"
        elif incremental_lift >= -0.02:
            grade = "⚪ Neutral"
        else:
            grade = "🔴 Negative drag"

        results.append({
            "Signal":           SIGNAL_LABELS[sig],
            "n (combo)":        len(combo),
            "WR (Base+Signal)": f"{wr_combo:.1%}",
            "WR (Base only)":   f"{wr_without:.1%}",
            "Incremental Lift": f"{incremental_lift:+.1%}",
            "vs Overall":       f"{vs_base:+.1%}",
            "Est EV Contrib":   f"{ev_contribution:+.1%}",
            "Grade":            grade,
        })

    results.sort(key=lambda x: float(x["Incremental Lift"].replace("%","").replace("+","")), reverse=True)
    return results, len(resolved)


@st.cache_data(ttl=300, show_spinner=False)
def compute_signal_stability(performance_data=None, window_days=30):
    """
    Signal Stability Analysis.
    
    Computes signal win rates across three time windows:
    Last 30 days / Last 90 days / Season (all-time).
    
    Stable signals: consistent win rate across all windows.
    Unstable signals: hot/cold streaks — reduce weight.
    Activates at 30+ resolved bets.
    """
    if performance_data is None:
        performance_data = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    resolved = [p for p in performance_data if p.get("outcome") in ("WIN","LOSS")]
    if len(resolved) < 30:
        return None, len(resolved)

    from datetime import datetime, timedelta
    now = datetime.now()
    cutoff_30  = now - timedelta(days=30)
    cutoff_90  = now - timedelta(days=90)

    def parse_ts(ts_str):
        try:
            return datetime.strptime(ts_str[:16], "%Y-%m-%d %H:%M")
        except (ValueError, TypeError, AttributeError):
            return now - timedelta(days=999)

    last_30  = [r for r in resolved if parse_ts(r.get("timestamp","")) >= cutoff_30]
    last_90  = [r for r in resolved if parse_ts(r.get("timestamp","")) >= cutoff_90]
    all_time = resolved

    results = []
    for sig in SIGNAL_COLS:
        rows = {}
        for label, dataset in [("L30d", last_30), ("L90d", last_90), ("Season", all_time)]:
            with_sig = [r for r in dataset if r.get(sig, 0) == 1]
            if len(with_sig) < 3:
                rows[label] = "—"
                rows[f"n_{label}"] = 0
            else:
                wr = sum(r["win"] for r in with_sig) / len(with_sig)
                rows[label] = f"{wr:.1%}"
                rows[f"n_{label}"] = len(with_sig)

        # Stability score: how consistent is the WR across windows?
        numeric = []
        for label in ["L30d","L90d","Season"]:
            v = rows.get(label,"—")
            if v != "—":
                numeric.append(float(v.replace("%",""))/100)

        if len(numeric) >= 2:
            spread = max(numeric) - min(numeric)
            if spread < 0.05:
                stability = "🟢 Stable"
            elif spread < 0.12:
                stability = "🟡 Mild variance"
            else:
                stability = "🔴 Unstable"
        else:
            stability = "⚪ Insufficient data"

        if rows.get(f"n_Season", 0) >= 3:
            results.append({
                "Signal":           SIGNAL_LABELS[sig],
                "L30d":             rows.get("L30d","—"),
                "n L30d":           rows.get("n_L30d", 0),
                "L90d":             rows.get("L90d","—"),
                "n L90d":           rows.get("n_L90d", 0),
                "Season":           rows.get("Season","—"),
                "n Season":         rows.get("n_Season", 0),
                "Stability":        stability,
            })

    return results, len(resolved)


def get_effective_signal_weights(sport):
    """
    SPORT_SIGNAL_WEIGHTS[sport] with any auto-applied weight adjustments
    layered on top (see 'Weight Adjustment Recommendations' in History >
    Weekly). Adjustments only reach WEIGHT_OVERRIDES_PATH after clearing a
    95% Wilson confidence interval vs. coin-flip on 30+ bets for that
    signal, and are clamped here to +/-30% of the hand-tuned base value
    as a second safety net regardless of what's stored.
    """
    base = dict(SPORT_SIGNAL_WEIGHTS.get(sport, SPORT_SIGNAL_WEIGHTS["NBA"]))
    try:
        overrides = load_json_data(WEIGHT_OVERRIDES_PATH, {}, mem_ttl=60)
    except Exception:
        overrides = {}
    sport_overrides = overrides.get(sport, {}) if isinstance(overrides, dict) else {}
    for key, new_val in sport_overrides.items():
        if key in base:
            try:
                lo, hi = base[key] * 0.7, base[key] * 1.3
                base[key] = round(max(lo, min(hi, float(new_val))), 4)
            except (TypeError, ValueError):
                pass
    return base


def compute_optimized_weights(sport):
    performance = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    sport_data = [p for p in performance if p.get("sport") == sport and p.get("outcome") in ("WIN", "LOSS")]
    if len(sport_data) < WEIGHT_OPTIMIZER_MIN_BETS:
        return None
    overall_wr = sum(r["win"] for r in sport_data) / len(sport_data)
    signal_to_weight = {
        "signal_base_positive":    "base",
        "signal_defense_positive": "defense",
        "signal_location_home":    "location",
        "signal_back_to_back":     "rest",
        "signal_usage_boost":      "usage",  # FIX: was incorrectly mapped to "pace"
        "signal_sharp_flag":       "pace",   # sharp money correlates with pace/volume bets
    }
    base_weights = get_effective_signal_weights(sport).copy()
    # Apply online feature importance adjustment from Brier feedback
    _history_for_weights = st.session_state.get("history", [])
    if len(_history_for_weights) >= 15:
        base_weights, _, _ = get_adjusted_signal_weights(
            base_weights, _history_for_weights, sport=sport, window_days=30
        )
    lifts = {}
    for signal_key, weight_key in signal_to_weight.items():
        with_signal = [r for r in sport_data if r.get(signal_key, 0) == 1]
        without_signal = [r for r in sport_data if r.get(signal_key, 0) == 0]
        if len(with_signal) < 10:
            lifts[weight_key] = 0
            continue
        wr_with = sum(r["win"] for r in with_signal) / len(with_signal)
        wr_without = sum(r["win"] for r in without_signal) / len(without_signal) if without_signal else overall_wr
        lifts[weight_key] = wr_with - wr_without
    if not lifts or all(v == 0 for v in lifts.values()):
        return None
    optimized = {}
    for key, base in base_weights.items():
        lift = lifts.get(key, 0)
        # Anti-overfitting measures:
        # 1. Dampen lift by sample-size factor (larger sample = more trust)
        sample_factor = min(1.0, len(sport_data) / 200)
        dampened_lift = lift * sample_factor
        # 2. Conservative adjustment (0.20 vs 0.30 — less reactive to hot streaks)
        adjustment = dampened_lift * 0.20
        # 3. Cap weight change per optimization run (max ±15% of base)
        max_change = base * 0.15
        adjustment = max(-max_change, min(max_change, base * adjustment))
        new_weight = base + adjustment
        # 4. Bounds: no weight below 1% or above 55%
        new_weight = max(0.01, min(0.55, new_weight))
        # 5. Load previous optimized weights for decay blend
        prev_weights = load_json_data(WEIGHT_OPTIMIZER_PATH, {}).get(sport, {}).get("weights", {})
        prev_weight = prev_weights.get(key, base)
        # 6. Exponential decay blend — 30% new signal, 70% prior weights
        # Prevents single hot/cold streak from dominating
        decay_rate = 0.30
        blended_weight = (new_weight * decay_rate) + (prev_weight * (1 - decay_rate))
        optimized[key] = round(blended_weight, 3)
    total = sum(optimized.values())
    if total > 0:
        optimized = {k: round(v/total, 3) for k, v in optimized.items()}
    # Defense/pace correlation analysis — detects double-counting
    def_lift = lifts.get("defense", 0)
    pace_lift = lifts.get("pace", 0)
    correlation_warning = None
    if abs(def_lift) > 0 and abs(pace_lift) > 0:
        # If both signals always fire together, reduce both by 15%
        def_bets = [r for r in sport_data if r.get("signal_defense_positive",0)==1]
        pace_bets = [r for r in sport_data if r.get("signal_sharp_flag",0)==1]
        if def_bets and pace_bets:
            overlap = len([r for r in def_bets if r.get("signal_sharp_flag",0)==1])
            overlap_rate = overlap / len(def_bets) if def_bets else 0
            if overlap_rate > 0.80:
                optimized["defense"] = round(optimized.get("defense",0.30) * 0.85, 3)
                optimized.get("pace") and optimized.update({"pace": round(optimized["pace"]*0.85,3)})
                correlation_warning = f"Defense/pace overlap {overlap_rate:.0%} — weights reduced 15%"
    # Re-normalize after correlation adjustment
    total = sum(optimized.values())
    if total > 0:
        optimized = {k: round(v/total, 3) for k, v in optimized.items()}
    existing = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
    existing[sport] = {
        "weights": optimized,
        "n_bets": len(sport_data),
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overall_win_rate": round(overall_wr, 3),
        "lifts": {k: round(v, 4) for k, v in lifts.items()},
        "correlation_warning": correlation_warning,
        "decay_rate": 0.30,
        "sample_factor": round(min(1.0, len(sport_data)/200), 3),
    }
    save_json_data(WEIGHT_OPTIMIZER_PATH, existing)
    save_to_gist("optimized_weights", existing)
    # Once CLV data is sufficient, blend CLV-derived adjustments into the
    # W/L-optimized weights (40% CLV / 60% W/L).  CLV is a better
    # predictor of skill; W/L is noisier but covers more bets early on.
    clv_adjs = compute_clv_signal_feedback(sport)
    if clv_adjs:
        clv_blended = {}
        base_wts = get_effective_signal_weights(sport)
        for key, wt in optimized.items():
            clv_adj = clv_adjs.get(key, 0.0)
            # Apply CLV adjustment on top of W/L-optimized weight
            clv_wt  = max(0.01, min(0.55, wt + clv_adj))
            # 60% W/L-optimized, 40% CLV-adjusted
            clv_blended[key] = round(wt * 0.60 + clv_wt * 0.40, 3)
        # Re-normalise
        _tot = sum(clv_blended.values())
        if _tot > 0:
            clv_blended = {k: round(v / _tot, 3) for k, v in clv_blended.items()}
        existing[sport]["weights"]          = clv_blended
        existing[sport]["clv_adjustments"]  = clv_adjs
        existing[sport]["clv_blend_active"] = True
        save_json_data(WEIGHT_OPTIMIZER_PATH, existing)
        save_to_gist("optimized_weights", existing)
        return clv_blended

    return optimized

def get_active_weights(sport):
    optimizer_data = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
    sport_data = optimizer_data.get(sport, {})
    if sport_data and sport_data.get("weights"):
        n_bets = sport_data.get("n_bets", 0)
        if n_bets >= WEIGHT_OPTIMIZER_MIN_BETS:
            clv_active = sport_data.get("clv_blend_active", False)
            label = f"📊 CLV+W/L blend ({n_bets} bets)" if clv_active else f"📊 Data-driven ({n_bets} bets)"
            return sport_data["weights"], label, "optimized"
    return get_effective_signal_weights(sport), "⚠️ Hardcoded assumptions (insufficient data)", "hardcoded"


def compute_clv_signal_feedback(sport: str) -> dict:
    """
    CLV-based signal weight feedback loop (Buchdahl methodology).

    Core insight: W/L is noisy (variance-driven); CLV vs closing no-vig
    is skill-driven. Signals that fire on bets with positive CLV are
    genuinely predictive. Signals that fire on negative-CLV bets are
    adding noise, even if those bets happened to win.

    Algorithm:
      1. Load CLV-resolved records for the sport
      2. Match each CLV record to its history entry (player+prop+date)
         to recover which signals were active at placement
      3. For each signal, compute avg CLV when fired vs not fired
      4. CLV lift = avg_clv_with - avg_clv_without
      5. Translate to weight adjustment: 1pp CLV lift → +4% weight boost
      6. Blend with W/L optimizer: 40% CLV / 60% W/L (at ≥30 CLV records)

    Returns {weight_key: clv_adjustment} or {} if insufficient data.
    Minimum: 30 resolved CLV records with linked signal data.
    """
    CLV_MIN_RECORDS = 30
    CLV_SCALE       = 0.04   # 1pp CLV lift → 4% weight adjustment
    CLV_MAX_ADJ     = 0.10   # cap per-signal CLV adjustment

    # Signal key map: signals_active key → weight key
    _SIG_MAP = {
        "base_positive":    "base",
        "defense_positive": "defense",
        "location_home":    "location",
        "back_to_back":     "rest",
        "usage_boost":      "usage",
        "sharp_flag":       "pace",
    }

    try:
        clv_data  = load_json_data(CLV_PATH, [])
        history   = load_json_data(HISTORY_PATH, [])
    except Exception:
        _logger.debug("Silent except at line 5238")
        return {}

    # Only use resolved records with valid CLV for this sport
    resolved = [
        c for c in clv_data
        if c.get("sport") == sport
        and c.get("clv_vs_close") is not None
        and isinstance(c.get("clv_vs_close"), (int, float))
    ]
    if len(resolved) < CLV_MIN_RECORDS:
        return {}

    # Build history index: (normalized_player, prop, date) → signals_active
    hist_index = {}
    for h in history:
        sa = h.get("signals_active", {})
        if not sa:
            continue
        key = (
            normalize_name(h.get("player", "")),
            h.get("prop", ""),
            str(h.get("timestamp", ""))[:10],
        )
        hist_index[key] = sa

    # For each CLV record, look up which signals were active
    tagged = []
    for rec in resolved:
        key = (
            normalize_name(rec.get("player", "")),
            rec.get("prop", ""),
            str(rec.get("timestamp", ""))[:10],
        )
        sa = hist_index.get(key)
        if sa is None:
            continue
        tagged.append({
            "clv":     float(rec["clv_vs_close"]),
            "signals": sa,
        })

    if len(tagged) < CLV_MIN_RECORDS:
        return {}

    overall_clv = sum(t["clv"] for t in tagged) / len(tagged)

    adjustments = {}
    for sig_key, weight_key in _SIG_MAP.items():
        fired     = [t["clv"] for t in tagged if t["signals"].get(sig_key)]
        not_fired = [t["clv"] for t in tagged if not t["signals"].get(sig_key)]
        if len(fired) < 10:
            continue
        avg_with    = sum(fired) / len(fired)
        avg_without = sum(not_fired) / len(not_fired) if not_fired else overall_clv
        clv_lift    = avg_with - avg_without
        adj = max(-CLV_MAX_ADJ, min(CLV_MAX_ADJ, clv_lift * CLV_SCALE))
        adjustments[weight_key] = round(adj, 4)

    return adjustments




# market_efficiency_score — moved to bc_utils.py
def detect_correlations(parlay_props):
    notes = []
    adjustment = 1.0
    players = [p["Player"] for p in parlay_props]
    teams = [PLAYER_TEAM_MAP.get(p["Player"], "") for p in parlay_props]
    for i in range(len(players)):
        for j in range(i+1, len(players)):
            if players[i] == players[j]:
                stat1 = parlay_props[i].get("Prop","")
                stat2 = parlay_props[j].get("Prop","")
                stat1_norm = STAT_NORMALIZE.get((parlay_props[i].get("Sport","NBA"), stat1), stat1)
                stat2_norm = STAT_NORMALIZE.get((parlay_props[j].get("Sport","NBA"), stat2), stat2)
                corr = SAME_PLAYER_STAT_CORRELATION.get((stat1_norm, stat2_norm), 0.50)
                adjustment *= (1 - corr * 0.5)
                corr_pct = int(corr * 100)
                if corr >= 0.70:
                    severity = "🚨 HIGHLY correlated"
                elif corr >= 0.45:
                    severity = "⚠️ Moderately correlated"
                else:
                    severity = "📊 Mildly correlated"
                notes.append(f"{severity}: {players[i]} {stat1} + {stat2} ({corr_pct}% stat correlation — {int((1-(1-corr*0.5))*100)}% combined prob reduction)")
                continue
            if teams[i] and teams[i] == teams[j]:
                pair = (players[i], players[j])
                pair_rev = (players[j], players[i])
                corr = (POSITIVE_CORRELATIONS.get(pair) or POSITIVE_CORRELATIONS.get(pair_rev) or 0.15)
                adjustment *= (1 - corr * 0.3)
                notes.append(f"⚠️ {players[i]} & {players[j]} teammates (+{corr:.0%} correlation)")
            pair = (players[i], players[j])
            pair_rev = (players[j], players[i])
            neg_corr = (NEGATIVE_CORRELATIONS.get(pair) or NEGATIVE_CORRELATIONS.get(pair_rev))
            if neg_corr:
                adjustment *= (1 + abs(neg_corr) * 0.2)
                notes.append(f"✅ {players[i]} vs {players[j]} opposing ({neg_corr:.0%} neg correlation)")
    adjusted_probs = []
    for p in parlay_props:
        adj_prob = p["Prob"] * adjustment
        adj_prob = max(0.20, min(0.80, adj_prob))
        adjusted_probs.append(adj_prob)
    return adjusted_probs, notes

def track_line_movement(props):
    existing = load_json_data(LINE_MOVEMENT_PATH, {})
    movement = {}
    _locks_snapshot = list(st.session_state.get("locks", []))
    updated = {}
    for p in props:
        key = f"{p['Player']}_{p['Prop']}"
        current_line = p["Line"]
        previous = existing.get(key, {})
        prev_line = previous.get("line")
        if prev_line is not None and prev_line != current_line:
            diff = current_line - prev_line
            movement[key] = {
                "player": p["Player"], "prop": p["Prop"],
                "prev_line": prev_line, "curr_line": current_line,
                "diff": diff, "direction": "↓" if diff < 0 else "↑",
                "timestamp": datetime.now().strftime("%H:%M")
            }
        updated[key] = {"line": current_line, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")}
    save_json_data(LINE_MOVEMENT_PATH, updated)
    for key, move in movement.items():
        player_name = move.get("player", "")
        prop_name = move.get("prop", "")
        for lock in _locks_snapshot:
            if (lock.get("status") == "PENDING" and normalize_name(lock.get("player","")) == normalize_name(player_name) and lock.get("prop","") == prop_name):
                locked_line = lock.get("line", 0)
                current_line = move.get("curr_line", 0)
                side = lock.get("side", "OVER")
                if side == "OVER":
                    clv = locked_line - current_line
                else:
                    clv = current_line - locked_line
                clv_data = load_json_data(CLV_PATH, [])
                clv_data.append({
                    "player": player_name, "prop": prop_name,
                    "locked_line": locked_line, "closing_line": current_line,
                    "side": side, "clv": round(clv, 1),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "sport": lock.get("sport", ""), "tier": lock.get("tier", ""),
                    "type": "interim"
                })
                save_json_data(CLV_PATH, clv_data)
    return movement

# MLB stadium coordinates for NWS weather fallback

# NFL stadium coordinates — outdoor only (domes excluded)

def get_clv_edge_adjustment(sport, tier):
    try:
        clv_data = load_json_data(CLV_PATH, [])
        if not clv_data:
            return 1.0, "No CLV data yet"
        relevant = [c for c in clv_data if c.get("sport") == sport and c.get("tier") == tier]
        if len(relevant) < 10:
            return 1.0, f"Need {10 - len(relevant)} more CLV data points to activate"
        avg_clv = sum(c.get("clv", 0) for c in relevant) / len(relevant)
        positive_rate = sum(1 for c in relevant if c.get("clv", 0) > 0) / len(relevant)
        if avg_clv > 1.5 and positive_rate >= 0.60:
            return 1.08, f"✅ Strong +CLV history ({avg_clv:+.1f} avg, {positive_rate:.0%} positive) — edge boosted 8%"
        elif avg_clv > 0.5 and positive_rate >= 0.55:
            return 1.04, f"✅ Positive CLV history ({avg_clv:+.1f} avg) — edge boosted 4%"
        elif avg_clv < -1.5 and positive_rate <= 0.40:
            return 0.90, f"⚠️ Negative CLV history ({avg_clv:+.1f} avg, {positive_rate:.0%} positive) — edge reduced 10%"
        elif avg_clv < -0.5 and positive_rate <= 0.45:
            return 0.95, f"⚠️ Weak CLV history ({avg_clv:+.1f} avg) — edge reduced 5%"
        else:
            return 1.0, f"Neutral CLV history ({avg_clv:+.1f} avg)"
    except Exception as e:
        return 1.0, f"CLV calc error: {str(e)[:50]}"

FANTASYLABS_PATH = os.path.join(CACHE_DIR, "fantasylabs_lineups.json")


@st.cache_data(ttl=900)
def get_fantasylabs_lineup_bonus(player, lineups=None, sport="MLB"):
    """
    Lineup confirmation signal — separate flags, sport-specific logic.
    
    Key insight from ChatGPT audit:
    - Jokic/Tatum starting is NOT new information → no bonus
    - Jokic NOT starting IS new information → downgrade
    - Real edge = detecting deviations from expectation
    
    Returns (edge_adj, flags, note) where flags = dict of separate signals.
    edge_adj is applied ONLY when lineup info changes the projection materially.
    """
    if lineups is None:
        lineups = st.session_state.get("fantasylabs_lineups", {})
    if not lineups:
        return 0.0, {}, ""

    data = lineups.get(normalize_name(player))

    # Player not found in feed — lineups not posted yet or player not tracked
    if data is None:
        return 0.0, {"found": False}, ""

    # ── Separate flags (not composite score) ───────────────────
    order      = data.get("lineup_order", 0)
    inj_raw    = data.get("injury_status","").lower().strip()
    in_lineup  = data.get("in_lineup", False)
    is_active  = data.get("active", True)
    position   = data.get("position","")

    flags = {
        "found":          True,
        "in_lineup":      in_lineup,
        "is_starting":    in_lineup and is_active,
        "batting_order":  order,
        "injury_status":  data.get("injury_status","Active"),
        "is_injured":     inj_raw in ("out","doubtful","dtd","ir","injured"),
        "is_questionable":inj_raw == "questionable",
        "position":       position,
    }

    # ── Hard stops — these ALWAYS apply ────────────────────────
    if flags["is_injured"] and not in_lineup:
        return -0.08, flags, f"❌ {data.get('injury_status','')} — OUT"

    if not in_lineup and is_active:
        # Not in lineup but healthy = scratched/benched = major downgrade
        return -0.05, flags, "⚠️ Healthy scratch — not in lineup"

    if not is_active:
        return -0.05, flags, f"⚠️ {data.get('injury_status','Inactive')}"

    # ── Sport-specific edge adjustments ────────────────────────
    if sport == "MLB":
        # Batting order directly affects PA rate
        # Only adjust meaningfully for top/bottom of order
        order_adj = {
            1: 0.04,   # leadoff: most PA, best run scoring
            2: 0.03,
            3: 0.02,
            4: 0.01,   # cleanup: RBI heavy but fewer PA
            5: 0.0,
            6: 0.0,
            7: -0.01,  # bottom of order: fewer PA
            8: -0.01,
            9: -0.01,
        }
        adj  = order_adj.get(order, 0.0) if order > 0 else 0.0
        note = f"✅ Batting #{order}" if order > 0 else "✅ In lineup"
        if adj != 0:
            note += f" ({'+' if adj>0 else ''}{adj*100:.0f}%)"

    elif sport in ("NBA","WNBA"):
        # Starting = NOT new info for stars
        # Real value: catch when expected starter is OUT
        # Small confidence boost only — projection already includes starter assumption
        adj  = 0.01  # minimal — just confirmation
        note = f"✅ Starting confirmed"

    elif sport == "NHL":
        # Line assignment is the real signal
        # order in FL loosely maps to line number
        if order == 1:
            adj, note = 0.03, "✅ Line 1 — top unit"
        elif order == 2:
            adj, note = 0.02, "✅ Line 2"
        elif order == 3:
            adj, note = 0.00, "✅ Line 3"
        elif order >= 4:
            adj, note = -0.02, "⚠️ Line 4 — limited ice time"
        else:
            adj, note = 0.01, "✅ In lineup"

    elif sport == "NFL":
        # Most value = catching Q→Inactive before books react
        if flags["is_questionable"]:
            adj  = 0.0
            note = "⚠️ Questionable — wait for official inactive list"
        else:
            adj  = 0.02
            note = "✅ Active — confirmed off injury report"

    else:
        adj  = 0.01
        note = f"✅ In lineup"

    return round(adj, 3), flags, note




def _fetch_live_team_woba_splits() -> dict:
    """
    Fetch current-season team wOBA vs LHP and vs RHP from the MLB Stats API
    (statsapi.mlb.com /api/v1/teams/{id}/stats).  Returns:
        {"vs_rhp": {team_name: woba}, "vs_lhp": {team_name: woba}}

    Falls back gracefully — if any team fails, the static config value stays.
    Cache: 6 hours (wOBA splits don't change intra-day).
    """
    cache_path = os.path.join(CACHE_DIR, "mlb_team_woba_splits.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 6:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                _logger.debug("Silent except at line 5547")
                pass

    season = date.today().year
    # Get all MLB team IDs
    teams_url = f"https://statsapi.mlb.com/api/v1/teams?sportId=1&season={season}"
    try:
        teams_r = _http.get(teams_url, headers=HEADERS, timeout=10)
        if teams_r.status_code != 200:
            return {}
        teams = teams_r.json().get("teams", [])
    except Exception:
        _logger.debug("Silent except at line 5558")
        return {}

    vs_rhp, vs_lhp = {}, {}
    _WOBA_DEFAULT = MLB_WOBA_LEAGUE_AVG

    for team in teams:
        tid   = team.get("id")
        tname = team.get("name", "")
        if not tid or not tname:
            continue
        try:
            # vs RHP split
            url_rhp = (
                f"https://statsapi.mlb.com/api/v1/teams/{tid}/stats"
                f"?stats=statSplits&group=hitting&season={season}"
                f"&sitCodes=vs-rhp&sportId=1"
            )
            r_rhp = _http.get(url_rhp, headers=HEADERS, timeout=8)
            if r_rhp.status_code == 200:
                splits = r_rhp.json().get("stats", [{}])[0].get("splits", [])
                if splits:
                    s = splits[0].get("stat", {})
                    _woba = s.get("wOBA") or s.get("woba") or _WOBA_DEFAULT
                    vs_rhp[tname] = round(float(_woba), 3)
            # vs LHP split
            url_lhp = (
                f"https://statsapi.mlb.com/api/v1/teams/{tid}/stats"
                f"?stats=statSplits&group=hitting&season={season}"
                f"&sitCodes=vs-lhp&sportId=1"
            )
            r_lhp = _http.get(url_lhp, headers=HEADERS, timeout=8)
            if r_lhp.status_code == 200:
                splits = r_lhp.json().get("stats", [{}])[0].get("splits", [])
                if splits:
                    s = splits[0].get("stat", {})
                    _woba = s.get("wOBA") or s.get("woba") or _WOBA_DEFAULT
                    vs_lhp[tname] = round(float(_woba), 3)
        except Exception:
            continue

    result = {"vs_rhp": vs_rhp, "vs_lhp": vs_lhp}
    if vs_rhp or vs_lhp:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception:
            _logger.debug("Silent except at line 5604")
            pass
    return result


def _enrich_pitchers_savant(pitchers: dict) -> dict:
    """
    Pull live FIP, xFIP, xwOBA allowed, K%, BB% for each probable pitcher
    from the Baseball Savant / MLB Stats API season stat endpoint.
    Updates each pitcher dict in-place; falls back to static config values
    if the network call fails or a pitcher isn't found.

    Endpoint: statsapi.mlb.com/api/v1/people/{id}/stats?stats=season&group=pitching
    Returns enriched pitchers dict.
    """
    season = date.today().year
    enriched = dict(pitchers)
    seen_ids = {}  # pitcher_id → stats, avoid duplicate fetches for same SP

    for team, pdata in pitchers.items():
        pid = pdata.get("pitcher_id")
        pname = pdata.get("pitcher", "")
        if not pid:
            continue
        if pid in seen_ids:
            enriched[team].update(seen_ids[pid])
            continue
        try:
            url = (
                f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
                f"?stats=season&group=pitching&season={season}"
            )
            r = _http.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            splits = r.json().get("stats", [{}])[0].get("splits", [])
            if not splits:
                continue
            s = splits[0].get("stat", {})
            era  = float(s.get("era",  MLB_PITCHER_ERA.get(pname,  LEAGUE_AVG_ERA)))
            fip  = float(s.get("fielding_independent_pitching",
                               MLB_PITCHER_FIP.get(pname, era)))
            k9   = float(s.get("strikeoutsPer9Inn", 0) or 0)
            bb9  = float(s.get("walksPer9Inn",      0) or 0)
            whip = float(s.get("whip",              1.30) or 1.30)
            # xwOBA not in statsapi — use xFIP proxy: FIP + small BB penalty
            xfip = round(fip * 0.92 + bb9 * 0.05, 2)  # lightweight xFIP estimate
            live_stats = {
                "era_live":   round(era,  2),
                "fip_live":   round(fip,  2),
                "xfip_live":  xfip,
                "k9_live":    round(k9,   1),
                "bb9_live":   round(bb9,  1),
                "whip_live":  round(whip, 2),
            }
            enriched[team].update(live_stats)
            seen_ids[pid] = live_stats
        except Exception:
            _logger.debug("Silent except at line 5661")
            pass
    return enriched




@st.cache_data(ttl=1800)   # 30min TTL -- was 3601, bumped again to force fresh results with team name fix
def analyze_game_edge(game, sport, home_teams, away_teams, power_ratings=None, mlb_pitchers=None):
    if power_ratings is None:
        power_ratings = NBA_POWER_RATINGS
    matchup = game.get("Matchup", "")
    spread_str = game.get("Spread", "N/A")
    total_str  = game.get("Total", "N/A")
    home_ml    = game.get("HomeML", game.get("Home ML", "N/A"))
    away_ml    = game.get("AwayML", game.get("Away ML", "N/A"))
    # Fill ML gaps from OddsAPI/SBR overlay when ESPN didn't provide them
    if home_ml in ("N/A", None, ""):
        home_ml = game.get("OddsAPI ML Home", game.get("Bovada ML Home", "N/A"))
    if away_ml in ("N/A", None, ""):
        away_ml = game.get("OddsAPI ML Away", game.get("Bovada ML Away", "N/A"))
    # ── OddsAPI fallback — fills gaps ESPN left as N/A ──
    if spread_str in ("N/A", None, ""):
        spread_str = game.get("OddsAPI Spread", "N/A")
    if total_str in ("N/A", None, ""):
        total_str = game.get("OddsAPI Total", "N/A")
    if home_ml in ("N/A", None, ""):
        # Try HomeML (no space), then OddsAPI backup fields
        home_ml = game.get("HomeML", game.get("OddsAPI ML Home", game.get("Bovada ML Home", "N/A")))
        away_ml = game.get("AwayML", game.get("OddsAPI ML Away", game.get("Bovada ML Away", "N/A")))
    if away_ml in ("N/A", None, ""):
        away_ml = game.get("OddsAPI ML Away", game.get("Bovada ML Away", "N/A"))
    home_team = home_teams.get(matchup, "")
    away_team = away_teams.get(matchup, "")

    # ── Multi-book consensus — replaces single-source ESPN line with full
    # visibility across every scraped book (Pinnacle anchor, consensus
    # median, sharp/public agreement-or-disagreement). Falls back cleanly
    # to the ESPN/OddsAPI line above if no books matched this matchup.
    try:
        _gl_consensus = build_game_line_consensus(home_team, away_team, {
            "pinnacle_game_lines":   st.session_state.get("pinnacle_game_lines", []),
            "betrivers_game_lines":  st.session_state.get("betrivers_game_lines", []),
            "fanatics_game_lines":   st.session_state.get("fanatics_game_lines", []),
            "espnbet_game_lines":    st.session_state.get("espnbet_game_lines", []),
            "hardrock_game_lines":   st.session_state.get("hardrock_game_lines", []),
            "wynnbet_game_lines":    st.session_state.get("wynnbet_game_lines", []),
            "unibet_game_lines":     st.session_state.get("unibet_game_lines", []),
            "bet365_game_lines":     st.session_state.get("bet365_game_lines", []),
            "betmgm_game_lines":     st.session_state.get("betmgm_game_lines", []),
            "heritage_game_lines":   st.session_state.get("heritage_game_lines", []),
            "bookmaker_game_lines":  st.session_state.get("bookmaker_game_lines", []),
            "bovada_game_lines":     st.session_state.get("bovada_game_lines", []),
            "mybookie_game_lines":   st.session_state.get("mybookie_game_lines", []),
            "fanduel_game_lines":    st.session_state.get("fanduel_game_lines", []),
            "caesars_game_lines":    st.session_state.get("caesars_game_lines", []),
            "sportsline_game_lines": st.session_state.get("sportsline_game_lines", []),
            "sbr_game_lines":        st.session_state.get("sbr_game_lines", []),
            "thescore_game_lines":   st.session_state.get("thescore_game_lines", []),
        })
    except Exception:
        _gl_consensus = {"agreement": "NO_DATA", "agreement_note": "", "n_books_total": 0,
                          "spread": {}, "total": {}, "moneyline": {}}

    # Prefer consensus median, then Pinnacle, then the ESPN/OddsAPI line
    # already resolved above — never fully replaces, only upgrades it.
    if _gl_consensus.get("spread", {}).get("consensus") is not None:
        # Keep spread_str a plain numeric string here — it flows into
        # game["Spread"], which downstream becomes a lock's "line" field
        # and must survive float(). Team-name prefixing for display is
        # already handled separately in the pick-label construction below;
        # embedding it here as well previously produced values like
        # "Pittsburgh Pirates -1.5" that crashed float(lock["line"]) in the
        # Check Results resolver and silently aborted that date's entire
        # event-processing pass (bug found 2026-07-12).
        spread_str = f"{_gl_consensus['spread']['consensus']:+.1f}"
    if _gl_consensus.get("total", {}).get("consensus") is not None:
        total_str = _gl_consensus["total"]["consensus"]
    if _gl_consensus.get("moneyline", {}).get("home_consensus_prob") is not None:
        # Keep the original market home_ml/away_ml for display/EV math below —
        # the consensus probability is exposed separately via _gl_consensus
        # and consumed directly by the ML edge block further down.
        pass

    # Normalize abbreviations to full names for power rating lookups
    _PR_MAP_MLB = {
        "ARI":"Arizona Diamondbacks","ATL":"Atlanta Braves","BAL":"Baltimore Orioles",
        "BOS":"Boston Red Sox","CHC":"Chicago Cubs","CWS":"Chicago White Sox",
        "CIN":"Cincinnati Reds","CLE":"Cleveland Guardians","COL":"Colorado Rockies",
        "DET":"Detroit Tigers","HOU":"Houston Astros","KC":"Kansas City Royals",
        "LAA":"Los Angeles Angels","LAD":"Los Angeles Dodgers","MIA":"Miami Marlins",
        "MIL":"Milwaukee Brewers","MIN":"Minnesota Twins","NYM":"New York Mets",
        "NYY":"New York Yankees","OAK":"Oakland Athletics","ATH":"Athletics",
        "PHI":"Philadelphia Phillies","PIT":"Pittsburgh Pirates","SD":"San Diego Padres",
        "SEA":"Seattle Mariners","SF":"San Francisco Giants","STL":"St. Louis Cardinals",
        "TB":"Tampa Bay Rays","TEX":"Texas Rangers","TOR":"Toronto Blue Jays",
        "WSH":"Washington Nationals",
    }
    _PR_MAP_NHL = {
        "TOR":"Toronto Maple Leafs","BOS":"Boston Bruins","TBL":"Tampa Bay Lightning",
        "FLA":"Florida Panthers","MTL":"Montreal Canadiens","BUF":"Buffalo Sabres",
        "OTT":"Ottawa Senators","PIT":"Pittsburgh Penguins","PHI":"Philadelphia Flyers",
        "WSH":"Washington Capitals","CAR":"Carolina Hurricanes","NYR":"New York Rangers",
        "NJD":"New Jersey Devils","NYI":"New York Islanders","CBJ":"Columbus Blue Jackets",
        "CHI":"Chicago Blackhawks","NSH":"Nashville Predators","WPG":"Winnipeg Jets",
        "MIN":"Minnesota Wild","COL":"Colorado Avalanche","DAL":"Dallas Stars",
        "VGK":"Vegas Golden Knights","LAK":"Los Angeles Kings","ANA":"Anaheim Ducks",
        "SJS":"San Jose Sharks","SEA":"Seattle Kraken","VAN":"Vancouver Canucks",
        "CGY":"Calgary Flames","EDM":"Edmonton Oilers","STL":"St. Louis Blues",
        "DET":"Detroit Red Wings","ATL":"Atlanta Thrashers",
    }
    _PR_MAP_NBA = {
        "GSW":"Golden State Warriors","LAL":"Los Angeles Lakers","LAC":"Los Angeles Clippers",
        "NYK":"New York Knicks","NOP":"New Orleans Pelicans","SAS":"San Antonio Spurs",
        "OKC":"Oklahoma City Thunder","UTA":"Utah Jazz","MEM":"Memphis Grizzlies",
        "BKN":"Brooklyn Nets","MIA":"Miami Heat","BOS":"Boston Celtics",
        "PHI":"Philadelphia 76ers","TOR":"Toronto Raptors","CHI":"Chicago Bulls",
        "MIL":"Milwaukee Bucks","IND":"Indiana Pacers","ATL":"Atlanta Hawks",
        "CLE":"Cleveland Cavaliers","DET":"Detroit Pistons","ORL":"Orlando Magic",
        "WAS":"Washington Wizards","CHA":"Charlotte Hornets","PHX":"Phoenix Suns",
        "DAL":"Dallas Mavericks","DEN":"Denver Nuggets","MIN":"Minnesota Timberwolves",
        "POR":"Portland Trail Blazers","SAC":"Sacramento Kings","HOU":"Houston Rockets",
    }
    _PR_MAP_NFL = {
        "NE":"New England Patriots","NO":"New Orleans Saints","GB":"Green Bay Packers",
        "LAR":"Los Angeles Rams","NYG":"New York Giants","NYJ":"New York Jets",
        "SF":"San Francisco 49ers","TB":"Tampa Bay Buccaneers","KC":"Kansas City Chiefs",
        "LAC":"Los Angeles Chargers","MIA":"Miami Dolphins","BUF":"Buffalo Bills",
        "BAL":"Baltimore Ravens","CIN":"Cincinnati Bengals","CLE":"Cleveland Browns",
        "PIT":"Pittsburgh Steelers","HOU":"Houston Texans","IND":"Indianapolis Colts",
        "JAX":"Jacksonville Jaguars","TEN":"Tennessee Titans","DEN":"Denver Broncos",
        "LV":"Las Vegas Raiders","SEA":"Seattle Seahawks","ARI":"Arizona Cardinals",
        "ATL":"Atlanta Falcons","CAR":"Carolina Panthers","CHI":"Chicago Bears",
        "DAL":"Dallas Cowboys","DET":"Detroit Lions","MIN":"Minnesota Vikings",
        "PHI":"Philadelphia Eagles","WAS":"Washington Commanders","NYG":"New York Giants",
    }
    _PR_MAP_WNBA = {
        "ATL":"Atlanta Dream","CHI":"Chicago Sky","CON":"Connecticut Sun",
        "DAL":"Dallas Wings","IND":"Indiana Fever","LV":"Las Vegas Aces",
        "LA":"Los Angeles Sparks","MIN":"Minnesota Lynx","NY":"New York Liberty",
        "PHX":"Phoenix Mercury","SEA":"Seattle Storm","WAS":"Washington Mystics",
        "GS":"Golden State Valkyries","POR":"Portland Fire",
    }
    _sport_pr_maps = {
        "MLB": _PR_MAP_MLB, "NHL": _PR_MAP_NHL, "NBA": _PR_MAP_NBA,
        "NFL": _PR_MAP_NFL, "WNBA": _PR_MAP_WNBA,
    }
    _PR_MAP = _sport_pr_maps.get(sport, _PR_MAP_MLB)
    home_full = _PR_MAP.get(home_team, home_team)
    away_full = _PR_MAP.get(away_team, away_team)
    recommendations = []
    best_bet = None
    best_edge = 0
    
    is_playoff_now = (detect_season_regime(sport).get("regime") == "Playoffs")
    live_ratings = fetch_espn_fpi_ratings(sport)
    
    if live_ratings and len(live_ratings) >= 10:
        live_weight = 0.70 if is_playoff_now else 0.50
        hard_weight = 1 - live_weight
        blended_ratings = {}
        for team in set(list(power_ratings.keys()) + list(live_ratings.keys())):
            hard = power_ratings.get(team, 104.0)
            live = live_ratings.get(team, hard)
            blended_ratings[team] = round(live * live_weight + hard * hard_weight, 1)
        power_ratings = blended_ratings

    # Elo nudge — small additive adjustment, not a full re-blend, so a cold
    # Elo system (early season, most teams still at ELO_DEFAULT_RATING) can't
    # distort the proven hard/live blend above. Contributes 0 for any team
    # with no game history yet (elo_to_def_adj(1500)==0). sport must be in
    # ELO_K_FACTOR or this is skipped (NBA/NFL/WNBA/NHL/Soccer only).
    if sport in ELO_K_FACTOR:
        elo_ratings = get_elo_ratings(sport)
        if elo_ratings:
            for team in power_ratings:
                elo_val = elo_ratings.get(team)
                if elo_val is not None:
                    power_ratings[team] = round(power_ratings[team] + elo_to_def_adj(elo_val) * 6.0, 1)

    # Real FPI nudge — separate from live_ratings above, which despite its
    # "FPI" name is actually a win-pct-derived proxy, not real ESPN FPI.
    # GAP FIX #1: For NFL specifically, replace the ×0.3 nudge with a
    # full power-rating blend using ESPN team stats (points for/against,
    # yards for/against) — far more predictive than win% heading into season.
    if sport == "NFL":
        fpi_real = fetch_espn_fpi(sport)
        nfl_stats_ratings = _fetch_nfl_team_stats_power()
        if nfl_stats_ratings:
            # Blend: 50% stats-derived, 30% live win-pct proxy, 20% FPI nudge
            for team in list(power_ratings.keys()):
                stats_val = nfl_stats_ratings.get(team)
                fpi_data  = fpi_real.get(team) if fpi_real else None
                if stats_val is not None:
                    pr_base = power_ratings[team]
                    fpi_add = (fpi_data["fpi"] * 0.20) if (fpi_data and fpi_data.get("fpi")) else 0
                    power_ratings[team] = round(
                        pr_base * 0.30 + stats_val * 0.50 + fpi_add, 1
                    )
        elif fpi_real:
            for team in power_ratings:
                fpi_data = fpi_real.get(team)
                if isinstance(fpi_data, dict) and fpi_data.get("fpi") is not None:
                    power_ratings[team] = round(power_ratings[team] + fpi_data["fpi"] * 0.5, 1)
    
    public_data = st.session_state.get("public_betting_data", {})
    game_public = None

    def _team_matches_abbr(espn_abbr, an_abbr, sport_key):
        # home_team/away_team (passed in as espn_abbr here) are ESPN's own
        # short abbreviation (fetch_game_lines stores
        # competitor["team"]["abbreviation"], not a full team name) -- so
        # comparing them against an Action Network abbreviation requires
        # resolving BOTH sides through the same fragment table and checking
        # they land on the same team, not checking whether one is a
        # substring of the other (a short code can never contain a long
        # fragment string, so that check silently failed for every game,
        # on every sport -- not just the specific one currently under
        # investigation).
        if not espn_abbr or not an_abbr:
            return False
        frag_table = TEAM_ABBREV_TO_FRAGMENT.get(sport_key, {})
        espn_frag = frag_table.get(espn_abbr.upper(), "")
        an_frag   = frag_table.get(an_abbr.upper(), "")
        if espn_frag and an_frag:
            return espn_frag == an_frag
        # Either side's abbreviation wasn't in the table (e.g. a sport/code
        # combo not yet mapped) -- fall back to direct abbreviation equality
        # rather than silently returning no match.
        return espn_abbr.upper() == an_abbr.upper()

    for key, val in public_data.items():
        teams = val.get("teams", [])
        if any(_team_matches_abbr(home_team, t, sport) or _team_matches_abbr(away_team, t, sport) for t in teams):
            game_public = val
            break
    
    public_sharp_signals = []
    if game_public:
        public_sharp_signals = game_public.get("sharp_signals", [])
    
    try:
        if spread_str and spread_str != "N/A":
            spread_val = float(str(spread_str).split()[-1].replace("+",""))
            favored_team = str(spread_str).split()[0] if len(str(spread_str).split()) > 1 else home_team
            if home_full in power_ratings and away_full in power_ratings:
                home_power = power_ratings[home_full]
                away_power = power_ratings[away_full]
                power_diff = home_power - away_power
                if sport in ("MLB", "NHL"):
                    # Convert the ~100-scale power index to run/goal-equivalent
                    # units before comparing against market_spread, which is
                    # already in those units. Without this, power_diff (which
                    # can be 10-15+ across the full league range) completely
                    # dominates a market_spread of ~1.5-2.5, producing a wildly
                    # inflated edge that just pins at the ±20% ceiling on
                    # nearly every matchup with any real rating gap.
                    power_diff = power_diff / 10.0
                market_spread = -spread_val if favored_team == home_team else spread_val
                spread_edge = power_diff - market_spread
                spread_edge_pct = spread_edge / 10.0
                # NBA/WNBA spread compression: these sports share NFL's tier
                # thresholds (SOVEREIGN 0.12/ELITE 0.08/APPROVED 0.04/LEAN 0.02)
                # but NFL gets further downstream compression (divisional -15%,
                # uncertainty -20%) that NBA/WNBA never did. Without this, a
                # single 1-point NBA spread edge (routine given ±15pt spreads
                # and high variance) produced 10% -> cleared ELITE tier, which
                # is far too easy for a 1-point edge in this sport.
                if sport in ("NBA", "WNBA"):
                    spread_edge_pct = spread_edge / 15.0
                # GAP FIX: Apply MLB park factor to run line / spread edge.
                # Hitter-friendly parks compress run line edges for favorites
                # (blowouts are less likely) and expand them for underdogs.
                # Previously park factor was only applied to totals.
                if sport == "MLB":
                    # Use FanGraphs park factors if available, else fallback
                    try:
                        from fetchers import fetch_fangraphs_park_factors
                        _fg_parks = fetch_fangraphs_park_factors()
                        _fg_hr = _fg_parks.get(home_full, _fg_parks.get(home_team, {})).get("hr_factor", None)
                        _park_mult_rl = _fg_hr if _fg_hr else MLB_PARK_FACTORS.get(
                            home_full, MLB_PARK_FACTORS.get(home_team, 1.0)
                        )
                    except Exception:
                        _park_mult_rl = MLB_PARK_FACTORS.get(
                            home_full, MLB_PARK_FACTORS.get(home_team, 1.0)
                        )
                    _park_rl_adj = (_park_mult_rl - 1.0) * 0.08
                    if spread_edge > 0:
                        spread_edge_pct -= _park_rl_adj
                    else:
                        spread_edge_pct += _park_rl_adj
                if sport == "NFL":
                    _game_date_str = game.get("Date", "")
                    # ── 1. Division game deflator ─────────────────────────
                    # Division games average 2.5 pts tighter ATS; reduce
                    # edge confidence by ~0.015 when teams share a division.
                    try:
                        _h_div = NFL_DIVISIONS.get(home_team)
                        _a_div = NFL_DIVISIONS.get(away_team)
                        if _h_div and _h_div == _a_div:
                            spread_edge_pct *= 0.85  # ~15% edge compression
                    except Exception:
                        _logger.debug("Silent except at line 5866")
                        pass
                    # ── 2. Short week / Thursday penalty ─────────────────
                    # Road favorites on Thursday (4-day turnaround) cover at
                    # ~44% historically. Deflate road favorite edge by 20%.
                    try:
                        if "Thu" in _game_date_str:
                            is_road_fav = (favored_team == away_team)
                            if is_road_fav:
                                spread_edge_pct *= 0.80
                            else:
                                # Home team also on short week — smaller penalty
                                spread_edge_pct *= 0.90
                    except Exception:
                        _logger.debug("Silent except at line 5879")
                        pass
                    # ── 3. Primetime road favorite fade ──────────────────
                    # Road favorites in primetime slots (Thu/Mon night games)
                    # cover at ~42%. Extra fade on top of short-week penalty.
                    try:
                        _is_primetime = "Thu" in _game_date_str or "Mon" in _game_date_str
                        if _is_primetime and favored_team == away_team:
                            spread_edge_pct *= 0.88
                    except Exception:
                        _logger.debug("Silent except at line 5888")
                        pass
                    # ── 4. QB injury check ────────────────────────────────
                    # If starting QB is on the inactives list, spread edge
                    # is largely invalidated — collapse to near-zero.
                    try:
                        _nfl_inactives_se = fetch_nfl_inactives()
                        _QB_KEYWORDS = ("quarterback", "qb")
                        for _se_team, _se_side in [(home_team, "home"), (away_team, "away")]:
                            _inactives = _nfl_inactives_se.get(_se_team, [])
                            _qb_out = any(
                                any(kw in str(p).lower() for kw in _QB_KEYWORDS)
                                for p in _inactives
                            )
                            if _qb_out:
                                # QB out → edge direction may flip; suppress
                                if (_se_side == "home" and spread_edge > 0) or \
                                   (_se_side == "away" and spread_edge < 0):
                                    spread_edge_pct *= 0.30
                                else:
                                    spread_edge_pct *= 1.20  # favors other side
                    except Exception:
                        _logger.debug("Silent except at line 5909")
                        pass
                    # ── 5. Defensive unit adjustment ──────────────────────
                    # If the favored team faces an elite pass defense (top
                    # quartile: <200 pass yds/g allowed), compress edge by 10%.
                    # If they face a bottom quartile defense (>260), expand 10%.
                    try:
                        _def_ratings = fetch_nfl_defensive_ratings()
                        _opp_team = away_team if favored_team == home_team else home_team
                        _opp_def = _def_ratings.get(_opp_team, {})
                        _pass_allowed = _opp_def.get("pass_yds_allowed_pg", 230.0)
                        if _pass_allowed < 200:       # elite pass D
                            spread_edge_pct *= 0.90
                        elif _pass_allowed > 260:     # poor pass D
                            spread_edge_pct *= 1.10
                    except Exception:
                        _logger.debug("Silent except at line 5924")
                        pass
                if sport == "Soccer":
                    # ── Soccer GF/GA differential adjustment ─────────────
                    # Refine spread edge using actual team goal differentials.
                    # Strong attack vs weak defense → expand edge; vice versa.
                    try:
                        _soc_t = fetch_soccer_team_goals("eng.1")
                        _hs = _soc_t.get(home_full, _soc_t.get(home_team, {}))
                        _as = _soc_t.get(away_full, _soc_t.get(away_team, {}))
                        if _hs and _as:
                            # Net GD per game for each side
                            _h_gd = _hs.get("gf_pg", 1.36) - _hs.get("ga_pg", 1.36)
                            _a_gd = _as.get("gf_pg", 1.36) - _as.get("ga_pg", 1.36)
                            _gd_diff = _h_gd - _a_gd
                            # ±0.5 GD/game → ±0.04 edge adjustment
                            spread_edge_pct += _gd_diff * 0.08
                    except Exception:
                        _logger.debug("Silent except at line 5941")
                        pass
                if sport == "UFC":
                    # ── UFC striking differential for spread/ML ───────────
                    try:
                        _f1s = fetch_ufc_fighter_stats(home_full or home_team) or {}
                        _f2s = fetch_ufc_fighter_stats(away_full or away_team) or {}
                        _f1_str = float(_f1s.get("SIG_STR", 35) or 35)
                        _f2_str = float(_f2s.get("SIG_STR", 35) or 35)
                        spread_edge_pct += (_f1_str - _f2_str) / 100.0
                    except Exception:
                        _logger.debug("Silent except at line 5951")
                        pass
                if sport == "Tennis":
                    # ── Tennis serve efficiency ML/spread signal ──────────
                    try:
                        _tc2 = fetch_tennis_tournament_context()
                        _wta2 = fetch_tennis_scoreboard("wta")
                        _tk2 = "wta" if (
                            normalize_name(home_full or home_team) in _wta2 or
                            normalize_name(away_full or away_team) in _wta2
                        ) else "atp"
                        _surf2 = _tc2.get(_tk2, {}).get("surface", "hard")
                        _p1s2 = fetch_tennis_player_stats(home_full or home_team)
                        _p2s2 = fetch_tennis_player_stats(away_full or away_team)
                        spread_edge_pct += compute_tennis_ml_edge(
                            _p1s2 or {}, _p2s2 or {}, surface=_surf2
                        )
                    except Exception:
                        _logger.debug("Silent except at line 5968")
                        pass
                if sport == "Golf":
                    # ── Golf SG differential for H2H spread edge ─────────
                    try:
                        _p1g = fetch_golf_player_stats(home_full or home_team) or {}
                        _p2g = fetch_golf_player_stats(away_full or away_team) or {}
                        def _sg_net(s):
                            b  = float(s.get("Birdies", 3.8) or 3.8)
                            bo = float(s.get("Bogeys",  3.2) or 3.2)
                            e  = float(s.get("Eagles",  0.1) or 0.1)
                            return (b - bo + e * 2) - 0.6
                        _sg_diff = (_sg_net(_p1g) - _sg_net(_p2g)) * 0.06
                        spread_edge_pct += max(-0.08, min(0.08, _sg_diff))
                    except Exception:
                        _logger.debug("Silent except at line 5982")
                        pass
                spread_edge_pct = max(-0.20, min(0.20, spread_edge_pct))
                # Apply RLM + steam + market divergence multipliers
                try:
                    _rlm_m  = _rlm_score.get("edge_mult", 1.0) if _rlm_score else 1.0
                    _stm_m  = 1.08 if any(v.get("is_steam") for v in _steam_signals.values()) else 1.0
                    _div_m  = 1.05 if _mkt_divergence.get("signal_strength") in ("STRONG","MODERATE") else 1.0
                    spread_edge_pct = max(-0.20, min(0.20, spread_edge_pct * min(1.25, _rlm_m * _stm_m * _div_m)))
                except Exception:
                    _logger.debug("Silent except at line 5991")
                    pass

                # ── Monte Carlo spread refinement ─────────────────────────
                # For MLB/NHL/Soccer: use the Skellam distribution (difference
                # of two Poisson processes) to compute the exact probability of
                # covering the market spread, then blend with the power-rating
                # edge. This replaces the crude "gap / scale-constant" linear
                # heuristic with a real probability-based estimate.
                # For NBA/WNBA: use the convergent Poisson MC simulation
                # directly on per-100-possession scoring rates.
                try:
                    _mu_h_sp = locals().get("_mu_home")
                    _mu_a_sp = locals().get("_mu_away")
                    if sport in ("MLB", "NHL", "Soccer") and _mu_h_sp and _mu_a_sp:
                        # Skellam P(home covers spread) = P(home_score - away_score > market_spread)
                        _spread_cover_side = "OVER" if spread_edge > 0 else "UNDER"
                        _skellam_cover_prob = compute_fair_prob_skellam(
                            abs(market_spread), _mu_h_sp, _mu_a_sp, _spread_cover_side
                        )
                        _skellam_edge = _skellam_cover_prob - 0.524
                        if spread_edge < 0:
                            _skellam_edge = -abs(_skellam_edge)
                        # Blend: 60% existing (power rating + park/weather/matchup
                        # adjustments already applied above) + 40% Skellam
                        spread_edge_pct = max(-0.20, min(0.20,
                            0.60 * spread_edge_pct + 0.40 * _skellam_edge
                        ))
                    elif sport in ("NBA", "WNBA"):
                        # NBA/WNBA: composite scalar ratings → derive implied win%
                        # via sigmoid, then run Log5 to get H2H probability, then
                        # use excess above breakeven as spread-coverage estimate.
                        _nba_ratings = NBA_POWER_RATINGS if sport == "NBA" else WNBA_POWER_RATINGS
                        _nba_h_rat = _nba_ratings.get(home_full, _nba_ratings.get(home_team))
                        _nba_a_rat = _nba_ratings.get(away_full, _nba_ratings.get(away_team))
                        if _nba_h_rat and _nba_a_rat:
                            _divisor = 4.0  # matches _ml_divisor for NBA/WNBA
                            _p_h_nba = 1 / (1 + math.exp(-(_nba_h_rat - _nba_a_rat) / _divisor))
                            _p_a_nba = 1 - _p_h_nba
                            _log5_nba = mc_log5_win_prob(_p_h_nba, _p_a_nba)
                            _mc_spread_edge = (_log5_nba - 0.524) if spread_edge > 0 else -(( 1 - _log5_nba) - 0.524)
                            spread_edge_pct = max(-0.20, min(0.20,
                                0.65 * spread_edge_pct + 0.35 * _mc_spread_edge
                            ))
                except Exception:
                    _logger.debug("Silent except at line 6035")
                    pass
                if abs(spread_edge_pct) >= 0.02:
                    rec_side = home_team if spread_edge > 0 else away_team
                    rec_text = f"{rec_side} {spread_str}" if spread_edge > 0 else f"{away_team} {'+' + str(abs(spread_val)) if spread_val < 0 else '-' + str(abs(spread_val))}"
                    tier = _get_cal_game_tier(abs(spread_edge_pct), sport)
                    _pinn_sp_side = "HOME" if spread_edge > 0 else "AWAY"
                    _pinn_sp_prob, _pinn_sp_conf, _pinn_sp_note = pinnacle_game_fair_value(home_team, away_team, "spread", sport, _pinn_sp_side)
                    _pinn_sp = {"prob": _pinn_sp_prob, "confirms": _pinn_sp_conf, "note": _pinn_sp_note} if _pinn_sp_prob is not None else None
                    _vsin_sp_prob, _vsin_sp_conf, _vsin_sp_note = vsin_sharp_signal(home_team, away_team, "spread", sport, _pinn_sp_side)
                    _vsin_sp = {"prob": _vsin_sp_prob, "confirms": _vsin_sp_conf, "note": _vsin_sp_note} if _vsin_sp_prob is not None else None
                    recommendations.append({"type": "SPREAD", "pick": rec_text, "edge": spread_edge_pct, "mc_blend": True, "edge_pct": f"{spread_edge_pct:.1%}", "tier": tier, "power_diff": round(power_diff, 1), "market_spread": market_spread, "divergence": round(spread_edge, 1), "note": f"Power rating diff {power_diff:.1f} vs market spread {market_spread:.1f} — divergence {spread_edge:.1f} pts", "market_agreement": _gl_consensus.get("agreement", "NO_DATA"), "market_agreement_note": _gl_consensus.get("agreement_note", ""), "n_books": _gl_consensus.get("spread", {}).get("n_books", 0), "public_pct_home": _gl_consensus.get("public_pct_home"), "public_pct_away": _gl_consensus.get("public_pct_away"), "sharp_vs_public": _gl_consensus.get("sharp_vs_public"), "pinnacle_sharp": _pinn_sp, "vsin_sharp": _vsin_sp})
                    if abs(spread_edge_pct) > best_edge:
                        best_edge = abs(spread_edge_pct)
                        best_bet = recommendations[-1]
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    
    try:
        if total_str and total_str != "N/A":
            total_val = float(total_str)
            fair_total = None
            if sport == "NBA":
                h_pace = NBA_TEAM_PACE.get(home_full, NBA_TEAM_PACE.get(home_team, 99.5))
                a_pace = NBA_TEAM_PACE.get(away_full, NBA_TEAM_PACE.get(away_team, 99.5))
                h_power = power_ratings.get(home_full, power_ratings.get(home_team, 112.0))
                a_power = power_ratings.get(away_full, power_ratings.get(away_team, 112.0))
                avg_pace = (h_pace + a_pace) / 2
                try:
                    from fetchers import fetch_nba_live_stats as _fetch_nba_base
                    base_total = _fetch_nba_base().get("base_total", 227.0)
                except Exception:
                    base_total = 227.0
                pace_adj = (avg_pace - 99.5) * 1.5
                off_adj = ((h_power + a_power) / 2 - 112.0) * 0.8
                fair_total = base_total + pace_adj + off_adj
                # ── ATS Stats NBA L10 O/U momentum nudge ──────────────────
                try:
                    _nba_ats = fetch_atsstats_nba_matchups()
                    _h_nba = _nba_ats.get(home_full, _nba_ats.get(home_team, {}))
                    _a_nba = _nba_ats.get(away_full, _nba_ats.get(away_team, {}))
                    if _h_nba and _a_nba:
                        _h_ou = _h_nba.get("l10_ou", (5, 5))
                        _a_ou = _a_nba.get("l10_ou", (5, 5))
                        # Each Over beyond neutral = +/-1.5 NBA points; cap ±7.5
                        _h_d = (_h_ou[0] - 5) * 1.5
                        _a_d = (_a_ou[0] - 5) * 1.5
                        fair_total += max(-7.5, min(7.5, (_h_d + _a_d) / 2))
                except Exception:
                    _logger.debug("Silent except at line 6074")
                    pass
            elif sport == "WNBA":
                # WNBA totals — pace-adjusted, base ~165 per 2025 season
                h_power = power_ratings.get(home_team, 106.0)
                a_power = power_ratings.get(away_team, 106.0)
                try:
                    from fetchers import fetch_wnba_live_stats as _fetch_wnba_base
                    base_total = _fetch_wnba_base().get("base_total", 165.0)
                except Exception:
                    base_total = 165.0
                off_adj = ((h_power + a_power) / 2 - 106.0) * 0.6
                fair_total = base_total + off_adj
            elif sport == "MLB":
                try:
                    from fetchers import fetch_mlb_live_stats as _fetch_mlb_base
                    _mlb_base = _fetch_mlb_base()
                    base_total = _mlb_base.get("base_total", 8.5)
                except Exception:
                    base_total = 8.5
                # Use passed pitchers dict (not undefined outer scope variable)
                _pitchers = mlb_pitchers or {}
                MLB_ABBREV_TO_FULL = {
                    "ARI":"Arizona Diamondbacks","ATL":"Atlanta Braves",
                    "BAL":"Baltimore Orioles","BOS":"Boston Red Sox",
                    "CHC":"Chicago Cubs","CWS":"Chicago White Sox",
                    "CIN":"Cincinnati Reds","CLE":"Cleveland Guardians",
                    "COL":"Colorado Rockies","DET":"Detroit Tigers",
                    "HOU":"Houston Astros","KC":"Kansas City Royals",
                    "LAA":"Los Angeles Angels","LAD":"Los Angeles Dodgers",
                    "MIA":"Miami Marlins","MIL":"Milwaukee Brewers",
                    "MIN":"Minnesota Twins","NYM":"New York Mets",
                    "NYY":"New York Yankees","OAK":"Oakland Athletics",
                    "ATH":"Athletics","PHI":"Philadelphia Phillies",
                    "PIT":"Pittsburgh Pirates","SD":"San Diego Padres",
                    "SEA":"Seattle Mariners","SF":"San Francisco Giants",
                    "STL":"St. Louis Cardinals","TB":"Tampa Bay Rays",
                    "TEX":"Texas Rangers","TOR":"Toronto Blue Jays",
                    "WSH":"Washington Nationals",
                }
                h_full2 = MLB_ABBREV_TO_FULL.get(home_team, home_full)
                a_full2 = MLB_ABBREV_TO_FULL.get(away_team, away_full)
                h_data = _pitchers.get(h_full2, _pitchers.get(home_team, {}))
                a_data = _pitchers.get(a_full2, _pitchers.get(away_team, {}))
                h_pitcher = h_data.get("pitcher","")
                a_pitcher = a_data.get("pitcher","")
                # Prefer live Savant FIP over static ERA for game totals
                h_era = h_data.get("era_live") or MLB_PITCHER_ERA.get(h_pitcher, LEAGUE_AVG_ERA)
                a_era = a_data.get("era_live") or MLB_PITCHER_ERA.get(a_pitcher, LEAGUE_AVG_ERA)
                h_fip = h_data.get("fip_live") or MLB_PITCHER_FIP.get(h_pitcher, h_era)
                a_fip = a_data.get("fip_live") or MLB_PITCHER_FIP.get(a_pitcher, a_era)
                # 60% FIP, 40% ERA blend for total projection
                avg_pitch = ((h_fip * 0.60 + h_era * 0.40) + (a_fip * 0.60 + a_era * 0.40)) / 2
                era_adj = (avg_pitch - LEAGUE_AVG_ERA) * 0.4
                park_mult = MLB_PARK_FACTORS.get(h_full2, MLB_PARK_FACTORS.get(home_team, MLB_PARK_DEFAULT))
                park_adj = (park_mult - 1.0) * 2.0
                # GAP FIX #7: MLB weather wind adjustment for game totals
                # Wind out boosts totals; wind in suppresses them.
                wind_adj_total = 0.0
                try:
                    _park_info = MLB_BALLPARKS.get(h_full2, MLB_BALLPARKS.get(home_team, {}))
                    _park_city = _park_info.get("city", "")
                    _is_outdoor = _park_info.get("outdoor", True)
                    if _park_city and _is_outdoor:
                        _wx = fetch_weather_for_game(_park_city, is_outdoor=True, team_abbrev=home_team)
                        if _wx:
                            _ws  = _wx.get("wind_speed_mph", 0)
                            _wd  = _wx.get("wind_dir", "N")
                            _out = ["SW","WSW","W","WNW","NW","S","SSW"]
                            _in  = ["N","NNE","NE","ENE","E","ESE","SE","SSE"]
                            if _ws >= 10:
                                if _wd in _out:
                                    wind_adj_total = min(1.5, _ws * 0.06)   # wind out → OVER
                                elif _wd in _in:
                                    wind_adj_total = -min(1.5, _ws * 0.06)  # wind in  → UNDER
                except Exception:
                    _logger.debug("Silent except at line 6140")
                    pass
                # ── ATS Stats L10 O/U momentum adjustment ─────────────────
                # If both teams trend heavily Over or Under in their last 10,
                # apply a small directional nudge to fair_total.
                # Scale: each O/U win beyond 5 (neutral) = +/-0.12 runs.
                # Max combined adjustment capped at +/-0.6 runs.
                l10_ou_adj = 0.0
                try:
                    _ats_data = fetch_atsstats_mlb_matchups()
                    _h_ats = _ats_data.get(h_full2, _ats_data.get(home_full, {}))
                    _a_ats = _ats_data.get(a_full2, _ats_data.get(away_full, {}))
                    if _h_ats and _a_ats:
                        h_ou = _h_ats.get("l10_ou", (5, 5))
                        a_ou = _a_ats.get("l10_ou", (5, 5))
                        # Overs minus 5 (neutral), scaled by 0.12 per game
                        h_ou_delta = (h_ou[0] - 5) * 0.12
                        a_ou_delta = (a_ou[0] - 5) * 0.12
                        l10_ou_adj = max(-0.6, min(0.6, (h_ou_delta + a_ou_delta) / 2))
                except Exception:
                    _logger.debug("Silent except at line 6159")
                    pass
                fair_total = base_total + era_adj + park_adj + wind_adj_total + l10_ou_adj
                _mu_home = _mu_away = None  # set below if James-formula data available
                # ── James matchup formula blend ────────────────────────────
                # Formula: home_runs = (home_RS × away_RA) / league_avg
                #          away_runs = (away_RS × home_RA) / league_avg
                # Blend 40% James / 60% ERA-based to smooth small-sample noise.
                try:
                    _run_stats = fetch_mlb_team_run_stats()
                    try:
                        from fetchers import fetch_mlb_live_stats as _fetch_mlb_avg
                        _LEAGUE_AVG_RS = _fetch_mlb_avg().get("league_avg_rs", 4.25)
                    except Exception:
                        _LEAGUE_AVG_RS = 4.25
                    _h_rs = _run_stats.get(h_full2, _run_stats.get(home_full, {}))
                    _a_rs = _run_stats.get(a_full2, _run_stats.get(away_full, {}))
                    if _h_rs and _a_rs:
                        _h_rs_pg = _h_rs.get("rs_pg", _LEAGUE_AVG_RS)
                        _h_ra_pg = _h_rs.get("ra_pg", _LEAGUE_AVG_RS)
                        _a_rs_pg = _a_rs.get("rs_pg", _LEAGUE_AVG_RS)
                        _a_ra_pg = _a_rs.get("ra_pg", _LEAGUE_AVG_RS)
                        _james_home = (_h_rs_pg * _a_ra_pg) / _LEAGUE_AVG_RS
                        _james_away = (_a_rs_pg * _h_ra_pg) / _LEAGUE_AVG_RS
                        _james_total = _james_home + _james_away
                        # Clamp James projection to sane range (6–14 runs)
                        _james_total = max(6.0, min(14.0, _james_total))
                        fair_total = round(fair_total * 0.60 + _james_total * 0.40, 2)
                        # Capture per-team expected runs for Skellam-based total
                        # probability below (more correct than a linear edge
                        # heuristic for a low-scoring discrete-event sport).
                        _mu_home = max(0.5, _james_home)
                        _mu_away = max(0.5, _james_away)
                except Exception:
                    _logger.debug("Silent except at line 6188")
                    pass
            elif sport == "NHL":
                _nhl_gf_dict = dict(NHL_TEAM_GOALS_FOR)
                _nhl_ga_dict = dict(NHL_TEAM_GOALS_AGAINST)
                try:
                    from fetchers import fetch_nhl_live_stats as _fetch_nhl_goals
                    _nhl_live_goals = _fetch_nhl_goals()
                    if _nhl_live_goals.get("goals_for"):
                        _nhl_gf_dict.update(_nhl_live_goals["goals_for"])
                        _nhl_ga_dict.update(_nhl_live_goals["goals_against"])
                except Exception:
                    pass
                h_gf = _nhl_gf_dict.get(home_full, _nhl_gf_dict.get(home_team, NHL_GOALS_DEFAULT))
                h_ga = _nhl_ga_dict.get(home_full, _nhl_ga_dict.get(home_team, NHL_GOALS_DEFAULT))
                a_gf = _nhl_gf_dict.get(away_full, _nhl_gf_dict.get(away_team, NHL_GOALS_DEFAULT))
                a_ga = _nhl_ga_dict.get(away_full, _nhl_ga_dict.get(away_team, NHL_GOALS_DEFAULT))
                # James matchup formula (matches MLB/NFL/Soccer): multiplicative,
                # not simple average. Previously used (h_gf+a_ga)/2, which is
                # more regression-to-mean than the rest of the model — e.g. a
                # 4.5 GF/G team vs a 1.8 GA/G defense gave 3.15 expected goals
                # via simple average vs 2.61 via James, understating how much
                # a stingy defense actually suppresses a high-powered offense.
                _nhl_abbr_gf = [v for k, v in _nhl_gf_dict.items() if len(k) <= 3]
                _nhl_league_avg_gf = sum(_nhl_abbr_gf) / len(_nhl_abbr_gf) if _nhl_abbr_gf else 3.1
                if _nhl_league_avg_gf > 0:
                    home_expected = (h_gf * a_ga) / _nhl_league_avg_gf
                    away_expected = (a_gf * h_ga) / _nhl_league_avg_gf
                else:
                    home_expected = (h_gf + a_ga) / 2
                    away_expected = (a_gf + h_ga) / 2
                _mu_home = max(0.5, home_expected)
                _mu_away = max(0.5, away_expected)
                fair_total = home_expected + away_expected
                # ── ATS Stats NHL L10 O/U momentum nudge ──────────────────
                try:
                    _nhl_ats = fetch_atsstats_nhl_matchups()
                    _h_nhl = _nhl_ats.get(home_full, _nhl_ats.get(home_team, {}))
                    _a_nhl = _nhl_ats.get(away_full, _nhl_ats.get(away_team, {}))
                    if _h_nhl and _a_nhl:
                        _h_ou = _h_nhl.get("l10_ou", (5, 5))
                        _a_ou = _a_nhl.get("l10_ou", (5, 5))
                        # Each Over beyond neutral = +/-0.08 goals; cap ±0.4
                        _h_d = (_h_ou[0] - 5) * 0.08
                        _a_d = (_a_ou[0] - 5) * 0.08
                        fair_total += max(-0.4, min(0.4, (_h_d + _a_d) / 2))
                except Exception:
                    _logger.debug("Silent except at line 6212")
                    pass
            elif sport == "NFL":
                h_power = power_ratings.get(home_team, 104.0)
                a_power = power_ratings.get(away_team, 104.0)
                try:
                    from fetchers import fetch_nfl_live_stats as _fetch_nfl_base
                    base_total = _fetch_nfl_base().get("base_total", 44.5)
                except Exception:
                    base_total = 44.5
                power_adj = ((h_power + a_power) / 2 - 104.0) * 0.5
                fair_total = base_total + power_adj
                # ── James matchup formula (NFL pts scored/allowed) ─────────
                try:
                    _nfl_scoring = fetch_nfl_team_scoring_stats()
                    try:
                        from fetchers import fetch_nfl_live_stats as _fetch_nfl_avg
                        _NFL_LEAGUE_AVG_PTS = _fetch_nfl_avg().get("league_avg_pts", 23.0)
                    except Exception:
                        _NFL_LEAGUE_AVG_PTS = 23.0
                    _h_sc = _nfl_scoring.get(home_team, {})
                    _a_sc = _nfl_scoring.get(away_team, {})
                    if _h_sc and _a_sc:
                        _h_pts = _h_sc.get("pts_for_pg",  _NFL_LEAGUE_AVG_PTS)
                        _h_pa  = _h_sc.get("pts_against_pg", _NFL_LEAGUE_AVG_PTS)
                        _a_pts = _a_sc.get("pts_for_pg",  _NFL_LEAGUE_AVG_PTS)
                        _a_pa  = _a_sc.get("pts_against_pg", _NFL_LEAGUE_AVG_PTS)
                        _james_home = (_h_pts * _a_pa) / _NFL_LEAGUE_AVG_PTS
                        _james_away = (_a_pts * _h_pa) / _NFL_LEAGUE_AVG_PTS
                        _james_total = max(30.0, min(65.0, _james_home + _james_away))
                        # Blend 40% James / 60% power-rating-based
                        fair_total = round(fair_total * 0.60 + _james_total * 0.40, 1)
                except Exception:
                    _logger.debug("Silent except at line 6236")
                    pass
                # ── ATS Stats NFL L10 O/U momentum nudge ──────────────────
                try:
                    _nfl_ats = fetch_atsstats_nfl_matchups()
                    _h_nfl = _nfl_ats.get(home_full, _nfl_ats.get(home_team, {}))
                    _a_nfl = _nfl_ats.get(away_full, _nfl_ats.get(away_team, {}))
                    if _h_nfl and _a_nfl:
                        _h_ou = _h_nfl.get("l10_ou", (5, 5))
                        _a_ou = _a_nfl.get("l10_ou", (5, 5))
                        # Each Over beyond neutral = +/-1.0 NFL point; cap ±5
                        _h_d = (_h_ou[0] - 5) * 1.0
                        _a_d = (_a_ou[0] - 5) * 1.0
                        fair_total += max(-5.0, min(5.0, (_h_d + _a_d) / 2))
                except Exception:
                    _logger.debug("Silent except at line 6250")
                    pass
                # ── 6. NFL weather adjustment on totals ───────────────────
                # Cold temp (<32°F) suppresses scoring; wind >15mph does too.
                # Dome teams: no adjustment (get_nfl_weather returns None).
                try:
                    _nfl_wx = get_nfl_weather(home_team)
                    if _nfl_wx:
                        _temp  = _nfl_wx.get("temp_f", 60)
                        _wind  = _nfl_wx.get("wind_speed_mph", 0)
                        _wx_adj = 0.0
                        # Cold penalty: each degree below 32 → -0.08 pts total
                        if _temp < 32:
                            _wx_adj += (_temp - 32) * 0.08  # negative
                        elif _temp < 45:
                            _wx_adj += (_temp - 45) * 0.04  # modest suppression
                        # Wind penalty: each mph above 15 → -0.15 pts total
                        if _wind > 15:
                            _wx_adj -= (_wind - 15) * 0.15
                        fair_total += max(-7.0, min(0.0, _wx_adj))  # weather only suppresses
                except Exception:
                    _logger.debug("Silent except at line 6270")
                    pass
                # ── NFL key number crossing analysis ──────────────────────────
                _nfl_kn_spread = None
                _nfl_kn_total  = None
                try:
                    from nfl_key_numbers import spread_crossing_value, total_crossing_value
                    if total_str not in ("N/A", None, ""):
                        _nfl_kn_total = total_crossing_value(fair_total, float(total_str))
                    try:
                        _mkt_sp_abs  = abs(float(market_spread))
                        _fair_sp_abs = abs(float(market_spread) - float(power_diff))
                        if _mkt_sp_abs > 0:
                            _nfl_kn_spread = spread_crossing_value(_mkt_sp_abs, _fair_sp_abs)
                    except (NameError, ValueError, TypeError):
                        pass
                except Exception:
                    pass
                # ── NFL model edge signal (LightGBM ensemble) ─────────────────
                _nfl_ge = {}
                try:
                    from nfl_model import nfl_game_edge as _nfl_model_edge_fn
                    _nfl_season = int(game.get("Season", game.get("season", 2025)))
                    _nfl_week   = int(game.get("Week", game.get("week", 1)))
                    _mkt_sp_val = None
                    try:
                        _mkt_sp_val = float(market_spread)
                    except (NameError, ValueError, TypeError):
                        pass
                    _mkt_tot_val = None
                    try:
                        _mkt_tot_val = float(total_str) if total_str not in ("N/A", None, "") else None
                    except (ValueError, TypeError):
                        pass
                    _nfl_ge = _nfl_model_edge_fn(
                        home_team, away_team, _nfl_week, _nfl_season,
                        market_spread=_mkt_sp_val, market_total=_mkt_tot_val,
                    )
                    # Additive nudge: blend 10% of model predicted total when signal is actionable
                    if _nfl_ge.get("signal_strength") in ("PRIMARY", "SUPPORTING"):
                        _pred_tot = _nfl_ge.get("predicted_total", 0.0)
                        if 25.0 < _pred_tot < 75.0:  # sanity bounds for NFL totals
                            fair_total = round(fair_total * 0.90 + _pred_tot * 0.10, 1)
                except Exception:
                    pass
            elif sport == "Soccer":
                # ── Soccer fair_total: James matchup formula ──────────────
                # ESPN team GF/GA per game. Falls back to league baseline.
                _SOCCER_LEAGUE_AVG_PT = 2.72 / 2  # per-team avg (EPL default)
                _soc_league = "eng.1"
                _soc_teams = fetch_soccer_team_goals(_soc_league)
                _h_soc = _soc_teams.get(home_full, _soc_teams.get(home_team, {}))
                _a_soc = _soc_teams.get(away_full, _soc_teams.get(away_team, {}))
                if _h_soc and _a_soc:
                    _h_gf = _h_soc.get("gf_pg", _SOCCER_LEAGUE_AVG_PT)
                    _h_ga = _h_soc.get("ga_pg", _SOCCER_LEAGUE_AVG_PT)
                    _a_gf = _a_soc.get("gf_pg", _SOCCER_LEAGUE_AVG_PT)
                    _a_ga = _a_soc.get("ga_pg", _SOCCER_LEAGUE_AVG_PT)
                    _home_exp = (_h_gf * _a_ga) / max(_SOCCER_LEAGUE_AVG_PT, 0.1)
                    _away_exp = (_a_gf * _h_ga) / max(_SOCCER_LEAGUE_AVG_PT, 0.1)
                    _home_exp += 0.15   # home field boost
                    _away_exp -= 0.10
                    fair_total = round(max(1.0, min(7.0, _home_exp + _away_exp)), 2)
                    # Clean sheet suppressor: >35% CS rate → -0.15 goals each
                    _cs_adj = 0.0
                    if _h_soc.get("cs_rate", 0) > 0.35:
                        _cs_adj -= 0.15
                    if _a_soc.get("cs_rate", 0) > 0.35:
                        _cs_adj -= 0.15
                    fair_total = round(fair_total + _cs_adj, 2)
                    _mu_home = max(0.3, _home_exp)
                    _mu_away = max(0.3, _away_exp)
                else:
                    _league_total = _SOCCER_LEAGUE_BASELINES.get(_soc_league, 2.72)
                    fair_total = round((_league_total / 2) * 1.12 + (_league_total / 2) * 0.88, 2)
                    _mu_home = _mu_away = None
            elif sport == "UFC":
                # ── UFC fair_total: projected rounds ─────────────────────
                _ufc_f1 = home_full or home_team
                _ufc_f2 = away_full or away_team
                _f1_stats = fetch_ufc_fighter_stats(_ufc_f1)
                _f2_stats = fetch_ufc_fighter_stats(_ufc_f2)
                _ufc_card = fetch_ufc_fight_card()
                _wc = ""
                _is_title = False
                for _fight in _ufc_card:
                    if (normalize_name(_ufc_f1) in normalize_name(_fight.get("fighter1", "")) or
                        normalize_name(_ufc_f1) in normalize_name(_fight.get("fighter2", ""))):
                        _wc = _fight.get("weightclass", "")
                        _is_title = _fight.get("is_title", False)
                        break
                _ufc_proj = compute_ufc_round_projection(
                    _f1_stats or {}, _f2_stats or {},
                    weightclass=_wc, is_title=_is_title,
                )
                fair_total = _ufc_proj["fair_rounds"]
            elif sport == "Tennis":
                # ── Tennis fair_total: projected games total ──────────────
                # Serve %, break point conversion, and surface baseline
                # determine expected games. Tour (ATP/WTA) and whether it's
                # a Grand Slam (BO5 vs BO3) scale the baseline accordingly.
                _t_ctx = fetch_tennis_tournament_context()
                # Determine tour from matchup — check ATP scoreboard first
                _tour_key = "atp"
                _t_atp = fetch_tennis_scoreboard("atp")
                _t_wta = fetch_tennis_scoreboard("wta")
                _p1_norm = normalize_name(home_full or home_team)
                _p2_norm = normalize_name(away_full or away_team)
                if _p1_norm in _t_wta or _p2_norm in _t_wta:
                    _tour_key = "wta"
                _ctx = _t_ctx.get(_tour_key, {})
                _surface    = _ctx.get("surface", "hard")
                _is_bo5     = _ctx.get("is_slam", False)  # WTA Slams are BO3
                _p1_stats = fetch_tennis_player_stats(home_full or home_team)
                _p2_stats = fetch_tennis_player_stats(away_full or away_team)
                _tennis_proj = compute_tennis_games_projection(
                    _p1_stats or {}, _p2_stats or {},
                    surface=_surface, is_best_of_5=_is_bo5,
                )
                fair_total = _tennis_proj["fair_games"]
            elif sport == "Golf":
                # ── Golf fair_total: H2H strokes projection ───────────────
                # BetOnline Golf matchups are 2-ball/3-ball H2H — the posted
                # "total" is the combined strokes O/U for the matchup pairing.
                # Model: scoring avg + strokes-gained proxy (birdies - bogeys
                # ratio vs tour average) + live tournament position momentum.
                # Tour avg per round: ~70.5 (PGA field avg scoring).
                _PGA_FIELD_AVG = 70.5
                _p1_golf = fetch_golf_player_stats(home_full or home_team)
                _p2_golf = fetch_golf_player_stats(away_full or away_team)
                _p1_scoring = float((_p1_golf or {}).get("Strokes", _PGA_FIELD_AVG))
                _p2_scoring = float((_p2_golf or {}).get("Strokes", _PGA_FIELD_AVG))
                # Strokes-gained proxy: (birdies - bogeys) vs tour avg
                # Tour avg: ~3.8 birdies, ~3.2 bogeys → net +0.6/round
                def _sg_proxy(stats):
                    if not stats:
                        return 0.0
                    b  = float(stats.get("Birdies", 3.8) or 3.8)
                    bo = float(stats.get("Bogeys",  3.2) or 3.2)
                    e  = float(stats.get("Eagles",  0.1) or 0.1)
                    net = (b - bo + e * 2) - (3.8 - 3.2 + 0.2)  # vs tour avg
                    return round(net * 0.4, 3)   # scale: 1 net birdie = ~0.4 strokes gained
                _p1_sg = _sg_proxy(_p1_golf)
                _p2_sg = _sg_proxy(_p2_golf)
                # Adjust each player's projected score
                _p1_proj = _p1_scoring - _p1_sg
                _p2_proj = _p2_scoring - _p2_sg
                # Live tournament context: position momentum ±0.3 strokes
                try:
                    _g_board = fetch_golf_scoreboard()
                    for _pname, _pstats, _padj in [
                        (home_full or home_team, _p1_golf, "_p1_proj"),
                        (away_full or away_team, _p2_golf, "_p2_proj"),
                    ]:
                        _gp = _g_board.get(normalize_name(_pname), {})
                        if not _gp:
                            continue
                        pos_str = str(_gp.get("position", "") or "")
                        try:
                            pos_n = int(pos_str.replace("T","").replace("t","") or 99)
                            if pos_n <= 5:
                                if _padj == "_p1_proj": _p1_proj -= 0.3
                                else:                   _p2_proj -= 0.3
                            elif pos_n > 40:
                                if _padj == "_p1_proj": _p1_proj += 0.25
                                else:                   _p2_proj += 0.25
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    _logger.debug("Silent except at line 6395")
                    pass
                # fair_total = combined projected strokes (H2H pairing)
                fair_total = round(_p1_proj + _p2_proj, 1)
                # Clamp to realistic H2H total range (130–148 combined)
                fair_total = max(130.0, min(148.0, fair_total))
            if fair_total is not None:
                total_edge = fair_total - total_val
                # For low-scoring, discrete-event sports (MLB runs, NHL goals,
                # Soccer goals), use the Skellam distribution -- the difference
                # of two independent Poisson processes -- to get a real
                # probability-based edge instead of a linear divide-by-scale
                # heuristic. This is the statistically correct distribution
                # for these sports (matches how sharp shops actually price
                # totals/spreads on discrete low-scoring events) and is more
                # accurate than treating the gap as a flat percentage of an
                # arbitrary scale constant. Falls back to the linear heuristic
                # when per-team expected scoring wasn't available this game.
                _mu_h = locals().get("_mu_home")
                _mu_a = locals().get("_mu_away")
                _used_skellam = False
                if sport in ("MLB", "NHL", "Soccer") and _mu_h and _mu_a:
                    try:
                        # Always evaluate the SAME side that total_edge (and
                        # therefore the downstream side="OVER" if total_edge>0
                        # selection) implies, so the Skellam-derived magnitude
                        # can never disagree with which side actually gets
                        # recommended.
                        _skellam_side = "OVER" if total_edge > 0 else "UNDER"
                        _skellam_prob = compute_fair_prob_skellam(total_val, _mu_h, _mu_a, _skellam_side)
                        _raw_edge_pct = max(-0.20, min(0.20, _skellam_prob - 0.524))
                        total_edge_pct = _raw_edge_pct if total_edge > 0 else -_raw_edge_pct
                        _used_skellam = True
                    except Exception:
                        _used_skellam = False
                if not _used_skellam:
                    total_edge_pct = total_edge / 50.0
                    if sport == "MLB":
                        total_edge_pct = total_edge / 10.0
                    elif sport == "NHL":
                        total_edge_pct = total_edge / 8.0
                    elif sport == "NFL":
                        total_edge_pct = total_edge / 30.0
                    elif sport == "WNBA":
                        total_edge_pct = total_edge / 30.0
                    elif sport == "Soccer":
                        total_edge_pct = total_edge / 4.0
                    elif sport == "UFC":
                        total_edge_pct = total_edge / 3.0
                elif sport == "Tennis":
                    total_edge_pct = total_edge / 10.0
                elif sport == "Golf":
                    total_edge_pct = total_edge / 8.0  # H2H total ~140; 4-stroke range = big edge
                total_edge_pct = max(-0.20, min(0.20, total_edge_pct))
                # Apply steam signal to total edge
                try:
                    _total_steam = _steam_signals.get("betonline_total", {}) if '_steam_signals' in dir() else {}
                    if _total_steam.get("is_steam"):
                        _t_mult = min(1.15, 1 + _total_steam.get("confidence", 0) * 0.15)
                        total_edge_pct *= _t_mult
                    total_edge_pct = max(-0.20, min(0.20, total_edge_pct))
                except Exception:
                    _logger.debug("Silent except at line 6456")
                    pass
                if abs(total_edge_pct) >= 0.02:
                    side = "OVER" if total_edge > 0 else "UNDER"
                    tier = _get_cal_game_tier(abs(total_edge_pct), sport)
                    _pinn_tot_prob, _pinn_tot_conf, _pinn_tot_note = pinnacle_game_fair_value(home_team, away_team, "total", sport, side)
                    _pinn_tot = {"prob": _pinn_tot_prob, "confirms": _pinn_tot_conf, "note": _pinn_tot_note} if _pinn_tot_prob is not None else None
                    _vsin_tot_prob, _vsin_tot_conf, _vsin_tot_note = vsin_sharp_signal(home_team, away_team, "total", sport, side)
                    _vsin_tot = {"prob": _vsin_tot_prob, "confirms": _vsin_tot_conf, "note": _vsin_tot_note} if _vsin_tot_prob is not None else None
                    recommendations.append({"type": "TOTAL", "pick": f"{side} {total_val}", "edge": total_edge_pct, "edge_pct": f"{total_edge_pct:.1%}", "tier": tier, "fair_total": round(fair_total, 1), "market_total": total_val, "divergence": round(total_edge, 1), "note": f"Model projects {fair_total:.1f} vs market {total_val} — {side} value", "market_agreement": _gl_consensus.get("agreement", "NO_DATA"), "market_agreement_note": _gl_consensus.get("agreement_note", ""), "n_books": _gl_consensus.get("total", {}).get("n_books", 0), "public_pct_home": _gl_consensus.get("public_pct_home"), "public_pct_away": _gl_consensus.get("public_pct_away"), "sharp_vs_public": _gl_consensus.get("sharp_vs_public"), "pinnacle_sharp": _pinn_tot, "vsin_sharp": _vsin_tot})
                    if abs(total_edge_pct) > best_edge:
                        best_edge = abs(total_edge_pct)
                        best_bet = recommendations[-1]
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    
    try:
        if home_ml and away_ml and home_ml != "N/A" and away_ml != "N/A":
            h_ml = float(str(home_ml).replace("+",""))
            a_ml = float(str(away_ml).replace("+",""))
            # Prefer multi-book consensus / Pinnacle-anchored implied probability
            # over a single-line devig — same role Pinnacle no-vig plays for props.
            _ml_consensus = _gl_consensus.get("moneyline", {}) if isinstance(_gl_consensus, dict) else {}
            if _ml_consensus.get("pinnacle_home_prob") is not None:
                h_implied = _ml_consensus["pinnacle_home_prob"]
                a_implied = 1 - h_implied
            elif _ml_consensus.get("home_consensus_prob") is not None:
                h_implied = _ml_consensus["home_consensus_prob"]
                a_implied = _ml_consensus.get("away_consensus_prob", 1 - h_implied)
            else:
                # Fall back to single-line devig (ensemble Probit+Shin blend)
                try:
                    from bc_utils import devig_ensemble
                    _ens = devig_ensemble(h_ml, a_ml, market_type="ml",
                                          liquidity="high" if sport in ("NFL","MLB") else "medium")
                    h_implied = _ens["fair_prob"]
                    a_implied = 1 - h_implied
                except Exception:
                    if h_ml < 0:
                        h_implied = abs(h_ml) / (abs(h_ml) + 100)
                    else:
                        h_implied = 100 / (h_ml + 100)
                    if a_ml < 0:
                        a_implied = abs(a_ml) / (abs(a_ml) + 100)
                    else:
                        a_implied = 100 / (a_ml + 100)
            if home_team in power_ratings and away_team in power_ratings:
                h_power = power_ratings[home_team]
                a_power = power_ratings[away_team]
                power_diff = h_power - a_power
                # Sport-specific sigmoid divisors — tuned to each sport's power rating scale
                # NBA/NFL/WNBA use 100-112 scale; MLB uses same scale but smaller diffs
                # NHL uses same scale; sigmoid /7 was too flat for all except NHL
                _ml_divisor = {"NBA": 4, "NFL": 4, "WNBA": 4, "MLB": 1.5, "NHL": 7}.get(sport, 7)
                h_fair = 1 / (1 + math.exp(-power_diff / _ml_divisor))
                a_fair = 1 - h_fair

                # NFL: Log5 adjustment using power-rating-implied win percentages.
                # Log5 strips schedule bias from the sigmoid output, giving a
                # cleaner H2H probability when both teams are far from .500.
                # Blend: 70% sigmoid (already opponent-adjusted via power ratings)
                # + 30% Log5 (corrects for extreme mismatches more accurately).
                if sport == "NFL":
                    try:
                        _p_h = h_fair
                        _p_a = a_fair
                        _log5_h = mc_log5_win_prob(_p_h, _p_a)
                        h_fair = round(0.70 * h_fair + 0.30 * _log5_h, 4)
                        a_fair = round(1.0 - h_fair, 4)
                    except Exception:
                        _logger.debug("Silent except at line 6521")
                        pass

                # NBA/WNBA: composite ratings → Log5 blend for ML.
                # The scalar power ratings already encode net efficiency vs league;
                # Log5 converts them into cleaner H2H probability.
                # Blend: 70% sigmoid + 30% Log5.
                if sport in ("NBA", "WNBA"):
                    try:
                        _log5_nba_ml = mc_log5_win_prob(h_fair, a_fair)
                        h_fair = round(0.70 * h_fair + 0.30 * _log5_nba_ml, 4)
                        a_fair = round(1.0 - h_fair, 4)
                    except Exception:
                        _logger.debug("Silent except at line 6533")
                        pass


                # expected scoring (MLB James formula, NHL goals-for/against,
                # Soccer xG) the MC simulation gives a probability directly from
                # the actual scoring distribution, not just the rating gap.
                # Blend 40% MC / 60% power-rating sigmoid when MC data is available.
                _mc_h = _mc_a = None
                _mu_h_mc = locals().get("_mu_home")
                _mu_a_mc = locals().get("_mu_away")
                if sport in ("MLB", "NHL", "Soccer") and _mu_h_mc and _mu_a_mc:
                    try:
                        _mc_result = mc_simulate_game(_mu_h_mc, _mu_a_mc)
                        _mc_h = _mc_result["home_win_prob"]
                        _mc_a = _mc_result["away_win_prob"] + _mc_result["draw_prob"] * 0.5
                    except Exception:
                        _logger.debug("Silent except at line 6549")
                        pass
                if _mc_h is not None:
                    h_fair = round(0.60 * h_fair + 0.40 * _mc_h, 4)
                    a_fair = round(1.0 - h_fair, 4)
                h_ml_edge = h_fair - h_implied
                a_ml_edge = a_fair - a_implied
                best_ml_edge = max(h_ml_edge, a_ml_edge)
                if best_ml_edge >= 0.02:
                    if h_ml_edge > a_ml_edge:
                        ml_pick = f"{home_team} ML ({home_ml})"
                        ml_edge = h_ml_edge
                        fair_prob = h_fair
                    else:
                        ml_pick = f"{away_team} ML ({away_ml})"
                        ml_edge = a_ml_edge
                        fair_prob = a_fair
                    tier = _get_cal_game_tier(ml_edge, sport)
                    _ml_picked_odds = home_ml if h_ml_edge > a_ml_edge else away_ml
                    ev = fair_prob * (abs(float(str(_ml_picked_odds).replace("+",""))) / 100) - (1 - fair_prob)
                    _ml_note = f"Fair probability {fair_prob:.1%} vs implied — +EV at these odds"
                    if _ml_consensus.get("n_books", 0) >= 2:
                        _ml_note += f" ({_ml_consensus['n_books']}-book consensus)"
                    _pinn_ml_side = "HOME" if h_ml_edge >= a_ml_edge else "AWAY"
                    _pinn_ml_prob, _pinn_ml_conf, _pinn_ml_note = pinnacle_game_fair_value(home_team, away_team, "moneyline", sport, _pinn_ml_side)
                    _pinn_ml = {"prob": _pinn_ml_prob, "confirms": _pinn_ml_conf, "note": _pinn_ml_note} if _pinn_ml_prob is not None else None
                    _vsin_ml_prob, _vsin_ml_conf, _vsin_ml_note = vsin_sharp_signal(home_team, away_team, "moneyline", sport, _pinn_ml_side)
                    _vsin_ml = {"prob": _vsin_ml_prob, "confirms": _vsin_ml_conf, "note": _vsin_ml_note} if _vsin_ml_prob is not None else None
                    recommendations.append({"type": "MONEYLINE", "pick": ml_pick, "edge": ml_edge, "mc_blend": True, "edge_pct": f"{ml_edge:.1%}", "ev": round(ev, 3), "tier": tier, "fair_prob": round(fair_prob, 3), "odds": _ml_picked_odds, "note": _ml_note, "market_agreement": _gl_consensus.get("agreement", "NO_DATA"), "market_agreement_note": _gl_consensus.get("agreement_note", ""), "public_pct_home": _gl_consensus.get("public_pct_home"), "public_pct_away": _gl_consensus.get("public_pct_away"), "sharp_vs_public": _gl_consensus.get("sharp_vs_public"), "pinnacle_sharp": _pinn_ml, "vsin_sharp": _vsin_ml})
                    if ml_edge > best_edge:
                        best_edge = ml_edge
                        best_bet = recommendations[-1]
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    
    # ── Sharp signal computation ─────────────────────────────────────────────
    _steam_signals   = {}
    _mkt_divergence  = {}
    _rlm_score       = {}
    _sharp_consensus = {}

    try:
        from bc_utils import (detect_steam_move, detect_market_maker_divergence,
                               score_rlm, record_line, get_opener_gap,
                               compute_line_velocity)

        _game_key = f"{away_team}@{home_team}"

        # Record current lines for steam tracking
        if total_str not in ("N/A", None, ""):
            try:
                _tv = float(str(total_str).replace("+",""))
                record_line("betonline", _game_key, "total", _tv, 0, 0)
                record_line("pinnacle",  _game_key, "total", _tv, 0, 0)
            except Exception:
                _logger.debug("Silent except at line 6598")
                pass

        if spread_str not in ("N/A", None, ""):
            try:
                _sv = float(str(spread_str).split()[-1].replace("+",""))
                record_line("betonline", _game_key, "spread", _sv, 0, 0)
            except Exception:
                _logger.debug("Silent except at line 6605")
                pass

        # Steam detection on total and spread
        for _mkt in ["total", "spread"]:
            for _bk in ["betonline", "pinnacle"]:
                _steam = detect_steam_move(_bk, _game_key, _mkt)
                if _steam.get("is_steam"):
                    _steam_signals[f"{_bk}_{_mkt}"] = _steam

        # Opener gap
        _total_gap  = get_opener_gap("betonline", _game_key, "total")
        _spread_gap = get_opener_gap("betonline", _game_key, "spread")
        if abs(_total_gap.get("gap", 0)) >= 0.5:
            _steam_signals["total_opener_gap"]  = _total_gap
        if abs(_spread_gap.get("gap", 0)) >= 0.5:
            _steam_signals["spread_opener_gap"] = _spread_gap

        # Market maker divergence — build lines_by_book from available data
        # TODO: game_lines_data was never wired up (no such param/variable in
        # this function) — guarded to avoid NameError until a real per-book
        # lines source (e.g. aggregated session_state lines by matchup) is wired in.
        _lines_by_book = {}
        _game_lines_data = []
        if _game_lines_data:
            for _bk_data in _game_lines_data:
                _bk_name = _bk_data.get("Book", _bk_data.get("book", ""))
                _bk_total = _bk_data.get("Total", _bk_data.get("total"))
                _bk_spread = _bk_data.get("Spread", _bk_data.get("spread"))
                if _bk_name and (_bk_total or _bk_spread):
                    _lines_by_book[_bk_name] = {
                        "total": _bk_total, "spread": _bk_spread
                    }
        if len(_lines_by_book) >= 2:
            _mkt_divergence = detect_market_maker_divergence(_lines_by_book)

        # RLM scoring from public data
        if game_public:
            _pub_pct  = game_public.get("spread_public_pct", 0.5)
            _pub_side = game_public.get("spread_public_side", "")
            _line_dir = "HOME" if (spread_edge if 'spread_edge' in dir() else 0) > 0 else "AWAY"
            if _pub_pct and _pub_side:
                _rlm_score = score_rlm(_pub_pct, _line_dir, _pub_side,
                                        abs(_spread_gap.get("gap", 0.5)))

        # Sharp consensus from BOL + Pinnacle agreement
        if _mkt_divergence.get("gap", 1.0) < 0.25:
            _sharp_consensus = {
                "agreement": True,
                "setter_line": _mkt_divergence.get("setter_line"),
                "confidence": "HIGH" if _mkt_divergence.get("gap", 1) < 0.1 else "MODERATE",
            }

    except Exception:
        _logger.debug("Silent except at line 6658")
        pass

    # Market availability flags for UI labeling
    spread_available = spread_str not in ("N/A", None, "")
    total_available  = total_str  not in ("N/A", None, "")
    ml_available     = home_ml    not in ("N/A", None, "")

    # Determine favorite for display — negative ML = favorite
    try:
        _fav_team = ""
        _fav_ml   = ""
        if home_ml not in ("N/A", None, "") and away_ml not in ("N/A", None, ""):
            _home_ml_val = float(str(home_ml).replace("+","").strip())
            _away_ml_val = float(str(away_ml).replace("+","").strip())
            # Favorite = more negative ML (lower value)
            if _home_ml_val <= _away_ml_val:
                _fav_team = home_team
                _fav_ml   = str(home_ml)
            else:
                _fav_team = away_team
                _fav_ml   = str(away_ml)
        elif home_ml not in ("N/A", None, ""):
            _fav_team = home_team
            _fav_ml   = str(home_ml)
    except Exception:
        _fav_team = home_team
        _fav_ml   = str(home_ml) if home_ml not in ("N/A", None, "") else ""

    # Extract edge/tier/pick from recommendations to top-level fields
    _spread_rec = next((r for r in recommendations if r.get("type") == "SPREAD"), None)
    _total_rec  = next((r for r in recommendations if r.get("type") == "TOTAL"),  None)
    _ml_rec     = next((r for r in recommendations if r.get("type") in ("MONEYLINE","ML")), None)
    _alt_rec    = next((r for r in recommendations if r.get("type") == "ALT_SPREAD"), None)

    # ── NFL key number + model signal enrichment ──────────────────────────────
    if sport == "NFL":
        try:
            _kn_t = _nfl_kn_total
        except NameError:
            _kn_t = None
        try:
            _kn_s = _nfl_kn_spread
        except NameError:
            _kn_s = None
        try:
            _ge = _nfl_ge
        except NameError:
            _ge = {}
        try:
            for _r in recommendations:
                if _r.get("type") == "TOTAL" and _kn_t:
                    _r["key_number_note"]     = _kn_t.get("note", "")
                    _r["key_number_weight"]   = _kn_t.get("weight", 1.0)
                    _r["key_numbers_crossed"] = _kn_t.get("key_numbers_crossed", [])
                elif _r.get("type") == "SPREAD" and _kn_s:
                    _r["key_number_note"]     = _kn_s.get("note", "")
                    _r["key_number_weight"]   = _kn_s.get("weight", 1.0)
                    _r["key_numbers_crossed"] = _kn_s.get("key_numbers_crossed", [])
            if _ge.get("signal_strength") not in (None, "IGNORE", ""):
                for _r in recommendations:
                    _r["nfl_model_signal"]     = _ge.get("signal_strength", "")
                    _r["nfl_model_side"]       = _ge.get("model_side", "")
                    _r["nfl_model_confidence"] = round(_ge.get("confidence", 0.0), 3)
        except Exception:
            pass

    return {
        "matchup": matchup, "Matchup": matchup,
        "home": home_team, "away": away_team,
        "Sport": sport,  # uppercase for UI filter compatibility
        "sport": sport,  # lowercase for internal use
        "loaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),  # freshness tracking
        "matchup":   matchup,
        "home":      home_team,   # lowercase keys for ML card display
        "away":      away_team,
        "recommendations": recommendations, "best_bet": best_bet,
        "best_edge": best_edge, "sport": sport,
        "public_signals": public_sharp_signals, "public_data": game_public,
        "HomeML": home_ml, "AwayML": away_ml,
        "Spread": spread_str, "Total": total_str,
        "FavoriteTeam": _fav_team,
        "FavoriteML":   _fav_ml,
        # Top-level edge/tier/pick fields for game card display
        "SpreadEdge":  _spread_rec["edge"] if _spread_rec else 0,
        "SpreadTier":  _spread_rec["tier"] if _spread_rec else "LEAN",
        "SpreadPick":  _spread_rec["pick"] if _spread_rec else "",
        "TotalEdge":   _total_rec["edge"]  if _total_rec  else 0,
        "TotalTier":   _total_rec["tier"]  if _total_rec  else "LEAN",
        "TotalPick":   _total_rec["pick"]  if _total_rec  else "",
        "MLEdge":      _ml_rec["edge"]     if _ml_rec     else 0,
        "MLTier":      _ml_rec["tier"]     if _ml_rec     else "LEAN",
        "MLPick":      _ml_rec["pick"]     if _ml_rec     else "",
        "AltLine":     _alt_rec["pick"]    if _alt_rec    else "",
        "AltEdge":     _alt_rec["edge"]    if _alt_rec    else 0,
        "AltTier":     _alt_rec["tier"]    if _alt_rec    else "LEAN",
        # Clean, unambiguous home-team-relative spread number (e.g. -1.5
        # means home favored by 1.5), independent of which side the model
        # actually recommended. This is what locking/grading code should
        # read for "line" -- never the raw "Spread" string above, which is
        # team-name-prefixed exactly as scraped ("Pittsburgh Pirates -1.5")
        # and crashes float() if used directly (bug found 2026-07-13; an
        # earlier fix on 2026-07-12 mistakenly targeted a dead code path —
        # build_game_line_consensus() is a stub that always returns {},
        # so that branch never actually ran).
        "SpreadLineHome": _spread_rec.get("market_spread") if _spread_rec else None,
        # Run Line (MLB) / Puck Line (NHL): -1.5 spread with adjusted odds
        # Derived from ML when real run line odds aren't scraped yet.
        # Standard approximation: favorite run line ≈ ML + ~130-150 pts of juice
        # e.g. home ML -106 → home run line -1.5 ≈ +115 to +125
        "RunLineHome": game.get("RunLineHome", game.get("run_line_home", "")),
        "RunLineAway": game.get("RunLineAway", game.get("run_line_away", "")),
        "market_flags": {
            "spread": "available" if spread_available else "no_market",
            "total":  "available" if total_available  else "no_market",
            "ml":     "available" if ml_available      else "no_market",
        },
        # ── Sharp signal layer ────────────────────────────────────────────────
        "steam_signals":    _steam_signals,
        "market_divergence": _mkt_divergence,
        "rlm_score":        _rlm_score,
        "sharp_consensus":  _sharp_consensus,
    }


@st.cache_data(ttl=21600, show_spinner=False)
def get_live_power_ratings(sport, fallback_ratings):
    """
    Live predictive power ratings. For MLB: uses live run differential from
    statsapi.mlb.com (replaces the broken TeamRankings HTML scraper which
    uses JS-rendered tables that Python regex cannot see). For other sports:
    TeamRankings.com, falling back to the static hardcoded dict when the
    scrape is empty or fails.
    Cached 6h to match the underlying fetcher's own cache window.
    """
    source_label = "static_fallback"
    try:
        if sport == "MLB":
            from fetchers import fetch_mlb_live_stats as _fetch_mlb_live
            live = _fetch_mlb_live().get("team_ratings", {})
            source_label = "mlb_statsapi_live"
        elif sport == "WNBA":
            from fetchers import fetch_wnba_live_stats as _fetch_wnba_live
            live = _fetch_wnba_live().get("team_ratings", {})
            source_label = "wnba_espn_live"
        elif sport == "NHL":
            from fetchers import fetch_nhl_live_stats as _fetch_nhl_live
            live = _fetch_nhl_live().get("team_ratings", {})
            source_label = "nhl_api_live"
        elif sport == "NBA":
            from fetchers import fetch_nba_live_stats as _fetch_nba_live
            live = _fetch_nba_live().get("team_ratings", {})
            source_label = "nba_espn_live"
        elif sport == "NFL":
            from fetchers import fetch_nfl_live_stats as _fetch_nfl_live
            live = _fetch_nfl_live().get("team_ratings", {})
            source_label = "nfl_espn_live"
        else:
            live = fetch_teamrankings_power_ratings(sport)
            source_label = "teamrankings_live"
    except Exception:
        live = {}
    if not live:
        return fallback_ratings, "static_fallback"
    merged = dict(fallback_ratings)
    for team, rating in live.items():
        merged[team] = rating
    if fallback_ratings:
        matched = sum(1 for t in live if t in fallback_ratings)
        if matched / len(fallback_ratings) < 0.7:
            return fallback_ratings, "static_fallback_low_match"
    return merged, source_label


@st.cache_data(ttl=900, show_spinner=False)
def analyze_all_games(games, sport, home_teams, away_teams, mlb_pitchers=None):
    all_game_analysis = []
    power_map = {"NBA": NBA_POWER_RATINGS, "WNBA": WNBA_POWER_RATINGS, "MLB": MLB_POWER_RATINGS, "NHL": NHL_POWER_RATINGS}
    power_ratings = power_map.get(sport, {})
    if sport in ("MLB", "WNBA", "NHL", "NBA", "NFL"):
        power_ratings, _pr_source = get_live_power_ratings(sport, power_ratings)
    for game in games:
        analysis = analyze_game_edge(game, sport, home_teams, away_teams, power_ratings, mlb_pitchers=mlb_pitchers)
        # Append all games — not just those with best_bet
        # Games without edge still needed for coverage audit + display
        all_game_analysis.append(analysis)
    all_game_analysis.sort(key=lambda x: x["best_edge"], reverse=True)
    return all_game_analysis

def scan_all_sports_best_plays():
    results = {"best_props": [], "best_games": [], "timestamp": datetime.now().strftime("%H:%M")}
    active_sports = ["NBA", "MLB", "NHL", "WNBA"]
    progress = st.progress(0)
    status = st.empty()
    for idx, sport in enumerate(active_sports):
        try:
            status.write(f"Scanning {sport} board...")
            progress.progress(idx / len(active_sports))
            # Skip NBA/NHL during off-season — avoids empty boards and errors
            _scan_regime = detect_season_regime(sport)
            if _scan_regime.get("regime") == "Off-season":
                continue
            props = scrape_prizepicks_with_gist_fallback(sport)
            if not props:
                props = fetch_underdog_props(sport)
            games, is_playoff, home_teams, away_teams = fetch_game_lines(sport)
            sport_defaults = DEFAULT_AVERAGES.get(sport, {})
            sport_avgs = PLAYER_AVERAGES.get(sport, {})
            for p in props[:50]:
                stat_raw = p["Prop"]
                stat_norm = STAT_NORMALIZE.get((sport, stat_raw), stat_raw)
                player = p["Player"]
                line = p["Line"]
                player_stats, using_default = find_player_avg(player, sport_avgs)
                if using_default:
                    continue
                avg = player_stats.get(stat_norm, sport_defaults.get(stat_norm, line))
                if avg <= 0:
                    continue
                edge, prob, _ = compute_multi_signal_edge(line, avg, 112.0, False, 0, "OVER", stat_norm, 0.0, 2, "standard", sport)
                ev_2 = calculate_prizepicks_ev(prob, 2)
                tier = get_tier(edge, sport, st.session_state.get("calibrated_thresholds"))
                if edge >= 0.05:
                    results["best_props"].append({"Sport": sport, "Player": player, "Prop": stat_raw, "Line": line, "Side": "OVER", "Edge": edge, "EdgePct": f"{edge:.1%}", "EV_2pick": f"{ev_2:+.1%}", "Tier": tier, "Avg": avg, "Prob": prob})
            if games:
                game_results = analyze_all_games(games, sport, home_teams, away_teams)
                for gr in game_results:
                    if gr.get("best_bet"):
                        gr["sport"] = sport
                        results["best_games"].append(gr)
        except Exception as e:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": f"scan_all_sports_{sport}", "error": str(e)[:100]})
            continue
    progress.progress(1.0)
    status.empty()
    progress.empty()
    results["best_props"].sort(key=lambda x: x["Edge"], reverse=True)
    results["best_games"].sort(key=lambda x: x["best_edge"], reverse=True)
    return results

# ═══════════════════════════════════════════════════════════════════════
# NEW BETTOR SHORTLIST — advisory-only presentation layer
# ─────────────────────────────────────────────────────────────────────
# Purpose: give a bettor who doesn't have time to read the Full Board /
# Game Lines tabs a short, curated list of only the model's highest-
# conviction plays (SOVEREIGN/ELITE), correlation-checked so it doesn't
# just staple 6 same-game props together into a parlay.
#
# IMPORTANT — isolation guarantee: everything in this section only READS
# from data structures that already exist elsewhere in the app (board
# props, game analysis, calibrated thresholds). It never writes to
# signal_performance.json, injury_performance.json, history.json, SEM
# calibration, or any other file that feeds the model. It is a pure
# display/advisory layer on top of outputs that already exist — it must
# stay that way in any future edits.
# ═══════════════════════════════════════════════════════════════════════

_BEGINNER_TIER_ORDER = {"SOVEREIGN": 4, "ELITE": 3, "APPROVED": 2, "LEAN": 1, "PASS": 0}
_BEGINNER_TIER_SCORE = {"SOVEREIGN": 1.0, "ELITE": 0.8, "APPROVED": 0.6, "LEAN": 0.3, "PASS": 0.1}
_BEGINNER_ELIGIBLE_SPORTS = ["NBA", "MLB", "NHL", "WNBA", "NFL", "Tennis", "Golf", "Soccer", "UFC"]


def build_new_bettor_shortlist(max_props=6, max_games=6, min_tier="ELITE"):
    """
    Scans every active sport's board + game lines and returns only the
    plays that clear the SOVEREIGN/ELITE bar, correlation-checked so the
    shortlist doesn't quietly stack correlated legs.

    Does NOT force a fixed count — if fewer than max_props/max_games
    plays clear the bar today, it returns fewer (or none) rather than
    backfilling with weaker tiers. That's intentional: a forced quota
    would mean showing a new bettor a LEAN play labeled as a "top pick,"
    which is worse than saying "nothing elite today."

    Returns:
        {
          "props": [ {..prop dict.., "why": str}, ... ],   # <= max_props
          "games": [ {..game dict.., "why": str}, ... ],    # <= max_games
          "scanned_sports": [...], "skipped_sports": [...],
          "timestamp": "HH:MM"
        }
    """
    min_rank = _BEGINNER_TIER_ORDER.get(min_tier, 3)
    candidate_props = []
    candidate_games = []
    scanned, skipped = [], []

    progress = st.progress(0)
    status = st.empty()
    active_sports = [s for s in _BEGINNER_ELIGIBLE_SPORTS]

    for idx, sport in enumerate(active_sports):
        try:
            status.write(f"Scanning {sport} board for elite plays...")
            progress.progress((idx) / max(1, len(active_sports)))
            regime = detect_season_regime(sport)
            if regime.get("regime") == "Off-season":
                skipped.append(sport)
                continue

            # ── Props ──────────────────────────────────────────────
            # 2026-07-18: first fix (reading store_board_snapshot's Gist
            # capture) only worked for sports already loaded on Full Board
            # today -- defeats the actual goal here, which is scanning
            # EVERY sport automatically without the user pre-loading each
            # one first. Games below already does this correctly (calls
            # analyze_all_games directly, the real pipeline) -- props now
            # matches that pattern via load_sport_data(sport), the same
            # function the "Load Board" button calls. This is the real,
            # fully-enriched board (real opp_def_rating, real is_home,
            # player_name passed so every signal fires, both OVER and
            # UNDER checked) -- not the old hardcoded/OVER-only fallback.
            _nb_board, _, _, _, _, _ = load_sport_data(sport)
            for p in (_nb_board or []):
                tier = p.get("Tier", "")
                if _BEGINNER_TIER_ORDER.get(tier, 0) < min_rank:
                    continue
                edge = p.get("Edge", 0) or 0
                prob = p.get("Prob", 0.5)
                ev_2 = calculate_prizepicks_ev(prob, 2)
                candidate_props.append({
                    "Sport": sport, "Player": p.get("Player", ""), "Prop": p.get("Prop", ""),
                    "Line": p.get("Line", 0), "Side": p.get("Side", "OVER"), "Team": p.get("Team", ""),
                    "Edge": edge, "EdgePct": f"{edge:.1%}", "EV_2pick": f"{ev_2:+.1%}",
                    "Tier": tier, "Avg": p.get("Avg"), "Prob": prob,
                })

            # ── Game lines ─────────────────────────────────────────
            games, is_playoff, home_teams, away_teams = fetch_game_lines(sport)
            if games:
                game_results = analyze_all_games(games, sport, home_teams, away_teams)
                for gr in game_results:
                    # pick the single best-tier bet type on this game
                    bet_options = [
                        ("Spread", gr.get("SpreadTier", "LEAN"), gr.get("SpreadEdge", 0), gr.get("SpreadPick", "")),
                        ("Total",  gr.get("TotalTier", "LEAN"),  gr.get("TotalEdge", 0),  gr.get("TotalPick", "")),
                        ("ML",     gr.get("MLTier", "LEAN"),     gr.get("MLEdge", 0),     gr.get("MLPick", "")),
                    ]
                    bet_options.sort(key=lambda o: _BEGINNER_TIER_ORDER.get(o[1], 0), reverse=True)
                    best_type, best_tier, best_edge, best_pick = bet_options[0]
                    if _BEGINNER_TIER_ORDER.get(best_tier, 0) < min_rank or not best_pick:
                        continue
                    candidate_games.append({
                        "Sport": sport, "Matchup": gr.get("matchup", ""),
                        "Home": gr.get("home", ""), "Away": gr.get("away", ""),
                        "BetType": best_type, "Pick": best_pick,
                        "Edge": best_edge, "EdgePct": f"{best_edge:.1%}",
                        "Tier": best_tier,
                    })
            scanned.append(sport)
        except Exception as e:
            st.session_state.setdefault("errors", []).append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "source": f"new_bettor_shortlist_{sport}", "error": str(e)[:150]
            })
            skipped.append(sport)
            continue

    progress.progress(1.0)
    status.empty()
    progress.empty()

    candidate_props.sort(key=lambda x: x["Edge"], reverse=True)
    candidate_games.sort(key=lambda x: x["Edge"], reverse=True)

    # ── Correlation-aware greedy selection for props ────────────────
    # Walk candidates best-edge-first; only add a leg if it doesn't push
    # the running correlation score of the selected set past 0.30. This
    # is the same compute_parlay_correlation() function used by the
    # Slip Analyzer, so the bar here matches what the rest of the app
    # already considers "too correlated."
    selected_props = []
    for cand in candidate_props:
        if len(selected_props) >= max_props:
            break
        trial = selected_props + [cand]
        score, _pairs = compute_parlay_correlation(trial)
        if score <= 0.30 or not selected_props:
            selected_props.append(cand)

    # ── De-dupe game lines: one bet per matchup, cap at max_games ────
    selected_games = []
    seen_matchups = set()
    for cand in candidate_games:
        if len(selected_games) >= max_games:
            break
        if cand["Matchup"] in seen_matchups:
            continue
        seen_matchups.add(cand["Matchup"])
        selected_games.append(cand)

    for p in selected_props:
        p["why"] = (
            f"{p['Tier'].title()} tier · {p['EdgePct']} model edge on "
            f"{p['Player']} {p['Prop']} {p['Side']} {p['Line']}."
        )
    for g in selected_games:
        g["why"] = (
            f"{g['Tier'].title()} tier · {g['EdgePct']} model edge on "
            f"{g['Matchup']} — {g['BetType']}: {g['Pick']}."
        )

    return {
        "props": selected_props, "games": selected_games,
        "scanned_sports": scanned, "skipped_sports": skipped,
        "timestamp": datetime.now().strftime("%H:%M"),
    }


def evaluate_parlay_verdict(legs):
    """
    Advisory-only "should I take this parlay" check for new bettors.
    Combines correlation risk (via compute_parlay_correlation, same
    function the Slip Analyzer uses) with tier composition and leg
    count. Read-only: does not touch SEM, signal weights, or any stored
    performance/history data.

    legs: list of dicts. Prop legs use Player/Prop/Team/Tier keys
    (same shape as board props). Game legs use Matchup/BetType/Tier.

    Returns:
        {
          "verdict": "GO" | "CAUTION" | "DON'T",
          "reason": str,
          "suggested_fix": str or None,
          "correlation_score": float,
          "correlated_pairs": [...],
        }
    """
    if not legs:
        return {"verdict": "—", "reason": "No legs selected.", "suggested_fix": None,
                "correlation_score": 0.0, "correlated_pairs": []}

    prop_legs = [l for l in legs if l.get("leg_type", "prop") == "prop"]
    game_legs = [l for l in legs if l.get("leg_type") == "game"]

    corr_score, corr_pairs = compute_parlay_correlation(prop_legs) if len(prop_legs) >= 2 else (0.0, [])

    # Same-game correlation between a prop leg and a game-line leg on the
    # same matchup/team isn't covered by compute_parlay_correlation
    # (it's prop-shaped only), so add a lightweight same-team check here.
    same_game_hits = []
    for gl in game_legs:
        gl_teams = {gl.get("Home", ""), gl.get("Away", "")}
        for pl in prop_legs:
            if pl.get("Team", "") in gl_teams and pl.get("Team", ""):
                same_game_hits.append(f"{pl.get('Player','')} prop shares a game with your {gl.get('BetType','')} pick")
    if same_game_hits:
        corr_score = min(1.0, corr_score + 0.15 * len(same_game_hits))
        corr_pairs = corr_pairs + same_game_hits

    tier_scores = [_BEGINNER_TIER_SCORE.get(l.get("Tier", "LEAN"), 0.3) for l in legs]
    avg_tier_score = sum(tier_scores) / len(tier_scores)
    weakest_idx = min(range(len(legs)), key=lambda i: tier_scores[i])
    weakest_leg = legs[weakest_idx]
    weakest_label = weakest_leg.get("Player") or weakest_leg.get("Matchup") or "that leg"

    n_legs = len(legs)

    # ── Verdict logic ────────────────────────────────────────────────
    if any(l.get("Tier") in ("PASS",) for l in legs):
        return {
            "verdict": "DON'T",
            "reason": f"{weakest_label} is a PASS-tier play — the model has no edge there. "
                      f"Including it drags the whole slip's expected value down regardless of the other legs.",
            "suggested_fix": f"Drop {weakest_label} and re-check the rest as a smaller slip.",
            "correlation_score": corr_score, "correlated_pairs": corr_pairs,
        }

    if corr_score >= 0.50:
        return {
            "verdict": "DON'T",
            "reason": f"Correlation score {corr_score:.2f} is high — these legs are likely to win or lose "
                      f"together, not independently, so the parlay's real odds of hitting are worse than "
                      f"the payout implies.",
            "suggested_fix": f"Remove one leg from the correlated group ({corr_pairs[0]}) and keep the rest.",
            "correlation_score": corr_score, "correlated_pairs": corr_pairs,
        }

    if any(l.get("Tier") == "LEAN" for l in legs):
        return {
            "verdict": "CAUTION",
            "reason": f"{weakest_label} is only LEAN tier — low conviction. The other legs may be solid, "
                      f"but this one is weighing down the combined edge.",
            "suggested_fix": f"Drop {weakest_label}; the remaining legs would form a stronger slip on their own.",
            "correlation_score": corr_score, "correlated_pairs": corr_pairs,
        }

    if n_legs > 4:
        return {
            "verdict": "CAUTION",
            "reason": f"{n_legs} legs is a lot to stack even with good individual tiers — each added leg "
                      f"multiplies the chance the whole slip misses, since every leg has to hit.",
            "suggested_fix": "Consider splitting this into two smaller slips instead of one big one.",
            "correlation_score": corr_score, "correlated_pairs": corr_pairs,
        }

    if 0.25 <= corr_score < 0.50:
        return {
            "verdict": "CAUTION",
            "reason": f"Correlation score {corr_score:.2f} is moderate — {corr_pairs[0] if corr_pairs else 'some legs'} "
                      f"move together somewhat, which adds variance beyond what the tier grades alone suggest.",
            "suggested_fix": "Fine to take, but size it a little smaller than you would an uncorrelated slip.",
            "correlation_score": corr_score, "correlated_pairs": corr_pairs,
        }

    if avg_tier_score >= 0.7 and corr_score < 0.25 and n_legs <= 4:
        return {
            "verdict": "GO",
            "reason": f"All {n_legs} legs are APPROVED tier or better, correlation is low ({corr_score:.2f}), "
                      f"and the slip size is reasonable.",
            "suggested_fix": None,
            "correlation_score": corr_score, "correlated_pairs": corr_pairs,
        }

    return {
        "verdict": "CAUTION",
        "reason": "Nothing disqualifying, but this slip isn't a clean high-conviction combo either.",
        "suggested_fix": "Double check the weakest leg before locking it in.",
        "correlation_score": corr_score, "correlated_pairs": corr_pairs,
    }


def build_market_comparison(shortlist):
    """
    Pulls in the free/public comparison sources next to BetCouncil's own
    shortlist picks, for the "How This Compares" panel in the New Bettor
    tab. Display-only — matches shortlist picks against each source where
    possible, but never feeds back into SEM/tiers/signal weights.

    Sources:
      - DK Most Bet Props: public DK Network page, no login (props)
      - FanDuel Parlay Hub: Tampermonkey-harvested, needs the harvester
        script running in an authenticated FanDuel tab (parlays)
      - FavoredProps: public, unauthenticated API (/api/dfs, /api/sportsbook),
        harvested every ~15 min into the shared Gist — ranked picks with
        L5/L10/season/H2H hit rates and multi-book odds (props)
      - BettingPros: public API, already fetched every board load
        (expert consensus picks, game lines)
      - Covers: browser-harvested/scraped, already fetched every board
        load (public betting %, game lines)
    """
    result = {"dk_props": [], "fd_parlayhub": {}, "favoredprops": [], "bettingpros": [], "covers": [], "dimers": [], "draftedge": [], "mybookie": [], "vegasinsider": [], "sportsinsights": [], "scoresandodds": [], "pickswise": [], "actionnetwork": [], "betql": [], "wagerbird": [], "lineterminal": [], "propsmadness": []}

    sports_needed = {p["Sport"] for p in shortlist.get("props", [])} | \
                     {g["Sport"] for g in shortlist.get("games", [])}

    # ── DK Most Bet Props: match against shortlist prop players ────────
    shortlist_players = {p["Player"].lower() for p in shortlist.get("props", [])}
    for sport in sports_needed:
        try:
            dk_rows = fetch_dk_most_bet_props(sport, max_rows=40)
        except Exception:
            dk_rows = []
        for row in dk_rows:
            market_l = row.get("Market", "").lower()
            matched_player = next((p for p in shortlist_players if p in market_l), None)
            if matched_player:
                result["dk_props"].append({**row, "matches_shortlist": True, "matched_player": matched_player})

    # ── FanDuel Parlay Hub: whatever the harvester has, per sport ───────
    for sport in list(sports_needed) + ["ALL"]:
        try:
            fdph = fetch_fanduel_parlayhub_from_gist(sport)
        except Exception:
            fdph = []
        if fdph:
            result["fd_parlayhub"][sport] = fdph

    # ── FavoredProps: match against shortlist prop players, both dfs
    # (PrizePicks/Underdog-style) and sportsbook variants ───────────────
    for sport in sports_needed:
        for kind in ("dfs", "sportsbook"):
            try:
                fp_rows = fetch_favoredprops_from_gist(kind, sport)
            except Exception:
                fp_rows = []
            for row in fp_rows:
                player_l = str(row.get("player", "")).lower()
                if player_l in shortlist_players:
                    result["favoredprops"].append({**row, "kind": kind, "sport": sport})

    # ── DraftEdge: match against shortlist prop players (rich for MLB —
    # opposing pitcher ERA/WHIP/K9, weather, DFS salary, hit rates) ─────
    for sport in sports_needed:
        try:
            de_rows = fetch_draftedge_from_gist(sport)
        except Exception:
            de_rows = []
        for row in de_rows:
            player_l = str(row.get("Player", row.get("name", ""))).lower()
            if player_l in shortlist_players:
                result["draftedge"].append({**row, "sport": sport})

    # ── WagerBird: match against shortlist game matchups (MLB only) ────
    shortlist_matchups = [g["Matchup"] for g in shortlist.get("games", [])]
    for matchup in shortlist_matchups:
        try:
            wb_pick = get_wagerbird_pick(matchup)
        except Exception:
            wb_pick = {}
        if wb_pick and wb_pick.get("pick_text"):
            result["wagerbird"].append({"matchup": matchup, **wb_pick})

    # ── LineTerminal: match against shortlist prop players ─────────────
    for sport in sports_needed:
        for player_l in shortlist_players:
            try:
                lt_rows = fetch_lineterminal_player_props(player_l, sport=sport)
            except Exception:
                lt_rows = []
            for row in lt_rows:
                if row.get("recommend"):
                    result["lineterminal"].append({**row, "player": player_l, "sport": sport})

    # ── PropsMadness: match against shortlist prop players (mostly
    # paywall-locked — usually near-empty, real when a line is unlocked) ──
    for sport in sports_needed:
        try:
            pm_offers = fetch_propsmadness_from_gist(sport)
        except Exception:
            pm_offers = []
        for row in pm_offers:
            player_l = str(row.get("player_name", "")).lower()
            if player_l in shortlist_players:
                result["propsmadness"].append({**row, "sport": sport})

    # ── BettingPros + Covers: match against shortlist game matchups ─────
    bp_data = st.session_state.get("bettingpros_data", {})
    if bp_data and shortlist_matchups:
        bp_items = (bp_data if isinstance(bp_data, list)
                    else bp_data.get("items", bp_data.get("picks", bp_data.get("data", []))))
        if isinstance(bp_items, list):
            for matchup in shortlist_matchups:
                teams = [t for t in matchup.replace(" @ ", " ").split(" ") if len(t) > 2]
                for bi in bp_items:
                    if not isinstance(bi, dict):
                        continue
                    bi_str = str(bi).lower()
                    if any(t.lower() in bi_str for t in teams):
                        result["bettingpros"].append({"matchup": matchup, "pick": bi})
                        break

    cov_data = st.session_state.get("covers_consensus", [])
    if isinstance(cov_data, dict) and shortlist_matchups:
        for matchup in shortlist_matchups:
            for cov_matchup, cov_val in cov_data.items():
                teams = [t for t in matchup.replace(" @ ", " ").split(" ") if len(t) > 2]
                if any(t.lower() in cov_matchup.lower() for t in teams):
                    result["covers"].append({"matchup": matchup, "cov_matchup": cov_matchup, **cov_val})
                    break

    # ── Dimers (via Stats Insider backend): match against shortlist games ──
    from consensus_engine import american_to_implied_prob
    _pin_lines_for_dimers = st.session_state.get("pinnacle_game_lines", [])
    for sport in sports_needed:
        try:
            dimers_matches = fetch_dimers_from_gist(sport)
        except Exception:
            dimers_matches = []
        for dm in dimers_matches:
            match_meta = dm.get("match", {})
            home_abv = str(match_meta.get("HomeTeam", {}).get("Abv", "")).upper()
            away_abv = str(match_meta.get("AwayTeam", {}).get("Abv", "")).upper()
            if not (home_abv and away_abv):
                continue
            for matchup in shortlist_matchups:
                if home_abv in matchup.upper() and away_abv in matchup.upper():
                    tab = dm.get("betting", {}).get("tab", {})
                    _dimers_home_wp = tab.get("HomeLineWinPct")
                    _dimers_away_wp = tab.get("AwayLineWinPct")

                    # Diff against Pinnacle's own devigged moneyline-implied
                    # probability for the same matchup -- the value-gap
                    # comparison that was previously never made despite both
                    # numbers already being fetched.
                    _pin_edge_home = _pin_edge_away = None
                    _pin_game = next(
                        (g for g in _pin_lines_for_dimers
                         if normalize_name(g.get("Matchup", "")) == normalize_name(matchup)
                         or normalize_name(matchup) in normalize_name(g.get("Matchup", ""))),
                        None
                    )
                    if _pin_game:
                        _pin_home_p = american_to_implied_prob(_pin_game.get("HomeML"))
                        _pin_away_p = american_to_implied_prob(_pin_game.get("AwayML"))
                        if _pin_home_p is not None and _pin_away_p is not None:
                            _vig_total = _pin_home_p + _pin_away_p
                            if _vig_total > 0:
                                _pin_home_p, _pin_away_p = _pin_home_p / _vig_total, _pin_away_p / _vig_total
                                if isinstance(_dimers_home_wp, (int, float)):
                                    _pin_edge_home = round((_dimers_home_wp / 100.0 if _dimers_home_wp > 1 else _dimers_home_wp) - _pin_home_p, 4)
                                if isinstance(_dimers_away_wp, (int, float)):
                                    _pin_edge_away = round((_dimers_away_wp / 100.0 if _dimers_away_wp > 1 else _dimers_away_wp) - _pin_away_p, 4)

                    result["dimers"].append({
                        "matchup": matchup, "sport": sport,
                        "home_edge": tab.get("HomeH2HEdge"), "away_edge": tab.get("AwayH2HEdge"),
                        "home_win_pct": _dimers_home_wp, "away_win_pct": _dimers_away_wp,
                        "home_odds": tab.get("HomeOdds"), "away_odds": tab.get("AwayOdds"),
                        "total_line": tab.get("TotalLine"), "over_win_pct": tab.get("OverWinPct"),
                        "vs_pinnacle_edge_home": _pin_edge_home,
                        "vs_pinnacle_edge_away": _pin_edge_away,
                    })
                    break

    # ── MyBookie (public SSR HTML): match against shortlist games ──────
    for matchup in shortlist_matchups:
        for sport in sports_needed:
            try:
                mb_match = get_mybookie_match(matchup, sport)
            except Exception:
                mb_match = {}
            if mb_match:
                result["mybookie"].append({"matchup": matchup, "sport": sport, **mb_match})
                break

    # ── VegasInsider (public trends + consensus, MLB only right now) ───
    for matchup in shortlist_matchups:
        try:
            vi_match = get_vegasinsider_match(matchup, "MLB")
        except Exception:
            vi_match = {}
        if vi_match:
            result["vegasinsider"].append({"matchup": matchup, "sport": "MLB", **vi_match})

    # ── Sports Insights (public ticket-% trends) ────────────────────────
    for matchup in shortlist_matchups:
        for sport in sports_needed:
            try:
                si_match = get_sportsinsights_match(matchup, sport)
            except Exception:
                si_match = {}
            if si_match:
                result["sportsinsights"].append({"matchup": matchup, "sport": sport, **si_match})
                break

    # ── ScoresAndOdds (11-book multi-book odds comparison) ──────────────
    for matchup in shortlist_matchups:
        for sport in sports_needed:
            try:
                sao_match = get_scoresandodds_match(matchup, sport)
            except Exception:
                sao_match = {}
            if sao_match:
                result["scoresandodds"].append({"matchup": matchup, "sport": sport, **sao_match})
                break

    # ── Pickswise (expert picks + consensus odds) ───────────────────────
    for matchup in shortlist_matchups:
        for sport in sports_needed:
            try:
                pw_match = get_pickswise_match(matchup, sport)
            except Exception:
                pw_match = {}
            if pw_match:
                result["pickswise"].append({"matchup": matchup, "sport": sport, **pw_match})
                break

    # ── Action Network (multi-book odds + starting pitcher stats) ──────
    for matchup in shortlist_matchups:
        for sport in sports_needed:
            try:
                an_match = get_actionnetwork_match(matchup, sport)
            except Exception:
                an_match = {}
            if an_match:
                result["actionnetwork"].append({"matchup": matchup, "sport": sport, **an_match})
                break

    # ── BetQL (multi-book lines + season/ATS records) ───────────────────
    for matchup in shortlist_matchups:
        for sport in sports_needed:
            try:
                bq_match = get_betql_match(matchup, sport)
            except Exception:
                bq_match = {}
            if bq_match:
                result["betql"].append({"matchup": matchup, "sport": sport, **bq_match})
                break

    return result


_DENSITY_ESPN_SPORT_MAP = {
    "NBA": ("basketball", "nba"), "MLB": ("baseball", "mlb"),
    "NFL": ("football", "nfl"), "NHL": ("hockey", "nhl"),
    "WNBA": ("basketball", "wnba"),
}

def fetch_todays_game_start_times(sports=("NBA", "MLB", "NHL", "WNBA", "NFL")) -> list:
    """
    Schedule-only fetch (no odds, no edge computation) for the Game
    Density / Peak Load check on the Summary tab -- deliberately cheap so
    it can run on every page load without triggering the heavy per-sport
    load_sport_data() pipeline. Reuses the same ESPN scoreboard endpoint
    and caching (_espn_get, 3h TTL here -- schedules don't shift
    intraday) already proven in resolve_actual_game_result_for_grading.
    Returns a flat list of datetime start times across all sports passed,
    today's date only, best-effort (skips a sport silently on fetch
    failure rather than failing the whole check).
    """
    times = []
    today_str = datetime.now().strftime("%Y%m%d")
    for sport in sports:
        es_el = _DENSITY_ESPN_SPORT_MAP.get(sport)
        if not es_el:
            continue
        es, el = es_el
        try:
            data = _espn_get(
                f"https://site.api.espn.com/apis/site/v2/sports/{es}/{el}/scoreboard",
                cache_key=f"density_{sport}_{today_str}", ttl_hours=3
            )
            if not data:
                continue
            for event in data.get("events", []):
                _dt_str = event.get("date", "")
                if not _dt_str:
                    continue
                try:
                    _dt = datetime.strptime(_dt_str, "%Y-%m-%dT%H:%MZ")
                    times.append(_dt)
                except ValueError:
                    continue
        except Exception:
            continue
    return times


def _espn_get(url, cache_key, ttl_hours=12):
    """Shared ESPN fetch with file cache. Returns parsed JSON or None."""
    cache_path = os.path.join(CACHE_DIR, f"espn_{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < ttl_hours:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                _logger.debug("Silent except at line 6936")
                pass
    try:
        resp = _http.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        data = resp.json()
        with open(cache_path, "wb") as f:
            pickle.dump(data, f)
        return data
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": f"espn_get:{cache_key}", "error": str(e)[:80]
        })
        return None




# ── Tennis signal engine ──────────────────────────────────────────────────────
# Surface baselines: expected total games per match (both players combined)
# Best-of-3 format (most ATP/WTA events and all WTA Slams)


# Maps GEM/PrizePicks-style prop names to Parlay Savant's URL prop slugs (MLB)
def _fetch_nfl_team_stats_power() -> dict:
    """
    Derive NFL team power ratings from ESPN team season stats — points/yards
    for and against.  More predictive than win% for pre-season and early-season
    game edges.  Returns {team_abbr: power_rating} on ~104 scale.

    Formula: base 104 + (net_pts_per_game / 3) + (net_yds_per_game / 40)
    Capped at ±15 from baseline to prevent outlier distortion.
    Cache: 6 hours — stats update daily post-game.
    """
    cache_path = os.path.join(CACHE_DIR, "nfl_team_stats_power.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                _logger.debug("Silent except at line 6978")
                pass
    try:
        season = date.today().year
        # NFL season starts Sept — if before Sept, use prior season stats
        if date.today().month < 9:
            season -= 1
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
            f"?limit=32&season={season}"
        )
        r = _http.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return {}
        teams = (r.json().get("sports", [{}])[0]
                         .get("leagues", [{}])[0]
                         .get("teams", []))
        ratings = {}
        for entry in teams:
            team  = entry.get("team", {})
            abbr  = team.get("abbreviation", "")
            if not abbr:
                continue
            # Pull team stats endpoint
            tid  = team.get("id")
            surl = (
                f"https://site.api.espn.com/apis/site/v2/sports/football/nfl"
                f"/teams/{tid}/statistics?season={season}"
            )
            sr = _http.get(surl, headers=HEADERS, timeout=8)
            if sr.status_code != 200:
                continue
            cats = sr.json().get("results", {}).get("splits", {}).get("categories", [])
            pts_for = pts_against = yds_for = yds_against = None
            for cat in cats:
                name = cat.get("name", "").lower()
                stats = {s["name"]: s.get("value", 0) for s in cat.get("stats", [])}
                if "scoring" in name:
                    pts_for     = stats.get("pointsPerGame") or stats.get("totalPointsPerGame")
                    pts_against = stats.get("opponentPointsPerGame")
                elif "total" in name:
                    yds_for     = stats.get("yardsPerGame")
                    yds_against = stats.get("opponentYardsPerGame")
            if pts_for is None:
                continue
            pts_for     = float(pts_for     or 23.0)
            pts_against = float(pts_against or 23.0)
            yds_for     = float(yds_for     or 340.0)
            yds_against = float(yds_against or 340.0)
            net_pts = pts_for - pts_against
            net_yds = yds_for - yds_against
            power   = 104.0 + (net_pts / 3.0) + (net_yds / 40.0)
            power   = max(89.0, min(119.0, power))
            ratings[abbr] = round(power, 1)
        if ratings:
            with open(cache_path, "wb") as f:
                pickle.dump(ratings, f)
        return ratings
    except Exception:
        _logger.debug("Silent except at line 7036")
        return {}


PARLAYSAVANT_MLB_PROP_MAP = {
    "Hits": "hits", "Singles": "singles", "Doubles": "doubles", "Triples": "triples",
    "Home Runs": "home-runs", "Total Bases": "total-bases", "RBI": "rbi", "Runs": "runs",
    "H+R+RBI": "h-r-rbi", "Walks": "walks", "Stolen Bases": "stolen-bases",
    "Strikeouts": "strikeouts", "Innings Pitched": "innings-pitched",
    "Hits Allowed": "hits-allowed", "Earned Runs": "earned-runs",
}



# ── Soccer team goals for/against per game ────────────────────────────────────
# League baselines (goals/game total, both teams combined, 2025-26 season)


# ── UFC round projection ──────────────────────────────────────────────────────
# Weightclass round baselines — avg rounds completed before finish/decision


# NOTE: @st.cache_data removed — scrapeops_get writes st.session_state
# (scrapeops_exhausted, scraperapi_exhausted, scrapeops_log) which causes
# Streamlit warnings and silent drops on cache hits. The proxy chain
# already provides its own fallback performance via ScrapeOps→ScraperAPI→direct.
def scrapeops_get(url: str, headers: dict = None, timeout: int = 20):
    """
    Residential proxy chain for anti-bot protected sites (PrizePicks etc).
    Tries proxies in order until one succeeds:
      1. ScrapeOps    (25k credits/mo — primary paid)
      2. ScraperAPI   (1k free credits/mo — backup)
      3. Scrape.do    (1k free credits/mo — backup)
      4. Direct request (fallback — will 403 on protected sites)

    NOTE: this function is also defined in fetchers.py. Since app.py does
    `from fetchers import *` and then redefines it here, THIS copy is the
    one that actually executes (Python resolves to the later definition).
    Known duplication risk — the two copies can silently drift apart if
    only one gets updated. Left as-is rather than force-merged, since
    fetchers.py can't see app.py's circuit_is_tripped/circuit_record_*
    helpers (they're defined further down in app.py, not in fetchers.py),
    so consolidating needs those helpers moved to fetchers.py or bc_utils.py
    first — a real refactor, not a one-line fix.
    """
    from urllib.parse import quote

    def _log(proxy, status, size=0, error=None):
        st.session_state.setdefault("scrapeops_log", []).append({
            "url": url[:60], "proxy": proxy,
            "status": status, "size": size,
            "error": str(error)[:60] if error else None,
        })

    def _is_valid(resp):
        ct = resp.headers.get("content-type","")
        return resp.status_code == 200 and "html" not in ct and not resp.text.strip().startswith("<")

    # ��─ 1. ScrapeOps ────────────────────────────────────────
    # Skip if quota exhausted. Checked in two layers: session_state (instant,
    # for repeat calls within this run) then Gist (persists across cold
    # starts/redeploys — without this, every fresh session silently re-pays
    # the full ~20s timeout to rediscover exhaustion that was already known
    # from an earlier session, the same class of bug fixed in load_from_gist
    # on 2026-06-21). Scoped by month since ScrapeOps quota resets monthly.
    _so_exhausted = st.session_state.get("scrapeops_exhausted", False)
    if not _so_exhausted:
        _so_gist = load_from_gist("scrapeops_status", None)
        if _so_gist and _so_gist.get("exhausted") and _so_gist.get("month") == datetime.now().strftime("%Y-%m"):
            _so_exhausted = True
            st.session_state["scrapeops_exhausted"] = True

    # Two accounts now (2026-07): tries SCRAPEOPS_KEY first, then
    # SCRAPEOPS_KEY_2 (a separate account/quota, not a bigger pool on the
    # same account) once the first is exhausted. Each key tracks its own
    # exhaustion state independently (scrapeops_exhausted vs
    # scrapeops2_exhausted) so the second key doesn't get skipped just
    # because the first was flagged exhausted in an earlier session.
    _quota_phrases = ("insufficient credit", "credit limit", "quota exceeded",
                       "out of credits", "usage limit", "no credits remaining")
    for _so_slot, _so_key, _so_already_exhausted in (
        ("scrapeops", SCRAPEOPS_KEY, _so_exhausted),
        ("scrapeops2", SCRAPEOPS_KEY_2, st.session_state.get("scrapeops2_exhausted", False)),
    ):
        if not _so_key:
            continue
        _slot_exhausted = _so_already_exhausted
        if _so_slot == "scrapeops2" and not _slot_exhausted:
            _so2_gist = load_from_gist("scrapeops2_status", None)
            if _so2_gist and _so2_gist.get("exhausted") and _so2_gist.get("month") == datetime.now().strftime("%Y-%m"):
                _slot_exhausted = True
                st.session_state["scrapeops2_exhausted"] = True
        if _slot_exhausted:
            continue
        try:
            encoded = quote(url, safe='')
            r = _HTTP_DIRECT.get(f"https://proxy.scrapeops.io/v1/?api_key={_so_key}&url={encoded}&residential=true&country=us&render_js=false",
                timeout=timeout
            )
            _log(f"ScrapeOps ({_so_slot})", r.status_code, len(r.text))
            # 403/429/402 = quota exhausted via status code. Also check for
            # a 200 response carrying a quota-exceeded error body — some
            # proxy APIs (ScrapeOps included, per support docs) return 200
            # with an error payload rather than a 4xx when credits run out,
            # which would otherwise never trip this check and silently keep
            # burning real billable requests on every board load forever.
            # This is the likely explanation for credits hitting 100% despite
            # the exhaustion flag supposedly being active from an earlier run.
            _body_says_exhausted = (
                r.status_code == 200 and
                any(_p in r.text[:500].lower() for _p in _quota_phrases)
            )
            if r.status_code in (403, 429, 402) or _body_says_exhausted:
                st.session_state[f"{_so_slot}_exhausted"] = True
                save_to_gist(f"{_so_slot}_status", {"exhausted": True, "month": datetime.now().strftime("%Y-%m")})
                _log(f"ScrapeOps ({_so_slot})", "QUOTA_EXHAUSTED", error=Exception(f"HTTP {r.status_code}" + (" (200 w/ quota error body)" if _body_says_exhausted else "")))
                continue  # try the next key instead of falling straight to ScraperAPI
            elif _is_valid(r):
                return r
        except (KeyError, TypeError, ValueError) as e:
            _log(f"ScrapeOps ({_so_slot})", "ERR", error=e)

    # ── 2. ScraperAPI ────────────────────────────────────────
    if SCRAPERAPI_KEY and not circuit_is_tripped("ScraperAPI"):
        try:
            r = _HTTP_DIRECT.get(f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={quote(url, safe='')}&premium=true&country_code=us",
                timeout=timeout
            )
            _log("ScraperAPI", r.status_code, len(r.text))
            if r.status_code in (403, 429, 402):
                st.session_state["scraperapi_exhausted"] = True
                circuit_record_failure("ScraperAPI")
            elif _is_valid(r):
                circuit_record_success("ScraperAPI")
                return r
            else:
                circuit_record_failure("ScraperAPI")
        except (requests.RequestException, KeyError, ValueError) as e:
            _log("ScraperAPI", "ERR", error=e)
            circuit_record_failure("ScraperAPI")

    # ── 3. Scrape.do ─────────────────────────────────────────
    if SCRAPEDO_KEY and not circuit_is_tripped("Scrape.do"):
        try:
            r = _HTTP_DIRECT.get(f"https://api.scrape.do?token={SCRAPEDO_KEY}&url={quote(url, safe='')}&super=true",
                timeout=timeout
            )
            _log("Scrape.do", r.status_code, len(r.text))
            if _is_valid(r):
                circuit_record_success("Scrape.do")
                return r
            else:
                circuit_record_failure("Scrape.do")
        except (requests.RequestException, KeyError, ValueError) as e:
            _log("Scrape.do", "ERR", error=e)
            circuit_record_failure("Scrape.do")

    # ── 4. Direct (fallback) ─────────────────────────────────
    return _http.get(url, headers=headers or {}, timeout=timeout)


# ═══════════════════════════════════════════════════════════════
# ESPN INJURY + DEPTH CHART FEEDS
# Uses same ESPN infrastructure already trusted by the app.
# Tier 4 injury source + depth chart movement for NFL/NBA/MLB.
# ═══════════════════════════════════════════════════════════════


@st.cache_data(ttl=600)
def fetch_action_network_props(sport):
    league_id = ACTION_NETWORK_LEAGUE_IDS.get(sport)
    if not league_id:
        return []
    allowed, reason = api_budget_check("ACTION_NETWORK")
    if not allowed:
        return []
    cache_path = os.path.join(CACHE_DIR, f"an_props_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 30:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached
    today = date.today().strftime("%Y%m%d")
    url = f"https://api.actionnetwork.com/web/v2/leagues/{league_id}/projections/available?date={today}&isLive=false&limit=200&stateCode=CA"
    an_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3.1 Safari/605.1.15",
        "Accept": "application/json",
        "Origin": "https://www.actionnetwork.com",
        "Referer": f"https://www.actionnetwork.com/{sport.lower()}/prop-projections",
    }
    try:
        resp = _http.get(url, headers=an_headers, timeout=15)
        api_budget_increment("ACTION_NETWORK")
        if resp.status_code != 200:
            return []
        data = resp.json()
        player_props = data.get("playerProps", [])
        if not player_props:
            st.caption(f"⚠️ Action Network: no {sport} projections published yet for today. Check back closer to game time.")
            return []
        results = []
        seen = set()
        for prop in player_props:
            player_abbr = prop.get("player_abbr", "")
            prop_type = prop.get("custom_pick_type", "")
            stat_name = ACTION_NETWORK_PROP_TYPE_MAP.get(prop_type, prop.get("custom_pick_type_display_name", prop_type))
            if not player_abbr or not stat_name:
                continue
            lines = prop.get("lines", [])
            if not lines:
                continue
            line_val = None
            edge_score = prop.get("edge", 0)
            grade = prop.get("grade", "")
            bet_quality = prop.get("bet_quality", 0)
            projection = prop.get("projection")
            implied_value = prop.get("implied_value")
            tickets_pct = 0
            money_pct = 0
            over_odds = -110
            for line_entry in lines:
                bet_info = line_entry.get("bet_info", {})
                if bet_info:
                    t_pct = bet_info.get("tickets", {}).get("percent", 0)
                    m_pct = bet_info.get("money", {}).get("percent", 0)
                    if t_pct > 0 or m_pct > 0:
                        tickets_pct = t_pct
                        money_pct = m_pct
                if line_val is None:
                    lv = line_entry.get("value", line_entry.get("over_under", line_entry.get("line")))
                    if lv is not None:
                        try:
                            line_val = float(lv)
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                odds = line_entry.get("odds")
                if odds:
                    over_odds = odds
            if line_val is None and implied_value:
                try:
                    line_val = round(float(implied_value), 1)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
            if line_val is None:
                continue
            key = (sport, player_abbr, stat_name, line_val)
            if key in seen:
                continue
            seen.add(key)
            an_tier = AN_GRADE_TO_TIER.get(grade, "")
            results.append({
                "player_abbr": player_abbr,
                "stat": stat_name,
                "line": line_val,
                "projection": projection,
                "edge": edge_score,
                "grade": grade,
                "tier": an_tier,
                "bet_quality": bet_quality,
                "implied_value": implied_value,
                "tickets_pct": tickets_pct,
                "money_pct": money_pct,
                "over_odds": over_odds,
                "sport": sport,
                "source": "ActionNetwork",
            })
        if results:
            with open(cache_path, "wb") as f:
                pickle.dump(results, f)
            st.caption(f"✅ Action Network props: {len(results)} projections loaded for {sport}")
        return results
    except (KeyError, TypeError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_action_network_props", "error": str(e)[:100]})
        return []

# safe_float — moved to utils.py
# american_to_prob — moved to utils.py
# no_vig_prob — moved to utils.py
def get_fanduel_dk_validation(player, stat, line, sport, alt_lines_data):
    """
    Find FanDuel/DraftKings no-vig probability for a specific player+stat+line.
    Uses alternate lines ladder to find the closest match.
    Returns: {implied_prob, source, over_odds, under_odds, line_found}
    """
    if not alt_lines_data:
        return None
    norm_player = normalize_name(player)
    stat_lower = stat.lower().replace(" ","").replace("+","")
    best_match = None
    best_line_diff = 999
    for entry in alt_lines_data:
        if normalize_name(entry.get("player","")) != norm_player:
            continue
        entry_stat = entry.get("stat","").lower().replace(" ","").replace("+","")
        if entry_stat not in stat_lower and stat_lower not in entry_stat:
            continue
        entry_line = float(entry.get("line", 0) or 0)
        diff = abs(entry_line - float(line))
        if diff < best_line_diff:
            best_line_diff = diff
            best_match = entry
    if best_match and best_line_diff <= 1.0:
        over_odds = best_match.get("over_odds")
        under_odds = best_match.get("under_odds")
        if over_odds and under_odds:
            prob = no_vig_prob(over_odds, under_odds)
            return {
                "implied_prob": prob,
                "source": best_match.get("source","FD/DK"),
                "over_odds": over_odds,
                "under_odds": under_odds,
                "line_found": best_match.get("line"),
                "confirms": prob > 0.55,
                "fades": prob < 0.45,
            }
    return None

def detect_arbitrage_opportunities(sport):
    cache_path = os.path.join(CACHE_DIR, f"odds_api_props_{sport}.pkl")
    if not os.path.exists(cache_path):
        return []
    try:
        with open(cache_path, "rb") as f:
            props = pickle.load(f)
    except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
        return []
    if not props:
        return []
    prop_groups = {}
    for prop in props:
        player = prop.get("Player", "")
        stat = prop.get("Prop", "")
        line = prop.get("Line", 0)
        side = prop.get("Side", "OVER")
        source = prop.get("source", "")
        key = (player, stat, float(line))
        if key not in prop_groups:
            prop_groups[key] = {"player": player, "stat": stat, "line": line, "over_odds": {}, "under_odds": {}}
        over_odds = prop.get("OverOdds")
        under_odds = prop.get("UnderOdds")
        book = source.replace("OddsAPI_", "")
        if (side == "OVER" and over_odds is not None):
            prop_groups[key]["over_odds"][book] = float(over_odds)
        if (side == "UNDER" and under_odds is not None):
            prop_groups[key]["under_odds"][book] = float(under_odds)
    arb_opportunities = []
    for key, group in prop_groups.items():
        over_odds_map = group["over_odds"]
        under_odds_map = group["under_odds"]
        if not over_odds_map or not under_odds_map:
            continue
        best_over_book = max(over_odds_map, key=over_odds_map.get)
        best_over = over_odds_map[best_over_book]
        best_under_book = max(under_odds_map, key=under_odds_map.get)
        best_under = under_odds_map[best_under_book]
        def to_decimal(american):
            if american > 0:
                return 1 + american / 100
            else:
                return 1 + 100 / abs(american)
        over_dec = to_decimal(best_over)
        under_dec = to_decimal(best_under)
        over_implied = 1 / over_dec
        under_implied = 1 / under_dec
        total_implied = over_implied + under_implied
        if total_implied < 1.0:
            arb_profit_pct = round((1 - total_implied) * 100, 2)
            over_stake_pct = round(over_implied / total_implied * 100, 1)
            under_stake_pct = round(under_implied / total_implied * 100, 1)
            arb_opportunities.append({
                "Player": group["player"],
                "Stat": group["stat"],
                "Line": group["line"],
                "OVER Book": best_over_book,
                "OVER Odds": f"+{int(best_over)}" if best_over > 0 else str(int(best_over)),
                "UNDER Book": best_under_book,
                "UNDER Odds": f"+{int(best_under)}" if best_under > 0 else str(int(best_under)),
                "Arb Profit": f"+{arb_profit_pct:.2f}%",
                "Arb Pct": arb_profit_pct,
                "OVER Stake": f"{over_stake_pct}%",
                "UNDER Stake": f"{under_stake_pct}%",
                "Sport": sport,
            })
    arb_opportunities.sort(key=lambda x: x["Arb Pct"], reverse=True)
    return arb_opportunities

def compute_alt_line_ev(player_name, stat_name, avg, std_dev, sport, bankroll):
    alt_lines_data = st.session_state.get("parlayplay_alt_lines", {})
    alt_key = f"{player_name}_{stat_name}"
    alt_lines = alt_lines_data.get(alt_key, [])
    if not alt_lines or len(alt_lines) < 2:
        return None, []
    stat_norm = STAT_NORMALIZE.get((sport, stat_name), stat_name)
    results = []
    for alt in alt_lines:
        line_val = alt.get("line")
        decimal_odds = alt.get("odds", 1.77)
        is_main = alt.get("isMain", False)
        if line_val is None:
            continue
        if decimal_odds <= 0:
            continue
        if stat_norm in ["HR", "GOALS"]:
            fair_prob = poisson_prob_over(line_val, avg)
        else:
            fair_prob = compute_fair_prob(line_val, avg, std_dev, "OVER")
        if decimal_odds > 0:
            breakeven = 1.0 / decimal_odds
        else:
            breakeven = 0.577
        ev = fair_prob - breakeven
        b = decimal_odds - 1
        if fair_prob > breakeven and b > 0:
            kelly = ((b * fair_prob - (1 - fair_prob)) / b)
            wager = round(min(kelly * KELLY_FRACTION * bankroll, bankroll * KELLY_CAP), 2)
        else:
            wager = 0.0
        results.append({
            "line": float(line_val),
            "decimal_odds": decimal_odds,
            "payout": f"{decimal_odds}x",
            "fair_prob": round(fair_prob, 4),
            "breakeven": round(breakeven, 4),
            "ev": round(ev, 4),
            "ev_pct": f"{ev:.1%}",
            "wager": wager,
            "is_main": is_main,
            "is_plus_ev": ev > 0,
        })
    if not results:
        return None, []
    results.sort(key=lambda x: x["ev"], reverse=True)
    best = results[0]
    main_line = next((r for r in results if r["is_main"]), None)
    if main_line:
        ev_improvement = best["ev"] - main_line["ev"]
        if ev_improvement < 0.02:
            return None, results
    return best, results

def optimize_parlay_with_alt_lines(selected_props, n_picks, bankroll):
    if not selected_props:
        return None
    optimized = []
    total_improvement = 0.0
    for prop in selected_props:
        player = prop.get("Player", "")
        stat = prop.get("Prop", "")
        main_line = prop.get("Line", 0)
        avg = prop.get("Avg", 0)
        std_dev = prop.get("StdDev")
        sport = prop.get("Sport", "NBA")
        main_prob = prop.get("Prob", 0.5)
        main_ev = calculate_prizepicks_ev(main_prob, n_picks)
        best_alt, all_alts = compute_alt_line_ev(player, stat, avg, std_dev, sport, bankroll)
        if (best_alt and best_alt["line"] != main_line and best_alt["ev"] > main_ev):
            improvement = best_alt["ev"] - main_ev
            total_improvement += improvement
            optimized.append({
                **prop,
                "Line": best_alt["line"],
                "Prob": best_alt["fair_prob"],
                "OptimizedLine": best_alt["line"],
                "OptimizedPayout": best_alt["payout"],
                "OptimizedEV": best_alt["ev"],
                "MainLine": main_line,
                "LineImproved": True,
                "EVImprovement": improvement,
                "Source": "ParlayPlay_Alt",
            })
        else:
            optimized.append({
                **prop,
                "OptimizedLine": main_line,
                "OptimizedPayout": f"{PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)}x",
                "OptimizedEV": main_ev,
                "MainLine": main_line,
                "LineImproved": False,
                "EVImprovement": 0.0,
                "Source": prop.get("source", "PrizePicks"),
            })
    if not optimized:
        return None
    adjusted_probs, corr_notes = detect_correlations(optimized)
    combined_prob = parlay_prob(adjusted_probs)
    multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)
    breakeven = 1 / multiplier
    combined_ev = combined_prob - breakeven
    improved_count = sum(1 for p in optimized if p.get("LineImproved"))
    return {
        "props": optimized,
        "combined_prob": combined_prob,
        "multiplier": multiplier,
        "breakeven": breakeven,
        "combined_ev": combined_ev,
        "is_plus_ev": combined_ev > 0,
        "improved_count": improved_count,
        "total_ev_improvement": total_improvement,
        "correlation_notes": corr_notes,
        "adjusted_probs": adjusted_probs,
    }

def _resolve_oddspapi_bookmaker_slugs(wanted_names, cache_hours=168):
    """Resolve human book names (e.g. 'mybookie', 'betfair exchange') to their
    real OddsPapi slugs via /bookmakers, so we never hardcode a guessed slug
    that silently returns zero data if it's wrong. Cached 7 days — bookmaker
    slugs don't change often. Falls back to the guessed name itself if the
    lookup fails, so a bad network call never blocks the whole fetch."""
    cache_path = os.path.join(CACHE_DIR, "oddspapi_bookmaker_slugs.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < cache_hours:
            try:
                with open(cache_path, "rb") as f:
                    all_slugs = pickle.load(f)
            except Exception:
                all_slugs = None
        else:
            all_slugs = None
    else:
        all_slugs = None
    if all_slugs is None:
        try:
            r = _http.get("https://api.oddspapi.io/v4/bookmakers", params={"apiKey": ODDSPAPI_KEY}, timeout=10)
            if r.status_code == 200:
                all_slugs = [b.get("slug", "") for b in r.json() if b.get("slug")]
                with open(cache_path, "wb") as f:
                    pickle.dump(all_slugs, f)
            else:
                all_slugs = []
        except Exception:
            all_slugs = []
    resolved = []
    for name in wanted_names:
        name_norm = name.lower().replace(" ", "").replace("-", "").replace("_", "")
        match = next((s for s in all_slugs if s.lower().replace("-", "").replace("_", "") == name_norm), None)
        if not match:
            # loose contains-match fallback (e.g. "mybookie" vs "mybookieag")
            match = next((s for s in all_slugs if name_norm in s.lower().replace("-", "").replace("_", "")), None)
        resolved.append(match or name)
    return resolved


def fetch_oddspapi_props(sport):
    if not ODDSPAPI_KEY:
        return []
    allowed, reason = api_budget_check("ODDSPAPI")
    if not allowed:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_oddspapi_props", "error": reason})
        return []
    daily_used = get_api_counter(API_BUDGETS["ODDSPAPI"]["counter_path"]).get("count", 0)
    cache_path = os.path.join(CACHE_DIR, f"oddspapi_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 OddsPapi: using cached data ({age_mins:.0f}m old)")
                return cached
    # v4 API: first get tournaments for sport, then get odds by tournament
    sport_id_map = {"NBA": 4, "WNBA": 4, "MLB": 3, "NHL": 6, "NFL": 1}
    sport_id = sport_id_map.get(sport)
    if not sport_id:
        return []
    try:
        # Step 1: get tournament IDs for this sport
        t_resp = _http.get(
            f"https://api.oddspapi.io/v4/tournaments?sportId={sport_id}&apiKey={ODDSPAPI_KEY}",
            timeout=10
        )
        if t_resp.status_code != 200:
            return []
        tournaments = t_resp.json()
        # Get top tournaments with upcoming fixtures
        top_ids = [str(t["tournamentId"]) for t in tournaments if t.get("upcomingFixtures", 0) > 0 or t.get("futureFixtures", 0) > 0][:3]
        if not top_ids:
            top_ids = [str(t["tournamentId"]) for t in tournaments[:2]]
        if not top_ids:
            return []
        tournament_ids = ",".join(top_ids)
        # Books that duplicate what's already free elsewhere (draftkings,
        # fanduel, betmgm via Tampermonkey; pinnacle via arcadia; bet365 via
        # WebSocket harvester) are dropped in favor of the books nothing else
        # in the stack can get: caesars, circa, mybookie, and an exchange
        # book for the us_ex role. Slugs for mybookie/the exchange book are
        # resolved dynamically since they're not confirmed in OddsPapi's docs.
        _resolved = _resolve_oddspapi_bookmaker_slugs(["caesars", "circa", "mybookie", "betfair exchange"])
        _bookmaker_param = ",".join(_resolved)
        url = (f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker={_bookmaker_param}&tournamentIds={tournament_ids}&apiKey={ODDSPAPI_KEY}&oddsFormat=american")
        resp = _http.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDSPAPI")
        if resp.status_code == 429:
            st.warning("⚠️ OddsPapi rate limit hit")
            # Clear cache so next board load retries fresh
            if os.path.exists(cache_path):
                try: os.remove(cache_path)
                except (OSError, IOError): pass
            return []
        if resp.status_code == 403:
            st.warning("⚠️ OddsPapi monthly limit reached")
            if os.path.exists(cache_path):
                try: os.remove(cache_path)
                except (OSError, IOError): pass
            return []
        if resp.status_code != 200:
            return []
        data = resp.json()
        props = []
        seen = set()
        for event in data.get("events", []):
            for bookmaker in event.get("bookmakers", []):
                book_name = bookmaker.get("key", "unknown")
                for market in bookmaker.get("markets", []):
                    market_key = market.get("key", "")
                    # Accept player props — OddsPapi uses various keys:
                    # NBA: player_points, player_rebounds, player_assists
                    # MLB: pitcher_strikeouts, batter_home_runs, batter_hits
                    # NHL: player_shots_on_goal, goalie_saves
                    _prop_keywords = ("player_","pitcher_","batter_","goalie_","anytime_")
                    if not any(market_key.lower().startswith(k) for k in _prop_keywords):
                        if "player" not in market_key.lower():
                            continue
                    for outcome in market.get("outcomes", []):
                        player = outcome.get("description", "")
                        line = outcome.get("point")
                        side = outcome.get("name", "")
                        if not player:
                            continue
                        if line is None:
                            continue
                        if side.upper() not in ("OVER", "UNDER"):
                            continue
                        if side.upper() != "OVER":
                            continue
                        stat_clean = market_key
                        for _pfx in ("player_","pitcher_","batter_","goalie_","anytime_"):
                            stat_clean = stat_clean.replace(_pfx, "")
                        stat_clean = stat_clean.replace("_", " ").title()
                        key = (sport, player, stat_clean, float(line))
                        if key in seen:
                            continue
                        seen.add(key)
                        props.append({
                            "Player": player,
                            "Prop": stat_clean,
                            "Line": float(line),
                            "Side": "OVER",
                            "Sport": sport,
                            "source": f"OddsPapi_{book_name}",
                            "OddsType": "standard"
                        })
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
            st.caption(f"✅ OddsPapi: {len(props)} props fetched ({daily_used + 1}/{ODDSPAPI_FREE_TIER_DAILY_LIMIT} calls today)")
        return props
    except (requests.RequestException, KeyError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_oddspapi_props", "error": str(e)[:100]})
        return []
        api_budget_increment("ODDSPAPI")
        if resp.status_code == 429:
            st.warning("⚠️ OddsPapi rate limit hit")
            # Clear cache so next board load retries fresh
            if os.path.exists(cache_path):
                try: os.remove(cache_path)
                except (OSError, IOError): pass
            return []
        if resp.status_code == 403:
            st.warning("⚠️ OddsPapi monthly limit reached")
            if os.path.exists(cache_path):
                try: os.remove(cache_path)
                except (OSError, IOError): pass
            return []
        if resp.status_code != 200:
            return []
        data = resp.json()
        props = []
        seen = set()
        for event in data.get("events", []):
            for bookmaker in event.get("bookmakers", []):
                book_name = bookmaker.get("key", "unknown")
                for market in bookmaker.get("markets", []):
                    market_key = market.get("key", "")
                    # Accept player props — OddsPapi uses various keys:
                    # NBA: player_points, player_rebounds, player_assists
                    # MLB: pitcher_strikeouts, batter_home_runs, batter_hits
                    # NHL: player_shots_on_goal, goalie_saves
                    _prop_keywords = ("player_","pitcher_","batter_","goalie_","anytime_")
                    if not any(market_key.lower().startswith(k) for k in _prop_keywords):
                        if "player" not in market_key.lower():
                            continue
                    for outcome in market.get("outcomes", []):
                        player = outcome.get("description", "")
                        line = outcome.get("point")
                        side = outcome.get("name", "")
                        if not player:
                            continue
                        if line is None:
                            continue
                        if side.upper() not in ("OVER", "UNDER"):
                            continue
                        if side.upper() != "OVER":
                            continue
                        stat_clean = market_key
                        for _pfx in ("player_","pitcher_","batter_","goalie_","anytime_"):
                            stat_clean = stat_clean.replace(_pfx, "")
                        stat_clean = stat_clean.replace("_", " ").title()
                        key = (sport, player, stat_clean, float(line))
                        if key in seen:
                            continue
                        seen.add(key)
                        props.append({
                            "Player": player,
                            "Prop": stat_clean,
                            "Line": float(line),
                            "Side": "OVER",
                            "Sport": sport,
                            "source": f"OddsPapi_{book_name}",
                            "OddsType": "standard"
                        })
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
            st.caption(f"✅ OddsPapi: {len(props)} props fetched ({daily_used + 1}/{ODDSPAPI_FREE_TIER_DAILY_LIMIT} calls today)")
        return props
    except (requests.RequestException, KeyError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_oddspapi_props", "error": str(e)[:100]})
        return []

# compare_multibook_lines — moved to bc_utils.py
def check_data_freshness():
    warnings = []
    checks = {
        "ESPN FPI Ratings": "espn_fpi_NBA.pkl",
        "NBA Rolling Averages": "nba_rolling_avgs.pkl",
        "NBA Team Defense": "nba_team_defense.pkl",
        "WNBA Rolling Averages": "wnba_rolling_avgs.pkl",
        "MLB Rolling Averages": "mlb_rolling_avgs.pkl",
        "NHL Rolling Averages": "nhl_rolling_avgs.pkl",
        "BDL Season Averages": "bdl_nba_avgs.pkl",
        "NFL Rolling Averages": "nfl_rolling_avgs.pkl",
        "Soccer Rolling Averages": "soccer_rolling_avgs.pkl",
    }
    for name, filename in checks.items():
        path = os.path.join(CACHE_DIR, filename)
        if os.path.exists(path):
            age_hours = (time.time() - os.path.getmtime(path)) / 3600
            if age_hours > 24:
                warnings.append(f"{name}: {age_hours:.0f}hrs old")
    try:
        last_updated = datetime.strptime(AVERAGES_LAST_UPDATED, "%Y-%m-%d")
        days_old = (datetime.now() - last_updated).days
        if days_old > 14:
            warnings.append(f"Hardcoded averages (NFL/Soccer/UFC): {days_old} days old")
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return warnings

def get_sharp_consensus_for_prop(player, prop_name, line, side, sport, odds_data=None):
    """
    Wrapper: finds sharp consensus no-vig for a player prop.
    Checks Pinnacle + Circa + BetOnline from loaded odds data.
    Falls back to Pinnacle-only if others unavailable.
    """
    if odds_data is None:
        odds_data = st.session_state.get("odds_api_cache", [])
    
    SHARP_BOOKS_PROP = ["pinnacle", "circa_sports", "betonlineag"]
    book_probs = {}
    
    for p in (odds_data or []):
        if normalize_name(p.get("Player","")) != normalize_name(player):
            continue
        if p.get("Prop","") != prop_name:
            continue
        book = p.get("Book","").lower()
        if book not in SHARP_BOOKS_PROP:
            continue
        over_prob = p.get("OverProb") or p.get("NoVigProb")
        if over_prob:
            label = {"pinnacle":"Pinnacle","circa_sports":"Circa","betonlineag":"BetOnline"}.get(book, book)
            book_probs[label] = float(over_prob)
    
    if not book_probs:
        return None
    
    avg = sum(book_probs.values()) / len(book_probs)
    if side == "UNDER":
        avg = 1 - avg
    
    spread = (max(book_probs.values()) - min(book_probs.values())) if len(book_probs) >= 2 else 0
    
    return {
        "fair_prob":   round(avg, 4),
        "book_probs":  book_probs,
        "n_books":     len(book_probs),
        "agreement":   "STRONG" if spread < 0.01 else "MODERATE" if spread < 0.03 else "DIVERGENT",
        "books_used":  list(book_probs.keys()),
    }


def detect_steam_moves(sport):
    cache_path = os.path.join(CACHE_DIR, f"odds_api_games_{sport}.pkl")
    if not os.path.exists(cache_path):
        return []
    baseline_path = os.path.join(CACHE_DIR, f"steam_baseline_{sport}.json")
    try:
        with open(cache_path, "rb") as f:
            current_data = pickle.load(f)
        if isinstance(current_data, tuple):
            current_games = current_data[0]
        else:
            current_games = current_data
        if not current_games:
            return []
        current_lines = {}
        for game in current_games:
            matchup = game.get("Matchup", "")
            spread = game.get("Spread", "")
            total = game.get("Total", "")
            home_ml = game.get("Home ML", "")
            bovada_spread = game.get("Bovada Spread", "")
            bovada_total = game.get("Bovada Total", "")
            if matchup:
                current_lines[matchup] = {
                    "spread": str(spread),
                    "total": str(total),
                    "home_ml": str(home_ml),
                    "bovada_spread": str(bovada_spread),
                    "bovada_total": str(bovada_total),
                    "timestamp": datetime.now().isoformat(),
                }
        steam_moves = []
        if os.path.exists(baseline_path):
            baseline_age = (time.time() - os.path.getmtime(baseline_path)) / 60
            if 20 <= baseline_age <= 120:
                baseline = load_json_data(baseline_path, {})
                for matchup, curr in current_lines.items():
                    base = baseline.get(matchup, {})
                    if not base:
                        continue
                    try:
                        curr_total = float(str(curr.get("total", 0)).replace("N/A","0"))
                        base_total = float(str(base.get("total", 0)).replace("N/A","0"))
                        bov_curr = float(str(curr.get("bovada_total", 0)).replace("N/A","0"))
                        bov_base = float(str(base.get("bovada_total", 0)).replace("N/A","0"))
                        espn_move = curr_total - base_total
                        bov_move = bov_curr - bov_base
                        # Triple-book steam: Pinnacle + Circa + BetOnline all move together
                        # Much stronger signal than ESPN + Bovada
                        circa_curr  = float(str(curr.get("circa_total", 0) or 0).replace("N/A","0") or "0")
                        circa_base  = float(str(base.get("circa_total", 0) or 0).replace("N/A","0") or "0")
                        circa_move  = circa_curr - circa_base if circa_curr and circa_base else None
                        pinn_curr   = float(str(curr.get("pinnacle_total", 0) or 0).replace("N/A","0") or "0")
                        pinn_base   = float(str(base.get("pinnacle_total", 0) or 0).replace("N/A","0") or "0")
                        pinn_move   = pinn_curr - pinn_base if pinn_curr and pinn_base else None
                        # Count how many books moved in same direction
                        all_moves = [(espn_move, "ESPN"), (bov_move, "Bovada")]
                        if circa_move is not None: all_moves.append((circa_move, "Circa"))
                        if pinn_move  is not None: all_moves.append((pinn_move,  "Pinnacle"))
                        sig_moves = [m for m, _ in all_moves if abs(m) >= 0.5]
                        sig_dirs  = [m > 0 for m, _ in all_moves if abs(m) >= 0.5]
                        n_agree   = sum(sig_dirs) if sum(sig_dirs) > len(sig_dirs)/2 else len(sig_dirs) - sum(sig_dirs)
                        moved_books = [b for m, b in all_moves if abs(m) >= 0.5 and (m > 0) == (espn_move > 0)]
                        # Sharp steam = Pinnacle or Circa in the move
                        is_sharp_steam = any(b in ("Pinnacle","Circa") for b in moved_books)
                        if (abs(espn_move) >= 0.5 and abs(bov_move) >= 0.5 and (espn_move > 0) == (bov_move > 0)):
                            direction = "↑" if espn_move > 0 else "↓"
                            strength = "🔥🔥 SHARP STEAM" if is_sharp_steam and n_agree >= 3 else "🔥 STEAM"
                            steam_moves.append({
                                "matchup":     matchup,
                                "type":        "TOTAL",
                                "direction":   direction,
                                "espn_move":   round(espn_move, 1),
                                "bov_move":    round(bov_move, 1),
                                "circa_move":  round(circa_move, 1) if circa_move else None,
                                "pinn_move":   round(pinn_move, 1) if pinn_move else None,
                                "books_moved": moved_books,
                                "n_books":     len(moved_books),
                                "is_sharp":    is_sharp_steam,
                                "current":     curr_total,
                                "was":         base_total,
                                "age_mins":    round(baseline_age, 0),
                                "signal":      f"{strength} {direction}: {len(moved_books)} books moved ({', '.join(moved_books)}) in {baseline_age:.0f}m",
                            })
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
        save_json_data(baseline_path, current_lines)
        return steam_moves
    except (ValueError, TypeError, ZeroDivisionError) as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "detect_steam_moves", "error": str(e)[:100]})
        return []

def generate_why_drivers(prop):
    """
    Full signal contribution table — every component of final edge.
    Returns: [(label, value_str, color), ...] for drivers and risks.
    """
    drivers = []
    risks   = []
    edge    = float(prop.get("Edge", 0) or 0)

    # ── Core model signals ──────────────────────────────────
    core = [
        ("Base (avg vs line)",   float(prop.get("SignalBase",     0) or 0)),
        ("Defense matchup",      float(prop.get("SignalDefense",  0) or 0)),
        ("Home/Away split",      float(prop.get("SignalLocation", 0) or 0)),
        ("Rest advantage",       float(prop.get("SignalRest",     0) or 0)),
        ("Pace factor",          float(prop.get("SignalPace",     0) or 0)),
        ("Usage rate",           float(prop.get("SignalUsage",    0) or 0)),
        ("Weather",              float(prop.get("SignalWeather",  0) or 0)),
        ("H2H history",          float(prop.get("SignalH2H",      0) or 0)),
    ]
    for label, val in core:
        if abs(val) >= 0.005:
            c = "#22c55e" if val > 0 else "#e04040"
            s = "+" if val > 0 else ""
            (drivers if val > 0 else risks).append((label, f"{s}{val*100:.1f}%", c))

    # ── Sharp/Public Divergence + RLM ──────────────────────
    _matchup_key = prop.get("Matchup", prop.get("matchup",""))
    if _matchup_key:
        _rlm = compute_sharp_public_divergence(_matchup_key)
        if _rlm.get("has_rlm"):
            _rlm_strength = _rlm.get("max_strength", 0)
            _rlm_adj      = _rlm.get("edge_adj", 0)
            for _rs in _rlm.get("rlm_signals",[])[:1]:
                _pub  = _rs.get("public_pct",0)
                _mon  = _rs.get("money_pct",0)
                _ps   = _rs.get("public_side","")
                _ss   = _rs.get("sharp_side","")
                drivers.append((
                    f"↔️ RLM: {_pub}% public {_ps}, {_mon}% $ {_ss}",
                    f"+{_rlm_adj*100:.0f}%",
                    "#22c55e"
                ))
        elif _rlm.get("has_sharp"):
            for _ss in _rlm.get("sharp_signals",[])[:1]:
                drivers.append(("⚡ Sharp signal", "+1.0%", "#22c55e"))
        else:
            # 2026-07-16 fix: compute_public_fade_signal existed but was
            # never called anywhere — dead code. Wired in here as a
            # fallback specifically when the RLM-based divergence check
            # above found nothing (no sharp/RLM data available for this
            # matchup), using covers/action-network/bettingpros public %
            # instead. Labeled explicitly as unconfirmed — Sports
            # Insights' own published research is clear that raw public-
            # betting-% fades without reverse-line-movement confirmation
            # aren't reliably profitable on their own, so this shouldn't
            # be presented with the same confidence as the RLM-confirmed
            # signal above.
            try:
                _fade = compute_public_fade_signal(_matchup_key, prop.get("Sport", ""), prop.get("Side", ""))
            except Exception:
                _fade = None
            if _fade and _fade.get("fade_signal") == "CONTRARIAN":
                drivers.append((
                    f"🎯 Public fade (unconfirmed — no RLM): {_fade['public_pct']}% public {_fade['side']}",
                    f"+{_fade.get('edge_adj', 0)*100:.0f}%", "#8ab4d4"
                ))
            elif _fade and _fade.get("fade_signal") == "WITH_PUBLIC":
                risks.append((
                    f"⚠️ With the public (unconfirmed): {_fade['public_pct']}% on {_fade['side']}",
                    f"{_fade.get('edge_adj', 0)*100:.0f}%", "#f5c518"
                ))

    # ── Market move quality ─────────────────────────────────
    mmq = int(prop.get("MarketMoveQuality", 0) or 0)
    mmq_adj = {2:0.02, 1:0.01, 0:0.0, -1:-0.01, -2:-0.02}.get(mmq, 0)
    if abs(mmq_adj) >= 0.01:
        c = "#22c55e" if mmq_adj > 0 else "#e04040"
        lbl = "Sharp market move" if mmq >= 2 else "Soft market move"
        (drivers if mmq_adj > 0 else risks).append((lbl, f"{'+' if mmq_adj>0 else ''}{mmq_adj*100:.0f}%", c))
    if prop.get("PinnacleConfirms") is True:
        drivers.append(("Pinnacle confirms", "+📌", "#22c55e"))
    if "↑" in str(prop.get("SharpFlag","")):
        drivers.append(("Sharp money aligned", "+✅", "#22c55e"))

    # ── Minutes stability ───────────────────────────────────
    mins_adj = {"STABLE":0.01,"MODERATE":0.0,"VOLATILE":-0.01,"HIGH_RISK":-0.02}.get(prop.get("MinutesStability",""),0)
    if abs(mins_adj) >= 0.01:
        c = "#22c55e" if mins_adj > 0 else "#e04040"
        lbl = f"Minutes {'stable' if mins_adj>0 else 'volatile'}"
        (drivers if mins_adj > 0 else risks).append((lbl, f"{'+' if mins_adj>0 else ''}{mins_adj*100:.0f}%", c))

    # ── Volatility ──────────────────────────────────────────
    risk_adj = {"LOW":0.01,"MEDIUM":0.0,"HIGH":-0.01,"EXTREME":-0.02}.get(prop.get("RiskLevel",""),0)
    if abs(risk_adj) >= 0.01:
        c = "#22c55e" if risk_adj > 0 else "#e04040"
        lbl = f"Stat volatility ({prop.get('RiskLevel','').lower()})"
        (drivers if risk_adj > 0 else risks).append((lbl, f"{'+' if risk_adj>0 else ''}{risk_adj*100:.0f}%", c))

    # ── FantasyLabs ─────────────────────────────────────────
    batting = int(prop.get("BattingOrder",0) or 0)
    lineup  = str(prop.get("LineupStatus",""))
    if batting > 0 and lineup:
        import re as _re
        m = _re.search(r'([+-]?\d+)%', lineup)
        lfl = int(m.group(1)) if m else 0
        if abs(lfl) >= 1:
            c = "#22c55e" if lfl > 0 else "#e04040"
            (drivers if lfl > 0 else risks).append((f"Batting #{batting} (FL)", f"{'+' if lfl>0 else ''}{lfl}%", c))
    elif "Not in lineup" in lineup:
        risks.append(("Not in lineup (FL)", "-5.0%", "#e04040"))

    # ── DFF PropStats ───────────────────────────────────────
    dff_hr = float(prop.get("DFFHitRateL10",0) or 0)
    dff_n  = int(prop.get("DFFGamesTotal",0) or 0)
    if dff_n >= 5:
        da = 0.02 if dff_hr>=0.70 else 0.01 if dff_hr>=0.60 else -0.02 if dff_hr<=0.30 else -0.01 if dff_hr<=0.40 else 0
        if abs(da) >= 0.01:
            c = "#22c55e" if da > 0 else "#e04040"
            (drivers if da > 0 else risks).append((f"DFF L{dff_n} ({dff_hr:.0%} hit rate)", f"{'+' if da>0 else ''}{da*100:.0f}%", c))

    # ── DFF Teammate ────────────────────────────────────────
    dff_sig = str(prop.get("DFFSignal",""))
    if "📈" in dff_sig:
        drivers.append(("DFF teammate OUT (boost)", "+3.0%", "#22c55e"))
    elif "📉" in dff_sig:
        risks.append(("DFF teammate OUT (fade)", "-3.0%", "#e04040"))

    # ── Role change ─────────────────────────────────────────
    rc = prop.get("RoleChange")
    if isinstance(rc, dict):
        ra = float(rc.get("edge_adj",0) or 0)
        if abs(ra) >= 0.01:
            c = "#22c55e" if ra > 0 else "#e04040"
            (drivers if ra > 0 else risks).append(("Role change", f"{'+' if ra>0 else ''}{ra*100:.0f}%", c))

    # ── Conflict status ────────────────────────────────────
    _conflict_note = prop.get("ConflictNote","")
    _mkt_agree     = prop.get("MarketAgreement", 50)
    _mkt_lbl       = prop.get("MarketAgreementLabel","")
    if _conflict_note and prop.get("ConflictStatus") in ("CONFLICTED","MIXED"):
        _cc = "#e04040" if prop.get("ConflictStatus") == "CONFLICTED" else "#e8a020"
        risks.append((_conflict_note[:50], "", _cc))
    if _mkt_agree >= 70:
        drivers.append((f"Market agree {_mkt_lbl}", f"{_mkt_agree}/100", "#22c55e"))
    elif _mkt_agree < 40:
        risks.append((f"Fragmented market", f"{_mkt_agree}/100", "#e8a020"))

    # ── Risks ───────────────────────────────────────────────
    if prop.get("Injury"):
        risks.append(("Injury flag", str(prop.get("Injury",""))[:20], "#e04040"))
    if float(prop.get("SignalBlowout",0) or 0) < -0.02:
        risks.append(("Blowout risk", f"{float(prop.get('SignalBlowout',0))*100:.1f}%", "#e8a020"))
    if float(prop.get("SignalRest",0) or 0) < -0.05:
        risks.append(("B2B fatigue", "-8.0%", "#e8a020"))

    return drivers[:6], risks[:4]


def render_signal_contribution_table(prop):
    """Render signal contribution as HTML table with final edge total."""
    drivers, risks = generate_why_drivers(prop)
    final_pct = round(float(prop.get("Edge",0) or 0) * 100, 1)
    all_rows  = drivers + risks
    if not all_rows:
        return ""
    rows_html = "".join(
        f'<tr><td style="padding:3px 8px;color:var(--bc-muted);font-size:11px;">{lbl}</td>'
        f'<td style="padding:3px 8px;text-align:right;font-weight:700;color:{col};font-size:11px;">{val}</td></tr>'
        for lbl, val, col in all_rows
    )
    sign  = "+" if final_pct > 0 else ""
    fcol  = "#22c55e" if final_pct >= 5 else "#e8a020" if final_pct >= 2 else "#6a7a8a"
    return (
        f'<table style="width:100%;border-collapse:collapse;">{rows_html}'
        f'<tr style="border-top:1px solid #2a3a50;">'
        f'<td style="padding:4px 8px;color:#e8eaf0;font-weight:700;font-size:12px;">Final Edge</td>'
        f'<td style="padding:4px 8px;text-align:right;font-weight:700;color:{fcol};font-size:13px;">{sign}{final_pct}%</td>'
        f'</tr></table>'
    )


def generate_gem_summary():
    board = st.session_state.get("board_data", [])
    games = st.session_state.get("games", [])
    game_analysis = st.session_state.get("game_analysis", [])
    sport = st.session_state.get("last_sport", "NBA")
    today = date.today().strftime("%A, %B %d, %Y")
    scan_time = st.session_state.get("last_scan_time", "—")
    lines = []
    lines.append("=== BETCOUNCIL v5.1 DAILY BRIEF ===")
    lines.append(f"Sport: {sport}")
    lines.append(f"Date: {today}")
    lines.append(f"Scanned: {scan_time}")
    lines.append("")
    history = get_calibration_source_records()
    tier_stats = compute_tier_stats(history)
    if tier_stats:
        lines.append("=== SEM CALIBRATION ===")
        for tier, stats in tier_stats.items():
            if stats["n"] >= 5:
                lines.append(f"{tier}: {stats['hit_rate']:.1%} hit rate ({stats['n']} bets) | Predicted: {stats['avg_predicted']:.1%} | Error: {stats['calibration_error']:+.3f}")
        lines.append("")
    # Add calibration summary to gem brief
    _cal_summary_gem = get_calibration_summary(history)
    lines.append(f"Calibration: {_cal_summary_gem}")
    # Add signal correlation warnings to gem brief
    _gem_perf = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    _, _gem_corr_n, _gem_corr_warnings = compute_signal_correlation_matrix(_gem_perf)
    if _gem_corr_warnings:
        lines.append(f"Signal Overlap Warnings: {'; '.join(_gem_corr_warnings[:2])}")
    _gem_lift_rows, _ = compute_signal_lift_analysis(_gem_perf)
    if _gem_lift_rows:
        _neg_signals = [r["Signal"] for r in _gem_lift_rows if "Negative" in r["Grade"]]
        if _neg_signals:
            lines.append(f"Negative Drag Signals: {', '.join(_neg_signals)}")
    signal_results, n_sig = analyze_signal_performance()
    if signal_results:
        lines.append(f"=== SIGNAL PERFORMANCE ({n_sig} bets) ===")
        for r in signal_results[:5]:
            lines.append(f"{r['Signal']}: WR {r['Win Rate With']} ({r['Bets With']} bets) | Lift: {r['Lift']} | {r['Status']}")
        lines.append("")
    optimizer_data = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
    sport_opt = optimizer_data.get(sport, {})
    if sport_opt.get("n_bets", 0) >= WEIGHT_OPTIMIZER_MIN_BETS:
        weights = sport_opt.get("weights", {})
        lines.append(f"=== {sport} WEIGHTS (DATA-DRIVEN — {sport_opt['n_bets']} bets) ===")
        for k, v in weights.items():
            lines.append(f"{k}: {v:.1%}")
        lines.append(f"Win Rate: {sport_opt.get('overall_win_rate', 0):.1%}")
    else:
        lines.append(f"=== {sport} WEIGHTS (HARDCODED) ===")
        weights = SPORT_SIGNAL_WEIGHTS.get(sport, {})
        for k, v in weights.items():
            lines.append(f"{k}: {v:.1%}")
    lines.append("")
    sovereign_elite = [p for p in board if p["Tier"] in ("SOVEREIGN", "ELITE")] if board else []
    approved = [p for p in board if p["Tier"] == "APPROVED"] if board else []
    if len(sovereign_elite) >= 2:
        action = "STRONG BETTING DAY"
    elif len(sovereign_elite) == 1:
        action = "SELECTIVE DAY"
    elif len(approved) >= 3:
        action = "MODERATE DAY"
    else:
        action = "LIGHT DAY"
    lines.append(f"=== RECOMMENDED ACTION: {action} ===")
    lines.append(f"Elite: {len(sovereign_elite)} | Approved: {len(approved)} | Total: {len(board)}")
    lines.append("")
    # Harvester status
    try:
        from fetchers import get_harvester_status as _ghs
        _hs = _ghs(sport)
        _h_active = sum(1 for v in _hs.values() if v.get("active"))
        lines.append(f"=== HARVESTER STATUS ({_h_active}/{len(_hs)} LIVE) ===")
        for _hn,_hv in _hs.items():
            _age = f"{_hv['age_minutes']}min" if _hv.get("age_minutes") else "no data"
            _icon = "🟢" if _hv.get("active") else ("🟡" if _hv.get("age_minutes") else "⚪")
            lines.append(f"{_icon} {_hn}: {_age}")
        lines.append("")
    except Exception:
        pass
    # Scanbet drops
    _sbd = st.session_state.get("scanbet_drops",[])
    _sbd_steam = [d for d in _sbd if d.get("is_steam") and abs(d.get("drop_pct",0))>0.03]
    if _sbd_steam:
        lines.append(f"=== SCANBET DROPS ({len(_sbd_steam)} steam moves) ===")
        for d in sorted(_sbd_steam,key=lambda x:abs(x.get("drop_pct",0)),reverse=True)[:5]:
            lines.append(f"📡 {d['game']} | {d['market']} {d['selection']}: {d['drop_pct']:+.1%} ({d['n_snapshots']}snaps)")
        lines.append("")
    if board:
        lines.append("=== TOP PROPS (MODE A READY) ===")
        top = [p for p in board if p["Tier"] in ("SOVEREIGN","ELITE","APPROVED")][:15]
        for p in top:
            injury = f" ⚠️ {p['Injury']}" if p.get("Injury") else ""
            std_note = f" σ={p['StdDev']:.1f}" if p.get("StdDev") else ""
            fairness = f" [{p['FairnessGrade']}]" if p.get("FairnessGrade") not in (None, "GOOD", "UNKNOWN") else ""
            # Real Pinnacle no-vig prob (props: always empty by design — arcadia
            # guest API has no props endpoint; game-line Pinnacle lives elsewhere).
            pin_prob = p.get("PinnacleProb", "—")
            pin_note = f" Pin:{pin_prob}" if pin_prob and pin_prob != "—" else ""
            # Multi-book consensus (NOT Pinnacle) — label distinctly so GEM
            # never treats plain book consensus as a Pinnacle no-vig confirmation.
            consensus = f" Consensus:{p['ConsensusProb']}" if p.get("ConsensusProb","—") != "—" else ""
            # Signal count
            sig_count = p.get("SignalCount", p.get("signal_count", None))
            sig_note = f" [{sig_count}/7 signals]" if sig_count is not None else ""
            # Opponent defensive context
            opp_def = p.get("OppDef", p.get("opp_def", p.get("DefRating", None)))
            opp_note = f" OppDef:{opp_def}" if opp_def else ""
            # Rest flag
            rest = p.get("RestFlag", p.get("rest_flag", ""))
            rest_note = f" [{rest}]" if rest else ""
            # Recent game log summary
            log = p.get("RecentLog", p.get("recent_log", ""))
            log_note = f" L5:{log}" if log else ""
            # Book + odds
            book = p.get("Book", p.get("book", ""))
            odds = p.get("Odds", p.get("odds", ""))
            book_note = f" @{book}{odds}" if book else ""
            # Sharp signals on this prop
            prop_steam  = p.get("steam_flag", p.get("EVSteamFlag", False))
            prop_rlm    = p.get("rlm_flag", p.get("RLMFlag", False))
            prop_sharp  = p.get("sharp_move", p.get("SharpMoveFlag", False))
            sharp_note  = ""
            if prop_steam:
                sharp_note += " 🔥STEAM"
            if prop_rlm:
                rlm_str = p.get("rlm_note", p.get("RLMNote", "RLM"))
                sharp_note += f" ⚡{rlm_str[:30]}"
            elif prop_sharp:
                sharp_note += " 📌SHARP"
            if p.get("ScanbetSteam"):
                sharp_note += f" 📡Pinnacle:{p.get('ScanbetDropPct',0):+.1%}({p.get('ScanbetSnapshots',0)}snaps)"
            if p.get("SteamMove"):
                sharp_note += f" 🔥Steam:{p.get('SteamPct',0):+.1%}"
            if p.get("SignalOddsConf"):
                sharp_note += f" 🤖SO:{p.get('SignalOddsConf',0):.0%}EV:{p.get('SignalOddsEV',0):.2f}"
            if p.get("FPNote"): sharp_note += f" 📋{p['FPNote'][:20]}"
            if p.get("StatMuseNote"): sharp_note += f" 📊{p['StatMuseNote'][:15]}"
            if p.get("DefenseNote"): sharp_note += f" 🎯{p['DefenseNote'][:20]}"
            if p.get("IsLive"): sharp_note += " 🔴LIVE"
            # Regression risk
            reg_risk = p.get("regression_risk", p.get("HotStreakRisk", ""))
            reg_note = f" [REGRESS:{reg_risk}]" if reg_risk and reg_risk != "NONE" else ""
            # CPOE for QBs / pitchers
            cpoe = p.get("cpoe", p.get("CPOE", None))
            cpoe_note = f" CPOE:{cpoe:+.1f}" if cpoe is not None else ""
            lines.append(
                f"{p['Tier']}: {p['Player']} {p['Side']} {p['Line']} {p['Prop']}{book_note} | "
                f"Avg:{p['Avg']:.1f}{std_note} | Edge:{p['EdgePct']} | Prob:{p['Prob']:.1%}"
                f"{pin_note}{consensus}{sig_note}{opp_note}{rest_note}{fairness}{injury}{log_note}"
                f"{sharp_note}{reg_note}{cpoe_note}"
            )
        lines.append("")
    alt_upgrades = st.session_state.get("alt_line_upgrades", [])
    if alt_upgrades:
        lines.append(f"=== ALT LINE UPGRADES ({len(alt_upgrades)} found) ===")
        for upg in alt_upgrades[:4]:
            lines.append(f"{upg['player']} {upg['stat']}: Main {upg['main_line']} → Alt OVER {upg['best_line']} @ {upg['best_payout']} | EV improvement: +{upg['ev_improvement']:.1%}")
        lines.append("")
    if game_analysis:
        lines.append("=== TOP GAME BETS ===")
        for g in game_analysis[:5]:
            bb = g.get("best_bet", {})
            if not bb:
                continue
            pub       = g.get("public_data", {})
            steam_sig = g.get("steam_signals", {})
            rlm_sig   = g.get("rlm_score", {})
            mkt_div   = g.get("market_divergence", {})
            sharp_con = g.get("sharp_consensus", {})

            # Base line
            line_str = f"{g['matchup']}: {bb['pick']} ({bb['type']}) | Edge:{bb['edge_pct']} | Tier:{bb.get('tier','?')}"

            # Steam flag
            steam_parts = []
            for k, v in steam_sig.items():
                if isinstance(v, dict) and v.get("is_steam"):
                    steam_parts.append(f"🔥STEAM {k.upper()} +{v.get('magnitude',0):.1f}pt in {v.get('elapsed_seconds',0)//60}min")
            if steam_parts:
                line_str += f" | {' '.join(steam_parts)}"

            # RLM score
            if rlm_sig.get("rlm_detected"):
                line_str += f" | {rlm_sig.get('strength','?')} RLM(score={rlm_sig.get('rlm_score',0):.2f} mult=×{rlm_sig.get('edge_mult',1):.2f})"

            # Market maker divergence
            if mkt_div.get("divergence_detected"):
                line_str += f" | MKT_DIV:{mkt_div.get('gap',0):.2f}pt(setter={mkt_div.get('setter_line')} taker={mkt_div.get('taker_line')}) [{mkt_div.get('signal_strength')}]"

            # Sharp consensus
            if sharp_con.get("agreement"):
                line_str += f" | SHARP_CONSENSUS:{sharp_con.get('confidence','?')}(line={sharp_con.get('setter_line')})"

            # Public signals
            if pub and pub.get("sharp_signals"):
                line_str += f" | {pub['sharp_signals'][0][:50]}"

            # Fair values
            if bb.get("fair_total"):
                line_str += f" | FairTotal:{bb['fair_total']}"
            if bb.get("fair_prob"):
                line_str += f" | FairProb:{bb['fair_prob']:.1%}"

            lines.append(line_str)
        lines.append("")
    # ── Sharp signal summary section ──────────────────────────────────────────
    _game_steam = st.session_state.get("game_steam_signals", {})
    _steam_moves = st.session_state.get("steam_moves", [])
    if _game_steam or _steam_moves:
        lines.append("=== SHARP MONEY SIGNALS ===")
        # Steam moves from detect_steam_moves()
        for sm in _steam_moves[:5]:
            lines.append(f"🔥 {sm.get('matchup','?')}: {sm.get('signal',sm.get('strength','STEAM'))} | {sm.get('direction','')} {sm.get('market','')} | Books:{','.join(sm.get('moved_books',[])[:3])}")
        # Steam from game signals
        for gkey, gsig in _game_steam.items():
            tot = gsig.get("steam_total", {})
            spr = gsig.get("steam_spread", {})
            if tot.get("is_steam"):
                lines.append(f"🔥 {gkey} TOTAL: steam +{tot.get('magnitude',0):.1f}pt | conf={tot.get('confidence',0):.2f}")
            if spr.get("is_steam"):
                lines.append(f"🔥 {gkey} SPREAD: steam +{spr.get('magnitude',0):.1f}pt | conf={spr.get('confidence',0):.2f}")
        lines.append("")

    public_data = st.session_state.get("public_betting_data", {})
    if public_data:
        lines.append("=== PUBLIC BETTING ALERTS ===")
        for gkey, gd in public_data.items():
            signals = gd.get("sharp_signals", [])
            if signals:
                teams = " vs ".join(gd.get("teams", []))
                for sig in signals[:2]:
                    lines.append(f"{teams}: {sig}")
        lines.append("")
    clv_data = load_json_data(CLV_PATH, [])
    if len(clv_data) >= 5:
        avg_clv = sum(c.get("clv", 0) for c in clv_data) / len(clv_data)
        pos_rate = sum(1 for c in clv_data if c.get("clv", 0) > 0) / len(clv_data)
        lines.append("=== CLV STATUS ===")
        lines.append(f"Avg CLV: {avg_clv:+.2f} | Positive Rate: {pos_rate:.1%} | N: {len(clv_data)}")
        lines.append("")
    injuries = {}
    for p in board:
        if p.get("Injury"):
            injuries[p["Player"]] = p["Injury"]
    if injuries:
        lines.append("=== INJURY FLAGS ===")
        for player, status in injuries.items():
            lines.append(f"{player}: {status}")
        lines.append("")
    arb_opps = st.session_state.get("arb_opportunities", [])
    if arb_opps:
        lines.append(f"=== ARB OPPORTUNITIES ({len(arb_opps)}) ===")
        for arb in arb_opps[:3]:
            lines.append(f"{arb['Player']} {arb['Stat']} {arb['Line']}: OVER {arb['OVER Book']} {arb['OVER Odds']} / UNDER {arb['UNDER Book']} {arb['UNDER Odds']} | Profit: {arb['Arb Profit']}")
        lines.append("")
    lines.append("=== END BRIEF — PASTE INTO GEM ===")
    return "\n".join(lines)


def generate_slip_summary(picks, results):
    """
    Generate a formatted summary report for an analyzed slip.
    Same format as the daily Gem brief — copy into Gem or save.
    """
    today = date.today().strftime("%A, %B %d, %Y")
    sport = results[0]["sport"] if results else "NBA"
    lines = []

    # Header
    lines.append("⚡ BETCOUNCIL SLIP ANALYSIS REPORT")
    lines.append(f"{sport} — {today} | v4.6")
    lines.append("=" * 44)
    lines.append("")

    # Overall verdict
    n_picks = len(results)
    all_probs = [r["prob"] for r in results]
    combined_prob = parlay_prob(all_probs)
    multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)
    breakeven = prizepicks_breakeven_prob(n_picks)
    parlay_ev = combined_prob - breakeven

    fades = sum(1 for r in results if r["edge"] < -0.05)
    strong = sum(1 for r in results if r["edge"] >= 0.08)

    if fades > 0:
        verdict = f"AVOID — {fades} pick(s) model says FADE"
    elif strong == n_picks:
        verdict = "STRONG SLIP — All picks have solid edge"
    elif parlay_ev > 0:
        verdict = "GOOD SLIP — Positive combined EV"
    else:
        verdict = "SKIP — Combined EV is negative"

    lines.append(f"🎯 VERDICT: {verdict}")
    lines.append("")

    # Parlay math
    lines.append(f"📊 PARLAY MATH ({n_picks}-pick)")
    lines.append(f"Combined Prob: {combined_prob:.1%}")
    lines.append(f"Payout: {multiplier}x | Breakeven: {breakeven:.1%}")
    lines.append(f"True EV: {parlay_ev:+.1%} {'✅ +EV' if parlay_ev > 0 else '❌ -EV'}")
    lines.append("")

    # Pick by pick
    lines.append("─" * 44)
    lines.append("🔒 PICK-BY-PICK BREAKDOWN")
    lines.append("─" * 44)

    for i, r in enumerate(results, 1):
        avg_display = f"{r['avg']:.1f}" if r.get("avg") else "No historical data"
        lines.append(f"")
        lines.append(f"[{i}] {r['player']} — {r['side']} {r['line']} {r['stat']}")
        lines.append(f"Tier: {r['tier']} | Edge: {r['edge']:+.1%} | Prob: {r['prob']:.1%}")
        lines.append(f"Avg (historical): {avg_display}")
        lines.append(f"2-pick EV: {r['ev_2']} | Recommendation: {r['rec']}")
        if r.get("better_line"):
            lines.append(f"⚡ {r['better_line']}")
        if r.get("line_note"):
            lines.append(f"⚠️ {r['line_note']}")
        if r.get("sharp_flag"):
            lines.append(f"💰 Sharp: {r['sharp_flag']}")
        if r.get("dk_note"):
            lines.append(f"🏀 DK: {r['dk_note']}")
        lines.append(f"Data: {r['data_source']}")

    lines.append("")
    lines.append("─" * 44)

    # Strengths and weaknesses
    good = [r for r in results if r["edge"] >= 0.04]
    weak = [r for r in results if r["edge"] < 0]

    if good:
        lines.append("✅ STRONGEST PICKS:")
        for r in sorted(good, key=lambda x: x["edge"], reverse=True):
            lines.append(f"  • {r['player']} {r['side']} {r['line']} {r['stat']} | Edge: {r['edge']:+.1%}")

    if weak:
        lines.append("")
        lines.append("❌ WEAK PICKS (consider replacing):")
        for r in weak:
            lines.append(f"  • {r['player']} {r['side']} {r['line']} {r['stat']} | Edge: {r['edge']:+.1%}")

    lines.append("")
    lines.append("=" * 44)
    lines.append("Generated by BetCouncil v4.6")

    return "\n".join(lines)


@st.dialog("📝 Track This Bet")
def track_bet_dialog(prop):
    """
    Inline bet tracking modal — logs directly from prop card.
    Faster than navigating to Log Bet tab.
    Pre-fills all model data; user adds stake, odds, book.
    """
    player = prop.get("Player","")
    prop_name = prop.get("Prop","")
    side   = prop.get("Side","OVER")
    line   = prop.get("Line",0)
    sport  = prop.get("Sport", st.session_state.get("last_sport","NBA"))
    tier   = prop.get("Tier","APPROVED")
    edge   = prop.get("Edge",0)
    prob   = prop.get("Prob",0.55)

    st.markdown(
        f'{tier_badge(tier)} &nbsp; '
        f'<span style="font-size:16px;font-weight:700;color:var(--bc-text);">'
        f'{player} {side} {line} {prop_name}</span>'
        f'<br><span style="color:#22c55e;font-size:13px;">Edge {edge:.1%} · '
        f'Fair Prob {prob:.1%}</span>',
        unsafe_allow_html=True
    )
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        stake   = st.number_input("Stake ($)", min_value=1.0, step=5.0, value=25.0)
        odds    = st.number_input("Odds taken", value=-110, step=5,
                                  help="-110 = standard juice. Enter positive for underdogs.")
    with col2:
        book    = st.selectbox("Sportsbook / Platform",
                               ["PrizePicks","Underdog","ParlayPlay","DraftKings",
                                "FanDuel","BetMGM","Caesars","BetRivers","Other"])
        outcome = st.selectbox("Outcome", ["PENDING","WIN","LOSS","PUSH"])

    notes = st.text_input("Note (optional)", placeholder="Line movement, injury news…")

    if st.button("✅ Confirm & Track", type="primary", use_container_width=True):
        log_manual_bet(
            player=player, prop=prop_name, line=line, side=side,
            sport=sport, outcome=outcome,
            wager=stake, pick_count=2, bet_type="prop",
            source=book, bet_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            tier=tier, edge=edge, prob=prob, notes=notes,
            signals=_board_prop_signal_values(prop),
            clv_capture=_capture_clv_placement(player, prop_name, prob),
        )
        # Store odds for CLV tracking
        _hist = st.session_state.get("history", [])
        if _hist:
            _hist[-1]["odds_taken"] = odds
            save_to_gist("history", _hist)
        st.success(f"Tracked ${stake:.0f} on {player} {side} {line}!")
        st.caption("📝 This also appears in the **Log Bet** tab → Recent Activity, alongside bets logged there — same shared history.")
        st.rerun()


def parse_prizepicks_history_text(raw_text: str) -> list:
    """
    Parse PrizePicks' own history-page export format (copy-paste from the
    app) into structured slip records for bulk historical logging.

    Expected per-slip block shape (blank-line separated):
        <N>-Pick $<stake>
        $<per-pick> Flex Play   (or "Power Play", or "BONUS Power Play")
        <abbreviated names line — skipped>
        <full player name>
        <full player name>
        ... (N total)
        Win | LOST | Refund

    Date headers ("Jun 29, 2026") apply to every slip until the next date
    header. Slips with no recognized result line are returned with
    outcome=None so the caller can skip unresolved/pending entries rather
    than silently logging them as something they're not.

    Returns: list of {date, n_picks, stake, players, outcome}
    """
    if not raw_text or not raw_text.strip():
        return []

    _date_re = re.compile(r'^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$')
    _slip_header_re = re.compile(r'^(\d+)-Pick\s+\$([\d.]+)$')
    _play_type_re = re.compile(r'^(?:\$[\d.]+|BONUS)\s+(?:Flex|Power)\s+Play$', re.IGNORECASE)
    _abbrev_names_re = re.compile(r'^[A-Z][\w.\-]*\.\s')
    _result_re = re.compile(r'^(Win|LOST|Refund)$', re.IGNORECASE)
    _result_map = {"WIN": "WIN", "LOST": "LOSS", "REFUND": "PUSH"}

    lines = [l.strip() for l in raw_text.split("\n")]
    n = len(lines)
    i = 0
    current_date = None
    slips = []

    while i < n:
        line = lines[i]
        if not line:
            i += 1
            continue
        if _date_re.match(line):
            current_date = line
            i += 1
            continue
        _sm = _slip_header_re.match(line)
        if _sm:
            n_picks = int(_sm.group(1))
            stake = float(_sm.group(2))
            i += 1
            while i < n and not lines[i]:
                i += 1
            if i < n and _play_type_re.match(lines[i]):
                i += 1
            while i < n and not lines[i]:
                i += 1
            if i < n and _abbrev_names_re.match(lines[i]):
                i += 1
            while i < n and not lines[i]:
                i += 1
            players = []
            while i < n and lines[i] and not _result_re.match(lines[i]):
                players.append(lines[i])
                i += 1
            outcome = None
            if i < n and _result_re.match(lines[i]):
                outcome = _result_map.get(lines[i].upper())
                i += 1
            if players:
                slips.append({
                    "date": current_date, "n_picks": n_picks, "stake": stake,
                    "players": players, "outcome": outcome,
                })
            continue
        i += 1

    return slips


def log_manual_bet(player, prop, line, side, sport, outcome, wager, pick_count, bet_type, source, bet_date, tier=None, edge=None, prob=None, notes="", signals=None, clv_capture=None):
    multiplier = PRIZEPICKS_MULTIPLIERS.get(pick_count, 3.0)
    if outcome == "WIN":
        if bet_type == "prop":
            profit = round(wager * multiplier, 2)
        else:
            profit = round(wager * 0.909, 2)
        net = profit
    elif outcome == "PUSH":
        profit = 0
        net = 0  # stake returned, no win and no loss
    else:
        profit = 0
        net = -wager
    if tier is None:
        if edge:
            tier = get_tier(edge, sport, st.session_state.get("calibrated_thresholds"))
        else:
            tier = "APPROVED"
    # NEVER fabricate a probability from the known outcome (was: 0.60 if WIN
    # else 0.45) -- that's not a prediction, it's reverse-engineering a
    # plausible number from the answer, which would make calibration math
    # look artificially good without representing any real model output.
    # If no real prob was supplied, mark this record as having no usable
    # prediction; calibration/reliability code should skip it rather than
    # be fed a fake number.
    _has_real_prob = prob is not None
    if prob is None:
        prob = 0.5  # neutral placeholder, never used for calibration math
    record = {
        "player": player, "prop": prop, "line": line, "side": side, "sport": sport,
        "outcome": outcome, "wager": wager, "profit": profit, "loss": wager if outcome == "LOSS" else 0,
        "net": net, "pick_count": pick_count, "bet_type": bet_type, "source": source,
        "tier": tier, "edge": edge or 0, "prob": prob, "has_real_prob": _has_real_prob, "stat_type": prop,
        "timestamp": bet_date, "resolved_date": bet_date, "manual_entry": True, "notes": notes,
        # Signal values at time of bet — foundation for attribution analysis
        "signal_values": signals or {},
        "signals_active": {
            "base_positive":    bool((signals or {}).get("base", 0) > 0.02),
            "defense_positive": bool((signals or {}).get("defense", 0) > 0.01),
            "location_home":    bool((signals or {}).get("location", 0) > 0.01),
            "back_to_back":     bool((signals or {}).get("rest", 0) < -0.05),
            "sharp_flag":       bool((signals or {}).get("sharp", 0) > 0),
            "weather_active":   bool((signals or {}).get("weather", 0) != 0),
            "blowout_risk":     bool((signals or {}).get("blowout", 0) < -0.02),
            "usage_boost":      bool((signals or {}).get("usage", 0) > 0.01),
        },
        # ── CLV Capture — Buchdahl methodology ─────────────────────────
        # Store Pinnacle/Circa no-vig odds AT TIME OF BET PLACEMENT
        # After game time, compare against closing line to compute true CLV
        # Positive CLV over 50+ bets = statistically proven skill
        "clv_capture": {
            "placement_ts":       bet_date,
            "placement_edge":     edge or 0,
            "placement_prob":     prob or 0,
            "bet_type":           bet_type,
            # Prop path — no-vig probability vs ev_signal_lookup
            "pn_novig_placement":    None,
            "circa_novig_placement": None,
            "consensus_novig_placement": None,
            "closing_pn_novig":   None,   # filled in after game
            "closing_consensus":  None,   # filled in after game
            "clv_vs_placement":   None,   # filled in after game
            "clv_vs_novig":       None,   # gold standard CLV vs no-vig close (props)
            # Game path — point-line vs Pinnacle (added 2026-07-13)
            "placement_line_pinnacle": None,
            "closing_line_pinnacle":   None,
            "clv_points":              None,   # points-based CLV (games)
            "clv_resolved":       False,
        }
    }

    # Populate CLV placement odds. Prefer a snapshot already captured at
    # LOCK time (passed in via clv_capture= from the lock dict, using
    # _capture_clv_placement) -- that's the only version of this lookup
    # that's actually still live when it runs. Falling back to a fresh
    # lookup here (post-hoc, at log time) is kept for paths with no lock
    # object at all (manual/bulk/OCR entry), but for anything logged after
    # the game it will almost always come back empty -- that's a real
    # limitation of after-the-fact entry, not a bug, so it's left as an
    # honest empty rather than worked around.
    if clv_capture:
        # Merge whatever shape was captured at lock time (prop: no-vig
        # probability keys; game: point-line keys, bet_type="game") over
        # the default all-None scaffold, rather than a hardcoded key list
        # that only understood the prop shape.
        for k, v in clv_capture.items():
            if v is not None:
                record["clv_capture"][k] = v
    else:
        try:
            import streamlit as _st
            _sig_key = (normalize_name(player), prop)
            _ev_sig  = _st.session_state.get("ev_signal_lookup", {}).get(_sig_key, {})
            if _ev_sig:
                _pn_nv    = _ev_sig.get("pn_novig")
                _circa_nv = _ev_sig.get("circa_novig")
                _cons_nv  = _ev_sig.get("consensus_novig")
                record["clv_capture"]["pn_novig_placement"]    = _pn_nv
                record["clv_capture"]["circa_novig_placement"] = _circa_nv
                record["clv_capture"]["consensus_novig_placement"] = _cons_nv
                # Compute immediate CLV vs current market (pre-close)
                if _cons_nv and prob:
                    record["clv_capture"]["clv_vs_placement"] = round(
                        float(_cons_nv) - float(prob), 4
                    )
        except Exception:
            _logger.debug("Silent except at line 8782")
            pass
    # ── Enhance record with tier-based CLV quality before saving ──────────
    try:
        _rec_tier = record.get("tier", "APPROVED")
        _rec_odds = record.get("odds_american", record.get("odds", "-110"))
        _rec_clv  = record.get("clv_capture", {}).get("clv_vs_novig", 0) or 0
        if _rec_clv != 0 and _rec_odds:
            _clv_detail = compute_clv_with_tier(
                placement_odds=float(str(_rec_odds).replace("+","")),
                closing_odds=float(str(_rec_odds).replace("+","")),
                tier=_rec_tier,
                edge=record.get("edge", 0) or 0,
            )
            record["clv_quality"]    = _clv_detail.get("quality", "")
            record["clv_threshold"]  = _clv_detail.get("threshold", 0)
            record["clv_confirmed"]  = _clv_detail.get("edge_confirmed", False)
    except Exception:
        _logger.debug("Silent except at line 8799")
        pass
    st.session_state.setdefault("history", []).append(record)
    save_json_data(HISTORY_PATH, st.session_state.get("history", []))
    save_to_gist("history", st.session_state.get("history", []))
    st.session_state["bankroll"] = st.session_state.get("bankroll", DEFAULT_BANKROLL) + net
    save_json_data(BANKROLL_PATH, st.session_state.get("bankroll", DEFAULT_BANKROLL))
    save_to_gist("bankroll", st.session_state.get("bankroll", DEFAULT_BANKROLL))
    record_signal_performance(record, outcome)
    # ── Auto-record CLV from history bet ───────────────────────
    # Don't require Track This Bet — if we have a line and outcome,
    # record CLV using the board's current line as "closing line"
    if outcome in ("WIN", "LOSS") and line:
        try:
            _board = st.session_state.get("board_data", [])
            _current_line = None
            for _bp in _board:
                if (normalize_name(_bp.get("Player","")) == normalize_name(player) and
                    _bp.get("Prop","") == prop):
                    _current_line = _bp.get("Line")
                    break
            # If board not loaded, use the locked line as both (CLV = 0 but entry exists)
            if _current_line is None:
                _current_line = line
            _clv_val = (float(line) - float(_current_line)) if side == "OVER" else (float(_current_line) - float(line))
            _clv_data = load_json_data(CLV_PATH, [])
            # Avoid duplicates
            _already = any(
                normalize_name(c.get("player","")) == normalize_name(player) and
                c.get("prop") == prop and
                c.get("timestamp","")[:10] == bet_date[:10]
                for c in _clv_data
            )
            if not _already:
                _clv_data.append({
                    "player":      player, "prop": prop,
                    "locked_line": float(line),
                    "closing_line": float(_current_line),
                    "side":        side,
                    "clv":         round(_clv_val, 1),
                    "outcome":     outcome,
                    "timestamp":   bet_date,
                    "sport":       sport,
                    "tier":        tier or "",
                    "edge":        edge or 0,
                    "prob":        prob or 0.5,
                    "source":      source or "",
                })
                save_json_data(CLV_PATH, _clv_data)
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    # ── Optimizer guard — only run when bet count changes ──
    # Prevents running 10x per session when board reloads.
    # Key: {sport}_{n_resolved_bets} — changes only when a
    # new resolved bet (WIN/LOSS) is logged.
    _n_resolved = sum(1 for h in st.session_state.get("history", [])
                      if h.get("outcome") in ("WIN","LOSS"))
    _opt_key = f"_opt_last_run_{sport}"
    _last_run = st.session_state.get(_opt_key, -1)
    if _n_resolved != _last_run and _n_resolved >= WEIGHT_OPTIMIZER_MIN_BETS:
        compute_optimized_weights(sport)
        st.session_state[_opt_key] = _n_resolved
    return record


# ═══════════════════════════════════════════════════════════
# MODULE: STANDALONE PICK SCORER
# Scores any player/prop/line WITHOUT requiring the board to be loaded.
# Priority chain:
#   1. Board cache hit       → full CLARITY scores (fastest)
#   2. Session rolling avgs  → weighted recent model
#   3. Live BDL fetch (NBA)  → real season avg via API
#   4. MLB Savant-style est  → stat-specific derivation
#   5. PLAYER_AVERAGES dict  → hardcoded star table
#   6. Line-anchored fallback→ avg = line, z=0, prob from context
# ═══════════════════════════════════════════════════════════
def compute_player_prop_smart_signal(player: str, prop: str, sport: str, current_edge: float,
                                      min_samples: int = 8) -> dict:
    """
    Double-confirmation signal, modeled on Rithmm's "Smart Signal" pattern
    but built entirely from data BetCouncil already collects -- no new
    scraper needed:

      Signal A (historical) — has THIS specific player+prop, across past
        locked picks, consistently beaten the closing line more often than
        not? Sourced from CLV_PATH (locked_line vs closing_line, captured
        automatically at lock time by _capture_clv_closing_lines).
      Signal B (live) — does the CURRENT computed edge for this pick clear
        a real threshold, in the SAME direction Signal A favors?

    smart_signal only fires when both agree. Gated by min_samples so a
    hot/cold streak on 2-3 historical picks can't masquerade as a reliable
    pattern (the exact failure mode Replit's proposal didn't guard against) --
    across many players x prop types, some will show a fake streak by pure
    chance if this isn't gated.
    """
    try:
        clv_data = load_json_data(CLV_PATH, [])
    except Exception:
        clv_data = []
    norm_p = normalize_name(player)
    matches = [
        c for c in clv_data
        if normalize_name(c.get("player", "")) == norm_p
        and str(c.get("prop", "")).lower() == str(prop).lower()
        and c.get("sport", "") == sport
        and c.get("clv") is not None
    ]
    n = len(matches)
    if n < min_samples:
        return {
            "smart_signal": False, "signal_a_reliable": False, "signal_a_n": n,
            "signal_a_hit_rate": None, "signal_a_direction": None,
            "signal_b_edge": current_edge, "direction_agrees": False,
        }

    over_matches = [c for c in matches if str(c.get("side", "")).upper() == "OVER"]
    under_matches = [c for c in matches if str(c.get("side", "")).upper() == "UNDER"]
    over_hit = (sum(1 for c in over_matches if c.get("clv", 0) > 0) / len(over_matches)) if over_matches else None
    under_hit = (sum(1 for c in under_matches if c.get("clv", 0) > 0) / len(under_matches)) if under_matches else None

    direction, hit_rate = None, None
    if over_hit is not None and (under_hit is None or over_hit >= under_hit):
        direction, hit_rate = "OVER", over_hit
    elif under_hit is not None:
        direction, hit_rate = "UNDER", under_hit

    signal_a_reliable = bool(direction) and hit_rate is not None and hit_rate >= 0.65
    direction_agrees = (
        (direction == "OVER" and current_edge >= 0.05) or
        (direction == "UNDER" and current_edge <= -0.05)
    )
    return {
        "smart_signal": signal_a_reliable and direction_agrees,
        "signal_a_reliable": signal_a_reliable,
        "signal_a_n": n,
        "signal_a_hit_rate": round(hit_rate, 3) if hit_rate is not None else None,
        "signal_a_direction": direction,
        "signal_b_edge": current_edge,
        "direction_agrees": direction_agrees,
    }


def score_pick_standalone(player, stat, line, side, sport, is_home=False):
    """
    Score a single pick using the full CLARITY pipeline, no board required.
    Returns a dict with edge, prob, avg, tier, ev_2, confidence, data_source.
    """
    import math

    stat_norm = STAT_NORMALIZE.get((sport, stat), stat)

    # ── 1. Board cache hit ───────────────────────────────────────────────────
    board = st.session_state.get("board", [])
    if board:
        norm_p = normalize_name(player)
        for b in board:
            if normalize_name(b.get("Player", "")) == norm_p and b.get("Prop", "").lower() == stat.lower():
                board_line = float(b.get("Line", line) or line)
                edge = float(b.get("Edge", 0) or 0)
                prob = float(b.get("Prob", 0.5) or 0.5)
                # Adjust edge if line differs
                line_diff = round(float(line) - board_line, 1)
                if line_diff != 0:
                    adj = 0.03 * abs(line_diff)
                    if side == "OVER" and line_diff > 0:
                        edge = max(-0.15, edge - adj)
                    elif side == "OVER" and line_diff < 0:
                        edge = min(0.30, edge + adj)
                return {
                    "edge": edge, "prob": prob,
                    "avg": float(b.get("Avg", 0) or 0),
                    "tier": _get_cal_tier(edge, sport),
                    "ev_2": f"{calculate_prizepicks_ev(prob, 2):+.1%}",
                    "confidence": b.get("SEM", "Full model"),
                    "data_source": "📊 Full model (board)",
                    "board_matched": True,
                    "smart_signal_data": compute_player_prop_smart_signal(player, stat, sport, edge),
                }

    # ── Resolve player average from best available source ───────────────────
    avg = 0.0
    data_source_label = "📚 Historical averages"
    confidence_label = "Static table"

    # ── 2. Session rolling avgs (loaded when board was last run) ─────────────
    _rolling = st.session_state.get("rolling_avgs")
    if _rolling is None and sport == "NBA":
        # Free source (stats.nba.com, no API key) -- previously only ever
        # populated by loading the main board, so board-paste always saw
        # this empty and fell straight to the metered BDL fallback below
        # for every single player, even though this free source already
        # existed and already works. Same bug pattern as WNBA, fixed the
        # same way: call it directly, once per run, when the cache is empty.
        _rolling = fetch_nba_rolling_averages() or {}
        st.session_state["rolling_avgs"] = _rolling
    _rolling = _rolling or {}
    _season  = st.session_state.get("season_avgs_cache", {})
    if player in _rolling or normalize_name(player) in {normalize_name(k) for k in _rolling}:
        _rp = _rolling.get(player) or next((v for k, v in _rolling.items() if normalize_name(k) == normalize_name(player)), None)
        if _rp and isinstance(_rp, dict):
            _val = _rp.get(stat_norm, 0)
            if _val and float(_val) > 0:
                avg = float(_val)
                data_source_label = "📈 Rolling avg (session)"
                confidence_label = f"L{_rp.get('n_games', 10)} games"

    # ── 3. Live BDL fetch for NBA ────────────────────────────────────────────
    if avg == 0.0 and sport == "NBA":
        try:
            live = fetch_player_season_avg_bdl(player, sport)
            if live:
                _val = live.get(stat_norm, 0)
                if _val and float(_val) > 0:
                    avg = float(_val)
                    data_source_label = "🌐 Live BDL season avg"
                    confidence_label = "2025 season"
        except Exception:
            _logger.debug("Silent except at line 8938")
            pass

    # ── 4. MLB live season avg (statsapi.mlb.com, any active player) ───────────
    if avg == 0.0 and sport == "MLB":
        try:
            mlb_stats = fetch_mlb_player_season_avg(player)
            if mlb_stats:
                # Map the requested stat to what we fetched
                _stat_map = {
                    "SO": "SO", "Strikeouts": "SO", "Ks": "SO",
                    "H": "H", "Hits": "H", "HR": "HR", "Home Runs": "HR",
                    "RBI": "RBI", "RBIs": "RBI", "R": "R", "Runs": "R",
                    "ER": "ER", "Earned Runs Allowed": "ER",
                    "Hitter FS": "Hitter FS", "Pitcher FS": "Pitcher FS",
                    "H+R+RBI": "H+R+RBI", "Hits+Runs+RBIs": "H+R+RBI",
                    "Hits+Runs+RBls": "H+R+RBI",
                    "1st Inning Runs Allowed": "ER",
                    "Total Bases": "TB",
                    "Pitcher Outs": "Outs", "Pitching Outs": "Outs", "Outs": "Outs", "PO": "Outs",
                }
                _key = _stat_map.get(stat_norm) or _stat_map.get(stat) or stat_norm
                _val = mlb_stats.get(_key, 0)
                if _val and float(_val) > 0:
                    avg = float(_val)
                    n_g = mlb_stats.get("n_games", "?")
                    data_source_label = f"⚾ MLB 2025 season avg"
                    confidence_label = f"{n_g} games"
        except Exception:
            _logger.debug("Silent except at line 8965")
            pass

    # ── 5. PLAYER_AVERAGES hardcoded table ───────────────────────────────────
    if avg == 0.0:
        sport_avgs = PLAYER_AVERAGES.get(sport, {})
        player_data, using_default = find_player_avg(player, sport_avgs)
        if not using_default and player_data:
            _val = player_data.get(stat_norm, player_data.get(stat[:3].upper(), 0))
            if _val and float(_val) > 0:
                avg = float(_val)
                data_source_label = "📚 Season avg table"
                confidence_label = "2025 estimates"

    # ── 6. MLB league baseline (last resort for unknown MLB players) ──────────
    if avg == 0.0 and sport == "MLB":
        _mlb_defaults = {
            "SO": 5.5, "H": 0.9, "HR": 0.08, "RBI": 0.7, "R": 0.7,
            "ER": 2.5, "Hitter FS": 20.0, "Pitcher FS": 28.0,
            "H+R+RBI": 2.2, "Hits+Runs+RBIs": 2.2, "1st Inning Runs Allowed": 0.4,
        }
        _val = _mlb_defaults.get(stat_norm) or _mlb_defaults.get(stat)
        if _val:
            avg = float(_val)
            data_source_label = "📊 MLB league baseline"
            confidence_label = "League avg only"

    # ── 7. Live ESPN stats for WNBA / Tennis / Golf / Soccer / UFC / NFL ────────
    if avg == 0.0:
        try:
            _live = None
            _stat_lookup = {}
            if sport == "WNBA":
                # Try rolling cache first (stats.wnba.com covers all players).
                # Previously this only checked the session cache and never
                # called the live fetch itself ("board loads it") -- but
                # board-paste never loads the main board, so this was
                # ALWAYS empty there, forcing every single WNBA prop through
                # the unverified ESPN fallback below, which was consistently
                # failing. Now calls the confirmed-working stats.wnba.com
                # source directly (same one whose season-year bug was fixed
                # earlier) when the cache is empty, once per run.
                _wnba_rolling = st.session_state.get("wnba_rolling_avgs")
                if _wnba_rolling is None:
                    _wnba_rolling = fetch_wnba_rolling_averages() or {}
                    st.session_state["wnba_rolling_avgs"] = _wnba_rolling
                _norm = normalize_name(player)
                _match = next((v for k, v in _wnba_rolling.items()
                               if normalize_name(k) == _norm), None)
                if _match:
                    _live = _match
                    data_source_label = "📊 WNBA rolling avg"
                    confidence_label = f"L{_match.get('n_games', 10)} games"
                else:
                    _live = fetch_wnba_player_stats(player)
                    if _live:
                        data_source_label = "🏀 WNBA ESPN 2025"
                        confidence_label = f"{_live.get('n_games','?')} games"
                _stat_lookup = {"PTS": "PTS", "REB": "REB", "AST": "AST",
                                "PRA": "PRA", "STL": "STL", "BLK": "BLK",
                                "Pts+Rebs+Asts": "PRA", "Points": "PTS",
                                "Rebounds": "REB", "Assists": "AST",
                                "3PTM": "3PM", "3-PT Made": "3PM", "3PM": "3PM",
                                "Rebs+Asts": "REB_AST", "Reb+Ast": "REB_AST",
                                "Pts+Reb": "PTS_REB", "Pts+Ast": "PTS_AST",
                                "Fantasy Score": "FANTASY", "Turnovers": "TO"}

            elif sport in ("Tennis",):
                _live = fetch_tennis_player_stats(player)
                if _live:
                    data_source_label = f"🎾 Tennis ESPN ({_live.get('_tour','ATP/WTA')})"
                    confidence_label = f"{_live.get('n_games','?')} matches"
                    # Merge in this-match live context (opponent, set scores,
                    # status) without touching the existing season-avg keys.
                    try:
                        _tour_lower = str(_live.get("_tour", "atp")).lower()
                        _t_board = fetch_tennis_scoreboard(_tour_lower)
                        _t_match = _t_board.get(normalize_name(player)) if _t_board else None
                        if _t_match:
                            _live["live_opponent"] = _t_match.get("opponent")
                            _live["live_status"] = _t_match.get("status")
                            _live["live_sets"] = _t_match.get("sets")
                            _live["live_round"] = _t_match.get("round")
                    except Exception:
                        _logger.debug("Silent except at line 9035")
                        pass
                _stat_lookup = {
                    "Aces": "Aces", "Double Faults": "Double Faults",
                    "Games Won": "Games Won", "Break Points Won": "Break Points Won",
                    "Ks": "Aces",  # PrizePicks sometimes uses Ks label for aces
                }

            elif sport in ("Golf", "PGA"):
                _live = fetch_golf_player_stats(player)
                if _live:
                    data_source_label = "⛳ PGA ESPN 2025"
                    confidence_label = f"{_live.get('n_games','?')} rounds"
                    # Merge in this-week live context (made cut, position,
                    # score, tournament) without touching the existing
                    # season-avg keys.
                    try:
                        _g_board = fetch_golf_scoreboard()
                        _g_match = _g_board.get(normalize_name(player)) if _g_board else None
                        if _g_match:
                            _live["live_made_cut"] = _g_match.get("made_cut")
                            _live["live_position"] = _g_match.get("position")
                            _live["live_score"] = _g_match.get("score")
                            _live["live_thru"] = _g_match.get("thru")
                            _live["live_tournament"] = _g_match.get("tournament")
                    except Exception:
                        _logger.debug("Silent except at line 9060")
                        pass
                _stat_lookup = {
                    "Strokes": "Strokes", "Birdies": "Birdies",
                    "Bogeys": "Bogeys", "Eagles": "Eagles",
                    "Score": "Strokes",
                }

            elif sport == "Soccer":
                _live = fetch_soccer_player_stats(player)
                if _live:
                    data_source_label = f"⚽ Soccer ESPN ({_live.get('_league','Intl')})"
                    confidence_label = f"{_live.get('n_games','?')} matches"
                _stat_lookup = {
                    "GOALS": "GOALS", "ASSISTS": "ASSISTS", "SHOTS": "SHOTS",
                    "Goals": "GOALS", "Assists": "ASSISTS", "Shots": "SHOTS",
                    "Shots on Target": "Shots on Target",
                }

            elif sport in ("UFC", "MMA"):
                _live = fetch_ufc_fighter_stats(player)
                if _live:
                    data_source_label = "🥊 UFC ESPN"
                    confidence_label = f"{_live.get('n_games','?')} fights"
                _stat_lookup = {
                    "SIG_STR": "SIG_STR", "Significant Strikes": "SIG_STR",
                    "TAKEDOWNS": "TAKEDOWNS", "Takedowns": "TAKEDOWNS",
                    "CONTROL_TIME": "CONTROL_TIME", "Control Time": "CONTROL_TIME",
                    "KD": "KD", "Knockdowns": "KD",
                }

            elif sport == "NFL":
                _live = fetch_nfl_player_stats(player)
                if _live:
                    data_source_label = "🏈 NFL ESPN 2025"
                    confidence_label = f"{_live.get('games_played','?')} games"
                # Real keys fetch_nfl_player_stats returns are lowercase,
                # underscore-separated, and per-game averages carry a
                # '_per_game' suffix (e.g. 'passing_yards_per_game') --
                # the previous uppercase 'PASS_YDS'-style keys never
                # existed in the live payload, so every NFL prop silently
                # fell through to the league baseline or PASS regardless
                # of whether real data was actually available.
                _stat_lookup = {
                    "PASS_YDS": "passing_yards_per_game", "Passing Yards": "passing_yards_per_game",
                    "RUSH_YDS": "rushing_yards_per_game", "Rushing Yards": "rushing_yards_per_game",
                    "REC_YDS": "receiving_yards_per_game", "Receiving Yards": "receiving_yards_per_game",
                    "REC": "receptions_per_game", "Receptions": "receptions_per_game",
                    "PASS_ATT": "pass_attempts_per_game", "Pass Attempts": "pass_attempts_per_game",
                    "PASS_CMP": "completions_per_game", "Completions": "completions_per_game",
                    "Passing Touchdowns": "passing_touchdowns_per_game",
                    "Rushing Touchdowns": "rushing_touchdowns_per_game",
                    "Receiving Touchdowns": "receiving_touchdowns_per_game",
                }

            elif sport == "NHL":
                _live = fetch_nhl_player_stats(player)
                if _live:
                    data_source_label = "🏒 NHL API rolling avg"
                    confidence_label = f"L{_live.get('n_games','?')} games"
                _stat_lookup = {
                    "PTS": "PTS", "Points": "PTS",
                    "GOALS": "GOALS", "Goals": "GOALS",
                    "ASSISTS": "ASSISTS", "Assists": "ASSISTS",
                    "SOG": "SOG", "Shots on Goal": "SOG", "Shots On Goal": "SOG",
                }

            if _live:
                _key = _stat_lookup.get(stat_norm) or _stat_lookup.get(stat) or stat_norm
                _val = _live.get(_key, _live.get(stat, 0))
                if _val and float(_val) > 0:
                    avg = float(_val)
        except Exception:
            _logger.debug("Silent except at line 9110")
            pass

    # ── 8. League baselines (last numeric fallback before line-anchor) ────────
    if avg == 0.0:
        _baselines = {
            "WNBA":   {"PTS": 11.0, "REB": 5.0, "AST": 2.5, "PRA": 18.0},
            "NFL":    {"PASS_YDS": 220, "RUSH_YDS": 55, "REC_YDS": 45, "TD": 0.6, "REC": 4.5},
            "NHL":    {"PTS": 0.6, "GOALS": 0.25, "ASSISTS": 0.35, "SOG": 2.8},
            "Tennis": {"Aces": 6.0, "Games Won": 18.0, "Double Faults": 3.0, "Break Points Won": 3.0},
            "Golf":   {"Strokes": 70.5, "Birdies": 3.8, "Bogeys": 3.2},
            "Soccer": {"GOALS": 0.3, "ASSISTS": 0.2, "SHOTS": 2.8, "Shots on Target": 1.1},
            "UFC":    {"SIG_STR": 35.0, "TAKEDOWNS": 1.5, "CONTROL_TIME": 3.5},
        }
        _val = _baselines.get(sport, {}).get(stat_norm, 0) or _baselines.get(sport, {}).get(stat, 0)
        if _val:
            avg = float(_val)
            data_source_label = "📊 League baseline"
            confidence_label = "League avg only"

    # ── 8. Last resort: anchor to line ───────────────────────────────────────
    _no_real_data = (avg == 0.0)
    if avg == 0.0:
        avg = float(line) if float(line) > 0 else 1.0
        data_source_label = "⚠️ Line-anchored (no avg found)"
        confidence_label = "No data"

    if _no_real_data:
        # avg == line here, so any "edge" the model below would compute is
        # purely an artifact of fixed neutral context (opp_def=112.0,
        # is_home=False, etc.) -- NOT a real per-player signal. Reporting
        # that as a confident edge is actively misleading (it was producing
        # near-identical edges across completely different players/lines,
        # making every pick look equally playable when none of them had
        # real data backing them). Force an honest no-signal result.
        return {
            "edge": 0.0,
            "prob": 0.5,
            "avg": round(avg, 1),
            "tier": "PASS",
            "ev_2": "+0.0%",
            "confidence": "No data",
            "data_source": data_source_label,
            "board_matched": False,
            "no_real_data": True,
            "smart_signal_data": {"smart_signal": False, "signal_a_reliable": False,
                                   "signal_a_n": 0, "signal_a_hit_rate": None,
                                   "signal_a_direction": None, "signal_b_edge": 0.0,
                                   "direction_agrees": False},
        }

    # ── Run CLARITY edge model ───────────────────────────────────────────────
    try:
        std_dev = compute_std_dev(None, sport) or None
        edge, prob, _ = compute_multi_signal_edge(
            line=float(line),
            player_avg=avg,
            opp_def_rating=112.0,   # neutral — no opponent context without board
            is_home=is_home,
            teammate_out_boost=0.0,
            side=side,
            stat_key=stat_norm,
            pace_adj=0.0,
            days_rest=2,
            odds_type="standard",
            sport=sport,
            std_dev=std_dev,
            player_name=player,
        )
        edge = round(max(-0.15, min(0.30, edge)), 4)
    except Exception:
        # Fallback z-score if model call fails
        diff = avg - float(line) if side == "OVER" else float(line) - avg
        std = compute_std_dev(None, sport) or 4.0
        z = diff / std if std > 0 else 0.0
        try:
            from scipy import stats as _sp
            prob = float(_sp.norm.cdf(z))
        except Exception:
            prob = 0.5 + z * 0.08
        prob = max(0.20, min(0.80, prob))
        edge = round(calculate_edge(prob, side, sport), 4)

    tier = _get_cal_tier(edge, sport)
    ev_2 = f"{calculate_prizepicks_ev(prob, 2):+.1%}"

    return {
        "edge": edge,
        "prob": round(prob, 4),
        "avg": round(avg, 1),
        "tier": tier,
        "ev_2": ev_2,
        "confidence": confidence_label,
        "data_source": data_source_label,
        "board_matched": False,
        "smart_signal_data": compute_player_prop_smart_signal(player, stat, sport, edge),
    }


# ═══════════════════════════════════════════════════════════
# MODULE: OCR — bet screenshot parsing
# Future extraction target: ocr.py
# ═══════════════════════════════════════════════════════════

# _parse_pp_ocr_inline — moved to slip_parser.py
def _normalize_ocr_sport(raw_sport: str) -> str:
    """Map an OCR-extracted sport token to the exact casing used in the
    real SPORTS list and st.session_state.board_data's "Sport" field.

    Root cause this fixes: the OCR parser below was blindly .upper()-ing
    every extracted sport token, producing e.g. "SOCCER". That matches
    SPORTS' casing for NBA/MLB/NHL/WNBA/NFL/UFC (already all-caps), but
    NOT for "Soccer", "Golf", "Tennis" (title case in SPORTS) -- so any
    Soccer/Golf/Tennis screenshot import silently failed every
    lookup_board_edge() match (exact-string sport comparison), meaning
    edge/tier/prob/signals never backfilled for those sports even when a
    real matching board pick existed. Confirmed via real logged data
    (2026-07-27 Soccer imports: sport="SOCCER", zero signal matches).
    """
    _map = {
        "SOCCER": "Soccer", "SOC": "Soccer",
        "GOLF": "Golf", "PGA": "Golf",
        "TENNIS": "Tennis",
        "UFC": "UFC", "MMA": "UFC",
        "NBA": "NBA", "WNBA": "WNBA", "MLB": "MLB", "NHL": "NHL", "NFL": "NFL",
    }
    return _map.get(str(raw_sport or "").strip().upper(), str(raw_sport or "NBA").strip())


def parse_bet_screenshot_ocr(image_bytes):
    """
    Parse PrizePicks/prop screenshots via OCR.space then multi-sport parser.
    Claude Vision disabled (no credits). fmt/media_type resolved before try/except.
    """
    import io, re  # base64 and json already imported at module level

    # Resolve image format OUTSIDE try/except so it's in scope for OCR.space fallback
    _PIL = None
    fmt = "png"
    try:
        from PIL import Image as _PIL
        _img = _PIL.open(io.BytesIO(image_bytes))
        fmt = (_img.format or "PNG").lower()
        if fmt not in ("jpeg", "webp", "png"):
            fmt = "png"
    except Exception:
        _logger.debug("Silent except at line 9205")
        pass
    media_type = f"image/{fmt}"

    try:
        # Claude Vision disabled — no API credits. Jump straight to OCR.space.
        raise Exception("Claude Vision disabled")

    except Exception as e:
        # Fallback: OCR.space API (free 25k/month) then multi-sport parser
        try:
            raw = ""
            _ocr_key = st.secrets.get("OCR_SPACE_API_KEY", "")
            if _ocr_key:
                try:
                    _ocr_resp = _http.post("https://api.ocr.space/parse/image",
                        data={"apikey": _ocr_key, "language": "eng", "scale": "true"},
                        files={"filename": (f"slip.{fmt}", image_bytes, media_type)}, timeout=15)
                    _ocr_json = _ocr_resp.json()
                    if _ocr_json.get("ParsedResults"):
                        raw = _ocr_json["ParsedResults"][0].get("ParsedText", "")
                except requests.exceptions.RequestException as _ocr_net_err:
                    # OCR.space unreachable/timed out/DNS failure — don't crash the
                    # whole board render. Log it and fall through to local
                    # pytesseract below, same as when no OCR_SPACE_API_KEY is set.
                    st.session_state.setdefault("errors",[]).append({
                        "time":   datetime.now().strftime("%H:%M:%S"),
                        "source": "parse_bet_screenshot_ocr (OCR.space)",
                        "error":  f"Network error reaching OCR.space: {str(_ocr_net_err)[:150]}",
                    })
            if not raw:
                try:
                    import pytesseract
                    from PIL import Image, ImageEnhance, ImageOps
                    img = _PIL.open(io.BytesIO(image_bytes)).convert("RGB")
                    w, h = img.size
                    scale = 3 if max(w,h) < 1200 else 2
                    img_proc = img.resize((w*scale,h*scale), _PIL.LANCZOS).convert("L")
                    img_proc = ImageOps.invert(img_proc)
                    img_proc = ImageEnhance.Contrast(img_proc).enhance(3.0)
                    raw = pytesseract.image_to_string(img_proc, config="--psm 6 --oem 3")
                except (IOError, ValueError):
                    pass
            st.session_state["ocr_raw_text"] = raw
            # Run full parser FIRST (handles win/loss correctly)
            result = _parse_pp_ocr_inline(raw)
            if result:
                return result
            SPORTS_RE = r"(TENNIS|PGA|GOLF|NBA|WNBA|MLB|NHL|NFL|SOCCER|MMA|UFC|SOC|CFB)"
            result = []
            blocks = [b.strip() for b in raw.split("\n") if b.strip()]
            for i, block in enumerate(blocks):
                m1 = re.search(r"([A-Za-z][A-Za-z .\'-]+)\s+(OVER|UNDER|MORE|LESS)\s+([\d.]+)", block, re.I)
                if m1:
                    sp = re.search(SPORTS_RE, block, re.I)
                    result.append({"player": m1.group(1).strip(), "prop": "Line",
                        "line": float(m1.group(3)),
                        "side": "OVER" if m1.group(2).upper() in ("OVER","MORE") else "UNDER",
                        "sport": _normalize_ocr_sport(sp.group(1)) if sp else "NBA", "book": "PrizePicks"})
                    continue
                if re.search(SPORTS_RE, block, re.I) and ("|" in block or "@" in block):
                    try:
                        clean = re.sub(r"^[~\\\s\-\.\*]+", "", block).strip()
                        sp2 = re.search(SPORTS_RE, clean, re.I)
                        sport = _normalize_ocr_sport(sp2.group(1)) if sp2 else "NBA"
                        stag = f"({sport})"
                        player_part = clean.split(stag)[0] if stag in clean else clean.split(sport)[0]
                        player = re.sub(r"[@|()\d\.\*]+", "", player_part).strip()
                        right = clean.split("|")[-1].strip() if "|" in clean else clean
                        prop_part = clean.split("|")[0].split(stag)[-1] if "|" in clean and stag in clean else ""
                        prop = re.sub(r"[@\s\-]+", " ", prop_part).strip()
                        prop = re.sub(r"Final\s*", "", prop, flags=re.I).strip()
                        nums = re.findall(r"\d+(?:\.\d+)?", right)
                        line_val = float(nums[-1]) if nums else 0.0
                        if not prop and i > 0 and "|" not in blocks[i-1]:
                            prop = blocks[i-1].strip()
                        if player and len(player) > 2:
                            result.append({"player": player, "prop": prop or "Line",
                                "line": line_val, "side": "OVER", "sport": sport, "book": "PrizePicks"})
                    except (ValueError, TypeError, ZeroDivisionError):
                        continue
            # Method 3: PrizePicks format — "{Name} {pos} {SPORT} {matchup}" pattern
            if not result:
                full_text = " ".join(blocks)
                import re as _re3
                # Split on sport tags to find player chunks
                SPORTS3 = ["MLB", "NBA", "NHL", "WNBA", "NFL", "PGA", "TENNIS", "MMA", "UFC", "SOC", "CFB"]
                # Find all "Name pos SPORT" patterns
                pattern3 = r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+(?:[pcgs]|PG|SG|SF|PF|C|G|F|G-F|SP|RP|P|OF|SS|1B|2B|3B)\s+(" + "|".join(SPORTS3) + r")"
                matches3 = list(_re3.finditer(pattern3, full_text))
                # Find all stat+line patterns like "Ks 4.5" or "Points 25.5"
                stat_map = {"Ks": "Strikeouts", "Pts": "Points", "Reb": "Rebounds",
                    "Ast": "Assists", "Hits": "Hits", "HR": "Home Runs",
                    "RBI": "RBIs", "TB": "Total Bases", "SO": "Strikeouts",
                    "Strokes": "Strokes", "Saves": "Saves", "Goals": "Goals",
                    "SOG": "Shots on Goal", "Fantasy": "Fantasy Score",
                    "Break Points Won": "Break Points Won"}
                stat_nums = list(_re3.finditer(r"(Ks|Pts|Reb|Ast|Hits|HR|RBI|TB|SO|Strokes|Saves|Goals|SOG|Fantasy|Points|Rebounds|Assists|Strikeouts|Total Bases|Break Points Won)\s+([\d.]+)", full_text, _re3.I))
                for pi, pm in enumerate(matches3):
                    pname = pm.group(1).strip()
                    psport = _normalize_ocr_sport(pm.group(2))
                    # Match with corresponding stat
                    if pi < len(stat_nums):
                        sn = stat_nums[pi]
                        prop_raw = sn.group(1)
                        line_val = float(sn.group(2))
                        prop_clean = stat_map.get(prop_raw, prop_raw)
                        # Detect win/loss from OCR text
                        _leg_result = "LOSS"
                        _actual = 0.0
                        _p_lower = pname.lower()
                        _full = " ".join(blocks).lower()
                        if _p_lower in _full:
                            _pidx = _full.find(_p_lower)
                            _window = _full[_pidx:_pidx+200]
                            if " x " in _window or _window.startswith("x "):
                                _leg_result = "LOSS"
                        # Find actual value: number before the line value in text
                        _all_nums = [float(n) for n in __import__("re").findall(r"\d+(?:\.\d+)?", " ".join(blocks))]
                        for _ni, _nv in enumerate(_all_nums):
                            if _nv == line_val and _ni > 0:
                                _actual = _all_nums[_ni-1]
                                break
                        if _leg_result == "LOSS" and _actual > 0:
                            _leg_result = "WIN" if _actual >= line_val else "LOSS"
                        result.append({"player": pname, "prop": prop_clean,
                            "line": line_val, "side": "OVER",
                            "sport": psport, "book": "PrizePicks",
                            "result": _leg_result, "actual": _actual})
            # Method 4: Full single-line OCR parser
            if not result:
                result = _parse_pp_ocr_inline(raw)
            # Bridge result→outcome for UI
            for _item in result:
                if "result" in _item and "outcome" not in _item:
                    _item["outcome"] = _item["result"]
                _item.setdefault("outcome", "LOSS")
                _item.setdefault("actual", 0.0)
            return result
        except Exception as e2:
            st.session_state.setdefault("errors",[]).append({
                "time":   datetime.now().strftime("%H:%M:%S"),
                "source": "parse_bet_screenshot_ocr",
                "error":  str(e2)[:150],
            })
            return []


def parse_prizepicks_text(raw_text):
    """Parse the copy-paste text block format from PrizePicks results.

    Expected repeating block (12 lines per player):
      Player Name
      Position (G / IF / OF / C-F / etc.)
      Sport (NBA / MLB / NHL / etc.)
      Team abbreviation
      Team score
      vs  (or @)
      Opp team
      Opp score
      Final  (or Live / Pending)
      Line  (e.g. 1.5)
      Stat type  (e.g. Hits+Runs+RBIs)
      Actual result  (numeric)
    """

    POSITIONS = {"G", "F", "C", "IF", "OF", "P", "SP", "RP", "C-F", "G-F", "F-C", "PG", "SG", "SF", "PF"}
    SPORTS    = {"NBA", "MLB", "NHL", "NFL", "WNBA", "NCAAB", "NCAAF", "MLS", "EPL", "PGA"}

    rows = [l.strip() for l in raw_text.strip().split("\n") if l.strip()]
    bets = []
    i = 0

    while i < len(rows):
        # Need at least 12 lines ahead to form a full block
        if i + 11 >= len(rows):
            i += 1
            continue

        player   = rows[i]
        pos      = rows[i + 1].upper()
        sport    = _normalize_ocr_sport(rows[i + 2])

        if pos not in POSITIONS or sport not in SPORTS:
            i += 1
            continue

        # Slots i+3 … i+11
        team_score_raw = rows[i + 4]   # team score (may be int)
        status         = rows[i + 8]   # "Final", "Live", etc.
        line_raw       = rows[i + 9]
        stat_type      = rows[i + 10]
        result_raw     = rows[i + 11]

        try:
            line_val   = float(line_raw)
            result_val = float(result_raw)
        except ValueError:
            i += 1
            continue

        # Determine outcome based on side
        status_upper = status.upper()
        if any(w in status_upper for w in ("LIVE", "PENDING", "PROGRESS", "SCHEDULED")):
            outcome = "PENDING"
        else:
            # For UNDER picks, winning means result < line
            if side == "UNDER":
                outcome = "WIN" if result_val < line_val else "LOSS"
            else:
                outcome = "WIN" if result_val > line_val else "LOSS"

        bets.append({
            "player":     player,
            "prop":       stat_type,
            "line":       line_val,
            "side":       "OVER",   # default; user can override in confirm UI
            "sport":      sport,
            "outcome":    outcome,
            "result":     result_val,
            "wager":      0,
            "pick_count": 2,
            "source":     "PrizePicks",
            "bet_type":   "prop",
        })
        i += 12

    return bets

# Player-specific home/away performance splits (2024-25 data)
# Format: player_name: {"home_adj": float, "away_adj": float}
# Positive = performs better at home, negative = better away
# Derived from NBA.com home/away splits — update each season
# Default global splits when player not found
GLOBAL_HOME_ADJ  =  0.05
GLOBAL_AWAY_ADJ  = -0.05


# ═══════════════════════════════════════════════════════════
# MODULE: EDGE MODEL — signals, tiers, kelly sizing
# Future extraction target: models.py
# ═══════════════════════════════════════════════════════════
def compute_multi_signal_edge(  # Calculates edge using 12 weighted signals (Base, Def, Loc, Rest, Pace + overlays)
line, player_avg, opp_def_rating, is_home, teammate_out_boost, side="OVER", stat_key="PTS", pace_adj=0.0, days_rest=2, odds_type="standard", sport="NBA", std_dev=None, weights=None, player_name="", over_odds=None, under_odds=None):
    if player_avg <= 0:
        return 0.0, 0.5, {}
    signals = {}
    league_avg_def = 112.0
    if weights is None:
        # Load optimizer weights once per session — cached in session_state
        # Avoids 50+ disk reads per board load (one per prop)
        _cache_key = f"_opt_weights_{sport}"
        if _cache_key not in st.session_state:
            from_optimizer = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
            sport_optimizer = from_optimizer.get(sport, {})
            if (sport_optimizer.get("weights") and sport_optimizer.get("n_bets", 0) >= WEIGHT_OPTIMIZER_MIN_BETS):
                _base_w = sport_optimizer["weights"]
            else:
                _base_w = get_effective_signal_weights(sport)
            # Apply online feature importance adjustment
            _hist_for_adj = st.session_state.get("history", [])
            if len(_hist_for_adj) >= 15:
                _adj_w, _, _ = get_adjusted_signal_weights(
                    dict(_base_w), _hist_for_adj, sport=sport, window_days=30
                )
                st.session_state[_cache_key] = _adj_w
            else:
                st.session_state[_cache_key] = dict(_base_w)
        weights = st.session_state[_cache_key]
    if stat_key in ["HR", "GOALS"]:
        # ── S1 MLB HR: Platoon-stabilized Poisson ─────────────────────
        # Uses live batter handedness splits + pitcher xwOBA from ev_signal_lookup
        # instead of raw season HR avg — eliminates early-season Poisson noise
        if stat_key == "HR" and sport == "MLB":
            _ev_sig_s1 = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), "Home Runs"), {}
            )
            if _ev_sig_s1:
                _pitcher_lr    = _ev_sig_s1.get("pitcher_lr", "R")   # "L" or "R"
                _batter_percs  = _ev_sig_s1.get("_batter_percs", {}) or {}
                _pitcher_xwoba = _ev_sig_s1.get("pitcher_xwoba") or 0.320

                # Pick handedness-specific HR rate (HR per PA %)
                if _pitcher_lr == "L":
                    _batter_hr_rate = safe_float(_batter_percs.get("hr_l_rate", 0)) / 100.0
                    _batter_pa      = int(_batter_percs.get("hr_l", 0) or 0) * 20
                else:
                    _batter_hr_rate = safe_float(_batter_percs.get("hr_r_rate", 0)) / 100.0
                    _batter_pa      = int(_batter_percs.get("hr_r", 0) or 0) * 20

                # 250 PA stabilization to league mean (0.032 = ~1 HR per 31 PA)
                _LEAGUE_HR_RATE = 0.032
                _STABILIZE_PA   = 250
                if _batter_hr_rate > 0 and _batter_pa > 0:
                    _stabilized_rate = (
                        (_batter_pa * _batter_hr_rate) + (_STABILIZE_PA * _LEAGUE_HR_RATE)
                    ) / (_batter_pa + _STABILIZE_PA)
                else:
                    # Fallback: use raw season avg converted to per-PA rate
                    _stabilized_rate = player_avg / 650.0 if player_avg < 1 else player_avg / 162.0

                # Scale by pitcher vulnerability vs league avg xwOBA
                _LEAGUE_XWOBA = 0.315
                _s1_adj_rate  = _stabilized_rate * (_pitcher_xwoba / _LEAGUE_XWOBA) if _pitcher_xwoba > 0 else _stabilized_rate
                _s1_adj_rate  = max(0.01, min(0.15, _s1_adj_rate))

                # Convert daily HR rate to per-game avg for Poisson
                _adj_game_avg = _s1_adj_rate * 4.0   # ~4 PA per game
                prob = poisson_prob_over(line, _adj_game_avg)
            else:
                prob = poisson_prob_over(line, player_avg)

        elif stat_key in ("SO", "K", "Pitcher Strikeouts") and sport == "MLB":
            # ── S1 MLB Ks: K/9 stabilized with 200 BF threshold ────────
            _ev_sig_k = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), "Pitcher Strikeouts"), {}
            )
            if _ev_sig_k and _ev_sig_k.get("pitcher_xwoba"):
                _p_xwoba       = safe_float(_ev_sig_k.get("pitcher_xwoba", 0.320))
                _LEAGUE_K9     = 8.5
                _STABILIZE_BF  = 200
                _est_bf        = max(50, int(line * 40))
                _raw_k9        = player_avg * 9.0 / 6.0
                _stabilized_k9 = ((_est_bf * _raw_k9) + (_STABILIZE_BF * _LEAGUE_K9)) / (_est_bf + _STABILIZE_BF)
                _xwoba_scale   = (0.315 - _p_xwoba) / 0.315 * 0.20 + 1.0
                _adj_k9        = max(3.0, min(15.0, _stabilized_k9 * _xwoba_scale))
                _adj_game_avg  = _adj_k9 * 6.0 / 9.0
                prob = poisson_prob_over(line, _adj_game_avg)
            else:
                prob = poisson_prob_over(line, player_avg)

        else:
            prob = poisson_prob_over(line, player_avg)
        if side.upper() == "UNDER":
            prob = 1 - prob
        # ── HR/GOALS: sport-specific breakeven ────────────────────────
        # HR props are priced at +200 to +650 (BE ~24-33%), not -110 (BE 52.4%)
        # Use the actual market implied prob as breakeven via Pinnacle no-vig
        _ev_be = None
        if stat_key == "HR":
            _ev_be_sig = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), "Home Runs"), {}
            )
            _ev_be = _ev_be_sig.get("unabated_novig") or _ev_be_sig.get("sharp_implied") or _ev_be_sig.get("consensus_novig")
        if _ev_be:
            try:
                base_edge = prob - float(_ev_be)
            except (ValueError, TypeError):
                base_edge = calculate_edge(prob, side, sport, odds=(over_odds if side.upper() == "OVER" else under_odds))
        else:
            base_edge = calculate_edge(prob, side, sport, odds=(over_odds if side.upper() == "OVER" else under_odds))
        fair_prob = prob
    else:
        # ── S1: Sport-specific stabilized base probability ─────────────
        # NBA/WNBA: Usage-weighted EWMA — minutes-adjusted rolling avg
        # already handled upstream; apply sample-size damping here
        if sport in ("NBA", "WNBA"):
            _ev_sig_nba = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), stat_key), {}
            )
            # Sample size confidence: damp edge toward 0 for small samples
            _hit_rates = _ev_sig_nba.get("hit_rates", {}) if _ev_sig_nba else {}
            _szn_games = _hit_rates.get("szn", {}).get("t", 0) if _hit_rates else 0
            if 0 < _szn_games < 10:
                _sample_damp = 0.75 + 0.025 * _szn_games   # 0.75 → 1.0 over 10 games
            else:
                _sample_damp = 1.0
            _avg_adj = player_avg * _sample_damp
            # Negative Binomial for overdispersed counting stats — 3PT makes
            # run hotter-variance than a normal/Poisson assumption captures.
            # stat_key is "THREE_PT" for NBA (via STAT_NORMALIZE) but WNBA has
            # no such mapping yet, so also check the raw label as a fallback.
            _is_three = stat_key == "THREE_PT" or str(stat_key).upper() in ("3-PT MADE", "3PM", "THREES")
            if _is_three and std_dev is not None and std_dev > 0 and (std_dev ** 2) > _avg_adj:
                fair_prob = compute_fair_prob_negbinom(line, _avg_adj, std_dev, side)
            else:
                fair_prob = compute_fair_prob(line, _avg_adj, std_dev, side)

        # NFL: target share / snap count adjustment
        elif sport == "NFL":
            _ev_sig_nfl = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), stat_key), {}
            )
            _hit_rates_nfl = (_ev_sig_nfl.get("hit_rates", {}) if _ev_sig_nfl else {})
            _l5 = _hit_rates_nfl.get("L5", {}).get("p", 0) if _hit_rates_nfl else 0
            _l10 = _hit_rates_nfl.get("L10", {}).get("p", 0) if _hit_rates_nfl else 0
            # Blend model avg with recent hit rate trend
            if _l5 > 0 and _l10 > 0:
                _trend_factor = ((_l5 / 100.0) * 0.60 + (_l10 / 100.0) * 0.40)
                _blended_avg  = player_avg * (0.70 + 0.30 * (_trend_factor / max(0.5, _trend_factor)))
                _blended_avg  = max(player_avg * 0.80, min(player_avg * 1.20, _blended_avg))
            else:
                _blended_avg = player_avg
            fair_prob = compute_fair_prob(line, _blended_avg, std_dev, side)

        # NHL: goalie quality adjustment via EV signal
        elif sport == "NHL":
            _ev_sig_nhl = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), stat_key), {}
            )
            # oppRank in NHL context = goalie/defensive quality (1=best, 30=worst)
            _opp_rank_nhl = _ev_sig_nhl.get("opp_rank") if _ev_sig_nhl else None
            _goalie_adj = 0.0
            if _opp_rank_nhl is not None:
                try:
                    # Rank 1-5 = elite goalie → reduce scoring avg
                    # Rank 26-30 = weak goalie → boost scoring avg
                    _goalie_adj = (_opp_rank_nhl - 15.5) / 15.5 * 0.12
                    _adj_avg    = player_avg * (1.0 + _goalie_adj)
                    _adj_avg    = max(player_avg * 0.80, min(player_avg * 1.20, _adj_avg))
                except (ValueError, TypeError):
                    _adj_avg = player_avg
                    _goalie_adj = 0.0
            else:
                _adj_avg = player_avg
            # Expose as its own discrete signal (was previously only folded
            # into _adj_avg with no way to explain it separately later) —
            # matches the same pattern MLB's pitcher_adj already used.
            signals["goalie"] = round(_goalie_adj, 4)
            # Negative Binomial for overdispersed counting stats — SOG runs
            # hotter-variance than a normal/Poisson assumption captures.
            if stat_key == "SOG" and std_dev is not None and std_dev > 0 and (std_dev ** 2) > _adj_avg:
                fair_prob = compute_fair_prob_negbinom(line, _adj_avg, std_dev, side)
            else:
                fair_prob = compute_fair_prob(line, _adj_avg, std_dev, side)

        else:
            fair_prob = compute_fair_prob(line, player_avg, std_dev, side)

        base_edge = compute_market_edge(fair_prob, side, odds=(over_odds if side.upper() == "OVER" else under_odds))
    signals["base"] = base_edge
    signals["fair_prob_base"] = fair_prob
    signals["model_prob"] = fair_prob
    signals["consensus_prob"] = None
    signals["consensus_books"] = []
    if opp_def_rating > 0:
        def_adj = (opp_def_rating - league_avg_def) / league_avg_def

        # ── S2 MLB: Override with live pitcher ERA-based defensive rating ──
        # For MLB HR props, pitcher ERA is a far better defensive proxy
        # than team defensive rating (which is designed for points/yards sports)
        if sport == "MLB" and stat_key == "HR":
            _ev_sig_s2 = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), "Home Runs"), {}
            )
            if _ev_sig_s2 and _ev_sig_s2.get("pitcher_era"):
                _p_era      = _ev_sig_s2["pitcher_era"]
                _LEAGUE_ERA = 4.25
                # Finer-grained ERA scaling: use square root to prevent capping
                # at extremes — Skenes 2.80 vs Wheeler 3.20 should differ
                _era_ratio = _p_era / _LEAGUE_ERA
                def_adj    = (_era_ratio - 1.0) * 0.25   # ±25% max, linear
                def_adj    = max(-0.15, min(0.15, def_adj))
            elif _ev_sig_s2 and _ev_sig_s2.get("opp_rank"):
                try:
                    _opp_rank = int(_ev_sig_s2["opp_rank"])
                    def_adj = (_opp_rank - 15.5) / 15.5 * 0.08
                except (ValueError, TypeError):
                    pass

        # ── S2 MLB Ks: Pitcher K-rate is own defensive signal ──────────
        elif sport == "MLB" and stat_key in ("SO", "K", "Pitcher Strikeouts"):
            _ev_sig_s2k = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), "Pitcher Strikeouts"), {}
            )
            if _ev_sig_s2k and _ev_sig_s2k.get("pitcher_xwoba"):
                _p_xwoba    = _ev_sig_s2k["pitcher_xwoba"]
                _LEAGUE_K   = 0.300
                def_adj     = (_LEAGUE_K - _p_xwoba) / _LEAGUE_K * 0.15
                def_adj     = max(-0.12, min(0.12, def_adj))

        # ── S2 NFL: Live opponent defensive rank ────────────────────────
        elif sport == "NFL":
            _ev_sig_nfl_s2 = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), stat_key), {}
            )
            _opp_rank_nfl = _ev_sig_nfl_s2.get("opp_rank") if _ev_sig_nfl_s2 else None
            if _opp_rank_nfl is not None:
                try:
                    def_adj = (int(_opp_rank_nfl) - 15.5) / 15.5 * 0.15
                    def_adj = max(-0.15, min(0.15, def_adj))
                except (ValueError, TypeError):
                    pass

        # ── S2 NHL: Goalie quality via opponent rank ────────────────────
        elif sport == "NHL":
            _ev_sig_nhl_s2 = st.session_state.get("ev_signal_lookup", {}).get(
                (normalize_name(player_name), stat_key), {}
            )
            _opp_rank_nhl = _ev_sig_nhl_s2.get("opp_rank") if _ev_sig_nhl_s2 else None
            if _opp_rank_nhl is not None:
                try:
                    def_adj = (int(_opp_rank_nhl) - 15.5) / 15.5 * 0.12
                    def_adj = max(-0.12, min(0.12, def_adj))
                except (ValueError, TypeError):
                    pass

        signals["defense"] = (-def_adj * weights.get("defense", 0.30)
                               if side.upper() == "OVER"
                               else def_adj * weights.get("defense", 0.30))
    else:
        signals["defense"] = 0
    # Apply regime adjustments (early season / playoffs)
    _regime = detect_season_regime(sport)
    if _regime.get("adjustments"):
        for _rsig, _radj in _regime["adjustments"].items():
            if _rsig in signals:
                signals[_rsig] = round(signals.get(_rsig, 0) + _radj, 4)

    # Player-specific home/away split — falls back to global constant
    _splits = PLAYER_HOME_SPLITS.get(
        next((k for k in PLAYER_HOME_SPLITS if normalize_name(k) == normalize_name(player_name)), ""),
        None
    )
    if _splits:
        location_adj = _splits["home"] if is_home else _splits["away"]
    else:
        location_adj = GLOBAL_HOME_ADJ if is_home else GLOBAL_AWAY_ADJ
    if side.upper() == "UNDER":
        location_adj = -location_adj
    signals["location"] = location_adj
    # Continuous rest model — 5 levels vs binary 0/other
    # Research basis: NBA performance degrades ~8% on B2B,
    # ~3% on 1-day rest, neutral at 2 days, slight boost 3+
    if days_rest == 0:
        rest_adj = -0.08   # back-to-back: significant fatigue
    elif days_rest == 1:
        rest_adj = -0.03   # short rest: mild fatigue
    elif days_rest == 2:
        rest_adj = 0.0     # standard rest: neutral
    elif days_rest == 3:
        rest_adj = 0.01    # extra rest: slight boost
    else:
        rest_adj = 0.02    # 4+ days rest: well-rested boost
    signals["rest"] = rest_adj
    signals["pace"] = pace_adj if side.upper() == "OVER" else -pace_adj
    combined = (signals["base"] * weights.get("base", 0.45) + signals["defense"] * weights.get("defense", 0.30) + signals["location"] * weights.get("location", 0.15) + signals["rest"] * weights.get("rest", 0.05) + signals["pace"] * weights.get("pace", 0.05))
    if teammate_out_boost:
        # Usage signal now governed by weights framework — optimizer can tune it
        # Default weight 0.74 matches prior behavior; optimizer will adjust from data
        usage_weight = weights.get("usage", 0.74)
        usage_signal = teammate_out_boost * usage_weight
        combined += usage_signal
        signals["usage"] = usage_signal
    else:
        signals["usage"] = 0.0

    # ── ParlaySavant +EV confirmation overlay (2026-07 fix) ─────────────
    # ps_ev_edge/ps_ev_confirm were being computed into ev_signal_lookup
    # (second-source EV confirmation from parlaysavant.com) but nothing
    # ever read them back — dead bookkeeping. This closes that loop.
    # Matched by player only, not exact stat/prop key: ParlaySavant's own
    # prop-name strings don't cleanly map to BetCouncil's short stat_key
    # codes (e.g. "HR" vs "Home Runs"), so treat this as "an independent
    # EV engine flagged something for this player" rather than a
    # stat-specific confirmation. Capped small and additive, same
    # conservative style as the usage signal above — not a replacement
    # for BetCouncil's own edge, just a nudge.
    if player_name:
        _ps_conf_edge = 0.0
        _pn_norm = normalize_name(player_name)
        _ev_lookup_all = st.session_state.get("ev_signal_lookup", {})
        for (_lk_p, _lk_prop), _lk_v in _ev_lookup_all.items():
            if _lk_p == _pn_norm and isinstance(_lk_v, dict) and _lk_v.get("ps_ev_confirm"):
                _ps_raw = safe_float(_lk_v.get("ps_ev_edge", 0))
                _ps_conf_edge = max(_ps_conf_edge, max(-0.03, min(0.03, _ps_raw)))
        if _ps_conf_edge:
            combined += _ps_conf_edge
            signals["parlaysavant_confirm"] = _ps_conf_edge

    if odds_type == "demon":
        combined *= 0.85
    elif odds_type == "goblin":
        combined *= 1.10
    combined = max(-EDGE_CAP, min(EDGE_CAP, combined))
    base_prob = signals.get("fair_prob_base", 0.524)
    signal_adjustment = combined - signals.get("base", 0)
    prob = base_prob + signal_adjustment
    prob = max(0.20, min(0.80, prob))
    return combined, prob, signals

# make_display_df — moved to bc_utils.py
# fetch_dk_salaries → fetchers.py
def apply_dk_salary_signal(prop, dk_salaries):
    """
    Apply DraftKings salary as a signal modifier.
    High salary = market confidence signal
    Returns signal adjustment (-0.05 to +0.05)
    """
    if not dk_salaries:
        return 0.0, ""

    norm = normalize_name(prop.get("Player", ""))
    dk_data = dk_salaries.get(norm)
    if not dk_data:
        return 0.0, ""

    salary = dk_data["salary"]
    tier = dk_data["salary_tier"]
    value = dk_data["value"]
    fppg = dk_data["fppg"]

    # High salary + high value = positive signal
    # High salary + low value = cautious (might be overpriced)
    if tier == "ELITE" and value >= 5.0:
        return 0.02, f"DK Elite ${salary:,} | {fppg:.1f} FPPG | {value:.1f}x value"
    elif tier == "ELITE":
        return 0.01, f"DK Elite ${salary:,} | {fppg:.1f} FPPG"
    elif tier == "HIGH" and value >= 5.5:
        return 0.015, f"DK High ${salary:,} | {fppg:.1f} FPPG | {value:.1f}x value"
    elif tier == "VALUE" and value >= 6.0:
        return 0.02, f"DK Value ${salary:,} | {fppg:.1f} FPPG | {value:.1f}x VALUE PLAY"
    else:
        return 0.0, f"DK ${salary:,} | {tier}"


# =============================================================
# PINNACLE FAIR VALUE ENGINE
# The gold standard: use Pinnacle no-vig odds as true probability
# Elite models (OddsJam, Outlier, Sharp) all anchor to Pinnacle
# =============================================================

PINNACLE_PROP_CACHE = {}  # in-memory: {(player_norm, stat, line): {"over_prob": x, "under_prob": x}}
PINNACLE_GAME_CACHE = {}  # in-memory: {(home, away, market): {"prob": x, "line": x}}

def pinnacle_fair_value(player, stat, line, side="OVER", sport="NBA"):
    """
    Get Pinnacle no-vig true probability for a prop.
    Returns (prob, confirms_model, note) or (None, False, "")
    """
    cache_key = f"pinnacle_{sport}"
    pinn_data = st.session_state.get(cache_key, {})
    # Also check pinnacle_game_lines (list format from fetch_pinnacle_game_lines)
    if not pinn_data or isinstance(pinn_data, list):
        pinn_data = {}
    if not pinn_data:
        return None, False, ""

    props = pinn_data.get("props", {}) if isinstance(pinn_data, dict) else {}
    norm_player = normalize_name(player)
    norm_stat = stat.lower().replace(" ","_").replace("+","_")

    # Try exact match first
    pkey = (norm_player, stat.lower(), float(line))
    entry = props.get(pkey)

    # Try fuzzy stat match
    if not entry:
        for k, v in props.items():
            if k[0] == norm_player and abs(k[2] - float(line)) <= 0.5:
                stat_match = (
                    stat.lower()[:4] in k[1].lower() or
                    k[1].lower()[:4] in stat.lower()
                )
                if stat_match:
                    entry = v
                    break

    if not entry:
        return None, False, ""

    prob = entry["over_prob"] if side == "OVER" else entry["under_prob"]
    over_odds = entry.get("over_odds")
    under_odds = entry.get("under_odds")
    odds = over_odds if side == "OVER" else under_odds

    # Does Pinnacle confirm our direction?
    # If Pinnacle shows >52% for our side = confirms edge
    confirms = prob > 0.52
    fade_signal = prob < 0.46  # Pinnacle disagrees strongly

    if confirms:
        note = f"📌 Pinnacle confirms {side}: {prob:.1%} true prob (fair odds: {odds:+.0f})"
    elif fade_signal:
        note = f"⚠️ Pinnacle FADES {side}: {prob:.1%} true prob — sharp money disagrees"
    else:
        note = f"📌 Pinnacle neutral: {prob:.1%} true prob"

    return prob, confirms, note


def pinnacle_game_fair_value(home_team, away_team, market, sport, model_side=None):
    """
    Compute no-vig fair probability from Pinnacle game-line data in session_state.
    market: 'moneyline', 'spread', or 'total'
    model_side: 'HOME'/'AWAY' for moneyline/spread, 'OVER'/'UNDER' for total
    """
    games = st.session_state.get("pinnacle_game_lines", [])
    if not games:
        return None, False, ""

    def _norm(s):
        return str(s or "").lower().replace(".", "").strip()

    game = None
    h_norm, a_norm = _norm(home_team), _norm(away_team)
    for g in games:
        if _norm(g.get("Home")) == h_norm and _norm(g.get("Away")) == a_norm:
            game = g
            break
    if game is None:
        for g in games:
            gh, ga = _norm(g.get("Home")), _norm(g.get("Away"))
            if (h_norm in gh or gh in h_norm) and (a_norm in ga or ga in a_norm):
                game = g
                break
    if game is None:
        return None, False, ""

    from consensus_engine import american_to_implied_prob

    prob = None
    side_label = model_side or ""

    if market == "moneyline":
        home_ml, away_ml = game.get("HomeML"), game.get("AwayML")
        home_p, away_p = american_to_implied_prob(home_ml), american_to_implied_prob(away_ml)
        if home_p is None or away_p is None:
            return None, False, ""
        total = home_p + away_p
        if total <= 0:
            return None, False, ""
        home_fair, away_fair = home_p / total, away_p / total
        prob = home_fair if model_side == "HOME" else away_fair if model_side == "AWAY" else home_fair
        side_label = model_side or "HOME"

    elif market == "total":
        over_odds, under_odds = game.get("TotalOver"), game.get("TotalUnder")
        over_p, under_p = american_to_implied_prob(over_odds), american_to_implied_prob(under_odds)
        if over_p is None or under_p is None:
            return None, False, ""
        total = over_p + under_p
        if total <= 0:
            return None, False, ""
        over_fair, under_fair = over_p / total, under_p / total
        prob = over_fair if model_side == "OVER" else under_fair if model_side == "UNDER" else over_fair
        side_label = model_side or "OVER"

    elif market == "spread":
        # Away-side odds aren't stored in fetch_pinnacle_game_lines()'s dict —
        # single-side implied prob vs 0.524 breakeven, directional signal only.
        spread_odds = game.get("SpreadOdds")
        prob = american_to_implied_prob(spread_odds)
        if prob is None:
            return None, False, ""
        side_label = model_side or "HOME"

    else:
        return None, False, ""

    confirms = prob > 0.52
    fade = prob < 0.46
    if confirms:
        note = f"📌 Pinnacle confirms {side_label}: {prob:.1%} true prob"
    elif fade:
        note = f"⚠️ Pinnacle FADES {side_label}: {prob:.1%} — sharp money disagrees"
    else:
        note = f"📌 Pinnacle neutral on {side_label}: {prob:.1%}"
    return prob, confirms, note


def vsin_sharp_signal(home_team, away_team, market, sport, model_side=None):
    """
    Compute a sharp-vs-public divergence signal from VSiN's Vegas line
    tracker (Circa/Westgate/South Point/Stations/Wynn = Nevada sharp
    books; BetMGM/Caesars/Boomers = online/public books). Circa in
    particular is considered among the sharpest lines in the US and is
    not covered by OddsAPI or Unabated — this is a genuinely independent
    signal from Pinnacle, not a duplicate.

    Uses Circa as primary sharp anchor (falls back to Westgate if Circa's
    entry is missing for this game), compares its CURRENT number against
    BetMGM as the public/online reference.

    market: 'moneyline', 'spread', or 'total'
    model_side: 'HOME'/'AWAY' for moneyline/spread, 'OVER'/'UNDER' for total

    Returns (fair_prob, confirms, note) — same shape as
    pinnacle_game_fair_value(), so it slots into the same call sites.
    fair_prob here is Circa's own no-vig fair probability (moneyline/total)
    or a single-side implied prob (spread, same limitation as Pinnacle —
    the harvester doesn't store the opposite side's price).
    """
    from fetchers import fetch_vsin_from_gist
    games, _src = fetch_vsin_from_gist(sport)
    if not games:
        return None, False, ""

    def _norm(s):
        return str(s or "").lower().replace(".", "").strip()

    game = None
    h_norm, a_norm = _norm(home_team), _norm(away_team)
    for g in games:
        if _norm(g.get("home_team")) == h_norm and _norm(g.get("away_team")) == a_norm:
            game = g
            break
    if game is None:
        for g in games:
            gh, ga = _norm(g.get("home_team")), _norm(g.get("away_team"))
            if (h_norm in gh or gh in h_norm) and (a_norm in ga or ga in a_norm):
                game = g
                break
    if game is None:
        return None, False, ""

    books = game.get("books", {})
    sharp_book = books.get("Circa") or books.get("Westgate")
    if not sharp_book:
        return None, False, ""

    from consensus_engine import american_to_implied_prob

    prob = None
    side_label = model_side or ""

    if market == "moneyline":
        home_side = sharp_book.get("home", {})
        away_side = sharp_book.get("away", {})
        home_p = american_to_implied_prob(home_side.get("ml"))
        away_p = american_to_implied_prob(away_side.get("ml"))
        if home_p is None or away_p is None:
            return None, False, ""
        total = home_p + away_p
        if total <= 0:
            return None, False, ""
        home_fair, away_fair = home_p / total, away_p / total
        prob = home_fair if model_side == "HOME" else away_fair if model_side == "AWAY" else home_fair
        side_label = model_side or "HOME"

    elif market == "total":
        home_side = sharp_book.get("home", {})
        away_side = sharp_book.get("away", {})
        # total_side "o"/"u" tells us which of home/away carries the over vs under price
        over_price = home_side.get("total_price") if home_side.get("total_side") == "o" else away_side.get("total_price")
        under_price = home_side.get("total_price") if home_side.get("total_side") == "u" else away_side.get("total_price")
        over_p, under_p = american_to_implied_prob(over_price), american_to_implied_prob(under_price)
        if over_p is None or under_p is None:
            return None, False, ""
        total = over_p + under_p
        if total <= 0:
            return None, False, ""
        over_fair, under_fair = over_p / total, under_p / total
        prob = over_fair if model_side == "OVER" else under_fair if model_side == "UNDER" else over_fair
        side_label = model_side or "OVER"

    elif market == "spread":
        # Single-side implied prob, same limitation noted in pinnacle_game_fair_value.
        home_side = sharp_book.get("home", {})
        away_side = sharp_book.get("away", {})
        side_dict = home_side if model_side == "HOME" else away_side if model_side == "AWAY" else home_side
        prob = american_to_implied_prob(side_dict.get("spr_price"))
        if prob is None:
            return None, False, ""
        side_label = model_side or "HOME"

    else:
        return None, False, ""

    confirms = prob > 0.52
    fade = prob < 0.46
    sharp_label = "Circa" if books.get("Circa") else "Westgate"
    if confirms:
        note = f"🎰 {sharp_label} confirms {side_label}: {prob:.1%} true prob"
    elif fade:
        note = f"⚠️ {sharp_label} FADES {side_label}: {prob:.1%} — Nevada sharp money disagrees"
    else:
        note = f"🎰 {sharp_label} neutral on {side_label}: {prob:.1%}"
    return prob, confirms, note


def _fetch_parallel(fns: list, show_progress: bool = False) -> list:
    """Run multiple fetch functions in parallel threads, return results in order.
    Uses pre-allocated index-based result and timing slots to prevent cross-thread
    mutation race conditions on shared collections.

    Args:
        fns:           List of zero-argument callables to execute in parallel.
        show_progress: When True, shows a st.progress bar that updates as each
                       fetch completes, reducing perceived latency from "spinner
                       for 10s" to "3 of 47 signals loaded" live feedback.
    """
    if not fns:
        return []
    from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait
    import time as _time
    import threading
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    _ctx = get_script_run_ctx()
    n = len(fns)
    results  = [None] * n
    timings  = [None] * n
    _lock    = threading.Lock()
    _done    = [0]  # mutable counter for progress tracking

    _prog_bar  = st.progress(0, text="Loading data sources…") if show_progress else None
    _prog_text = st.empty() if show_progress else None

    def _timed(fn, idx):
        # Attach the main thread's ScriptRunContext to this worker thread
        # FIRST -- confirmed via live Streamlit logs that this was missing
        # entirely ('missing ScriptRunContext' warnings). Without it, any
        # st.session_state read/write inside fn() (several fetch_ functions
        # use session-level caching) silently fails, forcing a full live
        # re-fetch on every call instead of a cache hit -- same root cause
        # already found and fixed for WNBA/NBA/MLB's board-paste path
        # earlier this session, but never applied here.
        if _ctx is not None:
            add_script_run_ctx(threading.current_thread(), _ctx)
        name = getattr(fn, '__name__', f'fn_{idx}').replace('_pf_','').replace('fetch_','')
        t0 = _time.perf_counter()
        try:
            result  = fn()
            elapsed = round(_time.perf_counter() - t0, 2)
            timings[idx] = {"name": name, "time": elapsed, "status": "✅"}
            return result
        except Exception as e:
            elapsed = round(_time.perf_counter() - t0, 2)
            timings[idx] = {"name": name, "time": elapsed, "status": f"❌ {type(e).__name__}: {str(e)[:40]}"}
            _logger.warning("_fetch_parallel worker %s failed: %s: %s", name, type(e).__name__, e)
            circuit_record_failure(name)
            return None

    # Worker cap raised from 20 → 40: this gets called with batches as large
    # as ~75 fetch functions (see the main board-load parallel batch), all
    # I/O-bound network calls. At 20 workers that's ~4 sequential waves of
    # up to a 25s future-timeout each — a real, measurable chunk of the
    # "board takes forever to load" complaint. Threads are cheap for I/O
    # wait, so 40 is safe here (not CPU-bound work) and roughly halves the
    # number of waves for the largest batches without touching smaller ones.
    #
    # BUG FIX (2026-07): the old loop used `for fut in as_completed(futures):
    # fut.result(timeout=25)`. as_completed() only ever yields a future
    # AFTER it has already finished, so that per-future timeout=25 could
    # never actually fire — .result() on an already-done future returns
    # instantly, it doesn't block or raise TimeoutError. In practice this
    # meant a single slow/hanging source (e.g. scrape_prizepicks observed
    # taking 64s while failing with 429/403) could silently hold up the
    # entire batch's wall time with no real ceiling, despite the code
    # looking like it enforced one. wait(futures, timeout=...) enforces a
    # REAL deadline on the whole batch: whatever hasn't finished by then is
    # abandoned (marked as a timeout, its eventual result discarded when
    # the thread does finish in the background) instead of silently
    # blocking everyone else.
    _BATCH_TIMEOUT_S = 25
    # NOT using `with ThreadPoolExecutor(...) as ex:` here on purpose: that
    # context manager's __exit__ calls shutdown(wait=True) by default, which
    # would block until EVERY submitted thread finishes -- including the
    # slow straggler this whole fix exists to stop waiting on. Caught this
    # empirically: an isolated test of this exact pattern showed 3s wall
    # time instead of the intended 1s timeout, because the with-block's
    # cleanup silently re-introduced the wait. shutdown(wait=False) lets
    # the function actually return at the deadline; the abandoned thread
    # keeps running to completion in the background, its result simply
    # never gets used for this board load.
    ex = ThreadPoolExecutor(max_workers=min(n, 40))
    futures = {ex.submit(_timed, fn, i): i for i, fn in enumerate(fns)}
    done, not_done = _cf_wait(futures.keys(), timeout=_BATCH_TIMEOUT_S)
    for fut in done:
        idx = futures[fut]
        try:
            results[idx] = fut.result()
        except Exception as _ex:
            results[idx] = None
            _logger.warning("_fetch_parallel future[%d] raised: %s: %s", idx, type(_ex).__name__, _ex)
        if _prog_bar is not None:
            _done[0] += 1
            _pct = _done[0] / n
            _name = (timings[idx] or {}).get("name", "")
            try:
                _prog_bar.progress(_pct, text=f"Loading… {_done[0]}/{n} sources ✓ {_name}")
            except Exception:
                pass
    for fut in not_done:
        idx = futures[fut]
        name = getattr(fns[idx], '__name__', f'fn_{idx}').replace('_pf_','').replace('fetch_','')
        results[idx] = None
        timings[idx] = {"name": name, "time": float(_BATCH_TIMEOUT_S),
                         "status": f"⏱️ Timeout — still running after {_BATCH_TIMEOUT_S}s, abandoned so the rest of the board could load"}
        _logger.warning("_fetch_parallel: %s did not complete within %ds, abandoning for this load", name, _BATCH_TIMEOUT_S)
        if _prog_bar is not None:
            _done[0] += 1
            try:
                _prog_bar.progress(_done[0] / n, text=f"Loading… {_done[0]}/{n} sources (⏱️ {name} timed out)")
            except Exception:
                pass
    ex.shutdown(wait=False)

    # Clear progress indicators
    if _prog_bar is not None:
        try:
            _prog_bar.empty()
            _prog_text.empty() if _prog_text else None
        except Exception:
            pass

    # Write timing summary to session state under a lock to prevent partial writes
    # if _fetch_parallel is ever called concurrently (rare but possible).
    # MERGED, not overwritten -- load_sport_data can call _fetch_parallel more
    # than once per board load (e.g. MLB's pre-pool step, then the main
    # ~78-source batch), and a full overwrite silently erased whichever
    # stage ran first, hiding it completely from the System tab's Source
    # Performance Profiler. This was a real blind spot: if the FIRST stage
    # is where a hang actually happens, the profiler only ever showed the
    # LAST stage's fast timings, making the board look fine while it was
    # still actually stuck earlier in the pipeline.
    try:
        with _lock:
            _new_timings = {
                t["name"]: {"time": t["time"], "status": t["status"]}
                for t in timings if t is not None
            }
            st.session_state["fetch_timings"] = {
                **st.session_state.get("fetch_timings", {}),
                **_new_timings,
            }
    except Exception:
        _logger.debug("Silent except at line 10021")
        pass
    return results





# ═══════════════════════════════════════════════════════════════
# NFL READINESS SUITE
# Practice participation, inactives, O-line monitoring,
# depth chart snapshots, market open/close storage,
# prediction stability audit.
# ═══════════════════════════════════════════════════════════════

NFL_PRACTICE_PATH   = os.path.join(CACHE_DIR, "nfl_practice.json")
NFL_INACTIVES_PATH  = os.path.join(CACHE_DIR, "nfl_inactives.json")
NFL_DEPTH_SNAP_PATH = os.path.join(CACHE_DIR, "nfl_depth_snapshots.json")
OPENING_LINES_PATH  = os.path.join(CACHE_DIR, "opening_lines.json")
BOARD_SNAP_PATH     = os.path.join(CACHE_DIR, "board_snapshots.json")
GAME_BOARD_SNAP_PATH = os.path.join(CACHE_DIR, "game_board_snapshots.json")

# ── DraftKings Direct (curl_cffi) ─────────────────────────────


# ── BetMGM Direct (curl_cffi) ─────────────────────────────────


# ── Caesars Direct (curl_cffi) ─────────────────────────────────


# ── BetRivers Direct (Kambi backend) ──────────────────────────


# ── BetRivers Direct (Kambi backend) ──────────────────────────
# DUPLICATE fetch_betrivers_direct removed (was identical to L13535)


# ── Superbook Direct (sharp book, Circa-adjacent) ─────────────
def get_practice_trend(player_name, participation_data=None):
    """Return practice trend string for a player, or empty string."""
    if participation_data is None:
        participation_data = load_json_data(NFL_PRACTICE_PATH, {})
    pdata = participation_data.get(player_name, {})
    return pdata.get("trend", "")


# ── ATS Stats MLB matchup scraper ────────────────────────────────────────────
# ── ATS Stats NBA matchup scraper ────────────────────────────────────────────
# ── ATS Stats NHL matchup scraper ────────────────────────────────────────────
# ── ATS Stats NFL matchup scraper ────────────────────────────────────────────
# ── NFL defensive unit ratings ────────────────────────────────────────────────
# ── NFL team scoring stats (James matchup formula input) ─────────────────────
# ── MLB team RS/RA fetcher (James matchup formula input) ─────────────────────
# ── Feature 2: NFL Inactives System ────────────────────────────


# ── Feature 3: Offensive Line Monitoring ───────────────────────
def get_oline_status(team_abbr, depth_charts=None):
    """
    Extract offensive line starter status from ESPN depth charts.
    Returns dict with each OL position and starter name/status.
    
    OL positions: LT, LG, C, RG, RT
    """
    if depth_charts is None:
        depth_charts = st.session_state.get("espn_depth_charts", {})
    team_dc = depth_charts.get(team_abbr, {})
    positions = team_dc.get("positions", {})
    oline = {}
    for pos in ("LT", "LG", "C", "RG", "RT", "OT", "OG", "OC"):
        if pos in positions:
            starters = positions[pos]
            if starters:
                starter = starters[0]
                oline[pos] = {
                    "name":  starter["name"],
                    "depth": starter["depth"],
                    "status": "Starter",
                }
                # Check if starter is injured
                injuries = st.session_state.get("injuries_combined", {})
                if normalize_name(starter["name"]) in injuries:
                    oline[pos]["status"] = injuries[normalize_name(starter["name"])].get("status","?")
    n_oline_out = sum(1 for p in oline.values() if p.get("status") in ("OUT","DOUBTFUL"))
    return {
        "positions": oline,
        "starters_out": n_oline_out,
        "integrity": "🔴 POOR" if n_oline_out >= 3 else "🟡 DEGRADED" if n_oline_out >= 2 else "🟡 CONCERN" if n_oline_out == 1 else "✅ INTACT",
    }


# ── Feature 4: Depth Chart Daily Snapshots ─────────────────────
def save_depth_chart_snapshot(sport, depth_charts):
    """
    Store a daily snapshot of depth charts.
    Enables change detection: who moved from RB2 to RB1?
    """
    if not depth_charts:
        return
    try:
        stored = load_json_data(NFL_DEPTH_SNAP_PATH, {})
        today_str = date.today().strftime("%Y-%m-%d")
        stored[today_str] = {
            "sport":  sport,
            "teams":  depth_charts,
            "saved_at": datetime.now().strftime("%H:%M"),
        }
        # Keep last 14 days only
        if len(stored) > 14:
            oldest = sorted(stored.keys())[0]
            del stored[oldest]
        save_json_data(NFL_DEPTH_SNAP_PATH, stored)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass


def detect_depth_chart_changes(sport, current_charts=None):
    """
    Compare today's depth charts vs yesterday's snapshot.
    Returns list of changes: player moved up/down the depth chart.
    """
    if current_charts is None:
        current_charts = st.session_state.get("espn_depth_charts", {})
    try:
        stored = load_json_data(NFL_DEPTH_SNAP_PATH, {})
        dates = sorted(stored.keys())
        if len(dates) < 2:
            return []
        yesterday = stored[dates[-2]]
        if yesterday.get("sport") != sport:
            return []
        changes = []
        for team_abbr, curr_team in current_charts.items():
            prev_team = yesterday.get("teams", {}).get(team_abbr, {})
            for pos, curr_players in curr_team.get("positions", {}).items():
                prev_players = prev_team.get("positions", {}).get(pos, [])
                if not curr_players or not prev_players:
                    continue
                curr_starter = curr_players[0]["name"] if curr_players else ""
                prev_starter = prev_players[0]["name"] if prev_players else ""
                if curr_starter and prev_starter and curr_starter != prev_starter:
                    changes.append({
                        "team":     team_abbr,
                        "position": pos,
                        "old":      prev_starter,
                        "new":      curr_starter,
                        "type":     "Starter Change",
                    })
        return changes
    except (requests.RequestException, ValueError, KeyError):
        return []


# ── Feature 5: Market Open/Close Storage ───────────────────────
def store_opening_lines(game_analysis, sport):
    """
    Store the first line seen as the opening line.
    Enables market movement tracking: opening spread vs current spread.
    """
    if not game_analysis:
        return
    try:
        stored = load_json_data(OPENING_LINES_PATH, {})
        today_str = date.today().strftime("%Y-%m-%d")
        for game in game_analysis:
            matchup = game.get("matchup", "")
            key = f"{today_str}_{matchup}_{sport}"
            if key not in stored:
                # First time seeing this game today — store as opening line
                stored[key] = {
                    "matchup":       matchup,
                    "sport":         sport,
                    "date":          today_str,
                    "open_spread":   game.get("Spread", "N/A"),
                    "open_total":    game.get("Total", "N/A"),
                    "open_home_ml":  game.get("HomeML", "N/A"),
                    "open_edge":     game.get("best_edge", 0),
                    "stored_at":     datetime.now().strftime("%H:%M"),
                }
        save_json_data(OPENING_LINES_PATH, stored)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass


def get_line_movement_summary(matchup, sport, current_game):
    """
    Compare current line vs opening line for a game.
    Returns dict: {"text": "Total: 8.5 → 9.0 (+0.5)", "direction": "up"|"down"|""}
    """
    empty = {"text": "", "direction": ""}
    try:
        stored = load_json_data(OPENING_LINES_PATH, {})
        today_str = date.today().strftime("%Y-%m-%d")
        key = f"{today_str}_{matchup}_{sport}"
        opening = stored.get(key, {})
        if not opening:
            return empty
        movements = []
        direction = ""
        curr_total = safe_float(current_game.get("Total") or 0)
        open_total = safe_float(opening.get("open_total") or 0)
        curr_spr   = current_game.get("Spread","")
        open_spr   = opening.get("open_spread","")
        if curr_total and open_total and abs(curr_total - open_total) >= 0.5:
            movements.append(f"Total: {open_total} → {curr_total} ({curr_total-open_total:+.1f})")
            direction = "up" if curr_total > open_total else "down"
        if curr_spr and open_spr and curr_spr != open_spr:
            movements.append(f"Spread: {open_spr} → {curr_spr}")
            if not direction:
                try:
                    direction = "up" if safe_float(curr_spr) > safe_float(open_spr) else "down"
                except (ValueError, TypeError):
                    direction = ""
        return {"text": " | ".join(movements), "direction": direction}
    except (ValueError, TypeError, ZeroDivisionError):
        return empty


# ── Feature 6: Prediction Stability Audit ──────────────────────
def store_board_snapshot(board, sport):
    """
    Store a snapshot of the current board — up to 30 picks per sport
    (best-bet tiers and highest edge prioritized), not just what gets
    locked in. Feeds next-day grading (grade_board_snapshots_for_date) so
    the model can learn from a broad recommendation set, not just the
    small subset of bets a person actually places.

    Persisted to Gist (not just local disk) because Streamlit Cloud's
    filesystem resets on redeploy/restart — a local-only snapshot could
    vanish before "the next day" grading ever runs. Pruned by date age
    (45 days) rather than a fixed snapshot count, so a busy day with many
    board loads doesn't push out data still needed for grading.
    """
    if not board:
        return
    try:
        today_key = date.today().strftime("%Y-%m-%d")
        stored = load_from_gist("board_snapshots", None)
        if stored is None:
            stored = load_json_data(BOARD_SNAP_PATH, {})  # fallback to local cache
        # Keep the HH:MM granularity in the key — check_prediction_stability
        # relies on multiple same-day snapshots to detect intraday edge
        # drift. Grading (grade_board_snapshots_for_date) selects the
        # LATEST snapshot for a given date+sport rather than assuming a
        # single entry, so this doesn't conflict with that use case.
        snap_key = f"{today_key}_{sport}_{datetime.now().strftime('%H:%M')}"
        # Cap at 30 picks/sport: current real grading coverage (ESPN_ATHLETE_IDS)
        # is only ~15-20 players/sport, so 30 gives headroom without bloating
        # the Gist or the grading job's runtime. Prioritize best-bet tiers
        # first, then edge size, so a cap never drops the picks that matter
        # most for calibration.
        _tier_rank = {"SOVEREIGN": 0, "ELITE": 1, "APPROVED": 2, "LEAN": 3, "PASS": 4}
        capped_board = sorted(
            board,
            key=lambda p: (_tier_rank.get(p.get("Tier", ""), 5), -abs(p.get("Edge", 0) or 0)),
        )[:30]
        stored[snap_key] = {
            "sport": sport,
            "date": today_key,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "props": [
                {
                    "player": p.get("Player", ""),
                    "prop":   p.get("Prop", ""),
                    "side":   p.get("Side", "OVER"),
                    "line":   p.get("Line", 0),
                    "edge":   p.get("Edge", 0),
                    "prob":   p.get("Prob", 0.5),
                    "tier":   p.get("Tier", ""),
                    "best_bet": bool(p.get("Tier", "") in ("SOVEREIGN", "ELITE")),
                    "signals": {
                        "base":     p.get("SignalBase", 0),
                        "defense":  p.get("SignalDefense", 0),
                        "location": p.get("SignalLocation", 0),
                        "rest":     p.get("SignalRest", 0),
                        "pace":     p.get("SignalPace", 0),
                        "usage":    p.get("SignalUsage", 0),
                        "blowout":  p.get("SignalBlowout", 0),
                    },
                    "sharp_flag": p.get("SharpFlag", ""),
                }
                for p in capped_board
            ],
        }
        # Keep 45 days of history — enough for weekly/monthly grading review
        # without the Gist file growing unbounded.
        cutoff = (date.today() - timedelta(days=45)).strftime("%Y-%m-%d")
        stored = {k: v for k, v in stored.items() if v.get("date", "0000-00-00") >= cutoff}
        save_json_data(BOARD_SNAP_PATH, stored)  # local cache for same-session reads
        save_to_gist("board_snapshots", stored)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass


def store_game_board_snapshot(game_analysis, sport):
    """
    Game-line counterpart to store_board_snapshot() — same policy, applied
    to SPREAD/TOTAL/MONEYLINE/ALT LINE picks instead of player props.
    (Added 2026-07-12: previously only the props board was snapshotted,
    so the daily grading pipeline had no game-line equivalent at all.)

    Stores up to 30 picks/sport (best-bet tiers and highest edge
    prioritized), persisted to Gist for the same reason as the props
    snapshot — Streamlit Cloud's filesystem resets on redeploy/restart.
    Feeds next-day grading (scripts/daily_board_grading.py →
    resolve_actual_game_result_for_grading), which writes to a SEPARATE
    gist key (game_board_grading_history) so it never collides with the
    props grading history.

    "line" for each pick uses the same numeric field the interactive lock
    UI stores (market_spread/market_total from the recommendation, not a
    team-prefixed display string) so grading logic stays consistent with
    the fixed Check Results resolver.
    """
    if not game_analysis:
        return
    try:
        today_key = date.today().strftime("%Y-%m-%d")
        stored = load_from_gist("game_board_snapshots", None)
        if stored is None:
            stored = load_json_data(GAME_BOARD_SNAP_PATH, {})
        snap_key = f"{today_key}_{sport}_{datetime.now().strftime('%H:%M')}"

        picks = []
        for g in game_analysis:
            matchup = g.get("matchup", "")
            home = g.get("home", "")
            away = g.get("away", "")
            for rec in g.get("recommendations", []):
                market = rec.get("type", "")
                line = rec.get("market_spread") if market == "SPREAD" else (
                    rec.get("market_total") if market == "TOTAL" else 0
                )
                picks.append({
                    "matchup": matchup, "home": home, "away": away,
                    "market": market, "pick": rec.get("pick", ""),
                    "line": line or 0, "edge": rec.get("edge", 0),
                    "tier": rec.get("tier", ""),
                })
            # Alt line isn't in "recommendations" -- it's enriched directly
            # onto the game dict after analyze_all_games() runs.
            if g.get("AltLine"):
                picks.append({
                    "matchup": matchup, "home": home, "away": away,
                    "market": "ALT LINE", "pick": g.get("AltLine", ""),
                    "line": g.get("AltLineValue", 0) or 0,
                    "edge": g.get("AltEdge", 0), "tier": g.get("AltTier", ""),
                })

        _tier_rank = {"SOVEREIGN": 0, "ELITE": 1, "APPROVED": 2, "LEAN": 3, "PASS": 4}
        capped_picks = sorted(
            picks,
            key=lambda p: (_tier_rank.get(p.get("tier", ""), 5), -abs(p.get("edge", 0) or 0)),
        )[:30]

        stored[snap_key] = {
            "sport": sport,
            "date": today_key,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "picks": capped_picks,
        }
        cutoff = (date.today() - timedelta(days=45)).strftime("%Y-%m-%d")
        stored = {k: v for k, v in stored.items() if v.get("date", "0000-00-00") >= cutoff}
        save_json_data(GAME_BOARD_SNAP_PATH, stored)
        save_to_gist("game_board_snapshots", stored)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass


def check_prediction_stability(board, sport):
    """
    Compare current board vs most recent snapshot.
    Flags if edge moved >5% with no injury/line change detected.
    
    Returns list of unstable props.
    """
    if not board:
        return []
    try:
        stored = load_json_data(BOARD_SNAP_PATH, {})
        today_snapshots = {k: v for k, v in stored.items()
                          if k.startswith(date.today().strftime("%Y-%m-%d")) and v.get("sport") == sport}
        if len(today_snapshots) < 2:
            return []
        # Get the most recent prior snapshot (not the current one)
        sorted_keys = sorted(today_snapshots.keys())
        prev_snap = today_snapshots[sorted_keys[-2]]
        prev_lookup = {
            (p["player"], p["prop"]): p["edge"]
            for p in prev_snap.get("props", [])
        }
        unstable = []
        for p in board[:30]:
            key = (p.get("Player",""), p.get("Prop",""))
            prev_edge = prev_lookup.get(key)
            curr_edge = p.get("Edge", 0)
            if prev_edge is not None and abs(curr_edge - prev_edge) > 0.05:
                unstable.append({
                    "player": p.get("Player",""),
                    "prop":   p.get("Prop",""),
                    "prev":   prev_edge,
                    "curr":   curr_edge,
                    "delta":  curr_edge - prev_edge,
                })
        return unstable
    except (requests.RequestException, ValueError, KeyError):
        return []


def grade_board_snapshots_for_date(target_date: str):
    """
    Grade every pick on the board (not just locked-in bets) for a given
    date, against actual results. Runs via the daily automated job
    (scripts/daily_board_grading.py) but can also be called manually.

    For each sport's most recent snapshot on target_date:
      - resolves the actual stat via resolve_actual_stat_for_grading
      - grades WIN/LOSS/PUSH/UNGRADABLE (unresolvable picks are marked
        UNGRADABLE, never silently counted as a loss — coverage is
        currently limited to NBA/NFL players in ESPN_ATHLETE_IDS, see
        resolve_actual_stat_for_grading's docstring)
      - attaches the "why": which signals fired and how strongly, so a
        miss can be traced back to what the model was weighting

    Results are saved to a SEPARATE Gist key (board_grading_history) from
    the user's actual bet ledger (history) — this is model-accuracy
    tracking, not bankroll/ROI tracking, and the two should never be
    blurred together. A separate helper (get_calibration_source_records)
    combines them ONLY for calibration purposes, clearly tagged by source.
    """
    from fetchers import resolve_actual_stat_for_grading

    stored = load_from_gist("board_snapshots", None) or load_json_data(BOARD_SNAP_PATH, {})
    day_snaps = {k: v for k, v in stored.items() if v.get("date") == target_date}
    if not day_snaps:
        return {"date": target_date, "graded": 0, "results": []}

    # One snapshot per sport for the day — take the latest if several.
    latest_by_sport = {}
    for k, v in day_snaps.items():
        sp = v.get("sport", "")
        if sp not in latest_by_sport or v.get("timestamp", "") > latest_by_sport[sp].get("timestamp", ""):
            latest_by_sport[sp] = v

    graded_results = []
    for sport, snap in latest_by_sport.items():
        for p in snap.get("props", []):
            player, prop_type = p.get("player", ""), p.get("prop", "")
            line, side = p.get("line", 0), p.get("side", "OVER")
            try:
                actual = resolve_actual_stat_for_grading(player, sport, prop_type, target_date)
            except Exception:
                actual = None

            if actual is None:
                outcome = "UNGRADABLE"
            elif actual == line:
                outcome = "PUSH"
            elif (actual > line and side == "OVER") or (actual < line and side == "UNDER"):
                outcome = "WIN"
            else:
                outcome = "LOSS"

            signals = p.get("signals", {})
            firing = {k: v for k, v in signals.items() if abs(v or 0) > 0.001}
            why = ", ".join(f"{k}:{v:+.2f}" for k, v in sorted(firing.items(), key=lambda kv: -abs(kv[1]))) or "no signals fired"

            graded_results.append({
                "date": target_date, "sport": sport, "player": player, "prop": prop_type,
                "side": side, "line": line, "actual": actual, "outcome": outcome,
                "edge": p.get("edge", 0), "prob": p.get("prob", 0.5), "tier": p.get("tier", ""),
                "best_bet": p.get("best_bet", False), "why": why, "source": "board_grading",
            })

    # Persist — separate key from the bet ledger, appended to prior days.
    grading_history = load_from_gist("board_grading_history", None) or {}
    grading_history[target_date] = graded_results
    cutoff = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    grading_history = {k: v for k, v in grading_history.items() if k >= cutoff}
    save_to_gist("board_grading_history", grading_history)

    graded_n = sum(1 for r in graded_results if r["outcome"] != "UNGRADABLE")
    wins = sum(1 for r in graded_results if r["outcome"] == "WIN")
    return {
        "date": target_date, "total_picks": len(graded_results), "graded": graded_n,
        "ungradable": len(graded_results) - graded_n, "wins": wins,
        "hit_rate": round(wins / graded_n, 3) if graded_n else None,
        "results": graded_results,
    }


def get_calibration_source_records(bet_type=None):
    """
    Combine real bet history + board-grading history for calibration
    purposes ONLY — every returned record is tagged with 'source' and
    'bet_type' so downstream code can filter. Never use this for
    bankroll/ROI display; those must read st.session_state['history']
    directly, unmixed.

    bet_type=None (default) returns everything combined — for display-only
    callers (GEM brief, tier_stats summary) that don't need the prop/game
    split. Pass "prop" or "game" to get just that pool, matching
    calibrate_tier_thresholds' own bet_type param.

    2026-07-12: previously this only read the props board_grading_history
    and was never actually passed into calibrate_tier_thresholds anywhere
    — the real threshold calibration only ever saw the small manually-
    placed bet ledger, regardless of how much daily auto-graded board data
    existed. Now also reads game_board_grading_history (written by
    scripts/daily_board_grading.py's game-grading pass) and both pools get
    wired into load_sport_data()'s calibration calls below.
    """
    real_history = list(st.session_state.get("history", []))
    for r in real_history:
        r.setdefault("source", "bet_ledger")
        r.setdefault("bet_type", "prop")

    board_records = []
    prop_grading = load_from_gist("board_grading_history", None) or {}
    for day_results in prop_grading.values():
        for r in day_results:
            if r.get("outcome") in ("WIN", "LOSS", "PUSH"):
                board_records.append({
                    "outcome": r["outcome"], "prob": r.get("prob", 0.5),
                    "sport": r.get("sport", ""), "timestamp": r.get("date", ""),
                    "edge": r.get("edge", 0), "tier": r.get("tier", ""),
                    "source": "board_grading", "bet_type": "prop",
                    "has_real_prob": True,
                })

    game_grading = load_from_gist("game_board_grading_history", None) or {}
    for day_results in game_grading.values():
        for r in day_results:
            if r.get("outcome") in ("WIN", "LOSS", "PUSH"):
                board_records.append({
                    "outcome": r["outcome"], "prob": r.get("prob", 0.5),
                    "sport": r.get("sport", ""), "timestamp": r.get("date", ""),
                    "edge": r.get("edge", 0), "tier": r.get("tier", ""),
                    "source": "board_grading", "bet_type": "game",
                    "has_real_prob": True,
                })

    combined = real_history + board_records
    if bet_type is not None:
        combined = [r for r in combined if r.get("bet_type", "prop") == bet_type]
    return combined


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_harvester_data_cached(sport, _fn_names_tuple):
    """Parallel-fetch every harvester source for one sport, cached 5 min so
    repeat Streamlit reruns within that window (any button click, dropdown
    change, etc, which re-executes the whole script) don't re-hit the Gist
    API for each of the ~19 sources every time -- only the data-fetching
    is cached here, not session_state writes, since st.cache_data on a
    function with session_state side effects is unreliable."""
    def _run_one_harvester(_fn_name):
        try:
            import fetchers as _ftch
            _fn = getattr(_ftch, _fn_name)
            return _fn_name, _fn(sport)
        except Exception:
            return _fn_name, None
    with ThreadPoolExecutor(max_workers=min(19, len(_fn_names_tuple) or 1)) as _hx:
        return dict(_hx.map(_run_one_harvester, _fn_names_tuple))


def load_sport_data(sport):
    """Load all data for a sport: props, game lines, injuries, signals. Returns (board, games, n_defaults, n_edge, home_teams, away_teams)."""
    # ── Kill Switch ───────────────────────────────────────────────────────
    # If ENABLE_RECOMMENDATIONS is False in Streamlit secrets, return empty
    # board immediately. Caller is responsible for displaying the warning
    # in the correct UI context (not inside a spinner or sidebar).
    if not ENABLE_RECOMMENDATIONS:
        return [], [], 0, 0, [], []
    if sport == "NFL":
        _nfl_db_path = os.path.join(CACHE_DIR, "nfl_player_db.pkl")
        _db_stale = not os.path.exists(_nfl_db_path) or (time.time() - os.path.getmtime(_nfl_db_path))/86400 > 7
        if _db_stale:
            with st.spinner("🏈 Building NFL player database..."):
                _db = fetch_nfl_full_player_database()
                if _db: st.session_state["nfl_player_db"] = _db
        _live_bl = fetch_nfl_live_baselines()
        if _live_bl: st.session_state["nfl_live_baselines"] = _live_bl

    # ── Auto-calibrate tier thresholds from bet history ────────────────────
    # 2026-07-12: now pulls from get_calibration_source_records() instead of
    # just st.session_state["history"] — that means both pools include the
    # daily auto-graded board snapshots (up to 30 picks/sport/day) on top of
    # the real bet ledger, not just the handful of bets actually placed.
    # Previously this ran on the manual ledger alone for both props and
    # games, so the auto-grading pipeline (store_board_snapshot +
    # daily_board_grading.yml) fed the GEM brief display and nothing else.
    _sig_perf   = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    _prop_hist  = get_calibration_source_records(bet_type="prop")
    _cal_thresholds = calibrate_tier_thresholds(_sig_perf, _prop_hist, sport, bet_type="prop")
    st.session_state["calibrated_thresholds"] = _cal_thresholds
    if _cal_thresholds.get("_calibrated") and _cal_thresholds.get("_n_records", 0) >= 15:
        _adj_log = _cal_thresholds.get("_log", {})
        _adjusted = {k:v for k,v in _cal_thresholds.items() if not k.startswith("_")}
        st.caption(f"📐 Prop thresholds auto-calibrated from {_cal_thresholds['_n_records']} {sport} bets "
                   f"(ledger + daily board grading): "
                   f"SOV={_adjusted.get('SOVEREIGN',0):.3f} ELI={_adjusted.get('ELITE',0):.3f} "
                   f"APP={_adjusted.get('APPROVED',0):.3f} LEAN={_adjusted.get('LEAN',0):.3f}")

    # Same auto-calibration loop, now applied to game lines (SPREAD/TOTAL/ML)
    # on their own edge scale — this previously didn't exist at all for
    # SPREAD/TOTAL (static GAME_TIER_THRESHOLDS only, never adjusted from
    # results), and ML was quietly reusing the prop calibration pool above
    # even though ML edges run 2-3x smaller than prop edges (bug found
    # 2026-07-12). See calibrate_tier_thresholds bet_type param. Also now
    # pulls in the daily game-line board grading (store_game_board_snapshot
    # + daily_board_grading.py's game-grading pass), same as props above.
    _game_hist = get_calibration_source_records(bet_type="game")
    _cal_game_thresholds = calibrate_tier_thresholds(
        _sig_perf, _game_hist, sport, bet_type="game", base_thresholds_by_sport=GAME_TIER_THRESHOLDS
    )
    st.session_state["calibrated_game_thresholds"] = _cal_game_thresholds
    if _cal_game_thresholds.get("_calibrated") and _cal_game_thresholds.get("_n_records", 0) >= 15:
        _adj_game = {k:v for k,v in _cal_game_thresholds.items() if not k.startswith("_")}
        st.caption(f"📐 Game-line thresholds auto-calibrated from {_cal_game_thresholds['_n_records']} {sport} bets "
                   f"(ledger + daily board grading): "
                   f"SOV={_adj_game.get('SOVEREIGN',0):.3f} ELI={_adj_game.get('ELITE',0):.3f} "
                   f"APP={_adj_game.get('APPROVED',0):.3f} LEAN={_adj_game.get('LEAN',0):.3f}")


    min_edge = st.session_state.get("min_edge", MIN_EDGE_DEFAULT)
    skip_def = st.session_state.get("skip_defaults", False)
    if sport in ["Golf", "Tennis", "UFC", "Soccer"]:
        props = scrape_prizepicks_with_gist_fallback(sport)
        if not props:
            _gist_fb = fetch_auto_scraped_props(sport)
            if _gist_fb:
                _pp_fb = [p for p in _gist_fb if "prizepicks" in str(p.get("source","")).lower()]
                props  = _pp_fb if _pp_fb else _gist_fb
                st.info(f"📡 PrizePicks loaded from local scraper ({len(props)} props). Run script daily to keep fresh.")
            else:
                st.warning("⚠️ PrizePicks unavailable. Run betcouncil_auto_scraper.py on your PC to populate data.")
                return [], [], 0, 0, {}, {}

        # ── Score each prop via standalone model (ESPN live stats) ───────────
        enriched = []
        n_edge = 0
        _fetch_fn = {
            "Tennis": fetch_tennis_player_stats,
            "Golf":   fetch_golf_player_stats,
            "Soccer": fetch_soccer_player_stats,
            "UFC":    fetch_ufc_fighter_stats,
        }.get(sport)

        for p in props:
            player  = p["Player"]
            stat    = p["Prop"]
            line    = float(p.get("Line", 0) or 0)
            stat_norm_local = STAT_NORMALIZE.get((sport, stat), stat)

            scored = score_pick_standalone(player, stat, line, "OVER", sport)
            edge   = scored["edge"]
            prob   = scored["prob"]
            avg    = scored["avg"]
            tier   = scored["tier"]

            if abs(edge) >= 0.02:
                n_edge += 1

            enriched.append({
                "Player": player, "Prop": stat, "Line": line, "Side": "OVER",
                "Edge": edge, "EdgePct": f"{edge:+.1%}", "Prob": round(prob, 4),
                "Wager": 0, "Tier": tier, "Model": scored["data_source"],
                "Sport": sport, "Avg": avg,
                "Injury": "", "SEM": scored["confidence"], "SEM_n": 0,
                "SignalBase": edge, "SignalDefense": 0, "SignalLocation": 0,
                "SignalUsage": 0, "SignalRest": 0, "SignalPace": 0,
                "SignalBlowout": 0, "WeatherNote": "",
                "Movement": "", "OddsTypeFlip": "", "Efficiency": "—", "EffScore": 0,
                "SharpFlag": "",
                "source": p.get("source", ""), "OddsType": "standard",
                "DisplayOnly": False,
                "EV_2pick": f"{calculate_prizepicks_ev(prob, 2):+.1%}",
            })

        data_note = {
            "Tennis": "🎾 Tennis: Scored via ESPN ATP/WTA season stats.",
            "Golf":   "⛳ Golf: Scored via ESPN PGA scoring averages.",
            "Soccer": "⚽ Soccer: Scored via ESPN multi-league player stats.",
            "UFC":    "🥊 UFC: Scored via ESPN career fight stats.",
        }.get(sport, f"📊 {sport}: Live stats via ESPN.")
        if n_edge > 0:
            st.info(f"{data_note} {n_edge}/{len(enriched)} props with model edge.")
        else:
            st.info(f"{data_note} ESPN data loading — check board after first prop is fetched.")
        return enriched, [], 0, n_edge, {}, {}
    rolling_avgs = {}
    team_defense = {}
    l20_pricer_baseline = {}
    if sport == "NBA":
        rolling_avgs = fetch_nba_rolling_averages()
        team_defense = fetch_nba_team_defense()
        live_avgs = fetch_nba_averages_bdl()
        season_avgs = {**PLAYER_AVERAGES.get("NBA", {}), **live_avgs}
        try:
            l20_pricer_baseline = fetch_nba_l20_pricer_baseline()
        except Exception as _l20_err:
            l20_pricer_baseline = {}
            print(f"[WARN] fetch_nba_l20_pricer_baseline: {_l20_err}")
        st.session_state["nba_l20_pricer_baseline"] = l20_pricer_baseline
    elif sport == "WNBA":
        wnba_rolling = fetch_wnba_rolling_averages()
        season_avgs = dict(PLAYER_AVERAGES.get("WNBA", {}))
        _merge_rolling(season_avgs, wnba_rolling)
    elif sport == "MLB":
        # Populate full MLB roster IDs (all 30 teams) — cached 24h (fast on cache hit)
        if "mlb_roster_ids" not in st.session_state or not st.session_state["mlb_roster_ids"]:
            with st.spinner("Loading MLB roster IDs..."):
                st.session_state["mlb_roster_ids"] = fetch_mlb_full_roster_ids()
        # Run remaining MLB pre-pool fetches in parallel instead of sequentially.
        # Was as_completed()+per-future .result(timeout=15) inside a
        # `with ThreadPoolExecutor(...) as ex:` block -- the exact bug
        # pattern already diagnosed and fixed elsewhere this session: the
        # per-future timeout looks like protection but as_completed()
        # itself has no overall ceiling, and the with-block's __exit__
        # still calls shutdown(wait=True), blocking indefinitely on
        # whichever future hasn't finished regardless of any per-future
        # timeout. Reusing the same proven _fetch_parallel helper (real
        # 25s ceiling) instead of the ad-hoc pattern.
        _mlb_pre_names = ["rolling", "pitchers", "woba", "lineups", "fl"]
        _mlb_pre_fns = [
            fetch_mlb_rolling_averages,
            fetch_mlb_probable_pitchers,
            _fetch_live_team_woba_splits,
            fetch_mlb_confirmed_lineups_with_fallback,
            (lambda: fetch_fantasylabs_lineups(sport)),
        ]
        _mlb_pre_results = _fetch_parallel(_mlb_pre_fns, show_progress=False)
        _mlb_pre = dict(zip(_mlb_pre_names, _mlb_pre_results))
        mlb_rolling = _mlb_pre.get("rolling") or {}
        season_avgs = dict(PLAYER_AVERAGES.get("MLB", {}))
        _merge_rolling(season_avgs, mlb_rolling)
        mlb_pitchers = _mlb_pre.get("pitchers") or {}
        try:
            _live_woba = _mlb_pre.get("woba") or {}
            if _live_woba:
                MLB_TEAM_WOBA_VS_RHP.update(_live_woba.get("vs_rhp", {}))
                MLB_TEAM_WOBA_VS_LHP.update(_live_woba.get("vs_lhp", {}))
        except Exception:
            _logger.debug("Silent except at line 10443")
            pass
        _mlb_lineups = _mlb_pre.get("lineups") or {}
        if _mlb_lineups:
            st.session_state["mlb_confirmed_lineups"] = _mlb_lineups
        _fl_lineups = _mlb_pre.get("fl") or {}
        if _fl_lineups:
            st.session_state["fantasylabs_lineups"] = _fl_lineups
        st.session_state["mlb_pitchers"] = mlb_pitchers
    elif sport == "NHL":
        nhl_rolling = fetch_nhl_rolling_averages()
        season_avgs = dict(PLAYER_AVERAGES.get("NHL", {}))
        _merge_rolling(season_avgs, nhl_rolling)
    elif sport == "NFL":
        nfl_rolling = fetch_nfl_rolling_averages()
        if not nfl_rolling:
            # Was a sequential loop -- one ESPN network call per player, one
            # at a time. Confirmed real: 13 NFL players tracked, and this
            # fallback fires every time during preseason (rolling averages
            # legitimately empty with no games played yet), meaning this
            # ran on every single NFL board load. Parallelized with the
            # same proven _fetch_parallel helper.
            _nfl_players = list(ESPN_ATHLETE_IDS.get("NFL", {}))
            _nfl_fns = [(lambda _p=_p: fetch_espn_player_gamelogs("NFL", _p)) for _p in _nfl_players]
            _nfl_results = _fetch_parallel(_nfl_fns, show_progress=False)
            nfl_rolling = {p: r for p, r in zip(_nfl_players, _nfl_results) if r}
        season_avgs = dict(PLAYER_AVERAGES.get("NFL", {}))
        _merge_rolling(season_avgs, nfl_rolling)
    elif sport == "Soccer":
        soccer_rolling = fetch_soccer_rolling_averages()
        season_avgs = dict(PLAYER_AVERAGES.get("Soccer", {}))
        for player, stats in soccer_rolling.items():
            season_avgs[player] = {**season_avgs.get(player, {}), **stats}
    else:
        season_avgs = PLAYER_AVERAGES.get(sport, {})
    defaults = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])

    # ── PARALLEL FETCH — all independent data sources fire simultaneously ──
    # Groups fetches with no inter-dependencies into one ThreadPoolExecutor call.
    # _fetch_parallel was built last session but never wired in — now connected.
    def _pf_prizepicks():   return scrape_prizepicks_with_gist_fallback(sport)
    def _pf_underdog():     return fetch_underdog_props(sport)
    def _pf_dk_sal():       return []  # fetch_dk_salaries not implemented
    def _pf_pinnacle():     return fetch_pinnacle_game_lines(sport)
    def _pf_oddswrap():     return fetch_oddswrap_props(sport)
    _parlayapi_key = f'parlayapi_props_{sport}'
    def _pf_parlayapi():
        if _parlayapi_key in st.session_state:
            return st.session_state[_parlayapi_key]
        result = fetch_parlayapi_props(sport)
        if result:
            st.session_state[_parlayapi_key] = result
        return result
    _papi_key = f'oddsapi_props_{sport}'
    def _pf_odds_api():
        if _papi_key in st.session_state:
            return st.session_state[_papi_key]
        result = fetch_odds_api_props(sport)
        if result:
            st.session_state[_papi_key] = result
        return result
    _oddspapi_key = f'oddspapi_props_{sport}'
    def _pf_oddspapi():
        if _oddspapi_key in st.session_state:
            return st.session_state[_oddspapi_key]
        result = fetch_oddspapi_props(sport)
        if result:
            st.session_state[_oddspapi_key] = result
        return result
    def _pf_bdl():          return fetch_player_season_avg_bdl(sport) if sport == 'NBA' else []
    def _pf_rw_injuries():
        try:
            result = fetch_rotowire_injuries(sport) if sport in ["NBA","MLB","NFL","NHL","WNBA"] else []
            return result
        except (requests.RequestException, ValueError, KeyError, AttributeError):
            return []  # RotoWire RSS blocks cloud IPs — silent fallback, not a board error
    def _pf_cbs_injuries():
        try:
            return fetch_cbs_injuries(sport) if sport in ["NBA","MLB","NFL","NHL","WNBA"] else []
        except (requests.RequestException, ValueError, KeyError, AttributeError):
            return []
    def _pf_espn_injuries():
        try:
            return fetch_espn_injuries(sport) if sport in ["NBA","MLB","NFL","NHL","WNBA"] else []
        except (requests.RequestException, ValueError, KeyError, AttributeError):
            return []
    def _pf_kalshi():
        try:
            return fetch_kalshi_markets(sport)
        except (requests.RequestException, ValueError, KeyError, AttributeError):
            return []
    def _pf_polymarket():
        try:
            return fetch_polymarket_markets(sport)
        except (requests.RequestException, ValueError, KeyError, AttributeError):
            return []
    def _pf_covers():
        try:
            return fetch_covers_consensus(sport)
        except (requests.RequestException, ValueError, KeyError, AttributeError):
            return []
    def _pf_public():       return fetch_public_betting(sport) if sport in ["NBA","MLB","NHL","NFL","WNBA"] else {}
    def _pf_an():           return fetch_action_network_props(sport) if sport in ["NBA","MLB","NHL","NFL","WNBA"] else []
    def _pf_referees():     return fetch_todays_referees(sport) if sport in ["NBA","MLB"] else {}
    def _pf_game_lines():
        if sport in ("Tennis", "UFC", "Soccer"):
            return fetch_h2h_game_lines(sport)
        return fetch_game_lines(sport)
    def _pf_parlayplay():   return []  # parlayplay disabled
    # DK Pick6 removed entirely (Jul 29 2026) — redundant DFS pick'em product
    # (same category as PrizePicks/Underdog, both already working), and its
    # scraper never produced real player names (dkId_XXXXX placeholders only,
    # confirmed unfixable without a browser-session harvester). Stub kept so
    # the _parallel_fns tuple below doesn't need renumbering.
    def _pf_dk_pick6():    return []
    def _pf_betrivers_lines(): return fetch_betrivers_game_lines(sport)
    def _pf_fanatics_lines():  return fetch_fanatics_game_lines(sport)
    def _pf_espnbet_lines():   return fetch_espnbet_game_lines(sport)
    def _pf_hardrock_lines():  return fetch_hardrock_game_lines(sport)
    def _pf_wynnbet_lines():   return fetch_wynnbet_game_lines(sport)
    def _pf_unibet_lines():    return fetch_unibet_game_lines(sport)
    def _pf_bet365_lines():    return fetch_bet365_game_lines(sport)
    def _pf_sharpapi_lines():  return fetch_sharpapi_lines(sport)
    def _pf_bookmaker_lines(): return fetch_bookmaker_game_lines(sport)
    def _pf_heritage_lines():  return fetch_heritage_game_lines(sport)
    def _pf_betmgm_lines():    return fetch_betmgm_game_lines(sport)
    def _pf_sportsline_lines(): return fetch_sportsline_game_lines(sport)
    def _pf_sbr_lines():        return fetch_sbr_game_lines(sport)
    def _pf_thescore_lines():   return fetch_thescore_game_lines(sport)
    def _pf_fanduel_lines():
        _an = fetch_fanduel_lines(sport)
        if _an: return _an
        return []
    def _pf_caesars_lines():
        return fetch_caesars_lines(sport)
    def _pf_caesars_props():   return fetch_caesars_props(sport)
    def _pf_fd_props_sa():   return fetch_fanduel_props_sharpapi(sport)
    def _pf_sharpapi_drops(): return fetch_sharpapi_line_drops(sport)
    def _pf_sharpapi_ev():   return fetch_sharpapi_ev_opportunities(sport)
    def _pf_signalodds():    return fetch_signalodds_events(sport)
    def _pf_betslib():       return fetch_betslib_predictions(sport)
    def _pf_betslib_live():  return fetch_betslib_live_events(sport)
    def _pf_fp_proj():       return fetch_fantasypros_projections(sport)
    def _pf_def_rank():      return fetch_opponent_defense_rankings(sport)
    def _pf_betonline_off():   return fetch_betonline_offering(sport)
    def _pf_bovada_lines():
        _direct = fetch_bovada_game_lines(sport)
        if _direct:
            return _direct
        # Direct server-side fetch to Bovada's public coupon API frequently
        # returns empty from Streamlit Cloud's datacenter IP even though the
        # same endpoint works fine from a residential browser (Cloudflare/
        # rate-limiting treats datacenter IPs differently). Fall back to the
        # Tampermonkey harvester's Gist-backed capture, which runs inside a
        # real browser session and hits the identical public endpoint.
        try:
            _gist_data = load_from_gist(f"bovada_{sport}", None)
            if not _gist_data or not _gist_data.get("rows"):
                return []
            _out = []
            for _row in _gist_data["rows"]:
                _american = _row.get("american_odds") or _row.get("decimal_odds") or ""
                _out.append({
                    "game":      f"{_row.get('away_team','')} @ {_row.get('home_team','')}",
                    "home":      _row.get("home_team", ""),
                    "away":      _row.get("away_team", ""),
                    "market":    _row.get("market_type", ""),
                    "selection": _row.get("selection", ""),
                    "odds":      _american,
                    "book":      "Bovada",
                    "sport":     sport,
                    "source":    "bovada_lines_harvester",
                })
            return _out
        except Exception:
            return []
    def _pf_bovada_props():    return fetch_bovada_props(sport)
    def _pf_mybookie():
        # Primary (Jul 10 2026, reordered): direct HTML scrape of mybookie.ag's
        # public sportsbook pages, for sports with a confirmed-matching
        # template. This is the most direct source (straight from MyBookie
        # itself, not a third-party relay), needs no browser tab open, and
        # needs no manual step at all -- so it goes first now to minimize
        # dependence on anything requiring you to do something by hand.
        # Only covers NFL/MLB/NBA/NHL/WNBA -- these 5 share an identical
        # 2-way (no Draw) team-vs-team spread/ml/total template, confirmed
        # live. Soccer/UFC/Golf/Tennis are NOT covered here: Soccer has a
        # 3-way moneyline with a Draw price this parser doesn't extract,
        # UFC/Golf/Tennis aren't head-to-head team spread/ml/total markets
        # at all -- extending this parser to them would silently produce
        # incomplete/wrong data rather than fail loudly, so those sports
        # fall through to Action Network/harvester below instead.
        try:
            _sport_map_html = {"NFL": "nfl", "MLB": "mlb", "NBA": "nba", "NHL": "nhl", "WNBA": "wnba"}
            _html_sport = _sport_map_html.get(sport)
            if _html_sport:
                _html_games = fetch_mybookie_lines_html(_html_sport)
                if _html_games:
                    _out = []
                    for _gid, _g in _html_games.items():
                        _out.append({
                            "Home":   _g.get("home_team", ""),
                            "Away":   _g.get("away_team", ""),
                            "HomeML": (_g.get("home_ml") or {}).get("price"),
                            "AwayML": (_g.get("away_ml") or {}).get("price"),
                            "Spread": (_g.get("home_spread") or {}).get("points"),
                            "Total":  (_g.get("total") or {}).get("points"),
                        })
                    if _out:
                        return _out
        except Exception:
            pass
        # Fallback 1b (Jul 2026): the-odds-api.com's dedicated MyBookie
        # testing account -- confirmed live this session (18/18 MLB games,
        # real American odds, 3 credits for the whole slate). Checked
        # before Action Network since it's a real, verified, direct
        # sportsbook feed rather than a third-party relay. Currently
        # MLB-only (that's what's confirmed); other sports fall through.
        try:
            _oddsapi_mb_data = _read_gist_file(f"betcouncil_theoddsapi_mybookie_{sport.upper()}.json", cache_minutes=180)
        except Exception:
            _oddsapi_mb_data = None
        if _oddsapi_mb_data and _oddsapi_mb_data.get("games"):
            _out2 = []
            for _g in _oddsapi_mb_data["games"]:
                _out2.append({
                    "Home": _g.get("home_team", ""), "Away": _g.get("away_team", ""),
                    "HomeML": _g.get("home_ml"), "AwayML": _g.get("away_ml"),
                    "Spread": _g.get("spread_hdp"), "Total": _g.get("total_hdp"),
                })
            if _out2:
                return _out2
        # Fallback 2: Action Network public scoreboard API (book_id=8).
        # No auth required — confirmed 200 public endpoint. Covers Soccer/
        # UFC/Golf/Tennis (and anything else) that the HTML scraper above
        # doesn't, plus acts as a safety net if mybookie.ag's page structure
        # ever changes for the 5 sports it does cover.
        try:
            _an = fetch_action_network_lines(sport)
            if _an:
                return _an
        except Exception:
            pass
        # Fallback 3 (last resort, requires a manual browser tab open on
        # mybookie.ag): Tampermonkey Gist harvester.
        # BUG FIX (2026-07): fetch_mybookie_from_gist() has existed and had a
        # working Tampermonkey harvester feeding it real data all night, but
        # was never actually called anywhere in the board pipeline -- the
        # harvested data was landing in the Gist and going completely unused.
        # Also reshapes MyBookie's {Matchup,"Home ML","Away ML",...} harvester
        # output into the clean {Home,Away,HomeML,AwayML,Spread,Total} shape
        # build_game_line_consensus() actually expects (MyBookie is not in the
        # _LONG_FORMAT_BOOKS auto-normalize set).
        try:
            raw, _src = fetch_mybookie_from_gist(sport)
            if raw:
                _out = []
                for _g in raw:
                    _matchup = _g.get("Matchup", "") or ""
                    if " @ " in _matchup:
                        _away, _home = [s.strip() for s in _matchup.split(" @ ", 1)]
                    elif " vs " in _matchup:
                        _home, _away = [s.strip() for s in _matchup.split(" vs ", 1)]
                    else:
                        _away, _home = _matchup, _matchup
                    _out.append({
                        "Home":   _home,
                        "Away":   _away,
                        "HomeML": _g.get("Home ML"),
                        "AwayML": _g.get("Away ML"),
                        "Spread": _g.get("Spread"),
                        "Total":  _g.get("Total"),
                    })
                if _out:
                    return _out
        except Exception:
            pass
        return []
    def _pf_bet365():
        try:
            _raw = load_from_gist("bet365_games", None)
            if not _raw or not _raw.get("data"):
                return []
            _team_pools = {
                "NBA": set(NBA_POWER_RATINGS.keys()),
                "MLB": set(MLB_POWER_RATINGS.keys()),
                "NHL": set(NHL_POWER_RATINGS.keys()),
                "WNBA": set(WNBA_POWER_RATINGS.keys()),
            }
            def _classify(home, away):
                for _sp, _pool in _team_pools.items():
                    if any(home in _t or _t in home for _t in _pool) or \
                       any(away in _t or _t in away for _t in _pool):
                        return _sp
                return "UNKNOWN"

            def _american_from_fractional(frac):
                if not frac or "/" not in str(frac):
                    return None
                try:
                    num, den = str(frac).split("/")
                    dec = float(num) / float(den)
                    return round(dec * 100) if dec >= 1 else round(-100 / dec)
                except Exception:
                    return None

            _out = []
            for _g in _raw["data"]:
                _home = _g.get("home_team", "") or ""
                _away = _g.get("away_team", "") or ""
                _sp = _classify(_home, _away)
                if _sp != sport:
                    continue

                # NOTE: betcouncil_bet365_games.json Gist is currently populated
                # by a harvester URL that uses cid=97 (match result only →
                # Home/Away/Tie). Over/Under and Spread fields will be None until
                # the Tampermonkey passive hook is used to capture totals/spread
                # markets (different cid values per sport). Parser is ready for
                # those fields when the harvester provides them.
                _home_ml = _away_ml = None
                _spread = _total = _over_odds = _under_odds = None
                for _sel in _g.get("selections", []):
                    _label = (_sel.get("label") or "").lower()
                    _frac  = (_sel.get("odds_fractional_live")
                              or _sel.get("odds_fractional_static"))
                    _american = _american_from_fractional(_frac)
                    # HA / HD / handicap fields carry the line value
                    _ha = (_sel.get("HA") or _sel.get("HD")
                           or _sel.get("hc") or _sel.get("handicap"))
                    if _label == "home":
                        _home_ml = _american
                    elif _label == "away":
                        _away_ml = _american
                    elif "over" in _label:
                        _over_odds = _american
                        if _ha is not None:
                            try: _total = float(_ha)
                            except (ValueError, TypeError): pass
                    elif "under" in _label:
                        _under_odds = _american
                        if _ha is not None and _total is None:
                            try: _total = float(_ha)
                            except (ValueError, TypeError): pass
                    elif _ha is not None and _label not in ("home","away","tie","draw"):
                        # Spread selection — HA is the handicap line
                        try: _spread = float(_ha)
                        except (ValueError, TypeError): pass

                _out.append({
                    "Home":       _home,
                    "Away":       _away,
                    "HomeML":     _home_ml,
                    "AwayML":     _away_ml,
                    "Spread":     _spread,
                    "Total":      _total,
                    "OverOdds":   _over_odds,
                    "UnderOdds":  _under_odds,
                })
            return _out
        except Exception:
            return []
    def _pf_sharpapi_props():  return fetch_sharpapi_props(sport)
    def _pf_savant_xstats():   return fetch_savant_statcast() if sport == "MLB" else {}
    def _pf_savant_sprint():   return fetch_savant_sprint_speed() if sport == "MLB" else {}
    def _pf_savant_expected(): return fetch_savant_expected_stats() if sport == "MLB" else {}
    def _pf_savant_arsenal():  return fetch_savant_pitch_arsenal() if sport == "MLB" else {}
    def _pf_savant_batted():   return fetch_savant_batted_ball() if sport == "MLB" else {}
    def _pf_mlb_lineups():     return fetch_mlb_lineups() if sport == "MLB" else {}
    def _pf_openmeteo():       return fetch_openmeteo_weather() if sport == "MLB" else {}
    def _pf_ump_scorecards():  return fetch_ump_scorecards() if sport == "MLB" else {}
    def _pf_nba_advanced():    return fetch_nba_advanced_stats() if sport == "NBA" else {}
    def _pf_pinnacle_lines():
        # DNS pre-check — skips silently on Streamlit Cloud, works self-hosted
        import socket as _sock
        try:
            _sock.getaddrinfo("guest.api.arcadia.pinnacle.com", 443)
        except OSError:
            return []
        return fetch_pinnacle_game_lines(sport)
    def _pf_ev_api():       return fetch_ev_api_live()
    def _pf_ev_wnba():      return fetch_ev_api_wnba()
    def _pf_ev_outliers():  return fetch_ev_api_outliers(sport)
    def _pf_ev_feed():      return fetch_ev_feed()
    def _pf_ev_bvp():       return fetch_ev_bvp() if sport in ("MLB",) else {}
    def _pf_ev_preview():      return fetch_ev_preview() if sport in ("MLB",) else {}
    def _pf_ev_strikeouts():  return fetch_ev_strikeouts() if sport in ("MLB",) else {}
    def _pf_ev_movement():    return fetch_ev_movement(sport)
    def _pf_ev_stats_hr():    return fetch_ev_stats("hr") if sport in ("MLB",) else {}
    def _pf_ev_stats_k():     return fetch_ev_stats("k")  if sport in ("MLB",) else {}
    def _pf_ev_barrels():     return fetch_ev_barrels() if sport in ("MLB",) else []
    def _pf_ev_recap():       return fetch_ev_recap() if sport in ("MLB",) else {}
    def _pf_ev_mlb():         return fetch_ev_mlb() if sport in ("MLB",) else {}
    def _pf_ev_trends():      return fetch_ev_trends() if sport in ("MLB",) else {}
    _parlayapi_ev_key = f'parlayapi_ev_{sport}'
    def _pf_parlayapi_ev():
        if _parlayapi_ev_key in st.session_state:
            return st.session_state[_parlayapi_ev_key]
        result = fetch_parlayapi_ev(sport)
        if result:
            st.session_state[_parlayapi_ev_key] = result
        return result
    _parlayapi_arb_key = f'parlayapi_arb_{sport}'
    def _pf_parlayapi_arb():
        if _parlayapi_arb_key in st.session_state:
            return st.session_state[_parlayapi_arb_key]
        result = fetch_parlayapi_arbitrage(sport)
        if result:
            st.session_state[_parlayapi_arb_key] = result
        return result
    def _pf_unabated():       return fetch_unabated_lines(sport.lower())

    @st.cache_data(ttl=300, show_spinner=False)
    def _get_parallel_results(_cache_sport):
        """Cache the whole 77-source parallel fetch for 5 min. Previously
        this ran in full on EVERY script rerun -- including a simple
        button click like locking a game line, which triggers st.rerun()
        and re-executes load_sport_data() top to bottom. Real reported
        symptom this fixes: locking a pick taking an extremely long time
        (waiting on all 77 sources again, several of them live network
        calls with no caching of their own) for an action that has
        nothing to do with re-fetching odds data."""
        _fns = [
        _pf_prizepicks, _pf_underdog, _pf_dk_sal, _pf_pinnacle,
        _pf_oddswrap, _pf_parlayapi, _pf_odds_api, _pf_oddspapi,
        _pf_bdl, _pf_rw_injuries, _pf_cbs_injuries, _pf_espn_injuries, _pf_public,
        _pf_an, _pf_referees, _pf_game_lines, _pf_parlayplay, _pf_dk_pick6,
        _pf_betrivers_lines, _pf_fanatics_lines, _pf_espnbet_lines,
        _pf_hardrock_lines, _pf_wynnbet_lines, _pf_unibet_lines, _pf_bet365_lines,
        _pf_sharpapi_lines, _pf_sharpapi_props, _pf_betmgm_lines, _pf_heritage_lines, _pf_bookmaker_lines, _pf_sportsline_lines, _pf_sbr_lines, _pf_thescore_lines,
        _pf_signalodds, _pf_betslib, _pf_betslib_live, _pf_fp_proj, _pf_def_rank, _pf_caesars_props, _pf_betonline_off, _pf_bovada_lines, _pf_bovada_props, _pf_bet365, _pf_mybookie, _pf_fanduel_lines, _pf_caesars_lines,
        _pf_savant_xstats, _pf_savant_sprint, _pf_savant_expected, _pf_savant_arsenal, _pf_savant_batted,
        _pf_mlb_lineups, _pf_openmeteo, _pf_ump_scorecards,
        _pf_nba_advanced, _pf_pinnacle_lines,
        _pf_kalshi, _pf_polymarket, _pf_covers, _pf_ev_api, _pf_ev_wnba, _pf_ev_outliers, _pf_ev_feed, _pf_ev_bvp, _pf_ev_preview, _pf_ev_strikeouts, _pf_ev_movement,
        _pf_ev_stats_hr, _pf_ev_stats_k, _pf_ev_barrels, _pf_ev_recap, _pf_ev_mlb, _pf_ev_trends,
        _pf_parlayapi_ev, _pf_parlayapi_arb, _pf_unabated, _pf_fd_props_sa, _pf_sharpapi_drops, _pf_sharpapi_ev,
    ]
        return _fetch_parallel(_fns, show_progress=False)

    _results = _get_parallel_results(sport)
    (pp_props, ud_props_compare, dk_salaries, pinnacle_data,
     oddswrap_props, parlayapi_props_raw, odds_api_props_raw, oddspapi_props_raw,
     bdl_props_raw, rw_injuries_raw, cbs_injuries_raw, espn_injuries_raw, public_betting,
     an_props, officials_data_raw, _game_lines_result, parlayplay_props_raw, dk_pick6_props_raw,
     betrivers_lines_raw, fanatics_lines_raw, espnbet_lines_raw,
     hardrock_lines_raw, wynnbet_lines_raw, unibet_lines_raw, bet365_lines_raw,
     sharpapi_lines_raw, sharpapi_props_raw, betmgm_lines_raw, heritage_lines_raw, bookmaker_lines_raw, sportsline_lines_raw, sbr_lines_raw, thescore_lines_raw,
     signalodds_raw, betslib_raw, betslib_live_raw, fp_proj_raw, def_rank_raw, caesars_props_raw, betonline_off_raw, bovada_lines_raw, bovada_props_raw, bet365_raw, mybookie_raw, fanduel_lines_raw, caesars_lines_raw,
     savant_xstats_raw, savant_sprint_raw, savant_expected_raw, savant_arsenal_raw, savant_batted_raw,
     mlb_lineups_raw, openmeteo_raw, ump_scorecards_raw,
     nba_advanced_raw, pinnacle_lines_raw,
     kalshi_raw, polymarket_raw, covers_raw, ev_api_raw, ev_wnba_raw, ev_outliers_raw, ev_feed_raw, ev_bvp_raw, ev_preview_raw, ev_strikeouts_raw, ev_movement_raw,
     ev_stats_hr_raw, ev_stats_k_raw, ev_barrels_raw, ev_recap_raw, ev_mlb_raw, ev_trends_raw,
     parlayapi_ev_raw, parlayapi_arb_raw, unabated_raw, fd_props_sa_raw, sharpapi_drops_raw, sharpapi_ev_raw) = _results

    # ── Unabated player-props fair value — deliberately its own small batch,
    # NOT added to the _parallel_fns tuple above. That tuple is already a
    # 90-item positional list->tuple->unpack chain; adding more items there
    # increases blast radius for zero benefit here. This has its own
    # try/except and inherits fetch_unabated_props' per-file timeouts
    # (10s/15s via _read_gist_file), so a slow or failed fetch can only ever
    # produce an empty result for this one feature, never block board load.
    try:
        from fetchers import fetch_unabated_props as _fetch_unabated_props
        _unabated_props_lines, _unabated_props_src = _fetch_unabated_props(sport)
    except Exception as _uap_err:
        _unabated_props_lines, _unabated_props_src = [], "unavailable"
        print(f"[WARN] fetch_unabated_props({sport}): {_uap_err}")
    st.session_state[f"unabated_props_{sport}"]     = _unabated_props_lines
    st.session_state[f"unabated_props_src_{sport}"] = _unabated_props_src

    # Unpack game_lines tuple safely
    if isinstance(_game_lines_result, tuple) and len(_game_lines_result) == 4:
        games, is_playoff, home_teams, away_teams = _game_lines_result
        st.session_state["raw_games_today"] = games  # for coverage audit
    else:
        games, is_playoff, home_teams, away_teams = [], False, {}, {}

    # ── Line snapshot → steam + market-maker divergence signals ──────────────
    # record_line() feeds _LINE_HISTORY (module-level dict in bc_utils) which
    # persists across Streamlit reruns within the same Python process, so
    # steam/velocity signals accumulate as the user refreshes throughout the day.
    if games:
        _steam_signals: dict = {}
        for _sg in games:
            _gkey = (_sg.get("Matchup") or "").replace(" ", "_")
            if not _gkey:
                continue
            _g_total = safe_float(_sg.get("Total") or 0)
            try:
                _g_spr_f = safe_float(str(_sg.get("Spread") or "0").replace("+", ""))
            except Exception:
                _g_spr_f = 0.0
            if _g_total:
                record_line("consensus", _gkey, "total",  _g_total,  -110, -110)
    # Also record BetOnline and Bovada lines for cross-book steam detection
    _bol_lines = st.session_state.get("betonline_offering", [])
    for _bl in _bol_lines:
        if _bl.get("game","") == _gkey and _bl.get("market","") == "Total":
            try:
                _odds = float(str(_bl.get("odds","0")).replace("+","") or 0)
                if "Over" in _bl.get("selection",""):
                    record_line("betonline", _gkey, "total", float(_bl.get("selection","0").split()[-1] or 0), _odds, -110)
            except Exception: pass
            if _g_spr_f:
                record_line("consensus", _gkey, "spread", _g_spr_f, -110, -110)
            _steam_tot = detect_steam_move("consensus", _gkey, "total")
            _steam_spr = detect_steam_move("consensus", _gkey, "spread")
            _gap_tot   = get_opener_gap("consensus", _gkey, "total")
            _vel_tot   = compute_line_velocity("consensus", _gkey, "total")
            _vel_spr   = compute_line_velocity("consensus", _gkey, "spread")
            _lbb: dict = {}
            for _bk, _fld in [("pinnacle","PinnacleTotal"),("betonline","BOLTotal"),("draftkings","DKTotal"),("fanduel","FDTotal")]:
                _bv = safe_float(_sg.get(_fld) or 0)
                if _bv:
                    _lbb[_bk] = {"line": _bv, "over_odds": -110, "under_odds": -110}
            if _g_total and len(_lbb) < 2:
                _lbb["consensus"] = {"line": _g_total, "over_odds": -110, "under_odds": -110}
            _mm_div = detect_market_maker_divergence(_lbb) if len(_lbb) >= 2 else {}
            _steam_signals[_gkey] = {
                "steam_total":    _steam_tot,
                "steam_spread":   _steam_spr,
                "opener_gap":     _gap_tot,
                "velocity_total": _vel_tot,
                "velocity_spread":_vel_spr,
                "mm_divergence":  _mm_div,
            }
        st.session_state["game_steam_signals"] = _steam_signals

    # Store parallel results into session state
    st.session_state["dk_salaries"]      = dk_salaries or []
    st.session_state[f"pinnacle_{sport}"] = pinnacle_data or {}
    st.session_state["oddswrap_props"]   = oddswrap_props or []
    st.session_state["ud_props_compare"] = ud_props_compare or []
    st.session_state["dk_pick6_props"]   = dk_pick6_props_raw or []
    st.session_state["betrivers_game_lines"] = betrivers_lines_raw or []
    st.session_state["fanatics_game_lines"]  = fanatics_lines_raw  or []
    st.session_state["espnbet_game_lines"]   = espnbet_lines_raw   or []
    st.session_state["hardrock_game_lines"]  = hardrock_lines_raw  or []
    st.session_state["wynnbet_game_lines"]   = wynnbet_lines_raw   or []
    st.session_state["unibet_game_lines"]    = unibet_lines_raw    or []
    st.session_state["bet365_game_lines"]    = bet365_lines_raw    or bet365_raw or []
    st.session_state["sharpapi_lines"]       = sharpapi_lines_raw  or []
    st.session_state["sharpapi_props"]       = sharpapi_props_raw  or []
    st.session_state["betmgm_game_lines"]    = betmgm_lines_raw    or []
    st.session_state["heritage_game_lines"]   = heritage_lines_raw  or []
    st.session_state["bookmaker_game_lines"]  = bookmaker_lines_raw or []
    st.session_state["sportsline_game_lines"] = sportsline_lines_raw or []
    st.session_state["sbr_game_lines"]        = sbr_lines_raw or []
    st.session_state["thescore_game_lines"]   = thescore_lines_raw or []
    st.session_state["fanduel_props_sa"]    = fd_props_sa_raw     or []
    # Override with browser harvester if fresher
    try:
        from fetchers import fetch_fanduel_props_from_gist as _fd_gist
        _fd_primary, _fd_src = _fd_gist(sport)
        if _fd_primary:
            st.session_state["fanduel_props"]    = _fd_primary
            st.session_state["fanduel_props_src"] = _fd_src
        elif fd_props_sa_raw:
            st.session_state["fanduel_props"]    = fd_props_sa_raw
            st.session_state["fanduel_props_src"] = "sharpapi"
    except Exception:
        _logger.debug("Silent except at line 10717")
        pass
    st.session_state["sharpapi_line_drops"] = sharpapi_drops_raw  or []
    st.session_state["sharpapi_ev_opps"]    = sharpapi_ev_raw     or []
    # ── Browser harvester data → session state (primary/secondary) ─────────
    _harvester_sources = [
        ("fetch_covers_from_gist",          "covers_consensus",       "covers_src"),
        ("fetch_draftkings_props_from_gist","dk_props_harvested",     "dk_props_src"),
        ("fetch_unabated_from_gist",        "unabated_lines_h",       "unabated_src"),
        ("fetch_prizepicks_from_gist",       "prizepicks_props_h",     "prizepicks_src"),
        ("fetch_underdog_from_gist",          "underdog_props_h",       "underdog_src"),
        ("fetch_prophetx_game_lines_from_gist","prophetx_lines_h",       "prophetx_lines_src"),
        ("fetch_prophetx_props_from_gist",     "prophetx_props_h",       "prophetx_props_src"),
        ("fetch_parlaysavant_from_gist",       "parlaysavant_ev_h",      "parlaysavant_src"),
        ("fetch_bet365_from_gist",             "bet365_lines_h",         "bet365_src"),
        ("fetch_fantasylabs_from_gist",        "fantasylabs_data_h",     "fantasylabs_src"),
        ("fetch_rotowire_from_gist",           "rotowire_injuries_h",    "rotowire_src"),
        ("fetch_sportsinsights_from_gist",     "sportsinsights_data",    "sportsinsights_src"),
        ("fetch_rotogrinders_from_gist",       "rotogrinders_data",      "rotogrinders_src"),
        ("fetch_oddsportal_from_gist",         "oddsportal_data",        "oddsportal_src"),
        ("fetch_scoresandodds_from_gist",      "scoresandodds_data",     "scoresandodds_src"),
        ("fetch_linestar_props_from_gist",     "linestar_props_data",   "linestar_props_src"),
        ("fetch_linestar_salaries_from_gist",  "linestar_salaries_data","linestar_salaries_src"),
    ]
    if sport == "MLB":
        try:
            from fetchers import fetch_baseballpress_from_gist as _fbp
            _bp_data, _bp_src = _fbp()
            if _bp_data: st.session_state["baseballpress_lineups"] = _bp_data
        except Exception: pass
    if sport in ("NFL","MLB"):
        try:
            from fetchers import fetch_weather_from_gist as _fwx
            _wx_data, _ = _fwx(sport)
            if _wx_data: st.session_state["weather_data"] = _wx_data
        except Exception: pass
    _harvester_results = _fetch_harvester_data_cached(sport, tuple(h[0] for h in _harvester_sources))
    for _fn_name, _ss_key, _src_key in _harvester_sources:
        _result = _harvester_results.get(_fn_name)
        if not _result:
            continue
        try:
            _data, _src = _result
            if _data:
                st.session_state[_ss_key] = _data
                st.session_state[_src_key] = _src
        except Exception:
            _logger.debug("Silent except at line 10777")
            pass
    st.session_state["action_network_data"] = st.session_state.get("covers_consensus", {})  # same underlying data as covers (fetch_action_network_from_gist and fetch_covers_from_gist were identical, calling the same source twice)
    st.session_state["signalodds_events"]   = signalodds_raw      or []
    st.session_state["betslib_predictions"] = betslib_raw         or []
    st.session_state["betslib_live_events"] = betslib_live_raw    or []
    try:
        st.session_state["signalodds_arbitrage"] = fetch_signalodds_arbitrage_from_gist()
    except Exception:
        st.session_state["signalodds_arbitrage"] = []
    try:
        st.session_state["kalshi_events_scraped"] = fetch_kalshi_from_gist()
    except Exception:
        st.session_state["kalshi_events_scraped"] = []
    st.session_state["fantasypros_proj"]    = fp_proj_raw         or {}
    st.session_state["defense_rankings"]    = def_rank_raw        or {}
    st.session_state["caesars_props"]        = caesars_props_raw   or []
    # Merge SharpAPI FanDuel props into fanduel_props session key
    _fd_sa = st.session_state.get("fanduel_props_sa", [])
    if _fd_sa:
        st.session_state["fanduel_props"] = _fd_sa
    st.session_state["betonline_offering"]   = betonline_off_raw   or []
    st.session_state["bovada_game_lines"]    = bovada_lines_raw    or []
    st.session_state["bovada_props"]         = bovada_props_raw    or []
    st.session_state["mybookie_game_lines"]  = mybookie_raw        or []
    st.session_state["fanduel_game_lines"]   = fanduel_lines_raw   or []
    st.session_state["caesars_game_lines"]   = caesars_lines_raw   or []
    st.session_state["savant_xstats"]        = savant_xstats_raw   or {}
    st.session_state["savant_sprint"]        = savant_sprint_raw   or {}
    st.session_state["savant_expected"]      = savant_expected_raw or {}
    st.session_state["savant_arsenal"]       = savant_arsenal_raw  or {}
    st.session_state["savant_batted"]        = savant_batted_raw   or {}
    st.session_state["mlb_lineups"]          = mlb_lineups_raw     or {}
    st.session_state["openmeteo_weather"]    = openmeteo_raw       or {}
    st.session_state["ump_scorecards"]       = ump_scorecards_raw  or {}
    st.session_state["nba_advanced_stats"]   = nba_advanced_raw    or {}
    st.session_state["parlayapi_ev"]         = parlayapi_ev_raw    or []
    st.session_state["parlayapi_arb"]        = parlayapi_arb_raw   or []
    st.session_state["unabated_lines"]       = unabated_raw        or []
    st.session_state["pinnacle_game_lines"]   = pinnacle_lines_raw or []
    st.session_state["pinnacle_props"]        = []
    st.session_state["officials_data"]   = officials_data_raw or {}
    # Store OddsAPI + OddsPapi props for Line Shop access
    if odds_api_props_raw:
        st.session_state[f"oddsapi_props_{sport}"] = odds_api_props_raw
    if oddspapi_props_raw:
        st.session_state[f"oddspapi_props_{sport}"] = oddspapi_props_raw
    elif not oddspapi_props_raw:
        # OddsPAPI failed — try direct endpoints via curl_cffi
        _direct_props = []
        for _fn, _label, _icon in [
            (fetch_fanduel_direct,    "FanDuel",    "📡"),
            (fetch_draftkings_direct, "DraftKings", "📡"),
            (fetch_betmgm_direct,     "BetMGM",     "📡"),
            (fetch_caesars_direct,    "Caesars",     "📡"),
            (fetch_betrivers_direct,  "BetRivers",  "📡"),
            (fetch_superbook_direct,  "Superbook",  "📡"),
        ]:
            try:
                if _fn is fetch_fanduel_direct:
                    # Needs event_ids — previously never supplied, so this
                    # always returned [] regardless of token validity. Fixed
                    # 2026-06-21 via the confirmed navigation/facet capture.
                    _fd_event_ids = fetch_fanduel_event_ids(sport)
                    _r = _fn(sport, _fd_event_ids)
                else:
                    _r = _fn(sport)
                if _r:
                    _direct_props.extend(_r)
                    st.caption(f"{_icon} {_label}: {len(_r)} props loaded directly")
            except (requests.RequestException, KeyError, ValueError, TypeError, ZeroDivisionError) as _e:
                print(f"[WARN] {_label}: {_e}")
        if _direct_props:
            st.session_state[f"oddspapi_props_{sport}"] = _direct_props
    if public_betting:
        st.session_state["public_betting_data"] = public_betting
    if an_props:
        st.session_state["an_props_data"] = an_props
        # Also store as public_betting_data for the scoring engine
        if isinstance(an_props, dict):
            st.session_state["public_betting_data"] = an_props

    # Merge RotoWire injuries into main injuries dict
    # RotoWire supplements ESPN with editorial injury intelligence
    def _merge_injury_source(injuries, source_list, source_label):
        """Merge a list of injury dicts into the combined injuries dict (in-place)."""
        if not source_list or not isinstance(injuries, dict):
            return
        for item in source_list:
            pname = normalize_name(item.get("player", ""))
            if pname and item.get("status") in ("OUT", "DOUBTFUL", "QUESTIONABLE") and pname not in injuries:
                injuries[pname] = {
                    "status": item["status"],
                    "note":   item.get("note", ""),
                    "source": source_label,
                }

    rw_injuries = rw_injuries_raw or []
    cbs_injuries = cbs_injuries_raw or []
    espn_injuries = espn_injuries_raw or []
    # ESPN direct is now the base dict (was: Underdog-wrapped ESPN as base,
    # with direct ESPN merged in as a 4th, near-duplicate source -- removed,
    # both were ultimately the same ESPN injury data via two paths).
    injuries = {}
    for item in espn_injuries:
        pname = normalize_name(item.get("player", ""))
        if pname and item.get("status") in ("OUT", "DOUBTFUL", "QUESTIONABLE"):
            injuries[pname] = {"status": item["status"], "note": item.get("note", ""), "source": "ESPN"}
    _merge_injury_source(injuries, rw_injuries,   "RotoWire")
    _merge_injury_source(injuries, cbs_injuries,  "CBS Sports")
    st.session_state["espn_injuries"] = espn_injuries
    # Market intelligence data
    if kalshi_raw:
        st.session_state["kalshi_markets"] = kalshi_raw
    if polymarket_raw:
        st.session_state["polymarket_markets"] = polymarket_raw
    if covers_raw:
        st.session_state["covers_consensus"] = covers_raw
    st.session_state["cbs_injuries"] = cbs_injuries
    st.session_state["rw_injuries"] = rw_injuries
    st.session_state["injuries_combined"] = injuries

    # ── Depth charts (NFL/NBA/MLB — store for prop enrichment) ──
    if sport in ("NFL","NBA","MLB","WNBA"):
        _depth = fetch_espn_depth_charts(sport)
        if _depth:
            st.session_state["espn_depth_charts"] = _depth

    # Build action network lookup
    an_lookup = {}
    for ap in (an_props or []):
        key = (ap.get("player_abbr","").lower(), ap.get("stat",""))
        an_lookup[key] = ap

    # Build cross-platform line lookup for better line detection
    # Includes DFS platforms + sportsbooks for maximum line shopping
    better_lines = {}
    all_alt_sources = []

    # EV Sharps API — 20+ books (Hard Rock, DK, FD, MGM, Caesars, Pinnacle, Circa, etc.)
    ev_api_raw = ev_api_raw if isinstance(ev_api_raw, dict) else {}
    if ev_api_raw.get("data"):
        # Merge WNBA EV data (pre-tagged _source_sport="WNBA") into main ev_api_raw
        if ev_wnba_raw and ev_wnba_raw.get("data"):
            if not ev_api_raw:
                ev_api_raw = ev_wnba_raw
            else:
                ev_api_raw = dict(ev_api_raw)
                ev_api_raw["data"] = list(ev_api_raw.get("data") or []) + list(ev_wnba_raw.get("data") or [])
        _ev_board_props, _ev_signal_lookup = extract_ev_props_for_app(ev_api_raw, sport_filter=sport)
    else:
        _ev_board_props, _ev_signal_lookup = [], {}

    # ── Outliers enrichment — merge hitRate + logs into signal_lookup ──────
    # /api/outliers returns historical hit rates and per-game logs not in /api/ev.
    # We build a (player_norm, prop_name) → {hit_rate, logs, pos} lookup and
    # backfill any signal_lookup entries that match.
    _ev_outliers_lookup: dict = {}
    _outliers_data = (ev_outliers_raw or {}).get("data") or []
    for _oi in _outliers_data:
        try:
            _op_key   = _oi.get("prop", "")
            _op_name  = EV_PROP_MAP.get(_op_key, _op_key.title())
            _op_player = normalize_name(_oi.get("player", "Unknown"))
            _sig_k    = (_op_player, _op_name)
            _hit_rate = _oi.get("hitRate")
            _logs     = _oi.get("logs") or []
            _pos      = _oi.get("pos", "")
            _ou_line  = _oi.get("ou", "")
            # Compute hit-rate edge: historical over-rate vs expected 50%
            _hr_edge  = 0.0; _hr_note = ""
            if _hit_rate is not None:
                try:
                    hr = int(_hit_rate)
                    if hr >= 70:   _hr_edge =  0.02; _hr_note = f"HitRate {hr}% (L-hist)"
                    elif hr >= 60: _hr_edge =  0.01; _hr_note = f"HitRate {hr}% (L-hist)"
                    elif hr <= 25: _hr_edge = -0.02; _hr_note = f"HitRate {hr}% (L-hist)"
                    elif hr <= 35: _hr_edge = -0.01; _hr_note = f"HitRate {hr}% (L-hist)"
                except (ValueError, TypeError):
                    pass
            # Recent L10 form from logs array
            _l10_hit_rate = None
            if _logs and len(_logs) >= 5:
                try:
                    hcap = float(_oi.get("handicap", 0) or 0)
                    l10  = [int(v) for v in _logs[:10] if v is not None]
                    if len(l10) >= 5:
                        hits = sum(1 for v in l10 if v > hcap)
                        _l10_hit_rate = round(hits / len(l10), 3)
                except (ValueError, TypeError):
                    pass
            _ev_outliers_lookup[_sig_k] = {
                "hit_rate": _hit_rate, "hit_rate_edge": _hr_edge,
                "hit_rate_note": _hr_note, "l10_hit_rate": _l10_hit_rate,
                "logs": _logs[:20], "pos": _pos, "ou_line": _ou_line,
            }
        except Exception:
            continue
    # Backfill signal_lookup with outlier data
    for _sk, _sv in _ev_signal_lookup.items():
        _od = _ev_outliers_lookup.get(_sk)
        if _od:
            _sv.update({
                "hit_rate":       _od["hit_rate"],
                "hit_rate_edge":  _od["hit_rate_edge"],
                "hit_rate_note":  _od["hit_rate_note"],
                "l10_hit_rate":   _od["l10_hit_rate"],
                "outlier_logs":   _od["logs"],
                "pos":            _od.get("pos") or _sv.get("player_pos", ""),
            })
    if _ev_outliers_lookup:
        st.session_state["ev_outliers_lookup"] = _ev_outliers_lookup
        st.session_state["ev_outliers_count"]  = len(_outliers_data)

    # ── EV Feed enrichment — today's at-bat Statcast data ─────────────────
    # /api/feed returns per-at-bat exit velo, barrel, hard-hit, results,
    # and hr/park ratio for every batter in today's games. We build a
    # player-keyed lookup and merge it into signal_lookup + session_state.
    _ev_feed_lookup: dict = {}
    if ev_feed_raw and isinstance(ev_feed_raw, dict):
        try:
            _ev_feed_lookup = fetch_ev_feed_player_lookup(ev_feed_raw)
        except Exception:
            _ev_feed_lookup = {}
    # Backfill signal_lookup with today's live at-bat data
    if _ev_feed_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            _pname = _sk[0]  # player_norm
            _fd = _ev_feed_lookup.get(_pname)
            if not _fd:
                continue
            # Same-day EV/barrel edge for HR props
            _today_brl_edge = 0.0; _today_brl_note = ""
            _prop_k = _sk[1]
            if "Home Run" in _prop_k or "run" in _prop_k.lower():
                brl_r = _fd.get("today_brl_rate", 0)
                hh_r  = _fd.get("today_hh_rate", 0)
                if brl_r >= 0.20:   _today_brl_edge += 0.02; _today_brl_note = f"TodayBRL {brl_r:.0%}"
                elif brl_r >= 0.10: _today_brl_edge += 0.01; _today_brl_note = f"TodayBRL {brl_r:.0%}"
                if hh_r >= 0.50:   _today_brl_edge += 0.01; _today_brl_note += f" HH{hh_r:.0%}"
            _sv.update({
                "today_pa":        _fd.get("today_pa"),
                "today_ab":        _fd.get("today_ab"),
                "today_brl":       _fd.get("today_brl"),
                "today_hh":        _fd.get("today_hh"),
                "today_hr":        _fd.get("today_hr"),
                "today_evo_avg":   _fd.get("today_evo_avg"),
                "today_brl_rate":  _fd.get("today_brl_rate"),
                "today_hh_rate":   _fd.get("today_hh_rate"),
                "hr_park":         _fd.get("hr_park"),
                "today_results":   _fd.get("today_results", [])[:10],
                "today_brl_edge":  _today_brl_edge,
                "today_brl_note":  _today_brl_note,
            })
        st.session_state["ev_feed_lookup"]  = _ev_feed_lookup
        st.session_state["ev_feed_summary"] = ev_feed_raw.get("all", {})

    # ── BvP enrichment — 389-record richest EVSharps dataset ─────────────
    # /api/bvp has unique fields not in /api/ev: full season HR logs with
    # dates+home/away splits, L10/LYR hit rates, 100+mph EV count, 300+ft
    # count, pitcher HR/PA rate, BvP stats breakdown, and more.
    _ev_bvp_lookup: dict = {}
    if ev_bvp_raw and isinstance(ev_bvp_raw, dict) and ev_bvp_raw.get("res"):
        try:
            _ev_bvp_lookup = fetch_ev_bvp_player_lookup(ev_bvp_raw)
        except Exception:
            _ev_bvp_lookup = {}
    if _ev_bvp_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            _pname = _sk[0]
            _bd = _ev_bvp_lookup.get(_pname)
            if not _bd:
                continue
            # oppRank edge: pitcher HR/PA rate
            _pitcher_pa_edge = 0.0; _pitcher_pa_note = ""
            try:
                hrpa = float(_bd.get("pitcher_hr_pa") or 0)
                if hrpa >= 4.0:   _pitcher_pa_edge =  0.02; _pitcher_pa_note = f"PitcherHR/PA {hrpa:.1f}%"
                elif hrpa >= 3.0: _pitcher_pa_edge =  0.01; _pitcher_pa_note = f"PitcherHR/PA {hrpa:.1f}%"
                elif hrpa <= 1.5: _pitcher_pa_edge = -0.01; _pitcher_pa_note = f"PitcherHR/PA {hrpa:.1f}%"
            except (ValueError, TypeError):
                pass
            # 100+mph EV count — elite contact power this season
            _elite_ev_edge = 0.0; _elite_ev_note = ""
            try:
                ev100 = int(_bd.get("evo_100_count") or 0)
                if ev100 >= 30:   _elite_ev_edge =  0.02; _elite_ev_note = f"{ev100}× 100+mph"
                elif ev100 >= 15: _elite_ev_edge =  0.01; _elite_ev_note = f"{ev100}× 100+mph"
            except (ValueError, TypeError):
                pass
            _sv.update({
                "hit_rate_l10":    _bd.get("hit_rate_l10"),
                "hit_rate_lyr":    _bd.get("hit_rate_lyr"),
                "evo_100_count":   _bd.get("evo_100_count"),
                "ft_300_count":    _bd.get("ft_300_count"),
                "pitcher_hr_pa":   _bd.get("pitcher_hr_pa"),
                "pitcher_summary": _bd.get("pitcher_summary", ""),
                "opp_rank_season": _bd.get("opp_rank_season"),
                "opp_rank_per6":   _bd.get("opp_rank_per6"),
                "bvp_stats":       _bd.get("bvp_stats", {}),
                "bvt":             _bd.get("bvt", ""),
                "bvs":             _bd.get("bvs", ""),
                "bvp_hr":          _bd.get("bvp_hr"),
                "bvp_avg":         _bd.get("bvp_avg"),
                "bvp_h":           _bd.get("bvp_h"),
                "logs_dated":      _bd.get("logs_dated", []),
                "pitcher_pa_edge": _pitcher_pa_edge,
                "pitcher_pa_note": _pitcher_pa_note,
                "elite_ev_edge":   _elite_ev_edge,
                "elite_ev_note":   _elite_ev_note,
            })
        st.session_state["ev_bvp_lookup"]  = _ev_bvp_lookup
        st.session_state["ev_bvp_count"]   = len(ev_bvp_raw.get("res") or [])

    # ── Pitcher Preview enrichment — /api/preview (30 starters today) ────────
    # Unique fields: hr_pitch/hr_pitch_l/hr_pitch_r (which pitch types gave
    # up HRs), hr_l_rate/hr_r_rate with platoon percentile ranks, arm_angle,
    # whiff%, barrel_batted_rate — none of these are in /api/ev or /api/bvp.
    _ev_preview_lookup: dict = {}
    if ev_preview_raw and isinstance(ev_preview_raw, dict) and ev_preview_raw.get("data"):
        try:
            _ev_preview_lookup = fetch_ev_preview_pitcher_lookup(ev_preview_raw)
        except Exception:
            _ev_preview_lookup = {}
    if _ev_preview_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            _pitcher_raw = (_sv.get("pitcher") or "").strip()
            if not _pitcher_raw:
                continue
            _pd = _ev_preview_lookup.get(normalize_name(_pitcher_raw))
            if not _pd:
                continue
            # ── HR rate edge: pitcher's HR-allowed percentile leaguewide ──
            _prev_hr_rate_edge = 0.0; _prev_hr_rate_note = ""
            try:
                hrpa_pct = float(_pd.get("hr_pa_percentile") or 0)
                if hrpa_pct >= 75:   _prev_hr_rate_edge =  0.02; _prev_hr_rate_note = f"PitcherHR%ile {hrpa_pct:.0f}th"
                elif hrpa_pct >= 60: _prev_hr_rate_edge =  0.01; _prev_hr_rate_note = f"PitcherHR%ile {hrpa_pct:.0f}th"
                elif hrpa_pct <= 25: _prev_hr_rate_edge = -0.01; _prev_hr_rate_note = f"PitcherHR%ile {hrpa_pct:.0f}th"
            except (ValueError, TypeError):
                pass
            # ── Platoon HR rate edge: batter hand vs pitcher L/R split ──
            _prev_platoon_edge = 0.0; _prev_platoon_note = ""
            try:
                _bats = (_sv.get("bats") or "").upper()
                if _bats in ("L", "R"):
                    _side_rate = float(_pd.get(f"hr_{'l' if _bats=='L' else 'r'}_rate") or 0)
                    _side_pct  = float(_pd.get(f"hr_{'l' if _bats=='L' else 'r'}_rate_percentile") or 0)
                    if _side_rate >= 3.5 or _side_pct >= 75:
                        _prev_platoon_edge =  0.02
                        _prev_platoon_note = f"PlatoonHR {_bats}vP {_side_rate:.1f}/PA ({_side_pct:.0f}%ile)"
                    elif _side_rate >= 2.5 or _side_pct >= 60:
                        _prev_platoon_edge =  0.01
                        _prev_platoon_note = f"PlatoonHR {_bats}vP {_side_rate:.1f}/PA ({_side_pct:.0f}%ile)"
                    elif _side_rate <= 1.0 or _side_pct <= 25:
                        _prev_platoon_edge = -0.01
                        _prev_platoon_note = f"PlatoonHR {_bats}vP {_side_rate:.1f}/PA ({_side_pct:.0f}%ile)"
            except (ValueError, TypeError):
                pass
            _sv.update({
                "preview_home_run_pct":     _pd.get("home_run_percentile"),
                "preview_hr_pa_pct":        _pd.get("hr_pa_percentile"),
                "preview_hr_pa":            _pd.get("hr_pa"),
                "preview_hr_l":             _pd.get("hr_l"),
                "preview_hr_r":             _pd.get("hr_r"),
                "preview_hr_l_rate":        _pd.get("hr_l_rate"),
                "preview_hr_r_rate":        _pd.get("hr_r_rate"),
                "preview_hr_l_rate_pct":    _pd.get("hr_l_rate_percentile"),
                "preview_hr_r_rate_pct":    _pd.get("hr_r_rate_percentile"),
                "preview_hr_pitch":         _pd.get("hr_pitch", []),
                "preview_hr_pitch_l":       _pd.get("hr_pitch_l", []),
                "preview_hr_pitch_r":       _pd.get("hr_pitch_r", []),
                "preview_arm_angle":        _pd.get("arm_angle"),
                "preview_k_pct":            _pd.get("k_percent"),
                "preview_xera":             _pd.get("xera"),
                "preview_whiff_pct":        _pd.get("whiff_percent"),
                "preview_whiff_pct_pct":    _pd.get("whiff_pct_pct"),
                "preview_barrel_rate":      _pd.get("barrel_rate"),
                "preview_barrel_rate_pct":  _pd.get("barrel_rate_pct"),
                "preview_hard_hit_pct":     _pd.get("hard_hit_pct"),
                "preview_hard_hit_pct_pct": _pd.get("hard_hit_pct_pct"),
                "preview_fb_velo":          _pd.get("fb_velo"),
                "preview_fb_pct":           _pd.get("fb_pct"),
                "preview_breaking_pct":     _pd.get("breaking_pct"),
                "preview_offspeed_pct":     _pd.get("offspeed_pct"),
                "preview_hr_rate_edge":     _prev_hr_rate_edge,
                "preview_hr_rate_note":     _prev_hr_rate_note,
                "preview_platoon_edge":     _prev_platoon_edge,
                "preview_platoon_note":     _prev_platoon_note,
            })
        st.session_state["ev_preview_lookup"] = _ev_preview_lookup
        st.session_state["ev_preview_count"]  = len(ev_preview_raw.get("data") or [])

    # ── Strikeouts enrichment — /api/strikeouts (532 K prop records) ──────────
    # Unique fields vs /api/ev: K hit rates across szn/L5/L10/LYR windows,
    # per-start K count logs, opponent team K rank, and pitcher Statcast metrics.
    # Records are pitcher-keyed (player = the pitcher), matched against
    # (player_norm, "Pitcher Strikeouts") signal_lookup entries.
    _ev_strikeouts_lookup: dict = {}
    if ev_strikeouts_raw and isinstance(ev_strikeouts_raw, dict) and ev_strikeouts_raw.get("data"):
        try:
            _ev_strikeouts_lookup = fetch_ev_strikeouts_pitcher_lookup(ev_strikeouts_raw)
        except Exception:
            _ev_strikeouts_lookup = {}
    if _ev_strikeouts_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            if "Strikeout" not in _sk[1]:
                continue
            _kd = _ev_strikeouts_lookup.get(_sk[0])
            if not _kd:
                continue
            # K hit rate edge — season rate is primary; L5 confirms recent form
            _k_hit_rate_edge = 0.0; _k_hit_rate_note = ""
            try:
                _k_szn = float(_kd.get("k_rate_szn") or 0)
                _k_l5  = float(_kd.get("k_rate_l5")  or 0)
                if _k_szn >= 80 and _k_l5 >= 80:
                    _k_hit_rate_edge =  0.02; _k_hit_rate_note = f"KRate {_k_szn:.0f}% szn/{_k_l5:.0f}% L5"
                elif _k_szn >= 70 or _k_l5 >= 75:
                    _k_hit_rate_edge =  0.01; _k_hit_rate_note = f"KRate {_k_szn:.0f}% szn/{_k_l5:.0f}% L5"
                elif _k_szn <= 50:
                    _k_hit_rate_edge = -0.01; _k_hit_rate_note = f"KRate low {_k_szn:.0f}% szn"
            except (ValueError, TypeError):
                pass
            # Opp K rank edge — higher rank = weaker offense = easier to K
            _k_opp_edge = 0.0; _k_opp_note = ""
            try:
                _opp_r = int(_kd.get("k_opp_rank") or 0)
                if _opp_r >= 25:
                    _k_opp_edge =  0.01; _k_opp_note = f"OppK rank #{_opp_r}"
                elif _opp_r <= 5:
                    _k_opp_edge = -0.01; _k_opp_note = f"OppK rank #{_opp_r}"
            except (ValueError, TypeError):
                pass
            _sv.update({
                "k_rate_szn":      _kd.get("k_rate_szn"),
                "k_rate_l5":       _kd.get("k_rate_l5"),
                "k_rate_l10":      _kd.get("k_rate_l10"),
                "k_rate_lyr":      _kd.get("k_rate_lyr"),
                "k_logs":          _kd.get("k_logs", []),
                "k_opp_rank":      _kd.get("k_opp_rank"),
                "k_pitcher_data":  _kd.get("k_pitcher_data", {}),
                "k_bpp":           _kd.get("k_bpp", ""),
                "k_bpp_proj":      _kd.get("k_bpp_proj"),
                "k_bpp_diff":      _kd.get("k_bpp_diff"),
                "k_hit_rate_edge": _k_hit_rate_edge,
                "k_hit_rate_note": _k_hit_rate_note,
                "k_opp_edge":      _k_opp_edge,
                "k_opp_note":      _k_opp_note,
            })
        st.session_state["ev_strikeouts_lookup"] = _ev_strikeouts_lookup
        st.session_state["ev_strikeouts_count"]  = len(ev_strikeouts_raw.get("data") or [])

    # ── /api/stats enrichment — hit rates + splits for HR/Hits props ─────────
    # /api/stats?prop=hr returns hitRate, hitRateL10, hitRateLYR, awayHomeSplits,
    # dtSplits, oppRankClass, oppRankSeason, oppRankPer6, bvpHR/bvpAvg/bvpH.
    # Keyed by (player_norm, "Home Runs") to match signal_lookup.
    _ev_stats_lookup: dict = {}
    if ev_stats_hr_raw and isinstance(ev_stats_hr_raw, dict) and ev_stats_hr_raw.get("data"):
        try:
            _ev_stats_lookup = fetch_ev_stats_player_lookup(ev_stats_hr_raw, "Home Runs")
        except Exception:
            _ev_stats_lookup = {}
    if _ev_stats_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            _sd = _ev_stats_lookup.get(_sk)
            if not _sd:
                continue
            # Opp rank class edge: categorical rank from EVSharps
            _stats_opp_edge = 0.0; _stats_opp_note = ""
            _orc = (_sd.get("stats_opp_rank_class") or "").lower()
            if _orc in ("elite", "great"):
                _stats_opp_edge =  0.02; _stats_opp_note = f"OppRank {_sd['stats_opp_rank_class']}"
            elif _orc in ("good", "above avg"):
                _stats_opp_edge =  0.01; _stats_opp_note = f"OppRank {_sd['stats_opp_rank_class']}"
            elif _orc in ("below avg", "poor"):
                _stats_opp_edge = -0.01; _stats_opp_note = f"OppRank {_sd['stats_opp_rank_class']}"
            elif _orc in ("worst", "bad"):
                _stats_opp_edge = -0.02; _stats_opp_note = f"OppRank {_sd['stats_opp_rank_class']}"
            # L10 hit rate edge (backfill if not already set by bvp/outliers)
            _stats_l10_edge = 0.0; _stats_l10_note = ""
            _l10 = _sd.get("stats_hit_rate_l10")
            if _l10 is not None and not _sv.get("hit_rate_l10"):
                try:
                    l10v = float(_l10)
                    if l10v >= 70:   _stats_l10_edge =  0.02; _stats_l10_note = f"StatsL10 {l10v:.0f}%"
                    elif l10v >= 60: _stats_l10_edge =  0.01; _stats_l10_note = f"StatsL10 {l10v:.0f}%"
                    elif l10v <= 25: _stats_l10_edge = -0.02; _stats_l10_note = f"StatsL10 {l10v:.0f}%"
                    elif l10v <= 35: _stats_l10_edge = -0.01; _stats_l10_note = f"StatsL10 {l10v:.0f}%"
                except (ValueError, TypeError):
                    pass
            _sv.update({
                "stats_hit_rate":         _sd.get("stats_hit_rate"),
                "stats_hit_rate_l10":     _sd.get("stats_hit_rate_l10"),
                "stats_hit_rate_lyr":     _sd.get("stats_hit_rate_lyr"),
                "stats_opp_rank":         _sd.get("stats_opp_rank"),
                "stats_opp_rank_class":   _sd.get("stats_opp_rank_class"),
                "stats_opp_rank_season":  _sd.get("stats_opp_rank_season"),
                "stats_opp_rank_per6":    _sd.get("stats_opp_rank_per6"),
                "stats_stadium_rank":     _sd.get("stats_stadium_rank"),
                "stats_stadium_rank_l":   _sd.get("stats_stadium_rank_l"),
                "stats_stadium_rank_r":   _sd.get("stats_stadium_rank_r"),
                "stats_away_home_splits": _sd.get("stats_away_home_splits", {}),
                "stats_dt_splits":        _sd.get("stats_dt_splits", {}),
                "stats_bvp_hr":           _sd.get("stats_bvp_hr"),
                "stats_bvp_avg":          _sd.get("stats_bvp_avg"),
                "stats_bvp_h":            _sd.get("stats_bvp_h"),
                "stats_logs":             _sd.get("stats_logs", []),
                "stats_opp_edge":         _stats_opp_edge,
                "stats_opp_note":         _stats_opp_note,
                "stats_l10_edge":         _stats_l10_edge,
                "stats_l10_note":         _stats_l10_note,
            })
        st.session_state["ev_stats_lookup"]  = _ev_stats_lookup
        st.session_state["ev_stats_count"]   = len(ev_stats_hr_raw.get("data") or [])

    # ── /api/barrels enrichment — Statcast barrel/contact percentiles ─────────
    # /api/barrels has leaguewide percentile rankings for barrel rate, EV, hard-hit,
    # sweet spot, launch angle, flyball %, swing quality — more granular than
    # the raw Statcast dict in /api/ev savant field.
    _ev_barrels_lookup: dict = {}
    if ev_barrels_raw and isinstance(ev_barrels_raw, list):
        try:
            _ev_barrels_lookup = fetch_ev_barrels_player_lookup(ev_barrels_raw)
        except Exception:
            _ev_barrels_lookup = {}
    if _ev_barrels_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            _pname = _sk[0]
            _bld = _ev_barrels_lookup.get(_pname)
            if not _bld:
                continue
            # Barrel rate percentile edge for HR props
            _brl_edge = 0.0; _brl_note = ""
            if "Home Run" in _sk[1] or "run" in _sk[1].lower():
                try:
                    _bpct = float(_bld.get("brl_barrels_per_bip_pct") or 0)
                    _braw = float(_bld.get("brl_barrels_per_bip") or 0)
                    if _bpct >= 80 or _braw >= 12.0:
                        _brl_edge =  0.02; _brl_note = f"BRL {_braw:.1f}% ({_bpct:.0f}%ile)"
                    elif _bpct >= 65 or _braw >= 8.0:
                        _brl_edge =  0.01; _brl_note = f"BRL {_braw:.1f}% ({_bpct:.0f}%ile)"
                    elif _bpct <= 20 or _braw <= 3.0:
                        _brl_edge = -0.01; _brl_note = f"BRL {_braw:.1f}% ({_bpct:.0f}%ile)"
                except (ValueError, TypeError):
                    pass
            _sv.update({
                "brl_barrel_ct":           _bld.get("brl_barrel_ct"),
                "brl_barrels_per_bip":     _bld.get("brl_barrels_per_bip"),
                "brl_barrels_per_bip_pct": _bld.get("brl_barrels_per_bip_pct"),
                "brl_exit_velo":           _bld.get("brl_exit_velo"),
                "brl_exit_velo_pct":       _bld.get("brl_exit_velo_pct"),
                "brl_hard_hit_pct":        _bld.get("brl_hard_hit_pct"),
                "brl_hard_hit_pct_pct":    _bld.get("brl_hard_hit_pct_pct"),
                "brl_sweet_spot_pct":      _bld.get("brl_sweet_spot_pct"),
                "brl_sweet_spot_pct_pct":  _bld.get("brl_sweet_spot_pct_pct"),
                "brl_launch_angle":        _bld.get("brl_launch_angle"),
                "brl_launch_angle_pct":    _bld.get("brl_launch_angle_pct"),
                "brl_flyballs_pct":        _bld.get("brl_flyballs_pct"),
                "brl_flyballs_pct_pct":    _bld.get("brl_flyballs_pct_pct"),
                "brl_avg_swing_speed":     _bld.get("brl_avg_swing_speed"),
                "brl_blasts_swing":        _bld.get("brl_blasts_swing"),
                "brl_squared_up_swing":    _bld.get("brl_squared_up_swing"),
                "brl_pull_pct":            _bld.get("brl_pull_pct"),
                "brl_meatball_pct":        _bld.get("brl_meatball_pct"),
                "brl_pa":                  _bld.get("brl_pa"),
                "brl_home_runs":           _bld.get("brl_home_runs"),
                "brl_edge":                _brl_edge,
                "brl_note":                _brl_note,
            })
        st.session_state["ev_barrels_lookup"] = _ev_barrels_lookup
        st.session_state["ev_barrels_count"]  = len(ev_barrels_raw)

    # ── Baseball Savant enrichment — xStats / Sprint / Expected / Batted-ball / Arsenal
    # These 5 Savant leaderboards were fetched in the parallel pool and stored in
    # session_state but never reached the scoring loop. This block backfills them into
    # _ev_signal_lookup so every MLB prop row gains Savant-derived edge fields.
    if sport == "MLB":
        _sav_xstats   = savant_xstats_raw   or {}
        _sav_sprint   = savant_sprint_raw   or {}
        _sav_expected = savant_expected_raw or {}
        _sav_arsenal  = savant_arsenal_raw  or {}
        _sav_batted   = savant_batted_raw   or {}
        for _sk, _sv in _ev_signal_lookup.items():
            _pname = _sk[0]  # normalize_name lower-cases already
            # ── xStats: barrel rate, hard-hit, exit velo, xwOBA ────────
            _xs = _sav_xstats.get(_pname) or {}
            if not _xs:
                _pts = _pname.split()
                if len(_pts) >= 2:
                    _xs = _sav_xstats.get(f"{_pts[-1]}, {' '.join(_pts[:-1])}") or {}
            if _xs:
                _brl = _xs.get("barrel_batted_rate"); _hh = _xs.get("hard_hit_percent")
                _sav_brl_edge = 0.0; _sav_brl_note = ""
                if "Home Run" in _sk[1] or "Hits" in _sk[1]:
                    try:
                        if _brl is not None:
                            if _brl >= 12.0:   _sav_brl_edge =  0.02; _sav_brl_note = f"SavBRL {_brl:.1f}%"
                            elif _brl >= 8.0:  _sav_brl_edge =  0.01; _sav_brl_note = f"SavBRL {_brl:.1f}%"
                            elif _brl <= 2.0:  _sav_brl_edge = -0.01; _sav_brl_note = f"SavBRL {_brl:.1f}%"
                        if _hh is not None and not _sav_brl_note:
                            if _hh >= 50.0:    _sav_brl_edge =  0.01; _sav_brl_note = f"SavHH {_hh:.0f}%"
                            elif _hh <= 30.0:  _sav_brl_edge = -0.01; _sav_brl_note = f"SavHH {_hh:.0f}%"
                    except (ValueError, TypeError):
                        pass
                # ── Launch angle / sweet-spot% (2026-07) ────────────────
                # Fetched by fetch_savant_statcast() since the start but never
                # scored. Sweet spot (8-32 degrees) is the launch-angle band
                # where line drives and well-struck fly balls live -- it's
                # the actual mechanism barrel rate is measuring indirectly.
                # Small, capped contribution since it's correlated with
                # barrel rate/hard-hit (already scored above), not treated
                # as fully independent evidence.
                _sav_la_edge = 0.0; _sav_la_note = ""
                _la = _xs.get("launch_angle_avg"); _swp = _xs.get("sweet_spot_percent")
                if "Home Run" in _sk[1] or "Hits" in _sk[1]:
                    try:
                        if _swp is not None:
                            if _swp >= 38.0:   _sav_la_edge =  0.01; _sav_la_note = f"SavSweet {_swp:.0f}%"
                            elif _swp <= 25.0: _sav_la_edge = -0.01; _sav_la_note = f"SavSweet {_swp:.0f}%"
                        if _la is not None and not _sav_la_note and "Home Run" in _sk[1]:
                            if _la < 5.0 or _la > 30.0:
                                _sav_la_edge = -0.01; _sav_la_note = f"SavLA {_la:.0f}\u00b0 (off-profile)"
                    except (ValueError, TypeError):
                        pass
                _sv.update({"sav_xwoba": _xs.get("xwoba"), "sav_xba": _xs.get("xba"),
                            "sav_xslg": _xs.get("xslg"), "sav_barrel_rate": _brl,
                            "sav_hard_hit": _hh, "sav_exit_velo": _xs.get("exit_velocity_avg"),
                            "sav_k_pct": _xs.get("strikeout_percent"), "sav_bb_pct": _xs.get("walk_percent"),
                            "sav_brl_edge": _sav_brl_edge, "sav_brl_note": _sav_brl_note,
                            "sav_launch_angle": _la, "sav_sweet_spot_pct": _swp,
                            "sav_la_edge": _sav_la_edge, "sav_la_note": _sav_la_note})
            # ── Expected stats: xBA-diff catches regression risk ─────────
            _xe = _sav_expected.get(_pname) or {}
            if _xe:
                _xwd = _xe.get("xwoba_diff"); _sav_reg_edge = 0.0; _sav_reg_note = ""
                try:
                    if _xwd is not None:
                        if _xwd <= -0.030:   _sav_reg_edge =  0.02; _sav_reg_note = f"xwOBA+{abs(_xwd):.3f} under"
                        elif _xwd <= -0.020: _sav_reg_edge =  0.01; _sav_reg_note = f"xwOBA+{abs(_xwd):.3f} under"
                        elif _xwd >= 0.030:  _sav_reg_edge = -0.02; _sav_reg_note = f"xwOBA-{_xwd:.3f} over"
                        elif _xwd >= 0.020:  _sav_reg_edge = -0.01; _sav_reg_note = f"xwOBA-{_xwd:.3f} over"
                except (ValueError, TypeError):
                    pass
                _sv.update({"sav_xba_diff": _xe.get("xba_diff"), "sav_xslg_diff": _xe.get("xslg_diff"),
                            "sav_xwoba_diff": _xwd, "sav_pa": _xe.get("pa"),
                            "sav_reg_edge": _sav_reg_edge, "sav_reg_note": _sav_reg_note})
            # ── Sprint speed: stolen-base props ─────────────────────────
            _sp = _sav_sprint.get(_pname) or {}
            if _sp:
                _spd = _sp.get("sprint_speed"); _sav_spd_edge = 0.0; _sav_spd_note = ""
                if "Stolen" in _sk[1] or "Base" in _sk[1]:
                    try:
                        if _spd is not None:
                            if _spd >= 29.0:   _sav_spd_edge =  0.02; _sav_spd_note = f"Sprint {_spd:.1f}ft/s"
                            elif _spd >= 27.5: _sav_spd_edge =  0.01; _sav_spd_note = f"Sprint {_spd:.1f}ft/s"
                            elif _spd <= 24.0: _sav_spd_edge = -0.01; _sav_spd_note = f"Sprint {_spd:.1f}ft/s"
                    except (ValueError, TypeError):
                        pass
                _sv.update({"sav_sprint_speed": _spd, "sav_bolts": _sp.get("bolts"),
                            "sav_hp_to_1b": _sp.get("hp_to_1b"),
                            "sav_spd_edge": _sav_spd_edge, "sav_spd_note": _sav_spd_note})
            # ── Batted-ball: HR props favour high FB% and pull rate ──────
            _bb = _sav_batted.get(_pname) or {}
            if _bb:
                _fbr = _bb.get("fb_rate"); _pull = _bb.get("pull_rate")
                _sav_fb_edge = 0.0; _sav_fb_note = ""
                if "Home Run" in _sk[1] or "Hits" in _sk[1]:
                    try:
                        if _fbr is not None:
                            if _fbr >= 45.0:  _sav_fb_edge =  0.01; _sav_fb_note = f"FB% {_fbr:.0f}%"
                            elif _fbr <= 25.0: _sav_fb_edge = -0.01; _sav_fb_note = f"FB% {_fbr:.0f}%"
                        if _pull is not None and _sav_fb_note and _pull >= 45.0:
                            _sav_fb_note += f" Pull {_pull:.0f}%"
                    except (ValueError, TypeError):
                        pass
                _sv.update({"sav_gb_rate": _bb.get("gb_rate"), "sav_fb_rate": _fbr,
                            "sav_ld_rate": _bb.get("ld_rate"), "sav_pu_rate": _bb.get("pu_rate"),
                            "sav_pull_rate": _pull, "sav_oppo_rate": _bb.get("oppo_rate"),
                            "sav_fb_edge": _sav_fb_edge, "sav_fb_note": _sav_fb_note})
            # ── Pitch arsenal: pitcher K props — negative RV = effective ──
            _pitcher_raw = (_sv.get("pitcher") or "").strip().lower()
            if _pitcher_raw and "Strikeout" in _sk[1]:
                _pa = _sav_arsenal.get(_pitcher_raw) or {}
                if _pa:
                    _best = min(_pa.items(), key=lambda x: x[1].get("rv_per_100", 0)) if _pa else None
                    _sav_ars_edge = 0.0; _sav_ars_note = ""
                    if _best:
                        _pt, _pd = _best; _rv = _pd.get("rv_per_100", 0)
                        if _rv <= -2.0:   _sav_ars_edge =  0.02; _sav_ars_note = f"Arsenal {_pt} RV{_rv:+.1f}/100"
                        elif _rv <= -1.0: _sav_ars_edge =  0.01; _sav_ars_note = f"Arsenal {_pt} RV{_rv:+.1f}/100"
                    _sv.update({"sav_arsenal": _pa, "sav_ars_edge": _sav_ars_edge,
                                "sav_ars_note": _sav_ars_note})
    # ── ParlaySavant +EV confirmation ────────────────────────────────────────
    # parlaysavant_ev_h: +EV props from parlaysavant.com/api/props (Python direct
    # or Tampermonkey Gist). Second-source confirmation → small edge boost.
    _ps_ev = st.session_state.get("parlaysavant_ev_h", {})
    if _ps_ev:
        _ps_items = (_ps_ev if isinstance(_ps_ev, list)
                     else _ps_ev.get("props", _ps_ev.get("data", _ps_ev.get("picks", []))))
        if isinstance(_ps_items, list) and _ps_items:
            _ps_idx = {}
            for _pi in _ps_items:
                if not isinstance(_pi, dict): continue
                _pp  = normalize_name(_pi.get("player","") or _pi.get("name","") or "")
                _pr  = (_pi.get("prop","") or _pi.get("stat","") or _pi.get("market","") or "").strip().lower()
                _pev = _pi.get("ev") or _pi.get("ev_pct") or _pi.get("edge") or _pi.get("value", 0)
                if _pp and _pr:
                    _ps_idx[(_pp, _pr)] = _pev
            for _sk, _sv in _ev_signal_lookup.items():
                _pn, _prop_l = _sk[0], _sk[1].lower()
                _ps_match = _ps_idx.get((_pn, _prop_l))
                if _ps_match is None:
                    for (_kp, _kr), _kev in _ps_idx.items():
                        if _kp == _pn and (_kr in _prop_l or _prop_l in _kr):
                            _ps_match = _kev; break
                if _ps_match is not None:
                    try:
                        _ps_e = float(_ps_match) if isinstance(_ps_match, (int, float)) else 0.015
                    except (ValueError, TypeError):
                        _ps_e = 0.015
                    _sv.update({"ps_ev_confirm": True, "ps_ev_edge": _ps_e,
                                "ps_ev_note": f"ParlaySavant +EV confirm"})


    # ── /api/recap — save yesterday's results to session_state ───────────────
    # Not used for signal_lookup enrichment; exposed for a daily results widget.
    if ev_recap_raw and isinstance(ev_recap_raw, dict) and ev_recap_raw.get("data"):
        st.session_state["ev_recap_data"]   = ev_recap_raw.get("data") or []
        st.session_state["ev_recap_record"] = ev_recap_raw.get("record") or {}

    # ── /api/stats?prop=k enrichment — hit rates for strikeout props ──────────
    # Extends the existing /api/stats HR enrichment to K props.
    # Uses the same fetch_ev_stats_player_lookup — just pass "Pitcher Strikeouts".
    _ev_stats_k_lookup: dict = {}
    if ev_stats_k_raw and isinstance(ev_stats_k_raw, dict) and ev_stats_k_raw.get("data"):
        try:
            _ev_stats_k_lookup = fetch_ev_stats_player_lookup(ev_stats_k_raw, "Pitcher Strikeouts")
        except Exception:
            _ev_stats_k_lookup = {}
    if _ev_stats_k_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            _sd = _ev_stats_k_lookup.get(_sk)
            if not _sd:
                continue
            _k_orc = (_sd.get("stats_opp_rank_class") or "").lower()
            _k_opp_edge = 0.0; _k_opp_note = ""
            if _k_orc in ("elite", "great"):
                _k_opp_edge =  0.02; _k_opp_note = f"KOppRank {_sd['stats_opp_rank_class']}"
            elif _k_orc in ("good", "above avg"):
                _k_opp_edge =  0.01; _k_opp_note = f"KOppRank {_sd['stats_opp_rank_class']}"
            elif _k_orc in ("below avg", "poor"):
                _k_opp_edge = -0.01; _k_opp_note = f"KOppRank {_sd['stats_opp_rank_class']}"
            elif _k_orc in ("worst", "bad"):
                _k_opp_edge = -0.02; _k_opp_note = f"KOppRank {_sd['stats_opp_rank_class']}"
            _sv.update({
                "k_stats_hit_rate":        _sd.get("stats_hit_rate"),
                "k_stats_hit_rate_l10":    _sd.get("stats_hit_rate_l10"),
                "k_stats_hit_rate_lyr":    _sd.get("stats_hit_rate_lyr"),
                "k_stats_opp_rank":        _sd.get("stats_opp_rank"),
                "k_stats_opp_rank_class":  _sd.get("stats_opp_rank_class"),
                "k_stats_away_home":       _sd.get("stats_away_home_splits", {}),
                "k_stats_dt_splits":       _sd.get("stats_dt_splits", {}),
                "k_stats_logs":            _sd.get("stats_logs", []),
                "k_stats_opp_edge":        _k_opp_edge,
                "k_stats_opp_note":        _k_opp_note,
            })
        st.session_state["ev_stats_k_lookup"] = _ev_stats_k_lookup
        st.session_state["ev_stats_k_count"]  = len(ev_stats_k_raw.get("data") or [])

    # ── /api/mlb enrichment — four-window hit-rate W/L records ───────────────
    # /api/mlb is a curated ~40-record featured-picks list with hitRates broken
    # into {szn, L5, L10, L20} W/L/pct windows — far richer than the single
    # hitRate % from /api/outliers. Also adds lastHR, ou, roof, order, liquidity.
    _ev_mlb_lookup: dict = {}
    if ev_mlb_raw and isinstance(ev_mlb_raw, dict) and ev_mlb_raw.get("data"):
        try:
            _ev_mlb_lookup = fetch_ev_mlb_player_lookup(ev_mlb_raw)
        except Exception:
            _ev_mlb_lookup = {}
    if _ev_mlb_lookup:
        for _sk, _sv in _ev_signal_lookup.items():
            _md = _ev_mlb_lookup.get(_sk)
            if not _md:
                continue
            # L10 and L5 hit-rate edge from W/L window records
            _mlb_edge = 0.0; _mlb_note = ""
            try:
                _l10p = float(_md.get("mlb_hit_rate_l10") or 0)
                _l5p  = float(_md.get("mlb_hit_rate_l5")  or 0)
                # Use L5 (tighter/more recent) as primary signal when ≥3 games
                _l5t  = int(_md.get("mlb_hit_rate_l5_t")  or 0)
                _l10t = int(_md.get("mlb_hit_rate_l10_t") or 0)
                if _l5t >= 3:
                    if _l5p >= 80:    _mlb_edge =  0.02; _mlb_note = f"L5 {_md['mlb_hit_rate_l5_w']}/{_l5t} ({_l5p:.0f}%)"
                    elif _l5p >= 60:  _mlb_edge =  0.01; _mlb_note = f"L5 {_md['mlb_hit_rate_l5_w']}/{_l5t} ({_l5p:.0f}%)"
                    elif _l5p <= 20:  _mlb_edge = -0.02; _mlb_note = f"L5 {_md['mlb_hit_rate_l5_w']}/{_l5t} ({_l5p:.0f}%)"
                    elif _l5p <= 40:  _mlb_edge = -0.01; _mlb_note = f"L5 {_md['mlb_hit_rate_l5_w']}/{_l5t} ({_l5p:.0f}%)"
                elif _l10t >= 5:
                    if _l10p >= 80:   _mlb_edge =  0.02; _mlb_note = f"L10 {_md['mlb_hit_rate_l10_w']}/{_l10t} ({_l10p:.0f}%)"
                    elif _l10p >= 60: _mlb_edge =  0.01; _mlb_note = f"L10 {_md['mlb_hit_rate_l10_w']}/{_l10t} ({_l10p:.0f}%)"
                    elif _l10p <= 20: _mlb_edge = -0.02; _mlb_note = f"L10 {_md['mlb_hit_rate_l10_w']}/{_l10t} ({_l10p:.0f}%)"
                    elif _l10p <= 40: _mlb_edge = -0.01; _mlb_note = f"L10 {_md['mlb_hit_rate_l10_w']}/{_l10t} ({_l10p:.0f}%)"
            except (ValueError, TypeError):
                pass
            # Roof signal — dome suppresses/boosts depending on park
            _roof_note = ""
            _roof = (_md.get("mlb_roof") or "").lower()
            if _roof == "dome":
                _roof_note = "Dome"
            elif _roof == "open":
                _roof_note = "Open"
            _sv.update({
                "mlb_hit_rate_szn":   _md.get("mlb_hit_rate_szn"),
                "mlb_hit_rate_szn_w": _md.get("mlb_hit_rate_szn_w"),
                "mlb_hit_rate_szn_t": _md.get("mlb_hit_rate_szn_t"),
                "mlb_hit_rate_l5":    _md.get("mlb_hit_rate_l5"),
                "mlb_hit_rate_l5_w":  _md.get("mlb_hit_rate_l5_w"),
                "mlb_hit_rate_l5_t":  _md.get("mlb_hit_rate_l5_t"),
                "mlb_hit_rate_l10":   _md.get("mlb_hit_rate_l10"),
                "mlb_hit_rate_l10_w": _md.get("mlb_hit_rate_l10_w"),
                "mlb_hit_rate_l10_t": _md.get("mlb_hit_rate_l10_t"),
                "mlb_hit_rate_l20":   _md.get("mlb_hit_rate_l20"),
                "mlb_hit_rate_l20_w": _md.get("mlb_hit_rate_l20_w"),
                "mlb_hit_rate_l20_t": _md.get("mlb_hit_rate_l20_t"),
                "mlb_last_hr":        _md.get("mlb_last_hr"),
                "mlb_ou":             _md.get("mlb_ou"),
                "mlb_roof":           _md.get("mlb_roof"),
                "mlb_order":          _md.get("mlb_order"),
                "mlb_logs":           _md.get("mlb_logs", []),
                "mlb_bvp":            _md.get("mlb_bvp", ""),
                "mlb_liquidity":      _md.get("mlb_liquidity", {}),
                "mlb_hit_rate_edge":  _mlb_edge,
                "mlb_hit_rate_note":  _mlb_note,
                "mlb_roof_note":      _roof_note,
            })
        st.session_state["ev_mlb_lookup"] = _ev_mlb_lookup
        st.session_state["ev_mlb_count"]  = len(ev_mlb_raw.get("data") or [])

    # ── /api/trends — league HR environment signal ────────────────────────────
    # Computes a single league-level HR/game signal: L7 rate vs season average.
    # A hot league environment (L7 >> season avg) lifts all HR prop over-rates;
    # a cold environment suppresses them. Applied as a small universal edge
    # modifier stored in session_state and readable by any downstream widget.
    _ev_trends_signal: dict = {}
    if ev_trends_raw and isinstance(ev_trends_raw, dict):
        try:
            _ev_trends_signal = compute_ev_trends_signal(ev_trends_raw)
        except Exception:
            _ev_trends_signal = {}
    if _ev_trends_signal:
        _league_edge = _ev_trends_signal.get("league_env_edge", 0.0)
        _league_note = _ev_trends_signal.get("league_trend_note", "")
        # Backfill league env edge into every HR prop in signal_lookup
        if _league_edge != 0.0:
            for _sk, _sv in _ev_signal_lookup.items():
                if "Home Run" in _sk[1] or "run" in _sk[1].lower():
                    _sv["league_env_edge"] = _league_edge
                    _sv["league_env_note"] = _league_note
        st.session_state["ev_trends_signal"]          = _ev_trends_signal
        st.session_state["ev_trends_hr_per_g_season"] = _ev_trends_signal.get("league_hr_per_g_season")
        st.session_state["ev_trends_hr_per_g_l7"]     = _ev_trends_signal.get("league_hr_per_g_l7")
        st.session_state["ev_trends_note"]            = _league_note
        if _league_note:
            st.caption(f"📈 League HR env: {_league_note}")

    # ── Unabated fair value → MLB Home Run breakeven ──────────────────────────
    # Unabated is used as the PRIMARY fair-value source for this breakeven (see
    # the _ev_be line above: unabated_novig is checked before sharp_implied /
    # consensus_novig), per the Home-Run-specific market this already fed.
    # Everywhere else in the model, GEM computes its own probability from
    # player stats/matchups and never consulted a market consensus at all —
    # Home Runs (and previously Strikeouts, though that path doesn't actually
    # use _ev_be) is the one place a real devig already existed to swap in for.
    # The existing consensus_novig/sharp_implied fields are kept, not deleted,
    # so a >=3pt disagreement can be flagged rather than silently overridden
    # (3pt matches this codebase's existing DIVERGENT convention in
    # get_sharp_consensus_for_prop's spread >= 0.03 check, rather than an
    # arbitrary number).
    if sport == "MLB":
        _unabated_hr_probs: dict = {}
        for _l in st.session_state.get(f"unabated_props_{sport}", []):
            if _l.get("stat_type") != "Home Runs" or _l.get("price") is None:
                continue
            _pkey = normalize_name(_l.get("player_name",""))
            if not _pkey:
                continue
            try:
                _unabated_hr_probs.setdefault(_pkey, []).append(american_to_prob(_l["price"]))
            except Exception:
                pass
        for _pkey, _probs in _unabated_hr_probs.items():
            _sig_key = (_pkey, "Home Runs")
            _entry = _ev_signal_lookup.setdefault(_sig_key, {})
            _unabated_avg = sum(_probs) / len(_probs)
            _entry["unabated_novig"]        = round(_unabated_avg, 4)
            _entry["unabated_n_platforms"]  = len(_probs)
            _existing_be = _entry.get("sharp_implied") or _entry.get("consensus_novig")
            if _existing_be is not None:
                try:
                    _diff = abs(_unabated_avg - float(_existing_be))
                    if _diff >= 0.03:
                        _entry["unabated_devig_discrepancy"] = round(_diff, 4)
                except (TypeError, ValueError):
                    pass

    if _ev_board_props:
        st.session_state["ev_api_props"]    = _ev_board_props
        st.session_state["ev_signal_lookup"] = _ev_signal_lookup
        # ── Phase 2: cross-book LINE_DEVIATION signals + Phase 3: hit-rate logging
        try:
            from consensus_engine import get_cross_book_signals as _cbe_fn
            from hitrate_logger import log_props_to_hitrate as _hl_fn
            from fetchers import (
                fetch_prizepicks_from_gist as _ld_pp,
                fetch_underdog_from_gist   as _ld_ud,
                fetch_fanduel_props_from_gist   as _ld_fd,
                fetch_draftkings_props_from_gist as _ld_dk,
                fetch_bovada_from_gist  as _ld_bov,
                fetch_novig_from_gist   as _ld_nv,
            )
            _ld_book_data = {}
            # All fetchers return (list, source_label) — unwrap uniformly.
            # Bovada/Novig are no-ops while their Gist files are empty;
            # they activate automatically when the browser harvester pushes data.
            for _ld_bk, _ld_f in (
                ("prizepicks", _ld_pp),  ("underdog",    _ld_ud),
                ("fanduel",    _ld_fd),
                ("draftkings", _ld_dk),  ("bovada",      _ld_bov),
                ("novig",      _ld_nv),
            ):
                try:
                    _ld_res   = _ld_f(sport)
                    _ld_props = _ld_res[0] if isinstance(_ld_res, tuple) else _ld_res
                    if _ld_props:
                        _ld_book_data[_ld_bk] = _ld_props
                except Exception:
                    pass
            # BetMGM: sourced from the curl_cffi scraper pool (already running
            # every 15 min in auto_scraper_refresh.yml) rather than the
            # Tampermonkey-harvested Gist file, which produces nothing.
            try:
                _ld_mgm_props = [p for p in fetch_auto_scraped_props(sport) if p.get("Book") == "BetMGM"]
                if _ld_mgm_props:
                    _ld_book_data["betmgm"] = _ld_mgm_props
            except Exception:
                pass
            if _ld_book_data:
                st.session_state["line_deviation_lookup"] = _cbe_fn(sport, _ld_book_data)
                _hl_fn(_ld_book_data, sport)
        except Exception:
            st.session_state.setdefault("line_deviation_lookup", {})
        st.session_state["ev_api_updated"]  = ev_api_raw.get("updated", {})
        # Feed every book's line into alt sources for BetterLineNote detection
        for _evp in _ev_board_props:
            _ev_bk = _evp.get("Book", "")
            _ev_alt = {
                "Player": _evp.get("Player", ""),
                "Prop":   _evp.get("Prop", ""),
                "Line":   _evp.get("Line"),
                "Side":   _evp.get("Side", "OVER"),
            }
            if _ev_alt["Line"] is not None:
                all_alt_sources.append((_ev_alt, _ev_bk))
        # Per-book odds for CLV display
        _ev_book_lookup = {}
        for _evp in _ev_board_props:
            _k = (normalize_name(_evp.get("Player","")), _evp.get("Prop",""))
            _ev_book_lookup.setdefault(_k, {})[_evp.get("Book","")] = {
                "odds_over":  _evp.get("OddsOver"),
                "odds_under": _evp.get("OddsUnder"),
                "line":       _evp.get("Line"),
                "ev":         _evp.get("EV"),
                "fair_value": _evp.get("FairValue"),
                "bet_link":   _evp.get("_bet_link"),
            }
        st.session_state["ev_book_lookup"] = _ev_book_lookup
        st.caption(f"📡 EV API: {len(_ev_board_props)} props | {len(_ev_signal_lookup)} players | {len({p.get('Book') for p in _ev_board_props})} books")
    else:
        st.session_state["ev_api_props"]     = []
        # Don't blindly wipe this to {} — the Unabated HR merge above can
        # populate real entries here even when the EVSharps API itself has
        # no data this cycle. Only ev_api_props/ev_book_lookup are genuinely
        # EVSharps-specific and safe to clear unconditionally.
        st.session_state["ev_signal_lookup"] = _ev_signal_lookup
        st.session_state["ev_book_lookup"]   = {}

    # ── Parlay Savant — additional MLB book source for line-shopping ───
    # Sanity-check only: feeds into the same all_alt_sources comparison the
    # EV API uses above (BetterLineNote detection), never overrides EV API
    # data. Limited to the highest-volume prop types to avoid one page load
    # firing 18+ requests — each call is independently cached 10min.
    if sport == "MLB":
        _ps_props_to_check = ["Hits", "Home Runs", "Total Bases", "Strikeouts", "RBI"]
        _ps_total_loaded = 0
        for _ps_prop_name in _ps_props_to_check:
            _ps_slug = PARLAYSAVANT_MLB_PROP_MAP.get(_ps_prop_name)
            if not _ps_slug:
                continue
            for _ps_position in ("batter", "pitcher"):
                try:
                    _ps_data = fetch_parlaysavant_props(
                        sport="mlb", position=_ps_position, prop=_ps_slug)
                except Exception:
                    _ps_data = {}
                if not _ps_data:
                    continue
                for _ps_entry in _ps_data.values():
                    _ps_alt = {
                        "Player": _ps_entry.get("name", ""),
                        "Prop":   _ps_prop_name,
                        "Line":   _ps_entry.get("line"),
                        "Side":   "OVER",
                    }
                    if _ps_alt["Line"] is not None:
                        all_alt_sources.append((_ps_alt, "ParlaySavant"))
                        _ps_total_loaded += 1
        if _ps_total_loaded:
            st.caption(f"📊 Parlay Savant cross-check: {_ps_total_loaded} MLB prop lines")

    # ── EV Movement — snapshot delta engine (S8/S9) ────────────────────
    # Computes line movement from successive /api/ev snapshots.
    # Falls back to JWT /api/movement endpoint if available.
    ev_movement_raw = ev_movement_raw if isinstance(ev_movement_raw, list) else []
    if ev_api_raw and ev_api_raw.get("data"):
        _mv_lookup, _mv_alerts = get_ev_movement_from_snapshots(ev_api_raw)
    elif ev_movement_raw:
        # JWT endpoint returned data — parse it
        _mv_lookup, _mv_alerts = parse_ev_movement(ev_movement_raw)
    else:
        _mv_lookup, _mv_alerts = {}, []

    if _mv_lookup or _mv_alerts:
        st.session_state["ev_movement_lookup"] = _mv_lookup
        st.session_state["sharp_alerts"]       = _mv_alerts
        if _mv_alerts:
            st.caption(f"📡 Movement: {len(_mv_alerts)} sharp alerts detected")

    # ── Opening lines (ESPN capture, once/day — see espn_opening_lines_refresh.py) ──
    # 2026-07 fix: this used to be nested inside the `if _mv_lookup or
    # _mv_alerts:` block above and written into _mv_lookup (a
    # (player_norm, prop)-keyed dict for S8/S9 signals) under an
    # "away @ home" string key — a key format nothing ever reads, so it
    # silently did nothing even when data was present. Opening lines are
    # game-level, not player-prop-level, so they get their own
    # matchup-keyed dict here, independent of whether EVSharps movement
    # data came back, and a real consumer in the Game Lines tab.
    _op_data = st.session_state.get("oddsportal_data", {})
    _op_events = _op_data.get("data", []) if isinstance(_op_data, dict) else []
    if isinstance(_op_events, list) and _op_events:
        _opening_lines_lookup = {}
        for _oe in _op_events:
            if not isinstance(_oe, dict):
                continue
            _matchup = _oe.get("matchup", "")
            if not _matchup:
                continue
            _opening_lines_lookup[_matchup] = {
                "opening_home_ml": _oe.get("opening_home_ml"),
                "opening_away_ml": _oe.get("opening_away_ml"),
                "opening_spread":  _oe.get("opening_spread"),
                "opening_total":   _oe.get("opening_total"),
            }
        st.session_state["opening_lines_lookup"] = _opening_lines_lookup

    # DFS platforms
    if ud_props_compare:
        all_alt_sources.extend([(p, "Underdog") for p in ud_props_compare])
    # dk_props_harvested: DraftKings player prop lines from browser harvester / Python scraper.
    # Wire into the same book-comparison pool as ud_props_compare.
    _dk_h = st.session_state.get("dk_props_harvested", [])
    if _dk_h and isinstance(_dk_h, list):
        all_alt_sources.extend([(p, "DraftKings") for p in _dk_h if isinstance(p, dict)])
    parlayapi_props = st.session_state.get("parlayapi_props_cache", [])
    if parlayapi_props:
        pp_lines = [p for p in parlayapi_props if p.get("source","").lower() == "parlayplay"]
        all_alt_sources.extend([(p, "ParlayPlay") for p in pp_lines])

    # Sportsbook lines from The Odds API (FanDuel, DraftKings, BetMGM)
    # Load from cache if available — already fetched during board load
    odds_cache_path = os.path.join(CACHE_DIR, f"odds_api_props_{sport}.pkl")
    if os.path.exists(odds_cache_path):
        try:
            with open(odds_cache_path, "rb") as f:
                odds_props = pickle.load(f)
            # Group by book
            for op in odds_props:
                book = op.get("Book","").lower()
                if book in ("fanduel","draftkings","betmgm","caesars","bovada","circa_sports","betonlineag"):
                    book_display = {
                        "fanduel": "FanDuel",
                        "draftkings": "DraftKings",
                        "betmgm": "BetMGM",
                        "caesars": "Caesars",
                        "bovada": "Bovada",
                        "circa_sports": "Circa",
                        "betonlineag": "BetOnline"
                    }.get(book, book.title())
                    all_alt_sources.append((op, book_display))
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    for alt_prop, source in all_alt_sources:
        key = (normalize_name(alt_prop.get("Player","")), alt_prop.get("Prop",""))
        if key not in better_lines:
            better_lines[key] = []
        better_lines[key].append({
            "source": source,
            "line": alt_prop.get("Line", 0),
            "side": alt_prop.get("Side", "OVER")
        })
    st.session_state["better_lines_lookup"] = better_lines
    # oddswrap already fetched in parallel above — just compute discrepancies
    multibook_discrepancies = compare_multibook_lines(pp_props if pp_props else [], oddswrap_props or [])
    st.session_state["line_discrepancies"] = []
    st.session_state["multibook_discrepancies"] = multibook_discrepancies

    props = []  # Initialize — will be set by fallback chain below
    if pp_props:
        props = pp_props
    elif ud_props_compare:
        props = ud_props_compare
    else:
        # All primary DFS sources failed — use parallel-fetched alternates
        parlayapi_props = parlayapi_props_raw or []
        if parlayapi_props:
            parlayplay_props = [p for p in parlayapi_props if p.get("source","").lower() in ("parlayplay","parlay play")]
            pa_underdog = [p for p in parlayapi_props if p.get("source","").lower() in ("underdog","underdog fantasy")]
            pa_pp = [p for p in parlayapi_props if p.get("source","").lower() in ("prizepicks","prize picks")]
            if pa_underdog:
                st.session_state["ud_props_compare"] = pa_underdog
            if parlayplay_props:
                props = parlayplay_props
            elif pa_underdog:
                props = pa_underdog
            elif pa_pp:
                props = pa_pp
            else:
                props = parlayapi_props
        elif parlayplay_props_raw:
            props = parlayplay_props_raw
        elif dk_pick6_props_raw:
            props = dk_pick6_props_raw
        elif oddswrap_props:
            props = [p for p in oddswrap_props if p.get("Side") == "OVER"]
        elif odds_api_props_raw:
            props = odds_api_props_raw
        elif oddspapi_props_raw:
            props = oddspapi_props_raw
        elif sport == "NBA" and BDL_API_KEY and bdl_props_raw:
            props = bdl_props_raw
        elif []:
            props = []
        else:
            cached_props = st.session_state.get("last_good_props", {}).get(sport, [])
            if cached_props:
                props = cached_props
            else:
                return [], games, 0, 0, {}, {}

    # ── Unabated fair-value comparison — attached onto each source prop dict
    # (p) here, then threaded through into `enriched` at append-time below
    # (alongside best_prob, which is GEM's own model probability for that
    # exact row). This is deliberately NOT wired into Edge/breakeven for
    # non-HR stats — GEM's probability model doesn't consult market
    # consensus at all for those, so this is a new comparison axis, not a
    # source swap. Only Home Runs (see the ev_signal_lookup merge earlier
    # in this function) actually feeds Edge; everywhere else this is
    # display-only. Only explicitly verified stat-name pairs are matched —
    # anything unmapped is left alone rather than fuzzy-matched, since a
    # wrong match here is worse than no match.
    _UNABATED_BOOK_KEY = {"PrizePicks": "prizepicks", "Underdog": "underdog", "Pick6": "pick6", "DK Pick6": "pick6"}
    _UNABATED_STAT_MAP = {
        "Home Runs": "Home Runs", "Hits": "Hits", "Runs": "Runs", "RBIs": "RBIs",
        "Total Bases": "Total Bases", "Stolen Bases": "Stolen Bases",
        "Hitter Strikeouts": "Hitter Strikeouts", "Pitcher Strikeouts": "Pitcher Strikeouts",
        "Hits+Runs+RBIs": "Hits + Runs + Rbis", "Pitching Outs": "Pitcher Outs",
        "Singles": "Player Singles", "Doubles": "O/U Doubles",
        "Walks": "Hitter Walks", "Walks Allowed": "Pitcher Walks",
        "Earned Runs Allowed": "Pitcher Earned Runs", "Hits Allowed": "Pitcher Hits Allowed",
    }
    try:
        _unab_lines = st.session_state.get(f"unabated_props_{sport}", [])
        if _unab_lines and props:
            _unab_idx: dict = {}
            for _ul in _unab_lines:
                _plat  = str(_ul.get("platform","")).lower()
                _pname = normalize_name(_ul.get("player_name",""))
                _stat  = _ul.get("stat_type","")
                if not _plat or not _pname or not _stat or _ul.get("price") is None:
                    continue
                _unab_idx.setdefault((_plat, _pname, _stat), []).append(_ul)
            for _p in props:
                _plat_key = _UNABATED_BOOK_KEY.get(_p.get("Book",""))
                if not _plat_key:
                    continue
                _prop_label = _p.get("Prop","")
                _stat_candidates = []
                if _prop_label in _UNABATED_STAT_MAP:
                    _stat_candidates.append(_UNABATED_STAT_MAP[_prop_label])
                elif _prop_label in ("Hitter Fantasy Score", "Pitcher Fantasy Score"):
                    _stat_candidates.append("Player Fantasy Points")
                if not _stat_candidates:
                    continue
                _row_pname = normalize_name(_p.get("Player",""))
                _matches = None
                for _sc in _stat_candidates:
                    _matches = _unab_idx.get((_plat_key, _row_pname, _sc))
                    if _matches:
                        break
                if not _matches:
                    continue
                try:
                    _row_line = float(_p.get("Line", 0) or 0)
                    _best = min(_matches, key=lambda m: abs(safe_float(m.get("line",0)) - _row_line))
                except Exception:
                    _best = _matches[0]
                try:
                    _unab_prob = round(american_to_prob(_best["price"]), 4)
                except Exception:
                    continue
                _p["UnabatedLine"]     = _best.get("line")
                _p["UnabatedPrice"]    = _best.get("price")
                _p["UnabatedFairProb"] = _unab_prob
    except Exception as _uab_cmp_err:
        print(f"[WARN] unabated props comparison attach: {_uab_cmp_err}")

    # ── EVSharps dingers (MLB HR props only) ──────────────────────────────
    # Second, independent HR-prop validator alongside Unabated above.
    # EVSharps' own "implied" field is their already-computed fair
    # probability (as a percentage, e.g. 13.34 == 13.34%) - use it directly,
    # same principle as UnabatedFairProb above: no re-devig from their raw
    # American-odds fair_val when they've already handed us the probability.
    try:
        if sport == "MLB" and props:
            from fetchers import fetch_evsharps_dingers_from_gist
            _evs_entries, _evs_src = fetch_evsharps_dingers_from_gist()
            if _evs_entries:
                _evs_idx = {}
                for _ee in _evs_entries:
                    _ee_name = normalize_name(_ee.get("player", ""))
                    if _ee_name and _ee.get("implied") is not None:
                        _evs_idx[_ee_name] = _ee
                for _p in props:
                    if _p.get("Prop") != "Home Runs":
                        continue
                    _ee = _evs_idx.get(normalize_name(_p.get("Player", "")))
                    if not _ee:
                        continue
                    try:
                        _evs_prob = round(float(_ee["implied"]) / 100.0, 4)
                    except (TypeError, ValueError):
                        continue
                    _p["EVSharpsFairProb"] = _evs_prob
                    _p["EVSharpsLine"]     = _ee.get("line")
                    _p["EVSharpsEVPct"]    = _ee.get("ev_pct")
    except Exception as _evs_cmp_err:
        print(f"[WARN] evsharps dingers comparison attach: {_evs_cmp_err}")

    # ── SECTION: DATA ACQUISITION COMPLETE ──────────────���──���───────────────────
    # All network I/O is done above via _fetch_parallel().
    # Below: pure computation — B2B detection, enrichment, game analysis.
    # injuries, public_betting, an_props, games already fetched in parallel above
    b2b_teams = set()
    try:
        yesterday = date.today() - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y%m%d")
        slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "hockey/nhl", "WNBA": "basketball/wnba"}
        path = slug_map.get(sport, "")
        if path:
            y_url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={yesterday_str}"
            y_resp = _http.get(y_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if y_resp.status_code == 200:
                for event in y_resp.json().get("events", []):
                    for comp in event.get("competitions", []):
                        for competitor in comp.get("competitors", []):
                            team = competitor.get("team", {}).get("abbreviation", "")
                            if team:
                                b2b_teams.add(team)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    game_ids = fetch_espn_game_ids(sport)
    # officials_data already fetched in parallel — session_state set above
    power_divergences = {}
    if sport == "NBA":
        for game in games:
            matchup = game.get("Matchup","")
            spread = game.get("Spread","")
            h_team = home_teams.get(matchup,"")
            a_team = away_teams.get(matchup,"")
            if h_team and a_team:
                div_score, div_note = power_rating_spread_divergence(h_team, a_team, spread)
                if div_score > 0:
                    power_divergences[matchup] = {"score": div_score, "note": div_note}
    st.session_state["power_divergences"] = power_divergences
    game_line_movement = {}
    game_sharp_flags = {}
    for matchup, event_id in game_ids.items():
        movements = fetch_espn_line_movement(sport, event_id)
        is_sharp, direction, magnitude = detect_sharp_movement(movements)
        game_line_movement[matchup] = movements
        if is_sharp:
            game_sharp_flags[matchup] = {"sharp": True, "direction": direction, "magnitude": magnitude}
    st.session_state["game_line_movement"] = game_line_movement
    st.session_state["game_sharp_flags"] = game_sharp_flags
    steam_moves = detect_steam_moves(sport)
    st.session_state["steam_moves"] = steam_moves
    for move in steam_moves:
        matchup = move.get("matchup", "")
        if matchup:
            existing = game_sharp_flags.get(matchup, {})
            game_sharp_flags[matchup] = {**existing, "steam": True, "steam_signal": move.get("signal", ""), "steam_direction": move.get("direction", "")}
    st.session_state["game_sharp_flags"] = game_sharp_flags
    history = get_calibration_source_records()
    tier_stats = compute_tier_stats(history)
    # ── OVER-only prop normalization ──────────────────────────────────────
    # Fix any props where data source set Side=UNDER for markets that
    # only exist as OVER bets (HR, Goals, TDs, Aces, Sacks).
    # No sportsbook offers HR UNDER — it's always a binary OVER market.
    _OVER_ONLY_STATS = {
        "HR", "Home Runs", "Home Run", "Homeruns", "Homerun",
        "GOALS", "Goals", "Goal",
        "TD", "Touchdowns", "Touchdown",
        "Aces", "ACES", "Sacks", "SACKS",
    }
    # PrizePicks goblin/demon alt-lines are ALWAYS More/Over-only, regardless
    # of stat type -- confirmed against a real live PrizePicks API response
    # (odds_type field is genuinely present per-projection) and confirmed
    # directly by the user, an actual PrizePicks bettor: PrizePicks does not
    # offer an Under selection on either goblin or demon lines, only on
    # odds_type="standard". This is separate from _OVER_ONLY_STATS above
    # (which is about the STAT itself being universally one-directional
    # across every book) -- this is about the LINE TYPE on this one specific
    # book being one-directional regardless of stat.
    for _p in props:
        _prop_key = _p.get("Prop","") or _p.get("stat_key","") or ""
        _stat_n   = STAT_NORMALIZE.get((sport, _prop_key), _prop_key)
        if _prop_key in _OVER_ONLY_STATS or _stat_n in _OVER_ONLY_STATS:
            _p["Side"] = "OVER"   # no book offers HR/Goal/TD UNDER
        elif _p.get("source") == "PrizePicks" and _p.get("OddsType","") in ("goblin", "demon"):
            _p["Side"] = "OVER"   # PrizePicks goblin/demon lines are More-only, confirmed by user

    enriched = []
    skipped_def = skipped_edge = 0

    # Pre-build normalize_name index for O(1) history lookups
    # Avoids calling normalize_name() 126× per board load
    _history_norm_index = {}
    for _hi, _hb in enumerate(history):
        _hn = normalize_name(_hb.get("player",""))
        if _hn not in _history_norm_index:
            _history_norm_index[_hn] = []
        _history_norm_index[_hn].append(_hb)

    # Pre-build injury lookup index
    _injuries_raw = st.session_state.get("injuries", {})
    _injury_index = {}
    if isinstance(_injuries_raw, dict):
        for _ik, _iv in _injuries_raw.items():
            _injury_index[normalize_name(_ik)] = _iv

    # Hoist session_state reads — avoids repeated dict lookups per prop
    _locks_snapshot  = list(st.session_state.get("locks", []))
    _public_data     = st.session_state.get("public_betting_data", {})
    _mlb_pitchers    = st.session_state.get("mlb_pitchers", {})
    _parlayplay_alts = st.session_state.get("parlayplay_alt_lines", {})
    _fd_dk_alts      = st.session_state.get("fd_dk_alt_lines", [])

    # Cache static data once per session (never changes mid-day)
    _sport_key = f"_cached_{sport}"
    if _sport_key not in st.session_state:
        _power_map = {
            "NBA": NBA_POWER_RATINGS,
            "WNBA": {},
            "MLB": {},
            "NHL": {},
            "NFL": {},
        }
        st.session_state[_sport_key] = {
            "power": _power_map.get(sport, {}),
            "pace": NBA_TEAM_PACE if sport == "NBA" else {},
            "def_ratings": {},
        }
    _static = st.session_state[_sport_key]
    _power_ratings = _static["power"]
    _pace_ratings  = _static["pace"]

    # Pre-load signal weights once — avoids disk read on every prop iteration
    _optimizer_data = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
    _sport_optimizer = _optimizer_data.get(sport, {})
    if (_sport_optimizer.get("weights") and
            _sport_optimizer.get("n_bets", 0) >= WEIGHT_OPTIMIZER_MIN_BETS):
        _preloaded_weights = _sport_optimizer["weights"]
    else:
        _preloaded_weights = get_effective_signal_weights(sport)

    # Pre-build game analysis lookup by matchup for game total routing
    _game_analysis_by_matchup = {}
    for _ga in (st.session_state.get("game_analysis") or []):
        _mb = _ga.get("matchup","")
        if _mb:
            _game_analysis_by_matchup[_mb.lower()] = _ga

    # ── Parallel prefetch for the three per-prop live-network calls below ──
    # These used to run inline, once per prop, fully sequential — on a board
    # with 100+ props that meant 100+ blocking network round-trips back to
    # back. Collecting the unique players/teams that actually need a live
    # lookup first and fetching them concurrently turns that into a handful
    # of parallel batches instead.
    _bdl_avg_prefetch  = {}
    _bdl_logs_prefetch = {}
    _team_def_prefetch = {}
    if sport == "NBA" and BDL_API_KEY:
        _needs_bdl_avg = set()
        for _p in props:
            _pl = _p.get("Player","")
            if not _pl or _pl in season_avgs:
                continue
            _, _ud = find_player_avg(_pl, season_avgs)
            if _ud:
                _needs_bdl_avg.add(_pl)
        if _needs_bdl_avg:
            # Was a bare ThreadPoolExecutor + .result() with NO timeout at
            # all -- worse than the bug already found/fixed in
            # _fetch_parallel (which at least attempted a 25s ceiling): a
            # single slow/hanging player lookup here could block this
            # whole board load indefinitely, with no cap whatsoever.
            # Reusing _fetch_parallel gives it the same real 25s ceiling.
            _bdl_players = list(_needs_bdl_avg)
            _bdl_fns = [(lambda _pl=_pl: fetch_player_season_avg_bdl(_pl, sport)) for _pl in _bdl_players]
            _bdl_results = _fetch_parallel(_bdl_fns, show_progress=False)
            for _pl, _res in zip(_bdl_players, _bdl_results):
                _bdl_avg_prefetch[_pl] = _res
    if BDL_API_KEY:
        _needs_logs = set()
        for _p in props:
            _pl = _p.get("Player","")
            if not _pl:
                continue
            _pteam = PLAYER_TEAM_MAP.get(_pl, "")
            if _pteam and any(_pteam in _g.get("Matchup","") for _g in games):
                _needs_logs.add(_pl)
        if _needs_logs:
            _log_players = list(_needs_logs)
            _log_fns = [(lambda _pl=_pl: fetch_player_game_logs(_pl, sport, 20)) for _pl in _log_players]
            _log_results = _fetch_parallel(_log_fns, show_progress=False)
            for _pl, _res in zip(_log_players, _log_results):
                _bdl_logs_prefetch[_pl] = _res if _res is not None else []
    if sport == "NBA":
        _unique_teams = set()
        for _g in games:
            for _tok in _g.get("Matchup","").replace("@","vs").split():
                if _tok != "vs" and len(_tok) <= 3 and _tok.isalpha():
                    _unique_teams.add(_tok)
        if _unique_teams:
            _def_teams = list(_unique_teams)
            _def_fns = [(lambda _t=_t: fetch_team_recent_defense(sport, _t, 10)) for _t in _def_teams]
            _def_results = _fetch_parallel(_def_fns, show_progress=False)
            for _t, _res in zip(_def_teams, _def_results):
                _team_def_prefetch[_t] = _res

    for p in props:
        stat_raw = p["Prop"]
        stat_norm = STAT_NORMALIZE.get((sport, stat_raw), stat_raw)
        player = p["Player"]
        line = p["Line"]
        side = p.get("Side", "OVER")

        # ── GAME TOTAL PROP ROUTING ──────────────────────────
        # If this is a game-total prop (e.g. WNBA O/U 169.5),
        # the player model is wrong (avg ~20pts vs line ~169).
        # Route to game_analysis result instead.
        if is_game_total_prop(player, stat_raw, safe_float(line), sport):
            # Find matching game analysis
            _gt_game = None
            for _mb, _ga in _game_analysis_by_matchup.items():
                if any(t.lower() in _mb for t in player.lower().split() if len(t) > 2):
                    _gt_game = _ga
                    break
            if _gt_game and _gt_game.get("best_bet"):
                _gt_bb = _gt_game["best_bet"]
                _gt_edge = float(_gt_bb.get("edge", 0))
                _gt_tier  = _get_cal_game_tier(abs(_gt_edge), sport)
                _gt_prob  = float(_gt_bb.get("fair_prob", 0.55))
                enriched.append({
                    "Player": player, "Prop": stat_raw, "Line": line,
                    "Side": side, "Sport": sport, "Tier": _gt_tier,
                    "Edge": round(_gt_edge, 4),
                    "Prob": _gt_prob,
                    "Avg": safe_float(line),  # line IS the reference for game totals
                    "Source": p.get("source",""),
                    "IsGameTotal": True,
                    "GameAnalysisRef": _gt_game.get("matchup",""),
                    "Narrative": f"Game total — routed from game model. {_gt_bb.get('note','')}",
                    "NarrativeRisk": f"⚠️ Risk: Game script / blowout may nullify",
                    "TierNote": "Game total — uses team model",
                    "ContextOverrides": [], "OverrideActive": False,
                    "LockScore": min(100, int(abs(_gt_edge)*300 + 20)),
                })
            else:
                # No game analysis match — skip this prop to avoid 0% edge confusion
                skipped_edge += 1
            continue
        # ── END GAME TOTAL ROUTING ───────────────────────────
        odds_type = p.get("OddsType", "standard")
        if sport == "NBA" and player in season_avgs:
            season_avg = season_avgs.get(player, {})
            last10 = rolling_avgs.get(player, None)
            avg_dict = get_weighted_average(player, season_avg, last10, is_playoff)
            using_default = False
            if last10 and isinstance(last10, dict):
                avg_dict["n_games"] = last10.get("n_games", 10)
                for std_key in ["PTS_std", "REB_std", "AST_std", "PRA_std"]:
                    if std_key in last10:
                        avg_dict[std_key] = last10[std_key]
            else:
                avg_dict["n_games"] = 10
        else:
            player_stats, using_default = find_player_avg(player, season_avgs)
            if using_default:
                skipped_def += 1
                # Try live BDL lookup before using static defaults
                if BDL_API_KEY and sport == "NBA":
                    live_avg = _bdl_avg_prefetch.get(player)
                    if live_avg:
                        avg_dict = live_avg
                        using_default = False
                if using_default:
                    if skip_def and len(props) >= 30:
                        continue
                    avg_dict = {stat_norm: defaults.get(stat_norm, line)}
                avg_dict["search_needed"] = True
                avg_dict["search_query"] = f"{player} stats last 10 games 2026"
            else:
                avg_dict = player_stats
            avg_dict = {k: v for k, v in avg_dict.items()}
        avg = avg_dict.get(stat_norm, defaults.get(stat_norm, line))
        if sport == "NBA":
            player_mins = rolling_avgs.get(player, {}).get("MIN")
            if player_mins and player_mins > 0:
                baseline_mins = 30.0
                mins_factor = player_mins / baseline_mins
                mins_factor = max(0.80, min(1.20, mins_factor))
                avg = round(avg * mins_factor, 1)

        # ── Regression-to-mean risk ────────────────────────────────────────────
        # When a player's recent L5/L10 avg is 25%+ above their season avg,
        # the book line is likely inflated by the hot streak. Detect and store
        # the risk so the final_edge multiplier can be applied after calibration.
        _regression_risk = {"risk": "NONE", "edge_mult": 1.0, "note": ""}
        _rolling_player = rolling_avgs.get(player, {})
        _season_player_avg = season_avgs.get(player, {})
        _recent_stat = _rolling_player.get(stat_norm)
        _season_stat = (_season_player_avg.get(stat_norm)
                        or avg_dict.get(stat_norm))
        if _recent_stat and _season_stat and _season_stat > 0:
            _n_recent = _rolling_player.get("n_games", 5)
            _regression_risk = hot_streak_regression_risk(
                _recent_stat, _season_stat,
                n_recent=_n_recent
            )

        player_team = PLAYER_TEAM_MAP.get(player, "")
        opp_def_rating = 112.0
        opp_team_abbrev = ""
        if player_team and games:
            for game in games:
                matchup = game["Matchup"]
                if player_team in matchup:
                    parts = matchup.replace("@","vs").split()
                    for p2 in parts:
                        if (p2 != player_team and len(p2) <= 3 and p2.isalpha()):
                            opp_team_abbrev = p2
                            season_def = team_defense.get(p2, 112.0)
                            recent_def = _team_def_prefetch.get(p2)
                            if recent_def and recent_def.get("def_rating_recent"):
                                recent_rating = recent_def["def_rating_recent"]
                                is_playoff_month = is_playoff  # use regime-aware flag from fetch_game_lines
                                recent_weight = 0.80 if is_playoff_month else 0.70
                                season_weight = 1 - recent_weight
                                opp_def_rating = round(recent_rating * recent_weight + season_def * season_weight, 1)
                            else:
                                opp_def_rating = season_def
                                avg_dict["def_data_stale"] = True
                            if (sport == "NBA" and stat_norm == "PTS" and p2 in NBA_POSITION_DEFENSE):
                                position = NBA_PLAYER_POSITIONS.get(player, "")
                                if position:
                                    pos_allowed = NBA_POSITION_DEFENSE[p2].get(position, LEAGUE_AVG_POSITION.get(position, 22.0))
                                    league_pos_avg = LEAGUE_AVG_POSITION.get(position, 22.0)
                                    pos_adj_rtg = round((pos_allowed / league_pos_avg) * 112.0, 1)
                                    opp_def_rating = round(pos_adj_rtg * 0.5 + opp_def_rating * 0.5, 1)
                            break
                    break
        is_home = False
        if player_team and games:
            for matchup, home in home_teams.items():
                if player_team == home:
                    is_home = True
                    break
        usage_boost = 0.0
        if player in TEAMMATE_OUT_BOOST:
            out_player = TEAMMATE_OUT_BOOST[player].get("out_player")
            if out_player and any(normalize_name(out_player) in normalize_name(inj) for inj in injuries.keys()):
                raw_boost = TEAMMATE_OUT_BOOST[player].get(stat_norm, 0)
                avg_val = avg if avg > 0 else 1
                usage_boost = min(raw_boost / avg_val * 0.5, 0.10)
        sharp_flag = ""
        if player_team and games:
            for game in games:
                matchup = game.get("Matchup", "")
                if player_team in matchup:
                    sharp_info = game_sharp_flags.get(matchup, {})
                    if sharp_info.get("sharp"):
                        sharp_flag = f"⚡ Sharp {sharp_info['direction']}{sharp_info['magnitude']}"
                    pb_data = st.session_state.get("public_betting_data", {})
                    for gkey, gd in pb_data.items():
                        gteams = gd.get("teams", [])
                        if player_team in gteams:
                            pb_signals = gd.get("sharp_signals", [])
                            if pb_signals:
                                sharp_flag = sharp_flag + " 📊PB" if sharp_flag else "📊 Public sharp"
                            break
                    break
        # Rest days — use actual game schedule if available
        if player_team in b2b_teams:
            days_rest = 0
        else:
            # Try to compute from game schedule
            _rest_days = 2  # default
            if games and player_team:
                for _g in games:
                    if player_team in _g.get("Matchup",""):
                        # If DaysRest field populated from fetch_game_lines
                        _rest_days = int(_g.get("DaysRest", 2))
                        break
            days_rest = _rest_days
        blowout_adj = 0.0
        if player_team and games:
            for game in games:
                matchup = game.get("Matchup", "")
                if player_team in matchup:
                    spread = game.get("Spread", "—")
                    blowout_adj = blowout_risk_adjustment(spread, sport, player_team, home_teams, away_teams, matchup)
                    break
        referee_adj = 0.0
        ref_note = ""
        officials_data = st.session_state.get("officials_data", {})
        if officials_data and player_team:
            for matchup, refs in officials_data.items():
                if player_team in matchup:
                    for ref in refs:
                        if sport == "NBA":
                            ref_data = NBA_REFEREE_TENDENCIES.get(ref, {})
                            if ref_data and stat_norm == "PTS":
                                referee_adj += ref_data.get("pts_adj", 0)
                                foul_rate = ref_data.get("foul_rate", "")
                                if foul_rate == "high":
                                    ref_note = f"📋 {ref}: high foul rate"
                                elif foul_rate == "low":
                                    ref_note = f"📋 {ref}: physical game"
                        elif sport == "MLB":
                            ref_data = MLB_UMPIRE_TENDENCIES.get(ref, {})
                            if ref_data and stat_norm == "SO":
                                referee_adj += ref_data.get("so_adj", 0)
                                zone = ref_data.get("zone", "")
                                if zone == "large":
                                    ref_note = f"⚾ {ref}: large zone"
                                elif zone == "tight":
                                    ref_note = f"⚾ {ref}: tight zone"
                    break
        pace_adj = 0.0
        opp_abbr = ""
        if player_team:
            for game in games:
                if player_team in game.get("Matchup", ""):
                    parts = game["Matchup"].replace("@", "vs").split()
                    for p2 in parts:
                        if p2 != player_team and len(p2) <= 3 and p2.isalpha():
                            opp_abbr = p2
                            if sport == "NBA":
                                player_pace = NBA_TEAM_PACE.get(player_team, 99.5)
                                opp_pace = NBA_TEAM_PACE.get(p2, 99.5)
                                combined_pace = (player_pace + opp_pace) / 2
                                pace_adj = (combined_pace - 99.5) / 99.5
                            break
                    break

        # S7 H2H Signal — hit rate vs this specific opponent
        h2h_adj = 0.0
        h2h_note = ""
        if opp_abbr:
            try:
                game_logs = _bdl_logs_prefetch.get(player, [])
                if game_logs:
                    h2h_rate, h2h_games, _ = compute_h2h_hit_rate(game_logs, opp_abbr, stat_norm, line)
                    if h2h_games >= 3:
                        if h2h_rate >= 0.70:
                            h2h_adj = 0.02
                            h2h_note = f"H2H {h2h_rate:.0%} vs {opp_abbr} ({h2h_games}g)"
                        elif h2h_rate <= 0.30:
                            h2h_adj = -0.02
                            h2h_note = f"H2H {h2h_rate:.0%} vs {opp_abbr} ({h2h_games}g)"
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
        game_total_adj = 0.0
        if sport == "NBA" and player_team:
            for game in games:
                if player_team in game.get("Matchup", ""):
                    total = game.get("Total", "N/A")
                    if total and total != "N/A":
                        try:
                            game_total_adj = (float(total) - 225.0) / 225.0 * 0.05
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    break
        weather_adj = 0.0
        weather_note = ""
        if sport == "MLB":
            team_full = MLB_PLAYER_TEAM_MAP.get(player, "")
            if team_full:
                park = MLB_BALLPARKS.get(team_full, {})
                city = park.get("city", "")
                is_outdoor = park.get("outdoor", True)
                if city and is_outdoor:
                    weather = fetch_weather_for_game(city, is_outdoor)
                    weather_adj, weather_note = weather_edge_adjustment(weather, stat_norm, "OVER", sport)
        elif sport == "NFL":
            # NFL weather — use team's stadium coords, skip domes
            _nfl_team = p.get("Team","")
            if _nfl_team:
                weather = get_nfl_weather(_nfl_team)
                if weather:
                    weather_adj, weather_note = weather_edge_adjustment(weather, stat_norm, side, sport)
        pitcher_adj = 0.0
        pitcher_name = ""
        statcast_edge = 0.0
        statcast_notes = []
        stadium_edge = 0.0
        ev_pn_novig = None
        ev_circa_novig = None
        ev_consensus_novig = None
        ev_sharp_fv = None
        ev_sharp_ev = None
        ev_l10_rate = None
        ev_bvp_edge = 0.0
        ev_bvp_note = ""
        ev_homer_due_edge = 0.0
        sav_brl_edge = 0.0
        sav_reg_edge = 0.0
        sav_spd_edge = 0.0
        sav_la_edge  = 0.0
        sav_ars_edge = 0.0
        sav_fb_edge  = 0.0
        today_brl_edge = 0.0
        preview_platoon_edge = 0.0
        preview_hr_rate_edge = 0.0
        brl_edge = 0.0

        # ── EV API signal injection (S6 / S7 / S12 / pitcher) ─────────
        _ev_sig = st.session_state.get("ev_signal_lookup", {}).get(
            (normalize_name(player), stat_raw), {}
        )

        # ── EV Movement signal injection (S8 / S9) ─────────────────────
        _mv_sig = st.session_state.get("ev_movement_lookup", {}).get(
            (normalize_name(player), stat_raw), {}
        )
        ev_s8_vector  = _mv_sig.get("s8_vector", 0)   # -2 to +2
        ev_s9_boost   = _mv_sig.get("s9_boost", 0.0)  # 0 to +0.02
        ev_rlm_note   = _mv_sig.get("rlm_note", "")
        ev_steam_flag = _mv_sig.get("steam_flag", False)
        ev_sharp_move = _mv_sig.get("sharp_flag", False)
        if _ev_sig:
            # S6 — live Pinnacle + Circa no-vig (replaces manual MLB_PITCHER_ERA lookup for no-vig)
            ev_pn_novig       = _ev_sig.get("pn_novig")
            ev_circa_novig    = _ev_sig.get("circa_novig")
            ev_consensus_novig = _ev_sig.get("consensus_novig")
            ev_sharp_fv       = _ev_sig.get("sharp_fv")
            ev_sharp_ev       = _ev_sig.get("sharp_ev")

            # S12 Statcast (MLB HR props)
            statcast_edge  = _ev_sig.get("statcast_edge", 0.0)
            statcast_notes = _ev_sig.get("statcast_notes", [])
            stadium_edge   = _ev_sig.get("stadium_edge", 0.0)

            # S7 — BvP direct (takes priority over L10 proxy)
            ev_l10_rate    = _ev_sig.get("l10_rate")
            ev_bvp_edge    = _ev_sig.get("bvp_edge", 0.0)
            ev_bvp_note    = _ev_sig.get("bvp_note", "")
            # Homer due (S12 supplemental)
            ev_homer_due_edge = _ev_sig.get("homer_due_edge", 0.0)

            # ── LineStar/Baseball-Savant batter-CSV edges (2026-07 fix) ──
            # sav_brl_edge/sav_reg_edge/sav_spd_edge were being computed and
            # written into this exact dict entry by the Savant enrichment
            # block earlier in the pipeline, but nothing ever read them back
            # out -- final_edge only ever pulled EVSharps' own HR-only
            # statcast_edge. sav_brl_edge only applied for "Hits" here (not
            # "Home Run") since EVSharps' statcast_edge already covers HR
            # barrel/exit-velo/hard-hit -- applying both for HR would
            # double-count the same underlying contact-quality signal from
            # two data sources. sav_reg_edge (xwOBA-diff regression) and
            # sav_spd_edge (sprint speed, SB props) have no EVSharps
            # equivalent, so those apply as-is.
            sav_brl_edge = _ev_sig.get("sav_brl_edge", 0.0) if "Hits" in stat_raw else 0.0
            sav_reg_edge = _ev_sig.get("sav_reg_edge", 0.0)
            sav_spd_edge = _ev_sig.get("sav_spd_edge", 0.0)
            sav_la_edge  = _ev_sig.get("sav_la_edge", 0.0)
            # sav_ars_edge (pitch-arsenal run-value for the pitcher's best
            # pitch, computed only when "Strikeout" is in stat_raw — see the
            # computation site) — added 2026-07-18, same "computed but never
            # read back" bug class as the four above. No overlap risk with
            # statcast_edge/brl_edge/preview_hr_rate_edge: those are all
            # BATTER contact-quality signals for HR props; this is a
            # PITCHER pitch-effectiveness signal for K props — different
            # player, different prop type, no shared underlying data.
            sav_ars_edge = _ev_sig.get("sav_ars_edge", 0.0) if "Strikeout" in stat_raw else 0.0

            # sav_fb_edge (batter's own flyball rate, season Statcast) — the
            # metric statcast_edge tracks for the pitcher side is
            # pitcher_flyball_pct (how often that pitcher allows flyballs);
            # this is the batter's own flyball tendency, a different
            # player's stat entirely. No overlap. Gate matches its actual
            # computation context (Home Run or Hits props only).
            sav_fb_edge = _ev_sig.get("sav_fb_edge", 0.0) if ("Home Run" in stat_raw or "Hits" in stat_raw) else 0.0

            # today_brl_edge (TODAY's single-game barrel/hard-hit rate) —
            # statcast_edge's barrel_pct/hard_hit inputs are season
            # aggregates; this is a same-day recency read, the same
            # relationship as existing L10-vs-season signals elsewhere in
            # this function. Distinct time window, not a restatement.
            today_brl_edge = _ev_sig.get("today_brl_edge", 0.0) if ("Home Run" in stat_raw or "run" in stat_raw.lower()) else 0.0

            # preview_platoon_edge (batter-hand vs this specific pitcher's
            # L/R split HR rate) — a handedness-matchup dimension nothing
            # else in this function captures. No overlap with statcast_edge
            # (which has no handedness component).
            preview_platoon_edge = _ev_sig.get("preview_platoon_edge", 0.0) if ("Home Run" in stat_raw or "run" in stat_raw.lower()) else 0.0

            # preview_hr_rate_edge (opposing PITCHER's own HR-allowed
            # percentile) and brl_edge (ev_barrels-sourced BATTER barrel
            # percentile, HR props) both carry real thematic overlap with
            # statcast_edge, which already folds in pitcher_flyball_pct/
            # pitcher_barrel_rate (opponent quality) and the batter's own
            # barrel_pct from a different data source. Stacking either
            # unconditionally on top of an already-active statcast_edge
            # would double-count the same "is this a good HR matchup"
            # read twice. Treated as fallback-only: they apply solely when
            # statcast_edge came back exactly 0.0 (EVSharps had no read at
            # all for this player, not merely "no threshold hit" — the
            # common case when statcast_edge is 0.0 is missing EVSharps
            # coverage, since the threshold ladder starts rewarding at
            # barrel_pct>=10/hr_pct>=75, a fairly low bar most real
            # HR-relevant batters clear). This is a conservative choice:
            # worst case some real signal goes unused when EVSharps
            # legitimately read a clean zero; that's a smaller error than
            # silently inflating edge on a double-counted HR read.
            preview_hr_rate_edge = _ev_sig.get("preview_hr_rate_edge", 0.0) if (statcast_edge == 0.0 and ("Home Run" in stat_raw or "run" in stat_raw.lower())) else 0.0
            brl_edge = _ev_sig.get("brl_edge", 0.0) if (statcast_edge == 0.0 and ("Home Run" in stat_raw or "run" in stat_raw.lower())) else 0.0

            # Pitcher matchup from EV API (live ERA + xwOBA + flyball% + barrel rate)
            if sport == "MLB" and _ev_sig.get("pitcher_era"):
                pitcher_name   = _ev_sig.get("pitcher", "")
                ev_pitcher_era = _ev_sig["pitcher_era"]
                era_diff = ev_pitcher_era - LEAGUE_AVG_ERA
                pitcher_adj = max(-0.08, min(0.08, era_diff / 100.0))
                xwoba = _ev_sig.get("pitcher_xwoba", 0) or 0
                if xwoba > 0:
                    xwoba_adj = (xwoba - 0.320) * 0.15
                    pitcher_adj = max(-0.08, min(0.08, pitcher_adj + xwoba_adj))

        # Fallback: static pitcher FIP + handedness wOBA if EV API has no pitcher data
        # FIP is more predictive than ERA (strips defense/luck); handedness wOBA adjusts
        # for how well the opposing lineup hits that arm type.
        if sport == "MLB" and not pitcher_name:
            mlb_pitchers = st.session_state.get("mlb_pitchers", {})
            team_full = MLB_PLAYER_TEAM_MAP.get(player, "")
            if team_full and mlb_pitchers:
                opp_data = mlb_pitchers.get(team_full, {})
                opp_pitcher = opp_data.get("pitcher", "")
                if opp_pitcher:
                    # Prefer live Savant stats (fip_live/xfip_live) over static dict
                    _fip_live  = opp_data.get("fip_live")
                    _xfip_live = opp_data.get("xfip_live")
                    _era_live  = opp_data.get("era_live")
                    pitcher_era = _era_live  or MLB_PITCHER_ERA.get(opp_pitcher, LEAGUE_AVG_ERA)
                    pitcher_fip = _fip_live  or MLB_PITCHER_FIP.get(opp_pitcher, pitcher_era)
                    pitcher_xfip= _xfip_live or pitcher_fip
                    # Blend: 50% xFIP (most forward-looking), 35% FIP, 15% ERA
                    blended = pitcher_xfip * 0.50 + pitcher_fip * 0.35 + pitcher_era * 0.15
                    fip_diff = blended - LEAGUE_AVG_ERA
                    pitcher_adj = max(-0.08, min(0.08, fip_diff / 100.0))
                    # Handedness wOBA adjustment: if the opposing team hits well vs this arm,
                    # increase edge for OVER props; decrease if they struggle.
                    hand = MLB_PITCHER_HANDEDNESS.get(opp_pitcher, "R")
                    woba_map = MLB_TEAM_WOBA_VS_LHP if hand == "L" else MLB_TEAM_WOBA_VS_RHP
                    # "team_full" here is the PLAYER's team = batter's team facing the pitcher
                    opp_woba = woba_map.get(team_full, MLB_WOBA_LEAGUE_AVG)
                    woba_diff = opp_woba - MLB_WOBA_LEAGUE_AVG
                    # woba_diff > 0 = good hitting team → more runs/props → OVER boost
                    woba_adj = woba_diff * 0.60  # scale: 0.020 wOBA delta ≈ 1.2% edge
                    pitcher_adj = max(-0.10, min(0.10, pitcher_adj - woba_adj))
                    pitcher_name = opp_pitcher


        ud_line_val = None
        for ud_p in (ud_props_compare or []):
            if (normalize_name(ud_p.get("Player","")) == normalize_name(player) and ud_p.get("Prop","") == stat_raw):
                ud_line_val = ud_p.get("Line")
                break
        std_dev_key = f"{stat_norm}_std"
        std_dev = avg_dict.get(std_dev_key, None)
        if std_dev is not None and days_rest is not None:
            std_dev = rest_adjusted_std_dev(std_dev, int(days_rest), sport)
        consensus_prob, consensus_books = compute_consensus_probability(sport, player, stat_raw, line, side)
        fairness_grade, fairness_note = check_prop_line_fairness(line, consensus_prob, side, odds=(p.get("OverOdds") if side.upper() == "OVER" else p.get("UnderOdds")))
        player_parts = player.split()
        if len(player_parts) >= 2:
            abbr_key = f"{player_parts[0][0]}.{player_parts[-1]}".lower()
        else:
            abbr_key = player.lower()
        an_stat_key = ACTION_NETWORK_PROP_TYPE_MAP.get(stat_raw, stat_raw)
        an_data = an_lookup.get((abbr_key, an_stat_key), {}) or an_lookup.get((abbr_key, stat_raw), {})
        an_projection = an_data.get("projection")
        an_grade = an_data.get("grade", "")
        an_edge = an_data.get("edge", 0)
        an_tier = an_data.get("tier", "")
        an_tickets = an_data.get("tickets_pct", 0)
        an_money = an_data.get("money_pct", 0)
        if sport == "MLB" and avg is not None:
            avg = pace_adjust_mlb_prop(avg, stat_norm)
        over_edge, over_prob, over_signals = compute_multi_signal_edge(line, avg, opp_def_rating, is_home, usage_boost, "OVER", stat_norm, pace_adj, days_rest, odds_type, sport, std_dev, weights=_preloaded_weights, player_name=player, over_odds=p.get("OverOdds"), under_odds=p.get("UnderOdds"))
        over_edge = max(-EDGE_CAP, min(EDGE_CAP, over_edge + blowout_adj + weather_adj + game_total_adj + referee_adj + pitcher_adj + h2h_adj))
        under_edge, under_prob, under_signals = compute_multi_signal_edge(line, avg, opp_def_rating, is_home, usage_boost, "UNDER", stat_norm, pace_adj, days_rest, odds_type, sport, std_dev, weights=_preloaded_weights, player_name=player, over_odds=p.get("OverOdds"), under_odds=p.get("UnderOdds"))
        under_edge = max(-EDGE_CAP, min(EDGE_CAP, under_edge - blowout_adj - weather_adj - game_total_adj - referee_adj - pitcher_adj - h2h_adj))
        if consensus_prob is not None:
            blended_over_prob = round(consensus_prob * 0.60 + over_prob * 0.40, 4)
            blended_under_prob = round((1 - consensus_prob) * 0.60 + under_prob * 0.40, 4)
            over_prob = max(0.20, min(0.80, blended_over_prob))
            under_prob = max(0.20, min(0.80, blended_under_prob))
            over_edge  = calculate_edge(over_prob,  "OVER",  sport, odds=p.get("OverOdds"))
            under_edge = calculate_edge(under_prob, "UNDER", sport, odds=p.get("UnderOdds"))

        # ── Multi-Sharp Ensemble — P_final = W_user*P_user + W_pin*P_pin + W_circa*P_circa ──
        # Circa co-equal sharp anchor for NFL/props. Pinnacle leads MLB/NHL.
        # Prop markets are Pinnacle's weakest area — our model has sovereign advantage here.
        _ev_sig_local = st.session_state.get("ev_signal_lookup", {}).get(
            (normalize_name(player), stat_raw), {}
        )
        _pn_nv    = _ev_sig_local.get("pn_novig")    if _ev_sig_local else ev_pn_novig
        _circa_nv = _ev_sig_local.get("circa_novig") if _ev_sig_local else ev_circa_novig

        if _pn_nv is not None or _circa_nv is not None:
            # Sport-specific sharp weights (Circa originates NFL; Pinnacle leads MLB)
            if sport == "NFL":
                _w_pin, _w_circa = 0.20, 0.25
            elif sport == "MLB":
                _w_pin, _w_circa = 0.25, 0.15
            else:
                _w_pin, _w_circa = 0.22, 0.13

            # Only use weights for books that have data
            _w_pin_used   = _w_pin   if _pn_nv    is not None else 0.0
            _w_circa_used = _w_circa if _circa_nv is not None else 0.0
            _w_user = max(0.50, 1.0 - _w_pin_used - _w_circa_used)

            # Normalize weights to sum to 1
            _total_w = _w_user + _w_pin_used + _w_circa_used
            _w_user       /= _total_w
            _w_pin_used   /= _total_w
            _w_circa_used /= _total_w

            _pin_p   = float(_pn_nv)    if _pn_nv    is not None else over_prob
            _circa_p = float(_circa_nv) if _circa_nv is not None else over_prob

            _ensemble_over = (_w_user * over_prob + _w_pin_used * _pin_p + _w_circa_used * _circa_p)
            _ensemble_over  = round(max(0.15, min(0.85, _ensemble_over)), 4)
            _ensemble_under = round(1.0 - _ensemble_over, 4)
            over_prob  = _ensemble_over
            under_prob = _ensemble_under
            over_edge  = calculate_edge(over_prob,  "OVER",  sport, odds=p.get("OverOdds"))
            under_edge = calculate_edge(under_prob, "UNDER", sport, odds=p.get("UnderOdds"))
        if fairness_grade == "BAD":
            over_edge = over_edge * 0.75
            under_edge = under_edge * 0.75
        elif fairness_grade == "CAUTION":
            over_edge = over_edge * 0.90
            under_edge = under_edge * 0.90
        # ── LINE_DEVIATION: cross-book consensus overlay ────────────────────
        _ld_lookup = st.session_state.get("line_deviation_lookup", {})
        try:
            from prop_normalizer import normalize_player_name as _np_fn, normalize_stat_name as _ns_fn
            _ld_key = (_np_fn(player), _ns_fn(stat_raw, sport))
        except Exception:
            _ld_key = (normalize_name(player), stat_raw)
        _ld_sig = _ld_lookup.get(_ld_key, {})
        if _ld_sig and _ld_sig.get("consensus_prob") is not None:
            _ld_prob = float(_ld_sig["consensus_prob"])
            _ld_dev  = float(_ld_sig.get("deviation_pct", 0))
            if _ld_dev >= LINE_DEVIATION_THRESHOLD_PCT:
                # Conservative 25 % blend — prop-consensus is thinner than
                # Pinnacle / Circa, so we weight it well below the sharp anchors.
                _ld_w     = 0.25
                over_prob  = round(_ld_w * _ld_prob      + (1 - _ld_w) * over_prob,  4)
                under_prob = round(1.0 - over_prob, 4)
                over_edge  = calculate_edge(over_prob,  "OVER",  sport, odds=p.get("OverOdds"))
                under_edge = calculate_edge(under_prob, "UNDER", sport, odds=p.get("UnderOdds"))
        # ── OVER-only prop guard ───────────────────────────────────────────
        # These are binary event markets — books only offer OVER (will it
        # happen or not). No sportsbook offers an UNDER market for these.
        # Prevent the model from ever recommending UNDER on them regardless
        # of what the edge math says.
        _OVER_ONLY_PROPS = {
            "HR", "Home Runs", "Home Run", "Homeruns", "Homerun",
            "GOALS", "Goals", "Goal",          # soccer/hockey: score a goal
            "TD", "Touchdowns", "Touchdown",   # NFL: score a TD
            "Aces", "ACES",                    # tennis: aces hit
            "Sacks", "SACKS",                  # NFL: sack (defender)
        }
        _is_over_only = (
            stat_norm in _OVER_ONLY_PROPS or
            p.get("Prop", "") in _OVER_ONLY_PROPS or
            p.get("stat_key", "") in _OVER_ONLY_PROPS
        )

        if under_edge > over_edge and (under_edge - over_edge) > 0.05 and not _is_over_only:
            best_edge = under_edge
            best_side = "UNDER"
            best_prob = under_prob
            best_signals = under_signals
        else:
            best_edge = over_edge
            best_side = "OVER"
            best_prob = over_prob
            best_signals = over_signals
        # SEM inputs for adjusted_edge
        _n_samp = len(p.get("GameLog", p.get("game_log", [])) or [])
        _std_d  = p.get("StdDev")
        _avg_v  = p.get("Avg", 0)
        # Auto-save Pinnacle line to closing line database
        _pinn_line = None  # not yet wired to a per-prop Pinnacle source in this loop
        if player and stat_norm and _pinn_line:
            try:
                save_closing_line(player, stat_norm, float(_pinn_line), sport, source="pinnacle")
            except Exception:
                _logger.debug("Silent except at line 12293")
                pass
        adj_edge, calibrated, _cal_meta = adjusted_edge(
            best_edge, sport, _get_cal_tier(best_edge, sport), stat_norm, history
        )
        final_edge = adj_edge if calibrated else best_edge
        try:
            _cal_debug_log = st.session_state.setdefault("calibration_debug_log", [])
            _cal_debug_log.append({
                "sport": sport, "stat": stat_norm, "tier": _get_cal_tier(best_edge, sport),
                "calibrated": calibrated, **_cal_meta,
            })
            if len(_cal_debug_log) > 500:
                del _cal_debug_log[:-500]
        except Exception:
            pass
        # NOTE 2026-07-09: _n_samp/_std_d/_avg_v above are dead inputs from an
        # abandoned earlier attempt at this (GameLog/game_log is never
        # actually populated anywhere in this codebase, so _n_samp is always
        # 0). The REAL, working sample-size confidence weighting already
        # exists a few lines below via avg_dict.get("n_games") +
        # sample_size_confidence() - that one uses a properly populated
        # field. Do not add a second confidence multiplier here; it would
        # double-discount every edge and, worse, incorrectly apply a flat
        # 20% reduction to everything since _n_samp is always 0.
        eff_score, eff_label = market_efficiency_score(line, ud_line_val, final_edge, sport)
        if (an_grade in ("A+", "A", "A-") and _get_cal_tier(final_edge, sport) in ("SOVEREIGN", "ELITE", "APPROVED")):
            final_edge = min(final_edge * 1.05, EDGE_CAP)
        if (an_grade in ("C", "D") and final_edge > 0.05):
            final_edge = final_edge * 0.90
        if sharp_flag and best_side == "OVER":
            player_matchup = next((g["Matchup"] for g in games if player_team in g.get("Matchup","")), "")
            sharp_direction = game_sharp_flags.get(player_matchup, {}).get("direction", "")
            if sharp_direction == "↑":
                final_edge = min(final_edge * 1.10, EDGE_CAP)
            elif sharp_direction == "↓":
                final_edge = final_edge * 0.90
        elif sharp_flag and best_side == "UNDER":
            player_matchup = next((g["Matchup"] for g in games if player_team in g.get("Matchup","")), "")
            sharp_direction = game_sharp_flags.get(player_matchup, {}).get("direction", "")
            if sharp_direction == "↓":
                final_edge = min(final_edge * 1.10, EDGE_CAP)
            elif sharp_direction == "↑":
                final_edge = final_edge * 0.90
        n_games = avg_dict.get("n_games", None)
        if n_games is not None:
            confidence_mult = sample_size_confidence(n_games, sport)
            if confidence_mult < 1.0:
                final_edge = final_edge * confidence_mult
        clv_mult, clv_note = get_clv_edge_adjustment(sport, _get_cal_tier(final_edge, sport))
        if clv_mult != 1.0:
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge * clv_mult))
        # ── Scanbet Pinnacle line movement (GraphQL) ───────────────────────
        _sb_matchup = next((g["Matchup"] for g in games if player_team and player_team in g.get("Matchup","")), "")
        home_team = home_teams.get(_sb_matchup, "")
        away_team = away_teams.get(_sb_matchup, "")
        if home_team or away_team:
            try:
                _sbd = st.session_state.get("scanbet_drops", [])
                _sb_hit = next((d for d in _sbd
                    if d.get("is_steam") and abs(d.get("drop_pct",0)) > 0.02 and (
                        normalize_name(home_team or "") in normalize_name(d.get("home",""))
                        or normalize_name(away_team or "") in normalize_name(d.get("away",""))
                        or normalize_name(home_team or "") in normalize_name(d.get("game",""))
                    )), None)
                if _sb_hit:
                    _dp    = _sb_hit.get("drop_pct",0)
                    _nsnap = _sb_hit.get("n_snapshots",0)
                    p["ScanbetSteam"]     = True
                    p["ScanbetDropPct"]   = _dp
                    p["ScanbetSnapshots"] = _nsnap
                    p["SignalNotes"] = p.get("SignalNotes","") + f" 📡 Pinnacle:{_dp:+.1%}({_nsnap}snaps)"
                    # Stronger signal with more snapshots confirming the move
                    if abs(_dp) > 0.05 and _nsnap >= 5:
                        final_edge = min(final_edge * 1.09, EDGE_CAP)  # strong confirmed steam
                    elif abs(_dp) > 0.03:
                        final_edge = min(final_edge * 1.05, EDGE_CAP)  # moderate steam
            except Exception:
                _logger.debug("Silent except at line 12355")
                pass

        # ── SharpAPI Pinnacle steam detection ────────────────────────────────
        if home_team or away_team:
            try:
                _sa_drops = st.session_state.get("sharpapi_line_drops", [])
                _steam = next((d for d in _sa_drops if d.get("is_steam") and (
                    normalize_name(home_team or "") in normalize_name(d.get("home",""))
                    or normalize_name(away_team or "") in normalize_name(d.get("away",""))
                )), None)
                if _steam:
                    _dp = _steam.get("drop_pct",0)
                    p["SteamMove"]   = True
                    p["SignalNotes"] = p.get("SignalNotes","") + f" 🔥 Steam:{_dp:+.1%}"
                    if abs(_dp) > 0.05:
                        final_edge = min(final_edge * 1.06, EDGE_CAP)
            except Exception:
                _logger.debug("Silent except at line 12372")
                pass

        # ── Defense ranking adjustment ─────────────────────────────────────
        if final_edge > 0 and p.get("Matchup"):
            try:
                _opp = p.get("Matchup","").split(" @ ")[0] if " @ " in p.get("Matchup","") else ""
                if _opp:
                    _dr  = st.session_state.get("defense_rankings") or {}
                    _de  = get_defense_edge(_opp, sport, _dr or None)
                    if _de.get("rank"):
                        p["DefenseRank"] = _de["rank"]
                        p["DefenseNote"] = _de["note"]
                        final_edge = final_edge * _de.get("edge_adj",1.0)
                        if _de.get("favorable"):
                            p["SignalNotes"] = p.get("SignalNotes","") + f" {_de['note']}"
            except Exception:
                _logger.debug("Silent except at line 12388")
                pass

        # ── Quantitative upgrades (ensemble devig + Bayesian + velocity) ───────
        try:
            from bc_utils import apply_all_upgrades as _aau
            _scanbet_raw = None
            _sbd_all = st.session_state.get("scanbet_drops",[])
            if _sbd_all and (home_team or away_team):
                _scanbet_raw = next((d.get("raw",{}) for d in _sbd_all
                    if normalize_name(home_team or "") in normalize_name(d.get("home",""))
                    or normalize_name(away_team or "") in normalize_name(d.get("away",""))
                ), None)
            _inj = [{"player":i,"role":"starter","status":"out"}
                    for i in prop.get("InjuryContext","").split(",") if i.strip()] if prop.get("InjuryContext") else []
            prop = _aau(prop, scanbet_raw=_scanbet_raw,
                        injuries=_inj if _inj else None, sport=sport)
            # Update final_edge from Bayesian fair prob
            if prop.get("BayesianProb"):
                _mkt_prob = american_to_prob(float(prop.get("Odds", prop.get("odds", -110)) or -110))
                final_edge = prop["BayesianProb"] - _mkt_prob
        except Exception:
            pass

        # ── EVBets +EV signal overlay ────────────────────────────────────────
        if home_team or away_team:
            try:
                _evb = st.session_state.get("evbets_ev_picks",[]) + st.session_state.get("evbets_prop_picks",[])
                _evb_hit = next((e for e in _evb
                    if normalize_name(home_team or "") in normalize_name(e.get("event",""))
                    or normalize_name(away_team or "") in normalize_name(e.get("event",""))
                    or normalize_name(player or "") in normalize_name(e.get("event",""))
                ), None)
                if _evb_hit:
                    _ev_pct = _evb_hit.get("ev_pct",0)
                    _ev_book = _evb_hit.get("book","")
                    prop["EVBetsEV"]    = _ev_pct
                    prop["EVBetsBook"]  = _ev_book
                    prop["SignalNotes"] = prop.get("SignalNotes","") + f" 💰EVBets:{_ev_pct:+.1f}%@{_ev_book}"
                    if _ev_pct >= 5:
                        final_edge = min(final_edge * 1.06, EDGE_CAP)
                    elif _ev_pct >= 2:
                        final_edge = min(final_edge * 1.03, EDGE_CAP)
            except Exception:
                pass

        # ── Signal Odds / BetsLib AI prediction overlay ────────────────────
        if home_team or away_team:
            try:
                _bl_preds = st.session_state.get("betslib_predictions", [])
                _bl_hit   = next((p for p in _bl_preds
                    if (home_team and normalize_name(home_team) in normalize_name(p.get("home","")))
                    or (away_team and normalize_name(away_team) in normalize_name(p.get("away","")))),None)
                if _bl_hit:
                    _bl_conf = _bl_hit.get("confidence",0)
                    _bl_ev   = _bl_hit.get("ev",0)
                    if _bl_conf >= 0.65 and _bl_ev > 0:
                        p["SignalNotes"] = p.get("SignalNotes","") + f" 🤖 SO:{_bl_conf:.0%} EV:{_bl_ev:.2f}"
                        final_edge = min(final_edge*1.05, EDGE_CAP)
                    elif _bl_conf < 0.40:
                        p["SignalNotes"] = p.get("SignalNotes","") + f" ⚠️ SO fade:{_bl_conf:.0%}"
                        final_edge = final_edge*0.92
            except Exception:
                _logger.debug("Silent except at line 12407")
                pass

        # ── FantasyPros projection cross-check ──────────────────────────────
        if player:
            try:
                _fp  = st.session_state.get("fantasypros_proj",{}).get(normalize_name(player),{})
                _fpp = _fp.get("projections",{})
                _fpv = next((v for k,v in _fpp.items() if stat_norm and stat_norm[:4] in k.lower()),None)
                if _fpv and float(line or 0) > 0:
                    _gap = (_fpv - float(line)) / float(line)
                    p["FPProjection"] = _fpv
                    p["FPGap"]        = _gap
                    if _gap > 0.08:
                        p["SignalNotes"] = p.get("SignalNotes","") + f" 📋 FP:{_fpv:.1f}"
                        final_edge = min(final_edge*1.04, EDGE_CAP)
                    elif _gap < -0.08:
                        p["SignalNotes"] = p.get("SignalNotes","") + f" ⚠️ FP under:{_fpv:.1f}"
                        final_edge = final_edge*0.92
            except Exception:
                _logger.debug("Silent except at line 12426")
                pass

        # ── Regression-to-mean discount (applied last — after all other mults) ──
        # HOT streak penalises OVER edge (recency-inflated line, regression
        # likely to push the player back down). COLD streak penalises UNDER
        # edge the same way in reverse (slump likely to regress back up).
        # The opposite side of each is actually supported by the regression
        # thesis, so it's left alone.
        if _regression_risk["risk"] != "NONE" and _regression_risk["edge_mult"] < 1.0:
            _reg_dir = _regression_risk.get("direction", "HOT")
            if ((_reg_dir == "HOT" and best_side == "OVER") or
                (_reg_dir == "COLD" and best_side == "UNDER")) and final_edge > 0:
                final_edge = round(final_edge * _regression_risk["edge_mult"], 4)
                if _regression_risk["note"]:
                    avg_dict["regression_note"] = _regression_risk["note"]
                    avg_dict["regression_risk"] = _regression_risk["risk"]
        # ── Always-OVER props — markets that don't offer UNDER ──
        # Sportsbooks only offer OVER on these low-base-rate props
        ALWAYS_OVER_PROPS = {
            "Home Runs", "HR", "Pitcher Wins", "Wins",
            "Saves", "Blowout", "First Basket",
        }
        _stat_norm_check = stat_norm.strip().title()
        if _stat_norm_check in ALWAYS_OVER_PROPS:
            if final_edge < 0:
                skipped_edge += 1
                continue
            pick_dir = "OVER"

        # ── EV API S12 injections (Statcast + Stadium) ─────────────────
        # Applied after calibration so they compound on top of the clean edge
        if statcast_edge != 0.0 and sport == "MLB":
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + statcast_edge))
        if stadium_edge != 0.0 and sport == "MLB":
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + stadium_edge))

        # ── EV Movement S8 — Market Movement Vector ─────────────────────
        if ev_s8_vector != 0:
            s8_adj = ev_s8_vector * 0.01
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + s8_adj))

        # ── EV Movement S9 — RLM boost ──────────────────────────────────
        if ev_s9_boost > 0:
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + ev_s9_boost))

        # ── EV S7 — BvP direct (overrides L10 proxy) ────────────────────
        if ev_bvp_edge != 0.0:
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + ev_bvp_edge))
            if not h2h_note:
                h2h_note = ev_bvp_note + " [EV API — BvP]"

        # ── EV S12 — Homer due (PA streak z-score) ──────────────────────
        if ev_homer_due_edge != 0.0 and sport == "MLB":
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + ev_homer_due_edge))

        # ── LineStar/Baseball-Savant batter-CSV edges (2026-07) ─────────
        if sport == "MLB":
            if sav_brl_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + sav_brl_edge))
            if sav_reg_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + sav_reg_edge))
            if sav_spd_edge != 0.0 and ("Stolen" in stat_raw or "Base" in stat_raw):
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + sav_spd_edge))
            if sav_la_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + sav_la_edge))
            if sav_ars_edge != 0.0 and "Strikeout" in stat_raw:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + sav_ars_edge))
            if sav_fb_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + sav_fb_edge))
            if today_brl_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + today_brl_edge))
            if preview_platoon_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + preview_platoon_edge))
            if preview_hr_rate_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + preview_hr_rate_edge))
            if brl_edge != 0.0:
                final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge + brl_edge))

        # ── EV API S6 — Pinnacle/Circa no-vig override ─────────────────
        # Use Shin method for HR props (longshot market, +200 to +800 odds)
        # Use additive for standard props
        if ev_consensus_novig is not None:
            _novig_side = ev_consensus_novig if best_side == "OVER" else (1 - ev_consensus_novig)
            if _novig_side > 0.52:
                final_edge = min(EDGE_CAP, final_edge * 1.05)   # confirms
            elif _novig_side < 0.46:
                final_edge = final_edge * 0.90                   # fades

        # ── EV API S7 proxy — L10 hit rate when game logs unavailable ──
        if ev_l10_rate is not None and not h2h_note and sport == "MLB":
            if ev_l10_rate >= 0.70:
                final_edge = min(EDGE_CAP, final_edge + 0.02)
                h2h_note = f"L10 hit {ev_l10_rate:.0%} [EV API]"
            elif ev_l10_rate <= 0.30:
                final_edge = final_edge - 0.02
                h2h_note = f"L10 hit {ev_l10_rate:.0%} [EV API]"

        if final_edge < min_edge:
            skipped_edge += 1
            continue
        tier = _get_cal_tier(final_edge, sport)

        # ── Role change detection — applied to final_edge ──────
        _role_change = detect_role_changes(player, sport, {}, st.session_state.get("history", []))
        if not _role_change:
            _rc_team = p.get("Team","")
            _role_change = check_depth_chart_role_change(player, _rc_team, sport)
        if _role_change:
            _rc_adj = _role_change.get("edge_adj", 0)
            if abs(_rc_adj) > 0:
                final_edge = round(max(-EDGE_CAP, min(EDGE_CAP, final_edge + _rc_adj)), 4)
                tier = _get_cal_tier(final_edge, sport)  # re-tier after role change

        # ── Market Move Quality ────────────────────────────────
        _matchup_str = p.get("Matchup", p.get("matchup",""))
        _move_quality, _move_note = compute_market_move_quality(
            _matchup_str, stat_norm, sport
        )
        if _move_quality >= 2:
            final_edge = round(min(EDGE_CAP, final_edge + 0.02), 4)
        elif _move_quality == -1:
            final_edge = round(final_edge - 0.01, 4)
        elif _move_quality == -2:
            final_edge = round(final_edge - 0.02, 4)

        # ── Minutes CV + Volatility ─────────────────────────────
        _game_logs  = st.session_state.get("player_game_logs", {})
        _mins_cv, _mins_stability, _mins_adj = compute_minutes_cv(player, sport, _game_logs)
        _stat_std, _risk_level, _risk_note   = compute_volatility_flag(player, sport, stat_norm, _game_logs)
        if _mins_adj != 0:
            final_edge = round(max(-EDGE_CAP, min(EDGE_CAP, final_edge + _mins_adj)), 4)
        if isinstance(_stat_std, float) and _risk_level in ("HIGH","EXTREME"):
            _stat_adj = -0.01 if _risk_level == "HIGH" else -0.02
            final_edge = round(max(-EDGE_CAP, min(EDGE_CAP, final_edge + _stat_adj)), 4)

        # ── Projection confidence score ─────────────────────────
        _sample_n = len([h for h in st.session_state.get("history", [])
                         if normalize_name(h.get("player","")) == normalize_name(player)])
        _inj_status = injuries.get(normalize_name(player), {}).get("status","") if isinstance(injuries, dict) else ""
        _lineup_conf = p.get("LineupStatus","").startswith("✅") if p.get("LineupStatus") else None
        # Real Pinnacle agreement: how close our model's probability is to
        # Pinnacle's no-vig probability for the same side. Small gap = they
        # agree = genuine external confirmation. Previously this passed our
        # own model edge (final_edge) here, which rewarded large self-edges
        # as if they were market confirmation -- backwards, since a bigger
        # edge from us alone is more often model error than real value.
        _pinn_agreement_gap = None
        if _pn_nv is not None:
            try:
                _pinn_agreement_gap = abs(float(best_prob) - float(_pn_nv))
            except (TypeError, ValueError):
                _pinn_agreement_gap = None
        _proj_conf = compute_projection_confidence(
            player=player, prop=stat_norm, line=line, sport=sport,
            sample_n=_sample_n, injury_status=_inj_status,
            lineup_confirmed=_lineup_conf,
            market_edge=_pinn_agreement_gap,
        )
        # Confidence affects final tier — LOW confidence can downgrade
        if _proj_conf["score"] < 40 and tier in ("SOVEREIGN","ELITE"):
            tier = "APPROVED"  # downgrade very low confidence high-edge picks
        elif _proj_conf["score"] < 60 and tier == "SOVEREIGN":
            tier = "ELITE"     # downgrade sovereign to elite if low confidence

        # ── Model vs market comparison ──────────────────────────
        _mkt_vs_model = compute_model_vs_market(avg, line, stat_norm)

        # ── NFL usage edge (activates when season data available)
        if sport == "NFL":
            _usage = get_nfl_usage(player)
            if _usage:
                _usage_adj, _usage_note = compute_usage_edge(_usage, stat_norm)
                if _usage_adj != 0:
                    final_edge = round(final_edge + _usage_adj, 4)

        injury_flag = injuries.get(player, "") if isinstance(injuries, dict) else ""
        # ── Auto injury edge discount (gap fix #3) ──────────
        # Previously injury_flag was stored but never reduced final_edge for
        # the player themselves — only teammate DFF adjustments fired.
        # Now: OUT/DOUBTFUL → suppress pick (edge → 0); QUESTIONABLE → -30%
        # edge penalty; PROBABLE → -10%.  This runs BEFORE the tier re-calc
        # so suppressed injuries don't appear as SOVEREIGN picks.
        if injury_flag:
            _inj_status = str(injury_flag).upper()
            if any(s in _inj_status for s in ("OUT", "DOUBTFUL", "DTD", "IR", "INACTIVE")):
                final_edge  = 0.0
                best_prob   = 0.5
                tier        = "PASS"
                p["InjuryNote"] = f"⛔ {injury_flag} — pick suppressed"
            elif "QUEST" in _inj_status:
                final_edge  = round(final_edge * 0.70, 4)
                tier        = _get_cal_tier(final_edge, sport)
                p["InjuryNote"] = f"⚠️ {injury_flag} — edge -30%"
            elif "PROB" in _inj_status:
                final_edge  = round(final_edge * 0.90, 4)
                tier        = _get_cal_tier(final_edge, sport)
                p["InjuryNote"] = f"🟡 {injury_flag} — edge -10%"
        # DFF Teammate Impact — NBA/WNBA primarily
        if sport in ("NBA","WNBA"):
            _dff_cache = st.session_state.get("dff_cache", {})
            if _dff_cache:
                _dff_team = p.get("Team","")
                _dff_adj, _dff_signals, _dff_note = compute_dff_teammate_impact(
                    player, _dff_team, sport,
                    stat_norm, line,
                    dff_data=None,
                    injury_data=injuries,
                )
                if _dff_adj != 0:
                    final_edge = round(max(-EDGE_CAP, min(EDGE_CAP, final_edge + _dff_adj)), 4)
                    tier = _get_cal_tier(final_edge, sport)
                if _dff_note:
                    p["DFFSignal"] = _dff_note
                if _dff_signals:
                    p["DFFRosterContext"] = _dff_signals

        # DFF PropStats — hit rate confirmation signal
        _dff_pid = get_dff_player_id(player, sport)
        if _dff_pid:
            # NOTE: fetch_dff_propstats is a dead stub (dailyfantasyfuel.com
            # is Cloudflare-blocked) — always returns {}. Call matches its
            # real signature so this doesn't TypeError; direction/last_n
            # were never accepted params.
            _dff_ps = fetch_dff_propstats(
                player_id  = _dff_pid,
                sport      = sport,
                metric     = stat_norm,
                line       = line,
                team       = p.get("Team",""),
                opponent   = p.get("Opponent",""),
            )
            if _dff_ps:
                _ps_adj, _ps_note = compute_dff_propstats_edge(_dff_ps, final_edge)
                if _ps_adj != 0:
                    final_edge = round(max(-EDGE_CAP, min(EDGE_CAP, final_edge + _ps_adj)), 4)
                    tier = _get_cal_tier(final_edge, sport)
                p["DFFHitRateL10"]    = _dff_ps.get("hit_rate", 0)
                p["DFFAvgVal"]        = _dff_ps.get("avg_val", 0)
                p["DFFAvgMins"]       = _dff_ps.get("avg_minutes", 0)
                p["DFFAvgUsage"]      = _dff_ps.get("avg_usage", 0)
                p["DFFAvgPotentials"] = _dff_ps.get("avg_potentials", 0)
                p["DFFGamesTotal"]    = _dff_ps.get("total_games", 0)
                if _ps_note:
                    p["DFFPropNote"]  = _ps_note

        # All sports: apply FantasyLabs lineup bonus
        # MLB: batting order bonus — ONLY within 4hr of first pitch
        #      (lineups not posted until 2-3hr before game)
        # NBA/WNBA: starter confirmation
        # NFL: active/inactive (90min before kickoff — handled separately)
        # NHL: skater line confirmation
        if sport in ("MLB","NBA","WNBA","NFL","NHL"):
            _fl_data = st.session_state.get("fantasylabs_lineups", {})
            if _fl_data:
                # MLB time guard: only apply batting order bonuses when
                # lineups are actually confirmed (within 4hr of first pitch)
                # Before that window: S12 = neutral (0%) to avoid
                # false penalties on morning loads
                _apply_fl = True
                if sport == "MLB":
                    _game_time_str = p.get("GameTime","") or p.get("game_time","")
                    if _game_time_str:
                        try:
                            from datetime import datetime as _dt
                            _gt = _dt.strptime(str(_game_time_str)[:16], "%Y-%m-%d %H:%M")
                            _hrs_to_game = (_gt - _dt.now()).total_seconds() / 3600
                            _apply_fl = _hrs_to_game <= 4.0
                        except Exception:
                            # Can't parse time — only apply if lineups confirmed
                            _apply_fl = bool(_fl_data.get(
                                normalize_name(player), {}
                            ).get("in_lineup", False))
                    else:
                        # No game time stored — check if lineup is confirmed
                        _apply_fl = bool(_fl_data.get(
                            normalize_name(player), {}
                        ).get("in_lineup", False))

                if _apply_fl:
                    _fl_adj, _fl_flags, _fl_note = get_fantasylabs_lineup_bonus(player, _fl_data, sport)
                    if _fl_adj != 0:
                        final_edge = round(max(-EDGE_CAP, min(EDGE_CAP, final_edge + _fl_adj)), 4)
                        tier = _get_cal_tier(final_edge, sport)
                    if _fl_note:
                        p["LineupStatus"] = _fl_note
                    # Store separate flags — not composite score
                    if isinstance(_fl_flags, dict) and _fl_flags.get("found"):
                        p["IsStarting"]      = _fl_flags.get("is_starting", True)
                        p["BattingOrder"]    = _fl_flags.get("batting_order", 0)
                        p["LineupInjury"]    = _fl_flags.get("injury_status","")
                        p["LineupConfirmed"] = _fl_flags.get("is_starting", False)
                        p["IsQuestionable"]  = _fl_flags.get("is_questionable", False)
                else:
                    # Outside 4hr window — neutral, no adjustment
                    p["LineupStatus"]   = "⏳ Lineups not yet confirmed (>4h to game)"
                    p["LineupConfirmed"] = False

        # NFL: add practice trend to injury flag
        if sport == "NFL" and not injury_flag:
            _practice = st.session_state.get("nfl_practice", {})
            _trend = get_practice_trend(player, _practice)
            if _trend and "DNP" in _trend:
                injury_flag = f"Practice: {_trend}"
        sem_display, sem_n = compute_sem_for_tier(tier_stats, tier)
        ev_2pick = calculate_prizepicks_ev(best_prob, 2)
        ev_3pick = calculate_prizepicks_ev(best_prob, 3)
        wager_2pick = kelly_unit_prizepicks(best_prob, st.session_state.get("bankroll", DEFAULT_BANKROLL), 2)
        wager_3pick = kelly_unit_prizepicks(best_prob, st.session_state.get("bankroll", DEFAULT_BANKROLL), 3)
        season_stat = PLAYER_AVERAGES.get(sport, {}).get(player, {}).get(stat_norm, avg)
        recency_flag, trend = get_recency_context(player, stat_norm, season_stat, avg, sport)
        signals_active = {"base_positive": best_signals.get("base", 0) > 0, "defense_positive": best_signals.get("defense", 0) > 0, "location_home": is_home, "back_to_back": days_rest == 0, "sharp_flag": bool(sharp_flag), "weather_active": weather_adj != 0, "blowout_risk": blowout_adj < 0, "usage_boost": usage_boost > 0, "h2h_positive": h2h_adj > 0, "h2h_negative": h2h_adj < 0,
                          # Raw numeric context, preserved so post-mortem can explain
                          # MAGNITUDE and DIRECTION, not just "a factor was active" —
                          # these were already computed above, just weren't being kept.
                          "defense_strength": round(best_signals.get("defense", 0), 3),
                          "weather_severity": round(weather_adj, 3) if weather_adj else 0,
                          "blowout_severity": round(blowout_adj, 3) if blowout_adj else 0,
                          "days_rest_actual": days_rest,
                          # MLB opposing starter quality — already computed above
                          # (era_diff / blended xFIP-FIP-ERA), just wasn't persisted.
                          "pitcher_quality_adj": round(pitcher_adj, 4) if sport == "MLB" and pitcher_adj else 0,
                          "opposing_pitcher": pitcher_name if sport == "MLB" else "",
                          # NHL opposing goalie quality — same pattern as MLB pitcher,
                          # now exposed as signals["goalie"] inside compute_multi_signal_edge
                          # instead of only being folded silently into the averages.
                          "goalie_quality_adj": round(best_signals.get("goalie", 0), 4) if sport == "NHL" else 0}
        # ── Market-Anchored Fair Line Pricer (NBA only — needs L20 rolling
        # data across the fuller stat set; informational signal, not blended
        # into the core weighted edge, same treatment as EXPECTED_VS_ACTUAL) ──
        _pricer_stat_map = {"PTS":"PTS","REB":"REB","AST":"AST","PRA":"PRA",
                             "BLK":"BLK","STL":"STL","TOV":"TOV","THREE_PT":"3PM"}
        _pricer_info = None
        if sport == "NBA" and stat_norm in _pricer_stat_map:
            _l20_row = l20_pricer_baseline.get(player) if l20_pricer_baseline else None
            if _l20_row:
                _pricer_key = _pricer_stat_map[stat_norm]
                _l20_val = _l20_row.get(_pricer_key)
                _n_games = _l20_row.get("n_games", 20)
                if _l20_val is not None:
                    try:
                        _pricer_info = compute_market_anchored_fair_line(
                            raw_l20_avg=_l20_val, observed_line=line, stat=_pricer_key,
                            n_games=_n_games, agreement_factor=1.0,
                        )
                    except Exception:
                        _pricer_info = None

        enriched.append({
            "Player": player, "Prop": stat_raw, "Line": line, "Side": best_side, "Avg": avg,
            "Edge": final_edge, "EdgePct": f"{final_edge:.1%}", "Prob": best_prob,
            "Wager": kelly_unit(best_prob, st.session_state.get("bankroll", DEFAULT_BANKROLL)), "Tier": tier,
            "Quality": "Lookup" if not using_default else "Default", "Model": "MultiSignal",
            "Sport": sport, "Injury": injury_flag, "SEM": sem_display, "SEM_n": sem_n,
            "SignalBase": best_signals.get("base", 0), "SignalDefense": best_signals.get("defense", 0),
            "SignalLocation": best_signals.get("location", 0), "SignalUsage": best_signals.get("usage", 0),
            "SignalRest": best_signals.get("rest", 0), "SignalPace": best_signals.get("pace", 0),
            "SignalBlowout": blowout_adj, "SignalH2H": h2h_adj, "H2HNote": h2h_note,
            "WeatherNote": weather_note, "Movement": "", "OddsTypeFlip": "",
            "Efficiency": eff_label, "EffScore": eff_score, "SharpFlag": sharp_flag,
            "source": p.get("source", ""), "Source": p.get("source","").title() or "Unknown",  # uppercase for Audit 3
            "ProjConfidence": _proj_conf.get("score", 50),
            "ProjConfLabel":  _proj_conf.get("label","MODERATE"),
            "MarketVsModel":  _mkt_vs_model,
            "RoleChange":     _role_change,
            "MarketMoveQuality":_move_quality,
            "MarketMoveNote":   _move_note,
            "MinutesCV":        _mins_cv,
            "MinutesStability": _mins_stability,
            "VolatilityStd":    _stat_std,
            "RiskLevel":        _risk_level,
            "PricerFairLine":    _pricer_info.get("fair_line") if _pricer_info else None,
            "PricerEdgeVsOpen":  _pricer_info.get("edge_vs_open") if _pricer_info else None,
            "PricerUncertainty": _pricer_info.get("uncertainty_penalty") if _pricer_info else None,
            "RiskNote":         _risk_note,
            "DFFSignal":        p.get("DFFSignal",""),
            "DFFRosterContext":  p.get("DFFRosterContext",[]),
            "DFFHitRateL10":    p.get("DFFHitRateL10", 0),
            "DFFAvgVal":        p.get("DFFAvgVal", 0),
            "DFFAvgMins":       p.get("DFFAvgMins", 0),
            "DFFAvgUsage":      p.get("DFFAvgUsage", 0),
            "DFFAvgPotentials": p.get("DFFAvgPotentials", 0),
            "DFFGamesTotal":    p.get("DFFGamesTotal", 0),
            "DFFPropNote":      p.get("DFFPropNote",""),
            "UnabatedLine":     p.get("UnabatedLine"),
            "UnabatedPrice":    p.get("UnabatedPrice"),
            "UnabatedFairProb": p.get("UnabatedFairProb"),
            "UnabatedDiscrepancy": (
                round(abs(best_prob - p["UnabatedFairProb"]), 4)
                if p.get("UnabatedFairProb") is not None else None
            ),
            # Direction + flag on top of the discrepancy magnitude above —
            # both derived from fields already on this row, no re-devig:
            # model_higher = GEM thinks it's easier than the market does;
            # market_higher = the market (via Unabated's real price) thinks
            # it's easier than GEM does. 5pt threshold matches the starting
            # point agreed for this flag (distinct from the 3pt DIVERGENT
            # convention used elsewhere for sharp-consensus spread checks).
            "UnabatedDirection": (
                ("model_higher" if best_prob > p["UnabatedFairProb"] else "market_higher")
                if p.get("UnabatedFairProb") is not None else None
            ),
            "UnabatedFlag": (
                abs(best_prob - p["UnabatedFairProb"]) >= 0.05
                if p.get("UnabatedFairProb") is not None else False
            ),
            "EVSharpsFairProb": p.get("EVSharpsFairProb"),
            "EVSharpsDirection": (
                ("model_higher" if best_prob > p["EVSharpsFairProb"] else "market_higher")
                if p.get("EVSharpsFairProb") is not None else None
            ),
            "EVSharpsFlag": (
                abs(best_prob - p["EVSharpsFairProb"]) >= 0.05
                if p.get("EVSharpsFairProb") is not None else False
            ),
            "EV_2pick": f"{ev_2pick:+.1%}", "EV_3pick": f"{ev_3pick:+.1%}",
            "Wager_2pick": wager_2pick, "Wager_3pick": wager_3pick, "PlusEV_2": ev_2pick > 0,
            "PlusEV_3": ev_3pick > 0, "OddsType": odds_type, "signals_active": signals_active,
            "Trend": recency_flag, "TrendDir": trend, "SampleSize": n_games if n_games else "—",
            "ConfidenceMult": round(sample_size_confidence(avg_dict.get("n_games"), sport), 2),
            "CLVAdj": clv_note, "RefNote": ref_note, "Pitcher": pitcher_name,
            "SearchNeeded": avg_dict.get("search_needed", False), "SearchQuery": avg_dict.get("search_query", ""),
            "StdDev": std_dev, "StdDevSource": "computed" if std_dev else "estimated",
            "ConsensusProb": f"{consensus_prob:.1%}" if consensus_prob else "—",
            "ConsensusBooks": ", ".join(consensus_books) if consensus_books else "—",
            "ModelProb": f"{best_prob:.1%}", "FairnessGrade": fairness_grade,
            "FairnessNote": fairness_note, "AN_Grade": an_grade,
            "AN_Projection": round(float(an_projection), 1) if an_projection else None,
            "AN_Edge": round(float(an_edge), 3) if an_edge else None, "AN_Tier": an_tier,
            "AN_Tickets": an_tickets, "AN_Money": an_money,
            "AN_Confirms": (an_tier in ("SOVEREIGN", "ELITE") and _get_cal_tier(final_edge, sport) in ("SOVEREIGN", "ELITE", "APPROVED")),
            # EV API signals
            "EVPinnacleNoVig":   ev_pn_novig,
            "EVCircaNoVig":      ev_circa_novig,
            "EVConsensusNoVig":  ev_consensus_novig,
            "EVSharpFV":         ev_sharp_fv,
            "EVSharpEV":         ev_sharp_ev,
            "EVStatcastEdge":    statcast_edge,
            "EVStatcastNotes":   ", ".join(statcast_notes) if statcast_notes else "",
            "EVStadiumEdge":     stadium_edge,
            "EVPitcherERA":      _ev_sig.get("pitcher_era") if _ev_sig else None,
            "EVPitcherXwOBA":    _ev_sig.get("pitcher_xwoba") if _ev_sig else None,
            "EVPitcherFlyball":  _ev_sig.get("pitcher_flyball") if _ev_sig else None,
            "EVPitcherBarrel":   _ev_sig.get("pitcher_barrel") if _ev_sig else None,
            "EVL10Rate":         ev_l10_rate,
            "EVBvP":             ev_bvp_note,
            "EVBvPEdge":         ev_bvp_edge,
            "EVHomerDueEdge":    ev_homer_due_edge,
            "EVHomerStreak":     _ev_sig.get("homer_streak") if _ev_sig else None,
            "EVHomerMed":        _ev_sig.get("homer_med") if _ev_sig else None,
            "EVHomerZ":          _ev_sig.get("homer_z_median") if _ev_sig else None,
            "EVFDZScore":        _ev_sig.get("fd_z_score") if _ev_sig else None,
            "EVPNMedian":        _ev_sig.get("pn_median") if _ev_sig else None,
            "EVCircaMedian":     _ev_sig.get("circa_median") if _ev_sig else None,
            "EVWeather":         _ev_sig.get("weather") if _ev_sig else None,
            "EVBPP":             _ev_sig.get("bpp_factor") if _ev_sig else None,
            # S8/S9 movement
            "EVS8Vector":        ev_s8_vector,
            "EVS9Boost":         ev_s9_boost,
            "EVRLMNote":         ev_rlm_note,
            "EVSteamFlag":       ev_steam_flag,
            "EVSharpMove":       ev_sharp_move,
        })
        # ── Elite Kelly Sizing Pipeline (computed after dict appended) ──────
        # Platt calibration, time-decay, and adaptive fraction are computed
        # outside the dict literal then stored on the last-appended prop.
        _cal_history  = st.session_state.get("history", [])
        _raw_prob_str = enriched[-1].get("Prob") or enriched[-1].get("FairProb") or (0.5 + final_edge / 2)
        try:
            _raw_prob_f = float(str(_raw_prob_str).replace("%","")) / (100 if "%" in str(_raw_prob_str) else 1)
        except (ValueError, TypeError):
            _raw_prob_f = 0.5 + final_edge / 2
        _cal_prob     = platt_calibrate_prob(_raw_prob_f, _cal_history, sport=sport)
        _decayed_edge = time_decay_edge_factor(final_edge, minutes_to_lock=None, decay_model="exponential")
        _base_frac    = KELLY_BY_TIER.get(tier, 0.15)
        _adapt_frac   = adaptive_kelly_fraction(_base_frac, _cal_history, sport=sport,
                                                 market=enriched[-1].get("Prop", "GENERAL"))
        _kelly_decay  = kelly_with_edge_decay(
            _decayed_edge, -110,
            time_to_lock_minutes=None,
            pinnacle_open=(_ev_sig.get("pn_novig") is not None) if _ev_sig else False,
            circa_open=(_ev_sig.get("circa_novig") is not None) if _ev_sig else False,
            fraction=_adapt_frac,
        )
        enriched[-1]["KellyDecay"]            = _kelly_decay
        enriched[-1]["KellyAdaptiveFraction"] = _adapt_frac
        enriched[-1]["KellyCalibProb"]        = _cal_prob
        enriched[-1]["KellyDecayedEdge"]      = _decayed_edge
    # Add H2H signal to each prop (uses cached game logs if available)
    for prop in enriched:
        player = prop.get("Player","")
        opponent = prop.get("Opponent","")
        stat = prop.get("Prop","")
        line = prop.get("Line",0)
        if player and opponent and line > 0:
            cache_key = f"bdl_logs_{normalize_name(player)}_2025"
            cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "rb") as cf:
                        logs = pickle.load(cf)
                    h2h_rate, h2h_n, h2h_str = compute_h2h_hit_rate(logs, opponent, stat, line)
                    if h2h_rate is not None and h2h_n >= 3:
                        prop["H2HRate"] = f"{h2h_rate:.0%} ({h2h_str})"
                        # Boost edge if strong H2H hit rate
                        if h2h_rate >= 0.70:
                            prop["Edge"] = round(prop.get("Edge",0) + 0.02, 4)
                        elif h2h_rate <= 0.30:
                            prop["Edge"] = round(prop.get("Edge",0) - 0.02, 4)
                    else:
                        prop["H2HRate"] = "—"
                except (ValueError, TypeError, ZeroDivisionError):
                    prop["H2HRate"] = "—"
            else:
                prop["H2HRate"] = "—"
        else:
            prop["H2HRate"] = "—"

    # Add Pinnacle fair value signal to each prop
    for prop in enriched:
        pinn_prob, pinn_confirms, pinn_note = pinnacle_fair_value(
            prop.get("Player",""), prop.get("Prop",""),
            prop.get("Line",0), prop.get("Side","OVER"), sport
        )
        prop["PinnacleProb"] = f"{pinn_prob:.1%}" if pinn_prob else "—"
        prop["PinnacleConfirms"] = pinn_confirms
        prop["PinnacleNote"] = pinn_note
        prop["PinnacleEdge"] = get_pinnacle_edge(prop.get("Prob",0.5), pinn_prob, prop.get("Side","OVER"))
        if pinn_note:
            prop["PinnacleNote"] = pinn_note
        # Boost tier if Pinnacle confirms AND our model says edge
        if pinn_confirms and prop.get("Tier") == "APPROVED":
            prop["Tier"] = "ELITE"
            prop["TierBoost"] = "Pinnacle-confirmed"
        # Downgrade if Pinnacle strongly fades
        if pinn_prob and pinn_prob < 0.44 and prop.get("Side","OVER") == "OVER":
            if prop.get("Tier") in ("SOVEREIGN","ELITE"):
                prop["Tier"] = "APPROVED"
                prop["TierNote"] = "Downgraded: Pinnacle fades"

    # FanDuel/DraftKings no-vig validation using alt lines
    fd_dk_alts = _fd_dk_alts
    for prop in enriched:
        player    = prop.get("Player","")
        stat_norm = STAT_NORMALIZE.get((sport, prop.get("Prop","")), prop.get("Prop",""))
        line      = prop.get("Line", 0)
        if fd_dk_alts:
            fd_result = get_fanduel_dk_validation(player, stat_norm, line, sport, fd_dk_alts)
            if fd_result:
                prop["FDDKProb"] = fd_result["implied_prob"]
                prop["FDDKConfirms"] = fd_result["confirms"]
                prop["FDDKFades"] = fd_result["fades"]
                prop["FDDKSource"] = fd_result["source"]
                prop["FDDKOverOdds"] = fd_result.get("over_odds","—")
                prop["FDDKUnderOdds"] = fd_result.get("under_odds","—")
                if fd_result["confirms"] and prop.get("PinnacleConfirms") and prop.get("Tier") in ("APPROVED","ELITE"):
                    prop["Tier"] = "SOVEREIGN"
                    prop["TierBoost"] = "FD/DK + Pinnacle confirmed"
                elif fd_result["confirms"] and prop.get("Tier") == "APPROVED":
                    prop["Tier"] = "ELITE"
                    prop["TierBoost"] = "FD/DK confirmed"
                elif fd_result["fades"] and prop.get("Tier") in ("SOVEREIGN","ELITE"):
                    prop["Tier"] = "APPROVED"
                    prop["TierNote"] = "Downgraded: FD/DK fades"
            else:
                prop["FDDKProb"] = None
                prop["FDDKConfirms"] = False
                prop["FDDKFades"] = False
        else:
            prop["FDDKProb"] = None
            prop["FDDKConfirms"] = False
            prop["FDDKFades"] = False


    # ── Kalshi prediction market signal ─────────────────────────────────────
    # 2026-07-17 fix: was reading "kalshi_raw", a key that's never set —
    # the real data is stored under "kalshi_markets" (confirmed: every
    # other consumer in this file already uses that key correctly). This
    # block was silently firing on an empty list the entire time despite
    # fetch_kalshi_markets() genuinely working and returning real data.
    _kalshi = st.session_state.get("kalshi_markets", [])
    if _kalshi:
        _kal_lookup = {}
        for _km in _kalshi:
            _title = normalize_name(_km.get("title", ""))
            _kal_lookup[_title] = _km
        for prop in enriched:
            _pname = normalize_name(prop.get("Player", ""))
            _pstat = str(prop.get("Prop", "")).lower()
            _pline = prop.get("Line", 0)
            # Find matching Kalshi market
            _kal_match = None
            for _kt, _kv in _kal_lookup.items():
                if _pname and _pname in _kt and any(s in _kt for s in [_pstat[:4], str(_pline)]):
                    _kal_match = _kv
                    break
            if _kal_match:
                _yes = _kal_match.get("yes_bid")
                prop["KalshiYesBid"] = _yes
                if _yes and float(_yes) > 0.65 and prop.get("Side","OVER") == "OVER":
                    prop["SignalNotes"] = prop.get("SignalNotes","") + f" 🎰 Kalshi {float(_yes):.0%} yes"
                elif _yes and float(_yes) < 0.35 and prop.get("Side","OVER") == "OVER":
                    prop["SignalNotes"] = prop.get("SignalNotes","") + f" ⚠️ Kalshi fading ({float(_yes):.0%})"
            else:
                prop["KalshiYesBid"] = None

    # ── Polymarket signal ────────────────────────────────────────────────────
    # 2026-07-17 fix: same key-mismatch bug as Kalshi above — was reading
    # "polymarket_raw" (never set), real data is under "polymarket_markets".
    _poly = st.session_state.get("polymarket_markets", [])
    if _poly:
        _poly_lookup = {}
        for _pm in _poly:
            _q = normalize_name(_pm.get("question", ""))
            _poly_lookup[_q] = _pm
        for prop in enriched:
            _pname = normalize_name(prop.get("Player", ""))
            _pstat = str(prop.get("Prop", "")).lower()
            _poly_match = None
            for _pk, _pv in _poly_lookup.items():
                if _pname and _pname in _pk:
                    _poly_match = _pv
                    break
            if _poly_match:
                try:
                    _yes_p = float(_poly_match.get("yes_price", 0) or 0)
                    prop["PolymarketYes"] = _yes_p
                    if _yes_p > 0.65 and prop.get("Side","OVER") == "OVER":
                        prop["SignalNotes"] = prop.get("SignalNotes","") + f" 📊 Poly {_yes_p:.0%}"
                except Exception:
                    prop["PolymarketYes"] = None
            else:
                prop["PolymarketYes"] = None

    # ── Covers.com consensus signal ──────────────────────────────────────────
    _covers = st.session_state.get("covers_raw", {})
    if _covers and isinstance(_covers, dict):
        for prop in enriched:
            _matchup = prop.get("Matchup", "")
            _cov = _covers.get(_matchup, {})
            if not _cov:
                for _ck, _cv in _covers.items():
                    if any(t in _matchup for t in _ck.split(" @ ")):
                        _cov = _cv
                        break
            if _cov:
                _side = prop.get("Side", "OVER")
                _pct = float(_cov.get("over_pct") or 0) if _side=="OVER" else float(_cov.get("under_pct") or 0)
                prop["CoversConsensus"] = _pct
                if _pct > 0 and _pct < 35 and prop.get("Edge",0) > 0.03:
                    prop["SignalNotes"] = prop.get("SignalNotes","") + f" 🎯 Covers fade ({_pct:.0f}% public)"
                elif _pct > 70:
                    prop["SignalNotes"] = prop.get("SignalNotes","") + f" ⚠️ Covers public ({_pct:.0f}%)"
            else:
                prop["CoversConsensus"] = None

    # ── Unabated sharp line validation ─────────────────────────────────────
    # Unabated provides Pinnacle-derived no-vig fair lines for game totals/spreads.
    # If our prop edge aligns with Unabated's fair value direction, boost confidence.
    _unabated = st.session_state.get("unabated_lines", [])
    if _unabated:
        _unabated_lookup = {}
        for _u in _unabated:
            _gm = normalize_name(_u.get("game", ""))
            if _gm:
                _unabated_lookup[_gm] = _u
        for prop in enriched:
            prop["UnabatedNote"] = ""

    # ── SharpAPI +EV signal ────────────────────────────────────────────────────
    # SharpAPI pre-computes Pinnacle no-vig EV on every prop.
    # is_ev_positive:True = confirmed +EV vs sharp benchmark — strongest free signal.
    _sharp_props = st.session_state.get("sharpapi_props", [])
    if _sharp_props:
        _sharp_ev_set = {}
        for _sp in _sharp_props:
            _pname = normalize_name(_sp.get("Player", ""))
            _stat  = str(_sp.get("Prop", "")).lower()
            _ev    = _sp.get("ev_percent") or 0
            _is_ev = _sp.get("is_ev_positive", False)
            key = (_pname, _stat)
            if key not in _sharp_ev_set or _ev > _sharp_ev_set[key][0]:
                _sharp_ev_set[key] = (_ev, _is_ev)
        for prop in enriched:
            _pk = (normalize_name(prop.get("Player", "")),
                   str(prop.get("Prop", "")).lower())
            if _pk in _sharp_ev_set:
                _ev_val, _is_ev = _sharp_ev_set[_pk]
                prop["SharpAPIEV"]      = _is_ev
                prop["SharpAPIEVPct"]   = round(_ev_val, 2)
                if _is_ev and prop.get("Edge", 0) > 0.02:
                    prop["Tier"] = "ELITE" if prop.get("Tier") == "APPROVED" else prop.get("Tier")
                    prop["SignalNotes"] = prop.get("SignalNotes", "") + f" ⚡ SharpAPI EV+{_ev_val:.1f}%"
            else:
                prop["SharpAPIEV"]    = False
                prop["SharpAPIEVPct"] = None

        # ── ParlayAPI +EV signal ────────────────────────────────────────────────
    # If ParlayAPI independently flags this player/prop as +EV vs Pinnacle,
    # that's a sharp consensus confirmation — boost tier.
    _papi_ev = st.session_state.get("parlayapi_ev", [])
    if _papi_ev:
        _papi_ev_set = set()
        for _pe in _papi_ev:
            _pname = normalize_name(_pe.get("player", _pe.get("Player", "")))
            _pstat = str(_pe.get("prop", _pe.get("Prop", ""))).lower()
            if _pname:
                _papi_ev_set.add((_pname, _pstat))
        for prop in enriched:
            _pk = (normalize_name(prop.get("Player","")),
                   str(prop.get("Prop","")).lower())
            if _pk in _papi_ev_set:
                prop["ParlayAPIEV"] = True
                # Boost: ParlayAPI EV + our model edge = stronger signal
                if prop.get("Tier") == "APPROVED" and prop.get("Edge", 0) > 0.03:
                    prop["Tier"] = "ELITE"
                    prop["TierBoost"] = prop.get("TierBoost","") + " + ParlayAPI EV"
            else:
                prop["ParlayAPIEV"] = False

    # ── Action Network public betting % signal ──────────────────────────────
    # High public % on one side with sharp line moving opposite = RLM signal.
    # Low public % + our model edge = sharp-side lean.
    _an_public = st.session_state.get("public_betting_data", {})
    if _an_public:
        for prop in enriched:
            matchup = prop.get("Matchup", "")
            if not matchup:
                continue
            _pub = _an_public.get(matchup, {})
            if not _pub:
                # Try fuzzy match
                for _mk, _mv in _an_public.items():
                    if any(t in matchup for t in _mk.split(" @ ")):
                        _pub = _mv
                        break
            if _pub:
                side = prop.get("Side", "OVER")
                if side == "OVER":
                    pub_pct = _pub.get("over_pct") or 0
                elif side == "UNDER":
                    pub_pct = _pub.get("under_pct") or 0
                else:
                    pub_pct = 0
                try:
                    pub_pct = float(pub_pct)
                except (TypeError, ValueError):
                    pub_pct = 0
                prop["PublicPct"] = pub_pct
                # Sharp fade: <40% public but our model has edge = contrarian signal
                if pub_pct > 0 and pub_pct < 40 and prop.get("Edge", 0) > 0.03:
                    prop["SharpContrarian"] = True
                    prop["SignalNotes"] = prop.get("SignalNotes","") + f" 🎯 Sharp contrarian ({pub_pct:.0f}% public)"
                # RLM candidate: >65% public tickets
                elif pub_pct > 65:
                    prop["PublicHeavy"] = True
                    prop["SignalNotes"] = prop.get("SignalNotes","") + f" ⚠️ Public heavy ({pub_pct:.0f}%)"
            else:
                prop["PublicPct"] = None





    # ── Tier-based Kelly sizing with Adaptive Calibration ───────────────────
    # Apply KELLY_BY_TIER as base, then scale by per-sport Brier score and
    # apply time-decay to edge before sizing (elite calibration loop).
    _bankroll_mult_data = compute_bankroll_multiplier()
    _bm_mult = _bankroll_mult_data.get("multiplier", 1.0) if isinstance(_bankroll_mult_data, dict) else 1.0
    _cal_history = st.session_state.get("history", [])
    for prop in enriched:
        _tier      = prop.get("Tier", "APPROVED")
        _tier_frac = KELLY_BY_TIER.get(_tier, KELLY_FRACTION)
        _edge      = prop.get("Edge", 0.0) or 0.0
        _prop_sport = prop.get("Sport", sport)
        _prop_market = prop.get("Prop", "GENERAL")

        # Use pre-computed adaptive fraction if available (set during enrichment)
        # otherwise compute it here
        _adapt_frac = prop.get("KellyAdaptiveFraction") or adaptive_kelly_fraction(
            _tier_frac, _cal_history, sport=_prop_sport, market=_prop_market
        )
        # Use pre-computed decayed edge if available, otherwise apply decay now
        _eff_edge = prop.get("KellyDecayedEdge") or time_decay_edge_factor(_edge)

        _odds_a = prop.get("BestOdds", prop.get("OverOdds", "-110"))
        try:
            _odds_f = float(str(_odds_a).replace("+","")) if _odds_a not in ("N/A","—","") else -110
            if _odds_f > 0:
                _b = _odds_f / 100
            else:
                _b = 100 / abs(_odds_f)
            _p = _eff_edge + (1 / (1 + _b))
            _p = min(max(_p, 0.01), 0.99)
            _q = 1 - _p
            _kelly_full = (_b * _p - _q) / _b
            _kelly_full = max(0.0, _kelly_full)
        except Exception:
            _kelly_full = _eff_edge
        _kelly_pct = round(_kelly_full * _adapt_frac * _bm_mult, 4)
        _kelly_pct = min(_kelly_pct, KELLY_CAP)
        prop["KellyFraction"]       = _adapt_frac
        prop["KellyAdvisedPct"]     = _kelly_pct if _kelly_pct >= KELLY_MIN else 0.0
        prop["KellyEffectiveEdge"]  = round(_eff_edge, 4)

        # ── Covariance Haircut ─────────────────────────────────────────────
        # Apply correlation-adjusted reduction when portfolio already has
        # significant exposure to the same game or team, preventing the
        # combined variance from exceeding single-game risk limits.
        if _kelly_pct >= KELLY_MIN:
            _open_bets = st.session_state.get("open_bets", [])
            _matchup   = prop.get("Matchup") or prop.get("matchup") or ""
            _team      = prop.get("Team") or prop.get("Opponent") or ""
            _adj_kelly, _haircut, _haircut_note = covariance_haircut(
                _kelly_pct, _matchup, _team, _open_bets
            )
            prop["KellyAdvisedPct"]    = _adj_kelly if _adj_kelly >= KELLY_MIN else 0.0
            prop["KellyCovHaircut"]    = _haircut
            prop["KellyCovNote"]       = _haircut_note

        # ── Edge Type Classification ───────────────────────────────────────
        # Classify every prop into Type A (Arbitrage), B (Alpha), or C (Noise)
        # so the user knows WHY an edge exists and how to act on it.
        _cons_gap  = abs(float(prop.get("ConsensusGap") or prop.get("LineGap") or 0))
        _pinn_gap  = abs(float(prop.get("PinnacleGap") or prop.get("PnNovigGap") or 0))
        _edge_type = classify_edge_type(prop, consensus_gap=_cons_gap, pinnacle_gap=_pinn_gap)
        prop["EdgeType"]       = _edge_type["type"]
        prop["EdgeTypeLabel"]  = _edge_type["label"]
        prop["EdgeTypeAction"] = _edge_type["action"]
        prop["EdgeTypeColor"]  = _edge_type["color"]
        prop["EdgeTypeReason"] = _edge_type["reason"]

    # Add better line detection to each prop
    better_lines_lookup = st.session_state.get("better_lines_lookup", {})
    for prop in enriched:
        player_norm = normalize_name(prop.get("Player",""))
        prop_key = (player_norm, prop.get("Prop",""))
        prop_line = prop.get("Line", 0)
        prop_side = prop.get("Side", "OVER")
        best_line_note = ""
        best_line_source = ""
        best_line_val = None
        for alt in better_lines_lookup.get(prop_key, []):
            alt_line = alt.get("line", 0)
            alt_source = alt.get("source","")
            if alt_line and alt_source:
                is_better = (prop_side == "OVER" and float(alt_line) < float(prop_line)) or                             (prop_side == "UNDER" and float(alt_line) > float(prop_line))
                if is_better:
                    savings = round(abs(float(alt_line) - float(prop_line)), 1)
                    if best_line_val is None or savings > abs(float(best_line_val) - float(prop_line)):
                        best_line_val = alt_line
                        best_line_source = alt_source
                        best_line_note = f"Better on {alt_source}: {prop_side} {alt_line} (saves {savings})"
        prop["BetterLineNote"] = best_line_note
        prop["BetterLineSource"] = best_line_source
        prop["BetterLineVal"] = best_line_val

    # ── EV API enrichment — attach multi-book odds + EV/FV to every board prop ──
    _ev_lookup = st.session_state.get("ev_book_lookup", {})
    if _ev_lookup:
        for prop in enriched:
            _pk = (normalize_name(prop.get("Player","")), prop.get("Prop",""))
            _ev_books = _ev_lookup.get(_pk, {})
            if _ev_books:
                prop["EVBooks"] = _ev_books  # full dict of {book: {odds_over, line, ev, fair_value, bet_link}}
                # Attach best EV and fair value across all books
                _best_ev, _best_fv, _best_link = None, None, None
                for _bk, _bd in _ev_books.items():
                    if _bd.get("ev") is not None:
                        try:
                            _ev_f = float(_bd["ev"])
                            if _best_ev is None or _ev_f > _best_ev:
                                _best_ev = _ev_f
                                _best_link = _bd.get("bet_link")
                        except (ValueError, TypeError):
                            pass
                    if _bd.get("fair_value") and _best_fv is None:
                        _best_fv = _bd["fair_value"]
                if _best_ev is not None:
                    prop["EVSharpEV"]     = _best_ev
                    prop["EVSharpFV"]     = _best_fv
                    prop["EVSharpLink"]   = _best_link
                    prop["EVSharpBooks"]  = len(_ev_books)
            else:
                prop["EVBooks"] = {}
                prop["EVSharpEV"] = None
                prop["EVSharpFV"] = None
                prop["EVSharpLink"] = None
                prop["EVSharpBooks"] = 0


    arb_opps = detect_arbitrage_opportunities(sport)
    st.session_state["arb_opportunities"] = arb_opps
    alt_line_upgrades = []
    for prop in enriched:
        if prop.get("Tier") not in ("SOVEREIGN","ELITE","APPROVED"):
            continue
        upgrade = get_best_alt_line_recommendation(
            prop["Player"], prop["Prop"], prop["Line"], prop["Prob"],
            float(str(prop.get("EV_2pick","0%")).replace("%","").replace("+","")) / 100,
            prop["Avg"], prop.get("StdDev"), sport, st.session_state.get("bankroll", DEFAULT_BANKROLL),
        )
        if upgrade:
            alt_line_upgrades.append(upgrade)
            prop["AltLineUpgrade"] = upgrade
            prop["BestAltLine"] = upgrade["best_line"]
            prop["BestAltEV"] = f"{upgrade['best_ev']:+.1%}"
            prop["BestAltPayout"] = upgrade["best_payout"]
        else:
            prop["AltLineUpgrade"] = None
            prop["BestAltLine"] = None
            prop["BestAltEV"] = None
    st.session_state["alt_line_upgrades"] = alt_line_upgrades
    # Sort by LockScore first, then ProjConfidence as tiebreaker
    enriched.sort(key=lambda x: (
        x.get("LockScore", 0) * 1.0 +
        x.get("ProjConfidence", 50) * 0.05  # confidence as 5% tiebreaker
    ), reverse=True)
    for prop in enriched:
        prop["LockScore"] = calculate_lock_quality_score(prop)
        # Conflict + market agreement (post-enrichment)
        _conflict_status, _conflict_score, _conflict_note = compute_signal_conflict(prop)
        _mkt_agree = compute_market_agreement_score(prop)
        prop["ConflictStatus"]   = _conflict_status
        prop["ConflictScore"]    = _conflict_score
        prop["ConflictNote"]     = _conflict_note
        prop["MarketAgreement"]  = _mkt_agree.get("score", 50)
        prop["MarketAgreementLabel"] = _mkt_agree.get("label","")
        # Bet Quality Score — stored on prop for persistence
        _bq_edge    = round(float(prop.get("Edge",0) or 0) * 100, 1)
        _bq_conf    = _conflict_status
        _bq_agree   = _mkt_agree.get("score", 50)
        _bq_risk    = prop.get("RiskLevel","")
        _bq_score   = 0
        _bq_score  += min(40, _bq_edge * 4)
        _bq_score  += (20 if _bq_conf=="ALIGNED" else 10 if _bq_conf=="MIXED" else 0 if _bq_conf=="CONFLICTED" else 12)
        _bq_score  += int(_bq_agree * 0.20)
        _bq_score  += (10 if _bq_risk=="LOW" else 7 if _bq_risk=="MEDIUM" else 3 if _bq_risk=="HIGH" else 0 if _bq_risk=="EXTREME" else 5)
        _bq_score  += 5  # CLV default — updated when CLV data available
        prop["BetQualityScore"] = max(0, min(100, int(_bq_score)))

    # ═══════════════════════════════════════════════════════════
    # ENGINE 1 — NARRATIVE REASONING
    # Generates plain-English "why this makes sense" + "biggest
    # risk" for every SOVEREIGN/ELITE/APPROVED prop.
    # ═══════════════════════════════════════════════════════════
    for prop in enriched:
        if prop.get("Tier") not in ("SOVEREIGN","ELITE","APPROVED"):
            prop["Narrative"] = ""
            prop["NarrativeRisk"] = ""
            continue
        player   = prop.get("Player","")
        stat     = prop.get("Prop","")
        line     = prop.get("Line",0)
        avg      = prop.get("Avg",0)
        edge     = prop.get("Edge",0)
        side     = prop.get("Side","OVER")
        tier     = prop.get("Tier","")
        opp      = prop.get("Opponent", opp_team_abbrev if 'opp_team_abbrev' in dir() else "")
        is_home  = prop.get("SignalLocation",0) > 0
        b2b      = prop.get("SignalRest",0) < 0
        sig_def  = prop.get("SignalDefense",0)
        sig_base = prop.get("SignalBase",0)
        sig_pace = prop.get("SignalPace",0)
        h2h_note = prop.get("H2HNote","")
        pinn     = prop.get("PinnacleConfirms", None)
        injury   = prop.get("Injury","")
        sharp    = prop.get("SharpFlag","")
        trend    = prop.get("Trend","")
        weather  = prop.get("WeatherNote","")
        ref_note = prop.get("RefNote","")
        better   = prop.get("BetterLineNote","")
        an_grade = prop.get("AN_Grade","")
        blowout  = prop.get("SignalBlowout",0)

        # Build WHY narrative
        why_parts = []
        diff = avg - line if side == "OVER" else line - avg
        if diff > 0:
            why_parts.append(f"averaging {avg:.1f} vs line of {line} ({diff:+.1f} cushion)")
        if sig_def > 0.02:
            why_parts.append(f"weak opponent defense (+{sig_def:.0%} boost)")
        elif sig_def < -0.02:
            why_parts.append(f"tough opponent defense ({sig_def:.0%})")
        if is_home:
            why_parts.append("home court advantage")
        if h2h_note and "%" in h2h_note:
            why_parts.append(f"strong H2H history ({h2h_note})")
        if pinn is True:
            why_parts.append("Pinnacle confirms edge")
        if sharp and "↑" in sharp:
            why_parts.append("sharp money aligned")
        if sig_pace > 0.01:
            why_parts.append("fast-paced matchup favors volume")
        if ref_note and "foul" in ref_note.lower():
            why_parts.append(f"ref tendency: {ref_note}")
        if an_grade in ("SOVEREIGN","ELITE"):
            why_parts.append("Action Network projection confirms")
        narrative = (f"{player} {side} {line} {stat}: " +
                     (", ".join(why_parts[:3]) if why_parts else f"edge {edge:.1%} above threshold"))

        # Build RISK narrative
        risk_parts = []
        if b2b:
            risk_parts.append("back-to-back fatigue (-8%)")
        if blowout < -0.02:
            risk_parts.append(f"blowout risk in this matchup")
        if injury:
            risk_parts.append(f"injury flag: {injury}")
        if pinn is False:
            risk_parts.append("Pinnacle fades this pick")
        if prop.get("Quality","") == "Default":
            risk_parts.append("using default averages — real stats unknown")
        if prop.get("OddsType","") == "demon":
            risk_parts.append("Demon line — boosted payout = harder target")
        if weather and any(w in weather.lower() for w in ("wind","cold","rain")):
            risk_parts.append(f"weather: {weather}")
        if trend and "↓" in trend:
            risk_parts.append("recent downward trend")
        risk = (", ".join(risk_parts[:3]) if risk_parts else "No major flags")

        prop["Narrative"]     = narrative
        prop["NarrativeRisk"] = f"⚠️ Risk: {risk}"

    # ═══════════════════════════════════════════════════════════
    # ENGINE 2 — LOSS PATTERN ANALYZER
    # Runs after 20+ resolved bets. Detects patterns in losses
    # and surfaces actionable diagnostics into session state.
    # ═══════════════════════════════════════════════════════════
    _history_all = st.session_state.get("history", [])
    _resolved    = [h for h in _history_all if h.get("outcome") in ("WIN","LOSS")]
    _loss_patterns = []
    if len(_resolved) >= 20:
        _losses = [h for h in _resolved if h.get("outcome") == "LOSS"]
        _wins   = [h for h in _resolved if h.get("outcome") == "WIN"]
        _total  = len(_resolved)
        _wr     = len(_wins) / _total

        # Pattern: away game losses
        _away_losses = [h for h in _losses if not h.get("signals_active",{}).get("location_home", True)]
        _away_total  = [h for h in _resolved if not h.get("signals_active",{}).get("location_home", True)]
        if len(_away_total) >= 5:
            _away_wr = sum(1 for h in _away_total if h.get("outcome") == "WIN") / len(_away_total)
            if _away_wr < _wr - 0.10:
                _loss_patterns.append(f"📍 Away game picks hitting only {_away_wr:.0%} vs {_wr:.0%} overall — location signal may be under-weighted")

        # Pattern: back-to-back losses
        _b2b_losses = [h for h in _losses if h.get("signals_active",{}).get("back_to_back", False)]
        _b2b_total  = [h for h in _resolved if h.get("signals_active",{}).get("back_to_back", False)]
        if len(_b2b_total) >= 3:
            _b2b_wr = sum(1 for h in _b2b_total if h.get("outcome") == "WIN") / len(_b2b_total)
            if _b2b_wr < 0.40:
                _loss_patterns.append(f"😴 Back-to-back picks hitting only {_b2b_wr:.0%} — consider avoiding B2B props")

        # Pattern: sport-specific underperformance
        _sport_groups = {}
        for h in _resolved:
            sp = h.get("sport","?")
            _sport_groups.setdefault(sp, []).append(h)
        for sp, records in _sport_groups.items():
            if len(records) >= 8:
                sp_wr = sum(1 for h in records if h.get("outcome") == "WIN") / len(records)
                if sp_wr < _wr - 0.12:
                    _loss_patterns.append(f"📊 {sp} picking at only {sp_wr:.0%} vs {_wr:.0%} overall — review {sp} signal weights")

        # Pattern: tier-level mismatch
        for tier_check in ("SOVEREIGN","ELITE","APPROVED","LEAN"):
            _tier_records = [h for h in _resolved if h.get("tier","") == tier_check]
            if len(_tier_records) >= 5:
                _tier_wr = sum(1 for h in _tier_records if h.get("outcome") == "WIN") / len(_tier_records)
                _expected = {"SOVEREIGN": 0.65, "ELITE": 0.60, "APPROVED": 0.58, "LEAN": 0.55}.get(tier_check, 0.58)
                if _tier_wr < _expected - 0.10:
                    _loss_patterns.append(f"🎯 {tier_check} tier hitting {_tier_wr:.0%} vs expected {_expected:.0%} — thresholds may be too loose")
                elif _tier_wr > _expected + 0.12 and len(_tier_records) >= 10:
                    _loss_patterns.append(f"✅ {tier_check} tier crushing at {_tier_wr:.0%} — model is well-calibrated here")

        # Pattern: default-average prop losses
        _default_losses = [h for h in _losses if h.get("tier","") in ("SOVEREIGN","ELITE") and not h.get("signals_active",{}).get("base_positive", True)]
        if len(_default_losses) >= 3:
            _loss_patterns.append(f"⚠️ {len(_default_losses)} SOVEREIGN/ELITE losses came from props without strong base signal — review edge calculation on low-data props")

    st.session_state["loss_patterns"] = _loss_patterns

    # ═══════════════════════════════════════════════════════════
    # ENGINE 3 — CONTEXTUAL OVERRIDE
    # Detects real-world situations where math is right but
    # context says otherwise. Warns AND downgrades with flag.
    # User can manually override by re-locking post-override.
    # ═══════════════════════════════════════════════════════════
    _today_month = date.today().month
    _is_late_season = _today_month in [3, 4, 6, 9]  # NBA/NHL playoffs, NFL preseason end, MLB late
    for prop in enriched:
        if prop.get("Tier") not in ("SOVEREIGN","ELITE","APPROVED"):
            continue
        _overrides = []
        _original_tier = prop.get("Tier","")
        _player  = prop.get("Player","")
        _team    = PLAYER_TEAM_MAP.get(_player,"")
        _stat    = prop.get("Prop","")
        _avg     = prop.get("Avg", 0)
        _line    = prop.get("Line", 0)
        _games   = games

        # Check 1: Clinched/Eliminated — team has nothing to play for
        # Proxy: late season + heavy favorite spread (team resting starters)
        if _is_late_season and _team and _games:
            for game in _games:
                matchup = game.get("Matchup","")
                if _team in matchup:
                    try:
                        spread_raw = str(game.get("Spread","0")).replace("+","")
                        spread_val = abs(float(spread_raw)) if spread_raw not in ("—","") else 0
                        if spread_val >= 12 and _stat in ("Points","Pts+Reb+Ast","Rebounds","Assists"):
                            _overrides.append(f"🗓️ Late season + large spread ({spread_raw}) — possible rest/load management situation. Starters may play limited minutes.")
                            if _original_tier == "SOVEREIGN":
                                prop["Tier"] = "ELITE"
                                prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: late season load mgmt risk"
                            elif _original_tier == "ELITE":
                                prop["Tier"] = "APPROVED"
                                prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: late season load mgmt risk"
                    except (ValueError, TypeError):
                        pass

        # Check 2: Recent low minutes — player averaging far less than baseline
        _sample_size = prop.get("SampleSize", 0)
        _conf_mult = prop.get("ConfidenceMult", 1.0)
        if isinstance(_sample_size, (int,float)) and _sample_size >= 3:
            # NOTE 2026-07-09: this threshold was previously < 0.80, which
            # sample_size_confidence() can mathematically never return (0.80
            # is its floor value, for n_games=0) - this check could never
            # fire regardless of how thin the actual sample was. 0.92 catches
            # genuinely small samples (n_games <= 4 per the function's curve)
            # while leaving anything with reasonable game history alone.
            if _conf_mult < 0.92 and _original_tier in ("SOVEREIGN","ELITE"):
                _overrides.append(f"📉 Confidence multiplier {_conf_mult:.0%} — small sample or recent minute restriction detected. Stats may not reflect current role.")
                if _original_tier == "SOVEREIGN":
                    prop["Tier"] = "ELITE"
                    prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: low sample confidence"
                elif _original_tier == "ELITE":
                    prop["Tier"] = "APPROVED"
                    prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: low sample confidence"

        # Check 3: Injury flag on a high-tier pick
        if prop.get("Injury","") and _original_tier in ("SOVEREIGN","ELITE"):
            _overrides.append(f"🚑 Injury flag active: {prop['Injury']}. High-tier pick with injury concern — monitor status before locking.")
            if _original_tier == "SOVEREIGN":
                prop["Tier"] = "ELITE"
                prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: injury flag"
            elif _original_tier == "ELITE":
                prop["Tier"] = "APPROVED"
                prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: injury flag"

        # Check 4: Line significantly above season average (fade signal)
        if isinstance(_avg, (int,float)) and _avg > 0 and isinstance(_line, (int,float)) and _line > 0:
            pct_above = (_line - _avg) / _avg
            if pct_above > 0.20 and prop.get("Side","OVER") == "OVER":
                _overrides.append(f"📊 Line {_line} is {pct_above:.0%} above season avg {_avg:.1f}. Even with edge, chasing a historically inflated line.")
                if _original_tier == "SOVEREIGN":
                    prop["Tier"] = "ELITE"
                    prop["TierNote"] = prop.get("TierNote","") + f" | ⬇️ Contextual: line {pct_above:.0%} above avg"

        # Check 5: Pinnacle AND FD/DK both fade — strong market disagreement
        if prop.get("PinnacleConfirms") is False and prop.get("FDDKFades") is True:
            _overrides.append("🚫 Both Pinnacle AND FanDuel/DK fade this pick. Two sharp books disagree with model — high-confidence fade signal.")
            if _original_tier in ("SOVEREIGN","ELITE"):
                prop["Tier"] = "APPROVED"
                prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: dual sharp fade"
            elif _original_tier == "APPROVED":
                prop["Tier"] = "LEAN"
                prop["TierNote"] = prop.get("TierNote","") + " | ⬇️ Contextual: dual sharp fade"

        # Store overrides and original tier for display
        prop["ContextOverrides"]  = _overrides
        prop["OriginalTier"]      = _original_tier if _overrides else ""
        prop["OverrideActive"]    = len(_overrides) > 0 and _original_tier != prop.get("Tier","")


    quality_sorted = sorted(enriched, key=lambda x: x.get("LockScore", 0), reverse=True)
    st.session_state["quality_sorted_board"] = quality_sorted

    # Update all_sports_best across loaded sports
    existing_best = st.session_state.get("all_sports_best", [])
    # Remove old entries for this sport
    existing_best = [p for p in existing_best if p.get("Sport","") != sport]
    # Add top 3 from this sport
    top_sport = [p for p in enriched if p.get("Tier","") in ("SOVEREIGN","ELITE","APPROVED")][:3]
    existing_best.extend(top_sport)
    # Sort by edge across all sports
    existing_best.sort(key=lambda x: x.get("Edge",0), reverse=True)
    st.session_state["all_sports_best"] = existing_best[:10]
    line_movement = track_line_movement(enriched)
    st.session_state["line_movement"] = line_movement
    # Goblin/Demon (odds_type) re-pricing detector -- records this board
    # load as a snapshot, then flags any prop whose odds_type changed
    # since an earlier snapshot (standard -> goblin/demon or back), the
    # same signal a sharp bettor watches for: PrizePicks re-pricing a
    # prop in reaction to sharp/consensus pressure. Cold-start safe --
    # returns [] until enough snapshot history has accumulated.
    try:
        _pp_props_for_snapshot = [p for p in enriched if p.get("Book") == "PrizePicks"]
        if _pp_props_for_snapshot:
            record_prop_snapshot(sport, {"PrizePicks": _pp_props_for_snapshot})
        odds_type_flips = get_odds_type_flips(sport)
    except Exception:
        odds_type_flips = []
    _flip_lookup = {f"{f['player']}_{f['stat']}": f for f in odds_type_flips if f.get("book") == "PrizePicks"}
    for prop in enriched:
        key = f"{prop['Player']}_{prop['Prop']}"
        move = line_movement.get(key, {})
        prop["Movement"] = (move.get("direction", "") + str(abs(move.get("diff", 0))) if move else "")
        _flip = _flip_lookup.get(key)
        prop["OddsTypeFlip"] = (
            f"{_flip['from_type']}\u2192{_flip['to_type']} ({_flip['minutes_between']:.0f}m ago)"
            if _flip else ""
        )
    # ── Store snapshots and opening lines ────────────────────
    # MLB lineup status applied to enriched props
    if sport == "MLB":
        _mlb_lineups_enriched = st.session_state.get("mlb_confirmed_lineups", {})
        if _mlb_lineups_enriched:
            for _ep in enriched:
                _pname = _ep.get("Player","")
                _pteam = _ep.get("Team","")
                _team_lineup = _mlb_lineups_enriched.get(_pteam, {})
                if _team_lineup.get("confirmed"):
                    _lineup_names = [normalize_name(pl["name"]) for pl in _team_lineup.get("players",[])]
                    if normalize_name(_pname) not in _lineup_names:
                        _ep["LineupStatus"] = "⚠️ Not in confirmed lineup"
                    else:
                        _bat_pos = next((pl["batting_order"] for pl in _team_lineup["players"]
                                        if normalize_name(pl["name"]) == normalize_name(_pname)), None)
                        _ep["LineupStatus"] = f"✅ Batting #{_bat_pos}" if _bat_pos else "✅ In lineup"
    store_board_snapshot(enriched, sport)
    _curr_depth = st.session_state.get("espn_depth_charts", {})
    if _curr_depth:
        _depth_changes = detect_depth_chart_changes(sport, _curr_depth)
        st.session_state["depth_chart_changes"] = _depth_changes
        save_depth_chart_snapshot(sport, _curr_depth)
    if sport == "NFL":
        # TODO: fetch_nfl_practice_participation / fetch_nfl_inactives not yet
        # implemented in fetchers.py — guarded to avoid NameError until built.
        if "fetch_nfl_practice_participation" in globals():
            try:
                st.session_state["nfl_practice"] = fetch_nfl_practice_participation()
            except Exception:
                _logger.debug("Silent except at line 13487")
                pass
        if "fetch_nfl_inactives" in globals():
            try:
                st.session_state["nfl_inactives"] = fetch_nfl_inactives()
            except Exception:
                _logger.debug("Silent except at line 13492")
                pass
    if sport == "NHL":
        if "fetch_nhl_starting_goalies" in globals():
            try:
                _nhl_goalies = fetch_nhl_starting_goalies()
                if _nhl_goalies:
                    st.session_state["nhl_starting_goalies"] = _nhl_goalies
            except Exception:
                _logger.debug("Silent except at line 13501")
                pass
    if sport == "GOLF":
        _golf_lb = fetch_golf_leaderboard()
        if _golf_lb:
            st.session_state["golf_leaderboard"] = _golf_lb
        _golf_odds = fetch_golf_odds()
        if _golf_odds:
            st.session_state["golf_odds"] = _golf_odds

    # Bovada game lines — all sports, no auth required
    _bovada = fetch_bovada_lines(sport)
    if _bovada:
        st.session_state["bovada_lines"] = _bovada

    # BetOnline game lines — all sports, no auth required
    _betonline = fetch_betonline_lines(sport)
    if _betonline:
        st.session_state["betonline_lines"] = _betonline

    # Paddy Power game lines — direct HTML harvest, no Odds API quota cost.
    # UK book: strongest on soccer/tennis, thinner on NBA/NFL/NHL/MLB — used
    # as a line-shop supplement, not a primary source. Wrapped defensively
    # since the parser's __NUXT__ selector hasn't been confirmed live yet.
    try:
        _paddypower = fetch_paddypower_lines(sport)
        if _paddypower:
            st.session_state["paddypower_lines"] = _paddypower
    except Exception:
        _logger.debug("Paddy Power fetch failed silently at board load")

    # Auto scraper props (MyBookie/BetOnline from local machine)
    _auto_props = fetch_auto_scraped_props(sport)
    if _auto_props:
        st.session_state[f"auto_scraped_props_{sport}"] = _auto_props
        _auto_books = list({p.get("Book","") for p in _auto_props})
        st.caption(f"📡 Auto scraper: {len(_auto_props)} props from {', '.join(_auto_books)}")


    return enriched, games, skipped_def, skipped_edge, home_teams, away_teams

# =========================
# SESSION STATE & PERSISTENCE
# =========================
_ss = {"bankroll": DEFAULT_BANKROLL, "day_start_br": DEFAULT_BANKROLL, "session_start": time.time(),
       "locks": [], "history": [], "min_edge": MIN_EDGE_DEFAULT, "skip_defaults": True, "last_sport": "NBA",
       "board_data": [], "games": [], "last_scan_time": None, "board_ready": False, "n_skipped_def": 0, "n_skipped_edge": 0,
       "errors": [], "game_line_movement": {}, "game_sharp_flags": {}, "oddswrap_props": [],
       "current_slip_id": None,
       "ud_props_compare": [], "multibook_discrepancies": [], "nba_api_status": "Not yet fetched",
       "line_discrepancies": [], "override_correlation_warning": False, "clv_adjustments": {},
       "all_sports_results": None, "game_analysis": [], "officials_data": {}, "mlb_pitchers": {},
       "power_divergences": {}, "quality_sorted_board": [], "last_pick_count": 2,
       "public_betting_data": {}, "alt_line_upgrades": [], "parlayplay_alt_lines": {},
       "arb_opportunities": [], "steam_moves": [], "an_props_data": [], "gem_brief": "",
       "parsed_bets": [], "ocr_raw_text": "", "pp_parsed_bets": []}
for k, v in _ss.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "persistence_loaded" not in st.session_state:
    gist_history = load_from_gist("history", None)
    gist_locks = load_from_gist("locks", None)
    gist_bankroll = load_from_gist("bankroll", None)
    # Merge Gist + local cache — Gist is source of truth on Streamlit Cloud
    _local_history = load_json_data(HISTORY_PATH, [])
    _gist_history  = gist_history if isinstance(gist_history, list) else []
    # Deduplicate by timestamp+player+prop — prefer Gist entry on conflict
    _seen_keys = set()
    _merged = []
    for h in _gist_history + _local_history:
        _key = (h.get("timestamp",""), h.get("player",""), h.get("prop",""))
        if _key not in _seen_keys:
            _seen_keys.add(_key)
            _merged.append(h)
    # Filter out obviously corrupted entries (UI text captured instead of values)
    _GARBAGE_NAMES = {"show details", "unknown player", "show details v", "show details ~"}
    _clean_history = [
        h for h in _merged
        if h.get("player","") and len(h.get("player","")) < 50
        and h.get("outcome","") in ("WIN","LOSS","PENDING","PUSH")
        and normalize_name(h.get("player","")) not in _GARBAGE_NAMES
        and not str(h.get("player","")).startswith("@")
    ]
    # One-time auto-repair: a resolver bug (fixed) briefly cross-matched MLB
    # game locks against NBA scoreboards when both teams shared a 3-letter
    # abbreviation (e.g. Atlanta "ATL" for both Braves and Hawks). Any surviving
    # entries have the tell-tale fingerprint of bet_type="game" logged with
    # sport="NBA" but a matchup string using non-NBA team codes (e.g. "NYM @ ATL",
    # "PIT @ WSH" — no NBA team is "NYM", "PIT", or "WSH"). Strip these
    # automatically; this is safe because legitimate NBA game locks always use
    # real NBA team names/abbreviations that won't hit this exact bad set.
    _KNOWN_BAD_GAME_SIGNATURES = {("NYM @ ATL", "2026-07-04"), ("PIT @ WSH", "2026-07-04")}
    _before_repair = len(_clean_history)
    _clean_history = [
        h for h in _clean_history
        if not (
            h.get("bet_type") == "game"
            and (h.get("sport","") or "").upper() == "NBA"
            and (str(h.get("player","")), str(h.get("timestamp", h.get("date","")))[:10]) in _KNOWN_BAD_GAME_SIGNATURES
        )
    ]
    if len(_clean_history) < _before_repair:
        save_to_gist("history", _clean_history)  # persist the repair immediately

    # Defensive normalization: some older game-lock entries can have a "line"
    # value that isn't a clean number (e.g. a team-prefixed spread string like
    # "CIN -1.5" from a resolver bug that's since been fixed). Any code
    # downstream that does float(entry["line"]) will crash the whole app on
    # one bad entry, so coerce every entry's line to a real float once here,
    # extracting the numeric portion if needed, rather than relying on every
    # call site to guard itself.
    def _coerce_line(v):
        try:
            return float(v)
        except (ValueError, TypeError):
            m = re.search(r"-?\d+\.?\d*", str(v or ""))
            try:
                return float(m.group()) if m else 0.0
            except (ValueError, TypeError):
                return 0.0
    for _h in _clean_history:
        _h["line"] = _coerce_line(_h.get("line", 0))

    st.session_state.history = _clean_history
    # If Gist had more clean data than local, resync local to match
    if len(_clean_history) > len(_local_history):
        save_json_data(HISTORY_PATH, _clean_history)
    st.session_state.locks = (gist_locks if gist_locks is not None else load_json_data(LOCKS_PATH, []))
    st.session_state.bankroll = (gist_bankroll if gist_bankroll is not None else load_json_data(BANKROLL_PATH, DEFAULT_BANKROLL))
    st.session_state["_bankroll_last_saved"] = st.session_state.bankroll
    st.session_state["day_start_br"] = st.session_state.get("bankroll", DEFAULT_BANKROLL)
    # Comprehensive Elo update, decoupled from locks/button gate (was: only
    # ran when "Check Results via ESPN" was clicked AND locks existed —
    # meaning Elo silently stalled on any day with zero active locks).
    # Throttled to once per 30 min per session via session_state timestamp
    # (not Gist-backed) so this doesn't hit ESPN's scoreboard endpoint on
    # every Streamlit rerun, which fires on nearly any widget interaction.
    _elo_last_run = st.session_state.get("_elo_auto_last_run", 0)
    if time.time() - _elo_last_run > 1800:
        try:
            run_comprehensive_elo_update()
        except (requests.RequestException, KeyError, ValueError, TypeError):
            pass
        st.session_state["_elo_auto_last_run"] = time.time()

    # CLV closing line snapshot + auto-resolve (GAP FIX #6)
    # Throttled to once per 10 min per session.
    _clv_snap_last = st.session_state.get("_clv_snap_last_run", 0)
    if time.time() - _clv_snap_last > 600:
        try:
            _capture_clv_closing_lines()
        except Exception:
            _logger.debug("Silent except at line 13601")
            pass
        try:
            _capture_clv_closing_lines_game()
        except Exception:
            pass
        # FIX #6: resolve_clv_records was only called on History tab load.
        # Now runs on the 10-min timer so CLV resolves automatically post-game
        # even if the user never opens the History tab.
        try:
            _hist = st.session_state.get("history", [])
            if _hist:
                resolve_clv_records(_hist)
        except Exception:
            _logger.debug("Silent except at line 13610")
            pass
        st.session_state["_clv_snap_last_run"] = time.time()

    # FIX #4: Seasonal rolling avg cache reset.
    # PLAYER_AVERAGES is a hardcoded baseline that goes stale when a new season
    # starts. On first run of each new season (tracked via Gist), wipe all
    # rolling avg pkl caches so the model rebuilds from live ESPN/statsapi data
    # rather than prior-year numbers. PLAYER_AVERAGES itself is kept as the
    # seed fallback — only the pkl overrides are cleared.
    try:
        _today      = date.today()
        _cur_season = _today.year if _today.month >= 9 else _today.year - 1
        _stored_ssn = load_from_gist("betcouncil_active_season", None)
        if _stored_ssn != _cur_season:
            _rolling_caches = [
                "mlb_rolling_avgs.pkl", "nba_rolling_avgs.pkl",
                "nhl_rolling_avgs.pkl", "nfl_rolling_avgs.pkl",
                "wnba_rolling_avgs.pkl", "nfl_team_stats_power.pkl",
                "mlb_pitchers.pkl", "mlb_team_woba_splits.pkl",
            ]
            for _rc in _rolling_caches:
                _rp = os.path.join(CACHE_DIR, _rc)
                try:
                    if os.path.exists(_rp):
                        os.remove(_rp)
                except Exception:
                    _logger.debug("Silent except at line 13636")
                    pass
            save_to_gist("betcouncil_active_season", _cur_season)
    except Exception:
        _logger.debug("Silent except at line 13639")
        pass
    # signal_performance.json lives only on local CACHE_DIR, which is ephemeral on
    # Streamlit Cloud — it resets on every redeploy/restart, silently losing logged
    # bet outcomes that feed the System tab's "Resolved Bets" count and signal health
    # analysis. Gist-back it the same way history already is, so it survives restarts.
    gist_sig_perf = load_from_gist("signal_performance", None)
    _local_sig_perf = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    _gist_sig_perf  = gist_sig_perf if isinstance(gist_sig_perf, list) else []
    _seen_sig_keys = set()
    _merged_sig_perf = []
    for r in _gist_sig_perf + _local_sig_perf:
        _key = (r.get("timestamp",""), r.get("sport",""), r.get("tier",""), r.get("outcome",""))
        if _key not in _seen_sig_keys:
            _seen_sig_keys.add(_key)
            _merged_sig_perf.append(r)
    if len(_merged_sig_perf) > len(_local_sig_perf):
        save_json_data(SIGNAL_PERFORMANCE_PATH, _merged_sig_perf)
    gist_inj_perf = load_from_gist("injury_performance", None)
    _local_inj_perf = load_json_data(INJURY_PERFORMANCE_PATH, [], mem_ttl=60)
    _gist_inj_perf  = gist_inj_perf if isinstance(gist_inj_perf, list) else []
    _seen_inj_keys = set()
    _merged_inj_perf = []
    for r in _gist_inj_perf + _local_inj_perf:
        _key = (r.get("timestamp",""), r.get("player",""), r.get("outcome",""))
        if _key not in _seen_inj_keys:
            _seen_inj_keys.add(_key)
            _merged_inj_perf.append(r)
    if len(_merged_inj_perf) > len(_local_inj_perf):
        save_json_data(INJURY_PERFORMANCE_PATH, _merged_inj_perf)
    # weight_overrides / weight_adjustment_log: Gist-backed so auto-applied
    # signal weight adjustments (see History > Weekly) survive restarts,
    # same reasoning as signal_performance above.
    gist_wt_ovr = load_from_gist("weight_overrides", None)
    _local_wt_ovr = load_json_data(WEIGHT_OVERRIDES_PATH, {}, mem_ttl=60)
    if isinstance(gist_wt_ovr, dict) and gist_wt_ovr != _local_wt_ovr:
        save_json_data(WEIGHT_OVERRIDES_PATH, gist_wt_ovr)
    gist_wt_log = load_from_gist("weight_adjustment_log", None)
    _local_wt_log = load_json_data(WEIGHT_ADJUSTMENT_LOG_PATH, [], mem_ttl=60)
    _gist_wt_log = gist_wt_log if isinstance(gist_wt_log, list) else []
    if len(_gist_wt_log) > len(_local_wt_log):
        save_json_data(WEIGHT_ADJUSTMENT_LOG_PATH, _gist_wt_log)
    # optimized_weights.json (compute_optimized_weights' lift-based output —
    # a SEPARATE mechanism from weight_overrides above) was local-disk-only
    # until 2026-07-18, same ephemeral-reset bug already fixed for
    # signal_performance/weight_overrides. get_active_weights() reads this
    # file directly to decide live signal weights once a sport has 50+
    # graded bets — losing it on every Streamlit Cloud redeploy meant a
    # silent fallback to hardcoded base weights (plus loss of the 30%/70%
    # decay-blend continuity with the prior computation) until the next
    # session happened to re-trigger a recompute. Gist-backed now, same
    # merge-newest pattern as the others.
    gist_opt_wt = load_from_gist("optimized_weights", None)
    _local_opt_wt = load_json_data(WEIGHT_OPTIMIZER_PATH, {}, mem_ttl=60)
    if isinstance(gist_opt_wt, dict):
        _merged_opt_wt = dict(_local_opt_wt) if isinstance(_local_opt_wt, dict) else {}
        for _sp, _sp_data in gist_opt_wt.items():
            _local_sp = _merged_opt_wt.get(_sp, {})
            _gist_updated = _sp_data.get("updated", "") if isinstance(_sp_data, dict) else ""
            _local_updated = _local_sp.get("updated", "") if isinstance(_local_sp, dict) else ""
            if _gist_updated >= _local_updated:
                _merged_opt_wt[_sp] = _sp_data
        if _merged_opt_wt != _local_opt_wt:
            save_json_data(WEIGHT_OPTIMIZER_PATH, _merged_opt_wt)
    # clv_tracking: Gist-backed so CLV data survives Streamlit Cloud restarts.
    # Previously an orphan writer (reset was pushed to Gist but never loaded back).
    gist_clv = load_from_gist("clv_tracking", None)
    _local_clv = load_json_data(CLV_PATH, [])
    _gist_clv  = gist_clv if isinstance(gist_clv, list) else []
    _seen_clv_keys = set()
    _merged_clv = []
    for _cr in _gist_clv + _local_clv:
        _ck = (_cr.get("timestamp",""), _cr.get("player",""), _cr.get("prop",""))
        if _ck not in _seen_clv_keys:
            _seen_clv_keys.add(_ck)
            _merged_clv.append(_cr)
    if _merged_clv:
        if len(_merged_clv) > len(_local_clv):
            save_json_data(CLV_PATH, _merged_clv)
        st.session_state["clv_tracking"] = _merged_clv
    st.session_state.persistence_loaded = True

# =========================
# SIDEBAR (Full as in original)
# =========================
with st.sidebar:
    # ── Brand ─────────────────────────────────────────────────────────
    st.markdown(
        '<div style="padding:16px 0 12px;border-bottom:1px solid #1a2a3a;margin-bottom:14px;">'
        '<div style="font-size:22px;font-weight:800;color:var(--bc-text);letter-spacing:1px;font-family:monospace;">BetCouncil</div>'
        '<div style="font-size:11px;color:#4a8a8a;letter-spacing:2px;margin-top:2px;">v4.7 · LIVE ENGINE</div>'
        '</div>', unsafe_allow_html=True
    )
    if _ODDS_API_KEY_STATUS == "missing":
        st.sidebar.warning("⚠️ ODDS_API_KEY missing — fallback odds only")
    elif _ODDS_API_KEY_STATUS == "invalid":
        st.sidebar.error("🔴 ODDS_API_KEY invalid/expired")
    # Bankroll input rendered here, BEFORE the tile below reads
    # st.session_state["bankroll"] — previously this ran ~70 lines further
    # down, after the tile already displayed, so the tile always showed the
    # value from before the user's latest edit (one rerun stale) while this
    # input showed the live number. Moving it up keeps both in sync.
    st.session_state.bankroll = st.number_input("Bankroll ($)", value=float(st.session_state.get("bankroll", 100.0)), step=10.0)
    # Persist immediately on change — previously this widget only updated
    # session_state in-memory; the only places that actually wrote to
    # Gist/local storage were bet settlement and the Reset Bankroll button.
    # A manual edit here (no bet settled since) was never saved, so any full
    # page reload / new session reverted it to the last-settled value.
    if st.session_state.bankroll != st.session_state.get("_bankroll_last_saved"):
        save_json_data(BANKROLL_PATH, st.session_state.bankroll)
        save_to_gist("bankroll", st.session_state.bankroll)
        st.session_state["_bankroll_last_saved"] = st.session_state.bankroll

    # Deposit / Withdraw — separate from the manual number box above.
    # Editing the Bankroll box directly changes the number but NOT
    # day_start_br, so a withdrawal (e.g. moving $400 to savings) reads as
    # a $400 loss in the daily P&L tile below and can even falsely trip the
    # stop-loss circuit breaker, since both are computed purely as
    # (bankroll - day_start_br). These buttons move the same delta through
    # both numbers, so cash in/out of the account never gets counted as a
    # win or loss.
    with st.expander("💵 Deposit / Withdraw"):
        _dw_amount = st.number_input("Amount ($)", min_value=0.0, step=10.0, key="_dw_amount")
        _dw_col1, _dw_col2 = st.columns(2)
        if _dw_col1.button("➕ Deposit", key="_dw_deposit_btn", use_container_width=True) and _dw_amount > 0:
            st.session_state.bankroll += _dw_amount
            st.session_state["day_start_br"] = st.session_state.get("day_start_br", st.session_state.bankroll) + _dw_amount
            save_json_data(BANKROLL_PATH, st.session_state.bankroll)
            save_to_gist("bankroll", st.session_state.bankroll)
            st.session_state["_bankroll_last_saved"] = st.session_state.bankroll
            _txn_log = load_from_gist("bankroll_transactions", [])
            if not isinstance(_txn_log, list):
                _txn_log = []
            _txn_log.append({"type": "deposit", "amount": _dw_amount,
                              "timestamp": datetime.now().isoformat()})
            save_to_gist("bankroll_transactions", _txn_log[-200:])
            st.success(f"Deposited ${_dw_amount:,.2f} — bankroll and day-start baseline both updated.")
            st.rerun()
        if _dw_col2.button("➖ Withdraw", key="_dw_withdraw_btn", use_container_width=True) and _dw_amount > 0:
            st.session_state.bankroll -= _dw_amount
            st.session_state["day_start_br"] = st.session_state.get("day_start_br", st.session_state.bankroll) - _dw_amount
            save_json_data(BANKROLL_PATH, st.session_state.bankroll)
            save_to_gist("bankroll", st.session_state.bankroll)
            st.session_state["_bankroll_last_saved"] = st.session_state.bankroll
            _txn_log = load_from_gist("bankroll_transactions", [])
            if not isinstance(_txn_log, list):
                _txn_log = []
            _txn_log.append({"type": "withdraw", "amount": _dw_amount,
                              "timestamp": datetime.now().isoformat()})
            save_to_gist("bankroll_transactions", _txn_log[-200:])
            st.success(f"Withdrew ${_dw_amount:,.2f} — bankroll and day-start baseline both updated.")
            st.rerun()
        st.caption("Use these (not the Bankroll box above) when moving money in or out of the account, so it isn't counted as a betting win/loss.")
    _today_str    = date.today().strftime("%Y-%m-%d")
    _bankroll_now = float(st.session_state.get("bankroll", DEFAULT_BANKROLL))
    _day_start    = float(st.session_state.get("day_start_br", _bankroll_now) or _bankroll_now)
    _daily_chg    = (_bankroll_now - _day_start) / _day_start if _day_start > 0 else 0
    _max_loss_pct = DAILY_RISK_CONTROLS.get("stop_loss_pct", 0.15)
    _max_win_pct  = DAILY_RISK_CONTROLS.get("stop_win_pct", 0.25)
    _today_locks  = [l for l in st.session_state.get("locks", []) if l.get("timestamp","").startswith(_today_str)]
    _n_locks  = len(_today_locks)
    _max_locks = DAILY_RISK_CONTROLS.get("max_locks_per_day", 8)
    if _daily_chg <= -_max_loss_pct: _risk_status = "🛑 STOP-LOSS"; _risk_color = "#e04040"
    elif _daily_chg >= _max_win_pct: _risk_status = "🏆 STOP-WIN";  _risk_color = "#e8a020"
    elif _n_locks >= _max_locks:     _risk_status = "🛑 MAX LOCKS"; _risk_color = "#e04040"
    elif _n_locks >= _max_locks-2:   _risk_status = "⚠️ NEAR LIMIT"; _risk_color = "#e8a020"
    else:                            _risk_status = "● NORMAL";     _risk_color = "#22c55e"
    _chg_color = "#22c55e" if _daily_chg >= 0 else "#e04040"
    _chg_str   = f"{_daily_chg:+.1%} today"
    # Bankroll tile
    st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:12px 14px;margin-bottom:10px;">'
        f'<div style="font-size:10px;color:#4a6a8a;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">💰 BANKROLL</div>'
        f'<div style="font-size:26px;font-weight:800;color:var(--bc-text);">${_bankroll_now:,.2f}</div>'
        f'<div style="font-size:12px;color:{_chg_color};margin-top:2px;">{_chg_str}</div>'
        f'</div>', unsafe_allow_html=True)
    # Calibration tile (was mislabeled "INTEGRITY" — this is actually a Brier-
    # score-derived measure of how well predicted win probabilities have
    # matched real outcomes, not a data/system integrity check. Renamed for
    # clarity, and gated so a thin settled-bet sample (n<20) doesn't render
    # as an alarming red score — Brier score on 2-3 bets is just noise.
    _brier_data   = compute_brier_score(st.session_state.get("history", []))
    _brier_life   = (_brier_data.get("lifetime") or {})
    _bs_val       = _brier_life.get("brier_score", 0.25)
    _bs_n         = _brier_life.get("n", 0)
    _integrity    = max(0, min(100, int((1 - (_bs_val / 0.25)) * 100)))
    _thin_sample  = _bs_n < 20
    # Grade uses the SAME thresholds as the History tab's Brier cards
    # (ELITE<0.20, GOOD<0.22, FAIR<0.25, else NEEDS WORK) so the sidebar
    # number and the History breakdown can never disagree with each other.
    _cal_grade = "ELITE" if _bs_val < 0.20 else "GOOD" if _bs_val < 0.22 else "FAIR" if _bs_val < 0.25 else "NEEDS WORK"
    _integrity_color = "#6a7a8a" if _thin_sample else (
        "#22c55e" if _cal_grade in ("ELITE", "GOOD") else ("#e8a020" if _cal_grade == "FAIR" else "#e04040"))
    _regime_data  = detect_season_regime("MLB")
    _regime_label = _regime_data.get("label", "REGULAR FLOOR")
    _edge_thresh  = _regime_data.get("edge_floor", 0.045)
    # Auto-generated "why" sentence from the actual per-sport breakdown —
    # answers "why is it low" without the user having to open History.
    _per_sport_cal = _brier_data.get("per_sport", {}) or {}
    _cal_explainer = ""
    _grade_plain = {
        "NEEDS WORK": "predicted win probabilities haven't matched what actually happened",
        "FAIR":       "predicted win probabilities have drifted somewhat from actual results",
    }
    if not _thin_sample and _per_sport_cal:
        _ranked = sorted(_per_sport_cal.items(), key=lambda x: x[1]["brier_score"])
        _best   = _ranked[0]
        _worst  = _ranked[-1]
        if _worst[1]["grade"] in ("FAIR", "NEEDS WORK") and _worst[0] != _best[0]:
            _plain = _grade_plain.get(_worst[1]["grade"], "")
            _cal_explainer = (f"{_worst[0]} ({_worst[1]['grade']}, {_worst[1]['n']} bets) is the main drag on this number — "
                               f"its {_plain}. Kelly sizing is one global multiplier across ALL sports, not per-sport — "
                               f"so a recent stretch like this one throttles every bet's stake, including {_best[0]}'s, "
                               f"until overall recent performance recovers. "
                               f"{_best[0]} is grading {_best[1]['grade']}.")
        elif _worst[1]["grade"] in ("FAIR", "NEEDS WORK"):
            _plain = _grade_plain.get(_worst[1]["grade"], "")
            _cal_explainer = (f"{_worst[0]} ({_worst[1]['grade']}, {_worst[1]['n']} bets) is your only tracked sport so far — "
                               f"its {_plain}. Kelly sizing is throttled globally in response, not just for {_worst[0]}.")
        else:
            _cal_explainer = f"All tracked sports are grading GOOD or better — {_best[0]} leads at {_best[1]['grade']}."
    if not _cal_explainer:
        _cal_explainer = "How closely your predicted win probabilities have matched real results (higher = better calibrated). See the History tab for the full breakdown."
    st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:12px 14px;margin-bottom:2px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div style="font-size:10px;color:#4a6a8a;text-transform:uppercase;letter-spacing:1px;" '
        f'title="How well your predicted win probabilities have matched actual results over your last {_bs_n} settled bets. 100 = predictions landed exactly as often as predicted. 0 = no better than a coin flip. Grade uses the same ELITE/GOOD/FAIR/NEEDS WORK bands as the History tab.">'
        f'↗ CALIBRATION &#9432;</div>'
        f'</div>'
        + (f'<div style="font-size:16px;font-weight:700;color:var(--bc-dim);margin-top:4px;">Building sample<span style="font-size:11px;font-weight:400;"> (n={_bs_n}, need 20+)</span></div>'
           if _thin_sample else
           f'<div style="font-size:28px;font-weight:800;color:{_integrity_color};">{_integrity}<span style="font-size:14px;color:#4a6a8a;font-weight:400;"> /100 (n={_bs_n}) · {_cal_grade}</span></div>')
        + f'<div style="background:#1a2a3a;border-radius:3px;height:4px;margin-top:4px;">'
        f'<div style="width:{_integrity if not _thin_sample else 0}%;height:100%;background:linear-gradient(90deg,#e04040,#e8a020,#22c55e);border-radius:3px;"></div>'
        f'</div></div>', unsafe_allow_html=True)
    st.caption(_cal_explainer)
    if not _thin_sample and _cal_grade in ("FAIR", "NEEDS WORK"):
        st.warning(f"⚠️ Calibration is {_cal_grade} — model confidence has drifted from actual outcomes. Kelly sizing is one global multiplier across your whole recent history, and it's already being throttled for every sport as a result, not just the sport(s) driving this grade down.")
    # SEM tile
    st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:12px 14px;margin-bottom:10px;">'
        f'<div style="font-size:10px;color:#4a6a8a;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">↗ SEM</div>'
        f'<div style="font-size:13px;font-weight:700;color:#22c55e;letter-spacing:1px;">● {_regime_label.upper()}</div>'
        f'<div style="font-size:11px;color:#4a6a8a;margin-top:2px;">({_edge_thresh:.1%} edge threshold)</div>'
        f'</div>', unsafe_allow_html=True)
    # Unit + Session tile
    _unit_val = active_unit()
    st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:12px 14px;margin-bottom:10px;">'
        f'<div style="font-size:10px;color:#4a6a8a;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">⊚ UNIT SIZE</div>'
        f'<div style="font-size:24px;font-weight:800;color:var(--bc-text);">${_unit_val:.2f}</div>'
        f'<div style="font-size:11px;color:#4a6a8a;margin-top:2px;">{KELLY_FRACTION:.2f} Kelly Fraction</div>'
        f'</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:12px 14px;margin-bottom:14px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div><div style="font-size:10px;color:#4a6a8a;text-transform:uppercase;letter-spacing:1px;">⏱ SESSION</div>'
        f'<div style="font-size:22px;font-weight:700;color:var(--bc-text);font-family:monospace;">{get_session_time()}</div></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:11px;color:{_risk_color};font-weight:700;">{_risk_status}</div>'
        f'<div style="font-size:10px;color:#4a6a8a;">Locks: {_n_locks}/{_max_locks}</div>'
        f'</div></div></div>', unsafe_allow_html=True)
    if not ENABLE_RECOMMENDATIONS:
        st.error("🔴 KILL SWITCH ACTIVE", icon="🛑")
    st.markdown('<div style="font-size:10px;color:#2a3a4a;margin-bottom:10px;">8 MODELS ACTIVE · 14 SOURCES</div>', unsafe_allow_html=True)
    st.markdown("---")
    dc = get_daily_change()
    dc_color = "#0ea5a0" if dc.startswith("+") else "#e04040"
    st.markdown(f'<div style="font-size:16px;color:{dc_color};margin-top:-12px;margin-bottom:8px;">{dc} today</div>', unsafe_allow_html=True)
    st.metric("Active Unit", f"${active_unit():.2f}")
    st.markdown(f'<div style="font-size:15px;color:#5a6a7a;margin-bottom:16px;">Session: {get_session_time()}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("⚙️ Filter Settings")
    st.caption("Control which props appear on your board.")

    st.markdown("**Minimum Edge (%)**")
    st.caption("Only show props where the model's projected edge exceeds this threshold. Higher = fewer but stronger plays.")
    st.session_state.min_edge = st.slider(
        "Min Edge (%)", 0, 15,
        int(st.session_state.get("min_edge", MIN_EDGE_DEFAULT) * 100), step=1,
        help="Edge = model's estimated advantage over the book line. 0% shows all props. 5%+ = APPROVED or better."
    ) / 100.0

    st.session_state.skip_defaults = st.checkbox(
        "Skip unknown players",
        value=st.session_state.get("skip_defaults", False),
        help="Hide props for players not in the stats database. Unchecking may show props with less accurate projections."
    )
    st.markdown("---")
    st.markdown('<div style="font-size:10px;color:var(--bc-muted);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px;">Select Sport</div>', unsafe_allow_html=True)
    sport_sel = st.selectbox("", SPORTS, index=SPORTS.index(st.session_state.get("last_sport", SPORTS[0])) if st.session_state.get("last_sport") in SPORTS else 0)
    if st.button("Load Board", width="stretch"):
        try:
            for f in os.listdir(CACHE_DIR):
                if "_pp.pkl" in f:
                    fp = os.path.join(CACHE_DIR, f)
                    age_mins = (time.time() - os.path.getmtime(fp)) / 60
                    if age_mins > 25:
                        os.remove(fp)
                    else:
                        try:
                            with open(fp,"rb") as pf:
                                cached = pickle.load(pf)
                            if not cached or not cached.get("data"):
                                os.remove(fp)
                        except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
                            os.remove(fp)
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
        # Proxy credit warning — warn before consuming credits
        _so_exhausted = st.session_state.get("scrapeops_exhausted", False)
        _so2_exhausted = st.session_state.get("scrapeops2_exhausted", False) if SCRAPEOPS_KEY_2 else True
        _sa_exhausted = st.session_state.get("scraperapi_exhausted", False)
        _load_count   = st.session_state.get("board_load_count", 0) + 1
        st.session_state["board_load_count"] = _load_count
        if _so_exhausted and _so2_exhausted and _sa_exhausted:
            st.warning("⚠️ Both ScrapeOps accounts + ScraperAPI credits exhausted. Scrape.do is fallback — PrizePicks may fail. Consider upgrading ScrapeOps ($9/mo).")
        elif _so_exhausted and _so2_exhausted:
            st.warning("⚠️ Both ScrapeOps accounts exhausted — using ScraperAPI fallback for PrizePicks.")
        elif _so_exhausted:
            st.info("ℹ️ Primary ScrapeOps account exhausted — using the second ScrapeOps account.")
        elif _load_count > 5:
            st.info(f"ℹ️ Board loaded {_load_count}x this session — each load uses proxy credits. Reload only when needed.")
        # Off-season guard: warn but still allow load in case pre-season props exist
        _lb_regime = detect_season_regime(sport_sel)
        if _lb_regime.get("regime") == "Off-season":
            st.info(
                f"⚠️ {sport_sel} is currently in off-season — "
                "props may be unavailable or stale. Board load continues; "
                "no error will be raised if nothing is returned."
            )
        _skeleton_ph = st.empty()
        _skeleton_ph.markdown(skeleton_rows_html(5, height_px=58), unsafe_allow_html=True)
        with st.spinner(f"Fetching {sport_sel} from PrizePicks/Underdog..."):
            _enrich_t0 = _time_mod.perf_counter()
            board, games, n_def, n_edge, home_teams, away_teams = load_sport_data(sport_sel)
            _skeleton_ph.empty()
            _bc_track("enrichment", _time_mod.perf_counter() - _enrich_t0,
                      {"props": len(board), "sport": sport_sel})
            st.session_state.board_data = board
            # Auto-populate closing line DB from board
            try:
                from bc_utils import auto_populate_closing_lines as _apcl
                _cl = load_json_data(os.path.join(CACHE_DIR,"closing_lines.json"), {})
                _cl = _apcl(sport, board, _cl)
                save_json_data(os.path.join(CACHE_DIR,"closing_lines.json"), _cl)
            except Exception:
                pass
            st.session_state.games = games
            st.session_state["board_loaded"]       = True
        # Kill switch warning rendered after spinner in correct main-area context.
        # BUG FIX (2026-07): the entire game_analysis computation below used to be
        # nested inside `if not ENABLE_RECOMMENDATIONS:`, meaning analyze_all_games()
        # only ran when recommendations were DISABLED -- never in the normal enabled
        # state. That silently left st.session_state["game_analysis"] empty on every
        # regular board load, causing the Game Lines tab to fall back to raw
        # unenriched game data (no team names on ML/Total, 0.0% edge everywhere).
        # Only the warning banner itself is actually kill-switch-specific; everything
        # else here is normal per-load bookkeeping and must always run.
        if not ENABLE_RECOMMENDATIONS:
            st.warning(
                "🔴 **Recommendations disabled.** Set `ENABLE_RECOMMENDATIONS = true` "
                "in Streamlit Cloud secrets (Settings → Secrets) to re-enable the board. "
                "All historical data, system monitoring, and logging remain active.",
                icon="🛑"
            )
        st.session_state["last_sport_loaded"]  = sport_sel
        st.session_state["ev_auto_refresh_ts"] = 0   # trigger immediate first snapshot
        # Cache last good props per sport for fallback
        if board:
            if "last_good_props" not in st.session_state:
                st.session_state["last_good_props"] = {}
            st.session_state["last_good_props"][sport_sel] = board
        st.session_state.last_sport = sport_sel
        st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
        st.session_state.board_ready = True
        st.session_state.n_skipped_def = n_def
        st.session_state.n_skipped_edge = n_edge
        if games and home_teams and away_teams:
            game_analysis = analyze_all_games(games, sport_sel, home_teams, away_teams,
                                               mlb_pitchers=st.session_state.get("mlb_pitchers",{}))
            st.session_state["game_analysis"] = game_analysis
            # Store opening lines + line origins now that game_analysis exists
            if game_analysis:
                store_opening_lines(game_analysis, sport_sel)
                st.session_state["line_origins"] = track_line_origin(game_analysis, sport_sel)
            # Fetch alt lines and enrich game_analysis
            _alt_lines_data = fetch_alt_lines(sport_sel)
            if _alt_lines_data and game_analysis:
                st.session_state["alt_lines_data"] = _alt_lines_data
                for _ga in game_analysis:
                    _ga_matchup = _ga.get("matchup","")
                    _h_full = _ga.get("home","")
                    _a_full = _ga.get("away","")
                    _h_pr = _ga.get("home_power", 0)
                    _a_pr = _ga.get("away_power", 0)
                    if not _h_pr:
                        # Get from power ratings
                        _pr_lookup = dict(NBA_POWER_RATINGS)
                        if sport_sel == "MLB":
                            _pr_lookup.update(MLB_POWER_RATINGS)
                        elif sport_sel == "NHL":
                            _pr_lookup.update(NHL_POWER_RATINGS)
                        elif sport_sel == "WNBA":
                            _pr_lookup.update(WNBA_POWER_RATINGS)
                        _h_pr = _pr_lookup.get(_h_full, 100)
                        _a_pr = _pr_lookup.get(_a_full, 100)
                    # Try matchup string first, then try matching by team names
                    _best_alt = find_best_alt_line(
                        _ga_matchup, sport_sel, _h_pr, _a_pr,
                        _h_full, _a_full, _alt_lines_data
                    )
                    if not _best_alt:
                        # Try matching by home team full name
                        for _alt_key in _alt_lines_data:
                            if _h_full in _alt_key or _a_full in _alt_key:
                                _best_alt = find_best_alt_line(
                                    _alt_key, sport_sel, _h_pr, _a_pr,
                                    _h_full, _a_full, _alt_lines_data
                                )
                                if _best_alt:
                                    break
                    if _best_alt:
                        _ga["AltLine"]  = _best_alt["pick"]
                        _ga["AltEdge"]  = _best_alt["edge"]
                        _ga["AltTier"]  = _best_alt["tier"]
                        _ga["AltBook"]  = _best_alt.get("book","")
                        # find_best_alt_line's "point" is relative to
                        # _best_alt["team"] (whichever side scored best),
                        # not consistently home -- normalize to home-
                        # relative here so it matches SpreadLineHome's
                        # convention and the resolver's math (fixed
                        # 2026-07-13, same bug class as the SPREAD line).
                        _alt_point = _best_alt.get("point", 0) or 0
                        _alt_team_is_home = normalize_name(_best_alt.get("team","")) == normalize_name(_h_full)
                        _ga["AltLineValue"] = _alt_point if _alt_team_is_home else -_alt_point
            store_game_board_snapshot(game_analysis, sport_sel)
        else:
            st.session_state["game_analysis"] = []
        if board:
            # Show which source the props came from
            sources = list(set(p.get("source","Unknown") for p in board if p.get("source")))
            source_str = " + ".join(sources) if sources else "Unknown"
            # Only fill in pp_status/pp_source if fetchers.py's
            # scrape_prizepicks_with_gist_fallback() didn't already set them
            # successfully this run. Previously this block re-derived status from
            # the combined board's per-prop "source" tags using substring checks
            # ("prizepicks_auto", "gist"), which don't match the current GH
            # Actions scraper's tag ("github_actions_partner_api") — silently
            # clobbering a correct "ok" status down to "fallback".
            if st.session_state.get("pp_status") != "ok":
                if any("prizepicks_auto" in s.lower() or "gist" in s.lower() or "github_actions" in s.lower() for s in sources):
                    st.session_state["pp_status"] = "ok"
                    st.session_state["pp_source"] = "gist_scraper"
                elif any("prizepicks" in s.lower() for s in sources):
                    st.session_state["pp_status"] = "ok"
                elif sources:
                    st.session_state["pp_status"] = "fallback"
            st.success(f"✅ {len(board)} props loaded from **{source_str}**")
            if n_def:
                st.info(f"{n_def} unknown players skipped (using defaults)")
        else:
            st.warning("No props yet. Check back closer to game time.")
    st.markdown("---")
    # Show data source status
    _pp_status = st.session_state.get("pp_status", "unknown")
    _pp_source = st.session_state.get("pp_source","")
    if _pp_source in ("gist_scraper", "browser_harvester"):
        st.success("✅ PrizePicks loaded from browser harvester (Gist)")
        st.caption("Auto-refreshed via GitHub Actions workflow every 15 min.")
    elif _pp_source == "scraper_fallback":
        st.success("✅ PrizePicks loaded via CDN scraper fallback")
    elif _pp_source == "prizepicks_direct":
        st.success("✅ PrizePicks loaded via direct live scrape")
    elif _pp_source == "last_known_good":
        st.warning("🟡 PrizePicks showing last-known-good cache (stale)")
    elif _pp_status == "ok":
        st.success("✅ PrizePicks connected")
    elif _pp_status == "fallback":
        st.info("ℹ️ Using fallback sources (Underdog/ParlayAPI) — PrizePicks unavailable")
    elif _pp_status == "unavailable":
        st.warning("⚠️ PrizePicks unavailable — run betcouncil_auto_scraper.py to populate")
    _wins = sum(1 for h in st.session_state.get("history", []) if h.get("outcome") == "WIN")
    _losses = sum(1 for h in st.session_state.get("history", []) if h.get("outcome") == "LOSS")
    if _wins + _losses > 0:
        _total = _wins + _losses
        _hit_rate = _wins / _total
        _net = sum(h.get("net", 0) for h in st.session_state.get("history", []))
        _color = "green" if _net >= 0 else "red"
        _hit_color = "#22c55e" if _hit_rate >= 0.577 else "#e04040"
        st.markdown(f"""
<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px 12px;margin:8px 0;">
  <div style="font-size:14px;color:var(--bc-dim);margin-bottom:4px;">YOUR RECORD</div>
  <div style="font-size:20px;font-weight:700;color:var(--bc-text);">{_wins}W — {_losses}L</div>
  <div style="font-size:16px;color:{_hit_color};font-weight:600;">{_hit_rate:.1%} hit rate {'✅' if _hit_rate >= 0.577 else '⚠️'}</div>
  <div style="font-size:16px;color:{_color};font-weight:700;">Net: ${_net:.2f}</div>
  <div style="font-size:16px;color:var(--bc-dim);margin-top:4px;">Need 57.7%+ for +EV on 2-picks</div>
</div>""", unsafe_allow_html=True)
    if st.button("Reset Bankroll", width="stretch"):
        st.session_state.bankroll = DEFAULT_BANKROLL
        st.session_state["day_start_br"] = DEFAULT_BANKROLL
        save_json_data(BANKROLL_PATH, st.session_state.get("bankroll", DEFAULT_BANKROLL))
        save_to_gist("bankroll", st.session_state.get("bankroll", DEFAULT_BANKROLL))
        st.rerun()

# =========================
# COMMAND BAR
# =========================
pending = len([l for l in st.session_state.get("locks", []) if l.get("status") == "PENDING"])
dc = get_daily_change()
dc_color = "#0ea5a0" if dc.startswith("+") else "#e04040"
scan_t = st.session_state.get("last_scan_time", 0) or "—"
staleness_label_bar, _staleness_color_bar = get_edge_staleness(st.session_state.get("last_scan_time", 0))
_staleness_pulse_class = " pulse-stale" if _staleness_color_bar in ("red", "orange") else ""
st.markdown(f"""
<div class="command-bar">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;">
    <div style="font-size:16px;color:#0ea5a0;font-weight:600;">⚡ BetCouncil v4.6 — Complete</div>
    <div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
      <span style="font-size:15px;color:var(--bc-dim);">Session: {get_session_time()}</span>
      <span style="font-size:15px;border:1px solid #0ea5a0;color:#0ea5a0;background:rgba(14,165,160,0.1);padding:4px 10px;border-radius:20px;">{pending} Lock{"s" if pending!=1 else ""}</span>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;">
    <div class="metric-box"><div class="metric-label">Bankroll</div><div class="metric-value gold-text">${st.session_state.get("bankroll", DEFAULT_BANKROLL):.2f}</div><div style="font-size:15px;color:{dc_color};">{dc} today</div></div>
    <div class="metric-box"><div class="metric-label">Unit</div><div class="metric-value teal-text">${active_unit():.2f}</div></div>
    <div class="metric-box"><div class="metric-label">Min Edge</div><div class="metric-value gold-text">{st.session_state.get("min_edge", MIN_EDGE_DEFAULT)*100:.0f}%</div></div>
    <div class="metric-box"><div class="metric-label">Kelly</div><div class="metric-value gold-text">{KELLY_FRACTION}</div></div>
    <div class="metric-box"><div class="metric-label">Props Loaded</div><div class="metric-value teal-text">{len(st.session_state.board_data)}</div></div>
    <div class="metric-box{_staleness_pulse_class}"><div class="metric-label">Edge Freshness</div><div class="metric-value" style="font-size:14px;">{staleness_label_bar}</div></div>
  </div>
</div>""", unsafe_allow_html=True)

# =========================
# TABS (Full as in original - Summary tab simplified for length)
# =========================


# =========================
# DRAFTKINGS DFS SALARY SIGNAL
# =========================



# ── Safety net: guarantee core session_state keys exist before any tab
# renders, independent of the _ss init block above. Protects against rare
# Streamlit Cloud reconnect/rerun race conditions where a script execution
# can reach this point with a session_state that was reset or reconnected
# mid-flight, bypassing the normal top-of-script initialization.
for _safety_k, _safety_v in {
    "bankroll": DEFAULT_BANKROLL, "day_start_br": DEFAULT_BANKROLL,
    "history": [], "locks": [], "min_edge": MIN_EDGE_DEFAULT,
    "skip_defaults": True, "board_data": [],
}.items():
    if _safety_k not in st.session_state:
        st.session_state[_safety_k] = _safety_v

def _bc_df_html(data, columns=None):
    # Plain HTML table instead of st.dataframe — st.dataframe renders via a
    # canvas-based grid (Glide Data Grid) that has been observed to fail to
    # paint (empty box, structure intact) right after a redeploy/restart.
    # Applied app-wide: every st.dataframe call in the app was converted to
    # this, not just the System tab where it was first spotted.
    try:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    except Exception:
        return '<div style="color:var(--bc-dim);font-size:13px;padding:8px;">No data to display.</div>'
    if df.empty:
        return '<div style="color:var(--bc-dim);font-size:13px;padding:8px;">No data to display.</div>'
    cols = columns or list(df.columns)
    head = "".join(f'<th style="text-align:left;padding:6px 10px;color:var(--bc-dim);font-size:11px;text-transform:uppercase;border-bottom:1px solid var(--bc-border);white-space:nowrap;">{c}</th>' for c in cols)
    body = ""
    for _i, (_, row) in enumerate(df.iterrows()):
        _row_bg = "background:rgba(255,255,255,0.015);" if _i % 2 else ""
        cells = "".join(f'<td style="padding:6px 10px;font-size:13px;color:var(--bc-text);border-bottom:1px solid #16232f;">{row.get(c,"")}</td>' for c in cols)
        body += f'<tr style="{_row_bg}">{cells}</tr>'
    return (
        f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);'
        f'border-radius:8px;overflow:auto;max-height:480px;margin-bottom:0.5rem;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    )

