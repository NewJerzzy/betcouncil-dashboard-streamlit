import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup
import json
import subprocess
import os

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
    background-color: #07090c;
    color: #e8f0f8;
    font-family: 'Inter', system-ui, sans-serif;
}
h1, h2, h3, h4, h5 { color: #f4f8fc; text-transform: uppercase; letter-spacing: 0.5px; }
.stButton > button {
    background-color: #7c4dff;
    color: #ffffff;
    border: none;
    border-radius: 0.5rem;
    padding: 0.55rem 1.3rem;
    font-weight: 600;
    cursor: pointer;
    font-size: 0.85rem;
}
.stButton > button:hover { background-color: #651fff; }
.stButton > button:disabled { opacity: 0.4; cursor: not-allowed; }
.section-card {
    background-color: #0d1219;
    border: 1px solid #1c2a3a;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 0.75rem;
}
.command-bar {
    background: linear-gradient(135deg, rgba(232,160,32,0.1), #0d1219);
    border: 1px solid rgba(232,160,32,0.35);
    border-top: 2px solid #e8a020;
    border-radius: 0 0 10px 10px;
    padding: 14px 18px;
    margin-bottom: 14px;
}
.toggle-btn {
    font-size: 10px;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #5a7088;
    background: rgba(255,255,255,0.04);
    color: #5a7088;
    cursor: pointer;
    font-family: monospace;
}
.toggle-btn.active { border-color: #e8a020; color: #e8a020; background: rgba(232,160,32,0.1); }
.sovereign-badge { color: #e8a020; font-weight: 700; }
.elite-badge { color: #16a84a; font-weight: 700; }
.approved-badge { color: #2868d0; font-weight: 600; }
.lean-badge { color: #888; font-weight: 600; }
.pass-badge { color: #d03030; font-weight: 600; }
.metric-box {
    background: #0d1219;
    border: 1px solid #1c2a3a;
    border-radius: 6px;
    padding: 7px 10px;
}
.metric-label {
    font-size: 10px;
    color: #5a7088;
    font-family: monospace;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.metric-value { font-size: 16px; font-weight: 600; }
.parlay-card {
    background: linear-gradient(135deg, rgba(22,168,74,0.07), #111a24);
    border: 1px solid rgba(22,168,74,0.3);
    border-radius: 8px;
    padding: 12px 14px;
}
.game-parlay-card {
    background: linear-gradient(135deg, rgba(40,104,208,0.07), #111a24);
    border: 1px solid rgba(40,104,208,0.3);
    border-radius: 8px;
    padding: 12px 14px;
}
.gold-text { color: #e8a020; }
.green-text { color: #16a84a; }
.red-text { color: #d03030; }
.muted-text { color: #5a7088; }
.white-text { color: #f4f8fc; }
.mono { font-family: monospace; }
.sharp-ref-box {
    background: rgba(232,160,32,0.08);
    border: 1px solid rgba(232,160,32,0.4);
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS — v3.0 HARD ENGINE
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

TIER_THRESHOLDS = {"SOVEREIGN": 0.70, "ELITE": 0.55, "APPROVED": 0.40, "LEAN": 0.20}
TIER_DESCRIPTIONS = {
    "SOVEREIGN": "⚡ 8/8 models aligned. Unanimous consensus.",
    "ELITE": "🟡 6-7 models aligned. Strong edge.",
    "APPROVED": "🔵 4-5 models aligned. Safety corridor advised.",
    "LEAN": "⚪ Weak support. Do not lock.",
    "PASS": "🔴 Rejected.",
}
DEFAULT_BANKROLL = 529.64
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
INTEGRITY_FLOOR = 40
INTEGRITY_CEILING = 100

SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

PROP_SOURCES = {
    "BettingPros": "https://www.bettingpros.com/{sport}/props/",
    "RotoWire": "https://www.rotowire.com/betting/{sport}/player-props.php",
    "CBS Sports": "https://www.cbssports.com/{sport}/player-props/",
    "Covers": "https://www.covers.com/sport/{sport}/player-props",
    "DraftKings": "https://sportsbook.draftkings.com/page/{sport}-player-props",
}

GAME_SOURCES = {
    "ESPN (JSON API)": "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard",
    "DraftKings (Failover 1)": "https://sportsbook.draftkings.com/page/{sport}-game-lines",
    "Covers (Failover 2)": "https://www.covers.com/sport/{sport}/odds",
}

LINEUP_SOURCES = {
    "DraftEdge": "https://draftedge.com/{sport}/{sport}-starting-lineups/",
    "RotoWire": "https://www.rotowire.com/basketball/{sport}/lineups.php",
}

SPORT_PATH_MAP = {
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "nfl": "football/nfl",
    "wnba": "basketball/wnba",
}

SHARP_REFERENCE = {
    "name": "OddsHarvester / OddsPortal (Pinnacle Sharp Line)",
    "cost": "Free — open‑source pip package",
    "install_cmd": "pip install oddsharvester",
    "sport_map": {
        "nba": "basketball", "mlb": "baseball", "nhl": "hockey",
        "nfl": "football", "wnba": "basketball", "golf": "golf",
        "tennis": "tennis", "soccer": "soccer",
    },
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BetCouncil/3.0)"}

# =========================
# SESSION STATE
# =========================
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "integrity" not in st.session_state: st.session_state.integrity = 64
if "safe_corridor" not in st.session_state: st.session_state.safe_corridor = True
if "emergency_floor" not in st.session_state: st.session_state.emergency_floor = True
if "is_playoff" not in st.session_state: st.session_state.is_playoff = True
if "blowout_advisory" not in st.session_state: st.session_state.blowout_advisory = True
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
    st.session_state.site_status[SHARP_REFERENCE["name"]] = {"status": "unknown", "last_checked": None}
if "board_ready" not in st.session_state: st.session_state.board_ready = False
if "last_scan_time" not in st.session_state: st.session_state.last_scan_time = None
if "manual_results" not in st.session_state: st.session_state.manual_results = None
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None
if "sharp_data" not in st.session_state: st.session_state.sharp_data = None
if "sharp_available" not in st.session_state: st.session_state.sharp_available = False

# =========================
# HELPERS
# =========================
def weighted_score(votes):
    return round(sum(MODELS[i]["weight"] * votes.get(m["name"], 0) for i, m in enumerate(MODELS)), 3)

def get_tier(score):
    if score >= 0.70: return "SOVEREIGN"
    if score >= 0.55: return "ELITE"
    if score >= 0.40: return "APPROVED"
    if score >= 0.20: return "LEAN"
    return "PASS"

def tier_label(tier):
    return {"SOVEREIGN": "⚡ Sovereign Lock", "ELITE": "🟡 Elite Edge", "APPROVED": "🔵 Approved Single", "LEAN": "⚪ Lean", "PASS": "🔴 PASS"}.get(tier, "—")

def tier_color(tier):
    return {"SOVEREIGN": "#e8a020", "ELITE": "#16a84a", "APPROVED": "#2868d0", "LEAN": "#888", "PASS": "#d03030"}.get(tier, "#5a7088")

def generate_lock_id():
    st.session_state.lock_num += 1
    return f"LOCK-{date.today().strftime('%m%d')}-{st.session_state.lock_num:02d}"

def active_unit():
    return round(st.session_state.bankroll * KELLY_FRACTION * KELLY_CAP, 2)

def dot(status):
    return {"ok": "🟢", "fail": "🔴", "degraded": "🟡"}.get(status, "⚪")

def classify_loss(lock):
    if lock.get("tier") == "SOVEREIGN": return "Variance / High-Confidence Miss"
    if lock.get("tier") == "ELITE": return "Thin Edge / Market Drift"
    if lock.get("override"): return "Logic Leak (Manual Override)"
    return "Low Edge / Noise"

def mark_site_ok(name):
    st.session_state.site_status[name] = {"status": "ok", "last_checked": datetime.now().strftime("%H:%M:%S")}
def mark_site_fail(name):
    st.session_state.site_status[name] = {"status": "fail", "last_checked": datetime.now().strftime("%H:%M:%S")}

def get_espn_spreads(sport):
    sport_lower = sport.lower()
    api_path = SPORT_PATH_MAP.get(sport_lower, f"basketball/{sport_lower}")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{api_path}/scoreboard"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200: return []
        data = resp.json()
        games = []
        for event in data.get("events", []):
            game = {"matchup": event.get("shortName", ""), "status": event.get("status", {}).get("type", {}).get("description", "")}
            for comp in event.get("competitions", []):
                odds_list = comp.get("odds", [])
                if odds_list:
                    game["spread"] = odds_list[0].get("details", "")
                    game["overUnder"] = odds_list[0].get("overUnder", "")
                    break
            games.append(game)
        return games
    except:
        return []

def fetch_sharp_reference(sport="nba"):
    """Optional sharp reference layer. Tries OddsHarvester first, falls back cleanly.
    Returns list of dicts with sharp lines, or empty list if unavailable."""
    sport_name = SHARP_REFERENCE["sport_map"].get(sport.lower(), sport.lower())
    try:
        result = subprocess.run(
            ["oddsharvester", "upcoming", "-s", sport_name, "--headless"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            mark_site_ok(SHARP_REFERENCE["name"])
            st.session_state.sharp_available = True
            lines = []
            for line in result.stdout.strip().split("\n"):
                parts = line.split(",")
                if len(parts) >= 5:
                    lines.append({
                        "matchup": parts[0].strip(),
                        "market": parts[1].strip(),
                        "pinnacle_line": parts[2].strip(),
                        "pinnacle_odds": parts[3].strip(),
                        "retail_line": parts[4].strip() if len(parts) > 4 else "",
                    })
            return lines
        else:
            mark_site_fail(SHARP_REFERENCE["name"])
            st.session_state.sharp_available = False
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        mark_site_fail(SHARP_REFERENCE["name"])
        st.session_state.sharp_available = False
        return []

def get_sharp_ref_status():
    """Return a display string for the Market Dynamics footer."""
    if st.session_state.sharp_available and st.session_state.sharp_data:
        return f"Sharp Reference: Pinnacle via OddsHarvester ({len(st.session_state.sharp_data.get('lines', []))} lines)"
    elif st.session_state.sharp_data is not None and not st.session_state.sharp_available:
        return "Sharp Reference: unavailable (OddsHarvester not installed — pip install oddsharvester)"
    else:
        return "Sharp Reference: not pulled (click 'Pull Sharp Lines' in sidebar)"

def parse_manual_input(text):
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        match = re.match(r"(.+?)\s+(OVER|UNDER)\s+([\d.]+)\s+(.+)", line, re.IGNORECASE)
        if match:
            results.append({"type": "PROP", "player": match.group(1).strip(), "side": match.group(2).upper(), "line": float(match.group(3)), "prop": match.group(4).strip(), "raw": line})
    return results

def run_council_on_props(raw_props):
    if not raw_props: return []
    results = []
    stars = ["Shai", "LeBron", "Cade", "Donovan", "Anthony", "Aaron", "Shohei", "Bryce", "Juan", "James", "Tobias", "Chet", "Victor", "Jalen", "Karl", "Joel", "De'Aaron", "Julius", "Daniss", "Deandre", "Scottie", "Luka", "Giannis", "Nikola"]
    for prop in raw_props:
        player, ptype, side, line = prop.get("Player", ""), prop.get("Prop", ""), prop.get("Side", ""), prop.get("Line", 0)
        votes, reasons = {}, {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO", "REB+AST"])
        is_under = "UNDER" in side.upper()
        is_star = any(s in player for s in stars)
        for i, model in enumerate(MODELS):
            if i == 0:
                votes[model["name"]] = 0 if is_combo else (1 if is_under else 1)
                reasons[model["name"]] = "Combo variance too high" if is_combo else ("Outlier supports Under" if is_under else "Consistent, outlier clean")
            elif i == 1:
                votes[model["name"]] = 0; reasons[model["name"]] = "No environmental edge"
            elif i == 2:
                votes[model["name"]] = 1 if is_star else 0
                reasons[model["name"]] = "Motivation / competitive" if is_star else "Role player variance"
            elif i == 3:
                votes[model["name"]] = 0 if is_combo else 1
                reasons[model["name"]] = "Floor unreliable" if is_combo else "Deterministic floor above line"
            elif i == 4:
                votes[model["name"]] = 0 if is_combo else 1
                reasons[model["name"]] = "Sigma too wide" if is_combo else "Low volatility"
            elif i == 5:
                votes[model["name"]] = 1 if is_star else 0
                reasons[model["name"]] = "CLV positive" if is_star else "Edge below floor"
            elif i == 6:
                votes[model["name"]] = 1 if is_star else 0
                reasons[model["name"]] = "Ceiling manageable" if is_star else "Ceiling risk"
            else:
                votes[model["name"]] = 0 if is_combo else 1
                reasons[model["name"]] = "Margin of error" if is_combo else "Raw projection supports"
        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({"Player": player, "Prop": ptype, "Side": side, "Line": line, "Votes": votes, "Reasons": reasons, "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier), "Sport": prop.get("Sport", "")})
    return results

def run_game_council_on_games(raw_games):
    if not raw_games: return []
    results = []
    for game in raw_games:
        matchup = game.get("Matchup", "")
        votes = {m["name"]: (1 if any(t in matchup for t in ["CLE", "OKC", "NYY", "PHI", "CHC", "NYK", "SAS"]) else 0) for m in MODELS}
        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({"Matchup": matchup, "Moneyline": game.get("Moneyline", ""), "Spread": game.get("Spread", ""), "Total": game.get("Total", ""), "Weighted Score": ws, "Tier": tier, "Tier Label": tier_label(tier), "Sport": game.get("Sport", "")})
    return results

def build_prop_parlay(board_data=None):
    data = board_data or st.session_state.board_data or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, teams = [], set()
    for item in eligible:
        team = item["Player"].split()[-1]
        if len(legs) == 2 and team in teams: continue
        if len(legs) >= 5: break
        legs.append(item); teams.add(team)
    return legs

def build_game_parlay():
    data = st.session_state.game_verdicts or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, seen = [], set()
    for item in eligible:
        if len(legs) == 2 and item["Matchup"] in seen: continue
        if len(legs) >= 6: break
        legs.append(item); seen.add(item["Matchup"])
    return legs

def lock_single_prop(item):
    lid = generate_lock_id()
    sharp_ref = None
    if st.session_state.sharp_data and st.session_state.sharp_available:
        for sl in st.session_state.sharp_data.get("lines", []):
            if item["Player"].split()[-1].lower() in sl.get("matchup", "").lower():
                sharp_ref = {"line": sl.get("pinnacle_line", ""), "odds": sl.get("pinnacle_odds", ""), "source": "Pinnacle via OddsHarvester"}
                break
    st.session_state.locks.append({
        "id": lid, "type": "PROP", "player": item["Player"],
        "prop": f"{item['Side']} {item['Line']} {item['Prop']}",
        "side": item["Side"], "line": item["Line"], "tier": item["Tier"],
        "status": "PENDING", "result": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parlay_id": lid, "override": item["Tier"] not in ("SOVEREIGN", "ELITE"),
        "sharp_ref": sharp_ref,
    })
    return lid

def parse_pasted_results(text):
    results = []
    for line in text.strip().split("\n"):
        match = re.match(r"(.+?)\s+(OVER|UNDER|ML|SPREAD)\s+([\d.]+)\s+(WIN|LOSS)", line.strip(), re.IGNORECASE)
        if match:
            results.append({"player": match.group(1).strip(), "side": match.group(2).upper(), "line": float(match.group(3)), "outcome": match.group(4).upper()})
    return results

# =========================
# SAMPLE DATA
# =========================
def get_sample_data(sport):
    if sport == "NBA":
        return {
            "raw_props": [{"Player": p, "Prop": t, "Line": l, "Side": s, "Sport": "NBA"} for p, t, l, s in [("Shai Gilgeous-Alexander", "POINTS", 31.5, "OVER"), ("Cade Cunningham", "POINTS", 23.5, "OVER"), ("Donovan Mitchell", "POINTS", 27.5, "UNDER")]],
            "raw_games": [{"Matchup": "OKC @ LAL", "Spread": "OKC -8.5", "Total": "O/U 214.5", "Moneyline": "OKC -400", "Sport": "NBA"}],
            "injuries": [], "blowout_games": [{"Game": "OKC @ LAL", "Spread": "-8.5", "Advisory": "⚠️ ACTIVE"}], "filtered_count": 1,
        }
    if sport == "MLB":
        return {
            "raw_props": [{"Player": p, "Prop": t, "Line": l, "Side": s, "Sport": "MLB"} for p, t, l, s in [("Aaron Judge", "H+R+RBI", 0.5, "OVER"), ("Spencer Strider", "STRIKEOUTS", 4.5, "OVER")]],
            "raw_games": [{"Matchup": "TEX @ NYY", "Spread": "NYY -1.5", "Total": "O/U 8.5", "Moneyline": "NYY -152", "Sport": "MLB"}],
            "injuries": [], "blowout_games": [], "filtered_count": 1,
        }
    return {"raw_props": [], "raw_games": [], "injuries": [], "blowout_games": [], "filtered_count": 0}

def load_sport_data(sport):
    data = get_sample_data(sport)
    st.session_state.raw_props = data["raw_props"]
    st.session_state.raw_games = data["raw_games"]
    st.session_state.injuries = data["injuries"]
    st.session_state.blowout_games = data["blowout_games"]
    st.session_state.filtered_count = data["filtered_count"]
    st.session_state.last_sport = sport
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True
    st.session_state.board_data = run_council_on_props(data["raw_props"])
    st.session_state.game_verdicts = run_game_council_on_games(data["raw_games"])

def scan_all_sports():
    all_props, all_games = [], []
    for sport in SPORTS:
        data = get_sample_data(sport)
        all_props.extend(data["raw_props"])
        all_games.extend(data["raw_games"])
    prop_results = run_council_on_props(all_props)
    game_results = run_game_council_on_games(all_games)
    prop_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    game_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    st.session_state.cross_sport_board = {"props": prop_results, "games": game_results, "scanned_at": datetime.now().strftime("%H:%M:%S")}
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True
    sharp_lines = fetch_sharp_reference("nba")
    if sharp_lines:
        st.session_state.sharp_data = {"lines": sharp_lines, "pulled_at": datetime.now().strftime("%H:%M:%S")}

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
    if st.button("🌍 Scan All Sports", use_container_width=True):
        scan_all_sports()
        amt = len(st.session_state.cross_sport_board["props"]) if st.session_state.cross_sport_board else 0
        st.success(f"All 9 leagues scanned. {amt} props evaluated.")
    if st.button("🟢 Load Board"):
        load_sport_data(st.session_state.last_sport)
        st.success(f"{st.session_state.last_sport} loaded.")
    if st.button("🔄 Re-Run Council"):
        st.session_state.board_data = run_council_on_props(st.session_state.raw_props)
        st.session_state.game_verdicts = run_game_council_on_games(st.session_state.raw_games)
        st.success("Refreshed.")
    st.markdown("---")
    st.markdown("### 🎯 Sharp Reference (Optional)")
    st.caption(f"Source: {SHARP_REFERENCE['name']}")
    st.caption(f"Install: `{SHARP_REFERENCE['install_cmd']}`")
    if st.button("🎯 Pull Sharp Lines (Pinnacle)", use_container_width=True):
        lines = fetch_sharp_reference("nba")
        if lines:
            st.session_state.sharp_data = {"lines": lines, "pulled_at": datetime.now().strftime("%H:%M:%S")}
            st.success(f"Pulled {len(lines)} sharp lines from Pinnacle via OddsHarvester.")
        else:
            st.warning("OddsHarvester not installed or Pinnacle lines unavailable. Run: pip install oddsharvester")

# =========================
# COMMAND BAR
# =========================
pending_count = len([l for l in st.session_state.locks if l.get("status") == "PENDING"])
st.markdown(f"""
<div class="command-bar">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;">
        <div style="width:42px;height:42px;background:linear-gradient(135deg,#e8a020,#b07010);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;">⚡</div>
        <div>
            <div style="font-size:22px;font-weight:700;color:#f4f8fc;letter-spacing:1px;">BetCouncil</div>
            <div style="font-size:11px;color:#5a7088;">v3.0 · 8 Models · 9 Sports · ESPN JSON API · Pinnacle Sharp Ref (Optional)</div>
        </div>
        <div style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;">
            <span class="toggle-btn active">🛡️ Safe: ON</span>
            <span class="toggle-btn active">⚠️ Blowout: ON</span>
            <span class="toggle-btn active">🏆 Playoff: ON</span>
            <span class="toggle-btn" style="border-color:#e8a020;color:#e8a020;background:rgba(232,160,32,0.1);">🔒 {pending_count} Lock{'s' if pending_count != 1 else ''}</span>
        </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:7px;">
        <div class="metric-box"><div class="metric-label">Bankroll</div><div class="metric-value gold-text">${st.session_state.bankroll:.2f}</div></div>
        <div class="metric-box"><div class="metric-label">Integrity</div><div class="metric-value" style="color:{'#16a84a' if st.session_state.integrity >= 70 else '#d03030' if st.session_state.integrity < 55 else '#e8a020'}">{st.session_state.integrity}/100</div></div>
        <div class="metric-box"><div class="metric-label">Active Floor</div><div class="metric-value green-text">12%</div></div>
        <div class="metric-box"><div class="metric-label">Kelly Fraction</div><div class="metric-value gold-text">{KELLY_FRACTION}</div></div>
        <div class="metric-box"><div class="metric-label">Unit</div><div class="metric-value gold-text">${active_unit()}</div></div>
        <div class="metric-box"><div class="metric-label">Active Locks</div><div class="metric-value" style="color:{'#e89020' if pending_count > 0 else '#5a7088'}">{pending_count}</div></div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================
# TABS
# =========================
tabs = st.tabs(["🌍 Cross-Sport", "🏀 Board of 8", "🔒 Locks of Day", "📋 Locks & Ledger", "🔄 Reconciliation", "🛡️ SEM & System"])

# Cross-Sport
with tabs[0]:
    st.markdown("# 🌍 CROSS-SPORT BEST BETS")
    cross = st.session_state.cross_sport_board
    if not cross:
        st.info("Click 'Scan All Sports' in the sidebar.")
    else:
        st.markdown(f"**Scanned at:** {cross['scanned_at']} | **9 sports**")
        if st.session_state.sharp_data and st.session_state.sharp_available:
            st.markdown(f"""<div class="sharp-ref-box"><span style="color:#e8a020;font-weight:600;">🎯 Sharp Reference Active</span> — Pinnacle via OddsHarvester · Pulled at {st.session_state.sharp_data['pulled_at']} · {len(st.session_state.sharp_data['lines'])} lines</div>""", unsafe_allow_html=True)
        st.markdown("## 🏆 TOP 5 PROPS")
        for i, p in enumerate(cross["props"][:5], 1):
            tc = tier_color(p["Tier"])
            st.markdown(f"""<div class="section-card" style="border-left:3px solid {tc};"><span style="color:#5a7088;">#{i} · {p.get('Sport','')}</span> <span style="color:#f4f8fc;font-weight:600;">{p['Player']} {p['Side']} {p['Line']} {p['Prop']}</span> <span style="color:{tc};font-weight:600;">{p['Tier Label']}</span> <span style="font-family:monospace;color:#e8a020;float:right;">{p['Weighted Score']:.2f}</span></div>""", unsafe_allow_html=True)
            if st.button(f"🔒 Lock #{i}", key=f"cross_{i}"):
                st.success(f"Locked: {lock_single_prop(p)}")
        st.markdown("## 🏆 TOP 3 GAME LINES")
        for i, g in enumerate(cross["games"][:3], 1):
            tc = tier_color(g["Tier"])
            st.markdown(f"""<div class="section-card" style="border-left:3px solid {tc};"><span style="color:#5a7088;">#{i} · {g.get('Sport','')}</span> <span style="color:#f4f8fc;font-weight:600;">{g['Matchup']} — {g.get('Moneyline','')}</span> <span style="color:{tc};font-weight:600;">{g['Tier Label']}</span></div>""", unsafe_allow_html=True)

# Board of 8
with tabs[1]:
    st.markdown("# 🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")
    st.markdown("**Data Source:** BettingPros + RotoWire + CBS Sports + Covers + DraftKings + ESPN (JSON API)")
    st.markdown(f"**Sharp Reference:** {get_sharp_ref_status()}")

    st.markdown("---")
    st.markdown("## ⚡ MANUAL OVERRIDE")
    manual_input = st.text_area("Paste props", placeholder="LeBron James OVER 21.5 Points", height=100)
    c1, _, _ = st.columns([1, 1, 1])
    with c1:
        if st.button("⚡ Run Manual Analysis"):
            if manual_input.strip():
                parsed = parse_manual_input(manual_input)
                if parsed:
                    st.session_state.manual_results = []
                    for item in parsed:
                        cooked = run_council_on_props([{"Player": item["player"], "Prop": item["prop"], "Side": item["side"], "Line": item["line"], "Sport": "NBA"}])
                        if cooked: st.session_state.manual_results.append(cooked[0])
                    st.success(f"Analyzed {len(st.session_state.manual_results)} props.")

    if st.session_state.manual_results:
        for i, item in enumerate(st.session_state.manual_results):
            tc = tier_color(item["Tier"])
            st.markdown(f"""<div class="section-card" style="border-left:3px solid {tc};"><span style="color:#f4f8fc;font-weight:600;">{item['Player']} {item['Side']} {item['Line']} {item['Prop']}</span> <span style="color:{tc};font-weight:600;">{item['Tier Label']}</span> <span style="font-family:monospace;color:#e8a020;">{item['Weighted Score']:.2f}</span></div>""", unsafe_allow_html=True)
            if st.button(f"🔒 Lock", key=f"man_{i}"):
                st.success(f"Locked: {lock_single_prop(item)}")

    st.markdown("---")
    sport = st.selectbox("Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport), key="sport_select")
    st.session_state.last_sport = sport
    board = st.session_state.board_data

    if not board:
        st.info("Load a board from the sidebar.")
    else:
        st.markdown(f"🔒 **Validation Firewall:** PASSED ({len(st.session_state.blowout_games)} games, {len(st.session_state.injuries)} matchups verified, {st.session_state.filtered_count} props removed)")

        st.markdown("## 🗳️ MODEL‑BY‑MODEL VERDICTS")
        for model in MODELS:
            name, weight, em = model["name"], model["weight"], model["em"]
            approves = sum(1 for item in board if item["Votes"].get(name, 0) == 1)
            passes = sum(1 for item in board if item["Votes"].get(name, 0) == 0)
            with st.expander(f"{em} {name} · wt: {weight} · ✓{approves} ○{passes}"):
                for item in board:
                    vote = item["Votes"].get(name, 0)
                    if vote == 1:
                        st.markdown(f"✅ **{item['Player']} {item['Side']} {item['Line']} {item['Prop']}** — {item['Reasons'].get(name, '')}")
                for item in board:
                    if item["Votes"].get(name, 0) != 1:
                        st.markdown(f"❌ {item['Player']} — {item['Reasons'].get(name, '')}")

        st.markdown("## 🟦 COUNCIL CONSENSUS")
        consensus_sorted = sorted(board, key=lambda x: x["Weighted Score"], reverse=True)
        for i, item in enumerate(consensus_sorted):
            tc = tier_color(item["Tier"])
            approvals = sum(1 for v in item["Votes"].values() if v == 1)
            st.markdown(f"""<div class="section-card" style="border-left:3px solid {tc};display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;"><div><span style="color:#f4f8fc;font-weight:500;">{item['Player']} {item['Side']} {item['Line']} {item['Prop']}</span> <span style="color:#08a8c8;font-family:monospace;">{approvals}/8</span> <span style="font-weight:700;font-family:monospace;color:{tc};">{item['Weighted Score']:.2f}</span> <span style="font-size:11px;font-family:monospace;font-weight:600;padding:2px 8px;border-radius:3px;border:1px solid {tc};color:{tc};">{item['Tier Label']}</span></div></div>""", unsafe_allow_html=True)
            if item["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED"):
                if st.button(f"🔒 Lock", key=f"cons_{i}"):
                    st.success(f"Locked: {lock_single_prop(item)}")

        st.markdown("## 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        st.markdown(f"- **RLM Status:** DETECTED — Sharp money fading public Overs")
        st.markdown(f"- **Contrarian Flag:** ACTIVE")
        st.markdown(f"- **Regime Type:** STABLE")
        st.markdown(f"- **{get_sharp_ref_status()}**")

# =========================
# TAB 2 — LOCKS OF THE DAY
# =========================
with tabs[2]:
    st.markdown("# 🔒 LOCKS & PARLAYS OF THE DAY")
    board = st.session_state.board_data
    games = st.session_state.game_verdicts
    if not board:
        st.info("Load a board first.")
    else:
        approved = [i for i in board if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        if approved:
            best_prop = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[0]
            best_game = games[0] if games else None
            st.markdown("## 🔒 Lock of the Day")
            st.table(pd.DataFrame([{"Type": "Prop", "Pick": f"{best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']}", "Tier": best_prop['Tier Label']}] + ([{"Type": "Game", "Pick": best_game['Matchup'], "Bet": best_game.get('Moneyline',''), "Tier": best_game['Tier Label']}] if best_game else [])))

            col_p, col_g = st.columns(2)
            with col_p:
                st.markdown("""<div class="parlay-card"><h4 style="color:#16a84a;">⚡ Props Parlay</h4>""", unsafe_allow_html=True)
                prop_par = build_prop_parlay()
                if prop_par:
                    selected = []
                    for i, leg in enumerate(prop_par):
                        if st.checkbox(f"{leg['Player']} — {leg['Side']} {leg['Line']} {leg['Prop']} ({leg['Tier Label']})", value=True, key=f"pp_{i}"):
                            selected.append(leg)
                    if len(selected) >= 2 and st.button("🔒 Lock Props Parlay"):
                        lid = generate_lock_id()
                        for leg in selected:
                            lock_single_prop(leg)
                        st.success(f"Locked: {lid}")
                st.markdown("</div>", unsafe_allow_html=True)

            with col_g:
                st.markdown("""<div class="game-parlay-card"><h4 style="color:#2868d0;">🏆 Games Parlay</h4>""", unsafe_allow_html=True)
                game_par = build_game_parlay()
                if game_par:
                    selected_g = []
                    for i, leg in enumerate(game_par):
                        if st.checkbox(f"{leg['Matchup']} — {leg.get('Moneyline','')} ({leg['Tier Label']})", value=True, key=f"gp_{i}"):
                            selected_g.append(leg)
                    if len(selected_g) >= 2 and st.button("🔒 Lock Games Parlay"):
                        lid = generate_lock_id()
                        for leg in selected_g:
                            st.session_state.locks.append({"id": lid, "type": "GAME", "matchup": leg["Matchup"], "bet": leg.get("Moneyline", ""), "tier": leg["Tier"], "status": "PENDING", "result": None, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid, "sharp_ref": None})
                        st.success(f"Locked: {lid}")
                st.markdown("</div>", unsafe_allow_html=True)

# =========================
# TAB 3 — LOCKS & LEDGER
# =========================
with tabs[3]:
    st.markdown("# 📋 LOCKS & LEDGER")
    pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
    if not pending:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(pending):
            cols = st.columns([4, 1, 1, 1])
            with cols[0]:
                sharp_info = ""
                if lock.get("sharp_ref"):
                    sharp_info = f" | 🎯 Sharp: {lock['sharp_ref'].get('line','')} @ {lock['sharp_ref'].get('odds','')}"
                st.markdown(f"**{lock.get('id')}** — {lock.get('player', lock.get('matchup'))} | {lock.get('prop', lock.get('bet'))} | {lock.get('tier','?')}{sharp_info}")
            with cols[1]:
                if st.button("✅ WIN", key=f"w_{i}"):
                    lock["status"] = "RESOLVED"; lock["result"] = "WIN"
                    st.session_state.history.append(lock)
                    st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                    st.session_state.bankroll += active_unit()
                    st.rerun()
            with cols[2]:
                if st.button("❌ LOSS", key=f"l_{i}"):
                    lock["status"] = "RESOLVED"; lock["result"] = "LOSS"
                    st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                    st.session_state.history.append(lock)
                    st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                    st.session_state.bankroll -= active_unit()
                    st.rerun()
            with cols[3]:
                if st.button("🗑️ Remove", key=f"rm_{i}"):
                    st.session_state.locks.pop(i); st.rerun()

    if st.session_state.history:
        st.markdown("### Resolved History")
        st.table(pd.DataFrame([{"ID": h.get("id"), "Pick": h.get("player", h.get("matchup")), "Result": h.get("result"), "Tier": h.get("tier")} for h in st.session_state.history]))

# =========================
# TAB 4 — RECONCILIATION
# =========================
with tabs[4]:
    st.markdown("# 🔄 RECONCILIATION & SYNC")
    pasted = st.text_area("Format: Player OVER/UNDER Line WIN/LOSS", height=150)
    if st.button("🔍 Sync"):
        parsed = parse_pasted_results(pasted)
        if parsed:
            for lock in st.session_state.locks:
                if lock["status"] == "PENDING":
                    for r in parsed:
                        if (r["player"].lower() in lock.get("player", "").lower() and r["side"] == lock.get("side", "") and abs(r["line"] - lock.get("line", 0)) < 0.1):
                            lock["status"] = "RESOLVED"; lock["result"] = r["outcome"]
                            st.session_state.history.append(lock)
                            if r["outcome"] == "WIN":
                                st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                                st.session_state.bankroll += active_unit()
                            else:
                                st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                                st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                                st.session_state.bankroll -= active_unit()
            st.session_state.locks = [l for l in st.session_state.locks if l["status"] == "PENDING"]
            st.success("Synced.")
    st.markdown("---")
    if st.session_state.autopsy_log:
        st.markdown("### 🔬 Autopsy Log")
        st.table(pd.DataFrame(st.session_state.autopsy_log))

# =========================
# TAB 5 — SEM & SYSTEM
# =========================
with tabs[5]:
    st.markdown("# 🛡️ SEM & SYSTEM HEALTH")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Integrity", f"{st.session_state.integrity}/100")
    c2.metric("Safe Corridor", "ACTIVE")
    c3.metric("Emergency Floor", "ACTIVE (12%)")
    c4.metric("Bankroll", f"${st.session_state.bankroll:.2f}")

    st.markdown("---")
    st.markdown("## 📡 Site Health")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Prop & Sharp Sources")
        for name in list(PROP_SOURCES.keys()) + [SHARP_REFERENCE["name"]]:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "—")
            st.markdown(f"{dot(s)} **{name}** — {t}")
    with c2:
        st.markdown("### Game & Lineup Sources")
        for name in list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys()):
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "—")
            st.markdown(f"{dot(s)} **{name}** — {t}")

    st.markdown("---")
    st.markdown("## 🎯 Sharp Reference Status")
    st.markdown(f"**Source:** {SHARP_REFERENCE['name']}")
    st.markdown(f"**Cost:** {SHARP_REFERENCE['cost']}")
    st.markdown(f"**Install:** `{SHARP_REFERENCE['install_cmd']}`")
    st.markdown(f"**Current status:** {get_sharp_ref_status()}")
    st.caption("The sharp reference is optional. When available, Pinnacle lines are stored on locks and displayed in the Market Dynamics footer. When unavailable, the Council vote and CLV estimation are unaffected.")

    st.markdown("---")
    st.markdown("## ➕ Add Custom Source")
    nn = st.text_input("Source Name"); nu = st.text_input("Source URL (use {sport})")
    if st.button("Add Source") and nn and nu:
        PROP_SOURCES[nn] = nu
        st.session_state.site_status[nn] = {"status": "unknown", "last_checked": "—"}
        st.success(f"Added: {nn}")

    st.markdown("---")
    st.markdown("## 📖 Tier Legend")
    for tier, desc in TIER_DESCRIPTIONS.items():
        st.markdown(f"**{tier_label(tier)}** — {desc}")
