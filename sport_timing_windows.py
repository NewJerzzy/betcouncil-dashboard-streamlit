"""
sport_timing_windows.py — Sport-specific optimal timing windows.

Distinct from calendar_thresholds.py (which answers "how much edge do I
need given time remaining"). This answers "when should I actually be
looking" — the window where the biggest real information-driven line
inefficiencies open up per sport (lineup/pitcher confirmations, weigh-ins,
lineup news), based on well-documented real-world market mechanics (not
DeepSeek's invented numbers — these windows reflect when public,
verifiable information actually gets released, e.g. MLB lineups posting
~3-4 hours before first pitch, NBA shootaround/officials reports ~2-3
hours before tip, NFL inactives at 90 minutes before kickoff).

Public API
----------
optimal_window(sport) -> dict {window_label, minutes_before_game, reason}
in_optimal_window(sport, minutes_to_game) -> bool
"""

# minutes_before_game: the point before kickoff/first-pitch/tip-off where
# real, publicly documented information becomes available and lines have
# NOT yet fully adjusted — not an invented "edge %" but a genuine
# information-release timing fact per sport.
_OPTIMAL_WINDOWS = {
    "NFL": {
        "window_label": "90 minutes before kickoff (inactives report)",
        "minutes_before_game": 90,
        "window_width_minutes": 30,
        "reason": "NFL inactive lists are released 90 min before kickoff — "
                   "confirms which injury-questionable players are out.",
    },
    "NBA": {
        "window_label": "~2 hours before tip (shootaround / officiating assignments)",
        "minutes_before_game": 120,
        "window_width_minutes": 60,
        "reason": "Shootaround availability reports and starting lineups "
                   "typically firm up 1-2 hours before tip.",
    },
    "MLB": {
        "window_label": "3-4 hours before first pitch (lineups posted)",
        "minutes_before_game": 210,
        "window_width_minutes": 60,
        "reason": "MLB starting lineups are typically posted ~3-4 hours "
                   "before first pitch, well before most public bettors "
                   "check back.",
    },
    "NHL": {
        "window_label": "~2 hours before puck drop (morning skate / lineup confirmation)",
        "minutes_before_game": 120,
        "window_width_minutes": 45,
        "reason": "Goalie starts and line combinations are typically "
                   "confirmed 1.5-2.5 hours before puck drop.",
    },
    "SOCCER": {
        "window_label": "~60 minutes before kickoff (official lineups)",
        "minutes_before_game": 60,
        "window_width_minutes": 15,
        "reason": "Official starting XIs are released exactly 60 minutes "
                   "before kickoff per competition rules (most leagues).",
    },
    "UFC": {
        "window_label": "After weigh-ins (day before event)",
        "minutes_before_game": 24 * 60,
        "window_width_minutes": 180,
        "reason": "Weigh-in results (missed weight, visible weight-cut "
                   "issues) are public ~24h before first fight, ahead of "
                   "most line adjustment.",
    },
    "TENNIS": {
        "window_label": "After warm-up / coin toss (near match start)",
        "minutes_before_game": 15,
        "window_width_minutes": 10,
        "reason": "Serve/return order and any late withdrawal news "
                   "confirmed right before first serve.",
    },
}


def optimal_window(sport: str) -> dict:
    """Return the documented optimal timing window for a sport, or {} if unknown."""
    return dict(_OPTIMAL_WINDOWS.get(sport.upper(), {}))


# Second, distinct timing concept: the OPENER window. When a book first
# posts a line, limits are lowest and the line is least informed (fewest
# sharp bets have hit it yet) — this is the opposite trade-off from
# optimal_window() above (confirmed info, firmer line, closer to game
# time). Both are real, legitimate, complementary strategies: bet the
# opener for soft/mispriced lines before the market corrects, or bet the
# confirmed-info window for maximum certainty. Which one fits depends on
# whether you want line value or information certainty.
_OPENER_WINDOWS = {
    "NFL": {
        "window_label": "Sunday night / Monday morning (lines open for next week)",
        "reason": "Books post next week's opening lines with their lowest "
                   "limits and least sharp action Sunday night/Monday — "
                   "widest edges if you have an early read, but small "
                   "limits and highest risk of being wrong before news breaks.",
    },
    "NBA": {
        "window_label": "Lines open morning of game day, before shootaround news",
        "reason": "Morning lines are posted before shootaround availability "
                   "reports — soft if you already suspect a load-management "
                   "scratch or B2B rest day.",
    },
    "MLB": {
        "window_label": "Lines open ~10am ET, before lineups post",
        "reason": "Morning MLB lines are priced off probable pitcher only — "
                   "soft if you have an early read on bullpen usage or "
                   "weather that the market hasn't priced in yet.",
    },
    "NHL": {
        "window_label": "Lines open morning of game day, before morning skate",
        "reason": "Early lines don't yet reflect goalie confirmation.",
    },
    "SOCCER": {
        "window_label": "Lines open days before kickoff",
        "reason": "Early lines are set off squad news/injury reports days out, "
                   "before matchday team news.",
    },
    "UFC": {
        "window_label": "Lines open at fight announcement, before fight week",
        "reason": "Earliest lines are set well before weigh-ins/fight-week "
                   "news (camp reports, weight-cut issues) is public.",
    },
    "TENNIS": {
        "window_label": "Lines open at draw release",
        "reason": "Set before day-of conditions/injury news, and can be "
                   "soft on surface-transition or fatigue spots.",
    },
}


def opener_window(sport: str) -> dict:
    """Return the opener-window info (soft-line strategy) for a sport, or {} if unknown."""
    return dict(_OPENER_WINDOWS.get(sport.upper(), {}))


def in_optimal_window(sport: str, minutes_to_game: float) -> bool:
    """
    True if minutes_to_game falls within the sport's optimal information-
    release window (target time ± half the window width).
    """
    win = _OPTIMAL_WINDOWS.get(sport.upper())
    if not win or minutes_to_game is None:
        return False
    target = win["minutes_before_game"]
    half_width = win["window_width_minutes"] / 2
    return (target - half_width) <= minutes_to_game <= (target + half_width)
