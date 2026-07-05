"""
unified_sharp_score.py — Combines existing CLV/steam (Scanbet) and RLM/sharp
(Action Network) signals into one per-game score for the board.

This does NOT reimplement odds math. It reuses:
  - fetch_scanbet_drops_from_gist()  -> real opener_prob/current_prob/drop_pct/is_steam
  - fetch_public_betting(sport)      -> real tickets/money %, sharp_signals, rlm_signals
  - team_canon.canon_game_key()      -> matches games across the two sources

Public API
----------
build_unified_sharp_board(sport) -> list[dict], sorted by score desc
    Each dict:
        {
            game_key, game_label, total_score,
            clv_signals: [...], steam_signals: [...], rlm_signals: [...],
            consensus_direction: str or None,
            tier: "STRONG" | "MODERATE" | "WEAK",
        }
"""
from collections import defaultdict

from fetchers import fetch_scanbet_drops_from_gist, fetch_public_betting
from team_canon import canon_game_key
from book_quality import counterparty_quality, weight_signal_by_counterparty
from bayesian_line_updater import bayesian_posterior
from movement_classifier import classify_event_movement
from bet_decision_layer import recommend_timing, signal_type_multiplier


def _tier(score: float) -> str:
    if score >= 8:
        return "STRONG"
    if score >= 5:
        return "MODERATE"
    return "WEAK"


def build_unified_sharp_board(sport: str) -> list:
    """
    Aggregate Scanbet (CLV/steam) + Action Network (RLM/sharp) signals into
    one score per game. Returns list sorted by total_score descending.
    """
    events = defaultdict(lambda: {
        "game_label": "",
        "clv_signals": [],
        "steam_signals": [],
        "rlm_signals": [],
        "total_score": 0.0,
        "direction_votes": defaultdict(float),
    })

    # ── Scanbet: CLV + steam (already correct implied-probability math) ──
    try:
        scanbet_rows = fetch_scanbet_drops_from_gist()
    except Exception:
        scanbet_rows = []

    for row in scanbet_rows:
        if row.get("sport", "").upper() != sport.upper():
            continue
        gk = canon_game_key(row["away"], row["home"], sport)
        ev = events[gk]
        ev["game_label"] = row["game"]

        drop_pct = row.get("drop_pct", 0.0)
        raw_score = min(abs(drop_pct) * 100, 10)
        # Scanbet tracks Pinnacle's own line — weight the signal by
        # Pinnacle's counterparty quality (high-trust source).
        sig_score = weight_signal_by_counterparty(raw_score, "pinnacle")
        direction = row.get("selection", "")

        bayes = {}
        if row.get("opener_prob") is not None and row.get("current_prob") is not None:
            bayes = bayesian_posterior(row["opener_prob"], row["current_prob"], "pinnacle")

        clv_entry = {
            "type": "CLV",
            "market": row.get("market"),
            "selection": row.get("selection"),
            "opener_odds": row.get("opener_odds"),
            "current_odds": row.get("current_odds"),
            "drop_pct": round(drop_pct * 100, 2),
            "n_snapshots": row.get("n_snapshots"),
            "score": round(sig_score, 2),
            "bayesian_posterior": bayes.get("posterior"),
            "bayesian_shift": bayes.get("shift"),
        }
        ev["clv_signals"].append(clv_entry)
        ev["total_score"] += sig_score
        if direction:
            ev["direction_votes"][direction] += sig_score

        if row.get("is_steam") and abs(drop_pct) >= 0.03:
            steam_entry = dict(clv_entry)
            steam_entry["type"] = "STEAM"
            ev["steam_signals"].append(steam_entry)
            ev["total_score"] += min(sig_score, 3)  # steam adds a bonus, capped

    # ── Action Network: RLM + sharp/public divergence (already correct) ──
    try:
        pb = fetch_public_betting(sport)
    except Exception:
        pb = {}

    for game_key, data in pb.items():
        teams = data.get("teams", [])
        if len(teams) < 2:
            continue
        gk = canon_game_key(teams[1], teams[0], sport)
        ev = events[gk]
        if not ev["game_label"]:
            ev["game_label"] = f"{teams[1]} @ {teams[0]}"

        for rlm in data.get("rlm_signals", []):
            strength = rlm.get("strength", 1)
            raw_score = min(strength * 2.5, 10)
            # RLM comes from Action Network's aggregated public-book money%,
            # a mixed retail/sharp pool rather than a single sharp book —
            # weight at a fixed mid-tier quality rather than assuming full trust.
            sig_score = weight_signal_by_counterparty(raw_score, "espn")
            entry = {
                "type": "RLM",
                "market": rlm.get("type"),
                "public_side": rlm.get("public_side"),
                "public_pct": rlm.get("public_pct"),
                "sharp_side": rlm.get("sharp_side"),
                "money_pct": rlm.get("money_pct"),
                "score": round(sig_score, 2),
            }
            ev["rlm_signals"].append(entry)
            ev["total_score"] += sig_score
            if rlm.get("sharp_side"):
                ev["direction_votes"][rlm["sharp_side"]] += sig_score

    # ── Finalize ──
    board = []
    for gk, ev in events.items():
        if not ev["clv_signals"] and not ev["rlm_signals"]:
            continue
        consensus_direction = None
        if ev["direction_votes"]:
            consensus_direction = max(ev["direction_votes"].items(), key=lambda kv: kv[1])[0]
        entry = {
            "game_key": gk,
            "game_label": ev["game_label"],
            "total_score": round(ev["total_score"], 2),
            "clv_signals": ev["clv_signals"],
            "steam_signals": ev["steam_signals"],
            "rlm_signals": ev["rlm_signals"],
            "consensus_direction": consensus_direction,
            "tier": _tier(ev["total_score"]),
        }
        entry["movement_cause"] = classify_event_movement(entry)

        signal_types = []
        if ev["clv_signals"]:
            signal_types.append("CLV")
        if ev["steam_signals"]:
            signal_types.append("STEAM")
        if ev["rlm_signals"]:
            signal_types.append("RLM")
        entry["timing"] = recommend_timing(
            has_steam=bool(ev["steam_signals"]),
            has_rlm=bool(ev["rlm_signals"]),
            has_arb=False,  # arb is scored separately by arbitrage_detector.py
        )
        entry["kelly_multiplier"] = signal_type_multiplier(signal_types)

        board.append(entry)

    board.sort(key=lambda x: x["total_score"], reverse=True)
    return board
