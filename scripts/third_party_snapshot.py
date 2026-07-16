"""
third_party_snapshot.py — daily snapshot of comparison-source picks, for backtesting
================================================================================

Stage 1 of 2 (see third_party_backtest.py for stage 2 — grading).

Every comparison source added to the New Bettor tab / Player Lookup this
session (FavoredProps, DraftEdge, Dimers) is currently display-only —
none of them are wired into compute_multi_signal_edge. To find out
whether any of them are actually predictive enough to justify wiring in,
this snapshots each source's picks daily; third_party_backtest.py grades
yesterday's snapshot the next day using the exact same ground-truth
resolvers (resolve_actual_stat_for_grading / resolve_actual_game_result_
for_grading) that already grade BetCouncil's own board every day.

Scope, stated plainly rather than overclaimed: only sources with their
own persisted Gist harvester (FavoredProps, DraftEdge, Dimers) are
snapshotted here. BettingPros/Covers/DK-Most-Bet are fetched live inside
the running Streamlit app (no standalone Gist file a GitHub Actions job
can read on its own), and LineStar/Situational-Splits/NBA-Trailing-Splits
aren't "picks" at all — they're context stats with no win/loss to grade
against. Backtesting those would need either a dedicated harvester built
first (for the live-fetch sources) or a completely different validation
approach (a feature-correlation study, not a hit-rate grade, for the
context-stat sources). Not attempted here — scoped honestly to what's
actually gradable with what already exists.

This script only reads existing source Gist files and writes a snapshot
history file. It never touches compute_multi_signal_edge, SEM, or any
signal weight — promoting a source from "backtested" to "live signal"
is a separate, explicit, human decision, not something this pipeline
does on its own.
"""

import json
import os
import sys
from datetime import date, timedelta

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SNAPSHOT_FILE = "betcouncil_third_party_snapshots.json"
SPORTS = ["MLB", "NBA", "NHL", "WNBA", "NFL"]


def log(msg: str) -> None:
    print(f"[third_party_snapshot] {msg}", flush=True)


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
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {filename: {"content": json.dumps(payload)}}},
        timeout=30,
    )
    return resp.status_code in (200, 201)


def snapshot_favoredprops(today: str) -> list:
    records = []
    for sport in SPORTS:
        for kind in ("dfs", "sportsbook"):
            data = gist_read(f"betcouncil_favoredprops_{kind}_{sport}.json")
            if not data:
                continue
            for row in data.get("props", []):
                bet = str(row.get("bet", "")).upper()
                side = "OVER" if bet.startswith("O") else ("UNDER" if bet.startswith("U") else None)
                if not (row.get("player") and row.get("stat_type") and row.get("line") is not None and side):
                    continue
                records.append({
                    "source": "favoredprops", "sport": sport, "player": row["player"],
                    "prop_type": row["stat_type"], "line": row["line"], "side": side,
                    "implied_prob": row.get("avg_pr"),
                })
    return records


def snapshot_draftedge(today: str) -> list:
    records = []
    for sport in SPORTS:
        data = gist_read(f"betcouncil_draftedge_{sport}.json")
        if not data:
            continue
        for row in data.get("props", []):
            player = row.get("Player") or row.get("name")
            if not player:
                continue
            # MLB shape: per-stat sections (HitsSection/HRSection/etc), each
            # with a Line + implied over/under if the book line is present.
            for stat_name, section_key in [("Hits", "HitsSection"), ("HR", "HRSection"),
                                            ("RBI", "RBISection"), ("TB", "TBSection"),
                                            ("SB", "SBSection")]:
                sec = row.get(section_key)
                if not isinstance(sec, dict) or sec.get("Line") is None:
                    continue
                implied_over = sec.get("Implied_Over")
                side = "OVER" if (implied_over or 0) >= 0.5 else "UNDER"
                records.append({
                    "source": "draftedge", "sport": sport, "player": player,
                    "prop_type": stat_name, "line": sec["Line"], "side": side,
                    "implied_prob": implied_over,
                })
    return records


def snapshot_dimers(today: str) -> list:
    records = []
    for sport in SPORTS:
        data = gist_read(f"betcouncil_dimers_{sport}.json")
        if not data:
            continue
        for dm in data.get("matches", []):
            match_meta = dm.get("match", {})
            home = match_meta.get("HomeTeam", {})
            away = match_meta.get("AwayTeam", {})
            home_abv = home.get("Abv", "") if isinstance(home, dict) else ""
            away_abv = away.get("Abv", "") if isinstance(away, dict) else ""
            if not (home_abv and away_abv):
                continue
            tab = dm.get("betting", {}).get("tab", {})
            h_edge, a_edge = tab.get("HomeH2HEdge"), tab.get("AwayH2HEdge")
            if not (isinstance(h_edge, (int, float)) and isinstance(a_edge, (int, float))):
                continue
            side = "HOME" if h_edge > a_edge else "AWAY"
            records.append({
                "source": "dimers", "sport": sport, "matchup": f"{away_abv} @ {home_abv}",
                "home": home_abv, "away": away_abv, "market": "MONEYLINE", "pick": side,
                "line": 0, "implied_prob": tab.get("HomeLineWinPct") if side == "HOME" else tab.get("AwayLineWinPct"),
            })
    return records


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    today = date.today().isoformat()
    props_records = snapshot_favoredprops(today) + snapshot_draftedge(today)
    game_records = snapshot_dimers(today)

    log(f"FavoredProps+DraftEdge props: {len(props_records)} | Dimers games: {len(game_records)}")

    history = gist_read(SNAPSHOT_FILE) or {}
    history[today] = {"props": props_records, "games": game_records}
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    history = {k: v for k, v in history.items() if k >= cutoff}

    ok = gist_write(token, SNAPSHOT_FILE, history)
    log("Snapshot pushed" if ok else "Snapshot push FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
