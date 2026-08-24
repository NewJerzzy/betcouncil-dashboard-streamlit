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


# ── Action Network public betting ──────────────────────────────────────
# Honest note, unlike the fixtures above: these are NOT captured from a
# live raw response (no direct API access from this environment). Built
# from confirmed field paths and example values from an external live
# audit (58% tickets / 93% money on a real active MLB spread market,
# game["markets"][book_id]["event"][market_type][n]["bet_info"]) --
# structurally accurate to the confirmed real schema, not a raw capture.

class _FakeResp:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


def _an_active_market_response():
    """One game with real ticket/money data under `markets` (not `odds`),
    matching the confirmed live schema."""
    return {
        "games": [
            {
                "teams": [{"abbr": "NYY"}, {"abbr": "BOS"}],
                "num_bets": 4200,
                "markets": {
                    "15": {
                        "event": {
                            "moneyline": [
                                {"side": "home", "odds": -150,
                                 "bet_info": {"tickets": {"percent": 42}, "money": {"percent": 60}}},
                                {"side": "away", "odds": 130,
                                 "bet_info": {"tickets": {"percent": 58}, "money": {"percent": 40}}},
                            ],
                            "spread": [
                                {"side": "home", "value": -1.5, "odds": -110,
                                 "bet_info": {"tickets": {"percent": 42}, "money": {"percent": 93}}},
                                {"side": "away", "value": 1.5, "odds": -110,
                                 "bet_info": {"tickets": {"percent": 58}, "money": {"percent": 7}}},
                            ],
                            "total": [
                                {"side": "over", "value": 8.5, "odds": -110,
                                 "bet_info": {"tickets": {"percent": 55}, "money": {"percent": 50}}},
                                {"side": "under", "value": 8.5, "odds": -110,
                                 "bet_info": {"tickets": {"percent": 45}, "money": {"percent": 50}}},
                            ],
                        }
                    }
                },
            }
        ]
    }


def test_action_network_public_betting_reads_markets_field():
    """Regression test for the confirmed real bug: the parser was reading
    `game["odds"]`, but the live response nests this data under
    `game["markets"]` instead -- same shape, different top-level key."""
    from unittest.mock import patch
    import fetchers
    resp = _FakeResp(200, _an_active_market_response())
    with patch.object(fetchers._http, "get", return_value=resp), \
         patch.object(fetchers, "api_budget_increment", lambda *a, **k: None):
        result = fetchers._fetch_public_betting_for_date("MLB", "mlb", "20260823", {})
    assert result, "parser produced nothing from a real-shaped active market response"
    game = next(iter(result.values()))
    assert game["spread"]["home"]["tickets"] == 42
    assert game["spread"]["home"]["money"] == 93, \
        "money% not read correctly from bet_info under markets"
    assert game["spread"]["away"]["tickets"] == 58


def test_action_network_nfl_empty_markets_produces_no_false_signal():
    """NFL preseason games can legitimately have zero published markets.
    Confirmed requirement: this must be skipped entirely, never treated
    as a real 0%/0% record that could feed a false RLM signal."""
    from unittest.mock import patch
    import fetchers
    empty_markets_response = {
        "games": [
            {"teams": [{"abbr": "KC"}, {"abbr": "SF"}], "num_bets": 0, "markets": {}}
        ]
    }
    resp = _FakeResp(200, empty_markets_response)
    with patch.object(fetchers._http, "get", return_value=resp), \
         patch.object(fetchers, "api_budget_increment", lambda *a, **k: None):
        result = fetchers._fetch_public_betting_for_date("NFL", "nfl", "20260823", {})
    assert result == {}, \
        "a game with empty markets produced a record -- risk of a fabricated 0% signal downstream"


def test_action_network_http_400_returns_empty_not_raises():
    """Confirmed real failure mode: the sport-suffixed route can return
    HTTP 400 INVALID_DATA. Must fail closed (empty dict), never raise
    and break the caller's loop over multiple sports/dates."""
    from unittest.mock import patch
    import fetchers
    resp = _FakeResp(400, text='{"error":"INVALID_DATA"}')
    with patch.object(fetchers._http, "get", return_value=resp), \
         patch.object(fetchers, "api_budget_increment", lambda *a, **k: None):
        result = fetchers._fetch_public_betting_for_date("NFL", "nfl", "20260823", {})
    assert result == {}, "a 400 response should fail closed to an empty dict, not raise or partially populate"


def test_action_network_missing_bet_info_defaults_safely():
    """An outcome missing bet_info entirely (partial/malformed row) must
    default to 0, not raise -- confirmed via the existing .get(...,{}) chain,
    tested explicitly here so a future refactor can't silently drop it."""
    from unittest.mock import patch
    import fetchers
    malformed = {
        "games": [{
            "teams": [{"abbr": "LAD"}, {"abbr": "SD"}],
            "num_bets": 100,
            "markets": {"15": {"event": {
                "moneyline": [{"side": "home", "odds": -120}],  # no bet_info key at all
                "spread": [], "total": [],
            }}},
        }]
    }
    resp = _FakeResp(200, malformed)
    with patch.object(fetchers._http, "get", return_value=resp), \
         patch.object(fetchers, "api_budget_increment", lambda *a, **k: None):
        result = fetchers._fetch_public_betting_for_date("MLB", "mlb", "20260823", {})
    assert result, "should still produce a record even with one outcome missing bet_info"
    game = next(iter(result.values()))
    assert game["ml"]["home"]["tickets"] == 0
    assert game["ml"]["home"]["money"] == 0
