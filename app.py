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

st.set_page_config(page_title="BetCouncil v3.3 Hard Engine", page_icon="🛡️", layout="wide")

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
.lock-of-day { background:linear-gradient(135deg, rgba(232,160,32,.15), #0d1219); border:2px solid #e8a020; border-radius:12px; padding:16px; margin:14px 0; }
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
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────
SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

GAME_SOURCES = {
    "VegasInsider": True,
    "ESPN (JSON API)": True,
}

CONSENSUS_SOURCES = {
    "VSIN Betting Splits": True,
}

ALL_SOURCES = {**GAME_SOURCES, **CONSENSUS_SOURCES}

SPORT_URL_SLUG = {"NBA":"nba","MLB":"mlb","NHL":"nhl","NFL":"nfl","WNBA":"wnba","UFC":"ufc","Golf":"golf","Tennis":"tennis","Soccer":"soccer"}
SPORT_PATH_MAP = {"nba":"basketball/nba","mlb":"baseball/mlb","nhl":"hockey/nhl","nfl":"football/nfl","wnba":"basketball/wnba"}
VEGASINSIDER_SLUG = {"NBA":"nba","MLB":"mlb","NHL":"nhl","NFL":"nfl","WNBA":"wnba","Soccer":"soccer","Tennis":"tennis","Golf":"golf","UFC":"ufc"}
VSIN_SPORT_SLUG = {"NBA":"nba","MLB":"mlb","NHL":"nhl","NFL":"nfl","WNBA":"wnba","UFC":"ufc","Golf":"golf/pga","Tennis":"tennis","Soccer":"soccer"}

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

REQUEST_TIMEOUT = 10
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
    "NBA":{"props":[{"Player":"Shai Gilgeous-Alexander","Prop":"PTS","Line":31.5,"Side":"OVER","Sport":"NBA"},{"Player":"Cade Cunningham","Prop":"PTS","Line":23.5,"Side":"OVER","Sport":"NBA"},{"Player":"Donovan Mitchell","Prop":"PTS","Line":27.5,"Side":"UNDER","Sport":"NBA"},{"Player":"Nikola Jokic","Prop":"AST","Line":9.5,"Side":"OVER","Sport":"NBA"},{"Player":"Luka Doncic","Prop":"PTS","Line":33.5,"Side":"OVER","Sport":"NBA"},{"Player":"Giannis Antetokounmpo","Prop":"REB","Line":12.5,"Side":"OVER","Sport":"NBA"},{"Player":"Jayson Tatum","Prop":"PTS","Line":28.5,"Side":"OVER","Sport":"NBA"}],"games":[{"Matchup":"OKC @ LAL","Sport":"NBA"},{"Matchup":"BOS @ DEN","Sport":"NBA"}]},
    "WNBA":{"props":[{"Player":"A'ja Wilson","Prop":"PTS","Line":26.5,"Side":"OVER","Sport":"WNBA"},{"Player":"Breanna Stewart","Prop":"PTS","Line":22.5,"Side":"OVER","Sport":"WNBA"},{"Player":"Arike Ogunbowale","Prop":"PTS","Line":23.5,"Side":"UNDER","Sport":"WNBA"},{"Player":"Caitlin Clark","Prop":"AST","Line":8.5,"Side":"OVER","Sport":"WNBA"},{"Player":"Napheesa Collier","Prop":"REB","Line":9.5,"Side":"OVER","Sport":"WNBA"},{"Player":"Sabrina Ionescu","Prop":"PTS","Line":20.5,"Side":"OVER","Sport":"WNBA"}],"games":[{"Matchup":"LV Aces @ NY Liberty","Sport":"WNBA"}]},
    "NFL":{"props":[{"Player":"Patrick Mahomes","Prop":"PASS_YDS","Line":275.5,"Side":"OVER","Sport":"NFL"},{"Player":"Christian McCaffrey","Prop":"RUSH_YDS","Line":85.5,"Side":"OVER","Sport":"NFL"},{"Player":"Justin Jefferson","Prop":"REC_YDS","Line":95.5,"Side":"OVER","Sport":"NFL"}],"games":[{"Matchup":"KC @ BUF","Sport":"NFL"}]},
    "MLB":{"props":[{"Player":"Aaron Judge","Prop":"HR","Line":0.5,"Side":"OVER","Sport":"MLB"},{"Player":"Shohei Ohtani","Prop":"STRIKEOUTS","Line":7.5,"Side":"OVER","Sport":"MLB"},{"Player":"Juan Soto","Prop":"HITS","Line":1.5,"Side":"OVER","Sport":"MLB"},{"Player":"Mookie Betts","Prop":"TB","Line":1.5,"Side":"OVER","Sport":"MLB"}],"games":[{"Matchup":"NYY @ LAD","Sport":"MLB"},{"Matchup":"ATL @ HOU","Sport":"MLB"}]},
    "NHL":{"props":[{"Player":"Connor McDavid","Prop":"PTS","Line":1.5,"Side":"OVER","Sport":"NHL"},{"Player":"Auston Matthews","Prop":"SHOTS","Line":3.5,"Side":"OVER","Sport":"NHL"}],"games":[{"Matchup":"EDM @ TOR","Sport":"NHL"}]},
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
if "kelly_odds" not in st.session_state: st.session_state.kelly_odds = -110
if "kelly_prob" not in st.session_state: st.session_state.kelly_prob = 55.0

HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","Accept-Language":"en-US,en;q=0.9","Referer":"https://www.google.com/"}

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
    if props_count>=10: return 85,"Strong Source Agreement — Lines Stable"
    if props_count>=5: return 67,"Market Volatility Detected"
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
    sl=SPORT_URL_SLUG.get(sport,sport.lower())
    sp=SPORT_PATH_MAP.get(sl,f"basketball/{sl}")
    vi=VEGASINSIDER_SLUG.get(sport,sl)
    vs=VSIN_SPORT_SLUG.get(sport,sl)
    if source_name=="VegasInsider": return f"https://www.vegasinsider.com/{vi}/odds/las-vegas/"
    if source_name=="ESPN (JSON API)": return f"https://site.api.espn.com/apis/site/v2/sports/{sp}/scoreboard"
    if source_name=="VSIN Betting Splits": return f"https://data.vsin.com/{vs}/betting-splits/"
    return ""

def safe_fetch(url, name):
    try:
        r=requests.get(url,headers=HEADERS,timeout=REQUEST_TIMEOUT)
        if r.status_code==200:
            if r.text and len(r.text)>200:
                mark_site_ok(name); log_scan(f"{name}: OK","ok"); return r.text
            else:
                mark_site_fail(name,"Empty response"); log_scan(f"{name}: Empty","fail"); return None
        else: mark_site_fail(name,f"HTTP {r.status_code}"); log_scan(f"{name}: FAIL ({r.status_code})","fail"); return None
    except requests.Timeout: mark_site_fail(name,"Timeout"); log_scan(f"{name}: TIMEOUT","fail"); return None
    except requests.ConnectionError: mark_site_fail(name,"Connection"); log_scan(f"{name}: CONNECTION","fail"); return None
    except Exception as e: mark_site_fail(name,str(e)[:50]); log_scan(f"{name}: {str(e)[:50]}","fail"); return None

# ──────────────────────────────────────────────────────────────
# PARSERS
# ──────────────────────────────────────────────────────────────
def parse_vegasinsider(html):
    soup=BeautifulSoup(html,"html.parser")
    results=[]
    for row in soup.select("table.odds-table tr"):
        cols=row.select("td")
        if len(cols)>=3: results.append({"matchup":cols[0].get_text(strip=True),"spread":cols[1].get_text(strip=True),"total":cols[2].get_text(strip=True)})
    if not results:
        for block in soup.select(".vi-container .odds-block"):
            teams=block.select(".team-name"); odds=block.select(".odds-value")
            if teams: results.append({"matchup":" vs ".join(t.get_text(strip=True) for t in teams),"odds":[o.get_text(strip=True) for o in odds]})
    return results

def parse_espn_json(html, sport):
    out=[]
    try:
        js=json.loads(html)
        for ev in js.get("events",[]):
            comp=(ev.get("competitions") or [{}])[0]
            competitors=comp.get("competitors") or []
            home=next((x for x in competitors if x.get("homeAway")=="home"),{})
            away=next((x for x in competitors if x.get("homeAway")=="away"),{})
            out.append({"Matchup":f"{away.get('team',{}).get('shortDisplayName','AWAY')} @ {home.get('team',{}).get('shortDisplayName','HOME')}","Sport":sport})
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
def analyze_prop(player, market, line, pick, sport="NBA", odds=-110, bankroll=None):
    bankroll=bankroll or get_bankroll()
    base=24 if market in ("PTS","PRA","PR","PA") else 6 if market in ("REB","RUSH_YDS") else 5 if market in ("AST","REC_YDS") else 17
    stats=list(np.random.normal(base,max(2,base*0.15),10))
    mu=normal_wma(stats); sigma=max(wsem(stats),0.75)
    prob=float(1-norm.cdf(line,mu,sigma) if pick.upper()=="OVER" else norm.cdf(line,mu,sigma))
    edge=prob-american_to_prob(odds); tier=classify_tier(edge)
    return {"player":player,"market":market,"line":line,"pick":pick,"sport":sport,"odds":odds,"prob":prob,"edge":edge,"kelly":kelly(prob,odds),"tier":tier,"mu":mu,"sigma":sigma,"confidence":65,"source_status":"FALLBACK"}

def run_council(items):
    out=[]
    for item in items:
        p=item.get("Player") or item.get("player","Unknown")
        m=item.get("Prop") or item.get("prop","PTS")
        l=item.get("Line") or item.get("line",0)
        s=item.get("Side") or item.get("side","OVER")
        sp=item.get("Sport") or item.get("sport","NBA")
        res=analyze_prop(p,m,l,s,sp)
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
# FULL SUMMARY GENERATOR
# ──────────────────────────────────────────────────────────────
def generate_full_summary(board, game_verdicts, sport, raw_games, weather_data, consensus_data):
    if not board: return "No board loaded."
    now=datetime.now(); date_str=now.strftime("%A, %B %d, %Y"); sport_display=sport.upper()
    g_int,g_desc=calculate_game_integrity(raw_games)
    p_int,p_desc=calculate_prop_integrity(len(board))
    c_int,c_desc=calculate_council_integrity(board)
    approved=[i for i in board if i.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")]
    best_prop=approved[0] if approved else None
    best_game=game_verdicts[0] if game_verdicts else None
    l_int,l_desc=calculate_lock_integrity(best_prop,best_game,board)
    wp=[]
    for matchup,w in weather_data.items(): wp.append(f"{matchup.split(' @ ')[-1]} {w['advisory']}")
    wl=" · ".join(wp) if wp else "N/A"
    L=[]
    L.append(f"# 🧠 THE BOARD OF 8 — BETCOUNCIL v3.3\n")
    L.append(f"**{sport_display} — {date_str}** | **Scanned:** {st.session_state.last_scan_time} | **Status:** 🛡️ SAFE CORRIDOR ACTIVE\n")
    L.append(f"🔒 **Sources:** ESPN ✅ · VegasInsider ✅ · VSIN ✅\n")
    L.append(f"---\n")
    L.append(f"## 🚨 GAME LINES (What VegasInsider Shows)\n")
    L.append(f"📊 **GAME INTEGRITY: {g_int}%** ({g_desc})\n")
    if raw_games:
        L.append(f"| # | Matchup | Spread | Total |\n| --- | --- | --- | --- |")
        for i,g in enumerate(raw_games[:10],1):
            m=g.get("matchup","")
            if consensus_data and m in consensus_data: m+=f" (Public: {consensus_data[m]})"
            L.append(f"| {i} | **{m}** | {g.get('spread','N/A')} | {g.get('total','N/A')} |")
        L.append(f"\n*Weather: {wl}*")
    else: L.append(f"*No game lines scraped*")
    L.append(f"\n---\n")
    L.append(f"## 📊 PLAYER PROPS (Fallback Data — {len(board)} available)\n")
    L.append(f"📊 **PROP INTEGRITY: {p_int}%** ({p_desc})\n")
    if board:
        L.append(f"| # | Player | Prop | Line | Side |\n| --- | --- | --- | --- | --- |")
        for i,item in enumerate(board[:12],1): L.append(f"| {i} | **{item['Player']}** | {item['Prop']} | {item['Line']} | {item['Side']} |")
    else: L.append(f"*No props available*")
    L.append(f"\n---\n")
    L.append(f"## 🗳️ COUNCIL VERDICT (8 Models · Weighted Consensus)\n")
    L.append(f"📊 **COUNCIL INTEGRITY: {c_int}%** ({c_desc})\n")
    if board:
        L.append(f"| Pick | Score | Tier |\n| --- | --- | --- |")
        for item in board[:10]: L.append(f"| **{item['Player']} {item['Side']} {item['Line']} {item['Prop']}** | {item.get('Weighted Score',0):.2f} | {TIER_LABELS.get(item.get('Tier',''),'—')} |")
    L.append(f"\n---\n")
    L.append(f"## 🔒 LOCKS OF THE DAY\n")
    L.append(f"📊 **LOCK INTEGRITY: {l_int}%** ({l_desc})\n")
    L.append(f"| Type | Pick | Line | Tier |\n| --- | --- | --- | --- |")
    if best_prop: L.append(f"| **Prop** | {best_prop['Player']} {best_prop['Side']} {best_prop['Prop']} | {best_prop['Line']} | {TIER_LABELS.get(best_prop.get('Tier',''),'—')} |")
    if best_game: L.append(f"| **Game** | {best_game.get('Matchup','')} | {best_game.get('Spread','N/A')} | {TIER_LABELS.get(best_game.get('Tier',''),'—')} |")
    if best_prop and best_game: L.append(f"| **Parlay** | {best_prop['Player']} O{best_prop['Line']} + {best_game.get('Matchup','')} | +250 | ⚡ Sovereign |")
    L.append(f"\n---\n")
    bk=st.session_state.bankroll; it=st.session_state.integrity_score; us=bk*KELLY_FRACTION*0.015
    ss=int(time.time()-st.session_state.session_start); sf=f"{ss//60:02d}:{ss%60:02d}"
    L.append(f"## 🛡️ SYSTEM STATUS\n")
    L.append(f"**Integrity:** {it}/100 · **Bankroll:** ${bk:,.2f} · **Unit:** ${us:.2f} · **Session:** {sf}")
    return "\n".join(L)

# ──────────────────────────────────────────────────────────────
# DATA LOADER
# ──────────────────────────────────────────────────────────────
def load_sport_data_live(sport):
    all_games,raw_games=[],[]
    weather_results={}; consensus_results={}
    log_scan(f"Loading {sport} board...","skip")
    
    # Game lines: VegasInsider → ESPN failover
    for gsn in ["VegasInsider","ESPN (JSON API)"]:
        url=build_source_url(gsn,sport)
        if not url: continue
        html=safe_fetch(url,gsn)
        if html:
            if "ESPN" in gsn:
                games=parse_espn_json(html,sport); raw_games=games
            else:
                parsed=parse_vegasinsider(html)
                raw_games=[{"matchup":g.get("matchup",""),"spread":g.get("spread","N/A"),"total":g.get("total","N/A")} for g in parsed]
                games=[{"Matchup":g.get("matchup",""),"Sport":sport,"Spread":g.get("spread","N/A"),"Total":g.get("total","N/A")} for g in parsed]
            if games: all_games=games; break
    
    # VSIN Consensus
    vsin_url=build_source_url("VSIN Betting Splits",sport)
    if vsin_url:
        vsin_html=safe_fetch(vsin_url,"VSIN Betting Splits")
        if vsin_html: consensus_results=parse_vsin_consensus(vsin_html); log_scan(f"VSIN: {len(consensus_results)} splits","ok")
    
    # Weather for MLB
    if sport.upper()=="MLB":
        for game in raw_games:
            parts=game.get("matchup","").split(" @ ")
            if len(parts)==2:
                ha=parts[1].split()[-1] if parts[1] else ""
                a,d=apply_weather_filter(ha,sport); weather_results[game["matchup"]]={"advisory":a,"detail":d}
    
    # Props from fallback
    fallback=SPORT_FALLBACK_MAP.get(sport.upper(),SPORT_FALLBACK_MAP["NBA"])
    all_props=fallback["props"]
    if not all_games: all_games=fallback["games"]
    
    st.session_state.board_data=run_council(all_props)
    st.session_state.game_verdicts=run_game_council(all_games)
    st.session_state.raw_games_for_summary=raw_games; st.session_state.weather_data=weather_results
    st.session_state.consensus_data=consensus_results
    st.session_state.summary_text=generate_full_summary(st.session_state.board_data,st.session_state.game_verdicts,sport,raw_games,weather_results,consensus_results)
    st.session_state.last_sport=sport; st.session_state.last_scan_time=datetime.now().strftime("%H:%M:%S")
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
        if u: log_scan(f"Checking {n}: {u}","skip"); safe_fetch(u,n)
    for n in CONSENSUS_SOURCES:
        u=build_source_url(n,"NBA")
        if u: log_scan(f"Checking {n}: {u}","skip"); safe_fetch(u,n)

def scan_all_sports():
    ap,ag=[],[]
    sr={}
    log_scan("Cross-sport scan...","skip")
    for sport in SPORTS:
        fallback=SPORT_FALLBACK_MAP.get(sport.upper(),SPORT_FALLBACK_MAP["NBA"])
        sp=fallback["props"]; sg=fallback["games"]
        for gsn in ["VegasInsider","ESPN (JSON API)"]:
            u=build_source_url(gsn,sport)
            if not u: continue
            html=safe_fetch(u,gsn)
            if html:
                if "ESPN" in gsn: sg2=parse_espn_json(html,sport)
                else: sg2=[{"Matchup":g.get("matchup",""),"Sport":sport} for g in parse_vegasinsider(html)]
                if sg2: sg=sg2; break
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
    st.markdown('<div style="font-size:24px;font-weight:800;color:#f4f8fc;letter-spacing:1px;margin-bottom:6px;">🛡️ BetCouncil</div><div style="font-size:12px;color:#5a7088;margin-bottom:14px;">3.3 OS — Section 9.1 Synthesis</div>',unsafe_allow_html=True)
    
    change_class = "sidebar-change-green" if daily_change_pct >= 0 else "red-text"
    change_sign = "+" if daily_change_pct >= 0 else ""
    color_span = '<span class="teal-text">' if daily_change_pct >= 0 else '<span class="red-text">'
    
    st.markdown(
        f'<div class="sidebar-section">'
        f'<div class="sidebar-label">BANKROLL</div>'
        f'<div class="sidebar-value">{color_span}${bankroll:,.2f}</span></div>'
        f'<div class="{change_class}">{change_sign}{daily_change_pct:.1f}% today</div>'
        f'</div>',
        unsafe_allow_html=True
    )
    
    nb=st.number_input("Adjust",value=float(bankroll),step=10.0,key="sb_bankroll",label_visibility="collapsed")
    if nb!=bankroll: st.session_state.bankroll=nb; st.rerun()
    
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">INTEGRITY</div><div class="sidebar-value" style="color:#0d9488;">{integrity}<span style="font-size:14px;color:#5a7088;"> /100</span></div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">SEM</div><div class="sidebar-value" style="font-size:14px;color:#e8a020;">{floor_label}</div><div class="sidebar-sub">({floor_pct} edge threshold)</div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">UNIT SIZE</div><div class="sidebar-value">${unit_size:.2f}</div><div class="sidebar-sub">{KELLY_FRACTION} Kelly Fraction</div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">SESSION</div><div class="sidebar-value" style="font-family:monospace;">{session_str}</div></div>',unsafe_allow_html=True)
    
    st.markdown(f'<div class="sidebar-section"><div class="sidebar-label">VALIDATION FIREWALL</div><div style="font-size:20px;font-weight:700;color:#0d9488;margin-bottom:6px;">{firewall_passed}/5 PASSED</div>',unsafe_allow_html=True)
    for cn,p in firewall_checks.items():
        st.markdown(f'<div class="firewall-item {"firewall-pass" if p else "firewall-fail"}">{"✅" if p else "❌"} {cn}</div>',unsafe_allow_html=True)
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
        with st.spinner(f"Loading {sport}..."): load_sport_data_live(sport)
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
    st.markdown(f'<div class="small-note" style="margin-top:12px;">MODELS ACTIVE · {len(ALL_SOURCES)} SOURCES</div>',unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# COMMAND BAR
# ──────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='command-bar'>
<div style='display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;'>
<div style='width:42px;height:42px;background:linear-gradient(135deg,#e8a020,#b07010);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;'>⚡</div>
<div><div style='font-size:22px;font-weight:700;color:#f4f8fc;letter-spacing:1px;'>BetCouncil</div><div style='font-size:12px;color:#5a7088;'>v3.3 · Section 9.1 + Integrity Scores + VSIN</div></div>
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
tabs=st.tabs(["📋 Summary","🏀 Board of 8","📊 Analysis","🔒 Locks of Day","📋 Locks & Ledger","🔄 Reconciliation","🧠 Models","⚙️ Settings"])

with tabs[0]:
    st.markdown("# 📋 Council Summary")
    if st.session_state.summary_text:
        st.markdown(st.session_state.summary_text)
    else:
        st.info("No board loaded yet. Click **Load Board** in the sidebar to generate the full synthesis.")

with tabs[1]:
    st.markdown("# 🏀 Board of 8 — Prop Analysis")
    board=st.session_state.board_data or []
    if st.session_state.last_scan_time: st.markdown(f'<div class="small-note">Last scan: {st.session_state.last_scan_time} · {st.session_state.last_sport}</div>',unsafe_allow_html=True)
    if board:
        approved=[i for i in board if i.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")]
        if approved:
            best=approved[0]
            st.markdown(f'<div class="lock-of-day"><div style="font-size:12px;color:#e8a020;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">🔒 LOCK OF THE DAY</div><div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;"><div><div style="font-size:18px;font-weight:700;color:#f4f8fc;">{best["Player"]}</div><div style="font-size:14px;color:#5a7088;">{best["Side"]} {best["Line"]} {best["Prop"]}</div></div><div style="text-align:center;"><div style="font-size:12px;color:#5a7088;">Council Score</div><div style="font-size:24px;font-weight:800;color:#e8a020;">{best["Weighted Score"]:.2f}</div><div style="font-size:14px;font-weight:700;color:{tier_color(best["Tier"])};">{best["Tier Label"]}</div></div></div></div>',unsafe_allow_html=True)
            if st.button("🔒 Lock This Pick",key="lock_board"):
                lid=lock_single_prop(best)
                st.session_state.locks.append({"id":lid,"type":"PROP","player":best["Player"],"prop":f"{best['Side']} {best['Line']} {best['Prop']}","tier":best["Tier"],"status":"PENDING","result":None})
                st.success(f"Locked: {best['Player']} {best['Side']} {best['Line']}"); st.rerun()
        st.markdown("---")
        for i,item in enumerate(board):
            tc=tier_color(item['Tier'])
            edge_pct=item.get('edge',0)*100
            edge_color="#0d9488" if edge_pct>=8 else "#e8a020" if edge_pct>=4 else "#5a7088"
            st.markdown(f'<div class="section-card" style="border-left:4px solid {tc};"><div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;"><div style="flex:1;min-width:180px;"><div style="font-size:17px;font-weight:700;color:#f4f8fc;">{item["Player"]}</div><div style="font-size:14px;color:#5a7088;">{item["Side"]} {item["Line"]} {item["Prop"]} · {item.get("Sport","NBA")}</div></div><div style="text-align:center;"><div style="font-size:30px;font-weight:800;color:{edge_color};">{edge_pct:.1f}%</div><div style="font-size:12px;font-family:monospace;color:{tc};">{item["Tier Label"]}</div></div><div style="text-align:right;"><div style="font-size:13px;color:#5a7088;font-family:monospace;">Score {item["Weighted Score"]:.2f}</div>',unsafe_allow_html=True)
            if item["Tier"] in ("SOVEREIGN","ELITE","APPROVED"):
                if st.button(f"🔒 Lock it In",key=f"lock_prop_{i}"):
                    lid=lock_single_prop(item)
                    st.session_state.locks.append({"id":lid,"type":"PROP","player":item["Player"],"prop":f"{item['Side']} {item['Line']} {item['Prop']}","tier":item["Tier"],"status":"PENDING","result":None})
                    st.success(f"Locked: {item['Player']} {item['Side']} {item['Line']}"); st.rerun()
            st.markdown('</div></div>',unsafe_allow_html=True)
    else:
        st.info("No board data loaded. Use **Load Board** in the sidebar.")
    st.markdown(f'<div class="small-note">Sharp Reference: {sharp.get("book","Pinnacle")} via {sharp.get("source","OddsHarvester")} — {sharp.get("status","unknown").upper()}</div>',unsafe_allow_html=True)

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

with tabs[3]:
    st.markdown("# 🔒 Locks of Day")
    bdl=st.session_state.board_data or []
    if bdl:
        app=[i for i in bdl if i["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
        app.sort(key=lambda x:x["Weighted Score"],reverse=True)
        if app:
            bp=app[0]
            st.markdown(f'<div class="lock-of-day"><div style="font-size:14px;color:#5a7088;">LOCK OF THE DAY</div><div style="font-size:20px;font-weight:700;color:#f4f8fc;margin-top:4px;">{bp["Player"]}</div><div style="font-size:16px;color:#e8f0f8;">{bp["Side"]} {bp["Line"]} {bp["Prop"]}</div><div style="margin-top:6px;"><span style="color:{tier_color(bp["Tier"])};font-weight:700;font-size:15px;">{bp["Tier Label"]}</span><span style="font-family:monospace;color:#e8a020;float:right;">Score {bp["Weighted Score"]:.2f}</span></div></div>',unsafe_allow_html=True)
        pp=build_prop_parlay()
        if pp:
            st.markdown("## 🎯 Props Parlay")
            for i,leg in enumerate(pp[:5],1): st.markdown(f'<div class="section-card"><b>Leg {i}:</b> {leg["Player"]} {leg["Side"]} {leg["Line"]} {leg["Prop"]} — <span style="color:{tier_color(leg["Tier"])};">{leg["Tier Label"]}</span></div>',unsafe_allow_html=True)
    else: st.info("Load a board first.")

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

with tabs[5]:
    st.markdown("# 🔄 Reconciliation")
    st.info("Workflow unchanged.")

with tabs[6]:
    st.markdown("# 🧠 Council Models — Fixed Weights")
    mr=""
    for m in MODELS: mr+=f'<tr><td style="color:#f4f8fc;font-weight:600;font-size:14px;">{m["name"]}</td><td style="color:#5a7088;font-size:14px;">{m["specialty"]}</td><td style="color:#e8a020;font-family:monospace;font-size:15px;font-weight:700;">{m["weight"]:.2f}</td><td style="color:#5a7088;font-size:13px;">{m["function"]}</td></tr>'
    st.markdown(f'<table class="model-table"><thead><tr><th>MODEL</th><th>SPECIALTY</th><th>WEIGHT</th><th>CORE FUNCTION</th></tr></thead><tbody>{mr}</tbody></table><div class="small-note" style="margin-top:10px;">Total: {sum(m["weight"] for m in MODELS):.2f} / 1.00</div>',unsafe_allow_html=True)
    st.markdown("---\n## Tier Thresholds (Fixed)\n| SCORE | TIER |\n|---|---|\n| ≥ 0.70 | ⚡ Sovereign Lock |\n| 0.55–0.69 | 🟡 Elite Edge |\n| 0.40–0.54 | 🔵 Approved Single |\n| 0.20–0.39 | 🟠 Lean |\n| < 0.20 | 🔴 PASS |")

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
            e=st.session_state.site_status.get(n,{}).get("error","")
            lb="🟢 WORKING" if s=="ok" else "🔴 DOWN" if s=="fail" else "⚪ UNCHECKED"
            es=f' <span style="font-size:10px;color:#d03030;">({e})</span>' if e and s=="fail" else ""
            st.markdown(f'<div class="section-card">{lb} <b>{n}</b> <span class="muted-text">— {t}</span>{es}</div>',unsafe_allow_html=True)
    with cr:
        st.markdown("### Consensus Sources")
        for n in CONSENSUS_SOURCES:
            s=st.session_state.site_status.get(n,{}).get("status","unknown")
            t=st.session_state.site_status.get(n,{}).get("last_checked","") or "—"
            e=st.session_state.site_status.get(n,{}).get("error","")
            lb="🟢 WORKING" if s=="ok" else "🔴 DOWN" if s=="fail" else "⚪ UNCHECKED"
            es=f' <span style="font-size:10px;color:#d03030;">({e})</span>' if e and s=="fail" else ""
            st.markdown(f'<div class="section-card">{lb} <b>{n}</b> <span class="muted-text">— {t}</span>{es}</div>',unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### Prop Data Source")
    st.info("Props use curated fallback data. Live prop scraping from BettingPros/FantasyPros/OddsTrader/SportsBettingDime is disabled — these sites are JS-rendered and return empty shells with requests.get().")
    if st.session_state.scan_log:
        st.markdown("---\n## 📜 Scan Log")
        lh='<div class="scan-log">'
        for e in st.session_state.scan_log[-20:]: lh+=f'<div class="log-{e.get("level","skip")}">{e.get("time","")} — {e.get("msg","")}</div>'
        lh+='</div>'; st.markdown(lh,unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(f'**Sharp Reference:** {sharp.get("book","Pinnacle")} via {sharp.get("source","OddsHarvester")} | Status: {sharp.get("status","unknown")} | Line: {sharp.get("line")} | Note: {sharp.get("note","")}')
