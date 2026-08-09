"""
oddsshark_consensus_refresh.py — OddsShark / Covers public consensus picks (no auth)
======================================================================================

Data source: contests.covers.com (the canonical backend OddsShark pages redirect to)

Two endpoints per sport:
  Sides  — https://contests.covers.com/consensus/topconsensus/{sport}/overall
  Totals — https://contests.covers.com/consensus/topoverunderconsensus/{sport}/overall

Both return real server-side HTML tables (confirmed 200 + real rows 2026-07-28).
No JavaScript rendering required. Parsed with BeautifulSoup.

Sports in scope: mlb, nfl, nba, nhl, ncaaf
Also scraped opportunistically: wnba, cfl (active when in-season)

Sides table columns:   Matchup | Date | Consensus (low%/high%) | Sides (ML) | Picks | Details
Totals table columns:  Matchup | Date | Consensus (Over%/Under%) | Total (line) | Picks | Details

Output files (pushed to shared Gist):
  betcouncil_oddsshark_consensus_{SPORT}.json   — sides + totals merged per game
  betcouncil_oddsshark_consensus_debug.json     — per-request status log

Why contests.covers.com directly (not oddsshark.com):
  - oddsshark.com/mlb/consensus-picks redirects to contests.covers.com internally
  - NFL/NBA/NHL/NCAAF on oddsshark.com redirect to contests.covers.com with #hash
  - Using covers directly skips the redirect and uses a stable, consistent URL pattern
  - Both domains confirmed accessible from Replit; oddsshark.com blocked on GH Actions
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock
from bs4 import BeautifulSoup

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

SIDES_URL  = "https://contests.covers.com/consensus/topconsensus/{sport}/overall"
TOTALS_URL = "https://contests.covers.com/consensus/topoverunderconsensus/{sport}/overall"

# Primary sports (user-requested). Offseason sports return 0 rows — that's correct, not a bug.
SPORTS = ["mlb", "nfl", "nba", "nhl", "ncaaf", "wnba", "cfl"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def fetch_html(url: str, sport: str, table_type: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        DEBUG_LOG.append({
            "sport": sport,
            "type": table_type,
            "url": url,
            "status": r.status_code,
            "size": len(r.text),
        })
        if r.status_code != 200:
            log(f"  {sport}/{table_type}: HTTP {r.status_code}")
            return None
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log(f"  {sport}/{table_type}: fetch error — {e}")
        DEBUG_LOG.append({"sport": sport, "type": table_type, "url": url, "error": str(e)})
        return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_matchup_cell(td) -> dict:
    """Extract away/home team names and matchup ID from the matchup cell."""
    away_block = td.find("span", class_="covers-CoversConsensus-table--teamBlock")
    home_block = td.find("span", class_="covers-CoversConsensus-table--teamBlock2")

    def team_info(block) -> dict:
        if not block:
            return {"name": None, "abbr": None}
        link = block.find("a")
        if not link:
            return {"name": None, "abbr": None}
        return {
            "name": link.get("title") or link.get_text(strip=True),
            "abbr": link.get_text(strip=True),
        }

    away = team_info(away_block)
    home = team_info(home_block)
    return {"away": away, "home": home}


def _parse_date_cell(td) -> str | None:
    """Return the raw date/time string from the date cell."""
    return " ".join(td.get_text(separator=" ", strip=True).split()) or None


def _parse_consensus_sides(td) -> dict:
    """
    Consensus cell for sides table:
      low  span = away (first-listed team) %
      high span = home (second-listed team) %
    Returns {"away_pct": int, "home_pct": int, "consensus_side": "away"|"home"|None}
    """
    low  = td.find("span", class_=re.compile(r"consensusTable--low"))
    high = td.find("span", class_=re.compile(r"consensusTable--high"))

    def pct(span) -> int | None:
        if not span:
            return None
        txt = span.get_text(strip=True).replace("%", "").strip()
        try:
            return int(txt)
        except ValueError:
            return None

    away_pct = pct(low)
    home_pct = pct(high)
    consensus_side = None
    if away_pct is not None and home_pct is not None:
        if away_pct > home_pct:
            consensus_side = "away"
        elif home_pct > away_pct:
            consensus_side = "home"
    return {
        "away_pct": away_pct,
        "home_pct": home_pct,
        "consensus_side": consensus_side,
    }


def _parse_consensus_totals(td) -> dict:
    """
    Consensus cell for totals table:
      high span = Over %   (e.g. "78 % Over")
      low  span = Under %  (e.g. "22 % Under")
    Returns {"over_pct": int, "under_pct": int, "consensus_side": "over"|"under"|None}
    """
    high = td.find("span", class_=re.compile(r"consensusTable--high"))
    low  = td.find("span", class_=re.compile(r"consensusTable--low"))

    def pct(span) -> int | None:
        if not span:
            return None
        txt = span.get_text(strip=True)
        # strip text like "78 % Over" → "78"
        m = re.search(r"(\d+)", txt)
        return int(m.group(1)) if m else None

    over_pct  = pct(high)
    under_pct = pct(low)
    consensus_side = None
    if over_pct is not None and under_pct is not None:
        if over_pct > under_pct:
            consensus_side = "over"
        elif under_pct > over_pct:
            consensus_side = "under"
    return {
        "over_pct":  over_pct,
        "under_pct": under_pct,
        "consensus_side": consensus_side,
    }


def _parse_ml_cell(td) -> dict:
    """Sides ML cell: away line <br> home line."""
    parts = [p.strip() for p in td.get_text(separator="\n").split("\n") if p.strip()]
    return {
        "away_ml": parts[0] if len(parts) > 0 else None,
        "home_ml": parts[1] if len(parts) > 1 else None,
    }


def _parse_total_cell(td) -> str | None:
    return td.get_text(strip=True) or None


def _parse_picks_cell(td) -> dict:
    parts = [p.strip() for p in td.get_text(separator="\n").split("\n") if p.strip()]
    try:
        side1 = int(parts[0]) if parts else None
    except ValueError:
        side1 = None
    try:
        side2 = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        side2 = None
    return {"side1_picks": side1, "side2_picks": side2}


def _parse_details_cell(td) -> str | None:
    link = td.find("a")
    if not link:
        return None
    href = link.get("href", "")
    # Extract UUID from e.g. /consensus/matchupconsensusdetails/508d4394-0f76-...
    m = re.search(r"/([0-9a-f-]{36})", href)
    return m.group(1) if m else href or None


# ---------------------------------------------------------------------------
# Table parsers
# ---------------------------------------------------------------------------

def parse_sides_table(soup: BeautifulSoup, sport: str) -> list[dict]:
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")[1:]  # skip header
    results = []
    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        try:
            matchup   = _parse_matchup_cell(cells[0])
            date_str  = _parse_date_cell(cells[1])
            consensus = _parse_consensus_sides(cells[2])
            ml        = _parse_ml_cell(cells[3])
            picks     = _parse_picks_cell(cells[4])
            match_id  = _parse_details_cell(cells[5]) if len(cells) > 5 else None

            results.append({
                "sport":          sport.upper(),
                "matchup_id":     match_id,
                "away_team":      matchup["away"]["name"],
                "away_abbr":      matchup["away"]["abbr"],
                "home_team":      matchup["home"]["name"],
                "home_abbr":      matchup["home"]["abbr"],
                "game_date":      date_str,
                "away_ml_pct":    consensus["away_pct"],
                "home_ml_pct":    consensus["home_pct"],
                "consensus_ml_side": consensus["consensus_side"],
                "away_ml":        ml["away_ml"],
                "home_ml":        ml["home_ml"],
                "away_picks":     picks["side1_picks"],
                "home_picks":     picks["side2_picks"],
            })
        except Exception as e:
            log(f"  {sport}/sides: parse error on row — {e}")
    return results


def parse_totals_table(soup: BeautifulSoup, sport: str) -> list[dict]:
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")[1:]  # skip header
    results = []
    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        try:
            matchup   = _parse_matchup_cell(cells[0])
            date_str  = _parse_date_cell(cells[1])
            consensus = _parse_consensus_totals(cells[2])
            total_line = _parse_total_cell(cells[3])
            picks      = _parse_picks_cell(cells[4])
            match_id   = _parse_details_cell(cells[5]) if len(cells) > 5 else None

            results.append({
                "sport":           sport.upper(),
                "matchup_id":      match_id,
                "away_team":       matchup["away"]["name"],
                "away_abbr":       matchup["away"]["abbr"],
                "home_team":       matchup["home"]["name"],
                "home_abbr":       matchup["home"]["abbr"],
                "game_date":       date_str,
                "over_pct":        consensus["over_pct"],
                "under_pct":       consensus["under_pct"],
                "consensus_ou_side": consensus["consensus_side"],
                "total_line":      total_line,
                "over_picks":      picks["side1_picks"],
                "under_picks":     picks["side2_picks"],
            })
        except Exception as e:
            log(f"  {sport}/totals: parse error on row — {e}")
    return results


# ---------------------------------------------------------------------------
# Merge sides + totals by matchup_id (or away/home team pair)
# ---------------------------------------------------------------------------

def merge_sides_totals(sides: list[dict], totals: list[dict]) -> list[dict]:
    """
    Merge sides and totals rows for the same game into one record.
    Match on matchup_id first; fall back to (away_team, home_team) pair.
    """
    totals_by_id:   dict[str, dict] = {}
    totals_by_pair: dict[tuple, dict] = {}
    for t in totals:
        if t.get("matchup_id"):
            totals_by_id[t["matchup_id"]] = t
        pair = (t.get("away_team"), t.get("home_team"))
        totals_by_pair[pair] = t

    merged = []
    for s in sides:
        total = (
            totals_by_id.get(s.get("matchup_id"))
            or totals_by_pair.get((s.get("away_team"), s.get("home_team")))
            or {}
        )
        merged.append({
            # identity
            "sport":         s["sport"],
            "matchup_id":    s.get("matchup_id"),
            "away_team":     s.get("away_team"),
            "away_abbr":     s.get("away_abbr"),
            "home_team":     s.get("home_team"),
            "home_abbr":     s.get("home_abbr"),
            "game_date":     s.get("game_date"),
            # ML consensus
            "away_ml_pct":       s.get("away_ml_pct"),
            "home_ml_pct":       s.get("home_ml_pct"),
            "consensus_ml_side": s.get("consensus_ml_side"),
            "away_ml":           s.get("away_ml"),
            "home_ml":           s.get("home_ml"),
            "away_picks":        s.get("away_picks"),
            "home_picks":        s.get("home_picks"),
            # O/U consensus
            "over_pct":          total.get("over_pct"),
            "under_pct":         total.get("under_pct"),
            "consensus_ou_side": total.get("consensus_ou_side"),
            "total_line":        total.get("total_line"),
            "over_picks":        total.get("over_picks"),
            "under_picks":       total.get("under_picks"),
        })

    # Add totals-only rows (games that appear in totals but not sides — rare)
    sides_ids = {s.get("matchup_id") for s in sides if s.get("matchup_id")}
    sides_pairs = {(s.get("away_team"), s.get("home_team")) for s in sides}
    for t in totals:
        if t.get("matchup_id") in sides_ids:
            continue
        if (t.get("away_team"), t.get("home_team")) in sides_pairs:
            continue
        merged.append({
            "sport": t["sport"], "matchup_id": t.get("matchup_id"),
            "away_team": t.get("away_team"), "away_abbr": t.get("away_abbr"),
            "home_team": t.get("home_team"), "home_abbr": t.get("home_abbr"),
            "game_date": t.get("game_date"),
            "away_ml_pct": None, "home_ml_pct": None,
            "consensus_ml_side": None, "away_ml": None, "home_ml": None,
            "away_picks": None, "home_picks": None,
            "over_pct": t.get("over_pct"), "under_pct": t.get("under_pct"),
            "consensus_ou_side": t.get("consensus_ou_side"),
            "total_line": t.get("total_line"),
            "over_picks": t.get("over_picks"), "under_picks": t.get("under_picks"),
        })

    return merged


# ---------------------------------------------------------------------------
# Gist push
# ---------------------------------------------------------------------------

def push_files(files_payload: dict, github_token: str) -> int:
    """
    Merges all per-sport consensus files into ONE combined file, using
    the real distributed lock. Confirmed real: this is the genuinely-
    used oddsshark source (app.py:4245), distinct from the confirmed-
    dead oddsshark_refresh.py output removed the same pass.
    """
    SHARED_FILE = "betcouncil_oddsshark_consensus_combined.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_oddsshark_consensus_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

    lock_token = acquire_lock(GIST_ID, github_token, "oddsshark_consensus_combined", holder="oddsshark_consensus")
    if not lock_token:
        log("Could not acquire oddsshark_consensus_combined lock -- skipping this run to avoid a collision")
        return 0
    try:
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                existing = requests.get(r_files[SHARED_FILE]["raw_url"], timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        existing.update(merged)
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        for attempt in range(4):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    return len(merged)
                if attempt < 3:
                    time.sleep(5)
                    continue
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 3:
                wait = (attempt + 1) * 8 + random.uniform(0, 5)
                log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0
        return 0
    finally:
        release_lock(GIST_ID, github_token, "oddsshark_consensus_combined", lock_token)


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
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
            log(
                f"Shared GitHub token budget low ({remaining} requests left this hour) "
                "— skipping this run cleanly"
            )
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) — proceeding anyway")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload: dict = {}
    any_data = False

    for sport in SPORTS:
        sides_url  = SIDES_URL.format(sport=sport)
        totals_url = TOTALS_URL.format(sport=sport)

        sides_soup  = fetch_html(sides_url,  sport, "sides")
        time.sleep(random.uniform(0.4, 0.9))  # polite crawl delay
        totals_soup = fetch_html(totals_url, sport, "totals")
        time.sleep(random.uniform(0.4, 0.9))

        sides  = parse_sides_table(sides_soup,  sport) if sides_soup  else []
        totals = parse_totals_table(totals_soup, sport) if totals_soup else []

        if not sides and not totals:
            log(f"  {sport.upper()}: 0 games (offseason or no schedule today)")
            continue

        games = merge_sides_totals(sides, totals)
        ml_sided  = sum(1 for g in games if g.get("consensus_ml_side"))
        ou_sided  = sum(1 for g in games if g.get("consensus_ou_side"))
        log(f"  {sport.upper()}: {len(games)} games | {ml_sided} ML consensus | {ou_sided} O/U consensus")

        any_data = True
        files_payload[f"betcouncil_oddsshark_consensus_{sport.upper()}.json"] = {
            "content": json.dumps({
                "source":       "oddsshark_covers_consensus",
                "sport":        sport.upper(),
                "captured_at":  now_iso,
                "sides_url":    sides_url,
                "totals_url":   totals_url,
                "games":        games,
            }, indent=2)
        }

    files_payload["betcouncil_oddsshark_consensus_debug.json"] = {
        "content": json.dumps({
            "captured_at": now_iso,
            "requests":    DEBUG_LOG,
        }, indent=2)
    }

    if not any_data:
        log("No game data captured across all sports — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files to Gist {GIST_ID}")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
