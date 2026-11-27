import ast
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from demon_hit_analysis import assess_hits, rank_assessments, wilson_interval
from demon_hit_sources import assess_player, _logs_for_player
from demon_nfl_logs import parse_nfl_gamelog, fetch_nfl_logs


TODAY = date(2026, 11, 27)


def logs(values, **extra):
    return [{"date": (TODAY - timedelta(days=i + 1)).isoformat(),
             "pts": value, "min": "32:00", **extra} for i, value in enumerate(values)]


class HitAnalysisTests(unittest.TestCase):
    def score(self, values, line=10, **kwargs):
        return assess_hits(logs(values), line, "pts", as_of=TODAY,
                           opportunity_key="min", **kwargs)

    def test_whole_line_push_is_not_over_or_under_hit(self):
        over = self.score([9, 10, 11])
        under = self.score([9, 10, 11], side="UNDER")
        self.assertEqual((over["hits"], over["pushes"]), (1, 1))
        self.assertEqual((under["hits"], under["pushes"]), (1, 1))
        self.assertLess(over["prob"] + under["prob"], 1)

    def test_half_lines_have_no_push(self):
        result = self.score([9, 10, 11], line=9.5)
        self.assertEqual(result["hits"], 2)
        self.assertEqual(result["pushes"], 0)

    def test_higher_demon_line_cannot_improve_historical_probability(self):
        lower = self.score(range(30), line=10.5)
        higher = self.score(range(30), line=20.5)
        self.assertGreater(lower["prob"], higher["prob"])
        self.assertGreater(lower["lower"], higher["lower"])

    def test_zero_is_a_real_observation(self):
        result = self.score([0] * 25, line=0.5)
        self.assertEqual(result["n"], 25)
        self.assertEqual(result["hits"], 0)
        self.assertEqual(result["grade"], "PASS")

    def test_small_perfect_sample_is_not_strong(self):
        result = self.score([20] * 7)
        self.assertEqual(result["grade"], "INSUFFICIENT")
        self.assertIsNone(result["rank_score"])
        self.assertLess(result["prob"], 1)

    def test_twenty_stable_games_can_support_stronger_history(self):
        self.assertEqual(self.score([20] * 20)["grade"], "STRONGER HISTORY")

    def test_unknown_or_unstable_opportunity_blocks_strong_grade(self):
        rows = logs([20] * 30)
        rows[0].pop("min")
        result = assess_hits(rows, 10, "pts", as_of=TODAY, opportunity_key="min")
        self.assertEqual(result["grade"], "PROVISIONAL")
        rows = logs([20] * 30)
        for i, row in enumerate(rows):
            row["min"] = 10 if i % 2 else 40
        result = assess_hits(rows, 10, "pts", as_of=TODAY, opportunity_key="min")
        self.assertTrue(any("Unstable" in item for item in result["warnings"]))

    def test_recent_role_change_is_flagged(self):
        rows = logs([20] * 30)
        for row in rows[:5]:
            row["min"] = 23
        result = assess_hits(rows, 10, "pts", as_of=TODAY, opportunity_key="min")
        self.assertTrue(any("changed" in item for item in result["warnings"]))

    def test_recent_form_disagreement_is_flagged(self):
        self.assertTrue(any("Recent form" in item for item in
                            self.score([0] * 5 + [20] * 25)["warnings"]))

    def test_stale_history_cannot_rank(self):
        rows = logs([20] * 20)
        for i, row in enumerate(rows):
            row["date"] = (TODAY - timedelta(days=80 + i)).isoformat()
        result = assess_hits(rows, 10, "pts", as_of=TODAY, opportunity_key="min")
        self.assertIsNone(result["rank_score"])
        self.assertEqual(result["grade"], "PROVISIONAL")

    def test_undated_future_same_day_old_invalid_dnp_excluded(self):
        rows = logs([20])
        rows += [
            {"date": TODAY.isoformat(), "pts": 20},
            {"date": (TODAY + timedelta(days=1)).isoformat(), "pts": 20},
            {"date": (TODAY - timedelta(days=366)).isoformat(), "pts": 20},
            {"date": "not a date", "pts": 20},
            {"date": "2026-11-20", "pts": float("nan")},
            {"date": "2026-11-19", "pts": float("inf")},
            {"date": "2026-11-18", "pts": None},
            {"date": "2026-11-17", "pts": 0, "min": "0:00"},
        ]
        self.assertEqual(assess_hits(rows, 10, "pts", as_of=TODAY,
                                    opportunity_key="min")["n"], 1)

    def test_duplicates_excluded_doubleheaders_preserved(self):
        rows = logs([20])
        rows += [dict(rows[0]), {**rows[0], "game_id": "doubleheader-2"}]
        self.assertEqual(assess_hits(rows, 10, "pts", as_of=TODAY)["n"], 2)

    def test_newest_thirty_only(self):
        result = self.score([20] * 30 + [0] * 20)
        self.assertEqual((result["n"], result["hits"]), (30, 30))

    def test_empty_never_gets_fifty_percent_fallback(self):
        self.assertIsNone(self.score([])["prob"])
        self.assertEqual(self.score([])["grade"], "UNGRADED")

    def test_invalid_inputs_stay_ungraded(self):
        for line in (None, "invalid", float("nan"), float("inf")):
            self.assertIsNone(self.score([20] * 30, line=line)["prob"])
        self.assertIsNone(self.score([20], side="MORE")["prob"])

    def test_interval_widens_for_less_evidence(self):
        short = wilson_interval(8, 10)
        long = wilson_interval(24, 30)
        self.assertGreater(short[1] - short[0], long[1] - long[0])

    def test_probability_uses_jeffreys_smoothing_not_edge(self):
        self.assertAlmostEqual(self.score([20] * 10 + [0] * 10)["prob"], 0.5)
        self.assertFalse(self.score([20] * 30)["calibrated"])

    def test_rank_ignores_payout_and_edge(self):
        strong = {"player": "stable", "edge": 0, "payout": 1,
                  "hit_analysis": self.score([20] * 30)}
        weak = {"player": "high payout", "edge": 0.9, "payout": 100,
                "hit_analysis": self.score([0] * 30)}
        self.assertEqual(rank_assessments([weak, strong])[0]["player"], "stable")


class SourceTests(unittest.TestCase):
    def setUp(self):
        _logs_for_player.clear()
        original = assess_hits
        mock = patch("demon_hit_sources.assess_hits",
                     side_effect=lambda *a, **k: original(*a, as_of=TODAY, **k))
        mock.start()
        self.addCleanup(mock.stop)

    def test_nba_uses_real_log_keyword_not_sport_as_season(self):
        core = SimpleNamespace(fetch_player_game_logs=lambda player, **kwargs: (
            self.assertEqual(kwargs, {"last_n": 30}) or logs([20] * 25)))
        with patch("demon_hit_sources.date") as mocked_date:
            mocked_date.today.return_value = TODAY
            result = assess_player(core, "Player", "Points", 15.5, "NBA")
        self.assertEqual(result["n"], 25)

    def test_combo_does_not_impute_missing_component_as_zero(self):
        core = SimpleNamespace(fetch_player_game_logs=lambda *a, **k: logs([20] * 25))
        result = assess_player(core, "Player", "PTS+REB", 15.5, "NBA")
        self.assertIsNone(result["prob"])

    def test_pitcher_strikeouts_never_use_batter_strikeouts(self):
        result = assess_player(SimpleNamespace(), "Player", "Pitcher Strikeouts", 6.5, "MLB")
        self.assertIsNone(result["prob"])
        self.assertIn("no verified", result["warnings"][0])

    def test_unsupported_tennis_is_explicit(self):
        result = assess_player(SimpleNamespace(), "Player", "Total Games", 20.5, "Tennis")
        self.assertEqual(result["grade"], "UNGRADED")

    def test_fetch_failure_is_not_a_baseline(self):
        core = SimpleNamespace(fetch_player_game_logs=lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
        result = assess_player(core, "Player", "Points", 20.5, "NBA")
        self.assertIsNone(result["prob"])
        self.assertIn("TimeoutError", result["warnings"][0])

    def test_wnba_uppercase_normalization(self):
        rows = [{"date": r["date"], "PTS": 20, "MIN": 30} for r in logs([20] * 25)]
        core = SimpleNamespace(fetch_wnba_player_game_logs=lambda *a, **k: rows)
        result = assess_player(core, "Player", "Points", 15.5, "WNBA")
        self.assertEqual(result["n"], 25)

    def test_nfl_parser_maps_positional_values_and_excludes_preseason(self):
        category = {"categories": [{"events": [{"eventId": "a", "stats": ["250", "20"]}]}]}
        payload = {
            "names": ["passingYards", "rushingYards"],
            "events": {"a": {"gameDate": "2026-11-20", "gameResult": "W"}},
            "seasonTypes": [{"displayName": "2026 Preseason", **category},
                            {"displayName": "2026 Regular Season", **category}],
        }
        rows = parse_nfl_gamelog(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["passingYards"], 250)
        self.assertEqual(rows[0]["rushingYards"], 20)
        payload["events"]["a"].pop("gameResult")
        self.assertEqual(parse_nfl_gamelog(payload), [])

    def test_unknown_nfl_player_never_uses_first_search_result(self):
        core = SimpleNamespace(ESPN_ATHLETE_IDS={"NFL": {"Other Player": 123}},
                               fetch_nfl_full_player_database=lambda: {},
                               normalize_name=lambda x: x.lower())
        self.assertEqual(fetch_nfl_logs(core, "Unknown Player", TODAY.year), [])

    def test_paste_worker_passes_exact_line_and_bypasses_edge_engine(self):
        tree = ast.parse(Path("app.py").read_text())
        function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                        and node.name == "_analyze_one_board_prop")
        received = []
        namespace = {
            "_board_hit_mode": True, "_app_core_module": object(),
            "assess_demon_player": lambda *args: received.append(args) or {"n": 20},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        prop = {"player": "Player", "opponent": "Opponent", "line": 39.5,
                "stat": "Points", "matchup_type": "@"}
        row = namespace["_analyze_one_board_prop"](prop, "NBA", {}, {})
        self.assertEqual(received[0][3], 39.5)
        self.assertIn("hit_analysis", row)
        self.assertNotIn("edge_val", row)


class HitViewTests(unittest.TestCase):
    def test_loaded_demons_render_on_click_and_reject_stale_line_results(self):
        from streamlit.testing.v1 import AppTest
        script = """
import streamlit as st
from types import SimpleNamespace
from demon_hit_ui import render_loaded_demons
line = st.number_input("Line", value=20.5)
render_loaded_demons(SimpleNamespace(), [
    {"Player": "Player", "Prop": "Points", "Line": line, "Sport": "NBA", "OddsType": "demon"},
    {"Player": "Regular", "Prop": "Points", "Line": 10.5, "Sport": "NBA", "OddsType": "standard"}
])
"""
        result = assess_hits(logs([30] * 25), 20.5, "pts", as_of=TODAY,
                             opportunity_key="min")
        with patch("demon_hit_ui.assess_player", return_value=result) as scorer:
            app = AppTest.from_string(script, default_timeout=15).run()
            self.assertFalse(app.exception)
            app.button(key="grade_loaded_demon_hits").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(scorer.call_count, 1)
            self.assertEqual(list(app.dataframe[0].value["Player"]), ["Player"])
            self.assertEqual(app.dataframe[0].value["More than"].iloc[0], 20.5)
            self.assertIn("unvalidated", app.info[0].value)
            app.number_input[0].set_value(30.5).run()
            self.assertEqual(len(app.dataframe), 0)
            self.assertTrue(any("lines changed" in item.value for item in app.caption))

    def test_missing_logs_render_without_invented_probability(self):
        from streamlit.testing.v1 import AppTest
        script = """
from demon_hit_ui import render_hit_rows
from demon_hit_analysis import assess_hits
render_hit_rows([{"player": "Player", "sport": "NFL", "stat": "Pass Yards",
                 "line": 250.5, "hit_analysis": assess_hits([], 250.5, "passingYards")}])
"""
        app = AppTest.from_string(script, default_timeout=15).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value["Historical estimate"].iloc[0], "—")
        self.assertEqual(app.dataframe[0].value["Assessment"].iloc[0], "UNGRADED")


if __name__ == "__main__":
    unittest.main()
