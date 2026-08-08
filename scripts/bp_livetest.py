"""
bettingpros_refresh.py — BettingPros props API (public, no auth)
====================================================================

GET https://api.bettingpros.com/v3/props?sport={SPORT}&limit=50

Confirmed live 2026-07-31, all 5 sports (MLB/NBA/NHL/WNBA/NFL — NFL
returns 0 results, expected, offseason). Every other endpoint on this
API (/v3/picks, /v3/events, /v3/players, /v3/markets, /v3/books,
/v3/offers) returns 403 -- /v3/props is the only open door.

The genuinely new piece for BetCouncil: `performance` — how many times
a player hit over/under on THIS SPECIFIC PROP in their last 1/5/10/15/20
games, season, prior season, and h2h vs this opponent, plus current
streak. BetCouncil has a whole module reserved for this
(hitrate_logger.py) whose compute_hit_rate() is a stub that always
returns None ("needs resolved data... future") -- this fills that gap
directly with real data instead of building the resolved-outcome
pipeline that stub was waiting on.

Also captures BettingPros' own line/consensus/odds/probability/EV/
bet_rating and projection (their model's own O/U call) per prop --
useful supplemental context, though the hit-rate/streak block is the
part nothing else in the codebase currently has at all.

Pushes one Gist file per sport: betcouncil_bettingpros_{SPORT}.json
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone

import requests
import re

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://api.bettingpros.com/v3/props"
SPORTS = ["MLB", "NBA", "NHL", "WNBA", "NFL"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "application/json"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


SITE_URL = "https://www.bettingpros.com/{sport_path}/props/"
_SPORT_PATHS = {"MLB": "mlb", "NBA": "nba", "NHL": "nhl", "WNBA": "wnba", "NFL": "nfl"}


def fetch_sport(sport: str) -> list:
    """
    api.bettingpros.com now returns a real HTTP 403 (AWS API Gateway
    ForbiddenException) as of 2026-08-07 -- confirmed via live testing,
    not a transient error. The site's own pages still embed the exact
    same prop data server-side in a JSON <script> tag, confirmed real
    and field-identical to the old API response. Scrapes that instead.
    """
    all_props = []
    seen_ids = set()
    sport_path = _SPORT_PATHS.get(sport, sport.lower())
    page = 1
    while page <= 12:
        url = SITE_URL.format(sport_path=sport_path)
        try:
            r = requests.get(url, headers=HEADERS, params={"page": page}, timeout=20)
            DEBUG_LOG.append({"sport": sport, "page": page, "status": r.status_code, "body_len": len(r.text)})
        except Exception as e:
            DEBUG_LOG.append({"sport": sport, "page": page, "error": str(e)[:200]})
            break
        if r.status_code != 200:
            break

        blocks = re.findall(r'<script type="application/json" class="island-props">(.*?)</script>', r.text, re.DOTALL)
        data = None
        for blk in blocks:
            if '"events"' not in blk:
                continue
            try:
                parsed = json.loads(blk)
                if parsed.get("props"):
                    data = parsed
                    break
            except Exception:
                continue
        if data is None:
            break

        props = data.get("props", [])
        if not isinstance(props, list) or not props:
            break

        new_count = 0
        for p in props:
            pid = (p.get("participant", {}).get("id"), p.get("market_id"))
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            all_props.append(p)
            new_count += 1

        # site shows a fixed ~25/page; stop once a page adds nothing new
        # (last page or duplicate content) rather than assuming a fixed count
        if new_count == 0:
            break
        page += 1

    log(f"{sport}: {len(all_props)} props ({page} page(s))")
    return all_props



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

    for sport in SPORTS:
        props = fetch_sport(sport)
        if props:
            any_data = True
        files_payload[f"betcouncil_bettingpros_{sport}.json"] = {
            "content": json.dumps({"captured_at": now_iso, "sport": sport,
                                    "source": "bettingpros_v3_props", "props": props})
        }

    files_payload["betcouncil_bettingpros_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
    }

    if not any_data:
        log("No data captured across any sport -- pushing debug only, not overwriting existing data with empty")
        return 1

    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1



# --- test wrapper ---
import sys as _s
_all = []
for sport in ["MLB", "NBA", "NHL", "WNBA", "NFL"]:
    props = fetch_sport(sport)
    _all.append((sport, len(props), props[0] if props else None))
_result = {"summary": [(s, n) for s, n, p in _all]}
for s, n, p in _all:
    if p:
        _result[f"{s}_sample"] = p
        break
_tok = os.environ.get("GITHUB_TOKEN")
requests.patch(f"https://api.github.com/gists/{GIST_ID}",
    headers={"Authorization": f"Bearer {_tok}", "Accept": "application/vnd.github+json"},
    json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps(_result, default=str)}}})
print("done")
