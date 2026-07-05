"""
nfl_key_numbers.py — Key number sensitivity for NFL spread/total movement.

Frequencies below are drawn from verified public research (Action Network,
Covers.com, walterfootball.com margin-of-victory studies since 2003/2015),
not from DeepSeek's unsourced numbers. Approximate and directionally
correct, not claimed as exact:
  Spreads: 3 (~15%), 7 (~9%), 6 (~6%), 10 (~5%), 4 (~4%), 14 (~3%)
  Totals cluster in ranges 37, 39-41, 43-51, 54-55 rather than sharp
  single-number spikes (totals key numbers are "key ranges", per Covers.com
  analysis) — modeled here as a broader per-number weight, lower peak than
  spreads, matching that documented flatness.

Public API
----------
spread_crossing_value(open_line, close_line) -> dict
    {cents_estimate, key_numbers_crossed, raw_move, adjusted_move}
total_crossing_value(open_total, close_total) -> dict
    Same shape, using totals key-number weights.
"""

# Relative importance weight per key number (spreads). Not literal cents —
# a multiplier applied to a base half-point value, calibrated so that
# crossing 3 is worth roughly 4x a non-key half-point move, matching the
# "worst number in football" framing documented across multiple sources.
SPREAD_KEY_NUMBERS = {
    3: 4.0,
    7: 2.5,
    6: 1.6,
    10: 1.4,
    4: 1.2,
    14: 1.1,
}

# Totals key numbers are flatter/"key ranges" rather than sharp spikes
# (Covers.com: peak total frequency ~4%, only ~3% more than the least
# frequent numbers — much flatter than spreads' 3/7). Weighted accordingly,
# lower than any spread key number.
TOTAL_KEY_NUMBERS = {
    41: 1.5,
    44: 1.4,
    37: 1.3,
    47: 1.3,
    51: 1.2,
    43: 1.2,
}

_BASE_HALF_POINT_VALUE = 1.0  # unit weight for a non-key half-point move


def _crossed_numbers(open_val: float, close_val: float, key_map: dict) -> list:
    """
    Return key numbers crossed moving from open_val to close_val (order-
    independent). A move from exactly 3 to 3.5 does NOT cross 3 (it starts
    there and moves away). A move from 2.5 to 3 or 2.5 to 3.5 DOES cross 3.
    """
    lo, hi = (open_val, close_val) if open_val <= close_val else (close_val, open_val)
    return [k for k in key_map if lo < k <= hi]


def spread_crossing_value(open_line: float, close_line: float) -> dict:
    """
    Estimate the REAL significance of a spread move, not just its raw size.
    Moves that cross 3 or 7 are weighted far more heavily than moves of the
    same raw magnitude that don't cross a key number.

    Uses absolute spread values (e.g. -2.5 and -3 -> 2.5 and 3.0) so the
    direction (favorite/underdog) doesn't matter for crossing detection.
    """
    open_abs = abs(open_line)
    close_abs = abs(close_line)
    raw_move = round(abs(close_abs - open_abs), 2)

    crossed = _crossed_numbers(open_abs, close_abs, SPREAD_KEY_NUMBERS)
    if not crossed:
        weight = 1.0
    else:
        # If multiple key numbers are crossed (rare, big move), sum their
        # weights rather than just taking the max — a move crossing both
        # 3 and 6 is more significant than crossing just one.
        weight = sum(SPREAD_KEY_NUMBERS[k] for k in crossed)

    adjusted_move = round(raw_move * weight, 3)

    return {
        "raw_move": raw_move,
        "key_numbers_crossed": crossed,
        "weight": round(weight, 2),
        "adjusted_move": adjusted_move,
        "note": (
            f"Crosses {', '.join(map(str, crossed))} — significance weighted {weight}x"
            if crossed else "No key number crossed — near base-rate significance"
        ),
    }


def total_crossing_value(open_total: float, close_total: float) -> dict:
    """Same concept as spread_crossing_value, using NFL totals key numbers."""
    raw_move = round(abs(close_total - open_total), 2)
    crossed = _crossed_numbers(open_total, close_total, TOTAL_KEY_NUMBERS)
    weight = sum(TOTAL_KEY_NUMBERS[k] for k in crossed) if crossed else 1.0
    adjusted_move = round(raw_move * weight, 3)

    return {
        "raw_move": raw_move,
        "key_numbers_crossed": crossed,
        "weight": round(weight, 2),
        "adjusted_move": adjusted_move,
        "note": (
            f"Crosses total {', '.join(map(str, crossed))} — weighted {weight}x"
            if crossed else "No total key number crossed"
        ),
    }
