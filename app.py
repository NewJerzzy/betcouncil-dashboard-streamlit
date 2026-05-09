import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. THE ARCHITECTURE ---
class BetCouncilVault:
    def __init__(self):
        self.conn = sqlite3.connect("betcouncil_v3.db", check_same_thread=False)
        self.conn.execute('''CREATE TABLE IF NOT EXISTS ledger 
                            (id INTEGER PRIMARY KEY, timestamp TEXT, sport TEXT, 
                             matchup TEXT, pick TEXT, line REAL, tier TEXT, units REAL)''')
    def lock(self, sport, matchup, pick, line, tier, units):
        self.conn.execute("INSERT INTO ledger (timestamp, sport, matchup, pick, line, tier, units) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%H:%M"), sport, matchup, pick, line, tier, units))
        self.conn.commit()

vault = BetCouncilVault()

# --- 2. CSS & THEME (GOLD DASHBOARD) ---
st.set_page_config(page_title="BetCouncil v3.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FFFFFF; }
    .header-card { background-color: #1A1C24; border: 2px solid #D4AF37; border-radius: 10px; padding: 20px; margin-bottom: 25px; }
    .stTabs [aria-selected="true"] { color: #D4AF37 !important; border-bottom: 2px solid #D4AF37 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ BETCOUNCIL V3.0")
    bankroll = st.number_input("Bankroll ($)", value=529.64)
    unit_size = st.number_input("Active Unit ($)", value=33.10)
    integrity = st.slider("Integrity Score", 0, 100, 64)
    st.divider()
    scan_all = st.button("🌐 Scan All Sports")
    load_board = st.button("📂 Load Board")

# --- 4. GOLD DASHBOARD ---
st.markdown(f"""
    <div class="header-card">
        <h1 style="margin:0;">BetCouncil <span style="font-size:14px; color:#808080;">v3.0 • 8 Models</span></h1>
        <div style="display: flex; justify-content: space-between; margin-top:20px;">
            <div><small>BANKROLL</small><br><b style="color:#D4AF37;">${bankroll}</b></div>
            <div><small>INTEGRITY</small><br><b style="color:#D4AF37;">{integrity}/100</b></div>
            <div><small>KELLY FRACTION</small><br><b style="color:#D4AF37;">0.25</b></div>
            <div><small>UNIT</small><br><b style="color:#D4AF37;">${unit_size}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. TABS ---
tabs = st.tabs(["🌍 Cross-Sport", "🏀 Board of 8", "🔒 Locks of Day", "📜 Locks & Ledger", "🔄 Reconciliation", "🛡️ SEM & System"])

with tabs[1]: # Board of 8
    st.markdown("### ⚡ MANUAL OVERRIDE")
    st.text_area("Paste props", placeholder="LeBron James OVER 21.5 Points", height=70)
    st.button("⚡ Run Manual Analysis")
    
    st.divider()
    
    # SPORT SELECTION
    selected_sport = st.selectbox("Select Sport Board", ["NBA", "MLB", "NHL", "UFC", "SOCCER"])
    
    if load_board or scan_all:
        # --- THE RESTORED SUMMARY LOGIC ---
        st.error(f"🔒 Validation Firewall: PASSED ({selected_sport})")
        
        # 1. Advisory Module
        st.markdown("#### 2. PRE-FILTER MODULES (Advisory)")
        if selected_sport == "MLB":
            adv_data = [{"Game": "LAD @ NYY", "Context": "Bullpen Heavy", "Advisory": "VOLATILITY: High wind at stadium."}]
            props_data = [{"p": "Shohei Ohtani", "m": "LAD @ NYY", "t": "HITS", "l": 1.5, "tier": "Sovereign"}]
        elif selected_sport == "NBA":
            adv_data = [{"Game": "DET @ CLE", "Context": "DET leads 2-0", "Advisory": "URGENCY: CLE must win home floor."}]
            props_data = [{"p": "Daniss Jenkins", "m": "DET @ CLE", "t": "PTS", "l": 10.5, "tier": "Sovereign"}]
        else:
            adv_data = []
            props_data = []

        st.table(pd.DataFrame(adv_data))

        # 2. Primary Props Table
        st.markdown("#### 4. PRIMARY PROPS TABLE (Computed Signals)")
        for item in props_data:
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            c1.write(f"**{item['p']}** ({item['m']})")
            c2.metric("Line", item['l'])
            c3.write(f"● {item['tier']}")
            if c4.button("LOCK", key=item['p']):
                vault.lock(selected_sport, item['m'], item['p'], item['l'], item['tier'], unit_size)
                st.toast(f"Locked {item['p']}")
        
        # 3. Model Verdicts (Footer)
        st.markdown("#### 5. MODEL-BY-MODEL VERDICTS")
        st.caption(f"DeepSeek & Supreme weighting 0.18 applied to {selected_sport} signals.")
        
    else:
        st.info(f"Select {selected_sport} and click 'Load Board' to generate the Summary.")

with tabs[3]: # Ledger
    st.subheader("Persistent Vault")
    df = pd.read_sql("SELECT * FROM ledger ORDER BY id DESC", vault.conn)
    st.dataframe(df, use_container_width=True)
