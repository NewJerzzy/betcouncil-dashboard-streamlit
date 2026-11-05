"""On-demand expert audit. Never runs in the dashboard or an ingestion job.

Input is the dated public pick history, including losses. ESPN responses are
cached under ignored generated-artifacts/ so grading can be inspected/repeated
without downloading every scoreboard and box score again.
"""

import argparse
import hashlib
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
    picks = source["picks"]
    mapping, summaries, errors, board_count = collect(picks)
    print(json.dumps({"pick_count": len(picks), "scoreboards": board_count, "boxscores": len(summaries), "network_errors": errors}), flush=True)
    if args.collect_only:
        return
    from scripts.expert_audit_grading import grade_pick, summarize
    rows = []
    for p in picks:
        event, reason = mapping.get(p["id"], (None, "no matching event"))
        summary = summaries.get((sport_path(p), event["id"]), {}) if event else {}
        rows.append(grade_pick(p, event, summary, reason))
    result = {"window": source["window"], "experts": {name: summarize([r for r in rows if r["bettor_name"] == name]) for name in sorted({p["bettor_name"] for p in picks})}, "network_errors": errors, "picks": rows}
    out = ROOT / "generated-artifacts/bettinginsider-other-experts-audit.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result["experts"], indent=2), flush=True)
    print("Written:", out.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
