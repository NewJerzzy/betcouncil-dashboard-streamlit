"""
vsin_splits_refresh.py — VSiN public betting splits (handle% + bets%) via data.vsin.com
=========================================================================================

VSiN's data.vsin.com/betting-splits is a genuine SSR page (no JavaScript
rendering required — confirmed 2026-08-01). The complete betting splits
table is embedded directly in the HTML response.

Endpoint confirmed working:
    GET https://data.vsin.com/betting-splits
    → 200, HTML with <table class="sp-table"> embedded in #main-content
    No auth, no cookies, no rate limits observed

Table structure (each game = 2 rows: road team + home team):
  Column 0:  action button — data-gamecode="YYYYMMDD{SPORT}{ID}"
             road row:  class="sp-act-history"
             home row:  class="sp-act-count"
  Column 1:  team name — a.sp-team-link
  Column 2:  spread line — span.sp-badge-line (first)
  Column 3:  spread handle% — span.sp-badge
  Column 4:  spread bets%   — span.sp-badge
  Column 5:  total line — span.sp-badge-line (second)
  Column 6:  total handle%  — span.sp-badge
  Column 7:  total bets%    — span.sp-badge
  Column 8:  ML line — span.sp-badge-line (third)
  Column 9:  ML handle%     — span.sp-badge
  Column 10: ML bets%       — span.sp-badge

Gamecode format: 20260731MLB00019 → date=20260731, sport=MLB, game_id=00019
(sport slug is variable width: MLB=3, CFL=3, WNB=3, etc.)

Gist slot management (300-file hard cap):
  betcouncil_oddsshark_NBA.json (143b — confirmed dead placeholder) is
  repurposed → betcouncil_vsin_splits.json on first run via GitHub Gist
  rename API. Subsequent runs push directly to betcouncil_vsin_splits.json.

Output shape:
{
  "captured_at": "2026-08-01T12:00:00+00:00",
  "source": "vsin_splits",
  "game_count": N,
  "games": [
    {
      "gamecode": "20260731MLB00019",
      "sport": "MLB",
      "date": "2026-07-31",
      "road_team": "New York Yankees",
      "home_team": "Chicago Cubs",
      "spread": {
        "road": {"line": "+1.5", "handle_pct": 21, "bets_pct": 47},
        "home": {"line": "-1.5", "handle_pct": 79, "bets_pct": 53}
      },
      "total": {
        "line": "9",
        "over": {"handle_pct": 60, "bets_pct": 44},
        "under": {"handle_pct": 40, "bets_pct": 56}
      },
      "moneyline": {
        "road": {"line": "+141", "handle_pct": 23, "bets_pct": 35},
        "home": {"line": "-171", "handle_pct": 77, "bets_pct": 65}
      },
      "vsin_pick_count": 8
    }
  ]
}
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
TARGET_FILE = "betcouncil_vsin_splits.json"
LEGACY_FILE = "betcouncil_bettingpros_debug.json"  # confirmed diagnostic-only, low-frequency owner cron (real oddsshark_NBA.json is active data, NOT dead -- do not target that)
BASE_URL = "https://data.vsin.com/betting-splits"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _parse_pct(text: str) -> int | None:
    """Parse '21%' or '21' → 21. Returns None on failure."""
    text = text.strip().rstrip("%")
    try:
        return int(text)
    except (ValueError, TypeError):
        return None


def _parse_gamecode(gamecode: str) -> tuple[str, str, str]:
    """
    Parse gamecode like '20260731MLB00019' into (date_iso, sport, game_id).
    Date portion is always 8 chars, game_id is always 5 chars.
    Sport is everything between them.
    """
    if len(gamecode) < 14:
        return ("", gamecode, "")
    date_raw = gamecode[:8]
    game_id = gamecode[-5:]
    sport = gamecode[8:-5]
    try:
        date_iso = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    except Exception:
        date_iso = date_raw
    return (date_iso, sport, game_id)


def fetch_splits_html() -> str:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=25)
    DEBUG_LOG.append({
        "url": BASE_URL,
        "status": resp.status_code,
        "content_type": resp.headers.get("Content-Type", ""),
        "body_len": len(resp.text),
    })
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.text


def parse_splits(html: str) -> list[dict]:
    """
    Parse the sp-table tbody rows into game records.
    Each game has exactly 2 consecutive rows (road team row + home team row),
    identified by whether the action button is sp-act-history (road) or
    sp-act-count (home).
    """
    # Extract every <tr class="sp-row ..."> row
    row_blocks = re.findall(
        r'<tr\s+class="sp-row[^"]*">(.*?)</tr>',
        html, re.DOTALL
    )
    log(f"  Found {len(row_blocks)} sp-row rows")

    games: dict[str, dict] = {}

    for row_html in row_blocks:
        # ── Gamecode ──────────────────────────────────────────────────────
        gc_m = re.search(r'data-gamecode=["\']([^"\']+)["\']', row_html)
        if not gc_m:
            continue
        gc = gc_m.group(1)

        # ── Road vs Home detection ────────────────────────────────────────
        is_road = bool(re.search(r'class="sp-act-history"', row_html))
        is_home = bool(re.search(r'class="sp-act-count"', row_html))
        if not (is_road or is_home):
            # Fallback: first occurrence of gamecode = road
            is_road = gc not in games or games[gc].get("road") is None

        # ── Team name ─────────────────────────────────────────────────────
        team_m = re.search(r'sp-team-link[^>]+>([^<]+)<', row_html)
        team = team_m.group(1).strip() if team_m else ""

        # ── VSiN pick count (home row button text) ────────────────────────
        vsin_picks = None
        if is_home:
            picks_m = re.search(r'sp-act-count[^>]+>(\d+)<', row_html)
            if picks_m:
                vsin_picks = int(picks_m.group(1))

        # ── Extract all <td> cells for ordered parsing ────────────────────
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)

        def _cell_text(idx: int) -> str:
            if idx >= len(cells):
                return ""
            return re.sub(r'<[^>]+>', '', cells[idx]).strip()

        def _badge_line(idx: int) -> str:
            """First sp-badge-line in cell idx."""
            if idx >= len(cells):
                return ""
            m = re.search(r'sp-badge-line[^>]+>([^<]+)<', cells[idx])
            return m.group(1).strip() if m else ""

        def _badge_pct(idx: int) -> int | None:
            """First plain sp-badge (not sp-badge-line) in cell idx."""
            if idx >= len(cells):
                return None
            # Skip sp-badge-line; find plain sp-badge or sp-badge-green
            for m in re.finditer(r'<span\s+class="sp-badge[^"]*"[^>]*>([^<]+)<', cells[idx]):
                text = m.group(1).strip()
                if re.match(r'\d+%?$', text):
                    return _parse_pct(text)
            return None

        # Cell layout (0-indexed after td extraction):
        # 0: action button
        # 1: team + logo
        # 2: spread line | handle% | bets%  (spread section, 1 td per col)
        # 3: spread handle%
        # 4: spread bets%
        # 5: total line
        # 6: total handle%
        # 7: total bets%
        # 8: ML line
        # 9: ML handle%
        # 10: ML bets%
        spread_line    = _badge_line(2)
        spread_handle  = _badge_pct(3)
        spread_bets    = _badge_pct(4)
        total_line     = _badge_line(5)
        total_handle   = _badge_pct(6)
        total_bets     = _badge_pct(7)
        ml_line        = _badge_line(8)
        ml_handle      = _badge_pct(9)
        ml_bets        = _badge_pct(10)

        # ── Assemble game record ──────────────────────────────────────────
        if gc not in games:
            date_iso, sport, game_id = _parse_gamecode(gc)
            games[gc] = {
                "gamecode": gc,
                "sport": sport,
                "date": date_iso,
                "game_id": game_id,
                "road_team": None,
                "home_team": None,
                "vsin_pick_count": None,
                "spread": {"road": {}, "home": {}},
                "total": {"line": None, "over": {}, "under": {}},
                "moneyline": {"road": {}, "home": {}},
            }

        g = games[gc]

        if is_road:
            g["road_team"] = team
            g["spread"]["road"] = {"line": spread_line, "handle_pct": spread_handle, "bets_pct": spread_bets}
            g["total"]["line"] = total_line
            g["total"]["over"] = {"handle_pct": total_handle, "bets_pct": total_bets}
            g["moneyline"]["road"] = {"line": ml_line, "handle_pct": ml_handle, "bets_pct": ml_bets}
        else:
            g["home_team"] = team
            if vsin_picks is not None:
                g["vsin_pick_count"] = vsin_picks
            g["spread"]["home"] = {"line": spread_line, "handle_pct": spread_handle, "bets_pct": spread_bets}
            g["total"]["under"] = {"handle_pct": total_handle, "bets_pct": total_bets}
            g["moneyline"]["home"] = {"line": ml_line, "handle_pct": ml_handle, "bets_pct": ml_bets}

    return list(games.values())


def _get_gist_files(github_token: str) -> set:
    """Return the set of filenames currently in the gist."""
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return set(resp.json().get("files", {}).keys())
    except Exception as e:
        log(f"  _get_gist_files: {e} — assuming target doesn't exist")
    return set()


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={"files": files_payload},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 4:
            base_wait = min(10 * (2 ** attempt), 90)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"  Gist push got {resp.status_code} — retrying in {wait:.1f}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue
        log(f"  Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget before doing any writes."""
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} requests left this hour) — skipping")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) — proceeding anyway")
    return True


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    if not _rate_limit_ok(github_token):
        return 0

    log(f"Fetching {BASE_URL}")
    try:
        html = fetch_splits_html()
    except Exception as e:
        log(f"FATAL: fetch failed — {e}")
        return 1

    log("Parsing splits table")
    games = parse_splits(html)

    sport_counts: dict[str, int] = {}
    for g in games:
        sport = g.get("sport", "?")
        sport_counts[sport] = sport_counts.get(sport, 0) + 1
    log(f"  Parsed {len(games)} games: {sport_counts}")

    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "captured_at": now_iso,
        "source": "vsin_splits",
        "page_url": BASE_URL,
        "game_count": len(games),
        "sports": sport_counts,
        "games": games,
    }
    content = json.dumps(payload, indent=2)

    # ── Gist slot management (300-file hard cap) ──────────────────────────
    # Check whether betcouncil_vsin_splits.json already exists.
    # If not, repurpose betcouncil_oddsshark_NBA.json (143b dead placeholder)
    # via the GitHub Gist rename API — atomically renames + updates content,
    # keeping total file count at 300.
    log("Checking gist slot availability")
    existing_files = _get_gist_files(github_token)

    if TARGET_FILE in existing_files:
        log(f"  Target '{TARGET_FILE}' exists — pushing update")
        files_payload = {TARGET_FILE: {"content": content}}
    else:
        log(f"  Target '{TARGET_FILE}' not found — repurposing '{LEGACY_FILE}' via rename")
        files_payload = {
            LEGACY_FILE: {
                "filename": TARGET_FILE,
                "content": content,
            }
        }

    if not games:
        log("No games parsed — aborting push (not overwriting with empty data)")
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} file(s) → {TARGET_FILE}")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
