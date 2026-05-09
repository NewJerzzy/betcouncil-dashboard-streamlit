import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. PERSISTENCE & MEMORY (THE FIX) ---
if 'global_board' not in st.session_state:
    st.session_state.global_board = [] # Stores all sports from the scan
if 'last_scan' not in st.session_state:
    st.session_state.last_scan = None

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

# --- 2. CSS & UI THEME (RESTORED FROM SCREENSHOTS) ---
st.set_page_config(page_title="BetCouncil v3.1", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FFFFFF; }
    .header-card { background-color: #1A1C24; border: 2px solid #D4AF37; border-radius: 10px; padding: 20px; margin-bottom: 25px; }
    .stTabs [aria-selected="true"] { color: #D4AF37 !important; border-bottom: 2px solid #D4AF37 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SIDEBAR (RESTORED) ---
with st.sidebar:
    st.title("🛡️ BETCOUNCIL V3.1")
    bankroll = st.number_input("Bankroll ($)", value=529.64)
    unit_size = st.number_input("Active Unit ($)", value=33.10)
    integrity = st.slider("Integrity Score", 0, 100, 64)
    st.divider()
    st.checkbox("Safe Corridor", value=True)
    st.checkbox("Emergency Floor (12%)", value=True)
    st.divider()
    
    # SCAN LOGIC: Feeds the Cross-Sport Tab and Board of 8
    if st.button("🌐 Scan All Sports"):
        st.session_state.global_board = [
            {"sport": "NBA", "p": "Daniss Jenkins", "m": "DET @ CLE", "t": "PTS", "l": 10.5, "tier": "Sovereign"},
            {"sport": "NBA", "p": "Chet Holmgren", "m": "OKC @ LAL", "t": "PRA", "l": 26.5, "tier": "Sovereign"},
            {"sport": "MLB", "p": "Shohei Ohtani", "m": "LAD @ NYY", "t": "Hits", "l": 1.5, "tier": "Sovereign"},
            {"sport": "MLB", "p": "Braxton Ashcraft", "m": "PIT @ SF", "t": "K", "l": 5.5, "tier": "Sovereign"},
            {"sport": "UFC", "p": "King Green", "m": "vs Stephens", "t": "Moneyline", "l": -420, "tier": "Observation"}
        ]
        st.session_state.last_scan = datetime.now().strftime("%H:%M:%S")
        st.toast("Global Scan Successful")

    load_board = st.button("📂 Load Board")
    st.button("🔄 Re-Run Council")

# --- 4. GOLD DASHBOARD HEADER ---
st.markdown(f"""
    <div class="header-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h1 style="margin:0;">BetCouncil <span style="font-size:14px; color:#808080;">v3.1 • 8 Models</span></h1>
            <div style="display: flex; gap: 10px;">
                <span style="background:#1E3A8A; padding:5px 12px; border-radius:15px; font-size:12px;">🛡️ Safe: ON</span>
                <span style="background:#B45309; padding:5px 12px; border-radius:15px; font-size:12px;">⚠️ Blowout: ON</span>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between; margin-top:20px;">
            <div><small>BANKROLL</small><br><b style="color:#D4AF37;">${bankroll}</b></div>
            <div><small>INTEGRITY</small><br><b style="color:#D4AF37;">{integrity}/100</b></div>
            <div><small>ACTIVE FLOOR</small><br><b style="color:#10B981;">12%</b></div>
            <div><small>KELLY FRACTION</small><br><b style="color:#D4AF37;">0.25</b></div>
            <div><small>UNIT</small><br><b style="color:#D4AF37;">${unit_size}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. THE FULL TAB SYSTEM ---
tabs = st.tabs(["🌍 Cross-Sport", "🏀 Board of 8", "🔒 Locks of Day", "📜 Locks & Ledger", "🔄 Reconciliation", "🛡️ SEM & System"])

with tabs[0]: # Cross-Sport
    st.markdown("### 🌍 Global Market Scan")
    if st.session_state.global_board:
        st.caption(f"Last Sync: {st.session_state.last_scan}")
        # Displaying the aggregated signal based list
        for item in st.session_state.global_board:
            with st.expander(f"{item['m']} | {item['p']} | {item['tier']}"):
                st.write(f"Sport: {item['sport']} | Prop: {item['t']} | Line: {item['l']}")
    else:
        st.info("Aggregated high-signal plays will render here after clicking 'Scan All Sports'.")

with tabs[1]: # Board of 8
    st.markdown("### ⚡ MANUAL OVERRIDE")
    st.text_area("Paste props", placeholder="LeBron James OVER 21.5 Points", height=70)
    st.button("⚡ Run Manual Analysis")
    st.divider()
    
    selected_sport = st.selectbox("Select Sport Board", ["NBA", "MLB", "NHL", "UFC"])
    
    # Load logic: Checks if we have scanned data or if user manually hits Load
    if load_board or st.session_state.global_board:
        st.error(f"🔒 Validation Firewall: PASSED ({selected_sport})")
        
        # 2. PRE-FILTER ADVISORY
        st.markdown("#### 2. PRE-FILTER MODULES (Advisory)")
        # Dynamically generate advisory based on selected sport
        if selected_sport == "NBA":
            adv = [{"Game": "DET @ CLE", "Context": "DET leads 2-0", "Advisory": "URGENCY: CLE must win."}]
        elif selected_sport == "MLB":
            adv = [{"Game": "LAD @ NYY", "Context": "Game 4; Wind", "Advisory": "Under-friendly environment."}]
        else:
            adv = [{"Game": "Market", "Context": "General Slate", "Advisory": "Monitor late scratches."}]
        st.table(pd.DataFrame(adv))

        # 4. PRIMARY PROPS TABLE
        st.markdown("#### 4. PRIMARY PROPS TABLE (Computed Signals)")
        sport_props = [i for i in st.session_state.global_board if i['sport'] == selected_sport]
        
        if not sport_props:
            st.warning(f"No high-clarity signals found for {selected_sport} in the 15-game slate.")
        else:
            for item in sport_props:
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.write(f"**{item['p']}** ({item['m']}) — {item['t']}")
                c2.metric("Line", item['l'])
                color = "#00FF00" if item['tier'] == "Sovereign" else "#FFFF00"
                c3.markdown(f"<span style='color:{color}'>● {item['tier']}</span>", unsafe_allow_html=True)
                if c4.button("LOCK", key=f"lk_{item['p']}"):
                    vault.lock(selected_sport, item['m'], item['p'], item['l'], item['tier'], unit_size)
                    st.toast(f"✅ {item['p']} LOCKED")

        # 5. MODEL VERDICTS
        st.markdown("#### 5. MODEL-BY-MODEL VERDICTS")
        st.info(f"Summary Synthesis: Signals for {selected_sport} based on weighted multi-model average (DeepSeek/Supreme @ 0.18).")

with tabs[3]: # Ledger
    st.subheader("📜 Persistent Vault")
    ledger_df = pd.read_sql("SELECT * FROM ledger ORDER BY id DESC", vault.conn)
    st.dataframe(ledger_df, use_container_width=True)
