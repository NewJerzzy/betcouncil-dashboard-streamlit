"""
Parser regression tests -- real captured API response shapes, not invented
ones. Added 2026-07-26 after three separate live incidents this session
where a parser silently mismatched the real shape and only surfaced once
deployed: Signal Odds' first "successful" run pushed null fields (nested
under `event`, not flat), Kalshi's field names had to be found via live
trial and error, and PrizePicks' JSON:API nesting needed exact unwrapping.

Each fixture in tests/fixtures/ is trimmed from a real response captured
live during this session (not hand-invented), so a parser passing these
tests means it handles the real shape, not an idealized one. Run with:
    pip install pytest --break-system-packages
    pytest tests/test_parsers.py -v
"""

import json
import os
import sys

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))


def _load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name)) as f:
        return json.load(f)


# ── PrizePicks ──────────────────────────────────────────────────────────

def test_prizepicks_parser_handles_real_shape():
    from fetchers import _parse_prizepicks_harvested
    fixture = _load_fixture("prizepicks_sample.json")
    raw = fixture["data"]  # matches caller's `raw = data.get("data", {})`
    props = _parse_prizepicks_harvested(raw, "MLB")
    assert len(props) > 0, "parser produced zero props from a real captured sample -- shape mismatch"
    for p in props:
        assert p.get("Player"), "a prop was parsed with no player name"
        assert p.get("Prop"), "a prop was parsed with no stat type"
        assert p.get("Line") is not None, "a prop was parsed with no line"
    # Real names must resolve from `included`, not fall back to a team code
    assert any(len(p["Player"].split()) >= 2 for p in props), \
        "no prop resolved a real multi-word player name -- likely fell back to a team abbreviation"


# ── Kalshi ──────────────────────────────────────────────────────────────

def test_kalshi_market_normalizer_handles_real_shape():
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    import kalshi_refresh
    fixture = _load_fixture("kalshi_sample.json")
    event = fixture["events"][0]
    normalized = kalshi_refresh._normalize_event(event, "MLB")
    assert normalized["title"], "title (matchup name) missing after normalization"
    assert normalized["event_ticker"], "event_ticker missing"
    assert len(normalized["markets"]) == len(event["markets"])
    for m in normalized["markets"]:
        assert m["ticker"], "a normalized market lost its ticker"
        assert m["title"], "a normalized market lost its title"


# ── Signal Odds ───────────────────────────────────────────────────────────

def test_signalodds_prediction_normalizer_handles_real_nested_shape():
    """Regression test for the exact bug hit live 2026-07-25: first
    'successful' run pushed null fields because team/time/league sit
    under a nested `event` object, not flat on the row."""
    import signalodds_refresh
    fixture = _load_fixture("signalodds_predictions_sample.json")
    row = fixture["data"]["items"][0]
    normalized = signalodds_refresh._normalize_prediction(row)
    assert normalized["home_team"], "home_team is null -- event nesting not unwrapped correctly"
    assert normalized["away_team"], "away_team is null -- event nesting not unwrapped correctly"
    assert normalized["commence_time"], "commence_time is null"
    assert normalized["confidence_pct"] is not None
    assert normalized["model_name"], "model name lost"


def test_signalodds_arbitrage_normalizer_handles_real_nested_shape():
    import signalodds_refresh
    fixture = _load_fixture("signalodds_arbitrage_sample.json")
    row = fixture["data"]["items"][0]
    normalized = signalodds_refresh._normalize_opportunity(row)
    assert normalized["home_team"], "home_team is null"
    assert normalized["margin_percent"] is not None
    assert len(normalized["legs"]) == 2, "arbitrage legs (per-bookmaker outcomes) lost in normalization"
    for leg in normalized["legs"]:
        assert leg["bookmaker"], "a leg lost its bookmaker name"
        assert leg["odds"] is not None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
