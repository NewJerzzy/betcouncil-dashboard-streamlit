"""BetCouncil Slip Parser — OCR and text parsing for bet slips."""
import re
import requests


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

    SPORTS = ["WORLD CUP","NBA","WNBA","MLB","NHL","NFL","TENNIS","PGA","MMA","UFC","SOCCER"]
    SKIP_POS = {"P","C","G","F","PG","SG","SF","PF","G-F","C-F","IF","SP","RP","OF","SS","1B","2B","3B",
                "DH","LF","CF","RF","MIDFIELDER","DEFENDER","GOALKEEPER","FORWARD"}
    BANNED = {"FINAL","LEADERBOARD","SHOW","DETAILS","PLAY","FLEX","POWER","WIN","PAY","VS","V","LB",
        "ARI","ATL","BAL","BOS","CHC","CWS","CHI","CIN","CLE","COL","DET","HOU","KC","LAA","LAD",
        "MIA","MIL","MIN","NYM","NYY","OAK","PHI","PIT","SD","SF","SEA","STL","TB","TEX","TOR","WSH",
        "BKN","CHA","DAL","DEN","GSW","IND","MEM","NOP","OKC","ORL","PHX","POR","SAC","SAS","UTA","WAS",
        "CON","LVA","LA","NYL","NY","USA","PAR",
        "MLB","NBA","NHL","NFL","WNBA","MMA","UFC","PGA","TENNIS","SOCCER"}
    # Sorted longest-first so compound props match before their substrings
    PROPS = sorted([
        "Pts+Rebs+Asts","Pts+Rebs","Pts+Asts","Assists","Points","Rebounds",
        "Strikeouts","Ks","Total Bases","Hits Allowed","Hits+Runs+RBIs","Hits+Runs+RBls",
        "H+R+RBI","RBIs","Earned Runs Allowed","Fantasy Score","Pitcher FS","Hitter FS",
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

    _header_win = bool(re.search(r"\bWin\b", raw_text[:200], re.I))

    # ── Sport tag scan ───────────────────────────────────────────────────────
    sports_re = r"\b(" + "|".join(re.escape(s) for s in SPORTS) + r")\b"
    sport_matches = list(re.finditer(sports_re, raw_text, re.I))
    header_sport = sport_matches[0].group(1).upper() if sport_matches else "MLB"

    # ── PLAYER EXTRACTION ────────────────────────────────────────────────────
    players = []

    if len(sport_matches) >= 2:
        # Layout A: sport tag appears between each player block
        for idx, sm in enumerate(sport_matches):
            sport = sm.group(1).upper()
            prev_end = sport_matches[idx-1].end() if idx > 0 else 0
            seg = raw_text[prev_end:sm.start()].strip()
            seg = re.sub(r".*?Play\s+.*?\$[\d,.]+.*?(?:Leaderboard|Show details|\bv\b)", "", seg, flags=re.I).strip()
            seg = re.sub(r"\bFinal\b", "", seg, flags=re.I).strip()
            # Strip stat/line section (everything from first digit onward — stats follow player info)
            seg = re.sub(r"\d.*$", "", seg).strip()
            # Strip arrows, bullets, jersey numbers
            seg = re.sub(r"[\u2191\u2193\u2B06\u2B07\u25B2\u25BC#\u2022\xB7]", " ", seg)
            seg = re.sub(r"\s+", " ", seg).strip()
            words = seg.split()
            pwords = []
            for w in reversed(words):
                cw = re.sub(r"[^a-zA-Z\'-]", "", w)
                if not cw or len(cw) < 2:
                    continue
                if cw.upper() in SKIP_POS or cw.upper() in BANNED:
                    if len(pwords) >= 2:
                        break
                    continue
                # Stop if we hit a standalone prop word (e.g. "Hitter", "Points")
                if cw in PROP_WORDS and len(pwords) >= 2:
                    break
                if cw[0].isupper():
                    pwords.insert(0, cw)
                if len(pwords) >= 2 and all(len(x) >= 2 for x in pwords):
                    break
            pname = " ".join(pwords) if len(pwords) >= 2 else ""
            pname = re.sub(r"^Final\s+", "", pname, flags=re.I).strip()
            if pname:
                players.append({"player": pname, "sport": sport, "book": "PrizePicks"})


        # Also extract the player after the LAST sport tag (loop only covers segments before tags)
        _last_sm = sport_matches[-1]
        _tail = raw_text[_last_sm.end():].strip()
        _tail = re.sub(r'\d.*$', '', _tail).strip()
        _tail = re.sub(r'[\u2191\u2193\u2B06\u2B07\u25B2\u25BC#\u2022\xB7]', ' ', _tail)
        _tail = re.sub(r'\bFinal\b', '', _tail, flags=re.I)
        _tail = re.sub(r'\s+', ' ', _tail).strip()
        _twords = _tail.split()
        _tpwords = []
        for _tw in reversed(_twords):
            _tcw = re.sub(r'[^a-zA-Z\'-]', '', _tw)
            if not _tcw or len(_tcw) < 2: continue
            if _tcw.upper() in SKIP_POS or _tcw.upper() in BANNED:
                if len(_tpwords) >= 2: break
                continue
            if _tcw in PROP_WORDS and len(_tpwords) >= 2: break
            if _tcw[0].isupper(): _tpwords.insert(0, _tcw)
            if len(_tpwords) >= 2 and all(len(x) >= 2 for x in _tpwords): break
        _tname = ' '.join(_tpwords) if len(_tpwords) >= 2 else ''
        if _tname and not any(p['player'] == _tname for p in players):
            players.append({'player': _tname, 'sport': _last_sm.group(1).upper(), 'book': 'PrizePicks'})
    else:
        # Layout B: single sport tag at header — scan for "Firstname Lastname" patterns
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
        body = re.sub(r"\s+", " ", body).strip()

        # Find "Firstname Lastname" — title-cased, at least 2 words, ≥2 chars each
        name_re = re.compile(r"\b([A-Z][a-z']+(?:\s+[A-Z][a-z']+)+)\b")
        for m in name_re.finditer(body):
            name = m.group(1).strip()
            parts = name.split()
            # Skip if any part is a banned word
            if any(p.upper() in BANNED or p.upper() in SKIP_POS for p in parts):
                continue
            if len(parts) >= 2 and all(len(p) >= 2 for p in parts):
                players.append({"player": name, "sport": header_sport, "book": "PrizePicks"})

    # ── PROP / LINE EXTRACTION ────────────────────────────────────────────────
    _has_final = bool(re.search(r"\bFinal\b", raw_text, re.I))
    if _has_final:
        _final_matches = list(re.finditer(r"\bFinal\b", raw_text, re.I))
        clean = raw_text[_final_matches[-1].end():]
    else:
        clean = raw_text

    # Strip time tokens and fix comma-numbers before scanning for lines
    clean = re.sub(r"\b\d{1,2}:\d{2}(?:am|pm)\b", "", clean, flags=re.I)
    clean = re.sub(r"\$([\d,]+)", lambda m: "$" + m.group(1).replace(",", ""), clean)
    clean = re.sub(r"&\s*'t", "", clean)
    clean = re.sub(r"\b\d+/\d+\b", "", clean)
    clean = re.sub(r"\bFinal\b", "", clean, flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip()

    props_re = r"\b(" + "|".join(re.escape(p) for p in PROPS) + r")\b"
    prop_matches = list(re.finditer(props_re, clean, re.I))

    metrics = []
    for pidx, pm in enumerate(prop_matches):
        lead_start = prop_matches[pidx-1].end() if pidx > 0 else 0
        lead = clean[lead_start:pm.start()].strip()
        has_x = "x" in lead.lower().split()
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
        result = "LOSS" if has_x else ("WIN" if actual >= line and line > 0 else "WIN" if actual > 0 else "LOSS")
        prop_name = pm.group(1)
        # Normalize prop aliases
        prop_name = re.sub(r"(?i)^Ks$", "Strikeouts", prop_name)
        prop_name = re.sub(r"RBls", "RBIs", prop_name)
        metrics.append({"prop": prop_name, "actual": actual, "line": line, "result": result, "side": "OVER"})

    # ── PENDING DETECTION ────────────────────────────────────────────────────
    _is_pending = not _has_final and not _header_win
    _overall = "PENDING" if _is_pending else ("WIN" if _header_win or (_payout > _wager and _payout > 0) else "LOSS")

    # Arrow-based OVER/UNDER (↑=OVER ↓=UNDER)
    _arrow_sides = ["OVER" if a in "↑⬆▲" else "UNDER"
                    for a in re.findall(r"[↑↓⬆⬇▲▼]", raw_text)]

    # ── COMBINE ──────────────────────────────────────────────────────────────
    out = []
    for i in range(min(len(players), len(metrics))):
        entry = {**players[i], **metrics[i]}
        entry["wager"] = _wager if i == 0 else 0.0
        entry["payout"] = _payout if i == 0 else 0.0
        entry["slip_type"] = _slip_type
        entry["overall_result"] = _overall
        if i < len(_arrow_sides):
            entry["side"] = _arrow_sides[i]
        if _is_pending:
            entry["result"] = "PENDING"
            entry["outcome"] = "PENDING"
            entry["actual"] = None
        elif _header_win:
            entry["result"] = "WIN"
            entry["outcome"] = "WIN"
        elif not entry.get("result") or entry.get("result") not in ("WIN", "LOSS"):
            entry["result"] = _overall
            entry["outcome"] = _overall
        else:
            entry["outcome"] = entry.get("result", _overall)
        out.append(entry)
    return out


def parse_bovada_slip_text(text: str) -> list:
    """Parse Bovada text slip into bet records."""
    import re
    bets = []
    if not text or not any(x in text.lower() for x in ['parlay', 'straight bet', 'ref.']):
        return bets
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    tl = text.lower()

    # Outcome
    outcome = "PENDING"
    if "winnings" in tl:
        win_match = re.search(r'winnings\s*\$?\s*([\d.]+)', tl)
        if win_match:
            winnings = float(win_match.group(1))
            outcome = "WIN" if winnings > 0 else "LOSS"
    elif "\nloss\n" in tl or tl.strip().endswith("loss"):
        outcome = "LOSS"
    elif "\nwin\n" in tl or tl.strip().endswith("win"):
        outcome = "WIN"

    # Wager
    wager = 0.0
    risk_match = re.search(r'risk\s*\$?\s*([\d.]+)', tl)
    if risk_match:
        wager = float(risk_match.group(1))

    # Bet type
    parlay_match = re.search(r'(\d+)\s+team\s+parlay', tl)
    is_parlay = bool(parlay_match)
    n_picks = int(parlay_match.group(1)) if parlay_match else 1

    # Parse each leg
    legs = re.findall(r'\*\s+(.+?)\s*\n(.+?)(?:\n|$)', text, re.MULTILINE)
    date_str = ""
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
    if date_match:
        date_str = date_match.group(1)

    for matchup, pick_line in legs:
        matchup = matchup.strip()
        pick_line = pick_line.strip()
        pick_match = re.match(r'^(.+?)\s*\(([+-]?\d+)\)', pick_line)
        if pick_match:
            team_pick = pick_match.group(1).strip()
            odds = pick_match.group(2)
            market = "Moneyline" if "moneyline" in pick_line.lower() else pick_line.split(")")[-1].strip()
            bets.append({
                "player": matchup, "prop": market, "line": 0,
                "side": team_pick, "sport": "MLB",
                "outcome": outcome, "wager": wager / max(1, n_picks),
                "pick_count": n_picks, "bet_type": "game",
                "source": "Bovada", "date": date_str,
                "odds": odds, "tier": "LEAN", "edge": 0, "prob": 0.5
            })

    if not bets and outcome != "PENDING":
        bets.append({
            "player": "Bovada Parlay", "prop": f"{n_picks}-Team Parlay",
            "line": 0, "side": "WIN", "sport": "MLB",
            "outcome": outcome, "wager": wager, "pick_count": n_picks,
            "bet_type": "game", "source": "Bovada", "date": date_str,
            "tier": "LEAN", "edge": 0, "prob": 0.5
        })
    return bets


def parse_mybookie_slip_text(text: str) -> list:
    """Parse MyBookie text slip into bet records."""
    import re
    bets = []
    if not text:
        return bets
    tl = text.lower()

    # Outcome
    outcome = "PENDING"
    if "straight bet - win" in tl or tl.rstrip().endswith("win"):
        outcome = "WIN"
    elif "straight bet - loss" in tl or tl.rstrip().endswith("loss"):
        outcome = "LOSS"
    elif re.search(r'win:\s*0\.00', tl):
        outcome = "LOSS"
    elif re.search(r'win:\s*[1-9]', tl):
        outcome = "WIN"

    # Wager
    wager = 0.0
    risk_match = re.search(r'risk:\s*([\d.]+)', tl)
    if risk_match:
        wager = float(risk_match.group(1))

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
            "sport": "MLB",
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
            "line": 0, "side": "WIN", "sport": "MLB",
            "outcome": outcome, "wager": wager, "pick_count": 1,
            "bet_type": "game", "source": "MyBookie", "date": date_str,
            "tier": "LEAN", "edge": 0, "prob": 0.5
        })
    return bets
