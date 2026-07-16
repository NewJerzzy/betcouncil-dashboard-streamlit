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

Scope, stated plainly rather than overclaimed: FavoredProps/DraftEdge/
Dimers read their own persisted Gist harvester output directly.
BettingPros/Covers/DK-Most-Bet don't have a persisted Gist file, but all
three already have standalone, session-independent fetch functions in
fetchers.py (no Streamlit dependency) — this script calls those
directly. DK Most Bet needed one extra step: its raw data embeds the
player name inside a "Market" text field with no clean separator from
the stat type, so it's matched against the player names already
collected from FavoredProps/DraftEdge in the same run, and skipped if no
match is found (no guessing). LineStar/Situational-Splits/NBA-Trailing-
Splits aren't "picks" at all — they're context stats with no win/loss to
grade against. Backtesting those needs a completely different validation
approach (a feature-correlation study, not a hit-rate grade) — not
attempted here.

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


def snapshot_covers(today: str) -> list:
    """
    fetch_covers_consensus(sport) -> {matchup_str: {away_pct, home_pct}}.
    Public betting %, not a model pick — treat the more-bet side as the
    "pick" for grading purposes (same convention used elsewhere for
    public-consensus sources), so it can still be graded against actual
    results even though it isn't really a prediction claim on Covers'
    part.
    """
    sys.path.insert(0, ".")
    from fetchers import fetch_covers_consensus

    records = []
    for sport in SPORTS:
        try:
            consensus = fetch_covers_consensus(sport)
        except Exception as e:
            log(f"  covers/{sport}: error — {e}")
            continue
        if not isinstance(consensus, dict):
            continue
        for matchup, pct in consensus.items():
            if not isinstance(pct, dict):
                continue
            home_pct, away_pct = pct.get("home_pct"), pct.get("away_pct")
            if not (isinstance(home_pct, (int, float)) and isinstance(away_pct, (int, float))):
                continue
            parts = matchup.replace(" @ ", " ").split(" ")
            teams = [t for t in parts if len(t) > 2]
            if len(teams) < 2:
                continue
            side = "HOME" if home_pct > away_pct else "AWAY"
            records.append({
                "source": "covers", "sport": sport, "matchup": matchup,
                "home": teams[-1], "away": teams[0], "market": "MONEYLINE", "pick": side,
                "line": 0, "implied_prob": max(home_pct, away_pct) / 100 if max(home_pct, away_pct) > 1 else max(home_pct, away_pct),
            })
    return records


def snapshot_bettingpros(today: str) -> list:
    """
    fetch_bettingpros_from_gist(sport) -> (data, source_tag). Exact field
    names for the "python_direct" path weren't verified live before this
    first deploy — parsed defensively; if the real shape differs this
    will just under-produce records rather than crash, and the next run's
    debug won't silently look identical since gradable count will show it.
    """
    sys.path.insert(0, ".")
    from fetchers import fetch_bettingpros_from_gist

    records = []
    for sport in SPORTS:
        try:
            data, _tag = fetch_bettingpros_from_gist(sport)
        except Exception as e:
            log(f"  bettingpros/{sport}: error — {e}")
            continue
        picks = data if isinstance(data, list) else data.get("picks", data.get("data", [])) if isinstance(data, dict) else []
        if not isinstance(picks, list):
            continue
        for p in picks:
            if not isinstance(p, dict):
                continue
            matchup = p.get("matchup") or p.get("event") or ""
            home = p.get("home_team") or p.get("home") or ""
            away = p.get("away_team") or p.get("away") or ""
            market = str(p.get("market_type") or p.get("market") or "").upper()
            pick = p.get("pick") or p.get("selection") or ""
            line = p.get("line", 0)
            if not (matchup and home and away and market and pick):
                continue
            records.append({
                "source": "bettingpros", "sport": sport, "matchup": matchup,
                "home": home, "away": away, "market": market, "pick": pick,
                "line": line, "implied_prob": p.get("consensus_pct") or p.get("win_pct"),
            })
    return records


def snapshot_dk_most_bet(today: str, known_players: set) -> list:
    """
    fetch_dk_most_bet_props returns {Event, EventDate, Market, Pick, Odds}
    where the player name is embedded inside "Market" text (e.g. "Kerry
    Carpenter Home Runs") with no clean separator from the stat type.
    Rather than guess-parse that, match against `known_players` — the
    player names already collected from FavoredProps/DraftEdge in this
    same run — and split on the matched name to recover the stat type.
    Anything that doesn't match a known player this same day is skipped
    rather than guessed at.
    """
    sys.path.insert(0, ".")
    from fetchers import fetch_dk_most_bet_props

    records = []
    for sport in SPORTS:
        try:
            rows = fetch_dk_most_bet_props(sport, max_rows=60)
        except Exception as e:
            log(f"  dk_most_bet/{sport}: error — {e}")
            continue
        for row in rows:
            market = row.get("Market", "")
            market_l = market.lower()
            matched_player = next((p for p in known_players if p.lower() in market_l), None)
            if not matched_player:
                continue
            prop_type = market_l.replace(matched_player.lower(), "").strip(" -:")
            pick_text = str(row.get("Pick", "")).upper()
            side = "OVER" if pick_text.startswith("O") else ("UNDER" if pick_text.startswith("U") else None)
            if not (prop_type and side):
                continue
            try:
                line = float("".join(c for c in pick_text if c.isdigit() or c == "."))
            except ValueError:
                continue
            records.append({
                "source": "dk_most_bet", "sport": sport, "player": matched_player,
                "prop_type": prop_type, "line": line, "side": side, "implied_prob": None,
            })
    return records


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    today = date.today().isoformat()
    debug_info = {"today": today, "steps": [], "error": None}

    try:
        fp_de_records = snapshot_favoredprops(today) + snapshot_draftedge(today)
        debug_info["steps"].append(f"favoredprops+draftedge: {len(fp_de_records)}")
        known_players = {r["player"] for r in fp_de_records if r.get("player")}

        dk_records = snapshot_dk_most_bet(today, known_players)
        debug_info["steps"].append(f"dk_most_bet: {len(dk_records)}")
        props_records = fp_de_records + dk_records

        dimers_records = snapshot_dimers(today)
        debug_info["steps"].append(f"dimers: {len(dimers_records)}")
        covers_records = snapshot_covers(today)
        debug_info["steps"].append(f"covers: {len(covers_records)}")
        bp_records = snapshot_bettingpros(today)
        debug_info["steps"].append(f"bettingpros: {len(bp_records)}")
        game_records = dimers_records + covers_records + bp_records
    except Exception as e:
        import traceback
        debug_info["error"] = f"{e}\n{traceback.format_exc()}"
        log(f"FATAL during snapshot collection: {e}")
        try:
            gist_write(token, "betcouncil_third_party_snapshot_debug.json", debug_info)
        except Exception:
            pass
        return 1

    by_source_props = {}
    for r in props_records:
        by_source_props[r["source"]] = by_source_props.get(r["source"], 0) + 1
    by_source_games = {}
    for r in game_records:
        by_source_games[r["source"]] = by_source_games.get(r["source"], 0) + 1
    log(f"Props by source: {by_source_props}")
    log(f"Games by source: {by_source_games}")
    debug_info["by_source_props"] = by_source_props
    debug_info["by_source_games"] = by_source_games

    history = gist_read(SNAPSHOT_FILE) or {}
    history[today] = {"props": props_records, "games": game_records}
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    history = {k: v for k, v in history.items() if k >= cutoff}

    ok = gist_write(token, SNAPSHOT_FILE, history)
    log("Snapshot pushed" if ok else "Snapshot push FAILED")
    gist_write(token, "betcouncil_third_party_snapshot_debug.json", debug_info)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
