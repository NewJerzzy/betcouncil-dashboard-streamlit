"""
unabated_refresh.py — Unabated sharp-line comparison (real endpoint found via browser capture)
================================================================================

Two straight URL guesses failed (unabated.com/api/lines and
data.unabated.com/market/{sport}/props/odds both returned a generic
Next.js 404 page server-side). The real endpoint was found by actually
watching a headless Chromium browser load unabated.com and recording
every real XHR/fetch response — see scripts/unabated_playwright_probe.py
for that capture script. This is the real, confirmed-live production
scraper built from what that capture found.

CONFIRMED REAL via live browser capture (2026-07-18):
    Base: https://api-k.unabated.com/api
    GET /markets/changes/query?full_refresh_ISO={ISO timestamp}
        -> full snapshot of current odds. No auth required. Confirmed
           live with real MLB moneyline/spread/total prices flowing
           (e.g. -200, +110, -130 on real games).

Required headers (captured from the real browser request, replicated
here): standard browser User-Agent, Accept: application/json, and
Referer: https://unabated.com/ — no auth token, no cookie needed.

Response shape (real, captured):
    {latestTimestamp, resultCode, results: [{
        latestTimestamp, resultCode, marketSources: [...], events: [...],
        marketLineChanges: [{
            gameOdds: {gameOddsEvents: {
                "{leagueId}:{periodType}:{phase}": [{
                    eventId, eventStart, statusId,
                    gameOddsMarketSourcesLines: {
                        "si{sideIndex}:ms{marketSourceId}:an{altNum}": {
                            "bt{betTypeId}": {
                                marketId, points, price, sourcePrice,
                                sourceFormat, marketSourceId, statusId,
                                sequenceNumber, modifiedOn, sideKey, ...
                            }
                        }
                    }
                }]
            }}
        }]
    }]}

This is a deeply nested, key-encoded structure (league/period/phase
packed into dict keys like "lg5:pt1:pregame", side/book/alt packed into
keys like "si0:ms20:an0") rather than a flat list — flattened here into
one row per (event, market source, bet type) for usability. bet_type_id
and market_source_id -> human names aren't resolved here (would need
the /bet-types and a market-sources lookup, neither confirmed live yet)
so both ship as raw IDs; a follow-up pass can map them once those
lookups are confirmed the same careful way this endpoint was.

Not sport-filtered at the source — the query returns whatever leagues
have live line changes at request time, so a single poll may return
MLB, NFL, CFB, etc. all mixed together. Split by leagueId prefix in the
gameOddsEvents key (lg1=NFL, lg5=MLB, lg7=CFB per real observed data;
unconfirmed mapping for others, logged to debug for follow-up).
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api-k.unabated.com/api"

HEADERS = {
    "Accept": "application/json",
    "Referer": "https://unabated.com/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}

# Observed live 2026-07-18 — unconfirmed for leagues not seen in the
# capture window (logged to debug so a wrong guess here is correctable
# from real data, not blind).
LEAGUE_ID_MAP = {
    "lg1": "NFL", "lg5": "MLB", "lg7": "CFB",
    # not observed live yet, best-guess only:
    "lg2": "NBA", "lg3": "NHL", "lg4": "CBB", "lg6": "WNBA",
    "lg8": "UFC", "lg9": "PGA",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str, params: dict = None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=25)
    except Exception as e:
        DEBUG_LOG.append({"url": url, "params": params, "error": str(e)})
        return None
    DEBUG_LOG.append({"url": url, "params": params, "status": r.status_code,
                       "body_snippet": r.text[:400]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def test_data_unabated_claim(github_token: str) -> None:
    """
    2026-07-18: testing a newly claimed second endpoint from a secondary
    session — data.unabated.com/market/{sport}/props/odds, claimed to
    hold PLAYER PROPS (personId-keyed), which the confirmed-working
    api-k.unabated.com/markets/changes/query endpoint does NOT capture
    (that one only had gameOdds, no props). Different domain than either
    of the two earlier failed guesses on this same "data.unabated.com"
    host, so worth a real test rather than assuming it shares their fate
    or trusting it blind — same standard as every claim in this repo.
    """
    test_results = {}
    for label, url in [
        ("bettype", "https://data.unabated.com/bettype"),
        ("props_odds", "https://data.unabated.com/market/mlb/props/odds"),
        ("props_people", "https://data.unabated.com/market/mlb/props/people"),
        ("straight_odds", "https://data.unabated.com/market/mlb/straight/odds"),
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            body_sample = None
            try:
                parsed = r.json()
                body_sample = json.dumps(parsed, default=str)[:1000]
            except Exception:
                body_sample = r.text[:500]
            test_results[label] = {"url": url, "status": r.status_code,
                                     "content_type": r.headers.get("content-type", ""),
                                     "body_sample": body_sample}
        except Exception as e:
            test_results[label] = {"url": url, "error": str(e)}
    push_files({"betcouncil_unabated_second_claim_test.json": {
        "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                "results": test_results}, indent=2, default=str)
    }}, github_token)


def flatten_market_changes(payload: dict) -> list:
    rows = []
    unmapped_leagues = set()
    for result in payload.get("results", []):
        mlc = result.get("marketLineChanges", [])
        game_odds_events = (mlc[0].get("gameOdds", {}).get("gameOddsEvents", {}) if mlc else {})
        for league_period_phase, events in game_odds_events.items():
            parts = league_period_phase.split(":")
            league_key = parts[0] if parts else ""
            period = parts[1] if len(parts) > 1 else ""
            phase = parts[2] if len(parts) > 2 else ""
            league = LEAGUE_ID_MAP.get(league_key)
            if not league:
                unmapped_leagues.add(league_key)
                continue
            for event in events:
                event_id = event.get("eventId")
                event_start = event.get("eventStart")
                status_id = event.get("statusId")
                for side_book_key, bet_types in event.get("gameOddsMarketSourcesLines", {}).items():
                    sb_parts = side_book_key.split(":")
                    side_index = sb_parts[0].replace("si", "") if sb_parts else None
                    market_source_id = sb_parts[1].replace("ms", "") if len(sb_parts) > 1 else None
                    for bt_key, line in bet_types.items():
                        bet_type_id = bt_key.replace("bt", "")
                        rows.append({
                            "league": league, "event_id": event_id, "event_start": event_start,
                            "status_id": status_id, "period": period, "phase": phase,
                            "side_index": side_index, "market_source_id": market_source_id,
                            "bet_type_id": bet_type_id, "market_id": line.get("marketId"),
                            "points": line.get("points"), "price": line.get("price"),
                            "source_price": line.get("sourcePrice"),
                            "modified_on": line.get("modifiedOn"),
                            "side_key": line.get("sideKey"),
                        })
    if unmapped_leagues:
        DEBUG_LOG.append({"unmapped_league_keys_seen": list(unmapped_leagues)})
    return rows


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(3):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=60,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code == 409 and attempt < 2:
            import time
            time.sleep((attempt + 1) * 4)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    payload = fetch_json(f"{BASE_URL}/markets/changes/query",
                          params={"full_refresh_ISO": now_iso})

    files_payload = {
        "betcouncil_unabated_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:10]},
                                   indent=2, default=str)
        }
    }

    if not payload:
        log("No data returned — see debug log")
        push_files(files_payload, github_token)
        return 1

    rows = flatten_market_changes(payload)
    by_league = {}
    for r in rows:
        by_league.setdefault(r["league"], []).append(r)

    log(f"Total rows: {len(rows)} across leagues: "
        f"{ {k: len(v) for k, v in by_league.items()} }")

    for league, league_rows in by_league.items():
        files_payload[f"betcouncil_unabated_odds_{league}.json"] = {
            "content": json.dumps({
                "source": "unabated", "league": league, "captured_at": now_iso,
                "total": len(league_rows), "lines": league_rows,
            }, default=str)
        }

    files_payload["betcouncil_unabated_debug.json"]["content"] = json.dumps({
        "captured_at": now_iso, "requests": DEBUG_LOG[:10],
        "total_rows": len(rows), "by_league_counts": {k: len(v) for k, v in by_league.items()},
    }, indent=2, default=str)

    if not rows:
        log("Payload received but zero rows flattened — see debug log")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
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
                push_files({"betcouncil_unabated_debug.json": {
                    "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                            "error": "unhandled_exception", "traceback": tb}, indent=2)
                }}, token)
        except Exception:
            pass
        sys.exit(1)
