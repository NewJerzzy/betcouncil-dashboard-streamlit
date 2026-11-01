"""Conservative ESPN grading: ambiguous identities, DNPs and markets stay unresolved."""

import re
import unicodedata
from datetime import datetime


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]", "", value.lower())


def outcome(margin):
    return "win" if margin > 0 else "loss" if margin < 0 else "push"


def number(value):
    value = str(value).replace("−", "-").replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        raise ValueError("missing/non-numeric ESPN statistic")
    return float(value)


def players(summary):
    found = {}
    for team in summary.get("boxscore", {}).get("players", []):
        for group in team.get("statistics", []):
            keys = group.get("keys", [])
            category = group.get("name") or group.get("type") or "general"
            if "fullInnings.partInnings" in keys:
                category = "pitching"
            elif "hits-atBats" in keys:
                category = "batting"
            for row in group.get("athletes", []):
                if row.get("didNotPlay") or not row.get("stats"):
                    continue
                athlete = row.get("athlete", {})
                pid = athlete.get("id")
                if not pid:
                    continue
                entry = found.setdefault(pid, {"athlete": athlete, "groups": {}, "team": team.get("team", {})})
                entry["groups"][category] = dict(zip(keys, row["stats"]))
    return found


def identify_player(title, pool):
    ranked = []
    for pid, item in pool.items():
        a = item["athlete"]
        display = a.get("displayName", "")
        last = a.get("lastName") or " ".join(display.split()[1:])
        first = a.get("firstName") or display.split()[0]
        aliases = [display, a.get("shortName"), (first[:1] + last), last]
        # Suffix-less spelling is accepted only if identity remains unique.
        aliases += [re.sub(r"\b(?:Jr|Sr|III|II)\.?\b", "", name or "", flags=re.I) for name in aliases]
        lengths = [len(norm(alias)) for alias in aliases if len(norm(alias)) >= 3 and norm(title).startswith(norm(alias))]
        if lengths:
            ranked.append((max(lengths), pid))
    if not ranked:
        raise ValueError("player absent from ESPN box score or name not identified")
    best = max(n for n, _ in ranked)
    ids = [pid for n, pid in ranked if n == best]
    if len(ids) != 1:
        raise ValueError("ambiguous ESPN player identity")
    return ids[0]


def _stat(player, key, category=None):
    groups = player["groups"]
    search = [groups.get(category, {})] if category else groups.values()
    values = [g[key] for g in search if key in g]
    if not values:
        raise ValueError("ESPN statistic not provided")
    if len(set(values)) != 1:
        raise ValueError("conflicting ESPN statistics")
    return values[0]


def player_value(title, player, pid, summary, sport):
    text = title.lower()
    stat = lambda key, cat=None: number(_stat(player, key, cat))
    if sport == "MLB":
        pitch = "pitching" if (
            ("pitching" in player["groups"] and "batting" not in player["groups"])
            or any(s in text for s in ("pitcher", "allowed", "earned run", " er", " ks", "strikeout"))
        ) and "batter" not in text else "batting"
        if re.search(r"\bouts\b", text):
            innings = str(_stat(player, "fullInnings.partInnings", "pitching"))
            whole, _, fraction = innings.partition(".")
            if fraction not in ("", "0", "1", "2"):
                raise ValueError("invalid innings fraction")
            return int(whole) * 3 + int(fraction or 0), "pitcher_outs"
        if "total bases" in text:
            # Exactly one terminal hit play per at-bat, independently reconciled
            # with the batter's box-score hit and home-run totals.
            hit_types = {"single": 1, "double": 2, "triple": 3, "home-run": 4}
            hits = {}
            for play in summary.get("plays", []):
                kind = play.get("type", {}).get("type")
                if kind not in hit_types:
                    continue
                batters = [x for x in play.get("participants", []) if x.get("type") == "batter" and str(x.get("athlete", {}).get("id")) == pid]
                if batters:
                    hits[play.get("atBatId") or play["id"]] = hit_types[kind]
            if len(hits) != stat("hits", "batting") or sum(v == 4 for v in hits.values()) != stat("homeRuns", "batting"):
                raise ValueError("total bases play-by-play incomplete")
            return sum(hits.values()), "batter_total_bases"
        if re.search(r"hits\s*\+\s*runs\s*\+\s*rbis|h/r/rbi|hrrbi", text):
            return sum(stat(k, "batting") for k in ("hits", "runs", "RBIs")), "batter_hits_runs_rbis"
        if "earned run" in text or re.search(r"\ber\b", text):
            return stat("earnedRuns", "pitching"), "pitcher_earned_runs"
        if "strikeout" in text or re.search(r"\bks\b", text):
            return stat("strikeouts", pitch), pitch + "_strikeouts"
        if "hits allowed" in text:
            return stat("hits", "pitching"), "pitcher_hits_allowed"
        if "home run" in text or re.search(r"\bhr\b", text):
            return stat("homeRuns", "batting"), "batter_home_runs"
        if "walk" in text:
            return stat("walks", pitch), pitch + "_walks"
        if re.search(r"\bhits\b", text):
            return stat("hits", "batting"), "batter_hits"
        if "rbi" in text:
            return stat("RBIs", "batting"), "batter_rbis"
        if " sb" in text or "stolen" in text:
            raise ValueError("stolen bases absent from ESPN basic box score")
    if sport in ("NFL", "CFB", "NCAAF"):
        if re.search(r"\b(?:1st|first|last)\s+td\b", text):
            raise ValueError("first/last TD requires ordered scorer verification")
        if "anytime" in text or re.search(r"\batd\b|\btd(?:\s+yes)?$", text):
            # Only grade an offensive scorer when rushing/receiving TD columns
            # are present. An absent player is never treated as an Under win.
            vals = [number(g[k]) for g in player["groups"].values() for k in ("rushingTouchdowns", "receivingTouchdowns", "kickReturnTouchdowns", "puntReturnTouchdowns", "defensiveTouchdowns", "interceptionTouchdowns") if k in g]
            if not vals:
                raise ValueError("touchdown participation evidence missing")
            return sum(vals), "player_anytime_td"
        if ("rush" in text or "rushing" in text) and ("rec" in text or "receiv" in text):
            return stat("rushingYards", "rushing") + stat("receivingYards", "receiving"), "player_rush_rec_yards"
        if "longest" in text and ("reception" in text or "rec" in text):
            return stat("longReception", "receiving"), "player_longest_reception"
        if "longest" in text and "rush" in text:
            return stat("longRushing", "rushing"), "player_longest_rush"
        if "tackles" in text:
            return stat("totalTackles", "defensive"), "player_tackles_assists"
        if "interception" in text or re.search(r"\bints?\b", text):
            return stat("interceptions", "passing"), "player_passing_interceptions"
        if "pass td" in text or "passing td" in text:
            return stat("passingTouchdowns", "passing"), "player_passing_tds"
        if "comp" in text:
            return number(str(_stat(player, "completions/passingAttempts", "passing")).split("/")[0]), "player_completions"
        if "pass att" in text:
            return number(str(_stat(player, "completions/passingAttempts", "passing")).split("/")[1]), "player_pass_attempts"
        if "pass" in text:
            return stat("passingYards", "passing"), "player_pass_yards"
        if "carries" in text or ("rush" in text and ("attempt" in text or " att" in text)):
            return stat("rushingAttempts", "rushing"), "player_rush_attempts"
        if "reception" in text or re.search(r"\brecs\b", text):
            return stat("receptions", "receiving"), "player_receptions"
        if "receiv" in text or " rec " in text:
            return stat("receivingYards", "receiving"), "player_rec_yards"
        if "rush" in text:
            return stat("rushingYards", "rushing"), "player_rush_yards"
    if sport == "NBA":
        if "pra" in text or ("pts" in text and "rebs" in text and "asts" in text):
            return sum(stat(k) for k in ("points", "rebounds", "assists")), "player_pra"
        if "3pm" in text or "3pt" in text:
            return number(str(_stat(player, "threePointFieldGoalsMade-threePointFieldGoalsAttempted")).split("-")[0]), "player_threes"
        if "assist" in text or "ast" in text:
            return stat("assists"), "player_assists"
        if "reb" in text:
            return stat("rebounds"), "player_rebounds"
        if "point" in text or "pts" in text:
            return stat("points"), "player_points"
    raise ValueError("unsupported or ambiguous player market")


def identify_team(title, competitors):
    ranks = []
    for c in competitors:
        t = c["team"]
        aliases = [t.get(k) for k in ("displayName", "shortDisplayName", "location", "name", "abbreviation")]
        aliases.append((t.get("name") or "").split()[-1] if t.get("name") else "")
        scores = [len(norm(a)) for a in aliases if norm(a) and norm(title).startswith(norm(a))]
        if scores:
            ranks.append((max(scores), c))
    if not ranks:
        raise ValueError("selected team not identified")
    best = max(v for v, _ in ranks)
    choices = [c for v, c in ranks if v == best]
    if len(choices) != 1:
        raise ValueError("ambiguous selected team")
    return choices[0]


def grade_pick(pick, event, summary, issue=None):
    row = {**pick, "verified": None, "issue": issue, "profit": None, "flat_profit": None}
    if not event or issue:
        return row
    row["espn_id"] = event["id"]
    league = {"CFB": "college-football", "NCAAF": "college-football"}.get(str(pick["sport"]).upper(), str(pick["sport"]).lower())
    row["espn_url"] = "https://www.espn.com/" + league + "/boxscore/_/gameId/" + event["id"]
    try:
        title = pick["bet_title"]
        kind = str(pick.get("bet_type") or "").lower()
        sport = str(pick["sport"]).upper()
        if "parlay" in kind or re.search(r"parlay|sgp|\+\s*(?:[a-z]+\s+ml|.*\btd\b)", title, re.I):
            raise ValueError("multi-leg selection requires every leg and settlement rules")
        if kind == "prop":
            pool = players(summary)
            pid = identify_player(title, pool)
            actual, market = player_value(title, pool[pid], pid, summary, sport)
            ou = re.search(r"\b(over|under|o|u)\s*(\d+(?:\.\d+)?)", title, re.I)
            alt = re.search(r"(\d+(?:\.\d+)?)\+", title)
            if market == "player_anytime_td":
                line, margin = 0.5, actual - 0.5
            elif ou:
                line = float(ou[2])
                margin = (actual - line) * (1 if ou[1].lower().startswith("o") else -1)
            elif alt:
                line = float(alt[1])
                margin = 1 if actual >= line else -1
            else:
                raise ValueError("missing threshold or direction")
            row.update(actual=actual, line=line, market=market, espn_player_id=pid, espn_player=pool[pid]["athlete"]["displayName"])
        else:
            competitors = event["competitions"][0]["competitors"]
            period = None
            q = re.search(r"(?:\bq([1-4])(?:_|\b)|\b([1-4])(?:st|nd|rd|th)\s+quarter)", kind + " " + title, re.I)
            if q:
                period = [int(q[1] or q[2])]
            elif "first_half" in kind or re.search(r"\b1h\b", title, re.I):
                period = [1, 2]
            elif "second_half" in kind or re.search(r"\b2h\b", title, re.I):
                period = list(range(3, 10))
            elif "first_inning" in kind or re.search(r"\b(?:1st\s+inning|first\s+inning|f1|nrfi|yrfi)\b", title, re.I):
                period = [1]
            elif re.search(r"\b(?:f5|first\s+5)\b", title, re.I):
                period = [1, 2, 3, 4, 5]
            scores = {}
            for c in competitors:
                if period:
                    lines = c.get("linescores") or next((t.get("linescores") for t in summary.get("header", {}).get("competitions", [{}])[0].get("competitors", []) if t["team"]["id"] == c["team"]["id"]), None)
                    if not lines or any(i <= 4 and i > len(lines) for i in period):
                        raise ValueError("ESPN period scores missing")
                    scores[c["id"]] = sum(number(lines[i - 1].get("value", lines[i - 1].get("displayValue"))) for i in period if i <= len(lines))
                else:
                    scores[c["id"]] = number(c["score"])
            ou = re.search(r"\b(over|under|o|u)\s*(\d+(?:\.\d+)?)", title, re.I)
            if "first_inning" in kind and re.search(r"\b(?:nrfi|yrfi)\b", title, re.I):
                ou = re.search(r"(under|over) (\d\.\d)", "under 0.5" if "nrfi" in title.lower() else "over 0.5")
            if "total" in kind and ou:
                actual = scores[identify_team(title, competitors)["id"]] if "team_total" in kind else sum(scores.values())
                line = float(ou[2])
                margin = (actual - line) * (1 if ou[1].lower().startswith("o") else -1)
            elif "moneyline" in kind or kind in ("spread", "runline") or "_spread" in kind:
                selected = identify_team(title, competitors)
                other = next(c for c in competitors if c["id"] != selected["id"])
                actual = scores[selected["id"]] - scores[other["id"]]
                spread = re.search(r"([+-]\d+(?:\.\d+)?)", title)
                if "moneyline" in kind:
                    line = 0
                elif spread:
                    line = float(spread[1])
                else:
                    raise ValueError("original handicap missing")
                margin = actual + line
            else:
                raise ValueError("unsupported/ambiguous game market")
            row.update(actual=actual, line=line, market=kind, periods=period)
        odds = number(pick["odds"])
        stake = number(pick["units"])
        if abs(odds) < 100 or stake <= 0:
            raise ValueError("invalid original price or units")
        result = outcome(margin)
        flat = (odds / 100 if odds > 0 else 100 / abs(odds)) if result == "win" else -1 if result == "loss" else 0
        posted = datetime.fromisoformat(str(pick.get("posted_at") or pick["created_at"]).replace("Z", "+00:00"))
        start = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        source_result = {"won": "win", "lost": "loss"}.get(pick["result"], pick["result"])
        row.update(
            verified=result, profit=flat * stake, flat_profit=flat,
            posted_before_espn_start=posted < start,
            provider_result_match=(result == source_result) if source_result in ("win", "loss", "push") else None,
        )
    except (KeyError, ValueError, TypeError, StopIteration, IndexError) as exc:
        row.update(issue=str(exc), verified=None, profit=None, flat_profit=None)
    return row


def summarize(rows):
    def stats(values):
        decided = [r for r in values if r.get("verified") and not r.get("duplicate_of") and r.get("result") in ("win", "loss", "push", "won", "lost")]
        stake = sum(float(r["units"]) for r in decided)
        profit = sum(r["profit"] for r in decided)
        return {
            "graded": len(decided), "wins": sum(r["verified"] == "win" for r in decided),
            "losses": sum(r["verified"] == "loss" for r in decided),
            "pushes": sum(r["verified"] == "push" for r in decided), "units_risked": stake,
            "profit": profit, "roi_pct": 100 * profit / stake if stake else None,
            "flat_profit": sum(r["flat_profit"] for r in decided),
            "grade_disagreements": sum(r["provider_result_match"] is False for r in decided),
        }
    verified = [r for r in rows if r.get("verified")]
    unresolved = [r for r in rows if not r.get("verified")]
    return {
        "retrieved": len(rows), "outcomes": stats(verified),
        "duplicates": sum(bool(r.get("duplicate_of")) for r in rows),
        "source_ungraded": sum(r.get("result") not in ("win", "loss", "push", "won", "lost") for r in rows),
        "posted_before_espn_start": stats([r for r in verified if r["posted_before_espn_start"]]),
        "at_or_after_espn_start": len([r for r in verified if not r["posted_before_espn_start"]]),
        "by_sport": {s: stats([r for r in verified if str(r["sport"]).upper() == s]) for s in sorted({str(r["sport"]).upper() for r in verified})},
        "unresolved": len(unresolved),
        "unresolved_reasons": {reason: sum(r["issue"] == reason for r in unresolved) for reason in sorted({r["issue"] for r in unresolved})},
    }
