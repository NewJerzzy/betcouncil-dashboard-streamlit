"""
vsin_harvester.py — VSiN Vegas Line Tracker scraper
=====================================================
Scrapes https://data.vsin.com/vegas-odds-linetracker/?sportid={sport}
which serves server-rendered HTML (no JS needed, no login) containing
lines from 8 Nevada/major books per game:
  Table A: Circa, Boomers, BetMGM, Caesars
  Table B: Westgate, Stations, South Point, Wynn

Circa, Westgate, South Point, and Stations are Nevada sharp books not
available in OddsAPI or Unabated — this is the unique value here.

FALLBACK DETECTION: VSiN serves the MLB page for any unknown/off-season
sport ID. We detect this by checking if team names contain MLB clubs —
if so, the sport is skipped rather than pushing stale data.

Pushes one Gist file per active sport:  betcouncil_vsin_{SPORT}.json
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# All sports to attempt, ordered by priority.
# Active now: MLB, WNBA, UFC, Golf
# Seasonal: NFL, NBA, NHL, CFL, NCAAF, NCAAB — auto-populate when live.
# VSiN sport IDs are lowercase, matching their linetracker ?sportid= param.
SPORTS = {
    "MLB":   "mlb",
    "WNBA":  "wnba",
    "UFC":   "ufc",
    "Golf":  "golf",
    "NFL":   "nfl",
    "NBA":   "nba",
    "NHL":   "nhl",
    "CFL":   "cfl",
    "NCAAF": "ncaaf",
    "NCAAB": "ncaab",
}

# If VSiN doesn't recognise a sport ID it falls back to the MLB page.
# Detect this by checking whether parsed teams contain MLB franchise names.
MLB_TEAM_FRAGMENTS = {
    "yankees", "red sox", "blue jays", "rays", "orioles",
    "white sox", "guardians", "twins", "royals", "tigers",
    "astros", "mariners", "rangers", "angels", "athletics",
    "dodgers", "giants", "padres", "diamondbacks", "rockies",
    "mets", "phillies", "braves", "marlins", "nationals",
    "cubs", "cardinals", "brewers", "reds", "pirates",
}

BOOKS_A = ["Circa", "Boomers", "BetMGM", "Caesars"]
BOOKS_B = ["Westgate", "Stations", "South Point", "Wynn"]
ALL_BOOKS = BOOKS_A + BOOKS_B

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/125.0.0.0 Safari/537.36"),
    "Accept": "text/html,*/*",
    "Referer": "https://vsin.com/",
}


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_html(sport_id: str) -> str:
    url = f"https://data.vsin.com/vegas-odds-linetracker/?sportid={sport_id}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("latin-1")


def clean_row(raw_tr: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', raw_tr)
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def is_mlb_fallback(games: list, sport: str) -> bool:
    """Return True if VSiN is serving the MLB fallback for this sport."""
    if sport == "MLB" or not games:
        return False
    # Sample team names from first few games
    sample_names = []
    for g in games[:5]:
        sample_names.append(g.get("away_team", "").lower())
        sample_names.append(g.get("home_team", "").lower())
    hits = sum(
        1 for name in sample_names
        if any(frag in name for frag in MLB_TEAM_FRAGMENTS)
    )
    return hits >= 2


def parse_book_odds(tokens: list, offset: int, has_ou: bool) -> dict | None:
    """
    Parse one book's block from a token list starting at offset.

    Time/open rows:  [spr, rl_price, ml, total]           → 4 tokens
    Competitor rows: [spr, rl_price, ml, total, side, vig] → 6 tokens
    Dashes ("-") are kept as-is to signal that a book has no line posted.
    """
    try:
        count = 6 if has_ou else 4
        if offset + count > len(tokens):
            return None
        t = tokens[offset:offset + count]
        result = {
            "spread":    t[0],
            "spr_price": t[1],
            "ml":        t[2],
            "total":     t[3],
        }
        if has_ou:
            result["total_side"]  = t[4]
            result["total_price"] = t[5]
        return result
    except Exception:
        return None


def is_time_row(tokens: list) -> bool:
    """Rows that start with a game time like '3:45' or '7:10'."""
    return bool(tokens and re.match(r'^\d{1,2}:\d{2}$', tokens[0]))


def is_book_header(text: str) -> bool:
    return any(b in text for b in [
        'Circa', 'Westgate', 'BetMGM', 'Stations',
        'South Point', 'Wynn', 'Boomers', 'Caesars',
        'SPR', 'ML ', 'TOT',
    ])


def is_date_header(text: str) -> bool:
    return bool(re.match(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s', text))


def extract_name(tokens: list) -> tuple[str, int]:
    """
    Competitor name: 1–4 words before the first odds/dash token.
    Returns (name, offset_of_first_odds_token).
    """
    name_parts = []
    for i, t in enumerate(tokens):
        if re.match(r'^[+-]\d', t) or re.match(r'^\d+\.?\d*$', t) or t == '-':
            return ' '.join(name_parts), i
        name_parts.append(t)
    return ' '.join(name_parts), len(tokens)


def parse_html(html: str) -> list[dict]:
    """
    Returns list of game/matchup dicts:
    {
      "time":      "7:05 PM ET",
      "away_team": "Golden State Valkyries",
      "home_team": "Toronto Tempo",
      "open": { "Circa": {"spread":"-7.5","spr_price":"-110","ml":"-300","total":"169.5"}, ... },
      "books": {
        "Circa": {
          "away": {"spread":"-8","spr_price":"-110","ml":"-330","total":"165.5",
                   "total_side":"o","total_price":"-110"},
          "home": {...}
        }, ...
      }
    }
    """
    rows_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    rows = [clean_row(r) for r in rows_raw]

    games = []
    pending = None   # accumulates time → away → home

    for row in rows:
        if not row or is_book_header(row) or is_date_header(row):
            continue

        tokens = row.split()
        if len(tokens) < 4:
            continue

        if is_time_row(tokens):
            # Format: "7:05 PM ET ET OPEN [spr spr_price ml total] × 8 books"
            game_time = f"{tokens[0]} {tokens[1]} {tokens[2]}"
            odds_start = 5 if len(tokens) > 5 and tokens[4] == 'OPEN' else 4
            open_tokens = tokens[odds_start:]
            open_odds = {}
            for i, book in enumerate(ALL_BOOKS):
                o = parse_book_odds(open_tokens, i * 4, has_ou=False)
                if o:
                    open_odds[book] = o
            pending = {"time": game_time, "open": open_odds}

        elif pending is not None and "away_team" not in pending:
            name, offset = extract_name(tokens)
            if not name:
                continue
            odds_tokens = tokens[offset:]
            book_odds = {}
            for i, book in enumerate(ALL_BOOKS):
                o = parse_book_odds(odds_tokens, i * 6, has_ou=True)
                if o:
                    book_odds[book] = {"away": o}
            pending["away_team"] = name
            pending["_away_books"] = book_odds

        elif pending is not None and "away_team" in pending:
            name, offset = extract_name(tokens)
            if not name:
                continue
            odds_tokens = tokens[offset:]
            books = pending.get("_away_books", {})
            for i, book in enumerate(ALL_BOOKS):
                o = parse_book_odds(odds_tokens, i * 6, has_ou=True)
                if o:
                    if book in books:
                        books[book]["home"] = o
                    else:
                        books[book] = {"home": o}

            games.append({
                "time":      pending.get("time", ""),
                "away_team": pending["away_team"],
                "home_team": name,
                "open":      pending.get("open", {}),
                "books":     books,
            })
            pending = None

    return games


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


def run():
    fetched_any = False
    for sport, sport_id in SPORTS.items():
        try:
            log(f"Fetching VSiN {sport} ({sport_id}) ...")
            html = fetch_html(sport_id)
            games = parse_html(html)

            if not games:
                log(f"  {sport}: 0 matchups parsed — off-season or layout change, skipping")
                continue

            if is_mlb_fallback(games, sport):
                log(f"  {sport}: VSiN served MLB fallback page — off-season, skipping")
                continue

            log(f"  {sport}: {len(games)} matchups parsed")
            payload = {
                "sport":   sport,
                "updated": datetime.now(timezone.utc).isoformat(),
                "books":   ALL_BOOKS,
                "games":   games,
            }
            key = f"betcouncil_vsin_{sport}.json"
            if push_to_gist(key, payload):
                log(f"  {sport}: pushed {key} ✓")
                fetched_any = True
            else:
                log(f"  {sport}: Gist push failed")
        except Exception as e:
            log(f"  {sport}: ERROR — {e}")

    if not fetched_any:
        log("No sports had real data this run")
        sys.exit(0)


if __name__ == "__main__":
    run()
