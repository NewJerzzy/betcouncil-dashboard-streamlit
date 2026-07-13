"""
daily_board_grading.py — grades the FULL board (best bets + everything
else on the board, not just picks you locked in) against actual results,
the day after it was generated. Runs automatically via GitHub Actions
(.github/workflows/daily_board_grading.yml) — no manual action needed.

Why the full board, not just locked bets: you only place a handful of
bets a day, but the board itself might carry 30-50+ picks. Grading all
of them gives the calibration/signal-weight system far more data to learn
from per day, without waiting weeks for enough placed-bet volume. This is
model-accuracy tracking — it stays completely separate from your actual
bankroll/ROI ledger, which only ever reflects real placed bets.

Coverage note, stated plainly rather than overclaimed: player-prop
grading uses full-roster/full-league player-ID lookups for all 5 sports
(fetch_mlb_full_roster_ids / fetch_nhl_full_roster_ids /
fetch_nba_full_roster_ids / fetch_wnba_full_roster_ids /
fetch_nfl_full_player_database — fetchers.py, closed 2026-07-11), not the
old hardcoded ESPN_ATHLETE_IDS subset (config.py, ~a few dozen players/
sport, now only used as an NFL last-resort fallback). A pick can still
come back UNGRADABLE for other reasons (stat category ESPN/MLB/NHL
doesn't expose, game not final yet, transient fetch error) — those are
real gaps, just not a name-coverage gap anymore.

Game-line grading (SPREAD/TOTAL/MONEYLINE/ALT LINE), added 2026-07-12,
mirrors the prop pipeline exactly but reads a separate snapshot file
(store_game_board_snapshot in app.py, or scripts/game_board_snapshot_headless.py
for MONEYLINE-only headless snapshots when nobody's opened the app that
day — added 2026-07-13, same snapshot schema, tagged "source":
"headless_snapshot" so it's traceable) and writes to a separate grading
history key so the two never collide. Coverage there is full — team/
score resolution via ESPN scoreboard works for any NBA/MLB/NFL/NHL
matchup, not a hardcoded player subset, since it only needs final scores.

This script only reads snapshots and writes grading results. It never
touches the bet ledger, bankroll, or locks.
"""

import json
import os
import sys
from datetime import date, timedelta

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SNAPSHOT_FILE = "betcouncil_board_snapshots.json"
GRADING_FILE = "betcouncil_board_grading_history.json"
GAME_SNAPSHOT_FILE = "betcouncil_game_board_snapshots.json"
GAME_GRADING_FILE = "betcouncil_game_board_grading_history.json"


def log(msg: str) -> None:
    print(f"[daily_board_grading] {msg}", flush=True)


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


def grade_day(target_date: str):
    sys.path.insert(0, ".")
    from fetchers import resolve_actual_stat_for_grading

    token = os.environ["GITHUB_TOKEN"]
    stored = gist_read(token, SNAPSHOT_FILE) or {}
    day_snaps = {k: v for k, v in stored.items() if v.get("date") == target_date}
    if not day_snaps:
        log(f"No board snapshots found for {target_date} — nothing to grade.")
        return {"date": target_date, "graded": 0, "results": []}

    latest_by_sport = {}
    for k, v in day_snaps.items():
        sp = v.get("sport", "")
        if sp not in latest_by_sport or v.get("timestamp", "") > latest_by_sport[sp].get("timestamp", ""):
            latest_by_sport[sp] = v

    graded_results = []
    for sport, snap in latest_by_sport.items():
        log(f"Grading {sport}: {len(snap.get('props', []))} picks from {snap.get('timestamp')}")
        for p in snap.get("props", []):
            player, prop_type = p.get("player", ""), p.get("prop", "")
            line, side = p.get("line", 0), p.get("side", "OVER")
            try:
                actual = resolve_actual_stat_for_grading(player, sport, prop_type, target_date)
            except Exception as e:
                log(f"  resolve error for {player}/{prop_type}: {e}")
                actual = None

            if actual is None:
                outcome = "UNGRADABLE"
            elif actual == line:
                outcome = "PUSH"
            elif (actual > line and side == "OVER") or (actual < line and side == "UNDER"):
                outcome = "WIN"
            else:
                outcome = "LOSS"

            signals = p.get("signals", {})
            firing = {k: v for k, v in signals.items() if abs(v or 0) > 0.001}
            why = ", ".join(f"{k}:{v:+.2f}" for k, v in sorted(firing.items(), key=lambda kv: -abs(kv[1]))) or "no signals fired"

            graded_results.append({
                "date": target_date, "sport": sport, "player": player, "prop": prop_type,
                "side": side, "line": line, "actual": actual, "outcome": outcome,
                "edge": p.get("edge", 0), "prob": p.get("prob", 0.5), "tier": p.get("tier", ""),
                "best_bet": p.get("best_bet", False), "why": why, "source": "board_grading",
            })

    grading_history = gist_read(token, GRADING_FILE) or {}
    grading_history[target_date] = graded_results
    cutoff = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    grading_history = {k: v for k, v in grading_history.items() if k >= cutoff}
    gist_write(token, GRADING_FILE, grading_history)

    graded_n = sum(1 for r in graded_results if r["outcome"] != "UNGRADABLE")
    wins = sum(1 for r in graded_results if r["outcome"] == "WIN")
    losses = sum(1 for r in graded_results if r["outcome"] == "LOSS")
    log(f"Done: {len(graded_results)} total picks, {graded_n} gradable "
        f"({len(graded_results) - graded_n} ungradable), {wins}W-{losses}L")
    return {"date": target_date, "total": len(graded_results), "graded": graded_n, "wins": wins, "losses": losses}


def grade_game_day(target_date: str):
    sys.path.insert(0, ".")
    from fetchers import resolve_actual_game_result_for_grading

    token = os.environ["GITHUB_TOKEN"]
    stored = gist_read(token, GAME_SNAPSHOT_FILE) or {}
    day_snaps = {k: v for k, v in stored.items() if v.get("date") == target_date}
    if not day_snaps:
        log(f"No game board snapshots found for {target_date} — nothing to grade.")
        return {"date": target_date, "graded": 0, "results": []}

    latest_by_sport = {}
    for k, v in day_snaps.items():
        sp = v.get("sport", "")
        if sp not in latest_by_sport or v.get("timestamp", "") > latest_by_sport[sp].get("timestamp", ""):
            latest_by_sport[sp] = v

    graded_results = []
    for sport, snap in latest_by_sport.items():
        log(f"Grading {sport} game lines: {len(snap.get('picks', []))} picks from {snap.get('timestamp')}")
        for p in snap.get("picks", []):
            matchup = p.get("matchup", "")
            home, away = p.get("home", ""), p.get("away", "")
            market, pick, line = p.get("market", ""), p.get("pick", ""), p.get("line", 0)
            try:
                outcome, home_score, away_score = resolve_actual_game_result_for_grading(
                    matchup, home, away, sport, market, pick, line, target_date
                )
            except Exception as e:
                log(f"  resolve error for {matchup}/{market}: {e}")
                outcome, home_score, away_score = None, None, None

            if outcome is None:
                outcome = "UNGRADABLE"

            graded_results.append({
                "date": target_date, "sport": sport, "matchup": matchup,
                "market": market, "pick": pick, "line": line, "outcome": outcome,
                "home_score": home_score, "away_score": away_score,
                "edge": p.get("edge", 0), "tier": p.get("tier", ""), "source": "board_grading",
            })

    grading_history = gist_read(token, GAME_GRADING_FILE) or {}
    grading_history[target_date] = graded_results
    cutoff = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    grading_history = {k: v for k, v in grading_history.items() if k >= cutoff}
    gist_write(token, GAME_GRADING_FILE, grading_history)

    graded_n = sum(1 for r in graded_results if r["outcome"] != "UNGRADABLE")
    wins = sum(1 for r in graded_results if r["outcome"] == "WIN")
    losses = sum(1 for r in graded_results if r["outcome"] == "LOSS")
    log(f"Done: {len(graded_results)} total game-line picks, {graded_n} gradable "
        f"({len(graded_results) - graded_n} ungradable), {wins}W-{losses}L")
    return {"date": target_date, "total": len(graded_results), "graded": graded_n, "wins": wins, "losses": losses}


def main():
    target_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    log(f"Grading board for {target_date}")
    grade_day(target_date)
    grade_game_day(target_date)


if __name__ == "__main__":
    main()
