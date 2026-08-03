# ============================================================
# SESSION_STATE KEY REGISTRY -- check this list before adding a
# new st.session_state[...] key anywhere in app.py or here.
# 2026-07-26: added after a real collision -- a new Kalshi
# pipeline was written to "kalshi_markets", already owned by an
# older, actively-used pipeline with 7 real consumers expecting a
# different shape. That crashed the app and blocked Game Lines
# lock-in as a side effect. Grep this list (or just grep the
# codebase for the literal key string) before reusing a name.
# Auto-generated snapshot, 189 keys in use as of this commit:
# _bankroll_last_saved, _board_paste_results, _board_paste_text, _clv_snap_last_run, _elo_auto_last_run, _kalshi_idx, _ls_source_flags, _pl_last_sport, _poly_idx, action_network_data, all_sports_best, alt_line_upgrades, alt_lines_data, an_props_data, analyzer_picks, analyzer_results, api_panel_results, arb_opportunities, bankroll, baseballpress_lineups, bc_telemetry, bet365_game_lines, betmgm_game_lines, betonline_lines, betonline_offering, betrivers_game_lines, betslib_live_events, betslib_predictions, better_lines_lookup, board_load_count, board_loaded, bookmaker_game_lines, bovada_game_lines, bovada_lines, bovada_props, caesars_game_lines, caesars_props, calibrated_game_thresholds, calibrated_thresholds, cbs_injuries, clv_tracking, covers_consensus, current_slip_id, day_start_br, defense_rankings, depth_chart_changes, dff_player_ids, dff_team_map, dk_pick6_props, dk_salaries, errors, espn_depth_charts, espn_injuries, espnbet_game_lines, ev_api_props, ev_api_updated, ev_auto_refresh_enabled, ev_auto_refresh_ts, ev_barrels_count, ev_barrels_lookup, ev_book_lookup, ev_bvp_count, ev_bvp_lookup, ev_feed_lookup, ev_feed_summary, ev_mlb_count, ev_mlb_lookup, ev_movement_lookup, ev_odds_snapshot, ev_outliers_count, ev_outliers_lookup, ev_preview_count, ev_preview_lookup, ev_recap_data, ev_recap_record, ev_signal_lookup, ev_stats_count, ev_stats_k_count, ev_stats_k_lookup, ev_stats_lookup, ev_strikeouts_count, ev_strikeouts_lookup, ev_trends_hr_per_g_l7, ev_trends_hr_per_g_season, ev_trends_note, ev_trends_signal, fanatics_game_lines, fanduel_game_lines, fanduel_props, fanduel_props_sa, fanduel_props_src, fantasylabs_lineups, fantasypros_proj, fetch_timings, game_analysis, game_line_movement, game_sharp_flags, game_steam_signals, gem_brief_output, gist_batch_start, gist_dirty, gist_last_write, golf_leaderboard, golf_odds, hardrock_game_lines, heritage_game_lines, injuries_combined, kalshi_events_scraped, kalshi_markets, last_good_props, last_sport_loaded, line_deviation_lookup, line_discrepancies, line_movement, line_origins, loss_patterns, mlb_confirmed_lineups, mlb_lineups, mlb_pitchers, mlb_roster_ids, multibook_discrepancies, mybookie_game_lines, nb_comparison, nb_shortlist, nba_advanced_stats, nba_l20_pricer_baseline, nfl_inactives, nfl_live_baselines, nfl_player_db, nfl_practice, nhl_starting_goalies, ocr_raw_text, oddswrap_props, officials_data, opening_lines_lookup, openmeteo_weather, paddypower_lines, parlayapi_arb, parlayapi_ev, parsed_bets, pinnacle_game_lines, pinnacle_props, pl_line, pl_logs, pl_name_display, pl_opp, pl_opp_autofill, pl_sport_used, polymarket_markets, portfolio_metrics, portfolio_selection, power_divergences, pp_source, pp_status, public_betting_data, quality_sorted_board, raw_games_today, rolling_avgs, rw_injuries, savant_arsenal, savant_batted, savant_expected, savant_sprint, savant_xstats, sbr_game_lines, scanbet_drops, scrapeops_exhausted, scraperapi_exhausted, session_start, sharp_alerts, sharpapi_ev_opps, sharpapi_line_drops, sharpapi_lines, sharpapi_props, signalodds_arbitrage, signalodds_events, sportsline_game_lines, steam_moves, thescore_game_lines, ud_props_compare, ump_scorecards, unabated_lines, unibet_game_lines, unified_sharp_board, uploader_key, weather_data, wnba_rolling_avgs, wnba_rolling_avgs_ts, wynnbet_game_lines
# ============================================================

"""
BetCouncil Fetchers — extracted data-fetch and utility functions.
Moved from app.py to keep app.py under 1 MB.
All functions callable from app.py via: from fetchers import *
"""
import os, time, pickle, json, re, csv, io, hashlib
import logging
_logger = logging.getLogger("betcouncil")
import urllib.request
import urllib.parse
try:
    from curl_cffi import requests as cf
except ImportError:
    cf = None
from datetime import date, datetime, timedelta, timezone
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as _Retry
try:
    from config import BOOKMAKER_CF, BOOKMAKER_SESSID
except ImportError:
    BOOKMAKER_CF = BOOKMAKER_SESSID = ""

def _make_retry_session() -> requests.Session:
    """Shared requests.Session with automatic retry.
    Retries up to 2 times with 1-second exponential backoff on transient
    server errors (429, 500, 502, 503, 504) and connection failures.
    Does NOT retry on 4xx client errors (auth, not-found, etc.)."""
    _s = requests.Session()
    _r = _Retry(
        total=2,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
        allowed_methods=False,   # retry any HTTP verb
    )
    _s.mount("https://", HTTPAdapter(max_retries=_r))
    _s.mount("http://",  HTTPAdapter(max_retries=_r))
    return _s

# Module-level retry session — shared across all fetchers.
# requests.Session is thread-safe for concurrent reads (connection pool is
# protected internally), so this is safe inside ThreadPoolExecutor workers.
_http = _make_retry_session()

# Plain Session for proxy calls — no auto-retry so proxy errors surface fast.
_HTTP_DIRECT = requests.Session()

# Supabase EV endpoint (used by _ev_do_refresh / _get_ev_jwt)
SUPABASE_URL  = "https://nkdhryqpiulrepmphwmt.supabase.co"
SUPABASE_ANON = "sb_publishable_mMniM5v3auOHfF72hlVL_w_LUNlh3yt"
_EV_TOKEN_CACHE: dict = {"access_token": None, "expires_at": 0}


try:
    from config import (
        CACHE_DIR, HEADERS, MLB_PLAYER_IDS,
        BETONLINE_BASE, BETONLINE_HEADERS, BETONLINE_MULTI_LEAGUE,
        NFL_OUTDOOR_STADIUMS, NFL_DIVISIONS, GOLF_TOURNAMENT_MAP,
        _SOCCER_LEAGUE_BASELINES, _SOCCER_LEAGUE_KEYS,
        _TENNIS_SURFACE_BASELINES_BO3, _TENNIS_SURFACE_BASELINES_BO5,
        _ATP_GRAND_SLAMS, _SLAM_SURFACE,
        _UFC_WEIGHTCLASS_BASELINES, _UFC_ROUND_DEFAULT, _UFC_CHAMPIONSHIP_ROUNDS,
        DFF_HEADERS, DFF_SPORT_MAP, DFF_TEAM_MAP, DFF_METRIC_MAP,
        ODDS_API_BASE, ODDS_API_KEY, ODDSPAPI_KEY, REQUEST_TIMEOUT,
        SCRAPEOPS_KEY, GITHUB_TOKEN, GITHUB_GIST_ID,
        ACTION_NETWORK_SPORT_MAP, ACTION_NETWORK_LEAGUE_IDS,
        ACTION_NETWORK_PROP_TYPE_MAP, ODDS_API_SPORT_MAP,
        PLAYER_AVERAGES_SOCCER, PLAYER_AVERAGES_UFC,
        DEFAULT_AVERAGES, STAT_NORMALIZE,
        BOVADA_BASE, BOVADA_SPORT_MAP, BOVADA_HEADERS, BOVADA_PATH,
        # ── Additional constants used in fetchers but previously missing from import ──
        BDL_API_KEY, BDL_PLAYER_IDS,
        ESPN_ATHLETE_IDS, ESPN_SLUG_MAP,
        TEAM_ABBREV_TO_FRAGMENT as _TEAM_ABBREV_TO_FRAGMENT_BY_SPORT,
        FL_HEADERS, FL_SPORT_MAP,
        KALSHI_SPORT_SERIES, MLB_STADIUM_COORDS,
        NHL_PLAYER_IDS,
        MLB_PITCHER_ERA, MLB_PITCHER_FIP, LEAGUE_AVG_ERA,
        CBS_SPORT_MAP,
        ACTION_NETWORK_BASE,
        ACTION_NETWORK_BOOK_IDS,
        BETONLINE_PATH,
        BETONLINE_PROP_PRICE_URL,
        BETONLINE_PROP_SPORT_CODES,
        BETONLINE_SPORT_MAP,
        CLV_PATH,
        COVERS_PATH,
        ESPN_CORE_BASE,
        ESPN_CORE_SPORT_MAP,
        FANDUEL_COMPETITION_IDS,
        FANTASYLABS_PATH,
        FIRECRAWL_KEY,
        GOLF_PATH,
        KALSHI_PATH,
        NFL_INACTIVES_PATH,
        NFL_PRACTICE_PATH,
        ODDSWRAP_SPORT_MAP,
        ODDS_API_BOOKS_GAMES, ODDS_API_BOOKS_PROPS,
        PARLAYSAVANT_MLB_PROP_MAP,
        PARLAY_API_BASE,
        PARLAY_API_KEY,
        PINNACLE_LINES_PATH,
        POLYMARKET_PATH,
        ROLLING_DEFENSE_CACHE_HOURS,
        SCRAPERAPI_KEY,
        API_BUDGETS, GIST_API, SCRAPEDO_KEY,
        PADDYPOWER_BASE, PADDYPOWER_PATH, PADDYPOWER_SPORT_MAP, PADDYPOWER_HEADERS,
        # ── Fixed 2026-07-11: were referenced in fetch functions below but
        # never imported, causing guaranteed NameErrors (100% error rate on
        # fetch_odds_api_props, fetch_betmgm_game_lines, fetch_sharpapi_lines,
        # fetch_sharpapi_props, fetch_fanduel_props_sharpapi, and would have
        # broken NFL prep via get_nfl_player_baseline / fetch_nfl_full_player_database) ──
        ODDS_API_PROP_MARKETS, ODDS_API_STAT_MAP,
        BETMGM_COOKIE, BETMGM_STATE, BETMGM_SPORT_MAP, BETMGM_WIDGET_MAP,
        SHARPAPI_KEY,
        NFL_POSITION_BASELINES, NFL_STAT_NORMALIZE_MAP, NFL_TEAM_ABBR_MAP,
    )
except ImportError:
    CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    MLB_PLAYER_IDS = {}
    # Stubs for the 9 previously-missing imports
    BDL_API_KEY = ""
    BDL_PLAYER_IDS = {}
    ESPN_ATHLETE_IDS = {}
    ESPN_SLUG_MAP = {}
    FL_HEADERS = {}
    FL_SPORT_MAP = {}
    KALSHI_SPORT_SERIES = {}
    MLB_STADIUM_COORDS = {}
    NHL_PLAYER_IDS = {}
    MLB_PITCHER_ERA = {}
    MLB_PITCHER_FIP = {}
    LEAGUE_AVG_ERA = 4.25
    ACTION_NETWORK_BASE = "https://api.actionnetwork.com/web/v2/scoreboard/publicbetting"
    ACTION_NETWORK_BOOK_IDS = "15,30,4727,4795,79,2988,69,68,75,123,71"
    ACTION_NETWORK_SPORT_MAP = {"NBA":"nba","MLB":"mlb","NHL":"nhl","NFL":"nfl","WNBA":"wnba"}
    ACTION_NETWORK_LEAGUE_IDS = {"NFL":1,"MLB":2,"NHL":3,"NBA":4,"WNBA":5}
    ACTION_NETWORK_PROP_TYPE_MAP = {}
    BETONLINE_PATH = ""
    BETONLINE_PROP_PRICE_URL = ""
    BETONLINE_PROP_SPORT_CODES = 0
    BETONLINE_SPORT_MAP = {}
    CLV_PATH = ""
    COVERS_PATH = ""
    ESPN_CORE_BASE = ""
    ESPN_CORE_SPORT_MAP = {}
    FANDUEL_COMPETITION_IDS = {}
    FANTASYLABS_PATH = ""
    FIRECRAWL_KEY = ""
    GOLF_PATH = ""
    KALSHI_PATH = ""
    NFL_INACTIVES_PATH = ""
    NFL_PRACTICE_PATH = ""
    ODDSWRAP_SPORT_MAP = {}
    ODDS_API_BOOKS_GAMES = 0
    ODDS_API_BOOKS_PROPS = "bovada,mybookieag,draftkings,fanduel,betmgm,caesars,us_ex,circa_sports,betonlineag"
    PARLAYSAVANT_MLB_PROP_MAP = {}
    PARLAY_API_BASE = ""
    PARLAY_API_KEY = ""
    PINNACLE_LINES_PATH = ""
    POLYMARKET_PATH = ""
    ROLLING_DEFENSE_CACHE_HOURS = 0
    SCRAPERAPI_KEY = ""
    API_BUDGETS = {}
    GIST_API = "https://api.github.com/gists"
    SCRAPEDO_KEY = ""
    CBS_SPORT_MAP = {}
    PADDYPOWER_BASE = "https://www.paddypower.com"
    PADDYPOWER_PATH = os.path.join(os.path.dirname(__file__), ".cache", "paddypower_lines.json")
    PADDYPOWER_SPORT_MAP = {
        "NBA": "basketball", "WNBA": "basketball", "NFL": "american-football",
        "NHL": "ice-hockey", "MLB": "baseball",
    }
    PADDYPOWER_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-GB,en;q=0.9"}
    ODDS_API_PROP_MARKETS = {}
    ODDS_API_STAT_MAP = {}
    NFL_POSITION_BASELINES = {}
    NFL_STAT_NORMALIZE_MAP = {}
    NFL_TEAM_ABBR_MAP = {}
    BOVADA_BASE = "https://www.bovada.lv/services/sports/event/coupon/events/A/description"
    BOVADA_PATH = os.path.join(os.path.dirname(__file__), ".cache", "bovada_lines.json")
    BOVADA_SPORT_MAP = {
        "NBA": "basketball/nba", "NFL": "football/nfl",
        "MLB": "baseball/mlb",   "NHL": "hockey/nhl", "WNBA": "basketball/wnba",
    }
    BOVADA_HEADERS = {
        "Accept": "application/json", "Origin": "https://www.bovada.lv",
        "Referer": "https://www.bovada.lv/sports",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-channel": "desktop", "x-sport-context": "BASE",
        "cookie": "LANG=en; Device-Type=Desktop|false; odds_format=AMERICAN;",
    }
    # New sources
    SHARPAPI_KEY   = ""
    SHARPAPI_BASE  = "https://api.sharpapi.io/api/v1"
    BETMGM_COOKIE  = ""
    BETMGM_STATE   = "az"
    BETMGM_SPORT_MAP = {}
    BETMGM_WIDGET_MAP = {}
    CAESARS_COMP_IDS = {}
    CAESARS_PROP_TABS = {}
    GITHUB_TOKEN   = ""
    GITHUB_GIST_ID = ""
    NFL_POSITION_BASELINES = {}
    NFL_STAT_NORMALIZE_MAP = {}
    NFL_TEAM_ABBR_MAP = {}
    NFL_PROP_MARKETS = []

# ── OddsWrap optional dependency ────────────────────────────────────────────
try:
    from oddswrap import OddsClient
    ODDSWRAP_AVAILABLE = True
except ImportError:
    ODDSWRAP_AVAILABLE = False
    class OddsClient:  # noqa: F811
        """Stub when oddswrap is not installed."""
        def __init__(self, **kwargs): pass
        def get_markets(self, *a, **kw): return []
        def get_lines(self, *a, **kw): return []

try:
    from bc_utils import normalize_name, safe_float, load_json_data, save_json_data, _load_cache, _save_cache, is_date_valid_for_today, compute_std_dev
except ImportError:
    def normalize_name(n): return n.strip().lower() if n else ""
    def safe_float(v, d=0.0):
        try: return float(v)
        except: return d

os.makedirs(CACHE_DIR, exist_ok=True)


def _safe_load_pkl(path):
    """Load a pickle cache file; returns None on corruption, EOFError, or any
    unpickling error so the caller falls through to a fresh network fetch.
    Without this guard a single corrupt .pkl (partial write, disk-full, etc.)
    would crash the entire board load.
    """
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _safe_save_pkl(path, obj):
    """Save obj to a pickle file, silently ignoring errors."""
    try:
        with open(path, "wb") as f:
            pickle.dump(obj, f)
    except Exception:
        pass

def fetch_golf_leaderboard():
    """
    Fetch current PGA Tour leaderboard from ESPN.
    Returns list of {name, position, score, today, thru, country}
    """
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard"
        r = _http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        players = []
        # ESPN golf scoreboard structure
        events = data.get("events", [])
        for event in events[:1]:  # current tournament only
            tournament_name = event.get("name","")
            competitions = event.get("competitions", [])
            for comp in competitions[:1]:
                for competitor in comp.get("competitors", []):
                    athlete = competitor.get("athlete", {})
                    stats   = competitor.get("statistics", [])
                    name    = athlete.get("displayName","")
                    pos     = competitor.get("status", {}).get("position", {}).get("displayName","")
                    score   = competitor.get("score","")
                    country = athlete.get("flag", {}).get("alt","")
                    # Get score details from statistics
                    today_score = ""
                    thru        = ""
                    for stat in stats:
                        if stat.get("name") == "today":
                            today_score = stat.get("displayValue","")
                        elif stat.get("name") == "thru":
                            thru = stat.get("displayValue","")
                    if name:
                        players.append({
                            "name":       name,
                            "position":   pos,
                            "total":      score,
                            "today":      today_score,
                            "thru":       thru,
                            "country":    country,
                            "tournament": tournament_name,
                        })
        if players:
            save_json_data(GOLF_PATH, {"leaderboard": players, "fetched": datetime.now().strftime("%H:%M")})
        return players
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        return load_json_data(GOLF_PATH, {}).get("leaderboard", [])

def fetch_golf_odds(tournament_key="default"):
    """
    Fetch golf player odds from OddsAPI.
    Returns player odds for win / top 5 / top 10 / top 20.
    Used to:
      1. Show market-implied win probability per player
      2. Compare vs model prediction for edge
      3. Support golf prop recommendations
    """
    if not ODDS_API_KEY:
        return {}
    sport_key = GOLF_TOURNAMENT_MAP.get(tournament_key, GOLF_TOURNAMENT_MAP["default"])
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey":      ODDS_API_KEY,
            "regions":     "us",
            "markets":     "outrights",
            "oddsFormat":  "american",
            "bookmakers":  "draftkings,fanduel,betmgm,pinnacle",
        }
        r = _http.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return {}
        events = r.json()
        players = {}
        for event in events[:1]:
            for bm in event.get("bookmakers",[])[:2]:
                for mkt in bm.get("markets",[]):
                    if mkt.get("key") != "outrights":
                        continue
                    for outcome in mkt.get("outcomes",[]):
                        name  = outcome.get("name","")
                        price = outcome.get("price", 0)
                        if name and price:
                            # Convert American odds to implied probability
                            if price > 0:
                                impl_prob = 100 / (price + 100)
                            else:
                                impl_prob = abs(price) / (abs(price) + 100)
                            if name not in players or impl_prob > players[name].get("implied_prob",0):
                                players[name] = {
                                    "name":         name,
                                    "odds":         price,
                                    "implied_prob": round(impl_prob, 4),
                                    "book":         bm.get("key",""),
                                }
        return players
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        return {}

def _fetch_dff_propstats_live(player_id, sport, metric, line,
                              team="", opponent="", home=False):
    """DEAD: dailyfantasyfuel.com is Cloudflare-blocked; endpoint URL unverified."""
    return {}
def fetch_dff_propstats(player_id, sport, metric, line, team="",
                        opponent="", home=False, cache_hours=6):
    """DEAD: dailyfantasyfuel.com is Cloudflare-blocked; endpoint URL unverified."""
    return {}
def fetch_bovada_lines(sport="NBA"):
    """
    Fetch Bovada game lines — moneyline, runline/spread, total.
    No authentication required. Confirmed endpoint:
      https://www.bovada.lv/services/sports/event/coupon/events/A/description/{sport_path}

    Key fix (2024-06): Bovada returns DUPLICATE market keys inside the
    "Game Lines" displayGroup (full-game + alt/first-half lines share key
    names like 2W-12, 2W-HCAP, 2W-OU).  The FIRST occurrence is always the
    standard full-game line; subsequent ones are alternates.  We now break
    after the first capture for each key so we never serve first-half or
    alternate-runline data as the main line.

    Returns list of:
      {matchup, home, away, home_ml, away_ml,
       spread, spread_odds, total, over_odds, under_odds,
       start_time, sport, link, event_id}

    On failure: falls back to last cached data (BOVADA_PATH).

    Early-exit / error guards:
      - unsupported sport → silent []
      - HTTP non-200      → st.warning + cached fallback
      - empty response    → cached fallback
      - exception         → logged + cached fallback
    """
    sport_path = BOVADA_SPORT_MAP.get(sport)
    if not sport_path:
        return []

    url = f"{BOVADA_BASE}/{sport_path}"

    try:
        r = _http.get(
            url,
            headers=BOVADA_HEADERS,
            params={"lang": "en", "eventsLimit": 50, "preMatchOnly": "true"},
            timeout=12,
        )
        if r.status_code != 200:
            st.warning(
                f"⚠️ Bovada: HTTP {r.status_code} from lines endpoint — "
                "using last cached data."
            )
            return load_json_data(BOVADA_PATH, [])

        raw = r.json()
        if not isinstance(raw, list) or not raw:
            return load_json_data(BOVADA_PATH, [])

        games = []
        for section in raw:
            for event in section.get("events", []):
                if event.get("type") != "GAMEEVENT":
                    continue
                if event.get("live"):
                    continue  # skip in-play events

                competitors = event.get("competitors", [])
                home_team   = next((c["name"] for c in competitors if c.get("home")), "")
                away_team   = next((c["name"] for c in competitors if not c.get("home")), "")
                if not home_team or not away_team:
                    continue

                game_lines_grp = next(
                    (g for g in event.get("displayGroups", [])
                     if g.get("description") == "Game Lines"),
                    None,
                )
                if not game_lines_grp:
                    continue

                ml_home = ml_away = None
                spread = spread_home = spread_odds = None
                total = over_odds = under_odds = None

                # ── BUG FIX: Bovada duplicates market keys inside the same
                # displayGroup (standard full-game first, then alternates).
                # Track captured keys and skip duplicates — first match wins.
                captured = set()

                for mkt in game_lines_grp.get("markets", []):
                    key = mkt.get("key", "")
                    if key in captured:
                        continue  # skip alternate / first-half duplicate

                    outcomes = mkt.get("outcomes", [])

                    if key == "2W-12":      # Moneyline
                        for out in outcomes:
                            price = out.get("price", {})
                            if out.get("type") == "H":
                                ml_home = price.get("american", "")
                            elif out.get("type") == "A":
                                ml_away = price.get("american", "")
                        captured.add(key)

                    elif key == "2W-HCAP":  # Runline / Spread
                        for out in outcomes:
                            price = out.get("price", {})
                            if out.get("type") == "H":
                                spread      = price.get("handicap", "")
                                spread_odds = price.get("american", "")
                        captured.add(key)

                    elif key == "2W-OU":    # Total
                        for out in outcomes:
                            price = out.get("price", {})
                            if out.get("type") == "O":
                                total     = price.get("handicap", "")
                                over_odds = price.get("american", "")
                            elif out.get("type") == "U":
                                under_odds = price.get("american", "")
                        captured.add(key)

                    # Stop early once all three markets captured
                    if len(captured) == 3:
                        break

                games.append({
                    "matchup":     f"{away_team} @ {home_team}",
                    "home":        home_team,
                    "away":        away_team,
                    "home_ml":     ml_home,
                    "away_ml":     ml_away,
                    "spread":      spread,
                    "spread_odds": spread_odds,
                    "total":       total,
                    "over_odds":   over_odds,
                    "under_odds":  under_odds,
                    "start_time":  event.get("startTime", 0),
                    "sport":       sport,
                    "link":        event.get("link", ""),
                    "event_id":    event.get("id", ""),
                })

        if games:
            save_json_data(BOVADA_PATH, games)
        return games or load_json_data(BOVADA_PATH, [])

    except Exception as _e:
        print(f"[WARN] Bovada ({sport}): {type(_e).__name__}: {_e}")
        return load_json_data(BOVADA_PATH, [])


def _fetch_betonline_one_league(sport_path, league_path, sport):
    """Single-league BetOnline game-lines fetch — the core logic extracted
    so fetch_betonline_lines() can call this once for normal sports or
    multiple times (merged) for sports like Tennis that span more than one
    BetOnline league."""
    sport_cap = sport_path.capitalize()
    payload = {
        "Sport": sport_path, "League": league_path, "ScheduleText": None,
        "filterTime": 0, "type": "prematch",
        "sport": sport_cap, "league": league_path,
    }

    try:
        r = _http.post(BETONLINE_BASE, headers=BETONLINE_HEADERS, json=payload, timeout=12)
        if r.status_code != 200:
            return []

        data = r.json()
        offering = (data or {}).get("GameOffering", {}) or {}
        games_desc = offering.get("GamesDescription", []) or []
        if not games_desc:
            return []

        def _ml(line_block):
            v = ((line_block or {}).get("MoneyLine", {}) or {}).get("Line")
            return v if v not in (None, 0) else None

        def _spread(line_block):
            sp = (line_block or {}).get("SpreadLine", {}) or {}
            pt, ln = sp.get("Point"), sp.get("Line")
            if pt in (None, 0) and ln in (None, 0):
                return None, None
            return pt, ln

        games = []
        for gd in games_desc:
            g = gd.get("Game", {}) or {}
            if not g:
                continue
            home_team = g.get("HomeTeam", "")
            away_team = g.get("AwayTeam", "")
            if not home_team or not away_team:
                continue

            away_line = g.get("AwayLine", {})
            home_line = g.get("HomeLine", {})
            total_block = (g.get("TotalLine", {}) or {}).get("TotalLine", {}) or {}
            spread_point, spread_odds = _spread(home_line)

            games.append({
                "matchup":     f"{away_team} @ {home_team}",
                "home":        home_team,
                "away":        away_team,
                "home_ml":     _ml(home_line),
                "away_ml":     _ml(away_line),
                "spread":      spread_point,
                "spread_odds": spread_odds,
                "total":       total_block.get("Point"),
                "over_odds":   (total_block.get("Over", {}) or {}).get("Line"),
                "under_odds":  (total_block.get("Under", {}) or {}).get("Line"),
                "start_time":  g.get("WagerCutOff", ""),
                "sport":       sport,
                "source":      "BetOnline",
                "game_id":     g.get("GameId"),
            })
        return games

    except Exception as e:
        return []

def fetch_betonline_lines(sport="NBA"):
    """
    Fetch BetOnline game lines — ML, spread, total — for every game in a
    league, one call (or merged across leagues for Tennis). No auth required.

    Returns list of dicts in the same shape as fetch_bovada_lines():
      {matchup, home, away, home_ml, away_ml,
       spread, spread_odds, total, over_odds, under_odds,
       start_time, sport, source}
    """
    if sport in BETONLINE_MULTI_LEAGUE:
        games = []
        for sport_path, league_path in BETONLINE_MULTI_LEAGUE[sport]:
            games.extend(_fetch_betonline_one_league(sport_path, league_path, sport))
    else:
        sport_path, league_path = BETONLINE_SPORT_MAP.get(sport, ("basketball", "nba"))
        games = _fetch_betonline_one_league(sport_path, league_path, sport)

    if games:
        save_json_data(BETONLINE_PATH, games)
    return games or load_json_data(BETONLINE_PATH, [])

# ── MyBookie sport configuration ─────────────────────────────────────────
# sport/league params mirror mybookie_scraper.py (confirmed against the
# engine.mybookie.ag/sports_api/leagues-lines endpoint discovered via DevTools).
_MB_SPORT_CONFIG = {
    "NBA":  {"sport": "basketball", "league": "nba",  "path": "basketball/nba"},
    "MLB":  {"sport": "baseball",   "league": "mlb",  "path": "baseball/mlb"},
    "NFL":  {"sport": "football",   "league": "nfl",  "path": "football/nfl"},
    "NHL":  {"sport": "hockey",     "league": "nhl",  "path": "hockey/nhl"},
    "WNBA": {"sport": "basketball", "league": "wnba", "path": "basketball/wnba"},
}


def _mb_fmt_ml(val):
    """Format a raw MyBookie money-line value as a signed string."""
    if val is None:
        return "N/A"
    try:
        n = int(float(val))
        return f"+{n}" if n > 0 else str(n)
    except (TypeError, ValueError):
        return str(val) if str(val).strip() else "N/A"


def _mb_extract_game(item: dict, sport: str):
    """
    Convert one raw leagues-lines game item into a fetch_game_lines()-compatible
    dict, or return None if the item lacks enough data to be useful.

    Field-name variants tried reflect both confirmed keys from mybookie_scraper.py
    (gameID, date, name/description/teams) and the standard naming conventions of
    DigitalSportsTech (the odds-data backend MyBookie uses under the hood).
    Without a captured real response the parser deliberately casts a wide net.
    """
    # ── Team names ─────────────────────────────────────────────────────────
    def _s(d, *keys):
        for k in keys:
            v = d.get(k)
            if v and str(v).strip():
                return str(v).strip()
        return ""

    home = _s(item, "homeTeam", "home_team", "HomeTeam", "homeName",
               "home", "team1")
    away = _s(item, "awayTeam", "away_team", "AwayTeam", "awayName",
               "away", "team2")

    if not home or not away:
        # Try composite name fields: "AWAY @ HOME", "HOME vs AWAY", etc.
        raw_name = _s(item, "name", "description", "teams", "matchup",
                      "event", "title", "gameName")
        for sep in (" @ ", " at ", " vs ", " v ", " VS "):
            if sep in raw_name:
                parts = raw_name.split(sep, 1)
                away, home = parts[0].strip(), parts[1].strip()
                break

    if not home or not away:
        return None   # not enough data to build a matchup

    # ── Money lines ─────────────────────────────────────────────────────────
    # Nested home/away dicts are also common in DST responses.
    home_node = item.get("home") if isinstance(item.get("home"), dict) else {}
    away_node = item.get("away") if isinstance(item.get("away"), dict) else {}

    home_ml = (item.get("homeML") or item.get("home_ml") or item.get("homeMl") or
               item.get("homeMoneyLine") or item.get("home_moneyline") or
               item.get("hml") or item.get("homeOdds") or item.get("homePrice") or
               home_node.get("ml") or home_node.get("moneyLine") or
               home_node.get("price") or home_node.get("odds"))
    away_ml = (item.get("awayML") or item.get("away_ml") or item.get("awayMl") or
               item.get("awayMoneyLine") or item.get("away_moneyline") or
               item.get("aml") or item.get("awayOdds") or item.get("awayPrice") or
               away_node.get("ml") or away_node.get("moneyLine") or
               away_node.get("price") or away_node.get("odds"))

    # ── Spread ──────────────────────────────────────────────────────────────
    spread_pt = (item.get("homeSpread") or item.get("home_spread") or
                 item.get("spread") or item.get("pointSpread") or
                 item.get("handicap") or item.get("spreadPoint") or
                 home_node.get("spread") or home_node.get("handicap") or
                 home_node.get("spreadPoint"))
    spread_odds = (item.get("homeSpreadOdds") or item.get("spreadOdds") or
                   item.get("spreadLine") or home_node.get("spreadOdds"))

    spread_str = "N/A"
    if spread_pt is not None:
        try:
            sp = float(spread_pt)
            spread_str = f"{home} {sp:+.1f}"
        except (TypeError, ValueError):
            spread_str = str(spread_pt)

    # ── Total ────────────────────────────────────────────────────────────────
    total_raw = (item.get("total") or item.get("overUnder") or
                 item.get("over_under") or item.get("gameTotal") or
                 item.get("totalPoints") or item.get("totalRuns") or
                 item.get("totalGoals") or item.get("ou") or item.get("OU"))
    if isinstance(total_raw, dict):
        total_raw = (total_raw.get("point") or total_raw.get("value") or
                     total_raw.get("line"))
    try:
        total = float(total_raw) if total_raw is not None else "N/A"
    except (TypeError, ValueError):
        total = "N/A"

    return {
        "Matchup":     f"{away} @ {home}",
        "Status":      "Scheduled",
        "Home ML":     _mb_fmt_ml(home_ml),
        "Away ML":     _mb_fmt_ml(away_ml),
        "Spread":      spread_str,
        "Total":       total,
        "Odds Source": "MyBookie",
        "Sport":       sport,
    }


def _mb_unwrap(data: object) -> list:
    """
    Unwrap a MyBookie API response to a flat list of raw game items.
    Handles:  bare list, {"data":[…]}, {"games":[…]}, {"events":[…]},
              {"leagues":[{"games":[…]}]}, {"results":[…]}.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "games", "events", "results", "items", "offerings"):
        val = data.get(key)
        if isinstance(val, list) and val:
            return val
    # Nested: {"leagues": [{"games": [...]}]}
    for league in (data.get("leagues") or []):
        for key in ("games", "events", "data"):
            val = league.get(key) if isinstance(league, dict) else []
            if isinstance(val, list) and val:
                return val
    return []


def fetch_mybookie_lines(sport="NBA"):
    """
    MyBookie game lines (ML / spread / total) via headed Playwright Chromium.

    WHY PLAYWRIGHT: engine.mybookie.ag/sports_api/* is behind Cloudflare bot
    detection (CF-Clearance fingerprinting, and on some paths Turnstile).
    Direct curl_cffi requests without a valid cf_clearance cookie return a
    403 / JS-challenge page.  A real headed browser solves the CF challenge
    natively, setting cf_clearance in the browser's cookie jar.  We then:
      1. Intercept XHR responses from engine.mybookie.ag as the page loads
         (the schedule page fires leagues-lines automatically for the sport's
         default date view).
      2. If the intercept yields nothing (CF challenge page, no JSON responses
         from the engine domain), fall back to page.request.get() — which
         reuses the browser's now-cleared cookies — to call leagues-lines
         directly.

    Pattern matches betonline_props_scraper.py:
      - headed Chromium, headless=False (better CF bypass)
      - --disable-blink-features=AutomationControlled
      - navigator.webdriver = undefined via add_init_script
      - page.on("response", …) to intercept engine.mybookie.ag XHR
      - page.request.get() authenticated direct call as fallback

    Sport → API params from mybookie_scraper.py (engine.mybookie.ag discovery):
      NBA:  sport=basketball league=nba   path=basketball/nba
      MLB:  sport=baseball   league=mlb   path=baseball/mlb
      NFL:  sport=football   league=nfl   path=football/nfl
      NHL:  sport=hockey     league=nhl   path=hockey/nhl
      WNBA: sport=basketball league=wnba  path=basketball/wnba

    Cache: 30 minutes (Playwright launch ≈ 5-10s).
    Headless: defaults to headed. Set env MYBOOKIE_HEADLESS=1 to force
    headless; also auto-falls back to headless=True if headed launch fails.

    Returns list of game dicts (same shape as fetch_game_lines()):
        [{"Matchup","Status","Home ML","Away ML","Spread","Total",
          "Odds Source":"MyBookie","Sport"}]
    Returns [] on playwright ImportError, unsupported sport, or any error.
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as _PWTimeout
    except ImportError:
        log_error_to_session(
            "fetch_mybookie_lines",
            "playwright not installed — pip install playwright && playwright install chromium",
            "warning",
        )
        return []

    cfg = _MB_SPORT_CONFIG.get(sport.upper())
    if not cfg:
        return []

    cache_path = os.path.join(CACHE_DIR, f"mybookie_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 30:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    raw_items: list = []

    def _on_response(response):
        url = response.url
        if "engine.mybookie.ag" not in url and "mybookie.ag/sports_api" not in url:
            return
        if response.status != 200:
            return
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            data = response.json()
        except Exception:
            return
        items = _mb_unwrap(data)
        if items:
            raw_items.extend(items)

    games = []
    try:
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ]
            headless = bool(os.environ.get("MYBOOKIE_HEADLESS", ""))
            try:
                browser = pw.chromium.launch(headless=headless, args=launch_args)
            except Exception:
                browser = pw.chromium.launch(headless=True, args=launch_args)

            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 720},
            )
            # Mask automation signals that Cloudflare inspects
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = ctx.new_page()
            page.on("response", _on_response)

            target_url = f"https://www.mybookie.ag/sportsbook/{cfg['path']}"
            try:
                # domcontentloaded is faster than networkidle and still lets
                # the sport schedule XHR fire before we start waiting.
                page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
            except _PWTimeout:
                pass
            except Exception:
                pass

            # Dwell: give the page time to load the schedule + fire leagues-lines XHR
            time.sleep(8)

            # ── Fallback: direct authenticated call from within the browser ───
            # If the XHR intercept caught nothing (CF challenge consumed the full
            # page load, or the schedule rendered from a cached hydration bundle
            # without a fresh XHR) we call the API endpoint directly.
            # page.request.get() uses the browser context's cookies — including
            # any cf_clearance set by the challenge page — so the request is
            # authenticated.
            if not raw_items:
                _api_hdrs = {
                    "Accept":          "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer":         target_url,
                    "Origin":          "https://www.mybookie.ag",
                }
                for _endpoint in (
                    "leagues-lines",
                    "leagues-lines-pregame",
                    "todays-lines",
                    "daily-lines",
                ):
                    try:
                        _r = page.request.get(
                            f"https://engine.mybookie.ag/sports_api/{_endpoint}",
                            params={"sport": cfg["sport"], "league": cfg["league"]},
                            headers=_api_hdrs,
                            timeout=12_000,
                        )
                        if _r.ok:
                            _data = _r.json()
                            _items = _mb_unwrap(_data)
                            if _items:
                                raw_items.extend(_items)
                                break  # stop at first endpoint that returns data
                    except Exception:
                        continue

            ctx.close()
            browser.close()

        games = [
            g for g in (
                _mb_extract_game(item, sport) for item in raw_items
            )
            if g is not None
        ]

    except Exception as _e:
        log_error_to_session("fetch_mybookie_lines", str(_e)[:150], "warning")
        return []

    if games:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(games, f)
        except OSError:
            pass

    return games

def fetch_betonline_prop_price(fixture_id, key, sport="MLB",
                                market_id=None, market_name=None, market_label_id=None,
                                selection_id=None, selection_name=None, entity_id=None,
                                global_id_long=None, global_id_short=None):
    """
    Price a single BetOnline player-prop selection via the sportcast widget.

    All of fixture_id/key/market_id/market_label_id/selection_id/entity_id/
    global_id_long/global_id_short must come from a live capture for now —
    see the unresolved items in the section header above. This function
    only handles the confirmed last-mile call (selection IDs in -> price
    out); it does not discover those IDs itself.

    Returns dict with american_price / decimal_price / raw, or None on
    failure (null MarketIdentifier / "Infinity" price counts as failure —
    that's the broken-request signature this whole feature was blocked on).
    """
    sport_code = BETONLINE_PROP_SPORT_CODES.get(sport)
    if sport_code is None or not all([fixture_id, key, market_id, selection_id]):
        return None

    payload = {
        "FixtureId": fixture_id,
        "Key": key,
        "Sport": sport_code,
        "MarketDetails": [{
            "MarketId": market_id,
            "MarketName": market_name,
            "MarketLabelId": market_label_id,
            "BetSelections": [{
                "Id": selection_id,
                "Selection": selection_name,
                "EntityId": entity_id,
                "GlobalIdLong": global_id_long,
                "GlobalIdShort": global_id_short,
            }],
        }],
        "ReturnBetSlip": False,
        "ReturnValidationMatrix": False,
        "Culture": "en-GB",
        "ReturnAllTranslations": False,
        "ReturnMarkets": False,
    }

    sport_id_header = {"MLB": "Baseball"}.get(sport, sport)
    # Headers corrected 2026-06-21 against a real captured browser request —
    # the previous version returned the documented broken signature (Price:
    # "Infinity", MarketIdentifier: null) even when replaying a genuinely
    # real, human-clicked request's exact body, which ruled out bot
    # detection as the cause and pointed at the request itself. Comparison
    # found: "Origin" was being sent here but is NOT present in the real
    # browser's request (likely flagged as inconsistent for what should be
    # a same-origin call); "http-loader" and "request-id" were both present
    # in the real request and completely absent here. request-id looks like
    # an Application Insights-style trace ID (format "|<8char>.<6char>") —
    # exact generation algorithm unconfirmed, but a similarly-shaped random
    # value is a reasonable approximation worth testing against omitting it
    # entirely, which is the known-broken state.
    import random as _bo_random
    import string as _bo_string
    _bo_op_id = ''.join(_bo_random.choices(_bo_string.ascii_letters + _bo_string.digits, k=8))
    _bo_req_id = ''.join(_bo_random.choices(_bo_string.ascii_letters + _bo_string.digits, k=6))
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": f"https://bl.widget-prod.sportcast.app/markets?key={key}&fixtureId={fixture_id}&odds=AmericanPrice&brand=betonline",
        "http-loader": "false",
        "request-id": f"|{_bo_op_id}.{_bo_req_id}",
        "sc-fixtureid": str(fixture_id),
        "sc-sportid": sport_id_header,
        "User-Agent": BETONLINE_HEADERS["User-Agent"],
    }

    try:
        r = _http.post(BETONLINE_PROP_PRICE_URL, headers=headers, json=payload, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        pl = (data or {}).get("PayLoad", {}) or {}
        price = pl.get("Price")
        if price in (None, "Infinity", 0):
            return None
        details = pl.get("PriceDetails", {}) or {}
        return {
            "american_price": details.get("AmericanPrice"),
            "decimal_price":  details.get("DecimalPriceRounded"),
            "raw":            details.get("Raw"),
            "selection":      selection_name,
            "market":         market_name,
            "source":         "BetOnline",
        }
    except Exception as e:
        return None

def fetch_auto_scraped_props(sport="NBA"):
    """Fetch props from GitHub Gist. Fallback when PrizePicks direct fails."""
    try:
        if not GITHUB_TOKEN or not GITHUB_GIST_ID:
            log_error_to_session("fetch_auto_scraped_props", "GitHub credentials not configured", "warning")
            return []

        r = _http.get(
            f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
            timeout=10
        )

        if r.status_code != 200:
            log_error_to_session("fetch_auto_scraped_props", f"Gist API returned {r.status_code}", "warning")
            return []

        files = r.json().get("files", {})
        if "auto_scraped_props.json" not in files:
            log_error_to_session("fetch_auto_scraped_props", "auto_scraped_props.json not found in Gist", "warning")
            return []

        file_obj = files["auto_scraped_props.json"]
        file_size = file_obj.get("size", 0)

        # Large files may be truncated — use raw_url
        if file_size > 900000:
            raw_url = file_obj.get("raw_url", "")
            if raw_url:
                r_raw = _http.get(raw_url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=15)
                if r_raw.status_code == 200:
                    gist_content = r_raw.json()
                else:
                    log_error_to_session("fetch_auto_scraped_props", f"Raw URL returned {r_raw.status_code}", "error")
                    return []
            else:
                log_error_to_session("fetch_auto_scraped_props", "raw_url not available", "error")
                return []
        else:
            content = file_obj.get("content", "")
            if not content:
                log_error_to_session("fetch_auto_scraped_props", "Gist content is empty", "warning")
                return []
            try:
                gist_content = json.loads(content)
            except json.JSONDecodeError as e:
                log_error_to_session("fetch_auto_scraped_props", f"JSON parse error: {str(e)[:100]}", "error")
                return []

        # Verify date freshness — two checks:
        #   (a) date == today  (existing: catches yesterday's data)
        #   (b) updated_at age — warn (not block) when data is same-day but >10h old
        gist_date = gist_content.get("date", "")
        if not is_date_valid_for_today(gist_date):
            # Allow up to 7 days stale — better than an empty board while the
            # PC auto-scraper is not running.  PrizePicks lines shift slowly.
            try:
                from datetime import date as _dc
                _age = (_dc.today() - _dc.fromisoformat(gist_date)).days
                if _age > 7:
                    log_error_to_session("fetch_auto_scraped_props",
                        f"Gist too stale ({_age}d old, date={gist_date}) — run betcouncil_auto_scraper.py", "warning")
                    return []
                log_error_to_session("fetch_auto_scraped_props",
                    f"Gist {_age}d old ({gist_date}) — returning stale data, run scraper for fresh props", "warning")
            except (ValueError, TypeError):
                log_error_to_session("fetch_auto_scraped_props",
                    f"Gist stale (date: {gist_date}) — skipping", "warning")
                return []
        # Hour-based freshness from GitHub Gist updated_at timestamp
        try:
            _gist_json = r.json()
            _updated_at = _gist_json.get("updated_at", "")
            if _updated_at:
                from datetime import datetime as _dt, timezone as _tz
                _gist_ts = _dt.fromisoformat(_updated_at.replace("Z", "+00:00"))
                _age_h = ((_dt.now(_tz.utc) - _gist_ts).total_seconds()) / 3600
                if _age_h > 10:
                    log_error_to_session(
                        "fetch_auto_scraped_props",
                        f"Gist is {_age_h:.1f}h old (updated_at: {_updated_at[:16]}) — "
                        "auto-scraper may not have run today. Data returned but may be stale.",
                        "warning",
                    )
        except Exception:
            pass

        # Filter by sport — case-insensitive to handle lowercase/uppercase mismatches
        all_props = gist_content.get("props", [])
        sport_upper = sport.upper()
        props = [p for p in all_props if p.get("Sport", "").upper() == sport_upper]

        if props:
            log_error_to_session("fetch_auto_scraped_props", f"Loaded {len(props)} {sport} props from Gist", "info")
        else:
            log_error_to_session("fetch_auto_scraped_props", f"No {sport} props in Gist", "warning")

        return props

    except requests.Timeout:
        log_error_to_session("fetch_auto_scraped_props", "Gist API timed out (10s)", "error")
        return []
    except (requests.RequestException, KeyError, ValueError) as e:
        log_error_to_session("fetch_auto_scraped_props", f"Unexpected: {str(e)[:100]}", "error")
        return []

def fetch_ev_api_live():
    """
    Fetch live EV API data. Public endpoint, no auth required.
    Returns raw JSON dict with 'data', 'games', 'updated' keys.
    ⚠️ Endpoint may be locked down at any time — always check status.
    """
    url = "https://api-production-3a3b.up.railway.app/api/ev"
    try:
        r = _http.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
        log_error_to_session("fetch_ev_api_live", f"EV API returned {r.status_code}", "warning")
        return {}
    except requests.exceptions.Timeout:
        log_error_to_session("fetch_ev_api_live", "EV API timeout", "warning")
        return {}
    except Exception as e:
        log_error_to_session("fetch_ev_api_live", str(e)[:100], "warning")
        return {}

def fetch_ev_feed():
    """
    Fetch real-time at-bat log data from EVSharps /api/feed (public, no auth).
    Returns a dict keyed by game string (e.g. "kc @ tb") plus "all" (league agg).

    Per at-bat fields: player, pitcher, pitcherLR, pitch, bats, team, stadium,
      evo (exit velo), la (launch angle), dist (distance ft), is_hh, is_brl,
      result, in (inning), pa (cumulative PA count), hr/park ("N/total" HRs
      hit at this stadium today), dt, created_at.

    "all" aggregate: pitchers, batters, pitches, ff%/si%/sl%/cu% (pitch mix),
      max_ev, hh%, brl%, avg, hr, so, liveGames, updated.

    Use fetch_ev_feed_player_lookup() to turn this into a player-keyed dict.
    """
    url = "https://api-production-3a3b.up.railway.app/api/feed"
    try:
        r = _http.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_feed_player_lookup(feed_data):
    """
    Convert raw /api/feed response into a player-keyed lookup dict.
    Returns { player_norm: {
        today_pa, today_ab, today_brl, today_hh, today_hr,
        today_evo_avg (float or None), today_brl_rate, today_hh_rate,
        hr_park_ratio (str "N/total"), today_results ([str...]),
        pitchers_faced ([str...])
    } }
    """
    from collections import defaultdict
    lookup = defaultdict(lambda: {
        "today_pa": 0, "today_ab": 0, "today_brl": 0, "today_hh": 0,
        "today_hr": 0, "today_evo_sum": 0.0, "today_evo_n": 0,
        "today_results": [], "pitchers_faced": set(),
        "hr_park": "", "game": "",
    })
    if not feed_data or not isinstance(feed_data, dict):
        return {}
    for game_key, records in feed_data.items():
        if game_key == "all" or not isinstance(records, list):
            continue
        for rec in records:
            pname = normalize_name(rec.get("player", ""))
            if not pname:
                continue
            p = lookup[pname]
            p["game"] = rec.get("game", "")
            try: p["today_pa"] = max(p["today_pa"], int(rec.get("pa", 0) or 0))
            except (ValueError, TypeError): pass
            p["today_ab"] += 1
            if rec.get("is_brl"): p["today_brl"] += 1
            if rec.get("is_hh"):  p["today_hh"] += 1
            result = rec.get("result", "")
            if result == "Home Run": p["today_hr"] += 1
            if result: p["today_results"].append(result)
            try:
                evo = float(rec.get("evo") or 0)
                if evo > 0: p["today_evo_sum"] += evo; p["today_evo_n"] += 1
            except (ValueError, TypeError): pass
            pitcher = rec.get("pitcher", "")
            if pitcher: p["pitchers_faced"].add(pitcher)
            hr_park = rec.get("hr/park", "")
            if hr_park: p["hr_park"] = hr_park
    # Finalize
    result_lookup = {}
    for pname, p in lookup.items():
        ab = p["today_ab"]
        evo_avg = round(p["today_evo_sum"] / p["today_evo_n"], 1) if p["today_evo_n"] else None
        result_lookup[pname] = {
            "today_pa":       p["today_pa"],
            "today_ab":       ab,
            "today_brl":      p["today_brl"],
            "today_hh":       p["today_hh"],
            "today_hr":       p["today_hr"],
            "today_evo_avg":  evo_avg,
            "today_brl_rate": round(p["today_brl"] / ab, 3) if ab else 0.0,
            "today_hh_rate":  round(p["today_hh"]  / ab, 3) if ab else 0.0,
            "hr_park":        p["hr_park"],
            "today_results":  p["today_results"],
            "pitchers_faced": list(p["pitchers_faced"]),
            "game":           p["game"],
        }
    return result_lookup


def fetch_ev_bvp(date=None):
    """
    Fetch the EVSharps /api/bvp endpoint — the richest analytical dataset on
    the site. Returns 389+ records for every batter in today's MLB games.

    Unique fields not in /api/ev:
      bvpStats   — full BvP breakdown: {hh%, ab, h, 2b/3b, hr, bb, ba, obp, ops}
      hitRateL10 — last 10 games hit rate %
      hitRateLYR — last year hit rate %
      100-evo    — count of 100+ mph EV at-bats this season
      300-ft     — count of 300+ ft contact at-bats
      pitcherHR_PA   — pitcher HR allowed per PA rate
      pitcherSummary — pre-formatted pitcher quality string
      oppRankSeason  — opponent HR rank on full season basis
      oppRankPer6    — opponent HR rank per 6 innings
      bvt / bvs      — batter vs team / batter vs stadium history
      logs + dtSplits + awayHomeSplits — full season HR log with dates+splits
      feed       — per-game EV arrays for recent at-bats (richer than /api/feed)

    date: optional "YYYY-MM-DD" to query historical data. Defaults to today.
    Returns {"date": "...", "res": [{...}, ...]} or {} on error.
    """
    path = "/api/bvp"
    if date:
        path += f"?date={date}"
    url = f"https://api-production-3a3b.up.railway.app{path}"
    try:
        r = _http.get(url, timeout=20, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/bvp",
        })
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_bvp_player_lookup(bvp_data):
    """
    Convert raw /api/bvp response into a player-keyed lookup dict.
    Only extracts fields that are NEW or RICHER than what /api/ev already provides.
    Returns { player_norm: {
        hit_rate_l10, hit_rate_lyr,
        evo_100_count, ft_300_count,
        pitcher_hr_pa, pitcher_summary,
        opp_rank_season, opp_rank_per6,
        bvp_stats, bvt, bvs,
        bvp_hr, bvp_avg, bvp_h,
        logs_dated ([{"dt","hw","val"}, ...] last 30),
    } }
    """
    lookup = {}
    if not bvp_data or not isinstance(bvp_data, dict):
        return lookup
    for rec in (bvp_data.get("res") or []):
        try:
            pname = normalize_name(rec.get("player", ""))
            if not pname:
                continue
            # Full-season HR log with dates + home/away tags
            logs     = rec.get("logs") or []
            dts      = rec.get("dtSplits") or []
            hw       = rec.get("awayHomeSplits") or []
            logs_dated = []
            for i, val in enumerate(logs[:30]):
                logs_dated.append({
                    "dt":  dts[i] if i < len(dts) else "",
                    "hw":  hw[i]  if i < len(hw)  else "",
                    "val": val,
                })
            lookup[pname] = {
                "hit_rate_l10":     rec.get("hitRateL10"),
                "hit_rate_lyr":     rec.get("hitRateLYR"),
                "evo_100_count":    rec.get("100-evo"),
                "ft_300_count":     rec.get("300-ft"),
                "pitcher_hr_pa":    rec.get("pitcherHR_PA"),
                "pitcher_summary":  rec.get("pitcherSummary", ""),
                "opp_rank_season":  rec.get("oppRankSeason"),
                "opp_rank_per6":    rec.get("oppRankPer6"),
                "bvp_stats":        rec.get("bvpStats") or {},
                "bvt":              rec.get("bvt", ""),
                "bvs":              rec.get("bvs", ""),
                "bvp_hr":           rec.get("bvpHR", 0),
                "bvp_avg":          rec.get("bvpAvg", 0),
                "bvp_h":            rec.get("bvpH", 0),
                "logs_dated":       logs_dated,
                "game":             rec.get("game", ""),
            }
        except Exception:
            continue
    return lookup


def fetch_ev_preview(prop=None):
    """
    Fetch the EVSharps /api/preview endpoint — today's starting pitchers.
    30 records, one per starter, with the richest pitcher Statcast dataset
    on the site (409 fields per record).

    Key unique fields for HR prop enrichment:
      home_run_percentile  — leaguewide HR-allowed percentile (higher = more HR-prone)
      hr_pa_percentile     — HR per PA percentile
      hr_pa                — raw HR per PA rate
      hr_l / hr_r          — HRs allowed vs L/R batters
      hr_l_rate / hr_r_rate — HR rate vs L/R batters (platoon signal)
      hr_pitch / hr_pitch_l / hr_pitch_r — which pitch types gave up HRs
      arm_angle            — pitcher arm slot
      whiff_percent / barrel_batted_rate / hard_hit_percent — quality metrics
      k_percent / xera     — K rate and expected ERA
      n_fastball_formatted / fastball_avg_speed — pitch mix and velo

    prop: optional "k" for K-prop-specific preview. Defaults to HR view.
    Returns {"tier": "free", "data": [{...}, ...]} or {} on error.
    """
    path = "/api/preview"
    if prop:
        path += f"?prop={prop}"
    url = f"https://api-production-3a3b.up.railway.app{path}"
    try:
        r = _http.get(url, timeout=15, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/preview",
        })
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_preview_pitcher_lookup(preview_data):
    """
    Convert raw /api/preview response into a pitcher-name-keyed lookup dict.
    Extracts the fields most actionable for HR prop enrichment.

    Returns { pitcher_norm: {
        home_run_percentile, hr_pa_percentile, hr_pa,
        hr_l, hr_r, hr_l_rate, hr_r_rate,
        hr_l_percentile, hr_r_percentile,
        hr_l_rate_percentile, hr_r_rate_percentile,
        hr_pitch, hr_pitch_l, hr_pitch_r,
        arm_angle, k_percent, xera, p_era,
        whiff_percent, whiff_pct_pct,
        barrel_rate, barrel_rate_pct,
        hard_hit_pct, hard_hit_pct_pct,
        fb_velo, fb_pct, breaking_pct, offspeed_pct,
        team, opp, game, weather, bpp,
    } }
    """
    lookup = {}
    if not preview_data or not isinstance(preview_data, dict):
        return lookup
    for rec in (preview_data.get("data") or []):
        try:
            pname = normalize_name(rec.get("player", ""))
            if not pname:
                continue
            lookup[pname] = {
                "home_run_percentile":      rec.get("home_run_percentile"),
                "hr_pa_percentile":         rec.get("hr_pa_percentile"),
                "hr_pa":                    rec.get("hr_pa"),
                "hr_l":                     rec.get("hr_l"),
                "hr_r":                     rec.get("hr_r"),
                "hr_l_rate":                rec.get("hr_l_rate"),
                "hr_r_rate":                rec.get("hr_r_rate"),
                "hr_l_percentile":          rec.get("hr_l_percentile"),
                "hr_r_percentile":          rec.get("hr_r_percentile"),
                "hr_l_rate_percentile":     rec.get("hr_l_rate_percentile"),
                "hr_r_rate_percentile":     rec.get("hr_r_rate_percentile"),
                "hr_pitch":                 rec.get("hr_pitch") or [],
                "hr_pitch_l":               rec.get("hr_pitch_l") or [],
                "hr_pitch_r":               rec.get("hr_pitch_r") or [],
                "arm_angle":                rec.get("arm_angle"),
                "k_percent":                rec.get("k_percent"),
                "xera":                     rec.get("xera"),
                "p_era":                    rec.get("p_era"),
                "whiff_percent":            rec.get("whiff_percent"),
                "whiff_pct_pct":            rec.get("whiff_percentPercentile"),
                "barrel_rate":              rec.get("barrel_batted_rate"),
                "barrel_rate_pct":          rec.get("barrel_batted_ratePercentile"),
                "hard_hit_pct":             rec.get("hard_hit_percent"),
                "hard_hit_pct_pct":         rec.get("hard_hit_percentPercentile"),
                "fb_velo":                  rec.get("fastball_avg_speed"),
                "fb_pct":                   rec.get("n_fastball_formatted"),
                "breaking_pct":             rec.get("n_breaking_formatted"),
                "offspeed_pct":             rec.get("n_offspeed_formatted"),
                "team":                     rec.get("team", ""),
                "opp":                      rec.get("opp", ""),
                "game":                     rec.get("game", ""),
                "weather":                  rec.get("weather") or {},
                "bpp":                      rec.get("bpp", ""),
            }
        except Exception:
            continue
    return lookup


def fetch_ev_strikeouts():
    """
    Fetch the EVSharps /api/strikeouts endpoint — 532 K prop records,
    one per pitcher/line combination for today's MLB games.

    Unique fields not in /api/ev:
      hitRates   — K hit rates across szn/lyr/L5/L10/L20 windows
                   each window: {w: wins, t: total, p: pct}
      logs       — raw K counts per start (last ~16 starts)
      pitcherData — Statcast quality metrics for the pitcher:
                    xwoba, barrel_batted_rate, hard_hit_percent,
                    sweet_spot_percent, exit_velocity_avg, p_era, etc.
      oppRank    — opponent team's K rank (higher rank = weaker K offense)
      bpp / bppProj / bppDiff — BetterProps projection vs book line

    Returns {"updated": {...}, "games": [...], "times": [...], "data": [...]}
    or {} on error.
    """
    url = "https://api-production-3a3b.up.railway.app/api/strikeouts"
    try:
        r = _http.get(url, timeout=20, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/strikeouts",
        })
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_strikeouts_pitcher_lookup(strikeouts_data):
    """
    Convert raw /api/strikeouts response into a pitcher-keyed lookup dict.
    Key: normalize_name(pitcher). Deduplicated — if a pitcher appears in
    multiple line records (over/under), only the first is kept since the
    pitcher-level fields (hitRates, logs, pitcherData) are identical.

    Returns { pitcher_norm: {
        k_rate_szn, k_rate_l5, k_rate_l10, k_rate_lyr,
        k_logs ([int, ...] last N K counts),
        k_opp_rank,
        k_pitcher_data (Statcast dict),
        k_bpp, k_bpp_proj, k_bpp_diff,
        k_ev, k_fair_val,
    } }
    """
    lookup = {}
    if not strikeouts_data or not isinstance(strikeouts_data, dict):
        return lookup
    for rec in (strikeouts_data.get("data") or []):
        try:
            pname = normalize_name(rec.get("player", ""))
            if not pname or pname in lookup:
                continue
            hr = rec.get("hitRates") or {}
            lookup[pname] = {
                "k_rate_szn":     (hr.get("szn") or {}).get("p"),
                "k_rate_l5":      (hr.get("L5") or {}).get("p"),
                "k_rate_l10":     (hr.get("L10") or {}).get("p"),
                "k_rate_lyr":     (hr.get("lyr") or {}).get("p"),
                "k_logs":         rec.get("logs") or [],
                "k_opp_rank":     rec.get("oppRank"),
                "k_pitcher_data": rec.get("pitcherData") or {},
                "k_bpp":          rec.get("bpp", ""),
                "k_bpp_proj":     rec.get("bppProj"),
                "k_bpp_diff":     rec.get("bppDiff"),
                "k_ev":           rec.get("ev"),
                "k_fair_val":     rec.get("fairVal"),
            }
        except Exception:
            continue
    return lookup


def fetch_ev_api_outliers(sport="mlb"):
    """
    Fetch outlier props from EVSharps /api/outliers?sport={sport}.
    Returns props with historical hit rates and per-game logs — a
    completely different dataset from /api/ev (no multi-book EV, but
    has hitRate % and a raw game-log array for recent form context).
    Schema per item: player, prop, game, team, opp, pos, bookOdds,
      hitRate (int %), logs ([int...] last ~50 games), ou (consensus line),
      ev, fairVal, implied, kelly, handicap.
    Returns {} on 500/error (WNBA/NBA/NHL return 500 off-season).
    """
    url = f"https://api-production-3a3b.up.railway.app/api/outliers?sport={sport.lower()}"
    try:
        r = _http.get(url, timeout=15)
        if r.status_code == 200:
            j = r.json()
            # Tag items so downstream knows the source
            for item in (j.get("data") or []):
                item["_outlier_source"] = True
                item["_source_sport"]   = sport.upper()
            return j
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_api_wnba():
    """
    Fetch live WNBA player props from EVSharps /api/wnba (public endpoint).
    Tags each item with _source_sport='WNBA' so _ev_infer_sport() can
    distinguish WNBA pts/reb/ast from NBA props.
    Returns a dict with same structure as fetch_ev_api_live():
      { "data": [...], "games": [...], "times": {...}, "updated": "..." }
    """
    url = "https://api-production-3a3b.up.railway.app/api/wnba"
    try:
        r = _http.get(url, timeout=15)
        if r.status_code == 200:
            j = r.json()
            for item in (j.get("data") or []):
                item["_source_sport"] = "WNBA"
            return j
        log_error_to_session("fetch_ev_api_wnba", f"WNBA EV API returned {r.status_code}", "warning")
        return {}
    except requests.exceptions.Timeout:
        log_error_to_session("fetch_ev_api_wnba", "WNBA EV API timeout", "warning")
        return {}
    except Exception as e:
        log_error_to_session("fetch_ev_api_wnba", str(e)[:100], "warning")
        return {}


def fetch_ev_movement(sport="mlb"):
    """
    Fetch line movement data from EVSharps /api/movement endpoint.
    Requires JWT token in st.secrets['EV_JWT'].
    Returns list of movement objects or [] on failure.

    Each object expected to contain:
      player, prop, handicap, team, opp, game,
      opening (opening odds dict per book),
      current (current odds dict per book),
      movement (direction/magnitude),
      bookOdds (current snapshot),
      and possibly: sharp_action, steam_move, reverse_line_move flags
    """
    jwt = _get_ev_jwt()
    if not jwt:
        return []

    url = "https://api-production-3a3b.up.railway.app/api/movement"
    try:
        r = _http.get(
            url,
            headers=_ev_auth_headers(),
            params={"sport": sport.lower()},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            # Handle both list and dict responses
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("data", data.get("movements", []))
            return []
        if r.status_code == 401:
            log_error_to_session("fetch_ev_movement", "JWT expired — update EV_JWT in Streamlit secrets", "warning")
        else:
            log_error_to_session("fetch_ev_movement", f"Movement API {r.status_code}", "warning")
        return []
    except requests.exceptions.Timeout:
        log_error_to_session("fetch_ev_movement", "Movement API timeout", "warning")
        return []
    except Exception as e:
        log_error_to_session("fetch_ev_movement", str(e)[:100], "warning")
        return []


def fetch_ev_stats(prop="hr"):
    """
    Fetch the EVSharps /api/stats?prop={prop} endpoint.
    prop: 'hr' (Home Runs), 'h' (Hits), 'h_r_rbi' (H+R+RBI combined).

    Returns {"tier": "free", "data": [...]} or {} on error.
    Response is gzip-encoded — requests handles decompression automatically.

    Unique fields vs /api/ev:
      hitRate, hitRateL10, hitRateLYR — historical over-rate % for this prop
      awayHomeSplits — {away: {...}, home: {...}} performance splits
      dtSplits — day-of-week / time-of-day splits
      oppRankClass — categorical label ("Below Avg", "Average", "Elite", etc.)
      oppRankSeason, oppRankPer6 — opponent rank breakdowns
      bvpHR, bvpAvg, bvpH — batter-vs-pitcher specific to HR/hits
      logs — raw per-game stat counts (last ~20 games)
    """
    url = f"https://api-production-3a3b.up.railway.app/api/stats?prop={prop}"
    try:
        r = _http.get(url, timeout=20, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/",
            "accept-encoding": "gzip, deflate",
        })
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_stats_player_lookup(stats_data, prop_name_mapped="Home Runs"):
    """
    Convert /api/stats response into a (player_norm, prop_name) keyed lookup.

    Key: (normalize_name(player), prop_name_mapped) — matches signal_lookup keys.
    Deduped: if a player has multiple line records for the same prop, only the
    first is kept (pitcher/line columns differ but player-level stats are the same).

    Returns { (player_norm, prop_name_mapped): {
        stats_hit_rate, stats_hit_rate_l10, stats_hit_rate_lyr,
        stats_opp_rank, stats_opp_rank_class, stats_opp_rank_season,
        stats_opp_rank_per6, stats_stadium_rank, stats_stadium_rank_l,
        stats_stadium_rank_r, stats_away_home_splits, stats_dt_splits,
        stats_bvp_hr, stats_bvp_avg, stats_bvp_h, stats_logs,
    } }
    """
    lookup = {}
    if not stats_data or not isinstance(stats_data, dict):
        return lookup
    for rec in (stats_data.get("data") or []):
        try:
            pname = normalize_name(rec.get("player", ""))
            if not pname:
                continue
            key = (pname, prop_name_mapped)
            if key in lookup:
                continue
            lookup[key] = {
                "stats_hit_rate":         rec.get("hitRate"),
                "stats_hit_rate_l10":     rec.get("hitRateL10"),
                "stats_hit_rate_lyr":     rec.get("hitRateLYR"),
                "stats_opp_rank":         rec.get("oppRank"),
                "stats_opp_rank_class":   rec.get("oppRankClass"),
                "stats_opp_rank_season":  rec.get("oppRankSeason"),
                "stats_opp_rank_per6":    rec.get("oppRankPer6"),
                "stats_stadium_rank":     rec.get("stadiumRank"),
                "stats_stadium_rank_l":   rec.get("stadiumRankLeft"),
                "stats_stadium_rank_r":   rec.get("stadiumRankRight"),
                "stats_away_home_splits": rec.get("awayHomeSplits") or {},
                "stats_dt_splits":        rec.get("dtSplits") or {},
                "stats_bvp_hr":           rec.get("bvpHR"),
                "stats_bvp_avg":          rec.get("bvpAvg"),
                "stats_bvp_h":            rec.get("bvpH"),
                "stats_logs":             rec.get("logs") or [],
            }
        except Exception:
            continue
    return lookup


def fetch_ev_barrels():
    """
    Fetch the EVSharps /api/barrels endpoint — 322-record Statcast contact dataset.
    Response is gzip-encoded — requests handles decompression automatically.

    Unique fields not available from /api/ev savant dict:
      barrels_per_bip + Percentile — barrel rate with leaguewide percentile rank
      exit_velocity_avg + Percentile — EV with rank
      hard_hit_percent + Percentile
      sweet_spot_percent + Percentile
      launch_angle_avg + Percentile
      flyballs_percent + Percentile
      avg_swing_speed, blasts_swing, squared_up_swing — swing quality metrics
      pull_percent, meatball_percent — contact tendencies

    Returns list of records (one per player) or [] on error.
    """
    url = "https://api-production-3a3b.up.railway.app/api/barrels"
    try:
        r = _http.get(url, timeout=20, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/",
            "accept-encoding": "gzip, deflate",
        })
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else (data.get("data") or [])
        return []
    except requests.exceptions.Timeout:
        return []
    except Exception:
        return []


def fetch_ev_barrels_player_lookup(barrels_data):
    """
    Convert /api/barrels list into player-keyed lookup.
    Key: normalize_name(player). Deduped — first record per player kept.

    Returns { player_norm: {
        brl_barrel_ct, brl_barrels_per_bip, brl_barrels_per_bip_pct,
        brl_exit_velo, brl_exit_velo_pct,
        brl_hard_hit_pct, brl_hard_hit_pct_pct,
        brl_sweet_spot_pct, brl_sweet_spot_pct_pct,
        brl_launch_angle, brl_launch_angle_pct,
        brl_flyballs_pct, brl_flyballs_pct_pct,
        brl_avg_swing_speed, brl_blasts_swing, brl_squared_up_swing,
        brl_pull_pct, brl_meatball_pct, brl_pa, brl_home_runs, brl_bip,
    } }
    """
    lookup = {}
    if not barrels_data or not isinstance(barrels_data, list):
        return lookup
    for rec in barrels_data:
        try:
            pname = normalize_name(rec.get("player", ""))
            if not pname or pname in lookup:
                continue
            lookup[pname] = {
                "brl_barrel_ct":           rec.get("barrel_ct"),
                "brl_barrels_per_bip":     rec.get("barrels_per_bip"),
                "brl_barrels_per_bip_pct": rec.get("barrels_per_bipPercentile"),
                "brl_exit_velo":           rec.get("exit_velocity_avg"),
                "brl_exit_velo_pct":       rec.get("exit_velocity_avgPercentile"),
                "brl_hard_hit_pct":        rec.get("hard_hit_percent"),
                "brl_hard_hit_pct_pct":    rec.get("hard_hit_percentPercentile"),
                "brl_sweet_spot_pct":      rec.get("sweet_spot_percent"),
                "brl_sweet_spot_pct_pct":  rec.get("sweet_spot_percentPercentile"),
                "brl_launch_angle":        rec.get("launch_angle_avg"),
                "brl_launch_angle_pct":    rec.get("launch_angle_avgPercentile"),
                "brl_flyballs_pct":        rec.get("flyballs_percent"),
                "brl_flyballs_pct_pct":    rec.get("flyballs_percentPercentile"),
                "brl_avg_swing_speed":     rec.get("avg_swing_speed"),
                "brl_blasts_swing":        rec.get("blasts_swing"),
                "brl_squared_up_swing":    rec.get("squared_up_swing"),
                "brl_pull_pct":            rec.get("pull_percent"),
                "brl_meatball_pct":        rec.get("meatball_percent"),
                "brl_pa":                  rec.get("pa"),
                "brl_home_runs":           rec.get("home_runs"),
                "brl_bip":                 rec.get("bip"),
            }
        except Exception:
            continue
    return lookup


def fetch_ev_recap():
    """
    Fetch the EVSharps /api/recap endpoint — yesterday's player prop results.
    Response is gzip-encoded — requests handles decompression automatically.

    Returns {"record": {...}, "data": [...]} or {} on error.
      record: nested ROI / win-loss breakdown by book-vs-sharp-book combination
              (e.g. "hr-vs-circa", "hr-vs-pn+circa") across bet sizes
              (probit / fd / dk / b365 / mgm / espn / fn / br / hr / kal / nv)
      data:   per-prop result rows with fields:
                dt, key, prop, game, player, pos, bookOdds, team, opp,
                oppRank, book, line, handicap, order, under, ouIdx,
                bvp, bpp, hit (bool), result (float pnl)
    """
    url = "https://api-production-3a3b.up.railway.app/api/recap"
    try:
        r = _http.get(url, timeout=15, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/",
            "accept-encoding": "gzip, deflate",
        })
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_mlb():
    """
    Fetch the EVSharps /api/mlb endpoint — today's curated featured MLB picks.
    ~40 records (filtered, highest-value props), gzip-encoded.

    Richer than /api/ev for the props it covers:
      hitRates  — {szn, L5, L10, L20} each {w: wins, t: total, p: pct}
                  — four-window W/L record vs a single hitRate % in /api/outliers
      lastHR    — date of batter's last home run
      liquidity — betting volume/liquidity per book
      ou        — consensus over/under line
      roof      — stadium roof status ("open", "dome", "closed")
      order     — batting order position
      logs      — raw game-by-game stat counts (last ~20 games)
      bvp       — batter-vs-pitcher summary string

    Returns {"data": [...], "games": [...], "updated": ...} or {} on error.
    """
    url = "https://api-production-3a3b.up.railway.app/api/mlb"
    try:
        r = _http.get(url, timeout=20, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/",
            "accept-encoding": "gzip, deflate",
        })
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def fetch_ev_mlb_player_lookup(mlb_data):
    """
    Convert /api/mlb response into a (player_norm, prop_name) keyed lookup.
    Key matches signal_lookup: (normalize_name(player), EV_PROP_MAP[prop]).
    Deduped — first record per player+prop kept.

    Returns { (player_norm, prop_name): {
        mlb_hit_rate_szn, mlb_hit_rate_szn_w, mlb_hit_rate_szn_t,
        mlb_hit_rate_l5,  mlb_hit_rate_l5_w,  mlb_hit_rate_l5_t,
        mlb_hit_rate_l10, mlb_hit_rate_l10_w, mlb_hit_rate_l10_t,
        mlb_hit_rate_l20, mlb_hit_rate_l20_w, mlb_hit_rate_l20_t,
        mlb_last_hr, mlb_ou, mlb_roof, mlb_order, mlb_logs, mlb_bvp,
        mlb_liquidity,
    } }
    """
    _EV_PROP_MAP = {
        "hr": "Home Runs", "hits": "Hits", "rbi": "RBI", "runs": "Runs",
        "sb": "Stolen Bases", "k": "Pitcher Strikeouts",
        "pts": "Points", "reb": "Rebounds", "ast": "Assists",
        "td": "Touchdowns", "rush_yards": "Rush Yards", "rec_yards": "Rec Yards",
        "goals": "Goals", "shots": "Shots",
    }
    lookup = {}
    if not mlb_data or not isinstance(mlb_data, dict):
        return lookup
    for rec in (mlb_data.get("data") or []):
        try:
            pname = normalize_name(rec.get("player", ""))
            if not pname:
                continue
            prop_key  = rec.get("prop", "")
            prop_name = _EV_PROP_MAP.get(prop_key, prop_key.title())
            key = (pname, prop_name)
            if key in lookup:
                continue
            hr = rec.get("hitRates") or {}
            def _w(win_key):
                block = hr.get(win_key) or {}
                return block.get("p"), block.get("w"), block.get("t")
            szn_p, szn_w, szn_t = _w("szn")
            l5_p,  l5_w,  l5_t  = _w("L5")
            l10_p, l10_w, l10_t = _w("L10")
            l20_p, l20_w, l20_t = _w("L20")
            lookup[key] = {
                "mlb_hit_rate_szn":   szn_p,
                "mlb_hit_rate_szn_w": szn_w,
                "mlb_hit_rate_szn_t": szn_t,
                "mlb_hit_rate_l5":    l5_p,
                "mlb_hit_rate_l5_w":  l5_w,
                "mlb_hit_rate_l5_t":  l5_t,
                "mlb_hit_rate_l10":   l10_p,
                "mlb_hit_rate_l10_w": l10_w,
                "mlb_hit_rate_l10_t": l10_t,
                "mlb_hit_rate_l20":   l20_p,
                "mlb_hit_rate_l20_w": l20_w,
                "mlb_hit_rate_l20_t": l20_t,
                "mlb_last_hr":        rec.get("lastHR"),
                "mlb_ou":             rec.get("ou"),
                "mlb_roof":           rec.get("roof"),
                "mlb_order":          rec.get("order"),
                "mlb_logs":           rec.get("logs") or [],
                "mlb_bvp":            rec.get("bvp", ""),
                "mlb_liquidity":      rec.get("liquidity") or {},
            }
        except Exception:
            continue
    return lookup


def fetch_ev_trends():
    """
    Fetch the EVSharps /api/trends endpoint — league-wide HR and barrel rates
    by year (1990-present), month, and day. Response is gzip-encoded.

    Structure: { year: { month: { hr:[...], g:[...], hr/g:[...], dt:[...],
                                   brl:[...], brl/g:[...] } } }

    Used to compute a same-day "league HR environment" signal:
      - today's league HR/game vs season average
      - whether this is a historically barrel-friendly or suppressed day
      - year-over-year HR rate trends for model calibration

    Returns the full nested dict or {} on error.
    """
    url = "https://api-production-3a3b.up.railway.app/api/trends"
    try:
        r = _http.get(url, timeout=15, headers={
            "origin":  "https://www.evsharps.com",
            "referer": "https://www.evsharps.com/",
            "accept-encoding": "gzip, deflate",
        })
        if r.status_code == 200:
            return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


def compute_ev_trends_signal(trends_data):
    """
    Compute league-level HR environment signals from /api/trends data.

    Returns dict:
      league_hr_per_g_season — avg HR/game for the current season-to-date
      league_hr_per_g_l7     — avg HR/game over the last 7 game-days
      league_hr_per_g_l7_vs_season — l7 rate minus season avg (positive = hot env)
      league_brl_per_g_season — avg barrel/game season-to-date
      league_trend_note       — human-readable summary string
      league_env_edge         — float signal: +0.01/+0.02 if hot, -0.01/-0.02 if cold
    """
    import datetime
    result = {
        "league_hr_per_g_season":      None,
        "league_hr_per_g_l7":          None,
        "league_hr_per_g_l7_vs_season": None,
        "league_brl_per_g_season":     None,
        "league_trend_note":           "",
        "league_env_edge":             0.0,
    }
    if not trends_data or not isinstance(trends_data, dict):
        return result
    try:
        today = datetime.date.today()
        yr    = str(today.year)
        yr_data = trends_data.get(yr) or {}
        if not yr_data:
            return result

        # Collect all daily data points for the current season
        all_hr_per_g = []
        all_brl_per_g = []
        all_days = []  # (date_str, hr_per_g, brl_per_g)
        for mo_str, mo_data in yr_data.items():
            dts    = mo_data.get("dt") or []
            hr_g   = mo_data.get("hr/g") or []
            brl_g  = mo_data.get("brl/g") or []
            for i, dt_str in enumerate(dts):
                try:
                    dt_full = f"{yr}-{dt_str}"
                    hrg  = float(hr_g[i])  if i < len(hr_g)  else None
                    brlg = float(brl_g[i]) if i < len(brl_g) else None
                    if hrg is not None:
                        all_hr_per_g.append(hrg)
                        all_brl_per_g.append(brlg or 0)
                        all_days.append((dt_full, hrg, brlg or 0))
                except (ValueError, TypeError, IndexError):
                    continue

        if not all_hr_per_g:
            return result

        season_avg   = round(sum(all_hr_per_g) / len(all_hr_per_g), 3)
        season_brl   = round(sum(all_brl_per_g) / len(all_brl_per_g), 3)
        l7_days      = all_days[-7:] if len(all_days) >= 7 else all_days
        l7_avg       = round(sum(d[1] for d in l7_days) / len(l7_days), 3) if l7_days else None
        l7_vs_season = round(l7_avg - season_avg, 3) if l7_avg is not None else None

        result["league_hr_per_g_season"]      = season_avg
        result["league_hr_per_g_l7"]          = l7_avg
        result["league_hr_per_g_l7_vs_season"] = l7_vs_season
        result["league_brl_per_g_season"]     = season_brl

        # Edge signal
        edge = 0.0; note = f"LeagueHR L7={l7_avg:.2f}/g vs szn={season_avg:.2f}/g"
        if l7_vs_season is not None:
            if l7_vs_season >= 0.40:   edge =  0.02; note += " 🔥HOT"
            elif l7_vs_season >= 0.20: edge =  0.01; note += " ↑hot"
            elif l7_vs_season <= -0.40: edge = -0.02; note += " 🥶COLD"
            elif l7_vs_season <= -0.20: edge = -0.01; note += " ↓cold"
        result["league_trend_note"] = note
        result["league_env_edge"]   = edge
    except Exception:
        pass
    return result


def fetch_fanduel_event_ids(sport):
    """Fetch today's FanDuel event IDs for a sport via the navigation/facet
    endpoint, confirmed via real capture to return a clean per-sport event
    list (16 distinct IDs for MLB, no unrelated/stale events mixed in —
    unlike content-managed-page which mixes in long-running futures markets).
    Feeds fetch_fanduel_direct's event_ids param, which previously had no
    caller supplying it and so always returned [] regardless of token
    validity."""
    competition_id = FANDUEL_COMPETITION_IDS.get(sport.upper())
    if not competition_id:
        return []

    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    px_context = _get_fanduel_px_context()
    if not px_context:
        return []
    state = _get_fanduel_state()

    cache_path = os.path.join(CACHE_DIR, f"fanduel_event_ids_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 10:
            try:
                cached = _safe_load_pkl(cache_path)
                if cached:
                    return cached
            except (IOError, ValueError):
                pass

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": f"https://{state}.sportsbook.fanduel.com",
        "referer": f"https://{state}.sportsbook.fanduel.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "x-application": "FhMFpcPWXMeyZxOx",
        "x-px-context": px_context,
    }
    body = {
        "filter": {
            "competitionIds": [competition_id],
            "contentGroup": {"language": "en", "regionCode": "NAMERICA"},
            "marketLevels": ["AVB_EVENT"],
            "maxResults": 0,
            "productTypes": ["SPORTSBOOK"],
            "selectBy": "FIRST_TO_START",
        },
        "facets": [{"type": "COMPETITION"}, {"type": "EVENT", "next": {"type": "IN_PLAY"}}],
        "currencyCode": "USD",
    }

    try:
        r = session.post(
            f"https://scan.{state}.sportsbook.fanduel.com/api/sports/navigation/facet/v1.0/search",
            headers=headers, json=body, timeout=15
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return []

    event_ids = set()
    def _walk(obj):
        if isinstance(obj, dict):
            eid = obj.get("eventId")
            if isinstance(eid, int):
                event_ids.add(eid)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
    _walk(data)
    result = list(event_ids)

    try:
        with open(cache_path, "wb") as f:
            pickle.dump(result, f)
    except (IOError, OSError):
        pass

    return result

def fetch_fanduel_direct(sport, event_ids=None):
    """Fetch FanDuel props directly using curl_cffi. Fallback when OddsPAPI is down.

    IMPORTANT — confirmed via TWO live DevTools captures (2026-06-20):

    1. Discovery endpoint (CONFIRMED, full response body captured): GET
       api.sportsbook.fanduel.com/sbapi/event-page?_ak=KEY&eventId={id} returns the
       full market list for ONE specific game under attachments.markets, keyed by
       marketId (e.g. "704.173602333"). Each market has marketName, marketType, and
       a runners[] list where odds live INLINE as runner["winRunnerOdds"]
       ["americanDisplayOdds"]["americanOdds"] — there is NO separate top-level
       "selections" lookup table, unlike this function's pre-2026-06-20 assumption.
       This is per-EVENT, not per-sport — there is no single "all games for this
       sport" discovery call confirmed yet, so this function requires a list of
       eventIds to query (see event_ids param). Getting a sport's full event ID list
       still needs its own DevTools capture (e.g. the sport-overview page load) —
       not yet done, flagged honestly rather than guessed at.

    2. Pricing endpoint (CONFIRMED): POST smp.{state}.sportsbook.fanduel.com/api/
       sports/fixedodds/readonly/v1/getMarketPrices?priceHistory=1 with a JSON body
       of {"marketIds": [...]}. Requires the same PerimeterX x-px-context header as
       event-page. NOTE: this function currently relies on event-page alone for both
       market discovery AND live odds (event-page already returns current odds
       inline) — getMarketPrices is kept available below for a future live-refresh
       pass but isn't required for a first working version.

    PerimeterX requirement (unchanged from prior finding, still accurate): both
    endpoints require a valid x-px-context header containing a PerimeterX session
    token (_px3/_pxvid/pxcts), generated by a real browser's JS challenge and
    observed to expire within minutes. No static request can generate this token.
    Until a Playwright-based session harvester exists (scaffolding in
    betcouncil_auto_scraper.py), this function reads the token from Streamlit
    secrets (FANDUEL_PX_CONTEXT) or a short-lived local cache file, and cleanly
    returns [] when no valid token is present rather than failing loudly.

    Market name parsing (CONFIRMED from real data): player prop markets follow TWO
    distinct naming patterns that both needed handling —
      - Over/Under markets: marketName="{Player} - Strikeouts", runnerName=
        "{Player} Over"/"{Player} Under", handicap=the line (e.g. 4.5)
      - Alt/count markets: marketName="{Player} - Alt Strikeouts", runnerName=
        "{Player} 3+ Strikeouts" / "4+ Strikeouts" / etc, handicap=0 (the count is
        IN the runner name, not the handicap field) — these are parsed into
        Line=N, Side=OVER from the leading digit in the runner name.
    Game-line markets (Moneyline, Run Line, Total Runs, etc.) are correctly
    excluded by the existing keyword filter on marketName/marketType.
    """
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    FD_KEY = "FhMFpcPWXMeyZxOx"
    px_context = _get_fanduel_px_context()
    if not px_context:
        # Downgraded from st.warning to a console log (2026-07-11): this token
        # expires within minutes and can only come from a live browser JS
        # challenge, so it's realistically never present — this fires on
        # nearly every OddsPAPI-empty fallback and was pure noise with no
        # actionable fix for the user. FanDuel props still arrive via the
        # separate fetch_fanduel_props_from_gist browser harvester; this
        # function is just a redundant direct-API fallback attempt, same as
        # the other 6 books in this loop which already fail silently.
        print("[INFO] fetch_fanduel_direct: no PerimeterX token available, skipping (props still available via Gist harvester)")
        return []

    state = _get_fanduel_state()

    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "origin": f"https://{state}.sportsbook.fanduel.com",
        "referer": f"https://{state}.sportsbook.fanduel.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "x-application": FD_KEY,
        "x-px-context": px_context,
    }

    props = []
    cache_path = os.path.join(CACHE_DIR, f"fanduel_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    # event_ids must be supplied by the caller (e.g. cross-referenced from another
    # book's schedule data for the same date/sport) until a confirmed sport-wide
    # discovery endpoint is captured. No silent guessing at an endpoint here.
    if not event_ids:
        return []

    PROP_KEYWORDS = ["point", "rebound", "assist", "steal", "block", "three",
                      "strikeout", "hit", "home run", "rbi", "bases",
                      "goal", "shot", "save", "yard", "reception",
                      "touchdown", "pass", "rush", "pra", "fantasy"]

    try:
        for eid in event_ids[:15]:  # defensive cap per call
            r = session.get(
                "https://api.sportsbook.fanduel.com/sbapi/event-page",
                params={"_ak": FD_KEY, "eventId": eid,
                        "useCombinedTouchdownsVirtualMarket": "true", "useQuickBets": "true"},
                headers=headers, timeout=15
            )
            if r.status_code != 200:
                continue

            data = r.json()
            markets = data.get("attachments", {}).get("markets", {})

            for mkt_id, mkt in markets.items():
                mkt_name = mkt.get("marketName", "")
                mkt_type = mkt.get("marketType", "")
                if not any(kw in mkt_name.lower() or kw in mkt_type.lower() for kw in PROP_KEYWORDS):
                    continue
                # Game-line markets (Moneyline, Run Line, Total Runs) share some
                # keyword overlap risk (e.g. "RUN" in Run Line vs "run" props) —
                # exclude known non-prop market types explicitly.
                if mkt_type in ("MATCH_HANDICAP_(2-WAY)", "TOTAL_POINTS_(OVER/UNDER)", "MONEY_LINE"):
                    continue

                # Player name lives in marketName as "{Player} - {PropLabel}"
                player_from_market = mkt_name.split(" - ")[0].strip() if " - " in mkt_name else ""

                for runner in mkt.get("runners", []):
                    rn_name = runner.get("runnerName", "")
                    handicap = runner.get("handicap")
                    am = (runner.get("winRunnerOdds", {}) or {}).get("americanDisplayOdds", {}).get("americanOdds")
                    odds = f"{'+' if am is not None and am > 0 else ''}{int(am)}" if am is not None else "—"

                    player, side, line = "", "OVER", None
                    if " Over" in rn_name:
                        player = rn_name.split(" Over")[0].strip()
                        side, line = "OVER", handicap
                    elif " Under" in rn_name:
                        player = rn_name.split(" Under")[0].strip()
                        side, line = "UNDER", handicap
                    else:
                        # Alt/count markets, e.g. "Troy Melton 3+ Strikeouts" — the
                        # line is the leading digit in the runner name, not handicap
                        # (handicap is 0 for these), confirmed from real capture.
                        m = re.match(r"^(.*?)\s+(\d+)\+\s", rn_name)
                        if m:
                            player = m.group(1).strip()
                            line = float(m.group(2)) - 0.5  # "3+" implies line 2.5 OVER
                            side = "OVER"
                        elif player_from_market:
                            player = player_from_market

                    if not player and player_from_market:
                        player = player_from_market
                    if line is None:
                        line = handicap

                    if player and line is not None:
                        props.append({
                            "Player": player, "Prop": mkt_name,
                            "Line": float(line), "Side": side,
                            "OverOdds": odds if side == "OVER" else "—",
                            "UnderOdds": odds if side == "UNDER" else "—",
                            "Book": "FanDuel", "Sport": sport,
                            "source": "fanduel_direct",
                        })
            time.sleep(0.2)

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except (IOError, ValueError) as _e:
        print(f"[WARN] fetch_fanduel_direct: {_e}")

    return props


# ── FanDuel Playwright game-lines fetcher ─────────────────────────────────
# Helpers and constants are module-level so they can be reused by any future
# FanDuel function without re-importing or re-defining.

_FD_SPORT_URL_PATHS = {
    "MLB":  "mlb-baseball",
    "NBA":  "nba-basketball",
    "NFL":  "nfl-football",
    "NHL":  "nhl-hockey",
    "WNBA": "wnba-basketball",
}

# Market types that represent game lines (ML / spread / total).
# These are EXCLUDED from fetch_fanduel_direct (props) and INCLUDED here.
_FD_GL_MARKET_TYPES = frozenset({
    "MONEY_LINE",
    "MATCH_HANDICAP_(2-WAY)",
    "RUN_LINE",                        # MLB
    "PUCK_LINE",                       # NHL
    "TOTAL_POINTS_(OVER/UNDER)",       # NBA / NFL
    "TOTAL_RUNS_(OVER/UNDER)",         # MLB
    "TOTAL_GOALS_(OVER/UNDER)",        # NHL
})


def _fd_american_odds(runner: dict):
    """Extract americanOdds int from a FanDuel runner dict, or None."""
    try:
        return int(
            runner.get("winRunnerOdds", {})
                  .get("americanDisplayOdds", {})
                  .get("americanOdds", None)
        )
    except (TypeError, ValueError):
        return None


def _fd_parse_event_name(name: str):
    """
    Parse a FanDuel event name string into (away_team, home_team).

    FanDuel uses several separators depending on sport:
      "Kansas City Royals @ Houston Astros"   →  Royals away, Astros home
      "Boston Celtics v Denver Nuggets"        →  Celtics away, Nuggets home
    Returns ("", "") when the name can't be split.
    """
    for sep in (" @ ", " at ", " v ", " vs ", " VS "):
        if sep in name:
            parts = name.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return "", ""


def _fd_ingest_response(data: object, events: dict) -> None:
    """
    Walk one deserialized FanDuel API response and update *events* in place.

    *events* maps str(eventId) →
        {"home", "away", "ml_h", "ml_a", "spread", "total", "status"}

    Handles two confirmed response shapes:
      1. event-page / content-managed-page:
            {"attachments": {"events": {…}, "markets": {…}}}
      2. navigation/facet: walked but rarely contains odds — captured for
            team names only.
    """
    if not isinstance(data, dict):
        return
    attachments = data.get("attachments") or {}

    # ── Event metadata — extract team names from event.name ──────────────
    raw_events = attachments.get("events") or {}
    if isinstance(raw_events, dict):
        for eid_str, ev in raw_events.items():
            entry = events.setdefault(str(eid_str), {
                "home": "", "away": "",
                "ml_h": None, "ml_a": None,
                "spread": "N/A", "total": "N/A",
                "status": "Scheduled",
            })
            if not entry["home"]:
                name = ev.get("name") or ev.get("eventName") or ""
                away, home = _fd_parse_event_name(name)
                if away:
                    entry["away"] = away
                if home:
                    entry["home"] = home
            status_raw = (ev.get("inPlay") and "In Progress") or                          ev.get("eventStatus") or ""
            if status_raw:
                entry["status"] = status_raw

    # ── Markets — extract ML / spread / total odds ───────────────────────
    raw_markets = attachments.get("markets") or {}
    if not isinstance(raw_markets, dict):
        return
    for mkt_id, mkt in raw_markets.items():
        mkt_type = mkt.get("marketType", "")
        if mkt_type not in _FD_GL_MARKET_TYPES:
            continue
        eid_str = str(mkt.get("eventId", ""))
        if not eid_str:
            continue
        entry = events.setdefault(eid_str, {
            "home": "", "away": "",
            "ml_h": None, "ml_a": None,
            "spread": "N/A", "total": "N/A",
            "status": "Scheduled",
        })
        runners = mkt.get("runners") or []

        if mkt_type == "MONEY_LINE":
            # FanDuel ML runners: index 0 = away, index 1 = home.
            # Confirmed from real DevTools captures (docstring above).
            for idx, runner in enumerate(runners[:2]):
                am    = _fd_american_odds(runner)
                rname = runner.get("runnerName", "")
                if idx == 0:
                    if am is not None:
                        entry["ml_a"] = am
                    if not entry["away"] and rname:
                        entry["away"] = rname
                else:
                    if am is not None:
                        entry["ml_h"] = am
                    if not entry["home"] and rname:
                        entry["home"] = rname

        elif mkt_type in ("MATCH_HANDICAP_(2-WAY)", "RUN_LINE", "PUCK_LINE"):
            for runner in runners:
                hcap  = runner.get("handicap") or 0
                rname = runner.get("runnerName", "")
                # Favourite carries the negative handicap
                if hcap < 0:
                    entry["spread"] = f"{rname} {hcap:+.1f}"

        elif mkt_type in (
            "TOTAL_POINTS_(OVER/UNDER)",
            "TOTAL_RUNS_(OVER/UNDER)",
            "TOTAL_GOALS_(OVER/UNDER)",
        ):
            # Both runners share the same handicap value — just read the first
            for runner in runners:
                hcap = runner.get("handicap")
                if hcap is not None:
                    try:
                        entry["total"] = float(hcap)
                    except (TypeError, ValueError):
                        pass
                    break


def fetch_fanduel_game_lines_playwright(sport: str) -> list:
    """
    Fetch FanDuel game lines (ML / spread / total) using headed Playwright Chromium.

    Why Playwright instead of curl_cffi?
    FanDuel's PerimeterX protection blocks every static HTTP request that
    doesn't carry a freshly-generated x-px-context session token.  The token
    is produced by a real browser's JS challenge and expires in minutes.
    Rather than harvesting and rotating it externally, this function launches a
    real headed Chromium session — PerimeterX runs inside the browser and signs
    every XHR the browser makes automatically.  We intercept those XHR
    responses and parse the odds from them.

    Automation masking:
      --disable-blink-features=AutomationControlled  (Chrome flag)
      navigator.webdriver = undefined                (JS override via add_init_script)
      window.chrome, navigator.plugins, navigator.languages spoofed

    Headless mode:
      Defaults to headed (headless=False) which passes PerimeterX more reliably.
      Set env var FANDUEL_HEADLESS=1 to force headless on hosts without a display
      (Streamlit Cloud, CI).  The function also falls back to headless=True
      automatically if the headed launch raises an exception (e.g. no $DISPLAY).

    Returns:
        List of game dicts compatible with fetch_game_lines() output shape:
        [{"Matchup": "AWAY @ HOME", "Home ML": str, "Away ML": str,
          "Spread": str, "Total": float|str, "Odds Source": "FanDuel",
          "Status": str, "Sport": str}]
        Returns [] on import error, unsupported sport, or any fetch failure.
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as _PWTimeout
    except ImportError:
        log_error_to_session(
            "fetch_fanduel_game_lines_playwright",
            "playwright not installed — pip install playwright && playwright install chromium",
            "warning",
        )
        return []

    sport_path = _FD_SPORT_URL_PATHS.get(sport.upper())
    if not sport_path:
        return []

    # 30-minute cache — Playwright launch is expensive; skip on re-renders
    cache_path = os.path.join(CACHE_DIR, f"fanduel_gl_playwright_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 30:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    events: dict = {}   # str(eventId) → partial game dict

    def _on_response(response):
        url = response.url
        # Only intercept FanDuel API domains — ignore CDN, analytics, ads
        if not any(d in url for d in (
            "api.sportsbook.fanduel.com",
            "sbapi.fanduel.com",
            ".sportsbook.fanduel.com/api",
        )):
            return
        if response.status != 200:
            return
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            _fd_ingest_response(response.json(), events)
        except Exception:
            pass  # malformed response — skip silently

    games = []
    try:
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ]
            headless = bool(os.environ.get("FANDUEL_HEADLESS", ""))
            try:
                browser = pw.chromium.launch(headless=headless, args=launch_args)
            except Exception:
                # No display available — fall back to headless
                browser = pw.chromium.launch(headless=True, args=launch_args)

            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 720},
            )

            # Mask automation fingerprints that PerimeterX inspects
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = ctx.new_page()
            page.on("response", _on_response)

            target_url = f"https://www.fanduel.com/sports/{sport_path}"
            try:
                page.goto(target_url, wait_until="networkidle", timeout=60_000)
            except _PWTimeout:
                # networkidle can time out on heavy pages — DOM is loaded, XHR
                # calls may still be in-flight; the 5s dwell below catches them
                pass
            except Exception:
                pass

            # Dwell to capture deferred XHR calls that fire after initial paint
            time.sleep(5)
            ctx.close()
            browser.close()

        def _fmt_ml(val):
            if val is None:
                return "N/A"
            return f"+{val}" if val > 0 else str(val)

        games = [
            {
                "Matchup":     f"{ev['away']} @ {ev['home']}",
                "Status":      ev.get("status", "Scheduled"),
                "Home ML":     _fmt_ml(ev.get("ml_h")),
                "Away ML":     _fmt_ml(ev.get("ml_a")),
                "Spread":      ev.get("spread", "N/A"),
                "Total":       ev.get("total", "N/A"),
                "Odds Source": "FanDuel",
                "Sport":       sport,
            }
            for ev in events.values()
            if ev.get("home") and ev.get("away")
        ]

    except Exception as _e:
        log_error_to_session(
            "fetch_fanduel_game_lines_playwright", str(_e)[:150], "warning"
        )
        return []

    if games:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(games, f)
        except OSError:
            pass

    return games



# FanDuel player-props URL tab mapping (sport → tab-specific path fragment)
_FD_PROPS_TAB_PATHS = {
    "MLB":  "baseball?tab=player-props",
    "NBA":  "basketball/nba?tab=player-props",
    "NFL":  "football/nfl?tab=player-props",
    "NHL":  "hockey/nhl?tab=player-props",
    "WNBA": "basketball/wnba?tab=player-props",
}


def fetch_fanduel_props_playwright(sport: str) -> list:
    """
    Fetch FanDuel player props using headed Playwright Chromium.

    Extends the fetch_fanduel_game_lines_playwright() pattern to the
    player-props tab.  The same PerimeterX protection applies, so we
    drive a real browser session.  We navigate to the sport's
    player-props tab URL and intercept JSON responses from
    api.sportsbook.fanduel.com.

    Parser looks for responses that carry a "markets" array where the
    market type or description suggests a player prop — specifically:
      - marketType not in the game-line whitelist (_FD_GL_MARKET_TYPES)
      - OR the response URL path contains "player" or "sgp"
      - OR the market description contains a player name pattern

    Returns list of BetCouncil standard prop dicts:
      {Player, Prop, Line, Over, Under, Sport, Book, source}
    Returns [] on import error, unsupported sport, or any failure.
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as _PWTimeout
    except ImportError:
        log_error_to_session(
            "fetch_fanduel_props_playwright",
            "playwright not installed — pip install playwright && playwright install chromium",
            "warning",
        )
        return []

    tab_path = _FD_PROPS_TAB_PATHS.get(sport.upper())
    if not tab_path:
        return []

    # 30-minute cache
    cache_path = os.path.join(CACHE_DIR, f"fanduel_props_playwright_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 30:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    props: list = []
    seen_keys: set = set()

    def _ingest_fd_props(data: dict, source_url: str):
        """Parse a FanDuel API response for player prop markets."""
        # Determine if this response is props-relevant
        url_is_props = any(
            kw in source_url.lower()
            for kw in ("player", "sgp", "prop", "participant")
        )

        markets = []
        # Shape 1: top-level "markets" list (offers endpoint)
        if "markets" in data:
            markets = data["markets"]
        # Shape 2: nested under "attachments" → "markets"
        attachments = data.get("attachments") or {}
        if "markets" in attachments:
            markets.extend(attachments["markets"].values()
                           if isinstance(attachments["markets"], dict)
                           else attachments["markets"])

        for mkt in markets:
            if not isinstance(mkt, dict):
                continue
            mkt_type = mkt.get("marketType") or mkt.get("bettingType") or ""
            mkt_desc = mkt.get("marketName") or mkt.get("description") or ""

            # Skip game-line markets unless the URL explicitly says props
            if not url_is_props and mkt_type in _FD_GL_MARKET_TYPES:
                continue

            runners = (
                mkt.get("runners")
                or mkt.get("selections")
                or mkt.get("outcomes")
                or []
            )
            for runner in runners:
                if not isinstance(runner, dict):
                    continue

                runner_name = (
                    runner.get("runnerName")
                    or runner.get("selectionName")
                    or runner.get("description")
                    or ""
                ).strip()
                handicap = runner.get("handicap") or runner.get("line")
                win_run_line = runner.get("winRunLine") or runner.get("spreadLine")

                line_raw = handicap if handicap is not None else win_run_line
                try:
                    line = float(str(line_raw).replace("+", "")) if line_raw is not None else None
                except (ValueError, TypeError):
                    line = None

                # FanDuel runners for props: runnerName = "Over 1.5" or "Nicky Lopez Over"
                # We need player name and direction separately
                import re as _re
                over_m = _re.search(r"(over|under)\s*([\d.]+)", runner_name, _re.I)
                if over_m:
                    direction = over_m.group(1).capitalize()
                    if line is None:
                        try:
                            line = float(over_m.group(2))
                        except (ValueError, TypeError):
                            pass
                    player = runner_name[:over_m.start()].strip(" -–")
                else:
                    direction = "Over"
                    player = runner_name

                if not player or line is None:
                    continue

                # Odds
                prices = runner.get("winRunnerOdds") or runner.get("currentPrices") or {}
                if isinstance(prices, dict):
                    american = prices.get("americanDisplayOdds") or prices.get("american") or "—"
                else:
                    american = "—"

                key = (player, mkt_desc, line, direction)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                props.append({
                    "Player": player,
                    "Prop":   mkt_desc,
                    "Line":   line,
                    "Over":   str(american) if direction == "Over" else "—",
                    "Under":  str(american) if direction == "Under" else "—",
                    "Sport":  sport.upper(),
                    "Book":   "FanDuel",
                    "source": "fanduel_props_playwright",
                })

    def _on_response(response):
        url = response.url
        if not any(d in url for d in (
            "api.sportsbook.fanduel.com",
            "sbapi.fanduel.com",
            ".sportsbook.fanduel.com/api",
        )):
            return
        if response.status != 200:
            return
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            _ingest_fd_props(response.json(), url)
        except Exception:
            pass

    try:
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ]
            headless = bool(os.environ.get("FANDUEL_HEADLESS", ""))
            try:
                browser = pw.chromium.launch(headless=headless, args=launch_args)
            except Exception:
                browser = pw.chromium.launch(headless=True, args=launch_args)

            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 720},
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = ctx.new_page()
            page.on("response", _on_response)

            target_url = f"https://sportsbook.fanduel.com/{tab_path}"
            try:
                page.goto(target_url, wait_until="networkidle", timeout=60_000)
            except _PWTimeout:
                pass
            except Exception:
                pass

            # Dwell to capture deferred XHR calls after initial paint
            time.sleep(5)
            ctx.close()
            browser.close()

    except Exception as _e:
        log_error_to_session(
            "fetch_fanduel_props_playwright", str(_e)[:150], "warning"
        )
        return []

    if props:
        try:
            with open(cache_path, "wb") as _f:
                pickle.dump(props, _f)
        except OSError:
            pass

    return props


def record_clv(lock, current_props):
    player = lock.get("player", "")
    prop = lock.get("prop", "")
    locked_line = lock.get("line", 0)
    side = lock.get("side", "OVER")
    current_line = None
    for p in current_props:
        if (normalize_name(p.get("Player","")) == normalize_name(player) and p.get("Prop","") == prop):
            current_line = p.get("Line")
            break
    if current_line is None:
        return None
    clv = locked_line - current_line if side == "OVER" else current_line - locked_line
    clv_data = load_json_data(CLV_PATH, [])
    clv_data.append({
        "player": player, "prop": prop,
        "locked_line": locked_line, "closing_line": current_line,
        "side": side, "clv": round(clv, 1),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sport": lock.get("sport", ""), "tier": lock.get("tier", ""),
        "source": lock.get("source", lock.get("book", "")),
    })
    save_json_data(CLV_PATH, clv_data)
    return round(clv, 1)

def record_pinnacle_game_line(lock, pinnacle_lines):
    """
    Game-line counterpart to record_pinnacle_line() — that one matches on
    Player+Prop against prop data, which doesn't fit a game lock (its
    "player" field holds the matchup string, e.g. "Lakers @ Celtics", and
    "prop" holds SPREAD/TOTAL/ML/ALT LINE). This matches on matchup instead,
    against fetch_pinnacle_game_lines() output (st.session_state
    "pinnacle_game_lines"), and writes to the same PINNACLE_LINES_PATH so
    the Pinnacle CLV Tracker reflects both props and game lines together.
    Returns the CLV value, or None if no Pinnacle line was found (e.g. off
    Streamlit Cloud's network, where Pinnacle's guest API is unreachable).
    """
    matchup   = lock.get("player", "")
    prop_lbl  = lock.get("prop", "")
    side      = lock.get("side", "")
    try:
        locked_line = float(str(lock.get("line", 0)).replace("+",""))
    except (ValueError, TypeError):
        return None
    if not matchup or not pinnacle_lines:
        return None

    pin_game = next(
        (g for g in pinnacle_lines
         if normalize_name(g.get("Matchup","")) == normalize_name(matchup)
         or normalize_name(matchup) in normalize_name(g.get("Matchup",""))),
        None
    )
    if not pin_game:
        return None

    pinnacle_line = None
    if prop_lbl == "SPREAD":
        pinnacle_line = pin_game.get("Spread")
    elif prop_lbl in ("TOTAL", "ALT LINE"):
        pinnacle_line = pin_game.get("Total")
    elif prop_lbl == "ML":
        # ML lock stores an implied-line proxy, not a point spread — CLV on
        # moneyline is normally price movement, not line movement, so this
        # is skipped rather than computing a misleading number.
        return None
    if pinnacle_line is None:
        return None

    try:
        pinnacle_line = float(pinnacle_line)
    except (ValueError, TypeError):
        return None

    clv = (locked_line - pinnacle_line) if "OVER" in side.upper() or "HOME" in side.upper() else (pinnacle_line - locked_line)
    record = {
        "player": matchup, "prop": prop_lbl,
        "locked_line": locked_line, "pinnacle_line": pinnacle_line,
        "pinnacle_clv": round(clv, 1), "side": side,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sport": lock.get("sport", ""), "tier": lock.get("tier", ""),
        "positive": clv > 0, "bet_type": "game",
    }
    existing = load_from_gist("pinnacle_lines", None)
    if existing is None:
        existing = load_json_data(PINNACLE_LINES_PATH, [])
    existing.append(record)
    save_json_data(PINNACLE_LINES_PATH, existing)
    save_to_gist("pinnacle_lines", existing)
    return round(clv, 1)


def record_pinnacle_line(lock, props_data):
    player = lock.get("player", "")
    prop = lock.get("prop", "")
    side = lock.get("side", "OVER")
    locked_line = lock.get("line", 0)
    pinnacle_line = None
    for p in props_data:
        p_source = p.get("source", "")
        if "pinnacle" not in p_source.lower():
            continue
        if (normalize_name(p.get("Player", "")) != normalize_name(player)):
            continue
        if p.get("Prop", "") != prop:
            continue
        pinnacle_line = p.get("Line")
        break
    if pinnacle_line is None:
        return None
    if side == "OVER":
        pinnacle_clv = locked_line - pinnacle_line
    else:
        pinnacle_clv = pinnacle_line - locked_line
    record = {
        "player": player,
        "prop": prop,
        "locked_line": locked_line,
        "pinnacle_line": float(pinnacle_line),
        "pinnacle_clv": round(pinnacle_clv, 1),
        "side": side,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sport": lock.get("sport", ""),
        "tier": lock.get("tier", ""),
        "positive": pinnacle_clv > 0,
    }
    existing = load_from_gist("pinnacle_lines", None)
    if existing is None:
        existing = load_json_data(PINNACLE_LINES_PATH, [])
    existing.append(record)
    save_json_data(PINNACLE_LINES_PATH, existing)
    save_to_gist("pinnacle_lines", existing)
    return round(pinnacle_clv, 1)

def get_nfl_weather(team_abbr):
    """Get weather for an NFL game based on stadium location."""
    stadium = NFL_OUTDOOR_STADIUMS.get(team_abbr)
    if not stadium:
        return None
    lat, lon, is_outdoor = stadium
    if not is_outdoor:
        return None  # Dome — weather irrelevant
    city = f"{lat},{lon}"
    return fetch_weather_for_game(city, is_outdoor=True)

def _fetch_nws_weather(city):
    """National Weather Service fallback — free, no key, US only."""
    try:
        # Map city to MLB team coords
        city_upper = city.upper().replace(" ", "")
        coords = None
        for abbr, latlon in MLB_STADIUM_COORDS.items():
            if abbr in city_upper or city_upper in abbr:
                coords = latlon
                break
        if not coords:
            return None
        lat, lon = coords
        # NWS points endpoint
        points_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
        r1 = _http.get(points_url, headers={"User-Agent": "BetCouncil/1.0"}, timeout=8)
        if r1.status_code != 200:
            return None
        forecast_url = r1.json().get("properties", {}).get("forecastHourly")
        if not forecast_url:
            return None
        r2 = _http.get(forecast_url, headers={"User-Agent": "BetCouncil/1.0"}, timeout=8)
        if r2.status_code != 200:
            return None
        periods = r2.json().get("properties", {}).get("periods", [])
        if not periods:
            return None
        p = periods[0]
        # Convert wind direction string to 16-point
        wind_str = p.get("windDirection", "N")
        wind_spd_str = p.get("windSpeed", "0 mph")
        try:
            wind_mph = int(wind_spd_str.split()[0])
        except (ValueError, KeyError, TypeError):
            wind_mph = 0
        temp_f = int(p.get("temperature", 70))
        return {
            "city": city, "wind_speed_mph": wind_mph,
            "wind_dir": wind_str, "temp_f": temp_f,
            "humidity": 50,  # NWS hourly doesn't always include humidity
            "fetched_at": datetime.now().strftime("%H:%M"),
            "source": "NWS",
        }
    except (ValueError, KeyError, TypeError):
        return None

def fetch_weather_for_game(city, is_outdoor=True, team_abbrev=None):
    if not is_outdoor:
        return None
    cache_key = hashlib.md5(f"weather_{city}_{date.today()}".encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}_weather.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 3:
            return _safe_load_pkl(cache_path)
    weather = None
    # Tier 0: LineStar GetFastUpdateV2 (2026-07) -- real per-game weather tied
    # to the actual matchup, rather than a city-name lookup. Falls through
    # silently to wttr.in/NWS below if the harvester hasn't run yet, the Gist
    # data is stale, or the team can't be matched.
    if team_abbrev:
        try:
            _ls_data, _ls_src = fetch_weather_from_gist("MLB")
            if _ls_data:
                _ls_wx = get_linestar_game_weather(_ls_data, team_abbrev)
                if _ls_wx:
                    weather = _ls_wx
        except Exception:
            pass
    # Tier 1: wttr.in (only if LineStar didn't already supply real per-game weather)
    if weather is None:
        try:
            url = f"https://wttr.in/{city.replace(' ', '+')}?format=j1"
            resp = _http.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                weather = {"city": city, "wind_speed_mph": int(current.get("windspeedMiles", 0)),
                           "wind_dir": current.get("winddir16Point", "N"), "temp_f": int(current.get("temp_F", 70)),
                           "humidity": int(current.get("humidity", 50)), "fetched_at": datetime.now().strftime("%H:%M"),
                           "source": "wttr.in"}
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    # Tier 2: NWS fallback
    if weather is None:
        weather = _fetch_nws_weather(city)
    if weather:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(weather, f)
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    return weather

def fetch_fantasylabs_lineups(sport="MLB"):
    """
    Fetch FantasyLabs confirmed lineups from public CloudFront endpoint.
    Requires Referer: https://www.fantasylabs.com/ header — confirmed working.
    
    Supports: MLB, NBA, NFL, NHL, WNBA
    URL: d3ttxfuywgi7br.cloudfront.net/fantasy/{sport}/lineups/{M}_{D}_{YYYY}/default.json
    
    Use STRICTLY for lineup confirmation — not projections.
    """
    sport_slug = FL_SPORT_MAP.get(sport, sport.lower())
    today = date.today()
    m, d, y = today.month, today.day, today.year
    url = f"https://d3ttxfuywgi7br.cloudfront.net/fantasy/{sport_slug}/lineups/{m}_{d}_{y}/default.json"
    try:
        r = _http.get(url, headers=FL_HEADERS, timeout=10)
        if r.status_code != 200:
            return load_json_data(FANTASYLABS_PATH, {})
        data = r.json()
        if not isinstance(data, list):
            return load_json_data(FANTASYLABS_PATH, {})
        lineups = {}
        for player in data:
            pname = player.get("PlayerName","") or player.get("Name","")
            if not pname:
                continue
            team    = player.get("TeamName","") or player.get("Team","")
            order   = int(player.get("LineupOrder", player.get("BattingOrder", 0)) or 0)
            injury  = player.get("InjuryStatus","") or player.get("Injury","") or "Active"
            active  = injury.strip().lower() in ("active","","none","healthy")
            salaries = {
                "dk": player.get("DraftKingsSalary", player.get("DKSalary", 0)),
                "fd": player.get("FanDuelSalary",    player.get("FDSalary",  0)),
            }
            lineups[normalize_name(pname)] = {
                "player": pname, "team": team,
                "lineup_order": order, "active": active,
                "injury_status": injury, "in_lineup": order > 0,
                "salaries": salaries,
                "fetched_at": datetime.now().strftime("%H:%M"),
            }
        if lineups:
            save_json_data(FANTASYLABS_PATH, lineups)
        return lineups
    except (requests.RequestException, ValueError, KeyError) as e:
        return load_json_data(FANTASYLABS_PATH, {})


def _enrich_pitchers_savant(pitchers: dict) -> dict:
    """
    Pull live FIP, xFIP, xwOBA allowed, K%, BB% for each probable pitcher
    from the Baseball Savant / MLB Stats API season stat endpoint.
    Updates each pitcher dict in-place; falls back to static config values
    if the network call fails or a pitcher isn't found.

    Endpoint: statsapi.mlb.com/api/v1/people/{id}/stats?stats=season&group=pitching
    Returns enriched pitchers dict.
    """
    season = date.today().year
    enriched = dict(pitchers)
    seen_ids = {}  # pitcher_id -> stats, avoid duplicate fetches for same SP

    for team, pdata in pitchers.items():
        pid = pdata.get("pitcher_id")
        pname = pdata.get("pitcher", "")
        if not pid:
            continue
        if pid in seen_ids:
            enriched[team].update(seen_ids[pid])
            continue
        try:
            url = (
                f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
                f"?stats=season&group=pitching&season={season}"
            )
            resp = _http.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            splits = resp.json().get("stats", [{}])[0].get("splits", [])
            if not splits:
                continue
            s = splits[0].get("stat", {})
            era  = float(s.get("era",  MLB_PITCHER_ERA.get(pname,  LEAGUE_AVG_ERA)))
            fip  = float(s.get("fielding_independent_pitching",
                               MLB_PITCHER_FIP.get(pname, era)))
            k9   = float(s.get("strikeoutsPer9Inn", 0) or 0)
            bb9  = float(s.get("walksPer9Inn",      0) or 0)
            whip = float(s.get("whip",              1.30) or 1.30)
            xfip = round(fip * 0.92 + bb9 * 0.05, 2)
            live_stats = {
                "era_live":   round(era,  2),
                "fip_live":   round(fip,  2),
                "xfip_live":  xfip,
                "k9_live":    round(k9,   1),
                "bb9_live":   round(bb9,  1),
                "whip_live":  round(whip, 2),
            }
            enriched[team].update(live_stats)
            seen_ids[pid] = live_stats
        except Exception:
            pass
    return enriched




# ── Additional functions from app.py needed by fetchers ──

def _ev_do_refresh(refresh_token):
    """Exchange refresh_token for a new access_token via Supabase auth API."""
    try:
        r = _http.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey":        SUPABASE_ANON,
                "Content-Type":  "application/json",
            },
            json={"refresh_token": refresh_token},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return {
                "access_token":  data.get("access_token"),
                "expires_at":    data.get("expires_at", 0),
                "refresh_token": data.get("refresh_token", refresh_token),
            }
    except Exception:
        pass
    return None

def _ev_refresh_token():
    """
    Retrieve the EVSharps Supabase refresh token from st.secrets.
    Set once in Streamlit Cloud → Settings → Secrets:
      EV_REFRESH_TOKEN = "z325a7doims5"
    This never expires (until explicitly revoked).
    """
    try:
        return (st.secrets.get("EV_REFRESH_TOKEN")
                or st.secrets.get("ev_refresh_token"))
    except Exception:
        return None

@st.cache_data(ttl=1800)

@st.cache_data(ttl=3600)

def get_api_counter(counter_path):
    """
    Reads the API usage counter for a given budget. Gist-backed (same
    pattern as signal_performance/injury_performance) so the count survives
    Streamlit Cloud redeploys — previously this only lived in local
    CACHE_DIR, which wipes on every redeploy, so the 80% hard-stop in
    api_budget_check() never actually triggered: the app always thought it
    was starting fresh while real upstream usage (e.g. The Odds API) kept
    climbing across redeploys. Confirmed via real usage hitting 498/500
    monthly credits despite the supposed 400/500 stop.
    """
    today = date.today().strftime("%Y-%m-%d")
    current_month = date.today().strftime("%Y-%m")
    data_type = os.path.basename(counter_path).replace(".json", "")
    # Use session_state as in-memory cache to avoid Gist/disk reads on every budget check
    _ss_key = f"_api_counter_{counter_path}"
    cached = st.session_state.get(_ss_key)
    if cached and cached.get("date") == today and cached.get("month") == current_month:
        return cached

    counter = None
    gist_counter = load_from_gist(data_type, None)
    if isinstance(gist_counter, dict) and "count" in gist_counter:
        counter = gist_counter
    elif os.path.exists(counter_path):
        try:
            with open(counter_path, "r") as f:
                counter = json.load(f)
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            counter = None

    if counter is None:
        counter = {"count": 0, "date": today, "month": current_month, "monthly_count": 0}
    else:
        if counter.get("date") != today:
            counter["date"] = today
            counter["count"] = 0
        if counter.get("month") != current_month:
            counter["month"] = current_month
            counter["monthly_count"] = 0

    st.session_state[_ss_key] = counter
    return counter

def increment_api_counter(counter_path, amount=1):
    counter = get_api_counter(counter_path)
    counter["count"] += amount
    counter["monthly_count"] = counter.get("monthly_count", 0) + amount
    save_json_data(counter_path, counter)  # local fallback, kept for same-session reads
    data_type = os.path.basename(counter_path).replace(".json", "")
    save_to_gist(data_type, counter)  # the persistence that actually survives redeploys
    # Refresh session cache with updated count
    st.session_state[f"_api_counter_{counter_path}"] = counter
    return counter

# ── Gist batch-write constants (mirrors app.py module-level globals) ────────
_GIST_BATCH_WINDOW   = 5.0   # seconds — flush after this many seconds of queued writes
_GIST_CRITICAL_KEYS  = frozenset({"history", "bankroll", "signal_performance", "injury_performance", "locks"})
# "locks" added 2026-07 — kept in sync with app.py's copy of this constant.
# See app.py's _GIST_CRITICAL_KEYS comment for why: a queued (non-critical)
# "locks" write could be lost if the session ended before the batch window
# flushed, letting settled slips reappear after Win/Loss/Void.


def _flush_batch_gist(dirty, now=None):
    """Write all queued dirty keys in a single GitHub Gist PATCH request."""
    if not dirty or not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return not dirty
    now = now or time.time()
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}",
                   "Accept": "application/vnd.github.v3+json"}
        files = {
            f"betcouncil_{k}.json": {"content": json.dumps(v, indent=2)}
            for k, v in dirty.items()
        }
        resp = _http.patch(
            f"{GIST_API}/{GITHUB_GIST_ID}",
            headers=headers,
            json={"files": files},
            timeout=15,
        )
        if resp.status_code == 200:
            if "gist_last_write" not in st.session_state:
                st.session_state["gist_last_write"] = {}
            for k in list(dirty.keys()):
                st.session_state["gist_last_write"][k] = now
            st.session_state["gist_dirty"].clear()
            st.session_state["gist_batch_start"] = now
        return resp.status_code == 200
    except (requests.RequestException, json.JSONDecodeError, OSError):
        return False


def save_to_gist(data_type, data):
    """
    Batched Gist writer — marks data as dirty and flushes once per batch window.

    Non-critical writes (locks, props, etc.) are queued for up to
    _GIST_BATCH_WINDOW seconds. When a critical write arrives, OR when the
    window expires, ALL dirty keys are flushed in a SINGLE Gist PATCH request.
    This replaces the previous per-key PATCH pattern and reduces API calls
    proportionally to the number of keys written together.
    """
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return False
    if "gist_dirty" not in st.session_state:
        st.session_state["gist_dirty"] = {}
    if "gist_last_write" not in st.session_state:
        st.session_state["gist_last_write"] = {}
    # Mark dirty
    st.session_state["gist_dirty"][data_type] = data
    now = time.time()
    # Open a new batch window the first time a key goes dirty
    if "gist_batch_start" not in st.session_state:
        st.session_state["gist_batch_start"] = now
    batch_age = now - st.session_state.get("gist_batch_start", now)
    is_critical = data_type in _GIST_CRITICAL_KEYS
    # Flush ALL dirty keys in one PATCH when:
    #   (a) a critical key was just written — don't delay history/bankroll
    #   (b) the batch window has expired — coalesce whatever accumulated
    if is_critical or batch_age >= _GIST_BATCH_WINDOW:
        return _flush_batch_gist(st.session_state["gist_dirty"], now)
    # Still within window — stay queued
    return True

# ── Functions migrated from app.py — needed by fetchers.py ──

def _espn_get(url, cache_key, ttl_hours=12):
    """Shared ESPN fetch with file cache. Returns parsed JSON or None."""
    cache_path = os.path.join(CACHE_DIR, f"espn_{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < ttl_hours:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass
    try:
        resp = _http.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            # Previously silent -- a 404/403/etc from ESPN left zero
            # diagnostic trail, making live-data failures indistinguishable
            # from "no data exists". Log it so it's actually visible.
            st.session_state.setdefault("errors", []).append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "source": f"espn_get:{cache_key}",
                "error": f"HTTP {resp.status_code}: {resp.text[:150]}",
                "url": url,
            })
            return None
        data = resp.json()
        with open(cache_path, "wb") as f:
            pickle.dump(data, f)
        return data
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": f"espn_get:{cache_key}", "error": str(e)[:150],
            "url": url,
        })
        return None




# ── Tennis signal engine ──────────────────────────────────────────────────────
# Surface baselines: expected total games per match (both players combined)
# Best-of-3 format (most ATP/WTA events and all WTA Slams)


# Maps GEM/PrizePicks-style prop names to Parlay Savant's URL prop slugs (MLB)

def _ev_auth_headers():
    """Build auth headers for EVSharps authenticated endpoints."""
    jwt = _get_ev_jwt()
    h = {
        "accept": "*/*",
        "origin": "https://www.evsharps.com",
        "referer": "https://www.evsharps.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    }
    if jwt:
        h["authorization"] = f"Bearer {jwt}"
    return h

@st.cache_data(ttl=1800)

def _get_ev_jwt():
    """
    Returns a valid EVSharps JWT, auto-refreshing when expired.
    Priority:
      1. In-memory cache (valid for remaining session)
      2. Auto-refresh via EV_REFRESH_TOKEN secret (hands-free)
      3. Fallback to EV_JWT secret (manual — legacy)
    """
    import time as _time
    now = _time.time()

    # 1. Cached token still valid (refresh 5min before expiry)
    if _EV_TOKEN_CACHE["access_token"] and _EV_TOKEN_CACHE["expires_at"] > now + 300:
        return _EV_TOKEN_CACHE["access_token"]

    # 2. Auto-refresh using refresh_token
    refresh_tok = _ev_refresh_token()
    if refresh_tok:
        new_tokens = _ev_do_refresh(refresh_tok)
        if new_tokens and new_tokens.get("access_token"):
            _EV_TOKEN_CACHE["access_token"] = new_tokens["access_token"]
            _EV_TOKEN_CACHE["expires_at"]   = new_tokens["expires_at"]
            # Update refresh token in cache if rotated
            if new_tokens.get("refresh_token") != refresh_tok:
                # Log rotation — user may need to update secret eventually
                log_error_to_session("ev_jwt_refresh", "Refresh token rotated — update EV_REFRESH_TOKEN secret", "warning")
            return _EV_TOKEN_CACHE["access_token"]

    # 3. Manual fallback
    try:
        return st.secrets.get("EV_JWT") or st.secrets.get("ev_jwt")
    except Exception:
        return None

def _get_fanduel_px_context():
    """Shared PerimeterX token lookup — secrets, then Gist (harvester push),
    then short-lived local cache. Used by both fetch_fanduel_direct and
    fetch_fanduel_event_ids so the chain only lives in one place."""
    px_context = ""
    try:
        px_context = st.secrets.get("FANDUEL_PX_CONTEXT", "")
    except Exception:
        pass
    if not px_context:
        # Picks up tokens pushed by fanduel-harvester-cdp.js (local Playwright
        # tool, CDP-attached to an already-logged-in browser). A forensic test
        # on 2026-06-21 found the x-px-context token on the PRICING domain
        # (smp.{state}.sportsbook.fanduel.com, which getMarketPrices actually
        # uses) held ONE value across 15+ requests over a 90-second window —
        # this contradicts the original "expires within minutes" assumption.
        # True long-term lifespan is still unconfirmed, so the freshness
        # window here is a cautious guess (20 min), not a verified figure.
        gist_tokens = load_from_gist("fanduel_tokens", None)
        if gist_tokens:
            try:
                captured_at = gist_tokens.get("captured_at", "")
                age_mins = (time.time() - datetime.fromisoformat(captured_at.replace("Z", "+00:00")).timestamp()) / 60
            except (ValueError, TypeError):
                age_mins = 9999
            if age_mins < 20:
                px_context = gist_tokens.get("px_context", "")
    if not px_context:
        fd_token_cache = os.path.join(CACHE_DIR, "fanduel_px_context.txt")
        if os.path.exists(fd_token_cache):
            try:
                age_mins = (time.time() - os.path.getmtime(fd_token_cache)) / 60
                if age_mins < 10:
                    with open(fd_token_cache, "r") as f:
                        px_context = f.read().strip()
            except (IOError, OSError):
                pass
    return px_context

def _get_fanduel_state():
    state = "az"
    try:
        state = (st.secrets.get("FANDUEL_STATE", "az") or "az").lower()
    except Exception:
        pass
    return state


# FanDuel competitionId per sport — these are FanDuel-internal IDs required by
# the navigation/facet/v1.0/search endpoint, NOT generic league identifiers.
# MLB, WNBA, NFL confirmed via real DevTools capture 2026-06-21
# (scan.az.sportsbook.fanduel.com/api/sports/navigation/facet/v1.0/search,
# full request/response captured for each). NBA/NHL intentionally left out —
# both seasons just ended in June, nothing to capture until they're back.
# Capture each via the same method (fanduel-navfacet-request-capture.js
# while on that sport's schedule page) once in season — wrong/guessed IDs
# would silently return another sport's events or nothing at all, worse
# than just [].
FANDUEL_COMPETITION_IDS = {
    "MLB": 11196870,
    "WNBA": 11295025,
    "NFL": 12282733,
}

def api_budget_check(budget_key):
    budget = API_BUDGETS.get(budget_key)
    if not budget:
        return True, ""
    counter = get_api_counter(budget["counter_path"])
    daily_used = counter.get("count", 0)
    monthly_used = counter.get("monthly_count", 0)
    stop_pct = budget.get("hard_stop_pct", 0.80)
    daily_limit = budget.get("daily_limit")
    if daily_limit:
        threshold = int(daily_limit * stop_pct)
        if daily_used >= threshold:
            return False, f"{budget_key} daily limit approached: {daily_used}/{daily_limit} — protecting free tier"
    monthly_limit = budget.get("monthly_limit")
    if monthly_limit:
        threshold = int(monthly_limit * stop_pct)
        if monthly_used >= threshold:
            return False, f"{budget_key} monthly limit approached: {monthly_used}/{monthly_limit} — protecting free tier"
    return True, ""

def api_budget_increment(budget_key, amount=1):
    budget = API_BUDGETS.get(budget_key)
    if budget:
        increment_api_counter(budget["counter_path"], amount)

@st.cache_data(ttl=3600)

def load_from_gist(data_type: str, default):
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return None
    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        resp = _http.get(
            f"{GIST_API}/{GITHUB_GIST_ID}",
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            return None
        files = resp.json().get("files", {})
        file_data = files.get(f"betcouncil_{data_type}.json", {})
        content = (file_data.get("content") or "").strip()
        if not content:
            # GitHub's bulk gist response can return empty content for ANY
            # file regardless of that file's own size, once another file in
            # the same gist is large enough to push the total response past
            # GitHub's inline-content limit. Confirmed 2026-06-21: a 405-byte
            # caesars_tokens file came back empty purely because
            # auto_scraped_props.json (2.5MB) sat alongside it in the same
            # gist — every data_type using this function was silently
            # affected, not just the large file. Always fall back to
            # raw_url rather than trusting an empty content field as "no data".
            raw_url = file_data.get("raw_url", "")
            if not raw_url:
                return None
            raw_resp = _http.get(raw_url, headers=headers, timeout=15)
            if raw_resp.status_code != 200:
                return None
            content = raw_resp.text.strip()
            if not content:
                return None
        return json.loads(content)
    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError):
        return None


# load_json_data — moved to bc_utils.py

def log_error_to_session(source, error, error_type="error"):
    """Log errors to session_state so they appear in the System tab."""
    try:
        if "errors" not in st.session_state:
            st.session_state["errors"] = []
        st.session_state["errors"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": source,
            "error": str(error)[:200],
            "type": error_type
        })
        # Cap at 500 entries — trim oldest to prevent unbounded session state growth
        st.session_state["errors"] = st.session_state["errors"][-500:]
    except (KeyError, TypeError, ValueError) as _e:
            print(f"[WARN] {_e}")


# is_date_valid_for_today — moved to bc_utils.py

def scrapeops_get(url: str, headers: dict = None, timeout: int = 20):
    """
    Residential proxy chain for anti-bot protected sites (PrizePicks etc).
    Tries proxies in order until one succeeds:
      1. ScrapeOps    (25k credits/mo — primary paid)
      2. ScraperAPI   (1k free credits/mo — backup)
      3. Scrape.do    (1k free credits/mo — backup)
      4. Direct request (fallback — will 403 on protected sites)
    """
    from urllib.parse import quote

    def _log(proxy, status, size=0, error=None):
        st.session_state.setdefault("scrapeops_log", []).append({
            "url": url[:60], "proxy": proxy,
            "status": status, "size": size,
            "error": str(error)[:60] if error else None,
        })

    def _is_valid(resp):
        ct = resp.headers.get("content-type","")
        return resp.status_code == 200 and "html" not in ct and not resp.text.strip().startswith("<")

    # ��─ 1. ScrapeOps ────────────────────────────────────────
    # Skip if quota exhausted. Checked in two layers: session_state (instant,
    # for repeat calls within this run) then Gist (persists across cold
    # starts/redeploys — without this, every fresh session silently re-pays
    # the full ~20s timeout to rediscover exhaustion that was already known
    # from an earlier session, the same class of bug fixed in load_from_gist
    # on 2026-06-21). Scoped by month since ScrapeOps quota resets monthly.
    _so_exhausted = st.session_state.get("scrapeops_exhausted", False)
    if not _so_exhausted:
        _so_gist = load_from_gist("scrapeops_status", None)
        if _so_gist and _so_gist.get("exhausted") and _so_gist.get("month") == datetime.now().strftime("%Y-%m"):
            _so_exhausted = True
            st.session_state["scrapeops_exhausted"] = True
    if SCRAPEOPS_KEY and not _so_exhausted:
        try:
            encoded = quote(url, safe='')
            r = _HTTP_DIRECT.get(f"https://proxy.scrapeops.io/v1/?api_key={SCRAPEOPS_KEY}&url={encoded}&residential=true&country=us&render_js=false",
                timeout=timeout
            )
            _log("ScrapeOps", r.status_code, len(r.text))
            # 403/429/402 = quota exhausted via status code. Also check for a
            # 200 response carrying a quota-exceeded error body — some proxy
            # APIs return 200 with an error payload rather than a 4xx when
            # credits run out, which would otherwise never trip this check.
            # (Kept in sync with the same fix in app.py's shadowing copy of
            # this function — see note there about the duplication.)
            _quota_phrases = ("insufficient credit", "credit limit", "quota exceeded",
                               "out of credits", "usage limit", "no credits remaining")
            _body_says_exhausted = (
                r.status_code == 200 and
                any(_p in r.text[:500].lower() for _p in _quota_phrases)
            )
            if r.status_code in (403, 429, 402) or _body_says_exhausted:
                st.session_state["scrapeops_exhausted"] = True
                save_to_gist("scrapeops_status", {"exhausted": True, "month": datetime.now().strftime("%Y-%m")})
                _log("ScrapeOps", "QUOTA_EXHAUSTED", error=Exception(f"HTTP {r.status_code}"))
            elif _is_valid(r):
                return r
        except (KeyError, TypeError, ValueError) as e:
            _log("ScrapeOps", "ERR", error=e)

    # ── 2. ScraperAPI ────────────────────────────────────────
    if SCRAPERAPI_KEY:
        try:
            r = _HTTP_DIRECT.get(f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={quote(url, safe='')}&premium=true&country_code=us",
                timeout=timeout
            )
            _log("ScraperAPI", r.status_code, len(r.text))
            if r.status_code in (403, 429, 402):
                st.session_state["scraperapi_exhausted"] = True
            elif _is_valid(r):
                return r
        except (requests.RequestException, KeyError, ValueError) as e:
            _log("ScraperAPI", "ERR", error=e)

    # ── 3. Scrape.do ─────────────────────────────────────────
    if SCRAPEDO_KEY:
        try:
            r = _HTTP_DIRECT.get(f"https://api.scrape.do?token={SCRAPEDO_KEY}&url={quote(url, safe='')}&super=true",
                timeout=timeout
            )
            _log("Scrape.do", r.status_code, len(r.text))
            if _is_valid(r):
                return r
        except (requests.RequestException, KeyError, ValueError) as e:
            _log("Scrape.do", "ERR", error=e)

    # ── 4. Direct (fallback) ─────────────────────────────────
    return _http.get(url, headers=headers or {}, timeout=timeout)


# ═══════════════════════════════════════════════════════════════
# ESPN INJURY + DEPTH CHART FEEDS
# Uses same ESPN infrastructure already trusted by the app.
# Tier 4 injury source + depth chart movement for NFL/NBA/MLB.
# ═══════════════════════════════════════════════════════════════

def fetch_mlb_player_season_avg(player_name: str) -> dict:
    """
    Real per-game season averages from statsapi.mlb.com (same API already
    used elsewhere in this codebase for probable pitchers/lineups).
    Covers both hitters and pitchers, since the same player-lookup call
    site serves both. Returns per-GAME averages (not season totals) for
    the counting stats consumed by fetch_prop_data_avg's stat_map: H, HR,
    RBI, R, SO, TB (hitting), ER, SO, Outs (pitching), plus n_games and
    the two "FS" (fantasy-score-style) combo stats already expected
    downstream. Cached 6h locally -- season stats don't move fast enough
    to justify per-request live calls.
    """
    if not player_name:
        return {}
    cp = os.path.join(CACHE_DIR, f"mlb_season_avg_{normalize_name(player_name)}.pkl")
    if os.path.exists(cp) and (time.time() - os.path.getmtime(cp)) / 60 < 360:
        c = _safe_load_pkl(cp)
        if c is not None:
            return c
    try:
        r = requests.get("https://statsapi.mlb.com/api/v1/people/search",
                          params={"names": player_name}, timeout=10)
        if r.status_code != 200:
            return {}
        people = r.json().get("people", [])
        match = next((p for p in people if normalize_name(p.get("fullName", "")) == normalize_name(player_name)), None)
        if not match and people:
            match = people[0]
        if not match:
            return {}
        pid = match["id"]
        is_pitcher = match.get("primaryPosition", {}).get("abbreviation") == "P"
        group = "pitching" if is_pitcher else "hitting"

        r2 = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",
                           params={"stats": "season", "group": group, "season": datetime.now().year}, timeout=10)
        if r2.status_code != 200:
            return {}
        splits = r2.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            return {}
        stat = splits[0].get("stat", {})
        games = stat.get("gamesPlayed", 0)
        if not games:
            return {}

        result = {"n_games": games}
        if is_pitcher:
            innings_str = str(stat.get("inningsPitched", "0.0"))
            whole, _, frac = innings_str.partition(".")
            outs_total = int(whole or 0) * 3 + int(frac or 0)
            result["ER"] = round(stat.get("earnedRuns", 0) / games, 2)
            result["SO"] = round(stat.get("strikeOuts", 0) / games, 2)
            result["Outs"] = round(outs_total / games, 2)
            result["Pitcher FS"] = round(result["SO"] * 3 - result["ER"] * 2, 2)
        else:
            result["H"] = round(stat.get("hits", 0) / games, 2)
            result["HR"] = round(stat.get("homeRuns", 0) / games, 2)
            result["RBI"] = round(stat.get("rbi", 0) / games, 2)
            result["R"] = round(stat.get("runs", 0) / games, 2)
            result["TB"] = round(stat.get("totalBases", 0) / games, 2)
            result["H+R+RBI"] = round(result["H"] + result["R"] + result["RBI"], 2)
            result["Hitter FS"] = round(result["H"] * 3 + result["R"] * 2 + result["RBI"] * 2 + result["HR"] * 2, 2)

        _safe_save_pkl(cp, result)
        return result
    except Exception:
        return {}


def fetch_mlb_probable_pitchers():
    cache_path = os.path.join(CACHE_DIR, "mlb_pitchers.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 3:
            return _safe_load_pkl(cache_path)
    today_str = date.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?date={today_str}&sportId=1&hydrate=probablePitcher,team"
    pitchers = {}
    try:
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for date_data in resp.json().get("dates", []):
            for game in date_data.get("games", []):
                away = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
                home = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "")
                away_pitcher = game.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("fullName", "")
                home_pitcher = game.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("fullName", "")
                away_pid = game.get("teams", {}).get("away", {}).get("probablePitcher", {}).get("id")
                home_pid = game.get("teams", {}).get("home", {}).get("probablePitcher", {}).get("id")
                if away:
                    pitchers[away] = {"pitcher": away_pitcher, "opponent": home,
                                      "home": False, "pitcher_id": away_pid}
                if home:
                    pitchers[home] = {"pitcher": home_pitcher, "opponent": away,
                                      "home": True, "pitcher_id": home_pid}
        # Enrich with live Savant stats (FIP, xFIP, xwOBA, K%, BB%)
        pitchers = _enrich_pitchers_savant(pitchers)
        if pitchers:
            with open(cache_path, "wb") as f:
                pickle.dump(pitchers, f)
    except (IOError, ValueError):
        pass
    return pitchers

def fetch_team_recent_defense(sport, team_abbrev, n_games=10):
    cache_key = f"recent_def_{sport}_{team_abbrev}_{n_games}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < ROLLING_DEFENSE_CACHE_HOURS:
            return _safe_load_pkl(cache_path)
    if sport != "NBA":
        return None
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/"
    }
    _season_types = ["Playoffs", "Regular+Season"] if date.today().month in (4, 5, 6) else ["Regular+Season"]
    for season_type in _season_types:
        url = f"https://stats.nba.com/stats/teamgamelogs?Season={_current_nba_season_str()}&SeasonType={season_type}&TeamID=&LastNGames={n_games}&MeasureType=Defense&PerMode=PerGame"
        try:
            resp = _http.get(url, headers=nba_headers, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            for row in rows:
                abbrev = row[col.get("TEAM_ABBREVIATION", 0)]
                if abbrev == team_abbrev:
                    def_rtg = row[col.get("DEF_RATING", 0)]
                    opp_pts = row[col.get("OPP_PTS", 0)]
                    result = {"def_rating_recent": def_rtg, "opp_pts_recent": opp_pts, "n_games": n_games, "season_type": season_type, "source": "NBA Stats API"}
                    with open(cache_path, "wb") as f:
                        pickle.dump(result, f)
                    return result
        except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
            continue
    return None

def fetch_espn_fpi_ratings(sport="NBA"):
    cache_path = os.path.join(CACHE_DIR, f"espn_fpi_{sport}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            return _safe_load_pkl(cache_path)
    sport_slug_map = {"NBA": "basketball/nba", "NFL": "football/nfl", "MLB": "baseball/mlb", "NHL": "hockey/nhl"}
    slug = sport_slug_map.get(sport)
    if not slug:
        return {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/{slug}/teams?limit=50"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        teams = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        ratings = {}
        for team_entry in teams:
            team = team_entry.get("team", {})
            abbr = team.get("abbreviation", "")
            if not abbr:
                continue
            records = team.get("record", {}).get("items", [])
            wins = 0
            losses = 0
            for record in records:
                if record.get("type") == "total":
                    for stat in record.get("stats", []):
                        if stat.get("name") == "wins":
                            wins = stat.get("value", 0)
                        elif stat.get("name") == "losses":
                            losses = stat.get("value", 0)
            total_games = wins + losses
            if total_games > 0:
                win_pct = wins / total_games
                power = round(95 + (win_pct * 20), 1)
                ratings[abbr] = power
        if ratings:
            with open(cache_path, "wb") as f:
                pickle.dump(ratings, f)
            return ratings
        return {}
    except (ValueError, TypeError, ZeroDivisionError) as e:
        return {}

def fetch_todays_referees(sport):
    cache_path = os.path.join(CACHE_DIR, f"officials_{sport}_{date.today()}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 6:
            return _safe_load_pkl(cache_path)
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb"}
    path = slug_map.get(sport)
    if not path:
        return {}
    officials = {}
    try:
        today_str = date.today().strftime("%Y%m%d")
        url = f"https://site.web.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={today_str}"
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for event in resp.json().get("events", []):
            matchup = event.get("shortName", "")
            for comp in event.get("competitions", []):
                refs = [o.get("displayName", "") for o in comp.get("officials", []) if o.get("displayName")]
                if refs and matchup:
                    officials[matchup] = refs
        if officials:
            with open(cache_path, "wb") as f:
                pickle.dump(officials, f)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return officials

def fetch_nba_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "nba_rolling_avgs.pkl")
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
        "Connection": "keep-alive",
        "Origin": "https://www.nba.com",
    }
    # Auto-detect current season
    _yr = date.today().year
    _season = f"{_yr-1}-{str(_yr)[2:]}" if date.today().month < 9 else f"{_yr}-{str(_yr+1)[2:]}"
    urls = [
        f"https://stats.nba.com/stats/playergamelogs?Season={_season}&SeasonType=Playoffs&PlayerOrTeam=P&LastNGames=10",
        f"https://stats.nba.com/stats/playergamelogs?Season={_season}&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
    ]
    rolling = {}
    for url in urls:
        try:
            resp = _http.get(url, headers=nba_headers, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            for row in rows:
                player_name = row[col["PLAYER_NAME"]]
                pts = row[col["PTS"]]
                reb = row[col["REB"]]
                ast = row[col["AST"]]
                col_min = col.get("MIN", col.get("E_PACE", None))
                minutes = round(float(row[col_min]), 1) if col_min and row[col_min] else None
                if player_name and pts is not None:
                    pts_val = round(float(pts), 1)
                    reb_val = round(float(reb), 1)
                    ast_val = round(float(ast), 1)
                    rolling[player_name] = {
                        "PTS": pts_val,
                        "REB": reb_val,
                        "AST": ast_val,
                        "PRA": round(pts_val + reb_val + ast_val, 1),
                        "MIN": minutes,
                        "PTS_std": round(pts_val * 0.40, 2) if pts_val > 0 else 4.0,
                        "REB_std": round(reb_val * 0.45, 2) if reb_val > 0 else 1.5,
                        "AST_std": round(ast_val * 0.50, 2) if ast_val > 0 else 1.0,
                        "PRA_std": round((pts_val + reb_val + ast_val) * 0.35, 2),
                    }
            if rolling:
                break
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
                requests.exceptions.RequestException, ValueError, KeyError, TypeError, AttributeError):
            # On timeout — use stale cache instead of crashing board
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "rb") as _cf:
                        return pickle.load(_cf)
                except (requests.RequestException, KeyError, ValueError):
                    pass
            continue
    if not rolling:
        print("[WARN] fetch_nba_rolling_averages: FAILED — likely blocked by hosting")
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling


def fetch_nba_l20_pricer_baseline():
    """
    L20 (last-20-game) rolling averages across all 11 stat types used by
    compute_market_anchored_fair_line (bc_utils.py) — pts/reb/ast/3pm plus
    the combo stats (pa/pr/pra/ra) and stl/blk/tov. Separate from
    fetch_nba_rolling_averages (which is L10, PTS/REB/AST/PRA only, and
    feeds a different part of the app) so that function's callers aren't
    affected by widening this one's stat set or window.
    Cached 6h — L20 averages don't move meaningfully within a day.
    Returns {player_name: {"PTS":.., "REB":.., ..., "TOV":.., "n_games": n}}.
    """
    cache_path = os.path.join(CACHE_DIR, "nba_l20_pricer_baseline.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
        "Connection": "keep-alive",
        "Origin": "https://www.nba.com",
    }
    _yr = date.today().year
    _season = f"{_yr-1}-{str(_yr)[2:]}" if date.today().month < 9 else f"{_yr}-{str(_yr+1)[2:]}"
    urls = [
        f"https://stats.nba.com/stats/playergamelogs?Season={_season}&SeasonType=Playoffs&PlayerOrTeam=P&LastNGames=20",
        f"https://stats.nba.com/stats/playergamelogs?Season={_season}&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=20",
    ]
    baseline = {}
    for url in urls:
        try:
            resp = _http.get(url, headers=nba_headers, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            # NBA Stats playergamelogs at LastNGames=N already returns the
            # N-game AVERAGE per row (not per-game rows) when queried this
            # way, matching the same pattern fetch_nba_rolling_averages
            # relies on for L10 — GP column gives the actual games counted,
            # which may be <20 early in a season or for injury-limited players.
            for row in rows:
                player_name = row[col.get("PLAYER_NAME", -1)] if "PLAYER_NAME" in col else None
                if not player_name:
                    continue
                def _v(key):
                    i = col.get(key)
                    if i is None or row[i] is None:
                        return 0.0
                    try:
                        return float(row[i])
                    except (TypeError, ValueError):
                        return 0.0
                pts, reb, ast = _v("PTS"), _v("REB"), _v("AST")
                fg3m, stl, blk, tov = _v("FG3M"), _v("STL"), _v("BLK"), _v("TOV")
                n_games = int(_v("GP")) if col.get("GP") is not None else 20
                baseline[player_name] = {
                    "PTS": round(pts, 1), "REB": round(reb, 1), "AST": round(ast, 1),
                    "3PM": round(fg3m, 1), "STL": round(stl, 1), "BLK": round(blk, 1),
                    "TOV": round(tov, 1),
                    "PA": round(pts + ast, 1), "PR": round(pts + reb, 1),
                    "PRA": round(pts + reb + ast, 1), "RA": round(reb + ast, 1),
                    "n_games": n_games,
                }
            if baseline:
                break
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
                requests.exceptions.RequestException, ValueError, KeyError, TypeError, AttributeError):
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "rb") as _cf:
                        return pickle.load(_cf)
                except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
                    pass
            continue
    if not baseline:
        print("[WARN] fetch_nba_l20_pricer_baseline: FAILED — likely blocked by hosting")
    if baseline:
        with open(cache_path, "wb") as f:
            pickle.dump(baseline, f)
    return baseline


def fetch_nba_all_player_ids():
    """
    Full active-roster name -> stats.nba.com PersonID lookup via
    commonallplayers. Cached 24h. Avoids hardcoding a short list of star
    players (the ESPN_ATHLETE_IDS map used elsewhere only covers ~15-20
    players/sport) — this covers the full active league.
    """
    cache_path = os.path.join(CACHE_DIR, "nba_all_player_ids.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 24:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
    }
    _yr = date.today().year
    _season = f"{_yr-1}-{str(_yr)[2:]}" if date.today().month < 9 else f"{_yr}-{str(_yr+1)[2:]}"
    url = f"https://stats.nba.com/stats/commonallplayers?LeagueID=00&Season={_season}&IsOnlyCurrentSeason=1"
    try:
        resp = _http.get(url, headers=nba_headers, timeout=12)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        result_set = data.get("resultSets", [{}])[0]
        headers_ = result_set.get("headers", [])
        rows = result_set.get("rowSet", [])
        col = {h: i for i, h in enumerate(headers_)}
        out = {}
        for row in rows:
            name = row[col.get("DISPLAY_FIRST_LAST", 0)]
            pid = row[col.get("PERSON_ID", 0)]
            if name and pid:
                out[name] = pid
        if out:
            _safe_save_pkl(cache_path, out)
        return out
    except Exception as e:
        print(f"[WARN] fetch_nba_all_player_ids: {e}")
        return {}


def fetch_nba_trailing_splits(player_name: str, season: str = None, point_diff: int = 5) -> dict:
    """
    A player's usage/production specifically for stretches when their
    team was trailing by up to `point_diff` points — the NBA-side
    equivalent of "targets while trailing" for NFL. Free, via
    stats.nba.com's own playerdashboardbyclutch endpoint (AheadBehind
    filter), same session/header pattern as fetch_nba_rolling_averages.

    Display/context only — NOT wired into compute_multi_signal_edge.
    Same standard as the LineStar projection panel in Player Lookup:
    would need a backtest against BetCouncil's own outcome history
    before it's trusted to influence edge or Kelly sizing.

    Returns {} if the player isn't found or the request fails —
    callers must treat empty as "not enough data," not "confirmed zero."
    """
    player_ids = fetch_nba_all_player_ids()
    pid = player_ids.get(player_name)
    if not pid:
        # fallback: case-insensitive / partial match
        name_l = player_name.lower()
        pid = next((v for k, v in player_ids.items() if name_l in k.lower()), None)
    if not pid:
        return {}

    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
    }
    if not season:
        _yr = date.today().year
        season = f"{_yr-1}-{str(_yr)[2:]}" if date.today().month < 9 else f"{_yr}-{str(_yr+1)[2:]}"

    url = (
        "https://stats.nba.com/stats/playerdashboardbyclutch"
        f"?PlayerID={pid}&Season={season}&SeasonType=Regular+Season"
        f"&MeasureType=Base&PerMode=PerGame&AheadBehind=Behind&PointDiff={point_diff}"
        "&PaceAdjust=N&PlusMinus=N&Rank=N&LastNGames=0&Month=0&OpponentTeamID=0"
        "&Period=0&SeasonSegment=&VsConference=&VsDivision=&GameSegment=&Location=&Outcome="
    )
    try:
        resp = _http.get(url, headers=nba_headers, timeout=12)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        # "PlayerClutch" result set holds the AheadBehind-filtered row
        for result_set in data.get("resultSets", []):
            headers_ = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers_ or not rows:
                continue
            col = {h: i for i, h in enumerate(headers_)}
            row = rows[0]
            out = {"player": player_name, "season": season, "point_diff": point_diff}
            for field in ["GP", "MIN", "PTS", "REB", "AST", "FGA", "FG_PCT", "FG3A", "FTA", "USG_PCT"]:
                if field in col:
                    out[field.lower()] = row[col[field]]
            return out
    except Exception as e:
        print(f"[WARN] fetch_nba_trailing_splits: {e}")
    return {}


def fetch_nba_player_gamelog_vs_opponent(player_name: str, opponent_abbr: str, sport: str = "NBA"):
    """
    A player's game log filtered to games against a specific opponent, this
    season. Powers EXPECTED_VS_ACTUAL: how has this player actually
    performed against THIS opponent, compared to today's posted line.

    Returns list of {date, PTS, REB, AST, PRA} dicts, one per game vs that
    opponent. Empty list if player not found, no games vs that opponent
    yet this season, or the request fails -- callers must treat empty as
    "not enough data," never as "confirmed zero."
    """
    if sport != "NBA":
        return []
    player_ids = fetch_nba_all_player_ids()
    person_id = player_ids.get(player_name)
    if not person_id:
        return []
    cache_path = os.path.join(CACHE_DIR, f"nba_gamelog_vs_opp_{person_id}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            cached = _safe_load_pkl(cache_path) or {}
            if opponent_abbr in cached:
                return cached[opponent_abbr]
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
    }
    _yr = date.today().year
    _season = f"{_yr-1}-{str(_yr)[2:]}" if date.today().month < 9 else f"{_yr}-{str(_yr+1)[2:]}"
    url = f"https://stats.nba.com/stats/playergamelog?PlayerID={person_id}&Season={_season}&SeasonType=Regular+Season"
    try:
        resp = _http.get(url, headers=nba_headers, timeout=12)
        if resp.status_code != 200:
            return []
        data = resp.json()
        result_set = data.get("resultSets", [{}])[0]
        headers_ = result_set.get("headers", [])
        rows = result_set.get("rowSet", [])
        col = {h: i for i, h in enumerate(headers_)}
        by_opponent = {}
        for row in rows:
            matchup = str(row[col.get("MATCHUP", 0)] or "")
            # MATCHUP looks like "OKC vs. LAL" or "OKC @ LAL"
            opp = matchup.replace("vs.", "@").split("@")[-1].strip() if "@" in matchup.replace("vs.", "@") else ""
            if not opp:
                continue
            pts = row[col.get("PTS", 0)] or 0
            reb = row[col.get("REB", 0)] or 0
            ast = row[col.get("AST", 0)] or 0
            entry = {
                "date": row[col.get("GAME_DATE", 0)],
                "PTS": pts, "REB": reb, "AST": ast, "PRA": pts + reb + ast,
            }
            by_opponent.setdefault(opp, []).append(entry)
        _safe_save_pkl(cache_path, by_opponent)
        return by_opponent.get(opponent_abbr, [])
    except Exception as e:
        print(f"[WARN] fetch_nba_player_gamelog_vs_opponent: {e}")
        return []


def _current_nba_season_start_year():
    """NBA season starts in October and spans two calendar years (e.g. the
    '2025-26' season). Jul-Sep (off-season) still resolves to the most
    recently completed season since that's the freshest real data
    available; the new season takes over starting in October."""
    now = datetime.now()
    return now.year if now.month >= 10 else now.year - 1


def _current_nba_season_str():
    y = _current_nba_season_start_year()
    return f"{y}-{str(y + 1)[-2:]}"


def _current_mlb_season_year():
    """MLB season runs roughly Mar/Apr-Oct/Nov within a single calendar
    year. Deep off-season (Jan-Feb) falls back to the most recently
    completed season."""
    now = datetime.now()
    return now.year if now.month >= 3 else now.year - 1


def _current_wnba_season_year():
    """WNBA seasons run within a single calendar year (May-Oct, unlike NBA's
    cross-year seasons). Off-season (Nov-Apr) falls back to the most recently
    completed season since there's no live data for a season that hasn't
    started. Computed dynamically instead of hardcoded so this doesn't go
    stale every year the way the previous hardcoded 'Season=2025' did —
    that bug caused every WNBA player lookup to miss (querying a season that
    had already ended) and silently fall back to defaults for almost the
    entire board."""
    now = datetime.now()
    return now.year if now.month >= 5 else now.year - 1


def fetch_wnba_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "wnba_rolling_avgs.pkl")
    nba_headers = {
        "Host": "stats.wnba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.wnba.com/",
        "Origin": "https://www.wnba.com",
    }
    _wnba_season = _current_wnba_season_year()
    urls = [
        f"https://stats.wnba.com/stats/playergamelogs?Season={_wnba_season}&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
        f"https://stats.wnba.com/stats/playergamelogs?Season={_wnba_season - 1}&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
    ]
    rolling = {}
    for url in urls:
        try:
            resp = _http.get(url, headers=nba_headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            for row in rows:
                name = row[col["PLAYER_NAME"]]
                pts = row[col["PTS"]]
                reb = row[col["REB"]]
                ast = row[col["AST"]]
                if name and pts is not None:
                    pts_val = round(float(pts), 1)
                    reb_val = round(float(reb), 1)
                    ast_val = round(float(ast), 1)
                    rolling[name] = {
                        "PTS": pts_val,
                        "REB": reb_val,
                        "AST": ast_val,
                        "PRA": round(pts_val + reb_val + ast_val, 1),
                        "PTS_std": round(pts_val * 0.40, 2) if pts_val > 0 else 4.0,
                        "REB_std": round(reb_val * 0.45, 2) if reb_val > 0 else 1.5,
                        "AST_std": round(ast_val * 0.50, 2) if ast_val > 0 else 1.0,
                        "PRA_std": round((pts_val + reb_val + ast_val) * 0.35, 2),
                        "n_games": 10,
                    }
            if rolling:
                break
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
                requests.exceptions.RequestException, ValueError, KeyError, TypeError, AttributeError):
            continue
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

_NHL_TEAM_ABBREVS = [
    "ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET",
    "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT",
    "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
    "WSH", "WPG",
]  # confirmed live against api-web.nhle.com/v1/roster/{abbr}/current 2026-08-03;
   # UTA (not ARI -- Arizona relocated) confirmed working, ARI confirmed 404


def fetch_nhl_full_roster_ids(force_refresh=False):
    """
    Fetch NHL player IDs for ALL active players across all 32 teams via
    api-web.nhle.com's public roster endpoint. Returns {player_name: player_id}.
    Cached 24h. Same pattern as fetch_mlb_full_roster_ids -- avoids the
    hardcoded-subset limitation of NHL_PLAYER_IDS (config.py).
    """
    cache_path = os.path.join(CACHE_DIR, "nhl_full_roster_ids.pkl")
    if not force_refresh and os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 24:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass

    all_ids = dict(NHL_PLAYER_IDS)  # seed with known IDs
    try:
        for abbr in _NHL_TEAM_ABBREVS:
            url = f"https://api-web.nhle.com/v1/roster/{abbr}/current"
            try:
                resp = _http.get(url, headers=HEADERS, timeout=8)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                for group in ("forwards", "defensemen", "goalies"):
                    for p in data.get(group, []):
                        first = (p.get("firstName", {}) or {}).get("default", "")
                        last  = (p.get("lastName", {}) or {}).get("default", "")
                        pid   = p.get("id")
                        name  = f"{first} {last}".strip()
                        if name and pid and name not in all_ids:
                            all_ids[name] = pid
                time.sleep(0.15)
            except Exception:
                continue
        if len(all_ids) > len(NHL_PLAYER_IDS):
            with open(cache_path, "wb") as f:
                pickle.dump(all_ids, f)
    except Exception:
        pass
    return all_ids


def fetch_wnba_full_roster_ids(force_refresh=False):
    """
    Fetch WNBA player IDs for ALL active players via ESPN's athletes list
    endpoint (site.api.espn.com, limit=300 covers the full league). Returns
    {player_name: player_id}. Cached 24h.
    """
    cache_path = os.path.join(CACHE_DIR, "wnba_full_roster_ids.pkl")
    if not force_refresh and os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 24:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass
    all_ids = {}
    try:
        roster_data = _espn_get(
            "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/athletes?limit=300&active=true",
            "wnba_roster_espn_full", ttl_hours=24
        )
        for a in (roster_data or {}).get("athletes", []):
            name = a.get("displayName", "")
            pid  = a.get("id")
            if name and pid:
                all_ids[name] = pid
        if all_ids:
            with open(cache_path, "wb") as f:
                pickle.dump(all_ids, f)
    except Exception:
        pass
    return all_ids


def _resolve_nhl_stat_for_grading(player: str, stat_key: str, game_date: str):
    """NHL grading resolver. Uses the same api-web.nhle.com game-log endpoint
    already proven in fetch_nhl_player_gamelog_vs_opponent, plus the new
    full-roster lookup (all 32 teams) instead of the hardcoded NHL_PLAYER_IDS
    subset. Returns float or None.
    """
    all_ids = fetch_nhl_full_roster_ids()
    player_id = all_ids.get(player)
    if not player_id:
        return None
    url = f"https://api-web.nhle.com/v1/player/{player_id}/game-log/now"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        games = resp.json().get("gameLog", [])
        g = next((x for x in games if str(x.get("gameDate", ""))[:10] == game_date[:10]), None)
        if not g:
            return None
        _field = {
            "GOALS": "goals", "ASSISTS": "assists", "SOG": "shots",
            "PPP": "powerPlayPoints", "BLOCKED_SHOTS": "blockedShots", "HITS": "hits",
        }.get(stat_key)
        if _field and _field in g:
            return float(g.get(_field, 0) or 0)
        if stat_key == "PTS":  # points = goals + assists
            return float((g.get("goals", 0) or 0) + (g.get("assists", 0) or 0))
    except Exception as e:
        print(f"[WARN] _resolve_nhl_stat_for_grading: {e}")
    return None


    return None


def fetch_mlb_full_roster_ids(force_refresh=False):
    """
    Fetch MLB player IDs for ALL active players across all 30 teams.
    Returns {player_name: player_id} dict. Cached 24h.
    Replaces the hardcoded MLB_PLAYER_IDS for rolling avg fetches.
    """
    cache_path = os.path.join(CACHE_DIR, "mlb_full_roster_ids.pkl")
    if not force_refresh and os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 24:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass

    all_ids = dict(MLB_PLAYER_IDS)  # seed with known IDs
    MLB_TEAM_IDS = [
        133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,158,
        108,109,110,111,112,113,114,115,116,117,118,119,120,121
    ]
    try:
        for team_id in MLB_TEAM_IDS:
            url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active&season={_current_mlb_season_year()}"
            try:
                resp = _http.get(url, headers=HEADERS, timeout=8)
                if resp.status_code != 200:
                    continue
                for p in resp.json().get("roster", []):
                    name = p["person"]["fullName"]
                    pid  = p["person"]["id"]
                    if name not in all_ids:
                        all_ids[name] = pid
                time.sleep(0.15)
            except Exception:
                continue
        if len(all_ids) > len(MLB_PLAYER_IDS):  # only cache if we got new data
            with open(cache_path, "wb") as f:
                pickle.dump(all_ids, f)
    except Exception as e:
        pass
    return all_ids


def fetch_mlb_player_gamelog_vs_opponent(player_name: str, opponent_abbr: str, sport: str = "MLB"):
    """
    MLB counterpart to fetch_nba_player_gamelog_vs_opponent — a player's
    game log filtered to games against a specific opponent, this season.
    Powers EXPECTED_VS_ACTUAL for MLB (built once NBA/NHL went off-season
    and MLB was the sport actually in season). Reuses the existing
    fetch_mlb_full_roster_ids (all 30 teams) rather than a new player-ID
    lookup, and the same statsapi.mlb.com gameLog endpoint already proven
    working in fetch_mlb_rolling_averages.

    Returns list of {date, H, HR, RBI, R, SO, ER} dicts (hitter or pitcher
    fields populated depending on role), one per game vs that opponent.
    Empty list if player not found, no games vs that opponent yet, or the
    request fails.
    """
    if sport != "MLB":
        return []
    all_ids = fetch_mlb_full_roster_ids()
    player_id = all_ids.get(player_name)
    if not player_id:
        return []
    cache_path = os.path.join(CACHE_DIR, f"mlb_gamelog_vs_opp_{player_id}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            cached = _safe_load_pkl(cache_path) or {}
            for opp_key, games in cached.items():
                if opponent_abbr.lower() in opp_key.lower() or opp_key.lower() in opponent_abbr.lower():
                    return games
    by_opponent = {}
    for group in ("hitting", "pitching"):
        url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group={group}&season={_current_mlb_season_year()}&gameType=R"
        try:
            resp = _http.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            stats_list = data.get("stats", [])
            if not stats_list:
                continue
            splits = stats_list[0].get("splits", [])
            for g in splits:
                opp = (g.get("opponent", {}) or {}).get("name", "") or (g.get("opponent", {}) or {}).get("abbreviation", "")
                if not opp:
                    continue
                stat = g.get("stat", {})
                entry = {
                    "date": g.get("date", ""),
                    "H":   stat.get("hits", 0),
                    "HR":  stat.get("homeRuns", 0),
                    "RBI": stat.get("rbi", 0),
                    "R":   stat.get("runs", 0),
                    "SO":  stat.get("strikeOuts", 0),
                    "ER":  stat.get("earnedRuns", 0),
                }
                by_opponent.setdefault(opp, []).append(entry)
            time.sleep(0.2)
        except Exception as e:
            print(f"[WARN] fetch_mlb_player_gamelog_vs_opponent ({group}): {e}")
            continue
    if by_opponent:
        _safe_save_pkl(cache_path, by_opponent)
    # Opponent field from statsapi is a full/short name, not always an
    # abbreviation — match by substring both ways rather than requiring
    # an exact key match.
    for opp_key, games in by_opponent.items():
        if opponent_abbr.lower() in opp_key.lower() or opp_key.lower() in opponent_abbr.lower():
            return games
    return []


def fetch_nhl_rolling_averages():
    import sys as _sys
    ewma_average = getattr(_sys.modules.get("app"), "ewma_average", None) or (lambda vals, decay=0.85, sport=None: round(sum(vals)/len(vals), 2) if vals else 0.0)
    cache_path = os.path.join(CACHE_DIR, "nhl_rolling_avgs.pkl")
    rolling = {}
    for player_name, player_id in NHL_PLAYER_IDS.items():
        url = f"https://api-web.nhle.com/v1/player/{player_id}/game-log/now"
        try:
            resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            games = data.get("gameLog", [])
            last10 = games[:10] if len(games) >= 10 else games
            if len(last10) < 3:
                continue
            pts_vals = [g.get("points",0) for g in last10]
            goal_vals = [g.get("goals",0) for g in last10]
            ast_vals = [g.get("assists",0) for g in last10]
            sog_vals = [g.get("shots",0) for g in last10]
            rolling[player_name] = {
                "PTS": ewma_average(pts_vals, sport="NHL"),
                "GOALS": ewma_average(goal_vals, sport="NHL"),
                "ASSISTS": ewma_average(ast_vals, sport="NHL"),
                "SOG": ewma_average(sog_vals, sport="NHL"),
                "PTS_std": compute_std_dev(pts_vals, sport="NHL") or 0.5,
                "GOALS_std": compute_std_dev(goal_vals, sport="NHL") or 0.3,
                "ASSISTS_std": compute_std_dev(ast_vals, sport="NHL") or 0.35,
                "SOG_std": compute_std_dev(sog_vals, sport="NHL") or 1.2,
                "n_games": len(last10)
            }
            time.sleep(0.3)
        except Exception as e:
            continue
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling


def fetch_nhl_player_gamelog_vs_opponent(player_name: str, opponent_abbr: str, sport: str = "NHL"):
    """
    NHL counterpart to fetch_nba_player_gamelog_vs_opponent — a player's
    game log filtered to games against a specific opponent, this season.
    Built alongside the MLB version even though NHL is currently
    off-season, so it's ready rather than forgotten when the season
    starts. Reuses the existing NHL_PLAYER_IDS map and the api-web.nhle.com
    endpoint already proven working in fetch_nhl_rolling_averages.

    Returns list of {date, PTS, GOALS, ASSISTS, SOG} dicts, one per game
    vs that opponent. Empty list if player not found, no games vs that
    opponent yet, or the request fails.
    """
    if sport != "NHL":
        return []
    player_id = NHL_PLAYER_IDS.get(player_name)
    if not player_id:
        return []
    cache_path = os.path.join(CACHE_DIR, f"nhl_gamelog_vs_opp_{player_id}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            cached = _safe_load_pkl(cache_path) or {}
            if opponent_abbr in cached:
                return cached[opponent_abbr]
    url = f"https://api-web.nhle.com/v1/player/{player_id}/game-log/now"
    by_opponent = {}
    try:
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        games = data.get("gameLog", [])
        for g in games:
            opp = g.get("opponentAbbrev", "")
            if not opp:
                continue
            entry = {
                "date":    g.get("gameDate", ""),
                "PTS":     g.get("points", 0),
                "GOALS":   g.get("goals", 0),
                "ASSISTS": g.get("assists", 0),
                "SOG":     g.get("shots", 0),
            }
            by_opponent.setdefault(opp, []).append(entry)
        if by_opponent:
            _safe_save_pkl(cache_path, by_opponent)
    except Exception as e:
        print(f"[WARN] fetch_nhl_player_gamelog_vs_opponent: {e}")
        return []
    return by_opponent.get(opponent_abbr, [])


def fetch_nba_team_defense():
    cache_path = os.path.join(CACHE_DIR, "nba_team_defense.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            return _safe_load_pkl(cache_path)
    nba_headers = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Referer": "https://www.nba.com/",
    }
    seasons = ["Playoffs", "Regular+Season"]
    team_def = {}
    for season_type in seasons:
        url = f"https://stats.nba.com/stats/leaguedashteamstats?Season={_current_nba_season_str()}&SeasonType={season_type}&MeasureType=Defense&PerMode=PerGame"
        try:
            resp = _http.get(url, headers=nba_headers, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            if not headers or not rows:
                continue
            col = {h: i for i, h in enumerate(headers)}
            def_rating_col = None
            for possible_name in ["DEF_RATING", "DEF_RTNG", "OPP_PTS", "PTS"]:
                if possible_name in col:
                    def_rating_col = possible_name
                    break
            if def_rating_col is None:
                continue
            for row in rows:
                team = row[col["TEAM_ABBREVIATION"]]
                def_rating = row[col[def_rating_col]]
                if def_rating is not None:
                    try:
                        team_def[team] = round(float(def_rating), 1)
                    except (ValueError, TypeError):
                        continue
            if team_def:
                break
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
                requests.exceptions.RequestException, ValueError, KeyError, TypeError, AttributeError):
            continue
    if team_def:
        with open(cache_path, "wb") as f:
            pickle.dump(team_def, f)
    return team_def

def fetch_nfl_roster(team_abbr: str) -> list:
    """
    Fetch current NFL team roster from ESPN.
    Returns list of {name, position, jersey, athlete_id}
    Cached 7 days (rosters don't change often).
    """
    cache_path = os.path.join(CACHE_DIR, f"nfl_roster_{team_abbr}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 86400 < 7:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    try:
        r = _http.get(
            f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_abbr}/roster",
            timeout=12
        )
        if r.status_code != 200:
            return []
        data = r.json()
        players = []
        for group in data.get("athletes", []):
            for athlete in group.get("items", []):
                players.append({
                    "name":       athlete.get("fullName", ""),
                    "position":   athlete.get("position", {}).get("abbreviation", ""),
                    "jersey":     athlete.get("jersey", ""),
                    "athlete_id": str(athlete.get("id", "")),
                    "team":       team_abbr,
                })
        if players:
            _safe_save_pkl(cache_path, players)
        return players
    except Exception as e:
        print(f"[WARN] fetch_nfl_roster({team_abbr}): {e}")
        return []


def fetch_nfl_full_player_database() -> dict:
    """
    Build full NFL player database from all 32 team rosters.
    Returns {normalize_name(player): {name, position, team, athlete_id}}
    Cached 7 days. Run once before season.
    """
    cache_path = os.path.join(CACHE_DIR, "nfl_player_db.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 86400 < 7:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached

    all_teams = list(NFL_TEAM_ABBR_MAP.values())
    db = {}
    for team in all_teams:
        try:
            roster = fetch_nfl_roster(team)
            for p in roster:
                key = normalize_name(p["name"])
                db[key] = p
            time.sleep(0.2)
        except Exception as e:
            print(f"[WARN] nfl_db {team}: {e}")

    if db:
        _safe_save_pkl(cache_path, db)
        print(f"[NFL] Player database built: {len(db)} players")
    return db


def get_nfl_player_position(player_name: str, db: dict = None) -> str:
    """Quick position lookup from NFL player database."""
    if db is None:
        db = _safe_load_pkl(os.path.join(CACHE_DIR, "nfl_player_db.pkl")) or {}
    key = normalize_name(player_name)
    return db.get(key, {}).get("position", "")


def get_nfl_player_baseline(player_name: str, stat: str, db: dict = None) -> float:
    """Get position-based baseline for an NFL player prop."""
    pos = get_nfl_player_position(player_name, db)
    baselines = NFL_POSITION_BASELINES.get(pos, {})
    stat_norm = NFL_STAT_NORMALIZE_MAP.get(stat.lower(), stat.lower().replace(" ","_"))
    return baselines.get(stat_norm, 0.0)

def fetch_nfl_rolling_averages():
    import sys as _sys
    ewma_average = getattr(_sys.modules.get("app"), "ewma_average", None) or (lambda vals, decay=0.85, sport=None: round(sum(vals)/len(vals), 2) if vals else 0.0)
    cache_path = os.path.join(CACHE_DIR, "nfl_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            return _safe_load_pkl(cache_path)
    rolling = {}
    season = 2025
    for player_name, athlete_id in ESPN_ATHLETE_IDS.get("NFL", {}).items():
        sport_path = "football/leagues/nfl"
        url = f"{ESPN_CORE_BASE}/sports/{sport_path}/seasons/{season}/athletes/{athlete_id}/eventlog?limit=10"
        try:
            resp = _http.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            game_stats = []
            for item in data.get("events", {}).get("items", [])[:10]:
                stats_ref = item.get("statistics", {}).get("$ref", "")
                if not stats_ref:
                    continue
                try:
                    stats_resp = _http.get(stats_ref, headers=HEADERS, timeout=10)
                    if stats_resp.status_code != 200:
                        continue
                    stats_data = stats_resp.json()
                    game_stat = {}
                    for split in stats_data.get("splits", {}).get("categories", []):
                        for stat in split.get("stats", []):
                            key = stat.get("abbreviation", "").upper()
                            game_stat[key] = stat.get("value", 0)
                    if game_stat:
                        game_stats.append(game_stat)
                    time.sleep(0.2)
                except Exception:
                    continue
            if not game_stats or len(game_stats) < 3:
                continue
            pass_yds = [g.get("PASSYDS", g.get("YDS", 0)) for g in game_stats]
            rush_yds = [g.get("RUSHYDS", g.get("RYDS", 0)) for g in game_stats]
            rec_yds = [g.get("RECYDS", g.get("RECYD", 0)) for g in game_stats]
            tds = [g.get("TD", 0) for g in game_stats]
            rolling[player_name] = {
                "PASS_YDS": ewma_average(pass_yds, sport="NFL"),
                "RUSH_YDS": ewma_average(rush_yds, sport="NFL"),
                "REC_YDS": ewma_average(rec_yds, sport="NFL"),
                "TD": ewma_average(tds, sport="NFL"),
                "PASS_YDS_std": compute_std_dev(pass_yds, sport="NFL") or 45.0,
                "RUSH_YDS_std": compute_std_dev(rush_yds, sport="NFL") or 15.0,
                "REC_YDS_std": compute_std_dev(rec_yds, sport="NFL") or 20.0,
                "TD_std": compute_std_dev(tds, sport="NFL") or 0.7,
                "n_games": len(game_stats)
            }
            time.sleep(0.3)
        except Exception as e:
            continue
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

def fetch_tennis_tournament_context() -> dict:
    """
    Pulls current ATP and WTA tournament info from ESPN scoreboards.
    Returns {tour: {"surface": str, "tournament": str, "is_slam": bool}}
    Cached 1 hour — tournament surface doesn't change mid-event.
    """
    context = {}
    for tour in ("atp", "wta"):
        try:
            data = _espn_get(
                f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard",
                f"tennis_{tour}_scoreboard_ctx", ttl_hours=1,
            )
            if not data:
                continue
            events = data.get("events", [])
            if not events:
                continue
            event = events[0]
            tournament = event.get("name", "").lower()
            # Detect surface from tournament name
            surface = "hard"  # default
            for slam, surf in _SLAM_SURFACE.items():
                if slam in tournament:
                    surface = surf
                    break
            else:
                if "clay" in tournament or "roland" in tournament or "french" in tournament:
                    surface = "clay"
                elif "grass" in tournament or "wimbledon" in tournament or "queen" in tournament:
                    surface = "grass"
                elif "indoor" in tournament or "covered" in tournament:
                    surface = "indoor hard"
            is_slam = any(s in tournament for s in _ATP_GRAND_SLAMS)
            context[tour] = {
                "surface":    surface,
                "tournament": event.get("name", ""),
                "is_slam":    is_slam and tour == "atp",  # WTA Slams are BO3
            }
        except Exception:
            context[tour] = {"surface": "hard", "tournament": "", "is_slam": False}
    return context

def compute_tennis_games_projection(p1_stats: dict, p2_stats: dict,
                                     surface: str = "hard",
                                     is_best_of_5: bool = False) -> dict:
    """
    Project total games in a tennis match.

    Model:
      base    = surface baseline (BO3 or BO5)
      serve_adj = serve dominance bonus — high 1st serve % → more holds →
                  more tiebreaks → more games (+/- 1.5 games max per player)
      bp_adj   = break point conversion penalty — high BP conversion → faster
                 set endings → fewer games (-/+ 1.0 games max per player)
      ace_adj  = ace rate proxy — dominant server holds faster → minor games boost

    Returns: {"fair_games": float, "surface": str, "serve_adj": float,
              "bp_adj": float, "is_best_of_5": bool}
    """
    baselines = _TENNIS_SURFACE_BASELINES_BO5 if is_best_of_5 else _TENNIS_SURFACE_BASELINES_BO3
    base = baselines.get(surface.lower(), baselines["hard"])

    def _serve_adj(stats):
        if not stats:
            return 0.0
        pct = float(stats.get("1st Serve %", 62.0) or 62.0)
        # Neutral = 62%; each % above → +0.06 games (more holds → tiebreaks)
        return round((pct - 62.0) * 0.06, 2)

    def _bp_adj(stats):
        if not stats:
            return 0.0
        bp = float(stats.get("Break Points Won", 3.0) or 3.0)
        # Neutral = 3 BP/match; each BP above → -0.20 games (breaks → shorter sets)
        return round((bp - 3.0) * -0.20, 2)

    def _ace_adj(stats):
        if not stats:
            return 0.0
        aces = float(stats.get("Aces", 6.0) or 6.0)
        # High aces → dominant service → slight games boost (more holds)
        return round(max(-0.5, min(1.0, (aces - 6.0) * 0.05)), 2)

    p1_sa = _serve_adj(p1_stats)
    p2_sa = _serve_adj(p2_stats)
    p1_bp = _bp_adj(p1_stats)
    p2_bp = _bp_adj(p2_stats)
    p1_ac = _ace_adj(p1_stats)
    p2_ac = _ace_adj(p2_stats)

    # Each player's serve adj adds to total (both hold more → more games)
    # Each player's BP conversion reduces total (breaks end sets faster)
    total_adj = (p1_sa + p2_sa) + (p1_bp + p2_bp) + (p1_ac + p2_ac)
    fair_games = round(max(12.0, min(50.0, base + total_adj)), 1)

    return {
        "fair_games":   fair_games,
        "surface":      surface,
        "serve_adj":    round(p1_sa + p2_sa, 2),
        "bp_adj":       round(p1_bp + p2_bp, 2),
        "ace_adj":      round(p1_ac + p2_ac, 2),
        "is_best_of_5": is_best_of_5,
        "base":         base,
    }

def compute_tennis_ml_edge(p1_stats: dict, p2_stats: dict, surface: str = "hard") -> float:
    """
    Compute serve-efficiency advantage for spread/ML edge.
    Returns a float: positive = p1 (home) advantage, negative = p2 advantage.
    Scale: ±0.10 max before normalization.

    Serve efficiency = (1st Serve %) × (1 - BP conversion rate vs them)
    Higher = harder to break = stronger server.
    """
    def _eff(stats):
        if not stats:
            return 0.0
        sp  = float(stats.get("1st Serve %", 62.0) or 62.0) / 100.0
        bp  = float(stats.get("Break Points Won", 3.0) or 3.0)
        # Normalise BP to a rate (proxy: 3 BP/match = ~0.35 break rate)
        bp_rate = min(0.80, bp / 8.5)
        # Efficiency: serve % × (opponent can't break easily)
        eff = sp * (1.0 - bp_rate * 0.5)
        return eff

    # Surface bonus: clay favours grinders (high BP), grass favours big servers
    surface_serve_mult = {"grass": 1.10, "hard": 1.00, "clay": 0.92,
                          "indoor hard": 1.03, "carpet": 1.08}.get(surface.lower(), 1.00)

    p1_eff = _eff(p1_stats) * surface_serve_mult
    p2_eff = _eff(p2_stats) * surface_serve_mult
    return round(max(-0.12, min(0.12, (p1_eff - p2_eff) * 0.8)), 4)

def fetch_espn_fpi(sport="NFL"):
    """
    ESPN Football Power Index — free, no key, team-strength rating updated
    daily. Returns {team_abbr: {"fpi": float, "rank": int, "off": float,
    "def": float}}. Server-rendered HTML table, no JSON endpoint found, so
    this parses the two side-by-side tables (team names + stat columns) by
    row position. sport: 'NFL' or 'NCF' (college).
    Cached 6h — FPI updates daily, not live.
    """
    cache_path = os.path.join(CACHE_DIR, f"espn_fpi_{sport.lower()}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass
    sport_path = "nfl" if sport.upper() == "NFL" else "college-football"
    try:
        from bs4 import BeautifulSoup
        url = f"https://www.espn.com/{sport_path}/fpi/_/view"
        resp = _http.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        if len(tables) < 2:
            return {}
        # First table: team name + link (gives abbreviation via href slug).
        # Second table: FPI numeric columns in the same row order.
        team_rows = tables[0].find_all("tr")[1:]  # skip header
        stat_rows = tables[1].find_all("tr")[1:]
        teams = []
        for row in team_rows:
            link = row.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            # href like /nfl/team/_/name/lar/los-angeles-rams
            parts = [p for p in href.split("/") if p]
            abbr = parts[parts.index("name") + 1].upper() if "name" in parts else None
            if abbr:
                teams.append(abbr)
        ratings = {}
        for abbr, row in zip(teams, stat_rows):
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cells) < 3:
                continue
            try:
                ratings[abbr] = {
                    "fpi": float(cells[1]),
                    "rank": int(cells[2]),
                    "off": float(cells[4]) if len(cells) > 4 else None,
                    "def": float(cells[5]) if len(cells) > 5 else None,
                    "_source": "ESPN FPI",
                }
            except (ValueError, IndexError):
                continue
        if ratings:
            with open(cache_path, "wb") as f:
                pickle.dump(ratings, f)
        return ratings
    except Exception as e:
        return {}

def fetch_paddypower_lines(sport="NBA"):
    """
    Direct HTML harvest of Paddy Power odds — no Odds API quota cost.

    Verified 2026-07-02: paddypower.com returns fully server-rendered
    match/odds data on plain GET (no WAF challenge page, no login wall,
    no JS execution required to see prices) — same shape of win as the
    BetOnline REST discovery, just HTML instead of JSON.

    Two extraction strategies, tried in order:
      1. Embedded state blob — Nuxt/Vue SSR apps typically inline the
         page's full data store as `window.__NUXT__ = {...}` (or similar)
         inside a <script> tag. If present, this is the reliable path —
         parse the JSON directly rather than scraping rendered text.
      2. Visible-text fallback — parse rendered match rows/odds directly
         from the HTML via BeautifulSoup if no embedded blob is found or
         its shape doesn't match what we expect.

    NOTE: the exact __NUXT__ key structure was not confirmed against a
    live fetch (paddypower.com is outside this environment's egress
    allowlist) — the first production run should be checked against
    logs/System tab, since the site's internal state shape may need a
    small selector adjustment.

    Returns a list of game dicts (home/away/matchup/spread/total/ml) in
    the same shape as fetch_betonline_lines, or [] on any failure so a
    parsing issue here never breaks the board.
    Cached 5 min — matches other game-line fetchers' refresh cadence.
    """
    cache_path = os.path.join(CACHE_DIR, f"paddypower_{sport.lower()}.pkl")
    if os.path.exists(cache_path):
        age_m = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_m < 5:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass

    sport_path = PADDYPOWER_SPORT_MAP.get(sport.upper())
    if not sport_path:
        return []

    games = []
    try:
        url = f"{PADDYPOWER_BASE}/{sport_path}"
        resp = _http.get(url, headers=PADDYPOWER_HEADERS, timeout=15)
        if resp.status_code != 200:
            _logger.info(f"Paddy Power [{sport}] HTTP {resp.status_code}")
            return []

        # ── Strategy 1: embedded SSR state blob ──────────────────────
        _state = None
        for _pattern in (
            r"window\.__NUXT__\s*=\s*(\{.*?\});?\s*</script>",
            r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*</script>",
            r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>',
        ):
            _m = re.search(_pattern, resp.text, re.DOTALL)
            if _m:
                try:
                    _state = json.loads(_m.group(1))
                    break
                except (json.JSONDecodeError, ValueError):
                    continue

        if _state:
            # Shape varies by site build — walk the tree looking for
            # anything that looks like a list of fixtures with prices,
            # rather than hard-coding one exact key path.
            def _walk(node, depth=0):
                if depth > 6 or not games_found_room():
                    return
                if isinstance(node, dict):
                    if {"homeTeam", "awayTeam"} <= node.keys() or \
                       {"home", "away"} <= node.keys():
                        games.append(node)
                        return
                    for v in node.values():
                        _walk(v, depth + 1)
                elif isinstance(node, list):
                    for v in node:
                        _walk(v, depth + 1)

            def games_found_room():
                return len(games) < 200

            _walk(_state)

        # ── Strategy 2: visible-text fallback via BeautifulSoup ──────
        if not games:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            # Paddy Power match rows are typically list items with a
            # participant/fixture data-testid; selector kept loose since
            # exact attribute names weren't confirmed against a live page.
            for row in soup.select('[data-testid*="event"], [class*="event-list"] li, [class*="fixture"]'):
                _txt = row.get_text(" ", strip=True)
                if not _txt or len(_txt) < 6:
                    continue
                games.append({"_raw": _txt, "_source": "PaddyPower_fallback_text"})

        # Normalize whatever we found into the shared game-line shape.
        _normalized = []
        for g in games:
            if "_raw" in g:
                # Fallback rows need manual/human review before use —
                # keep them but flag clearly rather than guessing fields.
                _normalized.append({
                    "Sport": sport, "Source": "PaddyPower", "_needs_review": True,
                    "raw_text": g["_raw"],
                })
                continue
            _home = g.get("homeTeam") or g.get("home") or {}
            _away = g.get("awayTeam") or g.get("away") or {}
            _normalized.append({
                "Sport": sport,
                "Source": "PaddyPower",
                "home": _home.get("name") if isinstance(_home, dict) else _home,
                "away": _away.get("name") if isinstance(_away, dict) else _away,
                "matchup": f"{g.get('awayTeam', g.get('away',''))} @ {g.get('homeTeam', g.get('home',''))}",
                "_raw_node": g,
            })

        if _normalized:
            with open(cache_path, "wb") as f:
                pickle.dump(_normalized, f)
        return _normalized
    except Exception as e:
        _logger.info(f"Paddy Power [{sport}] fetch failed: {e}")
        return load_json_data(PADDYPOWER_PATH, []) if os.path.exists(PADDYPOWER_PATH) else []



    """
    Line-shop a prop across 15-25+ books via Parlay Savant (free to browse,
    no login required for the table itself). Returns consensus line, best
    over/under price+book, and hold% per player — useful as a no-vig
    cross-check or backup when the EV Sharps API doesn't carry a player/prop.
    Cached 10min — odds move during the slate.
    prop: see PARLAYSAVANT_MLB_PROP_MAP for valid slugs.
    """
    cache_path = os.path.join(
        CACHE_DIR, f"parlaysavant_{sport}_{position}_{prop}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < (10 / 60):
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass
    try:
        from bs4 import BeautifulSoup
        url = (f"https://www.parlaysavant.com/props"
               f"?sport={sport}&position={position}&prop={prop}")
        resp = _http.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return {}
        props = {}
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 7:
                continue
            name_link = cells[0].find("a")
            if not name_link:
                continue
            player_name = name_link.get_text(strip=True)
            try:
                line = float(cells[1].get_text(strip=True))
            except (ValueError, IndexError):
                continue
            props[normalize_name(player_name)] = {
                "name": player_name,
                "line": line,
                "over_odds": cells[2].get_text(strip=True),
                "under_odds": cells[3].get_text(strip=True),
                "best_over": cells[4].get_text(strip=True),
                "best_under": cells[5].get_text(strip=True),
                "hold_pct": cells[6].get_text(strip=True),
                "_source": "ParlaySavant",
            }
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
        return props
    except Exception as e:
        return {}

def fetch_bettingpros_props(sport: str) -> list:
    """
    Whole-sport BettingPros props (line/consensus/odds/probability/EV/
    bet_rating/projection/performance per prop), for the harvester loop
    -- feeds the SignalNotes overlay in score_pick_standalone, matched
    per-player the same way GamblingForecast's playerProps is.
    """
    data = _read_gist_file(f"betcouncil_bettingpros_{sport.upper()}.json", cache_minutes=30)
    if not data:
        return []
    return data.get("props", [])


def fetch_bobbys_bets_picks(sport: str = "mlb") -> list:
    """
    Bobby's Bets curated picks (app.bobbysbets.com) -- confirmed live via
    GH Actions test 2026-08-01: real 200, no auth, no Cloudflare. Direct
    in-app fetch, no gist scraper needed (unlike PrizePicks/DK which are
    CF-gated).

    Deliberately scoped to /api/{sport}/picks (curated subset, ~100KB),
    NOT /api/{sport}/props (confirmed 5.2MB for MLB alone -- too large to
    fetch live on every board load).

    Each pick includes: player_name, stat_category, line, label (Over/
    Under), odds, hit_rate_l5/l10/l15/l20/home/away/all, current_streak,
    last5/10/20_values, dk_event_id/dk_outcome_id (deep-link IDs).

    Cached 15 min (added when this became a direct Predictions-tab
    dependency, no longer gated behind a sport board load first -- this
    was the only source feeding that tab with zero caching at all).
    """
    cp = os.path.join(CACHE_DIR, f"bobbysbets_picks_{sport.lower()}.pkl")
    if os.path.exists(cp) and (time.time() - os.path.getmtime(cp)) / 60 < 15:
        c = _safe_load_pkl(cp)
        if c is not None:
            return c
    try:
        r = requests.get(f"https://app.bobbysbets.com/api/{sport.lower()}/picks",
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/124.0.0.0 Safari/537.36"},
                          timeout=15)
        if r.status_code != 200:
            return []
        picks = r.json().get("picks", [])
        if picks:
            _safe_save_pkl(cp, picks)
        return picks
    except Exception:
        return []


def fetch_bobbys_bets_props_from_gist(sport: str = "mlb") -> list:
    """
    Full Bobby's Bets props board (all props, not just curated picks),
    from scripts/bobbys_bets_props_refresh.py -- scheduled scraper,
    handles the large payload (5.2MB raw for MLB) that's too big for a
    live in-app fetch on every board load.
    """
    data = _read_gist_file(f"betcouncil_bobbysbets_props_{sport.lower()}.json", cache_minutes=25)
    if not data:
        return []
    return data.get("props", [])


def fetch_bobbys_bets_briefing(sport: str = "mlb") -> dict:
    """
    Bobby's Bets AI slate briefing, confirmed live, no auth. Real shape
    (confirmed via live test, corrected from an earlier wrong guess):
      {"exists": bool, "date": str, "headline": str, "subhead": str,
       "spot": {"title": str, "why": str}}
    """
    try:
        r = requests.get("https://app.bobbysbets.com/api/briefing",
                          params={"sport": sport.lower()},
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/124.0.0.0 Safari/537.36"},
                          timeout=10)
        if r.status_code != 200:
            return {}
        data = r.json()
        return data if data.get("exists") else {}
    except Exception:
        return {}


def fetch_bobbys_bets_scoreboard(sport: str = "mlb") -> list:
    """Bobby's Bets live scoreboard, confirmed live, no auth. Returns games list."""
    try:
        r = requests.get(f"https://app.bobbysbets.com/api/{sport.lower()}/live/scoreboard",
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/124.0.0.0 Safari/537.36"},
                          timeout=15)
        if r.status_code != 200:
            return []
        return r.json().get("games", [])
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_bobbys_bets_weather(team: str, sport: str = "mlb") -> dict:
    """
    Bobby's Bets stadium/weather/park-factor data for one team, confirmed
    live, no auth. Returns {"stadium": {...}, "weather": {...}, "impact": {...}}.
    Cached 30 min + fast-fail timeout -- called live per-game in a Game
    Lines render loop (up to 15 MLB games), so must never risk stacking
    up slow sequential calls the way the pre-fix Log Bet loop did.
    """
    try:
        r = requests.get(f"https://app.bobbysbets.com/api/{sport.lower()}/weather",
                          params={"team": team.upper()},
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/124.0.0.0 Safari/537.36"},
                          timeout=5)
        if r.status_code != 200:
            return {}
        return r.json()
    except Exception:
        return {}


def fetch_bobbys_bets_best_prices(sport: str = "mlb") -> dict:
    """
    Bobby's Bets best-price-across-books comparison, confirmed live, no
    auth. Real shape: {"best": {"player|stat|line|side": {"book":str,
    "odds":int,"n_books":int}, ...}}. Key is a real, plain pipe-joined
    string exactly as returned -- lowercase player name.
    """
    try:
        r = requests.get(f"https://app.bobbysbets.com/api/best-prices",
                          params={"sport": sport.lower()},
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/124.0.0.0 Safari/537.36"},
                          timeout=20)
        if r.status_code != 200:
            return {}
        return r.json().get("best", {})
    except Exception:
        return {}


def fetch_tennis_scoreboard(tour: str = "atp") -> dict:
    """
    Confirmed undefined (real NameError, silently caught) at 2 call
    sites -- used to check which tour (atp/wta) a given player belongs
    to. Real ESPN endpoint, same one fetch_tennis_tournament_context
    already uses successfully. Confirmed live 2026-08-03: tennis
    scoreboards nest matches under groupings[].competitions[] (NOT
    directly under competitions[] like team-sport scoreboards), since
    a tournament runs many simultaneous matches. Returns
    {normalized_player_name: {"opponent": str, "tournament": str,
    "completed": bool, "status": str, "round": str, "sets": [(my_score,
    opp_score), ...]}}. (status/round/sets added after a deep audit found
    the real caller expected them but the original implementation never
    extracted them.)
    """
    try:
        data = _espn_get(
            f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard",
            f"tennis_{tour}_scoreboard_players", ttl_hours=1,
        )
        if not data:
            return {}
        out = {}
        for event in data.get("events", []):
            tournament = event.get("name", "")
            for grouping in event.get("groupings", []):
                round_name = grouping.get("grouping", "")
                for comp in grouping.get("competitions", []):
                    competitors = comp.get("competitors", [])
                    if len(competitors) != 2:
                        continue
                    names = [c.get("athlete", {}).get("displayName", "") for c in competitors]
                    status_type = comp.get("status", {}).get("type", {})
                    completed = status_type.get("completed", False)
                    status_desc = status_type.get("description", "")
                    for i, name in enumerate(names):
                        if not name:
                            continue
                        opponent = names[1 - i]
                        my_sets = [ls.get("value") for ls in competitors[i].get("linescores", [])]
                        opp_sets = [ls.get("value") for ls in competitors[1 - i].get("linescores", [])]
                        out[normalize_name(name)] = {
                            "opponent": opponent, "tournament": tournament, "completed": completed,
                            "status": status_desc, "round": round_name,
                            "sets": list(zip(my_sets, opp_sets)) if my_sets else [],
                        }
        return out
    except Exception:
        return {}


def fetch_tennis_player_stats(player_name, tour="atp"):
    """
    Real Sackmann ATP/WTA serve/return stats, from scripts/
    sackmann_tennis_refresh.py (betcouncil_tennis_sackmann_{TOUR}.json).
    Confirmed this function was called from 7+ sites in app.py/app_core.py
    but had no definition anywhere in the repo -- a silent NameError on
    every single tennis prop, masked by broad except blocks. Only ATP
    data is confirmed live; WTA has no verified source (matches the
    already-documented pattern for fetch_ufc_fighter_stats below).
    """
    if not player_name:
        return {}
    tour_upper = "WTA" if str(tour).lower() == "wta" else "ATP"
    if tour_upper == "WTA":
        return {}
    data = _read_gist_file(f"betcouncil_tennis_sackmann_{tour_upper}.json", cache_minutes=180)
    if not data:
        return {}
    players = data.get("players", {})
    target = normalize_name(player_name)
    for name, stats in players.items():
        if normalize_name(name) == target:
            return stats
    return {}


def fetch_ufc_fighter_stats(fighter_name):
    """
    No verified UFC fighter-stats data source exists in this codebase.
    Confirmed this function was called from 2+ sites but had no
    definition anywhere -- a silent NameError on every UFC prop, masked
    by broad except blocks. Returns {} deliberately rather than
    fabricate an unverified source; callers already handle {} safely
    (fall back to flat baseline scoring).
    """
    return {}


def fetch_bettingpros_hitrate(player_name, sport="MLB"):
    """
    Prop-level hit-rate/streak trend data (last 1/5/10/15/20 games,
    season, prior season, h2h vs opponent, current streak) from
    scripts/bettingpros_refresh.py (betcouncil_bettingpros_{sport}.json).

    This is the real data hitrate_logger.py's compute_hit_rate() was
    always meant to compute but never could (that function is a stub
    that always returns None, waiting on resolved-outcome data that
    was never wired in) -- this fills that gap directly instead.

    Returns a list of matching prop dicts (a player can have multiple
    props -- e.g. Strikeouts and Outs Recorded for a pitcher), each
    with its own performance/over/under/projection blocks. Matches by
    participant.player.short_name (BettingPros' own compact format,
    e.g. "S. Drohan").
    """
    data = _read_gist_file(f"betcouncil_bettingpros_{sport.upper()}.json", cache_minutes=30)
    if not data:
        return []
    props = data.get("props", [])
    if not props:
        return []

    parts = player_name.strip().split()
    if not parts:
        return []
    search_last = parts[-1].lower()
    search_first_initial = parts[0][0].lower() if parts[0] else ""

    matches = []
    for p in props:
        player = (p.get("participant", {}) or {}).get("player", {}) or {}
        short = str(player.get("short_name", "")).lower()
        last = str(player.get("last_name", "")).lower()
        first = str(player.get("first_name", "")).lower()
        if last == search_last and (not search_first_initial or first[:1] == search_first_initial or search_first_initial in short):
            matches.append(p)
    return matches


def fetch_gamblingforecast_matchup(player_name):
    """
    Batter-vs-this-specific-pitcher history (H/HR/RBI/AVG/OPS) from
    scripts/gamblingforecast_refresh.py (betcouncil_gamblingforecast_
    mlb_matchups.json). Real field names discovered live via GraphQL
    introspection when the scraper ran (not guessed).

    Name matching quirk (confirmed against real captured data): the
    stored `name` field glues FirstName+LastInitial+"."+LastName with
    no spaces, e.g. "SeiyaS.Suzuki" for Seiya Suzuki -- a formatting
    artifact on their end, not something to normalize away naively.
    Parses first/last name out of both the stored glued format and the
    plain search name, then compares those.
    """
    data = _read_gist_file("betcouncil_gamblingforecast_mlb_matchups.json", cache_minutes=180)
    if not data:
        return {}
    matchups = data.get("matchups", [])
    if not matchups:
        return {}

    search_parts = player_name.strip().split()
    search_first = search_parts[0].lower() if search_parts else ""
    search_last = search_parts[-1].lower() if len(search_parts) > 1 else ""
    if not search_first or not search_last:
        return {}

    for m in matchups:
        stored = str(m.get("name", "")).strip()
        glued = re.match(r"^([A-Za-z]+)([A-Z])\.([A-Za-z\-]+)$", stored)
        if glued:
            stored_first, _, stored_last = glued.groups()
        else:
            parts = stored.split()
            stored_first = parts[0] if parts else ""
            stored_last = parts[-1] if len(parts) > 1 else ""
        if stored_first.lower() == search_first and stored_last.lower() == search_last:
            return m
    return {}


def fetch_gamblingforecast_props(sport: str) -> list:
    """
    GamblingForecast's own model projection-vs-line, pre-sorted by edge
    (projDiff), from scripts/gamblingforecast_refresh.py
    (betcouncil_gamblingforecast_props_{sport}.json). Covers MLB/NBA/NFL.
    A second independent model's opinion, matched per-player into
    SignalNotes the same way SignalOdds/BetsLib already is.
    """
    data = _read_gist_file(f"betcouncil_gamblingforecast_props_{sport}.json", cache_minutes=30)
    if not data:
        return []
    return data.get("props", [])


def fetch_soccer_player_stats(player_name):
    """
    Confirmed dead end (live-tested): ESPN does not publish individual
    player stats for soccer via any public API -- every endpoint pattern
    (site.api.espn.com, site.web.api.espn.com, sports.core.api.espn.com)
    404s. Returns {} immediately instead of burning a network round-trip
    per player that always fails; this was a real contributor to slow
    board-paste analysis times for Soccer props.
    """
    return {}


def _fetch_soccer_player_stats_DEAD_ENDPOINT(player_name):
    """
    Fetch soccer player season stats from ESPN (goals, assists, shots).
    Searches MLS, EPL, La Liga, Serie A, Bundesliga, Ligue 1, Champions League.
    Cached 12h per player.
    """
    cache_key = f"soccer_player_{normalize_name(player_name)}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 12:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass

    SOCCER_LEAGUES = [
        ("usa.1", "MLS"), ("eng.1", "EPL"), ("esp.1", "La Liga"),
        ("ita.1", "Serie A"), ("ger.1", "Bundesliga"), ("fra.1", "Ligue 1"),
        ("uefa.champions", "UCL"),
    ]
    norm = normalize_name(player_name)
    result = None

    for league_key, league_name in SOCCER_LEAGUES:
        roster_data = _espn_get(
            f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_key}/athletes?limit=500",
            f"soccer_{league_key}_roster", ttl_hours=24
        )
        if not roster_data:
            continue
        match = next((a for a in roster_data.get("athletes", [])
                      if normalize_name(a.get("displayName","")) == norm), None)
        if not match:
            continue
        pid = match.get("id")
        if not pid:
            continue

        stats_data = _espn_get(
            f"https://site.web.api.espn.com/apis/common/v3/sports/soccer/{league_key}/athletes/{pid}/stats",
            f"soccer_{league_key}_{pid}_stats", ttl_hours=6
        )
        if not stats_data:
            continue

        stat_map = {}
        _cats = stats_data.get("categories") or stats_data.get("splits", {}).get("categories", [])
        for cat in _cats:
            for s in cat.get("stats", []):
                stat_map[s.get("name", "")] = s.get("value", 0)

        if stat_map:
            games = max(1, int(stat_map.get("gamesPlayed", stat_map.get("appearances", 20))))
            goals_total = float(stat_map.get("goals", 0))
            assists_total = float(stat_map.get("goalAssists", stat_map.get("assists", 0)))
            shots_total = float(stat_map.get("shots", stat_map.get("totalShots", 0)))
            shots_ot = float(stat_map.get("shotsOnTarget", 0))
            result = {
                "GOALS":           round(goals_total / games, 3),
                "ASSISTS":         round(assists_total / games, 3),
                "SHOTS":           round(shots_total / games, 2),
                "Shots on Target": round(shots_ot / games, 2),
                "n_games":         games,
                "_league":         league_name,
                "_source":         "ESPN",
            }
            break

    if result:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception:
            pass
    return result

def fetch_nfl_live_baselines(force_refresh=False) -> dict:
    """
    Fetch live NFL position baselines from ESPN stats leaders.
    Automatically called on first NFL board load each week.
    Cached 7 days.
    """
    cache_path = os.path.join(CACHE_DIR, "nfl_live_baselines.pkl")
    if not force_refresh and os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 86400 < 7:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    season = date.today().year if date.today().month >= 8 else date.today().year - 1
    try:
        r = _http.get(
            f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/leaders"
            f"?season={season}&seasontype=2&limit=32",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                     "Referer": "https://www.espn.com/"},
            timeout=12,
        )
        if r.status_code != 200:
            return {}
        baselines = {}
        for cat in r.json().get("categories", []):
            cat_name = cat.get("name", "").lower()
            values = [float(l.get("value",0)) for l in cat.get("leaders",[])[:24] if l.get("value",0)]
            if not values: continue
            avg = sum(values) / len(values) / 17  # per game
            if "passing" in cat_name and "yard" in cat_name:
                baselines.setdefault("QB",{})["passing_yards"] = round(avg,1)
            elif "passing" in cat_name and "touchdown" in cat_name:
                baselines.setdefault("QB",{})["passing_touchdowns"] = round(avg,2)
            elif "rushing" in cat_name and "yard" in cat_name:
                baselines.setdefault("RB",{})["rushing_yards"] = round(avg,1)
            elif "receiving" in cat_name and "yard" in cat_name:
                baselines.setdefault("WR",{})["receiving_yards"] = round(avg,1)
            elif "reception" in cat_name:
                baselines.setdefault("WR",{})["receptions"] = round(avg,1)
        if baselines:
            _safe_save_pkl(cache_path, baselines)
        return baselines
    except Exception as e:
        print(f"[WARN] fetch_nfl_live_baselines: {e}")
        return {}

def fetch_nfl_player_stats(player_name: str) -> dict:
    """
    Fetch NFL player season stats from ESPN public athlete API.
    Handles QB/RB/WR/TE automatically.
    Cached 6h during season, 24h off-season.
    Returns {passing_yards, rushing_yards, receiving_yards, receptions,
             targets, touchdowns, position, team, games_played}
    """
    norm = normalize_name(player_name)
    cache_path = os.path.join(CACHE_DIR, f"nfl_player_{norm[:20]}.pkl")
    cache_hours = 6 if date.today().month in (9,10,11,12,1) else 24
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < cache_hours:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    try:
        # Step 1: Search for player
        search_url = f"https://site.api.espn.com/apis/common/v3/search?query={urllib.parse.quote(player_name)}&limit=5&type=player&sport=football&league=nfl"
        r = _http.get(search_url, timeout=10)
        if r.status_code != 200:
            return {}
        results = r.json().get("items", [])
        if not results:
            return {}
        # Find best match
        athlete_id = None
        for item in results:
            if item.get("type") == "player":
                athlete_id = item.get("id")
                break
        if not athlete_id:
            return {}

        # Step 2: Get stats
        stats_url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{athlete_id}/stats"
        r2 = _http.get(stats_url, timeout=10)
        if r2.status_code != 200:
            return {}
        data = r2.json()

        result = {
            "player":       player_name,
            "athlete_id":   athlete_id,
            "position":     data.get("athlete", {}).get("position", {}).get("abbreviation", ""),
            "team":         data.get("athlete", {}).get("team", {}).get("abbreviation", ""),
            "games_played": 0,
        }

        # Parse stat categories -- real shape (confirmed by live testing,
        # same as WNBA): {"categories": [{"name": "passing", "names":
        # [...], "totals": [...]}, ...]}. Values are parallel arrays under
        # "names"/"totals", not {"name":x,"value":y} pairs.
        _stat_cats = data.get("categories") or data.get("splits", {}).get("categories", [])
        for cat in _stat_cats:
            cat_name = cat.get("name", "").lower()
            _names = cat.get("names", [])
            _totals = cat.get("totals", [])
            for sname_raw, sval in zip(_names, _totals):
                sname = str(sname_raw).lower().replace(" ", "_")
                try:
                    sval = float(sval)
                except (TypeError, ValueError):
                    continue
                if "passing" in cat_name:
                    if "yard" in sname or sname == "yds": result["passing_yards"] = sval
                    if "touchdown" in sname or sname == "td": result["passing_touchdowns"] = sval
                    if "attempt" in sname or sname == "att": result["pass_attempts"] = sval
                    if "completion" in sname or sname == "cmp": result["completions"] = sval
                elif "rushing" in cat_name:
                    if "yard" in sname or sname == "yds": result["rushing_yards"] = sval
                    if "touchdown" in sname or sname == "td": result["rushing_touchdowns"] = sval
                elif "receiving" in cat_name:
                    if "yard" in sname or sname == "yds": result["receiving_yards"] = sval
                    if "reception" in sname or "catch" in sname or sname == "rec": result["receptions"] = sval
                    if "target" in sname or sname == "tgt": result["targets"] = sval
                    if "touchdown" in sname or sname == "td": result["receiving_touchdowns"] = sval
                if ("game" in sname and "played" in sname) or sname == "gp":
                    result["games_played"] = int(sval)

        # Per-game averages
        gp = result.get("games_played", 1) or 1
        for k in ["passing_yards","rushing_yards","receiving_yards","receptions",
                   "targets","passing_touchdowns","rushing_touchdowns","receiving_touchdowns",
                   "pass_attempts","completions"]:
            if k in result:
                result[f"{k}_per_game"] = round(result[k] / gp, 2)

        _safe_save_pkl(cache_path, result)
        return result
    except Exception as e:
        print(f"[WARN] fetch_nfl_player_stats({player_name}): {e}")
        return {}


def fetch_nfl_player_gamelog_vs_opponent(player_name: str, opponent_abbr: str, sport: str = "NFL"):
    """
    NFL counterpart to fetch_nba_player_gamelog_vs_opponent — a player's
    game log filtered to games against a specific opponent, this season.
    Built alongside MLB/NHL even though NFL is off-season, so it's ready
    rather than forgotten when the season starts.

    Unlike the NBA/MLB/NHL versions, this doesn't reuse an already-proven
    per-game endpoint — it chases ESPN's search -> core API eventlog ->
    event detail chain (same pattern as resolve_actual_stat_for_grading)
    to pull each game's opponent team. This path is less battle-tested
    than the others; flagging that honestly rather than promising it's
    verified — worth a real check once the season starts and there's
    live data to confirm against.

    Returns list of {date, PASS_YDS, RUSH_YDS, REC_YDS, TD} dicts, one per
    game vs that opponent. Empty list if player not found, no games vs
    that opponent yet, or the request fails.
    """
    if sport != "NFL":
        return []
    try:
        search_url = f"https://site.api.espn.com/apis/common/v3/search?query={urllib.parse.quote(player_name)}&limit=5&type=player&sport=football&league=nfl"
        r = _http.get(search_url, timeout=10)
        if r.status_code != 200:
            return []
        results = r.json().get("items", [])
        athlete_id = None
        for item in results:
            if item.get("type") == "player":
                athlete_id = item.get("id")
                break
        if not athlete_id:
            return []
    except Exception as e:
        print(f"[WARN] fetch_nfl_player_gamelog_vs_opponent (search): {e}")
        return []

    # Need the player's OWN team abbreviation to correctly identify which
    # competitor in each game is the opponent (vs. their own team).
    own_team_stats = fetch_nfl_player_stats(player_name)
    own_team_abbr = (own_team_stats or {}).get("team", "").upper()
    if not own_team_abbr:
        return []

    cache_path = os.path.join(CACHE_DIR, f"nfl_gamelog_vs_opp_{athlete_id}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            cached = _safe_load_pkl(cache_path) or {}
            if opponent_abbr in cached:
                return cached[opponent_abbr]

    by_opponent = {}
    try:
        season = 2025 if date.today().month >= 3 else 2024
        url = f"{ESPN_CORE_BASE}/sports/football/leagues/nfl/seasons/{season}/athletes/{athlete_id}/eventlog?limit=20"
        resp = _http.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        for item in data.get("events", {}).get("items", [])[:20]:
            event_ref = item.get("event", {}).get("$ref", "") or item.get("$ref", "")
            stats_ref = item.get("statistics", {}).get("$ref", "")
            if not event_ref or not stats_ref:
                continue
            try:
                ev_resp = _http.get(event_ref, headers=HEADERS, timeout=10)
                if ev_resp.status_code != 200:
                    continue
                ev_data = ev_resp.json()
                game_date = ev_data.get("date", "")
                opp_abbrev = ""
                competitions = ev_data.get("competitions", [])
                if competitions:
                    for competitor in competitions[0].get("competitors", []):
                        team_ref = competitor.get("team", {}).get("$ref", "")
                        if not team_ref:
                            continue
                        team_resp = _http.get(team_ref, headers=HEADERS, timeout=8)
                        if team_resp.status_code == 200:
                            abbr = team_resp.json().get("abbreviation", "")
                            if abbr and abbr.upper() != own_team_abbr:
                                opp_abbrev = abbr
                if not opp_abbrev:
                    continue
                stats_resp = _http.get(stats_ref, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if stats_resp.status_code != 200:
                    continue
                stats_data = stats_resp.json()
                game_stat = {}
                for split in stats_data.get("splits", {}).get("categories", []):
                    for stat in split.get("stats", []):
                        game_stat[stat.get("abbreviation", "").upper()] = stat.get("value", 0)
                entry = {
                    "date": game_date,
                    "PASS_YDS": game_stat.get("PASSYDS", game_stat.get("YDS", 0)),
                    "RUSH_YDS": game_stat.get("RUSHYDS", game_stat.get("RYDS", 0)),
                    "REC_YDS":  game_stat.get("RECYDS", game_stat.get("RECYD", 0)),
                    "TD":       game_stat.get("TD", 0),
                }
                by_opponent.setdefault(opp_abbrev, []).append(entry)
                time.sleep(0.15)
            except Exception:
                continue
        if by_opponent:
            _safe_save_pkl(cache_path, by_opponent)
    except Exception as e:
        print(f"[WARN] fetch_nfl_player_gamelog_vs_opponent: {e}")
        return []
    return by_opponent.get(opponent_abbr, [])


def _fetch_wnba_roster_via_teams():
    """
    WNBA roster lookup, name -> ESPN athlete ID.
    The /athletes?limit=300&active=true endpoint is confirmed 404 (verified
    by live testing) -- ESPN doesn't expose a flat WNBA athlete index that
    way. The working approach is iterating all 15 teams and pulling each
    team's roster. Cached 24h as one combined dict since this is 16 HTTP
    calls (1 teams list + 15 rosters); not something to redo per player.

    Also cached at the session level (regardless of success/failure) so a
    failed attempt within one board-paste run doesn't retry this same
    16-call sequence for every subsequent player that needs the fallback --
    that repeat was a real contributor to very slow analysis times. An
    EMPTY session-cached result expires after 5 min rather than sticking
    for the whole browser session, so a transient failure self-heals on
    the next analysis run instead of silently blocking every player until
    a full page reload.
    """
    try:
        _cached_session = st.session_state.get("_wnba_roster_via_teams_session")
        _cached_ts = st.session_state.get("_wnba_roster_via_teams_session_ts", 0)
        if _cached_session:
            return _cached_session
        if _cached_session is not None and (time.time() - _cached_ts <= 300):
            # Empty result, but still fresh -- don't retry yet.
            return _cached_session
    except Exception:
        pass

    cache_path = os.path.join(CACHE_DIR, "wnba_roster_via_teams.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 24:
            try:
                with open(cache_path, "rb") as f:
                    _cached = pickle.load(f)
                try:
                    st.session_state["_wnba_roster_via_teams_session"] = _cached
                    st.session_state["_wnba_roster_via_teams_session_ts"] = time.time()
                except Exception:
                    pass
                return _cached
            except Exception:
                pass

    teams_data = _espn_get(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams",
        "wnba_teams_list", ttl_hours=24
    )
    if not teams_data:
        try:
            st.session_state["_wnba_roster_via_teams_session"] = {}
            st.session_state["_wnba_roster_via_teams_session_ts"] = time.time()
        except Exception:
            pass
        return {}
    team_ids = []
    for sport in teams_data.get("sports", []):
        for league in sport.get("leagues", []):
            for t in league.get("teams", []):
                tid = t.get("team", {}).get("id")
                if tid:
                    team_ids.append(tid)

    roster = {}
    for tid in team_ids:
        roster_data = _espn_get(
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{tid}/roster",
            f"wnba_team_{tid}_roster", ttl_hours=24
        )
        if not roster_data:
            continue
        for a in roster_data.get("athletes", []):
            name = a.get("displayName", "")
            aid = a.get("id")
            if name and aid:
                roster[normalize_name(name)] = aid

    if roster:
        with open(cache_path, "wb") as f:
            pickle.dump(roster, f)
    try:
        st.session_state["_wnba_roster_via_teams_session"] = roster
        st.session_state["_wnba_roster_via_teams_session_ts"] = time.time()
    except Exception:
        pass
    return roster


def fetch_wnba_player_stats(player_name):
    """
    Fetch WNBA player season stats from ESPN.
    Fallback for players not in stats.wnba.com rolling avg cache.
    Cached 6h. Logs the specific failure point to st.session_state["errors"]
    instead of silently returning None, since a silent failure here was
    previously indistinguishable from "no data exists" -- every WNBA prop
    was showing as unresolvable with zero way to tell why.
    """
    def _log(step, detail):
        try:
            st.session_state.setdefault("errors", []).append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "source": f"fetch_wnba_player_stats:{step}",
                "error": detail, "player": player_name,
            })
        except Exception:
            pass

    cache_key = f"wnba_player_{normalize_name(player_name)}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass

    norm = normalize_name(player_name)
    roster_map = _fetch_wnba_roster_via_teams()
    if not roster_map:
        _log("roster_fetch", "team-by-team roster lookup returned nothing -- see espn_get log above")
        return None
    pid = roster_map.get(norm)
    if not pid:
        _log("name_match", f"'{player_name}' not found among {len(roster_map)} team-roster entries -- name mismatch or not active")
        return None

    stats_data = _espn_get(
        f"https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{pid}/stats",
        f"wnba_{pid}_stats_{_current_wnba_season_year()}", ttl_hours=6
    )
    if not stats_data:
        _log("stats_fetch", f"stats endpoint failed for pid={pid} -- see espn_get log above for the real HTTP reason")
        return None

    # Real shape (confirmed by live testing): {"categories": [{"name":
    # "averages", "names": ["GP","GS","MIN","PTS",...], "totals": ["459",
    # "430","30.1","16.8",...]}, ...]}. Values are parallel arrays under
    # "names"/"totals", NOT {"name":x,"value":y} pairs -- zip them per
    # category, and use the "averages" category specifically (not
    # "totals"/"ranks", which are season-total and league-rank rows).
    stat_map = {}
    for cat in stats_data.get("categories", []):
        if str(cat.get("name", "")).lower() != "averages":
            continue
        # BUG FIX: ESPN returns two name arrays per category:
        #   "labels"  = short codes  -> ["GP","GS","MIN","PTS","OR","DR","REB","AST","STL","BLK","TO","FG","3PT","FT",...]
        #   "names"   = verbose keys -> ["gamesPlayed","gamesStarted","avgMinutes","avgPoints",...]
        # The stat lookups below all use short codes (PTS, REB, AST, TO, GP), so
        # we MUST zip against "labels", not "names". Using "names" here was the
        # root cause of every WNBA prop showing "no real player data found":
        # stat_map was non-empty (had verbose keys) so the empty-check passed,
        # but every subsequent .get("PTS") call returned 0, producing an all-zero
        # result dict that score_pick_standalone correctly flagged as no real data.
        labels = cat.get("labels", [])
        totals = cat.get("totals", [])
        for n, v in zip(labels, totals):
            try:
                # FG / 3PT / FT labels carry "makes-attempts" strings like "0.6-1.6".
                # Parse just the makes (first token) as a float; drop the attempts.
                v_str = str(v)
                if "-" in v_str and n in ("FG", "3PT", "FT"):
                    stat_map[n] = float(v_str.split("-")[0])
                else:
                    stat_map[n] = float(v_str)
            except (TypeError, ValueError):
                stat_map[n] = 0

    if not stat_map:
        _log("empty_stat_map", f"stats_data returned for pid={pid} but no 'averages' category parsed -- top-level keys: {list(stats_data.keys())[:10]}")
        return None

    pts = round(float(stat_map.get("PTS", 0)), 1)
    reb = round(float(stat_map.get("REB", 0)), 1)
    ast = round(float(stat_map.get("AST", 0)), 1)
    stl = round(float(stat_map.get("STL", 0)), 1)
    blk = round(float(stat_map.get("BLK", 0)), 1)
    # 3PT label (confirmed key in "labels" array) carries the 3-pointers-made avg.
    tpm = round(float(stat_map.get("3PT", stat_map.get("3PM", stat_map.get("3PTM", 0)))), 1)
    tov = round(float(stat_map.get("TO", stat_map.get("TOV", 0))), 1)
    games = max(1, int(stat_map.get("GP", 20)))

    result = {
        "PTS": pts, "REB": reb, "AST": ast,
        "STL": stl, "BLK": blk,
        "PRA": round(pts + reb + ast, 1),
        "PTS_REB": round(pts + reb, 1),
        "PTS_AST": round(pts + ast, 1),
        "REB_AST": round(reb + ast, 1),
        "3PM": tpm,
        "TO": tov,
        # Standard DraftKings-style basketball classic scoring, used as a
        # reasonable approximation since PrizePicks doesn't publish their
        # exact "Fantasy Score" formula.
        "FANTASY": round(pts * 1.0 + reb * 1.2 + ast * 1.5 + stl * 3.0 + blk * 3.0 - tov * 1.0, 1),
        "n_games": games,
        "_source": "ESPN",
    }
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(result, f)
    except Exception:
        pass
    return result

def fetch_soccer_team_goals(league_key: str = "eng.1") -> dict:
    """
    Fetch goals-for and goals-against per game for all teams in a soccer league.
    Uses ESPN team statistics endpoint.
    Returns: {team_display_name: {"gf_pg": float, "ga_pg": float, "cs_rate": float}}
    Cached 6 hours. Falls back to league baseline on failure.
    """
    cache_path = os.path.join(CACHE_DIR, f"soccer_team_goals_{league_key.replace('.','_')}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass
    try:
        teams_r = _http.get(
            f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_key}/teams?limit=30",
            headers=HEADERS, timeout=10,
        )
        if teams_r.status_code != 200:
            return {}
        teams = (teams_r.json().get("sports", [{}])[0]
                              .get("leagues", [{}])[0]
                              .get("teams", []))
    except Exception:
        return {}

    league_avg_per_team = _SOCCER_LEAGUE_BASELINES.get(league_key, 2.7) / 2
    result = {}
    for entry in teams:
        team = entry.get("team", {})
        name = team.get("displayName", "")
        tid  = team.get("id")
        if not name or not tid:
            continue
        try:
            sr = _http.get(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_key}"
                f"/teams/{tid}/statistics",
                headers=HEADERS, timeout=8,
            )
            if sr.status_code != 200:
                continue
            cats = sr.json().get("results", {}).get("splits", {}).get("categories", [])
            gf = ga = gp = cs = None
            for cat in cats:
                cname = cat.get("name", "").lower()
                stats = {s["name"]: float(s.get("value") or 0) for s in cat.get("stats", [])}
                if "general" in cname or "scoring" in cname or "goals" in cname:
                    gf = gf or stats.get("goalsFor") or stats.get("goals")
                    ga = ga or stats.get("goalsAgainst")
                    gp = gp or stats.get("gamesPlayed") or stats.get("played")
                    cs = cs or stats.get("cleanSheets")
            if gf is not None and gp and gp > 0:
                result[name] = {
                    "gf_pg":   round(float(gf) / float(gp), 3),
                    "ga_pg":   round(float(ga or 0) / float(gp), 3),
                    "cs_rate": round(float(cs or 0) / float(gp), 3),
                }
        except Exception:
            continue

    if result:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception:
            pass
    return result

def fetch_ufc_fight_card() -> list:
    """
    Fetch upcoming UFC event and fight card from ESPN MMA scoreboard.
    Returns list of dicts: {matchup, fighter1, fighter2, weightclass, is_title}
    Cached 1 hour.
    """
    try:
        r = _http.get(
            "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard",
            headers=HEADERS, timeout=10,
        )
        if r.status_code != 200:
            return []
        events = r.json().get("events", [])
        card = []
        for event in events:
            for comp in event.get("competitions", []):
                comps = comp.get("competitors", [])
                if len(comps) < 2:
                    continue
                f1 = comps[0].get("athlete", {}).get("displayName", "") or \
                     comps[0].get("team", {}).get("displayName", "")
                f2 = comps[1].get("athlete", {}).get("displayName", "") or \
                     comps[1].get("team", {}).get("displayName", "")
                if not f1 or not f2:
                    continue
                details = comp.get("details", [{}])
                weightclass = ""
                is_title = False
                for d in details:
                    txt = str(d.get("type", {}).get("description", "") or "").lower()
                    if "weight" in txt or "class" in txt:
                        weightclass = txt
                    if "title" in txt or "championship" in txt:
                        is_title = True
                card.append({
                    "matchup":    f"{f1} vs {f2}",
                    "fighter1":   f1,
                    "fighter2":   f2,
                    "weightclass": weightclass,
                    "is_title":   is_title,
                })
        return card
    except Exception:
        return []

def compute_ufc_round_projection(fighter1_stats: dict, fighter2_stats: dict,
                                  weightclass: str = "", is_title: bool = False) -> dict:
    """
    Project expected rounds for a UFC fight.

    Formula (Pythagorean finish-rate blend):
      finish_prob = (f1_finish_rate + f2_finish_rate) / 2
      rounds_if_finish  = baseline × 0.55   (early finish)
      rounds_if_decision = max_rounds × 0.92 (decision goes ~4.6/5 or ~2.75/3)
      projected = finish_prob × rounds_if_finish + (1-finish_prob) × rounds_if_decision

    Returns: {"fair_rounds": float, "finish_prob": float, "pace_factor": float}
    """
    max_rounds = _UFC_CHAMPIONSHIP_ROUNDS if is_title else 3
    wc_key = weightclass.lower().strip() if weightclass else ""
    baseline = next(
        (v for k, v in _UFC_WEIGHTCLASS_BASELINES.items() if k in wc_key),
        _UFC_ROUND_DEFAULT
    )
    if is_title:
        baseline = baseline * (5 / 3)  # scale baseline to 5-round context

    # Finish rate proxy — KD/15min and sub attempts/15min as finish indicators
    def _finish_rate(stats):
        if not stats:
            return 0.40  # league avg ~40% finish rate
        kd  = float(stats.get("KD", stats.get("KNOCKDOWNS", 0)) or 0)
        sub = float(stats.get("SUB_ATT", stats.get("SUB_ATTEMPTS", 0)) or 0)
        # KD > 0.2/fight → striker finish threat; sub > 0.8 → grappler finish threat
        finish = min(0.85, 0.35 + kd * 0.3 + sub * 0.2)
        return finish

    f1_fr = _finish_rate(fighter1_stats)
    f2_fr = _finish_rate(fighter2_stats)
    avg_finish_prob = (f1_fr + f2_fr) / 2

    rounds_if_finish  = baseline * 0.55
    rounds_if_decision = max_rounds * 0.92
    fair_rounds = avg_finish_prob * rounds_if_finish + (1 - avg_finish_prob) * rounds_if_decision

    # Pace factor — high sig strikes from both = faster finish
    f1_pace = float((fighter1_stats or {}).get("SIG_STR", 35) or 35)
    f2_pace = float((fighter2_stats or {}).get("SIG_STR", 35) or 35)
    avg_pace = (f1_pace + f2_pace) / 2
    # High pace (>50 strikes/min for both) → more likely early finish
    pace_factor = max(-0.4, min(0.3, (avg_pace - 40) * -0.02))
    fair_rounds = round(max(1.0, min(float(max_rounds), fair_rounds + pace_factor)), 2)

    return {
        "fair_rounds":   fair_rounds,
        "finish_prob":   round(avg_finish_prob, 3),
        "pace_factor":   round(pace_factor, 3),
        "max_rounds":    max_rounds,
        "weightclass":   weightclass,
    }

def fetch_epl_live_player_stats(comp_season_id=777, min_apps=5):
    """Fetch live current-season EPL player stats from the Premier League's own
    public Pulse Live API (footballapi.pulselive.com) -- no auth, no key, not
    blocked from any tested IP (Replit or GitHub Actions runners).

    Returns per-game GOALS/ASSISTS/SHOTS for every EPL player with >= min_apps
    appearances this season. comp_season_id must be refreshed each EPL season
    (call fetch_epl_current_season_id() or hardcode after checking
    footballapi.pulselive.com/football/competitions/1/compseasons).
    """
    cache_path = os.path.join(CACHE_DIR, "epl_live_stats.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    def _ranked(stat, page_size=100, max_pages=6):
        content = []
        for page in range(max_pages):
            url = (f"https://footballapi.pulselive.com/football/stats/ranked/players/{stat}"
                   f"?compSeasons={comp_season_id}&comps=1&page={page}"
                   f"&pageSize={page_size}&sort=desc&type=player")
            resp = _http.get(url, headers={"Origin": "https://www.premierleague.com"}, timeout=12)
            if resp.status_code != 200:
                break
            data = resp.json()
            batch = data.get("stats", {}).get("content", [])
            content.extend(batch)
            total = data.get("stats", {}).get("pageInfo", {}).get("numEntries", 0)
            if len(content) >= total:
                break
        return content

    try:
        goals_data = _ranked("goals")
        assists_data = _ranked("goal_assist")
        shots_data = _ranked("total_scoring_att")
        apps_data = _ranked("appearances")
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_epl_live_player_stats",
            "error": str(e)[:100]
        })
        return {}

    def _team(owner):
        ct = owner.get("currentTeam")
        return ct["name"] if ct else "Unknown"

    apps_map = {}
    for e in apps_data:
        pid = e["owner"]["id"]
        apps_map[pid] = {"name": e["owner"]["name"]["display"], "apps": e["value"],
                          "team": _team(e["owner"])}
    goals_map = {e["owner"]["id"]: (e["value"], _team(e["owner"])) for e in goals_data}
    assists_map = {e["owner"]["id"]: e["value"] for e in assists_data}
    shots_map = {e["owner"]["id"]: e["value"] for e in shots_data}

    live = {}
    for pid, info in apps_map.items():
        napps = info["apps"]
        if napps < min_apps:
            continue
        g, g_team = goals_map.get(pid, (0, None))
        a = assists_map.get(pid, 0)
        s = shots_map.get(pid, 0)
        if g == 0 and a == 0 and s == 0:
            continue
        goals_pg = round(g / napps, 3)
        assists_pg = round(a / napps, 3)
        shots_pg = round(s / napps, 3)
        live[info["name"]] = {
            "GOALS": goals_pg,
            "ASSISTS": assists_pg,
            "SHOTS": shots_pg,
            "GOALS_std": round(goals_pg * 0.80, 3),
            "ASSISTS_std": round(assists_pg * 0.75, 3),
            "SHOTS_std": round(shots_pg * 0.45, 3),
            "n_games": int(napps),
            "team": info["team"] if info["team"] != "Unknown" else (g_team or "Unknown"),
            "source": "live_epl_pulse"
        }

    if live:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(live, f)
        except Exception:
            pass
    return live



def fetch_mls_live_player_stats(competition_id="MLS-COM-000001", season_id="MLS-SEA-0001KA", min_apps=5):
    """Fetch live current-season MLS player stats from the league's own public
    sportapi.mlssoccer.com API -- no auth, no key, discovered from a real
    browser Network-tab capture of mlssoccer.com/stats/players/. Confirmed
    against known players before use: Messi 12g/7a, Suarez 6g/1a this season.

    Returns per-game GOALS/ASSISTS/SHOTS/XG for every MLS player with
    >= min_apps matches played. season_id must be refreshed each MLS season
    (capture a fresh request from mlssoccer.com/stats/players/ via DevTools
    Network tab and read the season id out of the request URL).
    """
    cache_path = os.path.join(CACHE_DIR, "mls_live_stats.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    def _ranked(stat, page_size=100, max_pages=10):
        content = []
        for page in range(1, max_pages + 1):
            url = (f"https://sportapi.mlssoccer.com/api/stats/players/competition/{competition_id}"
                   f"/season/{season_id}/order/{stat}/desc?pageSize={page_size}&page={page}")
            resp = _http.get(url, headers={
                "Origin": "https://www.mlssoccer.com",
                "Referer": "https://www.mlssoccer.com/"
            }, timeout=12)
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            content.extend(batch)
            if len(batch) < page_size:
                break
        return content

    try:
        players = _ranked("matches_played")
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_mls_live_player_stats",
            "error": str(e)[:100]
        })
        return {}

    live = {}
    for p in players:
        napps = p.get("matches_played") or 0
        if napps < min_apps:
            continue
        name = f"{p.get('player_first_name', '')} {p.get('player_last_name', '')}".strip()
        if not name:
            continue
        g = p.get("goals", 0) or 0
        a = p.get("assists", 0) or 0
        s = p.get("shots_at_goal_sum", 0) or 0
        xg = p.get("xG", 0) or 0
        if g == 0 and a == 0 and s == 0:
            continue
        goals_pg = round(g / napps, 3)
        assists_pg = round(a / napps, 3)
        shots_pg = round(s / napps, 3)
        xg_pg = round(xg / napps, 3)
        live[name] = {
            "GOALS": goals_pg,
            "ASSISTS": assists_pg,
            "SHOTS": shots_pg,
            "XG": xg_pg,
            "GOALS_std": round(goals_pg * 0.80, 3),
            "ASSISTS_std": round(assists_pg * 0.75, 3),
            "SHOTS_std": round(shots_pg * 0.45, 3),
            "n_games": int(napps),
            "team": p.get("team_three_letter_code", "Unknown"),
            "source": "live_mls_sportapi"
        }

    if live:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(live, f)
        except Exception:
            pass
    return live

def fetch_soccer_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "soccer_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            return _safe_load_pkl(cache_path)
    rolling = {}
    for player, stats in PLAYER_AVERAGES_SOCCER.items():
        goals = stats.get("GOALS", 0.3)
        assists = stats.get("ASSISTS", 0.2)
        shots = stats.get("SHOTS", 3.0)
        rolling[player] = {
            "GOALS": goals,
            "ASSISTS": assists,
            "SHOTS": shots,
            "GOALS_std": round(goals * 0.80, 3),
            "ASSISTS_std": round(assists * 0.75, 3),
            "SHOTS_std": round(shots * 0.45, 3),
            "n_games": 10,
            "source": "hardcoded_with_std"
        }

    # Overlay live current-season EPL stats where available -- real per-game
    # rates beat the StatsBomb-tournament-derived static baseline whenever we
    # have them.
    try:
        epl_live = fetch_epl_live_player_stats()
        for player, stats in epl_live.items():
            rolling[player] = stats
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_soccer_rolling_averages/epl_live_overlay",
            "error": str(e)[:100]
        })

    # Overlay live current-season MLS stats where available -- same rationale
    # as the EPL overlay above: real per-game rates beat the static baseline.
    try:
        mls_live = fetch_mls_live_player_stats()
        for player, stats in mls_live.items():
            rolling[player] = stats
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_soccer_rolling_averages/mls_live_overlay",
            "error": str(e)[:100]
        })

    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

def fetch_soccer_club_elo() -> dict:
    """Fetch team ELO ratings from ClubElo (free CSV API, no auth).

    Returns: dict of team_name -> elo_rating (float) for today's rankings.
    Endpoint: http://api.clubelo.com/{YYYY-MM-DD}  →  CSV with Rank,Club,Country,Level,Elo
    Cached 24h. Works from any IP — no datacenter block.

    Usage (opponent quality adjustment):
        elo = st.session_state.get("soccer_club_elo", {})
        opp_elo = elo.get(opponent_team, 1500.0)  # 1500 = average
        elo_adj = (opp_elo - 1500) / 1000          # ~0.0 for avg; +0.5 for elite
    """
    cache_path = os.path.join(CACHE_DIR, "soccer_club_elo.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    elo_map = {}
    today = time.strftime("%Y-%m-%d")
    url = f"http://api.clubelo.com/{today}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return elo_map
        lines = resp.text.strip().split("\n")
        for line in lines[1:]:          # skip header
            parts = line.strip().split(",")
            if len(parts) >= 5:
                club = parts[1].strip()
                try:
                    elo = float(parts[4])
                except (ValueError, IndexError):
                    continue
                elo_map[club] = elo
        if elo_map:
            try:
                with open(cache_path, "wb") as f:
                    import pickle
                    pickle.dump(elo_map, f)
            except Exception:
                pass
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_soccer_club_elo",
            "error": str(e)[:100]
        })
    return elo_map


def fetch_player_season_avg_bdl(player_name, sport="NBA", season=None):
    """
    Fetch season averages for a specific player by name search.
    Used when player isn't in BDL_PLAYER_IDS (e.g. playoff callups).
    """
    if season is None:
        season = _current_nba_season_start_year()
    if not BDL_API_KEY:
        return None
    cache_key = f"bdl_avg_{normalize_name(player_name)}_{season}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            return _safe_load_pkl(cache_path)

    # Budget guard: this is a metered/rate-limited key, and board-paste's
    # parallel analysis can otherwise fire a burst of live calls for every
    # new player in one click. Cap genuinely NEW live calls per session
    # (cache hits above don't count) rather than letting usage scale
    # unbounded with however many players get pasted.
    try:
        _calls = st.session_state.get("_bdl_live_calls_this_session", 0)
        if _calls >= 20:
            return None
        st.session_state["_bdl_live_calls_this_session"] = _calls + 1
    except Exception:
        pass

    try:
        r = _http.get(
            "https://api.balldontlie.io/v1/players",
            headers={"Authorization": BDL_API_KEY},
            params={"search": player_name, "per_page": 3},
            timeout=8
        )
        if r.status_code != 200:
            return None
        players = r.json().get("data", [])
        if not players:
            return None
        pid = players[0]["id"]
        r2 = _http.get(
            "https://api.balldontlie.io/v1/season_averages",
            headers={"Authorization": BDL_API_KEY},
            params={"season": season, "player_ids[]": pid},
            timeout=8
        )
        if r2.status_code != 200:
            return None
        avgs_data = r2.json().get("data", [])
        if not avgs_data:
            return None
        a = avgs_data[0]
        pts = round(float(a.get("pts", 0)), 1)
        reb = round(float(a.get("reb", 0)), 1)
        ast = round(float(a.get("ast", 0)), 1)
        stl = round(float(a.get("stl", 0)), 1)
        blk = round(float(a.get("blk", 0)), 1)
        tov = round(float(a.get("turnover", 0)), 1)
        result = {
            "PTS": pts, "REB": reb, "AST": ast,
            "PRA": round(pts + reb + ast, 1),
            "PTS_REB": round(pts + reb, 1),
            "PTS_AST": round(pts + ast, 1),
            "REB_AST": round(reb + ast, 1),
            "3PM": round(float(a.get("fg3m", 0)), 1),
            "STL": stl,
            "BLK": blk,
            "TO": tov,
            # Standard DraftKings-style NBA classic scoring, used as a
            # reasonable approximation for "Fantasy Score" props since
            # PrizePicks doesn't publish their exact formula.
            "FANTASY": round(pts * 1.0 + reb * 1.2 + ast * 1.5 + stl * 3.0 + blk * 3.0 - tov * 1.0, 1),
        }
        with open(cache_path, "wb") as f:
            pickle.dump(result, f)
        return result
    except (pickle.UnpicklingError, OSError, EOFError):
        return None

def fetch_nba_averages_bdl():
    cache_path = os.path.join(CACHE_DIR, "bdl_nba_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            return _safe_load_pkl(cache_path)
    if not BDL_API_KEY:
        return {}
    allowed, reason = api_budget_check("BDL")
    if not allowed:
        return {}
    ids = list(BDL_PLAYER_IDS.values())
    params = "&".join([f"player_ids[]={pid}" for pid in ids])
    url = f"https://api.balldontlie.io/v1/season_averages?season={_current_nba_season_start_year()}&{params}"
    headers = {"Authorization": BDL_API_KEY}
    try:
        resp = _http.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {}
        data = resp.json().get("data", [])
        id_to_name = {v: k for k, v in BDL_PLAYER_IDS.items()}
        avgs = {}
        for p in data:
            pid = p.get("player_id")
            name = id_to_name.get(pid)
            if not name:
                continue
            pts = round(float(p.get("pts", 0)), 1)
            reb = round(float(p.get("reb", 0)), 1)
            ast = round(float(p.get("ast", 0)), 1)
            avgs[name] = {"PTS": pts, "REB": reb, "AST": ast, "PRA": round(pts + reb + ast, 1)}
        if avgs:
            with open(cache_path, "wb") as f:
                pickle.dump(avgs, f)
        api_budget_increment("BDL")
        return avgs
    except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
        return {}

def fetch_underdog_props(sport):
    sport_map = {"NBA": "NBA", "MLB": "MLB", "NHL": "NHL", "NFL": "NFL", "WNBA": "WNBA"}
    sport_id = sport_map.get(sport)
    if not sport_id:
        return []
    # ── Cache layer (was missing — added for parity with all other fetch functions) ──
    cache_path = os.path.join(CACHE_DIR, f"underdog_props_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 25:
            try:
                with open(cache_path, "rb") as _f:
                    cached = pickle.load(_f)
                if cached:
                    return cached
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
    # Try new v1 lobbies endpoint first (discovered via DevTools May 2026)
    product_exp_id = "018e1234-5678-9abc-def0-123456789006"
    state_config_id = "725014ef-3570-4e93-871d-d69674ab3521"
    url_v1 = (
        f"https://api.underdogfantasy.com/v1/lobbies/content/lines"
        f"?include_live=true&product=fantasy"
        f"&product_experience_id={product_exp_id}"
        f"&show_mass_option_markets=false"
        f"&sport_id={sport_id}"
        f"&state_config_id={state_config_id}"
    )
    url_v2 = f"https://api.underdogfantasy.com/v2/over_under_lines?sport_id={sport_id}"
    url = url_v1
    try:
        ud_headers = {**HEADERS, "Origin": "https://underdogfantasy.com", "Referer": "https://underdogfantasy.com/pick-em"}
        resp = _http.get(url, headers=ud_headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 400 or resp.status_code == 403:
            # Fall back to v2
            resp = _http.get(url_v2, headers=ud_headers, timeout=REQUEST_TIMEOUT)
            url = url_v2
        if resp.status_code != 200:
            return []
        data = resp.json()
        props = []
        seen = set()

        # Detect v1 vs v2 response
        # v1 has "suggested_picks" wrapper, v2 has flat "over_under_lines" list
        is_v1 = "suggested_picks" in data
        sp = data["suggested_picks"] if is_v1 else data

        # Players: dict (v1) or list (v2)
        players_dict = sp.get("players", {})
        if isinstance(players_dict, dict):
            players_map = {pid: f"{p.get('first_name','').strip()} {p.get('last_name','').strip()}".strip()
                          for pid, p in players_dict.items()}
        elif isinstance(players_dict, list):
            players_map = {p["id"]: f"{p.get('first_name','').strip()} {p.get('last_name','').strip()}".strip()
                          for p in players_dict if isinstance(p, dict) and "id" in p}
        else:
            players_map = {}

        # Appearances: dict (v1) or list (v2)
        appearances_dict = sp.get("appearances", {})
        if isinstance(appearances_dict, dict):
            appearances_map = {aid: a.get("player_id","") for aid, a in appearances_dict.items()}
        elif isinstance(appearances_dict, list):
            appearances_map = {a["id"]: a.get("player_id","") for a in appearances_dict if isinstance(a, dict)}
        else:
            appearances_map = {}

        # over_under_lines: dict (v1) or list (v2)
        oul = sp.get("over_under_lines", {})
        if isinstance(oul, dict):
            lines_list = list(oul.values())
        elif isinstance(oul, list):
            lines_list = oul
        else:
            lines_list = []

        # Filter by sport
        sport_id = sport.upper()
        teams_dict = sp.get("teams", {})
        games_dict = sp.get("games", {})

        for line in lines_list:
            if line.get("status","") == "closed":
                continue

            line_val = line.get("stat_value")
            if line_val is None:
                continue

            # Get player name from options[0].selection_header (most reliable)
            options = line.get("options", [])
            if options:
                opt = options[0]
                name = opt.get("selection_header","").strip()
                stat_name = opt.get("stat_display","").strip()
                if not stat_name:
                    stat_name = opt.get("selection_subheader","").split(" ", 2)[-1] if opt.get("selection_subheader") else ""
            else:
                # Fallback: use over_under.appearance_stat
                ou = line.get("over_under", {})
                app_stat = ou.get("appearance_stat", {})
                app_id = app_stat.get("appearance_id","")
                player_id = appearances_map.get(app_id,"")
                name = players_map.get(player_id,"")
                stat_name = app_stat.get("display_stat","")

            if not name or not stat_name:
                continue

            # Sport filter: check player sport via appearances/games
            ou = line.get("over_under", {})
            app_stat = ou.get("appearance_stat", {})
            app_id = app_stat.get("appearance_id","")
            app_data = appearances_dict.get(app_id, {}) if isinstance(appearances_dict, dict) else {}
            match_id = str(app_data.get("match_id",""))
            game = games_dict.get(match_id, {}) if isinstance(games_dict, dict) else {}
            game_sport = game.get("sport_id","")

            if game_sport and game_sport.upper() != sport_id:
                continue

            key = (sport, name, stat_name, line_val)
            if key in seen:
                continue
            seen.add(key)
            props.append({
                "Player": name,
                "Prop": stat_name,
                "Line": float(line_val),
                "Side": "OVER",
                "Sport": sport,
                "source": "Underdog",
                "Book": "Underdog",
            })

        if not props and lines_list:
            # If sport filter removed everything, return without filter
            for line in lines_list[:50]:
                if line.get("status","") == "closed":
                    continue
                line_val = line.get("stat_value")
                options = line.get("options", [])
                if options and line_val:
                    opt = options[0]
                    name = opt.get("selection_header","").strip()
                    stat_name = opt.get("stat_display","").strip()
                    if name and stat_name:
                        key = (sport, name, stat_name, line_val)
                        if key not in seen:
                            seen.add(key)
                            props.append({"Player": name, "Prop": stat_name,
                                        "Line": float(line_val), "Side": "OVER",
                                        "Sport": sport, "source": "Underdog", "Book": "Underdog"})
        if props:
            try:
                with open(cache_path, "wb") as _f:
                    pickle.dump(props, _f)
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
        return props
    except (IOError, ValueError) as e:
        print(f"Underdog props error: {e}")
        return []

def scrape_prizepicks(sport):
    league_ids = {"NBA": 4, "MLB": 5, "NHL": 3, "NFL": 7, "WNBA": 8, "UFC": 6, "Golf": 11, "Tennis": 12, "Soccer": 2}
    league = league_ids.get(sport.upper())
    if not league:
        return []
    state_code = st.secrets.get("PP_STATE_CODE", "CA")
    urls = [
        # Primary: CDN endpoint — CloudFront, no Akamai protection
        "https://static.prizepicks.com/projections.json",
        # Fallback 1: partner API
        f"https://partner-api.prizepicks.com/projections?per_page=1000&league_id={league}",
        # Fallback 2: confirmed working URL May 2026
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code={state_code}&game_mode=prizepools",
        # Fallback 3: pickem game mode (separate market pool from prizepools)
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code={state_code}&game_mode=pickem",
        # Fallback 4: without game_mode
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250&single_stat=true&in_game=true&state_code={state_code}",
        # Fallback 5: basic API
        f"https://api.prizepicks.com/projections?league_id={league}&per_page=250",
    ]
    # Last-known-good cache path — written on every successful fetch, read when all paths fail
    _lkg_path = os.path.join(CACHE_DIR, f"pp_last_known_good_{sport}.pkl")

    # ── Real-browser header capture, 2026-06-21 ──────────────────────────
    # CDP-attached capture of this EXACT endpoint (fallback 2 above) loading
    # successfully in a real, logged-in browser session, no captcha/block,
    # showed two concrete gaps vs what this function was sending: (1) a
    # custom "x-device-info" header was present and is completely absent
    # here, (2) the real x-device-id was a per-install UUID, not a static
    # string — sending the literal same "betcouncil-v46" on every single
    # request across every session is itself a plausible bot signature.
    # Notably the real request had NO cookie at all, confirming this is
    # genuinely stateless — no PerimeterX/Caesars-style token harvest needed
    # here, just closer header fidelity.
    _device_id_path = os.path.join(CACHE_DIR, "pp_device_id.txt")

    # ── device_id load: local file → Gist fallback → generate new ────────────
    # Streamlit Cloud ephemeral filesystem resets on every redeploy, so
    # CACHE_DIR/pp_device_id.txt is wiped each time.  We fall back to a Gist
    # file (betcouncil_device_fingerprint.json) that survives redeploys, keeping
    # the same UUID across deploys and avoiding a fingerprint reset that flags
    # the scraper as a new device.
    #   Read order:  local file  →  Gist  →  generate new UUID
    #   Write order: local file  +  Gist (only when generating a new UUID)
    def _read_device_id_from_gist() -> str:
        """Fetch device_id from betcouncil_device_fingerprint.json in the Gist."""
        data = _read_gist_file("betcouncil_device_fingerprint.json", cache_minutes=5)
        return data.get("device_id", "") if data else ""

    def _write_device_id_to_gist(did: str) -> None:
        """Persist device_id to Gist so it survives Streamlit redeploys."""
        if not GITHUB_TOKEN or not GITHUB_GIST_ID:
            return
        try:
            _http.patch(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "files": {
                        "betcouncil_device_fingerprint.json": {
                            "content": json.dumps({"device_id": did})
                        }
                    }
                },
                timeout=10,
            )
        except Exception:
            pass

    # 1. Try local file (fast path — no network call)
    _device_id = ""
    if os.path.exists(_device_id_path):
        try:
            with open(_device_id_path, "r") as _f:
                _device_id = _f.read().strip()
        except (IOError, OSError):
            _device_id = ""

    # 2. If local file missing/empty (e.g. after a redeploy), try Gist
    if not _device_id:
        _device_id = _read_device_id_from_gist()
        if _device_id:
            # Restore the local file so subsequent calls are fast
            try:
                with open(_device_id_path, "w") as _f:
                    _f.write(_device_id)
            except (IOError, OSError):
                pass

    # 3. Still empty — generate a new UUID and persist to both places
    if not _device_id:
        import uuid as _uuid
        _device_id = str(_uuid.uuid4())
        try:
            with open(_device_id_path, "w") as _f:
                _f.write(_device_id)
        except (IOError, OSError):
            pass
        _write_device_id_to_gist(_device_id)
    _device_info = (
        f"anonymousId=,name=,os=windows,osVersion=Windows NT 10.0; Win64; x64,"
        f"platform=web,appVersion=,gameMode=prizepools,stateCode={state_code}"
    )

    pp_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
        "Referer": "https://app.prizepicks.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Origin": "https://app.prizepicks.com",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Cache-Control": "no-cache",
        "x-device-id": _device_id,
        "x-device-info": _device_info,
    }
    # ── _normalize_pp_gist — shared by Gist-first, chrome110 parse, and bottom fallback ──
    def _normalize_pp_gist(p, _sport=sport):
        """Normalize a Gist/API prop to the canonical live scrape output shape.

        Live scrape produces: {Player, Prop, Line (float), Side, Sport, source, OddsType}
        Gist and alternate sources may use different key casing or names.
        """
        player = p.get("Player") or p.get("player") or p.get("name", "")
        prop   = p.get("Prop")   or p.get("prop")   or p.get("stat_type", "")
        line   = p.get("Line")   or p.get("line",    0)
        try:
            line = float(line)
        except (TypeError, ValueError):
            line = 0.0
        return {
            "Player":   player,
            "Prop":     prop,
            "Line":     line,
            "Side":     p.get("Side")  or p.get("side",      "OVER"),
            "Sport":    p.get("Sport") or p.get("sport",     _sport),
            "source":   "PrizePicks",
            "Book":     "PrizePicks",
            "OddsType": p.get("OddsType") or p.get("odds_type", "standard"),
        }

    # ── GIST-FIRST: Gist is the primary reliable source when ScrapeOps is exhausted ──
    # fetch_auto_scraped_props() fetches the auto_scraped_props.json file from the
    # configured GitHub Gist (pushed by the background auto-scraper).  It validates
    # freshness (same-day date check) and filters by sport before returning.  This is
    # much faster than the URL loop below and avoids burning curl_cffi retries on
    # endpoints that have been 403-ing consistently.
    try:
        _gist_early = fetch_auto_scraped_props(sport)
        if _gist_early:
            _pp_early = [p for p in _gist_early
                         if "prizepicks" in str(p.get("source", "")).lower()
                         or p.get("Book", "") == "PrizePicks"]
            if not _pp_early:
                # Accept any source from Gist if no PrizePicks-tagged rows
                _pp_early = _gist_early
            _norm_early = [
                _normalize_pp_gist(p) for p in _pp_early
                if p.get("Player") or p.get("player") or p.get("name")
            ]
            if _norm_early:
                log_error_to_session(
                    "scrape_prizepicks",
                    f"Gist-first: returned {len(_norm_early)} {sport} props",
                    "info",
                )
                try:
                    with open(_lkg_path, "wb") as _lf: pickle.dump(_norm_early, _lf)
                except OSError:
                    pass
                return _norm_early
    except Exception as _gist_early_e:
        log_error_to_session(
            "scrape_prizepicks",
            f"Gist-first attempt failed: {str(_gist_early_e)[:80]}",
            "warning",
        )

    all_props = []
    seen = set()
    for url in urls:
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}_pp.pkl")
        data = None
        if os.path.exists(cache_path):
            age = (time.time() - os.path.getmtime(cache_path)) / 60
            if age < 20:
                try:
                    cached = _safe_load_pkl(cache_path)
                    # Only use cache if it has real data (not a 403 error cache)
                    if cached and cached.get("data") and len(cached.get("data", [])) > 0:
                        data = cached
                    else:
                        os.remove(cache_path)  # Clear bad cache
                except (IOError, ValueError):
                    try: os.remove(cache_path)
                    except Exception: pass
        if data is None:
            try:
                # ── Attempt 1: curl_cffi with Chrome TLS fingerprint ──
                # Mimics real Chrome at the TLS layer — may bypass Akamai
                # without ScrapeOps proxy. Silent fallback if unavailable.
                _cffi_success = False
                try:
                    from curl_cffi import requests as cffi_requests
                    _cffi_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
                        "accept": "application/json, text/plain, */*",
                        "accept-language": "en-US,en;q=0.9",
                        "accept-encoding": "gzip, deflate, br, zstd",
                        "content-type": "application/json",
                        "origin": "https://app.prizepicks.com",
                        "referer": "https://app.prizepicks.com/",
                        "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "sec-fetch-dest": "empty",
                        "sec-fetch-mode": "cors",
                        "sec-fetch-site": "same-site",
                        "x-device-id": _device_id,
                        "x-device-info": _device_info,
                    }
                    _cffi_resp = cffi_requests.get(
                        url, headers=_cffi_headers,
                        impersonate="chrome124", timeout=15
                    )
                    if _cffi_resp.status_code == 200:
                        content_type = _cffi_resp.headers.get("content-type","")
                        if "html" not in content_type and not _cffi_resp.text.strip().startswith("<"):
                            data = _cffi_resp.json()
                            _cffi_success = True
                            log_error_to_session("scrape_prizepicks_cffi", f"200 OK on {url[-40:]}", "info")
                        else:
                            log_error_to_session("scrape_prizepicks_cffi", f"200 but HTML/captcha body on {url[-40:]}", "warning")
                    else:
                        # Previously this branch was completely silent — added
                        # 2026-06-21 specifically to verify whether the
                        # x-device-info header fix actually changes the
                        # response (was a 403 before; if still 403, the header
                        # fix didn't help and the real blocker is elsewhere).
                        log_error_to_session("scrape_prizepicks_cffi", f"HTTP {_cffi_resp.status_code} on {url[-40:]}", "warning")
                except ImportError:
                    log_error_to_session("scrape_prizepicks_cffi", "curl_cffi not installed", "warning")
                except (requests.RequestException, KeyError, ValueError) as _cffi_e:
                    log_error_to_session("scrape_prizepicks_cffi", f"{type(_cffi_e).__name__}: {str(_cffi_e)[:80]} on {url[-40:]}", "warning")

                # ── Attempt 2: ScrapeOps residential proxy ──────────────────
                # Guard: skip entirely when SCRAPEOPS_KEY is empty (exhausted /
                # not configured). Falls through to the Gist fallback below.
                # Also fixes the prior scrapeops_get() NameError — that helper
                # was never defined; replaced with a direct requests.get using
                # the standard ScrapeOps proxy URL pattern.
                #
                # EXHAUSTION GATE (2026-07): this path used to fire regardless
                # of known exhaustion — it never checked session_state or the
                # Gist before calling, unlike scrapeops_get() elsewhere. That
                # meant it kept burning/re-hitting a dead key on every URL in
                # this loop (up to 6) for every sport on every board load.
                # Same check as scrapeops_get(), scoped by month.
                _pp_so_exhausted = st.session_state.get("scrapeops_exhausted", False)
                if not _pp_so_exhausted:
                    _pp_so_gist = load_from_gist("scrapeops_status", None)
                    if _pp_so_gist and _pp_so_gist.get("exhausted") and _pp_so_gist.get("month") == datetime.now().strftime("%Y-%m"):
                        _pp_so_exhausted = True
                        st.session_state["scrapeops_exhausted"] = True
                if not _cffi_success and SCRAPEOPS_KEY and not _pp_so_exhausted:
                    try:
                        from urllib.parse import quote as _q
                        _so_url = (
                            f"https://proxy.scrapeops.io/v1/?api_key={SCRAPEOPS_KEY}"
                            f"&url={_q(url, safe='')}&residential=true"
                        )
                        resp = _http.get(_so_url, headers=pp_headers, timeout=20)
                        _pp_quota_phrases = ("insufficient credit", "credit limit", "quota exceeded",
                                             "out of credits", "usage limit", "no credits remaining")
                        _pp_body_exhausted = (
                            resp.status_code == 200 and
                            any(_p in resp.text[:500].lower() for _p in _pp_quota_phrases)
                        )
                        if resp.status_code in (403, 429, 402) or _pp_body_exhausted:
                            st.session_state["scrapeops_exhausted"] = True
                            save_to_gist("scrapeops_status", {"exhausted": True, "month": datetime.now().strftime("%Y-%m")})
                        if resp.status_code == 200 and not _pp_body_exhausted:
                            # Check for captcha response (returns HTML not JSON)
                            content_type = resp.headers.get("content-type", "")
                            if "html" in content_type or resp.text.strip().startswith("<"):
                                continue
                            data = resp.json()
                            if data and data.get("data"):
                                with open(cache_path, "wb") as f:
                                    pickle.dump(data, f)
                        elif resp.status_code == 429:
                            time.sleep(2)
                            continue
                        elif resp.status_code == 403:
                            # Bot protection — try next URL
                            continue
                    except (requests.RequestException, ValueError, KeyError, TypeError, OSError):
                        pass
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        if not data or not data.get("data"):
            continue
        for proj in data["data"]:
            if proj["type"] != "projection":
                continue
            # CDN endpoint returns all sports — filter by league_id
            # Check multiple possible locations for league ID
            _proj_league = None
            _rel_league = proj.get("relationships",{}).get("league",{}).get("data",{})
            if _rel_league:
                _proj_league = str(_rel_league.get("id",""))
            _attrs_check = proj.get("attributes",{})
            if not _proj_league:
                _proj_league = str(_attrs_check.get("league_id",""))
            # Only filter if we found a league ID AND it doesn't match
            if _proj_league and _proj_league not in (str(league), "", "None"):
                continue
            attrs = proj["attributes"]
            pid = proj["relationships"]["new_player"]["data"]["id"]
            name = attrs.get("display_name", "") or attrs.get("name", "")
            if not name:
                continue
            line = attrs.get("line_score")
            stat = attrs.get("stat_type")
            if line is None or not stat:
                continue
            try:
                line = float(line)
            except (ValueError, TypeError):
                continue
            key = (sport, pid, stat, line)
            if key in seen:
                continue
            seen.add(key)
            odds_type = attrs.get("odds_type", "standard")
            all_props.append({"Player": name, "Prop": stat, "Line": line, "Side": "OVER", "Sport": sport, "source": "PrizePicks", "OddsType": odds_type})
    if all_props:
        try:
            with open(_lkg_path, "wb") as _lf: pickle.dump(all_props, _lf)
        except OSError:
            pass
        return all_props

    # ── CHROME110 DIRECT: second fallback — curl_cffi chrome110 fingerprint ─────────────
    # Targets https://api.prizepicks.com/projections directly with the exact Origin/Referer
    # headers PrizePicks expects from app.prizepicks.com.  Uses chrome110 TLS fingerprint
    # (distinct from chrome124 used above) to try a different fingerprint profile that may
    # bypass Akamai bot detection.  Runs only after the URL loop fails so it does not add
    # latency on the happy path.
    try:
        from curl_cffi import requests as _c110_req
        _c110_url = (
            f"https://api.prizepicks.com/projections"
            f"?league_id={league}&per_page=250&single_stat=true&state_code={state_code}"
        )
        _c110_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://app.prizepicks.com",
            "Referer": "https://app.prizepicks.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "sec-ch-ua": '"Chromium";v="110", "Google Chrome";v="110", "Not A;Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "x-device-id": _device_id,
            "x-device-info": _device_info,
        }
        _c110_resp = _c110_req.get(
            _c110_url,
            headers=_c110_headers,
            impersonate="chrome110",
            timeout=15,
        )
        if _c110_resp.status_code == 200:
            _c110_ct = _c110_resp.headers.get("content-type", "")
            if "html" not in _c110_ct and not _c110_resp.text.strip().startswith("<"):
                _c110_data = _c110_resp.json()
                _c110_props = []
                _c110_seen: set = set()
                for _proj in (_c110_data.get("data") or []):
                    if _proj.get("type") != "projection":
                        continue
                    _attrs = _proj.get("attributes") or {}
                    _rel   = _proj.get("relationships") or {}
                    # League filter
                    _proj_league = str(
                        (_rel.get("league") or {}).get("data", {}).get("id", "")
                        or _attrs.get("league_id", "")
                    )
                    if _proj_league and _proj_league not in (str(league), "", "None"):
                        continue
                    _pid  = (_rel.get("new_player") or {}).get("data", {}).get("id", "")
                    _name = _attrs.get("display_name", "") or _attrs.get("name", "")
                    _line = _attrs.get("line_score")
                    _stat = _attrs.get("stat_type")
                    if not _name or _line is None or not _stat:
                        continue
                    try:
                        _line = float(_line)
                    except (ValueError, TypeError):
                        continue
                    _key = (sport, _pid, _stat, _line)
                    if _key in _c110_seen:
                        continue
                    _c110_seen.add(_key)
                    _c110_props.append({
                        "Player":   _name,
                        "Prop":     _stat,
                        "Line":     _line,
                        "Side":     "OVER",
                        "Sport":    sport,
                        "source":   "PrizePicks",
                        "OddsType": _attrs.get("odds_type", "standard"),
                    })
                if _c110_props:
                    log_error_to_session(
                        "scrape_prizepicks_chrome110",
                        f"chrome110 direct: returned {len(_c110_props)} {sport} props",
                        "info",
                    )
                    try:
                        with open(_lkg_path, "wb") as _lf: pickle.dump(_c110_props, _lf)
                    except OSError:
                        pass
                    return _c110_props
                else:
                    log_error_to_session(
                        "scrape_prizepicks_chrome110",
                        "200 OK but 0 projections parsed",
                        "warning",
                    )
            else:
                log_error_to_session(
                    "scrape_prizepicks_chrome110",
                    "200 OK but response body is HTML/captcha",
                    "warning",
                )
        else:
            log_error_to_session(
                "scrape_prizepicks_chrome110",
                f"HTTP {_c110_resp.status_code} from api.prizepicks.com",
                "warning",
            )
    except ImportError:
        log_error_to_session(
            "scrape_prizepicks_chrome110",
            "curl_cffi not installed — skipping chrome110 attempt",
            "warning",
        )
    except Exception as _c110_e:
        log_error_to_session(
            "scrape_prizepicks_chrome110",
            f"{type(_c110_e).__name__}: {str(_c110_e)[:80]}",
            "warning",
        )

    # ── GIST FALLBACK (existing path — do not break) ────────────────────────────────────
    # Note: _normalize_pp_gist is now defined at the top of this function so the
    # definition block that used to live here has been removed (same function, same logic).
    try:
        _gist_props = fetch_auto_scraped_props(sport)
        if _gist_props:
            _pp_gist = [p for p in _gist_props
                        if "prizepicks" in str(p.get("source","")).lower()
                        or p.get("Book","") == "PrizePicks"]
            if _pp_gist:
                # Normalize to live-scrape format before returning
                _normalized = [_normalize_pp_gist(p) for p in _pp_gist
                               if p.get("Player") or p.get("player") or p.get("name")]
                if _normalized:
                    return _normalized
            elif _gist_props:
                # Non-PrizePicks auto-scraped fallback — still normalize
                # so callers don't see a different key shape
                _normalized = [_normalize_pp_gist(p) for p in _gist_props
                               if p.get("Player") or p.get("player") or p.get("name")]
                if _normalized:
                    return _normalized
    except (KeyError, TypeError, ValueError) as _e:
            print(f"[WARN] {_e}")
    # ── Last-known-good: serve stale props with warning rather than bare [] ──
    # All live paths failed. If we have a prior successful fetch, return it with
    # a staleness warning so the UI degrades gracefully instead of going blank.
    try:
        if os.path.exists(_lkg_path):
            _lkg_age_h = (time.time() - os.path.getmtime(_lkg_path)) / 3600
            # A slate is only valid for the day it's posted — PrizePicks props
            # for yesterday's games (e.g. a player who already played) will
            # still look like a normal props list and can surface as a top
            # edge / Lock of the Day if served past their game day. Refuse to
            # serve anything older than one slate cycle instead of silently
            # treating it as current data.
            if _lkg_age_h > 6:
                log_error_to_session(
                    "scrape_prizepicks",
                    f"Last-known-good cache is {_lkg_age_h:.1f}h old — too stale "
                    "to serve (likely yesterday's slate). Treating as unavailable.",
                    "error",
                )
                return []
            with open(_lkg_path, "rb") as _lf:
                _lkg_data = pickle.load(_lf)
            if _lkg_data:
                log_error_to_session(
                    "scrape_prizepicks",
                    f"All live paths failed — serving last-known-good cache "
                    f"({_lkg_age_h:.1f}h old, {len(_lkg_data)} props). "
                    "Gist auto-scraper may be stale.",
                    "warning",
                )
                return _lkg_data
    except (OSError, pickle.UnpicklingError, EOFError):
        pass
    return []  # Truly nothing available

def fetch_underdog_injuries(sport):
    sport_map = {"NBA": "NBA", "MLB": "MLB", "NFL": "NFL", "NHL": "NHL"}
    sport_id = sport_map.get(sport)
    if not sport_id:
        return {}
    url = f"https://api.underdogfantasy.com/v2/news_items?sport_id={sport_id}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        injuries = {}
        for item in resp.json().get("news_items", []):
            content = item.get("content", "").lower()
            player = item.get("player", {})
            name = f"{player.get('first_name','')} {player.get('last_name','')}".strip()
            if not name:
                continue
            import_time = item.get("created_at", "")
            if import_time:
                try:
                    item_dt = datetime.fromisoformat(import_time.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - item_dt).total_seconds() / 3600
                    if age_hours > 48:
                        continue
                except Exception:
                    pass
            if "out" in content and "ruled out" in content:
                injuries[name] = "Out"
            elif "questionable" in content or "day-to-day" in content:
                injuries[name] = "Questionable"
        return injuries
    except Exception as e:
        print(f"Underdog injuries error: {e}")
        return {}

def fetch_espn_injuries(sport):
    """
    ESPN injury report — Tier 4 injury source (after Underdog/CBS/RotoWire).
    Uses the same ESPN API infrastructure already trusted by the app.
    Returns list of {player, status, note, sport, source} dicts.
    
    Endpoint: site.api.espn.com/apis/site/v2/sports/{path}/injuries
    Free, no key, no auth — same as all other ESPN endpoints.
    """
    slug = ESPN_SLUG_MAP.get(sport)
    if not slug:
        return []
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{slug}/injuries"
        r = _http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        results = []
        # ESPN returns injuries grouped by team
        for team in data.get("injuries", []):
            team_abbr = team.get("team", {}).get("abbreviation", "")
            for injury in team.get("injuries", []):
                athlete = injury.get("athlete", {})
                player_name = athlete.get("displayName", "")
                status_obj  = injury.get("status", "")
                detail      = injury.get("details", {})
                # Normalize status
                raw_status  = (detail.get("type") or status_obj or "").upper()
                if "OUT" in raw_status or "DOUBTFUL" in raw_status:
                    status = "OUT" if "OUT" in raw_status else "DOUBTFUL"
                elif "QUEST" in raw_status:
                    status = "QUESTIONABLE"
                elif "PROB" in raw_status:
                    status = "PROBABLE"
                elif raw_status in ("", "ACTIVE"):
                    continue  # Skip healthy players
                else:
                    status = "QUESTIONABLE"
                note = detail.get("detail", "") or injury.get("longComment", "")[:150]
                if player_name:
                    results.append({
                        "player": player_name,
                        "status": status,
                        "note":   note[:150],
                        "team":   team_abbr,
                        "sport":  sport,
                        "source": "ESPN",
                    })
        return results
    except (requests.RequestException, ValueError, KeyError):
        return []

def fetch_espn_depth_charts(sport):
    """
    ESPN depth charts — exposes RB/WR/QB depth for NFL,
    starting lineup depth for NBA, rotation for MLB.
    
    Key use case: if RB1 is questionable, is RB2 worth a prop?
    If cleanup hitter is scratched, who moves up?
    
    Returns dict: {team_abbr: {position: [player1, player2, ...]}}
    Endpoint: site.api.espn.com/apis/site/v2/sports/{path}/teams/{id}/depthcharts
    """
    slug = ESPN_SLUG_MAP.get(sport)
    if not slug:
        return {}
    # High value sports for depth charts
    if sport not in ("NFL", "NBA", "MLB", "WNBA"):
        return {}
    try:
        # First get team list
        teams_url = f"https://site.api.espn.com/apis/site/v2/sports/{slug}/teams?limit=50"
        r = _http.get(teams_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return {}
        teams = r.json().get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        depth_charts = {}
        # Fetch depth chart for each team (limit to avoid rate limiting)
        for team_data in teams[:32]:
            team = team_data.get("team", {})
            team_id   = team.get("id")
            team_abbr = team.get("abbreviation", "")
            if not team_id:
                continue
            try:
                dc_url = f"https://site.api.espn.com/apis/site/v2/sports/{slug}/teams/{team_id}/depthcharts"
                rd = _http.get(dc_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                if rd.status_code != 200:
                    continue
                dc_data = rd.json()
                positions = {}
                for pos_group in dc_data.get("positionGroups", []):
                    pos_name = pos_group.get("position", {}).get("abbreviation", "")
                    players = []
                    for slot in pos_group.get("athletes", []):
                        pname = slot.get("athlete", {}).get("displayName", "")
                        depth = slot.get("rank", 99)
                        if pname:
                            players.append({"name": pname, "depth": depth})
                    players.sort(key=lambda x: x["depth"])
                    if players and pos_name:
                        positions[pos_name] = players
                if positions:
                    depth_charts[team_abbr] = {
                        "positions": positions,
                        "fetched_at": datetime.now().strftime("%H:%M"),
                    }
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return depth_charts
    except (requests.RequestException, ValueError, KeyError):
        return {}

def fetch_cbs_injuries(sport):
    """
    CBS Sports injury feed — Tier 2 injury source.
    Free RSS, no key needed, different infrastructure from RotoWire.
    Provides redundancy when RotoWire/ESPN are unavailable.
    """
    CBS_SPORT_MAP = {
        "NBA": "nba", "MLB": "mlb", "NFL": "nfl",
        "NHL": "nhl", "WNBA": "wnba",
    }
    cbs_sport = CBS_SPORT_MAP.get(sport)
    if not cbs_sport:
        return []
    try:
        urls = [
            f"https://www.cbssports.com/rss/headlines/fantasy/{cbs_sport}/",
            f"https://www.cbssports.com/{cbs_sport}/players/injuries/",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        for url in urls:
            try:
                r = _http.get(url, headers=headers, timeout=8)
                if r.status_code != 200:
                    continue
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.content)
                channel = root.find("channel")
                if channel is None:
                    continue
                results = []
                for item in channel.findall("item")[:20]:
                    title_el = item.find("title")
                    desc_el  = item.find("description")
                    title = (title_el.text or "").strip() if title_el is not None else ""
                    desc  = (desc_el.text or "").strip()[:150] if desc_el is not None else ""
                    if not title:
                        continue
                    if ":" in title:
                        player, note = title.split(":", 1)
                    else:
                        player, note = title, desc
                    note_lower = note.lower()
                    if any(w in note_lower for w in ("out","ruled out","won't play","dnp")):
                        status = "OUT"
                    elif "doubtful" in note_lower:
                        status = "DOUBTFUL"
                    elif any(w in note_lower for w in ("questionable","limited","day-to-day")):
                        status = "QUESTIONABLE"
                    elif any(w in note_lower for w in ("probable","likely")):
                        status = "PROBABLE"
                    else:
                        status = "NEWS"
                    results.append({
                        "player": player.strip(),
                        "status": status,
                        "note":   note.strip()[:150],
                        "sport":  sport,
                        "source": "CBS Sports",
                    })
                if results:
                    return results
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return []
    except (requests.RequestException, ValueError, KeyError):
        return []

def fetch_rotowire_injuries(sport):
    """
    Fetch injury/news feed from RotoWire RSS — free, no key needed.
    Supplements ESPN injury data with RotoWire's editorial injury intel.
    Returns list of {player, status, note, sport, source} dicts.
    URL format: rotowire.com/rss/news.php?sport=NBA
    """
    SPORT_MAP = {
        "NBA": "NBA", "MLB": "MLB", "NHL": "NHL",
        "NFL": "NFL", "WNBA": "WNBA",
    }
    rw_sport = SPORT_MAP.get(sport)
    if not rw_sport:
        return []
    try:
        url = f"https://www.rotowire.com/rss/news.php?sport={rw_sport}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        # Was using the shared _http retry session -- confirmed real root
        # cause of this consistently hitting the full 25s _fetch_parallel
        # ceiling: urllib3's Retry(total=2) also retries on read timeouts
        # by default, so one slow/tarpitted response (RotoWire likely
        # blocks datacenter IPs, same pattern as several other sources
        # confirmed this session) meant up to ~3 attempts x 10s each plus
        # backoff sleeps -- ~33s worst case, exceeding the 25s ceiling.
        # A plain one-shot request with a short timeout fails fast instead
        # of compounding the wait against a source unlikely to succeed on
        # retry anyway. Direct request — RotoWire blocks proxies too, so
        # no point routing through proxy.
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code != 200:
            return []

        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        channel = root.find("channel")
        if channel is None:
            return []

        results = []
        for item in channel.findall("item")[:20]:
            # Extract CDATA content from title and description
            title_el = item.find("title")
            desc_el  = item.find("description")
            title    = (title_el.text or "").strip() if title_el is not None else ""
            desc     = (desc_el.text or "").strip() if desc_el is not None else ""

            if not title:
                continue

            # RotoWire format: "Player Name: News detail here"
            if ":" in title:
                player_part, news_part = title.split(":", 1)
                player = player_part.strip()
                note   = news_part.strip()
            else:
                player = title
                note   = desc[:150] if desc else ""

            # Detect injury status from keywords
            note_lower = note.lower()
            if any(w in note_lower for w in ("out ", "ruled out", "won't play", "will not play", "did not play")):
                status = "OUT"
            elif any(w in note_lower for w in ("doubtful",)):
                status = "DOUBTFUL"
            elif any(w in note_lower for w in ("questionable", "uncertain", "listed", "probable")):
                status = "QUESTIONABLE"
            elif any(w in note_lower for w in ("day-to-day", "dtd", "limited", "rest")):
                status = "QUESTIONABLE"
            elif any(w in note_lower for w in ("returns", "cleared", "activated", "available", "no injury")):
                status = "AVAILABLE"
            else:
                status = "NEWS"

            results.append({
                "player": player,
                "status": status,
                "note":   note[:200],
                "sport":  sport,
                "source": "RotoWire",
            })

        return results
    except (requests.RequestException, ValueError, KeyError):
        return []


    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NFL": "football/nfl", "NHL": "hockey/nhl"}
    path = slug_map.get(sport, "")
    if not path:
        injuries = {}
    else:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/news"
        try:
            resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                injuries = {}
            else:
                data = resp.json()
                injuries = {}
                for article in data.get("articles", []):
                    headline = article.get("headline", "")
                    if "injury" in headline.lower() or "out" in headline.lower() or "questionable" in headline.lower():
                        players = re.findall(r'([A-Z][a-z]+ [A-Z][a-z]+)', headline)
                        for p in players:
                            if "out" in headline.lower():
                                injuries[p] = "Out"
                            elif "questionable" in headline.lower() or "day-to-day" in headline.lower():
                                injuries[p] = "Questionable"
        except (ValueError, IndexError, AttributeError):
            injuries = {}
    underdog_injuries = fetch_underdog_injuries(sport)
    injuries.update(underdog_injuries)
    return injuries

def _fetch_public_betting_for_date(sport, sport_slug, date_str, an_headers):
    """
    Fetches and parses Action Network public-betting data for a single
    calendar date (YYYYMMDD). Split out of fetch_public_betting() so the
    caller can query multiple dates and merge -- see comment there for why.
    Returns a dict of {game_key: {...}} same as fetch_public_betting(), or
    {} on any failure (never raises, so a bad second-date call can't drop
    a good first-date result).
    """
    url = f"{ACTION_NETWORK_BASE}/{sport_slug}?bookIds={ACTION_NETWORK_BOOK_IDS}&date={date_str}&periods=event"
    try:
        resp = _http.get(url, headers=an_headers, timeout=15)
        api_budget_increment("ACTION_NETWORK")
        if resp.status_code != 200:
            return {}
        data = resp.json()
        games_list = data.get("games", [])
        if not games_list:
            return {}
        public_betting = {}
        for game in games_list:
            teams = game.get("teams", [])
            if len(teams) < 2:
                continue
            team_abbrs = [t.get("abbr", "") for t in teams]
            if len(team_abbrs) < 2:
                continue
            odds_data = game.get("odds", {})
            # Previously hardcoded to book "15" only -- if that one book
            # didn't have odds for a given game (common; no single book
            # covers every game), the whole game was silently dropped via
            # `continue` below, even though 10 other requested books
            # (ACTION_NETWORK_BOOK_IDS) might have had usable data. This is
            # why only one game out of an entire slate was ever showing up.
            # Now tries every requested book ID in order and uses the first
            # one with actual event data.
            event_data = {}
            for _book_id in ACTION_NETWORK_BOOK_IDS.split(","):
                _candidate = odds_data.get(_book_id.strip(), {}).get("event", {})
                if _candidate:
                    event_data = _candidate
                    break
            if not event_data:
                continue
            ml_data = event_data.get("moneyline", [])
            ml_pcts = {}
            for outcome in ml_data:
                side = outcome.get("side", "")
                bet_info = outcome.get("bet_info", {})
                tickets_pct = bet_info.get("tickets", {}).get("percent", 0)
                money_pct = bet_info.get("money", {}).get("percent", 0)
                ml_pcts[side] = {"tickets": tickets_pct, "money": money_pct, "odds": outcome.get("odds", 0)}
            spread_data = event_data.get("spread", [])
            spread_pcts = {}
            for outcome in spread_data:
                side = outcome.get("side", "")
                bet_info = outcome.get("bet_info", {})
                tickets_pct = bet_info.get("tickets", {}).get("percent", 0)
                money_pct = bet_info.get("money", {}).get("percent", 0)
                spread_val = outcome.get("value", 0)
                spread_pcts[side] = {"tickets": tickets_pct, "money": money_pct, "spread": spread_val, "odds": outcome.get("odds", 0)}
            total_data = event_data.get("total", [])
            total_pcts = {}
            for outcome in total_data:
                side = outcome.get("side", "")
                bet_info = outcome.get("bet_info", {})
                tickets_pct = bet_info.get("tickets", {}).get("percent", 0)
                money_pct = bet_info.get("money", {}).get("percent", 0)
                total_pcts[side] = {"tickets": tickets_pct, "money": money_pct, "total": outcome.get("value", 0), "odds": outcome.get("odds", 0)}
            sharp_signals = []
            rlm_signals   = []

            def _sharp_divergence(tickets, money, side_label, market_type):
                """
                Compute sharp/public divergence score.
                tickets% vs money% tells you who is betting.
                Large money% vs small tickets% = sharp money.
                """
                if not tickets or not money:
                    return 0, ""
                diff = money - tickets
                if diff >= 30:
                    score = 3
                    note  = f"💰 Strong sharp: {tickets}% tickets vs {money}% money on {side_label} ({market_type})"
                elif diff >= 20:
                    score = 2
                    note  = f"💰 Sharp: {tickets}% tickets vs {money}% money on {side_label} ({market_type})"
                elif diff >= 12:
                    score = 1
                    note  = f"⚡ Mild sharp: {tickets}% tickets vs {money}% money on {side_label}"
                elif diff <= -20:
                    score = -2
                    note  = f"👥 Public trap: {tickets}% tickets vs {money}% money on {side_label}"
                else:
                    score = 0
                    note  = ""
                return score, note

            # ML divergence
            home_ml  = ml_pcts.get("home", {})
            away_ml  = ml_pcts.get("away", {})
            if home_ml and away_ml:
                h_t = home_ml.get("tickets", 0)
                h_m = home_ml.get("money",   0)
                a_t = away_ml.get("tickets",  0)
                a_m = away_ml.get("money",    0)
                h_score, h_note = _sharp_divergence(h_t, h_m, team_abbrs[0] if team_abbrs else "Home", "ML")
                a_score, a_note = _sharp_divergence(a_t, a_m, team_abbrs[1] if len(team_abbrs)>1 else "Away", "ML")
                if h_score >= 1 and h_note: sharp_signals.append(h_note)
                if a_score >= 1 and a_note: sharp_signals.append(a_note)
                if h_score <= -2 and h_note: sharp_signals.append(h_note)

            # Spread divergence
            home_sprd = spread_pcts.get("home", {})
            away_sprd = spread_pcts.get("away", {})
            if home_sprd and away_sprd:
                hs_score, hs_note = _sharp_divergence(
                    home_sprd.get("tickets",0), home_sprd.get("money",0),
                    team_abbrs[0] if team_abbrs else "Home", "Spread"
                )
                as_score, as_note = _sharp_divergence(
                    away_sprd.get("tickets",0), away_sprd.get("money",0),
                    team_abbrs[1] if len(team_abbrs)>1 else "Away", "Spread"
                )
                if abs(hs_score) >= 1 and hs_note: sharp_signals.append(hs_note)
                if abs(as_score) >= 1 and as_note: sharp_signals.append(as_note)

            # Total divergence + RLM detection
            over_total  = total_pcts.get("over",  {})
            under_total = total_pcts.get("under", {})
            if over_total:
                o_t = over_total.get("tickets",  0)
                o_m = over_total.get("money",    0)
                u_t = under_total.get("tickets", 0) if under_total else 0
                u_m = under_total.get("money",   0) if under_total else 0

                # Sharp divergence on total
                if o_t >= 65 and u_m >= 50:
                    sharp_signals.append(
                        f"🔥 Reverse total: {o_t}% tickets OVER but {u_m}% money UNDER\n"
                        f"   Large bettors opposing public side"
                    )
                    rlm_signals.append({
                        "type":        "TOTAL",
                        "public_side": "OVER",
                        "public_pct":  o_t,
                        "sharp_side":  "UNDER",
                        "money_pct":   u_m,
                        "signal":      "RLM",
                        "strength":    3 if (o_t >= 75 and u_m >= 55) else 2,
                    })
                elif u_t >= 65 and o_m >= 50:
                    sharp_signals.append(
                        f"🔥 Reverse total: {u_t}% tickets UNDER but {o_m}% money OVER\n"
                        f"   Large bettors opposing public side"
                    )
                    rlm_signals.append({
                        "type":        "TOTAL",
                        "public_side": "UNDER",
                        "public_pct":  u_t,
                        "sharp_side":  "OVER",
                        "money_pct":   o_m,
                        "signal":      "RLM",
                        "strength":    3 if (u_t >= 75 and o_m >= 55) else 2,
                    })
                elif o_t >= 80 and o_m >= 75:
                    sharp_signals.append(f"✅ Sharp+Public OVER: {o_t}% tickets {o_m}% money aligned")
            num_bets = game.get("num_bets", 0)
            game_key = f"{team_abbrs[0]}_{team_abbrs[1]}"
            public_betting[game_key] = {
                "teams": team_abbrs,
                "num_bets": num_bets,
                "ml": ml_pcts,
                "spread": spread_pcts,
                "total": total_pcts,
                "sharp_signals": sharp_signals,
                "rlm_signals":   rlm_signals,
                "has_sharp": len(sharp_signals) > 0,
            }
        return public_betting
    except (KeyError, TypeError, ValueError):
        return {}


def fetch_public_betting(sport):
    sport_slug = ACTION_NETWORK_SPORT_MAP.get(sport)
    if not sport_slug:
        return {}
    allowed, reason = api_budget_check("ACTION_NETWORK")
    if not allowed:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"public_betting_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 5:
            return _safe_load_pkl(cache_path)
    an_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.actionnetwork.com",
        "Referer": "https://www.actionnetwork.com/",
    }
    today_str = date.today().strftime("%Y%m%d")
    public_betting = _fetch_public_betting_for_date(sport, sport_slug, today_str, an_headers)
    # Also pull tomorrow's date and merge in any games not already covered.
    # The server clock here runs UTC (Streamlit Cloud), but Action Network
    # buckets games by US Eastern slate day. A late-night West Coast game
    # (e.g. a 10pm ET WNBA tip) can therefore land in AN's "tomorrow"
    # bucket while every earlier game that same night is still "today" --
    # that mismatch is why only one of two same-night games was ever
    # showing public-betting data. Merging both dates closes that gap;
    # `today_str`'s entries take priority since they're the more precise
    # match, tomorrow's are only added if that game_key wasn't already found.
    try:
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y%m%d")
        tomorrow_betting = _fetch_public_betting_for_date(sport, sport_slug, tomorrow_str, an_headers)
        for _gk, _gv in tomorrow_betting.items():
            if _gk not in public_betting:
                public_betting[_gk] = _gv
    except Exception:
        pass
    if public_betting:
        with open(cache_path, "wb") as f:
            pickle.dump(public_betting, f)
    return public_betting


def fetch_game_lines(sport):
    if sport not in ["NBA", "MLB", "NFL", "NHL", "WNBA"]:
        return [], False, {}, {}
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NFL": "football/nfl", "NHL": "hockey/nhl", "WNBA": "basketball/wnba"}
    path = slug_map.get(sport, "")
    if not path:
        return [], False, {}, {}
    def _fetch_date(target_date):
        date_str = target_date.strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={date_str}"
        try:
            resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])
                playoff = any(e.get("season", {}).get("type", 0) == 3 for e in events)
                games = []
                home_teams = {}
                away_teams = {}
                for event in events:
                    matchup = event.get("shortName", "")
                    status = event.get("status", {}).get("type", {}).get("description", "")
                    spread = "N/A"
                    total = "N/A"
                    home_ml = "N/A"
                    away_ml = "N/A"
                    provider = "ESPN"
                    for comp in event.get("competitions", []):
                        odds_data = comp.get("odds", [{}])[0] if comp.get("odds") else {}
                        raw_spread = odds_data.get("details", "N/A")
                        total      = odds_data.get("overUnder", "N/A")
                        home_ml    = odds_data.get("homeTeamOdds", {}).get("moneyLine", "N/A")
                        away_ml    = odds_data.get("awayTeamOdds", {}).get("moneyLine", "N/A")
                        provider   = odds_data.get("provider", {}).get("name", "ESPN")
                        # Validate spread — must contain a decimal point spread value (e.g. "TB -1.5")
                        # ESPN sometimes puts ML odds in the details field for MLB — reject those
                        spread = "N/A"
                        if raw_spread and raw_spread != "N/A":
                            try:
                                # A real spread has a number with .5 or .0 (e.g. -1.5, +2.5, -3.0)
                                parts = str(raw_spread).split()
                                if parts:
                                    spread_num = float(parts[-1].replace("+",""))
                                    # ML odds are typically > 100 in absolute value for MLB
                                    # Spreads in MLB are typically -1.5 or +1.5 (run line)
                                    if abs(spread_num) <= 30:  # valid spread range
                                        spread = raw_spread
                                    # else: it's probably a ML value — leave as N/A for ESPN overlay to fill
                            except (ValueError, IndexError):
                                spread = "N/A"
                        for competitor in comp.get("competitors", []):
                            team = competitor.get("team", {}).get("abbreviation", "")
                            home_away = competitor.get("homeAway", "")
                            if home_away == "home":
                                home_teams[matchup] = team
                            else:
                                away_teams[matchup] = team
                    games.append({"Matchup": matchup, "Status": status, "Spread": spread, "Total": total, "Home ML": home_ml, "Away ML": away_ml, "Odds Source": provider, "Date": target_date.strftime("%a %b %d"), "Sport": sport})
                return games, playoff, home_teams, away_teams
        except Exception as e:
            print(f"ESPN fetch error: {e}")
        return [], False, {}, {}
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_games, playoff, home_teams, away_teams = _fetch_date(today)
    all_final = all(g["Status"].lower() in ("final", "game over", "final/ot", "final/so", "postponed") for g in today_games) if today_games else True
    if all_final:
        tomorrow_games, playoff, home_teams, away_teams = _fetch_date(tomorrow)
        if tomorrow_games:
            today_games = tomorrow_games

    # ── Definitive ESPN abbrev → full-name fragment mapping ──
    # Covers every MLB team + all major sports. Hoisted out of the
    # ODDS_API_KEY block below so the BetOnline fallback pass (which
    # doesn't depend on that secret) can reuse the same matching logic.
    # ── ESPN/Action-Network-style abbrev -> full-name fragment mapping ──
    # Moved to config.py as TEAM_ABBREV_TO_FRAGMENT (sport-separated, since
    # abbreviations like "TB"/"SF"/"TOR"/"WSH" collide across leagues and a
    # flat dict was silently dropping entries to the last sport defined).
    TEAM_ABBREV_TO_FRAGMENT = _TEAM_ABBREV_TO_FRAGMENT_BY_SPORT.get(sport, {})

    # ── SBR/OddsAPI overlay — SBR primary (no key needed), OddsAPI fallback ──
    # fetch_odds_api_game_lines() tries SBR first; falls back to OddsAPI
    # only when ODDS_API_KEY is set and api_budget_check("ODDS_API") passes.
    try:
        odds_games, odds_home, odds_away = fetch_odds_api_game_lines(sport)
        if odds_games:
            odds_lookup = {g["Matchup"]: g for g in odds_games}

            for game in today_games:
                matchup = game.get("Matchup","")
                home1 = home_teams.get(matchup, "")
                away1 = away_teams.get(matchup, "")
                best_match = None

                # Get both team abbrevs from matchup "AWAY @ HOME"
                esp_parts = [t.strip().upper() for t in matchup.split("@")] if "@" in matchup else []

                for odds_matchup, odds_game in odds_lookup.items():
                    home2 = odds_home.get(odds_matchup, "").upper()
                    away2 = odds_away.get(odds_matchup, "").upper()
                    both  = home2 + " " + away2

                    matched = False
                    for abbr in esp_parts:
                        if not abbr or len(abbr) < 2:
                            continue
                        # Direct: abbrev appears in full team name
                        if abbr in home2 or abbr in away2:
                            matched = True; break
                        # Fragment lookup: known mapping
                        frag = TEAM_ABBREV_TO_FRAGMENT.get(abbr,"").upper()
                        if frag and frag in both:
                            matched = True; break
                        # Fallback: first 3 chars of SBR name vs ESPN abbrev
                        if len(home2) >= 3 and home2[:3] in abbr:
                            matched = True; break
                        if len(away2) >= 3 and away2[:3] in abbr:
                            matched = True; break

                    if matched:
                        best_match = odds_game
                        break
                if best_match:
                    # Always store SBR/OddsAPI data as backup fields
                    game["OddsAPI ML Home"] = best_match.get("Home ML", "N/A")
                    game["OddsAPI ML Away"] = best_match.get("Away ML", "N/A")
                    game["OddsAPI Spread"]  = best_match.get("Spread", "N/A")
                    game["OddsAPI Total"]   = best_match.get("Total", "N/A")
                    game["OddsAPI Source"]  = best_match.get("Odds Source", "SBR")
                    # Bovada-compatible fields (for steam detection)
                    game["Bovada ML Home"]  = best_match.get("Home ML", "N/A")
                    game["Bovada ML Away"]  = best_match.get("Away ML", "N/A")
                    game["Bovada Spread"]   = best_match.get("Spread", "N/A")
                    game["Bovada Total"]    = best_match.get("Total", "N/A")
                    # ── Fill in ESPN N/A gaps with SBR/OddsAPI data ──
                    # Set both "Home ML" (ESPN key) and "HomeML" (analysis key)
                    _sbr_home_ml = best_match.get("Home ML", "N/A")
                    _sbr_away_ml = best_match.get("Away ML", "N/A")
                    if game.get("Home ML") in ("N/A", None, ""):
                        game["Home ML"] = _sbr_home_ml
                    if game.get("Away ML") in ("N/A", None, ""):
                        game["Away ML"] = _sbr_away_ml
                    # Also set HomeML/AwayML (no space) for analyze_game_edge compatibility
                    if game.get("HomeML","N/A") in ("N/A", None, ""):
                        game["HomeML"] = game.get("Home ML", "N/A")
                    if game.get("AwayML","N/A") in ("N/A", None, ""):
                        game["AwayML"] = game.get("Away ML", "N/A")
                    if game.get("Spread") in ("N/A", None, ""):
                        game["Spread"] = best_match.get("Spread", "N/A")
                    if game.get("Total") in ("N/A", None, ""):
                        game["Total"] = best_match.get("Total", "N/A")
                    # Mark which source filled the data
                    if game.get("Odds Source") in ("ESPN", "N/A", ""):
                        game["Odds Source"] = best_match.get("Odds Source", "SBR")
            # Add any SBR/OddsAPI games ESPN missed entirely
            espn_matchups = {g.get("Matchup","").lower() for g in today_games}
            for odds_game in odds_games:
                om = odds_game.get("Matchup","").lower()
                home_word = om.split(" @ ")[-1][:4] if " @ " in om else ""
                if not any(home_word in m for m in espn_matchups if home_word):
                    today_games.append(odds_game)
    except (ValueError, KeyError, TypeError, AttributeError) as _ovl_err:
        print(f"[fetch_game_lines] odds overlay error for {sport}: {_ovl_err}")

    # ── BetOnline overlay — independent of ODDS_API_KEY ──
    # Fills any ML/spread/total still "N/A" after the ESPN+OddsAPI passes
    # above. This is the real fix for the "No Market" Game Lines bug when
    # its cause is an empty/invalid ODDS_API_KEY secret (that overlay
    # silently no-ops if ODDS_API_KEY isn't set) — BetOnline doesn't need
    # any key, so it still runs. Uses fetch_betonline_lines() directly
    # (not session_state) so this works even on the very first load before
    # the normal sport-scan populates session_state["betonline_lines"].
    try:
        bol_games = fetch_betonline_lines(sport)
        if bol_games:
            for game in today_games:
                still_missing = any(
                    game.get(k) in ("N/A", None, "")
                    for k in ("Home ML", "Away ML", "Spread", "Total")
                )
                if not still_missing:
                    continue
                matchup = game.get("Matchup", "")
                esp_parts = [t.strip().upper() for t in matchup.split("@")] if "@" in matchup else []
                best_match = None
                for bol_game in bol_games:
                    home2 = (bol_game.get("home", "") or "").upper()
                    away2 = (bol_game.get("away", "") or "").upper()
                    both = home2 + " " + away2
                    matched = False
                    for abbr in esp_parts:
                        if not abbr or len(abbr) < 2:
                            continue
                        if abbr in home2 or abbr in away2:
                            matched = True; break
                        frag = TEAM_ABBREV_TO_FRAGMENT.get(abbr, "").upper()
                        if frag and frag in both:
                            matched = True; break
                        if len(home2) >= 3 and home2[:3] in abbr:
                            matched = True; break
                        if len(away2) >= 3 and away2[:3] in abbr:
                            matched = True; break
                    if matched:
                        best_match = bol_game
                        break
                if best_match:
                    if game.get("Home ML") in ("N/A", None, ""):
                        game["Home ML"] = best_match.get("home_ml") or "N/A"
                    if game.get("Away ML") in ("N/A", None, ""):
                        game["Away ML"] = best_match.get("away_ml") or "N/A"
                    if game.get("HomeML", "N/A") in ("N/A", None, ""):
                        game["HomeML"] = game.get("Home ML", "N/A")
                    if game.get("AwayML", "N/A") in ("N/A", None, ""):
                        game["AwayML"] = game.get("Away ML", "N/A")
                    if game.get("Spread") in ("N/A", None, "") and best_match.get("spread") is not None:
                        game["Spread"] = best_match.get("spread")
                    if game.get("Total") in ("N/A", None, "") and best_match.get("total") is not None:
                        game["Total"] = best_match.get("total")
                    if game.get("Odds Source") in ("ESPN", "N/A", ""):
                        game["Odds Source"] = "BetOnline"
    except Exception:
        pass

    # ── Pinnacle overlay — dedicated fields, always populated when available ──
    # Free arcadia guest API, no key needed. Stores its own Pinnacle ML/Spread/
    # Total fields (not just N/A-filling) so it's always present for CLV,
    # since Pinnacle is a sharp reference book regardless of what else fired.
    try:
        pinn_games = fetch_pinnacle_game_lines(sport)
        if pinn_games:
            for game in today_games:
                matchup = game.get("Matchup", "")
                esp_parts = [t.strip().upper() for t in matchup.split("@")] if "@" in matchup else []
                best_match = None
                for pg in pinn_games:
                    home2 = (pg.get("Home", "") or "").upper()
                    away2 = (pg.get("Away", "") or "").upper()
                    both = home2 + " " + away2
                    matched = False
                    for abbr in esp_parts:
                        if not abbr or len(abbr) < 2:
                            continue
                        if abbr in home2 or abbr in away2:
                            matched = True; break
                        frag = TEAM_ABBREV_TO_FRAGMENT.get(abbr, "").upper()
                        if frag and frag in both:
                            matched = True; break
                        if len(home2) >= 3 and home2[:3] in abbr:
                            matched = True; break
                        if len(away2) >= 3 and away2[:3] in abbr:
                            matched = True; break
                    if matched:
                        best_match = pg
                        break
                if best_match:
                    game["Pinnacle ML Home"] = best_match.get("HomeML", "N/A")
                    game["Pinnacle ML Away"] = best_match.get("AwayML", "N/A")
                    game["Pinnacle Spread"]  = best_match.get("Spread", "N/A")
                    game["Pinnacle Total"]   = best_match.get("Total", "N/A")
                    if game.get("Home ML") in ("N/A", None, "") and best_match.get("HomeML") is not None:
                        game["Home ML"] = best_match["HomeML"]
                    if game.get("Away ML") in ("N/A", None, "") and best_match.get("AwayML") is not None:
                        game["Away ML"] = best_match["AwayML"]
                    if game.get("Odds Source") in ("ESPN", "N/A", ""):
                        game["Odds Source"] = "Pinnacle"
    except Exception as _pinn_err:
        print(f"[fetch_game_lines] Pinnacle overlay error for {sport}: {_pinn_err}")

    if not today_games:
        return [], playoff, home_teams, away_teams
    return today_games, playoff, home_teams, away_teams

def fetch_h2h_game_lines(sport):
    """
    Game-line fetcher for head-to-head (non-North-American-team) sports —
    Tennis (ATP/WTA), UFC, Soccer. Same ESPN scoreboard odds shape and
    contract as fetch_game_lines() (games, is_playoff, home_teams,
    away_teams) so it can feed analyze_all_games()/analyze_game_edge()
    through the same pipeline, including the multi-book market consensus
    layer. Kept separate from fetch_game_lines() because that function's
    post-ESPN enrichment (TEAM_ABBREV_TO_FRAGMENT, SBR/OddsAPI overlay
    matching) is built specifically around North American team
    abbreviations and would silently mismatch player/fighter names.

    Soccer is a 3-way market (home/draw/away) — "Spread" is repurposed to
    carry the draw odds (e.g. "Draw +240") when present, since these sports
    don't have a true spread; analyze_game_edge's per-sport branches treat
    it as informational context, not a real ATS line. For Tennis/UFC,
    Spread stays "N/A" since there's no spread market on a 1v1 matchup.
    """
    _h2h_slug_map = {
        "Tennis": [("tennis/atp", "ATP"), ("tennis/wta", "WTA")],
        "UFC":    [("mma/ufc", "UFC")],
        "Soccer": [("soccer/eng.1", "EPL"), ("soccer/usa.1", "MLS")],
    }
    slugs = _h2h_slug_map.get(sport)
    if not slugs:
        return [], False, {}, {}

    games, home_teams, away_teams = [], {}, {}
    playoff = False
    today = date.today()
    date_str = today.strftime("%Y%m%d")

    for path, league_label in slugs:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={date_str}"
            resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            events = data.get("events", [])
            for event in events:
                competitors_raw = []
                for comp in event.get("competitions", []):
                    competitors_raw = comp.get("competitors", [])
                if len(competitors_raw) < 2:
                    continue
                p1 = competitors_raw[0].get("athlete", {}).get("displayName") or \
                     competitors_raw[0].get("team", {}).get("displayName", "")
                p2 = competitors_raw[1].get("athlete", {}).get("displayName") or \
                     competitors_raw[1].get("team", {}).get("displayName", "")
                if not p1 or not p2:
                    continue
                matchup = f"{p2} @ {p1}" if sport != "Soccer" else event.get("shortName", f"{p2} @ {p1}")
                status = event.get("status", {}).get("type", {}).get("description", "")

                total = "N/A"
                home_ml = "N/A"
                away_ml = "N/A"
                draw_odds = "N/A"
                provider = "ESPN"
                for comp in event.get("competitions", []):
                    odds_data = comp.get("odds", [{}])[0] if comp.get("odds") else {}
                    total      = odds_data.get("overUnder", "N/A")
                    home_ml    = odds_data.get("homeTeamOdds", {}).get("moneyLine", "N/A")
                    away_ml    = odds_data.get("awayTeamOdds", {}).get("moneyLine", "N/A")
                    draw_odds  = odds_data.get("drawOdds", {}).get("moneyLine", "N/A")
                    provider   = odds_data.get("provider", {}).get("name", "ESPN")

                spread = f"Draw {draw_odds}" if (sport == "Soccer" and draw_odds not in ("N/A", None, "")) else "N/A"

                home_teams[matchup] = p1
                away_teams[matchup] = p2
                games.append({
                    "Matchup": matchup, "Status": status, "Spread": spread,
                    "Total": total, "Home ML": home_ml, "Away ML": away_ml,
                    "Odds Source": provider, "Date": today.strftime("%a %b %d"),
                    "Sport": sport, "League": league_label,
                })
        except Exception as e:
            print(f"[WARN] fetch_h2h_game_lines({sport},{path}): {e}")
            continue

    return games, playoff, home_teams, away_teams


def fetch_alt_lines(sport):
    """
    Fetch alternate spread lines from OddsAPI.
    Used to find playable lines when the standard spread has no edge.

    Example: PHI -1.5 (run line) -> no edge
             PHI -0.5 -> APPROVED edge (adjusted for easier cover)
             PHI +1.5 -> ELITE edge (can lose by 1 and still win)

    Returns dict: {matchup: {team: [{line, home_odds, away_odds}]}}
    SBR does not expose alternate lines; OddsAPI is the only source.
    Silently returns {} when key is absent or budget is exhausted.
    """
    if not ODDS_API_KEY:
        return {}
    try:
        _ok, _ = api_budget_check("ODDS_API")
        if not _ok:
            return {}
    except Exception:
        pass  # budget check unavailable — proceed with key-only guard
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return {}
    # Only fetch for sports where alt lines matter
    if sport not in ("MLB","WNBA","NBA","NFL","NHL"):
        return {}
    cache_path = os.path.join(CACHE_DIR, f"alt_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            return _safe_load_pkl(cache_path)
    try:
        # alternate_spreads is an "additional market" — OddsAPI only serves
        # these via the per-event endpoint, not the bulk /sports/{sport}/odds
        # endpoint. Requesting it in bulk returns an error dict, not events.
        events_url = f"{ODDS_API_BASE}/sports/{sport_key}/events?apiKey={ODDS_API_KEY}&dateFormat=iso"
        events_resp = _http.get(events_url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API", amount=0)  # /events is a free metadata endpoint
        if events_resp.status_code != 200:
            print(f"[WARN] fetch_alt_lines({sport}): OddsAPI events HTTP {events_resp.status_code}: {events_resp.text[:200]}")
            return {}
        events = events_resp.json()
        if not isinstance(events, list):
            print(f"[WARN] fetch_alt_lines({sport}): unexpected OddsAPI events response (not a list): {events}")
            return {}
        today_str = date.today().strftime("%Y-%m-%d")
        today_events = [e for e in events if isinstance(e, dict) and e.get("commence_time","").startswith(today_str)]
        if not today_events:
            tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
            today_events = [e for e in events if isinstance(e, dict) and e.get("commence_time","").startswith(tomorrow_str)]
        if not today_events:
            return {}

        alt_data = {}
        for event in today_events[:10]:
            event_id = event.get("id","")
            home = event.get("home_team","")
            away = event.get("away_team","")
            if not event_id or not home or not away:
                continue
            matchup = f"{away} @ {home}"
            odds_url = (f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds"
                        f"?apiKey={ODDS_API_KEY}&regions=us,us2"
                        f"&markets=alternate_spreads"
                        f"&oddsFormat=american"
                        f"&bookmakers=draftkings,fanduel,betmgm")
            try:
                resp = _http.get(odds_url, headers=HEADERS, timeout=15)
                api_budget_increment("ODDS_API", amount=20)  # 10 x 1 market x 2 regions
                if resp.status_code != 200:
                    continue
                event_data = resp.json()
                if not isinstance(event_data, dict):
                    continue
                lines = []
                for bm in event_data.get("bookmakers",[])[:2]:
                    if not isinstance(bm, dict):
                        continue
                    for mkt in bm.get("markets",[]):
                        if not isinstance(mkt, dict) or mkt.get("key") != "alternate_spreads":
                            continue
                        for o in mkt.get("outcomes",[]):
                            if not isinstance(o, dict):
                                continue
                            lines.append({
                                "team":  o.get("name",""),
                                "point": o.get("point",0),
                                "price": o.get("price",0),
                                "book":  bm.get("key",""),
                            })
                if lines:
                    alt_data[matchup] = {
                        "home": home, "away": away,
                        "lines": lines,
                    }
            except (requests.RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
                print(f"[WARN] fetch_alt_lines({sport}) event {event_id}: {e}")
                continue

        if alt_data:
            with open(cache_path, "wb") as f:
                pickle.dump(alt_data, f)
        return alt_data
    except (requests.RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        print(f"[WARN] fetch_alt_lines({sport}): {e}")
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# SportsbookReview (SBR) scraper
# Provides consensus game lines (ML, spread, totals) with no API key via
# __NEXT_DATA__ JSON embedded in each SBR page.  cloudscraper handles
# Cloudflare bot-detection; falls back to curl_cffi or plain requests if
# cloudscraper is not installed.
# ─────────────────────────────────────────────────────────────────────────────

_SBR_BASE = "https://www.sportsbookreview.com/betting-odds"

_SBR_SPORT_SLUG = {
    "MLB":  "mlb-baseball",
    "NBA":  "nba-basketball",
    "NFL":  "nfl-football",
    "NHL":  "nhl-hockey",
    "WNBA": "wnba-basketball",
}

_SBR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sportsbookreview.com/",
}

# Sportsbooks ranked by reliability; first available value wins per field
_SBR_BOOK_PRIORITY = [
    "draftkings", "fanduel", "betmgm", "caesars", "bet365",
    "pointsbet", "betrivers", "pinnacle", "bovada", "betonline",
]


def _sbr_parse_rows(html):
    """Extract gameRows list from SBR __NEXT_DATA__ JSON. Returns [] on error."""
    import re as _re, json as _json
    m = _re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, _re.DOTALL
    )
    if not m:
        return []
    try:
        data = _json.loads(m.group(1))
        tables = data["props"]["pageProps"]["oddsTables"]
        rows = []
        for tbl in tables:
            rows.extend(tbl.get("oddsTableModel", {}).get("gameRows", []))
        return rows
    except (KeyError, ValueError, TypeError):
        return []


def _sbr_pick(odds_views, field):
    """Return currentLine[field] from the highest-priority available sportsbook."""
    book_map = {ov.get("sportsbook", ""): ov for ov in odds_views}
    for book in _SBR_BOOK_PRIORITY:
        ov = book_map.get(book)
        if ov:
            val = ov.get("currentLine", {}).get(field)
            if val is not None:
                return val
    for ov in odds_views:
        val = ov.get("currentLine", {}).get(field)
        if val is not None:
            return val
    return None


def _sbr_fmt_ml(val):
    """Format a raw SBR money-line integer as signed American odds string."""
    if val is None:
        return "N/A"
    try:
        v = int(val)
        return f"+{v}" if v > 0 else str(v)
    except (TypeError, ValueError):
        return "N/A"


def _sbr_make_scraper():
    """Return a scraper session that bypasses Cloudflare bot detection.

    Preference order: cloudscraper -> curl_cffi -> plain requests.
    """
    try:
        import cloudscraper
        return cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
    except ImportError:
        pass
    try:
        from curl_cffi import requests as _cf

        class _Wrap:
            def get(self, url, **kw):
                return _cf.get(url, impersonate="chrome124", **kw)
        return _Wrap()
    except ImportError:
        pass
    import requests as _r
    return _r.Session()


def _sbr_fetch_games(sport):
    """Fetch today's game lines from SportsbookReview.com (no API key required).

    Scrapes three SBR pages per sport:
      - /betting-odds/{slug}/                       -> money-line (homeOdds/awayOdds)
      - /betting-odds/{slug}/pointspread/full-game/ -> spread (homeSpread/awaySpread)
      - /betting-odds/{slug}/totals/full-game/      -> total (total field)

    Returns (games, home_teams, away_teams) in the same shape as
    fetch_odds_api_game_lines().  Results cached 20 minutes.
    """
    slug = _SBR_SPORT_SLUG.get(sport)
    if not slug:
        return [], {}, {}

    cache_path = os.path.join(CACHE_DIR, f"sbr_games_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 20:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    scraper = _sbr_make_scraper()

    def _get(url):
        try:
            r = scraper.get(url, headers=_SBR_HEADERS, timeout=15)
            if r.status_code == 200:
                return _sbr_parse_rows(r.text)
        except Exception:
            pass
        return []

    base = f"{_SBR_BASE}/{slug}"
    ml_rows  = _get(f"{base}/")
    sp_rows  = _get(f"{base}/pointspread/full-game/")
    tot_rows = _get(f"{base}/totals/full-game/")

    if not ml_rows:
        return [], {}, {}

    # Index spread + total rows by gameId for O(1) lookup
    sp_by_id  = {r["gameView"]["gameId"]: r for r in sp_rows  if r.get("gameView", {}).get("gameId")}
    tot_by_id = {r["gameView"]["gameId"]: r for r in tot_rows if r.get("gameView", {}).get("gameId")}

    games, home_teams, away_teams = [], {}, {}
    today_str = date.today().strftime("%a %b %d")

    for row in ml_rows:
        gv         = row.get("gameView", {})
        gid        = gv.get("gameId")
        away_short = gv.get("awayTeam", {}).get("shortName", "")
        home_short = gv.get("homeTeam", {}).get("shortName", "")
        away_full  = gv.get("awayTeam", {}).get("fullName", away_short)
        home_full  = gv.get("homeTeam", {}).get("fullName", home_short)
        matchup    = f"{away_short} @ {home_short}"

        # Money line (from ML page)
        ov_ml   = row.get("oddsViews", [])
        home_ml = _sbr_fmt_ml(_sbr_pick(ov_ml, "homeOdds"))
        away_ml = _sbr_fmt_ml(_sbr_pick(ov_ml, "awayOdds"))

        # Spread (from pointspread page)
        spread = "N/A"
        sp_row = sp_by_id.get(gid, {})
        if sp_row:
            home_sp = _sbr_pick(sp_row.get("oddsViews", []), "homeSpread")
            if home_sp is not None:
                try:
                    spread = f"{home_short} {float(home_sp):+.1f}"
                except (TypeError, ValueError):
                    pass

        # Total (from totals page)
        total = "N/A"
        tot_row = tot_by_id.get(gid, {})
        if tot_row:
            tot_val = _sbr_pick(tot_row.get("oddsViews", []), "total")
            if tot_val is not None:
                try:
                    total = float(tot_val)
                except (TypeError, ValueError):
                    pass

        home_teams[matchup] = home_full
        away_teams[matchup] = away_full
        games.append({
            "Matchup":    matchup,
            "Status":     "Scheduled",
            "Spread":     spread,
            "Total":      total,
            "Home ML":    home_ml,
            "Away ML":    away_ml,
            "Odds Source": "SBR",
            "Date":       today_str,
            "Sport":      sport,
        })

    result = (games, home_teams, away_teams)
    if games:
        try:
            with open(cache_path, "wb") as _f:
                pickle.dump(result, _f)
        except Exception:
            pass
    return result


def fetch_odds_api_game_lines(sport):
    # ── SBR primary (no API key required) ──
    sbr_games, sbr_home, sbr_away = _sbr_fetch_games(sport)
    if sbr_games:
        return sbr_games, sbr_home, sbr_away

    # ── OddsAPI fallback (requires key + remaining budget) ──
    if not ODDS_API_KEY:
        print("[ODDS_API] ODDS_API_KEY not set — OddsAPI game lines skipped")
        return [], {}, {}
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return [], {}, {}
    allowed, reason = api_budget_check("ODDS_API")
    if not allowed:
        print(f"[ODDS_API] budget check blocked game lines for {sport}: {reason}")
        return [], {}, {}
    cache_path = os.path.join(CACHE_DIR, f"odds_api_games_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            return _safe_load_pkl(cache_path)
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds?apiKey={ODDS_API_KEY}&regions=us,us2&markets=h2h,spreads,totals&oddsFormat=american&bookmakers={ODDS_API_BOOKS_GAMES}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API", amount=60)  # 10 x 3 markets x 2 regions
        if resp.status_code != 200:
            print(f"[ODDS_API] game lines HTTP {resp.status_code} for {sport} — "
                  f"{'ODDS_API_KEY invalid or expired' if resp.status_code in (401, 403) else 'upstream error'}")
            return [], {}, {}
        events = resp.json()
        games = []
        home_teams = {}
        away_teams = {}
        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            matchup = f"{away} @ {home}"
            spread = "N/A"
            total = "N/A"
            home_ml = "N/A"
            away_ml = "N/A"
            odds_source = "N/A"
            priority = ["bovada", "mybookieag", "draftkings", "fanduel", "betmgm", "caesars", "circa_sports", "betonlineag", "us_ex"]
            for preferred_book in priority:
                for bm in event.get("bookmakers", []):
                    if bm.get("key") != preferred_book:
                        continue
                    odds_source = bm.get("title", preferred_book)
                    for mkt in bm.get("markets", []):
                        key = mkt.get("key","")
                        outcomes = mkt.get("outcomes", [])
                        if key == "h2h":
                            for o in outcomes:
                                if o.get("name") == home:
                                    home_ml = o.get("price", home_ml)
                                elif o.get("name") == away:
                                    away_ml = o.get("price", away_ml)
                        elif key == "spreads":
                            for o in outcomes:
                                if o.get("name") == home and o.get("point") is not None:
                                    try:
                                        spread = f"{home} {float(o['point']):+.1f}"
                                    except (TypeError, ValueError):
                                        pass
                        elif key == "totals":
                            for o in outcomes:
                                if o.get("name") == "Over":
                                    total = o.get("point", "N/A")
                    break
                if odds_source != "N/A":
                    break
            home_teams[matchup] = home
            away_teams[matchup] = away
            games.append({
                "Matchup": matchup,
                "Status": "Scheduled",
                "Spread": spread,
                "Total": total,
                "Home ML": home_ml,
                "Away ML": away_ml,
                "Odds Source": odds_source,
                "Date": date.today().strftime("%a %b %d"),
                "Sport": sport,
            })
        result = (games, home_teams, away_teams)
        if games:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        return result
    except Exception as e:
        print(f"[ODDS_API] game lines fetch exception for {sport}: {e}")
        return [], {}, {}

def fetch_preview_game_lines(sport):
    # PREVIEW BOARD (2026-07): raw next-day game lines only — no tier scoring,
    # no Kelly staking. Reuses the same OddsAPI /odds bulk call as
    # fetch_odds_api_game_lines() (that endpoint already returns the full
    # upcoming window, not just today — it just wasn't being filtered by
    # date before). This filters to tomorrow's commence_time and stamps the
    # real game date instead of hardcoding date.today(). Cached separately
    # from the live board's cache so it never collides with or overwrites
    # today's board state.
    if not ODDS_API_KEY:
        return []
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return []
    allowed, reason = api_budget_check("ODDS_API")
    if not allowed:
        print(f"[ODDS_API] budget check blocked preview lines for {sport}: {reason}")
        return []
    cache_path = os.path.join(CACHE_DIR, f"preview_games_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            return _safe_load_pkl(cache_path)
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds?apiKey={ODDS_API_KEY}&regions=us,us2&markets=h2h,spreads,totals&oddsFormat=american&bookmakers={ODDS_API_BOOKS_GAMES}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API", amount=60)  # 10 x 3 markets x 2 regions
        if resp.status_code != 200:
            print(f"[ODDS_API] preview lines HTTP {resp.status_code} for {sport}")
            return []
        events = resp.json()
        if not isinstance(events, list):
            return []
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_events = [e for e in events if isinstance(e, dict) and e.get("commence_time", "").startswith(tomorrow_str)]
        games = []
        priority = ["bovada", "mybookieag", "draftkings", "fanduel", "betmgm", "caesars", "circa_sports", "betonlineag", "us_ex"]
        for event in tomorrow_events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            if not home or not away:
                continue
            matchup = f"{away} @ {home}"
            spread = "N/A"
            total = "N/A"
            home_ml = "N/A"
            away_ml = "N/A"
            odds_source = "N/A"
            for preferred_book in priority:
                for bm in event.get("bookmakers", []):
                    if bm.get("key") != preferred_book:
                        continue
                    odds_source = bm.get("title", preferred_book)
                    for mkt in bm.get("markets", []):
                        key = mkt.get("key", "")
                        outcomes = mkt.get("outcomes", [])
                        if key == "h2h":
                            for o in outcomes:
                                if o["name"] == home:
                                    home_ml = o["price"]
                                elif o["name"] == away:
                                    away_ml = o["price"]
                        elif key == "spreads":
                            for o in outcomes:
                                if o["name"] == home:
                                    spread = f"{home} {o['point']:+.1f}"
                        elif key == "totals":
                            for o in outcomes:
                                if o["name"] == "Over":
                                    total = o.get("point", "N/A")
                    break
                if odds_source != "N/A":
                    break
            games.append({
                "Matchup": matchup,
                "Spread": spread,
                "Total": total,
                "Home ML": home_ml,
                "Away ML": away_ml,
                "Odds Source": odds_source,
                "Game Time": event.get("commence_time", ""),
                "Sport": sport,
            })
        if games:
            with open(cache_path, "wb") as f:
                pickle.dump(games, f)
        return games
    except (IOError, ValueError) as e:
        print(f"[ODDS_API] preview lines fetch exception for {sport}: {e}")
        return []

def fetch_oddswrap_props(sport):
    if not ODDSWRAP_AVAILABLE:
        return []
    sport_key = ODDSWRAP_SPORT_MAP.get(sport)
    if not sport_key:
        return []
    cache_path = os.path.join(CACHE_DIR, f"oddswrap_props_{sport}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 1:
            return _safe_load_pkl(cache_path)
    all_props = []
    try:
        client = OddsClient(books=["draftkings", "fanduel", "bovada", "betrivers", "betmgm", "caesars"])
        seen = set()
        for book in ["draftkings", "fanduel", "bovada", "betrivers", "betmgm", "caesars"]:
            try:
                cats = client.get_prop_categories(sport_key, book=book)
                for cat in cats[:10]:
                    try:
                        props = client.get_props(sport_key, category_id=cat.category_id, subcategory_id=cat.subcategory_id, book=book)
                        for prop in props:
                            if not prop.player or prop.line is None:
                                continue
                            key = (prop.player, prop.market, prop.book)
                            if key in seen:
                                continue
                            seen.add(key)
                            all_props.append({"Player": prop.player, "Prop": prop.market, "Line": float(prop.line), "Side": "OVER", "OverOdds": prop.over_odds, "UnderOdds": prop.under_odds, "Book": prop.book, "Sport": sport, "source": f"oddswrap_{prop.book}"})
                    except (ValueError, TypeError):
                        continue
            except (ValueError, TypeError):
                continue
        if all_props:
            with open(cache_path, "wb") as f:
                pickle.dump(all_props, f)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        pass
    return all_props

def fetch_action_network_public_betting(sport: str) -> dict:
    """
    Fetch Action Network public betting percentages.
    Returns {matchup: {home_pct, away_pct, over_pct, under_pct, tickets, money}}
    Cached 20 min. Free — no API key needed.

    2026-07-17 fix: renamed from fetch_action_network_props (kept that
    name would silently collide with an unrelated, different-purpose
    function of the exact same name defined later in app.py — Action
    Network's PROP PROJECTIONS fetcher, not public betting %. Because
    app.py does `from fetchers import *` and then defines its own
    fetch_action_network_props afterward, app.py's version always wins
    inside app.py; this function was completely unreachable under its
    old name from anywhere in the app, real and correct as it is. Only
    fetchers.py's own internal self-import (in
    fetch_action_network_from_gist below) ever actually reached this
    implementation, since that import targets the fetchers module
    explicitly. Renamed so both functions can coexist without either
    silently shadowing the other.
    """
    sport_slug = ACTION_NETWORK_SPORT_MAP.get(sport)
    league_id  = ACTION_NETWORK_LEAGUE_IDS.get(sport)
    if not sport_slug or not league_id:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"an_props_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 20:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    try:
        today = date.today().strftime("%Y%m%d")
        url = (
            f"https://api.actionnetwork.com/web/v2/scoreboard/publicbetting"
            f"?bookIds={ACTION_NETWORK_BOOK_IDS}&date={today}&leagueId={league_id}"
        )
        r = _http.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.actionnetwork.com/",
        }, timeout=12)
        if r.status_code != 200:
            return {}
        data = r.json()
        result = {}
        for game in data.get("games", []):
            teams = game.get("teams", [])
            if len(teams) < 2:
                continue
            away = teams[0].get("full_name", teams[0].get("name", ""))
            home = teams[1].get("full_name", teams[1].get("name", ""))
            matchup = f"{away} @ {home}"
            books = game.get("books", [])
            if not books:
                continue
            b = books[0]
            result[matchup] = {
                "home_ml_pct":   b.get("home_ml_pct"),
                "away_ml_pct":   b.get("away_ml_pct"),
                "over_pct":      b.get("over_pct"),
                "under_pct":     b.get("under_pct"),
                "home_spread_pct": b.get("home_spread_pct"),
                "away_spread_pct": b.get("away_spread_pct"),
                "total_bets":    b.get("num_bets"),
            }
        if result:
            _safe_save_pkl(cache_path, result)
        return result
    except Exception as e:
        print(f"[WARN] fetch_action_network_public_betting: {e}")
        return {}


def fetch_parlayapi_props(sport):
    """
    Fetch ParlayPlay props via parlay-api.com aggregator.
    Costs 3 credits per call. Returns ParlayPlay lines cleanly.
    Also pulls PrizePicks and Underdog for line comparison.
    """
    if not PARLAY_API_KEY:
        return []
    cache_path = os.path.join(CACHE_DIR, f"parlayapi_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached
    sport_map = {
        "NBA": "basketball_nba", "WNBA": "basketball_wnba",
        "MLB": "baseball_mlb", "NHL": "icehockey_nhl", "NFL": "americanfootball_nfl"
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    stat_map = {
        "player_points": "Points", "player_rebounds": "Rebounds",
        "player_assists": "Assists", "player_threes": "3-PT Made",
        "player_steals": "Steals", "player_blocks": "Blocked Shots",
        "player_turnovers": "Turnovers", "player_pra": "Pts+Reb+Ast",
        "player_pts_rebs": "Pts+Reb", "player_pts_asts": "Pts+Ast",
        "player_rebs_asts": "Reb+Ast", "player_double_double": "Double-Double",
        "player_hits": "Hits", "player_home_runs": "Home Runs",
        "player_total_bases": "Total Bases", "player_rbis": "RBIs",
        "player_strikeouts": "Strikeouts", "player_hits_runs_rbis": "Hits+Runs+RBIs",
        "player_goals": "Goals", "player_shots_on_goal": "Shots On Goal",
        "player_pass_yds": "Passing Yards", "player_rush_yds": "Rushing Yards",
        "player_rec_yds": "Receiving Yards", "player_receptions": "Receptions",
    }
    try:
        resp = _http.get(
            f"{PARLAY_API_BASE}/sports/{sport_key}/props",
            headers={"X-API-Key": PARLAY_API_KEY},
            params={"bookmakers": "parlayplay,prizepicks,underdog", "dfsOdds": "midpoint"},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        props = []
        seen = set()
        for row in data:
            bookmaker = row.get("bookmaker", "")
            if bookmaker not in ("parlayplay", "prizepicks", "underdog"):
                continue
            player = row.get("player", "")
            market_key = row.get("market_key", "")
            stat = stat_map.get(market_key, market_key.replace("player_","").replace("_"," ").title())
            line = row.get("line")
            over_price = row.get("over_price")
            if not player or not stat or line is None:
                continue
            key = (bookmaker, player, stat, line)
            if key in seen:
                continue
            seen.add(key)
            # Detect Demon/Goblin from price (DFS midpoint pricing)
            odds_type = "standard"
            if bookmaker == "parlayplay":
                if over_price and over_price > 110:
                    odds_type = "goblin"
                elif over_price and over_price < -110:
                    odds_type = "demon"
            props.append({
                "Player": player,
                "Prop": stat,
                "Line": float(line),
                "Side": "OVER",
                "Sport": sport,
                "source": bookmaker.title(),
                "odds_type": odds_type,
                "over_price": over_price,
                "under_price": row.get("under_price"),
            })
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
        return props
    except (IOError, ValueError) as e:
        return []

def fetch_parlayapi_arbitrage(sport):
    """Fetch arbitrage opportunities via parlay-api.com"""
    if not PARLAY_API_KEY:
        return []
    sport_map = {
        "NBA": "basketball_nba", "WNBA": "basketball_wnba",
        "MLB": "baseball_mlb", "NHL": "icehockey_nhl", "NFL": "americanfootball_nfl"
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    try:
        resp = _http.get(
            f"{PARLAY_API_BASE}/sports/{sport_key}/arbitrage",
            headers={"X-API-Key": PARLAY_API_KEY},
            params={"limit": 20},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return resp.json()
    except (json.JSONDecodeError, KeyError, TypeError):
        return []

def fetch_parlayapi_ev(sport):
    """Fetch +EV picks vs Pinnacle baseline via parlay-api.com"""
    if not PARLAY_API_KEY:
        return []
    sport_map = {
        "NBA": "basketball_nba", "WNBA": "basketball_wnba",
        "MLB": "baseball_mlb", "NHL": "icehockey_nhl", "NFL": "americanfootball_nfl"
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    try:
        resp = _http.get(
            f"{PARLAY_API_BASE}/sports/{sport_key}/ev",
            headers={"X-API-Key": PARLAY_API_KEY},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return resp.json()
    except (json.JSONDecodeError, KeyError, TypeError):
        return []

def fetch_espn_game_ids(sport):
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "hockey/nhl", "NFL": "football/nfl", "WNBA": "basketball/wnba"}
    path = slug_map.get(sport)
    if not path:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"espn_ids_{sport}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 60
        if age < 30:
            return _safe_load_pkl(cache_path)
    game_ids = {}
    try:
        today_str = date.today().strftime("%Y%m%d")
        url = f"https://site.web.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={today_str}"
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for event in resp.json().get("events", []):
            event_id = event.get("id", "")
            matchup = event.get("shortName", "")
            if event_id and matchup:
                game_ids[matchup] = event_id
        if game_ids:
            with open(cache_path, "wb") as f:
                pickle.dump(game_ids, f)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return game_ids

def fetch_espn_line_movement(sport, event_id):
    if not event_id:
        return []
    cache_path = os.path.join(CACHE_DIR, f"line_move_{event_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 60
        if age < 15:
            return _safe_load_pkl(cache_path)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return []
    # Use site.web.api.espn.com (confirmed working on Streamlit Cloud)
    espn_sport_map = {"NBA": ("basketball","nba"), "MLB": ("baseball","mlb"), "NHL": ("hockey","nhl"), "NFL": ("football","nfl"), "WNBA": ("basketball","wnba")}
    if sport not in espn_sport_map:
        return []
    espn_sport, espn_league = espn_sport_map[sport]
    # Get game summary which includes odds/lines history
    url = f"https://site.web.api.espn.com/apis/site/v2/sports/{espn_sport}/{espn_league}/summary?event={event_id}&region=us&lang=en&contentorigin=espn"
    try:
        resp = _http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        # Extract odds info from header
        header = data.get("header", {})
        competitions = header.get("competitions", [{}])
        comp = competitions[0] if competitions else {}
        odds_list = comp.get("odds", [])
        movements = []
        for odd in odds_list:
            movements.append({
                "spread": odd.get("spread","—"),
                "over_under": odd.get("overUnder","—"),
                "home_ml": odd.get("homeTeamOdds",{}).get("moneyLine","—"),
                "away_ml": odd.get("awayTeamOdds",{}).get("moneyLine","—"),
                "provider": odd.get("provider",{}).get("name",""),
                "time": ""
            })
        if movements:
            with open(cache_path, "wb") as f:
                pickle.dump(movements, f)
        return movements
    except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
        return []

def fetch_espn_player_gamelogs(sport, player_name, n_games=10):
    athlete_id = ESPN_ATHLETE_IDS.get(sport, {}).get(player_name)
    if not athlete_id:
        return None
    cache_path = os.path.join(CACHE_DIR, f"espn_gamelog_{sport}_{athlete_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 24:
            return _safe_load_pkl(cache_path)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return None
    season = 2025
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/seasons/{season}/athletes/{athlete_id}/eventlog?limit={n_games}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        game_stats = []
        for item in data.get("events", {}).get("items", [])[:n_games]:
            stats_ref = item.get("statistics", {}).get("$ref", "")
            if not stats_ref:
                continue
            try:
                stats_resp = _http.get(stats_ref, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if stats_resp.status_code != 200:
                    continue
                stats_data = stats_resp.json()
                game_stat = {}
                for split in stats_data.get("splits", {}).get("categories", []):
                    for stat in split.get("stats", []):
                        game_stat[stat.get("abbreviation", "").upper()] = stat.get("value", 0)
                if game_stat:
                    game_stats.append(game_stat)
                time.sleep(0.2)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        if not game_stats:
            return None
        if sport == "NBA":
            avg = {"PTS": round(sum(g.get("PTS", 0) for g in game_stats) / len(game_stats), 1), "REB": round(sum(g.get("REB", 0) for g in game_stats) / len(game_stats), 1), "AST": round(sum(g.get("AST", 0) for g in game_stats) / len(game_stats), 1)}
            avg["PRA"] = round(avg["PTS"] + avg["REB"] + avg["AST"], 1)
        elif sport == "NFL":
            avg = {"PASS_YDS": round(sum(g.get("PASSYDS", g.get("YDS", 0)) for g in game_stats) / len(game_stats), 1), "RUSH_YDS": round(sum(g.get("RUSHYDS", g.get("RYDS", 0)) for g in game_stats) / len(game_stats), 1), "REC_YDS": round(sum(g.get("RECYDS", g.get("RECYD", 0)) for g in game_stats) / len(game_stats), 1), "TD": round(sum(g.get("TD", 0) for g in game_stats) / len(game_stats), 2)}
        else:
            avg = {}
        avg["n_games"] = len(game_stats)
        with open(cache_path, "wb") as f:
            pickle.dump(avg, f)
        return avg
    except (pickle.UnpicklingError, OSError, EOFError):
        return None


# Prop-type text → stat abbreviation. Permissive substring matching since
# board prop-type strings come from various upstream sources and aren't a
# single controlled vocabulary. Covers NBA/NFL (original) and MLB (added
# for the MLB EXPECTED_VS_ACTUAL build).
_GRADING_PROP_STAT_MAP = [
    (("pts+reb+ast", "points+rebounds+assists", "pra"), "PRA"),
    (("pts+reb", "points+rebounds", "points + rebounds"), "PR"),
    (("pts+ast", "points+assists", "points + assists"), "PA_COMBO"),
    (("reb+ast", "rebounds+assists", "rebounds + assists"), "RA"),
    (("three", "3pm", "3-pointer", "3 pointer"), "3PM"),
    (("steal",), "STL"),
    (("block",), "BLK"),
    (("turnover",), "TO"),
    (("point", "pts"), "PTS"),
    (("rebound", "reb"), "REB"),
    (("assist", "ast"), "AST"),
    (("pass", "yard"), "PASS_YDS"),
    (("rush", "yard"), "RUSH_YDS"),
    (("rec", "yard"), "REC_YDS"),
    (("touchdown", "td"), "TD"),
    # MLB
    (("strikeout", "so", " k's", "pitcher strikeouts"), "SO"),
    (("earned run", "era", " er"), "ER"),
    (("home run", "hr"), "HR"),
    (("rbi",), "RBI"),
    (("total base",), "TB"),
    (("run scored", "runs"), "R"),
    (("hit",), "H"),
]


def _map_prop_to_stat_key(prop_type: str, sport: str = None):
    p = (prop_type or "").lower()
    # "Assists" means different things (and different field-key conventions
    # already established elsewhere in this codebase) per sport: NBA uses
    # "AST", but 5+ existing NHL functions already use "ASSISTS" — rather
    # than force one to change, branch on sport for this one ambiguous case.
    # Order matters: check SOG before GOALS, since "Shots on Goal" contains
    # "goal" as a substring and would otherwise match GOALS first.
    if sport == "NHL":
        if "power play point" in p or "ppp" in p:
            return "PPP"
        if "block" in p:
            return "BLOCKED_SHOTS"
        if "hit" in p:
            return "HITS"
        if "sog" in p or "shot" in p:
            return "SOG"
        if "assist" in p:
            return "ASSISTS"
        if "point" in p:
            return "PTS"
        if "goal" in p:
            return "GOALS"
    if sport == "MLB":
        if "total base" in p:
            return "TOTAL_BASES"
        if "strikeout" in p or p.strip() in ("k", "ks"):
            return "PITCHER_K"
        if "home run" in p or p.strip() in ("hr", "hrs"):
            return "HR"
        if "rbi" in p:
            return "RBI"
        if "run" in p and "home" not in p and "earned" not in p:
            return "RUNS"
        if "double" in p:
            return "DOUBLES"
        if "triple" in p:
            return "TRIPLES"
        if "stolen base" in p or "sb" == p.strip():
            return "SB"
        if "walk allowed" in p:
            return "WALKS_ALLOWED"
        if "walk" in p:
            return "WALKS"
        if "earned run" in p:
            return "ER"
        if "hit allowed" in p or "hits allowed" in p:
            return "HITS_ALLOWED"
        if "out" in p and "record" in p:
            return "OUTS"
        if "hit" in p:
            return "HITS"
    for keywords, stat_key in _GRADING_PROP_STAT_MAP:
        # Multi-word tuples (e.g. "pass"+"yard") require ALL keywords
        # present, not any single one — otherwise any prop containing just
        # "yard" always matched whichever tuple appears first (PASS_YDS),
        # regardless of whether it was actually a rushing or receiving
        # prop. Single-keyword tuples still match on simple presence.
        if len(keywords) > 1 and all(len(k.strip()) > 3 for k in keywords):
            if all(kw in p for kw in keywords):
                return stat_key
        elif any(kw in p for kw in keywords):
            return stat_key
    return None


def _resolve_mlb_stat_for_grading(player: str, stat_key: str, game_date: str):
    """MLB counterpart to the ESPN_ATHLETE_IDS-based NBA/NFL grading path.
    Uses the same statsapi.mlb.com gameLog endpoint already proven in
    fetch_mlb_player_gamelog_vs_opponent / fetch_mlb_rolling_averages, and
    fetch_mlb_full_roster_ids for name->id (all 30 teams, not a hardcoded
    ~15-20 player subset) -- so MLB grading coverage isn't limited the way
    the NBA/NFL ESPN_ATHLETE_IDS path is. Returns float or None.
    """
    all_ids = fetch_mlb_full_roster_ids()
    player_id = all_ids.get(player)
    if not player_id:
        return None
    for group in ("hitting", "pitching"):
        url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group={group}&season={game_date[:4]}&gameType=R"
        try:
            resp = _http.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            splits = (resp.json().get("stats") or [{}])[0].get("splits", [])
            g = next((s for s in splits if s.get("date") == game_date[:10]), None)
            if not g:
                continue
            stat = g.get("stat", {})
            if stat_key == "TOTAL_BASES":
                tb = stat.get("totalBases")
                if tb is not None:
                    return float(tb)
                h, d2, t3, hr = stat.get("hits", 0), stat.get("doubles", 0), stat.get("triples", 0), stat.get("homeRuns", 0)
                singles = h - d2 - t3 - hr
                return float(singles + 2 * d2 + 3 * t3 + 4 * hr)
            _field = {
                "HITS": "hits", "HR": "homeRuns", "RBI": "rbi", "RUNS": "runs",
                "DOUBLES": "doubles", "TRIPLES": "triples", "SB": "stolenBases",
                "WALKS": "baseOnBalls", "PITCHER_K": "strikeOuts", "ER": "earnedRuns",
                "HITS_ALLOWED": "hits", "WALKS_ALLOWED": "baseOnBalls",
            }.get(stat_key)
            if _field and _field in stat:
                return float(stat.get(_field, 0) or 0)
            if stat_key == "OUTS":
                ip = stat.get("inningsPitched")
                if ip is not None:
                    whole, _, frac = str(ip).partition(".")
                    return float(int(whole or 0) * 3 + int(frac or 0))
        except Exception as e:
            print(f"[WARN] _resolve_mlb_stat_for_grading ({group}): {e}")
            continue
    return None


def fetch_nba_full_roster_ids(force_refresh=False):
    """
    Fetch NBA player IDs for ALL active players via ESPN's athletes list
    endpoint (site.api.espn.com, limit=500 covers the full league -- 30
    teams x ~15-17 roster spots). Returns {player_name: player_id}.
    Cached 24h. Same pattern as fetch_wnba_full_roster_ids.
    """
    cache_path = os.path.join(CACHE_DIR, "nba_full_roster_ids.pkl")
    if not force_refresh and os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 24:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass
    all_ids = dict(ESPN_ATHLETE_IDS.get("NBA", {}))  # seed with known IDs
    try:
        roster_data = _espn_get(
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/athletes?limit=500&active=true",
            "nba_roster_espn_full", ttl_hours=24
        )
        for a in (roster_data or {}).get("athletes", []):
            name = a.get("displayName", "")
            pid  = a.get("id")
            if name and pid and name not in all_ids:
                all_ids[name] = pid
        if len(all_ids) > len(ESPN_ATHLETE_IDS.get("NBA", {})):
            with open(cache_path, "wb") as f:
                pickle.dump(all_ids, f)
    except Exception:
        pass
    return all_ids


def _resolve_espn_core_stat(sport: str, athlete_id, stat_key: str, game_date: str):
    """Shared ESPN core eventlog resolver for NBA/NFL/WNBA -- same endpoint,
    same per-game stat-category parsing, same composite stats (PRA for
    basketball, yardage aliasing for football) for all three, so a WNBA prop
    graded via this path behaves identically to an NBA one rather than
    silently missing the composite-stat handling.
    """
    if not athlete_id:
        return None
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return None

    cache_path = os.path.join(CACHE_DIR, f"grading_stat_{sport}_{athlete_id}_{game_date}.pkl")
    if os.path.exists(cache_path):
        cached = _safe_load_pkl(cache_path)
        if cached is not None:
            return cached.get(stat_key)

    season = 2025
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/seasons/{season}/athletes/{athlete_id}/eventlog?limit=15"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:
        print(f"[WARN] _resolve_espn_core_stat: {e}")
        return None

    for item in data.get("events", {}).get("items", []):
        event_ref = item.get("event", {}).get("$ref", "") or item.get("$ref", "")
        item_date = item.get("date", "")
        if not item_date and event_ref:
            try:
                ev_resp = _http.get(event_ref, headers=HEADERS, timeout=10)
                if ev_resp.status_code == 200:
                    item_date = ev_resp.json().get("date", "")
            except Exception:
                pass
        if not item_date or not item_date.startswith(game_date):
            continue
        stats_ref = item.get("statistics", {}).get("$ref", "")
        if not stats_ref:
            continue
        try:
            stats_resp = _http.get(stats_ref, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if stats_resp.status_code != 200:
                continue
            stats_data = stats_resp.json()
            game_stat = {}
            for split in stats_data.get("splits", {}).get("categories", []):
                for stat in split.get("stats", []):
                    game_stat[stat.get("abbreviation", "").upper()] = stat.get("value", 0)
            if not game_stat:
                continue
            if sport in ("NBA", "WNBA"):
                result = {
                    "PTS": game_stat.get("PTS", 0), "REB": game_stat.get("REB", 0),
                    "AST": game_stat.get("AST", 0),
                    "3PM": game_stat.get("3PM", game_stat.get("TPM", game_stat.get("FG3M", 0))),
                    "STL": game_stat.get("STL", 0),
                    "BLK": game_stat.get("BLK", 0),
                    "TO":  game_stat.get("TO", game_stat.get("TOV", 0)),
                }
                result["PRA"]       = result["PTS"] + result["REB"] + result["AST"]
                result["PR"]        = result["PTS"] + result["REB"]
                result["PA_COMBO"]  = result["PTS"] + result["AST"]
                result["RA"]        = result["REB"] + result["AST"]
            else:  # NFL
                result = {
                    "PASS_YDS": game_stat.get("PASSYDS", game_stat.get("YDS", 0)),
                    "RUSH_YDS": game_stat.get("RUSHYDS", game_stat.get("RYDS", 0)),
                    "REC_YDS":  game_stat.get("RECYDS", game_stat.get("RECYD", 0)),
                    "TD":       game_stat.get("TD", 0),
                }
            _safe_save_pkl(cache_path, result)
            return result.get(stat_key)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return None


def resolve_actual_stat_for_grading(player: str, sport: str, prop_type: str, game_date: str):
    """
    Resolve the actual stat value a player recorded on a specific date, for
    grading a board pick after the fact.

    Coverage (2026-07): all 5 sports have automated grading, each via a
    full-roster/full-league player-ID lookup rather than a hardcoded subset:
      - MLB:  statsapi.mlb.com          + fetch_mlb_full_roster_ids  (30 teams)
      - NHL:  api-web.nhle.com          + fetch_nhl_full_roster_ids  (32 teams)
      - NBA:  ESPN core eventlog        + fetch_nba_full_roster_ids  (full league)
      - WNBA: ESPN core eventlog        + fetch_wnba_full_roster_ids (full league)
      - NFL:  ESPN core eventlog        + fetch_nfl_full_player_database (32 teams)
    Callers must treat None as "ungradable this pick" rather than assuming a
    miss -- a game not yet played, a stat category ESPN/MLB/NHL doesn't
    expose, or a transient fetch error all return None the same way.

    Returns: float stat value, or None if unresolvable.
    """
    if sport == "MLB":
        stat_key = _map_prop_to_stat_key(prop_type, sport="MLB")
        if not stat_key:
            return None
        return _resolve_mlb_stat_for_grading(player, stat_key, game_date)

    if sport == "NHL":
        stat_key = _map_prop_to_stat_key(prop_type, sport="NHL")
        if not stat_key:
            return None
        return _resolve_nhl_stat_for_grading(player, stat_key, game_date)

    if sport == "WNBA":
        stat_key = _map_prop_to_stat_key(prop_type)
        if not stat_key:
            return None
        athlete_id = fetch_wnba_full_roster_ids().get(player)
        return _resolve_espn_core_stat("WNBA", athlete_id, stat_key, game_date)

    if sport == "NBA":
        stat_key = _map_prop_to_stat_key(prop_type)
        if not stat_key:
            return None
        athlete_id = fetch_nba_full_roster_ids().get(player)
        return _resolve_espn_core_stat("NBA", athlete_id, stat_key, game_date)

    if sport == "NFL":
        stat_key = _map_prop_to_stat_key(prop_type)
        if not stat_key:
            return None
        nfl_db = fetch_nfl_full_player_database()
        athlete_id = (nfl_db.get(normalize_name(player), {}) or {}).get("athlete_id") \
            or ESPN_ATHLETE_IDS.get("NFL", {}).get(player)
        return _resolve_espn_core_stat("NFL", athlete_id, stat_key, game_date)

    return None


_GAME_GRADING_ESPN_SPORT_MAP = {
    "NBA": ("basketball", "nba"), "MLB": ("baseball", "mlb"),
    "NFL": ("football", "nfl"), "NHL": ("hockey", "nhl"),
    "WNBA": ("basketball", "wnba"),
}

def resolve_actual_game_result_for_grading(matchup: str, home: str, away: str, sport: str,
                                            market: str, pick: str, line, game_date: str):
    """
    Game-line counterpart to resolve_actual_stat_for_grading() — resolves
    WIN/LOSS/PUSH for a SPREAD/TOTAL/MONEYLINE/ALT LINE board pick, for
    grading a game-line board snapshot after the fact (added 2026-07-12,
    store_game_board_snapshot's grading path).

    Uses the exact same side-detection and outcome math as the interactive
    Check Results resolver in app.py (fixed 2026-07-12): team-name-in-pick
    containment (not the reverse — a bug that previously made SPREAD/ML
    resolution silently backwards), OVER/UNDER token matching rather than
    exact string equality (the stored pick text is always "OVER 8.5", not
    "OVER"), ALT LINE scored identically to SPREAD, and PUSH on an exact
    line tie. This mirrors that logic intentionally rather than importing
    it (that resolver lives inline in a Streamlit button handler) — if one
    changes, check the other.

    Returns (outcome, home_score, away_score). outcome is "WIN"/"LOSS"/
    "PUSH", or None if the game isn't found/final yet, or the pick text
    couldn't be parsed (caller should treat None as ungradable, same
    convention as resolve_actual_stat_for_grading).
    """
    es_el = _GAME_GRADING_ESPN_SPORT_MAP.get(sport)
    if not es_el:
        return None, None, None
    es, el = es_el
    try:
        line = float(line or 0)
    except (TypeError, ValueError):
        return None, None, None

    try:
        d0 = datetime.strptime(game_date, "%Y-%m-%d")
        check_dates = [d0.strftime("%Y%m%d")] + [
            (d0 + timedelta(days=delta)).strftime("%Y%m%d") for delta in (-1, 1)
        ]
    except (TypeError, ValueError):
        check_dates = [None]

    pick_norm = normalize_name(pick or "")
    home_norm = normalize_name(home or "")
    away_norm = normalize_name(away or "")
    matchup_lower = (matchup or "").lower()

    for ds in check_dates:
        try:
            params = {"dates": ds} if ds else {}
            resp = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{es}/{el}/scoreboard",
                headers={"User-Agent": "Mozilla/5.0"}, params=params, timeout=10,
            )
            if resp.status_code != 200:
                continue
            for event in resp.json().get("events", []):
                if not event.get("status", {}).get("type", {}).get("completed"):
                    continue
                comps = event.get("competitions", [{}])[0]
                teams = comps.get("competitors", [])
                if len(teams) < 2:
                    continue
                ev_home, ev_away = teams[0], teams[1]
                ev_home_name = ev_home.get("team", {}).get("displayName", "")
                ev_away_name = ev_away.get("team", {}).get("displayName", "")
                ev_home_abbr = ev_home.get("team", {}).get("abbreviation", "")
                ev_away_abbr = ev_away.get("team", {}).get("abbreviation", "")
                ev_home_norm = normalize_name(ev_home_name)
                ev_away_norm = normalize_name(ev_away_name)

                # Match this ESPN event to our snapshot's matchup by team
                # name (preferred) or abbreviation-in-matchup-string fallback.
                home_hit = (home_norm and home_norm in ev_home_norm) or \
                           (bool(ev_home_abbr) and ev_home_abbr.lower() in matchup_lower)
                away_hit = (away_norm and away_norm in ev_away_norm) or \
                           (bool(ev_away_abbr) and ev_away_abbr.lower() in matchup_lower)
                if not (home_hit and away_hit):
                    continue

                home_score = float(ev_home.get("score", 0) or 0)
                away_score = float(ev_away.get("score", 0) or 0)
                total = home_score + away_score
                market_up = (market or "").upper()

                if "SPREAD" in market_up or "ALT" in market_up:
                    pick_is_home = (bool(ev_home_norm) and ev_home_norm in pick_norm) or \
                                   (bool(ev_home_abbr) and ev_home_abbr.lower() in (pick or "").lower())
                    pick_is_away = (bool(ev_away_norm) and ev_away_norm in pick_norm) or \
                                   (bool(ev_away_abbr) and ev_away_abbr.lower() in (pick or "").lower())
                    if not pick_is_home and not pick_is_away:
                        return None, home_score, away_score
                    # "line" is always home-relative (negative = home
                    # favored). Fixed 2026-07-13: the previous formula
                    # (pick_score - opp_score + line) only gave the right
                    # answer for home picks -- an away pick needs the
                    # home_margin's sign flipped, not "line" added
                    # directly to the away score.
                    home_margin = home_score - away_score + line
                    if pick_is_home:
                        outcome = "PUSH" if home_margin == 0 else ("WIN" if home_margin > 0 else "LOSS")
                    else:
                        outcome = "PUSH" if home_margin == 0 else ("WIN" if home_margin < 0 else "LOSS")
                    return outcome, home_score, away_score

                if "TOTAL" in market_up:
                    pick_up = (pick or "").upper()
                    if "OVER" in pick_up:
                        outcome = "PUSH" if total == line else ("WIN" if total > line else "LOSS")
                    elif "UNDER" in pick_up:
                        outcome = "PUSH" if total == line else ("WIN" if total < line else "LOSS")
                    else:
                        return None, home_score, away_score
                    return outcome, home_score, away_score

                if "ML" in market_up or "MONEYLINE" in market_up:
                    pick_is_home = (bool(ev_home_norm) and ev_home_norm in pick_norm) or \
                                   (bool(ev_home_abbr) and ev_home_abbr.lower() in (pick or "").lower())
                    pick_is_away = (bool(ev_away_norm) and ev_away_norm in pick_norm) or \
                                   (bool(ev_away_abbr) and ev_away_abbr.lower() in (pick or "").lower())
                    if not pick_is_home and not pick_is_away:
                        return None, home_score, away_score
                    win_is_home = home_score > away_score
                    outcome = "WIN" if pick_is_home == win_is_home else "LOSS"
                    return outcome, home_score, away_score

                return None, home_score, away_score
        except (requests.RequestException, ValueError, TypeError, KeyError):
            continue
    return None, None, None

def fetch_player_id_bdl(player_name):
    """Search BallsDontLie for player ID by name."""
    if not BDL_API_KEY:
        return None
    cache_path = os.path.join(CACHE_DIR, f"bdl_pid_{normalize_name(player_name)}.pkl")
    if os.path.exists(cache_path):
        age_days = (time.time() - os.path.getmtime(cache_path)) / 86400
        if age_days < 7:
            return _safe_load_pkl(cache_path)
    try:
        r = _http.get(
            f"https://api.balldontlie.io/v1/players",
            headers={"Authorization": BDL_API_KEY},
            params={"search": player_name, "per_page": 5},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                pid = data[0]["id"]
                with open(cache_path, "wb") as f:
                    pickle.dump(pid, f)
                return pid
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return None

def fetch_player_game_logs(player_name, season=None, last_n=15):
    """
    Fetch last N game logs for a player.
    Returns list of game dicts with pts, reb, ast, min, opponent, date, home/away.
    """
    if season is None:
        season = _current_nba_season_start_year()
    if not BDL_API_KEY:
        return []
    cache_key = f"bdl_logs_{normalize_name(player_name)}_{season}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 4:
            return _safe_load_pkl(cache_path)

    pid = fetch_player_id_bdl(player_name)
    if not pid:
        return []

    try:
        r = _http.get(
            f"https://api.balldontlie.io/v1/stats",
            headers={"Authorization": BDL_API_KEY},
            params={
                "player_ids[]": pid,
                "seasons[]": season,
                "per_page": last_n,
                "sort_by": "date",
                "order": "desc"
            },
            timeout=15
        )
        if r.status_code != 200:
            return []

        games = r.json().get("data", [])
        logs = []
        for g in games:
            game = g.get("game", {})
            team = g.get("team", {})
            home_team_id = game.get("home_team_id")
            is_home = team.get("id") == home_team_id
            opp_id = game.get("visitor_team_id") if is_home else game.get("home_team_id")

            logs.append({
                "date": game.get("date", "")[:10],
                "home": is_home,
                "opponent_id": opp_id,
                "pts": g.get("pts", 0),
                "reb": g.get("reb", 0),
                "ast": g.get("ast", 0),
                "stl": g.get("stl", 0),
                "blk": g.get("blk", 0),
                "turnover": g.get("turnover", 0),
                "fg3m": g.get("fg3m", 0),
                "min": g.get("min", "0"),
                "pra": (g.get("pts",0) or 0) + (g.get("reb",0) or 0) + (g.get("ast",0) or 0),
            })

        if logs:
            with open(cache_path, "wb") as f:
                pickle.dump(logs, f)
        return logs

    except (IOError, ValueError) as e:
        return []

def fetch_mlb_confirmed_lineups():
    """
    Fetch confirmed MLB batting lineups for today's games.
    Uses statsapi.mlb.com — same API as mlb averages, already trusted.
    
    Returns dict: {team_abbr: [player1, player2, ...]} in batting order.
    Lineup is "confirmed" when it comes from today's actual game feed.
    
    Why this matters: cleanup hitter scratches move HR/RBI props significantly.
    A confirmed lineup vs a projected lineup is a real betting edge.
    """
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        schedule_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today_str}&hydrate=lineups,probablePitcher"
        r = _http.get(schedule_url, timeout=10)
        if r.status_code != 200:
            return {}
        games = r.json().get("dates", [{}])[0].get("games", [])
        lineups = {}
        for game in games:
            game_id = game.get("gamePk")
            if not game_id:
                continue
            # Get lineups from game feed
            feed_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live?fields=gameData,liveData,boxscore,teams,batters,battingOrder,players,fullName,currentTeam,abbreviation"
            try:
                rf = _http.get(feed_url, timeout=8)
                if rf.status_code != 200:
                    continue
                feed = rf.json()
                # Extract home/away batting orders
                for side in ("home", "away"):
                    team_data = feed.get("liveData",{}).get("boxscore",{}).get("teams",{}).get(side,{})
                    batting_order = team_data.get("battingOrder", [])
                    players = team_data.get("players", {})
                    team_abbr = feed.get("gameData",{}).get("teams",{}).get(side,{}).get("abbreviation","")
                    if batting_order and team_abbr:
                        lineup = []
                        for pid in batting_order:
                            player_key = f"ID{pid}"
                            pdata = players.get(player_key, {})
                            pname = pdata.get("person",{}).get("fullName","")
                            pos = pdata.get("position",{}).get("abbreviation","")
                            if pname:
                                lineup.append({"name": pname, "position": pos, "batting_order": len(lineup)+1})
                        if lineup:
                            lineups[team_abbr] = {
                                "players": lineup,
                                "confirmed": len(lineup) >= 9,
                                "source": "MLB Stats API",
                                "fetched_at": datetime.now().strftime("%H:%M"),
                            }
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return lineups
    except (requests.RequestException, ValueError, KeyError):
        return {}

def fetch_sleeper_scoreboard(sport: str, target_date=None):
    """
    Generic version of fetch_sleeper_mlb_scoreboard() (Jul 10 2026) — same
    confirmed-public, no-auth endpoint, generalized to any sport Sleeper's
    /scores page covers: mlb, nba, nfl, nhl, wnba, cbb.

    GET https://api.sleeper.app/scores/{sport}/date/YYYY-MM-DD

    IMPORTANT CAVEAT: only MLB's response shape has actually been verified
    against a live capture (confirmed field names: team, name, score,
    probable_pitcher_name, lineup entries with inning/order/sequence/
    player_name). Non-MLB sports have NOT been individually verified — the
    "inning" field is baseball terminology and almost certainly doesn't
    apply the same way to NBA/NFL/NHL/WNBA lineups (no innings in those
    sports). This function does NOT filter by inning==0 for non-MLB sports
    for that reason — it returns the full raw lineup list as posted, which
    may include bench players or a different starters/subs distinction
    entirely depending on how Sleeper structures each sport. Treat non-MLB
    output as provisional until spot-checked against a real game day for
    that sport.

    Returns a dict keyed by game_id:
        {
          "<game_id>": {
            "status": "...",
            "away": {"team": abbr, "name": ..., "score": ...,
                      "lineup": [{"name": ..., "order": ...}, ...] (raw,
                      unfiltered for non-MLB sports)},
            "home": {...same shape...},
            "fetched_at": iso8601,
          }, ...
        }
    Returns {} (never raises) on any failure.
    """
    sport = sport.lower()
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")
    cache_path = os.path.join(CACHE_DIR, f"sleeper_scoreboard_{sport}_{target_date}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 15:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    url = f"https://api.sleeper.app/scores/{sport}/date/{target_date}"
    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        resp.raise_for_status()
        games = resp.json()
    except Exception as e:
        logging.warning(f"[Sleeper] {sport} scoreboard fetch failed: {e}")
        return {}

    fetched_at = datetime.now(timezone.utc).isoformat()
    result = {}
    for g in games or []:
        game_id = g.get("game_id")
        if not game_id:
            continue
        meta = g.get("metadata") or {}

        def _side(block, is_mlb=(sport == "mlb")):
            block = block or {}
            raw_lineup = block.get("lineup") or []
            if is_mlb:
                starters = [p for p in raw_lineup if p.get("player_name") and p.get("inning") == 0]
                starters.sort(key=lambda p: p.get("sequence", 0))
                lineup = [
                    {"name": p.get("player_name", ""), "batting_order": p.get("order", 0)}
                    for p in starters
                ]
            else:
                # Unverified for this sport — pass through as-is rather than
                # guess at a starters/subs filter that may not apply.
                lineup = [
                    {"name": p.get("player_name", ""), "order": p.get("order", 0)}
                    for p in raw_lineup if p.get("player_name")
                ]
            return {
                "team": block.get("team", ""),
                "name": block.get("name", ""),
                "score": block.get("score"),
                "probable_pitcher": block.get("probable_pitcher_name", "") if is_mlb else None,
                "lineup": lineup,
            }

        result[game_id] = {
            "status": g.get("status", ""),
            "away": _side(meta.get("away_team")),
            "home": _side(meta.get("home_team")),
            "fetched_at": fetched_at,
        }
    if result:
        _safe_save_pkl(cache_path, result)
    return result


def fetch_sleeper_mlb_scoreboard(target_date=None):
    """
    Pulls today's (or target_date's) real MLB games, scores, and starting
    lineups from Sleeper's public consumer-app API — the same endpoint
    sleeper.com/scores calls in-browser, NOT the documented api.sleeper.app/v1
    fantasy-league API (which has no cross-league scoreboard endpoint at all).

    Verified live via direct HTTP fetch (Jul 10 2026):
        GET https://api.sleeper.app/scores/mlb/date/YYYY-MM-DD
    Returns a JSON list of games. No authentication required — no API key,
    JWT, or cookie needed; confirmed 200 OK from a plain unauthenticated
    request. Each game's metadata.away_team / metadata.home_team include
    `team` (3-letter abbr), `name`, `score`, `probable_pitcher_name`, and a
    `lineup` list of {id, player_name, order, sequence} once posted.

    Thin wrapper over fetch_sleeper_scoreboard("mlb", ...) — kept as its own
    function since fetch_mlb_confirmed_lineups_with_fallback() already calls
    it by this name.

    Returns a dict keyed by game_id:
        {
          "<game_id>": {
            "status": "complete" | "pregame" | "in_progress" | ...,
            "away": {"team": "CHC", "name": "Cubs", "score": 2,
                      "probable_pitcher": "David Peterson",
                      "lineup": [{"name": "...", "batting_order": 1}, ...]},
            "home": {...same shape...},
            "fetched_at": "<iso8601>",
          },
          ...
        }
    Returns {} (never raises) on any network/parse failure so callers can
    treat this purely as an optional fallback source.
    """
    return fetch_sleeper_scoreboard("mlb", target_date)


def fetch_nhl_starting_goalies():
    """
    Fills a previously-empty stub (app.py has called this since before the
    Sleeper work, guarded by an `in globals()` check that always no-op'd
    since the function didn't exist).

    Uses the same confirmed-public, no-auth Sleeper scoreboard endpoint as
    MLB (fetch_sleeper_scoreboard("nhl", ...)). UNVERIFIED CAVEAT: NHL's
    exact lineup field shape has not been individually confirmed against a
    live NHL game day the way MLB was — this assumes the same "order 0 =
    starter in the non-numbered roster slot" pattern MLB uses for its
    probable pitcher (MLB's order=0 entry is always the starting pitcher,
    with batters as order 1-9), and treats NHL's order=0 lineup entry the
    same way for the starting goalie. If NHL's actual data doesn't follow
    that pattern, this will silently return wrong or empty data rather than
    erroring — spot-check against a live NHL game day before trusting it.

    Returns {team_abbr: {"goalie": name, "confirmed": bool, "source": str}}
    """
    try:
        games = fetch_sleeper_scoreboard("nhl")
    except Exception as e:
        print(f"[WARN] fetch_nhl_starting_goalies: {e}")
        return {}
    result = {}
    for g in (games or {}).values():
        for side in ("away", "home"):
            team_block = g.get(side, {}) or {}
            abbr = team_block.get("team", "")
            lineup = team_block.get("lineup", [])
            if not abbr or not lineup:
                continue
            goalie_entry = next((p for p in lineup if p.get("order") == 0), None)
            if goalie_entry and goalie_entry.get("name"):
                result[abbr] = {
                    "goalie": goalie_entry["name"],
                    "confirmed": True,
                    "source": "Sleeper (unverified field mapping)",
                }
    return result


def fetch_mlb_confirmed_lineups_with_fallback():
    """
    Same contract as fetch_mlb_confirmed_lineups(), but fills in any team
    statsapi.mlb.com didn't return (rate-limited / "Max retries exceeded" /
    down — the known failure mode against statsapi) using Sleeper's live
    scoreboard API as a second, independent source. statsapi stays primary
    since it's the longer-trusted source; Sleeper only fills gaps.

    fetch_sleeper_mlb_scoreboard() (implemented Jul 10 2026, see its own
    docstring above) is a public, unauthenticated endpoint — no secrets
    or JWT needed, so this fallback runs unconditionally.
    """
    lineups = fetch_mlb_confirmed_lineups()
    try:
        sleeper_games = fetch_sleeper_mlb_scoreboard()
        for g in (sleeper_games or {}).values():
            for side in ("away", "home"):
                team_block = g.get(side, {}) or {}
                abbr = team_block.get("team", "")
                sleeper_lineup = team_block.get("lineup", [])
                if abbr and abbr not in lineups and sleeper_lineup:
                    lineups[abbr] = {
                        "players": [
                            {"name": p.get("name", ""), "position": "",
                             "batting_order": p.get("batting_order", 0)}
                            for p in sleeper_lineup
                        ],
                        "confirmed": len(sleeper_lineup) >= 9,
                        "source": "Sleeper (fallback)",
                        "fetched_at": g.get("fetched_at", ""),
                    }
    except Exception:
        pass
    return lineups

def fetch_draftkings_direct(sport):
    """Fetch DraftKings props directly using curl_cffi. Fallback when OddsPAPI is down."""
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://sportsbook.draftkings.com",
        "Referer": "https://sportsbook.draftkings.com/",
    }

    # League IDs and player prop subcategory IDs
    league_map = {
        "NBA":  {"leagueId": "42648",    "subCatId": "16477"},  # NBA player props
        "MLB":  {"leagueId": "84240",    "subCatId": "11145"},  # MLB player props (fixed Jun 2026)
        "NHL":  {"leagueId": "42133",    "subCatId": "16477"},
        "WNBA": {"leagueId": "92483",    "subCatId": "16477"},
        "NFL":  {"leagueId": "88670775", "subCatId": "16477"},
    }
    cfg = league_map.get(sport, league_map["NBA"])
    props = []

    cache_path = os.path.join(CACHE_DIR, f"draftkings_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    try:
        lid = cfg["leagueId"]
        sid = cfg["subCatId"]

        url = "https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets"
        params = {
            "isBatchable": "false",
            "templateVars": lid,
            "eventsQuery": f"$filter=leagueId eq '{lid}' AND clientMetadata/Subcategories/any(s: s/Id eq '{sid}')",
            "marketsQuery": f"$filter=clientMetadata/subCategoryId eq '{sid}' AND tags/all(t: t ne 'SportcastBetBuilder')",
            "include": "Events",
            "entity": "events",
        }

        r = session.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[WARN] Superbook: HTTP {r.status_code} from Kambi (sport={sport})")
            return []

        data = r.json()
        events = data.get("events", [])
        markets = data.get("markets", [])
        selections = data.get("selections", [])

        # Build selection lookup by marketId
        sel_by_market = {}
        for sel in selections:
            mid = sel.get("marketId")
            if mid:
                sel_by_market.setdefault(mid, []).append(sel)

        for mkt in markets:
            mkt_name = mkt.get("name", "")
            mkt_id = mkt.get("id") or mkt.get("marketId")

            for sel in sel_by_market.get(mkt_id, []):
                label = sel.get("label", "")
                parts = sel.get("participants", [])
                player = parts[0].get("name","") if parts else ""
                if not player:
                    player = label
                line = sel.get("points") or sel.get("line") or sel.get("handicap")
                odds_am = sel.get("displayOdds", {}).get("american", "—")

                # Parse Over/Under from label
                if "Under" in label:
                    side = "UNDER"
                    if not player or player == label:
                        player = label.replace("Under","").strip()
                elif "Over" in label:
                    side = "OVER"
                    if not player or player == label:
                        player = label.replace("Over","").strip()
                else:
                    side = "OVER"
                # Extract line from label if not in fields
                if line is None:
                    _lm = re.search(r"([\d.]+)", label)
                    if _lm:
                        try: line = float(_lm.group(1))
                        except (ValueError, TypeError, ZeroDivisionError): pass

                if player and line is not None:
                    props.append({
                        "Player": player, "Prop": mkt_name,
                        "Line": float(str(line).replace("+", "")),
                        "Side": side,
                        "OverOdds": str(odds_am) if side == "OVER" else "—",
                        "UnderOdds": str(odds_am) if side == "UNDER" else "—",
                        "Book": "DraftKings", "Sport": sport,
                        "source": "draftkings_direct",
                    })

        # Cache
        # Event-level fallback (declanwalpole pattern):
        # If subcat query returned nothing, fetch today's events and pull all markets
        if not props:
            try:
                events_url = f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/dkusny/v1/leagues/{lid}/eventgroups"
                r_ev = session.get(events_url, headers=headers, timeout=12)
                if r_ev.status_code == 200:
                    ev_data = r_ev.json()
                    for eg in ev_data.get("eventGroups", []):
                        for ev in eg.get("events", []):
                            eid = ev.get("eventId") or ev.get("id")
                            if not eid:
                                continue
                            # Per-event endpoint — exposes ALL markets/subcategories
                            ev_url = f"https://sportsbook.draftkings.com/sites/US-SB/api/v3/event/{eid}"
                            r_e = session.get(ev_url, headers=headers, timeout=10)
                            if r_e.status_code != 200:
                                continue
                            e_data = r_e.json()
                            for cat in e_data.get("eventCategories", []):
                                for mg in cat.get("componentizedOffers", []):
                                    grp_name = mg.get("subcategoryName", "")
                                    for mkt_group in mg.get("offers", []):
                                        for mkt in (mkt_group if isinstance(mkt_group, list) else [mkt_group]):
                                            if mkt.get("isSuspended") or not mkt.get("isOpen"):
                                                continue
                                            mkt_label = mkt.get("label", "")
                                            for outcome in mkt.get("outcomes", []):
                                                if outcome.get("hidden"):
                                                    continue
                                                o_label = outcome.get("label", "")
                                                parts = outcome.get("participants", [])
                                                player = parts[0].get("name", "") if parts else ""
                                                if not player:
                                                    player = o_label
                                                line = outcome.get("line") or outcome.get("points") or outcome.get("handicap")
                                                odds_am = outcome.get("oddsAmerican", "") or outcome.get("displayOdds", {}).get("american", "—")
                                                side = "UNDER" if "Under" in o_label else "OVER"
                                                if line is None:
                                                    _lm2 = re.search(r"([\d.]+)", o_label)
                                                    if _lm2:
                                                        try: line = float(_lm2.group(1))
                                                        except (ValueError, TypeError): pass
                                                if player and line is not None:
                                                    try:
                                                        props.append({
                                                            "Player": player, "Prop": mkt_label or grp_name,
                                                            "Line": float(str(line).replace("+", "")),
                                                            "Side": side,
                                                            "OverOdds": str(odds_am) if side == "OVER" else "—",
                                                            "UnderOdds": str(odds_am) if side == "UNDER" else "—",
                                                            "Book": "DraftKings", "Sport": sport,
                                                            "source": "draftkings_event_level",
                                                        })
                                                    except (ValueError, TypeError):
                                                        continue
                            time.sleep(0.2)  # be gentle
            except (IOError, ValueError, KeyError) as _ef:
                print(f"[WARN] DK event-level fallback: {_ef}")

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except (IOError, ValueError) as _e:
            print(f"[WARN] {_e}")

    return props

def fetch_betmgm_direct(sport):
    """Fetch BetMGM props directly using curl_cffi."""
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    MGM_KEY = "N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.az.betmgm.com",
        "Referer": "https://www.az.betmgm.com/",
    }
    props = []

    cache_path = os.path.join(CACHE_DIR, f"betmgm_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    # Sport config: sportId for listing fixtures
    sport_ids = {"NBA": 7, "MLB": 23, "NHL": 19, "WNBA": 7, "NFL": 11}
    sid = sport_ids.get(sport, 7)

    try:
        # Step 1: Get today's fixtures
        r1 = session.get(
            "https://www.az.betmgm.com/cds-api/bettingoffer/fixtures",
            params={
                "x-bwin-accessid": MGM_KEY,
                "lang": "en-us", "country": "US", "userCountry": "US",
                "subdivision": "US-AZ", "offerMapping": "Filtered",
                "sportIds": sid, "fixtureTypes": "Standard",
                "state": "Latest", "skip": 0, "take": 30, "sortBy": "StartDate",
            },
            headers=headers, timeout=15
        )
        if r1.status_code != 200:
            return []

        fixtures = r1.json().get("fixtures", [])

        # Step 2: For each fixture, get player props
        for fix in fixtures[:8]:
            fix_id = fix.get("id")
            if not fix_id:
                continue

            # Get all game IDs (market categories) for this fixture
            games = fix.get("games", [])
            prop_game_ids = []
            for g in games:
                gname = (g.get("name", {}).get("value", "") or "").lower()
                if any(kw in gname for kw in
                       ["point", "rebound", "assist", "strikeout", "hit",
                        "home run", "rbi", "goal", "shot", "save",
                        "yard", "touchdown", "pass", "rush", "pra",
                        "fantasy", "three", "steal", "block", "bases"]):
                    gid = g.get("id")
                    if gid:
                        prop_game_ids.append(str(gid))

            if not prop_game_ids:
                # Try fixture-offers without game filter
                prop_game_ids = [str(g.get("id","")) for g in games if g.get("id")]

            if not prop_game_ids:
                continue

            r2 = session.get(
                "https://www.az.betmgm.com/cds-api/bettingoffer/fixture-offers",
                params={
                    "x-bwin-accessid": MGM_KEY,
                    "lang": "en-us", "country": "US", "userCountry": "US",
                    "subdivision": "US-AZ",
                    "fixtureIds": fix_id,
                    "gameIds": ",".join(prop_game_ids[:10]),
                    "offerMapping": "Filtered",
                },
                headers=headers, timeout=10
            )
            if r2.status_code != 200:
                continue

            data2 = r2.json()
            fixture_data = data2.get("fixtures", [data2]) if isinstance(data2, dict) else data2

            for fd in fixture_data:
                for game in fd.get("games", []):
                    mkt_name = game.get("name", {}).get("value", "")
                    for result in game.get("results", []):
                        full_name = result.get("name", {}).get("value", "")
                        odds_d    = result.get("price", {}).get("americanOdds")
                        attr      = result.get("attr", "")

                        # Parse player name and side from full_name
                        player = full_name
                        side = "OVER"
                        if " Over " in full_name:
                            player = full_name.split(" Over ")[0].strip()
                            side = "OVER"
                        elif " Under " in full_name:
                            player = full_name.split(" Under ")[0].strip()
                            side = "UNDER"

                        line = attr or result.get("handicap")
                        if not player or line is None or line == "":
                            continue

                        try:
                            line_f = float(str(line).replace("+", ""))
                        except (ValueError, TypeError):
                            continue

                        odds_str = "—"
                        if odds_d is not None:
                            odds_str = f"{'+' if odds_d > 0 else ''}{int(odds_d)}"

                        props.append({
                            "Player": player, "Prop": mkt_name,
                            "Line": line_f, "Side": side,
                            "OverOdds": odds_str if side == "OVER" else "—",
                            "UnderOdds": odds_str if side == "UNDER" else "—",
                            "Book": "BetMGM", "Sport": sport,
                            "source": "betmgm_direct",
                        })

            time.sleep(0.3)

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except (IOError, ValueError) as _e:
            print(f"[WARN] {_e}")

    return props


# ── Caesars Playwright token harvester ───────────────────────────────────────


def harvest_caesars_tokens(max_wait: int = 90) -> dict:
    """
    Playwright-based Caesars JWT + AWS WAF token harvester.

    WHY: fetch_caesars_direct() requires two auth headers — "authorization:
    Bearer <JWT>" and "x-aws-waf-token" — that Caesars injects client-side
    after a real browser login.  The JWT carries a ~24h "exp" claim and must
    be refreshed whenever it expires; previously that required a manual
    DevTools copy-paste.  This function automates that refresh by launching
    a real headed Chromium session, navigating to sportsbook.caesars.com, and
    intercepting the outgoing requests that carry those headers.

    HOW: Playwright's page.on("request", ...) fires for every outgoing XHR.
    Requests to api.americanwagering.com always include the freshly-generated
    auth headers — we read them via request.all_headers() and stop as soon
    as we see a valid Bearer token (len > 50 chars, starts with "Bearer ").

    Automation masking applied (same pattern as fetch_fanduel_game_lines_playwright):
      --disable-blink-features=AutomationControlled (launch arg)
      navigator.webdriver = undefined               (add_init_script)
      window.chrome, navigator.plugins, languages   (add_init_script)

    Headless: defaults to headed (False) — Caesars WAF challenge passes more
    reliably in headed mode.  Set env var CAESARS_HEADLESS=1 to force headless.
    Auto-falls back to headless=True if headed launch raises (no $DISPLAY).

    Persists tokens in two places so fetch_caesars_direct() can pick them up
    immediately on retry without re-running Playwright:
      1. Gist key "caesars_tokens"
             → {"bearer_jwt": "…", "waf_token": "…", "captured_at": "…"}
             (exact shape load_from_gist("caesars_tokens", None) returns)
      2. CACHE_DIR/caesars_session_token.txt
             → bearer_jwt on line 1, waf_token on line 2

    Returns the harvested dict on success, {} on any failure (errors are
    logged via log_error_to_session, never raised).
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as _PWTimeout
    except ImportError:
        log_error_to_session(
            "harvest_caesars_tokens",
            "playwright not installed — pip install playwright && playwright install chromium",
            "warning",
        )
        return {}

    harvested: dict = {}
    _stop = {"done": False}

    def _on_request(request):
        """Intercept every outgoing request; grab auth headers from Caesars API calls."""
        if _stop["done"]:
            return
        if "americanwagering.com" not in request.url:
            return
        try:
            hdrs = request.all_headers()
        except Exception:
            return
        auth = hdrs.get("authorization", "")
        # Real JWTs are several hundred characters; reject stubs / basic auth
        if not auth.startswith("Bearer ") or len(auth) < 60:
            return
        harvested["bearer_jwt"]  = auth[len("Bearer "):]
        harvested["waf_token"]   = hdrs.get("x-aws-waf-token", "")
        harvested["captured_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        _stop["done"] = True

    try:
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ]
            headless = bool(os.environ.get("CAESARS_HEADLESS", ""))
            try:
                browser = pw.chromium.launch(headless=headless, args=launch_args)
            except Exception:
                # No display available (e.g. Streamlit Cloud) — fall back to headless
                browser = pw.chromium.launch(headless=True, args=launch_args)

            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 720},
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = ctx.new_page()
            page.on("request", _on_request)

            # Navigate to the AZ sportsbook — the az subdomain is the default;
            # if the org switches states, update FANDUEL_STATE-style env var.
            try:
                page.goto(
                    "https://sportsbook.caesars.com/us/az/bet",
                    wait_until="networkidle",
                    timeout=60_000,
                )
            except _PWTimeout:
                # networkidle can time out on heavy pages; requests are still
                # in-flight — the polling loop below will catch them.
                pass
            except Exception:
                pass

            # Poll until a valid token arrives or max_wait elapses
            deadline = time.time() + max_wait
            while not _stop["done"] and time.time() < deadline:
                time.sleep(1)

            ctx.close()
            browser.close()

    except Exception as _e:
        log_error_to_session("harvest_caesars_tokens", str(_e)[:150], "warning")
        return {}

    if not harvested.get("bearer_jwt"):
        log_error_to_session(
            "harvest_caesars_tokens",
            f"No Bearer token captured after {max_wait}s — "
            "confirm the Caesars account is logged in at sportsbook.caesars.com "
            "on the machine running Playwright",
            "warning",
        )
        return {}

    # ── Persist to Gist ──────────────────────────────────────────────────────
    # File is "betcouncil_caesars_tokens.json" -- this MUST match the filename
    # every consumer reads (_get_caesars_tokens, fetch_caesars_waf_from_gist,
    # the curl_cffi Caesars props fetcher in betcouncil_auto_scraper.py, and
    # scripts/caesars_token_refresh.py). Previously wrote to "caesars_tokens.json"
    # instead -- a filename that no reader in the codebase actually looked at,
    # so every token this function ever harvested was silently discarded.
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        try:
            _http.patch(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"files": {"betcouncil_caesars_tokens.json": {"content": json.dumps(harvested, indent=2)}}},
                timeout=10,
            )
        except Exception as _ge:
            log_error_to_session(
                "harvest_caesars_tokens",
                f"Gist write failed: {str(_ge)[:80]}",
                "warning",
            )

    # ── Local file cache ─────────────────────────────────────────────────────
    try:
        czr_cache = os.path.join(CACHE_DIR, "caesars_session_token.txt")
        with open(czr_cache, "w") as _f:
            _f.write(harvested["bearer_jwt"])
            if harvested.get("waf_token"):
                _f.write("\n" + harvested["waf_token"])
    except (IOError, OSError):
        pass

    return harvested
def harvest_draftkings_tokens(max_wait: int = 90) -> dict:
    """
    Playwright-based DraftKings Authorization + x-api-key harvester.

    WHY: fetch_draftkings_direct() hits sportsbook-nash.draftkings.com which
    does not require auth for public odds, but the richer api.draftkings.com
    endpoints (used for live props and personalised offers) require two
    client-side headers injected after a real browser session:
      - "authorization: Bearer <JWT>"
      - "x-api-key: <key>"
    This function automates extraction by launching a real Chromium session,
    navigating to sportsbook.draftkings.com, and intercepting outgoing XHR
    requests to api.draftkings.com to grab those headers.

    HOW: Playwright page.on("request", ...) fires for every outgoing request.
    Any request to api.draftkings.com is inspected; we capture the first
    request that carries a Bearer token (len > 50) and an x-api-key value.

    Automation masking applied (same pattern as harvest_caesars_tokens):
      --disable-blink-features=AutomationControlled (launch arg)
      navigator.webdriver = undefined               (add_init_script)
      window.chrome, navigator.plugins, languages   (add_init_script)

    Headless: defaults to headed (False) — DraftKings bot detection is more
    reliable to bypass in headed mode.  Set env var DRAFTKINGS_HEADLESS=1 to
    force headless.  Auto-falls back to headless=True if headed launch raises
    (no $DISPLAY available).

    Persists tokens in two places so callers can pick them up immediately:
      1. Gist key "draftkings_tokens"
             → {"bearer_jwt": "…", "api_key": "…", "captured_at": "…"}
      2. CACHE_DIR/draftkings_session_token.txt
             → bearer_jwt on line 1, api_key on line 2

    Returns the harvested dict on success, {} on any failure (errors are
    logged via log_error_to_session, never raised).
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as _PWTimeout
    except ImportError:
        log_error_to_session(
            "harvest_draftkings_tokens",
            "playwright not installed — pip install playwright && playwright install chromium",
            "warning",
        )
        return {}

    harvested: dict = {}
    _stop = {"done": False}

    def _on_request(request):
        """Intercept every outgoing request; grab auth headers from DraftKings API calls."""
        if _stop["done"]:
            return
        if "api.draftkings.com" not in request.url:
            return
        try:
            hdrs = request.all_headers()
        except Exception:
            return
        auth = hdrs.get("authorization", "")
        api_key = hdrs.get("x-api-key", "")
        # Real JWTs are several hundred characters; reject stubs / basic auth
        if not auth.startswith("Bearer ") or len(auth) < 60:
            return
        harvested["bearer_jwt"]  = auth[len("Bearer "):]
        harvested["api_key"]     = api_key
        harvested["captured_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        _stop["done"] = True

    try:
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ]
            headless = bool(os.environ.get("DRAFTKINGS_HEADLESS", ""))
            try:
                browser = pw.chromium.launch(headless=headless, args=launch_args)
            except Exception:
                # No display available (e.g. Streamlit Cloud) — fall back to headless
                browser = pw.chromium.launch(headless=True, args=launch_args)

            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 720},
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = ctx.new_page()
            page.on("request", _on_request)

            # Navigate to the DraftKings sportsbook home page.
            # networkidle can time out on heavy JS bundles — that's fine; our
            # request listener will have fired well before the page is fully idle.
            try:
                page.goto(
                    "https://sportsbook.draftkings.com",
                    wait_until="networkidle",
                    timeout=60_000,
                )
            except _PWTimeout:
                pass
            except Exception:
                pass

            # Poll until a valid token arrives or max_wait elapses
            deadline = time.time() + max_wait
            while not _stop["done"] and time.time() < deadline:
                time.sleep(1)

            ctx.close()
            browser.close()

    except Exception as _e:
        log_error_to_session("harvest_draftkings_tokens", str(_e)[:150], "warning")
        return {}

    if not harvested.get("bearer_jwt"):
        log_error_to_session(
            "harvest_draftkings_tokens",
            f"No Bearer token captured after {max_wait}s — "
            "confirm a DraftKings account is logged in at sportsbook.draftkings.com "
            "on the machine running Playwright",
            "warning",
        )
        return {}

    # ── Persist to Gist ──────────────────────────────────────────────────────
    # File is named "draftkings_tokens.json"; content is the JSON-serialised dict.
    # load_from_gist("draftkings_tokens", None) in app.py parses this back to a
    # dict — that's the shape fetch_draftkings_direct() reads from the Gist.
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        try:
            _http.patch(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"files": {"draftkings_tokens.json": {"content": json.dumps(harvested, indent=2)}}},
                timeout=10,
            )
        except Exception as _ge:
            log_error_to_session(
                "harvest_draftkings_tokens",
                f"Gist write failed: {str(_ge)[:80]}",
                "warning",
            )

    # ── Local file cache ─────────────────────────────────────────────────────
    try:
        dk_cache = os.path.join(CACHE_DIR, "draftkings_session_token.txt")
        with open(dk_cache, "w") as _f:
            _f.write(harvested["bearer_jwt"])
            if harvested.get("api_key"):
                _f.write("\n" + harvested["api_key"])
    except (IOError, OSError):
        pass

    return harvested


def fetch_caesars_direct(sport):
    """Fetch Caesars props directly via api.americanwagering.com.

    Parsing rewritten 2026-06-20 based on a real captured response body from the
    SCHEDULE|Batter Props tab (105-523kB responses, status 200 — confirmed these
    requests are NOT blocked the way FanDuel's PerimeterX-gated endpoint is).

    CONFIRMED real structure (differs meaningfully from this function's prior
    assumption):
    - Markets are nested under event["keyMarketGroups"][i]["markets"], NOT a flat
      event["markets"] list.
    - Player name is in market["metadata"]["player"] — a clean string, no parsing
      needed. The previous version tried to extract player name from
      selection["name"], which only ever contains the count/line text (e.g. "|2+|"),
      never a player name — that was a real bug, not just an inefficiency.
    - market["metadata"]["marketTypeCode"] gives a clean machine-readable prop type
      (e.g. "player-alt-hits") — more reliable than keyword-matching market name.
    - Selections use a count-based format for alt-line markets: selection["name"]
      is "|N+|" (e.g. "|1+|", "|2+|", "|3+|"), selection["type"] is the literal
      string "over", and selection["price"]["a"] is American odds. The line value
      is derived as N-0.5 (e.g. "2+" implies a 1.5 line, OVER side) since Caesars
      doesn't expose a separate numeric line field for these markets — confirmed
      from the real "Hits" market data (1+/2+/3+ with no other line field present).

    NOT yet confirmed: the exact request URL for the captured response (only the
    response body was captured, not headers/URL) — the competitions+tab discovery
    path below is the pre-existing best-effort structure and has NOT been verified
    request-side. If this returns no data, that URL path is the next thing to
    re-verify via a full cURL capture (Copy as cURL), not the parsing logic below,
    which IS verified against real response data.
    """
    try:
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://sportsbook.caesars.com",
        "Referer": "https://sportsbook.caesars.com/",
    }

    # AUTH REQUIREMENT confirmed via real DevTools cURL capture, 2026-06-20: this
    # endpoint requires THREE additional headers the prior version never sent —
    # "authorization: Bearer <JWT>", "sessionid: <same JWT>", and "x-aws-waf-token"
    # (an AWS WAF challenge token, separate mechanism from the JWT). Their absence
    # is the likely real cause of this function returning nothing, more so than the
    # parsing bug fixed in the previous commit.
    #
    # IMPORTANT — this JWT is NOT a generic API key. Decoding it shows a "sub" claim
    # matching the account's player ID format seen elsewhere (e.g. the
    # excluded-players/player-id/ endpoint) — this is a real, personal, LOGGED-IN
    # account session token, not an anonymous read-only credential. That changes the
    # risk profile versus FanDuel's PerimeterX token: this ties scraper traffic
    # directly to the account, subject to the same ~24h expiry pattern (per its JWT
    # "exp" claim) AND to whatever rate-limiting or ToS exposure applies to an
    # account's session being used for repeated automated requests. This is a
    # decision worth making deliberately, not silently baking into a scheduled
    # scraper — hence reading it from configurable secrets/cache below, never
    # hardcoded, and documented here so the tradeoff is visible.
    czr_bearer = ""
    czr_waf_token = ""
    try:
        czr_bearer = st.secrets.get("CAESARS_SESSION_TOKEN", "")
        czr_waf_token = st.secrets.get("CAESARS_WAF_TOKEN", "")
    except Exception:
        pass
    if not czr_bearer:
        # Picks up tokens pushed by caesars-harvester.js (local Playwright tool
        # run manually after logging into the account), so the daily refresh no
        # longer requires copy-pasting into Streamlit secrets by hand. Same
        # ~24h staleness window as the local file cache below, since it's
        # captured from the same JWT.
        gist_tokens = load_from_gist("caesars_tokens", None)
        if gist_tokens:
            try:
                captured_at = gist_tokens.get("captured_at", "")
                age_mins = (time.time() - datetime.fromisoformat(captured_at.replace("Z", "+00:00")).timestamp()) / 60
            except (ValueError, TypeError):
                age_mins = 9999
            if age_mins < 1200:
                czr_bearer = gist_tokens.get("bearer_jwt", "")
                czr_waf_token = gist_tokens.get("waf_token", "")
    if not czr_bearer:
        czr_token_cache = os.path.join(CACHE_DIR, "caesars_session_token.txt")
        if os.path.exists(czr_token_cache):
            try:
                age_mins = (time.time() - os.path.getmtime(czr_token_cache)) / 60
                if age_mins < 1200:  # JWT observed ~24h (1440min) validity; refresh well before
                    with open(czr_token_cache, "r") as f:
                        cached_lines = f.read().strip().split("\n")
                        czr_bearer = cached_lines[0] if cached_lines else ""
                        czr_waf_token = cached_lines[1] if len(cached_lines) > 1 else ""
            except (IOError, OSError, IndexError):
                pass
    if not czr_bearer:
        # No valid session token configured — expected state until the account
        # session is deliberately wired in. Returning [] cleanly rather than
        # attempting an unauthenticated request that's confirmed to fail.
        st.warning(
            "🔑 Caesars JWT expired or not configured — re-run caesars-harvester.js "
            "after logging into sportsbook.caesars.com, or paste the token into "
            "CAESARS_SESSION_TOKEN in Streamlit secrets. Skipping Caesars scrape."
        )
        return []

    headers["authorization"] = f"Bearer {czr_bearer}"
    headers["sessionid"] = czr_bearer
    if czr_waf_token:
        headers["x-aws-waf-token"] = czr_waf_token
    props = []

    cache_path = os.path.join(CACHE_DIR, f"caesars_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    sport_map = {
        "NBA": "basketball", "MLB": "baseball", "NHL": "icehockey",
        "WNBA": "basketball", "NFL": "americanfootball",
    }
    czr_sport = sport_map.get(sport, "basketball")
    base_url = f"https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/{czr_sport}"

    # Player-prop tabs differ by sport — confirmed from real capture for MLB
    # ("SCHEDULE|Batter Props" / "SCHEDULE|Pitcher Props"). Other sports' exact tab
    # names are a best-effort guess based on the MLB pattern, not individually
    # confirmed yet.
    prop_tabs_by_sport = {
        "MLB": ["SCHEDULE%7CBatter%20Props", "SCHEDULE%7CPitcher%20Props"],
        "NBA": ["SCHEDULE%7CPlayer%20Props"],
        "WNBA": ["SCHEDULE%7CPlayer%20Props"],
        "NHL": ["SCHEDULE%7CPlayer%20Props"],
        "NFL": ["SCHEDULE%7CPlayer%20Props"],
    }
    tabs_to_try = prop_tabs_by_sport.get(sport, ["SCHEDULE%7CPlayer%20Props"])

    try:
        # Step 1: Get competitions (league IDs)
        r1 = session.get(f"{base_url}/competitions", headers=headers, timeout=15)
        if r1.status_code == 401:
            # JWT expired — launch the Playwright harvester to refresh it, then
            # retry once.  harvest_caesars_tokens() also persists the new token
            # to the Gist and local cache so future calls don't need Playwright.
            fresh = harvest_caesars_tokens()
            if fresh.get("bearer_jwt"):
                headers["authorization"] = f"Bearer {fresh['bearer_jwt']}"
                headers["sessionid"]     = fresh["bearer_jwt"]
                if fresh.get("waf_token"):
                    headers["x-aws-waf-token"] = fresh["waf_token"]
                r1 = session.get(f"{base_url}/competitions", headers=headers, timeout=15)
        if r1.status_code != 200:
            return []

        comps = r1.json()
        comp_list = comps if isinstance(comps, list) else comps.get("competitions", [])

        target_names = {
            "NBA": ["nba"], "MLB": ["mlb", "major league"],
            "NHL": ["nhl", "national hockey"], "WNBA": ["wnba"],
            "NFL": ["nfl", "national football"],
        }
        targets = target_names.get(sport, ["nba"])
        comp_id = None
        for comp in comp_list:
            cname = (comp.get("name", "") or "").lower()
            cid = comp.get("id", "")
            if any(t in cname for t in targets):
                comp_id = cid
                break
        if not comp_id and comp_list:
            comp_id = comp_list[0].get("id", "")
        if not comp_id:
            return []

        # Step 2: Get player props for this competition — try each known tab
        for tab in tabs_to_try:
            r2 = session.get(
                f"{base_url}/competitions/{comp_id}/tabs/{tab}",
                headers=headers, timeout=15
            )
            if r2.status_code != 200:
                continue

            data = r2.json()
            for comp_block in data.get("competitions", []):
                for event in comp_block.get("events", []):
                    for group in event.get("keyMarketGroups", []):
                        for market in group.get("markets", []):
                            meta = market.get("metadata", {}) or {}
                            player = meta.get("player", "")
                            mkt_name = (market.get("name", "") or "").strip("|")
                            if not player:
                                continue

                            for sel in market.get("selections", []):
                                sel_name = (sel.get("name", "") or "").strip("|")
                                sel_type = sel.get("type", "")
                                price = sel.get("price", {}) or {}
                                odds_a = price.get("a")
                                if odds_a is None:
                                    continue

                                line, side = None, "OVER"
                                m_count = re.match(r"^(\d+)\+$", sel_name)
                                m_overunder = re.match(r"^(Over|Under)\s+([\d.]+)$", sel_name, re.I)
                                if m_count:
                                    line = float(m_count.group(1)) - 0.5
                                    side = "OVER"
                                elif m_overunder:
                                    side = m_overunder.group(1).upper()
                                    line = float(m_overunder.group(2))
                                elif sel_type.lower() in ("over", "under"):
                                    side = sel_type.upper()
                                    # Fall back to a points/handicap field if present,
                                    # since not every market uses the count-string format.
                                    line = sel.get("points") or sel.get("handicap") or sel.get("line")

                                if line is None:
                                    continue

                                odds_str = f"{'+' if odds_a > 0 else ''}{int(odds_a)}"
                                props.append({
                                    "Player": player, "Prop": mkt_name,
                                    "Line": float(line), "Side": side,
                                    "OverOdds": odds_str if side == "OVER" else "—",
                                    "UnderOdds": odds_str if side == "UNDER" else "—",
                                    "Book": "Caesars", "Sport": sport,
                                    "source": "caesars_direct",
                                })
            time.sleep(0.2)

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except Exception as _e:
        print(f"[WARN] fetch_caesars_direct: {_e}")

    return props

def fetch_betrivers_direct(sport):
    """Fetch BetRivers props — Kambi backend, no auth needed."""
    try:
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://az.betrivers.com",
        "Referer": "https://az.betrivers.com/",
    }
    props = []

    cache_path = os.path.join(CACHE_DIR, f"betrivers_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            return _safe_load_pkl(cache_path)

    # Step 1: Get event list from Kambi
    sport_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "ice_hockey/nhl",
                 "WNBA": "basketball/wnba", "NFL": "american_football/nfl"}
    kambi_sport = sport_map.get(sport, "basketball/nba")

    try:
        r1 = session.get(
            f"https://eu-offering-api.kambicdn.com/offering/v2/rvn/listView/{kambi_sport}/all/all.json",
            params={"lang": "en_US", "market": "US-AZ", "useCombined": "true"},
            headers=headers, timeout=15
        )
        if r1.status_code != 200:
            return []

        events = r1.json().get("events", [])

        # Step 2: For each event, get player props
        for ev in events[:10]:
            ev_id = ev.get("event", {}).get("id")
            if not ev_id:
                continue

            r2 = session.get(
                f"https://az.betrivers.com/api/service/sportsbook/offering/playerprops",
                params={"groupId": ev_id, "pageNr": 1, "pageSize": 100, "cageCode": 602},
                headers=headers, timeout=10
            )
            if r2.status_code != 200:
                continue

            data = r2.json()
            items = data.get("items", data.get("offerings", []))
            if isinstance(items, dict):
                items = list(items.values())

            for item in items:
                # Kambi structure: criterion.label has prop name
                criterion = item.get("criterion", {})
                prop_label = criterion.get("label", "")

                for outcome in item.get("outcomes", []):
                    player = outcome.get("participantName", "") or outcome.get("label", "")
                    odds_am = outcome.get("americanOdds") or outcome.get("oddsAmerican")
                    line = outcome.get("line") or outcome.get("handicap") or outcome.get("overUnder")

                    # Parse Over/Under
                    side = "OVER"
                    otype = (outcome.get("type", "") or outcome.get("outcomeType", "")).upper()
                    if "UNDER" in otype or "Under" in str(outcome.get("label", "")):
                        side = "UNDER"

                    if not player or line is None:
                        continue

                    try:
                        line_f = float(str(line).replace("+", ""))
                    except (ValueError, TypeError):
                        continue

                    odds_str = "—"
                    if odds_am is not None:
                        odds_str = f"{'+' if float(odds_am) > 0 else ''}{int(float(odds_am))}"

                    props.append({
                        "Player": player, "Prop": prop_label,
                        "Line": line_f, "Side": side,
                        "OverOdds": odds_str if side == "OVER" else "—",
                        "UnderOdds": odds_str if side == "UNDER" else "—",
                        "Book": "BetRivers", "Sport": sport,
                        "source": "betrivers_direct",
                    })

            time.sleep(0.3)

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except (IOError, ValueError) as _e:
            print(f"[WARN] {_e}")

    return props


def fetch_novig_lines(sport):
    """Fetch no-vig reference lines for devig and sharp-line comparison.

    Primary source: SBR consensus (no API key required).
    Fallback: OddsAPI bookmaker key "us_ex" (NoVig) when ODDS_API_KEY is set
    and api_budget_check("ODDS_API") passes.

    Returns list of dicts with keys: Matchup, HomeML, AwayML, Spread,
    Total, Book, Sport, source.
    """
    # ── SBR primary (no API key required) ──
    sbr_games, _, _ = _sbr_fetch_games(sport)
    if sbr_games:
        return [
            {
                "Matchup": g["Matchup"],
                "HomeML":  g.get("Home ML", "N/A"),
                "AwayML":  g.get("Away ML", "N/A"),
                "Spread":  g.get("Spread", "N/A"),
                "Total":   g.get("Total", "N/A"),
                "Book":    "SBR-Consensus",
                "Sport":   sport,
                "source":  "sbr_scrape",
            }
            for g in sbr_games
        ]

    # ── OddsAPI/NoVig fallback ──
    if not ODDS_API_KEY:
        return []
    try:
        _ok, _ = api_budget_check("ODDS_API")
        if not _ok:
            return []
    except Exception:
        pass

    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return []

    cache_path = os.path.join(CACHE_DIR, f"novig_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 30:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached
    url = (
        f"{ODDS_API_BASE}/sports/{sport_key}/odds"
        f"?apiKey={ODDS_API_KEY}"
        f"&regions=us"
        f"&markets=h2h,spreads,totals"
        f"&oddsFormat=american"
        f"&bookmakers=us_ex"
    )
    line_dicts = []
    try:
        resp = _http.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API", amount=30)  # 10 x 3 markets x 1 region — was never tracked before
        if resp.status_code == 401:
            st.warning(
                "⚠️ NoVig (Odds API): invalid API key — "
                "update the ODDS_API_KEY secret."
            )
            return []
        if resp.status_code == 422:
            st.warning(
                f"⚠️ NoVig (Odds API): sport key ‘{sport_key}’ "
                "not accepted — NoVig may not carry this sport."
            )
            return []
        if resp.status_code != 200:
            st.warning(
                f"⚠️ NoVig (Odds API): HTTP {resp.status_code} — "
                "rate-limited or service unavailable. Try again shortly."
            )
            return []

        events = resp.json()
        if not isinstance(events, list):
            st.warning("⚠️ NoVig (Odds API): unexpected response format.")
            return []

        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            matchup = f"{away} @ {home}"
            home_ml = away_ml = spread = total = "N/A"

            for bm in event.get("bookmakers", []):
                if bm.get("key") != "us_ex":
                    continue
                for mkt in bm.get("markets", []):
                    mkey = mkt.get("key", "")
                    outcomes = mkt.get("outcomes", [])
                    if mkey == "h2h":
                        for o in outcomes:
                            if o.get("name") == home:
                                home_ml = o.get("price", "N/A")
                            elif o.get("name") == away:
                                away_ml = o.get("price", "N/A")
                    elif mkey == "spreads":
                        for o in outcomes:
                            if o.get("name") == home:
                                pt = o.get("point")
                                spread = f"{home} {pt:+.1f}" if pt is not None else "N/A"
                    elif mkey == "totals":
                        for o in outcomes:
                            if o.get("name") == "Over":
                                total = o.get("point", "N/A")
                break  # only one us_ex entry per event

            line_dicts.append({
                "Matchup": matchup,
                "HomeML":  home_ml,
                "AwayML":  away_ml,
                "Spread":  spread,
                "Total":   total,
                "Book":    "NoVig",
                "Sport":   sport,
                "source":  "novig_odds_api",
            })

        if line_dicts:
            with open(cache_path, "wb") as _f:
                pickle.dump(line_dicts, _f)

    except Exception as _e:
        st.warning(
            f"⚠️ NoVig: failed to fetch lines ({type(_e).__name__}: {_e}). "
            "Check network or Odds API status."
        )
        return []

    return line_dicts


def fetch_superbook_direct(sport):
    """
    Fetch Superbook props via their public API.
    Superbook carries strong sharp signal weight (Circa Sports ownership group).
    Used as additional devig source alongside Pinnacle/Circa.
    """
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        print("[WARN] Superbook: curl_cffi not installed — skipping")
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://co.superbook.com",
        "Referer": "https://co.superbook.com/sports",
    }
    props = []

    cache_path = os.path.join(CACHE_DIR, f"superbook_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            try:
                cached = _safe_load_pkl(cache_path)
                if cached:
                    return cached
            except Exception:
                pass

    sport_map = {
        "NBA": "basketball/nba", "MLB": "baseball/mlb",
        "NHL": "ice-hockey/nhl", "NFL": "american-football/nfl",
        "WNBA": "basketball/wnba",
    }
    sb_sport = sport_map.get(sport)
    if not sb_sport:
        return []

    try:
        # Superbook uses Kambi backend (same as BetRivers)
        # Offering endpoint returns all available markets
        kambi_url = (
            f"https://eu-offering-api.kambicdn.com/offering/v2018/superbook"
            f"/listView/{sb_sport}.json"
            f"?lang=en_US&market=US&client_id=2&channel_id=1"
            f"&ncids=1&category=player-props&useCombined=true"
        )
        r = session.get(kambi_url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []

        data = r.json()
        events = data.get("events", [])

        for event in events:
            ev_info = event.get("event", {})
            for betOffer in event.get("betOffers", []):
                if not betOffer.get("open", True):
                    continue
                market_name = betOffer.get("criterion", {}).get("label", "")
                for outcome in betOffer.get("outcomes", []):
                    if outcome.get("status") != "OPEN":
                        continue
                    label = outcome.get("label", "")
                    participant = outcome.get("participant", label)
                    odds_eu = outcome.get("odds", 0)  # European format *1000
                    odds_dec = odds_eu / 1000  # Kambi always returns integer milliunits (e.g. 1909 = 1.909x)
                    line = outcome.get("line")
                    if line is not None:
                        line = line / 1000  # Kambi stores lines *1000

                    # Parse Over/Under
                    side = "OVER"
                    player = participant
                    if " Over " in label:
                        side = "OVER"
                        player = label.split(" Over ")[0].strip()
                    elif " Under " in label:
                        side = "UNDER"
                        player = label.split(" Under ")[0].strip()
                    elif label.startswith("Over"):
                        side = "OVER"
                    elif label.startswith("Under"):
                        side = "UNDER"

                    if not player or line is None:
                        continue

                    # Convert decimal odds to American
                    try:
                        d = float(odds_dec)
                        if d >= 2.0:
                            odds_am = f"+{int((d - 1) * 100)}"
                        else:
                            odds_am = f"{int(-100 / (d - 1))}"
                    except (ValueError, ZeroDivisionError):
                        odds_am = "—"

                    try:
                        props.append({
                            "Player": player.strip(),
                            "Prop": market_name,
                            "Line": float(line),
                            "Side": side,
                            "OverOdds": odds_am if side == "OVER" else "—",
                            "UnderOdds": odds_am if side == "UNDER" else "—",
                            "Book": "Superbook",
                            "Sport": sport,
                            "source": "superbook_direct",
                        })
                    except (ValueError, TypeError):
                        continue

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except Exception as _e:
        print(f"[WARN] Superbook: {type(_e).__name__}: {_e}")

    return props

# Alias so callers can use either name
fetch_superbook_lines = fetch_superbook_direct


# ─────────────────────────────────────────────────────────────────────────────
# KAMBI GAME LINES — BetRivers / Fanatics / ESPN Bet
#
# All three books use the Kambi sportsbook backend (eu-offering-api.kambicdn.com).
# Offering IDs:
#   BetRivers → "rvn"     (Rush Street Gaming / SugarHouse; confirmed by the
#                            existing fetch_betrivers_direct which uses same URL)
#   Fanatics  → "ftn"     (Fanatics Sportsbook via Kambi; best-effort — degrades
#                            silently to [] if offering ID is wrong)
#   ESPN Bet  → "espnbet" (Penn Entertainment ESPN Bet brand on Kambi)
#
# curl_cffi TLS impersonation bypasses Kambi's IP-level 429 rate-limiting that
# blocks plain urllib/requests from datacenter IPs — same pattern as
# fetch_superbook_direct and fetch_betrivers_direct.
#
# Kambi line encoding: all numeric values are integers x 1000.
#   odds=1909   → decimal 1.909 → American ≈ -110
#   line=-5500  → spread -5.5
#   line=215500 → total  215.5
# ─────────────────────────────────────────────────────────────────────────────

def _kambi_dec_to_am(odds_int: int) -> str:
    """Convert Kambi integer odds (e.g. 1909) to American odds string (+110/-110)."""
    try:
        d = odds_int / 1000.0
        if d >= 2.0:
            return f"+{int(round((d - 1) * 100))}"
        elif d > 1.0:
            return f"{int(round(-100 / (d - 1)))}"
        return "N/A"
    except (TypeError, ZeroDivisionError, ValueError):
        return "N/A"


def _fetch_kambi_game_lines(offering_id: str, sport: str, book_label: str) -> list:
    """
    Core Kambi game-lines fetcher shared by BetRivers / Fanatics / ESPN Bet.

    Queries eu-offering-api.kambicdn.com with category=match (game lines only;
    no player props), parses spread / total / moneyline markets, returns the
    standard BetCouncil game-lines list.

    Returns list of dicts:
        {Matchup, Home, Away, HomeML, AwayML, Spread, SpreadOdds,
         Total, OverOdds, UnderOdds, Book, Sport, source}
    """
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    sport_map = {
        "NBA":  "basketball/nba",
        "MLB":  "baseball/mlb",
        "NHL":  "ice-hockey/nhl",
        "NFL":  "american-football/nfl",
        "WNBA": "basketball/wnba",
        "Soccer": "football",
    }
    kambi_sport = sport_map.get(sport)
    if not kambi_sport:
        return []

    cache_path = os.path.join(CACHE_DIR, f"kambi_{offering_id}_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    url = (
        f"https://eu-offering-api.kambicdn.com/offering/v2018/{offering_id}"
        f"/listView/{kambi_sport}.json"
        f"?lang=en_US&market=US&client_id=2&channel_id=1&ncids=1"
        f"&category=match&useCombined=true"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://sportsbook.draftkings.com",
        "Referer": "https://sportsbook.draftkings.com/sports",
    }

    games = []
    try:
        r = session.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        events = data.get("events", [])

        for ev_wrap in events:
            ev = ev_wrap.get("event", {})
            home_name = ev.get("homeName", "") or ev.get("home", "")
            away_name = ev.get("awayName", "") or ev.get("away", "")
            if not home_name or not away_name:
                ev_name = ev.get("englishName") or ev.get("name", "")
                for sep in (" @ ", " vs ", " v ", " - "):
                    if sep in ev_name:
                        parts = ev_name.split(sep, 1)
                        away_name, home_name = parts[0].strip(), parts[1].strip()
                        break
            if not home_name or not away_name:
                continue

            matchup  = f"{away_name} @ {home_name}"
            home_ml  = away_ml = "N/A"
            spread   = spread_odds = "N/A"
            total    = over_odds = under_odds = "N/A"

            for offer in ev_wrap.get("betOffers", []):
                if not offer.get("open", True):
                    continue
                criterion = offer.get("criterion", {})
                label     = (criterion.get("englishLabel") or criterion.get("label") or "").lower()
                outcomes  = offer.get("outcomes", [])

                # Money Line
                if any(x in label for x in ("money line", "moneyline", "match result", "match winner")):
                    for o in outcomes:
                        otype   = (o.get("type") or "").upper()
                        o_label = (o.get("englishLabel") or o.get("label") or "").lower()
                        am      = _kambi_dec_to_am(o.get("odds", 0))
                        if otype == "OT_2" or home_name.lower() in o_label:
                            home_ml = am
                        elif otype == "OT_1" or away_name.lower() in o_label:
                            away_ml = am
                        elif home_ml == "N/A":
                            home_ml = am
                        else:
                            away_ml = am

                # Handicap / Spread
                elif any(x in label for x in ("handicap", "point spread", "spread")):
                    for o in outcomes:
                        if o.get("line") is None:
                            continue
                        line_val = o["line"] / 1000.0
                        am       = _kambi_dec_to_am(o.get("odds", 0))
                        otype    = (o.get("type") or "").upper()
                        if otype == "OT_1" or away_name.lower() in (o.get("label","")).lower():
                            spread       = f"{away_name} {line_val:+.1f}"
                            spread_odds  = am
                        elif spread == "N/A":
                            spread       = f"{away_name} {line_val:+.1f}"
                            spread_odds  = am

                # Over/Under / Total
                elif any(x in label for x in ("over/under", "total", "goals")):
                    for o in outcomes:
                        if o.get("line") is None:
                            continue
                        line_val = o["line"] / 1000.0
                        am       = _kambi_dec_to_am(o.get("odds", 0))
                        otype    = (o.get("type") or "").upper()
                        if "OVER" in otype:
                            total      = str(line_val)
                            over_odds  = am
                        elif "UNDER" in otype:
                            under_odds = am
                        elif total == "N/A":
                            total      = str(line_val)

            if home_ml == "N/A" and spread == "N/A" and total == "N/A":
                continue

            games.append({
                "Matchup":    matchup,
                "Home":       home_name,
                "Away":       away_name,
                "HomeML":     home_ml,
                "AwayML":     away_ml,
                "Spread":     spread,
                "SpreadOdds": spread_odds,
                "Total":      total,
                "OverOdds":   over_odds,
                "UnderOdds":  under_odds,
                "Book":       book_label,
                "Sport":      sport,
                "source":     f"kambi_{offering_id}",
            })

    except Exception as _e:
        print(f"[WARN] Kambi {book_label}: {type(_e).__name__}: {_e}")

    if games:
        _safe_save_pkl(cache_path, games)
    return games


def fetch_betrivers_game_lines(sport: str) -> list:
    """
    BetRivers game lines via Kambi backend (offering_id='rvn').

    Rush Street Gaming / BetRivers is a confirmed Kambi operator; the same
    offering_id is used by the existing fetch_betrivers_direct for player props.
    Returns {Matchup, Home, Away, HomeML, AwayML, Spread, Total,
             Book: 'BetRivers', Sport, source} per game.  Cached 60 min.
    """
    return _fetch_kambi_game_lines("rvn", sport, "BetRivers")


def _savant_parse_csv(text):
    """Parse Savant CSV text → list[dict].  Handles the 'last, first' header."""
    if not text or not text.strip():
        return []
    rows = []
    lines = [l.rstrip("\r") for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return []
    # Savant CSV is well-formed; split on comma respecting quoted fields
    def _split(line):
        fields, cur, in_q = [], [], False
        for ch in line:
            if ch == '"': in_q = not in_q
            elif ch == ',' and not in_q: fields.append("".join(cur)); cur = []
            else: cur.append(ch)
        fields.append("".join(cur))
        return [f.strip('"').strip() for f in fields]

    headers = _split(lines[0])
    for line in lines[1:]:
        vals = _split(line)
        if len(vals) == len(headers):
            rows.append(dict(zip(headers, vals)))
    return rows


def _savant_name_key(row):
    """Return lowercase 'first last' from a Savant row (handles last, first format)."""
    raw = row.get("last_name, first_name") or row.get("name") or row.get("player_name") or ""
    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        return f"{parts[1]} {parts[0]}".lower().strip()
    n = row.get("first_name", ""); s = row.get("last_name", "")
    if n and s:
        return f"{n} {s}".lower().strip()
    return raw.lower().strip()


def fetch_savant_statcast(season=None):
    """
    Baseball Savant xStats leaderboard — completely free, no auth.
    Returns dict: lowercase_name → {xba, xslg, xwoba, xobp, xiso,
      exit_velocity_avg, launch_angle_avg, barrel_batted_rate,
      hard_hit_percent, strikeout_percent, walk_percent, sweet_spot_percent,
      player_id}
    Cached 2 hours.
    """
    if season is None:
        season = _current_mlb_season_year()
    cache_path = os.path.join(CACHE_DIR, f"savant_xstats_{season}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 2:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached

    url = (
        f"https://baseballsavant.mlb.com/leaderboard/custom"
        f"?year={season}&type=batter&filter=&sort=xwoba&sortDir=desc&min=q"
        f"&selections=xba,xslg,xwoba,xobp,xiso,exit_velocity_avg,launch_angle_avg"
        f",barrel_batted_rate,hard_hit_percent,strikeout_percent,walk_percent"
        f",sweet_spot_percent&csv=true"
    )
    try:
        r = _http.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200: return {}
        rows = _savant_parse_csv(r.text)
        lookup = {}
        for row in rows:
            key = _savant_name_key(row)
            if not key: continue
            def _f(k): 
                v = row.get(k, "")
                try: return float(v) if v not in ("", "null", "None") else None
                except: return None
            lookup[key] = {
                "player_id":          row.get("player_id", ""),
                "xba":                _f("xba"),
                "xslg":               _f("xslg"),
                "xwoba":              _f("xwoba"),
                "xobp":               _f("xobp"),
                "xiso":               _f("xiso"),
                "exit_velocity_avg":  _f("exit_velocity_avg"),
                "launch_angle_avg":   _f("launch_angle_avg"),
                "barrel_batted_rate": _f("barrel_batted_rate"),
                "hard_hit_percent":   _f("hard_hit_percent"),
                "strikeout_percent":  _f("strikeout_percent"),
                "walk_percent":       _f("walk_percent"),
                "sweet_spot_percent": _f("sweet_spot_percent"),
            }
        if lookup: _safe_save_pkl(cache_path, lookup)
        return lookup
    except Exception as _e:
        print(f"[WARN] fetch_savant_statcast: {_e}")
        return _safe_load_pkl(cache_path) or {}


def fetch_savant_sprint_speed(season=None):
    """
    Baseball Savant sprint speed leaderboard — free, no auth.
    Returns dict: lowercase_name → {sprint_speed, bolts, hp_to_1b, team, position}
    sprint_speed in ft/s; bolts = 30+ ft/s sprints; hp_to_1b in seconds.
    Cached 2 hours.
    """
    if season is None:
        season = _current_mlb_season_year()
    cache_path = os.path.join(CACHE_DIR, f"savant_sprint_{season}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 2:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    url = f"https://baseballsavant.mlb.com/sprint_speed_leaderboard?year={season}&position=&team=&min=10&csv=true"
    try:
        r = _http.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200: return {}
        rows = _savant_parse_csv(r.text)
        lookup = {}
        for row in rows:
            # Sprint speed CSV uses "last_name, first_name" column
            key = _savant_name_key(row)
            if not key: continue
            def _f(k):
                v = row.get(k, "")
                try: return float(v) if v not in ("", "null") else None
                except: return None
            lookup[key] = {
                "sprint_speed": _f("sprint_speed"),
                "bolts":        _f("bolts"),
                "hp_to_1b":     _f("hp_to_1b"),
                "team":         row.get("team", ""),
                "position":     row.get("position", ""),
                "player_id":    row.get("player_id", ""),
            }
        if lookup: _safe_save_pkl(cache_path, lookup)
        return lookup
    except Exception as _e:
        print(f"[WARN] fetch_savant_sprint_speed: {_e}")
        return _safe_load_pkl(cache_path) or {}


def fetch_savant_expected_stats(season=None):
    """
    Baseball Savant expected stats (xBA, xSLG, xwOBA) vs actual — catches
    overperformers (due for regression) and underperformers (breakout candidates).
    Returns dict: lowercase_name → {ba, xba, xba_diff, slg, xslg, xslg_diff,
                                     woba, xwoba, xwoba_diff, pa}
    Cached 2 hours.
    """
    if season is None:
        season = _current_mlb_season_year()
    cache_path = os.path.join(CACHE_DIR, f"savant_expected_{season}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 2:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    url = f"https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=batter&year={season}&position=&team=&min=q&csv=true"
    try:
        r = _http.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200: return {}
        rows = _savant_parse_csv(r.text)
        lookup = {}
        for row in rows:
            key = _savant_name_key(row)
            if not key: continue
            def _f(k):
                v = row.get(k, "")
                try: return float(v) if v not in ("", "null") else None
                except: return None
            lookup[key] = {
                "pa":         _f("pa"),
                "ba":         _f("ba"),
                "xba":        _f("est_ba"),
                "xba_diff":   _f("est_ba_minus_ba_diff"),
                "slg":        _f("slg"),
                "xslg":       _f("est_slg"),
                "xslg_diff":  _f("est_slg_minus_slg_diff"),
                "woba":       _f("woba"),
                "xwoba":      _f("est_woba"),
                "xwoba_diff": _f("est_woba_minus_woba_diff"),
            }
        if lookup: _safe_save_pkl(cache_path, lookup)
        return lookup
    except Exception as _e:
        print(f"[WARN] fetch_savant_expected_stats: {_e}")
        return _safe_load_pkl(cache_path) or {}


def fetch_savant_pitch_arsenal(season=None):
    """
    Baseball Savant pitch arsenal — run value per 100 pitches by type,
    per pitcher.  Negative run value = good for pitcher (run-saving pitch).
    Returns dict: lowercase_pitcher_name → {FF, SL, CH, CU, SI, FC, ...}
      each value = run_value_per_100 for that pitch type.
    Cached 2 hours.
    """
    if season is None:
        season = _current_mlb_season_year()
    cache_path = os.path.join(CACHE_DIR, f"savant_arsenal_{season}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 2:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    url = f"https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats?type=pitcher&pitchType=&year={season}&team=&min=10&csv=true"
    try:
        r = _http.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200: return {}
        rows = _savant_parse_csv(r.text)
        # Group rows by pitcher (one row per pitch type)
        from collections import defaultdict
        pitcher_map = defaultdict(dict)
        for row in rows:
            key = _savant_name_key(row)
            if not key: continue
            pitch_type = row.get("pitch_type", "UNK")
            rv_raw = row.get("run_value_per_100", "")
            try: rv = float(rv_raw)
            except: rv = None
            pitch_pct_raw = row.get("pitch_usage", row.get("pitch_percent", ""))
            try: pitch_pct = float(pitch_pct_raw)
            except: pitch_pct = None
            if rv is not None:
                pitcher_map[key][pitch_type] = {"rv_per_100": rv, "usage_pct": pitch_pct}
        result = dict(pitcher_map)
        if result: _safe_save_pkl(cache_path, result)
        return result
    except Exception as _e:
        print(f"[WARN] fetch_savant_pitch_arsenal: {_e}")
        return _safe_load_pkl(cache_path) or {}


def fetch_savant_batted_ball(season=None):
    """
    Baseball Savant batted-ball profile per batter —
    GB%, FB%, LD%, PU%, pull/straight/oppo rates.
    Returns dict: lowercase_name → {gb_rate, fb_rate, ld_rate, pu_rate,
                                     pull_rate, oppo_rate, sweet_spot_rate}
    Cached 2 hours.
    """
    if season is None:
        season = _current_mlb_season_year()
    cache_path = os.path.join(CACHE_DIR, f"savant_batted_{season}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 2:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached
    url = f"https://baseballsavant.mlb.com/leaderboard/batted-ball?year={season}&csv=true"
    try:
        r = _http.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200: return {}
        rows = _savant_parse_csv(r.text)
        lookup = {}
        for row in rows:
            # Batted ball uses "id" + "name" columns
            raw_name = row.get("name", "")
            key = raw_name.lower().strip() if raw_name else _savant_name_key(row)
            if not key: continue
            def _f(k):
                v = row.get(k, "")
                try: return float(v) if v not in ("", "null") else None
                except: return None
            lookup[key] = {
                "bbe":         _f("bbe"),
                "gb_rate":     _f("gb_rate"),
                "fb_rate":     _f("fb_rate"),
                "ld_rate":     _f("ld_rate"),
                "pu_rate":     _f("pu_rate"),
                "pull_rate":   _f("pull_rate"),
                "oppo_rate":   _f("oppo_rate"),
                "player_id":   row.get("id", ""),
            }
        if lookup: _safe_save_pkl(cache_path, lookup)
        return lookup
    except Exception as _e:
        print(f"[WARN] fetch_savant_batted_ball: {_e}")
        return _safe_load_pkl(cache_path) or {}


# ─────────────────────────────────────────────────────────────────────────────
# OPENMETEO WEATHER — Free JSON API, no key, any lat/lng, hourly precision.
# Wind speed + direction at game time is the top external factor for MLB HR props.
# Dome/retractable parks are excluded — weather doesn't affect indoor games.
# ─────────────────────────────────────────────────────────────────────────────

_MLB_STADIUM_COORDS = {
    # team_abbrev: (latitude, longitude, iana_timezone)
    "ARI": (33.4455, -112.0667, "America/Phoenix"),
    "ATL": (33.7554, -84.3900,  "America/New_York"),
    "BAL": (39.2839, -76.6218,  "America/New_York"),
    "BOS": (42.3467, -71.0972,  "America/New_York"),
    "CHC": (41.9484, -87.6553,  "America/Chicago"),
    "CWS": (41.8300, -87.6338,  "America/Chicago"),
    "CIN": (39.0974, -84.5082,  "America/New_York"),
    "CLE": (41.4962, -81.6852,  "America/New_York"),
    "COL": (39.7559, -104.9942, "America/Denver"),
    "DET": (42.3390, -83.0485,  "America/New_York"),
    "KC":  (39.0517, -94.4803,  "America/Chicago"),
    "LAA": (33.8003, -117.8827, "America/Los_Angeles"),
    "LAD": (34.0739, -118.2400, "America/Los_Angeles"),
    "MIN": (44.9817, -93.2776,  "America/Chicago"),
    "NYM": (40.7571, -73.8458,  "America/New_York"),
    "NYY": (40.8296, -73.9262,  "America/New_York"),
    "ATH": (37.7516, -122.2007, "America/Los_Angeles"),
    "PHI": (39.9057, -75.1665,  "America/New_York"),
    "PIT": (40.4469, -80.0057,  "America/New_York"),
    "SD":  (32.7076, -117.1570, "America/Los_Angeles"),
    "SF":  (37.7786, -122.3893, "America/Los_Angeles"),
    "STL": (38.6226, -90.1928,  "America/Chicago"),
    "WSH": (38.8730, -77.0074,  "America/New_York"),
}
# Dome / full retractable-roof parks — weather irrelevant regardless of setting
_MLB_DOME_PARKS = {"HOU", "MIA", "MIL", "SEA", "TEX", "TOR", "TB"}


def fetch_openmeteo_weather(date=None):
    """
    Fetch hourly wind/temp forecasts for all MLB outdoor stadiums via OpenMeteo.
    OpenMeteo is completely free — no API key, no account needed.

    Returns dict: team_abbrev → {
        wind_speed_mph: float,     # at game time (7pm local default)
        wind_dir_deg: int,         # 0=N 90=E 180=S 270=W
        wind_cardinal: str,        # 'N','NE','E','SE','S','SW','W','NW'
        temp_f: float,
        precip_pct: int,           # precipitation probability 0-100
        is_dome: bool,
    }
    Dome parks always return is_dome=True with null weather values.
    Cached 30 minutes.
    """
    from datetime import date as _date, datetime as _dt
    today = (date or _date.today()).strftime("%Y-%m-%d") if not isinstance(date, str) else date
    cache_path = os.path.join(CACHE_DIR, f"openmeteo_{today}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached

    def _deg_to_cardinal(deg):
        if deg is None: return "—"
        dirs = ["N","NE","E","SE","S","SW","W","NW"]
        return dirs[round(deg / 45) % 8]

    result = {}
    # Add dome parks first
    for abbr in _MLB_DOME_PARKS:
        result[abbr] = {"is_dome": True, "wind_speed_mph": None, "wind_dir_deg": None,
                        "wind_cardinal": "—", "temp_f": None, "precip_pct": None}

    def _fetch_one_stadium(abbr, lat, lon, tz):
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&hourly=wind_speed_10m,wind_direction_10m,temperature_2m,precipitation_probability"
                f"&wind_speed_unit=mph&temperature_unit=fahrenheit"
                f"&timezone={tz.replace('/', '%2F')}&forecast_days=1"
            )
            # Plain one-shot request, not the shared retry session -- avoids
            # the same compounding-timeout risk already found and fixed for
            # RotoWire this session (a retry session's Retry(total=N) also
            # retries on read timeouts, not just error codes, so a slow
            # response can multiply a short per-attempt timeout well past
            # what it looks like on paper).
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                return abbr, {"is_dome": False, "error": r.status_code}
            data = r.json()
            hourly = data.get("hourly", {})
            times  = hourly.get("time", [])
            winds  = hourly.get("wind_speed_10m", [])
            dirs   = hourly.get("wind_direction_10m", [])
            temps  = hourly.get("temperature_2m", [])
            precip = hourly.get("precipitation_probability", [])
            game_hr = next(
                (i for i, t in enumerate(times) if t.endswith("T19:00") or t.endswith("T18:00")),
                next((i for i, t in enumerate(times) if t.endswith("T13:00")), 12)
            )
            def _get(lst, idx):
                try: return lst[idx]
                except: return None
            spd = _get(winds, game_hr)
            deg = _get(dirs,  game_hr)
            return abbr, {
                "is_dome":        False,
                "wind_speed_mph": round(spd, 1) if spd is not None else None,
                "wind_dir_deg":   int(deg) if deg is not None else None,
                "wind_cardinal":  _deg_to_cardinal(deg),
                "temp_f":         round(_get(temps,  game_hr), 1) if _get(temps, game_hr) is not None else None,
                "precip_pct":     int(_get(precip, game_hr)) if _get(precip, game_hr) is not None else None,
            }
        except Exception as _we:
            return abbr, {"is_dome": False, "error": str(_we)[:50]}

    from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait
    stadiums = list(_MLB_STADIUM_COORDS.items())
    if stadiums:
        ex = ThreadPoolExecutor(max_workers=min(len(stadiums), 20))
        futures = {ex.submit(_fetch_one_stadium, abbr, lat, lon, tz): abbr for abbr, (lat, lon, tz) in stadiums}
        done, not_done = _cf_wait(futures.keys(), timeout=20)
        for fut in done:
            try:
                abbr, info = fut.result()
                result[abbr] = info
            except Exception:
                pass
        ex.shutdown(wait=False)

    if result: _safe_save_pkl(cache_path, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MLB.com OFFICIAL LINEUPS — Confirmed batting orders + probable pitchers +
# home-plate umpire assignments from MLB Stats API (completely free, no auth).
# Lineups confirmed ~3-4 hours before game time.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_mlb_lineups(date=None):
    """
    Fetch confirmed batting orders, probable pitchers, and home-plate umpire
    from MLB Stats API (statsapi.mlb.com).  Completely free, no auth required.

    Returns dict: '{away_abbr}@{home_abbr}' → {
        home_team, away_team, home_abbr, away_abbr,
        home_lineup: [list of batter names in order],
        away_lineup: [...],
        home_pitcher: str, home_pitcher_hand: str,
        away_pitcher: str, away_pitcher_hand: str,
        hp_umpire: str,     # home plate umpire name
        game_time: str,     # ISO format
        venue: str,
        game_pk: int,
    }
    Cached 30 minutes.
    """
    from datetime import date as _date
    today = (date or _date.today()).strftime("%Y-%m-%d") if not isinstance(date, str) else date
    cache_path = os.path.join(CACHE_DIR, f"mlb_lineups_{today}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached

    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={today}"
        f"&hydrate=lineups,probablePitcher(note),officials,teams,venue"
    )
    result = {}
    try:
        r = _http.get(url, headers={"User-Agent": HEADERS.get("User-Agent", "")}, timeout=15)
        if r.status_code != 200: return {}
        data = r.json()
        for date_block in data.get("dates", []):
            for game in date_block.get("games", []):
                try:
                    gid    = game.get("gamePk", 0)
                    teams  = game.get("teams", {})
                    home   = teams.get("home", {}).get("team", {})
                    away   = teams.get("away", {}).get("team", {})
                    home_n = home.get("name", "")
                    away_n = away.get("name", "")
                    home_a = home.get("abbreviation", home_n[:3].upper())
                    away_a = away.get("abbreviation", away_n[:3].upper())
                    key = f"{away_a}@{home_a}"

                    # Batting lineups
                    lineups = game.get("lineups", {})
                    def _extract_lineup(side):
                        players = lineups.get(side, {}).get("batters", [])
                        return [p.get("fullName", "") for p in players if p.get("fullName")]
                    home_lu = _extract_lineup("homePlayers")
                    away_lu = _extract_lineup("visitingPlayers")

                    # Probable pitchers
                    def _pitcher_info(side):
                        pp = teams.get(side, {}).get("probablePitcher", {})
                        return pp.get("fullName", "TBD"), (pp.get("pitchHand", {}) or {}).get("code", "")
                    home_p, home_ph = _pitcher_info("home")
                    away_p, away_ph = _pitcher_info("away")

                    # Umpire assignments
                    hp_ump = ""
                    for official in game.get("officials", []):
                        ot = official.get("officialType", "")
                        if ot == "Home Plate":
                            hp_ump = official.get("official", {}).get("fullName", "")
                            break

                    result[key] = {
                        "game_pk":           gid,
                        "home_team":         home_n,
                        "away_team":         away_n,
                        "home_abbr":         home_a,
                        "away_abbr":         away_a,
                        "home_lineup":       home_lu,
                        "away_lineup":       away_lu,
                        "home_pitcher":      home_p,
                        "home_pitcher_hand": home_ph,
                        "away_pitcher":      away_p,
                        "away_pitcher_hand": away_ph,
                        "hp_umpire":         hp_ump,
                        "venue":             game.get("venue", {}).get("name", ""),
                        "game_time":         game.get("gameDate", ""),
                        "confirmed_lineup":  bool(home_lu or away_lu),
                    }
                except Exception: continue
    except Exception as _e:
        print(f"[WARN] fetch_mlb_lineups: {_e}")

    if result: _safe_save_pkl(cache_path, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# UMP SCORECARDS — Career HP ump tendencies (K%, BB%, run scoring).
# Source: umpscorecards.com/api/umpires (confirmed public, no auth).
# Cross-referenced with hp_umpire from fetch_mlb_lineups() for today's games.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ump_scorecards():
    """
    Fetch career home-plate umpire stats from umpscorecards.com.

    Returns dict: lowercase_ump_name → {
        n_games: int,
        accuracy_pct: float,       # called strike accuracy
        favor_home_pct: float,     # % of incorrect calls favoring home team
        k_rate_above_avg: float,   # extra Ks per 9 vs league avg (pos = more Ks)
        called_correct_pct: float,
        games: int,
    }
    Cached 6 hours (career stats don't change game-to-game).
    """
    cache_path = os.path.join(CACHE_DIR, "ump_scorecards.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached

    url = "https://umpscorecards.com/api/umpires"
    try:
        r = _http.get(url, headers={**HEADERS, "Referer": "https://umpscorecards.com/"},
                      timeout=15)
        if r.status_code != 200: return {}
        data = r.json()
        rows = data.get("rows", data) if isinstance(data, dict) else data
        lookup = {}
        for row in rows:
            name = (row.get("umpire") or "").strip()
            if not name: continue
            key = name.lower()
            n   = row.get("n", 0) or 0
            correct = row.get("called_correct_sum", 0) or 0
            total   = row.get("called_pitches_sum", 1) or 1
            x_correct = row.get("x_correct_calls_sum", correct) or correct
            lookup[key] = {
                "umpire":              name,
                "n_games":             int(n),
                "called_correct_pct":  round(correct / total * 100, 2) if total else None,
                "x_correct_calls":     x_correct,
                "accuracy_pct":        round(x_correct / total * 100, 2) if total else None,
                "raw":                 row,
            }
        if lookup: _safe_save_pkl(cache_path, lookup)
        return lookup
    except Exception as _e:
        print(f"[WARN] fetch_ump_scorecards: {_e}")
        return _safe_load_pkl(cache_path) or {}


# ─────────────────────────────────────────────────────────────────────────────
# NBA ADVANCED STATS — Via NBA.com stats API.
# Requires curl_cffi TLS impersonation + NBA-specific headers.
# Returns BPM, TS%, USG%, AST%, TOV%, DBPM, OBPM per player.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_nba_advanced_stats(season="2025-26"):
    """
    Fetch NBA advanced stats via stats.nba.com.
    Returns dict: lowercase_player_name → {ts_pct, usg_pct, ast_pct, tov_pct,
                                            bpm, obpm, dbpm, per, ws_per_48}
    curl_cffi required to bypass NBA.com bot detection.
    Cached 4 hours.
    """
    cache_path = os.path.join(CACHE_DIR, f"nba_advanced_{season.replace('-','_')}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 4:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached

    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return {}

    nba_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Connection": "keep-alive",
    }
    url = (
        "https://stats.nba.com/stats/leaguedashplayerstats"
        f"?MeasureType=Advanced&Season={season}&SeasonType=Regular+Season"
        "&PerMode=PerGame&LeagueID=00&PORound=0&Conference=&Division=&Team"
        "ID=0&PlayerExperience=&PlayerPosition=&StarterBench=&GameScope=&GameSegment=&Period=0"
        "&LastNGames=0&Month=0&OpponentTeamID=0&Location=&Outcome=&DateFrom=&DateTo=&College=&Country=&DraftPick=&DraftYear=&Height=&Weight=&ISTRound="
    )
    try:
        r = session.get(url, headers=nba_headers, timeout=20)
        if r.status_code != 200: return {}
        data = r.json()
        rs  = data.get("resultSets", [])
        if not rs: return {}
        headers = rs[0].get("headers", [])
        rows    = rs[0].get("rowSet", [])
        lookup = {}
        for row in rows:
            rec = dict(zip(headers, row))
            name = (rec.get("PLAYER_NAME") or "").lower().strip()
            if not name: continue
            def _f(k): v = rec.get(k); return float(v) if v is not None else None
            lookup[name] = {
                "player_id": rec.get("PLAYER_ID"),
                "team":      rec.get("TEAM_ABBREVIATION", ""),
                "gp":        rec.get("GP"),
                "ts_pct":    _f("TS_PCT"),
                "usg_pct":   _f("USG_PCT"),
                "ast_pct":   _f("AST_PCT"),
                "tov_pct":   _f("TOV_PCT"),
                "reb_pct":   _f("REB_PCT"),
                "pie":       _f("PIE"),
                "pace":      _f("PACE"),
                "per":       None,
            }
        if lookup: _safe_save_pkl(cache_path, lookup)
        return lookup
    except Exception as _e:
        print(f"[WARN] fetch_nba_advanced_stats: {_e}")
        return _safe_load_pkl(cache_path) or {}


# ─────────────────────────────────────────────────────────────────────────────
# ADDITIONAL KAMBI GAME LINES — Hard Rock / WynnBET / Unibet
# All use the same _fetch_kambi_game_lines() core; curl_cffi bypasses the
# 429 rate-limit that Kambi enforces against datacenter IPs.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_hardrock_game_lines(sport: str) -> list:
    """Hard Rock Bet game lines via Kambi (offering_id='hardrock'). Cached 60 min."""
    return _fetch_kambi_game_lines("hardrock", sport, "Hard Rock")


def fetch_wynnbet_game_lines(sport: str) -> list:
    """WynnBET game lines via Kambi (offering_id='wynn'). Cached 60 min."""
    return _fetch_kambi_game_lines("wynn", sport, "WynnBET")


def fetch_unibet_game_lines(sport: str) -> list:
    """Unibet game lines via Kambi (offering_id='unibet'). Cached 60 min."""
    return _fetch_kambi_game_lines("unibet", sport, "Unibet")


def fetch_betonline_offering(sport: str) -> list:
    """BetOnline game lines via offering-by-league POST API. No auth. Cached 15 min."""
    sport_map = {
        "MLB":  ("Baseball", "mlb",   "baseball"),
        "NBA":  ("Basketball","nba",  "basketball"),
        "NFL":  ("Football",  "nfl",  "football"),
        "NHL":  ("Hockey",    "nhl",  "hockey"),
        "WNBA": ("Basketball","wnba", "basketball"),
    }
    if sport not in sport_map: return []
    sport_display, league_slug, sport_slug = sport_map[sport]
    cache_path = os.path.join(CACHE_DIR, f"betonline_offering_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 15:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        payload = json.dumps({
            "Sport": sport_display, "League": league_slug,
            "ScheduleText": None, "filterTime": 0,
            "type": "prematch", "league": league_slug, "sport": sport_slug,
        }).encode()
        req = urllib.request.Request(
            "https://api-offering.betonline.ag/api/offering/Sports/offering-by-league",
            data=payload, method="POST",
            headers={
                "Accept": "application/json", "Content-Type": "application/json",
                "Origin": "https://www.betonline.ag", "Referer": "https://www.betonline.ag/",
                "gsetting": "bolsassite", "utc-offset": "420",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200: return []
            data = json.loads(r.read())
        results = []
        # Real confirmed schema (verified against live response, MLB 2026-07-05):
        # GameOffering.GamesDescription[].Game.{AwayTeam,HomeTeam,
        #   AwayLine.{SpreadLine:{Point,Line}, MoneyLine:{Line}},
        #   HomeLine.{SpreadLine:{Point,Line}, MoneyLine:{Line}},
        #   TotalLine.TotalLine.{Point, Over:{Line}, Under:{Line}}}
        games_desc = (data.get("GameOffering", {}) or {}).get("GamesDescription", []) or []
        for gd in games_desc:
            g = gd.get("Game", {})
            away, home = g.get("AwayTeam"), g.get("HomeTeam")
            if not away or not home:
                continue
            game = f"{away} @ {home}"
            away_line = g.get("AwayLine", {})
            home_line = g.get("HomeLine", {})

            away_ml = away_line.get("MoneyLine", {}).get("Line")
            home_ml = home_line.get("MoneyLine", {}).get("Line")
            if away_ml:
                results.append({"game": game, "home": home, "away": away, "market": "Moneyline", "selection": away, "odds": away_ml, "book": "BetOnline", "sport": sport, "source": "betonline"})
            if home_ml:
                results.append({"game": game, "home": home, "away": away, "market": "Moneyline", "selection": home, "odds": home_ml, "book": "BetOnline", "sport": sport, "source": "betonline"})

            away_spread = away_line.get("SpreadLine", {})
            home_spread = home_line.get("SpreadLine", {})
            if away_spread.get("Line"):
                results.append({"game": game, "home": home, "away": away, "market": "Spread", "selection": f"{away} {away_spread.get('Point','')}", "odds": away_spread["Line"], "book": "BetOnline", "sport": sport, "source": "betonline"})
            if home_spread.get("Line"):
                results.append({"game": game, "home": home, "away": away, "market": "Spread", "selection": f"{home} {home_spread.get('Point','')}", "odds": home_spread["Line"], "book": "BetOnline", "sport": sport, "source": "betonline"})

            total_line = (g.get("TotalLine", {}) or {}).get("TotalLine", {}) or {}
            total_point = total_line.get("Point")
            over_odds = total_line.get("Over", {}).get("Line")
            under_odds = total_line.get("Under", {}).get("Line")
            if total_point and over_odds:
                results.append({"game": game, "home": home, "away": away, "market": "Total", "selection": f"Over {total_point}", "odds": over_odds, "book": "BetOnline", "sport": sport, "source": "betonline"})
            if total_point and under_odds:
                results.append({"game": game, "home": home, "away": away, "market": "Total", "selection": f"Under {total_point}", "odds": under_odds, "book": "BetOnline", "sport": sport, "source": "betonline"})

        if results: _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_betonline_offering: {e}"); return []


CAESARS_COMP_IDS = {
    "MLB": "04f90892-3afa-4e84-acce-5b89f151063d",
    "NBA": "aeaaf4d8-1f8c-4f22-bb50-79c2a3fcff37",
    "NFL": "007d7c61-07a7-4e18-bb40-15104b6eac92",
    "NHL": "144fe91b-f078-4ccd-ac3a-d77c2de451a5",
}
CAESARS_PROP_TABS = {
    "MLB": ["SCHEDULE|Batter Props","SCHEDULE|Pitcher Props"],
    "NBA": ["SCHEDULE|Player Props"],
    "NFL": ["SCHEDULE|Player Props"],
    "NHL": ["SCHEDULE|Player Props"],
}

def _get_caesars_tokens():
    """Bearer JWT + WAF token for Caesars, both from the same Gist file that
    fetch_caesars_waf_from_gist() reads (waf only). Routed through the shared
    _read_gist_file() rather than a separate raw fetch, so there's one code
    path to this file instead of two that could drift out of sync."""
    try:
        tokens = _read_gist_file("betcouncil_caesars_tokens.json", cache_minutes=5)
        return tokens.get("bearer_jwt",""), tokens.get("waf_token","")
    except Exception as e:
        print(f"[WARN] _get_caesars_tokens: {e}"); return "",""

def fetch_parlayapi_retail_props(bookmaker: str, sport: str) -> list:
    """
    Fetch retail sportsbook player props via the same ParlayAPI endpoint
    already integrated for DFS-book comparison (fetch_parlayapi_props) --
    same key, same 3-credits-flat cost regardless of which bookmakers are
    requested (confirmed live this session, plus independently
    cross-checked against ParlayAPI's own public docs/homepage, which
    explicitly list Caesars and BetRivers among supported bookmakers with
    a matching field schema: bookmaker, player, market_key, market, line,
    over_price, under_price -- American odds ints for retail rows, not
    the DFS-normalized midpoint pricing).

    bookmaker: ParlayAPI's exact key name, e.g. "caesars", "betrivers"
    (no "_sportsbook" suffix -- confirmed via their public /v1/bookmakers
    endpoint).
    """
    if not PARLAY_API_KEY:
        return []
    cache_path = os.path.join(CACHE_DIR, f"parlayapi_retail_{bookmaker}_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 20:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached
    sport_map = {
        "NBA": "basketball_nba", "WNBA": "basketball_wnba",
        "MLB": "baseball_mlb", "NHL": "icehockey_nhl", "NFL": "americanfootball_nfl"
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    stat_map = {
        "player_points": "Points", "player_rebounds": "Rebounds",
        "player_assists": "Assists", "player_threes": "3-PT Made",
        "player_steals": "Steals", "player_blocks": "Blocked Shots",
        "player_turnovers": "Turnovers", "player_pra": "Pts+Reb+Ast",
        "player_pts_rebs": "Pts+Reb", "player_pts_asts": "Pts+Ast",
        "player_rebs_asts": "Reb+Ast", "player_double_double": "Double-Double",
        "player_hits": "Hits", "player_home_runs": "Home Runs",
        "player_total_bases": "Total Bases", "player_rbis": "RBIs",
        "player_strikeouts": "Strikeouts", "player_hits_runs_rbis": "Hits+Runs+RBIs",
        "player_goals": "Goals", "player_shots_on_goal": "Shots On Goal",
        "player_pass_yds": "Passing Yards", "player_rush_yds": "Rushing Yards",
        "player_rec_yds": "Receiving Yards", "player_receptions": "Receptions",
    }
    try:
        resp = _http.get(
            f"{PARLAY_API_BASE}/sports/{sport_key}/props",
            headers={"X-API-Key": PARLAY_API_KEY},
            params={"bookmakers": bookmaker},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        props = []
        seen = set()
        for row in data:
            if row.get("bookmaker", "") != bookmaker:
                continue
            player = row.get("player", "")
            market_key = row.get("market_key", "")
            stat = stat_map.get(market_key, row.get("market") or market_key.replace("player_", "").replace("_", " ").title())
            line = row.get("line")
            if not player or not stat or line is None:
                continue
            key = (player, stat, line)
            if key in seen:
                continue
            seen.add(key)
            props.append({
                "Player": player, "Prop": stat, "Line": float(line),
                "OverOdds": row.get("over_price"), "UnderOdds": row.get("under_price"),
                "Book": bookmaker.title(), "Sport": sport, "source": "parlayapi",
            })
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
        return props
    except (IOError, ValueError):
        return []


def fetch_caesars_props(sport: str) -> list:
    """
    PRIMARY (Jul 2026): ParlayAPI retail props -- confirmed live this
    session (529 real MLB prop rows across 20 stat categories), same 0
    extra cost as the already-integrated DFS calls on this key. Replaces
    the fragile Bearer+WAF-token scraper as primary; that path needs a
    manually-refreshed session (tokens expire ~24h, automated login was
    attempted and confirmed blocked by an invisible WAF gate earlier this
    session).

    SECONDARY (previous primary): americanwagering.com direct, kept as a
    real fallback rather than removed.
    """
    try:
        primary = fetch_parlayapi_retail_props("caesars", sport)
    except Exception:
        primary = []
    if primary:
        return primary
    return _fetch_caesars_props_direct(sport)


def _fetch_caesars_props_direct(sport: str) -> list:
    """Caesars player props via americanwagering.com. Bearer from Gist. Cached 20 min."""
    import urllib.parse as _up
    comp_id = CAESARS_COMP_IDS.get(sport)
    tabs    = CAESARS_PROP_TABS.get(sport, [])
    if not comp_id or not tabs: return []
    cache_path = os.path.join(CACHE_DIR, f"caesars_props_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 20:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    bearer, waf = _get_caesars_tokens()
    if not bearer: return []
    hdrs = {
        "Accept":"application/json","Authorization":f"Bearer {bearer}",
        "Content-Type":"application/json","Origin":"https://sportsbook.caesars.com",
        "Referer":"https://sportsbook.caesars.com/","x-app-version":"7.50.0",
        "x-aws-waf-token":waf,"x-platform":"cordova-desktop",
        "x-unique-device-id":"d1231cdb-6e59-4f9c-9402-d250d10085e4","sessionid":bearer,
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    results = []
    for tab in tabs:
        try:
            url = (f"https://api.americanwagering.com/regions/us/locations/az/brands/czr"
                   f"/sb/v4/sports/{sport.lower()}/competitions/{comp_id}/tabs/{_up.quote(tab,safe='')}")
            r = _http.get(url, headers=hdrs, timeout=15)
            if r.status_code == 401: print("[WARN] Caesars token expired"); break
            if r.status_code != 200: continue
            for comp in r.json().get("competitions",[]):
                for event in comp.get("events",[]):
                    for mkt in event.get("markets",[]):
                        mn = mkt.get("name","")
                        player = mn.split(" - ")[0] if " - " in mn else mn
                        prop_t = mn.split(" - ")[-1] if " - " in mn else mn
                        ov=un=ln=""
                        for oc in mkt.get("outcomes",[]):
                            nm=oc.get("name",""); pr=oc.get("price",{}); od=pr.get("a",pr.get("d",""))
                            hd=str(oc.get("handicap",""))
                            if hd and hd!="None": ln=hd
                            if "Over" in nm or "over" in nm: ov=str(int(float(od))) if od else "N/A"
                            elif "Under" in nm or "under" in nm: un=str(int(float(od))) if od else "N/A"
                        if player and (ov or un):
                            results.append({"Player":player,"Prop":prop_t,"Line":ln,
                                "OverOdds":ov or "N/A","UnderOdds":un or "N/A",
                                "Book":"Caesars","Sport":sport,"source":"caesars_props"})
            time.sleep(0.3)
        except Exception as e:
            print(f"[WARN] fetch_caesars_props {tab}: {e}")
    if results: _safe_save_pkl(cache_path, results)
    return results

def fetch_kalshi_markets(sport: str) -> list:
    """
    Fetch Kalshi prediction market contracts for sports props.
    Public API — no auth needed. Cached 30 min.

    Filters by keyword match on market title/subtitle rather than the
    series_ticker param -- Kalshi's real series tickers are internal
    prefixed codes (e.g. a confirmed real example: 'KX1HALVING'), not
    plain sport names, so filtering server-side by an uppercased sport
    word like 'MLB' or 'BASKETBALL' almost certainly matched zero real
    series and silently returned nothing every time.
    """
    cache_path = os.path.join(CACHE_DIR, f"kalshi_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        sport_keywords = {
            "MLB": ["baseball", "mlb"],
            "NBA": ["basketball", "nba"],
            "WNBA": ["wnba"],
            "NFL": ["football", "nfl"],
            "NHL": ["hockey", "nhl"],
        }
        keywords = sport_keywords.get(sport, [sport.lower()])
        results = []
        cursor = None
        for _ in range(3):  # a few pages of open markets, bounded
            params = {"status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            r = _http.get(
                "https://api.elections.kalshi.com/trade-api/v2/markets",
                params=params,
                headers={"Accept": "application/json"},
                timeout=12,
            )
            if r.status_code != 200:
                break
            data = r.json()
            for mkt in data.get("markets", []):
                _title = (mkt.get("title", "") + " " + mkt.get("subtitle", "")).lower()
                if not any(kw in _title for kw in keywords):
                    continue
                _yes_bid = mkt.get("yes_bid")
                try:
                    _implied_prob = float(_yes_bid) / 100.0 if _yes_bid is not None else 0.5
                except (TypeError, ValueError):
                    _implied_prob = 0.5
                try:
                    _volume = float(mkt.get("volume") or 0)
                except (TypeError, ValueError):
                    _volume = 0.0
                results.append({
                    "title":        mkt.get("title", ""),
                    "event":        mkt.get("title", ""),
                    "ticker":       mkt.get("ticker", ""),
                    "yes_bid":      _yes_bid,
                    "no_bid":       mkt.get("no_bid"),
                    "implied_prob": _implied_prob,
                    "volume":       _volume,
                    "sport":        sport,
                    "source":       "kalshi",
                })
            cursor = data.get("cursor")
            if not cursor:
                break
            time.sleep(0.2)
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_kalshi_markets: {e}")
        return []


def fetch_polymarket_markets(sport: str) -> list:
    """
    Fetch Polymarket prediction markets for sports.
    Public API — no auth needed. Cached 30 min.

    Uses numeric tag_id (confirmed live-verified in SharpTrack's harvester
    this same session) via /events, not text-based tag= filtering on
    /markets -- Polymarket's tag_slug/tag text filtering is confirmed
    broken (tag_slug=nba returned unrelated politics/election events, zero
    NBA content, live-tested), so the same unreliable pattern isn't reused
    here even though it's a different endpoint/param.
    """
    cache_path = os.path.join(CACHE_DIR, f"polymarket_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        sport_tag_ids = {
            "NFL": 450, "NBA": 745, "WNBA": 100254, "MLB": 100381, "NHL": 899,
        }
        tag_id = sport_tag_ids.get(sport)
        if not tag_id:
            return []
        r = _http.get(
            "https://gamma-api.polymarket.com/events",
            params={"tag_id": tag_id, "active": "true", "closed": "false",
                    "order": "volume24hr", "ascending": "false", "limit": 50},
            headers={"Accept": "application/json"},
            timeout=12,
        )
        if r.status_code != 200:
            return []
        results = []
        for event in r.json():
            for mkt in event.get("markets", []) or []:
                _outcome_prices = mkt.get("outcomePrices")
                if isinstance(_outcome_prices, str):
                    try:
                        _outcome_prices = json.loads(_outcome_prices)
                    except (TypeError, ValueError):
                        _outcome_prices = None
                _yes_price = _outcome_prices[0] if _outcome_prices else None
                try:
                    _implied_prob = float(_yes_price) if _yes_price not in (None, "") else 0.5
                except (TypeError, ValueError):
                    _implied_prob = 0.5
                try:
                    _volume = float(mkt.get("volume") or 0)
                except (TypeError, ValueError):
                    _volume = 0.0
                results.append({
                    "question":     mkt.get("question", ""),
                    "slug":         mkt.get("slug", ""),
                    "yes_price":    _yes_price,
                    "implied_prob": _implied_prob,
                    "volume":       _volume,
                    "sport":        sport,
                    "source":       "polymarket",
                })
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_polymarket_markets: {e}")
        return []


def fetch_covers_consensus(sport: str) -> dict:
    """
    Fetch Covers.com public consensus betting data.

    URL FIX (Jul 9 2026): the old covers.com/sport/{sport}/consensus page
    was retired — Covers moved consensus picks to a separate contests
    subdomain: contests.covers.com/consensus/topconsensus/{sport}/overall.

    PARSER FIX (Jul 9 2026, verified via direct HTTP fetch of the real page):
    this is plain server-rendered HTML, NOT embedded JSON — there is no
    window.__INITIAL_STATE__ blob on this page (confirmed: 0 matches).
    Real per-row structure:
      - Away team:  <span class="covers-CoversConsensus-table--teamBlock">
      - Home team:  <span class="covers-CoversConsensus-table--teamBlock2">
      - Consensus%: <span class="covers-CoversConsensus-consensusTable--low">
                    and "...--high"> (low = less-picked side, high = more-
                    picked side — these describe magnitude, not home/away,
                    so they're paired with team names by DOM order, not by
                    the low/high label itself)
      - Odds:       plain text "-106<br />-117" in the next <td>
      - Picks:      plain text "12<br />39"
    Returns {matchup: {away_pct, home_pct}}. Cached 30 min.
    """
    cache_path = os.path.join(CACHE_DIR, f"covers_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        sport_map = {
            "MLB": "mlb", "NBA": "nba", "NFL": "nfl", "NHL": "nhl",
            "WNBA": "wnba", "CFL": "cfl",
        }
        slug = sport_map.get(sport)
        if not slug:
            return {}
        url = f"https://contests.covers.com/consensus/topconsensus/{slug}/overall"
        r = _http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"}, timeout=15)
        if r.status_code != 200 and SCRAPERAPI_KEY:
            proxy_url = f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={url}"
            r = _http.get(proxy_url, timeout=20)
        if r.status_code != 200:
            return {}
        results = {}
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.find_all("tr"):
                away_block = row.find("span", class_="covers-CoversConsensus-table--teamBlock")
                home_block = row.find("span", class_="covers-CoversConsensus-table--teamBlock2")
                if not away_block or not home_block:
                    continue
                away_team = away_block.get_text(strip=True)
                home_team = home_block.get_text(strip=True)
                if not away_team or not home_team:
                    continue
                pct_spans = row.find_all("span", class_=lambda c: c and (
                    "covers-CoversConsensus-consensusTable--low" in c or
                    "covers-CoversConsensus-consensusTable--high" in c
                ))
                pcts = []
                for span in pct_spans:
                    m = re.search(r"(\d{1,3})%", span.get_text(strip=True))
                    if m:
                        pcts.append(int(m.group(1)))
                if len(pcts) != 2:
                    continue
                results[f"{away_team} @ {home_team}"] = {
                    "away_pct": pcts[0],
                    "home_pct": pcts[1],
                }
        except ImportError:
            pass
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_covers_consensus: {e}")
        return {}


# ── Functions extracted from app.py ──────────────────────────────────────

def fetch_dk_salaries(sport="NBA"):
    """
    Fetch DraftKings DFS salary data for today's slate.
    Returns dict: {player_name: {salary, avg_points, value_score}}
    High salary = DK model projects big game
    Value score = projected points per $1000 salary
    """
    cache_path = os.path.join(CACHE_DIR, f"dk_salaries_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                return pickle.load(f)

    sport_map = {
        "NBA": "NBA", "MLB": "MLB", "NHL": "NHL",
        "NFL": "NFL", "WNBA": "WNBA"
    }
    dk_sport = sport_map.get(sport)
    if not dk_sport:
        return {}

    try:
        # Step 1: get draftGroupId
        contests_r = _http.get(
            f"https://www.draftkings.com/lobby/getcontests?sport={dk_sport}",
            headers={**HEADERS, "Referer": "https://www.draftkings.com/"},
            timeout=10
        )
        if contests_r.status_code != 200:
            return {}

        contests = contests_r.json().get("Contests", [])
        draft_group_id = None
        for c in contests:
            name = c.get("n", "").lower()
            if ("classic" in name or "showdown" not in name) and c.get("dg"):
                draft_group_id = c["dg"]
                break

        if not draft_group_id:
            return {}

        # Step 2: get draftable players with salaries
        players_r = _http.get(
            f"https://api.draftkings.com/draftgroups/v1/{draft_group_id}/draftables",
            headers={**HEADERS, "Referer": "https://www.draftkings.com/"},
            timeout=10
        )
        if players_r.status_code != 200:
            return {}

        data = players_r.json()
        draftables = data.get("draftables", [])

        salaries = {}
        for player in draftables:
            name = player.get("displayName", "")
            salary = player.get("salary", 0)
            avg_pts = player.get("draftStatAttributes", [{}])
            # Extract average FPPG
            fppg = 0.0
            for attr in player.get("draftStatAttributes", []):
                if attr.get("id") == 90:  # FPPG stat id
                    try:
                        fppg = float(attr.get("value", 0))
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            if name and salary:
                value_score = round((fppg / (salary / 1000)), 2) if salary > 0 else 0
                salaries[normalize_name(name)] = {
                    "name": name,
                    "salary": salary,
                    "fppg": fppg,
                    "value": value_score,
                    "salary_tier": (
                        "ELITE" if salary >= 9000 else
                        "HIGH" if salary >= 7500 else
                        "MID" if salary >= 6000 else
                        "VALUE"
                    )
                }

        if salaries:
            with open(cache_path, "wb") as f:
                pickle.dump(salaries, f)
            st.session_state["dk_salaries"] = salaries

        return salaries

    except (KeyError, TypeError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_dk_salaries",
            "error": str(e)[:100]
        })
        return {}

def fetch_mlb_rolling_averages():
    import sys as _sys
    ewma_average = getattr(_sys.modules.get("app"), "ewma_average", None) or (lambda vals, decay=0.85, sport=None: round(sum(vals)/len(vals), 2) if vals else 0.0)
    PLAYER_AVERAGES = getattr(_sys.modules.get("app"), "PLAYER_AVERAGES", None) or {}
    cache_path = os.path.join(CACHE_DIR, "mlb_rolling_avgs.pkl")

    # Was write-only -- this cache file got saved on every successful run
    # but was NEVER checked before doing the full expensive per-player
    # fetch again. Confirmed real root cause of multi-minute board loads
    # (live Streamlit logs showed this function timing out at the full
    # 25s ceiling): a fully SEQUENTIAL loop over the entire MLB roster
    # (potentially 750+ players across 30 teams), one HTTP call at a
    # time, plus an explicit time.sleep(0.3) after every successful call.
    # 20-minute freshness window -- rolling averages don't need to be
    # any fresher than that within a single browsing session.
    if os.path.exists(cache_path):
        age_min = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_min < 20:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    all_roster_ids = st.session_state.get("mlb_roster_ids") or MLB_PLAYER_IDS
    _errors = []

    def _fetch_one(player_name, player_id):
        player_avgs = PLAYER_AVERAGES.get("MLB", {}).get(player_name, {})
        is_pitcher = "SO" in player_avgs or "ER" in player_avgs
        group = "pitching" if is_pitcher else "hitting"
        url = (f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group={group}&season={_current_mlb_season_year()}&gameType=R")
        resp = None
        for _attempt in range(2):
            try:
                resp = _http.get(url, headers=HEADERS, timeout=10)
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                    requests.exceptions.RetryError, requests.exceptions.ChunkedEncodingError) as _conn_e:
                if _attempt == 0:
                    time.sleep(1.0)
                    continue
                _errors.append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_mlb_rolling_averages",
                                 "error": f"statsapi unreachable after retry: {str(_conn_e)[:80]}"})
                resp = None
        if resp is None:
            return None
        try:
            if resp.status_code != 200:
                return None
            data = resp.json()
            stats_list = data.get("stats", [])
            if not stats_list:
                return None
            splits = stats_list[0].get("splits", [])
            last10 = splits[-10:] if len(splits) >= 10 else splits
            if len(last10) < 3:
                return None
            if is_pitcher:
                so_vals = [g["stat"].get("strikeOuts",0) for g in last10]
                er_vals = [g["stat"].get("earnedRuns",0) for g in last10]
                h_vals = [g["stat"].get("hits",0) for g in last10]
                return {
                    "SO": ewma_average(so_vals, sport="MLB"),
                    "ER": ewma_average(er_vals, sport="MLB"),
                    "H": ewma_average(h_vals, sport="MLB"),
                    "SO_std": compute_std_dev(so_vals, sport="MLB") or 2.0,
                    "ER_std": compute_std_dev(er_vals, sport="MLB") or 1.0,
                    "H_std": compute_std_dev(h_vals, sport="MLB") or 0.3,
                    "n_games": len(last10)
                }
            else:
                h_vals = [g["stat"].get("hits",0) for g in last10]
                hr_vals = [g["stat"].get("homeRuns",0) for g in last10]
                rbi_vals = [g["stat"].get("rbi",0) for g in last10]
                r_vals = [g["stat"].get("runs",0) for g in last10]
                return {
                    "H": ewma_average(h_vals, sport="MLB"),
                    "HR": ewma_average(hr_vals, sport="MLB"),
                    "RBI": ewma_average(rbi_vals, sport="MLB"),
                    "R": ewma_average(r_vals, sport="MLB"),
                    "H_std": compute_std_dev(h_vals, sport="MLB") or 0.4,
                    "HR_std": compute_std_dev(hr_vals, sport="MLB") or 0.12,
                    "RBI_std": compute_std_dev(rbi_vals, sport="MLB") or 0.5,
                    "R_std": compute_std_dev(r_vals, sport="MLB") or 0.4,
                    "n_games": len(last10)
                }
        except Exception as e:
            _errors.append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_mlb_rolling_averages", "error": str(e)[:100]})
            return None

    # Parallelized (was fully sequential + a mandatory 0.3s sleep per
    # player) -- real wait(timeout=...) ceiling, not the buggy
    # as_completed()+per-future-timeout pattern, and not a `with...as ex:`
    # block (that pattern's __exit__ blocks until every thread finishes
    # regardless of the timeout, already diagnosed and fixed elsewhere
    # this session). No st.session_state access needed inside workers --
    # roster data resolved once up front, errors collected in a plain
    # list and flushed to session_state after the parallel section ends.
    from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait
    players = list(all_roster_ids.items())
    rolling = {}
    if players:
        ex = ThreadPoolExecutor(max_workers=min(len(players), 30))
        futures = {ex.submit(_fetch_one, name, pid): name for name, pid in players}
        done, not_done = _cf_wait(futures.keys(), timeout=25)
        for fut in done:
            name = futures[fut]
            try:
                result = fut.result()
            except Exception:
                result = None
            if result:
                rolling[name] = result
        ex.shutdown(wait=False)

    if _errors:
        st.session_state.setdefault("errors", []).extend(_errors[:20])

    try:
        if rolling:
            with open(cache_path, "wb") as f:
                pickle.dump(rolling, f)
    except Exception:
        pass
    return rolling


# ═══════════════════════════════════════════════════════════
# MODULE: LIVE STATS — Tennis, Golf, Soccer, UFC, NFL, WNBA
# All use ESPN public API (site.api.espn.com) — free, no key.
# Works in deployed app via curl_cffi TLS impersonation.
# Cached 6-24h per sport. Falls back to hardcoded baselines.
# ═══════════════════════════════════════════════════════════

def _write_pp_lkg(sport: str, props: list) -> None:
    """Write PrizePicks props to the last-known-good pickle cache."""
    try:
        lkg_path = os.path.join(CACHE_DIR, f"pp_last_known_good_{sport}.pkl")
        with open(lkg_path, "wb") as _f:
            pickle.dump(props, _f)
    except OSError:
        pass


def scrape_prizepicks_with_gist_fallback(sport):
    """
    Priority order:
    1. Gist (from auto-scraper)   — primary; Gist-first already baked into
                                    scrape_prizepicks(), but we also call
                                    fetch_auto_scraped_props() directly here
                                    to capture the result for LKG caching.
    2. scrape_prizepicks(sport)   — curl_cffi chrome124/chrome110 + Gist safety net.
    3. Last-known-good cache      — stale pickle from last successful run,
                                    surfaced with a visible st.warning banner
                                    instead of silently returning [].

    LKG is written on every successful return so it's always as fresh as
    the most recent working fetch.
    """
    import pickle as _pkl

    lkg_path = os.path.join(CACHE_DIR, f"pp_last_known_good_{sport}.pkl")

    # ── 0. Dedicated PrizePicks Gist file (browser harvester / daily script) ───
    # betcouncil_prizepicks_{sport}.json is written by the Tampermonkey script
    # or scripts/fetch_prizepicks_daily.py.  Checked first because it is always
    # sport-specific and fresher than the multi-book auto_scraped_props dump.
    try:
        _pp_h_props, _pp_h_src = fetch_prizepicks_from_gist(sport)
        if _pp_h_props:
            st.session_state["pp_source"] = _pp_h_src
            st.session_state["pp_status"] = "ok"
            _write_pp_lkg(sport, _pp_h_props)
            return _pp_h_props
    except Exception:
        pass

    # ── 1. Gist direct (auto_scraped_props.json from local PC scraper) ────────
    gist_props = fetch_auto_scraped_props(sport)
    if gist_props:
        st.session_state["pp_source"] = "gist_scraper"
        st.session_state["pp_status"] = "ok"
        _write_pp_lkg(sport, gist_props)
        return gist_props

    # ── 2. Live scrape (curl_cffi → chrome110 → Gist safety-net) ─────────────
    log_error_to_session(
        "scrape_prizepicks_with_gist_fallback",
        f"Gist empty for {sport} — trying live scrape...",
        "warning",
    )
    pp_props = scrape_prizepicks(sport)
    if pp_props:
        st.session_state["pp_source"] = "prizepicks_direct"
        st.session_state["pp_status"] = "ok"
        _write_pp_lkg(sport, pp_props)
        return pp_props

    # ── 3. Last-known-good ────────────────────────────────────────────────────
    try:
        if os.path.exists(lkg_path):
            _lkg_age_h = (time.time() - os.path.getmtime(lkg_path)) / 3600
            # Refuse to serve a slate older than one cycle — an old cache can
            # contain players whose games already happened, which would
            # otherwise surface as a top-edge / Lock of the Day pick today.
            if _lkg_age_h > 6:
                st.session_state["pp_status"] = "unavailable"
                st.session_state["pp_source"] = "none"
                log_error_to_session(
                    "scrape_prizepicks_with_gist_fallback",
                    f"LKG cache is {_lkg_age_h:.1f}h old — too stale to serve "
                    "(likely yesterday's slate). Treating as unavailable.",
                    "error",
                )
            else:
                with open(lkg_path, "rb") as _f:
                    _lkg = _pkl.load(_f)
                if _lkg:
                    st.warning(
                        f"⚠️ **PrizePicks live data unavailable** — showing last cached "
                        f"props ({_lkg_age_h:.0f}h old). Data may be stale. Refresh to retry.",
                        icon="🟡",
                    )
                    st.session_state["pp_source"] = "last_known_good"
                    st.session_state["pp_status"] = "stale"
                    log_error_to_session(
                        "scrape_prizepicks_with_gist_fallback",
                        f"Serving LKG cache ({_lkg_age_h:.1f}h old, {len(_lkg)} props)",
                        "warning",
                    )
                    return _lkg
    except (OSError, _pkl.UnpicklingError, EOFError):
        pass

    # ── 4. Truly nothing ─────────────────────────────────────────────────────
    st.session_state["pp_status"] = "unavailable"
    st.session_state["pp_source"] = "none"
    log_error_to_session(
        "scrape_prizepicks_with_gist_fallback",
        f"PrizePicks unavailable for {sport} — all paths exhausted, no LKG cache",
        "error",
    )
    return []




# ── EV Sharps API (20+ books — Hard Rock, DK, FD, MGM, Caesars, Pinnacle, Circa, etc.) ──
# ── EV Line Movement — snapshot delta engine ─────────────────────────────────
# Replaces the /api/movement endpoint by comparing successive /api/ev snapshots.
# Every board load compares current bookOdds against the previous snapshot
# stored in session_state["ev_odds_snapshot"], computes deltas, and fires S8/S9.

def fetch_bovada_game_lines(sport: str) -> list:
    """
    Fetch Bovada game lines via public coupon API — no auth required.
    Endpoint: /services/sports/event/coupon/events/A/description/{sport_path}
    Returns list of {game, home, away, market, selection, odds, book, sport, source}
    Cached 15 min.
    """
    sport_map = {
        "MLB":  "baseball/mlb",
        "NBA":  "basketball/nba",
        "NFL":  "football/nfl",
        "NHL":  "hockey/nhl",
        "WNBA": "basketball/wnba",
    }
    sport_path = sport_map.get(sport)
    if not sport_path:
        return []

    cache_path = os.path.join(CACHE_DIR, f"bovada_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 15:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        url = (
            f"https://www.bovada.lv/services/sports/event/coupon/events/A/description"
            f"/{sport_path}?marketFilterId=def&preMatchOnly=true&eventsLimit=5000&lnGrp=2&lang=en"
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
            "Referer": f"https://www.bovada.lv/sports/{sport_path}",
            "x-channel": "desktop",
            "x-sport-context": "BASE",
            "cookie": "LANG=en; Device-Type=Desktop|false; odds_format=AMERICAN;",
        }
        r = _http.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[WARN] fetch_bovada_game_lines HTTP {r.status_code}")
            return []

        data = r.json()
        results = []
        for group in data:
            for event in group.get("events", []):
                competitors = event.get("competitors", [])
                if len(competitors) < 2:
                    continue
                away = competitors[0].get("name", "")
                home = competitors[1].get("name", "")
                game = f"{away} @ {home}"

                for display_grp in event.get("displayGroups", []):
                    for market in display_grp.get("markets", []):
                        market_desc = market.get("description", "")
                        for outcome in market.get("outcomes", []):
                            label = outcome.get("description", "")
                            price = outcome.get("price", {})
                            american = price.get("american", "")
                            if not american or american in ("EVEN", ""):
                                american = price.get("decimal", "")
                            results.append({
                                "game":      game,
                                "home":      home,
                                "away":      away,
                                "market":    market_desc,
                                "selection": label,
                                "odds":      american,
                                "book":      "Bovada",
                                "sport":     sport,
                                "source":    "bovada_lines",
                            })
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_bovada_game_lines: {e}")
        return []


def fetch_bovada_props(sport: str) -> list:
    """
    PRIMARY (Jul 2026): Odds-API.io -- confirmed live this session (18/18
    MLB games, 50-51 real Bovada prop entries per game), using its own
    separate account/key (ODDS_API_IO_KEY_BOVADA) since the free tier
    caps at 2 bookmakers per key (Bet365+FanDuel already use the other
    key's 2 slots). Identical "Player (Stat)" label format to FanDuel,
    confirmed via live test.

    SECONDARY (previous primary): direct public Bovada props API, kept
    as a real fallback rather than removed.
    Returns list of {Player, Prop, Line, OverOdds, UnderOdds, Book, Sport, source}
    """
    try:
        oddsapiio_data = _read_gist_file(f"betcouncil_oddsapiio_bovada_props_{sport.upper()}.json", cache_minutes=15)
    except Exception:
        oddsapiio_data = None
    if oddsapiio_data and oddsapiio_data.get("props"):
        return oddsapiio_data["props"]
    return _fetch_bovada_props_direct(sport)


def _fetch_bovada_props_direct(sport: str) -> list:
    """
    Fetch Bovada player props via public props API — no auth required.
    Endpoint: /services/sports/event/coupon/events/A/description/{sport}-season-props
    Returns list of {Player, Prop, Line, OverOdds, UnderOdds, Book, Sport, source}
    Cached 20 min.
    """
    props_map = {
        "MLB":  "baseball/mlb-season-props",
        "NBA":  "basketball/nba-season-props",
        "NFL":  "football/nfl-season-props",
        "NHL":  "hockey/nhl-season-props",
    }
    props_path = props_map.get(sport)
    if not props_path:
        return []

    cache_path = os.path.join(CACHE_DIR, f"bovada_props_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 20:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        url = (
            f"https://www.bovada.lv/services/sports/event/coupon/events/A/description"
            f"/{props_path}?azSorting=true&lang=en"
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
            "Referer": f"https://www.bovada.lv/sports/{props_path}",
            "x-channel": "desktop",
            "x-sport-context": "BASE",
            "cookie": "LANG=en; Device-Type=Desktop|false; odds_format=AMERICAN;",
        }
        r = _http.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[WARN] fetch_bovada_props HTTP {r.status_code}")
            return []

        data = r.json()
        results = []
        for group in data:
            for event in group.get("events", []):
                for display_grp in event.get("displayGroups", []):
                    for market in display_grp.get("markets", []):
                        market_desc = market.get("description", "")
                        outcomes = market.get("outcomes", [])
                        # Pair Over/Under outcomes
                        over_odds = under_odds = line = player = ""
                        for outcome in outcomes:
                            desc  = outcome.get("description", "")
                            price = outcome.get("price", {})
                            odds  = price.get("american", "")
                            hdp   = price.get("handicap", "")
                            if not player:
                                # Player name often in market description
                                player = market_desc.split(" - ")[0] if " - " in market_desc else market_desc
                            if hdp:
                                line = str(hdp)
                            if "Over" in desc or "over" in desc:
                                over_odds = odds
                            elif "Under" in desc or "under" in desc:
                                under_odds = odds
                            else:
                                over_odds = odds  # moneyline-style prop

                        if player:
                            prop_type = market_desc.split(" - ")[-1] if " - " in market_desc else market_desc
                            results.append({
                                "Player":     player,
                                "Prop":       prop_type,
                                "Line":       line,
                                "OverOdds":   over_odds or "N/A",
                                "UnderOdds":  under_odds or "N/A",
                                "Book":       "Bovada",
                                "Sport":      sport,
                                "source":     "bovada_props",
                            })
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_bovada_props: {e}")
        return []

def fetch_betmgm_game_lines(sport: str) -> list:
    """
    Fetch BetMGM game lines (ML/spread/total) via widgetdata API.
    No Bearer token needed — uses session cookies from BETMGM_COOKIE secret.
    Cookie lasts ~24h. State: BETMGM_STATE (default az).

    FALLBACK (2026-07): if the direct widgetdata call fails (WAF-blocked
    from datacenter IPs, matches the same Cloudflare pattern found on
    Caesars/BetOnline this session), fall back to VSiN's line tracker,
    which already covers BetMGM (confirmed in its own docstring: "8 books
    ... + BetMGM, Caesars, Boomers"). VSiN was already being pulled
    elsewhere in the app for display, but was never wired as an actual
    fallback source here -- same "computed/fetched but not consumed"
    pattern found repeatedly this session. Same defensive multi-key
    book-name lookup as the rest of this session's work, since the exact
    casing VSiN uses for "BetMGM" in its books{} dict isn't independently
    confirmed against a live payload.
    Returns list of {game, home, away, market, selection, odds, book, sport, source}
    Cached 15 min.
    """
    result = _fetch_betmgm_widgetdata(sport)
    if result:
        return result
    return _fetch_betmgm_lines_via_vsin(sport)


def _fetch_betmgm_lines_via_vsin(sport: str) -> list:
    """VSiN-backed fallback for BetMGM game lines. See fetch_betmgm_game_lines
    for why this exists. Returns [] (not a guess) if VSiN's payload doesn't
    have a BetMGM entry under any of the plausible key casings.
    """
    try:
        games, src = fetch_vsin_from_gist(sport)
        if not games:
            return []
        out = []
        for g in games:
            books = g.get("books", {}) or {}
            bm = books.get("BetMGM") or books.get("betmgm") or books.get("BETMGM") or books.get("bet_mgm")
            if not bm:
                continue
            out.append({
                "game":     f"{g.get('away_team','')} @ {g.get('home_team','')}",
                "home":     g.get("home_team", ""), "away": g.get("away_team", ""),
                "spread":   bm.get("spread"), "spread_odds": bm.get("spread_odds"),
                "ml":       bm.get("ml"),     "total": bm.get("total"),
                "total_odds": bm.get("total_odds"),
                "book": "BetMGM", "sport": sport, "source": "vsin_fallback",
            })
        if out:
            print(f"[BetMGM] Fallback: {len(out)} games from VSiN")
        return out
    except Exception as e:
        print(f"[BetMGM] VSiN fallback error: {e}")
        return []


def _fetch_betmgm_widgetdata(sport: str) -> list:
    """
    Direct BetMGM widgetdata call -- the original implementation of what
    used to be fetch_betmgm_game_lines(), split out so VSiN can serve as
    a real fallback (see fetch_betmgm_game_lines / _fetch_betmgm_lines_via_vsin).
    No Bearer token needed — uses session cookies from BETMGM_COOKIE secret.
    Cookie lasts ~24h. State: BETMGM_STATE (default az).
    Returns list of {game, home, away, market, selection, odds, book, sport, source}
    Cached 15 min.
    """
    cookie = BETMGM_COOKIE
    state  = BETMGM_STATE or "az"
    ids    = BETMGM_SPORT_MAP.get(sport, {})
    widget = BETMGM_WIDGET_MAP.get(sport, "")
    if not ids or not widget:
        return []

    cache_path = os.path.join(CACHE_DIR, f"betmgm_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 15:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        sport_id  = ids["sportId"]
        region_id = ids["regionId"]
        comp_id   = ids["competitionId"]
        url = (
            f"https://www.{state}.betmgm.com/en/sports/api/widget/widgetdata"
            f"?layoutSize=Small&page=CompetitionLobby"
            f"&sportId={sport_id}&regionId={region_id}"
            f"&competitionId={comp_id}&compoundCompetitionId=1:{comp_id}"
            f"&widgetId=/mobilesports-v1.0/layout/layout_us/modules/{widget}"
            f"&shouldIncludePayload=true"
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
            "Referer": f"https://www.{state}.betmgm.com/en/sports",
            "sports-api-version": "SportsAPIv2",
            "x-bwin-sports-api": "prod",
            "x-device-type": "desktop_Windows 11",
            "x-from-product": "host-app",
        }
        if cookie:
            headers["cookie"] = cookie

        r = _http.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[WARN] fetch_betmgm_game_lines HTTP {r.status_code}")
            return []

        data = r.json()
        results = []

        # Parse widgetdata response — nested structure
        payload = data.get("payload", data)
        if isinstance(payload, str):
            import json as _json
            payload = _json.loads(payload)

        # Navigate to fixtures
        fixtures = []
        if isinstance(payload, dict):
            for key in ("fixtures", "events", "items", "data"):
                if key in payload:
                    fixtures = payload[key]
                    break
            # Try deeper nesting
            if not fixtures:
                for v in payload.values():
                    if isinstance(v, list) and v:
                        fixtures = v
                        break

        for fix in fixtures:
            if not isinstance(fix, dict):
                continue
            home = fix.get("homeTeam", {}).get("name", "") or fix.get("home", "")
            away = fix.get("awayTeam", {}).get("name", "") or fix.get("away", "")
            if not home or not away:
                continue
            game = f"{away} @ {home}"

            markets = fix.get("markets", fix.get("betOffers", []))
            for mkt in markets:
                market_name = mkt.get("name", mkt.get("betOfferType", {}).get("name", ""))
                for outcome in mkt.get("outcomes", mkt.get("betOffers", [])):
                    label  = outcome.get("label", outcome.get("name", ""))
                    price  = outcome.get("odds", outcome.get("americanOdds", outcome.get("price")))
                    if price is None:
                        continue
                    results.append({
                        "game":      game,
                        "home":      home,
                        "away":      away,
                        "market":    market_name,
                        "selection": label,
                        "odds":      price,
                        "book":      "BetMGM",
                        "sport":     sport,
                        "source":    "betmgm_lines",
                    })

        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_betmgm_game_lines: {e}")
        return []

def fetch_espnbet_game_lines(sport: str) -> list:
    """
    ESPN Bet no longer exists as a sportsbook -- confirmed via independent
    news search, not just a guess: ESPN Bet fully shut down and was
    replaced by theScore Bet on December 1, 2025 (PENN Entertainment and
    ESPN ended their sportsbook partnership; the app itself was updated
    in-place to theScore Bet's branding that day, with no ESPN Bet
    product remaining in any form). This isn't a transient outage to
    retry -- there is no "espnbet" Kambi offering to ever succeed again.
    theScore Bet's own data is already covered properly and separately by
    fetch_thescore_game_lines() (Unabated primary, browser-harvester
    fallback) -- that's the real, live successor to what this function
    used to represent. Returns [] immediately rather than wasting a
    network call on a permanently defunct endpoint.
    """
    return []


def fetch_fanatics_game_lines(sport: str) -> list:
    """Fanatics Sportsbook game lines via Kambi (offering_id='fanaticssb'). Cached 60 min."""
    return _fetch_kambi_game_lines("fanaticssb", sport, "Fanatics")


def fetch_thescore_game_lines(sport: str) -> list:
    """
    theScore Bet game lines.

    PRIMARY (Jul 10 2026): Unabated `straight` market data (source_id=36,
    theScore US), via the free scheduled Unabated refresher — no browser
    tab needs to stay open, unlike the Tampermonkey harvester below.

    FALLBACK: fetch_thescore_from_gist — browser harvester captures the
    CompetitionPageSectionLinesTabNode GraphQL response and pushes to Gist.
    Kept as a fallback since it's still a real, working, independently-
    sourced feed (and Unabated could theoretically drop theScore coverage
    without notice) — just no longer the primary since it requires you to
    keep a browser tab open, which the Unabated path doesn't.
    SECONDARY-SECONDARY: none — Kambi (offering_id='thescore') returned
    HTTP 410 Gone after theScore's Dec 2025 rebrand from ESPN Bet.

    Harvester config (fallback only):
      operationName : CompetitionPageSectionLinesTabNode
      sha256Hash    : 1ec1bed0d31b92e88825523405e45e88d6f34d484f4b0f3bbe4beb319229cab6
      Gist file     : betcouncil_thescore_games.json
    """
    props, _src = fetch_thescore_from_gist(sport)
    return props



def fetch_bet365_game_lines(sport: str) -> list:
    """
    Bet365 game lines.

    PRIMARY (Jul 2026): Odds-API.io, confirmed live this session against a
    real MLB game -- full moneyline + spread + totals coverage, not just
    match-result. Independently cross-checked against the vendor's own
    official SDK repos and best-practices docs before wiring in, not just
    a single live-test report.

    SECONDARY: Unabated `straight` market data (source_id=78) -- kept as
    a real, working fallback for whatever the primary above might be
    missing on a given day, rather than removed. Previously the only
    source, but only ever provided partial (moneyline/match-result)
    coverage -- spread/totals were always empty via this path alone.

    REMOVED: the old Kambi-based fallback, which this function's own
    docstring already flagged as very likely non-functional (Bet365 isn't
    a known Kambi platform customer) -- dead weight, not a real fallback.
    """
    try:
        data = _read_gist_file(f"betcouncil_oddsapiio_bet365_{sport.upper()}.json", cache_minutes=15)
    except Exception:
        data = None
    if data and data.get("games"):
        primary = [
            {
                "home_team": g.get("home_team"), "away_team": g.get("away_team"),
                "home_ml": g.get("home_ml"), "away_ml": g.get("away_ml"),
                "spread": g.get("spread_hdp"),
                "spread_home_odds": g.get("spread_home_odds"), "spread_away_odds": g.get("spread_away_odds"),
                "total": g.get("total_hdp"),
                "over_odds": g.get("over_odds"), "under_odds": g.get("under_odds"),
            }
            for g in data["games"]
        ]
        if primary:
            return primary
    return []


# ─────────────────────────────────────────────────────────────────────────────
# PINNACLE — Guest API (no credentials required)
#
# Pinnacle.com is blocked to US residents, so the authenticated API is
# inaccessible from US IPs.  The guest endpoint is public and requires no auth:
#   https://guest.api.pinnaclesports.com/v1/
#
# Sport IDs (integers): Baseball=3  Basketball=4  NFL=6  NHL=19  Soccer=29
# Odds format: oddsFormat=2 (American)
#
# Will return [] silently if the endpoint is unreachable from this server.
# ─────────────────────────────────────────────────────────────────────────────

# ── Pinnacle arcadia guest API ─────────────────────────────────────────────
# Confirmed from DevTools 2026-06-27:
#   GET guest.api.arcadia.pinnacle.com/0.1/leagues/{id}/matchups
#   GET guest.api.arcadia.pinnacle.com/0.1/leagues/{id}/markets/straight
# No auth. CORS open (*). DNS-blocked on Streamlit Cloud — use when self-hosted.

_PINNACLE_ARCADIA_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
_PINNACLE_ARCADIA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
}
_PINNACLE_SPORT_IDS = {
    "MLB": 3, "NBA": 4, "WNBA": 4, "NFL": 15, "NHL": 19,
}
_PINNACLE_LEAGUE_IDS = {
    "MLB": 246, "NBA": 487, "WNBA": 578, "NFL": 889, "NHL": 1456,
}


def _pinnacle_arcadia_get(path):
    """GET guest.api.arcadia.pinnacle.com/0.1{path}. No auth needed."""
    url = f"{_PINNACLE_ARCADIA_BASE}{path}"
    try:
        from curl_cffi import requests as _cf
        r = _cf.Session(impersonate="chrome124").get(url, headers=_PINNACLE_ARCADIA_HEADERS, timeout=12)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] Pinnacle arcadia HTTP {r.status_code} for {path}")
        return None
    except ImportError:
        try:
            import urllib.request as _ur
            req = _ur.Request(url, headers=_PINNACLE_ARCADIA_HEADERS)
            with _ur.urlopen(req, timeout=12) as resp:
                return json.loads(resp.read())
        except Exception as e2:
            print(f"[WARN] _pinnacle_arcadia_get fallback ({path}): {e2}")
            return None
    except Exception as e:
        print(f"[WARN] _pinnacle_arcadia_get ({path}): {e}")
        return None


def _pinn_american(price):
    """Arcadia returns American odds as integers already."""
    if price is None:
        return None
    try:
        return int(price)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


_TEAMRANKINGS_SPORT_PATHS = {
    "NBA": "nba", "WNBA": "wnba", "MLB": "mlb", "NHL": "nhl", "NFL": "nfl",
}

# Maps TeamRankings' short display names to the abbreviations/full names
# used elsewhere in app.py's power_ratings dicts. Extend as needed when a
# team comes back N/A in the merged ratings.
_TEAMRANKINGS_NAME_MAP = {
    "MLB": {
        "LA Dodgers": "Los Angeles Dodgers", "NY Yankees": "New York Yankees",
        "Philadelphia": "Philadelphia Phillies", "Boston": "Boston Red Sox",
        "Milwaukee": "Milwaukee Brewers", "Chi Cubs": "Chicago Cubs",
        "NY Mets": "New York Mets", "San Diego": "San Diego Padres",
        "Texas": "Texas Rangers", "Toronto": "Toronto Blue Jays",
        "Atlanta": "Atlanta Braves", "Seattle": "Seattle Mariners",
        "Arizona": "Arizona Diamondbacks", "Detroit": "Detroit Tigers",
        "Tampa Bay": "Tampa Bay Rays", "Houston": "Houston Astros",
        "Cincinnati": "Cincinnati Reds", "SF Giants": "San Francisco Giants",
        "Kansas City": "Kansas City Royals", "Cleveland": "Cleveland Guardians",
        "Baltimore": "Baltimore Orioles", "Minnesota": "Minnesota Twins",
        "St. Louis": "St. Louis Cardinals", "Pittsburgh": "Pittsburgh Pirates",
        "Sacramento": "Athletics", "LA Angels": "Los Angeles Angels",
        "Miami": "Miami Marlins", "Washington": "Washington Nationals",
        "Chi Sox": "Chicago White Sox", "Colorado": "Colorado Rockies",
    },
    "WNBA": {
        "New York": "New York Liberty", "Las Vegas": "Las Vegas Aces",
        "Connecticut": "Connecticut Sun", "Minnesota": "Minnesota Lynx",
        "Seattle": "Seattle Storm", "Dallas": "Dallas Wings",
        "Chicago": "Chicago Sky", "Phoenix": "Phoenix Mercury",
        "Atlanta": "Atlanta Dream", "Indiana": "Indiana Fever",
        "Washington": "Washington Mystics", "LA Sparks": "Los Angeles Sparks",
        "Los Angeles": "Los Angeles Sparks", "Toronto": "Toronto Tempo",
        "Golden State": "Golden State Valkyries", "Portland": "Portland Fire",
    },
}


def fetch_teamrankings_power_ratings(sport: str) -> dict:
    """
    Live, daily-updating predictive power ratings from TeamRankings.com —
    free, no auth, no login. Replaces/augments the static hardcoded
    *_POWER_RATINGS dicts in config.py, which never self-update.

    Returns {team_name: rating_float} using the same team-name keys as the
    existing power_ratings dicts (full names for MLB/WNBA, abbreviations
    for NBA/NFL/NHL handled by the caller's own normalization).
    Cached 6 hours (ratings don't move fast intra-day).
    """
    path = _TEAMRANKINGS_SPORT_PATHS.get(sport)
    if not path:
        return {}

    cache_path = os.path.join(CACHE_DIR, f"teamrankings_power_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 6:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    url = f"https://www.teamrankings.com/{path}/rankings/"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        html = resp.text
    except Exception as e:
        print(f"[WARN] fetch_teamrankings_power_ratings({sport}): {e}")
        return {}

    ratings = {}
    try:
        # Primary pattern: standard TR ratings table rows.
        # <tr ...><td>1</td><td class="text-right">1.09</td><td>...><a ...>LA Dodgers</a>...
        patterns = [
            re.compile(
                r'<tr[^>]*>\s*<td[^>]*>\s*(\d+)\s*</td>\s*<td[^>]*>\s*(-?[\d.]+)\s*</td>\s*<td[^>]*>.*?<a[^>]*>([^<(]+?)\s*(?:\([^)]*\))?\s*</a>',
                re.S
            ),
            # Fallback: looser match in case rank/rating column order or
            # wrapper tags differ from the primary pattern's assumption.
            re.compile(
                r'<a[^>]*href="/mlb/team/[^"]*"[^>]*>([^<(]+?)\s*(?:\([^)]*\))?\s*</a>\s*</td>\s*<td[^>]*>\s*(-?[\d.]+)\s*</td>',
                re.S
            ),
        ]
        for i, pat in enumerate(patterns):
            matches = pat.findall(html)
            if not matches:
                continue
            for m in matches:
                if i == 0:
                    _rank, rating_str, team_name = m
                else:
                    team_name, rating_str = m
                team_name = team_name.strip()
                if not team_name:
                    continue
                try:
                    rating_val = float(rating_str)
                except ValueError:
                    continue
                name_map = _TEAMRANKINGS_NAME_MAP.get(sport, {})
                mapped_name = name_map.get(team_name, team_name)
                ratings[mapped_name] = rating_val
            if ratings:
                break
        # Sanity check: a real ratings page has 28-32 teams depending on
        # sport. Fewer than ~20 means the parser likely matched garbage
        # (e.g. an unrelated table) — discard rather than poison the model.
        _min_teams = {"MLB": 25, "NBA": 25, "WNBA": 10, "NHL": 25, "NFL": 28}.get(sport, 20)
        if len(ratings) < _min_teams:
            print(f"[WARN] fetch_teamrankings_power_ratings({sport}): only parsed {len(ratings)} teams, expected >= {_min_teams} — discarding (page structure may have changed)")
            return {}
    except Exception as e:
        print(f"[WARN] fetch_teamrankings_power_ratings({sport}) parse: {e}")
        return {}

    if ratings:
        _safe_save_pkl(cache_path, ratings)
    return ratings



def fetch_mlb_live_stats() -> dict:
    """
    Live MLB season stats from statsapi.mlb.com standings.
    Replaces the broken TeamRankings HTML scraper (JS-rendered, unscrapeable)
    for MLB power ratings and provides a live base_total and league_avg_rs
    for use in analyze_game_edge.

    Returns:
      {
        "base_total": float,       # league avg RS/G * 2 (both teams combined)
        "league_avg_rs": float,    # league avg RS/G per team
        "team_ratings": {          # {full_team_name: rating} on 88-118 scale
            "Los Angeles Dodgers": 112.3, ...
        }
      }
    Cached 6 hours. Falls back to {} on any error (callers must handle).
    Rating formula: 100 + (run_differential_per_game * 7), capped 88-118.
    This matches the existing MLB_POWER_RATINGS scale in config.py.
    """
    cache_path = os.path.join(CACHE_DIR, "mlb_live_stats.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            cached = _safe_load_pkl(cache_path)
            if cached and isinstance(cached.get("team_ratings"), dict) and len(cached["team_ratings"]) >= 25:
                return cached

    url = (
        "https://statsapi.mlb.com/api/v1/standings"
        f"?leagueId=103,104&season={_current_mlb_season_year()}&standingsTypes=regularSeason&hydrate=team"
    )
    try:
        resp = _http.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            print(f"[WARN] fetch_mlb_live_stats: HTTP {resp.status_code}")
            return {}
        data = resp.json()
    except Exception as e:
        print(f"[WARN] fetch_mlb_live_stats: {e}")
        return {}

    total_rs = 0
    total_g = 0
    team_ratings: dict = {}
    team_run_stats: dict = {}

    for record in data.get("records", []):
        for tr in record.get("teamRecords", []):
            name = tr.get("team", {}).get("name", "")
            g = tr.get("gamesPlayed", 0)
            rs = tr.get("runsScored", 0)
            rd = tr.get("runDifferential", 0)
            if g > 0 and name:
                total_rs += rs
                total_g += g
                rd_pg = rd / g
                # Map run differential/game to 88-118 rating scale matching
                # the existing MLB_POWER_RATINGS in config.py (100 = average,
                # +1 RD/G ≈ +7 rating points). Capped to prevent outliers.
                rating = round(max(88.0, min(118.0, 100.0 + rd_pg * 7.0)), 1)
                team_ratings[name] = rating
                ra = rs - rd  # runs allowed = runs scored - run differential
                team_run_stats[name] = {"RS": round(rs / g, 3), "RA": round(ra / g, 3)}

    if len(team_ratings) < 25 or total_g == 0:
        print(f"[WARN] fetch_mlb_live_stats: only got {len(team_ratings)} teams — discarding")
        return {}

    avg_rs_pg = total_rs / total_g
    result = {
        "base_total": round(avg_rs_pg * 2, 2),
        "league_avg_rs": round(avg_rs_pg, 3),
        "team_ratings": team_ratings,
        "team_run_stats": team_run_stats,
    }
    _safe_save_pkl(cache_path, result)
    return result


def fetch_mlb_team_run_stats() -> dict:
    """
    Confirmed undefined (real NameError, silently caught) at its one
    call site in analyze_game_edge's James matchup formula. Thin wrapper
    around fetch_mlb_live_stats' real per-team RS/RA (runs scored/
    allowed per game) -- same live statsapi.mlb.com standings call
    already made for base_total/team_ratings, just also keeping the
    per-team runs breakdown instead of discarding it. No new API call.
    """
    live = fetch_mlb_live_stats()
    return live.get("team_run_stats", {})


def fetch_wnba_live_stats() -> dict:
    """
    Live WNBA season stats from ESPN standings API.
    Returns:
      { "base_total": float, "league_avg_pf": float,
        "team_ratings": {full_team_name: rating} on 95-120 scale }
    Rating formula: 106 + (point_differential_per_game * 2.0), capped 95-120.
    Center 106 matches the existing WNBA_POWER_RATINGS center in config.py.
    Cached 6 hours.
    """
    cache_path = os.path.join(CACHE_DIR, "wnba_live_stats.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            cached = _safe_load_pkl(cache_path)
            if cached and isinstance(cached.get("team_ratings"), dict) and len(cached["team_ratings"]) >= 10:
                return cached

    url = f"https://site.api.espn.com/apis/v2/sports/basketball/wnba/standings?season={_current_wnba_season_year()}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            print(f"[WARN] fetch_wnba_live_stats: HTTP {resp.status_code}")
            return {}
        data = resp.json()
    except Exception as e:
        print(f"[WARN] fetch_wnba_live_stats: {e}")
        return {}

    groups = data.get("children", data.get("groups", []))
    all_entries = []
    for g in groups:
        all_entries += g.get("standings", {}).get("entries", [])

    total_pf = 0.0
    n = 0
    team_ratings: dict = {}
    for entry in all_entries:
        name = entry.get("team", {}).get("displayName", "")
        stats = {s["name"]: s.get("value", s.get("displayValue")) for s in entry.get("stats", [])}
        try:
            pf = float(stats.get("avgPointsFor") or 0)
            pa = float(stats.get("avgPointsAgainst") or 0)
        except (TypeError, ValueError):
            continue
        if pf > 0 and name:
            diff = pf - pa
            total_pf += pf
            n += 1
            # Center at 106 to match existing WNBA_POWER_RATINGS scale in config.py
            rating = round(max(95.0, min(120.0, 106.0 + diff * 2.0)), 1)
            team_ratings[name] = rating

    if len(team_ratings) < 10 or n == 0:
        print(f"[WARN] fetch_wnba_live_stats: only got {len(team_ratings)} teams — discarding")
        return {}

    avg_pf = total_pf / n
    result = {
        "base_total": round(avg_pf * 2, 1),
        "league_avg_pf": round(avg_pf, 2),
        "team_ratings": team_ratings,
    }
    _safe_save_pkl(cache_path, result)
    return result


def fetch_nhl_live_stats() -> dict:
    """
    Live NHL season stats from api-web.nhle.com (official NHL public API).
    Returns:
      { "goals_for": {team_key: gf_per_game},
        "goals_against": {team_key: ga_per_game} }
    Each dict includes both the full team name and abbreviation as keys so
    the existing NHL_TEAM_GOALS_FOR/AGAINST lookup logic works unchanged.
    Cached 6 hours.
    """
    cache_path = os.path.join(CACHE_DIR, "nhl_live_stats.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            cached = _safe_load_pkl(cache_path)
            if cached and isinstance(cached.get("goals_for"), dict) and len(cached["goals_for"]) >= 20:
                return cached

    url = "https://api-web.nhle.com/v1/standings/now"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            print(f"[WARN] fetch_nhl_live_stats: HTTP {resp.status_code}")
            return {}
        data = resp.json()
    except Exception as e:
        print(f"[WARN] fetch_nhl_live_stats: {e}")
        return {}

    goals_for: dict = {}
    goals_against: dict = {}
    for rec in data.get("standings", []):
        full_name = rec.get("teamCommonName", {}).get("default", "")
        abbr = rec.get("teamAbbrev", {}).get("default", "")
        gp = rec.get("gamesPlayed", 0) or 0
        gf = rec.get("goalFor", 0) or 0
        ga = rec.get("goalAgainst", 0) or 0
        if gp > 10 and full_name:
            gf_pg = round(gf / gp, 3)
            ga_pg = round(ga / gp, 3)
            # Store under both full name and abbreviation for flexible lookup
            for key in (full_name, abbr):
                if key:
                    goals_for[key] = gf_pg
                    goals_against[key] = ga_pg

    if len(goals_for) < 20:
        print(f"[WARN] fetch_nhl_live_stats: only got {len(goals_for)//2} teams — discarding")
        return {}

    # Compute power ratings (88-115 scale) from goal differential per game.
    # Center at 105 to match existing NHL_POWER_RATINGS midpoint in config.py.
    # Formula: 105 + gd_pg * 5.0, where +1 GD/G ≈ +5 rating points.
    avg_gf_pg = sum(v for k, v in goals_for.items() if len(k) <= 3) / max(1, sum(1 for k in goals_for if len(k) <= 3))
    avg_ga_pg = sum(v for k, v in goals_against.items() if len(k) <= 3) / max(1, sum(1 for k in goals_against if len(k) <= 3))
    team_ratings: dict = {}
    for key in goals_for:
        gf_pg = goals_for[key]
        ga_pg = goals_against.get(key, avg_ga_pg)
        gd_pg = gf_pg - ga_pg
        rating = round(max(88.0, min(115.0, 105.0 + gd_pg * 5.0)), 1)
        team_ratings[key] = rating

    result = {
        "goals_for": goals_for,
        "goals_against": goals_against,
        "team_ratings": team_ratings,
        "base_total": round((avg_gf_pg + avg_ga_pg), 2),
    }
    _safe_save_pkl(cache_path, result)
    return result


def fetch_nba_live_stats() -> dict:
    """
    Live NBA season stats from ESPN standings API.
    Returns:
      { "base_total": float, "league_avg_pf": float,
        "team_ratings": {full_team_name: rating} on 90-125 scale }
    Rating formula: 105 + (point_differential_per_game * 1.0), capped 90-125.
    Center 105 approximates the existing NBA_POWER_RATINGS midpoint in bc_utils.py.
    Cached 6 hours.
    """
    cache_path = os.path.join(CACHE_DIR, "nba_live_stats.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            cached = _safe_load_pkl(cache_path)
            if cached and isinstance(cached.get("team_ratings"), dict) and len(cached["team_ratings"]) >= 25:
                return cached

    url = f"https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season={_current_nba_season_start_year() + 1}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            print(f"[WARN] fetch_nba_live_stats: HTTP {resp.status_code}")
            return {}
        data = resp.json()
    except Exception as e:
        print(f"[WARN] fetch_nba_live_stats: {e}")
        return {}

    groups = data.get("children", data.get("groups", []))
    all_entries = []
    for g in groups:
        all_entries += g.get("standings", {}).get("entries", [])

    total_pf = 0.0
    total_g = 0
    team_ratings: dict = {}
    for entry in all_entries:
        name = entry.get("team", {}).get("displayName", "")
        stats = {s["name"]: s.get("value", s.get("displayValue")) for s in entry.get("stats", [])}
        try:
            pf_total = float(stats.get("pointsFor") or 0)
            pa_total = float(stats.get("pointsAgainst") or 0)
            wins = float(stats.get("wins") or 0)
            losses = float(stats.get("losses") or 0)
        except (TypeError, ValueError):
            continue
        gp = wins + losses
        if gp > 0 and pf_total > 0 and name:
            pf_pg = pf_total / gp
            pa_pg = pa_total / gp
            diff = pf_pg - pa_pg
            total_pf += pf_total
            total_g += gp
            # Center at 105 to approximate existing NBA_POWER_RATINGS midpoint
            rating = round(max(90.0, min(125.0, 105.0 + diff * 1.0)), 1)
            team_ratings[name] = rating

    if len(team_ratings) < 25 or total_g == 0:
        print(f"[WARN] fetch_nba_live_stats: only got {len(team_ratings)} teams — discarding")
        return {}

    avg_pf_pg = total_pf / total_g
    result = {
        "base_total": round(avg_pf_pg * 2, 1),
        "league_avg_pf": round(avg_pf_pg, 2),
        "team_ratings": team_ratings,
    }
    _safe_save_pkl(cache_path, result)
    return result



def fetch_nfl_live_stats() -> dict:
    """
    Live NFL season stats from ESPN standings API (most recent completed season).
    Returns:
      { "base_total": float,        # league avg PF/G * 2 (both teams)
        "league_avg_pts": float,    # league avg PF/G per team
        "team_ratings": {key: rating},     # on 88-120 scale, center 104
        "scoring_stats": {key: {"pts_for_pg": x, "pts_against_pg": y}} }
    Keys include both abbreviation (e.g. "BUF") and full name for flexible lookup.
    Rating formula: 104 + diff_per_game * 1.5, capped 88-120.
    Center 104 matches the existing NFL power_adj center in analyze_game_edge.
    Cached 6 hours.
    """
    cache_path = os.path.join(CACHE_DIR, "nfl_live_stats.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            cached = _safe_load_pkl(cache_path)
            if cached and isinstance(cached.get("team_ratings"), dict) and len(cached["team_ratings"]) >= 28:
                return cached

    # Try current season first, fall back to previous completed season
    team_ratings: dict = {}
    scoring_stats: dict = {}
    total_pf = 0.0
    total_g = 0
    result_season = None

    import datetime as _dt
    current_year = _dt.date.today().year
    # NFL season overlaps two calendar years; use previous year before Sep
    if _dt.date.today().month < 9:
        current_year -= 1

    for season in (current_year, current_year - 1):
        url = f"https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season={season}"
        try:
            resp = _http.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            print(f"[WARN] fetch_nfl_live_stats season={season}: {e}")
            continue

        groups = data.get("children", data.get("groups", []))
        all_entries = []
        for g in groups:
            for sg in g.get("children", [g]):
                all_entries += sg.get("standings", {}).get("entries", [])

        if len(all_entries) < 28:
            continue

        for entry in all_entries:
            team = entry.get("team", {})
            name = team.get("displayName", "")
            abbr = team.get("abbreviation", "")
            stats = {s["name"]: s.get("value") for s in entry.get("stats", [])}
            try:
                wins   = float(stats.get("wins") or 0)
                losses = float(stats.get("losses") or 0)
                ties   = float(stats.get("ties") or 0)
                pf     = float(stats.get("pointsFor") or 0)
                pa     = float(stats.get("pointsAgainst") or 0)
            except (TypeError, ValueError):
                continue
            gp = wins + losses + ties
            if gp > 0 and pf > 0:
                pf_pg = pf / gp
                pa_pg = pa / gp
                diff   = pf_pg - pa_pg
                total_pf += pf
                total_g  += gp
                rating = round(max(88.0, min(120.0, 104.0 + diff * 1.5)), 1)
                scoring = {"pts_for_pg": round(pf_pg, 2), "pts_against_pg": round(pa_pg, 2)}
                for key in (abbr, name):
                    if key:
                        team_ratings[key] = rating
                        scoring_stats[key] = scoring

        if len(team_ratings) >= 28:
            result_season = season
            break

    if len(team_ratings) < 28 or total_g == 0:
        print(f"[WARN] fetch_nfl_live_stats: only {len(team_ratings)//2} teams — discarding")
        return {}

    avg_pts_pg = total_pf / total_g
    result = {
        "base_total":     round(avg_pts_pg * 2, 1),
        "league_avg_pts": round(avg_pts_pg, 2),
        "team_ratings":   team_ratings,
        "scoring_stats":  scoring_stats,
        "season":         result_season,
    }
    _safe_save_pkl(cache_path, result)
    return result


def fetch_nfl_team_scoring_stats() -> dict:
    """
    Per-team NFL scoring stats (pts_for_pg, pts_against_pg) keyed by
    abbreviation and full team name. Thin wrapper around fetch_nfl_live_stats.
    Called by the James matchup formula in analyze_game_edge.
    """
    live = fetch_nfl_live_stats()
    return live.get("scoring_stats", {})


def fetch_atsstats_nba_matchups() -> dict:
    """
    Confirmed undefined (real NameError, silently caught). Expected to
    return {team_name: {"l10_ou": (overs, unders)}} -- last-10-games
    over/under record per team. A real implementation needs either a
    full computation pipeline (real final scores cross-referenced
    against real closing totals, 10 games back per team) or a verified
    scrape of a real ATS source (covers.com confirmed reachable with
    real ATS content present, but safely parsing its actual page
    structure needs dedicated verification, not a guess, given this
    feeds a live betting-edge nudge). Clean stub -- the nudge this fed
    was already silently zero before (undefined function crashed
    into except), so this changes nothing functionally, just removes
    the crash risk.
    """
    return {}


def fetch_atsstats_mlb_matchups() -> dict:
    """See fetch_atsstats_nba_matchups -- same situation, same stub reasoning."""
    return {}


def fetch_atsstats_nhl_matchups() -> dict:
    """See fetch_atsstats_nba_matchups -- same situation, same stub reasoning."""
    return {}


def fetch_atsstats_nfl_matchups() -> dict:
    """See fetch_atsstats_nba_matchups -- same situation, same stub reasoning."""
    return {}


def fetch_nfl_practice_participation() -> dict:
    """
    Confirmed undefined (real NameError, silently caught) at one call
    site (already safely guarded with `if "fetch_x" in globals()`, so
    this fixes a real no-op, not a crash). No confirmed free source
    found for weekly practice-participation reports specifically --
    these are a separate feed from injury/inactive reports (which
    fetch_nfl_inactives now covers via nflverse) and weren't found in
    sportsdataverse's NFL wrapper. Clean stub rather than a guess.
    """
    return {}


def fetch_nfl_inactives() -> dict:
    """
    Confirmed undefined (real NameError, silently caught) at 2 call
    sites -- one already guarded (`if "fetch_nfl_inactives" in globals()`),
    one not (the QB-injury check inside analyze_game_edge). Real source:
    sdv_nfl_injuries() (sdv_source.py, wraps nflverse's load_nfl_injuries,
    a real deployed dependency confirmed in requirements.txt).

    NOTE: built defensively against common nflverse injury-report field
    names (team/recent_team, full_name/player_name, report_status) since
    the underlying sportsdataverse package is a heavy dependency that
    can't be easily test-run from a lightweight verification script --
    unlike this session's other fixes, the exact field names here were
    not confirmed against a live response. Worth a real check once NFL
    injury reports are actually populated in-season (preseason right now).
    Returns {team_name: [player_description, ...]} for players with an
    "Out" report status.
    """
    try:
        from sdv_source import sdv_nfl_injuries
        records = sdv_nfl_injuries(datetime.now().year)
    except Exception:
        return {}
    if not records:
        return {}
    out = {}
    for r in records:
        status = str(r.get("report_status", r.get("status", ""))).lower()
        if "out" not in status:
            continue
        team = r.get("team", r.get("recent_team", r.get("club_code", "")))
        name = r.get("full_name", r.get("player_name", r.get("name", "")))
        pos = r.get("position", r.get("pos", ""))
        if not team or not name:
            continue
        out.setdefault(team, []).append(f"{name} ({pos})" if pos else name)
    return out


def fetch_nfl_defensive_ratings() -> dict:
    """
    Confirmed undefined (real NameError, silently caught) at its call
    site in app_core.py, which wanted pass_yds_allowed_pg specifically --
    no free source for that exact stat was found after checking ESPN's
    team-statistics endpoint exhaustively (11 categories, confirmed it
    only exposes each team's own offense and defensive event counts,
    never yards allowed). Real, already-working alternative: this reuses
    fetch_nfl_team_scoring_stats' real pts_against_pg (points allowed
    per game) as the defensive-quality proxy instead -- points allowed
    is a legitimate, commonly-used defensive indicator, just a different
    stat than the caller originally wanted. The caller was updated to
    match (see analyze_game_edge's defensive-unit-adjustment block).
    """
    scoring = fetch_nfl_team_scoring_stats()
    return {team: {"pts_against_pg": stats.get("pts_against_pg")}
            for team, stats in scoring.items() if stats.get("pts_against_pg") is not None}


def fetch_pinnacle_game_lines(sport: str) -> list:
    """
    Pinnacle game lines via arcadia guest API (no auth).
    Workflow: matchups → participant map, then markets/straight → join on matchupId.
    Returns list of {Matchup, Home, Away, HomeML, AwayML, Spread, SpreadOdds,
                     Total, TotalOver, TotalUnder, Book, Sport, source}
    Cached 30 min.
    """
    league_id = _PINNACLE_LEAGUE_IDS.get(sport)
    if not league_id:
        return []

    cache_path = os.path.join(CACHE_DIR, f"pinnacle_arcadia_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    # Step 1: matchups → team + participant maps
    matchups_data = _pinnacle_arcadia_get(f"/leagues/{league_id}/matchups")
    if not matchups_data:
        return []

    matchup_teams = {}   # matchupId → {home, away}
    participant_map = {} # participantId → {matchupId, alignment}
    for mu in matchups_data:
        if mu.get("type") != "matchup":
            continue
        mid = mu.get("id")
        if not mid:
            continue
        home = away = ""
        for p in mu.get("participants", []):
            pid = p.get("id") or p.get("rotation")
            alignment = p.get("alignment", "")
            name = p.get("name", "")
            if alignment == "home":
                home = name
            elif alignment == "away":
                away = name
            if pid:
                participant_map[pid] = {"matchupId": mid, "alignment": alignment}
        matchup_teams[mid] = {"home": home, "away": away}

    # Step 2: markets/straight → flat price list
    markets_data = _pinnacle_arcadia_get(f"/leagues/{league_id}/markets/straight")
    if not markets_data:
        return []

    game_markets = {}  # matchupId → {moneyline, spread, total}
    for market in markets_data:
        mid    = market.get("matchupId")
        period = market.get("period", 0)
        mtype  = market.get("type", "")
        prices = market.get("prices", [])
        # Full-game (period=0), non-alternate main lines only
        if period != 0 or market.get("isAlternate") or not mid or mid not in matchup_teams:
            continue
        if mid not in game_markets:
            game_markets[mid] = {}

        # Arcadia prices use designation:'home'/'away'/'over'/'under' directly
        if mtype == "moneyline":
            ml = {}
            for p in prices:
                desig = p.get("designation", "")
                if desig == "home":
                    ml["home"] = _pinn_american(p.get("price"))
                elif desig == "away":
                    ml["away"] = _pinn_american(p.get("price"))
            if ml:
                game_markets[mid]["moneyline"] = ml

        elif mtype == "spread":
            sp = {}
            for p in prices:
                desig = p.get("designation", "")
                if desig == "home":
                    sp["hdp"]        = p.get("points")
                    sp["home_price"] = _pinn_american(p.get("price"))
                elif desig == "away":
                    sp["away_price"] = _pinn_american(p.get("price"))
            if sp:
                game_markets[mid]["spread"] = sp

        elif mtype == "total":
            tot = {}
            for p in prices:
                desig = p.get("designation", "")
                if desig == "over":
                    tot["points"]     = p.get("points")
                    tot["over_price"] = _pinn_american(p.get("price"))
                elif desig == "under":
                    tot["under_price"] = _pinn_american(p.get("price"))
            if tot:
                game_markets[mid]["total"] = tot

    # Step 3: assemble
    results = []
    for mid, teams in matchup_teams.items():
        home = teams.get("home", "")
        away = teams.get("away", "")
        if not home or not away:
            continue
        mkts = game_markets.get(mid, {})
        ml   = mkts.get("moneyline", {})
        sp   = mkts.get("spread", {})
        tot  = mkts.get("total", {})
        results.append({
            "Matchup":    f"{away} @ {home}",
            "Home":       home,
            "Away":       away,
            "HomeML":     ml.get("home"),
            "AwayML":     ml.get("away"),
            "Spread":     sp.get("hdp"),
            "SpreadOdds": sp.get("home_price"),
            "Total":      tot.get("points"),
            "TotalOver":  tot.get("over_price"),
            "TotalUnder": tot.get("under_price"),
            "Book":       "Pinnacle",
            "Sport":      sport,
            "source":     "pinnacle_lines",
        })

    if results:
        _safe_save_pkl(cache_path, results)
    return results


def _cache_pkl(path, data):
    try:
        import pickle
        with open(path, "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass


def _load_pkl(path, max_age_h=6):
    import os, time, pickle
    if not os.path.exists(path):
        return None
    if (time.time() - os.path.getmtime(path)) / 3600 > max_age_h:
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


# ── FanGraphs ─────────────────────────────────────────────────────────────────

def fetch_golf_scoreboard(tour: str = "pga") -> dict:
    """Fetch live golf leaderboard from ESPN hidden API."""
    import os
    cache_path = os.path.join(CACHE_DIR, f"golf_{tour}_scoreboard.pkl")
    cached = _load_pkl(cache_path, max_age_h=0.25)
    if cached is not None:
        return cached

    url = f"https://site.api.espn.com/apis/site/v2/sports/golf/{tour}/scoreboard"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code != 200:
            return {}
        data = r.json()
        _cache_pkl(cache_path, data)
        return data
    except Exception:
        return {}


def fetch_golf_player_stats(player_id: str, tour: str = "pga") -> dict:
    """
    Confirmed dead end (live-tested): no working public ESPN endpoint
    exists for individual golf player stats -- every pattern 404s. Returns
    {} immediately instead of burning a network round-trip per player that
    always fails.
    """
    return {}


def _fetch_golf_player_stats_DEAD_ENDPOINT(player_id: str, tour: str = "pga") -> dict:
    """
    Fetch golf player season stats from ESPN by name-to-ID resolution.

    player_id: player name string (e.g. "Scottie Scheffler").  Parameter name
               kept for caller compatibility in app.py — resolved internally
               to an ESPN numeric athlete ID via the athletes roster endpoint.
    tour:      "pga", "lpga", or "kft" (default "pga").
    Cached 12h per player+tour.
    """
    cache_key  = f"golf_player_{normalize_name(player_id)}_{tour}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 12:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    norm         = normalize_name(player_id)
    roster_data  = _espn_get(
        f"https://site.api.espn.com/apis/site/v2/sports/golf/{tour}/athletes?limit=500",
        f"golf_{tour}_roster", ttl_hours=24
    )
    if not roster_data:
        return {}

    match = next(
        (a for a in roster_data.get("athletes", [])
         if normalize_name(a.get("displayName", "")) == norm),
        None
    )
    if not match:
        return {}
    pid = match.get("id")
    if not pid:
        return {}

    stats_data = _espn_get(
        f"https://site.web.api.espn.com/apis/common/v3/sports/golf/{tour}/athletes/{pid}/stats",
        f"golf_{tour}_{pid}_stats", ttl_hours=6
    )
    if not stats_data:
        return {}

    stat_map = {}
    _cats = stats_data.get("categories") or stats_data.get("splits", {}).get("categories", [])
    for cat in _cats:
        for s in cat.get("stats", []):
            stat_map[s.get("name", "")] = s.get("value", 0)

    if not stat_map:
        return {}

    n_rounds = int(stat_map.get("roundsPlayed", stat_map.get("events", 20))) or 20
    result = {
        # Keys read by app.py _sg_net() and _stat_lookup
        "Birdies":    float(stat_map.get("birdies",
                            stat_map.get("birdieAverage",
                            stat_map.get("birdiePct", 3.8)))),
        "Bogeys":     float(stat_map.get("bogeys",
                            stat_map.get("bogeyAverage",
                            stat_map.get("bogeysAvg", 3.2)))),
        "Eagles":     float(stat_map.get("eagles",
                            stat_map.get("eagleAverage", 0.1))),
        "Strokes":    float(stat_map.get("scoringAverage",
                            stat_map.get("strokesGainedTotal", 71.5))),
        # Strokes gained — available where ESPN exposes SG data
        "SG_Total":   float(stat_map.get("strokesGainedTotal", 0)),
        "SG_Off_Tee": float(stat_map.get("strokesGainedOffTheTee", 0)),
        "SG_App":     float(stat_map.get("strokesGainedApproach", 0)),
        "SG_Putting": float(stat_map.get("strokesGainedPutting", 0)),
        "FIR%":       float(stat_map.get("fairwaysHitPercentage",
                            stat_map.get("fairwayPct", 60))),
        "GIR%":       float(stat_map.get("greensInRegulationPercentage",
                            stat_map.get("greenPct", 65))),
        "Putts":      float(stat_map.get("puttingAverage",
                            stat_map.get("puttsPerRound", 28))),
        # Metadata keys read by app.py live-data path
        "n_games":    n_rounds,
        "_tour":      tour.upper(),
        "_source":    "ESPN",
    }
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(result, f)
    except Exception:
        pass
    return result


# ── MMA / UFC ─────────────────────────────────────────────────────────────────

def _fetch_ufc_fighter_stats_DEAD_ENDPOINT(fighter_id: str) -> dict:
    """
    Fetch UFC fighter career stats from ESPN by name-to-ID resolution.

    fighter_id: fighter name string (e.g. "Jon Jones").  Parameter name
                kept for caller compatibility in app.py — resolved internally
                to an ESPN numeric athlete ID via the athletes roster endpoint.
    Cached 12h per fighter.
    """
    cache_key  = f"ufc_fighter_{normalize_name(fighter_id)}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 12:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    norm         = normalize_name(fighter_id)
    roster_data  = _espn_get(
        "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/athletes?limit=500",
        "ufc_roster", ttl_hours=24
    )
    if not roster_data:
        return {}

    match = next(
        (a for a in roster_data.get("athletes", [])
         if normalize_name(a.get("displayName", "")) == norm),
        None
    )
    if not match:
        return {}
    pid = match.get("id")
    if not pid:
        return {}

    stats_data = _espn_get(
        f"https://site.web.api.espn.com/apis/common/v3/sports/mma/ufc/athletes/{pid}/stats",
        f"ufc_{pid}_stats", ttl_hours=6
    )
    if not stats_data:
        return {}

    stat_map = {}
    _cats = stats_data.get("categories") or stats_data.get("splits", {}).get("categories", [])
    for cat in _cats:
        for s in cat.get("stats", []):
            stat_map[s.get("name", "")] = s.get("value", 0)

    if not stat_map:
        return {}

    wins   = int(stat_map.get("wins",   match.get("wins",   0)))
    losses = int(stat_map.get("losses", match.get("losses", 0)))
    result = {
        # Keys read by app.py _stat_lookup and spread edge math
        "SIG_STR":      float(stat_map.get("significantStrikes",
                              stat_map.get("sigStrikes",
                              stat_map.get("significantStrikesPerMinute", 35)))),
        "SIG_STR_ACC":  float(stat_map.get("significantStrikeAccuracy",
                              stat_map.get("sigStrikeAccuracy", 45))),
        "TAKEDOWNS":    float(stat_map.get("takedownAverage",
                              stat_map.get("takedowns",
                              stat_map.get("takedownsPerFight", 1.5)))),
        "TD_ACC":       float(stat_map.get("takedownAccuracy", 40)),
        "CONTROL_TIME": float(stat_map.get("controlTime",
                              stat_map.get("avgControlTime", 0))),
        "KD":           float(stat_map.get("knockdownAverage",
                              stat_map.get("knockdowns",
                              stat_map.get("knockdownsPerFight", 0.3)))),
        "SUB_AVG":      float(stat_map.get("submissionAverage",
                              stat_map.get("submissions", 0.5))),
        # Metadata keys read by app.py live-data path
        "n_games":      wins + losses or 10,
        "_record":      f"{wins}-{losses}",
        "_source":      "ESPN",
    }
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(result, f)
    except Exception:
        pass
    return result


# ── Soccer / MLS ──────────────────────────────────────────────────────────────

def _sbr_parse_html(html: str, sport: str, league_path: str = "") -> list:
    """Parse one SBR odds page HTML into a list of game dicts."""
    games = []
    try:
        _team_re  = re.compile(r'\[\*\*([A-Z]{2,4})\*\*\s*-?\s*([^\]]*)\]')
        _pct_re   = re.compile(r'(\d+)%')
        _open_re  = re.compile(r'^([+-]\d+)$', re.M)
        _book_re  = re.compile(
            r'\[([+-]\d+)([+-]\d+)\]\(https://c\.sportsbookreview\.com/([^)]+)\)'
        )
        _time_re  = re.compile(r'(\d+:\d+\s*[AP]M\s*[A-Z]{2,3})')
        blocks    = re.split(r'\d+:\d+\s*[AP]M\s*[A-Z]{2,3}', html)
        time_tags = _time_re.findall(html)
        # Derive league label from path for Soccer sub-leagues
        _league_label = {
            "major-league-soccer": "MLS", "english-premier-league": "EPL",
            "champions-league": "UCL", "la-liga": "LaLiga",
            "bundesliga": "Bundesliga", "serie-a": "SerieA", "ligue-1": "Ligue1",
        }.get(league_path, sport)
        for idx, block in enumerate(blocks[1:], 0):
            game_time = time_tags[idx] if idx < len(time_tags) else ""
            teams = _team_re.findall(block)
            if len(teams) < 2:
                continue
            away_abbr, away_info = teams[0][0], teams[0][1].strip()
            home_abbr, home_info = teams[1][0], teams[1][1].strip()
            pcts = _pct_re.findall(block)
            away_pct = int(pcts[0]) if len(pcts) > 0 else None
            home_pct = int(pcts[1]) if len(pcts) > 1 else None
            clean_for_open = re.sub(r'\[[^\]]+\]', '', block)
            opens = _open_re.findall(clean_for_open)
            away_open = int(opens[0]) if len(opens) > 0 else None
            home_open = int(opens[1]) if len(opens) > 1 else None
            book_hits = _book_re.findall(block)
            books_ml = {}
            for away_odds_str, home_odds_str, book_slug in book_hits:
                book_key = _SBR_BOOK_MAP.get(
                    book_slug.split("_")[0] + "_usa",
                    _SBR_BOOK_MAP.get(book_slug, book_slug.split("_")[0])
                )
                try:
                    books_ml[book_key] = {
                        "away_ml": int(away_odds_str),
                        "home_ml": int(home_odds_str) * (
                            -1 if int(home_odds_str) > 0 and away_odds_str.startswith("+") else 1
                        ),
                    }
                except (ValueError, TypeError):
                    pass
            best_away_ml = min(
                (v["away_ml"] for v in books_ml.values() if v.get("away_ml")),
                key=lambda x: abs(x), default=away_open
            ) if books_ml else away_open
            best_home_ml = min(
                (v["home_ml"] for v in books_ml.values() if v.get("home_ml")),
                key=lambda x: abs(x), default=home_open
            ) if books_ml else home_open
            games.append({
                "Home": home_abbr, "Away": away_abbr,
                "HomePitcher": home_info, "AwayPitcher": away_info,
                "GameTime": game_time, "Sport": sport, "League": _league_label,
                "HomeML": best_home_ml, "AwayML": best_away_ml,
                "HomeMLOpen": home_open, "AwayMLOpen": away_open,
                "PublicPctHome": home_pct, "PublicPctAway": away_pct,
                "Books": books_ml, "Source": "SBR",
                "Matchup": f"{away_abbr} @ {home_abbr}",
            })
    except Exception as e:
        print(f"[WARN] _sbr_parse_html({sport}/{league_path}): {e}")
    return games


_SBR_SPORT_PATHS = {
    "NFL": "nfl-football", "NBA": "nba-basketball", "MLB": "mlb-baseball",
    "NHL": "nhl-hockey", "WNBA": "wnba-basketball",
    "NCAAF": "ncaaf-football", "NCAAB": "ncaab-basketball", "CFL": "cfl-football",
}


def fetch_sbr_game_lines(sport: str) -> list:
    """
    Scrape SportsbookReview.com odds for all supported sports/leagues.

    Covers: NFL, MLB, NBA, NHL, WNBA, NCAAF, NCAAB, CFL, MLS/Soccer,
    EPL, Champions League, La Liga, Bundesliga, Serie A, Ligue 1.
    Soccer automatically fetches all 7 league paths in one call.

    Returns game dicts with per-book moneylines, opening lines, and
    public betting percentages (the only source in the stack with public
    money split data). Same shape as other game-line scrapers so it plugs
    directly into build_game_line_consensus().
    """
    _SOCCER_PATHS = [
        "major-league-soccer", "english-premier-league", "champions-league",
        "la-liga", "bundesliga", "serie-a", "ligue-1",
    ]
    paths = _SOCCER_PATHS if sport == "Soccer" else (
        [_SBR_SPORT_PATHS.get(sport)] if _SBR_SPORT_PATHS.get(sport) else []
    )
    if not paths or not paths[0]:
        return []

    cache_path = os.path.join(CACHE_DIR, f"sbr_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 0.25:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    all_games = []
    for path in paths:
        url = f"https://www.sportsbookreview.com/betting-odds/{path}/"
        try:
            resp = _http.get(
                url,
                headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                all_games.extend(_sbr_parse_html(resp.text, sport, path))
        except Exception as e:
            print(f"[WARN] fetch_sbr_game_lines({sport}/{path}): {e}")

    if all_games:
        _safe_save_pkl(cache_path, all_games)
    return all_games

_SPORTSLINE_SPORT_PATHS = {
    "NFL": "nfl", "NBA": "nba", "MLB": "mlb", "NHL": "nhl",
    "WNBA": "wnba", "Soccer": "soccer",
}


def fetch_sportsline_game_lines(sport: str) -> list:
    """
    Scrape SportsLine.com's odds comparison table (NFL/MLB/NBA/NHL/WNBA/Soccer).

    Returns a list of game dicts in the same shape as the other game-line
    fetchers (Home/Away/Spread/Total/HomeML/AwayML + per-book breakdown),
    including the consensus line, opening line, and line-movement flags --
    same format as fetch_pinnacle_game_lines/fetch_betrivers_game_lines so
    it plugs directly into build_game_line_consensus().

    SportsLine's table is rendered as plain text by the fetch stack (confirmed
    live -- no Cloudflare/JS-rendering issue, plain HTTP GET works). Columns:
      consensus | BetMGM | Caesars | DraftKings | FanDuel | Bet365

    This is the equivalent of having a free, no-auth line-shopping feed that
    also tracks opening lines, which your current scrapers don't provide in one
    place. The opening-line column enables line-movement / steam detection for
    every game on the board.
    """
    path = _SPORTSLINE_SPORT_PATHS.get(sport)
    if not path:
        return []

    cache_path = os.path.join(CACHE_DIR, f"sportsline_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 0.25:  # 15min cache
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    url = f"https://www.sportsline.com/{path}/odds/"
    try:
        resp = _http.get(url, headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"},
                         timeout=REQUEST_TIMEOUT)
        if resp.status_code == 403:
            _deny = resp.headers.get("x-deny-reason", "")
            if "allowlist" in _deny.lower() or "not in allowlist" in resp.text.lower():
                print(f"[WARN] fetch_sportsline_game_lines: www.sportsline.com not in Streamlit Cloud egress allowlist. "
                      f"Add it at Settings → Network in the Streamlit Cloud dashboard.")
            return []
        if resp.status_code != 200:
            return []
        html = resp.text
    except Exception as e:
        print(f"[WARN] fetch_sportsline_game_lines({sport}): {e}")
        return []

    games = []
    try:
        _team_re = re.compile(r'svg\)\s+([\w\' ]+?)\s*\|', re.S)
        _date_re = re.compile(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,\s+[\d:APMUTC ]+on\s+\w+'
        )

        rows = [r for r in html.split('\n') if r.strip().startswith('|')]
        current_game: dict = {}
        current_date: str = ""
        pending_away: dict = {}

        for row in rows:
            # Date/network row
            if _date_re.search(row) and row.count('|') <= 4:
                current_date = _date_re.search(row).group(0)
                continue

            # Team row
            tm = _team_re.search(row)
            if not tm:
                continue
            team_name = tm.group(1).strip()
            cols = [c.strip() for c in row.split('|')]
            if len(cols) < 6:
                continue

            sl_data = {
                "team":      team_name,
                "consensus": _sl_parse_col(cols[_SL_COL_CONSENSUS] if len(cols) > _SL_COL_CONSENSUS else ""),
                "betmgm":    _sl_parse_col(cols[_SL_COL_BETMGM]    if len(cols) > _SL_COL_BETMGM    else ""),
                "caesars":   _sl_parse_col(cols[_SL_COL_CAESARS]   if len(cols) > _SL_COL_CAESARS   else ""),
                "draftkings":_sl_parse_col(cols[_SL_COL_DK]        if len(cols) > _SL_COL_DK        else ""),
                "fanduel":   _sl_parse_col(cols[_SL_COL_FD]        if len(cols) > _SL_COL_FD        else ""),
                "bet365":    _sl_parse_col(cols[_SL_COL_BET365]    if len(cols) > _SL_COL_BET365    else ""),
            }

            if not pending_away:
                # First team in the pair = away
                pending_away = sl_data
                pending_away["date"] = current_date
            else:
                # Second team = home; build the game dict
                away_data = pending_away
                home_data = sl_data
                pending_away = {}

                # Consensus line from the away team row (always the underdog row
                # in SportsLine's layout when a favorite exists, but we just
                # use whichever has a line value).
                _cons_away = away_data.get("consensus")
                _cons_home = home_data.get("consensus")
                spread      = _cons_home["line"] if _cons_home else (
                              -_cons_away["line"] if _cons_away else None)
                open_spread = _cons_home["open"] if _cons_home else (
                              -_cons_away["open"] if _cons_away else None)
                line_moved  = (
                    spread is not None and open_spread is not None
                    and abs(spread - open_spread) >= 0.5
                )

                game = {
                    "Matchup":     f"{away_data['team']} @ {home_data['team']}",
                    "Home":        home_data["team"],
                    "Away":        away_data["team"],
                    "Date":        away_data.get("date", current_date),
                    "Sport":       sport,
                    "Spread":      spread,
                    "SpreadOpen":  open_spread,
                    "LineMoved":   line_moved,
                    "Source":      "SportsLine",
                    # Per-book spreads for build_game_line_consensus()
                    "Books": {
                        "consensus":  _cons_home,
                        "betmgm":     home_data.get("betmgm"),
                        "caesars":    home_data.get("caesars"),
                        "draftkings": home_data.get("draftkings"),
                        "fanduel":    home_data.get("fanduel"),
                        "bet365":     home_data.get("bet365"),
                    },
                    # Away-team book spreads for completeness
                    "AwayBooks": {
                        "consensus":  _cons_away,
                        "betmgm":     away_data.get("betmgm"),
                        "caesars":    away_data.get("caesars"),
                        "draftkings": away_data.get("draftkings"),
                        "fanduel":    away_data.get("fanduel"),
                        "bet365":     away_data.get("bet365"),
                    },
                }
                games.append(game)
    except Exception as e:
        print(f"[WARN] fetch_sportsline_game_lines({sport}) parse: {e}")
        return []

    if games:
        _safe_save_pkl(cache_path, games)
    return games


BOOKMAKER_SPORT_PATHS = {
    "NFL": "football", "NBA": "basketball", "MLB": "baseball",
    "NHL": "hockey", "WNBA": "basketball",
}


def fetch_bookmaker_game_lines(sport: str) -> list:
    """
    Fetch Bookmaker.eu game lines via lines.bookmaker.eu -- a separate
    public SEO subdomain from the CF/login-gated www.bookmaker.eu
    sportsbook. Confirmed live 2026-08-01 via GH Actions
    workflow_dispatch: 200 status, zero cookies sent, real server-
    rendered <table class='oddsTable'> in the response. No auth needed.

    Real row structure (confirmed from live HTML, not guessed):
      <tr id='vTeam_N'> (visitor) / <tr id='hTeam_N'> (home), each with
      <td id='vN_N'>/<td id='hN_N'>  -- team name (inside <a> text)
      <td id='vS_N'>/<td id='hS_N'>  -- run line / spread (uses unicode ½)
      <td id='vT_N'>/<td id='hT_N'>  -- total
      <td id='vM_N'>/<td id='hM_N'>  -- moneyline
    Cached 20 min.
    """
    sport_path = BOOKMAKER_SPORT_PATHS.get(sport)
    if not sport_path:
        return []

    cache_path = os.path.join(CACHE_DIR, f"bookmaker_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 20:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached

    try:
        url = f"https://lines.bookmaker.eu/en/sports/{sport_path}/"
        headers = {
            "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
        }
        r = _http.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"[WARN] fetch_bookmaker_game_lines HTTP {r.status_code}")
            return []

        html = r.text
        import re as _re

        def _cell(row_id_prefix, n):
            m = _re.search(
                rf"id='{row_id_prefix}_{n}'[^>]*>(?:<a[^>]*>)?([^<]+)",
                html)
            return m.group(1).strip() if m else ""

        def _frac_to_float(s):
            if not s:
                return None
            s = s.replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
            try:
                return float(s)
            except (TypeError, ValueError):
                return None

        results = []
        game_ids = sorted(set(int(m) for m in _re.findall(r"id='vTeam_(\d+)'", html)))
        for n in game_ids:
            away = _cell("vN", n)
            home = _cell("hN", n)
            if not away or not home:
                continue
            game = f"{away} @ {home}"
            away_sp = _cell("vS", n)
            home_sp = _cell("hS", n)
            away_tot = _cell("vT", n)
            home_tot = _cell("hT", n)
            away_ml = _cell("vM", n)
            home_ml = _cell("hM", n)

            for mkt, sel, val in [
                ("Moneyline", away, away_ml),
                ("Moneyline", home, home_ml),
                ("Spread", f"{away} {away_sp}", away_sp),
                ("Spread", f"{home} {home_sp}", home_sp),
                ("Total", f"Over {away_tot}", away_tot),
                ("Total", f"Under {home_tot}", home_tot),
            ]:
                if val:
                    results.append({"game": game, "home": home, "away": away,
                        "market": mkt, "selection": sel, "odds": val,
                        "book": "Bookmaker", "sport": sport, "source": "bookmaker"})

        if results:
            _safe_save_pkl(cache_path, results)
        return results

    except Exception as e:
        print(f"[WARN] fetch_bookmaker_game_lines: {e}")
        return []


# ── StatMuse ──────────────────────────────────────────────────────────────────
STATMUSE_SPORT_MAP = {"MLB":"mlb","NBA":"nba","NFL":"nfl","NHL":"nhl","WNBA":"wnba","TENNIS":"tennis","GOLF":"pga"}
STATMUSE_HEADERS = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    "Accept":"text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language":"en-US,en;q=0.9",
    "Referer":"https://www.statmuse.com/",
}

def _sm_url(query, sport):
    import re as _r
    s=_r.sub(r"[^a-z0-9\s-]","",query.lower().replace("'","").replace(".","")).replace(" ","-")
    return f"https://www.statmuse.com/{STATMUSE_SPORT_MAP.get(sport,'mlb')}/ask/{_r.sub(r'-+','-',s).strip('-')}"

def _sm_parse(html):
    import re as _r
    out={"text":"","stats":[]}
    try:
        m=_r.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',html,_r.S)
        if m:
            p=json.loads(m.group(1)).get("props",{}).get("pageProps",{})
            a=p.get("answer",p.get("card",{}))
            if isinstance(a,dict):
                out["text"]=a.get("summary",a.get("text",a.get("sentence","")))
                out["stats"]=a.get("rows",a.get("data",a.get("stats",[])))[:20]
            elif isinstance(a,str): out["text"]=a
        if not out["text"]:
            out["text"]=_r.sub(r"\s+"," ",_r.sub(r"<[^>]+>"," ",html)).strip()[:300]
    except Exception as e: out["error"]=str(e)
    return out

def fetch_statmuse_player(player_name, stat_query, sport="MLB"):
    """StatMuse player stat query. Free/no auth. Cached 2h."""
    import re as _r
    cp=os.path.join(CACHE_DIR,f"statmuse_{_r.sub(r'[^a-z0-9]','_',player_name.lower())[:20]}_{_r.sub(r'[^a-z0-9]','_',stat_query.lower())[:20]}.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/3600<2:
        c=_safe_load_pkl(cp)
        if c: c["cached"]=True; return c
    try:
        r=_http.get(_sm_url(f"{player_name} {stat_query}",sport),headers=STATMUSE_HEADERS,timeout=15)
        if r.status_code!=200: return {"error":f"HTTP {r.status_code}","source":"statmuse","text":""}
        out=_sm_parse(r.text)
        out.update({"source":"statmuse","player":player_name,"stat":stat_query,"sport":sport,"cached":False})
        if out.get("text") or out.get("stats"): _safe_save_pkl(cp,out)
        return out
    except Exception as e:
        print(f"[WARN] fetch_statmuse_player: {e}"); return {"error":str(e),"source":"statmuse","text":""}

def fetch_statmuse_league_leaders(sport, stat, n=10):
    """League leaders for a stat. Cached 6h."""
    import re as _r
    cp=os.path.join(CACHE_DIR,f"statmuse_lead_{sport}_{_r.sub(r'[^a-z0-9]','_',stat.lower())[:20]}.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/3600<6:
        c=_safe_load_pkl(cp); return c if c else []
    try:
        r=_http.get(_sm_url(f"leaders in {stat}",sport),headers=STATMUSE_HEADERS,timeout=15)
        if r.status_code!=200: return []
        leaders=_sm_parse(r.text).get("stats",[])[:n]
        if leaders: _safe_save_pkl(cp,leaders)
        return leaders
    except Exception as e:
        print(f"[WARN] fetch_statmuse_league_leaders: {e}"); return []



# ── FantasyPros Consensus Projections ─────────────────────────────────────────
FANTASYPROS_URLS = {
    "NBA":{"all":"https://www.fantasypros.com/nba/projections/players.php"},
    "MLB":{"hitters":"https://www.fantasypros.com/mlb/projections/hitters.php",
           "pitchers":"https://www.fantasypros.com/mlb/projections/pitchers.php"},
    "NFL":{"qb":"https://www.fantasypros.com/nfl/projections/qb.php",
           "rb":"https://www.fantasypros.com/nfl/projections/rb.php",
           "wr":"https://www.fantasypros.com/nfl/projections/wr.php",
           "te":"https://www.fantasypros.com/nfl/projections/te.php"},
    "NHL":{"all":"https://www.fantasypros.com/nhl/projections/players.php"},
}
FP_HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Accept":"text/html,*/*","Referer":"https://www.fantasypros.com/"}

def fetch_fantasypros_projections(sport: str) -> dict:
    """FantasyPros expert consensus projections. Free, no auth. Cached 3h."""
    cp = os.path.join(CACHE_DIR, f"fantasypros_{sport}.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/3600 < 3:
        c = _safe_load_pkl(cp)
        if c: return c
    urls = FANTASYPROS_URLS.get(sport, {})
    if not urls: return {}
    all_proj = {}
    import re as _re
    for position, url in urls.items():
        try:
            r = _http.get(url, headers=FP_HEADERS, timeout=15)
            if r.status_code != 200: continue
            html = r.text
            m = _re.search(r'var ecrData\s*=\s*(\{.*?\});', html, _re.S)
            if m:
                try:
                    for p in json.loads(m.group(1)).get("players",[]):
                        nm = p.get("player_name","")
                        if not nm: continue
                        stats = {k:float(v) for k,v in p.items()
                                 if k not in ("player_name","player_id","rank","team","pos")
                                 and isinstance(v,(int,float))}
                        if stats: all_proj[normalize_name(nm)] = {"name":nm,"pos":position,"projections":stats,"source":"fantasypros"}
                    time.sleep(0.2); continue
                except Exception: pass
            tm = _re.search(r'<table[^>]*id="data"[^>]*>(.*?)</table>', html, _re.S|_re.I)
            if not tm: time.sleep(0.2); continue
            hdrs = [_re.sub(r'<[^>]+>','',h).strip().lower()
                    for h in _re.findall(r'<th[^>]*>(.*?)</th>', tm.group(1), _re.S|_re.I)]
            for row in _re.findall(r'<tr[^>]*>(.*?)</tr>', tm.group(1), _re.S|_re.I):
                cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.S|_re.I)
                if len(cells) < 2: continue
                nm = _re.sub(r'<[^>]+>','',cells[0]).strip()
                if not nm or nm.lower() == 'player': continue
                stats = {}
                for j,col in enumerate(hdrs[1:],1):
                    if j < len(cells):
                        try: stats[col] = float(_re.sub(r'<[^>]+>','',cells[j]).strip())
                        except Exception: pass
                if stats: all_proj[normalize_name(nm)] = {"name":nm,"pos":position,"projections":stats,"source":"fantasypros"}
            time.sleep(0.3)
        except Exception as e:
            print(f"[WARN] fantasypros {sport}/{position}: {e}")
    if all_proj: _safe_save_pkl(cp, all_proj)
    return all_proj


# ── Closing Line Auto-Capture Database ───────────────────────────────────────
def save_closing_line(player, prop, line, sport, over_odds=None, under_odds=None, source="pinnacle"):
    """Auto-save closing line to Gist. Called from enrichment loop."""
    try:
        key = f"{normalize_name(player)}_{prop.lower().replace(' ','_')}_{date.today().isoformat()}"
        db = _read_gist_file("betcouncil_closing_lines.json", cache_minutes=0)
        db[key] = {"player":player,"prop":prop,"line":line,"sport":sport,
                   "over_odds":over_odds,"under_odds":under_odds,"source":source,
                   "timestamp":datetime.now().isoformat()}
        if len(db) > 500:
            for k in sorted(db, key=lambda x: db[x].get("timestamp",""))[:len(db)-500]: del db[k]
        upd = urllib.request.Request(f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            data=json.dumps({"files":{"betcouncil_closing_lines.json":{"content":json.dumps(db,indent=2)}}}).encode(),
            method="PATCH",
            headers={"Authorization":f"token {GITHUB_TOKEN}","Accept":"application/vnd.github.v3+json","Content-Type":"application/json"})
        with urllib.request.urlopen(upd, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"[WARN] save_closing_line: {e}"); return False

def load_closing_line(player, prop, date_str=None):
    """Load closing line from Gist database."""
    try:
        if date_str is None: date_str = date.today().isoformat()
        key = f"{normalize_name(player)}_{prop.lower().replace(' ','_')}_{date_str}"
        db = _read_gist_file("betcouncil_closing_lines.json", cache_minutes=10)
        return db.get(key, {})
    except Exception as e:
        print(f"[WARN] load_closing_line: {e}"); return {}

def fetch_all_closing_lines():
    """Load full closing line DB from Gist. Cached 10 min."""
    try:
        return _read_gist_file("betcouncil_closing_lines.json", cache_minutes=10)
    except Exception as e:
        print(f"[WARN] fetch_all_closing_lines: {e}"); return {}


# ── Opponent Defense Rankings — All Sports ────────────────────────────────────
ESPN_DEFENSE_URLS = {
    "NBA":  "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams?limit=30&enable=stats",
    "MLB":  "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams?limit=30&enable=stats",
    "NFL":  "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams?limit=32&enable=stats",
    "NHL":  "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams?limit=32&enable=stats",
    "WNBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams?limit=14&enable=stats",
}
ESPN_DEF_HEADERS = {"User-Agent":"Mozilla/5.0","Accept":"application/json","Referer":"https://www.espn.com/"}

def fetch_opponent_defense_rankings(sport: str) -> dict:
    """Opponent defense rankings from ESPN public API. All sports. Cached 6h."""
    cp = os.path.join(CACHE_DIR, f"defense_rankings_{sport}.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/3600 < 6:
        c = _safe_load_pkl(cp)
        if c: return c
    url = ESPN_DEFENSE_URLS.get(sport)
    if not url: return {}
    try:
        r = _http.get(url, headers=ESPN_DEF_HEADERS, timeout=12)
        if r.status_code != 200: return {}
        data  = r.json()
        teams = data.get("sports",[{}])[0].get("leagues",[{}])[0].get("teams",[]) if "sports" in data else data.get("teams",[])
        rankings = {}; raw = []
        for te in teams:
            t    = te.get("team", te)
            abbr = t.get("abbreviation","")
            name = t.get("displayName","")
            smap = {}
            for sg in t.get("stats",{}).get("splits",[]):
                for s in sg.get("stats",[]):
                    if s.get("value") is not None:
                        smap[s.get("name","").lower()] = float(s["value"])
            pa = None
            if sport=="NBA":    pa=smap.get("pointsagainst",smap.get("opppts"))
            elif sport=="MLB":  pa=smap.get("era",smap.get("earnedrunavg"))
            elif sport=="NFL":  pa=smap.get("pointsagainst",smap.get("totalyardsagainst"))
            elif sport=="NHL":  pa=smap.get("goalsagainst",smap.get("goalsagainstpergame"))
            elif sport=="WNBA": pa=smap.get("pointsagainst",smap.get("opppts"))
            if abbr and pa is not None:
                rankings[abbr]={"name":name,"pts_allowed":pa,"sport":sport}
                raw.append((abbr,pa))
        raw.sort(key=lambda x: x[1], reverse=True)
        n=len(raw)
        for rank,(abbr,_) in enumerate(raw,1):
            if abbr in rankings:
                rankings[abbr]["rank"]      = rank
                rankings[abbr]["percentile"]= round((rank-1)/max(n-1,1),3)
                rankings[abbr]["favorable"] = rank <= n//3
        if rankings: _safe_save_pkl(cp, rankings)
        return rankings
    except Exception as e:
        print(f"[WARN] fetch_opponent_defense_rankings({sport}): {e}"); return {}

def get_defense_edge(opponent_team: str, sport: str, rankings: dict = None) -> dict:
    """Get defensive edge multiplier for a prop matchup."""
    if rankings is None: rankings = fetch_opponent_defense_rankings(sport)
    if not rankings: return {"favorable":None,"rank":None,"note":"No data","edge_adj":1.0}
    t = str(opponent_team).upper().strip()
    d = rankings.get(t)
    if not d:
        for abbr,data in rankings.items():
            if t in data.get("name","").upper() or abbr in t: d=data; break
    if not d: return {"favorable":None,"rank":None,"note":f"{opponent_team} not found","edge_adj":1.0}
    rank=d.get("rank",0); pct=d.get("percentile",0.5); n=len(rankings)
    if pct<=0.25:   adj,note=1.08,f"🎯 Weak defense (#{rank}/{n})"
    elif pct<=0.50: adj,note=1.03,f"📊 Below-avg defense (#{rank}/{n})"
    elif pct<=0.75: adj,note=0.97,f"📊 Above-avg defense (#{rank}/{n})"
    else:           adj,note=0.92,f"🛡️ Elite defense (#{rank}/{n})"
    return {"favorable":d.get("favorable",False),"rank":rank,"n_teams":n,
            "percentile":pct,"note":note,"edge_adj":adj,"sport":sport}



# ── Signal Odds — Free AI predictions + 60+ book best odds ───────────────────
SIGNALODDS_SLUGS = {
    "MLB":"baseball-mlb","NBA":"basketball-nba","NFL":"american-football-nfl",
    "NHL":"ice-hockey-nhl","WNBA":"basketball-wnba","UFC":"mixed-martial-arts-ufc",
}
SIGNALODDS_HEADERS = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    "Accept":"text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language":"en-US,en;q=0.9",
    "Referer":"https://signalodds.com/",
}

def _so_dec_to_amer(dec):
    try:
        if dec >= 2.0: return int((dec-1)*100)
        else:          return int(-100/(dec-1))
    except Exception: return 0

def fetch_signalodds_events(sport: str) -> list:
    """
    Signal Odds: today's events with best odds from 60+ bookmakers + sure bet flags.
    Parses initialEvents JSON from Next.js page (HTML or RSC wire format).
    Free, no auth. Cached 20 min.
    """
    slug = SIGNALODDS_SLUGS.get(sport)
    if not slug: return []
    cp = os.path.join(CACHE_DIR, f"signalodds_{sport}.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/60 < 20:
        c = _safe_load_pkl(cp)
        if c is not None: return c
    try:
        r = _http.get(f"https://signalodds.com/leagues/{slug}",
                      headers=SIGNALODDS_HEADERS, timeout=20)
        if r.status_code != 200: return []
        html = r.text
        # Try __NEXT_DATA__ first
        events_raw = []
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if m:
            try:
                events_raw = json.loads(m.group(1)).get("props",{}).get("pageProps",{}).get("initialEvents",[])
            except Exception: pass
        # RSC wire format fallback
        if not events_raw:
            m2 = re.search(r'"initialEvents":(\[.*?\]),"initialTotalEvents"', html, re.S)
            if m2:
                try: events_raw = json.loads(m2.group(1))
                except Exception: pass
        results = []
        for ev in events_raw:
            home = ev.get("home_team",{}).get("full_name","")
            away = ev.get("away_team",{}).get("full_name","")
            if not home or not away: continue
            # Parse best_odds
            bods = {}
            for bo in ev.get("best_odds",[]):
                outcome = bo.get("outcome_name","")
                dec     = bo.get("odds",1.0)
                if outcome not in bods or dec > bods[outcome]["dec"]:
                    bods[outcome] = {"book":bo.get("bookmaker_name",""),"dec":dec,
                                     "american":_so_dec_to_amer(dec)}
            sure = ev.get("sure_bet_count",0) or 0
            results.append({
                "game":f"{away} @ {home}","home":home,"away":away,"sport":sport,
                "commence_time":ev.get("commence_time",""),
                "sure_bet_count":sure,"prediction_count":ev.get("prediction_count",0) or 0,
                "odds_api_key":ev.get("odds_api_key",""),
                "best_odds":bods,
                "home_ml":bods.get(home,{}).get("american"),
                "away_ml":bods.get(away,{}).get("american"),
                "best_book_home":bods.get(home,{}).get("book",""),
                "best_book_away":bods.get(away,{}).get("book",""),
                "has_sure_bet":sure > 0,
                "source":"signalodds","slug":ev.get("slug",""),
            })
        if results: _safe_save_pkl(cp, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_signalodds_events({sport}): {e}"); return []



# ── BetsLib / Signal Odds API ─────────────────────────────────────────────────
# api.betslib.com — Signal Odds backend
# Auth: SIGNAL_ODDS_JWT in Streamlit secrets (expires ~Aug 27 2026)
# Refresh: log into signalodds.com → DevTools → find api.betslib.com request → copy Bearer token
BETSLIB_BASE     = "https://api.betslib.com"
BETSLIB_SPORT_MAP = {
    "MLB":"baseball","NBA":"basketball","NFL":"american-football",
    "NHL":"hockey","WNBA":"basketball","UFC":"mma","SOCCER":"soccer",
    "TENNIS":"tennis",
}

def _betslib_jwt():
    try:
        import streamlit as st
        return st.secrets.get("SIGNAL_ODDS_JWT","")
    except Exception:
        return ""

def fetch_betslib_predictions(sport: str, limit: int = 20) -> list:
    """
    Signal Odds AI predictions via api.betslib.com.
    Returns {event,home,away,sport,market,pick,confidence,ev,odds,bookmaker,model,source}
    Auth: SIGNAL_ODDS_JWT. Cached 30 min.
    """
    slug = BETSLIB_SPORT_MAP.get(sport)
    if not slug: return []
    cp = os.path.join(CACHE_DIR, f"betslib_{sport}.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/60 < 30:
        c = _safe_load_pkl(cp)
        if c is not None: return c
    jwt = _betslib_jwt() or None
    try:
        hdrs = {
            "Accept":        "application/json, text/plain, */*",
            "Origin":        "https://signalodds.com",
            "Referer":       "https://signalodds.com/",
            "x-client-source": "web",
            "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        if jwt:
            hdrs["Authorization"] = f"Bearer {jwt}"
        url = f"{BETSLIB_BASE}/predictions?date_filter=upcoming&limit={limit}&page=1&sort_by=commence_time&sort_dir=asc&sport={slug}"
        r   = _http.get(url, headers=hdrs, timeout=15)
        if r.status_code == 401 and jwt:
            hdrs.pop("Authorization", None)
            r = _http.get(url, headers=hdrs, timeout=15)
        if r.status_code == 401:
            print("[WARN] betslib: 401 even anonymous — endpoint now requires auth"); return []
        if r.status_code != 200:
            print(f"[WARN] betslib HTTP {r.status_code}"); return []
        raw  = r.json()
        preds = raw if isinstance(raw,list) else raw.get("data", raw.get("predictions", raw.get("results",[])))
        if isinstance(preds, dict):
            preds = preds.get("items", preds.get("predictions", preds.get("results", [])))
        if not isinstance(preds, list):
            preds = []
        results = []
        for p in preds:
            ev_obj  = p.get("event", p.get("match", p.get("game",{})))
            home    = ev_obj.get("home_team", p.get("home_team",""))
            away    = ev_obj.get("away_team", p.get("away_team",""))
            if isinstance(home,dict): home = home.get("name", home.get("full_name",""))
            if isinstance(away,dict): away = away.get("name", away.get("full_name",""))
            model   = p.get("model", p.get("model_name",""))
            if isinstance(model,dict): model = model.get("name","")
            results.append({
                "event":        f"{away} @ {home}" if home and away else p.get("event_name",""),
                "home":home,"away":away,"sport":sport,
                "market":       p.get("market", p.get("market_key","h2h")),
                "pick":         p.get("pick", p.get("prediction", p.get("outcome",""))),
                "confidence":   float(p.get("confidence", p.get("probability",0)) or 0),
                "ev":           float(p.get("expected_value", p.get("ev",0)) or 0),
                "odds":         p.get("odds", p.get("best_odds", p.get("price",0))),
                "bookmaker":    p.get("bookmaker", p.get("bookie","")),
                "commence_time":ev_obj.get("commence_time","") or p.get("commence_time",""),
                "model":model,"source":"signalodds",
            })
        if results: _safe_save_pkl(cp, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_betslib_predictions({sport}): {e}"); return []

def fetch_betslib_models() -> list:
    """Signal Odds model leaderboard. Cached 6h."""
    cp = os.path.join(CACHE_DIR, "betslib_models.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/3600 < 6:
        c = _safe_load_pkl(cp)
        if c is not None: return c
    jwt = _betslib_jwt()
    if not jwt: return []
    try:
        hdrs = {"Authorization":f"Bearer {jwt}","Accept":"application/json",
                "Origin":"https://signalodds.com","x-client-source":"web"}
        r = _http.get(f"{BETSLIB_BASE}/models?limit=100&sort_by=name&sort_dir=asc",
                      headers=hdrs, timeout=10)
        if r.status_code != 200: return []
        raw  = r.json()
        mods = raw if isinstance(raw,list) else raw.get("data", raw.get("models",[]))
        results = [{"name":m.get("name",m.get("model_name","")),
                    "accuracy_30d":m.get("accuracy_30d",m.get("accuracy",0)),
                    "total_predictions":m.get("total_predictions",m.get("count",0)),
                    "sport":m.get("sport",""),"roi":m.get("roi",0),"source":"signalodds"}
                   for m in mods]
        if results: _safe_save_pkl(cp, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_betslib_models: {e}"); return []


def fetch_signalodds_arbitrage_from_gist(max_age_minutes: int = 100) -> list:
    """
    Signal Odds cross-book arbitrage (real guaranteed-profit spreads across
    60+ bookmakers -- confirmed live 2026-07-25: real entries seen include
    Betfair/Coolbet/BetOnline.ag/Smarkets with actual computed stake sizing).

    Distinct from fetch_betslib_predictions() above -- that one calls
    api.betslib.com live from inside this app using SIGNAL_ODDS_JWT in
    Streamlit secrets. This one instead reads scripts/signalodds_refresh.py's
    output from the Gist (GitHub Actions, cron 10,40 * * * *, its own
    SIGNAL_ODDS_JWT copy in repo secrets) -- game-level arbitrage has no
    other consumer in this app, unlike predictions which already has the
    live path above.

    Each item: {sport, league, home_team, away_team, commence_time,
    market_key, market_name, margin_percent, freshness_status, expires_at,
    legs: [{bookmaker, outcome, odds, stake_pct}], locked}
    """
    data = _read_gist_file("betcouncil_signalodds_opportunities.json", cache_minutes=10)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("opportunities", [])
        if isinstance(raw, list):
            return raw
    return []


def fetch_kalshi_from_gist(sport: str = None, max_age_minutes: int = 100) -> list:
    """
    Kalshi prediction-market prices (real bid/ask, volume, open interest --
    confirmed live 2026-07-25: 72 MLB events/117 markets across game/total/
    spread series, plus NFL game markets, no auth needed for reading).

    Distinct from the existing indirect Kalshi exposure buried inside
    fetch_ev_api()'s multi-book aggregation -- this is a direct connection
    (scripts/kalshi_refresh.py, GitHub Actions cron 5,35 * * * *) giving the
    FULL picture per game rather than one blended number: every run-total
    threshold priced separately (e.g. 1.5/2.5/3.5/4.5 runs each with their
    own live yes/no price), which is what lets a caller reconstruct Kalshi's
    implied probability distribution over the total rather than a single
    line.

    Each event: {sport, event_ticker, title, series_ticker, markets: [
    {ticker, title, yes_bid, yes_ask, last_price, volume, open_interest,
    liquidity, close_time, rules_primary}]}. Pass sport="MLB" or "NFL" to
    filter; omit for everything.
    """
    data = _read_gist_file("betcouncil_kalshi_markets.json", cache_minutes=10)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("events", [])
        if isinstance(raw, list):
            if sport:
                return [e for e in raw if e.get("sport") == sport]
            return raw
    return []



def fetch_betslib_events(sport: str = None, category: str = "upcoming", limit: int = 50) -> list:
    """
    BetsLib public events endpoint — NO AUTH REQUIRED.
    category: "upcoming" | "live" | "finished"
    Returns list of {game, home, away, sport, commence_time, status,
                     best_odds, sure_bet_count, prediction_count, source}
    Cached 5 min for live, 20 min for upcoming.
    """
    sport_slug = BETSLIB_SPORT_MAP.get(sport) if sport else None
    cache_key  = f"betslib_events_{sport or 'all'}_{category}"
    cp         = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    ttl        = 5 if category == "live" else 20
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/60 < ttl:
        c = _safe_load_pkl(cp)
        if c is not None: return c
    try:
        hdrs = {
            "Accept":          "application/json, text/plain, */*",
            "Origin":          "https://signalodds.com",
            "Referer":         "https://signalodds.com/",
            "x-client-source": "web",
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        url = f"{BETSLIB_BASE}/events?limit={limit}&sort_by=commence_time&category={category}"
        if sport_slug:
            url += f"&sport={sport_slug}"
        r = _http.get(url, headers=hdrs, timeout=15)
        if r.status_code != 200:
            print(f"[WARN] fetch_betslib_events HTTP {r.status_code}"); return []
        raw   = r.json()
        items = raw if isinstance(raw, list) else raw.get("data", raw.get("events", raw.get("results", [])))
        results = []
        for ev in items:
            home = ev.get("home_team", ev.get("home", {}))
            away = ev.get("away_team", ev.get("away", {}))
            if isinstance(home, dict): home = home.get("name", home.get("full_name", ""))
            if isinstance(away, dict): away = away.get("name", away.get("full_name", ""))
            if not home and not away: continue
            # Parse best odds
            bods = {}
            for bo in ev.get("best_odds", ev.get("odds", [])):
                outcome = bo.get("outcome_name", bo.get("outcome", ""))
                dec     = float(bo.get("odds", bo.get("price", 1.0)) or 1.0)
                book    = bo.get("bookmaker_name", bo.get("bookmaker", bo.get("book", "")))
                if outcome not in bods or dec > bods[outcome]["dec"]:
                    try:
                        amer = int((dec-1)*100) if dec >= 2.0 else int(-100/(dec-1))
                    except Exception:
                        amer = 0
                    bods[outcome] = {"book":book,"dec":dec,"american":amer}
            results.append({
                "game":             f"{away} @ {home}",
                "home":             home,
                "away":             away,
                "sport":            ev.get("sport", ev.get("sport_key", sport or "")),
                "commence_time":    ev.get("commence_time", ev.get("start_time", "")),
                "status":           ev.get("status", category),
                "best_odds":        bods,
                "home_ml":          bods.get(home, {}).get("american"),
                "away_ml":          bods.get(away, {}).get("american"),
                "best_book_home":   bods.get(home, {}).get("book", ""),
                "best_book_away":   bods.get(away, {}).get("book", ""),
                "sure_bet_count":   ev.get("sure_bet_count", 0) or 0,
                "prediction_count": ev.get("prediction_count", 0) or 0,
                "has_sure_bet":     (ev.get("sure_bet_count", 0) or 0) > 0,
                "is_live":          category == "live" or ev.get("status","") == "live",
                "league":           ev.get("league", ev.get("competition", {}) or {}).get("name","") if isinstance(ev.get("league",{}),dict) else ev.get("league",""),
                "source":           "betslib",
                "raw_id":           ev.get("id",""),
            })
        if results: _safe_save_pkl(cp, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_betslib_events({sport},{category}): {e}"); return []


def fetch_betslib_live_events(sport: str = None) -> list:
    """Live events from BetsLib — public, no auth. Cached 5 min."""
    return fetch_betslib_events(sport=sport, category="live", limit=50)


def _amer_to_prob(odds):
    try:
        o=float(odds)
        return 100.0/(o+100.0) if o>0 else (-o)/((-o)+100.0)
    except Exception: return 0.5






def _parse_scanbet_drop(d: dict, ts: str) -> list:
    """Parse a single scanbet drop event into BetCouncil format."""
    results = []
    try:
        game   = d.get("eventName", d.get("event_name", d.get("name","")))
        sport  = d.get("sport", d.get("sportName",""))
        market = d.get("market", d.get("marketName",""))
        # Handle nested movements
        movements = d.get("movements", d.get("odds", [d] if "oldOdds" in d or "old_odds" in d else []))
        for m in (movements if isinstance(movements,list) else [movements]):
            old_odds = m.get("oldOdds", m.get("old_odds", m.get("openOdds")))
            new_odds = m.get("newOdds", m.get("new_odds", m.get("currentOdds")))
            if old_odds and new_odds:
                try:
                    def to_prob(o):
                        o=float(o)
                        return 100/(o+100) if o>0 else -o/(-o+100)
                    dp = to_prob(new_odds) - to_prob(old_odds)
                    results.append({
                        "game":      game,
                        "sport":     sport,
                        "market":    market,
                        "selection": m.get("selection", m.get("name","")),
                        "old_odds":  old_odds,
                        "new_odds":  new_odds,
                        "drop_pct":  round(dp,4),
                        "is_steam":  dp > 0,
                        "timestamp": ts,
                        "source":    "scanbet_bookmarklet",
                    })
                except Exception: pass
    except Exception: pass
    return results



# ── Scanbet GraphQL — Pinnacle Line Movement History ─────────────────────────
# GraphQL endpoint: POST https://scanbet.io/graphql
# Blocked from datacenter — must be called from browser (bookmarklet) or local machine
# Data pushed to Gist file: betcouncil_scanbet_drops.json
# Bookmarklet runs the query and pushes result to Gist automatically

# Filter IDs for each sport/league (from URL: scanbet.io/pinnacle/sports?filter=XXX)
SCANBET_FILTER_IDS = {
    "MLB":    "f3e9a7ebfb522115",  # confirmed working
    "NFL":    None,  # navigate to scanbet.io, click NFL, copy filter= from URL
    "NBA":    None,
    "NHL":    None,
    "SOCCER": None,
}

# Odds array positions (9 values per snapshot)
# [0]=home_ml [1]=away_ml [2]=spread_val [3]=away_spread_juice
# [4]=spread_val2 [5]=home_spread_juice [6]=total [7]=over_juice [8]=under_juice
SCANBET_ODDS_IDX = {
    "home_ml": 0, "away_ml": 1,
    "spread":  2, "away_spread_juice": 3,
    "total":   6, "over_juice": 7, "under_juice": 8,
}


def _dec_to_amer(dec):
    """Convert decimal odds to American."""
    try:
        d = float(dec)
        if d >= 2.0: return int((d-1)*100)
        else:        return int(-100/(d-1))
    except Exception: return 0


def _dec_to_prob(dec):
    """Convert decimal odds to implied probability."""
    try: return 1.0 / float(dec)
    except Exception: return 0.5


def fetch_scanbet_drops_from_gist() -> list:
    """
    Read Pinnacle line movement data from Gist (pushed by browser bookmarklet).
    Parses Scanbet GraphQL response format — full odds history per game.
    Detects drops: compares first snapshot (opener) vs last snapshot (current).
    Returns list of {game, home, away, sport, market, selection,
                     opener_odds, current_odds, opener_prob, current_prob,
                     drop_pct, is_steam, n_snapshots, source}
    Cached 5 min.
    """
    cp = os.path.join(CACHE_DIR, "scanbet_drops_gist.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/60 < 5:
        c = _safe_load_pkl(cp)
        if c is not None: return c

    raw = _read_gist_file("betcouncil_scanbet_drops.json", cache_minutes=5)
    if not raw: return []

    try:
        # Handle both direct GraphQL response and wrapped format
        if isinstance(raw, dict) and "data" in raw:
            sports_data = raw["data"]["events"]["pageData"]["sports"]
        elif isinstance(raw, list):
            # Legacy format from old bookmarklet
            return _parse_legacy_scanbet(raw)
        else:
            return []

        results = []
        for sport_obj in sports_data:
            sport_name = sport_obj.get("sportName","")
            # Map Scanbet sport names to BetCouncil sport codes
            sport_map = {"Baseball":"MLB","Basketball":"NBA","Football":"NFL",
                         "Ice Hockey":"NHL","Soccer":"SOCCER","Tennis":"TENNIS"}
            sport_code = sport_map.get(sport_name, sport_name.upper()[:6])

            for league_obj in sport_obj.get("leagues",[]):
                league = league_obj.get("leagueName","")
                if isinstance(league, list): league = league[0] if league else ""

                for event in league_obj.get("events",[]):
                    home = event.get("home","")
                    away = event.get("away","")
                    game = f"{away} @ {home}"
                    snapshots = event.get("eventOdds",[])

                    if len(snapshots) < 2:
                        continue  # No movement

                    opener  = snapshots[0]["odds"]
                    current = snapshots[-1]["odds"]
                    n_snaps = len(snapshots)

                    # Detect drops for each market
                    markets = [
                        ("Moneyline", "home", SCANBET_ODDS_IDX["home_ml"], home),
                        ("Moneyline", "away", SCANBET_ODDS_IDX["away_ml"], away),
                        ("Total",     "over", SCANBET_ODDS_IDX["over_juice"], "Over"),
                        ("Total",     "under",SCANBET_ODDS_IDX["under_juice"],"Under"),
                    ]

                    for market, side, idx, label in markets:
                        try:
                            open_dec = opener[idx]
                            curr_dec = current[idx]
                            if not open_dec or not curr_dec: continue

                            open_prob = _dec_to_prob(open_dec)
                            curr_prob = _dec_to_prob(curr_dec)
                            drop_pct  = curr_prob - open_prob  # positive = prob up = line moved toward this side

                            # Only report meaningful moves (>1%)
                            if abs(drop_pct) < 0.01: continue

                            results.append({
                                "game":         game,
                                "home":         home,
                                "away":         away,
                                "sport":        sport_code,
                                "league":       league,
                                "market":       market,
                                "selection":    label,
                                "opener_odds":  _dec_to_amer(open_dec),
                                "current_odds": _dec_to_amer(curr_dec),
                                "opener_dec":   open_dec,
                                "current_dec":  curr_dec,
                                "opener_prob":  round(open_prob, 4),
                                "current_prob": round(curr_prob, 4),
                                "drop_pct":     round(drop_pct, 4),
                                "is_steam":     drop_pct > 0,  # prob went UP = money on this side
                                "n_snapshots":  n_snaps,
                                "source":       "scanbet_graphql",
                            })
                        except Exception:
                            continue

                    # ── Point-value tracking (spread/total NUMBER, not just juice) ──
                    # Needed for key-number crossing analysis (nfl_key_numbers.py).
                    # The juice-based "Total"/"Moneyline" entries above track price
                    # movement; this tracks the actual line value movement.
                    try:
                        open_spread = opener[SCANBET_ODDS_IDX["spread"]]
                        curr_spread = current[SCANBET_ODDS_IDX["spread"]]
                        if open_spread and curr_spread and open_spread != curr_spread:
                            results.append({
                                "game": game, "home": home, "away": away,
                                "sport": sport_code, "league": league,
                                "market": "SpreadValue", "selection": "line",
                                "opener_value": open_spread, "current_value": curr_spread,
                                "n_snapshots": n_snaps, "source": "scanbet_graphql",
                            })
                    except Exception:
                        pass
                    try:
                        open_total = opener[SCANBET_ODDS_IDX["total"]]
                        curr_total = current[SCANBET_ODDS_IDX["total"]]
                        if open_total and curr_total and open_total != curr_total:
                            results.append({
                                "game": game, "home": home, "away": away,
                                "sport": sport_code, "league": league,
                                "market": "TotalValue", "selection": "line",
                                "opener_value": open_total, "current_value": curr_total,
                                "n_snapshots": n_snaps, "source": "scanbet_graphql",
                            })
                    except Exception:
                        pass

        # Sort by absolute drop magnitude
        results.sort(key=lambda x: abs(x["drop_pct"]), reverse=True)

        if results:
            _safe_save_pkl(cp, results)
            print(f"[Scanbet] {len(results)} line movements detected across {len(sports_data)} sports")

        return results

    except Exception as e:
        print(f"[WARN] fetch_scanbet_drops_from_gist: {e}")
        return []


def _parse_legacy_scanbet(raw_list: list) -> list:
    """Parse legacy bookmarklet format (list of {timestamp, data})."""
    results = []
    for entry in raw_list:
        data = entry.get("data",{})
        if isinstance(data, dict) and "data" in data:
            try:
                sports = data["data"]["events"]["pageData"]["sports"]
                results.extend(fetch_scanbet_drops_from_gist.__wrapped__({"data":{"events":{"pageData":{"sports":sports}}}}))
            except Exception:
                pass
    return results



# ── Browser Harvester Gist Readers ───────────────────────────────────────────
# These read data pushed by the browser-side auto-harvester in BetCouncil.
# Primary source = browser harvester (residential IP, bypasses WAFs).
# Secondary source = existing server-side scrapers (fallback if harvester fails).
# Status tracking lets BetCouncil show which source is active.

def _read_gist_file(filename: str, cache_minutes: int = 10) -> dict:
    """Read a file from the BetCouncil Gist. Cached locally."""
    cp = os.path.join(CACHE_DIR, f"gist_{filename.replace('.json','')}.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/60 < cache_minutes:
        c = _safe_load_pkl(cp)
        if c is not None: return c
    try:
        req = urllib.request.Request(
            f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization":f"token {GITHUB_TOKEN}",
                     "Accept":"application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            gist = json.loads(r.read())
        f = gist.get("files",{}).get(filename,{})
        if not f: return {}
        content = f.get("content","")
        # The combined gist endpoint truncates per-file content (returns "" and
        # truncated:true) once the gist's total aggregate size gets large enough,
        # regardless of how small this individual file is. Fall back to the
        # file's own raw_url in that case. raw_url is fetched fresh right here,
        # not stored/cached, since it's a point-in-time snapshot URL tied to a
        # commit SHA and would go stale if reused across later pushes.
        if (not content or f.get("truncated")) and f.get("raw_url"):
            raw_req = urllib.request.Request(
                f["raw_url"],
                headers={"Authorization": f"token {GITHUB_TOKEN}"})
            with urllib.request.urlopen(raw_req, timeout=15) as rr:
                content = rr.read().decode("utf-8")
        data = json.loads(content or "{}")
        _safe_save_pkl(cp, data)
        return data
    except Exception as e:
        print(f"[WARN] _read_gist_file({filename}): {e}")
        return {}


def _is_fresh(data: dict, max_age_minutes: int = 30) -> bool:
    """Check if harvested data is recent enough to use.

    NOTE (2026-07): call sites reading */15 cron-scheduled Gist files used to
    pass max_age_minutes=22, assuming GitHub Actions actually fires every 15
    min. Checked real run history — GitHub's scheduled cron is best-effort
    and was firing every ~65-70 min on average (up to 99 min gaps) on this
    repo, not 15. A 22-min window rejected fresh data as "stale" on nearly
    every board load, silently forcing live-scrape fallback (and burning
    ScrapeOps credits) even when the workflow was running fine. Widened those
    call sites to max_age_minutes=100 to match observed real-world cadence.
    """
    ts = data.get("captured_at","")
    if not ts: return False
    try:
        from datetime import datetime, timezone
        captured = datetime.fromisoformat(ts.replace("Z","+00:00"))
        age = (datetime.now(timezone.utc) - captured).total_seconds() / 60
        return age <= max_age_minutes
    except Exception:
        return False


def _gist_data_age_minutes(data: dict):
    """Age in minutes of a harvested payload's captured_at, or None if missing/bad."""
    ts = (data or {}).get("captured_at", "")
    if not ts:
        return None
    try:
        from datetime import datetime, timezone
        captured = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - captured).total_seconds() / 60
    except Exception:
        return None


# ── Harvester health registry ────────────────────────────────────────────
# (gist_filename_template, expected_interval_minutes, tier) for every browser
# harvester / scheduled source, pulled directly from the throttled(...) call
# intervals in the injected JS and the GitHub Actions cron schedules. tier is
# "sharp" (benchmark sources — alert loudly), "lines"/"props" (books —
# alert), or "signal" (secondary context — informational only).
HARVESTER_REGISTRY = {
    "evsharps":        ("betcouncil_tokens.json",                    50, "sharp"),
    "betmgm":          ("betcouncil_betmgm_{sport}.json",            25, "lines"),
    "action_network":  ("betcouncil_actionnetwork_{sport}.json",     40, "signal"),
    "covers":          ("betcouncil_covers_{sport}.json",            20, "signal"),
    "dk_props":        ("betcouncil_dk_props_{sport}.json",          20, "props"),
    "unabated":        ("betcouncil_unabated_{sport}.json",          30, "sharp"),
    "oddsjam":         ("betcouncil_oddsjam_{sport}.json",           20, "sharp"),
    "propswap":        ("betcouncil_propswap_{sport}.json",          30, "signal"),
    "evsharps_ev":     ("betcouncil_evsharps_dingers_MLB.json",      25, "sharp"),
    "underdog":        ("betcouncil_underdog_{sport}.json",          20, "props"),
    "bovada":          ("betcouncil_bovada_{sport}.json",            20, "lines"),
    "polymarket":      ("betcouncil_sharptrack_live.json",           30, "signal"),
    "mybookie":        ("betcouncil_mybookie_{sport}.json",          25, "lines"),
    "parlaysavant":    ("betcouncil_parlaysavant_{sport}.json",      20, "props"),
    "bet365":          ("betcouncil_bet365_games.json",              25, "lines"),
    "pregame":         ("betcouncil_pregame_{sport}.json",           30, "signal"),
    "fantasylabs":     ("betcouncil_fantasylabs_{sport}.json",       30, "signal"),
    "rotowire":        ("betcouncil_rotowire_{sport}.json",          15, "signal"),
    "sleeper":         ("betcouncil_sleeper_{sport}.json",           30, "signal"),
    "numberfire":      ("betcouncil_numberfire_{sport}.json",        30, "signal"),
    "sportsinsights":  ("betcouncil_sportsinsights_{sport}.json",    15, "signal"),
    "oddsshark":       ("betcouncil_oddsshark_{sport}.json",         20, "signal"),
    "vegasinsider":    ("betcouncil_vegasinsider_{sport}.json",      20, "signal"),
    "propscash":       ("betcouncil_propscash_{sport}.json",         20, "signal"),
    "bettingpros":     ("betcouncil_bettingpros_{sport}.json",       20, "signal"),
    "stokastic":       ("betcouncil_stokastic_{sport}.json",         30, "signal"),
    "rotogrinders":    ("betcouncil_rotogrinders_{sport}.json",      30, "signal"),
    "oddsportal":      ("betcouncil_oddsportal_{sport}.json",        300, "signal"),  # now ESPN opening-lines capture, once/day
    "outlier":         ("betcouncil_outlier_{sport}.json",           20, "signal"),
    "smarkets":        ("betcouncil_smarkets_{sport}.json",          25, "signal"),
    "pickwise":        ("betcouncil_pickwise_{sport}.json",          20, "signal"),
    "scoresandodds":   ("betcouncil_scoresandodds_{sport}.json",     15, "signal"),
    "kalshi":          ("betcouncil_kalshi_{sport}.json",            30, "signal"),
    "pickswise":       ("betcouncil_pickswise_{sport}.json",         30, "signal"),
    "betus":           ("betcouncil_betus_{sport}.json",             25, "props"),
    "bet105":          ("betcouncil_bet105_{sport}.json",            25, "lines"),
    "betwhale":        ("betcouncil_betwhale_{sport}.json",          25, "lines"),
    "ybets":           ("betcouncil_ybets_{sport}.json",             25, "lines"),
    "zamba":           ("betcouncil_zamba_{sport}.json",             25, "lines"),
    "evbets":          ("betcouncil_evbets_{sport}.json",            20, "sharp"),
    "evbets_props":    ("betcouncil_evbets_props_{sport}.json",      20, "sharp"),
    # Caesars WAF/bearer token — expires ~24h, no auto-refresh (passive
    # capture only fires when a real logged-in tab makes an authenticated
    # call). expected_minutes set to 12h so it goes 🟡 with lead time to
    # manually re-run caesars_login_harvest.py before the hard expiry.
    "caesars":         ("betcouncil_caesars_tokens.json",             720, "lines"),
    # GitHub-Actions-backed sources (cron, not a live browser tab) — 2x their
    # cron cadence as the freshness bar so a single missed run doesn't trip.
    "prizepicks":      ("betcouncil_prizepicks_{sport}.json",        30, "props"),
    "pick6":           ("betcouncil_pick6_props.json",               60, "props"),
}


HARVESTER_DISPLAY_NAMES = {
    "evsharps": "EV Sharps (Pinnacle/Circa benchmark)",
    "evsharps_ev": "EV Sharps EV feed",
    "unabated": "Unabated (sharp line consensus)",
    "oddsjam": "OddsJam (sharp line consensus)",
    "evbets": "EV Bets (sharp line feed)",
    "evbets_props": "EV Bets props feed",
    "betmgm": "BetMGM", "bovada": "Bovada", "mybookie": "MyBookie",
    "dk_props": "DraftKings props", "underdog": "Underdog",
    "prizepicks": "PrizePicks", "pick6": "DK Pick6",
    "caesars": "Caesars",
}

def harvester_display_name(key: str) -> str:
    """Falls back to a cleaned-up version of the raw key (underscores to
    spaces, title case) for anything not explicitly mapped, rather than
    showing the internal registry key as-is."""
    return HARVESTER_DISPLAY_NAMES.get(key, key.replace("_", " ").title())


def check_harvester_health(sport: str, tiers=("sharp", "lines", "props", "signal")) -> list:
    """
    Check every registered harvester source's Gist payload age against its
    expected refresh interval. Returns a list of dicts:
      {name, tier, status, age_minutes, expected_minutes}
    status is 🟢 fresh (<=1x expected), 🟡 stale (1x-3x expected),
    🔴 dead (>3x expected), or ⚫ never-seen (no captured_at data at all).
    Does not raise — a source that can't be checked is reported ⚫, not skipped.
    """
    results = []
    for name, (fname_tmpl, expected_min, tier) in HARVESTER_REGISTRY.items():
        if tier not in tiers:
            continue
        fname = fname_tmpl.format(sport=sport) if "{sport}" in fname_tmpl else fname_tmpl
        try:
            data = _read_gist_file(fname, cache_minutes=5)
        except Exception:
            data = {}
        age = _gist_data_age_minutes(data)
        if age is None:
            status = "⚫"
        elif age <= expected_min:
            status = "🟢"
        elif age <= expected_min * 3:
            status = "🟡"
        else:
            status = "🔴"
        results.append({
            "name": name, "tier": tier, "status": status,
            "age_minutes": round(age, 1) if age is not None else None,
            "expected_minutes": expected_min,
        })
    return results


def get_harvester_alerts(sport: str, persist: bool = True) -> list:
    """
    Same-day dead-source alerting: compares this check's results against the
    last persisted check (stored in the Gist as
    betcouncil_harvester_health_prev_{sport}.json) and returns only sources
    that just TRANSITIONED to 🔴 dead since the previous check — not every
    source that's been dead for weeks, which would just be noise every load.
    Sharp-tier sources are always included even on a repeat-dead check, since
    those are high-priority enough to keep surfacing.
    """
    current = check_harvester_health(sport)
    prev_fname = f"betcouncil_harvester_health_prev_{sport}.json"
    try:
        prev_data = _read_gist_file(prev_fname, cache_minutes=1)
    except Exception:
        prev_data = {}
    prev_status = (prev_data or {}).get("status", {})

    alerts = []
    for r in current:
        was = prev_status.get(r["name"])
        if r["status"] == "🔴" and (was != "🔴" or r["tier"] == "sharp"):
            alerts.append(r)

    if persist:
        try:
            new_snapshot = {
                "status": {r["name"]: r["status"] for r in current},
                "captured_at": datetime.utcnow().isoformat() + "Z",
                "sport": sport,
            }
            save_to_gist(f"harvester_health_prev_{sport}", new_snapshot)
        except Exception:
            pass

    return alerts


def fetch_caesars_waf_from_gist() -> str:
    """
    Get Caesars WAF token from Gist (pushed by browser harvester).
    Falls back to CAESARS_WAF_TOKEN secret.
    """
    data = _read_gist_file("betcouncil_caesars_tokens.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=100):
        waf = data.get("waf_token","")
        if waf:
            print("[Caesars] Using auto-harvested WAF token")
            return waf
    try:
        import streamlit as st
        return st.secrets.get("CAESARS_WAF_TOKEN","")
    except Exception:
        return ""


def fetch_fanduel_props_from_gist(sport: str) -> list:
    """
    PRIMARY (Jul 2026): Odds-API.io -- confirmed live this session against
    a real pending MLB game (307 real FanDuel prop entries across 10 stat
    categories), independently cross-checked against the vendor's own
    official docs before wiring in. No PerimeterX token, no browser tab,
    no expiring session -- one clean REST call. Shares a 100/hr free-tier
    budget with the Bet365 game-lines source on the same account/key.

    SECONDARY: browser harvester Gist (previous primary) -- kept as a
    real fallback, not removed, in case the odds-api.io source is ever
    unavailable or its free-tier budget is exhausted for the hour.
    TERTIARY: fetch_fanduel_props_sharpapi() if stale.
    QUATERNARY (2026-07): LineStar's GetPropBets already includes FanDuel as
    one of its books (Source=2), server-side, already proven live this
    session (wired into Line Shop as "FanDuel (LineStar)"). Cheap, real,
    zero additional infra risk.

    REMOVED (2026-07): a Playwright last-resort tier was briefly wired in
    here and caused a production segfault -- Playwright's sync API crashes
    natively when invoked from a background thread with its own event loop,
    which is exactly how Streamlit executes app.py (_run_script_thread).
    That's a native crash below the Python interpreter, so the try/except
    around the call never had a chance to catch it. Do not re-add a
    Playwright call on this path without running it in a genuinely separate
    process (not a thread) first.
    Returns (props_list, source_label)
    """
    try:
        oddsapiio_data = _read_gist_file(f"betcouncil_oddsapiio_fanduel_props_{sport.upper()}.json", cache_minutes=15)
    except Exception:
        oddsapiio_data = None
    if oddsapiio_data and oddsapiio_data.get("props"):
        print(f"[FanDuel] PRIMARY: {len(oddsapiio_data['props'])} props from odds-api.io")
        return oddsapiio_data["props"], "oddsapiio"

    data = _read_gist_file(f"betcouncil_fd_props_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=28):
        raw = data.get("props", data.get("data",[]))
        if raw:
            # Parse FanDuel API format
            results = _parse_fanduel_harvested(raw, sport)
            if results:
                print(f"[FanDuel] SECONDARY: {len(results)} props from browser harvester")
                return results, "browser_harvester"

    # Tertiary fallback (SharpAPI) removed Aug 1 2026 -- see fetch_sharpapi_lines
    # comment above for why. QUATERNARY below remains a real fallback.

    # Quaternary fallback: LineStar GetPropBets, FanDuel book (Source=2)
    try:
        ls_data, _ = fetch_linestar_props_from_gist(sport)
        if ls_data:
            ls_by_book = parse_linestar_props_all_books(ls_data, sport)
            fd_list = ls_by_book.get("FanDuel") or ls_by_book.get("Fanduel") or []
            if fd_list:
                print(f"[FanDuel] QUATERNARY: {len(fd_list)} props from LineStar")
                return fd_list, "linestar_fallback"
    except Exception:
        pass

    return [], "unavailable"


def fetch_pick6_props_from_gist(sport: str = "MLB", max_age_minutes: int = 60) -> tuple:
    """
    Reads DraftKings Pick6 player props from the Gist (pushed by the
    Replit SSR-scrape script — no login/browser automation needed on
    the scraping side; Pick6 embeds its full prop dataset directly in
    the page's server-rendered HTML).
    Returns (props_list, source_label)
    """
    data = _read_gist_file("betcouncil_pick6_props.json", cache_minutes=10)
    if not data:
        return [], "unavailable"

    if not _is_fresh(data, max_age_minutes=max_age_minutes):
        print(f"[Pick6] Gist data is stale (>{max_age_minutes}min old) — skipping")
        return [], "stale"

    raw_props = data.get("props", data) if isinstance(data, dict) else data
    if not raw_props:
        return [], "unavailable"

    results = []
    seen = set()
    for p in raw_props:
        player = p.get("player") or p.get("Player")
        stat_name = p.get("stat_name") or p.get("Prop") or p.get("stat")
        line = p.get("line") or p.get("Line") or p.get("targetValue")
        multiplier = p.get("multiplier") or p.get("standingsMultiplier")

        if not player or line is None:
            continue
        try:
            line_val = float(line)
        except (TypeError, ValueError):
            continue

        key = (player, stat_name, line_val, multiplier)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "Player": player,
            "Prop": stat_name or "Unknown",
            "Line": line_val,
            "Multiplier": multiplier,
            "Book": "Pick6",
            "Sport": sport,
            "source": "pick6_ssr_scrape",
            "captured_at": p.get("captured_at", data.get("captured_at", "") if isinstance(data, dict) else ""),
        })

    if results:
        print(f"[Pick6] {len(results)} props from SSR scrape (no login required)")
        return results, "ssr_scrape"
    return [], "unavailable"




def _parse_fanduel_harvested(raw, sport: str) -> list:
    """Parse FanDuel browser-harvested data into BetCouncil prop format."""
    results = []
    try:
        # Handle various FD API response structures
        if isinstance(raw, dict):
            # Try common FD API structures
            items = (raw.get("attachments",{}).get("markets",{}).values() or
                     raw.get("markets",[]) or
                     raw.get("events",[]) or [])
            if isinstance(items, dict): items = list(items.values())
        elif isinstance(raw, list):
            items = raw
        else:
            return []

        for item in items:
            if not isinstance(item, dict): continue
            market_name = item.get("marketName", item.get("market_name",""))
            if not market_name: continue
            runners = item.get("runners", item.get("selections", item.get("outcomes",[])))
            for runner in (runners if isinstance(runners,list) else []):
                name      = runner.get("runnerName", runner.get("name",""))
                handicap  = runner.get("handicap", runner.get("line",""))
                win_odds  = runner.get("winRunnerOdds",{})
                american  = (win_odds.get("americanDisplayOdds",{}).get("americanOdds") if isinstance(win_odds,dict)
                             else runner.get("price", runner.get("odds","")))
                if not name: continue
                # Split "Player OVER X.X" format
                side = "OVER" if "over" in str(name).lower() or "over" in str(market_name).lower() else "UNDER"
                player = name.replace(" Over","").replace(" Under","").replace(" over","").replace(" under","").strip()
                results.append({
                    "Player":    player,
                    "Prop":      market_name,
                    "Line":      handicap,
                    "OverOdds":  american if side=="OVER" else "N/A",
                    "UnderOdds": american if side=="UNDER" else "N/A",
                    "Book":      "FanDuel",
                    "Sport":     sport,
                    "source":    "fanduel_browser_harvest",
                })
    except Exception as e:
        print(f"[WARN] _parse_fanduel_harvested: {e}")
    return results


def _parse_betmgm_harvested(raw, sport: str) -> list:
    """Parse BetMGM browser-harvested data."""
    results = []
    try:
        widgets = raw.get("widgets", raw.get("bettables", []))
        if isinstance(widgets, dict): widgets = list(widgets.values())
        for widget in (widgets if isinstance(widgets,list) else []):
            if not isinstance(widget,dict): continue
            markets = widget.get("markets", widget.get("fixtures",[]))
            for market in (markets if isinstance(markets,list) else []):
                if not isinstance(market,dict): continue
                market_name = market.get("name","")
                for outcome in market.get("outcomes", market.get("selections",[])):
                    if not isinstance(outcome,dict): continue
                    name  = outcome.get("name","")
                    odds  = outcome.get("americanOdds", outcome.get("price",""))
                    line  = outcome.get("attr", outcome.get("handicap",""))
                    if not name: continue
                    results.append({
                        "Player":    name.replace(" Over","").replace(" Under","").strip(),
                        "Prop":      market_name,
                        "Line":      line,
                        "OverOdds":  odds if "over" in name.lower() else "N/A",
                        "UnderOdds": odds if "under" in name.lower() else "N/A",
                        "Book":      "BetMGM",
                        "Sport":     sport,
                        "source":    "betmgm_browser_harvest",
                    })
    except Exception as e:
        print(f"[WARN] _parse_betmgm_harvested: {e}")
    return results


def fetch_action_network_from_gist(sport: str) -> dict:
    """
    Action Network public betting % (sharp splits) via
    fetch_action_network_public_betting(). Returns dict of game data with
    sharp split percentages.

    Previously had a PRIMARY Gist-harvester path reading
    "betcouncil_actionnetwork_{sport}.json" under a "data" key -- removed
    2026-07-17. That path was doubly broken even before its in-app JS
    harvester was removed: (1) the harvester fetched Action Network's
    scoreboard/game-lines endpoint, not the public-betting-% endpoint this
    function actually needs, and (2) actionnetwork_refresh.py (the real,
    live, server-side cron that now owns that same Gist filename) writes
    scoreboard data under a "games" key for a *different* consumer
    (fetch_actionnetwork_from_gist / get_actionnetwork_match) entirely.
    Public betting % has no working harvested source right now, so this
    just calls the scraper directly.
    """
    try:
        from fetchers import fetch_action_network_public_betting as _fetch_an
        secondary = _fetch_an(sport)
        if secondary:
            return secondary, "scraper_fallback"
    except Exception:
        pass
    return {}, "unavailable"



def fetch_covers_from_gist(sport: str) -> tuple:
    """PRIMARY: Covers consensus % from browser harvester. SECONDARY: scraper."""
    data = _read_gist_file(f"betcouncil_covers_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=100):
        raw = data.get("data",{})
        if raw:
            print(f"[Covers] PRIMARY: browser harvester")
            return raw, "browser_harvester"
    try:
        from fetchers import fetch_covers_consensus as _fc
        s = _fc(sport)
        if s: return s, "scraper_fallback"
    except Exception: pass
    return {}, "unavailable"


def fetch_draftkings_props_from_gist(sport: str) -> tuple:
    """PRIMARY: DK props from browser harvester.
    SECONDARY: LineStar GetPropBets Source=1 (server-side, no auth, no Tampermonkey).
    TERTIARY: Python scraper fallback."""
    data = _read_gist_file(f"betcouncil_dk_props_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=100):
        raw = data.get("data",{})
        if raw:
            props = _parse_dk_harvested(raw, sport)
            if props:
                print(f"[DraftKings] PRIMARY: {len(props)} props from browser harvester")
                return props, "browser_harvester"
    # SECONDARY: LineStar GetPropBets contains DraftKings prop lines (Source=1) — fully
    # server-side, no browser harvester or tokens needed. Provides equivalent prop lines.
    ls_props = _read_gist_file(f"betcouncil_linestar_props_{sport}.json", cache_minutes=5)
    if ls_props and _is_fresh(ls_props, max_age_minutes=70):
        props = _parse_linestar_as_dk_props(ls_props.get("data", {}), sport)
        if props:
            print(f"[DraftKings] SECONDARY: {len(props)} props from LineStar GetPropBets")
            return props, "linestar_fallback"
    try:
        from fetchers import fetch_draftkings_direct as _fdk
        s = _fdk(sport)
        if s: return s, "scraper_fallback"
    except Exception: pass
    return [], "unavailable"


def _parse_linestar_as_dk_props(pb_data: dict, sport: str) -> list:
    """Convert LineStar GetPropBets response (Source=1=DraftKings) into standard prop format.
    Output matches the shape produced by _parse_dk_harvested() so downstream code is unchanged."""
    results = []
    try:
        # Build lookup dicts from integer IDs
        bet_types = {b["Id"]: b["StatName"] for b in pb_data.get("BetTypes", [])}
        players   = {p["Id"]: p["Name"]    for p in pb_data.get("Players", [])}
        books     = {b["Source"]: b["Name"] for b in pb_data.get("SportsBooks", [])}
        for prop in pb_data.get("PropBets", []):
            if prop.get("Source") != 1:
                continue  # DraftKings only
            pid  = prop.get("PlayerId")
            name = players.get(pid, "")
            if not name:
                continue
            stat = bet_types.get(prop.get("StatId"), "")
            line = prop.get("OverUnderValue")
            if line is None:
                continue
            over_odds  = prop.get("OverOdds")
            under_odds = prop.get("UnderOdds")
            results.append({
                "Player":    name,
                "Prop":      stat,
                "Line":      float(line),
                "OverOdds":  str(over_odds)  if over_odds  is not None else "N/A",
                "UnderOdds": str(under_odds) if under_odds is not None else "N/A",
                "Book":      "DraftKings",
                "Sport":     sport,
                "source":    "linestar_fallback",
                "ls_proj":   prop.get("LineStarStatProj"),
            })
    except Exception as e:
        print(f"[WARN] _parse_linestar_as_dk_props: {e}")
    return results


# Best-effort LineStar StatName -> BetCouncil canonical Prop name. Matching
# against board_data's Prop strings is exact-string, so anything not mapped
# here just won't line up with a board row (safe no-op, not a wrong value).
# Confirm/extend this against a real captured payload as books show gaps.
_LS_STAT_NAME_MAP = {
    "hits": "Hits", "total bases": "Total Bases", "home runs": "Home Runs", "hr": "Home Runs",
    "rbis": "RBI", "rbi": "RBI", "runs": "Runs", "singles": "Singles", "doubles": "Doubles",
    "triples": "Triples", "stolen bases": "Stolen Bases", "walks": "Walks",
    "pitcher strikeouts": "Pitcher Strikeouts", "strikeouts": "Pitcher Strikeouts",
    "walks allowed": "Walks Allowed", "outs recorded": "Outs Recorded",
    "earned runs allowed": "Earned Runs Allowed", "hits allowed": "Hits Allowed",
}

def parse_linestar_props_all_books(pb_data: dict, sport: str) -> dict:
    """Convert LineStar GetPropBets into {book_name: [{"Player","Prop","Line",...}]}
    for every book in the payload (not just DraftKings — see _parse_linestar_as_dk_props
    for the DK-only fallback used elsewhere). Intended for the Line Shop tab, where each
    book's list gets fed into _ls_add() under a "<Book> (LineStar)" source label so it
    never overwrites lines already harvested directly from that book.
    """
    out = {}
    try:
        bet_types = {b["Id"]: b["StatName"] for b in pb_data.get("BetTypes", [])}
        players   = {p["Id"]: p["Name"]    for p in pb_data.get("Players", [])}
        books     = {b["Source"]: b["Name"] for b in pb_data.get("SportsBooks", [])}
        for prop in pb_data.get("PropBets", []):
            pid  = prop.get("PlayerId")
            name = players.get(pid, "")
            book = books.get(prop.get("Source"))
            line = prop.get("OverUnderValue")
            if not name or not book or line is None:
                continue
            raw_stat = bet_types.get(prop.get("StatId"), "")
            stat = _LS_STAT_NAME_MAP.get(str(raw_stat).strip().lower(), raw_stat)
            out.setdefault(book, []).append({
                "Player": name, "Prop": stat, "Line": float(line),
                "OverOdds": prop.get("OverOdds"), "UnderOdds": prop.get("UnderOdds"),
                "ls_proj": prop.get("LineStarStatProj"),
            })
    except Exception as e:
        print(f"[WARN] parse_linestar_props_all_books: {e}")
    return out


def _parse_dk_harvested(raw: dict, sport: str) -> list:
    """Parse DraftKings category API response into prop format."""
    results = []
    try:
        cats = raw.get("eventGroup",{}).get("offerCategories",[])
        for cat in cats:
            for subcat in cat.get("offerSubcategoryDescriptors",[]):
                for offer in subcat.get("offerSubcategory",{}).get("offers",[]):
                    for o in (offer if isinstance(offer,list) else [offer]):
                        if not isinstance(o,dict): continue
                        label    = o.get("label","")
                        outcomes = o.get("outcomes",[])
                        over_odds = under_odds = line = None
                        player = ""
                        for oc in outcomes:
                            if not isinstance(oc,dict): continue
                            if not player: player = oc.get("participant","")
                            hdp = oc.get("line", oc.get("handicap"))
                            if hdp is not None: line = hdp
                            odds = oc.get("oddsAmerican", oc.get("odds",""))
                            lbl  = oc.get("label","").lower()
                            if "over" in lbl:  over_odds  = odds
                            if "under" in lbl: under_odds = odds
                        if player or label:
                            results.append({
                                "Player":    player or label,
                                "Prop":      label,
                                "Line":      line,
                                "OverOdds":  over_odds  or "N/A",
                                "UnderOdds": under_odds or "N/A",
                                "Book":      "DraftKings",
                                "Sport":     sport,
                                "source":    "dk_browser_harvest",
                            })
    except Exception as e:
        print(f"[WARN] _parse_dk_harvested: {e}")
    return results


# ═══════════════════════════════════════════════════════════════════════
# NEW BETTOR — public/book comparison sources
# ─────────────────────────────────────────────────────────────────────
# These two functions feed the "How This Compares" panel in the New
# Bettor tab only. They are display/comparison data, not signals — do
# not wire either into compute_multi_signal_edge, SEM, or any
# signal_performance.json / calibration path.
# ═══════════════════════════════════════════════════════════════════════

def fetch_propsmadness_from_gist(sport: str = "MLB", max_age_minutes: int = 30) -> list:
    """
    PropsMadness — mostly paywall-locked (only offerType:"fallback" rows
    are usable, typically ~1 per full slate), but real when present.
    Aggregates across all market files for the sport since each market
    (player-strikeouts, player-hits, etc.) is a separate Gist file.
    """
    if sport != "MLB":
        return []
    league = "mlb"
    markets = ["player-strikeouts", "player-hits", "player-home-runs",
               "player-total-bases", "player-rbis", "player-runs",
               "player-walks", "player-stolen-bases", "player-earned-runs",
               "player-hits-allowed", "player-pitcher-outs", "player-hits-runs-rbis"]
    offers = []
    for market in markets:
        data = _read_gist_file(f"betcouncil_propsmadness_{league}_{market}.json", cache_minutes=10)
        if data and _is_fresh(data, max_age_minutes=max_age_minutes):
            offers.extend(data.get("offers", []))
    return offers


def fetch_lineterminal_player_props(player: str, sport: str = "MLB") -> list:
    """
    LineTerminal (Inside Edge Inc) — all of this player's props for the
    day, each with model probability vs market-implied probability, tier,
    best book/price. Display-only comparison source, same category as
    Dimers/Covers/WagerBird.
    """
    data = _read_gist_file(f"betcouncil_lineterminal_props_{sport}.json", cache_minutes=5)
    if not data or not _is_fresh(data, max_age_minutes=30):
        return []
    player_u = normalize_name(player)
    rows = []
    for game in data.get("games", []):
        for p in game.get("props", []):
            if normalize_name(p.get("player_name", "")) != player_u:
                continue
            v = p.get("verdict", {}) or {}
            if not v.get("side"):
                continue
            rows.append({
                "stat_label": p.get("stat_label"), "point": p.get("point"),
                "side": v.get("side"), "tier": v.get("tier"),
                "recommend": v.get("recommend"),
                "model_prob_pct": v.get("model_prob_pct"),
                "implied_prob_pct": v.get("implied_prob_pct"),
                "edge_pct": v.get("edge_pct"),
                "best_book": v.get("best_book"), "best_price": v.get("best_price"),
                "confidence": v.get("confidence"),
            })
    return rows


def fetch_dimers_from_gist(sport: str, max_age_minutes: int = 100) -> list:
    """
    Dimers.com game-line picks (edges, model win probabilities, odds per
    market) via their Stats Insider backend — confirmed live 2026-07,
    every field verified against a real response. Dimers visually gates
    most picks behind "Dimers Pro" on their own site, but that gating is
    frontend-only; the underlying data (scripts/dimers_refresh.py) is
    public and unauthenticated.

    Returns the raw "matches" list, each with:
        {sim_match_id, match: {AwayTeam, HomeTeam, Date, ...},
         betting: {tab: {AwayH2HEdge, HomeH2HEdge, AwayLineEdge,
                          HomeLineEdge, OverEdge, UnderEdge, AwayOdds,
                          HomeOdds, HomeLine, TotalLine, AwayLineWinPct,
                          HomeLineWinPct, OverWinPct, UnderWinPct, ...}}}
    Game-line comparison data — same category as BettingPros/Covers in
    the New Bettor panel, not props like FavoredProps/DK.
    """
    data = _read_gist_file(f"betcouncil_dimers_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("matches", [])
        if isinstance(raw, list):
            return raw
    return []


def get_dimers_match(matchup: str, sport: str) -> dict:
    """
    Single-game lookup against Dimers' data — matches by team abbreviation
    substring against a BetCouncil matchup string (e.g. "TOR @ CWS"),
    same matching approach used in build_market_comparison() for the New
    Bettor shortlist, factored out here for reuse in Game Lines and
    anywhere else a per-game comparison is useful.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        matches = fetch_dimers_from_gist(sport)
    except Exception:
        matches = []
    matchup_u = matchup.upper()
    for dm in matches:
        match_meta = dm.get("match", {})
        home_abv = str(match_meta.get("HomeTeam", {}).get("Abv", "")).upper()
        away_abv = str(match_meta.get("AwayTeam", {}).get("Abv", "")).upper()
        if home_abv and away_abv and home_abv in matchup_u and away_abv in matchup_u:
            tab = dm.get("betting", {}).get("tab", {})
            return {
                "home_abv": home_abv, "away_abv": away_abv,
                "home_edge": tab.get("HomeH2HEdge"), "away_edge": tab.get("AwayH2HEdge"),
                "home_win_pct": tab.get("HomeLineWinPct"), "away_win_pct": tab.get("AwayLineWinPct"),
                "home_odds": tab.get("HomeOdds"), "away_odds": tab.get("AwayOdds"),
                "home_line": tab.get("HomeLine"), "total_line": tab.get("TotalLine"),
                "over_win_pct": tab.get("OverWinPct"), "under_win_pct": tab.get("UnderWinPct"),
            }
    return {}


def fetch_wagerbird_from_gist(max_age_minutes: int = 30) -> list:
    """
    WagerBird free MLB picks (wagerbird.com/picks) via scripts/
    wagerbird_refresh.py — public Next.js RSC page, no auth, parsed via
    regex (not a structured JSON API on their end). Confirmed live
    2026-07-18: 110 real picks parsed from a single run, real matchups/
    odds/graded results. Display-only comparison source, same category
    as Dimers/Covers/BettingPros — not wired into compute_multi_signal_edge.
    MLB only (WagerBird's free picks page covers MLB exclusively).

    Returns the raw "picks" list, each with:
        {sport, matchup, game_time, pick_text, odds, tier, confidence_score,
         rationale, result, pick_date, prediction_url}
    """
    data = _read_gist_file("betcouncil_wagerbird_picks.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("picks", [])
        if isinstance(raw, list):
            return raw
    return []


def get_wagerbird_pick(matchup: str) -> dict:
    """
    Single-game lookup against WagerBird's picks — matches by team
    abbreviation substring against a BetCouncil matchup string, same
    approach as get_dimers_match(). If a game has multiple WagerBird
    picks (moneyline + total, etc.), returns the highest-confidence one
    and notes the count so the caller can indicate more exist.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        picks = fetch_wagerbird_from_gist()
    except Exception:
        picks = []
    if not picks:
        return {}
    matchup_u = matchup.upper()
    game_picks = []
    for p in picks:
        wb_matchup = str(p.get("matchup", "")).upper()
        if not wb_matchup or " @ " not in wb_matchup:
            continue
        away_abv, home_abv = [x.strip() for x in wb_matchup.split(" @ ", 1)]
        if home_abv and away_abv and home_abv in matchup_u and away_abv in matchup_u:
            game_picks.append(p)
    if not game_picks:
        return {}
    game_picks.sort(key=lambda p: p.get("confidence_score") or 0, reverse=True)
    best = game_picks[0]
    return {
        "pick_text": best.get("pick_text"), "odds": best.get("odds"),
        "tier": best.get("tier"), "confidence_score": best.get("confidence_score"),
        "result": best.get("result"), "prediction_url": best.get("prediction_url"),
        "other_picks_count": len(game_picks) - 1,
    }


def fetch_draftedge_from_gist(sport: str, max_age_minutes: int = 100) -> list:
    """
    DraftEdge.com's player props/projections — public SSR JSON, no auth
    (confirmed live 2026-07: /api/{sport}/{sport}props.json). MLB is the
    rich one: per-stat sections (Hits/HR/RBI/TB/SB) each with L5/L15/L30
    hit rates and a projection, plus opposing pitcher ERA/WHIP/K9,
    weather (temp/wind/humidity/description), DFS salary, and injury
    designation, all bundled per player.

    BetCouncil already has its own live weather (LineStar+NWS/wttr.in)
    and park-factor (FanGraphs) pipelines, so this isn't a new signal —
    it's comparison/cross-check context, same tier as FavoredProps.
    Not wired into edge computation.

    Returns the raw "props" list (each entry is one player's full
    record — see get_draftedge_player() for a single-player lookup).
    """
    data = _read_gist_file(f"betcouncil_draftedge_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("props", [])
        if isinstance(raw, list):
            return raw
    return []


def get_draftedge_player(player_name: str, sport: str) -> dict:
    """
    Single-player lookup against DraftEdge's data. Matches on exact name
    first, falls back to last-name substring (same fuzzy pattern used by
    get_player_situational_splits in nfl_features.py).

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        records = fetch_draftedge_from_gist(sport)
    except Exception:
        records = []
    name_l = player_name.lower().strip()
    for row in records:
        if str(row.get("Player", "")).lower().strip() == name_l:
            return row
    last_name = name_l.split()[-1] if name_l.split() else name_l
    for row in records:
        if last_name in str(row.get("Player", "")).lower():
            return row
    return {}


def fetch_mybookie_ssr_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    MyBookie's game lines via their public server-rendered HTML (data-*
    attributes on bet buttons) — no login, no API. Confirmed live
    2026-07-16 via mybookie_refresh.py. This replaced the original
    Tampermonkey MyBookie harvester, which watched for XHR calls
    (/sports_api/leagues-lines, /sports_api/search-props) that the
    current site version doesn't appear to fire anymore.

    Returns the raw "games" list, each a dict with game_id, sport,
    game_date, is_live, and "sides" (per-team spread/moneyline/total
    entries). Game-line comparison data — same category as Dimers/
    BettingPros/Covers, not props.
    """
    data = _read_gist_file(f"betcouncil_mybookie_ssr_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("games", [])
        if isinstance(raw, list):
            return raw
    return []


def get_mybookie_match(matchup: str, sport: str) -> dict:
    """
    Single-game lookup against MyBookie's SSR data. MyBookie's own game
    records use full team names ("New York Mets"), while BetCouncil's
    matchup strings use abbreviations ("NYM @ PHI") — matched via
    TEAM_ABBREV_TO_FRAGMENT (same team-name-fragment table used
    elsewhere in this codebase), checking whether each abbreviation's
    fragment appears in the game's team names.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    frag_map = _TEAM_ABBREV_TO_FRAGMENT_BY_SPORT.get(sport.upper(), {})
    if not frag_map:
        return {}
    matchup_abbrevs = [a for a in frag_map if a in matchup.upper().replace(" @ ", " ").split(" ")]
    if len(matchup_abbrevs) < 2:
        # fall back to substring match against the whole matchup string,
        # in case abbreviations aren't cleanly space-separated
        matchup_abbrevs = [a for a in frag_map if a in matchup.upper()]
    if not matchup_abbrevs:
        return {}
    fragments = [frag_map[a].upper() for a in matchup_abbrevs]

    try:
        games = fetch_mybookie_ssr_from_gist(sport)
    except Exception:
        games = []

    for game in games:
        team_names_u = " ".join(
            str(s.get("team", "")) + " " + str(s.get("vs", "")) for s in game.get("sides", [])
        ).upper()
        if all(frag in team_names_u for frag in fragments):
            sp_side = next((s for s in game.get("sides", []) if s.get("type") == "sp"), None)
            ml_side = next((s for s in game.get("sides", []) if s.get("type") == "ml"), None)
            to_side = next((s for s in game.get("sides", []) if s.get("type") == "to"), None)
            return {
                "game_id": game.get("game_id"), "is_live": game.get("is_live"),
                "spread_team": sp_side.get("team") if sp_side else None,
                "spread_points": sp_side.get("points") if sp_side else None,
                "spread_odds": sp_side.get("odds") if sp_side else None,
                "ml_team": ml_side.get("team") if ml_side else None,
                "ml_odds": ml_side.get("odds") if ml_side else None,
                "total_points": to_side.get("points") if to_side else None,
                "total_odds": to_side.get("odds") if to_side else None,
            }
    return {}


def fetch_vegasinsider_consensus_from_gist(sport: str = "MLB", max_age_minutes: int = 60) -> dict:
    """
    VegasInsider's public betting trends (public %, SU/OU/ATS records) +
    consensus lines (opening vs current) — no login, no API. Confirmed
    live 2026-07-16 via vegasinsider_refresh.py, MLB only right now
    (same as the investigation covered). CSS display-gate only, same
    pattern as MyBookie/RotoGrinders — the data is present in the
    unauthenticated response, just visually hidden on the live site for
    non-members.

    Named "_consensus_" rather than the more obvious
    fetch_vegasinsider_from_gist — that name is already used by an older
    dead stub (board-load dispatch table entry from the June 29 bulk
    add, expects a per-sport gist file that was never populated).
    Reusing it would have created a same-name collision where Python
    resolves to whichever definition is later in the file, silently
    breaking one of the two callers.

    Returns {} if sport isn't MLB or no fresh data — treat as "no data,"
    not "confirmed absent." Returns the raw {"trends": [...], "consensus":
    [...]} dict otherwise.
    """
    if sport.upper() != "MLB":
        return {}
    data = _read_gist_file("betcouncil_vegasinsider.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        return data
    return {}


def get_vegasinsider_match(matchup: str, sport: str = "MLB") -> dict:
    """
    Single-game lookup against VegasInsider's trends + consensus data.
    VegasInsider's own records use team abbreviations directly ("NYM",
    "PHI"), same format BetCouncil's matchup strings already use — no
    fragment-mapping needed here, unlike MyBookie/Dimers.

    Uses fetch_vegasinsider_consensus_from_gist(), not
    fetch_vegasinsider_from_gist() — that name was already taken by an
    older dead stub (part of the June 29 bulk-add batch, registered in
    the board-load dispatch table expecting a (data, source) tuple from
    a per-sport gist file that was never populated). Reusing that name
    here would have silently shadowed one function or the other
    depending on definition order — renamed instead of touching the
    shared dispatcher.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        data = fetch_vegasinsider_consensus_from_gist(sport)
    except Exception:
        data = {}
    if not data:
        return {}

    matchup_u = matchup.upper()
    result = {}

    for consensus in data.get("consensus", []):
        away, home = consensus.get("away_team", ""), consensus.get("home_team", "")
        if away and home and away.upper() in matchup_u and home.upper() in matchup_u:
            result.update({
                "open_ml": consensus.get("open_ml"), "open_total": consensus.get("open_total"),
                "open_spread": consensus.get("open_spread"),
                "consensus_ml": consensus.get("consensus_ml"), "consensus_total": consensus.get("consensus_total"),
                "consensus_spread": consensus.get("consensus_spread"),
            })
            break

    trend_rows = [t for t in data.get("trends", []) if str(t.get("team", "")).upper() in matchup_u]
    if trend_rows:
        result["trends"] = trend_rows

    return result


def fetch_rotogrinders_lineups_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    RotoGrinders' lineup confirmation + DFS projected points (pfpts) —
    public JSON, no auth (confirmed live 2026-07-16 via
    rotogrinders_refresh.py). Real prop-picks tools are fully paywalled
    (checked — no free preview at all), but the lineups.json endpoint is
    genuinely open.

    Named "_lineups_" rather than the more obvious
    fetch_rotogrinders_from_gist — that name is already used by an older
    dead stub (board-load dispatch table entry from the June 29 bulk
    add, expects a per-sport gist file that was never populated), same
    collision issue found and worked around for VegasInsider.

    This is lineup-confirmation + DFS-projection context, not a pick —
    same category as LineStar/Situational Splits, belongs in Player
    Lookup, not the New Bettor comparison panel.

    Returns [] if no fresh data — treat as "no data," not "confirmed
    absent."
    """
    data = _read_gist_file(f"betcouncil_rotogrinders_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("records", [])
        if isinstance(raw, list):
            return raw
    return []


def get_rotogrinders_player(player_name: str, sport: str) -> dict:
    """
    Single-player lookup against RotoGrinders' lineup data. Matches on
    exact name first, falls back to last-name substring (same fuzzy
    pattern used by get_player_situational_splits/get_draftedge_player).

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        records = fetch_rotogrinders_lineups_from_gist(sport)
    except Exception:
        records = []
    name_l = player_name.lower().strip()
    for row in records:
        if str(row.get("player", "")).lower().strip() == name_l:
            return row
    last_name = name_l.split()[-1] if name_l.split() else name_l
    for row in records:
        if last_name in str(row.get("player", "")).lower():
            return row
    return {}


def fetch_sportsinsights_trends_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    Sports Insights' public ticket-percentage betting trends — no login,
    no API key. Confirmed live 2026-07-17 via sportsinsights_refresh.py,
    matches Sports Insights' own marketing copy which explicitly calls
    out "money percentages" as the premium unlock (the free data here is
    ticket %, not money %, exactly as advertised).

    Named "_trends_" rather than the more obvious
    fetch_sportsinsights_from_gist — that name is already used by an
    older dead stub (board-load dispatch table entry from the June 29
    bulk add, expects a per-sport gist file that was never populated),
    same collision pattern found and worked around for VegasInsider/
    RotoGrinders.

    Returns [] if no fresh data — treat as "no data," not "confirmed
    absent."
    """
    data = _read_gist_file(f"betcouncil_sportsinsights_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("games", [])
        if isinstance(raw, list):
            return raw
    return []


def get_sportsinsights_match(matchup: str, sport: str) -> dict:
    """
    Single-game lookup against Sports Insights' ticket-% data. Uses team
    abbreviations directly ("PHI", "NYM"), same format BetCouncil's
    matchup strings already use.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        games = fetch_sportsinsights_trends_from_gist(sport)
    except Exception:
        games = []
    matchup_u = matchup.upper()
    for game in games:
        home_abv, away_abv = str(game.get("home_abv", "")).upper(), str(game.get("away_abv", "")).upper()
        if home_abv and away_abv and home_abv in matchup_u and away_abv in matchup_u:
            return game
    return {}


def fetch_scoresandodds_multibook_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    ScoresAndOdds' 11-book multi-book odds comparison (Action Network's
    public Lambda, no auth) — confirmed live 2026-07-17, event ID
    cross-validated against 4 other independently-verified sources this
    session before build.

    Named "_multibook_" rather than the more obvious
    fetch_scoresandodds_from_gist — that name is already used by an
    older dead stub (board-load dispatch table entry from the June 29
    bulk add), same collision pattern found and worked around for
    VegasInsider/RotoGrinders/Sports Insights.

    Returns [] if no fresh data — treat as "no data," not "confirmed
    absent."
    """
    data = _read_gist_file(f"betcouncil_scoresandodds_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("games", [])
        if isinstance(raw, list):
            return raw
    return []


def get_scoresandodds_match(matchup: str, sport: str) -> dict:
    """
    Single-game lookup against ScoresAndOdds' multi-book data. Uses team
    abbreviations directly ("PHI", "NYM"), same format BetCouncil's
    matchup strings already use.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        games = fetch_scoresandodds_multibook_from_gist(sport)
    except Exception:
        games = []
    matchup_u = matchup.upper()
    for game in games:
        home_abv, away_abv = str(game.get("home_team", "")).upper(), str(game.get("away_team", "")).upper()
        if home_abv and away_abv and home_abv in matchup_u and away_abv in matchup_u:
            return game
    return {}


def fetch_pickswise_picks_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    Pickswise's expert picks + consensus odds — no login, no paywall on
    any field (confirmed 2026-07-17 via pickswise_refresh.py). Same site
    as pickwise.com (a plain alias, not a different product).

    Named "_picks_" rather than the more obvious
    fetch_pickswise_from_gist — that name is already used by an older
    dead stub (board-load dispatch table entry from the June 29 bulk
    add), same collision pattern found and worked around for
    VegasInsider/RotoGrinders/Sports Insights/ScoresAndOdds.

    Note: pick_rating/pick_side/pick_bet/pick_playable_to will be None
    for games Pickswise hasn't published a pick article for yet
    (confirmed via live testing — only imminent games reliably have
    picks; further-out games return real odds but no pick yet). That's
    real data sparsity, not a bug — treat a None pick as "not published
    yet," not "confirmed no pick."

    Returns [] if no fresh data.
    """
    data = _read_gist_file(f"betcouncil_pickswise_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("games", [])
        if isinstance(raw, list):
            return raw
    return []


def get_pickswise_match(matchup: str, sport: str) -> dict:
    """
    Single-game lookup against Pickswise's picks/odds data. Uses team
    abbreviations directly ("PHI", "NYM"), same format BetCouncil's
    matchup strings already use.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        games = fetch_pickswise_picks_from_gist(sport)
    except Exception:
        games = []
    matchup_u = matchup.upper()
    for game in games:
        home_abv, away_abv = str(game.get("home_team", "")).upper(), str(game.get("away_team", "")).upper()
        if home_abv and away_abv and home_abv in matchup_u and away_abv in matchup_u:
            return game
    return {}


def fetch_actionnetwork_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    Action Network's scoreboard API (game odds across 4+ books, starting
    pitcher stats, standings, rotation numbers) — confirmed live
    2026-07-17 via actionnetwork_refresh.py. Same open backend already
    confirmed powering Sports Insights/RotoGrinders/VegasInsider/
    ScoresAndOdds — the flagship AN site is WAF bot-gated, but this API
    subdomain isn't.

    Note: this is a distinct function from the existing (unrelated)
    fetch_action_network_public_betting()/fetch_action_network_lines()
    in this file, which hit different Action Network endpoints (public
    betting %, a different lines path). fetch_action_network_public_
    betting was renamed (2026-07-17) from fetch_action_network_props
    specifically because that name collided with a different, real,
    already-in-use function of the same name in app.py (prop
    projections, not public betting %) — since app.py does
    `from fetchers import *` and then defines its own version after,
    app.py's always won, leaving this one permanently unreachable under
    the shared name. Fixed by renaming; app.py's own version is
    untouched and behaves exactly as before.

    Returns [] if no fresh data.
    """
    data = _read_gist_file(f"betcouncil_actionnetwork_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("games", [])
        if isinstance(raw, list):
            return raw
    return []


def get_actionnetwork_match(matchup: str, sport: str) -> dict:
    """
    Single-game lookup against Action Network's scoreboard data. Uses
    team abbreviations directly ("PHI", "NYM"), same format BetCouncil's
    matchup strings already use.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        games = fetch_actionnetwork_from_gist(sport)
    except Exception:
        games = []
    matchup_u = matchup.upper()
    for game in games:
        home_abv, away_abv = str(game.get("home_team", "")).upper(), str(game.get("away_team", "")).upper()
        if home_abv and away_abv and home_abv in matchup_u and away_abv in matchup_u:
            return game
    return {}


def fetch_wiseguyteam_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    WiseGuyTeam sharp report -- sharp_flags/has_sharp on each game are
    free and real (which side sharp/big money is leaning); the actual
    named "play" (wgt_play) is member-only and its side is hidden.
    Stored merged into betcouncil_evbets_combined.json under a
    "wiseguyteam" key (standalone per-sport files confirmed to never
    successfully land on this Gist -- see scripts/wiseguyteam_refresh.py).
    """
    combined = _read_gist_file("betcouncil_evbets_combined.json", cache_minutes=10)
    data = (combined or {}).get("wiseguyteam", {}).get(sport.upper())
    if not data or not isinstance(data, dict):
        return []
    games = data.get("games", [])
    return games if isinstance(games, list) else []


ESPN_LOGO_SPORT_PATHS = {
    "MLB": "baseball/mlb", "NBA": "basketball/nba", "NFL": "football/nfl",
    "NHL": "hockey/nhl", "WNBA": "basketball/wnba",
}


def fetch_espn_team_logos(sport: str) -> dict:
    """
    Real team logo URLs from ESPN's own public teams API -- confirmed
    live 2026-08-03, no auth. Keyed by every name variant ESPN itself
    provides (displayName, shortDisplayName, name, location, abbreviation)
    so callers can match against whatever team-name format they have on
    hand without guessing abbreviations. Cached 7 days locally -- team
    logos/rosters don't change intra-season.
    """
    path = ESPN_LOGO_SPORT_PATHS.get(sport.upper())
    if not path:
        return {}
    cp = os.path.join(CACHE_DIR, f"espn_logos_{sport.lower()}.pkl")
    if os.path.exists(cp) and (time.time() - os.path.getmtime(cp)) / 60 < 10080:
        c = _safe_load_pkl(cp)
        if c is not None:
            return c
    try:
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams", timeout=15)
        if r.status_code != 200:
            return {}
        teams = r.json().get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        logos = {}
        for t in teams:
            team = t.get("team", {})
            logo_url = (team.get("logos") or [{}])[0].get("href", "")
            if not logo_url:
                continue
            for key in (team.get("displayName"), team.get("shortDisplayName"),
                        team.get("name"), team.get("location"), team.get("abbreviation")):
                if key:
                    logos[key] = logo_url
        if logos:
            _safe_save_pkl(cp, logos)
        return logos
    except Exception:
        return {}


def fetch_betql_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    BetQL's public GraphQL events query (multi-book lines, and — rare
    across sources this session — team season W/L AND against-the-
    spread W/L records) — confirmed live 2026-07-17 via
    betql_refresh.py.

    Returns [] if no fresh data.
    """
    data = _read_gist_file(f"betcouncil_betql_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("games", [])
        if isinstance(raw, list):
            return raw
    return []


def get_betql_match(matchup: str, sport: str) -> dict:
    """
    Single-game lookup against BetQL's data. Uses team abbreviations
    directly ("PHI", "NYM"), same format BetCouncil's matchup strings
    already use.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    """
    try:
        games = fetch_betql_from_gist(sport)
    except Exception:
        games = []
    matchup_u = matchup.upper()
    for game in games:
        home_abv, away_abv = str(game.get("home_team", "")).upper(), str(game.get("away_team", "")).upper()
        if home_abv and away_abv and home_abv in matchup_u and away_abv in matchup_u:
            return game
    return {}


def fetch_dk_most_bet_props(sport: str, max_rows: int = 15) -> list:
    """
    DK Network's public "Most Bet Player Props" page — no login, no
    Tampermonkey needed, updated ~every 5 min. This is PUBLIC BETTING
    POPULARITY (what the crowd is stacking their bet slips with by
    handle), NOT DraftKings' own recommendation — label it that way
    wherever it's shown.

    Sport-filters the scraped rows by matching a known team abbreviation
    (TEAM_ABBREV_TO_FRAGMENT) inside the "AWAY @ HOME" event string DK
    Network uses (e.g. "TEX Rangers @ DET Tigers").
    """
    try:
        import requests as _req
        from bs4 import BeautifulSoup as _BS
    except Exception:
        return []
    try:
        r = _req.get(
            "https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                     "Accept": "text/html,application/xhtml+xml"},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        soup = _BS(r.text, "html.parser")
        table = soup.find("table")
        if not table:
            return []
        abbrev_map = _TEAM_ABBREV_TO_FRAGMENT_BY_SPORT.get(sport.upper(), {})
        results = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            event = cells[0].get_text(strip=True)
            if abbrev_map and not any(a in event for a in abbrev_map):
                continue  # not this sport
            results.append({
                "Sport": sport,
                "Event": event,
                "EventDate": cells[1].get_text(strip=True),
                "Market": cells[2].get_text(strip=True),
                "Pick": cells[3].get_text(strip=True),
                "Odds": cells[4].get_text(strip=True) if len(cells) > 4 else "",
            })
            if len(results) >= max_rows:
                break
        return results
    except Exception as e:
        print(f"[WARN] fetch_dk_most_bet_props: {e}")
        return []


def fetch_fanduel_parlayhub_from_gist(sport: str, max_age_minutes: int = 60) -> list:
    """
    Reads FanDuel's "Parlay Hub" (curated popular same-game-parlay picks;
    login-gated in FanDuel's own app) from the Gist file pushed by
    scripts/tampermonkey_fanduel_parlayhub_harvester.user.js while you
    browse Parlay Hub in your own authenticated FanDuel tab. No Parlay
    Hub API is public — this is the only path to it, same pattern as
    the existing BetMGM/FanDuel-props browser harvesters.

    2026-07-16 fix: confirmed the real response shape via a live capture
    — it's a nested dict ({"popularBettingOpportunities": [...],
    "attachments": {"markets": {...}, "events": {...}}}), not a flat
    list as originally assumed. This now parses it into clean records
    (narrative/teams/odds/totalBets) via _parse_fanduel_parlayhub()
    instead of returning the raw nested structure.

    Returns [] if the harvester hasn't pushed anything recently (no
    forced/fake data).
    """
    data = _read_gist_file(f"betcouncil_fd_parlayhub_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("data", {})
        if isinstance(raw, dict) and raw.get("popularBettingOpportunities"):
            return _parse_fanduel_parlayhub(raw)
        if isinstance(raw, list) and raw:
            return raw  # legacy/unexpected-shape fallback
    return []


def _parse_fanduel_parlayhub(raw: dict) -> list:
    """
    Turns FanDuel's raw betting-opportunities/all response into clean,
    display-ready records. Each popularBettingOpportunities entry already
    carries americanOdds/totalBets/type directly; team names come from
    the entry itself (SGP type) or get resolved via the attachments.markets
    block (PARLAY type, where team info sits on the market's runners).
    """
    opportunities = raw.get("popularBettingOpportunities", [])
    markets = raw.get("attachments", {}).get("markets", {})

    records = []
    for opp in opportunities:
        matchup = opp.get("abbreviatedEventNameShort", "")
        if not matchup:
            home = opp.get("homeTeam", {}).get("abbrName")
            away = opp.get("awayTeam", {}).get("abbrName")
            if home and away:
                matchup = f"{away} @ {home}"
        if not matchup:
            # PARLAY entries often span multiple games — pull team names
            # from the first selection's market, if attached.
            for sel in opp.get("selections", []):
                mkt = markets.get(sel.get("marketId", ""), {})
                for runner in mkt.get("runners", []):
                    home = runner.get("homeTeam", {}).get("abbrName")
                    away = runner.get("awayTeam", {}).get("abbrName")
                    if home and away:
                        matchup = f"{away} @ {home}"
                        break
                if matchup:
                    break

        records.append({
            "type": opp.get("type", ""),
            "narrative": opp.get("narrative", ""),
            "matchup": matchup,
            "total_bets": opp.get("totalBets", 0),
            "american_odds": opp.get("americanOdds"),
            "num_legs": len(opp.get("selections", [])),
        })

    records.sort(key=lambda r: r.get("total_bets", 0), reverse=True)
    return records


def fetch_favoredprops_from_gist(kind: str, sport: str, max_age_minutes: int = 100) -> list:
    """
    Reads FavoredProps' public props data (no login, no key — confirmed
    live 2026-07 via direct API discovery: /api/dfs and /api/sportsbook
    are unauthenticated Next.js API routes) from the Gist file pushed by
    the FavoredProps harvester workflow, every 15 min.

    kind: "dfs" (PrizePicks/Underdog-style ranked picks with hit rates)
          or "sportsbook" (multi-book player props with hit rates)
    sport: BetCouncil sport name — NBA, MLB, NHL, WNBA map directly;
           NFL isn't in FavoredProps' current league set (CBB/CFB used
           for college instead), so NFL calls will just return [].

    Returns the raw "props" list from that file, each entry already
    including hit-rate fields (l5_hit_rate, l10_hit_rate, szn_hit_rate,
    h2h_hit_rate) and multi-book odds (books list). Comparison/display
    data only — never wired into SEM or edge computation.
    """
    if kind not in ("dfs", "sportsbook"):
        return []
    data = _read_gist_file(f"betcouncil_favoredprops_{kind}_{sport.upper()}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=max_age_minutes):
        raw = data.get("props", [])
        if isinstance(raw, list):
            return raw
    return []


def get_favoredprops_match(player: str, stat: str, sport: str, side: str = None) -> dict:
    """
    Single-leg lookup against FavoredProps' sportsbook + dfs data — used
    by Slip Analyzer and Player Lookup to cross-check one pick at a time
    (rather than pulling the full list, like build_market_comparison
    does for the New Bettor shortlist).

    Matches on normalized player name + fuzzy stat_type substring match
    (FavoredProps' stat names don't always match BetCouncil's exactly,
    e.g. "Total Bases" vs "TB"). Prefers a side (Over/Under) match when
    `side` is given, but falls back to any line for that player+stat if
    no side match — better to show mismatched-side context than none.

    Returns {} if no match — treat as "no data," not "confirmed absent."
    Display/comparison only, same as everywhere else FavoredProps is used.
    """
    player_l = str(player).lower().strip()
    stat_l = str(stat).lower().strip()
    side_l = str(side).lower().strip() if side else None

    best = {}
    for kind in ("sportsbook", "dfs"):
        try:
            rows = fetch_favoredprops_from_gist(kind, sport)
        except Exception:
            rows = []
        for row in rows:
            if str(row.get("player", "")).lower().strip() != player_l:
                continue
            row_stat_l = str(row.get("stat_type", "")).lower()
            if stat_l not in row_stat_l and row_stat_l not in stat_l:
                continue
            row_bet = str(row.get("bet", "")).lower()
            if side_l and row_bet and side_l[0] == row_bet[0]:  # "over"/"o" match
                return {**row, "kind": kind}
            if not best:
                best = {**row, "kind": kind}
    return best


def fetch_unabated_from_gist(sport: str) -> tuple:
    """PRIMARY: Unabated sharp lines from browser harvester. SECONDARY: scraper."""
    data = _read_gist_file(f"betcouncil_unabated_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=32):
        raw = data.get("data",{})
        if raw:
            print(f"[Unabated] PRIMARY: browser harvester")
            return raw, "browser_harvester"
    try:
        from fetchers import fetch_unabated_lines as _fu
        s = _fu(sport)
        if s: return s, "scraper_fallback"
    except Exception: pass
    return {}, "unavailable"


def fetch_unabated_props(sport: str, platform: str = None) -> tuple:
    """
    Unabated player-props fair-value data (PrizePicks/Underdog/Pick6 lines,
    sourced via Unabated's unabated_data_api), pushed per-platform per-sport
    by the browser harvester as betcouncil_unabated_{platform}_{sport}.json.

    This is NOT the same feature as fetch_unabated_from_gist above, which reads
    game-level sharp lines (spreads/totals/moneylines) from a different
    Unabated endpoint. Do not merge the two.

    The scraper already filters out events that started more than 2 hours ago
    before pushing, and skips writing a file entirely for a sport/platform
    combo with zero surviving lines (e.g. off-season leagues). So an empty
    result here can legitimately mean "nothing fresh" rather than a failure.

    Args:
        sport: league code, e.g. "MLB", "WNBA", "NFL", "NHL".
        platform: "prizepicks" | "underdog" | "pick6", or None for all three
                  merged together (each line tagged with its "platform").

    Returns (lines: list[dict], source: str). source is "unabated_props" if
    any fresh data was found, else "unavailable".
    """
    platforms = [platform] if platform else ["prizepicks", "underdog", "pick6"]
    combined = []
    for p in platforms:
        fname = f"betcouncil_unabated_{p}_{sport}.json"
        data = _read_gist_file(fname, cache_minutes=10)
        if not data:
            continue
        if not _is_fresh(data, max_age_minutes=180):
            continue
        plat_label = data.get("platform", p.title())
        for line in data.get("lines", []):
            line = dict(line)
            line["platform"] = plat_label
            combined.append(line)
    if combined:
        return combined, "unabated_props"
    return [], "unavailable"


def get_harvester_status(sport: str = "MLB") -> dict:
    """
    Real-time status of ALL browser harvesters.
    Returns dict: {source_name: {active, age_minutes, source, warning}}
    Shown in BetCouncil sidebar — tells you exactly which sources are live vs stale.

    BUG FIX (2026-07): every filename below used to be hardcoded to "_MLB"
    regardless of which sport's board was actually loaded -- so loading a
    WNBA (or NBA/NFL/NHL) board always checked MLB's harvester gist files,
    which are legitimately empty/stale outside MLB season/slate, making
    every sport-specific harvester (FanDuel props, BetMGM props, DraftKings
    props, Unabated, Action Network, Covers, etc.) permanently show
    "Pending — load a board to activate" no matter how many boards were
    loaded. Now takes the current sport and checks that sport's files.
    """
    checks = [
        ("Scanbet (Pinnacle drops)",    "betcouncil_scanbet_drops.json",     10),
        ("EVSharps JWT",                "betcouncil_tokens.json",             55),
        ("Caesars WAF",                 "betcouncil_caesars_tokens.json",     22),
        ("FanDuel props",               f"betcouncil_fd_props_{sport}.json",       28),
        ("BetMGM props",                f"betcouncil_mgm_props_{sport}.json",      28),
        ("Action Network",              f"betcouncil_actionnetwork_{sport}.json",  18),
        ("Covers.com consensus",        f"betcouncil_covers_{sport}.json",         22),
        ("DraftKings props",            f"betcouncil_dk_props_{sport}.json",       22),
        ("Unabated sharp lines",        f"betcouncil_unabated_{sport}.json",       32),
        ("Unabated props (PrizePicks)", f"betcouncil_unabated_prizepicks_{sport}.json", 180),
        ("Unabated props (Underdog)",   f"betcouncil_unabated_underdog_{sport}.json",   180),
        ("Unabated props (Pick6)",      f"betcouncil_unabated_pick6_{sport}.json",      180),
        ("OddsJam +EV",                 f"betcouncil_oddsjam_{sport}.json",        22),
        ("PrizePicks props",             f"betcouncil_prizepicks_{sport}.json",     22),
        ("MyBookie lines",               f"betcouncil_mybookie_{sport}.json",       28),
        ("ParlaySavant +EV",             f"betcouncil_parlaysavant_{sport}.json",   22),
        ("Bet365 lines",                 "betcouncil_bet365_games.json",       28),
        ("SportsInsights steam",         f"betcouncil_sportsinsights_{sport}.json", 18),
        ("OddsShark consensus",          f"betcouncil_oddsshark_{sport}.json",      22),
        ("VegasInsider lines",           f"betcouncil_vegasinsider_{sport}.json",   22),
        ("Props.cash cross-book",        f"betcouncil_propscash_{sport}.json",      22),
        ("BaseballPress lineups",        "betcouncil_baseballpress.json",       18),
        ("BettingPros consensus",        f"betcouncil_bettingpros_{sport}.json",    22),
        ("Stokastic DFS proj",           f"betcouncil_stokastic_{sport}.json",      32),
        ("RotoGrinders ownership",       f"betcouncil_rotogrinders_{sport}.json",   32),
        ("OddsPortal history",           f"betcouncil_oddsportal_{sport}.json",     65),
        ("Outlier +EV",                  f"betcouncil_outlier_{sport}.json",        22),
        ("Smarkets exchange",            f"betcouncil_smarkets_{sport}.json",       28),
        ("Pickwise props",               f"betcouncil_pickwise_{sport}.json",       22),
        ("Weather data",                 f"betcouncil_weather_{sport}.json",        65),
        ("ScoresAndOdds %",              f"betcouncil_scoresandodds_{sport}.json",  18),
        ("Kalshi markets",               f"betcouncil_kalshi2_{sport}.json",        32),
        ("Pregame sharp plays",          f"betcouncil_pregame_{sport}.json",        32),
        ("FantasyLabs ownership",        f"betcouncil_fantasylabs_{sport}.json",    32),
        ("Rotowire injuries",            f"betcouncil_rotowire_{sport}.json",       18),
        ("NumberFire projections",       f"betcouncil_numberfire_{sport}.json",     32),
        ("Pickswise expert picks",       f"betcouncil_pickswise_{sport}.json",      32),
        ("BetUS props",                  f"betcouncil_betus_{sport}.json",          28),
        ("Bet105 lines",                 f"betcouncil_bet105_{sport}.json",         28),
        ("BetWhale lines",               f"betcouncil_betwhale_{sport}.json",       28),
        ("Ybets lines",                  f"betcouncil_ybets_{sport}.json",          28),
        ("Zamba lines",                  f"betcouncil_zamba_{sport}.json",          28),
        ("EVBets +EV feed",              f"betcouncil_evbets_{sport}.json",         22),
        ("EVBets props +EV",             f"betcouncil_evbets_props_{sport}.json",   22),
    ]
    from datetime import datetime, timezone
    status = {}
    for name, filename, max_age in checks:
        try:
            data = _read_gist_file(filename, cache_minutes=2)
            if not data:
                status[name] = {"active":False,"age_minutes":None,
                                "source":"none",
                                "warning":"⚪ No data yet — load a board first"}
                continue
            ts    = data.get("captured_at","")
            age   = None
            fresh = False
            if ts:
                try:
                    captured = datetime.fromisoformat(ts.replace("Z","+00:00"))
                    age      = round((datetime.now(timezone.utc)-captured).total_seconds()/60,1)
                    fresh    = age <= max_age
                except Exception: pass
            src = data.get("source","unknown")
            n_lines = len(data.get("lines", [])) if isinstance(data.get("lines"), list) else None
            status[name] = {
                "active":      fresh,
                "age_minutes": age,
                "source":      src,
                "count":       n_lines,
                "warning":     ("" if fresh
                                else f"🟡 Stale ({age}min) — reload BetCouncil to refresh"),
            }
        except Exception as e:
            status[name] = {"active":False,"age_minutes":None,
                            "source":"error","warning":f"🔴 Error: {str(e)[:50]}"}

    # ── Paddy Power (direct HTML harvest — local pkl cache, not gist-backed) ──
    try:
        _pp_files = [f for f in os.listdir(CACHE_DIR) if f.startswith("paddypower_") and f.endswith(".pkl")]
        if not _pp_files:
            status["Paddy Power (direct)"] = {
                "active": False, "age_minutes": None, "source": "none",
                "warning": "⚪ No data yet — load a board first",
            }
        else:
            _newest = max(_pp_files, key=lambda f: os.path.getmtime(os.path.join(CACHE_DIR, f)))
            _age = round((time.time() - os.path.getmtime(os.path.join(CACHE_DIR, _newest))) / 60, 1)
            _fresh = _age <= 10
            try:
                _n_games = len(_safe_load_pkl(os.path.join(CACHE_DIR, _newest)) or [])
            except Exception:
                _n_games = 0
            status["Paddy Power (direct)"] = {
                "active": _fresh and _n_games > 0,
                "age_minutes": _age,
                "source": "html_harvest",
                "warning": ("" if (_fresh and _n_games > 0)
                            else (f"🟡 Stale ({_age}min) — reload BetCouncil to refresh" if _fresh is False
                                  else "🔴 Last fetch returned 0 games — parser may need a selector update")),
            }
    except Exception as e:
        status["Paddy Power (direct)"] = {"active": False, "age_minutes": None,
                                           "source": "error", "warning": f"🔴 Error: {str(e)[:50]}"}

    return status



def fetch_prizepicks_from_gist(sport: str) -> tuple:
    """
    PRIMARY: PrizePicks props from browser harvester.
    SECONDARY: Falls back to fetch_prizepicks_props() CDN scraper.
    Returns (props_list, source_label)
    """
    data = _read_gist_file(f"betcouncil_prizepicks_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=100):
        raw = data.get("data",{})
        if raw:
            props = _parse_prizepicks_harvested(raw, sport)
            if props:
                print(f"[PrizePicks] PRIMARY: {len(props)} props from browser harvester")
                return props, "browser_harvester"
    try:
        secondary = scrape_prizepicks(sport)
        if secondary:
            print(f"[PrizePicks] SECONDARY: {len(secondary)} props from CDN scraper")
            return secondary, "scraper_fallback"
    except Exception:
        pass
    return [], "unavailable"


def _parse_prizepicks_harvested(raw, sport: str) -> list:
    """Parse PrizePicks api.prizepicks.com/projections response format."""
    results = []
    try:
        items    = raw if isinstance(raw, list) else raw.get("data", [])
        included = raw.get("included", []) if isinstance(raw, dict) else []
        players  = {}
        for inc in included:
            if isinstance(inc, dict) and inc.get("type") in ("new_player","player"):
                pid  = inc.get("id","")
                attr = inc.get("attributes",{})
                players[pid] = {"name":attr.get("name","") or attr.get("display_name",""),"team":attr.get("team","") or attr.get("market",""),
                                "position":attr.get("position","")}
        for item in items:
            if not isinstance(item, dict): continue
            attr      = item.get("attributes",{})
            line      = attr.get("line_score", attr.get("line"))
            stat_type = attr.get("stat_type","")
            desc      = attr.get("description","")
            rels      = item.get("relationships",{})
            p_rel     = rels.get("new_player", rels.get("player",{}))
            pid       = p_rel.get("data",{}).get("id","") if isinstance(p_rel.get("data"),dict) else ""
            pinfo     = players.get(pid, {})
            pname     = pinfo.get("name","") or desc
            if not pname or not stat_type or line is None: continue
            odds_type = attr.get("odds_type", "standard")
            results.append({
                "Player":    pname,
                "Prop":      stat_type,
                "Line":      line,
                "OverOdds":  "-110",
                "UnderOdds": "-110",
                "Team":      pinfo.get("team",""),
                "Book":      "PrizePicks",
                "Sport":     sport,
                "source":    "prizepicks_browser_harvest",
                # Real field from PrizePicks projections API — was previously
                # discarded here even though the CDN scraper fallback path
                # already captured it. standard/goblin/demon drives payout
                # difficulty tiering; -110 above is a display placeholder,
                # NOT PrizePicks' real pricing (PrizePicks doesn't post
                # American-odds juice — payout structure IS the price).
                "OddsType":  odds_type,
            })
    except Exception as e:
        print(f"[WARN] _parse_prizepicks_harvested: {e}")
    return results



def fetch_underdog_from_gist(sport: str) -> tuple:
    """PRIMARY: Underdog props merged into betcouncil_evbets_combined.json
    (per-sport standalone files confirmed to never successfully land on
    this Gist -- see push_sport_files in underdog_ssr_scraper.py).
    SECONDARY: scraper."""
    combined = _read_gist_file("betcouncil_evbets_combined.json", cache_minutes=5)
    data = (combined or {}).get("underdog", {}).get(sport)
    if data and _is_fresh(data, max_age_minutes=100):
        raw = data.get("data",{})
        if raw:
            props = _parse_underdog_harvested(raw, sport)
            if props: return props, "browser_harvester"
    try:
        from fetchers import fetch_underdog_props as _f
        s = _f(sport)
        if s: return s, "scraper_fallback"
    except Exception: pass
    return [], "unavailable"

def _parse_underdog_harvested(raw, sport: str) -> list:
    """Parse Underdog beta/v5/over_under_lines."""
    results = []
    try:
        lines   = raw.get("over_under_lines", raw if isinstance(raw,list) else [])
        players = {p["id"]:p for p in raw.get("players",[]) if isinstance(p,dict)}
        for line in (lines if isinstance(lines,list) else []):
            if not isinstance(line,dict): continue
            pid   = line.get("player_id","")
            pinfo = players.get(pid,{})
            name  = (pinfo.get("first_name","") + " " + pinfo.get("last_name","")).strip() or line.get("title","")
            stat  = line.get("stat_value","")
            if not name or not stat: continue
            results.append({"Player":name,"Prop":line.get("stat_type",""),"Line":stat,
                            "OverOdds":"3x","UnderOdds":"3x","Book":"Underdog","Sport":sport,
                            "source":"underdog_browser_harvest"})
    except Exception as e:
        print(f"[WARN] _parse_underdog_harvested: {e}")
    return results


def _parse_bovada_props_harvested(raw, sport: str) -> list:
    """
    Parse Bovada coupon API response (betcouncil_bovada_{sport}.json) for player props.
    
    Expected raw shape (same as fetch_bovada_game_lines API):
      [{events: [{competitors: [...], displayGroups: [{markets: [
          {description: str, outcomes: [{description: str, price: {american, handicap}}]}
      ]}]}]}]
    
    Player-specific markets are identified by having a single competitor or by a
    " - " delimiter in the market description (e.g. "Josh Allen - Passing Yards").
    """
    results = []
    try:
        groups = raw if isinstance(raw, list) else raw.get("data", raw.get("groups", []))
        if not isinstance(groups, list):
            groups = [groups]
        for group in groups:
            for event in (group.get("events", []) if isinstance(group, dict) else []):
                competitors = event.get("competitors", [])
                # Single-competitor event = individual player market (rare but valid)
                solo_player = competitors[0].get("name", "") if len(competitors) == 1 else ""
                for dg in event.get("displayGroups", []):
                    for market in dg.get("markets", []):
                        market_desc = market.get("description", "")
                        # Extract player name from "Player Name - Stat Type" format
                        if " - " in market_desc:
                            parts     = market_desc.split(" - ", 1)
                            player    = parts[0].strip()
                            prop_name = parts[1].strip()
                        elif solo_player:
                            player    = solo_player
                            prop_name = market_desc
                        else:
                            continue
                        over_odds = under_odds = None
                        line = None
                        for oc in market.get("outcomes", []):
                            label    = oc.get("description", "")
                            price    = oc.get("price", {}) if isinstance(oc.get("price"), dict) else {}
                            american = price.get("american", "")
                            handicap = price.get("handicap", oc.get("attr", ""))
                            if handicap is not None and line is None:
                                try:
                                    line = float(str(handicap).replace("+", ""))
                                except (ValueError, TypeError):
                                    pass
                            lbl = label.lower()
                            if "over" in lbl:
                                over_odds = american
                            elif "under" in lbl:
                                under_odds = american
                        if not player or line is None:
                            continue
                        results.append({
                            "Player":    player,
                            "Prop":      prop_name,
                            "Line":      line,
                            "OverOdds":  over_odds  or "N/A",
                            "UnderOdds": under_odds or "N/A",
                            "Book":      "Bovada",
                            "Sport":     sport,
                            "source":    "bovada_browser_harvest",
                        })
    except Exception as e:
        print(f"[WARN] _parse_bovada_props_harvested: {e}")
    return results


def _parse_novig_props_harvested(raw, sport: str) -> list:
    """
    Parse OddsAPI-format Novig player props from betcouncil_novig_{sport}.json.
    
    Expected raw shape (OddsAPI /odds endpoint with markets=player_*):
      [{bookmakers: [{markets: [{key: "player_pass_yards",
          outcomes: [{name: "Josh Allen", description: "Over", price: -115, point: 249.5}]
      }]}]}]
    """
    results = []
    try:
        games = raw if isinstance(raw, list) else raw.get("data", [])
        for game in (games if isinstance(games, list) else []):
            for bm in game.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    stat_key = mkt.get("key", "")
                    by_player: dict = {}
                    for oc in mkt.get("outcomes", []):
                        pname = oc.get("name", "")
                        if not pname:
                            continue
                        side = (oc.get("description") or "").lower()
                        by_player.setdefault(pname, {})
                        by_player[pname]["line"] = oc.get("point")
                        if "over" in side:
                            by_player[pname]["over_odds"] = oc.get("price")
                        elif "under" in side:
                            by_player[pname]["under_odds"] = oc.get("price")
                    for pname, pdata in by_player.items():
                        if pdata.get("line") is None:
                            continue
                        results.append({
                            "Player":    pname,
                            "Prop":      stat_key,
                            "Line":      pdata["line"],
                            "OverOdds":  pdata.get("over_odds", "N/A"),
                            "UnderOdds": pdata.get("under_odds", "N/A"),
                            "Book":      "Novig",
                            "Sport":     sport,
                            "source":    "novig_browser_harvest",
                        })
    except Exception as e:
        print(f"[WARN] _parse_novig_props_harvested: {e}")
    return results



def fetch_bovada_from_gist(sport: str) -> tuple:
    """PRIMARY: Bovada props from browser harvester (parsed). SECONDARY: returns empty
    — game-line scraper fallback does not carry player props."""
    data = _read_gist_file(f"betcouncil_bovada_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=100):
        raw = data.get("data", {})
        if raw:
            props = _parse_bovada_props_harvested(raw, sport)
            if props:
                return props, "browser_harvester"
    return [], "unavailable"

def fetch_novig_from_gist(sport: str) -> tuple:
    """PRIMARY: Novig props from browser harvester (parsed, OddsAPI format).
    SECONDARY: returns empty — fetch_novig_lines gives game lines, not player props."""
    data = _read_gist_file(f"betcouncil_novig_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=100):
        raw = data.get("data", {})
        if raw:
            props = _parse_novig_props_harvested(raw, sport)
            if props:
                return props, "browser_harvester"
    return [], "unavailable"

def _px_best_price(side_list):
    """Return the best (first) price from one side's price list, or None."""
    if not side_list or not isinstance(side_list[0], dict):
        return None
    return side_list[0]


def _px_strip_odds_suffix(name):
    """'Chicago Sky -132' → 'Chicago Sky'  |  'over 8.5' → 'over 8.5' (unchanged)"""
    return re.sub(r'\s+[+-]\d+\.?\d*$', '', str(name)).strip()


def _px_parse_prop_name(market_name):
    """'Kamilla Cardoso Total Rebounds' → ('Kamilla Cardoso', 'Total Rebounds')
    Falls back to (market_name, market_name) if no split point found."""
    for marker in ("Total ", "First ", "Last ", "Alternate "):
        idx = market_name.find(marker)
        if idx > 0:
            return market_name[:idx].strip(), market_name[idx:].strip()
    return market_name, market_name


_PROPHETX_GAME_MARKETS = {
    "moneyline", "moneyline (2 way)", "spread", "game spread",
    "run line", "puck line", "point spread", "total", "totals",
    "total points", "total runs", "total goals (regular time)",
    "total games", "total sets", "total rounds",
    "spread (regular time)", "draw (90 min)",
    "1st inning moneyline", "1st inning total runs",
    "1st-5th inning moneyline", "1st-5th inning spread", "1st-5th inning total runs",
}


def _parse_prophetx_event_markets(markets_payload, game_label, home, away, sport):
    """Split one event's raw v2 markets payload into (game_line_rows, prop_rows)."""
    lines_out, props_out = [], []
    if not markets_payload:
        return lines_out, props_out

    # Real envelope: {"data": {"markets": [...]}}
    markets = []
    if isinstance(markets_payload, dict):
        inner = markets_payload.get("data")
        if isinstance(inner, dict):
            markets = inner.get("markets", [])
        elif isinstance(inner, list):
            markets = inner
        else:
            for key in ("markets", "results"):
                if isinstance(markets_payload.get(key), list):
                    markets = markets_payload[key]
                    break
    if not isinstance(markets, list):
        return lines_out, props_out

    for mkt in markets:
        if not isinstance(mkt, dict):
            continue
        if mkt.get("status") != "active":
            continue

        label = mkt.get("name", "")
        label_lc = label.lower()
        is_game = label_lc in _PROPHETX_GAME_MARKETS

        # Structure-first routing (more robust than name matching alone):
        #   selections len>=2, each element a list → two-sided exchange market (h2h/moneyline)
        #   marketLines present                    → spread/total/prop (over-under format)
        sels = mkt.get("selections", [])
        mkt_lines = mkt.get("marketLines", [])
        has_two_sided = len(sels) >= 2 and isinstance(sels[0], list)
        has_market_lines = bool(mkt_lines)

        if has_two_sided:
            # ── Two-sided exchange market (Moneyline, 1st Inning ML, h2h, etc.) ──
            p0 = _px_best_price(sels[0])
            p1 = _px_best_price(sels[1])
            if p0 and p1:
                lines_out.append({
                    "game": game_label, "home": home, "away": away,
                    "market": label,
                    "selection": _px_strip_odds_suffix(p0.get("name", "")),
                    "odds": p0.get("odds"), "line": 0,
                    "book": "ProphetX", "sport": sport, "source": "prophetx_exchange",
                })
                lines_out.append({
                    "game": game_label, "home": home, "away": away,
                    "market": label,
                    "selection": _px_strip_odds_suffix(p1.get("name", "")),
                    "odds": p1.get("odds"), "line": 0,
                    "book": "ProphetX", "sport": sport, "source": "prophetx_exchange",
                })

        elif has_market_lines and is_game:
            # ── Spread / Total (game-level over-under market) ──
            for ml in mkt_lines[:1]:
                ml_sels = ml.get("selections", [])
                if len(ml_sels) < 2:
                    continue
                p0 = _px_best_price(ml_sels[0])
                p1 = _px_best_price(ml_sels[1])
                if not (p0 and p1):
                    continue
                mkt_label = "Spread" if any(k in label_lc for k in ("spread", "run line", "puck line")) else "Total"
                lines_out.append({
                    "game": game_label, "home": home, "away": away,
                    "market": mkt_label,
                    "selection": _px_strip_odds_suffix(p0.get("name", "")),
                    "odds": p0.get("odds"), "line": p0.get("line"),
                    "book": "ProphetX", "sport": sport, "source": "prophetx_exchange",
                })
                lines_out.append({
                    "game": game_label, "home": home, "away": away,
                    "market": mkt_label,
                    "selection": _px_strip_odds_suffix(p1.get("name", "")),
                    "odds": p1.get("odds"), "line": p1.get("line"),
                    "book": "ProphetX", "sport": sport, "source": "prophetx_exchange",
                })

        elif has_market_lines and not is_game:
            # ── Player props (over-under format via marketLines) ──
            player_name, stat_label = _px_parse_prop_name(label)
            if not player_name:
                continue
            for ml in mkt_lines[:1]:
                ml_sels = ml.get("selections", [])
                if len(ml_sels) < 2:
                    continue
                p_over  = _px_best_price(ml_sels[0])
                p_under = _px_best_price(ml_sels[1])
                if not p_over:
                    continue
                line_val = p_over.get("line")
                if line_val is None:
                    continue
                props_out.append({
                    "Player":    player_name,
                    "Prop":      stat_label,
                    "Line":      line_val,
                    "OverOdds":  p_over.get("odds", "N/A"),
                    "UnderOdds": p_under.get("odds", "N/A") if p_under else "N/A",
                    "Book":      "ProphetX",
                    "Sport":     sport,
                    "source":    "prophetx_exchange",
                })

    return lines_out, props_out


def _parse_prophetx_events(events: list, sport: str):
    all_lines, all_props = [], []
    for ev in (events or []):
        if not isinstance(ev, dict):
            continue
        # ProphetX event name: "Away Team at Home Team" — no separate home/away fields
        name = ev.get("name") or ev.get("displayName") or ev.get("title") or ""
        parts = name.split(" at ", 1)
        if len(parts) == 2:
            away, home = parts[0].strip(), parts[1].strip()
        else:
            home, away = name, ""
        lines, props = _parse_prophetx_event_markets(ev.get("markets"), name, home, away, sport)
        all_lines.extend(lines)
        all_props.extend(props)
    return all_lines, all_props


def fetch_prophetx_game_lines_from_gist(sport: str) -> tuple:
    """ProphetX exchange game lines (moneyline/spread/total), normalized to
    BetCouncil's standard {game, home, away, market, selection, odds, book,
    sport, source} schema — same shape as fetch_bovada_game_lines."""
    events, _ = fetch_prophetx_from_gist(sport)
    if not events:
        return [], "unavailable"
    lines, _props = _parse_prophetx_events(events, sport)
    if lines:
        return lines, "prophetx_exchange"
    return [], "unavailable"


def fetch_prophetx_props_from_gist(sport: str) -> tuple:
    """ProphetX exchange player props, normalized to BetCouncil's standard
    {Player, Prop, Line, OverOdds, UnderOdds, Book, Sport, source} schema —
    same shape as fetch_novig_from_gist."""
    events, _ = fetch_prophetx_from_gist(sport)
    if not events:
        return [], "unavailable"
    _lines, props = _parse_prophetx_events(events, sport)
    if props:
        return props, "prophetx_exchange"
    return [], "unavailable"


def fetch_prophetx_from_gist(sport: str) -> tuple:
    """ProphetX exchange odds (all sports) from scripts/prophetx_harvester.py,
    run every 15 min via .github/workflows/prophetx_refresh.yml. Public,
    unauthenticated exchange API — consensus/peer-to-peer pricing, not a
    book's posted line. Raw pass-through: 'events' each carry 'markets'
    (v2 live odds) and 'commissions'. Sport bucket is one of NFL/NBA/WNBA/
    MLB/NHL/MMA/TENNIS/GOLF/SOCCER/OTHER (see prophetx_harvester.py
    classify_sport). Not yet normalized into BetCouncil's internal prop/
    line schema — callers get the raw harvester payload today."""
    data = _read_gist_file(f"betcouncil_prophetx_{sport}.json", cache_minutes=10)
    if data and _is_fresh(data, max_age_minutes=100):
        events = data.get("events", [])
        if events:
            return events, "prophetx_exchange"
    return [], "unavailable"



def fetch_mybookie_from_gist(sport: str) -> tuple:
    """PRIMARY: MyBookie lines from browser harvester. SECONDARY: server scraper."""
    data = _read_gist_file(f"betcouncil_mybookie_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=28):
        raw = data.get("data",{})
        if raw: return raw, "browser_harvester"
    # NOTE: fetch_mybookie_lines (Playwright) removed as fallback here.
    # Action Network (book_id=8) is now the primary in _pf_mybookie() in app.py
    # and handles all cases where Gist is empty. Calling Playwright here
    # caused "playwright not installed" errors on Streamlit Cloud.
    return {}, "unavailable"


def fetch_parlaysavant_props(sport: str, position: str, prop: str) -> dict:
    """
    Confirmed undefined (real NameError, silently caught) at its one call
    site in app_core.py. Direct scrape of parlaysavant.com confirmed
    Cloudflare-blocked (real 403 "Just a moment..." challenge on every
    URL pattern tried, 2026-08-03). The browser-harvester alternative
    (fetch_parlaysavant_from_gist) was already confirmed in an earlier
    audit this session to carry zero real data at the source -- so
    redirecting here would swap one silent no-op for another, not
    restore real functionality. Clean stub until a real access path
    exists, matching the SharpAPI/Heritage Sports removal pattern.
    """
    return {}


def fetch_parlaysavant_from_gist(sport: str) -> tuple:
    """PRIMARY: ParlaySavant +EV from browser harvester. SECONDARY: server scraper."""
    data = _read_gist_file(f"betcouncil_parlaysavant_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=100):
        raw = data.get("data",{})
        if raw: return raw, "browser_harvester"
    # fetch_parlaysavant_props did not exist — direct Python HTTP (no CORS server-side)
    # Also checks sport-specific Gist files from the Tampermonkey parlaysavant harvester
    # (which pushes betcouncil_parlaysavant_{SPORT}_{pageType}_{market}.json)
    try:
        import requests as _req
        _sport_l = sport.lower()
        _r = _req.get(
            f"https://parlaysavant.com/api/props?sport={_sport_l}&type=positive_ev&limit=100",
            headers={"Accept": "application/json",
                     "Referer": "https://parlaysavant.com/",
                     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=14)
        if _r.status_code == 200:
            _d = _r.json()
            return (_d if isinstance(_d, (list, dict)) else {}), "python_direct"
    except Exception:
        pass
    return {}, "unavailable"


def _frac_to_american(frac_str) -> int:
    """Convert bet365's fractional odds string (e.g. '20/23') to American odds."""
    try:
        num, den = str(frac_str).split("/")
        decimal = 1 + (float(num) / float(den))
    except (ValueError, ZeroDivisionError):
        return None
    if decimal >= 2.0:
        return round((decimal - 1) * 100)
    return round(-100 / (decimal - 1))


def fetch_bet365_from_gist(sport: str) -> tuple:
    """
    PRIMARY: Bet365 lines from browser harvester. SECONDARY: server scraper.

    Real confirmed filename (verified against live Gist content, 2026-07-05):
    'betcouncil_bet365_games.json' — NOT 'betcouncil_bet365_{sport}.json' as
    previously assumed. The harvester writes ALL sports to one combined file
    with no per-sport key or per-game sport tag, so this function returns
    parsed results for every game in the file; callers should filter by
    team-name match against the sport board they're viewing (matches the
    existing merge-by-name pattern already used elsewhere in Line Shop).

    Real confirmed schema: {"captured_at":..., "game_count":..., "data": [
      {"matchup", "home_team", "away_team", "kickoff", "selections": [
        {"label": <team name or "+X.Y"/"-X.Y" or "unknown">,
         "odds_fractional_static": "20/23", "handicap": null}, ...]}]}

    KNOWN LIMITATION: the two "unknown"-labeled selections per game are
    Over/Under, but the harvester does not currently capture the actual
    total line number (label is literally "unknown", handicap is null) —
    only moneyline and spread are recoverable from this data as-is. This
    needs a harvester JS fix to capture the real total value, not a parser
    fix (there is no total number anywhere in the payload to parse).
    """
    data = _read_gist_file("betcouncil_bet365_games.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=28) and isinstance(data.get("data"), list) and data["data"]:
        results = []
        for game in data["data"]:
            home, away = game.get("home_team"), game.get("away_team")
            matchup = game.get("matchup") or f"{away} @ {home}"
            selections = game.get("selections", [])
            if len(selections) < 4:
                continue

            # First two selections are always [home ML, away ML] per confirmed schema
            home_ml_odds = _frac_to_american(selections[0].get("odds_fractional_static"))
            away_ml_odds = _frac_to_american(selections[1].get("odds_fractional_static"))
            if home_ml_odds is not None:
                results.append({"game": matchup, "home": home, "away": away, "market": "Moneyline", "selection": home, "odds": home_ml_odds, "book": "Bet365", "sport": sport, "source": "bet365_harvester"})
            if away_ml_odds is not None:
                results.append({"game": matchup, "home": home, "away": away, "market": "Moneyline", "selection": away, "odds": away_ml_odds, "book": "Bet365", "sport": sport, "source": "bet365_harvester"})

            # Spread pair (selections[2], selections[3]): favorite always gets
            # the minus number (standard convention) — determined by which
            # team has the more-favored (higher implied prob / less positive)
            # moneyline, NOT by fixed position, since the +/- order flips
            # between games in the real captured data.
            spread_a, spread_b = selections[2], selections[3]
            label_a, label_b = spread_a.get("label", ""), spread_b.get("label", "")
            odds_a = _frac_to_american(spread_a.get("odds_fractional_static"))
            odds_b = _frac_to_american(spread_b.get("odds_fractional_static"))
            if home_ml_odds is not None and away_ml_odds is not None and odds_a is not None and odds_b is not None:
                home_is_favorite = home_ml_odds < away_ml_odds  # more negative = bigger favorite
                minus_label = label_a if label_a.startswith("-") else label_b
                plus_label = label_b if label_a.startswith("-") else label_a
                minus_odds = odds_a if label_a.startswith("-") else odds_b
                plus_odds = odds_b if label_a.startswith("-") else odds_a
                fav_team, dog_team = (home, away) if home_is_favorite else (away, home)
                results.append({"game": matchup, "home": home, "away": away, "market": "Spread", "selection": f"{fav_team} {minus_label}", "odds": minus_odds, "book": "Bet365", "sport": sport, "source": "bet365_harvester"})
                results.append({"game": matchup, "home": home, "away": away, "market": "Spread", "selection": f"{dog_team} {plus_label}", "odds": plus_odds, "book": "Bet365", "sport": sport, "source": "bet365_harvester"})

        if results:
            return results, "browser_harvester"

    try:
        from fetchers import fetch_bet365_game_lines as _f
        s = _f(sport)
        if s: return s, "scraper_fallback"
    except Exception: pass
    return {}, "unavailable"




def _thescore_odds_to_american(fmt):
    """theScore's formattedOdds is pre-formatted American odds, except 'Even' for pick'em lines."""
    if fmt is None:
        return "N/A"
    if str(fmt).strip().lower() == "even":
        return "+100"
    return fmt


def _parse_thescore_golf_outrights(raw_resp: dict, market_label: str, sport: str = "Golf") -> list:
    """
    Parser for theScore Bet golf outright/field markets (Tournament Winner,
    Top 10 Finish, etc.) — CONFIRMED against real captured data (John Deere
    Classic, 2026-07-05).

    Golf uses a fundamentally different query and shape than team sports:
      operationName : CompetitionDrawerContent (same query as prop drawers
                       like home-runs/player-awards — NOT
                       CompetitionPageSectionLinesTabNode)
      Real shape: data.competitionDrawer.drawerChildren[].marketplaceShelfChildren[]
                  each has .market: {"name", "type": "LIST", "selections": [
                      {"name": {"cleanName": <player>}, "odds": {"formattedOdds"},
                       "participant": {"fullName", "resourceUri": "/golf/players/{id}"}}
                  ]}
      No home/away, no spread/total — just one market with the whole field.

    competitionSlug and groupId are PER-TOURNAMENT (change weekly), unlike
    team sports' stable season-long sectionId — the harvester config for golf
    needs the current week's tournament slug/groupId, not a fixed ID.

    Returns list of {Player, Market, Odds, Book, Sport, source} — different
    shape than _parse_thescore_game_lines since there's no matchup structure.
    """
    results = []
    try:
        if isinstance(raw_resp, dict) and "data" in raw_resp:
            drawer = (raw_resp["data"] or {}).get("competitionDrawer") or {}
        elif isinstance(raw_resp, dict) and "competitionDrawer" in raw_resp:
            drawer = raw_resp["competitionDrawer"] or {}
        else:
            drawer = raw_resp if isinstance(raw_resp, dict) else {}

        if not drawer:
            return []

        for child in drawer.get("drawerChildren") or []:
            for shelf_item in child.get("marketplaceShelfChildren") or []:
                mkt = shelf_item.get("market") or {}
                mkt_name = mkt.get("name", market_label)
                for sel in mkt.get("selections") or []:
                    participant = sel.get("participant") or {}
                    player = participant.get("fullName") or (sel.get("name") or {}).get("cleanName")
                    odds_val = _thescore_odds_to_american((sel.get("odds") or {}).get("formattedOdds"))
                    if not player:
                        continue
                    results.append({
                        "Player": player,
                        "Market": mkt_name,
                        "Odds": odds_val,
                        "Book": "theScore Bet",
                        "Sport": sport,
                        "source": "thescore_gist_harvester",
                    })
    except Exception as e:
        print(f"[WARN] _parse_thescore_golf_outrights: {e}")
    return results


def _parse_thescore_game_lines(raw_resp: dict, sport: str) -> list:
    """
    Parse theScore Bet game-line data into BetCouncil format.

    CORRECTED (verified against real captured DevTools data, 2026-07-05):
    The real per-game board does NOT come from CompetitionDrawerContent (that
    query only returns prop drawers — home runs, player awards, etc., each
    scoped to its own groupId/sectionSlug, never the main board no matter
    which sectionSlug is tried).

    The REAL query is a DIFFERENT operation entirely:
      operationName : CompetitionPageSectionLinesTabNode
      sha256Hash    : 1ec1bed0d31b92e88825523405e45e88d6f34d484f4b0f3bbe4beb319229cab6
      variables     : {"sectionId": "Section:d9513891-c315-4c16-8554-09d52d3ce9b2", ...}
                      (sectionId is fixed/static — confirmed same value works,
                      no per-sport variation needed beyond competitionSlug context)

    Real confirmed response shape:
      data.competitionSection.sectionChildren[] — an array where:
        [0] is always the Featured Parlays carousel (has "featuredBetsCarouselChildren" — SKIP)
        [1] is "MarketplaceShelf:..." (has "marketplaceShelfChildren" — THIS is the real board)
      Each marketplaceShelfChildren entry is a "GridMarketCard" (one per game) with:
        markets: [{"type": "MONEYLINE"|"SPREAD"|"TOTAL", "selections": [...]}]
        selections[].type: AWAY_MONEYLINE/HOME_MONEYLINE/AWAY_SPREAD/HOME_SPREAD/OVER/UNDER
        selections[].odds.formattedOdds: pre-formatted American odds, or "Even" for pick'em
        selections[].points.formattedPoints: spread/total number (e.g. "+1.5", "8.5")
        selections[].participant.fullName: real team name

    Replit's original harvester config (groupId 844647ef-..., CompetitionDrawerContent)
    was capturing the wrong query — that groupId is specifically the "home-runs" prop
    drawer, not a general game-lines drawer as originally assumed. The harvester needs
    to be reconfigured to capture CompetitionPageSectionLinesTabNode instead.
    """
    results = []
    try:
        if isinstance(raw_resp, dict) and "data" in raw_resp:
            comp_section = (raw_resp["data"] or {}).get("competitionSection") or {}
        elif isinstance(raw_resp, dict) and "competitionSection" in raw_resp:
            comp_section = raw_resp["competitionSection"] or {}
        else:
            comp_section = raw_resp if isinstance(raw_resp, dict) else {}

        if not comp_section:
            return []

        for child in comp_section.get("sectionChildren") or []:
            shelf_children = child.get("marketplaceShelfChildren")
            if not shelf_children:
                continue  # this is the Featured Parlays carousel, not the board

            for card in shelf_children:
                markets = card.get("markets") or []
                if not markets:
                    continue

                home = away = None
                home_ml = away_ml = "N/A"
                spread = spread_odds = "N/A"
                total = over_odds = under_odds = "N/A"

                for mkt in markets:
                    mtype = mkt.get("type", "")
                    for sel in (mkt.get("selections") or []):
                        sel_type = sel.get("type", "")
                        odds_val = _thescore_odds_to_american((sel.get("odds") or {}).get("formattedOdds"))
                        participant = sel.get("participant") or {}
                        team_name = participant.get("fullName") or (sel.get("name") or {}).get("cleanName")

                        if mtype == "MONEYLINE":
                            if sel_type == "HOME_MONEYLINE":
                                home, home_ml = team_name, odds_val
                            elif sel_type == "AWAY_MONEYLINE":
                                away, away_ml = team_name, odds_val
                        elif mtype == "SPREAD":
                            pts = (sel.get("points") or {}).get("formattedPoints", "")
                            if sel_type == "HOME_SPREAD":
                                spread, spread_odds = f"{team_name or home} {pts}", odds_val
                        elif mtype == "TOTAL":
                            pts = (sel.get("points") or {}).get("formattedPoints")
                            if sel_type == "OVER":
                                over_odds = odds_val
                                if pts: total = pts
                            elif sel_type == "UNDER":
                                under_odds = odds_val

                if not home or not away:
                    continue

                results.append({
                    "Matchup": f"{away} @ {home}", "Home": home, "Away": away,
                    "HomeML": home_ml, "AwayML": away_ml,
                    "Spread": spread, "SpreadOdds": spread_odds,
                    "Total": total, "OverOdds": over_odds, "UnderOdds": under_odds,
                    "Book": "theScore Bet", "Sport": sport, "source": "thescore_gist_harvester",
                })
    except Exception as e:
        print(f"[WARN] _parse_thescore_game_lines: {e}")
    return results


def fetch_thescore_from_gist(sport: str) -> tuple:
    """
    PRIMARY source for theScore Bet game lines.

    Browser harvester config (CORRECTED — verified against real captured data,
    2026-07-05; the original CompetitionDrawerContent config never worked
    because that query only serves prop drawers, not the main board):
      operationName    : CompetitionPageSectionLinesTabNode
      sha256Hash       : 1ec1bed0d31b92e88825523405e45e88d6f34d484f4b0f3bbe4beb319229cab6
      sectionId        : Section:d9513891-c315-4c16-8554-09d52d3ce9b2
      Gist file        : betcouncil_thescore_games.json

    Real response shape: data.competitionSection.sectionChildren[1] (the
    "MarketplaceShelf" entry, NOT [0] which is the Featured Parlays carousel)
    contains marketplaceShelfChildren — one GridMarketCard per real game.

    UPDATED — harvester now pushes multiple sports in one file, keyed by
    sport: {"captured_at": ..., "data": {"MLB": {...}, "NFL": {...}, ...}}.
    This function selects the sub-payload for the requested sport before
    handing it to the parser (which still expects a single GraphQL envelope).

    WHY Gist-only (not direct API):
      Direct server calls return HTTP 403 UNAUTHORIZED — the query is
      geo/session-gated. A real browser session in a licensed US state is
      required; the harvester provides that.

    Returns (list, source_label) — same tuple convention as other _from_gist fetchers.
    """
    data = _read_gist_file("betcouncil_thescore_games.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=28):
        by_sport = data.get("data", {})
        sport_payload = by_sport.get(sport.upper()) if isinstance(by_sport, dict) else None
        if sport_payload:
            results = _parse_thescore_game_lines(sport_payload, sport)
            if results:
                print(f"[theScore Bet] {len(results)} game-line records from Gist harvester")
                return results, "gist_harvester"
    return [], "unavailable"


def fetch_fantasylabs_from_gist(sport: str) -> tuple:
    data = _read_gist_file(f"betcouncil_fantasylabs_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=32):
        raw = data.get("data",{})
        if raw: return raw, "browser_harvester"
    try:
        from fetchers import fetch_fantasylabs_lineups as _f; s=_f(sport)
        if s: return s, "scraper_fallback"
    except Exception: pass
    return {}, "unavailable"

def fetch_rotowire_from_gist(sport: str) -> tuple:
    data = _read_gist_file(f"betcouncil_rotowire_{sport}.json", cache_minutes=5)
    if data and _is_fresh(data, max_age_minutes=18):
        raw = data.get("data",{})
        if raw: return raw, "browser_harvester"
    try:
        from fetchers import fetch_rotowire_injuries as _f; s=_f(sport)
        if s: return s, "scraper_fallback"
    except Exception: pass
    return {}, "unavailable"

def fetch_numberfire_direct(sport: str) -> dict:
    """
    Direct server-side NumberFire fetch — no browser tab required.

    CONFIRMED live and public (Jul 9 2026), no auth/cookies needed:
      NFL: https://www.numberfire.com/external/widgets/top-players[/<pos>]
      NBA: https://www.numberfire.com/external/widgets/nba/fanduel-values/<pos>

    NOT YET CONFIRMED for MLB/NHL/WNBA — numberfire.com/info/widgets?fs=true
    lists the full widget catalog and should be checked for those sports'
    equivalent paths before assuming they don't exist; returns {} for them
    here rather than guessing a URL that might silently 404 or return the
    wrong sport's data.
    """
    cache_path = os.path.join(CACHE_DIR, f"numberfire_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 60:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached
    url_map = {
        "NFL": "https://www.numberfire.com/external/widgets/top-players",
        "NBA": "https://www.numberfire.com/external/widgets/nba/fanduel-values/sf",
    }
    url = url_map.get(sport)
    if not url:
        return {}
    try:
        r = _http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"}, timeout=12)
        if r.status_code != 200:
            return {}
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        if not table:
            return {}
        players = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            link = row.find("a", href=True)
            if not link:
                continue
            name_text = link.get_text(strip=True)
            row_text = row.get_text(" ", strip=True)
            players.append({"name": name_text, "raw_row": row_text})
        result = {"players": players, "sport": sport}
        if players:
            _safe_save_pkl(cache_path, result)
        return result
    except Exception as e:
        print(f"[WARN] fetch_numberfire_direct: {e}")
        return {}


def fetch_sportsinsights_from_gist(sport):
    data=_read_gist_file(f"betcouncil_sportsinsights_{sport}.json",5)
    if data and _is_fresh(data,18): return data.get("games",{}), "browser_harvester"
    return {}, "unavailable"

def fetch_baseballpress_from_gist():
    data=_read_gist_file("betcouncil_baseballpress.json",5)
    if data and _is_fresh(data,18): return data.get("data",{}), "browser_harvester"
    return {}, "unavailable"

def fetch_rotogrinders_from_gist(sport):
    data=_read_gist_file(f"betcouncil_rotogrinders_{sport}.json",5)
    if data and _is_fresh(data,32): return data.get("records",{}), "browser_harvester"
    return {}, "unavailable"

def fetch_oddsportal_from_gist(sport):
    """
    Today's opening lines (moneyline/spread/total), captured once per
    day. Despite the function name (kept for gist-filename/registry
    compatibility), the real source is ESPN's scoreboard endpoint via
    scripts/espn_opening_lines_refresh.py — not OddsPortal.

    2026-07 fix: this previously called
    "https://www.oddsportal.com/api/v1/events/{sport}/today", an
    endpoint that was never verified and, on inspection, doesn't appear
    to be real — OddsPortal's odds tables load via client-side JS, not
    present in server-rendered HTML, and the site has no documented
    public API. Rather than keep a silently-broken guess in place, this
    now reads the real harvester's output. Returns ({}, "unavailable")
    if the harvester hasn't run yet today.
    """
    data = _read_gist_file(f"betcouncil_oddsportal_{sport}.json", 5)
    if data and _is_fresh(data, 300):  # capture happens once/day, so allow up to 5hrs old
        return data, "espn_opening_lines"
    return {}, "unavailable"

def fetch_weather_from_gist(sport):
    data=_read_gist_file(f"betcouncil_weather_{sport}.json",5)
    if data and _is_fresh(data,65): return data.get("data",{}), "browser_harvester"
    return {}, "unavailable"

def fetch_linestar_props_from_gist(sport="MLB"):
    """Cross-book prop odds snapshot from LineStar's public GetPropBets endpoint.
    Covers DK/FD/Yahoo/PrizePicks/Underdog/Caesars/BetMGM/PointsBet/SuperDraft.
    Schema confirmed 2026-07: data.PropBets[], data.BetTypes[], data.Players[],
    data.SportsBooks[], data.Teams[], data.Games[] (with weather + Vegas lines).
    Harvested browser-side via app.py throttled block; enriched with team abbrevs.
    """
    data = _read_gist_file(f"betcouncil_linestar_props_{sport}.json", 5)
    if data and _is_fresh(data, 65):
        return data.get("data", {}), "browser_harvester"
    return {}, "unavailable"

def fetch_linestar_salaries_from_gist(sport="MLB"):
    """LineStar GetSalariesV5: full DFS player projection table with Ceil/Floor/Conf
    and MatchupData wOBA/ISO/wRC+/HR-PA splits over 150 games per player.
    Harvested browser-side via app.py throttled block.
    SalaryContainerJson.Salaries[] fields: Name, PID, PP (proj pts), PS (actual pts),
    Ceil, Floor, Conf, HTEAM, OTEAM, GI (game info), OppRank, SAL (salary), POS, Notes.
    MatchupData[].PlayerMatchups[]: SID, PlayerId, Values [PA,AVG,SB,HR,RBI,ISO,wOBA,
    wOBA+ISO,HR/PA,HR+SB/PA,wRC+,FP/PA], Ranks.
    """
    data = _read_gist_file(f"betcouncil_linestar_salaries_{sport}.json", 5)
    if data and _is_fresh(data, 65):
        return data.get("data", {}), "browser_harvester"
    return {}, "unavailable"

def get_linestar_player_salary_row(salaries_data, player_name):
    """Pull one player's row from LineStar GetSalariesV5: Ceil/Floor/Conf/Salary/
    OppRank plus matchup splits (wOBA/ISO/wRC+/HR-PA) from MatchupData, if present.

    Name matching is case-insensitive exact-match first, then substring fallback,
    since LineStar/BallsDontLie/MLB-API naming can differ slightly (suffixes,
    accents, "Jr." etc). Returns None on no match rather than a partial/wrong row.
    """
    if not isinstance(salaries_data, dict) or not player_name:
        return None
    try:
        sc = json.loads(salaries_data.get("SalaryContainerJson") or "{}")
    except Exception:
        return None
    salaries = sc.get("Salaries") or []
    target = player_name.strip().lower()
    row = next((s for s in salaries if isinstance(s, dict)
                and str(s.get("Name", "")).strip().lower() == target), None)
    if row is None:
        row = next((s for s in salaries if isinstance(s, dict)
                    and target in str(s.get("Name", "")).strip().lower()), None)
    if row is None:
        return None
    out = {
        "salary": row.get("SAL"), "proj": row.get("PP"), "ceil": row.get("Ceil"),
        "floor": row.get("Floor"), "conf": row.get("Conf"), "opp_rank": row.get("OppRank"),
        "position": row.get("POS"), "game_info": row.get("GI"),
        "home_team": row.get("HTEAM"), "away_team": row.get("OTEAM"), "notes": row.get("Notes"),
        # Fields below (2026-07) are best-effort/unverified against a live payload --
        # display-only, fail silently (None/empty) rather than guess wrong.
        "alert_score": row.get("AlertScore"),
        "stars": row.get("Stars"),
        "ppg": row.get("PPG"),
        "status_flags": {k: row.get(k) for k in ("STAT", "IS", "SIC") if row.get(k) is not None} or None,
    }
    pid = row.get("PID")
    if pid is not None:
        _labels = ["PA", "AVG", "SB", "HR", "RBI", "ISO", "wOBA", "wOBA+ISO",
                   "HR/PA", "HR+SB/PA", "wRC+", "FP/PA"]
        # Collect every matchup section this player appears in (Last 7 / Last 30 /
        # Season / vs-LHP / vs-RHP etc), not just the first match, so Player Lookup
        # can show the full split picture rather than one arbitrary table.
        sections = {}
        for md in (sc.get("MatchupData") or []):
            for pm in (md.get("PlayerMatchups") or []):
                if pm.get("PlayerId") == pid:
                    vals = pm.get("Values") or []
                    label = md.get("Title") or md.get("Name") or "Splits"
                    sections[label] = dict(zip(_labels, vals))
                    break
        if sections:
            out["matchup_sections"] = sections
    return out


# Team-level standings (GetSalariesV5 Records[]) -- best-effort/unverified field
# names, display-only. Returns None rather than a guessed-wrong value.
def get_linestar_team_record(salaries_data, team_abbrev):
    if not isinstance(salaries_data, dict) or not team_abbrev:
        return None
    try:
        sc = json.loads(salaries_data.get("SalaryContainerJson") or "{}")
    except Exception:
        return None
    for rec in (sc.get("Records") or []):
        if not isinstance(rec, dict):
            continue
        if str(rec.get("Team") or rec.get("Abbreviation") or "").upper() == team_abbrev.upper():
            return {
                "wins": rec.get("W"), "losses": rec.get("L"),
                "off_rank": rec.get("OffenseRankingOverall"),
                "def_rank": rec.get("DefenseRankingOverall"),
                "pts_for_pg": rec.get("TotalPointsScoredPerGame"),
                "pts_against_pg": rec.get("TotalPointsAllowedPerGame"),
            }
    return None


def _summarize_loj(loj):
    """Turn a LineStar LOJ (Last Over/Under Journey) value into a readable
    hit-rate badge, e.g. "7/10 Over". Handles a few plausible shapes
    defensively since the exact format hasn't been independently confirmed:
    a list of "O"/"U" strings, a list of 1/0 (over=1), or a list of dicts
    with a Result-style key. Returns None (not a guess) if the shape doesn't
    match anything recognized.
    """
    if not loj or not isinstance(loj, list):
        return None
    try:
        vals = []
        for item in loj:
            if isinstance(item, str):
                s = item.strip().upper()
                if s in ("O", "OVER", "1"):
                    vals.append(1)
                elif s in ("U", "UNDER", "0"):
                    vals.append(0)
            elif isinstance(item, dict):
                r = str(item.get("Result") or item.get("R") or "").strip().upper()
                if r in ("O", "OVER"):
                    vals.append(1)
                elif r in ("U", "UNDER"):
                    vals.append(0)
            elif isinstance(item, (int, float)):
                vals.append(1 if item else 0)
        if not vals:
            return None
        hits = sum(vals)
        return f"{hits}/{len(vals)} Over"
    except Exception:
        return None


def get_linestar_player_chartdata(props_data, player_name):
    """Best-effort pull of a player's rolling game-log (GetPropBets ChartData[]),
    per Replit's 2026-07 field inventory -- exact shape not independently
    confirmed here, so this is defensive: returns None rather than a guessed
    layout if the expected keys aren't present.
    """
    if not isinstance(props_data, dict) or not player_name:
        return None
    players = {p["Id"]: p["Name"] for p in props_data.get("Players", []) if isinstance(p, dict)}
    target = player_name.strip().lower()
    pid = next((pid for pid, nm in players.items() if nm.lower() == target), None)
    if pid is None:
        pid = next((pid for pid, nm in players.items() if target in nm.lower()), None)
    if pid is None:
        return None
    for cd in (props_data.get("ChartData") or []):
        if isinstance(cd, dict) and cd.get("PlayerId") == pid:
            return cd.get("Values") or cd.get("Games") or cd.get("Data")
    return None


def get_linestar_prop_lines(props_data, player_name):
    """Extract per-book prop lines for a player from LineStar GetPropBets data.
    Returns dict: {book_name: {stat_name: {line, over_odds, under_odds, ls_proj}}}
    Schema confirmed 2026-07: Source=int maps to SportsBooks[].Source/Name;
    StatId=int maps to BetTypes[].Id/StatName; PlayerId int maps to Players[].Id/Name.

    STATUS: wired into the Player Lookup tab (2026-07) alongside
    get_linestar_player_salary_row(). Bulk DK-only extraction for Line Shop
    is handled separately by _parse_linestar_as_dk_props() /
    parse_linestar_props_all_books().
    """
    if not isinstance(props_data, dict) or not player_name:
        return {}
    players  = {p["Id"]: p["Name"] for p in props_data.get("Players", []) if isinstance(p, dict)}
    books    = {b["Source"]: b["Name"] for b in props_data.get("SportsBooks", []) if isinstance(b, dict)}
    stats    = {bt["Id"]: bt["StatName"] for bt in props_data.get("BetTypes", []) if isinstance(bt, dict)}
    target   = player_name.strip().lower()
    pid      = next((pid for pid, nm in players.items() if nm.lower() == target), None)
    if pid is None:
        # Fallback: substring match (LineStar/BallsDontLie/MLB-API naming can
        # differ slightly -- suffixes, accents, "Jr." etc).
        pid = next((pid for pid, nm in players.items() if target in nm.lower()), None)
    if pid is None:
        return {}
    result = {}
    for pb in props_data.get("PropBets", []):
        if not isinstance(pb, dict) or pb.get("PlayerId") != pid:
            continue
        book_name = books.get(pb.get("Source"), f"Book{pb.get('Source')}")
        stat_name = stats.get(pb.get("StatId"), f"Stat{pb.get('StatId')}")
        if book_name not in result:
            result[book_name] = {}
        result[book_name][stat_name] = {
            "line":       pb.get("OverUnderValue"),
            "over_odds":  pb.get("OverOdds"),
            "under_odds": pb.get("UnderOdds"),
            "ls_proj":    pb.get("LineStarStatProj"),
            "loj_badge":  _summarize_loj(pb.get("LOJ")),
        }
    return result

# WindDirection int→string. Confirmed range 0-7 from docs; value 8 observed in live
# payloads (2026-07) with no documented meaning — treated as "Var" (variable/calm).
# get() with fallback handles any future undocumented values without silent None.
_LS_WIND_DIR = {0:"N",1:"NE",2:"E",3:"SE",4:"S",5:"SW",6:"W",7:"NW",8:"Var"}

def get_linestar_game_weather(weather_gist_data, team_abbrev):
    """Pull one game's weather from the enriched LineStar weather Gist file.

    Schema confirmed 2026-07 against live GetFastUpdateV2 + GetPropBets payloads:
    - Games[]: Id, AwayTeamId, HomeTeamId, WindSpeed (float mph), WindDirection
      (int 0-7 → N/NE/E/SE/S/SW/W/NW; value 8 observed in live data → "Var"),
      RainAmount (float inches), PostponeChance,
      Humidity (float %), Temp (float °F), IsDome (bool).
    - AwayTeamAbrev / HomeTeamAbrev are None in the raw API; the app.py harvester
      enriches games with _AwayAbbr / _HomeAbbr from the PropBets Teams array.
    - TeamMap in the gist root: {TeamId: Abbrev} built from PropBets.Teams[] PLUS
      SalariesV5.SalaryContainerJson.Salaries[].HTID/HTEAM+OTID/OTEAM. Covers all
      DFS-slate teams (PropBets.Teams[] alone only has teams with active props).
    Matching priority: _AwayAbbr/_HomeAbbr (enriched) → TeamMap lookup by TeamId.
    """
    if not isinstance(weather_gist_data, dict):
        return None
    games    = weather_gist_data.get("Games") or []
    team_map = weather_gist_data.get("TeamMap") or {}  # {str(TeamId): Abbrev}
    if not isinstance(games, list):
        return None
    team_abbrev = (team_abbrev or "").upper()
    for g in games:
        if not isinstance(g, dict):
            continue
        home = str(g.get("_HomeAbbr") or g.get("HomeTeamAbrev") or "").upper()
        away = str(g.get("_AwayAbbr") or g.get("AwayTeamAbrev") or "").upper()
        if not home and not away:
            home = team_map.get(str(g.get("HomeTeamId", "")), "")
            away = team_map.get(str(g.get("AwayTeamId", "")), "")
        if team_abbrev not in (home, away):
            continue
        wind_speed = g.get("WindSpeed")
        wind_dir_i = g.get("WindDirection")
        wind_dir   = _LS_WIND_DIR.get(int(wind_dir_i), f"Dir{int(wind_dir_i)}") if wind_dir_i is not None else "N"
        temp       = g.get("Temp")
        humidity   = g.get("Humidity")
        is_dome    = g.get("IsDome")
        rain       = g.get("RainAmount")
        if is_dome:
            return {"city": team_abbrev, "wind_speed_mph": 0, "wind_dir": "N",
                    "temp_f": int(temp) if temp is not None else 72,
                    "humidity": int(humidity) if humidity is not None else 50,
                    "fetched_at": datetime.now().strftime("%H:%M"), "source": "LineStar(dome)"}
        if wind_speed is None and temp is None:
            return None
        return {"city": team_abbrev,
                "wind_speed_mph": round(float(wind_speed), 1) if wind_speed is not None else 0,
                "wind_dir": wind_dir,
                "temp_f": round(float(temp)) if temp is not None else 70,
                "humidity": round(float(humidity)) if humidity is not None else 50,
                "rain_in": round(float(rain), 3) if rain else 0,
                "postpone_pct": g.get("PostponeChance", 0),
                "vegas_total": g.get("VegasTotals"),
                "fetched_at": datetime.now().strftime("%H:%M"),
                "source": "LineStar"}
    return None

def fetch_scoresandodds_from_gist(sport):
    data=_read_gist_file(f"betcouncil_scoresandodds_{sport}.json",5)
    if data and _is_fresh(data,18): return data.get("games",{}), "browser_harvester"
    return {}, "unavailable"

def _parse_evbets_data(raw, sport: str) -> list:
    """Parse EVBets HTML/JSON response into BetCouncil pick format."""
    results = []
    try:
        # Handle JSON API response
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = raw.get("picks", raw.get("value_bets", raw.get("data", [])))
        else:
            return []

        for item in (items if isinstance(items, list) else []):
            if not isinstance(item, dict): continue
            ev = item.get("ev", item.get("ev_pct", item.get("expected_value", 0)))
            if not ev: continue
            results.append({
                "event":    item.get("event", item.get("match", item.get("game", ""))),
                "outcome":  item.get("outcome", item.get("selection", item.get("pick", ""))),
                "market":   item.get("market", item.get("market_type", "h2h")),
                "ev_pct":   float(str(ev).replace("%","").replace("+","") or 0),
                "best_odds":item.get("best_odds", item.get("odds", item.get("price", 0))),
                "book":     item.get("bookmaker", item.get("book", item.get("sportsbook", ""))),
                "kelly":    item.get("kelly", item.get("kelly_stake", 0)),
                "sport":    sport,
                "source":   "evbets",
            })
        # Sort by EV descending
        results.sort(key=lambda x: x.get("ev_pct", 0), reverse=True)
    except Exception as e:
        print(f"[WARN] _parse_evbets_data: {e}")
    return results


def fetch_odds_api_props(sport):
    if not ODDS_API_KEY:
        return []
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return []
    allowed, reason = api_budget_check("ODDS_API")
    if not allowed:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_odds_api_props", "error": reason})
        return []
    cache_path = os.path.join(CACHE_DIR, f"odds_api_props_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 Odds API props: cached ({age_mins:.0f}m old)")
                return cached
    events_url = f"{ODDS_API_BASE}/sports/{sport_key}/events?apiKey={ODDS_API_KEY}&dateFormat=iso"
    try:
        events_resp = _http.get(events_url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API", amount=0)  # /events is a free metadata endpoint
        if events_resp.status_code != 200:
            return []
        events = events_resp.json()
        if not events:
            return []
        today_str = date.today().strftime("%Y-%m-%d")
        today_events = [e for e in events if e.get("commence_time","").startswith(today_str)]
        if not today_events:
            tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
            today_events = [e for e in events if e.get("commence_time","").startswith(tomorrow_str)]
        if not today_events:
            return []
        markets = ODDS_API_PROP_MARKETS.get(sport, [])
        if not markets:
            return []
        markets_str = ",".join(markets)
        all_props = []
        seen = set()
        for event in today_events[:5]:
            event_id = event.get("id", "")
            if not event_id:
                continue
            props_url = f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds?apiKey={ODDS_API_KEY}&regions=us,us2&markets={markets_str}&oddsFormat=american&bookmakers={ODDS_API_BOOKS_PROPS}"
            try:
                props_resp = _http.get(props_url, headers=HEADERS, timeout=15)
                api_budget_increment("ODDS_API", amount=10 * len(markets) * 2)  # 10 x N markets x 2 regions
                if props_resp.status_code != 200:
                    continue
                event_data = props_resp.json()
                for bookmaker in event_data.get("bookmakers", []):
                    book_key = bookmaker.get("key","")
                    book_title = bookmaker.get("title", book_key)
                    for market in bookmaker.get("markets", []):
                        market_key = market.get("key", "")
                        stat_name = ODDS_API_STAT_MAP.get(market_key, market_key.replace("_", " ").title())
                        for outcome in market.get("outcomes", []):
                            player = outcome.get("description", "")
                            side = outcome.get("name", "").upper()
                            line = outcome.get("point")
                            if not player or line is None:
                                continue
                            if side not in ("OVER", "UNDER"):
                                continue
                            if side != "OVER":
                                continue
                            key = (sport, player, stat_name, float(line))
                            if key in seen:
                                continue
                            seen.add(key)
                            all_props.append({
                                "Player": player,
                                "Prop": stat_name,
                                "Line": float(line),
                                "Side": "OVER",
                                "Sport": sport,
                                "source": f"OddsAPI_{book_title}",
                                "OddsType": "standard",
                                "OverOdds": outcome.get("price", -110),
                                "UnderOdds": None,
                            })
                time.sleep(0.2)
            except (requests.RequestException, KeyError, ValueError) as e:
                st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_odds_api_props", "error": str(e)[:100]})
                continue
        if all_props:
            with open(cache_path, "wb") as f:
                pickle.dump(all_props, f)
            st.caption(f"✅ Odds API: {len(all_props)} props from Bovada/MyBookie/DK/FD/Novig")
        return all_props
    except (requests.RequestException, KeyError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_odds_api_props", "error": str(e)[:100]})
        return []


def fetch_parlayplay_props(sport):
    allowed, reason = api_budget_check("PARLAYPLAY")
    if not allowed:
        return []
    cache_path = os.path.join(CACHE_DIR, f"parlayplay_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 ParlayPlay: cached ({age_mins:.0f}m old)")
                return cached
    url = "https://parlayplay.io/api/v1/crossgame/offering/"
    pp_session = st.secrets.get("PARLAYPLAY_SESSION", "")
    pp_cookie_full = st.secrets.get("PARLAYPLAY_COOKIES", "")
    if pp_cookie_full:
        pp_cookie = pp_cookie_full
    elif pp_session:
        pp_cookie = f"sessionid={pp_session}"
    else:
        pp_cookie = ""
    pp_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://parlayplay.io",
        "Referer": "https://parlayplay.io/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "x-csrftoken": "1",
        "x-parlay-request": "1",
        "x-parlayplay-native-platform": "web",
        "x-parlayplay-platform": "web",
        "x-requested-with": "XMLHttpRequest",
        "Cookie": pp_cookie,
    }
    league_slug_map = {"NBA": ["nba"], "MLB": ["mlb"], "NHL": ["nhl"], "NFL": ["nfl"], "WNBA": ["wnba"]}
    valid_slugs = league_slug_map.get(sport, [])
    if not valid_slugs:
        return []
    stat_map = {
        "Points": "Points", "Rebounds": "Rebounds", "Assists": "Assists",
        "Pts + Reb + Ast": "Pts+Reb+Ast", "Pts + Reb": "Pts+Reb+Ast", "Pts + Ast": "Pts+Reb+Ast",
        "Steals": "Steals", "Blocks": "Blocked Shots", "Three Pointers Made": "3-PT Made",
        "Threes": "3-PT Made", "Turnovers": "Turnovers", "Hits": "Hits",
        "Homeruns": "Home Runs", "Home Runs": "Home Runs", "RBIs": "RBIs",
        "Runs": "Runs", "Singles": "Singles", "Doubles": "Doubles", "Total Bases": "Total Bases",
        "Hits + Runs + RBIs": "Hits+Runs+RBIs", "Walks": "Walks", "Strikeouts": "Strikeouts",
        "Pitcher Strikeouts": "Strikeouts", "Goals": "Goals", "Shots on Goal": "Shots On Goal",
        "Shots On Goal": "Shots On Goal", "Passing Yards": "Passing Yards",
        "Rushing Yards": "Rushing Yards", "Receiving Yards": "Receiving Yards",
        "Touchdowns": "Touchdowns", "Receptions": "Receptions",
    }
    try:
        # Use curl_cffi to bypass TLS fingerprinting / bot protection
        try:
            from curl_cffi import requests as cf_requests
            resp = cf_requests.get(url, headers=pp_headers, impersonate="chrome120", timeout=20)
        except (requests.RequestException, KeyError, ValueError):
            resp = _http.get(url, headers=pp_headers, timeout=20)
        api_budget_increment("PARLAYPLAY")
        if resp.status_code == 403:
            st.caption("⚠️ ParlayPlay: 403 — blocked by bot protection")
            if os.path.exists(cache_path):
                try: os.remove(cache_path)
                except (OSError, IOError): pass
            return []
        if resp.status_code != 200:
            return []
        data = resp.json()
        players_data = data.get("players", [])
        if not players_data:
            return []
        props = []
        seen = set()
        alt_lines_store = {}
        for player_entry in players_data:
            player_obj = player_entry.get("player", {})
            player_name = player_obj.get("fullName", "")
            if not player_name:
                continue
            match_obj = player_entry.get("match", {})
            league_obj = match_obj.get("league", {})
            league_slug = league_obj.get("slug", "").lower()
            if league_slug not in valid_slugs:
                continue
            team_obj = player_obj.get("team", {})
            team_abbr = team_obj.get("teamAbbreviation", "")
            home_team = match_obj.get("homeTeam", {}).get("teamAbbreviation", "")
            away_team = match_obj.get("awayTeam", {}).get("teamAbbreviation", "")
            for stat in player_entry.get("stats", []):
                challenge_name = stat.get("challengeName", "")
                stat_name = stat_map.get(challenge_name, challenge_name)
                alt_lines_obj = stat.get("altLines", {})
                line_values = alt_lines_obj.get("values", [])
                if not line_values:
                    continue
                main_line = next((lv for lv in line_values if lv.get("isMainLine")), line_values[0] if line_values else None)
                if not main_line:
                    continue
                line_val = main_line.get("selectionPoints")
                if line_val is None:
                    continue
                multiplier = stat.get("defaultMultiplier", 1.77)
                live_val = stat.get("liveStatValue", 0)
                alt_count = stat.get("altLineCount", 0)
                alt_key = f"{player_name}_{stat_name}"
                if len(line_values) > 1:
                    alt_lines_store[alt_key] = [{"line": lv.get("selectionPoints"), "odds": lv.get("decimalPriceOver"), "isMain": lv.get("isMainLine", False), "source": "ParlayPlay"} for lv in line_values if lv.get("selectionPoints") is not None]
                key = (player_name, stat_name, float(line_val))
                if key in seen:
                    continue
                seen.add(key)
                props.append({
                    "Player": player_name,
                    "Prop": stat_name,
                    "Line": float(line_val),
                    "Side": "OVER",
                    "Sport": sport,
                    "source": "ParlayPlay",
                    "OddsType": "standard",
                    "PPMultiplier": multiplier,
                    "LiveStat": live_val,
                    "AltLineCount": alt_count,
                    "TeamAbbr": team_abbr,
                    "HomeTeam": home_team,
                    "AwayTeam": away_team,
                })
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)
            alt_count = sum(1 for p in props if p.get("AltLineCount", 0) > 1)
            st.caption(f"✅ ParlayPlay: {len(props)} props | {alt_count} with alt lines | All sports")
        return props
    except (KeyError, TypeError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_parlayplay_props", "error": str(e)[:100]})
        return []


def fetch_bdl_props(sport):
    if sport != "NBA":
        return []
    if not BDL_API_KEY:
        return []
    allowed, reason = api_budget_check("BDL")
    if not allowed:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_bdl_props", "error": reason})
        return []
    daily_used = get_api_counter(API_BUDGETS["BDL"]["counter_path"]).get("count", 0)
    cache_path = os.path.join(CACHE_DIR, "bdl_props_nba.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                st.caption(f"📦 BDL Props: using cached data ({age_mins:.0f}m old)")
                return cached
    today_str = date.today().strftime("%Y-%m-%d")
    games_url = f"https://api.balldontlie.io/v1/games?dates[]={today_str}&per_page=30"
    bdl_headers = {"Authorization": BDL_API_KEY}
    try:
        games_resp = _http.get(games_url, headers=bdl_headers, timeout=10)
        api_budget_increment("BDL")
        if games_resp.status_code != 200:
            return []
        game_ids = [g["id"] for g in games_resp.json().get("data", [])]
        if not game_ids:
            return []
        all_props = []
        seen = set()
        stat_map = {
            "points": "Points", "rebounds": "Rebounds", "assists": "Assists",
            "pts_reb_ast": "Pts+Reb+Ast", "steals": "Steals", "blocks": "Blocked Shots",
            "three_pointers_made": "3-PT Made", "turnovers": "Turnovers",
        }
        for game_id in game_ids[:5]:
            props_url = f"https://api.balldontlie.io/v1/player_props?game_id={game_id}"
            try:
                props_resp = _http.get(props_url, headers=bdl_headers, timeout=10)
                api_budget_increment("BDL")
                if props_resp.status_code != 200:
                    continue
                for prop in props_resp.json().get("data", []):
                    if prop.get("market", {}).get("type") != "over_under":
                        continue
                    player = prop.get("player", {})
                    player_name = f"{player.get('first_name','')} {player.get('last_name','')}".strip()
                    prop_type = prop.get("prop_type", "")
                    line = prop.get("line_value")
                    if not player_name or not line:
                        continue
                    if not prop_type:
                        continue
                    stat_name = stat_map.get(prop_type, prop_type.replace("_", " ").title())
                    try:
                        line_val = float(line)
                    except (ValueError, TypeError):
                        continue
                    key = (player_name, stat_name, line_val)
                    if key in seen:
                        continue
                    seen.add(key)
                    all_props.append({
                        "Player": player_name,
                        "Prop": stat_name,
                        "Line": line_val,
                        "Side": "OVER",
                        "Sport": "NBA",
                        "source": "BDL_DraftKings",
                        "OddsType": "standard"
                    })
                time.sleep(0.3)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        if all_props:
            with open(cache_path, "wb") as f:
                pickle.dump(all_props, f)
            monthly_limit = API_BUDGETS["BDL"].get("monthly_limit", 200)
            st.caption(f"✅ BDL Props: {len(all_props)} props fetched — BDL monthly: {daily_used + 1}/{monthly_limit} calls")
        return all_props
    except (requests.RequestException, KeyError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_bdl_props", "error": str(e)[:100]})
        return []

@st.cache_data(ttl=600)


def fetch_pinnacle_lines(sport):
    """
    Fetch Pinnacle lines via OddsPAPI (already in our stack).
    Cache in session state — only 1 API call per board load per sport.
    Respects free tier: 100 calls/day, 1000/month.
    """
    cache_key = f"pinnacle_{sport}"
    if st.session_state.get(cache_key):
        return st.session_state[cache_key]

    # Check disk cache first — 60 min TTL for Pinnacle lines
    cache_path = os.path.join(CACHE_DIR, f"pinnacle_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 60:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached

    if not ODDSPAPI_KEY:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_pinnacle_lines", "error": "ODDSPAPI_KEY not set in secrets"})
        return {}

    allowed, reason = api_budget_check("ODDSPAPI")
    if not allowed:
        st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_pinnacle_lines", "error": reason})
        return {}

    sport_id_map = {"NBA": 4, "WNBA": 4, "MLB": 3, "NHL": 6, "NFL": 1}
    sport_id = sport_id_map.get(sport)
    if not sport_id:
        return {}

    pinnacle_data = {"props": {}, "games": {}}

    try:
        # Get tournaments
        t_resp = _http.get(
            f"https://api.oddspapi.io/v4/tournaments?sportId={sport_id}&apiKey={ODDSPAPI_KEY}",
            timeout=10
        )
        if t_resp.status_code != 200:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_pinnacle_lines", "error": f"tournaments HTTP {t_resp.status_code}: {t_resp.text[:150]}"})
            return {}

        tournaments = t_resp.json()
        top_ids = [str(t["tournamentId"]) for t in tournaments
                   if t.get("upcomingFixtures", 0) > 0][:3]
        if not top_ids:
            top_ids = [str(t["tournamentId"]) for t in tournaments[:2]]
        if not top_ids:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_pinnacle_lines", "error": f"no tournaments returned for sportId={sport_id} ({sport})"})
            return {}

        tournament_ids = ",".join(top_ids)

        # Fetch Pinnacle ONLY — saves API credits vs fetching all books
        resp = _http.get(
            f"https://api.oddspapi.io/v4/odds-by-tournaments"
            f"?bookmaker=pinnacle&tournamentIds={tournament_ids}"
            f"&apiKey={ODDSPAPI_KEY}&oddsFormat=american",
            headers=HEADERS,
            timeout=15
        )
        api_budget_increment("ODDSPAPI")

        if resp.status_code != 200:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_pinnacle_lines", "error": f"odds-by-tournaments HTTP {resp.status_code}: {resp.text[:150]}"})
            return {}

        data = resp.json()

        for event in data.get("events", []):
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            for bookmaker in event.get("bookmakers", []):
                if bookmaker.get("key", "").lower() != "pinnacle":
                    continue
                for market in bookmaker.get("markets", []):
                    mkey = market.get("key", "")
                    outcomes = market.get("outcomes", [])

                    # Player props
                    if "player" in mkey.lower():
                        over_out = next((o for o in outcomes if o.get("name","").upper() == "OVER"), None)
                        under_out = next((o for o in outcomes if o.get("name","").upper() == "UNDER"), None)
                        if over_out and under_out:
                            over_imp = devig_odds(over_out.get("price"))
                            under_imp = devig_odds(under_out.get("price"))
                            if over_imp and under_imp:
                                total = over_imp + under_imp
                                over_nv = round(over_imp / total, 4)
                                under_nv = round(under_imp / total, 4)
                                player = over_out.get("description", "")
                                line = over_out.get("point")
                                stat = mkey.replace("player_","").replace("_"," ").title()
                                if player and line is not None:
                                    pkey = (normalize_name(player), stat.lower(), float(line))
                                    pinnacle_data["props"][pkey] = {
                                        "over_prob": over_nv,
                                        "under_prob": under_nv,
                                        "over_odds": over_out.get("price"),
                                        "under_odds": under_out.get("price"),
                                        "player": player, "stat": stat, "line": float(line)
                                    }

                    # Game lines
                    elif mkey in ("h2h", "spreads", "totals"):
                        if len(outcomes) >= 2:
                            imp_a = devig_odds(outcomes[0].get("price"))
                            imp_b = devig_odds(outcomes[1].get("price"))
                            if imp_a and imp_b:
                                total = imp_a + imp_b
                                prob_a = round(imp_a / total, 4)
                                game_key = (normalize_name(home), normalize_name(away), mkey)
                                pinnacle_data["games"][game_key] = {
                                    "prob_home": prob_a,
                                    "prob_away": round(imp_b / total, 4),
                                    "line_home": outcomes[0].get("point"),
                                    "line_away": outcomes[1].get("point"),
                                    "odds_home": outcomes[0].get("price"),
                                    "odds_away": outcomes[1].get("price"),
                                }

        # Cache to disk
        with open(cache_path, "wb") as f:
            pickle.dump(pinnacle_data, f)
        n_props = len(pinnacle_data["props"])
        n_games = len(pinnacle_data["games"])
        return pinnacle_data

    except (KeyError, TypeError, ValueError) as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "fetch_pinnacle_lines",
            "error": str(e)[:100]
        })
        return {}


def fetch_mlb_player_game_logs(player_name, last_n=15):
    """Fetch MLB player recent game logs via MLB Stats API."""
    try:
        cache_key = f"mlb_logs_{normalize_name(player_name)}"
        if cache_key in st.session_state:
            return st.session_state[cache_key]
        # Search for player ID
        search_url = f"https://statsapi.mlb.com/api/v1/people/search?names={player_name.replace(' ','+')}&sportId=1"
        r = _http.get(search_url, timeout=8)
        if r.status_code != 200: return []
        people = r.json().get("people", [])
        if not people: return []
        player_id = people[0]["id"]
        # Get recent game logs
        stats_url = (f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
                     f"?stats=gameLog&season={_current_mlb_season_year()}&sportId=1&group=hitting")
        r2 = _http.get(stats_url, timeout=8)
        if r2.status_code != 200: return []
        splits = r2.json().get("stats", [{}])[0].get("splits", [])[-last_n:]
        logs = []
        for s in splits:
            stat = s.get("stat", {})
            game = s.get("game", {})
            team = s.get("team", {})
            opponent = s.get("opponent", {})
            logs.append({
                "date":     s.get("date",""),
                "home":     s.get("isHome", True),
                "opponent": opponent.get("abbreviation",""),
                "H":        stat.get("hits", 0),
                "HR":       stat.get("homeRuns", 0),
                "RBI":      stat.get("rbi", 0),
                "R":        stat.get("runs", 0),
                "BB":       stat.get("baseOnBalls", 0),
                "K":        stat.get("strikeOuts", 0),
                "AB":       stat.get("atBats", 0),
            })
        return logs
    except (requests.RequestException, ValueError, KeyError):
        return []


def fetch_nhl_player_stats(player_name):
    """
    NHL player rolling averages, built from fetch_nhl_player_game_logs --
    there's no dedicated NHL season-average endpoint the way WNBA/NFL/etc.
    have, so this averages the last 20 games into per-game stats. Matches
    the fetch_X_player_stats(player) -> dict pattern every other sport uses
    so it plugs into score_pick_standalone's live-fetch dispatch, which
    previously had no NHL branch at all -- every NHL board-paste prop fell
    straight to the flat league baseline or a forced PASS regardless of
    which player it actually was.
    """
    logs = fetch_nhl_player_game_logs(player_name, last_n=20)
    if not logs:
        return {}
    n = len(logs)
    pts = sum(g.get("PTS", 0) or 0 for g in logs) / n
    goals = sum(g.get("G", 0) or 0 for g in logs) / n
    assists = sum(g.get("A", 0) or 0 for g in logs) / n
    sog = sum(g.get("SOG", 0) or 0 for g in logs) / n
    return {
        "PTS": round(pts, 2), "GOALS": round(goals, 2), "ASSISTS": round(assists, 2),
        "SOG": round(sog, 2), "n_games": n, "_source": "NHL API",
    }


def fetch_nhl_player_game_logs(player_name, last_n=15):
    """Fetch NHL player recent game logs via NHL API."""
    try:
        cache_key = f"nhl_logs_{normalize_name(player_name)}"
        if cache_key in st.session_state:
            return st.session_state[cache_key]
        # Player ID lookup: search.d3.nhle.com is confirmed dead (404 from
        # datacenter IPs, live-tested) -- use the team-roster-iteration
        # lookup instead (same working approach as WNBA's roster fix).
        roster_ids = fetch_nhl_full_roster_ids()
        norm = normalize_name(player_name)
        player_id = next((pid for name, pid in roster_ids.items()
                           if normalize_name(name) == norm), None)
        if not player_id:
            return []
        # Get game log
        log_url = f"https://api-web.nhle.com/v1/player/{player_id}/game-log/now"
        r2 = _http.get(log_url, timeout=8)
        if r2.status_code != 200: return []
        game_log = r2.json().get("gameLog", [])[-last_n:]
        logs = []
        for g in game_log:
            logs.append({
                "date":      g.get("gameDate",""),
                "home":      g.get("homeRoadFlag","H") == "H",
                "opponent":  g.get("opponentAbbrev",""),
                "PTS":       g.get("points", 0),
                "G":         g.get("goals", 0),
                "A":         g.get("assists", 0),
                "SOG":       g.get("shots", 0),
                "TOI":       g.get("toi","0:00"),
            })
        return logs
    except (requests.RequestException, ValueError, KeyError):
        return []


@st.cache_data(ttl=1800)


def fetch_wnba_player_game_logs(player_name, last_n=15):
    """Fetch WNBA player recent game logs via WNBA Stats API."""
    try:
        cache_key = f"wnba_logs_{normalize_name(player_name)}"
        if cache_key in st.session_state:
            return st.session_state[cache_key]
        url = ("https://stats.wnba.com/stats/playergamelogs"
               "?DateFrom=&DateTo=&GameSegment=&LastNGames=0&LeagueID=10"
               "&Location=&MeasureType=Base&Month=0&OpponentTeamID=0"
               "&Outcome=&PORound=0&PerMode=PerGame&Period=0&PlayerID=0"
               f"&Season={_current_wnba_season_year()}&SeasonSegment=&SeasonType=Regular+Season"
               "&ShotClockRange=&VsConference=&VsDivision=")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.wnba.com/",
            "Origin": "https://www.wnba.com",
        }
        r = _http.get(url, headers=headers, timeout=10)
        if r.status_code != 200: return []
        result_sets = r.json().get("resultSets", [])
        if not result_sets: return []
        headers_list = result_sets[0]["headers"]
        rows = result_sets[0]["rowSet"]
        # Filter by player name
        name_idx = headers_list.index("PLAYER_NAME") if "PLAYER_NAME" in headers_list else -1
        if name_idx < 0: return []
        player_rows = [row for row in rows
                       if normalize_name(str(row[name_idx])) == normalize_name(player_name)][-last_n:]
        logs = []
        idx = {h: i for i, h in enumerate(headers_list)}
        for row in player_rows:
            logs.append({
                "date":      str(row[idx.get("GAME_DATE",0)])[:10],
                "home":      "vs" in str(row[idx.get("MATCHUP",0)]),
                "opponent":  str(row[idx.get("MATCHUP",0)]).split()[-1] if "MATCHUP" in idx else "",
                "PTS":       row[idx.get("PTS",0)] or 0,
                "REB":       row[idx.get("REB",0)] or 0,
                "AST":       row[idx.get("AST",0)] or 0,
                "MIN":       row[idx.get("MIN",0)] or 0,
            })
        return logs
    except (requests.RequestException, ValueError, KeyError):
        return []





# ----- TAB 6: PLAYER LOOKUP -----


# ── Action Network game lines ─────────────────────────────────────────────

# Book IDs from live browser session capture (2026-07-04).
# 8=MyBookie  15=Caesars  30=BetMGM  4727=FanDuel  4795=DraftKings
# 79=PointsBet  2988=WynnBET  69=BetRivers  68=Barstool  75=Bet365  123=Unibet  71=BetAmerica
_AN_BOOK_IDS = "8,15,30,4727,4795,79,2988,69,68,75,123,71"

_AN_SPORT_SLUGS = {
    "mlb":        "mlb",   "baseball":    "mlb",
    "nba":        "nba",   "basketball":  "nba",
    "nfl":        "nfl",   "football":    "nfl",
    "nhl":        "nhl",   "hockey":      "nhl",
    "wnba":       "wnba",
    "ncaab":      "ncaab", "ncaaf":       "ncaaf",
    "ufc":        "ufc",   "mma":         "ufc",
    "soccer":     "soccer","mls":         "soccer",
}


def fetch_action_network_lines(sport: str) -> list:
    """
    Pull full-game lines from Action Network's public scoreboard API.
    No authentication required — confirmed 200 public endpoint.

    sport:   case-insensitive sport slug (mlb/nba/nfl/nhl/wnba/ncaab/ncaaf/ufc/soccer).
    Returns: list of dicts per game that has a MyBookie (book_id=8) line:
               {Home, Away, HomeML, AwayML, Spread, SpreadOdds,
                Total, OverOdds, UnderOdds, book, book_id}
    Returns [] if no MyBookie lines are available, so callers can fall back
    to the Gist harvester.
    Cached 10 minutes (odds update frequently; shorter TTL than roster caches).
    """
    slug = _AN_SPORT_SLUGS.get(sport.lower().strip(), sport.lower().strip())
    today = datetime.now().strftime("%Y%m%d")

    cache_key  = f"an_lines_{slug}_{today}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_m = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_m < 10:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    url = (
        f"https://api.actionnetwork.com/web/v1/scoreboard/{slug}"
        f"?bookIds={_AN_BOOK_IDS}&date={today}&periods=event"
    )
    _an_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        resp = _http.get(url, headers=_an_headers, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    games  = data.get("games", [])
    result = []

    for g in games:
        teams = g.get("teams", [])
        if len(teams) < 2:
            continue

        # Resolve home/away by matching team IDs
        away_id   = g.get("away_team_id")
        home_id   = g.get("home_team_id")
        team_by_id = {t["id"]: t for t in teams}
        away_team  = team_by_id.get(away_id, teams[0])
        home_team  = team_by_id.get(home_id, teams[1] if len(teams) > 1 else teams[0])

        away_name = away_team.get("full_name") or away_team.get("display_name", "")
        home_name = home_team.get("full_name") or home_team.get("display_name", "")

        # Find MyBookie full-game odds entry (book_id=8, type="game")
        mybookie_odds = next(
            (o for o in g.get("odds", [])
             if o.get("book_id") == 8 and o.get("type") == "game"),
            None
        )
        if not mybookie_odds:
            continue

        result.append({
            "Home":       home_name,
            "Away":       away_name,
            "HomeML":     mybookie_odds.get("ml_home"),
            "AwayML":     mybookie_odds.get("ml_away"),
            "Spread":     mybookie_odds.get("spread_away"),
            "SpreadOdds": mybookie_odds.get("spread_away_line"),
            "Total":      mybookie_odds.get("total"),
            "OverOdds":   mybookie_odds.get("over"),
            "UnderOdds":  mybookie_odds.get("under"),
            "book":       "MyBookie",
            "book_id":    8,
        })

    if result:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception:
            pass

    return result

# ═══════════════════════════════════════════════════════════════════════════
# FanDuel + Caesars game lines — server-side, no browser required
# ═══════════════════════════════════════════════════════════════════════════
# FANDUEL:
#   Primary  – Action Network (book_id=69, FanDuel NJ).  Already in
#              _AN_BOOK_IDS so the scoreboard request costs nothing extra.
#              Confirmed: 15/15 MLB, 4/4 NBA, 16/16 NFL; no auth.
#   Fallback – FanDuel sbapi: sbapi.{state}.sportsbook.fanduel.com/api/
#              content-managed-page?page=SPORT&eventTypeId={id}&_ak=FhMFpcPWXMeyZxOx
#              This is a different API from the PerimeterX-protected
#              smp.*.sportsbook.fanduel.com endpoint.  No PX challenge,
#              no auth; confirmed HTTP 200 from datacenter IPs.
#              American odds are embedded directly in each runner:
#              runners[].winRunnerOdds.americanDisplayOdds.americanOddsInt
# CAESARS:
#   api.americanwagering.com returns HTTP 403 from CloudFront on
#   datacenter IPs.  Action Network (book_id=123, Caesars NJ) is the
#   only viable server-side source.
#   Confirmed: 14-15/15 MLB, 4/4 NBA, 16/16 NFL; no auth.
# ═══════════════════════════════════════════════════════════════════════════

_FD_SBAPI_AK    = "FhMFpcPWXMeyZxOx"
_FD_SBAPI_STATE = "nj"   # any US state works; nj confirmed 200
_FD_SBAPI_ET    = {       # FanDuel eventTypeId → sport slug
    "mlb":  7511,         # Baseball (27 MLB events confirmed live)
    "nba":  7522,         # Basketball (NBA + WNBA share this ID)
    "nfl":  6423,         # American Football (99 events confirmed)
    "nhl":  7524,         # Ice Hockey
    "wnba": 7522,         # shares Basketball ID with NBA
}


def _fetch_an_book_lines(sport: str, book_id: int, book_label: str) -> list:
    """
    Pull full-game lines from Action Network for any book already listed
    in _AN_BOOK_IDS.  Reuses the same scoreboard request but filters to
    the requested book_id instead of MyBookie (8).
    Cached 10 minutes per (sport, book_id, date).
    Returns same schema as fetch_action_network_lines().
    """
    slug  = _AN_SPORT_SLUGS.get(sport.lower().strip(), sport.lower().strip())
    today = datetime.now().strftime("%Y%m%d")

    cache_key  = f"an_lines_{slug}_{book_id}_{today}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_m = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_m < 10:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    url = (
        f"https://api.actionnetwork.com/web/v1/scoreboard/{slug}"
        f"?bookIds={_AN_BOOK_IDS}&date={today}&periods=event"
    )
    _an_hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        resp = _http.get(url, headers=_an_hdrs, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    result = []
    for g in data.get("games", []):
        teams = g.get("teams", [])
        if len(teams) < 2:
            continue
        away_id    = g.get("away_team_id")
        home_id    = g.get("home_team_id")
        team_by_id = {t["id"]: t for t in teams}
        away_team  = team_by_id.get(away_id, teams[0])
        home_team  = team_by_id.get(home_id, teams[1] if len(teams) > 1 else teams[0])
        away_name  = away_team.get("full_name") or away_team.get("display_name", "")
        home_name  = home_team.get("full_name") or home_team.get("display_name", "")

        odds = next(
            (o for o in g.get("odds", [])
             if o.get("book_id") == book_id and o.get("type") == "game"),
            None,
        )
        if not odds:
            continue

        result.append({
            "Home":       home_name,
            "Away":       away_name,
            "HomeML":     odds.get("ml_home"),
            "AwayML":     odds.get("ml_away"),
            "Spread":     odds.get("spread_away"),
            "SpreadOdds": odds.get("spread_away_line"),
            "Total":      odds.get("total"),
            "OverOdds":   odds.get("over"),
            "UnderOdds":  odds.get("under"),
            "book":       book_label,
            "book_id":    book_id,
        })

    if result:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception:
            pass
    return result


def _fetch_fanduel_sbapi(sport: str) -> list:
    """
    Fallback FanDuel lines via state sbapi — no PerimeterX, no auth.
    Distinct from the blocked smp.*.sportsbook.fanduel.com endpoint.
    Prices are embedded: runners[].winRunnerOdds.americanDisplayOdds.americanOddsInt
    Cached 10 minutes.
    """
    et = _FD_SBAPI_ET.get(sport.lower().strip())
    if not et:
        return []

    cache_path = os.path.join(
        CACHE_DIR,
        f"fd_sbapi_{sport.lower()}_{datetime.now().strftime('%Y%m%d')}.pkl",
    )
    if os.path.exists(cache_path):
        age_m = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_m < 10:
            cached = _safe_load_pkl(cache_path)
            if cached is not None:
                return cached

    url = (
        f"https://sbapi.{_FD_SBAPI_STATE}.sportsbook.fanduel.com/api/content-managed-page"
        f"?page=SPORT&eventTypeId={et}&_ak={_FD_SBAPI_AK}&timezone=America%2FNew_York"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        resp = _http.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] FanDuel sbapi HTTP {resp.status_code}")
            return []
        att = resp.json().get("attachments", {})
    except Exception as e:
        print(f"[WARN] _fetch_fanduel_sbapi: {e}")
        return []

    events  = att.get("events",  {})   # {eventId: {name, eventId, …}}
    markets = att.get("markets", {})   # {marketId: {marketName, marketType, eventId, runners, …}}

    # Group markets by eventId for O(n) lookup
    by_event: dict = {}
    for m in markets.values():
        by_event.setdefault(str(m.get("eventId", "")), []).append(m)

    def _price(runner: dict) -> "int | None":
        return (
            (runner.get("winRunnerOdds") or {})
            .get("americanDisplayOdds", {})
            .get("americanOddsInt")
        )

    result = []
    for eid, ev in events.items():
        ev_markets = by_event.get(str(eid), [])
        if not ev_markets:
            continue

        # FanDuel uses "Home Team v Away Team" naming
        name   = ev.get("name", "")
        parts  = name.split(" v ", 1)
        home_name = parts[0].strip() if len(parts) == 2 else name
        away_name = parts[1].strip() if len(parts) == 2 else ""

        row: dict = {"Home": home_name, "Away": away_name,
                     "book": "FanDuel", "book_id": 69}

        for m in ev_markets:
            mname   = m.get("marketName", "")
            mtype   = m.get("marketType", "")
            runners = m.get("runners", [])

            if mtype == "MATCH_ODDS" or mname == "Moneyline":
                home_r = next((r for r in runners
                               if r.get("result", {}).get("type") == "HOME"), None)
                away_r = next((r for r in runners
                               if r.get("result", {}).get("type") == "AWAY"), None)
                if home_r:
                    row["HomeML"] = _price(home_r)
                if away_r:
                    row["AwayML"] = _price(away_r)

            elif "HANDICAP" in mtype or mname in ("Spread", "Run Line", "Puck Line"):
                away_r = next((r for r in runners
                               if r.get("result", {}).get("type") == "AWAY"), None)
                if away_r:
                    row["Spread"]     = away_r.get("handicap")
                    row["SpreadOdds"] = _price(away_r)

            elif "OVER_UNDER" in mtype or mname in ("Total Points", "Total Runs", "Total Goals"):
                over_r  = next((r for r in runners
                                if "over"  in r.get("runnerName", "").lower()), None)
                under_r = next((r for r in runners
                                if "under" in r.get("runnerName", "").lower()), None)
                if over_r:
                    row["Total"]    = over_r.get("handicap")
                    row["OverOdds"] = _price(over_r)
                if under_r:
                    row["UnderOdds"] = _price(under_r)

        if "HomeML" in row or "Spread" in row:
            result.append(row)

    if result:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception:
            pass
    return result


def fetch_fanduel_lines(sport: str = "MLB") -> list:
    """
    FanDuel game lines (ML, spread, total) — no browser, no PerimeterX.

    Primary:  Action Network (book_id=69, FanDuel NJ).  Confirmed live:
              15/15 MLB, 4/4 NBA, 16/16 NFL; no auth required.
    Fallback: FanDuel state sbapi (sbapi.nj.sportsbook.fanduel.com).
              Public content API, completely separate from the PerimeterX-
              protected smp.*.sportsbook.fanduel.com endpoint.
              HTTP 200 from datacenter IPs confirmed; runner prices embedded.

    REMOVED (2026-07): a Playwright last-resort tier was briefly wired in
    here and caused a production segfault -- see fetch_fanduel_props_from_gist's
    docstring for the full explanation (sync API + Streamlit's threaded
    script execution is a known-bad combination that crashes natively,
    bypassing any try/except).

    sport: "MLB" | "NBA" | "NFL" | "NHL" | "WNBA"
    Returns list of:
      {Home, Away, HomeML, AwayML, Spread, SpreadOdds,
       Total, OverOdds, UnderOdds, book="FanDuel", book_id=69}
    """
    result = _fetch_an_book_lines(sport, 69, "FanDuel")
    if not result:
        result = _fetch_fanduel_sbapi(sport)
    return result


def fetch_caesars_lines(sport: str = "MLB") -> list:
    """
    Caesars Sportsbook game lines (ML, spread, total) — no browser required.

    PRIMARY: Action Network (book_id=123, Caesars NJ).
    Confirmed live: 14–15/15 MLB, 4/4 NBA, 16/16 NFL; no auth required.
    api.americanwagering.com (direct Caesars API) is CloudFront-403
    from datacenter IPs — Action Network is the only viable server path
    for the direct-from-Caesars feed.

    FALLBACK (Jul 10 2026): Unabated `straight` market data (source_id=20).
    Action Network already works well here, so this is a cross-check/
    backup rather than a fix for something broken — but it's an
    independent second reading of Caesars' actual lines, worth having
    in case Action Network's Caesars coverage ever gaps for a sport/game.

    sport: "MLB" | "NBA" | "NFL" | "NHL" | "WNBA"
    Returns list of:
      {Home, Away, HomeML, AwayML, Spread, SpreadOdds,
       Total, OverOdds, UnderOdds, book="Caesars", book_id=123}
    """
    primary = _fetch_an_book_lines(sport, 123, "Caesars")
    return primary



def fetch_vsin_from_gist(sport: str = "MLB", max_age_minutes: int = 45) -> tuple:
    """
    Reads VSiN Vegas line-tracker data from the Gist (pushed by
    scripts/vsin_harvester.py — plain curl against data.vsin.com's
    server-rendered linetracker, no auth, no browser).

    Covers 8 books: Circa, Westgate, South Point, Stations, Wynn (Nevada
    sharp books) + BetMGM, Caesars, Boomers (online). Circa/Westgate in
    particular are considered among the sharpest lines in the US and
    aren't available through OddsAPI or Unabated — this is a genuinely
    independent sharp-reference source, not a duplicate of Pinnacle.

    NOTE: this source's freshness field is "updated", not "captured_at"
    like most other Gist-backed sources in this file — do not swap this
    to the shared _is_fresh() helper without accounting for that, or every
    call will silently report stale forever (this bit Unabated earlier).

    Returns (games_list, source_label). games_list items:
        {time, away_team, home_team, open: {spread,ml,total},
         books: {book_name: {spread, ml, total, spread_odds, ...}}}
    """
    combined = _read_gist_file("betcouncil_evbets_combined.json", cache_minutes=10)
    data = (combined or {}).get("vsin_lines", {}).get(sport.upper()) if combined else None
    if not data or not isinstance(data, dict):
        return [], "unavailable"

    updated_str = data.get("updated", "")
    if not updated_str:
        return [], "unavailable"
    try:
        from datetime import datetime, timezone
        updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - updated).total_seconds() / 60
        if age_min > max_age_minutes:
            print(f"[VSiN] {sport} data is stale ({age_min:.0f}min old) — skipping")
            return [], "stale"
    except Exception:
        return [], "unavailable"

    games = data.get("games", [])
    if not games:
        return [], "unavailable"
    return games, "vsin_live"


def fetch_evsharps_dingers_from_gist(max_age_minutes: int = 45) -> tuple:
    """
    Reads EVSharps HR-prop data from the Gist (pushed by
    scripts/evsharps_dingers_harvester.py — unauthenticated Railway API
    behind evsharps.com/dingers).

    Each entry carries EVSharps' own pre-computed fair value (their devig,
    independent of ours) plus full batter/pitcher Statcast and multi-book
    odds (b365, BetVictor, DK, FD, ESPN Bet, Hard Rock, ProphetX). The
    fair_val field can be used the same way as Unabated's fair prob — a
    second, independent validator specifically for HR props.

    NOTE: same as fetch_vsin_from_gist above — freshness field here is
    "updated", not "captured_at". Do not swap to the shared _is_fresh()
    helper without handling that.

    MLB-only currently (evsharps.com/dingers is a home-run-specific page).

    Returns (entries_list, source_label). entries_list items include:
        {player_name/name, game, line, book_odds, ev_pct, fair_val,
         batter_percs, hit_rates, homer_logs, ...}
    """
    data = _read_gist_file("betcouncil_evsharps_dingers_MLB.json", cache_minutes=10)
    if not data or not isinstance(data, dict):
        return [], "unavailable"

    updated_str = data.get("updated", "")
    if not updated_str:
        return [], "unavailable"
    try:
        from datetime import datetime, timezone
        updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - updated).total_seconds() / 60
        if age_min > max_age_minutes:
            print(f"[EVSharps dingers] data is stale ({age_min:.0f}min old) — skipping")
            return [], "stale"
    except Exception:
        return [], "unavailable"

    entries = data.get("entries", [])
    if not entries:
        return [], "unavailable"
    return entries, "evsharps_dingers_live"


def fetch_mybookie_lines_html(sport="nfl"):
    """
    NOTE ON NAMING: this is intentionally NOT named fetch_mybookie_lines().
    That name is already taken by the existing Playwright/CDP-based headed-
    browser scraper that intercepts XHR from engine.mybookie.ag/sports_api/*
    (that specific API endpoint is Cloudflare-protected, unlike the plain
    sportsbook page this function scrapes). This function is a distinct,
    separate candidate source — it does NOT replace fetch_mybookie_lines()
    or the Gist harvester wiring (fetch_mybookie_from_gist() / Tampermonkey
    -> betcouncil_mybookie_{sport}.json) and is not called from anywhere
    yet. Wiring/replacement is a separate decision for later.

    Scrapes MyBookie's public sportsbook pages directly — confirmed via live
    HTTP fetch (2026-07-10) that these pages are fully server-rendered HTML
    with odds embedded as data-* attributes on <button> elements. No
    Cloudflare challenge, no login, no JS execution needed (unlike Bet365/
    FanDuel/Caesars, all of which block plain server-side requests).

    Verified URL pattern: https://www.mybookie.ag/sportsbook/{sport}/
    sport examples confirmed live: "nfl", "mlb", "nba" (Jul 10 2026 — same
    template: spread/moneyline/total data-* attributes, no bot wall)
    "nhl", "wnba" share the identical nav/page-generation template as the
    confirmed three (same site-wide structure) but haven't been individually
    spot-checked the same way — should behave the same, flag it if not.
    (nav also lists: "ncaa-basketball", "ufc", "boxing", "e-sports" — same
    page template, not wired in or verified yet)

    Each game row contains up to 6 <button> elements (spread/moneyline/total
    x away/home side), each carrying:
      data-gameid            -> unique game id (string of digits)
      data-wager-type          -> "sp" (spread), "ml" (moneyline), "to" (total)
      data-team                 -> team name for this side of the bet
      data-team-vs               -> opposing team name
      data-points                 -> line value: spread number (e.g. "-3.5"),
                                     total number (e.g. "8"); "0"/"" for ml
      data-odd / data-odds         -> American price, e.g. "-110", "+112"
      data-gameDate / data-time     -> kickoff/start time (attribute name
                                        varies by where it's rendered on page)
      button id suffix "_visit_*"    -> away side  (also: Over, for totals)
      button id suffix "_home_*"      -> home side (also: Under, for totals)

    Returns a dict keyed by game_id:
        {
          "<gameid>": {
            "away_team": "New England Patriots",
            "home_team": "Seattle Seahawks",
            "start_time": "2026-09-09 18:20:00",
            "away_spread": {"points": -3.5, "price": -110},
            "home_spread": {"points": 3.5, "price": -110},
            "away_ml": {"price": 130},
            "home_ml": {"price": -150},
            "total": {"points": 8.0, "over_price": -117, "under_price": -103},
          },
          ...
        }
    Games missing a resolved away_team/home_team (rare partial rows) are
    dropped. Returns {} (never raises) on any network/parse failure, so
    callers can treat this as an optional source like the other harvesters.

    NOTE: requires BeautifulSoup (`from bs4 import BeautifulSoup`) — reuse
    the import already present in fetchers.py for the Covers consensus
    parser rather than adding a second one.

    KNOWN SITE BUG (confirmed live, 2026-07-10): MyBookie's own HTML has a
    templating artifact on "ml" and "to" buttons — a second, differently-
    cased `data-gameId="<id>}"` attribute (note the stray trailing "}")
    duplicates the clean lowercase `data-gameid="<id>"` already present on
    the same tag. HTML parsers case-fold attribute names, so the dirty
    mixed-case value silently overwrites the clean one once parsed, which
    would otherwise split each game's moneyline/total legs into a
    second, bogus game_id and break the merge with its spread legs. We
    strip trailing non-digit characters from data-gameid below specifically
    to neutralize this.
    """
    import re
    from bs4 import BeautifulSoup

    url = f"https://www.mybookie.ag/sportsbook/{sport}/"
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logging.warning(f"[MyBookie] fetch failed ({sport}): {e}")
        return {}

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logging.warning(f"[MyBookie] parse failed ({sport}): {e}")
        return {}

    def _to_num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    games = {}
    for btn in soup.find_all("button", attrs={"data-gameid": True}):
        raw_game_id = btn.get("data-gameid")
        game_id = re.sub(r"\D+$", "", raw_game_id or "")
        if not game_id:
            continue

        wager_type = btn.get("data-wager-type", "")
        team = btn.get("data-team", "")
        team_vs = btn.get("data-team-vs", "")
        points = _to_num(btn.get("data-points"))
        price = _to_num(btn.get("data-odd") or btn.get("data-odds"))
        start_time = btn.get("data-gameDate") or btn.get("data-time") or ""
        btn_id = btn.get("id", "")
        is_away = "_visit_" in btn_id
        is_home = "_home_" in btn_id

        entry = games.setdefault(
            game_id,
            {
                "away_team": None,
                "home_team": None,
                "start_time": "",
                "away_spread": None,
                "home_spread": None,
                "away_ml": None,
                "home_ml": None,
                "total": None,
            },
        )
        if start_time and not entry["start_time"]:
            entry["start_time"] = start_time

        if is_away:
            entry["away_team"] = team or entry["away_team"]
            entry["home_team"] = entry["home_team"] or team_vs
        elif is_home:
            entry["home_team"] = team or entry["home_team"]
            entry["away_team"] = entry["away_team"] or team_vs

        if wager_type == "sp":
            entry["away_spread" if is_away else "home_spread"] = {
                "points": points,
                "price": price,
            }
        elif wager_type == "ml":
            entry["away_ml" if is_away else "home_ml"] = {"price": price}
        elif wager_type == "to":
            total = entry["total"] or {"points": None}
            if points is not None:
                total["points"] = points
            if is_away:
                total["over_price"] = price
            elif is_home:
                total["under_price"] = price
            entry["total"] = total

    return {
        gid: g
        for gid, g in games.items()
        if g["away_team"] and g["home_team"]
    }


# ══════════════════════════════════════════════════════════════════════════
# AUTO-INSTRUMENTATION — health tracking for every fetch_* function
# ══════════════════════════════════════════════════════════════════════════
# Wraps every fetch_* function defined in this module (retroactively, at
# import time) so calls, errors, empty-results, and latency are tracked
# automatically — with zero per-function wiring required. This exists
# because a July 2026 audit found 243 fetch_* functions but only 45 under
# active health monitoring (HARVESTER_REGISTRY, which only covers the
# browser-injection Gist harvesters) — the other ~200 had no visibility at
# all: no way to tell a silently-failing source from one that's simply
# never called this session.
#
# This does NOT delete or judge any function — a function showing
# NEVER_CALLED this session may simply be gated behind an off-season sport
# check, a feature flag, or work in progress. It just makes that visible
# instead of invisible, so the decision to wire in / remove / hold gets
# made with real data instead of a guess.
import time as _fh_time
import threading as _fh_threading

_FETCH_HEALTH = {}
_FETCH_HEALTH_LOCK = _fh_threading.Lock()


def _fh_wrap(_fh_name, _fh_fn):
    def _fh_wrapped(*args, **kwargs):
        _fh_t0 = _fh_time.time()
        try:
            _fh_result = _fh_fn(*args, **kwargs)
            _fh_elapsed = _fh_time.time() - _fh_t0
            with _FETCH_HEALTH_LOCK:
                h = _FETCH_HEALTH.setdefault(_fh_name, {
                    "calls": 0, "errors": 0, "empty": 0,
                    "last_error": None, "last_called_ts": None,
                    "last_success_ts": None, "total_latency": 0.0,
                })
                h["calls"] += 1
                h["last_called_ts"] = _fh_t0
                h["last_success_ts"] = _fh_time.time()
                h["total_latency"] += _fh_elapsed
                if _fh_result in (None, [], {}, ""):
                    h["empty"] += 1
            return _fh_result
        except Exception as _fh_e:
            with _FETCH_HEALTH_LOCK:
                h = _FETCH_HEALTH.setdefault(_fh_name, {
                    "calls": 0, "errors": 0, "empty": 0,
                    "last_error": None, "last_called_ts": None,
                    "last_success_ts": None, "total_latency": 0.0,
                })
                h["calls"] += 1
                h["errors"] += 1
                h["last_called_ts"] = _fh_t0
                h["last_error"] = f"{type(_fh_e).__name__}: {str(_fh_e)[:200]}"
            raise
    _fh_wrapped.__name__ = _fh_name
    _fh_wrapped.__doc__ = getattr(_fh_fn, "__doc__", None)
    _fh_wrapped._fh_original = _fh_fn
    return _fh_wrapped


def fetch_evbets_from_gist(sport: str = "MLB", max_age_minutes: int = 35) -> list:
    """
    Read betcouncil_evbets_combined.json from the shared Gist and return a flat
    list of value-bet dicts filtered to the requested sport.

    Each returned dict includes at minimum:
      "event"   — matchup string (e.g. "Hawthorn Hawks vs North Melbourne Kangaroos")
      "ev_pct"  — EV as decimal number (e.g. 0.524 = +0.52%)
      "book"    — bookmaker slug (e.g. "betfair")

    The JSON is produced by scripts/evbets_refresh.py (pushed every 30 min by GH Actions).
    When there are no active bets the file records total_bets==0 — an empty list is
    returned and is NOT treated as an error.

    Sport matching: slug-based lookup is attempted first (baseball-mlb → MLB), then
    display-name matching. Falls back to all bets if sport mapping is unknown.
    """
    _SLUG_TO_SPORT = {
        "baseball-mlb":              "MLB",
        "basketball-nba":            "NBA",
        "american-football-nfl":     "NFL",
        "hockey-nhl":                "NHL",
        "mma-mixed-martial-arts":    "UFC",
        "basketball-wnba":           "WNBA",
        "soccer-epl":                "SOCCER",
        "aussierules-afl":           "AFL",
    }
    data = _read_gist_file("betcouncil_evbets_combined.json", cache_minutes=max_age_minutes)
    if not data:
        return []
    by_sport = data.get("by_sport", {})
    if not by_sport:
        return []
    sport_upper = sport.upper()
    matches: list[dict] = []
    for display_name, sport_block in by_sport.items():
        if not isinstance(sport_block, dict):
            continue
        slug = sport_block.get("slug", "")
        mapped = _SLUG_TO_SPORT.get(slug, display_name).upper()
        if mapped == sport_upper or display_name.upper() == sport_upper:
            matches.extend(sport_block.get("value_bets", []))
    return matches


def fetch_vsin_splits_from_gist(sport: str = "MLB", max_age_minutes: int = 35) -> list:
    """
    Read betcouncil_vsin_splits.json from the shared Gist and return a list of
    game-split dicts filtered to the requested sport.

    Each game dict shape:
    {
      "gamecode":        "20260731MLB00019",
      "sport":           "MLB",
      "date":            "2026-07-31",
      "road_team":       "New York Yankees",
      "home_team":       "Chicago Cubs",
      "vsin_pick_count": 8,
      "spread": {
        "road": {"line": "+1.5", "handle_pct": 21, "bets_pct": 47},
        "home": {"line": "-1.5", "handle_pct": 79, "bets_pct": 53}
      },
      "total": {
        "line": "9",
        "over":  {"handle_pct": 60, "bets_pct": 44},
        "under": {"handle_pct": 40, "bets_pct": 56}
      },
      "moneyline": {
        "road": {"line": "+141", "handle_pct": 23, "bets_pct": 35},
        "home": {"line": "-171", "handle_pct": 77, "bets_pct": 65}
      }
    }

    Produced by scripts/vsin_splits_refresh.py (GH Actions cron).
    Returns [] on parse error or stale/missing file (not an error — caller handles
    empty gracefully). Sport filter is exact-match on the "sport" field.
    """
    data = _read_gist_file("betcouncil_evbets_combined.json", cache_minutes=max_age_minutes)
    if not data:
        return []
    data = data.get("vsin_splits", {})
    if not data:
        return []
    games = data.get("games", [])
    if not isinstance(games, list):
        return []
    sport_upper = sport.upper()
    return [g for g in games if isinstance(g, dict) and g.get("sport", "").upper() == sport_upper]


def _fh_instrument_all():
    for _fh_gname in list(globals().keys()):
        if not _fh_gname.startswith("fetch_"):
            continue
        _fh_obj = globals()[_fh_gname]
        if not callable(_fh_obj):
            continue
        if getattr(_fh_obj, "_fh_original", None) is not None:
            continue  # already wrapped
        globals()[_fh_gname] = _fh_wrap(_fh_gname, _fh_obj)


_fh_instrument_all()


def get_fetch_health_report():
    """
    Snapshot of every fetch_* function's health for the current process.
    Returns a list of dicts sorted by status severity (worst first):
      status: "DEAD" (100% error rate, has been called), "ERRORING"
      (some errors), "EMPTY_ONLY" (runs, never returns data), "OK",
      or "NEVER_CALLED" (defined but not invoked this session — may be
      gated behind an off-season check or simply not wired in yet, not
      necessarily broken).
    Resets on every process restart — this is live-session visibility,
    not historical/persisted status (HARVESTER_REGISTRY covers the
    persisted-across-restarts case for the Gist-backed sources).
    """
    with _FETCH_HEALTH_LOCK:
        snapshot = {k: dict(v) for k, v in _FETCH_HEALTH.items()}

    all_names = sorted(
        n for n in globals()
        if n.startswith("fetch_") and callable(globals()[n]) and not n.startswith("_fh_")
    )

    _sev = {"DEAD": 0, "ERRORING": 1, "EMPTY_ONLY": 2, "NEVER_CALLED": 3, "OK": 4}
    report = []
    for name in all_names:
        h = snapshot.get(name)
        if not h or h["calls"] == 0:
            report.append({
                "name": name, "status": "NEVER_CALLED", "calls": 0, "errors": 0,
                "error_rate": None, "empty_rate": None, "last_error": None,
                "avg_latency_s": None,
            })
            continue
        err_rate = h["errors"] / h["calls"]
        empty_rate = h["empty"] / h["calls"]
        if err_rate == 1.0:
            status = "DEAD"
        elif err_rate >= 0.3:
            status = "ERRORING"
        elif empty_rate >= 0.8:
            status = "EMPTY_ONLY"
        else:
            status = "OK"
        report.append({
            "name": name, "status": status, "calls": h["calls"], "errors": h["errors"],
            "error_rate": round(err_rate, 3), "empty_rate": round(empty_rate, 3),
            "last_error": h["last_error"],
            "avg_latency_s": round(h["total_latency"] / h["calls"], 2),
        })

    report.sort(key=lambda r: _sev.get(r["status"], 9))
    return report
