"""
movement_classifier.py — classifies the likely cause of a line move based
on which signal types fired together for an event.

Built to satisfy unified_sharp_score.py's import (classify_event_movement),
which was missing entirely.
"""

def classify_event_movement(entry: dict) -> dict:
    """
    entry: the built event dict from unified_sharp_score.py, with
    clv_signals / steam_signals / rlm_signals / consensus_direction keys.

    Returns {"cause": str, "confidence": float 0-1}.
    """
    has_clv = bool(entry.get("clv_signals"))
    has_steam = bool(entry.get("steam_signals"))
    has_rlm = bool(entry.get("rlm_signals"))
    has_direction = bool(entry.get("consensus_direction"))

    if has_steam and has_rlm:
        # Multiple sharp books moved fast AND public/sharp money are
        # diverging in the same direction -- the strongest combined read.
        return {"cause": "CONFIRMED_SHARP_ACTION", "confidence": 0.85}
    if has_steam:
        return {"cause": "STEAM_MOVE", "confidence": 0.7}
    if has_rlm and has_direction:
        return {"cause": "REVERSE_LINE_MOVEMENT", "confidence": 0.65}
    if has_rlm:
        return {"cause": "PUBLIC_SHARP_DIVERGENCE", "confidence": 0.5}
    if has_clv:
        # Only an isolated sharp-book reprice (e.g. Pinnacle alone via
        # Scanbet), no confirming steam or public-money signal.
        return {"cause": "ISOLATED_BOOK_REPRICE", "confidence": 0.4}
    return {"cause": "UNCLEAR", "confidence": 0.0}
