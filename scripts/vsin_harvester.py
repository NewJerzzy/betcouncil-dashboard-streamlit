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


def push_merged_to_gist(accumulated: dict) -> bool:
    """
    Confirmed real bug (Aug 2 2026): standalone betcouncil_vsin_{SPORT}.json
    filenames never once landed in this Gist despite the workflow
    repeatedly reporting success -- proven across 4 independent scripts
    (Underdog, WiseGuyTeam, Unabated, VSIN) hitting the identical
    symptom: this Gist reliably cannot create brand-new filenames.
    Merges into the already-existing, actively-written
    betcouncil_evbets_combined.json under a "vsin_lines" key instead.

    UPDATED (2026-08-03): confirmed a real, live production data-loss
    race -- multiple scripts merge into this same shared file on
    independent cron schedules, and one script's write can silently
    clobber another's just-written key if their timing overlaps.
    Added an outer retry: after a successful write, verify no
    previously-present key vanished, and redo the whole cycle from a
    fresh read if one did, up to 3 times total.
    """
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False
    SHARED_FILE = "betcouncil_sharp_feeds.json"

    for outer_attempt in range(3):
        try:
            req = urllib.request.Request(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                listing = json.loads(r.read())
            r_files = listing.get("files", {})
            if SHARED_FILE in r_files:
                raw_url = r_files[SHARED_FILE]["raw_url"]
                with urllib.request.urlopen(raw_url, timeout=15) as r2:
                    existing = json.loads(r2.read())
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        pre_write_keys = set(existing.keys())
        existing["vsin_lines"] = accumulated
        body = json.dumps({"files": {SHARED_FILE: {"content": json.dumps(existing)}}}).encode()

        write_ok = False
        for attempt in range(4):
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
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    if r.status != 200:
                        return False
                    resp_body = json.loads(r.read())
                    if SHARED_FILE in (resp_body.get("files") or {}):
                        write_ok = True
                        break
                    log(f"  Push returned 200 but {SHARED_FILE} missing from response -- retrying")
            except urllib.error.HTTPError as e:
                if e.code not in (403, 429, 409) or attempt >= 3:
                    log(f"  Gist push failed: HTTP {e.code}")
                    return False
            except Exception as e:
                log(f"  Gist push failed: {e}")
                return False
            if attempt < 3:
                import time as _t
                _t.sleep(8 * (attempt + 1))

        if not write_ok:
            return False

        try:
            import time as _t
            _t.sleep(2)
            req3 = urllib.request.Request(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req3, timeout=15) as r3:
                listing2 = json.loads(r3.read())
            raw_url2 = listing2.get("files", {}).get(SHARED_FILE, {}).get("raw_url")
            with urllib.request.urlopen(raw_url2, timeout=15) as r4:
                post_write = json.loads(r4.read())
            post_write_keys = set(post_write.keys())
            lost_keys = pre_write_keys - post_write_keys - {"vsin_lines"}
            if "vsin_lines" in post_write_keys and not lost_keys:
                return True
            log(f"  Post-write verification found lost keys {lost_keys} or missing own key -- retrying full cycle (outer attempt {outer_attempt+1}/3)")
        except Exception as e:
            log(f"  Post-write verification failed to check: {e} -- treating write as successful anyway")
            return True

    log("  Gave up after 3 full read-modify-write cycles -- concurrent writers kept colliding")
    return False


def push_to_gist(key: str, payload: dict) -> bool:
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False
    body = json.dumps({"files": {key: {"content": json.dumps(payload, indent=2)}}}).encode()
    for attempt in range(4):
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
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status != 200:
                    return False
                resp_body = json.loads(r.read())
                if key in (resp_body.get("files") or {}):
                    return True
                log(f"  Push returned 200 but {key} missing from response -- retrying")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 409) and attempt < 3:
                pass
            else:
                log(f"  Gist push failed: HTTP {e.code}")
                return False
        except Exception as e:
            log(f"  Gist push failed: {e}")
            return False
        if attempt < 3:
            import time as _t
            _t.sleep(8 * (attempt + 1))
    return False


def run():
    fetched_any = False
    accumulated = {}
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
            accumulated[sport] = payload
            fetched_any = True
        except Exception as e:
            log(f"  {sport}: ERROR — {e}")

    if accumulated:
        if push_merged_to_gist(accumulated):
            log(f"Pushed {len(accumulated)} sports merged ✓")
        else:
            log("Merged push failed")
            fetched_any = False

    if not fetched_any:
        log("No sports had real data this run -- this is a real failure, not exiting 0")
        # Emergency diagnostic push so the actual cause (parse failures,
        # site blocking, layout drift) is visible in Gist -- confirmed via
        # real data that this workflow has reported "success" on every
        # run while zero betcouncil_vsin_*.json files have ever existed.
        try:
            if GITHUB_TOKEN:
                debug_payload = {
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "note": "0 games parsed for every sport this run",
                }
                push_to_gist("betcouncil_vsin_debug.json", debug_payload)
        except Exception as _e:
            log(f"debug push also failed: {_e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
