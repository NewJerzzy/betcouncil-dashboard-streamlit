"""
BetCouncil Fetchers — extracted data-fetch and utility functions.
Moved from app.py to keep app.py under 1 MB.
All functions callable from app.py via: from fetchers import *
"""
import os, time, pickle, json, re, csv, io, hashlib
try:
    from curl_cffi import requests as cf
except ImportError:
    cf = None
from datetime import date, datetime, timedelta
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as _Retry

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
        ODDS_API_BOOKS_GAMES,
        PARLAYSAVANT_MLB_PROP_MAP,
        PARLAY_API_BASE,
        PARLAY_API_KEY,
        PINNACLE_LINES_PATH,
        POLYMARKET_PATH,
        ROLLING_DEFENSE_CACHE_HOURS,
        SCRAPERAPI_KEY,
        API_BUDGETS, GIST_API, SCRAPEDO_KEY,
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

def fetch_kalshi_markets(sport="NBA"):
    """
    Fetch Kalshi prediction market probabilities for sports events.
    Kalshi = regulated prediction market, institutional money.
    
    Implied probability divergence from model = real edge signal.
    High volume Kalshi market + model disagreement = actionable.
    
    Uses ScrapeOps proxy (already integrated).
    Returns list of {event, ticker, implied_prob, volume, sport}
    """
    series = KALSHI_SPORT_SERIES.get(sport, [sport])
    results = []
    
    for series_ticker in series:
        try:
            url = f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series_ticker}&limit=50&status=open"
            # Try direct first — Kalshi is less protected than Covers
            r = _http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=10)
            if r.status_code != 200 and SCRAPERAPI_KEY:
                # Use ScraperAPI (free 1k/mo) not ScrapeOps for Kalshi
                from urllib.parse import quote as _q
                r = _http.get(
                    f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={_q(url,safe='')}",
                    timeout=15
                )
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, (dict, list)):
                continue
            markets = data.get("markets", data if isinstance(data, list) else [])
            if not isinstance(markets, list):
                continue
            for mkt in markets:
                yes_price = float(mkt.get("yes_bid", mkt.get("last_price", 50)) or 50)
                no_price  = 100 - yes_price
                volume    = int(mkt.get("volume", 0) or 0)
                if volume < 100:  # Skip illiquid markets
                    continue
                results.append({
                    "event":        mkt.get("title", mkt.get("subtitle","")),
                    "ticker":       mkt.get("ticker",""),
                    "yes_price":    yes_price,
                    "no_price":     no_price,
                    "implied_prob": round(yes_price / 100, 3),
                    "volume":       volume,
                    "sport":        sport,
                    "source":       "Kalshi",
                    "fetched_at":   datetime.now().strftime("%H:%M"),
                })
        except (requests.RequestException, ValueError, KeyError) as _ke:
            continue

    if results:
        save_json_data(KALSHI_PATH, results)
    else:
        results = load_json_data(KALSHI_PATH, [])
    return results

def fetch_polymarket_markets(sport="NBA"):
    """
    Fetch Polymarket prediction market probabilities.
    Polymarket = decentralized, high liquidity, sophisticated traders.
    
    Returns list of {question, implied_prob, volume, sport}
    """
    sport_tags = {
        "NBA": "nba", "MLB": "mlb", "NFL": "nfl",
        "NHL": "nhl", "WNBA": "wnba",
    }
    tag = sport_tags.get(sport, sport.lower())
    
    try:
        url = f"https://gamma-api.polymarket.com/markets?active=true&tag={tag}&limit=50&order=volume&ascending=false"
        r = _http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=10)
        if r.status_code != 200:
            url2 = f"https://gamma-api.polymarket.com/markets?active=true&limit=50&tag=sports"
            r = _http.get(url2, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return load_json_data(POLYMARKET_PATH, [])
        
        markets = r.json()
        if isinstance(markets, dict):
            markets = markets.get("markets", markets.get("data", []))
        
        results = []
        for mkt in markets:
            # Filter for relevant sport
            tags_list = [t.lower() for t in mkt.get("tags", [])]
            if tag not in tags_list and "sports" not in tags_list:
                continue
            
            best_ask   = float(mkt.get("bestAsk", mkt.get("outcomePrices","0.5").split(",")[0].strip('" ') if "," in str(mkt.get("outcomePrices","")) else 0.5) or 0.5)
            volume     = float(mkt.get("volume", mkt.get("volumeNum", 0)) or 0)
            
            if volume < 1000:
                continue
            
            results.append({
                "question":     mkt.get("question", mkt.get("title","")),
                "slug":         mkt.get("slug",""),
                "implied_prob": round(min(0.99, max(0.01, best_ask)), 3),
                "volume":       int(volume),
                "sport":        sport,
                "source":       "Polymarket",
                "fetched_at":   datetime.now().strftime("%H:%M"),
            })
        
        results.sort(key=lambda x: -x["volume"])
        if results:
            save_json_data(POLYMARKET_PATH, results)
        return results
    except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as _pe:
        return load_json_data(POLYMARKET_PATH, [])

def fetch_covers_consensus(sport="MLB"):
    """
    Fetch Covers.com public betting consensus via Firecrawl.
    Firecrawl handles JavaScript rendering and Cloudflare bypassing.
    
    Returns list of {matchup, public_pct, side, picks, sport}
    Confirmed working: returns structured JSON with all consensus data.
    
    Requires FIRECRAWL_KEY in Streamlit secrets.
    Free tier: 500 credits/month (each scrape = 1 credit)
    """
    FIRECRAWL_KEY = st.secrets.get("FIRECRAWL_KEY", "fc-296afd1583694440938141e0bc113a38")
    if not FIRECRAWL_KEY:
        return load_json_data(COVERS_PATH, [])

    try:
        # Firecrawl interact endpoint — handles JS rendering
        url = "https://api.firecrawl.dev/v1/scrape"
        payload = {
            "url": "https://contests.covers.com/consensus",
            "formats": ["extract"],
            "extract": {
                "prompt": (
                    "Extract all rows from the consensus table. "
                    "For each row return: matchup (team names), "
                    "consensus_percentage (favorite team and %), "
                    "sides_odds (ML odds), pick_counts (number of picks per team). "
                    "Return as JSON array."
                )
            },
            "waitFor": 3000,
            "actions": [{"type": "wait", "milliseconds": 2000}],
        }
        headers = {
            "Authorization": f"Bearer {FIRECRAWL_KEY}",
            "Content-Type": "application/json",
        }
        r = _http.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code != 200:
            return load_json_data(COVERS_PATH, [])

        data = r.json()
        raw = data.get("data", {})
        if isinstance(raw, dict):
            raw = raw.get("extract", raw.get("content", []))
        if isinstance(raw, str):
            import json as _json
            try:
                raw = _json.loads(raw)
            except (requests.RequestException, ValueError, KeyError):
                return load_json_data(COVERS_PATH, [])

        if not isinstance(raw, list):
            return load_json_data(COVERS_PATH, [])

        # Normalize Firecrawl response to BetCouncil schema
        results = []
        SPORT_KEYWORDS = {
            "MLB": ["royals","reds","padres","phillies","dodgers","yankees","mets","braves",
                    "cubs","sox","giants","brewers","cardinals","pirates","astros","rangers",
                    "mariners","angels","twins","tigers","guardians","orioles","rays","jays",
                    "nationals","marlins","athletics","rockies","diamondbacks"],
            "NHL": ["knights","hurricanes","bruins","maple leafs","rangers","oilers",
                    "avalanche","lightning","panthers","stars","jets","predators","blues",
                    "canucks","flames","wild","ducks","kings","sharks","sabres","senators",
                    "canadiens","flyers","penguins","capitals","devils","islanders","blackhawks","red wings","blue jackets","coyotes","kraken"],
            "NBA": ["lakers","celtics","warriors","bucks","heat","bulls","knicks","nets",
                    "76ers","suns","clippers","nuggets","jazz","spurs","pistons","pacers"],
            "WNBA": ["aces","sky","storm","mercury","fever","liberty","lynx","mystics",
                     "wings","dream","sparks","sun"],
        }

        for item in raw:
            matchup = item.get("matchup","")
            if not matchup:
                continue

            # Detect sport from team names
            matchup_lower = matchup.lower()
            detected_sport = sport  # default to requested sport
            for sp, keywords in SPORT_KEYWORDS.items():
                if any(kw in matchup_lower for kw in keywords):
                    detected_sport = sp
                    break

            # Extract consensus — find the majority side
            cons_pct = item.get("consensus_percentage", {})
            odds     = item.get("sides_odds", {})
            picks    = item.get("pick_counts", {})

            if isinstance(cons_pct, dict):
                # Find favorite (highest %)
                fav_team = max(cons_pct, key=lambda k: int(str(cons_pct[k]).replace("%","") or 0), default="")
                pub_pct  = int(str(cons_pct.get(fav_team,"50")).replace("%","") or 50)
                fav_odds = odds.get(fav_team,"")
                fav_picks= int(picks.get(fav_team, 0) or 0)
                total_picks = sum(int(v or 0) for v in picks.values())
            else:
                fav_team = ""
                pub_pct  = 50
                fav_odds = ""
                fav_picks = 0
                total_picks = 0

            results.append({
                "matchup":    matchup,
                "public_pct": pub_pct,
                "side":       fav_team,
                "odds":       fav_odds,
                "picks":      fav_picks,
                "total_picks":total_picks,
                "raw_pcts":   cons_pct,
                "sport":      detected_sport,
                "source":     "Covers",
                "fetched_at": datetime.now().strftime("%H:%M"),
            })

        if results:
            save_json_data(COVERS_PATH, results)
        return results

    except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as _ce:
        return load_json_data(COVERS_PATH, [])

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


def fetch_bovada_props(sport: str = "MLB") -> list:
    """
    Fetch Bovada player props using Playwright WebSocket interception.

    WHY WebSocket: Bovada streams its live odds via a WebSocket connection at
    wss://ws.bovada.lv — player-prop markets are pushed through this channel
    and are NOT available on the static coupon REST endpoint used by
    fetch_bovada_lines().  A real browser session is required because Bovada's
    Cloudflare challenge fires before the WS handshake.

    HOW: Playwright's page.on("websocket", …) exposes every WS connection
    opened by the page; ws.on("framereceived", …) fires for each incoming
    text or binary frame.  We parse frames that are valid JSON and look for
    the "displayGroups" payload shape that Bovada uses for odds data.
    Any displayGroup whose description contains "PLAYER" (case-insensitive)
    is treated as a player-prop group.

    Fallback: if the WS channel delivers a top-level "events" list (same shape
    as the REST coupon endpoint), we also scan those events for player-prop
    displayGroups.  This makes the parser resilient to Bovada switching between
    REST-over-WS and live-push formats.

    Headless: defaults to headed (False) — Cloudflare passes reliably in
    headed mode.  Set env var BOVADA_HEADLESS=1 to force headless.

    Returns list of dicts in BetCouncil standard format:
      {Player, Prop, Line, Over, Under, Sport, Book, source}
    Returns [] on import error, unsupported sport, or any failure.
    """
    sport_path_map = {
        "MLB":  "baseball/mlb",
        "NBA":  "basketball/nba",
        "NHL":  "hockey/nhl",
        "WNBA": "basketball/wnba",
        "NFL":  "football/nfl",
    }
    sport_path = sport_path_map.get(sport.upper())
    if not sport_path:
        return []

    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as _PWTimeout
    except ImportError:
        log_error_to_session(
            "fetch_bovada_props",
            "playwright not installed — pip install playwright && playwright install chromium",
            "warning",
        )
        return []

    props = []
    ws_frames: list = []   # collect raw JSON payloads for later parsing

    def _on_ws(ws):
        """Attach a frame listener to every new WebSocket connection."""
        if "bovada.lv" not in ws.url and "ws.bovada" not in ws.url:
            return

        def _on_frame(payload):
            if isinstance(payload, (bytes, bytearray)):
                try:
                    payload = payload.decode("utf-8", errors="ignore")
                except Exception:
                    return
            if not isinstance(payload, str) or not payload.startswith("{"):
                return
            ws_frames.append(payload)

        ws.on("framereceived", lambda p: _on_frame(p.get("payload", p) if isinstance(p, dict) else p))

    try:
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ]
            headless = bool(os.environ.get("BOVADA_HEADLESS", ""))
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
                Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = ctx.new_page()
            page.on("websocket", _on_ws)

            target = f"https://www.bovada.lv/sports/{sport_path}"
            try:
                page.goto(target, wait_until="networkidle", timeout=60_000)
            except _PWTimeout:
                pass
            except Exception:
                pass

            # Dwell to collect push frames that arrive after initial paint
            time.sleep(6)
            ctx.close()
            browser.close()

    except Exception as _e:
        log_error_to_session("fetch_bovada_props", str(_e)[:150], "warning")
        return []

    # ── Log raw WS frame sample for shape validation ──────────────────────
    # On the first real Playwright session, write the first raw WS frame to
    # CACHE_DIR/bovada_ws_sample_{sport}.json so the operator can inspect the
    # actual message shape in the System tab.  Overwrites on each successful
    # run so the sample stays current.  Truncated to 4 KB to stay readable.
    if ws_frames:
        try:
            _sample_path = os.path.join(CACHE_DIR, f"bovada_ws_sample_{sport}.json")
            _sample_raw = ws_frames[0][:4096]
            with open(_sample_path, "w") as _sf:
                _sf.write(_sample_raw)
            log_error_to_session(
                "fetch_bovada_props",
                f"WS frame sample written ({len(ws_frames)} frames collected, "
                f"first frame {len(ws_frames[0])} chars). "
                f"Sample: {ws_frames[0][:200]}",
                "info",
            )
        except Exception:
            pass
    else:
        log_error_to_session(
            "fetch_bovada_props",
            f"0 WS frames collected for {sport} — page may have loaded without WebSocket traffic "
            f"(Cloudflare challenge still active, or sport has no live markets)",
            "warning",
        )

    # ── Parse collected WS frames ─────────────────────────────────────────
    def _parse_display_group(dg, event_competitors: list) -> list:
        """Extract player props from a single Bovada displayGroup dict."""
        desc = (dg.get("description") or "").upper()
        if "PLAYER" not in desc and "PROP" not in desc and "PARTICIPANT" not in desc:
            return []
        rows = []
        for market in (dg.get("markets") or []):
            prop_name = _clean_text(market.get("description") or "")
            for outcome in (market.get("outcomes") or []):
                odesc = outcome.get("description", "")
                price = outcome.get("price") or {}
                american = str(price.get("american") or price.get("handicap") or "—")
                # Player name: prefer explicit participant list, else first competitor
                participants = (
                    outcome.get("participants")
                    or outcome.get("competitors")
                    or event_competitors
                    or []
                )
                player_name = ""
                if participants:
                    player_name = _clean_text(
                        participants[0].get("name") or participants[0].get("description") or ""
                    )
                if not player_name:
                    player_name = _clean_text(odesc)

                # Line: pointSpread or handicap field
                line_raw = (
                    outcome.get("pointSpread")
                    or outcome.get("handicap")
                    or market.get("line")
                    or market.get("point")
                )
                try:
                    line = float(str(line_raw).replace("+", "")) if line_raw is not None else None
                except (ValueError, TypeError):
                    line = None

                if not player_name or line is None:
                    continue

                side = odesc.upper()
                rows.append({
                    "Player": player_name,
                    "Prop":   prop_name,
                    "Line":   line,
                    "Over":   american if "OVER" in side else "—",
                    "Under":  american if "UNDER" in side else "—",
                    "Sport":  sport.upper(),
                    "Book":   "Bovada",
                    "source": "bovada_ws",
                })
        return rows

    def _clean_text(s):
        import re as _re
        return _re.sub(r"\s+", " ", (s or "")).strip()

    seen_keys: set = set()
    for raw in ws_frames:
        try:
            msg = json.loads(raw)
        except Exception:
            continue

        # Shape A: top-level dict with "displayGroups" (single event push)
        if "displayGroups" in msg:
            competitors = msg.get("competitors") or msg.get("teams") or []
            for dg in msg["displayGroups"]:
                for row in _parse_display_group(dg, competitors):
                    key = (row["Player"], row["Prop"], row["Line"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        props.append(row)

        # Shape B: list of events under "events" key (bulk REST-over-WS push)
        for event in (msg.get("events") or []):
            competitors = event.get("competitors") or []
            for dg in (event.get("displayGroups") or []):
                for row in _parse_display_group(dg, competitors):
                    key = (row["Player"], row["Prop"], row["Line"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        props.append(row)

        # Shape C: nested under arbitrary wrapper key
        for val in msg.values():
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and "displayGroups" in item:
                        competitors = item.get("competitors") or []
                        for dg in item["displayGroups"]:
                            for row in _parse_display_group(dg, competitors):
                                key = (row["Player"], row["Prop"], row["Line"])
                                if key not in seen_keys:
                                    seen_keys.add(key)
                                    props.append(row)

        # Shape D: recursive DFS — catches any nesting depth Bovada may use.
        # Only runs when shapes A/B/C found nothing in THIS frame to avoid
        # double-counting rows already extracted by the faster paths above.
        _before = len(props)
        if len(props) == _before:
            def _walk(obj, parent_comps=None):
                if isinstance(obj, dict):
                    if "displayGroups" in obj and obj not in (msg,):
                        comps = (obj.get("competitors") or obj.get("teams")
                                 or parent_comps or [])
                        for dg in obj["displayGroups"]:
                            for row in _parse_display_group(dg, comps):
                                key = (row["Player"], row["Prop"], row["Line"])
                                if key not in seen_keys:
                                    seen_keys.add(key)
                                    props.append(row)
                    for v in obj.values():
                        _walk(v, obj.get("competitors") or obj.get("teams") or parent_comps)
                elif isinstance(obj, list):
                    for item in obj:
                        _walk(item, parent_comps)
            _walk(msg)

    return props


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
            log_error_to_session("fetch_auto_scraped_props", f"Gist stale (date: {gist_date}, today: {date.today().isoformat()})", "warning")
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


def fetch_ev_heatmap(sport="mlb", method="worst"):
    """
    Fetch the EVSharps Cheat Sheet heatmap data (static .json.gz files).
    Returns { "record": {book: {prop-vs-book: {All/L3/L7/L14/L30: {wins,losses,roi,profit,kelly}}}},
              "xy": {prop: [...]} }

    sport:  "mlb" | "wnba" | "nba" | "nhl" | "nfl"
    method: "worst" (Worst Line devig) | "probit" (Probit devig)
    Both mlb_worst and mlb_probit confirmed accessible.
    """
    import gzip as _gzip
    url = f"https://www.evsharps.com/heatmaps/{sport.lower()}_{method}.json.gz"
    try:
        r = _http.get(url, timeout=20, headers={
            "Referer": "https://www.evsharps.com/cheat?sport=" + sport.lower(),
            "Accept-Encoding": "gzip, deflate",
        })
        if r.status_code == 200:
            try:
                return json.loads(_gzip.decompress(r.content))
            except Exception:
                return r.json()
        return {}
    except requests.exceptions.Timeout:
        return {}
    except Exception:
        return {}


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
        st.warning(
            "🔒 FanDuel PerimeterX token missing or expired — FanDuel props blocked. "
            "Run the Playwright session harvester, or set FANDUEL_PX_CONTEXT in secrets."
        )
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
        st.warning(
            "🔒 FanDuel PerimeterX token missing or expired — FanDuel props blocked. "
            "Run the Playwright session harvester, or set FANDUEL_PX_CONTEXT in secrets."
        )
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
    existing = load_json_data(PINNACLE_LINES_PATH, [])
    existing.append(record)
    save_json_data(PINNACLE_LINES_PATH, existing)
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

def fetch_weather_for_game(city, is_outdoor=True):
    if not is_outdoor:
        return None
    cache_key = hashlib.md5(f"weather_{city}_{date.today()}".encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}_weather.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 3:
            return _safe_load_pkl(cache_path)
    weather = None
    # Tier 1: wttr.in
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

def increment_api_counter(counter_path):
    counter = get_api_counter(counter_path)
    counter["count"] += 1
    counter["monthly_count"] = counter.get("monthly_count", 0) + 1
    save_json_data(counter_path, counter)  # local fallback, kept for same-session reads
    data_type = os.path.basename(counter_path).replace(".json", "")
    save_to_gist(data_type, counter)  # the persistence that actually survives redeploys
    # Refresh session cache with updated count
    st.session_state[f"_api_counter_{counter_path}"] = counter
    return counter

# ── Gist batch-write constants (mirrors app.py module-level globals) ────────
_GIST_BATCH_WINDOW   = 5.0   # seconds — flush after this many seconds of queued writes
_GIST_CRITICAL_KEYS  = frozenset({"history", "bankroll", "signal_performance", "injury_performance"})


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
            return None
        data = resp.json()
        with open(cache_path, "wb") as f:
            pickle.dump(data, f)
        return data
    except Exception as e:
        st.session_state.setdefault("errors", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": f"espn_get:{cache_key}", "error": str(e)[:80]
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

def api_budget_increment(budget_key):
    budget = API_BUDGETS.get(budget_key)
    if budget:
        increment_api_counter(budget["counter_path"])

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
            # 403/429 = quota exhausted — flag and skip for rest of session
            if r.status_code in (403, 429, 402):
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
        url = f"https://stats.nba.com/stats/teamgamelogs?Season=2025-26&SeasonType={season_type}&TeamID=&LastNGames={n_games}&MeasureType=Defense&PerMode=PerGame"
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

def fetch_alternate_lines(sport, matchup):
    if not ODDSWRAP_AVAILABLE:
        return {}
    sport_key = ODDSWRAP_SPORT_MAP.get(sport)
    if not sport_key:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"alt_lines_{sport}_{hashlib.md5(matchup.encode()).hexdigest()[:8]}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 2:
            return _safe_load_pkl(cache_path)
    alternates = {"spreads": [], "totals": [], "source": "OddsWrap"}
    try:
        client = OddsClient(books=["draftkings", "bovada"])
        games = client.get_all(sport_key)
        for game in games:
            game_name = f"{game.away_team} @ {game.home_team}"
            if game.away_team.upper() in matchup.upper() or game.home_team.upper() in matchup.upper():
                for line in game.lines:
                    if hasattr(line, "alt_spreads"):
                        for alt in line.alt_spreads:
                            alternates["spreads"].append({"spread": alt.spread, "odds": alt.odds, "book": line.book})
                    if hasattr(line, "alt_totals"):
                        for alt in line.alt_totals:
                            alternates["totals"].append({"total": alt.total, "side": alt.side, "odds": alt.odds, "book": line.book})
                break
        if alternates["spreads"] or alternates["totals"]:
            with open(cache_path, "wb") as f:
                pickle.dump(alternates, f)
    except (IOError, ValueError) as e:
        pass
    return alternates

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
    urls = [
        "https://stats.wnba.com/stats/playergamelogs?Season=2025&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
        "https://stats.wnba.com/stats/playergamelogs?Season=2024&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=10",
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

def fetch_wnba_player_season_avg(player_name):
    """
    Fetch 2025 WNBA season averages for any player via stats.wnba.com.
    Returns stat dict or None. Cached 6h.
    """
    cache_path = os.path.join(CACHE_DIR, f"wnba_season_{normalize_name(player_name)}.pkl")
    cached = _load_cache(cache_path, 6)
    if cached:
        return cached
    try:
        # stats.wnba.com player search
        url = ("https://stats.wnba.com/stats/playergamelogs"
               "?Season=2025&SeasonType=Regular+Season&PlayerOrTeam=P&LastNGames=0")
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Referer": "https://www.wnba.com/",
            "Origin": "https://www.wnba.com/",
            "x-nba-stats-origin": "stats",
            "x-nba-stats-token": "true",
        }
        r = _http.get(url, headers=hdrs, timeout=12)
        if r.status_code != 200:
            return None
        rs = r.json().get("resultSets", [{}])[0]
        col = {h: i for i, h in enumerate(rs.get("headers", []))}
        rows = rs.get("rowSet", [])
        norm = normalize_name(player_name)
        player_rows = [row for row in rows
                       if normalize_name(str(row[col.get("PLAYER_NAME", 0)])) == norm]
        if not player_rows:
            return None
        # Aggregate all games
        pts_vals = [float(r[col["PTS"]]) for r in player_rows if col.get("PTS") and r[col["PTS"]] is not None]
        reb_vals = [float(r[col["REB"]]) for r in player_rows if col.get("REB") and r[col["REB"]] is not None]
        ast_vals = [float(r[col["AST"]]) for r in player_rows if col.get("AST") and r[col["AST"]] is not None]
        if not pts_vals:
            return None
        pts = round(sum(pts_vals) / len(pts_vals), 1)
        reb = round(sum(reb_vals) / len(reb_vals), 1) if reb_vals else 0.0
        ast = round(sum(ast_vals) / len(ast_vals), 1) if ast_vals else 0.0
        result = {
            "PTS": pts, "REB": reb, "AST": ast,
            "PRA": round(pts + reb + ast, 1),
            "n_games": len(pts_vals),
            "PTS_std": round(compute_std_dev(pts_vals, "WNBA") or pts * 0.35, 2),
            "REB_std": round(compute_std_dev(reb_vals, "WNBA") or reb * 0.40, 2),
            "AST_std": round(compute_std_dev(ast_vals, "WNBA") or ast * 0.45, 2),
        }
        _save_cache(cache_path, result)
        return result
    except Exception as e:
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
            url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active&season=2025"
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

def fetch_nhl_rolling_averages():
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
        url = f"https://stats.nba.com/stats/leaguedashteamstats?Season=2025-26&SeasonType={season_type}&MeasureType=Defense&PerMode=PerGame"
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

def fetch_parlaysavant_props(sport="mlb", position="batter", prop="hits"):
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

def fetch_soccer_player_stats(player_name):
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
            f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_key}/athletes/{pid}/stats",
            f"soccer_{league_key}_{pid}_stats", ttl_hours=6
        )
        if not stats_data:
            continue

        stat_map = {}
        for cat in stats_data.get("categories", []):
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
        stats_url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes/{athlete_id}/stats"
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

        # Parse stat categories
        for cat in data.get("stats", []):
            cat_name = cat.get("name", "").lower()
            for stat in cat.get("stats", []):
                sname = stat.get("name", "").lower().replace(" ", "_")
                sval  = stat.get("value")
                if sval is None: continue
                if "passing" in cat_name:
                    if "yard" in sname: result["passing_yards"] = float(sval)
                    if "touchdown" in sname: result["passing_touchdowns"] = float(sval)
                    if "attempt" in sname: result["pass_attempts"] = float(sval)
                    if "completion" in sname: result["completions"] = float(sval)
                elif "rushing" in cat_name:
                    if "yard" in sname: result["rushing_yards"] = float(sval)
                    if "touchdown" in sname: result["rushing_touchdowns"] = float(sval)
                elif "receiving" in cat_name:
                    if "yard" in sname: result["receiving_yards"] = float(sval)
                    if "reception" in sname or "catch" in sname: result["receptions"] = float(sval)
                    if "target" in sname: result["targets"] = float(sval)
                    if "touchdown" in sname: result["receiving_touchdowns"] = float(sval)
                if "game" in sname and "played" in sname:
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


def fetch_wnba_player_stats(player_name):
    """
    Fetch WNBA player 2025 season stats from ESPN.
    Fallback for players not in stats.wnba.com rolling avg cache.
    Cached 6h.
    """
    cache_key = f"wnba_player_{normalize_name(player_name)}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            try:
                return _safe_load_pkl(cache_path)
            except Exception:
                pass

    roster_data = _espn_get(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/athletes?limit=300&active=true",
        "wnba_roster_espn", ttl_hours=24
    )
    if not roster_data:
        return None
    norm = normalize_name(player_name)
    match = next((a for a in roster_data.get("athletes", [])
                  if normalize_name(a.get("displayName", "")) == norm), None)
    if not match:
        return None
    pid = match.get("id")
    if not pid:
        return None

    stats_data = _espn_get(
        f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/athletes/{pid}/stats?season=2025",
        f"wnba_{pid}_stats_2025", ttl_hours=6
    )
    if not stats_data:
        return None

    stat_map = {}
    for cat in stats_data.get("categories", []):
        for s in cat.get("stats", []):
            stat_map[s.get("name", "")] = s.get("value", 0)

    if not stat_map:
        return None

    pts = round(float(stat_map.get("points", stat_map.get("avgPoints", 0))), 1)
    reb = round(float(stat_map.get("rebounds", stat_map.get("avgRebounds", 0))), 1)
    ast = round(float(stat_map.get("assists", stat_map.get("avgAssists", 0))), 1)
    stl = round(float(stat_map.get("steals", 0)), 1)
    blk = round(float(stat_map.get("blocks", 0)), 1)
    games = max(1, int(stat_map.get("gamesPlayed", 20)))

    result = {
        "PTS": pts, "REB": reb, "AST": ast,
        "STL": stl, "BLK": blk,
        "PRA": round(pts + reb + ast, 1),
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
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

def fetch_player_season_avg_bdl(player_name, sport="NBA", season=2025):
    """
    Fetch season averages for a specific player by name search.
    Used when player isn't in BDL_PLAYER_IDS (e.g. playoff callups).
    """
    if not BDL_API_KEY:
        return None
    cache_key = f"bdl_avg_{normalize_name(player_name)}_{season}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            return _safe_load_pkl(cache_path)
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
        result = {
            "PTS": pts, "REB": reb, "AST": ast,
            "PRA": round(pts + reb + ast, 1),
            "3PM": round(float(a.get("fg3m", 0)), 1),
            "STL": round(float(a.get("stl", 0)), 1),
            "BLK": round(float(a.get("blk", 0)), 1),
            "TO": round(float(a.get("turnover", 0)), 1),
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
    url = f"https://api.balldontlie.io/v1/season_averages?season=2025&{params}"
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
                "source": "Underdog"
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
                                        "Sport": sport, "source": "Underdog"})
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
        if not GITHUB_TOKEN or not GITHUB_GIST_ID:
            return ""
        try:
            _gr = _http.get(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                },
                timeout=8,
            )
            if _gr.status_code != 200:
                return ""
            _gf = _gr.json().get("files", {}).get("betcouncil_device_fingerprint.json", {})
            _gc = _gf.get("content", "")
            return json.loads(_gc).get("device_id", "") if _gc else ""
        except Exception:
            return ""

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
                if not _cffi_success and SCRAPEOPS_KEY:
                    try:
                        from urllib.parse import quote as _q
                        _so_url = (
                            f"https://proxy.scrapeops.io/v1/?api_key={SCRAPEOPS_KEY}"
                            f"&url={_q(url, safe='')}&residential=true"
                        )
                        resp = _http.get(_so_url, headers=pp_headers, timeout=20)
                        if resp.status_code == 200:
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

def fetch_injury_news(sport):
    """
    Consolidated injury feed — Tier 1 source.
    Wraps fetch_underdog_injuries (ESPN-backed) as primary.
    Returns dict of {player_name: status_string}.
    """
    return fetch_underdog_injuries(sport) or {}

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
        # Direct request — RotoWire blocks proxies too, so no point routing through proxy
        r = _http.get(url, headers=headers, timeout=10)
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
        if age_mins < 20:
            return _safe_load_pkl(cache_path)
    today = date.today().strftime("%Y%m%d")
    url = f"{ACTION_NETWORK_BASE}/{sport_slug}?bookIds={ACTION_NETWORK_BOOK_IDS}&date={today}&periods=event"
    an_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.actionnetwork.com",
        "Referer": "https://www.actionnetwork.com/",
    }
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
            book_15 = odds_data.get("15", {})
            event_data = book_15.get("event", {})
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
        if public_betting:
            with open(cache_path, "wb") as f:
                pickle.dump(public_betting, f)
        return public_betting
    except (KeyError, TypeError, ValueError) as e:
        return {}

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
    TEAM_ABBREV_TO_FRAGMENT = {
        # MLB
        "ARI":"Arizona","ATL":"Atlanta Braves","BAL":"Baltimore",
        "BOS":"Boston Red","CHC":"Chicago Cubs","CWS":"Chicago White",
        "CIN":"Cincinnati","CLE":"Cleveland","COL":"Colorado",
        "DET":"Detroit","HOU":"Houston Astros","KC":"Kansas City",
        "LAA":"Los Angeles Angels","LAD":"Los Angeles Dodgers",
        "MIA":"Miami","MIL":"Milwaukee","MIN":"Minnesota",
        "NYM":"New York Mets","NYY":"New York Yankees",
        "OAK":"Oakland","ATH":"Athletics",
        "PHI":"Philadelphia","PIT":"Pittsburgh",
        "SD":"San Diego","SEA":"Seattle","SF":"San Francisco",
        "STL":"St. Louis","TB":"Tampa Bay","TEX":"Texas",
        "TOR":"Toronto","WSH":"Washington Nationals",
        # NBA
        "GSW":"Golden State","LAL":"Los Angeles Lakers",
        "LAC":"Los Angeles","NYK":"New York Knicks",
        "NOP":"New Orleans","SAS":"San Antonio",
        "OKC":"Oklahoma","UTA":"Utah","MEM":"Memphis",
        # NFL — KC and LAC keys already defined above; omitting duplicates
        # to prevent the NFL entry silently overwriting the MLB/NBA fragment.
        # "Kansas City" (MLB KC key) matches both Royals and Chiefs.
        # "Los Angeles" (NBA LAC key) matches both Clippers and Chargers.
        "NE":"New England","NO":"New Orleans Saints",
        "GB":"Green Bay",
        "LAR":"Los Angeles Rams",
        "NYG":"New York Giants","NYJ":"New York Jets",
        "SF":"San Francisco 49ers","TB":"Tampa Bay Buccaneers",
        # NHL
        "TBL":"Tampa Bay Lightning","TOR":"Toronto",
        "WSH":"Washington Capitals","NJD":"New Jersey",
        "LAK":"Los Angeles Kings","SJS":"San Jose",
        "CBJ":"Columbus","VGK":"Vegas Golden",
    }

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

    if not today_games:
        return [], playoff, home_teams, away_teams
    return today_games, playoff, home_teams, away_teams

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
        if age_mins < 30:
            return _safe_load_pkl(cache_path)
    try:
        url = (f"{ODDS_API_BASE}/sports/{sport_key}/odds"
               f"?apiKey={ODDS_API_KEY}&regions=us,us2"
               f"&markets=alternate_spreads"
               f"&oddsFormat=american"
               f"&bookmakers=draftkings,fanduel,betmgm")
        resp = _http.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API")
        if resp.status_code != 200:
            return {}
        events = resp.json()
        alt_data = {}
        for event in events:
            home = event.get("home_team","")
            away = event.get("away_team","")
            matchup = f"{away} @ {home}"
            lines = []
            for bm in event.get("bookmakers",[])[:2]:
                for mkt in bm.get("markets",[]):
                    if mkt.get("key") != "alternate_spreads":
                        continue
                    outcomes = mkt.get("outcomes",[])
                    # Group by point spread
                    for o in outcomes:
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
        if alt_data:
            with open(cache_path, "wb") as f:
                pickle.dump(alt_data, f)
        return alt_data
    except (requests.RequestException, ValueError, KeyError):
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
        if age_mins < 20:
            return _safe_load_pkl(cache_path)
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds?apiKey={ODDS_API_KEY}&regions=us,us2&markets=h2h,spreads,totals&oddsFormat=american&bookmakers={ODDS_API_BOOKS_GAMES}"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API")
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
    except (IOError, ValueError) as e:
        print(f"[ODDS_API] game lines fetch exception for {sport}: {e}")
        return [], {}, {}

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
        client = OddsClient(books=["draftkings", "bovada", "betrivers"])
        seen = set()
        for book in ["draftkings", "bovada"]:
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

def fetch_oddswrap_lines(sport):
    if not ODDSWRAP_AVAILABLE:
        return []
    sport_key = ODDSWRAP_SPORT_MAP.get(sport)
    if not sport_key:
        return []
    cache_path = os.path.join(CACHE_DIR, f"oddswrap_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 2:
            return _safe_load_pkl(cache_path)
    lines_data = []
    try:
        client = OddsClient(books=["draftkings", "fanduel", "bovada", "betrivers", "betmgm", "caesars"])
        games = client.get_all(sport_key)
        for game in games:
            game_dict = {"Matchup": f"{game.away_team} @ {game.home_team}", "Sport": sport, "Live": game.live}
            for line in game.lines:
                book = line.book.title()
                if line.total:
                    game_dict[f"{book}_Total"] = line.total
                if line.home_spread:
                    game_dict[f"{book}_Spread"] = line.home_spread
                if line.home_odds:
                    game_dict[f"{book}_HomeML"] = line.home_odds
            best_home = game.best_home_odds()
            best_away = game.best_away_odds()
            if best_home:
                game_dict["BestHomeML"] = best_home.home_odds
                game_dict["BestHomeBook"] = best_home.book
            if best_away:
                game_dict["BestAwayML"] = best_away.away_odds
                game_dict["BestAwayBook"] = best_away.book
            lines_data.append(game_dict)
        if lines_data:
            with open(cache_path, "wb") as f:
                pickle.dump(lines_data, f)
    except (IOError, ValueError) as e:
        pass
    return lines_data

def fetch_action_network_props(sport: str) -> dict:
    """
    Fetch Action Network public betting percentages.
    Returns {matchup: {home_pct, away_pct, over_pct, under_pct, tickets, money}}
    Cached 20 min. Free — no API key needed.
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
        print(f"[WARN] fetch_action_network_props: {e}")
        return {}


def fetch_oddspapi_props(sport: str) -> list:
    """
    Fetch player props via OddsPAPI — aggregates DraftKings, FanDuel, BetMGM etc.
    Key: ODDSPAPI_KEY in Streamlit secrets.
    Returns list of {Player, Prop, Line, OverOdds, UnderOdds, Book, Sport, source}
    Cached 30 min.
    """
    if not ODDSPAPI_KEY:
        return []
    sport_map = {
        "MLB": "baseball_mlb", "NBA": "basketball_nba",
        "NFL": "americanfootball_nfl", "NHL": "icehockey_nhl",
        "WNBA": "basketball_wnba",
    }
    sport_key = sport_map.get(sport)
    if not sport_key:
        return []
    cache_path = os.path.join(CACHE_DIR, f"oddspapi_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        r = _http.get(
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/events",
            params={"apiKey": ODDSPAPI_KEY, "dateFormat": "iso"},
            timeout=12,
        )
        if r.status_code != 200:
            print(f"[WARN] fetch_oddspapi_props events: HTTP {r.status_code}")
            return []
        events = r.json()[:10]  # limit to 10 games to save credits
        props = []
        prop_markets = {
            "MLB": ["batter_hits", "batter_total_bases", "batter_rbis",
                    "batter_home_runs", "pitcher_strikeouts", "pitcher_outs"],
            "NBA": ["player_points", "player_rebounds", "player_assists",
                    "player_threes", "player_points_rebounds_assists"],
            "NFL": ["player_pass_yds", "player_rush_yds", "player_reception_yds",
                    "player_receptions", "player_touchdowns"],
            "NHL": ["player_shots_on_goal", "player_points", "player_goals"],
            "WNBA": ["player_points", "player_rebounds", "player_assists"],
        }.get(sport, [])
        if not prop_markets:
            return []
        for event in events[:5]:  # max 5 events
            eid = event.get("id", "")
            if not eid: continue
            for market in prop_markets[:3]:  # max 3 markets per event
                try:
                    mr = _http.get(
                        f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{eid}/odds",
                        params={
                            "apiKey": ODDSPAPI_KEY,
                            "markets": market,
                            "oddsFormat": "american",
                            "bookmakers": "draftkings,fanduel,betmgm",
                        },
                        timeout=10,
                    )
                    if mr.status_code != 200: continue
                    event_data = mr.json()
                    for bm in event_data.get("bookmakers", [])[:2]:
                        book = bm.get("key", "")
                        for mkt in bm.get("markets", []):
                            for outcome in mkt.get("outcomes", []):
                                player = outcome.get("description", "")
                                line   = outcome.get("point")
                                price  = outcome.get("price")
                                name   = outcome.get("name", "")
                                if not player or line is None: continue
                                if name.lower() == "over":
                                    props.append({
                                        "Player": player,
                                        "Prop": market.replace("_", " ").title(),
                                        "Line": float(line),
                                        "OverOdds": str(int(price)) if price else "N/A",
                                        "UnderOdds": "N/A",
                                        "Book": book,
                                        "Sport": sport,
                                        "source": "oddspapi",
                                    })
                    time.sleep(0.2)
                except Exception:
                    continue
        if props:
            _safe_save_pkl(cache_path, props)
        return props
    except Exception as e:
        print(f"[WARN] fetch_oddspapi_props: {e}")
        return []

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

def fetch_espn_predictor(sport, event_id):
    if not event_id:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"predictor_{event_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 3:
            return _safe_load_pkl(cache_path)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return {}
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/events/{event_id}/competitions/{event_id}/predictor"
    try:
        resp = _http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        home = data.get("homeTeam", {})
        away = data.get("awayTeam", {})
        predictor = {"home_win_pct": home.get("statistics", [{}])[0].get("value") if home.get("statistics") else None, "away_win_pct": away.get("statistics", [{}])[0].get("value") if away.get("statistics") else None, "home_projected_score": home.get("statistics", [{}, {}])[1].get("value") if home.get("statistics") and len(home.get("statistics", [])) > 1 else None, "away_projected_score": away.get("statistics", [{}, {}])[1].get("value") if away.get("statistics") and len(away.get("statistics", [])) > 1 else None}
        with open(cache_path, "wb") as f:
            pickle.dump(predictor, f)
        return predictor
    except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
        return {}

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

def fetch_player_game_logs(player_name, season=2025, last_n=15):
    """
    Fetch last N game logs for a player.
    Returns list of game dicts with pts, reb, ast, min, opponent, date, home/away.
    """
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

def fetch_dk_nba_draftgroup_id():
    """Find today's NBA classic draftGroupId from DraftKings."""
    cache_path = os.path.join(CACHE_DIR, "dk_draftgroup_nba.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 120:
            return _safe_load_pkl(cache_path)
    try:
        r = _http.get(
            "https://www.draftkings.com/lobby/getcontests?sport=NBA",
            headers={**HEADERS, "Referer": "https://www.draftkings.com/"},
            timeout=10
        )
        if r.status_code != 200:
            return None
        contests = r.json().get("Contests", [])
        # Find Classic contest (contestTypeId=21 or name contains Classic)
        for c in contests:
            name = c.get("n", "").lower()
            if "classic" in name and c.get("dg"):
                dgid = c["dg"]
                with open(cache_path, "wb") as f:
                    pickle.dump(dgid, f)
                return dgid
        # Fallback: first contest with a draftGroupId
        for c in contests:
            if c.get("dg"):
                dgid = c["dg"]
                with open(cache_path, "wb") as f:
                    pickle.dump(dgid, f)
                return dgid
    except (IOError, ValueError) as e:
        pass
    return None

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

def fetch_mlb_confirmed_lineups_with_fallback():
    """
    Same contract as fetch_mlb_confirmed_lineups(), but fills in any team
    statsapi.mlb.com didn't return (rate-limited / "Max retries exceeded" /
    down — the known failure mode against statsapi) using Sleeper's live
    scoreboard API as a second, independent source. statsapi stays primary
    since it's the longer-trusted source; Sleeper only fills gaps.

    Confirmed via real DevTools capture 2026-06-21 (api.sleeper.app, no
    auth). Note: Sleeper's lineup array mixes starting 9 with in-game
    substitutions appended later — fetch_sleeper_mlb_scoreboard() already
    filters to batting_order 0-9 + inning==0 to keep only starters.
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
                    _lm = _re.search(r"([\d.]+)", label)
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
                                                    _lm2 = _re.search(r"([\d.]+)", o_label)
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


def fetch_nfl_injuries() -> list:
    """
    Fetch current NFL injury report from ESPN's public injuries endpoint.

    Endpoint: https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries
    Public, no authentication required, no rate limits documented.

    Response shape (per team entry):
      {
        "team": {"displayName": "...", "abbreviation": "..."},
        "injuries": [
          {
            "athlete": {"fullName": "...", "position": {"abbreviation": "..."}},
            "status": "Questionable",
            "shortComment": "Ankle",
            "longComment": "..."
          }
        ]
      }

    Returns list of dicts:
      {Player, Team, TeamAbbr, Position, Status, Comment, Sport, source}
    Returns [] on any failure (no warnings raised — injuries are supplemental data).
    """
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
    try:
        r = _http.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        injuries = []
        for team_entry in (data.get("injuries") or []):
            team_info  = team_entry.get("team") or {}
            team_name  = team_info.get("displayName") or team_info.get("name") or ""
            team_abbr  = team_info.get("abbreviation") or ""
            for inj in (team_entry.get("injuries") or []):
                athlete  = inj.get("athlete") or {}
                position = (athlete.get("position") or {}).get("abbreviation") or ""
                player   = (
                    athlete.get("fullName")
                    or athlete.get("displayName")
                    or ""
                )
                status   = inj.get("status") or ""
                comment  = inj.get("shortComment") or inj.get("longComment") or ""
                if not player:
                    continue
                injuries.append({
                    "Player":   player,
                    "Team":     team_name,
                    "TeamAbbr": team_abbr,
                    "Position": position,
                    "Status":   status,
                    "Comment":  comment,
                    "Sport":    "NFL",
                    "source":   "espn_nfl_injuries",
                })
        return injuries
    except Exception:
        return []


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
    # File is named "caesars_tokens.json"; content is the JSON-serialised dict.
    # load_from_gist("caesars_tokens", None) in app.py parses this back to a
    # dict — that's the shape fetch_caesars_direct() reads from the Gist.
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        try:
            _http.patch(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"files": {"caesars_tokens.json": {"content": json.dumps(harvested, indent=2)}}},
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




# ─────────────────────────────────────────────────────────────────────────────
# DRAFTKINGS PICK6 — player-props contest product (DK's PrizePicks equivalent)
#
# Auth: Bearer JWT + x-api-key harvested from pick6.draftkings.com via
# Playwright (harvest_pick6_tokens).  Falls back to existing sportsbook tokens
# (harvest_draftkings_tokens) since both products share api.draftkings.com.
#
# Endpoint confirmed via network inspection: api.draftkings.com/lineups/v1/
# player-groups — requires auth; 404 without Bearer header.
# ─────────────────────────────────────────────────────────────────────────────

_P6_STAT_MAP = {
    # Basketball
    "Points": "PTS", "Rebounds": "REB", "Assists": "AST",
    "Pts+Reb+Ast": "PRA", "Pts+Ast": "PA", "Pts+Reb": "PR",
    "Reb+Ast": "RA", "3-Pointers Made": "3PM", "Blocks": "BLK",
    "Steals": "STL", "Turnovers": "TO", "Minutes": "MIN",
    "Double Doubles": "DD", "Triple Doubles": "TD2",
    # Baseball
    "Hits": "H", "Runs": "R", "RBI": "RBI", "Home Runs": "HR",
    "Strikeouts": "SO", "Pitcher Strikeouts": "SO",
    "Hits Allowed": "HA", "Total Bases": "TB", "Earned Runs": "ER",
    "Walks": "BB", "Stolen Bases": "SB",
    # Hockey
    "Shots on Goal": "SOG", "Goals": "G",
    "Goals+Assists": "GA", "Saves": "SV",
    # Football
    "Passing Yards": "PYD", "Rushing Yards": "RYD",
    "Receiving Yards": "RecYD", "Receptions": "REC",
    "Touchdowns": "TD", "Passing TDs": "PTD", "Interceptions": "INT",
    "Carries": "CAR", "Targets": "TGT",
    # Combat/MMA
    "Significant Strikes": "SST", "Takedowns": "TKD",
}


def _load_dk_pick6_tokens() -> dict:
    """
    Load DK Pick6 auth tokens.
    Read order: local pick6_session_token.txt → Gist pick6_tokens.json
                → local draftkings_session_token.txt (sportsbook fallback)
                → Gist draftkings_tokens.json.
    Returns {"bearer_jwt": str, "api_key": str, ...} or {}.
    """
    # 1. Pick6-specific local cache
    p6_cache = os.path.join(CACHE_DIR, "pick6_session_token.txt")
    if os.path.exists(p6_cache):
        try:
            age_mins = (time.time() - os.path.getmtime(p6_cache)) / 60
            if age_mins < 360:
                tok_lines = open(p6_cache).read().strip().splitlines()
                if tok_lines and tok_lines[0]:
                    return {"bearer_jwt": tok_lines[0],
                            "api_key": tok_lines[1] if len(tok_lines) > 1 else ""}
        except Exception:
            pass
    # 2. Gist pick6_tokens.json
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        try:
            _gr = _http.get(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={"Authorization": f"token {GITHUB_TOKEN}",
                         "Accept": "application/vnd.github.v3+json"},
                timeout=8,
            )
            if _gr.status_code == 200:
                _gf = _gr.json().get("files", {}).get("pick6_tokens.json", {})
                if _gf.get("content"):
                    _d = json.loads(_gf["content"])
                    if _d.get("bearer_jwt"):
                        return _d
        except Exception:
            pass
    # 3. Sportsbook token fallback (same auth domain)
    sb_cache = os.path.join(CACHE_DIR, "draftkings_session_token.txt")
    if os.path.exists(sb_cache):
        try:
            age_mins = (time.time() - os.path.getmtime(sb_cache)) / 60
            if age_mins < 360:
                tok_lines = open(sb_cache).read().strip().splitlines()
                if tok_lines and tok_lines[0]:
                    return {"bearer_jwt": tok_lines[0],
                            "api_key": tok_lines[1] if len(tok_lines) > 1 else ""}
        except Exception:
            pass
    # 4. Gist draftkings_tokens.json
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        try:
            _gr = _http.get(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={"Authorization": f"token {GITHUB_TOKEN}",
                         "Accept": "application/vnd.github.v3+json"},
                timeout=8,
            )
            if _gr.status_code == 200:
                _gf = _gr.json().get("files", {}).get("draftkings_tokens.json", {})
                if _gf.get("content"):
                    _d = json.loads(_gf["content"])
                    if _d.get("bearer_jwt"):
                        return _d
        except Exception:
            pass
    return {}


def harvest_pick6_tokens(max_wait: int = 90) -> dict:
    """
    Playwright-based DraftKings Pick6 auth token harvester.

    Navigates to pick6.draftkings.com (user must be logged in to their DK
    account) and intercepts outgoing XHR to api.draftkings.com, capturing:
      - Bearer JWT
      - x-api-key
      - The actual Pick6 API endpoint URL (stored in pick6_endpoint key)

    Falls back gracefully: if pick6.draftkings.com doesn't produce tokens fast
    enough, the result of harvest_draftkings_tokens() (sportsbook tokens) will
    work equally well since both products authenticate via api.draftkings.com.

    Persists tokens to:
      1. Gist file "pick6_tokens.json"
      2. CACHE_DIR/pick6_session_token.txt  (line 1 = JWT, line 2 = api-key)

    Returns harvested dict on success, {} on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_error_to_session(
            "harvest_pick6_tokens",
            "playwright not installed — pip install playwright && playwright install chromium",
            "warning",
        )
        return {}

    harvested: dict = {}
    _stop = {"done": False}
    _endpoints: list = []

    def _on_request(request):
        if _stop["done"]:
            return
        if "api.draftkings.com" not in request.url:
            return
        try:
            req_hdrs = request.all_headers()
        except Exception:
            return
        auth = req_hdrs.get("authorization", "")
        api_key = req_hdrs.get("x-api-key", "")
        if not auth.startswith("Bearer ") or len(auth) < 60:
            return
        # Capture endpoint URL if it looks like a Pick6 API call
        if any(x in request.url for x in
               ["player-groups", "picks", "lobby", "featured", "lineup", "projection"]):
            _endpoints.append(request.url)
        harvested["bearer_jwt"]     = auth[len("Bearer "):]
        harvested["api_key"]        = api_key
        harvested["captured_at"]    = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        harvested["source_domain"]  = "pick6.draftkings.com"
        if _endpoints:
            harvested["pick6_endpoint"] = _endpoints[0]
        _stop["done"] = True

    try:
        import time as _t
        with sync_playwright() as pw:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--window-size=1280,720",
            ]
            headless = bool(os.environ.get("DRAFTKINGS_HEADLESS", ""))
            try:
                browser = pw.chromium.launch(headless=headless, args=launch_args)
            except Exception:
                browser = pw.chromium.launch(headless=True, args=launch_args)

            ctx = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
            )
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            """)
            page = ctx.new_page()
            page.on("request", _on_request)
            page.goto(
                "https://pick6.draftkings.com/",
                timeout=30000,
                wait_until="domcontentloaded",
            )
            deadline = _t.time() + max_wait
            while _t.time() < deadline and not _stop["done"]:
                _t.sleep(0.5)
            browser.close()
    except Exception as _e:
        log_error_to_session("harvest_pick6_tokens", str(_e)[:200], "warning")

    if not harvested.get("bearer_jwt"):
        log_error_to_session(
            "harvest_pick6_tokens",
            "No auth token captured from pick6.draftkings.com — ensure you are logged in "
            "to your DraftKings account in the browser session.",
            "warning",
        )
        return {}

    # Persist to Gist
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        try:
            _http.patch(
                f"https://api.github.com/gists/{GITHUB_GIST_ID}",
                headers={"Authorization": f"token {GITHUB_TOKEN}",
                         "Accept": "application/vnd.github.v3+json"},
                json={"files": {"pick6_tokens.json": {
                    "content": json.dumps(harvested, indent=2)
                }}},
                timeout=10,
            )
        except Exception:
            pass
    # Persist to local cache
    try:
        open(os.path.join(CACHE_DIR, "pick6_session_token.txt"), "w").write(
            f"{harvested['bearer_jwt']}\n{harvested.get('api_key','')}\n"
        )
    except Exception:
        pass

    return harvested


def fetch_draftkings_pick6(sport: str) -> list:
    """
    Fetch DraftKings Pick6 player props (DK's PrizePicks-style contest product).

    Authentication: Bearer JWT + x-api-key from harvest_pick6_tokens() or the
    existing harvest_draftkings_tokens() result (same auth domain).

    Endpoint: api.draftkings.com/lineups/v1/player-groups  (auth-required;
    confirmed 404 without Bearer — standard DK API gateway pattern).

    Returns list of props in BetCouncil format:
        {Player, Prop, Line, Sport, source: "DK Pick6", Book: "DK Pick6",
         Team, Opponent, StatLabel}

    Cached 20 minutes per sport.
    """
    cache_path = os.path.join(CACHE_DIR, f"dk_pick6_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 20:
            cached = _safe_load_pkl(cache_path)
            if cached:
                return cached

    # ── Load tokens ───────────────────────────────────────────────────────────
    tokens = _load_dk_pick6_tokens()
    if not tokens.get("bearer_jwt"):
        log_error_to_session(
            "fetch_draftkings_pick6",
            "No DK auth tokens — click 'Harvest Pick6 Tokens' in the Settings panel "
            "while logged in to your DraftKings account.",
            "warning",
        )
        return []

    auth_hdrs = {
        "Authorization": f"Bearer {tokens['bearer_jwt']}",
        "x-api-key":     tokens.get("api_key", ""),
        "Accept":        "application/json",
        "Content-Type":  "application/json",
        "User-Agent":    (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Origin":        "https://pick6.draftkings.com",
        "Referer":       "https://pick6.draftkings.com/",
    }

    # Sport ID map (DK internal)
    sport_ids = {
        "NBA": 4, "MLB": 2, "NFL": 1, "NHL": 5,
        "WNBA": 11, "UFC": 13, "MMA": 13,
        "PGA": 19, "Golf": 19, "Tennis": 18,
        "ATP": 18, "WTA": 18,
    }
    sport_id = sport_ids.get(sport.upper(), sport_ids.get(sport, 4))

    # ── Try endpoints in priority order ───────────────────────────────────────
    # If harvest captured the real URL, it goes first.
    saved = tokens.get("pick6_endpoint", "")
    candidates = [saved] if saved else []
    candidates += [
        # Confirmed pattern from DK network inspection (requires auth)
        f"https://api.draftkings.com/lineups/v1/player-groups?sport={sport_id}",
        f"https://api.draftkings.com/lineups/v1/player-groups?sport={sport_id}&state=NJ",
        f"https://api.draftkings.com/lineups/v1/player-groups?sportId={sport_id}",
        # Alternative paths tried during investigation
        f"https://api.draftkings.com/picks/v1/player-groups?sport={sport_id}",
        f"https://api.draftkings.com/picks/v2/player-groups?sport={sport_id}",
        # Draft group type 96 = Pick6 contest type
        f"https://api.draftkings.com/draftgroups/v1/draftgroups?sport={sport_id}&typeid=96",
        f"https://api.draftkings.com/lineups/v1/player-groups",
    ]
    candidates = list(dict.fromkeys(c for c in candidates if c))  # dedupe, preserve order

    raw_data = None
    hit_url  = ""
    for endpoint in candidates:
        try:
            resp = _http.get(endpoint, headers=auth_hdrs, timeout=14)
            if resp.status_code == 200:
                raw_data = resp.json()
                hit_url  = endpoint
                break
            elif resp.status_code in (401, 403):
                log_error_to_session(
                    "fetch_draftkings_pick6",
                    f"Pick6 auth expired (HTTP {resp.status_code}) — "
                    "re-run Harvest Pick6 Tokens.",
                    "warning",
                )
                return []
            # 404 = wrong endpoint path, try next
        except Exception:
            continue

    if not raw_data:
        log_error_to_session(
            "fetch_draftkings_pick6",
            "Pick6: all endpoint patterns failed. Tokens may be valid but endpoint "
            "URL changed — re-run Harvest Pick6 Tokens to auto-capture the live URL.",
            "warning",
        )
        return []

    # ── Parse response ─────────────────────────────────────────────────────────
    # DK API returns one of several shapes depending on which endpoint responds.
    # We normalise all known shapes to a flat list of (name, stat_label, line).
    props: list = []
    try:
        # Shape A: {"playerGroups": [{players: [{displayName, draftStatAttributes:[{label,sortValue}]}]}]}
        groups = (
            raw_data.get("playerGroups")
            or raw_data.get("draftGroups")
            or raw_data.get("data", {}).get("playerGroups")
            or raw_data.get("result", {}).get("playerGroups")
            or (raw_data if isinstance(raw_data, list) else [])
        )
        for grp in groups:
            group_sport = (grp.get("sport") or grp.get("sportName") or sport).upper()
            players = grp.get("players") or grp.get("draftables") or []
            for player in players:
                name = (
                    player.get("displayName") or player.get("name")
                    or player.get("playerName") or player.get("shortName") or ""
                ).strip()
                if not name:
                    continue
                team = player.get("teamAbbreviation") or player.get("team") or ""
                opp  = player.get("opponent") or player.get("opp") or ""

                stats = (
                    player.get("draftStatAttributes")
                    or player.get("stats")
                    or player.get("projections")
                    or []
                )
                for stat in stats:
                    label = (
                        stat.get("label") or stat.get("statName")
                        or stat.get("name") or stat.get("abbreviation") or ""
                    ).strip()
                    raw_val = (
                        stat.get("sortValue") or stat.get("value")
                        or stat.get("projection") or stat.get("line")
                    )
                    if not label or raw_val is None:
                        continue
                    try:
                        line = float(raw_val)
                    except (ValueError, TypeError):
                        continue
                    if line <= 0:
                        continue

                    prop_key = _P6_STAT_MAP.get(label, label)
                    props.append({
                        "Player":    name,
                        "Prop":      prop_key,
                        "Line":      line,
                        "Sport":     group_sport or sport,
                        "source":    "DK Pick6",
                        "Book":      "DK Pick6",
                        "Team":      team,
                        "Opponent":  opp,
                        "StatLabel": label,
                    })

        # Shape B: flat list of projections {"playerName", "statType", "line"}
        if not props and isinstance(raw_data, list):
            for item in raw_data:
                name  = item.get("playerName") or item.get("displayName") or ""
                label = item.get("statType") or item.get("stat") or item.get("label") or ""
                line_val = item.get("line") or item.get("projection") or item.get("value")
                if not name or not label or line_val is None:
                    continue
                try:
                    line = float(line_val)
                except (ValueError, TypeError):
                    continue
                if line <= 0:
                    continue
                props.append({
                    "Player":    name.strip(),
                    "Prop":      _P6_STAT_MAP.get(label, label),
                    "Line":      line,
                    "Sport":     sport,
                    "source":    "DK Pick6",
                    "Book":      "DK Pick6",
                    "Team":      item.get("team") or item.get("teamAbbreviation") or "",
                    "Opponent":  item.get("opponent") or "",
                    "StatLabel": label,
                })

    except Exception as _parse_err:
        log_error_to_session(
            "fetch_draftkings_pick6",
            f"Pick6 parse error: {_parse_err} (endpoint: {hit_url})",
            "warning",
        )

    if props:
        _safe_save_pkl(cache_path, props)
        log_error_to_session(
            "fetch_draftkings_pick6",
            f"✅ DK Pick6: {len(props)} props fetched for {sport}",
            "info",
        )
    return props


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

def fetch_betr_direct(sport):
    """Fetch Betr player props and DFS projections via GraphQL (public, no auth).

    Endpoint: https://api.fantasy.betr.app/graphql

    Each Projection in the Betr response carries:
      name/label   : human-readable stat name (e.g. "Pitching Strikeouts")
      value        : static DFS projection line
      currentValue : live-updated line (preferred when non-null)
      type         : ProjectionType enum ("REGULAR" for all live markets)
      marketId     : unique market ID.  Two formats exist:
                       - Integer string (e.g. "1032606232847459352"):
                           pure DFS market, no canonical stat type.
                       - Base64 string (e.g. "NmEyZjc4..."):
                           decodes to {eventId}:{playerId}:{STAT_TYPE}:{line}:{type}
                           e.g. "....:STRIKEOUTS:5.0:REGULAR"
                           The STAT_TYPE segment is the canonical stat type code.
      marketStatus : "OPENED" | "CLOSED" | "SUSPENDED" etc.

    Projections with a base64-encoded marketId carry an embedded statType (e.g.
    STRIKEOUTS, HITS_ALLOWED).  All OPENED projections are returned as player
    props in BetCouncil standard format; the decoded stat_type is included as an
    extra metadata field for downstream deduplication and canonical mapping.

    Over/Under odds are em-dash placeholders — Betr is a DFS platform and does
    not publish American moneyline odds on this public endpoint.

    Returns list of dicts: {Player, Prop, Line, Over, Under, Sport, Book, ...}

    Early-exit guards:
      - unsupported sport   -> silent []
      - HTTP non-200        -> st.warning + []
      - GraphQL-level error -> st.warning + []
      - network/parse error -> st.warning + []
    """
    league_map = {"NBA": "NBA", "MLB": "MLB", "NHL": "NHL", "WNBA": "WNBA", "NFL": "NFL"}
    league = league_map.get(sport)
    if not league:
        return []

    # marketId and marketStatus added so we can:
    #   (a) filter out CLOSED/SUSPENDED lines, and
    #   (b) decode the stat type from base64-encoded market IDs.
    query = """query LeagueUpcomingEvents($league: League!) {
      getUpcomingEventsV2(league: $league) {
        name sport league
        ... on TeamVersusEvent {
          teams { name players { firstName lastName position
            projections { name label value currentValue type marketId marketStatus }
          }}
        }
        ... on IndividualVersusEvent {
          players { firstName lastName position
            projections { name label value currentValue type marketId marketStatus }
          }
        }
      }
    }"""

    props = []
    try:
        import requests as _req, base64 as _b64

        def _decode_stat_type(market_id):
            """Extract canonical stat type from a base64-encoded Betr marketId.

            Base64 marketIds decode to colon-delimited strings of the form:
              {eventId}:{playerId}:{STAT_TYPE}:{line}:{projectionType}
            The STAT_TYPE segment (index 2) is ALL_CAPS_WITH_UNDERSCORES.
            Integer-only IDs are pure DFS markets — returns None for those.
            """
            if not market_id or str(market_id).isdigit():
                return None
            try:
                padded = market_id + "=" * (-len(market_id) % 4)
                decoded = _b64.b64decode(padded).decode("utf-8", errors="ignore")
                parts = decoded.split(":")
                if len(parts) >= 3:
                    candidate = parts[2]
                    # Stat type codes are ALL_CAPS; guard against decode noise
                    if candidate and candidate.replace("_", "").isalpha() and candidate == candidate.upper():
                        return candidate
            except Exception:
                pass
            return None

        r = _req.post(
            "https://api.fantasy.betr.app/graphql",
            json={
                "operationName": "LeagueUpcomingEvents",
                "query": query,
                "variables": {"league": league},
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=12,
        )
        if r.status_code != 200:
            st.warning(
                f"⚠️ Betr: endpoint returned HTTP {r.status_code} — "
                "projections unavailable. Try again later."
            )
            return []

        data = r.json()
        gql_errors = data.get("errors")
        if gql_errors:
            st.warning(
                f"⚠️ Betr GraphQL error: {gql_errors[0].get('message', gql_errors)}"
            )
            return []

        events = (data.get("data") or {}).get("getUpcomingEventsV2") or []
        for event in events:
            players_list = []
            for team in (event.get("teams") or []):
                if team and team.get("players"):
                    players_list.extend(team["players"])
            if event.get("players"):
                players_list.extend(event["players"])

            for player in players_list:
                if not player:
                    continue
                full_name = (
                    f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
                )
                if not full_name:
                    continue

                for proj in (player.get("projections") or []):
                    if not proj:
                        continue

                    # Skip markets that are not open (CLOSED, SUSPENDED, etc.)
                    mkt_status = proj.get("marketStatus") or ""
                    if mkt_status and mkt_status != "OPENED":
                        continue

                    # currentValue is the live-updated line; fall back to static value
                    line_raw = proj.get("currentValue") or proj.get("value")
                    if line_raw is None:
                        continue

                    prop_name = proj.get("label") or proj.get("name") or ""
                    if not prop_name:
                        continue

                    # Decode stat type from base64-encoded marketId when present.
                    # e.g. marketId "NmEyZjc4..." → decoded "...:STRIKEOUTS:5.0:REGULAR"
                    # → stat_type = "STRIKEOUTS".  Integer marketIds → None.
                    _raw_mid = proj.get("marketId") or ""
                    stat_type = _decode_stat_type(_raw_mid)
                    # Fallback: when marketId is an integer (pure DFS) or decode fails,
                    # use the human-readable label as stat_type for downstream mapping.
                    # This ensures stat_type is always non-None for OPENED projections.
                    if stat_type is None:
                        stat_type = (proj.get("label") or proj.get("name") or "").upper().replace(" ", "_") or None

                    # ── marketId shape logger (first prop only) ─────────────────
                    # Log a raw marketId sample on the very first projection so the
                    # base64 decode assumption can be verified from the System tab.
                    # Writes once per sport per session (guarded by props being empty).
                    if not props and _raw_mid:
                        try:
                            import base64 as _b64_log
                            _padded = _raw_mid + "=" * (-len(_raw_mid) % 4)
                            _decoded_sample = _b64_log.b64decode(_padded).decode("utf-8", errors="replace")
                        except Exception:
                            _decoded_sample = "(not base64)"
                        log_error_to_session(
                            "fetch_betr_direct",
                            f"marketId sample — raw: {_raw_mid[:80]} | "
                            f"decoded: {_decoded_sample[:120]} | "
                            f"stat_type extracted: {stat_type}",
                            "info",
                        )
                        try:
                            _mid_path = os.path.join(CACHE_DIR, f"betr_market_id_sample_{sport}.txt")
                            with open(_mid_path, "w") as _mf:
                                _mf.write(
                                    "raw:     " + str(_raw_mid) + "\n" +
                                    "decoded: " + str(_decoded_sample) + "\n" +
                                    "stat_type: " + str(stat_type) + "\n"
                                )
                        except Exception:
                            pass

                    try:
                        props.append({
                            "Player":        full_name,
                            "Prop":          prop_name,
                            "Line":          float(line_raw),
                            "Over":          "—",
                            "Under":         "—",
                            "Sport":         sport,
                            "Book":          "Betr",
                            "source":        "betr_direct",
                            "stat_type":     stat_type,
                            "market_id":     proj.get("marketId"),
                            "market_status": mkt_status,
                        })
                    except (ValueError, TypeError):
                        continue

    except Exception as _e:
        st.warning(
            f"⚠️ Betr: failed to fetch projections ({type(_e).__name__}: {_e}). "
            "Check network connectivity."
        )
        return []

    return props


# Alias so callers may use either name
fetch_betr_lines = fetch_betr_direct


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


def fetch_fanatics_game_lines(sport: str) -> list:
    """
    Fanatics Sportsbook game lines via Kambi backend (offering_id='ftn').

    Fanatics operates on Kambi as 'ftn'.  Degrades silently (returns []) if the
    offering ID is wrong — no harmful side effects.
    Returns {Matchup, Home, Away, HomeML, AwayML, Spread, Total,
             Book: 'Fanatics', Sport, source} per game.  Cached 60 min.
    """
    return _fetch_kambi_game_lines("ftn", sport, "Fanatics")


def fetch_espnbet_game_lines(sport: str) -> list:
    """
    ESPN Bet game lines via Kambi backend (offering_id='espnbet').

    ESPN Bet (Penn Entertainment) uses Kambi sportsbook infrastructure.
    Returns {Matchup, Home, Away, HomeML, AwayML, Spread, Total,
             Book: 'ESPN Bet', Sport, source} per game.  Cached 60 min.
    """
    return _fetch_kambi_game_lines("espnbet", sport, "ESPN Bet")

# ─────────────────────────────────────────────────────────────────────────────
# BASEBALL SAVANT STATCAST — MLB's own free public data, no auth required.
# Five CSV endpoints; each cached 2 hours.  All return dicts keyed by a
# lowercase "first last" player name for easy lookup in the scoring loop.
# ─────────────────────────────────────────────────────────────────────────────

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


def fetch_savant_statcast(season=2026):
    """
    Baseball Savant xStats leaderboard — completely free, no auth.
    Returns dict: lowercase_name → {xba, xslg, xwoba, xobp, xiso,
      exit_velocity_avg, launch_angle_avg, barrel_batted_rate,
      hard_hit_percent, strikeout_percent, walk_percent, player_id}
    Cached 2 hours.
    """
    cache_path = os.path.join(CACHE_DIR, f"savant_xstats_{season}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 3600 < 2:
            cached = _safe_load_pkl(cache_path)
            if cached: return cached

    url = (
        f"https://baseballsavant.mlb.com/leaderboard/custom"
        f"?year={season}&type=batter&filter=&sort=xwoba&sortDir=desc&min=q"
        f"&selections=xba,xslg,xwoba,xobp,xiso,exit_velocity_avg,launch_angle_avg"
        f",barrel_batted_rate,hard_hit_percent,strikeout_percent,walk_percent&csv=true"
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
            }
        if lookup: _safe_save_pkl(cache_path, lookup)
        return lookup
    except Exception as _e:
        print(f"[WARN] fetch_savant_statcast: {_e}")
        return _safe_load_pkl(cache_path) or {}


def fetch_savant_sprint_speed(season=2026):
    """
    Baseball Savant sprint speed leaderboard — free, no auth.
    Returns dict: lowercase_name → {sprint_speed, bolts, hp_to_1b, team, position}
    sprint_speed in ft/s; bolts = 30+ ft/s sprints; hp_to_1b in seconds.
    Cached 2 hours.
    """
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


def fetch_savant_expected_stats(season=2026):
    """
    Baseball Savant expected stats (xBA, xSLG, xwOBA) vs actual — catches
    overperformers (due for regression) and underperformers (breakout candidates).
    Returns dict: lowercase_name → {ba, xba, xba_diff, slg, xslg, xslg_diff,
                                     woba, xwoba, xwoba_diff, pa}
    Cached 2 hours.
    """
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


def fetch_savant_pitch_arsenal(season=2026):
    """
    Baseball Savant pitch arsenal — run value per 100 pitches by type,
    per pitcher.  Negative run value = good for pitcher (run-saving pitch).
    Returns dict: lowercase_pitcher_name → {FF, SL, CH, CU, SI, FC, ...}
      each value = run_value_per_100 for that pitch type.
    Cached 2 hours.
    """
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


def fetch_savant_batted_ball(season=2026):
    """
    Baseball Savant batted-ball profile per batter —
    GB%, FB%, LD%, PU%, pull/straight/oppo rates.
    Returns dict: lowercase_name → {gb_rate, fb_rate, ld_rate, pu_rate,
                                     pull_rate, oppo_rate, sweet_spot_rate}
    Cached 2 hours.
    """
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

    for abbr, (lat, lon, tz) in _MLB_STADIUM_COORDS.items():
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&hourly=wind_speed_10m,wind_direction_10m,temperature_2m,precipitation_probability"
                f"&wind_speed_unit=mph&temperature_unit=fahrenheit"
                f"&timezone={tz.replace('/', '%2F')}&forecast_days=1"
            )
            r = _http.get(url, timeout=8)
            if r.status_code != 200:
                result[abbr] = {"is_dome": False, "error": r.status_code}
                continue
            data = r.json()
            hourly = data.get("hourly", {})
            times  = hourly.get("time", [])
            winds  = hourly.get("wind_speed_10m", [])
            dirs   = hourly.get("wind_direction_10m", [])
            temps  = hourly.get("temperature_2m", [])
            precip = hourly.get("precipitation_probability", [])
            # Use hour 19 (7 PM local) as representative game time; fall back to 13 (1 PM)
            game_hr = next(
                (i for i, t in enumerate(times) if t.endswith("T19:00") or t.endswith("T18:00")),
                next((i for i, t in enumerate(times) if t.endswith("T13:00")), 12)
            )
            def _get(lst, idx):
                try: return lst[idx]
                except: return None
            spd = _get(winds, game_hr)
            deg = _get(dirs,  game_hr)
            result[abbr] = {
                "is_dome":        False,
                "wind_speed_mph": round(spd, 1) if spd is not None else None,
                "wind_dir_deg":   int(deg) if deg is not None else None,
                "wind_cardinal":  _deg_to_cardinal(deg),
                "temp_f":         round(_get(temps,  game_hr), 1) if _get(temps, game_hr) is not None else None,
                "precip_pct":     int(_get(precip, game_hr)) if _get(precip, game_hr) is not None else None,
            }
            time.sleep(0.1)
        except Exception as _we:
            result[abbr] = {"is_dome": False, "error": str(_we)[:50]}

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
        def extract(obj):
            if isinstance(obj, list):
                for i in obj: yield from extract(i)
            elif isinstance(obj, dict):
                if "participants" in obj or "moneyLine" in obj: yield obj
                else:
                    for v in obj.values():
                        if isinstance(v, (list,dict)): yield from extract(v)
        for event in extract(data):
            parts = event.get("participants", [])
            if len(parts) < 2: continue
            away = parts[0].get("name",""); home = parts[1].get("name","")
            if not home or not away: continue
            game = f"{away} @ {home}"
            ml = event.get("moneyLine",{})
            if ml.get("awayOdds"): results.append({"game":game,"home":home,"away":away,"market":"Moneyline","selection":away,"odds":ml["awayOdds"],"book":"BetOnline","sport":sport,"source":"betonline"})
            if ml.get("homeOdds"): results.append({"game":game,"home":home,"away":away,"market":"Moneyline","selection":home,"odds":ml["homeOdds"],"book":"BetOnline","sport":sport,"source":"betonline"})
            sp = event.get("spread", event.get("runLine",{}))
            if sp.get("awayOdds"): results.append({"game":game,"home":home,"away":away,"market":"Spread","selection":f"{away} {sp.get('awayHandicap','')}","odds":sp["awayOdds"],"book":"BetOnline","sport":sport,"source":"betonline"})
            if sp.get("homeOdds"): results.append({"game":game,"home":home,"away":away,"market":"Spread","selection":f"{home} {sp.get('homeHandicap','')}","odds":sp["homeOdds"],"book":"BetOnline","sport":sport,"source":"betonline"})
            tot = event.get("total", event.get("overUnder",{}))
            tl = tot.get("totalLine", tot.get("line",""))
            if tot.get("overOdds"):  results.append({"game":game,"home":home,"away":away,"market":"Total","selection":f"Over {tl}","odds":tot["overOdds"],"book":"BetOnline","sport":sport,"source":"betonline"})
            if tot.get("underOdds"): results.append({"game":game,"home":home,"away":away,"market":"Total","selection":f"Under {tl}","odds":tot["underOdds"],"book":"BetOnline","sport":sport,"source":"betonline"})
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
    try:
        req = urllib.request.Request(f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization":f"token {GITHUB_TOKEN}","Accept":"application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            tokens = json.loads(json.loads(r.read()).get("files",{}).get("betcouncil_caesars_tokens.json",{}).get("content","{}"))
            return tokens.get("bearer_jwt",""), tokens.get("waf_token","")
    except Exception as e:
        print(f"[WARN] _get_caesars_tokens: {e}"); return "",""

def fetch_caesars_props(sport: str) -> list:
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
    """
    cache_path = os.path.join(CACHE_DIR, f"kalshi_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        sport_keywords = {
            "MLB": ["baseball", "mlb", "runs", "strikeouts", "hits"],
            "NBA": ["basketball", "nba", "points", "rebounds", "assists"],
            "NFL": ["football", "nfl", "touchdowns", "yards"],
            "NHL": ["hockey", "nhl", "goals"],
        }
        keywords = sport_keywords.get(sport, [sport.lower()])
        results = []
        for kw in keywords[:2]:  # limit to 2 keywords to save calls
            r = _http.get(
                "https://api.elections.kalshi.com/trade-api/v2/markets",
                params={"status": "open", "series_ticker": kw.upper(), "limit": 100},
                headers={"Accept": "application/json"},
                timeout=12,
            )
            if r.status_code != 200:
                continue
            for mkt in r.json().get("markets", []):
                results.append({
                    "title":      mkt.get("title", ""),
                    "ticker":     mkt.get("ticker", ""),
                    "yes_bid":    mkt.get("yes_bid"),
                    "no_bid":     mkt.get("no_bid"),
                    "volume":     mkt.get("volume"),
                    "sport":      sport,
                    "source":     "kalshi",
                })
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
    """
    cache_path = os.path.join(CACHE_DIR, f"polymarket_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        sport_tags = {
            "MLB": "Baseball", "NBA": "Basketball",
            "NFL": "Football", "NHL": "Hockey",
        }
        tag = sport_tags.get(sport)
        if not tag:
            return []
        r = _http.get(
            "https://gamma-api.polymarket.com/markets",
            params={"tag": tag, "active": "true", "closed": "false", "limit": 100},
            headers={"Accept": "application/json"},
            timeout=12,
        )
        if r.status_code != 200:
            return []
        results = []
        for mkt in r.json():
            results.append({
                "question":    mkt.get("question", ""),
                "slug":        mkt.get("slug", ""),
                "yes_price":   mkt.get("outcomePrices", [""])[0] if mkt.get("outcomePrices") else None,
                "volume":      mkt.get("volume"),
                "sport":       sport,
                "source":      "polymarket",
            })
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_polymarket_markets: {e}")
        return []


def fetch_covers_consensus(sport: str) -> dict:
    """
    Fetch Covers.com public consensus betting data via ScraperAPI proxy.
    Returns {matchup: {home_pct, away_pct, over_pct, under_pct}}
    Cached 30 min.
    """
    cache_path = os.path.join(CACHE_DIR, f"covers_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 30:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        sport_map = {
            "MLB": "mlb", "NBA": "nba", "NFL": "nfl", "NHL": "nhl"
        }
        slug = sport_map.get(sport)
        if not slug:
            return {}
        # Covers blocks datacenter IPs — use ScraperAPI proxy
        proxy_url = (
            f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}"
            f"&url=https://www.covers.com/sport/{slug}/consensus"
        )
        r = _http.get(proxy_url, timeout=20)
        if r.status_code != 200:
            return {}
        # Parse HTML for consensus percentages
        import re as _re
        html = r.text
        results = {}
        # Look for JSON data embedded in page
        m = _re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, _re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                games = data.get("consensus", {}).get("games", [])
                for game in games:
                    home = game.get("homeTeam", {}).get("name", "")
                    away = game.get("awayTeam", {}).get("name", "")
                    if home and away:
                        results[f"{away} @ {home}"] = {
                            "home_pct":  game.get("homeConsensus"),
                            "away_pct":  game.get("awayConsensus"),
                            "over_pct":  game.get("overConsensus"),
                            "under_pct": game.get("underConsensus"),
                        }
            except Exception:
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
    cache_path = os.path.join(CACHE_DIR, "mlb_rolling_avgs.pkl")
    rolling = {}
    # Use full active roster IDs (all 30 teams) instead of hardcoded 29-player list
    all_roster_ids = st.session_state.get("mlb_roster_ids") or MLB_PLAYER_IDS
    for player_name, player_id in all_roster_ids.items():
        player_avgs = PLAYER_AVERAGES.get("MLB", {}).get(player_name, {})
        is_pitcher = "SO" in player_avgs or "ER" in player_avgs
        group = "pitching" if is_pitcher else "hitting"
        url = (f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group={group}&season=2025&gameType=R")
        resp = None
        for _attempt in range(2):  # one retry on transient connection failures
            try:
                resp = _http.get(url, headers=HEADERS, timeout=10)
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                    requests.exceptions.RetryError, requests.exceptions.ChunkedEncodingError) as _conn_e:
                if _attempt == 0:
                    time.sleep(1.0)
                    continue
                st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_mlb_rolling_averages", "error": f"statsapi unreachable after retry: {str(_conn_e)[:80]}"})
                resp = None
        if resp is None:
            continue
        try:
            if resp.status_code != 200:
                continue
            data = resp.json()
            stats_list = data.get("stats", [])
            if not stats_list:
                continue
            splits = stats_list[0].get("splits", [])
            last10 = splits[-10:] if len(splits) >= 10 else splits
            if len(last10) < 3:
                continue
            if is_pitcher:
                so_vals = [g["stat"].get("strikeOuts",0) for g in last10]
                er_vals = [g["stat"].get("earnedRuns",0) for g in last10]
                h_vals = [g["stat"].get("hits",0) for g in last10]
                rolling[player_name] = {
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
                rolling[player_name] = {
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
            time.sleep(0.3)
        except Exception as e:
            st.session_state.setdefault("errors", []).append({"time": datetime.now().strftime("%H:%M:%S"), "source": "fetch_mlb_rolling_averages", "error": str(e)[:100]})
            continue
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

    # ── 1. Gist direct ────────────────────────────────────────────────────────
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
    """ESPN BET game lines via Kambi (offering_id='espnbet'). Cached 60 min."""
    return _fetch_kambi_game_lines("espnbet", sport, "ESPN BET")


def fetch_fanatics_game_lines(sport: str) -> list:
    """Fanatics Sportsbook game lines via Kambi (offering_id='fanaticssb'). Cached 60 min."""
    return _fetch_kambi_game_lines("fanaticssb", sport, "Fanatics")


def fetch_thescore_game_lines(sport: str) -> list:
    """theScore Bet game lines via Kambi (offering_id='thescore'). Cached 60 min."""
    return _fetch_kambi_game_lines("thescore", sport, "theScore")

def fetch_sharpapi_lines(sport: str) -> list:
    """
    Fetch game lines from SharpAPI — 20+ books, Pinnacle no-vig EV pre-computed.
    Returns list of {game, sport, market, book, odds_american, ev_percent,
                     fair_odds, is_ev_positive, home_team, away_team}
    Free tier: 12 req/min. Cached 15 min.
    Auth: X-API-Key header.
    """
    if not SHARPAPI_KEY:
        return []
    sport_map = {
        "MLB": "baseball_mlb", "NBA": "basketball_nba",
        "NFL": "americanfootball_nfl", "NHL": "icehockey_nhl",
        "WNBA": "basketball_wnba",
    }
    league = sport_map.get(sport)
    if not league:
        return []
    cache_path = os.path.join(CACHE_DIR, f"sharpapi_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 15:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        r = _http.get(
            f"{SHARPAPI_BASE}/odds",
            params={"league": league, "market_type": "moneyline,spread,total"},
            headers={"X-API-Key": SHARPAPI_KEY, "Accept": "application/json"},
            timeout=12,
        )
        if r.status_code == 429:
            print("[WARN] SharpAPI rate limit hit")
            return []
        if r.status_code != 200:
            print(f"[WARN] fetch_sharpapi_lines HTTP {r.status_code}")
            return []
        data = r.json().get("data", [])
        results = []
        for event in data:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            game = f"{away} @ {home}"
            for line in event.get("odds", []):
                results.append({
                    "game":          game,
                    "home_team":     home,
                    "away_team":     away,
                    "sport":         sport,
                    "book":          line.get("sportsbook", ""),
                    "market":        line.get("market_type", ""),
                    "selection":     line.get("selection", ""),
                    "odds_american": line.get("odds_american"),
                    "ev_percent":    line.get("ev_percent"),
                    "fair_odds":     line.get("fair_odds"),
                    "is_ev_positive": line.get("is_ev_positive", False),
                    "source":        "sharpapi",
                })
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_sharpapi_lines: {e}")
        return []


def fetch_sharpapi_props(sport: str) -> list:
    """
    Fetch player props from SharpAPI — Pinnacle no-vig EV pre-computed per prop.
    Returns list of {Player, Prop, Line, OverOdds, UnderOdds, Book,
                     ev_percent, fair_odds, is_ev_positive, Sport, source}
    Free tier: 12 req/min. Cached 20 min.
    """
    if not SHARPAPI_KEY:
        return []
    sport_map = {
        "MLB": "baseball_mlb", "NBA": "basketball_nba",
        "NFL": "americanfootball_nfl", "NHL": "icehockey_nhl",
        "WNBA": "basketball_wnba",
    }
    league = sport_map.get(sport)
    if not league:
        return []
    cache_path = os.path.join(CACHE_DIR, f"sharpapi_props_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 20:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached
    try:
        r = _http.get(
            f"{SHARPAPI_BASE}/odds",
            params={"league": league, "market_type": "player_props"},
            headers={"X-API-Key": SHARPAPI_KEY, "Accept": "application/json"},
            timeout=12,
        )
        if r.status_code == 429:
            print("[WARN] SharpAPI rate limit hit (props)")
            return []
        if r.status_code != 200:
            print(f"[WARN] fetch_sharpapi_props HTTP {r.status_code}")
            return []
        data = r.json().get("data", [])
        results = []
        for event in data:
            for line in event.get("odds", []):
                player = line.get("player", line.get("description", ""))
                if not player:
                    continue
                market = line.get("market_type", "")
                selection = line.get("selection", "").upper()
                results.append({
                    "Player":        player,
                    "Prop":          market.replace("player_", "").replace("_", " ").title(),
                    "Line":          line.get("point", line.get("handicap")),
                    "OverOdds":      str(int(line.get("odds_american", 0))) if selection == "OVER" else "N/A",
                    "UnderOdds":     str(int(line.get("odds_american", 0))) if selection == "UNDER" else "N/A",
                    "Book":          line.get("sportsbook", ""),
                    "ev_percent":    line.get("ev_percent"),
                    "fair_odds":     line.get("fair_odds"),
                    "is_ev_positive": line.get("is_ev_positive", False),
                    "Sport":         sport,
                    "source":        "sharpapi",
                })
        if results:
            _safe_save_pkl(cache_path, results)
        return results
    except Exception as e:
        print(f"[WARN] fetch_sharpapi_props: {e}")
        return []

def fetch_bet365_game_lines(sport: str) -> list:
    """Bet365 game lines via Kambi (offering_id='bet365'). Cached 60 min."""
    return _fetch_kambi_game_lines("bet365", sport, "Bet365")


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


def fetch_pinnacle_props(sport: str) -> list:
    """Pinnacle player props — not available on arcadia guest API. Returns []."""
    return []

# ══════════════════════════════════════════════════════════════════════════════
# ADDITIONAL DATA SOURCES — v9.1
# FanGraphs, Baseball Savant direct, Unabated, OddsJam, Tennis, Golf, MMA,
# Soccer (MLS), UFC, PropSwap
# ══════════════════════════════════════════════════════════════════════════════

import io as _io

_SPORT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


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

def fetch_fangraphs_batting(season: int = 2026, min_pa: int = 10) -> list:
    """
    Fetch FanGraphs batting leaderboard — xwOBA, barrel%, hard hit%, BABIP, ISO.
    URL: fangraphs.com/api/leaders/major-league/data
    Free, no auth. Returns list of player stat dicts.
    """
    import os, time
    cache_path = os.path.join(CACHE_DIR, f"fg_batting_{season}.pkl")
    cached = _load_pkl(cache_path, max_age_h=6)
    if cached is not None:
        return cached

    url = f"https://www.fangraphs.com/api/leaders/major-league/data"
    params = {
        "age": 0, "pos": "all", "stats": "bat", "lg": "all",
        "qual": min_pa, "season": season, "season1": season,
        "month": 0, "team": 0, "pageitems": 500, "pagenum": 1,
        "ind": 0, "type": 8,  # type=8 = advanced stats
    }
    try:
        r = _http.get(url, params=params, headers=_SPORT_HEADERS, timeout=20)
        if r.status_code != 200:
            st.warning(f"⚠️ FanGraphs batting: HTTP {r.status_code}")
            return []
        data = r.json()
        players = data.get("data", data) if isinstance(data, dict) else data
        _cache_pkl(cache_path, players)
        return players
    except Exception as e:
        st.warning(f"⚠️ FanGraphs batting error: {e}")
        return []


def fetch_fangraphs_pitching(season: int = 2026, min_ip: int = 5) -> list:
    """
    Fetch FanGraphs pitching leaderboard — SIERA, xFIP, K/9, BB/9, HR/9.
    SIERA is the best ERA estimator for next-start prop prediction.
    """
    import os
    cache_path = os.path.join(CACHE_DIR, f"fg_pitching_{season}.pkl")
    cached = _load_pkl(cache_path, max_age_h=6)
    if cached is not None:
        return cached

    url = "https://www.fangraphs.com/api/leaders/major-league/data"
    params = {
        "pos": "all", "stats": "pit", "lg": "all",
        "qual": min_ip, "season": season, "season1": season,
        "month": 0, "team": 0, "pageitems": 500, "pagenum": 1,
        "type": 8,
    }
    try:
        r = _http.get(url, params=params, headers=_SPORT_HEADERS, timeout=20)
        if r.status_code != 200:
            st.warning(f"⚠️ FanGraphs pitching: HTTP {r.status_code}")
            return []
        data = r.json()
        players = data.get("data", data) if isinstance(data, dict) else data
        _cache_pkl(cache_path, players)
        return players
    except Exception as e:
        st.warning(f"⚠️ FanGraphs pitching error: {e}")
        return []


def fetch_fangraphs_park_factors(season: int = 2026) -> dict:
    """
    Fetch FanGraphs park factors per team.
    Returns {team_abbr: {HR_factor, R_factor, H_factor}}
    """
    import os
    cache_path = os.path.join(CACHE_DIR, f"fg_park_factors_{season}.pkl")
    cached = _load_pkl(cache_path, max_age_h=24)
    if cached is not None:
        return cached

    url = "https://www.fangraphs.com/api/guts.aspx"
    params = {"type": "pf", "teamid": 0, "season": season}
    try:
        r = _http.get(url, params=params, headers=_SPORT_HEADERS, timeout=20)
        if r.status_code != 200:
            return {}
        data = r.json()
        parks = {}
        for row in (data if isinstance(data, list) else data.get("data", [])):
            team = row.get("Team", row.get("team", ""))
            if team:
                parks[team] = {
                    "hr_factor":  float(row.get("HR",  row.get("hr",  100))) / 100,
                    "r_factor":   float(row.get("R",   row.get("r",   100))) / 100,
                    "h_factor":   float(row.get("H",   row.get("h",   100))) / 100,
                    "bb_factor":  float(row.get("BB",  row.get("bb",  100))) / 100,
                    "so_factor":  float(row.get("SO",  row.get("so",  100))) / 100,
                }
        _cache_pkl(cache_path, parks)
        return parks
    except Exception as e:
        return {}


# ── Baseball Savant direct ────────────────────────────────────────────────────


def fetch_savant_statcast_player(player_id: int, season: int = 2026) -> dict:
    """
    Fetch Statcast data for a specific player from Baseball Savant.
    Returns detailed exit velo, launch angle, barrel%, hard hit%.
    player_id: MLB player ID (e.g. 660271 = Juan Soto)
    """
    import os
    cache_path = os.path.join(CACHE_DIR, f"savant_player_{player_id}_{season}.pkl")
    cached = _load_pkl(cache_path, max_age_h=3)
    if cached is not None:
        return cached

    url = "https://baseballsavant.mlb.com/savant-player"
    params = {
        "player_id": player_id, "stats": "statcast",
        "game_date_gt": f"{season}-03-01",
        "game_date_lt": f"{season}-11-01",
        "type": "batter",
    }
    try:
        r = _http.get(url, params=params, headers=_SPORT_HEADERS, timeout=20)
        if r.status_code != 200:
            return {}
        # Parse JSON from HTML page (embedded in script tag)
        import re
        match = re.search(r'window\.statcast_data\s*=\s*(\{[^;]+\})', r.text)
        if match:
            import json
            data = json.loads(match.group(1))
            _cache_pkl(cache_path, data)
            return data
        return {}
    except Exception:
        return {}


# ── Unabated (no-vig Pinnacle screener) ──────────────────────────────────────

def fetch_unabated_lines(sport: str = "mlb") -> list:
    """
    Fetch Unabated no-vig lines — Pinnacle-based fair value screener.
    Free public data. Returns list of {game, market, fair_line, books}.
    """
    import os
    cache_path = os.path.join(CACHE_DIR, f"unabated_{sport}.pkl")
    cached = _load_pkl(cache_path, max_age_h=0.25)  # 15 min cache
    if cached is not None:
        return cached

    # Unabated public endpoint
    url = f"https://unabated.com/api/lines/{sport.lower()}"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code != 200:
            # Try alternate endpoint
            url2 = f"https://unabated.com/lines/{sport.lower()}"
            r = _http.get(url2, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            games = data if isinstance(data, list) else data.get("games", data.get("data", []))
            _cache_pkl(cache_path, games)
            return games
        return []
    except Exception:
        return []


# ── OddsJam positive EV ───────────────────────────────────────────────────────



def fetch_oddsjam_positive_ev(sport: str = "baseball_mlb",
                               api_key: str = "") -> list:
    """
    Fetch positive EV props from OddsJam.
    Requires API key (free tier available at oddsjam.com).
    Set ODDSJAM_KEY in Streamlit secrets.
    """
    import os
    if not api_key:
        try:
            api_key = st.secrets.get("ODDSJAM_KEY", "")
        except Exception:
            pass
    if not api_key:
        return []

    cache_path = os.path.join(CACHE_DIR, f"oddsjam_ev_{sport}.pkl")
    cached = _load_pkl(cache_path, max_age_h=0.25)
    if cached is not None:
        return cached

    url = "https://api.oddsjam.com/api/v2/positive-ev"
    params = {"apikey": api_key, "sport": sport, "min_ev": 1.0}
    try:
        r = _http.get(url, params=params, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code == 401:
            st.warning("⚠️ OddsJam: invalid API key — set ODDSJAM_KEY in secrets")
            return []
        if r.status_code != 200:
            return []
        data = r.json()
        props = data.get("data", data) if isinstance(data, dict) else data
        _cache_pkl(cache_path, props)
        return props
    except Exception:
        return []


# ── Tennis ────────────────────────────────────────────────────────────────────

def fetch_tennis_scoreboard(tour: str = "atp") -> dict:
    """
    Fetch live/upcoming tennis scores from ESPN hidden API.
    tour: "atp" or "wta"
    """
    import os
    cache_path = os.path.join(CACHE_DIR, f"tennis_{tour}_scoreboard.pkl")
    cached = _load_pkl(cache_path, max_age_h=0.5)
    if cached is not None:
        return cached

    url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code != 200:
            return {}
        data = r.json()
        _cache_pkl(cache_path, data)
        return data
    except Exception:
        return {}


def fetch_tennis_player_stats(player_id: str, tour: str = "atp") -> dict:
    """Fetch tennis player stats from ESPN."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/athletes/{player_id}"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Golf ──────────────────────────────────────────────────────────────────────

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
    """Fetch golf player historical stats from ESPN."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/golf/{tour}/athletes/{player_id}/statistics"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── MMA / UFC ─────────────────────────────────────────────────────────────────

def fetch_ufc_scoreboard() -> dict:
    """Fetch UFC/MMA event data from ESPN."""
    import os
    cache_path = os.path.join(CACHE_DIR, "ufc_scoreboard.pkl")
    cached = _load_pkl(cache_path, max_age_h=1)
    if cached is not None:
        return cached

    url = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code != 200:
            return {}
        data = r.json()
        _cache_pkl(cache_path, data)
        return data
    except Exception:
        return {}


def fetch_ufc_fighter_stats(fighter_id: str) -> dict:
    """Fetch UFC fighter stats from ESPN."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/mma/ufc/athletes/{fighter_id}"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Soccer / MLS ──────────────────────────────────────────────────────────────

def fetch_soccer_scoreboard(league: str = "usa.1") -> dict:
    """
    Fetch soccer scoreboard from ESPN.
    league: usa.1=MLS, eng.1=EPL, esp.1=La Liga, ger.1=Bundesliga,
            ita.1=Serie A, fra.1=Ligue 1, uefa.champions=UCL
    """
    import os
    cache_path = os.path.join(CACHE_DIR, f"soccer_{league.replace('.','_')}_scoreboard.pkl")
    cached = _load_pkl(cache_path, max_age_h=0.25)
    if cached is not None:
        return cached

    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code != 200:
            return {}
        data = r.json()
        _cache_pkl(cache_path, data)
        return data
    except Exception:
        return {}


def fetch_soccer_standings(league: str = "usa.1", season: int = 2026) -> list:
    """Fetch soccer standings from ESPN."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/standings?season={season}"
    try:
        r = _http.get(url, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("standings", data.get("children", []))
    except Exception:
        return []


# ── PropSwap (secondary market pricing) ──────────────────────────────────────


BOOKMAKER_SPORT_PATHS = {
    "MLB":  "baseball",
    "NBA":  "basketball/nba",
    "NFL":  "football/nfl",
    "NHL":  "hockey/nhl",
    "WNBA": "basketball/wnba",
}


def fetch_bookmaker_game_lines(sport: str) -> list:
    """
    Fetch Bookmaker.eu game lines via HTML scraping (server-rendered page).
    Auth: cf_clearance + PHPSESSID cookies stored in Streamlit secrets.
    Cached 20 min.
    """
    sport_path = BOOKMAKER_SPORT_PATHS.get(sport)
    if not sport_path:
        return []

    try:
        cf   = BOOKMAKER_CF   if BOOKMAKER_CF   else ""
        sess = BOOKMAKER_SESSID if BOOKMAKER_SESSID else ""
    except Exception:
        cf = sess = ""

    cache_path = os.path.join(CACHE_DIR, f"bookmaker_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        if (time.time() - os.path.getmtime(cache_path)) / 60 < 20:
            cached = _safe_load_pkl(cache_path)
            if cached is not None: return cached

    try:
        url = f"https://lines.bookmaker.eu/en/sports/{sport_path}/"
        cookie_parts = []
        if cf:   cookie_parts.append(f"cf_clearance={cf}")
        if sess: cookie_parts.append(f"PHPSESSID={sess}")
        headers = {
            "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
            "Referer":         "https://lines.bookmaker.eu/en/sports/",
            "upgrade-insecure-requests": "1",
        }
        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)

        r = _http.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"[WARN] fetch_bookmaker_game_lines HTTP {r.status_code}")
            return []

        html = r.text
        results = []

        # Try JSON embedded in script tag
        import re as _re
        for pattern in [
            r'var\s+lines\s*=\s*(\[.*?\]);',
            r'var\s+events\s*=\s*(\[.*?\]);',
            r'"events"\s*:\s*(\[.*?\])',
        ]:
            jm = _re.search(pattern, html, _re.S)
            if jm:
                try:
                    events = json.loads(jm.group(1))
                    for ev in events:
                        home = ev.get("home", ev.get("homeTeam", ""))
                        away = ev.get("away", ev.get("awayTeam", ""))
                        if not home or not away: continue
                        game = f"{away} @ {home}"
                        for mkt, sel, odds_key in [
                            ("Moneyline", away, "awayML"),
                            ("Moneyline", home, "homeML"),
                        ]:
                            odds = ev.get(odds_key, "")
                            if odds:
                                results.append({"game":game,"home":home,"away":away,
                                    "market":mkt,"selection":sel,"odds":odds,
                                    "book":"Bookmaker","sport":sport,"source":"bookmaker"})
                    if results:
                        _safe_save_pkl(cache_path, results)
                        return results
                except Exception:
                    pass

        # HTML table parsing — Bookmaker renders odds in data attributes
        rows = _re.findall(
            r'data-away="([^"]+)"[^>]*data-home="([^"]+)"[^>]*'
            r'(?:data-away-ml="([^"]*)")?[^>]*(?:data-home-ml="([^"]*)")?'
            r'(?:[^>]*data-total-line="([^"]*)")?'
            r'(?:[^>]*data-over-price="([^"]*)")?'
            r'(?:[^>]*data-under-price="([^"]*)")?'
            r'(?:[^>]*data-away-spread="([^"]*)")?'
            r'(?:[^>]*data-home-spread="([^"]*)")?',
            html, _re.S
        )
        for row in rows:
            away, home = row[0].strip(), row[1].strip()
            if not away or not home: continue
            game = f"{away} @ {home}"
            away_ml  = row[2] if len(row) > 2 else ""
            home_ml  = row[3] if len(row) > 3 else ""
            tot_line = row[4] if len(row) > 4 else ""
            over_p   = row[5] if len(row) > 5 else ""
            under_p  = row[6] if len(row) > 6 else ""
            away_sp  = row[7] if len(row) > 7 else ""
            home_sp  = row[8] if len(row) > 8 else ""
            for mkt, sel, odds in [
                ("Moneyline", away, away_ml),
                ("Moneyline", home, home_ml),
                ("Total", f"Over {tot_line}",  over_p),
                ("Total", f"Under {tot_line}", under_p),
                ("Spread", f"{away} {away_sp}", away_sp),
                ("Spread", f"{home} {home_sp}", home_sp),
            ]:
                if odds and odds not in ("", "0", "EV"):
                    results.append({"game":game,"home":home,"away":away,
                        "market":mkt,"selection":sel,"odds":odds,
                        "book":"Bookmaker","sport":sport,"source":"bookmaker"})

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

def fetch_statmuse_prop_context(player_name, prop_type, line, sport="MLB"):
    """L10 hit rate vs prop line from StatMuse."""
    pmap={"hits":"hits last 10 games","home_runs":"home runs last 10 games","rbi":"rbi last 10 games",
          "total_bases":"total bases last 10 games","strikeouts":"strikeouts last 10 games",
          "pitcher_ks":"strikeouts last 5 starts","points":"points last 10 games",
          "rebounds":"rebounds last 10 games","assists":"assists last 10 games",
          "passing_yards":"passing yards last 5 games","rushing_yards":"rushing yards last 5 games",
          "receiving_yards":"receiving yards last 5 games","goals":"goals last 10 games"}
    pn=prop_type.lower().replace(" ","_").replace("-","_")
    out=fetch_statmuse_player(player_name,pmap.get(pn,f"{prop_type} last 10 games"),sport)
    hr=None
    try:
        rows=out.get("stats",[])
        if rows and isinstance(rows,list):
            ov=tot=0
            for row in rows[-10:]:
                if isinstance(row,dict):
                    for k,v in row.items():
                        if pn[:3] in k.lower():
                            try:
                                if float(v)>=float(line): ov+=1
                                tot+=1
                            except Exception: pass
                            break
            if tot>0: hr=ov/tot
    except Exception: pass
    out.update({"hit_rate_l10":hr,"prop_line":line,"prop_type":prop_type,"supporting_bet":(hr is not None and hr>=0.60)})
    return out

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
        req = urllib.request.Request(f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization":f"token {GITHUB_TOKEN}","Accept":"application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            gist = json.loads(r.read())
        f  = gist.get("files",{}).get("betcouncil_closing_lines.json",{})
        db = json.loads(f.get("content","{}")) if f else {}
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
        req = urllib.request.Request(f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization":f"token {GITHUB_TOKEN}","Accept":"application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            gist = json.loads(r.read())
        f = gist.get("files",{}).get("betcouncil_closing_lines.json",{})
        return json.loads(f.get("content","{}")).get(key,{}) if f else {}
    except Exception as e:
        print(f"[WARN] load_closing_line: {e}"); return {}

def fetch_all_closing_lines():
    """Load full closing line DB from Gist. Cached 10 min."""
    cp = os.path.join(CACHE_DIR, "closing_lines_db.pkl")
    if os.path.exists(cp) and (time.time()-os.path.getmtime(cp))/60 < 10:
        c = _safe_load_pkl(cp)
        if c: return c
    try:
        req = urllib.request.Request(f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization":f"token {GITHUB_TOKEN}","Accept":"application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            gist = json.loads(r.read())
        f  = gist.get("files",{}).get("betcouncil_closing_lines.json",{})
        db = json.loads(f.get("content","{}")) if f else {}
        _safe_save_pkl(cp, db); return db
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
    jwt = _betslib_jwt()
    if not jwt: return []
    try:
        hdrs = {
            "Authorization": f"Bearer {jwt}",
            "Accept":        "application/json, text/plain, */*",
            "Origin":        "https://signalodds.com",
            "Referer":       "https://signalodds.com/",
            "x-client-source": "web",
            "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        url = f"{BETSLIB_BASE}/predictions?date_filter=upcoming&limit={limit}&page=1&sort_by=commence_time&sort_dir=asc&sport={slug}"
        r   = _http.get(url, headers=hdrs, timeout=15)
        if r.status_code == 401:
            print("[WARN] betslib: JWT expired — refresh SIGNAL_ODDS_JWT in secrets"); return []
        if r.status_code != 200:
            print(f"[WARN] betslib HTTP {r.status_code}"); return []
        raw  = r.json()
        preds = raw if isinstance(raw,list) else raw.get("data", raw.get("predictions", raw.get("results",[])))
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


def fetch_propswap_listings(sport: str = "baseball") -> list:
    """
    Fetch PropSwap secondary market ticket listings.
    Secondary market prices reveal true sharp value on props.
    Listings where market price > face value = sharp money on that side.
    """
    import os
    cache_path = os.path.join(CACHE_DIR, f"propswap_{sport}.pkl")
    cached = _load_pkl(cache_path, max_age_h=1)
    if cached is not None:
        return cached

    url = f"https://propswap.com/api/v1/events"
    params = {"sport": sport, "status": "active"}
    try:
        r = _http.get(url, params=params, headers=_SPORT_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        listings = data if isinstance(data, list) else data.get("events", data.get("data", []))
        _cache_pkl(cache_path, listings)
        return listings
    except Exception:
        return []


def get_propswap_sharp_signal(player: str, prop_type: str,
                               listings: list) -> dict:
    """
    Check if PropSwap secondary market shows sharp signal for a prop.
    Market price > face value = demand exceeds supply = sharp side.
    """
    name_lower = player.lower().strip()
    prop_lower  = prop_type.lower().strip()

    for listing in listings:
        name = str(listing.get("player_name", listing.get("name", ""))).lower()
        prop = str(listing.get("prop_type", listing.get("stat", ""))).lower()
        if name_lower not in name and prop_lower not in prop:
            continue
        face  = float(listing.get("face_value", listing.get("price", 0)) or 0)
        mkt   = float(listing.get("market_value", listing.get("last_sale", 0)) or 0)
        if face > 0 and mkt > 0:
            premium = (mkt - face) / face
            return {
                "sharp_signal":  premium > 0.05,  # 5%+ premium = demand
                "premium_pct":   round(premium, 3),
                "face_value":    face,
                "market_value":  mkt,
                "direction":     "OVER" if premium > 0 else "UNDER",
            }
    return {"sharp_signal": False, "premium_pct": 0.0}

