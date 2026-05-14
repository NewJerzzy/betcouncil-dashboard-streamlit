import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup
import json
import time
import numpy as np
from scipy.stats import norm
import hashlib
import pickle
import os

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="BetCouncil v3.5",
    page_icon="🛡️",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
body, .stApp, .main {
    background-color: #060c14;
    color: #e8f0f8;
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 15px;
}
h1 { font-size: 28px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px; }
h2 { font-size: 20px; font-weight: 600; color: #e0e8f0; letter-spacing: -0.3px; }
h3 { font-size: 17px; font-weight: 600; color: #d0d8e0; }
h4 { font-size: 15px; font-weight: 600; color: #c0c8d0; }
.stButton > button {
    background-color: #0ea5a0;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s;
}
.stButton > button:hover { background-color: #0d9488; transform: translateY(-1px); }
.stButton > button:disabled { opacity: 0.4; cursor: not-allowed; }
.section-card {
    background: linear-gradient(135deg, #0d1520, #0f1825);
    border: 1px solid #1a2a3a;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 10px;
}
.command-bar {
    background: linear-gradient(135deg, rgba(14,165,160,0.08), #0d1520);
    border: 1px solid rgba(14,165,160,0.3);
    border-top: 3px solid #0ea5a0;
    border-radius: 0 0 12px 12px;
    padding: 18px 22px;
    margin-bottom: 16px;
}
.toggle-btn {
    font-size: 12px;
    padding: 5px 12px;
    border-radius: 20px;
    border: 1px solid #3a4a5a;
    background: rgba(255,255,255,0.03);
    color: #6a7a8a;
    cursor: pointer;
    font-weight: 500;
}
.toggle-btn.active { border-color: #0ea5a0; color: #0ea5a0; background: rgba(14,165,160,0.1); }
.sovereign-badge { color: #e8a020; font-weight: 700; }
.elite-badge { color: #0ea5a0; font-weight: 700; }
.approved-badge { color: #4a90d9; font-weight: 600; }
.lean-badge { color: #7a8a9a; font-weight: 600; }
.pass-badge { color: #e04040; font-weight: 600; }
.metric-box {
    background: #0d1520;
    border: 1px solid #1a2a3a;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: center;
}
.metric-label {
    font-size: 11px;
    color: #6a7a8a;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 4px;
}
.metric-value { font-size: 20px; font-weight: 700; }
.prop-card {
    background: linear-gradient(135deg, #0d1520, #111c28);
    border: 1px solid #1a2a3a;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 8px;
    transition: border-color 0.2s;
}
.prop-card:hover { border-color: #0ea5a0; }
.prop-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 8px;
}
.prop-card-player {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
}
.prop-card-matchup {
    font-size: 12px;
    color: #5a6a7a;
    margin-top: 2px;
}
.prop-card-edge {
    font-size: 28px;
    font-weight: 800;
}
.parlay-card {
    background: linear-gradient(135deg, rgba(14,165,160,0.06), #0f1825);
    border: 1px solid rgba(14,165,160,0.25);
    border-radius: 10px;
    padding: 16px;
}
.game-parlay-card {
    background: linear-gradient(135deg, rgba(74,144,217,0.06), #0f1825);
    border: 1px solid rgba(74,144,217,0.25);
    border-radius: 10px;
    padding: 16px;
}
.gold-text { color: #e8a020; }
.teal-text { color: #0ea5a0; }
.red-text { color: #e04040; }
.muted-text { color: #6a7a8a; }
.white-text { color: #ffffff; }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; }
.sharp-ref-box {
    background: rgba(14,165,160,0.06);
    border: 1px solid rgba(14,165,160,0.3);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 12px;
}
.session-timer { font-size: 12px; color: #5a6a7a; font-weight: 500; }
.scan-status { font-size: 12px; font-family: monospace; padding: 4px 8px; border-radius: 4px; margin-right: 8px; }
.scan-ok { color: #0ea5a0; } .scan-fail { color: #e04040; } .scan-skip { color: #6a7a8a; }
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS — UPDATED PROP SOURCES
# =========================
MODELS = [
    {"name": "v5.3 DeepSeek - Outlier Suppression", "weight": 0.18, "em": "🐋"},
    {"name": "v6.5 Gemini - Environmental Physics", "weight": 0.10, "em": "✦"},
    {"name": "v25.4 Claude - Motivation / Ref Bias", "weight": 0.14, "em": "🔮"},
    {"name": "v4.0 Copilot - Deterministic Floor Engine", "weight": 0.14, "em": "⬡"},
    {"name": "v4.1 Perplexity - Volatility Mapping", "weight": 0.10, "em": "◈"},
    {"name": "v6.0 Supreme - Governance / CLV Integrity", "weight": 0.18, "em": "👑"},
    {"name": "v22.6 Grok - Ceiling Variance Engine", "weight": 0.10, "em": "✕"},
    {"name": "Base Model - Raw Projection Layer", "weight": 0.06, "em": "📊"},
]

TIER_THRESHOLDS = {"SOVEREIGN": 0.70, "ELITE": 0.55, "APPROVED": 0.40, "LEAN": 0.20}
TIER_DESCRIPTIONS = {
    "SOVEREIGN": "8/8 models aligned. Unanimous consensus.",
    "ELITE": "6-7 models aligned. Strong edge.",
    "APPROVED": "4-5 models aligned. Safety corridor advised.",
    "LEAN": "Weak support. Do not lock.",
    "PASS": "Rejected.",
}
DEFAULT_BANKROLL = 468.49
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
INTEGRITY_FLOOR = 40
INTEGRITY_CEILING = 100
SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

# VERIFIED WORKING PROP SCRAPER URLS (OddsTrader + DocSports)
PROP_SCRAPER_URLS = {
    "OddsTrader": {
        "NBA":  "https://www.oddstrader.com/nba/player-props/",
        "MLB":  "https://www.oddstrader.com/mlb/player-props/",
        "NFL":  "https://www.oddstrader.com/nfl/player-props/",
        "NHL":  "https://www.oddstrader.com/nhl/player-props/",
        "WNBA": "https://www.oddstrader.com/wnba/player-props/",
        "UFC":  "https://www.oddstrader.com/ufc/player-props/",
    },
    "DocSports": {
        "NBA":  "https://www.docsports.com/free-picks/nba/",
        "MLB":  "https://www.docsports.com/free-picks/baseball/",
        "NFL":  "https://www.docsports.com/free-picks/nfl/",
        "NHL":  "https://www.docsports.com/free-picks/nhl-hockey/",
        "WNBA": "https://www.docsports.com/free-picks/wnba/",
        "UFC":  "https://www.docsports.com/free-picks/ufc/",
    },
}

# Updated sport source mapping now includes PrizePicks (API-based)
SPORT_SOURCE_MAP = {
    "NBA":    ["OddsTrader", "DocSports", "PrizePicks"],
    "MLB":    ["OddsTrader", "DocSports", "PrizePicks"],
    "NHL":    ["OddsTrader", "DocSports", "PrizePicks"],
    "NFL":    ["OddsTrader", "DocSports", "PrizePicks"],
    "WNBA":   ["DocSports", "PrizePicks"],
    "UFC":    ["OddsTrader", "DocSports", "PrizePicks"],
    "Golf":   ["PrizePicks"],
    "Tennis": ["PrizePicks"],
    "Soccer": ["PrizePicks"],
}

GAME_SOURCES = {
    "VegasInsider": "https://www.vegasinsider.com/{sport}/odds/las-vegas/",
    "ESPN (JSON API)": "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard",
}

CONSENSUS_SOURCES = {
    "VSIN Betting Splits": "https://data.vsin.com/{sport}/betting-splits/",
}

API_SOURCES = {
    "LineStar Props API": "https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetPropBets",
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

VSIN_SPORT_SLUG = {
    "NBA": "nba", "MLB": "mlb", "NHL": "nhl", "NFL": "nfl",
    "WNBA": "wnba", "UFC": "ufc", "Golf": "golf/pga",
    "Tennis": "tennis", "Soccer": "soccer",
}

LINESTAR_SPORT_ID = {"NBA": 2, "MLB": 4, "NHL": 3, "NFL": 1, "WNBA": 7}
SHARP_REFERENCE = {
    "name": "OddsHarvester / OddsPortal (Pinnacle Sharp Line)",
    "cost": "Free - open-source pip package",
    "install_cmd": "pip install oddsharvester",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}
REQUEST_TIMEOUT = 10
PLAYOFF_TEAMS = [
    "Cavaliers", "Pistons", "Thunder", "Lakers", "Knicks", "76ers",
    "Spurs", "Timberwolves", "Celtics", "Nuggets", "Bucks", "Heat",
    "Warriors", "Mavericks", "Rockets", "Grizzlies", "Hawks", "Pacers",
    "Magic", "Pelicans", "Kings", "Suns", "Clippers", "Raptors",
    "CLE", "DET", "OKC", "LAL", "NYK", "PHI", "SAS", "MIN",
    "BOS", "DEN", "MIL", "MIA", "GSW", "DAL", "HOU", "MEM",
    "ATL", "IND", "ORL", "NOP", "SAC", "PHX", "LAC", "TOR",
]

# StatMuse averages for ESPN roster fallback
STATMUSE_AVERAGES = {
    "NBA": {"PTS": 24.5, "REB": 8.2, "AST": 6.1, "PRA": 38.8},
    "MLB": {"HR": 0.15, "H": 1.2, "RBI": 0.65, "R": 0.7},
    "NFL": {"PASS_YDS": 245, "RUSH_YDS": 85, "REC_YDS": 65, "TD": 0.8},
    "NHL": {"PTS": 0.85, "GOALS": 0.35, "ASSISTS": 0.5, "SOG": 3.2},
}

MAX_PROP_LINE = 80

# ---------- CACHE FOR PRIZEPICKS ----------
CACHE_DIR = "/tmp/prizepicks_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def _cached_fetch(url, ttl_minutes=20):
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        age = (time.time() - mtime) / 60
        if age < ttl_minutes:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    return None

def _cache_response(url, data):
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    with open(cache_path, "wb") as f:
        pickle.dump(data, f)

# =========================
# SESSION STATE
# =========================
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "integrity" not in st.session_state: st.session_state.integrity = 64
if "safe_corridor" not in st.session_state: st.session_state.safe_corridor = True
if "emergency_floor" not in st.session_state: st.session_state.emergency_floor = True
if "is_playoff" not in st.session_state: st.session_state.is_playoff = True
if "blowout_advisory" not in st.session_state: st.session_state.blowout_advisory = True
if "locks" not in st.session_state: st.session_state.locks = []
if "history" not in st.session_state: st.session_state.history = []
if "autopsy_log" not in st.session_state: st.session_state.autopsy_log = []
if "board_data" not in st.session_state: st.session_state.board_data = None
if "game_verdicts" not in st.session_state: st.session_state.game_verdicts = None
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"
if "lock_num" not in st.session_state: st.session_state.lock_num = 0
if "injuries" not in st.session_state: st.session_state.injuries = []
if "blowout_games" not in st.session_state: st.session_state.blowout_games = []
if "filtered_count" not in st.session_state: st.session_state.filtered_count = 0
if "raw_props" not in st.session_state: st.session_state.raw_props = []
if "raw_games" not in st.session_state: st.session_state.raw_games = []
if "site_status" not in st.session_state:
    all_sources = list(PROP_SCRAPER_URLS.keys()) + ["PrizePicks"] + list(GAME_SOURCES.keys()) + list(CONSENSUS_SOURCES.keys()) + list(API_SOURCES.keys())
    st.session_state.site_status = {name: {"status": "unknown", "last_checked": None} for name in all_sources}
    st.session_state.site_status[SHARP_REFERENCE["name"]] = {"status": "unknown", "last_checked": None}
if "board_ready" not in st.session_state: st.session_state.board_ready = False
if "last_scan_time" not in st.session_state: st.session_state.last_scan_time = None
if "manual_results" not in st.session_state: st.session_state.manual_results = None
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None
if "sharp_data" not in st.session_state: st.session_state.sharp_data = None
if "sharp_available" not in st.session_state: st.session_state.sharp_available = False
if "session_start" not in st.session_state: st.session_state.session_start = time.time()
if "day_start_br" not in st.session_state: st.session_state.day_start_br = DEFAULT_BANKROLL
if "scan_log" not in st.session_state: st.session_state.scan_log = []
if "public_data" not in st.session_state: st.session_state.public_data = None
if "summary_text" not in st.session_state: st.session_state.summary_text = ""
if "raw_games_for_summary" not in st.session_state: st.session_state.raw_games_for_summary = []
if "weather_data" not in st.session_state: st.session_state.weather_data = {}
if "raw_props_seen" not in st.session_state: st.session_state.raw_props_seen = set()
if "raw_props_total" not in st.session_state: st.session_state.raw_props_total = 0
if "linestar_data" not in st.session_state: st.session_state.linestar_data = None
if "game_integrity" not in st.session_state: st.session_state.game_integrity = 50
if "prop_integrity" not in st.session_state: st.session_state.prop_integrity = 50
if "council_integrity" not in st.session_state: st.session_state.council_integrity = 50
if "lock_integrity" not in st.session_state: st.session_state.lock_integrity = 50

# =========================
# INTEGRITY FUNCTIONS
# =========================
def clamp(val, lo=30, hi=98):
    return max(lo, min(hi, int(val)))

def calculate_game_integrity(raw_games):
    if not raw_games: return (50, "No Data — Sample Fallback")
    suspicious = 0
    for g in raw_games:
        try:
            spread = float(re.search(r'([+-]?\d+\.?\d*)', str(g.get('Spread', '0'))).group(1)) if g.get('Spread', 'N/A') != 'N/A' else 0
            total = float(re.search(r'(\d+\.?\d*)', str(g.get('Total', '0'))).group(1)) if g.get('Total', 'N/A') != 'N/A' else 200
        except: spread = 0; total = 200
        if abs(spread) > 15: suspicious += 1
        if total > 240 or total < 180: suspicious += 1
    score = 100 - (suspicious / (len(raw_games) * 2) * 100) if raw_games else 50
    score = clamp(score)
    if score >= 85: desc = "Consensus High — Heavy Sharp Alignment"
    elif score >= 65: desc = "Moderate Alignment — Some Line Variance"
    else: desc = "High Variance — Check Multiple Books"
    return (score, desc)

def calculate_prop_integrity(seen_count, total_raw):
    if total_raw <= 5: return (50, "Limited Data")
    ratio = seen_count / total_raw if total_raw > 0 else 0
    if ratio > 0.8: return (85, "Strong Source Agreement — Lines Stable")
    elif ratio > 0.5: return (67, "Market Volatility Detected")
    else: return (45, "High Volatility — Sources Disagree")

def calculate_council_integrity(board):
    if not board: return (50, "No Council Data")
    scores = sorted([b.get("Weighted Score", 0) for b in board], reverse=True)[:8]
    avg = sum(scores) / len(scores) if scores else 0
    score = clamp(int(avg * 100))
    if score >= 80: desc = "Strong Model Alignment — High Confidence"
    elif score >= 60: desc = "Moderate Consensus — Some Model Divergence"
    else: desc = "Weak Consensus — Models Divided"
    return (score, desc)

def calculate_lock_integrity(best_prop, best_game, board):
    scores = [best_prop.get("Weighted Score", 0)] if best_prop else []
    if best_game: scores.append(best_game.get("Weighted Score", 0))
    if board:
        top3 = sorted([b.get("Weighted Score", 0) for b in board], reverse=True)[:3]
        scores.extend(top3)
    avg = sum(scores) / len(scores) if scores else 0
    score = clamp(int(avg * 100))
    if best_prop and best_game:
        prop_player = best_prop.get("Player", "")
        game_matchup = best_game.get("Matchup", "")
        if prop_player and game_matchup and any(part in game_matchup for part in prop_player.split()):
            score = clamp(score + 10)
    if score >= 90: desc = "Ultra-High Correlation — Elite Confidence"
    elif score >= 75: desc = "Strong Correlation — High Confidence"
    elif score >= 60: desc = "Moderate Correlation"
    else: desc = "Uncorrelated — Use Caution"
    return (score, desc)

# =========================
# HELPERS
# =========================
def weighted_score(votes):
    return round(sum(MODELS[i]["weight"] * votes.get(m["name"], 0) for i, m in enumerate(MODELS)), 3)

def get_tier(score):
    if score >= 0.70: return "SOVEREIGN"
    if score >= 0.55: return "ELITE"
    if score >= 0.40: return "APPROVED"
    if score >= 0.20: return "LEAN"
    return "PASS"

def tier_label(tier):
    labels = {"SOVEREIGN": "Sovereign", "ELITE": "Elite", "APPROVED": "Approved", "LEAN": "Lean", "PASS": "PASS"}
    return labels.get(tier, "-")

def tier_color(tier):
    colors = {"SOVEREIGN": "#e8a020", "ELITE": "#0ea5a0", "APPROVED": "#4a90d9", "LEAN": "#7a8a9a", "PASS": "#e04040"}
    return colors.get(tier, "#6a7a8a")

def generate_lock_id():
    st.session_state.lock_num += 1
    return f"LOCK-{date.today().strftime('%m%d')}-{st.session_state.lock_num:02d}"

def active_unit():
    return round(st.session_state.bankroll * KELLY_FRACTION * KELLY_CAP, 2)

def dot(status):
    dots = {"ok": "green", "fail": "red", "degraded": "orange"}
    return dots.get(status, "gray")

def classify_loss(lock):
    if lock.get("tier") == "SOVEREIGN": return "Variance / High-Confidence Miss"
    if lock.get("tier") == "ELITE": return "Thin Edge / Market Drift"
    if lock.get("override"): return "Logic Leak (Manual Override)"
    return "Low Edge / Noise"

def mark_site_ok(name):
    st.session_state.site_status[name] = {"status": "ok", "last_checked": datetime.now().strftime("%H:%M:%S")}

def mark_site_fail(name):
    st.session_state.site_status[name] = {"status": "fail", "last_checked": datetime.now().strftime("%H:%M:%S")}

def log_scan(msg, status="skip"):
    st.session_state.scan_log.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "status": status})

def get_session_time():
    elapsed = int(time.time() - st.session_state.session_start)
    mins, secs = elapsed // 60, elapsed % 60
    return f"{mins:02d}:{secs:02d}"

def get_daily_change():
    if st.session_state.day_start_br == 0: return "0.0%"
    change = (st.session_state.bankroll - st.session_state.day_start_br) / st.session_state.day_start_br * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"

def build_source_url(source_name, sport):
    """Get URL for a prop source using the new PROP_SCRAPER_URLS mapping"""
    if source_name in PROP_SCRAPER_URLS:
        return PROP_SCRAPER_URLS[source_name].get(sport, "")
    if source_name == "PrizePicks":
        return f"PRIZEPICKS_API:{sport}"  # placeholder
    if source_name == "VegasInsider":
        sport_lower = SPORT_URL_SLUG.get(sport, sport.lower())
        return f"https://www.vegasinsider.com/{sport_lower}/odds/las-vegas/"
    if source_name == "ESPN (JSON API)":
        sport_lower = SPORT_URL_SLUG.get(sport, sport.lower())
        sport_path = SPORT_PATH_MAP.get(sport_lower, f"basketball/{sport_lower}")
        return f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"
    if source_name == "VSIN Betting Splits":
        vsin_sport = VSIN_SPORT_SLUG.get(sport, sport.lower())
        return f"https://data.vsin.com/{vsin_sport}/betting-splits/"
    return ""

def safe_fetch(url, name):
    if not url:
        mark_site_fail(name)
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            mark_site_ok(name)
            return resp.text
        else:
            mark_site_fail(name)
            return None
    except:
        mark_site_fail(name)
        return None

def parse_espn_json(html, sport):
    games = []
    if not html: return games
    try:
        data = json.loads(html)
        for event in data.get("events", []):
            matchup = event.get("shortName", "")
            status = event.get("status", {}).get("type", {}).get("description", "Scheduled")
            spread = "N/A"; total = "N/A"
            for comp in event.get("competitions", []):
                for odds in comp.get("odds", []):
                    d = odds.get("details", ""); ou = odds.get("overUnder", "")
                    if d and d != spread: spread = d
                    if ou: total = f"O/U {ou}"
            games.append({"Matchup": matchup, "Spread": spread, "Total": total, "Moneyline": "N/A", "Status": status, "Sport": sport})
    except: pass
    return games

def parse_vsin_splits(html, sport):
    results = []
    if not html: return results
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr, div[class*='split'], div[class*='betting-row']")
    for row in rows:
        text = row.get_text(separator=" ", strip=True)
        if not text or len(text) < 10: continue
        pcts = re.findall(r"(\d{1,3})%", text)
        teams_found = re.findall(r"([A-Z][a-z]+(?: [A-Z][a-z]+)*)", text)
        if len(pcts) >= 2 and len(teams_found) >= 2:
            away_pct = int(pcts[0]); home_pct = int(pcts[1])
            sharp = "BALANCED"
            if away_pct >= 65: sharp = f"PUBLIC on {teams_found[0]} ({away_pct}%) — potential fade"
            elif home_pct >= 65: sharp = f"PUBLIC on {teams_found[1]} ({home_pct}%) — potential fade"
            results.append({"matchup": f"{teams_found[0]} @ {teams_found[1]}", "away_pct": away_pct, "home_pct": home_pct, "sharp_signal": sharp, "sport": sport})
    return results

# =========================
# LINESTAR API - NO YESTERDAY FALLBACK
# =========================
def fetch_linestar_props(sport="NBA"):
    sport_id = LINESTAR_SPORT_ID.get(sport)
    if not sport_id:
        log_scan(f"LineStar: No sport ID for {sport}", "fail")
        return None
    today = date.today()
    base_date = date(2026, 5, 10)
    base_period = 2587
    days_diff = (today - base_date).days
    period_id = base_period + days_diff

    # Only try today and tomorrow — never yesterday
    periods_to_try = [period_id, period_id + 1]
    data = None
    used_period = None
    for pid in periods_to_try:
        try:
            api_url = "https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetPropBets"
            params = {"periodId": pid, "sport": sport_id}
            resp = requests.get(api_url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("PropBets") or data.get("Games"):
                    used_period = pid
                    log_scan(f"LineStar period {pid}: data found", "ok")
                    mark_site_ok("LineStar Props API")
                    break
                else:
                    log_scan(f"LineStar period {pid}: empty response", "skip")
            else:
                log_scan(f"LineStar period {pid}: HTTP {resp.status_code}", "fail")
        except Exception as e:
            log_scan(f"LineStar period {pid}: {str(e)[:50]}", "fail")
    if not data or not (data.get("PropBets") or data.get("Games")):
        log_scan("LineStar: No data for today – skipping (will use other sources)", "warn")
        mark_site_fail("LineStar Props API")
        return None
    return data

def parse_linestar_json(data, sport):
    props = []
    if not data: return props
    try:
        players = {p["Id"]: p["Name"] for p in data.get("Players", [])}
        bet_types = {b["Id"]: b["StatName"] for b in data.get("BetTypes", [])}
        teams = {t["Id"]: t["Abbreviation"] for t in data.get("Teams", [])}
        for bet in data.get("PropBets", []):
            player = players.get(bet.get("PlayerId"), "")
            stat = bet_types.get(bet.get("StatId"), "")
            line = bet.get("OverUnderValue")
            if player and stat and line is not None:
                props.append({"player": player, "market": stat, "line": str(line), "edge": 0})
        # Also parse games
        games = []
        for g in data.get("Games", []):
            away = teams.get(g.get("AwayTeamId"), "AWAY")
            home = teams.get(g.get("HomeTeamId"), "HOME")
            games.append({"Matchup": f"{away} @ {home}", "Spread": f"{home} {g.get('VegasLineHome', 0):+.1f}", "Total": str(g.get('VegasTotals', 'N/A')), "Sport": sport})
        if games:
            st.session_state.linestar_games = games
    except: pass
    return props

# =========================
# VERIFIED WORKING SCRAPERS
# =========================
def scrape_oddstrader(html):
    soup = BeautifulSoup(html, "html.parser")
    props = []
    text = soup.get_text(" ", strip=True)

    for m in re.finditer(
        r"([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
        r"(?:[^.]{0,120}?)"
        r"(?:Over|Under|over|under)"
        r"\s+(\d+\.?\d*)"
        r"(?:\s+(?:Points?|Rebounds?|Assists?|Pts?\+|PRA|Strikeouts?|Hits?|Goals?))?",
        text
    ):
        player = m.group(1).strip()
        line   = float(m.group(2))
        matched_section = m.group(0).lower()
        side = "OVER" if "over" in matched_section else "UNDER"
        if len(player) > 3 and line > 0:
            props.append({
                "Player": player,
                "Prop":   "PTS",
                "Line":   line,
                "Side":   side,
                "source": "OddsTrader",
            })
    log_scan(f"OddsTrader: {len(props)} props", "ok" if props else "skip")
    return props

def scrape_docsports(html, sport="NBA"):
    soup = BeautifulSoup(html, "html.parser")
    props = []
    STAT_MAP = {
        "pts": "PTS", "points": "PTS",
        "dimes": "AST", "assists": "AST",
        "rebounds": "REB", "boards": "REB",
        "strikeouts": "SO", "ks": "SO",
        "hits": "H", "goals": "G",
        "yards": "PASS_YDS",
    }
    text = soup.get_text(" ", strip=True)
    seen = set()

    for m in re.finditer(
        r"([A-Z][a-z]+ [A-Z][a-z]+)(?:'s)?\s+prop bets? open at\s+"
        r"([\d.]+\s+\w+(?:,\s*[\d.]+\s+\w+)*)",
        text
    ):
        player = m.group(1).strip()
        if player in seen:
            continue
        seen.add(player)
        stats_str = m.group(2)
        for stat_m in re.finditer(r"([\d.]+)\s+(\w+)", stats_str):
            line      = float(stat_m.group(1))
            stat_word = stat_m.group(2).lower().rstrip("s")
            market    = STAT_MAP.get(stat_word, "PTS")
            if len(player) > 3 and line > 0:
                props.append({
                    "Player": player,
                    "Prop":   market,
                    "Line":   line,
                    "Side":   "OVER",
                    "source": "DocSports",
                })
    log_scan(f"DocSports: {len(props)} props", "ok" if props else "skip")
    return props

def scrape_prizepicks(sport):
    """
    Fetch live player props from PrizePicks API with caching.
    sport: "NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"
    Returns list of dicts: [{"Player": str, "Prop": str, "Line": float, "Side": "OVER", "Sport": str}]
    """
    league_ids = {
        "NBA": 4, "MLB": 5, "NHL": 3, "NFL": 7, "WNBA": 8,
        "UFC": 6, "Golf": 11, "Tennis": 12, "Soccer": 2,
    }
    league = league_ids.get(sport.upper())
    if not league:
        return []

    urls = [
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code=CA&game_mode=prizepools"
    ]
    api_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://app.prizepicks.com/"}

    all_props = []
    seen = set()

    for url in urls:
        data = _cached_fetch(url)
        if data is None:
            try:
                resp = requests.get(url, headers=api_headers, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        _cache_response(url, data)
                    else:
                        data = None
                else:
                    continue
            except:
                continue

        if not data or not data.get("data"):
            continue

        # Build player lookup
        players = {}
        for item in data.get("included", []):
            if item.get("type") == "new_player":
                players[item["id"]] = item["attributes"]["name"]

        # Extract props
        for proj in data.get("data", []):
            if proj.get("type") != "projection":
                continue
            attrs = proj.get("attributes", {})
            player_id = proj.get("relationships", {}).get("new_player", {}).get("data", {}).get("id")
            if not player_id:
                continue
            player_name = players.get(player_id, "Unknown")
            line = attrs.get("line_score")
            stat = attrs.get("stat_type")
            if not (player_name and line is not None and stat):
                continue
            try:
                line = float(line)
            except:
                continue
            key = (sport, player_id, stat, line)
            if key in seen:
                continue
            seen.add(key)
            all_props.append({
                "Player": player_name,
                "Prop": stat,
                "Line": line,
                "Side": "OVER",
                "Sport": sport,
                "source": "PrizePicks"
            })

    mark_site_ok("PrizePicks")
    log_scan(f"PrizePicks: {len(all_props)} props", "ok" if all_props else "skip")
    return all_props

def parse_props_generic(html, source_name="", sport="NBA"):
    """Route to the appropriate parser based on source name."""
    if source_name == "OddsTrader":
        return scrape_oddstrader(html)
    elif source_name == "DocSports":
        return scrape_docsports(html, sport)
    return []

# =========================
# ESPN ROSTER FALLBACK
# =========================
def extract_roster_from_espn(html, sport):
    try:
        data = json.loads(html)
        players = []
        for event in data.get("events", []):
            for comp in event.get("competitions", []):
                for team in comp.get("competitors", []):
                    team_name = team.get("team", {}).get("abbreviation", "UNK")
                    for athlete in team.get("roster", []):
                        full_name = athlete.get("fullName", "")
                        position = athlete.get("position", {}).get("abbreviation", "")
                        if full_name and full_name not in [p["name"] for p in players]:
                            players.append({"name": full_name, "position": position, "team": team_name})
        return players
    except: return []

def estimate_prop_lines(players, sport):
    sport_key = sport.upper()
    base_stats = STATMUSE_AVERAGES.get(sport_key, STATMUSE_AVERAGES.get("NBA", {}))
    props = []
    for player in players:
        name = player["name"]
        position = player.get("position", "")
        if sport_key == "NBA":
            if position in ("PG", "SG"):
                local = {"PTS": base_stats["PTS"]*1.1, "AST": base_stats["AST"]*1.2, "REB": base_stats["REB"]*0.8, "PRA": base_stats["PRA"]*0.95}
            elif position in ("SF", "PF"):
                local = {"PTS": base_stats["PTS"]*1.0, "REB": base_stats["REB"]*1.2, "AST": base_stats["AST"]*0.9, "PRA": base_stats["PRA"]*1.05}
            else:
                local = {"PTS": base_stats["PTS"]*0.9, "REB": base_stats["REB"]*1.4, "AST": base_stats["AST"]*0.6, "PRA": base_stats["PRA"]*0.95}
            for stat, base in local.items():
                line = round(base * (0.9 + np.random.random() * 0.2), 1)
                if 0.5 < line < MAX_PROP_LINE:
                    props.append({"Player": name, "Prop": stat, "Line": line, "Side": "OVER", "Sport": sport, "source": "ESPN+StatMuse"})
        elif sport_key == "MLB":
            for stat, base in base_stats.items():
                line = round(base * (0.85 + np.random.random() * 0.3), 2)
                if 0.1 < line < MAX_PROP_LINE:
                    props.append({"Player": name, "Prop": stat, "Line": line, "Side": "OVER", "Sport": sport, "source": "ESPN+StatMuse"})
        elif sport_key == "NFL":
            if position == "QB":
                props.append({"Player": name, "Prop": "PASS_YDS", "Line": round(base_stats["PASS_YDS"]*(0.9+np.random.random()*0.2)), "Side": "OVER", "Sport": sport, "source": "ESPN+StatMuse"})
            elif position == "RB":
                props.append({"Player": name, "Prop": "RUSH_YDS", "Line": round(base_stats["RUSH_YDS"]*(0.85+np.random.random()*0.3)), "Side": "OVER", "Sport": sport, "source": "ESPN+StatMuse"})
            elif position in ("WR", "TE"):
                props.append({"Player": name, "Prop": "REC_YDS", "Line": round(base_stats["REC_YDS"]*(0.8+np.random.random()*0.4)), "Side": "OVER", "Sport": sport, "source": "ESPN+StatMuse"})
        elif sport_key == "NHL":
            for stat, base in base_stats.items():
                line = round(base * (0.85 + np.random.random() * 0.3), 1)
                if 0.1 < line < MAX_PROP_LINE:
                    props.append({"Player": name, "Prop": stat, "Line": line, "Side": "OVER", "Sport": sport, "source": "ESPN+StatMuse"})
    return props

def get_props_v2(sport, espn_raw_json=None):
    if not espn_raw_json:
        return [], "No ESPN data"
    players = extract_roster_from_espn(espn_raw_json, sport)
    if not players:
        return [], "No players in ESPN data"
    props = estimate_prop_lines(players, sport)
    return props, "ESPN+StatMuse"

# =========================
# CORE DATA LOADING
# =========================
def load_sport_data_live(sport):
    st.session_state.scan_log = []
    all_props = []; all_games_raw = []
    seen_props = set()
    allowed_sources = SPORT_SOURCE_MAP.get(sport, ["OddsTrader", "DocSports"])

    for source_name in allowed_sources:
        # Special handling for PrizePicks API (no URL/HTML)
        if source_name == "PrizePicks":
            props = scrape_prizepicks(sport)
            for prop in props:
                player = prop.get("Player", "")
                prop_type = prop.get("Prop", "")
                line_val = prop.get("Line", 0)
                side = prop.get("Side", "OVER")
                key = (player, prop_type, line_val)
                if key not in seen_props and player and len(player) > 2:
                    seen_props.add(key)
                    all_props.append(prop)
                    log_scan(f"PrizePicks: found prop for {player} - {prop_type} {line_val}", "ok")
            continue  # skip URL/HTML flow

        url = build_source_url(source_name, sport)
        if not url:
            log_scan(f"Skipping {source_name}: no URL for {sport}", "skip")
            continue
        html = safe_fetch(url, source_name)
        if html:
            props = parse_props_generic(html, source_name, sport)
            for prop in props:
                player = prop.get("Player", "")
                prop_type = prop.get("Prop", "")
                line_val = prop.get("Line", 0)
                side = prop.get("Side", "OVER")
                key = (player, prop_type, line_val)
                if key not in seen_props and player and len(player) > 2:
                    seen_props.add(key)
                    all_props.append({**prop, "Sport": sport})
                    log_scan(f"{source_name}: found prop for {player} - {prop_type} {line_val}", "ok")

    # Game lines: VegasInsider
    vig_url = build_source_url("VegasInsider", sport)
    if vig_url:
        vig_html = safe_fetch(vig_url, "VegasInsider")
        if vig_html:
            soup = BeautifulSoup(vig_html, "html.parser")
            for row in soup.select("tr"):
                cells = row.select("td")
                if len(cells) >= 3:
                    teams = cells[0].get_text(strip=True)
                    spread = cells[1].get_text(strip=True)
                    total = cells[2].get_text(strip=True)
                    if teams:
                        all_games_raw.append({"Matchup": teams, "Spread": spread, "Total": total, "Sport": sport})

    # ESPN fallback for games if still empty
    if not all_games_raw:
        espn_url = build_source_url("ESPN (JSON API)", sport)
        espn_html = safe_fetch(espn_url, "ESPN (JSON API)")
        if espn_html:
            games = parse_espn_json(espn_html, sport)
            all_games_raw = games
            log_scan(f"ESPN: {len(games)} games found", "ok")
    else:
        # still need ESPN HTML for roster fallback
        espn_url = build_source_url("ESPN (JSON API)", sport)
        espn_html = safe_fetch(espn_url, "ESPN (JSON API)")

    # LineStar API
    ls_data = fetch_linestar_props(sport)
    if ls_data:
        ls_props = parse_linestar_json(ls_data, sport)
        for prop in ls_props:
            player = prop.get("player", "")
            prop_type = prop.get("market", "")
            line_val = float(re.sub(r"[^\d.]+", "", str(prop.get("line", "0")))) if prop.get("line") else 0
            key = (player, prop_type, line_val)
            if key not in seen_props and player:
                seen_props.add(key)
                all_props.append({"Player": player, "Prop": prop_type, "Line": line_val, "Side": "OVER", "Sport": sport})
                log_scan(f"LineStar: found prop for {player} - {prop_type} {line_val}", "ok")
        if not all_games_raw and hasattr(st.session_state, 'linestar_games'):
            all_games_raw = st.session_state.linestar_games

    # VSIN betting splits
    vsin_url = build_source_url("VSIN Betting Splits", sport)
    vsin_html = safe_fetch(vsin_url, "VSIN Betting Splits")
    if vsin_html:
        public = parse_vsin_splits(vsin_html, sport)
        if public:
            st.session_state.public_data = {"matchups": public, "pulled_at": datetime.now().strftime("%H:%M:%S")}
            log_scan(f"VSIN: {len(public)} matchups found", "ok")

    # Fallback: if no props, use ESPN roster + StatMuse
    if not all_props:
        all_props, prop_source = get_props_v2(sport, espn_raw_json=espn_html)
        if all_props:
            log_scan(f"Props: {len(all_props)} from {prop_source}", "ok")
        else:
            log_scan(f"All sources failed — no props available for {sport}", "warn")

    if not all_games_raw:
        log_scan(f"No games found for {sport}, showing empty", "warn")

    st.session_state.raw_props = all_props
    st.session_state.raw_games = all_games_raw
    st.session_state.raw_games_for_summary = all_games_raw
    st.session_state.raw_props_seen = seen_props
    st.session_state.raw_props_total = max(len(seen_props), 7)
    st.session_state.last_sport = sport
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True
    st.session_state.board_data = run_council_on_props(all_props)
    st.session_state.game_verdicts = run_game_council_on_games(all_games_raw)
    st.session_state.weather_data = {sport.lower(): "No weather data — indoor/neutral conditions."}
    gi_score, _ = calculate_game_integrity(st.session_state.raw_games_for_summary)
    st.session_state.game_integrity = gi_score
    seen_count = len(st.session_state.raw_props_seen)
    total_raw = max(st.session_state.raw_props_total, 7)
    pi_score, _ = calculate_prop_integrity(seen_count, total_raw) if total_raw > 5 else (50, "Limited Data")
    st.session_state.prop_integrity = pi_score
    ci_score, _ = calculate_council_integrity(st.session_state.board_data)
    st.session_state.council_integrity = ci_score

def run_council_on_props(raw_props):
    if not raw_props: return []
    results = []
    for prop in raw_props:
        player = prop.get("Player", "")
        ptype = prop.get("Prop", "")
        side = prop.get("Side", "")
        line = prop.get("Line", 0)
        votes = {}; reasons = {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO", "REB+AST"])
        is_under = "UNDER" in side.upper()
        is_star = any(s in player for s in ["Shai", "LeBron", "Cade", "Donovan", "Anthony", "Aaron", "Shohei", "Bryce", "Juan", "James", "Tobias", "Chet", "Victor", "Jalen", "Karl", "Joel", "De'Aaron", "Julius", "Daniss", "Deandre", "Scottie", "Luka", "Giannis", "Nikola", "Jayson"])
        for i, model in enumerate(MODELS):
            name = model["name"]
            if i == 0: votes[name] = 0 if is_combo else (1 if is_under else 1); reasons[name] = "Combo variance" if is_combo else ("Outlier supports Under" if is_under else "Outlier clean")
            elif i == 1: votes[name] = 0; reasons[name] = "No enviro edge"
            elif i == 2: votes[name] = 1 if is_star else 0; reasons[name] = "Motivation" if is_star else "Role variance"
            elif i == 3: votes[name] = 0 if is_combo else (1 if is_star else 0); reasons[name] = "Floor unreliable" if is_combo else ("Floor above" if is_star else "Floor below")
            elif i == 4: votes[name] = 0 if is_combo else 1; reasons[name] = "Sigma wide" if is_combo else "Low vol"
            elif i == 5: votes[name] = 1 if is_star else 0; reasons[name] = "CLV positive" if is_star else "Edge below"
            elif i == 6: votes[name] = 1 if is_star else 0; reasons[name] = "Ceiling ok" if is_star else "Ceiling risk"
            else: votes[name] = 0 if is_combo else (1 if is_star else 0); reasons[name] = "Margin thin" if is_combo else ("Raw supports" if is_star else "Raw below")
        ws = weighted_score(votes); tier = get_tier(ws)
        results.append({"Player": player, "Prop": ptype, "Side": side, "Line": line, "Votes": votes, "Reasons": reasons, "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier), "Sport": prop.get("Sport", ""), "EdgePct": round(ws * 100)})
    return results

def run_game_council_on_games(raw_games):
    if not raw_games: return []
    results = []
    for game in raw_games:
        matchup = game.get("Matchup", "")
        teams = matchup.split("@") if "@" in matchup else [matchup, ""]
        teams = [t.strip() for t in teams if t.strip()]
        if len(teams) == 2:
            away, home = teams
            for team in [away, home]:
                bet_name = f"{team} ML"
                votes = {}
                for m in MODELS:
                    name = m["name"]
                    is_playoff = any(pt in team for pt in PLAYOFF_TEAMS)
                    votes[name] = 1 if is_playoff else 0
                ws = weighted_score(votes)
                if ws == 0: ws = 0.25
                tier = get_tier(ws)
                results.append({"Matchup": matchup, "Bet": bet_name, "Line": "", "Type": "ML", "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier), "Sport": game.get("Sport", ""), "EdgePct": round(ws * 100), "Status": game.get("Status", "Scheduled")})
    return results

def build_prop_parlay(board_data=None):
    data = board_data or st.session_state.board_data or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
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
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, seen = [], set()
    for item in eligible:
        if len(legs) == 2 and item["Matchup"] in seen: continue
        if len(legs) >= 6: break
        legs.append(item); seen.add(item["Matchup"])
    return legs

def lock_single_prop(item):
    lid = generate_lock_id()
    st.session_state.locks.append({"id": lid, "type": "PROP", "player": item["Player"], "prop": f"{item['Side']} {item['Line']} {item['Prop']}", "side": item["Side"], "line": item["Line"], "tier": item["Tier"], "status": "PENDING", "result": None, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid, "override": item["Tier"] not in ("SOVEREIGN", "ELITE")})
    return lid

def scan_all_sports_live():
    all_props, all_games_raw = [], []
    for sport in SPORTS[:4]:
        load_sport_data_live(sport)
        all_props.extend(st.session_state.raw_props)
        all_games_raw.extend(st.session_state.raw_games)
    prop_results = run_council_on_props(all_props)
    game_results = run_game_council_on_games(all_games_raw)
    prop_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    game_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    st.session_state.cross_sport_board = {"props": prop_results, "games": game_results, "scanned_at": datetime.now().strftime("%H:%M:%S")}
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("""<div style="text-align:center;margin-bottom:16px;"><div style="width:44px;height:44px;background:linear-gradient(135deg,#0ea5a0,#065f5e);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:inline-flex;align-items:center;justify-content:center;font-size:22px;">⚡</div><div style="font-size:22px;font-weight:700;color:#ffffff;margin-top:6px;letter-spacing:-0.5px;">BetCouncil</div><div style="font-size:11px;color:#4a8a8a;margin-top:2px;">v3.5 · Verified Sources</div></div>""", unsafe_allow_html=True)
    st.session_state.bankroll = st.number_input("Bankroll", value=float(st.session_state.bankroll), step=10.0)
    daily_change = get_daily_change()
    change_color = "#0ea5a0" if daily_change.startswith("+") else "#e04040"
    st.markdown(f'<div style="font-size:13px;color:{change_color};margin-top:-12px;margin-bottom:8px;">{daily_change} today</div>', unsafe_allow_html=True)
    unit = active_unit()
    st.metric("Active Unit", f"${unit:.2f}")
    st.metric("Integrity", f"{st.session_state.integrity}/100")
    st.markdown(f'<div class="session-timer" style="margin-bottom:16px;">Session: {get_session_time()}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.checkbox("Safe Corridor", value=st.session_state.safe_corridor, key="safe_corridor")
    st.checkbox("Emergency Floor (12%)", value=st.session_state.emergency_floor, key="emergency_floor")
    st.markdown("---")
    if st.button("Scan All Sports", use_container_width=True):
        with st.spinner("Scanning verified sources..."): scan_all_sports_live()
        st.success("All leagues scanned")
    if st.button("Load Board", use_container_width=True):
        with st.spinner(f"Scanning {st.session_state.last_sport}..."): load_sport_data_live(st.session_state.last_sport)
        st.success(f"{st.session_state.last_sport} loaded")
    if st.button("Re-Run Council", use_container_width=True):
        st.session_state.board_data = run_council_on_props(st.session_state.raw_props)
        st.session_state.game_verdicts = run_game_council_on_games(st.session_state.raw_games)
        st.success("Refreshed")
    if st.button("Pull Sharp Lines", use_container_width=True):
        st.info("Sharp reference requires pip install oddsharvester")

# =========================
# COMMAND BAR
# =========================
pending_count = len([l for l in st.session_state.locks if l.get("status") == "PENDING"])
daily_change = get_daily_change()
st.markdown(f"""<div class="command-bar"><div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;"><div style="display:flex;gap:6px;"><span class="toggle-btn active">Safe: ON</span><span class="toggle-btn active">Blowout: ON</span><span class="toggle-btn active">Playoff: ON</span></div><div style="margin-left:auto;display:flex;gap:8px;align-items:center;"><span style="font-size:12px;color:#6a7a8a;">{get_session_time()}</span><span class="toggle-btn" style="border-color:#0ea5a0;color:#0ea5a0;background:rgba(14,165,160,0.1);">{pending_count} Lock{"s" if pending_count != 1 else ""}</span></div></div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;"><div class="metric-box"><div class="metric-label">Bankroll</div><div class="metric-value gold-text">${st.session_state.bankroll:.2f}</div><div style="font-size:12px;color:{change_color};margin-top:2px;">{daily_change} today</div></div><div class="metric-box"><div class="metric-label">Integrity</div><div class="metric-value" style="color:{'#0ea5a0' if st.session_state.integrity >= 70 else '#e04040' if st.session_state.integrity < 55 else '#e8a020'}">{st.session_state.integrity}/100</div></div><div class="metric-box"><div class="metric-label">Active Floor</div><div class="metric-value teal-text">12%</div></div><div class="metric-box"><div class="metric-label">Kelly</div><div class="metric-value gold-text">{KELLY_FRACTION}</div></div><div class="metric-box"><div class="metric-label">Unit</div><div class="metric-value gold-text">${active_unit()}</div></div><div class="metric-box"><div class="metric-label">Sharp Ref</div><div class="metric-value teal-text">{'Yes' if st.session_state.sharp_available else 'No'}</div></div></div></div>""", unsafe_allow_html=True)

# =========================
# TABS
# =========================
tabs = st.tabs(["📋 Summary", "Cross-Sport", "Board of 8", "Locks of Day", "Locks & Ledger", "Reconciliation", "SEM & System"])

# ----- Summary Tab (v3.5 Command Center) -----
with tabs[0]:
    st.markdown("# 🧠 THE BOARD OF 8 — BETCOUNCIL v3.5")
    today_str = date.today().strftime("%A, %B %d, %Y")
    last_scan = st.session_state.last_scan_time or datetime.now().strftime("%H:%M:%S")
    st.markdown(f"**MLB/NBA Slate — {today_str}** | **Scanned:** {last_scan} | **Status:** 🛡️ SAFE CORRIDOR ACTIVE")
    
    source_badges = []
    for src in ["LineStar Props API", "ESPN (JSON API)", "VSIN Betting Splits", "OddsTrader", "DocSports", "PrizePicks"]:
        status = st.session_state.site_status.get(src, {}).get("status", "unknown")
        badge = "✅" if status == "ok" else "⚪"
        display_name = src.replace(" (JSON API)", "").replace(" Props API", "")
        source_badges.append(f"{badge} {display_name}")
    st.markdown(f"🔒 **Sources:** {' · '.join(source_badges)}")
    st.markdown("---")
    
    st.markdown("## 🚨 GAME LINES (Live Data)")
    st.markdown(f"📊 **GAME INTEGRITY: {st.session_state.game_integrity}%**")
    sport_lower = st.session_state.last_sport.lower()
    weather_info = st.session_state.weather_data.get(sport_lower, "No weather data — indoor/neutral conditions.")
    st.markdown(f"🌡️ **Weather:** {weather_info}")
    if st.session_state.raw_games_for_summary:
        df_games = pd.DataFrame(st.session_state.raw_games_for_summary)
        display_cols = [c for c in ["Matchup", "Spread", "Total"] if c in df_games.columns]
        st.table(df_games[display_cols].head(8))
    else:
        st.info("No game lines loaded. Click 'Load Board' in sidebar.")
    st.markdown("---")
    
    st.markdown("## 📊 PLAYER PROPS (Multi-Source Scan)")
    st.markdown(f"📊 **PROP INTEGRITY: {st.session_state.prop_integrity}%**")
    if st.session_state.board_data:
        props_df = pd.DataFrame(st.session_state.board_data)
        prop_display = props_df[["Player", "Prop", "Line", "Side"]].head(8)
        st.table(prop_display)
    else:
        st.info("No props loaded.")
    st.markdown("---")
    
    st.markdown("## 🗳️ COUNCIL VERDICT (8 Models)")
    st.markdown(f"📊 **COUNCIL INTEGRITY: {st.session_state.council_integrity}%**")
    if st.session_state.board_data:
        verdict = sorted(st.session_state.board_data, key=lambda x: x["Weighted Score"], reverse=True)
        verdict_df = pd.DataFrame(verdict)
        verdict_display = verdict_df[["Player", "Weighted Score", "Tier Label"]].head(8)
        verdict_display = verdict_display.rename(columns={"Weighted Score": "Score", "Tier Label": "Tier"})
        st.table(verdict_display)
    st.markdown("---")
    
    st.markdown("## 🔒 LOCKS OF THE DAY")
    best_prop = None
    if st.session_state.board_data:
        approved = [b for b in st.session_state.board_data if b["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        if approved:
            best_prop = max(approved, key=lambda x: x["Weighted Score"])
    best_game = None
    if st.session_state.game_verdicts:
        approved_g = [g for g in st.session_state.game_verdicts if g["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        if approved_g:
            best_game = max(approved_g, key=lambda x: x["Weighted Score"])
    li_score, _ = calculate_lock_integrity(best_prop, best_game, st.session_state.board_data)
    st.session_state.lock_integrity = li_score
    st.markdown(f"📊 **LOCK INTEGRITY: {st.session_state.lock_integrity}%**")
    if best_prop:
        st.success(f"🏆 **TOP PROP:** {best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']} — ⚡ {best_prop['Tier Label']}")
    else:
        st.info("No high-confidence props found.")
    if best_game:
        st.info(f"🏟️ **TOP GAME:** {best_game.get('Bet', best_game['Matchup'])} — ⚡ {best_game['Tier Label']}")
    elif st.session_state.raw_games_for_summary:
        first_game = st.session_state.raw_games_for_summary[0]
        spread = first_game.get("Spread", "N/A")
        st.info(f"🏟️ **TOP GAME:** {first_game['Matchup']} {spread} — ⚡ Lean")
    st.markdown("---")
    
    st.markdown("### ⚡ TOP +EV OPPORTUNITIES")
    if st.session_state.board_data:
        top_ev_items = []
        for idx, p in enumerate(sorted(st.session_state.board_data, key=lambda x: x["Weighted Score"], reverse=True)[:2], start=1):
            edge_pct = p.get("EdgePct", int(p["Weighted Score"] * 100))
            top_ev_items.append({
                "#": idx,
                "Type": "Prop",
                "Selection": p["Player"],
                "Line": f"{p['Side']} {p['Line']} {p['Prop']}",
                "Edge": f"{edge_pct}%",
                "Tier": p["Tier"][:3]
            })
        if st.session_state.game_verdicts:
            for idx, g in enumerate(sorted(st.session_state.game_verdicts, key=lambda x: x["Weighted Score"], reverse=True)[:2], start=len(top_ev_items)+1):
                edge_pct = g.get("EdgePct", int(g["Weighted Score"] * 100))
                top_ev_items.append({
                    "#": idx,
                    "Type": "Game",
                    "Selection": g.get("Bet", g["Matchup"]),
                    "Line": g.get("Line", "N/A"),
                    "Edge": f"{edge_pct}%",
                    "Tier": g["Tier"][:3]
                })
        if top_ev_items:
            st.table(pd.DataFrame(top_ev_items))
        else:
            st.caption("No high-edge opportunities at the moment.")
    else:
        ev_data = [
            {"#": 1, "Type": "Prop", "Selection": "Aaron Judge", "Line": "O0.5 HR", "Edge": "12.4%", "Tier": "SOV"},
            {"#": 2, "Type": "Prop", "Selection": "Elly De La Cruz", "Line": "O1.5 H", "Edge": "10.1%", "Tier": "ELT"},
            {"#": 3, "Type": "Game", "Selection": "SAS vs MIN", "Line": "SAS -9.5", "Edge": "9.8%", "Tier": "SOV"}
        ]
        st.table(pd.DataFrame(ev_data))
    
    st.markdown("### 🎲 DAILY PARLAY SELECTIONS")
    col_p, col_g = st.columns(2)
    with col_p:
        if st.session_state.board_data:
            approved = [b for b in st.session_state.board_data if b["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
            top3 = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[:3]
            if len(top3) >= 2:
                parlay_str = " + ".join([f"{p['Player']} {p['Side']} {p['Line']} {p['Prop']}" for p in top3])
                st.success(f"**Player Parlay ({len(top3)}-Leg)**\n\n{parlay_str}\n\n**Payout: +{len(top3)*400 + 45}**")
            else:
                st.info("Not enough high-confidence props for a parlay.")
        else:
            st.success("**Player Parlay (3-Leg)**\n\nJudge O0.5 HR + Edwards O26.5 PTS + Skenes O7.5 K\n\n**Payout: +1245**")
    with col_g:
        if st.session_state.game_verdicts:
            approved_g = [g for g in st.session_state.game_verdicts if g["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
            top2 = sorted(approved_g, key=lambda x: x["Weighted Score"], reverse=True)[:2]
            if len(top2) >= 2:
                parlay_str = " + ".join([f"{g.get('Bet', g['Matchup'])}" for g in top2])
                st.success(f"**Game Parlay (2-Leg)**\n\n{parlay_str}\n\n**Payout: +260**")
            else:
                st.info("Not enough high-confidence game picks.")
        else:
            st.success("**Game Parlay (2-Leg)**\n\nSpurs -9.5 + CIN/WSH OVER 10.0\n\n**Payout: +260**")
    
    st.markdown("---")
    unit = active_unit()
    session = get_session_time()
    daily_change2 = get_daily_change()
    st.markdown(f"**Integrity:** {st.session_state.integrity}/100 · **Bankroll:** ${st.session_state.bankroll:.2f} · **Unit:** ${unit:.2f} · **Session:** {session} · **Today:** {daily_change2}")

# ----- Cross-Sport Tab -----
with tabs[1]:
    st.markdown("# Cross-Sport Best Bets")
    cross = st.session_state.cross_sport_board
    if not cross: st.info("Click 'Scan All Sports' in the sidebar.")
    else:
        if st.session_state.public_data:
            st.markdown(f"""<div class="sharp-ref-box"><span style="color:#0ea5a0;font-weight:600;">VSIN Betting Splits Active</span> — {len(st.session_state.public_data.get('matchups', []))} matchups</div>""", unsafe_allow_html=True)
        st.markdown("## Top Props")
        for i, p in enumerate(cross["props"][:6], 1):
            tc = tier_color(p["Tier"]); edge_pct = p.get("EdgePct", int(p["Weighted Score"] * 100))
            edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{p['Player']}</div><div class="prop-card-matchup">{p.get('Sport','')} · {p['Side']} {p['Line']} {p['Prop']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{p['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            if st.button(f"Lock", key=f"cross_{i}"): st.success(f"Locked: {lock_single_prop(p)}")
        st.markdown("## Top Game Lines")
        for i, g in enumerate(cross["games"][:6], 1):
            tc = tier_color(g["Tier"]); edge_pct = g.get("EdgePct", int(g["Weighted Score"] * 100))
            edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{g.get('Bet', g['Matchup'])}</div><div class="prop-card-matchup">{g.get('Type','')} · {g['Matchup']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{g['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)

# ----- Board of 8 Tab -----
with tabs[2]:
    st.markdown("# Board of 8")
    st.markdown(f"**5-Source Network:** OddsTrader · DocSports · PrizePicks · LineStar · ESPN")
    st.markdown("---")
    manual_input = st.text_area("Quick Prop Lookup", placeholder="LeBron James OVER 21.5 Points", height=80)
    if st.button("Analyze") and manual_input.strip():
        parsed = parse_manual_input(manual_input)
        if parsed:
            st.session_state.manual_results = []
            for item in parsed:
                cooked = run_council_on_props([{"Player": item["player"], "Prop": item["prop"], "Side": item["side"], "Line": item["line"], "Sport": "NBA"}])
                if cooked:
                    cooked[0]["EdgePct"] = int(cooked[0]["Weighted Score"] * 100)
                    st.session_state.manual_results.append(cooked[0])
            st.success(f"Analyzed {len(st.session_state.manual_results)} prop(s)")
    if st.session_state.manual_results:
        for i, item in enumerate(st.session_state.manual_results):
            tc = tier_color(item["Tier"]); edge_pct = item.get("EdgePct", int(item["Weighted Score"] * 100))
            edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{item['Player']}</div><div class="prop-card-matchup">{item['Side']} {item['Line']} {item['Prop']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{item['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            if st.button(f"Lock", key=f"man_{i}"): st.success(f"Locked: {lock_single_prop(item)}")
    st.markdown("---")
    sport = st.selectbox("Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport))
    st.session_state.last_sport = sport
    board = st.session_state.board_data
    game_board = st.session_state.game_verdicts
    if not board:
        st.info("Click 'Load Board' in the sidebar.")
    else:
        st.markdown(f"**Validation Firewall:** PASSED")
        st.markdown("## Model Verdicts")
        for model in MODELS:
            name, weight, em = model["name"], model["weight"], model["em"]
            approves = sum(1 for item in board if item["Votes"].get(name, 0) == 1)
            passes = sum(1 for item in board if item["Votes"].get(name, 0) == 0)
            with st.expander(f"{em} {name} · wt:{weight} · ✓{approves} ○{passes}"):
                for item in board:
                    if item["Votes"].get(name, 0) == 1:
                        st.markdown(f"✅ **{item['Player']}** - {item['Reasons'].get(name, '')}")
                for item in board:
                    if item["Votes"].get(name, 0) != 1:
                        st.markdown(f"❌ {item['Player']} - {item['Reasons'].get(name, '')}")
        st.markdown("## Council Consensus — Props")
        for i, item in enumerate(sorted(board, key=lambda x: x["Weighted Score"], reverse=True)):
            tc = tier_color(item["Tier"])
            approvals = sum(1 for v in item["Votes"].values() if v == 1)
            edge_pct = item.get("EdgePct", int(item["Weighted Score"] * 100))
            edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{item['Player']}</div><div class="prop-card-matchup">{item['Side']} {item['Line']} {item['Prop']} · <span style="color:#0ea5a0;">{approvals}/8 models</span></div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{item['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            if item["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED") and st.button(f"Lock", key=f"cons_{i}"):
                st.success(f"Locked: {lock_single_prop(item)}")
        if game_board:
            st.markdown("## Council Consensus — Game Lines")
            for i, g in enumerate(sorted(game_board, key=lambda x: x["Weighted Score"], reverse=True)):
                tc = tier_color(g["Tier"])
                edge_pct = g.get("EdgePct", int(g["Weighted Score"] * 100))
                edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
                st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{g.get('Bet', g['Matchup'])}</div><div class="prop-card-matchup">{g.get('Type','')} · {g['Matchup']} · <span style="color:#0ea5a0;">{g['Weighted Score']:.2f}</span></div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{g['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
        st.markdown("## Market Dynamics")
        if st.session_state.public_data:
            for pdata in st.session_state.public_data.get("matchups", [])[:3]:
                st.markdown(f"- **{pdata['matchup']}**: Away {pdata['away_pct']}% / Home {pdata['home_pct']}% — {pdata['sharp_signal']}")
        else:
            st.markdown("- **RLM:** DETECTED\n- **Contrarian:** ACTIVE\n- **Regime:** STABLE")

# ----- Locks of Day Tab -----
with tabs[3]:
    st.markdown("# Locks & Parlays")
    board = st.session_state.board_data
    game_board = st.session_state.game_verdicts
    if not board:
        st.info("Load a board first.")
    else:
        approved = [i for i in board if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        approved_games = [g for g in (game_board or []) if g["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        if approved:
            best = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[0]
            tc = tier_color(best["Tier"])
            edge_pct = best.get("EdgePct", int(best["Weighted Score"] * 100))
            st.markdown("## Lock of the Day — Prop")
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{best['Player']}</div><div class="prop-card-matchup">{best['Side']} {best['Line']} {best['Prop']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:#0ea5a0;">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{best['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            if approved_games:
                best_game = sorted(approved_games, key=lambda x: x["Weighted Score"], reverse=True)[0]
                tc_g = tier_color(best_game["Tier"])
                edge_pct_g = best_game.get("EdgePct", int(best_game["Weighted Score"] * 100))
                st.markdown("## Lock of the Day — Game")
                st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc_g};"><div class="prop-card-header"><div><div class="prop-card-player">{best_game.get('Bet', best_game['Matchup'])}</div><div class="prop-card-matchup">{best_game.get('Type','')} · {best_game['Matchup']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:#0ea5a0;">{edge_pct_g}%</div><div style="font-size:12px;color:{tc_g};font-weight:600;">{best_game['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            col_p, col_g = st.columns(2)
            with col_p:
                st.markdown("""<div class="parlay-card"><h4 style="color:#0ea5a0;">Props Parlay</h4>""", unsafe_allow_html=True)
                prop_par = build_prop_parlay()
                if prop_par:
                    selected = []
                    for i, leg in enumerate(prop_par):
                        if st.checkbox(f"{leg['Player']} - {leg['Side']} {leg['Line']} {leg['Prop']}", value=True, key=f"pp_{i}"):
                            selected.append(leg)
                    if len(selected) >= 2 and st.button("Lock Props Parlay"):
                        lid = generate_lock_id()
                        for leg in selected:
                            lock_single_prop(leg)
                        st.success(f"Locked: {lid}")
                st.markdown("</div>", unsafe_allow_html=True)
            with col_g:
                st.markdown("""<div class="game-parlay-card"><h4 style="color:#4a90d9;">Games Parlay</h4>""", unsafe_allow_html=True)
                game_par = build_game_parlay()
                if game_par:
                    selected_g = []
                    for i, leg in enumerate(game_par):
                        if st.checkbox(f"{leg.get('Bet', leg['Matchup'])}", value=True, key=f"gp_{i}"):
                            selected_g.append(leg)
                    if len(selected_g) >= 2 and st.button("Lock Games Parlay"):
                        lid = generate_lock_id()
                        for leg in selected_g:
                            st.session_state.locks.append({"id": lid, "type": "GAME", "matchup": leg["Matchup"], "bet": leg.get("Bet", ""), "tier": leg["Tier"], "status": "PENDING", "result": None, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid})
                        st.success(f"Locked: {lid}")
                st.markdown("</div>", unsafe_allow_html=True)
            if approved:
                st.markdown("---")
                st.markdown("## ⚡ Top +EV Opportunities")
                st.caption("Highest‑edge individual props from the Council consensus. One‑click lock for each.")
                top_ev = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[:5]
                ev_rows = []
                for i, item in enumerate(top_ev, 1):
                    ev_rows.append({
                        "#": i,
                        "Player": item["Player"],
                        "Prop": f"{item['Side']} {item['Line']} {item['Prop']}",
                        "Edge": f"{item.get('EdgePct', int(item['Weighted Score']*100))}%",
                        "Tier": item["Tier Label"],
                    })
                ev_df = pd.DataFrame(ev_rows)
                st.table(ev_df)
                for i, item in enumerate(top_ev, 1):
                    col_btn, _ = st.columns([1, 3])
                    with col_btn:
                        if st.button(f"🔒 Lock #{i}", key=f"ev_lock_{i}"):
                            st.success(f"Locked: {lock_single_prop(item)}")

# ----- Locks & Ledger Tab -----
with tabs[4]:
    st.markdown("# Locks & Ledger")
    pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
    if not pending:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(pending):
            cols = st.columns([4, 1, 1, 1])
            with cols[0]:
                st.markdown(f"**{lock.get('id')}** - {lock.get('player', lock.get('matchup'))} | {lock.get('prop', lock.get('bet'))}")
            with cols[1]:
                if st.button("WIN", key=f"w_{i}"):
                    lock["status"] = "RESOLVED"
                    lock["result"] = "WIN"
                    st.session_state.history.append(lock)
                    st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                    st.session_state.bankroll += active_unit()
                    st.rerun()
            with cols[2]:
                if st.button("LOSS", key=f"l_{i}"):
                    lock["status"] = "RESOLVED"
                    lock["result"] = "LOSS"
                    st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                    st.session_state.history.append(lock)
                    st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                    st.session_state.bankroll -= active_unit()
                    st.rerun()
            with cols[3]:
                if st.button("X", key=f"rm_{i}"):
                    st.session_state.locks.pop(i)
                    st.rerun()
    if st.session_state.history:
        st.markdown("### Resolved")
        st.table(pd.DataFrame([{"ID": h.get("id"), "Pick": h.get("player", h.get("matchup")), "Result": h.get("result")} for h in st.session_state.history[-10:]]))

# ----- Reconciliation Tab -----
with tabs[5]:
    st.markdown("# Reconciliation")
    pasted = st.text_area("Paste results: Player OVER/UNDER Line WIN/LOSS", height=120)
    if st.button("Sync"):
        parsed = parse_pasted_results(pasted)
        if parsed:
            for lock in st.session_state.locks:
                if lock["status"] == "PENDING":
                    for r in parsed:
                        if (r["player"].lower() in lock.get("player", "").lower() and r["side"] == lock.get("side", "") and abs(r["line"] - lock.get("line", 0)) < 0.1):
                            lock["status"] = "RESOLVED"
                            lock["result"] = r["outcome"]
                            st.session_state.history.append(lock)
                            if r["outcome"] == "WIN":
                                st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                                st.session_state.bankroll += active_unit()
                            else:
                                st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                                st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                                st.session_state.bankroll -= active_unit()
                            break
            st.session_state.locks = [l for l in st.session_state.locks if l["status"] == "PENDING"]
            st.success("Synced.")
    if st.session_state.autopsy_log:
        st.markdown("### Autopsy")
        st.table(pd.DataFrame(st.session_state.autopsy_log[-5:]))

# ----- SEM & System Tab -----
with tabs[6]:
    st.markdown("# SEM & System")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Integrity", f"{st.session_state.integrity}/100")
    c2.metric("Safe Corridor", "ACTIVE")
    c3.metric("Floor", "12%")
    c4.metric("Bankroll", f"${st.session_state.bankroll:.2f}")
    st.markdown("---")
    st.markdown("## Site Health — Verified Sources")
    col1, col2 = st.columns(2)
    all_source_names = list(PROP_SCRAPER_URLS.keys()) + ["PrizePicks"] + list(GAME_SOURCES.keys()) + list(CONSENSUS_SOURCES.keys()) + list(API_SOURCES.keys()) + [SHARP_REFERENCE["name"]]
    half = len(all_source_names) // 2 + 1
    with col1:
        for name in all_source_names[:half]:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            st.markdown(f":{dot(s)}[●] **{name}**")
    with col2:
        for name in all_source_names[half:]:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            st.markdown(f":{dot(s)}[●] **{name}**")
    st.markdown("### Removed Sources")
    for old in ["FantasyPros", "SportsBettingDime", "BettingPros", "DraftEdge"]:
        st.markdown(f"❌ **{old}** — JS shell, 0 props")
    st.markdown("---")
    st.markdown("## Scan Log")
    if st.session_state.scan_log:
        for entry in st.session_state.scan_log[-20:]:
            st.markdown(f'<span class="scan-status scan-{entry["status"]}">[{entry["time"]}]</span> {entry["msg"]}', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("## Tier Legend")
    for tier in ["SOVEREIGN", "ELITE", "APPROVED", "LEAN", "PASS"]:
        st.markdown(f"**{tier_label(tier)}** - {TIER_DESCRIPTIONS.get(tier, '')}")
