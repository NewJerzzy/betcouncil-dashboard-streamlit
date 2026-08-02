"""
propsmadness_refresh.py — PropsMadness player prop + game line slate (public, no auth)
================================================================================

api.propsmadness.com — separate Express backend behind the propsmadness.com
Next.js frontend (Clerk-gated for premium UI features only; the API itself
has no auth on these routes). Discovered via bundle URL-builder extraction,
not from official docs — confirmed live during discovery: /offer/mlb/bets/
player-strikeouts returned 24 games / 261 player-level offers on a real
query.

Primary endpoint (the "jackpot" — full slate in one call):
    GET https://api.propsmadness.com/api/offer/{leagueCode}/bets/{marketCode}
    -> {leagueCode, market, matchOffers, playerInjuryMap}

leagueCodes confirmed: mlb, nba, wnba, nfl, fifa-world-cup (+ ~15 soccer)
MLB marketCodes confirmed: player-strikeouts, player-pitcher-outs,
player-earned-runs, player-hits-allowed, player-hits, player-home-runs,
player-total-bases, player-hits-runs-rbis, player-runs, player-rbis,
player-walks, player-stolen-bases, moneyline, run-line, total-runs,
team-total, point-spread

Each offer carries an offerType: "fallback" (live book line — the useful
case), "locked" (line hidden behind subscription — title/player still
visible, no line), or "noOffer" (no current line, historical reference
only). Only "fallback" offers are pushed as usable; locked/noOffer are
counted in debug output but not treated as real lines.

NOT independently verified live from this sandbox — api.propsmadness.com
isn't in this environment's network allowlist, so this ships from the
discovery session's findings, same caveat class as edgeterminal_refresh.py's
first deploy. Ships with full debug logging (per-market row counts, a raw
sample offer) so a schema drift is caught on first live Actions run instead
of silently returning nothing.

Pushes to betcouncil_propsmadness_{LEAGUE}_{MARKET}.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import random
import time

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
BASE_URL = "https://api.propsmadness.com/api"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}

# MLB only for now — this is an in-season sport with the richest confirmed
# market list from discovery. Other leagues (nba/wnba/nfl/soccer) use the
# same endpoint shape and can be added once MLB is confirmed live.
LEAGUE = "mlb"
MARKETS = [
    "player-strikeouts", "player-hits", "player-home-runs",
    "player-total-bases", "player-rbis", "player-runs",
    "player-walks", "player-stolen-bases", "player-earned-runs",
    "player-hits-allowed", "player-pitcher-outs", "player-hits-runs-rbis",
    "moneyline", "run-line", "total-runs",
]

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_market(league: str, market: str):
    url = f"{BASE_URL}/offer/{league}/bets/{market}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"market": market, "url": url, "error": str(e)})
        return None
    DEBUG_LOG.append({"market": market, "url": url, "status": r.status_code,
                       "body_snippet": r.text[:300]})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def extract_usable_offers(payload: dict) -> list:
    """
    Real structure confirmed live (2026-07-18, Actions run 29625921231):
    matchOffers[].match.{id, homeTeam, awayTeam, startDateTimestamp,
    homeScore, awayScore} + matchOffers[].offer[] (a LIST despite the
    singular key name), each offer = {player: {id, firstName, lastName,
    position, teamId, ...}, bet: {sportsbook, market, line, odds},
    offerType, fallbackLine, referenceBet}. Line/odds live under bet.*,
    not at the offer's top level — first version of this parser assumed
    flat top-level fields and silently produced empty/null records every
    time despite a 200 response; this version was verified against the
    real captured sample before being trusted.
    """
    offers = []
    match_offers = payload.get("matchOffers", [])
    if not isinstance(match_offers, list):
        return offers
    for match_entry in match_offers:
        if not isinstance(match_entry, dict):
            continue
        match_meta = match_entry.get("match", {}) or {}
        match_id = match_meta.get("id")
        home = match_meta.get("homeTeam", {}) or {}
        away = match_meta.get("awayTeam", {}) or {}
        raw_offers = match_entry.get("offer") or match_entry.get("offers") or []
        if isinstance(raw_offers, dict):
            raw_offers = [raw_offers]
        for o in raw_offers:
            if not isinstance(o, dict):
                continue
            if o.get("offerType") != "fallback":
                continue  # skip locked/noOffer — no real line to use
            player = o.get("player", {}) or {}
            bet = o.get("bet", {}) or {}
            player_name = " ".join(filter(None, [player.get("firstName"), player.get("lastName")])) or None
            offers.append({
                "match_id": match_id,
                "home_team": home.get("nameAbbreviation") or home.get("shortName"),
                "away_team": away.get("nameAbbreviation") or away.get("shortName"),
                "start_timestamp": match_meta.get("startDateTimestamp"),
                "player_id": player.get("id"),
                "player_name": player_name,
                "position": player.get("position"),
                "line": bet.get("line") if bet.get("line") is not None else o.get("fallbackLine"),
                "odds": bet.get("odds"),
                "book": bet.get("sportsbook"),
                "market": (bet.get("market") or {}).get("slug"),
                "offer_type": o.get("offerType"),
            })
    return offers


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
            base_wait = min(10 * (2 ** attempt), 90)
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
    sample_saved = False

    for market in MARKETS:
        try:
            payload = fetch_market(LEAGUE, market)
        except Exception as e:
            log(f"  {market}: error — {e}")
            continue
        if not payload:
            log(f"  {market}: no data / non-200")
            continue
        offers = extract_usable_offers(payload)
        log(f"  {market}: {len(offers)} usable offers "
            f"({len(payload.get('matchOffers', []))} games in slate)")
        if offers:
            any_data = True
            files_payload[f"betcouncil_propsmadness_{LEAGUE}_{market}.json"] = {
                "content": json.dumps({
                    "source": "propsmadness", "league": LEAGUE, "market": market,
                    "captured_at": now_iso, "offers": offers,
                    "injury_map": payload.get("playerInjuryMap", {}),
                })
            }
        if not sample_saved and payload.get("matchOffers"):
            DEBUG_LOG.append({"raw_sample_match": payload["matchOffers"][0]})
            sample_saved = True

    files_payload["betcouncil_propsmadness_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:20]}, indent=2, default=str)
    }

    if not any_data:
        log("No usable offers captured across any market — see debug log")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
