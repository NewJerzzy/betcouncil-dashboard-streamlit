"""
team_canon.py — team-name canonicalization for cross-source game matching.

Built to satisfy unified_sharp_score.py's imports (canon_game_key, canon),
which were missing entirely -- the whole Sharp Board silently returned
nothing because of this. Reuses the real, already-existing
TEAM_ABBREV_TO_FRAGMENT mapping from config.py (per-sport abbreviation ->
a distinctive city/team-name fragment) rather than inventing a new,
unverified team-name dataset.
"""
from config import TEAM_ABBREV_TO_FRAGMENT

# Reverse index per sport: distinctive fragment (lowercased) -> abbreviation,
# built once at import time from the real config.py data.
_FRAGMENT_TO_ABBREV = {}
for _sport, _teams in TEAM_ABBREV_TO_FRAGMENT.items():
    _FRAGMENT_TO_ABBREV[_sport] = {
        frag.lower(): abbrev for abbrev, frag in _teams.items()
    }


def canon(name: str, sport: str) -> str:
    """
    Canonicalize a team name (from any source's spelling/format) to its
    standard abbreviation for that sport. Falls back to a normalized
    version of the input name itself if no match is found, so downstream
    matching degrades gracefully instead of raising.
    """
    if not name:
        return ""
    name_l = str(name).strip().lower()
    sport_u = str(sport).upper()

    # Already an abbreviation?
    frag_map = _FRAGMENT_TO_ABBREV.get(sport_u, {})
    all_abbrevs = set(TEAM_ABBREV_TO_FRAGMENT.get(sport_u, {}).keys())
    if name.strip().upper() in all_abbrevs:
        return name.strip().upper()

    # Match against known fragments -- longest fragment first, so e.g.
    # "Los Angeles Dodgers" matches the specific Dodgers fragment before
    # a shorter generic "Los Angeles" one could exist.
    for frag in sorted(frag_map.keys(), key=len, reverse=True):
        if frag in name_l:
            return frag_map[frag]

    # No match -- normalize to a stable fallback (strip whitespace/case)
    # rather than raising, so a genuinely new/unlisted team name still
    # produces a consistent (if imperfect) key.
    return "".join(ch for ch in name_l if ch.isalnum())[:12]


def canon_game_key(away: str, home: str, sport: str) -> str:
    """Stable, order-aware key for matching the same game across sources
    with potentially different team-name spellings/formats."""
    return f"{canon(away, sport)}@{canon(home, sport)}|{str(sport).upper()}"
