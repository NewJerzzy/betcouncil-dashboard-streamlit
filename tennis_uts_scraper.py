"""
tennis_uts_scraper.py — Player surface performance from
ultimatetennisstatistics.com.

Site's only stated restriction: "Please do not perform massive parallel
crawling... hosted on very modest hardware (1 CPU Core, 2 GB RAM)." This
is a politeness request, not a scraping ban (unlike FanGraphs) — honored
here via sequential requests only, generous caching, and a rate-limit
delay between calls.

CAVEAT: a direct fetch of a playerProfile?tab=performance page did not
return the data table in raw HTML during verification — this app may
render some content client-side. This scraper tries multiple real
candidate selectors defensively and returns {} rather than guessing at a
schema if none match, so it fails safe instead of returning fabricated
numbers.

Public API
----------
fetch_player_surface_performance(player_id) -> dict
    {surface: {win_pct, matches}} or {} if the table couldn't be parsed.
"""
import time
import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_REQUEST_DELAY_SECONDS = 2.0  # respect their stated small-server hosting
_SURFACES = ("Hard", "Clay", "Grass", "Carpet")

_CACHE = {}  # player_id -> {surface: {...}}, avoid re-hitting the same profile


def fetch_player_surface_performance(player_id: int) -> dict:
    """
    Attempts to parse surface win% breakdown from a player's performance
    tab. Returns {} on any parsing failure rather than guessed data.
    """
    if player_id in _CACHE:
        return _CACHE[player_id]

    url = f"https://www.ultimatetennisstatistics.com/playerProfile?playerId={player_id}&tab=performance"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        time.sleep(_REQUEST_DELAY_SECONDS)  # polite pacing before/after each call
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")

        result = {}
        # Defensive: try to find any table row whose first cell names a
        # known surface, and a following cell that looks like a W-L record
        # or win percentage. Multiple candidate table classes tried since
        # the real rendered structure wasn't confirmed live.
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if not cells:
                    continue
                surface_cell = cells[0]
                matched_surface = next((s for s in _SURFACES if s.lower() == surface_cell.lower()), None)
                if not matched_surface:
                    continue
                # look for a W-L record or a percentage in the remaining cells
                for c in cells[1:]:
                    if "-" in c and c.replace("-", "").isdigit():
                        w, _, l = c.partition("-")
                        try:
                            w, l = int(w), int(l)
                            total = w + l
                            if total > 0:
                                result[matched_surface] = {
                                    "win_pct": round(w / total * 100, 1),
                                    "matches": total,
                                }
                        except ValueError:
                            continue
                    elif c.endswith("%"):
                        try:
                            result[matched_surface] = {"win_pct": float(c.rstrip("%")), "matches": None}
                        except ValueError:
                            continue

        _CACHE[player_id] = result
        return result
    except Exception as e:
        print(f"[WARN] fetch_player_surface_performance({player_id}): {e}")
        return {}


def surface_transition_flag(player_id: int, from_surface: str, to_surface: str) -> dict:
    """
    Flags a real surface-performance gap for a player transitioning
    surfaces (e.g. clay -> grass), using their own actual win% split
    rather than DeepSeek's invented -4%/-3% figures. Returns {} if data
    unavailable for either surface.
    """
    perf = fetch_player_surface_performance(player_id)
    from_data = perf.get(from_surface.capitalize())
    to_data = perf.get(to_surface.capitalize())
    if not from_data or not to_data:
        return {}

    gap = to_data["win_pct"] - from_data["win_pct"]
    return {
        "from_surface": from_surface,
        "to_surface": to_surface,
        "from_win_pct": from_data["win_pct"],
        "to_win_pct": to_data["win_pct"],
        "gap": round(gap, 1),
        "note": (
            f"{abs(gap):.1f}pt lower win% on {to_surface} vs {from_surface}"
            if gap < 0 else f"No drop-off moving to {to_surface}"
        ),
    }
