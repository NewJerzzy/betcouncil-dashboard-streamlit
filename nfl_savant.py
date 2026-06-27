"""
nfl_savant.py
=============
nflsavant.com scraper for BetCouncil NFL model.

Provides route data and snap counts not available in nflfastR.
No login required — public site.

Data available:
  - Snap counts per player per week (offense/defense/ST snap %)
  - Play-by-play with route type (SLANT, GO, CROSS, CURL, OUT, FLAT, SCREEN)
  - Formation data (SHOTGUN, SINGLEBACK, I_FORM, etc.)
  - Pass type (SHORT_LEFT, DEEP_MIDDLE, etc.)

Usage:
    from nfl_savant import fetch_savant_snaps, fetch_savant_routes, get_player_route_profile
    snaps = fetch_savant_snaps(2024)
    routes = fetch_savant_routes(2024)
    profile = get_player_route_profile("CeeDee Lamb", "DAL", 2024)
"""

from __future__ import annotations

import io
import logging
import os
import pickle
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "nfl")
os.makedirs(CACHE_DIR, exist_ok=True)

SAVANT_BASE = "https://nflsavant.com"

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://nflsavant.com/",
})


def _safe_float(val, default=0.0):
    try:
        return float(str(val).replace("%","").strip()) if val not in (None,"","N/A") else default
    except Exception:
        return default


# ── Snap counts ───────────────────────────────────────────────────────────────

def fetch_savant_snaps(season: int, week: Optional[int] = None) -> list[dict]:
    """
    Fetch snap count data from nflsavant.com.

    Args:
        season: NFL season year (e.g. 2024)
        week:   Specific week (None = full season)

    Returns list of:
        {player, team, position, week, season,
         offense_snaps, offense_pct,
         defense_snaps, defense_pct,
         st_snaps, st_pct}
    """
    cache_key = f"savant_snaps_{season}{'_w'+str(week) if week else ''}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")

    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 6:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not available")
        return []

    params = {"year": season, "f": "csv"}
    if week:
        params["week"] = week

    url = f"{SAVANT_BASE}/snap_counts.php"
    logger.info("[nflsavant] Fetching snap counts %d week=%s", season, week or "all")

    try:
        r = _session.get(url, params=params, timeout=30)
        if r.status_code != 200:
            logger.warning("[nflsavant] snap counts HTTP %s", r.status_code)
            return []

        df = pd.read_csv(io.StringIO(r.text))

        # Normalize columns
        col_map = {
            "Name": "player", "name": "player",
            "Team": "team", "team": "team",
            "Pos": "position", "pos": "position", "Position": "position",
            "Wk": "week", "wk": "week", "Week": "week",
            "OSnaps": "offense_snaps", "o_snaps": "offense_snaps",
            "OPct": "offense_pct", "o_pct": "offense_pct",
            "DSnaps": "defense_snaps", "d_snaps": "defense_snaps",
            "DPct": "defense_pct", "d_pct": "defense_pct",
            "STSnaps": "st_snaps", "st_snaps": "st_snaps",
            "STPct": "st_pct", "st_pct": "st_pct",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df["season"] = season

        # Convert pct columns (may be "75%" or "0.75" or "75")
        for col in ["offense_pct", "defense_pct", "st_pct"]:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: _safe_float(x) / 100
                                        if _safe_float(x) > 1 else _safe_float(x))

        records = df.to_dict("records")
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(records, f)
        except Exception:
            pass

        logger.info("[nflsavant] %d snap count records", len(records))
        return records

    except Exception as e:
        logger.warning("[nflsavant] snap counts error: %s", e)
        return []


# ── Play-by-play with routes ───────────────────────────────────────────────────

def fetch_savant_routes(season: int) -> list[dict]:
    """
    Fetch play-by-play data with route types from nflsavant.com.
    This is the primary source for receiver route profiles.

    Returns list of passing play dicts with:
        {game_id, date, week, offense_team, defense_team,
         quarterback, receiver, route, pass_type, yards_gained,
         formation, down, yards_to_go, result}
    """
    cache_path = os.path.join(CACHE_DIR, f"savant_routes_{season}.pkl")

    if os.path.exists(cache_path):
        age_days = (time.time() - os.path.getmtime(cache_path)) / 86400
        if age_days < 1:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    try:
        import pandas as pd
    except ImportError:
        return []

    url = f"{SAVANT_BASE}/pbp_data.php"
    logger.info("[nflsavant] Fetching PBP route data for %d...", season)

    try:
        r = _session.get(url, params={"year": season}, timeout=120)
        if r.status_code != 200:
            logger.warning("[nflsavant] PBP HTTP %s", r.status_code)
            return []

        df = pd.read_csv(io.StringIO(r.text))

        # Filter to passing plays with route data
        if "PlayType" in df.columns:
            df = df[df["PlayType"].str.upper().isin(["PASS", "SACK", "SCRAMBLE"])]
        if "Route" in df.columns:
            df = df[df["Route"].notna() & (df["Route"] != "")]

        # Normalize
        col_map = {
            "GameId": "game_id", "GameDate": "date",
            "OffenseTeam": "offense_team", "DefenseTeam": "defense_team",
            "QuarterbackName": "quarterback", "ReceiverName": "receiver",
            "TargetName": "receiver",
            "Route": "route", "PassType": "pass_type",
            "Formation": "formation", "YardsGained": "yards_gained",
            "Down": "down", "ToGo": "yards_to_go",
            "IsComplete": "complete", "IsTouchdown": "touchdown",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Add week from game_id or date if not present
        if "week" not in df.columns and "game_id" in df.columns:
            # nflsavant game IDs encode week: e.g. 2024_01_ATL_PHI
            df["week"] = df["game_id"].astype(str).str.extract(r"_(\d{2})_").astype(float)

        df["season"] = season

        records = df.to_dict("records")
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(records, f)
        except Exception:
            pass

        logger.info("[nflsavant] %d passing plays with route data", len(records))
        return records

    except Exception as e:
        logger.warning("[nflsavant] routes error: %s", e)
        return []


# ── Player route profile ──────────────────────────────────────────────────────

def get_player_route_profile(player_name: str, team: str,
                              season: int,
                              routes: Optional[list] = None) -> dict:
    """
    Build route usage profile for a receiver.

    Returns:
        {player, team, season, games, total_routes,
         route_mix: {SLANT: 0.15, GO: 0.12, ...},
         top_route: "SLANT",
         yards_per_route: float,
         target_rate: float,
         catch_rate: float,
         deep_pct: float,   # GO + POST routes (air yards > 15)
         short_pct: float,  # SLANT + FLAT + SCREEN
        }
    """
    if routes is None:
        routes = fetch_savant_routes(season)

    name_lower = player_name.lower().strip()
    player_plays = [
        p for p in routes
        if name_lower in str(p.get("receiver", "")).lower()
        and str(p.get("offense_team", "")) == team
    ]

    if not player_plays:
        return {"player": player_name, "team": team, "season": season,
                "games": 0, "total_routes": 0, "route_mix": {},
                "top_route": "", "yards_per_route": 0.0,
                "target_rate": 0.0, "catch_rate": 0.0,
                "deep_pct": 0.0, "short_pct": 0.0}

    # Count routes
    route_counts: dict[str, int] = {}
    total_yards = 0.0
    completions = 0
    touchdowns  = 0

    for play in player_plays:
        route = str(play.get("route", "OTHER")).upper().strip()
        route_counts[route] = route_counts.get(route, 0) + 1
        total_yards += _safe_float(play.get("yards_gained", 0))
        if play.get("complete") or play.get("IsComplete"):
            completions += 1
        if play.get("touchdown") or play.get("IsTouchdown"):
            touchdowns += 1

    total = max(1, len(player_plays))
    route_mix = {r: c / total for r, c in sorted(route_counts.items(),
                                                   key=lambda x: x[1], reverse=True)}

    deep_routes  = {"GO", "POST", "CORNER", "SEAM"}
    short_routes = {"SLANT", "FLAT", "SCREEN", "QUICK", "CURL", "STICK"}

    deep_pct  = sum(v for r, v in route_mix.items() if r in deep_routes)
    short_pct = sum(v for r, v in route_mix.items() if r in short_routes)

    # Unique games
    games = len(set(p.get("game_id", p.get("date", "")) for p in player_plays))

    return {
        "player":          player_name,
        "team":            team,
        "season":          season,
        "games":           games,
        "total_routes":    total,
        "route_mix":       route_mix,
        "top_route":       max(route_counts, key=route_counts.get) if route_counts else "",
        "yards_per_route": total_yards / total,
        "catch_rate":      completions / total,
        "td_rate":         touchdowns / total,
        "deep_pct":        deep_pct,
        "short_pct":       short_pct,
        "touchdowns":      touchdowns,
    }


def get_team_snap_leaders(team: str, season: int,
                          position: Optional[str] = None,
                          snaps: Optional[list] = None) -> list[dict]:
    """
    Get snap count leaders for a team, sorted by offense snap %.
    Useful for identifying starting lineup and usage hierarchy.
    """
    if snaps is None:
        snaps = fetch_savant_snaps(season)

    team_snaps = [
        s for s in snaps
        if str(s.get("team", "")) == team
        and (position is None or str(s.get("position", "")).upper() == position.upper())
    ]

    # Average across weeks
    player_avgs: dict[str, dict] = {}
    for s in team_snaps:
        name = s.get("player", "")
        if name not in player_avgs:
            player_avgs[name] = {
                "player": name, "team": team, "season": season,
                "position": s.get("position", ""),
                "offense_pct_vals": [], "games": 0,
            }
        player_avgs[name]["offense_pct_vals"].append(_safe_float(s.get("offense_pct", 0)))
        player_avgs[name]["games"] += 1

    result = []
    for name, data in player_avgs.items():
        vals = data.pop("offense_pct_vals")
        data["offense_snap_pct"] = sum(vals) / len(vals) if vals else 0.0
        result.append(data)

    return sorted(result, key=lambda x: x["offense_snap_pct"], reverse=True)
