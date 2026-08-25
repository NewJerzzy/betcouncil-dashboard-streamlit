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

# Real, direct probe of the Kambi shared function (feeds BetRivers, Hard
# Rock, WynnBet, Unibet, Fanatics -- all 5 confirmed showing zero real
# items). The wrapper itself silently returns [] on any non-200 status
# or exception with zero logging, so calling the real URL construction
# directly here to see the true raw response.
_kambi_raw_result = None
try:
    from curl_cffi import requests as _cf
    _kambi_session = _cf.Session(impersonate="chrome124")
    _kambi_url = (
        "https://eu-offering-api.kambicdn.com/offering/v2018/rvn"
        "/listView/baseball/mlb.json"
        "?lang=en_US&market=US&client_id=2&channel_id=1&ncids=1"
        "&category=match&useCombined=true"
    )
    _kambi_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://sportsbook.draftkings.com",
        "Referer": "https://sportsbook.draftkings.com/sports",
    }
    _kr = _kambi_session.get(_kambi_url, headers=_kambi_headers, timeout=15)
    _kambi_raw_result = {"status": _kr.status_code, "body": _kr.text[:2000]}
except Exception as e:
    _kambi_raw_result = {"error": f"{type(e).__name__}: {str(e)[:200]}"}

# Real, focused set: the specific sources already suspected tonight (from
# the Replit report + confirmed-slow OddsWrap from earlier this session).
TARGETS = [
    ("OddsWrap", "fetch_oddswrap_props", ("MLB",), False),

    ("ParlayAPI Props", "fetch_parlayapi_props", ("MLB",), False),

    ("ParlayAPI Arbitrage", "fetch_parlayapi_arbitrage", ("MLB",), False),

    ("ParlayAPI EV", "fetch_parlayapi_ev", ("MLB",), False),

    ("SharpAPI Lines", "fetch_sharpapi_lines", ("MLB",), False),

    ("SharpAPI Props", "fetch_sharpapi_props", ("MLB",), False),

    ("Pinnacle Game Lines", "fetch_pinnacle_game_lines", ("MLB",), False),

    ("Action Network Game Lines", "fetch_action_network_lines", ("MLB",), False),

    ("CBS Injuries", "fetch_cbs_injuries", ("MLB",), False),

    ("ESPN Injuries", "fetch_espn_injuries", ("MLB",), False),

    ("H2H Game Lines", "fetch_h2h_game_lines", ("MLB",), False),

    ("Caesars Lines", "fetch_caesars_lines", ("MLB",), False),

    ("Bovada Lines", "fetch_bovada_lines", ("MLB",), False),

    ("FanDuel Lines", "fetch_fanduel_lines", ("MLB",), False),

    # Real, new additions -- confirmed via direct, manual review of each
    # real _pf_X wrapper's def body, not automated/regex-matched.
    ("BetRivers Lines", "fetch_betrivers_game_lines", ("MLB",), False),

    ("Fanatics Lines", "fetch_fanatics_game_lines", ("MLB",), False),

    ("ESPN Bet Lines", "fetch_espnbet_game_lines", ("MLB",), False),

    ("Hard Rock Lines", "fetch_hardrock_game_lines", ("MLB",), False),

    ("WynnBet Lines", "fetch_wynnbet_game_lines", ("MLB",), False),

    ("Unibet Lines", "fetch_unibet_game_lines", ("MLB",), False),

    ("Bet365 Lines", "fetch_bet365_game_lines", ("MLB",), False),

    ("BetMGM Lines", "fetch_betmgm_game_lines", ("MLB",), False),

    ("Bookmaker Lines", "fetch_bookmaker_game_lines", ("MLB",), False),

    ("SportsLine Lines", "fetch_sportsline_game_lines", ("MLB",), False),

    ("SBR Lines", "fetch_sbr_game_lines", ("MLB",), False),

    ("TheScore Lines", "fetch_thescore_game_lines", ("MLB",), False),

    ("Signal Odds Events", "fetch_signalodds_events", ("MLB",), False),

    ("BetsLib Predictions", "fetch_betslib_predictions", ("MLB",), False),

    ("GamblingForecast Props", "fetch_gamblingforecast_props", ("MLB",), False),

    ("BettingPros Props", "fetch_bettingpros_props", ("MLB",), False),

    ("SportsInsights", "fetch_sportsinsights_from_gist", ("MLB",), False),

    ("MLB Probable Pitchers", "fetch_mlb_probable_pitchers", (), False),

    ("NumberFire (NBA)", "fetch_numberfire_direct", ("NBA",), False),

    ("BetsLib Live Events", "fetch_betslib_live_events", ("MLB",), False),

    ("FantasyPros Projections", "fetch_fantasypros_projections", ("MLB",), False),

    ("Opponent Defense Rankings", "fetch_opponent_defense_rankings", ("MLB",), False),

    ("Caesars Props", "fetch_caesars_props", ("MLB",), False),

    ("BetOnline Offering", "fetch_betonline_offering", ("MLB",), False),

    ("Bovada Props", "fetch_bovada_props", ("MLB",), False),

    ("Savant Statcast", "fetch_savant_statcast", (), False),

    ("Savant Sprint Speed", "fetch_savant_sprint_speed", (), False),

    ("Savant Expected Stats", "fetch_savant_expected_stats", (), False),

    ("Savant Pitch Arsenal", "fetch_savant_pitch_arsenal", (), False),

    ("Savant Batted Ball", "fetch_savant_batted_ball", (), False),

    ("MLB Lineups", "fetch_mlb_lineups", (), False),

    ("EV API Live", "fetch_ev_api_live", (), False),

    ("EV API WNBA", "fetch_ev_api_wnba", (), False),

    ("EV API Outliers", "fetch_ev_api_outliers", ("MLB",), False),

    ("EV Feed", "fetch_ev_feed", (), False),

    ("EV BVP", "fetch_ev_bvp", (), False),

    ("EV Preview", "fetch_ev_preview", (), False),

    ("EV Strikeouts", "fetch_ev_strikeouts", (), False),

    ("EV Movement", "fetch_ev_movement", ("MLB",), False),

    ("EV Stats HR", "fetch_ev_stats", ("hr",), False),

    ("EV Stats K", "fetch_ev_stats", ("k",), False),

    ("EV Barrels", "fetch_ev_barrels", (), False),

    ("EV Recap", "fetch_ev_recap", (), False),

    ("EV MLB", "fetch_ev_mlb", (), False),

    ("EV Trends", "fetch_ev_trends", (), False),

    ("PrizePicks", "scrape_prizepicks_with_gist_fallback", ("MLB",), False),
    ("Underdog Props", "fetch_underdog_props", ("MLB",), False),
    ("Public Betting", "fetch_public_betting", ("MLB",), False),
    ("Todays Referees", "fetch_todays_referees", ("MLB",), False),
    # Real, final batch -- the genuinely more complex remainder, confirmed
    # safe via direct, manual review (not automated) of each real wrapper.
    ("Kalshi", "fetch_kalshi_from_gist", ("MLB",), False),
    ("Polymarket", "fetch_polymarket_markets", ("MLB",), False),
    ("Covers", "fetch_covers_from_gist", ("MLB",), True),
    ("OddsPortal", "fetch_oddsportal_from_gist", ("MLB",), True),
    ("Odds API Props", "fetch_odds_api_props", ("MLB",), False),
    ("OddsPAPI Props", "fetch_oddspapi_props", ("MLB",), False),
    ("RotoWire Injuries", "fetch_rotowire_injuries", ("MLB",), False),
    ("DK Pick6 Props", "fetch_pick6_props_from_gist", ("MLB",), True),
    ("Bobby's Bets Picks", "fetch_bobbys_bets_picks", ("mlb",), False),
    ("Bobby's Bets Props", "fetch_bobbys_bets_props_from_gist", ("mlb",), False),
    ("Bobby's Bets Briefing", "fetch_bobbys_bets_briefing", ("mlb",), False),
    ("Bobby's Bets Scoreboard", "fetch_bobbys_bets_scoreboard", ("mlb",), False),
    ("Bobby's Bets Best Prices", "fetch_bobbys_bets_best_prices", ("mlb",), False),
    ("EVBets (Gist)", "fetch_evbets_from_gist", ("MLB",), False),
    ("VSiN Splits (Gist)", "fetch_vsin_splits_from_gist", ("MLB",), False),
    ("BaseballPress (Gist)", "fetch_baseballpress_from_gist", (), False),
    ("Weather (Gist)", "fetch_weather_from_gist", ("MLB",), False),
]

results = []
for label, fn_name, args, is_tuple in TARGETS:
    fn = getattr(fetchers, fn_name, None)
    if fn is None:
        results.append({"source": label, "function": fn_name, "status": "MISSING", "seconds": None})
        continue
    start = time.time()
    _captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(_captured):
            data = fn(*args)
            if is_tuple and isinstance(data, tuple) and len(data) > 0:
                data = data[0]
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
    "kambi_raw_response": _kambi_raw_result,
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
