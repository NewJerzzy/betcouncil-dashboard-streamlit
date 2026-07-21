"""
sackmann_tennis_refresh.py — ATP + WTA per-player season stats.

================================================================================
Source: Jeff Sackmann / Tennis Abstract's tennis_atp and tennis_wta GitHub
repos (github.com/JeffSackmann/tennis_atp, github.com/JeffSackmann/tennis_wta).
Confirmed live this session (not assumed from documentation):
  - atp_matches_2025.csv exists, 2,945 lines / 603 KB of real match data
  - atp_matches_2026.csv also exists (current season, in progress)
  - WTA repo uses an identical column schema (confirmed directly from
    wta_matches_2023.csv's real header + data rows)
  - raw.githubusercontent.com serves these files with ZERO authentication
    required, for any public repo -- no GitHub token needed at all,
    regardless of that token's scopes. An earlier investigation assumed a
    repo-scoped PAT was required and that the 2025 file didn't exist yet;
    both of those were checked directly and found incorrect.

LICENSE: Creative Commons Attribution-NonCommercial-ShareAlike 4.0
International (CC BY-NC-SA 4.0). Attribution required, non-commercial use
only. Per the repo's own README: "I'm serious about the license... if
violations continue, I may stop updating the repo entirely." This script
is used for personal betting research (BetCouncil), not resale of the
underlying data -- keep it that way. Attribution: Jeff Sackmann /
Tennis Abstract (http://www.tennisabstract.com/), based on a work at
https://github.com/JeffSackmann.

WHAT THIS BUILDS: per-player, per-tour SEASON AVERAGES (aces, double
faults, first-serve %, break points saved %, etc.) aggregated across all
of that player's matches this season, from both the winner_* and loser_*
columns of every match row they appear in. Match-level data, not live
in-tournament data -- updates once a match result is posted, not
mid-match.

Pushes to betcouncil_tennis_sackmann_ATP.json / _WTA.json.
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

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://raw.githubusercontent.com/JeffSackmann"

# Both current-season files -- 2026 may 404 early in the year before
# Sackmann has posted it yet; handled gracefully, not fatal.
YEARS = [2025, 2026]

TOURS = {
    "ATP": {"repo": "tennis_atp", "prefix": "atp_matches"},
    "WTA": {"repo": "tennis_wta", "prefix": "wta_matches"},
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
    repo = TOURS[tour]["repo"]
    prefix = TOURS[tour]["prefix"]
    url = f"{BASE_URL}/{repo}/master/{prefix}_{year}.csv"
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
        except Exception as e:
            DEBUG_LOG.append({"tour": tour, "year": year, "url": url, "attempt": attempt + 1, "error": str(e)})
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return None
        DEBUG_LOG.append({"tour": tour, "year": year, "url": url, "status": r.status_code, "bytes": len(r.content)})
        if r.status_code == 404:
            # Expected for a not-yet-started season or a not-yet-posted
            # file -- not an error, just nothing to aggregate this year.
            return None
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
    for attempt in range(3):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 2:
            base_wait = 10 * (2 ** attempt)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/3)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

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
