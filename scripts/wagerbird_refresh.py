"""
wagerbird_refresh.py — WagerBird free MLB picks (wagerbird.com/picks)
================================================================================

Public page, no auth. Next.js RSC payload embedded as
self.__next_f.push([1,"...json-escaped-string..."]) script blocks in the raw
HTML — plain GET + regex parse, no browser/JS execution needed.

Per pick: sport, matchup, market/pick text, odds, confidence tier
(WB2/WB3/GEMS) + numeric score, written rationale, graded result
(Win/Loss/pending), game time, prediction_url (which encodes pick_date).

Confirmed live 2026-07-17: date-regex scan across a raw page fetch turned up
dates from 2026-05-23 through 2026-07-17 (today), confirming continuous
real-time updates rather than a frozen archive -- this was the deciding
check before building, since an unrelated public feed (Snapp's /news) was
independently found to be frozen ~3 months stale during the same research
pass and was correctly rejected for that reason.

Verified live via GitHub Actions (run 29624366106, 2026-07-18): 200 fetch,
137 RSC push blocks found, 114 matched as pick blocks, 110 deduped picks
parsed with real matchups/odds/rationale/graded results. Confirmed correct
via the Gist output, not just a green checkmark. Ships with debug logging
(raw pick-block count, parse failures, a raw HTML snippet on zero-pick runs)
so a future schema drift is caught immediately instead of silently returning
zero picks.

Pushes to betcouncil_wagerbird_picks.json (+ betcouncil_wagerbird_debug.json).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
import time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
URL = "https://wagerbird.com/picks"

HEADERS = {
    "Accept": "text/html",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}

PUSH_BLOCK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.DOTALL)
PREDICTION_URL_RE = re.compile(
    r'"href":"(/picks/mlb/[a-z0-9\-]+-prediction-(\d{4}-\d{2}-\d{2}))"'
)
SPORT_MATCHUP_RE = re.compile(
    r'text-\[#205FFF\]\\?","children":\["([A-Z]+)","[^"]*?","([^"]+)"\]'
)
GAME_TIME_RE = re.compile(
    r'text-\[#5A5A5A\]\\?","children":"([^"]+ET)"'
)
PICK_TITLE_RE = re.compile(
    r'font-barlow-condensed text-\[30px\][^"]*","children":"([^"]+)"'
)
ODDS_RE = re.compile(
    r'text-\[#171717\]\\?","children":"([+-]\d+)"'
)
TIER_SCORE_RE = re.compile(
    r'"children":\["([A-Z0-9]+)","[^"]*?(\d+)"?\]'
)
RATIONALE_RE = re.compile(
    r'leading-\[1\.55\] text-\[#5A5A5A\]\\?","children":"([^"]+)"'
)
RESULT_RE = re.compile(r'"children":"(Win|Loss)"')

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def decode_rsc_string(raw_field: str) -> str:
    try:
        return json.loads(f'"{raw_field}"')
    except Exception:
        return raw_field


def fetch_html():
    try:
        r = requests.get(URL, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"url": URL, "error": str(e)})
        return None
    DEBUG_LOG.append({"url": URL, "status": r.status_code, "bytes": len(r.text)})
    if r.status_code != 200:
        return None
    return r.text


def extract_picks(html: str):
    picks = []
    blocks = PUSH_BLOCK_RE.findall(html)
    DEBUG_LOG.append({"push_blocks_found": len(blocks)})

    pick_blocks_matched = 0
    for block in blocks:
        decoded = decode_rsc_string(block)
        pred_match = PREDICTION_URL_RE.search(decoded)
        if not pred_match:
            continue
        pick_blocks_matched += 1
        pred_url, pick_date = pred_match.groups()

        sport_matchup = SPORT_MATCHUP_RE.search(decoded)
        game_time = GAME_TIME_RE.search(decoded)
        title = PICK_TITLE_RE.search(decoded)
        odds = ODDS_RE.search(decoded)
        tier_score = TIER_SCORE_RE.search(decoded)
        rationale = RATIONALE_RE.search(decoded)
        result = RESULT_RE.search(decoded)

        picks.append({
            "sport": sport_matchup.group(1) if sport_matchup else None,
            "matchup": sport_matchup.group(2) if sport_matchup else None,
            "game_time": game_time.group(1) if game_time else None,
            "pick_text": title.group(1) if title else None,
            "odds": odds.group(1) if odds else None,
            "tier": tier_score.group(1) if tier_score else None,
            "confidence_score": int(tier_score.group(2)) if tier_score else None,
            "rationale": rationale.group(1) if rationale else None,
            "result": result.group(1) if result else "pending",
            "pick_date": pick_date,
            "prediction_url": f"https://wagerbird.com{pred_url}",
        })

    DEBUG_LOG.append({"pick_blocks_matched": pick_blocks_matched})

    seen = set()
    deduped = []
    for p in picks:
        key = (p["prediction_url"], p["pick_text"], p["odds"])
        if key in seen or not p["pick_text"]:
            continue
        seen.add(key)
        deduped.append(p)

    return deduped


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(3):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
        )
        if resp.status_code in (200, 201):
            return len(files_payload)
        if resp.status_code in (403, 429) and attempt < 2:
            # Secondary rate limit -- many workflows sharing one GITHUB_TOKEN
            # can burst-trigger this when GitHub bunches scheduled cron runs
            # near the top of the hour (confirmed real: 15 unrelated scripts
            # all failed in the same ~10min window on 2026-07-20, every one
            # with a successful underlying data fetch, pointing at the shared
            # Gist push as the actual failure point). Back off and retry
            # instead of failing the whole job over a transient limit.
            wait = 10 * (attempt + 1)
            log(f"Gist push got {resp.status_code} (likely rate limit) -- retrying in {wait}s")
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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    html = fetch_html()
    files_payload = {}

    if html is None:
        log("Fetch failed — see debug log")
        files_payload["betcouncil_wagerbird_debug.json"] = {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15]}, indent=2)
        }
        push_files(files_payload, github_token)
        return 1

    picks = extract_picks(html)
    # WagerBird dates picks by US Eastern game day, not UTC — comparing
    # against UTC "today" undercounts near midnight UTC (i.e. all evening
    # ET games). Use the most recent pick_date actually present instead.
    latest_date = max((p["pick_date"] for p in picks if p["pick_date"]), default=today)
    todays_picks = [p for p in picks if p["pick_date"] == latest_date]
    log(f"Parsed {len(picks)} total picks, {len(todays_picks)} dated on latest slate ({latest_date})")

    files_payload["betcouncil_wagerbird_picks.json"] = {
        "content": json.dumps({
            "source": "wagerbird_picks_page",
            "captured_at": now_iso,
            "total_picks": len(picks),
            "todays_picks_count": len(todays_picks),
            "picks": picks,
        }, indent=2)
    }
    files_payload["betcouncil_wagerbird_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15],
                                "html_snippet": html[:1000] if len(picks) == 0 else None},
                               indent=2)
    }

    if not picks:
        log("0 picks parsed — regex likely drifted from live markup, see debug snippet")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
