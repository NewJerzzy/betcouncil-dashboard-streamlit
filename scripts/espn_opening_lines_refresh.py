"""
espn_opening_lines_refresh.py — Daily opening-line capture via ESPN (public, no auth)
================================================================================

Replaces the old "oddsportal" harvester slot. That one assumed a
`https://www.oddsportal.com/api/v1/events/{sport}/today` endpoint that
was never verified and, on inspection, doesn't appear to exist —
OddsPortal's actual odds tables load via client-side JS, not present in
the served HTML, and the site has no documented public API. Rather than
build a fragile, unverified scraper against a JS-heavy site, this uses
ESPN's scoreboard endpoint (site.api.espn.com) — the exact same source
and odds-field shape fetch_game_lines() in this codebase already uses
successfully for live board odds.

The key difference from fetch_game_lines(): this script captures each
game's moneyline ONCE per day and never overwrites it — that's what
makes it an "opening" line rather than just another current-odds read.
On each run, it checks whether today's snapshot already exists in the
Gist for a given sport; if so, it leaves it alone (already have the
real opening number); if not, it captures today's first-seen odds as
the opening reference.

Pushes to betcouncil_oddsportal_{sport}.json — same filename the
existing fetch_oddsportal_from_gist() reader already expects, so no
changes needed on the read side beyond fixing the docstring/fallback
(done separately in fetchers.py).
"""

import json
import os
import sys
from datetime import date, datetime, timezone

import requests
import random
import time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SPORTS = ["MLB", "NBA", "NFL", "NHL", "WNBA"]
SLUG_MAP = {
    "MLB": "baseball/mlb", "NBA": "basketball/nba", "NFL": "football/nfl",
    "NHL": "hockey/nhl", "WNBA": "basketball/wnba",
}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _read_gist_file(filename: str) -> dict | None:
    r = requests.get(f"https://api.github.com/gists/{GIST_ID}", timeout=20)
    if r.status_code != 200:
        return None
    f = r.json().get("files", {}).get(filename)
    if not f:
        return None
    content = f.get("content", "")
    if f.get("truncated") or not content:
        content = requests.get(f["raw_url"], timeout=20).text
    try:
        return json.loads(content)
    except Exception:
        return None


def fetch_espn_odds(sport: str) -> list:
    path = SLUG_MAP[sport]
    today_str = date.today().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={today_str}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    data = r.json()
    events = data.get("events", [])
    out = []
    for event in events:
        matchup = event.get("shortName", "")
        home_team, away_team = "", ""
        home_ml, away_ml = None, None
        spread_detail, over_under = None, None
        for comp in event.get("competitions", []):
            odds_data = comp.get("odds", [{}])[0] if comp.get("odds") else {}
            spread_detail = odds_data.get("details")
            over_under = odds_data.get("overUnder")
            home_ml = odds_data.get("homeTeamOdds", {}).get("moneyLine")
            away_ml = odds_data.get("awayTeamOdds", {}).get("moneyLine")
            for competitor in comp.get("competitors", []):
                team_name = competitor.get("team", {}).get("displayName", "")
                if competitor.get("homeAway") == "home":
                    home_team = team_name
                else:
                    away_team = team_name
        if not (home_team and away_team):
            continue
        out.append({
            "matchup": matchup, "home_team": home_team, "away_team": away_team,
            "opening_home_ml": home_ml, "opening_away_ml": away_ml,
            "opening_spread": spread_detail, "opening_total": over_under,
        })
    return out


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 4:
                wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                time.sleep(wait)
                continue
            if missing:
                log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                return len(files_payload) - len(missing)
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 4:
            base_wait = min(10 * (2 ** attempt), 90)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget for this shared token before
    doing any writes. With ~30 scripts sharing one token/Gist, the hourly
    5000-request budget can run dry during a busy stretch (confirmed real:
    2026-07-25 06:17-06:40 UTC, 403 'API rate limit exceeded for user ID').
    When that happens, skip this run cleanly (exit 0) instead of burning
    retries against an already-exhausted budget and getting flagged as a
    failure -- the next scheduled run picks the data back up once the
    hourly window resets."""
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} requests left this hour) -- skipping this run cleanly, next scheduled run will pick it up")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) -- proceeding anyway")
    return True


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    if not _rate_limit_ok(github_token):
        try:
            requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": {"betcouncil_oddsportal_debug.json": {
                    "content": json.dumps({"reached": "rate_limit_ok returned False, early exit", "at": datetime.now(timezone.utc).isoformat()})
                }}},
                timeout=15,
            )
        except Exception:
            pass
        return 0

    today_str = date.today().isoformat()
    files_payload = {}
    captured, skipped = 0, 0
    _skip_log = []

    for sport in SPORTS:
        filename = f"betcouncil_oddsportal_{sport}.json"
        existing = _read_gist_file(filename)
        _skip_log.append({"sport": sport, "existing_capture_date": (existing or {}).get("capture_date"), "today_str": today_str})
        if existing and existing.get("capture_date") == today_str and existing.get("data"):
            skipped += 1
            log(f"  {sport}: already captured today's opening lines — leaving as-is")
            continue
        try:
            events = fetch_espn_odds(sport)
        except Exception as e:
            log(f"  {sport}: fetch error — {e}")
            continue
        if not events:
            log(f"  {sport}: no games/odds today")
            continue
        files_payload[filename] = {
            "content": json.dumps({
                "source": "espn_opening_lines", "sport": sport,
                "capture_date": today_str,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "data": events,
            })
        }
        captured += 1
        log(f"  {sport}: captured {len(events)} games as today's opening lines")

    if not files_payload:
        log(f"Nothing new to push ({skipped} already captured today, 0 new)")
        try:
            requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": {"betcouncil_oddsportal_debug.json": {
                    "content": json.dumps({"reached": "files_payload empty after loop", "skip_log": _skip_log, "at": datetime.now(timezone.utc).isoformat()})
                }}},
                timeout=15,
            )
        except Exception:
            pass
        return 0

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files ({captured} newly captured, {skipped} already had today's snapshot)")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
