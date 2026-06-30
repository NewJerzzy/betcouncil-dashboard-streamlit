"""BetCouncil Slip Parser — OCR and text parsing for bet slips."""
import re
import requests

# ── CamelCase name corrections ────────────────────────────────────────────────
# OCR engines often produce "Lebron" or "Mcavid" instead of "LeBron"/"McDavid".
# Map lowercased full name → correct spelling. Applied before any name extraction.
_CAMELCASE_NAMES = {
    "lebron james":       "LeBron James",
    "lebron":             "LeBron",
    "connor mcdavid":     "Connor McDavid",
    "mcdavid":            "McDavid",
    "deandre ayton":      "DeAndre Ayton",
    "deandre hunter":     "DeAndre Hunter",
    "devante parker":     "DeVante Parker",
    "devonta smith":      "DeVonta Smith",
    "devin singletary":   "Devin Singletary",
    "deshaun watson":     "Deshaun Watson",
    "deshawn stevenson":  "DeShawn Stevenson",
    "jalen mcmillan":     "Jalen McMillan",
    "jevon mcnider":      "JeVon McNider",
    "jarvis landry":      "Jarvis Landry",
    "jakobi meyers":      "Jakobi Meyers",
    "kadarius toney":     "Kadarius Toney",
    "kj osborn":          "KJ Osborn",
    "tj watt":            "TJ Watt",
    "tj hockenson":       "TJ Hockenson",
    "tj mcconnell":       "TJ McConnell",
    "aj brown":           "AJ Brown",
    "aj green":           "AJ Green",
    "jt daniels":         "JT Daniels",
    "dj moore":           "DJ Moore",
    "dj uiagalelei":      "DJ Uiagalelei",
    "malik mcdowell":     "Malik McDowell",
    "mac jones":          "Mac Jones",
    "mccaffrey":          "McCaffrey",
    "christian mccaffrey": "Christian McCaffrey",
    "demarvin leal":      "DeMarvion Overshown",
    "jaquan brisker":     "Jaquan Brisker",
    "myles mcbride":      "Miles McBride",
    "andrew mccutchen":   "Andrew McCutchen",
    "collin mchugh":      "Collin McHugh",
    "lance mccullers":    "Lance McCullers",
    "jake mccarthy":      "Jake McCarthy",
    "michael mchenry":    "Michael McHenry",
    "brendan mckay":      "Brendan McKay",
    "lamar jackson":      "Lamar Jackson",
    "desmond ridder":     "Desmond Ridder",
    "devante adams":      "Davante Adams",
    "davante adams":      "Davante Adams",
}

def _fix_camelcase(text: str) -> str:
    """
    Apply CamelCase corrections to OCR text before name extraction.
    Case-insensitive replacement of known name variants.
    """
    for wrong, correct in _CAMELCASE_NAMES.items():
        # Word-boundary aware, case-insensitive
        text = re.sub(r"(?<![A-Za-z])" + re.escape(wrong) + r"(?![A-Za-z])",
                      correct, text, flags=re.IGNORECASE)
    return text


def _parse_pp_ocr_inline(raw_text):
    """Parse single-line OCR text from PrizePicks screenshots. All sports.
    
    Handles two layouts:
    A) Sport tag between each player (old multi-sport layout):
       "... NBA PlayerA NBA PlayerB ..."
    B) Single sport tag at header (current PP layout):
       "MLB ... PlayerA ... PlayerB ... 0.5 Hits+Runs+RBIs Ks"
    """
    import re

    raw_text = re.sub(r"WORLDCUP", "WORLD CUP", raw_text, flags=re.I)
    raw_text = _fix_camelcase(raw_text)

    # Save original for prop extraction (footer strip below may remove stat tokens)
    _raw_for_props = raw_text

    # Strip PrizePicks footer noise for player name extraction
    # Two-column OCR puts stats AFTER the footer, so we preserve them in _raw_for_props
    raw_text = re.sub(r"Slide for Refund.*?(?=\d{1,2}:\d{2}|$)", "", raw_text, flags=re.I|re.S).strip()
    raw_text = re.sub(r"Self refund available[^\n]*", "", raw_text, flags=re.I).strip()
    raw_text = re.sub(r"PRIZEPICKS\s+\w+\s+\d+,\s+\d{4}.*", "", raw_text, flags=re.I).strip()
    raw_text = re.sub(r"\b\d{2}:\d{2}:\d{2}\b", "", raw_text).strip()  # countdown timer HH:MM:SS

    SPORTS = ["WORLD CUP","NBA","WNBA","MLB","NHL","NFL","TENNIS","PGA","MMA","UFC","SOCCER"]
    SKIP_POS = {"P","C","G","F","PG","SG","SF","PF","G-F","C-F","IF","SP","RP","OF","SS","1B","2B","3B",
                "DH","LF","CF","RF","MIDFIELDER","DEFENDER","GOALKEEPER","FORWARD"}
    BANNED = {"FINAL","LEADERBOARD","SHOW","DETAILS","PLAY","FLEX","POWER","WIN","PAY","VS","V","LB",
        "ARI","ATL","BAL","BOS","CHC","CWS","CHI","CIN","CLE","COL","DET","HOU","KC","LAA","LAD",
        "MIA","MIL","MIN","NYM","NYY","OAK","PHI","PIT","SD","SF","SEA","STL","TB","TEX","TOR","WSH",
        "BKN","CHA","DAL","DEN","GSW","IND","MEM","NOP","OKC","ORL","PHX","POR","SAC","SAS","UTA","WAS",
        "CON","LVA","LA","NYL","NY","USA","PAR",
        "MLB","NBA","NHL","NFL","WNBA","MMA","UFC","PGA","TENNIS","SOCCER",
        "AZ","GSV","GSW","NYL","CHI","CHA",
        "SLIDE","SELF","REFUND","REMAINING","TIME","PICK"}
    # Sorted longest-first so compound props match before their substrings
    PROPS = sorted([
        "Pts+Rebs+Asts","Pts+Rebs","Pts+Asts","Assists","Points","Rebounds",
        "Strikeouts","Ks","Total Bases","Hits Allowed","Hits+Runs+RBIs","Hits+Runs+RBls",
        "1st Inning Runs Allowed","H+R+RBI","RBIs","Earned Runs Allowed","Fantasy Score","Pitcher FS","Hitter FS","PRA",
        "Passes Attempted","Goals","Goalie Saves","Saves","Break Points Won","Strokes",
        "Aces","Total Games Won","Runs","Turnovers","Blocks","Steals","3-Pointers","Hits",
    ], key=len, reverse=True)
    # Prop word set for filtering during name extraction (catches partial matches like "Hitter", "Points")
    PROP_WORDS = {"Hitter","Pitcher","Fantasy","Points","Assists","Rebounds","Blocks","Steals",
                  "Turnovers","Runs","Goals","Saves","Strokes","Aces","Score","Allowed","Earned"}

    # ── Header extraction (wager / payout / slip type) ──────────────────────
    _slip_type = ""
    _wager = 0.0
    _payout = 0.0

    _tm = re.search(r"(\d+-Pick\s+(?:Flex|Power)\s+Play)", raw_text, re.I)
    if _tm:
        _slip_type = _tm.group(1)

    # Allow comma-formatted numbers: $1,050  $500
    _wm = re.search(r"\$([\d,]+(?:\.\d+)?)\s+to\s+(?:pay|win|Play)", raw_text, re.I)
    if not _wm:
        _wm = re.search(r"Play\s+\$([\d,]+(?:\.\d+)?)", raw_text, re.I)
    if _wm:
        _wager = float(_wm.group(1).replace(",", ""))

    _pm = re.search(r"(?:pay|win)\s+\$([\d,]+(?:\.\d+)?)", raw_text, re.I)
    if _pm:
        _payout = float(_pm.group(1).replace(",", ""))

    # The green "Win" badge appears as its own standalone line right after
    # the slip-type header (e.g. "4-Pick Flex Play\nWin\n$1.00 to win
    # $1.80"). A prior version matched any "\bWin\b" in the first 200
    # chars, which also matches the word "win" inside the ALWAYS-PRESENT
    # "$X to win $Y" slip-terms phrasing -- that phrase describes the
    # potential payout and is shown identically whether the slip won or
    # lost, so it can't be used as a result signal. PrizePicks has no
    # equivalent "Loss" badge at all -- absence of the Win badge plus all
    # legs Final means the slip lost.
    _header_win = bool(re.search(r"^\s*Win\s*$", raw_text[:200], re.I | re.M))

    # ── Sport tag scan ───────────────────────────────────────────────────────
    sports_re = r"\b(" + "|".join(re.escape(s) for s in SPORTS) + r")\b"
    sport_matches = list(re.finditer(sports_re, raw_text, re.I))
    header_sport = sport_matches[0].group(1).upper() if sport_matches else "MLB"

    # ── PLAYER EXTRACTION ────────────────────────────────────────────────────
    players = []

    # If all sport tags cluster at the start (<20 chars), they're header badges not
    # player separators (happens in two-column OCR reads). Treat entire body as Layout B.
    _tags_spread = len(sport_matches) >= 2 and not all(m.start() < 25 for m in sport_matches)

    if _tags_spread:
        # Layout A: each player block is bracketed by sport tags
        # Layout: "MLB {matchup} {time} {Player} {TEAM}•{POS}•#{N} {stats} MLB ..."
        # The last player comes AFTER the last sport tag (handled by tail extraction)

        def _clean_seg(seg):
            """Strip times, bullets, arrows, jersey numbers, trailing stat section."""
            seg = re.sub(r"\bFinal\b", "", seg, flags=re.I)
            seg = re.sub(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", "", seg, flags=re.I)  # day names
            seg = re.sub(r"\b\d{1,2}:\d{2}(?:\s*[aApP][mM])?\b", "", seg)  # times
            seg = re.sub(r"[\u2022\xB7\u2191\u2193\u2B06\u2B07\u25B2\u25BC]", " ", seg)  # bullets/arrows
            seg = re.sub(r"#\d+(?:/\s*#?\d+)?", "", seg)   # jersey #s
            seg = re.sub(r"\s+\d+(?:\s+[\d.]+).*$", "", seg)  # trailing stats: "0 0.5 Prop..."
            seg = re.sub(r"[/\\]", " ", seg)                 # slash separators
            seg = re.sub(r"\s+", " ", seg).strip()
            return seg

        def _extract_name(seg):
            """Extract player name(s) from cleaned segment, handling combo picks (A + B)."""
            if " + " in seg:
                names = []
                for part in seg.split(" + "):
                    ws = part.split()
                    nw = []
                    for w in reversed(ws):
                        cw = re.sub(r"[^a-zA-Z\'\.-]", "", w)
                        if not cw: continue
                        cup = cw.upper().rstrip(".")
                        if cup in BANNED or cup in SKIP_POS:
                            if nw: break
                            continue
                        if cw[0].isupper():
                            nw.insert(0, cw)
                        if len(nw) >= 2: break
                    if nw:
                        names.append(" ".join(nw))
                return " + ".join(names) if names else ""
            # Single player
            pwords = []
            for w in reversed(seg.split()):
                cw = re.sub(r"[^a-zA-Z\'\.-]", "", w)
                if not cw or len(cw) < 1: continue
                cup = cw.upper().rstrip(".")
                if cup in SKIP_POS or cup in BANNED:
                    if len(pwords) >= 2: break
                    continue
                if cw in PROP_WORDS and len(pwords) >= 2: break
                if cw[0].isupper():
                    pwords.insert(0, cw)
                if len(pwords) >= 2: break
            return " ".join(pwords) if len(pwords) >= 2 else ""

        for idx, sm in enumerate(sport_matches):
            sport = sm.group(1).upper()
            prev_end = sport_matches[idx-1].end() if idx > 0 else 0
            seg = raw_text[prev_end:sm.start()]
            seg = _clean_seg(seg)
            pname = _extract_name(seg)
            if pname:
                players.append({"player": pname, "sport": sport, "book": "PrizePicks"})

        # Tail: last player appears AFTER the final sport tag
        _last_sm = sport_matches[-1]
        _tail = _clean_seg(raw_text[_last_sm.end():])
        _tname = _extract_name(_tail)
        if _tname and not any(p["player"] == _tname for p in players):
            players.append({"player": _tname, "sport": _last_sm.group(1).upper(), "book": "PrizePicks"})

    else:
        # Layout B: single sport tag at header OR clustered badges — scan for "Firstname Lastname" patterns
        # Strip everything up to and including the slip type line
        body = raw_text
        if _tm:
            body = raw_text[_tm.end():]
        # Remove time tokens (11:10am) so they don't confuse name detection
        body = re.sub(r"\b\d{1,2}:\d{2}(?:am|pm)\b", "", body, flags=re.I)
        # Replace bullet chars with spaces
        body = re.sub(r"[•·]", " ", body)
        # Remove standalone all-caps tokens that are team codes / positions
        body = re.sub(r"\b([A-Z]{1,4})\b", lambda m: " " if m.group(1) in BANNED or m.group(1) in SKIP_POS else m.group(1), body)
        # Remove title-case status/noise words (e.g. "Final") that the all-caps strip above
        # misses because OCR renders them title-case, not all-caps. Without this, "Final"
        # gets glued onto the next title-case run and swallowed into the player name match.
        body = re.sub(r"\bFinal\b", " ", body, flags=re.I)
        # Strip known prop labels (e.g. "Total Bases", "Fantasy Score", "3-Pointers") before
        # name matching. Without this, a prop label sitting directly next to the following
        # player's name (no separator left after OCR/footer cleanup) merges into one
        # title-case run and gets misread as part of the player name, e.g.
        # "Total Bases Shohei Ohtani" or "3-Pointers Nikola Jokic".
        for _p in PROPS:
            body = re.sub(r"\b" + re.escape(_p) + r"\b", " ", body, flags=re.I)
        # Strip single-word prop labels too (e.g. "Points" as a standalone, or as the lead
        # word swallowed into "Points Stephen Curry"). These must go BEFORE name matching,
        # not just be filtered after: re.finditer finds non-overlapping matches, so a match
        # like "Points Stephen Curry" consumes the whole span — even if rejected post-hoc
        # for containing "Points", the real name "Stephen Curry" was already consumed and
        # never gets a second chance to match on its own.
        for _pw in sorted(PROP_WORDS, key=len, reverse=True):
            body = re.sub(r"\b" + re.escape(_pw) + r"(?:ers|s)?\b", " ", body, flags=re.I)
        body = re.sub(r"\s+", " ", body).strip()

        # Find "Firstname Lastname" — title-cased, at least 2 words, ≥2 chars each.
        # Each word allows ONE internal capital+lowercase run (Mc/Le/De/Van/Mac
        # prefixes) so camelCase names like LeBron, McDavid, DeAndre match too —
        # previously the plain [A-Z][a-z']+ pattern broke on the second internal
        # capital and silently failed to match these names at all. Still requires
        # a lowercase letter in every word, so bare acronyms (NBA, MLB) can't match
        # on their own (and BANNED/PROP_WORDS filtering below catches them anyway).
        _NAME_WORD = r"[A-Z](?:[a-z']+[A-Z][a-z']*|[a-z']+)"
        name_re = re.compile(rf"\b({_NAME_WORD}(?:\s+{_NAME_WORD})+)\b")
        for m in name_re.finditer(body):
            name = m.group(1).strip()
            parts = name.split()
            # Skip if any part is a banned word
            if any(p.upper() in BANNED or p.upper() in SKIP_POS for p in parts):
                continue
            # Skip if the whole phrase is actually a prop label (e.g. "Total Bases",
            # "Fantasy Score") rather than a player name — mirrors the PROP_WORDS
            # filtering already used in the Layout A name extractor.
            if any(p in PROP_WORDS for p in parts) or name in PROPS:
                continue
            if len(parts) >= 2 and all(len(p) >= 2 for p in parts):
                players.append({"player": name, "sport": header_sport, "book": "PrizePicks"})

    # ── PROP / LINE EXTRACTION ────────────────────────────────────────────────
    # Use original raw text (pre-footer-strip) for prop extraction so two-column
    # OCR layouts (where stats appear after the footer) still get their lines
    _prop_source = _raw_for_props
    _has_final = bool(re.search(r"\bFinal\b", _prop_source, re.I))
    # NOTE: settled multi-pick slips show "Final" once PER LEG (each pick's game has its
    # own status marker), not once as a single header banner. The previous version assumed
    # a single occurrence and truncated everything before the LAST "Final", which silently
    # discarded every earlier leg's prop/line data on 2+ pick settled slips. Strip each
    # occurrence in place instead so all legs' data survives.
    clean = re.sub(r"\bFinal\b", " ", _prop_source, flags=re.I)

    # Strip time tokens and fix comma-numbers before scanning for lines
    clean = re.sub(r"\b\d{1,2}:\d{2}(?:am|pm)\b", "", clean, flags=re.I)
    clean = re.sub(r"\$([\d,]+)", lambda m: "$" + m.group(1).replace(",", ""), clean)
    clean = re.sub(r"&\s*'t", "", clean)
    clean = re.sub(r"\b\d+/\d+\b", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    props_re = r"\b(" + "|".join(re.escape(p) for p in PROPS) + r")\b"
    prop_matches = list(re.finditer(props_re, clean, re.I))

    metrics = []
    for pidx, pm in enumerate(prop_matches):
        lead_start = prop_matches[pidx-1].end() if pidx > 0 else 0
        lead = clean[lead_start:pm.start()].strip()
        has_x = "x" in lead.lower().split()
        # "Did not play" / DNP legs are voided by PrizePicks (push, not a
        # real win or loss) -- e.g. a player scratched after the slip was
        # placed. Without this check, a DNP leg's actual=0 would be
        # compared against its line and almost always score as a false
        # LOSS, even on slips PrizePicks itself still paid out.
        _is_dnp = bool(re.search(r"did not play", lead, re.I))
        trail_end = prop_matches[pidx+1].start() if pidx+1 < len(prop_matches) else len(clean)
        trail = clean[pm.end():trail_end].strip()
        # Exclude dollar-prefixed numbers when scanning for lines
        pre_nums = re.findall(r"(?<!\$)\b(\d+(?:\.\d+)?)\b", lead)
        post_nums = re.findall(r"(?<!\$)\b(\d+(?:\.\d+)?)\b", trail)
        actual = 0.0
        line = 0.0
        if _has_final:
            # Settled: pre_nums[-1] = line, post_nums[0] = actual
            if pre_nums:
                line = float(pre_nums[-1])
            if post_nums:
                actual = float(post_nums[0])
        else:
            # Pending: pre_nums[-1] is the line (printed before prop name)
            if pre_nums:
                line = float(pre_nums[-1])
            elif post_nums:
                line = float(post_nums[0])
        # result_raw stores the OVER-side result; it is corrected for UNDER
        # bets in the COMBINE loop below once entry["side"] is known.
        # A prior version's fallback clause ("WIN" if actual > 0 else
        # "LOSS") scored ANY nonzero actual stat as a win regardless of
        # whether it actually cleared the line -- e.g. actual=5 vs line=6
        # (a real loss) was being scored WIN simply because 5 > 0. Fixed
        # to a direct actual-vs-line comparison with no such fallback.
        if _is_dnp:
            result_raw = "PUSH"
        elif has_x:
            result_raw = "LOSS"
        elif line > 0:
            result_raw = "WIN" if actual >= line else "LOSS"
        else:
            # No usable line was extracted -- can't determine a real
            # result, so don't fabricate one either direction.
            result_raw = "PENDING"
        prop_name = pm.group(1)
        # Normalize prop aliases
        prop_name = re.sub(r"(?i)^Ks$", "Strikeouts", prop_name)
        prop_name = re.sub(r"RBls", "RBIs", prop_name)
        metrics.append({"prop": prop_name, "actual": actual, "line": line, "result": result_raw, "side": "OVER"})

    # ── NAME SANITY FILTER ───────────────────────────────────────────────────
    # Reject garbled names from OCR artifacts: prop words, month fragments, keywords
    _INVALID_NAME_TOKENS = {
        "OVER","UNDER","MORE","LESS","PRIZEPICKS","UNDERDOG","PARLAY","PLAY",
        "AM","PM","JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC",
        "MON","TUE","WED","THU","FRI","SAT","SUN",
        "RUNS","HITS","KS","PRA","RBI","RBIS","FS","HITTER","PITCHER","FANTASY",
        "1ST","2ND","3RD","INNING","ALLOWED","POINTS","REBOUNDS","ASSISTS","STRIKEOUTS"
    }
    _PROP_SUBSTRINGS = ["hits", "runs", "rbis", "rbl", "strikeout", "pitcherfs", "hitterfs"]

    def _is_valid_name(name):
        if not name or len(name.strip()) < 4:
            return False
        for part in re.split(r"\s+", name.strip()):
            if part in ("+", ""):
                continue
            clean = re.sub(r"[^a-zA-Z]", "", part).upper()
            if not clean:
                continue
            if clean in _INVALID_NAME_TOKENS:
                return False
            if part == part.upper() and len(clean) > 4:
                return False
        name_flat = name.lower().replace(" ", "").replace("+", "")
        return not any(s in name_flat and len(name_flat) > len(s) + 2 for s in _PROP_SUBSTRINGS)

    players = [p for p in players if _is_valid_name(p["player"])]

    # ── PENDING DETECTION ────────────────────────────────────────────────────
    _is_pending = not _has_final and not _header_win
    # No payout-vs-wager fallback: _payout is parsed from the static "to
    # pay $X" / "to win $X" slip-terms text, which is identical whether
    # the slip won or lost (it describes the potential payout, not an
    # actual result) -- using it as a win signal was the root cause of
    # losing slips being misreported as WIN. The only reliable overall
    # signal is the explicit Win badge; its absence on a fully-settled
    # (all legs Final) slip means LOSS.
    _overall = "PENDING" if _is_pending else ("WIN" if _header_win else "LOSS")

    # Arrow-based OVER/UNDER (↑=OVER ↓=UNDER)
    _arrow_sides = ["OVER" if a in "↑⬆▲" else "UNDER"
                    for a in re.findall(r"[↑↓⬆⬇▲▼]", raw_text)]

    # ── COMBINE ──────────────────────────────────────────────────────────────
    out = []
    if len(players) != len(metrics):
        import warnings
        warnings.warn(
            f"[slip_parser] player/metric count mismatch: {len(players)} players, "
            f"{len(metrics)} metrics — {abs(len(players)-len(metrics))} leg(s) will be dropped",
            stacklevel=2,
        )
    for i in range(min(len(players), len(metrics))):
        entry = {**players[i], **metrics[i]}
        entry["wager"] = _wager if i == 0 else 0.0
        entry["payout"] = _payout if i == 0 else 0.0
        entry["slip_type"] = _slip_type
        entry["overall_result"] = _overall
        if i < len(_arrow_sides):
            entry["side"] = _arrow_sides[i]
        # Correct result for UNDER bets: flip WIN/LOSS when side is UNDER.
        # The raw result was computed assuming OVER (actual >= line = WIN).
        # For UNDER legs, WIN requires actual <= line.
        _side = entry.get("side", "OVER")
        _act  = entry.get("actual") or 0.0
        _ln   = entry.get("line") or 0.0
        _raw  = entry.get("result", "")
        if _side == "UNDER" and not _is_pending and _ln > 0 and _act is not None and entry.get("result") != "PUSH":
            entry["result"] = "WIN" if _act <= _ln else "LOSS"
        if _is_pending:
            entry["result"] = "PENDING"
            entry["outcome"] = "PENDING"
            entry["actual"] = None
        elif entry.get("result") in ("WIN", "LOSS", "PUSH"):
            # Trust the real per-leg actual-vs-line computation (or PUSH
            # for a voided/DNP leg). A Flex Play parlay can win overall
            # with one or more legs having individually missed their
            # number (that's the whole point of Flex Play -- it pays out
            # on partial hits) -- a prior version forced every leg's
            # outcome to match the overall slip result, which silently
            # overwrote real per-leg losses as wins on any winning
            # multi-pick slip. overall_result (already stored above) is
            # kept as the separate slip-level fact; this field is the
            # individual leg's own result.
            # is the individual leg's own result.
            entry["outcome"] = entry["result"]
        else:
            # No usable per-leg actual/line was extracted -- only fall
            # back to the slip-level result as a last resort.
            entry["result"] = _overall
            entry["outcome"] = _overall
        out.append(entry)
    return out


def parse_bovada_slip_text(text: str) -> list:
    """Parse Bovada text slip into bet records.

    Edge-case hardening:
    - All float() / int() calls guarded against ValueError from bad OCR.
    - Leg regex accepts both LF and CRLF line endings.
    - Sport inferred from slip text rather than hardcoded to MLB.
    """
    import re
    bets = []
    if not text or not any(x in text.lower() for x in ['parlay', 'straight bet', 'ref.']):
        return bets
    try:
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        tl = text.lower()

        # Infer sport from text — fall back to MLB if unrecognisable
        _SPORT_HINTS = [
            (["nba", "basketball"], "NBA"),
            (["nfl", "football"], "NFL"),
            (["nhl", "hockey"], "NHL"),
            (["soccer", "mls", "epl", "premier league"], "SOCCER"),
            (["tennis"], "TENNIS"),
            (["ufc", "mma"], "MMA"),
        ]
        sport = "MLB"
        for hints, sname in _SPORT_HINTS:
            if any(h in tl for h in hints):
                sport = sname
                break

        # Outcome — check the explicit WIN/LOSS status line first since
        # it's the most reliable signal; fall back to parsing a winnings
        # dollar amount only if no explicit status line is found. A prior
        # version checked "winnings" in tl FIRST and, if that branch's
        # regex failed to extract a number (e.g. real Bovada slips show
        # "Winnings\n+ $7.29" with a leading + sign the old regex didn't
        # handle), it never fell through to check the Win/Loss line at
        # all -- silently leaving every real winning/losing slip as
        # PENDING even though the status was right there in the text.
        outcome = "PENDING"
        if "\nloss\n" in tl or tl.strip().endswith("loss"):
            outcome = "LOSS"
        elif "\nwin\n" in tl or tl.strip().endswith("win"):
            outcome = "WIN"
        elif "winnings" in tl:
            win_match = re.search(r'winnings\s*\n?\s*[+\-]?\s*\$?\s*([\d.]+)', tl)
            if win_match:
                try:
                    winnings = float(win_match.group(1))
                    outcome = "WIN" if winnings > 0 else "LOSS"
                except ValueError:
                    pass

        # Wager
        wager = 0.0
        risk_match = re.search(r'risk\s*\$?\s*([\d,]+(?:\.\d+)?)', tl)
        if risk_match:
            try:
                wager = float(risk_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Bet type
        parlay_match = re.search(r'(\d+)\s+team\s+parlay', tl)
        n_picks = 1
        if parlay_match:
            try:
                n_picks = int(parlay_match.group(1))
            except ValueError:
                pass

        # Parse each leg — each leg is a 3-line block: matchup, date/time,
        # then the actual pick line with odds (e.g. "Under 10.5 (-110)
        # (Game) Total"). A prior version only captured 2 lines, which
        # grabbed the date as the "pick" and silently produced zero bets
        # since the date line never matches the odds pattern below.
        # Accepts both LF and CRLF line endings.
        legs = re.findall(r'\*\s+(.+?)\s*\r?\n(.+?)\r?\n(.+?)(?:\r?\n|$)', text, re.MULTILINE)
        date_str = ""
        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
        if date_match:
            date_str = date_match.group(1)

        for matchup, _leg_date, pick_line in legs:
            matchup = matchup.strip()
            pick_line = pick_line.strip()
            pick_match = re.match(r'^(.+?)\s*\(([+-]?\d+)\)', pick_line)
            if pick_match:
                team_pick = pick_match.group(1).strip()
                odds = pick_match.group(2)
                market = "Moneyline" if "moneyline" in pick_line.lower() else pick_line.split(")")[-1].strip()
                bets.append({
                    "player": matchup, "prop": market, "line": 0,
                    "side": team_pick, "sport": sport,
                    "outcome": outcome, "wager": wager / max(1, n_picks),
                    "pick_count": n_picks, "bet_type": "game",
                    "source": "Bovada", "date": date_str,
                    "odds": odds, "tier": "LEAN", "edge": 0, "prob": 0.5
                })

        if not bets and outcome != "PENDING":
            bets.append({
                "player": "Bovada Parlay", "prop": f"{n_picks}-Team Parlay",
                "line": 0, "side": "WIN", "sport": sport,
                "outcome": outcome, "wager": wager, "pick_count": n_picks,
                "bet_type": "game", "source": "Bovada", "date": date_str,
                "tier": "LEAN", "edge": 0, "prob": 0.5
            })
    except Exception as _e:
        import warnings
        warnings.warn(f"[slip_parser] parse_bovada_slip_text failed: {type(_e).__name__}: {_e}", stacklevel=2)
    return bets


def parse_mybookie_slip_text(text: str) -> list:
    """Parse MyBookie text slip into bet records.

    Edge-case hardening:
    - All float() calls guarded against ValueError from bad OCR.
    - Sport inferred from slip text rather than hardcoded to MLB.
    - Full function wrapped in try/except so a bad slip never crashes the caller.
    """
    import re
    bets = []
    if not text:
        return bets
    try:
      tl = text.lower()

      # Infer sport from text — fall back to MLB
      _SPORT_HINTS = [
          (["nba", "basketball"], "NBA"),
          (["nfl", "football"], "NFL"),
          (["nhl", "hockey"], "NHL"),
          (["soccer", "mls", "epl", "premier league"], "SOCCER"),
          (["tennis"], "TENNIS"),
          (["ufc", "mma"], "MMA"),
      ]
      sport = "MLB"
      for hints, sname in _SPORT_HINTS:
          if any(h in tl for h in hints):
              sport = sname
              break

      # Outcome — ONLY trust an explicit settled-status indicator. A
      # prior version also matched on the literal "Win: <amount>" text,
      # but MyBookie shows that label as the POTENTIAL PAYOUT on every
      # slip, settled or not (e.g. "Risk: 1.00 Win: 1.89" on a slip with
      # no result yet) -- that heuristic was misclassifying still-open,
      # unresolved bets as already-won, which would have logged fake
      # wins into history the moment an unsettled slip was submitted.
      outcome = "PENDING"
      if "straight bet - win" in tl:
          outcome = "WIN"
      elif "straight bet - loss" in tl:
          outcome = "LOSS"

      # Wager
      wager = 0.0
      risk_match = re.search(r'risk:\s*([\d,]+(?:\.\d+)?)', tl)
      if risk_match:
          try:
              wager = float(risk_match.group(1).replace(",", ""))
          except ValueError:
              pass

      lines = text.splitlines()
      date_str = ""
      team_odds_pattern = re.compile(r'^(.+?)\s*\(\s*.+?\s*\)\s*([+-]\d+)\s*$')
      legs = []
      for i, line in enumerate(lines):
          m = team_odds_pattern.match(line.strip())
          if m:
              team = m.group(1).strip()
              odds = m.group(2).strip()
              for j in range(i, min(i+5, len(lines))):
                  date_m = re.search(r'Game Date:\s*(.+)', lines[j])
                  if date_m and not date_str:
                      date_str = date_m.group(1).strip()[:10]
              legs.append({"team": team, "odds": odds})

      n_picks = max(1, len(legs))
      for leg in legs:
          bets.append({
              "player": leg["team"],
              "prop": "Moneyline",
              "line": 0,
              "side": leg["team"],
              "sport": sport,
              "outcome": outcome,
              "wager": round(wager / n_picks, 2),
              "pick_count": n_picks,
              "bet_type": "game",
              "source": "MyBookie",
              "date": date_str,
              "odds": leg["odds"],
              "tier": "LEAN",
              "edge": 0,
              "prob": 0.5
          })

      if not bets and outcome != "PENDING":
          bets.append({
              "player": "MyBookie Bet", "prop": "Moneyline",
              "line": 0, "side": "WIN", "sport": sport,
              "outcome": outcome, "wager": wager, "pick_count": 1,
              "bet_type": "game", "source": "MyBookie", "date": date_str,
              "tier": "LEAN", "edge": 0, "prob": 0.5
          })
    except Exception as _e:
        import warnings
        warnings.warn(f"[slip_parser] parse_mybookie_slip_text failed: {type(_e).__name__}: {_e}", stacklevel=2)
    return bets
