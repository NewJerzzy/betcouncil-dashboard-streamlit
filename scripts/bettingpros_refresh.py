"""
bettingpros_refresh.py — BettingPros props via SSR HTML scraping
=================================================================

The /v3/props API endpoint began blocking GitHub Actions runner IPs
on 2026-08-07. The website itself is not blocked and embeds the full
props JSON server-side in every page (as a `"props":[...]` literal in
a <script> tag).

Strategy: iterate every active market slug per sport, extract the
embedded JSON blob, deduplicate by (event_id, participant_id, market_id),
then push to Gist exactly as before.

Coverage vs old API approach:
  MLB  : 14 markets × ~25 props = ~350  (API was 400+, difference is low-EV tail props)
  WNBA : 10 markets × ~25 props = ~250
  NBA  : 10 markets × ~25 props = ~250
  NHL  :  6 markets × ~25 props = ~150
  NFL  :  0 (offseason — same as before)

Output format is identical to the API version so downstream consumers
are unaffected.

Pushes one Gist file per sport: betcouncil_bettingpros_{SPORT}.json
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bettingpros.com/",
}

# sport → (url_prefix, [market_slugs])
# Slugs come from the `markets` array embedded on the main prop-bets page for
# each sport. Only active markets with confirmed SSR props data are listed.
SPORT_MARKETS: dict[str, tuple[str, list[str]]] = {
    "MLB": (
        "https://www.bettingpros.com/mlb/picks/prop-bets",
        [
            "strikeouts",
            "hits",
            "runs",
            "rbi",
            "earned-runs-allowed",
            "doubles",
            "total-bases",
            "steals",
            "singles",
            "homeruns",
            "runs-hits-rbis",
            "hits-allowed",
            "outs-recorded",
            "walks-allowed",
        ],
    ),
    "WNBA": (
        "https://www.bettingpros.com/wnba/picks/prop-bets",
        [
            "points",
            "rebounds",
            "assists",
            "threes",
            "blocks",
            "steals",
            "points-rebounds",
            "points-assists",
            "rebounds-assists",
            "points-assists-rebounds",
        ],
    ),
    "NBA": (
        "https://www.bettingpros.com/nba/picks/prop-bets",
        [
            "points",
            "rebounds",
            "assists",
            "threes",
            "blocks",
            "steals",
            "points-rebounds",
            "points-assists",
            "rebounds-assists",
            "points-assists-rebounds",
        ],
    ),
    "NHL": (
        "https://www.bettingpros.com/nhl/picks/prop-bets",
        [
            "goals",
            "points",
            "assists",
            "shots",
            "saves",
            "blocked-shots",
        ],
    ),
    "NFL": (
        "https://www.bettingpros.com/nfl/picks/prop-bets",
        # Slugs confirmed active during the season — offseason returns 0 props
        # from the default page, which is fine (exits cleanly).
        [],
    ),
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def extract_props_from_html(html: str) -> list:
    """Pull the `"props":[...]` blob embedded by BettingPros SSR."""
    idx = html.find('"props":[{"sport"')
    if idx < 0:
        return []
    start = html.index("[", idx)
    depth = 0
    end = start
    for i, ch in enumerate(html[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    try:
        return json.loads(html[start:end])
    except Exception:
        return []


def fetch_market_page(url: str, sport: str, slug: str) -> list:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        DEBUG_LOG.append({
            "sport": sport,
            "slug": slug,
            "url": url,
            "status": r.status_code,
            "body_len": len(r.text),
        })
        if r.status_code != 200:
            log(f"  {sport}/{slug}: HTTP {r.status_code} — skipping")
            return []
        props = extract_props_from_html(r.text)
        return props
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "slug": slug, "url": url, "error": str(e)[:200]})
        log(f"  {sport}/{slug}: exception — {e}")
        return []


def fetch_sport(sport: str) -> list:
    base_url, slugs = SPORT_MARKETS[sport]

    # Always fetch the default (no-slug) page first — it often has "top"
    # props that may not appear on any individual market page.
    all_props: list = []
    seen: set = set()  # dedup key: (event_id, participant_id, market_id)

    pages = [""] + slugs  # "" = default page

    for slug in pages:
        url = f"{base_url}/{slug}/" if slug else f"{base_url}/"
        props = fetch_market_page(url, sport, slug or "default")

        new = 0
        for p in props:
            key = (
                p.get("event_id"),
                (p.get("participant") or {}).get("id"),
                p.get("market_id"),
            )
            if key not in seen:
                seen.add(key)
                all_props.append(p)
                new += 1

        log(f"  {sport}/{slug or 'default'}: {len(props)} props, {new} new (total {len(all_props)})")

        # Polite delay between pages — avoid hammering the CDN
        if slug != pages[-1]:
            time.sleep(random.uniform(0.8, 1.8))

    log(f"{sport}: {len(all_props)} unique props across {len(pages)} pages")
    return all_props


# ── Gist helpers (unchanged from API version) ────────────────────────────────

def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
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
            log(f"Shared GitHub token budget low ({remaining} left) — skipping this run cleanly")
            return False
    except Exception as e:
        log(f"rate_limit check failed (continuing anyway): {e}")
    return True


def push_files(files_payload: dict, github_token: str) -> int:
    if not _rate_limit_ok(github_token):
        return 0
    for attempt in range(6):
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
        if resp.status_code in (409, 403, 429) and attempt < 5:
            base_wait = min((attempt + 1) * 8, 60)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist {resp.status_code} — retrying in {wait:.1f}s (attempt {attempt + 1}/6)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload: dict = {}
    any_data = False

    for sport in SPORT_MARKETS:
        props = fetch_sport(sport)
        if props:
            any_data = True
        files_payload[f"betcouncil_bettingpros_{sport}.json"] = {
            "content": json.dumps({
                "captured_at": now_iso,
                "sport": sport,
                "source": "bettingpros_html_ssr",
                "props": props,
            })
        }

    files_payload["betcouncil_bettingpros_debug.json"] = {
        "content": json.dumps(
            {"captured_at": now_iso, "requests": DEBUG_LOG[:50]},
            indent=2,
        )
    }

    if not any_data:
        log("No data captured across any sport — pushing debug only, not overwriting existing data with empty")
        push_files({"betcouncil_bettingpros_debug.json": files_payload["betcouncil_bettingpros_debug.json"]}, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
