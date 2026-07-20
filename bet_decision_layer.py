"""
bet_decision_layer.py — timing guidance and signal-count Kelly multiplier.

Built to satisfy unified_sharp_score.py's imports (recommend_timing,
signal_type_multiplier), which were missing entirely.
"""

def recommend_timing(has_steam: bool = False, has_rlm: bool = False, has_arb: bool = False) -> dict:
    """Returns {"action": str, "reason": str} -- when to act on this signal."""
    if has_steam:
        return {
            "action": "BET NOW",
            "reason": "Steam moves are fast — multiple books typically adjust/limit within minutes",
        }
    if has_arb:
        return {
            "action": "BET NOW",
            "reason": "Arbitrage windows close quickly as books reprice",
        }
    if has_rlm:
        return {
            "action": "MONITOR",
            "reason": "RLM can build over hours — no immediate urgency, but worth tracking",
        }
    return {"action": "WAIT", "reason": "No strong timing signal yet"}


def signal_type_multiplier(signal_types: list) -> float:
    """
    More independent signal TYPES confirming the same direction is a
    qualitatively stronger read than one signal alone (the same idea
    Replit's audit flagged as missing for correlated market moves) --
    scales the Kelly multiplier up with signal-type count rather than
    treating every combination as equally strong.
    """
    n = len(set(signal_types or []))
    if n >= 3:
        return 1.3
    if n == 2:
        return 1.15
    if n == 1:
        return 1.0
    return 0.8
