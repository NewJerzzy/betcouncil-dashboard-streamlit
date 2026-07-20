"""
bayesian_line_updater.py — Bayesian update of a game's win/cover probability
as new market information (line movement) arrives.

Built to satisfy unified_sharp_score.py's import (bayesian_posterior), which
was missing entirely. Treats the opening probability as the prior and the
current probability as new evidence; the update weight (how much the
current price is trusted to move the posterior) scales with the reporting
book's counterparty quality via book_quality.py, so a Pinnacle move shifts
the posterior more than a soft-book move of the same size.
"""
import math
from book_quality import counterparty_quality


def _prob_to_logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _logit_to_prob(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def bayesian_posterior(opener_prob: float, current_prob: float, book_name: str) -> dict:
    """
    Blends the opening probability (prior) with the current probability
    (new evidence) in log-odds space, weighted by the reporting book's
    trust level. A sharp book's current price pulls the posterior further
    toward itself than a soft book's price would for the same raw move.

    Returns {prior, observation, posterior, shift, weight}.
    """
    try:
        prior_p = float(opener_prob)
        obs_p = float(current_prob)
    except (TypeError, ValueError):
        return {"prior": None, "observation": None, "posterior": None, "shift": 0.0, "weight": 0.0}

    weight = counterparty_quality(book_name)["weight"]
    # Normalize weight to a 0-1 blend factor (sharp books ~3.0 -> trust the
    # new observation heavily; soft books ~0.6 -> barely move the prior).
    blend = min(weight / (weight + 1.0), 0.85)

    prior_logit = _prob_to_logit(prior_p)
    obs_logit = _prob_to_logit(obs_p)
    posterior_logit = prior_logit + blend * (obs_logit - prior_logit)
    posterior_p = round(_logit_to_prob(posterior_logit), 4)

    return {
        "prior": round(prior_p, 4),
        "observation": round(obs_p, 4),
        "posterior": posterior_p,
        "shift": round(posterior_p - prior_p, 4),
        "weight": weight,
    }
