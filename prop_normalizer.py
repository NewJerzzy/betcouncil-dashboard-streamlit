"""
prop_normalizer.py — Cross-book player/prop name normalization and matching.

Public API
----------
normalize_player_name(raw) -> str
normalize_stat_name(raw, sport) -> str
build_prop_key(player, stat, line, sport, fixture_id=None) -> str
match_props_across_books(book_data, sport) -> list[dict]
get_fuzzy_review_queue() -> list[dict]
"""
import re
import unicodedata
import logging
from datetime import date
from typing import Optional

try:
    from rapidfuzz import fuzz, process as rf_process
    _RAPIDFUZZ = True
except ImportError:
    _RAPIDFUZZ = False

_logger = logging.getLogger("betcouncil.prop_normalizer")

# ── Player name override dict ─────────────────────────────────────────────────
# Maps canonical (normalized) name → list of known aliases.
# Extend this dict (or push betcouncil_player_name_overrides.json to the Gist)
# to add new aliases without a redeploy.
PLAYER_NAME_OVERRIDES: dict[str, list[str]] = {
    "shohei ohtani":                 ["s ohtani", "ohtani shohei", "ohtani"],
    "cj mccollum":                   ["cj mccollum", "c j mccollum"],
    "aj brown":                      ["a j brown"],
    "tj mcconnell":                  ["t j mcconnell"],
    "dj augustin":                   ["d j augustin"],
    "pj tucker":                     ["p j tucker"],
    "de aaron fox":                  ["deaaron fox", "d fox"],
    "shai gilgeous-alexander":       ["sga", "shai gilgeous alexander", "s gilgeous-alexander"],
    "luka doncic":                   ["luka", "doncic"],
    "giannis antetokounmpo":         ["giannis", "greek freak"],
    "anthony edwards":               ["ant edwards", "ant"],
    "jaren jackson jr":              ["jji", "jaren jackson"],
    "michael porter jr":             ["mpj", "michael porter"],
    "gary trent jr":                 ["gary trent"],
    "robert williams iii":           ["robert williams", "rob williams"],
    "ronald acuna jr":               ["ronald acuna", "r acuna"],
}

# Reverse lookup: alias → canonical  (built once at import time)
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canon, _aliases in PLAYER_NAME_OVERRIDES.items():
    _ALIAS_TO_CANONICAL[_canon] = _canon
    for _a in _aliases:
        _ALIAS_TO_CANONICAL[_a.lower().strip()] = _canon

# ── Stat taxonomy per sport ───────────────────────────────────────────────────
STAT_MAP: dict[str, dict[str, str]] = {
    "MLB": {
        "hits": "player_hits", "h": "player_hits", "hit": "player_hits",
        "base hits": "player_hits", "base_hits": "player_hits",
        "runs": "player_runs", "r": "player_runs",
        "runs scored": "player_runs", "runs_scored": "player_runs",
        "rbi": "player_rbi", "rbis": "player_rbi",
        "runs batted in": "player_rbi", "runs_batted_in": "player_rbi",
        "home runs": "player_home_runs", "home run": "player_home_runs",
        "hr": "player_home_runs", "homeruns": "player_home_runs",
        "homerun": "player_home_runs",
        "total bases": "player_total_bases", "total_bases": "player_total_bases",
        "tb": "player_total_bases",
        "batter strikeouts": "player_strikeouts_batter",
        "batter_strikeouts": "player_strikeouts_batter",
        "strikeouts (batter)": "player_strikeouts_batter",
        "pitcher strikeouts": "player_strikeouts_pitcher",
        "strikeouts": "player_strikeouts_pitcher",
        "strikeouts pitched": "player_strikeouts_pitcher",
        "pitching strikeouts": "player_strikeouts_pitcher",
        "ks": "player_strikeouts_pitcher", "k": "player_strikeouts_pitcher",
        "so": "player_strikeouts_pitcher",
        "walks": "player_walks", "bb": "player_walks",
        "base on balls": "player_walks",
        "earned runs": "player_earned_runs", "er": "player_earned_runs",
        "runs allowed": "player_earned_runs",
        "innings pitched": "player_innings_pitched", "ip": "player_innings_pitched",
        "innings": "player_innings_pitched",
        "stolen bases": "player_stolen_bases", "sb": "player_stolen_bases",
        "stolen_bases": "player_stolen_bases",
        "singles": "player_singles", "1b": "player_singles",
        "doubles": "player_doubles", "2b": "player_doubles",
        "triples": "player_triples", "3b": "player_triples",
        "h+r+rbi": "player_hits_runs_rbi", "h r rbi": "player_hits_runs_rbi",
        "hits+runs+rbi": "player_hits_runs_rbi", "hrr": "player_hits_runs_rbi",
        "hits allowed": "player_hits_allowed", "ha": "player_hits_allowed",
        "outs recorded": "player_pitching_outs", "outs": "player_pitching_outs",
        "pitching outs": "player_pitching_outs",
        "walks allowed": "player_walks_allowed",
    },
    "NBA": {
        "points": "player_points", "pts": "player_points",
        "points scored": "player_points",
        "rebounds": "player_rebounds", "reb": "player_rebounds",
        "total rebounds": "player_rebounds", "boards": "player_rebounds",
        "assists": "player_assists", "ast": "player_assists", "dimes": "player_assists",
        "steals": "player_steals", "stl": "player_steals",
        "blocks": "player_blocks", "blk": "player_blocks",
        "turnovers": "player_turnovers", "to": "player_turnovers", "tov": "player_turnovers",
        "three pointers made": "player_three_pointers",
        "3-pointers made": "player_three_pointers",
        "3 pointers made": "player_three_pointers",
        "3pm": "player_three_pointers", "fg3m": "player_three_pointers",
        "threes": "player_three_pointers", "3-pt made": "player_three_pointers",
        "pts+reb+ast": "player_pra", "pra": "player_pra",
        "points+rebounds+assists": "player_pra", "pts + reb + ast": "player_pra",
        "pts+reb": "player_pr", "pr": "player_pr", "points+rebounds": "player_pr",
        "pts+ast": "player_pa", "pa": "player_pa", "points+assists": "player_pa",
        "reb+ast": "player_ra", "ra": "player_ra", "rebounds+assists": "player_ra",
        "fantasy points": "player_fantasy_points", "fp": "player_fantasy_points",
        "minutes": "player_minutes", "min": "player_minutes",
        "field goals made": "player_field_goals", "fgm": "player_field_goals",
    },
    "NFL": {
        "passing yards": "player_passing_yards", "pass yds": "player_passing_yards",
        "passing yds": "player_passing_yards",
        "rushing yards": "player_rushing_yards", "rush yds": "player_rushing_yards",
        "rushing yds": "player_rushing_yards",
        "receiving yards": "player_receiving_yards", "rec yds": "player_receiving_yards",
        "receiving yds": "player_receiving_yards", "recv yards": "player_receiving_yards",
        "receptions": "player_receptions", "recs": "player_receptions",
        "catches": "player_receptions",
        "passing touchdowns": "player_passing_tds", "pass tds": "player_passing_tds",
        "rushing touchdowns": "player_rushing_tds", "rush tds": "player_rushing_tds",
        "receiving touchdowns": "player_receiving_tds", "rec tds": "player_receiving_tds",
        "pass attempts": "player_pass_attempts", "pass att": "player_pass_attempts",
        "completions": "player_completions", "comps": "player_completions",
        "targets": "player_targets", "tgts": "player_targets",
        "longest reception": "player_longest_reception",
        "longest rec": "player_longest_reception",
        "interceptions": "player_interceptions", "ints": "player_interceptions",
        "sacks": "player_sacks",
        "kicking points": "player_kicking_points",
    },
    "NHL": {
        "goals": "player_goals", "goal": "player_goals",
        "assists": "player_assists", "assist": "player_assists",
        "points": "player_points", "pts": "player_points",
        "goals+assists": "player_points", "g+a": "player_points",
        "shots on goal": "player_shots_on_goal", "sog": "player_shots_on_goal",
        "shots": "player_shots_on_goal",
        "blocked shots": "player_blocked_shots", "blocks": "player_blocked_shots",
        "penalty minutes": "player_penalty_minutes", "pim": "player_penalty_minutes",
        "saves": "player_saves",
        "time on ice": "player_toi", "toi": "player_toi",
    },
}
STAT_MAP["WNBA"] = STAT_MAP["NBA"].copy()

# Fuzzy match threshold: 0-100. Below this score we log to the review queue.
FUZZY_THRESHOLD: int = 90

# Accumulated low-confidence fuzzy matches — review to extend PLAYER_NAME_OVERRIDES
_FUZZY_REVIEW_QUEUE: list[dict] = []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def normalize_player_name(raw_name: str) -> str:
    """
    Canonical player name normalization:
      1. Lowercase + strip
      2. Remove diacritical marks (é→e, ñ→n …)
      3. Remove suffixes: Jr., Sr., II, III, IV, V
      4. Remove periods in initials (C.J. → cj)
      5. Collapse whitespace
      6. Apply PLAYER_NAME_OVERRIDES alias lookup
    """
    if not raw_name:
        return ""
    s = raw_name.strip().lower()
    s = _strip_accents(s)
    s = re.sub(r"\b(jr\.?|sr\.?|iii|ii|iv|v)\b", "", s)
    s = s.replace(".", "")
    s = " ".join(s.split())
    return _ALIAS_TO_CANONICAL.get(s, s)


def normalize_stat_name(raw_stat: str, sport: str) -> str:
    """
    Map a book-specific stat label to the canonical BetCouncil taxonomy.
    Falls back to a slugified version of the raw name if not in the map.
    """
    if not raw_stat:
        return ""
    sport_map = STAT_MAP.get(sport.upper(), {})
    key = raw_stat.strip().lower()
    if key in sport_map:
        return sport_map[key]
    key2 = re.sub(r"[^a-z0-9 +]", " ", key)
    key2 = " ".join(key2.split())
    if key2 in sport_map:
        return sport_map[key2]
    slug = re.sub(r"[^a-z0-9]", "_", key2)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"player_{slug}" if slug else "player_unknown"


def build_prop_key(
    player: str,
    stat: str,
    line: float,
    sport: str,
    fixture_id: Optional[str] = None,
) -> str:
    """
    Canonical cross-book prop key.
    Format: {sport}:{stat_canonical}:{player_canonical}:{line}:{fixture_id}
    fixture_id defaults to today's date (YYYYMMDD).
    """
    if fixture_id is None:
        fixture_id = date.today().strftime("%Y%m%d")
    try:
        line_str = f"{float(line):.1f}"
    except (TypeError, ValueError):
        line_str = str(line)
    return (
        f"{sport.lower()}"
        f":{normalize_stat_name(stat, sport)}"
        f":{normalize_player_name(player)}"
        f":{line_str}"
        f":{fixture_id}"
    )


def build_market_key(player: str, stat: str, sport: str = "", fixture_id: Optional[str] = None) -> str:
    """
    Cross-book market key WITHOUT the line value — deliberately looser than
    build_prop_key(). Two books posting the SAME player/stat at DIFFERENT
    lines must land on the same key here so middling opportunities (PP at
    0.5, Underdog at 1.5) can be detected. build_prop_key() stays as-is for
    exact same-line odds comparison; this is the companion key for
    cross-line comparison.
    Format: {sport}:{stat_canonical}:{player_canonical}:{fixture_id}
    """
    if fixture_id is None:
        fixture_id = date.today().strftime("%Y%m%d")
    return (
        f"{sport.lower()}"
        f":{normalize_stat_name(stat, sport)}"
        f":{normalize_player_name(player)}"
        f":{fixture_id}"
    )


def find_middling_opportunities(book_data: dict[str, list[dict]], sport: str = "") -> list[dict]:
    """
    Group props by player+stat (ignoring line), and flag any group where
    two or more books post DIFFERENT lines for the same player/stat —
    the definition of a middling opportunity.

    Returns
    -------
    list[dict]: one entry per player/stat with 2+ distinct lines:
        {market_key, player, stat, sport, lines: {book: {line, over_odds, under_odds}},
         min_line, max_line, spread}
    """
    grouped: dict[str, dict] = {}

    for book, props in book_data.items():
        if not isinstance(props, list):
            continue
        for p in props:
            player_raw = str(p.get("Player") or p.get("player") or "")
            stat_raw   = str(p.get("Prop") or p.get("Stat") or p.get("stat") or "")
            line_raw   = p.get("Line") or p.get("line")
            sport_p    = sport or str(p.get("Sport") or p.get("sport") or "")
            if not player_raw or not stat_raw or line_raw is None:
                continue
            try:
                line_f = float(line_raw)
            except (TypeError, ValueError):
                continue

            mkey = build_market_key(player_raw, stat_raw, sport_p)
            if mkey not in grouped:
                grouped[mkey] = {
                    "market_key": mkey,
                    "player": normalize_player_name(player_raw),
                    "stat":   normalize_stat_name(stat_raw, sport_p),
                    "sport":  (sport_p or sport).upper(),
                    "lines":  {},
                }
            grouped[mkey]["lines"][book] = {
                "line": line_f,
                "over_odds":  p.get("OverOdds") or p.get("over_odds"),
                "under_odds": p.get("UnderOdds") or p.get("under_odds"),
            }

    opportunities = []
    for mkey, g in grouped.items():
        distinct_lines = {v["line"] for v in g["lines"].values()}
        if len(distinct_lines) >= 2:
            g["min_line"] = min(distinct_lines)
            g["max_line"] = max(distinct_lines)
            g["spread"] = round(g["max_line"] - g["min_line"], 2)
            opportunities.append(g)

    opportunities.sort(key=lambda x: x["spread"], reverse=True)
    return opportunities


def match_props_across_books(
    book_data: dict[str, list[dict]],
    sport: str = "",
) -> list[dict]:
    """
    Group the same real-world prop across books with different label formats.

    Parameters
    ----------
    book_data : {book_name: [prop_dicts]}
        Each prop_dict must have at least: Player, Prop (or Stat), Line.
        Optional: OverOdds, UnderOdds, Team, Sport.
    sport : str
        Sport context for stat normalization.

    Returns
    -------
    list[dict]  — one entry per matched prop group:
        {prop_key, player, stat, line, sport, books: {book: {over_odds, under_odds, …}}}
    """
    grouped: dict[str, dict] = {}

    for book, props in book_data.items():
        if not isinstance(props, list):
            continue
        for p in props:
            player_raw = str(p.get("Player") or p.get("player") or "")
            stat_raw   = str(p.get("Prop") or p.get("Stat") or p.get("stat") or "")
            line_raw   = p.get("Line") or p.get("line")
            sport_p    = sport or str(p.get("Sport") or p.get("sport") or "")
            if not player_raw or not stat_raw or line_raw is None:
                continue
            try:
                line_f = float(line_raw)
            except (TypeError, ValueError):
                continue

            player_norm = normalize_player_name(player_raw)
            stat_canon  = normalize_stat_name(stat_raw, sport_p)
            prop_key    = build_prop_key(player_norm, stat_canon, line_f, sport_p)

            if prop_key not in grouped:
                grouped[prop_key] = {
                    "prop_key": prop_key,
                    "player":   player_norm,
                    "stat":     stat_canon,
                    "line":     line_f,
                    "sport":    (sport_p or sport).upper(),
                    "books":    {},
                }
            grouped[prop_key]["books"][book] = {
                "over_odds":  p.get("OverOdds") or p.get("over_odds"),
                "under_odds": p.get("UnderOdds") or p.get("under_odds"),
                "raw_stat":   stat_raw,
                "raw_player": player_raw,
            }

    # Fuzzy fallback — merge near-duplicate player names that didn't exact-match
    if _RAPIDFUZZ:
        keys   = list(grouped.keys())
        merged: set[str] = set()
        for i, k1 in enumerate(keys):
            if k1 in merged:
                continue
            g1 = grouped[k1]
            for k2 in keys[i + 1:]:
                if k2 in merged:
                    continue
                g2 = grouped[k2]
                if g1["stat"] != g2["stat"] or g1["line"] != g2["line"]:
                    continue
                score = fuzz.token_sort_ratio(g1["player"], g2["player"])
                if score >= FUZZY_THRESHOLD:
                    for bk, bv in g2["books"].items():
                        if bk not in g1["books"]:
                            g1["books"][bk] = bv
                    merged.add(k2)
                elif score >= 75:
                    _FUZZY_REVIEW_QUEUE.append({
                        "p1": g1["player"], "p2": g2["player"],
                        "stat": g1["stat"], "score": score,
                    })
        for k in merged:
            del grouped[k]

    return list(grouped.values())


def get_fuzzy_review_queue() -> list[dict]:
    """Return accumulated low-confidence fuzzy match candidates for manual review."""
    return list(_FUZZY_REVIEW_QUEUE)
