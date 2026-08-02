"""
lineterminal_refresh.py — LineTerminal (Inside Edge Inc) prop research data
================================================================================

lineterminal.com — a prop-research site powered by Inside Edge Inc
analytics. No Cloudflare, no auth wall on the core data endpoints.

REAL SCHEMA CONFIRMED (not guessed): a prior session manually pushed a
real, live pull of this data straight to the Gist on 2026-07-18 without
committing any code — this script's parser is built directly against that
actual captured payload (2,046 real MLB props across 14 games, verified
structure below), not against the site's marketing description. The
FETCH URLs below are inferred from that session's own description of the
endpoints it hit and have NOT been independently re-verified live from
this sandbox (lineterminal.com isn't in this environment's network
allowlist) — confirm on first live Actions run.

Confirmed public endpoints (per the prior session, unverified by this one):
    GET /api/props?sport={sport}&date=YYYY-MM-DD   -> full prop slate
    GET /api/games/{league}/lineups                -> starters, weather, pitcher stats
    GET /api/pulse/{league}                        -> team matchup notes

Locked (401 / canSeeAll:false, not attempted here): /api/picks,
/api/swing-signals/today, /api/stats, /api/games (full feed).

Real prop record shape (confirmed from actual captured data):
    {id, player_name, player_team, market, stat_label, stat, point,
     line_type, status, first_seen, updated_at, headshot_url,
     game_context: {game_total, game_spread, is_home, is_favorite,
                     player_ml, home_ml, away_ml},
     analysis: {hit_rate, hit_rate_l5/l10/l20, roi_l5/l10/szn_over/under,
                consistency, sample_size, avg_value, edge, grade, caution,
                splits: {home,away,favorite,underdog,win,loss},
                contextual_splits: {spread:{...}, total:{...}},
                current_season, hit_rate_szn, sample_size_szn,
                splits_szn, at_line_* (season record vs this exact line),
                verdict: {recommend, side, tier, edgePct, modelProbPct,
                          impliedProbPct, fairProbPct, bestPrice, bestBook,
                          confidence, corroboration, caution,
                          overEdgePct, underEdgePct, bothSidesOffered,
                          drivers: [str, ...]},
                enrichment},
     lines: {} (often empty; book pricing mainly comes via verdict.bestPrice/bestBook)}

`verdict` is the actionable summary (model prob vs implied/fair prob,
recommended side, tier, best book+price, plain-language drivers) — this
is the field worth surfacing, not the full analysis blob.

Slimmed on push: per-prop recent_games logs / last5/last10 value arrays
are dropped (redundant with the summary hit-rate fields already present)
to stay under the Gist 10MB-per-file limit — same reason the prior
session's manual push needed slimming (MLB was 14MB unslimmed).

Pushes to betcouncil_lineterminal_props_{SPORT}.json (+ lineups/pulse
for MLB). MLB + WNBA only initially, matching the prior session's scope.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://lineterminal.com/api"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}

SPORTS = {
    "MLB": "baseball_mlb",
    "WNBA": "basketball_wnba",
    "NBA": "basketball_nba",
    "NFL": "americanfootball_nfl",
    "NHL": "icehockey_nhl",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url: str, params: dict = None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=25)
    except Exception as e:
        DEBUG_LOG.append({"url": url, "params": params, "error": str(e)})
        return None
    DEBUG_LOG.append({"url": url, "params": params, "status": r.status_code,
                       "body_snippet": r.text[:300]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def slim_prop(p: dict) -> dict:
    """
    Field names confirmed against a live raw sample (2026-07-18, Actions
    run debug capture) — the top level uses camelCase for several fields
    (gameContext, lineType, headshotUrl) while analysis.* is snake_case;
    first version of this parser guessed snake_case everywhere and
    game_context/line_type/headshot_url all silently came back None on
    every prop despite a 200 response and correct prop count — a
    same-shape-as-PropsMadness silent-parse-failure, caught by comparing
    live output against the manually-captured sample rather than trusting
    a clean exit code. analysis.last5_values/last10_values/recent_games/
    streak_visual are real and large (a big part of why the prior
    session's manual push needed slimming to fit the 10MB Gist limit) —
    dropped here since analysis already carries the same info as
    hit_rate_l5/l10/l20 summary fields.
    """
    analysis = p.get("analysis", {}) or {}
    verdict = analysis.get("verdict", {}) or {}
    game_context = p.get("gameContext") or {}
    return {
        "player_name": p.get("player_name"),
        "player_team": p.get("player_team"),
        "market": p.get("market"),
        "stat_label": p.get("stat_label"),
        "point": p.get("point"),
        "line_type": p.get("lineType"),
        "status": p.get("status"),
        "updated_at": p.get("updated_at"),
        "game_context": game_context if game_context else None,
        "hit_rate_l5": analysis.get("hit_rate_l5"),
        "hit_rate_l10": analysis.get("hit_rate_l10"),
        "hit_rate_l20": analysis.get("hit_rate_l20"),
        "hit_rate_szn": analysis.get("hit_rate_szn"),
        "sample_size_szn": analysis.get("sample_size_szn"),
        "edge": analysis.get("edge"),
        "grade": analysis.get("grade"),
        "caution": analysis.get("caution"),
        "at_line_rate_szn": analysis.get("at_line_rate_szn"),
        "at_line_total_szn": analysis.get("at_line_total_szn"),
        "verdict": {
            "recommend": verdict.get("recommend"),
            "side": verdict.get("side"),
            "tier": verdict.get("tier"),
            "edge_pct": verdict.get("edgePct"),
            "model_prob_pct": verdict.get("modelProbPct"),
            "implied_prob_pct": verdict.get("impliedProbPct"),
            "fair_prob_pct": verdict.get("fairProbPct"),
            "best_price": verdict.get("bestPrice"),
            "best_book": verdict.get("bestBook"),
            "confidence": verdict.get("confidence"),
            "corroboration": verdict.get("corroboration"),
            "drivers": verdict.get("drivers"),
        },
    }


def push_files(files_payload: dict, github_token: str) -> int:
    for attempt in range(5):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": files_payload}, timeout=60,
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
            # 409 = another workflow on this same shared Gist collided at
            # the same instant (confirmed real, multiple scripts on tight
            # cron schedules). True exponential backoff + random jitter --
            # without jitter, colliding scripts would all retry at the
            # same instant again.
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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    files_payload = {}
    any_data = False

    for sport_label, sport_param in SPORTS.items():
        payload = fetch_json(f"{BASE_URL}/props", params={"sport": sport_param, "date": today})
        if not payload or not payload.get("games"):
            log(f"  {sport_label}: no data / non-200 / empty games")
            continue
        games = payload["games"]
        if games and games[0].get("props") and sport_label == "MLB":
            DEBUG_LOG.append({"raw_sample_prop": games[0]["props"][0],
                               "raw_sample_game_keys": list(games[0].keys())})
        slim_games = []
        total_props = 0
        for g in games:
            slim_props = [slim_prop(p) for p in g.get("props", []) if isinstance(p, dict)]
            total_props += len(slim_props)
            slim_games.append({
                "event_id": g.get("event_id"),
                "home_team": g.get("home_team"),
                "away_team": g.get("away_team"),
                "commence_time": g.get("commence_time"),
                "props": slim_props,
            })
        log(f"  {sport_label}: {total_props} props across {len(slim_games)} games")
        if total_props:
            any_data = True
            files_payload[f"betcouncil_lineterminal_props_{sport_label}.json"] = {
                "content": json.dumps({
                    "source": "lineterminal", "sport": sport_label,
                    "captured_at": now_iso, "total_props": total_props,
                    "games": slim_games,
                }, default=str)
            }

    # MLB-only supplemental endpoints
    lineups = fetch_json(f"{BASE_URL}/games/mlb/lineups")
    if lineups:
        files_payload["betcouncil_lineterminal_lineups_MLB.json"] = {
            "content": json.dumps({"source": "lineterminal", "captured_at": now_iso,
                                    "data": lineups}, default=str)
        }
        any_data = True

    pulse = fetch_json(f"{BASE_URL}/pulse/mlb")
    if pulse:
        files_payload["betcouncil_lineterminal_pulse_MLB.json"] = {
            "content": json.dumps({"source": "lineterminal", "captured_at": now_iso,
                                    "data": pulse}, default=str)
        }
        any_data = True

    files_payload["betcouncil_lineterminal_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2, default=str)
    }

    if not any_data:
        log("No usable data captured across any endpoint — see debug log")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("UNHANDLED EXCEPTION:\n" + tb)
        try:
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                push_files({"betcouncil_lineterminal_debug.json": {
                    "content": json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(),
                                            "error": "unhandled_exception", "traceback": tb}, indent=2)
                }}, token)
        except Exception:
            pass
        sys.exit(1)
