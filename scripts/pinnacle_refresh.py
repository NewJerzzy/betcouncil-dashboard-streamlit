"""
pinnacle_refresh.py -- headless Pinnacle Arcadia fetch, runs via GitHub
Actions on a schedule.

Why this exists: guest.api.arcadia.pinnacle.com is confirmed open,
no-auth, and live -- but the existing in-app fetch (fetchers.py
fetch_pinnacle_game_lines) only runs when the Streamlit app itself
calls it, and that domain is DNS-blocked on Streamlit Cloud (documented
directly in fetchers.py's own comment: "DNS-blocked on Streamlit Cloud
-- use when self-hosted"). This never had anything to do with a schema
mismatch -- there was simply no path that could ever reach this API
from the deployed app. This script runs on a GitHub Actions runner
instead, which isn't DNS-blocked, and pushes the result to the Gist so
the app can read it like every other source.

Reuses the exact parsing logic already proven correct in
fetch_pinnacle_game_lines, just without the Streamlit/session-state
dependencies.
"""
import os
import sys
import json
import time
from datetime import datetime, timezone

import requests

GIST_ID = os.environ.get("GIST_ID", "7e52e1c2c2054847c7c4663a157386c5")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock  # noqa: E402

ARCADIA_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
ARCADIA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
}
SPORT_LEAGUE_IDS = {
    "MLB": 246, "NBA": 487, "WNBA": 578, "NFL": 889, "NHL": 1456,
}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def arcadia_get(path: str):
    try:
        r = requests.get(f"{ARCADIA_BASE}{path}", headers=ARCADIA_HEADERS, timeout=15)
        if r.status_code != 200:
            log(f"HTTP {r.status_code} for {path}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        log(f"Request error for {path}: {e}")
        return None


def pinn_american(price):
    if price is None:
        return None
    try:
        return int(price)
    except (TypeError, ValueError):
        return None


def fetch_sport(sport: str, league_id: int) -> list:
    matchups_data = arcadia_get(f"/leagues/{league_id}/matchups")
    if not matchups_data:
        return []

    matchup_teams = {}
    matchup_start = {}
    for mu in matchups_data:
        if mu.get("type") != "matchup":
            continue
        mid = mu.get("id")
        if not mid:
            continue
        home = away = ""
        for p in mu.get("participants", []):
            alignment = p.get("alignment", "")
            name = p.get("name", "")
            if alignment == "home":
                home = name
            elif alignment == "away":
                away = name
        matchup_teams[mid] = {"home": home, "away": away}
        matchup_start[mid] = mu.get("startTime") or mu.get("cutoffAt")

    markets_data = arcadia_get(f"/leagues/{league_id}/markets/straight")
    if not markets_data:
        return []

    game_markets = {}
    for market in markets_data:
        mid = market.get("matchupId")
        period = market.get("period", 0)
        mtype = market.get("type", "")
        prices = market.get("prices", [])
        if period != 0 or market.get("isAlternate") or not mid or mid not in matchup_teams:
            continue
        if mid not in game_markets:
            game_markets[mid] = {}

        if mtype == "moneyline":
            ml = {}
            for p in prices:
                desig = p.get("designation", "")
                if desig == "home":
                    ml["home"] = pinn_american(p.get("price"))
                elif desig == "away":
                    ml["away"] = pinn_american(p.get("price"))
            if ml:
                game_markets[mid]["moneyline"] = ml
        elif mtype == "spread":
            sp = {}
            for p in prices:
                desig = p.get("designation", "")
                if desig == "home":
                    sp["hdp"] = p.get("points")
                    sp["home_price"] = pinn_american(p.get("price"))
                elif desig == "away":
                    sp["away_price"] = pinn_american(p.get("price"))
            if sp:
                game_markets[mid]["spread"] = sp
        elif mtype == "total":
            tot = {}
            for p in prices:
                desig = p.get("designation", "")
                if desig == "over":
                    tot["points"] = p.get("points")
                    tot["over_price"] = pinn_american(p.get("price"))
                elif desig == "under":
                    tot["under_price"] = pinn_american(p.get("price"))
            if tot:
                game_markets[mid]["total"] = tot

    results = []
    for mid, teams in matchup_teams.items():
        home, away = teams.get("home", ""), teams.get("away", "")
        if not home or not away:
            continue
        mkts = game_markets.get(mid, {})
        ml, sp, tot = mkts.get("moneyline", {}), mkts.get("spread", {}), mkts.get("total", {})
        is_closing = False
        start_raw = matchup_start.get(mid)
        if start_raw:
            try:
                start_dt = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
                minutes_to_start = (start_dt - datetime.now(timezone.utc)).total_seconds() / 60
                is_closing = 0 <= minutes_to_start <= 30
            except (ValueError, TypeError):
                pass
        results.append({
            "MatchupId": mid,
            "Matchup": f"{away} @ {home}", "Home": home, "Away": away,
            "HomeML": ml.get("home"), "AwayML": ml.get("away"),
            "Spread": sp.get("hdp"), "SpreadOdds": sp.get("home_price"),
            "Total": tot.get("points"), "TotalOver": tot.get("over_price"),
            "TotalUnder": tot.get("under_price"),
            "Book": "Pinnacle", "Sport": sport, "source": "pinnacle_lines",
            "StartTime": start_raw, "IsClosing": is_closing,
        })
    return results


def push_files(files_payload: dict, github_token: str) -> int:
    if not files_payload:
        return 0
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": files_payload}, timeout=30,
    )
    if resp.status_code != 200:
        log(f"Gist push failed: HTTP {resp.status_code} {resp.text[:200]}")
        return 0
    return len(files_payload)


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    import atexit
    lock_token = acquire_lock(GIST_ID, github_token, "sharp_feeds", holder="pinnacle", max_attempts=6)
    if not lock_token:
        log("Could not acquire sharp_feeds lock -- skipping this run")
        return 1
    atexit.register(lambda: release_lock(GIST_ID, github_token, "sharp_feeds", lock_token))

    files_payload = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    total_rows = 0
    all_closing_rows = []

    for sport, league_id in SPORT_LEAGUE_IDS.items():
        rows = fetch_sport(sport, league_id)
        log(f"{sport}: {len(rows)} rows")
        if rows:
            total_rows += len(rows)
            files_payload[f"betcouncil_pinnacle_{sport}.json"] = {
                "content": json.dumps({
                    "source": "pinnacle_arcadia", "sport": sport,
                    "captured_at": now_iso, "total": len(rows), "data": rows,
                }, default=str)
            }
            closing_now = [r for r in rows if r.get("IsClosing")]
            for r in closing_now:
                r["Sport"] = sport
            all_closing_rows.extend(closing_now)
        time.sleep(1)

    # Real closing-line accumulator: merge newly-closing games into whatever
    # was already captured, keyed by MatchupId, so a game captured on one
    # run isn't lost or overwritten by a later run once it's live/finished.
    if all_closing_rows:
        try:
            existing_resp = requests.get(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}"}, timeout=15,
            )
            existing_files = existing_resp.json().get("files", {})
            existing_content = {}
            cl_file = existing_files.get("betcouncil_unabated_closing_lines.json")
            if cl_file and cl_file.get("content"):
                existing_content = json.loads(cl_file["content"]).get("by_matchup", {})
        except Exception as e:
            log(f"Could not read existing closing lines (starting fresh): {e}")
            existing_content = {}

        for r in all_closing_rows:
            key = str(r.get("MatchupId"))
            if key not in existing_content:
                existing_content[key] = r

        files_payload["betcouncil_pinnacle_closing_lines.json"] = {
            "content": json.dumps({
                "source": "pinnacle_arcadia_closing", "captured_at": now_iso,
                "total": len(existing_content), "by_matchup": existing_content,
            }, default=str)
        }
        log(f"Closing lines: {len(all_closing_rows)} new, {len(existing_content)} total accumulated")

    if not files_payload:
        log("No data from any sport -- nothing written")
        return 0

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files, {total_rows} total rows")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
