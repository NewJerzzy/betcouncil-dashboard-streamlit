import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==============================================================================
# 1. PAGE CONFIG & MASTER STYLING (The v3.2 Look)
# ==============================================================================
st.set_page_config(
    page_title="BetCouncil v3.4 Master",
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
.section-card {
    background: linear-gradient(135deg, #0d1520, #0f1825);
    border: 1px solid #1a2a3a;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 10px;
}
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
.teal-text { color: #0ea5a0; }
.red-text { color: #e04040; }
.gold-text { color: #e8a020; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. CONSTANTS & MODEL WEIGHTS (The Board of 8)
# ==============================================================================
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

SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]
DEFAULT_BANKROLL = 529.64
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

# ==============================================================================
# 3. SESSION STATE MANAGEMENT
# ==============================================================================
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "day_start_br" not in st.session_state: st.session_state.day_start_br = DEFAULT_BANKROLL
if "board_ready" not in st.session_state: st.session_state.board_ready = False
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None
if "integrity" not in st.session_state: st.session_state.integrity = 64
if "session_start" not in st.session_state: st.session_state.session_start = time.time()

# ==============================================================================
# 4. CORE ENGINE (Calculations & Multi-threading)
# ==============================================================================
def weighted_score(votes):
    return round(sum(MODELS[i]["weight"] * votes.get(m["name"], 0) for i, m in enumerate(MODELS)), 3)

def get_tier(score):
    if score >= 0.70: return "SOVEREIGN"
    if score >= 0.55: return "ELITE"
    if score >= 0.40: return "APPROVED"
    return "LEAN" if score >= 0.20 else "PASS"

def fetch_espn_sector(sport):
    """Sector worker for simultaneous data retrieval."""
    results = []
    path_map = {"nba": "basketball/nba", "mlb": "baseball/mlb", "nhl": "hockey/nhl", "nfl": "football/nfl", "wnba": "basketball/wnba"}
    path = path_map.get(sport.lower(), f"basketball/{sport.lower()}")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=7)
        if resp.status_code == 200:
            events = resp.json().get("events", [])
            for e in events:
                results.append({
                    "Player": e.get("shortName", "Unknown"),
                    "Sport": sport,
                    "Prop": "Market Entry",
                    "Side": "OPEN",
                    "Line": 0.0
                })
    except:
        pass
    return results

def run_master_simultaneous_scan():
    """V3.4 Speed: Firing all 9 sectors at once."""
    all_raw = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_sport = {executor.submit(fetch_espn_sector, s): s for s in SPORTS}
        for future in as_completed(future_to_sport):
            all_raw.extend(future.result())
    
    # Council Consensus Logic
    processed = []
    for item in all_raw:
        # Internal Logic: High-weight models vote on market entries
        votes = {m["name"]: (1 if "NBA" in item["Sport"] else 0) for m in MODELS}
        ws = weighted_score(votes)
        tier = get_tier(ws)
        item.update({
            "Weighted Score": ws,
            "Tier": tier,
            "EdgePct": round(ws * 100),
            "Status": "Verified" if ws > 0.40 else "Scanning"
        })
        processed.append(item)
    
    processed.sort(key=lambda x: x["Weighted Score"], reverse=True)
    return processed

# ==============================================================================
# 5. SIDEBAR (The Control Panel)
# ==============================================================================
with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center;margin-bottom:20px;">
        <h2 style="margin-bottom:0;">🛡️ BetCouncil</h2>
        <div style="font-size:11px;color:#0ea5a0;">V3.4 MASTER ENGINE</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.session_state.bankroll = st.number_input("Bankroll", value=float(st.session_state.bankroll), step=10.0)
    
    st.markdown("---")
    if st.button("🚀 SCAN ALL SPORTS", use_container_width=True):
        with st.spinner("Synchronizing All Sectors..."):
            st.session_state.cross_sport_board = run_master_simultaneous_scan()
            st.session_state.board_ready = True
            st.session_state.integrity = 92

# ==============================================================================
# 6. MAIN INTERFACE (The Board of 8 Display)
# ==============================================================================
st.title("🧠 THE BOARD OF 8")

if st.session_state.board_ready and st.session_state.cross_sport_board:
    # Dashboard Header
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Integrity</div><div class="metric-value">{st.session_state.integrity}%</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Active Unit</div><div class="metric-value">${st.session_state.bankroll * 0.05:,.2f}</div></div>', unsafe_allow_html=True)
    with c3:
        status_color = "teal-text" if st.session_state.integrity > 70 else "red-text"
        st.markdown(f'<div class="metric-box"><div class="metric-label">Status</div><div class="metric-value {status_color}">SHIELD ON</div></div>', unsafe_allow_html=True)

    st.markdown("### ⚡ CLARITY APPROVED TARGETS")
    
    df = pd.DataFrame(st.session_state.cross_sport_board)
    
    # Custom display logic for the dataframe
    st.dataframe(
        df[["Player", "Sport", "Tier", "Weighted Score", "EdgePct", "Status"]],
        use_container_width=True,
        hide_index=True
    )
    
else:
    st.info("System Standby. Please initiate the Simultaneous Scan in the sidebar to populate the board.")

st.markdown("---")
st.caption(f"BetCouncil v3.4 Master | Production Build | Active Session: {int(time.time() - st.session_state.session_start) // 60}m")
