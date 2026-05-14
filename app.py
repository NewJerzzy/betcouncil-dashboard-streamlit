import streamlit as st
import pandas as pd
from datetime import datetime, date
import re
import requests
from bs4 import BeautifulSoup
import json
import time
import hashlib
import pickle
import os
import unicodedata
from math import exp, factorial

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="BetCouncil v4.4 – Final Edition", page_icon="🛡️", layout="wide")

# CSS (same dark theme – kept as in previous version)
st.markdown("""
<style>
/* Add your dark theme CSS here – unchanged */
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS & CONFIG
# =========================
DEFAULT_BANKROLL = 468.49
KELLY_FRACTION = 0.25
ODDS = -110
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
REQUEST_TIMEOUT = 10
CACHE_DIR = "/tmp/betcouncil_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

EDGE_CAP = 0.20
MIN_EDGE_DEFAULT = 0.02

# Hardcoded player averages (accurate per-game)
PLAYER_AVERAGES = {
    "NBA": {
        "LeBron James": {"PTS": 23.7, "REB": 8.5, "AST": 8.3, "PRA": 40.5},
        "Luka Doncic": {"PTS": 28.1, "REB": 9.3, "AST": 8.7, "PRA": 46.1},
        "Nikola Jokic": {"PTS": 29.4, "REB": 13.0, "AST": 10.2, "PRA": 52.6},
        "Shai Gilgeous-Alexander": {"PTS": 31.5, "REB": 5.5, "AST": 6.5, "PRA": 43.5},
        "Giannis Antetokounmpo": {"PTS": 30.4, "REB": 11.9, "AST": 6.5, "PRA": 48.8},
        "Jayson Tatum": {"PTS": 27.5, "REB": 8.7, "AST": 4.9, "PRA": 41.1},
        "Joel Embiid": {"PTS": 33.1, "REB": 10.2, "AST": 4.2, "PRA": 47.5},
        "Stephen Curry": {"PTS": 26.4, "REB": 4.5, "AST": 5.1, "PRA": 36.0},
        "Kevin Durant": {"PTS": 27.1, "REB": 6.6, "AST": 5.0, "PRA": 38.7},
        "Anthony Davis": {"PTS": 24.7, "REB": 12.6, "AST": 3.5, "PRA": 40.8},
        "Damian Lillard": {"PTS": 24.3, "REB": 4.4, "AST": 7.0, "PRA": 35.7},
        "Devin Booker": {"PTS": 27.1, "REB": 4.5, "AST": 6.9, "PRA": 38.5},
        "Donovan Mitchell": {"PTS": 27.5, "REB": 5.0, "AST": 5.5, "PRA": 38.0},
        "Jimmy Butler": {"PTS": 20.8, "REB": 5.3, "AST": 5.0, "PRA": 31.1},
        "Trae Young": {"PTS": 25.7, "REB": 2.8, "AST": 10.8, "PRA": 39.3},
        "Ja Morant": {"PTS": 25.1, "REB": 5.6, "AST": 8.1, "PRA": 38.8},
        "Zion Williamson": {"PTS": 22.9, "REB": 5.8, "AST": 5.0, "PRA": 33.7},
        "Domantas Sabonis": {"PTS": 19.4, "REB": 13.7, "AST": 8.2, "PRA": 41.3},
        "Karl-Anthony Towns": {"PTS": 21.8, "REB": 8.3, "AST": 3.0, "PRA": 33.1},
        "Bam Adebayo": {"PTS": 20.4, "REB": 10.2, "AST": 3.5, "PRA": 34.1},
        "Rudy Gobert": {"PTS": 14.0, "REB": 12.9, "AST": 1.2, "PRA": 28.1},
    },
    "MLB": {
        "Aaron Judge": {"HR": 0.15, "H": 1.2, "RBI": 0.9, "R": 0.9},
        "Shohei Ohtani": {"HR": 0.14, "H": 1.1, "RBI": 0.8, "R": 0.8},
        "Mookie Betts": {"HR": 0.12, "H": 1.2, "RBI": 0.7, "R": 0.9},
        "Ronald Acuña Jr.": {"HR": 0.13, "H": 1.2, "RBI": 0.8, "R": 0.9},
        "Bryce Harper": {"HR": 0.14, "H": 1.1, "RBI": 0.8, "R": 0.8},
        "Juan Soto": {"HR": 0.13, "H": 1.1, "RBI": 0.8, "R": 0.8},
        "Corey Seager": {"HR": 0.12, "H": 1.1, "RBI": 0.7, "R": 0.7},
        "Mike Trout": {"HR": 0.14, "H": 1.0, "RBI": 0.8, "R": 0.8},
        "Freddie Freeman": {"HR": 0.11, "H": 1.2, "RBI": 0.7, "R": 0.8},
        "Jose Ramirez": {"HR": 0.12, "H": 1.1, "RBI": 0.8, "R": 0.8},
        "Matt Olson": {"HR": 0.15, "H": 1.0, "RBI": 0.9, "R": 0.7},
        "Pete Alonso": {"HR": 0.15, "H": 1.0, "RBI": 0.9, "R": 0.7},
        "Francisco Lindor": {"HR": 0.12, "H": 1.1, "RBI": 0.7, "R": 0.8},
        "Bo Bichette": {"HR": 0.11, "H": 1.2, "RBI": 0.7, "R": 0.8},
        "Vladimir Guerrero Jr.": {"HR": 0.12, "H": 1.2, "RBI": 0.8, "R": 0.8},
    },
    "NFL": {
        "Patrick Mahomes": {"PASS_YDS": 280, "TD": 2.2},
        "Josh Allen": {"PASS_YDS": 260, "RUSH_YDS": 35, "TD": 2.5},
        "Jalen Hurts": {"PASS_YDS": 230, "RUSH_YDS": 45, "TD": 2.2},
        "Lamar Jackson": {"PASS_YDS": 220, "RUSH_YDS": 65, "TD": 2.0},
        "Joe Burrow": {"PASS_YDS": 270, "TD": 2.0},
        "Justin Herbert": {"PASS_YDS": 265, "TD": 2.0},
        "Dak Prescott": {"PASS_YDS": 260, "TD": 2.0},
        "Trevor Lawrence": {"PASS_YDS": 250, "TD": 1.8},
        "Kirk Cousins": {"PASS_YDS": 260, "TD": 2.0},
        "Christian McCaffrey": {"RUSH_YDS": 85, "REC_YDS": 45, "TD": 1.0},
        "Derrick Henry": {"RUSH_YDS": 90, "TD": 0.9},
        "Saquon Barkley": {"RUSH_YDS": 80, "REC_YDS": 35, "TD": 0.8},
        "Tyreek Hill": {"REC_YDS": 95, "TD": 0.8},
        "Justin Jefferson": {"REC_YDS": 90, "TD": 0.7},
        "Ja'Marr Chase": {"REC_YDS": 85, "TD": 0.7},
        "Travis Kelce": {"REC_YDS": 70, "TD": 0.6},
    },
    "NHL": {
        "Connor McDavid": {"PTS": 1.5, "GOALS": 0.6, "ASSISTS": 0.9, "SOG": 3.5},
        "Leon Draisaitl": {"PTS": 1.4, "GOALS": 0.6, "ASSISTS": 0.8, "SOG": 3.2},
        "Nathan MacKinnon": {"PTS": 1.4, "GOALS": 0.5, "ASSISTS": 0.9, "SOG": 3.4},
        "David Pastrnak": {"PTS": 1.2, "GOALS": 0.6, "ASSISTS": 0.6, "SOG": 3.5},
        "Mikko Rantanen": {"PTS": 1.3, "GOALS": 0.5, "ASSISTS": 0.8, "SOG": 3.0},
        "Nikita Kucherov": {"PTS": 1.5, "GOALS": 0.5, "ASSISTS": 1.0, "SOG": 3.0},
        "Auston Matthews": {"PTS": 1.2, "GOALS": 0.7, "ASSISTS": 0.5, "SOG": 3.7},
        "Mitch Marner": {"PTS": 1.2, "GOALS": 0.4, "ASSISTS": 0.8, "SOG": 2.8},
        "Artemi Panarin": {"PTS": 1.2, "GOALS": 0.5, "ASSISTS": 0.7, "SOG": 3.1},
        "Kirill Kaprizov": {"PTS": 1.1, "GOALS": 0.5, "ASSISTS": 0.6, "SOG": 3.2},
        "Cale Makar": {"PTS": 0.9, "GOALS": 0.2, "ASSISTS": 0.7, "SOG": 2.5},
        "Roman Josi": {"PTS": 0.8, "GOALS": 0.2, "ASSISTS": 0.6, "SOG": 2.5},
    }
}

AVERAGES_LAST_UPDATED = "2025-05-13"  # Update manually when you change the dict

# Sport-aware stat name normalization (simplified)
STAT_NORMALIZE = {
    ("NBA", "Points"): "PTS", ("NBA", "Rebounds"): "REB", ("NBA", "Assists"): "AST",
    ("NBA", "Pts+Reb+Ast"): "PRA",
    ("MLB", "Home Runs"): "HR", ("MLB", "Hits"): "H", ("MLB", "RBIs"): "RBI", ("MLB", "Runs"): "R",
    ("NFL", "Passing Yards"): "PASS_YDS", ("NFL", "Rushing Yards"): "RUSH_YDS",
    ("NFL", "Receiving Yards"): "REC_YDS", ("NFL", "Touchdowns"): "TD",
    ("NHL", "Points"): "PTS", ("NHL", "Goals"): "GOALS", ("NHL", "Assists"): "ASSISTS",
    ("NHL", "Shots On Goal"): "SOG",
}
DEFAULT_AVERAGES = {
    "NBA": {"PTS": 10.0, "REB": 4.0, "AST": 2.5, "PRA": 16.5},
    "MLB": {"HR": 0.05, "H": 0.8, "RBI": 0.3, "R": 0.3},
    "NFL": {"PASS_YDS": 200, "RUSH_YDS": 35, "REC_YDS": 40, "TD": 0.5},
    "NHL": {"PTS": 0.45, "GOALS": 0.18, "ASSISTS": 0.27, "SOG": 1.8},
}

# =========================
# UTILITIES
# =========================
def normalize_name(name):
    """Normalize player name: remove accents, lowercase, strip common suffixes."""
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    name = re.sub(r'\s+(jr|sr|ii|iii)\.?$', '', name, flags=re.I)
    return name.strip().lower()

def find_player_avg(player_name, avgs_dict):
    """Fuzzy match player name to hardcoded averages."""
    # Exact match
    if player_name in avgs_dict:
        return avgs_dict[player_name], False
    # Normalized match
    norm_target = normalize_name(player_name)
    for key, val in avgs_dict.items():
        if normalize_name(key) == norm_target:
            return val, False
    return {}, True  # not found

def poisson_prob_over(line, avg_per_game):
    """P(X > line) for Poisson distribution, used for low-base stats like HR."""
    k = int(line)  # e.g., line 0.5 -> k=0
    p_under = sum((avg_per_game**i * exp(-avg_per_game)) / factorial(i) for i in range(k+1))
    return 1 - p_under

def compute_edge(line, player_avg, stat, sport, side="OVER"):
    """
    Compute edge and implied probability.
    Uses Poisson model for binary-like stats (HR, etc.), else normal deviation model.
    """
    if player_avg <= 0:
        return 0, 0.5

    # Determine if stat is binary (low average, line is 0.5)
    is_binary = (player_avg < 0.5 and line <= 1.0) or stat in ["HR", "Home Runs", "TD"]
    if is_binary:
        prob = poisson_prob_over(line, player_avg)
        if side.upper() == "OVER":
            edge = prob - 0.5
        else:
            edge = 0.5 - prob
        edge = max(-EDGE_CAP, min(EDGE_CAP, edge))
        prob = max(0.3, min(0.7, prob))
        return edge, prob

    # Normal percentage deviation model
    diff = (line - player_avg) / player_avg
    if side.upper() == "OVER":
        edge = -diff
    else:
        edge = diff
    edge = max(-EDGE_CAP, min(EDGE_CAP, edge))
    prob = 0.5 + edge
    prob = max(0.3, min(0.7, prob))
    return edge, prob

def kelly_unit(prob, bankroll, odds=-110):
    if prob <= 0.5:
        return 0
    b = 100 / abs(odds) if odds < 0 else odds / 100
    q = 1 - prob
    kelly = (b * prob - q) / b
    if kelly <= 0:
        return 0
    fractional = kelly * KELLY_FRACTION
    wager = fractional * bankroll
    return round(min(wager, bankroll * 0.25), 2)

# =========================
# CACHE HELPERS
# =========================
def cached_fetch(url, ttl_minutes=30):
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        age = (time.time() - mtime) / 60
        if age < ttl_minutes:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            with open(cache_path, "wb") as f:
                pickle.dump(resp.text, f)
            return resp.text
        else:
            return None
    except:
        return None

# =========================
# PRIZEPICKS SCRAPER (with cache empty guard and URL order swap)
# =========================
def scrape_prizepicks(sport):
    league_ids = {"NBA":4,"MLB":5,"NHL":3,"NFL":7,"WNBA":8,"UFC":6,"Golf":11,"Tennis":12,"Soccer":2}
    league = league_ids.get(sport.upper())
    if not league:
        return []
    # Broader URL first (no state_code), then CA-scoped as fallback
    urls = [
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true",
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code=CA&game_mode=prizepools"
    ]
    headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://app.prizepicks.com/"}
    all_props = []
    seen = set()

    for url in urls:
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}_prize.pkl")
        data = None

        # Check cache
        if os.path.exists(cache_path):
            mtime = os.path.getmtime(cache_path)
            age = (time.time() - mtime) / 60
            if age < 20:
                with open(cache_path, "rb") as f:
                    data = pickle.load(f)
                # If cached data is None or empty, treat as cache miss
                if not data or not data.get("data"):
                    data = None

        if data is None:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    # Cache only if non-empty
                    if data.get("data"):
                        with open(cache_path, "wb") as f:
                            pickle.dump(data, f)
                    else:
                        # Don't cache empty responses
                        data = None
                else:
                    continue
            except:
                continue

        if not data or not data.get("data"):
            continue

        # Parse data
        players = {item["id"]: item["attributes"]["name"] for item in data.get("included",[]) if item["type"]=="new_player"}
        for proj in data["data"]:
            if proj["type"] != "projection":
                continue
            attrs = proj["attributes"]
            pid = proj["relationships"]["new_player"]["data"]["id"]
            name = players.get(pid, "Unknown")
            line = attrs.get("line_score")
            stat = attrs.get("stat_type")
            if not (name and line is not None and stat):
                continue
            try:
                line = float(line)
            except:
                continue
            key = (sport, pid, stat, line)
            if key in seen:
                continue
            seen.add(key)
            all_props.append({"Player":name,"Prop":stat,"Line":line,"Side":"OVER","Sport":sport,"source":"PrizePicks"})

    return all_props

# =========================
# GAME LINES – ESPN scoreboard (matchups only)
# =========================
def fetch_game_lines(sport):
    slug_map = {"NBA":"basketball/nba","MLB":"baseball/mlb","NFL":"football/nfl","NHL":"hockey/nhl"}
    path = slug_map.get(sport.lower(), "")
    if not path:
        return []
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            games = []
            for event in data.get("events", []):
                matchup = event.get("shortName", "")
                games.append({"Matchup": matchup, "Spread": "N/A", "Total": "N/A", "Sport": sport})
            return games
        else:
            return []
    except:
        return []

# =========================
# MAIN LOAD FUNCTION (with fuzzy name matching and binary stat handling)
# =========================
def load_sport_data(sport):
    avgs = PLAYER_AVERAGES.get(sport, {})
    default = DEFAULT_AVERAGES.get(sport, DEFAULT_AVERAGES["NBA"])
    props = scrape_prizepicks(sport)
    if not props:
        st.warning(f"No props from PrizePicks for {sport}. Check later.")
        return [], []
    min_edge = st.session_state.get("min_edge", MIN_EDGE_DEFAULT)
    skip_defaults = st.session_state.get("skip_defaults", True)
    enriched = []
    for p in props:
        stat_raw = p["Prop"]
        stat_norm = STAT_NORMALIZE.get((sport, stat_raw), stat_raw)
        player = p["Player"]
        side = p["Side"]  # "OVER"

        # Find player average (fuzzy match)
        player_stats, not_found = find_player_avg(player, avgs)
        if not_found:
            if skip_defaults:
                continue
            avg = default.get(stat_norm, p["Line"])
            using_default = True
        else:
            avg = player_stats.get(stat_norm, default.get(stat_norm, p["Line"]))
            using_default = False

        edge, prob = compute_edge(p["Line"], avg, stat_raw, sport, side)
        p["PlayerAvg"] = avg
        p["Edge"] = edge
        p["Prob"] = prob
        p["KellyWager"] = kelly_unit(prob, st.session_state.bankroll)
        p["DataQuality"] = "Lookup" if not using_default else "Default (unreliable)"
        if edge >= min_edge:
            enriched.append(p)
    if not enriched:
        st.info(f"No props with edge ≥ {min_edge*100}% found. Try lowering min edge or check later.")
        return [], []
    return enriched, fetch_game_lines(sport)

# =========================
# SESSION STATE
# =========================
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "locks" not in st.session_state: st.session_state.locks = []
if "history" not in st.session_state: st.session_state.history = []
if "site_status" not in st.session_state: st.session_state.site_status = {}
if "min_edge" not in st.session_state: st.session_state.min_edge = MIN_EDGE_DEFAULT
if "skip_defaults" not in st.session_state: st.session_state.skip_defaults = True
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("# 🛡️ BetCouncil v4.4")
    st.markdown(f"*Averages: {AVERAGES_LAST_UPDATED}*")
    st.session_state.bankroll = st.number_input("Bankroll ($)", value=st.session_state.bankroll, step=10.0)
    st.session_state.min_edge = st.slider("Minimum Edge (%)", 0, 10, int(st.session_state.min_edge*100), step=1) / 100.0
    st.session_state.skip_defaults = st.checkbox("Skip unreliable players (no season avg)", value=st.session_state.skip_defaults)
    st.markdown("---")
    sport = st.selectbox("Sport", ["NBA","MLB","NFL","NHL","WNBA"], index=["NBA","MLB","NFL","NHL","WNBA"].index(st.session_state.last_sport))
    if st.button("Load Board", use_container_width=True):
        with st.spinner(f"Fetching {sport} props from PrizePicks..."):
            board, games = load_sport_data(sport)
            st.session_state.board_data = board
            st.session_state.games = games
            st.session_state.last_sport = sport
        st.success(f"{len(board)} props with edge ≥ {st.session_state.min_edge*100}%")
    st.markdown("---")
    st.metric("Bankroll", f"${st.session_state.bankroll:.2f}")
    if st.button("Reset Bankroll", use_container_width=True):
        st.session_state.bankroll = DEFAULT_BANKROLL
        st.rerun()

# =========================
# TABS
# =========================
tabs = st.tabs(["📊 Props", "🏟️ Game Lines", "🔒 Locks", "📈 History", "⚙️ System"])

# PROPS TAB
with tabs[0]:
    if st.session_state.get("board_data"):
        df = pd.DataFrame(st.session_state.board_data)
        display_cols = ["Player","Prop","Line","PlayerAvg","Edge","Prob","KellyWager","DataQuality"]
        styled_df = df[display_cols].style.format({
            "Edge": "{:.2%}",
            "Prob": "{:.1%}",
            "KellyWager": "${:.2f}"
        })
        st.dataframe(styled_df)
        if len(df) > 0:
            options = [f"{row['Player']} {row['Prop']} OVER {row['Line']} (Edge: {row['Edge']:.1%})" for _, row in df.iterrows()]
            selected_idx = st.selectbox("Select prop to lock", range(len(options)), format_func=lambda i: options[i])
            if st.button("🔒 Lock Selected"):
                row = df.iloc[selected_idx]
                st.session_state.locks.append({
                    "player": row["Player"],
                    "prop": row["Prop"],
                    "line": row["Line"],
                    "side": "OVER",
                    "wager": row["KellyWager"],
                    "prob": row["Prob"],
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success(f"Locked {row['Player']} – wagered ${row['KellyWager']:.2f}")
                st.rerun()
    else:
        st.info("Select a sport and click 'Load Board'.")

# GAME LINES TAB
with tabs[1]:
    if st.session_state.get("games"):
        st.table(pd.DataFrame(st.session_state.games))
    else:
        st.info("Game lines (matchups only) – use sportsbook for live odds.")

# LOCKS TAB (with Push/Void button)
with tabs[2]:
    if st.session_state.locks:
        locks_copy = st.session_state.locks.copy()
        for i, lock in enumerate(locks_copy):
            col1, col2, col3, col4 = st.columns([3,1,1,1])
            col1.write(f"{lock['player']} {lock['side']} {lock['line']} {lock['prop']} – Wager: ${lock['wager']:.2f}")
            if col2.button("✅ WIN", key=f"win_{i}"):
                profit = lock['wager'] * (100 / 110)
                st.session_state.bankroll += profit
                entry = {**lock, "outcome": "WIN", "profit": profit, "loss": 0, "net": profit}
                st.session_state.history.append(entry)
                st.session_state.locks = [l for j,l in enumerate(st.session_state.locks) if j != i]
                st.rerun()
            if col3.button("❌ LOSS", key=f"loss_{i}"):
                st.session_state.bankroll -= lock['wager']
                entry = {**lock, "outcome": "LOSS", "profit": 0, "loss": lock['wager'], "net": -lock['wager']}
                st.session_state.history.append(entry)
                st.session_state.locks = [l for j,l in enumerate(st.session_state.locks) if j != i]
                st.rerun()
            if col4.button("🔄 VOID", key=f"void_{i}"):
                # Void: no change to bankroll, just remove lock, record as void
                entry = {**lock, "outcome": "VOID", "profit": 0, "loss": 0, "net": 0}
                st.session_state.history.append(entry)
                st.session_state.locks = [l for j,l in enumerate(st.session_state.locks) if j != i]
                st.rerun()
    else:
        st.info("No active locks.")

# HISTORY TAB (with P&L summary)
with tabs[3]:
    if st.session_state.history:
        # Compute summary stats
        total_net = sum(h.get("net", 0) for h in st.session_state.history)
        wins = sum(1 for h in st.session_state.history if h.get("outcome") == "WIN")
        losses = sum(1 for h in st.session_state.history if h.get("outcome") == "LOSS")
        voids = sum(1 for h in st.session_state.history if h.get("outcome") == "VOID")
        hit_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
        col1, col2, col3 = st.columns(3)
        col1.metric("Record", f"{wins}W - {losses}L - {voids}V")
        col2.metric("Net P&L", f"${total_net:.2f}")
        col3.metric("Hit Rate", f"{hit_rate:.1%}")
        st.markdown("---")
        # Show history table
        history_df = pd.DataFrame(st.session_state.history)
        st.table(history_df[["player","prop","line","side","wager","outcome","profit","loss","net","timestamp"]])
    else:
        st.info("No bet history yet.")

# SYSTEM TAB
with tabs[4]:
    st.write("**System Status**")
    st.write(f"Bankroll: ${st.session_state.bankroll:.2f}")
    st.write(f"Minimum Edge: {st.session_state.min_edge*100}%")
    st.write(f"Skip unreliable players: {'Yes' if st.session_state.skip_defaults else 'No'}")
    st.write(f"Player averages last updated: {AVERAGES_LAST_UPDATED}")
    st.write("---")
    st.write("**Data Sources**")
    st.write("- Player averages: Hardcoded (manual, reliable). Update the `PLAYER_AVERAGES` dict as needed.")
    st.write("- Props: PrizePicks public API (cached 20 min, empty responses not cached).")
    st.write("- Game lines: ESPN scoreboard (matchups only – no odds).")
    st.write("---")
    st.write("**How edge is calculated**")
    st.write("- For binary stats (HR, TD, etc.): Poisson probability model.")
    st.write("- For counting stats (points, yards): Line vs. player average deviation.")
    st.write("Kelly wager uses quarter-Kelly with -110 odds.")
    st.write("---")
    st.write("**Fixes in v4.4**")
    st.write("✅ Cache empty-response guard\n✅ Name normalization (accents, suffixes)\n✅ Poisson model for HR/TD\n✅ History P&L summary\n✅ Push/Void button\n✅ URL order swap (broader first)")
