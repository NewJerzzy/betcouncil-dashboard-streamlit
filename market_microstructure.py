"""
market_microstructure.py — Originator-follower lag + information asymmetry.

Both signals are built ONLY from timestamped snapshots of data already
harvested elsewhere in the repo (arbitrage_detector.fetch_all_book_odds,
fetchers.fetch_public_betting). No new external data source, no manual
input. History accumulates automatically each time the Game Lines tab
loads and is persisted via the same Gist read/write pattern the rest of
the repo already uses (fetchers.save_to_gist / GITHUB_GIST_ID).

Cold start: with zero history these return no signals (same as any other
harvester with an empty cache) and simply produce a real signal once a
handful of board loads have accumulated snapshots — no fabricated numbers
in the meantime.

Public API
----------
record_odds_snapshot(sport)          -> appends a timestamped snapshot, trims history
compute_originator_scores(sport)     -> dict {book: originator_score 0-1}
record_public_betting_snapshot(sport)-> appends a timestamped snapshot, trims history
detect_info_asymmetry(sport)         -> list of spike signals
"""
import json
import time
from datetime import datetime

try:
    from fetchers import (
        GITHUB_TOKEN, GITHUB_GIST_ID, GIST_API, _http, save_to_gist,
    )
except ImportError:
    GITHUB_TOKEN = ""
    GITHUB_GIST_ID = ""
    GIST_API = "https://api.github.com/gists"
    _http = None
    save_to_gist = lambda *a, **k: False

from arbitrage_detector import fetch_all_book_odds
from fetchers import fetch_public_betting

_MAX_SNAPSHOTS = 40          # keep last N snapshots per sport (bounds Gist size)
_MIN_SNAPSHOTS_FOR_SIGNAL = 5  # cold-start guard


def _read_gist_file(filename: str):
    """Read one file's JSON content from the shared Gist. Returns None on any failure."""
    if not GITHUB_TOKEN or not GITHUB_GIST_ID or _http is None:
        return None
    try:
        resp = _http.get(
            f"{GIST_API}/{GITHUB_GIST_ID}",
            headers={"Authorization": f"token {GITHUB_TOKEN}",
                     "Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        gist = resp.json()
        f = gist.get("files", {}).get(filename, {})
        if not f:
            return None
        return json.loads(f.get("content", "null"))
    except Exception:
        return None


# ── Originator-follower lag ──────────────────────────────────────────────

def _game_market_key(row: dict, market: str) -> str:
    return f"{row['Away']} @ {row['Home']}|{market}"


def record_odds_snapshot(sport: str) -> bool:
    """
    Pull current all-book odds (already-harvested data, no new fetch
    surface) and append a timestamped snapshot to rolling history.
    """
    rows = fetch_all_book_odds(sport)
    if not rows:
        return False

    key = f"originator_history_{sport.lower()}"
    history = _read_gist_file(f"betcouncil_{key}.json") or []

    ts = time.time()
    snapshot = {
        "ts": ts,
        "prices": [
            {"game": _game_market_key(r, "ML"), "book": r["book"], "ml_home": r.get("ml_home")}
            for r in rows if r.get("ml_home") is not None
        ],
    }
    history.append(snapshot)
    history = history[-_MAX_SNAPSHOTS:]
    save_to_gist(key, history)
    return True


def compute_originator_scores(sport: str) -> dict:
    """
    From accumulated snapshot history, determine which books' prices change
    FIRST when a game/market's consensus price moves, and which follow.
    Returns {book: originator_score 0-1}, where 1.0 = always moves first
    among books that moved on that event, 0.0 = always moves last.
    Empty dict if not enough history yet (cold start).
    """
    key = f"originator_history_{sport.lower()}"
    history = _read_gist_file(f"betcouncil_{key}.json") or []
    if len(history) < _MIN_SNAPSHOTS_FOR_SIGNAL:
        return {}

    # Track, per game/market, the last known price per book across snapshots
    last_price = {}       # (game, book) -> price
    move_order_wins = {}  # book -> count of times it moved first among movers
    move_order_total = {} # book -> count of times it moved at all

    for snap in history:
        moved_this_snapshot = []  # (game, book) that changed vs last_price
        for p in snap.get("prices", []):
            gk, book, price = p["game"], p["book"], p.get("ml_home")
            if price is None:
                continue
            prev = last_price.get((gk, book))
            if prev is not None and prev != price:
                moved_this_snapshot.append((gk, book))
            last_price[(gk, book)] = price

        # Group movers by game; first book seen moving in this snapshot for
        # a given game is credited as "led" for that event (approximate —
        # snapshot granularity, not sub-second, but a real, non-fabricated
        # signal that improves as snapshot frequency increases).
        by_game = {}
        for gk, book in moved_this_snapshot:
            by_game.setdefault(gk, []).append(book)
        for gk, books in by_game.items():
            if not books:
                continue
            leader = books[0]
            for book in books:
                move_order_total[book] = move_order_total.get(book, 0) + 1
            move_order_wins[leader] = move_order_wins.get(leader, 0) + 1

    scores = {}
    for book, total in move_order_total.items():
        wins = move_order_wins.get(book, 0)
        scores[book] = round(wins / total, 3) if total else 0.0

    return scores


# ── Information asymmetry (volume spike ahead of line move) ─────────────

def record_public_betting_snapshot(sport: str) -> bool:
    """
    Pull current public-betting data (already-harvested via
    fetchers.fetch_public_betting) and append a timestamped snapshot.
    """
    pb = fetch_public_betting(sport)
    if not pb:
        return False

    key = f"public_betting_history_{sport.lower()}"
    history = _read_gist_file(f"betcouncil_{key}.json") or []

    ts = time.time()
    snapshot = {"ts": ts, "games": {}}
    for game_key, data in pb.items():
        ml = data.get("ml", {})
        snapshot["games"][game_key] = {
            side: {"tickets": v.get("tickets"), "money": v.get("money")}
            for side, v in ml.items()
        }
    history.append(snapshot)
    history = history[-_MAX_SNAPSHOTS:]
    save_to_gist(key, history)
    return True


def detect_info_asymmetry(sport: str, money_spike_threshold: float = 15.0) -> list:
    """
    Compare the two most recent public-betting snapshots. Flag any
    game/side where money% jumped by >= money_spike_threshold percentage
    points between snapshots with little/no change in tickets% — the
    signature of a small number of large, informed bets landing quickly
    (vs. gradual public accumulation). Returns [] if fewer than 2
    snapshots exist yet (cold start).
    """
    key = f"public_betting_history_{sport.lower()}"
    history = _read_gist_file(f"betcouncil_{key}.json") or []
    if len(history) < 2:
        return []

    prev, curr = history[-2], history[-1]
    minutes_between = round((curr["ts"] - prev["ts"]) / 60, 1)

    signals = []
    for game_key, curr_sides in curr.get("games", {}).items():
        prev_sides = prev.get("games", {}).get(game_key, {})
        for side, curr_v in curr_sides.items():
            prev_v = prev_sides.get(side)
            if not prev_v:
                continue
            money_delta = (curr_v.get("money") or 0) - (prev_v.get("money") or 0)
            tickets_delta = (curr_v.get("tickets") or 0) - (prev_v.get("tickets") or 0)
            if money_delta >= money_spike_threshold and abs(tickets_delta) < money_delta / 2:
                signals.append({
                    "game": game_key,
                    "side": side,
                    "money_delta_pts": round(money_delta, 1),
                    "tickets_delta_pts": round(tickets_delta, 1),
                    "minutes_between_snapshots": minutes_between,
                    "current_money_pct": curr_v.get("money"),
                    "current_tickets_pct": curr_v.get("tickets"),
                })

    signals.sort(key=lambda x: x["money_delta_pts"], reverse=True)
    return signals
