"""
derivative_validator.py — Derivative cross-validation (which side is wrong).

Extends bc_utils.detect_game_script_contradictions(), which already flags
WHEN a player prop's implied production contradicts a game/team total.
This module adds the missing piece: deciding WHICH market is more likely
mispriced, using data already computed elsewhere (consensus_engine's
n_books/consensus_prob — a liquidity/agreement proxy — and book_quality
counterparty scores).

Rule of thumb used (standard market-structure reasoning, not invented
numbers): game lines are the most liquid, most heavily bet, most
book-scrutinized market — they get sharp attention first. Player props are
priced by fewer, often automated, models and get less scrutiny. So when
they contradict:
  - If the prop consensus has FEW contributing books and/or wide book
    disagreement (per consensus_engine.flag_outliers), the prop total is
    the more likely mispriced side.
  - If the prop consensus has MANY contributing books in tight agreement,
    but is quoted mostly at low-counterparty-quality (retail) books, the
    game total (typically driven by sharp books) is trusted more.
  - If both hold up (tight prop consensus AND sharp-book contribution),
    flag as "GENUINE_DIVERGENCE" — a real, tradeable dislocation rather
    than a pricing error on one side.

Public API
----------
validate_derivative(prop_consensus, game_total, sport, prop_books=None) -> dict
    {contradiction, likely_mispriced, confidence, reasons}
"""
from book_quality import counterparty_quality

_TIGHT_AGREEMENT_BOOKS = 5   # consensus_engine treats 5+ books as trimmed-mean eligible


def validate_derivative(prop_consensus: dict, implied_game_total: float,
                         prop_implied_total: float, sport: str = "",
                         prop_books: list = None) -> dict:
    """
    prop_consensus:        output of consensus_engine.compute_consensus()
                            for the relevant prop group (has n_books,
                            consensus_prob, book_probs).
    implied_game_total:    the game/team total your model already computed
                            (e.g. from bc_utils.detect_game_script_contradictions'
                            game_total_map).
    prop_implied_total:    the total production the prop side implies
                            (e.g. sum of correlated prop lines).
    prop_books:            optional list of book names/keys the prop
                            consensus was built from, for counterparty
                            weighting.

    Returns {contradiction, likely_mispriced, confidence, reasons}
    where likely_mispriced is "PROP", "GAME_TOTAL", or "GENUINE_DIVERGENCE".
    """
    reasons = []
    if implied_game_total is None or prop_implied_total is None:
        return {"contradiction": False, "likely_mispriced": None, "confidence": 0.0, "reasons": ["missing inputs"]}

    deviation = prop_implied_total - implied_game_total
    deviation_pct = abs(deviation) / implied_game_total * 100 if implied_game_total else 0

    if deviation_pct < 5:
        return {
            "contradiction": False,
            "likely_mispriced": None,
            "confidence": 0.0,
            "reasons": [f"Deviation {deviation_pct:.1f}% within normal correlation noise — no real contradiction"],
        }

    n_books = (prop_consensus or {}).get("n_books", 0)
    book_probs = (prop_consensus or {}).get("book_probs", {})

    tight_agreement = False
    if book_probs and len(book_probs) >= 2:
        spread = max(book_probs.values()) - min(book_probs.values())
        tight_agreement = spread <= 0.04  # within 4 probability points across books

    avg_prop_quality = 0.45
    if prop_books:
        quals = [counterparty_quality(b) for b in prop_books]
        avg_prop_quality = sum(quals) / len(quals) if quals else 0.45

    has_enough_books = n_books >= _TIGHT_AGREEMENT_BOOKS
    sharp_backed = avg_prop_quality >= 0.65

    if not has_enough_books or not tight_agreement:
        likely_mispriced = "PROP"
        confidence = 0.7
        reasons.append(f"Prop consensus thin/disagreeing ({n_books} books, "
                        f"{'tight' if tight_agreement else 'wide'} agreement) — prop side more likely mispriced")
    elif has_enough_books and tight_agreement and not sharp_backed:
        likely_mispriced = "GAME_TOTAL"
        confidence = 0.55
        reasons.append(f"Prop consensus is deep ({n_books} books) and tightly agreed, but mostly retail books — "
                        "game total (sharp-book driven) may be the stale side")
    else:
        likely_mispriced = "GENUINE_DIVERGENCE"
        confidence = 0.5
        reasons.append("Prop consensus is deep, tight, AND sharp-book backed — this looks like a real "
                        "tradeable dislocation rather than a pricing error on either side")

    return {
        "contradiction": True,
        "deviation_pct": round(deviation_pct, 2),
        "likely_mispriced": likely_mispriced,
        "confidence": confidence,
        "reasons": reasons,
    }
