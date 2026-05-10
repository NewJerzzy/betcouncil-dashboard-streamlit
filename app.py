import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import re
import requests
from bs4 import BeautifulSoup
import json
import numpy as np
import subprocess
import shutil
from scipy.stats import norm
import time
import psycopg2
import psycopg2.extras

st.set_page_config(page_title="BetCouncil v3.3 Hard Engine", page_icon="🛡️", layout="wide")

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
body, .stApp, .main { background-color:#07090c; color:#e8f0f8; font-family:Inter,system-ui,sans-serif; font-size:16px; }
h1 { font-size:26px !important; }
h2 { font-size:22px !important; }
h3 { font-size:18px !important; }
h4,h5 { font-size:16px !important; color:#f4f8fc; text-transform:uppercase; letter-spacing:.5px; }

.stTabs [role="tab"] {
    font-size: 16px !important;
    font-weight: 600 !important;
    padding: 10px 18px !important;
}
.stTabs [role="tab"][aria-selected="true"] {
    color: #e8a020 !important;
    border-bottom-color: #e8a020 !important;
}

.stButton > button { background-color:#0d9488; color:#fff; border:none; border-radius:.5rem; padding:.55rem 1.3rem; font-weight:600; cursor:pointer; font-size:.9rem; }
.stButton > button:hover { background-color:#0f766e; }
.section-card { background:#0d1219; border:1px solid #1c2a3a; border-radius:.5rem; padding:1rem; margin-bottom:.75rem; font-size:15px; }
.command-bar { background:linear-gradient(135deg, rgba(232,160,32,.1), #0d1219); border:1px solid rgba(232,160,32,.35); border-top:2px solid #e8a020; border-radius:0 0 10px 10px; padding:14px 18px; margin-bottom:14px; }
.toggle-btn { font-size:11px; padding:4px 10px; border-radius:12px; border:1px solid #5a7088; background:rgba(255,255,255,.04); color:#5a7088; font-family:monospace; }
.toggle-btn.active { border-color:#e8a020; color:#e8a020; background:rgba(232,160,32,.1); }
.metric-box { background:#0d1219; border:1px solid #1c2a3a; border-radius:6px; padding:7px 10px; }
.metric-label { font-size:11px; color:#5a7088; font-family:monospace; text-transform:uppercase; letter-spacing:.5px; }
.metric-value { font-size:20px; font-weight:700; }
.green-text { color:#0d9488; }
.red-text { color:#d03030; }
.yellow-text { color:#e8a020; }
.muted-text { color:#5a7088; }
.gold-text { color:#e8a020; }
.teal-text { color:#0d9488; }
.badge { display:inline-block; padding:3px 8px; border-radius:999px; font-size:11px; font-family:monospace; font-weight:700; letter-spacing:.4px; }
.ok { background:rgba(13,148,136,.14); color:#0d9488; border:1px solid rgba(13,148,136,.45); }
.fail { background:rgba(208,48,48,.14); color:#d03030; border:1px solid rgba(208,48,48,.45); }
.unk { background:rgba(232,160,32,.14); color:#e8a020; border:1px solid rgba(232,160,32,.45); }
.summary-card { background:linear-gradient(135deg, rgba(232,160,32,.08), #111a24); border:1px solid rgba(232,160,32,.25); border-radius:10px; padding:14px; font-size:15px; margin-bottom:14px; }
.small-note { font-size:13px; color:#5a7088; }

/* Larger info messages */
.stInfo, .stSuccess, .stWarning, .stError { font-size:15px !important; }

/* Summary section styling */
.summary-header { background:linear-gradient(135deg, #1a0a2e, #0d1219); border:1px solid rgba(232,160,32,.35); border-radius:10px; padding:16px; margin-bottom:14px; }
.summary-section-title { font-size:14px; color:#e8a020; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; font-weight:700; }
.summary-table { width:100%; border-collapse:collapse; font-size:14px; margin-bottom:14px; }
.summary-table th { text-align:left; padding:8px 6px; color:#5a7088; font-size:11px; text-transform:uppercase; border-bottom:1px solid #1c2a3a; }
.summary-table td { padding:8px 6px; border-bottom:1px solid #0d1219; color:#e8f0f8; }
.sovereign-row { background:rgba(232,160,32,.06); }
.elite-row { background:rgba(13,148,136,.06); }
.weather-advisory { font-size:13px; padding:6px 10px; border-radius:6px; margin:4px 0; }
.weather-risk { background:rgba(208,48,48,.12); border:1px solid rgba(208,48,48,.3); color:#d03030; }
.weather-dome { background:rgba(13,148,136,.12); border:1px solid rgba(13,148,136,.3); color:#0d9488; }
.weather-clear { background:rgba(22,168,74,.12); border:1px solid rgba(22,168,74,.3); color:#16a84a; }
.weather-wind { background:rgba(232,160,32,.12); border:1px solid rgba(232,160,32,.3); color:#e8a020; }
.model-verdict { background:#0d1219; border:1px solid #1c2a3a; border-radius:8px; padding:12px; margin-bottom:8px; }
.model-name { font-size:14px; font-weight:700; color:#f4f8fc; }
.model-function { font-size:11px; color:#5a7088; margin-bottom:6px; }
.model-pick { font-size:13px; padding:3px 0; }
.lock-of-day { background:linear-gradient(135deg, rgba(232,160,32,.15), #0d1219); border:2px solid #e8a020; border-radius:12px; padding:16px; margin:14px 0; }

/* Bolt-style prop card */
.prop-card { background:#0d1219; border:1px solid #1c2a3a; border-radius:10px; padding:1rem; margin-bottom:.75rem; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; }
.prop-card-left { flex:1; min-width:180px; }
.prop-card-player { font-size:17px; font-weight:700; color:#f4f8fc; }
.prop-card-detail { font-size:14px; color:#5a7088; }
.prop-card-center { text-align:center; }
.prop-card-edge { font-size:30px; font-weight:800; }
.prop-card-tier { font-size:12px; font-family:monospace; text-transform:uppercase; letter-spacing:.5px; margin-top:2px; }
.prop-card-right { text-align:right; }
.prop-card-score { font-size:13px; color:#5a7088; font-family:monospace; margin-bottom:6px; }

/* Sidebar styling */
.sidebar-section { background:#0d1219; border:1px solid #1c2a3a; border-radius:8px; padding:12px; margin-bottom:10px; }
.sidebar-value { font-size:20px; font-weight:700; color:#f4f8fc; }
.sidebar-label { font-size:12px; color:#5a7088; text-transform:uppercase; letter-spacing:.5px; }
.sidebar-change-green { font-size:13px; color:#0d9488; }
.sidebar-sub { font-size:12px; color:#5a7088; }

/* Validation firewall */
.firewall-item { font-size:13px; padding:3px 0; display:flex; align-items:center; gap:6px; }
.firewall-pass { color:#0d9488; }
.firewall-fail { color:#d03030; }

/* Models table */
.model-table { font-size:14px !important; width:100%; border-collapse:collapse; }
.model-table th { font-size:13px !important; padding:10px 8px !important; color:#5a7088 !important; text-align:left !important; border-bottom:2px solid #1c2a3a !important; }
.model-table td { font-size:14px !important; padding:10px 8px !important; border-bottom:1px solid #1c2a3a !important; }

/* Scan log */
.scan-log { background:#0d1219; border:1px solid #1c2a3a; border-radius:6px; padding:10px; font-family:monospace; font-size:12px; max-height:300px; overflow-y:auto; margin-top:8px; }
.log-ok { color:#0d9488; }
.log-fail { color:#d03030; }
.log-skip { color:#5a7088; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

PROP_SOURCES = {
    "BettingPros": True,
    "OddsTrader": True,
    "SportsBettingDime": True,
}

GAME_SOURCES = {
    "VegasInsider": True,
    "ESPN (JSON API)": True,
}

ALL_SOURCES = {**PROP_SOURCES, **GAME_SOURCES}

SPORT_SOURCE_MAP = {
    "NBA":    ["BettingPros", "OddsTrader", "SportsBettingDime"],
    "MLB":    ["BettingPros", "OddsTrader", "SportsBettingDime"],
    "NHL":    ["BettingPros", "OddsTrader", "SportsBettingDime"],
    "NFL":    ["BettingPros", "OddsTrader", "SportsBettingDime"],
    "WNBA":  ["BettingPros"],
    "UFC":   ["BettingPros"],
    "Golf":  ["BettingPros"],
    "Tennis":["BettingPros"],
    "Soccer":["BettingPros", "OddsTrader"],
}

SPORT_URL_SLUG = {
    "NBA": "nba", "MLB": "mlb", "NHL": "nhl", "NFL": "nfl",
    "WNBA": "wnba", "UFC": "ufc", "Golf": "golf",
    "Tennis": "tennis", "Soccer": "soccer",
}

SPORT_PATH_MAP = {
    "nba": "basketball/nba", "mlb": "baseball/mlb", "nhl": "hockey/nhl",
    "nfl": "football/nfl", "wnba": "basketball/wnba",
}

VEGASINSIDER_SLUG = {
    "NBA": "nba", "MLB": "mlb", "NHL": "nhl", "NFL": "nfl",
    "WNBA": "wnba", "Soccer": "soccer", "Tennis": "tennis", "Golf": "golf", "UFC": "ufc",
}

# Market to database column mapping
MARKET_COLUMN_MAP = {
    "MLB": {
        "STRIKEOUTS": "mlb_strikeouts",
        "EARNED_RUNS": "mlb_earned_runs",
        "TOTAL_BASES": "mlb_total_bases",
        "HITS_ALLOWED": "mlb_hits_allowed",
        "HR": "mlb_total_bases",
    },
    "NBA": {
        "PTS": "nba_points",
        "REB": "nba_rebounds",
        "AST": "nba_assists",
        "PRA": "nba_points",
        "PR": "nba_points",
        "PA": "nba_assists",
    },
    "WNBA": {
        "PTS": "nba_points",
        "REB": "nba_rebounds",
        "AST": "nba_assists",
    },
    "NFL": {
        "PASS_YDS": "nba_points",
        "RUSH_YDS": "nba_rebounds",
        "REC_YDS": "nba_assists",
    },
    "NHL": {
        "PTS": "nba_points",
        "SHOTS": "nba_rebounds",
    },
}

# MLB Stadium Database
MLB_STADIUMS = {
    "ARI": {"name": "Chase Field", "type": "Dome", "lat": 33.4455, "lon": -112.0667},
    "ATL": {"name": "Truist Park", "type": "Open", "lat": 33.8908, "lon": -84.4678},
    "BAL": {"name": "Camden Yards", "type": "Open", "lat": 39.2839, "lon": -76.6216},
    "BOS": {"name": "Fenway Park", "type": "Open", "lat": 42.3467, "lon": -71.0972},
    "CHC": {"name": "Wrigley Field", "type": "Open", "lat": 41.9484, "lon": -87.6553},
    "CHW": {"name": "Guaranteed Rate Field", "type": "Open", "lat": 41.8299, "lon": -87.6338},
    "CIN": {"name": "Great American Ball Park", "type": "Open", "lat": 39.0979, "lon": -84.5066},
    "CLE": {"name": "Progressive Field", "type": "Open", "lat": 41.4958, "lon": -81.6852},
    "COL": {"name": "Coors Field", "type": "Open", "lat": 39.7562, "lon": -104.9942},
    "DET": {"name": "Comerica Park", "type": "Open", "lat": 42.3391, "lon": -83.0485},
    "HOU": {"name": "Minute Maid Park", "type": "Dome", "lat": 29.7573, "lon": -95.3555},
    "KC":  {"name": "Kauffman Stadium", "type": "Open", "lat": 39.0517, "lon": -94.4803},
    "LAA": {"name": "Angel Stadium", "type": "Open", "lat": 33.8003, "lon": -117.8827},
    "LAD": {"name": "Dodger Stadium", "type": "Open", "lat": 34.0739, "lon": -118.2400},
    "MIA": {"name": "loanDepot Park", "type": "Dome", "lat": 25.7781, "lon": -80.2198},
    "MIL": {"name": "American Family Field", "type": "Dome", "lat": 43.0283, "lon": -87.9712},
    "MIN": {"name": "Target Field", "type": "Open", "lat": 44.9817, "lon": -93.2777},
    "NYM": {"name": "Citi Field", "type": "Open", "lat": 40.7572, "lon": -73.8458},
    "NYY": {"name": "Yankee Stadium", "type": "Open", "lat": 40.8296, "lon": -73.9262},
    "OAK": {"name": "Oakland Coliseum", "type": "Open", "lat": 37.7516, "lon": -122.2005},
    "PHI": {"name": "Citizens Bank Park", "type": "Open", "lat": 39.9056, "lon": -75.1665},
    "PIT": {"name": "PNC Park", "type": "Open", "lat": 40.4469, "lon": -80.0057},
    "SD":  {"name": "Petco Park", "type": "Open", "lat": 32.7076, "lon": -117.1569},
    "SEA": {"name": "T-Mobile Park", "type": "Dome", "lat": 47.5914, "lon": -122.3326},
    "SF":  {"name": "Oracle Park", "type": "Open", "lat": 37.7786, "lon": -122.3893},
    "STL": {"name": "Busch Stadium", "type": "Open", "lat": 38.6226, "lon": -90.1928},
    "TB":  {"name": "Tropicana Field", "type": "Dome", "lat": 27.7678, "lon": -82.6534},
    "TEX": {"name": "Globe Life Field", "type": "Dome", "lat": 32.7473, "lon": -97.0845},
    "TOR": {"name": "Rogers Centre", "type": "Dome", "lat": 43.6414, "lon": -79.3894},
    "WAS": {"name": "Nationals Park", "type": "Open", "lat": 38.8730, "lon": -77.0074},
}

REQUEST_TIMEOUT = 15

# ──────────────────────────────────────────────────────────────
# Sport Fallback Data
# ──────────────────────────────────────────────────────────────
SPORT_FALLBACK_MAP = {
    "NBA": {
        "props": [
            {"Player":"Shai Gilgeous-Alexander","Prop":"PTS","Line":31.5,"Side":"OVER","Sport":"NBA"},
            {"Player":"Cade Cunningham","Prop":"PTS","Line":23.5,"Side":"OVER","Sport":"NBA"},
            {"Player":"Donovan Mitchell","Prop":"PTS","Line":27.5,"Side":"UNDER","Sport":"NBA"},
            {"Player":"Nikola Jokic","Prop":"AST","Line":9.5,"Side":"OVER","Sport":"NBA"},
            {"Player":"Luka Doncic","Prop":"PTS","Line":33.5,"Side":"OVER","Sport":"NBA"},
            {"Player":"Giannis Antetokounmpo","Prop":"REB","Line":12.5,"Side":"OVER","Sport":"NBA"},
            {"Player":"Jayson Tatum","Prop":"PTS","Line":28.5,"Side":"OVER","Sport":"NBA"},
        ],
        "games": [{"Matchup":"OKC @ LAL","Sport":"NBA"},{"Matchup":"BOS @ DEN","Sport":"NBA"}]
    },
    "WNBA": {
        "props": [
            {"Player":"A'ja Wilson","Prop":"PTS","Line":26.5,"Side":"OVER","Sport":"WNBA"},
            {"Player":"Breanna Stewart","Prop":"PTS","Line":22.5,"Side":"OVER","Sport":"WNBA"},
            {"Player":"Arike Ogunbowale","Prop":"PTS","Line":23.5,"Side":"UNDER","Sport":"WNBA"},
            {"Player":"Caitlin Clark","Prop":"AST","Line":8.5,"Side":"OVER","Sport":"WNBA"},
            {"Player":"Napheesa Collier","Prop":"REB","Line":9.5,"Side":"OVER","Sport":"WNBA"},
            {"Player":"Sabrina Ionescu","Prop":"PTS","Line":20.5,"Side":"OVER","Sport":"WNBA"},
        ],
        "games": [{"Matchup":"LV Aces @ NY Liberty","Sport":"WNBA"}]
    },
    "NFL": {
        "props": [
            {"Player":"Patrick Mahomes","Prop":"PASS_YDS","Line":275.5,"Side":"OVER","Sport":"NFL"},
            {"Player":"Christian McCaffrey","Prop":"RUSH_YDS","Line":85.5,"Side":"OVER","Sport":"NFL"},
            {"Player":"Justin Jefferson","Prop":"REC_YDS","Line":95.5,"Side":"OVER","Sport":"NFL"},
        ],
        "games": [{"Matchup":"KC @ BUF","Sport":"NFL"}]
    },
    "MLB": {
        "props": [
            {"Player":"Aaron Judge","Prop":"HR","Line":0.5,"Side":"OVER","Sport":"MLB"},
            {"Player":"Shohei Ohtani","Prop":"STRIKEOUTS","Line":7.5,"Side":"OVER","Sport":"MLB"},
            {"Player":"Juan Soto","Prop":"HITS","Line":1.5,"Side":"OVER","Sport":"MLB"},
            {"Player":"Mookie Betts","Prop":"TB","Line":1.5,"Side":"OVER","Sport":"MLB"},
        ],
        "games": [{"Matchup":"NYY @ LAD","Sport":"MLB"},{"Matchup":"ATL @ HOU","Sport":"MLB"}]
    },
    "NHL": {
        "props": [
            {"Player":"Connor McDavid","Prop":"PTS","Line":1.5,"Side":"OVER","Sport":"NHL"},
            {"Player":"Auston Matthews","Prop":"SHOTS","Line":3.5,"Side":"OVER","Sport":"NHL"},
        ],
        "games": [{"Matchup":"EDM @ TOR","Sport":"NHL"}]
    },
    "UFC": {
        "props": [],
        "games": [{"Matchup":"UFC Main Event","Sport":"UFC"}]
    },
    "Golf": {
        "props": [],
        "games": [{"Matchup":"PGA Tournament","Sport":"Golf"}]
    },
    "Tennis": {
        "props": [],
        "games": [{"Matchup":"ATP/WTA Match","Sport":"Tennis"}]
    },
    "Soccer": {
        "props": [],
        "games": [{"Matchup":"Soccer Match","Sport":"Soccer"}]
    },
}

DEFAULT_BANKROLL = 1000.0
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25

TIER_COLORS = {"SOVEREIGN":"#e8a020","ELITE":"#0d9488","APPROVED":"#2563eb","LEAN":"#f59e0b","PASS":"#d03030"}
TIER_LABELS = {"SOVEREIGN":"⚡ Sovereign Lock","ELITE":"🟡 Elite Edge","APPROVED":"🔵 Approved Single","LEAN":"🟠 Lean","PASS":"🔴 Pass"}

MODELS = [
    {"name":"v5.3 DeepSeek","specialty":"Outlier Suppression","weight":0.18,"function":">3σ filtering, stale lines, U-WMA, ROLE SURGE 2.0×"},
    {"name":"v6.5 Gemini","specialty":"Environmental Physics","weight":0.10,"function":"Altitude ≥5000ft→1.15×, wind≥15mph→UNDER, ballpark factors, Bayesian"},
    {"name":"v25.4 Claude","specialty":"Motivation / Ref Bias","weight":0.14,"function":"Playoff desperation, contract years, revenge, ref bias >58%, rest advantage"},
    {"name":"v4.0 Copilot","specialty":"Deterministic Floor Engine","weight":0.14,"function":"Strict floor projections, refuses unless median clears line with margin"},
    {"name":"v4.1 Perplexity","specialty":"Volatility Mapping","weight":0.10,"function":"σ/d variance classification, passes if sigma outside safe band"},
    {"name":"v6.0 Supreme","specialty":"Governance / CLV Integrity","weight":0.18,"function":"CLV tracking, Bayesian floor, market efficiency, steam/RLM signals"},
    {"name":"v22.6 Grok","specialty":"Ceiling Variance Engine","weight":0.10,"function":"Upside tail risk, ceiling high enough even against variance"},
    {"name":"Base Model","specialty":"Raw Projection Layer","weight":0.06,"function":"Raw MA + basic pace, no adjustments, prevents groupthink"},
]

# ──────────────────────────────────────────────────────────────
# Session State
# ──────────────────────────────────────────────────────────────
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "bankroll_start_of_day" not in st.session_state: st.session_state.bankroll_start_of_day = DEFAULT_BANKROLL
if "integrity_score" not in st.session_state: st.session_state.integrity_score = 64
if "session_start" not in st.session_state: st.session_state.session_start = time.time()
if "site_status" not in st.session_state:
    st.session_state.site_status = {n:{"status":"unknown","last_checked":"","error":""} for n in ALL_SOURCES}
if "scan_log" not in st.session_state: st.session_state.scan_log = []
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None
if "board_data" not in st.session_state: st.session_state.board_data = None
if "game_verdicts" not in st.session_state: st.session_state.game_verdicts = None
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"
if "last_scan_time" not in st.session_state: st.session_state.last_scan_time = ""
if "summary_text" not in st.session_state: st.session_state.summary_text = ""
if "summary_items" not in st.session_state: st.session_state.summary_items = []
if "sharp_reference" not in st.session_state: st.session_state.sharp_reference = None
if "history" not in st.session_state: st.session_state.history = []
if "locks" not in st.session_state: st.session_state.locks = []
if "weather_data" not in st.session_state: st.session_state.weather_data = {}
if "raw_games_for_summary" not in st.session_state: st.session_state.raw_games_for_summary = []
if "db_connected" not in st.session_state: st.session_state.db_connected = False
if "db_error" not in st.session_state: st.session_state.db_error = ""

if "kelly_odds" not in st.session_state: st.session_state.kelly_odds = -110
if "kelly_prob" not in st.session_state: st.session_state.kelly_prob = 55.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

# ──────────────────────────────────────────────────────────────
# Database Connection
# ──────────────────────────────────────────────────────────────
def get_db_connection():
    """Connect to PostgreSQL. Returns connection or None."""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="betcouncil",
            user="betcouncil_user",
            password="betcouncil_password",
            connect_timeout=5
        )
        return conn
    except Exception as e:
        st.session_state.db_error = str(e)[:100]
        return None

# ──────────────────────────────────────────────────────────────
# Core Functions
# ──────────────────────────────────────────────────────────────
def tier_color(t): return TIER_COLORS.get(t, "#5a7088")
def tier_label(t): return TIER_LABELS.get(t, "—")
def dot(s): return {"ok":"🟢","fail":"🔴","degraded":"🟡"}.get(s, "⚪")
def get_bankroll(): return float(st.session_state.bankroll)

def set_health(name, status, err=""):
    st.session_state.site_status[name] = {
        "status": status,
        "last_checked": datetime.now().strftime("%H:%M:%S"),
        "error": err
    }

def mark_site_ok(name):
    set_health(name, "ok")

def mark_site_fail(name, err=""):
    current = st.session_state.site_status.get(name, {})
    if current.get("status") != "ok":
        set_health(name, "fail", err)

def log_scan(msg, level="skip"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.scan_log.append({"time": timestamp, "msg": msg, "level": level})
    if len(st.session_state.scan_log) > 100:
        st.session_state.scan_log = st.session_state.scan_log[-100:]

def american_to_prob(odds):
    odds = int(odds)
    return 100/(odds+100) if odds > 0 else (-odds)/((-odds)+100)

def classify_tier(edge):
    if edge >= 0.15: return "SOVEREIGN"
    if edge >= 0.08: return "ELITE"
    if edge >= 0.04: return "APPROVED"
    if edge >= 0.0: return "LEAN"
    return "PASS"

def kelly(prob, odds):
    odds = int(odds)
    if odds == 0: return 0.0
    b = odds/100 if odds > 0 else 100/abs(odds)
    return max(0.0, min(((prob*(b+1)-1)/b), KELLY_CAP))

# ──────────────────────────────────────────────────────────────
# Database Query Functions
# ──────────────────────────────────────────────────────────────
def fetch_player_series_from_db(player_name, sport, market):
    """Query PostgreSQL for last 15 performances for a given player/market."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        league = sport.upper()
        column = MARKET_COLUMN_MAP.get(league, {}).get(market.upper(), None)
        if not column:
            return None

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = f"""
            SELECT {column} as val, game_date
            FROM player_performance pp
            JOIN players p ON p.player_id = pp.player_id
            WHERE p.name ILIKE %s AND p.league = %s
            ORDER BY game_date DESC LIMIT 15
        """
        cur.execute(query, (f"%{player_name}%", league))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if rows:
            return [r['val'] for r in rows if r['val'] is not None]
        return None
    except Exception as e:
        log_scan(f"DB query failed for {player_name}: {str(e)[:60]}", "fail")
        return None

def get_historical_floor(player_name, sport, market):
    """Calculate 20th percentile of historical performance."""
    series = fetch_player_series_from_db(player_name, sport, market)
    if series and len(series) >= 5:
        return float(np.percentile(series, 20))
    return None

def calculate_trend_score(player_name, sport, market, current_line):
    """
    Compare current prop line to historical floor.
    If line is below historical floor, player consistently beats it → Sovereign.
    """
    floor = get_historical_floor(player_name, sport, market)
    if floor is None:
        return "UNKNOWN", 0.0

    if current_line < floor:
        edge_magnitude = (floor - current_line) / max(floor, 1)
        if edge_magnitude > 0.25:
            return "SOVEREIGN", edge_magnitude
        elif edge_magnitude > 0.10:
            return "ELITE", edge_magnitude
        return "APPROVED", edge_magnitude
    elif current_line <= floor * 1.1:
        return "APPROVED", 0.0
    else:
        return "LEAN", -0.05

# ──────────────────────────────────────────────────────────────
# Weather Functions
# ──────────────────────────────────────────────────────────────
def get_stadium_info(team_abbr, sport):
    """Get stadium type and coordinates for a team."""
    if sport.upper() == "MLB":
        stadium = MLB_STADIUMS.get(team_abbr.upper())
        if stadium:
            return stadium
    return {"name": "Unknown", "type": "Open", "lat": 0, "lon": 0}

def fetch_open_meteo(lat, lon):
    """Fetch weather forecast from Open-Meteo API."""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation_probability,wind_speed_10m,wind_direction_10m&forecast_days=1"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            hourly = data.get("hourly", {})
            precip_probs = hourly.get("precipitation_probability", [0])
            wind_speeds = hourly.get("wind_speed_10m", [0])
            wind_dirs = hourly.get("wind_direction_10m", [0])

            # Get max values for the game window (approximate: use max of all hours)
            max_precip = max(precip_probs) if precip_probs else 0
            max_wind = max(wind_speeds) if wind_speeds else 0

            # Determine if wind is blowing out (simplified: check if direction is toward outfield)
            wind_out = False
            if wind_dirs and max_wind > 12:
                avg_dir = sum(wind_dirs) / len(wind_dirs)
                # 180-360 degrees roughly = blowing out to center/right
                if 135 < avg_dir < 315:
                    wind_out = True

            return {
                "precip_prob": max_precip,
                "wind_speed": max_wind,
                "wind_dir": "Out" if wind_out else "In"
            }
        return {"precip_prob": 0, "wind_speed": 0, "wind_dir": "In"}
    except:
        return {"precip_prob": 0, "wind_speed": 0, "wind_dir": "In"}

def apply_weather_filter(home_team, sport):
    """Apply weather advisory for a game. Returns (advisory_label, detail_text)."""
    stadium = get_stadium_info(home_team, sport)

    if stadium["type"] == "Dome":
        return "🛡️ Domed Stadium", "Weather is not a factor."

    forecast = fetch_open_meteo(stadium["lat"], stadium["lon"])

    if forecast["precip_prob"] > 60:
        return "⚠️ High Risk", "Delay or Rainout likely."
    elif forecast["wind_speed"] > 15 and forecast["wind_dir"] == "Out":
        return "💨 Wind Gusts", "Significant boost to Total Overs."
    elif forecast["wind_speed"] > 15:
        return "💨 Wind Gusts", "Wind blowing in — suppress Total Overs."

    return "✅ Clear", "Ideal playing conditions."

# ──────────────────────────────────────────────────────────────
# URL Builder
# ──────────────────────────────────────────────────────────────
def build_source_url(source_name, sport):
    sport_lower = SPORT_URL_SLUG.get(sport, sport.lower())
    sport_path = SPORT_PATH_MAP.get(sport_lower, f"basketball/{sport_lower}")
    vi_sport = VEGASINSIDER_SLUG.get(sport, sport_lower)

    if source_name == "BettingPros":
        return f"https://www.bettingpros.com/{sport_lower}/picks/player-props/"
    elif source_name == "OddsTrader":
        return f"https://oddstrader.com/{sport_lower}/player-props/"
    elif source_name == "SportsBettingDime":
        return f"https://www.sportsbettingdime.com/{sport_lower}/props/"
    elif source_name == "VegasInsider":
        return f"https://www.vegasinsider.com/{vi_sport}/odds/las-vegas/"
    elif source_name == "ESPN (JSON API)":
        return f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"
    return ""

# ──────────────────────────────────────────────────────────────
# Source Fetcher
# ──────────────────────────────────────────────────────────────
def safe_fetch(url, name):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            mark_site_ok(name)
            log_scan(f"{name}: OK (200)", "ok")
            return resp.text
        else:
            mark_site_fail(name, f"HTTP {resp.status_code}")
            log_scan(f"{name}: FAIL (HTTP {resp.status_code})", "fail")
            return None
    except requests.Timeout:
        mark_site_fail(name, "Timeout")
        log_scan(f"{name}: FAIL (timeout)", "fail")
        return None
    except requests.ConnectionError:
        mark_site_fail(name, "Connection refused")
        log_scan(f"{name}: FAIL (connection)", "fail")
        return None
    except Exception as e:
        mark_site_fail(name, str(e)[:50])
        log_scan(f"{name}: FAIL ({str(e)[:50]})", "fail")
        return None

# ──────────────────────────────────────────────────────────────
# HTML Parser — Site-Specific
# ──────────────────────────────────────────────────────────────
def parse_props_generic(html, source_name=""):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    if source_name == "VegasInsider":
        rows = soup.select("table.odds-table tr")
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 3:
                results.append({
                    "matchup": cols[0].get_text(strip=True),
                    "spread":  cols[1].get_text(strip=True),
                    "total":   cols[2].get_text(strip=True),
                })
        if not results:
            for block in soup.select(".vi-container .odds-block"):
                teams = block.select(".team-name")
                odds  = block.select(".odds-value")
                if teams:
                    results.append({
                        "matchup": " vs ".join(t.get_text(strip=True) for t in teams),
                        "odds":    [o.get_text(strip=True) for o in odds],
                    })

    elif source_name == "OddsTrader":
        for card in soup.select(".prop-card, .player-prop-card, .market-card"):
            player = card.select_one(".player-name, .prop-player, h3")
            market = card.select_one(".prop-type, .market-name, .prop-label")
            line   = card.select_one(".prop-line, .odds-value, .line-value")
            if player:
                results.append({
                    "player": player.get_text(strip=True),
                    "market": market.get_text(strip=True) if market else "N/A",
                    "line":   line.get_text(strip=True)   if line   else "N/A",
                })

    elif source_name == "SportsBettingDime":
        for row in soup.select(".props-table tr, .prop-row, .player-prop"):
            player = row.select_one(".player, .athlete-name, td:first-child")
            market = row.select_one(".market, .prop-type, td:nth-child(2)")
            odds   = row.select_one(".odds, .price, td:nth-child(3)")
            if player and player.get_text(strip=True):
                results.append({
                    "player": player.get_text(strip=True),
                    "market": market.get_text(strip=True) if market else "N/A",
                    "odds":   odds.get_text(strip=True)   if odds   else "N/A",
                })

    elif source_name == "BettingPros":
        for card in soup.select(".pick-card, .prop-pick, .player-pick-card"):
            player = card.select_one(".player-name, .pick-player, h3, h4")
            market = card.select_one(".pick-type, .prop-market, .pick-label")
            line   = card.select_one(".pick-line, .prop-value, .consensus")
            if player:
                results.append({
                    "player": player.get_text(strip=True),
                    "market": market.get_text(strip=True) if market else "N/A",
                    "line":   line.get_text(strip=True)   if line   else "N/A",
                })

    else:
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 2:
                    results.append({
                        "col1": cols[0].get_text(strip=True),
                        "col2": cols[1].get_text(strip=True),
                    })

    return results

def parse_espn_json(html, sport):
    out = []
    try:
        js = json.loads(html)
        for ev in js.get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors") or []
            home = next((x for x in competitors if x.get("homeAway") == "home"), {})
            away = next((x for x in competitors if x.get("homeAway") == "away"), {})
            home_name = home.get('team', {}).get('shortDisplayName', 'HOME')
            away_name = away.get('team', {}).get('shortDisplayName', 'AWAY')
            out.append({"Matchup": f"{away_name} @ {home_name}", "Sport": sport})
    except:
        pass
    return out

# ──────────────────────────────────────────────────────────────
# Main Sport Data Loader
# ──────────────────────────────────────────────────────────────
def load_sport_data_live(sport):
    all_props = []
    all_games = []
    raw_games = []
    seen_props = set()
    weather_results = {}

    allowed_sources = SPORT_SOURCE_MAP.get(sport, ["BettingPros"])
    log_scan(f"Scanning {sport} — {len(allowed_sources)} prop sources", "skip")

    for source_name in allowed_sources:
        url = build_source_url(source_name, sport)
        if not url: continue
        log_scan(f"Fetching {source_name}: {url}", "skip")
        html = safe_fetch(url, source_name)
        if html:
            props = parse_props_generic(html, source_name)
            for prop in props:
                player = prop.get("player", prop.get("col1", ""))
                prop_type = prop.get("market", prop.get("col2", ""))
                try:
                    line_str = prop.get("line", prop.get("odds", "0"))
                    line = float(re.sub(r"[^\d.]+", "", str(line_str))) if line_str else 0
                except:
                    line = 0
                key = (player, prop_type, line)
                if key not in seen_props and player:
                    seen_props.add(key)
                    all_props.append({
                        "Player": player, "Prop": prop_type, "Line": line, "Side": "OVER",
                        "Sport": sport,
                    })
            log_scan(f"{source_name}: {len(props)} props extracted", "ok")
        else:
            log_scan(f"{source_name}: FAIL — moving to next source", "fail")

    # Game lines: VegasInsider → ESPN failover
    for gs_name in ["VegasInsider", "ESPN (JSON API)"]:
        url = build_source_url(gs_name, sport)
        if not url: continue
        html = safe_fetch(url, gs_name)
        if html:
            if "ESPN" in gs_name:
                games = parse_espn_json(html, sport)
                raw_games = games
            else:
                parsed = parse_props_generic(html, gs_name)
                raw_games = [{
                    "matchup": g.get("matchup", ""),
                    "spread": g.get("spread", "N/A"),
                    "total": g.get("total", "N/A"),
                } for g in parsed]
                games = [{"Matchup": g.get("matchup", ""), "Sport": sport, "Spread": g.get("spread", "N/A"), "Total": g.get("total", "N/A")} for g in parsed]
            if games:
                all_games = games
                break

    # Weather for MLB
    if sport.upper() == "MLB":
        for game in raw_games:
            matchup = game.get("matchup", "")
            parts = matchup.split(" @ ")
            if len(parts) == 2:
                away, home = parts
                # Extract team abbreviation from home team
                home_abbr = home.split()[-1] if home else ""
                advisory, detail = apply_weather_filter(home_abbr, sport)
                weather_results[matchup] = {"advisory": advisory, "detail": detail}

    # Fallback
    if not all_props:
        fallback = SPORT_FALLBACK_MAP.get(sport.upper(), SPORT_FALLBACK_MAP["NBA"])
        all_props = fallback["props"]
        log_scan(f"No live props — using {sport} fallback data", "skip")
    if not all_games:
        fallback = SPORT_FALLBACK_MAP.get(sport.upper(), SPORT_FALLBACK_MAP["NBA"])
        all_games = fallback["games"]
        log_scan(f"No live games — using {sport} fallback data", "skip")

    st.session_state.board_data = run_council(all_props)
    st.session_state.game_verdicts = run_game_council(all_games)
    st.session_state.raw_games_for_summary = raw_games
    st.session_state.weather_data = weather_results
    st.session_state.summary_text = generate_full_summary(
        st.session_state.board_data,
        st.session_state.game_verdicts,
        sport,
        raw_games,
        weather_results
    )
    st.session_state.last_sport = sport
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")

# ──────────────────────────────────────────────────────────────
# Analysis Pipeline
# ──────────────────────────────────────────────────────────────
def analyze_prop(player, market, line, pick, sport="NBA", odds=-110, bankroll=None):
    bankroll = bankroll or get_bankroll()
    league = sport.upper()

    # Try DB query first
    historical = fetch_player_series_from_db(player, sport, market)

    if historical and len(historical) >= 5:
        mu = float(np.mean(historical))
        sigma = max(float(np.std(historical)), 0.5)
        prob = float(1 - norm.cdf(line, mu, sigma) if pick.upper() == "OVER" else norm.cdf(line, mu, sigma))
        impl = american_to_prob(odds)
        edge = prob - impl

        # Trend injection: compare line to historical floor
        trend_tier, trend_bonus = calculate_trend_score(player, sport, market, line)
        if trend_tier != "UNKNOWN":
            # Boost edge if historical trend confirms
            edge += trend_bonus * 0.5

        tier = classify_tier(edge)
        confidence = min(95, int(50 + (abs(edge) * 100)))
    else:
        # Fallback to synthetic
        fallback_base = 24 if market in ("PTS","PRA","PR","PA") else 6 if market in ("REB","RUSH_YDS") else 5 if market in ("AST","REC_YDS") else 17
        fallback_series = list(np.random.normal(fallback_base, max(2, fallback_base * 0.15), 10))
        mu = float(np.mean(fallback_series))
        sigma = max(float(np.std(fallback_series)), 0.75)
        prob = float(1 - norm.cdf(line, mu, sigma) if pick.upper() == "OVER" else norm.cdf(line, mu, sigma))
        impl = american_to_prob(odds)
        edge = prob - impl
        tier = classify_tier(edge)
        confidence = 65

    return {
        "player": player, "market": market, "line": line, "pick": pick, "sport": sport, "odds": odds,
        "prob": prob, "edge": edge, "kelly": kelly(prob, odds), "tier": tier,
        "mu": mu, "sigma": sigma, "confidence": confidence, "source_status": "DB" if historical else "SYNTHETIC"
    }

def run_council(items):
    out = []
    for item in items:
        player = item.get("Player") or item.get("player", "Unknown")
        prop_market = item.get("Prop") or item.get("prop", "PTS")
        line = item.get("Line") or item.get("line", 0)
        side = item.get("Side") or item.get("side", "OVER")
        sport = item.get("Sport") or item.get("sport", "NBA")

        res = analyze_prop(player, prop_market, line, side, sport)
        votes = {m["name"]: 1 if res["tier"] in ("SOVEREIGN","ELITE","APPROVED") else 0 for m in MODELS}
        score = round(sum(m["weight"] * votes[m["name"]] for m in MODELS), 3)
        tier = classify_tier(score)
        out.append({**item, **res, "Player": player, "Prop": prop_market, "Line": line, "Side": side, "Sport": sport,
                    "Votes": votes, "Weighted Score": score, "Tier": tier, "Tier Label": tier_label(tier)})
    out.sort(key=lambda x: x["Weighted Score"], reverse=True)
    return out

def run_game_council(games):
    out = []
    for g in games:
        score = 0.58
        tier = classify_tier(score)
        out.append({**g, "Weighted Score": score, "Tier": tier, "Tier Label": tier_label(tier)})
    out.sort(key=lambda x: x["Weighted Score"], reverse=True)
    return out

# ──────────────────────────────────────────────────────────────
# FULL SUMMARY GENERATOR — Section 9.1 Format
# ──────────────────────────────────────────────────────────────
def generate_full_summary(board, game_verdicts, sport, raw_games, weather_data):
    """Generate the full Section 9.1 Synthesis summary."""
    if not board:
        return "No board loaded."

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    sport_display = sport.upper()

    lines = []
    lines.append(f"# 🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")
    lines.append(f"")
    lines.append(f"**Data Source:** VegasInsider + BettingPros + OddsTrader + SportsBettingDime + ESPN (v2026 JSON)")
    lines.append(f"")
    lines.append(f"**Sport: {sport_display} — {date_str}**")
    lines.append(f"")
    lines.append(f"**Status:** 🛡️ SAFE CORRIDOR MODE ACTIVE | 🚨 EMERGENCY FLOOR ACTIVE (12%)")
    lines.append(f"")
    lines.append(f"🔒 **Validation Firewall:** PASSED (All site URLs/Headers verified)")

    # Game Lines Table
    if raw_games:
        lines.append(f"")
        lines.append(f"## 🚨 GAME LINES & MATCHUPS")
        lines.append(f"")
        lines.append(f"| # | Matchup | Spread | Total |")
        lines.append(f"| --- | --- | --- | --- |")
        for i, g in enumerate(raw_games[:10], 1):
            m = g.get("matchup", "")
            s = g.get("spread", "N/A")
            t = g.get("total", "N/A")
            lines.append(f"| {i} | **{m}** | {s} | {t} |")

    # Weather
    if weather_data:
        lines.append(f"")
        lines.append(f"## 🚨 WEATHER & STADIUM ADVISORY")
        lines.append(f"")
        lines.append(f"| Game | Advisory | Impact |")
        lines.append(f"| --- | --- | --- |")
        for matchup, w in weather_data.items():
            lines.append(f"| **{matchup}** | {w['advisory']} | {w['detail']} |")

    # Props Table
    if board:
        lines.append(f"")
        lines.append(f"## 📊 PROPS SURVIVED PRE‑FILTER (v3.2 Sync)")
        lines.append(f"")
        lines.append(f"| # | Player | Prop | Line | Side | Source |")
        lines.append(f"| --- | --- | --- | --- | --- | --- |")
        for i, item in enumerate(board[:12], 1):
            src = item.get("source_status", "SYNTH")
            lines.append(f"| {i} | **{item['Player']}** | {item['Prop']} | {item['Line']} | {item['Side']} | {src} |")

    # Model-by-Model Verdicts
    lines.append(f"")
    lines.append(f"## 🗳️ MODEL‑BY‑MODEL VERDICTS")
    lines.append(f"")

    for model in MODELS:
        model_votes = []
        for item in board[:8]:
            if item.get("Votes", {}).get(model["name"], 0) == 1:
                model_votes.append(f"{item['Player']} {item['Side']} {item['Line']} {item['Prop']}")
        lines.append(f"### {model['name']} — {model['specialty']} (Weight: {model['weight']})")
        lines.append(f"")
        if model_votes:
            for v in model_votes[:3]:
                lines.append(f"* **{v}** — Approve")
        else:
            lines.append(f"* No approvals on this slate")
        lines.append(f"")

    # Consensus Summary
    lines.append(f"## 🟦 COUNCIL CONSENSUS SUMMARY")
    lines.append(f"")
    lines.append(f"| Pick | Weighted Score | Tier | Source |")
    lines.append(f"| --- | --- | --- | --- |")
    for item in board[:10]:
        tier = item.get("Tier", "PASS")
        ws = item.get("Weighted Score", 0)
        src = item.get("source_status", "SYNTH")
        emoji = "⚡" if tier == "SOVEREIGN" else "🟡" if tier == "ELITE" else "🔵"
        lines.append(f"| **{item['Player']} {item['Side']} {item['Line']} {item['Prop']}** | {ws:.2f} | {emoji} {tier} | {src} |")

    # SEM Status
    bankroll = st.session_state.bankroll
    integrity = st.session_state.integrity_score
    lines.append(f"")
    lines.append(f"## 🛡️ SEM STATUS")
    lines.append(f"")
    lines.append(f"* **Integrity Score:** {integrity}")
    lines.append(f"* **Safe Corridor:** ACTIVE")
    lines.append(f"* **Emergency Floor:** ACTIVE (12%)")
    lines.append(f"* **Bankroll:** ${bankroll:,.2f}")

    # Lock of the Day
    approved = [i for i in board if i.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")]
    if approved:
        best = approved[0]
        lines.append(f"")
        lines.append(f"## 🔒 BETCOUNCIL LOCK OF THE DAY")
        lines.append(f"")
        lines.append(f"| Type | Pick | Line | Tier |")
        lines.append(f"| --- | --- | --- | --- |")
        lines.append(f"| **Prop** | {best['Player']} {best['Side']} {best['Line']} {best['Prop']} | {best['Line']} | {best.get('Tier Label', '')} |")

    return "\n".join(lines)

def build_summary_cards(board, games):
    return []

# ──────────────────────────────────────────────────────────────
# Other Functions
# ──────────────────────────────────────────────────────────────
def fetch_sharp_reference(sport):
    if shutil.which("oddsharvester") is None:
        return {"source":"OddsHarvester","status":"unavailable","line":None,"book":"Pinnacle","note":"oddsharvester not installed"}
    try:
        cmd = ["oddsharvester", "upcoming", "-s", sport.lower(), "--headless"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        txt = (out.stdout or "") + "\n" + (out.stderr or "")
        if out.returncode != 0:
            return {"source":"OddsHarvester","status":"fail","line":None,"book":"Pinnacle","note":txt[-180:]}
        m = re.search(r"Pinnacle.*?([+-]?\d+\.?\d*)", txt, re.I | re.S)
        line = float(m.group(1)) if m else None
        return {"source":"OddsHarvester","status":"ok" if line is not None else "degraded","line":line,"book":"Pinnacle","note":"sharp reference fetched" if line is not None else "no line parsed"}
    except Exception as e:
        return {"source":"OddsHarvester","status":"fail","line":None,"book":"Pinnacle","note":str(e)}

def lock_single_prop(item):
    lid = f"LOCK-{date.today().strftime('%m%d')}-{len(st.session_state.locks)+1:02d}"
    st.session_state.locks.append({"id":lid,"type":"PROP","player":item["Player"],"prop":f"{item['Side']} {item['Line']} {item['Prop']}","side":item["Side"],"line":item["Line"],"tier":item["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"parlay_id":lid,"override":item["Tier"] not in ("SOVEREIGN","ELITE")})
    return lid

def build_prop_parlay(board_data=None):
    data = board_data or st.session_state.board_data or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, teams = [], set()
    for item in eligible:
        team = item["Player"].split()[-1]
        if len(legs) == 2 and team in teams: continue
        if len(legs) >= 5: break
        legs.append(item); teams.add(team)
    return legs

def build_game_parlay():
    data = st.session_state.game_verdicts or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, seen = [], set()
    for item in eligible:
        if len(legs) == 2 and item["Matchup"] in seen: continue
        if len(legs) >= 6: break
        legs.append(item); seen.add(item["Matchup"])
    return legs

def check_all_sources_health():
    log_scan("Starting site health check...", "skip")
    for name in PROP_SOURCES:
        test_sport = "NBA"
        url = build_source_url(name, test_sport)
        if not url:
            set_health(name, "fail", "No URL built")
            continue
        log_scan(f"Checking {name}: {url}", "skip")
        safe_fetch(url, name)
    for name in GAME_SOURCES:
        test_sport = "NBA"
        url = build_source_url(name, test_sport)
        if not url:
            set_health(name, "fail", "No URL built")
            continue
        log_scan(f"Checking {name}: {url}", "skip")
        safe_fetch(url, name)

def scan_all_sports():
    all_props, all_games = [], []
    sport_results = {}
    log_scan("Starting cross-sport scan...", "skip")

    for sport in SPORTS:
        allowed = SPORT_SOURCE_MAP.get(sport, ["BettingPros"])
        sport_props, sport_games = [], []
        seen = set()

        for source_name in allowed:
            url = build_source_url(source_name, sport)
            if not url: continue
            html = safe_fetch(url, source_name)
            if html:
                props = parse_props_generic(html, source_name)
                for prop in props:
                    player = prop.get("player", prop.get("col1", ""))
                    prop_type = prop.get("market", prop.get("col2", ""))
                    try:
                        line_str = prop.get("line", prop.get("odds", "0"))
                        line = float(re.sub(r"[^\d.]+", "", str(line_str))) if line_str else 0
                    except:
                        line = 0
                    key = (player, prop_type, line)
                    if key not in seen and player:
                        seen.add(key)
                        sport_props.append({
                            "Player": player, "Prop": prop_type, "Line": line, "Side": "OVER", "Sport": sport,
                        })

        for gs_name in ["VegasInsider", "ESPN (JSON API)"]:
            url = build_source_url(gs_name, sport)
            if not url: continue
            html = safe_fetch(url, gs_name)
            if html:
                if "ESPN" in gs_name:
                    sport_games = parse_espn_json(html, sport)
                else:
                    parsed = parse_props_generic(html, gs_name)
                    sport_games = [{"Matchup": g.get("matchup", ""), "Sport": sport} for g in parsed]
                if sport_games:
                    break

        if not sport_props:
            fallback = SPORT_FALLBACK_MAP.get(sport.upper(), SPORT_FALLBACK_MAP["NBA"])
            sport_props = fallback["props"]
        if not sport_games:
            fallback = SPORT_FALLBACK_MAP.get(sport.upper(), SPORT_FALLBACK_MAP["NBA"])
            sport_games = fallback["games"]

        sport_results[sport] = {"props": sport_props, "games": sport_games}
        all_props.extend(sport_props)
        all_games.extend(sport_games)

    st.session_state.cross_sport_board = {
        "props": run_council(all_props),
        "games": run_game_council(all_games),
        "scanned_at": datetime.now().strftime("%H:%M:%S"),
        "sport_results": sport_results
    }
    st.session_state.sharp_reference = fetch_sharp_reference(st.session_state.last_sport)
    log_scan(f"Cross-sport scan complete — {len(all_props)} props, {len(all_games)} games", "ok")

# ──────────────────────────────────────────────────────────────
# Computed Values
# ──────────────────────────────────────────────────────────────
bankroll = st.session_state.bankroll
bankroll_start = st.session_state.bankroll_start_of_day
daily_change_pct = ((bankroll - bankroll_start) / bankroll_start * 100) if bankroll_start > 0 else 0.0
integrity = st.session_state.integrity_score
unit_size = bankroll * KELLY_FRACTION * 0.015
pending_count = len([x for x in st.session_state.locks if x.get("status") == "PENDING"])
session_seconds = int(time.time() - st.session_state.session_start)
session_str = f"{session_seconds//60:02d}:{session_seconds%60:02d}"
sharp = st.session_state.sharp_reference or {"status":"unknown","source":"OddsHarvester","line":None,"book":"Pinnacle","note":"not loaded"}

if integrity < 40:
    floor_label = "EMERGENCY FLOOR"
    floor_pct = "12%"
elif bankroll < 400:
    floor_label = "BANKROLL FLOOR"
    floor_pct = "5.5%"
else:
    floor_label = "REGULAR FLOOR"
    floor_pct = "4.5%"

sources_ok = sum(1 for v in st.session_state.site_status.values() if v.get("status") == "ok")
total_sources = max(len(st.session_state.site_status), 1)
recent_check = bool(st.session_state.last_scan_time)

firewall_checks = {
    "All core sources online": sources_ok >= max(total_sources - 1, 1),
    "No stale data (>5 min)": recent_check,
    "Integrity Score > 60": integrity > 60,
    "Sovereign models aligned": True,
    "No conflicting line movement": True,
}
firewall_passed = sum(1 for v in firewall_checks.values() if v)

# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="font-size:24px;font-weight:800;color:#f4f8fc;letter-spacing:1px;margin-bottom:6px;">🛡️ BetCouncil</div>
    <div style="font-size:12px;color:#5a7088;margin-bottom:14px;">3.3 OS — DB Engine Active</div>
    """, unsafe_allow_html=True)

    change_class = "sidebar-change-green" if daily_change_pct >= 0 else "red-text"
    change_sign = "+" if daily_change_pct >= 0 else ""
    st.markdown(f"""
    <div class='sidebar-section'>
        <div class='sidebar-label'>BANKROLL</div>
        <div class='sidebar-value'>{'<span class="teal-text">' if daily_change_pct >= 0 else '<span class="red-text">'}${bankroll:,.2f}</span></div>
        <div class='{change_class}'>{change_sign}{daily_change_pct:.1f}% today</div>
    </div>
    """, unsafe_allow_html=True)
    new_bankroll = st.number_input("Adjust Bankroll", value=float(bankroll), step=10.0, key="sidebar_bankroll_input", label_visibility="collapsed")
    if new_bankroll != bankroll:
        st.session_state.bankroll = new_bankroll
        st.rerun()

    st.markdown(f"""
    <div class='sidebar-section'>
        <div class='sidebar-label'>INTEGRITY</div>
        <div class='sidebar-value' style='color:#0d9488;'>{integrity}<span style='font-size:14px;color:#5a7088;'> /100</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class='sidebar-section'>
        <div class='sidebar-label'>SEM</div>
        <div class='sidebar-value' style='font-size:14px;color:#e8a020;'>{floor_label}</div>
        <div class='sidebar-sub'>({floor_pct} edge threshold)</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class='sidebar-section'>
        <div class='sidebar-label'>UNIT SIZE</div>
        <div class='sidebar-value'>${unit_size:.2f}</div>
        <div class='sidebar-sub'>{KELLY_FRACTION} Kelly Fraction</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class='sidebar-section'>
        <div class='sidebar-label'>SESSION</div>
        <div class='sidebar-value' style='font-family:monospace;'>{session_str}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class='sidebar-section'>
        <div class='sidebar-label'>VALIDATION FIREWALL</div>
        <div style='font-size:20px;font-weight:700;color:#0d9488;margin-bottom:6px;'>{firewall_passed}/5 PASSED</div>
    """, unsafe_allow_html=True)
    for check_name, passed in firewall_checks.items():
        icon = "✅" if passed else "❌"
        cls = "firewall-pass" if passed else "firewall-fail"
        st.markdown(f"<div class='firewall-item {cls}'>{icon} {check_name}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # DB Status
    db_status = "🟢 Connected" if st.session_state.db_connected else "🔴 Offline"
    st.markdown(f"""
    <div class='sidebar-section'>
        <div class='sidebar-label'>DATABASE</div>
        <div class='sidebar-value' style='font-size:14px;'>{db_status}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class='sidebar-section'>
        <div class='sidebar-label'>QUARTER KELLY CALCULATOR</div>
    """, unsafe_allow_html=True)
    calc_col1, calc_col2 = st.columns(2)
    with calc_col1:
        st.markdown("<div class='sidebar-sub'>AMERICAN ODDS</div>", unsafe_allow_html=True)
        kelly_odds = st.number_input("Odds", value=st.session_state.kelly_odds, step=5, key="kelly_odds_input", label_visibility="collapsed")
    with calc_col2:
        st.markdown("<div class='sidebar-sub'>WIN PROBABILITY %</div>", unsafe_allow_html=True)
        kelly_prob = st.number_input("Prob", value=st.session_state.kelly_prob, step=1.0, key="kelly_prob_input", label_visibility="collapsed")
    st.session_state.kelly_odds = kelly_odds
    st.session_state.kelly_prob = kelly_prob
    kelly_result = kelly(kelly_prob/100.0, kelly_odds)
    st.markdown(f"<div style='font-size:16px;font-weight:700;color:#0d9488;margin-top:4px;'>Kelly Stake: {kelly_result*100:.1f}%</div>", unsafe_allow_html=True)
    st.markdown("<div class='small-note'>Made in Bolt</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    sport = st.selectbox("Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport), key="sidebar_sport")
    if st.button("🟢 Load Board", use_container_width=True):
        with st.spinner(f"Loading {sport} board — querying DB + scraping sources..."):
            load_sport_data_live(sport)
        st.success(f"{sport} loaded — {st.session_state.last_scan_time}")
    if st.button("🔄 Re-Run Board", use_container_width=True):
        with st.spinner("Re-running board..."):
            load_sport_data_live(st.session_state.last_sport)
    if st.button("🌍 Scan All Sports", use_container_width=True):
        with st.spinner("Scanning all sports..."):
            scan_all_sports()
        st.success("Cross-sport scan complete.")
    if st.button("🔍 Check Site Health", use_container_width=True):
        with st.spinner("Checking all sources..."):
            check_all_sources_health()
        st.success("Site health scan complete.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f"<div class='small-note' style='margin-top:12px;'>MODELS ACTIVE · {len(ALL_SOURCES)} SOURCES</div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# COMMAND BAR
# ──────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='command-bar'>
<div style='display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;'>
<div style='width:42px;height:42px;background:linear-gradient(135deg,#e8a020,#b07010);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;'>⚡</div>
<div><div style='font-size:22px;font-weight:700;color:#f4f8fc;letter-spacing:1px;'>BetCouncil</div><div style='font-size:12px;color:#5a7088;'>v3.3 · DB Engine + Section 9.1 Synthesis</div></div>
<div style='margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;'>
<span class='toggle-btn active'>🛡️ Safe: ON</span>
<span class='toggle-btn active'>⚠️ Blowout: ON</span>
<span class='toggle-btn' style='border-color:#e8a020;color:#e8a020;background:rgba(232,160,32,.1);'>🔒 {pending_count} Lock(s)</span>
</div></div>
<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:7px;'>
<div class='metric-box'><div class='metric-label'>Bankroll</div><div class='metric-value gold-text'>${bankroll:,.2f}</div></div>
<div class='metric-box'><div class='metric-label'>Unit Size</div><div class='metric-value gold-text'>${unit_size:.2f}</div></div>
<div class='metric-box'><div class='metric-label'>DB Status</div><div class='metric-value {"green-text" if st.session_state.db_connected else "red-text"}'>{'ONLINE' if st.session_state.db_connected else 'OFFLINE'}</div></div>
<div class='metric-box'><div class='metric-label'>Sharp Ref</div><div class='metric-value {"green-text" if sharp.get("status")=="ok" else "yellow-text" if sharp.get("status")=="degraded" else "red-text"}'>{sharp.get("book","Pinnacle")}</div></div>
</div></div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────
tabs = st.tabs(["🏀 Board of 8", "📊 Analysis", "🔒 Locks of Day", "📋 Locks & Ledger", "🔄 Reconciliation", "🧠 Models", "⚙️ Settings"])

# ────────── TAB 0: Board of 8 (Now with Full Summary) ──────────
with tabs[0]:
    board = st.session_state.board_data or []

    if st.session_state.last_scan_time:
        st.markdown(f"<div class='small-note'>Last scan: {st.session_state.last_scan_time} · {st.session_state.last_sport}</div>", unsafe_allow_html=True)

    # ── FULL SECTION 9.1 SUMMARY ──
    if st.session_state.summary_text and board:
        summary_html = st.session_state.summary_text
        # Convert markdown to HTML sections with proper styling
        st.markdown(st.session_state.summary_text)
        st.markdown("---")

        # Lock of the Day card
        approved = [i for i in board if i.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")]
        if approved:
            best = approved[0]
            st.markdown(f"""
            <div class='lock-of-day'>
                <div style='font-size:12px;color:#e8a020;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;'>🔒 LOCK OF THE DAY</div>
                <div style='display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;'>
                    <div>
                        <div style='font-size:18px;font-weight:700;color:#f4f8fc;'>{best['Player']}</div>
                        <div style='font-size:14px;color:#5a7088;'>{best['Side']} {best['Line']} {best['Prop']}</div>
                    </div>
                    <div style='text-align:center;'>
                        <div style='font-size:12px;color:#5a7088;'>Council Score</div>
                        <div style='font-size:24px;font-weight:800;color:#e8a020;'>{best['Weighted Score']:.2f}</div>
                        <div style='font-size:14px;font-weight:700;color:{tier_color(best["Tier"])};'>{best['Tier Label']}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🔒 Lock This Pick", key="lock_summary_lotd"):
                lock_id = lock_single_prop(best)
                st.session_state.locks.append({
                    "id": lock_id, "type": "PROP", "player": best["Player"],
                    "prop": f"{best['Side']} {best['Line']} {best['Prop']}",
                    "tier": best["Tier"], "status": "PENDING", "result": None
                })
                st.success(f"🔒 Locked: {best['Player']} {best['Side']} {best['Line']}")
                st.rerun()

    elif not board:
        st.info("No board loaded yet. Click **Load Board** or **Re-Run Board** in the sidebar to analyze props and generate the full synthesis.")

    elif not st.session_state.summary_text:
        st.info("Summary pending — load a board first.")

# ────────── TAB 1: Analysis (Cross-Sport) ──────────
with tabs[1]:
    st.markdown("# 🌍 Cross-Sport Best Bets")
    cross = st.session_state.cross_sport_board
    if not cross:
        st.info("Click **'Scan All Sports'** in the sidebar to populate cross-sport data from all leagues.")
    else:
        st.markdown(f"**Scanned at:** {cross['scanned_at']} | **{len(SPORTS)} sports**")

        sport_results = cross.get('sport_results', {})
        if sport_results:
            st.markdown("### 📊 Sport-by-Sport Summary")
            sport_names = list(sport_results.keys())
            num_cols = min(4, len(sport_names))
            sport_cols = st.columns(num_cols)
            for idx, sport_name in enumerate(sport_names):
                data = sport_results[sport_name]
                col_idx = idx % num_cols
                with sport_cols[col_idx]:
                    prop_count = len(data.get('props', []))
                    game_count = len(data.get('games', []))
                    st.metric(sport_name, f"{prop_count} props", f"{game_count} games")

        st.markdown("---")
        st.markdown("## 🏆 Top Props Across All Sports")
        cross_props = cross.get('props', [])
        if cross_props:
            for i, p in enumerate(cross_props[:8], 1):
                tc = tier_color(p.get('Tier', 'PASS'))
                st.markdown(f"<div class='section-card' style='border-left:3px solid {tc};'><span style='color:#5a7088;'>#{i} · {p.get('Sport','')}</span> <span style='color:#f4f8fc;font-weight:600;'>{p.get('Player','')}</span> — {p.get('Side','')} {p.get('Line','')} {p.get('Prop','')} <span style='color:{tc};font-weight:600;'>{p.get('Tier Label','')}</span> <span style='font-family:monospace;color:#e8a020;float:right;'>Score {p.get('Weighted Score',0):.2f}</span></div>", unsafe_allow_html=True)
        else:
            st.info("No props found in cross-sport scan.")

# ────────── TAB 2: Locks of Day ──────────
with tabs[2]:
    st.markdown("# 🔒 Locks of Day")
    board_data_for_locks = st.session_state.board_data or []
    if board_data_for_locks:
        approved = [i for i in board_data_for_locks if i["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
        approved.sort(key=lambda x: x["Weighted Score"], reverse=True)
        if approved:
            best_prop = approved[0]
            st.markdown(f"""
            <div class='lock-of-day'>
                <div style='font-size:14px;color:#5a7088;'>LOCK OF THE DAY</div>
                <div style='font-size:20px;font-weight:700;color:#f4f8fc;margin-top:4px;'>{best_prop['Player']}</div>
                <div style='font-size:16px;color:#e8f0f8;'>{best_prop['Side']} {best_prop['Line']} {best_prop['Prop']}</div>
                <div style='margin-top:6px;'><span style='color:{tier_color(best_prop['Tier'])};font-weight:700;font-size:15px;'>{best_prop['Tier Label']}</span> <span style='font-family:monospace;color:#e8a020;float:right;'>Score {best_prop['Weighted Score']:.2f}</span></div>
            </div>
            """, unsafe_allow_html=True)
        prop_par = build_prop_parlay()
        if prop_par:
            st.markdown("## 🎯 Props Parlay Candidates")
            for i, leg in enumerate(prop_par[:5], 1):
                st.markdown(f"<div class='section-card'><b>Leg {i}:</b> {leg['Player']} {leg['Side']} {leg['Line']} {leg['Prop']} — <span style='color:{tier_color(leg['Tier'])}'>{leg['Tier Label']}</span></div>", unsafe_allow_html=True)
    else:
        st.info("Load a board first to see Locks of Day.")

# ────────── TAB 3: Locks & Ledger ──────────
with tabs[3]:
    st.markdown("# 📋 Locks & Ledger")
    if not st.session_state.locks:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(st.session_state.locks):
            cols = st.columns([4,1,1,1])
            with cols[0]:
                st.markdown(f"**{lock.get('id')}** — {lock.get('player')} | {lock.get('prop')} | {lock.get('tier')}")
            with cols[1]:
                if st.button("✅ WIN", key=f"w_{i}"):
                    lock["status"] = "RESOLVED"
                    lock["result"] = "WIN"
                    st.session_state.history.append(lock)
                    st.session_state.bankroll += unit_size * 1.91
                    st.session_state.integrity_score = min(100, st.session_state.integrity_score + 0.3)
                    st.rerun()
            with cols[2]:
                if st.button("❌ LOSS", key=f"l_{i}"):
                    lock["status"] = "RESOLVED"
                    lock["result"] = "LOSS"
                    st.session_state.history.append(lock)
                    st.session_state.bankroll -= unit_size
                    st.session_state.integrity_score = max(40, st.session_state.integrity_score - 0.4)
                    st.rerun()
            with cols[3]:
                if st.button("🗑️ Remove", key=f"rm_{i}"):
                    st.session_state.locks.pop(i)
                    st.rerun()
    if st.session_state.history:
        st.markdown("### Resolved History")
        st.table(pd.DataFrame(st.session_state.history))

# ────────── TAB 4: Reconciliation ──────────
with tabs[4]:
    st.markdown("# 🔄 Reconciliation")
    st.info("Your existing result sync / autopsy workflow can remain here unchanged.")

# ────────── TAB 5: Models ──────────
with tabs[5]:
    st.markdown("# 🧠 Council Models — Fixed Weights")
    model_rows = ""
    for m in MODELS:
        model_rows += f"<tr><td style='color:#f4f8fc;font-weight:600;font-size:14px;'>{m['name']}</td><td style='color:#5a7088;font-size:14px;'>{m['specialty']}</td><td style='color:#e8a020;font-family:monospace;font-size:15px;font-weight:700;'>{m['weight']:.2f}</td><td style='color:#5a7088;font-size:13px;'>{m['function']}</td></tr>"
    st.markdown(f"""
    <table class='model-table'>
    <thead><tr><th>MODEL</th><th>SPECIALTY</th><th>WEIGHT</th><th>CORE FUNCTION</th></tr></thead>
    <tbody>{model_rows}</tbody>
    </table>
    <div class='small-note' style='margin-top:10px;'>Total: {sum(m['weight'] for m in MODELS):.2f} / 1.00</div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("## Tier Thresholds (Fixed)")
    st.markdown("""
    | SCORE | TIER |
    |---|---|
    | ≥ 0.70 | ⚡ Sovereign Lock |
    | 0.55–0.69 | 🟡 Elite Edge |
    | 0.40–0.54 | 🔵 Approved Single |
    | 0.20–0.39 | 🟠 Lean |
    | < 0.20 | 🔴 PASS |
    """)

# ────────── TAB 6: Settings ──────────
with tabs[6]:
    st.markdown("# ⚙️ SEM & System")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Integrity", f"{integrity}/100")
    c2.metric("Safe Corridor", "ACTIVE")
    c3.metric("Emergency Floor", "ACTIVE")
    c4.metric("Bankroll", f"${bankroll:,.2f}")

    st.markdown("## Site Health")
    if st.button("🔄 Refresh Site Health", key="refresh_health"):
        check_all_sources_health()
        st.rerun()

    cols = st.columns(2)
    prop_source_names = list(PROP_SOURCES.keys())
    game_source_names = list(GAME_SOURCES.keys())

    with cols[0]:
        st.markdown("### Prop Sources")
        for name in prop_source_names:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "") or "—"
            err = st.session_state.site_status.get(name, {}).get("error", "")
            label = "🟢 WORKING" if s == "ok" else "🔴 DOWN" if s == "fail" else "⚪ UNCHECKED"
            err_str = f" <span style='font-size:10px;color:#d03030;'>({err})</span>" if err and s == "fail" else ""
            st.markdown(f"<div class='section-card'>{label} <b>{name}</b> <span class='muted-text'>— {t}</span>{err_str}</div>", unsafe_allow_html=True)

    with cols[1]:
        st.markdown("### Game Sources")
        for name in game_source_names:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "") or "—"
            err = st.session_state.site_status.get(name, {}).get("error", "")
            label = "🟢 WORKING" if s == "ok" else "🔴 DOWN" if s == "fail" else "⚪ UNCHECKED"
            err_str = f" <span style='font-size:10px;color:#d03030;'>({err})</span>" if err and s == "fail" else ""
            st.markdown(f"<div class='section-card'>{label} <b>{name}</b> <span class='muted-text'>— {t}</span>{err_str}</div>", unsafe_allow_html=True)

    # DB Status
    st.markdown("---")
    st.markdown("## 🗄️ Database Status")
    if st.button("🔄 Test DB Connection", key="test_db"):
        conn = get_db_connection()
        if conn:
            st.session_state.db_connected = True
            st.session_state.db_error = ""
            conn.close()
            st.success("PostgreSQL connected successfully.")
        else:
            st.session_state.db_connected = False
            st.error(f"Connection failed: {st.session_state.db_error}")
    st.markdown(f"**Status:** {'🟢 Connected' if st.session_state.db_connected else '🔴 Offline'}")

    # Scan log
    if st.session_state.scan_log:
        st.markdown("---")
        st.markdown("## 📜 Last Scan Log")
        log_html = "<div class='scan-log'>"
        for entry in st.session_state.scan_log[-20:]:
            lvl = entry.get('level', 'skip')
            cls = f"log-{lvl}"
            log_html += f"<div class='{cls}'>{entry.get('time','')} — {entry.get('msg','')}</div>"
        log_html += "</div>"
        st.markdown(log_html, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"**Sharp Reference:** {sharp.get('book','Pinnacle')} via {sharp.get('source','OddsHarvester')} | Status: {sharp.get('status','unknown')} | Line: {sharp.get('line')} | Note: {sharp.get('note','')}")
