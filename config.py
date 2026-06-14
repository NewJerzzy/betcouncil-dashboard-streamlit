"""BetCouncil Config — shared constants for app.py and scrapers."""
import os
import streamlit as st

# === API KEYS (from Streamlit secrets) ===
def get_secret(key, default=""):
    try:
        return st.secrets.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)

GITHUB_TOKEN = get_secret("GITHUB_TOKEN")
GITHUB_GIST_ID = get_secret("GITHUB_GIST_ID", "7e52e1c2c2054847c7c4663a157386c5")
ODDS_API_KEY = get_secret("ODDS_API_KEY")
ODDSPAPI_KEY = get_secret("ODDSPAPI_KEY")
ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
OCR_SPACE_API_KEY = get_secret("OCR_SPACE_API_KEY")
SCRAPEOPS_KEY = get_secret("SCRAPEOPS_KEY")
BDL_API_KEY = get_secret("BALLSDONTLIE_API_KEY")
RAPIDAPI_KEY = get_secret("RAPIDAPI_KEY")

# === REQUEST CONFIG ===
REQUEST_TIMEOUT = 15
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# === API BASE URLS ===
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ESPN_CORE_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# === SPORT MAPPINGS ===
ODDS_API_SPORT_MAP = {
    "NBA": "basketball_nba",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    "WNBA": "basketball_wnba",
    "NFL": "americanfootball_nfl",
}

ESPN_CORE_SPORT_MAP = {
    "NBA": "basketball/nba",
    "MLB": "baseball/mlb",
    "NHL": "hockey/nhl",
    "WNBA": "basketball/wnba",
    "NFL": "football/nfl",
}

CBS_SPORT_MAP = {
    "NBA": "NBA", "MLB": "MLB", "NHL": "NHL",
    "WNBA": "WNBA", "NFL": "NFL",
}

# === BOOKS ===
ACTIVE_BOOKS = ["PrizePicks", "Underdog", "Novig", "Betr", "DraftKings", "BetMGM", "Bovada"]
DISABLED_BOOKS = ["Sleeper", "BetOnline", "FanDuel", "Caesars"]

# === TIER COLORS ===
TIER_COLORS = {
    "SOVEREIGN": "#ffd700",
    "ELITE": "#00ff88",
    "APPROVED": "#58a6ff",
    "LEAN": "#ff8c00",
    "PASS": "#ff4444",
}
