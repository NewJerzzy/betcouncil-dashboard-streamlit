"""Exact-line historical hit assessment, independent of payout and edge tiers.

These are descriptive estimates, not a calibrated matchup forecast. All sample
sizes refer to actual dated observations, never a season-average fallback.
"""
import math
from datetime import date, datetime
from statistics import mean, pstdev


VERSION = "exact-line-history-v1"


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def wilson_interval(hits, total):
    """Two-sided 90% Wilson interval for a historical Bernoulli rate."""
    if not total:
        return None, None
    z = 1.6448536269514722
    rate = hits / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total**2)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def assess_hits(logs, line, stat_key, *, side="OVER", as_of=None,
                opportunity_key=None, max_age_days=45):
    """Assess strict clearing of the submitted line from at most 30 past games.

    Pushes count as non-hits for ranking, and are also reported separately.
    Future/same-day, undated, duplicate, DNP and invalid records are excluded.
    A date-only log cannot establish that today's game has already finished.
    """
    today = as_of or date.today()
    if isinstance(today, datetime):
        today = today.date()
    result = {
        "version": VERSION, "line": line, "side": side, "n": 0,
        "prob": None, "lower": None, "upper": None, "grade": "UNGRADED",
        "rank_score": None, "warnings": [], "calibrated": False,
    }
    threshold = _number(line)
    if threshold is None or side not in ("OVER", "UNDER"):
        result["warnings"] = ["Invalid line or side."]
        return result
    observations, seen = [], set()
    for row in logs or []:
        try:
            played = date.fromisoformat(str(row.get("date", ""))[:10])
        except (ValueError, TypeError, AttributeError):
            continue
        # Preserve doubleheaders when the source supplies game IDs.
        identity = str(row.get("game_id") or played)
        value = _number(row.get(stat_key))
        if played >= today or (today - played).days > 365 or identity in seen or value is None:
            continue
        opportunity = row.get(opportunity_key) if opportunity_key else None
        if isinstance(opportunity, str) and ":" in opportunity:
            try:
                minutes, seconds = opportunity.split(":")
                opportunity = float(minutes) + float(seconds) / 60
            except (ValueError, TypeError):
                opportunity = None
        opportunity = _number(opportunity)
        if opportunity is not None and opportunity <= 0 and opportunity_key in ("min", "TOI"):
            continue
        seen.add(identity)
        observations.append((played, value, opportunity))
    observations.sort(key=lambda item: item[0], reverse=True)
    observations = observations[:30]
    n = len(observations)
    result["n"] = n
    if not n:
        result["warnings"] = ["No usable dated game logs for this stat; no baseline substituted."]
        return result
    values = [item[1] for item in observations]
    wins = [value > threshold if side == "OVER" else value < threshold for value in values]
    hits = sum(wins)
    lower, upper = wilson_interval(hits, n)
    result.update({
        "hits": hits, "pushes": sum(value == threshold for value in values),
        "prob": (hits + 0.5) / (n + 1),  # Jeffreys-smoothed historical predictive rate
        "lower": lower, "upper": upper, "rate": hits / n,
        "last5": sum(wins[:5]) / min(5, n),
        "last10": sum(wins[:10]) / min(10, n),
        "average": mean(values), "std_dev": pstdev(values),
        "latest": observations[0][0].isoformat(),
        "oldest": observations[-1][0].isoformat(),
    })
    warnings = result["warnings"]
    if n < 20:
        warnings.append("Small sample: fewer than 20 games; provisional only.")
    if (today - observations[0][0]).days > max_age_days:
        warnings.append("Stale logs: latest game is outside the freshness window.")
    opportunities = [item[2] for item in observations if item[2] is not None]
    if len(opportunities) < n:
        warnings.append("Playing time/opportunity not verified for every game.")
    elif opportunities:
        avg_opportunity = mean(opportunities)
        cv = pstdev(opportunities) / avg_opportunity if avg_opportunity else 0
        result["opportunity_cv"] = cv
        if cv > 0.25:
            warnings.append("Unstable playing time/opportunity (variation above 25%).")
        # A stable full-window average can hide a recent role change.
        recent = [item[2] for item in observations[:5]]
        older = [item[2] for item in observations[5:]]
        if older and mean(older) and abs(mean(recent) / mean(older) - 1) > 0.20:
            warnings.append("Recent playing time/opportunity changed by more than 20%.")
    if n >= 10 and abs(result["last5"] - result["rate"]) > 0.25:
        warnings.append("Recent form differs substantially from the full sample.")
    if n < 8:
        result["grade"] = "INSUFFICIENT"
    elif warnings:
        result["grade"] = "PROVISIONAL"
    elif lower >= 0.60:
        result["grade"] = "STRONGER HISTORY"
    elif lower >= 0.50:
        result["grade"] = "SUPPORTED"
    else:
        result["grade"] = "PASS"
    if n >= 8 and not any("Stale" in warning for warning in warnings):
        result["rank_score"] = lower
    result["context_note"] = (
        "Not adjusted for today's injury, matchup or lineup. Verify these before choosing a pick."
    )
    return result


def rank_assessments(rows):
    """Usable evidence first, then conservative historical clearing rate."""
    order = {"STRONGER HISTORY": 4, "SUPPORTED": 3, "PASS": 2,
             "PROVISIONAL": 1, "INSUFFICIENT": 0, "UNGRADED": -1}
    return sorted(rows, key=lambda row: (
        order.get(row.get("hit_analysis", {}).get("grade"), -1),
        row.get("hit_analysis", {}).get("rank_score") or 0,
        row.get("hit_analysis", {}).get("n", 0),
    ), reverse=True)
