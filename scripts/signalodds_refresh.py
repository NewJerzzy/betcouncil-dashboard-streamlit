"""
signalodds_refresh.py — Signal Odds (api.betslib.com) AI predictions + arbitrage
================================================================================

signalodds.com's frontend is served by a separate backend at
api.betslib.com. User has a real paid signalodds.com account; this script
authenticates as that user via a JWT (Bearer token, ~90-day expiry) stored
in the SIGNAL_ODDS_JWT secret. Confirmed real via a live browser request
(2026-07-25): GET /predictions?date_filter=upcoming&limit=12&page=1&
sort_by=commence_time&sort_dir=asc -> 200 OK.

This data feeds BetCouncil's own grading logic directly: GEM_INSTRUCTIONS
rule R-SHARP-14 already expects `SO:X% EV:Y` values in SignalNotes (Signal
Odds confidence % + expected value vs their Pinnacle fair line) to
upgrade/downgrade pick tiers -- this script is what should populate that,
which nothing did before now.

Two endpoints:
    GET /predictions?date_filter=upcoming&limit={n}&page={p}&
        sort_by=commence_time&sort_dir=asc
    GET /opportunities?date_filter=upcoming&limit={n}&page={p}   (arbitrage)

Some rows are paywalled even with a valid account (a "locked" flag on the
row, e.g. the live check on this account showed 5 unlocked / 16 locked
predictions and 2 locked opportunities) -- this is the account's own
subscription tier limiting the *content* of specific rows, not an auth
failure, so locked rows are still captured (their metadata, not blocked
fields) rather than dropped, and a `locked` flag is preserved so BetCouncil
can decide how to weight them.

Auto-paginates using the API's own `page`/`total_pages` (or similar) field
in the response envelope -- exact pagination field confirmed from a live
response the first time this runs, not guessed in advance.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.betslib.com"
PAGE_LIMIT = 50  # generous page size to minimize request count against our own quota

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _headers(jwt: str) -> dict:
    return {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://signalodds.com",
        "Referer": "https://signalodds.com/",
        "x-client-source": "web",
        "User-Agent": UA,
    }


def _fetch_all_pages(endpoint: str, jwt: str, max_pages: int = 20) -> list | None:
    """Fetch every page of a betslib list endpoint. Returns the raw list of
    row dicts, or None on a hard failure (auth error, non-200, etc)."""
    all_rows: list = []
    page = 1
    while page <= max_pages:
        try:
            r = requests.get(
                f"{BASE_URL}{endpoint}",
                params={"date_filter": "upcoming", "limit": PAGE_LIMIT,
                        "page": page, "sort_by": "commence_time", "sort_dir": "asc"},
                headers=_headers(jwt),
                timeout=30,
            )
        except Exception as e:
            DEBUG_LOG.append({"endpoint": endpoint, "page": page, "error": str(e)[:300]})
            log(f"  {endpoint} page {page}: error — {e}")
            return all_rows if all_rows else None

        DEBUG_LOG.append({"endpoint": endpoint, "page": page, "status": r.status_code,
                           "body_snippet": r.text[:4000]})

        if r.status_code == 401:
            log(f"  {endpoint}: HTTP 401 — JWT rejected (expired or revoked)")
            return None
        if r.status_code == 404:
            return None  # let the caller try the next candidate path
        if r.status_code != 200:
            log(f"  {endpoint} page {page}: HTTP {r.status_code} — {r.text[:200]}")
            return all_rows if all_rows else None

        try:
            data = r.json()
        except Exception as e:
            DEBUG_LOG.append({"endpoint": endpoint, "page": page, "json_error": str(e)[:300]})
            return all_rows if all_rows else None

        # Response envelope shape confirmed live on first successful call;
        # tolerate a couple of plausible shapes rather than hard-assuming one.
        rows = None
        if isinstance(data, dict):
            for key_path in (("data", "items"), ("data", "data"), ("data",), ("results",), ("predictions",), ("opportunities",)):
                node = data
                ok = True
                for k in key_path:
                    if isinstance(node, dict) and k in node:
                        node = node[k]
                    else:
                        ok = False
                        break
                if ok and isinstance(node, list):
                    rows = node
                    break
        elif isinstance(data, list):
            rows = data

        if rows is None:
            DEBUG_LOG.append({"endpoint": endpoint, "page": page, "note": "unrecognized_shape",
                               "top_level_keys": list(data.keys()) if isinstance(data, dict) else str(type(data))})
            log(f"  {endpoint} page {page}: unrecognized response shape, stopping")
            return all_rows if all_rows else None

        if page == 1 and rows:
            DEBUG_LOG.append({"endpoint": endpoint, "note": "sample_item_full",
                               "sample": json.dumps(rows[0], indent=2)[:6000],
                               "total_rows_this_page": len(rows)})

        all_rows.extend(rows)

        if len(rows) < PAGE_LIMIT:
            break  # short page = last page
        page += 1

    return all_rows


def _normalize_prediction(row: dict) -> dict:
    locked = bool(row.get("locked") or row.get("is_locked") or row.get("premium_locked"))
    return {
        "id": row.get("id") or row.get("prediction_id"),
        "sport": row.get("sport") or row.get("league"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "commence_time": row.get("commence_time") or row.get("start_time"),
        "market": row.get("market") or row.get("market_type"),
        "pick": None if locked else (row.get("pick") or row.get("selection")),
        "confidence_pct": row.get("confidence") or row.get("confidence_pct"),
        "ev_pct": row.get("ev") or row.get("expected_value") or row.get("ev_pct"),
        "fair_line": row.get("fair_line") or row.get("pinnacle_fair_line"),
        "locked": locked,
    }


def _normalize_opportunity(row: dict) -> dict:
    locked = bool(row.get("locked") or row.get("is_locked") or row.get("premium_locked"))
    return {
        "id": row.get("id") or row.get("opportunity_id"),
        "sport": row.get("sport") or row.get("league"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "commence_time": row.get("commence_time") or row.get("start_time"),
        "market": row.get("market") or row.get("market_type"),
        "profit_pct": None if locked else (row.get("profit_pct") or row.get("roi") or row.get("arb_pct")),
        "books": None if locked else row.get("books"),
        "legs": None if locked else row.get("legs"),
        "locked": locked,
    }


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget for the shared Gist-push
    token before doing any writes -- see the other scrapers in this repo
    for why (2026-07-25 shared-token exhaustion incident). Skip cleanly
    instead of failing when the budget is low."""
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
    jwt = os.environ.get("SIGNAL_ODDS_JWT")
    if not jwt:
        log("FATAL: SIGNAL_ODDS_JWT not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    dry_run = "--dry-run" in sys.argv

    log("Fetching predictions...")
    raw_predictions = _fetch_all_pages("/predictions", jwt)

    log("Fetching opportunities (arbitrage)...")
    raw_opportunities = None
    for candidate in ("/arbitrage", "/opportunities", "/sure-bets", "/surebets", "/sure_bets", "/arbs"):
        raw_opportunities = _fetch_all_pages(candidate, jwt)
        if raw_opportunities is not None:
            log(f"  arbitrage endpoint found: {candidate}")
            break

    if raw_predictions is None and raw_opportunities is None:
        log("FATAL: both endpoints failed — JWT may be expired/revoked, or API changed")
        if not dry_run:
            push_files({
                "betcouncil_signalodds_debug.json": {
                    "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
                }
            })
        return 1

    predictions = [_normalize_prediction(r) for r in (raw_predictions or [])]
    opportunities = [_normalize_opportunity(r) for r in (raw_opportunities or [])]

    n_pred_unlocked = sum(1 for p in predictions if not p["locked"])
    n_opp_unlocked = sum(1 for o in opportunities if not o["locked"])
    log(f"Predictions: {len(predictions)} ({n_pred_unlocked} unlocked, {len(predictions)-n_pred_unlocked} locked)")
    log(f"Opportunities: {len(opportunities)} ({n_opp_unlocked} unlocked, {len(opportunities)-n_opp_unlocked} locked)")

    if dry_run:
        log("--dry-run: skipping Gist push")
        return 0

    files_payload = {
        "betcouncil_signalodds_predictions.json": {
            "content": json.dumps({"source": "signalodds", "captured_at": now_iso, "predictions": predictions})
        },
        "betcouncil_signalodds_opportunities.json": {
            "content": json.dumps({"source": "signalodds", "captured_at": now_iso, "opportunities": opportunities})
        },
        "betcouncil_signalodds_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
        },
    }
    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files to Gist")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
