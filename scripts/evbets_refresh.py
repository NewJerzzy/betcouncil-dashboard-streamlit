"""
evbets_refresh.py — EVBets positive-EV value bets (evbets.app, SSR Astro, no auth)
====================================================================================

evbets.app is an Astro framework app hosted on Cloudflare Pages. All bet data
is server-side rendered directly into the HTML response — no JavaScript
execution or browser required. Confirmed via:
  - Cloudflare cache headers: x-cache-status: STALE / cf-cache-status: EXPIRED
  - cfOrigin;dur=594 (origin doing ~600ms server computation per request)
  - Live data confirmed: `<table class="vb-table">` appears in the DOM when
    bets exist (confirmed 2026-08-01 via AFL page with 1 live signal)
  - "No X value bets right now" placeholder appears when no bets for a sport

Discovery flow:
  1. GET https://evbets.app/value-bets → vbh-sports-grid section lists every
     sport slug that currently has at least 1 signal (e.g. "1 signal" count)
  2. For each active sport, GET https://evbets.app/value-bets/{sport-slug}
  3. Parse <table class="vb-table" id="vb-main-table"> tbody rows

Each bet row structure (confirmed from live AFL data 2026-08-01):
  <tr
    data-ev="0.524"                   ← EV% as decimal (0.524 = +0.52%)
    data-bm="betfair"                 ← bookmaker slug (internal key)
    data-market="h2h"                 ← market type (h2h, spreads, totals, etc.)
    data-odds="1.210"                 ← best available decimal odds
    data-hours="0.6"                  ← hours until game starts
    onclick="window.location.href='...'">
    <td>1</td>                        ← row number
    <td><a href="...">Event Name</a></td>
    <td>Outcome/Team</td>
    <td><span class="market-tag">h2h</span></td>
    <td>1.21</td>                     ← best odds (decimal)
    <td><a href="...">Bookmaker</a></td>
    <td><span class="ev-chip...">+0.52%</span></td>
    <td>$6</td>                       ← Kelly $1k stake
    <td class="countdown-cell" data-commence="2026-08-01T03:35:16+00:00"></td>
  </tr>

Sport slugs: 71 total in sitemap. Script fetches the hub page first, then
only fetches sport pages that show active signals — avoids hammering 71 pages
when only 1-3 sports have bets.

Gist slot management (300-file hard cap):
  betcouncil_oddsshark_CFB.json (143b — confirmed dead placeholder) is
  repurposed → betcouncil_evbets_combined.json on first run via GitHub Gist
  rename API. Subsequent runs push directly to betcouncil_evbets_combined.json.

Output shape:
{
  "captured_at": "2026-08-01T12:00:00+00:00",
  "source": "evbets",
  "total_bets": 1,
  "by_sport": {
    "AFL": {
      "slug": "aussierules-afl",
      "bet_count": 1,
      "value_bets": [
        {
          "event": "Hawthorn Hawks vs North Melbourne Kangaroos",
          "outcome": "Hawthorn Hawks",
          "market": "h2h",
          "odds": 1.21,
          "ev_pct": 0.524,
          "book": "betfair",
          "book_display": "Betfair",
          "kelly_1k": "$6",
          "commence": "2026-08-01T03:35:16+00:00",
          "hours_until_start": 0.6
        }
      ]
    }
  }
}

Consumer compatibility (app_core.py line ~16170):
  Each bet dict includes "event", "ev_pct", "book" — the three fields
  consumed by the existing EVBets annotation logic.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
TARGET_FILE = "betcouncil_evbets_combined.json"
LEGACY_FILE = "betcouncil_oddsapiio_bovada_props_debug.json"  # confirmed diagnostic-only, safe to repurpose (real oddsshark_CFB.json is active data, NOT dead -- do not target that)
HUB_URL = "https://evbets.app/value-bets"
SPORT_URL = "https://evbets.app/value-bets/{slug}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
# Delay between sport-page requests to be polite (seconds)
REQUEST_DELAY = 1.5

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _fetch(url: str, timeout: int = 20) -> str:
    """GET url, return text decoded as UTF-8. Raises on non-200."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    # Explicitly decode as UTF-8 — requests defaults to latin-1 for HTML
    # when the server doesn't send a charset in the Content-Type header,
    # which produces mojibake for non-ASCII glyphs (e.g. ↗ in bookmaker names).
    text = resp.content.decode("utf-8", errors="replace")
    DEBUG_LOG.append({
        "url": url,
        "status": resp.status_code,
        "body_len": len(text),
    })
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} from {url}")
    return text


def discover_active_sports(hub_html: str) -> dict[str, str]:
    """
    Parse the /value-bets hub page to find sport slugs that currently have
    at least 1 active signal. Returns {display_name: slug}.

    The hub page contains a vbh-sports-grid with vbh-sport-card links for
    every sport that currently has bets. Sports with zero bets are absent
    from this grid entirely.

    Each card looks like:
      <a href="/value-bets/{slug}" class="vbh-sport-card">
        <span class="vbh-sport-icon">🏆</span>
        <div class="vbh-sport-meta">
          <div class="vbh-sport-name">Aussie Rules</div>
          <div><span class="vbh-sport-count">1 signal</span>...</div>
        </div>
      </a>
    """
    active: dict[str, str] = {}

    # Find sport cards in the hub grid
    cards = re.findall(
        r'<a\s+href="/value-bets/([^"]+)"\s+class="vbh-sport-card[^"]*"[^>]*>(.*?)</a>',
        hub_html, re.DOTALL
    )
    for slug, inner in cards:
        name_m = re.search(r'vbh-sport-name[^>]+>([^<]+)<', inner)
        count_m = re.search(r'vbh-sport-count[^>]+>([^<]+)<', inner)
        if name_m:
            display_name = name_m.group(1).strip()
            count_text = count_m.group(1).strip() if count_m else ""
            active[display_name] = slug
            log(f"  Active sport: {display_name} ({slug}) — {count_text}")

    # Also check the league-grid section for the league-level links
    # (same slugs as sport cards, but sometimes listed separately)
    league_links = re.findall(
        r'<a\s+href="/value-bets/([^"]+)"\s+class="vbh-league-row[^"]*"',
        hub_html
    )
    for slug in league_links:
        # Deduplicate — sport cards are enough, league links just confirm
        if not any(v == slug for v in active.values()):
            active[slug] = slug  # use slug as display name fallback

    return active


def parse_bet_rows(sport_html: str) -> list[dict]:
    """
    Parse <table class="vb-table" id="vb-main-table"> tbody rows.
    Returns list of bet dicts; empty list if no bets.
    """
    # Quick bail-out: page says "no bets right now"
    if re.search(r'no\s+\w+\s+value bets right now', sport_html, re.I):
        return []

    # Find the main bet table
    table_m = re.search(
        r'<table[^>]+class="vb-table"[^>]*id="vb-main-table"[^>]*>(.*?)</table>',
        sport_html, re.DOTALL
    )
    if not table_m:
        # Try without id in case markup changes
        table_m = re.search(
            r'<table[^>]+class="vb-table"[^>]*>(.*?)</table>',
            sport_html, re.DOTALL
        )
    if not table_m:
        return []

    tbody_m = re.search(r'<tbody[^>]*>(.*?)</tbody>', table_m.group(1), re.DOTALL)
    if not tbody_m:
        return []

    bets = []
    # Each <tr> in the tbody is one bet
    rows = re.findall(r'<tr\s([^>]+)>(.*?)</tr>', tbody_m.group(1), re.DOTALL)

    for attr_str, row_html in rows:
        # ── Data attributes from <tr> ─────────────────────────────────────
        def _attr(name: str) -> str:
            m = re.search(rf'data-{name}=["\']([^"\']*)["\']', attr_str)
            return m.group(1) if m else ""

        ev_raw    = _attr("ev")
        bm        = _attr("bm")
        market    = _attr("market")
        odds_raw  = _attr("odds")
        hours_raw = _attr("hours")

        # Skip rows missing essential data attributes (header row, spacers)
        if not ev_raw and not bm:
            continue

        # ── Text content from <td> cells ──────────────────────────────────
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)

        def _cell_text(idx: int) -> str:
            if idx >= len(cells):
                return ""
            return re.sub(r'<[^>]+>', '', cells[idx]).strip()

        # Cell 1: event name — from link text
        event = ""
        if len(cells) > 1:
            link_m = re.search(r'<a[^>]+>([^<]+)</a>', cells[1])
            event = link_m.group(1).strip() if link_m else _cell_text(1)

        # Cell 2: outcome
        outcome = _cell_text(2) if len(cells) > 2 else ""

        # Cell 5: bookmaker display name — strip all tags, then remove arrow glyph
        book_display = ""
        if len(cells) > 5:
            raw = re.sub(r'<[^>]+>', '', cells[5]).strip()
            # Remove trailing affiliate arrow (↗, ›, →, or ASCII >)
            book_display = re.sub(r'[\u2197\u203a\u2192>]+\s*$', '', raw).strip()

        # Cell 6: EV% display text
        ev_display = ""
        if len(cells) > 6:
            ev_m = re.search(r'ev-chip[^>]+>([^<]+)<', cells[6])
            ev_display = ev_m.group(1).strip() if ev_m else _cell_text(6)

        # Cell 7: Kelly $1k
        kelly = _cell_text(7) if len(cells) > 7 else ""

        # Commence timestamp: data-commence is an attribute on the <td> tag itself,
        # not in its inner HTML — must search raw row_html, not cells[8].
        comm_m = re.search(r'data-commence=["\']([^"\']+)["\']', row_html)
        commence = comm_m.group(1) if comm_m else ""

        # ── Numeric conversion ────────────────────────────────────────────
        try:
            ev_pct = float(ev_raw)
        except (ValueError, TypeError):
            ev_pct = None

        try:
            odds = float(odds_raw)
        except (ValueError, TypeError):
            odds = None

        try:
            hours_until = float(hours_raw)
        except (ValueError, TypeError):
            hours_until = None

        bets.append({
            "event":             event,
            "outcome":           outcome,
            "market":            market or _cell_text(3),
            "odds":              odds,
            "ev_pct":            ev_pct,
            "ev_display":        ev_display,
            "book":              bm,
            "book_display":      book_display,
            "kelly_1k":          kelly,
            "commence":          commence,
            "hours_until_start": hours_until,
        })

    return bets


def _get_gist_files(github_token: str) -> set:
    """Return the set of filenames currently in the gist."""
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return set(resp.json().get("files", {}).keys())
    except Exception as e:
        log(f"  _get_gist_files: {e} — assuming target doesn't exist")
    return set()


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
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
            return len(files_payload)
        if resp.status_code in (403, 429, 409) and attempt < 4:
            base_wait = min(10 * (2 ** attempt), 90)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"  Gist push got {resp.status_code} — retrying in {wait:.1f}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue
        log(f"  Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget before doing any writes."""
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} requests left this hour) — skipping")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) — proceeding anyway")
    return True


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    if not _rate_limit_ok(github_token):
        return 0

    # ── Step 1: Discover active sports from hub page ──────────────────────
    log(f"Fetching hub page: {HUB_URL}")
    try:
        hub_html = _fetch(HUB_URL)
    except Exception as e:
        log(f"FATAL: hub fetch failed — {e}")
        return 1

    active_sports = discover_active_sports(hub_html)
    log(f"Active sports with bets: {len(active_sports)}")

    # ── Step 2: Fetch each active sport page and parse bets ───────────────
    by_sport: dict[str, dict] = {}
    total_bets = 0

    for display_name, slug in active_sports.items():
        time.sleep(REQUEST_DELAY)
        url = SPORT_URL.format(slug=slug)
        log(f"  Fetching {slug}")
        try:
            sport_html = _fetch(url)
        except Exception as e:
            log(f"    {slug}: fetch error — {e}")
            continue

        bets = parse_bet_rows(sport_html)
        log(f"    {slug}: {len(bets)} bets")
        if bets:
            by_sport[display_name] = {
                "slug":      slug,
                "bet_count": len(bets),
                "value_bets": bets,
            }
            total_bets += len(bets)

    log(f"Total bets across all sports: {total_bets}")

    # ── Step 3: Build output payload ──────────────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "captured_at": now_iso,
        "source": "evbets",
        "hub_url": HUB_URL,
        "total_bets": total_bets,
        "sport_count": len(by_sport),
        "by_sport": by_sport,
        "debug": DEBUG_LOG[:20],
    }
    content = json.dumps(payload, indent=2)

    # ── Step 4: Gist slot management ──────────────────────────────────────
    log("Checking gist slot availability")
    existing_files = _get_gist_files(github_token)

    if TARGET_FILE in existing_files:
        log(f"  Target '{TARGET_FILE}' exists — pushing update")
        files_payload = {TARGET_FILE: {"content": content}}
    else:
        log(f"  Target '{TARGET_FILE}' not found — repurposing '{LEGACY_FILE}' via rename")
        files_payload = {
            LEGACY_FILE: {
                "filename": TARGET_FILE,
                "content": content,
            }
        }

    # Push even when total_bets == 0 so the "no active bets" state is
    # recorded in the gist (avoids stale data from a previous run with bets).
    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} file(s) → {TARGET_FILE}")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
