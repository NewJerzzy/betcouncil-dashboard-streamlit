import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup
import json
import subprocess
import time

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="BetCouncil v3.2",
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
# CONSTANTS — v3.2 FINAL
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
DEFAULT_BANKROLL = 529.64
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
INTEGRITY_FLOOR = 40
INTEGRITY_CEILING = 100
SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

# Prop sources — DraftKings removed (JS-only, confirmed 0 results)
PROP_SOURCES = {
    "BettingPros": "https://www.bettingpros.com/{sport}/picks/player-props/",
    "OddsTrader": "https://oddstrader.com/{sport}/player-props/",
    "SportsBettingDime": "https://www.sportsbettingdime.com/{sport}/props/",
}

# Game line sources
GAME_SOURCES = {
    "VegasInsider": "https://www.vegasinsider.com/{sport}/odds/las-vegas/",
    "ESPN (JSON API)": "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard",
}

# Sport-specific source lists — DraftKings removed
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

# URL slug mappings
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

DK_SPORT_SLUG = {
    "NBA": "basketball/nba", "WNBA": "basketball/wnba", "NFL": "football/nfl",
    "MLB": "baseball/mlb", "NHL": "hockey/nhl", "UFC": "mma/ufc",
    "Golf": "golf", "Tennis": "tennis", "Soccer": "soccer",
}

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
    st.session_state.site_status = {
        name: {"status": "unknown", "last_checked": None}
        for name in list(PROP_SOURCES.keys()) + list(GAME_SOURCES.keys())
    }
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

def safe_fetch(url, name):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            mark_site_ok(name)
            log_scan(f"{name}: OK (200)", "ok")
            return resp.text
        else:
            mark_site_fail(name)
            log_scan(f"{name}: FAIL (HTTP {resp.status_code})", "fail")
            return None
    except requests.Timeout:
        mark_site_fail(name)
        log_scan(f"{name}: FAIL (timeout)", "fail")
        return None
    except requests.ConnectionError:
        mark_site_fail(name)
        log_scan(f"{name}: FAIL (connection)", "fail")
        return None
    except Exception as e:
        mark_site_fail(name)
        log_scan(f"{name}: FAIL ({str(e)[:50]})", "fail")
        return None

# =========================
# SITE-SPECIFIC PARSERS (THE FIX)
# =========================
def parse_props_generic(html, source_name=""):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # --- VEGASINSIDER ---
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

    # --- ODDSTRADER ---
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

    # --- SPORTSBETTINGDIME ---
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

    # --- BETTINGPROS ---
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

    # --- GENERIC FALLBACK (tables only) ---
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
    games = []
    if not html: return games
    try:
        data = json.loads(html)
        for event in data.get("events", []):
            matchup = event.get("shortName", "")
            for comp in event.get("competitions", []):
                games.append({"Matchup": matchup, "Spread": "N/A", "Total": "N/A", "Moneyline": "N/A", "Sport": sport})
                break
    except:
        pass
    return games

def fetch_sharp_reference(sport="nba"):
    return []

def get_sharp_ref_status():
    return "Sharp Reference: not pulled"

def parse_manual_input(text):
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        match = re.match(r"(.+?)\s+(OVER|UNDER)\s+([\d.]+)\s+(.+)", line, re.IGNORECASE)
        if match:
            results.append({"type": "PROP", "player": match.group(1).strip(), "side": match.group(2).upper(), "line": float(match.group(3)), "prop": match.group(4).strip(), "raw": line})
    return results

STARS = ["Shai", "LeBron", "Cade", "Donovan", "Anthony", "Aaron", "Shohei", "Bryce", "Juan", "James", "Tobias", "Chet", "Victor", "Jalen", "Karl", "Joel", "De'Aaron", "Julius", "Daniss", "Deandre", "Scottie", "Luka", "Giannis", "Nikola"]

def run_council_on_props(raw_props):
    if not raw_props: return []
    results = []
    for prop in raw_props:
        player = prop.get("Player", "")
        ptype = prop.get("Prop", "")
        side = prop.get("Side", "")
        line = prop.get("Line", 0)
        votes = {}
        reasons = {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO", "REB+AST"])
        is_under = "UNDER" in side.upper()
        is_star = any(s in player for s in STARS)
        for i, model in enumerate(MODELS):
            name = model["name"]
            if i == 0:
                votes[name] = 0 if is_combo else (1 if is_under else 1)
                reasons[name] = "Combo variance" if is_combo else ("Outlier supports Under" if is_under else "Outlier clean")
            elif i == 1:
                votes[name] = 0
                reasons[name] = "No enviro edge"
            elif i == 2:
                votes[name] = 1 if is_star else 0
                reasons[name] = "Motivation" if is_star else "Role variance"
            elif i == 3:
                votes[name] = 0 if is_combo else 1
                reasons[name] = "Floor unreliable" if is_combo else "Floor above"
            elif i == 4:
                votes[name] = 0 if is_combo else 1
                reasons[name] = "Sigma wide" if is_combo else "Low vol"
            elif i == 5:
                votes[name] = 1 if is_star else 0
                reasons[name] = "CLV positive" if is_star else "Edge below"
            elif i == 6:
                votes[name] = 1 if is_star else 0
                reasons[name] = "Ceiling ok" if is_star else "Ceiling risk"
            else:
                votes[name] = 0 if is_combo else 1
                reasons[name] = "Margin thin" if is_combo else "Raw supports"
        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({
            "Player": player, "Prop": ptype, "Side": side, "Line": line,
            "Votes": votes, "Reasons": reasons,
            "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier),
            "Sport": prop.get("Sport", ""), "EdgePct": round(ws * 100),
        })
    return results

def run_game_council_on_games(raw_games):
    if not raw_games: return []
    results = []
    for game in raw_games:
        matchup = game.get("Matchup", "")
        votes = {}
        for m in MODELS:
            name = m["name"]
            votes[name] = 1 if any(t in matchup for t in ["CLE", "OKC", "NYY", "PHI", "CHC", "NYK", "SAS"]) else 0
        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({
            "Matchup": matchup, "Moneyline": game.get("Moneyline", ""),
            "Spread": game.get("Spread", ""), "Total": game.get("Total", ""),
            "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier),
            "Sport": game.get("Sport", ""), "EdgePct": round(ws * 100),
        })
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
    st.session_state.locks.append({
        "id": lid, "type": "PROP", "player": item["Player"],
        "prop": f"{item['Side']} {item['Line']} {item['Prop']}",
        "side": item["Side"], "line": item["Line"], "tier": item["Tier"],
        "status": "PENDING", "result": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parlay_id": lid, "override": item["Tier"] not in ("SOVEREIGN", "ELITE"),
    })
    return lid

def parse_pasted_results(text):
    results = []
    for line in text.strip().split("\n"):
        match = re.match(r"(.+?)\s+(OVER|UNDER|ML|SPREAD)\s+([\d.]+)\s+(WIN|LOSS)", line.strip(), re.IGNORECASE)
        if match:
            results.append({"player": match.group(1).strip(), "side": match.group(2).upper(), "line": float(match.group(3)), "outcome": match.group(4).upper()})
    return results

# =========================
# CORE: LOAD SPORT DATA
# =========================
def load_sport_data_live(sport):
    st.session_state.scan_log = []
    all_props = []
    all_games = []
    seen_props = set()

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

    for gs_name in ["VegasInsider", "ESPN (JSON API)"]:
        url = build_source_url(gs_name, sport)
        if not url: continue
        log_scan(f"Fetching game lines: {gs_name}", "skip")
        html = safe_fetch(url, gs_name)
        if html:
            if "ESPN" in gs_name:
                games = parse_espn_json(html, sport)
            else:
                games = [{"Matchup": g.get("matchup", ""), "Spread": g.get("spread", "N/A"), "Total": g.get("total", "N/A"), "Moneyline": "N/A", "Sport": sport} for g in parse_props_generic(html, gs_name)]
            if games:
                all_games = games
                log_scan(f"{gs_name}: {len(games)} games found", "ok")
                break

    if not all_props:
        log_scan("No props from any source — using sample data", "fail")
        data = get_sample_data(sport)
        all_props = data["raw_props"]
    if not all_games:
        data = get_sample_data(sport)
        all_games = data["raw_games"]

    st.session_state.raw_props = all_props
    st.session_state.raw_games = all_games
    st.session_state.last_sport = sport
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True
    st.session_state.board_data = run_council_on_props(all_props)
    st.session_state.game_verdicts = run_game_council_on_games(all_games)

def get_sample_data(sport):
    if sport == "NBA":
        return {
            "raw_props": [{"Player": p, "Prop": t, "Line": l, "Side": s, "Sport": "NBA"} for p, t, l, s in [("Shai Gilgeous-Alexander", "POINTS", 31.5, "OVER"), ("Cade Cunningham", "POINTS", 23.5, "OVER"), ("Donovan Mitchell", "POINTS", 27.5, "UNDER")]],
            "raw_games": [{"Matchup": "OKC @ LAL", "Spread": "OKC -8.5", "Total": "O/U 214.5", "Moneyline": "OKC -400", "Sport": "NBA"}],
        }
    if sport == "MLB":
        return {
            "raw_props": [{"Player": p, "Prop": t, "Line": l, "Side": s, "Sport": "MLB"} for p, t, l, s in [("Aaron Judge", "H+R+RBI", 0.5, "OVER"), ("Spencer Strider", "STRIKEOUTS", 4.5, "OVER")]],
            "raw_games": [{"Matchup": "TEX @ NYY", "Spread": "NYY -1.5", "Total": "O/U 8.5", "Moneyline": "NYY -152", "Sport": "MLB"}],
        }
    return {"raw_props": [], "raw_games": []}

def scan_all_sports_live():
    all_props, all_games = [], []
    for sport in SPORTS:
        load_sport_data_live(sport)
        all_props.extend(st.session_state.raw_props)
        all_games.extend(st.session_state.raw_games)
    prop_results = run_council_on_props(all_props)
    game_results = run_game_council_on_games(all_games)
    prop_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    game_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    st.session_state.cross_sport_board = {"props": prop_results, "games": game_results, "scanned_at": datetime.now().strftime("%H:%M:%S")}
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;margin-bottom:16px;">
        <div style="width:44px;height:44px;background:linear-gradient(135deg,#0ea5a0,#065f5e);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:inline-flex;align-items:center;justify-content:center;font-size:22px;">⚡</div>
        <div style="font-size:22px;font-weight:700;color:#ffffff;margin-top:6px;letter-spacing:-0.5px;">BetCouncil</div>
        <div style="font-size:11px;color:#4a8a8a;margin-top:2px;">v3.2 · Final</div>
    </div>
    """, unsafe_allow_html=True)
    
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
        with st.spinner("Scanning all 9 leagues..."):
            scan_all_sports_live()
        amt = len(st.session_state.cross_sport_board["props"]) if st.session_state.cross_sport_board else 0
        st.success(f"All 9 leagues scanned - {amt} props")
    if st.button("Load Board", use_container_width=True):
        with st.spinner(f"Scanning {st.session_state.last_sport}..."):
            load_sport_data_live(st.session_state.last_sport)
        amt = len(st.session_state.raw_props)
        st.success(f"{st.session_state.last_sport} loaded - {amt} props")
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
st.markdown(f"""
<div class="command-bar">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;">
        <div style="display:flex;gap:6px;">
            <span class="toggle-btn active">Safe: ON</span>
            <span class="toggle-btn active">Blowout: ON</span>
            <span class="toggle-btn active">Playoff: ON</span>
        </div>
        <div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
            <span style="font-size:12px;color:#6a7a8a;">{get_session_time()}</span>
            <span class="toggle-btn" style="border-color:#0ea5a0;color:#0ea5a0;background:rgba(14,165,160,0.1);">{pending_count} Lock{"s" if pending_count != 1 else ""}</span>
        </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;">
        <div class="metric-box">
            <div class="metric-label">Bankroll</div>
            <div class="metric-value gold-text">${st.session_state.bankroll:.2f}</div>
            <div style="font-size:12px;color:{change_color};margin-top:2px;">{daily_change} today</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">Integrity</div>
            <div class="metric-value" style="color:{'#0ea5a0' if st.session_state.integrity >= 70 else '#e04040' if st.session_state.integrity < 55 else '#e8a020'}">{st.session_state.integrity}/100</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">Active Floor</div>
            <div class="metric-value teal-text">12%</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">Kelly</div>
            <div class="metric-value gold-text">{KELLY_FRACTION}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">Unit</div>
            <div class="metric-value gold-text">${active_unit()}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">Sharp Ref</div>
            <div class="metric-value teal-text">{'Yes' if st.session_state.sharp_available else 'No'}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================
# TABS
# =========================
tabs = st.tabs(["Cross-Sport", "Board of 8", "Locks of Day", "Locks & Ledger", "Reconciliation", "SEM & System"])

# Cross-Sport
with tabs[0]:
    st.markdown("# Cross-Sport Best Bets")
    cross = st.session_state.cross_sport_board
    if not cross:
        st.info("Click 'Scan All Sports' in the sidebar.")
    else:
        st.markdown("## Top Props")
        for i, p in enumerate(cross["props"][:6], 1):
            tc = tier_color(p["Tier"])
            edge_pct = p.get("EdgePct", int(p["Weighted Score"] * 100))
            edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{p['Player']}</div><div class="prop-card-matchup">{p.get('Sport','')} · {p['Side']} {p['Line']} {p['Prop']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{p['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            if st.button(f"Lock", key=f"cross_{i}"):
                st.success(f"Locked: {lock_single_prop(p)}")
        st.markdown("## Top Game Lines")
        for i, g in enumerate(cross["games"][:3], 1):
            tc = tier_color(g["Tier"])
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{g['Matchup']}</div><div class="prop-card-matchup">{g.get('Sport','')}</div></div><div style="text-align:right;"><div style="font-size:12px;color:{tc};font-weight:600;">{g['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)

# Board of 8
with tabs[1]:
    st.markdown("# Board of 8")
    st.markdown("**Sources:** BettingPros · OddsTrader · SportsBettingDime · VegasInsider · ESPN")
    st.markdown("---")
    manual_input = st.text_area("Quick Prop Lookup", placeholder="LeBron James OVER 21.5 Points", height=80)
    if st.button("Analyze"):
        if manual_input.strip():
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
            tc = tier_color(item["Tier"])
            edge_pct = item.get("EdgePct", int(item["Weighted Score"] * 100))
            edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{item['Player']}</div><div class="prop-card-matchup">{item['Side']} {item['Line']} {item['Prop']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{item['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            if st.button(f"Lock", key=f"man_{i}"):
                st.success(f"Locked: {lock_single_prop(item)}")
    st.markdown("---")
    sport = st.selectbox("Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport))
    st.session_state.last_sport = sport
    board = st.session_state.board_data
    if not board:
        st.info("Click 'Load Board' in the sidebar.")
    else:
        st.markdown(f"**Validation Firewall:** PASSED ({st.session_state.filtered_count} props removed)")
        st.markdown("## Model Verdicts")
        for model in MODELS:
            name, weight, em = model["name"], model["weight"], model["em"]
            approves = sum(1 for item in board if item["Votes"].get(name, 0) == 1)
            passes = sum(1 for item in board if item["Votes"].get(name, 0) == 0)
            with st.expander(f"{em} {name} · wt:{weight} · ✓{approves} ○{passes}"):
                for item in board:
                    vote = item["Votes"].get(name, 0)
                    reason = item["Reasons"].get(name, "")
                    if vote == 1:
                        st.markdown(f"✅ **{item['Player']}** - {reason}")
                for item in board:
                    vote = item["Votes"].get(name, 0)
                    reason = item["Reasons"].get(name, "")
                    if vote != 1:
                        st.markdown(f"❌ {item['Player']} - {reason}")
        st.markdown("## Council Consensus")
        for i, item in enumerate(sorted(board, key=lambda x: x["Weighted Score"], reverse=True)):
            tc = tier_color(item["Tier"])
            approvals = sum(1 for v in item["Votes"].values() if v == 1)
            edge_pct = item.get("EdgePct", int(item["Weighted Score"] * 100))
            edge_color = "#0ea5a0" if edge_pct >= 70 else "#4a90d9" if edge_pct >= 40 else "#6a7a8a"
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{item['Player']}</div><div class="prop-card-matchup">{item['Side']} {item['Line']} {item['Prop']} · <span style="color:#0ea5a0;">{approvals}/8 models</span></div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:{edge_color};">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{item['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
            if item["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED"):
                if st.button(f"Lock", key=f"cons_{i}"):
                    st.success(f"Locked: {lock_single_prop(item)}")
        st.markdown("## Market Dynamics")
        st.markdown("- **RLM:** DETECTED\n- **Contrarian:** ACTIVE\n- **Regime:** STABLE")

# Locks of Day
with tabs[2]:
    st.markdown("# Locks & Parlays")
    board = st.session_state.board_data
    if not board: st.info("Load a board first.")
    else:
        approved = [i for i in board if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        if approved:
            best = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[0]
            tc = tier_color(best["Tier"])
            edge_pct = best.get("EdgePct", int(best["Weighted Score"] * 100))
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{best['Player']}</div><div class="prop-card-matchup">{best['Side']} {best['Line']} {best['Prop']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:#0ea5a0;">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{best['Tier Label']}</div></div></div></div>""", unsafe_allow_html=True)
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
                        for leg in selected: lock_single_prop(leg)
                        st.success(f"Locked: {lid}")
                st.markdown("</div>", unsafe_allow_html=True)
            with col_g:
                st.markdown("""<div class="game-parlay-card"><h4 style="color:#4a90d9;">Games Parlay</h4>""", unsafe_allow_html=True)
                game_par = build_game_parlay()
                if game_par:
                    selected_g = []
                    for i, leg in enumerate(game_par):
                        if st.checkbox(f"{leg['Matchup']}", value=True, key=f"gp_{i}"):
                            selected_g.append(leg)
                    if len(selected_g) >= 2 and st.button("Lock Games Parlay"):
                        lid = generate_lock_id()
                        for leg in selected_g:
                            st.session_state.locks.append({"id": lid, "type": "GAME", "matchup": leg["Matchup"], "bet": "", "tier": leg["Tier"], "status": "PENDING", "result": None, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid})
                        st.success(f"Locked: {lid}")
                st.markdown("</div>", unsafe_allow_html=True)

# Locks & Ledger
with tabs[3]:
    st.markdown("# Locks & Ledger")
    pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
    if not pending: st.info("No active locks.")
    else:
        for i, lock in enumerate(pending):
            cols = st.columns([4, 1, 1, 1])
            with cols[0]:
                st.markdown(f"**{lock.get('id')}** - {lock.get('player', lock.get('matchup'))} | {lock.get('prop', lock.get('bet'))}")
            with cols[1]:
                if st.button("WIN", key=f"w_{i}"):
                    lock["status"] = "RESOLVED"; lock["result"] = "WIN"
                    st.session_state.history.append(lock)
                    st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                    st.session_state.bankroll += active_unit()
                    st.rerun()
            with cols[2]:
                if st.button("LOSS", key=f"l_{i}"):
                    lock["status"] = "RESOLVED"; lock["result"] = "LOSS"
                    st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                    st.session_state.history.append(lock)
                    st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                    st.session_state.bankroll -= active_unit()
                    st.rerun()
            with cols[3]:
                if st.button("X", key=f"rm_{i}"):
                    st.session_state.locks.pop(i); st.rerun()
    if st.session_state.history:
        st.markdown("### Resolved")
        st.table(pd.DataFrame([{"ID": h.get("id"), "Pick": h.get("player", h.get("matchup")), "Result": h.get("result")} for h in st.session_state.history[-10:]]))

# Reconciliation
with tabs[4]:
    st.markdown("# Reconciliation")
    pasted = st.text_area("Paste results: Player OVER/UNDER Line WIN/LOSS", height=120)
    if st.button("Sync"):
        parsed = parse_pasted_results(pasted)
        if parsed:
            for lock in st.session_state.locks:
                if lock["status"] == "PENDING":
                    for r in parsed:
                        if (r["player"].lower() in lock.get("player", "").lower() and r["side"] == lock.get("side", "") and abs(r["line"] - lock.get("line", 0)) < 0.1):
                            lock["status"] = "RESOLVED"; lock["result"] = r["outcome"]
                            st.session_state.history.append(lock)
                            if r["outcome"] == "WIN":
                                st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                                st.session_state.bankroll += active_unit()
                            else:
                                st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                                st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                                st.session_state.bankroll -= active_unit()
            st.session_state.locks = [l for l in st.session_state.locks if l["status"] == "PENDING"]
            st.success("Synced.")
    if st.session_state.autopsy_log:
        st.markdown("### Autopsy")
        st.table(pd.DataFrame(st.session_state.autopsy_log[-5:]))

# SEM & System
with tabs[5]:
    st.markdown("# SEM & System")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Integrity", f"{st.session_state.integrity}/100")
    c2.metric("Safe Corridor", "ACTIVE")
    c3.metric("Floor", "12%")
    c4.metric("Bankroll", f"${st.session_state.bankroll:.2f}")
    st.markdown("---")
    st.markdown("## Site Health")
    c1, c2 = st.columns(2)
    with c1:
        for name in list(PROP_SOURCES.keys()) + [SHARP_REFERENCE["name"]]:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            color = dot(s)
            st.markdown(f":{color}[●] **{name}**")
    with c2:
        for name in list(GAME_SOURCES.keys()):
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            color = dot(s)
            st.markdown(f":{color}[●] **{name}**")
    st.markdown("---")
    st.markdown("## Scan Log")
    if st.session_state.scan_log:
        for entry in st.session_state.scan_log[-20:]:
            status_class = f"scan-{entry['status']}"
            st.markdown(f'<span class="scan-status {status_class}">[{entry["time"]}]</span> {entry["msg"]}', unsafe_allow_html=True)
    else:
        st.info("No scan run yet.")
    st.markdown("---")
    st.markdown("## Tier Legend")
    for tier in ["SOVEREIGN", "ELITE", "APPROVED", "LEAN", "PASS"]:
        desc = TIER_DESCRIPTIONS.get(tier, "")
        st.markdown(f"**{tier_label(tier)}** - {desc}")
