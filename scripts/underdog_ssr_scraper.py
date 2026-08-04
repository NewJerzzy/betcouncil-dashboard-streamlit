"""
underdog_ssr_scraper.py — Underdog Fantasy props scraper (public API, no auth)
================================================================================

Runs on GitHub Actions on a schedule. Uses Underdog's public
beta/v6/over_under_lines endpoint (no login, no proxy needed — confirmed
working directly), joins player names via the appearance_id chain, and
reshapes the result into the flat format BetCouncil's existing
_parse_underdog_harvested() already expects:

    {"over_under_lines": [{"player_id", "stat_type", "stat_value", "title"}],
     "players": [{"id", "first_name", "last_name"}]}

Split by sport (players[].sport_id) into separate Gist files named
betcouncil_underdog_{SPORT}.json — matching fetch_underdog_from_gist()'s
existing lookup pattern exactly. No wiring changes needed anywhere else.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://api.underdogfantasy.com/beta/v6/over_under_lines"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_all_lines() -> dict:
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }
    resp = requests.get(API_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_flat_records(payload: dict) -> dict:
    """
    Join over_under_lines -> appearances -> players, and reshape into the
    flat {player_id, stat_type, stat_value, title} shape the existing
    BetCouncil parser expects. Returns {sport: {"over_under_lines": [...],
    "players": [...]}}.
    """
    players_by_id = {p["id"]: p for p in payload.get("players", []) if isinstance(p, dict)}
    appearances_by_id = {a["id"]: a for a in payload.get("appearances", []) if isinstance(a, dict)}

    by_sport: dict = {}

    for line in payload.get("over_under_lines", []):
        if not isinstance(line, dict):
            continue
        ou = line.get("over_under", {}) or {}
        appearance_stat = ou.get("appearance_stat", {}) or {}
        appearance_id = appearance_stat.get("appearance_id")
        display_stat = appearance_stat.get("display_stat", "")
        stat_value = line.get("stat_value")

        appearance = appearances_by_id.get(appearance_id, {})
        player_id = appearance.get("player_id")
        player = players_by_id.get(player_id, {})
        sport = player.get("sport_id", "UNKNOWN")

        # Fallback name from the options[] selection_header if the player
        # join comes up empty for any reason.
        title = None
        options = line.get("options", [])
        if options and isinstance(options, list):
            title = options[0].get("selection_header")

        if not player_id and not title:
            continue
        if stat_value is None:
            continue

        sport_key = str(sport).upper().replace(" ", "_")
        by_sport.setdefault(sport_key, {"over_under_lines": [], "players": {}})

        by_sport[sport_key]["over_under_lines"].append({
            "player_id": player_id,
            "stat_type": display_stat,
            "stat_value": stat_value,
            "title": title,
        })
        if player_id and player_id not in by_sport[sport_key]["players"]:
            by_sport[sport_key]["players"][player_id] = {
                "id": player_id,
                "first_name": player.get("first_name", ""),
                "last_name": player.get("last_name", ""),
            }

    # Convert players dict -> list per sport
    result = {}
    for sport_key, bucket in by_sport.items():
        result[sport_key] = {
            "over_under_lines": bucket["over_under_lines"],
            "players": list(bucket["players"].values()),
        }
    return result


def push_sport_files(by_sport: dict) -> int:
    import time
    github_token = os.environ["GITHUB_TOKEN"]
    now_iso = datetime.now(timezone.utc).isoformat()

    # Confirmed real bug (Aug 2 2026): all 11 betcouncil_underdog_{SPORT}.json
    # filenames have NEVER once landed in the Gist despite every push
    # reporting either success or a detected-and-retried failure -- this
    # Gist reliably cannot create brand-new filenames (proven across 4
    # independent scripts hitting the identical symptom: Underdog,
    # WiseGuyTeam, Unabated, VSIN). Merging into the already-existing,
    # actively-written betcouncil_evbets_combined.json instead, under an
    # "underdog" key -- the same fix that already worked for VSIN splits.
    #
    # UPDATED (2026-08-03): confirmed a real, live production data-loss
    # race -- multiple scripts merge into this same shared file on
    # independent cron schedules, and one script's write can silently
    # clobber another's just-written key if their timing overlaps.
    # Added an outer retry: after a successful write, verify no
    # previously-present key vanished, and redo the whole cycle from a
    # fresh read if one did, up to 3 times total.
    SHARED_FILE = "betcouncil_sharp_feeds.json"
    merged_payload = {sport_key: {
        "sport": sport_key, "captured_at": now_iso, "data": body,
        "source": "github_actions_public_api",
    } for sport_key, body in by_sport.items()}

    for outer_attempt in range(3):
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                raw_url = r_files[SHARED_FILE]["raw_url"]
                existing = requests.get(raw_url, timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        pre_write_keys = set(existing.keys())
        existing["underdog"] = merged_payload
        content = json.dumps(existing)
        files_payload = {SHARED_FILE: {"content": content}}

        write_ok = False
        for attempt in range(4):
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
                returned_files = resp.json().get("files", {}) or {}
                missing = [fn for fn in files_payload if fn not in returned_files]
                if missing and attempt < 4:
                    wait = min((attempt + 1) * 5, 30)
                    log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                    time.sleep(wait)
                    continue
                if missing:
                    log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                    return 0
                write_ok = True
                break
            if resp.status_code in (409, 403, 429) and attempt < 3:
                base_wait = (attempt + 1) * 8
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist {resp.status_code} (conflict or rate limit) — retrying in {wait:.1f}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0

        if not write_ok:
            return 0

        try:
            time.sleep(2)
            r2 = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                               headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                               timeout=15)
            raw_url2 = r2.json().get("files", {}).get(SHARED_FILE, {}).get("raw_url")
            post_write = requests.get(raw_url2, timeout=15).json() if raw_url2 else {}
            post_write_keys = set(post_write.keys())
            lost_keys = pre_write_keys - post_write_keys - {"underdog"}
            if "underdog" in post_write_keys and not lost_keys:
                return len(by_sport)
            log(f"Post-write verification found lost keys {lost_keys} or missing own key -- retrying full cycle (outer attempt {outer_attempt+1}/3)")
        except Exception as e:
            log(f"Post-write verification failed to check: {e} -- treating write as successful anyway")
            return len(by_sport)

    log("Gave up after 3 full read-modify-write cycles -- concurrent writers kept colliding")
    return 0


def main() -> int:
    if not os.environ.get("GITHUB_TOKEN"):
        log("FATAL: GITHUB_TOKEN not set")
        return 1
    github_token = os.environ["GITHUB_TOKEN"]

    import atexit
    _lock_token = acquire_lock(GIST_ID, github_token, "sharp_feeds", holder="underdog")
    if not _lock_token:
        log("Could not acquire sharp_feeds lock after retries -- skipping this run to avoid a collision")
        return 1
    atexit.register(lambda: release_lock(GIST_ID, github_token, "sharp_feeds", _lock_token))

    try:
        payload = fetch_all_lines()
    except Exception as e:
        log(f"FATAL: fetch error — {e}")
        try:
            import requests as _rq, json as _j
            token = os.environ.get("GITHUB_TOKEN")
            _rq.patch(f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                json={"files": {"betcouncil_underdog_MLB.json": {"content": _j.dumps({"TEMP_DIAG_ERROR": str(e), "type": str(type(e))})}}},
                timeout=15)
        except Exception:
            pass
        return 1

    total = len(payload.get("over_under_lines", []))
    log(f"Fetched {total} total over_under_lines")
    if total == 0:
        log("FATAL: zero lines returned")
        return 1

    by_sport = build_flat_records(payload)
    for k, v in by_sport.items():
        log(f"  {k}: {len(v['over_under_lines'])} lines, {len(v['players'])} players")

    pushed = push_sport_files(by_sport)
    log(f"Pushed {pushed} sport files to Gist")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
