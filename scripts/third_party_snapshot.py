"""
third_party_snapshot.py — daily snapshot of comparison-source picks, for backtesting
================================================================================

Stage 1 of 2 (see third_party_backtest.py for stage 2 — grading).

Every comparison source added to the New Bettor tab / Player Lookup this
session (FavoredProps, DraftEdge, Dimers) is currently display-only —
none of them are wired into compute_multi_signal_edge. To find out
whether any of them are actually predictive enough to justify wiring in,
this snapshots each source's picks daily; third_party_backtest.py grades
yesterday's snapshot the next day using the exact same ground-truth
resolvers (resolve_actual_stat_for_grading / resolve_actual_game_result_
for_grading) that already grade BetCouncil's own board every day.

Scope, stated plainly rather than overclaimed: FavoredProps/DraftEdge/
Dimers read their own persisted Gist harvester output directly.
BettingPros/Covers/DK-Most-Bet don't have a persisted Gist file, but all
three already have standalone, session-independent fetch functions in
fetchers.py (no Streamlit dependency) — this script calls those
directly. DK Most Bet needed one extra step: its raw data embeds the
player name inside a "Market" text field with no clean separator from
the stat type, so it's matched against the player names already
collected from FavoredProps/DraftEdge in the same run, and skipped if no
match is found (no guessing). LineStar/Situational-Splits/NBA-Trailing-
Splits aren't "picks" at all — they're context stats with no win/loss to
grade against. Backtesting those needs a completely different validation
approach (a feature-correlation study, not a hit-rate grade) — not
attempted here.

This script only reads existing source Gist files and writes a snapshot
history file. It never touches compute_multi_signal_edge, SEM, or any
signal weight — promoting a source from "backtested" to "live signal"
is a separate, explicit, human decision, not something this pipeline
does on its own.
"""

import json
import os
import re
import sys
from datetime import date, timedelta

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
SNAPSHOT_FILE = "betcouncil_third_party_snapshots.json"
SPORTS = ["MLB", "NBA", "NHL", "WNBA", "NFL"]


def log(msg: str) -> None:
    print(f"[third_party_snapshot] {msg}", flush=True)


def gist_read(filename: str):
    # Authenticated: unauthenticated Gist API calls share a 60/h limit and were
    # silently returning None (-> 0 records) for most sources.
    _tok = os.environ.get("GITHUB_TOKEN", "")
    resp = requests.get(f"https://api.github.com/gists/{GIST_ID}", timeout=20,
                        headers={"Authorization": f"Bearer {_tok}"} if _tok else {})
    if resp.status_code != 200:
        log(f"  gist_read({filename}): HTTP {resp.status_code}")
        return None
    f = resp.json().get("files", {}).get(filename)
    if not f:
        return None
    content = f.get("content", "")
    if f.get("truncated") or not content:
        content = requests.get(f["raw_url"], timeout=20).text
    try:
        return json.loads(content) if content.strip() else None
    except json.JSONDecodeError:
        return None


def gist_write(token: str, filename: str, payload) -> bool:
    import time
    for attempt in range(4):
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"files": {filename: {"content": json.dumps(payload)}}},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return True
        if resp.status_code == 409 and attempt < 3:
            time.sleep((attempt + 1) * 5)
            continue
        log(f"gist_write({filename}) failed: {resp.status_code} {resp.text[:200]}")
        return False
    return False


def snapshot_lineterminal(today: str) -> list:
    records = []
    for sport in ("MLB", "WNBA"):
        data = gist_read(f"betcouncil_lineterminal_props_{sport}.json")
        if not data:
            continue
        for game in data.get("games", []):
            for p in game.get("props", []):
                v = p.get("verdict", {}) or {}
                if not v.get("recommend") or not v.get("side"):
                    continue
                if not (p.get("player_name") and p.get("stat_label") and p.get("point") is not None):
                    continue
                records.append({
                    "source": "lineterminal", "sport": sport, "player": p["player_name"],
                    "prop_type": p["stat_label"], "line": p["point"], "side": v["side"].upper(),
                    "implied_prob": v.get("model_prob_pct") / 100.0 if v.get("model_prob_pct") is not None else None,
                })
    return records


def snapshot_favoredprops(today: str) -> list:
    # FavoredProps now lives in ONE combined Gist file keyed "<kind>_<SPORT>";
    # the old per-sport files no longer exist, so this tracker silently
    # recorded 0 picks until fixed.
    records = []
    combined = gist_read("betcouncil_favoredprops_combined.json") or {}
    for sport in SPORTS:
        for kind in ("dfs", "sportsbook"):
            data = combined.get(f"{kind}_{sport}") or {}
            for row in data.get("props", []):
                bet = str(row.get("bet", "")).upper()
                side = "OVER" if bet.startswith("O") else ("UNDER" if bet.startswith("U") else None)
                if not (row.get("player") and row.get("stat_type") and row.get("line") is not None and side):
                    continue
                records.append({
                    "source": "favoredprops", "sport": sport, "player": row["player"],
                    "prop_type": row["stat_type"], "line": row["line"], "side": side,
                    "implied_prob": row.get("avg_pr"),
                })
    return records


def snapshot_draftedge(today: str) -> list:
    records = []
    for sport in SPORTS:
        data = gist_read(f"betcouncil_draftedge_{sport}.json")
        if not data:
            continue
        for row in data.get("props", []):
            player = row.get("Player") or row.get("name")
            if not player:
                continue
            # MLB shape: per-stat sections (HitsSection/HRSection/etc), each
            # with a Line + implied over/under if the book line is present.
            for stat_name, section_key in [("Hits", "HitsSection"), ("HR", "HRSection"),
                                            ("RBI", "RBISection"), ("TB", "TBSection"),
                                            ("SB", "SBSection")]:
                sec = row.get(section_key)
                if not isinstance(sec, dict) or sec.get("Line") is None:
                    continue
                implied_over = sec.get("Implied_Over")
                side = "OVER" if (implied_over or 0) >= 0.5 else "UNDER"
                records.append({
                    "source": "draftedge", "sport": sport, "player": player,
                    "prop_type": stat_name, "line": sec["Line"], "side": side,
                    "implied_prob": implied_over,
                })
    return records


def snapshot_dimers(today: str) -> list:
    records = []
    for sport in SPORTS:
        data = gist_read(f"betcouncil_dimers_{sport}.json")
        if not data:
            continue
        for dm in data.get("matches", []):
            match_meta = dm.get("match", {})
            home = match_meta.get("HomeTeam", {})
            away = match_meta.get("AwayTeam", {})
            home_abv = home.get("Abv", "") if isinstance(home, dict) else ""
            away_abv = away.get("Abv", "") if isinstance(away, dict) else ""
            if not (home_abv and away_abv):
                continue
            tab = dm.get("betting", {}).get("tab", {})
            h_edge, a_edge = tab.get("HomeH2HEdge"), tab.get("AwayH2HEdge")
            if not (isinstance(h_edge, (int, float)) and isinstance(a_edge, (int, float))):
                continue
            side = "HOME" if h_edge > a_edge else "AWAY"
            records.append({
                "source": "dimers", "sport": sport, "matchup": f"{away_abv} @ {home_abv}",
                "home": home_abv, "away": away_abv, "market": "MONEYLINE", "pick": side,
                "line": 0, "implied_prob": tab.get("HomeLineWinPct") if side == "HOME" else tab.get("AwayLineWinPct"),
            })
    return records


def snapshot_covers(today: str) -> list:
    """
    fetch_covers_consensus(sport) -> {matchup_str: {away_pct, home_pct}}.
    Public betting %, not a model pick — treat the more-bet side as the
    "pick" for grading purposes (same convention used elsewhere for
    public-consensus sources), so it can still be graded against actual
    results even though it isn't really a prediction claim on Covers'
    part.
    """
    sys.path.insert(0, ".")
    from fetchers import fetch_covers_consensus

    records = []
    for sport in SPORTS:
        try:
            consensus = fetch_covers_consensus(sport)
        except Exception as e:
            log(f"  covers/{sport}: error — {e}")
            continue
        if not isinstance(consensus, dict):
            continue
        for matchup, pct in consensus.items():
            if not isinstance(pct, dict):
                continue
            home_pct, away_pct = pct.get("home_pct"), pct.get("away_pct")
            if not (isinstance(home_pct, (int, float)) and isinstance(away_pct, (int, float))):
                continue
            parts = matchup.replace(" @ ", " ").split(" ")
            teams = [t for t in parts if len(t) > 2]
            if len(teams) < 2:
                continue
            side = "HOME" if home_pct > away_pct else "AWAY"
            records.append({
                "source": "covers", "sport": sport, "matchup": matchup,
                "home": teams[-1], "away": teams[0], "market": "MONEYLINE", "pick": side,
                "line": 0, "implied_prob": max(home_pct, away_pct) / 100 if max(home_pct, away_pct) > 1 else max(home_pct, away_pct),
            })
    return records


MLB_TEAM_ABBR = {
    "arizona": "AZ", "atlanta": "ATL", "baltimore": "BAL", "boston": "BOS",
    "chicago cubs": "CHC", "cubs": "CHC", "chicago white sox": "CWS", "white sox": "CWS",
    "cincinnati": "CIN", "cleveland": "CLE", "colorado": "COL", "detroit": "DET",
    "houston": "HOU", "kansas city": "KC", "los angeles angels": "LAA", "angels": "LAA",
    "los angeles dodgers": "LAD", "dodgers": "LAD", "miami": "MIA", "milwaukee": "MIL",
    "minnesota": "MIN", "new york yankees": "NYY", "yankees": "NYY",
    "new york mets": "NYM", "mets": "NYM", "athletics": "ATH", "oakland": "ATH",
    "philadelphia": "PHI", "pittsburgh": "PIT", "san diego": "SD",
    "san francisco": "SF", "seattle": "SEA", "st. louis": "STL", "st louis": "STL",
    "tampa bay": "TB", "texas": "TEX", "toronto": "TOR", "washington": "WSH",
}

WAGERBIRD_MARKET_PATTERNS = [
    # (regex, market, group->pick logic)
    (re.compile(r"^(.+?)\s+ML$"), "MONEYLINE"),
    (re.compile(r"^(.+?)\s+([+-]\d+(?:\.\d+)?)$"), "RUN_LINE"),
    (re.compile(r"^(.+?)\s+F5\s+Team\s+Total\s+(Over|Under)\s*([\d.]+)?$", re.I), "F5_TEAM_TOTAL"),
    (re.compile(r"^(.+?)\s+First\s+5\s+Team\s+Total\s+(Over|Under)\s*([\d.]+)?$", re.I), "F5_TEAM_TOTAL"),
    (re.compile(r"^(.+?)\s+Team\s+Total\s+(Over|Under)\s*([\d.]+)?$", re.I), "TEAM_TOTAL"),
    (re.compile(r"^Game\s+Total\s+(Over|Under)\s*([\d.]+)?$", re.I), "GAME_TOTAL"),
]


def _team_to_abbr(name: str):
    n = name.lower().strip()
    if n in MLB_TEAM_ABBR:
        return MLB_TEAM_ABBR[n]
    for k, v in MLB_TEAM_ABBR.items():
        if k in n or n in k:
            return v
    return None


def snapshot_wagerbird(today: str) -> list:
    """
    Parses betcouncil_wagerbird_picks.json (written by wagerbird_refresh.py)
    into the same game-record schema used by dimers/covers/bettingpros above.
    WagerBird's `pick_text` is a short human title ("San Diego ML", "Arizona
    +1.5", "Baltimore F5 Team Total Under 2.5", "Game Total Under 10.5") with
    no separate structured market/side fields, so it's parsed here via
    regex rather than trusted as already-structured — not verified against
    resolve_actual_game_result_for_grading before this first deploy, so a
    100% UNGRADABLE rate on the first backtest run would mean the team-name
    -> abbreviation mapping or market string doesn't match what that
    resolver expects, not that WagerBird's data is bad.
    Team-total lines with no number in the title (e.g. "Houston Team Total
    Under" with the actual number only in the prose rationale) are skipped
    rather than guessed — line=None records are dropped, not graded.
    """
    data = gist_read("betcouncil_wagerbird_picks.json")
    if not data:
        return []
    records = []
    for p in data.get("picks", []):
        matchup = p.get("matchup") or ""
        pick_text = (p.get("pick_text") or "").strip()
        if " @ " not in matchup or not pick_text:
            continue
        away_abv, home_abv = [x.strip() for x in matchup.split(" @ ", 1)]

        market, pick, line = None, None, None

        m = re.match(r"^(.+?)\s+ML$", pick_text)
        if m:
            team_abv = _team_to_abbr(m.group(1)) or m.group(1).strip().upper()
            if team_abv in (home_abv, away_abv):
                market, pick, line = "MONEYLINE", ("HOME" if team_abv == home_abv else "AWAY"), 0
        if market is None:
            m = re.match(r"^(.+?)\s+([+-]\d+(?:\.\d+)?)$", pick_text)
            if m:
                team_abv = _team_to_abbr(m.group(1)) or m.group(1).strip().upper()
                if team_abv in (home_abv, away_abv):
                    market = "RUN_LINE"
                    pick = "HOME" if team_abv == home_abv else "AWAY"
                    line = float(m.group(2))
        if market is None:
            m = re.match(r"^(.+?)\s+(?:F5|First\s+5)\s+Team\s+Total\s+(Over|Under)\s*([\d.]+)?$", pick_text, re.I)
            if m and m.group(3):
                team_abv = _team_to_abbr(m.group(1)) or m.group(1).strip().upper()
                market, pick, line = "F5_TEAM_TOTAL", m.group(2).upper(), float(m.group(3))
                if team_abv not in (home_abv, away_abv):
                    market = None
        if market is None:
            m = re.match(r"^(.+?)\s+Team\s+Total\s+(Over|Under)\s*([\d.]+)?$", pick_text, re.I)
            if m and m.group(3):
                team_abv = _team_to_abbr(m.group(1)) or m.group(1).strip().upper()
                market, pick, line = "TEAM_TOTAL", m.group(2).upper(), float(m.group(3))
                if team_abv not in (home_abv, away_abv):
                    market = None
        if market is None:
            m = re.match(r"^Game\s+Total\s+(Over|Under)\s*([\d.]+)?$", pick_text, re.I)
            if m and m.group(2):
                market, pick, line = "GAME_TOTAL", m.group(1).upper(), float(m.group(2))

        if not (market and pick is not None and line is not None):
            continue  # unparsed title shape or missing line — skip rather than guess

        records.append({
            "source": "wagerbird", "sport": "MLB", "matchup": matchup,
            "home": home_abv, "away": away_abv, "market": market, "pick": pick,
            "line": line, "implied_prob": None,
            "wagerbird_tier": p.get("tier"), "wagerbird_score": p.get("confidence_score"),
        })
    return records


def snapshot_bettingpros(today: str) -> list:
    """
    fetch_bettingpros_from_gist(sport) -> (data, source_tag). Exact field
    names for the "python_direct" path weren't verified live before this
    first deploy — parsed defensively; if the real shape differs this
    will just under-produce records rather than crash, and the next run's
    debug won't silently look identical since gradable count will show it.
    """
    sys.path.insert(0, ".")
    try:
        from fetchers import fetch_bettingpros_from_gist
    except ImportError:
        log("  bettingpros: fetch_bettingpros_from_gist no longer exists in fetchers.py (removed as dead code 2026-07-26) -- skipping this snapshot section")
        return []

    records = []
    raw_samples = []
    for sport in SPORTS:
        try:
            data, _tag = fetch_bettingpros_from_gist(sport)
        except Exception as e:
            log(f"  bettingpros/{sport}: error — {e}")
            continue
        picks = data if isinstance(data, list) else data.get("picks", data.get("data", [])) if isinstance(data, dict) else []
        if sport == "MLB" and len(raw_samples) < 1:
            raw_samples.append({"sport": sport, "tag": _tag,
                                 "data_type": type(data).__name__,
                                 "data_keys": list(data.keys())[:20] if isinstance(data, dict) else None,
                                 "picks_sample": picks[:2] if isinstance(picks, list) else str(picks)[:500]})
        if not isinstance(picks, list):
            continue
        for p in picks:
            if not isinstance(p, dict):
                continue
            matchup = p.get("matchup") or p.get("event") or ""
            home = p.get("home_team") or p.get("home") or ""
            away = p.get("away_team") or p.get("away") or ""
            market = str(p.get("market_type") or p.get("market") or "").upper()
            pick = p.get("pick") or p.get("selection") or ""
            line = p.get("line", 0)
            if not (matchup and home and away and market and pick):
                continue
            records.append({
                "source": "bettingpros", "sport": sport, "matchup": matchup,
                "home": home, "away": away, "market": market, "pick": pick,
                "line": line, "implied_prob": p.get("consensus_pct") or p.get("win_pct"),
            })
    if not records and raw_samples:
        try:
            gist_write(os.environ.get("GITHUB_TOKEN", ""), "betcouncil_bettingpros_snapshot_debug.json", raw_samples)
        except Exception:
            pass
    return records


def snapshot_dk_most_bet(today: str, known_players: set) -> list:
    """
    fetch_dk_most_bet_props returns {Event, EventDate, Market, Pick, Odds}
    where the player name is embedded inside "Market" text (e.g. "Kerry
    Carpenter Home Runs") with no clean separator from the stat type.
    Rather than guess-parse that, match against `known_players` — the
    player names already collected from FavoredProps/DraftEdge in this
    same run — and split on the matched name to recover the stat type.
    Anything that doesn't match a known player this same day is skipped
    rather than guessed at.
    """
    sys.path.insert(0, ".")
    from fetchers import fetch_dk_most_bet_props

    records = []
    for sport in SPORTS:
        try:
            rows = fetch_dk_most_bet_props(sport, max_rows=60)
        except Exception as e:
            log(f"  dk_most_bet/{sport}: error — {e}")
            continue
        for row in rows:
            market = row.get("Market", "")
            market_l = market.lower()
            matched_player = next((p for p in known_players if p.lower() in market_l), None)
            if not matched_player:
                continue
            prop_type = market_l.replace(matched_player.lower(), "").strip(" -:")
            pick_text = str(row.get("Pick", "")).upper()
            side = "OVER" if pick_text.startswith("O") else ("UNDER" if pick_text.startswith("U") else None)
            if not (prop_type and side):
                continue
            try:
                line = float("".join(c for c in pick_text if c.isdigit() or c == "."))
            except ValueError:
                continue
            records.append({
                "source": "dk_most_bet", "sport": sport, "player": matched_player,
                "prop_type": prop_type, "line": line, "side": side, "implied_prob": None,
            })
    return records


def _ms_within(ms, hours=30):
    try:
        t = float(ms) / 1000.0
    except (TypeError, ValueError):
        return False
    import time as _t
    return _t.time() - 3 * 3600 < t < _t.time() + hours * 3600


def snapshot_sportsline(today: str) -> list:
    """SportsLine insider (named-expert) PENDING picks via their native mobile feed.
    Only spread/total picks are kept (priced near -110, so a flat 52.4% breakeven
    test is fair); moneyline picks are skipped because favourites inflate hit rate.
    Counts a complete snapshot only (livePicks must match delivered rows)."""
    import re
    url = "https://www.sportsline.com/sportsline-web/service/v1/mobile/insiderPicks"
    rows, expected = [], None
    for page in range(20):
        try:
            r = requests.get(url, params={"max": 100, "offset": page * 100},
                             headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}, timeout=30)
            d = r.json()
        except Exception as e:
            log(f"  sportsline: fetch error — {e}")
            return []
        expected = d.get("livePicks")
        got = d.get("insiderPicks") or []
        rows += [x for x in got if x.get("resultStatus") == "PENDING"]
        if len(rows) >= (expected or 0) or len(got) < 100:
            break
    if expected is not None and len(rows) != expected:
        log(f"  sportsline: incomplete snapshot ({len(rows)}/{expected}) — skipped, no partial data")
        return []
    records, skipped = [], 0
    for x in rows:
        sport = str(x.get("leagueAbbrv", "")).upper()
        if sport not in SPORTS or not _ms_within(x.get("startDt")):
            continue
        home, away = x.get("homeTeamName", ""), x.get("awayTeamName", "")
        if not (home and away):
            continue
        label = str(x.get("pickLabel", ""))
        author = f"{x.get('firstName','')} {x.get('lastName','')}".strip()
        base = {"source": "sportsline", "sport": sport, "matchup": f"{away} @ {home}",
                "home": home, "away": away, "expert": author, "implied_prob": None}
        m = re.match(r"^\s*(O|U|OVER|UNDER)\b", label, re.I)
        if x.get("ouTotal") and m:
            records.append({**base, "market": "TOTAL",
                            "pick": ("OVER " if m.group(1).upper().startswith("O") else "UNDER ") + str(x["ouTotal"]),
                            "line": x["ouTotal"]})
        elif (x.get("psHomeOdds") or x.get("psAwayOdds")) and x.get("pickSide") in (1, 2):
            hh = x.get("psHomeHandicap", 0) or 0
            records.append({**base, "market": "SPREAD", "pick": home if x["pickSide"] == 2 else away, "line": hh})
        else:
            skipped += 1
    log(f"  sportsline: {len(records)} spread/total picks kept, {skipped} moneyline/other skipped")
    return records


def snapshot_fantasylabs(today: str) -> list:
    """FantasyLabs PickLabs expert player-prop picks (native Next.js flight data)."""
    import re
    try:
        r = requests.get("https://terminal.fantasylabs.com/picklabs?site=prizepicks&view=experts",
                         headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"}, timeout=60)
        html = r.text
        flight = "".join(
            (c[1] if isinstance(c, list) and c and c[0] == 1 and isinstance(c[1], str) else "")
            for c in (_safe_json(m) for m in re.findall(r"self\.__next_f\.push\((.*?)\)</script>", html, re.S)))
        i = flight.index('"experts":')
        start = flight.index("[", i)
        depth, instr, esc = 0, False, False
        end = None
        for k in range(start, len(flight)):
            ch = flight[k]
            if instr:
                esc = (not esc) if ch == "\\" else False
                if ch == '"' and not esc:
                    instr = False
            elif ch == '"':
                instr = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        if end is None:
            log("  fantasylabs: truncated feed — skipped")
            return []
        rows = json.loads(flight[start:end + 1])
    except Exception as e:
        log(f"  fantasylabs: error — {e}")
        return []
    from datetime import datetime as _dt
    records = []
    for row in rows:
        try:
            mk, pl = row["market"], row["market"]["player"]
            side = str(row.get("side", "")).upper()
            sport = str(mk.get("sport", "")).upper()
            ev = mk.get("eventDate")
            if side not in ("OVER", "UNDER") or sport not in SPORTS:
                continue
            import time as _tm
            if isinstance(ev, str) and ev not in ("$undefined",):
                t = _dt.fromisoformat(ev.replace("Z", "+00:00")).timestamp()
                if not _ms_within(t * 1000):
                    continue
            else:
                # Source supplies no game time for most expert picks (its own docs say so);
                # fall back to publication time (timezone unspecified -> wide window).
                pub = _dt.fromisoformat(str(row.get("date")).replace(" ", "T")).timestamp()
                if not (_tm.time() - 30 * 3600 < pub < _tm.time() + 12 * 3600):
                    continue
            records.append({"source": "fantasylabs", "sport": sport, "player": pl["playerName"],
                            "prop_type": mk["stat"], "line": float(mk["value"]), "side": side,
                            "expert": (row.get("expert") or {}).get("name"), "implied_prob": None})
        except Exception:
            continue
    log(f"  fantasylabs: {len(records)} of {len(rows)} expert prop picks kept")
    return records


def _safe_json(x):
    try:
        return json.loads(x)
    except Exception:
        return None


PICKWATCH_EXPERTS = [
    "pete-prisco", "tyler-sullivan", "dave-richard", "jared-dubin", "john-breech", "brad-gagnon",
    "brent-sobleski", "gary-davenport", "bill-bender", "vinnie-iyer", "chris-simms", "frank-schwab",
    "gennaro-filice", "jarrett-bell", "sam-farmer",
]
_PW_HEADERS = {"Accept": "application/json", "Origin": "https://nflpickwatch.com",
               "Referer": "https://nflpickwatch.com/",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def snapshot_pickwatch(today: str) -> list:
    """Pickwatch NFL ATS picks from 15 named analysts (CBS, B/R, NBC, Yahoo...). Needs the
    Origin/Referer headers -- without them Cloudflare returns 403. The analysts are republished,
    so this is ONE source ("pickwatch"), never 15 independent votes. Row 'spread' is relative to
    the picked team (verified live), converted here to the home-relative line the grader expects."""
    A = "https://api.nflpickwatch.com/v1/general"
    try:
        meta = requests.get(f"{A}/metadata", headers=_PW_HEADERS, timeout=30).json()
        cur = meta["timeframes"]["nfl"]["current"]
        sn, wk, ph = cur["season_id"], cur["week_id"], cur["week_type_id"]
        games = requests.get(f"{A}/games/{sn}/{wk}/nfl/{ph}?region_id=1", headers=_PW_HEADERS, timeout=30).json()
        names = {t["id"]: t["full_name"] for t in meta["teams"]["nfl"]["selectTeams"] if t.get("full_name")}
    except Exception as e:
        log(f"  pickwatch: metadata/games error — {e}")
        return []
    import time as _tm
    from datetime import datetime as _dt
    open_games = {}
    for g in games:
        try:
            ko = _dt.fromisoformat(str(g["kickoff"]).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if not g.get("kicked_off") and _tm.time() < ko < _tm.time() + 30 * 3600:
            open_games[g["id"]] = g
    records = []
    for ex in PICKWATCH_EXPERTS:
        try:
            c = requests.get(f"{A}/profile/picks/nfl/{ex}/{sn}/{wk}", params={"types": '["ats"]', "teams": "[]"},
                             headers=_PW_HEADERS, timeout=30).json()
        except Exception:
            continue
        per_game = {}
        for row in c.get("picks", []):
            g = open_games.get(row.get("game_id"))
            if (row.get("pick_type") != "ats" or not g or row.get("auto_pick") is not False
                    or row.get("pick") not in (g["home_team_id"], g["road_team_id"])
                    or not isinstance(row.get("spread"), (int, float))):
                continue
            per_game.setdefault(g["id"], []).append(row)
        for gid, rws in per_game.items():
            if len({(r["pick"], r["spread"]) for r in rws}) != 1:
                continue  # conflicting duplicate picks -> skip, never guess
            row, g = rws[0], open_games[gid]
            home, away = names.get(g["home_team_id"]), names.get(g["road_team_id"])
            if not (home and away):
                continue
            pick_home = row["pick"] == g["home_team_id"]
            records.append({"source": "pickwatch", "sport": "NFL", "matchup": f"{away} @ {home}",
                            "home": home, "away": away, "market": "SPREAD",
                            "pick": home if pick_home else away,
                            "line": row["spread"] if pick_home else -row["spread"],
                            "expert": ex, "implied_prob": None})
    log(f"  pickwatch: {len(records)} analyst ATS picks on {len(open_games)} upcoming games")
    return records


# Only labels the grader's stat mapper resolves CORRECTLY (verified); combos / receptions / attempts
# etc. map to the wrong stat there, so they are deliberately left out rather than mis-graded.
_BP_SAFE = {
    "NBA": {156: "Points", 157: "Rebounds", 151: "Assists", 160: "Steals", 152: "Blocks", 162: "3-Pointers Made"},
    "NFL": {105: "Receiving Yards", 107: "Rushing Yards", 103: "Passing Yards"},
    "NHL": {318: "Goals", 319: "Points", 320: "Assists", 321: "Shots on Goal"},
}


def snapshot_bettingpros_props(today: str) -> list:
    """BettingPros recommended-side props (bet_signals probability) from the combined Gist."""
    combined = gist_read("betcouncil_bettingpros_combined.json") or {}
    records = []
    for sport, labels in _BP_SAFE.items():
        for p in (combined.get(sport) or {}).get("props", []):
            label = labels.get(p.get("market_id"))
            proj = p.get("projection") or {}
            side = str(proj.get("recommended_side") or "").lower()
            if not label or side not in ("over", "under"):
                continue
            leg = p.get(side) or {}
            name = (p.get("participant") or {}).get("name")
            if not name or leg.get("line") is None:
                continue
            records.append({"source": "bettingpros", "sport": sport, "player": name, "prop_type": label,
                            "line": leg["line"], "side": side.upper(),
                            "implied_prob": proj.get("probability")})
    log(f"  bettingpros props: {len(records)} recommended-side picks")
    return records


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    today = date.today().isoformat()
    debug_info = {"today": today, "run_id": os.environ.get("GITHUB_RUN_ID", "local"), "steps": [], "error": None}

    try:
        fp_de_records = snapshot_favoredprops(today) + snapshot_draftedge(today)
        debug_info["steps"].append(f"favoredprops+draftedge: {len(fp_de_records)}")
        known_players = {r["player"] for r in fp_de_records if r.get("player")}

        # DK Most Bet disabled: it is crowd popularity (no prediction claim) and its table is now
        # Event/Date/Market/Betslip-Line/Odds (anytime-TD style), which the old parser never matched.
        dk_records = []
        lt_records = snapshot_lineterminal(today)
        debug_info["steps"].append(f"lineterminal: {len(lt_records)}")
        fl_records = snapshot_fantasylabs(today)
        debug_info["steps"].append(f"fantasylabs: {len(fl_records)}")
        bpp_records = snapshot_bettingpros_props(today)
        debug_info["steps"].append(f"bettingpros_props: {len(bpp_records)}")
        props_records = fp_de_records + dk_records + lt_records + fl_records + bpp_records

        dimers_records = snapshot_dimers(today)
        debug_info["steps"].append(f"dimers: {len(dimers_records)}")
        covers_records = snapshot_covers(today)
        debug_info["steps"].append(f"covers: {len(covers_records)}")
        bp_records = []  # old game-pick BettingPros function was removed; props handled above
        wb_records = snapshot_wagerbird(today)
        debug_info["steps"].append(f"wagerbird: {len(wb_records)}")
        sl_records = snapshot_sportsline(today)
        debug_info["steps"].append(f"sportsline: {len(sl_records)}")
        pw_records = snapshot_pickwatch(today)
        debug_info["steps"].append(f"pickwatch: {len(pw_records)}")
        game_records = dimers_records + covers_records + bp_records + wb_records + sl_records + pw_records
    except Exception as e:
        import traceback
        debug_info["error"] = f"{e}\n{traceback.format_exc()}"
        log(f"FATAL during snapshot collection: {e}")
        try:
            gist_write(token, "betcouncil_third_party_snapshot_debug.json", debug_info)
        except Exception:
            pass
        return 1

    by_source_props = {}
    for r in props_records:
        by_source_props[r["source"]] = by_source_props.get(r["source"], 0) + 1
    by_source_games = {}
    for r in game_records:
        by_source_games[r["source"]] = by_source_games.get(r["source"], 0) + 1
    log(f"Props by source: {by_source_props}")
    log(f"Games by source: {by_source_games}")
    debug_info["by_source_props"] = by_source_props
    debug_info["by_source_games"] = by_source_games

    history = gist_read(SNAPSHOT_FILE) or {}
    history[today] = {"props": props_records, "games": game_records}
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    history = {k: v for k, v in history.items() if k >= cutoff}

    ok = gist_write(token, SNAPSHOT_FILE, history)
    log("Snapshot pushed" if ok else "Snapshot push FAILED")
    gist_write(token, "betcouncil_third_party_snapshot_debug.json", debug_info)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
