"""Rithmm model-pick collector (ported from the Research Lab's rithmmResearch.ts / rithmmExpertPicks.ts).

Logs into the owner's OWN Rithmm account with a headless browser, captures the app's own authorized
read requests (matches best_bets, player_props best_bets), replays them with pagination, and keeps ONLY
explicit native recommendations (bet_recommended == true, not locked, explicit side). Nothing is inferred
from projections. Picks are attributed to Rithmm models (one provider, not independent experts).
Scout / Parlay Optimizer are NOT connected. Output: Gist file betcouncil_rithmm.json.
Secrets: RITHMM_LOGIN_EMAIL, RITHMM_LOGIN_PASSWORD, GITHUB_TOKEN (Gist write).
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

GIST_ID = os.environ.get("GITHUB_GIST_ID", "7e52e1c2c2054847c7c4663a157386c5")
APP = "https://app.rithmm.com"
API = "https://api.rithmm.com"
GAME_PATH = "/api/v3/info/matches/best_bets/"
PROP_PATH = "/api/v4/info/player_props/best_bets/"
OUT_FILE = "betcouncil_rithmm.json"
SPORTS = {"nfl": "NFL", "nba": "NBA", "wnba": "WNBA", "mlb": "MLB", "cfb": "NCAAF", "cbb": "NCAAB", "golf": "GOLF",
          "ncaaf": "NCAAF", "ncaab": "NCAAB", "nhl": "NHL"}


def log(m):
    print(m, flush=True)


# ---------------------------------------------------------------- normalization (pure, testable)
def _t(*vals):
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
    return ""


def _num(*vals):
    for v in vals:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def _league(v):
    return SPORTS.get(str(v or "").strip().lower(), str(v or "").upper())


def _index(rows, *keys):
    out = {}
    for r in rows or []:
        if isinstance(r, dict):
            k = _t(*[r.get(x) for x in keys])
            if k:
                out[k] = r
    return out


def _prob(v):
    v = _num(v)
    if v is None:
        return None
    v = v / 100 if v > 1 else v
    return v if 0 <= v <= 1 else None


def normalize_games(raw: dict) -> list:
    teams = _index(raw.get("teams"), "team_id", "id")
    games = _index(raw.get("games"), "game_id", "id")
    odds = _index(raw.get("game_odds"), "game_odds_id")
    models = _index(raw.get("models"), "model_id", "id")
    out, seen = [], set()
    for parent in raw.get("best_bets") or []:
        if not isinstance(parent, dict):
            continue
        kids = parent.get("predictions") if isinstance(parent.get("predictions"), list) else [parent]
        for i, kid in enumerate(kids):
            row = {**parent, **(kid if isinstance(kid, dict) else {})}
            pred = row.get("prediction") if isinstance(row.get("prediction"), dict) else {}
            if row.get("locked") is True or row.get("is_locked") is True or pred.get("bet_recommended") is not True:
                continue
            g = games.get(_t(row.get("game_id")))
            if not g:
                continue
            home = _t((teams.get(_t(g.get("home_team_id"))) or {}).get("full_name"), (teams.get(_t(g.get("home_team_id"))) or {}).get("name"))
            away = _t((teams.get(_t(g.get("away_team_id"))) or {}).get("full_name"), (teams.get(_t(g.get("away_team_id"))) or {}).get("name"))
            if not (home and away):
                continue
            o = odds.get(_t(row.get("game_odds_id"))) or {}
            code = _t(pred.get("bet_type")).lower()
            hs, as_, ou = _num(o.get("home_team_point_spread")), _num(o.get("away_team_point_spread")), _num(o.get("over_under"))
            if code == "home_spread" and hs is not None:
                market, pick, line = "SPREAD", home, hs
            elif code == "away_spread" and as_ is not None:
                market, pick, line = "SPREAD", away, -as_   # stored home-relative, as the grader expects
            elif code == "home_ml":
                market, pick, line = "MONEYLINE", home, 0
            elif code == "away_ml":
                market, pick, line = "MONEYLINE", away, 0
            elif code in ("over", "under") and ou is not None:
                market, pick, line = "TOTAL", f"{code.upper()} {ou:g}", ou
            else:
                continue
            m = models.get(_t(row.get("model_id"))) or {}
            key = (_t(row.get("game_id")), market, pick, _t(row.get("model_id")))
            if key in seen:
                continue
            seen.add(key)
            out.append({"source": "rithmm", "sport": _league(g.get("sport") or row.get("sport")),
                        "matchup": f"{away} @ {home}", "home": home, "away": away, "market": market,
                        "pick": pick, "line": line, "expert": f"Rithmm · {_t(m.get('name')) or 'Model'}",
                        "implied_prob": _prob(pred.get("probability")), "starts_at": _t(g.get("date_time")) or None})
    return out


# Only stat labels the grader's mapper resolves correctly; unknown Rithmm codes are dropped, never guessed.
_PROP_LABEL = {
    "NBA": {"points": "Points", "rebounds": "Rebounds", "assists": "Assists", "steals": "Steals", "blocks": "Blocks",
            "threes": "3-Pointers Made", "three_pointers_made": "3-Pointers Made", "3pm": "3-Pointers Made"},
    "NFL": {"receiving_yards": "Receiving Yards", "rushing_yards": "Rushing Yards", "passing_yards": "Passing Yards"},
    "NHL": {"goals": "Goals", "assists": "Assists", "points": "Points", "shots_on_goal": "Shots on Goal"},
}


def normalize_props(raw: dict, stats: dict = None) -> list:
    stats = stats if stats is not None else {}
    teams = _index(raw.get("teams"), "team_id", "id")
    players = _index(raw.get("players"), "player_id", "id")
    models = _index(raw.get("models"), "model_id", "id")
    out, seen = [], set()
    for g in raw.get("games") or []:
        if not isinstance(g, dict):
            continue
        sport = _league(g.get("sport"))
        buckets = list(g.get("prop_predictions") or [])
        extra = [b for b in (raw.get("best_bets") or []) if isinstance(b, dict) and _t(b.get("game_id")) == _t(g.get("game_id"))]
        if extra:
            buckets.append({"predictions": extra})
        for b in buckets:
            for p in (b.get("predictions") or []):
                if not isinstance(p, dict):
                    continue
                side = _t(p.get("pick"), p.get("recommendation"), p.get("side"), p.get("lean"),
                          p.get("prediction") if isinstance(p.get("prediction"), str) else "").lower()
                if p.get("bet_recommended") is not True or p.get("locked") is True or p.get("is_locked") is True \
                        or side not in ("over", "under"):
                    continue
                pl = players.get(_t(p.get("player_id"))) or {}
                name = f"{_t(p.get('player_first_name'), pl.get('first_name'))} {_t(p.get('player_last_name'), pl.get('last_name'))}".strip()
                line = _num(p.get("sb_ou_value"), p.get("line"))
                code = _t(p.get("bet_type_code"), b.get("bet_type_code")).lower().replace(" ", "_")
                label = _PROP_LABEL.get(sport, {}).get(code)
                if not name or line is None:
                    continue
                if not label:
                    stats[code or "?"] = stats.get(code or "?", 0) + 1
                    continue
                m = models.get(_t(p.get("model_id"), b.get("model_id"))) or {}
                key = (_t(g.get("game_id")), name, label, line, side, _t(p.get("model_id")))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"source": "rithmm", "sport": sport, "player": name, "prop_type": label, "line": line,
                            "side": side.upper(), "expert": f"Rithmm · {_t(m.get('name')) or 'Model'}",
                            "implied_prob": _prob(p.get("probability")), "starts_at": _t(g.get("date_time")) or None})
    return out


# ---------------------------------------------------------------- live collection
def _merge(result, batch):
    for k in ("best_bets", "games", "teams", "players", "models", "prop_odds", "game_odds"):
        if isinstance(batch.get(k), list):
            comb = (result.get(k) or []) + batch[k]
            result[k] = list({json.dumps(r, sort_keys=True): r for r in comb}.values())


def collect_raw():
    from playwright.sync_api import sync_playwright
    email, pw = os.environ.get("RITHMM_LOGIN_EMAIL"), os.environ.get("RITHMM_LOGIN_PASSWORD")
    if not (email and pw):
        raise RuntimeError("RITHMM_LOGIN_EMAIL / RITHMM_LOGIN_PASSWORD not set")
    auth, tmpl, captured = {}, {}, {}
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--disable-gpu"])
        ctx = br.new_context(service_workers="block", viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.set_default_timeout(10000)

        def on_req(r):
            if not r.url.startswith(API):
                return
            path = r.url[len(API):].split("?")[0]
            if path in (GAME_PATH, PROP_PATH):
                a = r.headers.get("authorization")
                if a and a.startswith("Bearer "):
                    auth[path] = a
                tmpl[path] = {"method": r.method, "body": r.post_data or "", "ct": r.headers.get("content-type", "application/json")}

        def on_resp(r):
            if not r.url.startswith(API) or not (200 <= r.status < 300):
                return
            path = r.url[len(API):].split("?")[0]
            if path in (GAME_PATH, PROP_PATH):
                try:
                    captured.setdefault(path, []).append(r.json())
                except Exception:
                    pass

        page.on("request", on_req)
        page.on("response", on_resp)
        page.goto(f"{APP}/signup_landing", wait_until="domcontentloaded", timeout=20000)
        page.locator('input[type="email"], input[name*="email" i]').first.fill(email)
        page.get_by_text("continue with email", exact=False).first.click()
        page.locator('input[type="password"]:visible, input[name*="password" i]:visible').first.fill(pw)
        page.get_by_text("Sign in", exact=True).last.click()
        try:
            page.wait_for_url("**/home**", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(8000)
        body = (page.locator("body").inner_text() or "").lower()
        if any(w in body for w in ("verification code", "authenticator", "captcha", "verify you are human")):
            raise RuntimeError("Rithmm login blocked by MFA/CAPTCHA")
        if "/home" not in page.url.lower():
            raise RuntimeError(f"Rithmm login failed (landed on {page.url.split('?')[0]})")
        br.close()

    raw = {GAME_PATH: {}, PROP_PATH: {}}
    for path in (GAME_PATH, PROP_PATH):
        for first in captured.get(path, []):
            if isinstance(first, dict):
                _merge(raw[path], first)
        t, a = tmpl.get(path), auth.get(path) or next(iter(auth.values()), "")
        if not (t and a):
            log(f"  {path}: no captured request template/token — using only the app's own responses")
            continue
        # replay for every sport when the app's body carries a sport selector, else once as captured
        bodies = [t["body"]]
        try:
            j = json.loads(t["body"]) if t["body"] else None
            if isinstance(j, dict) and isinstance(j.get("sport"), str):
                bodies = [json.dumps({**j, "sport": s.upper()}) for s in ("NFL", "NBA", "MLB", "CFB", "CBB", "WNBA")]
        except Exception:
            pass
        for body in bodies:
            url, pages = f"{API}{path}", 0
            while url and pages < 40:
                r = requests.request(t["method"], url, data=body or None, timeout=30, headers={
                    "Accept": "application/json", "Authorization": a, "Origin": APP, "Referer": f"{APP}/home",
                    "Content-Type": t["ct"]})
                if r.status_code != 200:
                    log(f"  {path}: HTTP {r.status_code}")
                    break
                j = r.json()
                _merge(raw[path], j)
                url, pages = j.get("next"), pages + 1
    return raw


def gist_write(token, payload):
    for attempt in range(4):
        r = requests.patch(f"https://api.github.com/gists/{GIST_ID}", timeout=30,
                           headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                           json={"files": {OUT_FILE: {"content": json.dumps(payload)}}})
        if r.status_code in (200, 201):
            return True
        if r.status_code == 409 and attempt < 3:
            time.sleep((attempt + 1) * 5)
            continue
        log(f"gist write failed {r.status_code}")
        return False
    return False


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1
    status = {"captured_at": datetime.now(timezone.utc).isoformat(), "games": [], "props": [], "status": "ok"}
    try:
        raw = collect_raw()
        dropped = {}
        status["games"] = normalize_games(raw[GAME_PATH])
        status["props"] = normalize_props(raw[PROP_PATH], dropped)
        status["unmapped_prop_codes"] = dropped
        log(f"rithmm: {len(status['games'])} game picks, {len(status['props'])} prop picks, unmapped prop codes {dropped}")
    except Exception as e:
        status["status"] = f"error: {str(e)[:200]}"
        log(f"rithmm collector error: {e}")
        # keep the previous good picks rather than blanking them on a transient login failure
        try:
            prev = requests.get(f"https://gist.githubusercontent.com/NewJerzzy/{GIST_ID}/raw/{OUT_FILE}?cb={int(time.time())}", timeout=20).json()
            status["games"], status["props"] = prev.get("games", []), prev.get("props", [])
            status["stale_from"] = prev.get("captured_at")
        except Exception:
            pass
    ok = gist_write(token, status)
    return 0 if ok and status["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
