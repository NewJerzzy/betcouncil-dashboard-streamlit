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
        GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
        GITHUB_GIST_ID = st.secrets.get("GITHUB_GIST_ID", "")
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
