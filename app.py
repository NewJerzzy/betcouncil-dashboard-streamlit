import json
import random
from datetime import datetime, timedelta

import streamlit as st

# -----------------------------
# CONFIG & GLOBALS
# -----------------------------

st.set_page_config(
    page_title="BetCouncil v3.1 OS",
    page_icon="📊",
    layout="wide",
)

MODEL_WEIGHTS = {
    "DeepSeek": 0.18,
    "Supreme": 0.18,
    "Claude": 0.14,
    "Copilot": 0.14,
    "Gemini": 0.10,
    "Perplexity": 0.10,
    "Grok": 0.10,
    "Base": 0.06,
}

MODEL_NAMES = list(MODEL_WEIGHTS.keys())


def get_tier(consensus: int) -> str:
    if consensus > 75:
        return "sovereign"
    if consensus >= 65:
        return "elite"
    if consensus >= 55:
        return "value"
    return "unrated"


# -----------------------------
# SAMPLE DATA GENERATION
# -----------------------------

PLAYERS = [
    {"player": "Luka Doncic", "team": "DAL", "opponent": "OKC", "propType": "Points", "line": 28.5, "odds": "-115"},
    {"player": "Shai Gilgeous-Alexander", "team": "OKC", "opponent": "DAL", "propType": "Points", "line": 31.5, "odds": "-110"},
    {"player": "Jayson Tatum", "team": "BOS", "opponent": "CLE", "propType": "Rebounds", "line": 8.5, "odds": "+105"},
    {"player": "Donovan Mitchell", "team": "CLE", "opponent": "BOS", "propType": "Points", "line": 26.5, "odds": "-120"},
    {"player": "Nikola Jokic", "team": "DEN", "opponent": "MIN", "propType": "Assists", "line": 9.5, "odds": "-105"},
    {"player": "Anthony Edwards", "team": "MIN", "opponent": "DEN", "propType": "Points", "line": 25.5, "odds": "-110"},
    {"player": "Tyrese Haliburton", "team": "IND", "opponent": "NYK", "propType": "Assists", "line": 10.5, "odds": "+100"},
    {"player": "Jalen Brunson", "team": "NYK", "opponent": "IND", "propType": "Points", "line": 29.5, "odds": "-115"},
]


def random_vote():
    r = random.random()
    if r < 0.45:
        return "over"
    if r < 0.85:
        return "under"
    return "pass"


def generate_votes():
    votes = []
    for model in MODEL_NAMES:
        votes.append(
            {
                "model": model,
                "weight": MODEL_WEIGHTS[model],
                "vote": random_vote(),
                "confidence": 0.5 + random.random() * 0.5,
            }
        )
    return votes


def compute_consensus(votes):
    over_w = under_w = pass_w = 0.0
    for v in votes:
        w = v["weight"] * v["confidence"]
        if v["vote"] == "over":
            over_w += w
        elif v["vote"] == "under":
            under_w += w
        else:
            pass_w += w

    total = over_w + under_w + pass_w
    if total == 0:
        return 0, "pass"

    max_w = max(over_w, under_w, pass_w)
    if max_w == over_w:
        direction = "over"
    elif max_w == under_w:
        direction = "under"
    else:
        direction = "pass"

    score = round((max_w / total) * 100)
    return score, direction


def generate_sample_props():
    props = []
    for i, p in enumerate(PLAYERS, start=1):
        votes = generate_votes()
        score, direction = compute_consensus(votes)
        tier = get_tier(score)
        timestamp = (datetime.utcnow() - timedelta(minutes=random.randint(0, 60))).isoformat()
        firewall_passed = tier != "unrated" and random.random() > 0.2
        props.append(
            {
                "id": f"prop-{i:03d}",
                "player": p["player"],
                "team": p["team"],
                "opponent": p["opponent"],
                "propType": p["propType"],
                "line": p["line"],
                "odds": p["odds"],
                "votes": votes,
                "consensus": score,
                "consensusDirection": direction,
                "timestamp": timestamp,
                "firewallPassed": firewall_passed,
            }
        )
    return props


# -----------------------------
# SESSION STATE INIT
# -----------------------------

if "props" not in st.session_state:
    st.session_state.props = generate_sample_props()

if "ledger" not in st.session_state:
    st.session_state.ledger = []  # list of {id, prop, lockedAt, stake}

if "locked_ids" not in st.session_state:
    st.session_state.locked_ids = set()

if "is_scanning" not in st.session_state:
    st.session_state.is_scanning = False

if "is_refreshing" not in st.session_state:
    st.session_state.is_refreshing = False


# -----------------------------
# HELPERS
# -----------------------------

def refresh_analysis():
    new_props = []
    for p in st.session_state.props:
        new_votes = []
        for v in p["votes"]:
            new_votes.append(
                {
                    **v,
                    "vote": random.choice(["over", "under", "pass"]),
                    "confidence": 0.5 + random.random() * 0.5,
                }
            )
        score, direction = compute_consensus(new_votes)
        new_props.append({**p, "votes": new_votes, "consensus": score, "consensusDirection": direction})
    st.session_state.props = new_props


def lock_prop(prop, stake: float):
    entry = {
        "id": f"bet-{int(datetime.utcnow().timestamp() * 1000)}",
        "prop": prop,
        "lockedAt": datetime.utcnow().isoformat(),
        "stake": stake,
    }
    st.session_state.ledger.append(entry)
    st.session_state.locked_ids.add(prop["id"])


def export_ledger_json():
    return json.dumps(st.session_state.ledger, indent=2)


# -----------------------------
# SIDEBAR / NAV
# -----------------------------

st.sidebar.title("BetCouncil v3.1 OS")
st.sidebar.caption("Synthetic Betting Analytics Dashboard")

master_tab = st.sidebar.radio(
    "Navigation",
    ["Analysis", "Locks", "History", "SEM / Tools", "Settings"],
)

st.sidebar.markdown("---")
st.sidebar.metric("Bankroll", "$527.25")
st.sidebar.metric("Integrity Score", "69")
st.sidebar.metric("SEM Status", "Active")


# -----------------------------
# TOP BAR
# -----------------------------

col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("### Betting Analytics Dashboard")
    st.caption(
        f"BETCOUNCIL v3.1 OS · {datetime.now().strftime('%A, %b %d')}"
    )

with col_right:
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button("Ping", help="Ping all sources (mock)"):
            st.success("Ping complete: 11/11 sources online (mock)")

    with c2:
        if st.button("Scrape", help="Run scrape cycle (mock)"):
            st.session_state.is_scanning = True
            refresh_analysis()
            st.session_state.is_scanning = False
            st.success("Props pulled and board updated (mock)")

    with c3:
        if st.button("Refresh", help="Refresh model votes"):
            st.session_state.is_refreshing = True
            refresh_analysis()
            st.session_state.is_refreshing = False
            st.success("Analysis refreshed with latest signals")

    with c4:
        ledger_json = export_ledger_json()
        st.download_button(
            "Export",
            data=ledger_json,
            file_name=f"betcouncil-ledger-{datetime.utcnow().date()}.json",
            mime="application/json",
        )


st.markdown("---")

# -----------------------------
# ANALYSIS TAB
# -----------------------------

if master_tab == "Analysis":
    sub_tab = st.tabs(["Props Board", "Game Lines", "Injuries"])[0]

    props_tab, lines_tab, injuries_tab = st.tabs(
        ["Props Board", "Game Lines", "Injuries"]
    )

    # --- Props Board ---
    with props_tab:
        st.subheader("Props Board")

        # Filters (simple)
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            min_consensus = st.slider("Min Consensus %", 0, 100, 0, 5)
        with col_f2:
            dir_filter = st.selectbox("Direction", ["any", "over", "under", "pass"])
        with col_f3:
            firewall_only = st.checkbox("Firewall Passed Only", value=False)

        filtered = []
        for p in st.session_state.props:
            if p["consensus"] < min_consensus:
                continue
            if dir_filter != "any" and p["consensusDirection"] != dir_filter:
                continue
            if firewall_only and not p["firewallPassed"]:
                continue
            filtered.append(p)

        if not filtered:
            st.info("No props match the current filters.")
        else:
            for p in filtered:
                tier = get_tier(p["consensus"])
                locked = p["id"] in st.session_state.locked_ids

                with st.container(border=True):
                    top_cols = st.columns([3, 2, 2, 2, 2])
                    with top_cols[0]:
                        st.markdown(f"**{p['player']}**  \n{p['team']} vs {p['opponent']}")
                        st.caption(f"{p['propType']} · Line {p['line']} · Odds {p['odds']}")

                    with top_cols[1]:
                        st.metric("Consensus", f"{p['consensus']}%", p["consensusDirection"])

                    with top_cols[2]:
                        st.write("Tier")
                        st.markdown(f"**{tier.upper()}**")

                    with top_cols[3]:
                        st.write("Firewall")
                        st.markdown("✅ Passed" if p["firewallPassed"] else "⚠️ Blocked")

                    with top_cols[4]:
                        st.write("Lock")
                        if locked:
                            st.success("Locked")
                        else:
                            stake = st.number_input(
                                f"Stake for {p['id']}",
                                min_value=0.0,
                                value=10.0,
                                step=1.0,
                                key=f"stake_{p['id']}",
                            )
                            if st.button("Lock", key=f"lock_{p['id']}"):
                                if stake > 0:
                                    lock_prop(p, stake)
                                    st.success(
                                        f"Locked: {p['player']} {p['propType']} {p['line']} for ${stake:.2f}"
                                    )
                                else:
                                    st.warning("Stake must be > 0")

                    with st.expander("Model Votes"):
                        for v in p["votes"]:
                            st.write(
                                f"- **{v['model']}** · vote: `{v['vote']}` · "
                                f"weight: {v['weight']:.2f} · conf: {v['confidence']:.2f}"
                            )

    # --- Game Lines (placeholder) ---
    with lines_tab:
        st.subheader("Game Lines (Mock)")
        st.info("In the original app, this pulls from Supabase. Here it's just a placeholder.")
        st.table(
            [
                {"Matchup": "DAL @ OKC", "Spread": "OKC -3.5", "Total": 228.5},
                {"Matchup": "BOS @ CLE", "Spread": "BOS -4.0", "Total": 221.0},
                {"Matchup": "DEN @ MIN", "Spread": "DEN -2.5", "Total": 223.5},
            ]
        )

    # --- Injuries (placeholder) ---
    with injuries_tab:
        st.subheader("Injuries (Mock)")
        st.info("In the original app, this pulls from Supabase. Here it's just a placeholder.")
        st.table(
            [
                {"Player": "Luka Doncic", "Team": "DAL", "Status": "Questionable"},
                {"Player": "Donovan Mitchell", "Team": "CLE", "Status": "Probable"},
                {"Player": "Anthony Edwards", "Team": "MIN", "Status": "Out"},
            ]
        )

# -----------------------------
# LOCKS TAB
# -----------------------------

elif master_tab == "Locks":
    st.subheader("Locked Bets Ledger")

    if not st.session_state.ledger:
        st.info("No locked bets yet.")
    else:
        if st.button("Clear Ledger"):
            st.session_state.ledger = []
            st.session_state.locked_ids = set()
            st.success("Ledger cleared.")

        rows = []
        for e in st.session_state.ledger:
            p = e["prop"]
            rows.append(
                {
                    "Bet ID": e["id"],
                    "Player": p["player"],
                    "Prop": p["propType"],
                    "Line": p["line"],
                    "Odds": p["odds"],
                    "Stake": e["stake"],
                    "Locked At": e["lockedAt"],
                }
            )
        st.dataframe(rows, use_container_width=True)

# -----------------------------
# HISTORY TAB (placeholder)
# -----------------------------

elif master_tab == "History":
    st.subheader("History (Mock)")
    st.info("You could wire this to real results or past ledgers. For now, it's just a placeholder.")
    st.write("Imagine charts, hit rates, and ROI curves here.")

# -----------------------------
# SEM / TOOLS TAB (placeholder)
# -----------------------------

elif master_tab == "SEM / Tools":
    st.subheader("SEM / Tools")
    st.info("In your React app, this is a dedicated tools panel. Here it's a sandbox area.")
    st.write("- Integrity Score: 69")
    st.write("- Bankroll: $527.25")
    st.write("- SEM Status: Active")
    st.write("You can extend this tab with whatever tooling you want (simulators, bankroll mgmt, etc.).")

# -----------------------------
# SETTINGS TAB (placeholder)
# -----------------------------

elif master_tab == "Settings":
    st.subheader("Settings")
    st.info("This is a placeholder for user preferences, themes, etc.")
    dark_mode = st.checkbox("Dark mode (visual only, Streamlit already dark-ish)", value=True)
    st.write("You can add more settings here as needed.")

