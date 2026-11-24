"""
clv_closing.py — closing-line value (CLV) for graded game-line picks.

Source: Odds-API.io v3 free plan (/historical/events + /historical/odds,
DraftKings + FanDuel only; payload is decimal odds captured at kickoff, so
it IS the closing line). No sharp/Pinnacle close on the free plan -- CLV is
therefore measured against DK/FD, stated plainly in the output ("close_book").

Per pick (added to grading rows by daily_board_grading.py):
  MONEYLINE: clv_ev = open_decimal * close_no_vig_prob - 1   (>0 = beat the close)
  SPREAD/TOTAL: clv_pts = points of line value vs the close (>0 = beat the close)
Picks with no stored opening price/line just get no CLV fields.
"""
import os
import re
import requests
from datetime import datetime, timedelta, timezone

BASE = "https://api.odds-api.io/v3"
_LEAGUE = {"NFL": ("american-football", "usa-nfl"),
           "NCAAF": ("american-football", "usa-ncaaf"),
           "NBA": ("basketball", "usa-nba"),
           "NHL": ("ice-hockey", "usa-nhl"),
           "MLB": ("baseball", "usa-mlb")}
_BOOKS = "DraftKings,FanDuel"
_events_cache = {}


def _key():
    return os.environ.get("ODDS_API_IO_KEY", "")


def _get(path, **params):
    params["apiKey"] = _key()
    try:
        r = requests.get(f"{BASE}{path}", params=params, timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _events(sport, target_date):
    if (sport, target_date) in _events_cache:
        return _events_cache[(sport, target_date)]
    sp, lg = _LEAGUE.get(sport, (None, None))
    out = []
    if sp and _key():
        d = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        out = _get("/historical/events", sport=sp, league=lg,
                   **{"from": (d - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "to": (d + timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")}) or []
    _events_cache[(sport, target_date)] = out
    return out


def _dec(american):
    try:
        a = float(str(american).replace("+", ""))
    except Exception:
        return None
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def _find_event(sport, target_date, home, away):
    for ev in _events(sport, target_date):
        if _norm(ev.get("home")) == _norm(home) and _norm(ev.get("away")) == _norm(away):
            return ev
    for ev in _events(sport, target_date):  # loose match on last word (team nickname)
        if _norm(home).endswith(_norm((ev.get("home") or "x").split()[-1])) and \
           _norm(away).endswith(_norm((ev.get("away") or "x").split()[-1])):
            return ev
    return None


def _close_markets(ev):
    d = _get("/historical/odds", eventId=ev["id"], bookmakers=_BOOKS, markets="ML,Spread,Totals")
    if not isinstance(d, dict):
        return None, None
    for book in ("DraftKings", "FanDuel"):
        ms = {m.get("name"): m.get("odds") or [] for m in (d.get("bookmakers", {}).get(book) or [])}
        if ms:
            return ms, book
    return None, None


def compute_clv(pick, sport, target_date):
    """Return dict of CLV fields for one snapshot pick ({} if not computable)."""
    home, away = pick.get("home", ""), pick.get("away", "")
    market = pick.get("market", "")
    if market not in ("MONEYLINE", "SPREAD", "TOTAL"):
        return {}
    ev = _find_event(sport, target_date, home, away)
    if not ev:
        return {}
    ms, book = _close_markets(ev)
    if not ms:
        return {}
    pick_home = _norm(pick.get("pick", "")).startswith(_norm(home)[:6]) or _norm(home) in _norm(pick.get("pick", ""))
    try:
        if market == "MONEYLINE":
            o = (ms.get("ML") or [{}])[0]
            h, a = float(o["home"]), float(o["away"])
            ph, pa = 1 / h, 1 / a
            fair = (ph if pick_home else pa) / (ph + pa)
            open_dec = _dec(pick.get("odds"))
            if open_dec is None:
                return {}
            return {"close_book": book, "close_novig_prob": round(fair, 4),
                    "open_decimal": round(open_dec, 3), "clv_ev": round(open_dec * fair - 1, 4)}
        if market == "SPREAD":
            rows = ms.get("Spread") or []
            if not rows or pick.get("line") in (None, ""):
                return {}
            close_home = float(min(rows, key=lambda r: abs(float(r["home"]) - float(r["away"])))["hdp"])
            my_home = float(pick["line"])  # snapshot line = home spread
            # closing hdp in the feed is the home line; positive hdp = home gets points
            pts = (my_home - close_home) if pick_home else (close_home - my_home)
            return {"close_book": book, "close_line_home": close_home, "clv_pts": round(pts, 1)}
        if market == "TOTAL":
            rows = ms.get("Totals") or []
            if not rows or not pick.get("line"):
                return {}
            close_t = float(min(rows, key=lambda r: abs(float(r["over"]) - float(r["under"])))["hdp"])
            my_t = float(pick["line"])
            over = str(pick.get("pick", "")).upper().startswith("OVER")
            pts = (close_t - my_t) if over else (my_t - close_t)
            return {"close_book": book, "close_total": close_t, "clv_pts": round(pts, 1)}
    except Exception:
        return {}
    return {}
