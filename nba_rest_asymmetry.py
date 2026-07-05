"""
nba_rest_asymmetry.py — Rest advantage asymmetry (not just B2B binary).

Pure logic on schedule data already fetched by nba_b2b_classifier.py
(fetch_team_recent_games). No new data source. Complements the B2B
subtype classifier: that module covers back-to-backs specifically, this
module covers the general rest-differential spectrum, including the
"too much rest = rust" case a simple rested-vs-tired flag misses.

Public API
----------
rest_days_before_game(team_games: list, game_date=None) -> int
    Days since the team's last game, as of game_date (defaults to next
    day after last entry).

classify_rest_asymmetry(home_games, away_games, game_date=None) -> dict
    {home_rest_days, away_rest_days, differential, point_adjustment,
     favored_side, note}
"""
from datetime import datetime, timedelta

# Point adjustments are directional magnitudes (favor the better-rested
# team), not literally validated coefficients — flagged as approximate,
# matching the documented direction (rest matters, but plateaus, and too
# much rest can mean rust) rather than treated as exact ground truth.
_REST_DIFF_ADJUSTMENTS = {
    0: 0.0,
    1: 0.5,
    2: 1.0,
    3: 1.5,   # mini-bye
}
_MAX_DIFF_ADJUSTMENT = 2.5  # 4+ days rest advantage caps out here

# A team with 4+ days off can come out rusty rather than sharp — small
# negative adjustment applied on TOP of the rest-advantage credit, net
# effect: still favored, but by less than a naive "more rest = better"
# model would suggest.
_RUST_THRESHOLD_DAYS = 4
_RUST_PENALTY = -0.5


def _parse_date(d):
    if isinstance(d, datetime):
        return d
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(d)[:19], fmt)
        except ValueError:
            continue
    return None


def rest_days_before_game(team_games: list, game_date=None) -> int:
    """
    Days of rest a team has going into game_date, based on the date of
    their most recent prior game in team_games (chronological list of
    {date, is_home} — same shape as nba_b2b_classifier.fetch_team_recent_games).
    """
    dated = [g for g in team_games if _parse_date(g.get("date")) is not None]
    if not dated:
        return None
    dated.sort(key=lambda g: _parse_date(g["date"]))
    last_game_date = _parse_date(dated[-1]["date"])

    ref_date = _parse_date(game_date) if game_date else last_game_date + timedelta(days=1)
    return (ref_date - last_game_date).days - 1  # days of rest = gap - 1


def classify_rest_asymmetry(home_games: list, away_games: list, game_date=None) -> dict:
    """
    Compare rest days between the two teams in an upcoming matchup and
    return a point-adjustment favoring the better-rested side, with a
    rust penalty applied if a team has 4+ days off.
    """
    home_rest = rest_days_before_game(home_games, game_date)
    away_rest = rest_days_before_game(away_games, game_date)
    if home_rest is None or away_rest is None:
        return {}

    diff = home_rest - away_rest  # positive = home team more rested
    favored_side = "HOME" if diff > 0 else "AWAY" if diff < 0 else None
    abs_diff = min(abs(diff), 4)
    adjustment = _REST_DIFF_ADJUSTMENTS.get(abs_diff, _MAX_DIFF_ADJUSTMENT)

    # Apply rust penalty to whichever side has 4+ days off, reducing (not
    # flipping) their rest-advantage credit.
    rust_note = ""
    if favored_side == "HOME" and home_rest >= _RUST_THRESHOLD_DAYS:
        adjustment = max(adjustment + _RUST_PENALTY, 0.0)
        rust_note = " (rust factor applied — 4+ days off)"
    elif favored_side == "AWAY" and away_rest >= _RUST_THRESHOLD_DAYS:
        adjustment = max(adjustment + _RUST_PENALTY, 0.0)
        rust_note = " (rust factor applied — 4+ days off)"

    return {
        "home_rest_days": home_rest,
        "away_rest_days": away_rest,
        "differential": diff,
        "point_adjustment": round(adjustment, 2),
        "favored_side": favored_side,
        "note": (
            f"{favored_side} rested {abs(diff)} day(s) more{rust_note}"
            if favored_side else "Equal rest — no adjustment"
        ),
    }
