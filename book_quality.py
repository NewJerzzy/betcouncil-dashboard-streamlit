"""
book_quality.py — counterparty (sportsbook) trust/quality weighting.

Built to satisfy unified_sharp_score.py's imports (counterparty_quality,
weight_signal_by_counterparty), which were missing entirely. Reuses the
existing classify_book_role() from bc_utils.py and the same weight values
already established (and live) in build_game_line_consensus, rather than
inventing a new, unverified weighting scheme.
"""
from bc_utils import classify_book_role

# Same weight tiers already used in build_game_line_consensus (bc_utils.py)
# for game-line consensus -- kept identical so "sharp books count more"
# means the same thing everywhere in the app, not a second, divergent scale.
_ROLE_WEIGHTS = {
    "sharp":  3.0,   # Pinnacle, Circa, Bookmaker, BetCris, BetOnline, Heritage
    "market": 1.0,   # Standard regulated US books that follow the market
    "square": 0.6,   # Recreational-skewing retail books
    "dfs":    0.8,   # PrizePicks/Underdog/Novig -- flat-payout, different pricing model
}


def counterparty_quality(book_name: str) -> dict:
    """Returns the trust classification and numeric weight for a book."""
    role = classify_book_role(book_name)
    return {
        "book": book_name,
        "role": role,
        "weight": _ROLE_WEIGHTS.get(role, 1.0),
    }


def weight_signal_by_counterparty(raw_score: float, book_name: str) -> float:
    """Scales a raw signal score by the originating book's trust weight."""
    try:
        raw = float(raw_score)
    except (TypeError, ValueError):
        return 0.0
    weight = counterparty_quality(book_name)["weight"]
    return raw * weight
