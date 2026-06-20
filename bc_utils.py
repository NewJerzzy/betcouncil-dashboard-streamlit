"""BetCouncil Utilities — helper functions used across the app."""
import re
import os
import json
import math
import pickle
from math import exp, factorial, log, sqrt, floor, ceil, pi
import pandas as pd
from datetime import datetime, date, timedelta
import unicodedata
from functools import lru_cache
from scipy import stats as scipy_stats

# Inline to avoid circular import through config.py (which imports streamlit)
SPORT_EWMA_DECAY = {"NBA": 0.85, "MLB": 0.92, "NHL": 0.88, "WNBA": 0.85, "NFL": 0.80}


def safe_float(val, default: float = 0.0) -> float:
    """Type-safe float conversion with fallback."""
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default



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
        # Normalize then map to Z-space
        z_over = scipy_stats.norm.ppf(min(max(p_over / total, 0.0001), 0.9999))
        fair_p = float(scipy_stats.norm.cdf(z_over))
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
        if any(p in prop_lower for p in ["pts","reb","ast","pra","dd","stl","blk","min","3pt"]):
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
        b    = (odds / 100) if odds > 0 else (100 / abs(odds))
        p    = max(0.01, min(0.99, 0.524 + edge))   # implied win prob from edge
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
    return round(max(0.20, min(0.80, prob)), 4)


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
    return round(max(0.20, min(0.80, prob)), 4)


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
ELO_K_FACTOR = {"NFL": 20, "NBA": 20, "WNBA": 20, "NHL": 20, "Soccer": 20}


def elo_expected_score(rating_a, rating_b):
    """Standard Elo win-probability formula for team A vs team B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def elo_update(rating_a, rating_b, score_a, k=20):
    """Incremental Elo update after a game result.
    score_a: 1.0 = team A win, 0.5 = draw/tie, 0.0 = team A loss.
    Returns (new_rating_a, new_rating_b). Seeds at ELO_DEFAULT_RATING (1500) for
    unseen teams — this is a forward-updating tracker, not a historical backfill,
    so ratings are most reliable after the first several weeks of a season as they
    converge, same cold-start behavior as any live Elo system."""
    expected_a = elo_expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a
    new_a = rating_a + k * (score_a - expected_a)
    new_b = rating_b + k * (score_b - expected_b)
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


def detect_season_regime(sport="NBA"):
    """
    Detect current season phase and return weight adjustments.
    Used by enrichment loop (S weight modifiers) and History tab display.
    Returns: {regime, description, adjustments, month}
    """
    month = date.today().month

    if sport in ("NBA", "WNBA"):
        if month in (10, 11):
            regime = "Early Season"
            desc   = "First month — small sample, base stats less reliable"
            adj    = {"base": -0.04, "defense": -0.03}
        elif month in (4, 5, 6):
            regime = "Playoffs"
            desc   = "Playoffs — defense weight increases, pace less predictive"
            adj    = {"defense": 0.04, "pace": -0.02}
        elif month in (3,):
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
        else:
            regime = "Mid Season"
            desc   = "Full weights active"
            adj    = {}
    elif sport == "NFL":
        if month in (9,):
            regime = "Early Season"
            desc   = "Early NFL — base signal less reliable"
            adj    = {"base": -0.05}
        elif month in (1,):
            regime = "Playoffs"
            desc   = "NFL Playoffs — defense weight increases significantly"
            adj    = {"defense": 0.06}
        elif month in (12,):
            regime = "Late Season"
            desc   = "Late NFL — rest critical"
            adj    = {"rest": 0.03}
        else:
            regime = "Mid Season"
            desc   = "Full weights active"
            adj    = {}
    else:
        regime = "Mid Season"
        desc   = "Full weights active"
        adj    = {}

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
    """Check if date_str is today or yesterday."""
    try:
        from datetime import timedelta as _td
        today = date.today()
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

