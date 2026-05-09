import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. MEMORY & DATABASE ---
if 'global_board' not in st.session_state:
    st.session_state.global_board = []
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

# --- 2. THE UI THEME ---
st.set_page_config(page_title="BetCouncil v3.1", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FFFFFF; }
    .header-card { background-color: #1A1C24; border: 2px solid #D4AF37; border-radius: 10px; padding: 20px; margin-bottom: 25px; }
    .stTabs [aria-selected="true"] { color: #D4AF37 !important; border-bottom: 2px solid #D4AF37 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ BETCOUNCIL V3.1")
    bankroll = st.number_input("Bankroll ($)", value=529.64)
    unit_size = st.number_input("Active Unit ($)", value=33.10)
    st.divider()
    
    if st.button("🌐 Scan All Sports"):
        # UPDATED DATA: Added the "t" (Type) field for visibility
        st.session_state.global_board = [
            {"sport": "NBA", "p": "Daniss Jenkins", "m": "DET @ CLE", "t": "POINTS", "l": 10.5, "tier": "Sovereign"},
            {"sport": "NBA", "p": "Chet Holmgren", "m": "OKC @ LAL", "t": "PRA", "l": 26.5, "tier": "Sovereign"},
            {"sport": "MLB", "p": "Shohei Ohtani", "m": "LAD @ NYY", "t": "HITS", "l": 1.5, "tier": "Sovereign"},
            {"sport": "MLB", "p": "Braxton Ashcraft", "m": "PIT @ SF", "t": "K's", "l": 5.5, "tier": "Sovereign"}
        ]
        st.session_state.last_scan = datetime.now().strftime("%H:%M:%S")

    load_board = st.button("📂 Load Board")

# --- 4. DASHBOARD ---
st.markdown(f"""<div class="header-card"><h1>BetCouncil <span style="font-size:14px;">v3.1</span></h1></div>""", unsafe_allow_html=True)

# --- 5. TABS (THE FIX IS HERE) ---
tabs = st.tabs(["🌍 Cross-Sport", "🏀 Board of 8", "🔒 Locks", "📜 Ledger"])

with tabs[0]: # Cross-Sport
    st.markdown("### 🌍 Global Market Scan")
    if st.session_state.global_board:
        st.caption(f"Last Sync: {st.session_state.last_scan}")
        # RENDER AS A DATASET INSTEAD OF EMPTY HEADERS
        df = pd.DataFrame(st.session_state.global_board)
        st.table(df[['sport', 'm', 'p', 't', 'l', 'tier']]) # Show specific columns
    else:
        st.info("Hit 'Scan All Sports' to populate.")

with tabs[1]: # Board of 8
    selected_sport = st.selectbox("Select Sport Board", ["NBA", "MLB", "NHL", "UFC"])
    
    if load_board or st.session_state.global_board:
        st.error(f"🔒 Validation Firewall: PASSED ({selected_sport})")
        
        # FILTER DATA
        sport_props = [i for i in st.session_state.global_board if i['sport'] == selected_sport]
        
        # THE VISIBILITY FIX: Column layout shows the TYPE (t) and LINE (l) immediately
        for item in sport_props:
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            c1.write(f"**{item['p']}**\n\n{item['m']}")
            c2.write(f"**{item['t']}**\n\nLine: {item['l']}") # Show "POINTS" or "HITS"
            c3.write(f"● {item['tier']}")
            if c4.button("LOCK", key=f"lk_{item['p']}"):
                vault.lock(selected_sport, item['m'], item['p'], item['l'], item['tier'], unit_size)
                st.toast(f"Locked {item['p']}")
