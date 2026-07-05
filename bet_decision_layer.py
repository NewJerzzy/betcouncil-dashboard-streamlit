"""
bet_decision_layer.py — Pure decision logic on top of existing signals.
No new data sources. Covers:

  1. Bet timing recommendation (bet now vs. wait)
  2. Book rotation order (bet soft books first, sharp books last)
  3. Signal aging/decay (a 45-min-old steam signal isn't a fresh one)
  4. Signal-type Kelly multiplier (arb > combined signals > single signal)

Public API
----------
recommend_timing(has_steam, has_rlm, has_arb) -> dict {action, reason}
book_rotation_order(books) -> list[str], softest-first
decay_signal_confidence(signal_type, minutes_elapsed) -> float (0-1)
signal_type_multiplier(signal_types: list[str]) -> float
"""
import math

from book_quality import counterparty_quality

# ── 1. Timing ─────────────────────────────────────────────────────────────

def recommend_timing(has_steam: bool, has_rlm: bool, has_arb: bool) -> dict:
    """
    Decision rule on top of signals you already compute:
      - Arb exists          -> BET NOW (won't last)
      - Steam against you   -> BET NOW (line is actively moving away)
      - RLM (sharp on your side, public on other) -> WAIT (public tends to
        push the line further your way as more public money lands)
      - Nothing detected    -> WAIT until closer to game (lines often
        soften as the game approaches and public money arrives)
    """
    if has_arb:
        return {"action": "BET_NOW", "reason": "Arbitrage — window closes as soon as either book adjusts"}
    if has_steam:
        return {"action": "BET_NOW", "reason": "Steam detected — price is actively moving away from you"}
    if has_rlm:
        return {"action": "WAIT", "reason": "RLM detected — public money typically pushes the line further your way"}
    return {"action": "WAIT", "reason": "No movement signal — lines often soften closer to game time"}


# ── 2. Book rotation ──────────────────────────────────────────────────────

def book_rotation_order(books: list) -> list:
    """
    Order books from softest (bet first — limits slowest) to sharpest
    (bet last — burns the account, and signals the market). Uses the same
    counterparty_quality score already built: lower quality = softer book.
    """
    return sorted(books, key=lambda b: counterparty_quality(b))


# ── 3. Signal aging / decay ──────────────────────────────────────────────

# Decay rate per signal type — how fast a signal's confidence should fade.
# Arb windows close in seconds/minutes (fast decay); RLM reflects a
# standing market condition and persists longer (slow decay).
_DECAY_LAMBDA = {
    "ARB": 0.50,
    "STEAM": 0.10,
    "CLV": 0.01,
    "RLM": 0.005,
}
_DEFAULT_LAMBDA = 0.05


def decay_signal_confidence(signal_type: str, minutes_elapsed: float) -> float:
    """
    confidence(t) = e^(-lambda * t). Returns 0-1. A signal_type not in the
    known map uses a moderate default decay rather than assuming it never
    expires.
    """
    lam = _DECAY_LAMBDA.get(str(signal_type).upper(), _DEFAULT_LAMBDA)
    minutes_elapsed = max(minutes_elapsed, 0)
    return round(math.exp(-lam * minutes_elapsed), 4)


# ── 4. Signal-type Kelly multiplier ──────────────────────────────────────

def signal_type_multiplier(signal_types: list) -> float:
    """
    Scale the base Kelly fraction by how many independent signal types
    align, with special-cases for arbitrage (guaranteed profit — bet max)
    and contradiction (signals disagree — shrink stake for uncertainty).
    signal_types: list of strings, e.g. ["CLV", "STEAM", "RLM"] or
    ["CLV", "RLM_CONTRA"] to flag a contradiction.
    """
    types = {str(t).upper() for t in signal_types}
    if "ARB" in types:
        return 3.0
    if any(t.endswith("_CONTRA") for t in types):
        return 0.5
    n = len(types)
    if n >= 3:
        return 2.0
    if n == 2:
        return 1.5
    if n == 1:
        return 1.0
    return 0.0
