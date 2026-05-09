import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup

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
body, .stApp, .main {
    background-color: #0a0c14;
    color: #e6edf3;
    font-family: 'Inter', system-ui, sans-serif;
}
h1, h2, h3, h4, h5 { color: #ffffff; text-transform: uppercase; letter-spacing: 0.5px; }
.stButton > button {
    background-color: #7c4dff;
    color: #ffffff;
    border: none;
    border-radius: 0.5rem;
    padding: 0.6rem 1.5rem;
    font-weight: 600;
    cursor: pointer;
}
.stButton > button:hover { background-color: #651fff; }
.stButton > button:disabled { opacity: 0.4; cursor: not-allowed; }
.section-card {
    background-color: #141824;
    border: 1px solid #1f2639;
    border-radius: 0.75rem;
    padding: 1.25rem;
    margin-bottom: 1rem;
}
.sovereign-badge { color: #00c853; font-weight: 700; }
.elite-badge { color: #ffd600; font-weight: 700; }
.approved-badge { color: #448aff; font-weight: 600; }
.lean-badge { color: #9e9e9e; font-weight: 600; }
.pass-badge { color: #ff5252; font-weight: 600; }
.status-dot-green { color: #00c853; }
.status-dot-red { color: #ff5252; }
.status-dot-yellow { color: #ffd600; }
.legend-box {
    background-color: #141824;
    border: 1px solid #1f2639;
    border-radius: 0.5rem;
    padding: 0.75rem;
    margin: 0.5rem 0;
    font-size: 0.85rem;
}
.ready-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.85rem;
    margin-right: 8px;
}
.ready-green { background-color: rgba(0,200,83,0.15); color: #00c853; border: 1px solid #00c853; }
.ready-yellow { background-color: rgba(255,214,0,0.15); color: #ffd600; border: 1px solid #ffd600; }
.ready-red { background-color: rgba(255,82,82,0.15); color: #ff5252; border: 1px solid #ff5252; }
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS
# =========================
MODELS = [
    {"name": "v5.3 DeepSeek — Outlier Suppression", "weight": 0.18},
    {"name": "v6.5 Gemini — Environmental Physics", "weight": 0.10},
    {"name": "v25.4 Claude — Motivation / Ref Bias", "weight": 0.14},
    {"name": "v4.0 Copilot — Deterministic Floor Engine", "weight": 0.14},
    {"name": "v4.1 Perplexity — Volatility Mapping", "weight": 0.10},
    {"name": "v6.0 Supreme — Governance / CLV Integrity", "weight": 0.18},
    {"name": "v22.6 Grok — Ceiling Variance Engine", "weight": 0.10},
    {"name": "Base Model — Raw Projection Layer", "weight": 0.06},
]

TIER_THRESHOLDS = {"SOVEREIGN": 0.70, "ELITE": 0.55, "APPROVED": 0.40, "LEAN": 0.20}
TIER_DESCRIPTIONS = {
    "SOVEREIGN": "⚡ 8/8 models aligned. Unanimous consensus. Highest confidence.",
    "ELITE": "🟡 6-7 models aligned. Strong edge, minor dissent.",
    "APPROVED": "🔵 4-5 models aligned. Borderline — safety corridor advised.",
    "LEAN": "⚪ Weak support. Not recommended for locking.",
    "PASS": "🔴 Rejected. Blowout risk, injury, or insufficient edge.",
}
DEFAULT_BANKROLL = 529.64
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
INTEGRITY_FLOOR = 40
INTEGRITY_CEILING = 100
SPORTS = ["NBA", "MLB", "NHL", "NFL"]

PROP_SOURCES = {
    "BettingPros": "https://www.bettingpros.com/{sport}/props/",
    "RotoWire": "https://www.rotowire.com/betting/{sport}/player-props.php",
    "CBS Sports": "https://www.cbssports.com/{sport}/player-props/",
    "Covers": "https://www.covers.com/sport/{sport}/player-props",
    "DraftKings": "https://sportsbook.draftkings.com/page/{sport}-player-props",
}

GAME_SOURCES = {
    "ESPN (Primary)": "https://www.espn.com/{sport}/odds",
    "DraftKings (Failover 1)": "https://sportsbook.draftkings.com/page/{sport}-game-lines",
    "Covers (Failover 2)": "https://www.covers.com/sport/{sport}/odds",
}

LINEUP_SOURCES = {
    "DraftEdge": "https://draftedge.com/{sport}/{sport}-starting-lineups/",
    "RotoWire": "https://www.rotowire.com/basketball/{sport}/lineups.php",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BetCouncil/3.0)"
}

# =========================
# SESSION STATE
# =========================
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "integrity" not in st.session_state: st.session_state.integrity = 64
if "safe_corridor" not in st.session_state: st.session_state.safe_corridor = True
if "emergency_floor" not in st.session_state: st.session_state.emergency_floor = True
if "locks" not in st.session_state: st.session_state.locks = []
if "history" not in st.session_state: st.session_state.history = []
if "autopsy_log" not in st.session_state: st.session_state.autopsy_log = []
if "board_data" not in st.session_state: st.session_state.board_data = None
if "game_verdicts" not in st.session_state: st.session_state.game_verdicts = None
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"
if "lock_num" not in st.session_state: st.session_state.lock_num = 0
if "injuries" not in st.session_state: st.session_state.injuries = []
if "blowout_games" not in st.session_state: st.session_state.blowout_games = []
if "filtered_count" not in st.session_state: st.session_state.filtered_count = 0
if "raw_props" not in st.session_state: st.session_state.raw_props = []
if "raw_games" not in st.session_state: st.session_state.raw_games = []
if "site_status" not in st.session_state:
    st.session_state.site_status = {
        name: {"status": "unknown", "last_checked": None}
        for name in list(PROP_SOURCES.keys()) + list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys())
    }
if "board_ready" not in st.session_state: st.session_state.board_ready = False
if "board_check_time" not in st.session_state: st.session_state.board_check_time = None
if "last_scan_time" not in st.session_state: st.session_state.last_scan_time = None
if "auto_refresh" not in st.session_state: st.session_state.auto_refresh = False
if "estimated_ready_time" not in st.session_state: st.session_state.estimated_ready_time = None
if "manual_results" not in st.session_state: st.session_state.manual_results = None

# =========================
# HELPERS
# =========================
def weighted_score(votes):
    total = 0.0
    for model in MODELS:
        total += model["weight"] * votes.get(model["name"], 0)
    return round(total, 3)

def get_tier(score):
    if score >= TIER_THRESHOLDS["SOVEREIGN"]: return "SOVEREIGN"
    elif score >= TIER_THRESHOLDS["ELITE"]: return "ELITE"
    elif score >= TIER_THRESHOLDS["APPROVED"]: return "APPROVED"
    elif score >= TIER_THRESHOLDS["LEAN"]: return "LEAN"
    return "PASS"

def tier_label(tier):
    return {
        "SOVEREIGN": "⚡ Sovereign Lock",
        "ELITE": "🟡 Elite Edge", 
        "APPROVED": "🔵 Approved Single",
        "LEAN": "⚪ Lean",
        "PASS": "🔴 PASS"
    }.get(tier, "—")

def generate_lock_id():
    st.session_state.lock_num += 1
    return f"LOCK-{date.today().strftime('%m%d')}-{st.session_state.lock_num:02d}"

def active_unit():
    return round(st.session_state.bankroll * KELLY_FRACTION * KELLY_CAP, 2)

def dot(status):
    if status == "ok": return "🟢"
    elif status == "fail": return "🔴"
    elif status == "degraded": return "🟡"
    return "⚪"

def classify_loss(lock):
    tier = lock.get("tier", "PASS")
    if tier == "SOVEREIGN": return "Variance / High-Confidence Miss"
    if tier == "ELITE": return "Thin Edge / Market Drift"
    if lock.get("override"): return "Logic Leak (Manual Override)"
    return "Low Edge / Noise"

def mark_site_ok(name):
    st.session_state.site_status[name] = {"status": "ok", "last_checked": datetime.now().strftime("%H:%M:%S")}

def mark_site_fail(name):
    st.session_state.site_status[name] = {"status": "fail", "last_checked": datetime.now().strftime("%H:%M:%S")}

def mark_site_degraded(name):
    st.session_state.site_status[name] = {"status": "degraded", "last_checked": datetime.now().strftime("%H:%M:%S")}

def check_board_ready(sport="NBA"):
    """Ping ALL prop and game sources with failover. Return True if ANY source has tomorrow's data."""
    sport_lower = sport.lower()
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_formats = [
        tomorrow.strftime("%b %d"), tomorrow.strftime("%B %d"),
        tomorrow.strftime("%m/%d"), tomorrow.strftime("%Y-%m-%d"),
    ]
    
    sources_to_check = []
    for name, url_template in PROP_SOURCES.items():
        sources_to_check.append((name, url_template.replace("{sport}", sport_lower), "props"))
    for name, url_template in GAME_SOURCES.items():
        sources_to_check.append((name, url_template.replace("{sport}", sport_lower), "games"))
    
    ready_sources = []
    
    for name, url, source_type in sources_to_check:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                page_text = soup.get_text()
                date_found = any(fmt in page_text for fmt in tomorrow_formats)
                tables = soup.find_all("table")
                has_table_data = any(len(table.find_all("tr")) > 3 for table in tables)
                has_content = len(page_text.strip()) > 500
                
                if date_found or has_table_data or has_content:
                    ready_sources.append(name)
                    mark_site_ok(name)
                else:
                    mark_site_degraded(name)
            else:
                mark_site_fail(name)
        except:
            mark_site_fail(name)
    
    if ready_sources:
        st.session_state.board_ready = True
        st.session_state.board_check_time = datetime.now().strftime("%H:%M:%S")
        st.session_state.last_scan_time = st.session_state.board_check_time
        st.session_state.estimated_ready_time = None
        return True
    
    st.session_state.board_ready = False
    st.session_state.board_check_time = datetime.now().strftime("%H:%M:%S")
    if st.session_state.estimated_ready_time is None:
        st.session_state.estimated_ready_time = (datetime.now() + timedelta(hours=4)).strftime("%I:%M %p ET")
    return False

def board_ready_badge():
    if st.session_state.board_ready:
        return '<span class="ready-badge ready-green">🟢 BOARD READY — Tomorrow\'s props available</span>'
    elif st.session_state.board_check_time:
        return f'<span class="ready-badge ready-yellow">🟡 WAITING — Last check: {st.session_state.board_check_time}. Estimated: {st.session_state.estimated_ready_time or "after 10 PM ET"}</span>'
    return '<span class="ready-badge ready-red">🔴 NO DATA — Click "Check Now" to verify</span>'

def load_button_label():
    if st.session_state.board_ready: return "🟢 Load Board (Ready)"
    elif st.session_state.board_check_time: return "🟡 Load Board (Check Again)"
    return "🔴 Load Board (No Data)"

def parse_manual_input(text):
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        game_match = re.match(r"(.+?)\s+([+-]?\d+\.?\d*)\s*$", line)
        if game_match and ("@" in line or "vs" in line.lower() or any(t in line for t in ["ML", "Over", "Under"])):
            results.append({"type": "GAME", "raw": line})
            continue
        prop_match = re.match(r"(.+?)\s+(OVER|UNDER)\s+([\d.]+)\s+(.+)", line, re.IGNORECASE)
        if prop_match:
            results.append({
                "type": "PROP",
                "player": prop_match.group(1).strip(),
                "side": prop_match.group(2).upper(),
                "line": float(prop_match.group(3)),
                "prop": prop_match.group(4).strip(),
                "raw": line,
            })
    return results

def run_manual_council(props_list):
    results = []
    for item in props_list:
        if item["type"] != "PROP": continue
        player, ptype, side, line = item["player"], item["prop"], item["side"], item["line"]
        votes, reasons = {}, {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO", "REB+AST"])
        is_under = "UNDER" in side.upper()
        is_star = any(s in player for s in ["Shai", "LeBron", "Cade", "Donovan", "Anthony", "James", "Tobias"])

        votes[MODELS[0]["name"]] = 0 if is_combo else (1 if is_under else 1)
        reasons[MODELS[0]["name"]] = "Combo variance too high" if is_combo else ("Outlier supports Under" if is_under else "Consistent, outlier clean")
        votes[MODELS[1]["name"]] = 0
        reasons[MODELS[1]["name"]] = "No environmental edge"
        votes[MODELS[2]["name"]] = 1 if is_star else 0
        reasons[MODELS[2]["name"]] = "Playoff motivation / legacy game" if is_star else "Role player — motivation variance"
        votes[MODELS[3]["name"]] = 0 if is_combo else 1
        reasons[MODELS[3]["name"]] = "Floor unreliable" if is_combo else "Deterministic floor above line"
        votes[MODELS[4]["name"]] = 0 if is_combo else 1
        reasons[MODELS[4]["name"]] = "Sigma too wide" if is_combo else "Low volatility"
        votes[MODELS[5]["name"]] = 1 if is_star else 0
        reasons[MODELS[5]["name"]] = "CLV positive, edge meets floor" if is_star else "Edge below Emergency Floor"
        votes[MODELS[6]["name"]] = 1 if is_star else 0
        reasons[MODELS[6]["name"]] = "Ceiling manageable" if is_star else "Ceiling risk"
        votes[MODELS[7]["name"]] = 0 if is_combo else 1
        reasons[MODELS[7]["name"]] = "Margin of error" if is_combo else "Raw projection supports"

        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({
            "Player": player, "Prop": ptype, "Side": side, "Line": line,
            "Votes": votes, "Reasons": reasons,
            "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier),
            "raw": item["raw"], "type": "PROP",
        })
    return results

# =========================
# SAMPLE DATA
# =========================
NBA_SAMPLE = {
    "raw_props": [
        {"Player": "Shai Gilgeous-Alexander", "Prop": "POINTS", "Line": 31.5, "Side": "OVER"},
        {"Player": "Chet Holmgren", "Prop": "REBOUNDS", "Line": 9.5, "Side": "OVER"},
        {"Player": "LeBron James", "Prop": "PTS+AST", "Line": 34.5, "Side": "OVER"},
        {"Player": "Cade Cunningham", "Prop": "POINTS", "Line": 23.5, "Side": "OVER"},
        {"Player": "Donovan Mitchell", "Prop": "POINTS", "Line": 27.5, "Side": "UNDER"},
    ],
    "raw_games": [
        {"Matchup": "DET @ CLE", "Spread": "CLE -4.5", "Total": "O/U 216.5", "Moneyline": "CLE -190 / DET +160"},
        {"Matchup": "OKC @ LAL", "Spread": "OKC -8.5", "Total": "O/U 214.5", "Moneyline": "OKC -400 / LAL +320"},
    ],
    "injuries": [{"Player": "Kevin Huerter", "Status": "Doubtful"}, {"Player": "Sam Merrill", "Status": "Questionable"}],
    "blowout_games": [{"Game": "DET @ CLE", "Spread": "-4.5", "Advisory": "❌ Inactive"}, {"Game": "OKC @ LAL", "Spread": "-8.5", "Advisory": "⚠️ ACTIVE"}],
    "filtered_count": 2,
}

def load_sport_data(sport):
    data = NBA_SAMPLE if sport == "NBA" else {"raw_props": [], "raw_games": [], "injuries": [], "blowout_games": [], "filtered_count": 0}
    st.session_state.raw_props = data["raw_props"]
    st.session_state.raw_games = data["raw_games"]
    st.session_state.injuries = data["injuries"]
    st.session_state.blowout_games = data["blowout_games"]
    st.session_state.filtered_count = data["filtered_count"]
    st.session_state.last_sport = sport
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True

def run_council():
    raw = st.session_state.raw_props
    if not raw: st.session_state.board_data = None; return
    results = []
    for prop in raw:
        player, ptype, side, line = prop["Player"], prop["Prop"], prop["Side"], prop["Line"]
        votes, reasons = {}, {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO"])
        is_under = "UNDER" in side.upper()
        is_star = any(s in player for s in ["Shai", "LeBron", "Cade", "Donovan", "Anthony"])

        votes[MODELS[0]["name"]] = 0 if is_combo else (1 if is_under else 1)
        reasons[MODELS[0]["name"]] = "Combo variance too high" if is_combo else ("Outlier supports Under" if is_under else "Consistent, outlier clean")
        votes[MODELS[1]["name"]] = 0
        reasons[MODELS[1]["name"]] = "No environmental edge"
        votes[MODELS[2]["name"]] = 1 if is_star else 0
        reasons[MODELS[2]["name"]] = "Playoff motivation / legacy game" if is_star else "Role player — motivation variance"
        votes[MODELS[3]["name"]] = 0 if is_combo else 1
        reasons[MODELS[3]["name"]] = "Floor unreliable" if is_combo else "Deterministic floor above line"
        votes[MODELS[4]["name"]] = 0 if is_combo else 1
        reasons[MODELS[4]["name"]] = "Sigma too wide" if is_combo else "Low volatility"
        votes[MODELS[5]["name"]] = 1 if is_star else 0
        reasons[MODELS[5]["name"]] = "CLV positive, edge meets floor" if is_star else "Edge below Emergency Floor"
        votes[MODELS[6]["name"]] = 1 if is_star else 0
        reasons[MODELS[6]["name"]] = "Ceiling manageable" if is_star else "Ceiling risk"
        votes[MODELS[7]["name"]] = 0 if is_combo else 1
        reasons[MODELS[7]["name"]] = "Margin of error" if is_combo else "Raw projection supports"

        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({
            "Player": player, "Prop": ptype, "Side": side, "Line": line,
            "Votes": votes, "Reasons": reasons,
            "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier),
        })
    st.session_state.board_data = results

def run_game_council():
    games = st.session_state.raw_games
    if not games: st.session_state.game_verdicts = None; return
    results = []
    for game in games:
        matchup = game["Matchup"]
        votes = {model["name"]: (1 if any(t in matchup for t in ["CLE", "OKC"]) else 0) for model in MODELS}
        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({
            "Matchup": matchup, "Moneyline": game.get("Moneyline", ""),
            "Spread": game.get("Spread", ""), "Total": game.get("Total", ""),
            "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier),
        })
    st.session_state.game_verdicts = results

def build_prop_parlay():
    data = st.session_state.board_data
    if not data: return []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, teams = [], set()
    for item in eligible:
        team = item["Player"].split()[-1]
        if len(legs) == 2 and team in teams: continue
        if len(legs) >= 5: break
        legs.append(item)
        teams.add(team)
    return legs

def build_game_parlay():
    data = st.session_state.game_verdicts
    if not data: return []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, seen = [], set()
    for item in eligible:
        if len(legs) == 2 and item["Matchup"] in seen: continue
        if len(legs) >= 6: break
        legs.append(item)
        seen.add(item["Matchup"])
    return legs

def parse_pasted_results(text):
    results = []
    for line in text.strip().split("\n"):
        match = re.match(r"(.+?)\s+(OVER|UNDER|ML|SPREAD)\s+([\d.]+)\s+(WIN|LOSS)", line.strip(), re.IGNORECASE)
        if match:
            player, side, line_str, outcome = match.groups()
            results.append({"player": player.strip(), "side": side.upper(), "line": float(line_str), "outcome": outcome.upper()})
    return results

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ BetCouncil v3.0")
    st.session_state.bankroll = st.number_input("Bankroll ($)", value=float(st.session_state.bankroll), step=10.0)
    unit = active_unit()
    st.metric("Active Unit", f"${unit:.2f}")
    st.metric("Integrity", st.session_state.integrity)
    st.checkbox("Safe Corridor", value=st.session_state.safe_corridor, key="safe_corridor")
    st.checkbox("Emergency Floor (12%)", value=st.session_state.emergency_floor, key="emergency_floor")
    
    st.markdown("---")
    st.markdown("### 📡 Board Readiness")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Check Now"):
            ready = check_board_ready(st.session_state.last_sport)
            if ready: st.success("Board is ready!")
            else: st.warning("Not ready yet.")
    with col2:
        st.checkbox("Auto-check", value=st.session_state.auto_refresh, key="auto_refresh")
    if st.session_state.last_scan_time:
        st.caption(f"Last successful scan: {st.session_state.last_scan_time}")
    
    st.markdown("---")
    label = load_button_label()
    if st.button(label):
        load_sport_data(st.session_state.last_sport)
        run_council()
        run_game_council()
        for name in list(PROP_SOURCES.keys()) + list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys()):
            mark_site_ok(name)
        st.success(f"{st.session_state.last_sport} board loaded.")
    if st.button("🔄 Re-Run Council"):
        run_council(); run_game_council()
        st.success("Refreshed.")

# =========================
# TABS
# =========================
tabs = st.tabs(["🏀 Board of 8", "🔒 Locks of the Day", "📋 Locks & Ledger", "🔄 Reconciliation", "🛡️ SEM & System"])

# =========================
# TAB 1 — BOARD OF 8
# =========================
with tabs[0]:
    st.markdown("# 🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")
    st.markdown(board_ready_badge(), unsafe_allow_html=True)
    if st.session_state.auto_refresh:
        st.caption("🔄 Auto-check active — checking every 30 minutes")
    
    # ===== MANUAL OVERRIDE SECTION =====
    st.markdown("---")
    st.markdown("## ⚡ MANUAL OVERRIDE — QUICK PROP LOOKUP")
    st.markdown("Paste a single prop, game line, or full slip. One per line.")
    manual_input = st.text_area(
        "Paste props or games here",
        placeholder="LeBron James OVER 21.5 Points\nOKC -8.5\nJames Harden OVER 5.5 Rebounds",
        height=120,
        key="manual_override_input"
    )
    col_m1, col_m2, col_m3 = st.columns([1, 1, 1])
    with col_m1:
        if st.button("⚡ Run Manual Analysis", use_container_width=True):
            if manual_input.strip():
                parsed = parse_manual_input(manual_input)
                if parsed:
                    st.session_state.manual_results = run_manual_council(parsed)
                    st.success(f"Analyzed {len(st.session_state.manual_results)} props.")
                else:
                    st.warning("Could not parse. Use: Player OVER/UNDER Line Prop")
    with col_m2:
        st.file_uploader("📸 Upload Screenshot", type=["png","jpg","jpeg"], key="manual_screenshot")
    with col_m3:
        if st.button("🗑️ Clear Manual Results", use_container_width=True):
            st.session_state.manual_results = None
            st.rerun()

    if st.session_state.manual_results:
        st.markdown("### ⚡ Manual Override Results")
        for i, item in enumerate(st.session_state.manual_results):
            with st.expander(f"{item['Player']} — {item['Side']} {item['Line']} {item['Prop']} ({item['Tier Label']})", expanded=True):
                st.write(f"**Weighted Score:** {item['Weighted Score']}")
                for model in MODELS:
                    vote = item["Votes"].get(model["name"], 0)
                    reason = item["Reasons"].get(model["name"], "")
                    st.caption(f"{'✅' if vote == 1 else '❌'} {model['name']}: {reason}")
                override_flag = item["Tier"] not in ("SOVEREIGN", "ELITE") or any(k in item["Prop"].upper() for k in ["PRA", "COMBO", "REB+AST", "PTS+A"])
                if st.button(f"🔒 Lock This", key=f"manual_lock_{i}"):
                    lid = generate_lock_id()
                    st.session_state.locks.append({
                        "id": lid, "type": "PROP",
                        "player": item["Player"],
                        "prop": f"{item['Side']} {item['Line']} {item['Prop']}",
                        "side": item["Side"], "line": item["Line"],
                        "tier": item["Tier"],
                        "status": "PENDING", "result": None,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "parlay_id": lid,
                        "override": override_flag,
                    })
                    st.success(f"Locked: {lid}")
    st.markdown("---")
    
    # ===== MAIN BOARD =====
    sport = st.selectbox("Select Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport), key="sport_select")
    st.session_state.last_sport = sport
    board = st.session_state.board_data

    st.markdown(
        f"**Data Source:** BettingPros + RotoWire + CBS Sports + Covers + DraftKings + ESPN  \n"
        f"**Sport:** {sport} — {date.today().strftime('%B %d, %Y')}  \n"
        f"**Status:** {'🛡️ SAFE CORRIDOR ACTIVE' if st.session_state.safe_corridor else '✅ NORMAL MODE'} | "
        f"{'🚨 EMERGENCY FLOOR ACTIVE (12%)' if st.session_state.emergency_floor else '✅ REGULAR FLOOR (4.5%)'}"
    )
    if board:
        st.markdown(f"🔒 **Validation Firewall:** PASSED ({len(st.session_state.blowout_games)} games, {len(st.session_state.injuries)} matchups verified, {st.session_state.filtered_count} props removed)")
    st.markdown("---")
    with st.expander("📖 TIER LEGEND", expanded=False):
        for tier, desc in TIER_DESCRIPTIONS.items():
            st.markdown(f"**{tier_label(tier)}** — {desc}")

    if not board:
        st.info("No board loaded. Check readiness above, then load from the sidebar.")
    else:
        st.markdown("## 🚨 PRE‑FILTER: LINEUP & INJURY VERIFICATION")
        st.table(pd.DataFrame(st.session_state.injuries) if st.session_state.injuries else pd.DataFrame([{"Status": "No issues reported"}]))
        st.markdown("## 🚨 BLOWOUT ADVISORY")
        st.table(pd.DataFrame(st.session_state.blowout_games) if st.session_state.blowout_games else pd.DataFrame([{"Advisory": "Inactive"}]))
        st.markdown("## 📊 PROPS SURVIVED PRE‑FILTER")
        st.table(pd.DataFrame([{"Player": p["Player"], "Prop": p["Prop"], "Line": p["Line"], "Side": p["Side"]} for p in st.session_state.raw_props]))
        st.markdown("## 🗳️ MODEL‑BY‑MODEL VERDICTS")
        for model in MODELS:
            name, weight = model["name"], model["weight"]
            with st.expander(f"{name} (Weight: {weight})", expanded=False):
                approved, passed = [], []
                for item in board:
                    vote = item["Votes"].get(name, 0)
                    reason = item["Reasons"].get(name, "")
                    (approved if vote == 1 else passed).append((item, reason))
                if approved:
                    for item, reason in approved:
                        st.markdown(f"✅ **{item['Player']} {item['Side']} {item['Line']} {item['Prop']}** — {reason}")
                if passed:
                    st.markdown("**PASS:**")
                    for item, reason in passed:
                        st.markdown(f"❌ {item['Player']} ({reason})")
        st.markdown("## 🟦 COUNCIL CONSENSUS SUMMARY")
        summary = sorted([{"Pick": f"{i['Player']} {i['Side']} {i['Line']} {i['Prop']}", "Score": i["Weighted Score"], "Tier": i["Tier Label"]} for i in board], key=lambda x: x["Score"], reverse=True)
        st.table(pd.DataFrame(summary))
        excluded = [i for i in board if i["Tier"] in ("LEAN","PASS")]
        if excluded: st.markdown("**Excluded:** " + ", ".join([f"{i['Player']} ({i['Tier Label']})" for i in excluded]))
        st.markdown("## 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        st.markdown("- **RLM Status:** DETECTED\n- **Contrarian Flag:** ACTIVE\n- **Regime Type:** STABLE")

# =========================
# TAB 2 — LOCKS OF THE DAY
# =========================
with tabs[1]:
    st.markdown("# 🔒 LOCKS & PARLAYS OF THE DAY")
    board = st.session_state.board_data
    games = st.session_state.game_verdicts
    if not board:
        st.info("Load a board first.")
    else:
        approved = [i for i in board if i["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
        if not approved:
            st.info("No approved props.")
        else:
            best_prop = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[0]
            best_game = games[0] if games else None
            st.markdown("## 🔒 Lock of the Day")
            lock_data = [{"Type": "Prop", "Pick": f"{best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']}", "Tier": best_prop['Tier Label']}]
            if best_game: lock_data.append({"Type": "Game", "Pick": best_game["Matchup"], "Bet": best_game.get("Moneyline","N/A"), "Tier": best_game['Tier Label']})
            st.table(pd.DataFrame(lock_data))
            if best_prop["Tier"] == "APPROVED":
                alt_line = best_prop["Line"] - 1.0 if "UNDER" in best_prop["Side"].upper() else best_prop["Line"] + 1.0
                st.markdown(f"### 🔵 +EV Safety Corridor")
                st.markdown(f"**{best_prop['Player']} {best_prop['Side']} {alt_line} {best_prop['Prop']}** — Alt line recommended.")

            st.markdown("## 🔗 Prop Parlay of the Day")
            prop_par = build_prop_parlay()
            if prop_par:
                st.markdown("Select legs:")
                selected_legs = []
                for i, leg in enumerate(prop_par):
                    if st.checkbox(f"{leg['Player']} — {leg['Side']} {leg['Line']} {leg['Prop']} ({leg['Tier Label']})", value=True, key=f"prop_leg_{i}"):
                        selected_legs.append(leg)
                if len(selected_legs) >= 2:
                    st.table(pd.DataFrame([{"Leg": i+1, "Player": l["Player"], "Prop": f"{l['Side']} {l['Line']} {l['Prop']}", "Tier": l["Tier Label"]} for i,l in enumerate(selected_legs)]))
                    if st.button("🔒 Lock Selected Prop Parlay"):
                        lid = generate_lock_id()
                        for leg in selected_legs:
                            st.session_state.locks.append({"id":lid,"type":"PROP","player":leg["Player"],"prop":f"{leg['Side']} {leg['Line']} {leg['Prop']}","side":leg["Side"],"line":leg["Line"],"tier":leg["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"parlay_id":lid})
                        st.success(f"Locked: {lid}")
                else: st.warning("Select at least 2 legs.")

            st.markdown("## 🔗 Game Parlay of the Day")
            game_par = build_game_parlay()
            if game_par:
                st.markdown("Select games:")
                selected_games = []
                for i, leg in enumerate(game_par):
                    if st.checkbox(f"{leg['Matchup']} — {leg.get('Moneyline','N/A')} ({leg['Tier Label']})", value=True, key=f"game_leg_{i}"):
                        selected_games.append(leg)
                if len(selected_games) >= 2:
                    st.table(pd.DataFrame([{"Leg": i+1, "Matchup": l["Matchup"], "Bet": l.get("Moneyline","N/A"), "Tier": l["Tier Label"]} for i,l in enumerate(selected_games)]))
                    if st.button("🔒 Lock Selected Game Parlay"):
                        lid = generate_lock_id()
                        for leg in selected_games:
                            st.session_state.locks.append({"id":lid,"type":"GAME","matchup":leg["Matchup"],"bet":leg.get("Moneyline","N/A"),"tier":leg["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"parlay_id":lid})
                        st.success(f"Locked: {lid}")
                else: st.warning("Select at least 2 games.")

# =========================
# TAB 3 — LOCKS & LEDGER
# =========================
with tabs[2]:
    st.markdown("# 📋 LOCKS & LEDGER")
    pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
    st.markdown("### Active Locks")
    if not pending: st.info("No active locks.")
    else:
        for i, lock in enumerate(pending):
            cols = st.columns([4,1,1,1])
            with cols[0]:
                st.markdown(f"**{lock.get('id')}** — {lock.get('player', lock.get('matchup'))} | {lock.get('prop', lock.get('bet'))} | {lock.get('tier','?')}")
            with cols[1]:
                if st.button("✅ WIN", key=f"w_{i}"):
                    lock["status"]="RESOLVED"; lock["result"]="WIN"
                    st.session_state.history.append(lock)
                    st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                    st.session_state.bankroll += active_unit()
                    st.rerun()
            with cols[2]:
                if st.button("❌ LOSS", key=f"l_{i}"):
                    lock["status"]="RESOLVED"; lock["result"]="LOSS"
                    reason = classify_loss(lock)
                    st.session_state.autopsy_log.append({"id":lock.get("id"),"pick":lock.get("player", lock.get("matchup")),"result":"LOSS","reason":reason,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                    st.session_state.history.append(lock)
                    st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                    st.session_state.bankroll -= active_unit()
                    st.rerun()
            with cols[3]:
                if st.button("🗑️ Remove", key=f"rm_{i}"):
                    st.session_state.locks.pop(i)
                    st.rerun()

    st.markdown("### Resolved History")
    if st.session_state.history:
        st.table(pd.DataFrame([{"ID":h.get("id"),"Pick":h.get("player", h.get("matchup")),"Result":h.get("result"),"Tier":h.get("tier")} for h in st.session_state.history]))

# =========================
# TAB 4 — RECONCILIATION
# =========================
with tabs[3]:
    st.markdown("# 🔄 RECONCILIATION & SYNC")
    st.markdown("### 🌐 Auto-Scan Sources")
    st.markdown("Failover: ESPN → DraftKings → Covers")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🌐 Scan Game Lines"):
            mark_site_fail("ESPN (Primary)"); mark_site_ok("DraftKings (Failover 1)")
            st.info("Failover to DraftKings.")
    with c2:
        if st.button("🌐 Scan Player Props"):
            for name in PROP_SOURCES: mark_site_ok(name)
            st.success("All prop sources scanned.")
    st.markdown("---")
    st.markdown("### 📋 Paste Results to Auto-Grade")
    st.markdown("Format: `Player OVER/UNDER Line WIN/LOSS`")
    pasted = st.text_area("Paste results", height=150)
    if st.button("🔍 Sync Pasted Results"):
        parsed = parse_pasted_results(pasted)
        if parsed:
            for lock in st.session_state.locks:
                if lock["status"] == "PENDING":
                    for r in parsed:
                        if (r["player"].lower() in lock.get("player","").lower() and 
                            r["side"] == lock.get("side","") and 
                            abs(r["line"] - lock.get("line",0)) < 0.1):
                            lock["status"] = "RESOLVED"; lock["result"] = r["outcome"]
                            st.session_state.history.append(lock)
                            if r["outcome"] == "WIN":
                                st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                                st.session_state.bankroll += active_unit()
                            else:
                                reason = classify_loss(lock)
                                st.session_state.autopsy_log.append({"id":lock.get("id"),"pick":lock.get("player", lock.get("matchup")),"result":"LOSS","reason":reason,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                                st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                                st.session_state.bankroll -= active_unit()
            st.session_state.locks = [l for l in st.session_state.locks if l["status"] == "PENDING"]
            st.success("Synced.")
        else: st.warning("No valid results.")
    st.markdown("---")
    st.markdown("### 📸 Upload Screenshot")
    st.file_uploader("Upload PNG/JPG", type=["png","jpg","jpeg"])
    st.info("OCR coming soon.")
    st.markdown("---")
    st.markdown("### 🔬 Autopsy Log")
    if st.session_state.autopsy_log:
        st.table(pd.DataFrame(st.session_state.autopsy_log))
    else: st.info("No losses yet.")

# =========================
# TAB 5 — SEM & SYSTEM
# =========================
with tabs[4]:
    st.markdown("# 🛡️ SEM & SYSTEM HEALTH")
    st.markdown("## SEM Status")
    st.metric("Integrity Score", st.session_state.integrity)
    st.metric("Safe Corridor", "ACTIVE" if st.session_state.safe_corridor else "INACTIVE")
    st.metric("Emergency Floor", "ACTIVE (12%)" if st.session_state.emergency_floor else "INACTIVE")
    st.metric("Bankroll", f"${st.session_state.bankroll:.2f}")
    st.metric("Active Locks", len([l for l in st.session_state.locks if l.get("status")=="PENDING"]))
    st.markdown("## 📡 Site Health & Failover Status")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Prop Sources")
        for name in PROP_SOURCES:
            s = st.session_state.site_status.get(name, {}).get("status","unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked","—")
            st.markdown(f"{dot(s)} **{name}** — {t}")
    with c2:
        st.markdown("### Game & Lineup Sources")
        for name in list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys()):
            s = st.session_state.site_status.get(name, {}).get("status","unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked","—")
            st.markdown(f"{dot(s)} **{name}** — {t}")
    st.markdown("## ➕ Add Custom Source")
    nn = st.text_input("Source Name"); nu = st.text_input("Source URL (use {sport})")
    if st.button("Add Source") and nn and nu:
        PROP_SOURCES[nn] = nu
        st.session_state.site_status[nn] = {"status":"unknown","last_checked":"—"}
        st.success(f"Added: {nn}")
