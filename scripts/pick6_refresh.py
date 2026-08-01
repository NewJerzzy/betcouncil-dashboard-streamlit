"""
pick6_refresh.py — DraftKings Pick6 via pickCardsByCategory (public, no auth)
================================================================================

Confirmed live 2026-08-01 via GH Actions workflow_dispatch (not guessed):

  GET https://pick6.draftkings.com/resources/pickCardsByCategory/{pickGroupId}/{categoryId}

Returns real JSON with everything needed in ONE call -- this fully replaces
the old approach (parsing the React Router stream payload for pick lines,
which had no way to resolve player names -- dkId and name were confirmed
in separate, uncorrelated dict shapes in that older payload):

  pickCardByPickableId  -- pick lines, target values, multipliers per player
  entityInfoByDkId       -- dkId -> {name, fullName, jerseyNum, imageUrls}
                            CONFIRMED to contain real full names (e.g.
                            "James McCann", "Jose Ramirez"), not placeholders.

pickGroupId is date/sport-dependent, embedded in the homepage's escaped
RSC-stream payload as the literal substring \"pickGroupId\",\"151460\" --
extracted fresh each run rather than hardcoded (it changes daily).

Category IDs: confirmed 1-20 all return real MLB data when tested live.
This script sweeps that range per sport and stops early once no new
pickable IDs are found across CATEGORY_STOP_STREAK consecutive categories
(some sports/days have fewer than 20 real categories).

Pushes to betcouncil_pick6_props.json (matches what fetch_pick6_props_
from_gist already reads -- confirmed still wired into the app).
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
SPORTS = ["MLB", "NBA", "NFL", "NHL", "WNBA", "UFC", "SOCCER"]
MAX_CATEGORY = 20
CATEGORY_STOP_STREAK = 4

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
           "Accept": "application/json"}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def get_pick_group_id(sport: str) -> str | None:
    """Extract today's pickGroupId from the homepage's escaped RSC payload."""
    try:
        r = requests.get(f"https://pick6.draftkings.com/?sport={sport}",
                          headers=HEADERS, timeout=20)
        DEBUG_LOG.append({"sport": sport, "homepage_status": r.status_code})
        if r.status_code != 200:
            return None
        m = re.search(r'\\?"pickGroupId\\?",\\?"(\d+)\\?"', r.text)
        return m.group(1) if m else None
    except Exception as e:
        DEBUG_LOG.append({"sport": sport, "homepage_error": str(e)[:200]})
        return None


def fetch_category(pick_group_id: str, category_id: int) -> dict | None:
    try:
        r = requests.get(
            f"https://pick6.draftkings.com/resources/pickCardsByCategory/{pick_group_id}/{category_id}",
            headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def parse_category(data: dict, sport: str) -> list:
    """Combine pickCardByPickableId (lines) + entityInfoByDkId (names)."""
    props = []
    cards = data.get("pickCardByPickableId", {}) or {}
    entities = data.get("entityInfoByDkId", {}) or {}
    markets = data.get("pickSixMarketById", {}) or {}

    for pickable_id, card in cards.items():
        card_entities = card.get("entities", []) or []
        if not card_entities:
            continue
        dk_id = str(card_entities[0].get("dkId", ""))
        entity = entities.get(dk_id, {})
        player_name = entity.get("fullName") or entity.get("name")
        if not player_name:
            continue

        for market in card.get("activePickableMarkets", []) or []:
            market_id = market.get("pickSixMarketId")
            market_info = markets.get(str(market_id), {}) if market_id else {}
            stat_name = market_info.get("name") or market_info.get("displayName") or f"Market {market_id}"
            target_value = market.get("targetValue")
            selections = market.get("activeSelections", []) or []
            multiplier = selections[0].get("formattedStandingsMultiplier") if selections else None
            if target_value is None:
                continue
            props.append({
                "Player": player_name,
                "Prop": stat_name,
                "Line": target_value,
                "Multiplier": multiplier,
                "Book": "Pick6",
                "Sport": sport,
                "source": "pick6_pickcards_api",
                "captured_at": datetime.now(timezone.utc).isoformat(),
            })
    return props


def fetch_sport(sport: str) -> list:
    pick_group_id = get_pick_group_id(sport)
    if not pick_group_id:
        log(f"{sport}: no pickGroupId found, skipping")
        return []
    log(f"{sport}: pickGroupId={pick_group_id}")

    all_props = []
    seen_pickable_counts = []
    for cat in range(1, MAX_CATEGORY + 1):
        data = fetch_category(pick_group_id, cat)
        if not data:
            seen_pickable_counts.append(0)
        else:
            cards = data.get("pickCardByPickableId", {}) or {}
            seen_pickable_counts.append(len(cards))
            if cards:
                props = parse_category(data, sport)
                all_props.extend(props)
        if len(seen_pickable_counts) >= CATEGORY_STOP_STREAK and \
           all(c == 0 for c in seen_pickable_counts[-CATEGORY_STOP_STREAK:]):
            log(f"{sport}: stopping at category {cat} (last {CATEGORY_STOP_STREAK} empty)")
            break

    log(f"{sport}: {len(all_props)} props from {sum(1 for c in seen_pickable_counts if c)} non-empty categories")
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
            # A 200 doesn't guarantee the content actually landed -- confirmed
            # this session on VSIN's push (200 every time, file silently
            # absent). Verify each file is actually present in the response's
            # own returned file list before trusting it.
            returned_files = resp.json().get("files", {}) or {}
            missing = [fn for fn in files_payload if fn not in returned_files]
            if missing and attempt < 5:
                base_wait = min((attempt + 1) * 5, 30)
                log(f"Push returned 200 but {missing} missing from response -- retrying in {base_wait}s (attempt {attempt+1}/6)")
                time.sleep(base_wait)
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

    all_props = []
    for sport in SPORTS:
        try:
            props = fetch_sport(sport)
            all_props.extend(props)
        except Exception as e:
            log(f"{sport}: error — {e}")

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload = {
        "betcouncil_pick6_props.json": {
            "content": json.dumps({"captured_at": now_iso, "source": "pick6_pickcards_api",
                                    "props": all_props})
        },
        "betcouncil_pick6_debug.json": {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2)
        },
    }

    if not all_props:
        log("No props captured across any sport -- pushing debug only, not overwriting existing data with empty")
        push_files({"betcouncil_pick6_debug.json": files_payload["betcouncil_pick6_debug.json"]})
        return 1

    real_named = sum(1 for p in all_props if not p["Player"].startswith("dkId_"))
    log(f"Total: {len(all_props)} props, {real_named} with real resolved names")

    pushed = push_files(files_payload)
    log(f"Pushed {pushed} files" if pushed else "Push FAILED")
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
