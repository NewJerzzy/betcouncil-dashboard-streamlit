"""
calendar_thresholds.py — Calendar-aware edge thresholds.

Pure math on data you already have (game start time, your model's raw
edge number). No new data source.

Rationale: a given edge% means different things depending on how much
time/information remains before the market closes. Early in the week
(NFL) or early morning (MLB/NBA same-day), lines are thin and more likely
to be stale/inefficient — but also more likely to move further before
close, so a small edge is less trustworthy as a final number. Close to
game time, the market has absorbed lineups/weather/injury news and grown
efficient — so a surviving edge close to close is more meaningful, not
less. This module raises the bar for "how much edge is required to call
a signal real" the further out you are from game time, and lowers it as
game time approaches and the line has had time to firm up.

Public API
----------
required_edge_threshold(sport, minutes_to_game, is_weekend_primetime=False) -> float
passes_calendar_adjusted_threshold(raw_edge_pct, sport, minutes_to_game, ...) -> bool
"""
from datetime import datetime

# Base minimum edge% required at each remaining-time bucket, per sport.
# Buckets are wider (require more edge) far from game time, and tighten
# (require less edge / trust the number more) close to close.
_BASE_THRESHOLDS = {
    "NFL": [
        (24 * 60, 5.0),   # 24h+ out: need 5%+ edge to trust it
        (6 * 60, 3.5),    # 6-24h out
        (2 * 60, 2.5),    # 2-6h out
        (60, 1.5),        # 1-2h out
        (0, 1.0),         # <1h out: line has firmed, trust smaller edges
    ],
    "NBA": [
        (12 * 60, 5.0),
        (4 * 60, 3.5),
        (90, 2.5),
        (30, 1.5),
        (0, 1.0),
    ],
    "MLB": [
        (18 * 60, 5.0),   # starting pitcher / lineup uncertainty far out
        (6 * 60, 3.5),
        (90, 2.5),
        (30, 1.5),
        (0, 1.0),
    ],
    "NHL": [
        (12 * 60, 5.0),
        (4 * 60, 3.5),
        (90, 2.5),
        (30, 1.5),
        (0, 1.0),
    ],
}
_DEFAULT_THRESHOLDS = _BASE_THRESHOLDS["NFL"]

# Sunday afternoon NFL, primetime games etc. draw the most efficient
# (sharpest, most liquid) market action — require slightly more edge
# since more eyes have already priced it.
_PRIMETIME_MULTIPLIER = 1.15


def required_edge_threshold(sport: str, minutes_to_game: float,
                             is_weekend_primetime: bool = False) -> float:
    """
    Return the minimum edge% (e.g. 3.5 = 3.5%) required to treat a signal
    as real, given how much time remains before game start.
    """
    buckets = _BASE_THRESHOLDS.get(sport.upper(), _DEFAULT_THRESHOLDS)
    threshold = buckets[-1][1]
    for minute_floor, thresh in buckets:
        if minutes_to_game >= minute_floor:
            threshold = thresh
            break
    if is_weekend_primetime:
        threshold *= _PRIMETIME_MULTIPLIER
    return round(threshold, 2)


def passes_calendar_adjusted_threshold(raw_edge_pct: float, sport: str,
                                        minutes_to_game: float,
                                        is_weekend_primetime: bool = False) -> dict:
    """
    Convenience check: does this edge clear the calendar-adjusted bar?
    Returns {passes, required_threshold, raw_edge_pct, margin}.
    """
    required = required_edge_threshold(sport, minutes_to_game, is_weekend_primetime)
    return {
        "passes": raw_edge_pct >= required,
        "required_threshold": required,
        "raw_edge_pct": round(raw_edge_pct, 2),
        "margin": round(raw_edge_pct - required, 2),
    }


def minutes_until(game_time: datetime, now: datetime = None) -> float:
    """Helper: minutes between now and game_time. Negative if game already started."""
    now = now or datetime.now(game_time.tzinfo) if game_time.tzinfo else datetime.now()
    return (game_time - now).total_seconds() / 60.0
