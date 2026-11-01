"""Current expert picks restricted to independently audited sport/market scopes.

Uses the site's public website API, NOT the historical-only developer /v1 API.
No login, full odds-board import, signal scoring, futures, or scheduler.
"""

import math
import re
from datetime import datetime, timedelta, timezone

import requests


BASE = "https://www.thebettinginsider.com"
SOURCE = "The Betting Insider — Goodelleaks"
EXPERTS = {
    "analyst_goodelleaks": ("Goodelleaks", ("NFL", "NCAAF"), ("moneyline", "spread", "total", "team_total", "team_total_over", "team_total_under")),
    "bf44041c-3090-481d-b584-5843256033b4": ("Invisible Insider", ("NFL", "NCAAF"), ("moneyline", "spread", "total")),
    "1f3ae3b4-893b-410c-8a1e-addd978e6d80": ("Insider Mike", ("MLB",), ("prop",)),
}
PICKS_URL = BASE + "/api/picks/list?mode=all"
_PERIOD = re.compile(
    r"\b(?:[12]H|Q[1-4]|[1-4]Q|[12](?:st|nd)\s+half|first\s+half|second\s+half"
    r"|(?:1st|first)\s+(?:quarter|inning)|F[15]|first\s+5)\b", re.I,
)
_TOTAL = re.compile(r"\b(over|under|o|u)\s*(\d+(?:\.\d+)?)", re.I)


def _mlb_prop_market(title):
    """Only market families represented in Mike's verified pregame sample."""
    t = title.lower()
    if re.search(r"\b(?:parlay|sgp|ml)\b", t):
        return None
    if "total bases" in t:
        return "batter_total_bases"
    if re.search(r"hits\s*\+\s*runs\s*\+\s*rbis|h/r/rbi|hrrbi", t):
        return "batter_hits_runs_rbis"
    if re.search(r"\bouts\b", t):
        return "pitcher_outs"
    if "strikeout" in t or re.search(r"\bks\b", t):
        return None if "batter" in t else "pitching_strikeouts"
    if "earned run" in t or re.search(r"\ber\b", t):
        return "pitcher_earned_runs"
    if "hits allowed" in t:
        return "pitcher_hits_allowed"
    if "walk" in t:
        return "pitching_walks" if "pitcher" in t else "batting_walks"
    if re.search(r"\bhits\b", t):
        return "batter_hits"
    return None


def _time(value):
    value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Expert timestamp has no timezone")
    return value.astimezone(timezone.utc)


def _get_json(url):
    with requests.get(url, timeout=(5, 15), stream=True) as response:
        response.raise_for_status()
        content, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > 5_000_000:
                raise ValueError("Live expert response exceeded the size limit")
            content.append(chunk)
        import json
        data = json.loads(b"".join(content))
    if not isinstance(data, dict) or data.get("success") is not True:
        raise ValueError("Live expert API returned an unsuccessful response")
    return data


def normalize_pending_picks(data, errors=None):
    if not isinstance(data.get("picks"), list):
        raise ValueError("The Betting Insider picks schema changed")
    output, seen = [], set()
    for p in data["picks"]:
        expert = EXPERTS.get(p.get("bettor_id"))
        if not expert:
            continue
        if p.get("result") != "pending" or not p.get("is_active") or p.get("is_future"):
            continue
        sport = {"NFL": "NFL", "CFB": "NCAAF", "NCAAF": "NCAAF", "MLB": "MLB"}.get(str(p.get("sport")).upper())
        market = str(p.get("bet_type", "")).lower()
        title = str(p.get("bet_title", "")).strip()
        if sport not in expert[1] or market not in expert[2]:
            continue
        # The source sometimes labels half-game totals simply "total".
        if _PERIOD.search(title):
            continue
        if expert[0] == "Invisible Insider" and re.search(r"\b(?:tt|team\s+total)\b", title, re.I):
            continue
        prop_market = _mlb_prop_market(title) if market == "prop" else None
        if market == "prop" and not prop_market:
            continue
        try:
            start, posted = _time(p["game_time"]), _time(p.get("posted_at") or p["created_at"])
            if posted >= start:
                continue
            odds = float(str(p["odds"]).replace("−", "-"))
            units = float(p["units"])
            if not math.isfinite(odds) or abs(odds) < 100 or not math.isfinite(units) or units <= 0:
                raise ValueError("Invalid published price or stake")
            teams = p["game_title"].split(" @ ")
            if len(teams) != 2 or not all(t.strip() for t in teams) or not p.get("game_id") or not title:
                raise ValueError("Missing event identity")
            if market == "spread" and not re.search(r"[+-]\d+(?:\.\d+)?|\b(?:pk|pick.?em)\b", title, re.I):
                raise ValueError("Missing original spread")
            if ("total" in market) and not _TOTAL.search(title):
                raise ValueError("Missing original total")
            if market == "prop" and not (_TOTAL.search(title) or re.search(r"\b\d+\+\s", title)):
                raise ValueError("Missing original player-prop threshold")
            identity = str(p["id"])
            if identity in seen:
                continue
            seen.add(identity)
            output.append({
                "id": identity, "source": "The Betting Insider — " + expert[0], "sport": sport,
                "away": teams[0].strip(), "home": teams[1].strip(),
                "event_key": p["game_id"], "start_time": start.isoformat(),
                "published_at": posted.isoformat(), "selection": title,
                "market": market, "american_odds": odds,
                "expert_units": units, "published_book": str(p.get("sportsbook") or "book not supplied"),
                "prop_market": prop_market,
            })
        except (KeyError, TypeError, ValueError) as exc:
            if errors is not None:
                errors.append("The Betting Insider — " + expert[0] + ": malformed approved pending pick")
                continue
            raise ValueError("The Betting Insider has a malformed approved pending pick") from exc
    return output


def _current(picks, now):
    return [
        p for p in picks
        if _time(p["published_at"]) <= now < _time(p["start_time"]) <= now + timedelta(days=7)
    ]


def fetch_public_snapshot():
    now = datetime.now(timezone.utc)
    pick_errors = []
    picks = _current(normalize_pending_picks(_get_json(PICKS_URL), errors=pick_errors), now)
    wanted = {p["event_key"] for p in picks}
    markets, errors = {}, []
    for sport in sorted({p["sport"] for p in picks}):
        query = {"NFL": "nfl", "NCAAF": "ncaaf", "MLB": "mlb"}[sport]
        try:
            data = _get_json(BASE + "/api/games/upcoming?sport=" + query)
            if not isinstance(data.get("games"), list):
                raise ValueError("Current market schema changed")
            for game in data["games"]:
                if game.get("id") in wanted:
                    markets[game["id"]] = {
                        key: game.get(key) for key in (
                            "id", "kickoff", "homeTeam", "awayTeam", "homeTeamAbbr",
                            "awayTeamAbbr", "spread", "totals", "moneyline", "sportsbook",
                        )
                    }
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(f"{sport}: {type(exc).__name__}")
    return {
        "picks": picks, "markets": markets, "market_errors": errors,
        "pick_errors": pick_errors,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def market_reference(pick, game):
    if pick["market"] == "prop":
        return "Current player-prop quote not supplied by the game-line feed"
    if not game or abs((_time(game["kickoff"]) - _time(pick["start_time"])).total_seconds()) > 300:
        return "Current market unavailable"
    market = pick["market"]
    title = pick["selection"]
    if market == "total":
        value = (game.get("totals") or {}).get("number")
        return f"Current consensus total {value:g} (price not supplied)" if isinstance(value, (int, float)) else "Current total unavailable"
    if market.startswith("team_total"):
        return "Current team total unavailable"
    prefix = _norm(re.split(r"[+-]\d|\bML\b|·", title, flags=re.I)[0])
    sides = []
    for side in ("home", "away"):
        aliases = [game.get(side + "Team"), game.get(side + "TeamAbbr"), pick[side]]
        if prefix and any(
            _norm(a) and (prefix == _norm(a) or prefix.endswith(_norm(a)) or _norm(a).endswith(prefix))
            for a in aliases
        ):
            sides.append(side)
    if len(sides) != 1:
        return "Current selected-side market unavailable"
    side = sides[0]
    if market == "moneyline":
        value = (game.get("moneyline") or {}).get(side)
        return f"Current consensus {game.get(side + 'TeamAbbr', side)} ML {value:+g}" if isinstance(value, (int, float)) else "Current moneyline unavailable"
    value = (game.get("spread") or {}).get(side + "Line")
    return f"Current consensus {game.get(side + 'TeamAbbr', side)} {value:+g} (price not supplied)" if isinstance(value, (int, float)) else "Current spread unavailable"


def prediction_items(snapshot, now=None):
    now = now or datetime.now(timezone.utc)
    fetched = _time(snapshot["fetched_at"])
    if now - fetched > timedelta(minutes=10) or fetched > now + timedelta(minutes=1):
        raise ValueError("The Betting Insider snapshot is stale or future-dated")
    return [{
        **p,
        "text": (
            f"{p['selection']} ({p['american_odds']:+g}, published at {p['published_book']})"
            f" · {p['expert_units']:g}u expert stake"
            f" · posted {_time(p['published_at']):%b %d %H:%M UTC}"
            f" · {market_reference(p, snapshot['markets'].get(p['event_key']))}"
            f" · retrieved {fetched:%H:%M UTC}; market quote age not supplied"
            " · consensus is not an executable book quote"
        ),
    } for p in _current(snapshot["picks"], now)]
