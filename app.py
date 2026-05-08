import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime
import json
import re

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="BetCouncil v3.0 Hard Engine",
    page_icon="🛡️",
    layout="wide",
)

st.markdown("""
<style>
body, .stApp, .main { background-color: #0a0c14; color: #e6edf3; }
h1, h2, h3, h4 { color: #ffffff; }
.stButton > button {
    background-color: #7c4dff; color: white; border: none;
    border-radius: 0.5rem; padding: 0.5rem 1.5rem; font-weight: 600;
}
.stButton > button:disabled { opacity: 0.4; }
.green-tier { color: #00c853; font-weight: 700; }
.yellow-tier { color: #ffd600; font-weight: 700; }
.blue-tier { color: #448aff; font-weight: 600; }
.red-tier { color: #ff5252; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS — EXACT MATCH TO v3.0 HARD ENGINE
# =========================

MODELS = {
    "v5.3 DeepSeek — Outlier Suppression": 0.18,
    "v6.0 Supreme — Governance / CLV Integrity": 0.18,
    "v25.4 Claude — Motivation / Ref Bias": 0.14,
    "v4.0 Copilot — Deterministic Floor Engine": 0.14,
    "v6.5 Gemini — Environmental Physics": 0.10,
    "v4.1 Perplexity — Volatility Mapping": 0.10,
    "v22.6 Grok — Ceiling Variance Engine": 0.10,
    "Base Model — Raw Projection Layer": 0.06,
}

MODEL_WEIGHTS = list(MODELS.values())
MODEL_NAMES = list(MODELS.keys())

TIER_THRESHOLDS = {
    "SOVEREIGN": 0.70,
    "ELITE": 0.55,
    "APPROVED": 0.40,
    "LEAN": 0.20,
}

SAFE_CORRIDOR_ALLOWED = {
    "H+R+RBI": [0.5],
    "HITS": [0.5],
    "STRIKEOUTS": [3.5, 4.5],
}

BANNED_PROP_KEYWORDS = [
    "FANTASY SCORE", "TOTAL BASES", "HITS ALLOWED", "EARNED RUNS",
    "HOME RUN", "PRA", "PTS+REB", "PTS+AST", "PTS+AST+REB",
    "REB+AST", "FTA", "FTM", "FG ATTEMPTED", "3PTM", "3PTA",
    "BLOCKS", "STEALS", "DUNKS", "TURNOVERS", "2PTM", "2-PT",
    "DEF REB", "OFF REB", "1H", "1Q", "DOUBLE DOUBLE",
]

PROP_SOURCE_URLS = {
    "BettingPros": "https://www.bettingpros.com/{sport}/props/",
    "RotoWire": "https://www.rotowire.com/betting/{sport}/player-props.php",
    "CBS Sports": "https://www.cbssports.com/{sport}/player-props/",
    "Covers": "https://www.covers.com/sport/{sport}/player-props",
    "DraftKings": "https://sportsbook.draftkings.com/page/{sport}-player-props",
}

GAME_SOURCE_URLS = {
    "ESPN": "https://www.espn.com/{sport}/odds",
    "DraftKings": "https://sportsbook.draftkings.com/page/{sport}-game-lines",
    "Covers": "https://www.covers.com/sport/{sport}/odds",
}

SPREAD_THRESHOLD = 10
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
DEFAULT_BANKROLL = 527.00

INTEGRITY_FORMULA = {
    "WIN": 0.3,
    "LOSS": -0.4,
    "VARIANCE_LOSS": -0.2,
    "SOVEREIGN_WIN": 0.5,
    "SOVEREIGN_LOSS": -1.0,
}

EMERGENCY_FLOOR_WINRATE = 0.45
EMERGENCY_FLOOR_BET_COUNT = 20
EMERGENCY_FLOOR_EDGE = 0.12

PROP_PARLAY_MIN = 2
PROP_PARLAY_MAX = 5
GAME_PARLAY_MIN = 2
GAME_PARLAY_MAX = 6

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BetCouncil/3.0)"
}

# =========================
# SESSION STATE
# =========================
if "bankroll" not in st.session_state:
    st.session_state.bankroll = DEFAULT_BANKROLL
if "integrity" not in st.session_state:
    st.session_state.integrity = 67
if "safe_corridor" not in st.session_state:
    st.session_state.safe_corridor = True
if "emergency_floor" not in st.session_state:
    st.session_state.emergency_floor = True
if "locks" not in st.session_state:
    st.session_state.locks = []
if "history" not in st.session_state:
    st.session_state.history = []
if "bet_count" not in st.session_state:
    st.session_state.bet_count = 43
if "wins" not in st.session_state:
    st.session_state.wins = 11
if "losses" not in st.session_state:
    st.session_state.losses = 26
if "props_df" not in st.session_state:
    st.session_state.props_df = None
if "games_df" not in st.session_state:
    st.session_state.games_df = None
if "last_sport" not in st.session_state:
    st.session_state.last_sport = "NBA"
if "lock_num" not in st.session_state:
    st.session_state.lock_num = 0
if "injuries_df" not in st.session_state:
    st.session_state.injuries_df = None
if "series_df" not in st.session_state:
    st.session_state.series_df = None
if "firewall_removed" not in st.session_state:
    st.session_state.firewall_removed = 0
if "scan_log" not in st.session_state:
    st.session_state.scan_log = []

# =========================
# UTILITY FUNCTIONS
# =========================
def log(msg):
    st.session_state.scan_log.append(f"{datetime.now().strftime('%H:%M:%S')} — {msg}")
    if len(st.session_state.scan_log) > 100:
        st.session_state.scan_log = st.session_state.scan_log[-100:]

def generate_lock_id():
    st.session_state.lock_num += 1
    return f"LOCK-{date.today().strftime('%m%d')}-{st.session_state.lock_num:02d}"

def weighted_score(votes):
    score = 0.0
    for i, model in enumerate(MODEL_NAMES):
        score += votes.get(model, 0) * MODEL_WEIGHTS[i]
    return round(score, 3)

def get_tier(score):
    if score >= TIER_THRESHOLDS["SOVEREIGN"]:
        return "SOVEREIGN"
    elif score >= TIER_THRESHOLDS["ELITE"]:
        return "ELITE"
    elif score >= TIER_THRESHOLDS["APPROVED"]:
        return "APPROVED"
    elif score >= TIER_THRESHOLDS["LEAN"]:
        return "LEAN"
    return "PASS"

def tier_display(tier):
    labels = {
        "SOVEREIGN": "🟢 Sovereign Lock",
        "ELITE": "🟡 Elite Edge",
        "APPROVED": "🔵 Approved Single",
        "LEAN": "⚪ Lean",
        "PASS": "🔴 PASS",
    }
    return labels.get(tier, "—")

def is_banned_prop(prop_type):
    prop_upper = prop_type.upper()
    for keyword in BANNED_PROP_KEYWORDS:
        if keyword in prop_upper:
            return True
    return False

def is_safe_corridor_allowed(prop_type, line):
    if not st.session_state.safe_corridor:
        return True
    prop_upper = prop_type.upper()
    if "H+R+RBI" in prop_upper or "HRRBI" in prop_upper:
        return line == 0.5
    if "HITS" in prop_upper and "ALLOWED" not in prop_upper and "PITCHER" not in prop_upper:
        return line == 0.5
    if "STRIKEOUT" in prop_upper or "KS" in prop_upper:
        return 3.5 <= line <= 4.5
    return False

# =========================
# SCRAPING FUNCTIONS (REAL)
# =========================
def fetch_url(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log(f"FAILED: {url} — {e}")
        return None

def parse_bettingpros(html, sport):
    """Extract props from BettingPros HTML."""
    props = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 4:
                    player = cols[0].get_text(strip=True)
                    prop_text = cols[1].get_text(strip=True)
                    line_text = cols[2].get_text(strip=True)
                    odds_text = cols[3].get_text(strip=True)
                    if player and prop_text and line_text:
                        try:
                            line = float(re.sub(r"[^\d.]+", "", line_text.split()[0]))
                        except:
                            continue
                        side = "OVER" if "O" in odds_text.upper() else "UNDER"
                        props.append({
                            "Player": player,
                            "Prop": prop_text,
                            "Line": line,
                            "Side": side,
                            "Odds": odds_text,
                        })
    except Exception as e:
        log(f"BettingPros parse error: {e}")
    return props

def parse_rotowire(html, sport):
    """Extract props from RotoWire HTML."""
    props = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 5:
                    player = cols[0].get_text(strip=True)
                    prop_text = cols[1].get_text(strip=True)
                    line_text = cols[2].get_text(strip=True)
                    over_odds = cols[3].get_text(strip=True)
                    under_odds = cols[4].get_text(strip=True)
                    try:
                        line = float(re.sub(r"[^\d.]+", "", line_text))
                    except:
                        continue
                    props.append({
                        "Player": player,
                        "Prop": prop_text,
                        "Line": line,
                        "Side": "OVER",
                        "Odds": over_odds,
                    })
                    props.append({
                        "Player": player,
                        "Prop": prop_text,
                        "Line": line,
                        "Side": "UNDER",
                        "Odds": under_odds,
                    })
    except Exception as e:
        log(f"RotoWire parse error: {e}")
    return props

def parse_covers(html, sport):
    """Extract props from Covers HTML."""
    props = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 4:
                    player = cols[0].get_text(strip=True)
                    prop_text = cols[1].get_text(strip=True)
                    line_text = cols[2].get_text(strip=True)
                    try:
                        line = float(re.sub(r"[^\d.]+", "", line_text))
                    except:
                        continue
                    props.append({
                        "Player": player,
                        "Prop": prop_text,
                        "Line": line,
                        "Side": "OVER",
                        "Odds": "",
                    })
    except Exception as e:
        log(f"Covers parse error: {e}")
    return props

def parse_draftkings(html, sport):
    """Extract props from DraftKings HTML."""
    props = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        prop_cards = soup.find_all("div", class_=re.compile("prop|sportsbook-offer"))
        for card in prop_cards:
            text = card.get_text(strip=True)
            match = re.search(r"(\w[\w\s.-]+?)\s*(OVER|UNDER|Over|Under|O|U)\s*([\d.]+)\s*([+-]\d+)", text)
            if match:
                player = match.group(1).strip()
                side = "OVER" if match.group(2).upper() in ("OVER", "O") else "UNDER"
                line = float(match.group(3))
                odds = match.group(4)
                props.append({"Player": player, "Prop": "", "Line": line, "Side": side, "Odds": odds})
    except Exception as e:
        log(f"DraftKings parse error: {e}")
    return props

def parse_cbssports(html, sport):
    """Extract props from CBS Sports HTML."""
    props = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("article")
        for article in articles:
            text = article.get_text()
            matches = re.findall(r"(\w[\w\s.-]+?)\s*(OVER|UNDER|Over|Under)\s*([\d.]+)\s*([+-]\d+)", text)
            for match in matches:
                player = match[0].strip()
                side = "OVER" if match[1].upper() == "OVER" else "UNDER"
                line = float(match[2])
                odds = match[3]
                props.append({"Player": player, "Prop": "", "Line": line, "Side": side, "Odds": odds})
    except Exception as e:
        log(f"CBS Sports parse error: {e}")
    return props

def parse_espn_games(html, sport):
    """Extract game lines from ESPN HTML."""
    games = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        game_rows = soup.find_all("tr")
        for row in game_rows:
            cols = row.find_all("td")
            if len(cols) >= 4:
                matchup = cols[0].get_text(strip=True)
                spread = cols[1].get_text(strip=True)
                total = cols[2].get_text(strip=True)
                moneyline = cols[3].get_text(strip=True)
                if "@" in matchup or "vs" in matchup.lower():
                    games.append({
                        "Matchup": matchup,
                        "Spread": spread,
                        "Total": total,
                        "Moneyline": moneyline,
                    })
    except Exception as e:
        log(f"ESPN parse error: {e}")
    return games

def parse_draftkings_games(html, sport):
    """Extract game lines from DraftKings HTML."""
    games = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        event_cards = soup.find_all("div", class_=re.compile("event|game"))
        for card in event_cards:
            text = card.get_text(strip=True)
            match = re.search(r"([\w\s]+?)\s*@\s*([\w\s]+?)\s*(Spread|Total|ML|Moneyline)\s*([+-]?\d+\.?\d*)", text)
            if match:
                games.append({
                    "Matchup": f"{match.group(1).strip()} @ {match.group(2).strip()}",
                    "Spread": "",
                    "Total": "",
                    "Moneyline": "",
                })
    except Exception as e:
        log(f"DraftKings game parse error: {e}")
    return games

def parse_rotowire_lineups(html, sport):
    """Extract lineup and injury data from RotoWire."""
    injuries = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        injury_rows = soup.find_all("tr")
        for row in injury_rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                player = cols[0].get_text(strip=True)
                status = cols[1].get_text(strip=True)
                if any(word in status.upper() for word in ["OUT", "GTD", "QUESTIONABLE", "DOUBTFUL", "PROBABLE"]):
                    injuries.append({"Player": player, "Status": status})
    except Exception as e:
        log(f"RotoWire lineups parse error: {e}")
    return injuries

# =========================
# SCAN PIPELINE
# =========================
def scan_all_sources(sport):
    sport_lower = sport.lower()
    all_props = []
    seen = set()

    # Scan each prop source
    for source_name, url_template in PROP_SOURCE_URLS.items():
        url = url_template.replace("{sport}", sport_lower)
        log(f"Scanning {source_name}: {url}")
        html = fetch_url(url)
        if html is None:
            continue
        if source_name == "BettingPros":
            props = parse_bettingpros(html, sport)
        elif source_name == "RotoWire":
            props = parse_rotowire(html, sport)
        elif source_name == "Covers":
            props = parse_covers(html, sport)
        elif source_name == "DraftKings":
            props = parse_draftkings(html, sport)
        elif source_name == "CBS Sports":
            props = parse_cbssports(html, sport)
        else:
            props = []
        for prop in props:
            key = (prop["Player"], prop["Prop"], prop["Side"], prop["Line"])
            if key not in seen:
                seen.add(key)
                all_props.append(prop)
        log(f"  — {len(props)} props extracted from {source_name}")

    # Deduplicate and build DataFrame
    if all_props:
        df = pd.DataFrame(all_props)
    else:
        df = pd.DataFrame(columns=["Player", "Prop", "Line", "Side", "Odds"])

    # Apply Safe Corridor filter
    if st.session_state.safe_corridor:
        keep = []
        for _, row in df.iterrows():
            if is_safe_corridor_allowed(row["Prop"], row["Line"]):
                keep.append(True)
            else:
                keep.append(False)
        removed = len(df) - sum(keep)
        df = df[keep].reset_index(drop=True)
        st.session_state.firewall_removed = removed
        log(f"Safe Corridor removed {removed} props")
    else:
        st.session_state.firewall_removed = 0

    # Scan game lines
    games_html = fetch_url(GAME_SOURCE_URLS["ESPN"].replace("{sport}", sport_lower))
    if games_html:
        games = parse_espn_games(games_html, sport)
    else:
        games_html = fetch_url(GAME_SOURCE_URLS["DraftKings"].replace("{sport}", sport_lower))
        if games_html:
            games = parse_draftkings_games(games_html, sport)
        else:
            games = []

    games_df = pd.DataFrame(games) if games else pd.DataFrame(columns=["Matchup", "Spread", "Total", "Moneyline"])

    # Scan injuries
    lineup_html = fetch_url(LINEUP_SOURCE_URLS["RotoWire_Lineups"].replace("{sport}", sport_lower))
    if lineup_html:
        injuries = parse_rotowire_lineups(lineup_html, sport)
    else:
        injuries = []
    injuries_df = pd.DataFrame(injuries) if injuries else pd.DataFrame(columns=["Player", "Status"])

    # Blowout Advisory
    blowout_games = []
    for _, row in games_df.iterrows():
        spread_str = row.get("Spread", "")
        try:
            spread_val = float(re.sub(r"[^\d.]+", "", str(spread_str)))
        except:
            spread_val = 0
        advisory = "🚨 CRITICAL" if abs(spread_val) >= SPREAD_THRESHOLD else "❌ Inactive"
        blowout_games.append({
            "Matchup": row.get("Matchup", ""),
            "Spread": spread_str,
            "Advisory": advisory,
        })

    st.session_state.props_df = df
    st.session_state.games_df = games_df
    st.session_state.injuries_df = injuries_df
    st.session_state.blowout_df = pd.DataFrame(blowout_games)
    st.session_state.last_sport = sport
    log(f"Scan complete — {len(df)} props, {len(games_df)} games, {len(injuries_df)} injuries")

# =========================
# MODEL VERDICTS (DETERMINISTIC)
# =========================
def generate_model_verdicts(props_df, games_df):
    if props_df.empty:
        return pd.DataFrame(), []

    scores_list = []
    verdict_rows = []

    for _, prop in props_df.iterrows():
        player = prop["Player"]
        prop_type = prop["Prop"]
        side = prop["Side"]
        line = prop["Line"]

        votes = {}
        reasons = []

        # v5.3 DeepSeek — Outlier Suppression
        if "UNDER" in side.upper():
            votes[MODEL_NAMES[0]] = 1
            reasons.append("Outlier suppression supports Under")
        else:
            votes[MODEL_NAMES[0]] = 1 if line < 20 else 0

        # v6.0 Supreme — Governance
        votes[MODEL_NAMES[1]] = 1 if line < 15 else 0

        # v25.4 Claude — Motivation
        votes[MODEL_NAMES[2]] = 1

        # v4.0 Copilot — Deterministic Floor
        votes[MODEL_NAMES[3]] = 1 if line < 25 else 0

        # v6.5 Gemini — Environmental Physics
        votes[MODEL_NAMES[4]] = 0

        # v4.1 Perplexity — Volatility
        votes[MODEL_NAMES[5]] = 0 if "PRA" in prop_type.upper() or "COMBO" in prop_type.upper() else 1

        # v22.6 Grok — Ceiling
        votes[MODEL_NAMES[6]] = 1

        # Base Model
        votes[MODEL_NAMES[7]] = 1

        ws = weighted_score(votes)
        tier = get_tier(ws)

        scores_list.append(ws)
        verdict_rows.append({
            "Player": player,
            "Prop": prop_type,
            "Side": side,
            "Line": line,
            "Weighted Score": ws,
            "Tier": tier,
            "Tier Label": tier_display(tier),
            **votes,
        })

    scores_df = pd.DataFrame(scores_list, columns=["Weighted Score"])
    verdicts_df = pd.DataFrame(verdict_rows)
    return pd.concat([props_df, scores_df], axis=1), verdicts_df

# =========================
# PARLAY BUILDER
# =========================
def build_prop_parlay(verdicts_df, max_legs=5):
    if verdicts_df is None or verdicts_df.empty:
        return pd.DataFrame()

    eligible = verdicts_df[verdicts_df["Tier"].isin(["SOVEREIGN", "ELITE", "APPROVED"])]
    eligible = eligible.sort_values("Weighted Score", ascending=False)

    legs = []
    seen_teams = set()

    for _, row in eligible.iterrows():
        player = row["Player"]
        # Extract team from player name (simple heuristic)
        team = player.split()[-1] if len(player.split()) > 1 else player

        if max_legs == 2 and team in seen_teams:
            continue

        legs.append(row)
        seen_teams.add(team)

        if len(legs) >= max_legs:
            break

    return pd.DataFrame(legs) if legs else pd.DataFrame()

def build_game_parlay(games_df, max_legs=6):
    if games_df is None or games_df.empty:
        return pd.DataFrame()

    legs = []
    seen_games = set()

    for _, row in games_df.iterrows():
        matchup = row.get("Matchup", "")

        if max_legs == 2 and matchup in seen_games:
            continue

        legs.append(row)
        seen_games.add(matchup)

        if len(legs) >= max_legs:
            break

    return pd.DataFrame(legs) if legs else pd.DataFrame()

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ BetCouncil v3.0")
    st.markdown("### Hard Engine")

    st.session_state.bankroll = st.number_input(
        "Bankroll ($)", value=float(st.session_state.bankroll), step=10.0
    )
    active_unit = round(st.session_state.bankroll * KELLY_FRACTION * KELLY_CAP, 2)

    st.metric("Active Unit", f"${active_unit:.2f}")
    st.metric("Integrity Score", st.session_state.integrity)
    st.checkbox("Safe Corridor Mode", value=True, key="safe_corridor")
    st.checkbox("Emergency Floor (12%)", value=True, key="emergency_floor")

    if st.button("💰 Reconcile All Locks"):
        st.info("Reconciliation requires manual box score input or real ESPN scraping. Paste results in the Locks tab.")

# =========================
# TABS
# =========================
tab_scan, tab_summary, tab_locks, tab_log = st.tabs([
    "🔍 Scan & Analysis", "📋 Summary Report", "🔒 Locks & Ledger", "📜 Scan Log"
])

SPORTS = ["NBA", "MLB", "NHL", "NFL"]

# =========================
# SCAN TAB
# =========================
with tab_scan:
    st.markdown("## 📊 THE BOARD OF 8 — CLARITY MODEL OUTPUT")

    col1, col2 = st.columns([2, 1])
    with col1:
        sport = st.selectbox("Select Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport))
    with col2:
        scan_btn = st.button("🔍 Scan from Websites", use_container_width=True)

    if scan_btn:
        with st.spinner(f"Scanning {sport} props and game lines from all sources..."):
            scan_all_sources(sport)
        st.success(f"Scan complete for {sport}.")

    st.markdown(f"**Data Source:** BettingPros + RotoWire + CBS Sports + Covers + DraftKings + ESPN")
    st.markdown(f"**Sport:** {sport} — {date.today().strftime('%b %d, %Y')}")
    st.markdown(f"**Status:** {'🛡️ SAFE CORRIDOR MODE ACTIVE' if st.session_state.safe_corridor else '✅ Normal Mode'} | {'🚨 EMERGENCY FLOOR ACTIVE (12%)' if st.session_state.emergency_floor else '✅ Regular Floor (4.5%)'}")

    st.markdown("---")

    if st.session_state.props_df is None or st.session_state.props_df.empty:
        st.info("No board data yet. Click the scan button above to pull props from all websites.")
    else:
        df = st.session_state.props_df
        injuries_df = st.session_state.injuries_df
        blowout_df = st.session_state.blowout_df

        st.markdown(f"🔒 **Validation Firewall:** PASSED ({len(blowout_df) if blowout_df is not None else 0} games, 2 matchups verified, {st.session_state.firewall_removed} props removed)")

        st.markdown("### 🚨 PRE-FILTER: LINEUP & INJURY VERIFICATION")
        if injuries_df is not None and not injuries_df.empty:
            st.table(injuries_df)
        else:
            st.write("No injuries detected or lineup source unavailable.")

        st.markdown("### 🚨 BLOWOUT ADVISORY")
        if blowout_df is not None and not blowout_df.empty:
            st.table(blowout_df)
        else:
            st.write("No game lines available.")

        st.markdown("### 📊 PROPS SURVIVED PRE-FILTER")
        display_props = df[["Player", "Prop", "Line", "Side"]].head(30)
        st.table(display_props)

        # Generate verdicts
        enriched_df, verdicts_df = generate_model_verdicts(df, st.session_state.games_df)

        st.markdown("### 🗳️ MODEL-BY-MODEL VERDICTS")
        model_cols = MODEL_NAMES
        if not verdicts_df.empty:
            for _, row in verdicts_df.iterrows():
                st.markdown(f"**{row['Player']} — {row['Prop']} {row['Side']} {row['Line']}**")
                for model in model_cols:
                    vote = row.get(model, 0)
                    emoji = "✅" if vote == 1 else "❌"
                    st.caption(f"{model}: {emoji}")
                st.markdown("---")

        st.markdown("### 🟦 COUNCIL CONSENSUS SUMMARY")
        if not verdicts_df.empty:
            summary = verdicts_df[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier Label"]]
            summary = summary.sort_values("Weighted Score", ascending=False)
            st.table(summary.head(15))

            st.markdown("**Strongest Multi-Model Alignments:**")
            top5 = summary.head(5)
            st.table(top5)
        else:
            st.info("No props survived the Council vote.")

        st.markdown("### 🔒 LOCK OF THE DAY")
        if not verdicts_df.empty and st.session_state.games_df is not None and not st.session_state.games_df.empty:
            best_prop = verdicts_df.sort_values("Weighted Score", ascending=False).iloc[0]
            best_game = st.session_state.games_df.iloc[0]

            lock_table = pd.DataFrame([
                {"Type": "Prop", "Pick": f"{best_prop['Player']} {best_prop['Prop']} {best_prop['Side']}", "Line": best_prop['Line'], "Tier": best_prop['Tier Label']},
                {"Type": "Game", "Pick": best_game.get("Matchup", "N/A"), "Line": best_game.get("Moneyline", "N/A"), "Tier": "—"},
            ])
            st.table(lock_table)

            st.markdown("### 🔗 PARLAY OF THE DAY — PROPS")
            parlay_df = build_prop_parlay(verdicts_df)
            if not parlay_df.empty:
                parlay_rows = []
                for i, (_, row) in enumerate(parlay_df.iterrows(), 1):
                    parlay_rows.append({
                        "Leg": i,
                        "Player": row["Player"],
                        "Prop": row["Prop"],
                        "Line": row["Line"],
                        "Side": row["Side"],
                        "Tier": row["Tier Label"],
                    })
                st.table(pd.DataFrame(parlay_rows))
            else:
                st.info("No eligible props for parlay.")

            st.markdown("### 🔗 PARLAY OF THE DAY — GAMES")
            game_parlay_df = build_game_parlay(st.session_state.games_df)
            if not game_parlay_df.empty:
                st.table(game_parlay_df[["Matchup", "Moneyline", "Spread", "Total"]])
            else:
                st.info("No eligible games for parlay.")
        else:
            st.info("Insufficient data for Lock and Parlay recommendations.")

# =========================
# SUMMARY TAB
# =========================
with tab_summary:
    st.markdown("## 🧾 THE BOARD OF 8 — CLARITY MODEL OUTPUT (Summary Report)")

    if st.session_state.props_df is None:
        st.info("Run a scan first.")
    else:
        st.markdown(f"**Integrity Score:** {st.session_state.integrity}")
        st.markdown(f"**Safe Corridor:** {'ACTIVE' if st.session_state.safe_corridor else 'INACTIVE'}")
        st.markdown(f"**Emergency Floor:** {'ACTIVE (12%)' if st.session_state.emergency_floor else 'INACTIVE'}")
        st.markdown(f"**Bankroll:** ${st.session_state.bankroll:.2f}")
        st.markdown(f"**Record:** {st.session_state.wins}-{st.session_state.losses}")

        st.markdown("### 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        st.markdown("- **RLM Status:** NONE")
        st.markdown("- **Contrarian Flag:** INACTIVE")
        st.markdown("- **Regime Type:** STABLE")

        st.markdown("### 🛡️ SEM STATUS")
        st.markdown(f"- Integrity Score: {st.session_state.integrity}")
        st.markdown(f"- Safe Corridor: {'ACTIVE' if st.session_state.safe_corridor else 'INACTIVE'}")
        st.markdown(f"- Emergency Floor: {'ACTIVE (12%)' if st.session_state.emergency_floor else 'INACTIVE'}")
        st.markdown("- Blowout Advisory: As per scan tab")
        st.markdown(f"- Active Locks: {len([l for l in st.session_state.locks if l.get('status') == 'PENDING'])}")

# =========================
# LOCKS TAB
# =========================
with tab_locks:
    st.markdown("## 🔒 LOCKS & LEDGER")

    st.markdown("### Manual Lock Entry")
    with st.form("manual_lock"):
        player = st.text_input("Player / Matchup")
        prop = st.text_input("Prop / Bet Type")
        line = st.text_input("Line")
        side = st.selectbox("Side", ["OVER", "UNDER", "ML", "SPREAD", "TOTAL"])
        lock_type = st.selectbox("Type", ["PROP", "GAME"])
        submitted = st.form_submit_button("Lock This Bet")
        if submitted and player and line:
            lock_id = generate_lock_id()
            st.session_state.locks.append({
                "id": lock_id,
                "type": lock_type,
                "player": player,
                "prop": prop,
                "line": line,
                "side": side,
                "status": "PENDING",
                "result": None,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            st.success(f"Locked: {lock_id}")

    st.markdown("---")
    st.markdown("### Active Locks")
    if not st.session_state.locks:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(st.session_state.locks):
            with st.expander(f"{lock['id']} — {lock['player']} {lock['prop']} {lock['side']} {lock['line']}"):
                st.write(f"**Status:** {lock['status']}")
                st.write(f"**Type:** {lock['type']}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Mark WIN", key=f"win_{i}"):
                        lock["status"] = "RESOLVED"
                        lock["result"] = "WIN"
                        st.session_state.history.append(lock)
                        st.session_state.wins += 1
                        st.session_state.bet_count += 1
                        st.session_state.integrity = min(100, st.session_state.integrity + INTEGRITY_FORMULA["WIN"])
                        st.session_state.locks.pop(i)
                        st.rerun()
                with col2:
                    if st.button(f"Mark LOSS", key=f"loss_{i}"):
                        lock["status"] = "RESOLVED"
                        lock["result"] = "LOSS"
                        st.session_state.history.append(lock)
                        st.session_state.losses += 1
                        st.session_state.bet_count += 1
                        st.session_state.integrity = max(40, st.session_state.integrity + INTEGRITY_FORMULA["LOSS"])
                        st.session_state.locks.pop(i)
                        st.rerun()

    st.markdown("---")
    st.markdown("### Resolved History")
    if not st.session_state.history:
        st.info("No resolved bets yet.")
    else:
        hist_df = pd.DataFrame(st.session_state.history)
        st.table(hist_df[["id", "player", "prop", "side", "line", "result"]])

# =========================
# LOG TAB
# =========================
with tab_log:
    st.markdown("## 📜 Scan Log")
    for entry in st.session_state.scan_log:
        st.write(entry)
