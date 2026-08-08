"""
prophetx_harvester.py — ProphetX exchange odds harvester (all sports)
=======================================================================
Runs every 15 min via .github/workflows/prophetx_refresh.yml.

ProphetX is a US prediction/betting exchange proxied through
www.prophetx.co (CloudFront, same-origin). Public, unauthenticated API —
no token, no login, just two static headers.

Endpoints used:
  GET /trade/public/api/v1/sports                        -> sport id map
  GET /trade/public/api/v1/events?limit=500               -> all events
  GET /trade/public/api/v2/events/{id}/markets             -> markets + live odds
  GET /commission/public/commissions?event_ids={id,id,..} -> commission rates

Pipeline:
  1. Pull the sport list and the full event list (limit=500 covers
     everything in one call — the `sport` query param is broken upstream
     and returns all events regardless, so we filter client-side instead).
  2. Classify each event into a BetCouncil sport bucket (NFL/NBA/MLB/NHL/
     WNBA/MMA/TENNIS/GOLF/SOCCER/OTHER) using whatever sport/league fields
     are present, falling back to keyword matching on the event title.
  3. Pull the v2 markets payload for every event (raw pass-through — exact
     market schema is captured as-is since it hasn't been fully mapped
     against BetCouncil's internal prop/line normalizer yet).
  4. Pull commission rates in batched chunks.
  5. Push one Gist file per sport bucket (betcouncil_prophetx_{SPORT}.json)
     plus a combined betcouncil_prophetx_all.json and a
     betcouncil_prophetx_sports.json id map, mirroring the existing
     per-sport Gist convention every other harvester in this repo uses.

This is a raw capture layer. Normalizing ProphetX's market shape into
BetCouncil's internal prop/line format (like fetch_polymarket_from_gist's
downstream consumers do) is a separate follow-up once the live shape is
inspected — fetch_prophetx_from_gist() in fetchers.py just returns this
raw payload today.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
import random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gist_lock import acquire_lock, release_lock

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

BASE = "https://www.prophetx.co"
HEADERS = {
    "x-currency": "cash",
    "__source": "web",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

EVENTS_LIMIT = 500
COMMISSION_CHUNK_SIZE = 25
MARKET_FETCH_DELAY_SEC = 0.05  # be polite across ~130+ sequential calls

# BetCouncil sport buckets <- keyword fallbacks for classifying events
# whose payload doesn't cleanly expose a sport name.
SPORT_KEYWORDS = {
    "NFL":    ["nfl", "football"],
    "NBA":    ["nba"],
    "WNBA":   ["wnba"],
    "MLB":    ["mlb", "baseball"],
    "NHL":    ["nhl", "hockey"],
    "MMA":    ["ufc", "mma", "fight night"],
    "TENNIS": ["tennis", "atp", "wta", "grand slam"],
    "GOLF":   ["golf", "pga", "open championship", "masters", "ryder cup"],
    "SOCCER": ["soccer", "premier league", "world cup", "la liga", "champions league",
               "bundesliga", "serie a", "ligue 1", "mls"],
}


def log(msg):
    print(f"[prophetx] {msg}", flush=True)


def _http_get_json(path_or_url, params=None, timeout=15, retries=2):
    url = path_or_url if path_or_url.startswith("http") else f"{BASE}{path_or_url}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    log(f"  GET failed ({url[:100]}): {last_err}")
    return None


# ── Step 1: sports + events ─────────────────────────────────────────────
def fetch_sports():
    data = _http_get_json("/trade/public/api/v1/sports")
    return data if data is not None else []


def fetch_events(limit=EVENTS_LIMIT):
    data = _http_get_json("/trade/public/api/v1/events", {"limit": limit})
    if isinstance(data, dict):
        # tolerate either a bare list or a {"events": [...]} / {"data": [...]} envelope
        for key in ("events", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    return data if isinstance(data, list) else []


def _event_text_blob(event: dict) -> str:
    parts = []
    for key in ("name", "title", "display_name", "event_name", "league", "league_name",
                "sport_name", "category", "competition"):
        v = event.get(key)
        if isinstance(v, str):
            parts.append(v)
    # nested sport/league objects
    for key in ("sport", "league", "competition"):
        v = event.get(key)
        if isinstance(v, dict):
            for sub in ("name", "display_name", "title"):
                if isinstance(v.get(sub), str):
                    parts.append(v[sub])
    home = event.get("home_team") or event.get("home") or ""
    away = event.get("away_team") or event.get("away") or ""
    if isinstance(home, dict):
        home = home.get("name", "")
    if isinstance(away, dict):
        away = away.get("name", "")
    parts.append(str(home))
    parts.append(str(away))
    return " ".join(parts).lower()


def classify_sport(event: dict, sport_id_map: dict) -> str:
    # direct sport_id lookup first, if the id map resolved a usable name
    sid = event.get("sport_id") or event.get("sportId")
    if sid is not None and sid in sport_id_map:
        name = str(sport_id_map[sid]).upper().strip()
        known_buckets = ("NFL", "WNBA", "NBA", "MLB", "NHL", "MMA", "TENNIS", "GOLF", "SOCCER")
        if name in known_buckets:
            return name
        # substring fallback, longest bucket name first so "WNBA" wins over "NBA"
        for bucket in sorted(known_buckets, key=len, reverse=True):
            if bucket in name:
                return bucket

    blob = _event_text_blob(event)
    for bucket, keywords in SPORT_KEYWORDS.items():
        if any(kw in blob for kw in keywords):
            return bucket
    return "OTHER"


# ── Step 3: markets per event ───────────────────────────────────────────
def fetch_markets_for_event(event_id):
    return _http_get_json(f"/trade/public/api/v2/events/{event_id}/markets")


# ── Step 4: commissions, batched ────────────────────────────────────────
def fetch_commissions(event_ids: list) -> dict:
    out = {}
    for i in range(0, len(event_ids), COMMISSION_CHUNK_SIZE):
        chunk = event_ids[i:i + COMMISSION_CHUNK_SIZE]
        data = _http_get_json(
            "/commission/public/commissions",
            {"event_ids": ",".join(str(x) for x in chunk)},
        )
        if isinstance(data, dict):
            # Real shape: {"commissions": [{commission, eventId, marketId, ...}], "length": N}
            for row in data.get("commissions", []):
                eid = str(row.get("eventId") or row.get("event_id") or "")
                if eid:
                    out.setdefault(eid, []).append(row)
        elif isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                eid = str(row.get("eventId") or row.get("event_id") or "")
                if eid:
                    out.setdefault(eid, []).append(row)
    return out


# ── Gist push ────────────────────────────────────────────────────────────
def push_merged_to_gist(sports_payload: dict, buckets_payload: dict) -> bool:
    """
    Merges all per-sport-bucket ProphetX files into ONE file
    (betcouncil_prophetx_combined.json) instead of 10+ separate files.
    Confirmed real: all 10 sport buckets (NFL/NBA/WNBA/MLB/NHL/MMA/
    TENNIS/GOLF/SOCCER/OTHER) are genuinely read by fetch_prophetx_from_gist,
    unlike PrizePicks' fringe leagues -- this reduces file COUNT while
    keeping all real data, using the real distributed lock since this
    now writes to one shared file.
    """
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False
    SHARED_FILE = "betcouncil_prophetx_combined.json"

    lock_token = acquire_lock(GIST_ID, GITHUB_TOKEN, "prophetx_combined", holder="prophetx")
    if not lock_token:
        log("Could not acquire prophetx_combined lock -- skipping this run to avoid a collision")
        return False
    try:
        try:
            req = urllib.request.Request(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                listing = json.loads(r.read())
            r_files = listing.get("files", {})
            if SHARED_FILE in r_files:
                with urllib.request.urlopen(r_files[SHARED_FILE]["raw_url"], timeout=15) as r2:
                    existing = json.loads(r2.read())
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        existing["sports"] = sports_payload
        existing.update(buckets_payload)
        body = json.dumps({"files": {SHARED_FILE: {"content": json.dumps(existing, default=str)}}}).encode()

        for attempt in range(4):
            req = urllib.request.Request(
                f"https://api.github.com/gists/{GIST_ID}", data=body, method="PATCH",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    if r.status != 200:
                        return False
                    resp_body = json.loads(r.read())
                    if SHARED_FILE in (resp_body.get("files") or {}):
                        return True
                    log(f"  Push returned 200 but {SHARED_FILE} missing from response -- retrying")
            except urllib.error.HTTPError as e:
                if e.code in (403, 429, 409) and attempt < 3:
                    wait = 8 * (attempt + 1)
                    log(f"  Gist push got HTTP {e.code} -- retrying in {wait}s (attempt {attempt+1}/4)")
                    time.sleep(wait)
                    continue
                log(f"  Gist push failed: HTTP {e.code}")
                return False
            except Exception as e:
                log(f"  Gist push failed: {e}")
                return False
            if attempt < 3:
                time.sleep(5)
        return False
    finally:
        release_lock(GIST_ID, GITHUB_TOKEN, "prophetx_combined", lock_token)


def push_to_gist(key: str, payload: dict) -> bool:
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False
    body = json.dumps({"files": {key: {"content": json.dumps(payload, indent=2, default=str)}}}).encode()
    for attempt in range(3):
        req = urllib.request.Request(
            f"https://api.github.com/gists/{GIST_ID}",
            data=body,
            method="PATCH",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status != 200:
                    return False
                resp_body = json.loads(r.read())
                if key in (resp_body.get("files") or {}):
                    return True
                log(f"  Push returned 200 but {key} missing from response -- retrying")
                if attempt < 2:
                    import time as _t
                    _t.sleep(5 * (attempt + 1))
                    continue
                return False
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 409) and attempt < 2:
                base_wait = 10 * (2 ** attempt)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"  Gist push got HTTP {e.code} -- retrying in {wait:.1f}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            log(f"  Gist push failed for {key}: HTTP {e.code} {e.read()[:300]}")
            return False
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            # Previously only HTTPError was caught here -- a socket timeout on
            # the multi-MB payloads (all.json/MLB.json) raises URLError, not
            # HTTPError, and was propagating uncaught, crashing the whole
            # harvester with no debug output. Treat it like a retryable
            # server hiccup instead.
            if attempt < 2:
                base_wait = 10 * (2 ** attempt)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"  Gist push errored for {key}: {e} -- retrying in {wait:.1f}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            log(f"  Gist push failed for {key}: {e}")
            return False
    return False


def run():
    log("Fetching sports list...")
    sports_raw = fetch_sports()
    # build id -> name map defensively regardless of exact schema
    sport_id_map = {}
    if isinstance(sports_raw, list):
        for s in sports_raw:
            if isinstance(s, dict):
                sid = s.get("id") or s.get("sport_id")
                name = s.get("name") or s.get("display_name")
                if sid is not None and name:
                    sport_id_map[sid] = name
    log(f"  {len(sport_id_map)} sports mapped")

    log("Fetching events (limit=500)...")
    events = fetch_events()
    if not events:
        log("No events returned — aborting without overwriting existing data")
        sys.exit(0)
    log(f"  {len(events)} events pulled")

    buckets = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        eid = ev.get("id") or ev.get("event_id")
        if eid is None:
            continue
        sport_bucket = classify_sport(ev, sport_id_map)
        buckets.setdefault(sport_bucket, []).append(ev)

    log("Sport breakdown: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(buckets.items())))

    log("Fetching markets for every event...")
    event_ids = [ev.get("id") or ev.get("event_id") for ev in events]
    markets_by_event = {}
    fetched, failed = 0, 0
    for eid in event_ids:
        m = fetch_markets_for_event(eid)
        if m is not None:
            markets_by_event[str(eid)] = m
            fetched += 1
        else:
            failed += 1
        time.sleep(MARKET_FETCH_DELAY_SEC)
    log(f"  markets: {fetched} fetched, {failed} failed")

    log("Fetching commission rates...")
    commissions_by_event = fetch_commissions(event_ids)
    log(f"  commissions: {len(commissions_by_event)} event entries")

    now_iso = datetime.now(timezone.utc).isoformat()

    def enrich(ev):
        eid = str(ev.get("id") or ev.get("event_id"))
        return {
            **ev,
            "markets": markets_by_event.get(eid),
            "commissions": commissions_by_event.get(eid),
        }

    sports_payload = {
        "captured_at": now_iso, "updated": now_iso,
        "sport_id_map": sport_id_map,
    }
    buckets_payload = {}
    for bucket, bucket_events in buckets.items():
        buckets_payload[bucket] = {
            "captured_at": now_iso, "updated": now_iso,
            "sport": bucket,
            "event_count": len(bucket_events),
            "events": [enrich(ev) for ev in bucket_events],
        }
        log(f"  {bucket}: {len(bucket_events)} events")

    all_ok = push_merged_to_gist(sports_payload, buckets_payload)

    if not all_ok:
        # Previously exited here with zero diagnostic trail left in the Gist
        # -- only visible in GH Actions logs, which aren't reliably
        # reachable for diagnosis. Best-effort push a debug summary.
        try:
            push_to_gist("betcouncil_prophetx_debug.json", {
                "captured_at": now_iso,
                "error": "merged_push_failed",
            })
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("UNHANDLED EXCEPTION:\n" + tb)
        try:
            push_to_gist("betcouncil_prophetx_debug.json", {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "error": "unhandled_exception",
                "traceback": tb,
            })
        except Exception:
            pass  # don't let debug-push failure mask the real error's exit code
        sys.exit(1)
