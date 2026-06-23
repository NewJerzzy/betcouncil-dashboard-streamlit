# team_canon.py
# Team name canonicalization for BetCouncil
# Adapted from declansx/sports-prediction-market-aggregator canonicalization pattern.
#
# Canonicalization chain (in order):
#   1. Sport-scoped manual override  (MANUAL_BY_SPORT)
#   2. Global manual alias map       (MANUAL)
#   3. Affix stripping               (org prefixes/suffixes)
#   4. Trailing-parenthesis strip
#   5. Whitespace/case normalization
#
# Usage:
#   from team_canon import canon, match_teams, merge_by_canon
#
#   canon("New York Yankees", "MLB")      → "Yankees"  (uses MANUAL)
#   canon("LA Kings", "NHL")              → "Kings" (sport-scoped)
#   match_teams("Chi Cubs", "Chicago Cubs", "MLB")  → True
#   merge_by_canon(lines, splits, "MLB")  → merged list

import re
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# 1. Sport-scoped manual overrides
#    For cross-sport name collisions (Kings, Heat, etc.)
# ---------------------------------------------------------------------------
MANUAL_BY_SPORT = {
    "NBA": {
        "kings":           "Sacramento Kings",
        "sacramento kings": "Sacramento Kings",
        "la kings":        "Sacramento Kings",  # NBA context only
        "heat":            "Miami Heat",
        "miami heat":      "Miami Heat",
    },
    "NHL": {
        "kings":           "LA Kings",
        "la kings":        "LA Kings",
        "los angeles kings": "LA Kings",
    },
}

# ---------------------------------------------------------------------------
# 2. Global manual alias map
#    Key: any known variant (lowercased), Value: canonical form
# ---------------------------------------------------------------------------
MANUAL = {
    # ── MLB ──────────────────────────────────────────────────────────────────
    "new york yankees":        "Yankees",
    "ny yankees":              "Yankees",
    "nyy":                     "Yankees",
    "new york mets":           "Mets",
    "ny mets":                 "Mets",
    "nym":                     "Mets",
    "boston red sox":          "Red Sox",
    "bos":                     "Red Sox",
    "chicago cubs":            "Cubs",
    "chc":                     "Cubs",
    "chicago white sox":       "White Sox",
    "cws":                     "White Sox",
    "chw":                     "White Sox",
    "los angeles dodgers":     "Dodgers",
    "la dodgers":              "Dodgers",
    "lad":                     "Dodgers",
    "los angeles angels":      "Angels",
    "la angels":               "Angels",
    "laa":                     "Angels",
    "anaheim angels":          "Angels",
    "san francisco giants":    "Giants",
    "sf giants":               "Giants",
    "sfg":                     "Giants",
    "san diego padres":        "Padres",
    "sd padres":               "Padres",
    "sdp":                     "Padres",
    "colorado rockies":        "Rockies",
    "col":                     "Rockies",
    "arizona diamondbacks":    "Diamondbacks",
    "az diamondbacks":         "Diamondbacks",
    "ari":                     "Diamondbacks",
    "st. louis cardinals":     "Cardinals",
    "st louis cardinals":      "Cardinals",
    "stl":                     "Cardinals",
    "milwaukee brewers":       "Brewers",
    "mil":                     "Brewers",
    "cincinnati reds":         "Reds",
    "cin":                     "Reds",
    "pittsburgh pirates":      "Pirates",
    "pit":                     "Pirates",
    "atlanta braves":          "Braves",
    "atl":                     "Braves",
    "philadelphia phillies":   "Phillies",
    "phi":                     "Phillies",
    "washington nationals":    "Nationals",
    "was":                     "Nationals",
    "wsh":                     "Nationals",
    "miami marlins":           "Marlins",
    "mia":                     "Marlins",
    "minnesota twins":         "Twins",
    "min":                     "Twins",
    "cleveland guardians":     "Guardians",
    "cle":                     "Guardians",
    "detroit tigers":          "Tigers",
    "det":                     "Tigers",
    "kansas city royals":      "Royals",
    "kc royals":               "Royals",
    "kcr":                     "Royals",
    "tampa bay rays":          "Rays",
    "tb rays":                 "Rays",
    "tbr":                     "Rays",
    "toronto blue jays":       "Blue Jays",
    "tor":                     "Blue Jays",
    "baltimore orioles":       "Orioles",
    "bal":                     "Orioles",
    "houston astros":          "Astros",
    "hou":                     "Astros",
    "texas rangers":           "Rangers",
    "tex":                     "Rangers",
    "seattle mariners":        "Mariners",
    "sea":                     "Mariners",
    "oakland athletics":       "Athletics",
    "athletics":               "Athletics",
    "oak":                     "Athletics",
    "sacramento athletics":    "Athletics",
    # ── NBA ──────────────────────────────────────────────────────────────────
    "golden state warriors":   "Warriors",
    "gsw":                     "Warriors",
    "los angeles lakers":      "Lakers",
    "la lakers":               "Lakers",
    "lal":                     "Lakers",
    "los angeles clippers":    "Clippers",
    "la clippers":             "Clippers",
    "lac":                     "Clippers",
    "boston celtics":          "Celtics",
    "bos celtics":             "Celtics",
    "bkn":                     "Nets",
    "brooklyn nets":           "Nets",
    "new york knicks":         "Knicks",
    "nyk":                     "Knicks",
    "philadelphia 76ers":      "76ers",
    "phila 76ers":             "76ers",
    "phi 76ers":               "76ers",
    "phi76ers":                "76ers",
    "phx":                     "Suns",
    "phoenix suns":            "Suns",
    "denver nuggets":          "Nuggets",
    "den":                     "Nuggets",
    "dallas mavericks":        "Mavericks",
    "dal":                     "Mavericks",
    "memphis grizzlies":       "Grizzlies",
    "mem":                     "Grizzlies",
    "new orleans pelicans":    "Pelicans",
    "no pelicans":             "Pelicans",
    "nop":                     "Pelicans",
    "san antonio spurs":       "Spurs",
    "sa spurs":                "Spurs",
    "sas":                     "Spurs",
    "oklahoma city thunder":   "Thunder",
    "okc":                     "Thunder",
    "portland trail blazers":  "Trail Blazers",
    "portland trailblazers":   "Trail Blazers",
    "por":                     "Trail Blazers",
    "utah jazz":               "Jazz",
    "uta":                     "Jazz",
    "minnesota timberwolves":  "Timberwolves",
    "min timberwolves":        "Timberwolves",
    "min wolves":              "Timberwolves",
    "chicago bulls":           "Bulls",
    "chi bulls":               "Bulls",
    "chi":                     "Bulls",
    "milwaukee bucks":         "Bucks",
    "mil bucks":               "Bucks",
    "indiana pacers":          "Pacers",
    "ind":                     "Pacers",
    "cleveland cavaliers":     "Cavaliers",
    "cle cavs":                "Cavaliers",
    "detroit pistons":         "Pistons",
    "det pistons":             "Pistons",
    "toronto raptors":         "Raptors",
    "tor raptors":             "Raptors",
    "charlotte hornets":       "Hornets",
    "cha":                     "Hornets",
    "washington wizards":      "Wizards",
    "was wizards":             "Wizards",
    "orlando magic":           "Magic",
    "orl":                     "Magic",
    "atlanta hawks":           "Hawks",
    "atl hawks":               "Hawks",
    "miami heat":              "Heat",
    "mia heat":                "Heat",
    # ── NFL ──────────────────────────────────────────────────────────────────
    "new england patriots":    "Patriots",
    "ne patriots":             "Patriots",
    "ne":                      "Patriots",
    "ne pats":                 "Patriots",
    "new york giants":         "Giants",
    "ny giants":               "Giants",
    "nyg":                     "Giants",
    "new york jets":           "Jets",
    "ny jets":                 "Jets",
    "nyj":                     "Jets",
    "dallas cowboys":          "Cowboys",
    "dal cowboys":             "Cowboys",
    "philadelphia eagles":     "Eagles",
    "phi eagles":              "Eagles",
    "washington commanders":   "Commanders",
    "was commanders":          "Commanders",
    "washington football team": "Commanders",
    "washington redskins":     "Commanders",
    "san francisco 49ers":     "49ers",
    "sf 49ers":                "49ers",
    "sf":                      "49ers",
    "sfo":                     "49ers",
    "los angeles rams":        "Rams",
    "la rams":                 "Rams",
    "lar":                     "Rams",
    "seattle seahawks":        "Seahawks",
    "sea seahawks":            "Seahawks",
    "arizona cardinals":       "Cardinals",
    "az cardinals":            "Cardinals",
    "ari cardinals":           "Cardinals",
    "green bay packers":       "Packers",
    "gb":                      "Packers",
    "chicago bears":           "Bears",
    "chi bears":               "Bears",
    "minnesota vikings":       "Vikings",
    "min vikings":             "Vikings",
    "detroit lions":           "Lions",
    "det lions":               "Lions",
    "kansas city chiefs":      "Chiefs",
    "kc chiefs":               "Chiefs",
    "kc":                      "Chiefs",
    "las vegas raiders":       "Raiders",
    "lv raiders":              "Raiders",
    "oak raiders":             "Raiders",
    "denver broncos":          "Broncos",
    "den broncos":             "Broncos",
    "los angeles chargers":    "Chargers",
    "la chargers":             "Chargers",
    "lac chargers":            "Chargers",
    "pittsburgh steelers":     "Steelers",
    "pit steelers":            "Steelers",
    "baltimore ravens":        "Ravens",
    "bal ravens":              "Ravens",
    "cincinnati bengals":      "Bengals",
    "cin bengals":             "Bengals",
    "cleveland browns":        "Browns",
    "cle browns":              "Browns",
    "miami dolphins":          "Dolphins",
    "mia dolphins":            "Dolphins",
    "buffalo bills":           "Bills",
    "buf":                     "Bills",
    "jacksonville jaguars":    "Jaguars",
    "jax":                     "Jaguars",
    "tennessee titans":        "Titans",
    "ten":                     "Titans",
    "indianapolis colts":      "Colts",
    "ind colts":               "Colts",
    "houston texans":          "Texans",
    "hou texans":              "Texans",
    "new orleans saints":      "Saints",
    "no saints":               "Saints",
    "nor":                     "Saints",
    "atlanta falcons":         "Falcons",
    "atl falcons":             "Falcons",
    "carolina panthers":       "Panthers",
    "car":                     "Panthers",
    "tampa bay buccaneers":    "Buccaneers",
    "tb bucs":                 "Buccaneers",
    "tb buccaneers":           "Buccaneers",
    "tbr buccaneers":          "Buccaneers",
    "new york giants":         "Giants",
    "new york jets":           "Jets",
    # ── NHL ──────────────────────────────────────────────────────────────────
    "boston bruins":           "Bruins",
    "bos bruins":              "Bruins",
    "toronto maple leafs":     "Maple Leafs",
    "tor maple leafs":         "Maple Leafs",
    "montreal canadiens":      "Canadiens",
    "mtl":                     "Canadiens",
    "new york rangers":        "Rangers",
    "ny rangers":              "Rangers",
    "nyr":                     "Rangers",
    "new york islanders":      "Islanders",
    "ny islanders":            "Islanders",
    "nyi":                     "Islanders",
    "pittsburgh penguins":     "Penguins",
    "pit penguins":            "Penguins",
    "washington capitals":     "Capitals",
    "was capitals":            "Capitals",
    "wsh capitals":            "Capitals",
    "philadelphia flyers":     "Flyers",
    "phi flyers":              "Flyers",
    "new jersey devils":       "Devils",
    "nj devils":               "Devils",
    "njd":                     "Devils",
    "carolina hurricanes":     "Hurricanes",
    "car hurricanes":          "Hurricanes",
    "florida panthers":        "Panthers",
    "fla":                     "Panthers",
    "tampa bay lightning":     "Lightning",
    "tb lightning":            "Lightning",
    "tbl":                     "Lightning",
    "detroit red wings":       "Red Wings",
    "det red wings":           "Red Wings",
    "chicago blackhawks":      "Blackhawks",
    "chi blackhawks":          "Blackhawks",
    "nashville predators":     "Predators",
    "nas":                     "Predators",
    "st. louis blues":         "Blues",
    "st louis blues":          "Blues",
    "stl blues":               "Blues",
    "colorado avalanche":      "Avalanche",
    "col avalanche":           "Avalanche",
    "minnesota wild":          "Wild",
    "min wild":                "Wild",
    "winnipeg jets":           "Jets",
    "wpg":                     "Jets",
    "calgary flames":          "Flames",
    "cgy":                     "Flames",
    "edmonton oilers":         "Oilers",
    "edm":                     "Oilers",
    "vancouver canucks":       "Canucks",
    "van":                     "Canucks",
    "seattle kraken":          "Kraken",
    "sea kraken":              "Kraken",
    "san jose sharks":         "Sharks",
    "sjs":                     "Sharks",
    "anaheim ducks":           "Ducks",
    "ana":                     "Ducks",
    "los angeles kings":       "LA Kings",
    "la kings":                "LA Kings",
    "lak":                     "LA Kings",
    "vegas golden knights":    "Golden Knights",
    "vgk":                     "Golden Knights",
    "arizona coyotes":         "Coyotes",
    "ari coyotes":             "Coyotes",
    "utah hockey club":        "Utah HC",
    "utah hc":                 "Utah HC",
    "ottawa senators":         "Senators",
    "ott":                     "Senators",
    "buffalo sabres":          "Sabres",
    "buf sabres":              "Sabres",
    "columbus blue jackets":   "Blue Jackets",
    "cbj":                     "Blue Jackets",
    "dallas stars":            "Stars",
    "dal stars":               "Stars",
    "phoenix coyotes":         "Coyotes",
    # ── WNBA ─────────────────────────────────────────────────────────────────
    "las vegas aces":          "Aces",
    "lv aces":                 "Aces",
    "new york liberty":        "Liberty",
    "ny liberty":              "Liberty",
    "chicago sky":             "Sky",
    "seattle storm":           "Storm",
    "connecticut sun":         "Sun",
    "minnesota lynx":          "Lynx",
    "los angeles sparks":      "Sparks",
    "la sparks":               "Sparks",
    "phoenix mercury":         "Mercury",
    "phx mercury":             "Mercury",
    "indiana fever":           "Fever",
    "atlanta dream":           "Dream",
    "dallas wings":            "Wings",
    "golden state valkyries":  "Valkyries",
    "washington mystics":      "Mystics",
    "was mystics":             "Mystics",
}

# ---------------------------------------------------------------------------
# 3. Affix stripping
# ---------------------------------------------------------------------------
_PREFIX_RE = re.compile(
    r"^(?:afc|nfc|fc|cf|afc|ca|club|cd|real|as|ac|sc|sk|bk|if|hc|hv|fk|rfc|ss|us|ud|rc|ue|ge|sv|vfl|vfb|fsv|tsg|sg|rb|bsc|fsc|gfc|pfc|csk)\s+",
    re.I,
)
_SUFFIX_RE = re.compile(
    r"\s+(?:fc|cf|sc|ac|afc|rfc|bk|if|hc|hv|fk|ss|us|ud|rc|ue|ge|sv|vfl|vfb|fsv|bc|bsc|city|town|united|utd|athletic|atletico|sports|sport|soccer)$",
    re.I,
)
_PAREN_RE = re.compile(r"\s*\([^)]+\)$")


def _strip_affixes(name: str) -> str:
    name = _PAREN_RE.sub("", name).strip()
    name = _PREFIX_RE.sub("", name).strip()
    name = _SUFFIX_RE.sub("", name).strip()
    return name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def canon(name: str, sport: str = "") -> str:
    """
    Return the canonical team name for BetCouncil.
    Applies the full chain: sport-scope → manual → affix strip → normalize.
    """
    if not name:
        return ""

    key = name.strip().lower()

    # 1. Sport-scoped override
    sport_map = MANUAL_BY_SPORT.get(sport.upper(), {})
    if key in sport_map:
        return sport_map[key]

    # 2. Global manual map
    if key in MANUAL:
        return MANUAL[key]

    # 3. Affix stripping → retry manual map
    stripped = _strip_affixes(name).strip()
    stripped_key = stripped.lower()
    if stripped_key != key:
        if stripped_key in sport_map:
            return sport_map[stripped_key]
        if stripped_key in MANUAL:
            return MANUAL[stripped_key]

    # 4. Return affix-stripped form with title case if we changed something
    if stripped_key != key:
        return stripped.title()

    # 5. Return as-is (title-cased)
    return name.strip()


def _sim(a: str, b: str) -> float:
    """SequenceMatcher ratio on lowercased strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def match_teams(a: str, b: str, sport: str = "", threshold: float = 0.82) -> bool:
    """
    Return True if two team name strings refer to the same team.
    Uses canonical form comparison first, then fuzzy fallback.
    """
    ca = canon(a, sport)
    cb = canon(b, sport)
    if ca.lower() == cb.lower():
        return True
    # Fuzzy on canonical forms
    if _sim(ca, cb) >= threshold:
        return True
    # Fuzzy on raw forms (catches partial inputs like "Cubs" matching "Chicago Cubs")
    if _sim(a, b) >= threshold:
        return True
    # One is substring of the other (e.g. "Yankees" in "New York Yankees")
    al, bl = a.lower(), b.lower()
    if al in bl or bl in al:
        return True
    cal, cbl = ca.lower(), cb.lower()
    if cal in cbl or cbl in cal:
        return True
    return False


def canon_game_key(away: str, home: str, sport: str = "", date_str: str = "") -> str:
    """
    Generate a stable canonical key for a game, for cross-source merging.
    Key: sport|date|sorted(canon_away, canon_home)
    Sorted team names so source order doesn't matter.
    """
    ca = canon(away, sport).lower()
    ch = canon(home, sport).lower()
    teams_key = "|".join(sorted([ca, ch]))
    return f"{sport.upper()}|{date_str}|{teams_key}"


def merge_by_canon(
    primary: list,
    secondary: list,
    sport: str = "",
    primary_away_key: str = "away_team",
    primary_home_key: str = "home_team",
    secondary_away_key: str = "away_team",
    secondary_home_key: str = "home_team",
    fields_to_merge: list = None,
    threshold: float = 0.82,
) -> list:
    """
    Merge two lists of game dicts using canonical team name matching.
    Replaces SequenceMatcher-only fuzzy merge in vsin_scraper.py.

    For each game in primary, finds the best match in secondary and
    copies fields_to_merge from secondary into primary (if null in primary).

    Returns the merged primary list.
    """
    if fields_to_merge is None:
        fields_to_merge = [
            "spread_bet_pct_home", "spread_handle_pct_home",
            "ml_bet_pct_home", "ml_handle_pct_home",
            "total_over_bet_pct", "total_over_handle_pct",
        ]

    used = set()
    result = []

    for pg in primary:
        p_away = pg.get(primary_away_key, "")
        p_home = pg.get(primary_home_key, "")

        best_i = None
        best_score = 0.0

        for i, sg in enumerate(secondary):
            if i in used:
                continue
            s_away = sg.get(secondary_away_key, "")
            s_home = sg.get(secondary_home_key, "")

            # Try canonical key match first (exact)
            pa_c = canon(p_away, sport).lower()
            ph_c = canon(p_home, sport).lower()
            sa_c = canon(s_away, sport).lower()
            sh_c = canon(s_home, sport).lower()

            if (pa_c == sa_c and ph_c == sh_c) or (pa_c == sh_c and ph_c == sa_c):
                best_i = i
                best_score = 1.0
                break

            # Fuzzy fallback
            score = max(
                (_sim(pa_c, sa_c) + _sim(ph_c, sh_c)) / 2,
                (_sim(pa_c, sh_c) + _sim(ph_c, sa_c)) / 2,
            )
            # Substring boost
            if pa_c in sa_c or sa_c in pa_c:
                score = max(score, 0.85)
            if ph_c in sh_c or sh_c in ph_c:
                score = max(score, 0.85)

            if score > best_score:
                best_score = score
                best_i = i

        game = dict(pg)
        if best_i is not None and best_score >= threshold:
            used.add(best_i)
            sg = secondary[best_i]
            for field in fields_to_merge:
                if game.get(field) is None and sg.get(field) is not None:
                    game[field] = sg[field]

        result.append(game)

    return result


# ---------------------------------------------------------------------------
# Convenience: normalize a player name (for prop matching across books)
# ---------------------------------------------------------------------------

_PLAYER_SUFFIX_RE = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", re.I)
_PLAYER_PREFIX_RE = re.compile(r"^(de|van|von|el|al|le|la|di|da|du|dos|del|della|dell|des|los|las)\s+", re.I)


def canon_player(name: str) -> str:
    """
    Normalize a player name for cross-book matching.
    Strips suffixes (Jr, Sr, II, III), lowercases, strips punctuation.
    """
    if not name:
        return ""
    n = name.strip()
    n = _PLAYER_SUFFIX_RE.sub("", n).strip()
    n = re.sub(r"[.\-']", "", n)
    n = re.sub(r"\s+", " ", n).strip().lower()
    return n


def match_players(a: str, b: str, threshold: float = 0.88) -> bool:
    """Return True if two player name strings refer to the same player."""
    ca, cb = canon_player(a), canon_player(b)
    if ca == cb:
        return True
    if _sim(ca, cb) >= threshold:
        return True
    # Handle camelCase names: LeBron → lebron
    if ca in cb or cb in ca:
        return True
    return False


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        # (a, b, sport, expected_match)
        ("New York Yankees",   "Yankees",            "MLB", True),
        ("NY Yankees",         "New York Yankees",   "MLB", True),
        ("NYY",                "Yankees",            "MLB", True),
        ("Chicago Cubs",       "Chi Cubs",           "MLB", True),
        ("LA Dodgers",         "Los Angeles Dodgers","MLB", True),
        ("Tampa Bay Rays",     "Rays",               "MLB", True),
        ("Athletics",          "Oakland Athletics",  "MLB", True),
        ("Kings",              "Sacramento Kings",   "NBA", True),
        ("Kings",              "LA Kings",           "NHL", True),
        ("Patriots",           "New England Patriots","NFL",True),
        ("Jets",               "New York Jets",      "NFL", True),
        ("Jets",               "Winnipeg Jets",      "NHL", True),
        ("Cardinals",          "Arizona Cardinals",  "NFL", True),
        ("Cardinals",          "St. Louis Cardinals","MLB", True),
        ("Yankees",            "Red Sox",            "MLB", False),
        ("Lakers",             "Celtics",            "NBA", False),
    ]

    print("=== Canon tests ===")
    for name, sport, expected_canon in [
        ("New York Yankees",       "MLB", "Yankees"),
        ("NYY",                    "MLB", "Yankees"),
        ("LA Dodgers",             "MLB", "Dodgers"),
        ("Athletics",              "MLB", "Athletics"),
        ("Kings",                  "NBA", "Sacramento Kings"),
        ("Kings",                  "NHL", "LA Kings"),
        ("New England Patriots",   "NFL", "Patriots"),
        ("St. Louis Cardinals",    "MLB", "Cardinals"),
        ("Arizona Cardinals",      "NFL", "Cardinals"),
    ]:
        result = canon(name, sport)
        status = "✅" if result == expected_canon else f"❌ (got {result!r})"
        print(f"  canon({name!r}, {sport!r}) = {result!r} {status}")

    print("\n=== Match tests ===")
    passed = 0
    for a, b, sport, expected in tests:
        result = match_teams(a, b, sport)
        status = "✅" if result == expected else f"❌ (got {result})"
        print(f"  match({a!r}, {b!r}, {sport!r}) = {result} {status}")
        if result == expected:
            passed += 1

    print(f"\n{passed}/{len(tests)} tests passed")

    print("\n=== Player canon tests ===")
    player_tests = [
        ("LeBron James", "lebron james"),
        ("Michael Jordan Jr.", "michael jordan"),
        ("De'Aaron Fox", "deaaron fox"),
        ("Karl-Anthony Towns", "karlanthony towns"),
    ]
    for raw, expected in player_tests:
        result = canon_player(raw)
        status = "✅" if result == expected else f"❌ (got {result!r})"
        print(f"  canon_player({raw!r}) = {result!r} {status}")
