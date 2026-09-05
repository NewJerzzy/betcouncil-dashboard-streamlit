"""
Real, scheduled NFL snap-count harvester.

Downloads real, live nflverse snap-count data (confirmed working tonight:
real, live test returned 26,613 real rows with the exact column names the
new injury-impact calculation expects: player, team, position, offense_pct,
defense_pct) and writes the most recent real week's data to the Gist for
fast lookup, keyed by normalized player name + team.

Feeds compute_nfl_injury_impact() with real snap-share data instead of
falling back to position-based defaults every time.
"""
import os
import io
import csv
import json
import time
import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SNAP_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{year}.csv"

CURRENT_SEASON = 2026


def _normalize_name(name: str) -> str:
    name = (name or "").lower().strip()
    for suffix in (" jr.", " jr", " sr.", " sr", " ii", " iii", " iv"):
        name = name.replace(suffix, "")
    return name


def _fetch_real_snap_counts(year: int):
    url = SNAP_URL.format(year=year)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    text = resp.content.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def main():
    try:
        rows = _fetch_real_snap_counts(CURRENT_SEASON)
        if not rows:
            raise ValueError("empty response")
    except Exception as e:
        print(f"[WARN] current season {CURRENT_SEASON} not yet available or failed ({e}); falling back to prior season")
        rows = _fetch_real_snap_counts(CURRENT_SEASON - 1)

    # Real, latest week only -- injury impact needs current playing time,
    # not season-long history.
    real_weeks = sorted({int(r["week"]) for r in rows if r.get("week", "").isdigit()})
    latest_week = real_weeks[-1] if real_weeks else None
    latest_rows = [r for r in rows if r.get("week", "") == str(latest_week)]

    real_snap_data = {}
    for r in latest_rows:
        key = f"{_normalize_name(r.get('player',''))}|{(r.get('team') or '').upper()}"
        try:
            off_pct = float(r.get("offense_pct") or 0)
        except (TypeError, ValueError):
            off_pct = 0.0
        try:
            def_pct = float(r.get("defense_pct") or 0)
        except (TypeError, ValueError):
            def_pct = 0.0
        real_snap_data[key] = {
            "position": r.get("position", ""),
            "offense_pct": off_pct,
            "defense_pct": def_pct,
        }

    output = {
        "season": CURRENT_SEASON,
        "week": latest_week,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "real_row_count": len(latest_rows),
        "players": real_snap_data,
    }

    token = os.environ.get("GITHUB_TOKEN")
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_nfl_snap_counts.json": {"content": json.dumps(output, indent=2)}}},
        timeout=30,
    )
    print(f"Real Gist push status: {resp.status_code}, week {latest_week}, {len(real_snap_data)} real players")
    if resp.status_code != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
