"""
smarkets_refresh.py — Smarkets betting exchange (public API, no auth)
================================================================================

Smarkets (smarkets.com) is a UK betting EXCHANGE, not a sportsbook — prices
are peer-to-peer order-book quotes (back/lay), often cited as one of the
sharpest available prices since there's no bookmaker margin baked in, just
real money on both sides of every contract. Public REST API, no auth for
read-only market data.

REAL SCHEMA CONFIRMED (not guessed): a prior session manually pushed real,
live MLB game-line and player-prop data straight to the Gist on 2026-07-18
without committing any code. This script's output shape is built directly
against that actual captured payload (real event/market/contract structure
below) — but the FETCH side (which real Smarkets endpoints assemble that
structure) is inferred from Smarkets' known v3 API design, NOT independently
verified live from this sandbox (api.smarkets.com isn't in this
environment's network allowlist). Higher uncertainty here than other
scrapers in this repo — Smarkets' three-endpoint chain (events -> markets
-> live pricing) has more moving parts than a single-call API like
LineTerminal or a well-known CSV export like Baseball Savant. Ships with
heavy debug logging specifically because of that; expect this one may need
more than one live-iterate round to get exactly right.

Assumed endpoint chain (Smarkets v3 REST API):
    GET /v3/events/?type=sport&state=upcoming&sport_ids={mlb_sport_id}
        -> event list. sport_ids for MLB not independently confirmed;
           first live run's debug log dumps the raw sports list response
           so this can be corrected without guessing twice.
    GET /v3/markets/?event_ids={csv of event ids}
        -> market list per event (moneyline, totals, player props all
           come back in one call, filtered client-side by market_type)
    GET /v3/prices/?market_ids={csv of market ids}
        -> live order-book quotes (best back/lay) per contract

Real captured output shape (what this script must reproduce):
    game_lines: {source, league, captured_at, note, games: [
        {smarkets_event_id, event_name, markets: [
            {market_id, market_type, market_name, param, volume_pence,
             contracts: [{contract_id, name, side, best_back_price,
                          best_lay_price, implied_pct, american_odds,
                          last_executed_pct}]}
        ]}
    ]}
    props: {source, league, captured_at, note, props: [
        {smarkets_event_id, event_name, market_id, market_name,
         market_type, player_name, player_id, line, volume_pence,
         over: {...contract...}, under: {...contract...}}
    ]}

Prices are on a 0-10000 integer scale (implied probability * 100, i.e.
4167 = 41.67%). american_odds is derived here from best_back_price (the
best available price to back/buy, i.e. the price you could actually get
matched at right now).
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.smarkets.com/v3"
LEAGUE = "MLB"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
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
                       "body_snippet": r.text[:500]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def implied_pct_to_american(price_10000_scale) -> int:
    """4167 (=41.67%) -> +140 style American odds."""
    if not price_10000_scale or price_10000_scale <= 0 or price_10000_scale >= 10000:
        return None
    prob = price_10000_scale / 10000.0
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    return round(100 * (1 - prob) / prob)


def build_contract(c: dict) -> dict:
    # 2026-07-18 live run #5 fix: side is nested {"contract_type":
    # {"name": "AWAY"}}, same nested-dict pattern as market_type -- not a
    # flat "side" field. Real contract identity confirmed live (Twins/
    # Cubs AWAY/HOME contracts, Over/Under N.N runs contracts); pricing
    # fields (best_back_price etc) are NOT part of this object -- merged
    # in separately from the /v3/prices/?contract_ids= lookup, still
    # unverified live as of this comment.
    _ct_raw = c.get("contract_type") or {}
    side = _ct_raw.get("name", "") if isinstance(_ct_raw, dict) else str(c.get("side", ""))
    back = c.get("best_back_price") or c.get("last_executed_price")
    return {
        "contract_id": str(c.get("id") or c.get("contract_id") or ""),
        "name": c.get("name", ""),
        "side": side.upper()[:10],
        "best_back_price": c.get("best_back_price"),
        "best_lay_price": c.get("best_lay_price"),
        "implied_pct": round(back / 100.0, 2) if back else None,
        "american_odds": implied_pct_to_american(back),
        "last_executed_pct": round(c.get("last_executed_price", 0) / 100.0, 2)
            if c.get("last_executed_price") else None,
    }


def push_files(files_payload: dict, github_token: str) -> int:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": files_payload}, timeout=60,
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

    # 2026-07-18 live run #1 fix: /v3/sports/ doesn't exist (404) -- not
    # needed anyway. /v3/events/?type=sport&sport_ids=X returned 400 with
    # the API's own valid-value list in the error body: type must be one
    # of a fixed set of match-type strings, 'baseball_match' among them --
    # no separate sport_id lookup required at all.
    events_resp = fetch_json(f"{BASE_URL}/events/", params={
        "type": "baseball_match", "state": "upcoming",
    })
    events = []
    if isinstance(events_resp, dict):
        events = events_resp.get("events", events_resp.get("results", []))
    log(f"events found: {len(events)}")

    if not events:
        log("No events returned — see debug log for raw sports/events response")
        files_payload["betcouncil_smarkets_debug.json"] = {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15]}, indent=2, default=str)
        }
        push_files(files_payload, github_token)
        return 1

    event_ids = [str(e.get("id")) for e in events if e.get("id")]
    event_name_by_id = {str(e.get("id")): e.get("name", "") for e in events}

    # 2026-07-18 live run #2 fix: /v3/markets/?event_ids=a,b,c 404'd --
    # bulk query-param form doesn't exist. Smarkets nests markets under
    # each event instead: /v3/events/{id}/markets/. Fetched per event
    # (capped at 20 events/run to keep runtime reasonable).
    markets = []
    for eid in event_ids[:8]:
        mkt_resp = fetch_json(f"{BASE_URL}/events/{eid}/markets/")
        if isinstance(mkt_resp, dict):
            for m in mkt_resp.get("markets", mkt_resp.get("results", [])):
                if isinstance(m, dict):
                    m.setdefault("event_id", eid)
                    markets.append(m)
    log(f"markets found: {len(markets)}")
    DEBUG_LOG.append({
        "step": "markets_contract_check",
        "sample_market_keys": list(markets[0].keys()) if markets else [],
        "sample_market_has_contracts_field": "contracts" in markets[0] if markets else None,
        "sample_market_contracts_value": markets[0].get("contracts") if markets else None,
    })

    # 2026-07-18 live run #5: /v3/markets/{id}/contracts/ confirmed real
    # (200, correct contract identity: id/name/side/market_id) -- markets
    # themselves have no inline contracts field, confirmed via a direct
    # key check. Contracts carry NO pricing fields at all (no
    # best_back_price etc).
    #
    # Live run #6: tried bulk /v3/prices/ keyed by both market_ids AND
    # contract_ids -- both 404 on every chunk, meaning that whole bulk
    # endpoint path doesn't exist under either key. Per-contract fetching
    # would need ~4800 additional calls at full event scope (the
    # contracts fetch alone already took ~12 minutes for 1732 markets --
    # not viable inside a 15-min cron window either way). Stopping the
    # pricing chase here rather than continuing to guess indefinitely or
    # scale this cron job into something that risks overlapping runs or
    # hammering Smarkets with thousands of calls every 15 min.
    #
    # Ships as identity/structure only for now: real matchups, real
    # markets (moneyline/totals/props), real contract names and sides,
    # NO live back/lay prices. Still useful for cross-referencing which
    # lines Smarkets even offers, just not (yet) for a price comparison.
    # Revisit if a real single-contract pricing endpoint gets found later.
    contracts_by_market = {}
    for m in markets:
        mid = str(m.get("id", ""))
        if not mid:
            continue
        resp = fetch_json(f"{BASE_URL}/markets/{mid}/contracts/")
        if isinstance(resp, dict):
            contracts_by_market[mid] = resp.get("contracts", resp.get("results", []))
    all_contract_ids = [str(c.get("id")) for cs in contracts_by_market.values() for c in cs if c.get("id")]
    log(f"contracts found: {len(all_contract_ids)} across {len(contracts_by_market)} markets")

    prices_by_contract = {}  # intentionally empty -- see note above
    prices_calls_made = 0

    games_out, props_out = {}, []
    for m in markets:
        eid = str(m.get("event_id", ""))
        # 2026-07-18 live run #3 fix: market_type comes back as a nested
        # dict {"name": "WINNER_2_WAY"}, not a flat string -- stringifying
        # the raw dict would have made every prop-detection check compare
        # against "{'name': ...}" instead of the actual type name.
        _mt_raw = m.get("market_type") or m.get("type") or {}
        market_type_raw = _mt_raw.get("name", "") if isinstance(_mt_raw, dict) else str(_mt_raw)
        contracts_out = []
        for c in contracts_by_market.get(str(m.get("id", "")), []):
            cid = str(c.get("id", ""))
            price_data = prices_by_contract.get(cid, {})
            contracts_out.append(build_contract({**c, **price_data}))

        is_prop = "PLAYER" in market_type_raw.upper() or "player" in str(m.get("name", "")).lower()
        if is_prop and len(contracts_out) >= 2:
            props_out.append({
                "smarkets_event_id": eid, "event_name": event_name_by_id.get(eid, ""),
                "market_id": str(m.get("id", "")), "market_name": m.get("name", ""),
                "market_type": market_type_raw,
                "player_name": m.get("player_name", m.get("name", "").split(" ")[0] if m.get("name") else ""),
                "player_id": m.get("player_id"),
                "line": m.get("param"), "volume_pence": m.get("volume", 0),
                "over": next((c for c in contracts_out if c["side"] == "OVER"), contracts_out[0]),
                "under": next((c for c in contracts_out if c["side"] == "UNDER"), contracts_out[-1]),
            })
        elif not is_prop:
            games_out.setdefault(eid, {
                "smarkets_event_id": eid, "event_name": event_name_by_id.get(eid, ""), "markets": [],
            })["markets"].append({
                "market_id": str(m.get("id", "")), "market_type": market_type_raw,
                "market_name": m.get("name", ""), "param": m.get("param"),
                "volume_pence": m.get("volume", 0), "contracts": contracts_out,
            })

    note = ("Identity/structure only as of 2026-07-18 -- real matchups, markets, and contract "
            "names/sides, but no live back/lay pricing yet (Smarkets' bulk pricing endpoint "
            "returns 404 under both market_ids and contract_ids; per-contract fetching isn't "
            "practical at this scale within a cron job). american_odds/implied_pct/best_back_price "
            "fields will be null until a working pricing endpoint is found.")
    files_payload["betcouncil_smarkets_game_lines_MLB.json"] = {
        "content": json.dumps({
            "source": "smarkets_exchange", "league": LEAGUE, "captured_at": now_iso,
            "note": note, "games": list(games_out.values()),
        }, default=str)
    }
    files_payload["betcouncil_smarkets_props_MLB.json"] = {
        "content": json.dumps({
            "source": "smarkets_exchange", "league": LEAGUE, "captured_at": now_iso,
            "note": note, "props": props_out,
        }, default=str)
    }
    files_payload["betcouncil_smarkets_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15],
                                "last_requests": DEBUG_LOG[-10:],
                                "contracts_count": len(all_contract_ids),
                                "prices_calls_made": prices_calls_made,
                                "prices_by_contract_count": len(prices_by_contract),
                                "games_count": len(games_out), "props_count": len(props_out)},
                               indent=2, default=str)
    }

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files ({len(games_out)} games, {len(props_out)} props)")
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
                push_files({"betcouncil_smarkets_debug.json": {
                    "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                            "error": "unhandled_exception", "traceback": tb}, indent=2)
                }}, token)
        except Exception:
            pass
        sys.exit(1)
