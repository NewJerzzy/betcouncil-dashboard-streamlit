"""
covers_consensus_refresh.py — Covers.com public betting consensus
====================================================================

Converts the existing in-app fetch_covers_consensus() (fetchers.py) into
a scheduled server-side scraper. That function's parsing logic was
already verified correct against the real live page (Jul 9 2026 fix
notes in its docstring) -- this just moves it to a reliable cron+Gist
pattern instead of a risky synchronous call at board-load time, whose
primary Gist-backed path (a browser harvester) has never actually
captured anything (zero betcouncil_covers_*.json files existed in the
Gist as of 2026-07-31, confirmed).

URL: https://contests.covers.com/consensus/topconsensus/{sport}/overall
Plain server-rendered HTML (no embedded JSON). Real per-row structure:
  - Away team:  <span class="covers-CoversConsensus-table--teamBlock">
  - Home team:  <span class="covers-CoversConsensus-table--teamBlock2">
  - Consensus%: <span class="covers-CoversConsensus-consensusTable--low">
                and "...--high"> (magnitude only, paired with team names
                by DOM order, not by the low/high label itself)

Returns public PICK percentage only (not a money/handle percentage --
Covers' free page doesn't expose that split). This is a genuine public-
lean signal, not a full tickets-vs-money RLM signal on its own.
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
SPORT_MAP = {"MLB": "mlb", "NBA": "nba", "NFL": "nfl", "NHL": "nhl",
             "WNBA": "wnba", "CFL": "cfl"}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "text/html"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_sport(sport: str, slug: str) -> dict:
    url = f"https://contests.covers.com/consensus/topconsensus/{slug}/overall"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        DEBUG_LOG.append({"sport": sport, "url": url, "status": r.status_code, "body_len": len(r.text)})
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "url": url, "error": str(e)[:200]})
        return {}
    if r.status_code != 200:
        return {}

    results = {}
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        DEBUG_LOG.append({"sport": sport, "error": "bs4 not installed"})
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    for row in soup.find_all("tr"):
        away_block = row.find("span", class_="covers-CoversConsensus-table--teamBlock")
        home_block = row.find("span", class_="covers-CoversConsensus-table--teamBlock2")
        if not away_block or not home_block:
            continue
        away_team = away_block.get_text(strip=True)
        home_team = home_block.get_text(strip=True)
        if not away_team or not home_team:
            continue
        pct_spans = row.find_all("span", class_=lambda c: c and (
            "covers-CoversConsensus-consensusTable--low" in c or
            "covers-CoversConsensus-consensusTable--high" in c
        ))
        pcts = []
        for span in pct_spans:
            m = re.search(r"(\d{1,3})%", span.get_text(strip=True))
            if m:
                pcts.append(int(m.group(1)))
        if len(pcts) != 2:
            continue
        results[f"{away_team} @ {home_team}"] = {"away_pct": pcts[0], "home_pct": pcts[1]}

    log(f"{sport}: {len(results)} matchups")
    return results


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} left) -- skipping this run cleanly")
            return False
    except Exception as e:
        log(f"rate_limit check failed (continuing anyway): {e}")
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
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 4:
                wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {wait}s")
                time.sleep(wait)
                continue
            if missing:
                log(f"Push returned 200 but {missing} still missing after retries -- treating as failed")
                return len(files_payload) - len(missing)
            return len(files_payload)
        if resp.status_code in (409, 403, 429) and attempt < 5:
            base_wait = min((attempt + 1) * 8, 60)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/6)")
            time.sleep(wait)
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
    files_payload = {}
    any_data = False

    for sport, slug in SPORT_MAP.items():
        matchups = fetch_sport(sport, slug)
        if matchups:
            any_data = True
        files_payload[f"betcouncil_covers_{sport}.json"] = {
            "content": json.dumps({"captured_at": now_iso, "sport": sport,
                                    "source": "covers_consensus_scraper", "data": matchups})
        }

    files_payload["betcouncil_covers_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
    }

    if not any_data:
        log("No data captured across any sport -- pushing debug only, not overwriting existing data with empty")
        return 1

    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
