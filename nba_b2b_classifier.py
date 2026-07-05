"""
nba_b2b_classifier.py — B2B subtype classification (pure schedule logic).

Replaces the existing binary back_to_back flag with the correct subtype,
using only game location history you already have (home/away per date).
No new data source.

Public API
----------
classify_b2b(team_games: list) -> dict
    team_games: chronological list of {date, is_home} for a team's last
    ~5 games (already available from schedule/game-log data).
    Returns {subtype, point_adjustment, note} or {} if not on a B2B.
"""
from datetime import datetime

# Point adjustments are directional magnitudes to SUBTRACT from a team's
# expected performance, not literal validated coefficients — flagged as
# approximate, consistent with the well-documented direction (B2Bs hurt
# performance, road-heavy B2Bs hurt more) rather than DeepSeek's precise
# unsourced numbers.
_B2B_ADJUSTMENTS = {
    "HOME_HOME": -0.5,
    "ROAD_ROAD": -2.0,
    "ROAD_HOME": -1.5,   # traveled between games
    "HOME_ROAD": -2.5,   # worst case: travel + no rest
    "3_IN_4": -3.0,
    "4_IN_5": -4.5,
}


def _parse_date(d):
    if isinstance(d, datetime):
        return d
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(d)[:19], fmt)
        except ValueError:
            continue
    return None


def classify_b2b(team_games: list) -> dict:
    """
    team_games: chronological list of dicts, most recent last, e.g.
        [{"date": "2026-01-05", "is_home": True}, {"date": "2026-01-06", "is_home": False}, ...]
    Only the last 5 entries are used (today's game should be included last
    if already scheduled, or omitted if classifying pre-game).
    """
    games = [g for g in team_games if _parse_date(g.get("date")) is not None]
    games.sort(key=lambda g: _parse_date(g["date"]))
    if len(games) < 2:
        return {}

    last = games[-1]
    prev = games[-2]
    last_dt, prev_dt = _parse_date(last["date"]), _parse_date(prev["date"])
    gap_days = (last_dt - prev_dt).days

    if gap_days != 1:
        return {}  # not a true back-to-back

    # Density check first: 3-in-4 / 4-in-5 supersede the simple pair classification
    if len(games) >= 4:
        span4 = (last_dt - _parse_date(games[-4]["date"])).days
        if span4 <= 4:
            return {
                "subtype": "3_IN_4",
                "point_adjustment": _B2B_ADJUSTMENTS["3_IN_4"],
                "note": "3 games in 4 nights — strong fade",
            }
    if len(games) >= 5:
        span5 = (last_dt - _parse_date(games[-5]["date"])).days
        if span5 <= 5:
            return {
                "subtype": "4_IN_5",
                "point_adjustment": _B2B_ADJUSTMENTS["4_IN_5"],
                "note": "4 games in 5 nights — severe fade",
            }

    prev_home, last_home = bool(prev.get("is_home")), bool(last.get("is_home"))
    if prev_home and last_home:
        subtype = "HOME_HOME"
    elif not prev_home and not last_home:
        subtype = "ROAD_ROAD"
    elif not prev_home and last_home:
        subtype = "ROAD_HOME"
    else:
        subtype = "HOME_ROAD"

    return {
        "subtype": subtype,
        "point_adjustment": _B2B_ADJUSTMENTS[subtype],
        "note": subtype.replace("_", "→").title() + " back-to-back",
    }
