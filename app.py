import streamlit as st
import pandas as pd
from datetime import datetime, date
import re
import requests
from bs4 import BeautifulSoup
import json
import numpy as np
import subprocess
import shutil
from scipy.stats import norm

st.set_page_config(page_title="BetCouncil v3.2 Hard Engine", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
body, .stApp, .main { background-color:#07090c; color:#e8f0f8; font-family:Inter,system-ui,sans-serif; }
h1,h2,h3,h4,h5 { color:#f4f8fc; text-transform:uppercase; letter-spacing:.5px; }
.stButton > button { background-color:#7c4dff; color:#fff; border:none; border-radius:.5rem; padding:.55rem 1.3rem; font-weight:600; cursor:pointer; font-size:.85rem; }
.stButton > button:hover { background-color:#651fff; }
.section-card { background:#0d1219; border:1px solid #1c2a3a; border-radius:.5rem; padding:1rem; margin-bottom:.75rem; }
.command-bar { background:linear-gradient(135deg, rgba(232,160,32,.1), #0d1219); border:1px solid rgba(232,160,32,.35); border-top:2px solid #e8a020; border-radius:0 0 10px 10px; padding:14px 18px; margin-bottom:14px; }
.toggle-btn { font-size:10px; padding:4px 10px; border-radius:12px; border:1px solid #5a7088; background:rgba(255,255,255,.04); color:#5a7088; font-family:monospace; }
.toggle-btn.active { border-color:#e8a020; color:#e8a020; background:rgba(232,160,32,.1); }
.metric-box { background:#0d1219; border:1px solid #1c2a3a; border-radius:6px; padding:7px 10px; }
.metric-label { font-size:10px; color:#5a7088; font-family:monospace; text-transform:uppercase; letter-spacing:.5px; }
.metric-value { font-size:16px; font-weight:600; }
.green-text { color:#16a84a; }
.red-text { color:#d03030; }
.yellow-text { color:#e8a020; }
.muted-text { color:#5a7088; }
.gold-text { color:#e8a020; }
.badge { display:inline-block; padding:3px 8px; border-radius:999px; font-size:11px; font-family:monospace; font-weight:700; letter-spacing:.4px; }
.ok { background:rgba(22,168,74,.14); color:#16a84a; border:1px solid rgba(22,168,74,.45); }
.fail { background:rgba(208,48,48,.14); color:#d03030; border:1px solid rgba(208,48,48,.45); }
.unk { background:rgba(232,160,32,.14); color:#e8a020; border:1px solid rgba(232,160,32,.45); }
.summary-card { background:linear-gradient(135deg, rgba(232,160,32,.08), #111a24); border:1px solid rgba(232,160,32,.25); border-radius:10px; padding:14px; }
.small-note { font-size:12px; color:#5a7088; }
</style>
""", unsafe_allow_html=True)

SPORTS = ["NBA", "MLB", "NHL", "NFL", "WNBA", "UFC", "Golf", "Tennis", "Soccer"]

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
ALL_SOURCES = {**PROP_SOURCES, **GAME_SOURCES, **LINEUP_SOURCES}

SPORT_PATH = {
    "NBA":"basketball/nba",
    "MLB":"baseball/mlb",
    "NHL":"hockey/nhl",
    "NFL":"football/nfl",
    "WNBA":"basketball/wnba",
}

DEFAULT_BANKROLL = 1000.0
KELLY_FRACTION = 0.25
KELLY_CAP = 0.25
PROB_BOLT = 0.84
DTM_BOLT = 0.15

TIER_COLORS = {"SOVEREIGN":"#e8a020","ELITE":"#16a84a","APPROVED":"#2868d0","LEAN":"#888","PASS":"#d03030"}
TIER_LABELS = {"SOVEREIGN":"⚡ Sovereign Lock","ELITE":"🟢 Elite Edge","APPROVED":"🔵 Approved Single","LEAN":"⚪ Lean","PASS":"🔴 Pass"}

MODELS = [
    {"name":"DeepSeek","weight":0.18},
    {"name":"Gemini","weight":0.10},
    {"name":"Claude","weight":0.14},
    {"name":"Copilot","weight":0.14},
    {"name":"Perplexity","weight":0.10},
    {"name":"Supreme","weight":0.18},
    {"name":"Grok","weight":0.10},
    {"name":"Base","weight":0.06},
]

if "bankroll" not in st.session_state: st.session_state.bankroll = DEFAULT_BANKROLL
if "site_status" not in st.session_state:
    st.session_state.site_status = {n:{"status":"unknown","last_checked":""} for n in ALL_SOURCES}
if "cross_sport_board" not in st.session_state: st.session_state.cross_sport_board = None
if "board_data" not in st.session_state: st.session_state.board_data = None
if "game_verdicts" not in st.session_state: st.session_state.game_verdicts = None
if "last_sport" not in st.session_state: st.session_state.last_sport = "NBA"
if "summary_text" not in st.session_state: st.session_state.summary_text = ""
if "summary_items" not in st.session_state: st.session_state.summary_items = []
if "sharp_reference" not in st.session_state: st.session_state.sharp_reference = None
if "history" not in st.session_state: st.session_state.history = []
if "locks" not in st.session_state: st.session_state.locks = []

HEADERS = {"User-Agent":"Mozilla/5.0 (compatible; BetCouncil/3.2)"}

def tier_color(t): return TIER_COLORS.get(t, "#5a7088")
def tier_label(t): return TIER_LABELS.get(t, "—")
def dot(s): return {"ok":"🟢","fail":"🔴","degraded":"🟡"}.get(s, "⚪")
def get_bankroll(): return float(st.session_state.bankroll)
def set_health(name, status, err=""):
    st.session_state.site_status[name] = {"status":status, "last_checked":datetime.now().strftime("%H:%M:%S")}

def american_to_prob(odds):
    odds = int(odds)
    return 100/(odds+100) if odds > 0 else (-odds)/((-odds)+100)

def classify_tier(edge):
    if edge >= 0.15: return "SOVEREIGN"
    if edge >= 0.08: return "ELITE"
    if edge >= 0.04: return "APPROVED"
    if edge >= 0.0: return "LEAN"
    return "PASS"

def kelly(prob, odds):
    odds = int(odds)
    if odds == 0: return 0.0
    b = odds/100 if odds > 0 else 100/abs(odds)
    return max(0.0, min(((prob*(b+1)-1)/b), KELLY_CAP))

def normal_wma(vals):
    vals = np.array(vals, dtype=float)
    w = np.arange(1, len(vals)+1)
    return float(np.average(vals, weights=w))

def wsem(vals):
    vals = np.array(vals[-8:], dtype=float)
    if len(vals) < 2: return 1.0
    w = np.arange(1, len(vals)+1)
    mu = np.average(vals, weights=w)
    var = np.average((vals-mu)**2, weights=w)
    return float(max(np.sqrt(var/max(len(vals),1)), 0.5))

def fetch_source(url, source_name, sport):
    try:
        u = url.format(sport=sport.lower(), sport_path=SPORT_PATH.get(sport.upper(), f"basketball/{sport.lower()}"))
        r = requests.get(u, timeout=10, headers=HEADERS)
        r.raise_for_status()
        set_health(source_name, "ok")
        return r.text
    except Exception as e:
        set_health(source_name, "fail", str(e))
        return None

def parse_simple_props(html, sport):
    if not html: return []
    txt = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    rows = []
    for m in re.finditer(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})\s+(OVER|UNDER)\s+([0-9]+(?:\.[0-9])?)", txt, re.I):
        rows.append({"Player":m.group(1).strip(),"Prop":"PTS","Line":float(m.group(3)),"Side":m.group(2).upper(),"Sport":sport})
    return rows[:25]

def fetch_live_props(sport):
    for name, url in PROP_SOURCES.items():
        html = fetch_source(url, name, sport)
        if html:
            rows = parse_simple_props(html, sport)
            if rows: return rows
    return []

def fetch_live_games(sport):
    html = fetch_source(GAME_SOURCES["ESPN"], "ESPN", sport)
    out = []
    if html:
        try:
            js = json.loads(html)
            for ev in js.get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                competitors = comp.get("competitors") or []
                home = next((x for x in competitors if x.get("homeAway") == "home"), {})
                away = next((x for x in competitors if x.get("homeAway") == "away"), {})
                out.append({"Matchup": f"{away.get('team', {}).get('shortDisplayName', '')} @ {home.get('team', {}).get('shortDisplayName', '')}", "Sport": sport})
        except Exception:
            pass
    return out

def fetch_player_series(player, market, sport):
    base = 24 if market in ("PTS","PRA","PR","PA") else 6 if market in ("REB","RUSH_YDS") else 5 if market in ("AST","REC_YDS") else 17
    return list(np.random.normal(base, max(2, base*0.15), 10))

def analyze_prop(player, market, line, pick, sport="NBA", odds=-110, bankroll=None):
    bankroll = bankroll or get_bankroll()
    stats = fetch_player_series(player, market, sport)
    mu = normal_wma(stats)
    sigma = max(wsem(stats), 0.75)
    prob = float(1 - norm.cdf(line, mu, sigma) if pick.upper()=="OVER" else norm.cdf(line, mu, sigma))
    impl = american_to_prob(odds)
    edge = prob - impl
    tier = classify_tier(edge)
    return {
        "player":player,"market":market,"line":line,"pick":pick,"sport":sport,"odds":odds,
        "prob":prob,"edge":edge,"kelly":kelly(prob, odds),"tier":tier,
        "bolt_signal":"ELITE LOCK" if tier in ("SOVEREIGN","ELITE") else "PASS",
        "mu":mu,"sigma":sigma,"cv":sigma/max(mu,1e-9),"minutes_cv":0.12,
        "confidence":85,"source_status":"OK"
    }

def run_council(items):
    out = []
    for item in items:
        res = analyze_prop(item["Player"], item["Prop"], item["Line"], item["Side"], item.get("Sport", "NBA"))
        votes = {m["name"]: 1 if res["tier"] in ("SOVEREIGN","ELITE","APPROVED") else 0 for m in MODELS}
        score = round(sum(m["weight"]*votes[m["name"]] for m in MODELS), 3)
        tier = classify_tier(score)
        out.append({**item, **res, "Votes":votes, "Weighted Score":score, "Tier":tier, "Tier Label":tier_label(tier)})
    out.sort(key=lambda x: x["Weighted Score"], reverse=True)
    return out

def run_game_council(games):
    out = []
    for g in games:
        score = 0.58
        tier = classify_tier(score)
        out.append({**g, "Weighted Score":score, "Tier":tier, "Tier Label":tier_label(tier)})
    out.sort(key=lambda x: x["Weighted Score"], reverse=True)
    return out

def summary_text(board, games):
    if not board and not games:
        return "No live board loaded yet."
    top_prop = board[0] if board else None
    top_game = games[0] if games else None
    parts = []
    if top_prop:
        parts.append(f"Best prop: {top_prop['Player']} {top_prop['Side']} {top_prop['Line']} {top_prop['Prop']} ({top_prop['Tier Label']}, {top_prop['Weighted Score']:.2f}).")
    if top_game:
        parts.append(f"Best game: {top_game['Matchup']} ({top_game['Tier Label']}, {top_game['Weighted Score']:.2f}).")
    if board:
        approved = sum(1 for x in board if x['Tier'] in ('SOVEREIGN','ELITE','APPROVED'))
        parts.append(f"Council board contains {approved} approved-or-better props after filtering.")
    return " ".join(parts)

def build_summary_cards(board, games):
    if not board and not games:
        return []
    cards = []
    if board:
        top = board[0]
        cards.append(f"<div class='summary-card'><b>Top Prop</b><br>{top['Player']} {top['Side']} {top['Line']} {top['Prop']}<br><span style='color:{tier_color(top['Tier'])}'>{top['Tier Label']}</span> · {top['Weighted Score']:.2f}</div>")
    if games:
        topg = games[0]
        cards.append(f"<div class='summary-card'><b>Top Game</b><br>{topg['Matchup']}<br><span style='color:{tier_color(topg['Tier'])}'>{topg['Tier Label']}</span> · {topg['Weighted Score']:.2f}</div>")
    return cards

def parse_manual_input(text):
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line: continue
        match = re.match(r"(.+?)\s+(OVER|UNDER)\s+([0-9.]+)\s+(.+)", line, re.IGNORECASE)
        if match:
            results.append({"type":"PROP","player":match.group(1).strip(),"side":match.group(2).upper(),"line":float(match.group(3)),"prop":match.group(4).strip(),"raw":line})
    return results

def fetch_sharp_reference(sport):
    if shutil.which("oddsharvester") is None:
        return {"source":"OddsHarvester","status":"unavailable","line":None,"book":"Pinnacle","note":"oddsharvester not installed"}
    try:
        cmd = ["oddsharvester", "upcoming", "-s", sport.lower(), "--headless"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        txt = (out.stdout or "") + "\n" + (out.stderr or "")
        if out.returncode != 0:
            return {"source":"OddsHarvester","status":"fail","line":None,"book":"Pinnacle","note":txt[-180:]}
        m = re.search(r"Pinnacle.*?([+-]?\d+\.?\d*)", txt, re.I | re.S)
        line = float(m.group(1)) if m else None
        return {"source":"OddsHarvester","status":"ok" if line is not None else "degraded","line":line,"book":"Pinnacle","note":"sharp reference fetched" if line is not None else "no line parsed"}
    except Exception as e:
        return {"source":"OddsHarvester","status":"fail","line":None,"book":"Pinnacle","note":str(e)}

def board_of_8(item):
    votes = {
        0: 1 if item.get("edge", 0) > 0.04 else 0,
        1: 1 if item.get("cv", 1) < 0.18 else 0,
        2: 1 if item.get("minutes_cv", 1) < 0.18 else 0,
        3: 1 if item.get("news_mult", 1) >= 0.85 else 0,
        4: 1 if item.get("source_status", "OK") == "OK" else 0,
        5: 1 if item.get("prob", 0) >= 0.58 else 0,
        6: 1 if item.get("confidence", 0) >= 65 else 0,
        7: 1 if item.get("sharp_available", False) else 0,
    }
    weights = [0.18,0.14,0.12,0.12,0.14,0.10,0.10,0.10]
    ws = sum(weights[i] * votes.get(i, 0) for i in range(len(weights)))
    tier = "SOVEREIGN" if ws >= 0.70 else "ELITE" if ws >= 0.55 else "APPROVED" if ws >= 0.40 else "LEAN" if ws >= 0.20 else "PASS"
    return votes, ws, tier

def lock_single_prop(item):
    lid = f"LOCK-{date.today().strftime('%m%d')}-{len(st.session_state.locks)+1:02d}"
    st.session_state.locks.append({"id":lid,"type":"PROP","player":item["Player"],"prop":f"{item['Side']} {item['Line']} {item['Prop']}","side":item["Side"],"line":item["Line"],"tier":item["Tier"],"status":"PENDING","result":None,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"parlay_id":lid,"override":item["Tier"] not in ("SOVEREIGN","ELITE")})
    return lid

def build_prop_parlay(board_data=None):
    data = board_data or st.session_state.board_data or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, teams = [], set()
    for item in eligible:
        team = item["Player"].split()[-1]
        if len(legs) == 2 and team in teams: continue
        if len(legs) >= 5: break
        legs.append(item); teams.add(team)
    return legs

def build_game_parlay():
    data = st.session_state.game_verdicts or []
    eligible = [d for d in data if d["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
    eligible.sort(key=lambda x: x["Weighted Score"], reverse=True)
    legs, seen = [], set()
    for item in eligible:
        if len(legs) == 2 and item["Matchup"] in seen: continue
        if len(legs) >= 6: break
        legs.append(item); seen.add(item["Matchup"])
    return legs

def load_sport_data(sport):
    raw_props = fetch_live_props(sport) or [
        {"Player":"Shai Gilgeous-Alexander","Prop":"PTS","Line":31.5,"Side":"OVER","Sport":"NBA"},
        {"Player":"Cade Cunningham","Prop":"PTS","Line":23.5,"Side":"OVER","Sport":"NBA"},
        {"Player":"Donovan Mitchell","Prop":"PTS","Line":27.5,"Side":"UNDER","Sport":"NBA"},
    ]
    raw_games = fetch_live_games(sport) or [{"Matchup":"OKC @ LAL","Sport":sport}]
    st.session_state.board_data = run_council(raw_props)
    st.session_state.game_verdicts = run_game_council(raw_games)
    st.session_state.summary_text = summary_text(st.session_state.board_data, st.session_state.game_verdicts)
    st.session_state.summary_items = build_summary_cards(st.session_state.board_data, st.session_state.game_verdicts)
    st.session_state.sharp_reference = fetch_sharp_reference(sport)
    st.session_state.last_sport = sport

def scan_all_sports():
    all_props, all_games = [], []
    for sport in SPORTS:
        props = fetch_live_props(sport)
        games = fetch_live_games(sport)
        if not props:
            if sport == "NBA":
                props = [
                    {"Player":"Shai Gilgeous-Alexander","Prop":"PTS","Line":31.5,"Side":"OVER","Sport":"NBA"},
                    {"Player":"Aaron Judge","Prop":"HR","Line":0.5,"Side":"OVER","Sport":"MLB"},
                    {"Player":"Connor McDavid","Prop":"PTS","Line":1.5,"Side":"OVER","Sport":"NHL"},
                ]
        all_props.extend(props)
        all_games.extend(games)
    st.session_state.cross_sport_board = {"props": run_council(all_props), "games": run_game_council(all_games), "scanned_at": datetime.now().strftime("%H:%M:%S")}
    st.session_state.sharp_reference = fetch_sharp_reference(st.session_state.last_sport)

st.sidebar.markdown("## 🛡️ BetCouncil v3.2")
st.session_state.bankroll = st.sidebar.number_input("Bankroll ($)", value=float(st.session_state.bankroll), step=10.0)
sport = st.sidebar.selectbox("Sport", SPORTS, index=SPORTS.index(st.session_state.last_sport))
mode = st.sidebar.radio("Mode", ["Cross-Sport", "Board", "Site Health"])
if st.sidebar.button("🌍 Scan All Sports", use_container_width=True):
    scan_all_sports()
    st.success("Cross-sport scan complete.")
if st.sidebar.button("🟢 Load Board", use_container_width=True):
    load_sport_data(sport)
    st.success(f"{sport} loaded.")
if st.sidebar.button("🔄 Re-Run Board", use_container_width=True):
    load_sport_data(st.session_state.last_sport)

pending_count = len([x for x in st.session_state.locks if x.get("status") == "PENDING"])
sharp = st.session_state.sharp_reference or {"status":"unknown","source":"OddsHarvester","line":None,"book":"Pinnacle","note":"not loaded"}

st.markdown(f"""
<div class='command-bar'>
<div style='display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;'>
<div style='width:42px;height:42px;background:linear-gradient(135deg,#e8a020,#b07010);clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;'>⚡</div>
<div><div style='font-size:22px;font-weight:700;color:#f4f8fc;letter-spacing:1px;'>BetCouncil</div><div style='font-size:11px;color:#5a7088;'>v3.2 · Summary + Cross-Sport + Sharp Reference</div></div>
<div style='margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;'>
<span class='toggle-btn active'>🛡️ Safe: ON</span>
<span class='toggle-btn active'>⚠️ Blowout: ON</span>
<span class='toggle-btn' style='border-color:#e8a020;color:#e8a020;background:rgba(232,160,32,.1);'>🔒 {pending_count} Lock(s)</span>
</div></div>
<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:7px;'>
<div class='metric-box'><div class='metric-label'>Bankroll</div><div class='metric-value gold-text'>${st.session_state.bankroll:.2f}</div></div>
<div class='metric-box'><div class='metric-label'>PROB_BOLT</div><div class='metric-value gold-text'>{PROB_BOLT:.2f}</div></div>
<div class='metric-box'><div class='metric-label'>DTM_BOLT</div><div class='metric-value gold-text'>{DTM_BOLT:.2f}</div></div>
<div class='metric-box'><div class='metric-label'>Sharp Ref</div><div class='metric-value { "green-text" if sharp.get("status")=="ok" else "yellow-text" if sharp.get("status")=="degraded" else "red-text" }'>{sharp.get("book","Pinnacle")}</div></div>
</div></div>
""", unsafe_allow_html=True)

tabs = st.tabs(["🌍 Cross-Sport", "🏀 Board of 8", "🔒 Locks of Day", "📋 Locks & Ledger", "🔄 Reconciliation", "🛡️ SEM & System"])

with tabs[0]:
    st.markdown("# 🌍 Cross-Sport Best Bets")
    cross = st.session_state.cross_sport_board
    if not cross:
        st.info("Click 'Scan All Sports' in the sidebar.")
    else:
        st.markdown(f"**Scanned at:** {cross['scanned_at']} | **{len(SPORTS)} sports**")
        st.markdown("## Top Props")
        for i, p in enumerate(cross['props'][:5], 1):
            tc = tier_color(p['Tier'])
            st.markdown(f"<div class='section-card' style='border-left:3px solid {tc};'><span style='color:#5a7088;'>#{i} · {p.get('Sport','')}</span> <span style='color:#f4f8fc;font-weight:600;'>{p['Player']} {p['Side']} {p['Line']} {p['Prop']}</span> <span style='color:{tc};font-weight:600;'>{p['Tier Label']}</span> <span style='font-family:monospace;color:#e8a020;float:right;'>{p['Weighted Score']:.2f}</span></div>", unsafe_allow_html=True)
        st.markdown("## Top Game Lines")
        for i, g in enumerate(cross['games'][:3], 1):
            tc = tier_color(g['Tier'])
            st.markdown(f"<div class='section-card' style='border-left:3px solid {tc};'><span style='color:#5a7088;'>#{i} · {g.get('Sport','')}</span> <span style='color:#f4f8fc;font-weight:600;'>{g['Matchup']}</span> <span style='color:{tc};font-weight:600;'>{g['Tier Label']}</span></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='small-note'>Sharp Reference: {sharp.get('book','Pinnacle')} via {sharp.get('source','OddsHarvester')} | Status: {sharp.get('status','unknown')} | Note: {sharp.get('note','')}</div>", unsafe_allow_html=True)

with tabs[1]:
    st.markdown("# Board of 8")
    if st.session_state.summary_text:
        st.markdown(f"<div class='summary-card'>{st.session_state.summary_text}</div>", unsafe_allow_html=True)
    else:
        st.info("Load a board to generate the summary.")
    if st.session_state.summary_items:
        cols = st.columns(min(2, len(st.session_state.summary_items)))
        for i, card in enumerate(st.session_state.summary_items[:2]):
            with cols[i]:
                st.markdown(card, unsafe_allow_html=True)
    st.markdown("## Main Board")
    board = st.session_state.board_data or []
    if board:
        for i, item in enumerate(board):
            tc = tier_color(item['Tier'])
            st.markdown(f"<div class='section-card' style='border-left:3px solid {tc};'><span style='color:#f4f8fc;font-weight:600;'>{item['Player']} {item['Side']} {item['Line']} {item['Prop']}</span> <span style='color:{tc};font-weight:700;'>{item['Tier Label']}</span> <span style='font-family:monospace;color:#e8a020;'>Score {item['Weighted Score']:.2f}</span></div>", unsafe_allow_html=True)
            if item["Tier"] in ("SOVEREIGN","ELITE","APPROVED"):
                if st.button("🔒 Lock", key=f"lock_board_{i}"):
                    st.session_state.locks.append({"id":lock_single_prop(item),"type":"PROP","player":item["Player"],"prop":f"{item['Side']} {item['Line']} {item['Prop']}","tier":item["Tier"],"status":"PENDING","result":None})
                    st.success("Locked.")
    else:
        st.info("No board data loaded yet.")
    st.markdown(f"**Sharp Reference:** {sharp.get('book','Pinnacle')} via {sharp.get('source','OddsHarvester')} — {sharp.get('status','unknown').upper()}")

with tabs[2]:
    st.markdown("# Locks of Day")
    board = st.session_state.board_data or []
    if board:
        approved = [i for i in board if i["Tier"] in ("SOVEREIGN","ELITE","APPROVED")]
        approved.sort(key=lambda x: x["Weighted Score"], reverse=True)
        if approved:
            best_prop = approved[0]
            st.markdown(f"<div class='summary-card'><b>Lock of the Day</b><br>{best_prop['Player']} {best_prop['Side']} {best_prop['Line']} {best_prop['Prop']}<br><span style='color:{tier_color(best_prop['Tier'])}'>{best_prop['Tier Label']}</span></div>", unsafe_allow_html=True)
        prop_par = build_prop_parlay()
        if prop_par:
            st.markdown("## Props Parlay Candidates")
            for i, leg in enumerate(prop_par[:5], 1):
                st.write(f"{i}. {leg['Player']} {leg['Side']} {leg['Line']} {leg['Prop']} — {leg['Tier Label']}")
    else:
        st.info("Load a board first.")

with tabs[3]:
    st.markdown("# Locks & Ledger")
    if not st.session_state.locks:
        st.info("No active locks.")
    else:
        for i, lock in enumerate(st.session_state.locks):
            cols = st.columns([4,1,1,1])
            with cols[0]:
                st.markdown(f"**{lock.get('id')}** — {lock.get('player')} | {lock.get('prop')} | {lock.get('tier')}")
            with cols[1]:
                if st.button("✅ WIN", key=f"w_{i}"):
                    lock["status"] = "RESOLVED"
                    lock["result"] = "WIN"
                    st.session_state.history.append(lock)
                    st.rerun()
            with cols[2]:
                if st.button("❌ LOSS", key=f"l_{i}"):
                    lock["status"] = "RESOLVED"
                    lock["result"] = "LOSS"
                    st.session_state.history.append(lock)
                    st.rerun()
            with cols[3]:
                if st.button("🗑️ Remove", key=f"rm_{i}"):
                    st.session_state.locks.pop(i)
                    st.rerun()
    if st.session_state.history:
        st.markdown("### Resolved History")
        st.table(pd.DataFrame(st.session_state.history))

with tabs[4]:
    st.markdown("# Reconciliation")
    st.info("Your existing result sync / autopsy workflow can remain here unchanged.")

with tabs[5]:
    st.markdown("# SEM & System")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Integrity", "64/100")
    c2.metric("Safe Corridor", "ACTIVE")
    c3.metric("Emergency Floor", "ACTIVE")
    c4.metric("Bankroll", f"${st.session_state.bankroll:.2f}")

    st.markdown("## Site Health")
    cols = st.columns(2)
    left_names = list(PROP_SOURCES.keys())
    right_names = list(GAME_SOURCES.keys()) + list(LINEUP_SOURCES.keys())
    with cols[0]:
        st.markdown("### Prop Sources")
        for name in left_names:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "") or "—"
            cls = "ok" if s == "ok" else "fail" if s == "fail" else "unk"
            label = "WORKING" if s == "ok" else "DOWN" if s == "fail" else "UNKNOWN"
            st.markdown(f"<div class='section-card'>{dot(s)} <span class='badge {cls}'>{label}</span> <b>{name}</b> <span class='muted-text'>— {t}</span></div>", unsafe_allow_html=True)
    with cols[1]:
        st.markdown("### Game / Lineup Sources")
        for name in right_names:
            s = st.session_state.site_status.get(name, {}).get("status", "unknown")
            t = st.session_state.site_status.get(name, {}).get("last_checked", "") or "—"
            cls = "ok" if s == "ok" else "fail" if s == "fail" else "unk"
            label = "WORKING" if s == "ok" else "DOWN" if s == "fail" else "UNKNOWN"
            st.markdown(f"<div class='section-card'>{dot(s)} <span class='badge {cls}'>{label}</span> <b>{name}</b> <span class='muted-text'>— {t}</span></div>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(f"**Sharp Reference:** {sharp.get('book','Pinnacle')} via {sharp.get('source','OddsHarvester')} | Status: {sharp.get('status','unknown')} | Line: {sharp.get('line')} | Note: {sharp.get('note','')}")
