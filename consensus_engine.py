"""
consensus_engine.py — Cross-book prop consensus price and outlier detection.

Public API
----------
compute_consensus(prop_group)              -> dict
flag_outliers(prop_group, consensus)       -> list[dict]
get_cross_book_signals(sport, book_data)   -> dict  (session_state-ready lookup)
"""
import logging
import re
from typing import Optional

_logger = logging.getLogger("betcouncil.consensus_engine")

try:
    from config import LINE_DEVIATION_THRESHOLD_PCT, PROP_CROSS_BOOK_MIN_BOOKS
except ImportError:
    LINE_DEVIATION_THRESHOLD_PCT = 5.0
    PROP_CROSS_BOOK_MIN_BOOKS    = 2

from prop_normalizer import match_props_across_books, normalize_player_name, normalize_stat_name

try:
    from book_quality import counterparty_quality
except ImportError:
    def counterparty_quality(book_name):
        return {"book": book_name, "role": "market", "weight": 1.0}


# ── Odds helpers ──────────────────────────────────────────────────────────────

def american_to_implied_prob(odds) -> Optional[float]:
    """
    Convert American odds (int, float, or string like "-110" / "+120") to
    implied probability.  Returns None for non-standard formats (e.g. "3x",
    "N/A", None).
    """
    if odds is None:
        return None
    s = str(odds).strip()
    # Reject DFS multiplier format ("3x", "4.5x") and non-numeric strings
    if re.search(r"[a-zA-Z]", s):
        return None
    s = s.replace("+", "")
    try:
        o = float(s)
    except ValueError:
        return None
    if o == 0:
        return None
    if o > 0:
        return round(100.0 / (o + 100.0), 6)
    else:  # negative
        return round(abs(o) / (abs(o) + 100.0), 6)


def implied_prob_to_american(prob: float) -> int:
    """Convert implied probability to American odds (rounded to integer)."""
    if prob <= 0 or prob >= 1:
        return -110
    if prob >= 0.5:
        return -round(prob / (1 - prob) * 100)
    else:
        return round((1 - prob) / prob * 100)


# ── Core consensus computation ────────────────────────────────────────────────

def compute_consensus(prop_group: dict) -> dict:
    """
    Compute the consensus over-probability and fair odds for a grouped prop.

    Algorithm:
      • Collect the over implied probability from each book (skip non-numeric odds).
      • If ≥ 5 books: trimmed mean (drop highest and lowest).
      • If 2-4 books: simple mean.
      • If < PROP_CROSS_BOOK_MIN_BOOKS valid data points: return empty.

    Returns
    -------
    dict with keys:
      consensus_prob      float  — fair probability that the OVER hits
      consensus_fair_odds int    — American odds equivalent
      n_books             int    — number of books contributing
      book_probs          dict   — {book: implied_prob}
    """
    books = prop_group.get("books", {})
    book_probs: dict[str, float] = {}
    for book, bdata in books.items():
        over_p  = american_to_implied_prob(bdata.get("over_odds"))
        under_p = american_to_implied_prob(bdata.get("under_odds"))
        if over_p is not None and under_p is not None:
            # Vig-remove: normalize so over + under sum to 1
            total = over_p + under_p
            if total > 0:
                book_probs[book] = round(over_p / total, 6)
        elif over_p is not None:
            book_probs[book] = over_p

    n = len(book_probs)
    if n < PROP_CROSS_BOOK_MIN_BOOKS:
        return {}

    # Weight each book's probability by its counterparty quality (sharp
    # books like Pinnacle count ~3x a soft book like MyBookie) instead of
    # treating every book identically -- same weighting already used for
    # game-line consensus, previously missing here for props.
    weighted = sorted(
        ((prob, counterparty_quality(book)["weight"]) for book, prob in book_probs.items()),
        key=lambda pw: pw[0],
    )
    if n >= 5:
        trimmed = weighted[1:-1]
    else:
        trimmed = weighted
    total_weight = sum(w for _, w in trimmed)
    if total_weight > 0:
        consensus_prob = round(sum(p * w for p, w in trimmed) / total_weight, 6)
    else:
        consensus_prob = round(sum(p for p, _ in trimmed) / len(trimmed), 6)
    return {
        "consensus_prob":      consensus_prob,
        "consensus_fair_odds": implied_prob_to_american(consensus_prob),
        "n_books":             n,
        "book_probs":          book_probs,
    }


# ── Outlier detection ─────────────────────────────────────────────────────────

def flag_outliers(
    prop_group: dict,
    consensus: dict,
    threshold_pct: float = LINE_DEVIATION_THRESHOLD_PCT,
) -> list[dict]:
    """
    Identify books whose implied probability deviates from consensus by more
    than `threshold_pct` percentage points.

    Returns list of dicts:
        {book, book_prob, consensus_prob, deviation_pct, direction}
    """
    if not consensus:
        return []
    c_prob = consensus.get("consensus_prob")
    if c_prob is None:
        return []
    book_probs = consensus.get("book_probs", {})
    outliers = []
    for book, bp in book_probs.items():
        dev_pct = round((bp - c_prob) * 100, 2)
        if abs(dev_pct) >= threshold_pct:
            outliers.append({
                "book":           book,
                "book_prob":      bp,
                "consensus_prob": c_prob,
                "deviation_pct":  dev_pct,
                "direction":      "OVER_FRIENDLY" if dev_pct > 0 else "UNDER_FRIENDLY",
            })
    outliers.sort(key=lambda x: abs(x["deviation_pct"]), reverse=True)
    return outliers


# ── Full pipeline: book data → session_state lookup ───────────────────────────

def get_cross_book_signals(
    sport: str,
    book_data: dict[str, list[dict]],
) -> dict[tuple[str, str], dict]:
    """
    Full LINE_DEVIATION pipeline:
      1. match_props_across_books  → grouped props
      2. compute_consensus         → fair probability per group
      3. flag_outliers             → deviation signals per book
      4. Return session_state-ready lookup keyed by (player_norm, stat_canon)

    The lookup dict is stored in st.session_state["line_deviation_lookup"] by
    the caller (app.py) so the main prop pipeline can read it per-prop.

    Each value is:
        {
            signal:         "LINE_DEVIATION",
            consensus_prob: float,
            n_books:        int,
            deviation_pct:  float,       # deviation of the current display book
            outliers:       list[dict],
        }
    """
    if not book_data:
        return {}

    grouped = match_props_across_books(book_data, sport)
    lookup: dict[tuple[str, str], dict] = {}

    for prop_group in grouped:
        consensus = compute_consensus(prop_group)
        if not consensus:
            continue
        outliers = flag_outliers(prop_group, consensus)
        # The largest-deviation outlier drives the signal strength shown in dashboard
        max_dev = max((abs(o["deviation_pct"]) for o in outliers), default=0.0)
        signal_entry = {
            "signal":         "LINE_DEVIATION",
            "consensus_prob": consensus["consensus_prob"],
            "n_books":        consensus["n_books"],
            "deviation_pct":  max_dev,
            "book_probs":     consensus["book_probs"],
            "outliers":       outliers,
        }
        player_norm = prop_group["player"]
        stat_canon  = prop_group["stat"]
        key = (player_norm, stat_canon)
        # If multiple lines exist for same player+stat, keep the one with the
        # most contributing books (richer consensus = more confidence)
        if key not in lookup or consensus["n_books"] > lookup[key].get("n_books", 0):
            lookup[key] = signal_entry

    _logger.debug(
        "[LINE_DEVIATION] %s: %d prop groups matched, %d lookup entries",
        sport, len(grouped), len(lookup),
    )
    return lookup
