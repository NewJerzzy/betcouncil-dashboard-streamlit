"""
nfl_features.py
===============
NFL feature engineering pipeline for BetCouncil.

Adapted from thadhutch/sports-quant with additions for BetCouncil's
prop and game-line edge model.

Feature set:
  - PFF grade ranks (11 categories × home/away = 22 features)
  - nflfastR EPA per play (pass/rush, offense/defense)
  - Rolling season averages with season-reset logic
  - Injury impact scores
  - Weather/stadium factors

Data sources (all free, no API key):
  - nflverse GitHub releases (nflfastR play-by-play CSVs)
  - ESPN NFL API (roster, injuries, schedule)
  - Pro Football Reference (box scores via HTTP)
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
from datetime import date, datetime
from functools import lru_cache
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache", "nfl")
os.makedirs(CACHE_DIR, exist_ok=True)

ESPN_NFL_BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
NFLVERSE_BASE = "https://github.com/nflverse/nflverse-data/releases/download"

# PFF grade categories (from sports-quant)
PFF_STATS = ["off", "pass", "pblk", "recv", "run", "rblk", "def", "rdef", "tack", "prsh", "cov"]

# NFL team abbreviation → canonical name
NFL_TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LAC": "Los Angeles Chargers", "LAR": "Los Angeles Rams",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

NFL_ABBREV = {v: k for k, v in NFL_TEAMS.items()}

# ── HTTP helper ───────────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})


def _get(url: str, timeout: int = 20, cache_hours: float = 6.0) -> Optional[dict]:
    cache_key = url.replace("/", "_").replace(":", "").replace("?", "_")[:120]
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")

    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < cache_hours:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    try:
        r = _session.get(url, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            try:
                with open(cache_path, "wb") as f:
                    pickle.dump(data, f)
            except Exception:
                pass
            return data
        logger.warning("NFL fetch %s → %s", url, r.status_code)
    except Exception as e:
        logger.warning("NFL fetch error %s: %s", url, e)
    return None


# ── ESPN data fetchers ────────────────────────────────────────────────────────

def fetch_nfl_schedule(season: int, season_type: int = 2) -> list[dict]:
    """
    Fetch NFL schedule from ESPN.
    season_type: 1=preseason, 2=regular, 3=playoffs
    Returns list of game dicts.
    """
    games = []
    week = 1
    while week <= 22:
        url = f"{ESPN_NFL_BASE}/scoreboard?seasontype={season_type}&season={season}&week={week}"
        data = _get(url, cache_hours=1.0)
        if not data:
            break
        events = data.get("events", [])
        if not events:
            break
        for event in events:
            comps = event.get("competitions", [{}])
            comp = comps[0] if comps else {}
            competitors = comp.get("competitors", [])
            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            games.append({
                "game_id":   event.get("id", ""),
                "date":      event.get("date", "")[:10],
                "week":      week,
                "season":    season,
                "home_team": home.get("team", {}).get("abbreviation", ""),
                "away_team": away.get("team", {}).get("abbreviation", ""),
                "home_score": int(home.get("score", 0) or 0),
                "away_score": int(away.get("score", 0) or 0),
                "status":    event.get("status", {}).get("type", {}).get("name", ""),
                "venue":     comp.get("venue", {}).get("fullName", ""),
                "indoor":    comp.get("venue", {}).get("indoor", False),
            })
        week += 1
    logger.info("NFL schedule: %d games for %d season", len(games), season)
    return games


def fetch_nfl_injuries(team_abbr: Optional[str] = None) -> list[dict]:
    """Fetch NFL injuries from ESPN. Returns list of injury dicts."""
    url = f"{ESPN_NFL_BASE}/injuries"
    data = _get(url, cache_hours=0.5)
    if not data:
        return []

    injuries = []
    for team_entry in data.get("injuries", []):
        team = team_entry.get("team", {})
        abbr = team.get("abbreviation", "")
        if team_abbr and abbr != team_abbr:
            continue
        for inj in team_entry.get("injuries", []):
            athlete = inj.get("athlete", {})
            injuries.append({
                "team":     abbr,
                "player":   athlete.get("displayName", ""),
                "position": athlete.get("position", {}).get("abbreviation", ""),
                "status":   inj.get("status", ""),
                "detail":   inj.get("shortComment", ""),
                "sport":    "NFL",
            })
    return injuries


def fetch_nfl_roster(team_abbr: str) -> list[dict]:
    """Fetch NFL roster from ESPN for a team."""
    url = f"{ESPN_NFL_BASE}/teams/{team_abbr}/roster"
    data = _get(url, cache_hours=24.0)
    if not data:
        return []

    players = []
    for group in data.get("athletes", []):
        for player in group.get("items", []):
            players.append({
                "id":       player.get("id", ""),
                "name":     player.get("displayName", ""),
                "position": player.get("position", {}).get("abbreviation", ""),
                "jersey":   player.get("jersey", ""),
                "team":     team_abbr,
                "sport":    "NFL",
            })
    return players


def fetch_nfl_team_stats(season: int) -> dict[str, dict]:
    """
    Fetch season team stats from ESPN.
    Returns {team_abbr: {stat: value}}.
    """
    url = f"{ESPN_NFL_BASE}/teams?season={season}&limit=32"
    data = _get(url, cache_hours=6.0)
    if not data:
        return {}

    stats = {}
    for team in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
        t = team.get("team", {})
        abbr = t.get("abbreviation", "")
        if abbr:
            stats[abbr] = {
                "name":   t.get("displayName", ""),
                "abbr":   abbr,
                "wins":   0,
                "losses": 0,
                "record": t.get("record", {}).get("items", [{}])[0].get("summary", "0-0"),
            }
    return stats


# ── nflfastR play-by-play data ────────────────────────────────────────────────

def fetch_nflfastr_data(season: int) -> list[dict]:
    """
    Pull nflfastR play-by-play CSV from nflverse GitHub releases.
    Parses EPA, air yards, target share, RACR per player per game.

    Returns list of player-game stat dicts.
    """
    cache_path = os.path.join(CACHE_DIR, f"nflfastr_{season}.pkl")

    if os.path.exists(cache_path):
        age_days = (time.time() - os.path.getmtime(cache_path)) / 86400
        if age_days < 1:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    # Try to import pandas for CSV parsing
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not available — skipping nflfastR data")
        return []

    # nflverse data releases URL
    url = f"{NFLVERSE_BASE}/pbp/play_by_play_{season}.csv.gz"
    logger.info("Fetching nflfastR PBP for %d season...", season)

    try:
        r = _session.get(url, timeout=120, stream=True)
        if r.status_code != 200:
            logger.warning("nflfastR %d: HTTP %s", season, r.status_code)
            return []

        import io
        df = pd.read_csv(io.BytesIO(r.content), compression="gzip", low_memory=False,
                         usecols=["game_id", "posteam", "defteam", "week", "season",
                                  "epa", "pass", "rush", "complete_pass",
                                  "air_yards", "yards_after_catch",
                                  "receiver_player_name", "rusher_player_name",
                                  "passer_player_name", "play_type"])

        # Aggregate per player per game
        records = []

        # Passing stats
        pass_df = df[df["play_type"] == "pass"].dropna(subset=["passer_player_name"])
        pass_agg = pass_df.groupby(["game_id", "passer_player_name", "posteam", "week", "season"]).agg(
            pass_attempts=("pass", "sum"),
            completions=("complete_pass", "sum"),
            pass_epa=("epa", "sum"),
            air_yards=("air_yards", "sum"),
        ).reset_index()
        for _, row in pass_agg.iterrows():
            records.append({
                "game_id": row["game_id"], "player": row["passer_player_name"],
                "team": row["posteam"], "week": int(row["week"]), "season": int(row["season"]),
                "stat_type": "passing", "attempts": int(row["pass_attempts"]),
                "completions": int(row["completions"]), "epa": float(row["pass_epa"]),
                "air_yards": float(row["air_yards"]),
            })

        # Rushing stats
        rush_df = df[df["play_type"] == "run"].dropna(subset=["rusher_player_name"])
        rush_agg = rush_df.groupby(["game_id", "rusher_player_name", "posteam", "week", "season"]).agg(
            carries=("rush", "sum"),
            rush_epa=("epa", "sum"),
        ).reset_index()
        for _, row in rush_agg.iterrows():
            records.append({
                "game_id": row["game_id"], "player": row["rusher_player_name"],
                "team": row["posteam"], "week": int(row["week"]), "season": int(row["season"]),
                "stat_type": "rushing", "carries": int(row["carries"]),
                "epa": float(row["rush_epa"]),
            })

        # Receiving stats
        recv_df = df[df["play_type"] == "pass"].dropna(subset=["receiver_player_name"])
        recv_agg = recv_df.groupby(["game_id", "receiver_player_name", "posteam", "week", "season"]).agg(
            targets=("pass", "sum"),
            receptions=("complete_pass", "sum"),
            recv_epa=("epa", "sum"),
            air_yards=("air_yards", "sum"),
            yac=("yards_after_catch", "sum"),
        ).reset_index()
        for _, row in recv_agg.iterrows():
            racr = (float(row["air_yards"]) / max(1, float(row["receptions"]))) if row["receptions"] > 0 else 0.0
            records.append({
                "game_id": row["game_id"], "player": row["receiver_player_name"],
                "team": row["posteam"], "week": int(row["week"]), "season": int(row["season"]),
                "stat_type": "receiving", "targets": int(row["targets"]),
                "receptions": int(row["receptions"]), "epa": float(row["recv_epa"]),
                "air_yards": float(row["air_yards"]), "yac": float(row["yac"]), "racr": racr,
            })

        # Cache result
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(records, f)
        except Exception:
            pass

        logger.info("nflfastR %d: %d player-game records", season, len(records))
        return records

    except Exception as e:
        logger.warning("nflfastR fetch error: %s", e)
        return []


# ── Rolling team stats (PFF-style) ───────────────────────────────────────────

def compute_rolling_team_stats(games: list[dict], epa_records: list[dict]) -> dict[str, dict]:
    """
    Compute rolling season team stats from schedule + EPA data.
    Returns {team_abbr: {stat_key: value}}.

    Stats computed:
      - pass_epa_per_play, rush_epa_per_play (offense/defense)
      - points_per_game, points_allowed_per_game
      - win_pct, home_win_pct, away_win_pct
    """
    team_stats: dict[str, dict] = {}

    # Build EPA lookup by game+team
    epa_by_game: dict[tuple, dict] = {}
    for rec in epa_records:
        key = (rec["game_id"], rec["team"])
        if key not in epa_by_game:
            epa_by_game[key] = {"pass_epa": 0.0, "rush_epa": 0.0, "plays": 0}
        if rec["stat_type"] == "passing":
            epa_by_game[key]["pass_epa"] += rec.get("epa", 0.0)
            epa_by_game[key]["plays"] += rec.get("attempts", 0)
        elif rec["stat_type"] == "rushing":
            epa_by_game[key]["rush_epa"] += rec.get("epa", 0.0)
            epa_by_game[key]["plays"] += rec.get("carries", 0)

    def _init():
        return {
            "games": 0, "wins": 0, "home_games": 0, "home_wins": 0,
            "points_for": 0.0, "points_against": 0.0,
            "pass_epa": 0.0, "rush_epa": 0.0, "def_pass_epa": 0.0, "def_rush_epa": 0.0,
            "season": None,
        }

    for game in sorted(games, key=lambda g: g.get("date", "")):
        home = game.get("home_team", "")
        away = game.get("away_team", "")
        hs = game.get("home_score", 0)
        as_ = game.get("away_score", 0)
        gid = game.get("game_id", "")
        season = game.get("season")

        for team, opp, pts_for, pts_against, is_home in [
            (home, away, hs, as_, True),
            (away, home, as_, hs, False),
        ]:
            if not team:
                continue
            if team not in team_stats or team_stats[team]["season"] != season:
                team_stats[team] = _init()
                team_stats[team]["season"] = season

            s = team_stats[team]
            epa = epa_by_game.get((gid, team), {})
            opp_epa = epa_by_game.get((gid, opp), {})

            s["games"] += 1
            s["points_for"] += pts_for
            s["points_against"] += pts_against
            s["pass_epa"] += epa.get("pass_epa", 0.0)
            s["rush_epa"] += epa.get("rush_epa", 0.0)
            s["def_pass_epa"] += opp_epa.get("pass_epa", 0.0)
            s["def_rush_epa"] += opp_epa.get("rush_epa", 0.0)

            if pts_for > pts_against:
                s["wins"] += 1
            if is_home:
                s["home_games"] += 1
                if pts_for > pts_against:
                    s["home_wins"] += 1

    # Convert to per-game rates
    result = {}
    for team, s in team_stats.items():
        g = max(1, s["games"])
        result[team] = {
            "games_played":          s["games"],
            "win_pct":               s["wins"] / g,
            "home_win_pct":          s["home_wins"] / max(1, s["home_games"]),
            "points_per_game":       s["points_for"] / g,
            "points_allowed_per_game": s["points_against"] / g,
            "pass_epa_per_play":     s["pass_epa"] / g,
            "rush_epa_per_play":     s["rush_epa"] / g,
            "def_pass_epa_per_play": s["def_pass_epa"] / g,
            "def_rush_epa_per_play": s["def_rush_epa"] / g,
            "season":                s["season"],
        }

    return result


# ── Game feature builder ──────────────────────────────────────────────────────

def build_nfl_game_features(home_team: str, away_team: str,
                             season: int, week: int,
                             team_stats: Optional[dict] = None) -> dict:
    """
    Build feature dict for a single NFL game matchup.

    Args:
        home_team:  Team abbreviation (e.g. "KC")
        away_team:  Team abbreviation (e.g. "BUF")
        season:     NFL season year (e.g. 2025)
        week:       NFL week number
        team_stats: Pre-computed rolling stats from compute_rolling_team_stats()
                    If None, fetched fresh.

    Returns:
        Dict of features ready for model input.
    """
    if team_stats is None:
        games = fetch_nfl_schedule(season)
        epa = fetch_nflfastr_data(season)
        team_stats = compute_rolling_team_stats(games, epa)

    home = team_stats.get(home_team, {})
    away = team_stats.get(away_team, {})

    def _s(d, k, default=0.0):
        return float(d.get(k, default))

    features = {
        # Offensive EPA
        "home_pass_epa":     _s(home, "pass_epa_per_play"),
        "away_pass_epa":     _s(away, "pass_epa_per_play"),
        "home_rush_epa":     _s(home, "rush_epa_per_play"),
        "away_rush_epa":     _s(away, "rush_epa_per_play"),
        # Defensive EPA (lower = better defense)
        "home_def_pass_epa": _s(home, "def_pass_epa_per_play"),
        "away_def_pass_epa": _s(away, "def_pass_epa_per_play"),
        "home_def_rush_epa": _s(home, "def_rush_epa_per_play"),
        "away_def_rush_epa": _s(away, "def_rush_epa_per_play"),
        # Scoring
        "home_ppg":          _s(home, "points_per_game"),
        "away_ppg":          _s(away, "points_per_game"),
        "home_papg":         _s(home, "points_allowed_per_game"),
        "away_papg":         _s(away, "points_allowed_per_game"),
        # Win rates
        "home_win_pct":      _s(home, "win_pct"),
        "away_win_pct":      _s(away, "win_pct"),
        "home_home_win_pct": _s(home, "home_win_pct"),
        # Metadata
        "home_team":         home_team,
        "away_team":         away_team,
        "season":            season,
        "week":              week,
        # Differential features (most predictive)
        "ppg_diff":          _s(home, "points_per_game") - _s(away, "points_per_game"),
        "def_ppg_diff":      _s(away, "points_allowed_per_game") - _s(home, "points_allowed_per_game"),
        "pass_epa_diff":     _s(home, "pass_epa_per_play") - _s(away, "pass_epa_per_play"),
        "rush_epa_diff":     _s(home, "rush_epa_per_play") - _s(away, "rush_epa_per_play"),
        "total_epa_diff":    (
            _s(home, "pass_epa_per_play") + _s(home, "rush_epa_per_play") -
            _s(away, "pass_epa_per_play") - _s(away, "rush_epa_per_play")
        ),
    }

    return features


def build_nfl_features(season: int, week: Optional[int] = None) -> list[dict]:
    """
    Build features for all NFL games in a season (or a specific week).

    Returns list of feature dicts, one per game.
    """
    games = fetch_nfl_schedule(season)
    if week is not None:
        games = [g for g in games if g.get("week") == week]

    epa = fetch_nflfastr_data(season)
    team_stats = compute_rolling_team_stats(games, epa)

    features = []
    for game in games:
        feat = build_nfl_game_features(
            game["home_team"], game["away_team"],
            season, game["week"], team_stats
        )
        feat.update({
            "actual_home_score": game.get("home_score", 0),
            "actual_away_score": game.get("away_score", 0),
            "actual_total":      game.get("home_score", 0) + game.get("away_score", 0),
            "actual_spread":     game.get("home_score", 0) - game.get("away_score", 0),
            "game_id":           game.get("game_id", ""),
            "date":              game.get("date", ""),
            "status":            game.get("status", ""),
        })
        features.append(feat)

    return features


# ── Player prop feature builder ───────────────────────────────────────────────

def build_nfl_player_features(player_name: str, team: str,
                               season: int, epa_records: Optional[list] = None) -> dict:
    """
    Build player-level features for prop analysis.

    Returns dict with recent averages and EPA metrics for the player.
    """
    if epa_records is None:
        epa_records = fetch_nflfastr_data(season)

    # Normalize name for matching
    name_lower = player_name.lower().strip()
    player_records = [
        r for r in epa_records
        if r.get("team") == team and name_lower in r.get("player", "").lower()
    ]

    if not player_records:
        return {"player": player_name, "team": team, "season": season, "games": 0}

    # Sort by week
    player_records = sorted(player_records, key=lambda r: r.get("week", 0))
    recent = player_records[-5:]  # L5 games

    def _avg(records, key):
        vals = [r.get(key, 0.0) for r in records if key in r]
        return sum(vals) / max(1, len(vals))

    return {
        "player":          player_name,
        "team":            team,
        "season":          season,
        "games":           len(player_records),
        "stat_type":       player_records[-1].get("stat_type", ""),
        # Season averages
        "epa_per_game":    _avg(player_records, "epa"),
        "air_yards_avg":   _avg(player_records, "air_yards"),
        "targets_avg":     _avg(player_records, "targets"),
        "receptions_avg":  _avg(player_records, "receptions"),
        "carries_avg":     _avg(player_records, "carries"),
        "racr_avg":        _avg(player_records, "racr"),
        # Recent (L5)
        "epa_l5":          _avg(recent, "epa"),
        "air_yards_l5":    _avg(recent, "air_yards"),
        "targets_l5":      _avg(recent, "targets"),
        "receptions_l5":   _avg(recent, "receptions"),
        "carries_l5":      _avg(recent, "carries"),
        # Trend (L5 vs season)
        "epa_trend":       _avg(recent, "epa") - _avg(player_records, "epa"),
    }
