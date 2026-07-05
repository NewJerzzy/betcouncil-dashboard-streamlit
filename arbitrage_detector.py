"""
arbitrage_detector.py — Cross-book arbitrage detection on real, already-
harvested Action Network scoreboard data.

Uses the SAME endpoint fetch_action_network_lines() already calls
(api.actionnetwork.com/web/v1/scoreboard/{slug}?bookIds=...), but reads
every book's entry in g["odds"] instead of filtering to a single book_id,
so no new network surface is introduced.

Arb math uses consensus_engine.american_to_implied_prob (already correct,
already in the repo) rather than reinventing odds conversion.

Public API
----------
fetch_all_book_odds(sport) -> list[dict]
    One row per (game, book) with real fields pulled straight off the
    scoreboard response: Home, Away, book, book_id, ml_home, ml_away,
    spread_away, spread_away_line, total, over, under.

find_arbitrage(sport) -> list[dict]
    Moneyline and total arbs, sorted by profit_pct descending. Each:
        {game, market, side_a: {book, odds}, side_b: {book, odds},
         implied_total, profit_pct}
"""
import os
import time
from datetime import datetime

from consensus_engine import american_to_implied_prob

try:
    from fetchers import _http, _AN_SPORT_SLUGS, _AN_BOOK_IDS, CACHE_DIR, _safe_load_pkl, _safe_save_pkl
except ImportError:
    _http = None
    _AN_SPORT_SLUGS = {}
    _AN_BOOK_IDS = ""
    CACHE_DIR = "/tmp"
    _safe_load_pkl = lambda p: None
    _safe_save_pkl = lambda p, d: None

# Only book_ids confirmed named elsewhere in fetchers.py; others are labeled
# generically rather than guessed, since their names aren't documented in
# the codebase.
_KNOWN_BOOK_NAMES = {
    8: "MyBookie",
    69: "FanDuel",
    123: "Caesars",
}


def fetch_all_book_odds(sport: str) -> list:
    """
    Pull full-game lines for every book in the Action Network scoreboard
    response (not just one book_id). Same endpoint/schema already confirmed
    working by fetch_action_network_lines() in fetchers.py.
    Cached 10 minutes per (sport, date), same TTL as the existing fetch.
    """
    if _http is None:
        return []

    slug = _AN_SPORT_SLUGS.get(sport.lower().strip(), sport.lower().strip())
    today = datetime.now().strftime("%Y%m%d")

    cache_path = os.path.join(CACHE_DIR, f"an_all_books_{slug}_{today}.pkl")
    if os.path.exists(cache_path):
        age_m = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_m < 10:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    url = (
        f"https://api.actionnetwork.com/web/v1/scoreboard/{slug}"
        f"?bookIds={_AN_BOOK_IDS}&date={today}&periods=event"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        resp = _http.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    games = data.get("games", [])
    rows = []

    for g in games:
        teams = g.get("teams", [])
        if len(teams) < 2:
            continue
        away_id = g.get("away_team_id")
        home_id = g.get("home_team_id")
        team_by_id = {t["id"]: t for t in teams}
        away_team = team_by_id.get(away_id, teams[0])
        home_team = team_by_id.get(home_id, teams[1] if len(teams) > 1 else teams[0])
        away_name = away_team.get("full_name") or away_team.get("display_name", "")
        home_name = home_team.get("full_name") or home_team.get("display_name", "")

        for o in g.get("odds", []):
            if o.get("type") != "game":
                continue
            book_id = o.get("book_id")
            rows.append({
                "Home": home_name,
                "Away": away_name,
                "book_id": book_id,
                "book": _KNOWN_BOOK_NAMES.get(book_id, f"book_{book_id}"),
                "ml_home": o.get("ml_home"),
                "ml_away": o.get("ml_away"),
                "spread_away": o.get("spread_away"),
                "spread_away_line": o.get("spread_away_line"),
                "total": o.get("total"),
                "over": o.get("over"),
                "under": o.get("under"),
            })

    if rows:
        try:
            _safe_save_pkl(cache_path, rows)
        except Exception:
            pass

    return rows


def _game_key(row: dict) -> str:
    return f"{row['Away']} @ {row['Home']}"


def find_arbitrage(sport: str, min_profit_pct: float = 0.5) -> list:
    """
    Detect real cross-book arbitrage: moneyline (home vs away) and totals
    (over vs under), using implied probability sums < 1.0 as the arb test.
    An arb exists when best-home-price-implied-prob + best-away-price-implied-
    prob < 1.0 (i.e. you can back both sides across two books and lock a
    profit regardless of outcome).

    Returns list sorted by profit_pct descending. Each entry:
        {game, market, side_a: {book, odds}, side_b: {book, odds}, profit_pct}
    """
    rows = fetch_all_book_odds(sport)
    if not rows:
        return []

    by_game = {}
    for r in rows:
        by_game.setdefault(_game_key(r), []).append(r)

    arbs = []
    for game, book_rows in by_game.items():
        # ── Moneyline arb ──
        best_home = None
        best_away = None
        for r in book_rows:
            hp = american_to_implied_prob(r.get("ml_home"))
            ap = american_to_implied_prob(r.get("ml_away"))
            if hp is not None and (best_home is None or hp < best_home[0]):
                best_home = (hp, r["book"], r["ml_home"])
            if ap is not None and (best_away is None or ap < best_away[0]):
                best_away = (ap, r["book"], r["ml_away"])
        if best_home and best_away and best_home[1] != best_away[1]:
            total_prob = best_home[0] + best_away[0]
            if total_prob < 1.0:
                profit_pct = round((1.0 / total_prob - 1.0) * 100, 2)
                if profit_pct >= min_profit_pct:
                    arbs.append({
                        "game": game,
                        "market": "Moneyline",
                        "side_a": {"book": best_home[1], "odds": best_home[2], "side": "HOME"},
                        "side_b": {"book": best_away[1], "odds": best_away[2], "side": "AWAY"},
                        "profit_pct": profit_pct,
                    })

        # ── Total (over/under) arb ──
        # Only compare books quoting the SAME total number — different
        # numbers aren't a true arb, they're just different lines.
        totals_seen = {}
        for r in book_rows:
            t = r.get("total")
            if t is None:
                continue
            totals_seen.setdefault(t, []).append(r)
        for t, trows in totals_seen.items():
            best_over = None
            best_under = None
            for r in trows:
                op = american_to_implied_prob(r.get("over"))
                up = american_to_implied_prob(r.get("under"))
                if op is not None and (best_over is None or op < best_over[0]):
                    best_over = (op, r["book"], r["over"])
                if up is not None and (best_under is None or up < best_under[0]):
                    best_under = (up, r["book"], r["under"])
            if best_over and best_under and best_over[1] != best_under[1]:
                total_prob = best_over[0] + best_under[0]
                if total_prob < 1.0:
                    profit_pct = round((1.0 / total_prob - 1.0) * 100, 2)
                    if profit_pct >= min_profit_pct:
                        arbs.append({
                            "game": game,
                            "market": f"Total {t}",
                            "side_a": {"book": best_over[1], "odds": best_over[2], "side": "OVER"},
                            "side_b": {"book": best_under[1], "odds": best_under[2], "side": "UNDER"},
                            "profit_pct": profit_pct,
                        })

    arbs.sort(key=lambda x: x["profit_pct"], reverse=True)
    return arbs
