"""On-demand expert audit. Never runs in the dashboard or an ingestion job.

Input is the dated public pick history, including losses. ESPN responses are
cached under ignored generated-artifacts/ so grading can be inspected/repeated
without downloading every scoreboard and box score again.
"""

import argparse
import hashlib
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "generated-artifacts" / "espn-expert-audit-cache"
PATHS = {
    "NFL": "football/nfl", "CFB": "football/college-football",
    "NCAAF": "football/college-football", "MLB": "baseball/mlb",
    "NBA": "basketball/nba", "NHL": "hockey/nhl",
}
ABBR = {"WSH": "WAS", "JAX": "JAC", "ATH": "OAK", "AZ": "ARI", "CWS": "CHW", "KC": "KCR", "SF": "SFG", "SD": "SDP", "TB": "TBR"}


def get_json(url):
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text())
    r = requests.get(url, timeout=(5, 25))
    r.raise_for_status()
    data = r.json()
    # Strip news, videos, ads, standings and odds. They are not audit evidence.
    keep = ("events",) if "events" in data else ("header", "boxscore", "plays", "scoringPlays")
    data = {k: data[k] for k in keep if k in data}
    if not data:
        raise ValueError("ESPN returned no score or box-score evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))
    return data


def utc(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def sport_path(p):
    return PATHS.get(str(p.get("sport")).upper())


def date_key(p):
    # Date in the source event key is the Eastern slate date, not UTC midnight.
    m = re.match(r"^[A-Z]+-(\d{8})-", p.get("game_id") or "")
    return m[1] if m else (utc(p["game_time"]) - timedelta(hours=4)).strftime("%Y%m%d")


def scoreboard_url(path, day):
    return "https://site.api.espn.com/apis/site/v2/sports/" + path + "/scoreboard?dates=" + day + ("&groups=80&limit=200" if path.endswith("college-football") else "&limit=200")


def resolve_event(p, events):
    from scripts.expert_audit_grading import norm
    identity = p.get("game_id") or ""
    explicit = re.search(r"-(\d{9})$", identity)
    if explicit:
        matches = [e for e in events if e["id"] == explicit[1]]
    else:
        parts = identity.split("-")
        def same(a, b):
            a, b = a.upper(), b.upper()
            return ABBR.get(a, a) == ABBR.get(b, b)
        matches = []
        for e in events:
            sides = {c["homeAway"]: c["team"]["abbreviation"] for c in e["competitions"][0]["competitors"]}
            if len(parts) >= 4 and same(sides.get("away", ""), parts[2]) and same(sides.get("home", ""), parts[3]):
                matches.append(e)
            elif not identity:
                names = re.split(r"\s+(?:@|at|vs\.?)\s+", p.get("game_title", ""), flags=re.I)
                if len(names) == 2 and all(
                    any(norm(n) in (norm(c["team"].get("location")), norm(c["team"].get("displayName"))) for c in e["competitions"][0]["competitors"])
                    for n in names
                ):
                    matches.append(e)
    if not matches and not explicit:
        names = re.split(r"\s+(?:@|at|vs\.?)\s+", p.get("game_title", ""), flags=re.I)
        if len(names) == 2:
            for e in events:
                cs = e["competitions"][0]["competitors"]
                if all(any(norm(n) in {norm(c["team"].get(k)) for k in ("displayName", "shortDisplayName", "location", "name")} for c in cs) for n in names):
                    matches.append(e)
    if len(matches) > 1:
        # Doubleheaders need the scheduled game, not just the two team names.
        close = [e for e in matches if abs((utc(e["date"]) - utc(p["game_time"])).total_seconds()) <= 300]
        if len(close) == 1:
            matches = close
    if len(matches) != 1:
        return None, "ambiguous/missing ESPN event"
    event = matches[0]
    if not event.get("status", {}).get("type", {}).get("completed"):
        return None, "ESPN event not final"
    return event, None


def collect(picks):
    pairs = sorted({(sport_path(p), date_key(p)) for p in picks if sport_path(p) and p.get("game_time")})
    def board(pair):
        path, day = pair
        try:
            return pair, get_json(scoreboard_url(path, day)).get("events", []), None
        except (requests.RequestException, ValueError) as exc:
            return pair, [], str(exc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        boards = list(pool.map(board, pairs))
    events = {key: value for key, value, error in boards}
    errors = [{"path": k[0], "date": k[1], "error": error} for k, _, error in boards if error]
    mapping, needed = {}, {}
    for p in picks:
        path = sport_path(p)
        if not path or p.get("is_future"):
            mapping[p["id"]] = (None, "future or unsupported sport")
            continue
        event, reason = resolve_event(p, events.get((path, date_key(p)), []))
        local_day = (utc(p["game_time"]) - timedelta(hours=4)).strftime("%Y%m%d")
        if not event and local_day != date_key(p):
            try:
                alternate = get_json(scoreboard_url(path, local_day)).get("events", [])
                event, reason = resolve_event(p, alternate)
            except (requests.RequestException, ValueError) as exc:
                errors.append({"path": path, "date": local_day, "error": str(exc)})
        mapping[p["id"]] = (event, reason)
        if event:
            needed[(path, event["id"])] = True
    def summary(key):
        path, event_id = key
        url = "https://site.api.espn.com/apis/site/v2/sports/" + path + "/summary?event=" + event_id
        try:
            return key, get_json(url), None
        except (requests.RequestException, ValueError) as exc:
            return key, {}, str(exc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        summaries = list(pool.map(summary, needed))
    for key, _, error in summaries:
        if error:
            errors.append({"path": key[0], "event": key[1], "error": error})
    return mapping, {key: value for key, value, _ in summaries}, errors, len(pairs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    source = json.loads((ROOT / "generated-artifacts/bettinginsider-other-experts-source.json").read_text())
    picks = sorted(source["picks"], key=lambda p: (utc(p.get("posted_at") or p["created_at"]).timestamp(), p["id"]))
    mapping, summaries, errors, board_count = collect(picks)
    print(json.dumps({"pick_count": len(picks), "scoreboards": board_count, "boxscores": len(summaries), "network_errors": errors}), flush=True)
    if args.collect_only:
        return
    from scripts.expert_audit_grading import grade_pick, summarize
    rows = []
    seen = {}
    for p in picks:
        event, reason = mapping.get(p["id"], (None, "no matching event"))
        summary = summaries.get((sport_path(p), event["id"]), {}) if event else {}
        row = grade_pick(p, event, summary, reason)
        key = (p["bettor_id"], row.get("espn_id") or p["game_id"], re.sub(r"\s+", " ", p["bet_title"].strip().lower()))
        if key in seen:
            row["duplicate_of"] = seen[key]
        else:
            seen[key] = p["id"]
        rows.append(row)
    result = {"window": source["window"], "experts": {name: summarize([r for r in rows if r["bettor_name"] == name]) for name in sorted({p["bettor_name"] for p in picks})}, "network_errors": errors, "picks": rows}
    out = ROOT / "generated-artifacts/bettinginsider-other-experts-audit.json"
    out.write_text(json.dumps(result, indent=2))
    write_report(result)
    print(json.dumps(result["experts"], indent=2), flush=True)
    print("Written:", out.relative_to(ROOT), flush=True)


def write_report(result):
    """Self-contained evidence table; no chart or third-party assets."""
    from scripts.expert_audit_grading import summarize
    esc = lambda value: html.escape(str(value if value is not None else ""))
    names = sorted(result["experts"])
    summary_rows = []
    for name in names:
        data = result["experts"][name]
        s = data["posted_before_espn_start"]
        summary_rows.append(
            f"<tr><td>{esc(name)}</td><td>{data['retrieved']}</td><td>{data['outcomes']['graded']}</td>"
            f"<td>{s['wins']}–{s['losses']}–{s['pushes']}</td><td>{s['profit']:+.2f}u</td>"
            f"<td>{s['flat_profit']:+.2f}u</td><td>{data['unresolved']}</td>"
            f"<td>{data['at_or_after_espn_start']}</td><td>{data['duplicates']}</td></tr>"
        )
    admitted_rows = []
    for name in ("Invisible Insider", "Insider Mike"):
        rows = [
            p for p in result["picks"] if p["bettor_name"] == name
            and p.get("posted_before_espn_start") and p.get("verified")
            and (
                (name == "Invisible Insider" and str(p["sport"]).upper() in ("NFL", "CFB", "NCAAF")
                 and p["bet_type"] in ("spread", "moneyline", "total") and not p.get("periods"))
                or (name == "Insider Mike" and str(p["sport"]).upper() == "MLB" and str(p["bet_type"]).lower() == "prop")
            )
        ]
        s = summarize(rows)["outcomes"]
        admitted_rows.append(
            f"<tr><td>{esc(name)}</td><td>{'Full-game NFL/NCAAF sides/totals/ML' if name == 'Invisible Insider' else 'Reviewed MLB player-prop families'}</td>"
            f"<td>{s['wins']}–{s['losses']}–{s['pushes']}</td><td>{s['profit']:+.2f}u</td>"
            f"<td>{s['roi_pct']:.2f}%</td><td>{s['flat_profit']:+.2f}u</td></tr>"
        )
    pick_rows = []
    for p in result["picks"]:
        label = p.get("verified") or "UNRESOLVED"
        if p.get("duplicate_of"):
            label += " · duplicate excluded"
        if p.get("result") == "pending":
            label += " · source pending excluded"
        timing = "Before ESPN start" if p.get("posted_before_espn_start") else "Not proven pregame" if p.get("verified") else "Unresolved"
        pick_rows.append(
            "<tr>" + "".join("<td>" + esc(v) + "</td>" for v in (
                p["bettor_name"], p["game_title"], p["bet_title"], p["odds"], p["units"],
                p["result"], label, p.get("actual"), p.get("line"), timing, p.get("issue"),
            )) + "<td>" + (f'<a href="{esc(p["espn_url"])}">ESPN box score</a>' if p.get("espn_url") else "No unique event") + "</td></tr>"
        )
    doc = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Betting Insider — remaining experts audit</title><style>
body{font:15px system-ui,sans-serif;color:#182438;max-width:1500px;margin:32px auto;padding:0 20px;line-height:1.5}
h1{font-size:28px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;font-size:13px}
td,th{padding:9px;border-bottom:1px solid #dbe2eb;text-align:left}th{background:#edf3f9}.scroll{overflow:auto}
.note{border-left:4px solid #1765ad;background:#edf4fb;padding:15px}a{color:#0759ac}</style>
<h1>The Betting Insider — remaining experts reviewed</h1><p>November 1, 2026. Review window: September 1–October 31, 2026.</p>
<div class="note"><strong>Decision:</strong> Add Invisible Insider's full-game football picks and Insider Mike's reviewed MLB prop families.
Do not admit their losing/unverified sport-market scopes. Skip Michael Wong on this evidence. Goodelleaks remains enabled under the earlier football audit.
This supersedes the initial one-expert admission decision.</div>
<h2>What was independently checked</h2>
<p>859 records from the three other experts were retrieved through 61 dated website-history requests, including losses and pushes.
Outcomes were reconciled with completed ESPN events and individual box-score statistics, not just final scores for props.
Quarter/half-game and first-inning/first-five-innings selections use period scores. Pitcher outs use baseball innings notation, not strikeouts.
Batter total bases use deduplicated terminal hit plays reconciled to box-score hits and home runs. Ambiguous identities, missing statistics,
DNP-like absent players, unclear multi-leg settlements and unfinished futures remain unresolved rather than being guessed.</p>
<h2>All-scope review and strict pregame cohort</h2>
<p>The pregame columns exclude source-pending records, duplicate recommendations and picks whose displayed publication time was at or after ESPN's scheduled start.
These are subset results, not a claim that every source record was independently verifiable.</p>
<div class="scroll"><table><thead><tr><th>Expert</th><th>Retrieved</th><th>Graded completed, deduplicated</th>
<th>Pregame W–L–P</th><th>Pregame units</th><th>Pregame flat 1u</th><th>Unresolved</th><th>At/after start</th><th>Duplicates</th></tr></thead><tbody>"""
    doc += "".join(summary_rows)
    doc += """</tbody></table></div><h2>Newly admitted scopes</h2><table><thead><tr><th>Expert</th><th>Scope</th>
<th>Verified pregame W–L–P</th><th>Published-unit profit</th><th>ROI</th><th>Flat 1u profit</th></tr></thead><tbody>"""
    doc += "".join(admitted_rows)
    doc += """</tbody></table><p>Insider Mike's NFL and college-football props were not admitted: the independently verified pregame samples lost money at his published stakes.
Invisible Insider's NFL props and college partial-game selections also lost money in their reviewed cohorts and were not admitted.
Small NBA/NHL/MLB subgroups are not treated as proof merely because some show a profit.</p>
<h2>Corrections and limits</h2><p>Two completed Insider Mike records disagreed with the displayed source grade:
Austin Hays Under 0.5 hits was graded a win on the site but the matched ESPN box score lists one hit; it is a loss at that displayed threshold.
A Yankees–Angels first-five-innings Under 4 was graded a loss on the site but the matched first five innings total one run; it is a win at the displayed threshold.
The admitted MLB prop record includes the corrected hit-prop loss. A source-pending NBA selection is excluded from performance and is not called a grading error.
Original-line and market-label inconsistencies may explain source-grade differences; the audit does not silently trust them.</p>
<p>ESPN verifies scores/statistics only. It does not independently establish the availability of historical prices, immutability of publication timestamps,
or completeness of the provider's history. Past subset profitability is not proof of future betting returns. Sport/market restrictions were chosen after reviewing
this window; they are not an independent out-of-sample validation and are not used to raise model probability or Lab stakes.</p>
<h2>Live connection</h2><p>The existing website endpoint <code>/api/picks/list?mode=all</code> supplies current pending selections, not the developer historical API.
Original lines, prices, books, units and publication times are preserved. The same five-minute cache and pregame/staleness filters apply.
Only games matching approved current picks are retained from <code>/api/games/upcoming</code>.
The game-line feed does not provide current player-prop quotes; no game spread is substituted for a prop line.
No additional odds board, scheduled ingestion job, subscription, login or scoring/staking boost was added.</p>
<h2>Pick-by-pick evidence</h2><div class="scroll"><table><thead><tr><th>Expert</th><th>Game</th><th>Original pick</th><th>American price</th>
<th>Expert units</th><th>Source result</th><th>Audit result</th><th>ESPN actual</th><th>Original threshold</th><th>Timing</th><th>Unresolved reason</th><th>Evidence</th></tr></thead><tbody>"""
    doc += "".join(pick_rows) + "</tbody></table></div></html>"
    (ROOT / "generated-artifacts/bettinginsider-other-experts-audit.html").write_text(doc)


if __name__ == "__main__":
    main()
