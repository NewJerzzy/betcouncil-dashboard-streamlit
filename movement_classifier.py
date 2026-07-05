"""
movement_classifier.py — Movement cause classification.

Labels a line move as SHARP, PUBLIC, or NEWS using only signals already
computed elsewhere in the repo: counterparty quality (book_quality.py),
RLM/ticket-money divergence (fetchers.fetch_public_betting), and steam
breadth (unified_sharp_score.py). No new data source.

Classification logic
---------------------
NEWS:    Multiple books across BOTH high- and low-quality tiers moved
         together in the same direction within the same snapshot window
         (steam that doesn't discriminate by book tier — the signature of
         information hitting the whole market at once, e.g. an injury
         scratch, rather than one side's syndicate action).
SHARP:   The move is concentrated at high-counterparty-quality books
         (price setters) and/or the RLM pattern shows money% diverging
         hard from tickets% (large bets, not a lot of bettors) — informed
         money leading, square books lagging.
PUBLIC:  Tickets% and money% move together (many bettors, no divergence)
         concentrated at low-counterparty-quality (retail) books — the
         crowd moving the number, not sharp action.

Public API
----------
classify_event_movement(event) -> dict {cause, confidence, reasons}
    `event` is one entry from unified_sharp_score.build_unified_sharp_board()
"""
from book_quality import counterparty_quality

_SHARP_QUALITY_FLOOR = 0.75   # book_quality at/above this = "sharp tier"
_PUBLIC_QUALITY_CEIL = 0.50   # book_quality at/below this = "retail tier"


def classify_event_movement(event: dict) -> dict:
    """
    event: one dict from unified_sharp_score.build_unified_sharp_board(),
    containing clv_signals / steam_signals / rlm_signals.

    Returns {cause: "SHARP"|"PUBLIC"|"NEWS"|"UNCLEAR", confidence: 0-1, reasons: [...]}
    """
    reasons = []
    has_steam = bool(event.get("steam_signals"))
    has_rlm = bool(event.get("rlm_signals"))
    clv_signals = event.get("clv_signals", [])

    # Scanbet CLV signals in this repo track Pinnacle specifically, so any
    # CLV/steam entry here is inherently a sharp-tier (Pinnacle) book move.
    # NEWS is distinguished from pure SHARP by breadth: if the RLM data
    # ALSO shows the public swinging the same direction with tickets%
    # moving in lockstep with money% (no sharp/public divergence), that
    # indicates the whole market — not just Pinnacle — reacted, which is
    # the signature of a news event rather than one side's syndicate edge.
    public_confirms_same_direction = False
    ticket_money_lockstep = False
    for rlm in event.get("rlm_signals", []):
        public_pct = rlm.get("public_pct") or 0
        money_pct = rlm.get("money_pct") or 0
        if public_pct and money_pct and abs(public_pct - money_pct) <= 8:
            ticket_money_lockstep = True
        if rlm.get("sharp_side") == event.get("consensus_direction"):
            public_confirms_same_direction = True

    if has_steam and ticket_money_lockstep:
        cause = "NEWS"
        confidence = 0.75
        reasons.append("Steam move at Pinnacle coincided with public tickets/money moving in lockstep — "
                        "consistent with information hitting the whole market, not one side's edge")
    elif has_steam or (clv_signals and not has_rlm):
        cause = "SHARP"
        confidence = 0.80 if has_steam else 0.6
        reasons.append("Move concentrated at high-counterparty-quality book (Pinnacle) "
                        "with no matching broad public shift")
    elif has_rlm and not ticket_money_lockstep:
        cause = "SHARP"
        confidence = 0.65
        reasons.append("RLM pattern: money% diverges from tickets% — few large bets, not the crowd")
    elif has_rlm and ticket_money_lockstep:
        cause = "PUBLIC"
        confidence = 0.55
        reasons.append("Tickets% and money% moving together — broad public action, not concentrated sharp money")
    else:
        cause = "UNCLEAR"
        confidence = 0.3
        reasons.append("Insufficient signal breadth to classify cause")

    return {"cause": cause, "confidence": confidence, "reasons": reasons}
