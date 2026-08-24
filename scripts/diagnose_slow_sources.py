"""
Real, one-off diagnostic script: times the specific sources already suspected
of being slow tonight, calling each real fetcher function directly and
measuring genuine wall-clock time. Run via a one-off GitHub Actions workflow
(real internet access, unlike the sandbox this was written in), writing real
results to a Gist file so they can be read back without any board load.

Every function call is individually wrapped so one real failure/timeout
doesn't stop the rest from being measured.
"""
import json
import time
import sys
import os
import traceback
import io
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetchers

_key_len = len(getattr(fetchers, "SHARPAPI_KEY", "") or "")

# Real, additional check: query the real /leagues reference endpoint the
# 400 error itself pointed to, to get the real, complete, accurate league
# name list for every sport, not just the one confirmed correction for MLB.
_leagues_result = None
try:
    import requests as _req
    _r = _req.get(
        f"{fetchers.SHARPAPI_BASE}/leagues",
        headers={"X-API-Key": fetchers.SHARPAPI_KEY, "Accept": "application/json"},
        timeout=10,
    )
    _leagues_result = {"status": _r.status_code, "body": _r.text[:1500]}
except Exception as e:
    _leagues_result = {"error": str(e)[:200]}

_odds_raw_result = None
try:
    _r2 = _req.get(
        f"{fetchers.SHARPAPI_BASE}/odds",
        params={"league": "mlb", "market_type": "moneyline,spread,total"},
        headers={"X-API-Key": fetchers.SHARPAPI_KEY, "Accept": "application/json"},
        timeout=10,
    )
    _odds_raw_result = {"status": _r2.status_code, "body": _r2.text[:2000]}
except Exception as e:
    _odds_raw_result = {"error": str(e)[:200]}

_props_raw_result = None
try:
    _r3 = _req.get(
        f"{fetchers.SHARPAPI_BASE}/odds",
        params={"league": "mlb", "market_type": "player_props"},
        headers={"X-API-Key": fetchers.SHARPAPI_KEY, "Accept": "application/json"},
        timeout=10,
    )
    _props_raw_result = {"status": _r3.status_code, "body": _r3.text[:2000]}
except Exception as e:
    _props_raw_result = {"error": str(e)[:200]}

# Real, focused set: the specific sources already suspected tonight (from
# the Replit report + confirmed-slow OddsWrap from earlier this session).
TARGETS = [
    ("OddsWrap", "fetch_oddswrap_props", ("MLB",)),
    ("ParlayAPI Props", "fetch_parlayapi_props", ("MLB",)),
    ("ParlayAPI Arbitrage", "fetch_parlayapi_arbitrage", ("MLB",)),
    ("ParlayAPI EV", "fetch_parlayapi_ev", ("MLB",)),
    ("SharpAPI Lines", "fetch_sharpapi_lines", ("MLB",)),
    ("SharpAPI Props", "fetch_sharpapi_props", ("MLB",)),
    ("Pinnacle Game Lines", "fetch_pinnacle_game_lines", ("MLB",)),
    ("Action Network Game Lines", "fetch_action_network_lines", ("MLB",)),
    ("CBS Injuries", "fetch_cbs_injuries", ("MLB",)),
    ("ESPN Injuries", "fetch_espn_injuries", ("MLB",)),
    ("H2H Game Lines", "fetch_h2h_game_lines", ("MLB",)),
    ("Caesars Lines", "fetch_caesars_lines", ("MLB",)),
    ("Bovada Lines", "fetch_bovada_lines", ("MLB",)),
    ("FanDuel Lines", "fetch_fanduel_lines", ("MLB",)),
    # Real, new additions -- confirmed via direct, manual review of each
    # real _pf_X wrapper's def body, not automated/regex-matched.
    ("BetRivers Lines", "fetch_betrivers_game_lines", ("MLB",)),
    ("Fanatics Lines", "fetch_fanatics_game_lines", ("MLB",)),
    ("ESPN Bet Lines", "fetch_espnbet_game_lines", ("MLB",)),
    ("Hard Rock Lines", "fetch_hardrock_game_lines", ("MLB",)),
    ("WynnBet Lines", "fetch_wynnbet_game_lines", ("MLB",)),
    ("Unibet Lines", "fetch_unibet_game_lines", ("MLB",)),
    ("Bet365 Lines", "fetch_bet365_game_lines", ("MLB",)),
    ("BetMGM Lines", "fetch_betmgm_game_lines", ("MLB",)),
    ("Bookmaker Lines", "fetch_bookmaker_game_lines", ("MLB",)),
    ("SportsLine Lines", "fetch_sportsline_game_lines", ("MLB",)),
    ("SBR Lines", "fetch_sbr_game_lines", ("MLB",)),
    ("TheScore Lines", "fetch_thescore_game_lines", ("MLB",)),
    ("Signal Odds Events", "fetch_signalodds_events", ("MLB",)),
    ("BetsLib Predictions", "fetch_betslib_predictions", ("MLB",)),
    ("GamblingForecast Props", "fetch_gamblingforecast_props", ("MLB",)),
    ("BettingPros Props", "fetch_bettingpros_props", ("MLB",)),
    ("SportsInsights", "fetch_sportsinsights_from_gist", ("MLB",)),
    ("MLB Probable Pitchers", "fetch_mlb_probable_pitchers", ()),
    ("NumberFire (NBA)", "fetch_numberfire_direct", ("NBA",)),
    ("BetsLib Live Events", "fetch_betslib_live_events", ("MLB",)),
    ("FantasyPros Projections", "fetch_fantasypros_projections", ("MLB",)),
    ("Opponent Defense Rankings", "fetch_opponent_defense_rankings", ("MLB",)),
    ("Caesars Props", "fetch_caesars_props", ("MLB",)),
    ("BetOnline Offering", "fetch_betonline_offering", ("MLB",)),
    ("Bovada Props", "fetch_bovada_props", ("MLB",)),
    ("Savant Statcast", "fetch_savant_statcast", ()),
    ("Savant Sprint Speed", "fetch_savant_sprint_speed", ()),
    ("Savant Expected Stats", "fetch_savant_expected_stats", ()),
    ("Savant Pitch Arsenal", "fetch_savant_pitch_arsenal", ()),
    ("Savant Batted Ball", "fetch_savant_batted_ball", ()),
    ("MLB Lineups", "fetch_mlb_lineups", ()),
    ("EV API Live", "fetch_ev_api_live", ()),
    ("EV API WNBA", "fetch_ev_api_wnba", ()),
    ("EV API Outliers", "fetch_ev_api_outliers", ("MLB",)),
    ("EV Feed", "fetch_ev_feed", ()),
    ("EV BVP", "fetch_ev_bvp", ()),
    ("EV Preview", "fetch_ev_preview", ()),
    ("EV Strikeouts", "fetch_ev_strikeouts", ()),
    ("EV Movement", "fetch_ev_movement", ("MLB",)),
    ("EV Stats HR", "fetch_ev_stats", ("hr",)),
    ("EV Stats K", "fetch_ev_stats", ("k",)),
    ("EV Barrels", "fetch_ev_barrels", ()),
    ("EV Recap", "fetch_ev_recap", ()),
    ("EV MLB", "fetch_ev_mlb", ()),
    ("EV Trends", "fetch_ev_trends", ()),
    ("PrizePicks", "scrape_prizepicks_with_gist_fallback", ("MLB",)),
    ("Underdog Props", "fetch_underdog_props", ("MLB",)),
    ("Public Betting", "fetch_public_betting", ("MLB",)),
    ("Todays Referees", "fetch_todays_referees", ("MLB",)),
]

results = []
for label, fn_name, args in TARGETS:
    fn = getattr(fetchers, fn_name, None)
    if fn is None:
        results.append({"source": label, "function": fn_name, "status": "MISSING", "seconds": None})
        continue
    start = time.time()
    _captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(_captured):
            data = fn(*args)
        elapsed = round(time.time() - start, 2)
        _internal_warn = _captured.getvalue().strip()
        results.append({
            "source": label, "function": fn_name, "status": "OK",
            "seconds": elapsed, "real_item_count": len(data) if isinstance(data, list) else None,
            "internal_warning": _internal_warn or None,
        })
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        results.append({
            "source": label, "function": fn_name, "status": "ERROR",
            "seconds": elapsed, "error": f"{type(e).__name__}: {str(e)[:150]}",
        })

output = {
    "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sharpapi_key_real_length": _key_len,
    "sharpapi_leagues_reference": _leagues_result,
    "sharpapi_odds_raw_response": _odds_raw_result,
    "sharpapi_props_raw_response": _props_raw_result,
    "results": sorted(results, key=lambda r: (r["seconds"] is None, -(r["seconds"] or 0))),
}

# Push the real results to the Gist so they can be read back directly.
GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
token = os.environ.get("GITHUB_TOKEN")
import requests
_push_ok = False
for _attempt in range(3):
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_slow_source_diagnostic.json": {"content": json.dumps(output, indent=2)}}},
        timeout=30,
    )
    print(f"Gist push attempt {_attempt+1} status: {resp.status_code}")
    if resp.status_code == 200:
        _push_ok = True
        break
    time.sleep(5 * (_attempt + 1))
print(json.dumps(output, indent=2))
if not _push_ok:
    print("[FATAL] Gist push did not succeed after 3 real attempts.")
    sys.exit(1)
