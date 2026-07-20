"""
game_board_snapshot_headless.py — captures today's game-line board (real
market odds vs. model) WITHOUT needing anyone to open the Streamlit app.

Why this exists: store_game_board_snapshot() in app.py only fires when a
user has the Game Lines tab open for a given sport in a live session. As
of 2026-07-13, that meant the game-line grading pipeline (added
2026-07-12, scripts/daily_board_grading.py) had zero snapshots to grade —
betcouncil_game_board_snapshots.json had never been written. This script
runs headless on a schedule (.github/workflows/game_board_snapshot.yml)
so a snapshot exists every day regardless of whether the app gets opened.

Scope, stated plainly: this grades MONEYLINE only, not SPREAD/TOTAL/ALT
LINE. The interactive app's analyze_game_edge() builds its edge from a
17-book line consensus that lives entirely in st.session_state (populated
by a full per-sport data load inside a live Streamlit run) — reproducing
that headlessly would mean re-implementing a large, actively-changing
part of app.py outside of it, which is a correctness risk this script
deliberately avoids. Moneyline lets it use a simpler, self-contained,
defensible edge: devigged market win probability (no_vig_prob, same devig
math used everywhere else in this codebase) vs. a model win probability
derived from the same power ratings the interactive tool uses (live
fetch_*_live_stats() overlaid on the static config.py dict, same pattern
as get_live_power_ratings in app.py), via a standard logistic win-prob
mapping. This is a real, independently-computed edge — not a placeholder —
but it is a proxy for the full interactive model, not a mirror of it.
Picks are tagged "source": "headless_snapshot" so that's traceable.

Market line source: scrape_bovada_lines() (betcouncil_auto_scraper.py) —
already-proven, no-login, curl_cffi-free plain-requests scrape of
Bovada's public odds feed. Chosen over ESPN's embedded odds field, which
this project's own scraping notes found sparse/unreliable for moneyline
coverage.

NFL is skipped: no NFL_POWER_RATINGS exists in config.py (analyze_all_games
doesn't compute NFL game-line power-rating edges in the interactive app
either), so there's no model side to compare against without inventing
one. Left out rather than faked.

Writes to the exact same Gist key/schema as store_game_board_snapshot()
in app.py, so scripts/daily_board_grading.py needs zero changes to start
consuming this.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GAME_SNAPSHOT_FILE = "betcouncil_game_board_snapshots.json"
# Dedicated debug log, not the shared betcouncil_scraper_debug_log.txt --
# confirmed via live Gist inspection that auto_scraper's every-15-min
# writes (verbose, hundreds of lines per run) completely crowd out this
# script's twice-daily entries within the shared file's 400-line
# retention window, making it impossible to diagnose a real failure here.
DEBUG_LOG_FILE = "betcouncil_game_board_snapshot_debug.txt"

SEASON_ACTIVE_MONTHS = {
    "NBA":  [10, 11, 12, 1, 2, 3, 4, 5, 6],
    "NHL":  [10, 11, 12, 1, 2, 3, 4, 5, 6],
    "MLB":  [3, 4, 5, 6, 7, 8, 9, 10],
    "WNBA": [5, 6, 7, 8, 9, 10],
    # NFL intentionally excluded -- see module docstring.
}

# Logistic scale for rating-diff -> win-probability. Ratings in this
# codebase are centered ~100-106 with roughly a +/-15-20 spread across a
# league (see config.py POWER_RATINGS dicts), not a full Elo-style 0-2000+
# range, so a 400-point Elo divisor would flatten every game to ~50/50.
# 25 puts a realistic ~10-point rating gap (a good team vs. a bad one) at
# roughly a 65-70% model win probability, which is in the right
# neighborhood for a real favorite -- reasonable but explicitly a rough
# approximation, not a fitted constant.
RATING_PROB_SCALE = 25.0

_tier_rank = {"SOVEREIGN": 0, "ELITE": 1, "APPROVED": 2, "LEAN": 3, "PASS": 4}

# NBA_POWER_RATINGS/WNBA_POWER_RATINGS in config.py are keyed by team
# abbreviation ("BOS", "OKC"), but Bovada's matchup/outcome strings use
# full team names ("Boston Celtics"). MLB/NHL power ratings are already
# keyed by full name, so they don't need this. Mirrors the exact
# abbreviation maps app.py's analyze_game_edge already maintains
# (_PR_MAP_NBA / _PR_MAP_WNBA) so ratings mean the same thing here as in
# the interactive tool.
_PR_MAP_NBA = {
    "GSW":"Golden State Warriors","LAL":"Los Angeles Lakers","LAC":"Los Angeles Clippers",
    "NYK":"New York Knicks","NOP":"New Orleans Pelicans","SAS":"San Antonio Spurs",
    "OKC":"Oklahoma City Thunder","UTA":"Utah Jazz","MEM":"Memphis Grizzlies",
    "BKN":"Brooklyn Nets","MIA":"Miami Heat","BOS":"Boston Celtics",
    "PHI":"Philadelphia 76ers","TOR":"Toronto Raptors","CHI":"Chicago Bulls",
    "MIL":"Milwaukee Bucks","IND":"Indiana Pacers","ATL":"Atlanta Hawks",
    "CLE":"Cleveland Cavaliers","DET":"Detroit Pistons","ORL":"Orlando Magic",
    "WAS":"Washington Wizards","CHA":"Charlotte Hornets","PHX":"Phoenix Suns",
    "DAL":"Dallas Mavericks","DEN":"Denver Nuggets","MIN":"Minnesota Timberwolves",
    "POR":"Portland Trail Blazers","SAC":"Sacramento Kings","HOU":"Houston Rockets",
}
_PR_MAP_WNBA = {
    "ATL":"Atlanta Dream","CHI":"Chicago Sky","CON":"Connecticut Sun",
    "DAL":"Dallas Wings","IND":"Indiana Fever","LV":"Las Vegas Aces",
    "LA":"Los Angeles Sparks","MIN":"Minnesota Lynx","NY":"New York Liberty",
    "PHX":"Phoenix Mercury","SEA":"Seattle Storm","WAS":"Washington Mystics",
    "GS":"Golden State Valkyries","POR":"Portland Fire",
}


def log(msg: str) -> None:
    print(f"[game_board_snapshot_headless] {msg}", flush=True)


def gist_read(token, filename):
    resp = requests.get(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    if resp.status_code != 200:
        log(f"Gist read failed: {resp.status_code}")
        return None
    files = resp.json().get("files", {})
    f = files.get(filename)
    if not f:
        return None
    content = f.get("content", "")
    if f.get("truncated"):
        content = requests.get(f["raw_url"], timeout=20).text
    try:
        return json.loads(content) if content.strip() else None
    except json.JSONDecodeError:
        return None


def gist_write(token, filename, payload):
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {filename: {"content": json.dumps(payload, indent=2)}}},
        timeout=30,
    )
    return resp.status_code in (200, 201)


def gist_append_debug_log(token, text):
    try:
        existing = gist_read(token, DEBUG_LOG_FILE) or ""
        if not isinstance(existing, str):
            existing = ""
        combined = (existing + "\n" + text).strip()
        # Keep the relay file from growing unbounded -- last ~400 lines.
        lines = combined.splitlines()[-400:]
        gist_write(token, DEBUG_LOG_FILE, "\n".join(lines))
    except Exception as e:
        log(f"debug log relay failed (non-fatal): {e}")


def in_season_sports():
    month = datetime.now().month
    return [s for s, months in SEASON_ACTIVE_MONTHS.items() if month in months]


def model_win_prob(home_rating: float, away_rating: float) -> float:
    diff = home_rating - away_rating
    try:
        return 1.0 / (1.0 + 10 ** (-diff / RATING_PROB_SCALE))
    except OverflowError:
        return 0.99 if diff > 0 else 0.01


def get_power_ratings(sport: str) -> dict:
    """Live ratings overlaid on the static config.py dict -- same pattern
    as get_live_power_ratings() in app.py, minus the st.cache_data wrapper
    (not usable outside a running Streamlit app) and minus the st.session_state
    UI-source tracking, which this headless run has no use for.
    """
    from config import NBA_POWER_RATINGS, MLB_POWER_RATINGS, NHL_POWER_RATINGS, WNBA_POWER_RATINGS
    static_map = {
        "NBA": NBA_POWER_RATINGS, "MLB": MLB_POWER_RATINGS,
        "NHL": NHL_POWER_RATINGS, "WNBA": WNBA_POWER_RATINGS,
    }
    fallback = static_map.get(sport, {})
    if sport == "NBA":
        fallback = {_PR_MAP_NBA.get(k, k): v for k, v in fallback.items()}
    elif sport == "WNBA":
        fallback = {_PR_MAP_WNBA.get(k, k): v for k, v in fallback.items()}
    try:
        from fetchers import (
            fetch_mlb_live_stats, fetch_nba_live_stats,
            fetch_nhl_live_stats, fetch_wnba_live_stats,
        )
        live_fn = {
            "MLB": fetch_mlb_live_stats, "NBA": fetch_nba_live_stats,
            "NHL": fetch_nhl_live_stats, "WNBA": fetch_wnba_live_stats,
        }.get(sport)
        live = (live_fn().get("team_ratings", {}) if live_fn else {}) or {}
    except Exception as e:
        log(f"{sport}: live power-rating fetch failed, using static only ({e})")
        live = {}
    merged = dict(fallback)
    merged.update(live)
    return merged


def fetch_bovada_moneylines(sport: str) -> list:
    """Returns [{"matchup", "home_guess", "away_guess", "home_ml", "away_ml"}]
    parsed from scrape_bovada_lines() raw output. Bovada's coupon
    description format is "Away @ Home" -- team name matching against the
    power-ratings dict is fuzzy (normalize_name + substring), since
    Bovada's naming doesn't always exactly match config.py's team keys.
    """
    from betcouncil_auto_scraper import scrape_bovada_lines
    from utils import normalize_name

    raw = scrape_bovada_lines(sport)
    by_matchup = {}
    for line in raw:
        market = (line.get("market") or "").lower()
        if "moneyline" not in market:
            continue
        matchup = line.get("matchup", "")
        if not matchup:
            continue
        by_matchup.setdefault(matchup, {})[line.get("outcome", "")] = line.get("american")

    games = []
    for matchup, sides in by_matchup.items():
        if len(sides) != 2:
            continue
        (team_a, ml_a), (team_b, ml_b) = list(sides.items())
        if ml_a is None or ml_b is None:
            continue
        parts = [p.strip() for p in matchup.split("@")]
        away_guess, home_guess = (parts[0], parts[1]) if len(parts) == 2 else (team_a, team_b)
        # Map team_a/team_b (Bovada's own outcome labels) onto home/away by
        # normalized substring match against the matchup's own two halves,
        # since Bovada's outcome label and matchup-string team name aren't
        # always identically formatted.
        na, nb = normalize_name(team_a), normalize_name(team_b)
        nh, nw = normalize_name(home_guess), normalize_name(away_guess)
        if na in nh or nh in na:
            home_ml, away_ml = ml_a, ml_b
        elif nb in nh or nh in nb:
            home_ml, away_ml = ml_b, ml_a
        else:
            continue  # can't confidently assign home/away -- skip rather than guess
        games.append({
            "matchup": matchup, "home_guess": home_guess, "away_guess": away_guess,
            "home_ml": home_ml, "away_ml": away_ml,
        })
    return games


def match_team_rating(name: str, ratings: dict):
    from utils import normalize_name
    target = normalize_name(name)
    if not target:
        return None
    for team, rating in ratings.items():
        nt = normalize_name(team)
        if nt == target or target in nt or nt in target:
            return rating
    return None


def build_snapshot_picks(sport: str) -> list:
    from utils import no_vig_prob
    from bc_utils import get_game_tier

    ratings = get_power_ratings(sport)
    if not ratings:
        log(f"{sport}: no power ratings available, skipping")
        return []

    try:
        games = fetch_bovada_moneylines(sport)
    except Exception as e:
        log(f"{sport}: Bovada fetch failed ({e})")
        return []

    picks = []
    for g in games:
        try:
            home_rating = match_team_rating(g["home_guess"], ratings)
            away_rating = match_team_rating(g["away_guess"], ratings)
            if home_rating is None or away_rating is None:
                continue
            model_home_p = model_win_prob(home_rating, away_rating)
            market_home_p = no_vig_prob(g["home_ml"], g["away_ml"])
            edge = model_home_p - market_home_p
            side = "home" if edge > 0 else "away"
            pick_team = g["home_guess"] if side == "home" else g["away_guess"]
            tier = get_game_tier(abs(edge), sport)
            if tier == "PASS":
                continue
            picks.append({
                "matchup": g["matchup"], "home": g["home_guess"], "away": g["away_guess"],
                "market": "MONEYLINE", "pick": pick_team, "line": 0,
                "edge": round(abs(edge), 4), "tier": tier,
                "source": "headless_snapshot",
            })
        except Exception as e:
            log(f"{sport}: skipping one matchup due to error ({e})")
            continue

    picks.sort(key=lambda p: (_tier_rank.get(p["tier"], 5), -abs(p["edge"])))
    return picks[:30]


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        log("No GITHUB_TOKEN in environment -- aborting")
        sys.exit(1)

    sports = in_season_sports()
    log(f"In-season sports: {sports or '(none)'}")

    today_key = date.today().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    stored = gist_read(token, GAME_SNAPSHOT_FILE) or {}

    total_picks = 0
    summary_lines = [f"=== game_board_snapshot_headless run {now_str} ==="]
    for sport in sports:
        picks = build_snapshot_picks(sport)
        snap_key = f"{today_key}_{sport}_{datetime.now().strftime('%H:%M')}"
        if picks:
            stored[snap_key] = {
                "sport": sport, "date": today_key, "timestamp": now_str,
                "picks": picks, "source": "headless_snapshot",
            }
            total_picks += len(picks)
        summary_lines.append(f"  {sport}: {len(picks)} picks")
        log(f"{sport}: {len(picks)} picks captured")

    cutoff = (date.today() - timedelta(days=45)).strftime("%Y-%m-%d")
    stored = {k: v for k, v in stored.items() if v.get("date", "0000-00-00") >= cutoff}

    if total_picks:
        ok = gist_write(token, GAME_SNAPSHOT_FILE, stored)
        log(f"Gist write {'ok' if ok else 'FAILED'} -- {total_picks} total picks across {len(sports)} sports")
        summary_lines.append(f"TOTAL: {total_picks} picks written | gist_write_ok={ok}")
    else:
        log("No picks captured this run -- nothing written")
        summary_lines.append("TOTAL: 0 picks -- nothing written")

    gist_append_debug_log(token, "\n".join(summary_lines))


if __name__ == "__main__":
    main()
