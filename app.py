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
CLV_PATH = os.path.join(CACHE_DIR, "clv_tracking.json")
LINE_MOVEMENT_PATH = os.path.join(CACHE_DIR, "line_movement.json")
SHARP_PATH = os.path.join(CACHE_DIR, "sharp_flags.json")

# API counter paths
API_SPORTS_COUNTER_PATH = os.path.join(CACHE_DIR, "api_sports_counter.json")
SPORTMONKS_COUNTER_PATH = os.path.join(CACHE_DIR, "sportmonks_counter.json")
UNIFIED_COUNTER_PATH = os.path.join(CACHE_DIR, "unified_counter.json")

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

# Blowout thresholds
BLOWOUT_THRESHOLDS = {
    "NBA": 12, "NFL": 14, "MLB": 3, 
    "NHL": 2, "WNBA": 10
}

# Negative correlations (opposing teams)
NEGATIVE_CORRELATIONS = {
    ("Nikola Jokic", "Joel Embiid"): -0.3,
    ("Luka Doncic", "Shai Gilgeous-Alexander"): -0.2,
    ("Jayson Tatum", "Giannis Antetokounmpo"): -0.2,
}

# Positive correlations (same team)
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

# Wind impact on HR props (mph)
WIND_HR_THRESHOLDS = {
    "strong_out": 15,
    "strong_in": 15,
}

# MLB Ballpark Locations Map
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

# MLB Player Team Map
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

# WNBA Player IDs
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

# API Keys
BDL_API_KEY = "9d7c9ea5-54ea-4084-b0d0-2541ac7c360d"
ODDS_API_IO_KEY = "6c4421ef9db7d9d28d7cb81bd30076b4"
OCR_SPACE_API_KEY = "K89641020988957"
UNIFIED_API_KEY = "96241c1a5ba686f34a9e4c3463b61661"
API_SPORTS_KEY = "8c20c34c3b0a6314e04c4997bf0922d2"
ODDS_API_KEY = "6c4421ef9db7d9d28d7cb81bd30076b4"
RAPIDAPI_KEY = "01a7d8b9femshe49a2a69573b73ap105654jsn60f30519d1f5"
SPORTMONKS_API_KEY = "mUrD13i5iE2C65K5iAJVQNDdbKqSYFDXvBx0AjW3cqixBkXdj0lkLdqb038t"

# Try importing oddswrap
try:
    from oddswrap import OddsClient, Sport
    ODDSWRAP_AVAILABLE = True
except ImportError:
    ODDSWRAP_AVAILABLE = False

ODDSWRAP_SPORT_MAP = {
    "NBA": "nba", "MLB": "mlb",
    "NFL": "nfl", "NHL": "nhl"
}

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_SPORTS_MAP = {
    "NBA": "basketball_nba",
    "MLB": "baseball_mlb",
    "NFL": "americanfootball_nfl",
    "NHL": "icehockey_nhl",
    "WNBA": "basketball_wnba",
}

# =========================
# ESPN CORE API CONSTANTS
# =========================
ESPN_CORE_BASE = "https://sports.core.api.espn.com/v2"
ESPN_CORE_SPORT_MAP = {
    "NBA": "basketball/leagues/nba",
    "MLB": "baseball/leagues/mlb",
    "NHL": "hockey/leagues/nhl",
    "NFL": "football/leagues/nfl",
    "WNBA": "basketball/leagues/wnba",
    "Soccer": "soccer/leagues/eng.1",
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
# API COUNTER MANAGEMENT
# =========================
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
# BLOWOUT RISK ADJUSTMENT
# =========================
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

# =========================
# CLV TRACKING
# =========================
def record_clv(lock, current_props):
    player = lock.get("player", "")
    prop = lock.get("prop", "")
    locked_line = lock.get("line", 0)
    side = lock.get("side", "OVER")
    current_line = None
    for p in current_props:
        if (normalize_name(p.get("Player","")) == normalize_name(player) and
            p.get("Prop","") == prop):
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

# =========================
# MARKET EFFICIENCY SCORE
# =========================
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

# =========================
# CORRELATION DETECTION
# =========================
def detect_correlations(parlay_props):
    notes = []
    adjustment = 1.0
    players = [p["Player"] for p in parlay_props]
    teams = [PLAYER_TEAM_MAP.get(p["Player"], "") for p in parlay_props]
    for i in range(len(players)):
        for j in range(i+1, len(players)):
            if teams[i] and teams[i] == teams[j]:
                pair = (players[i], players[j])
                pair_rev = (players[j], players[i])
                corr = (POSITIVE_CORRELATIONS.get(pair) or POSITIVE_CORRELATIONS.get(pair_rev) or 0.15)
                adjustment *= (1 - corr * 0.3)
                notes.append(f"⚠️ {players[i]} & {players[j]} teammates (+{corr:.0%} correlation — parlay edge reduced)")
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

# =========================
# LINE MOVEMENT TRACKING
# =========================
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
    return movement

# =========================
# WEATHER FUNCTIONS
# =========================
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
        weather = {
            "city": city,
            "wind_speed_mph": int(current.get("windspeedMiles", 0)),
            "wind_dir": current.get("winddir16Point", "N"),
            "temp_f": int(current.get("temp_F", 70)),
            "humidity": int(current.get("humidity", 50)),
            "fetched_at": datetime.now().strftime("%H:%M"),
        }
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
# NBA ROLLING AVERAGES
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
# WNBA ROLLING AVERAGES
# =========================
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
# BALLDONTLIE API
# =========================
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
        print(f"Underdog props error: {e}")
        return []

# =========================
# PRIZEPICKS SCRAPER (with Partner API primary)
# =========================
def scrape_prizepicks(sport):
    league_ids = {"NBA": 4, "MLB": 5, "NHL": 3, "NFL": 7, "WNBA": 8, "UFC": 6, "Golf": 11, "Tennis": 12, "Soccer": 2}
    league = league_ids.get(sport.upper())
    if not league:
        return []
    urls = [
        # Partner API — 1000 per page, more stable
        f"https://partner-api.prizepicks.com/projections?per_page=1000&league_id={league}",
        # Fallbacks
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
# UNDERDOG INJURIES FETCH
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
    except Exception as e:
        print(f"Underdog injuries error: {e}")
        return {}

# =========================
# ESPN INJURY FETCH
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
    underdog_injuries = fetch_underdog_injuries(sport)
    injuries.update(underdog_injuries)
    return injuries

# =========================
# ESPN GAME LINES
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
                        "Matchup": matchup, "Status": status,
                        "Spread": spread, "Total": total,
                        "Home ML": home_ml, "Away ML": away_ml,
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
# ODDSWRAP FUNCTIONS
# =========================
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
                            all_props.append({
                                "Player": prop.player, "Prop": prop.market,
                                "Line": float(prop.line), "Side": "OVER",
                                "OverOdds": prop.over_odds, "UnderOdds": prop.under_odds,
                                "Book": prop.book, "Sport": sport, "source": f"oddswrap_{prop.book}"
                            })
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

# =========================
# MULTI-BOOK LINE COMPARISON
# =========================
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
                            discrepancies.append({
                                "Player": norm_player.title(), "Prop": prop,
                                "PrizePicks": pp_line, "Book": ow_data["book"].title(),
                                "BookLine": ow_data["line"], "Diff": round(diff, 1),
                                "Favor": ("OVER on PP" if diff > 0 else f"OVER on {ow_data['book'].title()}")
                            })
    return sorted(discrepancies, key=lambda x: abs(x["Diff"]), reverse=True)

# =========================
# DATA FRESHNESS CHECK
# =========================
def check_data_freshness():
    warnings = []
    checks = {
        "NBA Rolling Averages": "nba_rolling_avgs.pkl",
        "NBA Team Defense": "nba_team_defense.pkl",
        "WNBA Rolling Averages": "wnba_rolling_avgs.pkl",
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
            warnings.append(f"Hardcoded averages (NFL/Soccer/UFC): {days_old} days old")
    except:
        pass
    return warnings

# =========================
# ESPN CORE API FUNCTIONS
# =========================
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
            movements.append({
                "spread": item.get("spread"),
                "over_under": item.get("overUnder"),
                "home_ml": item.get("homeTeamOdds", {}).get("moneyLine"),
                "away_ml": item.get("awayTeamOdds", {}).get("moneyLine"),
                "time": item.get("recordedAt", ""),
            })
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
        predictor = {
            "home_win_pct": home.get("statistics", [{}])[0].get("value") if home.get("statistics") else None,
            "away_win_pct": away.get("statistics", [{}])[0].get("value") if away.get("statistics") else None,
            "home_projected_score": home.get("statistics", [{}, {}])[1].get("value") if home.get("statistics") and len(home.get("statistics", [])) > 1 else None,
            "away_projected_score": away.get("statistics", [{}, {}])[1].get("value") if away.get("statistics") and len(away.get("statistics", [])) > 1 else None,
        }
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
            avg = {
                "PTS": round(sum(g.get("PTS", 0) for g in game_stats) / len(game_stats), 1),
                "REB": round(sum(g.get("REB", 0) for g in game_stats) / len(game_stats), 1),
                "AST": round(sum(g.get("AST", 0) for g in game_stats) / len(game_stats), 1),
            }
            avg["PRA"] = round(avg["PTS"] + avg["REB"] + avg["AST"], 1)
        elif sport == "NFL":
            avg = {
                "PASS_YDS": round(sum(g.get("PASSYDS", g.get("YDS", 0)) for g in game_stats) / len(game_stats), 1),
                "RUSH_YDS": round(sum(g.get("RUSHYDS", g.get("RYDS", 0)) for g in game_stats) / len(game_stats), 1),
                "REC_YDS": round(sum(g.get("RECYDS", g.get("RECYD", 0)) for g in game_stats) / len(game_stats), 1),
                "TD": round(sum(g.get("TD", 0) for g in game_stats) / len(game_stats), 2),
            }
        else:
            avg = {}
        avg["n_games"] = len(game_stats)
        with open(cache_path, "wb") as f:
            pickle.dump(avg, f)
        return avg
    except:
        return None

# =========================
# MULTI-SIGNAL EDGE CALCULATION
# =========================
def compute_multi_signal_edge(line, player_avg, opp_def_rating, is_home, teammate_out_boost, side="OVER", stat_key="PTS"):
    if player_avg <= 0:
        return 0.0, 0.5, {}
    signals = {}
    league_avg_def = 112.0
    if stat_key in ["HR", "GOALS", "TD", "SO"]:
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
    signals["base"] = base_edge
    if opp_def_rating > 0:
        def_adj = (opp_def_rating - league_avg_def) / league_avg_def
        if side.upper() == "OVER":
            signals["defense"] = -def_adj * 0.30
        else:
            signals["defense"] = def_adj * 0.30
    else:
        signals["defense"] = 0
    if side.upper() == "OVER":
        location_adj = 0.05 if is_home else -0.05
    else:
        location_adj = -0.05 if is_home else 0.05
    signals["location"] = location_adj
    usage_adj = teammate_out_boost if teammate_out_boost else 0.0
    signals["usage"] = usage_adj
    weights = {"base": 0.55, "defense": 0.30, "location": 0.15, "usage": 0.0}
    combined = (signals["base"] * weights["base"] + signals["defense"] * weights["defense"] + signals["location"] * weights["location"])
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
                             "SignalBase": 0, "SignalDefense": 0, "SignalLocation": 0, "SignalUsage": 0,
                             "SignalBlowout": 0, "WeatherNote": "", "Movement": "", "Efficiency": "—", "EffScore": 0,
                             "SharpFlag": ""})
        return enriched, [], 0, 0

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
        games, _, _, _ = fetch_game_lines(sport)
        return [], games, 0, 0

    injuries = fetch_injury_news(sport) if sport in ["NBA", "MLB", "NFL", "NHL"] else {}
    games, is_playoff, home_teams, away_teams = fetch_game_lines(sport)

    # Back-to-back detection
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

    # ESPN game IDs for line movement
    game_ids = fetch_espn_game_ids(sport)
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

        # Opponent defense
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

        # Sharp movement flag
        sharp_flag = ""
        if player_team and games:
            for game in games:
                matchup = game.get("Matchup", "")
                if player_team in matchup:
                    sharp_info = game_sharp_flags.get(matchup, {})
                    if sharp_info.get("sharp"):
                        sharp_flag = f"⚡ Sharp {sharp_info['direction']}{sharp_info['magnitude']}"
                    break

        # Back-to-back
        days_rest = 0 if player_team in b2b_teams else 2

        # Blowout risk
        blowout_adj = 0.0
        if player_team and games:
            for game in games:
                matchup = game.get("Matchup", "")
                if player_team in matchup:
                    spread = game.get("Spread", "—")
                    blowout_adj = blowout_risk_adjustment(spread, sport, player_team, home_teams, away_teams, matchup)
                    break

        # MLB Weather
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

        # Market efficiency
        ud_line_val = None
        for ud_p in (ud_props_compare or []):
            if (normalize_name(ud_p.get("Player","")) == normalize_name(player) and
                ud_p.get("Prop","") == stat_raw):
                ud_line_val = ud_p.get("Line")
                break
        eff_score, eff_label = market_efficiency_score(line, ud_line_val, 0, sport)

        # Evaluate OVER/UNDER
        best_edge = -1
        best_side = side
        best_prob = 0.5
        best_signals = {}
        
        for test_side in ["OVER", "UNDER"]:
            combined_edge, prob, signals = compute_multi_signal_edge(
                line, avg, opp_def_rating, is_home, usage_boost, test_side, stat_norm
            )
            combined_edge = max(-EDGE_CAP, min(EDGE_CAP, combined_edge + blowout_adj + weather_adj))
            if combined_edge > best_edge:
                best_edge = combined_edge
                best_side = test_side
                best_prob = prob
                best_signals = signals

        adj_edge, calibrated = adjusted_edge(best_edge, sport, get_tier(best_edge), stat_norm, history)
        final_edge = adj_edge if calibrated else best_edge

        if final_edge < min_edge:
            skipped_edge += 1
            continue

        tier = get_tier(final_edge)
        injury_flag = injuries.get(player, "")
        sem_display, sem_n = compute_sem_for_tier(tier_stats, tier)

        enriched.append({
            "Player": player, "Prop": stat_raw, "Line": line, "Side": best_side, "Avg": avg,
            "Edge": final_edge, "EdgePct": f"{final_edge:.1%}", "Prob": best_prob,
            "Wager": kelly_unit(best_prob, st.session_state.bankroll), "Tier": tier,
            "Quality": "Lookup" if not using_default else "Default",
            "Model": "MultiSignal", "Sport": sport, "Injury": injury_flag,
            "SEM": sem_display, "SEM_n": sem_n,
            "SignalBase": best_signals.get("base", 0),
            "SignalDefense": best_signals.get("defense", 0),
            "SignalLocation": best_signals.get("location", 0),
            "SignalUsage": best_signals.get("usage", 0),
            "SignalBlowout": blowout_adj, "WeatherNote": weather_note,
            "Movement": "", "Efficiency": eff_label, "EffScore": eff_score,
            "SharpFlag": sharp_flag
        })

    enriched.sort(key=lambda x: x["Edge"], reverse=True)
    
    line_movement = track_line_movement(enriched)
    st.session_state["line_movement"] = line_movement
    for prop in enriched:
        key = f"{prop['Player']}_{prop['Prop']}"
        move = line_movement.get(key, {})
        prop["Movement"] = (move.get("direction", "") + str(abs(move.get("diff", 0))) if move else "")
    
    return enriched, games, skipped_def, skipped_edge

# =========================
# HARDCODED FALLBACK AVERAGES
# =========================
PLAYER_AVERAGES = {}
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
# TABS
# =========================
tabs = st.tabs(["📋 Summary", "📊 Full Board", "🏟️ Game Lines", "🔒 Locks & Ledger", "📈 History", "⚙️ System"])

# ----- TAB 0: SUMMARY -----
with tabs[0]:
    st.markdown("# 🧠 THE BOARD — BETCOUNCIL v4.6")
    today_str = date.today().strftime("%A, %B %d, %Y")
    st.markdown(f"**{st.session_state.last_sport} Slate — {today_str}** | **Scanned:** {scan_t} | **Edge Model:** Multi‑Signal (4 signals)")
    st.markdown("🔒 **Sources:** PrizePicks (primary) · Partner API · Underdog (fallback) · ESPN Odds")
    st.markdown("---")
    st.markdown("## 🏟️ TODAY'S GAMES")
    if st.session_state.games:
        df_games = pd.DataFrame(st.session_state.games)
        display_cols = ["Matchup", "Status", "Spread", "Total", "Home ML", "Away ML", "Date"]
        display_cols = [c for c in display_cols if c in df_games.columns]
        st.table(df_games[display_cols])
    else:
        st.info("No games loaded. Click 'Load Board' in the sidebar.")
    
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
                        weather_data.append({
                            "City": city, "Temp": f"{weather['temp_f']}°F",
                            "Wind": f"{weather['wind_speed_mph']}mph {weather['wind_dir']}",
                            "Humidity": f"{weather['humidity']}%", "Updated": weather["fetched_at"],
                        })
        if weather_data:
            st.dataframe(pd.DataFrame(weather_data), width="stretch")
            st.caption("Weather affects HR and hits props at outdoor stadiums. Wind >15mph is significant.")
        else:
            st.caption("Load MLB board to see weather conditions.")
    
    st.markdown("### ⚡ Sharp Money Alerts")
    sharp_flags = st.session_state.get("game_sharp_flags", {})
    if sharp_flags:
        for matchup, info in sharp_flags.items():
            st.warning(f"**{matchup}**: Line moved {info['direction']}{info['magnitude']} — possible sharp action")
    else:
        st.caption("No significant line movement detected for today's games.")
    
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
            display_cols = ["Player", "Prop", "Line", "Side", "Avg", "EdgePct", "Tier", "SharpFlag", "Efficiency", "SEM", "Injury", "Movement"]
            display_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[display_cols], width="stretch")
            
            with st.expander("📊 Signal Breakdown"):
                signal_cols = ["Player", "SignalBase", "SignalDefense", "SignalLocation", "SignalUsage", "SignalBlowout", "WeatherNote", "EdgePct"]
                signal_cols = [c for c in signal_cols if c in df.columns]
                if signal_cols:
                    signal_df = df[signal_cols].copy()
                    for col in ["SignalBase", "SignalDefense", "SignalLocation", "SignalUsage", "SignalBlowout"]:
                        if col in signal_df.columns:
                            signal_df[col] = signal_df[col].apply(lambda x: f"{x:.1%}" if isinstance(x, (int, float)) else x)
                    st.dataframe(signal_df.head(10), width="stretch")
            
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
                        first = movements[-1]
                        last = movements[0]
                        st.write(f"**Opening:** Spread {first.get('spread','—')} | Total {first.get('over_under','—')}")
                        st.write(f"**Current:** Spread {last.get('spread','—')} | Total {last.get('over_under','—')}")
                        move_df = pd.DataFrame(movements[:10])
                        if not move_df.empty:
                            cols = [c for c in ["time", "spread", "over_under", "home_ml", "away_ml"] if c in move_df.columns]
                            st.dataframe(move_df[cols], width="stretch")
                    else:
                        st.caption("Not enough movement data yet")
        else:
            st.caption("Load board to see line movement.")
    else:
        st.info("No games found.")

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
    st.write("- **Base (55%)**: Line vs player's rolling average")
    st.write("- **Defense (30%)**: Opponent defensive rating")
    st.write("- **Location (15%)**: Home/away adjustment")
    st.write("- **Usage (bonus)**: Teammate out spike")
    st.write("- **Blowout**: Spread > threshold penalty")
    st.write("- **Weather (MLB)**: Wind/temp adjustment")
    st.write("- **Sharp Money**: ESPN line movement detection")
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
        st.info("No calibration data yet.")
    st.markdown("---")
    st.markdown("### 📊 API Usage")
    api_usage_cols = st.columns(3)
    with api_usage_cols[0]:
        st.write(format_api_usage(API_SPORTS_COUNTER_PATH, daily_limit=100, api_name="API-Sports"))
    with api_usage_cols[1]:
        st.write(format_api_usage(SPORTMONKS_COUNTER_PATH, monthly_limit=500, api_name="Sportmonks"))
    with api_usage_cols[2]:
        st.write(format_api_usage(UNIFIED_COUNTER_PATH, monthly_limit=200, api_name="Unified"))
    st.markdown("---")
    st.markdown("**Data Sources**")
    st.write("- Props: PrizePicks Partner API (primary) / Public API / Underdog / OddsWrap")
    st.write("- Game matchups + odds: ESPN scoreboard API")
    st.write("- Line movement: ESPN Core API")
    st.write("- NBA rolling averages: NBA Stats API")
    st.write("- NBA team defensive ratings: NBA Stats API")
    st.write("- NBA season averages: balldontlie API")
    wnba_cache = os.path.join(CACHE_DIR, "wnba_rolling_avgs.pkl")
    if os.path.exists(wnba_cache):
        age_hours = (time.time() - os.path.getmtime(wnba_cache)) / 3600
        with open(wnba_cache, "rb") as f:
            wnba_data = pickle.load(f)
        st.write(f"- WNBA rolling averages: WNBA Stats API ({len(wnba_data)} players, refreshed {age_hours:.1f}hrs ago)")
    else:
        st.write("- WNBA averages: hardcoded")
    st.write("- NFL/Soccer/UFC: Hardcoded averages")
    st.write("- MLB Weather: wttr.in free API")
    st.markdown("---")
    st.markdown("**Cache Management**")
    cache_cols = st.columns(3)
    with cache_cols[0]:
        if st.button("Clear NBA Rolling Cache"):
            cache = os.path.join(CACHE_DIR, "nba_rolling_avgs.pkl")
            if os.path.exists(cache):
                os.remove(cache)
            st.success("NBA rolling cache cleared")
    with cache_cols[1]:
        if st.button("Clear WNBA Rolling Cache"):
            cache = os.path.join(CACHE_DIR, "wnba_rolling_avgs.pkl")
            if os.path.exists(cache):
                os.remove(cache)
            st.success("WNBA rolling cache cleared")
    with cache_cols[2]:
        if st.button("Clear All API Counters"):
            for path in [API_SPORTS_COUNTER_PATH, SPORTMONKS_COUNTER_PATH, UNIFIED_COUNTER_PATH]:
                if os.path.exists(path):
                    os.remove(path)
            st.success("API counters reset")
    st.markdown("---")
    st.markdown("**🔍 PrizePicks API Debug**")
    debug_sport = st.selectbox("Test sport", SPORTS, key="debug_sport_sel")
    if st.button("Test PrizePicks API", key="debug_pp"):
        league_ids = {"NBA":4,"MLB":5,"NHL":3,"NFL":7,"WNBA":8,"UFC":6,"Golf":11,"Tennis":12,"Soccer":2}
        lid = league_ids.get(debug_sport, 5)
        test_url = f"https://partner-api.prizepicks.com/projections?per_page=1000&league_id={lid}"
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
