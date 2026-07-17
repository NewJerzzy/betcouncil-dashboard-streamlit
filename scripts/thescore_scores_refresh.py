"""
thescore_scores_refresh.py — theScore's public sports/scores API (no auth)
================================================================================

Not the same product as sportsbook.thescore.bet (the GeoComply-gated
betting product investigated earlier this session -- confirmed dead end,
datacenter IPs fail GeoComply outright, closed). This is theScore's
general sports/scores app API (api.thescore.com), a different domain
entirely, confirmed live and public this session:

    GET https://api.thescore.com/{sport}/events/upcoming
        -> array of today's games, each with an "api_uri" like
           "/mlb/events/99313"

    GET https://api.thescore.com/{sport}/events/{id}
        -> full event, including:
             "odd": {"home_odd": "-110", "away_odd": "T:9.5", "over_under": "9.5"}
             "timestamped_odds": [{"money_line_away": "-115",
                                    "money_line_home": "-105",
                                    "total": "9.5", "created_at": "..."}, ...]

Neither field is attributed to a specific book -- "odd" is a single
consensus-like snapshot, "timestamped_odds" is the full line-movement
history leading up to it. Useful as a book-agnostic consensus/movement
reference, not a per-book line source.

Not independently verified byte-for-byte by Claude before this first
deploy (built from a research summary's field names, not re-probed live
from this sandbox -- api.thescore.com isn't in this environment's network
allowlist). Ships with debug logging so a schema drift or unexpected shape
is caught immediately on first live run.

Pushes to betcouncil_thescore_scores_{SPORT}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.thescore.com"
SPORT_PATHS = {"MLB": "mlb", "NBA": "nba", "NFL": "nfl", "NHL": "nhl"}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

MAX_EVENTS_PER_SPORT = 30

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str, sport: str, label: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "label": label, "url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"sport": sport, "label": label, "url": url, "status": r.status_code,
                       "body_snippet": r.text[:400]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def fetch_upcoming(sport_path: str, sport: str) -> list:
    data = fetch_json(f"{BASE_URL}/{sport_path}/events/upcoming", sport, "upcoming")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Defensive: some theScore endpoints wrap the list under a key --
        # try common shapes rather than assuming a bare list.
        for key in ("events", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def normalize(sport: str, sport_path: str) -> list:
    upcoming = fetch_upcoming(sport_path, sport)
    if not upcoming:
        return []

    games = []
    for ev in upcoming[:MAX_EVENTS_PER_SPORT]:
        if not isinstance(ev, dict):
            continue
        api_uri = ev.get("api_uri")
        event_id = ev.get("id") or (api_uri.rsplit("/", 1)[-1] if api_uri else None)
        if not event_id:
            continue
        detail = fetch_json(f"{BASE_URL}/{sport_path}/events/{event_id}", sport, f"event[{event_id}]")
        if not isinstance(detail, dict):
            continue
        games.append({
            "sport": sport,
            "event_id": event_id,
            "home_team": (detail.get("home_team") or {}).get("name") or ev.get("home_team"),
            "away_team": (detail.get("away_team") or {}).get("name") or ev.get("away_team"),
            "game_date": detail.get("game_date") or ev.get("game_date"),
            "odd": detail.get("odd"),  # consensus-like snapshot, unattributed to a book
            "timestamped_odds": detail.get("timestamped_odds"),  # full movement history, unattributed
        })
    return games


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

    for sport, sport_path in SPORT_PATHS.items():
        try:
            games = normalize(sport, sport_path)
        except Exception as e:
            log(f"  {sport}: error — {e}")
            continue
        if not games:
            log(f"  {sport}: 0 games")
            continue
        any_data = True
        log(f"  {sport}: {len(games)} games")
        files_payload[f"betcouncil_thescore_scores_{sport}.json"] = {
            "content": json.dumps({
                "source": "thescore_public_api", "sport": sport,
                "captured_at": now_iso, "games": games,
            })
        }

    files_payload["betcouncil_thescore_scores_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:25]}, indent=2)
    }

    if not any_data:
        log("No data captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
