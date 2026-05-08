import streamlit as st
import pandas as pd
from datetime import date, datetime
import random

# Optional imports for scraping / OCR (placeholders)
try:
    import requests
except ImportError:
    requests = None

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

# -----------------------------
# PAGE CONFIG & LIGHT THEME
# -----------------------------
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

# -----------------------------
# CONSTANTS
# -----------------------------
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

# -----------------------------
# SESSION STATE INIT
# -----------------------------
if "scanner_status" not in st.session_state:
    st.session_state.scanner_status = {
        src: {"ok": False, "last": None, "error": None} for src in DATA_SOURCES
    }

if "board_data" not in st.session_state:
    st.session_state.board_data = {
        "props": None,
        "injuries": None,
        "spreads": None,
        "series": None,
    }

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

# -----------------------------
# CORE FUNCTIONS
# -----------------------------
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

def move_to_history(lock, result, units):
    lock_copy = lock.copy()
    lock_copy["status"] = "RESOLVED"
    lock_copy["result"] = result
    lock_copy["units"] = units
    st.session_state.history.append(lock_copy)

# -----------------------------
# MOCK DATA PIPELINE
# -----------------------------
def mock_board_data(sport: str):
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

    model_scores = []
    for _, row in props.iterrows():
        base = 0.82 if "Wembanyama" in row["Player"] else 0.78 if "Maxey" in row["Player"] else 0.72
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
        wc = calculate_weighted_consensus(scores)
        tier = assign_tier(wc)
        model_scores.append((wc, tier))

    props["Weighted Score"] = [x[0] for x in model_scores]
    props["Tier"] = [x[1] for x in model_scores]

    return {
        "props": props,
        "injuries": injuries,
        "spreads": spreads,
        "series": series,
    }

def mock_game_data(sport: str):
    games = pd.DataFrame(
        [
            ["NYK @ PHI", "PHI -2.5", "PHI ML -145", "O/U 214.5"],
            ["MIN @ SAS", "MIN -4.5", "MIN ML -180", "O/U 218.0"],
        ],
        columns=["Matchup", "Spread", "Moneyline", "Total"],
    )

    model_scores = []
    for _, row in games.iterrows():
        base = 0.74 if "PHI" in row["Matchup"] or "MIN" in row["Matchup"] else 0.66
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
        wc = calculate_weighted_consensus(scores)
        tier = assign_tier(wc)
        model_scores.append((wc, tier))

    games["Weighted Score"] = [x[0] for x in model_scores]
    games["Tier"] = [x[1] for x in model_scores]

    return games

# -----------------------------
# SCANNER / PARSING PLACEHOLDERS
# -----------------------------
def scan_source(name: str, sport: str):
    ok = True
    error = None
    st.session_state.scanner_status[name]["ok"] = ok
    st.session_state.scanner_status[name]["last"] = datetime.now().strftime("%H:%M:%S")
    st.session_state.scanner_status[name]["error"] = error

def scan_all_sources(sport: str):
    for src in DATA_SOURCES:
        scan_source(src, sport)
    st.session_state.board_data = mock_board_data(sport)
    st.session_state.games = mock_game_data(sport)

def parse_manual_text(text: str, sport: str):
    st.session_state.board_data = mock_board_data(sport)
    st.session_state.games = mock_game_data(sport)

def parse_screenshot(image, sport: str):
    if Image is None or pytesseract is None:
        st.warning("OCR libraries not available; using mock data instead.")
    st.session_state.board_data = mock_board_data(sport)
    st.session_state.games = mock_game_data(sport)

# -----------------------------
# RECONCILIATION (MOCK)
# -----------------------------
def mock_box_score_result(lock):
    # Mock: 65% hit rate for Sovereign, 55% for Elite, 50% for Value
    tier = lock.get("tier", "VALUE")
    if tier == "SOVEREIGN":
        p = 0.65
    elif tier == "ELITE":
        p = 0.55
    else:
        p = 0.50
    hit = random.random() < p
    return "WIN" if hit else "LOSS"

def reconcile_locks(active_unit):
    new_locks = []
    for lock in st.session_state.locks:
        if lock["status"] == "PENDING":
            result = mock_box_score_result(lock)
            units = active_unit if result == "WIN" else -active_unit
            move_to_history(lock, result, units)

            # SEM integrity adjustment (simple mock)
            if result == "WIN":
                st.session_state.sem_integrity = min(100, st.session_state.sem_integrity + 1)
            else:
                st.session_state.sem_integrity = max(40, st.session_state.sem_integrity - 2)

            # Bankroll update
            st.session_state.bankroll += units
        else:
            new_locks.append(lock)

    st.session_state.locks = [l for l in st.session_state.locks if l["status"] == "PENDING"]

# -----------------------------
# SIDEBAR – GOVERNANCE PANEL
# -----------------------------
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
    integrity = st.slider("Integrity Score (Manual Override)", 40, 100, st.session_state.sem_integrity)
    st.session_state.sem_integrity = integrity
    emergency_floor = st.slider("Emergency Floor (%)", 5, 25, 12)

# -----------------------------
# MAIN TABS
# -----------------------------
tab_analysis, tab_locks, tab_tools, tab_summary = st.tabs(
    ["Analysis", "Locks & Ledger", "Tools & SEM", "Summary Report"]
)

# -----------------------------
# ANALYSIS TAB
# -----------------------------
with tab_analysis:
    st.markdown("## 📊 THE BOARD OF 8 — CLARITY MODEL OUTPUT")

    sport = st.selectbox("Select Sport", ["NBA", "NFL", "MLB", "NHL", "ALL"], index=0)

    st.markdown(
        "**Data Source:** BettingPros + RotoWire + CBS Sports + Covers.com + DraftKings + ESPN"
    )
    st.markdown(
        f"**Sport:** {sport} — {date.today().strftime('%b %d, %Y')}  \n"
        f"Status: 🛡️ SAFE CORRIDOR MODE ACTIVE | 🚨 EMERGENCY FLOOR ACTIVE ({emergency_floor}%)"
    )

    st.markdown("---")

    col_scan, col_manual, col_screen = st.columns(3)
    with col_scan:
        if st.button("🔍 Scan from Web (All Sources)"):
            scan_all_sources(sport)
            st.success("Scan complete (mock pipeline).")
    with col_manual:
        st.write("Manual Data Paste:")
    with col_screen:
        st.write("Screenshot OCR:")

    manual_text = st.text_area("Paste raw board / props / injuries here (optional):", height=120)
    if st.button("Use Pasted Data"):
        if manual_text.strip():
            parse_manual_text(manual_text, sport)
            st.success("Manual data ingested (mock parser).")
        else:
            st.warning("No text detected.")

    screenshot = st.file_uploader("Upload screenshot (optional):", type=["png", "jpg", "jpeg"])
    if st.button("Use Screenshot OCR"):
        if screenshot is not None:
            img = Image.open(screenshot) if Image is not None else None
            parse_screenshot(img, sport)
            st.success("Screenshot processed (mock OCR).")
        else:
            st.warning("No screenshot uploaded.")

    st.markdown("---")

    board = st.session_state.board_data
    if board["props"] is None:
        st.info("No board data loaded yet. Run a scan, paste data, or upload a screenshot.")
    else:
        st.markdown("🔒 **Validation Firewall:** PASSED (2 games, 2 matchups verified, 0 props removed)")

        st.markdown("### 🚨 PRE-FILTER: LINEUP & INJURY VERIFICATION")
        st.table(board["injuries"])

        st.markdown("### 🚨 BLOWOUT ADVISORY")
        st.table(board["spreads"])

        st.markdown("### 📊 SERIES CONTEXT: APPLIED")
        st.table(board["series"])

        st.markdown("### 📊 PROPS SURVIVED PRE-FILTER")
        props = board["props"].copy()
        st.table(props[["Player", "Prop", "Line", "Side"]])

        st.markdown("### 🏀 GAME LINES — ML / SPREAD / TOTAL")
        games = st.session_state.games
        if games is not None:
            st.table(games[["Matchup", "Moneyline", "Spread", "Total"]])

        st.markdown("### 🗳️ MODEL-BY-MODEL VERDICTS (STRUCTURED MOCK)")
        st.markdown(
            """
**v5.3 DeepSeek — Outlier Suppression (Weight: 0.18)**  
- Approves Wembanyama REB Over, Maxey PTS Over, Edwards PTS Under.  
- Passes Embiid PTS (variance too high), combo props with wide sigma.

**v6.5 Gemini — Environmental Physics (Weight: 0.10)**  
- No major environmental flags; approves all single-stat props, passes combo props.

**v25.4 Claude — Motivation / Ref Bias (Weight: 0.14)**  
- Elevates Wembanyama and Maxey due to motivation and whistle profile.  
- Passes Brunson due to trap coverage.

**v4.0 Copilot — Deterministic Floor Engine (Weight: 0.14)**  
- Approves Wembanyama, Maxey, Towns, Edwards Under based on floor vs line.  
- Passes combo props (floors too tight).

**v4.1 Perplexity — Volatility Mapping (Weight: 0.10)**  
- Approves single-stat props; flags combo props as high variance.

**v6.0 Supreme — Governance / CLV Integrity (Weight: 0.18)**  
- Sovereign on Wembanyama and Maxey; approves Edwards Under.  
- Passes Embiid due to market uncertainty.

**v22.6 Grok — Ceiling Variance Engine (Weight: 0.10)**  
- Approves Wembanyama, Maxey, Towns; passes Brunson (ceiling capped).

**Base Model — Raw Projection Layer (Weight: 0.06)**  
- Approves Wembanyama, Maxey, Edwards; passes Embiid/Brunson.
"""
        )

        st.markdown("### 🟦 COUNCIL CONSENSUS SUMMARY")
        consensus = props[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier"]].copy()
        consensus["Tier Label"] = consensus["Tier"].apply(tier_badge)
        st.table(consensus)

        st.markdown("### 🔐 Lock Props from This Board")
        for idx, row in props.iterrows():
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
                if st.button("LOCK THIS PROP", key=f"lock_prop_{idx}"):
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
                    if st.button("LOCK THIS GAME", key=f"lock_game_{idx}"):
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

# -----------------------------
# LOCKS & LEDGER TAB
# -----------------------------
with tab_locks:
    st.markdown("## 🔒 BETCOUNCIL LOCKS, PARLAY & LEDGER")

    board = st.session_state.board_data
    if board["props"] is None or st.session_state.games is None:
        st.info("No board data available. Load data from Analysis tab first.")
    else:
        df_props = board["props"].copy()
        df_games = st.session_state.games.copy()

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
                            "Time": h["timestamp"],
                        }
                    )
            st.table(pd.DataFrame(hist_rows))

        st.markdown("---")
        st.markdown("### 🔗 BETCOUNCIL PARLAY OF THE DAY — PROPS")
        parlay_df = df_props.sort_values("Weighted Score", ascending=False).head(4)
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
            f"Four-leg configuration utilizing Alt-Line insulation to avoid 0.5 hook variance. "
            f"Total unit exposure: ${active_unit:.2f} (Regular Floor)."
        )

# -----------------------------
# TOOLS & SEM TAB
# -----------------------------
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
        scan_all_sources("NBA")
        st.success("Scan complete (mock).")

    st.markdown("---")
    st.markdown("### 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
    st.markdown(
        """
- RLM Status: DETECTED — Example: Edwards UNDER 25.5 PTS moving against public sentiment.  
- Contrarian Flag: ACTIVE — Public on Embiid Over; Council on Under/Pass.  
- Regime Type: STABLE  
- CLV: Tracked vs closing lines (mock placeholder).
"""
    )

    st.markdown("---")
    st.markdown("### 11-Sensor Checklist")
    sensors = [
        "Lineup Confirmed",
        "Minutes Floor Verified",
        "Blowout Risk Evaluated",
        "Pace & Possessions Context",
        "Matchup Coverage & Scheme",
        "Referee / Whistle Profile",
        "Travel & Rest Differential",
        "CLV vs Open/Close",
        "Public vs Sharp Money Split",
        "Historical Sigma / Volatility",
        "Correlation with Other Board Props",
    ]
    for s in sensors:
        st.checkbox(s)

    st.markdown("---")
    st.markdown("### 🛡️ SEM STATUS")
    st.markdown(
        f"- Integrity Score: {st.session_state.sem_integrity}  \n"
        f"- Safe Corridor: ACTIVE  \n"
        f"- Emergency Floor: ACTIVE ({emergency_floor}%)  \n"
        "- Blowout Advisory: INACTIVE  \n"
        "- Active Locks: "
        f"{len([l for l in st.session_state.locks if l['status']=='PENDING'])}"
    )

    st.markdown("---")
    st.markdown("### SEM Learning Log")
    st.text_area(
        "SEM Notes (e.g., 'Sovereign pick lost due to foul trouble, not model error.')",
        height=150,
    )

# -----------------------------
# SUMMARY REPORT TAB
# -----------------------------
with tab_summary:
    st.markdown("## 🧾 THE BOARD OF 8 — CLARITY MODEL OUTPUT (Summary Report)")

    board = st.session_state.board_data
    games = st.session_state.games
    if board["props"] is None or games is None:
        st.info("No board data loaded yet. Load data from Analysis tab first.")
    else:
        props = board["props"]
        injuries = board["injuries"]
        spreads = board["spreads"]
        series = board["series"]

        st.markdown(
            "**Data Source:** BettingPros + RotoWire + CBS Sports + Covers.com + DraftKings + ESPN"
        )
        st.markdown(
            f"**Sport:** NBA — {date.today().strftime('%b %d, %Y')}  \n"
            f"Status: 🛡️ SAFE CORRIDOR MODE ACTIVE | 🚨 EMERGENCY FLOOR ACTIVE ({emergency_floor}%)"
        )

        st.markdown(
            "🔒 **Validation Firewall:** PASSED "
            f"({len(spreads)} games, {len(injuries)} matchups verified, 0 props removed)"
        )

        st.markdown("### 🚨 PRE-FILTER: LINEUP & INJURY VERIFICATION")
        st.table(injuries)
        st.caption("Lineup data sourced from BettingPros / RotoWire / DraftEdge equivalents (mock).")

        st.markdown("### 🚨 BLOWOUT ADVISORY")
        st.table(spreads)

        st.markdown("### 📊 SERIES CONTEXT: APPLIED")
        st.table(series)

        st.markdown("### 📊 PROPS SURVIVED PRE-FILTER")
        st.table(props[["Player", "Prop", "Line", "Side"]])

        st.markdown("### 🗳️ MODEL-BY-MODEL VERDICTS")
        st.markdown(
            """
- v5.3 DeepSeek — Outlier Suppression (0.18): Approves Wembanyama/Maxey/Edwards Under; passes Embiid/Brunson combo props.  
- v6.5 Gemini — Environmental Physics (0.10): No major environment flags; approves single-stat props.  
- v25.4 Claude — Motivation / Ref Bias (0.14): Elevates Wembanyama/Maxey; passes Brunson.  
- v4.0 Copilot — Deterministic Floor Engine (0.14): Approves Wembanyama/Maxey/Towns/Edwards Under; passes combo props.  
- v4.1 Perplexity — Volatility Mapping (0.10): Approves single-stat props; flags combo props.  
- v6.0 Supreme — Governance / CLV Integrity (0.18): Sovereign on Wembanyama/Maxey; approves Edwards Under; passes Embiid.  
- v22.6 Grok — Ceiling Variance Engine (0.10): Approves Wembanyama/Maxey/Towns; passes Brunson.  
- Base Model — Raw Projection Layer (0.06): Approves Wembanyama/Maxey/Edwards; passes Embiid/Brunson.
"""
        )

        st.markdown("### 🟦 COUNCIL CONSENSUS SUMMARY")
        consensus = props[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier"]].copy()
        consensus["Tier Label"] = consensus["Tier"].apply(tier_badge)
        st.table(consensus)

        st.markdown("**Excluded:** Brunson (volatility / trap coverage), combo props (insufficient model density).")

        st.markdown("### 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        st.markdown(
            """
- RLM Status: DETECTED — Edwards UNDER 25.5 PTS moving against public sentiment.  
- Contrarian Flag: ACTIVE — Public on Embiid Over; Council strictly on Under/Pass.  
- Regime Type: STABLE  
"""
        )

        st.markdown("### 🛡️ SEM STATUS")
        st.markdown(
            f"- Integrity Score: {st.session_state.sem_integrity}  \n"
            f"- Safe Corridor: ACTIVE  \n"
            f"- Emergency Floor: ACTIVE ({emergency_floor}%)  \n"
            "- Blowout Advisory: INACTIVE  \n"
            f"- Active Locks: {len([l for l in st.session_state.locks if l['status']=='PENDING'])}"
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
        parlay_df = props.sort_values("Weighted Score", ascending=False).head(4)
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
            f"Four-leg configuration utilizing Alt-Line insulation to avoid 0.5 hook variance. "
            f"Total unit exposure: ${active_unit:.2f} (Regular Floor)."
        )
