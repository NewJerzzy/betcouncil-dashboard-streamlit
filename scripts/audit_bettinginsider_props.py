"""Independently audit dated Betting Insider player props against ESPN box scores.

This is an on-demand review tool, not a dashboard ingestion path. It reads the
public dated website pick history (not the historical-only developer API),
grades each settled player prop from ESPN event and box-score data, and writes
an inspectable JSON/HTML report under generated-artifacts/.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated-artifacts"
CACHE = OUT / "espn-prop-audit-cache"
BASE = "https://www.thebettinginsider.com"
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
PATHS = {
    "NFL": "football/nfl",
    "CFB": "football/college-football",
    "NCAAF": "football/college-football",
    "MLB": "baseball/mlb",
    "NBA": "basketball/nba",
}
ABBR = {"WSH": "WAS", "JAX": "JAC", "ATH": "OAK", "AZ": "ARI"}
EXPERTS = {"Insider Mike", "Invisible Insider", "Michael Wong"}
WINDOW_START = date(2026, 9, 1)
WINDOW_END = date(2026, 10, 31)

STAT_TYPES = {
    "player_reception_yds": ("receiving", "YDS"),
    "player_receptions": ("receiving", "REC"),
    "player_rush_yds": ("rushing", "YDS"),
    "player_rush_attempts": ("rushing", "CAR"),
    "player_pass_yds": ("passing", "YDS"),
    "player_pass_tds": ("passing", "TD"),
    "player_pass_completions": ("passing", "C/ATT:completed"),
    "player_pass_attempts": ("passing", "C/ATT:attempted"),
    "player_pass_interceptions": ("passing", "INT"),
    "player_longest_reception": ("receiving", "LONG"),
    "player_rush_reception_yds": ("combined", "rush+receiving:YDS"),
    "player_anytime_td": ("combined", "anytime_td"),
    "player_points": ("basketball", "PTS"),
    "player_rebounds": ("basketball", "REB"),
    "player_assists": ("basketball", "AST"),
    "player_threes": ("basketball", "3PT"),
    "player_points_rebounds_assists": ("basketball", "PRA"),
    "pitcher_outs": ("pitching", "IP:outs"),
    "pitcher_strikeouts": ("pitching", "K"),
    "pitcher_earned_runs": ("pitching", "ER"),
    "pitcher_hits_allowed": ("pitching", "H"),
    "pitcher_walks": ("pitching", "BB"),
    "batter_hits": ("batting", "H"),
    "batter_walks": ("batting", "BB"),
    "batter_hits_runs_rbis": ("batting", "H+R+RBI"),
    "batter_total_bases": ("batting", "TB"),
    "batter_home_runs": ("batting", "HR"),
    "batter_stolen_bases": ("batting", "SB"),
    "batter_strikeouts": ("batting", "K"),
}


def _cache_json(url: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text())
    response = requests.get(url, timeout=(5, 30))
    response.raise_for_status()
    data = response.json()
    path.write_text(json.dumps(data, separators=(",", ":")))
    return data


def _dated_source() -> tuple[list[dict], list[dict]]:
    days = []
    day = WINDOW_START
    while day <= WINDOW_END:
        days.append(day.isoformat())
        day += timedelta(days=1)

    def fetch(day: str):
        url = f"{BASE}/api/picks/list?mode=today&date={day}"
        try:
            data = _cache_json(url)
            if data.get("success") is not True or not isinstance(data.get("picks"), list):
                raise ValueError("unexpected dated picks response")
            return {"day": day, "status": 200, "count": len(data["picks"])}, data["picks"]
        except Exception as exc:
            return {"day": day, "error": f"{type(exc).__name__}: {exc}"}, []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, days))
    requests_log = [status for status, _ in fetched]
    rows, seen = [], set()
    for _, picks in fetched:
        for pick in picks:
            if pick.get("bettor_name") not in EXPERTS:
                continue
            if str(pick.get("bet_type", "")).lower() != "prop":
                continue
            identity = str(pick.get("id") or "")
            if identity and identity not in seen:
                seen.add(identity)
                rows.append(pick)
    return rows, requests_log


def _current_pending_props() -> list[dict]:
    response = requests.get(f"{BASE}/api/picks/list?mode=all", timeout=(5, 30))
    response.raise_for_status()
    data = response.json()
    if data.get("success") is not True or not isinstance(data.get("picks"), list):
        raise ValueError("unexpected live picks response")
    fields = (
        "id", "bettor_name", "sport", "game_id", "game_title", "bet_type",
        "bet_title", "stat_type", "odds", "units", "sportsbook", "posted_at",
        "game_time", "result",
    )
    return [
        {key: pick.get(key) for key in fields}
        for pick in data["picks"]
        if pick.get("bettor_name") in EXPERTS
        and str(pick.get("bet_type", "")).lower() == "prop"
        and pick.get("result") == "pending"
    ]


def _source_day(pick: dict) -> str | None:
    match = re.match(r"^[A-Z]+-(\d{8})-", str(pick.get("game_id") or ""))
    if match:
        return match.group(1)
    value = pick.get("game_time")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%Y%m%d")
    except (TypeError, ValueError):
        return None


def _sport_path(pick: dict) -> str | None:
    return PATHS.get(str(pick.get("sport") or "").upper())


def _scoreboard_url(path: str, day: str) -> str:
    extra = "&groups=80&limit=200" if path.endswith("college-football") else "&limit=200"
    return f"{ESPN}/{path}/scoreboard?dates={day}{extra}"


def _resolve_event(pick: dict, events: list[dict]) -> tuple[dict | None, str]:
    identity = str(pick.get("game_id") or "")
    explicit = re.search(r"-(\d{9})$", identity)
    if explicit:
        matches = [event for event in events if str(event.get("id")) == explicit.group(1)]
    else:
        pieces = identity.split("-")
        matches = []
        if len(pieces) >= 4:
            away, home = ABBR.get(pieces[2].upper(), pieces[2].upper()), ABBR.get(pieces[3].upper(), pieces[3].upper())
            for event in events:
                competitors = event.get("competitions", [{}])[0].get("competitors", [])
                sides = {
                    competitor.get("homeAway"): ABBR.get(
                        str(competitor.get("team", {}).get("abbreviation", "")).upper(),
                        str(competitor.get("team", {}).get("abbreviation", "")).upper(),
                    )
                    for competitor in competitors
                }
                if sides.get("away") == away and sides.get("home") == home:
                    matches.append(event)
    if len(matches) != 1:
        return None, "ambiguous/missing ESPN event"
    event = matches[0]
    if not event.get("status", {}).get("type", {}).get("completed"):
        return event, "ESPN event not final"
    return event, ""


def _collect_espn(rows: list[dict]) -> tuple[dict, list[dict]]:
    pairs = sorted({
        (_sport_path(pick), _source_day(pick))
        for pick in rows if _sport_path(pick) and _source_day(pick)
    })

    def scoreboard(pair):
        path, day = pair
        try:
            return pair, _cache_json(_scoreboard_url(path, day)).get("events", []), None
        except Exception as exc:
            return pair, [], f"{type(exc).__name__}: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        boards = list(pool.map(scoreboard, pairs))
    events_by_pair = {pair: events for pair, events, _ in boards}
    errors = [
        {"sport_path": pair[0], "date": pair[1], "error": error}
        for pair, _, error in boards if error
    ]
    mapping = {}
    summary_keys = set()
    for pick in rows:
        path, day = _sport_path(pick), _source_day(pick)
        if not path or not day:
            mapping[str(pick.get("id"))] = (None, None, "unsupported sport/date")
            continue
        event, reason = _resolve_event(pick, events_by_pair.get((path, day), []))
        mapping[str(pick.get("id"))] = (path, event, reason)
        if event and not reason:
            summary_keys.add((path, str(event["id"])))

    def summary(key):
        path, event_id = key
        try:
            return key, _cache_json(f"{ESPN}/{path}/summary?event={event_id}"), None
        except Exception as exc:
            return key, {}, f"{type(exc).__name__}: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        summaries = list(pool.map(summary, sorted(summary_keys)))
    summary_by_key = {key: data for key, data, _ in summaries}
    errors.extend(
        {"sport_path": key[0], "event": key[1], "error": error}
        for key, _, error in summaries if error
    )
    return (mapping, summary_by_key), errors


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _name_aliases(values: list[str]) -> set[str]:
    aliases = set()
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    for value in values:
        normalized = _norm(value)
        if normalized:
            aliases.add(normalized)
        tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
        original_tokens = list(tokens)
        while tokens and tokens[-1] in suffixes:
            tokens.pop()
        if len(tokens) >= 2:
            aliases.add(tokens[0][0] + tokens[-1])
            aliases.add(tokens[-1])
            if len(original_tokens) > len(tokens):
                aliases.add(tokens[0][0] + "".join(original_tokens[1:]))
                aliases.add("".join(original_tokens[1:]))
    return aliases


def _one_edit_apart(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1 or left == right:
        return False
    i = j = edits = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(left) > len(right):
            i += 1
        elif len(right) > len(left):
            j += 1
        else:
            i += 1
            j += 1
    edits += (len(left) - i) + (len(right) - j)
    return edits == 1


def _player_candidates(pick: dict, summary: dict) -> list[dict]:
    title = _norm(pick.get("bet_title", ""))
    matches = {}
    for team in summary.get("boxscore", {}).get("players", []):
        for category in team.get("statistics", []):
            for row in category.get("athletes", []):
                athlete = row.get("athlete", {})
                key = athlete.get("id") or _norm(athlete.get("displayName", ""))
                aliases = _name_aliases([
                    athlete.get("shortName", ""),
                    athlete.get("displayName", ""),
                    athlete.get("fullName", ""),
                    " ".join((athlete.get("firstName", ""), athlete.get("lastName", ""))),
                ])
                info = {
                    "id": athlete.get("id"),
                    "name": athlete.get("displayName") or athlete.get("fullName"),
                    "short_name": athlete.get("shortName"),
                    "team": team.get("team", {}).get("displayName"),
                }
                exact = [alias for alias in aliases if alias and title.startswith(alias)]
                if exact:
                    matches[key] = (max(map(len, exact)), "ESPN name", info)

    if matches:
        best = max(score for score, _, _ in matches.values())
        return [
            {**info, "match_method": method}
            for score, method, info in matches.values() if score == best
        ]

    # Permit one-character spelling variants only when they identify one
    # player in the entire ESPN box score. Do not use surname-only fuzzy matches.
    fuzzy = {}
    for team in summary.get("boxscore", {}).get("players", []):
        for category in team.get("statistics", []):
            for row in category.get("athletes", []):
                athlete = row.get("athlete", {})
                key = athlete.get("id") or _norm(athlete.get("displayName", ""))
                names = [
                    athlete.get("shortName", ""),
                    athlete.get("displayName", ""),
                    athlete.get("fullName", ""),
                    " ".join((athlete.get("firstName", ""), athlete.get("lastName", ""))),
                ]
                fuzzy_aliases = set()
                for name in names:
                    tokens = re.findall(r"[a-z0-9]+", str(name or "").lower())
                    while tokens and tokens[-1] in {"jr", "sr", "ii", "iii", "iv", "v"}:
                        tokens.pop()
                    if len(tokens) >= 2:
                        fuzzy_aliases.add(tokens[0][0] + tokens[-1])
                for alias in fuzzy_aliases:
                    for length in range(max(2, len(alias) - 1), len(alias) + 2):
                        prefix = title[:length]
                        if _one_edit_apart(alias, prefix):
                            fuzzy[key] = {
                                "id": athlete.get("id"),
                                "name": athlete.get("displayName") or athlete.get("fullName"),
                                "short_name": athlete.get("shortName"),
                                "team": team.get("team", {}).get("displayName"),
                                "match_method": "unique one-character ESPN name match",
                            }
                            break
                    if key in fuzzy:
                        break
    return list(fuzzy.values()) if len(fuzzy) == 1 else []


def _categories_for_player(summary: dict, athlete_id: str) -> list[tuple[str, str, dict]]:
    output = []
    for team in summary.get("boxscore", {}).get("players", []):
        for category in team.get("statistics", []):
            for row in category.get("athletes", []):
                if str(row.get("athlete", {}).get("id")) == str(athlete_id):
                    output.append((
                        str(category.get("name") or ""),
                        team.get("team", {}).get("displayName", ""),
                        {"labels": category.get("labels") or [], "stats": row.get("stats") or []},
                    ))
    return output


def _stat_type(pick: dict) -> tuple[str, str] | None:
    market = STAT_TYPES.get(str(pick.get("stat_type") or "").lower())
    if market:
        return market
    title = str(pick.get("bet_title") or "").lower()
    sport = str(pick.get("sport") or "").upper()
    # Conservative title-based fallback for older rows without a usable stat_type.
    if sport == "MLB":
        if "hits allowed" in title:
            return "pitching", "H"
        if "walks allowed" in title:
            return "pitching", "BB"
        if "earned runs" in title or re.search(r"\b(?:er|era)\b", title):
            return "pitching", "ER"
        if "pitcher outs" in title or "pitching outs" in title or re.search(r"\bouts\b", title):
            return "pitching", "IP:outs"
        if "pitcher" in title and re.search(r"\b(?:ks?|strikeouts)\b", title):
            return "pitching", "K"
        if "pitcher" in title and "walk" in title:
            return "pitching", "BB"
        if "total bases" in title:
            return "batting", "TB"
        if "hits + runs + rbis" in title or "hits+runs+rbis" in title or "h/r/rbi" in title or "hrrbi" in title:
            return "batting", "H+R+RBI"
        if "home run" in title or re.search(r"\bhr\b", title):
            return "batting", "HR"
        if "walk" in title:
            return "batting", "BB"
        if re.search(r"\b(?:ks?|strikeouts)\b", title):
            return "pitching", "K"
        if "hits" in title:
            return "batting", "H"
        if re.search(r"\bsbs?\b", title):
            return "batting", "SB"
    if "anytime td" in title or re.search(r"\btd\b", title):
        return "combined", "anytime_td"
    if "rush + rec" in title or "rush+rec" in title or "rushing + receiving" in title:
        return "combined", "rush+receiving:YDS"
    if "tackles+assists" in title or "tackles + assists" in title:
        return "defensive", "TOT"
    if "longest reception" in title:
        return "receiving", "LONG"
    if "receptions" in title or re.search(r"\brec(?:s)?\b", title):
        return "receiving", "REC"
    if "receiving" in title or re.search(r"\brec(?:eiving)?\s*(?:yds?|yards?)\b", title):
        return "receiving", "YDS"
    if "rush" in title and ("yards" in title or "yds" in title):
        return "rushing", "YDS"
    if "carries" in title or "rush attempts" in title:
        return "rushing", "CAR"
    if "rushing attempts" in title:
        return "rushing", "CAR"
    if "pass" in title and ("yards" in title or "yds" in title):
        return "passing", "YDS"
    if "pass td" in title:
        return "passing", "TD"
    if "interceptions" in title:
        return "passing", "INT"
    if "passing attempts" in title:
        return "passing", "C/ATT:attempted"
    if "completions" in title:
        return "passing", "C/ATT:completed"
    if "pra" in title:
        return "basketball", "PRA"
    if "points" in title:
        return "basketball", "PTS"
    if "rebounds" in title or re.search(r"\breb\b", title):
        return "basketball", "REB"
    if "assists" in title:
        return "basketball", "AST"
    if "3pm" in title or "three pointers" in title:
        return "basketball", "3PT"
    return None


def _line(pick: dict) -> tuple[str | None, float | None, str]:
    title = str(pick.get("bet_title") or "")
    selection_markers = re.findall(
        r"\b(?:over|under|o|u)\s*\d+(?:\.\d+)?\b"
        r"|\b\d+(?:\.\d+)?\s*(?:\+|plus)\s*(?:ks?|assists?|points?|yards?|"
        r"receptions?|sbs?|hrs?|hits?|bases?|er)\b"
        r"|\b(?:ml|moneyline|spread)\b"
        r"|\banytime\s+td\b",
        title, re.I,
    )
    if (
        re.search(r"\b(?:sgp|parlay|\d+\s*[- ]leg)\b", title, re.I)
        or len(selection_markers) > 1
    ):
        return None, None, "multi-leg or parlay selection; not a standalone player prop"
    if re.search(r"\b1st\s+td\b", title, re.I):
        return "first_td", None, ""
    if re.search(r"\blast\s+td\b", title, re.I):
        return "last_td", None, ""
    if re.search(r"\b(?:anytime\s+td|td)\s*$", title, re.I):
        return "yes", None, ""
    match = re.search(r"\b(over|under|o|u)\s*(\d+(?:\.\d+)?)\b", title, re.I)
    if match:
        return ("over" if match.group(1).lower() in ("over", "o") else "under", float(match.group(2)), "")
    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:\+|plus)\s*"
        r"(?:(?:passing|rushing|receiving)\s*)?"
        r"(?:ks?|assists?|points?|yards?|receptions?|sbs?|hrs?|hits?|bases?|er)\b",
        title, re.I,
    )
    if match:
        return "at_least", float(match.group(1)), ""
    return None, None, "unsupported or ambiguous selection/line"


def _as_number(value: str) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _extract_stat(pick: dict, summary: dict, player_id: str, market: tuple[str, str]) -> tuple[float | None, str]:
    family, stat = market
    categories = _categories_for_player(summary, player_id)
    if family == "combined" and stat == "rush+receiving:YDS":
        values = []
        for wanted in ("rushing", "receiving"):
            value = _category_value(categories, wanted, "YDS")
            if value is None:
                return None, "missing rushing/receiving box-score stat"
            values.append(value)
        return sum(values), "ESPN rushing YDS + receiving YDS"
    if family == "combined" and stat == "anytime_td":
        total = 0.0
        found = False
        for wanted, label in (("rushing", "TD"), ("receiving", "TD")):
            value = _category_value(categories, wanted, label)
            if value is not None:
                found, total = True, total + value
        # For non-skill positions, ESPN scoring plays identify named touchdown scorers.
        if found:
            return (1.0 if total > 0 else 0.0), "ESPN rushing/receiving TD"
        scorers = []
        for play in summary.get("scoringPlays", []):
            participants = play.get("athletesInvolved") or []
            if any(str(a.get("id")) == str(player_id) for a in participants):
                scorers.append(play)
        if scorers:
            return 1.0, "ESPN scoring-play participant"
        if categories:
            return 0.0, "ESPN player box score; no touchdown"
        return None, "no ESPN player box score"
    if family == "basketball" and stat == "PRA":
        values = [_category_value(categories, "statistics", label) for label in ("PTS", "REB", "AST")]
        if any(value is None for value in values):
            return None, "missing NBA PTS/REB/AST"
        return sum(values), "ESPN PTS + REB + AST"
    if family == "pitching" and stat == "IP:outs":
        value = _category_value(categories, "pitching", "IP")
        if value is None:
            return None, "missing pitching innings"
        whole, _, frac = f"{value:.1f}".partition(".")
        innings = int(whole)
        return float(innings * 3 + int(frac or 0)), "ESPN IP converted to outs"
    if family == "batting" and stat == "H+R+RBI":
        values = [_category_value(categories, "batting", label) for label in ("H", "R", "RBI")]
        if any(value is None for value in values):
            return None, "missing MLB H/R/RBI"
        return sum(values), "ESPN H + R + RBI"
    if family == "basketball" and stat == "3PT":
        raw = _category_raw(categories, "basketball", "3PT")
        if raw is None:
            return None, "ESPN box-score label basketball/3PT unavailable"
        made = _as_number(str(raw).split("-", 1)[0])
        if made is None:
            return None, "ESPN 3PT made/attempt value unavailable"
        return made, "ESPN 3PT made count"
    if (
        family == "batting" and stat == "BB"
        and str(pick.get("sport") or "").upper() == "MLB"
        and not re.search(r"\b(?:batter|batting)\b", str(pick.get("bet_title") or ""), re.I)
        and _category_raw(categories, "batting", "BB") is None
        and _category_raw(categories, "pitching", "BB") is not None
    ):
        return _category_value(categories, "pitching", "BB"), "ESPN pitching BB for matched pitcher"
    if family in ("passing", "rushing", "receiving", "defensive", "basketball", "batting", "pitching"):
        category = family
        label = stat
        if stat.startswith("C/ATT:"):
            part = stat.split(":", 1)[1]
            index = 0 if part == "completed" else 1
            raw = _category_raw(categories, category, "C/ATT")
            if raw is None or "/" not in raw:
                return None, "missing ESPN completion/attempt stat"
            value = _as_number(raw.split("/")[index])
            return value, f"ESPN passing {part}"
        value = _category_value(categories, category, label)
        if value is None:
            return None, f"ESPN box-score label {category}/{label} unavailable"
        return value, f"ESPN {category} {label}"
    return None, "unsupported ESPN stat mapping"


def _td_scorers(summary: dict) -> list[str]:
    scorers = []
    for play in summary.get("scoringPlays", []):
        kind = str(play.get("type", {}).get("text") or "")
        text = str(play.get("text") or "")
        if "touchdown" not in kind.lower():
            continue
        match = re.match(r"^(.+?)\s+\d+\s+yd\b", text, re.I)
        if match:
            scorers.append(match.group(1).strip())
    return scorers


def _is_selected_td_position(summary: dict, player: dict, selection: str) -> bool | None:
    scorers = _td_scorers(summary)
    if not scorers:
        return None
    target = _norm(player.get("name"))
    target_aliases = _name_aliases([player.get("name", "")])
    chosen = scorers[0] if selection == "first_td" else scorers[-1]
    chosen_norm = _norm(chosen)
    return chosen_norm == target or chosen_norm in target_aliases


def _unique_offensive_player(candidates: list[dict], summary: dict) -> dict | None:
    offensive = []
    defensive_only = []
    for candidate in candidates:
        categories = _categories_for_player(summary, str(candidate.get("id")))
        names = {name.lower() for name, _, _ in categories if name}
        if names and names <= {"defensive"}:
            defensive_only.append(candidate)
        else:
            offensive.append(candidate)
    if len(offensive) == 1 and defensive_only:
        return {**offensive[0], "match_method": "unique ESPN offensive-stat category match"}
    return None


def _category_raw(categories: list, category: str, label: str) -> str | None:
    for name, _, data in categories:
        labels = data["labels"]
        nameless = not name
        if category == "basketball":
            matches = nameless and all(key in labels for key in ("PTS", "REB", "AST"))
        elif category == "batting":
            matches = name.lower() == "batting" or (nameless and "H-AB" in labels)
        elif category == "pitching":
            matches = name.lower() == "pitching" or (nameless and "IP" in labels)
        elif category == "defensive":
            matches = name.lower() == "defensive"
        else:
            matches = name.lower() == category.lower() or (category == "statistics" and nameless)
        if not matches:
            continue
        if label in labels:
            index = labels.index(label)
            return data["stats"][index] if index < len(data["stats"]) else None
    return None


def _category_value(categories: list, category: str, label: str) -> float | None:
    raw = _category_raw(categories, category, label)
    if raw is None:
        return None
    if label == "IP":
        return _as_number(raw)
    return _as_number(raw)


def _grade(pick: dict, mapping: dict, summaries: dict) -> dict:
    path, event, event_reason = mapping.get(str(pick.get("id")), (None, None, "missing ESPN mapping"))
    kickoff = event.get("date") if event else None
    key = (path, str(event.get("id"))) if path and event else None
    summary = summaries.get(key, {}) if key else {}
    selection, line, selection_error = _line(pick)
    market = _stat_type(pick)
    player = None
    player_reason = "missing ESPN event"
    actual = None
    evidence = ""
    reason = event_reason or ""
    if event and not event_reason and summary:
        candidates = _player_candidates(pick, summary)
        if (
            len(candidates) > 1
            and str(pick.get("sport") or "").upper() in ("NFL", "CFB", "NCAAF")
            and market and market[0] in ("passing", "rushing", "receiving")
        ):
            role_match = _unique_offensive_player(candidates, summary)
            if role_match:
                candidates = [role_match]
        if len(candidates) == 1:
            player = candidates[0]
            player_id = player.get("id")
            if not player_id:
                player_reason = "ESPN player id missing"
            elif not market:
                player_reason = "unsupported or ambiguous player stat"
            elif selection in ("first_td", "last_td"):
                td_position = _is_selected_td_position(summary, player, selection)
                if td_position is None:
                    player_reason = "ESPN touchdown scoring-play order unavailable"
                else:
                    actual = 1.0 if td_position else 0.0
                    player_reason = f"ESPN {selection.replace('_', ' ')} scoring play"
                    evidence = player_reason
            else:
                categories = _categories_for_player(summary, player_id)
                if (
                    str(pick.get("sport") or "").upper() == "MLB"
                    and market == ("batting", "BB")
                    and not re.search(r"\b(?:batter|batting)\b", str(pick.get("bet_title") or ""), re.I)
                    and _category_raw(categories, "batting", "BB") is None
                    and _category_raw(categories, "pitching", "BB") is not None
                ):
                    market = ("pitching", "BB")
                actual, player_reason = _extract_stat(pick, summary, player_id, market)
                evidence = player.get("name") or ""
        elif len(candidates) > 1:
            player_reason = "ambiguous ESPN player match"
        else:
            player_reason = "ESPN box score has no exact player match"
    elif event and not reason:
        reason = "missing ESPN event summary"

    verdict = "unresolved"
    if selection_error:
        reason = selection_error
    elif not market:
        reason = "unsupported or ambiguous player stat"
    elif not actual is None and selection:
        if selection == "over":
            verdict = "win" if actual > line else "loss" if actual < line else "push"
        elif selection == "under":
            verdict = "win" if actual < line else "loss" if actual > line else "push"
        elif selection == "at_least":
            verdict = "win" if actual >= line else "loss"
        elif selection == "yes":
            verdict = "win" if actual > 0 else "loss"
        elif selection == "no":
            verdict = "win" if actual == 0 else "loss"
        elif selection in ("first_td", "last_td"):
            verdict = "win" if actual > 0 else "loss"
        else:
            verdict = "unresolved"
    else:
        verdict = "unresolved"
        if not reason:
            reason = player_reason
        elif player_reason and player_reason not in reason:
            reason += "; " + player_reason

    posted, game_start, late = None, None, None
    try:
        posted = datetime.fromisoformat(str(pick.get("posted_at") or pick.get("created_at")).replace("Z", "+00:00"))
        game_start = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00")) if kickoff else None
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if game_start and game_start.tzinfo is None:
            game_start = game_start.replace(tzinfo=timezone.utc)
        late = posted >= game_start if game_start else None
    except (TypeError, ValueError):
        posted, late = None, None
        reason = (reason + "; " if reason else "") + "invalid publication or kickoff timestamp"

    odds_raw = str(pick.get("odds") or "").strip().replace("−", "-")
    try:
        odds = float(odds_raw.replace("+", ""))
        if not math.isfinite(odds) or abs(odds) < 100:
            raise ValueError
    except (TypeError, ValueError):
        odds = None
    if verdict in ("win", "loss", "push") and odds is None:
        verdict = "unresolved"
        reason = (reason + "; " if reason else "") + "missing or invalid original price"
    try:
        stake = float(pick.get("units"))
        if stake <= 0:
            raise ValueError
    except (ValueError, TypeError):
        stake = None
    profit = None
    if verdict in ("win", "loss", "push") and odds is not None and stake is not None:
        profit = 0.0 if verdict == "push" else (
            stake * (odds / 100 if odds > 0 else 100 / abs(odds)) if verdict == "win" else -stake
        )
    publication_delta = (
        round((game_start - posted).total_seconds() / 60, 1)
        if game_start and posted else None
    )

    return {
        "id": pick.get("id"), "expert": pick.get("bettor_name"),
        "sport": pick.get("sport"), "event": pick.get("game_title"),
        "game_id": pick.get("game_id"), "espn_event_id": event.get("id") if event else None,
        "espn_url": f"https://www.espn.com/{path.split('/')[0]}/game/_/gameId/{event['id']}" if event and path else None,
        "player": (player or {}).get("name"), "selection": pick.get("bet_title"),
        "player_match_evidence": (player or {}).get("match_method"),
        "line": line, "direction": selection, "stat_type": pick.get("stat_type"),
        "verified_stat": actual, "stat_evidence": player_reason,
        "source_result": pick.get("result"), "independent_result": verdict,
        "original_odds": odds_raw or None, "original_stake_units": stake,
        "original_price_valid": odds is not None,
        "computed_profit_units": profit, "published_at": pick.get("posted_at") or pick.get("created_at"),
        "event_start_source": pick.get("game_time"), "event_start_espn": kickoff,
        "published_at_or_after_espn_start": late,
        "publication_delta_minutes": publication_delta,
        "unresolved_reason": reason or ("" if verdict != "unresolved" else player_reason),
        "market_mapping": f"{market[0]}/{market[1]}" if market else None,
    }


def _measure(rows: list[dict]) -> dict:
    final = [r for r in rows if r["independent_result"] in ("win", "loss", "push")]
    wins, losses, pushes = (sum(r["independent_result"] == result for r in final) for result in ("win", "loss", "push"))
    stake = sum(r["original_stake_units"] or 0 for r in final)
    profit = sum(r["computed_profit_units"] or 0 for r in final)
    flat_profit = 0.0
    for row in final:
        try:
            price = float(str(row["original_odds"]).replace("+", ""))
            flat_profit += 0 if row["independent_result"] == "push" else (
                price / 100 if row["independent_result"] == "win" and price > 0 else
                100 / abs(price) if row["independent_result"] == "win" else -1
            )
        except (ValueError, TypeError):
            pass
    return {
        "records": len(rows), "graded": len(final),
        "wins": wins, "losses": losses, "pushes": pushes,
        "win_rate_ex_pushes_pct": round(100 * wins / (wins + losses), 2) if wins + losses else None,
        "risk_units": round(stake, 3), "net_profit_units": round(profit, 3),
        "recorded_stake_roi_pct": round(100 * profit / stake, 2) if stake else None,
        "one_unit_flat_profit": round(flat_profit, 3),
        "one_unit_flat_roi_pct": round(100 * flat_profit / len(final), 2) if final else None,
        "unresolved": len(rows) - len(final),
    }


def _summarize(rows: list[dict]) -> dict:
    pregame = [r for r in rows if r["published_at_or_after_espn_start"] is False]
    final = [r for r in rows if r["independent_result"] in ("win", "loss", "push")]
    return {
        **_measure(rows),
        "pregame": _measure(pregame),
        "late_publications": sum(r["published_at_or_after_espn_start"] is True for r in rows),
        "late_publications_unknown": sum(r["published_at_or_after_espn_start"] is None for r in rows),
        "source_result_disagreements": sum(
            r["source_result"] in ("win", "loss", "push") and r["independent_result"] in ("win", "loss", "push")
            and r["source_result"] != r["independent_result"] for r in rows
        ),
        "missing_or_invalid_original_price": sum(not r["original_price_valid"] for r in rows),
        "missing_or_invalid_original_stake": sum(r["original_stake_units"] is None for r in rows),
        "graded_rows": len(final),
    }


def _pregame_performance(rows: list[dict]) -> dict:
    pregame = [r for r in rows if r["published_at_or_after_espn_start"] is False]
    resolved = [r for r in pregame if r["independent_result"] in ("win", "loss", "push")]

    def groups(key_fn):
        grouped = defaultdict(list)
        for row in resolved:
            key = key_fn(row)
            if key:
                grouped[key].append(row)
        return {key: _measure(group) for key, group in sorted(grouped.items())}

    by_expert = groups(lambda row: row["expert"])
    by_expert_sport = groups(
        lambda row: f'{row["expert"]} / {str(row["sport"]).upper()}'
    )
    by_market = groups(
        lambda row: " / ".join((
            row["expert"], str(row["sport"]).upper(),
            row["market_mapping"] or "unmapped market",
        ))
    )
    coverage_by_expert = {}
    for expert in sorted({row["expert"] for row in rows}):
        cohort = [row for row in pregame if row["expert"] == expert]
        coverage_by_expert[expert] = {
            "records": len(cohort),
            "resolved": sum(row["independent_result"] in ("win", "loss", "push") for row in cohort),
            "unresolved": sum(row["independent_result"] == "unresolved" for row in cohort),
        }

    missing_stats = defaultdict(list)
    for row in pregame:
        if row["independent_result"] != "unresolved":
            continue
        reason = row.get("unresolved_reason") or ""
        if reason.startswith("ESPN box-score label ") or reason.startswith("missing rushing/receiving box-score stat"):
            missing_stats[(str(row["sport"]).upper(), row.get("market_mapping") or "unmapped market", reason)].append(row)
    stat_availability = []
    for (sport, market, reason), affected in sorted(missing_stats.items()):
        if market == "batting/TB":
            finding = (
                "ESPN's event batting table has no total-bases field for these records. "
                "They remain unresolved; rounded batting totals were not used to infer TB."
            )
        elif market == "batting/K":
            finding = (
                "The matched ESPN player line is not exposed under the requested batting category. "
                "A pitching strikeout total is not substituted for a batter-strikeout market."
            )
        else:
            finding = (
                "The requested ESPN box-score category or label is absent for these event/player rows. "
                "A missing field is not treated as a zero."
            )
        stat_availability.append({
            "sport": sport,
            "market": market,
            "unresolved_rows": len(affected),
            "espn_field_finding": finding,
            "unresolved_reason": reason,
        })

    return {
        "basis": "only independently resolved picks published before ESPN event start",
        "eligible_pick_count": len(resolved),
        "pregame_record_count": len(pregame),
        "unresolved_pregame_count": len(pregame) - len(resolved),
        "by_expert": by_expert,
        "by_expert_sport": by_expert_sport,
        "by_market": by_market,
        "coverage_by_expert": coverage_by_expert,
        "espn_stat_availability": stat_availability,
        "unresolved_reason_counts": dict(sorted(Counter(
            row.get("unresolved_reason") or "unspecified"
            for row in pregame if row["independent_result"] == "unresolved"
        ).items())),
    }


def _report(result: dict) -> None:
    (OUT / "bettinginsider-prop-audit.json").write_text(json.dumps(result, indent=2))
    performance = result["pregame_performance"]
    mike_nfl = performance["by_expert_sport"].get("Insider Mike / NFL", {})
    invisible_nfl = performance["by_expert_sport"].get("Invisible Insider / NFL", {})
    wong = performance["by_expert"].get("Michael Wong", {})
    mike_outs = _measure([
        row for row in result["rows"]
        if row["expert"] == "Insider Mike" and str(row["sport"]).upper() == "MLB"
        and row["market_mapping"] == "pitching/IP:outs"
        and row["published_at_or_after_espn_start"] is False
        and row["independent_result"] in ("win", "loss", "push")
    ])
    current_mike = sum(pick["bettor_name"] == "Insider Mike" for pick in result["current_pending_props"])
    current_invisible = sum(pick["bettor_name"] == "Invisible Insider" for pick in result["current_pending_props"])
    mike_mlb_late = sum(
        row["expert"] == "Insider Mike" and str(row["sport"]).upper() == "MLB"
        and row["published_at_or_after_espn_start"] is True
        for row in result["rows"]
    )
    current_mike_nfl = sum(
        pick["bettor_name"] == "Insider Mike" and str(pick.get("sport", "")).upper() == "NFL"
        for pick in result["current_pending_props"]
    )
    decision = (
        f"<p><strong>Admission decision: skip additional prop experts for Predictions.</strong> "
        f"The current slate has {current_mike} pending Mike props ({current_mike_nfl} NFL) and "
        f"{current_invisible} pending Invisible Insider props. Mike's pregame NFL record is "
        f"{mike_nfl.get('wins', 0)}-{mike_nfl.get('losses', 0)} "
        f"across {mike_nfl.get('graded', 0)} independently resolved picks, with "
        f"{mike_nfl.get('recorded_stake_roi_pct')}% ROI on source-reported stakes. "
        f"His full MLB cohort has {mike_mlb_late} rows published at/after ESPN kickoff; among "
        f"timestamped pregame rows, "
        f"{performance['coverage_by_expert'].get('Insider Mike', {}).get('unresolved', 0)} remain unresolved. "
        f"The strongest isolated slice "
        f"(pitcher outs) is only {mike_outs['wins']}-{mike_outs['losses']} over {mike_outs['graded']} "
        f"graded picks, not a current-slate scope. Invisible Insider's pregame NFL record is "
        f"{invisible_nfl.get('wins', 0)}-{invisible_nfl.get('losses', 0)} with "
        f"{invisible_nfl.get('recorded_stake_roi_pct')}% ROI. "
        f"Michael Wong's resolved pregame record is {wong.get('wins', 0)}-{wong.get('losses', 0)} with "
        f"{performance['coverage_by_expert'].get('Michael Wong', {}).get('unresolved', 0)} unresolved. "
        f"No prop expert was added, and no observation-only "
        f"trial was created.</p>"
    )
    summary_rows = []
    for expert, summary in performance["by_expert"].items():
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            expert, summary["graded"], summary["wins"], summary["losses"],
            summary["pushes"], summary["win_rate_ex_pushes_pct"],
            summary["risk_units"], summary["net_profit_units"],
            summary["recorded_stake_roi_pct"], summary["one_unit_flat_profit"],
            summary["one_unit_flat_roi_pct"],
        ))
        summary_rows.append(f"<tr>{cells}</tr>")
    detail_rows = []
    for row in result["rows"]:
        cells = [
            row.get("expert"), row.get("sport"), row.get("event"), row.get("player"),
            row.get("player_match_evidence"),
            row.get("selection"), row.get("original_odds"), row.get("original_stake_units"),
            row.get("published_at"), row.get("event_start_espn"),
            row.get("published_at_or_after_espn_start"), row.get("verified_stat"),
            row.get("source_result"), row.get("independent_result"), row.get("unresolved_reason"),
            f'<a href="{html.escape(row["espn_url"], quote=True)}">ESPN</a>' if row.get("espn_url") else "",
        ]
        detail_rows.append("<tr>" + "".join(f"<td>{v if i == 15 else html.escape(str(v if v is not None else ''))}</td>" for i, v in enumerate(cells)) + "</tr>")
    headers = ("Expert", "Sport", "Event", "Matched player", "Player match evidence", "Original selection and line", "Price", "Stake", "Published UTC", "ESPN start UTC", "Late?", "ESPN stat", "Site result", "ESPN grade", "Unresolved reason", "Box score")
    header = "".join(f"<th>{html.escape(x)}</th>" for x in headers)
    current_rows = []
    for row in result["current_pending_props"]:
        current_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(row.get(key) or ''))}</td>"
            for key in ("bettor_name", "sport", "game_title", "bet_title", "odds",
                        "units", "posted_at", "game_time")
        ) + "</tr>")
    sport_rows = []
    for key, summary in performance["by_expert_sport"].items():
        sport_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>"
            for value in (
                key, summary["graded"], f'{summary["wins"]}-{summary["losses"]}-{summary["pushes"]}',
                summary["win_rate_ex_pushes_pct"], summary["net_profit_units"],
                summary["recorded_stake_roi_pct"],
            )
        ) + "</tr>")
    market_rows = []
    for key, summary in performance["by_market"].items():
        market_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>"
            for value in (
                key, summary["graded"], f'{summary["wins"]}-{summary["losses"]}-{summary["pushes"]}',
                summary["win_rate_ex_pushes_pct"], summary["net_profit_units"],
                summary["recorded_stake_roi_pct"],
            )
        ) + "</tr>")
    coverage_rows = []
    for expert, coverage in performance["coverage_by_expert"].items():
        coverage_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>"
            for value in (expert, coverage["records"], coverage["resolved"], coverage["unresolved"])
        ) + "</tr>")
    stat_rows = []
    for item in performance["espn_stat_availability"]:
        stat_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>"
            for value in (
                item["sport"], item["market"], item["unresolved_rows"],
                item["unresolved_reason"], item["espn_field_finding"],
            )
        ) + "</tr>")
    html_doc = f"""<!doctype html><meta charset="utf-8"><title>Betting Insider Prop Audit</title>
<style>body{{font:14px system-ui,sans-serif;margin:24px;color:#18212c}}h1{{margin-bottom:4px}}.note{{max-width:1100px;line-height:1.5;color:#465261}}table{{border-collapse:collapse;margin:18px 0;width:100%}}th,td{{border:1px solid #ccd3da;padding:6px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#eef2f6}}td{{font-size:12px}}.details{{overflow:auto;max-height:75vh}}.summary{{max-width:1200px}}.summary td{{font-size:14px}}</style>
<h1>The Betting Insider player-prop audit</h1>
<p class="note">Dated website history from {result["window"][0]} through {result["window"][1]}; source /api/picks/list?mode=today&date=YYYY-MM-DD; independent ESPN event and box-score grades. The website's historical /v1 developer API was not used as a live or graded-pick source. Original title, price, stake and publication timestamp are retained. Picks published at or after ESPN's listed kickoff are flagged; unresolved rows are not counted as wins.</p>
<p class="note">Records audited: {result["record_count"]}; date requests successful: {result["successful_dates"]}/{result["requested_dates"]}; ESPN retrieval errors: {len(result["espn_errors"])}. ESPN event and box-score data are outcome evidence only, not betting-market evidence.</p>
{decision}
<h2>Pregame performance from independently resolved picks only</h2>
<p class="note">All results below exclude picks published at or after ESPN kickoff, picks with unknown kickoff timing, and any pick that could not be independently graded from ESPN evidence. Unresolved picks remain listed below and are not included in expert or market totals.</p>
<table class="summary"><thead><tr>{''.join(f'<th>{x}</th>' for x in ("Expert", "Resolved pregame picks", "W", "L", "P", "Win rate %", "Risk units", "Net units", "Stake ROI %", "Flat 1u profit", "Flat 1u ROI %"))}</tr></thead><tbody>{''.join(summary_rows)}</tbody></table>
<h3>Expert and sport</h3>
<table><thead><tr>{''.join(f'<th>{x}</th>' for x in ("Expert / sport", "Resolved picks", "W-L-P", "Win rate %", "Net units", "Stake ROI %"))}</tr></thead><tbody>{''.join(sport_rows)}</tbody></table>
<h3>Expert, sport, and market</h3>
<table><thead><tr>{''.join(f'<th>{x}</th>' for x in ("Expert / sport / market", "Resolved picks", "W-L-P", "Win rate %", "Net units", "Stake ROI %"))}</tr></thead><tbody>{''.join(market_rows)}</tbody></table>
<h2>Pregame audit coverage</h2>
<table><thead><tr>{''.join(f'<th>{x}</th>' for x in ("Expert", "Pregame records", "Independently resolved", "Unresolved"))}</tr></thead><tbody>{''.join(coverage_rows)}</tbody></table>
<h2>ESPN box-score fields missing from unresolved records</h2>
<table><thead><tr>{''.join(f'<th>{x}</th>' for x in ("Sport", "Market", "Unresolved rows", "ESPN reason", "Finding"))}</tr></thead><tbody>{''.join(stat_rows)}</tbody></table>
<h2>Current live pending props</h2>
<p class="note">Snapshot from /api/picks/list?mode=all. Pending picks are listed for review and are not included in historical performance.</p>
<div class="details"><table><thead><tr>{''.join(f'<th>{x}</th>' for x in ("Expert", "Sport", "Event", "Published selection", "Original price", "Original stake", "Published UTC", "Source start UTC"))}</tr></thead><tbody>{''.join(current_rows)}</tbody></table></div>
<h2>All records, including losses and unresolved picks</h2>
<div class="details"><table><thead><tr>{header}</tr></thead><tbody>{''.join(detail_rows)}</tbody></table></div>
"""
    (OUT / "bettinginsider-prop-audit.html").write_text(html_doc)


def main() -> None:
    rows, request_log = _dated_source()
    current = _current_pending_props()
    (mapping, summaries), errors = _collect_espn(rows)
    audited = [_grade(pick, mapping, summaries) for pick in rows]
    pregame = [row for row in audited if row["published_at_or_after_espn_start"] is False]
    pregame_performance = _pregame_performance(audited)
    pregame_coverage = {
        "late_by_expert": {
            expert: sum(row["expert"] == expert and row["published_at_or_after_espn_start"] is True for row in audited)
            for expert in sorted({row["expert"] for row in audited})
        },
        "unknown_kickoff_by_expert": {
            expert: sum(row["expert"] == expert and row["published_at_or_after_espn_start"] is None for row in audited)
            for expert in sorted({row["expert"] for row in audited})
        },
    }
    result = {
        "window": [WINDOW_START.isoformat(), WINDOW_END.isoformat()],
        "source": "The Betting Insider dated public website API",
        "source_endpoint": "/api/picks/list?mode=today&date=YYYY-MM-DD",
        "outcome_source": "ESPN scoreboard and game-summary box scores",
        "record_count": len(audited),
        "requested_dates": len(request_log),
        "successful_dates": sum("status" in item for item in request_log),
        "source_request_log": request_log,
        "performance_basis": pregame_performance["basis"],
        "summary": pregame_performance["by_expert"],
        "breakdown_by_expert_sport": pregame_performance["by_expert_sport"],
        "pregame_performance": pregame_performance,
        "pregame_coverage": pregame_coverage,
        "pregame_records": len(pregame),
        "current_pending_props": current,
        "espn_errors": errors,
        "rows": audited,
    }
    _report(result)
    print(json.dumps({
        "record_count": result["record_count"],
        "dates": f'{result["successful_dates"]}/{result["requested_dates"]}',
        "pregame_performance": pregame_performance,
        "espn_errors": len(errors),
        "reports": ["generated-artifacts/bettinginsider-prop-audit.html",
                    "generated-artifacts/bettinginsider-prop-audit.json"],
    }, indent=2))


if __name__ == "__main__":
    main()
