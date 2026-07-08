"""
prop_market_intelligence.py — Cross-platform DFS prop intelligence.

Three features, in the priority order Abraham confirmed:

1. devig_vs_gem(price, gem_prob)      — devig a book's posted price and
   compare the implied probability to GEM's own probability for the same
   prop. Reuses consensus_engine.american_to_implied_prob (already correct,
   already in the repo) rather than reinventing odds math.

2. record_prop_snapshot / get_prop_line_moves — timestamped snapshots of
   PP/Underdog/Pick6 lines, Gist-backed, same pattern as
   market_microstructure.py's originator-lag snapshots. Diffing two
   snapshots surfaces "PrizePicks moved Judge HR 0.5 -> 1.5 between 10:00
   and 10:15" and feeds the existing (currently hardcoded empty-string)
   "Movement" column in the enriched prop dict in app.py.

3. group_props_by_event / find_cross_team_correlations — groups props by
   Matchup (same game) and flags CROSS-TEAM correlated pairs (QB passing
   yards <-> opposing WR receiving yards, pitcher Ks <-> opposing team hit
   total). This is additive to compute_prop_correlation_score() in app.py,
   which only checks same-player and same-team pairs today — it does not
   look across the matchup at the opposing side at all.

Cold start: snapshot-based functions return [] / no signal until enough
history has accumulated, same convention as market_microstructure.py.

Public API
----------
devig_vs_gem(price, gem_prob) -> dict | None
record_prop_snapshot(sport, book_data) -> bool
get_prop_line_moves(sport, min_minutes_apart=10) -> list[dict]
group_props_by_event(props) -> dict[str, list[dict]]
find_cross_team_correlations(props) -> list[dict]
"""
import time
from datetime import datetime

from consensus_engine import american_to_implied_prob

try:
    from fetchers import save_to_gist, GITHUB_TOKEN, GITHUB_GIST_ID, GIST_API, _http
except ImportError:
    save_to_gist = lambda *a, **k: False
    GITHUB_TOKEN = ""
    GITHUB_GIST_ID = ""
    GIST_API = "https://api.github.com/gists"
    _http = None

_MAX_SNAPSHOTS = 60          # ~15hrs at 15-min polling, bounds Gist size
_MIN_SNAPSHOTS_FOR_SIGNAL = 2


# ── 1. Devig DFS price vs. GEM probability ───────────────────────────────

def devig_vs_gem(price, gem_prob: float, threshold: float = 0.04) -> dict | None:
    """
    Devig a book's posted American-odds price and compare the implied
    probability to GEM's own Poisson/model probability for the same prop.

    Parameters
    ----------
    price : the book's posted price for the side GEM likes (e.g. "-130").
        Returns None for non-American-odds formats (PrizePicks standard
        lines, Underdog's "3x" payout format) since there's no real juice
        to devig there — those need odds_type-based tiering instead
        (see goblin/demon note in fetchers._parse_prizepicks_harvested).
    gem_prob : GEM's model probability (0-1) for the same side.
    threshold : minimum |market - model| gap worth flagging (default 4pts).

    Returns
    -------
    dict {market_implied_prob, gem_prob, gap, direction, flag} or None if
    price isn't devig-able or gem_prob is missing.
    """
    if gem_prob is None:
        return None
    market_prob = american_to_implied_prob(price)
    if market_prob is None:
        return None

    gap = round(market_prob - gem_prob, 4)
    return {
        "market_implied_prob": round(market_prob, 4),
        "gem_prob": round(gem_prob, 4),
        "gap": gap,
        # market > model: the book/market thinks it hits MORE than GEM does
        "direction": "market_higher" if gap > 0 else ("model_higher" if gap < 0 else "aligned"),
        "flag": abs(gap) >= threshold,
    }


# ── 2. Prop line movement snapshots (Gist-backed, mirrors market_microstructure.py) ──

def _read_gist_file(filename: str):
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
        import json
        return json.loads(f.get("content", "null"))
    except Exception:
        return None


def _prop_row_key(book: str, player: str, stat: str) -> str:
    return f"{book}|{player}|{stat}"


def record_prop_snapshot(sport: str, book_data: dict) -> bool:
    """
    Append a timestamped snapshot of every book's prop lines to rolling
    history. book_data: {book_name: [prop_dicts]} — same shape
    prop_normalizer.match_props_across_books() already consumes.
    Call this once per board load (same cadence as the 15-min poll cycle
    already in place for PrizePicks/Underdog GitHub Actions).
    """
    rows = []
    for book, props in (book_data or {}).items():
        if not isinstance(props, list):
            continue
        for p in props:
            player = str(p.get("Player") or p.get("player") or "")
            stat   = str(p.get("Prop") or p.get("Stat") or p.get("stat") or "")
            line   = p.get("Line") or p.get("line")
            if not player or not stat or line is None:
                continue
            try:
                line_f = float(line)
            except (TypeError, ValueError):
                continue
            rows.append({"key": _prop_row_key(book, player, stat), "line": line_f})

    if not rows:
        return False

    gist_key = f"prop_line_history_{sport.lower()}"
    history = _read_gist_file(f"betcouncil_{gist_key}.json") or []
    history.append({"ts": time.time(), "rows": rows})
    history = history[-_MAX_SNAPSHOTS:]
    return save_to_gist(gist_key, history)


def get_prop_line_moves(sport: str, min_minutes_apart: float = 10.0) -> list:
    """
    Compare the earliest and most recent snapshot at least
    min_minutes_apart minutes apart, and return every prop whose line
    changed between them.

    Returns
    -------
    list[dict]: {book, player, stat, from_line, to_line, delta,
                 minutes_between, direction}
        direction is "up" or "down" — a mover in GEM's favored direction is
        confirmation, a mover against it is a negative signal (apply that
        read where this is consumed, e.g. app.py's "Movement" column).
    Empty list on cold start (fewer than 2 snapshots, or none far enough
    apart yet).
    """
    gist_key = f"prop_line_history_{sport.lower()}"
    history = _read_gist_file(f"betcouncil_{gist_key}.json") or []
    if len(history) < _MIN_SNAPSHOTS_FOR_SIGNAL:
        return []

    latest = history[-1]
    baseline = None
    for snap in history:
        if (latest["ts"] - snap["ts"]) / 60.0 >= min_minutes_apart:
            baseline = snap  # keep advancing to the CLOSEST snapshot that still clears the gap
    if baseline is None:
        baseline = history[0]

    minutes_between = round((latest["ts"] - baseline["ts"]) / 60.0, 1)
    if minutes_between <= 0:
        return []

    base_lines = {r["key"]: r["line"] for r in baseline.get("rows", [])}
    moves = []
    for r in latest.get("rows", []):
        prev_line = base_lines.get(r["key"])
        if prev_line is None or prev_line == r["line"]:
            continue
        book, player, stat = r["key"].split("|", 2)
        delta = round(r["line"] - prev_line, 2)
        moves.append({
            "book": book, "player": player, "stat": stat,
            "from_line": prev_line, "to_line": r["line"], "delta": delta,
            "minutes_between": minutes_between,
            "direction": "up" if delta > 0 else "down",
        })

    moves.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return moves


# ── 3. Event grouping + cross-team correlation ───────────────────────────

# Cross-team (opposing-side) correlated stat pairs — distinct from the
# same-team/same-player pairs already in app.py's PROP_CORRELATION_PAIRS.
# These only make sense when the two legs are on OPPOSING teams in the
# same game, which compute_prop_correlation_score() in app.py does not
# check for at all today.
CROSS_TEAM_CORRELATION_PAIRS = {
    ("PASSING YARDS", "RECEIVING YARDS"): 0.55,   # QB <-> opposing-drive-adjacent WR is same-team; this pair is evaluated same-team elsewhere. Cross-team use: shootout game total correlation below.
    ("PITCHER STRIKEOUTS", "TEAM HITS"): 0.45,     # pitcher Ks (negative) <-> opposing team hit total (negative correlation: more Ks -> fewer hits)
    ("PITCHER STRIKEOUTS", "TEAM RUNS"): 0.40,
    ("POINTS", "POINTS"): 0.30,                    # high-pace/shootout game total correlation, both teams' top scorers
}


def group_props_by_event(props: list) -> dict:
    """
    Group a flat list of enriched props by Matchup ("Away @ Home"), the
    same field already populated elsewhere in app.py. Returns
    {matchup: [props]}. Props with no Matchup are dropped.
    """
    grouped: dict = {}
    for p in props or []:
        matchup = p.get("Matchup") or p.get("matchup") or ""
        if not matchup:
            continue
        grouped.setdefault(matchup, []).append(p)
    return grouped


def find_cross_team_correlations(props: list) -> list:
    """
    Within each event (Matchup), flag prop pairs on OPPOSING teams whose
    stat types are in CROSS_TEAM_CORRELATION_PAIRS. This is the piece
    compute_prop_correlation_score() in app.py doesn't cover — it only
    checks same-player and same-team pairs, never across the matchup.

    Returns
    -------
    list[dict]: {matchup, prop_a: "Player Stat (Team)", prop_b: "...",
                 correlation, note}
    """
    results = []
    for matchup, group in group_props_by_event(props).items():
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                p1, p2 = group[i], group[j]
                t1 = p1.get("Team") or p1.get("team") or ""
                t2 = p2.get("Team") or p2.get("team") or ""
                if not t1 or not t2 or t1 == t2:
                    continue  # only cross-team pairs; same-team already handled elsewhere
                s1 = (p1.get("Prop") or p1.get("prop") or "").upper()
                s2 = (p2.get("Prop") or p2.get("prop") or "").upper()
                pair_key = tuple(sorted([s1, s2]))
                corr = CROSS_TEAM_CORRELATION_PAIRS.get(pair_key)
                if corr is None:
                    continue
                results.append({
                    "matchup": matchup,
                    "prop_a": f"{p1.get('Player','')} {s1} ({t1})",
                    "prop_b": f"{p2.get('Player','')} {s2} ({t2})",
                    "correlation": corr,
                    "note": "cross-team same-game correlation",
                })

    results.sort(key=lambda x: x["correlation"], reverse=True)
    return results
