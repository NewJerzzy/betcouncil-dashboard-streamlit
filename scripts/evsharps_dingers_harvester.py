"""
evsharps_dingers_harvester.py — EVSharps HR prop EV scraper
=============================================================
Hits the unauthenticated Railway API behind evsharps.com/dingers:
  https://api-production-3a3b.up.railway.app/api/ev?sport=mlb

Returns per-player HR props with:
  - Book odds across b365, bv, dk, fd, fn, hr_oh (Hard Rock), px (ProphetX)
  - Pre-computed fair value, EV %, Kelly fraction, implied probability
  - Full batter Statcast percentiles (barrel%, hard-hit%, flyball%, exit velo)
  - Pitcher Statcast (xwOBA, barrel allowed, flyball%)
  - Stadium HR rank (L/R splits), weather, batting order
  - Odds chart (timestamp-level line movement history)
  - Hit rates: season, last year, L5/L10/L20

Unique value: EVSharps already devig's across books and computes fair value.
Their fairVal + EV can validate / supplement BetCouncil's own HR prop model.

Pushes:  betcouncil_evsharps_dingers_MLB.json
"""

import gzip
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

API_BASE = "https://api-production-3a3b.up.railway.app"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.evsharps.com/dingers",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return json.loads(raw)


def normalize_entry(entry: dict) -> dict:
    """
    Normalize one /api/ev data entry into a flat, app-friendly dict.
    Preserves all high-value fields; strips oddsChart (large, less useful).
    """
    return {
        "player":        entry.get("player", ""),
        "game":          entry.get("game", ""),
        "team":          entry.get("team", ""),
        "opp":           entry.get("opp", ""),
        "opp_rank":      entry.get("oppRank"),
        "pos":           entry.get("pos", ""),
        "prop":          entry.get("prop", "hr"),
        "handicap":      entry.get("handicap", "0.5"),
        "ou":            entry.get("ou", ""),          # "344/-525" format
        "bats":          entry.get("bats", ""),
        "pitcher":       entry.get("pitcher", ""),
        "pitcher_hand":  entry.get("pitcherLR", ""),
        "batting_order": entry.get("order"),
        "book":          entry.get("book", ""),        # best-value book
        "line":          entry.get("line"),             # best-value odds
        "book_odds":     entry.get("bookOdds", {}),    # all books
        "fair_val":      entry.get("fairVal"),          # devigged fair price
        "ev_pct":        entry.get("ev"),               # EV% vs best book
        "implied":       entry.get("implied"),          # implied prob %
        "kelly":         entry.get("kelly"),
        "stadium_rank":  entry.get("stadiumRank"),
        "stadium_rank_l": entry.get("stadiumRankLeft"),
        "stadium_rank_r": entry.get("stadiumRankRight"),
        "weather":       entry.get("weather", {}),
        "hit_rates":     entry.get("hitRates", {}),    # szn/lyr/L5/L10/L20
        "batter_percs":  entry.get("batter_percs", {}),# HR percentiles
        "percs":         entry.get("percs", {}),        # pitcher HR percs
        "savant":        entry.get("savant", {}),       # full Statcast
        "pitcher_data":  entry.get("pitcherData", {}), # pitcher Statcast
        "player_factor": entry.get("playerFactor"),
        "bvp":           entry.get("bvp", ""),
        "last_hr":       entry.get("lastHR", ""),
        "homer_logs":    entry.get("homerLogs", {}),
        "logs":          entry.get("logs", []),         # G-by-G HR history
        "links":         entry.get("links", {}),        # deep-link bet URLs
        "dt":            entry.get("dt", ""),
    }


def push_to_gist(key: str, payload: dict) -> bool:
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False
    body = json.dumps({"files": {key: {"content": json.dumps(payload, indent=2)}}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept":        "application/vnd.github.v3+json",
            "Content-Type":  "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status == 200


def run() -> None:
    log("Fetching EVSharps dingers (HR props) ...")
    try:
        data = fetch_json(f"{API_BASE}/api/ev?sport=mlb")
    except Exception as e:
        log(f"ERROR fetching /api/ev: {e}")
        sys.exit(1)

    raw_entries = data.get("data", [])
    if not raw_entries:
        log("No entries returned — API may be between refreshes")
        sys.exit(0)

    entries = [normalize_entry(e) for e in raw_entries]

    # Summary stats for quick health-check
    ev_pos = [e for e in entries if (e.get("ev_pct") or -99) > 0]
    books_seen = set()
    for e in entries:
        books_seen.update(e.get("book_odds", {}).keys())

    log(f"  {len(entries)} players, {len(ev_pos)} positive-EV, books: {sorted(books_seen)}")

    payload = {
        "updated":        datetime.now(timezone.utc).isoformat(),
        "sport":          "MLB",
        "prop":           "hr",
        "source":         "evsharps.com/dingers",
        "api_updated":    data.get("updated", {}),
        "games":          data.get("games", []),
        "total_entries":  len(entries),
        "positive_ev":    len(ev_pos),
        "books":          sorted(books_seen),
        "entries":        entries,
    }

    key = "betcouncil_evsharps_dingers_MLB.json"
    if push_to_gist(key, payload):
        log(f"Pushed {key} — {len(entries)} entries, {len(ev_pos)} +EV")
    else:
        log("Gist push failed")
        sys.exit(1)


if __name__ == "__main__":
    run()
