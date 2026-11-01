import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from bettinginsider import (
    SOURCE, EXPERTS, fetch_public_snapshot, market_reference,
    normalize_pending_picks, prediction_items,
)


NOW = datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)


def sample_pick():
    return {
        "id": "one", "bettor_id": "analyst_goodelleaks", "bettor_name": "Goodelleaks",
        "result": "pending", "is_active": True, "is_future": False, "sport": "NFL",
        "bet_type": "moneyline", "bet_title": "New York Jets ML",
        "game_time": "2026-11-01T18:00:00Z", "posted_at": "2026-10-28T14:59:57Z",
        "game_title": "Raiders @ Jets", "game_id": "NFL-20261101-LV-NYJ",
        "odds": "-115", "units": 1.5, "sportsbook": "FanDuel",
    }


def game():
    return {
        "id": "NFL-20261101-LV-NYJ", "kickoff": "2026-11-01T18:00:00Z",
        "awayTeam": "Las Vegas Raiders", "homeTeam": "New York Jets",
        "awayTeamAbbr": "LV", "homeTeamAbbr": "NYJ",
        "spread": {"awayLine": 2.5, "homeLine": -2.5},
        "totals": {"number": 46.5}, "moneyline": {"away": 120, "home": -140},
    }


class BettingInsiderTests(unittest.TestCase):
    def test_mlb_ui_path_does_not_fetch_football_only_source(self):
        from pathlib import Path
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        source = Path("app.py").read_text()
        start = source.index("    # Reviewed experts, not another full odds/EV feed")
        end = source.index("    # ── GROUP game-line items by matchup", start)
        block = "\n".join(line[4:] for line in source[start:end].splitlines())
        script = (
            "import streamlit as st\n_pred_gl_items=[]\n"
            "_pred_sport_match=lambda sport: sport=='MLB'\n"
            + block + "\nst.session_state['observed']=_pred_gl_items\n"
        )
        item = {"sport": "MLB", "away": "Nationals", "home": "Padres",
                "source": "The Betting Insider — Insider Mike", "text": "C. Cavalli 6+ Ks (+110)"}
        st.cache_data.clear()
        with (
            patch("oddsassist.fetch_public_picks", side_effect=AssertionError("must not fetch NFL in MLB view")) as odds,
            patch("bettinginsider.fetch_public_snapshot", return_value={"market_errors": []}),
            patch("bettinginsider.prediction_items", return_value=[item]),
        ):
            app = AppTest.from_string(script).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.warning), 0)
        self.assertEqual(app.session_state["observed"], [item])
        odds.assert_not_called()

    def test_experts_are_admitted_by_verified_scope_not_globally(self):
        def expert_pick(name, **changes):
            identity = next(k for k, v in EXPERTS.items() if v[0] == name)
            return {**sample_pick(), "id": name, "bettor_id": identity, "bettor_name": name, **changes}
        invisible = expert_pick("Invisible Insider")
        mike = expert_pick(
            "Insider Mike", sport="MLB", bet_type="prop",
            bet_title="C. Cavalli 6+ Ks", game_id="MLB-20261101-WSH-SD",
            game_title="Nationals @ Padres",
        )
        accepted = normalize_pending_picks({"picks": [sample_pick(), invisible, mike]})
        self.assertEqual(len(accepted), 3)
        self.assertEqual(accepted[-1]["prop_market"], "pitching_strikeouts")
        denied = [
            expert_pick("Insider Mike", bet_type="prop", bet_title="R. Dowdle Rush Yards Over 25.5"),
            expert_pick("Insider Mike", sport="NBA", bet_type="prop", bet_title="Player Over 20.5 Points"),
            expert_pick("Invisible Insider", bet_type="prop", bet_title="T. Higgins O70.5 Rec Yds"),
            expert_pick("Invisible Insider", bet_type="total", bet_title="Under 24.5 · TT Under"),
            expert_pick("Invisible Insider", bet_type="total", bet_title="1st quarter Under 10.5"),
            expert_pick("Michael Wong") if any(v[0] == "Michael Wong" for v in EXPERTS.values())
            else {**sample_pick(), "bettor_id": "analyst_michael_wong"},
            {**mike, "bet_title": "C. Cavalli First inning Ks Over 0.5"},
            {**mike, "bet_title": "C. Cavalli Ks Over 5.5 + Padres ML"},
            {**mike, "bet_title": "Player Home Runs Over 0.5"},
        ]
        self.assertEqual(normalize_pending_picks({"picks": denied}), [])

    def test_malformed_expert_pick_does_not_hide_other_experts(self):
        errors = []
        bad = {**sample_pick(), "id": "bad", "odds": "invalid"}
        picks = normalize_pending_picks({"picks": [bad, sample_pick()]}, errors=errors)
        self.assertEqual(len(picks), 1)
        self.assertEqual(len(errors), 1)

    def test_player_prop_keeps_original_line_without_using_game_spread(self):
        p = {**normalize_pending_picks({"picks": [sample_pick()]})[0], "market": "prop"}
        self.assertIn("not supplied", market_reference(p, game()))
        self.assertIn("not supplied", market_reference(p, None))

    def test_only_reviewed_expert_and_markets(self):
        picks = []
        for mutation in ("other_expert", "prop", "future", "graded", "inactive", "partial"):
            p = sample_pick()
            if mutation == "other_expert":
                p["bettor_id"] = "someone_else"
            elif mutation == "prop":
                p["bet_type"] = "prop"
            elif mutation == "future":
                p["is_future"] = True
            elif mutation == "graded":
                p["result"] = "win"
            elif mutation == "inactive":
                p["is_active"] = False
            else:
                p.update(bet_type="total", bet_title="1H Under 22.5")
            picks.append(p)
        self.assertEqual(normalize_pending_picks({"picks": picks}), [])

    def test_original_pick_and_current_market_are_separate(self):
        p = normalize_pending_picks({"picks": [sample_pick()]})[0]
        self.assertEqual(p["source"], SOURCE)
        self.assertEqual(p["american_odds"], -115)
        self.assertEqual(market_reference(p, game()), "Current consensus NYJ ML -140")
        self.assertEqual(p["american_odds"], -115)
        p.update(market="spread", selection="New York Jets -1")
        self.assertEqual(
            market_reference(p, game()), "Current consensus NYJ -2.5 (price not supplied)"
        )
        p.update(market="total", selection="Under 44.5")
        self.assertIn("total 46.5", market_reference(p, game()))
        p["market"] = "team_total"
        self.assertEqual(market_reference(p, game()), "Current team total unavailable")

    def test_mismatched_kickoff_and_missing_market_not_fabricated(self):
        p = normalize_pending_picks({"picks": [sample_pick()]})[0]
        self.assertEqual(market_reference(p, None), "Current market unavailable")
        g = game()
        g["kickoff"] = "2026-11-08T18:00:00Z"
        self.assertEqual(market_reference(p, g), "Current market unavailable")

    def test_dedup_and_reject_malformed_pending_record(self):
        p = sample_pick()
        self.assertEqual(len(normalize_pending_picks({"picks": [p, copy.deepcopy(p)]})), 1)
        for field, value in (("odds", "nan"), ("units", -1), ("game_id", ""), ("game_title", "Unknown")):
            bad = {**p, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_pending_picks({"picks": [bad]})

    def test_render_time_pregame_and_freshness_gates(self):
        snapshot = {
            "picks": normalize_pending_picks({"picks": [sample_pick()]}),
            "markets": {game()["id"]: game()}, "fetched_at": NOW.isoformat(),
        }
        items = prediction_items(snapshot, now=NOW)
        self.assertEqual(len(items), 1)
        self.assertIn("published at FanDuel", items[0]["text"])
        self.assertIn("Current consensus NYJ ML -140", items[0]["text"])
        self.assertIn("not an executable book quote", items[0]["text"])
        snapshot["fetched_at"] = "2026-11-01T17:59:00Z"
        self.assertEqual(
            prediction_items(snapshot, now=datetime(2026, 11, 1, 18, tzinfo=timezone.utc)), []
        )
        snapshot["fetched_at"] = "2026-11-01T15:00:00Z"
        with self.assertRaises(ValueError):
            prediction_items(snapshot, now=NOW)

    def test_market_failure_retains_original_pick_with_explicit_error(self):
        with (
            patch("bettinginsider.datetime", wraps=datetime) as clock,
            patch("bettinginsider._get_json", side_effect=[
                {"success": True, "picks": [sample_pick()]}, ValueError("market unavailable"),
            ]),
        ):
            clock.now.return_value = NOW
            snapshot = fetch_public_snapshot()
        self.assertEqual(len(snapshot["picks"]), 1)
        self.assertEqual(snapshot["markets"], {})
        self.assertEqual(snapshot["market_errors"], ["NFL: ValueError"])

    def test_only_matching_games_retained_and_no_extra_calls(self):
        other = {**game(), "id": "other"}
        with (
            patch("bettinginsider.datetime", wraps=datetime) as clock,
            patch("bettinginsider._get_json", side_effect=[
                {"success": True, "picks": [sample_pick()]},
                {"success": True, "games": [game(), other]},
            ]) as fetch,
        ):
            clock.now.return_value = NOW
            snapshot = fetch_public_snapshot()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(list(snapshot["markets"]), [game()["id"]])


if __name__ == "__main__":
    unittest.main()
