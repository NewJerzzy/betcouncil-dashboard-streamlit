import streamlit as st
import pandas as pd
from datetime import date

# -----------------------------
# LIGHT THEME (WHITE BACKGROUND)
# -----------------------------
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
        return '<span class="tier-gold">🟢 Sovereign</span>'
    if tier == "ELITE":
        return '<span class="tier-silver">🟡 Elite</span>'
    if tier == "VALUE":
        return '<span class="tier-bronze">🥉 Value</span>'
    return "—"

# -----------------------------
# MOCK DATA
# -----------------------------
def mock_props():
    data = [
        {
            "player": "Jayson Tatum",
            "prop": "Points",
            "line": 27.5,
            "side": "OVER",
            "firewall_ok": True,
            "series_context": "+8% usage last 3 games",
            "models": {
                "deepseek": 0.82, "supreme": 0.80, "claude": 0.78, "copilot": 0.81,
                "gemini": 0.76, "perplexity": 0.74, "grok": 0.79, "base": 0.70,
            },
        },
        {
            "player": "Jrue Holiday",
            "prop": "Assists",
            "line": 6.5,
            "side": "OVER",
            "firewall_ok": True,
            "series_context": "+12% potential assists vs coverage",
            "models": {
                "deepseek": 0.72, "supreme": 0.70, "claude": 0.69, "copilot": 0.71,
                "gemini": 0.66, "perplexity": 0.64, "grok": 0.68, "base": 0.61,
            },
        },
        {
            "player": "Derrick White",
            "prop": "3PM",
            "line": 2.5,
            "side": "UNDER",
            "firewall_ok": True,
            "series_context": "-9% volume vs contest rate",
            "models": {
                "deepseek": 0.69, "supreme": 0.67, "claude": 0.65, "copilot": 0.66,
                "gemini": 0.63, "perplexity": 0.62, "grok": 0.64, "base": 0.58,
            },
        },
    ]

    rows = []
    for idx, row in enumerate(data, start=1):
        wc = calculate_weighted_consensus(row["models"])
        tier = assign_tier(wc)
        rows.append({
            "#": idx,
            "Player": row["player"],
            "Prop": row["prop"],
            "Line": row["line"],
            "Side": row["side"],
            "Weighted Score": wc,
            "Tier": tier,
            "Firewall": "PASS" if row["firewall_ok"] else "BLOCK",
            "Series Context": row["series_context"],
        })
    return pd.DataFrame(rows)

# -----------------------------
# SIDEBAR
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
    integrity = st.slider("Integrity Score", 70, 100, 92)
    emergency = st.slider("Emergency Floor (%)", 5, 25, 12)

# -----------------------------
# MAIN TABS
# -----------------------------
tab_analysis, tab_locks, tab_tools = st.tabs(["Analysis", "Locks & Parlay", "Tools & SEM"])

# -----------------------------
# ANALYSIS TAB
# -----------------------------
with tab_analysis:
    st.markdown("## 📊 The Board of 8 — Clarity Model Output")

    st.markdown(f"**Sport:** NBA — {date.today().strftime('%b %d, %Y')}")

    st.markdown(
        """
        <div class="pill pill-green">🛡️ Safe Corridor Mode: ACTIVE</div>
        <div class="pill pill-amber">🚨 Emergency Floor: 12%</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    st.markdown("### Survivor Table (After Firewall)")
    df = mock_props()
    st.dataframe(df, use_container_width=True)

    st.markdown("---")

    st.markdown("### Council Consensus Summary")
    summary = df[["Player", "Prop", "Side", "Line", "Weighted Score", "Tier"]]
    st.table(summary)

# -----------------------------
# LOCKS & PARLAY TAB
# -----------------------------
with tab_locks:
    st.markdown("## 🔒 Lock of the Day")

    df_sorted = df.sort_values("Weighted Score", ascending=False)
    lock = df_sorted.iloc[0]

    lock_text = (
        f"**{lock['Player']} — {lock['Prop']} {lock['Side']} {lock['Line']}**  \n"
        f"Weighted Score: `{lock['Weighted Score']}`  \n"
        f"Tier: {lock['Tier']}"
    )
    st.markdown(lock_text, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Parlay Builder (Max 5 Legs)")
    legs = st.slider("Legs", 2, 5, 3)

    for i, (_, row) in enumerate(df_sorted.head(legs).iterrows(), start=1):
        leg_text = (
            f"**Leg {i}:** {row['Player']} — {row['Prop']} {row['Side']} {row['Line']}  \n"
            f"Score: `{row['Weighted Score']}` · Tier: {row['Tier']}"
        )
        st.markdown(leg_text)

# -----------------------------
# TOOLS & SEM TAB
# -----------------------------
with tab_tools:
    st.markdown("## 🧪 Tools & SEM Engine")

    st.markdown("### 11-Sensor Checklist")
    sensors = [
        "Lineup Confirmed", "Minutes Floor Verified", "Blowout Risk Evaluated",
        "Pace Context", "Matchup Coverage", "Referee Profile", "Travel/Rest",
        "CLV Check", "Public vs Sharp", "Volatility", "Correlation Check"
    ]
    for s in sensors:
        st.checkbox(s)

    st.markdown("---")
    st.markdown("### SEM Notes")
    st.text_area("Log Notes", height=150)
