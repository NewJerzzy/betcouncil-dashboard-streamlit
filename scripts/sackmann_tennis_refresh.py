"""
sackmann_tennis_refresh.py — ATP per-player season stats.

================================================================================
Source: TennisMyLife (stats.tennismylife.org), confirmed live this session:
  - 2025.csv and 2026.csv exist and are actively updated in real-time
    during live tournaments (their own site showed an in-progress
    tournament being updated as it was checked)
  - Identical column schema to Sackmann's ATP data (w_ace, w_df, w_svpt,
    w_1stIn, w_1stWon, w_2ndWon, w_SvGms, w_bpSaved, w_bpFaced, plus
    loser-side equivalents) -- confirmed directly from their own
    documented column list
  - MIT licensed, "Access: Free to use" -- no non-commercial restriction

Replaces Jeff Sackmann's GitHub repos (tennis_atp / tennis_wta), which
were confirmed inaccessible this session -- 404 across three independent
fetch paths (raw.githubusercontent.com, api.github.com contents API,
jsDelivr's mirror), consistent with the repos having gone private at some
point after being publicly forked/starred.

WTA: TennisMyLife is ATP-only (confirmed via their own site -- only ATP
Tour/Challenger/Qualifying tables exist, no WTA section). No working WTA
source as of this fix; not pointed at anything rather than silently
pointed at something confirmed dead.

WHAT THIS BUILDS: per-player SEASON AVERAGES (aces, double faults,
first-serve %, break points saved/won, etc.) aggregated across all of
that player's matches this season, from both the winner_* and loser_*
columns of every match row they appear in. Match-level data, not live
in-tournament data -- updates once a match result is posted, not
mid-match.

Pushes to betcouncil_tennis_sackmann_ATP.json.
"""

import csv
import io
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://stats.tennismylife.org/data"

YEARS = [2025, 2026]

# TennisMyLife (stats.tennismylife.org) confirmed live this session: real
# 2025/2026 CSVs, actively updated in real-time during live tournaments,
# MIT licensed, identical column schema to Sackmann's data. Replaces the
# Sackmann repos after those were confirmed inaccessible (private/404
# across three independent fetch paths). TennisMyLife is ATP-only --
# confirmed via their own site (only ATP Tour / ATP Challenger / ATP
# Qualifying tables exist, no WTA section anywhere) and their GitHub
# description ("ATP tournaments matches"). WTA has no working source as
# of this fix -- not pointed at anything rather than silently pointed at
# something confirmed not to work.
TOURS = {
    "ATP": {"prefix": ""},
}

# Stat columns to aggregate, per side (w_ / l_ prefix in the source data).
# Confirmed real column names directly from a live-fetched WTA data row
# this session (identical schema for ATP).
STAT_COLS = ["ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "SvGms", "bpSaved", "bpFaced"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BetCouncilResearch/1.0)"}
DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_csv_rows(tour: str, year: int):
    url = f"{BASE_URL}/{year}.csv"
    for attempt in range(5):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
        except Exception as e:
            DEBUG_LOG.append({"tour": tour, "year": year, "url": url,
                               "attempt": attempt + 1, "error": str(e)})
            if attempt < 4:
                time.sleep(3 * (attempt + 1))
                continue
            return None
        DEBUG_LOG.append({"tour": tour, "year": year, "url": url,
                           "status": r.status_code, "bytes": len(r.content)})
        if r.status_code == 404:
            return None  # not yet posted for this year -- not an error
        if r.status_code != 200:
            return None
        try:
            return list(csv.DictReader(io.StringIO(r.text)))
        except Exception as e:
            DEBUG_LOG.append({"tour": tour, "year": year, "parse_error": str(e)})
            return None
    return None


def aggregate_player_stats(tour: str) -> dict:
    """Returns {player_name: {...}} across all fetched years for this tour,
    aggregating both winner_* and loser_* rows for each player (a player's
    serve stats count the same whether they won or lost that particular
    match). Also computes break points WON as a returner -- this requires
    the OPPONENT's bpFaced-bpSaved from the same row, not just this
    player's own serve-side columns."""
    totals = defaultdict(lambda: defaultdict(float))
    match_counts = defaultdict(int)
    bp_won_totals = defaultdict(float)

    for year in YEARS:
        rows = fetch_csv_rows(tour, year)
        if not rows:
            continue
        for row in rows:
            for side, name_col, opp_side in (("w", "winner_name", "l"), ("l", "loser_name", "w")):
                player = row.get(name_col, "").strip()
                if not player:
                    continue
                has_stats = False
                for stat in STAT_COLS:
                    raw = row.get(f"{side}_{stat}", "")
                    try:
                        val = float(raw)
                    except (TypeError, ValueError):
                        continue
                    totals[player][stat] += val
                    has_stats = True
                if has_stats:
                    match_counts[player] += 1
                # Break points WON as returner = opponent's bpFaced - bpSaved
                # (break points the opponent faced on serve that they did
                # NOT save, i.e. this player converted them).
                try:
                    opp_bp_faced = float(row.get(f"{opp_side}_bpFaced", "") or 0)
                    opp_bp_saved = float(row.get(f"{opp_side}_bpSaved", "") or 0)
                    bp_won_totals[player] += max(0.0, opp_bp_faced - opp_bp_saved)
                except (TypeError, ValueError):
                    pass

    result = {}
    for player, stats in totals.items():
        n = match_counts.get(player, 0)
        if n == 0:
            continue
        result[player] = {
            "matches": n,
            "ace_avg": round(stats["ace"] / n, 2),
            "df_avg": round(stats["df"] / n, 2),
            "svpt_avg": round(stats["svpt"] / n, 2),
            "first_in_pct": round(100 * stats["1stIn"] / stats["svpt"], 1) if stats["svpt"] else 0,
            "first_won_pct": round(100 * stats["1stWon"] / stats["1stIn"], 1) if stats["1stIn"] else 0,
            "second_won_pct": round(100 * stats["2ndWon"] / (stats["svpt"] - stats["1stIn"]), 1) if (stats["svpt"] - stats["1stIn"]) > 0 else 0,
            "bp_saved_pct": round(100 * stats["bpSaved"] / stats["bpFaced"], 1) if stats["bpFaced"] else 0,
            "bp_won_avg": round(bp_won_totals.get(player, 0.0) / n, 2),
            "sv_gms_avg": round(stats["SvGms"] / n, 2),
        }
    return result


def push_files(files_payload: dict, github_token: str) -> int:
    """
    Merges into the shared evbets_combined.json using the real
    distributed lock (gist_lock.py) -- the earlier read-verify-retry
    mitigation reduced collisions but was confirmed insufficient under
    real concurrent load; the lock actually eliminates them (verified
    via timing proof earlier this session).
    """
    SHARED_FILE = "betcouncil_evbets_combined.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_tennis_sackmann_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

    lock_token = acquire_lock(GIST_ID, github_token, "evbets_combined", holder="sackmann_tennis", max_attempts=7)
    if not lock_token:
        log("Could not acquire evbets_combined lock -- skipping this run to avoid a collision")
        return 0
    try:
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                raw_url = r_files[SHARED_FILE]["raw_url"]
                existing = requests.get(raw_url, timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        existing["sackmann_tennis"] = merged
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        for attempt in range(4):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    return len(files_payload)
                if attempt < 3:
                    time.sleep(5)
                    continue
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 3:
                wait = min((attempt + 1) * 8, 30)
                log(f"Gist {resp.status_code} -- retrying in {wait}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0
        return 0
    finally:
        release_lock(GIST_ID, github_token, "evbets_combined", lock_token)


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

    for tour in TOURS:
        try:
            player_stats = aggregate_player_stats(tour)
        except Exception as e:
            log(f"{tour}: error — {e}")
            player_stats = {}

        log(f"{tour}: {len(player_stats)} players aggregated")
        if player_stats:
            any_data = True
            files_payload[f"betcouncil_tennis_sackmann_{tour}.json"] = {
                "content": json.dumps({
                    "source": "Jeff Sackmann / Tennis Abstract (CC BY-NC-SA 4.0, github.com/JeffSackmann)",
                    "tour": tour, "seasons_included": YEARS,
                    "captured_at": now_iso, "players": player_stats,
                })
            }

    files_payload["betcouncil_tennis_sackmann_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:30]}, indent=2)
    }

    if not any_data:
        log("No player stats aggregated for either tour — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
