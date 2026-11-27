"""Dated NFL game logs from the lab's existing ESPN provider.

No season-average or first-search-result identity fallback is permitted.
"""
import re
from datetime import date

import requests
import streamlit as st


NFL_STATS = {
    "passyds": ("passingYards",), "passingyards": ("passingYards",),
    "passyards": ("passingYards",),
    "rushyds": ("rushingYards",), "rushingyards": ("rushingYards",),
    "rushyards": ("rushingYards",),
    "recyds": ("receivingYards",), "receivingyards": ("receivingYards",),
    "recyards": ("receivingYards",),
    "receptions": ("receptions",), "rec": ("receptions",),
    "passtd": ("passingTouchdowns",), "passingtds": ("passingTouchdowns",),
    "passcompletions": ("completions",), "passingcompletions": ("completions",),
    "passattempts": ("passingAttempts",), "passingattempts": ("passingAttempts",),
    "rushattempts": ("rushingAttempts",), "rushingattempts": ("rushingAttempts",),
    "rushrecyds": ("rushingYards", "receivingYards"),
    "rushingreceivingyards": ("rushingYards", "receivingYards"),
    "passrushyds": ("passingYards", "rushingYards"),
    "passingrushingyards": ("passingYards", "rushingYards"),
}


def parse_nfl_gamelog(payload):
    """ESPN common-v3 stats are positional: resolve through names, not labels."""
    names = payload.get("names", [])
    events = payload.get("events", {})
    rows = []
    for season_type in payload.get("seasonTypes", []):
        # Preseason stats must not inflate regular-season evidence.
        if not (str(season_type.get("type", "")) == "2"
                or "regular season" in season_type.get("displayName", "").lower()):
            continue
        for category in season_type.get("categories", []):
            for event in category.get("events", []):
                event_id = str(event.get("eventId", ""))
                meta = events.get(event_id, {})
                if not meta.get("gameDate") or meta.get("gameResult") not in ("W", "L", "T"):
                    continue
                row = {"date": meta["gameDate"], "game_id": event_id}
                for name, value in zip(names, event.get("stats", [])):
                    try:
                        row[name] = float(str(value).replace(",", ""))
                    except (TypeError, ValueError):
                        pass
                rows.append(row)
    return rows


@st.cache_data(ttl=1800, show_spinner=False)
def _request_logs(athlete_id, season):
    response = requests.get(
        f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{athlete_id}/gamelog",
        params={"season": season}, timeout=15,
    )
    response.raise_for_status()
    return parse_nfl_gamelog(response.json())


def fetch_nfl_logs(core, player, year):
    # The existing registry is exact-name keyed, not a fuzzy search result.
    registry = getattr(core, "ESPN_ATHLETE_IDS", {}).get("NFL", {})
    normalize = lambda name: re.sub(r"[^a-z]", "", name.lower())
    athlete_id = next((value for name, value in registry.items()
                       if normalize(name) == normalize(player)), None)
    if not athlete_id:
        database = core.fetch_nfl_full_player_database() or {}
        athlete_id = (database.get(core.normalize_name(player)) or {}).get("athlete_id")
        if not athlete_id:
            return []
    # NFL's season year changes in the spring, not on January 1.
    season = year if date.today().month >= 3 else year - 1
    return _request_logs(str(athlete_id), season)
