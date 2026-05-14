import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import re
import requests
import time
import hashlib
import pickle
import os
import json
import unicodedata
from math import exp, factorial

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
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
ODDS = -110
EDGE_CAP = 0.20
MIN_EDGE_DEFAULT = 0.02
REQUEST_TIMEOUT = 10
CACHE_DIR = "/tmp/betcouncil_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
AVERAGES_LAST_UPDATED = "2025-05-13"

# JSON persistence paths
HISTORY_PATH = os.path.join(CACHE_DIR, "history.json")
LOCKS_PATH = os.path.join(CACHE_DIR, "locks.json")
BANKROLL_PATH = os.path.join(CACHE_DIR, "bankroll.json")
CALIBRATION_PATH = os.path.join(CACHE_DIR, "calibration.json")

TIER_COLORS = {"SOVEREIGN": "#e8a020", "ELITE": "#0ea5a0", "APPROVED": "#4a90d9", "LEAN": "#7a8a9a", "PASS": "#e04040"}
TIER_DESCRIPTIONS = {"SOVEREIGN": "Edge ≥ 15%", "ELITE": "Edge ≥ 10%", "APPROVED": "Edge ≥ 5%", "LEAN": "Edge ≥ 2%", "PASS": "Edge < 2%"}

SPORTS = ["NBA", "MLB", "NHL", "WNBA", "NFL", "Soccer", "UFC", "Golf", "Tennis"]

# Hardcoded baselines for Soccer and UFC
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

# Home/Away adjustments (NBA)
HOME_BOOST = {"PTS": 1.5, "REB": 0.5, "AST": 0.4, "PRA": 2.4}
AWAY_PENALTY = {"PTS": -1.5, "REB": -0.5, "AST": -0.4, "PRA": -2.4}

# Teammate out usage spikes
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

# Expanded player-to-team mapping
PLAYER_TEAM_MAP = {
    "LeBron James": "LAL", "Anthony Davis": "LAL", "Austin Reaves": "LAL", "D'Angelo Russell": "LAL",
    "Luka Doncic": "DAL", "Kyrie Irving": "DAL", "Tim Hardaway Jr.": "DAL", "Derrick Jones Jr.": "DAL",
    "Nikola Jokic": "DEN", "Jamal Murray": "DEN", "Michael Porter Jr.": "DEN", "Aaron Gordon": "DEN",
    "Shai Gilgeous-Alexander": "OKC", "Jalen Williams": "OKC", "Chet Holmgren": "OKC", "Luguentz Dort": "OKC",
    "Giannis Antetokounmpo": "MIL", "Damian Lillard": "MIL", "Khris Middleton": "MIL", "Brook Lopez": "MIL",
    "Jayson Tatum": "BOS", "Jaylen Brown": "BOS", "Kristaps Porzingis": "BOS", "Derrick White": "BOS",
    "Stephen Curry": "GSW", "Klay Thompson": "GSW", "Draymond Green": "GSW", "Andrew Wiggins": "GSW",
    "Kevin Durant": "PHX", "Devin Booker": "PHX", "Bradley Beal": "PHX", "Jusuf Nurkic": "PHX",
    "Donovan Mitchell": "CLE", "Darius Garland": "CLE", "Evan Mobley": "CLE", "Jarrett Allen": "CLE",
    "Jimmy Butler": "MIA", "Bam Adebayo": "MIA", "Tyler Herro": "MIA", "Caleb Martin": "MIA",
    "Trae Young": "ATL", "Dejounte Murray": "ATL", "Clint Capela": "ATL", "Bogdan Bogdanovic": "ATL",
    "Ja Morant": "MEM", "Jaren Jackson Jr.": "MEM", "Desmond Bane": "MEM", "Marcus Smart": "MEM",
    "Zion Williamson": "NOP", "Brandon Ingram": "NOP", "CJ McCollum": "NOP", "Jonas Valanciunas": "NOP",
    "Kawhi Leonard": "LAC", "Paul George": "LAC", "James Harden": "LAC", "Russell Westbrook": "LAC",
    "Joel Embiid": "PHI", "Tyrese Maxey": "PHI", "Tobias Harris": "PHI", "Kelly Oubre Jr.": "PHI",
    "Karl-Anthony Towns": "MIN", "Anthony Edwards": "MIN", "Rudy Gobert": "MIN", "Mike Conley": "MIN",
    "Domantas Sabonis": "SAC", "De'Aaron Fox": "SAC", "Keegan Murray": "SAC", "Harrison Barnes": "SAC",
    "Victor Wembanyama": "SAS", "Cade Cunningham": "DET", "Jalen Brunson": "NYK", "Paolo Banchero": "ORL",
    "Scottie Barnes": "TOR", "Alperen Sengun": "HOU", "Franz Wagner": "ORL", "Tyrese Haliburton": "IND",
    "Pascal Siakam": "IND", "De'Aaron Fox": "SAC", "Kawhi Leonard": "LAC", "Zion Williamson": "NOP",
    "Jalen Williams": "OKC", "Desmond Bane": "MEM", "Scottie Barnes": "TOR", "Franz Wagner": "ORL",
}

# =========================
# PERSISTENCE LAYER
# =========================
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

# =========================
# SEM CALIBRATION FUNCTIONS
# =========================
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

# =========================
# HELPER FUNCTIONS
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
    return f"{'+' if change >= 0 else ''}{change:.1f}%"

# =========================
# WEIGHTED AVERAGE
# =========================
def get_weighted_average(player_name, season_avg, last10_avg, is_playoff=False):
    if last10_avg is None:
        return season_avg
    if is_playoff:
        return last10_avg
    return {
        "PTS": round(last10_avg.get("PTS", season_avg.get("PTS", 0)) * 0.7 + season_avg.get("PTS", 0) * 0.3, 1),
        "REB": round(last10_avg.get("REB", season_avg.get("REB", 0)) * 0.7 + season_avg.get("REB", 0) * 0.3, 1),
        "AST": round(last10_avg.get("AST", season_avg.get("AST", 0)) * 0.7 + season_avg.get("AST", 0) * 0.3, 1),
        "PRA": round(last10_avg.get("PRA", season_avg.get("PRA", 0)) * 0.7 + season_avg.get("PRA", 0) * 0.3, 1),
    }

# =========================
# NBA ROLLING AVERAGES — NBA STATS API
# =========================
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

                if player_name and pts is not None:
                    rolling[player_name] = {
                        "PTS": round(float(pts), 1),
                        "REB": round(float(reb), 1),
                        "AST": round(float(ast), 1),
                        "PRA": round(float(pts) + float(reb) + float(ast), 1),
                    }

            if rolling:
                break

        except Exception:
            continue

    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)

    return rolling

# =========================
# NBA TEAM DEFENSIVE RATINGS
# =========================
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

# =========================
# BALLDONTLIE API (Season Averages)
# =========================
BDL_API_KEY = "9d7c9ea5-54ea-4084-b0d0-2541ac7c360d"
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
# UNDERDOG PROPS FETCH (IMPROVED VERSION)
# =========================
def fetch_underdog_props(sport):
    sport_map = {"NBA": "NBA", "MLB": "MLB", "NHL": "NHL", 
                 "NFL": "NFL", "WNBA": "WNBA"}
    sport_id = sport_map.get(sport)
    if not sport_id:
        return []
    
    url = f"https://api.underdogfantasy.com/v2/over_under_lines?sport_id={sport_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        
        # Build player lookup from first/last name
        players = {
            p["id"]: f"{p.get('first_name','').strip()} {p.get('last_name','').strip()}".strip()
            for p in data.get("players", [])
        }
        
        # Build stat type name lookup
        stats_map = {
            s["id"]: s.get("display_name", s.get("name", ""))
            for s in data.get("stat_types", [])
        }
        
        # Build appearance lookup
        appearances = {
            a["id"]: a.get("player_id")
            for a in data.get("appearances", [])
        }
        
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
            
            props.append({
                "Player": name,
                "Prop": stat_name,
                "Line": float(line_val),
                "Side": "OVER",
                "Sport": sport,
                "source": "Underdog"
            })
        return props
    except Exception as e:
        print(f"Underdog props error: {e}")
        return []

# =========================
# PRIZEPICKS SCRAPER (with Underdog fallback)
# =========================
def scrape_prizepicks(sport):
    league_ids = {"NBA": 4, "MLB": 5, "NHL": 3, "NFL": 7, "WNBA": 8, "UFC": 6, "Golf": 11, "Tennis": 12, "Soccer": 2}
    league = league_ids.get(sport.upper())
    if not league:
        return []
    urls = [
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&state_code=CA",
    ]
    pp_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://app.prizepicks.com/", "Accept": "application/json", "X-Device-ID": "betcouncil-app"}
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
            all_props.append({"Player": name, "Prop": stat, "Line": line, "Side": "OVER", "Sport": sport, "source": "PrizePicks"})
    
    if all_props:
        return all_props
    # PrizePicks empty — try Underdog as fallback
    st.info("PrizePicks unavailable — trying Underdog Fantasy...")
    return fetch_underdog_props(sport)

# =========================
# UNDERDOG INJURIES FETCH
# =========================
def fetch_underdog_injuries(sport):
    """Fetch injury news from Underdog Fantasy API as fallback."""
    sport_map = {"NBA": "NBA", "MLB": "MLB", 
                 "NFL": "NFL", "NHL": "NHL"}
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
            if "out" in content and "ruled out" in content:
                injuries[name] = "Out"
            elif "questionable" in content or "day-to-day" in content:
                injuries[name] = "Questionable"
        return injuries
    except Exception as e:
        print(f"Underdog injuries error: {e}")
        return {}

# =========================
# ESPN INJURY FETCH (with Underdog merge)
# =========================
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
    
    # Merge Underdog injuries as fallback (Underdog overwrites ESPN on conflict)
    underdog_injuries = fetch_underdog_injuries(sport)
    injuries.update(underdog_injuries)
    return injuries

# =========================
# ESPN GAME LINES (with odds extraction)
# =========================
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
                        # Extract odds from ESPN response
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
                    
                    games.append({
                        "Matchup": matchup,
                        "Status": status,
                        "Spread": spread,
                        "Total": total,
                        "Home ML": home_ml,
                        "Away ML": away_ml,
                        "Odds Source": provider,
                        "Date": target_date.strftime("%a %b %d"),
                        "Sport": sport
                    })
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

# =========================
# MULTI-SIGNAL EDGE CALCULATION
# =========================
def compute_multi_signal_edge(line, player_avg, opp_def_rating, is_home, teammate_out_boost, side="OVER", stat_key="PTS"):
    """
    Combine 4 signals into a single edge.
    Weights: base 55%, defense 30%, location 15%
    """
    if player_avg <= 0:
        return 0.0, 0.5, {}
    
    signals = {}
    league_avg_def = 112.0
    
    # Signal 1: Base (line vs player average) — weight 55%
    if stat_key in ["HR", "GOALS", "TD", "SO"]:
        prob = poisson_prob_over(line, player_avg)
        if side.upper() == "UNDER":
            prob = 1 - prob
        base_edge = prob - 0.5
    else:
        diff = (line - player_avg) / player_avg
        if side.upper() == "OVER":
            base_edge = -diff
        else:  # UNDER
            base_edge = diff
    signals["base"] = base_edge
    
    # Signal 2: Opponent defense adjustment (30%)
    if opp_def_rating > 0:
        def_adj = (opp_def_rating - league_avg_def) / league_avg_def
        if side.upper() == "OVER":
            signals["defense"] = -def_adj * 0.30
        else:
            signals["defense"] = def_adj * 0.30
    else:
        signals["defense"] = 0
    
    # Signal 3: Home/away adjustment (15%)
    if side.upper() == "OVER":
        location_adj = 0.05 if is_home else -0.05
    else:
        location_adj = -0.05 if is_home else 0.05
    signals["location"] = location_adj
    
    # Signal 4: Teammate out usage spike (bonus)
    usage_adj = teammate_out_boost if teammate_out_boost else 0.0
    signals["usage"] = usage_adj
    
    # Weighted combination
    weights = {"base": 0.55, "defense": 0.30, "location": 0.15, "usage": 0.0}
    combined = (signals["base"] * weights["base"] + 
                signals["defense"] * weights["defense"] + 
                signals["location"] * weights["location"])
    if usage_adj:
        combined += usage_adj * 0.10
    
    combined = max(-EDGE_CAP, min(EDGE_CAP, combined))
    prob = max(0.30, min(0.70, 0.5 + combined))
    
    return combined, prob, signals

# =========================
# MAIN LOAD FUNCTION
# =========================
def load_sport_data(sport):
    min_edge = st.session_state.min_edge
    skip_def = st.session_state.skip_defaults

    if sport in ["Golf", "Tennis"]:
        props = scrape_prizepicks(sport)
        if not props:
            return [], [], 0, 0
        enriched = []
        for p in props:
            enriched.append({"Player": p["Player"], "Prop": p["Prop"], "Line": p["Line"], "Side": "OVER",
                             "Edge": 0, "EdgePct": "N/A", "Prob": 0.5, "Wager": 0, "Tier": "N/A",
                             "Model": "N/A", "Sport": sport, "Avg": 0, "Injury": "", "SEM": "—", "SEM_n": 0,
                             "SignalBase": 0, "SignalDefense": 0, "SignalLocation": 0, "SignalUsage": 0})
        return enriched, [], 0, 0

    rolling_avgs = {}
    team_defense = {}
    if sport == "NBA":
        rolling_avgs = fetch_nba_rolling_averages()
        team_defense = fetch_nba_team_defense()
        live_avgs = fetch_nba_averages_bdl()
        season_avgs = {**PLAYER_AVERAGES.get("NBA", {}), **live_avgs}
    else:
        season_avgs = PLAYER_AVERAGES.get(sport, {})

    defaults = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])
    props = scrape_prizepicks(sport)
    if not props:
        games, _, _, _ = fetch_game_lines(sport)
        return [], games, 0, 0

    injuries = fetch_injury_news(sport) if sport in ["NBA", "MLB", "NFL", "NHL"] else {}
    games, is_playoff, home_teams, away_teams = fetch_game_lines(sport)

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

        if sport == "NBA" and player in season_avgs:
            season_avg = season_avgs.get(player, {})
            last10 = rolling_avgs.get(player, None)
            avg_dict = get_weighted_average(player, season_avg, last10, is_playoff)
            using_default = False
        else:
            player_stats, using_default = find_player_avg(player, season_avgs)
            if using_default:
                skipped_def += 1
                if skip_def:
                    continue
                avg_dict = {stat_norm: defaults.get(stat_norm, line)}
            else:
                avg_dict = player_stats
            avg_dict = {k: v for k, v in avg_dict.items()}

        avg = avg_dict.get(stat_norm, defaults.get(stat_norm, line))

        # Determine opponent and defensive rating
        player_team = PLAYER_TEAM_MAP.get(player, "")
        opp_def_rating = 112.0
        if player_team and games:
            for game in games:
                matchup = game["Matchup"]
                if player_team in matchup:
                    parts = matchup.replace("@", "vs").split()
                    for p2 in parts:
                        if p2 != player_team and len(p2) <= 3 and p2.isalpha():
                            opp_def_rating = team_defense.get(p2, 112.0)
                            break
                    break

        # Home/away flag
        is_home = False
        if player_team and games:
            for matchup, home in home_teams.items():
                if player_team == home:
                    is_home = True
                    break

        # Teammate out boost
        usage_boost = 0.0
        if player in TEAMMATE_OUT_BOOST:
            out_player = TEAMMATE_OUT_BOOST[player].get("out_player")
            if out_player and any(out_player.lower() in inj.lower() for inj in injuries.keys()):
                usage_boost = TEAMMATE_OUT_BOOST[player].get(stat_norm, 0) / 100
                if usage_boost > 0.10:
                    usage_boost = 0.10

        # Evaluate both OVER and UNDER
        best_edge = -1
        best_side = side
        best_prob = 0.5
        best_signals = {}
        
        for test_side in ["OVER", "UNDER"]:
            combined_edge, prob, signals = compute_multi_signal_edge(
                line, avg, opp_def_rating, is_home, usage_boost, test_side, stat_norm
            )
            if combined_edge > best_edge:
                best_edge = combined_edge
                best_side = test_side
                best_prob = prob
                best_signals = signals

        # Apply SEM calibration adjustment
        adj_edge, calibrated = adjusted_edge(best_edge, sport, get_tier(best_edge), stat_norm, history)
        final_edge = adj_edge if calibrated else best_edge

        if final_edge < min_edge:
            skipped_edge += 1
            continue

        tier = get_tier(final_edge)
        injury_flag = injuries.get(player, "")
        sem_display, sem_n = compute_sem_for_tier(tier_stats, tier)

        enriched.append({"Player": player, "Prop": stat_raw, "Line": line, "Side": best_side, "Avg": avg,
                         "Edge": final_edge, "EdgePct": f"{final_edge:.1%}", "Prob": best_prob,
                         "Wager": kelly_unit(best_prob, st.session_state.bankroll), "Tier": tier,
                         "Quality": "Lookup" if not using_default else "Default",
                         "Model": "MultiSignal",
                         "Sport": sport, "Injury": injury_flag, "SEM": sem_display, "SEM_n": sem_n,
                         "SignalBase": best_signals.get("base", 0), "SignalDefense": best_signals.get("defense", 0),
                         "SignalLocation": best_signals.get("location", 0), "SignalUsage": best_signals.get("usage", 0)})

    enriched.sort(key=lambda x: x["Edge"], reverse=True)
    return enriched, games, skipped_def, skipped_edge

# =========================
# HARDCODED FALLBACK AVERAGES
# =========================
PLAYER_AVERAGES.update({
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
}

# =========================
# SESSION STATE & PERSISTENCE
# =========================
_ss = {"bankroll": DEFAULT_BANKROLL, "day_start_br": DEFAULT_BANKROLL, "session_start": time.time(),
       "locks": [], "history": [], "min_edge": MIN_EDGE_DEFAULT, "skip_defaults": True, "last_sport": "NBA",
       "board_data": [], "games": [], "last_scan_time": None, "board_ready": False, "n_skipped_def": 0, "n_skipped_edge": 0}
for k, v in _ss.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "persistence_loaded" not in st.session_state:
    st.session_state.bankroll = load_json_data(BANKROLL_PATH, DEFAULT_BANKROLL)
    st.session_state.day_start_br = st.session_state.bankroll
    st.session_state.history = load_json_data(HISTORY_PATH, [])
    st.session_state.locks = load_json_data(LOCKS_PATH, [])
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
        with st.spinner(f"Fetching {sport_sel} from PrizePicks/Underdog..."):
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
        st.markdown(f'<p style="color:{_c};font-weight:700;">Net: ${_net:.2f}</p>', unsafe_allow_html=True)
    if st.button("Reset Bankroll", width="stretch"):
        st.session_state.bankroll = DEFAULT_BANKROLL
        st.session_state.day_start_br = DEFAULT_BANKROLL
        save_json_data(BANKROLL_PATH, st.session_state.bankroll)
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
    <div class="metric-box"><div class="metric-label">Last Scan</div><div class="metric-value" style="font-size:13px;">{scan_t}</div></div>
  </div>
</div>""", unsafe_allow_html=True)

# =========================
# TABS (ALL 6 FULLY IMPLEMENTED)
# =========================
tabs = st.tabs(["📋 Summary", "📊 Full Board", "🏟️ Game Lines", "🔒 Locks & Ledger", "📈 History", "⚙️ System"])

# ----- TAB 0: SUMMARY -----
with tabs[0]:
    st.markdown("# 🧠 THE BOARD — BETCOUNCIL v4.6")
    today_str = date.today().strftime("%A, %B %d, %Y")
    st.markdown(f"**{st.session_state.last_sport} Slate — {today_str}** | **Scanned:** {scan_t} | **Edge Model:** Multi‑Signal (4 signals)")
    st.markdown("🔒 **Sources:** PrizePicks (primary) · Underdog (fallback) · ESPN Odds")
    st.markdown("---")
    st.markdown("## 🏟️ TODAY'S GAMES")
    if st.session_state.games:
        df_games = pd.DataFrame(st.session_state.games)
        display_cols = ["Matchup", "Status", "Spread", "Total", "Home ML", "Away ML", "Date"]
        display_cols = [c for c in display_cols if c in df_games.columns]
        st.table(df_games[display_cols])
    else:
        st.info("No games loaded. Click 'Load Board' in the sidebar.")
    st.markdown("---")
    st.markdown("## 📊 PLAYER PROPS — TOP PICKS")
    board = st.session_state.board_data
    if board:
        top8 = board[:8]
        rows = []
        for p in top8:
            injury_badge = f' <span class="injury-badge">{p.get("Injury", "")}</span>' if p.get("Injury") else ""
            sem_class = "sem-green" if p.get("SEM_n", 0) >= 20 else "sem-yellow" if p.get("SEM_n", 0) >= 5 else "sem-gray"
            sem_html = f'<span class="{sem_class}">{p.get("SEM", "—")}</span>' if p.get("SEM") != "—" else "—"
            rows.append({"Player": p["Player"] + injury_badge, "Prop": f"{p['Side']} {p['Line']} {p['Prop']}",
                         "Edge": p["EdgePct"], "Tier": p["Tier"], "SEM": sem_html})
        st.markdown(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.info("No props loaded.")
    st.markdown("---")
    st.markdown("## 🔒 LOCK OF THE DAY")
    best = next((p for p in board if p["Tier"] in ["SOVEREIGN", "ELITE", "APPROVED"]), None)
    if best:
        st.success(f"🏆 **TOP LOCK:** {best['Player']} {best['Side']} {best['Line']} {best['Prop']} — [{best['Tier']}]  Edge: {best['EdgePct']} | SEM: {best.get('SEM', '—')}")
        if st.button("🔒 Lock This Pick"):
            st.session_state.locks.append({"player": best["Player"], "prop": best["Prop"], "line": best["Line"], "side": best["Side"],
                                           "wager": best["Wager"], "prob": best["Prob"], "edge": best["Edge"], "tier": best["Tier"],
                                           "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "sport": best["Sport"]})
            save_json_data(LOCKS_PATH, st.session_state.locks)
            st.rerun()
    else:
        st.info("Load the board to see today's top lock.")
    st.markdown("---")
    st.markdown(f"**Bankroll:** ${st.session_state.bankroll:.2f} · **Unit:** ${active_unit():.2f} · **Session:** {get_session_time()} · **Today:** {get_daily_change()}")

# ----- TAB 1: FULL BOARD -----
with tabs[1]:
    st.markdown(f"## 📊 Full Board — {st.session_state.last_sport}")
    if st.session_state.board_data:
        tier_filter = st.multiselect("Filter by Tier", ["SOVEREIGN", "ELITE", "APPROVED", "LEAN"], default=["SOVEREIGN", "ELITE", "APPROVED"])
        filtered = [p for p in st.session_state.board_data if p["Tier"] in tier_filter]
        if filtered:
            df = pd.DataFrame(filtered)
            display_cols = ["Player", "Prop", "Line", "Side", "Avg", "EdgePct", "Tier", "SEM", "Injury"]
            st.dataframe(df[display_cols], width="stretch")
            
            with st.expander("📊 Signal Breakdown (Base | Defense | Location | Usage)"):
                signal_df = pd.DataFrame([{
                    "Player": p["Player"],
                    "Base": f"{p.get('SignalBase', 0):.1%}",
                    "Defense": f"{p.get('SignalDefense', 0):.1%}",
                    "Location": f"{p.get('SignalLocation', 0):.1%}",
                    "Usage": f"{p.get('SignalUsage', 0):.1%}",
                    "Net": p["EdgePct"],
                } for p in filtered[:10]])
                st.dataframe(signal_df, width="stretch")
            
            st.markdown("---")
            options = [f"{r['Player']} — {r['Side']} {r['Line']} {r['Prop']} (Edge: {r['EdgePct']} | {r['Tier']} | SEM: {r.get('SEM','—')})" for r in filtered]
            if options:
                sel = st.selectbox("Select prop", range(len(options)), format_func=lambda i: options[i])
                if st.button("🔒 Lock Selected"):
                    row = filtered[sel]
                    st.session_state.locks.append({"player": row["Player"], "prop": row["Prop"], "line": row["Line"], "side": row["Side"],
                                                   "wager": row["Wager"], "prob": row["Prob"], "edge": row["Edge"], "tier": row["Tier"],
                                                   "status": "PENDING", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "sport": row["Sport"]})
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    st.rerun()
        else:
            st.info("No props match selected filter.")
    else:
        st.info("Select a sport and click Load Board.")

# ----- TAB 2: GAME LINES (with odds display) -----
with tabs[2]:
    st.markdown(f"## 🏟️ Game Lines — {st.session_state.last_sport}")
    if st.session_state.games:
        games_df = pd.DataFrame(st.session_state.games)
        display_cols = ["Matchup", "Status", "Spread", "Total", "Home ML", "Away ML", "Odds Source", "Date"]
        display_cols = [c for c in display_cols if c in games_df.columns]
        st.dataframe(games_df[display_cols], width="stretch")
        st.caption("Odds from ESPN API. Lines may not be available for all games.")
    else:
        st.info("No games found. Load the board first, or no games scheduled today.")

# ----- TAB 3: LOCKS & LEDGER -----
with tabs[3]:
    st.markdown("## 🔒 Active Locks")
    if st.session_state.locks:
        for i, lock in enumerate(st.session_state.locks.copy()):
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            col1.write(f"**{lock['player']}** {lock['side']} {lock['line']} {lock['prop']} — {lock.get('tier','—')} | Wager: ${lock['wager']:.2f}")
            if col2.button("✅ WIN", key=f"win_{i}"):
                profit = round(lock["wager"] * (100 / 110), 2)
                st.session_state.bankroll += profit
                st.session_state.history.append({**lock, "outcome": "WIN", "profit": profit, "loss": 0, "net": profit})
                save_json_data(BANKROLL_PATH, st.session_state.bankroll)
                save_json_data(HISTORY_PATH, st.session_state.history)
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                st.rerun()
            if col3.button("❌ LOSS", key=f"loss_{i}"):
                st.session_state.bankroll -= lock["wager"]
                st.session_state.history.append({**lock, "outcome": "LOSS", "profit": 0, "loss": lock["wager"], "net": -lock["wager"]})
                save_json_data(BANKROLL_PATH, st.session_state.bankroll)
                save_json_data(HISTORY_PATH, st.session_state.history)
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                st.rerun()
            if col4.button("↩ VOID", key=f"void_{i}"):
                st.session_state.locks = [l for j, l in enumerate(st.session_state.locks) if j != i]
                save_json_data(LOCKS_PATH, st.session_state.locks)
                st.rerun()
    else:
        st.info("No active locks.")

# ----- TAB 4: HISTORY -----
with tabs[4]:
    st.markdown("## 📈 Full Bet History")
    if st.session_state.history:
        hist_df = pd.DataFrame(st.session_state.history)
        cols = [c for c in ["timestamp", "player", "prop", "line", "side", "tier", "wager", "outcome", "net"] if c in hist_df.columns]
        st.dataframe(hist_df[cols], width="stretch")
        if st.button("Clear History"):
            st.session_state.history = []
            save_json_data(HISTORY_PATH, [])
            st.rerun()
    else:
        st.info("No bet history yet.")

# ----- TAB 5: SYSTEM -----
with tabs[5]:
    st.markdown("## ⚙️ System Info")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Configuration**")
        st.write(f"Bankroll: ${st.session_state.bankroll:.2f}")
        st.write(f"Min Edge: {st.session_state.min_edge*100:.0f}%")
        st.write(f"Skip unknown players: {st.session_state.skip_defaults}")
        st.write(f"Kelly fraction: {KELLY_FRACTION}")
        st.write(f"Standard odds: {ODDS}")
    with c2:
        st.markdown("**Session Stats**")
        st.write(f"Active locks: {len(st.session_state.locks)}")
        st.write(f"History entries: {len(st.session_state.history)}")
        st.write(f"Props loaded: {len(st.session_state.board_data)}")
        st.write(f"Last scan: {st.session_state.last_scan_time or '—'}")
        st.write(f"Session time: {get_session_time()}")
    st.markdown("---")
    st.markdown("### 📊 Multi‑Signal Edge Model")
    st.write("**4 Signals Combined:**")
    st.write("- **Base (55%)**: Line vs player's rolling average")
    st.write("- **Defense (30%)**: Opponent defensive rating (NBA Stats API)")
    st.write("- **Location (15%)**: Home (+5%) vs Away (-5%)")
    st.write("- **Usage (bonus)**: Teammate out → +6‑10%")
    st.markdown("---")
    st.markdown("### 📊 SEM Calibration Summary")
    tier_stats = compute_tier_stats(st.session_state.history)
    if tier_stats:
        sem_df = pd.DataFrame([{"Tier": tier, "Bets": stats["n"], "Hit Rate": f"{stats['hit_rate']:.1%}",
                                "Predicted": f"{stats['avg_predicted']:.1%}", "Calibration Error": f"{stats['calibration_error']:+.1%}",
                                "SEM": f"±{stats['sem']:.3f}" if stats['sem'] else "—"} for tier, stats in tier_stats.items()])
        st.dataframe(sem_df, width="stretch")
        if all(stats["n"] < 20 for stats in tier_stats.values()):
            st.warning("⚠️ Need 20+ bets per tier for reliable SEM.")
    else:
        st.info("No calibration data yet. Resolve locks to build SEM history.")
    st.markdown("---")
    st.markdown("**Data Sources**")
    st.write("- Props: PrizePicks API (primary) / Underdog API (fallback)")
    st.write("- Game matchups + odds: ESPN scoreboard API")
    st.write("- NBA rolling averages: NBA Stats API")
    st.write("- NBA team defensive ratings: NBA Stats API")
    st.write("- NBA season averages: balldontlie API")
    st.write("- MLB/NFL/NHL/WNBA/Soccer/UFC: Hardcoded averages (update weekly)")
    st.markdown("---")
    st.markdown("**🔍 PrizePicks API Debug**")
    debug_sport = st.selectbox("Test sport", SPORTS, key="debug_sport_sel")
    if st.button("Test PrizePicks API", key="debug_pp"):
        league_ids = {"NBA":4,"MLB":5,"NHL":3,"NFL":7,"WNBA":8,"UFC":6,"Golf":11,"Tennis":12,"Soccer":2}
        lid = league_ids.get(debug_sport, 5)
        test_url = f"https://api.prizepicks.com/projections?league_id={lid}&per_page=250"
        try:
            resp = requests.get(test_url, headers=HEADERS, timeout=10)
            st.write(f"**Status code:** {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                st.write(f"**Projections returned:** {len(data.get('data', []))}")
                st.write(f"**Included types:** {list({i.get('type') for i in data.get('included', [])})}")
            else:
                st.error(f"Failed: HTTP {resp.status_code}")
        except Exception as e:
            st.error(f"Request error: {e}")
