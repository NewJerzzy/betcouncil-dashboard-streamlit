"""
baseballsavant_refresh.py — Baseball Savant Statcast leaderboards (public CSV, no auth)
================================================================================

baseballsavant.mlb.com — MLB's own public Statcast data site. Leaderboard
pages expose a `csv=true` query param that returns the underlying data as
CSV with no auth, no key — this is the same well-documented public export
mechanism the open-source `pybaseball` library scrapes.

REAL SCHEMA CONFIRMED (not guessed): a prior session manually pushed a real,
live pull of these 4 datasets straight to the Gist on 2026-07-18 without
committing any code. This script's parser is built directly against that
actual captured payload (256 batters / 367 pitchers / 544 sprint-speed
rows, verified field names below).

The endpoint URLs themselves are inferred from Baseball Savant's known,
stable, publicly-documented leaderboard CSV pattern (unauthenticated,
no sandbox verification possible — baseballsavant.mlb.com isn't in this
environment's network allowlist) — confirm on first live Actions run:

    GET /leaderboard/expected_statistics?type=batter&year={Y}&csv=true
        -> batter_xstats: {player_id, year, pa, bip, ba, est_ba,
           est_ba_minus_ba_diff, slg, est_slg, est_slg_minus_slg_diff,
           woba, est_woba, est_woba_minus_woba_diff, last_name, first_name}

    GET /leaderboard/statcast?type=batter&year={Y}&csv=true
        -> batter_statcast: {player_id, attempts, avg_hit_angle,
           anglesweetspotpercent, max_hit_speed, avg_hit_speed, ev50,
           fbld, gb, max_distance, avg_distance, avg_hr_distance,
           ev95plus, ev95percent, barrels, brl_percent, brl_pa,
           last_name, first_name}

    GET /leaderboard/statcast?type=pitcher&year={Y}&csv=true
        -> pitcher_statcast: same shape as batter_statcast (contact
           quality ALLOWED, not generated, when type=pitcher)

    GET /leaderboard/sprint_speed?year={Y}&csv=true
        -> sprint_speed: {player_id, team_id, team, position, age,
           competitive_runs, bolts, hp_to_1b, sprint_speed, last_name,
           first_name}

Pushes to betcouncil_baseballsavant_{dataset}.json, same filenames the
prior session's one-time push used (so any code already written against
those names keeps working). Cron every 6 hours, matching that session's
stated cadence — Statcast leaderboards update as games get logged, not
in real time, so 15-min polling would be wasteful.
"""

import csv
import io
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://baseballsavant.mlb.com/leaderboard"
YEAR = 2026

HEADERS = {
    "Accept": "text/csv,application/csv",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}

# (dataset_name, url, params, numeric_fields) — numeric_fields cast from
# CSV string to float/int; everything else stays a string. Matches the
# real captured sample's types (player_id/attempts/barrels are ints in
# the sample; percentages/speeds are floats).
DATASETS = [
    ("batter_xstats", f"{BASE_URL}/expected_statistics",
     {"type": "batter", "year": YEAR, "csv": "true"},
     {"player_id": int, "year": int, "pa": int, "bip": int,
      "ba": float, "est_ba": float, "est_ba_minus_ba_diff": float,
      "slg": float, "est_slg": float, "est_slg_minus_slg_diff": float,
      "woba": float, "est_woba": float, "est_woba_minus_woba_diff": float}),
    ("batter_statcast", f"{BASE_URL}/statcast",
     {"type": "batter", "year": YEAR, "csv": "true"},
     {"player_id": int, "attempts": int, "avg_hit_angle": float,
      "anglesweetspotpercent": float, "max_hit_speed": float, "avg_hit_speed": float,
      "ev50": float, "fbld": float, "gb": float, "max_distance": int,
      "avg_distance": int, "avg_hr_distance": int, "ev95plus": int,
      "ev95percent": float, "barrels": int, "brl_percent": float, "brl_pa": float}),
    ("pitcher_statcast", f"{BASE_URL}/statcast",
     {"type": "pitcher", "year": YEAR, "csv": "true"},
     {"player_id": int, "attempts": int, "avg_hit_angle": float,
      "anglesweetspotpercent": float, "max_hit_speed": float, "avg_hit_speed": float,
      "ev50": float, "fbld": float, "gb": float, "max_distance": int,
      "avg_distance": int, "avg_hr_distance": int, "ev95plus": int,
      "ev95percent": float, "barrels": int, "brl_percent": float, "brl_pa": float}),
    ("sprint_speed", f"{BASE_URL}/sprint_speed",
     {"year": YEAR, "csv": "true"},
     {"player_id": int, "team_id": int, "age": int, "competitive_runs": int,
      "bolts": int, "hp_to_1b": float, "sprint_speed": float}),
]

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_csv_rows(url: str, params: dict) -> list:
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    except Exception as e:
        DEBUG_LOG.append({"url": url, "params": params, "error": str(e)})
        return []
    DEBUG_LOG.append({"url": url, "params": params, "status": r.status_code,
                       "content_type": r.headers.get("content-type", ""),
                       "body_snippet": r.text[:300]})
    if r.status_code != 200:
        return []
    # Guard against a BOM at the start of the CSV (seen in the prior
    # session's debug notes — Baseball Savant's export includes one).
    text = r.text.lstrip("\ufeff")
    try:
        reader = csv.DictReader(io.StringIO(text))
        return [row for row in reader if row]
    except Exception as e:
        DEBUG_LOG.append({"url": url, "csv_parse_error": str(e)})
        return []


def cast_row(row: dict, numeric_fields: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k is None:
            continue  # guard against a trailing None key from a malformed CSV row
        k = k.strip()
        # Baseball Savant's CSV export combines the name into one column
        # literally titled "last_name, first_name" (comma inside the
        # header itself, a quoted CSV field) -- e.g. value "Wood, James".
        # First live run (2026-07-18) showed this passing through as one
        # raw string field instead of the separate last_name/first_name
        # keys the manually-captured sample had, which must have been
        # post-processed by whatever produced that sample. Split here so
        # the output matches the originally documented schema.
        if k == "last_name, first_name" and v:
            parts = [p.strip() for p in str(v).split(",", 1)]
            out["last_name"] = parts[0] if parts else None
            out["first_name"] = parts[1] if len(parts) > 1 else None
            continue
        if v is None or v == "":
            out[k] = None
            continue
        caster = numeric_fields.get(k)
        if caster:
            try:
                out[k] = caster(float(v)) if caster is int else caster(v)
            except (ValueError, TypeError):
                out[k] = None
        else:
            out[k] = v
    return out


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=60,
        )
        if resp.status_code in (200, 201):
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 4:
                wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                time.sleep(wait)
                continue
            if missing:
                log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                return len(files_payload) - len(missing)
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 4:
            base_wait = min(10 * (2 ** attempt), 90)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget for this shared token before
    doing any writes. With ~30 scripts sharing one token/Gist, the hourly
    5000-request budget can run dry during a busy stretch (confirmed real:
    2026-07-25 06:17-06:40 UTC, 403 'API rate limit exceeded for user ID').
    When that happens, skip this run cleanly (exit 0) instead of burning
    retries against an already-exhausted budget and getting flagged as a
    failure -- the next scheduled run picks the data back up once the
    hourly window resets."""
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} requests left this hour) -- skipping this run cleanly, next scheduled run will pick it up")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) -- proceeding anyway")
    return True


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for dataset, url, params, numeric_fields in DATASETS:
        rows = fetch_csv_rows(url, params)
        players = [cast_row(row, numeric_fields) for row in rows]
        log(f"  {dataset}: {len(players)} rows")
        if players:
            any_data = True
            files_payload[f"betcouncil_baseballsavant_{dataset}.json"] = {
                "content": json.dumps({
                    "source": "baseballsavant", "dataset": dataset, "year": YEAR,
                    "captured_at": now_iso, "total": len(players), "players": players,
                }, default=str)
            }

    files_payload["betcouncil_baseballsavant_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2, default=str)
    }

    if not any_data:
        log("No usable data captured across any dataset — see debug log")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("UNHANDLED EXCEPTION:\n" + tb)
        try:
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                push_files({"betcouncil_baseballsavant_debug.json": {
                    "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                            "error": "unhandled_exception", "traceback": tb}, indent=2)
                }}, token)
        except Exception:
            pass
        sys.exit(1)
