r"""
pickswise_refresh.py — Pickswise picks/odds via Next.js RSC streaming payload (public, no auth)
================================================================================

Pickswise (pickswise.com == pickwise.com, same site) is a Next.js App
Router site using RSC (React Server Component) streaming — not the
older Pages Router __NEXT_DATA__ pattern, and no separate JSON API.
Every page's data is embedded in the RSC payload itself, retrievable by
requesting any page with header RSC: 1, which returns the raw
text/x-component stream instead of rendered HTML.

Confirmed live 2026-07-17 — no auth wall, no blur, no paywall on any
field (odds, article text, pick statement, confidence rating).

Two-step scrape per league:
  1. GET /{league}/picks/ with RSC: 1 -> parse "initialData" -> all
     games + consensus odds (moneyline/spread/total, single book only
     — per-book breakdown is null, a premium field)
  2. For each game, GET /{league}/games/{slug}/picks/ with RSC: 1 ->
     parse the pick object (rating, author, reasoning) + extract the
     explicit pick statement from the article tail via regex:
        r"(\w[^:]+) prediction: (.+?)(?:available at time of publishing|\.)\s*Playable to ([+-]\d+)"

Exact RSC parsing wasn't independently verified byte-for-byte before
this first deploy (confirmed the site/content is real and public via
search, but RSC payloads are a less common format than plain JSON) —
ships with self-diagnostic logging so a structure mismatch is caught
immediately.

Pushes to betcouncil_pickswise_{SPORT}.json.
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
BASE_URL = "https://www.pickswise.com"
LEAGUE_PATHS = {"MLB": "mlb", "NBA": "nba", "NFL": "nfl", "NHL": "nhl", "WNBA": "wnba"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/x-component",
    "RSC": "1",
}

PICK_STATEMENT_RE = re.compile(
    r"([\w .'-]+) prediction: (.+?)(?:available at time of publishing|\.)\s*Playable to ([+-]\d+)",
    re.IGNORECASE,
)

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def _extract_json_after_marker(text: str, marker: str):
    """
    RSC streams are line-delimited chunks like `3a:{"initialData":...}\n`.
    Find the marker string, then locate the JSON object that starts at
    the next `{` and balance braces to find its true end (can't just
    regex a fixed-size chunk — nested objects vary in length).

    Works when marker is itself a wrapper key whose value is the object
    we want (e.g. "initialData":{...}). Does NOT work when marker is a
    field *inside* a larger object with sibling fields after it (e.g.
    "shortReasoningHtml" is a string value, not an object — the next
    "{" after it belongs to some unrelated sibling object, not the
    object we actually want). Use _parse_rsc_chunks + _find_dict_with_key
    for that case instead.
    """
    idx = text.find(marker)
    if idx == -1:
        return None
    start = text.find("{", idx)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def _parse_rsc_chunks(text: str) -> list:
    """
    RSC responses are newline-delimited chunks: `3a:{...}` or `4:[...]`
    (a chunk ID, colon, then a JSON value — sometimes prefixed further
    with a type char like `3a:I[...]` for client references, which
    won't parse as JSON and are skipped). Returns every chunk value that
    successfully parses as JSON, so callers can search across all of
    them for a specific key rather than guessing position from a
    substring marker (a marker string found *inside* a value doesn't
    tell you where that value's enclosing object actually starts —
    this is what _extract_json_after_marker got wrong for
    "shortReasoningHtml", which found an unrelated sibling object).
    """
    chunks = []
    for line in text.split("\n"):
        m = re.match(r"^[0-9a-f]+:(.*)$", line.strip(), re.IGNORECASE)
        if not m:
            continue
        payload = m.group(1)
        if not payload or payload[0] not in "{[":
            continue
        try:
            chunks.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return chunks


def _find_dict_with_key(obj, target_key: str, depth=0, max_depth=15):
    """Walk a parsed structure looking for the first dict that has
    target_key as one of its own keys (not nested inside it)."""
    if depth > max_depth:
        return None
    if isinstance(obj, dict):
        if target_key in obj:
            return obj
        for v in obj.values():
            found = _find_dict_with_key(v, target_key, depth + 1, max_depth)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_dict_with_key(item, target_key, depth + 1, max_depth)
            if found:
                return found
    return None


def fetch_league_games(sport: str, league_path: str) -> list:
    url = f"{BASE_URL}/{league_path}/picks/"
    r = requests.get(url, headers=HEADERS, timeout=25)
    DEBUG_LOG.append({"sport": sport, "step": "picks_page", "url": url,
                       "status": r.status_code, "body_len": len(r.text),
                       "body_snippet": r.text[:400]})
    if r.status_code != 200:
        return []

    data = _extract_json_after_marker(r.text, '"initialData"')
    if data is None:
        DEBUG_LOG.append({"sport": sport, "note": "initialData marker not found or brace-matching failed",
                           "has_initialData_string": '"initialData"' in r.text,
                           "has_games_string": '"games"' in r.text,
                           "has_homeTeam_string": '"homeTeam"' in r.text})
        # marker approach failed — try treating the whole response as
        # concatenated RSC chunks and scanning each JSON-looking line
        for line in r.text.split("\n"):
            m = re.search(r"^\w+:(\{.*\})$", line.strip())
            if m and '"games"' in m.group(1):
                try:
                    data = json.loads(m.group(1))
                    break
                except json.JSONDecodeError:
                    continue
    if not isinstance(data, dict):
        DEBUG_LOG.append({"sport": sport, "note": "could not locate initialData in RSC payload"})
        return []

    games = data.get("data", data.get("games", data.get("initialData", {}).get("games", [])))
    if not isinstance(games, list) or not games:
        DEBUG_LOG.append({"sport": sport, "note": "initialData found but no games list inside it",
                           "top_level_keys": list(data.keys())[:20],
                           "data_sample": json.dumps(data)[:800]})
        return []
    return games


def fetch_game_pick(league_path: str, slug: str) -> dict:
    url = f"{BASE_URL}/{league_path}/games/{slug}/picks/"
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        return {}

    chunks = _parse_rsc_chunks(r.text)
    pick_obj = None
    for chunk in chunks:
        found = _find_dict_with_key(chunk, "shortReasoningHtml")
        if found:
            pick_obj = found
            break
    result = dict(pick_obj) if isinstance(pick_obj, dict) else {}

    m = PICK_STATEMENT_RE.search(r.text)
    if m:
        result["pick_team_or_side"] = m.group(1).strip()
        result["pick_bet_and_odds"] = m.group(2).strip()
        result["pick_playable_to"] = m.group(3).strip()
    elif sum(1 for e in DEBUG_LOG if e.get("step") == "game_pick_diagnostic") < 5:
        DEBUG_LOG.append({"step": "game_pick_diagnostic", "url": url,
                           "num_chunks": len(chunks), "pick_obj_found": pick_obj is not None,
                           "pick_obj_sample": json.dumps(pick_obj)[:500] if pick_obj else None,
                           "has_prediction_word": "prediction:" in r.text.lower(),
                           "has_playable_word": "playable to" in r.text.lower(),
                           "body_len": len(r.text)})
    return result


def normalize_game(sport: str, game: dict, pick: dict) -> dict:
    home, away = game.get("homeTeam", {}), game.get("awayTeam", {})
    odds_list = game.get("odds", [])
    return {
        "sport": sport, "game_id": game.get("id"), "slug": game.get("slug"),
        "starts_at": game.get("startsAt"),
        "home_team": home.get("shortName"), "away_team": away.get("shortName"),
        "home_team_long": home.get("longName"), "away_team_long": away.get("longName"),
        "venue": game.get("venueName"),
        "odds": [{"title": o.get("title"), "book_odds": o.get("bookOdds")} for o in odds_list if isinstance(o, dict)],
        "pick_rating": pick.get("rating"), "pick_author": (pick.get("author") or {}).get("name"),
        "pick_reasoning": pick.get("shortReasoningHtml"),
        "pick_side": pick.get("pick_team_or_side"), "pick_bet": pick.get("pick_bet_and_odds"),
        "pick_playable_to": pick.get("pick_playable_to"),
    }


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=30,
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
        if resp.status_code in (403, 429, 409) and attempt < 4:
            # 403/429 = secondary rate limit (many workflows sharing one
            # GITHUB_TOKEN can burst-trigger this when GitHub bunches
            # scheduled cron runs near the top of the hour). 409 = another
            # workflow wrote to this same shared Gist at the same instant
            # (confirmed real: multiple unrelated scripts on tight cron
            # schedules collide on this exact shared resource). True
            # exponential backoff + random jitter -- without jitter, every
            # script that collided at T+0 would all retry at the identical
            # T+10 and just collide again.
            base_wait = min(10 * (2 ** attempt), 90)  # 10, 20
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Check GitHub's remaining request budget for this shared token before
    doing any writes. With ~30 scripts sharing one token/Gist, the hourly
    5000-request budget can run dry during a busy stretch (confirmed real:
    2026-07-25 06:17-06:40 UTC, 403 'API rate limit exceeded for user ID').
    When that happens, skip this run cleanly (exit 0) instead of burning
    retries against an already-exhausted budget and getting flagged as a
    failure -- the next scheduled run picks the data back up once the
    hourly window resets."""
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} requests left this hour) -- skipping this run cleanly, next scheduled run will pick it up")
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
    any_data = False
    fatal_error = None

    try:
        for sport, league_path in LEAGUE_PATHS.items():
            try:
                games = fetch_league_games(sport, league_path)
            except Exception as e:
                import traceback
                log(f"  {sport}: error fetching games — {e}")
                DEBUG_LOG.append({"sport": sport, "step": "fetch_league_games_exception",
                                   "error": str(e), "traceback": traceback.format_exc()[-1500:]})
                continue
            if not games:
                log(f"  {sport}: 0 games")
                continue

            normalized = []
            for g in games[:30]:  # reasonable cap per run
                slug = g.get("slug") if isinstance(g, dict) else None
                pick = {}
                if slug:
                    try:
                        pick = fetch_game_pick(league_path, slug)
                    except Exception as e:
                        log(f"  {sport}/{slug}: pick fetch error — {e}")
                try:
                    normalized.append(normalize_game(sport, g, pick))
                except Exception as e:
                    import traceback
                    DEBUG_LOG.append({"sport": sport, "step": "normalize_game_exception",
                                       "error": str(e), "traceback": traceback.format_exc()[-1000:]})

            any_data = True
            log(f"  {sport}: {len(normalized)} games")
            files_payload[f"betcouncil_pickswise_{sport}.json"] = {
                "content": json.dumps({
                    "source": "pickswise", "sport": sport,
                    "captured_at": now_iso, "games": normalized,
                })
            }
    except Exception as e:
        import traceback
        fatal_error = {"error": str(e), "traceback": traceback.format_exc()}
        log(f"FATAL unhandled error: {e}")

    files_payload["betcouncil_pickswise_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:30],
                                "fatal_error": fatal_error}, indent=2)
    }

    if not any_data:
        log("No data captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
