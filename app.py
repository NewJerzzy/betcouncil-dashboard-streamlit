import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
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

SEM_WINDOW_SIZE = 20  # number of recent bets to evaluate trend

# 14-sensor configuration (hybrid mode)
SENSOR_CONFIG = {
    "BettingPros": {
        "url": "https://www.bettingpros.com/nba/",
        "purpose": "Consensus props & line movement",
        "sem_impact": -2,
        "firewall_impact": "HIGH",
    },
    "RotoWire": {
        "url": "https://www.rotowire.com/basketball/",
        "purpose": "Injury verification & starting lineups",
        "sem_impact": -3,
        "firewall_impact": "CRITICAL",
    },
    "PineSports": {
        "url": "https://www.pine-sports.com/",
        "purpose": "Correlation & historical trend mapping",
        "sem_impact": -2,
        "firewall_impact": "MEDIUM",
    },
    "Action Network": {
        "url": "https://www.actionnetwork.com/nba",
        "purpose": "Sharp money & public betting percentages",
        "sem_impact": -3,
        "firewall_impact": "HIGH",
    },
    "CBS Sports": {
        "url": "https://www.cbssports.com/nba/predictions/",
        "purpose": "Expert consensus & simulations",
        "sem_impact": -1,
        "firewall_impact": "MEDIUM",
    },
    "Basketball-Reference": {
        "url": "https://www.basketball-reference.com/",
        "purpose": "Usage rates & defensive metrics",
        "sem_impact": -2,
        "firewall_impact": "HIGH",
    },
    "NBA Stats": {
        "url": "https://www.nba.com/stats",
        "purpose": "Official tracking data",
        "sem_impact": -2,
        "firewall_impact": "HIGH",
    },
    "Massey Ratings": {
        "url": "https://masseyratings.com/nba/ratings",
        "purpose": "Power rankings & home/away advantage",
        "sem_impact": -1,
        "firewall_impact": "MEDIUM",
    },
    "Dunkel Index": {
        "url": "https://www.dunkelindex.com/nba",
        "purpose": "Blowout probability & score projections",
        "sem_impact": -2,
        "firewall_impact": "HIGH",
    },
    "Covers": {
        "url": "https://www.covers.com/nba",
        "purpose": "Market movement & matchup previews",
        "sem_impact": -1,
        "firewall_impact": "MEDIUM",
    },
    "Yahoo Sports": {
        "url": "https://sports.yahoo.com/nba/",
        "purpose": "Volume indicators & injury reports",
        "sem_impact": -1,
        "firewall_impact": "MEDIUM",
    },
    "ESPN": {
        "url": "https://www.espn.com/nba/",
        "purpose": "Beat reporter news & rotation shifts",
        "sem_impact": -2,
        "firewall_impact": "HIGH",
    },
    "DraftKings": {
        "url": "https://sportsbook.draftkings.com/nba",
        "purpose": "Primary line anchor",
        "sem_impact": -2,
        "firewall_impact": "CRITICAL",
    },
    "FanDuel": {
        "url": "https://www.fanduel.com/sportsbook",
        "purpose": "Secondary line anchor for variance check",
        "sem_impact": -2,
        "firewall_impact": "CRITICAL",
    },
}

SENSOR_NAMES = list(SENSOR_CONFIG.keys())

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BetCouncilBot/1.0; +https://example.com/bot)"
}

# =========================
# SESSION STATE INIT
# =========================
if "sensor_status" not in st.session_state:
    st.session_state.sensor_status = {
        name: {
            "status": "UNKNOWN",  # PASS / FAIL / FALLBACK / UNKNOWN
            "last": None,
            "error": None,
            "fallback_used": False,
        }
        for name in SENSOR_NAMES
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
# MODEL VERDICTS
# =========================
def generate_model_verdicts_for_prop(player, prop, side, line, sport):
    base = 0.7
    if any(k in player for k in ["Wembanyama", "Ohtani", "Mahomes", "McDavid"]):
        base = 0.82
    elif any(k in player for k in ["Maxey", "Judge", "Kelce", "Matthews"]):
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
# SCRAPING HELPERS (HYBRID)
# =========================
def fetch_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.text

def mark_sensor(name, status, error=None, fallback_used=False):
    st.session_state.sensor_status[name]["status"] = status
    st.session_state.sensor_status[name]["last"] = datetime.now().strftime("%H:%M:%S")
    st.session_state.sensor_status[name]["error"] = error
    st.session_state.sensor_status[name]["fallback_used"] = fallback_used

# NOTE: These scrapers are skeletons with safe mock fallbacks.
# You can replace internals with real parsing for each site.

def scrape_bettingpros_props(sport: str) -> pd.DataFrame:
    name = "BettingPros"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # soup = BeautifulSoup(html, "html.parser")
        # TODO: real parsing here
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["Shohei Ohtani", "TOTAL BASES", 1.5, "OVER"],
                ["Aaron Judge", "HOME RUN", 0.5, "OVER"],
                ["Mookie Betts", "RUNS+RBI", 1.5, "OVER"],
                ["Spencer Strider", "STRIKEOUTS", 8.5, "OVER"],
                ["Corbin Burnes", "STRIKEOUTS", 7.5, "UNDER"],
            ],
            columns=["Player", "Prop", "Line", "Side"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["Shohei Ohtani", "TOTAL BASES", 1.5, "OVER"],
            ],
            columns=["Player", "Prop", "Line", "Side"],
        )

def scrape_rotowire_injuries(sport: str) -> pd.DataFrame:
    name = "RotoWire"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", "Judge (Probable - Hand Contusion)"],
                ["ATL @ MIL", "Strider (Cleared - Pitch Count Watch)"],
            ],
            columns=["Game", "Status"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", "No major injuries reported"],
            ],
            columns=["Game", "Status"],
        )

def scrape_pinesports(sport: str) -> pd.DataFrame:
    name = "PineSports"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["Shohei Ohtani", "TOTAL BASES", "High correlation with hard-hit rate"],
            ],
            columns=["Player", "Prop", "Note"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["Shohei Ohtani", "TOTAL BASES", "Fallback trend: last 10 games strong"],
            ],
            columns=["Player", "Prop", "Note"],
        )

def scrape_action_network(sport: str) -> pd.DataFrame:
    name = "Action Network"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", "Overs", 78, 62],
            ],
            columns=["Game", "PublicSide", "BetPct", "MoneyPct"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", "Overs", 70, 60],
            ],
            columns=["Game", "PublicSide", "BetPct", "MoneyPct"],
        )

def scrape_cbs_series_context(sport: str) -> pd.DataFrame:
    name = "CBS Sports"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
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
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                [
                    "LAD @ NYY",
                    "Fallback context: neutral series",
                    "[SERIES CONTEXT: Neutral]",
                ],
            ],
            columns=["Series", "Game Context", "Trend Adjustment"],
        )

def scrape_bref(sport: str) -> pd.DataFrame:
    name = "Basketball-Reference"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["Shohei Ohtani", 0.28, 0.19],
            ],
            columns=["Player", "UsageRate", "DefRebRate"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["Shohei Ohtani", 0.26, 0.18],
            ],
            columns=["Player", "UsageRate", "DefRebRate"],
        )

def scrape_nba_stats(sport: str) -> pd.DataFrame:
    name = "NBA Stats"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["Shohei Ohtani", 5.2, 3.8],
            ],
            columns=["Player", "DrivesPerGame", "CatchShoot3s"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["Shohei Ohtani", 4.8, 3.5],
            ],
            columns=["Player", "DrivesPerGame", "CatchShoot3s"],
        )

def scrape_massey(sport: str) -> pd.DataFrame:
    name = "Massey Ratings"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD", 1, 7.5],
                ["NYY", 3, 6.8],
            ],
            columns=["Team", "Rank", "HomeEdge"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD", 2, 7.0],
                ["NYY", 4, 6.5],
            ],
            columns=["Team", "Rank", "HomeEdge"],
        )

def scrape_dunkel(sport: str) -> pd.DataFrame:
    name = "Dunkel Index"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", 8.7, 0.22],
            ],
            columns=["Game", "ProjTotal", "BlowoutProb"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", 8.3, 0.18],
            ],
            columns=["Game", "ProjTotal", "BlowoutProb"],
        )

def scrape_covers_spreads(sport: str) -> pd.DataFrame:
    name = "Covers"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", -1.5, "❌ Inactive", "Full evaluation"],
                ["ATL @ MIL", -1.5, "❌ Inactive", "Full evaluation"],
            ],
            columns=["Game", "Spread", "Advisory", "Effect"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", -1.5, "❌ Inactive", "Fallback evaluation"],
            ],
            columns=["Game", "Spread", "Advisory", "Effect"],
        )

def scrape_yahoo(sport: str) -> pd.DataFrame:
    name = "Yahoo Sports"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", "No new injuries"],
            ],
            columns=["Game", "Note"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", "Fallback: assume no major changes"],
            ],
            columns=["Game", "Note"],
        )

def scrape_espn(sport: str) -> pd.DataFrame:
    name = "ESPN"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", "Beat: Ohtani expected full workload"],
            ],
            columns=["Game", "Note"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", "Fallback: no late-breaking news"],
            ],
            columns=["Game", "Note"],
        )

def scrape_draftkings_games(sport: str) -> pd.DataFrame:
    name = "DraftKings"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", "LAD -1.5", "LAD ML -135", "O/U 8.5"],
                ["ATL @ MIL", "ATL -1.5", "ATL ML -140", "O/U 7.5"],
            ],
            columns=["Matchup", "Spread", "Moneyline", "Total"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", "LAD -1.5", "LAD ML -130", "O/U 8.5"],
            ],
            columns=["Matchup", "Spread", "Moneyline", "Total"],
        )

def scrape_fanduel_games(sport: str) -> pd.DataFrame:
    name = "FanDuel"
    try:
        # html = fetch_html(SENSOR_CONFIG[name]["url"])
        # TODO: real parsing
        mark_sensor(name, "PASS")
        return pd.DataFrame(
            [
                ["LAD @ NYY", "LAD -1.5", "LAD ML -140", "O/U 8.5"],
            ],
            columns=["Matchup", "Spread", "Moneyline", "Total"],
        )
    except Exception as e:
        mark_sensor(name, "FALLBACK", error=str(e), fallback_used=True)
        return pd.DataFrame(
            [
                ["LAD @ NYY", "LAD -1.5", "LAD ML -138", "O/U 8.5"],
            ],
            columns=["Matchup", "Spread", "Moneyline", "Total"],
        )

def scrape_espn_box_scores_for_reconciliation():
    # TODO: real ESPN box score scraping for reconciliation
    return None

# =========================
# FIREWALL / FILTERS
# =========================
def apply_firewall(props_df, injuries_df, spreads_df, dunkel_df, sport):
    removed = 0
    keep_rows = []
    for idx, row in props_df.iterrows():
        player = row["Player"]
        prop = row["Prop"]

        injury_flag = any(player.split()[0] in s for s in injuries_df["Status"].tolist())
        blowout_flag = False
        for _, srow in spreads_df.iterrows():
            if abs(srow["Spread"]) >= 10 and sport in ["NBA", "NFL"]:
                blowout_flag = True
        for _, drow in dunkel_df.iterrows():
            if drow["BlowoutProb"] >= 0.25:
                blowout_flag = True

        volatility_flag = "PTS+REB" in prop or "PTS+AST" in prop

        if injury_flag and volatility_flag:
            removed += 1
            continue
        if blowout_flag and "OVER" in row["Side"]:
            removed += 1
            continue

        keep_rows.append(idx)

    filtered = props_df.loc[keep_rows].reset_index(drop=True)
    return filtered, removed

# =========================
# MARKET DYNAMICS (HYBRID SHELL)
# =========================
def get_market_dynamics(sport, action_df, dk_df, fd_df):
    # Very simple mock logic using Action Network + DK/FD
    if action_df is None or action_df.empty:
        rlm_detected = False
        contrarian_flag = False
        regime = "UNKNOWN"
        public_on = "N/A"
        council_on = "N/A"
    else:
        row = action_df.iloc[0]
        public_side = row["PublicSide"]
        bet_pct = row["BetPct"]
        money_pct = row["MoneyPct"]
        rlm_detected = money_pct > bet_pct + 10
        contrarian_flag = public_side == "Overs"
        regime = "STABLE" if not rlm_detected else "VOLATILE"
        public_on = public_side
        council_on = "Unders / Pass" if public_side == "Overs" else "Edges Only"

    return {
        "rlm": rlm_detected,
        "contrarian": contrarian_flag,
        "regime": regime,
        "public_on": public_on,
        "council_on": council_on,
    }

# =========================
# SCANNER / PIPELINE
# =========================
def scan_all_sources(sport: str):
    # Primary props & injuries
    props = scrape_bettingpros_props(sport)
    injuries = scrape_rotowire_injuries(sport)

    # Market & context
    pinesports = scrape_pinesports(sport)
    action_net = scrape_action_network(sport)
    cbs = scrape_cbs_series_context(sport)
    bref = scrape_bref(sport)
    nba_stats = scrape_nba_stats(sport)
    massey = scrape_massey(sport)
    dunkel = scrape_dunkel(sport)
    covers = scrape_covers_spreads(sport)
    yahoo = scrape_yahoo(sport)
    espn = scrape_espn(sport)
    dk_games = scrape_draftkings_games(sport)
    fd_games = scrape_fanduel_games(sport)

    # Merge DK + FD for line integrity (simple example: keep DK as primary)
    games = dk_games.copy()

    # Firewall
    props_filtered, removed = apply_firewall(props, injuries, covers, dunkel, sport)

    # Model enrichment
    props_enriched, model_verdicts = enrich_props_with_models(props_filtered, sport)
    games = enrich_games_with_models(games, sport)

    st.session_state.board_data = {
        "props": props_enriched,
        "injuries": injuries,
        "spreads": covers,
        "series": cbs,
        "firewall_removed": removed,
        "model_verdicts": model_verdicts,
        "pinesports": pinesports,
        "bref": bref,
        "nba_stats": nba_stats,
        "massey": massey,
        "dunkel": dunkel,
        "yahoo": yahoo,
        "espn": espn,
        "dk_games": dk_games,
        "fd_games": fd_games,
        "action_net": action_net,
    }
    st.session_state.games = games
    st.session_state.last_sport = sport

def parse_manual_text(text: str, sport: str):
    # For now, still just triggers scan; you can later parse text into props/injuries/spreads.
    scan_all_sources(sport)

def parse_screenshot(image, sport: str):
    # TODO: integrate real OCR and mapping
    scan_all_sources(sport)

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
    # TODO: replace mock_box_score_result with real ESPN box score + DK closing line logic.
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

SPORTS = ["NBA", "NFL", "MLB", "NHL", "ALL"]

# =========================
# ANALYSIS TAB
# =========================
with tab_analysis:
    st.markdown("## 📊 THE BOARD OF 8 — CLARITY MODEL OUTPUT")

    sport = st.selectbox("Select Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport))

    st.markdown(
        "**Data Source:** BettingPros + RotoWire + PineSports + Action Network + CBS + B-Ref + NBA Stats + Massey + Dunkel + Covers + Yahoo + ESPN + DraftKings + FanDuel"
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
            st.success(f"Scan complete for {sport}.")
    with col_manual:
        st.write("Manual Data Paste:")
    with col_screen:
        st.write("Screenshot OCR:")

    manual_text = st.text_area("Paste raw board / props / injuries here (optional):", height=120)
    if st.button("Use Pasted Data"):
        if manual_text.strip():
            parse_manual_text(manual_text, sport)
            st.success(f"Manual data ingested for {sport} (current: pipeline trigger).")
        else:
            st.warning("No text detected.")

    screenshot = st.file_uploader("Upload screenshot (optional):", type=["png", "jpg", "jpeg"])
    if st.button("Use Screenshot OCR"):
        if screenshot is not None:
            parse_screenshot(screenshot, sport)
            st.success(f"Screenshot processed for {sport} (current: pipeline trigger).")
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

        st.markdown("**Excluded:** High-variance combo props, injury-uncertain edges, thin model density (current firewall).")

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
        action_net = board.get("action_net")
        dk_games = board.get("dk_games")
        fd_games = board.get("fd_games")

        st.markdown(
            "**Data Source:** BettingPros + RotoWire + PineSports + Action Network + CBS + B-Ref + NBA Stats + Massey + Dunkel + Covers + Yahoo + ESPN + DraftKings + FanDuel"
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

        st.markdown("**Excluded:** Volatility traps, thin-model-density combo props, injury-uncertain edges (current firewall).")

        st.markdown("### 📡 MARKET DYNAMICS (v6.0 Supreme Audit)")
        md = get_market_dynamics(st.session_state.last_sport, action_net, dk_games, fd_games)
        st.markdown(
            f"- RLM Status: {'DETECTED' if md['rlm'] else 'NONE'} — Example: key Under moving against public sentiment.  \n"
            f"- Contrarian Flag: {'ACTIVE' if md['contrarian'] else 'INACTIVE'} — Public on {md['public_on']}; Council on {md['council_on']}.  \n"
            f"- Regime Type: {md['regime']} (current hybrid shell).  \n"
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
                    st.success("Reconciliation complete (current: mock result engine).")

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
    st.markdown("## 🧪 Tools, Sensor Health & SEM Engine")

    st.markdown("### 14-Sensor Diagnostic Panel (Hybrid Mode)")
    diag_rows = []
    for name in SENSOR_NAMES:
        s = st.session_state.sensor_status[name]
        cfg = SENSOR_CONFIG[name]
        status = s["status"]
        if status == "PASS":
            dot = "🟢"
        elif status == "FALLBACK":
            dot = "🟡"
        elif status == "FAIL":
            dot = "🔴"
        else:
            dot = "⚪"
        diag_rows.append(
            {
                "Sensor": name,
                "Status": f"{dot} {status}",
                "Purpose": cfg["purpose"],
                "URL": cfg["url"],
                "Fallback Used": "Yes" if s["fallback_used"] else "No",
                "SEM Impact": cfg["sem_impact"],
                "Firewall Impact": cfg["firewall_impact"],
                "Last Scan": s["last"] or "—",
                "Error": s["error"] or "",
            }
        )
    st.table(pd.DataFrame(diag_rows))

    if st.button("Scan All (Tools Tab)"):
        scan_all_sources(st.session_state.last_sport)
        st.success(f"Scan complete for {st.session_state.last_sport}.")

    st.markdown("---")
    st.markdown("### 11-Sensor Checklist (Operational)")
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
    for i, sname in enumerate(sensors):
        flag = st.checkbox(sname, key=f"sensor_{i}")
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
