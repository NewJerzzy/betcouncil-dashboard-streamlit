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
from team_canon import canon_game_key, canon
from book_quality import counterparty_quality, weight_signal_by_counterparty
from bayesian_line_updater import bayesian_posterior
from bc_utils import score_rlm

try:
    from nfl_key_numbers import spread_crossing_value, total_crossing_value
except ImportError:
    spread_crossing_value = None
    total_crossing_value = None

try:
    from soccer_draw_bias import detect_draw_value
except ImportError:
    detect_draw_value = None

try:
    from fangraphs_scrapers import team_starter_bullpen_gap, fetch_team_era_split
except ImportError:
    team_starter_bullpen_gap = None
    fetch_team_era_split = None
from movement_classifier import classify_event_movement
from bet_decision_layer import recommend_timing, signal_type_multiplier


def _tier(score: float) -> str:
    if score >= 8:
        return "STRONG"
    if score >= 5:
        return "MODERATE"
    return "WEAK"


def _market_bucket(raw_market) -> str:
    """Normalize varied raw market-name strings (SpreadValue, TotalValue,
    moneyline, ML, etc.) into a canonical spread/total/moneyline bucket, so
    signals from different sources can be checked for genuine multi-market
    agreement rather than just summed as if they were independent."""
    m = str(raw_market or "").lower()
    if "spread" in m:
        return "spread"
    if "total" in m or m in ("over", "under", "o/u"):
        return "total"
    if "moneyline" in m or m in ("ml", "h2h"):
        return "moneyline"
    return "other"


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
        "market_direction_votes": defaultdict(lambda: defaultdict(float)),
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
            ev["market_direction_votes"][_market_bucket(row.get("market"))][direction] += sig_score

        if row.get("is_steam") and abs(drop_pct) >= 0.03:
            steam_entry = dict(clv_entry)
            steam_entry["type"] = "STEAM"
            ev["steam_signals"].append(steam_entry)
            ev["total_score"] += min(sig_score, 3)  # steam adds a bonus, capped

    # ── NFL key-number-weighted spread/total line moves (verified frequencies) ──
    if sport.upper() == "NFL" and spread_crossing_value is not None:
        for row in scanbet_rows:
            if row.get("sport", "").upper() != "NFL":
                continue
            if row.get("market") not in ("SpreadValue", "TotalValue"):
                continue
            gk = canon_game_key(row["away"], row["home"], sport)
            ev = events[gk]
            if not ev["game_label"]:
                ev["game_label"] = row["game"]

            try:
                ov, cv = float(row["opener_value"]), float(row["current_value"])
            except (TypeError, ValueError, KeyError):
                continue

            if row["market"] == "SpreadValue":
                kn = spread_crossing_value(ov, cv)
            else:
                kn = total_crossing_value(ov, cv)

            if not kn["key_numbers_crossed"]:
                continue  # only surface moves that actually cross a key number

            kn_score = min(kn["adjusted_move"] * 2, 10)
            entry = {
                "type": "KEY_NUMBER",
                "market": row["market"],
                "opener_value": ov,
                "current_value": cv,
                "key_numbers_crossed": kn["key_numbers_crossed"],
                "note": kn["note"],
                "score": round(kn_score, 2),
            }
            ev["clv_signals"].append(entry)
            ev["total_score"] += kn_score


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
            public_pct = rlm.get("public_pct")
            public_side = rlm.get("public_side")
            sharp_side = rlm.get("sharp_side")
            strength = rlm.get("strength", 1)
            if public_pct is not None and public_side and sharp_side:
                try:
                    _rlm_result = score_rlm(
                        public_pct=float(public_pct) / 100.0 if float(public_pct) > 1 else float(public_pct),
                        line_move_direction=sharp_side,
                        public_side=public_side,
                        move_magnitude=float(strength) if strength else 0.5,
                    )
                    raw_score = min(_rlm_result.get("rlm_score", strength * 2.5), 10)
                except (TypeError, ValueError):
                    raw_score = min(strength * 2.5, 10)
            else:
                # Not enough real fields to run score_rlm (missing side/pct
                # data) -- fall back to the simple scalar rather than fail.
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
                ev["market_direction_votes"][_market_bucket(rlm.get("type"))][rlm["sharp_side"]] += sig_score

    # ── Finalize ──
    board = []
    for gk, ev in events.items():
        if not ev["clv_signals"] and not ev["rlm_signals"]:
            continue
        consensus_direction = None
        if ev["direction_votes"]:
            consensus_direction = max(ev["direction_votes"].items(), key=lambda kv: kv[1])[0]

        # Multi-market confirmation bonus: if spread AND total AND/or
        # moneyline all independently point the same direction, that's a
        # qualitatively stronger signal than one market moving alone --
        # previously just summed linearly with no bonus at all. Only
        # counts markets where that direction was actually the LEADING
        # vote within that market (not just present at all).
        confirming_markets = 0
        if consensus_direction:
            for _mkt, _votes in ev["market_direction_votes"].items():
                if _votes and max(_votes.items(), key=lambda kv: kv[1])[0] == consensus_direction:
                    confirming_markets += 1
        confirmation_multiplier = 1.0 + (0.15 * max(confirming_markets - 1, 0))  # +15% per additional confirming market
        adjusted_score = round(ev["total_score"] * confirmation_multiplier, 2)

        entry = {
            "game_key": gk,
            "game_label": ev["game_label"],
            "total_score": adjusted_score,
            "raw_score": round(ev["total_score"], 2),
            "confirming_markets": confirming_markets,
            "clv_signals": ev["clv_signals"],
            "steam_signals": ev["steam_signals"],
            "rlm_signals": ev["rlm_signals"],
            "consensus_direction": consensus_direction,
            "tier": _tier(adjusted_score),
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

    # ── MLB starter/bullpen enrichment (FanGraphs source, per user request) ──
    if sport.upper() == "MLB" and team_starter_bullpen_gap is not None and fetch_team_era_split is not None:
        try:
            fg_teams = fetch_team_era_split(pitcher_type="sta")
        except Exception:
            fg_teams = {}
        # Build canon(fangraphs_name) -> fangraphs_name lookup once, instead
        # of re-splitting game_label strings (which broke on full team
        # names vs FanGraphs abbreviations — fixed by using team_canon,
        # the same normalization already used elsewhere in this repo).
        fg_canon_map = {canon(fg_name, sport): fg_name for fg_name in fg_teams}

        for entry in board:
            label = entry.get("game_label", "")
            if "@" not in label:
                continue
            away_raw, home_raw = [t.strip() for t in label.split("@", 1)]
            for raw_name in (away_raw, home_raw):
                fg_name = fg_canon_map.get(canon(raw_name, sport))
                if not fg_name:
                    continue
                gap_data = team_starter_bullpen_gap(fg_name)
                if gap_data and gap_data.get("signal") != "NEUTRAL":
                    entry.setdefault("starter_bullpen_signals", []).append(gap_data)

    return board


def build_ufc_board(limit_events: int = 15) -> dict:
    """
    UFC doesn't fit the game-lines shape (no spread/total/moneyline per
    'event' the way team sports do), so this is a separate board rather
    than force-fit into build_unified_sharp_board(). Returns real
    finish-rate-by-weight-class data from ufc_scraper.py.
    """
    try:
        from ufc_scraper import compute_finish_rate_by_weightclass
        return compute_finish_rate_by_weightclass(limit_events)
    except Exception as e:
        print(f"[WARN] build_ufc_board: {e}")
        return {}
