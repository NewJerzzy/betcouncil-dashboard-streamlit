import streamlit as st
import pandas as pd
from datetime import date, datetime
import random

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="BetCouncil v3.1 OS",
    page_icon="🛡️",
    layout="wide",
)

st.markdown(
    """
    <style>
    body, .stApp, .main {
        background-color: #ffffff;
        color: #000000;
    }
    h1, h2, h3, h4 {
        color: #222222;
    }
    .gold-text {
        color: #d4a843;
        font-weight: 600;
    }
    .pill {
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        border: 1px solid #ccc;
        display: inline-block;
        margin-right: 6px;
    }
    .pill-green {
        background: rgba(34,197,94,0.12);
        border-color: rgba(34,197,94,0.6);
        color: #166534;
    }
    .pill-amber {
        background: rgba(245,158,11,0.12);
        border-color: rgba(245,158,11,0.6);
        color: #92400e;
    }
    .pill-red {
        background: rgba(239,68,68,0.12);
        border-color: rgba(239,68,68,0.6);
        color: #991b1b;
    }
    .tier-gold {
        color: #d4a843;
        font-weight: 700;
    }
    .tier-silver {
        color: #6b7280;
        font-weight: 600;
    }
    .tier-bronze {
        color: #b45309;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# CONSTANTS
# =========================
MODEL_WEIGHTS = {
    "deepseek": 0.18,
    "supreme": 0.18,
    "claude": 0.14,
    "copilot": 0.14,
    "gemini": 0.10,
    "perplexity": 0.10,
    "grok": 0.10,
    "base": 0.06,
}

TIER_THRESHOLDS = {
    "SOVEREIGN": 0.75,
    "ELITE": 0.65,
    "VALUE": 0.55,
}

DEFAULT_BANKROLL = 527.25
ACTIVE_FLOOR = 0.045
KELLY_FRACTION = 0.25

DATA_SOURCES = [
    "BettingPros",
    "RotoWire",
    "CBS Sports",
    "Covers.com",
    "DraftKings",
    "ESPN",
]

SPORTS = ["NBA", "NFL", "MLB", "NHL", "ALL"]

SEM_WINDOW_SIZE = 20  # number of recent bets to evaluate trend

# =========================
# SESSION STATE INIT
# =========================
if "scanner_status" not in st.session_state:
    st.session_state.scanner_status = {
        src: {"ok": False, "last": None, "error": None} for src in DATA_SOURCES
    }

if "board_data" not in st.session_state or not isinstance(st.session_state.board_data, dict):
    st.session_state.board_data = {
        "props": None,
        "injuries": None,
        "spreads": None,
        "series": None,
        "firewall_removed": 0,
        "model_verdicts": {},
    }
else:
    bd = st.session_state.board_data
    if "props" not in bd:
        bd["props"] = None
    if "injuries" not in bd:
        bd["injuries"] = None
    if "spreads" not in bd:
        bd["spreads"] = None
    if "series" not in bd:
        bd["series"] = None
    if "firewall_removed" not in bd:
        bd["firewall_removed"] = 0
    if "model_verdicts" not in bd:
        bd["model_verdicts"] = {}

if "games" not in st.session_state:
    st.session_state.games = None

if "locks" not in st.session_state:
    st.session_state.locks = []

if "history" not in st.session_state:
    st.session_state.history = []

if "sem_integrity" not in st.session_state:
    st.session_state.sem_integrity = 69

if "bankroll" not in st.session_state:
    st.session_state.bankroll = DEFAULT_BANKROLL

if "last_sport" not in st.session_state:
    st.session_state.last_sport = "NBA"

if "safe_corridor_active" not in st.session_state:
    st.session_state.safe_corridor_active = True

if "emergency_floor_pct" not in st.session_state:
    st.session_state.emergency_floor_pct = 12

if "sem_notes" not in st.session_state:
    st.session_state.sem_notes = ""

if "sem_mode" not in st.session_state:
    st.session_state.sem_mode = "NORMAL"  # NORMAL, DEFENSIVE, AGGRESSIVE

if "sem_profile" not in st.session_state:
    st.session_state.sem_profile = {
        "max_parlay_legs": 4,
        "allowed_tiers": ["SOVEREIGN", "ELITE", "VALUE"],
    }

if "sensor_score" not in st.session_state:
    st.session_state.sensor_score = 1.0

# =========================
# CORE UTILS
# =========================
def calculate_active_unit(bankroll):
    return round(bankroll * ACTIVE_FLOOR * KELLY_FRACTION, 2)

def calculate_weighted_consensus(model_scores):
    score = 0
    for model, weight in MODEL_WEIGHTS.items():
        score += model_scores.get(model, 0) * weight
    return round(score, 3)

def assign_tier(score):
    if score >= TIER_THRESHOLDS["SOVEREIGN"]:
        return "SOVEREIGN"
    if score >= TIER_THRESHOLDS["ELITE"]:
        return "ELITE"
    if score >= TIER_THRESHOLDS["VALUE"]:
        return "VALUE"
    return "PASS"

def tier_badge(tier):
    if tier == "SOVEREIGN":
        return "🟢 Sovereign Lock"
    if tier == "ELITE":
        return "🟡 Elite Edge"
    if tier == "VALUE":
        return "🥉 Value"
    return "—"

def add_lock(entry: dict):
    st.session_state.locks.append(entry)

def remove_lock(index: int):
    if 0 <= index < len(st.session_state.locks):
        st.session_state.locks.pop(index)

def clear_locks():
    st.session_state.locks = []

def move_to_history(lock, result, units, reason=""):
    lock_copy = lock.copy()
    lock_copy["status"] = "RESOLVED"
    lock_copy["result"] = result
    lock_copy["units"] = units
    lock_copy["reason"] = reason
    st.session_state.history.append(lock_copy)

# =========================
# SEM ENGINE
# =========================
def classify_loss_reason(lock):
    tier = lock.get("tier", "VALUE")
    if tier == "SOVEREIGN":
        return "Variance / High-Confidence Miss"
    if tier == "ELITE":
        return "Thin Edge / Market Drift"
    return "Low Edge / Noise"

def update_sem_profile():
    hist = st.session_state.history[-SEM_WINDOW_SIZE:]
    if not hist:
        st.session_state.sem_mode = "NORMAL"
        st.session_state.sem_profile = {
            "max_parlay_legs": 4,
            "allowed_tiers": ["SOVEREIGN", "ELITE", "VALUE"],
        }
        return

    wins = sum(1 for h in hist if h.get("result") == "WIN")
    losses = sum(1 for h in hist if h.get("result") == "LOSS")
    total = wins + losses
    if total == 0:
        winrate = 0.5
    else:
        winrate = wins / total

    if winrate >= 0.58:
        st.session_state.sem_mode = "AGGRESSIVE"
        st.session_state.sem_integrity = min(100, st.session_state.sem_integrity + 2)
        st.session_state.emergency_floor_pct = 10
        st.session_state.sem_profile = {
            "max_parlay_legs": 4,
            "allowed_tiers": ["SOVEREIGN", "ELITE", "VALUE"],
        }
    elif winrate <= 0.48:
        st.session_state.sem_mode = "DEFENSIVE"
        st.session_state.sem_integrity = max(40, st.session_state.sem_integrity - 3)
        st.session_state.emergency_floor_pct = 18
        st.session_state.sem_profile = {
            "max_parlay_legs": 2,
            "allowed_tiers": ["VALUE", "ELITE"],
        }
    else:
        st.session_state.sem_mode = "NORMAL"
        st.session_state.emergency_floor_pct = max(
            12, min(st.session_state.emergency_floor_pct, 15)
        )
        st.session_state.sem_profile = {
            "max_parlay_legs": 3,
            "allowed_tiers": ["SOVEREIGN", "ELITE", "VALUE"],
        }

    if st.session_state.sem_integrity < 55:
        st.session_state.safe_corridor_active = True
    else:
        st.session_state.safe_corridor_active = True

# =========================
# MOCK MODEL VERDICTS
# =========================
def generate_model_verdicts_for_prop(player, prop, side, line, sport):
    base = 0.7
    if "Wembanyama" in player or "Ohtani" in player or "Mahomes" in player or "McDavid" in player:
        base = 0.82
    elif "Maxey" in player or "Judge" in player or "Kelce" in player or "Matthews" in player:
        base = 0.78
    elif "UNDER" in side:
        base = 0.72

    scores = {
        "deepseek": base,
        "supreme": base - 0.02,
        "claude": base - 0.03,
        "copilot": base - 0.01,
        "gemini": base - 0.05,
        "perplexity": base - 0.06,
        "grok": base - 0.04,
        "base": base - 0.1,
    }

    verdicts = {}
    for model, s in scores.items():
        if s >= 0.75:
            verdicts[model] = "Elite Approve"
        elif s >= 0.65:
            verdicts[model] = "Approve"
        elif s >= 0.55:
            verdicts[model] = "Thin Edge"
        else:
            verdicts[model] = "Pass"

    wc = calculate_weighted_consensus(scores)
    tier = assign_tier(wc)
    return scores, verdicts, wc, tier

# =========================
# MULTI-SPORT MOCK DATA
# =========================
def mock_board_data_nba():
    props = pd.DataFrame(
        [
            ["Victor Wembanyama", "REBOUNDS", 12.5, "OVER"],
            ["Tyrese Maxey", "POINTS", 26.5, "OVER"],
            ["Karl-Anthony Towns", "REBOUNDS", 10.5, "OVER"],
            ["Jalen Brunson", "POINTS", 31.5, "OVER"],
            ["Anthony Edwards", "POINTS", 25.5, "UNDER"],
            ["Joel Embiid", "POINTS", 24.5, "UNDER"],
            ["Victor Wembanyama", "PTS+REB", 38.5, "OVER"],
            ["Tyrese Maxey", "PTS+AST", 32.5, "OVER"],
        ],
        columns=["Player", "Prop", "Line", "Side"],
    )

    injuries = pd.DataFrame(
        [
            ["NYK @ PHI", "Embiid (Probable - Grade 1 Ankle Sprain)"],
            ["MIN @ SAS", "Edwards (Cleared - Left Knee Bone Bruise)"],
        ],
        columns=["Game", "Status"],
    )

    spreads = pd.DataFrame(
        [
            ["NYK @ PHI", -2.5, "❌ Inactive", "Full evaluation"],
            ["MIN @ SAS", -4.5, "❌ Inactive", "Full evaluation"],
        ],
        columns=["Game", "Spread", "Advisory", "Effect"],
    )

    series = pd.DataFrame(
        [
            [
                "NYK @ PHI",
                "PHI must-win; Embiid restricted mobility",
                "[PLAYOFF RECENCY: +14% Usage Shift to Maxey]",
            ],
            [
                "MIN @ SAS",
                "Wemby Home Debut; Edwards mobility flag",
                "[PLAYOFF RECENCY: +15% Home Volume Adjustment — Wembanyama]",
            ],
        ],
        columns=["Series", "Game Context", "Trend Adjustment"],
    )

    return props, injuries, spreads, series

def mock_game_data_nba():
    games = pd.DataFrame(
        [
            ["NYK @ PHI", "PHI -2.5", "PHI ML -145", "O/U 214.5"],
            ["MIN @ SAS", "MIN -4.5", "MIN ML -180", "O/U 218.0"],
        ],
        columns=["Matchup", "Spread", "Moneyline", "Total"],
    )
    return games

def mock_board_data_mlb():
    props = pd.DataFrame(
        [
            ["Shohei Ohtani", "TOTAL BASES", 1.5, "OVER"],
            ["Aaron Judge", "HOME RUN", 0.5, "OVER"],
            ["Mookie Betts", "RUNS+RBI", 1.5, "OVER"],
            ["Spencer Strider", "STRIKEOUTS", 8.5, "OVER"],
            ["Corbin Burnes", "STRIKEOUTS", 7.5, "UNDER"],
        ],
        columns=["Player", "Prop", "Line", "Side"],
    )

    injuries = pd.DataFrame(
        [
            ["LAD @ NYY", "Judge (Probable - Hand Contusion)"],
            ["ATL @ MIL", "Strider (Cleared - Pitch Count Watch)"],
        ],
        columns=["Game", "Status"],
    )

    spreads = pd.DataFrame(
        [
            ["LAD @ NYY", -1.5, "❌ Inactive", "Full evaluation"],
            ["ATL @ MIL", -1.5, "❌ Inactive", "Full evaluation"],
        ],
        columns=["Game", "Spread", "Advisory", "Effect"],
    )

    series = pd.DataFrame(
        [
            [
                "LAD @ NYY",
                "Interleague marquee; bullpen fatigue edge LAD",
                "[SERIES CONTEXT: +10% Power Shift to Ohtani/Judge]",
            ],
            [
                "ATL @ MIL",
                "Pitching duel; low total environment",
                "[SERIES CONTEXT: -8% Run Environment Adjustment]",
            ],
        ],
        columns=["Series", "Game Context", "Trend Adjustment"],
    )

    return props, injuries, spreads, series

def mock_game_data_mlb():
    games = pd.DataFrame(
        [
            ["LAD @ NYY", "LAD -1.5", "LAD ML -135", "O/U 8.5"],
            ["ATL @ MIL", "ATL -1.5", "ATL ML -140", "O/U 7.5"],
        ],
        columns=["Matchup", "Spread", "Moneyline", "Total"],
    )
    return games

def mock_board_data_nfl():
    props = pd.DataFrame(
        [
            ["Patrick Mahomes", "PASSING YARDS", 285.5, "OVER"],
            ["Travis Kelce", "RECEPTIONS", 6.5, "OVER"],
            ["Christian McCaffrey", "RUSH+REC YARDS", 104.5, "OVER"],
            ["Justin Jefferson", "RECEIVING YARDS", 92.5, "UNDER"],
        ],
        columns=["Player", "Prop", "Line", "Side"],
    )

    injuries = pd.DataFrame(
        [
            ["KC @ SF", "Kelce (Probable - Knee Soreness)"],
            ["MIN @ GB", "Jefferson (Questionable - Hamstring)"],
        ],
        columns=["Game", "Status"],
    )

    spreads = pd.DataFrame(
        [
            ["KC @ SF", -2.5, "❌ Inactive", "Full evaluation"],
            ["MIN @ GB", 3.5, "❌ Inactive", "Full evaluation"],
        ],
        columns=["Game", "Spread", "Advisory", "Effect"],
    )

    series = pd.DataFrame(
        [
            [
                "KC @ SF",
                "Super Bowl rematch; high leverage environment",
                "[PLAYOFF CONTEXT: +12% Volume to Mahomes/Kelce]",
            ],
            [
                "MIN @ GB",
                "Divisional game; weather risk",
                "[ENVIRONMENT: -10% Passing Volume Adjustment]",
            ],
        ],
        columns=["Series", "Game Context", "Trend Adjustment"],
    )

    return props, injuries, spreads, series

def mock_game_data_nfl():
    games = pd.DataFrame(
        [
            ["KC @ SF", "KC -2.5", "KC ML -135", "O/U 51.5"],
            ["MIN @ GB", "GB -3.5", "GB ML -160", "O/U 44.0"],
        ],
        columns=["Matchup", "Spread", "Moneyline", "Total"],
    )
    return games

def mock_board_data_nhl():
    props = pd.DataFrame(
        [
            ["Connor McDavid", "POINTS", 1.5, "OVER"],
            ["Leon Draisaitl", "SHOTS ON GOAL", 3.5, "OVER"],
            ["Auston Matthews", "GOALS", 0.5, "OVER"],
            ["Igor Shesterkin", "SAVES", 29.5, "OVER"],
        ],
        columns=["Player", "Prop", "Line", "Side"],
    )

    injuries = pd.DataFrame(
        [
            ["EDM @ TOR", "Matthews (Probable - Wrist)"],
            ["NYR @ BOS", "Shesterkin (Confirmed Starter)"],
        ],
        columns=["Game", "Status"],
    )

    spreads = pd.DataFrame(
        [
            ["EDM @ TOR", -1.5, "❌ Inactive", "Full evaluation"],
            ["NYR @ BOS", 1.5, "❌ Inactive", "Full evaluation"],
        ],
        columns=["Game", "Spread", "Advisory", "Effect"],
    )

    series = pd.DataFrame(
        [
            [
                "EDM @ TOR",
                "High-event environment; elite offensive talent",
                "[PACE: +15% Shot Volume Adjustment]",
            ],
            [
                "NYR @ BOS",
                "Defensive grind; goalie duel",
                "[PACE: -10% Goal Expectation]",
            ],
        ],
        columns=["Series", "Game Context", "Trend Adjustment"],
    )

    return props, injuries, spreads, series

def mock_game_data_nhl():
    games = pd.DataFrame(
        [
            ["EDM @ TOR", "TOR -1.5", "TOR ML -130", "O/U 6.5"],
            ["NYR @ BOS", "BOS -1.5", "BOS ML -150", "O/U 5.5"],
        ],
        columns=["Matchup", "Spread", "Moneyline", "Total"],
    )
    return games

def mock_board_data_all():
    return mock_board_data_nba()

def mock_game_data_all():
    return mock_game_data_nba()

def mock_board_data(sport: str):
    if sport == "NBA":
        return mock_board_data_nba()
    if sport == "MLB":
        return mock_board_data_mlb()
    if sport == "NFL":
        return mock_board_data_nfl()
    if sport == "NHL":
        return mock_board_data_nhl()
    return mock_board_data_all()

def mock_game_data(sport: str):
    if sport == "NBA":
        return mock_game_data_nba()
    if sport == "MLB":
        return mock_game_data_mlb()
    if sport == "NFL":
        return mock_game_data_nfl()
    if sport == "NHL":
        return mock_game_data_nhl()
    return mock_game_data_all()

# =========================
# FIREWALL / FILTERS
# =========================
def apply_firewall(props_df, injuries_df, spreads_df, sport):
    removed = 0
    keep_rows = []
    for idx, row in props_df.iterrows():
        player = row["Player"]
        prop = row["Prop"]
        side = row["Side"]

        injury_flag = any(player.split()[0] in s for s in injuries_df["Status"].tolist())
        blowout_flag = False
        for _, srow in spreads_df.iterrows():
            if abs(srow["Spread"]) >= 10 and sport in ["NBA", "NFL"]:
                blowout_flag = True

        volatility_flag = "PTS+REB" in prop or "PTS+AST" in prop

        if injury_flag and volatility_flag:
            removed += 1
            continue
        keep_rows.append(idx)

    filtered = props_df.loc[keep_rows].reset_index(drop=True)
    return filtered, removed

# =========================
# MODEL VERDICTS + CONSENSUS
# =========================
def enrich_props_with_models(props_df, sport):
    model_verdicts = {}
    scores = []
    tiers = []
    for idx, row in props_df.iterrows():
        player = row["Player"]
        prop = row["Prop"]
        side = row["Side"]
        line = row["Line"]
        mscores, verdicts, wc, tier = generate_model_verdicts_for_prop(
            player, prop, side, line, sport
        )
        model_verdicts[idx] = verdicts
        scores.append(wc)
        tiers.append(tier)
    props_df["Weighted Score"] = scores
    props_df["Tier"] = tiers
    return props_df, model_verdicts

def enrich_games_with_models(games_df, sport):
    scores = []
    tiers = []
    for _, row in games_df.iterrows():
        matchup = row["Matchup"]
        base = 0.7
        if any(k in matchup for k in ["PHI", "MIN", "LAD", "ATL", "KC", "GB", "TOR", "BOS"]):
            base = 0.76
        mscores = {
            "deepseek": base,
            "supreme": base - 0.02,
            "claude": base - 0.03,
            "copilot": base - 0.01,
            "gemini": base - 0.05,
            "perplexity": base - 0.06,
            "grok": base - 0.04,
            "base": base - 0.1,
        }
        wc = calculate_weighted_consensus(mscores)
        tier = assign_tier(wc)
        scores.append(wc)
        tiers.append(tier)
    games_df["Weighted Score"] = scores
    games_df["Tier"] = tiers
    return games_df

# =========================
# SCANNER / PARSING MOCKS
# =========================
def scan_source(name: str, sport: str):
    st.session_state.scanner_status[name]["ok"] = True
    st.session_state.scanner_status[name]["last"] = datetime.now().strftime("%H:%M:%S")
    st.session_state.scanner_status[name]["error"] = None

def scan_all_sources(sport: str):
    for src in DATA_SOURCES:
        scan_source(src, sport)

    props, injuries, spreads, series = mock_board_data(sport)
    props_filtered, removed = apply_firewall(props, injuries, spreads, sport)
    props_enriched, model_verdicts = enrich_props_with_models(props_filtered, sport)
    games = mock_game_data(sport)
    games = enrich_games_with_models(games, sport)

    st.session_state.board_data = {
        "props": props_enriched,
        "injuries": injuries,
        "spreads": spreads,
        "series": series,
        "firewall_removed": removed,
        "model_verdicts": model_verdicts,
    }
    st.session_state.games = games
    st.session_state.last_sport = sport

def parse_manual_text(text: str, sport: str):
    scan_all_sources(sport)

def parse_screenshot(image, sport: str):
    scan_all_sources(sport)

# =========================
# MARKET DYNAMICS (MOCK)
# =========================
def get_market_dynamics(sport):
    rlm_detected = True
    contrarian_flag = True
    regime = "STABLE"
    public_on = "Overs"
    council_on = "Unders / Pass"
    return {
        "rlm": rlm_detected,
        "contrarian": contrarian_flag,
        "regime": regime,
        "public_on": public_on,
        "council_on": council_on,
    }

# =========================
# SEM / RECONCILIATION
# =========================
def mock_box_score_result(lock):
    tier = lock.get("tier", "VALUE")
    if tier == "SOVEREIGN":
        p = 0.65
    elif tier == "ELITE":
        p = 0.57
    else:
        p = 0.50
    hit = random.random() < p
    return "WIN" if hit else "LOSS"

def reconcile_locks(active_unit):
    for lock in list(st.session_state.locks):
        if lock["status"] == "PENDING":
            result = mock_box_score_result(lock)
            units = active_unit if result == "WIN" else -active_unit
            if result == "WIN":
                reason = "Model Edge / CLV Realized"
            else:
                reason = classify_loss_reason(lock)

            move_to_history(lock, result, units, reason)

            if result == "WIN":
                st.session_state.sem_integrity = min(100, st.session_state.sem_integrity + 1)
            else:
                st.session_state.sem_integrity = max(40, st.session_state.sem_integrity - 2)

            st.session_state.bankroll += units
            st.session_state.locks.remove(lock)

    update_sem_profile()

# =========================
# PARLAY ENGINE
# =========================
def build_parlay_from_props(props_df, max_legs=4):
    legs = []
    used_players = set()
    used_games = set()

    for _, row in props_df.sort_values("Weighted Score", ascending=False).iterrows():
        player = row["Player"]
        prop = row["Prop"]
        game_key = player.split()[0]

        if player in used_players or game_key in used_games:
            continue

        if row["Tier"] not in st.session_state.sem_profile["allowed_tiers"]:
            continue

        legs.append(row)
        used_players.add(player)
        used_games.add(game_key)

        if len(legs) >= max_legs:
            break

    return pd.DataFrame(legs)

# =========================
# SIDEBAR – GOVERNANCE PANEL
# =========================
with st.sidebar:
    st.markdown("### 🛡️ BetCouncil v3.1 OS")
    st.markdown('<span class="gold-text">Sovereign Governance Panel</span>', unsafe_allow_html=True)

    st.session_state.bankroll = st.number_input(
        "Bankroll ($)", value=float(st.session_state.bankroll), step=10.0
    )
    active_unit = calculate_active_unit(st.session_state.bankroll)

    st.metric("Active Floor", f"{ACTIVE_FLOOR*100:.1f}%")
    st.metric("Kelly Fraction", f"{KELLY_FRACTION:.2f}")
    st.metric("Active Unit", f"${active_unit:.2f}")

    st.markdown("---")
    integrity = st.slider("Integrity Score (SEM)", 40, 100, st.session_state.sem_integrity)
    st.session_state.sem_integrity = integrity

    emergency_floor = st.slider(
        "Emergency Floor (%)", 5, 25, st.session_state.emergency_floor_pct
    )
    st.session_state.emergency_floor_pct = emergency_floor

    st.markdown("---")
    st.checkbox("Safe Corridor Mode", value=True, key="safe_corridor_active")
    st.markdown(f"**SEM Mode:** {st.session_state.sem_mode}")

# =========================
# MAIN TABS (ORDERED)
# =========================
tab_analysis, tab_summary, tab_locks, tab_tools = st.tabs(
    ["Analysis", "Summary Report", "Locks & Ledger", "Tools & SEM"]
)

# =========================
# ANALYSIS TAB
# =========================
with tab_analysis:
    st.markdown("## 📊 THE BOARD OF 8 — CLARITY MODEL OUTPUT")

    sport = st.selectbox("Select Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport))

    st.markdown(
        "**Data Source:** BettingPros + RotoWire + CBS Sports + Covers.com + DraftKings + ESPN"
    )
    st.markdown(
        f"**Sport:** {sport} — {date.today().strftime('%b %d, %Y')}  \n"
        f"Status: 🛡️ SAFE CORRIDOR MODE ACTIVE | 🚨 EMERGENCY FLOOR ACTIVE ({st.session_state.emergency_floor_pct}%)"
    )

    st.markdown("---")

    col_scan, col_manual, col_screen = st.columns(3)
    with col_scan:
        if st.button("🔍 Scan from Web (All Sources)"):
            scan_all_sources(sport)
            st.success(f"Scan complete for {sport} (mock pipeline).")
    with col_manual:
        st.write("Manual Data Paste:")
    with col_screen:
        st.write("Screenshot OCR:")

    manual_text = st.text_area("Paste raw board / props / injuries here (optional):", height=120)
    if st.button("Use Pasted Data"):
        if manual_text.strip():
            parse_manual_text(manual_text, sport)
            st.success(f"Manual data ingested for {sport} (mock parser).")
        else:
            st.warning("No text detected.")

    screenshot = st.file_uploader("Upload screenshot (optional):", type=["png", "jpg", "jpeg"])
    if st.button("Use Screenshot OCR"):
        if screenshot is not None:
            parse_screenshot(screenshot, sport)
            st.success(f"Screenshot processed for {sport} (mock OCR).")
        else:
            st.warning("No screenshot uploaded.")

    st.markdown("---")

    board = st.session_state.board_data
    if board is None or board.get("props") is None:
        st.info("No board data loaded yet. Run a scan, paste data, or upload a screenshot.")
    else:
        props = board["props"]
        injuries = board["injuries"]
        spreads = board["spreads"]
        series = board["series"]
        removed = board.get("firewall_removed", 0)

        st.markdown(
            f"🔒 **Validation Firewall:** PASSED "
            f"({len(spreads)} games, {len(injuries)} matchups verified, {removed} props removed)"
        )

        st.markdown("### 🚨 PRE-FILTER: LINEUP & INJURY VERIFICATION")
        st.table(injuries)

        st.markdown("### 🚨 BLOWOUT / GAME SCRIPT ADVISORY")
        st.table(spreads)

        st.markdown("### 📊 SERIES / CONTEXT: APPLIED")
        st.table(series)

        st.markdown("### 📊 PROPS SURVIVED PRE-FILTER")
        st.table(props[["Player", "Prop", "Line", "Side"]])

        st.markdown("### 🏀 GAME LINES — ML / SPREAD / TOTAL")
        games = st.session_state.games
        if games is not None:
            st.table(games[["Matchup", "Moneyline", "Spread", "Total"]])

        st.markdown("### 🗳️ MODEL-BY-MODEL VERDICTS (PER PROP)")
        mv = board.get("model_verdicts", {})
        for idx, row in props.iterrows():
            st.markdown(f"**{row['Player']} — {row['Prop']} {row['Side']} {row['Line']}**")
            verdicts = mv.get(idx, {})
            cols = st.columns(4)
            models_list = list(MODEL_WEIGHTS.keys())
            for i, model in enumerate(models_list):
                with cols[i % 4]:
                    st.caption(f"{model.upper()}: {verdicts.get(model, '—')}")

        st.markdown("### 🟦 COUNCIL CONSENSUS SUMMARY")
        consensus = props[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier"]].copy()
        consensus["Tier Label"] = consensus["Tier"].apply(tier_badge)
        st.table(consensus)

        st.markdown("**Strongest Multi-Model Alignments:**")
        top_consensus = consensus.sort_values("Weighted Score", ascending=False).head(5)
        st.table(
            top_consensus[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier Label"]]
        )

        st.markdown("**Excluded:** High-variance combo props, injury-uncertain edges, thin model density (mock).")

        st.markdown("### 🔐 Lock Props from This Board")
        for idx, row in props.iterrows():
            if row["Tier"] not in st.session_state.sem_profile["allowed_tiers"]:
                continue
            c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 2])
            with c1:
                st.write(f"**{row['Player']}** — {row['Prop']}")
            with c2:
                st.write(f"{row['Side']} {row['Line']}")
            with c3:
                st.write(row["Tier"])
            with c4:
                st.write(f"{row['Weighted Score']:.3f}")
            with c5:
                disabled = st.session_state.sem_integrity < 50
                if st.button(
                    "LOCK THIS PROP",
                    key=f"lock_prop_{sport}_{idx}",
                    disabled=disabled,
                ):
                    add_lock(
                        {
                            "type": "PROP",
                            "sport": sport,
                            "player": row["Player"],
                            "prop": row["Prop"],
                            "side": row["Side"],
                            "line": row["Line"],
                            "tier": row["Tier"],
                            "score": row["Weighted Score"],
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "PENDING",
                            "result": None,
                            "is_parlay_leg": False,
                        }
                    )
                    st.success(f"Locked: {row['Player']} {row['Prop']} {row['Side']} {row['Line']}")

        if games is not None:
            st.markdown("### 🔐 Lock Games from This Board")
            for idx, row in games.iterrows():
                c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 2])
                with c1:
                    st.write(f"**{row['Matchup']}**")
                with c2:
                    st.write(f"{row['Moneyline']} | {row['Spread']} | {row['Total']}")
                with c3:
                    st.write(row["Tier"])
                with c4:
                    st.write(f"{row['Weighted Score']:.3f}")
                with c5:
                    disabled = st.session_state.sem_integrity < 50
                    if st.button(
                        "LOCK THIS GAME",
                        key=f"lock_game_{sport}_{idx}",
                        disabled=disabled,
                    ):
                        add_lock(
                            {
                                "type": "GAME",
                                "sport": sport,
                                "matchup": row["Matchup"],
                                "moneyline": row["Moneyline"],
                                "spread": row["Spread"],
                                "total": row["Total"],
                                "tier": row["Tier"],
                                "score": row["Weighted Score"],
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "status": "PENDING",
                                "result": None,
                                "is_parlay_leg": False,
                            }
                        )
                        st.success(f"Locked Game: {row['Matchup']}")

# =========================
# SUMMARY REPORT TAB
# =========================
with tab_summary:
    st.markdown("## 🧾 THE BOARD OF 8 — CLARITY MODEL OUTPUT (Summary Report)")

    board = st.session_state.board_data
    games = st.session_state.games
    if board is None or board.get("props") is None or games is None:
        st.info("No board data loaded yet. Load data from Analysis tab first.")
    else:
        props = board["props"]
        injuries = board["injuries"]
        spreads = board["spreads"]
        series = board["series"]
        removed = board.get("firewall_removed", 0)

        st.markdown(
            "**Data Source:** BettingPros + RotoWire + CBS Sports + Covers.com + DraftKings + ESPN"
        )
        st.markdown(
            f"**Sport:** {st.session_state.last_sport} — {date.today().strftime('%b %d, %Y')}  \n"
            f"Status: 🛡️ SAFE CORRIDOR MODE ACTIVE | 🚨 EMERGENCY FLOOR ACTIVE ({st.session_state.emergency_floor_pct}%)"
        )

        st.markdown(
            f"🔒 **Validation Firewall:** PASSED "
            f"({len(spreads)} games, {len(injuries)} matchups verified, {removed} props removed)."
        )

        st.markdown("### 🚨 PRE-FILTER: LINEUP & INJURY VERIFICATION")
        st.table(injuries)

        st.markdown("### 🚨 BLOWOUT / GAME SCRIPT ADVISORY")
        st.table(spreads)

        st.markdown("### 📊 SERIES / CONTEXT: APPLIED")
        st.table(series)

        st.markdown("### 📊 PROPS SURVIVED PRE-FILTER")
        st.table(props[["Player", "Prop", "Line", "Side"]])

        st.markdown("### 🗳️ MODEL-BY-MODEL VERDICTS (High Level)")
        st.markdown(
            """
- v5.3 DeepSeek — Outlier Suppression: Approves core edges; passes high-variance props.  
- v6.5 Gemini — Environmental Physics: Adjusts for environment; passes unstable conditions.  
- v25.4 Claude — Motivation / Ref Bias: Elevates must-win / narrative spots.  
- v4.0 Copilot — Deterministic Floor Engine: Approves only strong floors.  
- v4.1 Perplexity — Volatility Mapping: Flags sigma-heavy props.  
- v6.0 Supreme — Governance / CLV Integrity: Sovereign only with CLV + density.  
- v22.6 Grok — Ceiling Variance Engine: Approves high-ceiling edges.  
- Base Model — Raw Projection Layer: Baseline only.
"""
        )

        st.markdown("### 🟦 COUNCIL CONSENSUS SUMMARY")
        consensus = props[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier"]].copy()
        consensus["Tier Label"] = consensus["Tier"].apply(tier_badge)
        st.table(consensus)

        st.markdown("**Strongest Multi-Model Alignments:**")
        top_consensus = consensus.sort_values("Weighted Score", ascending=False).head(5)
        st.table(
            top_consensus[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier Label"]]
        )

        st.markdown("**Excluded:** Volatility traps, thin-model-density combo props, injury-uncertain edges (mock).")

        st.markdown("### 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        md = get_market_dynamics(st.session_state.last_sport)
        st.markdown(
            f"- RLM Status: {'DETECTED' if md['rlm'] else 'NONE'} — Example: key Under moving against public sentiment.  \n"
            f"- Contrarian Flag: {'ACTIVE' if md['contrarian'] else 'INACTIVE'} — Public on {md['public_on']}; Council on {md['council_on']}.  \n"
            f"- Regime Type: {md['regime']} (mock).  \n"
        )

        st.markdown("### 🛡️ SEM STATUS")
        st.markdown(
            f"- Integrity Score: {st.session_state.sem_integrity}  \n"
            f"- SEM Mode: {st.session_state.sem_mode}  \n"
            f"- Safe Corridor: {'ACTIVE' if st.session_state.safe_corridor_active else 'INACTIVE'}  \n"
            f"- Emergency Floor: ACTIVE ({st.session_state.emergency_floor_pct}%)  \n"
            "- Blowout Advisory: INACTIVE (mock)  \n"
            f"- Active Locks: {len([l for l in st.session_state.locks if l['status']=='PENDING'])}  \n"
            f"- Sensor Health: {st.session_state.sensor_score*100:.0f}%"
        )

        st.markdown("### 🔒 BETCOUNCIL LOCK OF THE DAY (PROP)")
        top_prop = props.sort_values("Weighted Score", ascending=False).iloc[0]
        st.table(
            pd.DataFrame(
                [
                    {
                        "Type": "Prop",
                        "Pick": f"{top_prop['Player']} {top_prop['Prop']} {top_prop['Side']}",
                        "Line": top_prop["Line"],
                        "Tier": tier_badge(top_prop["Tier"]),
                        "Weighted Score": top_prop["Weighted Score"],
                    }
                ]
            )
        )

        st.markdown("### 🏆 BETCOUNCIL GAME LOCK OF THE DAY")
        top_game = games.sort_values("Weighted Score", ascending=False).iloc[0]
        st.table(
            pd.DataFrame(
                [
                    {
                        "Matchup": top_game["Matchup"],
                        "Moneyline": top_game["Moneyline"],
                        "Spread": top_game["Spread"],
                        "Total": top_game["Total"],
                        "Tier": tier_badge(top_game["Tier"]),
                        "Weighted Score": top_game["Weighted Score"],
                    }
                ]
            )
        )

        st.markdown("### 🔗 BETCOUNCIL PARLAY OF THE DAY — PROPS")
        parlay_df = build_parlay_from_props(
            props, max_legs=st.session_state.sem_profile["max_parlay_legs"]
        )
        if parlay_df.empty:
            st.info("No eligible props for parlay (correlation / SEM filters).")
        else:
            parlay_rows = []
            for i, (_, row) in enumerate(parlay_df.iterrows(), start=1):
                parlay_rows.append(
                    {
                        "Leg": i,
                        "Player": row["Player"],
                        "Prop": row["Prop"],
                        "Line": row["Line"],
                        "Side": row["Side"],
                        "Tier": tier_badge(row["Tier"]),
                    }
                )
            st.table(pd.DataFrame(parlay_rows))
            st.caption(
                f"{len(parlay_rows)}-leg configuration with SEM-governed exposure. "
                f"Total unit exposure: ${active_unit:.2f} (Floor-adjusted)."
            )

# =========================
# LOCKS & LEDGER TAB
# =========================
with tab_locks:
    st.markdown("## 🔒 BETCOUNCIL LOCKS, PARLAY & LEDGER")

    board = st.session_state.board_data
    games = st.session_state.games
    if board is None or board.get("props") is None or games is None:
        st.info("No board data available. Load data from Analysis tab first.")
    else:
        df_props = board["props"].copy()
        df_games = games.copy()

        st.markdown("### 🔥 Prop Lock of the Day (Model)")
        lock_prop = df_props.sort_values("Weighted Score", ascending=False).iloc[0]
        st.table(
            pd.DataFrame(
                [
                    {
                        "Type": "Prop",
                        "Pick": f"{lock_prop['Player']} {lock_prop['Prop']} {lock_prop['Side']}",
                        "Line": lock_prop["Line"],
                        "Tier": tier_badge(lock_prop["Tier"]),
                        "Weighted Score": lock_prop["Weighted Score"],
                    }
                ]
            )
        )

        st.markdown("### 🏆 Game Lock of the Day (Model)")
        lock_game = df_games.sort_values("Weighted Score", ascending=False).iloc[0]
        st.table(
            pd.DataFrame(
                [
                    {
                        "Matchup": lock_game["Matchup"],
                        "Moneyline": lock_game["Moneyline"],
                        "Spread": lock_game["Spread"],
                        "Total": lock_game["Total"],
                        "Tier": tier_badge(lock_game["Tier"]),
                        "Weighted Score": lock_game["Weighted Score"],
                    }
                ]
            )
        )

        st.markdown("### 🔗 Parlay of the Day (Props)")
        parlay_df = build_parlay_from_props(
            df_props, max_legs=st.session_state.sem_profile["max_parlay_legs"]
        )
        if parlay_df.empty:
            st.info("No eligible props for parlay (correlation / SEM filters).")
        else:
            parlay_rows = []
            for i, (_, row) in enumerate(parlay_df.iterrows(), start=1):
                parlay_rows.append(
                    {
                        "Leg": i,
                        "Player": row["Player"],
                        "Prop": row["Prop"],
                        "Line": row["Line"],
                        "Side": row["Side"],
                        "Tier": tier_badge(row["Tier"]),
                    }
                )
            st.table(pd.DataFrame(parlay_rows))

        st.markdown("### 📊 Top 5 Props by Consensus")
        top_props = df_props.sort_values("Weighted Score", ascending=False).head(5)
        st.table(
            top_props[
                ["Player", "Prop", "Side", "Line", "Weighted Score", "Tier"]
            ].rename(columns={"Tier": "Tier Raw"})
        )

        st.markdown("### 📊 Top 5 Games by Consensus")
        top_games = df_games.sort_values("Weighted Score", ascending=False).head(5)
        st.table(
            top_games[
                ["Matchup", "Moneyline", "Spread", "Total", "Weighted Score", "Tier"]
            ].rename(columns={"Tier": "Tier Raw"})
        )

        st.markdown("---")
        st.markdown("### Your Locked Bets (Ledger)")

        if not st.session_state.locks:
            st.info("No locked bets yet. Lock props or games from the Analysis tab.")
        else:
            lock_rows = []
            for i, l in enumerate(st.session_state.locks):
                if l["type"] == "PROP":
                    lock_rows.append(
                        {
                            "#": i + 1,
                            "Type": "PROP",
                            "Sport": l["sport"],
                            "Player": l["player"],
                            "Prop": l["prop"],
                            "Side": l["side"],
                            "Line": l["line"],
                            "Tier": l["tier"],
                            "Score": l["score"],
                            "Status": l["status"],
                            "Result": l["result"],
                            "Time": l["timestamp"],
                        }
                    )
                else:
                    lock_rows.append(
                        {
                            "#": i + 1,
                            "Type": "GAME",
                            "Sport": l["sport"],
                            "Matchup": l["matchup"],
                            "Moneyline": l["moneyline"],
                            "Spread": l["spread"],
                            "Total": l["total"],
                            "Tier": l["tier"],
                            "Score": l["score"],
                            "Status": l["status"],
                            "Result": l["result"],
                            "Time": l["timestamp"],
                        }
                    )
            st.table(pd.DataFrame(lock_rows))

            cols = st.columns(3)
            with cols[0]:
                if st.button("Clear All Locks"):
                    clear_locks()
                    st.success("All locks cleared.")
            with cols[1]:
                if st.session_state.locks:
                    remove_index = st.number_input(
                        "Remove Lock #", min_value=1, max_value=len(st.session_state.locks), value=1
                    )
                    if st.button("Remove Selected Lock"):
                        remove_lock(remove_index - 1)
                        st.success("Lock removed.")
            with cols[2]:
                if st.button("Reconcile Now (Mock Box Scores)"):
                    reconcile_locks(active_unit)
                    st.success("Reconciliation complete (mock).")

        st.markdown("---")
        st.markdown("### 📜 Resolved Bets (History)")
        if not st.session_state.history:
            st.info("No resolved bets yet.")
        else:
            hist_rows = []
            for h in st.session_state.history:
                if h["type"] == "PROP":
                    hist_rows.append(
                        {
                            "Type": "PROP",
                            "Sport": h["sport"],
                            "Player": h["player"],
                            "Prop": h["prop"],
                            "Side": h["side"],
                            "Line": h["line"],
                            "Tier": h["tier"],
                            "Score": h["score"],
                            "Result": h["result"],
                            "Units": h["units"],
                            "Reason": h.get("reason", ""),
                            "Time": h["timestamp"],
                        }
                    )
                else:
                    hist_rows.append(
                        {
                            "Type": "GAME",
                            "Sport": h["sport"],
                            "Matchup": h["matchup"],
                            "Moneyline": h["moneyline"],
                            "Spread": h["spread"],
                            "Total": h["total"],
                            "Tier": h["tier"],
                            "Score": h["score"],
                            "Result": h["result"],
                            "Units": h["units"],
                            "Reason": h.get("reason", ""),
                            "Time": h["timestamp"],
                        }
                    )
            st.table(pd.DataFrame(hist_rows))

# =========================
# TOOLS & SEM TAB
# =========================
with tab_tools:
    st.markdown("## 🧪 Tools, Scanner Status & SEM Engine")

    st.markdown("### Scanner Status (Per Source)")
    status_rows = []
    for src in DATA_SOURCES:
        s = st.session_state.scanner_status[src]
        dot = "🟢" if s["ok"] else "🔴"
        last = s["last"] or "—"
        err = s["error"] or ""
        status_rows.append(
            {"Source": src, "Status": dot, "Last Scan": last, "Error": err}
        )
    st.table(pd.DataFrame(status_rows))

    if st.button("Scan All (Tools Tab)"):
        scan_all_sources(st.session_state.last_sport)
        st.success(f"Scan complete for {st.session_state.last_sport} (mock).")

    st.markdown("---")
    st.markdown("### 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
    md = get_market_dynamics(st.session_state.last_sport)
    st.markdown(
        f"- RLM Status: {'DETECTED' if md['rlm'] else 'NONE'} — Example: key Under moving against public sentiment.  \n"
        f"- Contrarian Flag: {'ACTIVE' if md['contrarian'] else 'INACTIVE'} — Public on {md['public_on']}; Council on {md['council_on']}.  \n"
        f"- Regime Type: {md['regime']} (mock).  \n"
    )

    st.markdown("---")
    st.markdown("### 11-Sensor Checklist")
    sensors = [
        "Lineup Confirmed",
        "Minutes / Usage Floor Verified",
        "Blowout / Game Script Risk Evaluated",
        "Pace / Possessions / Run Environment",
        "Matchup Coverage & Scheme",
        "Referee / Umpire / Whistle Profile",
        "Travel & Rest Differential",
        "CLV vs Open/Close",
        "Public vs Sharp Money Split",
        "Historical Sigma / Volatility",
        "Correlation with Other Board Props",
    ]
    sensor_flags = []
    for i, s in enumerate(sensors):
        flag = st.checkbox(s, key=f"sensor_{i}")
        sensor_flags.append(flag)
    if sensor_flags:
        st.session_state.sensor_score = sum(sensor_flags) / len(sensor_flags)
    else:
        st.session_state.sensor_score = 1.0

    st.markdown("---")
    st.markdown("### 🛡️ SEM STATUS")
    st.markdown(
        f"- Integrity Score: {st.session_state.sem_integrity}  \n"
        f"- SEM Mode: {st.session_state.sem_mode}  \n"
        f"- Safe Corridor: {'ACTIVE' if st.session_state.safe_corridor_active else 'INACTIVE'}  \n"
        f"- Emergency Floor: ACTIVE ({st.session_state.emergency_floor_pct}%)  \n"
        "- Blowout Advisory: INACTIVE (mock)  \n"
        f"- Active Locks: {len([l for l in st.session_state.locks if l['status']=='PENDING'])}  \n"
        f"- Sensor Health: {st.session_state.sensor_score*100:.0f}%"
    )

    st.markdown("---")
    st.markdown("### SEM Learning Log")
    st.session_state.sem_notes = st.text_area(
        "SEM Notes (e.g., 'Sovereign pick lost due to foul trouble, not model error.')",
        value=st.session_state.sem_notes,
        height=150,
    )
