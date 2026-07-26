"""
kalshi_refresh.py — Kalshi MLB prediction markets (moneylines, totals, spreads)
================================================================================

Kalshi's public trade API (api.elections.kalshi.com/trade-api/v2) requires NO
auth for reading market data -- confirmed against Kalshi's own official docs
(docs.kalshi.com Quick Start: "access real-time market data without
authentication") before building this, not just from a secondhand claim.
Only trade execution, price history/candlesticks, and full orderbook depth
require an API key -- this script only touches the open endpoints.

Three MLB series, fetched via /events (nested markets in one call, fewer
requests than /markets + /events separately):
    KXMLBGAME   -- moneylines
    KXMLBTOTAL  -- run totals, EVERY line simultaneously (not just one O/U --
                   Kalshi stacks a market per threshold, e.g. "8 or more",
                   "9 or more" runs, each with its own live yes/no price).
                   Grouped by event so a consumer can reconstruct the full
                   implied probability distribution over total runs, not
                   just a single number.
    KXMLBSPREAD -- run line spreads

Real per-market fields captured (dollars, not cents -- Kalshi's *_dollars
fields): yes_bid, yes_ask, last_price, volume, open_interest, liquidity,
close_time. rules_primary kept too since it's the plain-English statement of
exactly what the market resolves on (useful for the totals threshold, which
otherwise has to be parsed out of the title).
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
SPORT_SERIES = {
    "MLB": ["KXMLBGAME", "KXMLBTOTAL", "KXMLBSPREAD"],
    "NFL": ["KXNFLGAME", "KXNFLTOTAL", "KXNFLSPREAD"],
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _fetch_series_events(series_ticker: str) -> list | None:
    """Fetch every open event (with nested markets) for one series."""
    try:
        r = requests.get(
            f"{BASE_URL}/events",
            params={"series_ticker": series_ticker, "status": "open", "with_nested_markets": "true"},
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except Exception as e:
        DEBUG_LOG.append({"series": series_ticker, "error": str(e)[:300]})
        log(f"  {series_ticker}: error — {e}")
        return None

    DEBUG_LOG.append({"series": series_ticker, "status": r.status_code, "body_snippet": r.text[:2000]})

    if r.status_code != 200:
        log(f"  {series_ticker}: HTTP {r.status_code} — {r.text[:200]}")
        return None

    try:
        data = r.json()
    except Exception as e:
        DEBUG_LOG.append({"series": series_ticker, "json_error": str(e)[:300]})
        return None

    events = data.get("events")
    if not isinstance(events, list):
        DEBUG_LOG.append({"series": series_ticker, "note": "unrecognized_shape",
                           "top_level_keys": list(data.keys()) if isinstance(data, dict) else str(type(data))})
        return None

    if events:
        DEBUG_LOG.append({"series": series_ticker, "note": "sample_event_full",
                           "sample": json.dumps(events[0], indent=2)[:5000]})

    return events


def _normalize_market(m: dict) -> dict:
    return {
        "ticker": m.get("ticker"),
        "title": m.get("title"),
        "yes_bid": m.get("yes_bid_dollars"),
        "yes_ask": m.get("yes_ask_dollars"),
        "last_price": m.get("last_price_dollars"),
        "volume": m.get("volume_fp") or m.get("volume"),
        "open_interest": m.get("open_interest_fp") or m.get("open_interest"),
        "liquidity": m.get("liquidity_dollars"),
        "close_time": m.get("close_time"),
        "rules_primary": m.get("rules_primary"),
    }


def _normalize_event(ev: dict, sport: str) -> dict:
    markets = ev.get("markets") or []
    return {
        "sport": sport,
        "event_ticker": ev.get("event_ticker"),
        "title": ev.get("title"),
        "series_ticker": ev.get("series_ticker"),
        "markets": [_normalize_market(m) for m in markets],
    }


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget for the shared Gist-push
    token before doing any writes -- see the other scrapers in this repo
    for why (2026-07-25 shared-token exhaustion incident)."""
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} requests left this hour) -- skipping this run cleanly")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) -- proceeding anyway")
    return True


def push_files(files_payload: dict) -> int:
    github_token = os.environ["GITHUB_TOKEN"]
    if not _rate_limit_ok(github_token):
        return 0
    for attempt in range(6):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (409, 403, 429) and attempt < 5:
            base_wait = min((attempt + 1) * 8, 60)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist {resp.status_code} — retrying in {wait:.1f}s (attempt {attempt+1}/6)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def main() -> int:
    if not os.environ.get("GITHUB_TOKEN"):
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    dry_run = "--dry-run" in sys.argv

    all_events = []
    for sport, series_list in SPORT_SERIES.items():
        for series in series_list:
            log(f"Fetching {sport} {series}...")
            events = _fetch_series_events(series)
            if events is None:
                log(f"  {series}: failed or no data, skipping")
                continue
            log(f"  {series}: {len(events)} open events")
            all_events.extend(_normalize_event(e, sport) for e in events)

    total_markets = sum(len(e["markets"]) for e in all_events)
    by_sport = {}
    for e in all_events:
        by_sport[e["sport"]] = by_sport.get(e["sport"], 0) + 1
    log(f"Total: {len(all_events)} events ({by_sport}), {total_markets} markets")

    if not all_events:
        log("FATAL: no events fetched from any series")
        if not dry_run:
            push_files({
                "betcouncil_kalshi_debug.json": {
                    "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
                }
            })
        return 1

    if dry_run:
        log("--dry-run: skipping Gist push")
        return 0

    files_payload = {
        "betcouncil_kalshi_markets.json": {
            "content": json.dumps({"source": "kalshi", "captured_at": now_iso, "events": all_events})
        },
        "betcouncil_kalshi_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
        },
    }
    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files to Gist")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
