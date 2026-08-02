"""
wiseguyteam_refresh.py — WiseGuyTeam public betting splits (no auth)
================================================================================

wiseguyteam.com/betting-splits serves live public betting percentages — the
share of bets (ticket count) vs the share of money (handle) on each side —
across 9 sports, with sharp-money and big-money flags pre-calculated.

The page renders via an inline JS app that calls a Cloudflare Worker:

    GET https://inngest-worker.memberservice.workers.dev/sharp-report?sport={sport}

No auth, no cookies, no headers required beyond a standard User-Agent.
Confirmed open 2026-07-27. The worker lives at memberservice.workers.dev —
WGT's own Cloudflare Worker deployment.

Sports: mlb, nfl, nba, nhl, ufc, wnba, soccer, cfb, cbb

Response shape:
  {
    "sport": "mlb",
    "count": 16,
    "games": [ { ... } ],
    "wgtPlays": {"owner": 0, "official": 1, "total": 1}
  }

Per-game fields:
  gameID, time (epoch ms), timeLeft, live (bool), league, competition, round,
  away: {name, init, color}, home: {name, init, color},
  ml / sp / tot: {
      side1: {bet, handle, am, book, url},
      side2: {bet, handle, am, book, url},
      sharp: 0|1|2  (0=neither, 1=side1 sharp, 2=side2 sharp),
      big:   0|1|2  (0=neither, 1=side1 big money, 2=side2 big money),
      [tot only] line: float
  }

sp = spread (run line for MLB, puck line for NHL),
tot = total (over/under).

sharp flag: money % runs well ahead of bets % on a side (sharp action signal).
big flag:   a side has a heavily lopsided share of the total handle.

wgtPlays.total > 0 means WGT has a documented play on the board tonight
(members-only for the specific side, but the flag itself is public).

Pushes to betcouncil_wiseguyteam_{SPORT}.json + betcouncil_wiseguyteam_debug.json.
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://inngest-worker.memberservice.workers.dev/sharp-report"

# sport slug → display name
SPORTS = {
    "mlb":    "MLB",
    "nfl":    "NFL",
    "nba":    "NBA",
    "nhl":    "NHL",
    "ufc":    "UFC",
    "wnba":   "WNBA",
    "soccer": "SOCCER",
    "cfb":    "CFB",
    "cbb":    "CBB",
    # Confirmed via a real live API test 2026-07-28: sport=tennis returns
    # genuine live match data (37 real matches, real player names, real
    # moneyline structure) -- unlike golf/pga, which returned 0 games with
    # an empty structure on the same test, confirming golf genuinely has
    # no coverage here rather than just being an off-day.
    "tennis": "TENNIS",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://wiseguyteam.com/betting-splits",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_sport(sport_slug: str) -> dict:
    """Fetch the sharp-report for one sport. Returns the raw JSON dict."""
    url = BASE_URL
    params = {"sport": sport_slug}
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    DEBUG_LOG.append({
        "sport": sport_slug,
        "url": r.url,
        "status": r.status_code,
        "body_snippet": r.text[:400],
    })
    if r.status_code != 200:
        log(f"  {sport_slug}: HTTP {r.status_code}")
        return {}
    try:
        return r.json()
    except json.JSONDecodeError as e:
        log(f"  {sport_slug}: JSON decode error — {e}")
        return {}


def normalize_market(mkt: dict | None) -> dict | None:
    """Normalize a ml/sp/tot market dict into a clean structure."""
    if not mkt:
        return None

    def side(s: dict | None) -> dict:
        if not s:
            return {"bet_pct": None, "handle_pct": None, "odds": None, "book": None, "bet_url": None}
        return {
            "bet_pct":    s.get("bet"),
            "handle_pct": s.get("handle"),
            "odds":       s.get("am"),
            "book":       s.get("book") or None,
            "bet_url":    s.get("url") or None,
        }

    sharp_raw = mkt.get("sharp", 0)  # 0=no, 1=side1(away/over), 2=side2(home/under)
    big_raw   = mkt.get("big", 0)

    out = {
        "side1": side(mkt.get("side1") or mkt.get("over")),
        "side2": side(mkt.get("side2") or mkt.get("under")),
        "sharp_side": None if not sharp_raw else ("side1" if sharp_raw == 1 else "side2"),
        "big_money_side": None if not big_raw else ("side1" if big_raw == 1 else "side2"),
    }
    if "line" in mkt:
        out["line"] = mkt.get("line")
    return out


def normalize_game(sport_slug: str, g: dict) -> dict:
    """Flatten a raw game dict into a clean, analysis-ready structure."""
    away = g.get("away") or {}
    home = g.get("home") or {}

    ml  = normalize_market(g.get("ml"))
    sp  = normalize_market(g.get("sp"))
    tot = g.get("tot")
    if tot:
        # tot uses over/under keys instead of side1/side2
        tot_norm = normalize_market({
            "side1": tot.get("over"),
            "side2": tot.get("under"),
            "sharp": tot.get("sharp", 0),
            "big":   tot.get("big", 0),
            "line":  tot.get("line"),
        })
    else:
        tot_norm = None

    # Derive top-level sharp flags for easy downstream filtering
    sharp_flags = []
    if ml and ml.get("sharp_side"):
        sharp_flags.append(f"ml_{ml['sharp_side']}")
    if sp and sp.get("sharp_side"):
        sharp_flags.append(f"sp_{sp['sharp_side']}")
    if tot_norm and tot_norm.get("sharp_side"):
        sharp_flags.append(f"tot_{tot_norm['sharp_side']}")

    return {
        "sport":         sport_slug.upper(),
        "game_id":       g.get("gameID"),
        "league":        g.get("league"),
        "competition":   g.get("competition"),
        "round":         g.get("round"),
        "start_time_ms": g.get("time"),
        "time_left":     g.get("timeLeft") or None,
        "live":          g.get("live", False),
        "away_team":     away.get("name"),
        "away_abbr":     away.get("init"),
        "home_team":     home.get("name"),
        "home_abbr":     home.get("init"),
        "ml":            ml,
        "spread":        sp,
        "total":         tot_norm,
        "sharp_flags":   sharp_flags,   # ["ml_side2", "tot_side1"] etc — any market flagged sharp
        "has_sharp":     len(sharp_flags) > 0,
        "wgt_play":      g.get("wgtPlay", False),   # True = WGT has a documented play (member side hidden)
    }


def push_files(files_payload: dict, github_token: str) -> int:
    """
    NOTE (Aug 2 2026): this script's push has been observed failing
    persistently -- confirmed via live testing that BOTH a combined
    multi-file push AND a per-file-split push can fail the same way
    (200 response, content confirmed absent via the check below). The
    per-file split was tried and reverted -- it took ~9 minutes and
    still ultimately failed, worse than the combined approach, so this
    keeps the same hardened pattern used across the other 46 scripts
    in this codebase rather than a bespoke workaround that didn't
    actually help. Root cause not resolved; this at least reports
    failure honestly instead of silently succeeding.
    """
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
            base_wait = min(10 * (2 ** attempt), 90)
            wait = base_wait + random.uniform(0, base_wait * 0.4)
            log(f"Gist push got {resp.status_code} — retrying in {wait:.1f}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue
        log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
        return 0
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    """Skip cleanly if the shared GitHub token's hourly budget is almost gone
    (confirmed real problem 2026-07-25 with ~30 scripts sharing one token)."""
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
            log(
                f"Shared GitHub token budget low ({remaining} requests left this hour) "
                "— skipping this run cleanly, next scheduled run will pick it up"
            )
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

    now_iso = datetime.now(timezone.utc).isoformat()
    files_payload: dict = {}
    any_data = False

    for sport_slug, sport_display in SPORTS.items():
        try:
            raw = fetch_sport(sport_slug)
        except Exception as e:
            log(f"  {sport_display}: fetch error — {e}")
            continue

        games_raw = raw.get("games", [])
        wgt_plays = raw.get("wgtPlays", {})

        if not games_raw:
            log(f"  {sport_display}: 0 games")
            continue

        games = []
        for g in games_raw:
            try:
                games.append(normalize_game(sport_slug, g))
            except Exception as e:
                log(f"  {sport_display}: normalize error on game {g.get('gameID')} — {e}")

        sharp_count = sum(1 for g in games if g["has_sharp"])
        log(f"  {sport_display}: {len(games)} games, {sharp_count} with sharp flag"
            + (f", WGT plays: {wgt_plays.get('total',0)}" if wgt_plays.get("total") else ""))

        any_data = True
        files_payload[f"betcouncil_wiseguyteam_{sport_display}.json"] = {
            "content": json.dumps({
                "source":       "wiseguyteam",
                "sport":        sport_display,
                "captured_at":  now_iso,
                "wgt_plays":    wgt_plays,
                "games":        games,
            }, indent=2)
        }

    files_payload["betcouncil_wiseguyteam_debug.json"] = {
        "content": json.dumps({
            "captured_at": now_iso,
            "requests": DEBUG_LOG[:20],
        }, indent=2)
    }

    if not any_data:
        log("No sport data captured — pushing debug log only")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files to Gist {GIST_ID}")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
