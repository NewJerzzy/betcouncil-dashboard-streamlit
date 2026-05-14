import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import re
import requests
import time
import hashlib
import pickle
import os
import unicodedata
from math import exp, factorial

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="BetCouncil v4.4 – Chairman", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
body, .stApp, .main {
    background-color: #060c14; color: #e8f0f8;
    font-family: 'Inter', system-ui, sans-serif; font-size: 15px;
}
h1 { font-size: 28px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px; }
h2 { font-size: 20px; font-weight: 600; color: #e0e8f0; letter-spacing: -0.3px; }
h3 { font-size: 17px; font-weight: 600; color: #d0d8e0; }
h4 { font-size: 15px; font-weight: 600; color: #c0c8d0; }
.stButton > button {
    background-color: #0ea5a0; color: #ffffff; border: none;
    border-radius: 8px; padding: 8px 18px; font-weight: 600;
    font-size: 14px; transition: all 0.2s;
}
.stButton > button:hover { background-color: #0d9488; transform: translateY(-1px); }
.command-bar {
    background: linear-gradient(135deg, rgba(14,165,160,0.08), #0d1520);
    border: 1px solid rgba(14,165,160,0.3); border-top: 3px solid #0ea5a0;
    border-radius: 0 0 12px 12px; padding: 18px 22px; margin-bottom: 16px;
}
.metric-box {
    background: #0d1520; border: 1px solid #1a2a3a;
    border-radius: 8px; padding: 10px 14px; text-align: center;
}
.metric-label {
    font-size: 11px; color: #6a7a8a; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px;
}
.metric-value { font-size: 20px; font-weight: 700; }
.prop-card {
    background: linear-gradient(135deg, #0d1520, #111c28);
    border: 1px solid #1a2a3a; border-radius: 10px;
    padding: 14px 16px; margin-bottom: 8px; transition: border-color 0.2s;
}
.prop-card:hover { border-color: #0ea5a0; }
.parlay-card {
    background: linear-gradient(135deg, rgba(14,165,160,0.06), #0f1825);
    border: 1px solid rgba(14,165,160,0.25); border-radius: 10px; padding: 16px;
}
.game-parlay-card {
    background: linear-gradient(135deg, rgba(74,144,217,0.06), #0f1825);
    border: 1px solid rgba(74,144,217,0.25); border-radius: 10px; padding: 16px;
}
.section-card {
    background: linear-gradient(135deg, #0d1520, #0f1825);
    border: 1px solid #1a2a3a; border-radius: 10px; padding: 16px; margin-bottom: 10px;
}
.gold-text  { color: #e8a020; }
.teal-text  { color: #0ea5a0; }
.red-text   { color: #e04040; }
.muted-text { color: #6a7a8a; }
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS
# =========================
DEFAULT_BANKROLL      = 468.49
KELLY_FRACTION        = 0.25
KELLY_CAP             = 0.25
ODDS                  = -110
EDGE_CAP              = 0.20
MIN_EDGE_DEFAULT      = 0.02
REQUEST_TIMEOUT       = 10
CACHE_DIR             = "/tmp/betcouncil_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
HEADERS               = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
AVERAGES_LAST_UPDATED = "2025-05-13"

TIER_COLORS = {
    "SOVEREIGN": "#e8a020", "ELITE": "#0ea5a0",
    "APPROVED":  "#4a90d9", "LEAN":  "#7a8a9a", "PASS": "#e04040",
}
TIER_DESCRIPTIONS = {
    "SOVEREIGN": "Edge ≥ 15% — Highest confidence",
    "ELITE":     "Edge ≥ 10% — Strong edge",
    "APPROVED":  "Edge ≥ 5%  — Solid value",
    "LEAN":      "Edge ≥ 2%  — Marginal",
    "PASS":      "Edge < 2%  — No value",
}

# =========================
# PLAYER SEASON AVERAGES (Hardcoded Fallback)
# =========================
PLAYER_AVERAGES = {
    "NBA": {
        "LeBron James":            {"PTS": 23.7, "REB": 8.5,  "AST": 8.3,  "PRA": 40.5},
        "Luka Doncic":             {"PTS": 28.1, "REB": 9.3,  "AST": 8.7,  "PRA": 46.1},
        "Nikola Jokic":            {"PTS": 29.4, "REB": 13.0, "AST": 10.2, "PRA": 52.6},
        "Shai Gilgeous-Alexander": {"PTS": 31.5, "REB": 5.5,  "AST": 6.5,  "PRA": 43.5},
        "Giannis Antetokounmpo":   {"PTS": 30.4, "REB": 11.9, "AST": 6.5,  "PRA": 48.8},
        "Jayson Tatum":            {"PTS": 27.5, "REB": 8.7,  "AST": 4.9,  "PRA": 41.1},
        "Stephen Curry":           {"PTS": 26.4, "REB": 4.5,  "AST": 5.1,  "PRA": 36.0},
        "Kevin Durant":            {"PTS": 27.1, "REB": 6.6,  "AST": 5.0,  "PRA": 38.7},
        "Anthony Davis":           {"PTS": 24.7, "REB": 12.6, "AST": 3.5,  "PRA": 40.8},
        "Damian Lillard":          {"PTS": 24.3, "REB": 4.4,  "AST": 7.0,  "PRA": 35.7},
        "Devin Booker":            {"PTS": 27.1, "REB": 4.5,  "AST": 6.9,  "PRA": 38.5},
        "Donovan Mitchell":        {"PTS": 27.5, "REB": 5.0,  "AST": 5.5,  "PRA": 38.0},
        "Jimmy Butler":            {"PTS": 20.8, "REB": 5.3,  "AST": 5.0,  "PRA": 31.1},
        "Trae Young":              {"PTS": 25.7, "REB": 2.8,  "AST": 10.8, "PRA": 39.3},
        "Domantas Sabonis":        {"PTS": 19.4, "REB": 13.7, "AST": 8.2,  "PRA": 41.3},
        "Karl-Anthony Towns":      {"PTS": 21.8, "REB": 8.3,  "AST": 3.0,  "PRA": 33.1},
        "Bam Adebayo":             {"PTS": 20.4, "REB": 10.2, "AST": 3.5,  "PRA": 34.1},
        "Rudy Gobert":             {"PTS": 14.0, "REB": 12.9, "AST": 1.2,  "PRA": 28.1},
        "Tyrese Haliburton":       {"PTS": 20.1, "REB": 3.8,  "AST": 10.9, "PRA": 34.8},
        "Jalen Brunson":           {"PTS": 28.7, "REB": 3.7,  "AST": 7.4,  "PRA": 39.8},
        "Cade Cunningham":         {"PTS": 25.3, "REB": 6.0,  "AST": 9.0,  "PRA": 40.3},
        "Victor Wembanyama":       {"PTS": 21.4, "REB": 10.6, "AST": 3.9,  "PRA": 35.9},
        "Paolo Banchero":          {"PTS": 22.6, "REB": 6.9,  "AST": 5.4,  "PRA": 34.9},
        "Evan Mobley":             {"PTS": 18.0, "REB": 9.4,  "AST": 2.9,  "PRA": 30.3},
        "Darius Garland":          {"PTS": 20.6, "REB": 2.7,  "AST": 6.7,  "PRA": 30.0},
        "Tobias Harris":           {"PTS": 14.5, "REB": 5.8,  "AST": 2.1,  "PRA": 22.4},
        "Ja Morant":               {"PTS": 25.1, "REB": 5.6,  "AST": 8.1,  "PRA": 38.8},
        "Zion Williamson":         {"PTS": 22.9, "REB": 5.8,  "AST": 5.0,  "PRA": 33.7},
        "Jamal Murray":            {"PTS": 21.2, "REB": 4.2,  "AST": 6.5,  "PRA": 31.9},
        "Michael Porter Jr.":      {"PTS": 16.7, "REB": 6.9,  "AST": 1.4,  "PRA": 25.0},
        "Aaron Gordon":            {"PTS": 14.4, "REB": 6.5,  "AST": 3.5,  "PRA": 24.4},
        "Jalen Williams":          {"PTS": 23.9, "REB": 4.5,  "AST": 5.6,  "PRA": 34.0},
        "Alperen Sengun":          {"PTS": 21.1, "REB": 9.3,  "AST": 5.0,  "PRA": 35.4},
        "Desmond Bane":            {"PTS": 21.5, "REB": 4.8,  "AST": 4.2,  "PRA": 30.5},
        "Scottie Barnes":          {"PTS": 19.9, "REB": 8.2,  "AST": 6.1,  "PRA": 34.2},
        "Franz Wagner":            {"PTS": 19.7, "REB": 5.2,  "AST": 3.7,  "PRA": 28.6},
        "De'Aaron Fox":            {"PTS": 25.2, "REB": 4.5,  "AST": 5.9,  "PRA": 35.6},
        "Pascal Siakam":           {"PTS": 21.3, "REB": 7.8,  "AST": 4.5,  "PRA": 33.6},
        "Kawhi Leonard":           {"PTS": 23.7, "REB": 6.1,  "AST": 3.6,  "PRA": 33.4},
        "Luguentz Dort":           {"PTS": 13.7, "REB": 3.8,  "AST": 1.9,  "PRA": 19.4},
    },
    "MLB": {
        "Aaron Judge":             {"HR": 0.15, "H": 1.2,  "RBI": 0.9, "R": 0.9},
        "Shohei Ohtani":           {"HR": 0.14, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Mookie Betts":            {"HR": 0.12, "H": 1.2,  "RBI": 0.7, "R": 0.9},
        "Ronald Acuna Jr.":        {"HR": 0.13, "H": 1.2,  "RBI": 0.8, "R": 0.9},
        "Bryce Harper":            {"HR": 0.14, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Juan Soto":               {"HR": 0.13, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Freddie Freeman":         {"HR": 0.11, "H": 1.2,  "RBI": 0.7, "R": 0.8},
        "Jose Ramirez":            {"HR": 0.12, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Pete Alonso":             {"HR": 0.15, "H": 1.0,  "RBI": 0.9, "R": 0.7},
        "Vladimir Guerrero Jr.":   {"HR": 0.12, "H": 1.2,  "RBI": 0.8, "R": 0.8},
        "Francisco Lindor":        {"HR": 0.12, "H": 1.1,  "RBI": 0.7, "R": 0.8},
        "Bobby Witt Jr.":          {"HR": 0.12, "H": 1.2,  "RBI": 0.8, "R": 0.9},
        "Gunnar Henderson":        {"HR": 0.14, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Elly De La Cruz":         {"HR": 0.10, "H": 1.0,  "RBI": 0.6, "R": 0.7},
        "Corbin Carroll":          {"HR": 0.08, "H": 1.1,  "RBI": 0.5, "R": 0.8},
        "Paul Skenes":             {"SO": 8.5,  "H": 0.3,  "ER": 0.4},
        "Spencer Strider":         {"SO": 9.2,  "H": 0.3,  "ER": 0.5},
        "Gerrit Cole":             {"SO": 8.8,  "H": 0.4,  "ER": 0.5},
        "Zack Wheeler":            {"SO": 8.4,  "H": 0.4,  "ER": 0.5},
        "Tarik Skubal":            {"SO": 9.0,  "H": 0.3,  "ER": 0.4},
    },
    "NFL": {
        "Patrick Mahomes":         {"PASS_YDS": 280, "TD": 2.2},
        "Josh Allen":              {"PASS_YDS": 260, "RUSH_YDS": 35,  "TD": 2.5},
        "Jalen Hurts":             {"PASS_YDS": 230, "RUSH_YDS": 45,  "TD": 2.2},
        "Lamar Jackson":           {"PASS_YDS": 220, "RUSH_YDS": 65,  "TD": 2.0},
        "Joe Burrow":              {"PASS_YDS": 270, "TD": 2.0},
        "Justin Herbert":          {"PASS_YDS": 265, "TD": 2.0},
        "Dak Prescott":            {"PASS_YDS": 260, "TD": 2.0},
        "Christian McCaffrey":     {"RUSH_YDS": 85,  "REC_YDS": 45,  "TD": 1.0},
        "Derrick Henry":           {"RUSH_YDS": 90,  "TD": 0.9},
        "Saquon Barkley":          {"RUSH_YDS": 80,  "REC_YDS": 35,  "TD": 0.8},
        "Tyreek Hill":             {"REC_YDS": 95,  "TD": 0.8},
        "Justin Jefferson":        {"REC_YDS": 90,  "TD": 0.7},
        "Ja'Marr Chase":           {"REC_YDS": 85,  "TD": 0.7},
        "Travis Kelce":            {"REC_YDS": 70,  "TD": 0.6},
        "CeeDee Lamb":             {"REC_YDS": 92,  "TD": 0.7},
        "A.J. Brown":              {"REC_YDS": 88,  "TD": 0.7},
    },
    "NHL": {
        "Connor McDavid":          {"PTS": 1.5,  "GOALS": 0.6, "ASSISTS": 0.9, "SOG": 3.5},
        "Leon Draisaitl":          {"PTS": 1.4,  "GOALS": 0.6, "ASSISTS": 0.8, "SOG": 3.2},
        "Nathan MacKinnon":        {"PTS": 1.4,  "GOALS": 0.5, "ASSISTS": 0.9, "SOG": 3.4},
        "David Pastrnak":          {"PTS": 1.2,  "GOALS": 0.6, "ASSISTS": 0.6, "SOG": 3.5},
        "Nikita Kucherov":         {"PTS": 1.5,  "GOALS": 0.5, "ASSISTS": 1.0, "SOG": 3.0},
        "Auston Matthews":         {"PTS": 1.2,  "GOALS": 0.7, "ASSISTS": 0.5, "SOG": 3.7},
        "Mitch Marner":            {"PTS": 1.2,  "GOALS": 0.4, "ASSISTS": 0.8, "SOG": 2.8},
        "Cale Makar":              {"PTS": 0.9,  "GOALS": 0.2, "ASSISTS": 0.7, "SOG": 2.5},
        "Kirill Kaprizov":         {"PTS": 1.1,  "GOALS": 0.5, "ASSISTS": 0.6, "SOG": 3.2},
        "Mikko Rantanen":          {"PTS": 1.3,  "GOALS": 0.5, "ASSISTS": 0.8, "SOG": 3.0},
        "Matthew Tkachuk":         {"PTS": 1.1,  "GOALS": 0.4, "ASSISTS": 0.7, "SOG": 3.0},
        "Brayden Point":           {"PTS": 1.1,  "GOALS": 0.5, "ASSISTS": 0.6, "SOG": 3.1},
        "Sam Reinhart":            {"PTS": 1.0,  "GOALS": 0.5, "ASSISTS": 0.5, "SOG": 3.0},
        "Aleksander Barkov":       {"PTS": 1.0,  "GOALS": 0.4, "ASSISTS": 0.6, "SOG": 2.8},
    },
    "WNBA": {
        "A'ja Wilson":             {"PTS": 26.0, "REB": 9.4,  "AST": 2.4, "PRA": 37.8},
        "Breanna Stewart":         {"PTS": 21.8, "REB": 8.6,  "AST": 3.8, "PRA": 34.2},
        "Sabrina Ionescu":         {"PTS": 19.4, "REB": 4.5,  "AST": 6.3, "PRA": 30.2},
        "Kelsey Plum":             {"PTS": 18.9, "REB": 2.8,  "AST": 4.2, "PRA": 25.9},
        "Napheesa Collier":        {"PTS": 20.1, "REB": 9.3,  "AST": 2.7, "PRA": 32.1},
        "Caitlin Clark":           {"PTS": 19.2, "REB": 5.7,  "AST": 8.4, "PRA": 33.3},
        "Angel Reese":             {"PTS": 13.1, "REB": 13.1, "AST": 1.9, "PRA": 28.1},
        "Alyssa Thomas":           {"PTS": 12.5, "REB": 9.2,  "AST": 7.1, "PRA": 28.8},
        "Jackie Young":            {"PTS": 17.3, "REB": 4.1,  "AST": 4.0, "PRA": 25.4},
    },
}

DEFAULT_AVERAGES = {
    "NBA":  {"PTS": 10.0, "REB": 4.0,    "AST": 2.5,    "PRA": 16.5},
    "MLB":  {"HR": 0.05,  "H": 0.8,      "RBI": 0.3,    "R": 0.3,    "SO": 5.0},
    "NFL":  {"PASS_YDS": 200, "RUSH_YDS": 35, "REC_YDS": 40, "TD": 0.5},
    "NHL":  {"PTS": 0.45, "GOALS": 0.18, "ASSISTS": 0.27, "SOG": 1.8},
    "WNBA": {"PTS": 8.0,  "REB": 3.5,   "AST": 2.0,    "PRA": 13.5},
}

STAT_NORMALIZE = {
    ("NBA",  "Points"):           "PTS",
    ("NBA",  "Rebounds"):         "REB",
    ("NBA",  "Assists"):          "AST",
    ("NBA",  "Pts+Reb+Ast"):      "PRA",
    ("NBA",  "Pts+Reb"):          "PRA",
    ("NBA",  "Pts+Ast"):          "PRA",
    ("NBA",  "Reb+Ast"):          "PRA",
    ("MLB",  "Home Runs"):        "HR",
    ("MLB",  "Hits"):             "H",
    ("MLB",  "RBIs"):             "RBI",
    ("MLB",  "Runs"):             "R",
    ("MLB",  "Strikeouts"):       "SO",
    ("MLB",  "Earned Runs"):      "ER",
    ("NFL",  "Passing Yards"):    "PASS_YDS",
    ("NFL",  "Rushing Yards"):    "RUSH_YDS",
    ("NFL",  "Receiving Yards"):  "REC_YDS",
    ("NFL",  "Touchdowns"):       "TD",
    ("NHL",  "Points"):           "PTS",
    ("NHL",  "Goals"):            "GOALS",
    ("NHL",  "Assists"):          "ASSISTS",
    ("NHL",  "Shots On Goal"):    "SOG",
    ("WNBA", "Points"):           "PTS",
    ("WNBA", "Rebounds"):         "REB",
    ("WNBA", "Assists"):          "AST",
    ("WNBA", "Pts+Reb+Ast"):      "PRA",
}

POISSON_STATS = {"HR", "GOALS", "TD", "SO"}

# =========================
# CACHE
# =========================
def cached_fetch(url, ttl_minutes=25):
    cache_key  = hashlib.md5(url.encode()).hexdigest()
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

# =========================
# BALLDONTLIE — LIVE NBA AVERAGES (cached 24 hours, batched request)
# =========================
BDL_API_KEY = "9d7c9ea5-54ea-4084-b0d0-2541ac7c360d"

# Map player name -> balldontlie player_id for the ~40 most bet NBA players
BDL_PLAYER_IDS = {
    "LeBron James": 237, "Luka Doncic": 140, "Nikola Jokic": 279,
    "Shai Gilgeous-Alexander": 484, "Giannis Antetokounmpo": 15,
    "Jayson Tatum": 484, "Stephen Curry": 115, "Kevin Durant": 135,
    "Anthony Davis": 14, "Damian Lillard": 153, "Devin Booker": 70,
    "Donovan Mitchell": 300, "Jimmy Butler": 85, "Trae Young": 571,
    "Domantas Sabonis": 395, "Karl-Anthony Towns": 508, "Bam Adebayo": 2,
    "Rudy Gobert": 185, "Tyrese Haliburton": 613, "Jalen Brunson": 86,
    "Cade Cunningham": 625, "Victor Wembanyama": 794, "Paolo Banchero": 731,
    "Evan Mobley": 694, "Darius Garland": 578, "Tobias Harris": 216,
    "Ja Morant": 606, "Zion Williamson": 400, "Jamal Murray": 333,
    "Michael Porter Jr.": 585, "Aaron Gordon": 5, "Jalen Williams": 746,
    "Alperen Sengun": 700, "Desmond Bane": 616, "Scottie Barnes": 689,
    "Franz Wagner": 709, "De'Aaron Fox": 170, "Pascal Siakam": 400,
    "Kawhi Leonard": 232, "Luguentz Dort": 601,
}

def fetch_nba_averages_bdl():
    """Fetch NBA per-game averages from balldontlie. One batched call, cached 24 hours."""
    cache_path = os.path.join(CACHE_DIR, "bdl_nba_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    if not BDL_API_KEY:
        return {}
    ids = list(BDL_PLAYER_IDS.values())
    params = "&".join([f"player_ids[]={pid}" for pid in ids])
    url = f"https://api.balldontlie.io/v1/season_averages?season=2024&{params}"
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
        return avgs
    except:
        return {}

# =========================
# NAME MATCHING
# =========================
def normalize_name(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+(jr|sr|ii|iii)\.?$", "", s.lower().strip())
    return s

def find_player_avg(player_name, avgs_dict):
    if player_name in avgs_dict:
        return avgs_dict[player_name], False
    norm = normalize_name(player_name)
    for key, val in avgs_dict.items():
        if normalize_name(key) == norm:
            return val, False
    return {}, True

# =========================
# PRIZEPICKS SCRAPER
# =========================
def _parse_prizepicks_response(data, sport, seen):
    props = []
    included = data.get("included", [])
    players = {}
    for item in included:
        if item.get("type") in ("new_player", "player"):
            players[item["id"]] = item.get("attributes", {}).get("name", "Unknown")
    for proj in data.get("data", []):
        if proj.get("type") != "projection":
            continue
        attrs = proj.get("attributes", {})
        rel = proj.get("relationships", {})
        player_rel = rel.get("new_player") or rel.get("player")
        if not player_rel:
            continue
        pid = player_rel.get("data", {}).get("id")
        name = players.get(pid, "")
        if not name or name == "Unknown":
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
        props.append({
            "Player": name, "Prop": stat, "Line": line,
            "Side": "OVER", "Sport": sport, "source": "PrizePicks",
        })
    return props

def scrape_prizepicks(sport):
    league_ids = {"NBA":4,"MLB":5,"NHL":3,"NFL":7,"WNBA":8,"UFC":6,"Golf":11,"Tennis":12,"Soccer":2}
    league = league_ids.get(sport.upper())
    if not league:
        return []
    urls = [
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&state_code=CA",
    ]
    pp_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://app.prizepicks.com/",
                  "Accept": "application/json", "X-Device-ID": "betcouncil-app"}
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
                resp = requests.get(url, headers=pp_headers, timeout=REQUEST_TIMEOUT)
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
        parsed = _parse_prizepicks_response(data, sport, seen)
        all_props.extend(parsed)
        if all_props:
            break
    return all_props

# =========================
# GAME LINES — ESPN
# =========================
def fetch_game_lines(sport):
    slug_map = {"NBA":"basketball/nba","MLB":"baseball/mlb","NFL":"football/nfl","NHL":"hockey/nhl","WNBA":"basketball/wnba"}
    path = slug_map.get(sport, "")
    if not path:
        return []
    def _fetch_date(target_date):
        date_str = target_date.strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={date_str}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                events = resp.json().get("events", [])
                return [{"Matchup": e.get("shortName", ""),
                         "Status": e.get("status", {}).get("type", {}).get("description", ""),
                         "Date": target_date.strftime("%a %b %d"), "Sport": sport} for e in events]
        except:
            pass
        return []
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_games = _fetch_date(today)
    all_final = all(g["Status"].lower() in ("final","game over","final/ot","final/so","postponed") for g in today_games) if today_games else True
    if all_final:
        tomorrow_games = _fetch_date(tomorrow)
        if tomorrow_games:
            return tomorrow_games
        return today_games
    return today_games

# =========================
# EDGE & KELLY
# =========================
def poisson_prob_over(line, avg):
    if avg <= 0:
        return 0.5
    k = int(line)
    try:
        p_under = sum((avg**i * exp(-avg)) / factorial(i) for i in range(k + 1))
        return round(1 - p_under, 4)
    except:
        return 0.5

def compute_edge(line, player_avg, side="OVER", stat_key="PTS"):
    if player_avg <= 0:
        return 0.0, 0.5
    if stat_key in POISSON_STATS:
        prob = poisson_prob_over(line, player_avg)
        if side.upper() == "UNDER":
            prob = 1 - prob
        edge = prob - 0.5
    else:
        diff = (line - player_avg) / player_avg
        edge = -diff if side.upper() == "OVER" else diff
        edge = max(-EDGE_CAP, min(EDGE_CAP, edge))
        prob = max(0.30, min(0.70, 0.5 + edge))
    return round(edge, 4), round(prob, 4)

def kelly_unit(prob, bankroll):
    if prob <= 0.5:
        return 0.0
    b = 100 / abs(ODDS)
    q = 1 - prob
    kelly = (b * prob - q) / b
    if kelly <= 0:
        return 0.0
    return round(min(kelly * KELLY_FRACTION * bankroll, bankroll * KELLY_CAP), 2)

def get_tier(edge):
    if edge >= 0.15: return "SOVEREIGN"
    if edge >= 0.10: return "ELITE"
    if edge >= 0.05: return "APPROVED"
    if edge >= 0.02: return "LEAN"
    return "PASS"

def active_unit():
    return round(st.session_state.bankroll * KELLY_FRACTION * KELLY_CAP, 2)

def get_session_time():
    elapsed = int(time.time() - st.session_state.session_start)
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

def get_daily_change():
    if st.session_state.day_start_br == 0:
        return "0.0%"
    change = (st.session_state.bankroll - st.session_state.day_start_br) / st.session_state.day_start_br * 100
    return f"{'+'if change>=0 else''}{change:.1f}%"

# =========================
# MAIN LOAD
# =========================
def load_sport_data(sport):
    # NBA: merge live balldontlie data (priority) over hardcoded fallback
    if sport == "NBA":
        live_avgs = fetch_nba_averages_bdl()
        avgs = {**PLAYER_AVERAGES.get("NBA", {}), **live_avgs}
    else:
        avgs = PLAYER_AVERAGES.get(sport, {})
    defaults = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])
    min_edge = st.session_state.min_edge
    skip_def = st.session_state.skip_defaults
    props = scrape_prizepicks(sport)
    if not props:
        return [], fetch_game_lines(sport), 0, 0
    enriched = []
    skipped_def = skipped_edge = 0
    for p in props:
        stat_raw = p["Prop"]
        stat_norm = STAT_NORMALIZE.get((sport, stat_raw), stat_raw)
        player = p["Player"]
        side = p["Side"]
        player_stats, using_default = find_player_avg(player, avgs)
        if using_default:
            skipped_def += 1
            if skip_def:
                continue
            avg = defaults.get(stat_norm, p["Line"])
        else:
            avg = player_stats.get(stat_norm, defaults.get(stat_norm, p["Line"]))
        edge, prob = compute_edge(p["Line"], avg, side, stat_norm)
        if edge < min_edge:
            skipped_edge += 1
            continue
        tier = get_tier(edge)
        enriched.append({
            "Player": player, "Prop": stat_raw, "Line": p["Line"], "Side": side,
            "Avg": avg, "Edge": edge, "EdgePct": f"{edge:.1%}", "Prob": prob,
            "Wager": kelly_unit(prob, st.session_state.bankroll), "Tier": tier,
            "Quality": "Lookup" if not using_default else "Default",
            "Model": "Poisson" if stat_norm in POISSON_STATS else "Linear",
            "Sport": sport,
        })
    enriched.sort(key=lambda x: x["Edge"], reverse=True)
    return enriched, fetch_game_lines(sport), skipped_def, skipped_edge

# =========================
# SESSION STATE
# =========================
_ss = {
    "bankroll": DEFAULT_BANKROLL, "day_start_br": DEFAULT_BANKROLL,
    "session_start": time.time(), "locks": [], "history": [],
    "min_edge": MIN_EDGE_DEFAULT, "skip_defaults": True, "last_sport": "NBA",
    "board_data": [], "games": [], "last_scan_time": None,
    "board_ready": False, "n_skipped_def": 0, "n_skipped_edge": 0,
}
for k, v in _ss.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;margin-bottom:16px;">
        <div style="width:44px;height:44px;background:linear-gradient(135deg,#0ea5a0,#065f5e);
             clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);
             display:inline-flex;align-items:center;justify-content:center;font-size:22px;">⚡</div>
        <div style="font-size:22px;font-weight:700;color:#ffffff;margin-top:6px;letter-spacing:-0.5px;">BetCouncil</div>
        <div style="font-size:11px;color:#4a8a8a;margin-top:2px;">v4.4 · Chairman Mode</div>
    </div>""", unsafe_allow_html=True)
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
    _sport_list = ["NBA", "MLB", "NHL", "WNBA", "NFL"]
    _last = st.session_state.last_sport if st.session_state.last_sport in _sport_list else "NBA"
    sport_sel = st.selectbox("Sport", _sport_list, index=_sport_list.index(_last))
    if st.button("Load Board", width="stretch"):
        with st.spinner(f"Fetching {sport_sel} from PrizePicks..."):
            board, games, n_def, n_edge = load_sport_data(sport_sel)
            st.session_state.board_data = board
            st.session_state.games = games
            st.session_state.last_sport = sport_sel
            st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
            st.session_state.board_ready = True
            st.session_state.n_skipped_def = n_def
            st.session_state.n_skipped_edge = n_edge
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
        _net = sum(h.get("net", 0) for h in st.session_state.history)
        st.metric("Record", f"{_wins}W – {_losses}L")
        _c = "green" if _net >= 0 else "red"
        st.markdown(f'<p style="color:{_c};font-weight:700;font-size:14px;">Net: ${_net:.2f}</p>', unsafe_allow_html=True)
    if st.button("Reset Bankroll", width="stretch"):
        st.session_state.bankroll = DEFAULT_BANKROLL
        st.session_state.day_start_br = DEFAULT_BANKROLL
        st.rerun()

# =========================
# COMMAND BAR
# =========================
pending = len([l for l in st.session_state.locks if l.get("status") == "PENDING"])
dc = get_daily_change()
dc_color = "#0ea5a0" if dc.startswith("+") else "#e04040"
scan_t = st.session_state.last_scan_time or "—"
st.markdown(f"""
<div class="command-bar">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;">
    <div style="font-size:13px;color:#0ea5a0;font-weight:600;">⚡ BetCouncil v4.4 — Chairman Mode</div>
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
    <div class="metric-box"><div class="metric-label">Last Scan</div><div class="metric-value" style="font-size:13px;color:#6a7a8a;">{scan_t}</div></div>
  </div>
</div>""", unsafe_allow_html=True)

# =========================
# TABS
# =========================
tabs = st.tabs(["📋 Summary", "📊 Full Board", "🏟️ Game Lines", "🔒 Locks & Ledger", "📈 History", "⚙️ System"])

# TAB 0 — SUMMARY
with tabs[0]:
    st.markdown("# 🧠 THE BOARD — BETCOUNCIL v4.4")
    today_str = date.today().strftime("%A, %B %d, %Y")
    st.markdown(f"**{st.session_state.last_sport} Slate — {today_str}** | **Scanned:** {scan_t} | **Averages:** {AVERAGES_LAST_UPDATED}")
    st.markdown("🔒 **Source:** PrizePicks API (live) · ESPN Scoreboard · Hardcoded Season Averages")
    st.markdown("---")
    st.markdown("## 🏟️ TODAY'S GAMES")
    if st.session_state.games:
        st.table(pd.DataFrame(st.session_state.games))
    else:
        st.info("No games loaded. Click 'Load Board' in the sidebar.")
    st.markdown("---")
    st.markdown("## 📊 PLAYER PROPS — TOP PICKS")
    board = st.session_state.board_data
    if board:
        top8 = board[:8]
        rows = [{"Player": p["Player"], "Prop": p["Prop"], "Line": p["Line"], "Avg": p["Avg"], "Edge": p["EdgePct"], "Prob": f"{p['Prob']:.1%}", "Wager": f"${p['Wager']:.2f}", "Tier": p["Tier"], "Model": p["Model"]} for p in top8]
        st.table(pd.DataFrame(rows))
    else:
        st.info("No props loaded.")
    st.markdown("---")
    st.markdown("## 🔒 LOCK OF THE DAY")
    sovereign = [p for p in board if p["Tier"] == "SOVEREIGN"]
    elite = [p for p in board if p["Tier"] == "ELITE"]
    approved = [p for p in board if p["Tier"] == "APPROVED"]
    best = (sovereign or elite or approved or [None])[0]
    if best:
        tc = TIER_COLORS.get(best["Tier"], "#0ea5a0")
        st.success(f"🏆 **TOP LOCK:** {best['Player']} OVER {best['Line']} {best['Prop']} — [{best['Tier']}]  Edge: {best['EdgePct']} | Prob: {best['Prob']:.1%} | Wager: ${best['Wager']:.2f} | Model: {best['Model']}")
        if st.button("🔒 Lock This Pick"):
            st.session_state.locks.append({"player": best["Player"], "prop": best["Prop"], "line": best["Line"], "side": "OVER", "wager": best["Wager"], "prob": best["Prob"], "edge": best["Edge"], "tier": best["Tier"], "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")})
            st.success(f"Locked {best['Player']} — Wager: ${best['Wager']:.2f}")
            st.rerun()
    else:
        st.info("Load the board to see today's top lock.")
    st.markdown("---")
    st.markdown("### ⚡ TOP +EV OPPORTUNITIES")
    if board:
        ev_rows = [{"#": i+1, "Player": p["Player"], "Selection": f"OVER {p['Line']} {p['Prop']}", "Edge": p["EdgePct"], "Prob": f"{p['Prob']:.1%}", "Wager": f"${p['Wager']:.2f}", "Tier": p["Tier"]} for i, p in enumerate(board[:5])]
        st.table(pd.DataFrame(ev_rows))
    st.markdown("---")
    st.markdown("### 🎲 DAILY PARLAY BUILDER")
    col_p, col_g = st.columns(2)
    with col_p:
        st.markdown('<div class="parlay-card">', unsafe_allow_html=True)
        st.markdown("**⚡ Player Prop Parlay**")
        top3 = [p for p in board if p["Tier"] in ("SOVEREIGN","ELITE","APPROVED")][:3] if board else []
        if len(top3) >= 2:
            for p in top3:
                st.write(f"• {p['Player']} O{p['Line']} {p['Prop']} ({p['EdgePct']})")
            st.markdown(f"**Est. Payout: +{len(top3)*400+45}**")
        else:
            st.write("Not enough high-confidence props for a parlay.")
        st.markdown('</div>', unsafe_allow_html=True)
    with col_g:
        st.markdown('<div class="game-parlay-card">', unsafe_allow_html=True)
        st.markdown("**🏟️ Today's Matchups**")
        if st.session_state.games:
            for g in st.session_state.games[:4]:
                st.write(f"• {g['Matchup']}")
        else:
            st.write("Load board to see today's games.")
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(f"**Bankroll:** ${st.session_state.bankroll:.2f} · **Unit:** ${active_unit():.2f} · **Session:** {get_session_time()} · **Today:** {get_daily_change()}")

# TAB 1 — FULL BOARD
with tabs[1]:
    st.markdown(f"## 📊 Full Board — {st.session_state.last_sport}")
    if st.session_state.board_data:
        tier_filter = st.multiselect("Filter by Tier", ["SOVEREIGN", "ELITE", "APPROVED", "LEAN"], default=["SOVEREIGN", "ELITE", "APPROVED"])
        filtered = [p for p in st.session_state.board_data if p["Tier"] in tier_filter]
        if filtered:
            df = pd.DataFrame(filtered)
            disp = ["Player","Prop","Line","Avg","Edge","Prob","Wager","Tier","Model","Quality"]
            styled = df[disp].style.format({"Line": "{:.1f}", "Avg": "{:.2f}", "Edge": "{:.1%}", "Prob": "{:.1%}", "Wager": "${:.2f}"}).background_gradient(subset=["Edge"], cmap="RdYlGn")
            st.dataframe(styled, width="stretch")
            st.markdown("---")
            st.markdown("### Lock a Prop")
            options = [f"{r['Player']} — {r['Prop']} OVER {r['Line']}  (Edge: {r['Edge']:.1%} | {r['Tier']} | Wager: ${r['Wager']:.2f})" for r in filtered]
            sel = st.selectbox("Select prop", range(len(options)), format_func=lambda i: options[i])
            if st.button("🔒 Lock Selected"):
                row = filtered[sel]
                st.session_state.locks.append({"player": row["Player"], "prop": row["Prop"], "line": row["Line"], "side": "OVER", "wager": row["Wager"], "prob": row["Prob"], "edge": row["Edge"], "tier": row["Tier"], "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")})
                st.success(f"Locked {row['Player']} — Wager: ${row['Wager']:.2f}")
                st.rerun()
        else:
            st.info("No props match the selected tier filter.")
        st.markdown("---")
        st.markdown("### Tier Breakdown")
        tier_counts = {}
        for p in st.session_state.board_data:
            tier_counts[p["Tier"]] = tier_counts.get(p["Tier"], 0) + 1
        tcols = st.columns(max(len(tier_counts), 1))
        for i, (tier, count) in enumerate(sorted(tier_counts.items())):
            color = TIER_COLORS.get(tier, "#6a7a8a")
            tcols[i].markdown(f'<div class="metric-box"><div class="metric-label">{tier}</div><div class="metric-value" style="color:{color};">{count}</div><div style="font-size:11px;color:#6a7a8a;">{TIER_DESCRIPTIONS.get(tier,"")}</div></div>', unsafe_allow_html=True)
        if st.session_state.n_skipped_def or st.session_state.n_skipped_edge:
            st.markdown("---")
            st.caption(f"ℹ️ {st.session_state.n_skipped_def} unknown players skipped · {st.session_state.n_skipped_edge} below edge threshold")
    else:
        st.info("Select a sport and click **Load Board** in the sidebar.")

# TAB 2 — GAME LINES
with tabs[2]:
    st.markdown(f"## 🏟️ Game Lines — {st.session_state.last_sport}")
    if st.session_state.games:
        st.dataframe(pd.DataFrame(st.session_state.games), width="stretch")
        st.caption("Matchups from ESPN. No spread/total via free API — use sportsbook for live odds.")
    else:
        st.info("No games found. Load the board first, or no games scheduled today.")

# TAB 3 — LOCKS & LEDGER
with tabs[3]:
    st.markdown("## 🔒 Active Locks")
    if st.session_state.locks:
        for i, lock in enumerate(st.session_state.locks.copy()):
            tc = TIER_COLORS.get(lock.get("tier","APPROVED"), "#4a90d9")
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            col1.markdown(f"**{lock['player']}** OVER {lock['line']} {lock['prop']} — <span style='color:{tc};font-weight:700;'>{lock.get('tier','—')}</span> | Wager: **${lock['wager']:.2f}** | Edge: {lock.get('edge',0):.1%} | <span style='color:#5a6a7a;font-size:12px;'>{lock['timestamp']}</span>", unsafe_allow_html=True)
            if col2.button("✅ WIN", key=f"win_{i}"):
                profit = round(lock["wager"] * (100 / 110), 2)
                st.session_state.bankroll += profit
                st.session_state.history.append({**lock, "outcome":"WIN", "profit":profit, "loss":0, "net":profit})
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                st.rerun()
            if col3.button("❌ LOSS", key=f"loss_{i}"):
                st.session_state.bankroll -= lock["wager"]
                st.session_state.history.append({**lock, "outcome":"LOSS", "profit":0, "loss":lock["wager"], "net":-lock["wager"]})
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                st.rerun()
            if col4.button("↩ VOID", key=f"void_{i}"):
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                st.rerun()
    else:
        st.info("No active locks. Go to the Board tab and lock a prop.")
    st.markdown("---")
    st.markdown("## 📒 Ledger Summary")
    if st.session_state.history:
        wins = sum(1 for h in st.session_state.history if h["outcome"] == "WIN")
        total = len(st.session_state.history)
        net = sum(h.get("net", 0) for h in st.session_state.history)
        wagered = sum(h.get("wager", 0) for h in st.session_state.history)
        roi = (net / wagered * 100) if wagered > 0 else 0
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Record", f"{wins}W – {total-wins}L")
        c2.metric("Hit Rate", f"{wins/total:.1%}")
        c3.metric("Net P&L", f"${net:.2f}")
        c4.metric("ROI", f"{roi:.1f}%")
    else:
        st.caption("No settled bets yet.")

# TAB 4 — HISTORY
with tabs[4]:
    st.markdown("## 📈 Full Bet History")
    if st.session_state.history:
        wins = sum(1 for h in st.session_state.history if h["outcome"] == "WIN")
        total = len(st.session_state.history)
        net = sum(h.get("net", 0) for h in st.session_state.history)
        wagered = sum(h.get("wager", 0) for h in st.session_state.history)
        roi = (net / wagered * 100) if wagered > 0 else 0
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Record", f"{wins}W – {total-wins}L")
        c2.metric("Hit Rate", f"{wins/total:.1%}")
        c3.metric("Net P&L", f"${net:.2f}")
        c4.metric("ROI", f"{roi:.1f}%")
        st.markdown("---")
        hist_df = pd.DataFrame(st.session_state.history)
        cols = [c for c in ["timestamp","player","prop","line","side","tier","wager","outcome","net"] if c in hist_df.columns]
        st.dataframe(hist_df[cols], width="stretch")
        if st.button("Clear History"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("No bet history yet.")

# TAB 5 — SYSTEM
with tabs[5]:
    st.markdown("## ⚙️ System Info")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Configuration**")
        st.write(f"Bankroll: ${st.session_state.bankroll:.2f}")
        st.write(f"Min Edge: {st.session_state.min_edge*100:.0f}%")
        st.write(f"Skip unknown players: {st.session_state.skip_defaults}")
        st.write(f"Kelly fraction: {KELLY_FRACTION} (quarter-Kelly)")
        st.write(f"Standard odds: {ODDS}")
        st.write(f"Averages last updated: {AVERAGES_LAST_UPDATED}")
    with c2:
        st.markdown("**Session Stats**")
        st.write(f"Active locks: {len(st.session_state.locks)}")
        st.write(f"History entries: {len(st.session_state.history)}")
        st.write(f"Props loaded: {len(st.session_state.board_data)}")
        st.write(f"Last scan: {st.session_state.last_scan_time or '—'}")
        st.write(f"Session time: {get_session_time()}")
    st.markdown("---")
    st.markdown("**Data Sources**")
    st.write("- Props: PrizePicks public API (20-min cache)")
    st.write("- Game matchups: ESPN scoreboard API (free, no key)")
    bdl_cache = os.path.join(CACHE_DIR, "bdl_nba_avgs.pkl")
    if os.path.exists(bdl_cache):
        age_hours = (time.time() - os.path.getmtime(bdl_cache)) / 3600
        with open(bdl_cache, "rb") as f:
            bdl_data = pickle.load(f)
        st.write(f"- NBA averages: balldontlie live ({len(bdl_data)} players, refreshed {age_hours:.1f}hrs ago)")
    else:
        st.write("- NBA averages: balldontlie (not yet fetched — load NBA board first)")
    st.write("- MLB/NFL/NHL averages: Hardcoded — update PLAYER_AVERAGES dict weekly")
    st.markdown("---")
    st.markdown("**Edge Models**")
    st.write("- **Linear** (PTS, REB, AST, YDS): Edge = -(line − avg) / avg")
    st.write("  Positive when line is set BELOW the player's season average")
    st.write("- **Poisson** (HR, Goals, TD, SO): Poisson distribution for low-frequency events")
    st.write("- **Kelly**: Quarter-Kelly at -110. WIN profit = wager × (100/110)")
    st.markdown("---")
    st.markdown("**Tier System**")
    for tier, color in TIER_COLORS.items():
        st.markdown(f'<span style="color:{color};font-weight:700;">{tier}</span> — {TIER_DESCRIPTIONS[tier]}', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Updating Player Averages**")
    st.write("Edit `PLAYER_AVERAGES` in app.py and update `AVERAGES_LAST_UPDATED`.")
    st.write("Sources: Basketball-Reference · Baseball-Reference · Pro-Football-Reference · Hockey-Reference")
    st.markdown("---")
    st.markdown("**🔍 PrizePicks API Debug**")
    st.caption("Use this to diagnose why props might not be loading.")
    debug_sport = st.selectbox("Test sport", ["NBA","MLB","NHL","WNBA","NFL"], key="debug_sport_sel")
    if st.button("Test PrizePicks API", key="debug_pp"):
        league_ids = {"NBA":4,"MLB":5,"NHL":3,"NFL":7,"WNBA":8}
        lid = league_ids.get(debug_sport, 5)
        test_url = f"https://api.prizepicks.com/projections?league_id={lid}&per_page=250"
        pp_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://app.prizepicks.com/", "Accept": "application/json"}
        try:
            resp = requests.get(test_url, headers=pp_headers, timeout=10)
            st.write(f"**Status code:** {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                n_proj = len(data.get("data", []))
                n_incl = len(data.get("included", []))
                types = list({i.get("type") for i in data.get("included", [])})
                st.write(f"**Projections returned:** {n_proj}")
                st.write(f"**Included objects:** {n_incl}")
                st.write(f"**Included types found:** {types}")
                if n_proj == 0:
                    st.warning("PrizePicks returned 0 projections. No lines posted yet for this sport today.")
                else:
                    st.success(f"✅ {n_proj} projections available — scraper should work.")
                    if data["data"]:
                        st.write("**First projection (raw):**")
                        st.json(data["data"][0])
            elif resp.status_code == 429:
                st.error("429 Rate Limited — wait a few minutes before retrying.")
            else:
                st.error(f"Failed: HTTP {resp.status_code}")
        except Exception as e:
            st.error(f"Request error: {e}")
