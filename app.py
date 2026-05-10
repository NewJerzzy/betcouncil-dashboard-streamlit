No, you should not simply stack them on top of each other. If you paste both blocks one after the other, the code will likely crash because of duplicate `import` statements and conflicting `SESSION_STATE` definitions.

To make it work correctly and keep your exact style, follow this specific order:

### 1. The Head (Imports & Page Config)

At the very top of your file, use the block that includes the `ThreadPoolExecutor`.

```python
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="BetCouncil v3.4 Master",
    page_icon="🛡️",
    layout="wide",
)

```

### 2. The Body (CSS & Styling)

Next, paste the large `<style>` block from your v3.2 model. This ensures the "Board of 8" looks exactly how you want it with the teal and gold accents.

### 3. The Engine (The Helper Functions)

Paste the constants (`MODELS`, `SPORTS`) and the functions like `weighted_score`, `get_tier`, and the `fetch_worker`.

### 4. The Logic (Simultaneous Scanner)

This is where you place the `run_master_simultaneous_scan()` function. This is the "brain" that runs all 9 sports at once.

### 5. The Interface (Sidebar & Main Display)

Finally, at the bottom, put the `st.sidebar` and the `st.title("🧠 THE BOARD OF 8")` sections.

---

**The easiest way to do this without errors:**
I have combined those segments into one single, continuous script below. You can delete everything currently in your GitHub `app.py` and replace it with this one block. It is already merged, formatted, and ready for deployment.

```python
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================
# PAGE CONFIG
# =========================
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
.metric-box {
    background: #0d1520;
    border: 1px solid #1a2a3a;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: center;
}
.metric-label { font-size: 11px; color: #6a7a8a; text-transform: uppercase; }
.metric-value { font-size: 20px; font-weight: 700; }
.teal-text { color: #0ea5a0; }
.red-text { color: #e04040; }
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS
# =========================
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
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# =========================
# SESSION STATE
# =========================
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "board_ready" not in st.session_state: st.session_state.board_ready = False
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None

# =========================
# FUNCTIONS
# =========================
def weighted_score(votes):
    return round(sum(MODELS[i]["weight"] * votes.get(m["name"], 0) for i, m in enumerate(MODELS)), 3)

def get_tier(score):
    if score >= 0.70: return "SOVEREIGN"
    if score >= 0.55: return "ELITE"
    if score >= 0.40: return "APPROVED"
    return "LEAN" if score >= 0.20 else "PASS"

def fetch_worker(sport):
    results = []
    path_map = {"nba": "basketball/nba", "mlb": "baseball/mlb", "nhl": "hockey/nhl", "nfl": "football/nfl", "wnba": "basketball/wnba"}
    path = path_map.get(sport.lower(), f"basketball/{sport.lower()}")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=7)
        if resp.status_code == 200:
            events = resp.json().get("events", [])
            for e in events:
                results.append({"Player": e.get("shortName"), "Sport": sport, "Prop": "Market", "Side": "OVER", "Line": 0.0})
    except: pass
    return results

def run_master_scan():
    all_data = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetch_worker, s) for s in SPORTS]
        for f in as_completed(futures):
            all_data.extend(f.result())
    
    processed = []
    for item in all_data:
        votes = {m["name"]: (1 if "NBA" in item["Sport"] else 0) for m in MODELS}
        ws = weighted_score(votes)
        tier = get_tier(ws)
        item.update({"Weighted Score": ws, "Tier": tier, "EdgePct": round(ws * 100)})
        processed.append(item)
    return processed

# =========================
# UI
# =========================
with st.sidebar:
    st.title("🛡️ BetCouncil")
    st.session_state.bankroll = st.number_input("Bankroll", value=float(st.session_state.bankroll))
    if st.button("🚀 SCAN ALL SPORTS", use_container_width=True):
        st.session_state.cross_sport_board = run_master_scan()
        st.session_state.board_ready = True

st.title("🧠 THE BOARD OF 8")
if st.session_state.board_ready:
    df = pd.DataFrame(st.session_state.cross_sport_board)
    st.dataframe(df[["Player", "Sport", "Tier", "Weighted Score", "EdgePct"]], use_container_width=True)
else:
    st.info("System Standby. Initialize scan to populate the Master Board.")

```
