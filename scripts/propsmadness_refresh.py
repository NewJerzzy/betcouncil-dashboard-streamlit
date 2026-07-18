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
    matchOffers structure not fully confirmed live from this sandbox — parsed
    defensively. If real shape differs, this under-produces rather than
    crashes, and the debug log's raw sample makes the mismatch visible on
    first run rather than silently returning nothing every run after.
    """
    offers = []
    match_offers = payload.get("matchOffers", [])
    if not isinstance(match_offers, list):
        return offers
    for match in match_offers:
        if not isinstance(match, dict):
            continue
        match_id = match.get("matchId") or match.get("id")
        # singular "offer" per discovery notes, but check plural too in
        # case that varies by market/league
        raw_offers = match.get("offer") or match.get("offers") or []
        if isinstance(raw_offers, dict):
            raw_offers = [raw_offers]
        for o in raw_offers:
            if not isinstance(o, dict):
                continue
            if o.get("offerType") != "fallback":
                continue  # skip locked/noOffer — no real line to use
            offers.append({
                "match_id": match_id,
                "player_id": o.get("playerId"),
                "player_name": o.get("playerName") or o.get("player", {}).get("name")
                    if isinstance(o.get("player"), dict) else o.get("playerName"),
                "line": o.get("line"),
                "over_odds": o.get("overOdds") or o.get("over"),
                "under_odds": o.get("underOdds") or o.get("under"),
                "book": o.get("book") or o.get("sportsbook"),
                "offer_type": o.get("offerType"),
            })
    return offers


def push_files(files_payload: dict, github_token: str) -> int:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": files_payload}, timeout=30,
    )
    if resp.status_code in (200, 201):
        return len(files_payload)
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return 0


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

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
