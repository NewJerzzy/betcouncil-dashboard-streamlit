"""
team_canon.py — team-name canonicalization for cross-source game matching.

Built to satisfy unified_sharp_score.py's imports (canon_game_key, canon),
which were missing entirely -- the whole Sharp Board silently returned
nothing because of this. Also satisfies bc_utils.py's imports
(match_teams, match_players, merge_by_canon), which existed as import
statements with a defensive fallback for a long time but never had a
real implementation to import, since this file never existed until now --
bc_utils.py had always been silently running in degraded exact-string-
match mode as a result. Reuses the real, already-existing
TEAM_ABBREV_TO_FRAGMENT mapping from config.py (per-sport abbreviation ->
a distinctive city/team-name fragment) rather than inventing a new,
unverified team-name dataset.
"""
import difflib
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


def match_teams(a: str, b: str, sport: str = "", threshold: float = 0.82) -> bool:
    """
    Fuzzy match two team-name strings from potentially different sources.
    If a sport is given, first tries exact canonical-abbreviation match
    (fast, precise); falls back to string-similarity ratio either way so
    an unrecognized/new team name still gets a reasonable comparison
    instead of only ever matching on exact string equality.
    """
    if not a or not b:
        return False
    if sport:
        ca, cb = canon(a, sport), canon(b, sport)
        if ca and cb and ca == cb:
            return True
    ratio = difflib.SequenceMatcher(None, str(a).lower().strip(), str(b).lower().strip()).ratio()
    return ratio >= threshold


def match_players(a: str, b: str, threshold: float = 0.88) -> bool:
    """Fuzzy match two player-name strings (higher default threshold than
    team names, since player names are shorter and misspellings/initials
    can flip a match more easily on a loose threshold)."""
    if not a or not b:
        return False
    ratio = difflib.SequenceMatcher(None, str(a).lower().strip(), str(b).lower().strip()).ratio()
    return ratio >= threshold


def merge_by_canon(primary: dict, secondary: dict, **kwargs) -> dict:
    """
    Merge two records that represent the same real-world entity (matched
    via canonical team/player identity upstream) -- primary's values win
    on any overlapping key, secondary fills in whatever primary is
    missing. kwargs reserved for future field-specific merge rules (e.g.
    "prefer_secondary_for=[...]"), not used yet.
    """
    if not isinstance(primary, dict):
        return primary
    if not isinstance(secondary, dict):
        return primary
    merged = dict(secondary)
    merged.update({k: v for k, v in primary.items() if v is not None})
    return merged
