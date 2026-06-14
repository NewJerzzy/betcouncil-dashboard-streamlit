"""BetCouncil Utilities — helper functions used across the app."""
import re
import unicodedata
from functools import lru_cache


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


def get_best_alt_line_recommendation(player_name, stat_name, main_line, main_prob, main_ev, avg, std_dev, sport, bankroll):
    best_alt, all_alts = compute_alt_line_ev(player_name, stat_name, avg, std_dev, sport, bankroll)
    if not best_alt:
        return None
    if best_alt["line"] == main_line:
        return None
    return {
        "player": player_name,
        "stat": stat_name,
        "main_line": main_line,
        "main_ev": main_ev,
        "best_line": best_alt["line"],
        "best_ev": best_alt["ev"],
        "best_odds": best_alt["decimal_odds"],
        "best_payout": best_alt["payout"],
        "fair_prob": best_alt["fair_prob"],
        "wager": best_alt["wager"],
        "ev_improvement": round(best_alt["ev"] - main_ev, 4),
        "all_alts": all_alts,
        "source": "ParlayPlay",
    }


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

