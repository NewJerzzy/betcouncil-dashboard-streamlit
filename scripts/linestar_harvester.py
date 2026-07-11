"""
LineStar public API harvester — no auth, no login, no browser required.

Fetches GetFastUpdateV2, GetPropBets, and GetSalariesV5 for every active sport.

DFS sites fetched:
  Site=1 (DraftKings) -- always fetched; $50k cap, DK scoring
  Site=2 (FanDuel)    -- fetched in parallel; $35k cap, FD scoring (~30% higher
                        PP values), ~18 FD-exclusive players per MLB slate
  Site=3 (Yahoo)      -- returns None/empty; Yahoo DFS is dead, skipped

Sport IDs confirmed 2026-07: NFL=1, NBA=2, MLB=3, NHL=6, WNBA=12.
PeriodId fetched live per sport from the Projections page.

TeamMap built from PropBets.Teams[] + SalariesV5 HTID/HTEAM+OTID/OTEAM.
PropBets is site-agnostic -- fetched once (Site=1), covers all books.

Gist files produced per active sport:
  betcouncil_weather_{SPORT}.json              -- DK weather + Vegas lines
  betcouncil_linestar_props_{SPORT}.json       -- GetPropBets (all books)
  betcouncil_linestar_salaries_{SPORT}.json    -- DK GetSalariesV5
  betcouncil_weather_FD_{SPORT}.json           -- FD weather (same Games + FD Items)
  betcouncil_linestar_salaries_FD_{SPORT}.json -- FD GetSalariesV5
  (FD files only emitted when FD has an active slate that day)

Env vars required:
  GITHUB_TOKEN -- PAT with gist write scope (mapped from PICK6_GIST_TOKEN secret)
"""

import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

GIST_ID   = "7e52e1c2c2054847c7c4663a157386c5"
BASE_LS   = "https://www.linestarapp.com/DesktopModules/DailyFantasyApi/API/Fantasy"
PAGE_BASE = "https://www.linestarapp.com/Projections/Sport"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SPORTS = {
    "MLB":  {"id": 3,  "path": "MLB"},
    "WNBA": {"id": 12, "path": "WNBA"},
    "NFL":  {"id": 1,  "path": "NFL"},
    "NBA":  {"id": 2,  "path": "NBA"},
    "NHL":  {"id": 6,  "path": "NHL"},
}


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_json(url, retries=2):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.linestarapp.com/Projections",
    }
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except Exception as exc:
            if attempt < retries:
                time.sleep(2)
            else:
                raise exc
    return {}


def fetch_html(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html",
        "X-Requested-With": "XMLHttpRequest",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def get_period_id(sport_path):
    try:
        html = fetch_html(f"{PAGE_BASE}/{sport_path}/Site/DraftKings/")
        m = re.search(r"LineStar\.PeriodId\s*=\s*(\d+)", html)
        return m.group(1) if m else None
    except Exception as exc:
        log(f"  [warn] PeriodId fetch failed for {sport_path}: {exc}")
        return None


def sal_count(sv):
    try:
        sc = json.loads(sv.get("SalaryContainerJson") or "{}")
        return len(sc.get("Salaries") or [])
    except Exception:
        return 0


def build_team_map(pb, sv):
    team_map = {}
    for t in pb.get("Teams") or []:
        if isinstance(t, dict) and t.get("Id") and t.get("Abbreviation"):
            team_map[t["Id"]] = t["Abbreviation"]
    try:
        sc = json.loads(sv.get("SalaryContainerJson") or "{}")
        for s in sc.get("Salaries") or []:
            if isinstance(s, dict):
                if s.get("HTID") and s.get("HTEAM"):
                    team_map[s["HTID"]] = s["HTEAM"]
                if s.get("OTID") and s.get("OTEAM"):
                    team_map[s["OTID"]] = s["OTEAM"]
    except Exception as exc:
        log(f"  [warn] SalariesV5 teamMap parse: {exc}")
    return team_map


def enrich_games(fu, team_map):
    games = [
        {**g,
         "_AwayAbbr": team_map.get(g.get("AwayTeamId")),
         "_HomeAbbr": team_map.get(g.get("HomeTeamId"))}
        for g in ((fu or {}).get("Games") or [])
        if isinstance(g, dict)
    ]
    return {**(fu or {}), "Games": games, "TeamMap": team_map}


def run_sport(sport, cfg, captured_at):
    log(f"\n-- {sport} (id={cfg['id']}) --")
    period_id = get_period_id(cfg["path"])
    if not period_id:
        log(f"  [skip] No PeriodId -- no slate today")
        return None
    log(f"  PeriodId: {period_id}")

    sid = cfg["id"]

    def _get(ep, site):
        return fetch_json(f"{BASE_LS}/{ep}?Sport={sid}&Site={site}&PeriodId={period_id}")

    with ThreadPoolExecutor(max_workers=5) as pool:
        fut_fu_dk = pool.submit(_get, "GetFastUpdateV2", 1)
        fut_pb    = pool.submit(_get, "GetPropBets",     1)
        fut_sv_dk = pool.submit(_get, "GetSalariesV5",   1)
        fut_fu_fd = pool.submit(_get, "GetFastUpdateV2", 2)
        fut_sv_fd = pool.submit(_get, "GetSalariesV5",   2)
        try:
            fu_dk = fut_fu_dk.result(timeout=30)
            pb    = fut_pb.result(timeout=30)
            sv_dk = fut_sv_dk.result(timeout=60)
            fu_fd = fut_fu_fd.result(timeout=30)
            sv_fd = fut_sv_fd.result(timeout=60)
        except Exception as exc:
            log(f"  [error] Fetch failed: {exc}")
            return None

    games = (fu_dk or {}).get("Games") or []
    if not games:
        log(f"  [skip] 0 games -- offseason or empty slate")
        return None

    dk_n = sal_count(sv_dk)
    fd_n = sal_count(sv_fd) if sv_fd else 0
    log(f"  DK: {len(games)} games, {dk_n} players  |  FD: {fd_n} players  |  Props: {len(pb.get('PropBets') or [])}")

    team_map    = build_team_map(pb, sv_dk)
    enriched_dk = enrich_games(fu_dk, team_map)
    matched     = sum(1 for g in enriched_dk["Games"] if g.get("_AwayAbbr") and g.get("_HomeAbbr"))
    log(f"  TeamMap: {len(team_map)} teams, {matched}/{len(games)} games matched")

    meta = {"sport": sport, "captured_at": captured_at,
            "period_id": period_id, "source": "linestar_github_actions"}

    files = {
        f"betcouncil_weather_{sport}.json":           json.dumps({**meta, "data": enriched_dk}),
        f"betcouncil_linestar_props_{sport}.json":    json.dumps({**meta, "data": pb}),
        f"betcouncil_linestar_salaries_{sport}.json": json.dumps({**meta, "data": sv_dk}),
    }

    if fd_n > 0:
        enriched_fd = enrich_games(fu_fd, team_map)
        files[f"betcouncil_weather_FD_{sport}.json"]           = json.dumps({**meta, "site": "FanDuel", "data": enriched_fd})
        files[f"betcouncil_linestar_salaries_FD_{sport}.json"] = json.dumps({**meta, "site": "FanDuel", "data": sv_fd})
        log(f"  FanDuel slate active -- adding FD files")
    else:
        log(f"  FanDuel: no slate today -- skipping FD files")

    return files


def push_gist(files, token):
    payload = json.dumps({"files": {k: {"content": v} for k, v in files.items()}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=payload, method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        resp = json.loads(r.read())
    log(f"  Gist updated -- {len(resp.get('files', {}))} files")


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("GITHUB_TOKEN not set")

    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    log(f"LineStar harvester started -- {captured_at}")

    all_files = {}
    for sport, cfg in SPORTS.items():
        result = run_sport(sport, cfg, captured_at)
        if result:
            all_files.update(result)

    log(f"\nStaged {len(all_files)} files -- pushing to Gist ...")
    for f in sorted(all_files):
        log(f"  {f}  ({len(all_files[f]):,} bytes)")

    if all_files:
        push_gist(all_files, token)
    else:
        log("[warn] Nothing to push -- all sports had empty slates")


if __name__ == "__main__":
    main()
