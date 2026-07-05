"""
soccer_draw_bias.py — Three-way market draw-bias detector.

Uses draw odds already harvested (fetchers.py draw_odds/drawOdds field)
plus verified real league draw-rate baselines (FootyStats 2025/26,
Paraball Notes 5-yr averages) — not DeepSeek's unsourced figures.

LEAGUE_DRAW_RATES: approximate, sourced, not exact:
  Bundesliga ~25% (2025/26 season, FootyStats)
  EPL ~22.8% (5-yr avg, lowest of the big five)
  Serie A, La Liga: historically higher than EPL/Bundesliga (~25-27%)
Treated as approximate priors, not literal ground truth.

Public API
----------
detect_draw_value(draw_odds_american, league_key) -> dict
"""
from consensus_engine import american_to_implied_prob

LEAGUE_DRAW_RATES = {
    "eng.1": 0.228,   # EPL — lowest of the big five (verified, 5yr avg)
    "ger.1": 0.250,   # Bundesliga (verified, 2025/26 season)
    "ita.1": 0.265,   # Serie A — approximate, historically higher
    "esp.1": 0.255,   # La Liga — approximate
    "fra.1": 0.240,   # Ligue 1 — approximate
    "usa.1": 0.230,   # MLS — approximate, lower (playoff-oriented scoring)
}
_DEFAULT_DRAW_RATE = 0.25


def detect_draw_value(draw_odds_american, league_key: str, vig_estimate: float = 0.06) -> dict:
    """
    Compare the market-implied draw probability (de-vigged with a rough
    vig estimate since we don't always have all three prices) against the
    league's historical draw rate. Flags undervalued draws — a real,
    structural bias since public bettors avoid draws and books shade
    accordingly, per multiple sources cited above.
    """
    implied = american_to_implied_prob(draw_odds_american)
    if implied is None:
        return {}

    # Rough de-vig: subtract an estimated share of the vig from the raw
    # implied probability (a full de-vig needs all three prices, which
    # isn't always available — this is a conservative approximation).
    devigged = max(implied - (vig_estimate / 3), 0.01)

    baseline = LEAGUE_DRAW_RATES.get(league_key, _DEFAULT_DRAW_RATE)
    edge = baseline - devigged

    return {
        "market_implied_draw_prob": round(implied, 4),
        "devigged_draw_prob": round(devigged, 4),
        "league_baseline_draw_rate": baseline,
        "edge": round(edge, 4),
        "undervalued": edge > 0.02,  # market draw price is 2pts+ below historical baseline
        "note": (
            f"Draw priced at {devigged*100:.1f}% vs league baseline {baseline*100:.1f}% "
            f"— {'undervalued, consider draw' if edge > 0.02 else 'in line with baseline'}"
        ),
    }
