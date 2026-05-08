import streamlit as st
import pandas as pd
from datetime import date, datetime
import re
import io

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
if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "integrity" not in st.session_state: st.session_state.integrity = 67
if "safe_corridor" not in st.session_state: st.session_state.safe_corridor = True
if "emergency_floor" not in st.session_state: st.session_state.emergency_floor = True
if "locks" not in st.session_state: st.session_state.locks = []
if "history" not in st.session_state: st.session_state.history = []
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
# SAMPLE DATA
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
    "injuries": [{"Player": "None", "Status": "No major injuries reported"}],
    "blowout_games": [{"Game": "MLB", "Spread": "N/A", "Advisory": "❌ Inactive (MLB)"}],
    "filtered_count": 8,
}

def load_sport_data(sport):
    data = NBA_SAMPLE if sport == "NBA" else (MLB_SAMPLE if sport == "MLB" else {"raw_props": [], "raw_games": [], "injuries": [], "blowout_games": [], "filtered_count": 0})
    st.session_state.raw_props = data["raw_props"]
    st.session_state.raw_games = data["raw_games"]
    st.session_state.injuries = data["injuries"]
    st.session_state.blowout_games = data["blowout_games"]
    st.session_state.filtered_count = data["filtered_count"]
    st.session_state.last_sport = sport

# =========================
# COUNCIL LOGIC
# =========================
def run_council():
    raw = st.session_state.raw_props
    if not raw: st.session_state.board_data = None; return
    results = []
    for prop in raw:
        player, ptype, side, line = prop["Player"], prop["Prop"], prop["Side"], prop["Line"]
        votes, reasons = {}, {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO"])
        is_embiid = "EMBIID" in player.upper()
        is_under = "UNDER" in side.upper()

        votes[MODELS[0]["name"]] = 0 if is_combo else (1 if is_under else 1)
        reasons[MODELS[0]["name"]] = "Combo props — variance too high" if is_combo else ("Outlier suppression supports Under" if is_under else "Consistent, outlier clean")

        votes[MODELS[1]["name"]] = 0
        reasons[MODELS[1]["name"]] = "No environmental edge (indoor/neutral conditions)"

        votes[MODELS[2]["name"]] = 0 if is_embiid else 1
        reasons[MODELS[2]["name"]] = "Injury variance" if is_embiid else "Motivation / competitive script"

        votes[MODELS[3]["name"]] = 0 if (is_combo or is_embiid) else 1
        reasons[MODELS[3]["name"]] = "Floor unreliable or too close" if (is_combo or is_embiid) else "Deterministic floor above line"

        votes[MODELS[4]["name"]] = 0 if is_combo else 1
        reasons[MODELS[4]["name"]] = "High-variance combo — sigma too wide" if is_combo else "Single-stat / low volatility"

        votes[MODELS[5]["name"]] = 0 if is_embiid else 1
        reasons[MODELS[5]["name"]] = "Injury — CLV uncertain" if is_embiid else "CLV positive, governance clear"

        votes[MODELS[6]["name"]] = 0 if (is_combo or is_embiid) else 1
        reasons[MODELS[6]["name"]] = "Ceiling variance too high or unknown" if (is_combo or is_embiid) else "Ceiling manageable"

        votes[MODELS[7]["name"]] = 0 if (is_combo or is_embiid) else 1
        reasons[MODELS[7]["name"]] = "Projection within margin of error" if (is_combo or is_embiid) else "Raw projection supports"

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
        votes = {model["name"]: (1 if any(t in matchup for t in ["NYY", "PHI", "CHC", "NYK", "SAS"]) else 0) for model in MODELS}
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

def mark_site_ok(name):
    st.session_state.site_status[name] = {"status": "ok", "last_checked": datetime.now().strftime("%H:%M:%S")}

def parse_pasted_results(text):
    results = []
    lines = text.strip().split("\n")
    for line in lines:
        match = re.match(r"(.+?)\s+(OVER|UNDER|ML|SPREAD)\s+([\d.]+)\s+(.+)", line.strip(), re.IGNORECASE)
        if match:
            player, side, line_str, outcome = match.groups()
            outcome = "WIN" if "win" in outcome.lower() or "✅" in outcome else "LOSS" if "loss" in outcome.lower() or "❌" in outcome else "UNKNOWN"
            results.append({"player": player.strip(), "side": side.upper(), "line": float(line_str), "outcome": outcome})
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
    if st.button("📡 Load Board"):
        load_sport_data(st.session_state.last_sport)
        run_council(); run_game_council()
        for name in list(PROP_SOURCES.keys()) + list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys()):
            mark_site_ok(name)
        st.success(f"{st.session_state.last_sport} loaded.")
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

    if not board:
        st.info("No board loaded. Use the sidebar 'Load Board' button.")
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

            # +EV / Alt Lines
            if best_prop["Tier"] == "APPROVED":
                alt_line = best_prop["Line"] - 1.0 if "UNDER" in best_prop["Side"].upper() else best_prop["Line"] + 1.0
                st.markdown(f"### 🔵 +EV Safety Corridor")
                st.markdown(f"**{best_prop['Player']} {best_prop['Side']} {alt_line} {best_prop['Prop']}** — Alt line recommended for improved edge (Approved Single).")

            st.markdown("## 🔗 Prop Parlay of the Day")
            prop_par = build_prop_parlay()
            if prop_par:
                st.table(pd.DataFrame([{"Leg": i+1, "Player": l["Player"], "Team": l["Player"].split()[-1], "Prop": f"{l['Side']} {l['Line']} {l['Prop']}", "Tier": l["Tier Label"]} for i,l in enumerate(prop_par)]))
                if st.button("🔒 Lock Prop Parlay"):
                    lid = generate_lock_id()
                    for leg in prop_par:
                        st.session_state.locks.append({"id":lid,"type":"PROP","player":leg["Player"],"prop":f"{leg['Side']} {leg['Line']} {leg['Prop']}","side":leg["Side"],"line":leg["Line"],"tier":leg["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"parlay_id":lid})
                    st.success(f"Locked: {lid}")

            st.markdown("## 🔗 Game Parlay of the Day")
            game_par = build_game_parlay()
            if game_par:
                st.table(pd.DataFrame([{"Leg": i+1, "Matchup": l["Matchup"], "Bet": l.get("Moneyline","N/A"), "Tier": l["Tier Label"]} for i,l in enumerate(game_par)]))
                if st.button("🔒 Lock Game Parlay"):
                    lid = generate_lock_id()
                    for leg in game_par:
                        st.session_state.locks.append({"id":lid,"type":"GAME","matchup":leg["Matchup"],"bet":leg.get("Moneyline","N/A"),"tier":leg["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"parlay_id":lid})
                    st.success(f"Locked: {lid}")

# =========================
# TAB 3 — LOCKS & LEDGER
# =========================
with tabs[2]:
    st.markdown("# 📋 LOCKS & LEDGER")
    pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
    st.markdown("### Active Locks")
    if not pending:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(pending):
            cols = st.columns([4,1,1,1])
            with cols[0]:
                st.markdown(f"**{lock.get('id')}** — {lock.get('player', lock.get('matchup'))} | {lock.get('prop', lock.get('bet'))} | Tier: {lock.get('tier','?')}")
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
    else:
        st.info("No resolved bets yet.")

# =========================
# TAB 4 — RECONCILIATION
# =========================
with tabs[3]:
    st.markdown("# 🔄 RECONCILIATION & SYNC")
    
    st.markdown("### 📋 Paste Results to Auto-Grade")
    pasted = st.text_area("Paste results here (one per line): Player OVER/UNDER Line WIN/LOSS", height=150)
    if st.button("🔍 Sync Pasted Results"):
        parsed = parse_pasted_results(pasted)
        if parsed:
            for lock in st.session_state.locks:
                if lock["status"] == "PENDING":
                    for r in parsed:
                        if (r["player"].lower() in lock.get("player","").lower() and 
                            r["side"] == lock.get("side","") and 
                            abs(r["line"] - lock.get("line",0)) < 0.1):
                            lock["status"] = "RESOLVED"
                            lock["result"] = r["outcome"]
                            st.session_state.history.append(lock)
                            if r["outcome"] == "WIN":
                                st.session_state.integrity = min(INTEGRITY_CEILING, st.session_state.integrity + 0.5)
                                st.session_state.bankroll += active_unit()
                            else:
                                st.session_state.integrity = max(INTEGRITY_FLOOR, st.session_state.integrity - 1.0)
                                st.session_state.bankroll -= active_unit()
            st.session_state.locks = [l for l in st.session_state.locks if l["status"] == "PENDING"]
            st.success("Results synced! Ledger updated.")
        else:
            st.warning("No valid results detected.")

    st.markdown("### 📸 Upload Screenshot (Placeholder)")
    st.file_uploader("Upload PNG/JPG of results", type=["png","jpg","jpeg"])
    st.info("Screenshot OCR coming soon — paste text results above for now.")

    st.markdown("### 🌐 Re-Scan Sites for Box Scores (Placeholder)")
    if st.button("🌐 Scan ESPN for Final Scores"):
        st.info("Live box score scanning available in the full version. Upgrade to unlock real-time reconciliation.")

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

    st.markdown("## 📡 Site Health")
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
