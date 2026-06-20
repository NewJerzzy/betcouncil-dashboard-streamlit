"""BetCouncil shared configuration — constants, API keys, sport maps, signal weights, player/team reference data.

Extracted from app.py (2026-06-19) to bring app.py under the 1MB GitHub Contents API limit.
This module imports streamlit (for st.secrets) and is therefore intended to be imported ONLY by app.py.
bc_utils.py, slip_parser.py, and styles.py must remain streamlit-free and should NOT import from this file
(see bc_utils.py line 14 for the circular-import note that predates this extraction).
"""
import streamlit as st
import os

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_GIST_ID = st.secrets.get("GITHUB_GIST_ID", "7e52e1c2c2054847c7c4663a157386c5")
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "")
ODDSPAPI_KEY = st.secrets.get("ODDSPAPI_KEY", "")
ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")
OCR_SPACE_API_KEY = st.secrets.get("OCR_SPACE_API_KEY", "")
SCRAPEOPS_KEY = st.secrets.get("SCRAPEOPS_KEY", "")
BDL_API_KEY = st.secrets.get("BALLSDONTLIE_API_KEY", "")
RAPIDAPI_KEY = st.secrets.get("RAPIDAPI_KEY", "")
REQUEST_TIMEOUT = 15
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# === API BASE URLS ===
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# === SPORT MAPPINGS ===
ODDS_API_SPORT_MAP = {
    "NBA": "basketball_nba",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    "WNBA": "basketball_wnba",
    "NFL": "americanfootball_nfl",
}

CBS_SPORT_MAP = {
    "NBA": "NBA", "MLB": "MLB", "NHL": "NHL",
    "WNBA": "WNBA", "NFL": "NFL",
}

# === BOOKS ===
ACTIVE_BOOKS = ["PrizePicks", "Underdog", "Novig", "Betr", "DraftKings", "BetMGM", "Bovada"]
DISABLED_BOOKS = ["Sleeper", "BetOnline", "FanDuel", "Caesars"]

DAILY_RISK_CONTROLS = {
    "max_daily_loss_pct": 0.15,
    "max_locks_per_day": 8,
    "stop_win_pct": 0.25,
    "max_same_sport_locks": 4,
    "max_same_game_locks": 2,
}

ACTION_NETWORK_SPORT_MAP = {
    "NBA": "nba",
    "MLB": "mlb",
    "NHL": "nhl",
    "NFL": "nfl",
    "WNBA": "wnba",
}

ACTION_NETWORK_LEAGUE_IDS = {
    "NFL": 1,
    "MLB": 2,
    "NHL": 3,
    "NBA": 4,
    "WNBA": 5,
}

ACTION_NETWORK_PROP_TYPE_MAP = {
    "core_bet_type_27_points": "Points",
    "core_bet_type_28_rebounds": "Rebounds",
    "core_bet_type_29_assists": "Assists",
    "core_bet_type_30_pra": "Pts+Reb+Ast",
    "core_bet_type_31_steals": "Steals",
    "core_bet_type_32_blocks": "Blocked Shots",
    "core_bet_type_33_threes": "3-PT Made",
    "core_bet_type_34_turnovers": "Turnovers",
    "core_bet_type_pts": "Points",
    "core_bet_type_reb": "Rebounds",
    "core_bet_type_ast": "Assists",
    "core_bet_type_pra": "Pts+Reb+Ast",
    "core_bet_type_26_assists": "Assists",
    "core_bet_type_277_blocks": "Blocked Shots",
    "core_bet_type_1042_powerplay_points": "Power Play Points",
    "core_bet_type_hits": "Hits",
    "core_bet_type_hr": "Home Runs",
    "core_bet_type_rbi": "RBIs",
    "core_bet_type_runs": "Runs",
    "core_bet_type_total_bases": "Total Bases",
    "core_bet_type_strikeouts": "Strikeouts",
    "core_bet_type_pitcher_strikeouts": "Strikeouts",
    "core_bet_type_pitcher_outs": "Pitcher Outs",
    "core_bet_type_goals": "Goals",
    "core_bet_type_sog": "Shots On Goal",
    "core_bet_type_passing_yards": "Passing Yards",
    "core_bet_type_rushing_yards": "Rushing Yards",
    "core_bet_type_receiving_yards": "Receiving Yards",
    "core_bet_type_receptions": "Receptions",
    "core_bet_type_touchdowns": "Touchdowns",
    "core_bet_type_passing_tds": "Touchdowns",
}

AN_GRADE_TO_TIER = {
    "A+": "SOVEREIGN",
    "A": "ELITE",
    "A-": "ELITE",
    "B+": "APPROVED",
    "B": "APPROVED",
    "B-": "LEAN",
    "C+": "LEAN",
    "C": "LEAN",
}

ODDS_API_PROP_MARKETS = {
    "NBA": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_points_rebounds_assists",
        "player_steals",
        "player_blocks",
        "player_threes",
        "player_turnovers",
        # Alternate lines — FanDuel/DraftKings ladder odds
        "player_points_alternate",
        "player_rebounds_alternate",
        "player_assists_alternate",
        "player_points_rebounds_assists_alternate",
        "player_threes_alternate",
    ],
    "MLB": [
        "batter_hits",
        "batter_home_runs",
        "batter_rbis",
        "batter_runs_scored",
        "pitcher_strikeouts",
        "pitcher_outs",
        # Alternate lines
        "batter_hits_alternate",
        "batter_home_runs_alternate",
        "pitcher_strikeouts_alternate",
    ],
    "NHL": [
        "player_points",
        "player_goals",
        "player_assists",
        "player_shots_on_goal",
        "player_points_alternate",
    ],
    "NFL": [
        "player_pass_yds",
        "player_rush_yds",
        "player_reception_yds",
        "player_pass_tds",
        "player_pass_yds_alternate",
        "player_rush_yds_alternate",
        "player_reception_yds_alternate",
    ],
    "WNBA": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_points_alternate",
    ],
}

ODDS_API_STAT_MAP = {
    "player_points": "Points",
    "player_rebounds": "Rebounds",
    "player_assists": "Assists",
    "player_points_rebounds_assists": "Pts+Reb+Ast",
    "player_steals": "Steals",
    "player_blocks": "Blocked Shots",
    "player_threes": "3-PT Made",
    "player_turnovers": "Turnovers",
    "batter_hits": "Hits",
    "batter_home_runs": "Home Runs",
    "batter_rbis": "RBIs",
    "batter_runs_scored": "Runs",
    "pitcher_strikeouts": "Strikeouts",
    # Alternate line market keys
    "player_points_alternate": "Points",
    "player_rebounds_alternate": "Rebounds",
    "player_assists_alternate": "Assists",
    "player_points_rebounds_assists_alternate": "Pts+Reb+Ast",
    "player_threes_alternate": "3-PT Made",
    "batter_hits_alternate": "Hits",
    "batter_home_runs_alternate": "Home Runs",
    "pitcher_strikeouts_alternate": "Strikeouts",
    "player_pass_yds_alternate": "Pass Yards",
    "player_rush_yds_alternate": "Rush Yards",
    "player_reception_yds_alternate": "Receiving Yards",
    "pitcher_outs": "Pitcher Outs",
    "player_goals": "Goals",
    "player_assists": "Assists",
    "player_shots_on_goal": "Shots On Goal",
    "player_pass_yds": "Passing Yards",
    "player_rush_yds": "Rushing Yards",
    "player_reception_yds": "Receiving Yards",
    "player_pass_tds": "Touchdowns",
}

API_BUDGETS = {
    "BDL": {
        "key": "BALLSDONTLIE_API_KEY",
        "daily_limit": None,
        "monthly_limit": 200,
        "counter_path": os.path.join(CACHE_DIR, "bdl_unified_counter.json"),
        "description": "BallDontLie (averages + props)",
        "hard_stop_pct": 0.80,
    },
    "ODDSPAPI": {
        "key": "ODDSPAPI_KEY",
        "daily_limit": 100,
        "monthly_limit": 1000,
        "counter_path": os.path.join(CACHE_DIR, "oddspapi_counter.json"),
        "description": "OddsPapi props fallback",
        "hard_stop_pct": 0.80,
    },
    "PARLAYPLAY": {
        "key": None,
        "daily_limit": 200,
        "monthly_limit": None,
        "counter_path": os.path.join(CACHE_DIR, "parlayplay_counter.json"),
        "description": "ParlayPlay all sports",
        "hard_stop_pct": 0.90,
    },
    "ESPN": {
        "key": None,
        "daily_limit": None,
        "monthly_limit": None,
        "counter_path": os.path.join(CACHE_DIR, "espn_counter.json"),
        "description": "ESPN (unlimited public API)",
        "hard_stop_pct": 1.0,
    },
    "ODDS_API": {
        "key": "ODDS_API_KEY",
        "daily_limit": None,
        "monthly_limit": 500,
        "counter_path": os.path.join(CACHE_DIR, "odds_api_counter.json"),
        "description": "The Odds API",
        "hard_stop_pct": 0.80,
    },
    "ACTION_NETWORK": {
        "key": None,
        "daily_limit": 500,
        "monthly_limit": None,
        "counter_path": os.path.join(CACHE_DIR, "action_network_counter.json"),
        "description": "Action Network public betting %",
        "hard_stop_pct": 0.95,
    },
}

TIER_THRESHOLDS = {
    "NBA": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "MLB": {"SOVEREIGN": 0.08, "ELITE": 0.04, "APPROVED": 0.02, "LEAN": 0.01},
    # MLB game-line thresholds are lower than prop thresholds because
    # power rating diffs are small (0.5-3pts on 100-112 scale).
    # ML edge of 2% is genuinely meaningful in MLB betting.
    "NFL": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "NHL": {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "WNBA": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "Soccer": {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "UFC": {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "Golf": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "Tennis": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
}

SPORT_SIGNAL_WEIGHTS = {
    # NBA: defense is the strongest signal (opponent pts allowed to position),
    # pace matters significantly for counting stats (PTS/REB/AST),
    # location is meaningful (~3pt HCA), rest is critical on B2B
    "NBA":  {"base": 0.42, "defense": 0.28, "location": 0.13, "rest": 0.09, "pace": 0.08, "usage": 0.74},

    # MLB HR: platoon-adjusted S1 now does heavy lifting, pitcher (S2) is the
    # second-strongest signal, location matters (park factors already in S12),
    # rest is minimal (baseball plays every day)
    "MLB":  {"base": 0.45, "defense": 0.20, "location": 0.08, "rest": 0.04, "pace": 0.00, "pitcher": 0.15, "weather": 0.08, "usage": 0.74},

    # NFL: defense is the dominant signal (passing/rushing D rank),
    # location (home field) is the most significant HCA in pro sports,
    # rest matters enormously (bye week, short week), usage = target share
    "NFL":  {"base": 0.35, "defense": 0.38, "location": 0.13, "rest": 0.09, "pace": 0.05, "usage": 0.80},

    # NHL: base stat rate is most predictive (shots on goal / goals),
    # goalie quality is the key defensive signal (maps to defense weight),
    # location modest, rest matters on back-to-backs
    "NHL":  {"base": 0.48, "defense": 0.26, "location": 0.12, "rest": 0.09, "pace": 0.05, "usage": 0.74},

    # WNBA: smaller league, high variance — base rate is most reliable,
    # defense matters, pace significant in high-tempo games
    "WNBA": {"base": 0.48, "defense": 0.24, "location": 0.13, "rest": 0.08, "pace": 0.07, "usage": 0.74},

    # Soccer/UFC — lower data confidence, base dominates
    "Soccer": {"base": 0.60, "defense": 0.20, "location": 0.12, "rest": 0.05, "pace": 0.03, "usage": 0.74},
    "UFC":    {"base": 0.70, "defense": 0.10, "location": 0.10, "rest": 0.10, "pace": 0.00, "usage": 0.74},
}

SIGNAL_RELIABILITY = {
    "base": 0.72,       # rolling avg vs line — most reliable
    "defense": 0.65,    # opponent defense rating
    "location": 0.81,   # home/away advantage
    "rest": 0.88,       # rest days impact
    "pace": 0.58,       # pace adjustment
    "usage": 0.74,      # teammate out boost
    "blowout": 0.62,    # blowout risk
    "weather": 0.55,    # weather (MLB outdoor)
}

SIGNAL_LABELS = {
    "base": "Rolling Avg vs Line",
    "defense": "Opponent Defense",
    "location": "Home / Away",
    "rest": "Rest Days",
    "pace": "Pace Adjustment",
    "usage": "Usage / Teammate Out",
    "blowout": "Blowout Risk",
    "weather": "Weather Impact",
}

REGIME_LABELS = {
    "strong_over": ("CONFIRM OVER", "#22c55e"),
    "strong_under": ("CONFIRM UNDER", "#e04040"),
    "reprice_over": ("REPRICE", "#e8a020"),
    "reprice_under": ("REPRICE", "#e8a020"),
    "sharp_fade": ("SHARP FADE", "#9b59b6"),
    "neutral": ("NEUTRAL", "#6a7a8a"),
}

SPORT_EWMA_DECAY = {
    "NBA": 0.85,
    "MLB": 0.92,
    "NHL": 0.88,
    "WNBA": 0.85,
    "NFL": 0.80,
}

PRIZEPICKS_MULTIPLIERS = {
    2: 3.0,
    3: 5.0,
    4: 10.0,
    5: 20.0,
}

PLAYER_AVERAGES_SOCCER = {
    "Erling Haaland": {"GOALS": 0.85, "ASSISTS": 0.25, "SHOTS": 4.2},
    "Kylian Mbappe": {"GOALS": 0.75, "ASSISTS": 0.35, "SHOTS": 4.0},
    "Lionel Messi": {"GOALS": 0.45, "ASSISTS": 0.55, "SHOTS": 3.5},
    "Cristiano Ronaldo": {"GOALS": 0.65, "ASSISTS": 0.20, "SHOTS": 4.5},
    "Mohamed Salah": {"GOALS": 0.55, "ASSISTS": 0.40, "SHOTS": 3.8},
    "Harry Kane": {"GOALS": 0.70, "ASSISTS": 0.30, "SHOTS": 4.1},
    "Vinicius Jr.": {"GOALS": 0.50, "ASSISTS": 0.45, "SHOTS": 3.6},
    "Kevin De Bruyne": {"GOALS": 0.25, "ASSISTS": 0.75, "SHOTS": 2.5},
    "Jude Bellingham": {"GOALS": 0.40, "ASSISTS": 0.35, "SHOTS": 3.0},
    "Rodrygo": {"GOALS": 0.35, "ASSISTS": 0.30, "SHOTS": 2.8},
}

PLAYER_AVERAGES_UFC = {
    "Jon Jones": {"TAKEDOWNS": 2.5, "SIG_STR": 45, "CONTROL_TIME": 8.5},
    "Israel Adesanya": {"SIG_STR": 55, "TAKEDOWN_DEF": 0.95, "CONTROL_TIME": 5.5},
    "Alex Pereira": {"SIG_STR": 60, "KNOCKDOWNS": 0.5, "CONTROL_TIME": 4.5},
    "Conor McGregor": {"SIG_STR": 50, "TAKEDOWNS": 1.0, "CONTROL_TIME": 5.0},
    "Kamaru Usman": {"TAKEDOWNS": 3.0, "CONTROL_TIME": 7.5, "SIG_STR": 35},
    "Leon Edwards": {"SIG_STR": 42, "TAKEDOWNS": 1.5, "CONTROL_TIME": 6.0},
    "Charles Oliveira": {"TAKEDOWNS": 2.8, "SUB_ATTEMPTS": 1.2, "CONTROL_TIME": 6.5},
    "Dustin Poirier": {"SIG_STR": 52, "TAKEDOWN_DEF": 0.85, "CONTROL_TIME": 4.0},
}

DEFAULT_AVERAGES = {
    "NBA": {"PTS": 18.0, "REB": 5.5, "AST": 4.0, "PRA": 27.5,
            "3PM": 1.8, "STL": 1.0, "BLK": 0.8, "TO": 2.0},
    "MLB": {"HR": 0.05, "H": 0.8, "RBI": 0.3, "R": 0.3, "SO": 5.0},
    "NFL": {"PASS_YDS": 200, "RUSH_YDS": 35, "REC_YDS": 40, "TD": 0.5},
    "NHL": {"PTS": 0.45, "GOALS": 0.18, "ASSISTS": 0.27, "SOG": 1.8},
    "WNBA": {"PTS": 8.0, "REB": 3.5, "AST": 2.0, "PRA": 13.5},
    "Soccer": {"GOALS": 0.25, "ASSISTS": 0.15, "SHOTS": 2.5},
    "UFC": {"SIG_STR": 30, "TAKEDOWNS": 1.0, "CONTROL_TIME": 4.0},
    "Golf": {}, "Tennis": {},
}

STAT_NORMALIZE = {
    ("NBA", "Points"): "PTS", ("NBA", "Rebounds"): "REB", ("NBA", "Assists"): "AST",
    ("NBA", "Pts+Reb+Ast"): "PRA", ("MLB", "Home Runs"): "HR", ("MLB", "Hits"): "H",
    ("MLB", "RBIs"): "RBI", ("MLB", "Runs"): "R", ("MLB", "Strikeouts"): "SO",
    ("NFL", "Passing Yards"): "PASS_YDS", ("NFL", "Rushing Yards"): "RUSH_YDS",
    ("NFL", "Receiving Yards"): "REC_YDS", ("NFL", "Touchdowns"): "TD",
    ("NHL", "Points"): "PTS", ("NHL", "Goals"): "GOALS", ("NHL", "Assists"): "ASSISTS",
    ("NHL", "Shots On Goal"): "SOG", ("WNBA", "Points"): "PTS", ("WNBA", "Rebounds"): "REB",
    ("WNBA", "Assists"): "AST", ("WNBA", "Pts+Reb+Ast"): "PRA",
    ("MLB", "Earned Runs"): "ER", ("MLB", "Hits Allowed"): "H", ("MLB", "Total Bases"): "H",
    ("NHL", "Shots on Goal"): "SOG", ("NHL", "Goals"): "GOALS", ("NHL", "Assists"): "ASSISTS",
    ("NBA", "Pts+Rebs+Asts"): "PRA", ("NBA", "Pts+Reb"): "PRA", ("NBA", "Pts+Ast"): "PRA",
    ("NBA", "3-PT Made"): "THREE_PT", ("NBA", "Blocked Shots"): "BLK",
    ("NBA", "Steals"): "STL", ("NBA", "Turnovers"): "TOV",
    ("WNBA", "Pts+Reb+Ast"): "PRA", ("WNBA", "Pts+Reb"): "PRA",
    ("WNBA", "Pts+Ast"): "PRA",
    ("NBA", "pts"): "PTS", ("NBA", "reb"): "REB", ("NBA", "ast"): "AST",
    ("NBA", "points"): "PTS", ("NBA", "rebounds"): "REB", ("NBA", "assists"): "AST",
    ("MLB", "Strikeouts"): "SO", ("MLB", "Hits"): "H", ("MLB", "Home Runs"): "HR",
    ("Soccer", "Goals"): "GOALS", ("Soccer", "Assists"): "ASSISTS",
    ("Soccer", "Shots"): "SHOTS",
    ("UFC", "Significant Strikes"): "SIG_STR", ("UFC", "Takedowns"): "TAKEDOWNS",
    ("UFC", "Control Time"): "CONTROL_TIME",
}

TEAMMATE_OUT_BOOST = {
    "Luka Doncic": {"out_player": "Kyrie Irving", "PTS": 3.5, "AST": 1.5, "PRA": 5.0},
    "Shai Gilgeous-Alexander": {"out_player": "Jalen Williams", "PTS": 2.8, "AST": 1.2, "PRA": 4.0},
    "Nikola Jokic": {"out_player": "Jamal Murray", "PTS": 3.2, "AST": 1.8, "PRA": 5.0},
    "LeBron James": {"out_player": "Anthony Davis", "PTS": 2.5, "AST": 1.0, "PRA": 3.5},
    "Stephen Curry": {"out_player": "Draymond Green", "PTS": 3.0, "AST": 1.2, "PRA": 4.2},
    "Giannis Antetokounmpo": {"out_player": "Khris Middleton", "PTS": 2.8, "REB": 1.0, "PRA": 3.8},
    "Kevin Durant": {"out_player": "Devin Booker", "PTS": 2.5, "AST": 0.8, "PRA": 3.3},
    "Jayson Tatum": {"out_player": "Jaylen Brown", "PTS": 2.2, "AST": 0.8, "PRA": 3.0},
    "Damian Lillard": {"out_player": "Giannis Antetokounmpo", "PTS": 3.0, "AST": 1.5, "PRA": 4.5},
}

PLAYER_TEAM_MAP = {
    "LeBron James": "LAL", "Anthony Davis": "LAL", "Austin Reaves": "LAL", "D'Angelo Russell": "LAL",
    "Luka Doncic": "LAL", "Kyrie Irving": "DAL",
    "Nikola Jokic": "DEN", "Jamal Murray": "DEN", "Michael Porter Jr.": "DEN", "Aaron Gordon": "DEN",
    "Shai Gilgeous-Alexander": "OKC", "Jalen Williams": "OKC", "Chet Holmgren": "OKC", "Luguentz Dort": "OKC",
    "Giannis Antetokounmpo": "MIL", "Damian Lillard": "MIL", "Khris Middleton": "MIL", "Brook Lopez": "MIL",
    "Jayson Tatum": "BOS", "Jaylen Brown": "BOS", "Kristaps Porzingis": "BOS", "Derrick White": "BOS",
    "Stephen Curry": "GSW", "Draymond Green": "GSW", "Andrew Wiggins": "GSW",
    "Klay Thompson": "DAL",
    "Kevin Durant": "PHX", "Devin Booker": "PHX", "Bradley Beal": "PHX", "Jusuf Nurkic": "PHX",
    "Paul George": "PHI",
    "Donovan Mitchell": "CLE", "Darius Garland": "CLE", "Evan Mobley": "CLE", "Jarrett Allen": "CLE",
    "Jimmy Butler": "MIA", "Bam Adebayo": "MIA", "Tyler Herro": "MIA", "Caleb Martin": "MIA",
    "Trae Young": "ATL", "Dejounte Murray": "ATL", "Clint Capela": "ATL", "Bogdan Bogdanovic": "ATL",
    "Ja Morant": "MEM", "Jaren Jackson Jr.": "MEM", "Desmond Bane": "MEM", "Marcus Smart": "MEM",
    "Zion Williamson": "NOP", "Brandon Ingram": "NOP", "CJ McCollum": "NOP", "Jonas Valanciunas": "NOP",
    "Kawhi Leonard": "LAC", "James Harden": "LAC",
    "Joel Embiid": "PHI", "Tyrese Maxey": "PHI", "Tobias Harris": "PHI", "Kelly Oubre Jr.": "PHI",
    "Karl-Anthony Towns": "MIN", "Anthony Edwards": "MIN", "Rudy Gobert": "MIN", "Mike Conley": "MIN",
    "Domantas Sabonis": "SAC", "De'Aaron Fox": "SAS", "Keegan Murray": "SAC", "Harrison Barnes": "SAC",
    "Victor Wembanyama": "SAS", "Cade Cunningham": "DET", "Jalen Brunson": "NYK", "Paolo Banchero": "ORL",
    "Scottie Barnes": "TOR", "Alperen Sengun": "HOU", "Franz Wagner": "ORL", "Tyrese Haliburton": "IND",
    "Pascal Siakam": "IND",
}

POSITIVE_CORRELATIONS = {
    ("Luka Doncic", "Kyrie Irving"): 0.4,
    ("Nikola Jokic", "Jamal Murray"): 0.35,
    ("Stephen Curry", "Klay Thompson"): 0.3,
    ("Jayson Tatum", "Jaylen Brown"): 0.35,
    ("Shai Gilgeous-Alexander", "Jalen Williams"): 0.3,
    ("LeBron James", "Anthony Davis"): 0.3,
    ("Giannis Antetokounmpo", "Damian Lillard"): 0.3,
    ("Tyrese Haliburton", "Pascal Siakam"): 0.3,
}

SAME_PLAYER_STAT_CORRELATION = {
    ("PTS", "PRA"): 0.85, ("PRA", "PTS"): 0.85,
    ("PTS", "AST"): 0.45, ("AST", "PTS"): 0.45,
    ("PTS", "REB"): 0.30, ("REB", "PTS"): 0.30,
    ("REB", "AST"): 0.15, ("AST", "REB"): 0.15,
    ("PTS", "THREE_PT"): 0.70, ("THREE_PT", "PTS"): 0.70,
    ("PTS", "BLK"): 0.10, ("PTS", "STL"): 0.10,
    ("REB", "BLK"): 0.35, ("AST", "TOV"): 0.55,
    ("GOALS", "SOG"): 0.75, ("SOG", "GOALS"): 0.75,
    ("PTS", "SOG"): 0.80,
    ("HR", "RBI"): 0.65, ("RBI", "HR"): 0.65,
    ("H", "RBI"): 0.45, ("H", "R"): 0.50,
    ("PASS_YDS", "TD"): 0.55, ("RUSH_YDS", "TD"): 0.45,
    ("REC_YDS", "TD"): 0.40,
}

MLB_BALLPARKS = {
    "New York Yankees": {"city": "New York", "outdoor": True},
    "New York Mets": {"city": "New York", "outdoor": True},
    "Boston Red Sox": {"city": "Boston", "outdoor": True},
    "Chicago Cubs": {"city": "Chicago", "outdoor": True},
    "Chicago White Sox": {"city": "Chicago", "outdoor": True},
    "Los Angeles Dodgers": {"city": "Los Angeles", "outdoor": True},
    "Los Angeles Angels": {"city": "Anaheim", "outdoor": True},
    "San Francisco Giants": {"city": "San Francisco", "outdoor": True},
    "Seattle Mariners": {"city": "Seattle", "outdoor": True},
    "Texas Rangers": {"city": "Arlington", "outdoor": True},
    "Houston Astros": {"city": "Houston", "outdoor": False},
    "Toronto Blue Jays": {"city": "Toronto", "outdoor": True},
    "Baltimore Orioles": {"city": "Baltimore", "outdoor": True},
    "Tampa Bay Rays": {"city": "St Petersburg", "outdoor": False},
    "Cleveland Guardians": {"city": "Cleveland", "outdoor": True},
    "Detroit Tigers": {"city": "Detroit", "outdoor": True},
    "Kansas City Royals": {"city": "Kansas City", "outdoor": True},
    "Minnesota Twins": {"city": "Minneapolis", "outdoor": False},
    "Milwaukee Brewers": {"city": "Milwaukee", "outdoor": False},
    "St. Louis Cardinals": {"city": "St Louis", "outdoor": True},
    "Cincinnati Reds": {"city": "Cincinnati", "outdoor": True},
    "Pittsburgh Pirates": {"city": "Pittsburgh", "outdoor": True},
    "Philadelphia Phillies": {"city": "Philadelphia", "outdoor": True},
    "Washington Nationals": {"city": "Washington", "outdoor": True},
    "Atlanta Braves": {"city": "Atlanta", "outdoor": True},
    "Miami Marlins": {"city": "Miami", "outdoor": False},
    "Colorado Rockies": {"city": "Denver", "outdoor": True},
    "Arizona Diamondbacks": {"city": "Phoenix", "outdoor": False},
    "San Diego Padres": {"city": "San Diego", "outdoor": True},
    "Oakland Athletics": {"city": "Oakland", "outdoor": True},
}

MLB_PLAYER_TEAM_MAP = {
    "Aaron Judge": "New York Yankees",
    "Shohei Ohtani": "Los Angeles Dodgers",
    "Mookie Betts": "Los Angeles Dodgers",
    "Freddie Freeman": "Los Angeles Dodgers",
    "Juan Soto": "New York Mets",
    "Bryce Harper": "Philadelphia Phillies",
    "Ronald Acuna Jr.": "Atlanta Braves",
    "Jose Ramirez": "Cleveland Guardians",
    "Pete Alonso": "New York Mets",
    "Vladimir Guerrero Jr.": "Toronto Blue Jays",
    "Francisco Lindor": "New York Mets",
    "Bobby Witt Jr.": "Kansas City Royals",
    "Gunnar Henderson": "Baltimore Orioles",
    "Elly De La Cruz": "Cincinnati Reds",
    "Corbin Carroll": "Arizona Diamondbacks",
    "Paul Skenes": "Pittsburgh Pirates",
    "Spencer Strider": "Atlanta Braves",
    "Gerrit Cole": "New York Yankees",
    "Zack Wheeler": "Philadelphia Phillies",
    "Tarik Skubal": "Detroit Tigers",
    "Framber Valdez": "Houston Astros",
    "Logan Webb": "San Francisco Giants",
    "Yoshinobu Yamamoto": "Los Angeles Dodgers",
    "Luis Castillo": "Seattle Mariners",
    "Dylan Cease": "San Diego Padres",
    "Corbin Burnes": "Baltimore Orioles",
    "Hunter Brown": "Houston Astros",
    "Julio Rodriguez": "Seattle Mariners",
    "Yordan Alvarez": "Houston Astros",
    "Kyle Tucker": "Houston Astros",
    "Trea Turner": "Philadelphia Phillies",
    "Nolan Arenado": "St. Louis Cardinals",
    "Marcus Semien": "Texas Rangers",
    "Corey Seager": "Texas Rangers",
}

WNBA_PLAYER_IDS = {
    "A'ja Wilson": 1628932,
    "Breanna Stewart": 1626399,
    "Sabrina Ionescu": 1629887,
    "Kelsey Plum": 1628928,
    "Napheesa Collier": 1628886,
    "Caitlin Clark": 1641767,
    "Angel Reese": 1641768,
    "Alyssa Thomas": 1628961,
    "Jackie Young": 1629313,
    "Jewell Loyd": 1628932,
    "Kahleah Copper": 1628961,
    "Aliyah Boston": 1641769,
    "Rhyne Howard": 1641770,
    "Jonquel Jones": 1628886,
}

MLB_PLAYER_IDS = {
    "Aaron Judge": 592450, "Shohei Ohtani": 660271,
    "Mookie Betts": 605141, "Freddie Freeman": 518692,
    "Juan Soto": 665742, "Bryce Harper": 547180,
    "Ronald Acuna Jr.": 660670, "Jose Ramirez": 608070,
    "Pete Alonso": 624413, "Vladimir Guerrero Jr.": 665489,
    "Francisco Lindor": 596019, "Bobby Witt Jr.": 677951,
    "Gunnar Henderson": 683002, "Elly De La Cruz": 682829,
    "Corbin Carroll": 682998, "Paul Skenes": 694973,
    "Gerrit Cole": 543037, "Zack Wheeler": 554430,
    "Tarik Skubal": 669373, "Framber Valdez": 664285,
    "Logan Webb": 657277, "Luis Castillo": 622491,
    "Julio Rodriguez": 677594, "Yordan Alvarez": 670541,
    "Kyle Tucker": 663656, "Trea Turner": 607208,
    "Nolan Arenado": 571448, "Marcus Semien": 543760,
    "Corey Seager": 608369,
}

NHL_PLAYER_IDS = {
    "Connor McDavid": 8478402, "Leon Draisaitl": 8477934,
    "Nathan MacKinnon": 8477492, "David Pastrnak": 8477956,
    "Nikita Kucherov": 8476453, "Auston Matthews": 8479318,
    "Mitch Marner": 8481522, "Cale Makar": 8480069,
    "Kirill Kaprizov": 8481600, "Mikko Rantanen": 8481467,
    "Matthew Tkachuk": 8481559, "Brayden Point": 8478010,
    "Sam Reinhart": 8477998, "Aleksander Barkov": 8477493,
    "Brady Tkachuk": 8481528,
}

NBA_TEAM_PACE = {
    "MEM": 102.8, "SAC": 101.5, "BOS": 101.2,
    "DAL": 100.8, "OKC": 100.5, "LAL": 100.2,
    "DEN": 100.0, "PHX": 99.8, "GSW": 99.5,
    "NOP": 99.2, "ATL": 99.0, "IND": 98.8,
    "MIN": 98.5, "TOR": 98.3, "ORL": 98.0,
    "HOU": 97.8, "SAS": 97.5, "DET": 97.3,
    "LAC": 97.1, "MIL": 98.1, "CLE": 98.1,
    "NYK": 97.8, "MIA": 97.3, "PHI": 97.0,
}

NBA_POWER_RATINGS = {
    "BOS": 112.3, "OKC": 110.8, "DEN": 109.2,
    "MIN": 108.5, "CLE": 107.9, "NYK": 107.2,
    "IND": 106.8, "MIL": 106.1, "PHX": 105.8,
    "LAL": 105.4, "GSW": 104.9, "MEM": 104.6,
    "NOP": 103.8, "SAC": 103.5, "DAL": 103.2,
    "MIA": 102.9, "ATL": 102.4, "PHI": 102.1,
    "CHI": 101.8, "TOR": 101.5, "ORL": 101.2,
    "HOU": 100.9, "LAC": 100.6, "BKN": 100.2,
    "DET": 99.8, "CHA": 99.5, "SAS": 99.2,
    "POR": 98.9, "UTA": 98.5, "WAS": 98.1,
}

NBA_POSITION_DEFENSE = {
    "BOS": {"PG": 20.1, "SG": 19.8, "SF": 18.9, "PF": 20.2, "C": 21.4},
    "OKC": {"PG": 19.4, "SG": 20.1, "SF": 19.3, "PF": 19.8, "C": 22.1},
    "DEN": {"PG": 21.2, "SG": 21.8, "SF": 20.4, "PF": 21.1, "C": 23.2},
    "MIL": {"PG": 22.1, "SG": 21.4, "SF": 20.8, "PF": 21.5, "C": 24.1},
    "LAL": {"PG": 20.8, "SG": 21.2, "SF": 20.1, "PF": 22.4, "C": 23.8},
    "PHX": {"PG": 22.8, "SG": 23.1, "SF": 21.9, "PF": 22.2, "C": 24.8},
    "GSW": {"PG": 21.4, "SG": 22.2, "SF": 21.1, "PF": 22.8, "C": 24.2},
    "MIA": {"PG": 20.4, "SG": 21.1, "SF": 19.8, "PF": 20.9, "C": 22.8},
    "MEM": {"PG": 23.2, "SG": 22.8, "SF": 22.1, "PF": 23.4, "C": 25.1},
    "ATL": {"PG": 24.1, "SG": 23.8, "SF": 22.9, "PF": 23.2, "C": 25.4},
}

PLAYOFF_DEFENSE_WARNING = (
    "⚠️ PLAYOFF MODE: Hardcoded position defense "
    "data reflects regular season. Playoff defensive "
    "schemes change significantly. Search current "
    "matchup defense before trusting these numbers."
)

WNBA_POWER_RATINGS = {
    "New York Liberty": 112.0, "Las Vegas Aces": 111.0,
    "Connecticut Sun": 109.0, "Minnesota Lynx": 108.5,
    "Seattle Storm": 107.0, "Dallas Wings": 106.0,
    "Chicago Sky": 105.0, "Phoenix Mercury": 104.5,
    "Atlanta Dream": 104.0, "Indiana Fever": 103.5,
    "Washington Mystics": 102.0, "Los Angeles Sparks": 101.0,
    "Toronto Tempo": 103.0, "Golden State Valkyries": 102.5,
}

MLB_POWER_RATINGS = {
    "Los Angeles Dodgers": 112.0, "New York Yankees": 110.5,
    "Atlanta Braves": 109.0, "Philadelphia Phillies": 108.5,
    "Houston Astros": 108.0, "San Diego Padres": 107.5,
    "Cleveland Guardians": 107.0, "Baltimore Orioles": 106.5,
    "Minnesota Twins": 106.0, "Arizona Diamondbacks": 105.5,
    "San Francisco Giants": 104.5, "Seattle Mariners": 104.0,
    "Boston Red Sox": 103.5, "Tampa Bay Rays": 103.0,
    "Texas Rangers": 102.5, "Miami Marlins": 100.0,
    "Colorado Rockies": 97.0, "Chicago White Sox": 98.0,
    "Oakland Athletics": 97.5, "Kansas City Royals": 101.0,
    "Toronto Blue Jays": 102.0, "Chicago Cubs": 103.0,
    "St. Louis Cardinals": 102.5, "Milwaukee Brewers": 104.0,
    "Pittsburgh Pirates": 99.0, "Cincinnati Reds": 100.5,
    "Detroit Tigers": 101.5, "New York Mets": 103.5,
    "Washington Nationals": 99.5, "Los Angeles Angels": 100.0,
}

NHL_POWER_RATINGS = {
    "Florida Panthers": 110.0, "Vancouver Canucks": 109.0,
    "Colorado Avalanche": 108.5, "Boston Bruins": 108.0,
    "Dallas Stars": 107.5, "Carolina Hurricanes": 107.0,
    "Edmonton Oilers": 106.5, "New York Rangers": 106.0,
    "Tampa Bay Lightning": 105.5, "Vegas Golden Knights": 105.0,
    "Toronto Maple Leafs": 104.5, "New Jersey Devils": 104.0,
    "Minnesota Wild": 103.5, "Winnipeg Jets": 103.0,
    "Pittsburgh Penguins": 101.0, "Montreal Canadiens": 100.0,
    "Buffalo Sabres": 99.5, "Chicago Blackhawks": 98.0,
}

NBA_PLAYER_POSITIONS = {
    "Nikola Jokic": "C", "LeBron James": "SF", "Stephen Curry": "PG",
    "Giannis Antetokounmpo": "PF", "Luka Doncic": "PG",
    "Shai Gilgeous-Alexander": "PG", "Jayson Tatum": "SF",
    "Anthony Davis": "C", "Donovan Mitchell": "SG", "Damian Lillard": "PG",
    "Trae Young": "PG", "Devin Booker": "SG", "Joel Embiid": "C",
    "Tyrese Maxey": "PG", "Bam Adebayo": "C", "Ja Morant": "PG",
    "Zion Williamson": "PF", "Karl-Anthony Towns": "C",
    "Anthony Edwards": "SG", "Paolo Banchero": "PF",
    "Cade Cunningham": "PG", "Victor Wembanyama": "C",
    "Jalen Brunson": "PG", "Tyrese Haliburton": "PG",
    "Kevin Durant": "SF", "Jimmy Butler": "SF", "Kawhi Leonard": "SF",
    "Rudy Gobert": "C", "Jaylen Brown": "SG", "Darius Garland": "PG",
    "Evan Mobley": "C", "Jarrett Allen": "C", "Tyler Herro": "SG",
    "Dejounte Murray": "PG", "Jaren Jackson Jr.": "PF",
    "Desmond Bane": "SG", "CJ McCollum": "SG", "Paul George": "SF",
    "James Harden": "PG", "Tobias Harris": "SF",
    "Domantas Sabonis": "C", "De'Aaron Fox": "PG",
    "Keegan Murray": "SF", "Franz Wagner": "SF",
    "Scottie Barnes": "PF", "Alperen Sengun": "C",
    "Jalen Williams": "SG", "Chet Holmgren": "C", "Luguentz Dort": "SG",
    "Khris Middleton": "SF", "Brook Lopez": "C",
    "Kristaps Porzingis": "C", "Derrick White": "PG",
    "Andrew Wiggins": "SF", "Draymond Green": "PF",
    "Aaron Gordon": "PF", "Michael Porter Jr.": "SF",
    "Jamal Murray": "PG", "Caleb Martin": "SF",
    "Bogdan Bogdanovic": "SG", "Marcus Smart": "PG",
    "Jonas Valanciunas": "C", "Harrison Barnes": "SF",
    "Mike Conley": "PG", "Pascal Siakam": "PF",
}

NBA_REFEREE_TENDENCIES = {
    "Tony Brothers": {"foul_rate": "high", "pts_adj": 0.03},
    "Scott Foster": {"foul_rate": "high", "pts_adj": 0.03},
    "Marc Davis": {"foul_rate": "high", "pts_adj": 0.02},
    "Ken Mauer": {"foul_rate": "high", "pts_adj": 0.03},
    "James Capers": {"foul_rate": "high", "pts_adj": 0.02},
    "Bill Kennedy": {"foul_rate": "low", "pts_adj": -0.02},
    "Derrick Stafford": {"foul_rate": "low", "pts_adj": -0.02},
    "Kevin Scott": {"foul_rate": "low", "pts_adj": -0.02},
    "Jonathan Sterling": {"foul_rate": "low", "pts_adj": -0.01},
    "Tre Maddox": {"foul_rate": "low", "pts_adj": -0.01},
}

MLB_UMPIRE_TENDENCIES = {
    "Angel Hernandez": {"zone": "tight", "so_adj": -0.04},
    "CB Bucknor": {"zone": "tight", "so_adj": -0.04},
    "Vic Carapazza": {"zone": "tight", "so_adj": -0.03},
    "Jerry Meals": {"zone": "tight", "so_adj": -0.03},
    "Sam Holbrook": {"zone": "tight", "so_adj": -0.02},
    "Laz Diaz": {"zone": "large", "so_adj": 0.04},
    "Tim Welke": {"zone": "large", "so_adj": 0.03},
    "Lance Barrett": {"zone": "large", "so_adj": 0.04},
    "Dan Bellino": {"zone": "large", "so_adj": 0.03},
    "Junior Valentine": {"zone": "large", "so_adj": 0.02},
}

MLB_PITCHER_ERA = {
    "Justin Verlander": 3.20, "Gerrit Cole": 3.10, "Zack Wheeler": 3.15,
    "Shane Bieber": 3.30, "Dylan Cease": 3.40, "Pablo Lopez": 3.50,
    "Logan Webb": 3.20, "Tarik Skubal": 2.90, "Paul Skenes": 2.80,
    "Framber Valdez": 3.10, "Corbin Burnes": 3.00, "Spencer Strider": 3.05,
    "Luis Castillo": 3.40, "Yoshinobu Yamamoto": 3.00, "Kevin Gausman": 3.30,
    "Sandy Alcantara": 3.20, "Max Fried": 3.15, "Hunter Brown": 3.60,
    "George Kirby": 3.40, "Chris Sale": 3.50, "Sonny Gray": 3.70,
    "Blake Snell": 3.20, "Tony Gonsolin": 3.80, "Joe Ryan": 3.60,
    "Nestor Cortes": 3.90, "Jordan Montgomery": 3.80, "Miles Mikolas": 4.10,
    "Lance Lynn": 4.20,
}

MLB_PARK_FACTORS = {
    "Colorado Rockies": 1.15, "Cincinnati Reds": 1.08,
    "Texas Rangers": 1.06, "Chicago Cubs": 1.05,
    "Boston Red Sox": 1.04, "Philadelphia Phillies": 1.03,
    "New York Yankees": 1.02, "Atlanta Braves": 1.02,
    "Los Angeles Dodgers": 0.98, "San Francisco Giants": 0.96,
    "Oakland Athletics": 0.95, "Seattle Mariners": 0.94,
    "New York Mets": 0.97, "Houston Astros": 0.97,
    "Tampa Bay Rays": 0.96, "Minnesota Twins": 0.99,
    "Miami Marlins": 0.95, "San Diego Padres": 0.96,
}

NHL_TEAM_GOALS_FOR = {
    "EDM": 3.8, "BOS": 3.5, "TOR": 3.4,
    "COL": 3.6, "NYR": 3.3, "FLA": 3.2,
    "DAL": 3.1, "VGK": 3.0, "CAR": 3.2,
    "NJD": 3.1, "WPG": 3.3, "SEA": 3.0,
    "MIN": 2.9, "OTT": 3.1, "LAK": 2.9,
    "ANA": 2.7, "CHI": 2.7, "SJS": 2.6,
}

NHL_TEAM_GOALS_AGAINST = {
    "BOS": 2.5, "CAR": 2.6, "FLA": 2.7,
    "DAL": 2.6, "VGK": 2.7, "NYR": 2.8,
    "COL": 2.9, "EDM": 3.1, "TOR": 3.0,
    "MIN": 2.8, "WPG": 2.9, "NJD": 2.8,
    "SEA": 2.9, "LAK": 2.8, "OTT": 3.0,
    "ANA": 3.3, "CHI": 3.4, "SJS": 3.5,
}

ESPN_ATHLETE_IDS = {
    "NBA": {
        "Nikola Jokic": 3136776, "LeBron James": 1966,
        "Stephen Curry": 3975, "Giannis Antetokounmpo": 3032977,
        "Luka Doncic": 3945274, "Shai Gilgeous-Alexander": 4277905,
        "Jayson Tatum": 4065648, "Anthony Davis": 6583,
        "Donovan Mitchell": 3908809, "Damian Lillard": 6606,
        "Trae Young": 4277956, "Devin Booker": 3136193,
        "Joel Embiid": 3059318, "Tyrese Maxey": 4432816,
        "Bam Adebayo": 3907387, "Ja Morant": 4279888,
        "Zion Williamson": 4395725, "Karl-Anthony Towns": 3136196,
        "Anthony Edwards": 4594268, "Paolo Banchero": 4703249,
        "Cade Cunningham": 4432166, "Victor Wembanyama": 5105540,
        "Jalen Brunson": 3934648, "Tyrese Haliburton": 4395724,
    },
    "NFL": {
        "Patrick Mahomes": 3139477, "Josh Allen": 3918298,
        "Jalen Hurts": 4040715, "Lamar Jackson": 3916387,
        "Joe Burrow": 3915511, "Justin Herbert": 4038941,
        "Dak Prescott": 2577417, "Christian McCaffrey": 3054211,
        "Derrick Henry": 3054220, "Tyreek Hill": 3054978,
        "Justin Jefferson": 4241478, "CeeDee Lamb": 4241389,
        "Travis Kelce": 15847,
    }
}

GAME_TOTAL_LINE_THRESHOLDS = {
    "NBA":  180.0,   # game totals ~210-240
    "WNBA": 130.0,   # game totals ~155-175
    "MLB":  15.0,    # game totals ~7-12 runs
    "NHL":  8.0,     # game totals ~5-7 goals
    "NFL":  60.0,    # game totals ~40-55
    "Soccer": 4.0,   # game totals ~2-3 goals
}

PROP_CORRELATION_PAIRS = {
    # Same player different stats
    ("PTS", "PRA"):    0.85,
    ("PTS", "3PT"):    0.70,
    ("PTS", "AST"):    0.45,
    ("PTS", "REB"):    0.30,
    ("REB", "PRA"):    0.80,
    ("AST", "PRA"):    0.75,
    # MLB same player
    ("H",   "RBI"):    0.65,
    ("H",   "R"):      0.60,
    ("HR",  "RBI"):    0.80,
    ("HR",  "H"):      0.55,
    # NFL same player
    ("PASS YDS", "PASS CMP"): 0.85,
    ("RUSH YDS", "RUSH ATT"): 0.80,
    ("REC YDS",  "REC"):      0.82,
}

KALSHI_SPORT_SERIES = {
    "NBA":  ["KXNBA", "NBA"],
    "MLB":  ["KXMLB", "MLB"],
    "NFL":  ["KXNFL", "NFL"],
    "NHL":  ["KXNHL", "NHL"],
    "WNBA": ["KXWNBA", "WNBA"],
}

GOLF_TOURNAMENT_MAP = {
    "pga_championship":      "golf_pga_championship",
    "masters":               "golf_masters_tournament",
    "us_open":               "golf_us_open",
    "the_open":              "golf_the_open_championship",
    "players":               "golf_the_players_championship",
    "fedex_cup":             "golf_fedex_cup_playoff",
    "default":               "golf_pga_championship",
}

DFF_HEADERS   = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    "Accept":     "application/json, */*",
    "Referer":    "https://www.dailyfantasyfuel.com/",
    "Origin":     "https://www.dailyfantasyfuel.com",
}

DFF_SPORT_MAP = {
    "NBA":  "NBA",
    "NFL":  "NFL",
    "MLB":  "MLB",
    "NHL":  "NHL",
    "WNBA": "WNBA",
}

DFF_TEAM_MAP = {
    # NBA
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC", "San Antonio Spurs": "SA", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
    # WNBA
    "Las Vegas Aces": "LV", "New York Liberty": "NY", "Seattle Storm": "SEA",
    "Chicago Sky": "CHI", "Connecticut Sun": "CON", "Dallas Wings": "DAL",
    "Indiana Fever": "IND", "Los Angeles Sparks": "LA", "Minnesota Lynx": "MIN",
    "Phoenix Mercury": "PHX", "Washington Mystics": "WAS", "Atlanta Dream": "ATL",
}

DFF_METRIC_MAP = {
    # NBA/WNBA
    "Points":        "pts",
    "Rebounds":      "reb",
    "Assists":       "ast",
    "PRA":           "pra",
    "PR":            "pr",
    "PA":            "pa",
    "RA":            "ra",
    "Threes":        "three",
    "Steals":        "stl",
    "Blocks":        "blk",
    "Turnovers":     "to",
    "FTM":           "ftm",
    # MLB
    "Hits":          "hits",
    "Total Bases":   "tb",
    "RBI":           "rbi",
    "Runs":          "runs",
    "Strikeouts":    "k",
    "Pitching Ks":   "k",
    "Walks":         "bb",
    "HR":            "hr",
    # NHL
    "Goals":         "goals",
    "Shots":         "shots",
    "Saves":         "saves",
    # NFL
    "PassYds":       "passyds",
    "RushYds":       "rushyds",
    "RecYds":        "recyds",
    "Receptions":    "rec",
    "TDs":           "td",
}

BQ_WEIGHTS_DEFAULT = {
    "edge":      0.40,
    "alignment": 0.20,
    "agreement": 0.20,
    "volatility":0.10,
    "clv":       0.10,
}

BOVADA_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Referer":         "https://www.bovada.lv/",
    "Accept-Language": "en-US,en;q=0.9",
}

BOVADA_SPORT_MAP = {
    "NBA":  "basketball/nba",
    "MLB":  "baseball/mlb",
    "NHL":  "hockey/nhl",
    "WNBA": "basketball/wnba",
    "NFL":  "football/nfl",
    "GOLF": "golf/pga-tour",
}

SIGNAL_COLS = [
    "signal_base_positive",
    "signal_defense_positive",
    "signal_location_home",
    "signal_back_to_back",
    "signal_sharp_flag",
    "signal_usage_boost",
    "signal_blowout_risk",
    "signal_weather_active",
]

MLB_STADIUM_COORDS = {
    "NYY": (40.8296, -73.9262), "NYM": (40.7571, -73.8458),
    "BOS": (42.3467, -71.0972), "CHC": (41.9484, -87.6553),
    "CHW": (41.8299, -87.6338), "LAD": (34.0739, -118.2400),
    "LAA": (33.8003, -117.8827), "SF": (37.7786, -122.3893),
    "OAK": (37.7516, -122.2005), "SEA": (47.5914, -122.3325),
    "TEX": (32.7512, -97.0832), "HOU": (29.7573, -95.3555),
    "ATL": (33.8908, -84.4678), "MIA": (25.7781, -80.2198),
    "PHI": (39.9061, -75.1665), "WAS": (38.8730, -77.0074),
    "PIT": (40.4469, -80.0057), "CIN": (39.0975, -84.5067),
    "MIL": (43.0280, -87.9712), "STL": (38.6226, -90.1928),
    "COL": (39.7559, -104.9942), "ARI": (33.4455, -112.0667),
    "SD": (32.7076, -117.1570), "MIN": (44.9817, -93.2778),
    "DET": (42.3390, -83.0485), "CLE": (41.4962, -81.6852),
    "KC": (39.0517, -94.4803), "TB": (27.7682, -82.6534),
    "BAL": (39.2838, -76.6218), "TOR": (43.6414, -79.3894),
}

NFL_OUTDOOR_STADIUMS = {
    "BUF": (42.7738, -78.7870, True),   # Highmark Stadium — very weather-affected
    "NE":  (42.0909, -71.2643, True),   # Gillette Stadium
    "NYG": (40.8135, -74.0745, True),   # MetLife (open air)
    "NYJ": (40.8135, -74.0745, True),   # MetLife (open air)
    "BAL": (39.2780, -76.6227, True),   # M&T Bank Stadium
    "CLE": (41.5061, -81.6995, True),   # Cleveland Browns Stadium
    "PIT": (40.4468, -80.0158, True),   # Acrisure Stadium
    "CIN": (39.0955, -84.5160, True),   # Paycor Stadium
    "TEN": (36.1665, -86.7713, True),   # Nissan Stadium
    "JAC": (30.3239, -81.6373, True),   # EverBank Stadium
    "MIA": (25.9580, -80.2389, True),   # Hard Rock (open)
    "KC":  (39.0489, -94.4839, True),   # Arrowhead Stadium
    "DEN": (39.7439, -105.0201, True),  # Empower Field — high altitude
    "LV":  (36.0909, -115.1833, False), # Allegiant — dome
    "LAC": (33.9535, -118.3392, False), # SoFi — open but LA weather mild
    "LAR": (33.9535, -118.3392, False), # SoFi
    "SEA": (47.5952, -122.3316, True),  # Lumen Field — rain-affected
    "SF":  (37.4032, -121.9698, True),  # Levi's Stadium
    "ARI": (33.5277, -112.2626, False), # State Farm — dome
    "DAL": (32.7473, -97.0945, False),  # AT&T — dome
    "HOU": (29.6847, -95.4107, False),  # NRG — dome
    "IND": (39.7601, -86.1639, False),  # Lucas Oil — dome
    "MIN": (44.9736, -93.2575, False),  # US Bank — dome
    "NO":  (29.9511, -90.0812, False),  # Caesars — dome
    "ATL": (33.7554, -84.4008, False),  # Mercedes-Benz — dome
    "DET": (42.3400, -83.0456, False),  # Ford Field — dome
    "CHI": (41.8623, -87.6167, True),   # Soldier Field — weather-affected
    "GB":  (44.5013, -88.0622, True),   # Lambeau Field — most weather-affected
    "PHI": (39.9008, -75.1675, True),   # Lincoln Financial
    "WAS": (38.9077, -76.8645, True),   # FedEx Field
    "CAR": (35.2258, -80.8528, True),   # Bank of America
    "TB":  (27.9759, -82.5033, False),  # Raymond James — open but warm
}

FL_SPORT_MAP = {
    "MLB":  "mlb",
    "NBA":  "nba",
    "NFL":  "nfl",
    "NHL":  "nhl",
    "WNBA": "wnba",
    "GOLF": "pga",
}

FL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    "Referer":    "https://www.fantasylabs.com/",
    "Origin":     "https://www.fantasylabs.com",
    "Accept":     "application/json, */*",
}

GAME_TIER_THRESHOLDS = {
    "NBA":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "MLB":    {"SOVEREIGN": 0.06, "ELITE": 0.03, "APPROVED": 0.015, "LEAN": 0.005},
    "NFL":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "NHL":    {"SOVEREIGN": 0.10, "ELITE": 0.06, "APPROVED": 0.03, "LEAN": 0.01},
    "WNBA":   {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "Soccer": {"SOVEREIGN": 0.10, "ELITE": 0.06, "APPROVED": 0.03, "LEAN": 0.01},
}

BDL_PLAYER_IDS = {
    "LeBron James": 237, "Luka Doncic": 140, "Nikola Jokic": 279, "Shai Gilgeous-Alexander": 484,
    "Giannis Antetokounmpo": 15, "Jayson Tatum": 484, "Stephen Curry": 115, "Kevin Durant": 135,
    "Anthony Davis": 14, "Damian Lillard": 153, "Devin Booker": 70, "Donovan Mitchell": 300,
    "Jimmy Butler": 85, "Trae Young": 571, "Domantas Sabonis": 395, "Karl-Anthony Towns": 508,
    "Bam Adebayo": 2, "Rudy Gobert": 185, "Tyrese Haliburton": 613, "Jalen Brunson": 86,
    "Cade Cunningham": 625, "Victor Wembanyama": 794, "Paolo Banchero": 731, "Evan Mobley": 694,
    "Darius Garland": 578, "Tobias Harris": 216, "Ja Morant": 606, "Zion Williamson": 400,
    "Jamal Murray": 333, "Michael Porter Jr.": 585, "Aaron Gordon": 5, "Jalen Williams": 746,
    "Alperen Sengun": 700, "Desmond Bane": 616, "Scottie Barnes": 689, "Franz Wagner": 709,
    "De'Aaron Fox": 170, "Pascal Siakam": 400, "Kawhi Leonard": 232, "Luguentz Dort": 601,
}

ESPN_SLUG_MAP = {
    "NBA":  "basketball/nba",
    "NFL":  "football/nfl",
    "MLB":  "baseball/mlb",
    "NHL":  "hockey/nhl",
    "WNBA": "basketball/wnba",
}

PLAYER_HOME_SPLITS = {
    # True home performers
    "Nikola Jokic":       {"home": 0.07,  "away": -0.05},
    "LeBron James":       {"home": 0.05,  "away": -0.04},
    "Joel Embiid":        {"home": 0.08,  "away": -0.06},
    "Jayson Tatum":       {"home": 0.06,  "away": -0.04},
    "Luka Doncic":        {"home": 0.06,  "away": -0.04},
    "Giannis Antetokounmpo": {"home": 0.05, "away": -0.03},
    "Karl-Anthony Towns": {"home": 0.07,  "away": -0.05},
    "Anthony Davis":      {"home": 0.06,  "away": -0.04},
    "Bam Adebayo":        {"home": 0.06,  "away": -0.04},
    "Darius Garland":     {"home": 0.07,  "away": -0.05},
    # Neutral / road warriors
    "Stephen Curry":      {"home": 0.03,  "away": -0.02},
    "Kevin Durant":       {"home": 0.03,  "away": -0.02},
    "Kawhi Leonard":      {"home": 0.02,  "away": -0.01},
    "Jimmy Butler":       {"home": 0.02,  "away": -0.02},
    "Devin Booker":       {"home": 0.03,  "away": -0.02},
    # Better on the road (motivated / spotlight)
    "Shai Gilgeous-Alexander": {"home": 0.04, "away": -0.03},
    "Victor Wembanyama": {"home": 0.03,  "away": -0.02},
    "Chet Holmgren":      {"home": 0.03,  "away": -0.02},
    "Paolo Banchero":     {"home": 0.04,  "away": -0.03},
    "Scottie Barnes":     {"home": 0.04,  "away": -0.03},
}




# ═══════════════════════════════════════════════════════════════
# BETCOUNCIL TELEMETRY
# Zero-overhead timing. Results in System tab → Performance.
# ═══════════════════════════════════════════════════════════════
