"""BetCouncil Utilities — helper functions used across the app."""
import re
import os
import json
import math
import pickle
from math import exp, factorial, log, sqrt, floor, ceil, pi
import unicodedata
from functools import lru_cache


def safe_float(val, default: float = 0.0) -> float:
    """Type-safe float conversion with fallback."""
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default



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
    """Calculate no-vig true probability from both sides."""
    try:
        over_imp = american_to_prob(over_american)
        under_imp = american_to_prob(under_american)
        total = over_imp + under_imp
        if total <= 0:
            return 0.5
        return round(over_imp / total, 4)
    except (TypeError, ValueError):
        return 0.5


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


def calculate_edge(fair_prob, side="OVER", sport="NBA"):
    """
    Single source of truth for sportsbook edge calculation.
    All prop edge calculations must use this function.
    
    Returns signed edge: positive = good bet, negative = fade.
    For display: use abs(calculate_edge(...))
    The sign is preserved internally for UNDER detection logic.
    
    Breakeven: sportsbook -110 = 52.4%
    For DFS props use calculate_prizepicks_ev() instead.
    """
    breakeven = 0.524  # -110 standard juice
    return round(fair_prob - breakeven, 4)



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
    return round(max(0.20, min(0.80, prob)), 4)


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

