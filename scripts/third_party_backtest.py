"""
third_party_backtest.py — grades yesterday's third-party snapshots, tracks calibration
================================================================================

Stage 2 of 2 (see third_party_snapshot.py for stage 1 — snapshotting).

Runs daily, one day after third_party_snapshot.py captured that day's
picks. Grades each snapshotted prop/game using the exact same resolvers
daily_board_grading.py already uses for BetCouncil's own board
(resolve_actual_stat_for_grading / resolve_actual_game_result_for_grading
in fetchers.py) — same ground truth, so results are directly comparable
to BetCouncil's own hit rate.

Accumulates a rolling per-source calibration record: total graded, W/L,
hit rate, and (where the source provided one) implied probability vs.
actual hit rate — the actual calibration check, not just win%. Pushes to
betcouncil_third_party_calibration.json.

This script only reads snapshots and writes calibration stats. It never
touches compute_multi_signal_edge, SEM, or any signal weight. Whether a
source's accumulated numbers justify wiring it in as a live signal is a
separate, explicit decision for a human to make by reading this file —
not something this script decides or does automatically. A source
looking good over a small sample is not the same as a source that should
immediately start moving edge calculations; that call stays outside this
pipeline on purpose.
"""

import json
import os
import sys
import time
from datetime import date, timedelta

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SNAPSHOT_FILE = "betcouncil_third_party_snapshots.json"
CALIBRATION_FILE = "betcouncil_third_party_calibration.json"


def log(msg: str) -> None:
    print(f"[third_party_backtest] {msg}", flush=True)


def gist_read(filename: str):
    resp = requests.get(f"https://api.github.com/gists/{GIST_ID}", timeout=20)
    if resp.status_code != 200:
        return None
    f = resp.json().get("files", {}).get(filename)
    if not f:
        return None
    content = f.get("content", "")
    if f.get("truncated") or not content:
        content = requests.get(f["raw_url"], timeout=20).text
    try:
        return json.loads(content) if content.strip() else None
    except json.JSONDecodeError:
        return None


def gist_write(token: str, filename: str, payload) -> bool:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"files": {filename: {"content": json.dumps(payload, indent=2)}}},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return True
        if resp.status_code in (403, 429, 409) and attempt < 4:
            wait = min(10 * (2 ** attempt), 90)
            log(f"  Gist write got {resp.status_code} -- retrying in {wait}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue
        return False
    return False


def grade_props(records: list, target_date: str) -> list:
    sys.path.insert(0, ".")
    from fetchers import resolve_actual_stat_for_grading

    graded = []
    for r in records:
        try:
            actual = resolve_actual_stat_for_grading(r["player"], r["sport"], r["prop_type"], target_date)
        except Exception as e:
            log(f"  resolve error {r.get('source')}/{r['player']}/{r['prop_type']}: {e}")
            actual = None

        if actual is None:
            outcome = "UNGRADABLE"
        elif actual == r["line"]:
            outcome = "PUSH"
        elif (actual > r["line"] and r["side"] == "OVER") or (actual < r["line"] and r["side"] == "UNDER"):
            outcome = "WIN"
        else:
            outcome = "LOSS"

        graded.append({**r, "date": target_date, "actual": actual, "outcome": outcome})
    return graded


def grade_games(records: list, target_date: str) -> list:
    sys.path.insert(0, ".")
    from fetchers import resolve_actual_game_result_for_grading

    graded = []
    for r in records:
        try:
            outcome, home_score, away_score = resolve_actual_game_result_for_grading(
                r["matchup"], r["home"], r["away"], r["sport"], r["market"], r["pick"], r["line"], target_date
            )
        except Exception as e:
            log(f"  resolve error {r.get('source')}/{r['matchup']}: {e}")
            outcome, home_score, away_score = None, None, None
        if outcome is None:
            outcome = "UNGRADABLE"
        graded.append({**r, "date": target_date, "outcome": outcome,
                        "home_score": home_score, "away_score": away_score})
    return graded


def update_calibration(calibration: dict, graded_props: list, graded_games: list) -> dict:
    all_graded = graded_props + graded_games
    by_source: dict = {}
    for r in all_graded:
        by_source.setdefault(r["source"], []).append(r)

    for source, rows in by_source.items():
        stats = calibration.setdefault(source, {
            "total": 0, "gradable": 0, "wins": 0, "losses": 0, "pushes": 0,
            "implied_probs": [], "actual_hit_flags": [], "first_seen": rows[0].get("date"),
        })
        for r in rows:
            stats["total"] += 1
            outcome = r["outcome"]
            if outcome == "UNGRADABLE":
                continue
            stats["gradable"] += 1
            if outcome == "WIN":
                stats["wins"] += 1
                stats["actual_hit_flags"].append(1)
            elif outcome == "LOSS":
                stats["losses"] += 1
                stats["actual_hit_flags"].append(0)
            elif outcome == "PUSH":
                stats["pushes"] += 1
            if isinstance(r.get("implied_prob"), (int, float)) and outcome in ("WIN", "LOSS"):
                stats["implied_probs"].append(r["implied_prob"])
        # keep only the flags/probs needed for a rolling calibration read —
        # cap list growth rather than let it grow unbounded forever
        stats["actual_hit_flags"] = stats["actual_hit_flags"][-2000:]
        stats["implied_probs"] = stats["implied_probs"][-2000:]

    for source, stats in calibration.items():
        flags = stats.get("actual_hit_flags", [])
        stats["actual_hit_rate"] = round(sum(flags) / len(flags), 4) if flags else None
        probs = stats.get("implied_probs", [])
        stats["avg_implied_prob"] = round(sum(probs) / len(probs), 4) if probs else None
        stats["sample_size_note"] = (
            "under 100 graded — too small to judge" if stats["gradable"] < 100
            else "100+ graded — enough to look at, still worth more data before any promotion decision"
        )

    return calibration


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    target_date = (date.today() - timedelta(days=1)).isoformat()
    snapshots = gist_read(SNAPSHOT_FILE) or {}
    day_snap = snapshots.get(target_date)
    if not day_snap:
        log(f"No snapshot found for {target_date} — nothing to grade yet.")
        return 0

    graded_props = grade_props(day_snap.get("props", []), target_date)
    graded_games = grade_games(day_snap.get("games", []), target_date)

    gradable_props = sum(1 for r in graded_props if r["outcome"] != "UNGRADABLE")
    gradable_games = sum(1 for r in graded_games if r["outcome"] != "UNGRADABLE")
    log(f"{target_date}: {gradable_props}/{len(graded_props)} props gradable, "
        f"{gradable_games}/{len(graded_games)} games gradable")

    calibration = gist_read(CALIBRATION_FILE) or {}
    calibration = update_calibration(calibration, graded_props, graded_games)

    ok = gist_write(token, CALIBRATION_FILE, calibration)
    log("Calibration pushed" if ok else "Calibration push FAILED")
    for source, stats in calibration.items():
        log(f"  {source}: {stats['gradable']} graded, hit rate {stats.get('actual_hit_rate')}, "
            f"{stats['sample_size_note']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
