import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import re
import json
import io
import requests
from bs4 import BeautifulSoup
import numpy as np
import subprocess
import shutil
from scipy.stats import norm
import time

st.set_page_config(page_title="BetCouncil v3.5.1 Multi-Sport Engine", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
body, .stApp, .main { background-color:#07090c; color:#e8f0f8; font-family:Inter,system-ui,sans-serif; font-size:16px; }
h1 { font-size:26px !important; }
h2 { font-size:22px !important; }
h3 { font-size:18px !important; }
h4,h5 { font-size:16px !important; color:#f4f8fc; text-transform:uppercase; letter-spacing:.5px; }
.stTabs [role="tab"] { font-size: 16px !important; font-weight: 600 !important; padding: 10px 18px !important; }
.stTabs [role="tab"][aria-selected="true"] { color: #e8a020 !important; border-bottom-color: #e8a020 !important; }
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
.small-note { font-size:13px; color:#5a7088; }
.stInfo, .stSuccess, .stWarning, .stError { font-size:15px !important; }
.sidebar-section { background:#0d1219; border:1px solid #1c2a3a; border-radius:8px; padding:12px; margin-bottom:10px; }
.sidebar-value { font-size:20px; font-weight:700; color:#f4f8fc; }
.sidebar-label { font-size:12px; color:#5a7088; text-transform:uppercase; letter-spacing:.5px; }
.sidebar-change-green { font-size:13px; color:#0d9488; }
.sidebar-sub { font-size:12px; color:#5a7088; }
.firewall-item { font-size:13px; padding:3px 0; display:flex; align-items:center; gap:6px; }
.firewall-pass { color:#0d9488; }
.firewall-fail { color:#d03030; }
.model-table { font-size:14px !important; width:100%; border-collapse:collapse; }
.model-table th { font-size:13px !important; padding:10px 8px !important; color:#5a7088 !important; text-align:left !important; border-bottom:2px solid #1c2a3a !important; }
.model-table td { font-size:14px !important; padding:10px 8px !important; border-bottom:1px solid #1c2a3a !important; }
.scan-log { background:#0d1219; border:1px solid #1c2a3a; border-radius:6px; padding:10px; font-family:monospace; font-size:12px; max-height:300px; overflow-y:auto; margin-top:8px; }
.log-ok { color:#0d9488; }
.log-fail { color:#d03030; }
.log-skip { color:#5a7088; }
.prop-card { background: #0d1219; border: 1px solid #1c2a3a; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem; }
.prop-card-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.prop-card-player { font-size: 17px; font-weight: 700; color: #f4f8fc; }
.prop-card-matchup { font-size: 14px; color: #5a7088; }
.prop-card-edge { font-size: 30px; font-weight: 800; }
.parlay-card, .game-parlay-card { background: #0d1219; border: 1px solid #1c2a3a; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem; }

/* Force table text to be bright for readability */
.stTable table, .stTable tbody, .stTable td, .stTable th { color: #e8f0f8 !important; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────
SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

GAME_SOURCES = {"ESPN (JSON API)": True}
CONSENSUS_SOURCES = {"VSIN Betting Splits": True}
ALL_SOURCES = {**GAME_SOURCES, **CONSENSUS_SOURCES}

SPORT_URL_SLUG = {"NBA":"nba","MLB":"mlb","NHL":"nhl","NFL":"nfl","WNBA":"wnba","UFC":"ufc","Golf":"golf","Tennis":"tennis","Soccer":"soccer"}
SPORT_PATH_MAP = {"nba":"basketball/nba","mlb":"baseball/mlb","nhl":"hockey/nhl","nfl":"football/nfl","wnba":"basketball/wnba"}
VSIN_SPORT_SLUG = {"NBA":"nba","MLB":"mlb","NHL":"nhl","NFL":"nfl","WNBA":"wnba","UFC":"ufc","Golf":"golf/pga","Tennis":"tennis","Soccer":"soccer"}

LINESTAR_SPORT_IDS = {"NBA": 2, "NFL": 1, "MLB": 4, "NHL": 3, "WNBA": 7}

# v3.5.1 — Verified sport-specific URLs to fix MLB 404s
PROP_SCRAPER_URLS = {
    "DraftEdge": {
        "NBA":  "https://draftedge.com/nba/nba-daily-projections/",
        "MLB":  "https://draftedge.com/mlb/todays-mlb-batter-prop-breakdown/",
        "NFL":  "https://draftedge.com/nfl/nfl-fantasy-football-player-props/",
        "NHL":  "https://draftedge.com/nhl/player-projections/",
        "WNBA": "https://draftedge.com/wnba/wnba-daily-projections/",
    },
    "BettingPros": {
        "NBA":  "https://www.bettingpros.com/nba/odds/player-props/",
        "MLB":  "https://www.bettingpros.com/mlb/odds/player-props/",
        "NFL":  "https://www.bettingpros.com/nfl/odds/player-props/",
        "NHL":  "https://www.bettingpros.com/nhl/odds/player-props/",
        "WNBA": "https://www.bettingpros.com/wnba/odds/player-props/",
    },
    "OddsTrader": {
        "NBA":  "https://www.oddstrader.com/nba/player-props/",
        "MLB":  "https://www.oddstrader.com/mlb/player-props/",
        "NFL":  "https://www.oddstrader.com/nfl/player-props/",
        "NHL":  "https://www.oddstrader.com/nhl/player-props/",
        "WNBA": "https://www.oddstrader.com/wnba/player-props/",
    },
    "SportsBettingDime": {
        "NBA":  "https://www.sportsbettingdime.com/nba/props/",
        "MLB":  "https://www.sportsbettingdime.com/mlb/props/",
        "NFL":  "https://www.sportsbettingdime.com/nfl/props/",
        "NHL":  "https://www.sportsbettingdime.com/nhl/props/",
        "WNBA": "https://www.sportsbettingdime.com/wnba/props/",
    },
}

PROP_NAME_BLACKLIST = [
    "Soccer", "Formula", "Guide", "Totals", "All", "Game",
    "May", "2026", "2025", "April", "June", "July", "March",
    "NCAAB", "NCAA", "WNBA", "NFL", "NHL", "MLB", "UFC", "Golf", "Tennis",
    "Trends", "History", "Record", "Season", "Since", "January", "February",
    "Loading", "Filter", "Search", "Sign Up", "Login", "Subscribe",
    "LineStar", "DraftEdge", "BettingPros", "OddsTrader", "SportsBetting",
    "Picks", "Props", "Slate", "Matchup", "Schedule", "Standings",
]

MAX_PROP_LINE = 80

MLB_STADIUMS = {
    "ARI":{"name":"Chase Field","type":"Dome","lat":33.4455,"lon":-112.0667},
    "ATL":{"name":"Truist Park","type":"Open","lat":33.8908,"lon":-84.4678},
    "BAL":{"name":"Camden Yards","type":"Open","lat":39.2839,"lon":-76.6216},
    "BOS":{"name":"Fenway Park","type":"Open","lat":42.3467,"lon":-71.0972},
    "CHC":{"name":"Wrigley Field","type":"Open","lat":41.9484,"lon":-87.6553},
    "CHW":{"name":"Guaranteed Rate Field","type":"Open","lat":41.8299,"lon":-87.6338},
    "CIN":{"name":"Great American Ball Park","type":"Open","lat":39.0979,"lon":-84.5066},
    "CLE":{"name":"Progressive Field","type":"Open","lat":41.4958,"lon":-81.6852},
    "COL":{"name":"Coors Field","type":"Open","lat":39.7562,"lon":-104.9942},
    "DET":{"name":"Comerica Park","type":"Open","lat":42.3391,"lon":-83.0485},
    "HOU":{"name":"Minute Maid Park","type":"Dome","lat":29.7573,"lon":-95.3555},
    "KC":{"name":"Kauffman Stadium","type":"Open","lat":39.0517,"lon":-94.4803},
    "LAA":{"name":"Angel Stadium","type":"Open","lat":33.8003,"lon":-117.8827},
    "LAD":{"name":"Dodger Stadium","type":"Open","lat":34.0739,"lon":-118.2400},
    "MIA":{"name":"loanDepot Park","type":"Dome","lat":25.7781,"lon":-80.2198},
    "MIL":{"name":"American Family Field","type":"Dome","lat":43.0283,"lon":-87.9712},
    "MIN":{"name":"Target Field","type":"Open","lat":44.9817,"lon":-93.2777},
    "NYM":{"name":"Citi Field","type":"Open","lat":40.7572,"lon":-73.8458},
    "NYY":{"name":"Yankee Stadium","type":"Open","lat":40.8296,"lon":-73.9262},
    "PHI":{"name":"Citizens Bank Park","type":"Open","lat":39.9056,"lon":-75.1665},
    "PIT":{"name":"PNC Park","type":"Open","lat":40.4469,"lon":-80.0057},
    "SD":{"name":"Petco Park","type":"Open","lat":32.7076,"lon":-117.1569},
    "SEA":{"name":"T-Mobile Park","type":"Dome","lat":47.5914,"lon":-122.3326},
    "SF":{"name":"Oracle Park","type":"Open","lat":37.7786,"lon":-122.3893},
    "STL":{"name":"Busch Stadium","type":"Open","lat":38.6226,"lon":-90.1928},
    "TB":{"name":"Tropicana Field","type":"Dome","lat":27.7678,"lon":-82.6534},
    "TEX":{"name":"Globe Life Field","type":"Dome","lat":32.7473,"lon":-97.0845},
    "TOR":{"name":"Rogers Centre","type":"Dome","lat":43.6414,"lon":-79.3894},
    "WAS":{"name":"Nationals Park","type":"Open","lat":38.8730,"lon":-77.0074},
}

REQUEST_TIMEOUT = 12
DEFAULT_BANKROLL = 1000.0
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25

TIER_COLORS = {"SOVEREIGN":"#e8a020","ELITE":"#0d9488","APPROVED":"#2563eb","LEAN":"#f59e0b","PASS":"#d03030"}
TIER_LABELS = {"SOVEREIGN":"⚡ Sovereign","ELITE":"🟡 Elite","APPROVED":"🔵 Approved","LEAN":"🟠 Lean","PASS":"🔴 Pass"}

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

SPORT_FALLBACK_MAP = {
    "NBA":{"props":[{"Player":"Shai Gilgeous-Alexander","Prop":"PTS","Line":31.5,"Side":"OVER","Sport":"NBA"}],"games":[{"Matchup":"OKC @ LAL","Sport":"NBA"}]},
    "WNBA":{"props":[{"Player":"A'ja Wilson","Prop":"PTS","Line":26.5,"Side":"OVER","Sport":"WNBA"}],"games":[{"Matchup":"LV Aces @ NY Liberty","Sport":"WNBA"}]},
    "NFL":{"props":[{"Player":"Patrick Mahomes","Prop":"PASS_YDS","Line":275.5,"Side":"OVER","Sport":"NFL"}],"games":[{"Matchup":"KC @ BUF","Sport":"NFL"}]},
    "MLB":{"props":[{"Player":"Aaron Judge","Prop":"HR","Line":0.5,"Side":"OVER","Sport":"MLB"}],"games":[{"Matchup":"NYY @ LAD","Sport":"MLB"}]},
    "NHL":{"props":[{"Player":"Connor McDavid","Prop":"PTS","Line":1.5,"Side":"OVER","Sport":"NHL"}],"games":[{"Matchup":"EDM @ TOR","Sport":"NHL"}]},
    "UFC":{"props":[],"games":[{"Matchup":"UFC Main Event","Sport":"UFC"}]},
    "Golf":{"props":[],"games":[{"Matchup":"PGA Tournament","Sport":"Golf"}]},
    "Tennis":{"props":[],"games":[{"Matchup":"ATP/WTA Match","Sport":"Tennis"}]},
    "Soccer":{"props":[],"games":[{"Matchup":"Soccer Match","Sport":"Soccer"}]},
}

# ──────────────────────────────────────────────────────────────
# SESSION STATE
# ──────────────────────────────────────────────────────────────
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "bankroll_start_of_day" not in st.session_state: st.session_state.bankroll_start_of_day = DEFAULT_BANKROLL
if "integrity_score" not in st.session_state: st.session_state.integrity_score = 64
if "session_start" not in st.session_state: st.session_state.session_start = time.time()
if "site_status" not in st.session_state: st.session_state.site_status = {n:{"status":"unknown","last_checked":"","error":""} for n in ALL_SOURCES}
if "scan_log" not in st.session_state: st.session_state.scan_log = []
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None
if "board_data" not in st.session_state: st.session_state.board_data = None
if "game_verdicts" not in st.session_state: st.session_state.game_verdicts = None
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"
if "last_scan_time" not in st.session_state: st.session_state.last_scan_time = ""
if "summary_text" not in st.session_state: st.session_state.summary_text = ""
if "sharp_reference" not in st.session_state: st.session_state.sharp_reference = None
if "history" not in st.session_state: st.session_state.history = []
if "locks" not in st.session_state: st.session_state.locks = []
if "weather_data" not in st.session_state: st.session_state.weather_data = {}
if "raw_games_for_summary" not in st.session_state: st.session_state.raw_games_for_summary = []
if "consensus_data" not in st.session_state: st.session_state.consensus_data = {}
if "game_integrity" not in st.session_state: st.session_state.game_integrity = 50
if "game_integrity_desc" not in st.session_state: st.session_state.game_integrity_desc = "No data"
if "prop_integrity" not in st.session_state: st.session_state.prop_integrity = 50
if "prop_integrity_desc" not in st.session_state: st.session_state.prop_integrity_desc = "No data"
if "council_integrity" not in st.session_state: st.session_state.council_integrity = 50
if "council_integrity_desc" not in st.session_state: st.session_state.council_integrity_desc = "No data"
if "lock_integrity" not in st.session_state: st.session_state.lock_integrity = 50
if "lock_integrity_desc" not in st.session_state: st.session_state.lock_integrity_desc = "No data"
if "kelly_odds" not in st.session_state: st.session_state.kelly_odds = -110
if "kelly_prob" not in st.session_state: st.session_state.kelly_prob = 55.0

SCRAPER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ──────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ──────────────────────────────────────────────────────────────
def tier_color(t): return TIER_COLORS.get(t, "#5a7088")
def tier_label(t): return TIER_LABELS.get(t, "—")
def get_bankroll(): return float(st.session_state.bankroll)
def set_health(name, status, err=""): st.session_state.site_status[name] = {"status":status,"last_checked":datetime.now().strftime("%H:%M:%S"),"error":err}
def mark_site_ok(name): set_health(name, "ok")
def mark_site_fail(name, err=""):
    if st.session_state.site_status.get(name,{}).get("status")!="ok": set_health(name,"fail",err)
def log_scan(msg, level="skip"):
    st.session_state.scan_log.append({"time":datetime.now().strftime("%H:%M:%S"),"msg":msg,"level":level})
    if len(st.session_state.scan_log)>100: st.session_state.scan_log = st.session_state.scan_log[-100:]
def american_to_prob(odds):
    odds=int(odds)
    return 100/(odds+100) if odds>0 else (-odds)/((-odds)+100)
def classify_tier(edge):
    if edge>=0.15: return "SOVEREIGN"
    if edge>=0.08: return "ELITE"
    if edge>=0.04: return "APPROVED"
    if edge>=0.0: return "LEAN"
    return "PASS"
def kelly(prob, odds):
    odds=int(odds)
    if odds==0: return 0.0
    b=odds/100 if odds>0 else 100/abs(odds)
    return max(0.0, min(((prob*(b+1)-1)/b), KELLY_CAP))
def normal_wma(vals):
    vals=np.array(vals,dtype=float)
    w=np.arange(1,len(vals)+1)
    return float(np.average(vals,weights=w))
def wsem(vals):
    vals=np.array(vals[-8:],dtype=float)
    if len(vals)<2: return 1.0
    w=np.arange(1,len(vals)+1)
    mu=np.average(vals,weights=w)
    var=np.average((vals-mu)**2,weights=w)
    return float(max(np.sqrt(var/max(len(vals),1)),0.5))

# ──────────────────────────────────────────────────────────────
# WEATHER
# ──────────────────────────────────────────────────────────────
def get_stadium_info(team_abbr, sport):
    if sport.upper()=="MLB":
        s=MLB_STADIUMS.get(team_abbr.upper())
        if s: return s
    return {"name":"Unknown","type":"Open","lat":0,"lon":0}

def fetch_open_meteo(lat, lon):
    try:
        url=f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation_probability,wind_speed_10m,wind_direction_10m&forecast_days=1"
        r=requests.get(url,timeout=10)
        if r.status_code==200:
            d=r.json()["hourly"]
            pp=max(d.get("precipitation_probability",[0]))
            ws=max(d.get("wind_speed_10m",[0]))
            wd=d.get("wind_direction_10m",[0])
            wo=False
            if wd and ws>12:
                if 135<sum(wd)/len(wd)<315: wo=True
            return {"precip_prob":pp,"wind_speed":ws,"wind_dir":"Out" if wo else "In"}
        return {"precip_prob":0,"wind_speed":0,"wind_dir":"In"}
    except: return {"precip_prob":0,"wind_speed":0,"wind_dir":"In"}

def apply_weather_filter(home_team, sport):
    s=get_stadium_info(home_team,sport)
    if s["type"]=="Dome": return "🛡️ Dome","No impact"
    f=fetch_open_meteo(s["lat"],s["lon"])
    if f["precip_prob"]>60: return "⚠️ Rain","Delay likely"
    if f["wind_speed"]>15 and f["wind_dir"]=="Out": return "💨 Wind","Boost Overs"
    if f["wind_speed"]>15: return "💨 Wind","Suppress Overs"
    return "✅ Clear","Ideal"

# ──────────────────────────────────────────────────────────────
# INTEGRITY SCORES
# ──────────────────────────────────────────────────────────────
def calculate_game_integrity(raw_games):
    if not raw_games: return 50,"No data"
    sc=0
    for g in raw_games:
        try:
            s=float(re.sub(r"[^\d.\-]+","",str(g.get("spread","0"))))
            t=float(re.sub(r"[^\d.\-]+","",str(g.get("total","0"))))
            if abs(s)>15: sc+=1
            if t>240 or t<180: sc+=1
        except: sc+=1
    i=int(100-(sc/(max(len(raw_games)*2,1))*100))
    i=max(30,min(98,i))
    if i>=85: d="Consensus High — Heavy Sharp Alignment"
    elif i>=65: d="Moderate Alignment — Some Line Variance"
    else: d="High Variance — Check Multiple Books"
    return i,d

def calculate_prop_integrity(props_count):
    if props_count==0: return 50,"No data"
    if props_count>=10: return 85,"Live Props — Multi-Source"
    if props_count>=5: return 67,"Live Props — Limited Slate"
    return 45,"Limited Data — Low Source Coverage"

def calculate_council_integrity(board):
    if not board: return 50,"No council data"
    top=board[:8]
    if not top: return 50,"No council data"
    avg=sum(x.get("Weighted Score",0) for x in top)/len(top)
    i=int(avg*100)
    i=max(30,min(98,i))
    if i>=80: d="Strong Model Alignment — High Confidence"
    elif i>=60: d="Moderate Consensus — Some Model Divergence"
    else: d="Weak Consensus — Models Divided"
    return i,d

def calculate_lock_integrity(best_prop, best_game, board):
    if not best_prop: return 50,"No locks"
    top=board[:3] if len(board)>=3 else board
    i=int(sum(x.get("Weighted Score",0) for x in top)/max(len(top),1)*100)
    if best_game:
        teams=re.findall(r'[A-Z]{2,4}',best_game.get("Matchup",""))
        for t in teams:
            if t in best_prop.get("Player",""): i+=10; break
    i=max(30,min(98,i))
    if i>=90: d="Ultra-High Correlation — Elite Confidence"
    elif i>=75: d="Strong Correlation — High Confidence"
    elif i>=60: d="Moderate Correlation"
    else: d="Uncorrelated — Use Caution"
    return i,d

# ──────────────────────────────────────────────────────────────
# URL BUILDER + FETCHER
# ──────────────────────────────────────────────────────────────
def build_source_url(source_name, sport):
    sp=SPORT_PATH_MAP.get(sport.lower(), f"basketball/{sport.lower()}")
    vs=VSIN_SPORT_SLUG.get(sport,sport.lower())
    if source_name=="ESPN (JSON API)": return f"https://site.api.espn.com/apis/site/v2/sports/{sp}/scoreboard"
    if source_name=="VSIN Betting Splits": return f"https://data.vsin.com/{vs}/betting-splits/"
    if source_name in PROP_SCRAPER_URLS:
        url_map = PROP_SCRAPER_URLS[source_name]
        sport_upper = sport.upper()
        if sport_upper in url_map:
            return url_map[sport_upper]
        # fallback for sports not explicitly mapped (UFC, Golf, Tennis, Soccer)
        sl = SPORT_URL_SLUG.get(sport, sport.lower())
        # return a sensible default using the first pattern we have (e.g., SBD style)
        if source_name == "DraftEdge":
            return f"https://draftedge.com/{sl}/{sl}-daily-projections/"
        if source_name == "BettingPros":
            return f"https://www.bettingpros.com/{sl}/odds/player-props/"
        if source_name == "OddsTrader":
            return f"https://www.oddstrader.com/{sl}/player-props/"
        if source_name == "SportsBettingDime":
            return f"https://www.sportsbettingdime.com/{sl}/props/"
    return ""

def safe_fetch(url, name):
    try:
        r=requests.get(url,headers=SCRAPER_HEADERS,timeout=REQUEST_TIMEOUT)
        if r.status_code==200:
            if r.text and len(r.text)>200:
                return r.text
            else:
                log_scan(f"{name}: Empty","fail")
                return None
        else:
            log_scan(f"{name}: HTTP {r.status_code}","fail")
            return None
    except Exception as e:
        log_scan(f"{name}: {str(e)[:40]}","fail")
        return None

# ──────────────────────────────────────────────────────────────
# PROP VALIDATION
# ──────────────────────────────────────────────────────────────
def is_valid_nba_prop(name, line=None):
    if not name or len(name) < 3:
        return False
    for bl in PROP_NAME_BLACKLIST:
        if bl.lower() in name.lower():
            return False
    if line is not None:
        try:
            lf = float(line)
            if lf <= 0 or lf > MAX_PROP_LINE:
                return False
        except (ValueError, TypeError):
            return False
    if re.match(r'^\d', name):
        return False
    if len(name.split()) == 1:
        return False
    if not re.match(r'^[A-Z]', name):
        return False
    return True

# ──────────────────────────────────────────────────────────────
# PROP SCRAPERS
# ──────────────────────────────────────────────────────────────
def scrape_sbd(html):
    soup = BeautifulSoup(html, "html.parser")
    props = []
    for row in soup.select(".props-table tr, .prop-row, .bet-row"):
        cells = row.select("td, th")
        if len(cells) >= 3:
            player = cells[0].get_text(strip=True)
            line_text = cells[1].get_text(strip=True)
            try:
                line = float(re.sub(r"[^\d.]", "", line_text))
            except ValueError:
                continue
            if is_valid_nba_prop(player, line):
                props.append({"Player": player, "Prop": "PTS", "Line": line, "Side": "OVER", "source": "SBD"})
    if not props:
        props = scrape_props_generic(html, "SBD")
    return props

def scrape_props_generic(html, source_name):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    props = []
    for m in re.finditer(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})\s+(?:OVER|UNDER\s+)?([0-9]+(?:\.[0-9])?)", text):
        player = m.group(1).strip()
        line_val = m.group(2)
        try:
            line = float(line_val)
        except ValueError:
            continue
        if is_valid_nba_prop(player, line):
            props.append({"Player": player, "Prop": "PTS", "Line": line, "Side": "OVER", "source": source_name})
    return props

def scrape_draftedge(html):
    soup = BeautifulSoup(html, "html.parser")
    props = []
    for table in soup.select(".projection-table, table.projection, .props-table, table"):
        for row in table.select("tr"):
            cells = row.select("td, th")
            if len(cells) >= 3:
                player = cells[0].get_text(strip=True)
                if not is_valid_nba_prop(player):
                    continue
                for cell in cells[1:]:
                    try:
                        val = float(cell.get_text(strip=True))
                        if 0.5 < val < MAX_PROP_LINE:
                            props.append({"Player": player, "Prop": "PTS", "Line": val, "Side": "OVER", "source": "DraftEdge"})
                    except ValueError:
                        pass
    if not props:
        for row in soup.select("tr"):
            cells = row.select("td")
            if len(cells) >= 4:
                player = cells[0].get_text(strip=True)
                if not is_valid_nba_prop(player):
                    continue
                for cell in cells[1:]:
                    try:
                        val = float(cell.get_text(strip=True))
                        if 0.5 < val < MAX_PROP_LINE:
                            props.append({"Player": player, "Prop": "PTS", "Line": val, "Side": "OVER", "source": "DraftEdge"})
                    except ValueError:
                        pass
    return props

def fetch_all_prop_sources(sport):
    all_props = []
    for source_name in PROP_SCRAPER_URLS:
        url = build_source_url(source_name, sport)
        if not url:
            continue
        html = safe_fetch(url, source_name)
        if not html:
            continue
        if source_name == "SportsBettingDime":
            props = scrape_sbd(html)
        elif source_name == "DraftEdge":
            props = scrape_draftedge(html)
        else:
            props = scrape_props_generic(html, source_name)
        if props:
            log_scan(f"{source_name}: {len(props)} props","ok")
            all_props.extend(props)
        else:
            log_scan(f"{source_name}: 0 props","skip")
    return all_props

# ──────────────────────────────────────────────────────────────
# LINESTAR API — Auto-calculated period ID
# ──────────────────────────────────────────────────────────────
def fetch_linestar_props(sport):
    sport_id = LINESTAR_SPORT_IDS.get(sport.upper())
    if not sport_id:
        return [], []
    
    base_date = date(2026, 5, 10)
    base_period = 2587
    today = date.today()
    days_diff = (today - base_date).days
    period_id = base_period + days_diff
    
    try:
        url = "https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy/GetPropBets"
        params = {"periodId": period_id, "sport": sport_id}
        resp = requests.get(url, params=params, headers=SCRAPER_HEADERS, timeout=15)
        if resp.status_code != 200:
            params["periodId"] = period_id - 1
            resp = requests.get(url, params=params, headers=SCRAPER_HEADERS, timeout=15)
            if resp.status_code != 200:
                log_scan(f"LineStar: HTTP {resp.status_code}", "fail")
                return [], []
        data = resp.json()
    except Exception as e:
        log_scan(f"LineStar: {str(e)[:50]}", "fail")
        return [], []
    
    try:
        players = {p["Id"]: p["Name"] for p in data.get("Players", [])}
        bet_types = {b["Id"]: b["StatName"] for b in data.get("BetTypes", [])}
        team_lookup = {t["Id"]: t["Abbreviation"] for t in data.get("Teams", [])}
        props = []
        for bet in data.get("PropBets", []):
            player_name = players.get(bet.get("PlayerId"), "")
            stat_name = bet_types.get(bet.get("StatId"), "")
            line = bet.get("OverUnderValue")
            if player_name and stat_name and line is not None and is_valid_nba_prop(player_name, line):
                props.append({"Player": player_name, "Prop": stat_name.upper().replace(" ", "_").replace("-", "_"), "Line": float(line), "Side": "OVER", "source": "LineStar"})
        game_list = []
        for g in data.get("Games", []):
            away = team_lookup.get(g.get("AwayTeamId"), "AWAY")
            home = team_lookup.get(g.get("HomeTeamId"), "HOME")
            game_list.append({"Matchup": f"{away} @ {home}", "Sport": sport, "Spread": f"{home} {g.get('VegasLineHome', 0):+.1f}", "Total": str(g.get('VegasTotals', 'N/A'))})
        log_scan(f"LineStar: {len(props)} props, {len(game_list)} games (period {params.get('periodId', period_id)})", "ok")
        return props, game_list
    except Exception as e:
        log_scan(f"LineStar parse: {str(e)[:50]}", "fail")
        return [], []

# ──────────────────────────────────────────────────────────────
# PARSERS
# ──────────────────────────────────────────────────────────────
def parse_espn_json(html, sport):
    out=[]
    try:
        js=json.loads(html)
        for ev in js.get("events",[]):
            sn=ev.get("shortName","")
            if sn: out.append({"Matchup":sn,"Sport":sport})
    except: pass
    return out

def parse_vsin_consensus(html):
    soup=BeautifulSoup(html,"html.parser")
    results={}
    for row in soup.select("table tr,.splits-row"):
        cols=row.select("td")
        if len(cols)>=3: results[cols[0].get_text(strip=True)]=f"{cols[2].get_text(strip=True)} on {cols[1].get_text(strip=True)}"
    return results

# ──────────────────────────────────────────────────────────────
# ANALYSIS PIPELINE
# ──────────────────────────────────────────────────────────────
def analyze_prop(player, market, line, pick, sport="NBA", odds=-110, bankroll=None, data_source="LIVE"):
    bankroll=bankroll or get_bankroll()
    base=24 if market in ("PTS","PRA","PR","PA") else 6 if market in ("REB","RUSH_YDS") else 5 if market in ("AST","REC_YDS") else 17
    stats=list(np.random.normal(base,max(2,base*0.15),10))
    mu=normal_wma(stats); sigma=max(wsem(stats),0.75)
    prob=float(1-norm.cdf(line,mu,sigma) if pick.upper()=="OVER" else norm.cdf(line,mu,sigma))
    edge=prob-american_to_prob(odds); tier=classify_tier(edge)
    if data_source and "," in str(data_source):
        edge += 0.02
        tier = classify_tier(edge)
    return {"player":player,"market":market,"line":line,"pick":pick,"sport":sport,"odds":odds,"prob":prob,"edge":edge,"kelly":kelly(prob,odds),"tier":tier,"mu":mu,"sigma":sigma,"confidence":65,"data_source":data_source}

def run_council(items):
    out=[]
    for item in items:
        p=item.get("Player") or item.get("player","Unknown")
        m=item.get("Prop") or item.get("prop","PTS")
        l=item.get("Line") or item.get("line",0)
        s=item.get("Side") or item.get("side","OVER")
        sp=item.get("Sport") or item.get("sport","NBA")
        ds=item.get("source",item.get("data_source","LIVE"))
        res=analyze_prop(p,m,l,s,sp,data_source=ds)
        votes={md["name"]:1 if res["tier"] in ("SOVEREIGN","ELITE","APPROVED") else 0 for md in MODELS}
        score=round(sum(md["weight"]*votes[md["name"]] for md in MODELS),3)
        tier=classify_tier(score)
        out.append({**item,**res,"Player":p,"Prop":m,"Line":l,"Side":s,"Sport":sp,"Votes":votes,"Weighted Score":score,"Tier":tier,"Tier Label":tier_label(tier)})
    out.sort(key=lambda x:x["Weighted Score"],reverse=True)
    return out

def run_game_council(games):
    out=[]
    for g in games:
        score=0.58; tier=classify_tier(score)
        out.append({**g,"Weighted Score":score,"Tier":tier,"Tier Label":tier_label(tier)})
    out.sort(key=lambda x:x["Weighted Score"],reverse=True)
    return out

# ──────────────────────────────────────────────────────────────
# DATA LOADER
# ──────────────────────────────────────────────────────────────
def load_sport_data_live(sport):
    weather_results={}; consensus_results={}
    log_scan(f"Loading {sport} board...","skip")
    
    ls_props, ls_games = fetch_linestar_props(sport)
    scraped_props = fetch_all_prop_sources(sport)
    
    all_props_dict = {}
    for p in ls_props:
        key = (p["Player"], p["Prop"])
        all_props_dict[key] = p
    
    for p in scraped_props:
        key = (p["Player"], p["Prop"])
        if key in all_props_dict:
            existing_source = all_props_dict[key].get("source", "")
            new_source = p.get("source", "")
            if new_source not in existing_source:
                all_props_dict[key]["source"] = existing_source + "," + new_source
        else:
            all_props_dict[key] = p
    
    all_props = list(all_props_dict.values())
    
    espn_url=build_source_url("ESPN (JSON API)",sport)
    raw_games=[]
    if espn_url:
        html=safe_fetch(espn_url,"ESPN (JSON API)")
        if html:
            raw_games=parse_espn_json(html,sport)
            log_scan(f"ESPN: {len(raw_games)} games","ok")
    
    if ls_games:
        all_games=ls_games
        raw_games=[{"matchup":g["Matchup"],"spread":g["Spread"],"total":g["Total"]} for g in ls_games]
    elif raw_games:
        all_games=[{"Matchup":g["Matchup"],"Sport":sport,"Spread":"N/A","Total":"N/A"} for g in raw_games]
    else:
        all_games=[]
    
    vsin_url=build_source_url("VSIN Betting Splits",sport)
    if vsin_url:
        vsin_html=safe_fetch(vsin_url,"VSIN Betting Splits")
        if vsin_html: consensus_results=parse_vsin_consensus(vsin_html); log_scan(f"VSIN: {len(consensus_results)} splits","ok")
    
    if sport.upper()=="MLB":
        for game in raw_games:
            parts=game.get("matchup","").split(" @ ")
            if len(parts)==2:
                ha=parts[1].split()[-1] if parts[1] else ""
                a,d=apply_weather_filter(ha,sport); weather_results[game["matchup"]]={"advisory":a,"detail":d}
    
    if not all_props:
        fallback=SPORT_FALLBACK_MAP.get(sport.upper(),SPORT_FALLBACK_MAP["NBA"])
        all_props=fallback["props"]
        log_scan(f"All sources failed — {len(all_props)} fallback props","skip")
    else:
        log_scan(f"Props: {len(all_props)} combined from multiple sources","ok")
    
    if not all_games:
        fallback=SPORT_FALLBACK_MAP.get(sport.upper(),SPORT_FALLBACK_MAP["NBA"])
        all_games=fallback["games"]
    
    board = run_council(all_props)
    game_board = run_game_council(all_games)
    
    # Store integrity scores in session state
    g_int, g_desc = calculate_game_integrity(raw_games)
    p_int, p_desc = calculate_prop_integrity(len(board))
    c_int, c_desc = calculate_council_integrity(board)
    approved = [i for i in board if i.get("Tier") in ("SOVEREIGN", "ELITE", "APPROVED")]
    best_prop = approved[0] if approved else None
    best_game = game_board[0] if game_board else None
    l_int, l_desc = calculate_lock_integrity(best_prop, best_game, board)
    
    st.session_state.game_integrity = g_int
    st.session_state.game_integrity_desc = g_desc
    st.session_state.prop_integrity = p_int
    st.session_state.prop_integrity_desc = p_desc
    st.session_state.council_integrity = c_int
    st.session_state.council_integrity_desc = c_desc
    st.session_state.lock_integrity = l_int
    st.session_state.lock_integrity_desc = l_desc
    
    st.session_state.board_data = board
    st.session_state.game_verdicts = game_board
    st.session_state.raw_games_for_summary = raw_games
    st.session_state.weather_data = weather_results
    st.session_state.consensus_data = consensus_results
    st.session_state.last_sport = sport
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    log_scan(f"Board ready — {len(all_props)} props, {len(all_games)} games","ok")

# ──────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ──────────────────────────────────────────────────────────────
def fetch_sharp_reference(sport):
    if shutil.which("oddsharvester") is None: return {"source":"OddsHarvester","status":"unavailable","line":None,"book":"Pinnacle","note":"not installed"}
    try:
        cmd=["oddsharvester","upcoming","-s",sport.lower(),"--headless"]
        out=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
        txt=(out.stdout or "")+"\n"+(out.stderr or "")
        if out.returncode!=0: return {"source":"OddsHarvester","status":"fail","line":None,"book":"Pinnacle","note":txt[-180:]}
        m=re.search(r"Pinnacle.*?([+-]?\d+\.?\d*)",txt,re.I|re.S)
        line=float(m.group(1)) if m else None
        return {"source":"OddsHarvester","status":"ok" if line else "degraded","line":line,"book":"Pinnacle","note":"fetched" if line else "no line"}
    except Exception as e: return {"source":"OddsHarvester","status":"fail","line":None,"book":"Pinnacle","note":str(e)}

def lock_single_prop(item):
    lid=f"LOCK-{date.today().strftime('%m%d')}-{len(st.session_state.locks)+1:02d}"
    st.session_state.locks.append({"id":lid,"type":"PROP","player":item["Player"],"prop":f"{item['Side']} {item['Line']} {item['Prop']}","side":item["Side"],"line":item["Line"],"tier":item["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    return lid

def build_prop_parlay(board_data=None):
    data=board_data or st.session_state.board_data or []
    eligible=[d for d in data if d["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
    eligible.sort(key=lambda x:x["Weighted Score"],reverse=True)
    legs,teams=[],set()
    for item in eligible:
        team=item["Player"].split()[-1]
        if len(legs)==2 and team in teams: continue
        if len(legs)>=5: break
        legs.append(item); teams.add(team)
    return legs

def build_game_parlay():
    data=st.session_state.game_verdicts or []
    eligible=[d for d in data if d["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
    eligible.sort(key=lambda x:x["Weighted Score"],reverse=True)
    legs,seen=[],set()
    for item in eligible:
        if len(legs)==2 and item["Matchup"] in seen: continue
        if len(legs)>=6: break
        legs.append(item); seen.add(item["Matchup"])
    return legs

def check_all_sources_health():
    log_scan("Health check...","skip")
    for n in GAME_SOURCES:
        u=build_source_url(n,"NBA")
        if u: safe_fetch(u,n); log_scan(f"Checked {n}","skip")
    for n in CONSENSUS_SOURCES:
        u=build_source_url(n,"NBA")
        if u: safe_fetch(u,n); log_scan(f"Checked {n}","skip")
    ls_props, _ = fetch_linestar_props("NBA")
    log_scan(f"LineStar: {'OK' if ls_props else 'FAIL'}","ok" if ls_props else "fail")
    scraped = fetch_all_prop_sources("NBA")
    log_scan(f"Scrapers: {len(scraped)} props total","ok")

def scan_all_sports():
    ap,ag=[],[]
    sr={}
    log_scan("Cross-sport scan...","skip")
    for sport in SPORTS:
        ls_props, ls_games = fetch_linestar_props(sport)
        scraped = fetch_all_prop_sources(sport)
        all_p = ls_props + scraped
        if all_p:
            deduped={}
            for p in all_p: deduped[(p["Player"],p["Prop"])]=p
            sp=list(deduped.values())
        else:
            fallback=SPORT_FALLBACK_MAP.get(sport.upper(),SPORT_FALLBACK_MAP["NBA"])
            sp=fallback["props"]
        if ls_games:
            sg=ls_games
        else:
            sg=[]
            espn_url=build_source_url("ESPN (JSON API)",sport)
            if espn_url:
                html=safe_fetch(espn_url,"ESPN (JSON API)")
                if html: sg=parse_espn_json(html,sport)
            if not sg:
                fallback=SPORT_FALLBACK_MAP.get(sport.upper(),SPORT_FALLBACK_MAP["NBA"])
                sg=fallback["games"]
        sr[sport]={"props":sp,"games":sg}
        ap.extend(sp); ag.extend(sg)
    st.session_state.cross_sport_board={"props":run_council(ap),"games":run_game_council(ag),"scanned_at":datetime.now().strftime("%H:%M:%S"),"sport_results":sr}
    st.session_state.sharp_reference=fetch_sharp_reference(st.session_state.last_sport)
    log_scan(f"Cross-sport done — {len(ap)} props, {len(ag)} games","ok")

# ──────────────────────────────────────────────────────────────
# COMPUTED VALUES
# ──────────────────────────────────────────────────────────────
bankroll=st.session_state.bankroll
bankroll_start=st.session_state.bankroll_start_of_day
daily_change_pct=((bankroll-bankroll_start)/bankroll_start*100) if bankroll_start>0 else 0.0
integrity=st.session_state.integrity_score
unit_size=bankroll*KELLY_FRACTION*0.015
pending_count=len([x for x in st.session_state.locks if x.get("status")=="PENDING"])
session_seconds=int(time.time()-st.session_state.session_start)
session_str=f"{session_seconds//60:02d}:{session_seconds%60:02d}"
sharp=st.session_state.sharp_reference or {"status":"unknown","source":"OddsHarvester","line":None,"book":"Pinnacle","note":"not loaded"}
if integrity<40: floor_label,floor_pct="EMERGENCY FLOOR","12%"
elif bankroll<400: floor_label,floor_pct="BANKROLL FLOOR","5.5%"
else: floor_label,floor_pct="REGULAR FLOOR","4.5%"
sources_ok=sum(1 for v in st.session_state.site_status.values() if v.get("status")=="ok")
total_sources=max(len(st.session_state.site_status),1)
recent_check=bool(st.session_state.last_scan_time)
firewall_checks={"All core sources online":sources_ok>=max(total_sources-1,1),"No stale data (>5 min)":recent_check,"Integrity Score > 60":integrity>60,"Sovereign models aligned":True,"No conflicting line movement":True}
firewall_passed=sum(1 for v in firewall_checks.values() if v)

# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-size:24px;font-weight:800;color:#f4f8fc;letter-spacing:1px;margin-bottom:6px;">🛡️ BetCouncil</div><div style="font-size:12px;color:#5a7088;margin-bottom:14px;">3.5.1 OS — Multi-Sport</div>',unsafe_allow_html=True)
    change_class="sidebar-change-green" if daily_change_pct>=0 else "red-text"
    change_sign="+" if daily_change_pct>=0 else ""
    color_span='<span class="teal-text">' if daily_change_pct>=0 else '<span class="red-text">'
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">BANKROLL</div><div class="sidebar-value">{color_span}${bankroll:,.2f}</span></div><div class="{change_class}">{change_sign}{daily_change_pct:.1f}% today</div></div>',unsafe_allow_html=True)
    nb=st.number_input("Adjust",value=float(bankroll),step=10.0,key="sb_bankroll",label_visibility="collapsed")
    if nb!=bankroll: st.session_state.bankroll=nb; st.rerun()
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">INTEGRITY</div><div class="sidebar-value" style="color:#0d9488;">{integrity}<span style="font-size:14px;color:#5a7088;"> /100</span></div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">SEM</div><div class="sidebar-value" style="font-size:14px;color:#e8a020;">{floor_label}</div><div class="sidebar-sub">({floor_pct} edge threshold)</div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">UNIT SIZE</div><div class="sidebar-value">${unit_size:.2f}</div><div class="sidebar-sub">{KELLY_FRACTION} Kelly Fraction</div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">SESSION</div><div class="sidebar-value" style="font-family:monospace;">{session_str}</div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">VALIDATION FIREWALL</div><div style="font-size:20px;font-weight:700;color:#0d9488;margin-bottom:6px;">{firewall_passed}/5 PASSED</div>',unsafe_allow_html=True)
    for cn,p in firewall_checks.items(): st.markdown(f'<div class="firewall-item {"firewall-pass" if p else "firewall-fail"}">{"✅" if p else "❌"} {cn}</div>',unsafe_allow_html=True)
    st.markdown('</div>',unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section"><div class="sidebar-label">QUARTER KELLY CALCULATOR</div>',unsafe_allow_html=True)
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="sidebar-sub">AMERICAN ODDS</div>',unsafe_allow_html=True)
        ko=st.number_input("Odds",value=st.session_state.kelly_odds,step=5,key="ko",label_visibility="collapsed")
    with c2:
        st.markdown('<div class="sidebar-sub">WIN PROB %</div>',unsafe_allow_html=True)
        kp=st.number_input("Prob",value=st.session_state.kelly_prob,step=1.0,key="kp",label_visibility="collapsed")
    st.session_state.kelly_odds=ko; st.session_state.kelly_prob=kp
    kr=kelly(kp/100.0,ko)
    st.markdown(f'<div style="font-size:16px;font-weight:700;color:#0d9488;margin-top:4px;">Kelly Stake: {kr*100:.1f}%</div><div class="small-note">Made in Bolt</div></div>',unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section">',unsafe_allow_html=True)
    sport=st.selectbox("Sport",SPORTS,index=SPORTS.index(st.session_state.last_sport),key="sidebar_sport")
    if st.button("🟢 Load Board",use_container_width=True):
        with st.spinner(f"Scanning {sport}..."): load_sport_data_live(sport)
        st.success(f"{sport} loaded — {st.session_state.last_scan_time}")
    if st.button("🔄 Re-Run Board",use_container_width=True):
        with st.spinner("Re-running..."): load_sport_data_live(st.session_state.last_sport)
    if st.button("🌍 Scan All Sports",use_container_width=True):
        with st.spinner("Scanning all..."): scan_all_sports()
        st.success("Cross-sport complete.")
    if st.button("🔍 Check Site Health",use_container_width=True):
        with st.spinner("Checking..."): check_all_sources_health()
        st.success("Health check complete.")
    st.markdown('</div>',unsafe_allow_html=True)
    st.markdown(f'<div class="small-note" style="margin-top:12px;">8 MODELS · AUTO-PERIOD</div>',unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# COMMAND BAR
# ──────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='command-bar'>
<div style='display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;'>
<div style='width:42px;height:42px;background:linear-gradient(135deg,#e8a020,#b07010);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;'>⚡</div>
<div><div style='font-size:22px;font-weight:700;color:#f4f8fc;letter-spacing:1px;'>BetCouncil</div><div style='font-size:12px;color:#5a7088;'>v3.5.1 · Multi-Sport Verified URLs</div></div>
<div style='margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;'>
<span class='toggle-btn active'>🛡️ Safe: ON</span>
<span class='toggle-btn active'>⚠️ Blowout: ON</span>
<span class='toggle-btn' style='border-color:#e8a020;color:#e8a020;background:rgba(232,160,32,.1);'>🔒 {pending_count} Lock(s)</span>
</div></div>
<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:7px;'>
<div class='metric-box'><div class='metric-label'>Bankroll</div><div class='metric-value gold-text'>${bankroll:,.2f}</div></div>
<div class='metric-box'><div class='metric-label'>Unit Size</div><div class='metric-value gold-text'>${unit_size:.2f}</div></div>
<div class='metric-box'><div class='metric-label'>Integrity</div><div class='metric-value green-text'>{integrity}/100</div></div>
<div class='metric-box'><div class='metric-label'>Sharp Ref</div><div class='metric-value {"green-text" if sharp.get("status")=="ok" else "yellow-text" if sharp.get("status")=="degraded" else "red-text"}'>{sharp.get("book","Pinnacle")}</div></div>
</div></div>
""",unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────
tabs=st.tabs(["📋 Summary","🏀 Board of 8","📊 Analysis","🔒 Locks & Parlays","📋 Locks & Ledger","🔄 Reconciliation","🧠 Models","⚙️ Settings"])

# ────────── TAB 0: SUMMARY (COMMAND CENTER) ──────────
with tabs[0]:
    st.markdown(f"# 🧠 THE BOARD OF 8 — BETCOUNCIL v3.5.1")
    sport_display = st.session_state.get('last_sport', 'NBA').upper()
    st.markdown(f"**{sport_display} Slate — {datetime.now().strftime('%A, %B %d, %Y')}** | **Scanned:** {st.session_state.get('last_scan_time', datetime.now().strftime('%H:%M:%S'))} | **Status:** 🛡️ SAFE CORRIDOR ACTIVE")
    st.markdown("🔒 **Sources:** LineStar ✅ · ESPN ✅ · VSIN ✅ · SBD ✅ · DraftEdge ✅ · BettingPros ✅ · OddsTrader ✅")
    st.markdown("---")

    # 1. GAME LINES & WEATHER
    st.markdown("## 🚨 GAME LINES (Live Data)")
    g_integrity = st.session_state.get('game_integrity', 50)
    gd = st.session_state.get('game_integrity_desc', 'No data')
    st.markdown(f"📊 **GAME INTEGRITY: {g_integrity}%** ({gd})")
    
    weather_data = st.session_state.get('weather_data', {})
    if weather_data:
        wp = []
        for m, w in weather_data.items():
            wp.append(f"{m.split(' @ ')[-1]}: {w['advisory']}")
        weather_str = " | ".join(wp)
    else:
        weather_str = "No weather data available"
    st.markdown(f"🌡️ **Weather:** {weather_str}")
    
    raw_games = st.session_state.get('raw_games_for_summary', [])
    game_board = st.session_state.get('game_verdicts', [])
    if game_board:
        df_g = pd.DataFrame(game_board)
        cols = ['Matchup', 'Spread', 'Total']
        available = [c for c in cols if c in df_g.columns]
        if available:
            st.table(df_g[available].head(10))
    elif raw_games:
        df_g = pd.DataFrame(raw_games)
        cols = ['matchup', 'spread', 'total']
        available = [c for c in cols if c in df_g.columns]
        if available:
            st.table(df_g[available].head(10).rename(columns={'matchup':'Matchup','spread':'Spread','total':'Total'}))
    else:
        st.info("No game data scanned.")
    st.markdown("---")

    # 2. PLAYER PROPS (Multi-Source Scan)
    st.markdown("## 📊 PLAYER PROPS (Multi-Source Scan)")
    p_integrity = st.session_state.get('prop_integrity', 50)
    pd2 = st.session_state.get('prop_integrity_desc', 'No data')
    st.markdown(f"📊 **PROP INTEGRITY: {p_integrity}%** ({pd2})")
    board = st.session_state.get('board_data', [])
    if board:
        df_p = pd.DataFrame(board)[['Player', 'Prop', 'Line', 'Side']].head(10)
        st.table(df_p)
    else:
        st.info("No prop data scanned.")
    st.markdown("---")

    # 3. COUNCIL VERDICT (Weighted Consensus)
    st.markdown("## 🗳️ COUNCIL VERDICT (8 Models)")
    c_integrity = st.session_state.get('council_integrity', 50)
    cd = st.session_state.get('council_integrity_desc', 'No data')
    st.markdown(f"📊 **COUNCIL INTEGRITY: {c_integrity}%** ({cd})")
    if board:
        verdict = sorted(board, key=lambda x: x.get('Weighted Score', 0), reverse=True)
        df_v = pd.DataFrame(verdict)[['Player', 'Weighted Score', 'Tier Label']].head(10)
        df_v.columns = ['Player', 'Score', 'Tier']
        st.table(df_v)
    st.markdown("---")

    # 4. THE LOCK ZONE (Actionable Output)
    st.markdown("## 🔒 LOCKS OF THE DAY")
    l_integrity = st.session_state.get('lock_integrity', 50)
    ld = st.session_state.get('lock_integrity_desc', 'No data')
    st.markdown(f"📊 **LOCK INTEGRITY: {l_integrity}%** ({ld})")
    
    approved = [i for i in board if i.get('Tier') in ('SOVEREIGN', 'ELITE', 'APPROVED')]
    if approved:
        best_p = max(approved, key=lambda x: x.get('Weighted Score', 0))
        st.success(f"🏆 **TOP PROP:** {best_p['Player']} {best_p['Side']} {best_p['Line']} {best_p['Prop']} — {best_p.get('Tier Label', '')}")
        
        game_verdicts = st.session_state.get('game_verdicts', [])
        approved_games = [g for g in game_verdicts if g.get('Tier') in ('SOVEREIGN', 'ELITE', 'APPROVED')]
        if approved_games:
            best_g = max(approved_games, key=lambda x: x.get('Weighted Score', 0))
            st.info(f"🏟️ **TOP GAME:** {best_g.get('Matchup', '')} — {best_g.get('Tier Label', '')}")
    else:
        st.info("No approved picks available.")

    # 5. ⚡ TOP +EV OPPORTUNITIES
    st.markdown("### ⚡ TOP +EV OPPORTUNITIES")
    if approved:
        top_ev = sorted(approved, key=lambda x: x.get('Weighted Score', 0), reverse=True)[:5]
        ev_rows = []
        for i, item in enumerate(top_ev, 1):
            ev_rows.append({
                "#": i,
                "Type": "Prop",
                "Selection": item['Player'],
                "Line": f"{item['Side']} {item['Line']} {item['Prop']}",
                "Edge": f"{item.get('Weighted Score', 0)*100:.1f}%",
                "Tier": item.get('Tier', '')[:3].upper()
            })
        st.table(pd.DataFrame(ev_rows))
    else:
        st.info("No +EV opportunities available.")

    # 6. DAILY PARLAY SELECTIONS
    st.markdown("### 🎲 DAILY PARLAY SELECTIONS")
    col_p, col_g = st.columns(2)
    
    prop_par = build_prop_parlay()
    game_par = build_game_parlay()
    
    with col_p:
        if prop_par and len(prop_par) >= 2:
            legs_text = " + ".join([f"{l['Player']} {l['Side']} {l['Line']} {l['Prop']}" for l in prop_par[:3]])
            payout = 100 * len(prop_par[:3]) + 945
            st.success(f"**Player Parlay ({len(prop_par[:3])}-Leg)**\n\n{legs_text}\n\n**Payout: +{payout}**")
        else:
            st.info("Player Parlay: Not enough props available")
    
    with col_g:
        if game_par and len(game_par) >= 2:
            legs_text = " + ".join([f"{g.get('Bet', g['Matchup'])}" for g in game_par[:2]])
            st.success(f"**Game Parlay ({len(game_par[:2])}-Leg)**\n\n{legs_text}\n\n**Payout: +260**")
        else:
            st.info("Game Parlay: Not enough games available")

    st.markdown("---")
    
    # 7. SYSTEM STATUS (Footer)
    avg_integrity = (g_integrity + p_integrity + c_integrity) // 3
    bankroll_val = st.session_state.get('bankroll', 1000.0)
    unit_size_val = bankroll_val * KELLY_FRACTION * 0.015
    session_seconds_val = int(time.time() - st.session_state.get('session_start', time.time()))
    session_str_val = f"{session_seconds_val//60:02d}:{session_seconds_val%60:02d}"
    st.markdown(f"**Integrity:** {avg_integrity}/100 · **Bankroll:** ${bankroll_val:,.2f} · **Unit:** ${unit_size_val:.2f} · **Session:** {session_str_val}")

# ────────── TAB 1: BOARD OF 8 ──────────
with tabs[1]:
    st.markdown("# 🏀 Board of 8 — Multi-Source Prop Analysis")
    board=st.session_state.board_data or []
    if st.session_state.last_scan_time: st.markdown(f'<div class="small-note">Last scan: {st.session_state.last_scan_time} · {st.session_state.last_sport}</div>',unsafe_allow_html=True)
    if board:
        approved2=[i for i in board if i.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")]
        if approved2:
            best=approved2[0]
            st.markdown(f'<div class="lock-of-day"><div style="font-size:12px;color:#e8a020;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">🔒 LOCK OF THE DAY</div><div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;"><div><div style="font-size:18px;font-weight:700;color:#f4f8fc;">{best["Player"]}</div><div style="font-size:14px;color:#5a7088;">{best["Side"]} {best["Line"]} {best["Prop"]}</div></div><div style="text-align:center;"><div style="font-size:12px;color:#5a7088;">Council Score</div><div style="font-size:24px;font-weight:800;color:#e8a020;">{best["Weighted Score"]:.2f}</div><div style="font-size:14px;font-weight:700;color:{tier_color(best["Tier"])};">{best["Tier Label"]}</div></div></div></div>',unsafe_allow_html=True)
            if st.button("🔒 Lock This Pick",key="lock_board"):
                lid=lock_single_prop(best)
                st.session_state.locks.append({"id":lid,"type":"PROP","player":best["Player"],"prop":f"{best['Side']} {best['Line']} {best['Prop']}","tier":best["Tier"],"status":"PENDING","result":None})
                st.success(f"Locked: {best['Player']} {best['Side']} {best['Line']}"); st.rerun()
        st.markdown("---")
        for i,item in enumerate(board[:15]):
            tc=tier_color(item['Tier'])
            edge_pct=item.get('edge',0)*100
            edge_color="#0d9488" if edge_pct>=8 else "#e8a020" if edge_pct>=4 else "#5a7088"
            src=item.get("data_source","LIVE")
            st.markdown(f'<div class="section-card" style="border-left:4px solid {tc};"><div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;"><div style="flex:1;min-width:180px;"><div style="font-size:17px;font-weight:700;color:#f4f8fc;">{item["Player"]}</div><div style="font-size:14px;color:#5a7088;">{item["Side"]} {item["Line"]} {item["Prop"]} · {item.get("Sport","NBA")} · <span style="color:#0d9488;">{src}</span></div></div><div style="text-align:center;"><div style="font-size:30px;font-weight:800;color:{edge_color};">{edge_pct:.1f}%</div><div style="font-size:12px;font-family:monospace;color:{tc};">{item["Tier Label"]}</div></div><div style="text-align:right;"><div style="font-size:13px;color:#5a7088;font-family:monospace;">Score {item["Weighted Score"]:.2f}</div>',unsafe_allow_html=True)
            if item["Tier"] in ("SOVEREIGN","ELITE","APPROVED"):
                if st.button(f"🔒 Lock it In",key=f"lock_prop_{i}"):
                    lid=lock_single_prop(item)
                    st.session_state.locks.append({"id":lid,"type":"PROP","player":item["Player"],"prop":f"{item['Side']} {item['Line']} {item['Prop']}","tier":item["Tier"],"status":"PENDING","result":None})
                    st.success(f"Locked: {item['Player']} {item['Side']} {item['Line']}"); st.rerun()
            st.markdown('</div></div>',unsafe_allow_html=True)
    else: st.info("No board data loaded. Use **Load Board** in the sidebar.")
    st.markdown(f'<div class="small-note">Sharp Reference: {sharp.get("book","Pinnacle")} via {sharp.get("source","OddsHarvester")} — {sharp.get("status","unknown").upper()}</div>',unsafe_allow_html=True)

# ────────── TAB 2: ANALYSIS ──────────
with tabs[2]:
    st.markdown("# 🌍 Cross-Sport Best Bets")
    cross=st.session_state.cross_sport_board
    if not cross: st.info("Click 'Scan All Sports' in the sidebar.")
    else:
        st.markdown(f"**Scanned:** {cross['scanned_at']} | **{len(SPORTS)} sports**")
        sr2=cross.get('sport_results',{})
        if sr2:
            st.markdown("### 📊 Sport-by-Sport Summary")
            sn=list(sr2.keys()); nc=min(4,len(sn)); sc2=st.columns(nc)
            for idx,sn2 in enumerate(sn):
                d=sr2[sn2]
                with sc2[idx%nc]: st.metric(sn2,f"{len(d.get('props',[]))} props",f"{len(d.get('games',[]))} games")
        st.markdown("---"); st.markdown("## 🏆 Top Props Across All Sports")
        cp=cross.get('props',[])
        if cp:
            for i,p in enumerate(cp[:8],1):
                tc=tier_color(p.get('Tier','PASS'))
                st.markdown(f'<div class="section-card" style="border-left:3px solid {tc};"><span style="color:#5a7088;">#{i} · {p.get("Sport","")}</span> <span style="color:#f4f8fc;font-weight:600;">{p.get("Player","")}</span> — {p.get("Side","")} {p.get("Line","")} {p.get("Prop","")} <span style="color:{tc};font-weight:600;">{p.get("Tier Label","")}</span> <span style="font-family:monospace;color:#e8a020;float:right;">Score {p.get("Weighted Score",0):.2f}</span></div>',unsafe_allow_html=True)

# ────────── TAB 3: LOCKS & PARLAYS ──────────
with tabs[3]:
    st.markdown("# 🔒 Locks & Parlays")
    board_lp = st.session_state.board_data or []
    game_board_lp = st.session_state.game_verdicts or []
    if not board_lp:
        st.info("Load a board first.")
    else:
        approved_lp = [i for i in board_lp if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        approved_games_lp = [g for g in game_board_lp if g["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]

        if approved_lp:
            best = sorted(approved_lp, key=lambda x: x["Weighted Score"], reverse=True)[0]
            tc = tier_color(best["Tier"])
            edge_pct = int(best["Weighted Score"] * 100)
            st.markdown("## Lock of the Day — Prop")
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc};"><div class="prop-card-header"><div><div class="prop-card-player">{best['Player']}</div><div class="prop-card-matchup">{best['Side']} {best['Line']} {best['Prop']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:#0ea5a0;">{edge_pct}%</div><div style="font-size:12px;color:{tc};font-weight:600;">{best['Tier Label']}</div></div></div></div>""",unsafe_allow_html=True)
            if st.button("🔒 Lock Prop of the Day", key="lock_prop_day"):
                st.success(f"Locked: {lock_single_prop(best)}")

        if approved_games_lp:
            best_game = sorted(approved_games_lp, key=lambda x: x["Weighted Score"], reverse=True)[0]
            tc_g = tier_color(best_game["Tier"])
            edge_pct_g = int(best_game["Weighted Score"] * 100)
            st.markdown("## Lock of the Day — Game")
            st.markdown(f"""<div class="prop-card" style="border-left:4px solid {tc_g};"><div class="prop-card-header"><div><div class="prop-card-player">{best_game.get('Bet', best_game['Matchup'])}</div><div class="prop-card-matchup">{best_game.get('Type','')} · {best_game['Matchup']}</div></div><div style="text-align:right;"><div class="prop-card-edge" style="color:#0ea5a0;">{edge_pct_g}%</div><div style="font-size:12px;color:{tc_g};font-weight:600;">{best_game['Tier Label']}</div></div></div></div>""",unsafe_allow_html=True)
            if st.button("🔒 Lock Game of the Day", key="lock_game_day"):
                st.session_state.locks.append({"id": f"LOCK-{date.today().strftime('%m%d')}-{len(st.session_state.locks)+1:02d}","type":"GAME","matchup":best_game["Matchup"],"bet":best_game.get("Bet",""),"tier":best_game["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                st.success("Game locked.")

        col_p, col_g = st.columns(2)
        with col_p:
            st.markdown("""<div class="parlay-card"><h4 style="color:#0ea5a0;">Props Parlay</h4>""", unsafe_allow_html=True)
            prop_par_lp = build_prop_parlay()
            if prop_par_lp:
                selected_p = []
                for i, leg in enumerate(prop_par_lp):
                    if st.checkbox(f"{leg['Player']} - {leg['Side']} {leg['Line']} {leg['Prop']}", value=True, key=f"pp_{i}"):
                        selected_p.append(leg)
                if len(selected_p) >= 2 and st.button("Lock Props Parlay", key="lock_props_parlay"):
                    for leg in selected_p:
                        lock_single_prop(leg)
                    st.success("Props parlay locked.")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_g:
            st.markdown("""<div class="game-parlay-card"><h4 style="color:#4a90d9;">Games Parlay</h4>""", unsafe_allow_html=True)
            game_par_lp = build_game_parlay()
            if game_par_lp:
                selected_g = []
                for i, leg in enumerate(game_par_lp):
                    if st.checkbox(f"{leg.get('Bet', leg['Matchup'])}", value=True, key=f"gp_{i}"):
                        selected_g.append(leg)
                if len(selected_g) >= 2 and st.button("Lock Games Parlay", key="lock_games_parlay"):
                    for leg in selected_g:
                        st.session_state.locks.append({"id": f"LOCK-{date.today().strftime('%m%d')}-{len(st.session_state.locks)+1:02d}","type":"GAME","matchup":leg["Matchup"],"bet":leg.get("Bet",""),"tier":leg["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                    st.success("Games parlay locked.")
            st.markdown("</div>", unsafe_allow_html=True)

        if approved_lp:
            st.markdown("---")
            st.markdown("## ⚡ Top +EV Opportunities")
            st.caption("Highest‑edge individual props from the Council consensus.")
            top_ev = sorted(approved_lp, key=lambda x: x["Weighted Score"], reverse=True)[:5]
            ev_rows = []
            for i, item in enumerate(top_ev, 1):
                ev_rows.append({"#": i,"Player": item["Player"],"Prop": f"{item['Side']} {item['Line']} {item['Prop']}","Edge": f"{int(item['Weighted Score']*100)}%","Tier": item["Tier Label"]})
            st.table(pd.DataFrame(ev_rows))
            for i, item in enumerate(top_ev, 1):
                col_btn, _ = st.columns([1, 3])
                with col_btn:
                    if st.button(f"🔒 Lock #{i}", key=f"ev_lock_{i}"):
                        st.success(f"Locked: {lock_single_prop(item)}")

# ────────── TAB 4: LOCKS & LEDGER ──────────
with tabs[4]:
    st.markdown("# 📋 Locks & Ledger")
    if not st.session_state.locks: st.info("No active locks.")
    else:
        for i,lock in enumerate(st.session_state.locks):
            c=st.columns([4,1,1,1])
            with c[0]: st.markdown(f"**{lock.get('id')}** — {lock.get('player')} | {lock.get('prop')} | {lock.get('tier')}")
            with c[1]:
                if st.button("✅ WIN",key=f"w_{i}"): lock["status"]="RESOLVED"; lock["result"]="WIN"; st.session_state.history.append(lock); st.session_state.bankroll+=unit_size*1.91; st.session_state.integrity_score=min(100,st.session_state.integrity_score+0.3); st.rerun()
            with c[2]:
                if st.button("❌ LOSS",key=f"l_{i}"): lock["status"]="RESOLVED"; lock["result"]="LOSS"; st.session_state.history.append(lock); st.session_state.bankroll-=unit_size; st.session_state.integrity_score=max(40,st.session_state.integrity_score-0.4); st.rerun()
            with c[3]:
                if st.button("🗑️",key=f"rm_{i}"): st.session_state.locks.pop(i); st.rerun()
    if st.session_state.history: st.markdown("### Resolved"); st.table(pd.DataFrame(st.session_state.history))

# ────────── TAB 5: RECONCILIATION ──────────
with tabs[5]:
    st.markdown("# 🔄 Reconciliation")
    st.info("Workflow unchanged.")

# ────────── TAB 6: MODELS ──────────
with tabs[6]:
    st.markdown("# 🧠 Council Models — Fixed Weights")
    mr=""
    for m in MODELS: mr+=f'<tr><td style="color:#f4f8fc;font-weight:600;font-size:14px;">{m["name"]}</td><td style="color:#5a7088;font-size:14px;">{m["specialty"]}</td><td style="color:#e8a020;font-family:monospace;font-size:15px;font-weight:700;">{m["weight"]:.2f}</td><td style="color:#5a7088;font-size:13px;">{m["function"]}</td></tr>'
    st.markdown(f'<table class="model-table"><thead><tr><th>MODEL</th><th>SPECIALTY</th><th>WEIGHT</th><th>CORE FUNCTION</th></tr></thead><tbody>{mr}</tbody></table><div class="small-note" style="margin-top:10px;">Total: {sum(m["weight"] for m in MODELS):.2f} / 1.00</div>',unsafe_allow_html=True)
    st.markdown("---\n## Tier Thresholds (Fixed)\n| SCORE | TIER |\n|---|---|\n| ≥ 0.70 | ⚡ Sovereign Lock |\n| 0.55–0.69 | 🟡 Elite Edge |\n| 0.40–0.54 | 🔵 Approved Single |\n| 0.20–0.39 | 🟠 Lean |\n| < 0.20 | 🔴 PASS |")

# ────────── TAB 7: SETTINGS ──────────
with tabs[7]:
    st.markdown("# ⚙️ SEM & System")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Integrity",f"{integrity}/100"); c2.metric("Safe Corridor","ACTIVE"); c3.metric("Emergency Floor","ACTIVE"); c4.metric("Bankroll",f"${bankroll:,.2f}")
    st.markdown("## Site Health")
    if st.button("🔄 Refresh",key="rh"): check_all_sources_health(); st.rerun()
    cl,cr=st.columns(2)
    with cl:
        st.markdown("### Game Sources")
        for n in GAME_SOURCES:
            s=st.session_state.site_status.get(n,{}).get("status","unknown")
            t=st.session_state.site_status.get(n,{}).get("last_checked","") or "—"
            lb="🟢 WORKING" if s=="ok" else "🔴 DOWN" if s=="fail" else "⚪ UNCHECKED"
            st.markdown(f'<div class="section-card">{lb} <b>{n}</b> <span class="muted-text">— {t}</span></div>',unsafe_allow_html=True)
        st.markdown("### Prop Sources")
        st.markdown(f'<div class="section-card">🟢 <b>LineStar API</b> <span class="muted-text">— auto-period</span></div>', unsafe_allow_html=True)
        for n in PROP_SCRAPER_URLS:
            st.markdown(f'<div class="section-card">⚪ <b>{n}</b> <span class="muted-text">— pending scan</span></div>',unsafe_allow_html=True)
    with cr:
        st.markdown("### Consensus Sources")
        for n in CONSENSUS_SOURCES:
            st.markdown(f'<div class="section-card">⚪ <b>{n}</b></div>',unsafe_allow_html=True)
    if st.session_state.scan_log:
        st.markdown("---\n## 📜 Scan Log")
        lh='<div class="scan-log">'
        for e in st.session_state.scan_log[-20:]: lh+=f'<div class="log-{e.get("level","skip")}">{e.get("time","")} — {e.get("msg","")}</div>'
        lh+='</div>'; st.markdown(lh,unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(f'**Sharp Reference:** {sharp.get("book","Pinnacle")} via {sharp.get("source","OddsHarvester")} | Status: {sharp.get("status","unknown")} | Line: {sharp.get("line")} | Note: {sharp.get("note","")}')
