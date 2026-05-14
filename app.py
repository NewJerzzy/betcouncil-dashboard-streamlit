import streamlit as st
import pandas as pd
from datetime import datetime
import re
import requests
import time
import hashlib
import pickle
import os
import unicodedata
from math import exp, factorial

st.set_page_config(
    page_title="BetCouncil v4.3",
    page_icon="🛡️",
    layout="wide"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
body, .stApp { background-color: #060c14; color: #e8f0f8; font-family: 'Inter', sans-serif; }
h1 { color: #ffffff; font-size: 26px; font-weight: 700; }
h2 { color: #e0e8f0; font-size: 20px; }
h3 { color: #c0c8d0; font-size: 16px; }
.stButton > button {
    background-color: #0ea5a0; color: #fff; border: none;
    border-radius: 8px; padding: 8px 18px; font-weight: 600;
    transition: all 0.2s;
}
.stButton > button:hover { background-color: #0d9488; transform: translateY(-1px); }
.metric-card {
    background: #0d1520; border: 1px solid #1a2a3a;
    border-radius: 8px; padding: 12px; text-align: center;
}
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS
# =========================
DEFAULT_BANKROLL  = 468.49
KELLY_FRACTION    = 0.25
ODDS              = -110
EDGE_CAP          = 0.20
MIN_EDGE_DEFAULT  = 0.02
REQUEST_TIMEOUT   = 10
CACHE_DIR         = "/tmp/betcouncil_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

AVERAGES_LAST_UPDATED = "2025-05-13"

# =========================
# PLAYER SEASON AVERAGES
# Update this dict weekly.
# Sources: Basketball-Reference, Baseball-Reference, Pro-Football-Reference, Hockey-Reference
# =========================
PLAYER_AVERAGES = {
    "NBA": {
        "LeBron James":              {"PTS": 23.7, "REB": 8.5,  "AST": 8.3,  "PRA": 40.5},
        "Luka Doncic":               {"PTS": 28.1, "REB": 9.3,  "AST": 8.7,  "PRA": 46.1},
        "Nikola Jokic":              {"PTS": 29.4, "REB": 13.0, "AST": 10.2, "PRA": 52.6},
        "Shai Gilgeous-Alexander":   {"PTS": 31.5, "REB": 5.5,  "AST": 6.5,  "PRA": 43.5},
        "Giannis Antetokounmpo":     {"PTS": 30.4, "REB": 11.9, "AST": 6.5,  "PRA": 48.8},
        "Jayson Tatum":              {"PTS": 27.5, "REB": 8.7,  "AST": 4.9,  "PRA": 41.1},
        "Stephen Curry":             {"PTS": 26.4, "REB": 4.5,  "AST": 5.1,  "PRA": 36.0},
        "Kevin Durant":              {"PTS": 27.1, "REB": 6.6,  "AST": 5.0,  "PRA": 38.7},
        "Anthony Davis":             {"PTS": 24.7, "REB": 12.6, "AST": 3.5,  "PRA": 40.8},
        "Damian Lillard":            {"PTS": 24.3, "REB": 4.4,  "AST": 7.0,  "PRA": 35.7},
        "Devin Booker":              {"PTS": 27.1, "REB": 4.5,  "AST": 6.9,  "PRA": 38.5},
        "Donovan Mitchell":          {"PTS": 27.5, "REB": 5.0,  "AST": 5.5,  "PRA": 38.0},
        "Jimmy Butler":              {"PTS": 20.8, "REB": 5.3,  "AST": 5.0,  "PRA": 31.1},
        "Trae Young":                {"PTS": 25.7, "REB": 2.8,  "AST": 10.8, "PRA": 39.3},
        "Domantas Sabonis":          {"PTS": 19.4, "REB": 13.7, "AST": 8.2,  "PRA": 41.3},
        "Karl-Anthony Towns":        {"PTS": 21.8, "REB": 8.3,  "AST": 3.0,  "PRA": 33.1},
        "Bam Adebayo":               {"PTS": 20.4, "REB": 10.2, "AST": 3.5,  "PRA": 34.1},
        "Rudy Gobert":               {"PTS": 14.0, "REB": 12.9, "AST": 1.2,  "PRA": 28.1},
        "Tyrese Haliburton":         {"PTS": 20.1, "REB": 3.8,  "AST": 10.9, "PRA": 34.8},
        "Jalen Brunson":             {"PTS": 28.7, "REB": 3.7,  "AST": 7.4,  "PRA": 39.8},
        "Cade Cunningham":           {"PTS": 25.3, "REB": 6.0,  "AST": 9.0,  "PRA": 40.3},
        "Victor Wembanyama":         {"PTS": 21.4, "REB": 10.6, "AST": 3.9,  "PRA": 35.9},
        "Paolo Banchero":            {"PTS": 22.6, "REB": 6.9,  "AST": 5.4,  "PRA": 34.9},
        "Evan Mobley":               {"PTS": 18.0, "REB": 9.4,  "AST": 2.9,  "PRA": 30.3},
        "Darius Garland":            {"PTS": 20.6, "REB": 2.7,  "AST": 6.7,  "PRA": 30.0},
        "Tobias Harris":             {"PTS": 14.5, "REB": 5.8,  "AST": 2.1,  "PRA": 22.4},
        "Ja Morant":                 {"PTS": 25.1, "REB": 5.6,  "AST": 8.1,  "PRA": 38.8},
        "Zion Williamson":           {"PTS": 22.9, "REB": 5.8,  "AST": 5.0,  "PRA": 33.7},
        "Kawhi Leonard":             {"PTS": 23.7, "REB": 6.1,  "AST": 3.6,  "PRA": 33.4},
        "Pascal Siakam":             {"PTS": 21.3, "REB": 7.8,  "AST": 4.5,  "PRA": 33.6},
        "De'Aaron Fox":              {"PTS": 25.2, "REB": 4.5,  "AST": 5.9,  "PRA": 35.6},
        "Alperen Sengun":            {"PTS": 21.1, "REB": 9.3,  "AST": 5.0,  "PRA": 35.4},
        "Desmond Bane":              {"PTS": 21.5, "REB": 4.8,  "AST": 4.2,  "PRA": 30.5},
        "Scottie Barnes":            {"PTS": 19.9, "REB": 8.2,  "AST": 6.1,  "PRA": 34.2},
        "Franz Wagner":              {"PTS": 19.7, "REB": 5.2,  "AST": 3.7,  "PRA": 28.6},
        "Jalen Williams":            {"PTS": 23.9, "REB": 4.5,  "AST": 5.6,  "PRA": 34.0},
        "Luguentz Dort":             {"PTS": 13.7, "REB": 3.8,  "AST": 1.9,  "PRA": 19.4},
        "Aaron Gordon":              {"PTS": 14.4, "REB": 6.5,  "AST": 3.5,  "PRA": 24.4},
        "Michael Porter Jr.":        {"PTS": 16.7, "REB": 6.9,  "AST": 1.4,  "PRA": 25.0},
        "Jamal Murray":              {"PTS": 21.2, "REB": 4.2,  "AST": 6.5,  "PRA": 31.9},
    },
    "MLB": {
        "Aaron Judge":               {"HR": 0.15, "H": 1.2,  "RBI": 0.9, "R": 0.9},
        "Shohei Ohtani":             {"HR": 0.14, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Mookie Betts":              {"HR": 0.12, "H": 1.2,  "RBI": 0.7, "R": 0.9},
        "Ronald Acuna Jr.":          {"HR": 0.13, "H": 1.2,  "RBI": 0.8, "R": 0.9},
        "Bryce Harper":              {"HR": 0.14, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Juan Soto":                 {"HR": 0.13, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Freddie Freeman":           {"HR": 0.11, "H": 1.2,  "RBI": 0.7, "R": 0.8},
        "Jose Ramirez":              {"HR": 0.12, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Pete Alonso":               {"HR": 0.15, "H": 1.0,  "RBI": 0.9, "R": 0.7},
        "Vladimir Guerrero Jr.":     {"HR": 0.12, "H": 1.2,  "RBI": 0.8, "R": 0.8},
        "Francisco Lindor":          {"HR": 0.12, "H": 1.1,  "RBI": 0.7, "R": 0.8},
        "Corbin Carroll":            {"HR": 0.08, "H": 1.1,  "RBI": 0.5, "R": 0.8},
        "Gunnar Henderson":          {"HR": 0.14, "H": 1.1,  "RBI": 0.8, "R": 0.8},
        "Bobby Witt Jr.":            {"HR": 0.12, "H": 1.2,  "RBI": 0.8, "R": 0.9},
        "Elly De La Cruz":           {"HR": 0.10, "H": 1.0,  "RBI": 0.6, "R": 0.7},
        "Corey Seager":              {"HR": 0.12, "H": 1.1,  "RBI": 0.7, "R": 0.7},
        "Mike Trout":                {"HR": 0.14, "H": 1.0,  "RBI": 0.8, "R": 0.8},
        "Matt Olson":                {"HR": 0.15, "H": 1.0,  "RBI": 0.9, "R": 0.7},
        "Bo Bichette":               {"HR": 0.11, "H": 1.2,  "RBI": 0.7, "R": 0.8},
        "Paul Skenes":               {"SO": 8.5,  "H": 0.3,  "ER": 0.4},
        "Spencer Strider":           {"SO": 9.2,  "H": 0.3,  "ER": 0.5},
        "Gerrit Cole":               {"SO": 8.8,  "H": 0.4,  "ER": 0.5},
        "Zack Wheeler":              {"SO": 8.4,  "H": 0.4,  "ER": 0.5},
        "Tarik Skubal":              {"SO": 9.0,  "H": 0.3,  "ER": 0.4},
        "Logan Webb":                {"SO": 7.2,  "H": 0.5,  "ER": 0.5},
        "Chris Sale":                {"SO": 7.8,  "H": 0.4,  "ER": 0.5},
    },
    "NFL": {
        "Patrick Mahomes":           {"PASS_YDS": 280, "TD": 2.2},
        "Josh Allen":                {"PASS_YDS": 260, "RUSH_YDS": 35,  "TD": 2.5},
        "Jalen Hurts":               {"PASS_YDS": 230, "RUSH_YDS": 45,  "TD": 2.2},
        "Lamar Jackson":             {"PASS_YDS": 220, "RUSH_YDS": 65,  "TD": 2.0},
        "Joe Burrow":                {"PASS_YDS": 270, "TD": 2.0},
        "Justin Herbert":            {"PASS_YDS": 265, "TD": 2.0},
        "Dak Prescott":              {"PASS_YDS": 260, "TD": 2.0},
        "Trevor Lawrence":           {"PASS_YDS": 250, "TD": 1.8},
        "Kirk Cousins":              {"PASS_YDS": 260, "TD": 2.0},
        "Christian McCaffrey":       {"RUSH_YDS": 85,  "REC_YDS": 45,  "TD": 1.0},
        "Derrick Henry":             {"RUSH_YDS": 90,  "TD": 0.9},
        "Saquon Barkley":            {"RUSH_YDS": 80,  "REC_YDS": 35,  "TD": 0.8},
        "Tyreek Hill":               {"REC_YDS": 95,  "TD": 0.8},
        "Justin Jefferson":          {"REC_YDS": 90,  "TD": 0.7},
        "Ja'Marr Chase":             {"REC_YDS": 85,  "TD": 0.7},
        "Travis Kelce":              {"REC_YDS": 70,  "TD": 0.6},
        "CeeDee Lamb":               {"REC_YDS": 92,  "TD": 0.7},
        "Stefon Diggs":              {"REC_YDS": 72,  "TD": 0.5},
        "Davante Adams":             {"REC_YDS": 78,  "TD": 0.6},
        "Cooper Kupp":               {"REC_YDS": 68,  "TD": 0.5},
        "A.J. Brown":                {"REC_YDS": 88,  "TD": 0.7},
        "Deebo Samuel":              {"REC_YDS": 65,  "TD": 0.5},
        "Sam LaPorta":               {"REC_YDS": 58,  "TD": 0.5},
    },
    "NHL": {
        "Connor McDavid":            {"PTS": 1.5,  "GOALS": 0.6, "ASSISTS": 0.9, "SOG": 3.5},
        "Leon Draisaitl":            {"PTS": 1.4,  "GOALS": 0.6, "ASSISTS": 0.8, "SOG": 3.2},
        "Nathan MacKinnon":          {"PTS": 1.4,  "GOALS": 0.5, "ASSISTS": 0.9, "SOG": 3.4},
        "David Pastrnak":            {"PTS": 1.2,  "GOALS": 0.6, "ASSISTS": 0.6, "SOG": 3.5},
        "Nikita Kucherov":           {"PTS": 1.5,  "GOALS": 0.5, "ASSISTS": 1.0, "SOG": 3.0},
        "Auston Matthews":           {"PTS": 1.2,  "GOALS": 0.7, "ASSISTS": 0.5, "SOG": 3.7},
        "Mitch Marner":              {"PTS": 1.2,  "GOALS": 0.4, "ASSISTS": 0.8, "SOG": 2.8},
        "Cale Makar":                {"PTS": 0.9,  "GOALS": 0.2, "ASSISTS": 0.7, "SOG": 2.5},
        "Kirill Kaprizov":           {"PTS": 1.1,  "GOALS": 0.5, "ASSISTS": 0.6, "SOG": 3.2},
        "Mikko Rantanen":            {"PTS": 1.3,  "GOALS": 0.5, "ASSISTS": 0.8, "SOG": 3.0},
        "Brad Marchand":             {"PTS": 0.9,  "GOALS": 0.3, "ASSISTS": 0.6, "SOG": 2.8},
        "Matthew Tkachuk":           {"PTS": 1.1,  "GOALS": 0.4, "ASSISTS": 0.7, "SOG": 3.0},
        "Artemi Panarin":            {"PTS": 1.2,  "GOALS": 0.5, "ASSISTS": 0.7, "SOG": 3.1},
        "Roman Josi":                {"PTS": 0.8,  "GOALS": 0.2, "ASSISTS": 0.6, "SOG": 2.5},
        "Adam Fox":                  {"PTS": 0.9,  "GOALS": 0.2, "ASSISTS": 0.7, "SOG": 2.4},
        "Jake Guentzel":             {"PTS": 0.9,  "GOALS": 0.4, "ASSISTS": 0.5, "SOG": 3.0},
        "Brayden Point":             {"PTS": 1.1,  "GOALS": 0.5, "ASSISTS": 0.6, "SOG": 3.1},
        "Sam Reinhart":              {"PTS": 1.0,  "GOALS": 0.5, "ASSISTS": 0.5, "SOG": 3.0},
        "Aleksander Barkov":         {"PTS": 1.0,  "GOALS": 0.4, "ASSISTS": 0.6, "SOG": 2.8},
        "Elias Pettersson":          {"PTS": 1.0,  "GOALS": 0.4, "ASSISTS": 0.6, "SOG": 2.9},
    },
    "WNBA": {
        "A'ja Wilson":               {"PTS": 26.0, "REB": 9.4,  "AST": 2.4, "PRA": 37.8},
        "Breanna Stewart":           {"PTS": 21.8, "REB": 8.6,  "AST": 3.8, "PRA": 34.2},
        "Sabrina Ionescu":           {"PTS": 19.4, "REB": 4.5,  "AST": 6.3, "PRA": 30.2},
        "Kelsey Plum":               {"PTS": 18.9, "REB": 2.8,  "AST": 4.2, "PRA": 25.9},
        "Napheesa Collier":          {"PTS": 20.1, "REB": 9.3,  "AST": 2.7, "PRA": 32.1},
        "Jackie Young":              {"PTS": 17.3, "REB": 4.1,  "AST": 4.0, "PRA": 25.4},
        "Alyssa Thomas":             {"PTS": 12.5, "REB": 9.2,  "AST": 7.1, "PRA": 28.8},
        "Caitlin Clark":             {"PTS": 19.2, "REB": 5.7,  "AST": 8.4, "PRA": 33.3},
        "Angel Reese":               {"PTS": 13.1, "REB": 13.1, "AST": 1.9, "PRA": 28.1},
        "Jonquel Jones":             {"PTS": 15.5, "REB": 8.4,  "AST": 2.6, "PRA": 26.5},
        "Dearica Hamby":             {"PTS": 14.2, "REB": 8.9,  "AST": 2.5, "PRA": 25.6},
        "Kahleah Copper":            {"PTS": 17.5, "REB": 4.2,  "AST": 2.8, "PRA": 24.5},
        "Aliyah Boston":             {"PTS": 14.0, "REB": 8.0,  "AST": 3.2, "PRA": 25.2},
        "DiJonai Carrington":        {"PTS": 14.8, "REB": 4.9,  "AST": 2.4, "PRA": 22.1},
    },
}

DEFAULT_AVERAGES = {
    "NBA":  {"PTS": 10.0, "REB": 4.0,   "AST": 2.5,   "PRA": 16.5},
    "MLB":  {"HR": 0.05,  "H": 0.8,     "RBI": 0.3,   "R": 0.3,   "SO": 5.0},
    "NFL":  {"PASS_YDS": 200, "RUSH_YDS": 35, "REC_YDS": 40, "TD": 0.5},
    "NHL":  {"PTS": 0.45, "GOALS": 0.18,"ASSISTS": 0.27,"SOG": 1.8},
    "WNBA": {"PTS": 8.0,  "REB": 3.5,   "AST": 2.0,   "PRA": 13.5},
}

# Sport-aware stat name normalization (PrizePicks labels → internal keys)
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

# Stats where Poisson model is more accurate than linear % deviation
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
                return pickle.load(f)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):   # only cache non-empty responses
                with open(cache_path, "wb") as f:
                    pickle.dump(data, f)
            return data
        return None
    except:
        return None

# =========================
# NAME NORMALIZATION
# Handles accents (Acuña → Acuna) and suffixes (Jr., Sr., II, III)
# =========================
def normalize_name(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+(jr|sr|ii|iii)\.?$", "", s.lower().strip())
    return s

def find_player_avg(player_name, avgs_dict):
    """Return (stats_dict, using_default). Tries exact then accent-normalized match."""
    if player_name in avgs_dict:
        return avgs_dict[player_name], False
    norm_target = normalize_name(player_name)
    for key, val in avgs_dict.items():
        if normalize_name(key) == norm_target:
            return val, False
    return {}, True

# =========================
# PRIZEPICKS SCRAPER
# =========================
def scrape_prizepicks(sport):
    league_ids = {
        "NBA": 4, "MLB": 5, "NHL": 3, "NFL": 7,
        "WNBA": 8, "UFC": 6, "Golf": 11, "Tennis": 12, "Soccer": 2,
    }
    league = league_ids.get(sport.upper())
    if not league:
        return []

    # Broad endpoint first (no state restriction), CA-scoped second
    urls = [
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code=CA&game_mode=prizepools",
    ]

    all_props = []
    seen      = set()

    for url in urls:
        data = cached_fetch(url, ttl_minutes=20)
        if not data or not data.get("data"):
            continue

        players = {
            item["id"]: item["attributes"]["name"]
            for item in data.get("included", [])
            if item["type"] == "new_player"
        }
        for proj in data["data"]:
            if proj["type"] != "projection":
                continue
            attrs = proj["attributes"]
            pid   = proj["relationships"]["new_player"]["data"]["id"]
            name  = players.get(pid, "Unknown")
            line  = attrs.get("line_score")
            stat  = attrs.get("stat_type")
            if not (name and line is not None and stat):
                continue
            try:
                line = float(line)
            except:
                continue
            key = (sport, pid, stat, line)
            if key in seen:
                continue
            seen.add(key)
            all_props.append({
                "Player": name,
                "Prop":   stat,
                "Line":   line,
                "Side":   "OVER",
                "Sport":  sport,
                "source": "PrizePicks",
            })

        if all_props:
            break  # got data from first URL, skip second

    return all_props

# =========================
# GAME MATCHUPS — ESPN scoreboard (free, no key needed, no odds)
# =========================
def fetch_game_lines(sport):
    slug_map = {
        "NBA":  "basketball/nba",
        "MLB":  "baseball/mlb",
        "NFL":  "football/nfl",
        "NHL":  "hockey/nhl",
        "WNBA": "basketball/wnba",
    }
    path = slug_map.get(sport, "")
    if not path:
        return []
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return [
                {"Matchup": e.get("shortName", ""), "Status": e.get("status", {}).get("type", {}).get("description", ""), "Sport": sport}
                for e in data.get("events", [])
            ]
    except:
        pass
    return []

# =========================
# EDGE & KELLY
# =========================
def poisson_prob_over(line, avg_per_game):
    """P(X > line) using Poisson distribution. Best for HR, goals, TDs, strikeouts."""
    if avg_per_game <= 0:
        return 0.5
    k = int(line)
    try:
        p_at_or_under = sum(
            (avg_per_game ** i * exp(-avg_per_game)) / factorial(i)
            for i in range(k + 1)
        )
        return round(1 - p_at_or_under, 4)
    except:
        return 0.5

def compute_edge(line, player_avg, side="OVER", stat_key="PTS"):
    if player_avg <= 0:
        return 0.0, 0.5

    if stat_key in POISSON_STATS:
        # Poisson model for low-frequency binary-ish events
        prob = poisson_prob_over(line, player_avg)
        if side.upper() == "UNDER":
            prob = 1 - prob
        edge = prob - 0.5
    else:
        # Linear deviation model for counting stats
        diff  = (line - player_avg) / player_avg
        edge  = -diff if side.upper() == "OVER" else diff
        edge  = max(-EDGE_CAP, min(EDGE_CAP, edge))
        prob  = max(0.30, min(0.70, 0.5 + edge))

    return round(edge, 4), round(prob, 4)

def kelly_unit(prob, bankroll, odds=ODDS):
    if prob <= 0.5:
        return 0.0
    b     = 100 / abs(odds) if odds < 0 else odds / 100
    q     = 1 - prob
    kelly = (b * prob - q) / b
    if kelly <= 0:
        return 0.0
    return round(min(kelly * KELLY_FRACTION * bankroll, bankroll * 0.25), 2)

# =========================
# MAIN LOAD FUNCTION
# =========================
def load_sport_data(sport):
    avgs     = PLAYER_AVERAGES.get(sport, {})
    defaults = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])
    min_edge = st.session_state.min_edge
    skip_def = st.session_state.skip_defaults

    props = scrape_prizepicks(sport)
    if not props:
        return [], fetch_game_lines(sport), 0, 0

    enriched     = []
    skipped_def  = 0
    skipped_edge = 0

    for p in props:
        stat_raw  = p["Prop"]
        stat_norm = STAT_NORMALIZE.get((sport, stat_raw), stat_raw)
        player    = p["Player"]
        side      = p["Side"]

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

        enriched.append({
            "Player":  player,
            "Prop":    stat_raw,
            "Line":    p["Line"],
            "Avg":     avg,
            "Edge":    edge,
            "Prob":    prob,
            "Wager":   kelly_unit(prob, st.session_state.bankroll),
            "Quality": "Lookup" if not using_default else "Default",
            "Model":   "Poisson" if stat_norm in POISSON_STATS else "Linear",
        })

    enriched.sort(key=lambda x: x["Edge"], reverse=True)
    return enriched, fetch_game_lines(sport), skipped_def, skipped_edge

# =========================
# SESSION STATE INIT
# =========================
_ss_defaults = {
    "bankroll":      DEFAULT_BANKROLL,
    "locks":         [],
    "history":       [],
    "min_edge":      MIN_EDGE_DEFAULT,
    "skip_defaults": True,
    "last_sport":    "NBA",
    "board_data":    [],
    "games":         [],
}
for _k, _v in _ss_defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("# 🛡️ BetCouncil v4.3")
    st.markdown(f"*Averages updated: {AVERAGES_LAST_UPDATED}*")
    st.markdown("---")

    st.session_state.bankroll = st.number_input(
        "Bankroll ($)", value=float(st.session_state.bankroll), step=10.0
    )
    st.session_state.min_edge = st.slider(
        "Min Edge (%)", 0, 15,
        int(st.session_state.min_edge * 100), step=1
    ) / 100.0
    st.session_state.skip_defaults = st.checkbox(
        "Skip unknown players",
        value=st.session_state.skip_defaults
    )

    st.markdown("---")
    _sport_list = ["NBA", "MLB", "NHL", "WNBA", "NFL"]
    _last = st.session_state.last_sport if st.session_state.last_sport in _sport_list else "NBA"
    sport = st.selectbox("Sport", _sport_list, index=_sport_list.index(_last))

    if st.button("Load Board", use_container_width=True):
        with st.spinner(f"Fetching {sport} props from PrizePicks..."):
            board, games, n_def, n_edge = load_sport_data(sport)
            st.session_state.board_data = board
            st.session_state.games      = games
            st.session_state.last_sport = sport
        if board:
            st.success(f"{len(board)} props found")
            if n_def:
                st.info(f"{n_def} unknown players skipped")
            if n_edge:
                st.caption(f"{n_edge} props below edge threshold")
        else:
            st.warning(
                "No props returned. PrizePicks may not have lines posted yet "
                "for today's slate. Try again closer to game time."
            )

    st.markdown("---")
    st.metric("Bankroll", f"${st.session_state.bankroll:.2f}")

    _wins   = sum(1 for h in st.session_state.history if h.get("outcome") == "WIN")
    _losses = sum(1 for h in st.session_state.history if h.get("outcome") == "LOSS")
    if _wins + _losses > 0:
        st.metric("Record", f"{_wins}W – {_losses}L")
        _net   = sum(h.get("net", 0) for h in st.session_state.history)
        _color = "green" if _net >= 0 else "red"
        st.markdown(
            f'<p style="color:{_color};font-weight:700;">Net P&L: ${_net:.2f}</p>',
            unsafe_allow_html=True
        )

    if st.button("Reset Bankroll", use_container_width=True):
        st.session_state.bankroll = DEFAULT_BANKROLL
        st.rerun()

# =========================
# MAIN TABS
# =========================
tabs = st.tabs(["📊 Props", "🏟️ Games", "🔒 Locks", "📈 History", "⚙️ System"])

# ---- PROPS ----
with tabs[0]:
    st.markdown(f"## Props — {st.session_state.last_sport}")

    if st.session_state.board_data:
        df = pd.DataFrame(st.session_state.board_data)

        styled = df.style.format({
            "Line":  "{:.1f}",
            "Avg":   "{:.2f}",
            "Edge":  "{:.1%}",
            "Prob":  "{:.1%}",
            "Wager": "${:.2f}",
        }).background_gradient(subset=["Edge"], cmap="RdYlGn")

        st.dataframe(styled, use_container_width=True)

        st.markdown("### Lock a Prop")
        options = [
            f"{r['Player']} — {r['Prop']} OVER {r['Line']}  "
            f"(Edge: {r['Edge']:.1%} | Wager: ${r['Wager']:.2f} | {r['Model']})"
            for r in st.session_state.board_data
        ]
        sel = st.selectbox("Select prop", range(len(options)),
                           format_func=lambda i: options[i])
        if st.button("🔒 Lock Selected"):
            row = st.session_state.board_data[sel]
            st.session_state.locks.append({
                "player":    row["Player"],
                "prop":      row["Prop"],
                "line":      row["Line"],
                "side":      "OVER",
                "wager":     row["Wager"],
                "prob":      row["Prob"],
                "edge":      row["Edge"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            st.success(
                f"Locked {row['Player']} {row['Prop']} OVER {row['Line']} "
                f"— Wager: ${row['Wager']:.2f}"
            )
            st.rerun()
    else:
        st.info("Select a sport and click **Load Board** in the sidebar.")

# ---- GAMES ----
with tabs[1]:
    st.markdown(f"## Games Today — {st.session_state.last_sport}")
    if st.session_state.games:
        st.dataframe(pd.DataFrame(st.session_state.games), use_container_width=True)
        st.caption("Matchups from ESPN. No odds — use your sportsbook for live lines.")
    else:
        st.info("No games found. Load the board first, or no games scheduled today.")

# ---- LOCKS ----
with tabs[2]:
    st.markdown("## Active Locks")
    if st.session_state.locks:
        for i, lock in enumerate(st.session_state.locks.copy()):
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            col1.write(
                f"**{lock['player']}** {lock['side']} {lock['line']} {lock['prop']} "
                f"— Wager: **${lock['wager']:.2f}** | Edge: {lock['edge']:.1%}"
            )
            if col2.button("✅ WIN", key=f"win_{i}"):
                profit = round(lock["wager"] * (100 / 110), 2)
                st.session_state.bankroll += profit
                st.session_state.history.append({
                    **lock,
                    "outcome": "WIN",
                    "profit":  profit,
                    "loss":    0,
                    "net":     profit,
                })
                st.session_state.locks = [
                    l for j, l in enumerate(st.session_state.locks) if j != i
                ]
                st.rerun()
            if col3.button("❌ LOSS", key=f"loss_{i}"):
                st.session_state.bankroll -= lock["wager"]
                st.session_state.history.append({
                    **lock,
                    "outcome": "LOSS",
                    "profit":  0,
                    "loss":    lock["wager"],
                    "net":     -lock["wager"],
                })
                st.session_state.locks = [
                    l for j, l in enumerate(st.session_state.locks) if j != i
                ]
                st.rerun()
            if col4.button("↩ VOID", key=f"void_{i}"):
                st.session_state.locks = [
                    l for j, l in enumerate(st.session_state.locks) if j != i
                ]
                st.rerun()
    else:
        st.info("No active locks. Go to Props tab and lock a selection.")

# ---- HISTORY ----
with tabs[3]:
    st.markdown("## Bet History")
    if st.session_state.history:
        _wins  = sum(1 for h in st.session_state.history if h["outcome"] == "WIN")
        _total = len(st.session_state.history)
        _net   = sum(h.get("net", 0) for h in st.session_state.history)
        _wagered = sum(h.get("wager", 0) for h in st.session_state.history)
        _roi   = (_net / _wagered * 100) if _wagered > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Record",   f"{_wins}W – {_total - _wins}L")
        c2.metric("Hit Rate", f"{_wins / _total:.1%}")
        c3.metric("Net P&L",  f"${_net:.2f}")
        c4.metric("ROI",      f"{_roi:.1f}%")

        st.markdown("---")
        hist_df = pd.DataFrame(st.session_state.history)
        _cols   = [c for c in
                   ["timestamp", "player", "prop", "line", "side", "wager", "outcome", "net"]
                   if c in hist_df.columns]
        st.dataframe(hist_df[_cols], use_container_width=True)

        if st.button("Clear History"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("No bet history yet. Lock and resolve props to build your record.")

# ---- SYSTEM ----
with tabs[4]:
    st.markdown("## System Info")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Bankroll:** ${st.session_state.bankroll:.2f}")
        st.write(f"**Min Edge:** {st.session_state.min_edge * 100:.0f}%")
        st.write(f"**Skip unknown players:** {st.session_state.skip_defaults}")
        st.write(f"**Averages last updated:** {AVERAGES_LAST_UPDATED}")
    with c2:
        st.write(f"**Active locks:** {len(st.session_state.locks)}")
        st.write(f"**History entries:** {len(st.session_state.history)}")
        st.write(f"**Kelly fraction:** {KELLY_FRACTION} (quarter-Kelly)")
        st.write(f"**Standard odds:** {ODDS}")

    st.markdown("---")
    st.markdown("**Data Sources**")
    st.write("- Props: PrizePicks public API (20-min cache, no API key needed)")
    st.write("- Game matchups: ESPN scoreboard API (free, no key needed)")
    st.write("- Player averages: Hardcoded lookup — update `PLAYER_AVERAGES` dict weekly")

    st.markdown("---")
    st.markdown("**Edge Models**")
    st.write("- **Linear:** Counting stats (PTS, REB, AST, YDS). Edge = -(line - avg)/avg")
    st.write("- **Poisson:** Low-frequency events (HR, Goals, TD, SO). Uses Poisson distribution.")
    st.write("- **Kelly:** Quarter-Kelly sizing at standard -110 odds")
    st.write("- **WIN profit:** wager × (100/110). LOSS deducts full wager.")

    st.markdown("---")
    st.markdown("**Updating Averages**")
    st.write("Edit `PLAYER_AVERAGES` in `app.py` and update `AVERAGES_LAST_UPDATED`.")
    st.write("Sources: [Basketball-Reference](https://www.basketball-reference.com) · "
             "[Baseball-Reference](https://www.baseball-reference.com) · "
             "[Pro-Football-Reference](https://www.pro-football-reference.com) · "
             "[Hockey-Reference](https://www.hockey-reference.com)")
