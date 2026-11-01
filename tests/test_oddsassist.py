import copy
from pathlib import Path
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from oddsassist import (
    SOURCE, decode_page_data, fetch_public_picks,
    normalize_pending_picks, prediction_items,
)


NOW = datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)


def sample_pick():
    return {
        "id": 516, "result": None, "units": 2,
        "createdAt": "2026-11-01T15:44:25Z",
        "user": {"name": "Rob O'Connor"},
        "legs": [{
            "marketType": "POINT_SPREAD", "marketSegment": "FULL_MATCH",
            "type": "WIN", "participantKey": "nyj", "modifier": -1,
            "payout": 1.86956521739,
            "event": {
                "key": "lv-nyj", "type": "MATCH",
                "startTime": "2026-11-01T18:00:00Z",
                "homeParticipantKey": "nyj",
                "participants": [
                    {"key": "lv", "name": "Las Vegas Raiders"},
                    {"key": "nyj", "name": "New York Jets"},
                ],
                "competitionInstance": {"competition": {"shortName": "NFL"}},
            },
        }],
    }


def page(picks):
    return {"routes/_main.picks": {"data": {"picks": picks}}}


class OddsAssistTests(unittest.TestCase):
    def test_reference_decoder_and_date(self):
        self.assertEqual(
            decode_page_data('[{"_1":2,"_3":4,"_5":-5},"x",["D",0],"n",2,"null"]'),
            {"x": "1970-01-01T00:00:00+00:00", "n": 2, "null": None},
        )

    def test_decoder_rejects_script_and_invalid_references(self):
        for value in ('alert("no")', '[{"_1":99},"x"]', '[{"_99":1},"x"]'):
            with self.subTest(value=value), self.assertRaises((ValueError, IndexError)):
                decode_page_data(value)

    def test_original_selection_not_changed_by_current_market(self):
        p = sample_pick()
        p["legs"][0]["event"]["markets"] = [
            {"outcomes": [{"modifier": -1.5, "payout": 1.96}]},
        ]
        result = normalize_pending_picks(page([p, copy.deepcopy(p)]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["line"], -1)
        self.assertEqual(result[0]["source"], SOURCE)
        self.assertEqual(result[0]["decimal_odds"], 1.86956521739)
        self.assertNotIn("bookmaker", result[0])
        self.assertNotIn("confidence", result[0])

    def test_game_filters(self):
        base = sample_pick()
        candidates = []
        for mutation in ("graded", "futures", "other_expert", "prop", "period", "parlay"):
            p = copy.deepcopy(base)
            if mutation == "graded":
                p["result"] = "WIN"
            elif mutation == "futures":
                p["legs"][0]["event"]["type"] = "COMPETITION"
            elif mutation == "other_expert":
                p["user"]["name"] = "Unreviewed"
            elif mutation == "prop":
                p["legs"][0]["marketType"] = "PLAYER_PASSING_YARDS"
            elif mutation == "period":
                p["legs"][0]["marketSegment"] = "FIRST_HALF"
            else:
                p["legs"].append(copy.deepcopy(p["legs"][0]))
            candidates.append(p)
        self.assertEqual(normalize_pending_picks(page(candidates)), [])

    def test_totals_moneyline_and_college_football(self):
        p = sample_pick()
        leg = p["legs"][0]
        leg.update(marketType="POINT_TOTAL", type="UNDER", modifier=46, participantKey="")
        leg["event"]["competitionInstance"]["competition"]["shortName"] = "NCAAF"
        result = normalize_pending_picks(page([p]))[0]
        self.assertEqual(result["selection"], "Under 46")
        self.assertEqual(result["sport"], "NCAAF")
        leg.update(marketType="MONEYLINE", type="WIN", modifier=None, participantKey="nyj")
        self.assertEqual(normalize_pending_picks(page([p]))[0]["selection"], "New York Jets ML")

    def test_bad_pending_data_fails_explicitly(self):
        for field, value in (("payout", 1), ("payout", float("nan")), ("units", 0), ("modifier", None)):
            p = sample_pick()
            if field == "units":
                p[field] = value
            else:
                p["legs"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                normalize_pending_picks(page([p]))
        with self.assertRaises(ValueError):
            normalize_pending_picks({})

    def test_pregame_rechecked_on_cache_hit_and_staleness(self):
        snapshot = {
            "picks": normalize_pending_picks(page([sample_pick()])),
            "fetched_at": NOW.isoformat(),
        }
        result = prediction_items(snapshot, now=NOW)
        self.assertEqual(len(result), 1)
        self.assertIn("-115, published price", result[0]["text"])
        self.assertIn("2u expert stake", result[0]["text"])
        self.assertIn("not a current sportsbook quote", result[0]["text"])
        snapshot["fetched_at"] = "2026-11-01T17:59:00Z"
        kickoff = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(prediction_items(snapshot, now=kickoff), [])
        snapshot["fetched_at"] = "2026-11-01T15:00:00Z"
        with self.assertRaises(ValueError):
            prediction_items(snapshot, now=NOW)

    def test_publication_and_horizon(self):
        p = sample_pick()
        p["createdAt"] = "2026-11-01T18:00:00Z"
        with self.assertRaises(ValueError):
            normalize_pending_picks(page([p]))
        p["createdAt"] = "2026-11-01T17:00:00Z"
        snapshot = {"picks": normalize_pending_picks(page([p])), "fetched_at": NOW.isoformat()}
        self.assertEqual(prediction_items(snapshot, now=NOW), [])
        p["createdAt"] = "2026-11-01T15:00:00Z"
        p["legs"][0]["event"]["startTime"] = "2026-11-20T18:00:00Z"
        snapshot["picks"] = normalize_pending_picks(page([p]))
        self.assertEqual(prediction_items(snapshot, now=NOW), [])

    def test_network_errors_not_disguised_as_empty_feed(self):
        with patch("oddsassist.requests.get", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                fetch_public_picks()

    def test_actual_predictions_integration_shows_named_expert_and_failure(self):
        from streamlit.testing.v1 import AppTest

        app_source = Path("app.py").read_text()
        start = app_source.index('    # Reviewed experts, not another full odds/EV feed')
        end = app_source.index('    # ── GROUP game-line items by matchup', start)
        block = "\n".join(line[4:] for line in app_source[start:end].splitlines())
        script = (
            "import streamlit as st\n"
            "_pred_gl_items = []\n"
            "def _pred_sport_match(s): return s == 'NFL'\n"
            + block
            + "\nst.session_state['observed'] = _pred_gl_items\n"
        )
        snapshot = {
            "picks": normalize_pending_picks(page([sample_pick()])),
            "fetched_at": NOW.isoformat(),
        }
        actual_items = prediction_items
        tbi_item = {
            "sport": "NFL", "away": "Ravens", "home": "Bills",
            "source": "The Betting Insider — Goodelleaks",
            "text": "Baltimore +3.5 published; current consensus +3",
        }
        with (
            patch("oddsassist.fetch_public_picks", return_value=snapshot),
            patch("oddsassist.prediction_items", side_effect=lambda s: actual_items(s, now=NOW)),
            patch("bettinginsider.fetch_public_snapshot", return_value={"market_errors": []}),
            patch("bettinginsider.prediction_items", return_value=[tbi_item]),
        ):
            app = AppTest.from_string(script).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.session_state["observed"]), 2)
            item = app.session_state["observed"][0]
            self.assertEqual(item["source"], SOURCE)
            self.assertIn("published price", item["text"])
            self.assertNotIn("model_probability", item)
            self.assertNotIn("stake_adjustment", item)
            self.assertEqual(
                app.session_state["observed"][1]["source"], tbi_item["source"]
            )
        # Clear the function cache before simulating a failed upstream request.
        import streamlit as st
        st.cache_data.clear()
        with (
            patch("oddsassist.fetch_public_picks", side_effect=RuntimeError("offline")),
            patch("bettinginsider.fetch_public_snapshot", side_effect=RuntimeError("offline")),
        ):
            failed = AppTest.from_string(script).run()
            self.assertEqual(len(failed.exception), 0)
            self.assertEqual(failed.session_state["observed"], [])
            self.assertIn("unavailable", failed.warning[0].value)


if __name__ == "__main__":
    unittest.main()
