"""
vegasinsider_refresh.py — VegasInsider public betting trends + consensus odds
================================================================================

VegasInsider uses the same Action Network SSR platform as RotoGrinders
(bctn-vi.s3.amazonaws.com infrastructure, identical data-role/data-endpoint/
data-auth pattern). No login is required for the data collected here.

Two endpoints, both returning HTML fragments via XHR
(X-Requested-With: XMLHttpRequest):

1. /mlb/matchups/?date=DATE
   Pub betting % per team (ML/Total/Runline) + season SU/OU/ATS records.
   Cells are wrapped in data-auth="member" (free registered account) but
   the data IS present in the unauthenticated HTTP response -- it is a CSS
   display gate, not server-side redaction.

2. /mlb/picks/consensus/?date=DATE
   Opening line + current consensus line per game (free rows in the table:
   <tr class="game-odds open"> and <tr class="game-odds current">).
   Expert-pick counts require data-auth="subscriber" (paid).

Pushes to betcouncil_vegasinsider.json in GIST_ID.
"""

import gzip
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
TODAY = date.today().isoformat()

XHR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "X-Requested-With": "XMLHttpRequest",
}

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)
    DEBUG_LOG.append(f"[{ts}] {msg}")


def fetch_xhr(url: str, referer: str) -> str:
    headers = {**XHR_HEADERS, "Referer": referer}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def parse_matchups(html: str) -> list:
    """
    Parse /mlb/matchups/?date=DATE XHR response.

    Returns one dict per team row:
      team, ml_pct, total_pct (Over%), rl_pct,
      ml_side ("highlight"=ML favourite bets, "matte"=underdog),
      su_record, ou_record, ats_record, game_time_utc
    """
    games = []
    blocks = re.split(r'<tr class="header">', html)
    for block in blocks[1:]:
        rows = re.findall(r"<tr>(.*?)</tr>", block, re.DOTALL)
        for row in rows:
            if "team-plate" not in row:
                continue
            abbr_m = re.search(r'data-abbr="([A-Z]+)"', row)
            pills = re.findall(r'class="pill bold (\w+)">(\d+%)<', row)
            records = re.findall(r'class="small">\s*(\d+-\d+ [A-Z/]+)', row)
            time_m = re.search(r'data-value="([^"]+)"', block)
            if not abbr_m or len(pills) < 3:
                continue
            ml_side, ml_pct = pills[0]
            _, total_pct = pills[1]
            rl_side, rl_pct = pills[2]
            record: dict = {
                "team": abbr_m.group(1),
                "ml_pct": ml_pct,
                "total_pct": total_pct,
                "rl_pct": rl_pct,
                "ml_side": ml_side,
                "rl_side": rl_side,
            }
            if len(records) >= 3:
                record["su_record"] = records[0]
                record["ou_record"] = records[1]
                record["ats_record"] = records[2]
            if time_m:
                record["game_time_utc"] = time_m.group(1)
            games.append(record)
    return games


def parse_consensus(html: str) -> list:
    """
    Parse /mlb/picks/consensus/?date=DATE XHR response.

    Returns one dict per game:
      away_team, home_team, game_time_utc,
      open_ml, open_total, open_spread,
      consensus_ml, consensus_total, consensus_spread
    """
    results = []
    bodies = re.findall(r"<tbody>(.*?)</tbody>", html, re.DOTALL)
    for body in bodies:
        teams = re.findall(r'data-abbr="([A-Z]+)" aria-label="([^"]+)"', body)
        open_rows = re.findall(r'class="game-odds open">(.*?)</tr>', body, re.DOTALL)
        curr_rows = re.findall(r'class="game-odds current">(.*?)</tr>', body, re.DOTALL)
        time_m = re.search(r'data-value="([^"]+)"', body)
        if not teams or not open_rows or not curr_rows:
            continue

        def row_cells(row_html: str) -> list:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
            return [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

        open_cells = row_cells(open_rows[0])
        curr_cells = row_cells(curr_rows[0])
        record: dict = {
            "away_team": teams[0][0],
            "home_team": teams[1][0] if len(teams) >= 2 else "",
        }
        if time_m:
            record["game_time_utc"] = time_m.group(1)
        if len(open_cells) >= 4:
            record["open_ml"] = open_cells[1]
            record["open_total"] = open_cells[2]
            record["open_spread"] = open_cells[3]
        if len(curr_cells) >= 4:
            record["consensus_ml"] = curr_cells[1]
            record["consensus_total"] = curr_cells[2]
            record["consensus_spread"] = curr_cells[3]
        results.append(record)
    return results


def push_gist(payload: dict) -> None:
    if not GIST_ID or not GITHUB_TOKEN:
        log("No GIST_ID or GITHUB_TOKEN -- skipping push")
        return
    body = json.dumps({
        "files": {
            "betcouncil_vegasinsider.json": {
                "content": json.dumps(payload, indent=2)
            },
            "debug_log.txt": {
                "content": "\n".join(DEBUG_LOG)
            },
        }
    }, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read())
            log(f"Gist updated: {resp['html_url']}")
            return
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429, 409) and attempt < 2:
                base_wait = 10 * (2 ** attempt)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist push got HTTP {exc.code} -- retrying in {wait:.1f}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: HTTP {exc.code} {exc.read()[:300]}")
            return
        except Exception as exc:
            log(f"Gist push failed: {exc}")
            return


def main() -> None:
    now_utc = datetime.now(timezone.utc).isoformat()
    log(f"VegasInsider refresh starting -- date={TODAY}")

    base = "https://www.vegasinsider.com"

    try:
        matchups_html = fetch_xhr(
            f"{base}/mlb/matchups/?date={TODAY}",
            f"{base}/mlb/matchups/",
        )
        trends = parse_matchups(matchups_html)
        log(f"Matchup trends: {len(trends)} team rows parsed")
    except Exception as exc:
        log(f"ERROR fetching matchups: {exc}")
        trends = []

    try:
        consensus_html = fetch_xhr(
            f"{base}/mlb/picks/consensus/?date={TODAY}",
            f"{base}/mlb/picks/consensus/",
        )
        consensus = parse_consensus(consensus_html)
        log(f"Consensus lines: {len(consensus)} games parsed")
        if not consensus and consensus_html:
            # Real fix (2026-08-18): parse_consensus uses a regex-based
            # scraper against specific CSS class names / HTML structure.
            # "0 games parsed" with a real, non-empty HTML response almost
            # always means the site's markup changed and the regex no
            # longer matches -- but there was no way to see *what* changed
            # without capturing the actual HTML. Saving a real snippet so
            # the next failure's debug file shows the current structure.
            _snippet = consensus_html[:4000]
            _has_tbody = "<tbody>" in consensus_html
            _has_game_odds_open = 'class="game-odds open"' in consensus_html
            _has_game_odds_current = 'class="game-odds current"' in consensus_html
            _has_data_abbr = "data-abbr=" in consensus_html
            log(f"  DEBUG: html_len={len(consensus_html)} has_tbody={_has_tbody} "
                f"has_game_odds_open={_has_game_odds_open} "
                f"has_game_odds_current={_has_game_odds_current} "
                f"has_data_abbr={_has_data_abbr}")
    except Exception as exc:
        log(f"ERROR fetching consensus: {exc}")
        consensus = []
        _snippet = ""

    payload = {
        "source": "vegasinsider",
        "date": TODAY,
        "captured_at": now_utc,
        "sport": "mlb",
        "trends": trends,
        "consensus": consensus,
    }

    log(json.dumps(payload, indent=2))
    push_gist(payload)
    log("Done.")


if __name__ == "__main__":
    main()
