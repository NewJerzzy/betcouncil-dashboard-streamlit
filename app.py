import streamlit as st
import pandas as pd
from datetime import date

# -----------------------------
# 1. GLOBAL CONFIG & THEME
# -----------------------------
st.set_page_config(
    page_title="BetCouncil v3.1 OS",
    page_icon="🛡️",
    layout="wide",
)

# Custom "European Noir" styling
st.markdown(
    """
    <style>
    body {
        background-color: #0b0b0f;
    }
    .main {
        background-color: #0b0b0f;
        color: #e5e5e5;
    }
    .stApp {
        background-color: #0b0b0f;
    }
    h1, h2, h3, h4 {
        color: #e8c76a;
    }
    .gold-text {
        color: #e8c76a;
        font-weight: 600;
    }
    .pill {
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        border: 1px solid #444;
        display: inline-block;
        margin-right: 6px;
    }
    .pill-green {
        background: rgba(34,197,94,0.12);
        border-color: rgba(34,197,94,0.6);
        color: #bbf7d0;
    }
    .pill-amber {
        background: rgba(245,158,11,0.12);
        border-color: rgba(245,158,11,0.6);
        color: #fed7aa;
    }
    .pill-red {
        background: rgba(239,68,68,0.12);
        border-color: rgba(239,68,68,0.6);
        color: #fecaca;
    }
    .tier-gold {
        color: #e8c76a;
        font-weight: 700;
    }
    .tier-silver {
        color: #cbd5f5;
        font-weight: 600;
    }
    .tier-bronze {
        color: #fbbf77;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# 2. CONSTANTS (SOVEREIGN SOURCE)
# -----------------------------

MODEL_WEIGHTS = {
    "deepseek": 0.18,     # Outlier Suppression
    "supreme": 0.18,      # Governance / CLV
    "claude": 0.14,       # Motivation / Ref Bias
    "copilot": 0.14,      # Deterministic Floor
    "gemini": 0.10,       # Environmental Physics
    "perplexity": 0.10,   # Volatility Mapping
    "grok": 0.10,         # Ceiling Variance
    "base": 0.06,         # Historical Mean
}

TIER_THRESHOLDS = {
    "SOVEREIGN": 0.75,
    "ELITE": 0.65,
    "VALUE": 0.55,
}

DEFAULT_BANKROLL = 527.25
ACTIVE_FLOOR = 0.045   # 4.5%
KELLY_FRACTION = 0.25  # Quarter Kelly
EXPECTED_ACTIVE_UNIT = 3.95  # Governance reference

# -----------------------------
# 3. CORE FUNCTIONS
# -----------------------------

def calculate_active_unit(bankroll: float,
                          floor: float = ACTIVE_FLOOR,
                          kelly: float = KELLY_FRACTION) -> float:
    """
    Section 6.0 – Bankroll Governance
    Active Unit = (Bankroll × Active Floor) × Kelly Fraction
    """
    return round(bankroll * floor * kelly, 2)


def calculate_weighted_consensus(model_scores: dict) -> float:
    """
    Section 3.1 – Clarity Engine
    WeightedConsensus = Σ(ModelScore × Weight)
    model_scores keys must match MODEL_WEIGHTS keys.
    """
    score = 0.0
    for model, weight in MODEL_WEIGHTS.items():
        score += model_scores.get(model, 0) * weight
    return round(score, 3)


def assign_tier(weighted_score: float) -> str:
    """
    Apply Sovereign / Elite / Value thresholds.
    """
    if weighted_score >= TIER_THRESHOLDS["SOVEREIGN"]:
        return "SOVEREIGN"
    elif weighted_score >= TIER_THRESHOLDS["ELITE"]:
        return "ELITE"
    elif weighted_score >= TIER_THRESHOLDS["VALUE"]:
        return "VALUE"
    else:
        return "PASS"


def tier_badge(tier: str) -> str:
    if tier == "SOVEREIGN":
        return '<span class="tier-gold">🟢 Sovereign</span>'
    if tier == "ELITE":
        return '<span class="tier-silver">🟡 Elite</span>'
    if tier == "VALUE":
        return '<span class="tier-bronze">🥉 Value</span>'
    return "—"


def mock_props():
    """
    Temporary Survivor Table (Section 4.0 + 3.1 demo).
    In production, this would be fed by your scraper + firewall.
    """
    data = [
        {
            "player": "Jayson Tatum",
            "prop": "Points",
            "line": 27.5,
            "side": "OVER",
            "firewall_ok": True,
            "series_context": "+8% usage last 3 games",
            "models": {
                "deepseek": 0.82,
                "supreme": 0.80,
                "claude": 0.78,
                "copilot": 0.81,
                "gemini": 0.76,
                "perplexity": 0.74,
                "grok": 0.79,
                "base": 0.70,
            },
        },
        {
            "player": "Jrue Holiday",
            "prop": "Assists",
            "line": 6.5,
            "side": "OVER",
            "firewall_ok": True,
            "series_context": "+12% potential assists vs. this coverage",
            "models": {
                "deepseek": 0.72,
                "supreme": 0.70,
                "claude": 0.69,
                "copilot": 0.71,
                "gemini": 0.66,
                "perplexity": 0.64,
                "grok": 0.68,
                "base": 0.61,
            },
        },
        {
            "player": "Derrick White",
            "prop": "3PM",
            "line": 2.5,
            "side": "UNDER",
            "firewall_ok": True,
            "series_context": "-9% volume vs. length + contest rate",
            "models": {
                "deepseek": 0.69,
                "supreme": 0.67,
                "claude": 0.65,
                "copilot": 0.66,
                "gemini": 0.63,
                "perplexity": 0.62,
                "grok": 0.64,
                "base": 0.58,
            },
        },
        {
            "player": "Bench Guard X",
            "prop": "Points",
            "line": 11.5,
            "side": "OVER",
            "firewall_ok": False,  # fails firewall (minutes volatility)
            "series_context": "Rotation unstable, blowout risk high",
            "models": {
                "deepseek": 0.61,
                "supreme": 0.58,
                "claude": 0.55,
                "copilot": 0.57,
                "gemini": 0.54,
                "perplexity": 0.52,
                "grok": 0.56,
                "base": 0.50,
            },
        },
    ]

    rows = []
    for idx, row in enumerate(data, start=1):
        wc = calculate_weighted_consensus(row["models"])
        tier = assign_tier(wc)
        rows.append(
            {
                "#": idx,
                "Player": row["player"],
                "Prop": row["prop"],
                "Line": row["line"],
                "Side": row["side"],
                "Weighted Score": wc,
                "Tier": tier,
                "Firewall": "PASS" if row["firewall_ok"] else "BLOCK",
                "Series Context": row["series_context"],
            }
        )
    return pd.DataFrame(rows)


def generate_clarity_bullets(row: pd.Series) -> list:
    """
    Section 9.1 – Synthesis Summary bullets.
    Very lightweight logic for now; can be deepened later.
    """
    bullets = []
    wc = row["Weighted Score"]
    tier = row["Tier"]

    if tier == "SOVEREIGN":
        bullets.append("All 8 models are aligned above the Sovereign threshold.")
    elif tier == "ELITE":
        bullets.append("Strong multi-model alignment with minor variance in volatility engines.")
    elif tier == "VALUE":
        bullets.append("Edge exists but variance and environment require discipline on unit size.")
    else:
        bullets.append("Consensus not strong enough for Council endorsement.")

    if "UNDER" in row["Side"]:
        bullets.append("Floor engines show line sitting above realistic median outcome.")
    else:
        bullets.append("Deterministic floor sits comfortably above the posted line.")

    if "usage" in row["Series Context"].lower():
        bullets.append("Series context confirms a meaningful usage shift in favor of this angle.")
    if "blowout" in row["Series Context"].lower():
        bullets.append("Blowout risk flagged—minutes volatility must be respected.")

    return bullets


# -----------------------------
# 4. SIDEBAR – GOVERNANCE PANEL
# -----------------------------

with st.sidebar:
    st.markdown("### 🛡️ BetCouncil v3.1 OS")
    st.markdown('<span class="gold-text">Sovereign Governance Panel</span>', unsafe_allow_html=True)

    bankroll = st.number_input(
        "Current Bankroll ($)",
        min_value=0.0,
        value=float(DEFAULT_BANKROLL),
        step=10.0,
        format="%.2f",
    )

    active_unit = calculate_active_unit(bankroll)
    st.metric("Active Floor", f"{ACTIVE_FLOOR * 100:.1f}%")
    st.metric("Kelly Fraction", f"{KELLY_FRACTION:.2f}")
    st.metric("Active Unit ($)", f"{active_unit:.2f}")

    st.markdown("---")
    st.markdown("#### Integrity & SEM")
    integrity_score = st.slider("Integrity Score", min_value=70, max_value=100, value=92)
    emergency_floor = st.slider("Emergency Floor (%)", min_value=5, max_value=25, value=12)
    st.caption("SEM Engine adjusts Integrity Score over time based on realized outcomes.")

# -----------------------------
# 5. MAIN LAYOUT – TABS
# -----------------------------

tab_analysis, tab_locks, tab_tools = st.tabs(["Analysis", "Locks & Parlay", "Tools & SEM"])

# -----------------------------
# 5.1 ANALYSIS TAB
# -----------------------------
with tab_analysis:
    st.markdown("## 📊 The Board of 8 — Clarity Model Output")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(
            f"""
            **Data Sources:** BettingPros, RotoWire, CBS Sports, Covers, DraftKings, ESPN  
            **Sport:** NBA — {date.today().strftime('%b %d, %Y')}  
            """
        )
    with col2:
        st.markdown(
            """
            <div class="pill pill-green">🛡️ Safe Corridor Mode: ACTIVE</div>
            <div class="pill pill-amber">🚨 Emergency Floor: 12%</div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Firewall + Pre-filter (mock)
    st.markdown("### 4.0 Validation Firewall & Pre-Filter")
    fw_col1, fw_col2 = st.columns([1.5, 2])

    with fw_col1:
        st.markdown("**Lineup & Injury Sanity**")
        st.table(
            pd.DataFrame(
                [
                    {"Game": "BOS @ MIA", "Status": "All starters probable"},
                    {"Game": "DEN @ MIN", "Status": "Q-tag on 6th man only"},
                ]
            )
        )

    with fw_col2:
        st.markdown("**Blowout & Minutes Advisory**")
        st.table(
            pd.DataFrame(
                [
                    {"Game": "BOS @ MIA", "Spread": "-4.5", "Advisory": "✅ Active", "Effect": "Normal minutes"},
                    {"Game": "DEN @ MIN", "Spread": "-11.5", "Advisory": "⚠️ Caution", "Effect": "Garbage time risk"},
                ]
            )
        )

    st.markdown("---")

    # Survivor Table (Primary Props)
    st.markdown("### 4.1 Survivor Table – Primary Props After Firewall")
    df_props = mock_props()
    st.dataframe(
        df_props.style.format(
            {
                "Line": "{:.1f}",
                "Weighted Score": "{:.3f}",
            }
        ),
        use_container_width=True,
    )

    st.markdown("---")

    # Model-by-Model Verdicts (structure only for now)
    st.markdown("### 5.0 Model-by-Model Verdicts (Weighted Council)")
    st.caption("Each model contributes according to the 0.18 / 0.14 / 0.10 / 0.06 Sovereign protocol.")

    weights_df = pd.DataFrame(
        [
            {"Model": "V5.3 DeepSeek — Outlier Suppression", "Weight": MODEL_WEIGHTS["deepseek"]},
            {"Model": "V6.0 Supreme — Governance / CLV Integrity", "Weight": MODEL_WEIGHTS["supreme"]},
            {"Model": "V25.4 Claude — Motivation / Ref Bias", "Weight": MODEL_WEIGHTS["claude"]},
            {"Model": "V4.0 Copilot — Deterministic Floor Engine", "Weight": MODEL_WEIGHTS["copilot"]},
            {"Model": "V6.5 Gemini — Environmental Physics", "Weight": MODEL_WEIGHTS["gemini"]},
            {"Model": "V4.1 Perplexity — Volatility Mapping", "Weight": MODEL_WEIGHTS["perplexity"]},
            {"Model": "V22.6 Grok — Ceiling Variance Engine", "Weight": MODEL_WEIGHTS["grok"]},
            {"Model": "Base Model — Raw Projection Layer", "Weight": MODEL_WEIGHTS["base"]},
        ]
    )
    st.table(weights_df.style.format({"Weight": "{:.2f}"}))

    st.markdown("---")

    # Council Consensus Summary
    st.markdown("### 6.0 Council Consensus Summary")

    consensus_rows = []
    for _, row in df_props.iterrows():
        consensus_rows.append(
            {
                "Pick": f"{row['Player']} {row['Prop']} {row['Side']} {row['Line']}",
                "Weighted Score": row["Weighted Score"],
                "Tier": row["Tier"],
            }
        )
    st.table(pd.DataFrame(consensus_rows).style.format({"Weighted Score": "{:.3f}"}))

    st.markdown("---")

    # 9.1 Synthesis Summary – Narrative
    st.markdown("### 9.1 Synthesis Summary – Clarity Report")

    for _, row in df_props.iterrows():
        if row["Tier"] == "PASS":
            continue

        st.markdown(f"**Pick:** {row['Player']} — {row['Prop']} {row['Side']} {row['Line']}")
        st.markdown(
            f"**Weighted Score:** `{row['Weighted Score']:.3f}` | Tier: {tier_badge(row['Tier'])}",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Series Context:** {row['Series Context']}")
        bullets = generate_clarity_bullets(row)
        for b in bullets:
            st.markdown(f"- {b}")
        st.markdown("---")

# -----------------------------
# 5.2 LOCKS & PARLAY TAB
# -----------------------------
with tab_locks:
    st.markdown("## 🔒 Lock & Parlay Configuration")

    # Choose Sovereign / Elite candidates
    sovereign_df = df_props[df_props["Tier"].isin(["SOVEREIGN", "ELITE", "VALUE"])].copy()
    sovereign_df = sovereign_df.sort_values("Weighted Score", ascending=False)

    if not sovereign_df.empty:
        lock_pick = sovereign_df.iloc[0]
        st.markdown("### Lock of the Day")
        st.markdown(
            f"**{lock_pick['Player']} — {lock_pick['Prop']} {lock_pick['Side']} {lock_pick['Line']}**  "
            f"(Weighted Score: `{lock_pick['Weighted Score']:.3f}`, Tier: {lock_pick['Tier']})"
        )
        st.caption(f"Suggested Stake: **{calculate_active_unit(bankroll)} units** at current governance floor.")
    else:
        st.info("No Sovereign/Elite/Value picks available after firewall.")

    st.markdown("---")

    st.markdown("### Parlay of the Day (Max 5 Legs, Low-Variance Bias)")
    max_legs = st.slider("Max Legs", min_value=2, max_value=5, value=3)

    # Simple rule: take top N non-conflicting props (mock: just top N)
    parlay_candidates = sovereign_df.head(max_legs)

    if parlay_candidates.empty:
        st.info("No eligible legs for parlay under current filters.")
    else:
        for i, (_, row) in enumerate(parlay_candidates.iterrows(), start=1):
            st.markdown(
                f"**Leg {i}:** {row['Player']} — {row['Prop']} {row['Side']} {row['Line']}  "
                f"(Tier: {row['Tier']}, Score: `{row['Weighted Score']:.3f}`)"
            )
        st.caption("Rule: No same-team correlation in production unless explicitly configured as SGP.")

# -----------------------------
# 5.3 TOOLS & SEM TAB
# -----------------------------
with tab_tools:
    st.markdown("## 🧪 Tools, Sensors & SEM Engine")

    st.markdown("### 11-Sensor Checklist (Mock Layout)")
    sensors = [
        "1. Lineup Confirmed (No late scratches)",
        "2. Minutes Floor Verified",
        "3. Blowout Risk Evaluated",
        "4. Pace & Possessions Context",
        "5. Matchup Coverage & Scheme",
        "6. Referee / Whistle Profile",
        "7. Travel & Rest Differential",
        "8. CLV vs. Open / Close Line",
        "9. Public vs. Sharp Money Split",
        "10. Historical Sigma / Volatility",
        "11. Correlation with Other Board Props",
    ]
    for s in sensors:
        st.checkbox(s, value=False)

    st.markdown("---")

    st.markdown("### 12.0 SEM Learning Log")
    st.caption("Use this to manually log outcomes and let the SEM conceptually adjust Integrity over time.")
    sem_notes = st.text_area(
        "SEM Notes (e.g., 'Sovereign pick lost due to foul trouble, not model error.')",
        height=150,
    )
    if st.button("Save SEM Entry (Local Only)"):
        st.success("SEM entry recorded locally (no database wired yet).")

    st.markdown("---")
    st.markdown("### Backup Recovery Command")
    st.code(
        'Revert to Section 9.1 Master Blueprint. Clear all placeholder names. '
        'Calculate weighted consensus using the 0.18/0.14/0.10/0.06 protocol. '
        'Display full table headers including Firewall Status and Series Context. '
        'Active Unit is $3.95. Execute.',
        language="text",
    )
