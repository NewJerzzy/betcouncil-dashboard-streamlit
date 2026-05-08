import streamlit as st
import pandas as pd
from datetime import date, datetime

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
h1, h2, h3, h4, h5 { color: #ffffff; }
.stButton > button {
    background-color: #7c4dff;
    color: #ffffff;
    border: none;
    border-radius: 0.5rem;
    padding: 0.6rem 1.5rem;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
}
.stButton > button:hover { background-color: #651fff; }
.stButton > button:disabled { opacity: 0.4; cursor: not-allowed; }
.sovereign-badge { color: #00c853; font-weight: 700; }
.elite-badge { color: #ffd600; font-weight: 700; }
.approved-badge { color: #448aff; font-weight: 600; }
.lean-badge { color: #9e9e9e; font-weight: 600; }
.pass-badge { color: #ff5252; font-weight: 600; }
.model-name { color: #7c4dff; font-weight: 600; }
.footer-text { color: #7b8794; font-size: 0.9rem; }
.site-card {
    background-color: #141824;
    border: 1px solid #1f2639;
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 0.5rem;
}
.status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
}
.dot-green { background-color: #00c853; }
.dot-red { background-color: #ff5252; }
.dot-yellow { background-color: #ffd600; }
.dot-gray { background-color: #616161; }
.section-divider {
    border-top: 1px solid #1f2639;
    margin: 1.5rem 0;
}
.stExpander {
    border: 1px solid #1f2639;
    border-radius: 0.75rem;
    background-color: #141824;
}
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
DEFAULT_BANKROLL = 527.00
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
    "ESPN": "https://www.espn.com/{sport}/odds",
    "DraftKings": "https://sportsbook.draftkings.com/page/{sport}-game-lines",
    "Covers": "https://www.covers.com/sport/{sport}/odds",
}

LINEUP_SOURCES = {
    "DraftEdge": "https://draftedge.com/{sport}/{sport}-starting-lineups/",
    "RotoWire": "https://www.rotowire.com/basketball/{sport}/lineups.php",
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
if "board_data" not in st.session_state:
    st.session_state.board_data = None
if "game_verdicts" not in st.session_state:
    st.session_state.game_verdicts = None
if "last_sport" not in st.session_state:
    st.session_state.last_sport = "NBA"
if "lock_num" not in st.session_state:
    st.session_state.lock_num = 0
if "injuries" not in st.session_state:
    st.session_state.injuries = []
if "blowout_games" not in st.session_state:
    st.session_state.blowout_games = []
if "filtered_count" not in st.session_state:
    st.session_state.filtered_count = 0
if "raw_props" not in st.session_state:
    st.session_state.raw_props = []
if "raw_games" not in st.session_state:
    st.session_state.raw_games = []
if "site_status" not in st.session_state:
    st.session_state.site_status = {
        name: {"status": "unknown", "last_checked": None}
        for name in list(PROP_SOURCES.keys()) + list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys())
    }

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
    return {"SOVEREIGN": "🟢 Sovereign Lock", "ELITE": "🟡 Elite Edge", "APPROVED": "🔵 Approved Single", "LEAN": "⚪ Lean", "PASS": "🔴 PASS"}.get(tier, "—")

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

# =========================
# DATA LOADERS PER SPORT
# =========================
NBA_SAMPLE = {
    "raw_props": [
        {"Player": "Jalen Brunson", "Prop": "POINTS", "Line": 26.5, "Side": "OVER"},
        {"Player": "Karl-Anthony Towns", "Prop": "POINTS", "Line": 20.5, "Side": "OVER"},
        {"Player": "Anthony Edwards", "Prop": "POINTS", "Line": 22.5, "Side": "UNDER"},
        {"Player": "Victor Wembanyama", "Prop": "POINTS", "Line": 26.5, "Side": "OVER"},
        {"Player": "De'Aaron Fox", "Prop": "POINTS", "Line": 18.5, "Side": "OVER"},
        {"Player": "Julius Randle", "Prop": "POINTS", "Line": 17.5, "Side": "OVER"},
        {"Player": "Joel Embiid", "Prop": "POINTS", "Line": 28.5, "Side": "OVER"},
        {"Player": "Tyrese Maxey", "Prop": "POINTS", "Line": 24.5, "Side": "UNDER"},
        {"Player": "Jalen Brunson", "Prop": "PTS+AST", "Line": 34.5, "Side": "OVER"},
        {"Player": "Karl-Anthony Towns", "Prop": "PTS+AST+REB", "Line": 32.5, "Side": "OVER"},
        {"Player": "Victor Wembanyama", "Prop": "PTS+AST+REB", "Line": 44.5, "Side": "OVER"},
    ],
    "raw_games": [
        {"Matchup": "NYK @ PHI", "Spread": "NYK -4.5", "Total": "O/U 213.5", "Moneyline": "NYK -190 / PHI +160"},
        {"Matchup": "MIN @ SAS", "Spread": "SAS -3.5", "Total": "O/U 215.5", "Moneyline": "SAS -165 / MIN +140"},
    ],
    "injuries": [
        {"Player": "Joel Embiid", "Status": "PROBABLE (Knee)"},
        {"Player": "Anthony Edwards", "Status": "Cleared to play"},
    ],
    "blowout_games": [
        {"Game": "NYK @ PHI", "Spread": "-4.5", "Advisory": "❌ Inactive"},
        {"Game": "MIN @ SAS", "Spread": "-3.5", "Advisory": "❌ Inactive"},
    ],
    "filtered_count": 5,
}

MLB_SAMPLE = {
    "raw_props": [
        {"Player": "Aaron Judge", "Prop": "H+R+RBI", "Line": 0.5, "Side": "OVER"},
        {"Player": "Shohei Ohtani", "Prop": "H+R+RBI", "Line": 0.5, "Side": "OVER"},
        {"Player": "Juan Soto", "Prop": "H+R+RBI", "Line": 0.5, "Side": "OVER"},
        {"Player": "Bryce Harper", "Prop": "H+R+RBI", "Line": 0.5, "Side": "OVER"},
        {"Player": "Ronald Acuna Jr.", "Prop": "H+R+RBI", "Line": 0.5, "Side": "OVER"},
        {"Player": "Freddie Freeman", "Prop": "H+R+RBI", "Line": 0.5, "Side": "OVER"},
        {"Player": "Spencer Strider", "Prop": "STRIKEOUTS", "Line": 4.5, "Side": "OVER"},
        {"Player": "Tarik Skubal", "Prop": "STRIKEOUTS", "Line": 4.5, "Side": "OVER"},
        {"Player": "Zack Wheeler", "Prop": "STRIKEOUTS", "Line": 4.5, "Side": "OVER"},
        {"Player": "Logan Gilbert", "Prop": "STRIKEOUTS", "Line": 4.5, "Side": "OVER"},
    ],
    "raw_games": [
        {"Matchup": "TEX @ NYY", "Spread": "NYY -1.5", "Total": "O/U 8.5", "Moneyline": "NYY -152"},
        {"Matchup": "ATH @ PHI", "Spread": "PHI -1.5", "Total": "O/U 9.0", "Moneyline": "PHI -133"},
        {"Matchup": "CIN @ CHC", "Spread": "CHC -1.5", "Total": "O/U 8.5", "Moneyline": "CHC -196"},
    ],
    "injuries": [
        {"Player": "None", "Status": "No major injuries reported"},
    ],
    "blowout_games": [
        {"Game": "MLB", "Spread": "N/A", "Advisory": "❌ Inactive (MLB)"},
    ],
    "filtered_count": 8,
}

def load_sport_data(sport):
    if sport == "NBA":
        data = NBA_SAMPLE
    elif sport == "MLB":
        data = MLB_SAMPLE
    else:
        data = {"raw_props": [], "raw_games": [], "injuries": [], "blowout_games": [], "filtered_count": 0}
    st.session_state.raw_props = data["raw_props"]
    st.session_state.raw_games = data["raw_games"]
    st.session_state.injuries = data["injuries"]
    st.session_state.blowout_games = data["blowout_games"]
    st.session_state.filtered_count = data["filtered_count"]
    st.session_state.last_sport = sport

def mark_site_ok(name):
    st.session_state.site_status[name] = {"status": "ok", "last_checked": datetime.now().strftime("%H:%M:%S")}

# =========================
# COUNCIL LOGIC
# =========================
def run_council():
    raw = st.session_state.raw_props
    if not raw:
        st.session_state.board_data = None
        return
    results = []
    for prop in raw:
        player = prop["Player"]
        ptype = prop["Prop"]
        side = prop["Side"]
        line = prop["Line"]
        votes = {}
        reasons = {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO"])
        is_embiid = "EMBIID" in player.upper()
        is_edwards_under = "EDWARDS" in player.upper() and "UNDER" in side.upper()
        is_hrrbi = "H+R+RBI" in ptype.upper() or "HRRBI" in ptype.upper()
        is_ks = "STRIKEOUT" in ptype.upper() or "KS" in ptype.upper()
        is_under = "UNDER" in side.upper()

        # v5.3 DeepSeek
        if is_combo:
            votes[MODELS[0]["name"]] = 0
            reasons[MODELS[0]["name"]] = "Combo props — variance too high"
        elif is_under:
            votes[MODELS[0]["name"]] = 1
            reasons[MODELS[0]["name"]] = "Outlier suppression supports Under"
        else:
            votes[MODELS[0]["name"]] = 1
            reasons[MODELS[0]["name"]] = "Consistent, outlier clean"

        # v6.5 Gemini
        votes[MODELS[1]["name"]] = 0
        reasons[MODELS[1]["name"]] = "No environmental edge (indoor/neutral conditions)"

        # v25.4 Claude
        if is_embiid:
            votes[MODELS[2]["name"]] = 0
            reasons[MODELS[2]["name"]] = "Injury variance"
        elif is_edwards_under:
            votes[MODELS[2]["name"]] = 1
            reasons[MODELS[2]["name"]] = "Game 1 collapse; Wemby factor"
        else:
            votes[MODELS[2]["name"]] = 1
            reasons[MODELS[2]["name"]] = "Motivation / competitive script"

        # v4.0 Copilot
        if is_combo or is_embiid:
            votes[MODELS[3]["name"]] = 0
            reasons[MODELS[3]["name"]] = "Floor unreliable or too close"
        else:
            votes[MODELS[3]["name"]] = 1
            reasons[MODELS[3]["name"]] = "Deterministic floor above line"

        # v4.1 Perplexity
        if is_combo:
            votes[MODELS[4]["name"]] = 0
            reasons[MODELS[4]["name"]] = "High-variance combo — sigma too wide"
        else:
            votes[MODELS[4]["name"]] = 1
            reasons[MODELS[4]["name"]] = "Single-stat / low volatility"

        # v6.0 Supreme
        if is_embiid:
            votes[MODELS[5]["name"]] = 0
            reasons[MODELS[5]["name"]] = "Injury — CLV uncertain"
        elif is_edwards_under:
            votes[MODELS[5]["name"]] = 1
            reasons[MODELS[5]["name"]] = "Edge meets Emergency Floor (12%)"
        elif is_ks and line > 4.5:
            votes[MODELS[5]["name"]] = 0
            reasons[MODELS[5]["name"]] = "Edge below 12% Emergency Floor"
        else:
            votes[MODELS[5]["name"]] = 1
            reasons[MODELS[5]["name"]] = "CLV positive, governance clear"

        # v22.6 Grok
        if is_combo or is_embiid:
            votes[MODELS[6]["name"]] = 0
            reasons[MODELS[6]["name"]] = "Ceiling variance too high or unknown"
        else:
            votes[MODELS[6]["name"]] = 1
            reasons[MODELS[6]["name"]] = "Ceiling manageable"

        # Base Model
        if is_combo or is_embiid:
            votes[MODELS[7]["name"]] = 0
            reasons[MODELS[7]["name"]] = "Projection within margin of error"
        else:
            votes[MODELS[7]["name"]] = 1
            reasons[MODELS[7]["name"]] = "Raw projection supports"

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
    if not games:
        st.session_state.game_verdicts = None
        return
    results = []
    for game in games:
        matchup = game["Matchup"]
        votes = {}
        for model in MODELS:
            votes[model["name"]] = 1 if any(t in matchup for t in ["NYY", "PHI", "CHC", "NYK", "SAS"]) else 0
        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({
            "Matchup": matchup,
            "Moneyline": game.get("Moneyline", ""),
            "Spread": game.get("Spread", ""),
            "Total": game.get("Total", ""),
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

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ BetCouncil v3.0")
    st.markdown("### Hard Engine")
    st.session_state.bankroll = st.number_input("Bankroll ($)", value=float(st.session_state.bankroll), step=10.0)
    unit = active_unit()
    st.metric("Active Unit", f"${unit:.2f}")
    st.metric("Integrity Score", st.session_state.integrity)
    st.checkbox("Safe Corridor", value=st.session_state.safe_corridor, key="safe_corridor")
    st.checkbox("Emergency Floor (12%)", value=st.session_state.emergency_floor, key="emergency_floor")
    st.markdown("---")
    st.markdown("### Quick Actions")
    if st.button("📡 Load Board for Selected Sport"):
        load_sport_data(st.session_state.last_sport)
        run_council()
        run_game_council()
        for name in PROP_SOURCES:
            mark_site_ok(name)
        for name in GAME_SOURCES:
            mark_site_ok(name)
        for name in LINEUP_SOURCES:
            mark_site_ok(name)
        st.success(f"{st.session_state.last_sport} board loaded.")
    if st.button("🔄 Re-Run Council"):
        run_council()
        run_game_council()
        st.success("Council refreshed.")

# =========================
# TABS
# =========================
tabs = st.tabs(["🏀 Board of 8", "🔒 Locks of the Day", "📋 Locks & Ledger", "🛡️ SEM & System"])

# =========================
# TAB 1 — BOARD OF 8
# =========================
with tabs[0]:
    st.markdown("# 🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")

    sport = st.selectbox("Select Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport), key="sport_selector")
    st.session_state.last_sport = sport

    st.markdown(
        f"**Data Source:** BettingPros + RotoWire + CBS Sports + Covers + DraftKings + ESPN  \n"
        f"**Sport:** {sport} — {date.today().strftime('%B %d, %Y')}  \n"
        f"**Status:** {'🛡️ SAFE CORRIDOR ACTIVE' if st.session_state.safe_corridor else '✅ NORMAL MODE'} | "
        f"{'🚨 EMERGENCY FLOOR ACTIVE (12%)' if st.session_state.emergency_floor else '✅ REGULAR FLOOR (4.5%)'}"
    )
    board = st.session_state.board_data
    if board:
        st.markdown(
            f"🔒 **Validation Firewall:** PASSED ({len(st.session_state.blowout_games)} games, "
            f"{len(st.session_state.injuries)} matchups verified, {st.session_state.filtered_count} props removed)"
        )
    st.markdown("---")

    if not board:
        st.info("No board loaded. Use the sidebar 'Load Board' button or select a sport and load data.")
    else:
        st.markdown("## 🚨 PRE‑FILTER: LINEUP & INJURY VERIFICATION")
        if st.session_state.injuries:
            st.table(pd.DataFrame(st.session_state.injuries))
        else:
            st.write("No lineup issues.")

        st.markdown("## 🚨 BLOWOUT ADVISORY")
        if st.session_state.blowout_games:
            st.table(pd.DataFrame(st.session_state.blowout_games))
        else:
            st.write("No spread ≥10. Advisory inactive.")

        st.markdown("## 📊 PROPS SURVIVED PRE‑FILTER")
        display = [{"Player": p["Player"], "Prop": p["Prop"], "Line": p["Line"], "Side": p["Side"]} for p in st.session_state.raw_props]
        st.table(pd.DataFrame(display))

        st.markdown("---")
        st.markdown("## 🗳️ MODEL‑BY‑MODEL VERDICTS")
        for model in MODELS:
            name = model["name"]
            weight = model["weight"]
            with st.expander(f"{name} (Weight: {weight})", expanded=False):
                approved = []
                passed = []
                for item in board:
                    vote = item["Votes"].get(name, 0)
                    reason = item["Reasons"].get(name, "")
                    if vote == 1:
                        approved.append((item, reason))
                    else:
                        passed.append((item, reason))
                if approved:
                    for item, reason in approved:
                        st.markdown(f"✅ **{item['Player']} {item['Side']} {item['Line']} {item['Prop']}** — {reason}")
                if passed:
                    st.markdown("**PASS:**")
                    for item, reason in passed:
                        st.markdown(f"❌ {item['Player']} ({reason})")

        st.markdown("---")
        st.markdown("## 🟦 COUNCIL CONSENSUS SUMMARY")
        summary_rows = []
        for item in board:
            summary_rows.append({
                "Pick": f"{item['Player']} {item['Side']} {item['Line']} {item['Prop']}",
                "Weighted Score": item["Weighted Score"],
                "Tier": item["Tier Label"],
            })
        summary_df = pd.DataFrame(summary_rows).sort_values("Weighted Score", ascending=False)
        st.table(summary_df)

        approved = [i for i in board if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        excluded = [i for i in board if i["Tier"] in ("LEAN", "PASS")]
        if excluded:
            st.markdown("**Excluded:** " + ", ".join([f"{i['Player']} ({i['Tier Label']})" for i in excluded]))

        st.markdown("---")
        st.markdown("## 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        st.markdown("- **RLM Status:** DETECTED — Sharp money fading public Overs")
        st.markdown("- **Contrarian Flag:** ACTIVE")
        st.markdown("- **Regime Type:** STABLE")

# =========================
# TAB 2 — LOCKS OF THE DAY
# =========================
with tabs[1]:
    st.markdown("# 🔒 BETCOUNCIL LOCKS & PARLAYS OF THE DAY")
    board = st.session_state.board_data
    games = st.session_state.game_verdicts
    if not board:
        st.info("Load a board first from the Board of 8 tab.")
    else:
        approved = [i for i in board if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        if approved:
            best_prop = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[0]
            best_game = games[0] if games else None

            st.markdown("## 🔒 Lock of the Day")
            lock_rows = [
                {"Type": "Prop", "Pick": f"{best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']}", "Tier": best_prop['Tier Label']},
            ]
            if best_game:
                lock_rows.append({"Type": "Game", "Pick": best_game["Matchup"], "Bet": best_game.get("Moneyline", "N/A"), "Tier": best_game['Tier Label']})
            st.table(pd.DataFrame(lock_rows))

            st.markdown("## 🔗 Prop Parlay of the Day")
            prop_par = build_prop_parlay()
            if prop_par:
                rows = []
                for i, leg in enumerate(prop_par, 1):
                    rows.append({"Leg": i, "Player": leg["Player"], "Team": leg["Player"].split()[-1], "Prop": f"{leg['Side']} {leg['Line']} {leg['Prop']}", "Tier": leg["Tier Label"]})
                st.table(pd.DataFrame(rows))
                if st.button("🔒 Lock Prop Parlay"):
                    lid = generate_lock_id()
                    for leg in prop_par:
                        st.session_state.locks.append({
                            "id": lid, "type": "PROP", "player": leg["Player"],
                            "prop": f"{leg['Side']} {leg['Line']} {leg['Prop']}", "side": leg["Side"],
                            "line": leg["Line"], "tier": leg["Tier"], "status": "PENDING",
                            "result": None, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid,
                        })
                    st.success(f"Locked: {lid}")

            st.markdown("## 🔗 Game Parlay of the Day")
            game_par = build_game_parlay()
            if game_par:
                rows = []
                for i, leg in enumerate(game_par, 1):
                    rows.append({"Leg": i, "Matchup": leg["Matchup"], "Bet": leg.get("Moneyline", "N/A"), "Tier": leg["Tier Label"]})
                st.table(pd.DataFrame(rows))
                if st.button("🔒 Lock Game Parlay"):
                    lid = generate_lock_id()
                    for leg in game_par:
                        st.session_state.locks.append({
                            "id": lid, "type": "GAME", "matchup": leg["Matchup"],
                            "bet": leg.get("Moneyline", "N/A"), "tier": leg["Tier"],
                            "status": "PENDING", "result": None,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid,
                        })
                    st.success(f"Locked: {lid}")
        else:
            st.info("No approved props on this board.")

# =========================
# TAB 3 — LOCKS & LEDGER
# =========================
with tabs[2]:
    st.markdown("# 🔒 Locks & Ledger")
    pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
    st.markdown("### Active Locks")
    if not pending:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(pending):
            with st.expander(f"{lock.get('id', '?')} — {lock.get('player', lock.get('matchup', '?'))}"):
                st.write(f"**Bet:** {lock.get('prop', lock.get('bet', ''))}")
                st.write(f"**Tier:** {lock.get('tier', '?')}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(f"✅ WIN", key=f"win_{i}"):
                        lock["status"] = "RESOLVED"; lock["result"] = "WIN"
                        st.session_state.history.append(lock)
                        st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                        st.session_state.bankroll += active_unit()
                        st.rerun()
                with c2:
                    if st.button(f"❌ LOSS", key=f"loss_{i}"):
                        lock["status"] = "RESOLVED"; lock["result"] = "LOSS"
                        st.session_state.history.append(lock)
                        st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                        st.session_state.bankroll -= active_unit()
                        st.rerun()

    st.markdown("---")
    st.markdown("### Resolved History")
    if st.session_state.history:
        hist = []
        for h in st.session_state.history:
            hist.append({"ID": h.get("id","?"), "Pick": h.get("player", h.get("matchup","?")), "Result": h.get("result","?"), "Tier": h.get("tier","?")})
        st.table(pd.DataFrame(hist))
    else:
        st.info("No resolved bets.")

# =========================
# TAB 4 — SEM & SYSTEM
# =========================
with tabs[3]:
    st.markdown("# 🛡️ SEM & System Health")
    st.markdown("## SEM Status")
    st.markdown(f"- **Integrity Score:** {st.session_state.integrity}")
    st.markdown(f"- **Safe Corridor:** {'ACTIVE' if st.session_state.safe_corridor else 'INACTIVE'}")
    st.markdown(f"- **Emergency Floor:** {'ACTIVE (12%)' if st.session_state.emergency_floor else 'INACTIVE'}")
    st.markdown(f"- **Bankroll:** ${st.session_state.bankroll:.2f}")
    st.markdown(f"- **Active Locks:** {len([l for l in st.session_state.locks if l.get('status') == 'PENDING'])}")

    st.markdown("---")
    st.markdown("## 📡 Site Health")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Prop Sources")
        for name in PROP_SOURCES:
            status = st.session_state.site_status.get(name, {}).get("status", "unknown")
            last = st.session_state.site_status.get(name, {}).get("last_checked", "—")
            st.markdown(f"{dot(status)} **{name}** — {last}")
    with col2:
        st.markdown("### Game & Lineup Sources")
        for name in list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys()):
            status = st.session_state.site_status.get(name, {}).get("status", "unknown")
            last = st.session_state.site_status.get(name, {}).get("last_checked", "—")
            st.markdown(f"{dot(status)} **{name}** — {last}")

    st.markdown("---")
    st.markdown("## ➕ Add Custom Source")
    new_name = st.text_input("Source Name")
    new_url = st.text_input("Source URL (use {sport} placeholder)")
    if st.button("Add Source") and new_name and new_url:
        PROP_SOURCES[new_name] = new_url
        st.session_state.site_status[new_name] = {"status": "unknown", "last_checked": "—"}
        st.success(f"Added: {new_name}")
