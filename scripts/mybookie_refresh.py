"""
mybookie_refresh.py — MyBookie game lines scraper (public SSR HTML, no auth)
================================================================================

MyBookie's sportsbook pages server-render the entire odds board directly
into <button> elements with data-* attributes (data-gameid, data-wager-
type, data-team, data-odds, etc.) — no login required, no separate API
call to intercept. Confirmed live 2026-07-16 via direct fetch of
mybookie.ag/sportsbook/: real current games with matching spread/
moneyline/total data present in the page itself.

This came up because the Tampermonkey harvester (which watches for
/sports_api/leagues-lines and /sports_api/search-props XHR calls) wasn't
firing — those endpoints don't appear to be called by the current site
version. This script bypasses that entirely by reading the SSR HTML
directly, same approach as FavoredProps' embedded-data discovery.

Exact attribute schema wasn't independently verified byte-for-byte
before this first deploy (fetched the page and confirmed real odds data
is present, but the fetch tool renders to markdown, which strips raw
HTML attributes) — ships with debug logging so any schema mismatch is
caught immediately rather than silently producing nothing, same
precaution used for every first-deploy harvester this session.

Pushes to betcouncil_mybookie_ssr_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://www.mybookie.ag"
# Pages known to carry a real odds board (from the investigation):
# main page (mixed sports) plus sport-specific pages for reliable per-sport
# splitting. Football/soccer subpages had some unresolved template
# placeholders per the investigation — skip games whose wager-type field
# still contains "{{{" rather than trying to guess-fix them.
PAGES = {
    "MLB": "/sportsbook/mlb/",
    "NBA": "/sportsbook/nba/",
    "NFL": "/sportsbook/nfl/",
    "NHL": "/sportsbook/nhl/",
    "WNBA": "/sportsbook/wnba/",
    "SOCCER": "/sportsbook/soccer/",
}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_sport_page(sport: str, path: str) -> list:
    url = f"{BASE_URL}{path}"
    r = requests.get(url, headers=HEADERS, timeout=25)
    DEBUG_LOG.append({"sport": sport, "url": url, "status": r.status_code,
                       "body_len": len(r.text), "body_snippet": r.text[:600]})
    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    games: dict = {}

    for btn in soup.find_all(attrs={"data-gameid": True}):
        d = btn.attrs
        wager_type = d.get("data-wager-type", "")
        if "{{{" in wager_type:
            continue  # unresolved template placeholder, skip rather than guess

        game_id = d.get("data-gameid")
        if not game_id:
            continue
        if game_id not in games:
            games[game_id] = {
                "game_id": game_id,
                "sport": d.get("data-description", sport),
                "game_date": d.get("data-gamedate", ""),
                "is_live": d.get("data-islive", "") == "1",
                "sides": [],
            }
        games[game_id]["sides"].append({
            "type": wager_type,  # sp=spread, ml=moneyline, to=total
            "team": d.get("data-team", ""),
            "vs": d.get("data-team-vs", ""),
            "points": d.get("data-points", ""),
            "odds": d.get("data-odds", ""),
            "outcome_id": d.get("data-outcomeid", ""),
            "market_id": d.get("data-marketid", ""),
        })

    return list(games.values())


def push_files(files_payload: dict, github_token: str) -> int:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": files_payload}, timeout=30,
    )
    if resp.status_code in (200, 201):
        return len(files_payload)
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_data = False

    for sport, path in PAGES.items():
        try:
            games = fetch_sport_page(sport, path)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not games:
            log(f"  {sport}: 0 games found")
            continue
        any_data = True
        log(f"  {sport}: {len(games)} games")
        files_payload[f"betcouncil_mybookie_ssr_{sport}.json"] = {
            "content": json.dumps({
                "source": "mybookie_ssr", "sport": sport,
                "captured_at": now_iso, "games": games,
            })
        }

    files_payload["betcouncil_mybookie_ssr_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG}, indent=2)
    }

    if not any_data:
        log("No sport data captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
