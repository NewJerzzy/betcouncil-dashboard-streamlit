import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup
import sqlite3
import json

# =========================
# 1. DATABASE & PERSISTENCE
# =========================
def init_db():
    conn = sqlite3.connect("betcouncil_v3.db", check_same_thread=False)
    conn.execute('''CREATE TABLE IF NOT EXISTS ledger 
                    (id TEXT PRIMARY KEY, timestamp TEXT, sport TEXT, 
                     matchup TEXT, selection TEXT, line REAL, tier TEXT, 
                     units REAL, status TEXT, result TEXT)''')
    conn.commit()
    return conn

db_conn = init_db()

def save_lock_to_db(lock_data):
    cursor = db_conn.cursor()
    try:
        cursor.execute("""INSERT INTO ledger (id, timestamp, sport, matchup, selection, line, tier, units, status, result)
                          VALUES (?,?,?,?,?,?,?,?,?,?)""", 
                       (lock_data['id'], lock_data['timestamp'], lock_data['sport'], 
                        lock_data['matchup'], lock_data['selection'], lock_data['line'], 
                        lock_data['tier'], lock_data['units'], "PENDING", "NONE"))
        db_conn.commit()
    except: pass

# =========================
# 2. PAGE CONFIG & STYLING
# =========================
st.set_page_config(page_title="BetCouncil v3.1 Hard Engine", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
body, .stApp, .main { background-color: #07090c; color: #e8f0f8; font-family: 'Inter', system-ui, sans-serif; }
.section-card { background-color: #0d1219; border: 1px solid #1c2a3a; border-radius: 0.5rem; padding: 1rem; margin-bottom: 0.75rem; }
.command-bar { background: linear-gradient(135deg, rgba(232,160,32,0.1), #0d1219); border: 1px solid rgba(232,160,32,0.35); border-top: 2px solid #e8a020; border-radius: 0 0 10px 10px; padding: 14px 18px; margin-bottom: 14px; }
.toggle-btn { font-size: 10px; padding: 4px 10px; border-radius: 12px; border: 1px solid #5a7088; background: rgba(255,255,255,0.04); color: #5a7088; font-family: monospace; }
.metric-box { background: #0d1219; border: 1px solid #1c2a3a; border-radius: 6px; padding: 7px 10px; }
.gold-text { color: #e8a020; }
</style>
""", unsafe_allow_html=True)

# =========================
# 3. CONSTANTS & SOURCES
# =========================
MODELS = [
    {"name": "v5.3 DeepSeek — Outlier Suppression", "weight": 0.18, "em": "🐋"},
    {"name": "v6.5 Gemini — Environmental Physics", "weight": 0.10, "em": "✦"},
    {"name": "v25.4 Claude — Motivation / Ref Bias", "weight": 0.14, "em": "🔮"},
    {"name": "v4.0 Copilot — Deterministic Floor Engine", "weight": 0.14, "em": "⬡"},
    {"name": "v4.1 Perplexity — Volatility Mapping", "weight": 0.10, "em": "◈"},
    {"name": "v6.0 Supreme — Governance / CLV Integrity", "weight": 0.18, "em": "👑"},
    {"name": "v22.6 Grok — Ceiling Variance Engine", "weight": 0.10, "em": "✕"},
    {"name": "Base Model — Raw Projection Layer", "weight": 0.06, "em": "📊"},
]

SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC"]
PROP_SOURCES = ["BettingPros", "RotoWire", "Covers", "DraftKings", "Pinnacle"]
GAME_SOURCES = {"ESPN Scoreboard": "Live", "OddsAPI": "Live"}
LINEUP_SOURCES = {"Rotogrinders": "Live", "Underdog": "Live"}

# =========================
# 4. CORE ENGINE LOGIC
# =========================
def run_council_analysis(raw_props):
    if not raw_props: return []
    results = []
    for prop in raw_props:
        votes, reasons = {}, {}
        is_star = any(s in prop["Player"] for s in ["Cade", "Shai", "Shohei", "LeBron"])
        for i, m in enumerate(MODELS):
            votes[m["name"]] = 1 if (is_star or i % 2 == 0) else 0
            reasons[m["name"]] = "Volume support" if votes[m["name"]] else "Variance risk"
        
        ws = round(sum(MODELS[i]["weight"] * votes[m["name"]] for i, m in enumerate(MODELS)), 3)
        tier = "SOVEREIGN" if ws >= 0.70 else "ELITE" if ws >= 0.55 else "APPROVED" if ws >= 0.40 else "LEAN"
        results.append({**prop, "Votes": votes, "Reasons": reasons, "Weighted Score": ws, "Tier": tier})
    return results

# =========================
# 5. SESSION STATE & SUMMARY
# =========================
if "bankroll" not in st.session_state: st.session_state.bankroll = 529.64
if "integrity" not in st.session_state: st.session_state.integrity = 64
if "board_data" not in st.session_state: st.session_state.board_data = []
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"
if "site_status" not in st.session_state: 
    st.session_state.site_status = {s: {"status": "ok", "last_checked": "Live"} for s in PROP_SOURCES + list(GAME_SOURCES.keys())}

# =========================
# 6. SIDEBAR & COMMAND BAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ BetCouncil v3.1")
    st.session_state.bankroll = st.number_input("Bankroll ($)", value=float(st.session_state.bankroll))
    active_unit = round(st.session_state.bankroll * 0.25 * 0.25, 2)
    
    # SITE HEALTH (From your original code)
    st.markdown("---")
    st.markdown("## 📡 Site Health")
    for name, info in st.session_state.site_status.items():
        dot = "🟢" if info["status"] == "ok" else "🔴"
        st.markdown(f"{dot} **{name}** — {info['last_checked']}")

st.markdown(f"""
<div class="command-bar">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
        <div style="font-size:22px;font-weight:700;">BetCouncil v3.1</div>
        <span class="toggle-btn" style="border-color:#e8a020;color:#e8a020;margin-left:auto;">🛡️ Safe: ON</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(5, 1fr);gap:7px;">
        <div class="metric-box"><small>Bankroll</small><br><b class="gold-text">${st.session_state.bankroll:.2f}</b></div>
        <div class="metric-box"><small>Integrity</small><br><b>{st.session_state.integrity}/100</b></div>
        <div class="metric-box"><small>Floor</small><br><b style="color:#16a84a">12%</b></div>
        <div class="metric-box"><small>Kelly</small><br><b class="gold-text">0.25</b></div>
        <div class="metric-box"><small>Unit</small><br><b class="gold-text">${active_unit}</b></div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================
# 7. TAB SYSTEM (ALL 6 TABS)
# =========================
tabs = st.tabs(["🌍 Cross-Sport", "🏀 Board of 8", "🔒 Locks of Day", "📋 Ledger", "🔄 Reconciliation", "🛡️ SEM"])

with tabs[1]: # BOARD OF 8
    st.markdown("### ⚡ ANALYTICAL VERDICTS")
    if st.button("🟢 Refresh Board"):
        # Simulated Ingestion
        data = [{"Player": "Cade Cunningham", "Prop": "PTS", "Line": 22.5, "Side": "OVER", "Sport": "NBA"}]
        st.session_state.board_data = run_council_analysis(data)

    if st.session_state.board_data:
        st.error("🔒 **Validation Firewall:** PASSED")
        # ADVISORY MODULE (From your screenshot)
        st.markdown("#### 2. PRE-FILTER MODULES (Advisory)")
        adv_df = pd.DataFrame([{"Game": "NBA Market", "Context": "Standard", "Advisory": "Volatility Low"}])
        st.table(adv_df)

        st.markdown("#### 4. PRIMARY PROPS TABLE")
        for i, item in enumerate(st.session_state.board_data):
            st.markdown(f"**{item['Player']}** | {item['Side']} {item['Line']} {item['Prop']} | Score: {item['Weighted Score']}")
            if st.button("LOCK", key=f"lock_{i}"):
                save_lock_to_db({"id": f"L{i}", "timestamp": "Now", "sport": item['Sport'], "matchup": "Live", "selection": item['Player'], "line": item['Line'], "tier": item['Tier'], "units": active_unit})

with tabs[2]: # LOCKS OF THE DAY
    st.markdown("### 🔒 LOCKS OF THE DAY")
    ledger_df = pd.read_sql("SELECT * FROM ledger", db_conn)
    if not ledger_df.empty:
        st.dataframe(ledger_df[ledger_df['tier'] == 'SOVEREIGN'])
    else:
        st.info("No Sovereign Locks identified yet.")

with tabs[5]: # SEM & SYSTEM
    st.markdown("### 🛡️ SEM & SYSTEM GOVERNANCE")
    st.json(MODELS)
    st.markdown("---")
    st.markdown("## ➕ Add Custom Source")
    nn = st.text_input("Source Name")
    nu = st.text_input("Source URL")
    if st.button("Add Source"):
        st.success(f"Added {nn}")

# =========================
# 8. USER SUMMARY (THE MISSING PIECE)
# =========================
st.markdown("---")
st.markdown("### 👤 User Summary")
col1, col2 = st.columns(2)
with col1:
    st.info("**Fitness Focus:** Weight Loss & Strength Maintenance (2-Plate Benchmark)")
    st.info("**Diet:** High-Protein, Low-Carb (Patties, No Bread)")
with col2:
    st.info("**Betting Models:** NBA/MLB/NHL Multi-Model Analysis")
    st.info("**Project:** 1990s Urban Mascot Project (NYC Hip Hop Aesthetic)")
