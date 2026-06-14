"""BetCouncil Slip Parser — OCR and text parsing for bet slips."""
import re
import requests


def _parse_pp_ocr_inline(raw_text):
    """Parse single-line OCR text from PrizePicks screenshots. All sports."""
    import re
    # Normalize WORLDCUP → WORLD CUP
    raw_text = re.sub(r"WORLDCUP", "WORLD CUP", raw_text, flags=re.I)
    
    SPORTS = ["WORLD CUP","NBA","WNBA","MLB","NHL","NFL","TENNIS","PGA","MMA","UFC","SOCCER"]
    SKIP_POS = {"P","C","G","F","PG","SG","SF","PF","G-F","C-F","IF","SP","RP","OF","SS","1B","2B","3B",
                "MIDFIELDER","DEFENDER","GOALKEEPER","FORWARD"}
    BANNED = {"FINAL","LEADERBOARD","SHOW","DETAILS","PLAY","FLEX","POWER","WIN","PAY","VS","V",
        "ARI","ATL","BAL","BOS","CHC","CWS","CHI","CIN","CLE","COL","DET","HOU","KC","LAA","LAD",
        "MIA","MIL","MIN","NYM","NYY","OAK","PHI","PIT","SD","SF","SEA","STL","TB","TEX","TOR","WSH",
        "BKN","CHA","DAL","DEN","GSW","IND","MEM","NOP","OKC","ORL","PHX","POR","SAC","SAS","UTA","WAS",
        "CON","LVA","LA","NYL","NY","USA","PAR"}
    PROPS = ["Pts+Rebs+Asts","Pts+Rebs","Pts+Asts","Assists","Points","Rebounds",
        "Strikeouts","Ks","Total Bases","Hits Allowed","Hits","RBIs","Earned Runs Allowed",
        "Fantasy Score","Pitcher FS","Hitter FS","Passes Attempted","Goals","Goalie Saves",
        "Saves","Break Points Won","Strokes","Aces","Total Games Won","H+R+RBI","Runs",
        "Turnovers","Blocks","Steals","Rebounds","3-Pointers"]

    # Extract wager, payout, slip type
    _wager = 0.0
    _payout = 0.0
    _slip_type = ""
    _tm = re.search(r"(\d+-Pick\s+(?:Flex|Power)\s+Play)", raw_text, re.I)
    if _tm: _slip_type = _tm.group(1)
    _wm = re.search(r"\$([\d.]+)\s+to\s+(?:pay|win|Play)", raw_text, re.I)
    if not _wm: _wm = re.search(r"Play\s+\$([\d.]+)", raw_text, re.I)
    if _wm: _wager = float(_wm.group(1))
    _pm = re.search(r"(?:pay|win)\s+\$([\d.]+)", raw_text, re.I)
    if _pm: _payout = float(_pm.group(1))
    _header_win = bool(re.search(r"\bWin\b", raw_text[:200], re.I))

    # Step 1: Find all players by sport tag positions
    sports_re = r"\b(" + "|".join(re.escape(s) for s in SPORTS) + r")\b"
    sport_matches = list(re.finditer(sports_re, raw_text, re.I))
    
    players = []
    for idx, sm in enumerate(sport_matches):
        sport = sm.group(1).upper()
        prev_end = sport_matches[idx-1].end() if idx > 0 else 0
        seg = raw_text[prev_end:sm.start()].strip()
        seg = re.sub(r".*?Play\s+.*?\$[\d.]+.*?(?:Leaderboard|Show details|\bv\b)", "", seg, flags=re.I).strip()
        seg = re.sub(r"\bFinal\b", "", seg, flags=re.I).strip()
        words = seg.split()
        pwords = []
        for w in reversed(words):
            cw = re.sub(r"[^a-zA-Z\'-]", "", w)
            if not cw or len(cw) < 2: continue
            if cw.upper() in SKIP_POS or cw.upper() in BANNED: 
                if len(pwords) >= 2: break
                continue
            if cw[0].isupper():
                pwords.insert(0, cw)
            if len(pwords) >= 2 and all(len(x) >= 2 for x in pwords): break
        pname = " ".join(pwords) if len(pwords) >= 2 else ""
        pname = re.sub(r"^Final\\s+", "", pname, flags=re.I).strip()
        if pname:
            players.append({"player": pname, "sport": sport, "book": "PrizePicks"})

    # Step 2: Find all prop metrics anywhere in text
    # Step 2: Extract metrics AFTER last "Final" cluster only
    # Prevents matchup scores (85, 106) from contaminating prop data
    props_re = r"\b(" + "|".join(re.escape(p) for p in PROPS) + r")\b"
    _final_matches = list(re.finditer(r"Final", raw_text, re.I))
    if _final_matches:
        clean = raw_text[_final_matches[-1].end():]
    else:
        clean = raw_text
    clean = re.sub(r"&\s*'t", "", clean)
    clean = re.sub(r"\b\d+/\d+\b", "", clean)
    clean = re.sub(r"\bFinal\b", "", clean, flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip()
    met_pattern = r"(x)?\s*(\d+\.?\d*)\s+(.+?)\s+(\d+)"
    prop_matches = list(re.finditer(props_re, clean, re.I))
    
    metrics = []
    for pidx, pm in enumerate(prop_matches):
        lead_start = prop_matches[pidx-1].end() if pidx > 0 else 0
        lead = clean[lead_start:pm.start()].strip()
        has_x = "x" in lead.lower().split()
        trail_end = prop_matches[pidx+1].start() if pidx+1 < len(prop_matches) else len(clean)
        trail = clean[pm.end():trail_end].strip()
        nums = re.findall(r"\d+(?:\.\d+)?", trail)
        # Also check for numbers BEFORE the prop (line is often before prop name)
        pre_nums = re.findall(r"\d+(?:\.\d+)?", lead)
        actual, line = 0.0, 0.0
        if nums:
            actual = float(nums[0])
        if pre_nums:
            line = float(pre_nums[-1])
        if line == 0 and len(nums) >= 2:
            actual, line = float(nums[0]), float(nums[1])
        # Swap if needed (line should be the target, actual the result)
        result = "LOSS" if has_x else ("WIN" if actual >= line and line > 0 else "WIN" if actual > 0 else "LOSS")
        prop_clean = "Strikeouts" if pm.group(1).lower() == "ks" else pm.group(1)
        metrics.append({"prop": prop_clean, "actual": actual, "line": line, "result": result, "side": "OVER"})

    # Step 3: Combine and apply header win override
    _overall = "WIN" if _header_win or (_payout > _wager and _payout > 0) else "LOSS"
    out = []
    for i in range(min(len(players), len(metrics))):
        entry = {**players[i], **metrics[i]}
        entry["wager"] = _wager if i == 0 else 0.0
        entry["payout"] = _payout if i == 0 else 0.0
        entry["slip_type"] = _slip_type
        entry["overall_result"] = _overall
        if _header_win:
            entry["result"] = "WIN"
            entry["outcome"] = "WIN"
        elif not entry.get("result") or entry.get("result") not in ("WIN","LOSS"):
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

    # Parse each leg - Bovada format: "* Team1 @ Team2 / WinningTeam (odds)(type) Market"
    legs = re.findall(r'\*\s+(.+?)\s*\n(.+?)(?:\n|$)', text, re.MULTILINE)
    date_str = ""
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
    if date_match:
        date_str = date_match.group(1)

    for matchup, pick_line in legs:
        matchup = matchup.strip()
        pick_line = pick_line.strip()
        # Extract team and odds from pick line: "Detroit Tigers (-310)(Live Game) Moneyline"
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

    # If no legs parsed but we have outcome, create a single record
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

    # Parse each leg using line-by-line approach
    # MyBookie format: "Team Name ( Pitcher1 / Pitcher2 )-ODDS"
    lines = text.splitlines()
    date_str = ""
    team_odds_pattern = re.compile(r'^(.+?)\s*\(\s*.+?\s*\)\s*([+-]\d+)\s*$')
    legs = []
    for i, line in enumerate(lines):
        m = team_odds_pattern.match(line.strip())
        if m:
            team = m.group(1).strip()
            odds = m.group(2).strip()
            # Look for game date nearby
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



