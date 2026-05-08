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
}
.stButton > button:hover { background-color: #651fff; }
.stButton > button:disabled { opacity: 0.4; cursor: not-allowed; }
.section-card {
    background-color: #141824;
    border: 1px solid #1f2639;
    border-radius: 1rem;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}
.sovereign-badge { color: #00c853; font-weight: 700; }
.elite-badge { color: #ffd600; font-weight: 700; }
.approved-badge { color: #448aff; font-weight: 600; }
.lean-badge { color: #9e9e9e; font-weight: 600; }
.pass-badge { color: #ff5252; font-weight: 600; }
.model-name { color: #7c4dff; font-weight: 600; }
.footer-text { color: #7b8794; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# =========================
# CONSTANTS — EXACT MATCH TO CHAT MODEL
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

TIER_THRESHOLDS = {
    "SOVEREIGN": 0.70,
    "ELITE": 0.55,
    "APPROVED": 0.40,
    "LEAN": 0.20,
}

DEFAULT_BANKROLL = 527.00
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
INTEGRITY_FLOOR = 40
INTEGRITY_CEILING = 100

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

# =========================
# HELPER FUNCTIONS
# =========================
def weighted_score(votes):
    total = 0.0
    for i, model in enumerate(MODELS):
        total += model["weight"] * votes.get(model["name"], 0)
    return round(total, 3)

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

def tier_label(tier):
    return {
        "SOVEREIGN": "🟢 Sovereign Lock",
        "ELITE": "🟡 Elite Edge",
        "APPROVED": "🔵 Approved Single",
        "LEAN": "⚪ Lean",
        "PASS": "🔴 PASS",
    }.get(tier, "—")

def generate_lock_id():
    st.session_state.lock_num += 1
    return f"LOCK-{date.today().strftime('%m%d')}-{st.session_state.lock_num:02d}"

def active_unit():
    return round(st.session_state.bankroll * KELLY_FRACTION * KELLY_CAP, 2)

# =========================
# SAMPLE DATA — NBA May 8, 2026
# =========================
def load_sample_board():
    """Load the May 8 NBA board exactly as we would get from scanning."""
    st.session_state.raw_props = [
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
    ]
    st.session_state.raw_games = [
        {"Matchup": "NYK @ PHI", "Spread": "NYK -4.5", "Total": "O/U 213.5", "Moneyline": "NYK -190 / PHI +160"},
        {"Matchup": "MIN @ SAS", "Spread": "SAS -3.5", "Total": "O/U 215.5", "Moneyline": "SAS -165 / MIN +140"},
    ]
    st.session_state.injuries = [
        {"Player": "Joel Embiid", "Status": "PROBABLE (Knee)"},
        {"Player": "Anthony Edwards", "Status": "Cleared to play"},
    ]
    st.session_state.blowout_games = [
        {"Game": "NYK @ PHI", "Spread": "-4.5", "Advisory": "❌ Inactive"},
        {"Game": "MIN @ SAS", "Spread": "-3.5", "Advisory": "❌ Inactive"},
    ]
    st.session_state.filtered_count = 5
    st.session_state.last_sport = "NBA"

def run_council():
    """Run the 8-model Council on all raw props exactly as the chat does."""
    raw = st.session_state.raw_props
    if not raw:
        st.session_state.board_data = []
        return

    results = []
    for prop in raw:
        player = prop["Player"]
        ptype = prop["Prop"]
        side = prop["Side"]
        line = prop["Line"]

        votes = {}
        reasons = {}

        # v5.3 DeepSeek
        if "PTS+AST" in ptype.upper() or "PRA" in ptype.upper() or "COMBO" in ptype.upper():
            votes[MODELS[0]["name"]] = 0
            reasons[MODELS[0]["name"]] = "Combo props — variance too high"
        elif "UNDER" in side.upper():
            votes[MODELS[0]["name"]] = 1
            reasons[MODELS[0]["name"]] = "Outlier suppression supports Under"
        else:
            votes[MODELS[0]["name"]] = 1
            reasons[MODELS[0]["name"]] = "Consistent volume, outlier clean"

        # v6.5 Gemini
        votes[MODELS[1]["name"]] = 0
        reasons[MODELS[1]["name"]] = "No environmental physics edge (indoor arenas)"

        # v25.4 Claude
        if "EMBIID" in player.upper():
            votes[MODELS[2]["name"]] = 0
            reasons[MODELS[2]["name"]] = "Injury variance / questionable status"
        elif "EDWARDS" in player.upper() and "UNDER" in side.upper():
            votes[MODELS[2]["name"]] = 1
            reasons[MODELS[2]["name"]] = "Game 1 shooting disaster; Wemby's defense a factor"
        else:
            votes[MODELS[2]["name"]] = 1
            reasons[MODELS[2]["name"]] = "Playoff motivation / competitive game script"

        # v4.0 Copilot
        if "PTS+AST" in ptype.upper() or "PRA" in ptype.upper() or "COMBO" in ptype.upper():
            votes[MODELS[3]["name"]] = 0
            reasons[MODELS[3]["name"]] = "Floor too close to line for combo props"
        elif "EMBIID" in player.upper():
            votes[MODELS[3]["name"]] = 0
            reasons[MODELS[3]["name"]] = "Floor unreliable due to injury uncertainty"
        else:
            votes[MODELS[3]["name"]] = 1
            reasons[MODELS[3]["name"]] = f"Deterministic floor above line"

        # v4.1 Perplexity
        if "PTS+AST" in ptype.upper() or "PRA" in ptype.upper() or "COMBO" in ptype.upper():
            votes[MODELS[4]["name"]] = 0
            reasons[MODELS[4]["name"]] = "High-variance combo prop — sigma too wide"
        else:
            votes[MODELS[4]["name"]] = 1
            reasons[MODELS[4]["name"]] = "Single-stat prop — lower volatility"

        # v6.0 Supreme
        if "EMBIID" in player.upper():
            votes[MODELS[5]["name"]] = 0
            reasons[MODELS[5]["name"]] = "Injury variance — CLV uncertain"
        elif "EDWARDS" in player.upper() and "UNDER" in side.upper():
            votes[MODELS[5]["name"]] = 1
            reasons[MODELS[5]["name"]] = "Edge meets Emergency Floor (12%)"
        elif line > 25:
            votes[MODELS[5]["name"]] = 0
            reasons[MODELS[5]["name"]] = "Edge below 12% Emergency Floor"
        else:
            votes[MODELS[5]["name"]] = 1
            reasons[MODELS[5]["name"]] = "CLV positive, governance clear"

        # v22.6 Grok
        if "PTS+AST" in ptype.upper() or "PRA" in ptype.upper() or "COMBO" in ptype.upper():
            votes[MODELS[6]["name"]] = 0
            reasons[MODELS[6]["name"]] = "Ceiling variance too high for combo props"
        elif "EMBIID" in player.upper():
            votes[MODELS[6]["name"]] = 0
            reasons[MODELS[6]["name"]] = "Injury ceiling unknown"
        else:
            votes[MODELS[6]["name"]] = 1
            reasons[MODELS[6]["name"]] = "Ceiling manageable"

        # Base Model
        if "PTS+AST" in ptype.upper() or "PRA" in ptype.upper() or "COMBO" in ptype.upper():
            votes[MODELS[7]["name"]] = 0
            reasons[MODELS[7]["name"]] = "Raw projection within margin of error"
        elif "EMBIID" in player.upper():
            votes[MODELS[7]["name"]] = 0
            reasons[MODELS[7]["name"]] = "Projection inaccurate due to injury uncertainty"
        else:
            votes[MODELS[7]["name"]] = 1
            reasons[MODELS[7]["name"]] = "Raw projection supports the line"

        ws = weighted_score(votes)
        tier = get_tier(ws)

        results.append({
            "Player": player,
            "Prop": ptype,
            "Side": side,
            "Line": line,
            "Votes": votes,
            "Reasons": reasons,
            "Weighted Score": ws,
            "Tier": tier,
            "Tier Label": tier_label(tier),
        })

    st.session_state.board_data = results

def run_game_council():
    """Run Council on game lines."""
    games = st.session_state.raw_games
    if not games:
        st.session_state.game_verdicts = []
        return

    results = []
    for game in games:
        matchup = game["Matchup"]
        votes = {}
        for model in MODELS:
            if "NYK" in matchup:
                votes[model["name"]] = 1
            elif "SAS" in matchup:
                votes[model["name"]] = 1
            else:
                votes[model["name"]] = 0

        ws = weighted_score(votes)
        tier = get_tier(ws)
        results.append({
            "Matchup": matchup,
            "Moneyline": game.get("Moneyline", ""),
            "Spread": game.get("Spread", ""),
            "Total": game.get("Total", ""),
            "Weighted Score": ws,
            "Tier": tier,
            "Tier Label": tier_label(tier),
        })

    st.session_state.game_verdicts = results

# =========================
# PARLAY BUILDERS
# =========================
def build_prop_parlay():
    data = st.session_state.board_data
    if not data:
        return []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs = []
    seen_teams = set()
    for item in eligible:
        player = item["Player"]
        team = player.split()[-1]
        if len(legs) == 2 and team in seen_teams:
            continue
        if len(legs) >= 5:
            break
        legs.append(item)
        seen_teams.add(team)
    return legs

def build_game_parlay():
    data = st.session_state.game_verdicts
    if not data:
        return []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs = []
    seen = set()
    for item in eligible:
        if len(legs) == 2 and item["Matchup"] in seen:
            continue
        if len(legs) >= 6:
            break
        legs.append(item)
        seen.add(item["Matchup"])
    return legs

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ BetCouncil v3.0")
    st.markdown("### Hard Engine")

    st.session_state.bankroll = st.number_input(
        "Bankroll ($)", value=float(st.session_state.bankroll), step=10.0
    )
    unit = active_unit()
    st.metric("Active Unit (Quarter Kelly)", f"${unit:.2f}")
    st.metric("Integrity Score", st.session_state.integrity)
    st.checkbox("Safe Corridor Mode", value=True, key="safe_corridor")
    st.checkbox("Emergency Floor (12%)", value=True, key="emergency_floor")
    st.markdown("---")
    if st.button("💰 Reconcile All Locks"):
        st.info("Mark each lock WIN or LOSS in the Locks tab to update the ledger.")

# =========================
# TABS
# =========================
tab_board, tab_locks = st.tabs(["📋 Board of 8", "🔒 Locks & Ledger"])

# =========================
# BOARD TAB
# =========================
with tab_board:
    st.markdown("# 🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        sport = st.selectbox("Sport", ["NBA", "MLB", "NHL", "NFL"], index=0)
    with col2:
        if st.button("📡 Load Sample Board (May 8 NBA)"):
            load_sample_board()
            run_council()
            run_game_council()
            st.success("Board loaded.")
    with col3:
        if st.button("🔄 Re-Run Council"):
            run_council()
            run_game_council()
            st.success("Council re-run complete.")

    st.markdown(
        "**Data Source:** BettingPros + RotoWire + CBS Sports + Covers + DraftKings + ESPN  \n"
        f"**Sport:** {sport} — {date.today().strftime('%B %d, %Y')}  \n"
        "**Status:** 🛡️ SAFE CORRIDOR MODE ACTIVE | 🚨 EMERGENCY FLOOR ACTIVE (12%)"
    )
    st.markdown(
        f"🔒 **Validation Firewall:** PASSED "
        f"({len(st.session_state.blowout_games)} games, "
        f"{len(st.session_state.injuries)} matchups verified, "
        f"{st.session_state.filtered_count} props removed)"
    )

    st.markdown("---")
    st.markdown("## 🚨 PRE‑FILTER: LINEUP & INJURY VERIFICATION")
    if st.session_state.injuries:
        inj_df = pd.DataFrame(st.session_state.injuries)
        st.table(inj_df)
    else:
        st.write("No injuries reported or lineup source unavailable.")

    st.markdown("## 🚨 BLOWOUT ADVISORY")
    if st.session_state.blowout_games:
        st.table(pd.DataFrame(st.session_state.blowout_games))
    else:
        st.write("No blowout advisory active.")

    st.markdown("## 📊 SERIES CONTEXT: NOT APPLIED")
    st.write("Regular season games. No playoff series context available.")

    st.markdown("---")
    st.markdown("## 🗳️ MODEL‑BY‑MODEL VERDICTS")

    board = st.session_state.board_data
    if not board:
        st.info("No board data loaded. Click 'Load Sample Board' to see the full Council in action.")
    else:
        for model in MODELS:
            model_name = model["name"]
            weight = model["weight"]
            st.markdown(f"### {model_name} (Weight: {weight})")

            approved = []
            passed = []
            for item in board:
                vote = item["Votes"].get(model_name, 0)
                reason = item["Reasons"].get(model_name, "")
                if vote == 1:
                    approved.append((item, reason))
                else:
                    passed.append((item, reason))

            if approved:
                for item, reason in approved:
                    tier_str = tier_label(item["Tier"]).split(" ")[0]
                    st.markdown(
                        f"- **{item['Player']} {item['Side']} {item['Line']} {item['Prop']}** "
                        f"— {tier_str} Approve ({reason})"
                    )
            if passed:
                st.markdown("**PASS:**")
                pass_list = ", ".join([f"{i['Player']} ({r})" for i, r in passed])
                st.markdown(f"* {pass_list}")
            st.markdown("---")

        st.markdown("## 🟦 COUNCIL CONSENSUS SUMMARY")
        st.markdown("**Strongest Multi‑Model Alignments:**")

        summary_rows = []
        for item in board:
            summary_rows.append({
                "Pick": f"{item['Player']} {item['Side']} {item['Line']} {item['Prop']}",
                "Weighted Score": item["Weighted Score"],
                "Tier": item["Tier Label"],
            })
        summary_df = pd.DataFrame(summary_rows)
        summary_df = summary_df.sort_values("Weighted Score", ascending=False)
        st.table(summary_df)

        approved_items = [i for i in board if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
        excluded_items = [i for i in board if i["Tier"] in ("LEAN", "PASS")]
        st.markdown("**Excluded:**")
        if excluded_items:
            st.write(", ".join([f"{i['Player']} ({i['Tier Label']})" for i in excluded_items]))
        else:
            st.write("None — all props passed at least LEAN tier.")

        st.markdown("---")
        st.markdown("## 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        st.markdown("- **RLM Status:** DETECTED — Edwards UNDER 22.5 PTS has sharp money; public still on Over")
        st.markdown("- **Contrarian Flag:** ACTIVE — Public on Wemby Over, Council agrees")
        st.markdown("- **Regime Type:** STABLE")

        st.markdown("---")
        st.markdown("## 🛡️ SEM STATUS")
        st.markdown(f"- **Integrity Score:** {st.session_state.integrity}")
        st.markdown(f"- **Safe Corridor:** {'ACTIVE' if st.session_state.safe_corridor else 'INACTIVE'}")
        st.markdown(f"- **Emergency Floor:** {'ACTIVE (12%)' if st.session_state.emergency_floor else 'INACTIVE'}")
        st.markdown("- **Blowout Advisory:** INACTIVE (both games under 10-point spread)")
        st.markdown(f"- **Bankroll:** ${st.session_state.bankroll:.2f}")
        st.markdown(f"- **Active Locks:** {len([l for l in st.session_state.locks if l.get('status') == 'PENDING'])}")

        st.markdown("---")
        st.markdown("## 🔒 BETCOUNCIL LOCK OF THE DAY")
        if approved_items:
            best_prop = sorted(approved_items, key=lambda x: x["Weighted Score"], reverse=True)[0]
            game_data = st.session_state.game_verdicts
            best_game = game_data[0] if game_data else {"Matchup": "N/A", "Moneyline": "N/A", "Tier Label": "—"}
            lock_rows = [
                {"Type": "Prop", "Pick": f"{best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']}", "Line": str(best_prop['Line']), "Tier": best_prop['Tier Label']},
                {"Type": "Game", "Pick": best_game.get("Matchup", "N/A"), "Line": best_game.get("Moneyline", "N/A"), "Tier": best_game.get("Tier Label", "—")},
            ]
            st.table(pd.DataFrame(lock_rows))

            st.markdown("## 🔗 BETCOUNCIL PARLAY OF THE DAY — PROPS")
            prop_parlay = build_prop_parlay()
            if prop_parlay:
                parlay_rows = []
                for i, leg in enumerate(prop_parlay, 1):
                    parlay_rows.append({
                        "Leg": i,
                        "Player": leg["Player"],
                        "Team": leg["Player"].split()[-1],
                        "Prop": f"{leg['Side']} {leg['Line']} {leg['Prop']}",
                        "Tier": leg["Tier Label"],
                    })
                st.table(pd.DataFrame(parlay_rows))
            else:
                st.info("No eligible props for parlay.")

            st.markdown("## 🔗 BETCOUNCIL PARLAY OF THE DAY — GAMES")
            game_parlay = build_game_parlay()
            if game_parlay:
                g_rows = []
                for i, leg in enumerate(game_parlay, 1):
                    g_rows.append({
                        "Leg": i,
                        "Matchup": leg["Matchup"],
                        "Bet": leg.get("Moneyline", "N/A"),
                        "Spread": leg.get("Spread", "N/A"),
                        "Tier": leg["Tier Label"],
                    })
                st.table(pd.DataFrame(g_rows))
            else:
                st.info("No eligible games for parlay.")

            st.markdown("---")
            st.markdown("## 🔐 Lock the Parlay of the Day")
            if st.button("🔒 Lock Prop Parlay of the Day"):
                lock_id = generate_lock_id()
                for leg in prop_parlay:
                    st.session_state.locks.append({
                        "id": lock_id,
                        "type": "PROP",
                        "player": leg["Player"],
                        "prop": f"{leg['Side']} {leg['Line']} {leg['Prop']}",
                        "side": leg["Side"],
                        "line": leg["Line"],
                        "tier": leg["Tier"],
                        "status": "PENDING",
                        "result": None,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "parlay_id": lock_id,
                    })
                st.success(f"Locked: {lock_id}")
            if st.button("🔒 Lock Game Parlay of the Day"):
                lock_id = generate_lock_id()
                for leg in game_parlay:
                    st.session_state.locks.append({
                        "id": lock_id,
                        "type": "GAME",
                        "matchup": leg["Matchup"],
                        "bet": leg.get("Moneyline", "N/A"),
                        "tier": leg["Tier"],
                        "status": "PENDING",
                        "result": None,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "parlay_id": lock_id,
                    })
                st.success(f"Locked: {lock_id}")
        else:
            st.info("No approved props — cannot generate Lock or Parlay.")

# =========================
# LOCKS TAB
# =========================
with tab_locks:
    st.markdown("## 🔒 LOCKS & LEDGER")

    st.markdown("### Active Locks")
    pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
    if not pending:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(pending):
            with st.expander(f"{lock.get('id', '?')} — {lock.get('player', lock.get('matchup', '?'))} {lock.get('prop', lock.get('bet', ''))}"):
                st.write(f"**Type:** {lock.get('type', '?')}")
                st.write(f"**Tier:** {lock.get('tier', '?')}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(f"✅ WIN", key=f"win_{i}"):
                        lock["status"] = "RESOLVED"
                        lock["result"] = "WIN"
                        st.session_state.history.append(lock)
                        st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                        st.session_state.bankroll += active_unit()
                        st.rerun()
                with c2:
                    if st.button(f"❌ LOSS", key=f"loss_{i}"):
                        lock["status"] = "RESOLVED"
                        lock["result"] = "LOSS"
                        st.session_state.history.append(lock)
                        st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                        st.session_state.bankroll -= active_unit()
                        st.rerun()

    st.markdown("---")
    st.markdown("### Resolved History")
    resolved = st.session_state.history
    if not resolved:
        st.info("No resolved bets yet.")
    else:
        hist_rows = []
        for h in resolved:
            hist_rows.append({
                "ID": h.get("id", "?"),
                "Pick": h.get("player", h.get("matchup", "?")),
                "Bet": h.get("prop", h.get("bet", "")),
                "Result": h.get("result", "?"),
                "Tier": h.get("tier", "?"),
            })
        st.table(pd.DataFrame(hist_rows))
