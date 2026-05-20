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
LINE_MOVEMENT_PATH = os.path.join(CACHE_DIR, "line_movement.json")
SHARP_PATH = os.path.join(CACHE_DIR, "sharp_flags.json")

# API counter paths
API_SPORTS_COUNTER_PATH = os.path.join(CACHE_DIR, "api_sports_counter.json")
SPORTMONKS_COUNTER_PATH = os.path.join(CACHE_DIR, "sportmonks_counter.json")
UNIFIED_COUNTER_PATH = os.path.join(CACHE_DIR, "unified_counter.json")
ODDS_API_COUNTER_PATH = os.path.join(CACHE_DIR, "odds_api_counter.json")
BDL_COUNTER_PATH = os.path.join(CACHE_DIR, "bdl_counter.json")

# GitHub Gist persistence
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_GIST_ID = st.secrets.get("GITHUB_GIST_ID", "")
GIST_API = "https://api.github.com/gists"
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")

# OddsPapi constants
ODDSPAPI_KEY = st.secrets.get("ODDSPAPI_KEY", "")
ODDSPAPI_COUNTER_PATH = os.path.join(CACHE_DIR, "oddspapi_counter.json")
ODDSPAPI_FREE_TIER_DAILY_LIMIT = 100
ODDSPAPI_FREE_TIER_MONTHLY_LIMIT = 1000

# ParlayPlay constants
PARLAYPLAY_COUNTER_PATH = os.path.join(CACHE_DIR, "parlayplay_counter.json")
PARLAYPLAY_DAILY_LIMIT = 200

# BDL Props constants
BDL_PROPS_COUNTER_PATH = os.path.join(CACHE_DIR, "bdl_props_counter.json")
BDL_PROPS_DAILY_LIMIT = 60

# Unified API budgets — shared across all functions using the same key
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
        "description": "ParlayPlay NBA props",
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
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
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
# DISPLAY UTILITY
# =========================
def make_display_df(enriched_list):
    if not enriched_list:
        return pd.DataFrame()
    df = pd.DataFrame(enriched_list)
    rename_map = {
        "Player": "Player", "Prop": "Stat", "Line": "Line", "Side": "Play",
        "Avg": "Avg (10g)", "Prob": "Fair %", "EdgePct": "Edge",
        "EV_2pick": "2-Pick EV", "EV_3pick": "3-Pick EV",
        "Wager_2pick": "Bet Size", "Tier": "Tier", "SharpFlag": "Sharp $",
        "Efficiency": "Market", "SEM": "Confidence", "Injury": "Injury",
        "Movement": "Line Move", "source": "Source", "Trend": "Trend",
        "Pitcher": "vs Pitcher", "RefNote": "Ref", "SampleSize": "Games",
        "LockScore": "Lock Score",
    }
    display_df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    if "Fair %" in display_df.columns:
        display_df["Fair %"] = display_df["Fair %"].apply(lambda x: f"{x:.1%}" if isinstance(x, float) else x)
    if "Avg (10g)" in display_df.columns:
        display_df["Avg (10g)"] = display_df["Avg (10g)"].apply(lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x)
    return display_df

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
    """
    Centralized budget guardian.
    Returns (allowed, reason_string)
    Call before every external API request.
    """
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
            return False, (
                f"{budget_key} daily limit "
                f"approached: {daily_used}/"
                f"{daily_limit} — protecting free tier"
            )
    
    monthly_limit = budget.get("monthly_limit")
    if monthly_limit:
        threshold = int(monthly_limit * stop_pct)
        if monthly_used >= threshold:
            return False, (
                f"{budget_key} monthly limit "
                f"approached: {monthly_used}/"
                f"{monthly_limit} — protecting free tier"
            )
    
    return True, ""

def api_budget_increment(budget_key):
    """Increment unified counter after every API call."""
    budget = API_BUDGETS.get(budget_key)
    if budget:
        increment_api_counter(budget["counter_path"])

def api_budget_status(budget_key):
    """Returns current usage as display string."""
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
        color = (
            "🔴" if pct >= 80
            else "🟡" if pct >= 60
            else "🟢"
        )
        parts.append(f"{color} {daily_used}/{daily_limit} today")
    
    if monthly_limit:
        pct = monthly_used / monthly_limit * 100
        color = (
            "🔴" if pct >= 80
            else "🟡" if pct >= 60
            else "🟢"
        )
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
        result[tier] = {"n": n, "hit_rate": round(hit_rate, 3), "avg_predicted": round(avg_predicted, 3),
                        "sem": round(sem, 3) if sem else None, "calibration_error": round(calibration_error, 3)}
    return result

def compute_sem_for_tier(tier_stats, tier):
    if tier not in tier_stats:
        return "—", 0
    stats = tier_stats[tier]
    n = stats["n"]
    if n < 5:
        return "—", n
    sem = stats["sem"]
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
    if edge >= thresholds["ELITE"]:     return "ELITE"
    if edge >= thresholds["APPROVED"]:  return "APPROVED"
    if edge >= thresholds["LEAN"]:      return "LEAN"
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

def fetch_team_recent_defense(sport, team_abbrev, n_games=5):
    cache_key = f"recent_def_{sport}_{team_abbrev}_{n_games}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 12:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    if sport != "NBA":
        return None
    nba_headers = {"Host": "stats.nba.com", "User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*",
                   "x-nba-stats-origin": "stats", "x-nba-stats-token": "true", "Referer": "https://www.nba.com/"}
    url = f"https://stats.nba.com/stats/teamgamelogs?Season=2024-25&SeasonType=Playoffs&TeamID=&LastNGames={n_games}&MeasureType=Defense&PerMode=PerGame"
    try:
        resp = requests.get(url, headers=nba_headers, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        result_set = data.get("resultSets", [{}])[0]
        headers = result_set.get("headers", [])
        rows = result_set.get("rowSet", [])
        if not headers or not rows:
            return None
        col = {h: i for i, h in enumerate(headers)}
        for row in rows:
            abbrev = row[col.get("TEAM_ABBREVIATION", 0)]
            if abbrev == team_abbrev:
                def_rtg = row[col.get("DEF_RATING", 0)]
                result = {"def_rating_recent": def_rtg}
                with open(cache_path, "wb") as f:
                    pickle.dump(result, f)
                return result
    except:
        pass
    return None

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
                    recommendations.append({"type": "SPREAD", "pick": rec_text, "edge": spread_edge_pct, "edge_pct": f"{spread_edge_pct:.1%}", "tier": tier,
                                            "power_diff": round(power_diff, 1), "market_spread": market_spread, "divergence": round(spread_edge, 1),
                                            "note": f"Power rating diff {power_diff:.1f} vs market spread {market_spread:.1f} — divergence {spread_edge:.1f} pts"})
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
                    recommendations.append({"type": "TOTAL", "pick": f"{side} {total_val}", "edge": total_edge_pct, "edge_pct": f"{total_edge_pct:.1%}", "tier": tier,
                                            "fair_total": round(fair_total, 1), "market_total": total_val, "divergence": round(total_edge, 1),
                                            "note": f"Model projects {fair_total:.1f} vs market {total_val} — {side} value"})
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
                    recommendations.append({"type": "MONEYLINE", "pick": ml_pick, "edge": ml_edge, "edge_pct": f"{ml_edge:.1%}", "ev": round(ev, 3), "tier": tier,
                                            "fair_prob": round(fair_prob, 3), "note": f"Fair probability {fair_prob:.1%} vs implied — +EV at these odds"})
                    if ml_edge > best_edge:
                        best_edge = ml_edge
                        best_bet = recommendations[-1]
    except:
        pass
    return {"matchup": matchup, "home": home_team, "away": away_team,
            "recommendations": recommendations, "best_bet": best_bet, "best_edge": best_edge, "sport": sport}

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
                    rolling[player_name] = {
                        "PTS": round(float(pts), 1),
                        "REB": round(float(reb), 1),
                        "AST": round(float(ast), 1),
                        "PRA": round(float(pts) + float(reb) + float(ast), 1),
                        "MIN": minutes,
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
                    rolling[name] = {
                        "PTS": round(float(pts), 1),
                        "REB": round(float(reb), 1),
                        "AST": round(float(ast), 1),
                        "PRA": round(float(pts)+float(reb)+float(ast), 1),
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
                rolling[player_name] = {
                    "SO": ewma_average([g["stat"].get("strikeOuts",0) for g in last10], sport="MLB"),
                    "ER": ewma_average([g["stat"].get("earnedRuns",0) for g in last10], sport="MLB"),
                    "H": ewma_average([g["stat"].get("hits",0) for g in last10], sport="MLB"),
                    "n_games": len(last10)
                }
            else:
                rolling[player_name] = {
                    "H": ewma_average([g["stat"].get("hits",0) for g in last10], sport="MLB"),
                    "HR": ewma_average([g["stat"].get("homeRuns",0) for g in last10], sport="MLB"),
                    "RBI": ewma_average([g["stat"].get("rbi",0) for g in last10], sport="MLB"),
                    "R": ewma_average([g["stat"].get("runs",0) for g in last10], sport="MLB"),
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
            rolling[player_name] = {
                "PTS": ewma_average([g.get("points",0) for g in last10], sport="NHL"),
                "GOALS": ewma_average([g.get("goals",0) for g in last10], sport="NHL"),
                "ASSISTS": ewma_average([g.get("assists",0) for g in last10], sport="NHL"),
                "SOG": ewma_average([g.get("shots",0) for g in last10], sport="NHL"),
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
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_nba_averages_bdl",
            "error": reason
        })
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
    url = f"https://api.underdogfantasy.com/v2/over_under_lines?sport_id={sport_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
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
    urls = [
        f"https://partner-api.prizepicks.com/projections?per_page=1000&league_id={league}",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&state_code=CA",
    ]
    pp_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://app.prizepicks.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://app.prizepicks.com",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "X-Device-ID": "betcouncil-app-v4",
        "Cache-Control": "no-cache",
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
                    data = resp.json()
                    if data and data.get("data"):
                        with open(cache_path, "wb") as f:
                            pickle.dump(data, f)
                elif resp.status_code == 429:
                    time.sleep(2)
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
    return today_games, playoff, home_teams, away_teams

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

def fetch_parlayplay_props(sport):
    """
    ParlayPlay public endpoint — NBA only.
    No API key required.
    Community-discovered endpoint, may change.
    """
    if sport != "NBA":
        return []
    
    allowed, reason = api_budget_check("PARLAYPLAY")
    if not allowed:
        return []
    
    cache_path = os.path.join(CACHE_DIR, "parlayplay_nba.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached
    
    url = (
        "https://parlayplay.io/api/v1/crossgame/search/"
        "?sport=Basketball&league=NBA"
        "&includeAlt=true&version=2&includeBoost=true"
    )
    
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        api_budget_increment("PARLAYPLAY")
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        props = []
        seen = set()
        
        for game in data.get("games", []):
            for prop in game.get("props", []):
                player_name = prop.get("player", {}).get("name", "")
                stat_type = prop.get("stat", {}).get("name", "")
                line = prop.get("line", 0)
                
                if not player_name or not stat_type:
                    continue
                if not line:
                    continue
                
                key = (player_name, stat_type, float(line))
                if key in seen:
                    continue
                seen.add(key)
                
                props.append({
                    "Player": player_name,
                    "Prop": stat_type,
                    "Line": float(line),
                    "Side": "OVER",
                    "Sport": sport,
                    "source": "ParlayPlay",
                    "OddsType": "standard"
                })
        
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
        
        return props[:100]
        
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_parlayplay_props",
            "error": str(e)[:100]
        })
        return []

def fetch_bdl_props(sport):
    """
    BallDontLie player props endpoint.
    Uses existing BDL API key — no new key needed.
    Returns NBA player props from DraftKings
    in same format as PrizePicks.
    Only fires when PrizePicks + Underdog fail.
    """
    if sport != "NBA":
        return []
    
    if not BDL_API_KEY:
        return []
    
    allowed, reason = api_budget_check("BDL")
    if not allowed:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_bdl_props",
            "error": reason
        })
        return []
    
    daily_used = get_api_counter(API_BUDGETS["BDL"]["counter_path"]).get("count", 0)
    
    # 60 minute cache
    cache_path = os.path.join(CACHE_DIR, "bdl_props_nba.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 BDL Props: using cached data ({age_mins:.0f}m old)")
                return cached
    
    # Step 1 — get today's game IDs
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
        
        # Step 2 — get props for each game
        all_props = []
        seen = set()
        
        stat_map = {
            "points": "Points",
            "rebounds": "Rebounds",
            "assists": "Assists",
            "pts_reb_ast": "Pts+Reb+Ast",
            "steals": "Steals",
            "blocks": "Blocked Shots",
            "three_pointers_made": "3-PT Made",
            "turnovers": "Turnovers",
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
            st.caption(f"✅ BDL Props: {len(all_props)} props fetched ({daily_used + 1}/{BDL_PROPS_DAILY_LIMIT} calls today)")
        
        return all_props
        
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_bdl_props",
            "error": str(e)[:100]
        })
        return []

def fetch_oddspapi_props(sport):
    """
    OddsPapi fallback — only called when
    PrizePicks AND Underdog both fail.
    
    Free tier protection:
    - 90 minute cache per sport
    - Daily call counter with hard stop
    - Single batched request per call
    - Never called as primary source
    """
    if not ODDSPAPI_KEY:
        return []
    
    allowed, reason = api_budget_check("ODDSPAPI")
    if not allowed:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_oddspapi_props",
            "error": reason
        })
        return []
    
    daily_used = get_api_counter(API_BUDGETS["ODDSPAPI"]["counter_path"]).get("count", 0)
    
    # 90 minute cache — aggressive to save calls
    cache_path = os.path.join(CACHE_DIR, f"oddspapi_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 OddsPapi: using cached data ({age_mins:.0f}m old)")
                return cached
    
    sport_map = {
        "NBA": "basketball_nba",
        "MLB": "baseball_mlb",
        "NHL": "icehockey_nhl",
        "NFL": "americanfootball_nfl",
        "WNBA": "basketball_wnba",
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    
    # Single batched call — most efficient
    # Gets all bookmakers in one request
    url = (
        f"https://api.oddspapi.io/v1/odds"
        f"?apikey={ODDSPAPI_KEY}"
        f"&sport={sport_key}"
        f"&markets=player_props"
        f"&bookmakers=draftkings,fanduel,"
        f"betmgm,bovada,caesars,pinnacle"
    )
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        
        # Count this call regardless of result
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
                        
                        # Only keep OVER for consistency with our model
                        if side.upper() != "OVER":
                            continue
                        
                        # Normalize stat name
                        stat_clean = (
                            market_key
                            .replace("player_", "")
                            .replace("_", " ")
                            .title()
                        )
                        
                        # Deduplicate across books
                        # Keep first occurrence (DraftKings priority)
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
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_oddspapi_props",
            "error": str(e)[:100]
        })
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
    checks = {"NBA Rolling Averages": "nba_rolling_avgs.pkl", "NBA Team Defense": "nba_team_defense.pkl", "WNBA Rolling Averages": "wnba_rolling_avgs.pkl", "MLB Rolling Averages": "mlb_rolling_avgs.pkl", "NHL Rolling Averages": "nhl_rolling_avgs.pkl", "BDL Season Averages": "bdl_nba_avgs.pkl"}
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

def compute_multi_signal_edge(line, player_avg, opp_def_rating, is_home, teammate_out_boost, side="OVER", stat_key="PTS", pace_adj=0.0, days_rest=2, odds_type="standard", sport="NBA"):
    if player_avg <= 0:
        return 0.0, 0.5, {}
    signals = {}
    league_avg_def = 112.0
    weights = SPORT_SIGNAL_WEIGHTS.get(sport, SPORT_SIGNAL_WEIGHTS["NBA"])
    if stat_key in ["HR", "GOALS"]:
        prob = poisson_prob_over(line, player_avg)
        if side.upper() == "UNDER":
            prob = 1 - prob
        base_edge = prob - 0.5
    else:
        diff = (line - player_avg) / player_avg
        base_edge = -diff if side.upper() == "OVER" else diff
        if player_avg > 0:
            pct_diff = abs(line - player_avg) / player_avg
            if pct_diff > 0.15:
                base_edge = base_edge * 0.70
    signals["base"] = base_edge
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
    prob = max(0.30, min(0.70, 0.5 + combined))
    return combined, prob, signals

def load_sport_data(sport):
    min_edge = st.session_state.min_edge
    skip_def = st.session_state.skip_defaults
    if sport in ["Golf", "Tennis"]:
        props = scrape_prizepicks(sport)
        if not props:
            return [], [], 0, 0, {}, {}
        enriched = []
        for p in props:
            enriched.append({"Player": p["Player"], "Prop": p["Prop"], "Line": p["Line"], "Side": "OVER", "Edge": 0, "EdgePct": "N/A", "Prob": 0.5, "Wager": 0, "Tier": "N/A", "Model": "N/A", "Sport": sport, "Avg": 0, "Injury": "", "SEM": "—", "SEM_n": 0, "SignalBase": 0, "SignalDefense": 0, "SignalLocation": 0, "SignalUsage": 0, "SignalRest": 0, "SignalPace": 0, "SignalBlowout": 0, "WeatherNote": "", "Movement": "", "Efficiency": "—", "EffScore": 0, "SharpFlag": "", "source": p.get("source",""), "OddsType": "standard"})
        st.info(f"⚠️ {sport}: Lines displayed only. No statistical baseline available — edge calculation not possible for this sport.")
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
    else:
        season_avgs = PLAYER_AVERAGES.get(sport, {})
    defaults = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])
    pp_props = scrape_prizepicks(sport)
    ud_props_compare = fetch_underdog_props(sport)
    oddswrap_props = fetch_oddswrap_props(sport)
    st.session_state["oddswrap_props"] = oddswrap_props
    st.session_state["ud_props_compare"] = ud_props_compare
    multibook_discrepancies = compare_multibook_lines(pp_props if pp_props else [], oddswrap_props)
    st.session_state["line_discrepancies"] = []
    st.session_state["multibook_discrepancies"] = multibook_discrepancies
    
    if pp_props:
        props = pp_props
    elif ud_props_compare:
        props = ud_props_compare
    elif oddswrap_props:
        props = [p for p in oddswrap_props if p["Side"] == "OVER"]
        st.info("Using DraftKings/Bovada props as primary source")
    else:
        # Fallback 4 — BDL Props (NBA only)
        if sport == "NBA" and BDL_API_KEY:
            st.info("Primary sources unavailable — trying BDL Props backup...")
            bdl_props = fetch_bdl_props(sport)
            if bdl_props:
                props = bdl_props
                st.success(f"✅ BDL Props backup active — {len(bdl_props)} props loaded")
            else:
                # Fallback 5 — ParlayPlay
                st.info("BDL unavailable — trying ParlayPlay...")
                parlayplay_props = fetch_parlayplay_props(sport)
                if parlayplay_props:
                    props = parlayplay_props
                    st.success(f"✅ ParlayPlay backup — {len(parlayplay_props)} props")
                else:
                    # Fallback 6 — OddsPapi
                    oddspapi_props = fetch_oddspapi_props(sport)
                    if oddspapi_props:
                        props = oddspapi_props
                        st.success(f"✅ OddsPapi backup — {len(oddspapi_props)} props")
                    else:
                        games, _, _, _ = fetch_game_lines(sport)
                        return [], games, 0, 0, {}, {}
        else:
            # Non-NBA or no BDL key
            parlayplay_props = fetch_parlayplay_props(sport)
            if parlayplay_props:
                props = parlayplay_props
                st.success(f"✅ ParlayPlay backup — {len(parlayplay_props)} props")
            else:
                oddspapi_props = fetch_oddspapi_props(sport)
                if oddspapi_props:
                    props = oddspapi_props
                    st.success(f"✅ OddsPapi backup — {len(oddspapi_props)} props")
                else:
                    games, _, _, _ = fetch_game_lines(sport)
                    return [], games, 0, 0, {}, {}
    
    injuries = fetch_injury_news(sport) if sport in ["NBA", "MLB", "NFL", "NHL"] else {}
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
                            recent_def = fetch_team_recent_defense(sport, p2, 5)
                            if recent_def and recent_def.get("def_rating_recent"):
                                opp_def_rating = round(recent_def["def_rating_recent"] * 0.6 + season_def * 0.4, 1)
                            else:
                                opp_def_rating = season_def
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
        over_edge, over_prob, over_signals = compute_multi_signal_edge(line, avg, opp_def_rating, is_home, usage_boost, "OVER", stat_norm, pace_adj, days_rest, odds_type, sport)
        over_edge = max(-EDGE_CAP, min(EDGE_CAP, over_edge + blowout_adj + weather_adj + game_total_adj + referee_adj + pitcher_adj))
        under_edge, under_prob, under_signals = compute_multi_signal_edge(line, avg, opp_def_rating, is_home, usage_boost, "UNDER", stat_norm, pace_adj, days_rest, odds_type, sport)
        under_edge = max(-EDGE_CAP, min(EDGE_CAP, under_edge - blowout_adj - weather_adj - game_total_adj - referee_adj - pitcher_adj))
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
        enriched.append({"Player": player, "Prop": stat_raw, "Line": line, "Side": best_side, "Avg": avg, "Edge": final_edge, "EdgePct": f"{final_edge:.1%}", "Prob": best_prob, "Wager": kelly_unit(best_prob, st.session_state.bankroll), "Tier": tier, "Quality": "Lookup" if not using_default else "Default", "Model": "MultiSignal", "Sport": sport, "Injury": injury_flag, "SEM": sem_display, "SEM_n": sem_n, "SignalBase": best_signals.get("base", 0), "SignalDefense": best_signals.get("defense", 0), "SignalLocation": best_signals.get("location", 0), "SignalUsage": best_signals.get("usage", 0), "SignalRest": best_signals.get("rest", 0), "SignalPace": best_signals.get("pace", 0), "SignalBlowout": blowout_adj, "WeatherNote": weather_note, "Movement": "", "Efficiency": eff_label, "EffScore": eff_score, "SharpFlag": sharp_flag, "source": p.get("source", ""), "EV_2pick": f"{ev_2pick:+.1%}", "EV_3pick": f"{ev_3pick:+.1%}", "Wager_2pick": wager_2pick, "Wager_3pick": wager_3pick, "PlusEV_2": ev_2pick > 0, "PlusEV_3": ev_3pick > 0, "OddsType": odds_type, "signals_active": signals_active, "Trend": recency_flag, "TrendDir": trend, "SampleSize": n_games if n_games else "—", "ConfidenceMult": round(sample_size_confidence(avg_dict.get("n_games"), sport), 2), "CLVAdj": clv_note, "RefNote": ref_note, "Pitcher": pitcher_name, "SearchNeeded": avg_dict.get("search_needed", False), "SearchQuery": avg_dict.get("search_query", "")})
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
       "power_divergences": {}, "quality_sorted_board": [], "last_pick_count": 2}
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
# SIDEBAR
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
# TABS
# =========================
tabs = st.tabs(["📋 Summary", "📊 Full Board", "🏟️ Game Lines", "🔒 Locks & Ledger", "📈 History", "🛒 Line Shop", "⚙️ System"])

# ----- TAB 0: SUMMARY -----
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
                        weather_data.append({"City": city, "Temp": f"{weather['temp_f']}°F", "Wind": f"{weather['wind_speed_mph']}mph {weather['wind_dir']}", "Humidity": f"{weather['humidity']}%", "Updated": weather["fetched_at"]})
        if weather_data:
            st.dataframe(pd.DataFrame(weather_data), width="stretch")
            st.caption("Weather affects HR and hits props at outdoor stadiums.")
        else:
            st.caption("Load MLB board to see weather conditions.")
        
        st.markdown("### ⚾ Tonight's Probable Pitchers")
        mlb_pitchers = st.session_state.get("mlb_pitchers", {})
        if mlb_pitchers:
            pitcher_rows = []
            for team, data in mlb_pitchers.items():
                pitcher = data.get("pitcher", "TBD")
                era = MLB_PITCHER_ERA.get(pitcher, None)
                difficulty = "🔴 Ace" if era and era < 3.20 else "🟡 Average" if era and era < 4.00 else "🟢 Hittable"
                pitcher_rows.append({"Team": team, "Pitcher": pitcher if pitcher else "TBD", "ERA": f"{era:.2f}" if era else "—", "Difficulty": difficulty})
            if pitcher_rows:
                st.dataframe(pd.DataFrame(pitcher_rows), width="stretch", hide_index=True)
        else:
            st.caption("Load MLB board to see pitchers.")
    
    if st.session_state.last_sport in ["NBA", "MLB"]:
        st.markdown("### 👮 Officials on Duty")
        officials = st.session_state.get("officials_data", {})
        if officials:
            off_rows = []
            for matchup, refs in officials.items():
                notable = []
                for ref in refs:
                    if st.session_state.last_sport == "NBA":
                        data = NBA_REFEREE_TENDENCIES.get(ref, {})
                    else:
                        data = MLB_UMPIRE_TENDENCIES.get(ref, {})
                    if data:
                        notable.append(f"⚠️ {ref}")
                off_rows.append({"Game": matchup, "Officials": ", ".join(refs[:3]), "Notable": (", ".join(notable) if notable else "—")})
            if off_rows:
                st.dataframe(pd.DataFrame(off_rows), width="stretch", hide_index=True)
        else:
            st.caption("Load board to see today's officials.")
    
    st.markdown("### ⚡ Sharp Money Alerts")
    sharp_flags = st.session_state.get("game_sharp_flags", {})
    if sharp_flags:
        for matchup, info in sharp_flags.items():
            st.warning(f"**{matchup}**: Line moved {info['direction']}{info['magnitude']} — possible sharp action")
    else:
        st.caption("No significant line movement detected.")
    
    power_divs = st.session_state.get("power_divergences", {})
    if power_divs:
        st.markdown("### ⚡ Market Inefficiency Alerts")
        for matchup, data in power_divs.items():
            st.info(f"**{matchup}**: {data['note']}")
    
    st.markdown("### 📈 Prop Line Movement")
    st.caption("Props that moved since last board load")
    line_movement = st.session_state.get("line_movement", {})
    if line_movement:
        move_rows = []
        for key, move in line_movement.items():
            if abs(move.get("diff", 0)) >= 0.5:
                move_rows.append({"Player": move["player"], "Prop": move["prop"], "Was": move["prev_line"], "Now": move["curr_line"], "Move": f"{move['direction']}{abs(move['diff'])}", "Signal": ("🔥 Sharp" if abs(move["diff"]) >= 1.0 else "⚡ Notable")})
        if move_rows:
            st.dataframe(pd.DataFrame(move_rows), width="stretch")
        else:
            st.caption("No significant prop movement detected.")
    else:
        st.caption("Load board to track prop movements.")
    
    st.markdown("### 📊 Book Line Discrepancies")
    st.caption("Lines differing 0.5+ between PrizePicks and DraftKings/Bovada")
    discrepancies = st.session_state.get("multibook_discrepancies", [])
    if discrepancies:
        st.dataframe(pd.DataFrame(discrepancies[:8]), width="stretch")
    else:
        st.caption("No significant discrepancies found.")
    
    st.markdown("---")
    st.markdown("## 📊 PLAYER PROPS — TOP PICKS")
    board = st.session_state.board_data
    if board:
        top8 = board[:8]
        for p in top8:
            tier_colors = {"SOVEREIGN": "#e8a020", "ELITE": "#0ea5a0", "APPROVED": "#4a90d9", "LEAN": "#7a8a9a"}
            tier_color = tier_colors.get(p["Tier"], "#7a8a9a")
            injury_html = ""
            if p.get("Injury"):
                injury_html = f'<span style="background:#e04040;color:white;font-size:10px;padding:2px 6px;border-radius:10px;margin-left:6px;">{p["Injury"]}</span>'
            search_html = ""
            if p.get("SearchNeeded"):
                search_query = p.get("SearchQuery", "")
                search_html = (
                    f'<span style="background:#4a4a20;'
                    f'color:#e8d020;font-size:10px;'
                    f'padding:2px 6px;border-radius:10px;'
                    f'margin-left:6px;" '
                    f'title="Search: {search_query}">'
                    f'🔍 Verify avg</span>'
                )
            sharp_html = ""
            if p.get("SharpFlag"):
                sharp_html = f'<span style="color:#e8a020;font-size:11px;margin-left:8px;">{p["SharpFlag"]}</span>'
            trend_html = ""
            if p.get("Trend"):
                trend_html = f'<span style="font-size:11px;margin-left:8px;">{p["Trend"]}</span>'
            ev_2 = p.get("EV_2pick", "—")
            ev_color = "#22c55e" if str(ev_2).startswith("+") else "#e04040"
            avg_val = p.get("Avg", 0)
            line_val = p.get("Line", 0)
            side = p.get("Side", "OVER")
            if avg_val and line_val:
                diff = avg_val - line_val
                if side == "OVER" and diff > 0:
                    reason = f"Averaging {avg_val:.1f} vs line of {line_val} — {diff:.1f} above the number"
                elif side == "UNDER" and diff < 0:
                    reason = f"Averaging {avg_val:.1f} vs line of {line_val} — {abs(diff):.1f} below the number"
                else:
                    reason = f"Model edge detected: {p['EdgePct']}"
            else:
                reason = f"Edge: {p['EdgePct']}"
            st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {tier_color};border-radius:8px;padding:14px 18px;margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
    <div>
      <span style="font-size:16px;font-weight:700;color:#e8f0f8;">{p['Player']}</span>
      {injury_html}{search_html}{sharp_html}{trend_html}<br/>
      <span style="font-size:14px;color:{tier_color};font-weight:600;">{p['Side']} {p['Line']} {p['Prop']}</span>
    </div>
    <div style="text-align:right;">
      <span style="background:{tier_color};color:#000;font-weight:700;font-size:12px;padding:3px 10px;border-radius:20px;">{p['Tier']}</span>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px;">
    <div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">
      <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;letter-spacing:0.8px;">Edge</div>
      <div style="font-size:18px;font-weight:700;color:#0ea5a0;">{p['EdgePct']}</div>
    </div>
    <div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">
      <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;letter-spacing:0.8px;">2-Pick EV</div>
      <div style="font-size:18px;font-weight:700;color:{ev_color};">{ev_2}</div>
    </div>
    <div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">
      <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;letter-spacing:0.8px;">Avg (10g)</div>
      <div style="font-size:18px;font-weight:700;color:#e8f0f8;">{avg_val:.1f}</div>
    </div>
    <div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">
      <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;letter-spacing:0.8px;">Bet Size</div>
      <div style="font-size:18px;font-weight:700;color:#e8a020;">${p.get('Wager_2pick', p.get('Wager', 0)):.2f}</div>
    </div>
  </div>
  <div style="margin-top:8px;font-size:12px;color:#6a7a8a;font-style:italic;">
    📊 {reason}
    {f" | {p.get('RefNote','')}" if p.get('RefNote') else ""}
    {f" | {p.get('WeatherNote','')}" if p.get('WeatherNote') else ""}
    {f" | Confidence: {p.get('SEM','—')}" if p.get('SEM','—') != '—' else ""}
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.info("No props loaded.")
    
    st.markdown("---")
    st.markdown("## 🎯 RECOMMENDED ACTION TODAY")
    board = st.session_state.board_data
    game_analysis = st.session_state.get("game_analysis", [])
    sovereign_elite = [p for p in board if p["Tier"] in ("SOVEREIGN", "ELITE")] if board else []
    approved = [p for p in board if p["Tier"] == "APPROVED"] if board else []
    best_game = game_analysis[0] if game_analysis else None
    if not board and not game_analysis:
        st.info("Load the board to see today's recommended action.")
    else:
        if len(sovereign_elite) >= 2:
            action_color, action_text = "#22c55e", "STRONG BETTING DAY"
            action_detail = f"{len(sovereign_elite)} elite props available. High confidence board."
        elif len(sovereign_elite) == 1:
            action_color, action_text = "#0ea5a0", "SELECTIVE DAY"
            action_detail = f"1 elite prop + {len(approved)} approved plays. Be selective."
        elif len(approved) >= 3:
            action_color, action_text = "#4a90d9", "MODERATE DAY"
            action_detail = f"{len(approved)} approved plays. No elite props — reduce sizing."
        else:
            action_color, action_text = "#e8a020", "LIGHT DAY"
            action_detail = "Limited quality available. Consider sitting out or 1 pick max."
        st.markdown(f"""
<div style="background:linear-gradient(135deg,rgba(14,165,160,0.1),#0d1520);border:2px solid {action_color};border-radius:12px;padding:20px 24px;margin:12px 0;">
  <div style="font-size:22px;font-weight:800;color:{action_color};margin-bottom:8px;">{action_text}</div>
  <div style="font-size:15px;color:#e8f0f8;margin-bottom:16px;">{action_detail}</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
    <div style="background:#060c14;border-radius:8px;padding:12px;text-align:center;">
      <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;">Elite Plays</div>
      <div style="font-size:28px;font-weight:800;color:{action_color};">{len(sovereign_elite)}</div>
    </div>
    <div style="background:#060c14;border-radius:8px;padding:12px;text-align:center;">
      <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;">Total Props</div>
      <div style="font-size:28px;font-weight:800;color:#e8f0f8;">{len(board) if board else 0}</div>
    </div>
    <div style="background:#060c14;border-radius:8px;padding:12px;text-align:center;">
      <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;">Game Edges</div>
      <div style="font-size:28px;font-weight:800;color:#4a90d9;">{len(game_analysis)}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)
        best_prop = board[0] if board else None
        if best_prop or best_game:
            st.markdown("**Your best plays right now:**")
            if best_prop:
                st.markdown(f"🏀 **Best Prop:** {best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']} — {best_prop['EdgePct']} edge")
            if best_game and best_game.get("best_bet"):
                bb = best_game["best_bet"]
                st.markdown(f"🏟️ **Best Game:** {best_game['matchup']} → {bb['pick']} — {bb['edge_pct']} edge")
    
    st.markdown("---")
    st.markdown("## 🔒 LOCK OF THE DAY")
    quality_board = st.session_state.get("quality_sorted_board", board)
    best = next((p for p in quality_board if p["Tier"] in ["SOVEREIGN","ELITE","APPROVED"]), None)
    if best:
        tier_color = TIER_COLORS.get(best['Tier'], "#0ea5a0")
        avg_val = best.get('Avg', 0)
        line_val = best.get('Line', 0)
        diff = avg_val - line_val
        lock_score = best.get('LockScore', 0)
        if lock_score >= 80:
            lock_grade, lock_color = "🟢 PRIME LOCK", "#22c55e"
        elif lock_score >= 60:
            lock_grade, lock_color = "🟡 SOLID LOCK", "#e8a020"
        elif lock_score >= 40:
            lock_grade, lock_color = "🟠 SPECULATIVE", "#e07020"
        else:
            lock_grade, lock_color = "🔴 RISKY", "#e04040"
        st.markdown(f"""
<div style="background:linear-gradient(135deg,rgba({tier_color[1:3]},{tier_color[3:5]},{tier_color[5:7]},0.15),#0d1520);border:2px solid {tier_color};border-radius:12px;padding:20px 24px;margin:16px 0;">
  <div style="font-size:12px;color:{tier_color};font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">🏆 Lock of the Day — {best['Tier']}</div>
  <div style="font-size:22px;font-weight:800;color:#ffffff;margin-bottom:4px;">{best['Player']}</div>
  <div style="font-size:18px;color:{tier_color};font-weight:600;margin-bottom:12px;">{best['Side']} {best['Line']} {best['Prop']}</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:12px;">
    <div style="text-align:center;"><div style="font-size:10px;color:#6a7a8a;">EDGE</div><div style="font-size:24px;font-weight:800;color:#0ea5a0;">{best['EdgePct']}</div></div>
    <div style="text-align:center;"><div style="font-size:10px;color:#6a7a8a;">2-PICK EV</div><div style="font-size:24px;font-weight:800;color:#22c55e;">{best.get('EV_2pick','—')}</div></div>
    <div style="text-align:center;"><div style="font-size:10px;color:#6a7a8a;">BET SIZE</div><div style="font-size:24px;font-weight:800;color:#e8a020;">${best.get('Wager_2pick', best.get('Wager',0)):.2f}</div></div>
  </div>
  <div style="font-size:12px;color:#6a7a8a;margin-bottom:12px;">📊 Averaging {avg_val:.1f} vs line of {line_val} — {abs(diff):.1f} {'above' if diff > 0 else 'below'} the number | Confidence: {best.get('SEM','—')}</div>
  <div style="margin-top:8px;background:#060c14;border-radius:6px;padding:8px;text-align:center;">
    <div style="font-size:10px;color:#6a7a8a;text-transform:uppercase;">LOCK QUALITY SCORE</div>
    <div style="font-size:22px;font-weight:800;color:{lock_color};">{lock_score}/100 — {lock_grade}</div>
  </div>
</div>""", unsafe_allow_html=True)
        if st.button("🔒 Lock This Pick"):
            can_bet, risk_reason = check_daily_risk_limits(best["Sport"])
            if not can_bet:
                st.error(risk_reason)
            else:
                portfolio_warnings = check_portfolio_correlation(best, st.session_state.locks, PLAYER_TEAM_MAP, POSITIVE_CORRELATIONS, NEGATIVE_CORRELATIONS)
                if portfolio_warnings:
                    for w in portfolio_warnings:
                        st.warning(w)
                    if not st.session_state.get("override_correlation_warning", False):
                        st.session_state["override_correlation_warning"] = False
                        col_ow1, col_ow2 = st.columns(2)
                        if col_ow1.button("Lock Anyway", key="override_lock_day"):
                            st.session_state["override_correlation_warning"] = True
                            st.rerun()
                        col_ow2.button("Cancel", key="cancel_lock_day")
                        st.stop()
                already = any(l.get("player") == best["Player"] and l.get("prop") == best["Prop"] for l in st.session_state.locks)
                if not already:
                    st.session_state.locks.append({"player": best["Player"], "prop": best["Prop"], "line": best["Line"], "side": best["Side"], "wager": best["Wager"], "prob": best["Prob"], "edge": best["Edge"], "tier": best["Tier"], "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "sport": best["Sport"]})
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    save_to_gist("locks", st.session_state.locks)
                    st.rerun()
                else:
                    st.warning("Already locked")
    
    st.markdown("---")
    st.markdown("### ⚡ Quick Lock")
    sovereign_elite = [p for p in board if p["Tier"] in ("SOVEREIGN", "ELITE") and not any(l.get("player") == p["Player"] and l.get("prop") == p["Prop"] for l in st.session_state.locks)]
    if sovereign_elite:
        st.write(f"**{len(sovereign_elite)}** SOVEREIGN/ELITE props available:")
        for p in sovereign_elite[:5]:
            st.write(f"• **{p['Player']}** {p['Side']} {p['Line']} {p['Prop']} — {p['EdgePct']} | EV(2): {p.get('EV_2pick','—')}")
        can_bet, risk_reason = check_daily_risk_limits(st.session_state.last_sport)
        if can_bet:
            if st.button(f"🔒 Lock All {min(len(sovereign_elite), 3)} Top Picks"):
                locked_count = 0
                for p in sovereign_elite[:3]:
                    already = any(l.get("player") == p["Player"] and l.get("prop") == p["Prop"] for l in st.session_state.locks)
                    if not already:
                        st.session_state.locks.append({"player": p["Player"], "prop": p["Prop"], "line": p["Line"], "side": p["Side"], "wager": p.get("Wager_2pick", p["Wager"]), "prob": p["Prob"], "edge": p["Edge"], "tier": p["Tier"], "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "sport": p["Sport"]})
                        locked_count += 1
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)
                st.success(f"Locked {locked_count} picks")
                st.rerun()
        else:
            st.error(risk_reason)
    else:
        st.caption("No SOVEREIGN or ELITE props available.")
    
    st.markdown("---")
    st.markdown("## 🏟️ LOCK OF THE DAY — GAME")
    game_analysis = st.session_state.get("game_analysis", [])
    if game_analysis and game_analysis[0].get("best_bet"):
        best_game = game_analysis[0]
        bb = best_game["best_bet"]
        tier_color = TIER_COLORS.get(bb.get("tier","LEAN"), "#0ea5a0")
        alt_lines = fetch_alternate_lines(st.session_state.last_sport, best_game["matchup"])
        alt_text = ""
        if alt_lines.get("spreads") or alt_lines.get("totals"):
            alt_count = len(alt_lines.get("spreads",[])) + len(alt_lines.get("totals",[]))
            alt_text = f"+ {alt_count} alternate lines available"
        st.markdown(f"""
<div style="background:#0d1520;border:2px solid {tier_color};border-left:6px solid {tier_color};border-radius:12px;padding:20px 24px;margin:12px 0;">
  <div style="font-size:12px;color:{tier_color};font-weight:700;text-transform:uppercase;letter-spacing:1px;">🏟️ Best Game Bet — {bb.get('tier','—')}</div>
  <div style="font-size:20px;font-weight:800;color:#ffffff;margin:8px 0;">{best_game['matchup']}</div>
  <div style="font-size:18px;color:{tier_color};font-weight:700;margin-bottom:12px;">{bb['pick']} ({bb['type']})</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px;">
    <div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;"><div style="font-size:10px;color:#6a7a8a;">EDGE</div><div style="font-size:20px;font-weight:800;color:#0ea5a0;">{bb['edge_pct']}</div></div>
    <div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;"><div style="font-size:10px;color:#6a7a8a;">TYPE</div><div style="font-size:20px;font-weight:800;color:#e8f0f8;">{bb['type']}</div></div>
    <div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;"><div style="font-size:10px;color:#6a7a8a;">TIER</div><div style="font-size:20px;font-weight:800;color:{tier_color};">{bb.get('tier','—')}</div></div>
  </div>
  <div style="font-size:12px;color:#6a7a8a;margin-bottom:8px;">📊 {bb.get('note','')}</div>
  {f'<div style="font-size:11px;color:#4a90d9;">📋 {alt_text}</div>' if alt_text else ''}
</div>""", unsafe_allow_html=True)
        if alt_lines.get("spreads"):
            with st.expander("📋 Alternate Spread Lines"):
                alt_rows = [{"Spread": alt.get("spread","—"), "Odds": alt.get("odds","—"), "Book": alt.get("book","—").title()} for alt in alt_lines["spreads"][:10]]
                if alt_rows:
                    st.dataframe(pd.DataFrame(alt_rows), width="stretch", hide_index=True)
        if alt_lines.get("totals"):
            with st.expander("📋 Alternate Total Lines"):
                alt_rows = [{"Side": alt.get("side","—"), "Total": alt.get("total","—"), "Odds": alt.get("odds","—"), "Book": alt.get("book","—").title()} for alt in alt_lines["totals"][:10]]
                if alt_rows:
                    st.dataframe(pd.DataFrame(alt_rows), width="stretch", hide_index=True)
    else:
        st.info("Load the board to see today's best game bet.")
    
    st.markdown("---")
    st.markdown("## ⚡ PARLAY OF THE DAY — PROPS")
    board = st.session_state.board_data
    top_props = [p for p in board if p["Tier"] in ("SOVEREIGN","ELITE","APPROVED")] if board else []
    if len(top_props) >= 2:
        n_picks_parlay = st.radio("Picks in parlay", [2, 3, 4, 5], index=1, horizontal=True, key="prop_parlay_picks")
        parlay_props = top_props[:n_picks_parlay]
        adjusted_probs, corr_notes = detect_correlations(parlay_props)
        contradiction_warnings = detect_game_script_contradictions(parlay_props, st.session_state.games)
        for note in corr_notes:
            if "⚠️" in note or "🚨" in note:
                st.warning(note)
            else:
                st.info(note)
        for cw in contradiction_warnings:
            st.warning(cw)
        for p in parlay_props:
            ev_key = "EV_2pick" if n_picks_parlay == 2 else "EV_3pick"
            ev_val = p.get(ev_key, "—")
            ev_color = "#22c55e" if str(ev_val).startswith("+") else "#e04040"
            st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:3px solid #0ea5a0;border-radius:6px;padding:10px 14px;margin-bottom:6px;display:flex;justify-content:space-between;">
  <span style="color:#e8f0f8;font-weight:600;">{p['Player']} {p['Side']} {p['Line']} {p['Prop']}</span>
  <span style="color:{ev_color};font-weight:700;font-size:13px;">EV: {ev_val}</span>
</div>""", unsafe_allow_html=True)
        pp_multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks_parlay, 3.0)
        pp_breakeven = (1 / pp_multiplier)
        cp = parlay_prob(adjusted_probs)
        pp_ev = cp - pp_breakeven
        tw = sum(p.get("Wager_2pick", p.get("Wager", 0)) for p in parlay_props)
        ev_color = "#22c55e" if pp_ev > 0 else "#e04040"
        ev_label = f"+{pp_ev:.1%} ✅ +EV" if pp_ev > 0 else f"{pp_ev:.1%} ❌ -EV"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Combined Prob", f"{cp:.1%}")
        c2.metric(f"{n_picks_parlay}-pick Pays", f"{pp_multiplier}x")
        c3.metric("Breakeven", f"{pp_breakeven:.1%}")
        c4.metric("True EV", ev_label)
        if pp_ev > 0:
            st.success(f"✅ This {n_picks_parlay}-pick is +EV. If hits: ${tw * pp_multiplier:.2f}")
        else:
            st.error(f"❌ This {n_picks_parlay}-pick is -EV.")
    else:
        st.caption("Need 2+ SOVEREIGN/ELITE/APPROVED props.")
    
    st.markdown("---")
    st.markdown("## 🏟️ PARLAY OF THE DAY — GAMES")
    game_analysis = st.session_state.get("game_analysis", [])
    good_games = [g for g in game_analysis if g.get("best_bet") and g["best_edge"] >= 0.04]
    if len(good_games) >= 2:
        n_game_picks = st.radio("Games in parlay", [2, 3, 4], index=0, horizontal=True, key="game_parlay_picks")
        parlay_games = good_games[:n_game_picks]
        for g in parlay_games:
            bb = g["best_bet"]
            tier_color = TIER_COLORS.get(bb.get("tier","LEAN"), "#7a8a9a")
            st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:3px solid {tier_color};border-radius:6px;padding:10px 14px;margin-bottom:6px;">
  <span style="color:#6a7a8a;font-size:11px;">{g['matchup']} — {bb['type']}</span><br/>
  <span style="color:#e8f0f8;font-weight:700;font-size:15px;">{bb['pick']}</span>
  <span style="color:{tier_color};font-weight:600;font-size:13px;margin-left:12px;">{bb['edge_pct']} edge</span>
</div>""", unsafe_allow_html=True)
        game_probs = [min(0.70, 0.5 + g["best_edge"]) for g in parlay_games]
        combined = parlay_prob(game_probs)
        breakeven = 0.524 ** n_game_picks
        ev = combined - breakeven
        c1, c2, c3 = st.columns(3)
        c1.metric("Combined Prob", f"{combined:.1%}")
        c2.metric("Breakeven (-110)", f"{breakeven:.1%}")
        c3.metric("True EV", f"+{ev:.1%} ✅" if ev > 0 else f"{ev:.1%} ❌")
        if ev > 0:
            st.success(f"✅ This {n_game_picks}-game parlay is +EV at -110.")
        else:
            st.error(f"❌ Combined probability below breakeven.")
    else:
        st.caption("Need 2+ games with detected edge.")
    
    st.markdown("---")
    st.markdown("## 💰 BEST +EV PROPS TODAY")
    board = st.session_state.board_data
    if board:
        ev_filter = st.radio("Filter by pick count", ["2-pick", "3-pick", "Both"], index=0, horizontal=True, key="ev_filter")
        plus_ev_props = []
        for p in board:
            ev2 = p.get("EV_2pick","—")
            ev3 = p.get("EV_3pick","—")
            is_ev2 = str(ev2).startswith("+")
            is_ev3 = str(ev3).startswith("+")
            include = False
            if ev_filter == "2-pick" and is_ev2:
                include = True
            elif ev_filter == "3-pick" and is_ev3:
                include = True
            elif ev_filter == "Both" and (is_ev2 or is_ev3):
                include = True
            if include:
                plus_ev_props.append(p)
        if plus_ev_props:
            st.write(f"**{len(plus_ev_props)} +EV props found:**")
            for p in plus_ev_props[:8]:
                tier_color = TIER_COLORS.get(p["Tier"], "#7a8a9a")
                ev_show = p.get("EV_2pick","—") if "2" in ev_filter else p.get("EV_3pick","—")
                st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:3px solid {tier_color};border-radius:6px;padding:10px 14px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
  <div><span style="color:#e8f0f8;font-weight:700;">{p['Player']}</span><span style="color:{tier_color};font-size:13px;margin-left:8px;">{p['Side']} {p['Line']} {p['Prop']}</span></div>
  <div style="text-align:right;"><span style="color:#22c55e;font-weight:700;font-size:14px;">{ev_show}</span><span style="color:#6a7a8a;font-size:11px;margin-left:8px;">{p['Tier']}</span></div>
</div>""", unsafe_allow_html=True)
        else:
            st.info(f"No confirmed +EV props at {ev_filter} breakeven.")
    else:
        st.info("Load board to see +EV props.")
    
    st.markdown("---")
    st.markdown("## 💰 BEST +EV GAMES TODAY")
    game_analysis = st.session_state.get("game_analysis", [])
    plus_ev_games = [g for g in game_analysis if g.get("best_bet") and g["best_edge"] >= 0.05]
    if plus_ev_games:
        for g in plus_ev_games[:5]:
            bb = g["best_bet"]
            tier_color = TIER_COLORS.get(bb.get("tier","LEAN"), "#7a8a9a")
            fair_prob = min(0.70, 0.5 + g["best_edge"])
            ev_110 = fair_prob * (100/110) - (1-fair_prob) * 1
            ev_color = "#22c55e" if ev_110 > 0 else "#e04040"
            st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {tier_color};border-radius:8px;padding:12px 16px;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div><div style="color:#6a7a8a;font-size:11px;">{g['matchup']}</div><div style="color:#e8f0f8;font-weight:700;font-size:16px;margin:4px 0;">{bb['pick']}</div><div style="color:#6a7a8a;font-size:11px;">{bb.get('note','')}</div></div>
    <div style="text-align:right;"><div style="color:{tier_color};font-weight:700;font-size:18px;">{bb['edge_pct']}</div><div style="color:{ev_color};font-size:13px;font-weight:600;">EV: {ev_110:+.1%}</div><div style="color:#6a7a8a;font-size:10px;">{bb['type']}</div></div>
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.info("No +EV games detected.")
    
    st.markdown("---")
    st.markdown("## 🌐 BEST OF ALL SPORTS")
    all_sports_results = st.session_state.get("all_sports_results", None)
    col_scan1, col_scan2 = st.columns([2,1])
    with col_scan1:
        if st.button("🔍 Find Today's Best Plays Across All Sports", key="scan_all_sports_btn"):
            with st.spinner("Scanning all sports boards..."):
                results = scan_all_sports_best_plays()
                st.session_state["all_sports_results"] = results
                st.rerun()
    with col_scan2:
        if all_sports_results:
            st.caption(f"Last scanned: {all_sports_results.get('timestamp','—')}")
    if all_sports_results:
        best_props = all_sports_results.get("best_props", [])
        best_games = all_sports_results.get("best_games", [])
        if best_props:
            st.markdown(f"### 🏆 Top Props ({len(best_props)} found)")
            for p in best_props[:4]:
                tier_color = TIER_COLORS.get(p["Tier"], "#7a8a9a")
                ev_color = "#22c55e" if str(p.get("EV_2pick","—")).startswith("+") else "#e04040"
                st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {tier_color};border-radius:8px;padding:12px 16px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
  <div><span style="color:#6a7a8a;font-size:11px;">{p['Sport']}</span><br/><span style="color:#e8f0f8;font-weight:700;">{p['Player']}</span><span style="color:{tier_color};margin-left:8px;font-size:13px;">{p['Side']} {p['Line']} {p['Prop']}</span></div>
  <div style="text-align:right;"><div style="color:#0ea5a0;font-weight:800;">{p['EdgePct']}</div><div style="color:{ev_color};font-size:12px;">2-pick: {p.get('EV_2pick','—')}</div><div style="color:#6a7a8a;font-size:10px;">{p['Tier']}</div></div>
</div>""", unsafe_allow_html=True)
        if best_games:
            st.markdown(f"### 🏟️ Top Game Bets ({len(best_games)} found)")
            for g in best_games[:4]:
                bb = g.get("best_bet",{})
                tier_color = TIER_COLORS.get(bb.get("tier","LEAN"), "#7a8a9a")
                st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {tier_color};border-radius:8px;padding:12px 16px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
  <div><span style="color:#6a7a8a;font-size:11px;">{g.get('sport','—')} — {g['matchup']}</span><br/><span style="color:#e8f0f8;font-weight:700;">{bb.get('pick','—')}</span><span style="color:#6a7a8a;font-size:11px;margin-left:8px;">{bb.get('type','—')}</span></div>
  <div style="text-align:right;"><div style="color:#0ea5a0;font-weight:800;">{bb.get('edge_pct','—')}</div><div style="color:#6a7a8a;font-size:10px;">{bb.get('tier','—')}</div></div>
</div>""", unsafe_allow_html=True)
        top_slip_props = best_props[:3]
        top_slip_games = best_games[:2]
        if top_slip_props or top_slip_games:
            st.markdown("### 📋 Master Daily Slip")
            if top_slip_props:
                st.markdown("**Player Props:**")
                for p in top_slip_props:
                    st.markdown(f"• **{p['Sport']}** — {p['Player']} {p['Side']} {p['Line']} {p['Prop']} ({p['EdgePct']})")
            if top_slip_games:
                st.markdown("**Game Bets:**")
                for g in top_slip_games:
                    bb = g.get("best_bet",{})
                    st.markdown(f"• **{g.get('sport','—')}** — {g['matchup']}: {bb.get('pick','—')} ({bb.get('edge_pct','—')})")

# ----- TAB 1: FULL BOARD -----
with tabs[1]:
    st.markdown(f"## 📊 Full Board — {st.session_state.last_sport}")
    if st.session_state.board_data:
        tier_filter = st.multiselect("Filter by Tier", ["SOVEREIGN", "ELITE", "APPROVED", "LEAN"], default=["SOVEREIGN", "ELITE", "APPROVED"])
        filtered = [p for p in st.session_state.board_data if p["Tier"] in tier_filter]
        if filtered:
            display_df = make_display_df(filtered)
            show_cols = ["Player", "Stat", "Line", "Play", "Avg (10g)", "Fair %", "Edge", "2-Pick EV", "Bet Size", "Tier", "Sharp $", "Market", "Confidence", "Injury", "Line Move", "Trend", "Source"]
            show_cols = [c for c in show_cols if c in display_df.columns]
            st.dataframe(display_df[show_cols], width="stretch", hide_index=True)
            with st.expander("📊 Signal Breakdown"):
                signal_df_raw = pd.DataFrame(filtered)
                signal_cols_check = ["Player","SignalBase","SignalDefense","SignalLocation","SignalRest","SignalPace","SignalUsage","SignalBlowout","WeatherNote","SampleSize","ConfidenceMult","EdgePct"]
                signal_cols_check = [c for c in signal_cols_check if c in signal_df_raw.columns]
                if signal_cols_check:
                    signal_df = signal_df_raw[signal_cols_check].copy()
                    for col in ["SignalBase","SignalDefense","SignalLocation","SignalRest","SignalPace","SignalUsage","SignalBlowout"]:
                        if col in signal_df.columns:
                            signal_df[col] = signal_df[col].apply(lambda x: f"{x:.1%}" if isinstance(x,(int,float)) else x)
                    st.dataframe(signal_df.head(10), width="stretch")
            options = [f"{r['Player']} — {r['Side']} {r['Line']} {r['Prop']} (Edge: {r['EdgePct']} | {r['Tier']})" for r in filtered]
            if options:
                sel = st.selectbox("Select prop", range(len(options)), format_func=lambda i: options[i])
                if st.button("🔒 Lock Selected"):
                    row = filtered[sel]
                    can_bet, risk_reason = check_daily_risk_limits(row["Sport"])
                    if not can_bet:
                        st.error(risk_reason)
                    else:
                        portfolio_warnings = check_portfolio_correlation(row, st.session_state.locks, PLAYER_TEAM_MAP, POSITIVE_CORRELATIONS, NEGATIVE_CORRELATIONS)
                        if portfolio_warnings:
                            for w in portfolio_warnings:
                                st.warning(w)
                        if st.session_state.board_data:
                            contra = detect_game_script_contradictions([row], st.session_state.games)
                            for c in contra:
                                st.warning(c)
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
        with st.expander("📖 Column Guide"):
            st.markdown("**Player** — Athlete name\n**Stat** — Stat being projected\n**Line** — PrizePicks number\n**Play** — OVER/UNDER\n**Avg (10g)** — EWMA weighted average\n**Fair %** — Model probability\n**Edge** — Edge over implied\n**2-Pick EV** — Expected value in 2-pick (+ = profitable)\n**Bet Size** — Kelly-optimized wager\n**Tier** — Quality rating\n**Sharp $** — Sharp money detected\n**Market** — Market efficiency\n**Confidence** — Statistical confidence\n**Line Move** — Line movement since last load\n**Trend** — Hot/cold streak")
    else:
        st.info("Select a sport and click Load Board.")

# ----- TAB 2: GAME LINES -----
with tabs[2]:
    st.markdown(f"## 🏟️ Game Lines — {st.session_state.last_sport}")
    if st.session_state.games:
        games_df = pd.DataFrame(st.session_state.games)
        display_cols = ["Matchup", "Status", "Spread", "Total", "Home ML", "Away ML", "Odds Source", "Date"]
        display_cols = [c for c in display_cols if c in games_df.columns]
        st.dataframe(games_df[display_cols], width="stretch")
        st.markdown("---")
        st.markdown("### ⚡ Line Movement History")
        movement_data = st.session_state.get("game_line_movement", {})
        sharp_flags = st.session_state.get("game_sharp_flags", {})
        if movement_data:
            for matchup, movements in movement_data.items():
                if not movements:
                    continue
                sharp = sharp_flags.get(matchup, {})
                sharp_label = " ⚡ SHARP" if sharp.get("sharp") else ""
                with st.expander(f"{matchup}{sharp_label}"):
                    if len(movements) >= 2:
                        first, last = movements[-1], movements[0]
                        st.write(f"**Opening:** Spread {first.get('spread','—')} | Total {first.get('over_under','—')}")
                        st.write(f"**Current:** Spread {last.get('spread','—')} | Total {last.get('over_under','—')}")
                    else:
                        st.caption("Not enough movement data yet")
        else:
            st.caption("Load board to see line movement.")
    else:
        st.info("No games found.")

# ----- TAB 3: LOCKS & LEDGER -----
with tabs[3]:
    st.markdown("## 🔒 Active Locks")
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
            st.markdown(f"""
<div style="background:#0d1520;border:1px solid #1a2a3a;border-left:4px solid {tier_color};border-radius:8px;padding:12px 16px;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
    <div>
      <span style="color:#e8f0f8;font-weight:700;font-size:15px;">{lock['player']}</span>
      <span style="background:{tier_color};color:#000;font-size:10px;font-weight:700;padding:2px 8px;border-radius:12px;margin-left:8px;">{lock.get('tier','—')}</span><br/>
      <span style="color:{tier_color};font-weight:600;">{lock['side']} {lock['line']} {lock['prop']}</span>
      <span style="color:#6a7a8a;font-size:11px;margin-left:10px;">{lock.get('sport','—')} | Locked: {lock.get('timestamp','—')}</span>
    </div>
    <div style="text-align:right;">
      <div style="font-size:13px;color:#0ea5a0;font-weight:700;">Edge: {edge_val:.1%}</div>
      <div style="font-size:13px;color:{ev_color};font-weight:600;">2-pick EV: {ev_2:+.1%}</div>
      <div style="font-size:13px;color:#e8a020;font-weight:700;">Wager: ${lock['wager']:.2f}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)
            col1, col2, col3, col4 = st.columns([4,1,1,1])
            col1.write("")
            
            if col2.button("✅ WIN", key=f"win_{i}"):
                pick_count = st.session_state.get("last_pick_count", 2)
                multiplier = PRIZEPICKS_MULTIPLIERS.get(pick_count, 3.0)
                profit = round(lock["wager"] * multiplier, 2)
                st.session_state.bankroll += profit
                st.session_state.history.append({
                    **lock, "outcome": "WIN",
                    "profit": profit, "loss": 0,
                    "net": profit,
                    "pick_count": pick_count,
                    "stat_type": lock.get("prop", ""),
                    "resolved_date": date.today().strftime("%Y-%m-%d")
                })
                save_json_data(BANKROLL_PATH, st.session_state.bankroll)
                save_to_gist("bankroll", st.session_state.bankroll)
                save_json_data(HISTORY_PATH, st.session_state.history)
                save_to_gist("history", st.session_state.history)
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)
                record_clv(lock, st.session_state.board_data)
                st.rerun()
            
            if col3.button("❌ LOSS", key=f"loss_{i}"):
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
                st.rerun()
            if col4.button("↩ VOID", key=f"void_{i}"):
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)
                st.rerun()
    else:
        st.info("No active locks.")

# ----- TAB 4: HISTORY -----
with tabs[4]:
    st.markdown("## 📈 Full Bet History")
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
        st.markdown("### 📊 Performance Analytics")
        if len(st.session_state.history) >= 5:
            resolved = hist_df[hist_df["outcome"].isin(["WIN","LOSS"])] if "outcome" in hist_df.columns else pd.DataFrame()
            if not resolved.empty:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Hit Rate by Tier**")
                    if "tier" in resolved.columns:
                        tier_stats_h = resolved.groupby("tier").apply(lambda x: pd.Series({"Bets": len(x), "Hit Rate": f"{(x['outcome']=='WIN').mean():.1%}", "Net": f"${x['net'].sum():.2f}" if "net" in x else "—"})).reset_index()
                        st.dataframe(tier_stats_h, width="stretch")
                with col_b:
                    st.markdown("**Hit Rate by Sport**")
                    if "sport" in resolved.columns:
                        sport_stats_h = resolved.groupby("sport").apply(lambda x: pd.Series({"Bets": len(x), "Hit Rate": f"{(x['outcome']=='WIN').mean():.1%}", "Net": f"${x['net'].sum():.2f}" if "net" in x else "—"})).reset_index()
                        st.dataframe(sport_stats_h, width="stretch")
                outcomes = resolved["outcome"].tolist()
                if outcomes:
                    streak, streak_type = 1, outcomes[-1]
                    for i in range(len(outcomes)-2, -1, -1):
                        if outcomes[i] == streak_type:
                            streak += 1
                        else:
                            break
                    color = "green" if streak_type == "WIN" else "red"
                    st.markdown(f'<p style="color:{color};font-size:18px;font-weight:700;">Current Streak: {streak} {streak_type}{"s" if streak > 1 else ""}</p>', unsafe_allow_html=True)
                if "net" in resolved.columns:
                    rc = resolved.copy()
                    rc["cumulative"] = DEFAULT_BANKROLL + rc["net"].cumsum()
                    st.line_chart(rc["cumulative"])
                clv_data = load_json_data(CLV_PATH, [])
                if len(clv_data) >= 5:
                    clv_df = pd.DataFrame(clv_data)
                    avg_clv = clv_df["clv"].mean()
                    pos_rate = (clv_df["clv"] > 0).mean()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Avg CLV", f"{avg_clv:+.2f}")
                    c2.metric("Positive Rate", f"{pos_rate:.1%}")
                    c3.metric("Tracked", len(clv_data))
                    if avg_clv > 0:
                        st.success("✅ Positive CLV — process is sound.")
                    else:
                        st.warning("⚠️ Negative CLV — lines moving against you.")
    st.markdown("---")
    st.markdown("### 💰 ROI by Category")
    st.caption("The metrics that actually matter — profitability by pick count and sport")
    history = st.session_state.history
    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS")]
    if len(resolved) >= 5:
        col_roi1, col_roi2 = st.columns(2)
        with col_roi1:
            st.markdown("**ROI by Pick Count**")
            pick_roi = {}
            for h in resolved:
                pc = h.get("pick_count", 2)
                if pc not in pick_roi:
                    pick_roi[pc] = {"bets": 0, "wagered": 0, "returned": 0}
                wager = h.get("wager", 0)
                pick_roi[pc]["bets"] += 1
                pick_roi[pc]["wagered"] += wager
                if h["outcome"] == "WIN":
                    multiplier = PRIZEPICKS_MULTIPLIERS.get(pc, 3.0)
                    pick_roi[pc]["returned"] += wager * multiplier
            roi_rows = []
            for pc in sorted(pick_roi.keys()):
                data = pick_roi[pc]
                if data["wagered"] > 0:
                    roi = (data["returned"] - data["wagered"]) / data["wagered"] * 100
                    roi_color = "🟢" if roi > 0 else "🔴"
                    roi_rows.append({"Pick Count": f"{pc}-pick", "Bets": data["bets"], "Wagered": f"${data['wagered']:.2f}", "Returned": f"${data['returned']:.2f}", "ROI": f"{roi_color} {roi:+.1f}%"})
            if roi_rows:
                st.dataframe(pd.DataFrame(roi_rows), width="stretch", hide_index=True)
                best_pc = max(pick_roi.keys(), key=lambda x: (pick_roi[x]["returned"]-pick_roi[x]["wagered"])/max(pick_roi[x]["wagered"],1))
                st.success(f"✅ Best pick count: {best_pc}-pick")
        with col_roi2:
            st.markdown("**ROI by Sport**")
            sport_roi = {}
            for h in resolved:
                sp = h.get("sport", "Unknown")
                if sp not in sport_roi:
                    sport_roi[sp] = {"bets": 0, "wagered": 0, "net": 0}
                sport_roi[sp]["bets"] += 1
                sport_roi[sp]["wagered"] += h.get("wager", 0)
                sport_roi[sp]["net"] += h.get("net", 0)
            sport_rows = []
            for sp, data in sorted(sport_roi.items(), key=lambda x: x[1]["net"], reverse=True):
                if data["wagered"] > 0:
                    roi = data["net"] / data["wagered"] * 100
                    roi_color = "🟢" if roi > 0 else "🔴"
                    sport_rows.append({"Sport": sp, "Bets": data["bets"], "Net P&L": f"${data['net']:+.2f}", "ROI": f"{roi_color} {roi:+.1f}%"})
            if sport_rows:
                st.dataframe(pd.DataFrame(sport_rows), width="stretch", hide_index=True)
        st.markdown("**ROI by Tier**")
        tier_roi = {}
        for h in resolved:
            tier = h.get("tier", "Unknown")
            if tier not in tier_roi:
                tier_roi[tier] = {"bets": 0, "wagered": 0, "net": 0, "wins": 0}
            tier_roi[tier]["bets"] += 1
            tier_roi[tier]["wagered"] += h.get("wager",0)
            tier_roi[tier]["net"] += h.get("net", 0)
            if h["outcome"] == "WIN":
                tier_roi[tier]["wins"] += 1
        tier_order = ["SOVEREIGN","ELITE","APPROVED","LEAN","PASS"]
        tier_rows = []
        for tier in tier_order:
            if tier not in tier_roi:
                continue
            data = tier_roi[tier]
            if data["wagered"] > 0:
                roi = data["net"] / data["wagered"] * 100
                hit = data["wins"] / data["bets"] * 100
                vs_be = hit - 57.7
                roi_color = "🟢" if roi > 0 else "🔴"
                be_color = "✅" if vs_be > 0 else "❌"
                tier_rows.append({"Tier": tier, "Bets": data["bets"], "Hit Rate": f"{hit:.1f}%", "vs 57.7% BE": f"{be_color} {vs_be:+.1f}%", "Net P&L": f"${data['net']:+.2f}", "ROI": f"{roi_color} {roi:+.1f}%"})
        if tier_rows:
            st.dataframe(pd.DataFrame(tier_rows), width="stretch", hide_index=True)
            best_tier = max(tier_roi.keys(), key=lambda x: tier_roi[x]["net"])
            worst_tier = min(tier_roi.keys(), key=lambda x: tier_roi[x]["net"])
            st.success(f"✅ Most profitable tier: {best_tier}")
            if tier_roi[worst_tier]["net"] < 0:
                st.warning(f"⚠️ Losing tier: {worst_tier} — consider reducing sizing or stopping")
    else:
        st.caption("Need 5+ resolved bets for ROI analysis.")

# ----- TAB 5: LINE SHOP -----
with tabs[5]:
    st.markdown("## 🛒 Line Shopping")
    board = st.session_state.board_data
    ud_props = st.session_state.get("ud_props_compare", [])
    ow_props = st.session_state.get("oddswrap_props", [])
    if not board:
        st.info("Load the board first.")
    else:
        ud_dict = {}
        for p in ud_props:
            k = normalize_name(p["Player"])
            if k not in ud_dict:
                ud_dict[k] = {}
            ud_dict[k][p["Prop"]] = p["Line"]
        ow_dict = {}
        for p in ow_props:
            k = normalize_name(p["Player"])
            if k not in ow_dict:
                ow_dict[k] = {}
            book = p.get("Book","DK")
            prop = p.get("Prop","")
            if prop not in ow_dict[k]:
                ow_dict[k][prop] = {}
            ow_dict[k][prop][book] = p["Line"]
        rows = []
        for prop in board[:20]:
            player, pn, pp_line, side = prop["Player"], prop["Prop"], prop["Line"], prop["Side"]
            norm = normalize_name(player)
            ud_line = ud_dict.get(norm, {}).get(pn)
            ow_lines = ow_dict.get(norm, {}).get(pn, {})
            all_lines = {"PrizePicks": pp_line}
            if ud_line:
                all_lines["Underdog"] = ud_line
            all_lines.update(ow_lines)
            best_book = (min(all_lines, key=all_lines.get) if side == "OVER" else max(all_lines, key=all_lines.get))
            best_line = all_lines[best_book]
            prop_data = next((p for p in board if p["Player"] == player and p["Prop"] == pn), None)
            best_line_ev_2 = "—"
            ev_improvement = 0
            if prop_data and best_book != "PrizePicks":
                pp_prob = prop_data.get("Prob", 0.5)
                pp_avg = prop_data.get("Avg", 0)
                if pp_avg > 0:
                    line_diff = pp_line - best_line
                    if prop_data.get("Side") == "OVER":
                        improved_prob = min(0.70, pp_prob + (line_diff / pp_avg * 0.3))
                    else:
                        improved_prob = min(0.70, pp_prob - (line_diff / pp_avg * 0.3))
                    better_ev_2 = calculate_prizepicks_ev(improved_prob, 2)
                    orig_ev_2 = calculate_prizepicks_ev(pp_prob, 2)
                    best_line_ev_2 = f"{better_ev_2:+.1%}"
                    ev_improvement = round((better_ev_2 - orig_ev_2) * 100, 1)
            rows.append({"Player": player, "Prop": pn, "Side": side, "PrizePicks": pp_line, "Underdog": ud_line if ud_line else "—", "Best Line": best_line, "Best Book": best_book, "Saves": round(abs(best_line - pp_line), 1) if best_line != pp_line else 0, "PP EV(2)": prop_data.get("EV_2pick", "—") if prop_data else "—", "Best EV(2)": best_line_ev_2, "EV Gain": (f"+{ev_improvement}%" if ev_improvement > 0 else "—"), "Tier": prop.get("Tier", "—")})
        st.dataframe(pd.DataFrame(rows), width="stretch")
        best_opps = [r for r in rows if r["Best Book"] != "PrizePicks" and r["Saves"] >= 0.5]
        if best_opps:
            st.markdown("### 🔥 Better Lines Available")
            st.dataframe(pd.DataFrame(best_opps)[["Player","Prop","PrizePicks","Best Line","Best Book","Saves","Tier"]], width="stretch")
    st.markdown("---")
    st.markdown("### 📊 Cross-Book Discrepancies")
    disc = st.session_state.get("multibook_discrepancies", [])
    if disc:
        st.dataframe(pd.DataFrame(disc[:10]), width="stretch")
    else:
        st.caption("No significant discrepancies found.")

# ----- TAB 6: SYSTEM -----
with tabs[6]:
    st.markdown("## ⚙️ System Info")
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
    st.markdown("### 🛡️ Daily Risk Controls")
    st.write(f"Max locks/day: {DAILY_RISK_CONTROLS['max_locks_per_day']}")
    st.write(f"Stop-loss: -{DAILY_RISK_CONTROLS['max_daily_loss_pct']:.0%}")
    st.write(f"Stop-win: +{DAILY_RISK_CONTROLS['stop_win_pct']:.0%}")
    can_bet, risk_msg = check_daily_risk_limits()
    if can_bet:
        st.success("✅ All risk controls green")
    else:
        st.error(f"🛑 {risk_msg}")
    st.markdown("---")
    st.markdown("### 📊 Multi‑Signal Edge Model")
    st.write("- Base (45%): EWMA-weighted rolling avg")
    st.write("- Defense (30%): Position-specific rating")
    st.write("- Location (15%): Home/Away")
    st.write("- Rest (5%): Back-to-back penalty")
    st.write("- Pace (5%): Team pace")
    st.write("- Usage, Blowout, Weather, Pitcher, Referee, Sharp, Power Rating bonuses")
    current_month = date.today().month
    if current_month in [4, 5, 6]:
        st.warning("⚠️ Playoff season detected. Position defense data is regular season. Treat defense signal with extra caution.")
    st.markdown("---")
    st.markdown("### ⚖️ Sport Signal Weights")
    weight_rows = [{"Sport": sp, "Base": f"{w.get('base',0):.0%}", "Defense": f"{w.get('defense',0):.0%}", "Location": f"{w.get('location',0):.0%}", "Rest": f"{w.get('rest',0):.0%}", "Pace": f"{w.get('pace',0):.0%}"} for sp, w in SPORT_SIGNAL_WEIGHTS.items()]
    st.dataframe(pd.DataFrame(weight_rows), width="stretch", hide_index=True)
    st.markdown("---")
    st.markdown("### 💰 PrizePicks EV Model")
    ev_rows = [{"Picks": f"{n}-pick", "Payout": f"{mult}x", "Breakeven Per Leg": f"{prizepicks_breakeven_prob(n):.1%}", "vs -110 (52.4%)": f"+{(prizepicks_breakeven_prob(n)-0.524)*100:.1f}% harder"} for n, mult in PRIZEPICKS_MULTIPLIERS.items()]
    st.dataframe(pd.DataFrame(ev_rows), width="stretch", hide_index=True)
    st.caption("⚠️ 2-pick needs 57.7% to be +EV — not 52.4% like -110 sportsbook betting.")
    st.markdown("---")
    st.markdown("### 📊 SEM Calibration Summary")
    tier_stats = compute_tier_stats(st.session_state.history)
    if tier_stats:
        sem_df = pd.DataFrame([{"Tier": tier, "Bets": s["n"], "Hit Rate": f"{s['hit_rate']:.1%}", "Predicted": f"{s['avg_predicted']:.1%}", "SEM": f"±{s['sem']:.3f}" if s['sem'] else "—"} for tier, s in tier_stats.items()])
        st.dataframe(sem_df, width="stretch")
    else:
        st.info("No calibration data yet.")
    st.markdown("---")
    st.markdown("### 🔄 CLV Feedback Loop")
    clv_data = load_json_data(CLV_PATH, [])
    if clv_data and len(clv_data) >= 5:
        clv_summary = []
        for sp in SPORTS:
            for tier in ["SOVEREIGN","ELITE","APPROVED","LEAN"]:
                relevant = [c for c in clv_data if c.get("sport")==sp and c.get("tier")==tier]
                if len(relevant) < 3:
                    continue
                avg_clv = sum(c.get("clv",0) for c in relevant)/len(relevant)
                pos_rate = sum(1 for c in relevant if c.get("clv",0)>0)/len(relevant)
                mult, _ = get_clv_edge_adjustment(sp, tier)
                clv_summary.append({"Sport": sp, "Tier": tier, "N": len(relevant), "Avg CLV": f"{avg_clv:+.2f}", "Positive Rate": f"{pos_rate:.0%}", "Edge Adj": f"+{(mult-1)*100:.0f}%" if mult>1 else f"{(mult-1)*100:.0f}%" if mult<1 else "None"})
        if clv_summary:
            st.dataframe(pd.DataFrame(clv_summary), width="stretch", hide_index=True)
    else:
        st.info("No CLV data yet.")
    st.markdown("---")
    st.markdown("### 🔍 Error Log")
    errors = st.session_state.get("errors", [])
    if errors:
        for err in errors[-5:]:
            st.error(f"[{err.get('time','')}] {err.get('source','')}: {err.get('error','')}")
        if st.button("Clear Error Log"):
            st.session_state["errors"] = []
            st.rerun()
    else:
        st.caption("✅ No errors this session.")
    st.markdown("---")
    st.markdown("### 🔍 PrizePicks API Debug")
    if st.button("Test PrizePicks MLB Connection"):
        results = []
        test_urls = ["https://partner-api.prizepicks.com/projections?per_page=1000&league_id=5", "https://api.prizepicks.com/projections?league_id=5&per_page=250", "https://api.prizepicks.com/projections?league_id=5&per_page=250&single_stat=true"]
        
        test_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://app.prizepicks.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://app.prizepicks.com",
            "X-Device-ID": "betcouncil-app-v4",
            "Cache-Control": "no-cache",
        }
        
        for url in test_urls:
            try:
                resp = requests.get(url, headers=test_headers, timeout=10)
                data_count = 0
                if resp.status_code == 200:
                    data = resp.json()
                    data_count = len(data.get("data", []))
                results.append({"URL": url[:60]+"...", "Status": resp.status_code, "Props Found": data_count, "Result": "✅ OK" if resp.status_code==200 and data_count>0 else "⚠️ Empty" if resp.status_code==200 else "❌ Failed"})
            except Exception as e:
                results.append({"URL": url[:60]+"...", "Status": "Error", "Props Found": 0, "Result": f"❌ {str(e)[:50]}"})
        st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
    st.markdown("---")
    st.markdown("### 📊 API Health Dashboard")
    st.caption("🛡️ All APIs protected by unified budget guardian — hard stops at 80% of free tier")
    
    for key, budget in API_BUDGETS.items():
        has_key = True
        if budget.get("key"):
            has_key = bool(st.secrets.get(budget["key"], ""))
        
        key_status = "🟢 No key needed" if not budget["key"] else ("🟢 Key set" if has_key else "🔴 Key missing")
        
        usage_status = api_budget_status(key)
        
        allowed, _ = api_budget_check(key)
        gate_status = "✅ Open" if allowed else "🛑 Blocked — limit approached"
        
        with st.expander(f"{key} — {budget['description']}"):
            col_a, col_b, col_c = st.columns(3)
            col_a.markdown(f"**Key:** {key_status}")
            col_b.markdown(f"**Usage:** {usage_status}")
            col_c.markdown(f"**Gate:** {gate_status}")
            
            daily_limit = budget.get("daily_limit")
            monthly_limit = budget.get("monthly_limit")
            
            if daily_limit:
                st.caption(f"Daily limit: {daily_limit} | Hard stop at: {int(daily_limit * budget['hard_stop_pct'])}")
            if monthly_limit:
                st.caption(f"Monthly limit: {monthly_limit} | Hard stop at: {int(monthly_limit * budget['hard_stop_pct'])}")
            if not daily_limit and not monthly_limit:
                st.caption("No rate limits — free unlimited access")
    
    st.markdown("---")
    st.markdown("**Reset API Counters**")
    reset_cols = st.columns(len(API_BUDGETS))
    for idx, (key, budget) in enumerate(API_BUDGETS.items()):
        with reset_cols[idx]:
            if st.button(f"Reset {key}", key=f"reset_{key}"):
                path = budget["counter_path"]
                if os.path.exists(path):
                    os.remove(path)
                st.success(f"{key} reset")
    
    if st.button("Reset ALL API Counters"):
        for key, budget in API_BUDGETS.items():
            path = budget["counter_path"]
            if os.path.exists(path):
                os.remove(path)
        st.success("All API counters reset")
    
    st.markdown("---")
    st.markdown("**💾 Data Persistence Status**")
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        st.success("✅ GitHub Gist persistence active")
    else:
        st.error("⚠️ No persistence configured")
    st.markdown("---")
    st.markdown("**Cache Management**")
    cache_cols = st.columns(3)
    with cache_cols[0]:
        if st.button("Clear NBA Cache"):
            for f in ["nba_rolling_avgs.pkl", "nba_team_defense.pkl"]:
                p = os.path.join(CACHE_DIR, f)
                if os.path.exists(p):
                    os.remove(p)
            st.success("NBA cache cleared")
    with cache_cols[1]:
        if st.button("Clear All Rolling Caches"):
            for f in os.listdir(CACHE_DIR):
                if f.endswith("_rolling_avgs.pkl") or f.endswith("_team_defense.pkl"):
                    os.remove(os.path.join(CACHE_DIR, f))
            st.success("All rolling caches cleared")
    with cache_cols[2]:
        if st.button("Clear All API Counters"):
            for path in [API_SPORTS_COUNTER_PATH, SPORTMONKS_COUNTER_PATH, UNIFIED_COUNTER_PATH, ODDS_API_COUNTER_PATH, BDL_COUNTER_PATH, ODDSPAPI_COUNTER_PATH, PARLAYPLAY_COUNTER_PATH, BDL_PROPS_COUNTER_PATH]:
                if os.path.exists(path):
                    os.remove(path)
            for budget in API_BUDGETS.values():
                path = budget["counter_path"]
                if os.path.exists(path):
                    os.remove(path)
            st.success("API counters reset")
    st.markdown("---")
    st.markdown("**⚡ Session Management**")
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("🔄 Reset Session State"):
        keep = ["bankroll","history","locks","persistence_loaded","day_start_br","session_start"]
        for k in list(st.session_state.keys()):
            if k not in keep:
                del st.session_state[k]
        st.success("Session reset")
        st.rerun()
    if col_s2.button("🧹 Clean Old Cache Files"):
        cleaned = 0
        cutoff = time.time() - (7*24*3600)
        keep_files = ["history.json","locks.json","bankroll.json","calibration.json","line_movement.json","clv_tracking.json"]
        for f in os.listdir(CACHE_DIR):
            fp = os.path.join(CACHE_DIR, f)
            if os.path.isfile(fp) and f not in keep_files and os.path.getmtime(fp) < cutoff:
                os.remove(fp)
                cleaned += 1
        st.success(f"Cleaned {cleaned} old files")
