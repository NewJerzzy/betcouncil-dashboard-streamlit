"""
tennis_uts_scraper.py — Player surface performance from
ultimatetennisstatistics.com.

CONFIRMED real format (verified against live page content, Nadal
playerId=4742): the "Surface Breakdown" table contains combined text per
cell like "Hard 77.5% (516-150)" — surface name, win%, and W-L record all
in one string, not separate columns. Parsed via regex below.

Site's only stated restriction: "Please do not perform massive parallel
crawling... hosted on very modest hardware (1 CPU Core, 2 GB RAM)." This
is a politeness request, not a scraping ban (unlike FanGraphs) — honored
here via sequential requests only, generous caching, and a rate-limit
delay between calls.

Public API
----------
fetch_player_surface_performance(player_id) -> dict
    {surface: {win_pct, wins, losses, matches}} or {} on parse failure.
surface_transition_flag(player_id, from_surface, to_surface) -> dict
"""
import re
import time
import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_REQUEST_DELAY_SECONDS = 2.0  # respect their stated small-server hosting
_SURFACES = ("Hard", "Clay", "Grass", "Carpet")

# Confirmed real format: "Hard 77.5% (516-150)"
_SURFACE_PATTERN = re.compile(
    r"\b(Hard|Clay|Grass|Carpet)\s+([\d.]+)%\s*\((\d+)-(\d+)\)"
)

_CACHE = {}  # player_id -> {surface: {...}}


def fetch_player_surface_performance(player_id_or_name) -> dict:
    """
    Parses the real 'Surface Breakdown' table text (confirmed format
    'Hard 77.5% (516-150)') into {surface: {win_pct, wins, losses, matches}}.
    Accepts either a numeric UTS playerId or a player's full name (both
    are confirmed real URL param options on this site).
    """
    if player_id_or_name in _CACHE:
        return _CACHE[player_id_or_name]

    if isinstance(player_id_or_name, int) or str(player_id_or_name).isdigit():
        url = f"https://www.ultimatetennisstatistics.com/playerProfile?playerId={player_id_or_name}&tab=performance"
    else:
        name_param = str(player_id_or_name).replace(" ", "+")
        url = f"https://www.ultimatetennisstatistics.com/playerProfile?name={name_param}&tab=performance"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        time.sleep(_REQUEST_DELAY_SECONDS)  # polite pacing after each call
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        result = {}

        # Search all table cell text for the confirmed real pattern, rather
        # than assuming a specific table index/class (page layout details
        # beyond the confirmed text format weren't independently verified).
        for cell in soup.find_all(["td", "th", "div", "span"]):
            text = cell.get_text(" ", strip=True)
            if not text or not any(s in text for s in _SURFACES):
                continue
            m = _SURFACE_PATTERN.search(text)
            if not m:
                continue
            surface, pct, wins, losses = m.groups()
            if surface in result:
                continue  # keep first match, avoid double-counting nested elements
            result[surface] = {
                "win_pct": float(pct),
                "wins": int(wins),
                "losses": int(losses),
                "matches": int(wins) + int(losses),
            }

        _CACHE[player_id_or_name] = result
        return result
    except Exception as e:
        print(f"[WARN] fetch_player_surface_performance({player_id_or_name}): {e}")
        return {}


def surface_transition_flag(player_id: int, from_surface: str, to_surface: str) -> dict:
    """
    Real surface-performance gap for a player transitioning surfaces
    (e.g. clay -> grass), using their own actual win% split. The
    transition signal: the predictable drop in win probability equals the
    gap between the player's win% on their best vs. their worst surface,
    applied directionally to this specific from->to transition.
    """
    perf = fetch_player_surface_performance(player_id)
    from_data = perf.get(from_surface.capitalize())
    to_data = perf.get(to_surface.capitalize())
    if not from_data or not to_data:
        return {}

    gap = round(to_data["win_pct"] - from_data["win_pct"], 1)
    return {
        "from_surface": from_surface,
        "to_surface": to_surface,
        "from_win_pct": from_data["win_pct"],
        "to_win_pct": to_data["win_pct"],
        "from_record": f"{from_data['wins']}-{from_data['losses']}",
        "to_record": f"{to_data['wins']}-{to_data['losses']}",
        "gap": gap,
        "note": (
            f"{abs(gap):.1f}pt lower win% on {to_surface} ({to_data['win_pct']}%) "
            f"vs {from_surface} ({from_data['win_pct']}%)"
            if gap < 0 else f"No drop-off moving to {to_surface}"
        ),
    }
