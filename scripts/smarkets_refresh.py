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
    back = c.get("best_back_price") or c.get("last_executed_price")
    return {
        "contract_id": str(c.get("id") or c.get("contract_id") or ""),
        "name": c.get("name", ""),
        "side": c.get("side", c.get("name", "")).upper()[:10],
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

    # Step 1: find MLB's sport_id (dumped to debug regardless, so a wrong
    # guess here is correctable from one live run instead of guessing blind).
    sports_resp = fetch_json(f"{BASE_URL}/sports/")
    DEBUG_LOG.append({"step": "sports_list", "raw": sports_resp})
    mlb_sport_id = None
    if isinstance(sports_resp, dict):
        for s in sports_resp.get("sports", sports_resp.get("results", [])):
            if isinstance(s, dict) and "baseball" in str(s.get("name", "")).lower():
                mlb_sport_id = s.get("id")
                break

    events_resp = fetch_json(f"{BASE_URL}/events/", params={
        "type": "sport", "state": "upcoming",
        **({"sport_ids": mlb_sport_id} if mlb_sport_id else {}),
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

    markets_resp = fetch_json(f"{BASE_URL}/markets/", params={"event_ids": ",".join(event_ids[:50])})
    markets = []
    if isinstance(markets_resp, dict):
        markets = markets_resp.get("markets", markets_resp.get("results", []))
    log(f"markets found: {len(markets)}")

    market_ids = [str(m.get("id")) for m in markets if m.get("id")]
    prices_by_contract = {}
    if market_ids:
        # batch in chunks of 50 market ids per call
        for i in range(0, len(market_ids), 50):
            chunk = market_ids[i:i + 50]
            prices_resp = fetch_json(f"{BASE_URL}/prices/", params={"market_ids": ",".join(chunk)})
            if isinstance(prices_resp, dict):
                for mkt_id, contracts in prices_resp.get("prices", prices_resp.get("results", {})).items():
                    if isinstance(contracts, list):
                        for c in contracts:
                            cid = str(c.get("contract_id") or c.get("id") or "")
                            if cid:
                                prices_by_contract[cid] = c

    games_out, props_out = {}, []
    for m in markets:
        eid = str(m.get("event_id", ""))
        market_type_raw = str(m.get("type", m.get("market_type", "")))
        contracts_out = []
        for c in m.get("contracts", []):
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

    note = "prices on 0-10000 scale; volume in GBP pence; american_odds derived from best back (bid) price"
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
