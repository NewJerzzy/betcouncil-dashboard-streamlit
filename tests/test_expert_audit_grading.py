import unittest

from scripts.expert_audit_grading import (
    grade_pick, identify_player, number, player_value, summarize,
)


class ExpertAuditGradingTests(unittest.TestCase):
    def test_signed_american_prices_and_pitcher_outs_are_not_strikeouts(self):
        self.assertEqual(number("+110"), 110)
        player = {"groups": {"pitching": {
            "strikeouts": "3", "fullInnings.partInnings": "5.2", "walks": "2",
        }}}
        self.assertEqual(player_value("M. Scherzer Strikeouts U4.5", player, "1", {}, "MLB"), (3, "pitching_strikeouts"))
        self.assertEqual(player_value("M. Scherzer Pitcher Outs O16.5", player, "1", {}, "MLB"), (17, "pitcher_outs"))
        self.assertEqual(player_value("M. Scherzer Walks Over 1.5", player, "1", {}, "MLB"), (2, "pitching_walks"))

    def test_ambiguous_player_names_and_missing_stats_are_not_guessed(self):
        pool = {
            "1": {"athlete": {"displayName": "Brian Robinson", "firstName": "Brian", "lastName": "Robinson"}},
            "2": {"athlete": {"displayName": "Bijan Robinson", "firstName": "Bijan", "lastName": "Robinson"}},
        }
        with self.assertRaises(ValueError):
            identify_player("B. Robinson O50.5 Rush Yds", pool)
        with self.assertRaises(ValueError):
            player_value("Player Receiving Yards Under 10.5", {"groups": {"passing": {"passingYards": "200"}}}, "1", {}, "NFL")

    def test_total_bases_uses_reconciled_deduplicated_hit_plays(self):
        player = {"groups": {"batting": {"hits": "2", "homeRuns": "1"}}}
        def hit(identity, kind):
            return {"id": identity, "atBatId": identity, "type": {"type": kind},
                    "participants": [{"type": "batter", "athlete": {"id": "1"}}]}
        summary = {"plays": [hit("a", "double"), hit("a", "double"), hit("b", "home-run")]}
        self.assertEqual(player_value("A. Hays Total Bases O1.5", player, "1", summary, "MLB"), (6, "batter_total_bases"))
        with self.assertRaises(ValueError):
            player_value("A. Hays Total Bases O1.5", player, "1", {"plays": []}, "MLB")

    def test_period_titles_override_generic_total_label(self):
        def team(identity, name, values):
            return {"id": identity, "team": {"id": identity, "name": name, "displayName": name},
                    "score": str(sum(values)), "linescores": [{"value": n} for n in values]}
        event = {"id": "123", "date": "2026-09-01T18:00Z",
                 "competitions": [{"competitors": [team("1", "Home", [0, 0, 0, 1, 0, 8]), team("2", "Away", [0, 0, 0, 0, 0, 7])]}]}
        pick = {"id": "x", "bettor_name": "Test", "bet_type": "total", "bet_title": "1st inning Under 0.5",
                "sport": "MLB", "odds": "-110", "units": 1, "posted_at": "2026-09-01T16:00Z", "result": "win"}
        first = grade_pick(pick, event, {})
        self.assertEqual((first["verified"], first["actual"], first["periods"]), ("win", 0, [1]))
        five = grade_pick({**pick, "bet_title": "First 5 innings U4"}, event, {})
        self.assertEqual((five["verified"], five["actual"]), ("win", 1))
        quarter = grade_pick({**pick, "sport": "NFL", "bet_type": "q2_total", "bet_title": "Under 0.5"}, event, {})
        self.assertEqual((quarter["verified"], quarter["actual"], quarter["periods"]), ("win", 0, [2]))

    def test_source_pending_and_duplicate_rows_do_not_inflate_record(self):
        base = {"bettor_name": "Test", "sport": "NFL", "verified": "win", "units": 1,
                "profit": 1, "flat_profit": 1, "posted_before_espn_start": True,
                "provider_result_match": True, "result": "win"}
        result = summarize([base, {**base, "duplicate_of": "original"}, {**base, "result": "pending", "provider_result_match": None}])
        self.assertEqual(result["outcomes"]["graded"], 1)
        self.assertEqual(result["outcomes"]["profit"], 1)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["source_ungraded"], 1)


if __name__ == "__main__":
    unittest.main()
