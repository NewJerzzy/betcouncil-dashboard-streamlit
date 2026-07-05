"""
book_quality.py — Graduated counterparty quality scoring.

Replaces the existing binary SHARP_BOOKS_SET / SHARP_BOOKS_PROP flags
(app.py) with a continuous 0-1 score. Pure logic on data you already have
(which books you already classify as sharp vs. soft) — no new data source.

Rationale for the tiers: books with low retail limits and fast line
adjustment (Pinnacle, Circa) take mostly informed/professional action, so
a line move there carries more signal. High-limit retail books (DK, FD,
BetMGM) skew recreational, so their prices are noisier and their moves
carry less signal. This mirrors the SHARP_BOOKS_SET / SHARP_BOOKS_PROP
distinctions already present in app.py — this module just makes the
weighting continuous instead of binary.

Public API
----------
counterparty_quality(book_label_or_key) -> float   (0.0-1.0)
weight_signal_by_counterparty(score, book) -> float
"""

# Keyed by the same short book keys used in app.py's EV_BOOK_LABELS, plus
# full display names for sources (Scanbet/Action Network) that report full
# names instead of short keys. Tiers are derived from the sharp/soft
# distinctions already encoded in app.py's SHARP_BOOKS_SET (pn, circa, espn)
# and SHARP_BOOKS_PROP (pinnacle, circa_sports, betonlineag).
COUNTERPARTY_QUALITY = {
    # Sharp / low-limit / professional-heavy books — highest signal value
    "pn": 0.95, "pinnacle": 0.95,
    "circa": 0.90, "circa_sports": 0.90,
    "b365": 0.85, "bet365": 0.85,
    "bol": 0.80, "betonlineag": 0.80, "betonline": 0.80,
    "espn": 0.75, "espn bet": 0.75,

    # Mid-tier — mixed recreational/sharp
    "br": 0.60, "betrivers": 0.60,
    "fn": 0.55, "fanatics": 0.55,
    "kambi": 0.55,

    # High-limit retail, recreational-heavy — lowest signal value per move
    "dk": 0.45, "draftkings": 0.45,
    "fd": 0.45, "fanduel": 0.45,
    "mgm": 0.40, "betmgm": 0.40,
    "cz": 0.40, "caesars": 0.40,
    "hr": 0.40, "hard rock": 0.40, "hr_oh": 0.40,
    "bv": 0.35, "bovada": 0.35,
    "re": 0.30, "rebet": 0.30,
    "fl": 0.25, "fliff": 0.25,

    # DFS-style pick'em products — pure recreational counterparty
    "nv": 0.20, "novig": 0.20,
    "prizepicks": 0.20,
    "underdog": 0.20,

    # Prediction markets — priced by aggregated public belief, not a single
    # book's risk desk; treated as informative but distinct from sportsbook
    # sharp/soft framing
    "kal": 0.70, "kalshi": 0.70,
    "poly": 0.70, "polymarket": 0.70,
}

_DEFAULT_QUALITY = 0.45  # unknown book: assume mid/retail rather than sharp


def counterparty_quality(book) -> float:
    """
    Return a 0-1 counterparty quality score for a book. Accepts either the
    short key ("pn") or full label ("Pinnacle") used elsewhere in the repo.
    Unknown books default to 0.45 (retail-assumed) rather than guessing high.
    """
    if not book:
        return _DEFAULT_QUALITY
    key = str(book).strip().lower()
    return COUNTERPARTY_QUALITY.get(key, _DEFAULT_QUALITY)


def weight_signal_by_counterparty(raw_score: float, book) -> float:
    """
    Scale a raw signal score (e.g. CLV score, RLM score) by the counterparty
    quality of the book it came from. A move at Pinnacle (0.95) counts far
    more than the same-size move at BetMGM (0.40).
    """
    return round(raw_score * counterparty_quality(book), 3)
