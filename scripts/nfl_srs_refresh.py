"""
nfl_srs_refresh.py -- opponent-adjusted NFL team ratings from ACTUAL results (SRS).

Replaces the raw-points-per-game / preseason-odds ratings that pinned nearly every NFL spread
at the edge cap. Source: ESPN public scoreboard (final scores for the current season).
Margins are home-field adjusted (2.0) and capped at +/-24 (garbage-time blowouts), then solved
iteratively: rating = avg adjusted margin + avg opponent rating. Output is in POINTS vs average team.
Writes betcouncil_nfl_srs.json (keyed by full name and abbreviation) with captured_at.
"""
import json, os, sys
from datetime import date, datetime, timezone
import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HFA, CAP = 2.0, 24.0


def log(m): print(f"[nfl_srs] {m}", flush=True)


def season_start(today):
    y = today.year if today.month >= 8 else today.year - 1
    return date(y, 9, 1)


def fetch_games(today):
    a, b = season_start(today).strftime("%Y%m%d"), today.strftime("%Y%m%d")
    r = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
                     params={"dates": f"{a}-{b}", "limit": 1000, "seasontype": 2},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=40)
    r.raise_for_status()
    games = []
    for ev in r.json().get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        if not ev.get("status", {}).get("type", {}).get("completed"):
            continue
        cs = comp.get("competitors", [])
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        try:
            hs, as_ = float(home["score"]), float(away["score"])
        except (KeyError, TypeError, ValueError):
            continue
        games.append((home["team"]["displayName"], home["team"]["abbreviation"],
                      away["team"]["displayName"], away["team"]["abbreviation"], hs, as_))
    return games


def solve(games):
    abbr, rows = {}, []
    for hn, ha, an, aa, hs, as_ in games:
        abbr[hn], abbr[an] = ha, aa
        m = max(-CAP, min(CAP, (hs - as_) - HFA))   # neutral-field home margin
        rows.append((hn, an, m))
    teams = sorted(abbr)
    r = {t: 0.0 for t in teams}
    for _ in range(200):
        new = {}
        for t in teams:
            ms = [m if h == t else -m for h, a, m in rows if h == t or a == t]
            opp = [r[a] if h == t else r[h] for h, a, m in rows if h == t or a == t]
            new[t] = (sum(ms) + sum(opp)) / len(ms) if ms else 0.0
        mean = sum(new.values()) / len(new)
        r = {t: v - mean for t, v in new.items()}
    n = {t: sum(1 for h, a, _ in rows if t in (h, a)) for t in teams}
    return r, abbr, n


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    games = fetch_games(date.today())
    log(f"{len(games)} completed regular-season games")
    if len(games) < 50:
        log("too few games -- not writing")
        return 1
    r, abbr, n = solve(games)
    out = {"captured_at": datetime.now(timezone.utc).isoformat(), "games": len(games), "ratings": {}}
    for t, v in r.items():
        out["ratings"][t] = round(v, 2)
        out["ratings"][abbr[t]] = round(v, 2)
    out["games_played"] = {t: n[t] for t in n}
    for t, v in sorted(r.items(), key=lambda kv: -kv[1])[:5]:
        log(f"  {t}: {v:+.1f}")
    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"files": {"betcouncil_nfl_srs.json": {"content": json.dumps(out, indent=1)}}}, timeout=60)
    log(f"gist write {resp.status_code}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
