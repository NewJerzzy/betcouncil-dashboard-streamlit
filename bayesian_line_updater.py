"""
bayesian_line_updater.py — Bayesian posterior update on line movement.

Pure logic on data you already harvest (opener/current implied probability
from Scanbet, book counterparty quality). No new data source required.

Concept: a line move is evidence. How much you should update your belief
depends on (a) how big the move was, and (b) how much you trust the book
that moved (counterparty quality). This uses a Beta-Binomial-style update
rather than an invented ad hoc formula — a standard, defensible Bayesian
treatment of "probability of an event" updating with weighted evidence.

Public API
----------
bayesian_posterior(prior_prob, moved_prob, book, pseudo_n=20) -> dict
    {prior, posterior, shift, confidence_weight}

apply_bayesian_clv(clv_row, book, pseudo_n=20) -> dict
    Convenience wrapper for rows shaped like fetch_scanbet_drops_from_gist()
    output (opener_prob/current_prob) plus the book whose price you're
    evaluating against Pinnacle's move.
"""
from book_quality import counterparty_quality


def bayesian_posterior(prior_prob: float, moved_prob: float, book: str,
                        pseudo_n: int = 20) -> dict:
    """
    Update a prior probability using a Beta-Binomial conjugate update,
    where the "new evidence" is the moved (current) probability, and the
    weight given to that evidence scales with the counterparty quality of
    the book that moved (a Pinnacle move is stronger evidence than a
    BetMGM move of the same size).

    prior_prob:  probability implied by the opening line (0-1)
    moved_prob:  probability implied by the current/closing line (0-1)
    book:        the book whose move is being treated as evidence
    pseudo_n:    strength of the prior in "pseudo-observations" — higher
                 pseudo_n means the prior is stickier and moves less per
                 unit of evidence. 20 is a moderate default.

    Returns dict with prior, posterior, shift (posterior - prior), and
    confidence_weight (the counterparty-scaled evidence weight actually
    used, 0-1).
    """
    prior_prob = max(min(prior_prob, 0.999), 0.001)
    moved_prob = max(min(moved_prob, 0.999), 0.001)

    quality = counterparty_quality(book)  # 0-1, higher = more trusted

    # Represent the prior as pseudo-counts (Beta(a, b)) and the new
    # evidence as an additional pseudo_n observations, scaled down by how
    # much we trust the source. A low-quality book contributes weak
    # evidence and barely moves the posterior; a high-quality book (e.g.
    # Pinnacle) contributes close to full weight.
    evidence_n = pseudo_n * quality

    a_prior = prior_prob * pseudo_n
    b_prior = (1 - prior_prob) * pseudo_n

    a_evidence = moved_prob * evidence_n
    b_evidence = (1 - moved_prob) * evidence_n

    a_post = a_prior + a_evidence
    b_post = b_prior + b_evidence

    posterior = a_post / (a_post + b_post)

    return {
        "prior": round(prior_prob, 4),
        "posterior": round(posterior, 4),
        "shift": round(posterior - prior_prob, 4),
        "confidence_weight": round(quality, 3),
    }


def apply_bayesian_clv(clv_row: dict, evidence_book: str, pseudo_n: int = 20) -> dict:
    """
    Convenience wrapper for CLV rows shaped like the output of
    fetch_scanbet_drops_from_gist() in fetchers.py:
        {opener_prob, current_prob, ...}

    Treats the opener as the prior and the current line as new evidence
    from `evidence_book` (e.g. the book you're deciding whether to bet).
    Returns the same dict as bayesian_posterior(), plus the original
    game/market/selection context for display.
    """
    prior = clv_row.get("opener_prob")
    moved = clv_row.get("current_prob")
    if prior is None or moved is None:
        return {}

    result = bayesian_posterior(prior, moved, evidence_book, pseudo_n)
    result.update({
        "game": clv_row.get("game"),
        "market": clv_row.get("market"),
        "selection": clv_row.get("selection"),
        "n_snapshots": clv_row.get("n_snapshots"),
    })
    return result
