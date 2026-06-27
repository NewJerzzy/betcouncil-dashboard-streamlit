"""
nfl_pff_grades.py
=================
PFF player grade fetcher for BetCouncil NFL model.

Adapted from kan-ryan/pff_grades_fetches.

Endpoint: https://premium.pff.com/api/v1/facet/offense/summary?game_id=X
Auth:      4 session cookies from Chrome DevTools (expire 12-24h)

Usage:
    from nfl_pff_grades import fetch_pff_grades, harvest_pff_cookies, get_pff_game_ids
    grades = fetch_pff_grades(game_id=26200)

Cookie harvest:
    1. Open premium.pff.com and log in
    2. Run harvest_pff_cookies() — Playwright opens browser, captures cookies
    3. Cookies saved to Gist under key pff_tokens (24h TTL)
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
from datetime import datetime, date
from typing import Optional

import requests as _requests

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "nfl")
os.makedirs(CACHE_DIR, exist_ok=True)

PFF_BASE        = "https://premium.pff.com/api/v1"
PFF_OFFENSE_URL = f"{PFF_BASE}/facet/offense/summary"
PFF_DEFENSE_URL = f"{PFF_BASE}/facet/defense/summary"
PFF_TEAMS_URL   = f"{PFF_BASE}/teams/summary"
PFF_LEAGUE      = "nfl"

# Grade columns from sample CSV
PFF_GRADE_COLS = [
    "player", "player_id", "position", "franchise_id",
    "grades_offense", "grades_pass", "grades_pass_block",
    "grades_pass_route", "grades_run", "grades_run_block",
    "grades_defense", "grades_tackle", "grades_prsh", "grades_coverage",
    "snap_counts_total", "snap_counts_pass", "snap_counts_run",
    "snap_counts_pass_route", "snap_counts_pass_block",
    "status",
]

_http = _requests.Session()
_http.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://premium.pff.com/",
})


# ── Cookie management ─────────────────────────────────────────────────────────

def _load_pff_cookies() -> dict:
    """Load PFF cookies: Gist → local cache → empty."""
    # Try local cache first
    cache_path = os.path.join(CACHE_DIR, "pff_cookies.json")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 20:
            try:
                with open(cache_path) as f:
                    return json.load(f)
            except Exception:
                pass

    # Try Gist
    try:
        from app_fixes import load_from_gist
        gist_data = load_from_gist("pff_tokens", None)
        if gist_data and gist_data.get("_premium_key"):
            try:
                with open(cache_path, "w") as f:
                    json.dump(gist_data, f)
            except Exception:
                pass
            return gist_data
    except Exception:
        pass

    # Try st.secrets
    try:
        import streamlit as st
        cookies = {
            "_premium_key":        st.secrets.get("PFF_PREMIUM_KEY", ""),
            "c_groot_access_token":  st.secrets.get("PFF_ACCESS_TOKEN", ""),
            "c_groot_access_ts":     st.secrets.get("PFF_ACCESS_TS", ""),
            "c_groot_refresh_token": st.secrets.get("PFF_REFRESH_TOKEN", ""),
        }
        if cookies["_premium_key"]:
            return cookies
    except Exception:
        pass

    return {}


def _save_pff_cookies(cookies: dict) -> None:
    """Save cookies to local cache and Gist."""
    cache_path = os.path.join(CACHE_DIR, "pff_cookies.json")
    try:
        with open(cache_path, "w") as f:
            json.dump(cookies, f)
    except Exception:
        pass

    try:
        from app_fixes import save_to_gist
        cookies["captured_at"] = datetime.now().isoformat()
        save_to_gist("pff_tokens", cookies)
    except Exception:
        pass


# ── Playwright harvester ──────────────────────────────────────────────────────

def harvest_pff_cookies(headless: bool = False) -> dict:
    """
    Launch Playwright browser, log into PFF, capture session cookies.
    Saves to Gist under key pff_tokens.

    Returns cookie dict or {} on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright not installed — run: pip install playwright && playwright install chromium")
        return {}

    cookies_found = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = ctx.new_page()

        def on_request(request):
            if "premium.pff.com/api" in request.url:
                raw = request.all_headers()
                cookie_str = raw.get("cookie", "")
                if cookie_str and "_premium_key" in cookie_str:
                    for part in cookie_str.split(";"):
                        part = part.strip()
                        if "=" in part:
                            k, v = part.split("=", 1)
                            k = k.strip()
                            if k in ("_premium_key", "c_groot_access_token",
                                     "c_groot_access_ts", "c_groot_refresh_token"):
                                cookies_found[k] = v.strip()

        page.on("request", on_request)

        logger.info("[PFF] Opening premium.pff.com — log in if prompted")
        page.goto("https://premium.pff.com/nfl/overall", wait_until="domcontentloaded", timeout=60000)

        # Wait up to 90s for cookies to appear
        for _ in range(90):
            if len(cookies_found) >= 2:
                break
            time.sleep(1)

        browser.close()

    if cookies_found:
        _save_pff_cookies(cookies_found)
        logger.info("[PFF] Captured %d cookies", len(cookies_found))
    else:
        logger.warning("[PFF] No cookies captured — did you log in?")

    return cookies_found


# ── PFF API fetchers ──────────────────────────────────────────────────────────

def _pff_get(url: str, params: dict, cookies: dict, retries: int = 2) -> Optional[dict]:
    """Make authenticated GET to PFF API."""
    for attempt in range(retries + 1):
        try:
            r = _http.get(url, params=params, cookies=cookies, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 401:
                logger.warning("[PFF] 401 — cookies expired, triggering harvest")
                new_cookies = harvest_pff_cookies()
                if new_cookies:
                    cookies.update(new_cookies)
                    continue
                return None
            logger.warning("[PFF] HTTP %s for %s", r.status_code, url)
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                logger.warning("[PFF] Request error: %s", e)
    return None


def fetch_pff_grades(game_id: int, facet: str = "offense") -> list[dict]:
    """
    Fetch PFF player grades for a single game.

    Args:
        game_id: PFF game ID (integer)
        facet:   "offense" or "defense"

    Returns:
        List of player grade dicts matching PFF_GRADE_COLS schema.
    """
    cache_path = os.path.join(CACHE_DIR, f"pff_{facet}_{game_id}.pkl")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass

    cookies = _load_pff_cookies()
    if not cookies.get("_premium_key"):
        logger.warning("[PFF] No cookies — run harvest_pff_cookies() first")
        return []

    url = PFF_OFFENSE_URL if facet == "offense" else PFF_DEFENSE_URL
    data = _pff_get(url, {"game_id": game_id}, cookies)
    if not data:
        return []

    # Both offense and defense return list under same-name key
    key = f"{facet}_summary"
    grades = data.get(key, data.get("offense_summary", []))

    if grades:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(grades, f)
        except Exception:
            pass

    logger.info("[PFF] game %s %s: %d player grades", game_id, facet, len(grades))
    return grades


def fetch_pff_game_grades(game_id: int) -> dict:
    """
    Fetch both offense and defense grades for a game.
    Returns {"offense": [...], "defense": [...], "game_id": game_id}
    """
    return {
        "game_id":  game_id,
        "offense":  fetch_pff_grades(game_id, "offense"),
        "defense":  fetch_pff_grades(game_id, "defense"),
    }


def get_pff_game_ids(franchise_id: int, season: int,
                     weeks: Optional[list[int]] = None) -> list[int]:
    """
    Get PFF game IDs for a team/season.

    Args:
        franchise_id: PFF franchise ID (e.g. 22=Chiefs, 9=Cowboys)
        season:       NFL season year
        weeks:        List of week numbers (default: all)

    Returns:
        List of PFF game IDs.
    """
    cookies = _load_pff_cookies()
    if not cookies.get("_premium_key"):
        return []

    week_str = ",".join(str(w) for w in (weeks or range(0, 23)))
    data = _pff_get(PFF_TEAMS_URL, {
        "league": PFF_LEAGUE, "season": season,
        "franchise_id": franchise_id, "week": week_str,
    }, cookies)

    if not data:
        return []

    game_ids = []
    for game in data.get("team_summary", []):
        gid = game.get("game_id")
        if gid and gid not in game_ids:
            game_ids.append(int(gid))

    return game_ids


# ── Grade aggregation for model features ─────────────────────────────────────

# PFF franchise IDs for all 32 NFL teams
PFF_FRANCHISE_IDS = {
    "ARI": 1,  "ATL": 2,  "BAL": 33, "BUF": 3,  "CAR": 29, "CHI": 4,
    "CIN": 5,  "CLE": 6,  "DAL": 7,  "DEN": 8,  "DET": 9,  "GB": 10,
    "HOU": 34, "IND": 11, "JAX": 30, "KC": 22,  "LAC": 24, "LAR": 14,
    "LV": 13,  "MIA": 15, "MIN": 16, "NE": 17,  "NO": 18,  "NYG": 19,
    "NYJ": 20, "PHI": 21, "PIT": 23, "SEA": 25, "SF": 26,  "TB": 27,
    "TEN": 28, "WAS": 32,
}


def build_pff_team_grades(team_abbr: str, season: int,
                           last_n_games: int = 8) -> dict:
    """
    Build rolling PFF grade averages for a team.

    Returns dict with avg grades for each PFF category over last N games.
    Matches the feature schema expected by nfl_features.py (PFF_STATS).
    """
    franchise_id = PFF_FRANCHISE_IDS.get(team_abbr)
    if not franchise_id:
        logger.warning("[PFF] Unknown team: %s", team_abbr)
        return {}

    game_ids = get_pff_game_ids(franchise_id, season)
    if not game_ids:
        return {}

    # Use most recent N games
    recent_ids = game_ids[-last_n_games:]

    # Accumulate grades
    grade_sums: dict[str, list[float]] = {}
    for gid in recent_ids:
        grades = fetch_pff_grades(gid, "offense")
        for player in grades:
            fid = player.get("franchise_id")
            if str(fid) != str(franchise_id):
                continue
            for col in ["grades_offense", "grades_pass", "grades_pass_block",
                        "grades_pass_route", "grades_run", "grades_run_block"]:
                val = player.get(col)
                if val is not None:
                    try:
                        grade_sums.setdefault(col, []).append(float(val))
                    except (ValueError, TypeError):
                        pass

        def_grades = fetch_pff_grades(gid, "defense")
        for player in def_grades:
            fid = player.get("franchise_id")
            if str(fid) != str(franchise_id):
                continue
            for col in ["grades_defense", "grades_tackle", "grades_prsh", "grades_coverage"]:
                val = player.get(col)
                if val is not None:
                    try:
                        grade_sums.setdefault(col, []).append(float(val))
                    except (ValueError, TypeError):
                        pass

    # Average each category
    result = {"team": team_abbr, "season": season, "games_graded": len(recent_ids)}
    for col, vals in grade_sums.items():
        result[f"{col}_avg"] = sum(vals) / len(vals) if vals else 0.0

    # Map to sports-quant feature names
    mapping = {
        "grades_offense_avg":     "off",
        "grades_pass_avg":        "pass",
        "grades_pass_block_avg":  "pblk",
        "grades_pass_route_avg":  "recv",
        "grades_run_avg":         "run",
        "grades_run_block_avg":   "rblk",
        "grades_defense_avg":     "def",
        "grades_tackle_avg":      "tack",
        "grades_prsh_avg":        "prsh",
        "grades_coverage_avg":    "cov",
    }
    for pff_key, sq_key in mapping.items():
        result[sq_key] = result.get(pff_key, 0.0)

    return result


def build_pff_game_features(home_team: str, away_team: str,
                             season: int, last_n: int = 8) -> dict:
    """
    Build PFF feature differentials for a matchup.
    Matches the feature schema in nfl_features.py.
    """
    home_grades = build_pff_team_grades(home_team, season, last_n)
    away_grades = build_pff_team_grades(away_team, season, last_n)

    pff_stats = ["off", "pass", "pblk", "recv", "run", "rblk", "def", "tack", "prsh", "cov"]
    features  = {}

    for stat in pff_stats:
        h = home_grades.get(stat, 0.0)
        a = away_grades.get(stat, 0.0)
        features[f"home-{stat}-avg"] = h
        features[f"away-{stat}-avg"] = a
        features[f"{stat}_diff"]     = h - a  # positive = home advantage

    return features
