# ═══════════════════════════════════════════════════════════════
# BETCOUNCIL GIST FALLBACK FIXES
# These functions should be added/updated in app.py
# ═══════════════════════════════════════════════════════════════

import requests
import json
from datetime import date, timedelta
import streamlit as st
import logging
import pandas as pd
try:
    from config import GITHUB_TOKEN, GITHUB_GIST_ID
except ImportError:
    GITHUB_TOKEN   = st.secrets.get('GITHUB_TOKEN', '')
    GITHUB_GIST_ID = st.secrets.get('GITHUB_GIST_ID', '')

# Configure logging for error visibility
logger = logging.getLogger("betcouncil")

def log_error_to_session(source: str, error: str, error_type: str = "error"):
    """
    Log errors to session_state so they appear in the System tab.
    
    Args:
        source: Function/component name (e.g., "fetch_auto_scraped_props")
        error: Error message (truncated to 200 chars)
        error_type: "error", "warning", or "info"
    """
    try:
        if "errors" not in st.session_state:
            st.session_state["errors"] = []
        
        st.session_state["errors"].append({
            "time": pd.Timestamp.now().strftime("%H:%M:%S"),
            "source": source,
            "message": str(error)[:200],
            "type": error_type
        })
        # Keep only last 50 errors
        st.session_state["errors"] = st.session_state["errors"][-50:]
    except Exception as e:
        logger.error(f"Failed to log error: {e}", exc_info=True)


def is_date_valid_for_today(date_str: str) -> bool:
    """
    Check if date_str is today or yesterday (for overnight prop scrapes).
    Accepts ISO format: "2026-06-09", "2026-06-09T14:30:00Z", etc.
    """
    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Parse ISO date
        if "T" in date_str:
            date_obj = date.fromisoformat(date_str.split("T")[0])
        else:
            date_obj = date.fromisoformat(date_str)
        
        return date_obj in (today, yesterday)
    except (ValueError, IndexError):
        return False


def fetch_auto_scraped_props(sport: str, _use_cache: bool = True) -> list:
    """
    Fetch props from GitHub Gist (auto_scraped_props.json).
    This is the FALLBACK when PrizePicks direct scraping fails.
    
    The local betcouncil_auto_scraper.py script pushes props to this Gist.
    We use caching (10 min TTL) to avoid hammering GitHub API.
    
    Args:
        sport: "NBA", "MLB", "NHL", "WNBA", "NFL"
        _use_cache: Internal - set to False to bypass cache
    
    Returns:
        List of props from Gist, or [] if unavailable
    """
    props = []
    
    try:
        GIST_API = "https://api.github.com/gists"
        
        if not GITHUB_TOKEN or not GITHUB_GIST_ID:
            log_error_to_session(
                "fetch_auto_scraped_props",
                "GitHub credentials not configured in secrets",
                "warning"
            )
            return []
        
        # Fetch Gist metadata
        gist_url = f"{GIST_API}/{GITHUB_GIST_ID}"
        r = requests.get(
            gist_url,
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            timeout=10
        )
        
        if r.status_code != 200:
            log_error_to_session(
                "fetch_auto_scraped_props",
                f"Gist API returned {r.status_code}: {r.text[:100]}",
                "warning"
            )
            return []
        
        gist_data = r.json()
        files = gist_data.get("files", {})
        
        # Look for auto_scraped_props.json
        if "auto_scraped_props.json" not in files:
            log_error_to_session(
                "fetch_auto_scraped_props",
                "auto_scraped_props.json not found in Gist",
                "warning"
            )
            return []
        
        file_obj = files["auto_scraped_props.json"]
        
        # Check file size — if >1MB, use raw_url
        file_size = file_obj.get("size", 0)
        if file_size > 900000:  # Close to 1MB limit
            log_error_to_session(
                "fetch_auto_scraped_props",
                f"Gist file is {file_size/1000:.0f}KB (large), using raw_url",
                "info"
            )
            # Use raw content URL to avoid truncation
            raw_url = file_obj.get("raw_url", "")
            if raw_url:
                r_raw = requests.get(raw_url, timeout=10)
                if r_raw.status_code == 200:
                    gist_content = r_raw.json()
                else:
                    log_error_to_session(
                        "fetch_auto_scraped_props",
                        f"Raw URL returned {r_raw.status_code}",
                        "error"
                    )
                    return []
            else:
                log_error_to_session(
                    "fetch_auto_scraped_props",
                    "raw_url not available from Gist API",
                    "error"
                )
                return []
        else:
            # Parse from Gist API response
            content = file_obj.get("content", "")
            if not content:
                log_error_to_session(
                    "fetch_auto_scraped_props",
                    "Gist content is empty",
                    "warning"
                )
                return []
            try:
                gist_content = json.loads(content)
            except json.JSONDecodeError as e:
                log_error_to_session(
                    "fetch_auto_scraped_props",
                    f"Gist JSON parse error: {str(e)[:100]}",
                    "error"
                )
                return []
        
        # Verify date — script may run before midnight
        gist_date = gist_content.get("date", "")
        if not is_date_valid_for_today(gist_date):
            log_error_to_session(
                "fetch_auto_scraped_props",
                f"Gist is stale (date: {gist_date}, today: {date.today().isoformat()})",
                "warning"
            )
            return []
        
        # Extract props for this sport
        all_props = gist_content.get("props", [])
        props = [
            p for p in all_props
            if p.get("Sport") == sport
        ]
        
        if props:
            log_error_to_session(
                "fetch_auto_scraped_props",
                f"✅ Loaded {len(props)} {sport} props from Gist (auto_scraped_props.json)",
                "info"
            )
        else:
            log_error_to_session(
                "fetch_auto_scraped_props",
                f"No {sport} props in Gist (has: {set(p.get('Sport','') for p in all_props)})",
                "warning"
            )
        
        return props
    
    except requests.Timeout:
        log_error_to_session(
            "fetch_auto_scraped_props",
            "Gist API request timed out (10s)",
            "error"
        )
        return []
    
    except Exception as e:
        log_error_to_session(
            "fetch_auto_scraped_props",
            f"Unexpected error: {str(e)[:100]}",
            "error"
        )
        logger.error(f"fetch_auto_scraped_props failed: {e}", exc_info=True)
        return []


def scrape_prizepicks_with_gist_fallback(sport: str) -> list:
    """
    Try to scrape PrizePicks directly. If it fails, use Gist fallback.
    
    Fallback chain:
    1. scrape_prizepicks() — direct ScrapeOps proxy
    2. fetch_auto_scraped_props() — Gist from local scraper
    3. [] — empty if both fail
    
    This replaces direct scrape_prizepicks() call in load_sport_data().
    """
    pp_props = scrape_prizepicks(sport)  # Original direct scrape
    
    if pp_props:
        st.session_state["pp_source"] = "prizepicks_direct"
        st.session_state["pp_status"] = "ok"
        return pp_props
    
    # PrizePicks direct failed → try Gist fallback
    log_error_to_session(
        "scrape_prizepicks_with_gist_fallback",
        f"PrizePicks direct scraping failed for {sport}, trying Gist fallback...",
        "warning"
    )
    
    gist_props = fetch_auto_scraped_props(sport)
    
    if gist_props:
        st.session_state["pp_source"] = "gist_scraper"
        st.session_state["pp_status"] = "ok_gist"
        log_error_to_session(
            "scrape_prizepicks_with_gist_fallback",
            f"✅ Using {len(gist_props)} PrizePicks props from Gist",
            "info"
        )
        return gist_props
    
    # Both failed
    st.session_state["pp_status"] = "unavailable"
    st.session_state["pp_source"] = "none"
    log_error_to_session(
        "scrape_prizepicks_with_gist_fallback",
        f"PrizePicks unavailable (direct failed, Gist empty for {sport})",
        "error"
    )
    return []


def update_sidebar_status_message():
    """
    Update sidebar to show which props source was actually used.
    Call this AFTER load_sport_data() completes.
    """
    pp_source = st.session_state.get("pp_source", "none")
    pp_status = st.session_state.get("pp_status", "unknown")
    
    status_map = {
        "prizepicks_direct": "🟢 PrizePicks (direct scrape)",
        "gist_scraper": "🟡 PrizePicks (local scraper via Gist)",
        "unavailable": "🔴 PrizePicks unavailable",
        "none": "⚠️ No props source available",
    }
    
    status_msg = status_map.get(pp_source, f"? {pp_source}")
    
    with st.sidebar:
        st.markdown(f"**Props source:** {status_msg}")
        if pp_source == "gist_scraper":
            st.info("✅ Using local scraper (Gist). Remember to keep betcouncil_auto_scraper.py running on your PC!")


# ═══════════════════════════════════════════════════════════════
# INTEGRATION INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════
#
# 1. Copy all functions from this file into app.py (after imports)
#
# 2. In load_sport_data(), replace:
#      pp_props = scrape_prizepicks(sport)
#    With:
#      pp_props = scrape_prizepicks_with_gist_fallback(sport)
#
# 3. At the END of load_sport_data(), add:
#      update_sidebar_status_message()
#
# 4. Verify: python3 -m py_compile app.py
# 5. Test: Load app and check System tab for error messages
#
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# VSiN INTELLIGENCE — GIST READER
# Reads vsin_intelligence.json pushed by betcouncil_auto_scraper.py
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)
def fetch_vsin_intelligence(sport: str = "MLB") -> dict:
    """
    Fetch VSiN intelligence data from Gist (vsin_intelligence.json).
    Returns unified dict with lines, splits, makinen, team_summary,
    power_ratings, rlm_alerts, ats_signals.
    TTL: 10 minutes.
    """
    empty = {
        "sport": sport, "timestamp": None,
        "lines": [], "splits": [], "merged": [],
        "makinen": [], "team_summary": [], "dk_splits": [],
        "power_ratings": [], "rlm_alerts": [], "ats_signals": {},
    }
    try:
        if not GITHUB_TOKEN or not GITHUB_GIST_ID:
            return empty

        r = requests.get(
            f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            timeout=10,
        )
        if r.status_code != 200:
            return empty

        files = r.json().get("files", {})
        if "vsin_intelligence.json" not in files:
            return empty

        file_obj = files["vsin_intelligence.json"]
        if file_obj.get("size", 0) > 900000:
            raw = requests.get(file_obj["raw_url"], timeout=10)
            data = raw.json() if raw.status_code == 200 else empty
        else:
            content = file_obj.get("content", "")
            data = json.loads(content) if content else empty

        # Filter to requested sport
        if data.get("sport", "").upper() != sport.upper():
            return empty
        return data

    except Exception as e:
        log_error_to_session("fetch_vsin_intelligence", str(e), "warning")
        return empty


def get_vsin_team_signal(vsin_data: dict, team_name: str) -> dict:
    """
    Look up VSiN signals for a specific team.
    Returns dict with power_rating, makinen_proj, ats_hot/cold, ou_lean.
    """
    result = {
        "power_rating": None, "pr_rank": None,
        "starter_rating": None, "bullpen_rating": None,
        "ml_roi_pct": None, "rl_roi_pct": None, "ou_roi_pct": None,
        "ats_hot": False, "ats_cold": False, "ou_lean": None,
    }

    # Power ratings lookup
    for team in vsin_data.get("power_ratings", []):
        if team.get("team", "").lower() in team_name.lower() or \
           team_name.lower() in team.get("team", "").lower():
            result["power_rating"]   = team.get("power_rating")
            result["pr_rank"]        = team.get("pr_rank")
            result["starter_rating"] = team.get("starter_rating")
            result["bullpen_rating"] = team.get("bullpen_rating")
            break

    # Team summary lookup
    for team in vsin_data.get("team_summary", []):
        if team.get("team", "").lower() in team_name.lower() or \
           team_name.lower() in team.get("team", "").lower():
            result["ml_roi_pct"] = team.get("ml_roi_pct")
            result["rl_roi_pct"] = team.get("rl_roi_pct")
            result["ou_roi_pct"] = team.get("ou_roi_pct")
            break

    # ATS signals
    signals = vsin_data.get("ats_signals", {})
    result["ats_hot"]  = team_name in signals.get("ats_hot", [])
    result["ats_cold"] = team_name in signals.get("ats_cold", [])
    if team_name in signals.get("over_lean", []):
        result["ou_lean"] = "over"
    elif team_name in signals.get("under_lean", []):
        result["ou_lean"] = "under"

    return result


def get_vsin_game_signal(vsin_data: dict, away_team: str, home_team: str) -> dict:
    """
    Look up VSiN signals for a specific matchup.
    Returns dict with rlm, makinen projections, public splits.
    """
    result = {
        "rlm_detected": False, "rlm_direction": None,
        "rlm_strength": None, "public_pct": None,
        "away_score_proj": None, "home_score_proj": None,
        "projected_total": None, "makinen_favorite": None,
        "spread_bet_pct_home": None, "ml_bet_pct_home": None,
        "handle_pct_home": None,
    }

    from difflib import SequenceMatcher
    def sim(a, b):
        return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()

    # RLM from merged
    for g in vsin_data.get("rlm_alerts", []):
        if sim(g.get("away_team",""), away_team) > 0.6 or \
           sim(g.get("home_team",""), home_team) > 0.6:
            rlm = g.get("rlm", {})
            result["rlm_detected"]  = rlm.get("rlm_detected", False)
            result["rlm_direction"] = rlm.get("rlm_direction")
            result["rlm_strength"]  = rlm.get("rlm_strength")
            result["public_pct"]    = rlm.get("public_pct_vs_line")
            break

    # Splits from merged
    for g in vsin_data.get("merged", []):
        ah = sim(g.get("away_team",""), away_team)
        hh = sim(g.get("home_team",""), home_team)
        if ah > 0.6 and hh > 0.6:
            result["spread_bet_pct_home"] = g.get("spread_bet_pct_home")
            result["ml_bet_pct_home"]     = g.get("ml_bet_pct_home")
            result["handle_pct_home"]     = g.get("spread_handle_pct_home")
            break

    # Makinen projections
    for g in vsin_data.get("makinen", []):
        ah = sim(g.get("away_team",""), away_team)
        hh = sim(g.get("home_team",""), home_team)
        if ah > 0.5 and hh > 0.5:
            result["away_score_proj"]  = g.get("away_score_proj")
            result["home_score_proj"]  = g.get("home_score_proj")
            result["projected_total"]  = g.get("projected_total")
            result["makinen_favorite"] = g.get("makinen_favorite")
            break

    return result

def fetch_vsin_picks_and_ratings(sport: str = "MLB", mode: str = "today") -> dict:
    """
    Module-level callable for VSiNPicksAndRatings.
    Wraps VSiNPicksAndRatings.scrape_picks() and scrape_power_ratings() and
    returns a unified dict so app.py callers don't need to import the class
    directly.

    Returns:
        {
            "picks":          list of pro-pick dicts,
            "power_ratings":  list of Makinen power-rating dicts,
            "ratings_lookup": dict keyed by team name for O(1) access,
            "consensus":      dict keyed by game_id with consensus direction,
            "sport":          the requested sport string,
        }
    On any failure returns the same shape with empty collections.
    """
    empty = {
        "picks": [], "power_ratings": [],
        "ratings_lookup": {}, "consensus": {}, "sport": sport,
    }
    try:
        from vsin_picks_and_ratings import (
            VSiNPicksAndRatings,
            picks_consensus,
            power_ratings_lookup,
        )
        scraper = VSiNPicksAndRatings()
        picks   = scraper.scrape_picks(mode=mode, sport_filter=sport)
        ratings = scraper.scrape_power_ratings(sport=sport)
        return {
            "picks":          picks,
            "power_ratings":  ratings,
            "ratings_lookup": power_ratings_lookup(ratings),
            "consensus":      picks_consensus(picks, sport),
            "sport":          sport,
        }
    except Exception as e:
        log_error_to_session("fetch_vsin_picks_and_ratings", str(e), "warning")
        return empty


def fetch_vsin_pro_picks(sport: str = "MLB", mode: str = "today") -> list:
    """
    Playwright-backed VSiN Pro Picks fetcher for BetCouncil.

    Wraps fetch_vsin_propicks_playwright() from vsin_picks_and_ratings with
    Streamlit-friendly error handling and falls back to the static HTTP path
    (VSiNPicksAndRatings.scrape_picks) if Playwright is unavailable.

    Args:
        sport: Sport filter code, e.g. "MLB", "NBA", "NFL" (default "MLB").
        mode:  "today" (today's picks) or "active" (all pending picks).

    Returns:
        List of pick dicts:
          { sport, expert_name, expert_id, source_show, posted_date,
            pick_date, game_time, game_id, result, record_w, record_l,
            is_player_prop, is_pending, book,
            pick_text, player, team, bet_type, direction,
            line, odds, units, prop_stat, scraped_at, source }
        Returns [] on any failure.
    """
    try:
        from vsin_picks_and_ratings import (
            fetch_vsin_propicks_playwright,
            PROPICKS_URLS,
            VSiNPicksAndRatings,
        )
        url = PROPICKS_URLS.get(mode, PROPICKS_URLS.get("today"))
        picks = fetch_vsin_propicks_playwright(url=url, sport_filter=sport.upper())
        if picks:
            return picks
        # Playwright returned nothing — fall back to static HTTP scraper
        scraper = VSiNPicksAndRatings()
        return scraper.scrape_picks(mode=mode, sport_filter=sport.upper())
    except Exception as _e:
        log_error_to_session("fetch_vsin_pro_picks", str(_e)[:200], "warning")
        return []
