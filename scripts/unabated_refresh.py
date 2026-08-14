"""
unabated_refresh.py — Unabated props + straight lines
================================================================================
Confirmed working endpoints (2026-07-18, no auth required):
  https://data.unabated.com/bettype
  https://data.unabated.com/market/{sport}/props/odds   (~38MB raw, extracted here)
  https://data.unabated.com/market/{sport}/props/people
  https://data.unabated.com/market/{sport}/straight/odds

Required headers: standard User-Agent + Referer: https://unabated.com/
Source IDs in marketSourceLines: 72=PrizePicks, 73=Underdog, 84=Pick6
Sports supported: mlb, nfl, nba, wnba, nhl, pga, ufc, cbb, cfb
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SPORTS = ["mlb"]   # extend as needed: ["mlb", "nfl", "nba"]

# Source ID labels for reference — subset visible in marketSourceLines keys
SOURCE_LABELS = {72: "PrizePicks", 73: "Underdog", 84: "Pick6"}

# Hard safety cap as defense-in-depth beyond the time-window filter --
# a single Gist PATCH failed at 46MB/132k rows (422 "contents are too
# large"), so even a busy slate shouldn't be allowed to blow past a size
# that's comfortably under whatever the real limit is. Keep the soonest-
# starting events first when truncating.
MAX_ROWS_PER_FILE = 8000

HEADERS = {
    "Accept": "application/json",
    "Referer": "https://unabated.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_cdn_league_odds(league_id: int, timeout: int = 45):
    """Real fix attempt (2026-08-14): old data.unabated.com confirmed dead
    (401, matches the live failing workflow this was written to fix).
    Targets the CDN endpoint reported as open/no-auth. Could not verify
    from the environment that wrote this (network-blocked to this
    domain) -- defensively parsed so a wrong structure logs and returns
    None rather than crashing the whole run."""
    url = f"https://content.unabated.com/markets/v2/league/{league_id}/odds.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except Exception as e:
        log(f"CDN request error {url}: {e}")
        DEBUG_LOG.append({"url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"url": url, "status": r.status_code, "body_snippet": r.text[:300]})
    if r.status_code != 200:
        log(f"CDN HTTP {r.status_code} for {url}: {r.text[:200]}")
        return None
    try:
        return r.json()
    except Exception as e:
        log(f"CDN JSON parse error {url}: {e}")
        DEBUG_LOG.append({"url": url, "note": "json_parse_error", "error": str(e)})
        return None


def flatten_cdn_straight_lines(data, league_id: int) -> list:
    """Defensive parse of the CDN v2 odds file into flat straight-line
    rows. Real structure unconfirmed -- tries the shape described
    (pt1 = full game, nested by book/market source), logs and returns []
    on anything unexpected rather than crashing."""
    rows = []
    if not isinstance(data, dict):
        log("CDN response not a dict -- unexpected structure")
        return rows
    try:
        events = data.get("events") or data.get("data", {}).get("events") or []
        if not events and isinstance(data.get("data"), list):
            events = data["data"]
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("eventId") or event.get("id")
            event_start = event.get("eventStart") or event.get("start", "")
            home = event.get("homeTeam") or event.get("home", "")
            away = event.get("awayTeam") or event.get("away", "")
            periods = event.get("periods") or event.get("periodTypes") or {}
            pt1 = periods.get("pt1") if isinstance(periods, dict) else None
            if not pt1:
                continue
            sources = pt1.get("marketSourceLines") or pt1.get("sources") or {}
            for src_id, src_data in (sources.items() if isinstance(sources, dict) else []):
                if not isinstance(src_data, dict):
                    continue
                rows.append({
                    "event_id": event_id, "event_start": event_start,
                    "home": home, "away": away, "league_id": league_id,
                    "source_id": src_id, "raw": src_data,
                })
    except Exception as e:
        log(f"CDN parse error: {e}")
        DEBUG_LOG.append({"note": "cdn_parse_error", "error": str(e)})
    return rows


def fetch_json(url: str, timeout: int = 45):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except Exception as e:
        log(f"Request error {url}: {e}")
        DEBUG_LOG.append({"url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"url": url, "status": r.status_code, "body_snippet": r.text[:300]})
    if r.status_code != 200:
        log(f"HTTP {r.status_code} for {url}: {r.text[:200]}")
        return None
    try:
        return r.json()
    except Exception as e:
        log(f"JSON parse error {url}: {e}")
        DEBUG_LOG.append({"url": url, "note": "json_parse_error", "error": str(e)})
        return None


def build_bettype_map(data) -> dict:
    """betTypeId (int) -> name (str)"""
    result = {}
    if not data:
        return result
    # handle list or dict responses
    items = data if isinstance(data, list) else data.get("data", data)
    if isinstance(items, dict):
        items = list(items.values())
    for item in items:
        if isinstance(item, dict):
            bt_id = item.get("betTypeId") or item.get("id")
            name = item.get("name") or item.get("betTypeName") or str(bt_id)
            if bt_id is not None:
                result[int(bt_id)] = name
    return result


def build_people_map(data) -> dict:
    """personId (int) -> name (str)"""
    result = {}
    if not data:
        return result
    items = data if isinstance(data, list) else data.get("data", data)
    if isinstance(items, dict):
        # may be keyed by personId
        for k, v in items.items():
            if isinstance(v, dict):
                pid = v.get("personId") or v.get("id")
                name = v.get("name") or v.get("fullName") or v.get("playerName")
                if pid is not None and name:
                    result[int(pid)] = name
    elif isinstance(items, list):
        for item in items:
            pid = item.get("personId") or item.get("id")
            name = item.get("name") or item.get("fullName") or item.get("playerName")
            if pid is not None and name:
                result[int(pid)] = name
    return result


def _event_in_window(event_start: str, past_hours: int = 6, future_hours: int = 72) -> bool:
    """Keep only events starting within [-past_hours, +future_hours] of now.
    Without this, the props/odds endpoint returns every scheduled game for
    the rest of the season, not just near-term ones -- that's what blew
    the extracted payload up to 132k rows / 46MB, well over Gist's size
    limit, causing every push to fail with a 422."""
    if not event_start:
        return False
    try:
        start = datetime.fromisoformat(event_start.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return (now - timedelta(hours=past_hours)) <= start <= (now + timedelta(hours=future_hours))


def flatten_props_odds(data, bettype_map: dict, people_map: dict) -> list:
    """
    Extract compact prop rows from the deeply-nested props/odds response.
    Output: one row per (event, betType, side/player, marketSource).
    Filtered to near-term events and to the 3 market sources this
    integration targets (PrizePicks/Underdog/Pick6) -- see
    _event_in_window and SOURCE_LABELS.
    """
    rows = []
    try:
        leagues = data["data"]["odds"]
    except (KeyError, TypeError):
        log("Unexpected props/odds structure — missing data.odds")
        return rows

    for sport_key, league_obj in leagues.items():
        period_types = league_obj.get("periodTypes", {})
        for period_name, period_obj in period_types.items():
            for phase_name in ("pregame", "live"):
                phase = period_obj.get(phase_name, {})
                for composite_key, record in phase.items():
                    event_id = record.get("eventId")
                    event_name = record.get("eventName", "")
                    event_start = record.get("eventStart")
                    if not _event_in_window(event_start):
                        continue
                    bet_type_id = record.get("betTypeId")
                    bet_type_name = bettype_map.get(bet_type_id, str(bet_type_id))

                    for side_key, side_obj in record.get("sides", {}).items():
                        person_id = side_obj.get("personId")
                        player_name = people_map.get(person_id, "") if person_id else ""
                        for src_id_str, line in side_obj.get("marketSourceLines", {}).items():
                            try:
                                src_id = int(src_id_str)
                            except ValueError:
                                src_id = src_id_str
                            if src_id not in SOURCE_LABELS:
                                continue
                            rows.append({
                                "sport": sport_key,
                                "period": period_name,
                                "phase": phase_name,
                                "event_id": event_id,
                                "event_name": event_name,
                                "event_start": event_start,
                                "bet_type_id": bet_type_id,
                                "bet_type": bet_type_name,
                                "person_id": person_id,
                                "player": player_name,
                                "source_id": src_id,
                                "source": SOURCE_LABELS.get(src_id, str(src_id)),
                                "points": line.get("points"),
                                "price": line.get("price"),
                            })
    return rows


def flatten_straight_odds(data, bettype_map: dict) -> list:
    """
    Extract compact game-line rows from the straight/odds response.
    Output: one row per (event, betType, side, marketSource).
    Filtered to near-term events (see _event_in_window) -- no source-ID
    filter here since game lines should include every real sportsbook,
    unlike props which are scoped to the 3 DFS sources this integration
    targets.
    """
    rows = []
    try:
        leagues = data["data"]["odds"]
    except (KeyError, TypeError):
        log("Unexpected straight/odds structure — missing data.odds")
        return rows

    for sport_key, league_obj in leagues.items():
        period_types = league_obj.get("periodTypes", {})
        for period_name, period_obj in period_types.items():
            for phase_name in ("pregame", "live"):
                phase = period_obj.get(phase_name, {})
                for composite_key, record in phase.items():
                    event_id = record.get("eventId")
                    event_name = record.get("eventName", "")
                    event_start = record.get("eventStart")
                    if not _event_in_window(event_start):
                        continue
                    bet_type_id = record.get("betTypeId")
                    bet_type_name = bettype_map.get(bet_type_id, str(bet_type_id))

                    for side_key, side_obj in record.get("sides", {}).items():
                        for src_id_str, line in side_obj.get("marketSourceLines", {}).items():
                            try:
                                src_id = int(src_id_str)
                            except ValueError:
                                src_id = src_id_str
                            rows.append({
                                "sport": sport_key,
                                "period": period_name,
                                "phase": phase_name,
                                "event_id": event_id,
                                "event_name": event_name,
                                "event_start": event_start,
                                "bet_type_id": bet_type_id,
                                "bet_type": bet_type_name,
                                "side_key": side_key,
                                "source_id": src_id,
                                "source": src_id_str,
                                "points": line.get("points"),
                                "price": line.get("price"),
                            })
    return rows


def push_files(files_payload: dict, github_token: str) -> int:
    """
    Merges into the shared evbets_combined.json.

    UPDATED (2026-08-03): confirmed a real, live production data-loss
    race -- multiple scripts merge into the same shared file on
    independent cron schedules, and a full read-modify-write cycle
    means one script's write can silently clobber another's just-
    written key if their timing overlaps (confirmed happening for
    real: wagerbird/sportsinsights/unabated all independently observed
    missing after other scripts' writes landed in between). Added an
    outer retry: after a successful write, re-read and verify no
    previously-present key vanished (not just that OUR key landed) --
    if one did, redo the entire read-modify-write cycle from a fresh
    read, up to 3 times total.
    """
    SHARED_FILE = "betcouncil_sharp_feeds.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_unabated_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

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
        existing["unabated"] = merged
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        write_ok = False
        for attempt in range(5):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    write_ok = True
                    break
                if attempt < 4:
                    wait = min((attempt + 1) * 5, 30)
                    log(f"Push returned 200 but {SHARED_FILE} missing from response -- retrying in {wait}s")
                    time.sleep(wait)
                    continue
                log(f"Push returned 200 but {SHARED_FILE} still missing after retries -- treating as failed")
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 4:
                base_wait = min(10 * (2 ** attempt), 90)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0

        if not write_ok:
            return 0

        # Verify no previously-present key vanished (a concurrent writer's
        # stale read clobbering our just-written state).
        try:
            time.sleep(2)
            r2 = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                               headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                               timeout=15)
            raw_url2 = r2.json().get("files", {}).get(SHARED_FILE, {}).get("raw_url")
            post_write = requests.get(raw_url2, timeout=15).json() if raw_url2 else {}
            post_write_keys = set(post_write.keys())
            lost_keys = pre_write_keys - post_write_keys - {"unabated"}
            if "unabated" in post_write_keys and not lost_keys:
                return len(files_payload)
            log(f"Post-write verification found lost keys {lost_keys} or missing own key -- retrying full cycle (outer attempt {outer_attempt+1}/3)")
        except Exception as e:
            log(f"Post-write verification failed to check: {e} -- treating write as successful anyway")
            return len(files_payload)

    log("Gave up after 3 full read-modify-write cycles -- concurrent writers kept colliding")
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

    import atexit
    _lock_token = acquire_lock(GIST_ID, github_token, "sharp_feeds", holder="unabated")
    if not _lock_token:
        log("Could not acquire sharp_feeds lock after retries -- skipping this run to avoid a collision")
        return 1
    atexit.register(lambda: release_lock(GIST_ID, github_token, "sharp_feeds", _lock_token))

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()

    # Step 1: fetch lookup tables (small, fast)
    log("Fetching bettype lookup...")
    bettype_raw = fetch_json("https://data.unabated.com/bettype")
    bettype_map = build_bettype_map(bettype_raw)
    log(f"  {len(bettype_map)} bet types loaded")

    files_payload: dict = {}
    total_props_rows = 0
    total_straight_rows = 0

    # Real fix attempt (2026-08-14): try the CDN endpoint for MLB (lg5)
    # straight lines. Separate file, separate from the existing (broken)
    # flow below -- this is a genuine test of an unverified claim, kept
    # isolated so a wrong guess here doesn't take down what already runs.
    log("Trying CDN endpoint for MLB straight lines (lg5)...")
    cdn_mlb = fetch_cdn_league_odds(5)
    if cdn_mlb:
        cdn_rows = flatten_cdn_straight_lines(cdn_mlb, 5)
        log(f"  CDN: {len(cdn_rows)} MLB straight-line rows extracted")
        if cdn_rows:
            if len(cdn_rows) > MAX_ROWS_PER_FILE:
                cdn_rows = cdn_rows[:MAX_ROWS_PER_FILE]
            files_payload["betcouncil_unabated_cdn_mlb.json"] = {
                "content": json.dumps({
                    "source": "unabated_cdn", "sport": "mlb",
                    "captured_at": now_iso, "total": len(cdn_rows),
                    "rows": cdn_rows,
                }, default=str)
            }
    else:
        log("  CDN endpoint did not return usable data")

    for sport in SPORTS:
        # Step 2: player names (per sport)
        log(f"Fetching {sport} people map...")
        people_raw = fetch_json(f"https://data.unabated.com/market/{sport}/props/people")
        people_map = build_people_map(people_raw)
        log(f"  {len(people_map)} players loaded for {sport}")

        # Step 3: props odds (~38MB, extract only needed fields)
        log(f"Fetching {sport} props odds (large response)...")
        props_raw = fetch_json(
            f"https://data.unabated.com/market/{sport}/props/odds", timeout=90
        )
        if props_raw:
            props_rows = flatten_props_odds(props_raw, bettype_map, people_map)
            if len(props_rows) > MAX_ROWS_PER_FILE:
                props_rows.sort(key=lambda r: r.get("event_start") or "9999")
                log(f"  {len(props_rows)} prop rows extracted for {sport} — capping to {MAX_ROWS_PER_FILE} soonest-starting")
                props_rows = props_rows[:MAX_ROWS_PER_FILE]
            else:
                log(f"  {len(props_rows)} prop rows extracted for {sport}")
            total_props_rows += len(props_rows)
            files_payload[f"betcouncil_unabated_props_{sport}.json"] = {
                "content": json.dumps(
                    {
                        "source": "unabated",
                        "sport": sport,
                        "captured_at": now_iso,
                        "total": len(props_rows),
                        "rows": props_rows,
                    },
                    default=str,
                )
            }
        else:
            log(f"  No props data for {sport}")

        # Step 4: straight (game) lines
        log(f"Fetching {sport} straight odds...")
        straight_raw = fetch_json(
            f"https://data.unabated.com/market/{sport}/straight/odds", timeout=60
        )
        if straight_raw:
            straight_rows = flatten_straight_odds(straight_raw, bettype_map)
            if len(straight_rows) > MAX_ROWS_PER_FILE:
                straight_rows.sort(key=lambda r: r.get("event_start") or "9999")
                log(f"  {len(straight_rows)} straight rows extracted for {sport} — capping to {MAX_ROWS_PER_FILE} soonest-starting")
                straight_rows = straight_rows[:MAX_ROWS_PER_FILE]
            else:
                log(f"  {len(straight_rows)} straight rows extracted for {sport}")
            total_straight_rows += len(straight_rows)
            files_payload[f"betcouncil_unabated_lines_{sport}.json"] = {
                "content": json.dumps(
                    {
                        "source": "unabated",
                        "sport": sport,
                        "captured_at": now_iso,
                        "total": len(straight_rows),
                        "rows": straight_rows,
                    },
                    default=str,
                )
            }
        else:
            log(f"  No straight data for {sport}")

    if not files_payload:
        log("No data fetched from any sport/endpoint — pushing debug log and exiting with error")
        push_files(
            {"betcouncil_unabated_debug.json": {
                "content": json.dumps({
                    "captured_at": now_iso, "note": "no_data_graceful",
                    "requests": DEBUG_LOG[:20],
                }, indent=2, default=str)
            }},
            github_token,
        )
        return 1

    log(f"Pushing {len(files_payload)} files to Gist...")
    payload_bytes = sum(len(f.get("content", "")) for f in files_payload.values())
    log(f"  total payload size: {payload_bytes} bytes")
    pushed = push_files(files_payload, github_token)
    log(
        f"Done — {pushed} files pushed | "
        f"{total_props_rows} prop rows | {total_straight_rows} straight rows"
    )
    if pushed == 0:
        # The real payload push failed (DEBUG_LOG already has the status/
        # body from push_files above) -- retry with just a small debug
        # file on its own, since the failure may be a size issue (422)
        # that would recur if we tried to push the full payload again.
        push_files(
            {"betcouncil_unabated_debug.json": {
                "content": json.dumps({
                    "captured_at": now_iso, "note": "main_push_failed",
                    "payload_bytes": payload_bytes,
                    "total_props_rows": total_props_rows,
                    "total_straight_rows": total_straight_rows,
                    "requests": DEBUG_LOG[-10:],
                }, indent=2, default=str)
            }},
            github_token,
        )
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("UNHANDLED EXCEPTION:\n" + tb)
        try:
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                push_files(
                    {
                        "betcouncil_unabated_debug.json": {
                            "content": json.dumps(
                                {
                                    "captured_at": datetime.now(timezone.utc).isoformat(),
                                    "error": "unhandled_exception",
                                    "traceback": tb,
                                },
                                indent=2,
                            )
                        }
                    },
                    token,
                )
        except Exception:
            pass
        sys.exit(1)
