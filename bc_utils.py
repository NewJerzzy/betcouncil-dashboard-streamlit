"""BetCouncil Utilities — helper functions used across the app."""
import re
import os
import json
import math
import pickle
from math import exp, factorial, log, sqrt, floor
import pandas as pd
from datetime import datetime, date, timedelta
import unicodedata
from functools import lru_cache
from scipy import stats as scipy_stats

# Inline to avoid circular import through config.py (which imports streamlit)
SPORT_EWMA_DECAY = {"NBA": 0.82, "MLB": 0.90, "NHL": 0.85, "WNBA": 0.82, "NFL": 0.78}

# ── Constants inlined from config.py ────────────────────────────────────────
# config.py imports streamlit and cannot be imported here (circular import).
# These pure-data constants are duplicated here verbatim from config.py.
TIER_THRESHOLDS = {
    "NBA":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "MLB":    {"SOVEREIGN": 0.06, "ELITE": 0.03, "APPROVED": 0.015,"LEAN": 0.008},
    "NFL":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "NHL":    {"SOVEREIGN": 0.10, "ELITE": 0.07, "APPROVED": 0.035,"LEAN": 0.015},
    "WNBA":   {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "GOLF":   {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "TENNIS": {"SOVEREIGN": 0.15, "ELITE": 0.10, "APPROVED": 0.05, "LEAN": 0.02},
    "SOCCER": {"SOVEREIGN": 0.10, "ELITE": 0.07, "APPROVED": 0.035,"LEAN": 0.015},
    "UFC":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
}

GAME_TIER_THRESHOLDS = {
    "NBA":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "MLB":    {"SOVEREIGN": 0.06, "ELITE": 0.03, "APPROVED": 0.015, "LEAN": 0.005},
    "NFL":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "NHL":    {"SOVEREIGN": 0.10, "ELITE": 0.06, "APPROVED": 0.03, "LEAN": 0.01},
    "WNBA":   {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "Soccer": {"SOVEREIGN": 0.10, "ELITE": 0.06, "APPROVED": 0.03, "LEAN": 0.01},
}

PRIZEPICKS_MULTIPLIERS = {2: 3.0, 3: 5.0, 4: 10.0, 5: 20.0}

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
    ("NHL", "Shots on Goal"): "SOG",
    ("NBA", "Pts+Rebs+Asts"): "PRA", ("NBA", "Pts+Reb"): "PRA", ("NBA", "Pts+Ast"): "PRA",
    ("NBA", "3-PT Made"): "THREE_PT", ("NBA", "Blocked Shots"): "BLK",
    ("NBA", "Steals"): "STL", ("NBA", "Turnovers"): "TOV",
    ("WNBA", "Pts+Reb"): "PRA", ("WNBA", "Pts+Ast"): "PRA",
    ("NBA", "pts"): "PTS", ("NBA", "reb"): "REB", ("NBA", "ast"): "AST",
    ("NBA", "points"): "PTS", ("NBA", "rebounds"): "REB", ("NBA", "assists"): "AST",
    ("Soccer", "Goals"): "GOALS", ("Soccer", "Assists"): "ASSISTS", ("Soccer", "Shots"): "SHOTS",
    ("UFC", "Significant Strikes"): "SIG_STR", ("UFC", "Takedowns"): "TAKEDOWNS",
    ("UFC", "Control Time"): "CONTROL_TIME",
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

NBA_TEAM_PACE = {
    "MEM": 102.8, "SAC": 101.5, "BOS": 101.2, "DAL": 100.8, "OKC": 100.5, "LAL": 100.2,
    "DEN": 100.0, "PHX": 99.8, "GSW": 99.5, "NOP": 99.2, "ATL": 99.0, "IND": 98.8,
    "MIN": 98.5, "TOR": 98.3, "ORL": 98.0, "HOU": 97.8, "SAS": 97.5, "DET": 97.3,
    "LAC": 97.1, "MIL": 98.1, "CLE": 98.1, "NYK": 97.8, "MIA": 97.3, "PHI": 97.0,
}

NBA_POWER_RATINGS = {
    "BOS": 112.3, "OKC": 110.8, "DEN": 109.2, "MIN": 108.5, "CLE": 107.9, "NYK": 107.2,
    "IND": 106.8, "MIL": 106.1, "PHX": 105.8, "LAL": 105.4, "GSW": 104.9, "MEM": 104.6,
    "NOP": 103.8, "SAC": 103.5, "DAL": 103.2, "MIA": 102.9, "ATL": 102.4, "PHI": 102.1,
    "CHI": 101.8, "TOR": 101.5, "ORL": 101.2, "HOU": 100.9, "LAC": 100.6, "BKN": 100.2,
    "DET": 99.8, "CHA": 99.5, "SAS": 99.2, "POR": 98.9, "UTA": 98.5, "WAS": 98.1,
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
# ── End of inlined constants ─────────────────────────────────────────────────


@lru_cache(maxsize=2048)
def safe_float(val, default: float = 0.0) -> float:
    """Type-safe float conversion with fallback.

    Handles all common bad-value cases:
      - None            → default (short-circuit before float())
      - ""  (empty str) → default (float("") raises ValueError)
      - "abc" (non-num) → default (ValueError)
      - lists / dicts   → lru_cache will TypeError before entry; wrapped below

    lru_cache accelerates repeated calls with the same val (e.g. odds strings).
    val must be hashable; mutable types are not valid inputs anyway.
    """
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default



# ── Team name canonicalization (declansx pattern) ────────────────────────────
try:
    from team_canon import canon as canon_team, match_teams, match_players, merge_by_canon
    _TEAM_CANON_AVAILABLE = True
except ImportError:
    _TEAM_CANON_AVAILABLE = False
    def canon_team(name, sport=""): return name
    def match_teams(a, b, sport="", threshold=0.82): return a.lower().strip() == b.lower().strip()
    def match_players(a, b, threshold=0.88): return a.lower().strip() == b.lower().strip()
    def merge_by_canon(primary, secondary, **kwargs): return primary


@lru_cache(maxsize=4096)
def normalize_name(s: str) -> str:
    if not s:
        return ""
    try:
        s = unicodedata.normalize("NFD", str(s))
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = re.sub(r"\s+(jr|sr|ii|iii)\.?$", "", s.lower().strip())
        s = s.replace("-", " ").replace(".", "").replace("'", "")
        return re.sub(r"\s+", " ", s).strip()
    except (TypeError, AttributeError):
        return ""


def american_to_prob(american_odds) -> float:
    """Convert American odds to implied probability."""
    try:
        o = float(american_odds)
        if o == 0:
            return 0.5
        if o > 0:
            return 100.0 / (o + 100.0)
        return abs(o) / (abs(o) + 100.0)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.5


def no_vig_prob(over_american, under_american) -> float:
    """Calculate no-vig true probability from both sides (additive/proportional method)."""
    try:
        over_imp  = american_to_prob(over_american)
        under_imp = american_to_prob(under_american)
        total = over_imp + under_imp
        if total <= 0:
            return 0.5
        return round(over_imp / total, 4)
    except (TypeError, ValueError):
        return 0.5


def no_vig_prob_shin(over_american, under_american) -> float:
    """
    Shin method devig — more accurate for asymmetric markets (heavy faves/longshots).
    Used by sharp shops for props priced +200 to +1000.
    Accounts for favourite-longshot bias by solving for the vig iteratively.
    Reference: Shin (1993), Pinnacle educational resources.
    """
    try:
        p1 = american_to_prob(over_american)
        p2 = american_to_prob(under_american)
        total = p1 + p2
        if total <= 0 or total == 1.0:
            return no_vig_prob(over_american, under_american)
        z = total - 1.0   # vig/hold

        # Shin's formula: solve for fair probability accounting for longshot bias
        # p_fair = (sqrt(z^2 + 4*(1-z)*p_imp^2) - z) / (2*(1-z))
        if z <= 0 or z >= 1:
            return no_vig_prob(over_american, under_american)

        shin_p1 = (sqrt(z**2 + 4*(1-z)*p1**2) - z) / (2*(1-z))
        shin_p2 = (sqrt(z**2 + 4*(1-z)*p2**2) - z) / (2*(1-z))
        shin_total = shin_p1 + shin_p2
        if shin_total <= 0:
            return no_vig_prob(over_american, under_american)
        return round(shin_p1 / shin_total, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return no_vig_prob(over_american, under_american)


def no_vig_prob_log(over_american, under_american) -> float:
    """
    Logarithmic devig — produces slightly more accurate fair prices on
    extreme longshots by applying log-space normalization.
    Used by some sharp books for HR and high-odds props.
    """
    try:
        p1 = american_to_prob(over_american)
        p2 = american_to_prob(under_american)
        if p1 <= 0 or p2 <= 0:
            return no_vig_prob(over_american, under_american)
        # Log method: normalize in log space
        log_p1 = log(p1)
        log_p2 = log(p2)
        log_total = log_p1 + log_p2
        # Fair odds in log space
        log_fair_p1 = log_p1 - (log_total / 2)
        log_fair_p2 = log_p2 - (log_total / 2)
        fair_p1 = exp(log_fair_p1)
        fair_p2 = exp(log_fair_p2)
        denom = fair_p1 + fair_p2
        if denom <= 0:
            return no_vig_prob(over_american, under_american)
        return round(fair_p1 / denom, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return no_vig_prob(over_american, under_american)


def no_vig_prob_probit(over_american, under_american) -> float:
    """
    Probit devig — best method for NBA/WNBA counting stats (PTS/REB/AST).
    Maps implied probs to standard normal Z-space, strips vig in Z-space,
    converts back. Outperforms additive for symmetric counting stat markets.
    Validated by EVSharps cheat sheet: Probit is their default method.
    """
    try:
        p_over  = american_to_prob(over_american)
        p_under = american_to_prob(under_american)
        total   = p_over + p_under
        if total <= 0:
            return no_vig_prob(over_american, under_american)
        # Normalize
        p_over_norm  = min(max(p_over  / total, 0.0001), 0.9999)
        p_under_norm = min(max(p_under / total, 0.0001), 0.9999)
        # Map to Z-space, average (Probit devig standard — Buchdahl 2015)
        z_over  = scipy_stats.norm.ppf(p_over_norm)
        z_under = scipy_stats.norm.ppf(p_under_norm)
        z_fair  = (z_over - z_under) / 2   # average in probit space
        fair_p  = float(scipy_stats.norm.cdf(z_fair))
        return round(fair_p, 4)
    except Exception:
        return no_vig_prob(over_american, under_american)


# EVSharps BEST book+devig combinations — extracted from record.js (Probit method, 100+ bet samples)
# Format: {sport: {book: [(prop, devig_combo), ...]}}  ordered by ROI descending
EV_BEST_COMBOS = {
    "NBA": {
        "fd":   [("reb","circa"),("reb","dk"),("reb","pn+circa+hr"),("3ptm","pn+dk"),("3ptm","pn"),("3ptm","espn"),("3ptm","circa"),("ast","circa"),("ast","espn+hr"),("blk","hr"),("pts","circa"),("pts","dk+espn"),("pts+ast","dk+espn"),("pts+reb","espn"),("reb+ast","dk+espn"),("reb+ast","hr")],
        "dk":   [("dd","pn"),("pts","fd"),("pts","espn+hr"),("pts+ast","fd"),("pts+reb","hr"),("pts+reb+ast","pn"),("pts+reb+ast","fd"),("reb","pn"),("reb","pn+fd"),("reb+ast","espn")],
        "mgm":  [("3ptm","fd+dk"),("ast","pn"),("dd","espn"),("pts","fd+dk"),("pts","fd"),("pts+ast","fd"),("pts+reb","fd"),("pts+reb+ast","pn+fd"),("reb+ast","fd")],
        "espn": [("ast","bv"),("ast","fd+dk"),("blk","hr"),("pts","fd"),("pts+ast","fd"),("pts+reb","fd"),("pts+reb+ast","pn"),("reb","pn+espn+mgm")],
        "hr":   [("reb+ast","dk+espn"),("reb","fd+dk"),("pts+reb+ast","mgm"),("pts+reb","fd+dk"),("pts+ast","fd"),("pts+ast","dk"),("pts","espn"),("pts","fd"),("pts","pn"),("3ptm","circa")],
        "b365": [("3ptm","dk"),("ast","fd+espn+mgm"),("pts","fd"),("pts+ast","bv"),("pts+ast","fd"),("pts+ast","dk")],
        "fn":   [("pts","circa"),("pts","dk"),("reb","dk"),("reb+ast","dk"),("3ptm","circa"),("ast","circa")],
        "br":   [("pts","fd"),("reb","fd+dk"),("pts+reb+ast","pn+dk"),("3ptm","dk"),("ast","dk"),("blk","mgm")],
        "bv":   [("reb","pn"),("reb","fd"),("pts","pn"),("pts+ast","dk"),("dd","pn"),("dd","mgm"),("ast","pn")],
        "cz":   [("pts","pn"),("reb","fd"),("ast","hr")],
    },
    "MLB": {
        "best": [("hr","pn+fd"),("hr","pn+circa"),("hr","pn+circa+espn"),("double","fd"),("double","px")],
        "fd":   [("k","fd+dk"),("double","espn"),("double","b365"),("double","dk"),("double","mgm")],
        "dk":   [("double","fd"),("hr","kal"),("h","fd+espn+mgm"),("double","px"),("k","nv+circa")],
        "mgm":  [("hr","pn+fd"),("double","px"),("er","dk"),("double","fd+dk"),("double","dk")],
        "espn": [("double","hr"),("hr","kal"),("double","fd"),("double","dk"),("k","espn+hr")],
        "br":   [("double","b365"),("double","fd+dk"),("double","fd"),("double","dk+espn"),("double","espn+hr")],
        "hr":   [("double","fd+espn+mgm"),("double","fd"),("k","kal"),("outs","nv"),("k","pn+fd")],
        "bv":   [("tb","pn+dk"),("double","fd"),("tb","kal"),("rbi","dk+espn"),("double","dk+espn")],
        "cz":   [("tb","pn+dk"),("tb","dk+espn"),("double","mgm"),("tb","hr"),("tb","espn+hr")],
        "bol":  [("hr","b365"),("k","espn+hr"),("tb","pn+dk"),("h+r+rbi","dk+espn"),("tb","pn+espn+hr")],
        "fn":   [("hr","px"),("k","re+pn"),("k","dk"),("rbi","dk"),("k","kal")],
        "re":   [("k","espn+hr"),("tb","espn+hr"),("tb","espn"),("tb","hr"),("h","nv")],
        "b365": [("hr","re+fd+dk+espn"),("hr","fd+dk"),("hr","fd+espn+mgm"),("double","fd"),("k","nv")],
        "nv":   [("hr","pn+circa"),("hr","pn"),("hr","pn+circa+hr"),("hr","re+pn"),("tb","kal")],
        "px":   [("hr","pn+circa"),("hr","kal"),("double","b365"),("double","dk"),("single","hr")],
        "kal":  [("hr","pn+circa"),("hr","pn+circa+hr"),("hr","pn+circa+espn+hr"),("hr","re+pn"),("hr","fd+dk")],
    },
    "NHL": {
        "best": [("sog","px"),("sv","mgm"),("atgs","re+fd+dk"),("atgs","bv"),("pts","circa+espn")],
        "fd":   [("atgs","dk"),("atgs","b365"),("atgs","dk+espn"),("atgs","circa"),("sog","pn+espn")],
        "mgm":  [("pts","bol"),("atgs","dk+espn"),("sog","pn+espn"),("atgs","fd"),("sog","pn")],
        "fn":   [("atgs","fd"),("atgs","bv"),("atgs","pn+circa+hr"),("ast","re+pn"),("atgs","pn")],
        "br":   [("atgs","fd+dk"),("atgs","re+fd+dk"),("atgs","bv"),("atgs","fd+dk+bol"),("atgs","re+fd+dk+espn")],
        "b365": [("atgs","re+fd+dk"),("atgs","fd+dk"),("atgs","re+fd+dk+espn"),("atgs","bv"),("atgs","fd")],
        "bv":   [("pts","hr"),("ast","pn+espn"),("sog","fd+espn+mgm"),("sog","dk+espn"),("ast","pn+espn+hr")],
        "dk":   [("pts","re+fd+dk"),("atgs","pn+circa+espn+hr"),("atgs","fd"),("atgs","pn+circa+hr"),("atgs","pn+espn")],
        "espn": [("atgs","hr"),("pts","hr"),("pts","pn+dk"),("sog","fd+dk"),("pts","mgm")],
        "cz":   [("sog","pn+espn+hr"),("sog","espn"),("atgs","pn+espn+hr"),("pts","dk"),("sog","espn+hr")],
        "hr":   [("pts","bol"),("sog","circa"),("pts","pn+dk"),("sog","pn"),("sog","fd")],
        "re":   [("atgs","b365"),("sog","dk"),("ast","pn"),("ast","pn+dk"),("pts","dk")],
    },
    "NFL": {},  # insufficient data in probit method for 100+ samples
    "WNBA": {
        "best": [("3ptm","fd+dk"),("reb","fd+dk"),("pts","fd+dk"),("reb","re+fd+dk"),("reb","re+fd+dk+espn")],
        "fd":   [("3ptm","re+fd+dk"),("pts","fd+espn+mgm"),("reb","re+fd+dk"),("reb","dk"),("pts","mgm")],
        "dk":   [("reb","re+fd+dk"),("reb","fd"),("reb","re+espn"),("reb","bol"),("reb","espn")],
        "cz":   [("reb","fd"),("reb","bol"),("reb","dk"),("reb","dk+espn"),("reb","re")],
        "fn":   [("3ptm","bol"),("pts","espn+hr"),("reb","fd"),("reb","re+espn"),("pts","hr")],
        "br":   [("3ptm","espn"),("3ptm","re+espn"),("pts","dk"),("pts","dk+espn"),("3ptm","re")],
        "hr":   [("pts","mgm"),("reb","dk"),("3ptm","re"),("pts","dk+espn"),("pts","dk")],
        "espn": [("reb","dk"),("pts","re+espn"),("pts","mgm"),("pts","dk"),("reb","re")],
        "mgm":  [("reb","re+fd+dk"),("reb","fd+dk"),("reb","fd"),("reb","dk"),("pts","fd+dk")],
    },
}

# Prop types that use Probit devig (counting stats — symmetric, normal distribution)
PROBIT_PROPS = {"pts","reb","ast","pra","pts+reb","pts+ast","reb+ast","pts+reb+ast","dd","td","stl","blk","3ptm","to","min","g","a","sog","pim"}
# Prop types that use Shin devig (longshot/asymmetric)
SHIN_PROPS   = {"hr","goals","td_scorer","first_basket","anytime_td"}


def no_vig_prob_power(over_american, under_american) -> float:
    """
    Power/Exponential oversum devig — solves for exponent k such that:
    p_fav^k + p_dog^k = 1
    Corrects for Favourite-Longshot Bias: sharp books hide more vig on underdogs.
    Superior to linear normalization for asymmetric markets.
    """
    try:
        p_over  = american_to_prob(over_american)
        p_under = american_to_prob(under_american)
        total   = p_over + p_under
        if total <= 1.0:
            return no_vig_prob(over_american, under_american)
        # Binary search for k such that p_over^k + p_under^k = 1
        lo, hi = 0.5, 3.0
        for _ in range(50):
            k   = (lo + hi) / 2
            val = p_over**k + p_under**k
            if val > 1.0:
                lo = k
            else:
                hi = k
        k = (lo + hi) / 2
        fair_p = p_over**k / (p_over**k + p_under**k)
        return round(float(fair_p), 4)
    except Exception:
        return no_vig_prob(over_american, under_american)


def devig_best(over_american, under_american, market_type="standard", prop_key="") -> float:
    """
    Auto-select best devig method by market/prop type.
    Power:   Asymmetric markets (spreads, totals, game lines)
    Probit:  NBA/WNBA counting stats (PTS/REB/AST) — EVSharps default
    Shin:    HR/TD scorers/goals/longshots (+200 to +800)
    Log:     Extreme longshots (+500+)
    Additive: Fallback
    """
    try:
        prop_lower = (prop_key or "").lower().replace(" ","").replace("+","").replace("_","")
        o_val = float(over_american) if over_american else 0

        # Probit for counting stats
        if any(p in prop_lower for p in ["pts","reb","ast","pra","dd","stl","blk","min","3pt","points","rebounds","assists","blocks","steals","minutes","threes","three","combo","double"]):
            return no_vig_prob_probit(over_american, under_american)

        # Shin for longshot/asymmetric props
        if market_type == "longshot" or prop_lower in ["hr","goals","td"] or (200 <= o_val < 500):
            return no_vig_prob_shin(over_american, under_american)

        # Log for extreme longshots
        if o_val >= 500:
            return no_vig_prob_log(over_american, under_american)

        # Power for near-even markets (spreads, game totals, -200 to +200)
        return no_vig_prob_power(over_american, under_american)
    except (TypeError, ValueError):
        return no_vig_prob(over_american, under_american)


def kelly_with_edge_decay(edge, odds_american, time_to_lock_minutes=None,
                          pinnacle_open=True, circa_open=True,
                          fraction=0.25) -> float:
    """
    Kelly criterion with edge decay and liquidity multiplier.
    Early lines (high uncertainty): scale down — edge hasn't matured yet.
    Late lines (high liquidity, both sharp books open): scale up to 0.5x Kelly.

    Args:
        edge:                 Model edge (e.g. 0.08 = 8%)
        odds_american:        American odds for the bet
        time_to_lock_minutes: Minutes until game/prop locks (None = unknown)
        pinnacle_open:        Pinnacle still accepting bets at high limits
        circa_open:           Circa still accepting bets at high limits
        fraction:             Base fractional Kelly (default 0.25 = quarter Kelly)

    Returns:
        Recommended bet size as fraction of bankroll (e.g. 0.03 = 3%)
    """
    try:
        odds = float(odds_american)
        # Juice-aware: use net odds after implicit vig cost
        b_gross = (odds / 100) if odds > 0 else (100 / abs(odds))
        # Estimate juice cost: at -110 both sides, vig ≈ 4.55%
        # Net b adjusts for the cost of being wrong compounding
        b = b_gross
        # Derive true win prob from Kelly math: p = (b+1)*edge / (b*(1+edge))
        # This is the proper solve vs the hardcoded 0.524+edge offset
        # which only works at -110. At -200 or +150 it's materially wrong.
        if b > 0:
            p = max(0.01, min(0.99, (b + 1) * (0.5 + edge/2) / (b + 1)))
            # Simplified: p_fair ≈ 1/(1+1/b) + edge_fraction
            p = max(0.01, min(0.99, b / (b + 1) + edge * (1 / (b + 1))))
        else:
            p = max(0.01, min(0.99, 0.524 + edge))  # fallback
        q    = 1.0 - p
        kelly_full = (b * p - q) / b
        if kelly_full <= 0:
            return 0.0

        # Edge decay multiplier based on time to lock
        if time_to_lock_minutes is None:
            decay_mult = 1.0   # unknown — use base fraction
        elif time_to_lock_minutes > 240:
            decay_mult = 0.60  # >4hr before lock: high uncertainty
        elif time_to_lock_minutes > 60:
            decay_mult = 0.80  # 1-4hr: maturing
        elif time_to_lock_minutes > 20:
            decay_mult = 1.00  # 20-60min: solid signal
        else:
            decay_mult = 1.20  # <20min: fully verified market

        # Liquidity multiplier: both sharp books open = higher confidence
        if pinnacle_open and circa_open:
            liquidity_mult = min(2.0, 1.0 + (decay_mult - 1.0) * 0.5 + 0.2)
            final_fraction = min(0.50, fraction * liquidity_mult)
        else:
            final_fraction = fraction * decay_mult

        return round(kelly_full * final_fraction, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def compute_brier_score(history) -> dict:
    """
    Brier Score: mean squared error of probability predictions vs outcomes.
    BS = (1/N) * sum((P_pred - outcome)^2)
    Range: 0 (perfect) to 1 (worst). A fair coin flip = 0.25.
    Alert threshold: BS > 0.25 means model is worse than random.

    Also computes Log Loss and rolling Z-score vs closing market.
    Returns dict with lifetime, L30, L7 windows.
    """
    def _brier_window(records):
        if not records:
            return None
        scores = []
        log_losses = []
        for r in records:
            outcome = r.get("outcome", "")
            prob    = r.get("prob") or r.get("Prob")
            if outcome not in ("WIN", "LOSS") or prob is None:
                continue
            try:
                p   = float(str(prob).replace("%","")) / (100 if "%" in str(prob) else 1)
                p   = max(0.01, min(0.99, p))
                y   = 1.0 if outcome == "WIN" else 0.0
                scores.append((p - y) ** 2)
                log_losses.append(-(y * log(p) + (1 - y) * log(1 - p)))
            except (ValueError, TypeError):
                continue
        if not scores:
            return None
        bs  = round(sum(scores) / len(scores), 4)
        ll  = round(sum(log_losses) / len(log_losses), 4)
        n   = len(scores)
        # Alert: if BS > 0.25, model underperforming random
        alert = bs > 0.25
        grade = "ELITE" if bs < 0.20 else "GOOD" if bs < 0.22 else "FAIR" if bs < 0.25 else "NEEDS WORK"
        return {"brier_score": bs, "log_loss": ll, "n": n, "alert": alert, "grade": grade}

    if not history:
        return {}

    from datetime import datetime, timedelta
    now = datetime.now()

    def _filter_window(days):
        cutoff = now - timedelta(days=days)
        return [r for r in history if r.get("timestamp") and
                _parse_dt(r["timestamp"]) >= cutoff]

    def _parse_dt(ts):
        try:
            return datetime.fromisoformat(str(ts)[:19])
        except Exception:
            return datetime.min

    return {
        "lifetime": _brier_window(history),
        "L30":      _brier_window(_filter_window(30)),
        "L7":       _brier_window(_filter_window(7)),
    }


def compute_calibration_zscore(history) -> dict:
    """
    Z-score of model predictions vs closing market (Pinnacle no-vig).
    Z > 2.0 = model significantly overestimates edge (danger)
    Z < -2.0 = model underestimates edge (opportunity)
    """
    clv_values = [
        r.get("clv_capture", {}).get("clv_vs_novig")
        for r in (history or [])
        if r.get("clv_capture", {}).get("clv_resolved")
        and r.get("clv_capture", {}).get("clv_vs_novig") is not None
    ]
    if len(clv_values) < 10:
        return {"z_score": None, "n": len(clv_values), "alert": False}
    n    = len(clv_values)
    mean = sum(clv_values) / n
    var  = sum((v - mean)**2 for v in clv_values) / n
    std  = var**0.5 if var > 0 else 0.001
    z    = round(mean / (std / n**0.5), 3)
    return {
        "z_score":   z,
        "mean_clv":  round(mean, 4),
        "std_clv":   round(std, 4),
        "n":         n,
        "alert":     abs(z) > 2.0,
        "direction": "overconfident" if z < -2.0 else "underconfident" if z > 2.0 else "calibrated",
    }


def get_best_devig_combo(sport, book, prop):
    """Return the best sharp devig combination for a given sport/book/prop per EVSharps data."""
    sport_combos = EV_BEST_COMBOS.get(sport.upper(), {})
    book_combos  = sport_combos.get(book.lower(), [])
    prop_lower   = prop.lower().replace(" ","").replace("_","")
    for p, devig in book_combos:
        if p.replace("+","") == prop_lower or p == prop_lower:
            return devig
    return None


def compute_clv(placement_odds_american, closing_odds_american, side="OVER") -> float:
    """
    Compute Closing Line Value (CLV) — Buchdahl methodology.
    CLV = implied prob at placement vs implied prob at close (no-vig).
    Positive CLV = you got better odds than the market closed at = +EV.
    CLV is a more reliable indicator of skill than win/loss over small samples.
    Per Buchdahl: consistent +CLV over 50+ bets proves skill vs luck.

    NOTE: This function uses single-sided implied prob (with vig).
    For the gold-standard no-vig CLV, use compute_clv_novig() with
    both over and under odds. Always prefer compute_clv_novig().

    Returns CLV as a percentage (e.g. 0.05 = 5% CLV).
    """
    try:
        placement_prob = american_to_prob(placement_odds_american)
        closing_prob   = american_to_prob(closing_odds_american)
        if placement_prob <= 0 or closing_prob <= 0:
            return 0.0
        # CLV = closing implied prob - placement implied prob
        # Positive means you got better odds (lower implied prob = better odds)
        clv = closing_prob - placement_prob
        return round(clv, 4)
    except (TypeError, ValueError):
        return 0.0


def compute_clv_novig(placement_over, placement_under,
                      closing_over, closing_under, side="OVER") -> float:
    """
    CLV vs no-vig closing line (gold standard — Pinnacle methodology).
    Removes vig from both placement and closing odds before comparing.
    This is the most accurate CLV measure used by sharp shops.
    """
    try:
        placement_fair = no_vig_prob_shin(placement_over, placement_under)
        closing_fair   = no_vig_prob_shin(closing_over, closing_under)
        if side.upper() == "UNDER":
            placement_fair = 1 - placement_fair
            closing_fair   = 1 - closing_fair
        clv = closing_fair - placement_fair
        return round(clv, 4)
    except (TypeError, ValueError):
        return 0.0


def devig_odds(american_odds):
    if american_odds is None:
        return None
    try:
        odds = float(american_odds)
        if odds > 0:
            implied = 100 / (odds + 100)
        else:
            implied = abs(odds) / (abs(odds) + 100)
        return round(implied, 4)
    except (pickle.UnpicklingError, OSError, EOFError):
        return None


# calculate_edge — single source of truth for sportsbook edge
def calculate_edge(fair_prob, side="OVER", sport="NBA"):
    """Returns signed edge: positive = good bet. Breakeven = 52.4% (-110 juice)."""
    return round(float(fair_prob) - 0.524, 4)


def compute_std_dev(game_values, decay=0.85, sport=None):
    if not game_values or len(game_values) < 3:
        return None
    if sport:
        decay = SPORT_EWMA_DECAY.get(sport, decay)
    weights = [decay**i for i in range(len(game_values))]
    total_weight = sum(weights)
    weighted_mean = sum(v * w for v, w in zip(reversed(game_values), weights)) / total_weight
    weighted_var = sum(w * (v - weighted_mean)**2 for v, w in zip(reversed(game_values), weights)) / total_weight
    return round(weighted_var**0.5, 3)


def compute_fair_prob(line, avg, std_dev, side="OVER"):
    if avg <= 0:
        return 0.5
    if std_dev is None or std_dev <= 0:
        std_dev = avg * 0.40
    adjusted_line = line + 0.5 if (line == int(line)) else line
    if side.upper() == "OVER":
        prob = 1 - scipy_stats.norm.cdf(adjusted_line, loc=avg, scale=std_dev)
    else:
        prob = scipy_stats.norm.cdf(adjusted_line, loc=avg, scale=std_dev)
    return round(max(0.10, min(0.90, prob)), 4)  # widened from 0.20-0.80 (too conservative)


def compute_fair_prob_negbinom(line, avg, std_dev, side="OVER"):
    """Negative Binomial fair probability — better fit than the normal approximation
    for overdispersed counting stats (3PT attempts, shots on goal, strikeouts) where
    empirical variance exceeds the mean. Falls back to compute_fair_prob (normal
    approx) automatically when variance <= mean, since NB is undefined there and
    normal/Poisson already fit cleanly in that regime.
    std_dev should come from compute_std_dev() on real game-log values so the
    variance reflects actual observed dispersion, not an assumed constant."""
    if avg <= 0:
        return 0.5
    if std_dev is None or std_dev <= 0:
        return compute_fair_prob(line, avg, std_dev, side)
    variance = std_dev ** 2
    if variance <= avg:
        return compute_fair_prob(line, avg, std_dev, side)
    r = (avg ** 2) / (variance - avg)
    p = r / (r + avg)
    adjusted_line = line + 0.5 if (line == int(line)) else line
    k = math.floor(adjusted_line)
    if side.upper() == "OVER":
        prob = scipy_stats.nbinom.sf(k, r, p)
    else:
        prob = scipy_stats.nbinom.cdf(k, r, p)
    return round(max(0.10, min(0.90, prob)), 4)


def compute_fair_prob_skellam(line, mu_a, mu_b, side="OVER"):
    """Skellam distribution fair probability for goal/run differential markets
    (soccer/hockey spreads and totals on the margin) — models the difference of
    two independent Poisson-distributed scoring rates. mu_a/mu_b are each team's
    expected goals/runs for the game (xG-style inputs, not season averages)."""
    if mu_a <= 0 or mu_b <= 0:
        return 0.5
    adjusted_line = line + 0.5 if (line == int(line)) else line
    k = math.floor(adjusted_line)
    if side.upper() == "OVER":
        prob = scipy_stats.skellam.sf(k, mu_a, mu_b)
    else:
        prob = scipy_stats.skellam.cdf(k, mu_a, mu_b)
    return round(max(0.20, min(0.80, prob)), 4)


ELO_DEFAULT_RATING = 1500.0
ELO_K_FACTOR = {"NFL": 20, "NBA": 20, "WNBA": 20, "NHL": 20, "Soccer": 20, "MLB": 20}

# Margin-of-victory multiplier caps per sport — prevents extreme blowouts
# from dominating the Elo signal (a 50-pt NBA blowout shouldn't move ratings 5x).
ELO_MOV_CAP = {"NFL": 28, "NBA": 35, "WNBA": 30, "NHL": 5, "Soccer": 5, "MLB": 12}

# Sport-specific MOV scale factors — tuned so that a "normal" margin
# produces a multiplier near 1.0 and an extreme margin caps near 2.0.
ELO_MOV_SCALE = {"NFL": 14.0, "NBA": 17.5, "WNBA": 15.0, "NHL": 2.5,
                 "Soccer": 2.5, "MLB": 6.0}


def elo_expected_score(rating_a, rating_b):
    """Standard Elo win-probability formula for team A vs team B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def elo_update(rating_a, rating_b, score_a, k=20, margin=None, sport=None):
    """Incremental Elo update after a game result.
    score_a: 1.0 = team A win, 0.5 = draw/tie, 0.0 = team A loss.
    margin:  absolute score differential (e.g. 7 for NFL, 14 for NBA).
             When provided, applies a log-scale MOV multiplier to K so that
             blowouts update the rating more than 1-point wins.
    sport:   used to select the correct MOV cap and scale.

    MOV multiplier formula (FiveThirtyEight-style):
        mov_mult = ln(|margin| + 1) / scale
    Capped at 2.0 to prevent extreme outliers from dominating.

    Returns (new_rating_a, new_rating_b). Seeds at ELO_DEFAULT_RATING (1500) for
    unseen teams — this is a forward-updating tracker, not a historical backfill,
    so ratings are most reliable after the first several weeks of a season as they
    converge, same cold-start behavior as any live Elo system."""
    import math as _math
    expected_a = elo_expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    score_b    = 1.0 - score_a

    # Margin-of-victory K multiplier
    if margin is not None and sport is not None and score_a != 0.5:
        _cap   = ELO_MOV_CAP.get(sport, 20)
        _scale = ELO_MOV_SCALE.get(sport, 10.0)
        _mov   = min(abs(float(margin)), _cap)
        # ln(mov+1) / scale → 1.0 at average margin, up to ~2.0 at blowout
        mov_mult = min(2.0, max(0.5, _math.log(_mov + 1) / _math.log(_scale + 1)))
        k_eff = k * mov_mult
    else:
        k_eff = k

    new_a = rating_a + k_eff * (score_a - expected_a)
    new_b = rating_b + k_eff * (score_b - expected_b)
    return round(new_a, 1), round(new_b, 1)


def elo_to_def_adj(rating, league_avg=1500.0, scale=400.0):
    """Convert an Elo rating into a def_adj-style multiplier consistent with the
    existing (opp_rank-15.5)/15.5-style adjustments elsewhere in S2 — keeps Elo
    pluggable into the same edge pipeline without changing its shape."""
    return round((rating - league_avg) / scale, 4)


def tier_badge(tier):
    """Reusable HTML tier badge — use in any markdown block."""
    styles = {
        "SOVEREIGN": {"bg": "#c8840a", "color": "#fff",     "icon": "👑"},
        "ELITE":     {"bg": "#0ea5a0", "color": "#fff",     "icon": "⭐"},
        "APPROVED":  {"bg": "#378add", "color": "#fff",     "icon": "✓"},
        "LEAN":      {"bg": "#4a5a6a", "color": "#b8c6d6",  "icon": "📊"},
        "PASS":      {"bg": "#2a3a4a", "color": "#6a7a8a",  "icon": "⏸"},
    }
    s = styles.get(tier, styles["LEAN"])
    return (f'<span style="background:{s["bg"]};color:{s["color"]};'
            f'padding:2px 9px;border-radius:12px;font-size:11px;'
            f'font-weight:700;letter-spacing:0.03em;">'
            f'{s["icon"]} {tier}</span>')


# Game-total prop detection thresholds
# If a prop line exceeds this, it's a game total, not a player stat
GAME_TOTAL_LINE_THRESHOLDS = {
    "NBA":  180.0,   # game totals ~210-240
    "WNBA": 130.0,   # game totals ~155-175
    "MLB":  15.0,    # game totals ~7-12 runs
    "NHL":  8.0,     # game totals ~5-7 goals
    "NFL":  60.0,    # game totals ~40-55
    "Soccer": 4.0,   # game totals ~2-3 goals
}

GAME_TOTAL_PROP_NAMES = {
    "Points Total", "Total Points", "Game Total", "Match Total",
    "Total Goals", "Total Runs", "Total Score", "Team Total",
    "Alternate Total",
}


def is_game_total_prop(player, prop_name, line, sport):
    """
    Detect whether a prop is a game-total bet vs a player stat.
    Game total props must NOT use the player avg model.
    """
    threshold = GAME_TOTAL_LINE_THRESHOLDS.get(sport, 999)
    if line >= threshold:
        return True
    if any(t.lower() in prop_name.lower() for t in GAME_TOTAL_PROP_NAMES):
        return True
    if "@" in player or " vs " in player.lower():
        return True
    return False



def parlay_prob(probs):
    combined = 1.0
    for p in probs:
        combined *= p
    return combined


def parlay_payout(probs, odds=-110):
    combined = parlay_prob(probs)
    if combined <= 0:
        return 0
    fair_decimal = 1 / combined
    if fair_decimal >= 2.0:
        return round((fair_decimal - 1) * 100)
    else:
        return round(-100 / (fair_decimal - 1))


def poisson_prob_over(line, avg):
    if avg <= 0:
        return 0.5
    k = int(line)
    try:
        p_under = sum((avg**i * exp(-avg)) / factorial(int(i)) for i in range(int(k) + 1))
        return round(1 - p_under, 4)
    except (ValueError, OverflowError, ZeroDivisionError, TypeError):
        return 0.5


def classify_regime(signals, edge, line_moved):
    """Classify the market regime for a prop."""
    if abs(edge) >= 0.10 and not line_moved:
        return "strong_over" if edge > 0 else "strong_under"
    if line_moved and edge > 0.05:
        return "reprice_over"
    if line_moved and edge < -0.05:
        return "reprice_under"
    if line_moved and abs(edge) < 0.03:
        return "sharp_fade"
    return "neutral"



def load_json_data(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
            return default
    return default


def _espn_has_games_in_window(sport: str, days: int = 7) -> bool:
    """
    Check ESPN scoreboard to see if the given sport has any scheduled games
    in the next `days` days.  Used to detect off-season gaps inside months
    that are normally active (e.g. NBA June post-Finals).
    Returns True if at least one upcoming/live event is found.
    """
    _sport_map = {
        "NBA":  ("basketball", "nba"),
        "NHL":  ("hockey",     "nhl"),
        "MLB":  ("baseball",   "mlb"),
        "NFL":  ("football",   "nfl"),
        "WNBA": ("basketball", "wnba"),
    }
    if sport not in _sport_map:
        return True  # assume active for unknown sports
    es, el = _sport_map[sport]
    try:
        import requests as _req
        from datetime import timedelta as _td
        today = date.today()
        # ESPN scoreboard accepts a date range via &dates=YYYYMMDD-YYYYMMDD
        start_str = today.strftime("%Y%m%d")
        end_str   = (today + _td(days=days)).strftime("%Y%m%d")
        url = (
            f"https://site.web.api.espn.com/apis/site/v2/sports/{es}/{el}/scoreboard"
            f"?dates={start_str}-{end_str}&limit=10"
        )
        r = _req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if r.status_code != 200:
            return True  # network issue — assume active to avoid false suppression
        events = r.json().get("events", [])
        # Filter to non-completed events (scheduled or live)
        live_or_upcoming = [
            e for e in events
            if not e.get("status", {}).get("type", {}).get("completed", False)
        ]
        return len(live_or_upcoming) > 0
    except Exception:
        return True  # fail open — never suppress if check errors


def detect_season_regime(sport="NBA"):
    """
    Detect current season phase and return weight adjustments.
    Used by enrichment loop (S weight modifiers) and History tab display.
    Returns: {regime, description, adjustments, month}

    GAP FIX (2026-06-21): Months 4-6 for NBA and NHL always returned
    "Playoffs" even post-Finals / post-Stanley Cup when there are zero
    active games.  Now we verify with a live ESPN 7-day schedule check
    before committing to a Playoffs classification.  If no games are found
    in the window, we return "Off-Season" so signal generation is suppressed
    rather than firing stale Playoff-weighted picks.
    """
    month = date.today().month

    if sport == "NBA":
        if month in (7, 8, 9):
            regime = "Off-season"
            desc   = "No NBA games — current-season signals are stale"
            adj    = {"base": -0.06}
        elif month in (10, 11):
            regime = "Early Season"
            desc   = "First month — small sample, base stats less reliable"
            adj    = {"base": -0.04, "defense": -0.03}
        elif month in (4, 5, 6):
            today = date.today()
            # Hard cutoff: after June 20 the NBA Finals are over regardless of
            # whether ESPN shows any residual events.  This is faster (no network)
            # and more reliable than a live schedule check.
            if today >= date(today.year, 6, 20):
                regime = "Off-season"
                desc   = "NBA Finals complete (est. June 20) — current-season signals suppressed"
                adj    = {"base": -0.06}
            elif _espn_has_games_in_window("NBA", days=7):
                regime = "Playoffs"
                desc   = "Playoffs — defense weight increases, pace less predictive"
                adj    = {"defense": 0.04, "pace": -0.02}
            else:
                regime = "Off-season"
                desc   = "NBA season complete — no games in next 7 days, signals suppressed"
                adj    = {"base": -0.06}
        elif month in (3,):
            regime = "Late Season"
            desc   = "Late season — rest signal strengthens"
            adj    = {"rest": 0.02}
        else:
            regime = "Mid Season"
            desc   = "Full weights active"
            adj    = {}
    elif sport == "WNBA":
        if month in (11, 12, 1, 2, 3, 4):
            regime = "Off-season"
            desc   = "No WNBA games — current-season signals are stale"
            adj    = {"base": -0.06}
        elif month in (5,):
            regime = "Early Season"
            desc   = "First month — small sample, base stats less reliable"
            adj    = {"base": -0.04, "defense": -0.03}
        elif month in (9, 10):
            regime = "Playoffs"
            desc   = "Playoffs — defense weight increases, pace less predictive"
            adj    = {"defense": 0.04, "pace": -0.02}
        elif month in (8,):
            regime = "Late Season"
            desc   = "Late season — rest signal strengthens"
            adj    = {"rest": 0.02}
        else:
            regime = "Mid Season"
            desc   = "Full weights active"
            adj    = {}
    elif sport == "MLB":
        if month in (3, 4):
            regime = "Early Season"
            desc   = "Early MLB — small sample, pitcher ERA stabilizing"
            adj    = {"base": -0.04}
        elif month in (10,):
            regime = "Playoffs"
            desc   = "MLB Playoffs — defense weight increases"
            adj    = {"defense": 0.04}
        elif month in (9,):
            regime = "Late Season"
            desc   = "Late MLB — rest signal strengthens"
            adj    = {"rest": 0.02}
        elif month in (11, 12, 1, 2):
            regime = "Off-season"
            desc   = "MLB off-season — current-season signals are stale"
            adj    = {"base": -0.06}
        else:
            regime = "Mid Season"
            desc   = "Full weights active"
            adj    = {}
    elif sport == "NHL":
        if month in (7, 8):
            regime = "Off-season"
            desc   = "No NHL games — current-season signals are stale"
            adj    = {"base": -0.06}
        elif month in (10, 11):
            regime = "Early Season"
            desc   = "Early NHL — small sample, base stats less reliable"
            adj    = {"base": -0.04}
        elif month in (4, 5, 6):
            # Verify games are actually scheduled before calling this Playoffs
            if _espn_has_games_in_window("NHL", days=7):
                regime = "Playoffs"
                desc   = "NHL Playoffs — defense weight increases, pace less predictive"
                adj    = {"defense": 0.05, "pace": -0.02}
            else:
                regime = "Off-season"
                desc   = "NHL season complete — no games in next 7 days, signals suppressed"
                adj    = {"base": -0.06}
        elif month in (3,):
            regime = "Late Season"
            desc   = "Late NHL — rest signal strengthens"
            adj    = {"rest": 0.02}
        else:
            regime = "Mid Season"
            desc   = "Full weights active"
            adj    = {}
    elif sport == "NFL":
        today = date.today()
        day   = today.day
        # Date-based NFL regime boundaries:
        #   Preseason:      Aug 1  – Sep 5
        #   Early season:   Sep 6  – Sep 30
        #   Mid season:     Oct 1  – Nov 30
        #   Late season:    Dec 1  – Jan 15  (includes wild-card week)
        #   Playoffs:       Jan 16 – Feb 15  (divisional → Super Bowl)
        #   Off-season:     Feb 16 – Jul 31
        if month == 8 or (month == 9 and day <= 5):
            regime = "Preseason"
            desc   = "NFL Preseason — starters limited, signals unreliable"
            adj    = {"base": -0.07}
        elif (month == 9 and day >= 6) or month in (10, 11):
            if month == 9:
                regime = "Early Season"
                desc   = "Early NFL regular season — small sample, base stats less reliable"
                adj    = {"base": -0.05}
            else:
                regime = "Mid Season"
                desc   = "NFL mid-season — full weights active"
                adj    = {}
        elif month == 12 or (month == 1 and day <= 15):
            regime = "Late Season"
            desc   = "Late NFL regular season — rest signal critical"
            adj    = {"rest": 0.03}
        elif (month == 1 and day >= 16) or (month == 2 and day <= 15):
            regime = "Playoffs"
            desc   = "NFL Playoffs — defense weight increases significantly"
            adj    = {"defense": 0.06}
        elif month in (3, 4, 5, 6, 7) or (month == 2 and day >= 16):
            regime = "Off-season"
            desc   = "NFL off-season — current-season signals are stale"
            adj    = {"base": -0.06}
        else:
            regime = "Mid Season"
            desc   = "Full weights active"
            adj    = {}
    else:
        regime = "Mid Season"
        desc   = "Full weights active"
        adj    = {}

    adj = {k: max(-0.10, min(0.10, float(v))) for k, v in adj.items()}
    return {
        "regime":      regime,
        "description": desc,
        "adjustments": adj,
        "month":       month,
        "sport":       sport,
    }



def format_rlm_display(rlm_data):
    """Format RLM/sharp signal for prop card Why section."""
    if not rlm_data or not rlm_data.get("has_sharp"):
        return ""
    lines = []
    for sig in rlm_data.get("sharp_signals", [])[:2]:
        lines.append(sig)
    for rlm in rlm_data.get("rlm_signals", [])[:1]:
        lines.append(
            f"↔️ RLM: {rlm.get('public_pct',0)}% tickets on {rlm.get('public_side','')} | "
            f"{rlm.get('money_pct',0)}% money on {rlm.get('sharp_side','')} — sharp action detected"
        )
    return " | ".join(lines)



def track_closing_line_beat(bet_record, current_line):
    """
    Track whether model projection beat the closing line.
    
    This is more valuable than win/loss tracking:
    - Model projected 26.4, closing line was 24.5 → model correct
    - Actual was 25 (loss) but model beat the market
    
    Over thousands of bets this tells you:
    - True model edge vs the market
    - Separate from variance-driven wins/losses
    """
    model_proj = float(bet_record.get("model_proj", 0) or 0)
    locked_line = float(bet_record.get("line", 0) or 0)
    side        = bet_record.get("side","OVER")
    
    if model_proj <= 0 or locked_line <= 0 or not current_line:
        return None
    
    try:
        closing = float(current_line)
    except (ValueError, TypeError):
        return None
    
    # Did model correctly predict line direction?
    if side == "OVER":
        model_beat_close = model_proj > closing   # model higher than closing = OVER value
        line_moved_with  = closing > locked_line  # line moved up = confirmed OVER
    else:
        model_beat_close = model_proj < closing
        line_moved_with  = closing < locked_line
    
    return {
        "model_proj":       model_proj,
        "locked_line":      locked_line,
        "closing_line":     closing,
        "model_beat_close": model_beat_close,
        "line_moved_with":  line_moved_with,
        "clv_direction":    "correct" if model_beat_close else "wrong",
    }



def is_date_valid_for_today(date_str):
    """Check if date_str is today or yesterday — anchored to US/Eastern time.

    Bug fixed: date.today() returns UTC on Streamlit Cloud. At 8pm EST
    (1am UTC next day) that flips the date and marks fresh Gist data stale.
    """
    try:
        from datetime import timedelta as _td, timezone as _tz, datetime as _dt
        try:
            import zoneinfo as _zi
            _eastern = _zi.ZoneInfo("America/New_York")
            _now_eastern = _dt.now(_eastern)
        except Exception:
            _eastern = _tz(_td(hours=-5))
            _now_eastern = _dt.now(_eastern)
        today     = _now_eastern.date()
        yesterday = today - _td(days=1)
        if "T" in str(date_str):
            date_obj = date.fromisoformat(str(date_str).split("T")[0])
        else:
            date_obj = date.fromisoformat(str(date_str))
        return date_obj in (today, yesterday)
    except (ValueError, IndexError, TypeError):
        return False



def adjusted_edge(raw_edge, sport, tier, stat_norm, history):
    relevant = [b for b in history if b.get("tier") == tier and b.get("sport") == sport]
    n = len(relevant)
    if n < 20:
        return raw_edge, False
    outcomes = [1 if b["outcome"] == "WIN" else 0 for b in relevant]
    predicted = [b.get("prob", 0.5) for b in relevant]
    hit_rate = sum(outcomes) / n
    avg_predicted = sum(predicted) / n
    calibration_error = hit_rate - avg_predicted
    adjustment = calibration_error * min(1.0, n / 100)
    return raw_edge + adjustment, True

# normalize_name — moved to utils.py

def find_player_avg(player_name, avgs_dict):
    if player_name in avgs_dict:
        return avgs_dict[player_name], False
    norm = normalize_name(player_name)
    for key, val in avgs_dict.items():
        if normalize_name(key) == norm:
            return val, False
    return {}, True


def market_efficiency_score(pp_line, ud_line, edge, sport):
    if pp_line and ud_line and ud_line > 0:
        line_spread = abs(pp_line - ud_line)
        inefficiency = min(line_spread / 1.5, 1.0)
    else:
        inefficiency = 0.3
    score = round((abs(edge) * 0.6) + (inefficiency * 0.4), 3)
    if inefficiency > 0.5 and abs(edge) >= 0.10:
        label = "🔥 Inefficient"
    elif inefficiency > 0.3 and abs(edge) >= 0.05:
        label = "⚡ Moderate"
    else:
        label = "✓ Efficient"
    return score, label


def get_weighted_average(player_name, season_avg, last10_avg, is_playoff=False):
    if last10_avg is None:
        return season_avg
    if is_playoff:
        return last10_avg
    return {"PTS": round(last10_avg.get("PTS", season_avg.get("PTS", 0)) * 0.7 + season_avg.get("PTS", 0) * 0.3, 1),
            "REB": round(last10_avg.get("REB", season_avg.get("REB", 0)) * 0.7 + season_avg.get("REB", 0) * 0.3, 1),
            "AST": round(last10_avg.get("AST", season_avg.get("AST", 0)) * 0.7 + season_avg.get("AST", 0) * 0.3, 1),
            "PRA": round(last10_avg.get("PRA", season_avg.get("PRA", 0)) * 0.7 + season_avg.get("PRA", 0) * 0.3, 1)}


def get_recency_context(player_name, stat_norm, season_avg, rolling_avg, sport):
    if not rolling_avg or not season_avg:
        return "", "neutral"
    r_val = rolling_avg if isinstance(rolling_avg, (int, float)) else 0
    s_val = season_avg if isinstance(season_avg, (int, float)) else 0
    if s_val <= 0:
        return "", "neutral"
    diff_pct = (r_val - s_val) / s_val
    if diff_pct >= 0.20:
        return f"🔥 Hot streak (+{diff_pct:.0%} vs avg)", "hot"
    elif diff_pct <= -0.20:
        return f"🥶 Cold streak ({diff_pct:.0%} vs avg)", "cold"
    elif diff_pct >= 0.10:
        return f"📈 Trending up (+{diff_pct:.0%})", "warm"
    elif diff_pct <= -0.10:
        return f"📉 Trending down ({diff_pct:.0%})", "cooling"
    return "", "neutral"


def sample_size_confidence(n_games, sport):
    if n_games is None or n_games == 0:
        return 0.80
    n_games = max(0, int(n_games))
    full_n = 10
    min_conf = 0.80
    confidence = min(1.0, min_conf + (1.0 - min_conf) * (n_games ** 0.5) / (full_n ** 0.5))
    return round(confidence, 3)


# get_best_alt_line_recommendation — moved back to app.py (cross-module dependency)
def compare_multibook_lines(pp_props, oddswrap_props):
    if not oddswrap_props:
        return []
    discrepancies = []
    pp_dict = {}
    for p in pp_props:
        key = normalize_name(p["Player"])
        if key not in pp_dict:
            pp_dict[key] = {}
        pp_dict[key][p["Prop"]] = p["Line"]
    ow_dict = {}
    for p in oddswrap_props:
        key = normalize_name(p["Player"])
        prop = p["Prop"]
        if key not in ow_dict:
            ow_dict[key] = {}
        if prop not in ow_dict[key]:
            ow_dict[key][prop] = []
        ow_dict[key][prop].append({"line": p["Line"], "book": p["Book"]})
    for norm_player, props in pp_dict.items():
        if norm_player not in ow_dict:
            continue
        for prop, pp_line in props.items():
            for ow_prop, ow_lines in ow_dict[norm_player].items():
                if (normalize_name(prop) in normalize_name(ow_prop) or normalize_name(ow_prop) in normalize_name(prop)):
                    for ow_data in ow_lines:
                        diff = pp_line - ow_data["line"]
                        if abs(diff) >= 0.5:
                            discrepancies.append({"Player": norm_player.title(), "Prop": prop, "PrizePicks": pp_line, "Book": ow_data["book"].title(), "BookLine": ow_data["line"], "Diff": round(diff, 1), "Favor": ("OVER on PP" if diff > 0 else f"OVER on {ow_data['book'].title()}")})
    return sorted(discrepancies, key=lambda x: abs(x["Diff"]), reverse=True)


def make_display_df(props):
    """Convert raw enriched prop dicts into a clean display DataFrame with friendly column names."""
    rows = []
    for p in props:
        rows.append({
            "Player":         p.get("Player", ""),
            "Stat":           p.get("Prop", ""),
            "Line":           p.get("Line", ""),
            "Play":           f"{p.get('Side','OVER')} {p.get('Line','')}",
            "Avg (10g)":      round(p.get("Avg", 0), 1) if p.get("Avg") else "—",
            "Fair %":         p.get("ModelProb", "—"),
            "Edge":           p.get("EdgePct", "—"),
            "2-Pick EV":      p.get("EV_2pick", "—"),
            "Bet Size":       f"${p.get('Wager_2pick', p.get('Wager', 0)):.2f}",
            "Tier":           p.get("Tier", "—"),
            "AN Grade":       p.get("AN_Grade", "—"),
            "AN Proj":        p.get("AN_Projection", "—"),
            "AN Tier":        p.get("AN_Tier", "—"),
            "AN Confirms":    "✅" if p.get("AN_Confirms") else "—",
            "Line Fair?":     p.get("FairnessGrade", "—"),
            "Sharp $":        p.get("SharpFlag", "—"),
            "Market":         p.get("Efficiency", "—"),
            "Confidence":     p.get("ConfidenceMult", "—"),
            "Injury":         p.get("Injury", ""),
            "Line Move":      p.get("Movement", "—"),
            "Trend":          p.get("Trend", "—"),
            "Source":         p.get("source", "—"),
            "Consensus Prob": p.get("ConsensusProb", "—"),
            "Books":          p.get("ConsensusBooks", "—"),
            "Best Alt Line":  p.get("BestAltLine", "—"),
            "Alt EV":         p.get("BestAltEV", "—"),
            "Alt Payout":     p.get("BestAltPayout", "—"),
            "SEM":            p.get("SEM", "—"),
            "CLV Adj":        p.get("CLVAdj", "—"),
            "Side":           p.get("Side", "OVER"),
            "Prop":           p.get("Prop", ""),
        })
    return pd.DataFrame(rows)


def compute_market_edge(fair_prob, side="OVER"):
    market_implied = 0.524
    if side.upper() == "OVER":
        edge = fair_prob - market_implied
    else:
        edge = fair_prob - market_implied
    return round(edge, 4)

# devig_odds — moved to utils.py

def compute_market_implied_projection(line, stat_type, sport="NBA"):
    """
    Reverse-engineer the prop line to derive the market's implied average.
    
    The prop line IS the market's projection — it's set so that the
    no-vig probability is ~50%. But we can extract useful info:
    
    1. If our avg > line: model thinks player will exceed market expectation
    2. If line > our avg: market more bullish than our model
    3. Agreement score: how close is our projection to market?
    
    Returns: {implied_avg, agreement_pct, direction, note}
    """
    # Line is already the market's implied projection
    # The interesting metric is how far our model diverges
    implied_avg = float(line) if line else 0

    return {
        "implied_avg":    round(implied_avg, 1),
        "note":           f"Market implies {implied_avg:.1f} {stat_type}",
    }



def compute_sem_for_tier(tier_stats, tier):
    if tier not in tier_stats:
        return "—", 0
    stats = tier_stats[tier]
    n = stats["n"]
    if n < 5:
        return "—", n
    sem = stats["sem"]
    if sem is None:
        return "—", n
    return f"±{sem:.3f}", n

# adjusted_edge — moved to bc_utils.py
# find_player_avg — moved to bc_utils.py

def compute_h2h_hit_rate(game_logs, opponent_abbr, stat, line):
    """
    Compute H2H hit rate vs a specific opponent.
    Returns (hit_rate, games_played, sample_str)
    """
    stat_map = {
        "Points": "pts", "Rebounds": "reb", "Assists": "ast",
        "Steals": "stl", "Blocked Shots": "blk", "Turnovers": "turnover",
        "3-PT Made": "fg3m", "Pts+Reb+Ast": "pra",
    }
    stat_key = stat_map.get(stat, stat.lower()[:3])
    opp_games = [g for g in game_logs if str(g.get("opponent_id","")).lower() in opponent_abbr.lower()
                 or opponent_abbr.lower() in str(g.get("opponent_id","")).lower()]

    if not opp_games:
        return None, 0, "No H2H data"

    hits = sum(1 for g in opp_games if (g.get(stat_key) or 0) > line)
    rate = hits / len(opp_games)
    return rate, len(opp_games), f"{hits}/{len(opp_games)} vs this opponent"


# ─────────────────────────────────────────────────────────────────────────────
# Cross-book prop analytics
# ─────────────────────────────────────────────────────────────────────────────

def consensus_prop_line(lines_by_book: dict) -> dict:
    """
    Compute cross-book consensus fair line for a player prop.

    Takes all available book lines for the same player+stat, returns the
    median (robust to outliers) as the fair line, plus spread and confidence.

    Args:
        lines_by_book: {book_name: line_float}  e.g. {"DraftKings": 1.5, "FanDuel": 2.0}

    Returns:
        {fair_line, median_line, mean_line, spread, confidence, n_books, books}
        confidence: 0–1, higher when books agree and more books are present.
        Returns {} when fewer than 2 valid lines are available.
    """
    import statistics as _stats
    if not lines_by_book:
        return {}
    vals = [float(v) for v in lines_by_book.values() if v is not None]
    if len(vals) < 2:
        return {}
    n       = len(vals)
    median  = _stats.median(vals)
    mean    = round(sum(vals) / n, 2)
    spread  = round(max(vals) - min(vals), 2)
    # Confidence: penalised by spread relative to line and boosted by n_books
    conf_raw  = 1 - (spread / (median + 0.001)) * (2 / max(n, 2))
    confidence = round(max(0.0, min(1.0, conf_raw)), 3)
    return {
        "fair_line":   round(median, 2),
        "median_line": round(median, 2),
        "mean_line":   mean,
        "spread":      spread,
        "confidence":  confidence,
        "n_books":     n,
        "books":       list(lines_by_book.keys()),
    }


def detect_line_movement(
    current_line: float,
    previous_line: float,
    side: str = "OVER",
) -> dict:
    """
    Detect and classify line movement between two snapshots.

    Args:
        current_line:  latest line from the book
        previous_line: line value from prior snapshot
        side:          "OVER" or "UNDER" — context for "favorable"

    Returns:
        {moved, delta, direction, favorable, magnitude, is_sharp, abs_delta}
        moved=False when lines are equal or either is None.
    """
    if current_line is None or previous_line is None:
        return {"moved": False}
    delta = round(current_line - previous_line, 3)
    if delta == 0:
        return {"moved": False, "delta": 0}
    abs_delta = abs(delta)
    # For OVER bets: line dropping = easier to go over = favorable
    favorable  = (delta < 0) if side.upper() == "OVER" else (delta > 0)
    is_sharp   = abs_delta >= 0.5          # threshold for meaningful sharp move
    magnitude  = ("large"  if abs_delta >= 1.0 else
                  "medium" if abs_delta >= 0.5 else "small")
    return {
        "moved":     True,
        "delta":     delta,
        "direction": "down" if delta < 0 else "up",
        "favorable": favorable,
        "magnitude": magnitude,
        "is_sharp":  is_sharp,
        "abs_delta": abs_delta,
    }


def prop_edge_score(
    player_avg: float      = None,
    line: float            = None,
    hit_rate: float        = None,
    regime_adj: float      = 0.0,
    h2h_rate: float        = None,
    consensus_line: float  = None,
    line_movement: dict    = None,
) -> dict:
    """
    Unified prop edge score that combines all available analytical signals.

    Signal weights (sum to 1.0 across included signals only):
      L2L gap      (player_avg vs line)    30% — core value signal
      Hit rate     (rolling over/under %)  25% — historical edge
      Regime adj   (season phase)           8% — context modifier (research: >10% adds noise)
      H2H rate     (vs this opponent)      15% — matchup specificity
      Consensus gap (vs book median)       10% — market inefficiency signal
      Line movement (directional)           5% — late-money confirmation

    Confidence scales with how many signals are available (0 → 1).

    Args:
        player_avg:     rolling average for this stat (same units as line)
        line:           current book line
        hit_rate:       float 0–1, historical over rate for this player+stat near this line
        regime_adj:     float from detect_season_regime() adj dict, e.g. 0.03 or -0.05
        h2h_rate:       float 0–1, over rate vs this specific opponent
        consensus_line: median line across all books (from consensus_prop_line)
        line_movement:  dict from detect_line_movement()

    Returns:
        {edge, confidence, signals, recommendation}
        edge:           float −1→1  (positive = OVER edge, negative = UNDER edge)
        confidence:     float 0→1
        recommendation: "OVER" / "UNDER" / "PASS"
    """
    signals      = {}
    weighted_sum = 0.0
    weight_total = 0.0

    def _clamp(v, lo=-1.0, hi=1.0):
        return max(lo, min(hi, v))

    # 1. L2L gap — player average vs line (normalised)
    if player_avg is not None and line and line > 0:
        gap = _clamp((player_avg - line) / line)
        signals["l2l_gap"] = round(gap, 3)
        weighted_sum += gap * 0.30
        weight_total += 0.30

    # 2. Historical hit rate
    if hit_rate is not None:
        hr_signal = _clamp((hit_rate - 0.5) * 2)
        signals["hit_rate"]        = round(hit_rate, 3)
        signals["hit_rate_signal"] = round(hr_signal, 3)
        weighted_sum += hr_signal * 0.25
        weight_total += 0.25

    # 3. Season regime adjustment
    if regime_adj:
        signals["regime_adj"] = regime_adj
        weighted_sum += _clamp(regime_adj, -0.15, 0.15) * 0.15
        weight_total += 0.15

    # 4. H2H opponent rate
    if h2h_rate is not None:
        h2h_signal = _clamp((h2h_rate - 0.5) * 2)
        signals["h2h_rate"] = round(h2h_rate, 3)
        weighted_sum += h2h_signal * 0.15
        weight_total += 0.15

    # 5. Cross-book consensus gap
    if consensus_line is not None and line and line > 0:
        cg = _clamp((consensus_line - line) / line, -0.5, 0.5)
        signals["consensus_gap"] = round(cg, 3)
        weighted_sum += cg * 0.10
        weight_total += 0.10

    # 6. Line movement
    if isinstance(line_movement, dict) and line_movement.get("moved"):
        mv = 0.05 if line_movement.get("favorable") else -0.05
        if line_movement.get("magnitude") == "large":
            mv *= 2
        signals["line_movement"]    = line_movement.get("direction")
        signals["movement_favorable"] = line_movement.get("favorable")
        weighted_sum += mv * 0.05
        weight_total += 0.05

    if weight_total == 0:
        return {"edge": 0.0, "confidence": 0.0, "signals": {}, "recommendation": "PASS"}

    edge       = round(weighted_sum / weight_total, 4)
    confidence = round(min(weight_total, 1.0), 3)

    # Recommendation gates: need meaningful edge AND enough signal
    if edge >= 0.08 and confidence >= 0.4:
        rec = "OVER"
    elif edge <= -0.08 and confidence >= 0.4:
        rec = "UNDER"
    else:
        rec = "PASS"

    return {"edge": edge, "confidence": confidence, "signals": signals, "recommendation": rec}


# ─────────────────────────────────────────────────────────────────────────────
# Canonical cross-book stat-type normalization
# ─────────────────────────────────────────────────────────────────────────────
_CANONICAL_STAT_MAP: dict = {
    "strikeouts": "Pitcher Strikeouts", "pitcher strikeouts": "Pitcher Strikeouts",
    "pitcher_strikeouts": "Pitcher Strikeouts", "so": "Pitcher Strikeouts",
    "k": "Pitcher Strikeouts", "ks": "Pitcher Strikeouts", "strikeout": "Pitcher Strikeouts",
    "points": "Points", "pts": "Points", "point": "Points",
    "rebounds": "Rebounds", "reb": "Rebounds", "rebound": "Rebounds",
    "total rebounds": "Rebounds",
    "assists": "Assists", "ast": "Assists", "assist": "Assists",
    "pts+reb+ast": "Pts+Reb+Ast", "pra": "Pts+Reb+Ast",
    "points+rebounds+assists": "Pts+Reb+Ast", "pts reb ast": "Pts+Reb+Ast",
    "home runs": "Home Runs", "home run": "Home Runs", "hr": "Home Runs", "homers": "Home Runs",
    "hits": "Hits", "hit": "Hits",
    "rbis": "RBIs", "rbi": "RBIs", "runs batted in": "RBIs",
    "total bases": "Total Bases", "tb": "Total Bases", "totalbases": "Total Bases",
    "steals": "Steals", "stl": "Steals",
    "stolen bases": "Stolen Bases", "sb": "Stolen Bases",
    "blocks": "Blocked Shots", "blk": "Blocked Shots", "blocked shots": "Blocked Shots",
    "3-pt made": "3-PT Made", "three pointers made": "3-PT Made",
    "3pm": "3-PT Made", "threes": "3-PT Made", "3pointers": "3-PT Made",
    "passing yards": "Pass Yds", "pass yards": "Pass Yds", "pass yds": "Pass Yds",
    "passing_yards": "Pass Yds",
    "rushing yards": "Rush Yds", "rush yards": "Rush Yds", "rush yds": "Rush Yds",
    "rushing_yards": "Rush Yds",
    "receiving yards": "Rec Yds", "rec yards": "Rec Yds", "rec yds": "Rec Yds",
    "receptions": "Receptions", "recs": "Receptions",
    "touchdowns": "Touchdowns", "tds": "Touchdowns", "td": "Touchdowns",
    "goals": "Goals", "goal": "Goals",
    "shots on goal": "Shots On Goal", "sog": "Shots On Goal", "shots": "Shots On Goal",
    "saves": "Saves",
    "fantasy points": "Fantasy Points", "fantasy": "Fantasy Points",
    "turnovers": "Turnovers", "tov": "Turnovers",
    "walks": "Walks", "bb": "Walks",
    "innings pitched": "Innings Pitched", "ip": "Innings Pitched",
    "runs": "Runs", "r": "Runs",
}


def normalize_stat_type(raw: str, sport: str = "") -> str:
    """Map any book/source stat label to its canonical BetCouncil name.

    Handles case variants, abbreviations, underscores, and plurals.
    Unknown stats are returned title-cased as a graceful fallback.
    """
    if not raw:
        return raw
    key = raw.strip().lower().replace("-", " ").replace("_", " ")
    canonical = _CANONICAL_STAT_MAP.get(key)
    if canonical is None:
        canonical = _CANONICAL_STAT_MAP.get(key.rstrip("s"))
    return canonical if canonical else raw.strip().title()


# ─────────────────────────────────────────────────────────────────────────────
# Regression-to-mean risk detection
# ─────────────────────────────────────────────────────────────────────────────

def hot_streak_regression_risk(
    recent_avg: float,
    season_avg: float,
    n_recent: int = 5,
    threshold: float = 0.30,  # raised from 0.25 — NBA research: <30% gap is noise
) -> dict:
    """Flag when recent average is unsustainably above the season average.

    Returns an edge_mult < 1.0 to discount OVER edge when a player is on a
    hot streak that is likely to mean-revert. UNDER edge is unaffected.

    Args:
        recent_avg: Average over last N games (L5 or L10).
        season_avg: Full-season baseline (true talent level).
        n_recent:   Games in the recent sample (fewer = softer penalty).
        threshold:  Gap fraction to trigger risk (default 0.25 = 25% above).

    Returns:
        {risk, gap_pct, edge_mult, note}
    """
    if not recent_avg or not season_avg or season_avg <= 0:
        return {"risk": "NONE", "gap_pct": 0.0, "edge_mult": 1.0, "note": ""}

    gap_pct = (recent_avg - season_avg) / season_avg
    if gap_pct < threshold:
        return {"risk": "NONE", "gap_pct": round(gap_pct, 3), "edge_mult": 1.0, "note": ""}

    confidence = min(n_recent / 10, 1.0)

    if gap_pct >= 0.50:
        risk      = "HIGH"
        edge_mult = max(0.70, 1.0 - 0.30 * confidence)
        note      = (f"🔥 Hot streak: L{n_recent} avg {recent_avg:.1f} is "
                     f"{gap_pct:.0%} above season avg {season_avg:.1f}. "
                     "Regression likely — OVER edge discounted.")
    elif gap_pct >= 0.35:
        risk      = "MEDIUM"
        edge_mult = max(0.80, 1.0 - 0.20 * confidence)
        note      = (f"📈 Elevated: L{n_recent} avg {recent_avg:.1f} is "
                     f"{gap_pct:.0%} above season avg {season_avg:.1f}. "
                     "Moderate regression risk — discount applied.")
    else:
        risk      = "LOW"
        edge_mult = max(0.92, 1.0 - 0.08 * confidence)
        note      = (f"L{n_recent} avg {recent_avg:.1f} is {gap_pct:.0%} "
                     f"above season avg {season_avg:.1f} — minor regression risk.")

    return {
        "risk":      risk,
        "gap_pct":   round(gap_pct, 3),
        "edge_mult": round(edge_mult, 3),
        "note":      note,
    }


# ── Extracted from app.py (2026-06-25) — pure computation, no Streamlit deps ──
def check_prop_line_fairness(line, consensus_prob, side="OVER"):
    if consensus_prob is None:
        return "UNKNOWN", ""
    market_implied = 0.524
    if side.upper() == "OVER":
        gap = market_implied - consensus_prob
    else:
        gap = market_implied - (1 - consensus_prob)
    if gap >= 0.07:
        return "BAD", f"⚠️ Market prices this at {consensus_prob:.1%} — line is {gap:.1%} worse than market fair value. Reduce sizing or skip."
    elif gap >= 0.04:
        return "CAUTION", f"📊 Market prices this at {consensus_prob:.1%} — slightly unfavorable line. Verify before betting."
    else:
        return "GOOD", f"✅ Line is fair vs market ({consensus_prob:.1%} consensus)"

def save_json_data(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _get_elo_roster_confidence(sport: str, team: str, window_days: int = 14) -> float:
    """
    Return a K-factor confidence multiplier [0.5, 1.0] based on recent roster
    churn for the given team.  High churn (3+ moves in 14 days) degrades Elo
    reliability — we don't know how the new roster performs yet.

    Fetches ESPN transactions endpoint; returns 1.0 on any error so normal
    Elo updates proceed unaffected when the network is unavailable.
    """
    _sport_map = {
        "NBA": ("basketball", "nba"),
        "MLB": ("baseball",   "mlb"),
        "NHL": ("hockey",     "nhl"),
        "NFL": ("football",   "nfl"),
    }
    if sport not in _sport_map:
        return 1.0
    es, el = _sport_map[sport]
    try:
        from datetime import timedelta as _td
        import requests as _req
        cutoff = (datetime.now() - _td(days=window_days)).strftime("%Y%m%d")
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/{es}/{el}"
            f"/transactions?limit=100&date={cutoff}"
        )
        r = _req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if r.status_code != 200:
            return 1.0
        transactions = r.json().get("transactions", [])
        # Count moves involving this team (case-insensitive partial match)
        team_lower = team.lower()
        churn_count = sum(
            1 for t in transactions
            if team_lower in t.get("team", {}).get("displayName", "").lower()
        )
        # Scale: 0-2 moves → 1.0, 3-4 → 0.85, 5-6 → 0.70, 7+ → 0.50
        if churn_count <= 2:
            return 1.0
        elif churn_count <= 4:
            return 0.85
        elif churn_count <= 6:
            return 0.70
        else:
            return 0.50
    except Exception:
        return 1.0

def compute_signal_attribution(history=None):
    """
    Compute per-signal win rate and ROI from resolved bets.
    Activates at 20+ resolved bets.
    Returns (rows_list, resolved_count)
    """
    if history is None:
        history = []
    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS")]
    n = len(resolved)
    if n < 20:
        return None, n
    signal_stats = {}
    for bet in resolved:
        sv = bet.get("signal_values", {})
        for sig, val in sv.items():
            if sig not in signal_stats:
                signal_stats[sig] = {"wins":0,"total":0,"edge_sum":0}
            signal_stats[sig]["total"] += 1
            if bet.get("outcome") == "WIN":
                signal_stats[sig]["wins"] += 1
            signal_stats[sig]["edge_sum"] += float(val or 0)
    rows = []
    for sig, stats in sorted(signal_stats.items(), key=lambda x: -x[1]["total"]):
        if stats["total"] < 3:
            continue
        wr = stats["wins"] / stats["total"]
        rows.append({
            "Signal":   sig,
            "Bets":     stats["total"],
            "Win Rate": f"{wr:.0%}",
            "Avg Edge": f"{stats['edge_sum']/stats['total']:+.3f}",
            "Status":   "✅" if wr >= 0.55 else "⚠️" if wr >= 0.50 else "❌",
        })
    return rows, n

def compute_parlay_correlation(props):
    """
    Compute correlation score for a set of props.
    Returns (score 0-1, list of correlated pairs).
    """
    if not props or len(props) < 2:
        return 0.0, []
    KNOWN_CORR = [
        ("Points","PRA"), ("Rebounds","PRA"), ("Assists","PRA"),
        ("Points","Fantasy Score"), ("Hits","Total Bases"),
    ]
    corr_pairs = []
    score = 0.0
    players = [p.get("Player","") for p in props]
    # Same player = high correlation
    from collections import Counter
    dupes = [pl for pl, cnt in Counter(players).items() if cnt >= 2 and pl]
    for pl in dupes:
        corr_pairs.append(f"{pl} has multiple props")
        score += 0.35
    # Known correlated prop types
    prop_types = [(p.get("Player",""), p.get("Prop","")) for p in props]
    for i, (pl1, pr1) in enumerate(prop_types):
        for j, (pl2, pr2) in enumerate(prop_types):
            if i >= j:
                continue
            if pl1 == pl2:
                for ca, cb in KNOWN_CORR:
                    if (ca in pr1 and cb in pr2) or (cb in pr1 and ca in pr2):
                        corr_pairs.append(f"{pl1}: {pr1}+{pr2}")
                        score += 0.25
    return round(min(1.0, score), 2), corr_pairs

def generate_weight_recommendations(history=None, sport="NBA"):
    """
    Generate signal weight recommendations based on historical performance.
    Activates at 100+ resolved bets for the given sport.
    Returns (recommendations_list, resolved_count)
    """
    if history is None:
        history = []
    resolved = [h for h in history
                if h.get("outcome") in ("WIN","LOSS")
                and h.get("sport","") == sport]
    n = len(resolved)
    if n < 100:
        return None, n
    # Simple win rate by signal
    recs = []
    signal_perf = {}
    for bet in resolved:
        sv = bet.get("signal_values", {})
        for sig, val in sv.items():
            if sig not in signal_perf:
                signal_perf[sig] = {"wins":0,"total":0}
            signal_perf[sig]["total"] += 1
            if bet.get("outcome") == "WIN":
                signal_perf[sig]["wins"] += 1
    for sig, perf in sorted(signal_perf.items(), key=lambda x: -x[1]["total"]):
        if perf["total"] < 10:
            continue
        wr = perf["wins"] / perf["total"]
        if wr >= 0.58:
            recs.append({"signal": sig, "action": "INCREASE", "win_rate": wr,
                         "reason": f"{wr:.0%} win rate — above threshold"})
        elif wr <= 0.48:
            recs.append({"signal": sig, "action": "DECREASE", "win_rate": wr,
                         "reason": f"{wr:.0%} win rate — below threshold"})
    return recs, n

def generate_post_mortem(history, target_date=None):
    """
    Post-mortem analysis for a specific date (default: yesterday).
    Answers: why did we win/lose that day?
    
    Top failing signals, top succeeding signals,
    which tier underperformed, what to watch next time.
    """
    from datetime import timedelta
    if target_date is None:
        target_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    day_bets = [h for h in history
                if h.get("timestamp","").startswith(target_date)
                and h.get("outcome") in ("WIN","LOSS")]

    if not day_bets:
        return None

    n = len(day_bets)
    wins = sum(1 for h in day_bets if h.get("outcome") == "WIN")
    total_net = sum(h.get("net", 0) for h in day_bets)
    wr = wins / n

    # Signal performance for the day
    SIGNAL_KEYS = {
        "base":     "Base",
        "defense":  "Defense",
        "location": "Location",
        "rest":     "Rest",
        "usage":    "Usage",
        "blowout":  "Blowout",
        "weather":  "Weather",
        "sharp":    "Sharp",
    }
    signal_day = {}
    for h in day_bets:
        sig_vals = h.get("signal_values", {})
        for sk, sl in SIGNAL_KEYS.items():
            val = sig_vals.get(sk, 0)
            if abs(val) < 0.005:
                continue
            if sl not in signal_day:
                signal_day[sl] = {"wins": 0, "losses": 0, "net": 0}
            signal_day[sl]["net"] += h.get("net", 0)
            if h.get("outcome") == "WIN":
                signal_day[sl]["wins"] += 1
            else:
                signal_day[sl]["losses"] += 1

    failing  = sorted([(k,v) for k,v in signal_day.items() if v["net"] < 0],
                       key=lambda x: x[1]["net"])
    succeeding = sorted([(k,v) for k,v in signal_day.items() if v["net"] > 0],
                         key=lambda x: -x[1]["net"])

    # Tier breakdown
    tier_day = {}
    for h in day_bets:
        t = h.get("tier","?")
        if t not in tier_day:
            tier_day[t] = {"wins":0,"losses":0,"net":0}
        tier_day[t]["net"] += h.get("net",0)
        if h.get("outcome") == "WIN":
            tier_day[t]["wins"] += 1
        else:
            tier_day[t]["losses"] += 1

    # Verdict
    if total_net > 0:
        verdict = f"✅ Winning day: +{total_net:.1f}u ({wr:.0%} WR)"
    elif total_net == 0:
        verdict = f"⚪ Break-even day: {wr:.0%} WR"
    else:
        verdict = f"🔴 Losing day: {total_net:.1f}u ({wr:.0%} WR)"

    # Primary cause
    if failing:
        top_fail = failing[0]
        cause = f"{top_fail[0]} signal underperformed ({top_fail[1]['net']:+.1f}u)"
    elif wins == 0:
        cause = "No winning picks — review tier thresholds"
    else:
        cause = "Normal variance — no structural issues"

    return {
        "date":        target_date,
        "verdict":     verdict,
        "n":           n,
        "wins":        wins,
        "net":         round(total_net, 2),
        "win_rate":    f"{wr:.1%}",
        "cause":       cause,
        "failing":     [(k, round(v["net"],2), v["wins"], v["losses"]) for k,v in failing[:3]],
        "succeeding":  [(k, round(v["net"],2), v["wins"], v["losses"]) for k,v in succeeding[:3]],
        "tier_breakdown": {k: {"net": round(v["net"],2), "wr": f"{v['wins']/(v['wins']+v['losses']):.0%}" if (v['wins']+v['losses'])>0 else "—"}
                           for k,v in tier_day.items()},
        "watch_next":  [k for k,v in failing[:2]] if failing else [],
    }

def compute_projection_confidence(player, prop, line, sport,
                                   avg=None, sample_n=10,
                                   injury_status=None,
                                   lineup_confirmed=None,
                                   market_edge=None,
                                   volatility=None):
    """
    Projection confidence score (0-100).
    Combines multiple certainty factors into one number.
    
    Components:
      Sample size (25pts):   10+ games = full, <5 = penalized
      Injury certainty (25pts): Active = full, Questionable = half, Out = zero
      Lineup confirmed (20pts): MLB lineup confirmed = full
      Market agreement (20pts): If Pinnacle agrees = full
      Volatility (10pts):    Low std dev = confident
    
    80-100 = HIGH confidence (trust the projection)
    60-79  = MODERATE confidence
    40-59  = LOW confidence (use with caution)
    <40    = SKIP
    """
    score = 0

    # Sample size (25pts)
    if sample_n >= 10:
        score += 25
    elif sample_n >= 5:
        score += int(sample_n / 10 * 25)
    else:
        score += int(sample_n / 5 * 12)

    # Injury certainty (25pts)
    inj = (injury_status or "").upper()
    if not inj or inj in ("ACTIVE", "AVAILABLE", ""):
        score += 25
    elif inj == "PROBABLE":
        score += 20
    elif inj == "QUESTIONABLE":
        score += 12
    elif inj == "DOUBTFUL":
        score += 4
    elif inj == "OUT":
        score += 0

    # Lineup confirmed (20pts) — mainly MLB
    if lineup_confirmed is True:
        score += 20
    elif lineup_confirmed is False:
        score += 8
    else:
        score += 14  # Unknown — neutral

    # Market agreement (20pts)
    if market_edge is not None:
        if abs(market_edge) >= 0.05:
            score += 20   # Strong market signal
        elif abs(market_edge) >= 0.02:
            score += 14
        else:
            score += 8

    # Volatility (10pts)
    if volatility is not None:
        if volatility <= 0.15:
            score += 10   # Low variance player
        elif volatility <= 0.25:
            score += 7
        elif volatility <= 0.35:
            score += 4
        else:
            score += 1

    score = max(0, min(100, score))

    if score >= 80:
        label = "HIGH"
        color = "#22c55e"
    elif score >= 60:
        label = "MODERATE"
        color = "#e8a020"
    elif score >= 40:
        label = "LOW"
        color = "#e04040"
    else:
        label = "SKIP"
        color = "#8a9ab0"

    return {
        "score":      score,
        "label":      label,
        "color":      color,
        "components": {
            "sample":   min(25, score),
            "injury":   min(25, score),
            "lineup":   min(20, score),
            "market":   min(20, score),
            "volatility": min(10, score),
        }
    }


# ── 3. Market Implied Projection ────────────────────────────────
# compute_market_implied_projection — moved to bc_utils.py

def compute_model_vs_market(our_avg, line, stat_type):
    """
    Compare BetCouncil projection vs market implied projection.
    
    If our_avg and the line agree = low edge (market efficient)
    If our_avg >> line = value OVER
    If our_avg << line = value UNDER
    
    Agreement score tells you how much the model diverges from market.
    """
    if not line or not our_avg:
        return None

    line_val = float(line)
    our_val  = float(our_avg)

    if line_val <= 0:
        return None

    divergence = (our_val - line_val) / line_val
    agreement  = max(0, 1 - abs(divergence))

    if divergence >= 0.10:
        signal = "MODEL_BULLISH"
        note   = f"📈 Model ({our_val:.1f}) > Market ({line_val:.1f}) — consider OVER"
    elif divergence <= -0.10:
        signal = "MODEL_BEARISH"
        note   = f"📉 Model ({our_val:.1f}) < Market ({line_val:.1f}) — consider UNDER"
    else:
        signal = "AGREEMENT"
        note   = f"✅ Model ({our_val:.1f}) ≈ Market ({line_val:.1f}) — efficient"

    return {
        "our_avg":    our_val,
        "line":       line_val,
        "divergence": round(divergence, 3),
        "agreement":  round(agreement, 3),
        "signal":     signal,
        "note":       note,
    }


# ── 4. NFL Usage Metrics Framework ──────────────────────────────

def compute_dff_propstats_edge(propstats_data, model_edge):
    """
    Convert DFF hit rate into a small confirmation edge adjustment.
    
    Weight: +1% to +2% max — confirmation only.
    Never overrides Pinnacle EV.
    
    Logic:
      L10 hit rate ≥ 70%: +2% (strong historical confirmation)
      L10 hit rate ≥ 60%: +1% (mild confirmation)
      L10 hit rate ≤ 30%: -2% (historical fade signal)
      L10 hit rate ≤ 40%: -1% (mild fade)
    """
    if not propstats_data:
        return 0.0, ""
    
    hit_rate   = propstats_data.get("hit_rate", 0.5)
    total      = propstats_data.get("total_games", 0)
    avg_val    = propstats_data.get("avg_val", 0)
    avg_mins   = propstats_data.get("avg_minutes", 0)
    avg_pot    = propstats_data.get("avg_potentials", 0)
    line       = propstats_data.get("line", 0)
    
    # Need at least 5 games for signal
    if total < 5:
        return 0.0, f"DFF: {total} games (need 5+)"
    
    notes = []
    adj   = 0.0
    
    # Hit rate signal
    if hit_rate >= 0.70:
        adj += 0.02
        notes.append(f"📈 DFF L{total}: {hit_rate:.0%} hit rate")
    elif hit_rate >= 0.60:
        adj += 0.01
        notes.append(f"✅ DFF L{total}: {hit_rate:.0%} hit rate")
    elif hit_rate <= 0.30:
        adj -= 0.02
        notes.append(f"📉 DFF L{total}: {hit_rate:.0%} hit rate")
    elif hit_rate <= 0.40:
        adj -= 0.01
        notes.append(f"⚠️ DFF L{total}: {hit_rate:.0%} hit rate")
    
    # Avg value vs line
    if avg_val > 0 and line > 0:
        avg_vs_line = (avg_val - line) / line
        if abs(avg_vs_line) >= 0.10:
            dir_str = f"+{avg_vs_line:.0%}" if avg_vs_line > 0 else f"{avg_vs_line:.0%}"
            notes.append(f"avg {avg_val:.1f} vs line {line} ({dir_str})")
    
    # Minutes stability (NBA)
    if avg_mins > 0:
        notes.append(f"{avg_mins:.0f} min avg")
    
    adj = round(max(-0.02, min(0.02, adj)), 3)
    return adj, " | ".join(notes)



# ═══════════════════════════════════════════════════════════════
# TIER 1 HIGH-VALUE FEATURES
# 1. Market Move Quality (sharp attribution)
# 2. Minutes Stability Score (CV)
# 3. Volatility Flag
# 4. Closing Line Hit Rate tracking
# ═══════════════════════════════════════════════════════════════

# ── 1. Market Move Quality ──────────────────────────────────────

def get_clv_summary(history):
    """
    Compute CLV statistics across all resolved bets.
    Returns dict with avg_clv, beat_rate, n_resolved, and grade.
    Per Buchdahl: 50+ resolved bets needed for significance.
    """
    resolved = [
        r for r in (history or [])
        if r.get("clv_capture", {}).get("clv_resolved")
        and r.get("clv_capture", {}).get("clv_vs_novig") is not None
    ]
    if not resolved:
        return {"avg_clv": None, "beat_rate": None, "n_resolved": 0, "grade": "INSUFFICIENT"}

    clv_values = [r["clv_capture"]["clv_vs_novig"] for r in resolved]
    avg_clv    = round(sum(clv_values) / len(clv_values), 4)
    beat_rate  = round(sum(1 for v in clv_values if v > 0) / len(clv_values), 3)
    n          = len(resolved)

    if n < 50:
        grade = "INSUFFICIENT"
    elif avg_clv >= 0.05 and beat_rate >= 0.55:
        grade = "ELITE"
    elif avg_clv >= 0.03 and beat_rate >= 0.52:
        grade = "GOOD"
    elif avg_clv >= 0.01:
        grade = "POSITIVE"
    elif avg_clv >= -0.01:
        grade = "NEUTRAL"
    else:
        grade = "NEGATIVE"

    return {
        "avg_clv":    avg_clv,
        "beat_rate":  beat_rate,
        "n_resolved": n,
        "grade":      grade,
    }

def build_optimal_portfolio(board, n_bets=5, sport=None,
                             max_per_player=1, max_per_game=2,
                             max_volatile=1, min_bq=40):
    """
    Build optimal N-bet portfolio from the board.
    
    Controls:
      max_per_player: max props per player (default 1)
      max_per_game:   max props per game (default 2)
      max_volatile:   max HIGH/EXTREME volatility props
      min_bq:         minimum BQ score to include
    
    Algorithm:
      1. Filter board by min_bq and sport
      2. Sort by BetQualityScore descending
      3. Greedy selection with concentration constraints
      4. Return selected bets + portfolio health metrics
    """
    if not board:
        return [], {}
    
    # Filter and sort
    candidates = [
        p for p in board
        if int(p.get("BetQualityScore", 0) or 0) >= min_bq
        and (sport is None or p.get("Sport","") == sport or p.get("sport","") == sport)
    ]
    candidates.sort(key=lambda x: int(x.get("BetQualityScore",0) or 0), reverse=True)
    
    selected    = []
    player_count = {}
    game_count   = {}
    volatile_count = 0
    
    for prop in candidates:
        if len(selected) >= n_bets:
            break
        
        player  = normalize_name(prop.get("Player",""))
        matchup = prop.get("Matchup", prop.get("matchup",""))
        risk    = prop.get("RiskLevel","")
        
        # Concentration checks
        if player_count.get(player, 0) >= max_per_player:
            continue  # Too many props on same player
        
        if matchup and game_count.get(matchup, 0) >= max_per_game:
            continue  # Too many props from same game
        
        if risk in ("HIGH","EXTREME") and volatile_count >= max_volatile:
            continue  # Too many volatile props
        
        # Add to portfolio
        selected.append(prop)
        player_count[player] = player_count.get(player, 0) + 1
        if matchup:
            game_count[matchup] = game_count.get(matchup, 0) + 1
        if risk in ("HIGH","EXTREME"):
            volatile_count += 1
    
    # Portfolio health metrics
    if not selected:
        return [], {}
    
    avg_bq      = sum(int(p.get("BetQualityScore",0) or 0) for p in selected) / len(selected)
    avg_edge    = sum(float(p.get("Edge",0) or 0) for p in selected) / len(selected)
    n_aligned   = sum(1 for p in selected if p.get("ConflictStatus") == "ALIGNED")
    n_conflicted= sum(1 for p in selected if p.get("ConflictStatus") == "CONFLICTED")
    unique_games= len(set(p.get("Matchup","") for p in selected if p.get("Matchup","")))
    unique_players = len(set(normalize_name(p.get("Player","")) for p in selected))
    
    # Health score 0-100
    health = 50
    health += min(20, int(avg_bq * 0.20))
    health += (n_aligned / len(selected)) * 20
    health -= n_conflicted * 10
    health += (unique_games / max(1, len(selected))) * 10
    health = max(0, min(100, int(health)))
    
    if health >= 80:
        health_label = "🟢 Healthy"
    elif health >= 60:
        health_label = "🟡 Moderate"
    else:
        health_label = "🔴 Concentrated"
    
    metrics = {
        "n_selected":       len(selected),
        "avg_bq":           round(avg_bq, 1),
        "avg_edge":         round(avg_edge * 100, 1),
        "n_aligned":        n_aligned,
        "n_conflicted":     n_conflicted,
        "unique_games":     unique_games,
        "unique_players":   unique_players,
        "volatile_count":   volatile_count,
        "health":           health,
        "health_label":     health_label,
    }
    
    return selected, metrics

def _parse_american(raw):
    """Parse first side of American odds string. '300/-500' → 300.0"""
    try:
        return float(str(raw).split("/")[0].strip())
    except (ValueError, TypeError):
        return None

def _ev_parse_odds(raw):
    """Parse EV bookOdds string: '325' or '300/-595' → (over_str, under_str)."""
    if raw is None:
        return None, None
    raw = str(raw).strip()
    if "/" in raw:
        parts = raw.split("/", 1)
        return parts[0].strip() or None, parts[1].strip() or None
    return raw or None, None

def compute_tier_stats(history):
    stats = {}
    for bet in history:
        tier = bet.get("tier", "UNKNOWN")
        outcome = bet.get("outcome")
        predicted_prob = bet.get("prob", 0.5)
        if outcome not in ("WIN", "LOSS"):
            continue
        if tier not in stats:
            stats[tier] = {"outcomes": [], "predicted": []}
        stats[tier]["outcomes"].append(1 if outcome == "WIN" else 0)
        stats[tier]["predicted"].append(predicted_prob)
    result = {}
    for tier, data in stats.items():
        n = len(data["outcomes"])
        if n == 0:
            continue
        hit_rate = sum(data["outcomes"]) / n
        avg_predicted = sum(data["predicted"]) / n
        sem = (hit_rate * (1 - hit_rate) / n) ** 0.5 if n > 0 else None
        calibration_error = hit_rate - avg_predicted
        result[tier] = {"n": n, "hit_rate": round(hit_rate, 3), "avg_predicted": round(avg_predicted, 3), "sem": round(sem, 3) if sem else None, "calibration_error": round(calibration_error, 3)}
    return result

def compute_calibration_buckets(history):
    """
    Bucket calibration tracking — the most important model quality metric.
    Splits resolved bets into probability buckets and compares
    predicted probability vs actual hit rate per bucket.
    
    Elite models: predicted % ≈ actual hit rate in each bucket.
    If 65% bucket hits only 52%, model is systematically overconfident.
    
    Activates at 30+ resolved bets for meaningful buckets.
    """
    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS")]
    if len(resolved) < 30:
        return None, len(resolved)
    
    # Define buckets: center, label, range
    buckets = [
        (0.25, "20-30%", 0.20, 0.30),
        (0.35, "30-40%", 0.30, 0.40),
        (0.45, "40-50%", 0.40, 0.50),
        (0.55, "50-60%", 0.50, 0.60),
        (0.60, "55-65%", 0.55, 0.65),
        (0.65, "60-70%", 0.60, 0.70),
        (0.70, "65-75%", 0.65, 0.75),
        (0.75, "70-80%", 0.70, 0.80),
    ]
    
    results = []
    for center, label, low, high in buckets:
        bucket_bets = [
            h for h in resolved
            if low <= float(h.get("prob", 0) or 0) < high
        ]
        if len(bucket_bets) < 5:
            continue
        n = len(bucket_bets)
        actual_hr = sum(1 for h in bucket_bets if h.get("outcome") == "WIN") / n
        avg_predicted = sum(float(h.get("prob",0.5) or 0.5) for h in bucket_bets) / n
        error = actual_hr - avg_predicted
        # Calibration grade
        if abs(error) < 0.03:
            grade = "🟢 Excellent"
        elif abs(error) < 0.07:
            grade = "🟡 Good"
        elif abs(error) < 0.12:
            grade = "🟠 Fair"
        else:
            grade = "🔴 Needs Work"
        overunder = "OVER-confident" if error < -0.03 else ("UNDER-confident" if error > 0.03 else "Calibrated")
        results.append({
            "Bucket":       label,
            "Bets":         n,
            "Predicted":    f"{avg_predicted:.1%}",
            "Actual":       f"{actual_hr:.1%}",
            "Error":        f"{error:+.1%}",
            "Grade":        grade,
            "Bias":         overunder,
        })
    
    return results, len(resolved)

def get_calibration_summary(history):
    """
    Single-line calibration health summary for Gem Brief and Summary tab.
    Returns a string like: "Calibration: GOOD (avg error +2.1%, n=45)"
    """
    resolved = [h for h in history if h.get("outcome") in ("WIN","LOSS")]
    if len(resolved) < 30:
        return f"Calibration: INSUFFICIENT DATA ({len(resolved)}/30 bets)"
    buckets, n = compute_calibration_buckets(history)
    if not buckets:
        return f"Calibration: NO DATA"
    errors = [abs(float(b["Error"].replace("%","").replace("+",""))/100) for b in buckets]
    avg_error = sum(errors) / len(errors)
    if avg_error < 0.03:
        status = "EXCELLENT"
    elif avg_error < 0.07:
        status = "GOOD"
    elif avg_error < 0.12:
        status = "FAIR"
    else:
        status = "NEEDS CALIBRATION"
    return f"Calibration: {status} (avg error {avg_error:.1%}, n={n})"


# compute_sem_for_tier — moved to bc_utils.py

def prizepicks_breakeven_prob(n_picks=2):
    multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)
    return round((1 / multiplier) ** (1 / n_picks), 4)

def calculate_prizepicks_ev(fair_prob, n_picks=2):
    breakeven = prizepicks_breakeven_prob(n_picks)
    return round(fair_prob - breakeven, 4)

def get_tier(edge, sport  # Maps edge % to tier: SOVEREIGN/ELITE/APPROVED/LEAN/PASS
="NBA") -> str:
    try:
        edge = float(edge or 0)
    except (TypeError, ValueError):
        edge = 0.0
    thresholds = TIER_THRESHOLDS.get(sport, TIER_THRESHOLDS["NBA"])
    if edge >= thresholds["SOVEREIGN"]: return "SOVEREIGN"
    if edge >= thresholds["ELITE"]:     return "ELITE"
    if edge >= thresholds["APPROVED"]:  return "APPROVED"
    if edge >= thresholds["LEAN"]: return "LEAN"
    return "PASS"

# parlay_prob — moved to utils.py
# parlay_payout — moved to utils.py

def compute_clv_grade(clv_value, pinnacle_edge=None):
    """
    Grade the CLV performance.
    Elite bettors consistently beat closing line.
    +EV if consistently positive CLV vs Pinnacle.
    """
    if clv_value is None:
        return "—", "#6a7a8a"
    if clv_value >= 1.5:
        return "ELITE CLV", "#22c55e"
    elif clv_value >= 0.5:
        return "GOOD CLV", "#0ea5a0"
    elif clv_value >= 0:
        return "NEUTRAL", "#e8a020"
    elif clv_value >= -0.5:
        return "POOR CLV", "#e07020"
    else:
        return "BAD CLV", "#e04040"

def calculate_lock_quality_score(prop):
    score = 0
    edge = prop.get("Edge", 0)
    if isinstance(edge, (int, float)):
        edge_pts = min(30, edge * 150)
        score += edge_pts
    n_games = prop.get("SampleSize", 0)
    if isinstance(n_games, (int, float)) and n_games > 0:
        sample_pts = min(25, n_games * 2.5)
        score += sample_pts
    elif prop.get("Quality") == "Lookup":
        score += 12
    eff_score = prop.get("EffScore", 0)
    if isinstance(eff_score, (int, float)):
        score += min(20, eff_score * 20)
    source = prop.get("source", "")
    if "PrizePicks" in source:
        score += 15
    elif "Underdog" in source:
        score += 10
    elif source.startswith("oddswrap"):
        score += 8
    elif source.startswith("OddsAPI"):
        score += 12
    elif source.startswith("BDL"):
        score += 10
    elif source.startswith("ParlayPlay_Alt"):
        score += 14
    elif source.startswith("ParlayPlay"):
        score += 12
    else:
        score += 5
    if prop.get("Injury"):
        score -= 10
    sharp = prop.get("SharpFlag", "")
    if sharp and "↑" in sharp:
        score += 5
    clv_adj = prop.get("CLVAdj", "")
    if clv_adj and "Boosted" in str(clv_adj):
        score += 3
    # ── Projection confidence adjustment (new) ──────────────
    conf = prop.get("ProjConfidence", 50)
    if isinstance(conf, (int, float)):
        if conf >= 80:
            score += 5    # High confidence boost
        elif conf < 40:
            score -= 8    # Low confidence penalty
        elif conf < 60:
            score -= 3    # Moderate confidence minor penalty
    # ── Role change boost ────────────────────────────────────
    rc = prop.get("RoleChange")
    if rc and rc.get("direction") == "UP":
        score += 4    # Role increasing = more upside
    elif rc and rc.get("direction") == "DOWN":
        score -= 6    # Role decreasing = risky
    return round(min(100, max(0, score)), 1)

def detect_game_script_contradictions(parlay_props, games):
    warnings = []
    if not parlay_props or not games:
        return warnings
    game_total_map = {}
    for game in games:
        matchup = game.get("Matchup","")
        total = game.get("Total","N/A")
        if total and total != "N/A":
            try:
                game_total_map[matchup] = float(total)
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
    for i, j in combinations(range(len(parlay_props)), 2):
        p1 = parlay_props[i]
        p2 = parlay_props[j]
        team1 = PLAYER_TEAM_MAP.get(p1["Player"],"")
        team2 = PLAYER_TEAM_MAP.get(p2["Player"],"")
        shared_game = None
        for matchup in game_total_map:
            if team1 and team1 in matchup:
                if team2 and team2 in matchup:
                    shared_game = matchup
                    break
        if not shared_game:
            continue
        game_total = game_total_map.get(shared_game, 0)
        stat1 = STAT_NORMALIZE.get((p1.get("Sport","NBA"), p1["Prop"]), p1["Prop"])
        stat2 = STAT_NORMALIZE.get((p2.get("Sport","NBA"), p2["Prop"]), p2["Prop"])
        if (stat1 == "PTS" and p1["Side"] == "OVER" and game_total > 0 and game_total < 210):
            warnings.append(f"⚠️ Contradiction: {p1['Player']} PTS OVER but game total {game_total} is very low. Low scoring game hurts PTS props.")
        pos1 = NBA_PLAYER_POSITIONS.get(p1["Player"],"")
        pos2 = NBA_PLAYER_POSITIONS.get(p2["Player"],"")
        if (pos1 == "C" and pos2 == "C" and team1 != team2 and stat1 == "REB" and stat2 == "REB" and p1["Side"] == "OVER" and p2["Side"] == "OVER"):
            warnings.append(f"⚠️ Contradiction: {p1['Player']} and {p2['Player']} are both centers in the same game going OVER rebounds. They compete for the same boards.")
        if team1 and team2 and team1 != team2:
            pace1 = NBA_TEAM_PACE.get(team1, 99.5)
            pace2 = NBA_TEAM_PACE.get(team2, 99.5)
            if (abs(pace1 - pace2) < 2 and stat1 in ["PTS","AST","REB"] and stat2 in ["PTS","AST","REB"]):
                pass
            elif (pace1 < 98 and p1["Side"] == "OVER" and stat1 == "PTS"):
                warnings.append(f"📊 Note: {p1['Player']} plays for slow-paced {team1} ({pace1:.1f} pace). Fewer possessions may limit counting stats.")
        for game in games:
            matchup = game.get("Matchup","")
            if team1 in matchup:
                spread = game.get("Spread","")
                if spread and spread != "N/A":
                    try:
                        spread_val = abs(float(str(spread).split()[-1]))
                        if (spread_val > 12 and stat1 == "PTS" and p1["Side"] == "OVER"):
                            fav_team = str(spread).split()[0]
                            if team1 == fav_team:
                                warnings.append(f"⚠️ Blowout risk: {p1['Player']} on {team1} favored by {spread_val}pts. May sit late if big lead develops.")
                    except (ValueError, KeyError, TypeError):
                        pass
    return warnings

def weather_edge_adjustment(weather, stat_norm, side="OVER", sport="MLB"):
    if not weather:
        return 0.0, ""
    adjustment = 0.0
    notes = []
    wind_speed = weather.get("wind_speed_mph", 0)
    wind_dir   = weather.get("wind_dir", "N")
    temp       = weather.get("temp_f", 70)
    humidity   = weather.get("humidity", 50)
    out_winds  = ["SW", "WSW", "W", "WNW", "NW", "S", "SSW"]
    in_winds   = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE"]

    # ── MLB adjustments (existing) ────────────────────────────
    if stat_norm == "HR":
        if wind_dir in out_winds and wind_speed >= 15:
            adj = min(0.08, wind_speed / 100)
            adjustment += adj if side == "OVER" else -adj
            notes.append(f"💨 Wind {wind_speed}mph out — HR boost")
        elif wind_dir in in_winds and wind_speed >= 15:
            adj = min(0.08, wind_speed / 100)
            adjustment -= adj if side == "OVER" else -adj
            notes.append(f"💨 Wind {wind_speed}mph in — HR penalty")
        if temp < 45:
            cold_adj = (45 - temp) / 100
            adjustment -= cold_adj if side == "OVER" else -cold_adj
            notes.append(f"🥶 Cold ({temp}°F) — HR penalty")
        elif temp > 90:
            hot_adj = (temp - 90) / 200
            adjustment += hot_adj if side == "OVER" else -hot_adj
            notes.append(f"🌡️ Hot ({temp}°F) — HR boost")
    elif stat_norm == "H":
        if wind_dir in out_winds and wind_speed >= 20:
            adjustment += 0.03 if side == "OVER" else -0.03
            notes.append("💨 Wind out — hits boost")
        elif wind_dir in in_winds and wind_speed >= 20:
            adjustment -= 0.03 if side == "OVER" else -0.03
            notes.append("💨 Wind in — hits penalty")
        if temp < 45:
            adjustment -= 0.03 if side == "OVER" else -0.03

    # ── NFL adjustments (new) ─────────────────────────────────
    # Source: academic research on weather impact on NFL scoring
    # Wind is most significant factor; rain/snow secondary
    elif sport == "NFL":
        if stat_norm in ("PassYds", "pass_yds", "PASS", "PassingYards"):
            # Passing yards hurt most by wind
            if wind_speed >= 25:
                adj = min(0.15, (wind_speed - 25) * 0.006 + 0.10)
                adjustment -= adj if side == "OVER" else -adj
                notes.append(f"💨 High wind ({wind_speed}mph) — passing yards -{adj:.0%}")
            elif wind_speed >= 15:
                adj = 0.08
                adjustment -= adj if side == "OVER" else -adj
                notes.append(f"💨 Wind {wind_speed}mph — passing yards -{adj:.0%}")
            if temp < 20:
                adjustment -= 0.06 if side == "OVER" else -0.06
                notes.append(f"🥶 Extreme cold ({temp}°F) — passing penalty")
            elif temp < 35:
                adjustment -= 0.03 if side == "OVER" else -0.03
                notes.append(f"🥶 Cold ({temp}°F) — passing penalty")

        elif stat_norm in ("RecYds", "rec_yds", "REC", "ReceivingYards"):
            # Receiving yards correlate with passing yards
            if wind_speed >= 25:
                adj = min(0.12, (wind_speed - 25) * 0.005 + 0.08)
                adjustment -= adj if side == "OVER" else -adj
                notes.append(f"💨 High wind ({wind_speed}mph) — rec yards -{adj:.0%}")
            elif wind_speed >= 15:
                adjustment -= 0.06 if side == "OVER" else -0.06
                notes.append(f"💨 Wind {wind_speed}mph — rec yards -6%")
            if temp < 20:
                adjustment -= 0.04 if side == "OVER" else -0.04

        elif stat_norm in ("RushYds", "rush_yds", "RUSH", "RushingYards"):
            # Rushing yards slightly boosted by bad weather (teams run more)
            if wind_speed >= 20 or temp < 30:
                adjustment += 0.04 if side == "OVER" else -0.04
                notes.append(f"🌧️ Bad weather — rushing boost +4%")

        elif stat_norm in ("Receptions", "rec", "REC_COUNT"):
            # Receptions (catches) hurt by wind/rain
            if wind_speed >= 20:
                adjustment -= 0.05 if side == "OVER" else -0.05
                notes.append(f"💨 Wind {wind_speed}mph — reception count -5%")

        elif stat_norm in ("Touchdowns", "td", "TD"):
            # TDs correlate with total scoring — hurt by bad weather
            if wind_speed >= 20:
                adjustment -= 0.04 if side == "OVER" else -0.04
            if temp < 20:
                adjustment -= 0.03 if side == "OVER" else -0.03
            if notes or adjustment != 0:
                notes.append(f"🌧️ Weather reducing TD probability")

        elif stat_norm in ("Completions", "cmp", "PassCompletions"):
            if wind_speed >= 15:
                adj = min(0.10, wind_speed * 0.004)
                adjustment -= adj if side == "OVER" else -adj
                notes.append(f"💨 Wind {wind_speed}mph — completion % -{adj:.0%}")

    return round(adjustment, 3), " | ".join(notes)

# get_weighted_average — moved to bc_utils.py
# get_recency_context — moved to bc_utils.py
# sample_size_confidence — moved to bc_utils.py

def get_edge_staleness(last_scan_time):
    if not last_scan_time:
        return "⚫ Never loaded", "black"
    try:
        last = datetime.strptime(last_scan_time, "%H:%M:%S")
        now = datetime.now()
        elapsed_minutes = ((now.hour * 60 + now.minute) - (last.hour * 60 + last.minute))
        if elapsed_minutes < 0:
            elapsed_minutes += 1440
        if elapsed_minutes < 15:
            return f"🟢 Fresh ({elapsed_minutes}m ago)", "green"
        elif elapsed_minutes < 30:
            return f"🟡 Aging ({elapsed_minutes}m ago)", "yellow"
        elif elapsed_minutes < 60:
            return f"🟠 Stale ({elapsed_minutes}m ago)", "orange"
        else:
            return f"🔴 Very stale ({elapsed_minutes}m ago)", "red"
    except (ValueError, KeyError, TypeError):
        return "⚫ Unknown", "black"

def check_portfolio_correlation(new_prop, existing_locks, player_team_map, positive_correlations, negative_correlations):
    warnings = []
    new_player = new_prop.get("Player", new_prop.get("player", ""))
    new_sport = new_prop.get("Sport", new_prop.get("sport", ""))
    new_team = player_team_map.get(new_player, "")
    for lock in existing_locks:
        if lock.get("status") != "PENDING":
            continue
        lock_player = lock.get("player", "")
        lock_sport = lock.get("sport", "")
        lock_team = player_team_map.get(lock_player, "")
        if lock_sport != new_sport:
            continue
        if lock_player == new_player:
            warnings.append(f"⚠️ You already have a lock on **{new_player}** — same player props are 25% correlated")
            continue
        if new_team and new_team == lock_team:
            pair = (new_player, lock_player)
            pair_rev = (lock_player, new_player)
            corr = (positive_correlations.get(pair) or positive_correlations.get(pair_rev) or 0.15)
            warnings.append(f"⚠️ **{new_player}** and **{lock_player}** are teammates ({corr:.0%} correlation). Combined probability reduced.")
        same_game_locks = [l for l in existing_locks if (l.get("sport") == new_sport and l.get("status") == "PENDING" and player_team_map.get(l.get("player",""), "") == new_team)]
        if len(same_game_locks) >= 2:
            warnings.append(f"🛑 You already have {len(same_game_locks)} locks from this game. High concentration risk.")
            break
    return warnings

def power_rating_spread_divergence(home_team, away_team, spread_str):
    try:
        if not spread_str or spread_str in ("N/A", "—"):
            return 0, ""
        spread_val = float(str(spread_str).replace("+", "").strip())
        home_rating = NBA_POWER_RATINGS.get(home_team, 104)
        away_rating = NBA_POWER_RATINGS.get(away_team, 104)
        power_diff = home_rating - away_rating
        implied_spread = -power_diff
        divergence = abs(spread_val - implied_spread)
        if divergence >= 6:
            return min(10, divergence), f"⚡ Market diverges from power ratings by {divergence:.1f} pts"
        return 0, ""
    except (ValueError, TypeError, AttributeError):
        return 0, ""

def get_game_tier(edge, sport="NBA") -> str:
    """
    Tier for GAME LINES (spread/total/ML).
    Uses lower thresholds than prop tiers because power rating
    diffs are compressed — a 2% ML edge in MLB is meaningful.
    """
    thresholds = GAME_TIER_THRESHOLDS.get(sport, GAME_TIER_THRESHOLDS["NBA"])
    edge = abs(edge)
    if edge >= thresholds["SOVEREIGN"]: return "SOVEREIGN"
    if edge >= thresholds["ELITE"]:     return "ELITE"
    if edge >= thresholds["APPROVED"]:  return "APPROVED"
    if edge >= thresholds["LEAN"]:      return "LEAN"
    return "PASS"

# Soccer league goal baselines — must be defined before analyze_game_edge

def _load_cache(path, max_age_h=12):
    if os.path.exists(path):
        if (time.time() - os.path.getmtime(path)) / 3600 < max_age_h:
            try:
                with open(path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass
    return None

def _save_cache(path, data):
    try:
        with open(path, "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass


# ── WNBA: full roster + per-player season stats ─────────────────────────────

def find_best_alt_line(matchup, sport, home_power, away_power, home_full, away_full, alt_data=None):
    """
    Find the best alternate spread line that creates a playable edge.
    
    Compares model power rating diff against alternate spread numbers.
    Returns the alternate line with the best edge above APPROVED threshold.
    
    MLB: Run line is always -1.5/+1.5. Best alt = best non-standard number.
    WNBA/NBA: Alternate spreads give options like -3.5 instead of -7.5
    """
    if alt_data is None:
        return None
    game = alt_data.get(matchup, {})
    if not game:
        return None
    
    power_diff = home_power - away_power  # positive = home favored
    APPROVED_THRESHOLD = 0.015 if sport == "MLB" else 0.02
    
    best = None
    best_edge = APPROVED_THRESHOLD  # minimum to surface
    
    for line in game.get("lines", []):
        team  = line.get("team","")
        point = float(line.get("point",0) or 0)
        price = int(line.get("price",0) or 0)
        
        # Determine if this is home or away team line
        is_home = (team == game.get("home",""))
        
        # Model's implied spread: positive power_diff = home favored
        model_spread = power_diff / 10.0  # normalize to spread scale
        
        # Edge = model spread vs this alternate line
        if is_home:
            line_edge = model_spread - point  # positive = home covers this spread
        else:
            line_edge = -model_spread - point  # negative = away covers spread
        
        edge_pct = abs(line_edge) / (10.0 if sport in ("MLB","NHL") else 30.0)
        edge_pct = min(0.20, edge_pct)
        
        if edge_pct > best_edge:
            best_edge = edge_pct
            # Determine tier
            if sport == "MLB":
                tier = "SOVEREIGN" if edge_pct >= 0.06 else "ELITE" if edge_pct >= 0.03 else "APPROVED"
            else:
                tier = "SOVEREIGN" if edge_pct >= 0.12 else "ELITE" if edge_pct >= 0.08 else "APPROVED"
            
            # Format odds
            odds_str = f"+{price}" if price > 0 else str(price)
            best = {
                "team":    team,
                "point":   point,
                "price":   price,
                "pick":    f"{team} {'+' if point > 0 else ''}{point} ({odds_str})",
                "edge":    round(edge_pct, 3),
                "tier":    tier,
                "book":    line.get("book",""),
            }
    return best

def get_best_alt_line_recommendation(*args, **kwargs):
    return None

def detect_sharp_movement(movements):
    if len(movements) < 2:
        return False, "", 0
    first = movements[-1]
    last = movements[0]
    try:
        first_spread = float(first.get("spread") or 0)
        last_spread = float(last.get("spread") or 0)
        spread_move = abs(last_spread - first_spread)
        if spread_move >= 1.5:
            direction = "↑" if last_spread > first_spread else "↓"
            return True, direction, round(spread_move, 1)
        first_ou = float(first.get("over_under") or 0)
        last_ou = float(last.get("over_under") or 0)
        ou_move = abs(last_ou - first_ou)
        if ou_move >= 2.0:
            direction = "↑" if last_ou > first_ou else "↓"
            return True, direction, round(ou_move, 1)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return False, "", 0

def compute_sharp_consensus_no_vig(odds_data, matchup, market="total"):
    """
    Builds consensus fair price from the three sharpest books:
    Pinnacle, Circa Sports, BetOnline.
    
    Stronger signal than single-book no-vig because:
    - Eliminates idiosyncratic book error
    - Captures true market consensus
    - Reduces noise from temporary imbalances
    
    Returns: {"fair_prob": float, "books_used": list, 
              "consensus_line": float, "agreement": str}
    """
    SHARP_BOOKS = ["pinnacle", "circa_sports", "betonlineag"]
    SHARP_LABELS = {
        "pinnacle":    "Pinnacle",
        "circa_sports": "Circa",
        "betonlineag": "BetOnline",
    }
    
    book_probs = {}
    book_lines = {}
    
    for game in (odds_data or []):
        if matchup.lower() not in game.get("Matchup","").lower():
            continue
        for book_key, label in SHARP_LABELS.items():
            over_key  = f"{label} Over"
            under_key = f"{label} Under"
            line_key  = f"{label} Total"
            over_ml   = game.get(over_key)
            under_ml  = game.get(under_key)
            if over_ml and under_ml:
                try:
                    prob = no_vig_prob(int(over_ml), int(under_ml))
                    book_probs[label] = prob
                    if game.get(line_key):
                        book_lines[label] = float(game[line_key])
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

    if not book_probs:
        return None

    books_used  = list(book_probs.keys())
    avg_prob    = sum(book_probs.values()) / len(book_probs)
    avg_line    = sum(book_lines.values()) / len(book_lines) if book_lines else None

    # Agreement check — how spread are the sharp books?
    if len(book_probs) >= 2:
        spread = max(book_probs.values()) - min(book_probs.values())
        if spread < 0.01:
            agreement = "STRONG"   # books within 1% — high conviction
        elif spread < 0.03:
            agreement = "MODERATE"
        else:
            agreement = "DIVERGENT"  # sharp books disagree — flag it
    else:
        agreement = "SINGLE_BOOK"

    return {
        "fair_prob":       round(avg_prob, 4),
        "book_probs":      book_probs,
        "books_used":      books_used,
        "consensus_line":  round(avg_line, 1) if avg_line else None,
        "agreement":       agreement,
        "n_books":         len(book_probs),
        "label":           f"Consensus ({'/'.join(b[:3] for b in books_used)})",
    }

def get_pinnacle_edge(model_prob, pinnacle_prob, side="OVER"):
    """
    Calculate edge vs Pinnacle as the benchmark.
    This is the OddsJam/Outlier methodology.
    positive = we have edge over Pinnacle's true line
    """
    if pinnacle_prob is None or model_prob is None:
        return None
    # Edge = our model prob - Pinnacle true prob
    # If positive, we think this is MORE likely than Pinnacle does
    return round(model_prob - pinnacle_prob, 4)


# =============================================================
# PLAYER LOOKUP ENGINE — H2H, Game Logs, Splits
# Powers the Player Lookup tab and H2H signal
# =============================================================



# compute_h2h_hit_rate — moved to bc_utils.py

def compute_home_away_splits(game_logs, stat, line):
    """Compute home vs away hit rates for a stat."""
    stat_map = {
        "Points": "pts", "Rebounds": "reb", "Assists": "ast",
        "Steals": "stl", "Blocked Shots": "blk", "Turnovers": "turnover",
        "3-PT Made": "fg3m", "Pts+Reb+Ast": "pra",
    }
    stat_key = stat_map.get(stat, "pts")

    home_games = [g for g in game_logs if g.get("home")]
    away_games = [g for g in game_logs if not g.get("home")]

    home_avg = sum(g.get(stat_key,0) or 0 for g in home_games) / len(home_games) if home_games else 0
    away_avg = sum(g.get(stat_key,0) or 0 for g in away_games) / len(away_games) if away_games else 0
    home_hit = sum(1 for g in home_games if (g.get(stat_key,0) or 0) > line) / len(home_games) if home_games else 0
    away_hit = sum(1 for g in away_games if (g.get(stat_key,0) or 0) > line) / len(away_games) if away_games else 0

    return {
        "home_avg": round(home_avg, 1),
        "away_avg": round(away_avg, 1),
        "home_hit_rate": home_hit,
        "away_hit_rate": away_hit,
        "home_games": len(home_games),
        "away_games": len(away_games),
    }

def _merge_rolling(season_avgs, rolling, weight=0.7):
    """Merge rolling averages into season_avgs in-place. weight=rolling share."""
    rnd = 2
    for player, stats in rolling.items():
        if player in season_avgs:
            merged = {
                k: round(v * weight + season_avgs[player].get(k, v) * (1 - weight), rnd)
                for k, v in stats.items() if k != "n_games"
            }
            season_avgs[player] = {**season_avgs[player], **merged}
        else:
            season_avgs[player] = stats


# ── Correlated prop matrix ────────────────────────────────────────────────────
# Pairwise correlation coefficients for same-game prop combinations
# Source: NBA/MLB empirical correlation studies (Rosenblatt 2019, Sharp Edge 2022)
# Used to reduce Kelly sizing when multiple correlated props are in play

PROP_CORRELATION_MATRIX = {
    # NBA — same player
    ("PTS", "PRA"):   0.85,
    ("PTS", "3PT"):   0.70,
    ("PTS", "AST"):   0.45,
    ("PTS", "REB"):   0.30,
    ("REB", "AST"):   0.25,
    ("AST", "PRA"):   0.75,
    ("REB", "PRA"):   0.80,
    # NBA — teammates (same team, different players)
    ("PTS_TEAM", "PTS_TEAM"):  0.35,  # two scorers on same team
    ("AST_TEAM", "PTS_TEAM"):  0.20,
    # MLB — same game
    ("HITS", "RBI"):     0.55,
    ("HITS", "RUNS"):    0.50,
    ("HR",   "RBI"):     0.70,
    ("HR",   "HITS"):    0.45,
    ("SO",   "HITS"):   -0.30,  # negative: more Ks → fewer hits for batters
    # NFL — same game
    ("PASS_YDS", "RECV_YDS"):  0.72,  # QB + WR1 highly correlated
    ("PASS_YDS", "RECV_YDS2"): 0.55,  # QB + WR2
    ("RUSH_YDS", "RECV_YDS"):  0.15,  # RB rushing vs WR receiving (low corr)
    ("PASS_TDS", "RECV_TDS"):  0.80,  # QB TDs + receiver TDs nearly identical
}

def get_prop_correlation(prop1: str, prop2: str, same_player: bool = True) -> float:
    """
    Return correlation coefficient between two props.
    Used to scale Kelly sizing when multiple correlated props are in play.

    Args:
        prop1, prop2:  Normalized prop type strings (e.g. "PTS", "REB")
        same_player:   Whether both props are for the same player

    Returns:
        Correlation coefficient 0.0-1.0 (0 = independent, 1 = identical)
    """
    p1 = prop1.upper().strip()
    p2 = prop2.upper().strip()

    # Same prop = perfect correlation
    if p1 == p2:
        return 1.0

    # Check matrix (both orderings)
    corr = PROP_CORRELATION_MATRIX.get((p1, p2)) or PROP_CORRELATION_MATRIX.get((p2, p1))
    if corr is not None:
        return corr

    # Cross-player same team: halve the same-player correlation
    if not same_player:
        corr = PROP_CORRELATION_MATRIX.get((p1 + "_TEAM", p2 + "_TEAM"), 0.0)
        return corr * 0.5

    return 0.0


def correlated_kelly_adjustment(props: list[dict]) -> float:
    """
    Calculate Kelly size multiplier when multiple correlated props are active.

    Args:
        props: list of {prop_type, kelly_size, player, team} dicts

    Returns:
        Multiplier (0.5-1.0) to apply to each prop's Kelly size.
        Lower = more correlated = more size reduction.
    """
    if len(props) <= 1:
        return 1.0

    max_corr = 0.0
    for i, p1 in enumerate(props):
        for p2 in props[i+1:]:
            same_player = p1.get("player") == p2.get("player")
            corr = get_prop_correlation(
                p1.get("prop_type", ""),
                p2.get("prop_type", ""),
                same_player
            )
            max_corr = max(max_corr, corr)

    # Scale: 0 corr → 1.0 mult, 1.0 corr → 0.5 mult
    return round(max(0.50, 1.0 - max_corr * 0.50), 3)



def validate_mode_a_brief(brief_dict: dict) -> dict:
    """
    Validate that a MODE A brief from app.py contains all fields GEM expects.
    Returns {valid: bool, missing: list, warnings: list}
    """
    # Fields GEM reads from the brief (from GEM system prompt analysis)
    REQUIRED_FIELDS = [
        "sport", "date", "player", "prop", "line",
        "player_avg", "edge", "tier", "fair_prob",
        "over_odds", "under_odds", "book",
    ]
    OPTIONAL_FIELDS = [
        "h2h_rate", "hit_rate", "clv_est", "pinnacle_prob",
        "ev_api_line", "regime", "sharp_signal", "lqs_score",
        "sample_n", "std_dev", "kelly_size", "bet_size",
        "away_team", "home_team", "game_time",
    ]

    missing  = [f for f in REQUIRED_FIELDS if f not in brief_dict]
    present  = [f for f in OPTIONAL_FIELDS if f in brief_dict]
    warnings = []

    if brief_dict.get("edge", 0) > 0.20:
        warnings.append("edge >20% — verify not a calculation error")
    if brief_dict.get("fair_prob", 0.5) in (0.0, 1.0):
        warnings.append("fair_prob at boundary (0 or 1) — likely parse error")
    if not brief_dict.get("over_odds") and not brief_dict.get("under_odds"):
        warnings.append("no odds provided — GEM cannot devig")

    return {
        "valid":    len(missing) == 0,
        "missing":  missing,
        "optional_present": present,
        "warnings": warnings,
        "completeness": len(present) / max(1, len(OPTIONAL_FIELDS)),
    }

