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
st.set_page_config(page_title="BetCouncil v4.6 – Final", page_icon="🛡️", layout="wide")

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

# FIX 1: Season sync constants
CURRENT_NBA_SEASON = "2024-25"
CURRENT_BDL_SEASON = 2025

# Odds API counter and protection
ODDS_API_MONTHLY_LIMIT = 450
ODDS_API_COUNTER_PATH = os.path.join(CACHE_DIR, "odds_api_counter.json")

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

# FIX 10: Expanded Teammate out usage spikes
TEAMMATE_OUT_BOOST = {
    "Luka Doncic":   {"out_player": "Kyrie Irving", "PTS": 3.5, "AST": 1.5, "PRA": 5.0},
    "Shai Gilgeous-Alexander": {"out_player": "Jalen Williams", "PTS": 2.8, "AST": 1.2, "PRA": 4.0},
    "Nikola Jokic":  {"out_player": "Jamal Murray", "PTS": 3.2, "AST": 1.8, "PRA": 5.0},
    "LeBron James":  {"out_player": "Anthony Davis", "PTS": 2.5, "AST": 1.0, "PRA": 3.5},
    "Stephen Curry": {"out_player": "Draymond Green", "PTS": 3.0, "AST": 1.2, "PRA": 4.2},
    "Giannis Antetokounmpo": {"out_player": "Khris Middleton", "PTS": 2.8, "REB": 1.0, "PRA": 3.8},
    "Kevin Durant":  {"out_player": "Devin Booker", "PTS": 2.5, "AST": 0.8, "PRA": 3.3},
    "Jayson Tatum":  {"out_player": "Jaylen Brown", "PTS": 2.2, "AST": 0.8, "PRA": 3.0},
    "Damian Lillard": {"out_player": "Giannis Antetokounmpo", "PTS": 3.0, "AST": 1.5, "PRA": 4.5},
    "Tyrese Maxey":  {"out_player": "Joel Embiid", "PTS": 4.0, "AST": 1.5, "PRA": 5.5},
    "Desmond Bane":  {"out_player": "Ja Morant", "PTS": 3.5, "AST": 2.0, "PRA": 5.5},
    "Anthony Edwards": {"out_player": "Karl-Anthony Towns", "PTS": 3.0, "REB": 1.0, "PRA": 4.0},
    "Jalen Brunson": {"out_player": "OG Anunoby", "PTS": 2.0, "AST": 1.0, "PRA": 3.0},
    "De'Aaron Fox":  {"out_player": "Domantas Sabonis", "PTS": 2.5, "AST": 1.5, "PRA": 4.0},
    "Donovan Mitchell": {"out_player": "Darius Garland", "PTS": 3.5, "AST": 2.0, "PRA": 5.5},
    "Cade Cunningham": {"out_player": "Jalen Duren", "PTS": 2.0, "AST": 1.0, "PRA": 3.0},
    "Victor Wembanyama": {"out_player": "Devin Vassell", "PTS": 2.0, "REB": 1.0, "PRA": 3.0},
    "Tyrese Haliburton": {"out_player": "Pascal Siakam", "PTS": 2.5, "AST": 1.5, "PRA": 4.0},
    "Trae Young":    {"out_player": "Dejounte Murray", "PTS": 2.0, "AST": 2.0, "PRA": 4.0},
    "Paolo Banchero": {"out_player": "Franz Wagner", "PTS": 3.0, "AST": 1.0, "PRA": 4.0},
    "Franz Wagner":  {"out_player": "Paolo Banchero", "PTS": 3.0, "AST": 1.0, "PRA": 4.0},
}

# Expanded player-to-team mapping
PLAYER_TEAM_MAP = {
    "LeBron James": "LAL", "Anthony Davis": "LAL", "Austin Reaves": "LAL", "Luka Doncic": "LAL",
    "Kyrie Irving": "DAL", "Tim Hardaway Jr.": "DAL", "Derrick Jones Jr.": "DAL", "Klay Thompson": "DAL",
    "Nikola Jokic": "DEN", "Jamal Murray": "DEN", "Michael Porter Jr.": "DEN", "Aaron Gordon": "DEN",
    "Shai Gilgeous-Alexander": "OKC", "Jalen Williams": "OKC", "Chet Holmgren": "OKC", "Luguentz Dort": "OKC",
    "Giannis Antetokounmpo": "MIL", "Damian Lillard": "MIL", "Khris Middleton": "MIL", "Brook Lopez": "MIL",
    "Jayson Tatum": "BOS", "Jaylen Brown": "BOS", "Kristaps Porzingis": "BOS", "Derrick White": "BOS",
    "Stephen Curry": "GSW", "Draymond Green": "GSW", "Andrew Wiggins": "GSW",
    "Kevin Durant": "PHX", "Devin Booker": "PHX", "Bradley Beal": "PHX", "Jusuf Nurkic": "PHX",
    "Donovan Mitchell": "CLE", "Darius Garland": "CLE", "Evan Mobley": "CLE", "Jarrett Allen": "CLE", "Caris LeVert": "CLE", "Max Strus": "CLE",
    "Jimmy Butler": "MIA", "Bam Adebayo": "MIA", "Tyler Herro": "MIA", "Caleb Martin": "MIA",
    "Trae Young": "ATL", "Dejounte Murray": "ATL", "Clint Capela": "ATL", "Bogdan Bogdanovic": "ATL", "Zaccharie Risacher": "ATL",
    "Ja Morant": "MEM", "Jaren Jackson Jr.": "MEM", "Desmond Bane": "MEM", "Marcus Smart": "MEM", "GG Jackson": "MEM",
    "Zion Williamson": "NOP", "Brandon Ingram": "NOP", "CJ McCollum": "NOP", "Jonas Valanciunas": "NOP",
    "Kawhi Leonard": "LAC", "Paul George": "PHI", "James Harden": "LAC", "Russell Westbrook": "LAC",
    "Joel Embiid": "PHI", "Tyrese Maxey": "PHI", "Tobias Harris": "PHI", "Kelly Oubre Jr.": "PHI",
    "Karl-Anthony Towns": "NYK", "Anthony Edwards": "MIN", "Rudy Gobert": "MIN", "Mike Conley": "MIN", "Julius Randle": "MIN", "Naz Reid": "MIN",
    "Domantas Sabonis": "SAC", "Keegan Murray": "SAC", "Harrison Barnes": "SAC", "De'Aaron Fox": "SAS",
    "Victor Wembanyama": "SAS", "Keldon Johnson": "SAS", "Devin Vassell": "SAS",
    "Cade Cunningham": "DET", "Jalen Duren": "DET", "Ausar Thompson": "DET",
    "Jalen Brunson": "NYK", "OG Anunoby": "NYK", "Mikal Bridges": "NYK", "Josh Hart": "NYK",
    "Paolo Banchero": "ORL", "Franz Wagner": "ORL", "Wendell Carter Jr.": "ORL",
    "Alperen Sengun": "HOU", "Jalen Green": "HOU", "Amen Thompson": "HOU",
    "Tyrese Haliburton": "IND", "Pascal Siakam": "IND", "Myles Turner": "IND",
    "Nikola Vucevic": "CHI", "Coby White": "CHI", "Josh Giddey": "CHI",
    "Scottie Barnes": "TOR", "Immanuel Quickley": "TOR", "RJ Barrett": "TOR",
}

# FIX 6: NBA Team Pace mapping
NBA_TEAM_PACE = {
    "MEM": 102.8, "SAC": 101.5, "BOS": 101.2, "DAL": 100.8,
    "OKC": 100.5, "LAL": 100.2, "DEN": 100.0, "PHX": 99.8,
    "GSW": 99.5, "NOP": 99.2, "ATL": 99.0, "IND": 98.8,
    "MIN": 98.5, "TOR": 98.3, "ORL": 98.0, "HOU": 97.8,
    "SAS": 97.5, "DET": 97.3, "LAC": 97.1, "UTA": 96.9,
    "WAS": 96.7, "CHI": 96.5, "POR": 96.3, "CHA": 96.1,
    "MIL": 98.1, "CLE": 98.1, "NYK": 97.8, "MIA": 97.3,
    "PHI": 97.0, "BKN": 96.8,
}
LEAGUE_AVG_PACE = 99.5
LEAGUE_AVG_TOTAL = 225.0

# MLB Player ID Map
MLB_PLAYER_IDS = {
    "Aaron Judge": 592450, "Shohei Ohtani": 660271,
    "Mookie Betts": 605141, "Freddie Freeman": 518692,
    "Juan Soto": 665742, "Bryce Harper": 547180,
    "Ronald Acuna Jr.": 660670, "Jose Ramirez": 608070,
    "Pete Alonso": 624413, "Vladimir Guerrero Jr.": 665489,
    "Francisco Lindor": 596019, "Bobby Witt Jr.": 677951,
    "Gunnar Henderson": 683002, "Elly De La Cruz": 682829,
    "Corbin Carroll": 682998, "Paul Skenes": 694973,
    "Spencer Strider": 675911, "Gerrit Cole": 543037,
    "Zack Wheeler": 554430, "Tarik Skubal": 669373,
    "Blake Snell": 605483, "Framber Valdez": 664285,
    "Logan Webb": 657277, "Kevin Gausman": 592332,
    "Yoshinobu Yamamoto": 808967, "Luis Castillo": 622491,
    "Dylan Cease": 656302, "Corbin Burnes": 669456,
    "Sandy Alcantara": 645261, "Hunter Brown": 686613,
    "Julio Rodriguez": 677594, "Yordan Alvarez": 670541,
    "Kyle Tucker": 663656, "Trea Turner": 607208,
    "Nolan Arenado": 571448, "Paul Goldschmidt": 502671,
    "Xander Bogaerts": 519048, "Marcus Semien": 543760,
    "Corey Seager": 608369, "Nathaniel Lowe": 663993,
}

# NHL Player ID Map
NHL_PLAYER_IDS = {
    "Connor McDavid": 8478402, "Leon Draisaitl": 8477934,
    "Nathan MacKinnon": 8477492, "David Pastrnak": 8477956,
    "Nikita Kucherov": 8476453, "Auston Matthews": 8479318,
    "Mitch Marner": 8481522, "Cale Makar": 8480069,
    "Kirill Kaprizov": 8481600, "Mikko Rantanen": 8481467,
    "Matthew Tkachuk": 8481559, "Brayden Point": 8478010,
    "Sam Reinhart": 8477998, "Aleksander Barkov": 8477493,
    "Brady Tkachuk": 8481528, "Mark Scheifele": 8476979,
    "Elias Pettersson": 8480012, "Jack Hughes": 8481559,
    "Jason Robertson": 8481671, "Tage Thompson": 8479420,
    "Sebastian Aho": 8478427, "Jake Guentzel": 8477404,
    "Kyle Connor": 8479274, "Filip Forsberg": 8476887,
    "Vincent Trocheck": 8476882, "Andrei Svechnikov": 8481533,
    "J.T. Miller": 8477444, "Steven Stamkos": 8474564,
    "Anze Kopitar": 8471685, "Claude Giroux": 8473512,
}

# FIX 5: Sport-adjusted tier thresholds
TIER_THRESHOLDS = {
    "NBA":    {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "MLB":    {"SOVEREIGN": 0.20, "ELITE": 0.14, "APPROVED": 0.07, "LEAN": 0.03},
    "NHL":    {"SOVEREIGN": 0.18, "ELITE": 0.12, "APPROVED": 0.06, "LEAN": 0.02},
    "NFL":    {"SOVEREIGN": 0.22, "ELITE": 0.15, "APPROVED": 0.08, "LEAN": 0.03},
    "WNBA":   {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "Soccer": {"SOVEREIGN": 0.20, "ELITE": 0.14, "APPROVED": 0.07, "LEAN": 0.03},
    "UFC":    {"SOVEREIGN": 0.20, "ELITE": 0.14, "APPROVED": 0.07, "LEAN": 0.03},
    "Golf":   {"SOVEREIGN": 0.20, "ELITE": 0.14, "APPROVED": 0.07, "LEAN": 0.03},
    "Tennis": {"SOVEREIGN": 0.20, "ELITE": 0.14, "APPROVED": 0.07, "LEAN": 0.03},
}

# =========================
# ODDS API COUNTER FUNCTIONS
# =========================
def get_odds_api_usage():
    data = load_json_data(ODDS_API_COUNTER_PATH, {"count": 0, "month": datetime.now().strftime("%Y-%m")})
    if data.get("month") != datetime.now().strftime("%Y-%m"):
        data = {"count": 0, "month": datetime.now().strftime("%Y-%m")}
        save_json_data(ODDS_API_COUNTER_PATH, data)
    return data

def increment_odds_api_counter():
    data = get_odds_api_usage()
    data["count"] += 1
    save_json_data(ODDS_API_COUNTER_PATH, data)

def can_use_odds_api():
    return get_odds_api_usage()["count"] < ODDS_API_MONTHLY_LIMIT

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
# FIX 2: Updated normalize_name with hyphen handling
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

def kelly_unit(prob, bankroll):
    if prob <= 0.5:
        return 0.0
    b = 100 / abs(ODDS)
    q = 1 - prob
    kelly = (b * prob - q) / b
    if kelly <= 0:
        return 0.0
    return round(min(kelly * KELLY_FRACTION * bankroll, bankroll * KELLY_CAP), 2)

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
    return f"{'+' if change >= 0 else ''}{change:.1f}%"

# =========================
# FIX 4: WEIGHTED AVERAGE with sample size confidence
# =========================
def get_weighted_average(player_name, season_avg, last10_avg, is_playoff=False, n_games=10):
    if last10_avg is None:
        return season_avg
    if is_playoff:
        return last10_avg
    
    # Scale rolling weight by actual sample size
    rolling_weight = min(0.70, max(0.35, (n_games / 10) * 0.70))
    season_weight = 1 - rolling_weight
    
    result = {}
    for stat in ["PTS", "REB", "AST", "PRA"]:
        rolling_val = last10_avg.get(stat, season_avg.get(stat, 0))
        season_val = season_avg.get(stat, 0)
        result[stat] = round(rolling_val * rolling_weight + season_val * season_weight, 1)
    return result

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
        f"https://stats.nba.com/stats/playergamelogs?Season={CURRENT_NBA_SEASON}&SeasonType=Playoffs&PlayerOrTeam=P&LastNGames=10",
        f"https://stats.nba.com/stats/playergamelogs?Season={CURRENT_NBA_SEASON}&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
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
            n_games = len(rows)

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
                        "n_games": n_games,
                    }

            if rolling:
                break

        except Exception as e:
            continue

    if not rolling:
        st.session_state["nba_api_status"] = "FAILED"
    else:
        st.session_state["nba_api_status"] = f"OK ({len(rolling)} players)"

    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)

    return rolling

# =========================
# MLB ROLLING AVERAGES — MLB STATS API
# =========================
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
        url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group={group}&season=2025&gameType=R"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            splits = data.get("stats", [{}])[0].get("splits", [])
            last10 = splits[-10:] if len(splits) >= 10 else splits
            if len(last10) < 3:
                continue

            if is_pitcher:
                avg_so = round(sum(g["stat"].get("strikeOuts", 0) for g in last10) / len(last10), 1)
                avg_er = round(sum(g["stat"].get("earnedRuns", 0) for g in last10) / len(last10), 1)
                avg_h = round(sum(g["stat"].get("hits", 0) for g in last10) / len(last10), 1)
                rolling[player_name] = {"SO": avg_so, "ER": avg_er, "H": avg_h, "n_games": len(last10)}
            else:
                avg_h = round(sum(g["stat"].get("hits", 0) for g in last10) / len(last10), 1)
                avg_hr = round(sum(g["stat"].get("homeRuns", 0) for g in last10) / len(last10), 2)
                avg_rbi = round(sum(g["stat"].get("rbi", 0) for g in last10) / len(last10), 1)
                avg_r = round(sum(g["stat"].get("runs", 0) for g in last10) / len(last10), 1)
                rolling[player_name] = {"H": avg_h, "HR": avg_hr, "RBI": avg_rbi, "R": avg_r, "n_games": len(last10)}
            time.sleep(0.3)
        except Exception as e:
            continue

    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

# =========================
# NHL ROLLING AVERAGES — NHL API
# =========================
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

            avg_pts = round(sum(g.get("points", 0) for g in last10) / len(last10), 1)
            avg_goals = round(sum(g.get("goals", 0) for g in last10) / len(last10), 2)
            avg_assists = round(sum(g.get("assists", 0) for g in last10) / len(last10), 2)
            avg_sog = round(sum(g.get("shots", 0) for g in last10) / len(last10), 1)

            rolling[player_name] = {"PTS": avg_pts, "GOALS": avg_goals, "ASSISTS": avg_assists, "SOG": avg_sog, "n_games": len(last10)}
            time.sleep(0.3)
        except Exception as e:
            continue

    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

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
    url = f"https://api.balldontlie.io/v1/season_averages?season={CURRENT_BDL_SEASON}&{params}"
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
# UNDERDOG PROPS FETCH
# =========================
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
    st.info("PrizePicks unavailable — trying Underdog Fantasy...")
    return fetch_underdog_props(sport)

# =========================
# CROSS-BOOK LINE COMPARISON
# =========================
def compare_book_lines(pp_props, ud_props):
    discrepancies = []
    pp_dict = {}
    for p in pp_props:
        key = (normalize_name(p["Player"]), p["Prop"])
        pp_dict[key] = p["Line"]
    for p in ud_props:
        key = (normalize_name(p["Player"]), p["Prop"])
        if key in pp_dict:
            diff = pp_dict[key] - p["Line"]
            if abs(diff) >= 0.5:
                discrepancies.append({
                    "Player": p["Player"],
                    "Prop": p["Prop"],
                    "PrizePicks": pp_dict[key],
                    "Underdog": p["Line"],
                    "Diff": round(diff, 1),
                    "Favor": "OVER on PP" if diff > 0 else "OVER on UD"
                })
    return sorted(discrepancies, key=lambda x: abs(x["Diff"]), reverse=True)

# =========================
# ESPN INJURY FETCH (with Underdog merge)
# =========================
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
            if "out" in content and "ruled out" in content:
                injuries[name] = "Out"
            elif "questionable" in content or "day-to-day" in content:
                injuries[name] = "Questionable"
        return injuries
    except:
        return {}

def fetch_injury_news(sport):
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NFL": "football/nfl", "NHL": "hockey/nhl"}
    path = slug_map.get(sport, "")
    injuries = {}
    if path:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/news"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
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
            pass
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
                    comp_data = event.get("competitions", [{}])[0]
                    odds_data = comp_data.get("odds", [{}])[0] if comp_data.get("odds") else {}
                    spread = odds_data.get("details", "—")
                    total = odds_data.get("overUnder", "—")
                    home_ml = odds_data.get("homeTeamOdds", {}).get("moneyLine", "—")
                    away_ml = odds_data.get("awayTeamOdds", {}).get("moneyLine", "—")
                    provider = odds_data.get("provider", {}).get("name", "")
                    
                    for comp in event.get("competitions", []):
                        for competitor in comp.get("competitors", []):
                            team = competitor.get("team", {}).get("abbreviation", "")
                            home_away = competitor.get("homeAway", "")
                            if home_away == "home":
                                home_teams[matchup] = team
                            else:
                                away_teams[matchup] = team
                    
                    games.append({"Matchup": matchup, "Status": status, "Spread": spread, "Total": total,
                                  "Home ML": home_ml, "Away ML": away_ml, "Odds Source": provider,
                                  "Date": target_date.strftime("%a %b %d"), "Sport": sport})
                return games, playoff, home_teams, away_teams
        except:
            pass
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
        url = f"https://stats.nba.com/stats/leaguedashteamstats?Season={CURRENT_NBA_SEASON}&SeasonType={season_type}&MeasureType=Defense&PerMode=PerGame"
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
                    except:
                        continue
            if team_def:
                break
        except:
            continue

    if team_def:
        with open(cache_path, "wb") as f:
            pickle.dump(team_def, f)
    return team_def

# =========================
# DATA FRESHNESS CHECK
# =========================
def check_data_freshness():
    warnings = []
    checks = {
        "NBA Rolling Averages": "nba_rolling_avgs.pkl",
        "NBA Team Defense": "nba_team_defense.pkl",
        "MLB Rolling Averages": "mlb_rolling_avgs.pkl",
        "NHL Rolling Averages": "nhl_rolling_avgs.pkl",
        "BDL Season Averages": "bdl_nba_avgs.pkl",
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
            warnings.append(f"Hardcoded averages (NFL/WNBA/Soccer/UFC): {days_old} days old — update PLAYER_AVERAGES")
    except:
        pass
    return warnings

# =========================
# MULTI-SIGNAL EDGE CALCULATION
# =========================
def compute_multi_signal_edge(line, player_avg, opp_def_rating, is_home, usage_boost, side="OVER",
                               stat_key="PTS", pace_adj=0.0, game_total_adj=0.0, days_rest=2):
    if player_avg <= 0:
        return 0.0, 0.5, {}
    
    signals = {}
    league_avg_def = 112.0
    
    # Signal 1: Base (line vs player average) — weight 45%
    if stat_key in ["HR", "GOALS"]:
        prob = poisson_prob_over(line, player_avg)
        if side.upper() == "UNDER":
            prob = 1 - prob
        base_edge = prob - 0.5
    else:
        diff = (line - player_avg) / player_avg
        if side.upper() == "OVER":
            base_edge = -diff
        else:
            base_edge = diff
        if player_avg > 0:
            pct_diff = abs(line - player_avg) / player_avg
            if pct_diff > 0.15:
                base_edge = base_edge * 0.70
    signals["base"] = base_edge
    
    # Signal 2: Opponent defense adjustment (30%)
    if opp_def_rating > 0:
        def_adj = (opp_def_rating - league_avg_def) / league_avg_def
        signals["defense"] = (-def_adj * 0.30) if side.upper() == "OVER" else (def_adj * 0.30)
    else:
        signals["defense"] = 0
    
    # Signal 3: Home/away adjustment (15%)
    location_adj = 0.05 if is_home else -0.05
    if side.upper() == "UNDER":
        location_adj = -location_adj
    signals["location"] = location_adj
    
    # Signal 4: Rest days penalty (5%)
    rest_adj = -0.08 if days_rest == 0 else 0.0
    signals["rest"] = rest_adj
    
    # Signal 5: Pace adjustment (5%)
    signals["pace"] = pace_adj if side.upper() == "OVER" else -pace_adj
    
    # Weighted combination
    combined = (signals["base"] * 0.45 + signals["defense"] * 0.30 +
                signals["location"] * 0.15 + signals["rest"] * 0.05 + signals["pace"] * 0.05)
    
    if usage_boost:
        combined += usage_boost * 0.10
    if game_total_adj:
        combined += game_total_adj * 0.05
    
    combined = max(-EDGE_CAP, min(EDGE_CAP, combined))
    prob = max(0.30, min(0.70, 0.5 + combined))
    return combined, prob, signals

# =========================
# HARDCODED FALLBACK AVERAGES
# =========================
PLAYER_AVERAGES = {
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
}

STAT_NORMALIZE = {
    ("NBA", "Points"): "PTS", ("NBA", "Rebounds"): "REB", ("NBA", "Assists"): "AST",
    ("NBA", "Pts+Reb+Ast"): "PRA", ("NBA", "Pts+Reb"): "PRA", ("NBA", "Pts+Ast"): "PRA",
    ("NBA", "Reb+Ast"): "PRA", ("MLB", "Home Runs"): "HR", ("MLB", "Hits"): "H",
    ("MLB", "RBIs"): "RBI", ("MLB", "Runs"): "R", ("MLB", "Strikeouts"): "SO",
    ("MLB", "Earned Runs"): "ER", ("NFL", "Passing Yards"): "PASS_YDS",
    ("NFL", "Rushing Yards"): "RUSH_YDS", ("NFL", "Receiving Yards"): "REC_YDS",
    ("NFL", "Touchdowns"): "TD", ("NHL", "Points"): "PTS", ("NHL", "Goals"): "GOALS",
    ("NHL", "Assists"): "ASSISTS", ("NHL", "Shots On Goal"): "SOG",
    ("WNBA", "Points"): "PTS", ("WNBA", "Rebounds"): "REB", ("WNBA", "Assists"): "AST",
    ("WNBA", "Pts+Reb+Ast"): "PRA", ("Soccer", "Goals"): "GOALS", ("Soccer", "Assists"): "ASSISTS",
    ("Soccer", "Shots"): "SHOTS", ("UFC", "Significant Strikes"): "SIG_STR",
    ("UFC", "Takedowns"): "TAKEDOWNS", ("UFC", "Control Time"): "CONTROL_TIME",
    ("UFC", "Knockdowns"): "KNOCKDOWNS",
    ("NBA", "pts"): "PTS", ("NBA", "reb"): "REB", ("NBA", "ast"): "AST",
    ("NBA", "points"): "PTS", ("NBA", "rebounds"): "REB", ("NBA", "assists"): "AST",
    ("NBA", "3-PT Made"): "PTS", ("NBA", "Pts+Rebs+Asts"): "PRA",
    ("NBA", "Pts+Rebs"): "PRA", ("NBA", "Pts+Asts"): "PRA",
    ("MLB", "Strikeouts"): "SO", ("MLB", "Hits Allowed"): "H", ("MLB", "Total Bases"): "H",
    ("NHL", "Goals"): "GOALS", ("NHL", "Assists"): "ASSISTS", ("NHL", "Points"): "PTS",
    ("NHL", "Shots on Goal"): "SOG",
}

POISSON_STATS = {"HR", "GOALS"}

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
                             "SignalBase": 0, "SignalDefense": 0, "SignalLocation": 0, "SignalUsage": 0,
                             "SignalPace": 0})
        return enriched, [], 0, 0

    rolling_avgs = {}
    team_defense = {}
    if sport == "NBA":
        rolling_avgs = fetch_nba_rolling_averages()
        team_defense = fetch_nba_team_defense()
        live_avgs = fetch_nba_averages_bdl()
        season_avgs = {**PLAYER_AVERAGES.get("NBA", {}), **live_avgs}
    elif sport == "MLB":
        mlb_rolling = fetch_mlb_rolling_averages()
        season_avgs = PLAYER_AVERAGES.get("MLB", {})
        for player, stats in mlb_rolling.items():
            if player in season_avgs:
                merged = {}
                for stat, val in stats.items():
                    season_val = season_avgs[player].get(stat, val)
                    merged[stat] = round(val * 0.7 + season_val * 0.3, 2)
                season_avgs[player] = {**season_avgs[player], **merged}
    elif sport == "NHL":
        nhl_rolling = fetch_nhl_rolling_averages()
        season_avgs = PLAYER_AVERAGES.get("NHL", {})
        for player, stats in nhl_rolling.items():
            if player in season_avgs:
                merged = {}
                for stat, val in stats.items():
                    season_val = season_avgs[player].get(stat, val)
                    merged[stat] = round(val * 0.7 + season_val * 0.3, 2)
                season_avgs[player] = {**season_avgs[player], **merged}
    else:
        season_avgs = PLAYER_AVERAGES.get(sport, {})

    defaults = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])
    pp_props = scrape_prizepicks(sport)
    ud_props_compare = fetch_underdog_props(sport)
    line_discrepancies = compare_book_lines(pp_props if pp_props else [], ud_props_compare if ud_props_compare else [])
    st.session_state["line_discrepancies"] = line_discrepancies
    
    props = pp_props if pp_props else ud_props_compare
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

        if sport == "NBA" and player in season_avgs:
            season_avg = season_avgs.get(player, {})
            last10 = rolling_avgs.get(player, None)
            n_games = last10.get("n_games", 10) if last10 else 10
            avg_dict = get_weighted_average(player, season_avg, last10, is_playoff, n_games)
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

        avg = avg_dict.get(stat_norm, defaults.get(stat_norm, line))

        # Defensive rating
        player_team = PLAYER_TEAM_MAP.get(player, "")
        opp_def_rating = 112.0
        if player_team and games:
            for game in games:
                if player_team in game["Matchup"]:
                    parts = game["Matchup"].replace("@", "vs").split()
                    for p2 in parts:
                        if p2 != player_team and len(p2) <= 3 and p2.isalpha():
                            opp_def_rating = team_defense.get(p2, 112.0)
                            break
                    break

        # Home/away
        is_home = False
        if player_team and games:
            for matchup, home in home_teams.items():
                if player_team == home:
                    is_home = True
                    break

        # Usage boost
        usage_boost = 0.0
        if player in TEAMMATE_OUT_BOOST:
            out_player = TEAMMATE_OUT_BOOST[player].get("out_player")
            if out_player and any(out_player.lower() in inj.lower() for inj in injuries.keys()):
                usage_boost = TEAMMATE_OUT_BOOST[player].get(stat_norm, 0) / 100
                if usage_boost > 0.10:
                    usage_boost = 0.10

        # Pace adjustment (NBA only)
        pace_adj = 0.0
        if sport == "NBA" and player_team:
            for game in games:
                if player_team in game["Matchup"]:
                    parts = game["Matchup"].replace("@", "vs").split()
                    for p2 in parts:
                        if p2 != player_team and len(p2) <= 3 and p2.isalpha():
                            player_pace = NBA_TEAM_PACE.get(player_team, LEAGUE_AVG_PACE)
                            opp_pace = NBA_TEAM_PACE.get(p2, LEAGUE_AVG_PACE)
                            combined_pace = (player_pace + opp_pace) / 2
                            pace_adj = (combined_pace - LEAGUE_AVG_PACE) / LEAGUE_AVG_PACE
                            break
                    break

        # Game total adjustment
        game_total_adj = 0.0
        if sport == "NBA" and player_team:
            for game in games:
                if player_team in game.get("Matchup", ""):
                    total = game.get("Total", "—")
                    if total and total != "—":
                        try:
                            game_total_adj = (float(total) - LEAGUE_AVG_TOTAL) / LEAGUE_AVG_TOTAL * 0.10
                        except:
                            pass
                    break

        # Rest days (simplified)
        days_rest = 2

        # Evaluate OVER and UNDER
        over_edge, over_prob, over_signals = compute_multi_signal_edge(
            line, avg, opp_def_rating, is_home, usage_boost, "OVER", stat_norm, pace_adj, game_total_adj, days_rest
        )
        under_edge, under_prob, under_signals = compute_multi_signal_edge(
            line, avg, opp_def_rating, is_home, usage_boost, "UNDER", stat_norm, pace_adj, game_total_adj, days_rest
        )
        
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

        # Apply SEM calibration
        adj_edge, calibrated = adjusted_edge(best_edge, sport, get_tier(best_edge, sport), stat_norm, history)
        final_edge = adj_edge if calibrated else best_edge

        if final_edge < min_edge:
            skipped_edge += 1
            continue

        tier = get_tier(final_edge, sport)
        injury_flag = injuries.get(player, "")
        sem_display, sem_n = compute_sem_for_tier(tier_stats, tier)

        enriched.append({"Player": player, "Prop": stat_raw, "Line": line, "Side": best_side, "Avg": avg,
                         "Edge": final_edge, "EdgePct": f"{final_edge:.1%}", "Prob": best_prob,
                         "Wager": kelly_unit(best_prob, st.session_state.bankroll), "Tier": tier,
                         "Quality": "Lookup" if not using_default else "Default",
                         "Model": "Poisson" if stat_norm in ["HR", "GOALS"] else "Linear",
                         "Sport": sport, "Injury": injury_flag, "SEM": sem_display, "SEM_n": sem_n,
                         "SignalBase": best_signals.get("base", 0), "SignalDefense": best_signals.get("defense", 0),
                         "SignalLocation": best_signals.get("location", 0), "SignalUsage": best_signals.get("usage", 0),
                         "SignalPace": best_signals.get("pace", 0)})

    enriched.sort(key=lambda x: x["Edge"], reverse=True)
    return enriched, games, skipped_def, skipped_edge

# =========================
# SESSION STATE & PERSISTENCE
# =========================
_ss = {"bankroll": DEFAULT_BANKROLL, "day_start_br": DEFAULT_BANKROLL, "session_start": time.time(),
       "locks": [], "history": [], "min_edge": MIN_EDGE_DEFAULT, "skip_defaults": True, "last_sport": "NBA",
       "board_data": [], "games": [], "last_scan_time": None, "board_ready": False, "n_skipped_def": 0, "n_skipped_edge": 0,
       "nba_api_status": "Not yet fetched", "line_discrepancies": []}
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
    st.markdown('<div style="text-align:center;margin-bottom:16px;"><div style="width:44px;height:44px;background:linear-gradient(135deg,#0ea5a0,#065f5e);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:inline-flex;align-items:center;justify-content:center;font-size:22px;">⚡</div><div style="font-size:22px;font-weight:700;color:#ffffff;margin-top:6px;">BetCouncil</div><div style="font-size:11px;color:#4a8a8a;">v4.6 · Final</div></div>', unsafe_allow_html=True)
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
    <div style="font-size:13px;color:#0ea5a0;font-weight:600;">⚡ BetCouncil v4.6 — Final</div>
    <div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
      <span style="font-size:12px;color:#6a7a8a;">Session: {get_session_time()}</span>
      <span style="font-size:12px;border:1px solid #0ea5a0;color:#0ea5a0;background:rgba(14,165,160,0.1);padding:4px 10px;border-radius:20px;">{pending} Lock{"s" if pending!=1 else ""}</span>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;">
    <div class="metric-box"><div class="metric-label">Bankroll</div><div class="metric-value gold-text">${st.session_state.bankroll:.2f}</div><div style="font-size:12px;color:{dc_color};">{dc} today</div></div>
    <div class="metric-box"><div class="metric-label">Unit</div><div class="metric-value teal-text">${active_unit():.2f}</div></div>
    <div class="metric-box"><div class="metric-label">Min Edge</div><div class="metric-value gold-text">{st.session_state.min_edge*100:.0f}%</div></div>
    <div class
