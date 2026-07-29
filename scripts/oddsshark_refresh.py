"""
oddsshark_refresh.py — OddsShark public consensus picks (oddsshark.com)
================================================================================
Public, free, no-login consensus pages -- confirmed accessible via a plain
fetch (no paywall, no auth headers needed), e.g.
https://www.oddsshark.com/mlb/consensus-picks

Real page structure confirmed via a direct fetch before writing this parser
(not guessed): two tables per sport page -- "Side To Win" (moneyline
consensus: matchup, line, consensus %, best-line book, bet-against book)
and "Best Over/Under Bets" (total, consensus %, over/under side, best-line
book). This scraper targets a plain HTML <table> structure with
BeautifulSoup, same pattern already proven for fetch_numberfire_direct in
this same codebase.

NOTE: the exact CSS classes/table IDs on the live page have NOT been
individually confirmed (my sandbox can't reach oddsshark.com directly to
inspect raw HTML) -- this targets a reasonable generic table structure and
is meant to be tested live via workflow_dispatch, with the debug snippet
below showing exactly what came back if the real markup differs from this
guess. Same honest approach already used for WagerBird's real fix.

Pushes to betcouncil_oddsshark_{SPORT}.json (+ betcouncil_oddsshark_debug.json).
"""

import json
import os
import re
import sys
import time
import random
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

SPORTS = {
    "mlb": "MLB",
    "nfl": "NFL",
    "nba": "NBA",
    "nhl": "NHL",
    "ncaaf": "CFB",
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}

SCRAPEOPS_KEY = os.environ.get("SCRAPEOPS_KEY", "")

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_page(sport_slug: str):
    url = f"https://www.oddsshark.com/{sport_slug}/consensus-picks"
    # Bot-protection status here is inconsistent across runs: confirmed
    # blocked (HTTP 000, connection failure) on 2026-07-28, then confirmed
    # working via direct fetch for all 5 sports on 2026-07-29 -- treat as
    # intermittent, not a hard block. Direct fetch attempted first every
    # run regardless; the two-tier ScrapeOps fallback below only spends
    # credits on the runs where direct genuinely fails.
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            DEBUG_LOG.append({"url": url, "method": "direct", "status": r.status_code, "bytes": len(r.text)})
            return r.text
        DEBUG_LOG.append({"url": url, "method": "direct", "status": r.status_code})
    except Exception as e:
        DEBUG_LOG.append({"url": url, "method": "direct", "error": str(e)[:200]})

    if not SCRAPEOPS_KEY:
        DEBUG_LOG.append({"url": url, "method": "scrapeops", "error": "SCRAPEOPS_KEY not set"})
        return None

    import urllib.parse
    encoded = urllib.parse.quote(url, safe="")

    # Tier 1: plain residential proxy, no JS rendering. The confirmed block
    # (HTTP 000 / connection failure at the network layer, not a JS
    # challenge response) is an IP-reputation block, not something that
    # needs a real browser to clear -- render_js costs far more credits
    # per call on ScrapeOps' pricing, so only pay for it if this cheaper
    # tier actually fails.
    try:
        r = requests.get(
            f"https://proxy.scrapeops.io/v1/?api_key={SCRAPEOPS_KEY}&url={encoded}&residential=true&country=us&render_js=false",
            timeout=25,
        )
        DEBUG_LOG.append({"url": url, "method": "scrapeops_no_js", "status": r.status_code, "bytes": len(r.text), "body_snippet": r.text[:400]})
        if r.status_code == 200:
            return r.text
    except Exception as e:
        DEBUG_LOG.append({"url": url, "method": "scrapeops_no_js", "error": str(e)[:200]})

    # Tier 2: render_js=true fallback, only reached if the cheap tier failed.
    try:
        r = requests.get(
            f"https://proxy.scrapeops.io/v1/?api_key={SCRAPEOPS_KEY}&url={encoded}&residential=true&country=us&render_js=true",
            timeout=30,
        )
        DEBUG_LOG.append({"url": url, "method": "scrapeops_js", "status": r.status_code, "bytes": len(r.text), "body_snippet": r.text[:400]})
        if r.status_code != 200:
            return None
        return r.text
    except Exception as e:
        DEBUG_LOG.append({"url": url, "method": "scrapeops", "error": str(e)[:200]})
        return None


def parse_moneyline_table(soup, table):
    games = []
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        row_text = [c.get_text(strip=True) for c in cells]
        # Expect something like: [away, home, line, consensus_pct, best_line_book, bet_against_book]
        # Real column count/order confirmed only via live test -- parsed
        # defensively, skipping rows that don't look like real data.
        joined = " ".join(row_text)
        m = re.search(r"([+-]\d{2,4})", joined)
        pct = re.search(r"(\d{1,3})%", joined)
        if not (m and pct):
            continue
        games.append({
            "raw_row": row_text,
            "line": m.group(1),
            "consensus_pct": int(pct.group(1)),
        })
    return games


def parse_totals_table(soup, table):
    totals = []
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        row_text = [c.get_text(strip=True) for c in cells]
        joined = " ".join(row_text)
        pct = re.search(r"(\d{1,3})%", joined)
        side = "Over" if re.search(r"\bOver\b", joined) else ("Under" if re.search(r"\bUnder\b", joined) else None)
        if not (pct and side):
            continue
        totals.append({
            "raw_row": row_text,
            "consensus_pct": int(pct.group(1)),
            "side": side,
        })
    return totals


def extract_sport(html: str, sport_display: str):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        DEBUG_LOG.append({"error": "bs4 not installed"})
        return {"moneyline": [], "totals": []}
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    DEBUG_LOG.append({"sport": sport_display, "tables_found": len(tables)})
    moneyline, totals = [], []
    for t in tables:
        header_text = t.get_text(" ", strip=True)[:200].lower()
        if "consensus" in header_text or "line" in header_text:
            if not moneyline:
                moneyline = parse_moneyline_table(soup, t)
                if moneyline:
                    continue
        if not totals:
            parsed_totals = parse_totals_table(soup, t)
            if parsed_totals:
                totals = parsed_totals
    return {"moneyline": moneyline, "totals": totals}


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 4:
            wait = min(10 * (2 ** attempt), 90) + random.uniform(0, 5)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} left) -- skipping cleanly")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) -- proceeding anyway")
    return True


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1
    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {}
    any_real_data = False

    for slug, display in SPORTS.items():
        html = fetch_page(slug)
        if html is None:
            log(f"{display}: fetch failed")
            continue
        parsed = extract_sport(html, display)
        n_ml, n_tot = len(parsed["moneyline"]), len(parsed["totals"])
        log(f"{display}: {n_ml} moneyline rows, {n_tot} totals rows")
        if n_ml or n_tot:
            any_real_data = True
        files_payload[f"betcouncil_oddsshark_{display}.json"] = {
            "content": json.dumps({
                "source": "oddsshark_consensus", "sport": display,
                "captured_at": now_iso, **parsed,
            }, indent=2)
        }

    files_payload["betcouncil_oddsshark_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:10]}, indent=2)
    }

    if not any_real_data:
        log("0 real rows parsed across all sports -- see debug snippet")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as _e:
        import traceback
        _tb = traceback.format_exc()
        try:
            _emergency_token = os.environ.get("GITHUB_TOKEN", "")
            if _emergency_token:
                import urllib.request as _ur
                _body = json.dumps({"files": {"betcouncil_oddsshark_debug.json": {
                    "content": json.dumps({
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "uncaught_exception": str(_e),
                        "traceback": _tb[-3000:],
                    }, indent=2)
                }}}).encode()
                _req = _ur.Request(f"https://api.github.com/gists/{GIST_ID}", data=_body, method="PATCH",
                    headers={"Authorization": f"token {_emergency_token}", "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json"})
                _ur.urlopen(_req, timeout=15)
        except Exception:
            pass
        print(_tb, flush=True)
        sys.exit(1)
