import streamlit as st
import pandas as pd
from datetime import date, datetime

# Optional imports for scraping / OCR
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

# locks ledger: list of dicts
if "locks" not in st.session_state:
    st.session_state.locks = []

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
        return '<span class="tier-gold">🟢 Sovereign Lock</span>'
    if tier == "ELITE":
        return '<span class="tier-silver">🟡 Elite Edge</span>'
    if tier == "VALUE":
        return '<span class="tier-bronze">🥉 Value</span>'
    return "—"

def add_lock(entry: dict):
    st.session_state.locks.append(entry)

def remove_lock(index: int):
    if 0 <= index < len(st.session_state.locks):
        st.session_state.locks.pop(index)

def clear_locks():
    st.session_state.locks = []

# -----------------------------
# MOCK / PLACEHOLDER DATA PIPELINE
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
        base = 0.8 if "Wembanyama" in row["Player"] or "Maxey" in row["Player"] else 0.65
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

# -----------------------------
# SCRAPER / SCANNER PLACEHOLDERS
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

def parse_manual_text(text: str, sport: str):
    st.session_state.board_data = mock_board_data(sport)

def parse_screenshot(image, sport: str):
    if Image is None or pytesseract is None:
        st.warning("OCR libraries not available; using mock data instead.")
    st.session_state.board_data = mock_board_data(sport)

# -----------------------------
# SIDEBAR – GOVERNANCE PANEL
# -----------------------------
with st.sidebar:
    st.markdown("### 🛡️ BetCouncil v3.1 OS")
    st.markdown('<span class="gold-text">Sovereign Governance Panel</span>', unsafe_allow_html=True)

    bankroll = st.number_input("Bankroll ($)", value=DEFAULT_BANKROLL, step=10.0)
    active_unit = calculate_active_unit(bankroll)

    st.metric("Active Floor", f"{ACTIVE_FLOOR*100:.1f}%")
    st.metric("Kelly Fraction", f"{KELLY_FRACTION:.2f}")
    st.metric("Active Unit", f"${active_unit:.2f}")

    st.markdown("---")
    integrity = st.slider("Integrity Score", 60, 100, 69)
    emergency_floor = st.slider("Emergency Floor (%)", 5, 25, 12)

# -----------------------------
# MAIN TABS
# -----------------------------
tab_analysis, tab_locks, tab_tools, tab_summary = st.tabs(
    ["Analysis", "Locks & Parlay", "Tools & SEM", "Summary Report"]
)

# -----------------------------
# ANALYSIS TAB
# -----------------------------
with tab_analysis:
    st.markdown("## 📊 THE BOARD OF 8 — CLARITY MODEL OUTPUT")

    sport = st.selectbox("Select Sport", ["NBA", "NFL", "MLB", "NHL", "ALL"], index=0)

    st.markdown(
        f"**Data Source:** BettingPros + RotoWire + CBS Sports + Covers.com + DraftKings + ESPN"
    )
    st.markdown(
        f"**Sport:** {sport} — {date.today().strftime('%b %d, %Y')}  "
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
        st.markdown("### 🔒 Validation Firewall & Pre-Filter")
        st.markdown("**Lineup & Injury Verification**")
        st.table(board["injuries"])

        st.markdown("**Blowout Advisory**")
        st.table(board["spreads"])

        st.markdown("### 📊 Series Context: Applied")
        st.table(board["series"])

        st.markdown("### 📊 Props Survived Pre-Filter")
        props = board["props"].copy()
        st.dataframe(props, use_container_width=True)

        st.markdown("### 🔐 Lock Props from This Board")
        for idx, row in props.iterrows():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 2])
            with c1:
                st.write(f"**{row['Player']}** — {row['Prop']}")
            with c2:
                st.write(f"{row['Side']} {row['Line']}")
            with c3:
                st.write(f"{row['Tier']}")
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

# -----------------------------
# LOCKS & PARLAY TAB
# -----------------------------
with tab_locks:
    st.markdown("## 🔒 BETCOUNCIL LOCKS & PARLAY")

    board = st.session_state.board_data
    if board["props"] is None:
        st.info("No props available. Load data from Analysis tab first.")
    else:
        df = board["props"].copy()
        df_sorted = df.sort_values("Weighted Score", ascending=False)

        st.markdown("### Auto-Selected Lock of the Day (Model)")
        lock = df_sorted.iloc[0]
        lock_text = (
            f"**{lock['Player']} {lock['Prop']} {lock['Side']} {lock['Line']}**  \n"
            f"Weighted Score: `{lock['Weighted Score']:.3f}`  \n"
            f"Tier: {lock['Tier']}"
        )
        st.markdown(lock_text, unsafe_allow_html=True)
        st.caption(f"Unit Exposure: ${active_unit:.2f} (Regular Floor).")

        st.markdown("---")
        st.markdown("### Your Locked Bets (Ledger)")

        if not st.session_state.locks:
            st.info("No locked bets yet. Lock props from the Analysis tab.")
        else:
            lock_rows = []
            for i, l in enumerate(st.session_state.locks):
                lock_rows.append(
                    {
                        "#": i + 1,
                        "Type": l["type"],
                        "Sport": l["sport"],
                        "Player": l.get("player", ""),
                        "Prop": l.get("prop", ""),
                        "Side": l.get("side", ""),
                        "Line": l.get("line", ""),
                        "Tier": l.get("tier", ""),
                        "Score": l.get("score", ""),
                        "Status": l.get("status", ""),
                        "Result": l.get("result", ""),
                        "Time": l.get("timestamp", ""),
                    }
                )
            st.table(pd.DataFrame(lock_rows))

            cols = st.columns(3)
            with cols[0]:
                if st.button("Clear All Locks"):
                    clear_locks()
                    st.success("All locks cleared.")
            with cols[1]:
                remove_index = st.number_input(
                    "Remove Lock #", min_value=1, max_value=len(st.session_state.locks), value=1
                )
                if st.button("Remove Selected Lock"):
                    remove_lock(remove_index - 1)
                    st.success("Lock removed.")
            with cols[2]:
                st.write("Reconcile logic will be wired here (box score scan).")

        st.markdown("---")
        st.markdown("### Parlay of the Day — Props (Max 5 Legs)")
        legs = st.slider("Legs", 2, 5, 4)

        parlay_df = df_sorted.head(legs)
        rows = []
        for i, (_, row) in enumerate(parlay_df.iterrows(), start=1):
            rows.append(
                {
                    "Leg": i,
                    "Player": row["Player"],
                    "Prop": row["Prop"],
                    "Line": row["Line"],
                    "Side": row["Side"],
                    "Tier": row["Tier"],
                }
            )
        st.table(pd.DataFrame(rows))

        st.caption(
            f"Four-leg configuration utilizing Alt-Line insulation to avoid 0.5 hook variance. "
            f"Total unit exposure: ${active_unit:.2f}."
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
    if board["props"] is None:
        st.info("No board data loaded yet. Load data from Analysis tab first.")
    else:
        props = board["props"]
        injuries = board["injuries"]
        spreads = board["spreads"]
        series = board["series"]

        st.markdown(
            f"**Data Source:** BettingPros + RotoWire + CBS Sports + Covers.com + DraftKings + ESPN"
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

        st.markdown("### 🚨 BLOWOUT ADVISORY")
        st.table(spreads)

        st.markdown("### 📊 SERIES CONTEXT: APPLIED")
        st.table(series)

        st.markdown("### 📊 PROPS SURVIVED PRE-FILTER")
        st.table(props[["Player", "Prop", "Line", "Side"]])

        st.markdown("### 🟦 COUNCIL CONSENSUS SUMMARY")
        consensus = props[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier"]].copy()
        st.table(consensus)

        st.markdown("### 🔒 BETCOUNCIL LOCK OF THE DAY")
        top = props.sort_values("Weighted Score", ascending=False).iloc[0]
        st.table(
            pd.DataFrame(
                [
                    {
                        "Type": "Prop",
                        "Pick": f"{top['Player']} {top['Prop']} {top['Side']}",
                        "Line": top["Line"],
                        "Tier": top["Tier"],
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
                    "Tier": row["Tier"],
                }
            )
        st.table(pd.DataFrame(parlay_rows))
        st.caption(
            f"Four-leg configuration utilizing Alt-Line insulation to avoid 0.5 hook variance. "
            f"Total unit exposure: ${active_unit:.2f} (Regular Floor)."
        )
