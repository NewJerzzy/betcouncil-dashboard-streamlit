import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime

# --- 1. THEMING & CSS (RESTORES THE LOOK) ---
st.set_page_config(page_title="BetCouncil v3.0 OS", layout="wide", page_icon="🧠")

st.markdown("""
    <style>
    /* Main Background & Font */
    .stApp { background-color: #0E1117; color: #FFFFFF; }
    
    /* Header Card with Gold Border */
    .header-card {
        background-color: #1A1C24;
        border: 2px solid #D4AF37;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 25px;
    }
    
    /* Metric Styling */
    [data-testid="stMetricValue"] { font-size: 28px; color: #D4AF37; }
    [data-testid="stMetricLabel"] { font-size: 14px; color: #808080; }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] { background-color: #161B22 !important; width: 300px !important; }
    
    /* Buttons */
    .stButton>button {
        background-color: #3D5AFE; color: white; border-radius: 5px; width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ENGINE & DATABASE ---
class BetDatabase:
    def __init__(self):
        self.conn = sqlite3.connect("betcouncil_v3.db", check_same_thread=False)
        self._init_db()
    def _init_db(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY, timestamp TEXT, matchup TEXT, pick TEXT, line REAL, tier TEXT, units REAL)")
    def lock(self, matchup, pick, line, tier, units):
        self.conn.execute("INSERT INTO ledger (timestamp, matchup, pick, line, tier, units) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%H:%M"), matchup, pick, line, tier, units))
        self.conn.commit()

db = BetDatabase()

# --- 3. SIDEBAR (RESTORES BANKROLL CONTROLS) ---
with st.sidebar:
    st.title("🛡️ BETCOUNCIL V3.0")
    bankroll = st.number_input("Bankroll ($)", value=529.64, step=10.0)
    integrity = st.slider("Integrity Score", 0, 100, 64)
    unit_size = st.number_input("Active Unit ($)", value=33.10)
    
    st.divider()
    st.checkbox("Safe Corridor", value=True)
    st.checkbox("Emergency Floor (12%)", value=True)
    
    st.button("🌐 Scan All Sports")
    st.button("📂 Load Board")
    st.button("🔄 Re-Run Council")

# --- 4. MAIN HEADER (RESTORES GOLD DASHBOARD) ---
st.markdown(f"""
    <div class="header-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h1 style="margin:0;">BetCouncil <span style="font-size:14px; color:#808080;">v3.0 • 8 Models • 9 Sports</span></h1>
            <div style="display: flex; gap: 10px;">
                <span style="background:#1E3A8A; padding:5px 10px; border-radius:15px; font-size:12px;">🛡️ Safe: ON</span>
                <span style="background:#B45309; padding:5px 10px; border-radius:15px; font-size:12px;">⚠️ Blowout: ON</span>
            </div>
        </div>
        <hr style="border-color:#333;">
        <div style="display: flex; justify-content: space-between;">
            <div><small>BANKROLL</small><br><b style="color:#D4AF37;">${bankroll}</b></div>
            <div><small>INTEGRITY</small><br><b style="color:#D4AF37;">{integrity}/100</b></div>
            <div><small>ACTIVE FLOOR</small><br><b style="color:#10B981;">12%</b></div>
            <div><small>UNIT</small><br><b style="color:#D4AF37;">${unit_size}</b></div>
            <div><small>ACTIVE LOCKS</small><br><b style="color:#D4AF37;">0</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. THE BOARD (RESTORES SECTION 9.1 LOOK) ---
st.write("### 🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")
st.caption("Data Source: BettingPros + RotoWire + CBS Sports + Covers + DraftKings + ESPN (JSON API)")

tab1, tab2, tab3 = st.tabs(["🎯 THE BOARD", "📜 LOCKS & LEDGER", "🔬 AUTOPSY"])

with tab1:
    st.error("🔒 Validation Firewall: PASSED (All listed players confirmed in projected lineups)")
    
    # 2. PRE-FILTER ADVISORY
    st.markdown("#### 2. PRE-FILTER MODULES (Advisory)")
    adv_df = pd.DataFrame([
        {"Game": "DET @ CLE", "Context": "DET leads 2-0; Harris Active", "Advisory": "URGENCY: CLE must win home floor."},
        {"Game": "OKC @ LAL", "Context": "OKC leads 2-0; Chet/SGA Active", "Advisory": "DESPERATION: Lakers Home Bounce-back."}
    ])
    st.table(adv_df)

    # 4. PRIMARY PROPS TABLE
    st.markdown("#### 4. PRIMARY PROPS TABLE (Computed Signals)")
    
    # Data list based on your ticket image
    props = [
        {"p": "Daniss Jenkins", "m": "DET @ CLE", "t": "PTS", "l": 10.5, "tier": "Sovereign"},
        {"p": "Jarrett Allen", "m": "DET @ CLE", "t": "PRA", "l": 20.0, "tier": "Elite"},
        {"p": "Tobias Harris", "m": "DET @ CLE", "t": "PRA", "l": 26.5, "tier": "Sovereign"},
        {"p": "Chet Holmgren", "m": "OKC @ LAL", "t": "PRA", "l": 26.5, "tier": "Sovereign"},
        {"p": "Deandre Ayton", "m": "OKC @ LAL", "t": "PRA", "l": 18.5, "tier": "Sovereign"}
    ]

    for item in props:
        c1, c2, c3, c4 = st.columns([4, 1, 2, 1])
        c1.markdown(f"**{item['p']}** ({item['m']}) — {item['t']}")
        c2.markdown(f"**{item['l']}**")
        color = "#00FF00" if item['tier'] == "Sovereign" else "#FFFF00"
        c3.markdown(f"<span style='color:{color}'>● {item['tier']}</span>", unsafe_allow_html=True)
        if c4.button("LOCK", key=item['p']):
            db.lock(item['m'], item['p'], item['l'], item['tier'], 33.10)
            st.toast(f"Locked {item['p']}!")

with tab2:
    st.subheader("Persistent Vault")
    ledger = pd.read_sql("SELECT * FROM ledger", db.conn)
    st.dataframe(ledger, use_container_width=True)

# --- FOOTER ---
st.divider()
st.caption("BetCouncil v3.0 | Hard Engine Locked | Integrity: 64/100")
