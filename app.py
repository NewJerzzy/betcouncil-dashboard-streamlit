import streamlit as st, pandas as pd, requests, random
from bs4 import BeautifulSoup
from datetime import date, datetime

st.set_page_config(page_title="BetCouncil v3.1 OS", page_icon="🛡️", layout="wide")

MODEL_WEIGHTS={"deepseek":0.18,"supreme":0.18,"claude":0.14,"copilot":0.14,"gemini":0.10,"perplexity":0.10,"grok":0.10,"base":0.06}
TIER_THRESHOLDS={"SOVEREIGN":0.75,"ELITE":0.65,"VALUE":0.55}
DEFAULT_BANKROLL=527.25
ACTIVE_FLOOR=0.045
KELLY_FRACTION=0.25
SEM_WINDOW_SIZE=20

SENSOR_CONFIG={
"BettingPros":{"url":"https://www.bettingpros.com/","purpose":"Consensus props","sem_impact":-2,"firewall_impact":"HIGH"},
"RotoWire":{"url":"https://www.rotowire.com/","purpose":"Injuries","sem_impact":-3,"firewall_impact":"CRITICAL"},
"PineSports":{"url":"https://www.pine-sports.com/","purpose":"Correlation","sem_impact":-2,"firewall_impact":"MEDIUM"},
"Action Network":{"url":"https://www.actionnetwork.com/","purpose":"Sharp money","sem_impact":-3,"firewall_impact":"HIGH"},
"CBS Sports":{"url":"https://www.cbssports.com/","purpose":"Expert sims","sem_impact":-1,"firewall_impact":"MEDIUM"},
"Basketball-Reference":{"url":"https://www.basketball-reference.com/","purpose":"Usage","sem_impact":-2,"firewall_impact":"HIGH"},
"NBA Stats":{"url":"https://www.nba.com/stats","purpose":"Tracking","sem_impact":-2,"firewall_impact":"HIGH"},
"Massey Ratings":{"url":"https://masseyratings.com/","purpose":"Power ranks","sem_impact":-1,"firewall_impact":"MEDIUM"},
"Dunkel Index":{"url":"https://www.dunkelindex.com/","purpose":"Blowout prob","sem_impact":-2,"firewall_impact":"HIGH"},
"Covers":{"url":"https://www.covers.com/","purpose":"Market movement","sem_impact":-1,"firewall_impact":"MEDIUM"},
"Yahoo Sports":{"url":"https://sports.yahoo.com/","purpose":"Volume","sem_impact":-1,"firewall_impact":"MEDIUM"},
"ESPN":{"url":"https://www.espn.com/","purpose":"Beat news","sem_impact":-2,"firewall_impact":"HIGH"},
"DraftKings":{"url":"https://sportsbook.draftkings.com/","purpose":"Primary line","sem_impact":-2,"firewall_impact":"CRITICAL"},
"FanDuel":{"url":"https://www.fanduel.com/sportsbook","purpose":"Secondary line","sem_impact":-2,"firewall_impact":"CRITICAL"},
}

SENSOR_NAMES=list(SENSOR_CONFIG.keys())
HEADERS={"User-Agent":"Mozilla/5.0"}

if "sensor_status" not in st.session_state:
    st.session_state.sensor_status={n:{"status":"UNKNOWN","last":None,"error":None,"fallback_used":False} for n in SENSOR_NAMES}

if "board_data" not in st.session_state:
    st.session_state.board_data={"props":None,"injuries":None,"spreads":None,"series":None,"firewall_removed":0,"model_verdicts":{}}

if "games" not in st.session_state: st.session_state.games=None
if "locks" not in st.session_state: st.session_state.locks=[]
if "history" not in st.session_state: st.session_state.history=[]
if "sem_integrity" not in st.session_state: st.session_state.sem_integrity=69
if "bankroll" not in st.session_state: st.session_state.bankroll=DEFAULT_BANKROLL
if "last_sport" not in st.session_state: st.session_state.last_sport="NBA"
if "safe_corridor_active" not in st.session_state: st.session_state.safe_corridor_active=True
if "emergency_floor_pct" not in st.session_state: st.session_state.emergency_floor_pct=12
if "sem_notes" not in st.session_state: st.session_state.sem_notes=""
if "sem_mode" not in st.session_state: st.session_state.sem_mode="NORMAL"
if "sem_profile" not in st.session_state: st.session_state.sem_profile={"max_parlay_legs":4,"allowed_tiers":["SOVEREIGN","ELITE","VALUE"]}
if "sensor_score" not in st.session_state: st.session_state.sensor_score=1.0

def calculate_active_unit(b): return round(b*ACTIVE_FLOOR*KELLY_FRACTION,2)
def calculate_weighted_consensus(ms): return round(sum(ms.get(m,0)*w for m,w in MODEL_WEIGHTS.items()),3)
def assign_tier(s): return "SOVEREIGN" if s>=TIER_THRESHOLDS["SOVEREIGN"] else "ELITE" if s>=TIER_THRESHOLDS["ELITE"] else "VALUE" if s>=TIER_THRESHOLDS["VALUE"] else "PASS"
def add_lock(e): st.session_state.locks.append(e)
def move_to_history(l,r,u,reason=""): x=l.copy(); x["status"]="RESOLVED"; x["result"]=r; x["units"]=u; x["reason"]=reason; st.session_state.history.append(x)

def generate_model_verdicts_for_prop(player,prop,side,line,sport):
    base=0.7
    if any(k in player for k in["Wembanyama","Ohtani","Mahomes","McDavid"]): base=0.82
    elif any(k in player for k in["Maxey","Judge","Kelce","Matthews"]): base=0.78
    elif "UNDER" in side: base=0.72
    scores={"deepseek":base,"supreme":base-0.02,"claude":base-0.03,"copilot":base-0.01,"gemini":base-0.05,"perplexity":base-0.06,"grok":base-0.04,"base":base-0.1}
    verdicts={m:("Elite Approve" if s>=0.75 else "Approve" if s>=0.65 else "Thin Edge" if s>=0.55 else "Pass") for m,s in scores.items()}
    wc=calculate_weighted_consensus(scores)
    tier=assign_tier(wc)
    return scores,verdicts,wc,tier

def enrich_props_with_models(df,sport):
    mv={}; scores=[]; tiers=[]
    for i,r in df.iterrows():
        ms,v,wc,t=generate_model_verdicts_for_prop(r["Player"],r["Prop"],r["Side"],r["Line"],sport)
        mv[i]=v; scores.append(wc); tiers.append(t)
    df["Weighted Score"]=scores; df["Tier"]=tiers
    return df,mv

def enrich_games_with_models(df,sport):
    scores=[]; tiers=[]
    for _,r in df.iterrows():
        base=0.76 if any(k in r["Matchup"] for k in["PHI","MIN","LAD","ATL","KC","GB","TOR","BOS"]) else 0.7
        ms={"deepseek":base,"supreme":base-0.02,"claude":base-0.03,"copilot":base-0.01,"gemini":base-0.05,"perplexity":base-0.06,"grok":base-0.04,"base":base-0.1}
        wc=calculate_weighted_consensus(ms); t=assign_tier(wc)
        scores.append(wc); tiers.append(t)
    df["Weighted Score"]=scores; df["Tier"]=tiers
    return df

def get_sport_specific_props(s):
    if s=="NBA": return pd.DataFrame([["LeBron James","POINTS",27.5,"OVER"],["Anthony Davis","REBOUNDS",11.5,"OVER"],["Stephen Curry","THREES",4.5,"OVER"],["Jayson Tatum","POINTS",28.5,"UNDER"],["Nikola Jokic","ASSISTS",9.5,"OVER"]],columns=["Player","Prop","Line","Side"])
    if s=="NFL": return pd.DataFrame([["Patrick Mahomes","PASSING YARDS",285.5,"OVER"],["Travis Kelce","RECEPTIONS",6.5,"OVER"],["Josh Allen","RUSH YARDS",42.5,"OVER"],["Tyreek Hill","RECEIVING YARDS",94.5,"OVER"],["Christian McCaffrey","RUSH YARDS",82.5,"UNDER"]],columns=["Player","Prop","Line","Side"])
    if s=="NHL": return pd.DataFrame([["Connor McDavid","POINTS",1.5,"OVER"],["Auston Matthews","GOALS",0.5,"OVER"],["Nathan MacKinnon","SHOTS",4.5,"OVER"],["David Pastrnak","POINTS",1.5,"UNDER"],["Leon Draisaitl","ASSISTS",0.5,"OVER"]],columns=["Player","Prop","Line","Side"])
    return pd.DataFrame([["Shohei Ohtani","TOTAL BASES",1.5,"OVER"],["Aaron Judge","HOME RUN",0.5,"OVER"],["Mookie Betts","RUNS+RBI",1.5,"OVER"],["Spencer Strider","STRIKEOUTS",8.5,"OVER"],["Corbin Burnes","STRIKEOUTS",7.5,"UNDER"]],columns=["Player","Prop","Line","Side"])

def get_sport_specific_games(s):
    if s=="NBA": return pd.DataFrame([["LAL @ GSW","LAL -145","LAL -3.5","O/U 234.5"],["BOS @ DEN","BOS -120","BOS -1.5","O/U 227.5"]],columns=["Matchup","Moneyline","Spread","Total"])
    if s=="NFL": return pd.DataFrame([["KC @ BUF","KC -130","KC -2.5","O/U 48.5"],["PHI @ DAL","PHI -115","PHI -1.5","O/U 46.5"]],columns=["Matchup","Moneyline","Spread","Total"])
    if s=="NHL": return pd.DataFrame([["EDM @ TOR","EDM -125","EDM -1.5","O/U 6.5"],["COL @ BOS","COL -135","COL -1.5","O/U 5.5"]],columns=["Matchup","Moneyline","Spread","Total"])
    return pd.DataFrame([["LAD @ NYY","LAD -135","LAD -1.5","O/U 8.5"],["ATL @ MIL","ATL -140","ATL -1.5","O/U 7.5"]],columns=["Matchup","Moneyline","Spread","Total"])

def build_game_parlay(df):
    df=df.sort_values("Weighted Score",ascending=False)
    allowed=st.session_state.sem_profile["allowed_tiers"]
    maxlegs=st.session_state.sem_profile["max_parlay_legs"]
    legs=[]
    for _,r in df.iterrows():
        if r["Tier"] not in allowed: continue
        ml=r["Moneyline"]; sp=r["Spread"]; tot=r["Total"]
        best=r["Weighted Score"]
        legs.append(f"{r['Matchup']} — BEST LEG ({best}): {ml}, {sp}, {tot}")
        if len(legs)>=maxlegs: break
    return legs

def render():
    st.title("BetCouncil v3.1 OS")
    sport=st.selectbox("Select Sport",["NBA","NFL","MLB","NHL"])
    props=get_sport_specific_props(sport)
    games=get_sport_specific_games(sport)
    props,mv=enrich_props_with_models(props,sport)
    games=enrich_games_with_models(games,sport)
    st.subheader("Prop Board")
    st.dataframe(props)
    st.subheader("Game Board")
    st.dataframe(games)
    st.subheader("Game Parlay of the Day")
    legs=build_game_parlay(games)
    for l in legs: st.write("• "+l)

render()
