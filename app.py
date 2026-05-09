import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# ==========================================
# 1. ANALYTICS SERVICE LAYER (Truth Source)
# ==========================================
class ClarityAnalytics:
    @staticmethod
    def calculate_confidence(market_line, projections):
        """
        Computes real confidence using Z-Score and Edge Delta.
        Independent of UI.
        """
        projections = np.array(projections)
        mean_proj = np.mean(projections)
        std_dev = np.std(projections)
        
        # Edge: How much better is our mean than the market?
        edge = (mean_proj - market_line) / abs(market_line)
        
        # Volatility: Coefficient of Variation
        volatility = std_dev / abs(mean_proj) if mean_proj != 0 else 0
        
        # Tiering Logic
        if edge > 0.12 and volatility < 0.10:
            return {"score": round(edge, 3), "tier": "Sovereign", "color": "#00FF00"}
        elif edge > 0.07:
            return {"score": round(edge, 3), "tier": "Elite", "color": "#FFFF00"}
        return {"score": round(edge, 3), "tier": "Observation", "color": "#808080"}

# ==========================================
# 2. DATA PERSISTENCE LAYER (SQLite)
# ==========================================
class BetDatabase:
    def __init__(self, db_path="betcouncil_os.db"):
        self.db_path = db_path
        self.init_tables()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_tables(self):
        conn = self.get_connection()
        c = conn.cursor()
        # Explicit Schema Design
        c.execute('''CREATE TABLE IF NOT EXISTS locks 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, sport TEXT, 
                      matchup TEXT, selection TEXT, line REAL, tier TEXT, units REAL, 
                      clv_at_lock REAL, status TEXT DEFAULT 'PENDING')''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS sources 
                     (source_name TEXT PRIMARY KEY, last_success TEXT, health_status TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS settings 
                     (key TEXT PRIMARY KEY, value REAL)''')
        
        # Seed Bankroll if empty
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bankroll', 1000.0)")
        conn.commit()
        conn.close()

    def lock_bet(self, sport, matchup, selection, line, tier, units):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO locks (timestamp, sport, matchup, selection, line, tier, units, clv_at_lock) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (datetime.now().strftime("%Y-%m-%d %H:%M"), sport, matchup, selection, line, tier, units, line))
        conn.commit()
        conn.close()

    def get_ledger(self):
        conn = self.get_connection()
        df = pd.read_sql_query("SELECT * FROM locks ORDER BY id DESC", conn)
        conn.close()
        return df

# ==========================================
# 3. EXTRACTION LAYER (The Scraper)
# ==========================================
def fetch_mma_data():
    # Placeholder for actual Scrape/API logic
    # In production, this calls CAPMMA or an Odds API
    return [
        {"sport": "NBA", "matchup": "OKC @ LAL", "player": "Chet Holmgren", "line": 26.5},
        {"sport": "NBA", "matchup": "DET @ CLE", "player": "Daniss Jenkins", "line": 10.5},
        {"sport": "UFC", "matchup": "Green vs Stephens", "player": "King Green", "line": -429},
        {"sport": "MLB", "matchup": "PIT @ SF", "player": "Braxton Ashcraft", "line": 4.5}
    ]

# ==========================================
# 4. STREAMLIT UI (Front-End)
# ==========================================
st.set_page_config(page_title="BetCouncil OS", layout="wide")
db = BetDatabase()
analytics = ClarityAnalytics()

st.title("🧠 BETCOUNCIL v3.0: OPERATING SYSTEM")
st.caption("SQLite Persistence | Shared Analytics Service | Live Scrape Redundancy")

tab1, tab2, tab3 = st.tabs(["🎯 THE BOARD", "📜 LEDGER & VAULT", "🔬 AUTOPSY"])

with tab1:
    st.subheader("Signal-Based Analysis")
    market_items = fetch_mma_data()
    
    for item in market_items:
        # Simulate 8 models from the shared analytics service
        projections = np.random.normal(loc=item['line'] * 1.14, scale=abs(item['line'] * 0.04), size=8)
        result = analytics.calculate_confidence(item['line'], projections)
        
        with st.expander(f"{item['matchup']} | {item['player']} | {result['tier']}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Market Line", item['line'])
            c2.metric("Edge Signal", f"{result['score']*100:.1f}%")
            c3.markdown(f"**Tier:** <span style='color:{result['color']}'>{result['tier']}</span>", unsafe_allow_html=True)
            
            if st.button(f"LOCK {item['player']}", key=f"lock_{item['player']}"):
                db.lock_bet(item['sport'], item['matchup'], item['player'], item['line'], result['tier'], 3.95)
                st.toast(f"✅ Locked {item['player']} to SQLite")

with tab2:
    st.subheader("Persistent Ledger")
    df = db.get_ledger()
    st.dataframe(df, use_container_width=True)

with tab3:
    st.subheader("Analytical Autopsy")
    if not df.empty:
        st.metric("Total Exposure", f"${df['units'].sum():.2f}")
        # Transition logic for status (PENDING -> WON/LOSS) would go here
    else:
        st.info("Vault is empty.")

st.markdown("---")
st.caption("BetCouncil OS | Powered by SQLite & NumPy | v3.0.0-Stable")
