import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta, timezone
import re
import requests
import time
import hashlib
import pickle
import os
import json
import unicodedata
from math import exp, factorial
import math
from itertools import combinations
from scipy import stats as scipy_stats

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="BetCouncil v4.6 – Complete", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
body, .stApp, .main { background-color: #060c14; color: #e8f0f8; font-family: 'Inter', sans-serif; font-size: 15px; }
h1 { font-size: 28px; font-weight: 700; color: #ffffff; }
h2 { font-size: 20px; font-weight: 600; color: #e0e8f0; }
h3 { font-size: 17px; font-weight: 600; color: #d0d8e0; }
.stButton > button { background-color: #0ea5a0; color: #ffffff; border: none; border-radius: 8px; padding: 8px 18px; font-weight: 600; }
.stButton > button:hover { background-color: #0d9488; transform: translateY(-1px); }
.command-bar { background: linear-gradient(135deg, rgba(14,165,160,0.08), #0d1520); border: 1px solid rgba(14,165,160,0.3); border-top: 3px solid #0ea5a0; border-radius: 0 0 12px 12px; padding: 18px 22px; margin-bottom: 16px; }
.metric-box { background: #0d1520; border: 1px solid #1a2a3a; border-radius: 8px; padding: 10px 14px; text-align: center; }
.metric-label { font-size: 11px; color: #6a7a8a; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }
.metric-value { font-size: 20px; font-weight: 700; }
.gold-text { color: #e8a020; }
.teal-text { color: #0ea5a0; }
.red-text { color: #e04040; }
.muted-text { color: #6a7a8a; }
.injury-badge { background-color: #e04040; color: white; font-size: 10px; padding: 2px 6px; border-radius: 12px; margin-left: 6px; }
.sem-green { color: #0ea5a0; font-weight: 600; }
.sem-yellow { color: #e8a020; font-weight: 600; }
.sem-gray { color: #6a7a8a; }
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS
# =========================
DEFAULT_BANKROLL = 468.49
KELLY_FRACTION = 0.15
KELLY_CAP = 0.25
ODDS = -110
EDGE_CAP = 0.20
MIN_EDGE_DEFAULT = 0.02
REQUEST_TIMEOUT = 10
CACHE_DIR = "/tmp/betcouncil_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
AVERAGES_LAST_UPDATED = "2025-05-13"

# Daily risk controls
DAILY_RISK_CONTROLS = {
    "max_daily_loss_pct": 0.15,
    "max_locks_per_day": 8,
    "stop_win_pct": 0.25,
    "max_same_sport_locks": 4,
    "max_same_game_locks": 2,
}

# JSON persistence paths
HISTORY_PATH = os.path.join(CACHE_DIR, "history.json")
LOCKS_PATH = os.path.join(CACHE_DIR, "locks.json")
BANKROLL_PATH = os.path.join(CACHE_DIR, "bankroll.json")
CALIBRATION_PATH = os.path.join(CACHE_DIR, "calibration.json")
CLV_PATH = os.path.join(CACHE_DIR, "clv_tracking.json")
PINNACLE_LINES_PATH = os.path.join(CACHE_DIR, "pinnacle_lines.json")
INJURY_PERFORMANCE_PATH = os.path.join(CACHE_DIR, "injury_performance.json")
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
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")

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
ODDS_API_BOOKS_PROPS = "bovada,mybookieag,draftkings,fanduel,us_ex"
ODDS_API_BOOKS_GAMES = "bovada,mybookieag,draftkings,fanduel,betmgm,caesars,us_ex"

# Action Network public betting API
ACTION_NETWORK_BASE = (
    "https://api.actionnetwork.com"
    "/web/v2/scoreboard/publicbetting"
)
ACTION_NETWORK_BOOK_IDS = (
    "15,30,4727,4795,79,2988,"
    "69,68,75,123,71"
)
ACTION_NETWORK_SPORT_MAP = {
    "NBA": "nba",
    "MLB": "mlb",
    "NHL": "nhl",
    "NFL": "nfl",
    "WNBA": "wnba",
}

ACTION_NETWORK_LEAGUE_IDS = {
    "NFL": 1,
    "MLB": 2,
    "NHL": 3,
    "NBA": 4,
    "WNBA": 5,
}

ACTION_NETWORK_PROP_TYPE_MAP = {
    "core_bet_type_27_points": "Points",
    "core_bet_type_28_rebounds": "Rebounds",
    "core_bet_type_29_assists": "Assists",
    "core_bet_type_30_pra": "Pts+Reb+Ast",
    "core_bet_type_31_steals": "Steals",
    "core_bet_type_32_blocks": "Blocked Shots",
    "core_bet_type_33_threes": "3-PT Made",
    "core_bet_type_34_turnovers": "Turnovers",
    "core_bet_type_pts": "Points",
    "core_bet_type_reb": "Rebounds",
    "core_bet_type_ast": "Assists",
    "core_bet_type_pra": "Pts+Reb+Ast",
    "core_bet_type_26_assists": "Assists",
    "core_bet_type_277_blocks": "Blocked Shots",
    "core_bet_type_1042_powerplay_points": "Power Play Points",
    "core_bet_type_hits": "Hits",
    "core_bet_type_hr": "Home Runs",
    "core_bet_type_rbi": "RBIs",
    "core_bet_type_runs": "Runs",
    "core_bet_type_total_bases": "Total Bases",
    "core_bet_type_strikeouts": "Strikeouts",
    "core_bet_type_pitcher_strikeouts": "Strikeouts",
    "core_bet_type_pitcher_outs": "Pitcher Outs",
    "core_bet_type_goals": "Goals",
    "core_bet_type_sog": "Shots On Goal",
    "core_bet_type_passing_yards": "Passing Yards",
    "core_bet_type_rushing_yards": "Rushing Yards",
    "core_bet_type_receiving_yards": "Receiving Yards",
    "core_bet_type_receptions": "Receptions",
    "core_bet_type_touchdowns": "Touchdowns",
    "core_bet_type_passing_tds": "Touchdowns",
}

AN_GRADE_TO_TIER = {
    "A+": "SOVEREIGN",
    "A": "ELITE",
    "A-": "ELITE",
    "B+": "APPROVED",
    "B": "APPROVED",
    "B-": "LEAN",
    "C+": "LEAN",
    "C": "LEAN",
}

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
ODDS_API_PROP_MARKETS = {
    "NBA": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_points_rebounds_assists",
        "player_steals",
        "player_blocks",
        "player_threes",
        "player_turnovers",
    ],
    "MLB": [
        "batter_hits",
        "batter_home_runs",
        "batter_rbis",
        "batter_runs_scored",
        "pitcher_strikeouts",
        "pitcher_outs",
    ],
    "NHL": [
        "player_points",
        "player_goals",
        "player_assists",
        "player_shots_on_goal",
    ],
    "NFL": [
        "player_pass_yds",
        "player_rush_yds",
        "player_reception_yds",
        "player_pass_tds",
    ],
    "WNBA": [
        "player_points",
        "player_rebounds",
        "player_assists",
    ],
}

# Map Odds API market keys to our stat names
ODDS_API_STAT_MAP = {
    "player_points": "Points",
    "player_rebounds": "Rebounds",
    "player_assists": "Assists",
    "player_points_rebounds_assists": "Pts+Reb+Ast",
    "player_steals": "Steals",
    "player_blocks": "Blocked Shots",
    "player_threes": "3-PT Made",
    "player_turnovers": "Turnovers",
    "batter_hits": "Hits",
    "batter_home_runs": "Home Runs",
    "batter_rbis": "RBIs",
    "batter_runs_scored": "Runs",
    "pitcher_strikeouts": "Strikeouts",
    "pitcher_outs": "Pitcher Outs",
    "player_goals": "Goals",
    "player_assists": "Assists",
    "player_shots_on_goal": "Shots On Goal",
    "player_pass_yds": "Passing Yards",
    "player_rush_yds": "Rushing Yards",
    "player_reception_yds": "Receiving Yards",
    "player_pass_tds": "Touchdowns",
}

# Unified API budgets
API_BUDGETS = {
    "BDL": {
        "key": "BALLSDONTLIE_API_KEY",
        "daily_limit": None,
        "monthly_limit": 200,
        "counter_path": os.path.join(CACHE_DIR, "bdl_unified_counter.json"),
        "description": "BallDontLie (averages + props)",
        "hard_stop_pct": 0.80,
    },
    "ODDSPAPI": {
        "key": "ODDSPAPI_KEY",
        "daily_limit": 100,
        "monthly_limit": 1000,
        "counter_path": os.path.join(CACHE_DIR, "oddspapi_counter.json"),
        "description": "OddsPapi props fallback",
        "hard_stop_pct": 0.80,
    },
    "PARLAYPLAY": {
        "key": None,
        "daily_limit": 200,
        "monthly_limit": None,
        "counter_path": os.path.join(CACHE_DIR, "parlayplay_counter.json"),
        "description": "ParlayPlay all sports",
        "hard_stop_pct": 0.90,
    },
    "ESPN": {
        "key": None,
        "daily_limit": None,
        "monthly_limit": None,
        "counter_path": os.path.join(CACHE_DIR, "espn_counter.json"),
        "description": "ESPN (unlimited public API)",
        "hard_stop_pct": 1.0,
    },
    "ODDS_API": {
        "key": "ODDS_API_KEY",
        "daily_limit": None,
        "monthly_limit": 500,
        "counter_path": os.path.join(CACHE_DIR, "odds_api_counter.json"),
        "description": "The Odds API",
        "hard_stop_pct": 0.80,
    },
    "ACTION_NETWORK": {
        "key": None,
        "daily_limit": 500,
        "monthly_limit": None,
        "counter_path": os.path.join(CACHE_DIR, "action_network_counter.json"),
        "description": "Action Network public betting %",
        "hard_stop_pct": 0.95,
    },
}

TIER_COLORS = {"SOVEREIGN": "#e8a020", "ELITE": "#0ea5a0", "APPROVED": "#4a90d9", "LEAN": "#7a8a9a", "PASS": "#e04040"}
TIER_DESCRIPTIONS = {"SOVEREIGN": "Edge ≥ 15%", "ELITE": "Edge ≥ 10%", "APPROVED": "Edge ≥ 5%", "LEAN": "Edge ≥ 2%", "PASS": "Edge < 2%"}

TIER_THRESHOLDS = {
    "NBA": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "MLB": {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "NFL": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "NHL": {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "WNBA": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "Soccer": {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "UFC": {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "Golf": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "Tennis": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
}

# Sport-specific signal weights
SPORT_SIGNAL_WEIGHTS = {
    "NBA": {"base": 0.45, "defense": 0.30, "location": 0.15, "rest": 0.05, "pace": 0.05},
    "MLB": {"base": 0.40, "defense": 0.15, "location": 0.10, "rest": 0.05, "pace": 0.00, "pitcher": 0.15, "weather": 0.15},
    "NFL": {"base": 0.40, "defense": 0.35, "location": 0.10, "rest": 0.10, "pace": 0.05},
    "NHL": {"base": 0.50, "defense": 0.25, "location": 0.15, "rest": 0.05, "pace": 0.05},
    "WNBA": {"base": 0.50, "defense": 0.25, "location": 0.15, "rest": 0.05, "pace": 0.05},
    "Soccer": {"base": 0.60, "defense": 0.20, "location": 0.15, "rest": 0.05, "pace": 0.00},
    "UFC": {"base": 0.70, "defense": 0.10, "location": 0.10, "rest": 0.10, "pace": 0.00},
}

# Signal reliability scores based on historical accuracy
# These represent how often each signal correctly predicts outcome
SIGNAL_RELIABILITY = {
    "base": 0.72,       # rolling avg vs line — most reliable
    "defense": 0.65,    # opponent defense rating
    "location": 0.81,   # home/away advantage
    "rest": 0.88,       # rest days impact
    "pace": 0.58,       # pace adjustment
    "usage": 0.74,      # teammate out boost
    "blowout": 0.62,    # blowout risk
    "weather": 0.55,    # weather (MLB outdoor)
}

SIGNAL_LABELS = {
    "base": "Rolling Avg vs Line",
    "defense": "Opponent Defense",
    "location": "Home / Away",
    "rest": "Rest Days",
    "pace": "Pace Adjustment",
    "usage": "Usage / Teammate Out",
    "blowout": "Blowout Risk",
    "weather": "Weather Impact",
}

REGIME_LABELS = {
    "strong_over": ("CONFIRM OVER", "#22c55e"),
    "strong_under": ("CONFIRM UNDER", "#e04040"),
    "reprice_over": ("REPRICE", "#e8a020"),
    "reprice_under": ("REPRICE", "#e8a020"),
    "sharp_fade": ("SHARP FADE", "#9b59b6"),
    "neutral": ("NEUTRAL", "#6a7a8a"),
}

def classify_regime(signals, edge, line_moved):
    """Classify the market regime for a prop."""
    if abs(edge) >= 0.10 and not line_moved:
        return "strong_over" if edge > 0 else "strong_under"
    if line_moved and edge > 0.05:
        return "reprice_over"
    if line_moved and edge < -0.05:
        return "reprice_under"
    if line_moved and abs(edge) < 0.03:
        return "sharp_fade"
    return "neutral"

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
      <span style="font-size:12px;font-weight:500;color:#e8f0f8">{label}</span>
      <span style="font-size:10px;color:{bar_color};margin-left:8px;background:{bar_color}22;padding:1px 7px;border-radius:8px">{strength} {direction_word}</span>
    </div>
    <span style="font-size:10px;color:{rel_color}">{rel_label} ({int(reliability*100)}%)</span>
  </div>
  <div style="background:#0a1628;border-radius:4px;height:10px;overflow:hidden;margin-bottom:3px;">
    <div style="width:{bar_pct}%;height:100%;background:{bar_color};border-radius:4px;"></div>
  </div>
  <div style="font-size:10px;color:#6a7a8a">{desc}</div>
</div>"""

    zero_signals = [plain_labels.get(k, k) for k, v in signals.items() if abs(v) <= 0.0001]
    zero_html = ""
    if zero_signals:
        zero_html = f'<div style="font-size:10px;color:#4a5a6a;margin-top:4px">No impact: {", ".join(zero_signals)}</div>'

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

    html = f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-radius:10px;padding:16px;margin:6px 0;">

  <div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #1a2a3a;">
    <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px">Why this pick is rated the way it is</div>
    <div style="font-size:14px;font-weight:500;color:{delta_color}">{verdict}</div>
    <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;">
      <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
        <div style="font-size:9px;color:#6a7a8a;text-transform:uppercase">Signals firing</div>
        <div style="font-size:18px;font-weight:500;color:#e8f0f8">{firing}<span style="font-size:12px;color:#6a7a8a"> / {total}</span></div>
      </div>
      <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
        <div style="font-size:9px;color:#6a7a8a;text-transform:uppercase">Avg signal accuracy</div>
        <div style="font-size:18px;font-weight:500;color:#e8a020">{avg_reliability:.0%}</div>
      </div>
      <div style="background:#0a1628;border-radius:8px;padding:7px 14px;text-align:center;">
        <div style="font-size:9px;color:#6a7a8a;text-transform:uppercase">Market regime</div>
        <div style="font-size:13px;font-weight:500;color:{regime_color}">{regime_label}</div>
        <div style="font-size:9px;color:#6a7a8a">{regime_plain}</div>
      </div>
    </div>
  </div>

  <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Signal breakdown — what is pushing this pick</div>
  {rows_html}
  {zero_html}
</div>"""
    return html



# Sport-specific EWMA decay
SPORT_EWMA_DECAY = {
    "NBA": 0.85,
    "MLB": 0.92,
    "NHL": 0.88,
    "WNBA": 0.85,
    "NFL": 0.80,
}

SPORTS = ["NBA", "MLB", "NHL", "WNBA", "NFL", "Soccer", "UFC", "Golf", "Tennis"]

PRIZEPICKS_MULTIPLIERS = {
    2: 3.0,
    3: 5.0,
    4: 10.0,
    5: 20.0,
}

# API keys from secrets
BDL_API_KEY = st.secrets.get("BALLSDONTLIE_API_KEY", "")
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "")
API_SPORTS_KEY = st.secrets.get("API_SPORTS_KEY", "")
SPORTMONKS_API_KEY = st.secrets.get("SPORTMONKS_API_KEY", "")
UNIFIED_API_KEY = st.secrets.get("UNIFIED_API_KEY", "")
RAPIDAPI_KEY = st.secrets.get("RAPIDAPI_KEY", "")
ODDS_API_IO_KEY = st.secrets.get("ODDS_API_IO_KEY", "")
OCR_SPACE_API_KEY = st.secrets.get("OCR_SPACE_API_KEY", "")

# Hardcoded baselines
PLAYER_AVERAGES_SOCCER = {
    "Erling Haaland": {"GOALS": 0.85, "ASSISTS": 0.25, "SHOTS": 4.2},
    "Kylian Mbappe": {"GOALS": 0.75, "ASSISTS": 0.35, "SHOTS": 4.0},
    "Lionel Messi": {"GOALS": 0.45, "ASSISTS": 0.55, "SHOTS": 3.5},
    "Cristiano Ronaldo": {"GOALS": 0.65, "ASSISTS": 0.20, "SHOTS": 4.5},
    "Mohamed Salah": {"GOALS": 0.55, "ASSISTS": 0.40, "SHOTS": 3.8},
    "Harry Kane": {"GOALS": 0.70, "ASSISTS": 0.30, "SHOTS": 4.1},
    "Vinicius Jr.": {"GOALS": 0.50, "ASSISTS": 0.45, "SHOTS": 3.6},
    "Kevin De Bruyne": {"GOALS": 0.25, "ASSISTS": 0.75, "SHOTS": 2.5},
    "Jude Bellingham": {"GOALS": 0.40, "ASSISTS": 0.35, "SHOTS": 3.0},
    "Rodrygo": {"GOALS": 0.35, "ASSISTS": 0.30, "SHOTS": 2.8},
}

PLAYER_AVERAGES_UFC = {
    "Jon Jones": {"TAKEDOWNS": 2.5, "SIG_STR": 45, "CONTROL_TIME": 8.5},
    "Israel Adesanya": {"SIG_STR": 55, "TAKEDOWN_DEF": 0.95, "CONTROL_TIME": 5.5},
    "Alex Pereira": {"SIG_STR": 60, "KNOCKDOWNS": 0.5, "CONTROL_TIME": 4.5},
    "Conor McGregor": {"SIG_STR": 50, "TAKEDOWNS": 1.0, "CONTROL_TIME": 5.0},
    "Kamaru Usman": {"TAKEDOWNS": 3.0, "CONTROL_TIME": 7.5, "SIG_STR": 35},
    "Leon Edwards": {"SIG_STR": 42, "TAKEDOWNS": 1.5, "CONTROL_TIME": 6.0},
    "Charles Oliveira": {"TAKEDOWNS": 2.8, "SUB_ATTEMPTS": 1.2, "CONTROL_TIME": 6.5},
    "Dustin Poirier": {"SIG_STR": 52, "TAKEDOWN_DEF": 0.85, "CONTROL_TIME": 4.0},
}

PLAYER_AVERAGES = {}
PLAYER_AVERAGES.update({
    "NBA": {},
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

DEFAULT_AVERAGES = {
    "NBA": {"PTS": 10.0, "REB": 4.0, "AST": 2.5, "PRA": 16.5},
    "MLB": {"HR": 0.05, "H": 0.8, "RBI": 0.3, "R": 0.3, "SO": 5.0},
    "NFL": {"PASS_YDS": 200, "RUSH_YDS": 35, "REC_YDS": 40, "TD": 0.5},
    "NHL": {"PTS": 0.45, "GOALS": 0.18, "ASSISTS": 0.27, "SOG": 1.8},
    "WNBA": {"PTS": 8.0, "REB": 3.5, "AST": 2.0, "PRA": 13.5},
    "Soccer": {"GOALS": 0.25, "ASSISTS": 0.15, "SHOTS": 2.5},
    "UFC": {"SIG_STR": 30, "TAKEDOWNS": 1.0, "CONTROL_TIME": 4.0},
    "Golf": {}, "Tennis": {},
}

STAT_NORMALIZE = {
    ("NBA", "Points"): "PTS", ("NBA", "Rebounds"): "REB", ("NBA", "Assists"): "AST",
    ("NBA", "Pts+Reb+Ast"): "PRA", ("MLB", "Home Runs"): "HR", ("MLB", "Hits"): "H",
    ("MLB", "RBIs"): "RBI", ("MLB", "Runs"): "R", ("MLB", "Strikeouts"): "SO",
    ("NFL", "Passing Yards"): "PASS_YDS", ("NFL", "Rushing Yards"): "RUSH_YDS",
    ("NFL", "Receiving Yards"): "REC_YDS", ("NFL", "Touchdowns"): "TD",
    ("NHL", "Points"): "PTS", ("NHL", "Goals"): "GOALS", ("NHL", "Assists"): "ASSISTS",
    ("NHL", "Shots On Goal"): "SOG", ("WNBA", "Points"): "PTS", ("WNBA", "Rebounds"): "REB",
    ("WNBA", "Assists"): "AST", ("WNBA", "Pts+Reb+Ast"): "PRA",
    ("MLB", "Earned Runs"): "ER", ("MLB", "Hits Allowed"): "H", ("MLB", "Total Bases"): "H",
    ("NHL", "Shots on Goal"): "SOG", ("NHL", "Goals"): "GOALS", ("NHL", "Assists"): "ASSISTS",
    ("NBA", "Pts+Rebs+Asts"): "PRA", ("NBA", "Pts+Reb"): "PRA", ("NBA", "Pts+Ast"): "PRA",
    ("NBA", "3-PT Made"): "THREE_PT", ("NBA", "Blocked Shots"): "BLK",
    ("NBA", "Steals"): "STL", ("NBA", "Turnovers"): "TOV",
    ("WNBA", "Pts+Reb+Ast"): "PRA", ("WNBA", "Pts+Reb"): "PRA",
    ("WNBA", "Pts+Ast"): "PRA",
    ("NBA", "pts"): "PTS", ("NBA", "reb"): "REB", ("NBA", "ast"): "AST",
    ("NBA", "points"): "PTS", ("NBA", "rebounds"): "REB", ("NBA", "assists"): "AST",
    ("MLB", "Strikeouts"): "SO", ("MLB", "Hits"): "H", ("MLB", "Home Runs"): "HR",
    ("Soccer", "Goals"): "GOALS", ("Soccer", "Assists"): "ASSISTS",
    ("Soccer", "Shots"): "SHOTS",
    ("UFC", "Significant Strikes"): "SIG_STR", ("UFC", "Takedowns"): "TAKEDOWNS",
    ("UFC", "Control Time"): "CONTROL_TIME",
}

HOME_BOOST = {"PTS": 1.5, "REB": 0.5, "AST": 0.4, "PRA": 2.4}
AWAY_PENALTY = {"PTS": -1.5, "REB": -0.5, "AST": -0.4, "PRA": -2.4}

TEAMMATE_OUT_BOOST = {
    "Luka Doncic": {"out_player": "Kyrie Irving", "PTS": 3.5, "AST": 1.5, "PRA": 5.0},
    "Shai Gilgeous-Alexander": {"out_player": "Jalen Williams", "PTS": 2.8, "AST": 1.2, "PRA": 4.0},
    "Nikola Jokic": {"out_player": "Jamal Murray", "PTS": 3.2, "AST": 1.8, "PRA": 5.0},
    "LeBron James": {"out_player": "Anthony Davis", "PTS": 2.5, "AST": 1.0, "PRA": 3.5},
    "Stephen Curry": {"out_player": "Draymond Green", "PTS": 3.0, "AST": 1.2, "PRA": 4.2},
    "Giannis Antetokounmpo": {"out_player": "Khris Middleton", "PTS": 2.8, "REB": 1.0, "PRA": 3.8},
    "Kevin Durant": {"out_player": "Devin Booker", "PTS": 2.5, "AST": 0.8, "PRA": 3.3},
    "Jayson Tatum": {"out_player": "Jaylen Brown", "PTS": 2.2, "AST": 0.8, "PRA": 3.0},
    "Damian Lillard": {"out_player": "Giannis Antetokounmpo", "PTS": 3.0, "AST": 1.5, "PRA": 4.5},
}

PLAYER_TEAM_MAP = {
    "LeBron James": "LAL", "Anthony Davis": "LAL", "Austin Reaves": "LAL", "D'Angelo Russell": "LAL",
    "Luka Doncic": "LAL", "Kyrie Irving": "DAL",
    "Nikola Jokic": "DEN", "Jamal Murray": "DEN", "Michael Porter Jr.": "DEN", "Aaron Gordon": "DEN",
    "Shai Gilgeous-Alexander": "OKC", "Jalen Williams": "OKC", "Chet Holmgren": "OKC", "Luguentz Dort": "OKC",
    "Giannis Antetokounmpo": "MIL", "Damian Lillard": "MIL", "Khris Middleton": "MIL", "Brook Lopez": "MIL",
    "Jayson Tatum": "BOS", "Jaylen Brown": "BOS", "Kristaps Porzingis": "BOS", "Derrick White": "BOS",
    "Stephen Curry": "GSW", "Draymond Green": "GSW", "Andrew Wiggins": "GSW",
    "Klay Thompson": "DAL",
    "Kevin Durant": "PHX", "Devin Booker": "PHX", "Bradley Beal": "PHX", "Jusuf Nurkic": "PHX",
    "Paul George": "PHI",
    "Donovan Mitchell": "CLE", "Darius Garland": "CLE", "Evan Mobley": "CLE", "Jarrett Allen": "CLE",
    "Jimmy Butler": "MIA", "Bam Adebayo": "MIA", "Tyler Herro": "MIA", "Caleb Martin": "MIA",
    "Trae Young": "ATL", "Dejounte Murray": "ATL", "Clint Capela": "ATL", "Bogdan Bogdanovic": "ATL",
    "Ja Morant": "MEM", "Jaren Jackson Jr.": "MEM", "Desmond Bane": "MEM", "Marcus Smart": "MEM",
    "Zion Williamson": "NOP", "Brandon Ingram": "NOP", "CJ McCollum": "NOP", "Jonas Valanciunas": "NOP",
    "Kawhi Leonard": "LAC", "James Harden": "LAC",
    "Joel Embiid": "PHI", "Tyrese Maxey": "PHI", "Tobias Harris": "PHI", "Kelly Oubre Jr.": "PHI",
    "Karl-Anthony Towns": "MIN", "Anthony Edwards": "MIN", "Rudy Gobert": "MIN", "Mike Conley": "MIN",
    "Domantas Sabonis": "SAC", "De'Aaron Fox": "SAS", "Keegan Murray": "SAC", "Harrison Barnes": "SAC",
    "Victor Wembanyama": "SAS", "Cade Cunningham": "DET", "Jalen Brunson": "NYK", "Paolo Banchero": "ORL",
    "Scottie Barnes": "TOR", "Alperen Sengun": "HOU", "Franz Wagner": "ORL", "Tyrese Haliburton": "IND",
    "Pascal Siakam": "IND",
}

BLOWOUT_THRESHOLDS = {
    "NBA": 12, "NFL": 14, "MLB": 3,
    "NHL": 2, "WNBA": 10
}

NEGATIVE_CORRELATIONS = {
    ("Nikola Jokic", "Joel Embiid"): -0.3,
    ("Luka Doncic", "Shai Gilgeous-Alexander"): -0.2,
    ("Jayson Tatum", "Giannis Antetokounmpo"): -0.2,
}

POSITIVE_CORRELATIONS = {
    ("Luka Doncic", "Kyrie Irving"): 0.4,
    ("Nikola Jokic", "Jamal Murray"): 0.35,
    ("Stephen Curry", "Klay Thompson"): 0.3,
    ("Jayson Tatum", "Jaylen Brown"): 0.35,
    ("Shai Gilgeous-Alexander", "Jalen Williams"): 0.3,
    ("LeBron James", "Anthony Davis"): 0.3,
    ("Giannis Antetokounmpo", "Damian Lillard"): 0.3,
    ("Tyrese Haliburton", "Pascal Siakam"): 0.3,
}

SAME_PLAYER_STAT_CORRELATION = {
    ("PTS", "PRA"): 0.85, ("PRA", "PTS"): 0.85,
    ("PTS", "AST"): 0.45, ("AST", "PTS"): 0.45,
    ("PTS", "REB"): 0.30, ("REB", "PTS"): 0.30,
    ("REB", "AST"): 0.15, ("AST", "REB"): 0.15,
    ("PTS", "THREE_PT"): 0.70, ("THREE_PT", "PTS"): 0.70,
    ("PTS", "BLK"): 0.10, ("PTS", "STL"): 0.10,
    ("REB", "BLK"): 0.35, ("AST", "TOV"): 0.55,
    ("GOALS", "SOG"): 0.75, ("SOG", "GOALS"): 0.75,
    ("PTS", "SOG"): 0.80,
    ("HR", "RBI"): 0.65, ("RBI", "HR"): 0.65,
    ("H", "RBI"): 0.45, ("H", "R"): 0.50,
    ("PASS_YDS", "TD"): 0.55, ("RUSH_YDS", "TD"): 0.45,
    ("REC_YDS", "TD"): 0.40,
}

WIND_HR_THRESHOLDS = {"strong_out": 15, "strong_in": 15}

MLB_BALLPARKS = {
    "New York Yankees": {"city": "New York", "outdoor": True},
    "New York Mets": {"city": "New York", "outdoor": True},
    "Boston Red Sox": {"city": "Boston", "outdoor": True},
    "Chicago Cubs": {"city": "Chicago", "outdoor": True},
    "Chicago White Sox": {"city": "Chicago", "outdoor": True},
    "Los Angeles Dodgers": {"city": "Los Angeles", "outdoor": True},
    "Los Angeles Angels": {"city": "Anaheim", "outdoor": True},
    "San Francisco Giants": {"city": "San Francisco", "outdoor": True},
    "Seattle Mariners": {"city": "Seattle", "outdoor": True},
    "Texas Rangers": {"city": "Arlington", "outdoor": True},
    "Houston Astros": {"city": "Houston", "outdoor": False},
    "Toronto Blue Jays": {"city": "Toronto", "outdoor": True},
    "Baltimore Orioles": {"city": "Baltimore", "outdoor": True},
    "Tampa Bay Rays": {"city": "St Petersburg", "outdoor": False},
    "Cleveland Guardians": {"city": "Cleveland", "outdoor": True},
    "Detroit Tigers": {"city": "Detroit", "outdoor": True},
    "Kansas City Royals": {"city": "Kansas City", "outdoor": True},
    "Minnesota Twins": {"city": "Minneapolis", "outdoor": False},
    "Milwaukee Brewers": {"city": "Milwaukee", "outdoor": False},
    "St. Louis Cardinals": {"city": "St Louis", "outdoor": True},
    "Cincinnati Reds": {"city": "Cincinnati", "outdoor": True},
    "Pittsburgh Pirates": {"city": "Pittsburgh", "outdoor": True},
    "Philadelphia Phillies": {"city": "Philadelphia", "outdoor": True},
    "Washington Nationals": {"city": "Washington", "outdoor": True},
    "Atlanta Braves": {"city": "Atlanta", "outdoor": True},
    "Miami Marlins": {"city": "Miami", "outdoor": False},
    "Colorado Rockies": {"city": "Denver", "outdoor": True},
    "Arizona Diamondbacks": {"city": "Phoenix", "outdoor": False},
    "San Diego Padres": {"city": "San Diego", "outdoor": True},
    "Oakland Athletics": {"city": "Oakland", "outdoor": True},
}

MLB_PLAYER_TEAM_MAP = {
    "Aaron Judge": "New York Yankees",
    "Shohei Ohtani": "Los Angeles Dodgers",
    "Mookie Betts": "Los Angeles Dodgers",
    "Freddie Freeman": "Los Angeles Dodgers",
    "Juan Soto": "New York Mets",
    "Bryce Harper": "Philadelphia Phillies",
    "Ronald Acuna Jr.": "Atlanta Braves",
    "Jose Ramirez": "Cleveland Guardians",
    "Pete Alonso": "New York Mets",
    "Vladimir Guerrero Jr.": "Toronto Blue Jays",
    "Francisco Lindor": "New York Mets",
    "Bobby Witt Jr.": "Kansas City Royals",
    "Gunnar Henderson": "Baltimore Orioles",
    "Elly De La Cruz": "Cincinnati Reds",
    "Corbin Carroll": "Arizona Diamondbacks",
    "Paul Skenes": "Pittsburgh Pirates",
    "Spencer Strider": "Atlanta Braves",
    "Gerrit Cole": "New York Yankees",
    "Zack Wheeler": "Philadelphia Phillies",
    "Tarik Skubal": "Detroit Tigers",
    "Framber Valdez": "Houston Astros",
    "Logan Webb": "San Francisco Giants",
    "Yoshinobu Yamamoto": "Los Angeles Dodgers",
    "Luis Castillo": "Seattle Mariners",
    "Dylan Cease": "San Diego Padres",
    "Corbin Burnes": "Baltimore Orioles",
    "Hunter Brown": "Houston Astros",
    "Julio Rodriguez": "Seattle Mariners",
    "Yordan Alvarez": "Houston Astros",
    "Kyle Tucker": "Houston Astros",
    "Trea Turner": "Philadelphia Phillies",
    "Nolan Arenado": "St. Louis Cardinals",
    "Marcus Semien": "Texas Rangers",
    "Corey Seager": "Texas Rangers",
}

WNBA_PLAYER_IDS = {
    "A'ja Wilson": 1628932,
    "Breanna Stewart": 1626399,
    "Sabrina Ionescu": 1629887,
    "Kelsey Plum": 1628928,
    "Napheesa Collier": 1628886,
    "Caitlin Clark": 1641767,
    "Angel Reese": 1641768,
    "Alyssa Thomas": 1628961,
    "Jackie Young": 1629313,
    "Jewell Loyd": 1628932,
    "Kahleah Copper": 1628961,
    "Aliyah Boston": 1641769,
    "Rhyne Howard": 1641770,
    "Jonquel Jones": 1628886,
}

MLB_PLAYER_IDS = {
    "Aaron Judge": 592450, "Shohei Ohtani": 660271,
    "Mookie Betts": 605141, "Freddie Freeman": 518692,
    "Juan Soto": 665742, "Bryce Harper": 547180,
    "Ronald Acuna Jr.": 660670, "Jose Ramirez": 608070,
    "Pete Alonso": 624413, "Vladimir Guerrero Jr.": 665489,
    "Francisco Lindor": 596019, "Bobby Witt Jr.": 677951,
    "Gunnar Henderson": 683002, "Elly De La Cruz": 682829,
    "Corbin Carroll": 682998, "Paul Skenes": 694973,
    "Gerrit Cole": 543037, "Zack Wheeler": 554430,
    "Tarik Skubal": 669373, "Framber Valdez": 664285,
    "Logan Webb": 657277, "Luis Castillo": 622491,
    "Julio Rodriguez": 677594, "Yordan Alvarez": 670541,
    "Kyle Tucker": 663656, "Trea Turner": 607208,
    "Nolan Arenado": 571448, "Marcus Semien": 543760,
    "Corey Seager": 608369,
}

NHL_PLAYER_IDS = {
    "Connor McDavid": 8478402, "Leon Draisaitl": 8477934,
    "Nathan MacKinnon": 8477492, "David Pastrnak": 8477956,
    "Nikita Kucherov": 8476453, "Auston Matthews": 8479318,
    "Mitch Marner": 8481522, "Cale Makar": 8480069,
    "Kirill Kaprizov": 8481600, "Mikko Rantanen": 8481467,
    "Matthew Tkachuk": 8481559, "Brayden Point": 8478010,
    "Sam Reinhart": 8477998, "Aleksander Barkov": 8477493,
    "Brady Tkachuk": 8481528,
}

NBA_TEAM_PACE = {
    "MEM": 102.8, "SAC": 101.5, "BOS": 101.2,
    "DAL": 100.8, "OKC": 100.5, "LAL": 100.2,
    "DEN": 100.0, "PHX": 99.8, "GSW": 99.5,
    "NOP": 99.2, "ATL": 99.0, "IND": 98.8,
    "MIN": 98.5, "TOR": 98.3, "ORL": 98.0,
    "HOU": 97.8, "SAS": 97.5, "DET": 97.3,
    "LAC": 97.1, "MIL": 98.1, "CLE": 98.1,
    "NYK": 97.8, "MIA": 97.3, "PHI": 97.0,
}

NBA_POWER_RATINGS = {
    "BOS": 112.3, "OKC": 110.8, "DEN": 109.2,
    "MIN": 108.5, "CLE": 107.9, "NYK": 107.2,
    "IND": 106.8, "MIL": 106.1, "PHX": 105.8,
    "LAL": 105.4, "GSW": 104.9, "MEM": 104.6,
    "NOP": 103.8, "SAC": 103.5, "DAL": 103.2,
    "MIA": 102.9, "ATL": 102.4, "PHI": 102.1,
    "CHI": 101.8, "TOR": 101.5, "ORL": 101.2,
    "HOU": 100.9, "LAC": 100.6, "BKN": 100.2,
    "DET": 99.8, "CHA": 99.5, "SAS": 99.2,
    "POR": 98.9, "UTA": 98.5, "WAS": 98.1,
}

NBA_POSITION_DEFENSE = {
    "BOS": {"PG": 20.1, "SG": 19.8, "SF": 18.9, "PF": 20.2, "C": 21.4},
    "OKC": {"PG": 19.4, "SG": 20.1, "SF": 19.3, "PF": 19.8, "C": 22.1},
    "DEN": {"PG": 21.2, "SG": 21.8, "SF": 20.4, "PF": 21.1, "C": 23.2},
    "MIL": {"PG": 22.1, "SG": 21.4, "SF": 20.8, "PF": 21.5, "C": 24.1},
    "LAL": {"PG": 20.8, "SG": 21.2, "SF": 20.1, "PF": 22.4, "C": 23.8},
    "PHX": {"PG": 22.8, "SG": 23.1, "SF": 21.9, "PF": 22.2, "C": 24.8},
    "GSW": {"PG": 21.4, "SG": 22.2, "SF": 21.1, "PF": 22.8, "C": 24.2},
    "MIA": {"PG": 20.4, "SG": 21.1, "SF": 19.8, "PF": 20.9, "C": 22.8},
    "MEM": {"PG": 23.2, "SG": 22.8, "SF": 22.1, "PF": 23.4, "C": 25.1},
    "ATL": {"PG": 24.1, "SG": 23.8, "SF": 22.9, "PF": 23.2, "C": 25.4},
}

PLAYOFF_DEFENSE_WARNING = (
    "⚠️ PLAYOFF MODE: Hardcoded position defense "
    "data reflects regular season. Playoff defensive "
    "schemes change significantly. Search current "
    "matchup defense before trusting these numbers."
)

LEAGUE_AVG_POSITION = {"PG": 22.1, "SG": 21.8, "SF": 21.2, "PF": 22.0, "C": 23.5}

NBA_PLAYER_POSITIONS = {
    "Nikola Jokic": "C", "LeBron James": "SF", "Stephen Curry": "PG",
    "Giannis Antetokounmpo": "PF", "Luka Doncic": "PG",
    "Shai Gilgeous-Alexander": "PG", "Jayson Tatum": "SF",
    "Anthony Davis": "C", "Donovan Mitchell": "SG", "Damian Lillard": "PG",
    "Trae Young": "PG", "Devin Booker": "SG", "Joel Embiid": "C",
    "Tyrese Maxey": "PG", "Bam Adebayo": "C", "Ja Morant": "PG",
    "Zion Williamson": "PF", "Karl-Anthony Towns": "C",
    "Anthony Edwards": "SG", "Paolo Banchero": "PF",
    "Cade Cunningham": "PG", "Victor Wembanyama": "C",
    "Jalen Brunson": "PG", "Tyrese Haliburton": "PG",
    "Kevin Durant": "SF", "Jimmy Butler": "SF", "Kawhi Leonard": "SF",
    "Rudy Gobert": "C", "Jaylen Brown": "SG", "Darius Garland": "PG",
    "Evan Mobley": "C", "Jarrett Allen": "C", "Tyler Herro": "SG",
    "Dejounte Murray": "PG", "Jaren Jackson Jr.": "PF",
    "Desmond Bane": "SG", "CJ McCollum": "SG", "Paul George": "SF",
    "James Harden": "PG", "Tobias Harris": "SF",
    "Domantas Sabonis": "C", "De'Aaron Fox": "PG",
    "Keegan Murray": "SF", "Franz Wagner": "SF",
    "Scottie Barnes": "PF", "Alperen Sengun": "C",
    "Jalen Williams": "SG", "Chet Holmgren": "C", "Luguentz Dort": "SG",
    "Khris Middleton": "SF", "Brook Lopez": "C",
    "Kristaps Porzingis": "C", "Derrick White": "PG",
    "Andrew Wiggins": "SF", "Draymond Green": "PF",
    "Aaron Gordon": "PF", "Michael Porter Jr.": "SF",
    "Jamal Murray": "PG", "Caleb Martin": "SF",
    "Bogdan Bogdanovic": "SG", "Marcus Smart": "PG",
    "Jonas Valanciunas": "C", "Harrison Barnes": "SF",
    "Mike Conley": "PG", "Pascal Siakam": "PF",
}

NBA_REFEREE_TENDENCIES = {
    "Tony Brothers": {"foul_rate": "high", "pts_adj": 0.03},
    "Scott Foster": {"foul_rate": "high", "pts_adj": 0.03},
    "Marc Davis": {"foul_rate": "high", "pts_adj": 0.02},
    "Ken Mauer": {"foul_rate": "high", "pts_adj": 0.03},
    "James Capers": {"foul_rate": "high", "pts_adj": 0.02},
    "Bill Kennedy": {"foul_rate": "low", "pts_adj": -0.02},
    "Derrick Stafford": {"foul_rate": "low", "pts_adj": -0.02},
    "Kevin Scott": {"foul_rate": "low", "pts_adj": -0.02},
    "Jonathan Sterling": {"foul_rate": "low", "pts_adj": -0.01},
    "Tre Maddox": {"foul_rate": "low", "pts_adj": -0.01},
}

MLB_UMPIRE_TENDENCIES = {
    "Angel Hernandez": {"zone": "tight", "so_adj": -0.04},
    "CB Bucknor": {"zone": "tight", "so_adj": -0.04},
    "Vic Carapazza": {"zone": "tight", "so_adj": -0.03},
    "Jerry Meals": {"zone": "tight", "so_adj": -0.03},
    "Sam Holbrook": {"zone": "tight", "so_adj": -0.02},
    "Laz Diaz": {"zone": "large", "so_adj": 0.04},
    "Tim Welke": {"zone": "large", "so_adj": 0.03},
    "Lance Barrett": {"zone": "large", "so_adj": 0.04},
    "Dan Bellino": {"zone": "large", "so_adj": 0.03},
    "Junior Valentine": {"zone": "large", "so_adj": 0.02},
}

MLB_PITCHER_ERA = {
    "Justin Verlander": 3.20, "Gerrit Cole": 3.10, "Zack Wheeler": 3.15,
    "Shane Bieber": 3.30, "Dylan Cease": 3.40, "Pablo Lopez": 3.50,
    "Logan Webb": 3.20, "Tarik Skubal": 2.90, "Paul Skenes": 2.80,
    "Framber Valdez": 3.10, "Corbin Burnes": 3.00, "Spencer Strider": 3.05,
    "Luis Castillo": 3.40, "Yoshinobu Yamamoto": 3.00, "Kevin Gausman": 3.30,
    "Sandy Alcantara": 3.20, "Max Fried": 3.15, "Hunter Brown": 3.60,
    "George Kirby": 3.40, "Chris Sale": 3.50, "Sonny Gray": 3.70,
    "Blake Snell": 3.20, "Tony Gonsolin": 3.80, "Joe Ryan": 3.60,
    "Nestor Cortes": 3.90, "Jordan Montgomery": 3.80, "Miles Mikolas": 4.10,
    "Lance Lynn": 4.20,
}

MLB_PARK_FACTORS = {
    "Colorado Rockies": 1.15, "Cincinnati Reds": 1.08,
    "Texas Rangers": 1.06, "Chicago Cubs": 1.05,
    "Boston Red Sox": 1.04, "Philadelphia Phillies": 1.03,
    "New York Yankees": 1.02, "Atlanta Braves": 1.02,
    "Los Angeles Dodgers": 0.98, "San Francisco Giants": 0.96,
    "Oakland Athletics": 0.95, "Seattle Mariners": 0.94,
    "New York Mets": 0.97, "Houston Astros": 0.97,
    "Tampa Bay Rays": 0.96, "Minnesota Twins": 0.99,
    "Miami Marlins": 0.95, "San Diego Padres": 0.96,
}
MLB_PARK_DEFAULT = 1.00

NHL_TEAM_GOALS_FOR = {
    "EDM": 3.8, "BOS": 3.5, "TOR": 3.4,
    "COL": 3.6, "NYR": 3.3, "FLA": 3.2,
    "DAL": 3.1, "VGK": 3.0, "CAR": 3.2,
    "NJD": 3.1, "WPG": 3.3, "SEA": 3.0,
    "MIN": 2.9, "OTT": 3.1, "LAK": 2.9,
    "ANA": 2.7, "CHI": 2.7, "SJS": 2.6,
}

NHL_TEAM_GOALS_AGAINST = {
    "BOS": 2.5, "CAR": 2.6, "FLA": 2.7,
    "DAL": 2.6, "VGK": 2.7, "NYR": 2.8,
    "COL": 2.9, "EDM": 3.1, "TOR": 3.0,
    "MIN": 2.8, "WPG": 2.9, "NJD": 2.8,
    "SEA": 2.9, "LAK": 2.8, "OTT": 3.0,
    "ANA": 3.3, "CHI": 3.4, "SJS": 3.5,
}
NHL_GOALS_DEFAULT = 3.0

LEAGUE_AVG_ERA = 4.25

try:
    from oddswrap import OddsClient, Sport
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

ESPN_ATHLETE_IDS = {
    "NBA": {
        "Nikola Jokic": 3136776, "LeBron James": 1966,
        "Stephen Curry": 3975, "Giannis Antetokounmpo": 3032977,
        "Luka Doncic": 3945274, "Shai Gilgeous-Alexander": 4277905,
        "Jayson Tatum": 4065648, "Anthony Davis": 6583,
        "Donovan Mitchell": 3908809, "Damian Lillard": 6606,
        "Trae Young": 4277956, "Devin Booker": 3136193,
        "Joel Embiid": 3059318, "Tyrese Maxey": 4432816,
        "Bam Adebayo": 3907387, "Ja Morant": 4279888,
        "Zion Williamson": 4395725, "Karl-Anthony Towns": 3136196,
        "Anthony Edwards": 4594268, "Paolo Banchero": 4703249,
        "Cade Cunningham": 4432166, "Victor Wembanyama": 5105540,
        "Jalen Brunson": 3934648, "Tyrese Haliburton": 4395724,
    },
    "NFL": {
        "Patrick Mahomes": 3139477, "Josh Allen": 3918298,
        "Jalen Hurts": 4040715, "Lamar Jackson": 3916387,
        "Joe Burrow": 3915511, "Justin Herbert": 4038941,
        "Dak Prescott": 2577417, "Christian McCaffrey": 3054211,
        "Derrick Henry": 3054220, "Tyreek Hill": 3054978,
        "Justin Jefferson": 4241478, "CeeDee Lamb": 4241389,
        "Travis Kelce": 15847,
    }
}
# =========================
# FUNCTIONS
# =========================

def ewma_average(game_values, decay=0.85, sport=None):
    if not game_values:
        return 0.0
    if sport:
        decay = SPORT_EWMA_DECAY.get(sport, decay)
    weights = [decay**i for i in range(len(game_values))]
    weighted = sum(v * w for v, w in zip(reversed(game_values), weights))
    return round(weighted / sum(weights), 2)

def compute_std_dev(game_values, decay=0.85, sport=None):
    if not game_values or len(game_values) < 3:
        return None
    if sport:
        decay = SPORT_EWMA_DECAY.get(sport, decay)
    weights = [decay**i for i in range(len(game_values))]
    total_weight = sum(weights)
    weighted_mean = sum(v * w for v, w in zip(reversed(game_values), weights)) / total_weight
    weighted_var = sum(w * (v - weighted_mean)**2 for v, w in zip(reversed(game_values), weights)) / total_weight
    return round(weighted_var**0.5, 3)

def compute_fair_prob(line, avg, std_dev, side="OVER"):
    if avg <= 0:
        return 0.5
    if std_dev is None or std_dev <= 0:
        std_dev = avg * 0.40
    adjusted_line = line + 0.5 if (line == int(line)) else line
    if side.upper() == "OVER":
        prob = 1 - scipy_stats.norm.cdf(adjusted_line, loc=avg, scale=std_dev)
    else:
        prob = scipy_stats.norm.cdf(adjusted_line, loc=avg, scale=std_dev)
    return round(max(0.30, min(0.70, prob)), 4)

def compute_market_edge(fair_prob, side="OVER"):
    market_implied = 0.524
    if side.upper() == "OVER":
        edge = fair_prob - market_implied
    else:
        edge = fair_prob - market_implied
    return round(edge, 4)

def devig_odds(american_odds):
    if american_odds is None:
        return None
    try:
        odds = float(american_odds)
        if odds > 0:
            implied = 100 / (odds + 100)
        else:
            implied = abs(odds) / (abs(odds) + 100)
        return round(implied, 4)
    except:
        return None

def compute_consensus_probability(sport, player_name, stat_name, line_val, side="OVER"):
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
    except:
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
        over_implied = devig_odds(over_odds)
        under_implied = devig_odds(under_odds)
        if (over_implied is None or under_implied is None):
            continue
        total_implied = over_implied + under_implied
        if total_implied <= 0:
            continue
        over_no_vig = over_implied / total_implied
        if side.upper() == "OVER":
            book_probs.append(over_no_vig)
        else:
            book_probs.append(1 - over_no_vig)
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
    consensus = round(max(0.30, min(0.70, consensus)), 4)
    return consensus, books_used

def check_prop_line_fairness(line, consensus_prob, side="OVER"):
    if consensus_prob is None:
        return "UNKNOWN", ""
    market_implied = 0.524
    if side.upper() == "OVER":
        gap = market_implied - consensus_prob
    else:
        gap = market_implied - (1 - consensus_prob)
    if gap >= 0.07:
        return "BAD", f"⚠️ Market prices this at {consensus_prob:.1%} — line is {gap:.1%} worse than market fair value. Reduce sizing or skip."
    elif gap >= 0.04:
        return "CAUTION", f"📊 Market prices this at {consensus_prob:.1%} — slightly unfavorable line. Verify before betting."
    else:
        return "GOOD", f"✅ Line is fair vs market ({consensus_prob:.1%} consensus)"

def check_daily_risk_limits(sport=None):
    bankroll = st.session_state.bankroll
    day_start = st.session_state.day_start_br
    if day_start > 0:
        daily_change = (bankroll - day_start) / day_start
        if daily_change <= -DAILY_RISK_CONTROLS["max_daily_loss_pct"]:
            return False, f"🛑 Daily stop-loss hit ({daily_change:.1%}). No more bets today."
        if daily_change >= DAILY_RISK_CONTROLS["stop_win_pct"]:
            return False, f"🏆 Stop-win triggered (+{daily_change:.1%}). Lock in today's profits."
    today = date.today().strftime("%Y-%m-%d")
    today_locks = [l for l in st.session_state.history if l.get("timestamp", "").startswith(today)]
    today_locks += [l for l in st.session_state.locks if l.get("timestamp", "").startswith(today)]
    if len(today_locks) >= DAILY_RISK_CONTROLS["max_locks_per_day"]:
        return False, f"🛑 Max {DAILY_RISK_CONTROLS['max_locks_per_day']} locks per day reached."
    if sport:
        sport_locks = [l for l in st.session_state.locks if l.get("sport") == sport]
        if len(sport_locks) >= DAILY_RISK_CONTROLS["max_same_sport_locks"]:
            return False, f"⚠️ Max {DAILY_RISK_CONTROLS['max_same_sport_locks']} {sport} locks reached."
    return True, ""

def save_to_gist(data_type, data):
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return False
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        payload = {"files": {f"betcouncil_{data_type}.json": {"content": json.dumps(data, indent=2)}}}
        resp = requests.patch(f"{GIST_API}/{GITHUB_GIST_ID}", headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except:
        return False

def load_from_gist(data_type, default):
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return None
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        resp = requests.get(f"{GIST_API}/{GITHUB_GIST_ID}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        files = resp.json().get("files", {})
        file_data = files.get(f"betcouncil_{data_type}.json", {})
        content = file_data.get("content", "")
        if content:
            return json.loads(content)
        return None
    except:
        return None

def load_json_data(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json_data(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_api_counter(counter_path):
    today = date.today().strftime("%Y-%m-%d")
    current_month = date.today().strftime("%Y-%m")
    if os.path.exists(counter_path):
        try:
            with open(counter_path, "r") as f:
                counter = json.load(f)
            if counter.get("date") != today:
                counter["date"] = today
                counter["count"] = 0
            if counter.get("month") != current_month:
                counter["month"] = current_month
                counter["monthly_count"] = 0 if "monthly_count" in counter else 0
            return counter
        except:
            pass
    return {"count": 0, "date": today, "month": current_month, "monthly_count": 0}

def increment_api_counter(counter_path):
    counter = get_api_counter(counter_path)
    counter["count"] += 1
    counter["monthly_count"] = counter.get("monthly_count", 0) + 1
    save_json_data(counter_path, counter)
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

def compute_tier_stats(history):
    stats = {}
    for bet in history:
        tier = bet.get("tier", "UNKNOWN")
        outcome = bet.get("outcome")
        predicted_prob = bet.get("prob", 0.5)
        if outcome not in ("WIN", "LOSS"):
            continue
        if tier not in stats:
            stats[tier] = {"outcomes": [], "predicted": []}
        stats[tier]["outcomes"].append(1 if outcome == "WIN" else 0)
        stats[tier]["predicted"].append(predicted_prob)
    result = {}
    for tier, data in stats.items():
        n = len(data["outcomes"])
        if n == 0:
            continue
        hit_rate = sum(data["outcomes"]) / n
        avg_predicted = sum(data["predicted"]) / n
        sem = (hit_rate * (1 - hit_rate) / n) ** 0.5 if n > 0 else None
        calibration_error = hit_rate - avg_predicted
        result[tier] = {"n": n, "hit_rate": round(hit_rate, 3), "avg_predicted": round(avg_predicted, 3), "sem": round(sem, 3) if sem else None, "calibration_error": round(calibration_error, 3)}
    return result

def compute_sem_for_tier(tier_stats, tier):
    if tier not in tier_stats:
        return "—", 0
    stats = tier_stats[tier]
    n = stats["n"]
    if n < 5:
        return "—", n
    sem = stats["sem"]
    if sem is None:
        return "—", n
    return f"±{sem:.3f}", n

def adjusted_edge(raw_edge, sport, tier, stat_norm, history):
    relevant = [b for b in history if b.get("tier") == tier and b.get("sport") == sport]
    n = len(relevant)
    if n < 20:
        return raw_edge, False
    outcomes = [1 if b["outcome"] == "WIN" else 0 for b in relevant]
    predicted = [b.get("prob", 0.5) for b in relevant]
    hit_rate = sum(outcomes) / n
    avg_predicted = sum(predicted) / n
    calibration_error = hit_rate - avg_predicted
    adjustment = calibration_error * min(1.0, n / 100)
    return raw_edge + adjustment, True

def normalize_name(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+(jr|sr|ii|iii)\.?$", "", s.lower().strip())
    s = s.replace("-", " ").replace(".", "").replace("'", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def find_player_avg(player_name, avgs_dict):
    if player_name in avgs_dict:
        return avgs_dict[player_name], False
    norm = normalize_name(player_name)
    for key, val in avgs_dict.items():
        if normalize_name(key) == norm:
            return val, False
    return {}, True

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
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data and data.get("data"):
                with open(cache_path, "wb") as f:
                    pickle.dump(data, f)
            return data
        return None
    except:
        return None

def poisson_prob_over(line, avg):
    if avg <= 0:
        return 0.5
    k = int(line)
    try:
        p_under = sum((avg**i * exp(-avg)) / factorial(i) for i in range(k + 1))
        return round(1 - p_under, 4)
    except:
        return 0.5

def prizepicks_breakeven_prob(n_picks=2):
    multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)
    return round((1 / multiplier) ** (1 / n_picks), 4)

def calculate_prizepicks_ev(fair_prob, n_picks=2):
    breakeven = prizepicks_breakeven_prob(n_picks)
    return round(fair_prob - breakeven, 4)

def kelly_unit_prizepicks(prob, bankroll, n_picks=2):
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

def kelly_unit(prob, bankroll, n_picks=2):
    return kelly_unit_prizepicks(prob, bankroll, n_picks)

def get_tier(edge, sport="NBA"):
    thresholds = TIER_THRESHOLDS.get(sport, TIER_THRESHOLDS["NBA"])
    if edge >= thresholds["SOVEREIGN"]: return "SOVEREIGN"
    if edge >= thresholds["ELITE"]: return "ELITE"
    if edge >= thresholds["APPROVED"]: return "APPROVED"
    if edge >= thresholds["LEAN"]: return "LEAN"
    return "PASS"

def parlay_prob(probs):
    combined = 1.0
    for p in probs:
        combined *= p
    return combined

def parlay_payout(probs, odds=-110):
    combined = parlay_prob(probs)
    if combined <= 0:
        return 0
    fair_decimal = 1 / combined
    if fair_decimal >= 2.0:
        return round((fair_decimal - 1) * 100)
    else:
        return round(-100 / (fair_decimal - 1))

def active_unit():
    return round(st.session_state.bankroll * KELLY_FRACTION * KELLY_CAP, 2)

def get_session_time():
    elapsed = int(time.time() - st.session_state.session_start)
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

def get_daily_change():
    if st.session_state.day_start_br == 0:
        return "0.0%"
    change = (st.session_state.bankroll - st.session_state.day_start_br) / st.session_state.day_start_br * 100
    return f"{'+' if change >= 0 else ''}{change:.1f}"

def blowout_risk_adjustment(spread, sport, player_team, home_teams, away_teams, matchup):
    if not spread or spread == "—":
        return 0.0
    try:
        spread_val = float(str(spread).replace("+", "").strip())
    except:
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

def record_clv(lock, current_props):
    player = lock.get("player", "")
    prop = lock.get("prop", "")
    locked_line = lock.get("line", 0)
    side = lock.get("side", "OVER")
    current_line = None
    for p in current_props:
        if (normalize_name(p.get("Player","")) == normalize_name(player) and p.get("Prop","") == prop):
            current_line = p.get("Line")
            break
    if current_line is None:
        return None
    clv = locked_line - current_line if side == "OVER" else current_line - locked_line
    clv_data = load_json_data(CLV_PATH, [])
    clv_data.append({
        "player": player, "prop": prop,
        "locked_line": locked_line, "closing_line": current_line,
        "side": side, "clv": round(clv, 1),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sport": lock.get("sport", ""), "tier": lock.get("tier", ""),
    })
    save_json_data(CLV_PATH, clv_data)
    return round(clv, 1)

def record_pinnacle_line(lock, props_data):
    player = lock.get("player", "")
    prop = lock.get("prop", "")
    side = lock.get("side", "OVER")
    locked_line = lock.get("line", 0)
    pinnacle_line = None
    for p in props_data:
        p_source = p.get("source", "")
        if "pinnacle" not in p_source.lower():
            continue
        if (normalize_name(p.get("Player", "")) != normalize_name(player)):
            continue
        if p.get("Prop", "") != prop:
            continue
        pinnacle_line = p.get("Line")
        break
    if pinnacle_line is None:
        return None
    if side == "OVER":
        pinnacle_clv = locked_line - pinnacle_line
    else:
        pinnacle_clv = pinnacle_line - locked_line
    record = {
        "player": player,
        "prop": prop,
        "locked_line": locked_line,
        "pinnacle_line": float(pinnacle_line),
        "pinnacle_clv": round(pinnacle_clv, 1),
        "side": side,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sport": lock.get("sport", ""),
        "tier": lock.get("tier", ""),
        "positive": pinnacle_clv > 0,
    }
    existing = load_json_data(PINNACLE_LINES_PATH, [])
    existing.append(record)
    save_json_data(PINNACLE_LINES_PATH, existing)
    return round(pinnacle_clv, 1)

def record_injury_performance(lock, outcome, injuries):
    player = lock.get("player", "")
    sport = lock.get("sport", "")
    injury_status = injuries.get(player, "")
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
    existing = load_json_data(INJURY_PERFORMANCE_PATH, [])
    existing.append(record)
    save_json_data(INJURY_PERFORMANCE_PATH, existing)

def analyze_injury_performance():
    data = load_json_data(INJURY_PERFORMANCE_PATH, [])
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

def record_signal_performance(lock, outcome):
    signals_active = lock.get("signals_active", {})
    if not signals_active:
        return
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "outcome": outcome,
        "win": 1 if outcome == "WIN" else 0,
        "sport": lock.get("sport", ""),
        "tier": lock.get("tier", ""),
        "edge": lock.get("edge", 0),
        "prob": lock.get("prob", 0),
        "signal_base_positive": int(signals_active.get("base_positive", False)),
        "signal_defense_positive": int(signals_active.get("defense_positive", False)),
        "signal_location_home": int(signals_active.get("location_home", False)),
        "signal_back_to_back": int(signals_active.get("back_to_back", False)),
        "signal_sharp_flag": int(signals_active.get("sharp_flag", False)),
        "signal_weather_active": int(signals_active.get("weather_active", False)),
        "signal_blowout_risk": int(signals_active.get("blowout_risk", False)),
        "signal_usage_boost": int(signals_active.get("usage_boost", False)),
    }
    performance = load_json_data(SIGNAL_PERFORMANCE_PATH, [])
    performance.append(record)
    save_json_data(SIGNAL_PERFORMANCE_PATH, performance)

def analyze_signal_performance():
    performance = load_json_data(SIGNAL_PERFORMANCE_PATH, [])
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

def compute_optimized_weights(sport):
    performance = load_json_data(SIGNAL_PERFORMANCE_PATH, [])
    sport_data = [p for p in performance if p.get("sport") == sport and p.get("outcome") in ("WIN", "LOSS")]
    if len(sport_data) < WEIGHT_OPTIMIZER_MIN_BETS:
        return None
    overall_wr = sum(r["win"] for r in sport_data) / len(sport_data)
    signal_to_weight = {
        "signal_base_positive": "base",
        "signal_defense_positive": "defense",
        "signal_location_home": "location",
        "signal_back_to_back": "rest",
        "signal_usage_boost": "pace",
    }
    base_weights = SPORT_SIGNAL_WEIGHTS.get(sport, SPORT_SIGNAL_WEIGHTS["NBA"]).copy()
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
        adjustment = lift * 0.30
        new_weight = base * (1 + adjustment)
        new_weight = max(0.01, min(0.60, new_weight))
        optimized[key] = round(new_weight, 3)
    total = sum(optimized.values())
    if total > 0:
        optimized = {k: round(v/total, 3) for k, v in optimized.items()}
    existing = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
    existing[sport] = {
        "weights": optimized,
        "n_bets": len(sport_data),
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overall_win_rate": round(overall_wr, 3),
        "lifts": {k: round(v, 4) for k, v in lifts.items()}
    }
    save_json_data(WEIGHT_OPTIMIZER_PATH, existing)
    return optimized

def get_active_weights(sport):
    optimizer_data = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
    sport_data = optimizer_data.get(sport, {})
    if sport_data and sport_data.get("weights"):
        n_bets = sport_data.get("n_bets", 0)
        if n_bets >= WEIGHT_OPTIMIZER_MIN_BETS:
            return sport_data["weights"], f"📊 Data-driven ({n_bets} bets)", "optimized"
    return SPORT_SIGNAL_WEIGHTS.get(sport, SPORT_SIGNAL_WEIGHTS["NBA"]), "⚠️ Hardcoded assumptions (insufficient data)", "hardcoded"

def market_efficiency_score(pp_line, ud_line, edge, sport):
    if pp_line and ud_line and ud_line > 0:
        line_spread = abs(pp_line - ud_line)
        inefficiency = min(line_spread / 1.5, 1.0)
    else:
        inefficiency = 0.3
    score = round((abs(edge) * 0.6) + (inefficiency * 0.4), 3)
    if inefficiency > 0.5 and abs(edge) >= 0.10:
        label = "🔥 Inefficient"
    elif inefficiency > 0.3 and abs(edge) >= 0.05:
        label = "⚡ Moderate"
    else:
        label = "✓ Efficient"
    return score, label

def calculate_lock_quality_score(prop):
    score = 0
    edge = prop.get("Edge", 0)
    if isinstance(edge, (int, float)):
        edge_pts = min(30, edge * 150)
        score += edge_pts
    n_games = prop.get("SampleSize", 0)
    if isinstance(n_games, (int, float)) and n_games > 0:
        sample_pts = min(25, n_games * 2.5)
        score += sample_pts
    elif prop.get("Quality") == "Lookup":
        score += 12
    eff_score = prop.get("EffScore", 0)
    if isinstance(eff_score, (int, float)):
        score += min(20, eff_score * 20)
    source = prop.get("source", "")
    if "PrizePicks" in source:
        score += 15
    elif "Underdog" in source:
        score += 10
    elif source.startswith("oddswrap"):
        score += 8
    elif source.startswith("OddsAPI"):
        score += 12
    elif source.startswith("BDL"):
        score += 10
    elif source.startswith("ParlayPlay_Alt"):
        score += 14
    elif source.startswith("ParlayPlay"):
        score += 12
    else:
        score += 5
    if prop.get("Injury"):
        score -= 10
    sharp = prop.get("SharpFlag", "")
    if sharp and "↑" in sharp:
        score += 5
    clv_adj = prop.get("CLVAdj", "")
    if clv_adj and "Boosted" in str(clv_adj):
        score += 3
    return round(min(100, max(0, score)), 1)

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
        adj_prob = max(0.30, min(0.70, adj_prob))
        adjusted_probs.append(adj_prob)
    return adjusted_probs, notes

def detect_game_script_contradictions(parlay_props, games):
    warnings = []
    if not parlay_props or not games:
        return warnings
    game_total_map = {}
    for game in games:
        matchup = game.get("Matchup","")
        total = game.get("Total","N/A")
        if total and total != "N/A":
            try:
                game_total_map[matchup] = float(total)
            except:
                pass
    for i, j in combinations(range(len(parlay_props)), 2):
        p1 = parlay_props[i]
        p2 = parlay_props[j]
        team1 = PLAYER_TEAM_MAP.get(p1["Player"],"")
        team2 = PLAYER_TEAM_MAP.get(p2["Player"],"")
        shared_game = None
        for matchup in game_total_map:
            if team1 and team1 in matchup:
                if team2 and team2 in matchup:
                    shared_game = matchup
                    break
        if not shared_game:
            continue
        game_total = game_total_map.get(shared_game, 0)
        stat1 = STAT_NORMALIZE.get((p1.get("Sport","NBA"), p1["Prop"]), p1["Prop"])
        stat2 = STAT_NORMALIZE.get((p2.get("Sport","NBA"), p2["Prop"]), p2["Prop"])
        if (stat1 == "PTS" and p1["Side"] == "OVER" and game_total > 0 and game_total < 210):
            warnings.append(f"⚠️ Contradiction: {p1['Player']} PTS OVER but game total {game_total} is very low. Low scoring game hurts PTS props.")
        pos1 = NBA_PLAYER_POSITIONS.get(p1["Player"],"")
        pos2 = NBA_PLAYER_POSITIONS.get(p2["Player"],"")
        if (pos1 == "C" and pos2 == "C" and team1 != team2 and stat1 == "REB" and stat2 == "REB" and p1["Side"] == "OVER" and p2["Side"] == "OVER"):
            warnings.append(f"⚠️ Contradiction: {p1['Player']} and {p2['Player']} are both centers in the same game going OVER rebounds. They compete for the same boards.")
        if team1 and team2 and team1 != team2:
            pace1 = NBA_TEAM_PACE.get(team1, 99.5)
            pace2 = NBA_TEAM_PACE.get(team2, 99.5)
            if (abs(pace1 - pace2) < 2 and stat1 in ["PTS","AST","REB"] and stat2 in ["PTS","AST","REB"]):
                pass
            elif (pace1 < 98 and p1["Side"] == "OVER" and stat1 == "PTS"):
                warnings.append(f"📊 Note: {p1['Player']} plays for slow-paced {team1} ({pace1:.1f} pace). Fewer possessions may limit counting stats.")
        for game in games:
            matchup = game.get("Matchup","")
            if team1 in matchup:
                spread = game.get("Spread","")
                if spread and spread != "N/A":
                    try:
                        spread_val = abs(float(str(spread).split()[-1]))
                        if (spread_val > 12 and stat1 == "PTS" and p1["Side"] == "OVER"):
                            fav_team = str(spread).split()[0]
                            if team1 == fav_team:
                                warnings.append(f"⚠️ Blowout risk: {p1['Player']} on {team1} favored by {spread_val}pts. May sit late if big lead develops.")
                    except:
                        pass
    return warnings

def track_line_movement(props):
    existing = load_json_data(LINE_MOVEMENT_PATH, {})
    movement = {}
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
        for lock in st.session_state.get("locks", []):
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

def fetch_weather_for_game(city, is_outdoor=True):
    if not is_outdoor:
        return None
    cache_key = hashlib.md5(f"weather_{city}_{date.today()}".encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}_weather.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 3:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    try:
        url = f"https://wttr.in/{city.replace(' ', '+')}?format=j1"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        current = data.get("current_condition", [{}])[0]
        weather = {"city": city, "wind_speed_mph": int(current.get("windspeedMiles", 0)),
                   "wind_dir": current.get("winddir16Point", "N"), "temp_f": int(current.get("temp_F", 70)),
                   "humidity": int(current.get("humidity", 50)), "fetched_at": datetime.now().strftime("%H:%M")}
        with open(cache_path, "wb") as f:
            pickle.dump(weather, f)
        return weather
    except:
        return None

def weather_edge_adjustment(weather, stat_norm, side="OVER"):
    if not weather:
        return 0.0, ""
    adjustment = 0.0
    notes = []
    wind_speed = weather.get("wind_speed_mph", 0)
    wind_dir = weather.get("wind_dir", "N")
    temp = weather.get("temp_f", 70)
    out_winds = ["SW", "WSW", "W", "WNW", "NW", "S", "SSW"]
    in_winds = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE"]
    if stat_norm == "HR":
        if wind_dir in out_winds and wind_speed >= 15:
            adj = min(0.08, wind_speed / 100)
            adjustment += adj if side == "OVER" else -adj
            notes.append(f"💨 Wind {wind_speed}mph out — HR boost")
        elif wind_dir in in_winds and wind_speed >= 15:
            adj = min(0.08, wind_speed / 100)
            adjustment -= adj if side == "OVER" else -adj
            notes.append(f"💨 Wind {wind_speed}mph in — HR penalty")
        if temp < 45:
            cold_adj = (45 - temp) / 100
            adjustment -= cold_adj if side == "OVER" else -cold_adj
            notes.append(f"🥶 Cold ({temp}°F) — HR penalty")
        elif temp > 90:
            hot_adj = (temp - 90) / 200
            adjustment += hot_adj if side == "OVER" else -hot_adj
            notes.append(f"🌡️ Hot ({temp}°F) — HR boost")
    elif stat_norm == "H":
        if wind_dir in out_winds and wind_speed >= 20:
            adjustment += 0.03 if side == "OVER" else -0.03
            notes.append("💨 Wind out — hits boost")
        elif wind_dir in in_winds and wind_speed >= 20:
            adjustment -= 0.03 if side == "OVER" else -0.03
            notes.append("💨 Wind in — hits penalty")
        if temp < 45:
            adjustment -= 0.03 if side == "OVER" else -0.03
    return round(adjustment, 3), " | ".join(notes)

def get_weighted_average(player_name, season_avg, last10_avg, is_playoff=False):
    if last10_avg is None:
        return season_avg
    if is_playoff:
        return last10_avg
    return {"PTS": round(last10_avg.get("PTS", season_avg.get("PTS", 0)) * 0.7 + season_avg.get("PTS", 0) * 0.3, 1),
            "REB": round(last10_avg.get("REB", season_avg.get("REB", 0)) * 0.7 + season_avg.get("REB", 0) * 0.3, 1),
            "AST": round(last10_avg.get("AST", season_avg.get("AST", 0)) * 0.7 + season_avg.get("AST", 0) * 0.3, 1),
            "PRA": round(last10_avg.get("PRA", season_avg.get("PRA", 0)) * 0.7 + season_avg.get("PRA", 0) * 0.3, 1)}

def get_recency_context(player_name, stat_norm, season_avg, rolling_avg, sport):
    if not rolling_avg or not season_avg:
        return "", "neutral"
    r_val = rolling_avg if isinstance(rolling_avg, (int, float)) else 0
    s_val = season_avg if isinstance(season_avg, (int, float)) else 0
    if s_val <= 0:
        return "", "neutral"
    diff_pct = (r_val - s_val) / s_val
    if diff_pct >= 0.20:
        return f"🔥 Hot streak (+{diff_pct:.0%} vs avg)", "hot"
    elif diff_pct <= -0.20:
        return f"🥶 Cold streak ({diff_pct:.0%} vs avg)", "cold"
    elif diff_pct >= 0.10:
        return f"📈 Trending up (+{diff_pct:.0%})", "warm"
    elif diff_pct <= -0.10:
        return f"📉 Trending down ({diff_pct:.0%})", "cooling"
    return "", "neutral"

def sample_size_confidence(n_games, sport):
    if n_games is None or n_games == 0:
        return 0.80
    n_games = max(0, int(n_games))
    full_n = 10
    min_conf = 0.80
    confidence = min(1.0, min_conf + (1.0 - min_conf) * (n_games ** 0.5) / (full_n ** 0.5))
    return round(confidence, 3)

def get_edge_staleness(last_scan_time):
    if not last_scan_time:
        return "⚫ Never loaded", "black"
    try:
        last = datetime.strptime(last_scan_time, "%H:%M:%S")
        now = datetime.now()
        elapsed_minutes = ((now.hour * 60 + now.minute) - (last.hour * 60 + last.minute))
        if elapsed_minutes < 0:
            elapsed_minutes += 1440
        if elapsed_minutes < 15:
            return f"🟢 Fresh ({elapsed_minutes}m ago)", "green"
        elif elapsed_minutes < 30:
            return f"🟡 Aging ({elapsed_minutes}m ago)", "yellow"
        elif elapsed_minutes < 60:
            return f"🟠 Stale ({elapsed_minutes}m ago)", "orange"
        else:
            return f"🔴 Very stale ({elapsed_minutes}m ago)", "red"
    except:
        return "⚫ Unknown", "black"

def check_portfolio_correlation(new_prop, existing_locks, player_team_map, positive_correlations, negative_correlations):
    warnings = []
    new_player = new_prop.get("Player", new_prop.get("player", ""))
    new_sport = new_prop.get("Sport", new_prop.get("sport", ""))
    new_team = player_team_map.get(new_player, "")
    for lock in existing_locks:
        if lock.get("status") != "PENDING":
            continue
        lock_player = lock.get("player", "")
        lock_sport = lock.get("sport", "")
        lock_team = player_team_map.get(lock_player, "")
        if lock_sport != new_sport:
            continue
        if lock_player == new_player:
            warnings.append(f"⚠️ You already have a lock on **{new_player}** — same player props are 25% correlated")
            continue
        if new_team and new_team == lock_team:
            pair = (new_player, lock_player)
            pair_rev = (lock_player, new_player)
            corr = (positive_correlations.get(pair) or positive_correlations.get(pair_rev) or 0.15)
            warnings.append(f"⚠️ **{new_player}** and **{lock_player}** are teammates ({corr:.0%} correlation). Combined probability reduced.")
        same_game_locks = [l for l in existing_locks if (l.get("sport") == new_sport and l.get("status") == "PENDING" and player_team_map.get(l.get("player",""), "") == new_team)]
        if len(same_game_locks) >= 2:
            warnings.append(f"🛑 You already have {len(same_game_locks)} locks from this game. High concentration risk.")
            break
    return warnings

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

def fetch_mlb_probable_pitchers():
    cache_path = os.path.join(CACHE_DIR, "mlb_pitchers.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 3:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    today_str = date.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?date={today_str}&sportId=1&hydrate=probablePitcher,team"
    pitchers = {}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for date_data in resp.json().get("dates", []):
            for game in date_data.get("games", []):
                away = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
                home = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "")
                away_pitcher = game.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("fullName", "")
                home_pitcher = game.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("fullName", "")
                if away:
                    pitchers[away] = {"pitcher": away_pitcher, "opponent": home, "home": False}
                if home:
                    pitchers[home] = {"pitcher": home_pitcher, "opponent": away, "home": True}
        if pitchers:
            with open(cache_path, "wb") as f:
                pickle.dump(pitchers, f)
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_mlb_probable_pitchers", "error": str(e)[:100]})
    return pitchers


def fetch_team_recent_defense(sport, team_abbrev, n_games=10):
    cache_key = f"recent_def_{sport}_{team_abbrev}_{n_games}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < ROLLING_DEFENSE_CACHE_HOURS:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    if sport != "NBA":
        return None
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/"
    }
    for season_type in ["Playoffs", "Regular+Season"]:
        url = f"https://stats.nba.com/stats/teamgamelogs?Season=2024-25&SeasonType={season_type}&TeamID=&LastNGames={n_games}&MeasureType=Defense&PerMode=PerGame"
        try:
            resp = requests.get(url, headers=nba_headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            for row in rows:
                abbrev = row[col.get("TEAM_ABBREVIATION", 0)]
                if abbrev == team_abbrev:
                    def_rtg = row[col.get("DEF_RATING", 0)]
                    opp_pts = row[col.get("OPP_PTS", 0)]
                    result = {"def_rating_recent": def_rtg, "opp_pts_recent": opp_pts, "n_games": n_games, "season_type": season_type, "source": "NBA Stats API"}
                    with open(cache_path, "wb") as f:
                        pickle.dump(result, f)
                    return result
        except:
            continue
    return None


def fetch_espn_fpi_ratings(sport="NBA"):
    cache_path = os.path.join(CACHE_DIR, f"espn_fpi_{sport}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    sport_slug_map = {"NBA": "basketball/nba", "NFL": "football/nfl", "MLB": "baseball/mlb", "NHL": "hockey/nhl"}
    slug = sport_slug_map.get(sport)
    if not slug:
        return {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/{slug}/teams?limit=50"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        teams = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        ratings = {}
        for team_entry in teams:
            team = team_entry.get("team", {})
            abbr = team.get("abbreviation", "")
            if not abbr:
                continue
            records = team.get("record", {}).get("items", [])
            wins = 0
            losses = 0
            for record in records:
                if record.get("type") == "total":
                    for stat in record.get("stats", []):
                        if stat.get("name") == "wins":
                            wins = stat.get("value", 0)
                        elif stat.get("name") == "losses":
                            losses = stat.get("value", 0)
            total_games = wins + losses
            if total_games > 0:
                win_pct = wins / total_games
                power = round(95 + (win_pct * 20), 1)
                ratings[abbr] = power
        if ratings:
            with open(cache_path, "wb") as f:
                pickle.dump(ratings, f)
            return ratings
        return {}
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_espn_fpi_ratings", "error": str(e)[:100]})
        return {}

def power_rating_spread_divergence(home_team, away_team, spread_str):
    try:
        if not spread_str or spread_str in ("N/A", "—"):
            return 0, ""
        spread_val = float(str(spread_str).replace("+", "").strip())
        home_rating = NBA_POWER_RATINGS.get(home_team, 104)
        away_rating = NBA_POWER_RATINGS.get(away_team, 104)
        power_diff = home_rating - away_rating
        implied_spread = -power_diff
        divergence = abs(spread_val - implied_spread)
        if divergence >= 6:
            return min(10, divergence), f"⚡ Market diverges from power ratings by {divergence:.1f} pts"
        return 0, ""
    except:
        return 0, ""

def fetch_todays_referees(sport):
    cache_path = os.path.join(CACHE_DIR, f"officials_{sport}_{date.today()}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 6:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb"}
    path = slug_map.get(sport)
    if not path:
        return {}
    officials = {}
    try:
        today_str = date.today().strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={today_str}"
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for event in resp.json().get("events", []):
            matchup = event.get("shortName", "")
            for comp in event.get("competitions", []):
                refs = [o.get("displayName", "") for o in comp.get("officials", []) if o.get("displayName")]
                if refs and matchup:
                    officials[matchup] = refs
        if officials:
            with open(cache_path, "wb") as f:
                pickle.dump(officials, f)
    except:
        pass
    return officials

def analyze_game_edge(game, sport, home_teams, away_teams, power_ratings=None):
    if power_ratings is None:
        power_ratings = NBA_POWER_RATINGS
    matchup = game.get("Matchup", "")
    spread_str = game.get("Spread", "N/A")
    total_str = game.get("Total", "N/A")
    home_ml = game.get("Home ML", "N/A")
    away_ml = game.get("Away ML", "N/A")
    home_team = home_teams.get(matchup, "")
    away_team = away_teams.get(matchup, "")
    recommendations = []
    best_bet = None
    best_edge = 0
    
    is_playoff_now = (date.today().month in [4, 5, 6])
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
    
    public_data = st.session_state.get("public_betting_data", {})
    game_public = None
    for key, val in public_data.items():
        teams = val.get("teams", [])
        if (home_team in teams or away_team in teams):
            game_public = val
            break
    
    public_sharp_signals = []
    if game_public:
        public_sharp_signals = game_public.get("sharp_signals", [])
    
    try:
        if spread_str and spread_str != "N/A":
            spread_val = float(str(spread_str).split()[-1].replace("+",""))
            favored_team = str(spread_str).split()[0] if len(str(spread_str).split()) > 1 else home_team
            if home_team in power_ratings and away_team in power_ratings:
                home_power = power_ratings[home_team]
                away_power = power_ratings[away_team]
                power_diff = home_power - away_power
                market_spread = -spread_val if favored_team == home_team else spread_val
                spread_edge = power_diff - market_spread
                spread_edge_pct = spread_edge / 10.0
                spread_edge_pct = max(-0.20, min(0.20, spread_edge_pct))
                if abs(spread_edge_pct) >= 0.05:
                    rec_side = home_team if spread_edge > 0 else away_team
                    rec_text = f"{rec_side} {spread_str}" if spread_edge > 0 else f"{away_team} {'+' + str(abs(spread_val)) if spread_val < 0 else '-' + str(abs(spread_val))}"
                    tier = get_tier(abs(spread_edge_pct), sport)
                    recommendations.append({"type": "SPREAD", "pick": rec_text, "edge": spread_edge_pct, "edge_pct": f"{spread_edge_pct:.1%}", "tier": tier, "power_diff": round(power_diff, 1), "market_spread": market_spread, "divergence": round(spread_edge, 1), "note": f"Power rating diff {power_diff:.1f} vs market spread {market_spread:.1f} — divergence {spread_edge:.1f} pts"})
                    if abs(spread_edge_pct) > best_edge:
                        best_edge = abs(spread_edge_pct)
                        best_bet = recommendations[-1]
    except:
        pass
    
    try:
        if total_str and total_str != "N/A":
            total_val = float(total_str)
            fair_total = None
            if sport == "NBA":
                h_pace = NBA_TEAM_PACE.get(home_team, 99.5)
                a_pace = NBA_TEAM_PACE.get(away_team, 99.5)
                h_power = power_ratings.get(home_team, 112.0)
                a_power = power_ratings.get(away_team, 112.0)
                avg_pace = (h_pace + a_pace) / 2
                base_total = 220.0
                pace_adj = (avg_pace - 99.5) * 1.5
                off_adj = ((h_power + a_power) / 2 - 112.0) * 0.8
                fair_total = base_total + pace_adj + off_adj
            elif sport == "MLB":
                base_total = 8.5
                mlb_pitchers = st.session_state.get("mlb_pitchers", {})
                h_data = mlb_pitchers.get(home_team, {})
                a_data = mlb_pitchers.get(away_team, {})
                h_pitcher = h_data.get("pitcher","")
                a_pitcher = a_data.get("pitcher","")
                h_era = MLB_PITCHER_ERA.get(h_pitcher, LEAGUE_AVG_ERA)
                a_era = MLB_PITCHER_ERA.get(a_pitcher, LEAGUE_AVG_ERA)
                avg_era = (h_era + a_era) / 2
                era_adj = (avg_era - LEAGUE_AVG_ERA) * 0.4
                park_mult = MLB_PARK_FACTORS.get(home_team, MLB_PARK_DEFAULT)
                park_adj = (park_mult - 1.0) * 2.0
                fair_total = base_total + era_adj + park_adj
            elif sport == "NHL":
                h_gf = NHL_TEAM_GOALS_FOR.get(home_team, NHL_GOALS_DEFAULT)
                h_ga = NHL_TEAM_GOALS_AGAINST.get(home_team, NHL_GOALS_DEFAULT)
                a_gf = NHL_TEAM_GOALS_FOR.get(away_team, NHL_GOALS_DEFAULT)
                a_ga = NHL_TEAM_GOALS_AGAINST.get(away_team, NHL_GOALS_DEFAULT)
                home_expected = (h_gf + a_ga) / 2
                away_expected = (a_gf + h_ga) / 2
                fair_total = home_expected + away_expected
            elif sport == "NFL":
                h_power = power_ratings.get(home_team, 104.0)
                a_power = power_ratings.get(away_team, 104.0)
                base_total = 44.5
                power_adj = ((h_power + a_power) / 2 - 104.0) * 0.5
                fair_total = base_total + power_adj
            if fair_total is not None:
                total_edge = fair_total - total_val
                total_edge_pct = total_edge / 50.0
                if sport == "MLB":
                    total_edge_pct = total_edge / 10.0
                elif sport == "NHL":
                    total_edge_pct = total_edge / 8.0
                elif sport == "NFL":
                    total_edge_pct = total_edge / 30.0
                total_edge_pct = max(-0.20, min(0.20, total_edge_pct))
                if abs(total_edge_pct) >= 0.04:
                    side = "OVER" if total_edge > 0 else "UNDER"
                    tier = get_tier(abs(total_edge_pct), sport)
                    recommendations.append({"type": "TOTAL", "pick": f"{side} {total_val}", "edge": total_edge_pct, "edge_pct": f"{total_edge_pct:.1%}", "tier": tier, "fair_total": round(fair_total, 1), "market_total": total_val, "divergence": round(total_edge, 1), "note": f"Model projects {fair_total:.1f} vs market {total_val} — {side} value"})
                    if abs(total_edge_pct) > best_edge:
                        best_edge = abs(total_edge_pct)
                        best_bet = recommendations[-1]
    except:
        pass
    
    try:
        if home_ml and away_ml and home_ml != "N/A" and away_ml != "N/A":
            h_ml = float(str(home_ml).replace("+",""))
            a_ml = float(str(away_ml).replace("+",""))
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
                h_fair = 1 / (1 + math.exp(-power_diff/7))
                a_fair = 1 - h_fair
                h_ml_edge = h_fair - h_implied
                a_ml_edge = a_fair - a_implied
                best_ml_edge = max(h_ml_edge, a_ml_edge)
                if best_ml_edge >= 0.04:
                    if h_ml_edge > a_ml_edge:
                        ml_pick = f"{home_team} ML ({home_ml})"
                        ml_edge = h_ml_edge
                        fair_prob = h_fair
                    else:
                        ml_pick = f"{away_team} ML ({away_ml})"
                        ml_edge = a_ml_edge
                        fair_prob = a_fair
                    tier = get_tier(ml_edge, sport)
                    ev = fair_prob * (abs(float(str(home_ml if h_ml_edge > a_ml_edge else away_ml).replace("+",""))) / 100) - (1 - fair_prob)
                    recommendations.append({"type": "MONEYLINE", "pick": ml_pick, "edge": ml_edge, "edge_pct": f"{ml_edge:.1%}", "ev": round(ev, 3), "tier": tier, "fair_prob": round(fair_prob, 3), "note": f"Fair probability {fair_prob:.1%} vs implied — +EV at these odds"})
                    if ml_edge > best_edge:
                        best_edge = ml_edge
                        best_bet = recommendations[-1]
    except:
        pass
    
    return {"matchup": matchup, "home": home_team, "away": away_team, "recommendations": recommendations, "best_bet": best_bet, "best_edge": best_edge, "sport": sport, "public_signals": public_sharp_signals, "public_data": game_public}

def fetch_alternate_lines(sport, matchup):
    if not ODDSWRAP_AVAILABLE:
        return {}
    sport_key = ODDSWRAP_SPORT_MAP.get(sport)
    if not sport_key:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"alt_lines_{sport}_{hashlib.md5(matchup.encode()).hexdigest()[:8]}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 2:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    alternates = {"spreads": [], "totals": [], "source": "OddsWrap"}
    try:
        client = OddsClient(books=["draftkings", "bovada"])
        games = client.get_all(sport_key)
        for game in games:
            game_name = f"{game.away_team} @ {game.home_team}"
            if game.away_team.upper() in matchup.upper() or game.home_team.upper() in matchup.upper():
                for line in game.lines:
                    if hasattr(line, "alt_spreads"):
                        for alt in line.alt_spreads:
                            alternates["spreads"].append({"spread": alt.spread, "odds": alt.odds, "book": line.book})
                    if hasattr(line, "alt_totals"):
                        for alt in line.alt_totals:
                            alternates["totals"].append({"total": alt.total, "side": alt.side, "odds": alt.odds, "book": line.book})
                break
        if alternates["spreads"] or alternates["totals"]:
            with open(cache_path, "wb") as f:
                pickle.dump(alternates, f)
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_alternate_lines", "error": str(e)[:100]})
    return alternates

def analyze_all_games(games, sport, home_teams, away_teams):
    all_game_analysis = []
    power_map = {"NBA": NBA_POWER_RATINGS}
    power_ratings = power_map.get(sport, {})
    for game in games:
        analysis = analyze_game_edge(game, sport, home_teams, away_teams, power_ratings)
        if analysis["best_bet"]:
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
            props = scrape_prizepicks(sport)
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
                tier = get_tier(edge, sport)
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

def fetch_nba_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "nba_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
        "Connection": "keep-alive",
        "Origin": "https://www.nba.com",
    }
    urls = [
        "https://stats.nba.com/stats/playergamelogs?Season=2024-25&SeasonType=Playoffs&PlayerOrTeam=P&LastNGames=10",
        "https://stats.nba.com/stats/playergamelogs?Season=2024-25&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
    ]
    rolling = {}
    for url in urls:
        try:
            resp = requests.get(url, headers=nba_headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            for row in rows:
                player_name = row[col["PLAYER_NAME"]]
                pts = row[col["PTS"]]
                reb = row[col["REB"]]
                ast = row[col["AST"]]
                col_min = col.get("MIN", col.get("E_PACE", None))
                minutes = round(float(row[col_min]), 1) if col_min and row[col_min] else None
                if player_name and pts is not None:
                    pts_val = round(float(pts), 1)
                    reb_val = round(float(reb), 1)
                    ast_val = round(float(ast), 1)
                    rolling[player_name] = {
                        "PTS": pts_val,
                        "REB": reb_val,
                        "AST": ast_val,
                        "PRA": round(pts_val + reb_val + ast_val, 1),
                        "MIN": minutes,
                        "PTS_std": round(pts_val * 0.40, 2) if pts_val > 0 else 4.0,
                        "REB_std": round(reb_val * 0.45, 2) if reb_val > 0 else 1.5,
                        "AST_std": round(ast_val * 0.50, 2) if ast_val > 0 else 1.0,
                        "PRA_std": round((pts_val + reb_val + ast_val) * 0.35, 2),
                    }
            if rolling:
                break
        except Exception:
            continue
    if not rolling:
        st.session_state["nba_api_status"] = "FAILED — likely blocked by hosting"
    else:
        st.session_state["nba_api_status"] = f"OK ({len(rolling)} players)"
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

def fetch_wnba_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "wnba_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    nba_headers = {
        "Host": "stats.wnba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.wnba.com/",
        "Origin": "https://www.wnba.com",
    }
    urls = [
        "https://stats.wnba.com/stats/playergamelogs?Season=2025&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
        "https://stats.wnba.com/stats/playergamelogs?Season=2024&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
    ]
    rolling = {}
    for url in urls:
        try:
            resp = requests.get(url, headers=nba_headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            for row in rows:
                name = row[col["PLAYER_NAME"]]
                pts = row[col["PTS"]]
                reb = row[col["REB"]]
                ast = row[col["AST"]]
                if name and pts is not None:
                    pts_val = round(float(pts), 1)
                    reb_val = round(float(reb), 1)
                    ast_val = round(float(ast), 1)
                    rolling[name] = {
                        "PTS": pts_val,
                        "REB": reb_val,
                        "AST": ast_val,
                        "PRA": round(pts_val + reb_val + ast_val, 1),
                        "PTS_std": round(pts_val * 0.40, 2) if pts_val > 0 else 4.0,
                        "REB_std": round(reb_val * 0.45, 2) if reb_val > 0 else 1.5,
                        "AST_std": round(ast_val * 0.50, 2) if ast_val > 0 else 1.0,
                        "PRA_std": round((pts_val + reb_val + ast_val) * 0.35, 2),
                        "n_games": 10,
                    }
            if rolling:
                break
        except:
            continue
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

def fetch_mlb_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "mlb_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    rolling = {}
    for player_name, player_id in MLB_PLAYER_IDS.items():
        player_avgs = PLAYER_AVERAGES.get("MLB", {}).get(player_name, {})
        is_pitcher = "SO" in player_avgs or "ER" in player_avgs
        group = "pitching" if is_pitcher else "hitting"
        url = (f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group={group}&season=2025&gameType=R")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            stats_list = data.get("stats", [])
            if not stats_list:
                continue
            splits = stats_list[0].get("splits", [])
            last10 = splits[-10:] if len(splits) >= 10 else splits
            if len(last10) < 3:
                continue
            if is_pitcher:
                so_vals = [g["stat"].get("strikeOuts",0) for g in last10]
                er_vals = [g["stat"].get("earnedRuns",0) for g in last10]
                h_vals = [g["stat"].get("hits",0) for g in last10]
                rolling[player_name] = {
                    "SO": ewma_average(so_vals, sport="MLB"),
                    "ER": ewma_average(er_vals, sport="MLB"),
                    "H": ewma_average(h_vals, sport="MLB"),
                    "SO_std": compute_std_dev(so_vals, sport="MLB") or 2.0,
                    "ER_std": compute_std_dev(er_vals, sport="MLB") or 1.0,
                    "H_std": compute_std_dev(h_vals, sport="MLB") or 0.3,
                    "n_games": len(last10)
                }
            else:
                h_vals = [g["stat"].get("hits",0) for g in last10]
                hr_vals = [g["stat"].get("homeRuns",0) for g in last10]
                rbi_vals = [g["stat"].get("rbi",0) for g in last10]
                r_vals = [g["stat"].get("runs",0) for g in last10]
                rolling[player_name] = {
                    "H": ewma_average(h_vals, sport="MLB"),
                    "HR": ewma_average(hr_vals, sport="MLB"),
                    "RBI": ewma_average(rbi_vals, sport="MLB"),
                    "R": ewma_average(r_vals, sport="MLB"),
                    "H_std": compute_std_dev(h_vals, sport="MLB") or 0.4,
                    "HR_std": compute_std_dev(hr_vals, sport="MLB") or 0.12,
                    "RBI_std": compute_std_dev(rbi_vals, sport="MLB") or 0.5,
                    "R_std": compute_std_dev(r_vals, sport="MLB") or 0.4,
                    "n_games": len(last10)
                }
            time.sleep(0.3)
        except Exception as e:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_mlb_rolling_averages", "error": str(e)[:100]})
            continue
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling


def fetch_nhl_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "nhl_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    rolling = {}
    for player_name, player_id in NHL_PLAYER_IDS.items():
        url = f"https://api-web.nhle.com/v1/player/{player_id}/game-log/now"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            games = data.get("gameLog", [])
            last10 = games[:10] if len(games) >= 10 else games
            if len(last10) < 3:
                continue
            pts_vals = [g.get("points",0) for g in last10]
            goal_vals = [g.get("goals",0) for g in last10]
            ast_vals = [g.get("assists",0) for g in last10]
            sog_vals = [g.get("shots",0) for g in last10]
            rolling[player_name] = {
                "PTS": ewma_average(pts_vals, sport="NHL"),
                "GOALS": ewma_average(goal_vals, sport="NHL"),
                "ASSISTS": ewma_average(ast_vals, sport="NHL"),
                "SOG": ewma_average(sog_vals, sport="NHL"),
                "PTS_std": compute_std_dev(pts_vals, sport="NHL") or 0.5,
                "GOALS_std": compute_std_dev(goal_vals, sport="NHL") or 0.3,
                "ASSISTS_std": compute_std_dev(ast_vals, sport="NHL") or 0.35,
                "SOG_std": compute_std_dev(sog_vals, sport="NHL") or 1.2,
                "n_games": len(last10)
            }
            time.sleep(0.3)
        except Exception as e:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_nhl_rolling_averages", "error": str(e)[:100]})
            continue
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

def fetch_nba_team_defense():
    cache_path = os.path.join(CACHE_DIR, "nba_team_defense.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
    }
    seasons = ["Playoffs", "Regular+Season"]
    team_def = {}
    for season_type in seasons:
        url = f"https://stats.nba.com/stats/leaguedashteamstats?Season=2024-25&SeasonType={season_type}&MeasureType=Defense&PerMode=PerGame"
        try:
            resp = requests.get(url, headers=nba_headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            def_rating_col = None
            for possible_name in ["DEF_RATING", "DEF_RTNG", "OPP_PTS", "PTS"]:
                if possible_name in col:
                    def_rating_col = possible_name
                    break
            if def_rating_col is None:
                continue
            for row in rows:
                team = row[col["TEAM_ABBREVIATION"]]
                def_rating = row[col[def_rating_col]]
                if def_rating is not None:
                    try:
                        team_def[team] = round(float(def_rating), 1)
                    except (ValueError, TypeError):
                        continue
            if team_def:
                break
        except Exception:
            continue
    if team_def:
        with open(cache_path, "wb") as f:
            pickle.dump(team_def, f)
    return team_def

def fetch_nfl_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "nfl_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    rolling = {}
    season = 2025
    for player_name, athlete_id in ESPN_ATHLETE_IDS.get("NFL", {}).items():
        sport_path = "football/leagues/nfl"
        url = f"{ESPN_CORE_BASE}/sports/{sport_path}/seasons/{season}/athletes/{athlete_id}/eventlog?limit=10"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            game_stats = []
            for item in data.get("events", {}).get("items", [])[:10]:
                stats_ref = item.get("statistics", {}).get("$ref", "")
                if not stats_ref:
                    continue
                try:
                    stats_resp = requests.get(stats_ref, headers=HEADERS, timeout=10)
                    if stats_resp.status_code != 200:
                        continue
                    stats_data = stats_resp.json()
                    game_stat = {}
                    for split in stats_data.get("splits", {}).get("categories", []):
                        for stat in split.get("stats", []):
                            key = stat.get("abbreviation", "").upper()
                            game_stat[key] = stat.get("value", 0)
                    if game_stat:
                        game_stats.append(game_stat)
                    time.sleep(0.2)
                except:
                    continue
            if not game_stats or len(game_stats) < 3:
                continue
            pass_yds = [g.get("PASSYDS", g.get("YDS", 0)) for g in game_stats]
            rush_yds = [g.get("RUSHYDS", g.get("RYDS", 0)) for g in game_stats]
            rec_yds = [g.get("RECYDS", g.get("RECYD", 0)) for g in game_stats]
            tds = [g.get("TD", 0) for g in game_stats]
            rolling[player_name] = {
                "PASS_YDS": ewma_average(pass_yds, sport="NFL"),
                "RUSH_YDS": ewma_average(rush_yds, sport="NFL"),
                "REC_YDS": ewma_average(rec_yds, sport="NFL"),
                "TD": ewma_average(tds, sport="NFL"),
                "PASS_YDS_std": compute_std_dev(pass_yds, sport="NFL") or 45.0,
                "RUSH_YDS_std": compute_std_dev(rush_yds, sport="NFL") or 15.0,
                "REC_YDS_std": compute_std_dev(rec_yds, sport="NFL") or 20.0,
                "TD_std": compute_std_dev(tds, sport="NFL") or 0.7,
                "n_games": len(game_stats)
            }
            time.sleep(0.3)
        except Exception as e:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_nfl_rolling_averages", "error": str(e)[:100]})
            continue
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

def fetch_soccer_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "soccer_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    rolling = {}
    for player, stats in PLAYER_AVERAGES_SOCCER.items():
        goals = stats.get("GOALS", 0.3)
        assists = stats.get("ASSISTS", 0.2)
        shots = stats.get("SHOTS", 3.0)
        rolling[player] = {
            "GOALS": goals,
            "ASSISTS": assists,
            "SHOTS": shots,
            "GOALS_std": round(goals * 0.80, 3),
            "ASSISTS_std": round(assists * 0.75, 3),
            "SHOTS_std": round(shots * 0.45, 3),
            "n_games": 10,
            "source": "hardcoded_with_std"
        }
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

BDL_PLAYER_IDS = {
    "LeBron James": 237, "Luka Doncic": 140, "Nikola Jokic": 279, "Shai Gilgeous-Alexander": 484,
    "Giannis Antetokounmpo": 15, "Jayson Tatum": 484, "Stephen Curry": 115, "Kevin Durant": 135,
    "Anthony Davis": 14, "Damian Lillard": 153, "Devin Booker": 70, "Donovan Mitchell": 300,
    "Jimmy Butler": 85, "Trae Young": 571, "Domantas Sabonis": 395, "Karl-Anthony Towns": 508,
    "Bam Adebayo": 2, "Rudy Gobert": 185, "Tyrese Haliburton": 613, "Jalen Brunson": 86,
    "Cade Cunningham": 625, "Victor Wembanyama": 794, "Paolo Banchero": 731, "Evan Mobley": 694,
    "Darius Garland": 578, "Tobias Harris": 216, "Ja Morant": 606, "Zion Williamson": 400,
    "Jamal Murray": 333, "Michael Porter Jr.": 585, "Aaron Gordon": 5, "Jalen Williams": 746,
    "Alperen Sengun": 700, "Desmond Bane": 616, "Scottie Barnes": 689, "Franz Wagner": 709,
    "De'Aaron Fox": 170, "Pascal Siakam": 400, "Kawhi Leonard": 232, "Luguentz Dort": 601,
}

def fetch_nba_averages_bdl():
    cache_path = os.path.join(CACHE_DIR, "bdl_nba_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    if not BDL_API_KEY:
        return {}
    allowed, reason = api_budget_check("BDL")
    if not allowed:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_nba_averages_bdl", "error": reason})
        return {}
    ids = list(BDL_PLAYER_IDS.values())
    params = "&".join([f"player_ids[]={pid}" for pid in ids])
    url = f"https://api.balldontlie.io/v1/season_averages?season=2025&{params}"
    headers = {"Authorization": BDL_API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {}
        data = resp.json().get("data", [])
        id_to_name = {v: k for k, v in BDL_PLAYER_IDS.items()}
        avgs = {}
        for p in data:
            pid = p.get("player_id")
            name = id_to_name.get(pid)
            if not name:
                continue
            pts = round(float(p.get("pts", 0)), 1)
            reb = round(float(p.get("reb", 0)), 1)
            ast = round(float(p.get("ast", 0)), 1)
            avgs[name] = {"PTS": pts, "REB": reb, "AST": ast, "PRA": round(pts + reb + ast, 1)}
        if avgs:
            with open(cache_path, "wb") as f:
                pickle.dump(avgs, f)
        api_budget_increment("BDL")
        return avgs
    except:
        return {}

def fetch_underdog_props(sport):
    sport_map = {"NBA": "NBA", "MLB": "MLB", "NHL": "NHL", "NFL": "NFL", "WNBA": "WNBA"}
    sport_id = sport_map.get(sport)
    if not sport_id:
        return []
    # Try new v1 lobbies endpoint first (discovered via DevTools May 2026)
    product_exp_id = "018e1234-5678-9abc-def0-123456789006"
    state_config_id = "725014ef-3570-4e93-871d-d69674ab3521"
    url_v1 = (
        f"https://api.underdogfantasy.com/v1/lobbies/content/lines"
        f"?include_live=true&product=fantasy"
        f"&product_experience_id={product_exp_id}"
        f"&show_mass_option_markets=false"
        f"&sport_id={sport_id}"
        f"&state_config_id={state_config_id}"
    )
    url_v2 = f"https://api.underdogfantasy.com/v2/over_under_lines?sport_id={sport_id}"
    url = url_v1
    try:
        ud_headers = {**HEADERS, "Origin": "https://underdogfantasy.com", "Referer": "https://underdogfantasy.com/pick-em"}
        resp = requests.get(url, headers=ud_headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 400 or resp.status_code == 403:
            # Fall back to v2
            resp = requests.get(url_v2, headers=ud_headers, timeout=REQUEST_TIMEOUT)
            url = url_v2
        if resp.status_code != 200:
            return []
        data = resp.json()
        players = {p["id"]: f"{p.get('first_name','').strip()} {p.get('last_name','').strip()}".strip() for p in data.get("players", [])}
        stats_map = {s["id"]: s.get("display_name", s.get("name", "")) for s in data.get("stat_types", [])}
        appearances = {a["id"]: a.get("player_id") for a in data.get("appearances", [])}
        props = []
        seen = set()
        for line in data.get("over_under_lines", []):
            appearance_id = line.get("appearance_id")
            player_id = appearances.get(appearance_id)
            name = players.get(player_id, "")
            line_val = line.get("stat_value")
            stat_type_id = line.get("stat_type_id")
            stat_name = stats_map.get(stat_type_id, "")
            if not name or not stat_name or line_val is None:
                continue
            key = (sport, name, stat_name, line_val)
            if key in seen:
                continue
            seen.add(key)
            props.append({"Player": name, "Prop": stat_name, "Line": float(line_val), "Side": "OVER", "Sport": sport, "source": "Underdog"})
        return props
    except Exception as e:
        print(f"Underdog props error: {e}")
        return []

def scrape_prizepicks(sport):
    league_ids = {"NBA": 4, "MLB": 5, "NHL": 3, "NFL": 7, "WNBA": 8, "UFC": 6, "Golf": 11, "Tennis": 12, "Soccer": 2}
    league = league_ids.get(sport.upper())
    if not league:
        return []
    state_code = st.secrets.get("PP_STATE_CODE", "CA")
    urls = [
        # Primary: partner API — no bot protection, most reliable
        f"https://partner-api.prizepicks.com/projections?per_page=1000&league_id={league}",
        # Fallback 1: confirmed working URL May 2026
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code={state_code}&game_mode=prizepools",
        # Fallback 2: without game_mode
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code={state_code}",
        # Fallback 3: basic API
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250",
    ]
    pp_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
        "Referer": "https://app.prizepicks.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Origin": "https://app.prizepicks.com",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Cache-Control": "no-cache",
        "x-device-id": "betcouncil-v46",
    }
    all_props = []
    seen = set()
    for url in urls:
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}_pp.pkl")
        data = None
        if os.path.exists(cache_path):
            age = (time.time() - os.path.getmtime(cache_path)) / 60
            if age < 20:
                with open(cache_path, "rb") as f:
                    cached = pickle.load(f)
                if cached and cached.get("data"):
                    data = cached
        if data is None:
            try:
                resp = requests.get(url, headers=pp_headers, timeout=15)
                if resp.status_code == 200:
                    # Check for captcha response (returns HTML not JSON)
                    content_type = resp.headers.get("content-type", "")
                    if "html" in content_type or resp.text.strip().startswith("<"):
                        # Got captcha page — skip to next URL
                        st.session_state.setdefault("errors", []).append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "source": "scrape_prizepicks",
                            "error": f"Captcha detected on {url[:60]} — trying next source"
                        })
                        continue
                    data = resp.json()
                    if data and data.get("data"):
                        with open(cache_path, "wb") as f:
                            pickle.dump(data, f)
                elif resp.status_code == 429:
                    time.sleep(2)
                    continue
                elif resp.status_code == 403:
                    # Bot protection — try next URL
                    continue
            except:
                continue
        if not data or not data.get("data"):
            continue
        for proj in data["data"]:
            if proj["type"] != "projection":
                continue
            attrs = proj["attributes"]
            pid = proj["relationships"]["new_player"]["data"]["id"]
            name = attrs.get("display_name", "") or attrs.get("name", "")
            if not name:
                continue
            line = attrs.get("line_score")
            stat = attrs.get("stat_type")
            if line is None or not stat:
                continue
            try:
                line = float(line)
            except:
                continue
            key = (sport, pid, stat, line)
            if key in seen:
                continue
            seen.add(key)
            odds_type = attrs.get("odds_type", "standard")
            all_props.append({"Player": name, "Prop": stat, "Line": line, "Side": "OVER", "Sport": sport, "source": "PrizePicks", "OddsType": odds_type})
    if all_props:
        return all_props
    st.info("PrizePicks unavailable — trying Underdog Fantasy...")
    return fetch_underdog_props(sport)

def fetch_underdog_injuries(sport):
    sport_map = {"NBA": "NBA", "MLB": "MLB", "NFL": "NFL", "NHL": "NHL"}
    sport_id = sport_map.get(sport)
    if not sport_id:
        return {}
    url = f"https://api.underdogfantasy.com/v2/news_items?sport_id={sport_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        injuries = {}
        for item in resp.json().get("news_items", []):
            content = item.get("content", "").lower()
            player = item.get("player", {})
            name = f"{player.get('first_name','')} {player.get('last_name','')}".strip()
            if not name:
                continue
            import_time = item.get("created_at", "")
            if import_time:
                try:
                    item_dt = datetime.fromisoformat(import_time.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - item_dt).total_seconds() / 3600
                    if age_hours > 48:
                        continue
                except:
                    pass
            if "out" in content and "ruled out" in content:
                injuries[name] = "Out"
            elif "questionable" in content or "day-to-day" in content:
                injuries[name] = "Questionable"
        return injuries
    except Exception as e:
        print(f"Underdog injuries error: {e}")
        return {}

def fetch_injury_news(sport):
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NFL": "football/nfl", "NHL": "hockey/nhl"}
    path = slug_map.get(sport, "")
    if not path:
        injuries = {}
    else:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/news"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                injuries = {}
            else:
                data = resp.json()
                injuries = {}
                for article in data.get("articles", []):
                    headline = article.get("headline", "")
                    if "injury" in headline.lower() or "out" in headline.lower() or "questionable" in headline.lower():
                        players = re.findall(r'([A-Z][a-z]+ [A-Z][a-z]+)', headline)
                        for p in players:
                            if "out" in headline.lower():
                                injuries[p] = "Out"
                            elif "questionable" in headline.lower() or "day-to-day" in headline.lower():
                                injuries[p] = "Questionable"
        except:
            injuries = {}
    underdog_injuries = fetch_underdog_injuries(sport)
    injuries.update(underdog_injuries)
    return injuries

def fetch_public_betting(sport):
    sport_slug = ACTION_NETWORK_SPORT_MAP.get(sport)
    if not sport_slug:
        return {}
    allowed, reason = api_budget_check("ACTION_NETWORK")
    if not allowed:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"public_betting_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 20:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    today = date.today().strftime("%Y%m%d")
    url = f"{ACTION_NETWORK_BASE}/{sport_slug}?bookIds={ACTION_NETWORK_BOOK_IDS}&date={today}&periods=event"
    an_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.actionnetwork.com",
        "Referer": "https://www.actionnetwork.com/",
    }
    try:
        resp = requests.get(url, headers=an_headers, timeout=15)
        api_budget_increment("ACTION_NETWORK")
        if resp.status_code != 200:
            return {}
        data = resp.json()
        games_list = data.get("games", [])
        if not games_list:
            return {}
        public_betting = {}
        for game in games_list:
            teams = game.get("teams", [])
            if len(teams) < 2:
                continue
            team_abbrs = [t.get("abbr", "") for t in teams]
            if len(team_abbrs) < 2:
                continue
            odds_data = game.get("odds", {})
            book_15 = odds_data.get("15", {})
            event_data = book_15.get("event", {})
            if not event_data:
                continue
            ml_data = event_data.get("moneyline", [])
            ml_pcts = {}
            for outcome in ml_data:
                side = outcome.get("side", "")
                bet_info = outcome.get("bet_info", {})
                tickets_pct = bet_info.get("tickets", {}).get("percent", 0)
                money_pct = bet_info.get("money", {}).get("percent", 0)
                ml_pcts[side] = {"tickets": tickets_pct, "money": money_pct, "odds": outcome.get("odds", 0)}
            spread_data = event_data.get("spread", [])
            spread_pcts = {}
            for outcome in spread_data:
                side = outcome.get("side", "")
                bet_info = outcome.get("bet_info", {})
                tickets_pct = bet_info.get("tickets", {}).get("percent", 0)
                money_pct = bet_info.get("money", {}).get("percent", 0)
                spread_val = outcome.get("value", 0)
                spread_pcts[side] = {"tickets": tickets_pct, "money": money_pct, "spread": spread_val, "odds": outcome.get("odds", 0)}
            total_data = event_data.get("total", [])
            total_pcts = {}
            for outcome in total_data:
                side = outcome.get("side", "")
                bet_info = outcome.get("bet_info", {})
                tickets_pct = bet_info.get("tickets", {}).get("percent", 0)
                money_pct = bet_info.get("money", {}).get("percent", 0)
                total_pcts[side] = {"tickets": tickets_pct, "money": money_pct, "total": outcome.get("value", 0), "odds": outcome.get("odds", 0)}
            sharp_signals = []
            home_ml = ml_pcts.get("home", {})
            away_ml = ml_pcts.get("away", {})
            if home_ml and away_ml:
                home_ticket = home_ml.get("tickets", 0)
                home_money = home_ml.get("money", 0)
                away_ticket = away_ml.get("tickets", 0)
                away_money = away_ml.get("money", 0)
                if home_money - home_ticket >= 15:
                    sharp_signals.append(f"🔥 Sharp ML: {team_abbrs[0]} ({home_money}% money vs {home_ticket}% tickets)")
                elif home_ticket - home_money >= 15:
                    sharp_signals.append(f"🔥 Sharp ML fade: {team_abbrs[1]} ({away_money}% money vs {away_ticket}% tickets)")
            home_sprd = spread_pcts.get("home", {})
            away_sprd = spread_pcts.get("away", {})
            if home_sprd and away_sprd:
                h_t = home_sprd.get("tickets", 0)
                h_m = home_sprd.get("money", 0)
                a_t = away_sprd.get("tickets", 0)
                a_m = away_sprd.get("money", 0)
                if h_m - h_t >= 15:
                    sharp_signals.append(f"⚡ Sharp spread: {team_abbrs[0]} ({h_m}% money vs {h_t}% tickets)")
                elif a_m - a_t >= 15:
                    sharp_signals.append(f"⚡ Sharp spread: {team_abbrs[1]} ({a_m}% money vs {a_t}% tickets)")
            over_total = total_pcts.get("over", {})
            under_total = total_pcts.get("under", {})
            if over_total:
                o_t = over_total.get("tickets", 0)
                o_m = over_total.get("money", 0)
                u_t = under_total.get("tickets", 0) if under_total else 0
                u_m = under_total.get("money", 0) if under_total else 0
                if o_t >= 70 and u_m >= 40:
                    sharp_signals.append(f"🔥 Sharp UNDER: {o_t}% public tickets OVER but {u_m}% money UNDER")
                elif o_t >= 80 and o_m >= 75:
                    sharp_signals.append(f"✅ Sharp+Public OVER: {o_t}% tickets {o_m}% money")
            num_bets = game.get("num_bets", 0)
            game_key = f"{team_abbrs[0]}_{team_abbrs[1]}"
            public_betting[game_key] = {
                "teams": team_abbrs,
                "num_bets": num_bets,
                "ml": ml_pcts,
                "spread": spread_pcts,
                "total": total_pcts,
                "sharp_signals": sharp_signals,
                "has_sharp": len(sharp_signals) > 0,
            }
        if public_betting:
            with open(cache_path, "wb") as f:
                pickle.dump(public_betting, f)
            st.session_state["public_betting_data"] = public_betting
        return public_betting
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_public_betting", "error": str(e)[:100]})
        return {}

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
        resp = requests.get(url, headers=an_headers, timeout=15)
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
                        except:
                            pass
                odds = line_entry.get("odds")
                if odds:
                    over_odds = odds
            if line_val is None and implied_value:
                try:
                    line_val = round(float(implied_value), 1)
                except:
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
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_action_network_props", "error": str(e)[:100]})
        return []

def fetch_game_lines(sport):
    if sport not in ["NBA", "MLB", "NFL", "NHL", "WNBA"]:
        return [], False, {}, {}
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NFL": "football/nfl", "NHL": "hockey/nhl", "WNBA": "basketball/wnba"}
    path = slug_map.get(sport, "")
    if not path:
        return [], False, {}, {}
    def _fetch_date(target_date):
        date_str = target_date.strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={date_str}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])
                playoff = any(e.get("season", {}).get("type", 0) == 3 for e in events)
                games = []
                home_teams = {}
                away_teams = {}
                for event in events:
                    matchup = event.get("shortName", "")
                    status = event.get("status", {}).get("type", {}).get("description", "")
                    spread = "N/A"
                    total = "N/A"
                    home_ml = "N/A"
                    away_ml = "N/A"
                    provider = "ESPN"
                    for comp in event.get("competitions", []):
                        odds_data = comp.get("odds", [{}])[0] if comp.get("odds") else {}
                        spread = odds_data.get("details", "N/A")
                        total = odds_data.get("overUnder", "N/A")
                        home_ml = odds_data.get("homeTeamOdds", {}).get("moneyLine", "N/A")
                        away_ml = odds_data.get("awayTeamOdds", {}).get("moneyLine", "N/A")
                        provider = odds_data.get("provider", {}).get("name", "ESPN")
                        for competitor in comp.get("competitors", []):
                            team = competitor.get("team", {}).get("abbreviation", "")
                            home_away = competitor.get("homeAway", "")
                            if home_away == "home":
                                home_teams[matchup] = team
                            else:
                                away_teams[matchup] = team
                    games.append({"Matchup": matchup, "Status": status, "Spread": spread, "Total": total, "Home ML": home_ml, "Away ML": away_ml, "Odds Source": provider, "Date": target_date.strftime("%a %b %d"), "Sport": sport})
                return games, playoff, home_teams, away_teams
        except Exception as e:
            print(f"ESPN fetch error: {e}")
        return [], False, {}, {}
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_games, playoff, home_teams, away_teams = _fetch_date(today)
    all_final = all(g["Status"].lower() in ("final", "game over", "final/ot", "final/so", "postponed") for g in today_games) if today_games else True
    if all_final:
        tomorrow_games, playoff, home_teams, away_teams = _fetch_date(tomorrow)
        if tomorrow_games:
            return tomorrow_games, playoff, home_teams, away_teams
        return today_games, playoff, home_teams, away_teams
    if today_games and ODDS_API_KEY:
        try:
            bovada_games, bov_home, bov_away = fetch_odds_api_game_lines(sport)
            if bovada_games:
                bov_lookup = {g["Matchup"]: g for g in bovada_games}
                for game in today_games:
                    matchup = game.get("Matchup","")
                    for bov_matchup, bov_game in bov_lookup.items():
                        home1 = home_teams.get(matchup, "")
                        home2 = bov_home.get(bov_matchup, "")
                        if home1 and home2 and (home1.upper()[:3] in home2.upper() or home2.upper()[:3] in home1.upper()):
                            game["Bovada ML Home"] = bov_game.get("Home ML", "N/A")
                            game["Bovada ML Away"] = bov_game.get("Away ML", "N/A")
                            game["Bovada Spread"] = bov_game.get("Spread", "N/A")
                            game["Bovada Total"] = bov_game.get("Total", "N/A")
                            if game.get("Total") in ("N/A", None) and bov_game.get("Total") not in ("N/A", None):
                                game["Total"] = bov_game["Total"]
                            break
        except Exception as e:
            pass
    return today_games, playoff, home_teams, away_teams

def fetch_odds_api_props(sport):
    if not ODDS_API_KEY:
        return []
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return []
    allowed, reason = api_budget_check("ODDS_API")
    if not allowed:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_odds_api_props", "error": reason})
        return []
    cache_path = os.path.join(CACHE_DIR, f"odds_api_props_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 Odds API props: cached ({age_mins:.0f}m old)")
                return cached
    events_url = f"{ODDS_API_BASE}/sports/{sport_key}/events?apiKey={ODDS_API_KEY}&dateFormat=iso"
    try:
        events_resp = requests.get(events_url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API")
        if events_resp.status_code != 200:
            return []
        events = events_resp.json()
        if not events:
            return []
        today_str = date.today().strftime("%Y-%m-%d")
        today_events = [e for e in events if e.get("commence_time","").startswith(today_str)]
        if not today_events:
            tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
            today_events = [e for e in events if e.get("commence_time","").startswith(tomorrow_str)]
        if not today_events:
            return []
        markets = ODDS_API_PROP_MARKETS.get(sport, [])
        if not markets:
            return []
        markets_str = ",".join(markets)
        all_props = []
        seen = set()
        for event in today_events[:5]:
            event_id = event.get("id", "")
            if not event_id:
                continue
            props_url = f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds?apiKey={ODDS_API_KEY}&regions=us,us2&markets={markets_str}&oddsFormat=american&bookmakers={ODDS_API_BOOKS_PROPS}"
            try:
                props_resp = requests.get(props_url, headers=HEADERS, timeout=15)
                api_budget_increment("ODDS_API")
                if props_resp.status_code != 200:
                    continue
                event_data = props_resp.json()
                for bookmaker in event_data.get("bookmakers", []):
                    book_key = bookmaker.get("key","")
                    book_title = bookmaker.get("title", book_key)
                    for market in bookmaker.get("markets", []):
                        market_key = market.get("key", "")
                        stat_name = ODDS_API_STAT_MAP.get(market_key, market_key.replace("_", " ").title())
                        for outcome in market.get("outcomes", []):
                            player = outcome.get("description", "")
                            side = outcome.get("name", "").upper()
                            line = outcome.get("point")
                            if not player or line is None:
                                continue
                            if side not in ("OVER", "UNDER"):
                                continue
                            if side != "OVER":
                                continue
                            key = (sport, player, stat_name, float(line))
                            if key in seen:
                                continue
                            seen.add(key)
                            all_props.append({
                                "Player": player,
                                "Prop": stat_name,
                                "Line": float(line),
                                "Side": "OVER",
                                "Sport": sport,
                                "source": f"OddsAPI_{book_title}",
                                "OddsType": "standard",
                                "OverOdds": outcome.get("price", -110),
                                "UnderOdds": None,
                            })
                time.sleep(0.2)
            except Exception as e:
                st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_odds_api_props", "error": str(e)[:100]})
                continue
        if all_props:
            with open(cache_path, "wb") as f:
                pickle.dump(all_props, f)
            st.caption(f"✅ Odds API: {len(all_props)} props from Bovada/MyBookie/DK/FD/Novig")
        return all_props
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_odds_api_props", "error": str(e)[:100]})
        return []

def fetch_odds_api_game_lines(sport):
    if not ODDS_API_KEY:
        return [], {}, {}
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return [], {}, {}
    allowed, reason = api_budget_check("ODDS_API")
    if not allowed:
        return [], {}, {}
    cache_path = os.path.join(CACHE_DIR, f"odds_api_games_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 30:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds?apiKey={ODDS_API_KEY}&regions=us,us2&markets=h2h,spreads,totals&oddsFormat=american&bookmakers={ODDS_API_BOOKS_GAMES}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API")
        if resp.status_code != 200:
            return [], {}, {}
        events = resp.json()
        games = []
        home_teams = {}
        away_teams = {}
        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            matchup = f"{away} @ {home}"
            spread = "N/A"
            total = "N/A"
            home_ml = "N/A"
            away_ml = "N/A"
            odds_source = "N/A"
            priority = ["bovada", "mybookieag", "draftkings", "fanduel", "betmgm", "caesars", "us_ex"]
            for preferred_book in priority:
                for bm in event.get("bookmakers", []):
                    if bm.get("key") != preferred_book:
                        continue
                    odds_source = bm.get("title", preferred_book)
                    for mkt in bm.get("markets", []):
                        key = mkt.get("key","")
                        outcomes = mkt.get("outcomes", [])
                        if key == "h2h":
                            for o in outcomes:
                                if o["name"] == home:
                                    home_ml = o["price"]
                                elif o["name"] == away:
                                    away_ml = o["price"]
                        elif key == "spreads":
                            for o in outcomes:
                                if o["name"] == home:
                                    spread = f"{home} {o['point']:+.1f}"
                        elif key == "totals":
                            for o in outcomes:
                                if o["name"] == "Over":
                                    total = o.get("point", "N/A")
                    break
                if odds_source != "N/A":
                    break
            home_teams[matchup] = home
            away_teams[matchup] = away
            games.append({
                "Matchup": matchup,
                "Status": "Scheduled",
                "Spread": spread,
                "Total": total,
                "Home ML": home_ml,
                "Away ML": away_ml,
                "Odds Source": odds_source,
                "Date": date.today().strftime("%a %b %d"),
                "Sport": sport,
            })
        result = (games, home_teams, away_teams)
        if games:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        return result
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_odds_api_game_lines", "error": str(e)[:100]})
        return [], {}, {}

def detect_arbitrage_opportunities(sport):
    cache_path = os.path.join(CACHE_DIR, f"odds_api_props_{sport}.pkl")
    if not os.path.exists(cache_path):
        return []
    try:
        with open(cache_path, "rb") as f:
            props = pickle.load(f)
    except:
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

def fetch_oddswrap_props(sport):
    if not ODDSWRAP_AVAILABLE:
        return []
    sport_key = ODDSWRAP_SPORT_MAP.get(sport)
    if not sport_key:
        return []
    cache_path = os.path.join(CACHE_DIR, f"oddswrap_props_{sport}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 1:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    all_props = []
    try:
        client = OddsClient(books=["draftkings", "bovada", "betrivers"])
        seen = set()
        for book in ["draftkings", "bovada"]:
            try:
                cats = client.get_prop_categories(sport_key, book=book)
                for cat in cats[:10]:
                    try:
                        props = client.get_props(sport_key, category_id=cat.category_id, subcategory_id=cat.subcategory_id, book=book)
                        for prop in props:
                            if not prop.player or prop.line is None:
                                continue
                            key = (prop.player, prop.market, prop.book)
                            if key in seen:
                                continue
                            seen.add(key)
                            all_props.append({"Player": prop.player, "Prop": prop.market, "Line": float(prop.line), "Side": "OVER", "OverOdds": prop.over_odds, "UnderOdds": prop.under_odds, "Book": prop.book, "Sport": sport, "source": f"oddswrap_{prop.book}"})
                    except:
                        continue
            except:
                continue
        if all_props:
            with open(cache_path, "wb") as f:
                pickle.dump(all_props, f)
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_oddswrap_props", "error": str(e)[:100]})
    return all_props

def fetch_oddswrap_lines(sport):
    if not ODDSWRAP_AVAILABLE:
        return []
    sport_key = ODDSWRAP_SPORT_MAP.get(sport)
    if not sport_key:
        return []
    cache_path = os.path.join(CACHE_DIR, f"oddswrap_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 2:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    lines_data = []
    try:
        client = OddsClient(books=["draftkings", "fanduel", "bovada", "betrivers", "betmgm", "caesars"])
        games = client.get_all(sport_key)
        for game in games:
            game_dict = {"Matchup": f"{game.away_team} @ {game.home_team}", "Sport": sport, "Live": game.live}
            for line in game.lines:
                book = line.book.title()
                if line.total:
                    game_dict[f"{book}_Total"] = line.total
                if line.home_spread:
                    game_dict[f"{book}_Spread"] = line.home_spread
                if line.home_odds:
                    game_dict[f"{book}_HomeML"] = line.home_odds
            best_home = game.best_home_odds()
            best_away = game.best_away_odds()
            if best_home:
                game_dict["BestHomeML"] = best_home.home_odds
                game_dict["BestHomeBook"] = best_home.book
            if best_away:
                game_dict["BestAwayML"] = best_away.away_odds
                game_dict["BestAwayBook"] = best_away.book
            lines_data.append(game_dict)
        if lines_data:
            with open(cache_path, "wb") as f:
                pickle.dump(lines_data, f)
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_oddswrap_lines", "error": str(e)[:100]})
    return lines_data


def fetch_parlayapi_props(sport):
    """
    Fetch ParlayPlay props via parlay-api.com aggregator.
    Costs 3 credits per call. Returns ParlayPlay lines cleanly.
    Also pulls PrizePicks and Underdog for line comparison.
    """
    if not PARLAY_API_KEY:
        return []
    cache_path = os.path.join(CACHE_DIR, f"parlayapi_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached
    sport_map = {
        "NBA": "basketball_nba", "WNBA": "basketball_wnba",
        "MLB": "baseball_mlb", "NHL": "icehockey_nhl", "NFL": "americanfootball_nfl"
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    stat_map = {
        "player_points": "Points", "player_rebounds": "Rebounds",
        "player_assists": "Assists", "player_threes": "3-PT Made",
        "player_steals": "Steals", "player_blocks": "Blocked Shots",
        "player_turnovers": "Turnovers", "player_pra": "Pts+Reb+Ast",
        "player_pts_rebs": "Pts+Reb", "player_pts_asts": "Pts+Ast",
        "player_rebs_asts": "Reb+Ast", "player_double_double": "Double-Double",
        "player_hits": "Hits", "player_home_runs": "Home Runs",
        "player_total_bases": "Total Bases", "player_rbis": "RBIs",
        "player_strikeouts": "Strikeouts", "player_hits_runs_rbis": "Hits+Runs+RBIs",
        "player_goals": "Goals", "player_shots_on_goal": "Shots On Goal",
        "player_pass_yds": "Passing Yards", "player_rush_yds": "Rushing Yards",
        "player_rec_yds": "Receiving Yards", "player_receptions": "Receptions",
    }
    try:
        resp = requests.get(
            f"{PARLAY_API_BASE}/sports/{sport_key}/props",
            headers={"X-API-Key": PARLAY_API_KEY},
            params={"bookmakers": "parlayplay,prizepicks,underdog", "dfsOdds": "midpoint"},
            timeout=15
        )
        if resp.status_code != 200:
            st.session_state.setdefault("errors", []).append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "source": "fetch_parlayapi_props",
                "error": f"Status {resp.status_code}"
            })
            return []
        data = resp.json()
        props = []
        seen = set()
        for row in data:
            bookmaker = row.get("bookmaker", "")
            if bookmaker not in ("parlayplay", "prizepicks", "underdog"):
                continue
            player = row.get("player", "")
            market_key = row.get("market_key", "")
            stat = stat_map.get(market_key, market_key.replace("player_","").replace("_"," ").title())
            line = row.get("line")
            over_price = row.get("over_price")
            if not player or not stat or line is None:
                continue
            key = (bookmaker, player, stat, line)
            if key in seen:
                continue
            seen.add(key)
            # Detect Demon/Goblin from price (DFS midpoint pricing)
            odds_type = "standard"
            if bookmaker == "parlayplay":
                if over_price and over_price > 110:
                    odds_type = "goblin"
                elif over_price and over_price < -110:
                    odds_type = "demon"
            props.append({
                "Player": player,
                "Prop": stat,
                "Line": float(line),
                "Side": "OVER",
                "Sport": sport,
                "source": bookmaker.title(),
                "odds_type": odds_type,
                "over_price": over_price,
                "under_price": row.get("under_price"),
            })
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
        return props
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_parlayapi_props",
            "error": str(e)[:100]
        })
        return []


def fetch_parlayapi_arbitrage(sport):
    """Fetch arbitrage opportunities via parlay-api.com"""
    if not PARLAY_API_KEY:
        return []
    sport_map = {
        "NBA": "basketball_nba", "WNBA": "basketball_wnba",
        "MLB": "baseball_mlb", "NHL": "icehockey_nhl", "NFL": "americanfootball_nfl"
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    try:
        resp = requests.get(
            f"{PARLAY_API_BASE}/sports/{sport_key}/arbitrage",
            headers={"X-API-Key": PARLAY_API_KEY},
            params={"limit": 20},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return resp.json()
    except:
        return []


def fetch_parlayapi_ev(sport):
    """Fetch +EV picks vs Pinnacle baseline via parlay-api.com"""
    if not PARLAY_API_KEY:
        return []
    sport_map = {
        "NBA": "basketball_nba", "WNBA": "basketball_wnba",
        "MLB": "baseball_mlb", "NHL": "icehockey_nhl", "NFL": "americanfootball_nfl"
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    try:
        resp = requests.get(
            f"{PARLAY_API_BASE}/sports/{sport_key}/ev",
            headers={"X-API-Key": PARLAY_API_KEY},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return resp.json()
    except:
        return []

def fetch_parlayplay_props(sport):
    allowed, reason = api_budget_check("PARLAYPLAY")
    if not allowed:
        return []
    cache_path = os.path.join(CACHE_DIR, f"parlayplay_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 ParlayPlay: cached ({age_mins:.0f}m old)")
                return cached
    url = "https://parlayplay.io/api/v1/crossgame/offering/"
    pp_session = st.secrets.get("PARLAYPLAY_SESSION", "")
    pp_cookie_full = st.secrets.get("PARLAYPLAY_COOKIES", "")
    if pp_cookie_full:
        pp_cookie = pp_cookie_full
    elif pp_session:
        pp_cookie = f"sessionid={pp_session}"
    else:
        pp_cookie = ""
    pp_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://parlayplay.io",
        "Referer": "https://parlayplay.io/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "x-csrftoken": "1",
        "x-parlay-request": "1",
        "x-parlayplay-native-platform": "web",
        "x-parlayplay-platform": "web",
        "x-requested-with": "XMLHttpRequest",
        "Cookie": pp_cookie,
    }
    league_slug_map = {"NBA": ["nba"], "MLB": ["mlb"], "NHL": ["nhl"], "NFL": ["nfl"], "WNBA": ["wnba"]}
    valid_slugs = league_slug_map.get(sport, [])
    if not valid_slugs:
        return []
    stat_map = {
        "Points": "Points", "Rebounds": "Rebounds", "Assists": "Assists",
        "Pts + Reb + Ast": "Pts+Reb+Ast", "Pts + Reb": "Pts+Reb+Ast", "Pts + Ast": "Pts+Reb+Ast",
        "Steals": "Steals", "Blocks": "Blocked Shots", "Three Pointers Made": "3-PT Made",
        "Threes": "3-PT Made", "Turnovers": "Turnovers", "Hits": "Hits",
        "Homeruns": "Home Runs", "Home Runs": "Home Runs", "RBIs": "RBIs",
        "Runs": "Runs", "Singles": "Singles", "Doubles": "Doubles", "Total Bases": "Total Bases",
        "Hits + Runs + RBIs": "Hits+Runs+RBIs", "Walks": "Walks", "Strikeouts": "Strikeouts",
        "Pitcher Strikeouts": "Strikeouts", "Goals": "Goals", "Shots on Goal": "Shots On Goal",
        "Shots On Goal": "Shots On Goal", "Passing Yards": "Passing Yards",
        "Rushing Yards": "Rushing Yards", "Receiving Yards": "Receiving Yards",
        "Touchdowns": "Touchdowns", "Receptions": "Receptions",
    }
    try:
        # Use curl_cffi to bypass TLS fingerprinting / bot protection
        try:
            from curl_cffi import requests as cf_requests
            resp = cf_requests.get(url, headers=pp_headers, impersonate="chrome120", timeout=20)
        except Exception:
            resp = requests.get(url, headers=pp_headers, timeout=20)
        api_budget_increment("PARLAYPLAY")
        if resp.status_code == 403:
            st.caption("⚠️ ParlayPlay: 403 — blocked by bot protection")
            return []
        if resp.status_code != 200:
            return []
        data = resp.json()
        players_data = data.get("players", [])
        if not players_data:
            return []
        props = []
        seen = set()
        alt_lines_store = {}
        for player_entry in players_data:
            player_obj = player_entry.get("player", {})
            player_name = player_obj.get("fullName", "")
            if not player_name:
                continue
            match_obj = player_entry.get("match", {})
            league_obj = match_obj.get("league", {})
            league_slug = league_obj.get("slug", "").lower()
            if league_slug not in valid_slugs:
                continue
            team_obj = player_obj.get("team", {})
            team_abbr = team_obj.get("teamAbbreviation", "")
            home_team = match_obj.get("homeTeam", {}).get("teamAbbreviation", "")
            away_team = match_obj.get("awayTeam", {}).get("teamAbbreviation", "")
            for stat in player_entry.get("stats", []):
                challenge_name = stat.get("challengeName", "")
                stat_name = stat_map.get(challenge_name, challenge_name)
                alt_lines_obj = stat.get("altLines", {})
                line_values = alt_lines_obj.get("values", [])
                if not line_values:
                    continue
                main_line = next((lv for lv in line_values if lv.get("isMainLine")), line_values[0] if line_values else None)
                if not main_line:
                    continue
                line_val = main_line.get("selectionPoints")
                if line_val is None:
                    continue
                multiplier = stat.get("defaultMultiplier", 1.77)
                live_val = stat.get("liveStatValue", 0)
                alt_count = stat.get("altLineCount", 0)
                alt_key = f"{player_name}_{stat_name}"
                if len(line_values) > 1:
                    alt_lines_store[alt_key] = [{"line": lv.get("selectionPoints"), "odds": lv.get("decimalPriceOver"), "isMain": lv.get("isMainLine", False), "source": "ParlayPlay"} for lv in line_values if lv.get("selectionPoints") is not None]
                key = (player_name, stat_name, float(line_val))
                if key in seen:
                    continue
                seen.add(key)
                props.append({
                    "Player": player_name,
                    "Prop": stat_name,
                    "Line": float(line_val),
                    "Side": "OVER",
                    "Sport": sport,
                    "source": "ParlayPlay",
                    "OddsType": "standard",
                    "PPMultiplier": multiplier,
                    "LiveStat": live_val,
                    "AltLineCount": alt_count,
                    "TeamAbbr": team_abbr,
                    "HomeTeam": home_team,
                    "AwayTeam": away_team,
                })
        if alt_lines_store:
            existing = st.session_state.get("parlayplay_alt_lines", {})
            existing.update(alt_lines_store)
            st.session_state["parlayplay_alt_lines"] = existing
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
            alt_count = sum(1 for p in props if p.get("AltLineCount", 0) > 1)
            st.caption(f"✅ ParlayPlay: {len(props)} props | {alt_count} with alt lines | All sports")
        return props
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_parlayplay_props", "error": str(e)[:100]})
        return []

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

def get_best_alt_line_recommendation(player_name, stat_name, main_line, main_prob, main_ev, avg, std_dev, sport, bankroll):
    best_alt, all_alts = compute_alt_line_ev(player_name, stat_name, avg, std_dev, sport, bankroll)
    if not best_alt:
        return None
    if best_alt["line"] == main_line:
        return None
    return {
        "player": player_name,
        "stat": stat_name,
        "main_line": main_line,
        "main_ev": main_ev,
        "best_line": best_alt["line"],
        "best_ev": best_alt["ev"],
        "best_odds": best_alt["decimal_odds"],
        "best_payout": best_alt["payout"],
        "fair_prob": best_alt["fair_prob"],
        "wager": best_alt["wager"],
        "ev_improvement": round(best_alt["ev"] - main_ev, 4),
        "all_alts": all_alts,
        "source": "ParlayPlay",
    }

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

def fetch_bdl_props(sport):
    if sport != "NBA":
        return []
    if not BDL_API_KEY:
        return []
    allowed, reason = api_budget_check("BDL")
    if not allowed:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_bdl_props", "error": reason})
        return []
    daily_used = get_api_counter(API_BUDGETS["BDL"]["counter_path"]).get("count", 0)
    cache_path = os.path.join(CACHE_DIR, "bdl_props_nba.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 BDL Props: using cached data ({age_mins:.0f}m old)")
                return cached
    today_str = date.today().strftime("%Y-%m-%d")
    games_url = f"https://api.balldontlie.io/v1/games?dates[]={today_str}&per_page=30"
    bdl_headers = {"Authorization": BDL_API_KEY}
    try:
        games_resp = requests.get(games_url, headers=bdl_headers, timeout=10)
        api_budget_increment("BDL")
        if games_resp.status_code != 200:
            return []
        game_ids = [g["id"] for g in games_resp.json().get("data", [])]
        if not game_ids:
            return []
        all_props = []
        seen = set()
        stat_map = {
            "points": "Points", "rebounds": "Rebounds", "assists": "Assists",
            "pts_reb_ast": "Pts+Reb+Ast", "steals": "Steals", "blocks": "Blocked Shots",
            "three_pointers_made": "3-PT Made", "turnovers": "Turnovers",
        }
        for game_id in game_ids[:5]:
            props_url = f"https://api.balldontlie.io/v1/player_props?game_id={game_id}"
            try:
                props_resp = requests.get(props_url, headers=bdl_headers, timeout=10)
                api_budget_increment("BDL")
                if props_resp.status_code != 200:
                    continue
                for prop in props_resp.json().get("data", []):
                    if prop.get("market", {}).get("type") != "over_under":
                        continue
                    player = prop.get("player", {})
                    player_name = f"{player.get('first_name','')} {player.get('last_name','')}".strip()
                    prop_type = prop.get("prop_type", "")
                    line = prop.get("line_value")
                    if not player_name or not line:
                        continue
                    if not prop_type:
                        continue
                    stat_name = stat_map.get(prop_type, prop_type.replace("_", " ").title())
                    try:
                        line_val = float(line)
                    except:
                        continue
                    key = (player_name, stat_name, line_val)
                    if key in seen:
                        continue
                    seen.add(key)
                    all_props.append({
                        "Player": player_name,
                        "Prop": stat_name,
                        "Line": line_val,
                        "Side": "OVER",
                        "Sport": "NBA",
                        "source": "BDL_DraftKings",
                        "OddsType": "standard"
                    })
                time.sleep(0.3)
            except:
                continue
        if all_props:
            with open(cache_path, "wb") as f:
                pickle.dump(all_props, f)
            monthly_limit = API_BUDGETS["BDL"].get("monthly_limit", 200)
            st.caption(f"✅ BDL Props: {len(all_props)} props fetched — BDL monthly: {daily_used + 1}/{monthly_limit} calls")
        return all_props
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_bdl_props", "error": str(e)[:100]})
        return []

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
        t_resp = requests.get(
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
        url = (f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=draftkings,fanduel,betmgm,pinnacle&tournamentIds={tournament_ids}&apiKey={ODDSPAPI_KEY}&oddsFormat=american")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDSPAPI")
        if resp.status_code == 429:
            st.warning("⚠️ OddsPapi rate limit hit — will retry after cache expires")
            return []
        if resp.status_code == 403:
            st.warning("⚠️ OddsPapi monthly limit reached — free tier exhausted")
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
                        stat_clean = market_key.replace("player_", "").replace("_", " ").title()
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
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_oddspapi_props", "error": str(e)[:100]})
        return []

def compare_multibook_lines(pp_props, oddswrap_props):
    if not oddswrap_props:
        return []
    discrepancies = []
    pp_dict = {}
    for p in pp_props:
        key = normalize_name(p["Player"])
        if key not in pp_dict:
            pp_dict[key] = {}
        pp_dict[key][p["Prop"]] = p["Line"]
    ow_dict = {}
    for p in oddswrap_props:
        key = normalize_name(p["Player"])
        prop = p["Prop"]
        if key not in ow_dict:
            ow_dict[key] = {}
        if prop not in ow_dict[key]:
            ow_dict[key][prop] = []
        ow_dict[key][prop].append({"line": p["Line"], "book": p["Book"]})
    for norm_player, props in pp_dict.items():
        if norm_player not in ow_dict:
            continue
        for prop, pp_line in props.items():
            for ow_prop, ow_lines in ow_dict[norm_player].items():
                if (normalize_name(prop) in normalize_name(ow_prop) or normalize_name(ow_prop) in normalize_name(prop)):
                    for ow_data in ow_lines:
                        diff = pp_line - ow_data["line"]
                        if abs(diff) >= 0.5:
                            discrepancies.append({"Player": norm_player.title(), "Prop": prop, "PrizePicks": pp_line, "Book": ow_data["book"].title(), "BookLine": ow_data["line"], "Diff": round(diff, 1), "Favor": ("OVER on PP" if diff > 0 else f"OVER on {ow_data['book'].title()}")})
    return sorted(discrepancies, key=lambda x: abs(x["Diff"]), reverse=True)

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
    except:
        pass
    return warnings

def fetch_espn_game_ids(sport):
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "hockey/nhl", "NFL": "football/nfl", "WNBA": "basketball/wnba"}
    path = slug_map.get(sport)
    if not path:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"espn_ids_{sport}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 60
        if age < 30:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    game_ids = {}
    try:
        today_str = date.today().strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={today_str}"
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for event in resp.json().get("events", []):
            event_id = event.get("id", "")
            matchup = event.get("shortName", "")
            if event_id and matchup:
                game_ids[matchup] = event_id
        if game_ids:
            with open(cache_path, "wb") as f:
                pickle.dump(game_ids, f)
    except:
        pass
    return game_ids

def fetch_espn_line_movement(sport, event_id):
    if not event_id:
        return []
    cache_path = os.path.join(CACHE_DIR, f"line_move_{event_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 60
        if age < 15:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return []
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/events/{event_id}/competitions/{event_id}/odds/{ESPN_BET_PROVIDER_ID}/history/0/movement?limit=100"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        movements = []
        for item in data.get("items", []):
            movements.append({"spread": item.get("spread"), "over_under": item.get("overUnder"), "home_ml": item.get("homeTeamOdds", {}).get("moneyLine"), "away_ml": item.get("awayTeamOdds", {}).get("moneyLine"), "time": item.get("recordedAt", "")})
        if movements:
            with open(cache_path, "wb") as f:
                pickle.dump(movements, f)
        return movements
    except:
        return []

def detect_sharp_movement(movements):
    if len(movements) < 2:
        return False, "", 0
    first = movements[-1]
    last = movements[0]
    try:
        first_spread = float(first.get("spread") or 0)
        last_spread = float(last.get("spread") or 0)
        spread_move = abs(last_spread - first_spread)
        if spread_move >= 1.5:
            direction = "↑" if last_spread > first_spread else "↓"
            return True, direction, round(spread_move, 1)
        first_ou = float(first.get("over_under") or 0)
        last_ou = float(last.get("over_under") or 0)
        ou_move = abs(last_ou - first_ou)
        if ou_move >= 2.0:
            direction = "↑" if last_ou > first_ou else "↓"
            return True, direction, round(ou_move, 1)
    except:
        pass
    return False, "", 0

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
                        if (abs(espn_move) >= 0.5 and abs(bov_move) >= 0.5 and (espn_move > 0) == (bov_move > 0)):
                            direction = "↑" if espn_move > 0 else "↓"
                            steam_moves.append({
                                "matchup": matchup,
                                "type": "TOTAL",
                                "direction": direction,
                                "espn_move": round(espn_move, 1),
                                "bov_move": round(bov_move, 1),
                                "current": curr_total,
                                "was": base_total,
                                "age_mins": round(baseline_age, 0),
                                "signal": f"🔥 STEAM {direction}: Total moved {direction}{abs(espn_move)} on ESPN + Bovada in {baseline_age:.0f}m",
                            })
                    except:
                        pass
        save_json_data(baseline_path, current_lines)
        return steam_moves
    except Exception as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "detect_steam_moves", "error": str(e)[:100]})
        return []

def fetch_espn_predictor(sport, event_id):
    if not event_id:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"predictor_{event_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 3:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return {}
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/events/{event_id}/competitions/{event_id}/predictor"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        home = data.get("homeTeam", {})
        away = data.get("awayTeam", {})
        predictor = {"home_win_pct": home.get("statistics", [{}])[0].get("value") if home.get("statistics") else None, "away_win_pct": away.get("statistics", [{}])[0].get("value") if away.get("statistics") else None, "home_projected_score": home.get("statistics", [{}, {}])[1].get("value") if home.get("statistics") and len(home.get("statistics", [])) > 1 else None, "away_projected_score": away.get("statistics", [{}, {}])[1].get("value") if away.get("statistics") and len(away.get("statistics", [])) > 1 else None}
        with open(cache_path, "wb") as f:
            pickle.dump(predictor, f)
        return predictor
    except:
        return {}

def fetch_espn_player_gamelogs(sport, player_name, n_games=10):
    athlete_id = ESPN_ATHLETE_IDS.get(sport, {}).get(player_name)
    if not athlete_id:
        return None
    cache_path = os.path.join(CACHE_DIR, f"espn_gamelog_{sport}_{athlete_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return None
    season = 2025
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/seasons/{season}/athletes/{athlete_id}/eventlog?limit={n_games}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        game_stats = []
        for item in data.get("events", {}).get("items", [])[:n_games]:
            stats_ref = item.get("statistics", {}).get("$ref", "")
            if not stats_ref:
                continue
            try:
                stats_resp = requests.get(stats_ref, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if stats_resp.status_code != 200:
                    continue
                stats_data = stats_resp.json()
                game_stat = {}
                for split in stats_data.get("splits", {}).get("categories", []):
                    for stat in split.get("stats", []):
                        game_stat[stat.get("abbreviation", "").upper()] = stat.get("value", 0)
                if game_stat:
                    game_stats.append(game_stat)
                time.sleep(0.2)
            except:
                continue
        if not game_stats:
            return None
        if sport == "NBA":
            avg = {"PTS": round(sum(g.get("PTS", 0) for g in game_stats) / len(game_stats), 1), "REB": round(sum(g.get("REB", 0) for g in game_stats) / len(game_stats), 1), "AST": round(sum(g.get("AST", 0) for g in game_stats) / len(game_stats), 1)}
            avg["PRA"] = round(avg["PTS"] + avg["REB"] + avg["AST"], 1)
        elif sport == "NFL":
            avg = {"PASS_YDS": round(sum(g.get("PASSYDS", g.get("YDS", 0)) for g in game_stats) / len(game_stats), 1), "RUSH_YDS": round(sum(g.get("RUSHYDS", g.get("RYDS", 0)) for g in game_stats) / len(game_stats), 1), "REC_YDS": round(sum(g.get("RECYDS", g.get("RECYD", 0)) for g in game_stats) / len(game_stats), 1), "TD": round(sum(g.get("TD", 0) for g in game_stats) / len(game_stats), 2)}
        else:
            avg = {}
        avg["n_games"] = len(game_stats)
        with open(cache_path, "wb") as f:
            pickle.dump(avg, f)
        return avg
    except:
        return None

def generate_gem_summary():
    board = st.session_state.get("board_data", [])
    games = st.session_state.get("games", [])
    game_analysis = st.session_state.get("game_analysis", [])
    sport = st.session_state.get("last_sport", "NBA")
    today = date.today().strftime("%A, %B %d, %Y")
    scan_time = st.session_state.get("last_scan_time", "—")
    lines = []
    lines.append("=== BETCOUNCIL v4.6 DAILY BRIEF ===")
    lines.append(f"Sport: {sport}")
    lines.append(f"Date: {today}")
    lines.append(f"Scanned: {scan_time}")
    lines.append("")
    history = st.session_state.get("history", [])
    tier_stats = compute_tier_stats(history)
    if tier_stats:
        lines.append("=== SEM CALIBRATION ===")
        for tier, stats in tier_stats.items():
            if stats["n"] >= 5:
                lines.append(f"{tier}: {stats['hit_rate']:.1%} hit rate ({stats['n']} bets) | Predicted: {stats['avg_predicted']:.1%} | Error: {stats['calibration_error']:+.3f}")
        lines.append("")
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
    if board:
        lines.append("=== TOP PROPS ===")
        top = [p for p in board if p["Tier"] in ("SOVEREIGN","ELITE","APPROVED")][:8]
        for p in top:
            injury = f" ⚠️ {p['Injury']}" if p.get("Injury") else ""
            std_note = f" [σ={p['StdDev']:.1f}]" if p.get("StdDev") else ""
            fairness = f" [{p['FairnessGrade']}]" if p.get("FairnessGrade") not in (None, "GOOD", "UNKNOWN") else ""
            consensus = f" Consensus:{p['ConsensusProb']}" if p.get("ConsensusProb","—") != "—" else ""
            lines.append(f"{p['Tier']}: {p['Player']} {p['Side']} {p['Line']} {p['Prop']} | Avg:{p['Avg']:.1f}{std_note} | Edge:{p['EdgePct']} | EV:{p.get('EV_2pick','—')} | Prob:{p['Prob']:.1%}{consensus}{fairness}{injury}")
        lines.append("")
    alt_upgrades = st.session_state.get("alt_line_upgrades", [])
    if alt_upgrades:
        lines.append(f"=== ALT LINE UPGRADES ({len(alt_upgrades)} found) ===")
        for upg in alt_upgrades[:4]:
            lines.append(f"{upg['player']} {upg['stat']}: Main {upg['main_line']} → Alt OVER {upg['best_line']} @ {upg['best_payout']} | EV improvement: +{upg['ev_improvement']:.1%}")
        lines.append("")
    if game_analysis:
        lines.append("=== TOP GAME BETS ===")
        for g in game_analysis[:3]:
            bb = g.get("best_bet", {})
            if bb:
                pub = g.get("public_data", {})
                pub_note = ""
                if pub and pub.get("sharp_signals"):
                    pub_note = f" | Sharp: {pub['sharp_signals'][0][:40]}"
                lines.append(f"{g['matchup']}: {bb['pick']} ({bb['type']}) | Edge: {bb['edge_pct']}{pub_note}")
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


def log_manual_bet(player, prop, line, side, sport, outcome, wager, pick_count, bet_type, source, bet_date, tier=None, edge=None, prob=None, notes=""):
    multiplier = PRIZEPICKS_MULTIPLIERS.get(pick_count, 3.0)
    if outcome == "WIN":
        if bet_type == "prop":
            profit = round(wager * multiplier, 2)
        else:
            profit = round(wager * 0.909, 2)
        net = profit
    else:
        profit = 0
        net = -wager
    if tier is None:
        if edge:
            tier = get_tier(edge, sport)
        else:
            tier = "APPROVED"
    if prob is None:
        prob = 0.60 if outcome == "WIN" else 0.45
    record = {
        "player": player, "prop": prop, "line": line, "side": side, "sport": sport,
        "outcome": outcome, "wager": wager, "profit": profit, "loss": wager if outcome == "LOSS" else 0,
        "net": net, "pick_count": pick_count, "bet_type": bet_type, "source": source,
        "tier": tier, "edge": edge or 0, "prob": prob, "stat_type": prop,
        "timestamp": bet_date, "resolved_date": bet_date, "manual_entry": True, "notes": notes,
        "signals_active": {
            "base_positive": True, "defense_positive": False, "location_home": False,
            "back_to_back": False, "sharp_flag": False, "weather_active": False,
            "blowout_risk": False, "usage_boost": False,
        }
    }
    st.session_state.history.append(record)
    save_json_data(HISTORY_PATH, st.session_state.history)
    save_to_gist("history", st.session_state.history)
    st.session_state.bankroll += net
    save_json_data(BANKROLL_PATH, st.session_state.bankroll)
    save_to_gist("bankroll", st.session_state.bankroll)
    record_signal_performance(record, outcome)
    compute_optimized_weights(sport)
    return record

def parse_bet_screenshot_ocr(image_bytes):
    """Parse PrizePicks/prop screenshots using pytesseract.
    Optimised for dark-themed screenshots (white text on dark background).
    No external API needed — uses locally installed Tesseract.
    """
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageOps
        import io, re

        img = Image.open(io.BytesIO(image_bytes))
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        def preprocess(image, invert=False):
            w, h = image.size
            scale = 3 if max(w, h) < 1200 else 2
            image = image.resize((w * scale, h * scale), Image.LANCZOS)
            image = image.convert("L")
            if invert:
                image = ImageOps.invert(image)
            image = ImageEnhance.Contrast(image).enhance(3.0)
            image = ImageEnhance.Sharpness(image).enhance(2.0)
            image = image.point(lambda x: 0 if x < 128 else 255, "1").convert("L")
            return image

        raw_texts = []
        for inv in [True, False]:
            for psm in [6, 11, 4, 3]:
                try:
                    text = pytesseract.image_to_string(
                        preprocess(img.copy(), invert=inv),
                        config=f"--psm {psm} --oem 3"
                    )
                    if len(text.strip()) > 20:
                        raw_texts.append(text)
                except Exception:
                    continue

        if not raw_texts:
            return []

        raw_text = max(raw_texts, key=len)
        st.session_state["ocr_raw_text"] = raw_text
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        text_lower = raw_text.lower()

        # Detect sport
        sport = "NBA"
        for sp, kws in {
            "NBA": ["nba","okc","spurs","thunder","celtics","lakers","warriors","bucks","heat","nets","knicks","suns","sixers"],
            "MLB": ["mlb","baseball","strikeouts","rbis","innings","pitcher"],
            "NHL": ["nhl","hockey","saves","goalie"],
            "NFL": ["nfl","passing yards","rushing yards","touchdowns"],
            "WNBA": ["wnba"],
        }.items():
            if any(k in text_lower for k in kws):
                sport = sp
                break

        STAT_MAP = {
            "hits+runs+rbis": "Hits+Runs+RBIs",
            "pts+reb+ast":    "Pts+Reb+Ast",
            "fg attempted":   "FG Attempted",
            "fg made":        "FG Made",
            "hitter fs":      "Hitter FS",
            "fantasy score":  "Fantasy Score",
            "shots on goal":  "Shots On Goal",
            "passing yards":  "Passing Yards",
            "rushing yards":  "Rushing Yards",
            "receiving yards":"Receiving Yards",
            "home runs":      "Home Runs",
            "pra":            "Pts+Reb+Ast",
            "fga":            "FG Attempted",
            "fgm":            "FG Made",
            "points":         "Points",
            "rebounds":       "Rebounds",
            "assists":        "Assists",
            "steals":         "Steals",
            "blocks":         "Blocked Shots",
            "turnovers":      "Turnovers",
            "strikeouts":     "Strikeouts",
            "receptions":     "Receptions",
            "touchdowns":     "Touchdowns",
            "goals":          "Goals",
            "saves":          "Saves",
            "hits":           "Hits",
            "runs":           "Runs",
            "3pt":            "3-PT Made",
            "3-pt":           "3-PT Made",
            "threes":         "3-PT Made",
        }

        def get_stat(t):
            tl = t.lower()
            for k in sorted(STAT_MAP, key=len, reverse=True):
                if k in tl:
                    return STAT_MAP[k]
            return None

        def get_line(t):
            # Pass 1 — well-formed decimal (e.g. 21.5, 7.5)
            for n in re.findall(r"\b(\d{1,2}\.\d)\b", t):
                v = float(n)
                if 0.5 <= v <= 99.5:
                    return v
            # Pass 2 — clean integer that is a plausible PrizePicks line (e.g. 14, 8)
            for n in re.findall(r"\b(\d{1,2})\b", t):
                v = float(n)
                if 1.0 <= v <= 60.0:
                    return v
            # Pass 3 — OCR dropped decimal point: "215"→21.5, "75"→7.5, "235"→23.5
            # Only applies when the number ends in 5 (PrizePicks uses half-point lines)
            for n in re.findall(r"\b(\d{2,3})\b", t):
                iv = int(n)
                if str(iv).endswith("5"):
                    v = iv / 10.0
                    if 0.5 <= v <= 60.0:
                        return v
            return None

        def get_side(t):
            tl = t.lower()
            # Tesseract commonly misreads ↓ as: vv, vy, v (standalone)
            # and ↑ as: t, wt, tt, 1 (standalone before a number)
            under_tokens = ["less","under","demon","↓","vv","vy"]
            # Check for isolated "v" before a digit (OCR for ↓)
            if re.search(r'\bv[vy]?\b', tl) or any(w in tl for w in under_tokens):
                return "UNDER"
            return "OVER"

        def get_outcome(t):
            tl = t.lower()
            if any(w in tl for w in ["pending","live","locked","in progress"]): return "PENDING"
            if any(w in tl for w in ["won","win","correct","payout","winner"]):  return "WIN"
            if any(w in tl for w in ["lost","loss","incorrect","miss","loser"]): return "LOSS"
            return None

        entry_outcome = get_outcome(raw_text)

        # Tokenise by BOTH newlines AND 2+ consecutive spaces so we handle
        # PrizePicks screenshots where Tesseract collapses everything onto one long line
        tokens = re.split(r"\n+|\s{2,}", raw_text)
        lines = [t.strip() for t in tokens if t.strip()]

        # Position codes that can trail a player name and must be ignored
        POSITION_CODES = {
            "G","F","C","P","SP","RP","IF","OF",
            "PG","SG","SF","PF","C-F","G-F","F-C","F/C","G/F",
        }
        SKIP_WORDS = {
            "NBA","MLB","NHL","NFL","WNBA","NCAAB","NCAAF",
            "More","Less","Over","Under","Pick","Entry","Flex",
            "Goblin","Demon","Final","Pending","Live","Show",
            "Details","Leaderboard","Vs","At","Play","Win",
        }

        def is_player_name(tok):
            """Return cleaned player name if token looks like one, else None."""
            # Strip trailing position code
            cleaned = re.sub(
                r'\s+[A-Za-z]{1,3}(?:-[A-Za-z]{1,2})?$', '', tok
            ).strip()
            cleaned = re.sub(r"[^A-Za-z .\'-]", "", cleaned).strip()
            words = [w for w in cleaned.split() if w]
            if len(words) < 2 or len(cleaned) < 5:
                return None
            if any(w.upper() in SKIP_WORDS for w in words):
                return None
            # All substantial words must start with uppercase
            if not all(w[0].isupper() for w in words if len(w) > 1):
                return None
            # Must have at least 2 words of 3+ chars (filters out junk like "Vv Vy")
            if sum(1 for w in words if len(w) >= 3) < 2:
                return None
            return cleaned

        # --- Step 1: Find all player name positions in the token list ---
        player_positions = []   # list of (token_index, cleaned_name)
        for i, tok in enumerate(lines):
            name = is_player_name(tok)
            if name:
                player_positions.append((i, name))

        # --- Step 2: For each player extract stat + line from the segment after them ---
        bets = []
        for pi, (name_idx, player) in enumerate(player_positions):
            end_idx = (player_positions[pi + 1][0]
                       if pi + 1 < len(player_positions)
                       else len(lines))
            segment_toks = lines[name_idx + 1 : end_idx]
            segment_text = " ".join(segment_toks)

            stat     = get_stat(segment_text)
            line_val = None
            side     = "OVER"

            for tok in segment_toks:
                if line_val is None:
                    line_val = get_line(tok)
                    if line_val is not None:
                        side = get_side(tok)

            if stat is None or line_val is None:
                continue

            pick_outcome = get_outcome(segment_text) or entry_outcome or "PENDING"

            bets.append({
                "player":     player,
                "prop":       stat,
                "line":       line_val,
                "side":       side,
                "sport":      sport,
                "outcome":    pick_outcome,
                "wager":      0,
                "pick_count": 2,
                "source":     "PrizePicks",
                "bet_type":   "prop",
            })

        # Pull wager and pick count from slip header
        wager_m = re.search(r"\$(\d[\d,]*\.?\d*)", raw_text)
        if wager_m and bets:
            try:
                w = float(wager_m.group(1).replace(",", ""))
                if 1 <= w <= 10000:
                    for b in bets:
                        b["wager"] = w
            except Exception:
                pass

        pc_m = re.search(r"(\d+)[- ]pick|pick[- ](\d+)", raw_text.lower())
        if pc_m and bets:
            try:
                pc = int(pc_m.group(1) or pc_m.group(2))
                if 2 <= pc <= 6:
                    for b in bets:
                        b["pick_count"] = pc
            except Exception:
                pass

        return bets

    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time":   datetime.now().strftime("%H:%M:%S"),
            "source": "parse_bet_screenshot_ocr",
            "error":  str(e)[:150],
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
    import re

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
        sport    = rows[i + 2].upper()

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

        # Determine outcome assuming OVER pick (most common on PrizePicks)
        outcome = "WIN" if result_val > line_val else "LOSS"
        status_upper = status.upper()
        if any(w in status_upper for w in ("LIVE", "PENDING", "PROGRESS", "SCHEDULED")):
            outcome = "PENDING"

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

def compute_multi_signal_edge(line, player_avg, opp_def_rating, is_home, teammate_out_boost, side="OVER", stat_key="PTS", pace_adj=0.0, days_rest=2, odds_type="standard", sport="NBA", std_dev=None):
    if player_avg <= 0:
        return 0.0, 0.5, {}
    signals = {}
    league_avg_def = 112.0
    from_optimizer = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
    sport_optimizer = from_optimizer.get(sport, {})
    if (sport_optimizer.get("weights") and sport_optimizer.get("n_bets", 0) >= WEIGHT_OPTIMIZER_MIN_BETS):
        weights = sport_optimizer["weights"]
    else:
        weights = SPORT_SIGNAL_WEIGHTS.get(sport, SPORT_SIGNAL_WEIGHTS["NBA"])
    if stat_key in ["HR", "GOALS"]:
        prob = poisson_prob_over(line, player_avg)
        if side.upper() == "UNDER":
            prob = 1 - prob
        base_edge = prob - 0.524
        fair_prob = prob
    else:
        fair_prob = compute_fair_prob(line, player_avg, std_dev, side)
        base_edge = compute_market_edge(fair_prob, side)
    signals["base"] = base_edge
    signals["fair_prob_base"] = fair_prob
    signals["model_prob"] = fair_prob
    signals["consensus_prob"] = None
    signals["consensus_books"] = []
    if opp_def_rating > 0:
        def_adj = (opp_def_rating - league_avg_def) / league_avg_def
        signals["defense"] = (-def_adj * weights.get("defense", 0.30) if side.upper() == "OVER" else def_adj * weights.get("defense", 0.30))
    else:
        signals["defense"] = 0
    location_adj = 0.05 if is_home else -0.05
    if side.upper() == "UNDER":
        location_adj = -location_adj
    signals["location"] = location_adj
    rest_adj = -0.08 if days_rest == 0 else 0.0
    signals["rest"] = rest_adj
    signals["pace"] = pace_adj if side.upper() == "OVER" else -pace_adj
    combined = (signals["base"] * weights.get("base", 0.45) + signals["defense"] * weights.get("defense", 0.30) + signals["location"] * weights.get("location", 0.15) + signals["rest"] * weights.get("rest", 0.05) + signals["pace"] * weights.get("pace", 0.05))
    if teammate_out_boost:
        usage_signal = teammate_out_boost
        combined += usage_signal
        signals["usage"] = usage_signal
    else:
        signals["usage"] = 0.0
    if odds_type == "demon":
        combined *= 0.85
    elif odds_type == "goblin":
        combined *= 1.10
    combined = max(-EDGE_CAP, min(EDGE_CAP, combined))
    base_prob = signals.get("fair_prob_base", 0.524)
    signal_adjustment = combined - signals.get("base", 0)
    prob = base_prob + signal_adjustment
    prob = max(0.30, min(0.70, prob))
    return combined, prob, signals

def make_display_df(props):
    """Convert raw enriched prop dicts into a clean display DataFrame with friendly column names."""
    rows = []
    for p in props:
        rows.append({
            "Player":         p.get("Player", ""),
            "Stat":           p.get("Prop", ""),
            "Line":           p.get("Line", ""),
            "Play":           f"{p.get('Side','OVER')} {p.get('Line','')}",
            "Avg (10g)":      round(p.get("Avg", 0), 1) if p.get("Avg") else "—",
            "Fair %":         p.get("ModelProb", "—"),
            "Edge":           p.get("EdgePct", "—"),
            "2-Pick EV":      p.get("EV_2pick", "—"),
            "Bet Size":       f"${p.get('Wager_2pick', p.get('Wager', 0)):.2f}",
            "Tier":           p.get("Tier", "—"),
            "AN Grade":       p.get("AN_Grade", "—"),
            "AN Proj":        p.get("AN_Projection", "—"),
            "AN Tier":        p.get("AN_Tier", "—"),
            "AN Confirms":    "✅" if p.get("AN_Confirms") else "—",
            "Line Fair?":     p.get("FairnessGrade", "—"),
            "Sharp $":        p.get("SharpFlag", "—"),
            "Market":         p.get("Efficiency", "—"),
            "Confidence":     p.get("ConfidenceMult", "—"),
            "Injury":         p.get("Injury", ""),
            "Line Move":      p.get("Movement", "—"),
            "Trend":          p.get("Trend", "—"),
            "Source":         p.get("source", "—"),
            "Consensus Prob": p.get("ConsensusProb", "—"),
            "Books":          p.get("ConsensusBooks", "—"),
            "Best Alt Line":  p.get("BestAltLine", "—"),
            "Alt EV":         p.get("BestAltEV", "—"),
            "Alt Payout":     p.get("BestAltPayout", "—"),
            "SEM":            p.get("SEM", "—"),
            "CLV Adj":        p.get("CLVAdj", "—"),
            "Side":           p.get("Side", "OVER"),
            "Prop":           p.get("Prop", ""),
        })
    return pd.DataFrame(rows)

def load_sport_data(sport):
    min_edge = st.session_state.min_edge
    skip_def = st.session_state.skip_defaults
    if sport in ["Golf", "Tennis", "UFC", "Soccer"]:
        props = scrape_prizepicks(sport)
        if not props:
            return [], [], 0, 0, {}, {}
        enriched = []
        for p in props:
            enriched.append({
                "Player": p["Player"], "Prop": p["Prop"], "Line": p["Line"], "Side": "OVER",
                "Edge": 0, "EdgePct": "N/A", "Prob": 0.5, "Wager": 0, "Tier": "N/A", "Model": "N/A",
                "Sport": sport, "Avg": 0, "Injury": "", "SEM": "—", "SEM_n": 0,
                "SignalBase": 0, "SignalDefense": 0, "SignalLocation": 0, "SignalUsage": 0,
                "SignalRest": 0, "SignalPace": 0, "SignalBlowout": 0, "WeatherNote": "",
                "Movement": "", "Efficiency": "—", "EffScore": 0, "SharpFlag": "",
                "source": p.get("source",""), "OddsType": "standard", "DisplayOnly": True,
            })
        sport_warnings = {
            "UFC": "⚠️ UFC: Lines displayed only. Hardcoded averages from May 2025 — statistical analysis unavailable. Do not bet based on these lines.",
            "Soccer": "⚠️ Soccer: Lines displayed only. Hardcoded averages — no live data source connected. Statistical analysis unavailable.",
            "Golf": "⚠️ Golf: Lines displayed only. No statistical baseline available.",
            "Tennis": "⚠️ Tennis: Lines displayed only. No statistical baseline available.",
        }
        st.warning(sport_warnings.get(sport, f"⚠️ {sport}: Lines displayed only."))
        return enriched, [], 0, 0, {}, {}
    rolling_avgs = {}
    team_defense = {}
    if sport == "NBA":
        rolling_avgs = fetch_nba_rolling_averages()
        team_defense = fetch_nba_team_defense()
        live_avgs = fetch_nba_averages_bdl()
        season_avgs = {**PLAYER_AVERAGES.get("NBA", {}), **live_avgs}
    elif sport == "WNBA":
        wnba_rolling = fetch_wnba_rolling_averages()
        season_avgs = PLAYER_AVERAGES.get("WNBA", {})
        for player, stats in wnba_rolling.items():
            if player in season_avgs:
                merged = {}
                for stat, val in stats.items():
                    if stat == "n_games":
                        continue
                    season_val = season_avgs[player].get(stat, val)
                    merged[stat] = round(val * 0.7 + season_val * 0.3, 1)
                season_avgs[player] = {**season_avgs[player], **merged}
            else:
                season_avgs[player] = stats
    elif sport == "MLB":
        mlb_rolling = fetch_mlb_rolling_averages()
        season_avgs = dict(PLAYER_AVERAGES.get("MLB", {}))
        for player, stats in mlb_rolling.items():
            if player in season_avgs:
                merged = {}
                for stat, val in stats.items():
                    if stat == "n_games":
                        continue
                    season_val = season_avgs[player].get(stat, val)
                    merged[stat] = round(val * 0.7 + season_val * 0.3, 2)
                season_avgs[player] = {**season_avgs[player], **merged}
        mlb_pitchers = fetch_mlb_probable_pitchers()
        st.session_state["mlb_pitchers"] = mlb_pitchers
    elif sport == "NHL":
        nhl_rolling = fetch_nhl_rolling_averages()
        season_avgs = dict(PLAYER_AVERAGES.get("NHL", {}))
        for player, stats in nhl_rolling.items():
            if player in season_avgs:
                merged = {}
                for stat, val in stats.items():
                    if stat == "n_games":
                        continue
                    season_val = season_avgs[player].get(stat, val)
                    merged[stat] = round(val * 0.7 + season_val * 0.3, 2)
                season_avgs[player] = {**season_avgs[player], **merged}
    elif sport == "NFL":
        nfl_rolling = fetch_nfl_rolling_averages()
        if not nfl_rolling:
            nfl_rolling = {}
            for player_name in ESPN_ATHLETE_IDS.get("NFL", {}):
                avg = fetch_espn_player_gamelogs("NFL", player_name)
                if avg:
                    nfl_rolling[player_name] = avg
        season_avgs = dict(PLAYER_AVERAGES.get("NFL", {}))
        for player, stats in nfl_rolling.items():
            if player in season_avgs:
                merged = {}
                for stat, val in stats.items():
                    if stat == "n_games":
                        continue
                    season_val = season_avgs[player].get(stat, val)
                    merged[stat] = round(val * 0.7 + season_val * 0.3, 2)
                season_avgs[player] = {**season_avgs[player], **merged}
    elif sport == "Soccer":
        soccer_rolling = fetch_soccer_rolling_averages()
        season_avgs = dict(PLAYER_AVERAGES.get("Soccer", {}))
        for player, stats in soccer_rolling.items():
            season_avgs[player] = {**season_avgs.get(player, {}), **stats}
    else:
        season_avgs = PLAYER_AVERAGES.get(sport, {})
    defaults = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])
    pp_props = scrape_prizepicks(sport)
    ud_props_compare = fetch_underdog_props(sport)
    dk_salaries = fetch_dk_salaries(sport)
    st.session_state["dk_salaries"] = dk_salaries

    # Fetch Pinnacle fair value lines — 1 call per board load, cached 60 min
    pinnacle_data = fetch_pinnacle_lines(sport)
    st.session_state[f"pinnacle_{sport}"] = pinnacle_data

    # Build cross-platform line lookup for better line detection
    better_lines = {}
    all_alt_sources = []
    if ud_props_compare:
        all_alt_sources.extend([(p, "Underdog") for p in ud_props_compare])
    parlayapi_props = st.session_state.get("parlayapi_props_cache", [])
    if parlayapi_props:
        pp_lines = [p for p in parlayapi_props if p.get("source","").lower() == "parlayplay"]
        all_alt_sources.extend([(p, "ParlayPlay") for p in pp_lines])
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
    oddswrap_props = fetch_oddswrap_props(sport)
    st.session_state["oddswrap_props"] = oddswrap_props
    st.session_state["ud_props_compare"] = ud_props_compare
    multibook_discrepancies = compare_multibook_lines(pp_props if pp_props else [], oddswrap_props)
    st.session_state["line_discrepancies"] = []
    st.session_state["multibook_discrepancies"] = multibook_discrepancies
    
    if pp_props:
        props = pp_props
        st.caption(f"✅ PrizePicks: {len(pp_props)} props loaded")
    elif ud_props_compare:
        props = ud_props_compare
        st.caption(f"✅ Underdog Fantasy: {len(ud_props_compare)} props loaded (PrizePicks unavailable)")
    else:
        # Try parlay-api.com — clean aggregator with ParlayPlay + Underdog
        st.caption("⚠️ PrizePicks + Underdog unavailable — trying ParlayAPI aggregator...")
        parlayapi_props = fetch_parlayapi_props(sport)
        if parlayapi_props:
            parlayplay_props = [p for p in parlayapi_props if p.get("source","").lower() == "parlayplay"]
            pa_underdog = [p for p in parlayapi_props if p.get("source","").lower() == "underdog"]
            pa_pp = [p for p in parlayapi_props if p.get("source","").lower() == "prizepicks"]
            if pa_underdog:
                st.session_state["ud_props_compare"] = pa_underdog
            # Use whichever source has the most props
            if parlayplay_props:
                props = parlayplay_props
                st.caption(f"✅ ParlayPlay via ParlayAPI: {len(props)} props")
            elif pa_underdog:
                props = pa_underdog
                st.caption(f"✅ Underdog via ParlayAPI: {len(props)} props")
            elif pa_pp:
                props = pa_pp
                st.caption(f"✅ PrizePicks via ParlayAPI: {len(props)} props")
            else:
                props = parlayapi_props
                st.caption(f"✅ ParlayAPI: {len(props)} props")
        else:
            parlayplay_props = fetch_parlayplay_props(sport)
        if parlayplay_props:
            props = parlayplay_props
            st.success(f"✅ ParlayPlay — {len(parlayplay_props)} props")
        elif oddswrap_props:
            props = [p for p in oddswrap_props if p["Side"] == "OVER"]
            st.info("Using DraftKings/Bovada props as primary source")
        else:
            st.info("Primary sources unavailable — trying Bovada/MyBookie props...")
            odds_api_props = fetch_odds_api_props(sport)
            if odds_api_props:
                props = odds_api_props
                st.success(f"✅ Bovada/MyBookie props — {len(odds_api_props)} loaded")
            elif sport == "NBA" and BDL_API_KEY:
                st.info("Trying BDL Props backup...")
                bdl_props = fetch_bdl_props(sport)
                if bdl_props:
                    props = bdl_props
                    st.success(f"✅ BDL Props — {len(bdl_props)} loaded")
                else:
                    oddspapi_props = fetch_oddspapi_props(sport)
                    if oddspapi_props:
                        props = oddspapi_props
                        st.success(f"✅ OddsPapi — {len(oddspapi_props)} props")
                    else:
                        games, _, _, _ = fetch_game_lines(sport)
                        return [], games, 0, 0, {}, {}
            else:
                oddspapi_props = fetch_oddspapi_props(sport)
                if oddspapi_props:
                    props = oddspapi_props
                    st.success(f"✅ OddsPapi — {len(oddspapi_props)} props")
                else:
                    games, _, _, _ = fetch_game_lines(sport)
                    return [], games, 0, 0, {}, {}
    
    injuries = fetch_injury_news(sport) if sport in ["NBA", "MLB", "NFL", "NHL"] else {}
    public_betting = {}
    if sport in ["NBA", "MLB", "NHL", "NFL"]:
        public_betting = fetch_public_betting(sport)
        st.session_state["public_betting_data"] = public_betting
    an_props = []
    if sport in ["NBA", "MLB", "NHL", "NFL", "WNBA"]:
        an_props = fetch_action_network_props(sport)
        st.session_state["an_props_data"] = an_props
    an_lookup = {}
    for ap in an_props:
        key = (ap["player_abbr"].lower(), ap["stat"])
        an_lookup[key] = ap
    games, is_playoff, home_teams, away_teams = fetch_game_lines(sport)
    b2b_teams = set()
    try:
        yesterday = date.today() - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y%m%d")
        slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "hockey/nhl", "WNBA": "basketball/wnba"}
        path = slug_map.get(sport, "")
        if path:
            y_url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={yesterday_str}"
            y_resp = requests.get(y_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if y_resp.status_code == 200:
                for event in y_resp.json().get("events", []):
                    for comp in event.get("competitions", []):
                        for competitor in comp.get("competitors", []):
                            team = competitor.get("team", {}).get("abbreviation", "")
                            if team:
                                b2b_teams.add(team)
    except:
        pass
    game_ids = fetch_espn_game_ids(sport)
    if sport in ["NBA", "MLB"]:
        officials_data = fetch_todays_referees(sport)
        st.session_state["officials_data"] = officials_data
    else:
        st.session_state["officials_data"] = {}
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
    history = load_json_data(HISTORY_PATH, [])
    tier_stats = compute_tier_stats(history)
    enriched = []
    skipped_def = skipped_edge = 0
    for p in props:
        stat_raw = p["Prop"]
        stat_norm = STAT_NORMALIZE.get((sport, stat_raw), stat_raw)
        player = p["Player"]
        line = p["Line"]
        side = p["Side"]
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
                if skip_def:
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
                            recent_def = fetch_team_recent_defense(sport, p2, 10)
                            if recent_def and recent_def.get("def_rating_recent"):
                                recent_rating = recent_def["def_rating_recent"]
                                is_playoff_month = date.today().month in [4,5,6]
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
            if out_player and any(out_player.lower() in inj.lower() for inj in injuries.keys()):
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
        days_rest = 0 if player_team in b2b_teams else 2
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
        if sport == "NBA" and player_team:
            for game in games:
                if player_team in game.get("Matchup", ""):
                    parts = game["Matchup"].replace("@", "vs").split()
                    for p2 in parts:
                        if p2 != player_team and len(p2) <= 3 and p2.isalpha():
                            player_pace = NBA_TEAM_PACE.get(player_team, 99.5)
                            opp_pace = NBA_TEAM_PACE.get(p2, 99.5)
                            combined_pace = (player_pace + opp_pace) / 2
                            pace_adj = (combined_pace - 99.5) / 99.5
                            break
                    break
        game_total_adj = 0.0
        if sport == "NBA" and player_team:
            for game in games:
                if player_team in game.get("Matchup", ""):
                    total = game.get("Total", "N/A")
                    if total and total != "N/A":
                        try:
                            game_total_adj = (float(total) - 225.0) / 225.0 * 0.05
                        except:
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
                    weather_adj, weather_note = weather_edge_adjustment(weather, stat_norm, "OVER")
        pitcher_adj = 0.0
        pitcher_name = ""
        if sport == "MLB":
            mlb_pitchers = st.session_state.get("mlb_pitchers", {})
            team_full = MLB_PLAYER_TEAM_MAP.get(player,"")
            if team_full and mlb_pitchers:
                opp_data = mlb_pitchers.get(team_full, {})
                opp_pitcher = opp_data.get("pitcher","")
                if opp_pitcher:
                    pitcher_era = MLB_PITCHER_ERA.get(opp_pitcher, LEAGUE_AVG_ERA)
                    era_diff = pitcher_era - LEAGUE_AVG_ERA
                    pitcher_adj = era_diff / 100.0
                    pitcher_adj = max(-0.08, min(0.08, pitcher_adj))
                    pitcher_name = opp_pitcher
        ud_line_val = None
        for ud_p in (ud_props_compare or []):
            if (normalize_name(ud_p.get("Player","")) == normalize_name(player) and ud_p.get("Prop","") == stat_raw):
                ud_line_val = ud_p.get("Line")
                break
        std_dev_key = f"{stat_norm}_std"
        std_dev = avg_dict.get(std_dev_key, None)
        consensus_prob, consensus_books = compute_consensus_probability(sport, player, stat_raw, line, side)
        fairness_grade, fairness_note = check_prop_line_fairness(line, consensus_prob, side)
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
        over_edge, over_prob, over_signals = compute_multi_signal_edge(line, avg, opp_def_rating, is_home, usage_boost, "OVER", stat_norm, pace_adj, days_rest, odds_type, sport, std_dev)
        over_edge = max(-EDGE_CAP, min(EDGE_CAP, over_edge + blowout_adj + weather_adj + game_total_adj + referee_adj + pitcher_adj))
        under_edge, under_prob, under_signals = compute_multi_signal_edge(line, avg, opp_def_rating, is_home, usage_boost, "UNDER", stat_norm, pace_adj, days_rest, odds_type, sport, std_dev)
        under_edge = max(-EDGE_CAP, min(EDGE_CAP, under_edge - blowout_adj - weather_adj - game_total_adj - referee_adj - pitcher_adj))
        if consensus_prob is not None:
            blended_over_prob = round(consensus_prob * 0.60 + over_prob * 0.40, 4)
            blended_under_prob = round((1 - consensus_prob) * 0.60 + under_prob * 0.40, 4)
            over_prob = max(0.30, min(0.70, blended_over_prob))
            under_prob = max(0.30, min(0.70, blended_under_prob))
            over_edge = over_prob - 0.524
            under_edge = under_prob - 0.524
        if fairness_grade == "BAD":
            over_edge = over_edge * 0.75
            under_edge = under_edge * 0.75
        elif fairness_grade == "CAUTION":
            over_edge = over_edge * 0.90
            under_edge = under_edge * 0.90
        if under_edge > over_edge and (under_edge - over_edge) > 0.05:
            best_edge = under_edge
            best_side = "UNDER"
            best_prob = under_prob
            best_signals = under_signals
        else:
            best_edge = over_edge
            best_side = "OVER"
            best_prob = over_prob
            best_signals = over_signals
        adj_edge, calibrated = adjusted_edge(best_edge, sport, get_tier(best_edge, sport), stat_norm, history)
        final_edge = adj_edge if calibrated else best_edge
        eff_score, eff_label = market_efficiency_score(line, ud_line_val, final_edge, sport)
        if (an_grade in ("A+", "A", "A-") and get_tier(final_edge, sport) in ("SOVEREIGN", "ELITE", "APPROVED")):
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
        clv_mult, clv_note = get_clv_edge_adjustment(sport, get_tier(final_edge, sport))
        if clv_mult != 1.0:
            final_edge = max(-EDGE_CAP, min(EDGE_CAP, final_edge * clv_mult))
        if final_edge < min_edge:
            skipped_edge += 1
            continue
        tier = get_tier(final_edge, sport)
        injury_flag = injuries.get(player, "")
        sem_display, sem_n = compute_sem_for_tier(tier_stats, tier)
        ev_2pick = calculate_prizepicks_ev(best_prob, 2)
        ev_3pick = calculate_prizepicks_ev(best_prob, 3)
        wager_2pick = kelly_unit_prizepicks(best_prob, st.session_state.bankroll, 2)
        wager_3pick = kelly_unit_prizepicks(best_prob, st.session_state.bankroll, 3)
        season_stat = PLAYER_AVERAGES.get(sport, {}).get(player, {}).get(stat_norm, avg)
        recency_flag, trend = get_recency_context(player, stat_norm, season_stat, avg, sport)
        signals_active = {"base_positive": best_signals.get("base", 0) > 0, "defense_positive": best_signals.get("defense", 0) > 0, "location_home": is_home, "back_to_back": days_rest == 0, "sharp_flag": bool(sharp_flag), "weather_active": weather_adj != 0, "blowout_risk": blowout_adj < 0, "usage_boost": usage_boost > 0}
        enriched.append({
            "Player": player, "Prop": stat_raw, "Line": line, "Side": best_side, "Avg": avg,
            "Edge": final_edge, "EdgePct": f"{final_edge:.1%}", "Prob": best_prob,
            "Wager": kelly_unit(best_prob, st.session_state.bankroll), "Tier": tier,
            "Quality": "Lookup" if not using_default else "Default", "Model": "MultiSignal",
            "Sport": sport, "Injury": injury_flag, "SEM": sem_display, "SEM_n": sem_n,
            "SignalBase": best_signals.get("base", 0), "SignalDefense": best_signals.get("defense", 0),
            "SignalLocation": best_signals.get("location", 0), "SignalUsage": best_signals.get("usage", 0),
            "SignalRest": best_signals.get("rest", 0), "SignalPace": best_signals.get("pace", 0),
            "SignalBlowout": blowout_adj, "WeatherNote": weather_note, "Movement": "",
            "Efficiency": eff_label, "EffScore": eff_score, "SharpFlag": sharp_flag,
            "source": p.get("source", ""), "EV_2pick": f"{ev_2pick:+.1%}", "EV_3pick": f"{ev_3pick:+.1%}",
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
            "AN_Confirms": (an_tier in ("SOVEREIGN", "ELITE") and get_tier(final_edge, sport) in ("SOVEREIGN", "ELITE", "APPROVED")),
        })
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

    arb_opps = detect_arbitrage_opportunities(sport)
    st.session_state["arb_opportunities"] = arb_opps
    alt_line_upgrades = []
    for prop in enriched:
        if prop.get("Tier") not in ("SOVEREIGN","ELITE","APPROVED"):
            continue
        upgrade = get_best_alt_line_recommendation(
            prop["Player"], prop["Prop"], prop["Line"], prop["Prob"],
            float(str(prop.get("EV_2pick","0%")).replace("%","").replace("+","")) / 100,
            prop["Avg"], prop.get("StdDev"), sport, st.session_state.bankroll,
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
    enriched.sort(key=lambda x: x["Edge"], reverse=True)
    for prop in enriched:
        prop["LockScore"] = calculate_lock_quality_score(prop)
    quality_sorted = sorted(enriched, key=lambda x: x.get("LockScore", 0), reverse=True)
    st.session_state["quality_sorted_board"] = quality_sorted
    line_movement = track_line_movement(enriched)
    st.session_state["line_movement"] = line_movement
    for prop in enriched:
        key = f"{prop['Player']}_{prop['Prop']}"
        move = line_movement.get(key, {})
        prop["Movement"] = (move.get("direction", "") + str(abs(move.get("diff", 0))) if move else "")
    return enriched, games, skipped_def, skipped_edge, home_teams, away_teams

# =========================
# SESSION STATE & PERSISTENCE
# =========================
_ss = {"bankroll": DEFAULT_BANKROLL, "day_start_br": DEFAULT_BANKROLL, "session_start": time.time(),
       "locks": [], "history": [], "min_edge": MIN_EDGE_DEFAULT, "skip_defaults": True, "last_sport": "NBA",
       "board_data": [], "games": [], "last_scan_time": None, "board_ready": False, "n_skipped_def": 0, "n_skipped_edge": 0,
       "errors": [], "game_line_movement": {}, "game_sharp_flags": {}, "oddswrap_props": [],
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
    st.session_state.history = (gist_history if gist_history is not None else load_json_data(HISTORY_PATH, []))
    st.session_state.locks = (gist_locks if gist_locks is not None else load_json_data(LOCKS_PATH, []))
    st.session_state.bankroll = (gist_bankroll if gist_bankroll is not None else load_json_data(BANKROLL_PATH, DEFAULT_BANKROLL))
    st.session_state.day_start_br = st.session_state.bankroll
    st.session_state.persistence_loaded = True

# =========================
# SIDEBAR (Full as in original)
# =========================
with st.sidebar:
    st.markdown('<div style="text-align:center;margin-bottom:16px;"><div style="width:44px;height:44px;background:linear-gradient(135deg,#0ea5a0,#065f5e);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:inline-flex;align-items:center;justify-content:center;font-size:22px;">⚡</div><div style="font-size:22px;font-weight:700;color:#ffffff;margin-top:6px;">BetCouncil</div><div style="font-size:11px;color:#4a8a8a;">v4.6 · Complete</div></div>', unsafe_allow_html=True)
    st.session_state.bankroll = st.number_input("Bankroll ($)", value=float(st.session_state.bankroll), step=10.0)
    dc = get_daily_change()
    dc_color = "#0ea5a0" if dc.startswith("+") else "#e04040"
    st.markdown(f'<div style="font-size:13px;color:{dc_color};margin-top:-12px;margin-bottom:8px;">{dc} today</div>', unsafe_allow_html=True)
    st.metric("Active Unit", f"${active_unit():.2f}")
    st.markdown(f'<div style="font-size:12px;color:#5a6a7a;margin-bottom:16px;">Session: {get_session_time()}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Chairman Strategy")
    st.session_state.min_edge = st.slider("Min Edge (%)", 0, 15, int(st.session_state.min_edge * 100), step=1) / 100.0
    st.session_state.skip_defaults = st.checkbox("Skip unknown players", value=st.session_state.skip_defaults)
    st.markdown("---")
    sport_sel = st.selectbox("Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport) if st.session_state.last_sport in SPORTS else 0)
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
                        except:
                            os.remove(fp)
        except:
            pass
        with st.spinner(f"Fetching {sport_sel} from PrizePicks/Underdog..."):
            board, games, n_def, n_edge, home_teams, away_teams = load_sport_data(sport_sel)
            st.session_state.board_data = board
            st.session_state.games = games
            st.session_state.last_sport = sport_sel
            st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
            st.session_state.board_ready = True
            st.session_state.n_skipped_def = n_def
            st.session_state.n_skipped_edge = n_edge
            if games and home_teams and away_teams:
                game_analysis = analyze_all_games(games, sport_sel, home_teams, away_teams)
                st.session_state["game_analysis"] = game_analysis
            else:
                st.session_state["game_analysis"] = []
        if board:
            st.success(f"{len(board)} props loaded")
            if n_def:
                st.info(f"{n_def} unknown players skipped")
        else:
            st.warning("No props yet. Check back closer to game time.")
    st.markdown("---")
    _wins = sum(1 for h in st.session_state.history if h.get("outcome") == "WIN")
    _losses = sum(1 for h in st.session_state.history if h.get("outcome") == "LOSS")
    if _wins + _losses > 0:
        _total = _wins + _losses
        _hit_rate = _wins / _total
        _net = sum(h.get("net", 0) for h in st.session_state.history)
        _color = "green" if _net >= 0 else "red"
        _hit_color = "#22c55e" if _hit_rate >= 0.577 else "#e04040"
        st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-radius:8px;padding:10px 12px;margin:8px 0;">
  <div style="font-size:11px;color:#6a7a8a;margin-bottom:4px;">YOUR RECORD</div>
  <div style="font-size:20px;font-weight:700;color:#e8f0f8;">{_wins}W — {_losses}L</div>
  <div style="font-size:13px;color:{_hit_color};font-weight:600;">{_hit_rate:.1%} hit rate {'✅' if _hit_rate >= 0.577 else '⚠️'}</div>
  <div style="font-size:13px;color:{_color};font-weight:700;">Net: ${_net:.2f}</div>
  <div style="font-size:10px;color:#6a7a8a;margin-top:4px;">Need 57.7%+ for +EV on 2-picks</div>
</div>""", unsafe_allow_html=True)
    if st.button("Reset Bankroll", width="stretch"):
        st.session_state.bankroll = DEFAULT_BANKROLL
        st.session_state.day_start_br = DEFAULT_BANKROLL
        save_json_data(BANKROLL_PATH, st.session_state.bankroll)
        save_to_gist("bankroll", st.session_state.bankroll)
        st.rerun()

# =========================
# COMMAND BAR
# =========================
pending = len([l for l in st.session_state.locks if l.get("status") == "PENDING"])
dc = get_daily_change()
dc_color = "#0ea5a0" if dc.startswith("+") else "#e04040"
scan_t = st.session_state.last_scan_time or "—"
staleness_label_bar, _ = get_edge_staleness(st.session_state.last_scan_time)
st.markdown(f"""
<div class="command-bar">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;">
    <div style="font-size:13px;color:#0ea5a0;font-weight:600;">⚡ BetCouncil v4.6 — Complete</div>
    <div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
      <span style="font-size:12px;color:#6a7a8a;">Session: {get_session_time()}</span>
      <span style="font-size:12px;border:1px solid #0ea5a0;color:#0ea5a0;background:rgba(14,165,160,0.1);padding:4px 10px;border-radius:20px;">{pending} Lock{"s" if pending!=1 else ""}</span>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;">
    <div class="metric-box"><div class="metric-label">Bankroll</div><div class="metric-value gold-text">${st.session_state.bankroll:.2f}</div><div style="font-size:12px;color:{dc_color};">{dc} today</div></div>
    <div class="metric-box"><div class="metric-label">Unit</div><div class="metric-value teal-text">${active_unit():.2f}</div></div>
    <div class="metric-box"><div class="metric-label">Min Edge</div><div class="metric-value gold-text">{st.session_state.min_edge*100:.0f}%</div></div>
    <div class="metric-box"><div class="metric-label">Kelly</div><div class="metric-value gold-text">{KELLY_FRACTION}</div></div>
    <div class="metric-box"><div class="metric-label">Props Loaded</div><div class="metric-value teal-text">{len(st.session_state.board_data)}</div></div>
    <div class="metric-box"><div class="metric-label">Edge Freshness</div><div class="metric-value" style="font-size:11px;">{staleness_label_bar}</div></div>
  </div>
</div>""", unsafe_allow_html=True)

# =========================
# TABS (Full as in original - Summary tab simplified for length)
# =========================


# =========================
# DRAFTKINGS DFS SALARY SIGNAL
# =========================

def fetch_dk_nba_draftgroup_id():
    """Find today's NBA classic draftGroupId from DraftKings."""
    cache_path = os.path.join(CACHE_DIR, "dk_draftgroup_nba.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 120:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    try:
        r = requests.get(
            "https://www.draftkings.com/lobby/getcontests?sport=NBA",
            headers={**HEADERS, "Referer": "https://www.draftkings.com/"},
            timeout=10
        )
        if r.status_code != 200:
            return None
        contests = r.json().get("Contests", [])
        # Find Classic contest (contestTypeId=21 or name contains Classic)
        for c in contests:
            name = c.get("n", "").lower()
            if "classic" in name and c.get("dg"):
                dgid = c["dg"]
                with open(cache_path, "wb") as f:
                    pickle.dump(dgid, f)
                return dgid
        # Fallback: first contest with a draftGroupId
        for c in contests:
            if c.get("dg"):
                dgid = c["dg"]
                with open(cache_path, "wb") as f:
                    pickle.dump(dgid, f)
                return dgid
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_dk_nba_draftgroup_id",
            "error": str(e)[:100]
        })
    return None


def fetch_dk_salaries(sport="NBA"):
    """
    Fetch DraftKings DFS salary data for today's slate.
    Returns dict: {player_name: {salary, avg_points, value_score}}
    High salary = DK model projects big game
    Value score = projected points per $1000 salary
    """
    cache_path = os.path.join(CACHE_DIR, f"dk_salaries_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                return pickle.load(f)

    sport_map = {
        "NBA": "NBA", "MLB": "MLB", "NHL": "NHL",
        "NFL": "NFL", "WNBA": "WNBA"
    }
    dk_sport = sport_map.get(sport)
    if not dk_sport:
        return {}

    try:
        # Step 1: get draftGroupId
        contests_r = requests.get(
            f"https://www.draftkings.com/lobby/getcontests?sport={dk_sport}",
            headers={**HEADERS, "Referer": "https://www.draftkings.com/"},
            timeout=10
        )
        if contests_r.status_code != 200:
            return {}

        contests = contests_r.json().get("Contests", [])
        draft_group_id = None
        for c in contests:
            name = c.get("n", "").lower()
            if ("classic" in name or "showdown" not in name) and c.get("dg"):
                draft_group_id = c["dg"]
                break

        if not draft_group_id:
            return {}

        # Step 2: get draftable players with salaries
        players_r = requests.get(
            f"https://api.draftkings.com/draftgroups/v1/{draft_group_id}/draftables",
            headers={**HEADERS, "Referer": "https://www.draftkings.com/"},
            timeout=10
        )
        if players_r.status_code != 200:
            return {}

        data = players_r.json()
        draftables = data.get("draftables", [])

        salaries = {}
        for player in draftables:
            name = player.get("displayName", "")
            salary = player.get("salary", 0)
            avg_pts = player.get("draftStatAttributes", [{}])
            # Extract average FPPG
            fppg = 0.0
            for attr in player.get("draftStatAttributes", []):
                if attr.get("id") == 90:  # FPPG stat id
                    try:
                        fppg = float(attr.get("value", 0))
                    except:
                        pass

            if name and salary:
                value_score = round((fppg / (salary / 1000)), 2) if salary > 0 else 0
                salaries[normalize_name(name)] = {
                    "name": name,
                    "salary": salary,
                    "fppg": fppg,
                    "value": value_score,
                    "salary_tier": (
                        "ELITE" if salary >= 9000 else
                        "HIGH" if salary >= 7500 else
                        "MID" if salary >= 6000 else
                        "VALUE"
                    )
                }

        if salaries:
            with open(cache_path, "wb") as f:
                pickle.dump(salaries, f)
            st.session_state["dk_salaries"] = salaries
            st.caption(f"✅ DraftKings: {len(salaries)} player salaries loaded")

        return salaries

    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_dk_salaries",
            "error": str(e)[:100]
        })
        return {}


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

def fetch_pinnacle_lines(sport):
    """
    Fetch Pinnacle lines via OddsPAPI (already in our stack).
    Cache in session state — only 1 API call per board load per sport.
    Respects free tier: 100 calls/day, 1000/month.
    """
    cache_key = f"pinnacle_{sport}"
    if st.session_state.get(cache_key):
        return st.session_state[cache_key]

    # Check disk cache first — 60 min TTL for Pinnacle lines
    cache_path = os.path.join(CACHE_DIR, f"pinnacle_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.session_state[cache_key] = cached
                return cached

    if not ODDSPAPI_KEY:
        return {}

    allowed, reason = api_budget_check("ODDSPAPI")
    if not allowed:
        return {}

    sport_id_map = {"NBA": 4, "WNBA": 4, "MLB": 3, "NHL": 6, "NFL": 1}
    sport_id = sport_id_map.get(sport)
    if not sport_id:
        return {}

    pinnacle_data = {"props": {}, "games": {}}

    try:
        # Get tournaments
        t_resp = requests.get(
            f"https://api.oddspapi.io/v4/tournaments?sportId={sport_id}&apiKey={ODDSPAPI_KEY}",
            timeout=10
        )
        if t_resp.status_code != 200:
            return {}

        tournaments = t_resp.json()
        top_ids = [str(t["tournamentId"]) for t in tournaments
                   if t.get("upcomingFixtures", 0) > 0][:3]
        if not top_ids:
            top_ids = [str(t["tournamentId"]) for t in tournaments[:2]]
        if not top_ids:
            return {}

        tournament_ids = ",".join(top_ids)

        # Fetch Pinnacle ONLY — saves API credits vs fetching all books
        resp = requests.get(
            f"https://api.oddspapi.io/v4/odds-by-tournaments"
            f"?bookmaker=pinnacle&tournamentIds={tournament_ids}"
            f"&apiKey={ODDSPAPI_KEY}&oddsFormat=american",
            headers=HEADERS,
            timeout=15
        )
        api_budget_increment("ODDSPAPI")

        if resp.status_code != 200:
            return {}

        data = resp.json()

        for event in data.get("events", []):
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            for bookmaker in event.get("bookmakers", []):
                if bookmaker.get("key", "").lower() != "pinnacle":
                    continue
                for market in bookmaker.get("markets", []):
                    mkey = market.get("key", "")
                    outcomes = market.get("outcomes", [])

                    # Player props
                    if "player" in mkey.lower():
                        over_out = next((o for o in outcomes if o.get("name","").upper() == "OVER"), None)
                        under_out = next((o for o in outcomes if o.get("name","").upper() == "UNDER"), None)
                        if over_out and under_out:
                            over_imp = devig_odds(over_out.get("price"))
                            under_imp = devig_odds(under_out.get("price"))
                            if over_imp and under_imp:
                                total = over_imp + under_imp
                                over_nv = round(over_imp / total, 4)
                                under_nv = round(under_imp / total, 4)
                                player = over_out.get("description", "")
                                line = over_out.get("point")
                                stat = mkey.replace("player_","").replace("_"," ").title()
                                if player and line is not None:
                                    pkey = (normalize_name(player), stat.lower(), float(line))
                                    pinnacle_data["props"][pkey] = {
                                        "over_prob": over_nv,
                                        "under_prob": under_nv,
                                        "over_odds": over_out.get("price"),
                                        "under_odds": under_out.get("price"),
                                        "player": player, "stat": stat, "line": float(line)
                                    }

                    # Game lines
                    elif mkey in ("h2h", "spreads", "totals"):
                        if len(outcomes) >= 2:
                            imp_a = devig_odds(outcomes[0].get("price"))
                            imp_b = devig_odds(outcomes[1].get("price"))
                            if imp_a and imp_b:
                                total = imp_a + imp_b
                                prob_a = round(imp_a / total, 4)
                                game_key = (normalize_name(home), normalize_name(away), mkey)
                                pinnacle_data["games"][game_key] = {
                                    "prob_home": prob_a,
                                    "prob_away": round(imp_b / total, 4),
                                    "line_home": outcomes[0].get("point"),
                                    "line_away": outcomes[1].get("point"),
                                    "odds_home": outcomes[0].get("price"),
                                    "odds_away": outcomes[1].get("price"),
                                }

        # Cache to disk and session
        with open(cache_path, "wb") as f:
            pickle.dump(pinnacle_data, f)
        st.session_state[cache_key] = pinnacle_data
        n_props = len(pinnacle_data["props"])
        n_games = len(pinnacle_data["games"])
        if n_props or n_games:
            st.caption(f"✅ Pinnacle: {n_props} player props + {n_games} game lines loaded as fair value baseline")
        return pinnacle_data

    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_pinnacle_lines",
            "error": str(e)[:100]
        })
        return {}


def pinnacle_fair_value(player, stat, line, side="OVER", sport="NBA"):
    """
    Get Pinnacle no-vig true probability for a prop.
    Returns (prob, confirms_model, note) or (None, False, "")
    """
    cache_key = f"pinnacle_{sport}"
    pinn_data = st.session_state.get(cache_key, {})
    if not pinn_data:
        return None, False, ""

    props = pinn_data.get("props", {})
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


def get_pinnacle_edge(model_prob, pinnacle_prob, side="OVER"):
    """
    Calculate edge vs Pinnacle as the benchmark.
    This is the OddsJam/Outlier methodology.
    positive = we have edge over Pinnacle's true line
    """
    if pinnacle_prob is None or model_prob is None:
        return None
    # Edge = our model prob - Pinnacle true prob
    # If positive, we think this is MORE likely than Pinnacle does
    return round(model_prob - pinnacle_prob, 4)

tabs = st.tabs(["📋 Summary", "📊 Full Board", "🏟️ Game Lines", "🔒 Locks & Ledger", "📈 History", "🔍 Slip Analyzer", "📝 Log Bet", "🛒 Line Shop", "⚙️ System"])

# ----- TAB 0: SUMMARY (Full version from original) -----
with tabs[0]:
    st.markdown("# 🧠 THE BOARD — BETCOUNCIL v4.6")
    today_str = date.today().strftime("%A, %B %d, %Y")
    st.markdown(f"**{st.session_state.last_sport} Slate — {today_str}** | **Scanned:** {scan_t} | **Edge Model:** Multi‑Signal (5 signals + bonuses)")
    
    staleness_label, staleness_color = get_edge_staleness(st.session_state.last_scan_time)
    col_fresh1, col_fresh2, col_fresh3 = st.columns(3)
    with col_fresh1:
        st.markdown(f"**Edge Data:** {staleness_label}")
    with col_fresh2:
        if staleness_color in ("orange", "red"):
            if st.button("🔄 Refresh Board"):
                with st.spinner("Refreshing..."):
                    board, games, n_def, n_edge, home_teams, away_teams = load_sport_data(st.session_state.last_sport)
                    st.session_state.board_data = board
                    st.session_state.games = games
                    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
                    if games and home_teams and away_teams:
                        game_analysis = analyze_all_games(games, st.session_state.last_sport, home_teams, away_teams)
                        st.session_state["game_analysis"] = game_analysis
                    else:
                        st.session_state["game_analysis"] = []
                st.rerun()
    with col_fresh3:
        if staleness_color == "red":
            st.warning("⚠️ Edges over 60 minutes old. Lines may have moved.")
    
    fw = check_data_freshness()
    if fw:
        with st.expander(f"⚠️ {len(fw)} Data Freshness Warning(s)"):
            for w in fw:
                st.warning(w)
    
    st.markdown("🔒 **Sources:** PrizePicks (Partner API) · Underdog · ESPN Odds · OddsWrap")
    
    st.markdown("""
<div style="display:flex;gap:16px;flex-wrap:wrap;margin:8px 0 16px 0;">
  <span style="color:#e8a020;font-weight:600;font-size:13px;">🥇 SOVEREIGN 15%+</span>
  <span style="color:#0ea5a0;font-weight:600;font-size:13px;">🥈 ELITE 10%+</span>
  <span style="color:#4a90d9;font-weight:600;font-size:13px;">🥉 APPROVED 5%+</span>
  <span style="color:#7a8a9a;font-weight:600;font-size:13px;">📋 LEAN 2%+</span>
  <span style="color:#6a7a8a;font-size:13px;">· 2-pick needs 57.7% to be +EV</span>
  <span style="color:#6a7a8a;font-size:13px;">· 3-pick needs 58.5%</span>
</div>
""", unsafe_allow_html=True)
    
    can_bet, risk_reason = check_daily_risk_limits()
    if not can_bet:
        st.error(f"🛑 **Risk Control Active:** {risk_reason}")
    else:
        today = date.today().strftime("%Y-%m-%d")
        today_count = len([l for l in st.session_state.locks if l.get("timestamp","").startswith(today)]) + len([h for h in st.session_state.history if h.get("timestamp","").startswith(today)])
        remaining = DAILY_RISK_CONTROLS["max_locks_per_day"] - today_count
        st.caption(f"✅ Risk controls OK — {remaining} locks remaining today | Stop-loss: -{DAILY_RISK_CONTROLS['max_daily_loss_pct']:.0%} | Stop-win: +{DAILY_RISK_CONTROLS['stop_win_pct']:.0%}")
    
    if st.session_state.get("board_ready"):
        games = st.session_state.games
        is_playoff = any(g.get("Status","").lower() in ("scheduled","in progress") for g in games) and date.today().month in [4, 5, 6]
        if is_playoff and st.session_state.last_sport == "NBA":
            st.warning(PLAYOFF_DEFENSE_WARNING)
    
    st.markdown("---")
    
    st.markdown("## 🏟️ TODAY'S GAMES")
    st.caption("📊 **Column Guide:** • **Spread** = Run line (MLB) / Point spread • **Total** = Over/Under (combined runs) • **Home ML/Away ML** = Moneyline odds (N/A = not provided by ESPN API)")
    
    if st.session_state.games:
        df_games = pd.DataFrame(st.session_state.games)
        display_cols = ["Matchup", "Status", "Spread", "Total", "Home ML", "Away ML", "Date"]
        display_cols = [c for c in display_cols if c in df_games.columns]
        
        display_df = df_games[display_cols].copy()
        
        if "Total" in display_df.columns:
            display_df["Total"] = display_df["Total"].apply(lambda x: f"{float(x):.1f}" if x not in ("N/A", "—", None) and str(x).replace('.','',1).isdigit() else "—")
        
        if "Spread" in display_df.columns:
            display_df["Spread"] = display_df["Spread"].apply(lambda x: str(x).replace("N/A", "—") if x not in ("N/A", None) else "—")
        
        styled_df = display_df.style.set_properties(**{
            'color': '#e8f0f8',
            'background-color': '#0d1520',
            'border-color': '#1a2a3a',
            'text-align': 'left'
        }).set_table_styles([
            {'selector': 'th', 'props': [('text-align', 'left'), ('color', '#0ea5a0'), ('font-weight', '600')]},
            {'selector': 'td', 'props': [('text-align', 'left')]},
        ])
        
        st.dataframe(styled_df, width="stretch", use_container_width=True, hide_index=True)
        st.caption("💡 **What does Total mean?** The projected combined runs scored by both teams. Bet OVER if you think more runs will be scored, UNDER if fewer.")
        
    else:
        st.info("No games loaded.")
    

    if st.session_state.last_sport == "MLB":
        st.markdown("### 🌤️ MLB Weather Conditions")
        weather_data = []
        shown_cities = set()
        for prop in st.session_state.board_data[:20]:
            player = prop.get("Player", "")
            team = MLB_PLAYER_TEAM_MAP.get(player, "")
            if team:
                park = MLB_BALLPARKS.get(team, {})
                city = park.get("city", "")
                is_outdoor = park.get("outdoor", True)
                if city and is_outdoor and city not in shown_cities:
                    weather = fetch_weather_for_game(city, is_outdoor)
                    if weather:
                        shown_cities.add(city)
                        weather_data.append({"City": city, "Temp": f"{weather['temp_f']}\u00b0F", "Wind": f"{weather['wind_speed_mph']}mph {weather['wind_dir']}", "Humidity": f"{weather['humidity']}%", "Updated": weather["fetched_at"]})
        if weather_data:
            st.dataframe(pd.DataFrame(weather_data), width="stretch")
        else:
            st.caption("Load MLB board to see weather conditions.")

    st.markdown("---")
    st.markdown("## \U0001f916 AI ASSISTANT SYNC")
    st.caption("Generate a formatted daily summary to paste into your AI betting assistant (Gemini Gem). It gives the AI full context on today\'s board, picks, and game data so you can ask it questions.")
    col_gem1, col_gem2 = st.columns([2, 1])
    with col_gem1:
        if st.button("\U0001f4cb Generate Daily Summary", key="gen_gem_brief"):
            if not st.session_state.get("board_data"):
                st.warning("Load the board first.")
            else:
                brief = generate_gem_summary()
                st.session_state["gem_brief"] = brief
                st.success("\u2705 Summary generated \u2014 copy it and paste into your Gemini Gem")
    with col_gem2:
        if st.session_state.get("gem_brief"):
            _scan_t = st.session_state.last_scan_time or "\u2014"
            st.caption(f"Generated at {_scan_t}")
    if st.session_state.get("gem_brief"):
        st.caption("\U0001f4cc How to use: Copy everything below \u2192 open your Gemini Gem \u2192 paste it in. Your Gem will now know everything about today\'s board and you can ask it questions.")
        st.text_area("Copy this and paste into your Gemini Gem:", value=st.session_state["gem_brief"], height=300, key="gem_brief_display")

    st.markdown("---")
    st.markdown("### \u26a1 Sharp Money Alerts")
    sharp_flags = st.session_state.get("game_sharp_flags", {})
    if sharp_flags:
        for matchup, info in sharp_flags.items():
            st.warning(f"**{matchup}**: Line moved {info['direction']}{info['magnitude']} \u2014 possible sharp action")
    public_data = st.session_state.get("public_betting_data", {})
    if public_data:
        for game_key, gd in public_data.items():
            signals = gd.get("sharp_signals", [])
            teams = gd.get("teams", [])
            num_bets = gd.get("num_bets", 0)
            if signals:
                matchup_label = " vs ".join(teams)
                for sig in signals:
                    st.warning(f"**{matchup_label}** ({num_bets:,} bets): {sig}")
    if not sharp_flags and not public_data:
        st.caption("Load board to see sharp money and public betting data.")

    st.markdown("---")
    st.markdown("## \U0001f4ca PLAYER PROPS \u2014 TOP PICKS")
    board = st.session_state.board_data
    if board:
        for p in board[:8]:
            tier_color = TIER_COLORS.get(p["Tier"], "#7a8a9a")
            ev_2 = p.get("EV_2pick", "\u2014")
            ev_color = "#22c55e" if str(ev_2).startswith("+") else "#e04040"
            avg_val = p.get("Avg", 0)
            injury_html = f'<span style="background:#e04040;color:white;font-size:10px;padding:2px 6px;border-radius:10px;margin-left:6px;">{p["Injury"]}</span>' if p.get("Injury") else ""
            sharp_html = f'<span style="color:#e8a020;font-size:11px;margin-left:8px;">{p["SharpFlag"]}</span>' if p.get("SharpFlag") else ""
            better_line_html = f'<span style="background:#22c55e;color:#000;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;">⚡ Better on {p["BetterLineSource"]}: {p["Side"]} {p["BetterLineVal"]}</span>' if p.get("BetterLineSource") else ""
            pinnacle_html = f'<span style="background:#9b59b6;color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;">📌 Pinnacle {p["PinnacleProb"]}</span>' if p.get("PinnacleConfirms") else ""
            pinnacle_fade_html = f'<span style="background:#e04040;color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;">⚠️ Pinnacle Fades</span>' if p.get("PinnacleProb","—") != "—" and not p.get("PinnacleConfirms") and float(p.get("PinnacleProb","50%").replace("%",""))/100 < 0.46 else ""
            ev_2_display = p.get("EV_2pick", "\u2014")
            wager_display = p.get("Wager_2pick", p.get("Wager", 0))
            st.markdown(
                f'<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {tier_color};border-radius:8px;padding:14px 18px;margin-bottom:10px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
                f'<div><span style="font-size:16px;font-weight:700;color:#e8f0f8;">{p["Player"]}</span>{injury_html}{sharp_html}{better_line_html}{pinnacle_html}{pinnacle_fade_html}<br/>'
                f'<span style="font-size:14px;color:{tier_color};font-weight:600;">{p["Side"]} {p["Line"]} {p["Prop"]}</span></div>'
                f'<div style="text-align:right;"><span style="background:{tier_color};color:#000;font-weight:700;font-size:12px;padding:3px 10px;border-radius:20px;">{p["Tier"]}</span></div>'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px;">'
                f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;"><div style="font-size:10px;color:#6a7a8a;">Edge</div><div style="font-size:18px;font-weight:700;color:#0ea5a0;">{p["EdgePct"]}</div></div>'
                f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;"><div style="font-size:10px;color:#6a7a8a;">2-Pick EV</div><div style="font-size:18px;font-weight:700;color:{ev_color};">{ev_2_display}</div></div>'
                f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;"><div style="font-size:10px;color:#6a7a8a;">Avg (10g)</div><div style="font-size:18px;font-weight:700;color:#e8f0f8;">{avg_val:.1f}</div></div>'
                f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;"><div style="font-size:10px;color:#6a7a8a;">Bet Size</div><div style="font-size:18px;font-weight:700;color:#e8a020;">${wager_display:.2f}</div></div>'
                f'</div></div>',
                unsafe_allow_html=True
            )
            with st.expander(f"\U0001f4ca Why this pick is rated {p['Tier']} \u2014 see the signals", expanded=False):
                chart_html = render_signal_chart(p, p.get("Sport", "NBA"))
                st.markdown(chart_html, unsafe_allow_html=True)
    else:
        st.info("No props loaded.")

    st.markdown("---")
    st.markdown("## \U0001f3af RECOMMENDED ACTION TODAY")
    board = st.session_state.board_data
    game_analysis = st.session_state.get("game_analysis", [])
    sovereign_elite = [p for p in board if p["Tier"] in ("SOVEREIGN", "ELITE")] if board else []
    approved = [p for p in board if p["Tier"] == "APPROVED"] if board else []
    if not board and not game_analysis:
        st.info("Load the board to see today's recommended action.")
    else:
        if len(sovereign_elite) >= 2:
            action_color, action_text = "#22c55e", "STRONG BETTING DAY"
            action_detail = f"{len(sovereign_elite)} elite props available."
        elif len(sovereign_elite) == 1:
            action_color, action_text = "#0ea5a0", "SELECTIVE DAY"
            action_detail = f"1 elite prop + {len(approved)} approved plays."
        elif len(approved) >= 3:
            action_color, action_text = "#4a90d9", "MODERATE DAY"
            action_detail = f"{len(approved)} approved plays. No elite props."
        else:
            action_color, action_text = "#e8a020", "LIGHT DAY"
            action_detail = "Limited quality. Consider sitting out or 1 pick max."
        col_act1, col_act2, col_act3 = st.columns(3)
        col_act1.metric("Elite Plays", len(sovereign_elite))
        col_act2.metric("Total Props", len(board) if board else 0)
        col_act3.metric("Game Edges", len(game_analysis))
        st.markdown(f"### {action_text}")
        st.caption(action_detail)
        if board:
            best_prop = board[0]
            st.markdown(f"\U0001f3c0 **Best Prop:** {best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']} \u2014 {best_prop['EdgePct']} edge")
        if game_analysis and game_analysis[0].get("best_bet"):
            bb = game_analysis[0]["best_bet"]
            st.markdown(f"\U0001f3df\ufe0f **Best Game:** {game_analysis[0]['matchup']} \u2192 {bb['pick']} \u2014 {bb['edge_pct']} edge")

    st.markdown("---")
    st.markdown("## \U0001f512 LOCK OF THE DAY")
    quality_board = st.session_state.get("quality_sorted_board", board)
    best = next((p for p in quality_board if p["Tier"] in ["SOVEREIGN","ELITE","APPROVED"]), None)
    if best:
        tier_color = TIER_COLORS.get(best['Tier'], "#0ea5a0")
        lock_score = best.get('LockScore', 0)
        lock_grade = "\U0001f7e2 PRIME LOCK" if lock_score >= 80 else "\U0001f7e1 SOLID LOCK" if lock_score >= 60 else "\U0001f7e0 SPECULATIVE" if lock_score >= 40 else "\U0001f534 RISKY"
        st.markdown(f"**{best['Player']} {best['Side']} {best['Line']} {best['Prop']}** | {best['Tier']} | Edge: {best['EdgePct']} | EV: {best.get('EV_2pick','\u2014')} | Lock Score: {lock_score}/100 {lock_grade}")
        if st.button("\U0001f512 Lock This Pick"):
            can_bet, risk_reason = check_daily_risk_limits(best["Sport"])
            if not can_bet:
                st.error(risk_reason)
            else:
                already = any(l.get("player") == best["Player"] and l.get("prop") == best["Prop"] for l in st.session_state.locks)
                if not already:
                    st.session_state.locks.append({"player": best["Player"], "prop": best["Prop"], "line": best["Line"], "side": best["Side"], "wager": best["Wager"], "prob": best["Prob"], "edge": best["Edge"], "tier": best["Tier"], "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "sport": best["Sport"]})
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    save_to_gist("locks", st.session_state.locks)
                    st.rerun()
                else:
                    st.warning("Already locked")
        with st.expander("\U0001f4ca Why this is the Lock of the Day \u2014 see all signals", expanded=False):
            if best:
                chart_html = render_signal_chart(best, best.get("Sport", "NBA"))
                st.markdown(chart_html, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("## \U0001f500 ALT LINE UPGRADES")
    alt_upgrades = st.session_state.get("alt_line_upgrades", [])
    if alt_upgrades:
        for upg in alt_upgrades[:6]:
            ev_color = "#22c55e" if upg["best_ev"] > 0 else "#e04040"
            st.markdown(f"**{upg['player']}** {upg['stat']}: ~~Main: {upg['main_line']}~~ \u2192 Alt OVER **{upg['best_line']} @ {upg['best_payout']}** | EV: {upg['best_ev']:+.1%} (+{upg['ev_improvement']:.1%} improvement)")
            lock_key = f"lock_alt_{upg['player']}_{upg['stat']}".replace(" ", "_")
            if st.button("\U0001f512 Lock Alt", key=lock_key):
                can_bet, risk_reason = check_daily_risk_limits(st.session_state.last_sport)
                if not can_bet:
                    st.error(risk_reason)
                else:
                    alt_lock = {"player": upg["player"], "prop": upg["stat"], "line": upg["best_line"], "side": "OVER", "wager": upg["wager"], "prob": upg["fair_prob"], "edge": upg["best_ev"], "tier": "ALT", "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "sport": st.session_state.last_sport, "source": "ParlayPlay_Alt", "alt_payout": upg["best_payout"], "alt_line": True, "main_line": upg["main_line"]}
                    already = any(l.get("player") == upg["player"] and l.get("prop") == upg["stat"] for l in st.session_state.locks)
                    if not already:
                        st.session_state.locks.append(alt_lock)
                        save_json_data(LOCKS_PATH, st.session_state.locks)
                        save_to_gist("locks", st.session_state.locks)
                        st.rerun()
    elif st.session_state.get("board_ready"):
        st.caption("No alt line upgrades found.")
    else:
        st.caption("Load board to check for alt line upgrades.")

    st.markdown("---")
    st.markdown("## \U0001f4b0 BEST +EV PROPS TODAY")
    if board:
        ev_filter = st.radio("Filter by pick count", ["2-pick", "3-pick", "Both"], index=0, horizontal=True, key="ev_filter")
        plus_ev_props = [p for p in board if (ev_filter == "2-pick" and str(p.get("EV_2pick","\u2014")).startswith("+")) or (ev_filter == "3-pick" and str(p.get("EV_3pick","\u2014")).startswith("+")) or (ev_filter == "Both" and (str(p.get("EV_2pick","\u2014")).startswith("+") or str(p.get("EV_3pick","\u2014")).startswith("+")))]
        if plus_ev_props:
            st.write(f"**{len(plus_ev_props)} +EV props found:**")
            for p in plus_ev_props[:8]:
                tier_color = TIER_COLORS.get(p["Tier"], "#7a8a9a")
                ev_show = p.get("EV_2pick","\u2014") if "2" in ev_filter else p.get("EV_3pick","\u2014")
                st.markdown(f"**{p['Player']}** {p['Side']} {p['Line']} {p['Prop']} | EV: {ev_show} | {p['Tier']}")
        else:
            st.info(f"No confirmed +EV props at {ev_filter} breakeven.")
    else:
        st.info("Load board to see +EV props.")

    st.markdown("---")
    st.markdown("## \U0001f48e ARBITRAGE OPPORTUNITIES")
    arb_opps = st.session_state.get("arb_opportunities", [])
    if arb_opps:
        st.success(f"\u2705 {len(arb_opps)} arbitrage opportunities found")
        for arb in arb_opps[:5]:
            st.markdown(f"**{arb['Player']}** {arb['Stat']} Line {arb['Line']}: OVER {arb['OVER Book']} {arb['OVER Odds']} / UNDER {arb['UNDER Book']} {arb['UNDER Odds']} | **{arb['Arb Profit']} GUARANTEED**")
    elif st.session_state.get("board_ready"):
        st.caption("No arb opportunities right now.")
    else:
        st.caption("Load board to scan for arbitrage opportunities.")

    st.markdown("---")
    st.markdown("## \U0001f4b0 BEST +EV GAMES TODAY")
    game_analysis_g = st.session_state.get("game_analysis", [])
    plus_ev_games = [g for g in game_analysis_g if g.get("best_bet") and g["best_edge"] >= 0.05]
    if plus_ev_games:
        for g in plus_ev_games[:5]:
            bb = g["best_bet"]
            st.markdown(f"**{g['matchup']}**: {bb['pick']} | Edge: {bb['edge_pct']} | {bb['type']}")
    else:
        st.info("No +EV games detected.")

    st.markdown("---")
    st.markdown("## \u26a1 PARLAY OF THE DAY \u2014 PROPS")
    top_props = [p for p in board if p["Tier"] in ("SOVEREIGN","ELITE","APPROVED")] if board else []
    if len(top_props) >= 2:
        n_picks_parlay = st.radio("Picks in parlay", [2, 3, 4, 5], index=1, horizontal=True, key="prop_parlay_picks")
        parlay_props = top_props[:n_picks_parlay]
        has_alt_lines = bool(st.session_state.get("parlayplay_alt_lines"))
        use_alt = False
        if has_alt_lines:
            use_alt = st.checkbox("\U0001f500 Optimize with alt lines (ParlayPlay)", value=True, key="use_alt_parlay")
        if use_alt and has_alt_lines:
            optimized_result = optimize_parlay_with_alt_lines(parlay_props, n_picks_parlay, st.session_state.bankroll)
        else:
            optimized_result = None
        display_props = optimized_result["props"] if optimized_result else parlay_props
        adjusted_probs, corr_notes = (detect_correlations(display_props) if not optimized_result else (optimized_result["adjusted_probs"], optimized_result["correlation_notes"]))
        for note in corr_notes:
            if "\u26a0\ufe0f" in note or "\U0001f6a8" in note:
                st.warning(note)
            else:
                st.info(note)
        if optimized_result and optimized_result["improved_count"] > 0:
            st.success(f"\U0001f500 {optimized_result['improved_count']} props upgraded to better alt lines \u2014 EV improved by +{optimized_result['total_ev_improvement']:.1%}")
        for idx, p in enumerate(display_props):
            improved = p.get("LineImproved", False)
            ev_val = p.get("OptimizedEV", calculate_prizepicks_ev(p.get("Prob", 0.5), n_picks_parlay))
            ev_color = "#22c55e" if ev_val > 0 else "#e04040"
            payout_display = p.get("OptimizedPayout", f"{PRIZEPICKS_MULTIPLIERS.get(n_picks_parlay, 3.0)}x")
            alt_note = f" [Alt \u2191 was {p.get('MainLine',0)}]" if improved else ""
            st.markdown(f"**{p['Player']}** {p['Side']} {p['Line']} {p['Prop']}{alt_note} | EV: {ev_val:+.1%} @ {payout_display}")
        if optimized_result:
            cp = optimized_result["combined_prob"]
            pp_ev = optimized_result["combined_ev"]
            breakeven = optimized_result["breakeven"]
            multiplier = optimized_result["multiplier"]
        else:
            multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks_parlay, 3.0)
            breakeven = 1 / multiplier
            cp = parlay_prob(adjusted_probs)
            pp_ev = cp - breakeven
        tw = sum(p.get("Wager_2pick", p.get("Wager", 0)) for p in display_props)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Combined Prob", f"{cp:.1%}")
        c2.metric(f"{n_picks_parlay}-pick Pays", f"{multiplier}x")
        c3.metric("Breakeven", f"{breakeven:.1%}")
        c4.metric("True EV", f"+{pp_ev:.1%} \u2705" if pp_ev > 0 else f"{pp_ev:.1%} \u274c")
        if pp_ev > 0:
            st.success(f"\u2705 This {n_picks_parlay}-pick is +EV. If hits: ${tw * multiplier:.2f}")
        else:
            st.error(f"\u274c This {n_picks_parlay}-pick is -EV.")
    else:
        st.caption("Need 2+ SOVEREIGN/ELITE/APPROVED props.")

    st.markdown("---")
    st.markdown("## \U0001f3df\ufe0f PARLAY OF THE DAY \u2014 GAMES")
    good_games = [g for g in game_analysis if g.get("best_bet") and g["best_edge"] >= 0.04]
    if len(good_games) >= 2:
        n_game_picks = st.radio("Games in parlay", [2, 3, 4], index=0, horizontal=True, key="game_parlay_picks")
        parlay_games = good_games[:n_game_picks]
        for g in parlay_games:
            bb = g["best_bet"]
            tier_color = TIER_COLORS.get(bb.get("tier","LEAN"), "#7a8a9a")
            st.markdown(f"**{g['matchup']}**: {bb['pick']} ({bb['type']}) | Edge: {bb['edge_pct']}")
        game_probs = [min(0.70, 0.5 + g["best_edge"]) for g in parlay_games]
        combined = parlay_prob(game_probs)
        breakeven_g = 0.524 ** n_game_picks
        ev_g = combined - breakeven_g
        c1, c2, c3 = st.columns(3)
        c1.metric("Combined Prob", f"{combined:.1%}")
        c2.metric("Breakeven (-110)", f"{breakeven_g:.1%}")
        c3.metric("True EV", f"+{ev_g:.1%} \u2705" if ev_g > 0 else f"{ev_g:.1%} \u274c")
        if ev_g > 0:
            st.success(f"\u2705 This {n_game_picks}-game parlay is +EV.")
        else:
            st.error("\u274c Combined probability below breakeven.")
    else:
        st.caption("Need 2+ games with detected edge.")

    st.markdown("---")
    st.markdown("## \U0001f310 BEST OF ALL SPORTS")
    all_sports_results = st.session_state.get("all_sports_results", None)
    col_scan1, col_scan2 = st.columns([2,1])
    with col_scan1:
        if st.button("\U0001f50d Find Today's Best Plays Across All Sports", key="scan_all_sports_btn"):
            with st.spinner("Scanning all sports boards..."):
                results = scan_all_sports_best_plays()
                st.session_state["all_sports_results"] = results
                st.rerun()
    with col_scan2:
        if all_sports_results:
            st.caption(f"Last scanned: {all_sports_results.get('timestamp','\u2014')}")
    if all_sports_results:
        best_props_all = all_sports_results.get("best_props", [])
        best_games_all = all_sports_results.get("best_games", [])
        if best_props_all:
            st.markdown(f"### \U0001f3c6 Top Props ({len(best_props_all)} found)")
            for p in best_props_all[:5]:
                st.markdown(f"**{p['Sport']}** \u2014 {p['Player']} {p['Side']} {p['Line']} {p['Prop']} | Edge: {p['EdgePct']} | {p['Tier']}")
        if best_games_all:
            st.markdown(f"### \U0001f3df\ufe0f Top Game Bets ({len(best_games_all)} found)")
            for g in best_games_all[:4]:
                bb = g.get("best_bet",{})
                st.markdown(f"**{g.get('sport','\u2014')}** \u2014 {g['matchup']}: {bb.get('pick','\u2014')} | Edge: {bb.get('edge_pct','\u2014')}")

# ----- TAB 1: FULL BOARD -----
with tabs[1]:
    st.markdown(f"## \U0001f4ca Full Board \u2014 {st.session_state.last_sport}")
    if st.session_state.board_data:
        tier_filter = st.multiselect("Filter by Tier", ["SOVEREIGN", "ELITE", "APPROVED", "LEAN"], default=["SOVEREIGN", "ELITE", "APPROVED"])
        filtered = [p for p in st.session_state.board_data if p["Tier"] in tier_filter]
        if filtered:
            display_df = make_display_df(filtered)
            show_cols = ["Player", "Stat", "Line", "Play", "Avg (10g)", "Fair %", "Edge", "2-Pick EV", "Bet Size", "Tier", "Pinnacle Prob", "Pinnacle Edge", "DK Salary", "DK Tier", "Better Line", "AN Grade", "AN Proj", "AN Tier", "AN Confirms", "Line Fair?", "Sharp $", "Market", "Confidence", "Injury", "Line Move", "Trend", "Source", "Consensus Prob", "Books", "Best Alt Line", "Alt EV", "Alt Payout"]
            show_cols = [c for c in show_cols if c in display_df.columns]
            st.dataframe(display_df[show_cols], width="stretch", hide_index=True)
            with st.expander("\U0001f4ca Signal Breakdown — Module Delta Chart"):
                st.caption("Each bar shows how strongly a signal pushes the pick toward OVER or UNDER, and how accurate that signal has historically been.")
                for prop in filtered[:10]:
                    tier_color = TIER_COLORS.get(prop["Tier"], "#7a8a9a")
                    st.markdown(f"""<div style="font-size:13px;font-weight:600;color:#e8f0f8;margin-top:10px;">
                        <span style="background:{tier_color};color:#000;font-size:10px;padding:2px 8px;border-radius:8px;margin-right:8px">{prop["Tier"]}</span>
                        {prop["Player"]} — {prop["Side"]} {prop["Line"]} {prop["Prop"]}
                        <span style="font-size:11px;color:#6a7a8a;margin-left:8px">Edge: {prop["EdgePct"]}</span>
                    </div>""", unsafe_allow_html=True)
                    chart_html = render_signal_chart(prop, prop.get("Sport", "NBA"))
                    st.markdown(chart_html, unsafe_allow_html=True)
            options = [f"{r['Player']} \u2014 {r['Side']} {r['Line']} {r['Prop']} (Edge: {r['EdgePct']} | {r['Tier']})" for r in filtered]
            if options:
                sel = st.selectbox("Select prop", range(len(options)), format_func=lambda i: options[i])
                if st.button("\U0001f512 Lock Selected"):
                    row = filtered[sel]
                    can_bet, risk_reason = check_daily_risk_limits(row["Sport"])
                    if not can_bet:
                        st.error(risk_reason)
                    else:
                        already = any(l.get("player") == row["Player"] and l.get("prop") == row["Prop"] for l in st.session_state.locks)
                        if not already:
                            st.session_state.locks.append({"player": row["Player"], "prop": row["Prop"], "line": row["Line"], "side": row["Side"], "wager": row.get("Wager_2pick", row["Wager"]), "prob": row["Prob"], "edge": row["Edge"], "tier": row["Tier"], "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "sport": row["Sport"]})
                            save_json_data(LOCKS_PATH, st.session_state.locks)
                            save_to_gist("locks", st.session_state.locks)
                            st.rerun()
                        else:
                            st.warning("Already locked")
        else:
            st.info("No props match selected filter.")
    else:
        st.info("Select a sport and click Load Board.")

# ----- TAB 2: GAME LINES -----
with tabs[2]:
    st.markdown(f"## \U0001f3df\ufe0f Game Lines \u2014 {st.session_state.last_sport}")
    if st.session_state.games:
        games_df = pd.DataFrame(st.session_state.games)
        display_cols = ["Matchup", "Status", "Spread", "Total", "Home ML", "Away ML", "Bovada Spread", "Bovada Total", "Bovada ML Home", "Bovada ML Away", "Odds Source", "Date"]
        display_cols = [c for c in display_cols if c in games_df.columns]
        st.dataframe(games_df[display_cols], width="stretch")
        st.markdown("---")
        st.markdown("### \u26a1 Line Movement History")
        movement_data = st.session_state.get("game_line_movement", {})
        sharp_flags_g = st.session_state.get("game_sharp_flags", {})
        if movement_data:
            for matchup, movements in movement_data.items():
                if not movements:
                    continue
                sharp = sharp_flags_g.get(matchup, {})
                sharp_label = " \u26a1 SHARP" if sharp.get("sharp") else ""
                with st.expander(f"{matchup}{sharp_label}"):
                    if len(movements) >= 2:
                        first, last = movements[-1], movements[0]
                        st.write(f"**Opening:** Spread {first.get('spread','\u2014')} | Total {first.get('over_under','\u2014')}")
                        st.write(f"**Current:** Spread {last.get('spread','\u2014')} | Total {last.get('over_under','\u2014')}")
                    else:
                        st.caption("Not enough movement data yet")
        else:
            st.caption("Load board to see line movement.")
        st.markdown("---")
        st.markdown("### \U0001f4ca Public Betting Splits")
        public_data_g = st.session_state.get("public_betting_data", {})
        if public_data_g:
            pb_rows = []
            for game_key, gd in public_data_g.items():
                teams = gd.get("teams", [])
                num_bets = gd.get("num_bets", 0)
                ml = gd.get("ml", {})
                total_d = gd.get("total", {})
                home_ml_pb = ml.get("home", {})
                away_ml_pb = ml.get("away", {})
                over_tot = total_d.get("over", {})
                sharp = gd.get("sharp_signals", [])
                pb_rows.append({"Matchup": " vs ".join(teams), "Bets": f"{num_bets:,}", "ML Home Tickets": f"{home_ml_pb.get('tickets', 0)}%", "ML Home Money": f"{home_ml_pb.get('money', 0)}%", "Over Tickets": f"{over_tot.get('tickets', 0)}%", "Over Money": f"{over_tot.get('money', 0)}%", "Sharp Signal": "\u26a1 " + sharp[0][:30] if sharp else "\u2014"})
            st.dataframe(pd.DataFrame(pb_rows), width="stretch", hide_index=True)
        else:
            st.caption("Load board to see public betting splits.")
    else:
        st.info("No games found.")

# ----- TAB 3: LOCKS & LEDGER -----
with tabs[3]:
    st.markdown("## \U0001f512 Active Locks")
    st.markdown("**Pick count for this result:**")
    pick_count_sel = st.radio("This bet was part of a:", [2, 3, 4, 5], horizontal=True, key="last_pick_count_radio")
    st.session_state["last_pick_count"] = pick_count_sel
    if st.session_state.locks:
        for i, lock in enumerate(st.session_state.locks.copy()):
            tier_color = TIER_COLORS.get(lock.get("tier","LEAN"), "#7a8a9a")
            edge_val = lock.get("edge", 0)
            prob_val = lock.get("prob", 0)
            ev_2 = calculate_prizepicks_ev(prob_val, 2)
            ev_color = "#22c55e" if ev_2 > 0 else "#e04040"
            alt_badge = f' <span style="background:#0ea5a0;color:#000;font-size:10px;padding:2px 6px;border-radius:10px;">ALT @ {lock.get("alt_payout","")}</span>' if lock.get("alt_line") else ""
            st.markdown(
                f'<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {tier_color};border-radius:8px;padding:12px 16px;margin-bottom:8px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">'
                f'<div><span style="color:#e8f0f8;font-weight:700;font-size:15px;">{lock["player"]}</span>'
                f'<span style="background:{tier_color};color:#000;font-size:10px;font-weight:700;padding:2px 8px;border-radius:12px;margin-left:8px;">{lock.get("tier","\u2014")}</span>'
                f'{alt_badge}<br/>'
                f'<span style="color:{tier_color};font-weight:600;">{lock["side"]} {lock["line"]} {lock["prop"]}</span>'
                f'<span style="color:#6a7a8a;font-size:11px;margin-left:10px;">{lock.get("sport","\u2014")} | Locked: {lock.get("timestamp","\u2014")}</span></div>'
                f'<div style="text-align:right;">'
                f'<div style="font-size:13px;color:#0ea5a0;font-weight:700;">Edge: {edge_val:.1%}</div>'
                f'<div style="font-size:13px;color:{ev_color};font-weight:600;">2-pick EV: {ev_2:+.1%}</div>'
                f'<div style="font-size:13px;color:#e8a020;font-weight:700;">Wager: ${lock["wager"]:.2f}</div>'
                f'</div></div></div>',
                unsafe_allow_html=True
            )
            col1, col2, col3, col4 = st.columns([4,1,1,1])
            if col2.button("\u2705 WIN", key=f"win_{i}"):
                pick_count = st.session_state.get("last_pick_count", 2)
                multiplier = PRIZEPICKS_MULTIPLIERS.get(pick_count, 3.0)
                profit = round(lock["wager"] * multiplier, 2)
                st.session_state.bankroll += profit
                st.session_state.history.append({**lock, "outcome": "WIN", "profit": profit, "loss": 0, "net": profit, "pick_count": pick_count, "stat_type": lock.get("prop", ""), "resolved_date": date.today().strftime("%Y-%m-%d")})
                save_json_data(BANKROLL_PATH, st.session_state.bankroll)
                save_to_gist("bankroll", st.session_state.bankroll)
                save_json_data(HISTORY_PATH, st.session_state.history)
                save_to_gist("history", st.session_state.history)
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)
                record_clv(lock, st.session_state.board_data)
                record_pinnacle_line(lock, st.session_state.board_data)
                # Store Pinnacle fair value at lock time for CLV tracking
                board_match = next((p for p in st.session_state.board_data
                    if normalize_name(p.get("Player","")) == normalize_name(lock.get("player",""))
                    and p.get("Prop","").lower() == lock.get("prop","").lower()), None)
                if board_match:
                    lock["pinnacle_prob_at_lock"] = board_match.get("PinnacleProb","—")
                    lock["pinnacle_edge_at_lock"] = board_match.get("PinnacleEdge")
                    lock["pinnacle_confirms"] = board_match.get("PinnacleConfirms", False)
                record_injury_performance(lock, "WIN", fetch_injury_news(lock.get("sport", "NBA")))
                record_signal_performance(lock, "WIN")
                compute_optimized_weights(lock.get("sport", "NBA"))
                st.rerun()
            if col3.button("\u274c LOSS", key=f"loss_{i}"):
                st.session_state.bankroll -= lock["wager"]
                st.session_state.history.append({**lock, "outcome": "LOSS", "profit": 0, "loss": lock["wager"], "net": -lock["wager"], "pick_count": st.session_state.get("last_pick_count", 2), "stat_type": lock.get("prop", ""), "resolved_date": date.today().strftime("%Y-%m-%d")})
                save_json_data(BANKROLL_PATH, st.session_state.bankroll)
                save_to_gist("bankroll", st.session_state.bankroll)
                save_json_data(HISTORY_PATH, st.session_state.history)
                save_to_gist("history", st.session_state.history)
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)
                record_clv(lock, st.session_state.board_data)
                record_pinnacle_line(lock, st.session_state.board_data)
                record_injury_performance(lock, "LOSS", fetch_injury_news(lock.get("sport", "NBA")))
                record_signal_performance(lock, "LOSS")
                compute_optimized_weights(lock.get("sport", "NBA"))
                st.rerun()
            if col4.button("\u21a9 VOID", key=f"void_{i}"):
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)
                st.rerun()
    else:
        st.info("No active locks.")

# ----- TAB 4: HISTORY -----
with tabs[4]:
    st.markdown("## \U0001f4c8 Full Bet History")
    if st.session_state.history:
        hist_df = pd.DataFrame(st.session_state.history)
        hist_df = hist_df.iloc[::-1].reset_index(drop=True)
        cols = [c for c in ["timestamp", "player", "prop", "line", "side", "tier", "wager", "outcome", "net"] if c in hist_df.columns]
        st.dataframe(hist_df[cols], width="stretch")
        if st.button("Clear History"):
            st.session_state.history = []
            save_json_data(HISTORY_PATH, [])
            save_to_gist("history", st.session_state.history)
            st.rerun()
        st.markdown("---")
        if len(st.session_state.history) >= 5:
            resolved = hist_df[hist_df["outcome"].isin(["WIN","LOSS"])] if "outcome" in hist_df.columns else pd.DataFrame()
            if not resolved.empty:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Hit Rate by Tier**")
                    if "tier" in resolved.columns:
                        tier_stats_h = resolved.groupby("tier").apply(lambda x: pd.Series({"Bets": len(x), "Hit Rate": f"{(x['outcome']=='WIN').mean():.1%}", "Net": f"${x['net'].sum():.2f}" if "net" in x else "\u2014"})).reset_index()
                        st.dataframe(tier_stats_h, width="stretch")
                with col_b:
                    st.markdown("**Hit Rate by Sport**")
                    if "sport" in resolved.columns:
                        sport_stats_h = resolved.groupby("sport").apply(lambda x: pd.Series({"Bets": len(x), "Hit Rate": f"{(x['outcome']=='WIN').mean():.1%}", "Net": f"${x['net'].sum():.2f}" if "net" in x else "\u2014"})).reset_index()
                        st.dataframe(sport_stats_h, width="stretch")
                if "net" in resolved.columns:
                    rc = resolved.copy()
                    rc["cumulative"] = DEFAULT_BANKROLL + rc["net"].cumsum()
                    st.line_chart(rc["cumulative"])
    st.markdown("---")
    st.markdown("### \U0001f4b0 ROI by Category")
    resolved_h = [h for h in st.session_state.history if h.get("outcome") in ("WIN","LOSS")]
    if len(resolved_h) >= 5:
        pick_roi = {}
        for h in resolved_h:
            pc = h.get("pick_count", 2)
            if pc not in pick_roi:
                pick_roi[pc] = {"bets": 0, "wagered": 0, "returned": 0}
            pick_roi[pc]["bets"] += 1
            pick_roi[pc]["wagered"] += h.get("wager", 0)
            if h["outcome"] == "WIN":
                pick_roi[pc]["returned"] += h.get("wager", 0) * PRIZEPICKS_MULTIPLIERS.get(pc, 3.0)
        roi_rows = []
        for pc in sorted(pick_roi.keys()):
            data = pick_roi[pc]
            if data["wagered"] > 0:
                roi = (data["returned"] - data["wagered"]) / data["wagered"] * 100
                roi_rows.append({"Pick Count": f"{pc}-pick", "Bets": data["bets"], "Wagered": f"${data['wagered']:.2f}", "Returned": f"${data['returned']:.2f}", "ROI": f"{'\U0001f7e2' if roi > 0 else '\U0001f534'} {roi:+.1f}%"})
        if roi_rows:
            st.dataframe(pd.DataFrame(roi_rows), width="stretch", hide_index=True)
    else:
        st.caption("Need 5+ resolved bets for ROI analysis.")
    st.markdown("---")
    st.markdown("### \U0001f921 Injury Performance Tracker")
    injury_results, n_injured = analyze_injury_performance()
    if injury_results is None:
        st.info(f"Injury tracker activates after 20 injury-tagged resolved bets. Current: {n_injured}. Need {20 - n_injured} more.")
    else:
        col_i1, col_i2, col_i3 = st.columns(3)
        col_i1.metric("Injured WR", f"{injury_results['injured_wr']:.1%}")
        col_i2.metric("Healthy WR", f"{injury_results['healthy_wr']:.1%}")
        col_i3.metric("WR Gap", f"{injury_results['wr_gap']:+.1%}")
    st.markdown("---")
    st.markdown("### \U0001f52c Signal Performance Analysis")
    signal_results, n_resolved = analyze_signal_performance()
    if signal_results is None:
        st.info(f"Signal analysis activates at 20 resolved bets. Current: {n_resolved}. Need {20 - n_resolved} more.")
    else:
        st.success(f"\u2705 Analyzing {n_resolved} resolved bets")
        st.dataframe(pd.DataFrame(signal_results), width="stretch", hide_index=True)
    st.markdown("---")
    st.markdown("### \U0001f4cd Pinnacle CLV Tracker")
    pinnacle_data = load_json_data(PINNACLE_LINES_PATH, [])
    if len(pinnacle_data) >= 5:
        avg_pclv = sum(r.get("pinnacle_clv", 0) for r in pinnacle_data) / len(pinnacle_data)
        pos_rate = sum(1 for r in pinnacle_data if r.get("positive", False)) / len(pinnacle_data)
        p1, p2, p3 = st.columns(3)
        p1.metric("Avg Pinnacle CLV", f"{avg_pclv:+.2f}")
        p2.metric("Positive Rate", f"{pos_rate:.1%}")
        p3.metric("Bets Tracked", len(pinnacle_data))
    else:
        st.info(f"Pinnacle CLV activates after 5 resolved bets. Need {5 - len(pinnacle_data)} more.")

# ----- TAB 5: LOG BET -----

# ----- TAB 5: SLIP ANALYZER -----
with tabs[5]:
    st.markdown("## 🔍 Slip Analyzer")
    st.caption("Enter any prop slip — from PrizePicks, ParlayPlay, Underdog, or anywhere. The model analyzes each pick and scores the full parlay.")

    board = st.session_state.board_data
    board_loaded = bool(board)

    if not board_loaded:
        st.info("💡 Load the board first for full signal analysis. Or enter picks manually below — we'll analyze using historical averages.")

    st.markdown("### Enter Your Slip")
    st.caption("Add 2–6 picks. The model will analyze each one individually and score the combined parlay.")

    # Initialize slip state
    if "analyzer_picks" not in st.session_state:
        st.session_state["analyzer_picks"] = []

    # Screenshot upload section
    with st.expander("📸 Upload a screenshot of your slip (auto-parse)", expanded=False):
        slip_imgs = st.file_uploader(
            "Upload screenshot of your PrizePicks, ParlayPlay, or Underdog slip",
            type=["jpg", "jpeg", "png", "heic", "webp"],
            key="slip_screenshot",
            accept_multiple_files=True
        )
        if slip_imgs:
            if st.button("🔍 Parse Screenshot", key="parse_slip_screenshot"):
                all_parsed = []
                with st.spinner("Reading screenshot..."):
                    for img_file in slip_imgs:
                        img_bytes = img_file.read()
                        result = parse_bet_screenshot_ocr(img_bytes)
                        if result:
                            all_parsed.extend(result)
                if all_parsed:
                    # Convert OCR results to analyzer format
                    analyzer_picks = []
                    for bet in all_parsed:
                        if bet.get("outcome") in ("WIN", "LOSS"):
                            continue  # Skip settled bets
                        analyzer_picks.append({
                            "player": bet.get("player", ""),
                            "stat": bet.get("prop", ""),
                            "line": float(bet.get("line", 0) or 0),
                            "side": bet.get("side", "OVER"),
                            "sport": bet.get("sport", "NBA"),
                        })
                    if analyzer_picks:
                        st.session_state["analyzer_picks"] = analyzer_picks
                        st.success(f"✅ Found {len(analyzer_picks)} picks from screenshot")
                        st.rerun()
                    else:
                        st.warning("Screenshot parsed but no pending picks found. Try the paste option below.")
                else:
                    st.error("Could not read screenshot. Try the OCR Debug in Log Bet tab, or paste the slip manually below.")
        with st.expander("🔍 OCR Debug — what was extracted", expanded=False):
            raw = st.session_state.get("ocr_raw_text", "")
            if raw:
                st.text(raw[:500])
            else:
                st.caption("Upload a screenshot to see extracted text.")

    # Quick paste section
    with st.expander("📋 Paste a slip (auto-parse)", expanded=False):
        paste_text = st.text_area(
            "Paste your slip here (one pick per line)",
            placeholder="Nikola Jokic OVER 27.5 Points\nJayson Tatum OVER 8.5 Rebounds\nLuka Doncic OVER 7.5 Assists",
            height=120,
            key="slip_paste_input"
        )
        if st.button("📥 Parse Slip", key="parse_slip_btn"):
            if paste_text.strip():
                import re
                parsed_picks = []
                for line in paste_text.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    # Pattern: Player Name OVER/UNDER line Stat
                    # or: Player Name MORE/LESS line Stat
                    m = re.match(
                        r"([A-Za-z][A-Za-z\s\.'-]+?)\s+(OVER|UNDER|MORE|LESS)\s+([\d\.]+)\s+(.+)",
                        line, re.IGNORECASE
                    )
                    if m:
                        player = m.group(1).strip()
                        side = "OVER" if m.group(2).upper() in ("OVER","MORE") else "UNDER"
                        try:
                            line_val = float(m.group(3))
                        except:
                            continue
                        stat = m.group(4).strip()
                        parsed_picks.append({
                            "player": player, "stat": stat,
                            "line": line_val, "side": side,
                            "sport": "NBA"
                        })
                if parsed_picks:
                    st.session_state["analyzer_picks"] = parsed_picks
                    st.success(f"✅ Parsed {len(parsed_picks)} picks")
                    st.rerun()
                else:
                    st.error("Could not parse. Format: Player Name OVER/UNDER Line Stat")

    st.markdown("---")
    st.markdown("### Manual Entry")

    col_sa1, col_sa2 = st.columns(2)
    with col_sa1:
        sa_player = st.text_input("Player Name", placeholder="Nikola Jokic", key="sa_player")
        sa_stat = st.selectbox("Stat", [
            "Points", "Rebounds", "Assists", "3-PT Made", "Steals",
            "Blocked Shots", "Turnovers", "Pts+Reb+Ast", "Pts+Reb",
            "Pts+Ast", "Reb+Ast", "Fantasy Score", "Double-Double",
            "Hits", "Home Runs", "Strikeouts", "Total Bases",
            "Goals", "Shots On Goal", "Passing Yards", "Rushing Yards",
            "Receiving Yards", "Receptions", "Touchdowns"
        ], key="sa_stat")
    with col_sa2:
        sa_line = st.number_input("Line", min_value=0.0, value=0.0, step=0.5, key="sa_line")
        sa_side = st.radio("Side", ["OVER", "UNDER"], horizontal=True, key="sa_side")
        sa_sport = st.selectbox("Sport", SPORTS, key="sa_sport")

    if st.button("➕ Add to Slip", key="sa_add_pick"):
        if sa_player and sa_line > 0:
            st.session_state["analyzer_picks"].append({
                "player": sa_player, "stat": sa_stat,
                "line": sa_line, "side": sa_side, "sport": sa_sport
            })
            st.rerun()
        else:
            st.error("Enter player name and line.")

    # Show current slip
    if st.session_state["analyzer_picks"]:
        st.markdown("---")
        st.markdown(f"### Your Slip ({len(st.session_state['analyzer_picks'])} picks)")

        for i, pick in enumerate(st.session_state["analyzer_picks"]):
            col_p1, col_p2 = st.columns([5, 1])
            with col_p1:
                st.markdown(f"**{pick['player']}** {pick['side']} {pick['line']} {pick['stat']} ({pick.get('sport','NBA')})")
            with col_p2:
                if st.button("❌", key=f"remove_pick_{i}"):
                    st.session_state["analyzer_picks"].pop(i)
                    st.rerun()

        if st.button("🗑️ Clear Slip", key="clear_slip"):
            st.session_state["analyzer_picks"] = []
            st.rerun()

        st.markdown("---")

        if st.button("🔍 Analyze This Slip", key="analyze_slip_btn", type="primary"):
            picks = st.session_state["analyzer_picks"]
            results = []

            for pick in picks:
                player = pick["player"]
                stat = pick["stat"]
                line = pick["line"]
                side = pick["side"]
                sport = pick.get("sport", "NBA")

                # Try to find this prop in the loaded board first
                board_match = None
                if board:
                    norm_player = normalize_name(player)
                    for b in board:
                        if normalize_name(b.get("Player","")) == norm_player and                            b.get("Prop","").lower() == stat.lower():
                            board_match = b
                            break

                if board_match:
                    # Use full model data
                    edge = board_match.get("Edge", 0)
                    prob = board_match.get("Prob", 0.5)
                    avg = board_match.get("Avg", 0)
                    tier = board_match.get("Tier", "LEAN")
                    ev_2 = board_match.get("EV_2pick", "—")
                    better_line = board_match.get("BetterLineNote", "")
                    dk_note = board_match.get("DKSalaryNote", "")
                    sharp_flag = board_match.get("SharpFlag", "")
                    signal_base = board_match.get("SignalBase", 0)
                    signal_def = board_match.get("SignalDefense", 0)
                    confidence = board_match.get("SEM", "—")
                    data_source = "📊 Full model"

                    # Check if the line matches
                    board_line = board_match.get("Line", line)
                    line_diff = round(float(line) - float(board_line), 1)
                    line_note = ""
                    if line_diff != 0:
                        direction = "higher" if line_diff > 0 else "lower"
                        line_note = f"⚠️ Your line ({line}) is {abs(line_diff)} {direction} than board ({board_line})"
                        # Adjust edge for line difference
                        if side == "OVER" and line_diff > 0:
                            edge = max(0, edge - 0.03 * abs(line_diff))
                        elif side == "OVER" and line_diff < 0:
                            edge = min(0.30, edge + 0.03 * abs(line_diff))
                else:
                    # No board match — use historical averages
                    season_avgs = PLAYER_AVERAGES.get(sport, {})
                    player_data = season_avgs.get(player, {})
                    stat_key = stat.upper().replace(" ","_").replace("+","_").replace("-","_")
                    avg = player_data.get(stat_key, player_data.get(stat[:3].upper(), 0))

                    if avg > 0:
                        diff = avg - line if side == "OVER" else line - avg
                        std = compute_std_dev(None, sport) or 4.0
                        z = diff / std if std > 0 else 0
                        from scipy import stats as sp_stats
                        prob = float(sp_stats.norm.cdf(z))
                        edge = max(-0.15, min(0.25, prob - 0.577))
                    else:
                        prob = 0.5
                        edge = 0.0
                        avg = None

                    tier = get_tier(edge, sport)
                    ev_2 = f"{calculate_prizepicks_ev(prob, 2):+.1%}"
                    better_line = ""
                    dk_note = ""
                    sharp_flag = ""
                    line_note = ""
                    confidence = "Historical avg only"
                    data_source = "📚 Historical averages"

                # Determine recommendation
                if edge >= 0.08:
                    rec = "✅ STRONG PLAY"
                    rec_color = "#22c55e"
                elif edge >= 0.04:
                    rec = "✅ PLAY"
                    rec_color = "#0ea5a0"
                elif edge >= 0.0:
                    rec = "⚠️ LEAN"
                    rec_color = "#e8a020"
                elif edge >= -0.05:
                    rec = "⚠️ WEAK"
                    rec_color = "#e07020"
                else:
                    rec = "❌ FADE"
                    rec_color = "#e04040"

                results.append({
                    "player": player, "stat": stat, "line": line,
                    "side": side, "sport": sport,
                    "edge": edge, "prob": prob, "avg": avg,
                    "tier": tier, "ev_2": ev_2,
                    "rec": rec, "rec_color": rec_color,
                    "better_line": better_line,
                    "dk_note": dk_note,
                    "sharp_flag": sharp_flag,
                    "line_note": line_note,
                    "confidence": confidence,
                    "data_source": data_source,
                })

            st.session_state["analyzer_results"] = results

    # Display results
    if st.session_state.get("analyzer_results"):
        results = st.session_state["analyzer_results"]
        st.markdown("## 📊 Analysis Results")

        all_probs = [r["prob"] for r in results]
        combined_prob = parlay_prob(all_probs)
        n_picks = len(results)
        multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)
        breakeven = prizepicks_breakeven_prob(n_picks)
        parlay_ev = combined_prob - breakeven
        ev_color = "#22c55e" if parlay_ev > 0 else "#e04040"

        # Overall verdict
        strong_plays = sum(1 for r in results if r["edge"] >= 0.08)
        fades = sum(1 for r in results if r["edge"] < -0.05)

        if fades > 0:
            overall = f"❌ AVOID — {fades} pick(s) model says FADE"
            overall_color = "#e04040"
        elif strong_plays == n_picks:
            overall = "✅ STRONG SLIP — All picks have solid edge"
            overall_color = "#22c55e"
        elif strong_plays >= n_picks // 2:
            overall = "✅ GOOD SLIP — Most picks have edge"
            overall_color = "#0ea5a0"
        elif parlay_ev > 0:
            overall = "⚠️ MARGINAL — Positive EV but weak individual picks"
            overall_color = "#e8a020"
        else:
            overall = "❌ SKIP — Combined EV is negative"
            overall_color = "#e04040"

        st.markdown(
            f'<div style="background:#0d1520;border:2px solid {overall_color};border-radius:10px;'
            f'padding:16px 20px;margin-bottom:14px;">'
            f'<div style="font-size:18px;font-weight:700;color:{overall_color};margin-bottom:8px;">{overall}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:#6a7a8a;text-transform:uppercase">Combined Prob</div>'
            f'<div style="font-size:20px;font-weight:700;color:#e8f0f8">{combined_prob:.1%}</div></div>'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:#6a7a8a;text-transform:uppercase">{n_picks}-pick Payout</div>'
            f'<div style="font-size:20px;font-weight:700;color:#e8f0f8">{multiplier}x</div></div>'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:#6a7a8a;text-transform:uppercase">Breakeven</div>'
            f'<div style="font-size:20px;font-weight:700;color:#e8f0f8">{breakeven:.1%}</div></div>'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:#6a7a8a;text-transform:uppercase">True EV</div>'
            f'<div style="font-size:20px;font-weight:700;color:{ev_color}">{parlay_ev:+.1%}</div></div>'
            f'</div></div>',
            unsafe_allow_html=True
        )

        # Individual pick results
        st.markdown("### Pick-by-Pick Breakdown")
        for r in results:
            tier_color = TIER_COLORS.get(r["tier"], "#7a8a9a")
            avg_display = f"{r['avg']:.1f}" if r["avg"] else "No data"
            st.markdown(
                f'<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {r["rec_color"]};'
                f'border-radius:8px;padding:12px 16px;margin-bottom:10px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;margin-bottom:8px;">'
                f'<div><span style="font-size:15px;font-weight:700;color:#e8f0f8">{r["player"]}</span>'
                f'<span style="color:{tier_color};margin-left:8px;font-size:13px">{r["side"]} {r["line"]} {r["stat"]}</span>'
                f'<span style="background:{tier_color};color:#000;font-size:9px;font-weight:700;padding:2px 7px;border-radius:8px;margin-left:8px">{r["tier"]}</span></div>'
                f'<div style="background:{r["rec_color"]}22;border:1px solid {r["rec_color"]}44;border-radius:8px;'
                f'padding:5px 12px;font-size:13px;font-weight:700;color:{r["rec_color"]}">{r["rec"]}</div>'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px;">'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:#6a7a8a;text-transform:uppercase">Edge</div>'
                f'<div style="font-size:15px;font-weight:600;color:{r["rec_color"]}">{r["edge"]:+.1%}</div></div>'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:#6a7a8a;text-transform:uppercase">Hit Prob</div>'
                f'<div style="font-size:15px;font-weight:600;color:#e8f0f8">{r["prob"]:.1%}</div></div>'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:#6a7a8a;text-transform:uppercase">Avg vs Line</div>'
                f'<div style="font-size:15px;font-weight:600;color:#e8f0f8">{avg_display}</div></div>'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:#6a7a8a;text-transform:uppercase">2-pick EV</div>'
                f'<div style="font-size:15px;font-weight:600;color:#22c55e">{r["ev_2"]}</div></div>'
                f'</div>'
                f'<div style="font-size:11px;color:#6a7a8a">📡 {r["data_source"]} | Confidence: {r["confidence"]}'
                f'{" | " + r["sharp_flag"] if r["sharp_flag"] else ""}'
                f'{" | " + r["dk_note"] if r["dk_note"] else ""}</div>'
                f'{"<div style=\"font-size:11px;color:#22c55e;margin-top:4px\">⚡ " + r["better_line"] + "</div>" if r["better_line"] else ""}'
                f'{"<div style=\"font-size:11px;color:#e8a020;margin-top:4px\">⚠️ " + r["line_note"] + "</div>" if r["line_note"] else ""}'
                f'</div>',
                unsafe_allow_html=True
            )

        # Lock all good picks button
        good_picks = [r for r in results if r["edge"] >= 0.04]
        if good_picks and board:
            st.markdown("---")
            if st.button(f"🔒 Lock all {len(good_picks)} good picks from this slip", key="lock_slip_picks"):
                locked = 0
                for r in good_picks:
                    norm = normalize_name(r["player"])
                    board_match = next((b for b in board if normalize_name(b.get("Player","")) == norm and b.get("Prop","").lower() == r["stat"].lower()), None)
                    if board_match:
                        already = any(l.get("player") == r["player"] and l.get("prop") == r["stat"] for l in st.session_state.locks)
                        if not already:
                            st.session_state.locks.append({
                                "player": r["player"], "prop": r["stat"],
                                "line": r["line"], "side": r["side"],
                                "wager": active_unit(), "prob": r["prob"],
                                "edge": r["edge"], "tier": r["tier"],
                                "status": "PENDING",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "sport": r["sport"]
                            })
                            locked += 1
                if locked:
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    save_to_gist("locks", st.session_state.locks)
                    st.success(f"✅ Locked {locked} picks")
                    st.rerun()

        # Generate slip summary report
        st.markdown("---")
        st.markdown("## 📋 Slip Analysis Report")
        st.caption("Same format as your daily Gem brief — copy and paste into your Gemini Gem for deeper analysis.")
        slip_summary = generate_slip_summary(st.session_state["analyzer_picks"], results)
        st.text_area(
            "Copy this into your Gem:",
            value=slip_summary,
            height=400,
            key="slip_summary_output"
        )
        st.caption("💡 Ctrl+A to select all, Ctrl+C to copy.")

with tabs[6]:
    st.markdown("## \U0001f4dd Log A Bet")

    st.caption("Log any bet placed outside of BetCouncil \u2014 from PrizePicks app, Bovada, MyBookie, or anywhere. Feeds into all tracking systems.")
    log_tab1, log_tab2 = st.tabs(["Manual Entry", "Bulk Entry"])
    with log_tab1:
        st.markdown("### 📸 Upload Screenshot")
        st.caption("Upload one or more screenshots of your bet slip or result.")

        # Use a counter key so we can reset the uploader after submitting
        if "uploader_key" not in st.session_state:
            st.session_state["uploader_key"] = 0

        uploaded_imgs = st.file_uploader(
            "Upload bet screenshots (select multiple)",
            type=["jpg", "jpeg", "png", "heic", "webp"],
            key=f"bet_screenshot_{st.session_state['uploader_key']}",
            accept_multiple_files=True,
        )
        if uploaded_imgs:
            up_col1, up_col2 = st.columns([3, 1])
            up_col1.caption(f"{len(uploaded_imgs)} screenshot(s) loaded")
            if up_col2.button("🗑️ Clear", key="clear_uploader_btn"):
                st.session_state["uploader_key"] += 1
                st.session_state["parsed_bets"] = []
                st.session_state["ocr_raw_text"] = ""
                st.rerun()
            if st.button("🔍 Parse All Screenshots", key="parse_screenshot_btn"):
                all_parsed = []
                with st.spinner("Reading screenshots..."):
                    for img_file in uploaded_imgs:
                        img_bytes = img_file.read()
                        result = parse_bet_screenshot_ocr(img_bytes)
                        if result:
                            all_parsed.extend(result)
                if all_parsed:
                    st.session_state["parsed_bets"] = all_parsed
                    st.success(f"✅ Found {len(all_parsed)} bet(s) across {len(uploaded_imgs)} screenshots")
                else:
                    st.error("Could not read screenshots. Try manual entry below.")
        parsed_bets = st.session_state.get("parsed_bets", [])
        if parsed_bets:
            top_c1, top_c2 = st.columns([3, 1])
            top_c1.markdown("### \u2705 Confirm Parsed Bets")
            if top_c2.button("\u274c Clear All", key="clear_parsed_bets_top"):
                st.session_state["parsed_bets"] = []
                st.session_state["ocr_raw_text"] = ""
                st.rerun()
            for idx, bet in enumerate(parsed_bets):
                if bet.get("outcome") == "PENDING":
                    st.caption(f"\u23f3 {bet['player']} \u2014 PENDING, skipping")
                    continue
                with st.expander(f"{bet.get('player','?')} \u2014 {bet.get('outcome','?')}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Prop:** {bet.get('prop','?')}")
                    c1.write(f"**Line:** {bet.get('line','?')}")
                    c2.write(f"**Side:** {bet.get('side','?')}")
                    c2.write(f"**Sport:** {bet.get('sport','?')}")
                    c3.write(f"**Outcome:** {bet.get('outcome','?')}")
                    c3.write(f"**Wager:** ${bet.get('wager',0):.2f}")
            col_confirm1, col_confirm2 = st.columns(2)
            parsed_date = col_confirm1.date_input("Date of these bets", value=date.today(), key="parsed_bet_date")
            if col_confirm1.button("\u2705 Submit All Parsed Bets", key="submit_parsed_bets"):
                submitted = 0
                for bet in parsed_bets:
                    if bet.get("outcome") not in ("WIN","LOSS"):
                        continue
                    bet_date_str = datetime.combine(parsed_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M")
                    try:
                        log_manual_bet(player=bet.get("player",""), prop=bet.get("prop",""), line=float(bet.get("line",0) or 0), side=bet.get("side","OVER"), sport=bet.get("sport","NBA"), outcome=bet.get("outcome","LOSS"), wager=float(bet.get("wager",0) or 0), pick_count=int(bet.get("pick_count",2) or 2), bet_type=bet.get("bet_type","prop"), source=bet.get("source","Screenshot Import"), bet_date=bet_date_str)
                        submitted += 1
                    except:
                        continue
                if submitted > 0:
                    st.success(f"\u2705 Submitted {submitted} bets \u2014 Bankroll: ${st.session_state.bankroll:.2f}")
                    st.session_state["parsed_bets"] = []
                    st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1
                    st.session_state["ocr_raw_text"] = ""
                    st.rerun()
            if col_confirm2.button("❌ Clear Parsed Bets", key="clear_parsed_bets"):
                st.session_state["parsed_bets"] = []
                st.session_state["ocr_raw_text"] = ""
                st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1
                st.rerun()
        with st.expander("\U0001f50d OCR Debug \u2014 Raw Text Extracted"):
            raw_ocr = st.session_state.get("ocr_raw_text", "")
            if raw_ocr:
                st.text(raw_ocr)
            else:
                st.caption("Upload a screenshot to see extracted text.")
        st.markdown("---")
        st.markdown("### Single Bet")
        bet_type_sel = st.radio("Bet type", ["Player Prop", "Game Line"], horizontal=True, key="log_bet_type")
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            log_sport = st.selectbox("Sport", SPORTS, key="log_sport")
            log_date = st.date_input("Date of bet", value=date.today(), key="log_date")
            log_outcome = st.radio("Result", ["WIN", "LOSS"], horizontal=True, key="log_outcome")
            log_wager = st.number_input("Amount wagered ($)", min_value=0.0, value=float(active_unit()), step=1.0, key="log_wager")
        with col_l2:
            if bet_type_sel == "Player Prop":
                log_player = st.text_input("Player name", key="log_player")
                log_prop = st.text_input("Stat (e.g. Points, Rebounds)", key="log_prop")
                log_line = st.number_input("Line", min_value=0.0, value=0.0, step=0.5, key="log_line")
                log_side = st.radio("Side", ["OVER", "UNDER"], horizontal=True, key="log_side")
                log_pick_count = st.radio("Part of a", [2, 3, 4, 5], horizontal=True, key="log_pick_count")
                log_source = st.selectbox("Platform", ["PrizePicks", "Underdog", "ParlayPlay", "Other"], key="log_source")
            else:
                log_player = st.text_input("Matchup (e.g. CLE @ NYK)", key="log_game_matchup")
                log_prop = st.selectbox("Bet type", ["Moneyline", "Spread", "Total OVER", "Total UNDER", "Alt Spread", "Alt Total"], key="log_game_bet_type")
                log_line = st.number_input("Line/Number", min_value=-1000.0, value=0.0, step=0.5, key="log_game_line")
                log_side = log_prop
                log_pick_count = 1
                log_source = st.selectbox("Book", ["Bovada", "MyBookie", "DraftKings", "FanDuel", "BetMGM", "Other"], key="log_game_source")
        log_notes = st.text_input("Notes (optional)", placeholder="e.g. Jokic questionable, sharp line move", key="log_notes")
        log_edge = st.number_input("Edge % (optional)", min_value=0.0, max_value=50.0, value=0.0, step=0.1, key="log_edge") / 100.0
        st.markdown("---")
        if st.button("\u2705 Submit Bet Result", key="submit_manual_bet"):
            if not log_player:
                st.error("Enter player name or matchup.")
            elif log_wager <= 0:
                st.error("Enter wager amount.")
            else:
                bet_date_str = datetime.combine(log_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M")
                result = log_manual_bet(player=log_player, prop=log_prop, line=log_line, side=log_side, sport=log_sport, outcome=log_outcome, wager=log_wager, pick_count=log_pick_count, bet_type="prop" if bet_type_sel == "Player Prop" else "game", source=log_source, bet_date=bet_date_str, edge=log_edge if log_edge > 0 else None, notes=log_notes)
                st.success(f"\u2705 Logged: {log_player} \u2014 {log_outcome} | Net: ${result['net']:+.2f}")
                st.caption(f"Bankroll updated to ${st.session_state.bankroll:.2f} | History: {len(st.session_state.history)} bets")
                st.rerun()
    with log_tab2:
        st.markdown("### 📋 Paste PrizePicks Results")
        st.caption(
            "Copy your PrizePicks result screen text and paste it here. "
            "The parser reads the standard block format automatically. "
            "**All picks are assumed OVER** — flip any UNDER picks in the confirm step."
        )
        pp_text_input = st.text_area(
            "Paste PrizePicks result text",
            height=260,
            key="pp_text_paste",
            placeholder=(
                "José Ramírez\nIF\nMLB\nCLE\n1\nvs\nPHI\n0\nFinal\n1.5\nHits+Runs+RBIs\n1\n"
                "Junior Caminero\nIF\nMLB\nTB\n4\nvs\nNYY\n2\nFinal\n1.5\nHits+Runs+RBIs\n2"
            ),
        )

        pp_wager_col, pp_picks_col, pp_parse_col = st.columns([2, 2, 2])
        pp_wager  = pp_wager_col.number_input("Wager ($)", min_value=0.0, value=1.0, step=0.5, key="pp_wager")
        pp_picks  = pp_picks_col.number_input("# Picks", min_value=2, max_value=6, value=4, key="pp_picks")
        pp_date   = st.date_input("Date of entry", value=date.today(), key="pp_paste_date")

        if st.button("🔍 Parse PrizePicks Text", key="parse_pp_text_btn"):
            if not pp_text_input.strip():
                st.error("Nothing to parse — paste your result text above.")
            else:
                parsed_pp = parse_prizepicks_text(pp_text_input)
                if parsed_pp:
                    for b in parsed_pp:
                        b["wager"]      = pp_wager
                        b["pick_count"] = pp_picks
                    st.session_state["pp_parsed_bets"] = parsed_pp
                    st.success(f"✅ Found {len(parsed_pp)} prop(s) — review below, then submit.")
                else:
                    st.error("Could not parse any bets. Check that each block has 12 lines (name → position → sport … → stat → result).")

        pp_parsed = st.session_state.get("pp_parsed_bets", [])
        if pp_parsed:
            st.markdown("#### Confirm Parsed Props")
            st.caption("Flip any UNDER picks using the toggle. Edit outcomes if needed.")
            for idx, bet in enumerate(pp_parsed):
                with st.expander(f"{bet['player']}  —  {bet['prop']}  {bet['line']}  →  result: {bet.get('result', '?')}", expanded=True):
                    ec1, ec2, ec3 = st.columns(3)
                    outcome_choice = ec1.selectbox(
                        "Outcome", ["WIN", "LOSS", "PENDING"],
                        index=["WIN", "LOSS", "PENDING"].index(bet["outcome"]) if bet["outcome"] in ("WIN","LOSS","PENDING") else 2,
                        key=f"pp_outcome_{idx}"
                    )
                    side_choice = ec2.selectbox(
                        "Side", ["OVER", "UNDER"],
                        index=0 if bet["side"] == "OVER" else 1,
                        key=f"pp_side_{idx}"
                    )
                    sport_choice = ec3.selectbox(
                        "Sport", ["NBA","MLB","NHL","NFL","WNBA","NCAAB","NCAAF"],
                        index=["NBA","MLB","NHL","NFL","WNBA","NCAAB","NCAAF"].index(bet["sport"]) if bet["sport"] in ["NBA","MLB","NHL","NFL","WNBA","NCAAB","NCAAF"] else 1,
                        key=f"pp_sport_{idx}"
                    )
                    pp_parsed[idx]["outcome"] = outcome_choice
                    pp_parsed[idx]["side"]    = side_choice
                    pp_parsed[idx]["sport"]   = sport_choice

            sub_col, clr_col = st.columns(2)
            if sub_col.button("✅ Submit All", key="submit_pp_parsed"):
                submitted_pp = 0
                for bet in pp_parsed:
                    if bet.get("outcome") not in ("WIN", "LOSS"):
                        continue
                    try:
                        bd_str = datetime.combine(pp_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M")
                        log_manual_bet(
                            player=bet["player"], prop=bet["prop"],
                            line=float(bet["line"]), side=bet["side"],
                            sport=bet["sport"], outcome=bet["outcome"],
                            wager=float(bet["wager"]), pick_count=int(bet["pick_count"]),
                            bet_type="prop", source="PrizePicks Text Import",
                            bet_date=bd_str,
                        )
                        submitted_pp += 1
                    except Exception:
                        continue
                if submitted_pp > 0:
                    st.success(f"✅ Submitted {submitted_pp} bets — Bankroll: ${st.session_state.bankroll:.2f}")
                    st.session_state["pp_parsed_bets"] = []
                    st.rerun()
            if clr_col.button("❌ Clear", key="clear_pp_parsed"):
                st.session_state["pp_parsed_bets"] = []
                st.rerun()

        st.markdown("---")
        st.markdown("### CSV Bulk Entry")
        st.caption("Paste multiple bets at once. One bet per line: Player, Stat, Line, OVER/UNDER, Sport, WIN/LOSS, Wager, PickCount")
        st.caption("Example: Nikola Jokic, Points, 26.5, OVER, NBA, WIN, 25, 2")
        bulk_text = st.text_area("Paste bets here", height=200, key="bulk_bet_text", placeholder="Nikola Jokic, Points, 26.5, OVER, NBA, WIN, 25, 2\nJayson Tatum, Rebounds, 8.5, OVER, NBA, LOSS, 25, 2")
        bulk_date = st.date_input("Date for all bets", value=date.today(), key="bulk_date")
        if st.button("\U0001f4e5 Import All Bets", key="import_bulk_bets"):
            if not bulk_text.strip():
                st.error("No bets entered.")
            else:
                lines_list = [l.strip() for l in bulk_text.strip().split("\n") if l.strip()]
                success_count = 0
                error_count = 0
                for line_text in lines_list:
                    try:
                        parts = [p.strip() for p in line_text.split(",")]
                        if len(parts) < 7:
                            error_count += 1
                            continue
                        player_b, prop_b = parts[0], parts[1]
                        line_val_b = float(parts[2])
                        side_b = parts[3].upper()
                        sport_b = parts[4].upper()
                        outcome_b = parts[5].upper()
                        wager_b = float(parts[6])
                        pick_count_b = int(parts[7]) if len(parts) > 7 else 2
                        if outcome_b not in ("WIN", "LOSS"):
                            error_count += 1
                            continue
                        bet_date_str_b = datetime.combine(bulk_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M")
                        log_manual_bet(player=player_b, prop=prop_b, line=line_val_b, side=side_b, sport=sport_b, outcome=outcome_b, wager=wager_b, pick_count=pick_count_b, bet_type="prop", source="Manual Import", bet_date=bet_date_str_b)
                        success_count += 1
                    except:
                        error_count += 1
                        continue
                if success_count > 0:
                    st.success(f"\u2705 Imported {success_count} bets | Bankroll: ${st.session_state.bankroll:.2f}")
                if error_count > 0:
                    st.warning(f"\u26a0\ufe0f {error_count} lines skipped \u2014 check format")
                if success_count > 0:
                    st.rerun()
    st.markdown("---")
    st.markdown("### \U0001f4ca Recent Manual Entries")
    manual_history = [h for h in st.session_state.history if h.get("manual_entry")]
    if manual_history:
        st.caption(f"{len(manual_history)} manually logged bets")
        manual_df = pd.DataFrame(manual_history[-20:])
        show_cols_m = [c for c in ["timestamp", "player", "prop", "line", "side", "sport", "outcome", "wager", "net", "source"] if c in manual_df.columns]
        st.dataframe(manual_df[show_cols_m].iloc[::-1], width="stretch", hide_index=True)
    else:
        st.caption("No manual entries yet.")

# ----- TAB 6: LINE SHOP -----
with tabs[7]:
    st.markdown("## \U0001f6d2 Line Shopping")
    board_ls = st.session_state.board_data
    ud_props_ls = st.session_state.get("ud_props_compare", [])
    ow_props_ls = st.session_state.get("oddswrap_props", [])
    if not board_ls:
        st.info("Load the board first.")
    else:
        ud_dict_ls = {}
        for p in ud_props_ls:
            k = normalize_name(p["Player"])
            if k not in ud_dict_ls:
                ud_dict_ls[k] = {}
            ud_dict_ls[k][p["Prop"]] = p["Line"]
        rows_ls = []
        for prop in board_ls[:20]:
            player_ls, pn_ls, pp_line_ls, side_ls = prop["Player"], prop["Prop"], prop["Line"], prop["Side"]
            norm_ls = normalize_name(player_ls)
            ud_line_ls = ud_dict_ls.get(norm_ls, {}).get(pn_ls)
            all_lines_ls = {"PrizePicks": pp_line_ls}
            if ud_line_ls:
                all_lines_ls["Underdog"] = ud_line_ls
            best_book_ls = (min(all_lines_ls, key=all_lines_ls.get) if side_ls == "OVER" else max(all_lines_ls, key=all_lines_ls.get))
            best_line_ls = all_lines_ls[best_book_ls]
            rows_ls.append({"Player": player_ls, "Prop": pn_ls, "Side": side_ls, "PrizePicks": pp_line_ls, "Underdog": ud_line_ls if ud_line_ls else "\u2014", "Best Line": best_line_ls, "Best Book": best_book_ls, "Saves": round(abs(best_line_ls - pp_line_ls), 1) if best_line_ls != pp_line_ls else 0, "Tier": prop.get("Tier", "\u2014")})
        st.dataframe(pd.DataFrame(rows_ls), width="stretch")
        best_opps_ls = [r for r in rows_ls if r["Best Book"] != "PrizePicks" and r["Saves"] >= 0.5]
        if best_opps_ls:
            st.markdown("### \U0001f525 Better Lines Available")
            st.dataframe(pd.DataFrame(best_opps_ls)[["Player","Prop","PrizePicks","Best Line","Best Book","Saves","Tier"]], width="stretch")
    disc_ls = st.session_state.get("multibook_discrepancies", [])
    if disc_ls:
        st.markdown("### \U0001f4ca Cross-Book Discrepancies")
        st.dataframe(pd.DataFrame(disc_ls[:10]), width="stretch")

# ----- TAB 7: SYSTEM -----
with tabs[8]:
    st.markdown("## \u2699\ufe0f System Info")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Configuration**")
        st.write(f"Bankroll: ${st.session_state.bankroll:.2f}")
        st.write(f"Min Edge: {st.session_state.min_edge*100:.0f}%")
        st.write(f"Skip unknown players: {st.session_state.skip_defaults}")
        st.write(f"Kelly fraction: {KELLY_FRACTION}")
    with c2:
        st.markdown("**Session Stats**")
        st.write(f"Active locks: {len(st.session_state.locks)}")
        st.write(f"History entries: {len(st.session_state.history)}")
        st.write(f"Props loaded: {len(st.session_state.board_data)}")
        st.write(f"Session time: {get_session_time()}")
    st.markdown("---")
    st.markdown("### \U0001f6e1\ufe0f Daily Risk Controls")
    st.write(f"Max locks/day: {DAILY_RISK_CONTROLS['max_locks_per_day']}")
    st.write(f"Stop-loss: -{DAILY_RISK_CONTROLS['max_daily_loss_pct']:.0%}")
    st.write(f"Stop-win: +{DAILY_RISK_CONTROLS['stop_win_pct']:.0%}")
    can_bet_s, risk_msg_s = check_daily_risk_limits()
    if can_bet_s:
        st.success("\u2705 All risk controls green")
    else:
        st.error(f"\U0001f6d1 {risk_msg_s}")
    st.markdown("---")
    st.markdown("### \u2696\ufe0f Signal Weights Status")
    weight_rows = []
    for sp in ["NBA","MLB","NHL","NFL","WNBA"]:
        weights_s, status_s, weight_type_s = get_active_weights(sp)
        optimizer_data_s = load_json_data(WEIGHT_OPTIMIZER_PATH, {})
        sport_data_s = optimizer_data_s.get(sp, {})
        n_bets_s = sport_data_s.get("n_bets", 0)
        wr_s = sport_data_s.get("overall_win_rate", 0)
        weight_rows.append({"Sport": sp, "Status": status_s, "Base": f"{weights_s.get('base',0):.0%}", "Defense": f"{weights_s.get('defense',0):.0%}", "Location": f"{weights_s.get('location',0):.0%}", "Rest": f"{weights_s.get('rest',0):.0%}", "Pace": f"{weights_s.get('pace',0):.0%}", "Bets": n_bets_s, "Win Rate": f"{wr_s:.1%}" if wr_s > 0 else "\u2014", "Type": weight_type_s})
    st.dataframe(pd.DataFrame(weight_rows), width="stretch", hide_index=True)
    if st.button("Force Recalculate Weights"):
        for sp in ["NBA","MLB","NHL","NFL","WNBA"]:
            compute_optimized_weights(sp)
        st.success("Weights recalculated")
        st.rerun()
    st.markdown("---")
    st.markdown("### \U0001f4ca SEM Calibration")
    tier_stats_s = compute_tier_stats(st.session_state.history)
    if tier_stats_s:
        sem_df = pd.DataFrame([{"Tier": tier, "Bets": s["n"], "Hit Rate": f"{s['hit_rate']:.1%}", "Predicted": f"{s['avg_predicted']:.1%}", "SEM": f"\u00b1{s['sem']:.3f}" if s['sem'] else "\u2014"} for tier, s in tier_stats_s.items()])
        st.dataframe(sem_df, width="stretch")
    else:
        st.info("No calibration data yet.")
    st.markdown("---")
    st.markdown("### \U0001f50d Error Log")
    errors_s = st.session_state.get("errors", [])
    if errors_s:
        for err in errors_s[-5:]:
            st.error(f"[{err.get('time','')}] {err.get('source','')}: {err.get('error','')}")
        if st.button("Clear Error Log"):
            st.session_state["errors"] = []
            st.rerun()
    else:
        st.caption("\u2705 No errors this session.")
    st.markdown("---")
    st.markdown("---")
    st.markdown("### 📡 API Control Panel")
    st.caption("Live status of every data source. Hit Refresh to ping all APIs.")

    # --- Ping definitions ---
    _PP_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://app.prizepicks.com/",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://app.prizepicks.com",
    }
    _PING_SOURCES = [
        {
            "name": "PrizePicks",
            "description": "Primary prop source",
            "url": "https://api.prizepicks.com/projections?league_id=7&per_page=10&single_stat=true&in_game=true&state_code=CA&game_mode=prizepools",
            "headers": _PP_HEADERS,
            "budget_key": None,
            "count_key": None,
            "is_prop_source": True,
        },
        {
            "name": "Underdog Fantasy",
            "description": "Via ParlayAPI aggregator",
            "url": f"https://api.underdogfantasy.com/v1/lobbies/content/lines?include_live=true&product=fantasy&product_experience_id=018e1234-5678-9abc-def0-123456789006&show_mass_option_markets=false&sport_id=NBA&state_config_id=725014ef-3570-4e93-871d-d69674ab3521",
            "headers": {"Origin": "https://underdogfantasy.com", "Referer": "https://underdogfantasy.com/pick-em", "User-Agent": "Mozilla/5.0"},
            "budget_key": None,
            "count_key": None,
            "is_prop_source": True,
        },
        {
            "name": "ParlayPlay",
            "description": "Via ParlayAPI aggregator (bot-free)",
            "url": f"https://parlay-api.com/v1/sports/basketball_nba/props?bookmakers=parlayplay&dfsOdds=midpoint",
            "headers": {"X-API-Key": st.secrets.get("PARLAY_API_KEY", "")},
            "budget_key": "PARLAYPLAY",
            "count_key": "PARLAY_API_KEY",
            "is_prop_source": True,
        },
        {
            "name": "Action Network",
            "description": "Public betting % + projections",
            "url": "https://api.actionnetwork.com/web/v2/leagues/4/projections/available?limit=10",
            "headers": {"Origin": "https://www.actionnetwork.com", "Referer": "https://www.actionnetwork.com/"},
            "budget_key": "ACTION_NETWORK",
            "count_key": None,
            "is_prop_source": False,
        },
        {
            "name": "DraftKings DFS",
            "description": "Player salaries + value scores",
            "url": "https://www.draftkings.com/lobby/getcontests?sport=NBA",
            "headers": {"Referer": "https://www.draftkings.com/"},
            "budget_key": None,
            "count_key": None,
            "is_prop_source": False,
        },
        {
            "name": "BallsDontLie",
            "description": "Player averages + stats",
            "url": "https://api.balldontlie.io/v1/players?per_page=1",
            "headers": {"Authorization": st.secrets.get("BALLSDONTLIE_API_KEY", "")},
            "budget_key": "BDL",
            "count_key": "BALLSDONTLIE_API_KEY",
            "is_prop_source": False,
        },
        {
            "name": "ParlayAPI",
            "description": "ParlayPlay + Underdog + arb scanner",
            "url": f"https://api.underdogfantasy.com/v1/lobbies/content/lines?include_live=true&product=fantasy&product_experience_id=018e1234-5678-9abc-def0-123456789006&show_mass_option_markets=false&sport_id=NBA&state_config_id=725014ef-3570-4e93-871d-d69674ab3521",
            "headers": {"X-API-Key": st.secrets.get("PARLAY_API_KEY", "")},
            "budget_key": None,
            "count_key": "PARLAY_API_KEY",
            "is_prop_source": False,
        },
        {
            "name": "OddsPAPI",
            "description": "Props fallback odds",
            "url": "https://api.oddspapi.io/v4/sports?apiKey=" + st.secrets.get("ODDSPAPI_KEY", ""),
            "headers": {},
            "budget_key": "ODDSPAPI",
            "count_key": "ODDSPAPI_KEY",
            "is_prop_source": False,
        },
        {
            "name": "ESPN",
            "description": "Game schedules + scores",
            "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            "headers": {},
            "budget_key": "ESPN",
            "count_key": None,
            "is_prop_source": False,
        },
        {
            "name": "OddsAPI",
            "description": "Closing lines + CLV",
            "url": "https://api.the-odds-api.com/v4/sports?apiKey=" + st.secrets.get("ODDS_API_KEY", "demo"),
            "headers": {},
            "budget_key": "ODDS_API",
            "count_key": "ODDS_API_KEY",
            "is_prop_source": False,
        },
    ]

    def _ping_url(url, headers, timeout=8):
        """Returns (status_code, detail_str, color) — color: green/yellow/red."""
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            code = r.status_code
            if code == 200:
                return code, "✅ 200 OK — Responding normally", "green"
            elif code == 403:
                return code, "🔒 403 Forbidden — Blocked. Board will use fallback sources.", "red"
            elif code == 429:
                return code, "🚫 429 Rate Limited — Too many requests. Wait 15–30 min.", "yellow"
            elif code == 401:
                return code, "🔑 401 Unauthorized — API key missing or invalid.", "red"
            elif code == 404:
                return code, "❓ 404 Not Found — Endpoint may have changed.", "yellow"
            elif code >= 500:
                return code, f"💥 {code} Server Error — API is down on their end.", "red"
            else:
                return code, f"⚠️ {code} — Unexpected response.", "yellow"
        except requests.exceptions.Timeout:
            return None, "⏱️ Timeout — No response within 8s. API may be down.", "red"
        except requests.exceptions.ConnectionError:
            return None, "❌ Connection Error — Unreachable. Check if site is down.", "red"
        except Exception as ex:
            return None, f"❌ Error — {str(ex)[:60]}", "red"

    _COLOR_CSS = {
        "green":  "border-left: 4px solid #00c87a; background: rgba(0,200,122,0.07);",
        "yellow": "border-left: 4px solid #f0a500; background: rgba(240,165,0,0.07);",
        "red":    "border-left: 4px solid #e04040; background: rgba(224,64,64,0.07);",
    }
    _DOT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

    # Store ping results in session state so they persist until refresh
    if "api_panel_results" not in st.session_state:
        st.session_state["api_panel_results"] = {}

    col_refresh, col_reset = st.columns([2, 2])
    do_refresh = col_refresh.button("🔄 Refresh All", key="api_panel_refresh")
    do_reset   = col_reset.button("🗑️ Reset API Counters", key="api_panel_reset_counters")

    if do_reset:
        for key_s, budget_s in API_BUDGETS.items():
            path_s = budget_s["counter_path"]
            if os.path.exists(path_s):
                os.remove(path_s)
        st.success("✅ All API counters reset")

    if do_refresh or not st.session_state["api_panel_results"]:
        with st.spinner("Pinging all sources..."):
            results = {}
            for src in _PING_SOURCES:
                # Use curl_cffi for ParlayPlay to bypass bot protection
                code, detail, color = _ping_url(src["url"], src["headers"])
                # For prop sources returning JSON, try to count items
                extra = ""
                if color == "green" and src.get("is_prop_source"):
                    try:
                        r2 = requests.get(src["url"], headers=src["headers"], timeout=8)
                        d2 = r2.json()
                        n = len(d2.get("data", d2.get("over_under_lines", d2.get("projections", []))))
                        if n > 0:
                            extra = f" — {n} props returned"
                            detail = f"✅ 200 OK — Responding normally{extra}"
                        elif n == 0:
                            detail = "⚠️ 200 OK — Connected but 0 props. No slate posted yet."
                            color = "yellow"
                    except Exception:
                        pass
                results[src["name"]] = (code, detail, color)
            st.session_state["api_panel_results"] = results

    results = st.session_state.get("api_panel_results", {})

    # Auto-diagnosis summary
    if results:
        red_sources = [n for n, (c, d, col) in results.items() if col == "red"]
        yellow_sources = [n for n, (c, d, col) in results.items() if col == "yellow"]
        green_sources = [n for n, (c, d, col) in results.items() if col == "green"]

        if red_sources or yellow_sources:
            with st.expander("🔧 Auto-Diagnosis — What these errors mean and what to do", expanded=True):
                fixes = {
                    "ParlayPlay": {
                        "403": "ParlayPlay session cookie is missing or expired. Add PARLAYPLAY_SESSION to Streamlit Secrets. Get it from Chrome DevTools → parlayplay.io → Application → Cookies → sessionid value. Expires every ~2 weeks.",
                        "fix": "Add or refresh PARLAYPLAY_SESSION in Streamlit Secrets."
                    },
                    "Underdog Fantasy": {
                        "400": "Underdog changed their API format. This is a fallback source only — your board works fine without it.",
                        "fix": "No action needed. Used only for line comparison in Line Shop."
                    },
                    "OddsPAPI": {
                        "400": "Tournament ID lookup returned unexpected format. Try clearing cache and refreshing.",
                        "401": "API key is invalid or expired. Go to oddspapi.io/dashboard, regenerate your key, and update Streamlit Secrets.",
                        "fix": "Update ODDSPAPI_KEY in Streamlit Secrets."
                    },
                    "BallsDontLie": {
                        "401": "API key missing or expired. Go to balldontlie.io, check your key, update BALLSDONTLIE_API_KEY in Streamlit Secrets.",
                        "fix": "Update BALLSDONTLIE_API_KEY in Streamlit Secrets."
                    },
                    "PrizePicks": {
                        "200": "PrizePicks is responding but props may be cached from an earlier empty response. Click 'Clear PrizePicks Cache' below, then load the board again.",
                        "403": "PrizePicks is temporarily blocking requests. Wait 10 minutes and reload the board.",
                        "429": "PrizePicks rate limited — too many requests. Wait 15-30 minutes then try again.",
                        "fix": "Clear PrizePicks cache in System tab, then reload the board."
                    },
                }
                if green_sources:
                    st.success(f"✅ {len(green_sources)} sources working: {', '.join(green_sources)}")
                for name_err in red_sources + yellow_sources:
                    src_fix = fixes.get(name_err, {})
                    result_code, result_detail, result_color = results.get(name_err, (None, "", "yellow"))
                    code_str = str(result_code) if result_code else ""
                    explanation = src_fix.get(code_str, f"{name_err} is not responding correctly.")
                    fix_action = src_fix.get("fix", "Check the source's website and verify your API key.")
                    icon = "🔴" if result_color == "red" else "🟡"
                    st.markdown(f"""
<div style="background:#0d1520;border:1px solid {'#e04040' if result_color == 'red' else '#e8a020'};border-radius:8px;padding:12px 16px;margin-bottom:8px;">
  <div style="font-size:13px;font-weight:500;color:#e8f0f8;margin-bottom:4px;">{icon} {name_err} — Code {result_code}</div>
  <div style="font-size:12px;color:#9aa8b8;margin-bottom:6px;">{explanation}</div>
  <div style="font-size:11px;color:#0ea5a0;">→ {fix_action}</div>
</div>""", unsafe_allow_html=True)

    if results:
        for src in _PING_SOURCES:
            name = src["name"]
            desc = src["description"]
            code, detail, color = results.get(name, (None, "Not checked yet", "yellow"))

            # Key status
            key_label = src.get("count_key")
            if key_label:
                has_key = bool(st.secrets.get(key_label, ""))
                key_str = "🟢 Key set" if has_key else "🔴 Key missing"
            else:
                key_str = "🟢 No key needed"

            # Usage + gate
            bkey = src.get("budget_key")
            if bkey and bkey in API_BUDGETS:
                usage_str = api_budget_status(bkey)
                allowed_b, _ = api_budget_check(bkey)
                gate_str = "✅ Open" if allowed_b else "🛑 Blocked"
            else:
                usage_str = "—"
                gate_str  = "✅ Open"

            dot = _DOT.get(color, "🟡")
            css = _COLOR_CSS.get(color, "")

            st.markdown(f"""
<div style="padding:12px 16px; margin-bottom:10px; border-radius:8px; {css}">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <div>
      <span style="font-size:15px; font-weight:700; color:#e8f0f8;">{dot} {name}</span>
      <span style="font-size:12px; color:#8899aa; margin-left:10px;">{desc}</span>
    </div>
    <span style="font-size:12px; color:#aabbcc;">Code: {code if code else "—"}</span>
  </div>
  <div style="margin-top:6px; font-size:13px; color:#ccd8e8;">{detail}</div>
  <div style="margin-top:8px; display:flex; gap:24px; font-size:12px; color:#8899aa;">
    <span><b>Key:</b> {key_str}</span>
    <span><b>Usage:</b> {usage_str}</span>
    <span><b>Gate:</b> {gate_str}</span>
  </div>
</div>
""", unsafe_allow_html=True)
    else:
        st.info("Hit **🔄 Refresh All** to check all API sources.")
    st.markdown("---")
    st.markdown("**\U0001f4be Data Persistence Status**")
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        st.success("\u2705 GitHub Gist persistence active")
    else:
        st.error("\u26a0\ufe0f No persistence configured")
    st.markdown("---")
    st.markdown("**Cache Management**")
    cache_cols_s = st.columns(3)
    with cache_cols_s[0]:
        if st.button("Clear NBA Cache"):
            for f in ["nba_rolling_avgs.pkl", "nba_team_defense.pkl"]:
                p = os.path.join(CACHE_DIR, f)
                if os.path.exists(p):
                    os.remove(p)
            st.success("NBA cache cleared")

    st.markdown("---")
    st.markdown("**PrizePicks Cache**")
    col_pp1, col_pp2 = st.columns(2)
    with col_pp1:
        if st.button("🧹 Clear PrizePicks Cache", key="clear_pp_cache"):
            cleared = 0
            for f in os.listdir(CACHE_DIR):
                if f.endswith("_pp.pkl"):
                    os.remove(os.path.join(CACHE_DIR, f))
                    cleared += 1
            st.success(f"✅ Cleared {cleared} PrizePicks cache files — reload the board now")
    with col_pp2:
        pp_cache_files = [f for f in os.listdir(CACHE_DIR) if f.endswith("_pp.pkl")]
        pp_cache_age = 0
        if pp_cache_files:
            oldest = min(os.path.getmtime(os.path.join(CACHE_DIR, f)) for f in pp_cache_files)
            pp_cache_age = int((time.time() - oldest) / 60)
        st.caption(f"Cache files: {len(pp_cache_files)} | Oldest: {pp_cache_age}m ago")
    with cache_cols_s[1]:
        if st.button("Clear All Rolling Caches"):
            for f in os.listdir(CACHE_DIR):
                if f.endswith("_rolling_avgs.pkl") or f.endswith("_team_defense.pkl"):
                    os.remove(os.path.join(CACHE_DIR, f))
            st.success("All rolling caches cleared")
    with cache_cols_s[2]:
        if st.button("Clear All API Counters"):
            for budget_c in API_BUDGETS.values():
                path_c = budget_c["counter_path"]
                if os.path.exists(path_c):
                    os.remove(path_c)
            st.success("API counters reset")
    st.markdown("---")
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("\U0001f504 Reset Session State"):
        keep = ["bankroll","history","locks","persistence_loaded","day_start_br","session_start"]
        for k in list(st.session_state.keys()):
            if k not in keep:
                del st.session_state[k]
        st.success("Session reset")
        st.rerun()
    if col_s2.button("\U0001f9f9 Clean Old Cache Files"):
        cleaned = 0
        cutoff = time.time() - (7*24*3600)
        keep_files = ["history.json","locks.json","bankroll.json","calibration.json","line_movement.json","clv_tracking.json"]
        for f in os.listdir(CACHE_DIR):
            fp = os.path.join(CACHE_DIR, f)
            if os.path.isfile(fp) and f not in keep_files and os.path.getmtime(fp) < cutoff:
                os.remove(fp)
                cleaned += 1
        st.success(f"Cleaned {cleaned} old files")


