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

Pushes one Gist file per sport:  betcouncil_vsin_{SPORT}.json
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

SPORTS = {
    "MLB": "mlb",
    "NFL": "nfl",
    "NBA": "nba",
    "NHL": "nhl",
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


def parse_book_odds(tokens: list, offset: int, has_ou: bool) -> dict:
    """
    Parse one book's block from a token list starting at offset.
    Time/open rows: [spr, rl_price, ml, total]          → 4 tokens, no o/u
    Team rows:      [spr, rl_price, ml, total, ou, vig]  → 6 tokens
    Returns dict or None if tokens are missing/invalid.
    """
    try:
        count = 6 if has_ou else 4
        if offset + count > len(tokens):
            return None
        t = tokens[offset:offset + count]
        result = {
            "run_line": t[0],
            "rl_price": t[1],
            "ml": t[2],
            "total": t[3],
        }
        if has_ou:
            result["total_side"] = t[4]   # "o" or "u"
            result["total_price"] = t[5]
        return result
    except Exception:
        return None


def is_time_row(tokens: list) -> bool:
    """Rows that start with a time string like '3:45' or '7:10'."""
    return bool(tokens and re.match(r'^\d{1,2}:\d{2}$', tokens[0]))


def is_book_header(text: str) -> bool:
    return any(b in text for b in ['Circa', 'Westgate', 'BetMGM', 'Stations',
                                    'South Point', 'Wynn', 'Boomers', 'Caesars'])


def extract_team_name(tokens: list) -> tuple[str, int]:
    """
    Team names are 1-3 words before the first odds token.
    Returns (team_name, offset_after_name).
    """
    name_parts = []
    for i, t in enumerate(tokens):
        if re.match(r'^[+-]\d', t) or re.match(r'^\d+\.?\d*$', t):
            return ' '.join(name_parts), i
        name_parts.append(t)
    return ' '.join(name_parts), len(tokens)


def parse_html(html: str) -> list[dict]:
    """
    Returns list of game dicts:
    {
      "time": "3:45 PM ET",
      "away_team": "Toronto Blue Jays",
      "home_team": "San Francisco Giants",
      "open": { "run_line": "+1.5", "rl_price": "-220", "ml": "-105", "total": "7" },
      "books": {
        "Circa": { "away": {...6 fields}, "home": {...6 fields} },
        ...
      }
    }
    """
    rows_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    rows = [clean_row(r) for r in rows_raw]

    games = []
    current_game = None
    # Track which team slot we're filling: 0=away pending, 1=home pending
    pending_away = None   # tokens for away/time row
    game_time = None

    for row in rows:
        if not row or is_book_header(row):
            continue

        tokens = row.split()
        if len(tokens) < 4:
            continue

        if is_time_row(tokens):
            # "3:45 PM ET ET OPEN [spr rl_price ml total] x8"
            # Save time and open odds for next game
            game_time = f"{tokens[0]} {tokens[1]} {tokens[2]}"
            # Tokens after "ET OPEN" prefix (5 tokens): index 5 onward
            odds_start = 5 if len(tokens) > 5 and tokens[4] == 'OPEN' else 4
            open_tokens = tokens[odds_start:]
            # Open row has 4 tokens per book (8 books = 32 tokens)
            open_odds = {}
            for i, book in enumerate(ALL_BOOKS):
                o = parse_book_odds(open_tokens, i * 4, has_ou=False)
                if o:
                    open_odds[book] = o
            pending_away = {"time": game_time, "open": open_odds, "book_tokens": None}

        elif pending_away is not None and 'away_team' not in pending_away:
            # This is the away team row
            team_name, offset = extract_team_name(tokens)
            if not team_name:
                continue
            odds_tokens = tokens[offset:]
            book_odds = {}
            for i, book in enumerate(ALL_BOOKS):
                o = parse_book_odds(odds_tokens, i * 6, has_ou=True)
                if o:
                    book_odds[book] = {"away": o}
            pending_away['away_team'] = team_name
            pending_away['book_tokens_away'] = book_odds

        elif pending_away is not None and 'away_team' in pending_away:
            # This is the home team row
            team_name, offset = extract_team_name(tokens)
            if not team_name:
                continue
            odds_tokens = tokens[offset:]
            books = pending_away.get('book_tokens_away', {})
            for i, book in enumerate(ALL_BOOKS):
                o = parse_book_odds(odds_tokens, i * 6, has_ou=True)
                if o:
                    if book in books:
                        books[book]['home'] = o
                    else:
                        books[book] = {"home": o}

            game = {
                "time": pending_away.get("time", ""),
                "away_team": pending_away["away_team"],
                "home_team": team_name,
                "open": pending_away.get("open", {}),
                "books": books,
            }
            games.append(game)
            pending_away = None

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
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status == 200


def run():
    fetched_any = False
    for sport, sport_id in SPORTS.items():
        try:
            log(f"Fetching VSiN {sport} ...")
            html = fetch_html(sport_id)
            games = parse_html(html)
            if not games:
                log(f"  {sport}: 0 games (off-season or parse error) — skipping")
                continue
            log(f"  {sport}: {len(games)} games parsed")
            payload = {
                "sport": sport,
                "updated": datetime.now(timezone.utc).isoformat(),
                "books": ALL_BOOKS,
                "games": games,
            }
            key = f"betcouncil_vsin_{sport}.json"
            if push_to_gist(key, payload):
                log(f"  {sport}: pushed {key} OK")
                fetched_any = True
            else:
                log(f"  {sport}: Gist push failed")
        except Exception as e:
            log(f"  {sport}: ERROR — {e}")

    if not fetched_any:
        log("No sports had data (all off-season or all failed)")
        sys.exit(0)


if __name__ == "__main__":
    run()
