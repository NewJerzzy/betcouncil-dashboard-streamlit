"""
bookmaker_refresh.py — BookMaker.eu game lines scraper
=======================================================
Scrapes https://lines.bookmaker.eu/en/sports/{sport}/ for game-day
moneylines, spreads/run-lines, and totals.

BookMaker.eu is a sharp offshore sportsbook — its lines are widely cited
as a sharp reference (alongside Pinnacle, Circa, Novig). The lines feed
at lines.bookmaker.eu is publicly accessible with no auth or cookies.

Structure: server-rendered HTML <table class='oddsTable'> with columns:
  [Time] [Team] [Spread/Run Line] [Total] [Moneyline]
Two rows per game — first row is the away/visitor team (includes time),
second row is the home team.

Sports supported:
  baseball  → MLB run lines, totals, ML
  basketball → NBA spread, total, ML  (and other leagues in NBA section)
  football   → NFL spread, total, ML

Pushes: betcouncil_bookmaker_game_lines.json
"""

import gzip
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

BASE_URL = "https://lines.bookmaker.eu/en/sports"
GIST_FILENAME = "betcouncil_bookmaker_game_lines.json"
# Dead file to rename if gist is at the 300-file cap and GIST_FILENAME doesn't exist
DEAD_FILE_FOR_RENAME = "betcouncil_bettingpros_snapshot_debug.json"

SPORT_PATHS = {
    "MLB":  "baseball",
    "NBA":  "basketball",
    "NFL":  "football",
    "NHL":  "hockey",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://lines.bookmaker.eu/",
}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_html(sport_path: str) -> str:
    url = f"{BASE_URL}/{sport_path}/"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        return gzip.decompress(raw).decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _clean_cell(cell_html: str) -> str:
    """Strip HTML tags and normalize whitespace from a table cell."""
    text = re.sub(r'<[^>]+>', '', cell_html)
    return re.sub(r'\s+', ' ', text).strip()


def _parse_time(raw_time: str) -> str:
    """
    Convert Bookmaker.eu time like '8/011:10pmPT' → '08/01 1:10pm PT'.
    The format is M/DDH:MMampmTZ with no separating space.
    """
    # Pattern: digits/digits digits:digits am/pm TZ
    m = re.match(r'(\d+)/(\d+)(\d+:\d+(?:am|pm))(\w+)', raw_time, re.IGNORECASE)
    if m:
        mon, day, time_str, tz = m.groups()
        return f"{int(mon):02d}/{int(day):02d} {time_str} {tz}"
    return raw_time


def _strip_vulgar_fractions(s: str) -> str:
    """Replace ½ with .5 for numeric parsing downstream."""
    return s.replace('½', '.5').replace('¼', '.25').replace('¾', '.75')


def parse_table(html: str, sport: str) -> list[dict]:
    """
    Extract game lines from the oddsTable. Returns list of game dicts:
      {sport, league, game_time, away_team, home_team,
       spread_away, spread_home, total, ml_away, ml_home}
    """
    table_match = re.search(
        r"<table[^>]*class='oddsTable'[^>]*>(.*?)</table>",
        html, re.DOTALL
    )
    if not table_match:
        return []

    table_html = table_match.group(1)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

    games = []
    current_league = sport
    pending_away: dict | None = None

    for row in rows:
        cells_raw = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
        cells = [_clean_cell(c) for c in cells_raw]

        if not cells:
            continue

        # Header row: ['Time', 'Team', ...] — skip
        if cells[0] in ('Time', ''):
            continue

        # League sub-header: single cell like 'MLB' or 'NFL' or 'NFLMelbourne...'
        if len(cells) == 1:
            # Extract just the league code (leading uppercase letters)
            m = re.match(r'^([A-Z]{2,6})', cells[0])
            if m:
                current_league = m.group(1)
            pending_away = None
            continue

        # 5-cell row: [time+team?, team?, spread, total, ml]
        # After tag stripping the time and team name may land in separate cells
        # or be concatenated — the table uses one <td> for time + one for team.
        # Our extraction shows them as separate items in the list.

        if len(cells) == 5:
            # [time, team, spread, total, ml]
            game_time, team, spread, total, ml = cells
            game_time = _parse_time(game_time)
            spread = _strip_vulgar_fractions(spread)
            total = _strip_vulgar_fractions(total)
            pending_away = {
                "league":     current_league,
                "game_time":  game_time,
                "away_team":  team,
                "spread_away": spread,
                "total":      total,
                "ml_away":    ml,
            }
            continue

        if len(cells) == 4 and pending_away is not None:
            # [team, spread, total, ml] — home team
            team, spread, total, ml = cells
            spread = _strip_vulgar_fractions(spread)
            total = _strip_vulgar_fractions(total)
            game = dict(pending_away)
            game.update({
                "home_team":   team,
                "spread_home": spread,
                "ml_home":     ml,
            })
            # Sanity check: totals should match (or be very close)
            if game.get("total") != total:
                game["total_home"] = total  # keep both if they differ
            games.append(game)
            pending_away = None
            continue

        # Any other row shape — reset pending
        pending_away = None

    return games


def push_to_gist(payload: dict) -> bool:
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False

    content = json.dumps(payload, indent=2)
    gist_headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
    }

    # Try direct upsert (works if file exists or gist < 300 files)
    body = json.dumps({"files": {GIST_FILENAME: {"content": content}}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=body, method="PATCH", headers=gist_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status == 200:
                return True
    except urllib.error.HTTPError as e:
        if e.code != 422:
            log(f"Gist PATCH error {e.code}: {e.read().decode()[:200]}")
            return False
        log(f"Gist at cap; renaming dead file → {GIST_FILENAME}")

    # Rename dead file approach
    rename_body = json.dumps({
        "files": {DEAD_FILE_FOR_RENAME: {"filename": GIST_FILENAME, "content": content}}
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


def run() -> None:
    all_games: list[dict] = []
    sport_counts: dict[str, int] = {}

    for sport, path in SPORT_PATHS.items():
        log(f"Fetching BookMaker.eu lines: {sport} ...")
        try:
            html = fetch_html(path)
        except Exception as e:
            log(f"  ERROR fetching {sport}: {e}")
            continue

        games = parse_table(html, sport)
        log(f"  {sport}: {len(games)} games parsed")
        for g in games:
            g["sport"] = sport
        all_games.extend(games)
        sport_counts[sport] = len(games)

    if not all_games:
        log("No games found across all sports — skipping gist push")
        sys.exit(1)

    leagues = sorted({g.get("league", g["sport"]) for g in all_games})
    payload = {
        "updated":      datetime.now(timezone.utc).isoformat(),
        "source":       "lines.bookmaker.eu",
        "note":         "Sharp offshore sportsbook. Run lines (MLB), spreads (NBA/NFL), totals, moneylines.",
        "total_games":  len(all_games),
        "by_sport":     sport_counts,
        "leagues":      leagues,
        "games":        all_games,
    }

    if push_to_gist(payload):
        log(f"Pushed {GIST_FILENAME} — {len(all_games)} games total")
    else:
        log("ERROR: Gist push failed")
        sys.exit(1)


if __name__ == "__main__":
    run()
