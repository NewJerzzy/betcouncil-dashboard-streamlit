"""
evsharps_refresh.py — EVSharps full props board scraper
=========================================================
Hits the unauthenticated Railway API behind evsharps.com for ALL prop
types (pitcher strikeouts, walks, hitter props, etc.):

  https://api-production-3a3b.up.railway.app/api/mlb
  https://api-production-3a3b.up.railway.app/api/nba   (in-season only)
  https://api-production-3a3b.up.railway.app/api/nfl   (in-season only)

Each endpoint returns:
  - games:  list of game slugs ("stl @ tor")
  - times:  {game_slug: ISO datetime}
  - props:  list of prop type names available
  - data:   list of prop entries (player, prop, handicap, bookOdds, ev, fairVal, etc.)

Book keys in bookOdds:
  kal=Kalshi  fd=FanDuel  dk=DraftKings  hr=HardRock  hr_oh=HardRock(OH)
  bv=Bovada   br=BetRivers  fn=Fanatics  mgm=BetMGM  cz=Caesars
  fl=Fliff    re=BetRivers(alt)  bol=BetOnline  nv=Novig  circa=Circa
  espn=ESPN/theScore  pn=Pinnacle  kambi=Kambi  px=ProphetX

NOTE: For HR-specific EV analysis (more books, fair value, Kelly), see
evsharps_dingers_harvester.py which hits /api/ev specifically.

Pushes:
  betcouncil_evsharps_props_MLB.json
  betcouncil_evsharps_props_NBA.json   (skipped if no data)
  betcouncil_evsharps_props_NFL.json   (skipped if no data)
"""

import gzip
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

API_BASE = "https://api-production-3a3b.up.railway.app"

# Dead files we can rename at the 300-file cap.
# Map: new_filename → dead_filename_to_rename
DEAD_FILE_MAP = {
    "betcouncil_evsharps_props_MLB.json": "betcouncil_locks.json",
    "betcouncil_evsharps_props_NBA.json": "betcouncil_elo_nba.json",
    "betcouncil_evsharps_props_NFL.json": "betcouncil_elo_processed_nba.json",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.evsharps.com/",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}

# Book abbreviation → canonical display name
BOOK_NAMES = {
    "kal":   "Kalshi",
    "fd":    "FanDuel",
    "dk":    "DraftKings",
    "hr":    "HardRock",
    "hr_oh": "HardRock(OH)",
    "bv":    "Bovada",
    "br":    "BetRivers",
    "fn":    "Fanatics",
    "mgm":   "BetMGM",
    "cz":    "Caesars",
    "fl":    "Fliff",
    "re":    "BetRivers",
    "bol":   "BetOnline",
    "nv":    "Novig",
    "circa": "Circa",
    "espn":  "ESPN Bet",
    "pn":    "Pinnacle",
    "kambi": "Kambi",
    "px":    "ProphetX",
}

SPORT_PATHS = {
    "MLB": "mlb",
    "NBA": "nba",
    "NFL": "nfl",
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


def normalize_entry(entry: dict, sport: str) -> dict:
    """Normalize one /api/{sport} data entry into a flat, app-friendly dict."""
    book_odds_raw = entry.get("bookOdds", {})
    # Expand abbreviated book names in the odds dict
    book_odds = {BOOK_NAMES.get(k, k): v for k, v in book_odds_raw.items() if v}
    links_raw = entry.get("links", {})
    links = {BOOK_NAMES.get(k, k): v for k, v in links_raw.items() if v}
    return {
        "sport":          sport,
        "dt":             entry.get("dt", ""),
        "player":         entry.get("player", ""),
        "prop":           entry.get("prop", ""),
        "handicap":       entry.get("handicap", ""),
        "game":           entry.get("game", ""),
        "team":           entry.get("team", ""),
        "opp":            entry.get("opp", ""),
        "opp_rank":       entry.get("oppRank"),
        "pos":            entry.get("pos", ""),
        "batting_order":  entry.get("order"),
        "bats":           entry.get("bats", ""),
        "pitcher":        entry.get("pitcher", ""),
        "pitcher_hand":   entry.get("pitcherLR", ""),
        "under":          entry.get("under", False),
        "book":           entry.get("book", ""),
        "line":           entry.get("line"),
        "ou":             entry.get("ou", ""),        # "over/under" combined odds
        "book_odds":      book_odds,
        "fair_val":       entry.get("fairVal"),        # devigged fair price
        "ev_pct":         entry.get("ev"),             # EV%
        "implied":        entry.get("implied"),
        "kelly":          entry.get("kelly"),
        "hit_rates":      entry.get("hitRates", {}),  # szn/lyr/L5/L10/L20
        "logs":           entry.get("logs", []),       # game-by-game history
        "bpp":            entry.get("bpp", ""),
        "bpp_proj":       entry.get("bppProj"),
        "bpp_diff":       entry.get("bppDiff"),
        "stadium_rank":   entry.get("stadiumRank"),
        "roof":           entry.get("roof", False),
        "weather":        entry.get("weather", {}),
        "savant":         entry.get("savant", {}),
        "pitcher_data":   entry.get("pitcherData", {}),
        "batter_percs":   entry.get("batter_percs", {}),
        "bvp":            entry.get("bvp", ""),
        "links":          links,
    }


def push_to_gist(filename: str, payload: dict) -> bool:
    """
    Push payload to gist. If the file doesn't exist yet (gist at 300-file cap),
    rename a dead file to the target filename atomically via PATCH rename.
    """
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False

    content = json.dumps(payload, indent=2)
    gist_headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
    }

    # Try direct upsert first (works when file already exists or gist < 300 files)
    body = json.dumps({"files": {filename: {"content": content}}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=body, method="PATCH", headers=gist_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status == 200:
                return True
    except urllib.error.HTTPError as e:
        if e.code == 409:
            # 409 = gist update conflict (another update in-flight or <1s between writes)
            # Retry once after a brief pause
            import time as _time
            _time.sleep(3)
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(
                        f"https://api.github.com/gists/{GIST_ID}",
                        data=body, method="PATCH", headers=gist_headers,
                    ), timeout=20
                ) as r2:
                    return r2.status == 200
            except Exception as _e:
                log(f"Gist retry failed: {_e}")
                return False
        if e.code != 422:
            log(f"Gist PATCH error {e.code}: {e.read().decode()[:200]}")
            return False
        # 422 = Unprocessable Entity — likely at cap and file doesn't exist yet
        log(f"Gist at cap; attempting rename of dead file → {filename}")

    # Rename approach: rename a known dead file to the new target filename
    dead = DEAD_FILE_MAP.get(filename)
    if not dead:
        log(f"No dead file mapping for {filename} — cannot create new gist file at cap")
        return False

    rename_body = json.dumps({
        "files": {dead: {"filename": filename, "content": content}}
    }).encode()
    req2 = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=rename_body, method="PATCH", headers=gist_headers,
    )
    try:
        with urllib.request.urlopen(req2, timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        log(f"Gist rename error {e.code}: {e.read().decode()[:200]}")
        return False


def run_sport(sport: str) -> bool:
    path = SPORT_PATHS[sport]
    log(f"Fetching EVSharps props board for {sport} ...")

    try:
        data = fetch_json(f"{API_BASE}/api/{path}")
    except Exception as e:
        log(f"  ERROR fetching /api/{path}: {e}")
        return False

    # Some sport endpoints return [] directly (off-season), others return a dict
    if isinstance(data, list):
        raw_entries = data
    else:
        raw_entries = data.get("data", [])
    if not raw_entries:
        log(f"  {sport}: no entries returned (off-season or API between refreshes)")
        return True  # not a hard failure

    entries = [normalize_entry(e, sport) for e in raw_entries]

    # Summary
    prop_types = sorted({e["prop"] for e in entries})
    ev_pos = [e for e in entries if (e.get("ev_pct") or -99) > 0]
    books_seen = set()
    for e in entries:
        books_seen.update(e.get("book_odds", {}).keys())

    log(f"  {sport}: {len(entries)} props, {len(ev_pos)} +EV, "
        f"props={prop_types}, books={sorted(books_seen)}")

    payload = {
        "updated":       datetime.now(timezone.utc).isoformat(),
        "sport":         sport,
        "source":        f"evsharps.com (api/{path})",
        "api_updated":   data.get("updated", {}),
        "games":         data.get("games", []),
        "times":         data.get("times", {}),
        "prop_types":    prop_types,
        "total_entries": len(entries),
        "positive_ev":   len(ev_pos),
        "books":         sorted(books_seen),
        "entries":       entries,
    }

    filename = f"betcouncil_evsharps_props_{sport}.json"
    if push_to_gist(filename, payload):
        log(f"  Pushed {filename} — {len(entries)} entries")
        return True
    else:
        log(f"  ERROR: Gist push failed for {filename}")
        return False


def run() -> None:
    ok = True
    for sport in ["MLB", "NBA", "NFL"]:
        if not run_sport(sport):
            ok = False
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    run()
