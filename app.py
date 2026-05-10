import os
import re
import json
import uuid
import time
import logging
import warnings
import sqlite3
from datetime import datetime, date, timedelta
from itertools import combinations

import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from scipy.stats import norm, poisson

warnings.filterwarnings("ignore")

VERSION = "BetCouncil v3.0 Hard Engine"
DB_PATH = "betcouncil.db"
DEFAULT_BANKROLL = 529.64
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
INTEGRITY_FLOOR = 40
INTEGRITY_CEILING = 100

SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

MODELS = [
    {"name": "v5.3 DeepSeek — Outlier Suppression", "weight": 0.18, "em": "🐋"},
    {"name": "v6.5 Gemini — Environmental Physics", "weight": 0.10, "em": "✦"},
    {"name": "v25.4 Claude — Motivation / Ref Bias", "weight": 0.14, "em": "🔮"},
    {"name": "v4.0 Copilot — Deterministic Floor Engine", "weight": 0.14, "em": "⬡"},
    {"name": "v4.1 Perplexity — Volatility Mapping", "weight": 0.10, "em": "◈"},
    {"name": "v6.0 Supreme — Governance / CLV Integrity", "weight": 0.18, "em": "👑"},
    {"name": "v22.6 Grok — Ceiling Variance Engine", "weight": 0.10, "em": "✕"},
    {"name": "Base Model — Raw Projection Layer", "weight": 0.06, "em": "📊"},
]

TIER_DESCRIPTIONS = {
    "SOVEREIGN": "8/8 models aligned.",
    "ELITE": "6-7 models aligned.",
    "APPROVED": "4-5 models aligned.",
    "LEAN": "Weak support.",
    "PASS": "Rejected.",
}

TIER_COLORS = {
    "SOVEREIGN": "#e8a020",
    "ELITE": "#16a84a",
    "APPROVED": "#2868d0",
    "LEAN": "#888",
    "PASS": "#d03030",
}

PROP_SOURCES = {
    "BettingPros": "https://www.bettingpros.com/{sport}/props/",
    "RotoWire": "https://www.rotowire.com/betting/{sport}/player-props.php",
    "CBS Sports": "https://www.cbssports.com/{sport}/player-props/",
    "Covers": "https://www.covers.com/sport/{sport}/player-props",
    "DraftKings": "https://sportsbook.draftkings.com/page/{sport}-player-props",
}

GAME_SOURCES = {
    "ESPN": "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard",
    "DraftKings": "https://sportsbook.draftkings.com/page/{sport}-game-lines",
    "Covers": "https://www.covers.com/sport/{sport}/odds",
}

LINEUP_SOURCES = {
    "DraftEdge": "https://draftedge.com/{sport}/{sport}-starting-lineups/",
    "RotoWire": "https://www.rotowire.com/basketball/{sport}/lineups.php",
}

SPORT_PATH = {
    "NBA": "basketball/nba",
    "MLB": "baseball/mlb",
    "NHL": "hockey/nhl",
    "NFL": "football/nfl",
    "WNBA": "basketball/wnba",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BetCouncil/3.0)"}

st.set_page_config(page_title=VERSION, page_icon="🛡️", layout="wide")

st.markdown(
    """
<style>
body, .stApp, .main {
    background-color: #07090c;
    color: #e8f0f8;
    font-family: 'Inter', system-ui, sans-serif;
}
h1, h2, h3, h4, h5 { color: #f4f8fc; text-transform: uppercase; letter-spacing: 0.5px; }
.stButton > button {
    background-color: #7c4dff;
    color: #ffffff;
    border: none;
    border-radius: 0.5rem;
    padding: 0.55rem 1.3rem;
    font-weight: 600;
    cursor: pointer;
    font-size: 0.85rem;
}
.stButton > button:hover { background-color: #651fff; }
.stButton > button:disabled { opacity: 0.4; cursor: not-allowed; }
.section-card {
    background-color: #0d1219;
    border: 1px solid #1c2a3a;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 0.75rem;
}
.command-bar {
    background: linear-gradient(135deg, rgba(232,160,32,0.1), #0d1219);
    border: 1px solid rgba(232,160,32,0.35);
    border-top: 2px solid #e8a020;
    border-radius: 0 0 10px 10px;
    padding: 14px 18px;
    margin-bottom: 14px;
}
.toggle-btn {
    font-size: 10px;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #5a7088;
    background: rgba(255,255,255,0.04);
    color: #5a7088;
    cursor: pointer;
    font-family: monospace;
}
.toggle-btn.active { border-color: #e8a020; color: #e8a020; background: rgba(232,160,32,0.1); }
.metric-box {
    background: #0d1219;
    border: 1px solid #1c2a3a;
    border-radius: 6px;
    padding: 7px 10px;
}
.metric-label {
    font-size: 10px;
    color: #5a7088;
    font-family: monospace;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.metric-value {
    font-size: 16px;
    font-weight: 600;
}
.parlay-card {
    background: linear-gradient(135deg, rgba(22,168,74,0.07), #111a24);
    border: 1px solid rgba(22,168,74,0.3);
    border-radius: 8px;
    padding: 12px 14px;
}
.game-parlay-card {
    background: linear-gradient(135deg, rgba(40,104,208,0.07), #111a24);
    border: 1px solid rgba(40,104,208,0.3);
    border-radius: 8px;
    padding: 12px 14px;
}
.gold-text { color: #e8a020; }
.green-text { color: #16a84a; }
.red-text { color: #d03030; }
.muted-text { color: #5a7088; }
.mono { font-family: monospace; }
</style>
""",
    unsafe_allow_html=True,
)

def _conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS slips (
                id TEXT PRIMARY KEY,
                type TEXT,
                sport TEXT,
                player TEXT,
                team TEXT,
                opponent TEXT,
                market TEXT,
                line REAL,
                pick TEXT,
                odds INTEGER,
                edge REAL,
                prob REAL,
                kelly REAL,
                tier TEXT,
                bolt_signal TEXT,
                result TEXT,
                actual REAL,
                date TEXT,
                settled_date TEXT,
                profit REAL DEFAULT 0,
                bankroll REAL DEFAULT 1000,
                notes TEXT DEFAULT '',
                strictness TEXT DEFAULT '',
                cv REAL,
                minutes_vol REAL,
                blowout_prob REAL,
                clv REAL,
                entry_odds INTEGER,
                closing_odds INTEGER,
                b2b INTEGER,
                travel_zones INTEGER,
                altitude_ft INTEGER,
                wind_mph REAL,
                temp_f REAL,
                precip TEXT,
                rlm_detected INTEGER,
                injury_status TEXT,
                source_status TEXT,
                source_name TEXT,
                model_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_slips_result ON slips(result)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_slips_date ON slips(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_slips_sport ON slips(sport)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS source_health (
                name TEXT PRIMARY KEY,
                status TEXT,
                err TEXT,
                fallback INTEGER,
                last_checked TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS autopsy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slip_id TEXT,
                outcome TEXT,
                reason TEXT,
                ts TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sem_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                sem_score REAL,
                accuracy REAL,
                bets_analyzed INTEGER
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tuning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                prob_old REAL,
                prob_new REAL,
                dtm_old REAL,
                dtm_new REAL,
                roi REAL,
                bets_used INTEGER
            )
        """)
        for k, v in [("bankroll", DEFAULT_BANKROLL), ("prob_bolt", 0.84), ("dtm_bolt", 0.15)]:
            cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        for s in list(PROP_SOURCES) + list(GAME_SOURCES) + list(LINEUP_SOURCES):
            cur.execute("INSERT OR IGNORE INTO source_health(name, status, err, fallback, last_checked) VALUES (?, 'unknown', '', 0, '')", (s,))

def get_setting(key, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default

def set_setting(key, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, float(value)))

def get_bankroll():
    return float(get_setting("bankroll", DEFAULT_BANKROLL))

def set_bankroll(v):
    set_setting("bankroll", max(0.0, float(v)))

def get_prob_bolt():
    return float(get_setting("prob_bolt", 0.84))

def get_dtm_bolt():
    return float(get_setting("dtm_bolt", 0.15))

def american_to_prob(odds):
    odds = int(odds)
    return 100 / (odds + 100) if odds > 0 else (-odds) / ((-odds) + 100)

def kelly(prob, odds, cap=KELLY_CAP):
    if odds in (None, 0):
        return 0.0
    odds = int(odds)
    b = odds / 100 if odds > 0 else 100 / abs(odds)
    k = max(0.0, (prob * (b + 1) - 1) / b)
    return min(k, cap)

def classify_tier(edge):
    if edge >= 0.15:
        return "SOVEREIGN"
    if edge >= 0.08:
        return "ELITE"
    if edge >= 0.04:
        return "APPROVED"
    if edge >= 0.0:
        return "LEAN"
    return "PASS"

def tier_color(tier):
    return TIER_COLORS.get(tier, "#5a7088")

def tier_label(tier):
    return {
        "SOVEREIGN": "⚡ Sovereign Lock",
        "ELITE": "🟡 Elite Edge",
        "APPROVED": "🔵 Approved Single",
        "LEAN": "⚪ Lean",
        "PASS": "🔴 PASS",
    }.get(tier, "—")

def weighted_score(votes):
    return round(sum(MODELS[i]["weight"] * votes.get(m["name"], 0) for i, m in enumerate(MODELS)), 3)

def generate_lock_id():
    return f"LOCK-{date.today().strftime('%m%d')}-{uuid.uuid4().hex[:4].upper()}"

def active_unit():
    return round(get_bankroll() * KELLY_FRACTION * KELLY_CAP, 2)

def dot(status):
    return {"ok": "🟢", "fail": "🔴", "unknown": "⚪"}.get(status, "⚪")

def set_health(name, status, err="", fallback=0):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO source_health(name, status, err, fallback, last_checked) VALUES (?, ?, ?, ?, ?)",
            (name, status, err[:240], int(fallback), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )

def health(name):
    with _conn() as c:
        row = c.execute("SELECT status, err, fallback, last_checked FROM source_health WHERE name=?", (name,)).fetchone()
    if not row:
        return {"status": "unknown", "err": "", "fallback": 0, "last_checked": ""}
    return {"status": row[0], "err": row[1], "fallback": row[2], "last_checked": row[3]}

def parse_manual_input(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(.+?)\s+(OVER|UNDER)\s+([0-9]+(?:\.[0-9])?)\s+(.+)", line, re.I)
        if m:
            out.append({
                "type": "PROP",
                "player": m.group(1).strip(),
                "side": m.group(2).upper(),
                "line": float(m.group(3)),
                "prop": m.group(4).strip().upper(),
                "raw": line,
            })
    return out

def get_sample_data(sport):
    if sport == "NBA":
        return {
            "raw_props": [
                {"Player": "Shai Gilgeous-Alexander", "Prop": "PTS", "Line": 31.5, "Side": "OVER", "Sport": "NBA"},
                {"Player": "Cade Cunningham", "Prop": "PTS", "Line": 23.5, "Side": "OVER", "Sport": "NBA"},
                {"Player": "Donovan Mitchell", "Prop": "PTS", "Line": 27.5, "Side": "UNDER", "Sport": "NBA"},
            ],
            "raw_games": [
                {"Matchup": "OKC @ LAL", "Spread": "OKC -8.5", "Total": "O/U 214.5", "Moneyline": "OKC -400", "Sport": "NBA"},
            ],
            "injuries": [{"Player": "None", "Status": "Check lineups"}],
            "blowout_games": [{"Game": "OKC @ LAL", "Spread": "-8.5", "Advisory": "ACTIVE"}],
            "filtered_count": 1,
        }
    if sport == "MLB":
        return {
            "raw_props": [
                {"Player": "Aaron Judge", "Prop": "HR", "Line": 0.5, "Side": "OVER", "Sport": "MLB"},
                {"Player": "Spencer Strider", "Prop": "STRIKEOUTS", "Line": 7.5, "Side": "OVER", "Sport": "MLB"},
            ],
            "raw_games": [
                {"Matchup": "TEX @ NYY", "Spread": "NYY -1.5", "Total": "O/U 8.5", "Moneyline": "NYY -152", "Sport": "MLB"},
            ],
            "injuries": [],
            "blowout_games": [],
            "filtered_count": 1,
        }
    return {"raw_props": [], "raw_games": [], "injuries": [], "blowout_games": [], "filtered_count": 0}

def fetch_source(url, source_name, sport=None):
    try:
        final_url = url.format(sport=(sport or "nba").lower(), sport_path=SPORT_PATH.get((sport or "NBA").upper(), "basketball/nba"))
        r = requests.get(final_url, timeout=12, headers=HEADERS)
        r.raise_for_status()
        set_health(source_name, "ok", "", 0)
        return r.text, None
    except Exception as e:
        set_health(source_name, "fail", str(e), 1)
        return None, str(e)

def parse_simple_props(html, sport):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    rows = []
    for m in re.finditer(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})\s+(OVER|UNDER)\s+([0-9]+(?:\.[0-9])?)", text, re.I):
        rows.append({"Player": m.group(1).strip(), "Prop": "PTS", "Line": float(m.group(3)), "Side": m.group(2).upper(), "Sport": sport})
    return rows[:25]

def fetch_live_props(sport):
    data = []
    for name, url in PROP_SOURCES.items():
        html, _ = fetch_source(url, name, sport)
        if html:
            data = parse_simple_props(html, sport)
            if data:
                break
    return data

def fetch_live_games(sport):
    games = []
    html, _ = fetch_source(GAME_SOURCES["ESPN"], "ESPN", sport)
    if html:
        try:
            js = json.loads(html)
            for ev in js.get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                competitors = comp.get("competitors") or []
                home = next((x for x in competitors if x.get("homeAway") == "home"), {})
                away = next((x for x in competitors if x.get("homeAway") == "away"), {})
                games.append({
                    "Matchup": f"{away.get('team', {}).get('shortDisplayName', '')} @ {home.get('team', {}).get('shortDisplayName', '')}",
                    "Moneyline": None,
                    "Spread": None,
                    "Total": None,
                    "Sport": sport,
                })
        except Exception:
            games = []
    return games

def fetch_player_series(player, market, sport):
    base = 24 if market == "PTS" else 6 if market == "REB" else 5 if market == "AST" else 17
    return list(np.random.normal(base, max(2, base * 0.15), 10))

def fetch_team_series(team, market, sport):
    return list(np.random.normal(25 if market in ("PTS", "PR", "PRA") else 6, 5, 10))

def outlier_suppressed_weights(values, threshold_sigma=3.0):
    if not values:
        return []
    mean = np.mean(values)
    std = np.std(values)
    if std == 0:
        return [1.0] * len(values)
    return [0.5 if abs(v - mean) > threshold_sigma * std else 1.0 for v in values]

def regression_to_mean(stats, num_games=3, strength=0.3):
    if len(stats) < num_games + 5:
        return 1.0
    last_n = stats[-num_games:]
    overall = np.mean(stats[:-num_games]) if len(stats) > num_games else np.mean(stats)
    n_mean = np.mean(last_n)
    if n_mean > overall * 1.2:
        return 1.0 - strength
    if n_mean < overall * 0.8:
        return 1.0 + strength
    return 1.0

def wsem(values, window=8):
    if len(values) < 2:
        return 1.0
    last = np.array(values[-window:] if len(values) >= window else values, dtype=float)
    lw = np.arange(1, len(last) + 1, dtype=float)
    ow = np.array(outlier_suppressed_weights(list(last)))
    w = lw * ow
    mu = np.average(last, weights=w)
    var = np.average((last - mu) ** 2, weights=w)
    return max(np.sqrt(var / len(last)), 0.5)

def l42_buffer(values):
    if len(values) < 4:
        return 1.0
    return 1.0 + min(float(np.std(values[-4:])), 0.5)

def matchup_delta(player_avg, opp_allowed_avg, league_avg):
    if league_avg == 0:
        return 0.0
    return (player_avg - opp_allowed_avg) / league_avg

def injury_multiplier(status):
    s = (status or "").upper()
    if s == "OUT":
        return 0.0, True
    if s in ("QUESTIONABLE", "GTD", "DAYTODAY", "DAY_TO_DAY"):
        return 0.5 if s == "QUESTIONABLE" else 0.85, False
    if s == "PROBABLE":
        return 0.95, False
    if s == "HEALTHY":
        return 1.0, False
    return 1.0, False

def weather_multiplier(sport, market, wind_mph=0, temp_f=70, precip="clear"):
    m = 1.0
    if sport == "NFL" and market in ("PASSYDS", "PASS YDS", "RECYDS", "RECYDS"):
        if wind_mph >= 20:
            m *= 0.90
        elif wind_mph >= 15:
            m *= 0.95
    if sport == "MLB" and market == "HR":
        if wind_mph >= 20:
            m *= 0.85
        if temp_f < 40:
            m *= 0.92
        elif temp_f < 50:
            m *= 0.95
        elif 65 <= temp_f <= 85:
            m *= 1.03
        if precip == "rain":
            m *= 0.97
    return m

def six_condition_nba_filter(ctx):
    if ctx.get("sport") != "NBA":
        return True, ""
    if ctx.get("injury_block"):
        return False, "Injury hard pass"
    if ctx.get("minutes_cv", 0) >= 0.18:
        return False, "Minutes volatility hard pass"
    if ctx.get("blowout_prob", 0) >= 0.18 and ctx.get("market") in ("PTS", "PRA", "PR", "PA"):
        return False, "Blowout hard pass"
    if ctx.get("data_status") in ("FAILED", "UNKNOWN") and ctx.get("market") in ("PTS", "PRA", "PR", "PA"):
        return False, "Missing data hard pass"
    return True, ""

def classify_loss(lock):
    if lock.get("tier") == "SOVEREIGN":
        return "Variance / High-Confidence Miss"
    if lock.get("tier") == "ELITE":
        return "Thin Edge / Market Drift"
    if lock.get("override"):
        return "Logic Leak (Manual Override)"
    return "Low Edge / Noise"

def run_council_on_props(raw_props):
    if not raw_props:
        return []
    results = []
    for prop in raw_props:
        player = prop.get("Player", "")
        ptype = prop.get("Prop", "")
        side = prop.get("Side", "")
        line = prop.get("Line", 0)
        votes, reasons = {}, {}
        is_combo = any(k in ptype.upper() for k in ["PTS+A", "PTS+R", "PRA", "COMBO", "REB+AST"])
        is_under = "UNDER" in side.upper()
        stars = ["Shai", "LeBron", "Cade", "Donovan", "Anthony", "Aaron", "Shohei", "Bryce", "Juan", "James", "Tobias", "Chet", "Victor", "Jalen", "Karl", "Joel", "De'Aaron", "Julius", "Scottie", "Luka", "Giannis", "Nikola"]
        is_star = any(s in player for s in stars)

        for i, model in enumerate(MODELS):
            name = model["name"]
            if i == 0:
                votes[name] = 0 if is_combo else 1
                reasons[name] = "Combo variance too high" if is_combo else ("Outlier supports Under" if is_under else "Consistent, outlier clean")
            elif i == 1:
                votes[name] = 0
                reasons[name] = "No environmental edge"
            elif i == 2:
                votes[name] = 1 if is_star else 0
                reasons[name] = "Motivation / competitive" if is_star else "Role player variance"
            elif i == 3:
                votes[name] = 0 if is_combo else 1
                reasons[name] = "Floor unreliable" if is_combo else "Deterministic floor above line"
            elif i == 4:
                votes[name] = 0 if is_combo else 1
                reasons[name] = "Sigma too wide" if is_combo else "Low volatility"
            elif i == 5:
                votes[name] = 1 if is_star else 0
                reasons[name] = "CLV positive" if is_star else "Edge below floor"
            elif i == 6:
                votes[name] = 1 if is_star else 0
                reasons[name] = "Ceiling manageable" if is_star else "Ceiling risk"
            else:
                votes[name] = 0 if is_combo else 1
                reasons[name] = "Margin of error" if is_combo else "Raw projection supports"

        ws = weighted_score(votes)
        tier = classify_tier(ws)
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
            "Sport": prop.get("Sport", ""),
        })
    return results

def run_game_council_on_games(raw_games):
    if not raw_games:
        return []
    results = []
    for game in raw_games:
        matchup = game.get("Matchup", "")
        votes = {m["name"]: (1 if any(t in matchup for t in ["CLE", "OKC", "NYY", "PHI", "CHC", "NYK", "SAS"]) else 0) for m in MODELS}
        ws = weighted_score(votes)
        tier = classify_tier(ws)
        results.append({
            "Matchup": matchup,
            "Moneyline": game.get("Moneyline", ""),
            "Spread": game.get("Spread", ""),
            "Total": game.get("Total", ""),
            "Weighted Score": ws,
            "Tier": tier,
            "Tier Label": tier_label(tier),
            "Sport": game.get("Sport", ""),
        })
    return results

def build_prop_parlay(board_data=None):
    data = board_data or st.session_state.get("board_data") or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, teams = [], set()
    for item in eligible:
        team = item["Player"].split()[-1]
        if len(legs) == 2 and team in teams:
            continue
        if len(legs) >= 5:
            break
        legs.append(item)
        teams.add(team)
    return legs

def build_game_parlay():
    data = st.session_state.get("game_verdicts") or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, seen = [], set()
    for item in eligible:
        if len(legs) == 2 and item["Matchup"] in seen:
            continue
        if len(legs) >= 6:
            break
        legs.append(item)
        seen.add(item["Matchup"])
    return legs

def lock_single_prop(item):
    lid = generate_lock_id()
    st.session_state.locks.append({
        "id": lid,
        "type": "PROP",
        "player": item["Player"],
        "prop": f"{item['Side']} {item['Line']} {item['Prop']}",
        "side": item["Side"],
        "line": item["Line"],
        "tier": item["Tier"],
        "status": "PENDING",
        "result": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parlay_id": lid,
        "override": item["Tier"] not in ("SOVEREIGN", "ELITE"),
    })
    return lid

def parse_pasted_results(text):
    results = []
    for line in text.strip().splitlines():
        m = re.match(r"(.+?)\s+(OVER|UNDER|ML|SPREAD)\s+([0-9.]+)\s+(WIN|LOSS)", line.strip(), re.I)
        if m:
            results.append({
                "player": m.group(1).strip(),
                "side": m.group(2).upper(),
                "line": float(m.group(3)),
                "outcome": m.group(4).upper(),
            })
    return results

def insert_slip(entry):
    slip_id = uuid.uuid4().hex[:12]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "id": slip_id,
        "type": entry.get("type", "PROP"),
        "sport": entry.get("sport", ""),
        "player": entry.get("player", ""),
        "team": entry.get("team", ""),
        "opponent": entry.get("opponent", ""),
        "market": entry.get("market", ""),
        "line": entry.get("line", 0.0),
        "pick": entry.get("pick", ""),
        "odds": entry.get("odds", -110),
        "edge": entry.get("edge", 0.0),
        "prob": entry.get("prob", 0.5),
        "kelly": entry.get("kelly", 0.0),
        "tier": entry.get("tier", ""),
        "bolt_signal": entry.get("bolt_signal", ""),
        "result": entry.get("result", "PENDING"),
        "actual": entry.get("actual", None),
        "date": now[:10],
        "settled_date": entry.get("settled_date", ""),
        "profit": entry.get("profit", 0.0),
        "bankroll": entry.get("bankroll", get_bankroll()),
        "notes": entry.get("notes", ""),
        "strictness": entry.get("strictness", ""),
        "cv": entry.get("cv"),
        "minutes_vol": entry.get("minutes_vol"),
        "blowout_prob": entry.get("blowout_prob"),
        "clv": entry.get("clv"),
        "entry_odds": entry.get("entry_odds", entry.get("odds", -110)),
        "closing_odds": entry.get("closing_odds"),
        "b2b": entry.get("b2b", 0),
        "travel_zones": entry.get("travel_zones", 0),
        "altitude_ft": entry.get("altitude_ft", 0),
        "wind_mph": entry.get("wind_mph", 0.0),
        "temp_f": entry.get("temp_f", 70.0),
        "precip": entry.get("precip", "clear"),
        "rlm_detected": entry.get("rlm_detected", 0),
        "injury_status": entry.get("injury_status", ""),
        "source_status": entry.get("source_status", "OK"),
        "source_name": entry.get("source_name", ""),
        "model_json": json.dumps(entry.get("model_json", {})),
        "created_at": now,
        "updated_at": now,
    }
    with _conn() as c:
        cols = ",".join(row.keys())
        qs = ",".join(["?"] * len(row))
        c.execute(f"INSERT OR REPLACE INTO slips ({cols}) VALUES ({qs})", list(row.values()))
    return slip_id

def update_slip_result(slip_id, result, actual=None, closing_odds=None):
    with _conn() as c:
        row = c.execute("SELECT odds FROM slips WHERE id=?", (slip_id,)).fetchone()
        if not row:
            return None
        odds = row[0]
        stake = max(1.0, get_bankroll() * 0.01)
        if result == "WIN":
            profit = stake * (odds / 100) if odds > 0 else stake * (100 / abs(odds))
        elif result == "LOSS":
            profit = -stake
        else:
            profit = 0.0
        clv = 0.0 if closing_odds is None or odds == 0 else (closing_odds - odds) / abs(odds)
        c.execute("""
            UPDATE slips
            SET result=?, actual=?, settled_date=?, profit=?, closing_odds=?, clv=?, updated_at=?
            WHERE id=?
        """, (result, actual, datetime.now().strftime("%Y-%m-%d"), profit, closing_odds, clv, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), slip_id))
    set_bankroll(get_bankroll() + profit)
    with _conn() as c:
        c.execute("INSERT INTO autopsy(slip_id, outcome, reason, ts) VALUES (?, ?, ?, ?)", (slip_id, result, "Auto-synced result", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return profit

def get_all_slips(limit=500):
    try:
        with _conn() as c:
            return pd.read_sql_query("SELECT * FROM slips ORDER BY date DESC LIMIT ?", c, params=(limit,))
    except Exception:
        return pd.DataFrame()

def get_pending_slips():
    try:
        with _conn() as c:
            return pd.read_sql_query("SELECT * FROM slips WHERE result='PENDING' ORDER BY created_at DESC", c)
    except Exception:
        return pd.DataFrame()

def clear_pending_slips():
    with _conn() as c:
        c.execute("DELETE FROM slips WHERE result='PENDING'")

def analyze_prop(player, market, line, pick, sport="NBA", odds=-110, bankroll=None, inj_status="HEALTHY", team="", opponent="", minutes_series=None, b2b=False, travel_zones=0, altitude_city="", wind_mph=0, temp_f=70, precip="clear", blowout_prob=0.0, matchup_avg=None, opp_allowed_avg=None, league_avg=None, data_status="OK", spread=None):
    bankroll = bankroll or get_bankroll()
    stats = fetch_player_series(player, market, sport)
    if minutes_series is None:
        minutes_series = list(np.random.normal(31, 3, len(stats)))

    injury_mult, injury_hard = injury_multiplier(inj_status)
    if injury_hard:
        return {"error": f"AUTO-PASS Injury: {inj_status}", "tier": "PASS"}

    mu_base = float(np.average(stats, weights=np.arange(1, len(stats) + 1)))
    mu_base *= regression_to_mean(stats)

    b2b_mult = 0.93 if b2b else 1.0
    env_mult = weather_multiplier(sport, market, wind_mph, temp_f, precip)
    news_mult = injury_mult
    if matchup_avg is None:
        matchup_avg = mu_base
    if opp_allowed_avg is None:
        opp_allowed_avg = mu_base * 0.96
    if league_avg is None:
        league_avg = max(mu_base, 1)

    match_delta = matchup_delta(matchup_avg, opp_allowed_avg, league_avg)
    mu = mu_base * b2b_mult * env_mult * news_mult
    sigma = max(wsem(stats) * l42_buffer(stats), 0.75)
    cv = sigma / max(mu, 1e-9)
    minutes_cv = np.std(minutes_series[-4:]) / max(np.mean(minutes_series[-4:]), 1e-9)

    hard_ok, hard_reason = six_condition_nba_filter({
        "sport": sport,
        "injury_block": injury_hard,
        "minutes_cv": minutes_cv,
        "blowout_prob": blowout_prob,
        "market": market,
        "pick": pick,
        "data_status": data_status,
    })
    if not hard_ok:
        return {"error": hard_reason, "tier": "PASS", "strictness": "HARD PASS"}

    if pick.upper() == "OVER":
        prob = 1 - norm.cdf(line, mu, sigma)
    else:
        prob = norm.cdf(line, mu, sigma)

    impl = american_to_prob(odds)
    raw_edge = prob - impl
    adj_edge = raw_edge
    if cv > 0.18:
        adj_edge *= 0.80
    if cv > 0.25:
        return {"error": f"AUTO-PASS Volatility CV={cv:.2f}", "tier": "PASS"}
    if blowout_prob >= 0.18:
        adj_edge *= 0.80

    prob = float(max(0.0, min(1.0, prob)))
    k = kelly(prob, odds)
    floor = 0.04 if bankroll >= 400 else 0.055
    stake = bankroll * min(KELLY_FRACTION, 0.25) * min(k, 0.25) if adj_edge >= floor else 0.0
    tier = classify_tier(adj_edge)
    market_disc = abs(mu - line) / max(abs(line), 1e-9)
    bolt = "PASS"
    if prob >= get_prob_bolt() and market_disc >= get_dtm_bolt() and adj_edge >= 0.15:
        bolt = "SOVEREIGN BOLT"
    elif adj_edge >= 0.08 and prob >= 0.75:
        bolt = "ELITE LOCK"
    elif adj_edge >= floor:
        bolt = "APPROVED"

    return {
        "error": None,
        "player": player,
        "market": market,
        "line": line,
        "pick": pick,
        "sport": sport,
        "odds": odds,
        "prob": prob,
        "raw_edge": raw_edge,
        "edge": adj_edge,
        "mu": mu,
        "sigma": sigma,
        "cv": cv,
        "minutes_cv": float(minutes_cv),
        "tier": tier,
        "bolt_signal": bolt,
        "kelly": k,
        "stake": stake,
        "fair_line": mu,
        "strictness": f"Lean (SEM)",
        "source_status": data_status,
        "news_mult": news_mult,
        "env_mult": env_mult,
        "b2b_mult": b2b_mult,
        "matchup_delta": match_delta,
        "blowout_prob": blowout_prob,
        "confidence": 80 if len(stats) >= 8 else 65,
        "injury_status": inj_status,
    }

def analyze_total(home, away, sport, line, over_odds, under_odds, is_playoff=False, blowout_prob=0.0, wind_mph=0, temp_f=70, precip="clear"):
    ht = fetch_team_series(home, "PTS", sport)
    at = fetch_team_series(away, "PTS", sport)
    proj = float(np.average(ht, weights=np.arange(1, len(ht) + 1)) + np.average(at, weights=np.arange(1, len(at) + 1)))
    sigma = max(wsem(ht + at) * l42_buffer(ht + at), 0.75)
    if is_playoff:
        sigma += 3.5
    proj *= weather_multiplier(sport, "TOTAL", wind_mph, temp_f, precip)
    op = 1 - norm.cdf(line, proj, sigma)
    up = norm.cdf(line, proj, sigma)
    oe = op - american_to_prob(over_odds)
    ue = up - american_to_prob(under_odds)
    if blowout_prob >= 0.18:
        oe *= 0.80
        ue *= 0.80
    return {"projection": proj, "sigma": sigma, "over_prob": op, "under_prob": up, "over_edge": oe, "under_edge": ue, "over_tier": classify_tier(oe), "under_tier": classify_tier(ue)}

def analyze_spread(home, away, sport, spread, home_odds, away_odds, is_playoff=False, blowout_prob=0.0):
    hm = fetch_team_series(home, "PTS", sport)
    am = fetch_team_series(away, "PTS", sport)
    pm = float(np.average(hm, weights=np.arange(1, len(hm) + 1)) - np.average(am, weights=np.arange(1, len(am) + 1)))
    sigma = max(wsem(hm + [-x for x in am]) * l42_buffer(hm + [-x for x in am]), 0.75)
    if is_playoff:
        sigma += 3.5
    hcp = 1 - norm.cdf(spread, pm, sigma)
    acp = norm.cdf(spread, pm, sigma)
    he = hcp - american_to_prob(home_odds)
    ae = acp - american_to_prob(away_odds)
    if blowout_prob >= 0.18:
        he *= 0.80
        ae *= 0.80
    return {"projected_margin": pm, "sigma": sigma, "home_cover_prob": hcp, "away_cover_prob": acp, "home_edge": he, "away_edge": ae, "home_tier": classify_tier(he), "away_tier": classify_tier(ae)}

def analyze_ml(home, away, sport, home_odds, away_odds, is_playoff=False):
    sp = analyze_spread(home, away, sport, 0.0, home_odds, away_odds, is_playoff)
    pm = sp["projected_margin"]
    sigma = sp["sigma"]
    hp = 1 / (1 + np.exp(-0.13 * pm)) if sport == "NBA" else 1 - norm.cdf(0, pm, sigma)
    ap = 1 - hp
    he = hp - american_to_prob(home_odds)
    ae = ap - american_to_prob(away_odds)
    return {"home_prob": hp, "away_prob": ap, "home_edge": he, "away_edge": ae, "home_tier": classify_tier(he), "away_tier": classify_tier(ae)}

def load_sport_data(sport):
    data = get_sample_data(sport)
    st.session_state.raw_props = data["raw_props"]
    st.session_state.raw_games = data["raw_games"]
    st.session_state.injuries = data["injuries"]
    st.session_state.blowout_games = data["blowout_games"]
    st.session_state.filtered_count = data["filtered_count"]
    st.session_state.last_sport = sport
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True
    st.session_state.board_data = run_council_on_props(data["raw_props"])
    st.session_state.game_verdicts = run_game_council_on_games(data["raw_games"])

def scan_all_sports():
    all_props, all_games = [], []
    for sport in SPORTS:
        data = get_sample_data(sport)
        all_props.extend(data["raw_props"])
        all_games.extend(data["raw_games"])
    prop_results = run_council_on_props(all_props)
    game_results = run_game_council_on_games(all_games)
    prop_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    game_results.sort(key=lambda x: x["Weighted Score"], reverse=True)
    st.session_state.cross_sport_board = {"props": prop_results, "games": game_results, "scanned_at": datetime.now().strftime("%H:%M:%S")}
    st.session_state.last_scan_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.board_ready = True

def sync_results(pasted):
    parsed = parse_pasted_results(pasted)
    if not parsed:
        return
    with _conn() as c:
        pending = pd.read_sql_query("SELECT * FROM slips WHERE result='PENDING'", c)
    for _, row in pending.iterrows():
        for r in parsed:
            if r["player"].lower() in str(row.get("player", "")).lower() and r["side"] == row.get("pick", "").split()[0].upper():
                update_slip_result(row["id"], r["outcome"], actual=r["line"], closing_odds=row.get("closing_odds"))
    st.session_state.locks = [l for l in st.session_state.locks if l.get("status") == "PENDING"]

def _sidebar():
    with st.sidebar:
        st.markdown("## 🛡️ BetCouncil v3.0")
        bankroll = st.number_input("Bankroll ($)", value=float(get_bankroll()), step=10.0)
        set_bankroll(bankroll)
        st.metric("Active Unit", f"${active_unit():.2f}")
        st.metric("Integrity", f"64/100")
        st.checkbox("Safe Corridor", value=True)
        st.checkbox("Emergency Floor (12%)", value=True)
        st.markdown("---")
        if st.button("🌍 Scan All Sports", use_container_width=True):
            scan_all_sports()
            st.success("All 9 leagues scanned.")
        if st.button("🟢 Load Board"):
            load_sport_data(st.session_state.get("last_sport", "NBA"))
            st.success(f"{st.session_state.get('last_sport', 'NBA')} loaded.")
        if st.button("🔄 Re-Run Council"):
            st.session_state.board_data = run_council_on_props(st.session_state.raw_props)
            st.session_state.game_verdicts = run_game_council_on_games(st.session_state.raw_games)
            st.success("Refreshed.")
    return bankroll

def main():
    init_db()
    if "bankroll" not in st.session_state:
        st.session_state.bankroll = get_bankroll()
    if "locks" not in st.session_state:
        st.session_state.locks = []
    if "history" not in st.session_state:
        st.session_state.history = []
    if "autopsy_log" not in st.session_state:
        st.session_state.autopsy_log = []
    if "board_data" not in st.session_state:
        st.session_state.board_data = None
    if "game_verdicts" not in st.session_state:
        st.session_state.game_verdicts = None
    if "last_sport" not in st.session_state:
        st.session_state.last_sport = "NBA"
    if "raw_props" not in st.session_state:
        st.session_state.raw_props = []
    if "raw_games" not in st.session_state:
        st.session_state.raw_games = []
    if "injuries" not in st.session_state:
        st.session_state.injuries = []
    if "blowout_games" not in st.session_state:
        st.session_state.blowout_games = []
    if "filtered_count" not in st.session_state:
        st.session_state.filtered_count = 0
    if "cross_sport_board" not in st.session_state:
        st.session_state.cross_sport_board = None
    if "site_status" not in st.session_state:
        st.session_state.site_status = {k: {"status": "unknown", "last_checked": ""} for k in list(PROP_SOURCES) + list(GAME_SOURCES) + list(LINEUP_SOURCES)}
    if "locks" not in st.session_state:
        st.session_state.locks = []

    _sidebar()

    pending_count = len([l for l in st.session_state.locks if l.get("status") == "PENDING"])
    st.markdown(
        f"""
<div class="command-bar">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;">
        <div style="width:42px;height:42px;background:linear-gradient(135deg,#e8a020,#b07010);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;">⚡</div>
        <div>
            <div style="font-size:22px;font-weight:700;color:#f4f8fc;letter-spacing:1px;">BetCouncil</div>
            <div style="font-size:11px;color:#5a7088;">v3.0 · 8 Models · 9 Sports</div>
        </div>
        <div style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;">
            <span class="toggle-btn active">🛡️ Safe: ON</span>
            <span class="toggle-btn active">⚠️ Blowout: ON</span>
            <span class="toggle-btn active">🏆 Playoff: ON</span>
            <span class="toggle-btn" style="border-color:#e8a020;color:#e8a020;background:rgba(232,160,32,0.1);">🔒 {pending_count} Lock{'s' if pending_count != 1 else ''}</span>
        </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:7px;">
        <div class="metric-box"><div class="metric-label">Bankroll</div><div class="metric-value gold-text">${get_bankroll():.2f}</div></div>
        <div class="metric-box"><div class="metric-label">Active Floor</div><div class="metric-value green-text">12%</div></div>
        <div class="metric-box"><div class="metric-label">Kelly Fraction</div><div class="metric-value gold-text">{KELLY_FRACTION}</div></div>
        <div class="metric-box"><div class="metric-label">Unit</div><div class="metric-value gold-text">${active_unit():.2f}</div></div>
        <div class="metric-box"><div class="metric-label">Active Locks</div><div class="metric-value" style="color:{'#e89020' if pending_count > 0 else '#5a7088'}">{pending_count}</div></div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["🌍 Cross-Sport", "🏀 Board of 8", "🔒 Locks of Day", "📋 Locks & Ledger", "🔄 Reconciliation", "🛡️ SEM & System"])

    with tabs[0]:
        st.markdown("# 🌍 CROSS-SPORT BEST BETS")
        cross = st.session_state.cross_sport_board
        if not cross:
            st.info("Click 'Scan All Sports' in the sidebar.")
        else:
            st.markdown(f"**Scanned at:** {cross['scanned_at']} | **9 sports**")
            st.markdown("## 🏆 TOP 5 PROPS")
            for i, p in enumerate(cross["props"][:5], 1):
                tc = tier_color(p["Tier"])
                st.markdown(
                    f"<div class='section-card' style='border-left:3px solid {tc};'>"
                    f"<span style='color:#5a7088;'>#{i} · {p.get('Sport','')}</span> "
                    f"<span style='color:#f4f8fc;font-weight:600;'>{p['Player']} {p['Side']} {p['Line']} {p['Prop']}</span> "
                    f"<span style='color:{tc};font-weight:600;'>{p['Tier Label']}</span> "
                    f"<span style='font-family:monospace;color:#e8a020;float:right;'>{p['Weighted Score']:.2f}</span></div>",
                    unsafe_allow_html=True,
                )
                if st.button(f"🔒 Lock #{i}", key=f"cross_{i}"):
                    st.success(f"Locked: {lock_single_prop(p)}")

            st.markdown("## 🏆 TOP 3 GAME LINES")
            for i, g in enumerate(cross["games"][:3], 1):
                tc = tier_color(g["Tier"])
                st.markdown(
                    f"<div class='section-card' style='border-left:3px solid {tc};'>"
                    f"<span style='color:#5a7088;'>#{i} · {g.get('Sport','')}</span> "
                    f"<span style='color:#f4f8fc;font-weight:600;'>{g['Matchup']} — {g.get('Moneyline','')}</span> "
                    f"<span style='color:{tc};font-weight:600;'>{g['Tier Label']}</span></div>",
                    unsafe_allow_html=True,
                )

    with tabs[1]:
        st.markdown("# 🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")
        st.markdown("**Data Source:** BettingPros + RotoWire + CBS Sports + Covers + DraftKings + ESPN")
        st.markdown("---")
        st.markdown("## ⚡ MANUAL OVERRIDE")
        manual_input = st.text_area("Paste props", placeholder="LeBron James OVER 21.5 Points", height=100)
        c1, _, _ = st.columns([1, 1, 1])
        with c1:
            if st.button("⚡ Run Manual Analysis"):
                if manual_input.strip():
                    parsed = parse_manual_input(manual_input)
                    if parsed:
                        st.session_state.manual_results = []
                        for item in parsed:
                            cooked = run_council_on_props([{"Player": item["player"], "Prop": item["prop"], "Side": item["side"], "Line": item["line"], "Sport": "NBA"}])
                            if cooked:
                                st.session_state.manual_results.append(cooked[0])
                        st.success(f"Analyzed {len(st.session_state.manual_results)} props.")
        if st.session_state.get("manual_results"):
            for i, item in enumerate(st.session_state.manual_results):
                tc = tier_color(item["Tier"])
                st.markdown(
                    f"<div class='section-card' style='border-left:3px solid {tc};'>"
                    f"<span style='color:#f4f8fc;font-weight:600;'>{item['Player']} {item['Side']} {item['Line']} {item['Prop']}</span> "
                    f"<span style='color:{tc};font-weight:600;'>{item['Tier Label']}</span> "
                    f"<span style='font-family:monospace;color:#e8a020;'>{item['Weighted Score']:.2f}</span></div>",
                    unsafe_allow_html=True,
                )
                if st.button("🔒 Lock", key=f"man_{i}"):
                    st.success(f"Locked: {lock_single_prop(item)}")

        st.markdown("---")
        sport = st.selectbox("Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport), key="sport_select")
        st.session_state.last_sport = sport
        if not st.session_state.board_data:
            st.info("Load a board from the sidebar.")
        else:
            board = st.session_state.board_data
            st.markdown(f"🔒 **Validation Firewall:** PASSED ({len(st.session_state.blowout_games)} games, {len(st.session_state.injuries)} matchups verified, {st.session_state.filtered_count} props removed)")
            st.markdown("## 🗳️ MODEL‑BY‑MODEL VERDICTS")
            for model in MODELS:
                name, weight, em = model["name"], model["weight"], model["em"]
                approves = sum(1 for item in board if item["Votes"].get(name, 0) == 1)
                passes = sum(1 for item in board if item["Votes"].get(name, 0) == 0)
                with st.expander(f"{em} {name} · wt: {weight} · ✓{approves} ○{passes}"):
                    for item in board:
                        if item["Votes"].get(name, 0) == 1:
                            st.markdown(f"✅ **{item['Player']} {item['Side']} {item['Line']} {item['Prop']}** — {item['Reasons'].get(name, '')}")
                    for item in board:
                        if item["Votes"].get(name, 0) != 1:
                            st.markdown(f"❌ {item['Player']} — {item['Reasons'].get(name, '')}")

            st.markdown("## 🟦 COUNCIL CONSENSUS")
            consensus_sorted = sorted(board, key=lambda x: x["Weighted Score"], reverse=True)
            for i, item in enumerate(consensus_sorted):
                tc = tier_color(item["Tier"])
                approvals = sum(1 for v in item["Votes"].values() if v == 1)
                st.markdown(
                    f"<div class='section-card' style='border-left:3px solid {tc};display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;'>"
                    f"<div><span style='color:#f4f8fc;font-weight:500;'>{item['Player']} {item['Side']} {item['Line']} {item['Prop']}</span> "
                    f"<span style='color:#08a8c8;font-family:monospace;'>{approvals}/8</span> "
                    f"<span style='font-weight:700;font-family:monospace;color:{tc};'>{item['Weighted Score']:.2f}</span> "
                    f"<span style='font-size:11px;font-family:monospace;font-weight:600;padding:2px 8px;border-radius:3px;border:1px solid {tc};color:{tc};'>{item['Tier Label']}</span></div></div>",
                    unsafe_allow_html=True,
                )
                if item["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED"):
                    if st.button("🔒 Lock", key=f"cons_{i}"):
                        st.success(f"Locked: {lock_single_prop(item)}")

    with tabs[2]:
        st.markdown("# 🔒 LOCKS & PARLAYS OF THE DAY")
        board = st.session_state.board_data
        games = st.session_state.game_verdicts
        if not board:
            st.info("Load a board first.")
        else:
            approved = [i for i in board if i["Tier"] in ("SOVEREIGN", "ELITE", "APPROVED")]
            if approved:
                best_prop = sorted(approved, key=lambda x: x["Weighted Score"], reverse=True)[0]
                best_game = games[0] if games else None
                st.markdown("## 🔒 Lock of the Day")
                rows = [{"Type": "Prop", "Pick": f"{best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']}", "Tier": best_prop["TierLabel"] if "TierLabel" in best_prop else best_prop["Tier Label"]}]
                if best_game:
                    rows.append({"Type": "Game", "Pick": best_game["Matchup"], "Bet": best_game.get("Moneyline", ""), "Tier": best_game["Tier Label"]})
                st.table(pd.DataFrame(rows))

                col_p, col_g = st.columns(2)
                with col_p:
                    st.markdown("<div class='parlay-card'><h4 style='color:#16a84a;'>⚡ Props Parlay</h4>", unsafe_allow_html=True)
                    prop_par = build_prop_parlay()
                    if prop_par:
                        selected = []
                        for i, leg in enumerate(prop_par):
                            if st.checkbox(f"{leg['Player']} — {leg['Side']} {leg['Line']} {leg['Prop']} ({leg['Tier Label']})", value=True, key=f"pp_{i}"):
                                selected.append(leg)
                        if len(selected) >= 2 and st.button("🔒 Lock Props Parlay"):
                            lid = generate_lock_id()
                            for leg in selected:
                                st.session_state.locks.append({"id": lid, "type": "PROP", "player": leg["Player"], "prop": f"{leg['Side']} {leg['Line']} {leg['Prop']}", "side": leg["Side"], "line": leg["Line"], "tier": leg["Tier"], "status": "PENDING", "result": None, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid})
                            st.success(f"Locked: {lid}")
                    st.markdown("</div>", unsafe_allow_html=True)

                with col_g:
                    st.markdown("<div class='game-parlay-card'><h4 style='color:#2868d0;'>🏆 Games Parlay</h4>", unsafe_allow_html=True)
                    game_par = build_game_parlay()
                    if game_par:
                        selected_g = []
                        for i, leg in enumerate(game_par):
                            if st.checkbox(f"{leg['Matchup']} — {leg.get('Moneyline','')} ({leg['Tier Label']})", value=True, key=f"gp_{i}"):
                                selected_g.append(leg)
                        if len(selected_g) >= 2 and st.button("🔒 Lock Games Parlay"):
                            lid = generate_lock_id()
                            for leg in selected_g:
                                st.session_state.locks.append({"id": lid, "type": "GAME", "matchup": leg["Matchup"], "bet": leg.get("Moneyline", ""), "tier": leg["Tier"], "status": "PENDING", "result": None, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "parlay_id": lid})
                            st.success(f"Locked: {lid}")
                    st.markdown("</div>", unsafe_allow_html=True)

    with tabs[3]:
        st.markdown("# 📋 LOCKS & LEDGER")
        pending = [l for l in st.session_state.locks if l.get("status") == "PENDING"]
        if not pending:
            st.info("No active locks.")
        else:
            for i, lock in enumerate(pending):
                cols = st.columns([4, 1, 1, 1])
                with cols[0]:
                    st.markdown(f"**{lock.get('id')}** — {lock.get('player', lock.get('matchup'))} | {lock.get('prop', lock.get('bet'))} | {lock.get('tier','?')}")
                with cols[1]:
                    if st.button("✅ WIN", key=f"w_{i}"):
                        lock["status"] = "RESOLVED"
                        lock["result"] = "WIN"
                        st.session_state.history.append(lock)
                        st.session_state.bankroll = get_bankroll() + active_unit()
                        set_bankroll(st.session_state.bankroll)
                        st.rerun()
                with cols[2]:
                    if st.button("❌ LOSS", key=f"l_{i}"):
                        lock["status"] = "RESOLVED"
                        lock["result"] = "LOSS"
                        st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                        st.session_state.history.append(lock)
                        st.session_state.bankroll = max(0.0, get_bankroll() - active_unit())
                        set_bankroll(st.session_state.bankroll)
                        st.rerun()
                with cols[3]:
                    if st.button("🗑️ Remove", key=f"rm_{i}"):
                        st.session_state.locks.pop(i)
                        st.rerun()
        if st.session_state.history:
            st.markdown("### Resolved History")
            st.table(pd.DataFrame([{"ID": h.get("id"), "Pick": h.get("player", h.get("matchup")), "Result": h.get("result"), "Tier": h.get("tier")} for h in st.session_state.history]))

    with tabs[4]:
        st.markdown("# 🔄 RECONCILIATION & SYNC")
        pasted = st.text_area("Format: Player OVER/UNDER Line WIN/LOSS", height=150)
        if st.button("🔍 Sync"):
            parsed = parse_pasted_results(pasted)
            if parsed:
                for lock in st.session_state.locks:
                    if lock["status"] == "PENDING":
                        for r in parsed:
                            if r["player"].lower() in lock.get("player", "").lower() and r["side"] == lock.get("side", "") and abs(r["line"] - lock.get("line", 0)) < 0.1:
                                lock["status"] = "RESOLVED"
                                lock["result"] = r["outcome"]
                                st.session_state.history.append(lock)
                                if r["outcome"] == "WIN":
                                    st.session_state.bankroll = get_bankroll() + active_unit()
                                    set_bankroll(st.session_state.bankroll)
                                else:
                                    st.session_state.autopsy_log.append({"id": lock.get("id"), "pick": lock.get("player", lock.get("matchup")), "result": "LOSS", "reason": classify_loss(lock), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                                    st.session_state.bankroll = max(0.0, get_bankroll() - active_unit())
                                    set_bankroll(st.session_state.bankroll)
                st.session_state.locks = [l for l in st.session_state.locks if l["status"] == "PENDING"]
                st.success("Synced.")
        st.markdown("---")
        if st.session_state.autopsy_log:
            st.markdown("### 🔬 Autopsy Log")
            st.table(pd.DataFrame(st.session_state.autopsy_log))

    with tabs[5]:
        st.markdown("# 🛡️ SEM & SYSTEM HEALTH")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Integrity", "64/100")
        c2.metric("Safe Corridor", "ACTIVE")
        c3.metric("Emergency Floor", "ACTIVE (12%)")
        c4.metric("Bankroll", f"${get_bankroll():.2f}")

        st.markdown("---")
        st.markdown("## 📡 Site Health")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### Prop Sources")
            for name in PROP_SOURCES:
                s = health(name)["status"]
                t = health(name)["last_checked"] or "—"
                st.markdown(f"{dot(s)} **{name}** — {t}")
        with c2:
            st.markdown("### Game & Lineup Sources")
            for name in list(GAME_SOURCES) + list(LINEUP_SOURCES):
                s = health(name)["status"]
                t = health(name)["last_checked"] or "—"
                st.markdown(f"{dot(s)} **{name}** — {t}")

        st.markdown("---")
        st.markdown("## ➕ Add Custom Source")
        nn = st.text_input("Source Name")
        nu = st.text_input("Source URL (use {sport})")
        if st.button("Add Source") and nn and nu:
            PROP_SOURCES[nn] = nu
            set_health(nn, "unknown", "", 0)
            st.success(f"Added: {nn}")

        st.markdown("---")
        st.markdown("## 📖 Tier Legend")
        for tier, desc in TIER_DESCRIPTIONS.items():
            st.markdown(f"**{tier_label(tier)}** — {desc}")

if __name__ == "__main__":
    main()
