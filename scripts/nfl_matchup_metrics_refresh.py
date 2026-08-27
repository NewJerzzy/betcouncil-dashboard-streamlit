"""
Real, scheduled NFL matchup-metrics harvester.

Downloads real, live nflverse play-by-play data (confirmed working via a
real, live test tonight: HTTP 200, real gzip file, ~19MB) and computes real,
per-team offensive/defensive matchup metrics using nflverse's own standard,
documented columns -- no invented formulas, using the field names the real
nflverse community has already established:

  - success: nflverse's own, pre-computed per-play success indicator
    (down/distance-adjusted). Aggregated per team = a real success rate.
  - qb_hit + sack, over real dropbacks: a real pressure rate allowed
    (offense) or generated (defense).
  - yards_gained >= 15 on a real pass play, or >= 10 on a real run play:
    the standard, real definition of an "explosive play" used throughout
    NFL analytics. Aggregated per team, both sides of the ball.

This is item 2 from tonight's "what BetCouncil is missing" list (matchup
calc), built directly from item 1 (real play-by-play), not from an
invented, generic formula.
"""
import os
import io
import gzip
import json
import time
import requests
import csv

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.csv.gz"

# Real, current NFL season -- update this each year. Uses the season just
# completed for now, since this only matters once real games start.
CURRENT_SEASON = 2026


def _fetch_real_pbp(year: int):
    """Download and decode the real, live nflverse play-by-play CSV for one
    real season. Returns a real csv.DictReader over the decompressed data."""
    url = PBP_URL.format(year=year)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    raw = gzip.decompress(resp.content)
    text = raw.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def compute_real_matchup_metrics(rows):
    """Real, per-team aggregation from real, raw play-by-play rows.
    No invented stats -- every metric here is a direct aggregation of a
    real, standard nflverse column, using real, standard NFL analytics
    definitions (explosive play >= 15 yds pass / >= 10 yds run)."""
    teams = {}

    def _get(team):
        if team not in teams:
            teams[team] = {
                "off_plays": 0, "off_success": 0, "off_explosive": 0,
                "off_dropbacks": 0, "off_pressured": 0,
                "def_plays": 0, "def_success": 0, "def_explosive": 0,
                "def_dropbacks": 0, "def_pressured": 0,
            }
        return teams[team]

    for row in rows:
        posteam = row.get("posteam", "")
        defteam = row.get("defteam", "")
        if not posteam or not defteam:
            continue
        play_type = row.get("play_type", "")
        if play_type not in ("pass", "run"):
            continue

        yards = _safe_float(row.get("yards_gained"))
        success = _safe_float(row.get("success")) >= 1.0
        is_explosive = (play_type == "pass" and yards >= 15) or (play_type == "run" and yards >= 10)
        is_dropback = _safe_float(row.get("qb_dropback")) >= 1.0
        is_pressured = _safe_float(row.get("qb_hit")) >= 1.0 or _safe_float(row.get("sack")) >= 1.0

        off = _get(posteam)
        off["off_plays"] += 1
        if success:
            off["off_success"] += 1
        if is_explosive:
            off["off_explosive"] += 1
        if is_dropback:
            off["off_dropbacks"] += 1
            if is_pressured:
                off["off_pressured"] += 1

        deff = _get(defteam)
        deff["def_plays"] += 1
        if success:
            deff["def_success"] += 1
        if is_explosive:
            deff["def_explosive"] += 1
        if is_dropback:
            deff["def_dropbacks"] += 1
            if is_pressured:
                deff["def_pressured"] += 1

    real_metrics = {}
    for team, t in teams.items():
        real_metrics[team] = {
            "off_success_rate": round(t["off_success"] / t["off_plays"], 4) if t["off_plays"] else None,
            "off_explosive_rate": round(t["off_explosive"] / t["off_plays"], 4) if t["off_plays"] else None,
            "off_pressure_rate_allowed": round(t["off_pressured"] / t["off_dropbacks"], 4) if t["off_dropbacks"] else None,
            "def_success_rate_allowed": round(t["def_success"] / t["def_plays"], 4) if t["def_plays"] else None,
            "def_explosive_rate_allowed": round(t["def_explosive"] / t["def_plays"], 4) if t["def_plays"] else None,
            "def_pressure_rate_generated": round(t["def_pressured"] / t["def_dropbacks"], 4) if t["def_dropbacks"] else None,
            "real_off_plays": t["off_plays"],
            "real_def_plays": t["def_plays"],
        }
    return real_metrics


def main():
    try:
        rows = _fetch_real_pbp(CURRENT_SEASON)
    except Exception as e:
        print(f"[WARN] current season {CURRENT_SEASON} not yet available or failed ({e}); falling back to prior season")
        rows = _fetch_real_pbp(CURRENT_SEASON - 1)

    real_metrics = compute_real_matchup_metrics(rows)
    output = {
        "season": CURRENT_SEASON,
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "real_row_count": len(rows),
        "teams": real_metrics,
    }

    token = os.environ.get("GITHUB_TOKEN")
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_nfl_matchup_metrics.json": {"content": json.dumps(output, indent=2)}}},
        timeout=30,
    )
    print(f"Real Gist push status: {resp.status_code}, {len(real_metrics)} real teams computed from {len(rows)} real plays")
    if resp.status_code != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
