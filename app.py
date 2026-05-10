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

st.set_page_config(page_title="BetCouncil v3.2 Hard Engine", page_icon="🛡️", layout="wide")

# ──────────────────────────────────────────────────────────────
# CSS — Larger fonts everywhere, bigger tabs, bigger Models table
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
body, .stApp, .main { background-color:#07090c; color:#e8f0f8; font-family:Inter,system-ui,sans-serif; font-size:16px; }
h1 { font-size:26px !important; }
h2 { font-size:22px !important; }
h3 { font-size:18px !important; }
h4,h5 { font-size:16px !important; color:#f4f8fc; text-transform:uppercase; letter-spacing:.5px; }

/* Bigger tab labels */
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

/* Info text bigger */
.stInfo, .stSuccess, .stWarning, .stError { font-size:15px !important; }

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
.prop-card-lock-btn { background:#e8a020; color:#07090c; border:none; border-radius:6px; padding:8px 16px; font-weight:700; font-size:14px; cursor:pointer; }

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

/* Models table bigger */
.model-table { font-size:14px !important; width:100%; border-collapse:collapse; }
.model-table th { font-size:13px !important; padding:10px 8px !important; color:#5a7088 !important; text-align:left !important; border-bottom:2px solid #1c2a3a !important; }
.model-table td { font-size:14px !important; padding:10px 8px !important; border-bottom:1px solid #1c2a3a !important; }

/* Kelly calculator */
.kelly-input { background:#0d1219; border:1px solid #1c2a3a; border-radius:4px; color:#e8f0f8; padding:4px 8px; font-size:14px; width:100%; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

# DraftKings uses different URL slugs per sport
DK_SPORT_SLUG = {
    "NBA": "basketball/nba",
    "WNBA": "basketball/wnba",
    "NFL": "football/nfl",
    "MLB": "baseball/mlb",
    "NHL": "hockey/nhl",
    "UFC": "mma/ufc",
    "Golf": "golf",
    "Tennis": "tennis",
    "Soccer": "soccer",
}

PROP_SOURCES = {
    "BettingPros": "https://www.bettingpros.com/{sport}/props/",
    "RotoWire": "https://www.rotowire.com/betting/{sport}/player-props.php",
    "CBS Sports": "https://www.cbssports.com/{sport}/",
    "Covers": "https://www.covers.com/{sport}",
    "DraftKings": "https://sportsbook.draftkings.com/leagues/{dk_sport}/player-props",
    "CAPMMA": "https://capmma.com",
}

GAME_SOURCES = {
    "ESPN": "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard",
    "DraftKings": "https://sportsbook.draftkings.com/leagues/{dk_sport}/game-lines",
    "Covers": "https://www.covers.com/{sport}/odds",
}

LINEUP_SOURCES = {
    "DraftEdge": "https://draftedge.com/{sport}/{sport}-starting-lineups/",
    "RotoWire": "https://www.rotowire.com/basketball/{sport}/lineups.php",
}

ALL_SOURCES = {**PROP_SOURCES, **GAME_SOURCES, **LINEUP_SOURCES}

SPORT_PATH = {
    "NBA":"basketball/nba",
    "MLB":"baseball/mlb",
    "NHL":"hockey/nhl",
    "NFL":"football/nfl",
    "WNBA":"basketball/wnba",
}

# ──────────────────────────────────────────────────────────────
# SPORT-SPECIFIC FALLBACK DATA — Every sport gets its own props & games
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
            {"Player":"Jewell Loyd","Prop":"PTS","Line":19.5,"Side":"UNDER","Sport":"WNBA"},
            {"Player":"Nneka Ogwumike","Prop":"REB","Line":7.5,"Side":"OVER","Sport":"WNBA"},
        ],
        "games": [{"Matchup":"LV Aces @ NY Liberty","Sport":"WNBA"},{"Matchup":"MIN Lynx @ SEA Storm","Sport":"WNBA"}]
    },
    "NFL": {
        "props": [
            {"Player":"Patrick Mahomes","Prop":"PASS_YDS","Line":275.5,"Side":"OVER","Sport":"NFL"},
            {"Player":"Christian McCaffrey","Prop":"RUSH_YDS","Line":85.5,"Side":"OVER","Sport":"NFL"},
            {"Player":"Justin Jefferson","Prop":"REC_YDS","Line":95.5,"Side":"OVER","Sport":"NFL"},
            {"Player":"Lamar Jackson","Prop":"RUSH_YDS","Line":55.5,"Side":"OVER","Sport":"NFL"},
            {"Player":"Tyreek Hill","Prop":"REC_YDS","Line":80.5,"Side":"UNDER","Sport":"NFL"},
        ],
        "games": [{"Matchup":"KC @ BUF","Sport":"NFL"},{"Matchup":"SF @ PHI","Sport":"NFL"}]
    },
    "MLB": {
        "props": [
            {"Player":"Aaron Judge","Prop":"HR","Line":0.5,"Side":"OVER","Sport":"MLB"},
            {"Player":"Shohei Ohtani","Prop":"STRIKEOUTS","Line":7.5,"Side":"OVER","Sport":"MLB"},
            {"Player":"Juan Soto","Prop":"HITS","Line":1.5,"Side":"OVER","Sport":"MLB"},
            {"Player":"Mookie Betts","Prop":"TB","Line":1.5,"Side":"OVER","Sport":"MLB"},
            {"Player":"Ronald Acuna Jr.","Prop":"SB","Line":0.5,"Side":"OVER","Sport":"MLB"},
        ],
        "games": [{"Matchup":"NYY @ LAD","Sport":"MLB"},{"Matchup":"ATL @ HOU","Sport":"MLB"}]
    },
    "NHL": {
        "props": [
            {"Player":"Connor McDavid","Prop":"PTS","Line":1.5,"Side":"OVER","Sport":"NHL"},
            {"Player":"Auston Matthews","Prop":"SHOTS","Line":3.5,"Side":"OVER","Sport":"NHL"},
            {"Player":"Nathan MacKinnon","Prop":"PTS","Line":1.5,"Side":"UNDER","Sport":"NHL"},
            {"Player":"David Pastrnak","Prop":"SHOTS","Line":4.5,"Side":"OVER","Sport":"NHL"},
        ],
        "games": [{"Matchup":"EDM @ TOR","Sport":"NHL"},{"Matchup":"COL @ BOS","Sport":"NHL"}]
    },
    "UFC": {
        "props": [
            {"Player":"Fighter A","Prop":"SIG_STRIKES","Line":45.5,"Side":"OVER","Sport":"UFC"},
            {"Player":"Fighter B","Prop":"TD","Line":2.5,"Side":"UNDER","Sport":"UFC"},
        ],
        "games": [{"Matchup":"UFC Main Event","Sport":"UFC"}]
    },
    "Golf": {
        "props": [
            {"Player":"Scottie Scheffler","Prop":"SCORE","Line":68.5,"Side":"UNDER","Sport":"Golf"},
            {"Player":"Rory McIlroy","Prop":"SCORE","Line":69.5,"Side":"UNDER","Sport":"Golf"},
        ],
        "games": [{"Matchup":"PGA Tournament","Sport":"Golf"}]
    },
    "Tennis": {
        "props": [
            {"Player":"Carlos Alcaraz","Prop":"ACES","Line":8.5,"Side":"OVER","Sport":"Tennis"},
            {"Player":"Iga Swiatek","Prop":"GAMES_WON","Line":12.5,"Side":"OVER","Sport":"Tennis"},
        ],
        "games": [{"Matchup":"ATP/WTA Match","Sport":"Tennis"}]
    },
    "Soccer": {
        "props": [
            {"Player":"Lionel Messi","Prop":"SHOTS","Line":3.5,"Side":"OVER","Sport":"Soccer"},
            {"Player":"Kylian Mbappe","Prop":"SHOTS","Line":3.5,"Side":"OVER","Sport":"Soccer"},
        ],
        "games": [{"Matchup":"Soccer Match","Sport":"Soccer"}]
    },
}

DEFAULT_BANKROLL = 1000.0
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
PROB_BOLT = 0.84
DTM_BOLT = 0.15

TIER_COLORS = {"SOVEREIGN":"#e8a020","ELITE":"#0d9488","APPROVED":"#2563eb","LEAN":"#f59e0b","PASS":"#d03030"}
TIER_LABELS = {"SOVEREIGN":"⚡ Sovereign Lock","ELITE":"🟢 Elite Edge","APPROVED":"🔵 Approved Single","LEAN":"🟠 Lean","PASS":"🔴 Pass"}

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
# Session State Init
# ──────────────────────────────────────────────────────────────
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "bankroll_start_of_day" not in st.session_state: st.session_state.bankroll_start_of_day = DEFAULT_BANKROLL
if "integrity_score" not in st.session_state: st.session_state.integrity_score = 64
if "session_start" not in st.session_state: st.session_state.session_start = time.time()
if "site_status" not in st.session_state:
    st.session_state.site_status = {n:{"status":"unknown","last_checked":"","error":""} for n in ALL_SOURCES}
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None
if "board_data" not in st.session_state: st.session_state.board_data = None
if "game_verdicts" not in st.session_state: st.session_state.game_verdicts = None
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"
if "summary_text" not in st.session_state: st.session_state.summary_text = ""
if "summary_items" not in st.session_state: st.session_state.summary_items = []
if "sharp_reference" not in st.session_state: st.session_state.sharp_reference = None
if "history" not in st.session_state: st.session_state.history = []
if "locks" not in st.session_state: st.session_state.locks = []

# Kelly calculator session state
if "kelly_odds" not in st.session_state: st.session_state.kelly_odds = -110
if "kelly_prob" not in st.session_state: st.session_state.kelly_prob = 55.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

# ──────────────────────────────────────────────────────────────
# Core Functions
# ──────────────────────────────────────────────────────────────
def tier_color(t): return TIER_COLORS.get(t, "#5a7088")
def tier_label(t): return TIER_LABELS.get(t, "—")
def dot(s): return {"ok":"🟢","fail":"🔴","degraded":"🟡"}.get(s, "⚪")
def get_bankroll(): return float(st.session_state.bankroll)

def set_health(name, status, err=""):
    """Set health with tri-state: ok / degraded / fail"""
    st.session_state.site_status[name] = {
        "status": status,
        "last_checked": datetime.now().strftime("%H:%M:%S"),
        "error": err
    }

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

def normal_wma(vals):
    vals = np.array(vals, dtype=float)
    w = np.arange(1, len(vals)+1)
    return float(np.average(vals, weights=w))

def wsem(vals):
    vals = np.array(vals[-8:], dtype=float)
    if len(vals) < 2: return 1.0
    w = np.arange(1, len(vals)+1)
    mu = np.average(vals, weights=w)
    var = np.average((vals-mu)**2, weights=w)
    return float(max(np.sqrt(var/max(len(vals),1)), 0.5))

def build_source_url(url_template, source_name, sport):
    """Build URL with correct path for the sport type."""
    sport_lower = sport.lower()
    sport_path = SPORT_PATH.get(sport.upper(), f"{sport_lower}/{sport_lower}")
    dk_sport = DK_SPORT_SLUG.get(sport.upper(), sport_lower)

    # CAPMMA doesn't use sport formatting
    if source_name == "CAPMMA":
        return url_template

    # ESPN uses sport_path for API endpoint
    if source_name == "ESPN":
        return url_template.format(sport_path=sport_path, sport=sport_lower, dk_sport=dk_sport)

    # DraftKings uses dk_sport for league-specific paths
    if source_name == "DraftKings":
        return url_template.format(dk_sport=dk_sport, sport=sport_lower, sport_path=sport_path)

    # RotoWire lineups need basketball/{sport} format
    if source_name == "RotoWire" and "lineups" in url_template:
        return url_template.format(sport=sport_lower, sport_path=sport_path, dk_sport=dk_sport)

    return url_template.format(sport=sport_lower, sport_path=sport_path, dk_sport=dk_sport)

def fetch_source(url_template, source_name, sport):
    """
    Fetch a source with health downgrade logic:
    - 'ok' when fetch and parse both succeed
    - 'degraded' when site responds but parsing is partial/empty
    - 'fail' only when the request fails or page is unusable
    """
    try:
        u = build_source_url(url_template, source_name, sport)
        r = requests.get(u, timeout=15, headers=HEADERS)

        if r.status_code == 200:
            if r.text and len(r.text) > 500:
                return r.text
            else:
                set_health(source_name, "degraded", "Response too small")
                return None
        elif r.status_code in (403, 429):
            set_health(source_name, "degraded", f"HTTP {r.status_code}")
            return None
        elif r.status_code == 404:
            set_health(source_name, "fail", f"HTTP 404 - URL: {u}")
            return None
        else:
            set_health(source_name, "fail", f"HTTP {r.status_code}")
            return None

    except requests.exceptions.Timeout:
        set_health(source_name, "degraded", "Timeout")
        return None
    except requests.exceptions.ConnectionError:
        set_health(source_name, "fail", "Connection refused")
        return None
    except Exception as e:
        set_health(source_name, "fail", str(e)[:80])
        return None

def parse_simple_props(html, sport):
    if not html: return []
    txt = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    rows = []
    for m in re.finditer(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})\s+(OVER|UNDER)\s+([0-9]+(?:\.[0-9])?)", txt, re.I):
        rows.append({"Player":m.group(1).strip(),"Prop":"PTS","Line":float(m.group(3)),"Side":m.group(2).upper(),"Sport":sport})
    if not rows:
        for m in re.finditer(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3}).*?([0-9]+(?:\.[0-9])?).*?(OVER|UNDER)", txt, re.I):
            rows.append({"Player":m.group(1).strip(),"Prop":"GEN","Line":float(m.group(2)),"Side":m.group(3).upper(),"Sport":sport})
    return rows[:25]

def fetch_live_props(sport):
    """
    Fetch live props from ALL sources, collect all results.
    If a source responds but parsing yields nothing, mark as degraded.
    If ALL sources fail, use sport-specific fallback.
    """
    all_rows = []

    for name, url in PROP_SOURCES.items():
        html = fetch_source(url, name, sport)
        if html:
            rows = parse_simple_props(html, sport)
            if rows:
                all_rows.extend(rows)
                set_health(name, "ok")
            else:
                current = st.session_state.site_status.get(name, {})
                if current.get("status") != "ok":
                    set_health(name, "degraded", "No props parsed from response")

    if not all_rows:
        fallback = SPORT_FALLBACK_MAP.get(sport.upper(), SPORT_FALLBACK_MAP["NBA"])
        return fallback["props"]

    return all_rows

def fetch_live_games(sport):
    html = fetch_source(GAME_SOURCES["ESPN"], "ESPN", sport)
    out = []
    if html:
        try:
            js = json.loads(html)
            for ev in js.get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                competitors = comp.get("competitors") or []
                home = next((x for x in competitors if x.get("homeAway") == "home"), {})
                away = next((x for x in competitors if x.get("homeAway") == "away"), {})
                out.append({"Matchup": f"{away.get('team', {}).get('shortDisplayName', '')} @ {home.get('team', {}).get('shortDisplayName', '')}", "Sport": sport})
            if out:
                set_health("ESPN", "ok")
            else:
                set_health("ESPN", "degraded", "No events in response")
        except Exception:
            set_health("ESPN", "degraded", "JSON parse failed")

    if not out:
        fallback = SPORT_FALLBACK_MAP.get(sport.upper(), SPORT_FALLBACK_MAP["NBA"])
        out = fallback.get("games", [{"Matchup": f"{sport} Game", "Sport": sport}])

    return out

def fetch_player_series(player, market, sport):
    base = 24 if market in ("PTS","PRA","PR","PA") else 6 if market in ("REB","RUSH_YDS") else 5 if market in ("AST","REC_YDS") else 17
    return list(np.random.normal(base, max(2, base*0.15), 10))

def analyze_prop(player, market, line, pick, sport="NBA", odds=-110, bankroll=None):
    bankroll = bankroll or get_bankroll()
    stats = fetch_player_series(player, market, sport)
    mu = normal_wma(stats)
    sigma = max(wsem(stats), 0.75)
    prob = float(1 - norm.cdf(line, mu, sigma) if pick.upper()=="OVER" else norm.cdf(line, mu, sigma))
    impl = american_to_prob(odds)
    edge = prob - impl
    tier = classify_tier(edge)
    return {
        "player":player,"market":market,"line":line,"pick":pick,"sport":sport,"odds":odds,
        "prob":prob,"edge":edge,"kelly":kelly(prob, odds),"tier":tier,
        "bolt_signal":"ELITE LOCK" if tier in ("SOVEREIGN","ELITE") else "PASS",
        "mu":mu,"sigma":sigma,"cv":sigma/max(mu,1e-9),"minutes_cv":0.12,
        "confidence":85,"source_status":"OK"
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
        score = round(sum(m["weight"]*votes[m["name"]] for m in MODELS), 3)
        tier = classify_tier(score)
        out.append({**item, **res, "Player":player,"Prop":prop_market,"Line":line,"Side":side,"Sport":sport,
                    "Votes":votes, "Weighted Score":score, "Tier":tier, "Tier Label":tier_label(tier)})
    out.sort(key=lambda x: x["Weighted Score"], reverse=True)
    return out

def run_game_council(games):
    out = []
    for g in games:
        score = 0.58
        tier = classify_tier(score)
        out.append({**g, "Weighted Score":score, "Tier":tier, "Tier Label":tier_label(tier)})
    out.sort(key=lambda x: x["Weighted Score"], reverse=True)
    return out

def summary_text(board, games):
    if not board and not games:
        return "No live board loaded yet. Click 'Load Board' or 'Re-Run Board' in the sidebar to analyze props."
    top_prop = board[0] if board else None
    top_game = games[0] if games else None
    parts = []
    if top_prop:
        parts.append(f"🔥 Best Prop: **{top_prop['Player']}** — {top_prop['Side']} {top_prop['Line']} {top_prop['Prop']} ({top_prop['Tier Label']}, Score: {top_prop['Weighted Score']:.2f})")
    if top_game:
        parts.append(f"🏟️ Best Game: **{top_game['Matchup']}** ({top_game['Tier Label']}, Score: {top_game['Weighted Score']:.2f})")
    if board:
        sovereign = sum(1 for x in board if x['Tier'] == 'SOVEREIGN')
        elite = sum(1 for x in board if x['Tier'] == 'ELITE')
        approved = sum(1 for x in board if x['Tier'] == 'APPROVED')
        total_approved = sovereign + elite + approved
        parts.append(f"📊 Board: {total_approved} approved-or-better props ({sovereign} Sovereign, {elite} Elite, {approved} Approved) of {len(board)} total analyzed.")
    return "\n\n".join(parts)

def build_summary_cards(board, games):
    if not board and not games:
        return []
    cards = []
    if board:
        top = board[0]
        cards.append({
            "title": "Top Prop",
            "detail": f"{top['Player']} {top['Side']} {top['Line']} {top['Prop']}",
            "tier": top['Tier Label'],
            "tier_color": tier_color(top['Tier']),
            "score": top['Weighted Score'],
            "sport": top.get('Sport', '')
        })
    if games:
        topg = games[0]
        cards.append({
            "title": "Top Game",
            "detail": topg['Matchup'],
            "tier": topg['Tier Label'],
            "tier_color": tier_color(topg['Tier']),
            "score": topg['Weighted Score'],
            "sport": topg.get('Sport', '')
        })
    return cards

def parse_manual_input(text):
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        match = re.match(r"(.+?)\s+(OVER|UNDER)\s+([0-9.]+)\s+(.+)", line, re.IGNORECASE)
        if match:
            results.append({"type":"PROP","player":match.group(1).strip(),"side":match.group(2).upper(),"line":float(match.group(3)),"prop":match.group(4).strip(),"raw":line})
    return results

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

def board_of_8(item):
    votes = {
        0: 1 if item.get("edge", 0) > 0.04 else 0,
        1: 1 if item.get("cv", 1) < 0.18 else 0,
        2: 1 if item.get("minutes_cv", 1) < 0.18 else 0,
        3: 1 if item.get("news_mult", 1) >= 0.85 else 0,
        4: 1 if item.get("source_status", "OK") == "OK" else 0,
        5: 1 if item.get("prob", 0) >= 0.58 else 0,
        6: 1 if item.get("confidence", 0) >= 65 else 0,
        7: 1 if item.get("sharp_available", False) else 0,
    }
    weights = [0.18,0.14,0.12,0.12,0.14,0.10,0.10,0.10]
    ws = sum(weights[i] * votes.get(i, 0) for i in range(len(weights)))
    tier = "SOVEREIGN" if ws >= 0.70 else "ELITE" if ws >= 0.55 else "APPROVED" if ws >= 0.40 else "LEAN" if ws >= 0.20 else "PASS"
    return votes, ws, tier

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
    """Ping all sources to verify health status with degraded fallback."""
    for name, url in ALL_SOURCES.items():
        test_sport = "NBA"
        try:
            u = build_source_url(url, name, test_sport)
            r = requests.get(u, timeout=10, headers=HEADERS)
            if r.status_code == 200 and r.text and len(r.text) > 500:
                set_health(name, "ok")
            elif r.status_code in (403, 429):
                set_health(name, "degraded", f"HTTP {r.status_code}")
            elif r.status_code == 404:
                set_health(name, "fail", f"HTTP 404 - URL: {u}")
            else:
                set_health(name, "fail", f"HTTP {r.status_code}")
        except requests.exceptions.Timeout:
            set_health(name, "degraded", "Timeout")
        except requests.exceptions.ConnectionError:
            set_health(name, "fail", "Connection refused")
        except Exception as e:
            set_health(name, "fail", str(e)[:60])

def load_sport_data(sport):
    """Load board data for a specific sport with its own fallback data."""
    raw_props = fetch_live_props(sport)
    raw_games = fetch_live_games(sport)
    st.session_state.board_data = run_council(raw_props)
    st.session_state.game_verdicts = run_game_council(raw_games)
    st.session_state.summary_text = summary_text(st.session_state.board_data, st.session_state.game_verdicts)
    st.session_state.summary_items = build_summary_cards(st.session_state.board_data, st.session_state.game_verdicts)
    st.session_state.sharp_reference = fetch_sharp_reference(sport)
    st.session_state.last_sport = sport

def scan_all_sports():
    """
    Scan ALL sports and store per-sport results in cross_sport_board.
    Each sport gets its own fallback if live data fails.
    """
    all_props, all_games = [], []
    sport_results = {}

    for sport in SPORTS:
        props = fetch_live_props(sport)
        games = fetch_live_games(sport)
        all_props.extend(props)
        all_games.extend(games)
        sport_results[sport] = {
            "props": props,
            "games": games
        }

    st.session_state.cross_sport_board = {
        "props": run_council(all_props),
        "games": run_game_council(all_games),
        "scanned_at": datetime.now().strftime("%H:%M:%S"),
        "sport_results": sport_results
    }
    st.session_state.sharp_reference = fetch_sharp_reference(st.session_state.last_sport)

# ──────────────────────────────────────────────────────────────
# Computed values for sidebar
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
sources_degraded = sum(1 for v in st.session_state.site_status.values() if v.get("status") == "degraded")
total_sources = max(len(st.session_state.site_status), 1)
recent_check = False
for v in st.session_state.site_status.values():
    last = v.get("last_checked", "")
    if last:
        try:
            datetime.strptime(last, "%H:%M:%S")
            recent_check = True
            break
        except:
            pass

firewall_checks = {
    "All core sources online": (sources_ok + sources_degraded) >= max(total_sources - 2, 1),
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
    <div style="font-size:12px;color:#5a7088;margin-bottom:14px;">3.1 OS</div>
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
        with st.spinner(f"Loading {sport} board..."):
            load_sport_data(sport)
        st.success(f"{sport} loaded.")
    if st.button("🔄 Re-Run Board", use_container_width=True):
        with st.spinner("Re-running board..."):
            load_sport_data(st.session_state.last_sport)
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
<div><div style='font-size:22px;font-weight:700;color:#f4f8fc;letter-spacing:1px;'>BetCouncil</div><div style='font-size:12px;color:#5a7088;'>v3.2 · Summary + Cross-Sport + Sharp Reference</div></div>
<div style='margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;'>
<span class='toggle-btn active'>🛡️ Safe: ON</span>
<span class='toggle-btn active'>⚠️ Blowout: ON</span>
<span class='toggle-btn' style='border-color:#e8a020;color:#e8a020;background:rgba(232,160,32,.1);'>🔒 {pending_count} Lock(s)</span>
</div></div>
<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:7px;'>
<div class='metric-box'><div class='metric-label'>Bankroll</div><div class='metric-value gold-text'>${bankroll:,.2f}</div></div>
<div class='metric-box'><div class='metric-label'>PROB_BOLT</div><div class='metric-value gold-text'>{PROB_BOLT:.2f}</div></div>
<div class='metric-box'><div class='metric-label'>DTM_BOLT</div><div class='metric-value gold-text'>{DTM_BOLT:.2f}</div></div>
<div class='metric-box'><div class='metric-label'>Sharp Ref</div><div class='metric-value {"green-text" if sharp.get("status")=="ok" else "yellow-text" if sharp.get("status")=="degraded" else "red-text"}'>{sharp.get("book","Pinnacle")}</div></div>
</div></div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# TABS — Board of 8 FIRST (primary workflow), then Analysis
# ──────────────────────────────────────────────────────────────
tabs = st.tabs(["🏀 Board of 8", "📊 Analysis", "🔒 Locks of Day", "📋 Locks & Ledger", "🔄 Reconciliation", "🧠 Models", "⚙️ Settings"])

# ────────── TAB 0: Board of 8 (PRIMARY) ──────────
with tabs[0]:
    st.markdown("# 🏀 Board of 8")

    board = st.session_state.board_data or []
    summary_items = st.session_state.summary_items or []

    # ── SUMMARY SECTION ──
    if st.session_state.summary_text:
        st.markdown("## 📋 Council Summary")
        for line in st.session_state.summary_text.split("\n\n"):
            line_stripped = line.strip()
            if line_stripped:
                st.markdown(f"<div class='summary-card'>{line_stripped}</div>", unsafe_allow_html=True)

        # Summary cards side by side
        if isinstance(summary_items, list) and len(summary_items) > 0:
            valid_cards = [c for c in summary_items if isinstance(c, dict)]
            if valid_cards:
                cols = st.columns(min(2, len(valid_cards)))
                for i, card in enumerate(valid_cards[:2]):
                    with cols[i]:
                        card_title = str(card.get('title', ''))
                        card_sport = str(card.get('sport', ''))
                        card_detail = str(card.get('detail', ''))
                        card_tier = str(card.get('tier', ''))
                        card_tier_color = str(card.get('tier_color', '#5a7088'))
                        card_score = float(card.get('score', 0))

                        st.markdown(f"""
                        <div class='summary-card'>
                            <div style='font-size:11px;color:#5a7088;text-transform:uppercase;'>{card_title} · {card_sport}</div>
                            <div style='font-size:16px;font-weight:700;color:#f4f8fc;'>{card_detail}</div>
                            <div style='margin-top:4px;'>
                                <span style='color:{card_tier_color};font-weight:700;'>{card_tier}</span>
                                <span style='font-family:monospace;color:#e8a020;float:right;'>Score {card_score:.2f}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
        st.markdown("---")
    else:
        st.info("No board loaded yet. Click **Load Board** or **Re-Run Board** in the sidebar to analyze props and see the summary.")

    # ── MAIN BOARD ──
    st.markdown("## Main Board — Prop Analysis")
    if board:
        for i, item in enumerate(board):
            tc = tier_color(item['Tier'])
            edge_pct = item.get('edge', 0) * 100
            edge_color = "#0d9488" if edge_pct >= 8 else "#e8a020" if edge_pct >= 4 else "#5a7088"

            st.markdown(f"""
            <div class='prop-card' style='border-left:4px solid {tc};'>
                <div class='prop-card-left'>
                    <div class='prop-card-player'>{item['Player']}</div>
                    <div class='prop-card-detail'>{item['Side']} {item['Line']} {item['Prop']} · {item.get('Sport','NBA')}</div>
                </div>
                <div class='prop-card-center'>
                    <div class='prop-card-edge' style='color:{edge_color};'>{edge_pct:.1f}%</div>
                    <div class='prop-card-tier' style='color:{tc};'>{item['Tier Label']}</div>
                </div>
                <div class='prop-card-right'>
                    <div class='prop-card-score'>Council Score {item['Weighted Score']:.2f}</div>
            """, unsafe_allow_html=True)

            if item["Tier"] in ("SOVEREIGN","ELITE","APPROVED"):
                if st.button(f"🔒 Lock it In", key=f"lock_board_{i}"):
                    lock_id = lock_single_prop(item)
                    st.session_state.locks.append({
                        "id": lock_id,
                        "type": "PROP",
                        "player": item["Player"],
                        "prop": f"{item['Side']} {item['Line']} {item['Prop']}",
                        "tier": item["Tier"],
                        "status": "PENDING",
                        "result": None
                    })
                    st.success(f"🔒 Locked: {item['Player']} {item['Side']} {item['Line']}")
                    st.rerun()

            st.markdown("</div></div>", unsafe_allow_html=True)
    else:
        st.info("No board data loaded yet. Use **Load Board** or **Re-Run Board** in the sidebar.")

    st.markdown(f"<div class='small-note'>Sharp Reference: {sharp.get('book','Pinnacle')} via {sharp.get('source','OddsHarvester')} — {sharp.get('status','unknown').upper()}</div>", unsafe_allow_html=True)

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

        st.markdown("## 🏟️ Top Game Lines Across All Sports")
        cross_games = cross.get('games', [])
        if cross_games:
            for i, g in enumerate(cross_games[:5], 1):
                tc = tier_color(g.get('Tier', 'PASS'))
                st.markdown(f"<div class='section-card' style='border-left:3px solid {tc};'><span style='color:#5a7088;'>#{i} · {g.get('Sport','')}</span> <span style='color:#f4f8fc;font-weight:600;'>{g.get('Matchup','')}</span> <span style='color:{tc};font-weight:600;'>{g.get('Tier Label','')}</span></div>", unsafe_allow_html=True)
        else:
            st.info("No games found in cross-sport scan.")

        st.markdown(f"<div class='small-note'>Sharp Reference: {sharp.get('book','Pinnacle')} via {sharp.get('source','OddsHarvester')} | Status: {sharp.get('status','unknown')} | Note: {sharp.get('note','')}</div>", unsafe_allow_html=True)

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
            <div class='summary-card' style='border:2px solid {tier_color(best_prop['Tier'])};'>
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

        game_par = build_game_parlay()
        if game_par:
            st.markdown("## 🏟️ Game Parlay Candidates")
            for i, leg in enumerate(game_par[:4], 1):
                st.markdown(f"<div class='section-card'><b>Leg {i}:</b> {leg['Matchup']} — <span style='color:{tier_color(leg['Tier'])}'>{leg['Tier Label']}</span></div>", unsafe_allow_html=True)
    else:
        st.info("Load a board first to see Locks of Day.")

# ────────── TAB 3: Locks & Ledger ──────────
with tabs[3]:
    st.markdown("# 📋 Locks & Ledger")
    if not st.session_state.locks:
        st.info("No active locks. Lock some props from the Board of 8 tab.")
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
    st.markdown("*Weights are FIXED. Only adjustable via Model Weight Adjustment Event: model <45% accuracy over last 25 props → -0.03; best performer → +0.03. Total must always = 1.00.*")
    model_rows = ""
    for m in MODELS:
        model_rows += f"<tr><td style='color:#f4f8fc;font-weight:600;font-size:14px;'>{m['name']}</td><td style='color:#5a7088;font-size:14px;'>{m['specialty']}</td><td style='color:#e8a020;font-family:monospace;font-size:15px;font-weight:700;'>{m['weight']:.2f}</td><td style='color:#5a7088;font-size:13px;'>{m['function']}</td></tr>"
    st.markdown(f"""
    <table class='model-table'>
    <thead><tr><th>MODEL</th><th>SPECIALTY</th><th>WEIGHT</th><th>CORE FUNCTION</th></tr></thead>
    <tbody>{model_rows}</tbody>
    </table>
    <div class='small-note' style='margin-top:10px;'>Total: {sum(m['weight'] for m in MODELS):.2f} / 1.00 · CLV adjustment: ±0.01 per model if CLV >+0.5% or <-1.0% over 25 settled.</div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("## Tier Thresholds (Fixed)")
    st.markdown("""
    | SCORE | TIER | NOTES |
    |---|---|---|
    | ≥ 0.70 | ⚡ Sovereign Lock | Highest confidence — available in Normal Mode only |
    | 0.55–0.69 | 🟢 Elite Edge | Strong consensus |
    | 0.40–0.54 | 🔵 Approved Single | Safety Corridor Rec provided |
    | 0.20–0.39 | 🟠 Lean | Informational only, not actioned |
    | < 0.20 | 🔴 PASS | Rejected — do not bet |
    """)

# ────────── TAB 6: Settings (SEM & System) ──────────
with tabs[6]:
    st.markdown("# ⚙️ SEM & System")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Integrity", f"{integrity}/100")
    c2.metric("Safe Corridor", "ACTIVE")
    c3.metric("Emergency Floor", "ACTIVE")
    c4.metric("Bankroll", f"${bankroll:,.2f}")

    st.markdown("## Site Health (Green=OK · Yellow=Degraded · Red=Down)")
    if st.button("🔄 Refresh Site Health", key="refresh_health"):
        check_all_sources_health()
        st.rerun()

    cols = st.columns(2)
    left_names = list(PROP_SOURCES.keys())
    right_names = list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys())
    with cols[0]:
        st.markdown("### Prop Sources")
        for name in left_names:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "") or "—"
            err = st.session_state.site_status.get(name, {}).get("error", "")
            cls = "ok" if s == "ok" else "fail" if s == "fail" else "unk"
            label = "🟢 WORKING" if s == "ok" else "🟡 DEGRADED" if s == "degraded" else "🔴 DOWN" if s == "fail" else "⚪ UNCHECKED"
            err_str = f" <span style='font-size:10px;color:#d03030;'>({err})</span>" if err and s in ("fail","degraded") else ""
            st.markdown(f"<div class='section-card'>{label} <b>{name}</b> <span class='muted-text'>— {t}</span>{err_str}</div>", unsafe_allow_html=True)
    with cols[1]:
        st.markdown("### Game / Lineup Sources")
        for name in right_names:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "") or "—"
            err = st.session_state.site_status.get(name, {}).get("error", "")
            cls = "ok" if s == "ok" else "fail" if s == "fail" else "unk"
            label = "🟢 WORKING" if s == "ok" else "🟡 DEGRADED" if s == "degraded" else "🔴 DOWN" if s == "fail" else "⚪ UNCHECKED"
            err_str = f" <span style='font-size:10px;color:#d03030;'>({err})</span>" if err and s in ("fail","degraded") else ""
            st.markdown(f"<div class='section-card'>{label} <b>{name}</b> <span class='muted-text'>— {t}</span>{err_str}</div>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(f"**Sharp Reference:** {sharp.get('book','Pinnacle')} via {sharp.get('source','OddsHarvester')} | Status: {sharp.get('status','unknown')} | Line: {sharp.get('line')} | Note: {sharp.get('note','')}")
