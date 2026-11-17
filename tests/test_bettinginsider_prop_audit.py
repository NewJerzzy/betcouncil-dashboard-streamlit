import unittest

from scripts.audit_bettinginsider_props import (
    _extract_stat, _grade, _line, _player_candidates, _pregame_performance,
    _resolve_event, _summarize,
)


EVENT = {
    "id": "123456789",
    "date": "2026-09-01T18:00:00Z",
    "status": {"type": {"completed": True}},
}
SUMMARY = {
    "boxscore": {
        "players": [{
            "team": {"displayName": "Seattle Seahawks"},
            "statistics": [{
                "name": "receiving",
                "labels": ["REC", "YDS", "TD"],
                "athletes": [{
                    "athlete": {
                        "id": "player-1",
                        "firstName": "Mason",
                        "lastName": "Wilson",
                        "shortName": "M. Wilson",
                        "displayName": "Mason Wilson",
                    },
                    "stats": ["3", "25", "0"],
                }],
            }],
        }],
    },
}


def pick(**changes):
    return {
        "id": "pick-1",
        "bettor_name": "Insider Mike",
        "sport": "NFL",
        "game_id": "NFL-20260901-SEA-DEN-123456789",
        "game_title": "Seahawks @ Broncos",
        "bet_title": "M. Wilson Receiving Yards Over 10.5",
        "stat_type": "player_reception_yds",
        "odds": "-110",
        "units": 1,
        "posted_at": "2026-09-01T17:00:00Z",
        "result": "win",
        **changes,
    }


def grade(record, event=EVENT, summary=SUMMARY, reason=""):
    mapping = {str(record.get("id")): ("football/nfl", event, reason)}
    summaries = {("football/nfl", str(EVENT["id"])): summary} if event else {}
    return _grade(record, mapping, summaries)


class BettingInsiderPropAuditTests(unittest.TestCase):
    def test_parlay_and_multi_leg_titles_are_not_partially_parsed(self):
        titles = (
            "SGP: M. Wilson Receiving Yards Over 10.5",
            "M. Wilson Receiving Yards Over 10.5 + T. Hill Receptions Under 4.5",
            "M. Wilson Receiving Yards Over 10.5 + Seahawks ML",
        )
        for title in titles:
            with self.subTest(title=title):
                selection, line, reason = _line(pick(bet_title=title))
                row = grade(pick(bet_title=title))
                self.assertIsNone(selection)
                self.assertIsNone(line)
                self.assertIn("multi-leg or parlay", reason)
                self.assertEqual(row["independent_result"], "unresolved")
                self.assertEqual(_summarize([row])["graded"], 0)

    def test_missing_line_or_original_price_remains_unresolved(self):
        no_line = grade(pick(bet_title="M. Wilson Receiving Yards"))
        no_price = grade(pick(odds=None))
        invalid_price = grade(pick(odds="not-a-price"))

        for row in (no_line, no_price, invalid_price):
            with self.subTest(reason=row["unresolved_reason"]):
                self.assertEqual(row["independent_result"], "unresolved")
                self.assertEqual(_summarize([row])["pregame"]["graded"], 0)
        self.assertIn("selection/line", no_line["unresolved_reason"])
        self.assertIn("original price", no_price["unresolved_reason"])
        self.assertEqual(_summarize([no_price, invalid_price])["missing_or_invalid_original_price"], 2)

    def test_ambiguous_player_match_does_not_count_as_a_grade(self):
        ambiguous_summary = {
            "boxscore": {
                "players": [{
                    "team": {"displayName": "Example"},
                    "statistics": [{
                        "name": "receiving", "labels": ["YDS"],
                        "athletes": [
                            {"athlete": {"id": "1", "firstName": "David", "lastName": "Smith",
                                         "shortName": "D. Smith"}, "stats": ["30"]},
                            {"athlete": {"id": "2", "firstName": "Devin", "lastName": "Smith",
                                         "shortName": "D. Smith"}, "stats": ["0"]},
                        ],
                    }],
                }],
            },
        }
        row = grade(
            pick(bet_title="D. Smith Receiving Yards Over 10.5"),
            summary=ambiguous_summary,
        )
        self.assertIsNone(row["player"])
        self.assertIn("ambiguous ESPN player match", row["stat_evidence"])
        self.assertEqual(row["independent_result"], "unresolved")
        self.assertEqual(_summarize([row])["pregame"]["graded"], 0)

    def test_missing_espn_event_identity_does_not_count_as_a_grade(self):
        record = pick(game_id="", bet_title="M. Wilson Receiving Yards Over 10.5")
        event, reason = _resolve_event(record, [EVENT])
        row = grade(record, event=event, reason=reason)

        self.assertIsNone(event)
        self.assertIn("ambiguous/missing ESPN event", reason)
        self.assertIsNone(row["espn_event_id"])
        self.assertEqual(row["independent_result"], "unresolved")
        self.assertEqual(_summarize([row])["pregame"]["graded"], 0)

    def test_pregame_summary_excludes_at_and_after_kickoff_records(self):
        before = grade(pick(id="pregame", posted_at="2026-09-01T17:59:59Z"))
        at_kickoff = grade(pick(id="at-kickoff", posted_at="2026-09-01T18:00:00Z"))
        after = grade(pick(id="after-kickoff", posted_at="2026-09-01T18:01:00Z"))

        self.assertEqual(before["independent_result"], "win")
        self.assertEqual(at_kickoff["published_at_or_after_espn_start"], True)
        self.assertEqual(after["published_at_or_after_espn_start"], True)
        summary = _summarize([before, at_kickoff, after])
        self.assertEqual(summary["graded"], 3)
        self.assertEqual(summary["pregame"]["records"], 1)
        self.assertEqual(summary["pregame"]["graded"], 1)
        self.assertEqual(summary["pregame"]["wins"], 1)
        self.assertEqual(summary["late_publications"], 2)

    def test_line_parser_supports_qualified_plus_yard_props_and_td_markets(self):
        self.assertEqual(_line(pick(bet_title="F. Brandon 40+ Rushing Yards")), ("at_least", 40.0, ""))
        self.assertEqual(_line(pick(bet_title="O. Beckham Jr. TD")), ("yes", None, ""))
        self.assertEqual(_line(pick(bet_title="J. Smith 1st TD")), ("first_td", None, ""))
        self.assertEqual(_line(pick(bet_title="E. Johnson Last TD")), ("last_td", None, ""))
        self.assertEqual(_line(pick(bet_title="K. Pitts Anytime TD")), ("yes", None, ""))

    def test_player_matching_uses_full_names_and_suffixes_to_disambiguate(self):
        summary = {
            "boxscore": {
                "players": [{
                    "team": {"displayName": "Example"},
                    "statistics": [{
                        "name": "rushing", "labels": ["YDS"],
                        "athletes": [
                            {"athlete": {"id": "bijan", "firstName": "Bijan",
                                         "lastName": "Robinson", "shortName": "B. Robinson",
                                         "displayName": "Bijan Robinson"}, "stats": ["25"]},
                            {"athlete": {"id": "brian", "firstName": "Brian",
                                         "lastName": "Robinson Jr.", "shortName": "B. Robinson Jr.",
                                         "displayName": "Brian Robinson Jr."}, "stats": ["62"]},
                        ],
                    }],
                }],
            },
        }
        candidates = _player_candidates(pick(bet_title="B. Robinson Jr. U25.5 Rush Yds"), summary)
        self.assertEqual([candidate["id"] for candidate in candidates], ["brian"])

    def test_offensive_market_and_espn_categories_resolve_defensive_namesake(self):
        summary = {
            "boxscore": {
                "players": [{
                    "statistics": [{
                        "name": "passing", "labels": ["C/ATT", "YDS"],
                        "athletes": [{
                            "athlete": {"id": "trevor", "firstName": "Trevor",
                                        "lastName": "Lawrence", "displayName": "Trevor Lawrence"},
                            "stats": ["20/30", "280"],
                        }],
                    }],
                }, {
                    "statistics": [{
                        "name": "defensive", "labels": ["TOT", "SACKS"],
                        "athletes": [{
                            "athlete": {"id": "dexter", "firstName": "Dexter",
                                        "lastName": "Lawrence II", "displayName": "Dexter Lawrence II"},
                            "stats": ["4", "1"],
                        }],
                    }],
                }],
            },
        }
        row = grade(
            pick(sport="NFL", stat_type=None, bet_title="Lawrence O261.5 Pass Yds"),
            summary=summary,
        )
        self.assertEqual(row["player"], "Trevor Lawrence")
        self.assertEqual(row["player_match_evidence"], "unique ESPN offensive-stat category match")
        self.assertEqual(row["independent_result"], "win")

    def test_unique_one_character_name_variant_can_match_espn_player(self):
        summary = {
            "boxscore": {
                "players": [{
                    "team": {"displayName": "Example"},
                    "statistics": [{
                        "name": "basketball",
                        "labels": ["MIN", "PTS", "3PT", "REB", "AST"],
                        "athletes": [{
                            "athlete": {"id": "edgecombe", "firstName": "VJ",
                                        "lastName": "Edgecombe", "shortName": "V. Edgecombe",
                                        "displayName": "VJ Edgecombe"},
                            "stats": ["30", "10", "2-5", "3", "4"],
                        }],
                    }],
                }],
            },
        }
        candidates = _player_candidates(pick(bet_title="V. Edgecomb 3+ assists"), summary)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["id"], "edgecombe")
        self.assertIn("one-character", candidates[0]["match_method"])

    def test_espn_three_point_made_attempt_value_uses_made_count(self):
        summary = {
            "boxscore": {
                "players": [{
                    "statistics": [{
                        "name": None, "labels": ["MIN", "PTS", "3PT", "REB", "AST"],
                        "athletes": [{
                            "athlete": {"id": "player-3"},
                            "stats": ["30", "12", "2-5", "4", "3"],
                        }],
                    }],
                }],
            },
        }
        value, evidence = _extract_stat(pick(), summary, "player-3", ("basketball", "3PT"))
        self.assertEqual(value, 2)
        self.assertEqual(evidence, "ESPN 3PT made count")

    def test_generic_mlb_walks_use_pitching_box_score_only_for_pitcher_line(self):
        pitching_summary = {
            "boxscore": {
                "players": [{
                    "statistics": [{
                        "name": "pitching", "labels": ["IP", "BB", "K"],
                        "athletes": [{
                            "athlete": {"id": "player-1", "firstName": "Mason",
                                        "lastName": "Wilson", "shortName": "M. Wilson",
                                        "displayName": "Mason Wilson"},
                            "stats": ["5.0", "2", "6"],
                        }],
                    }],
                }],
            },
        }
        row = grade(
            pick(sport="MLB", stat_type=None, bet_title="M. Wilson Walks O1.5"),
            summary=pitching_summary,
        )
        self.assertEqual(row["independent_result"], "win")
        self.assertEqual(row["market_mapping"], "pitching/BB")
        self.assertEqual(row["verified_stat"], 2)

    def test_first_touchdown_is_graded_from_espn_scoring_play_order(self):
        summary = {
            **SUMMARY,
            "scoringPlays": [{
                "type": {"text": "Passing Touchdown"},
                "text": "Mason Wilson 4 Yd pass from Jordan Example (Kick)",
            }],
        }
        row = grade(
            pick(bet_title="M. Wilson 1st TD"),
            summary=summary,
        )
        self.assertEqual(row["independent_result"], "win")
        self.assertEqual(row["stat_evidence"], "ESPN first td scoring play")

    def test_missing_espn_kickoff_is_not_assumed_to_be_pregame(self):
        event_without_start = {key: value for key, value in EVENT.items() if key != "date"}
        row = grade(pick(), event=event_without_start)

        self.assertEqual(row["independent_result"], "win")
        self.assertIsNone(row["published_at_or_after_espn_start"])
        self.assertIsNone(row["publication_delta_minutes"])
        summary = _summarize([row])
        self.assertEqual(summary["pregame"]["records"], 0)
        self.assertEqual(summary["pregame"]["graded"], 0)
        self.assertEqual(summary["late_publications_unknown"], 1)

    def test_performance_totals_only_use_resolved_timestamped_pregame_picks(self):
        pregame = grade(pick(id="pregame"))
        late = grade(pick(id="late", posted_at="2026-09-01T18:01:00Z"))
        unknown_start = {**EVENT}
        unknown_start.pop("date")
        unknown = grade(pick(id="unknown"), event=unknown_start)
        unresolved = grade(pick(id="unresolved", odds=None))

        performance = _pregame_performance([pregame, late, unknown, unresolved])
        self.assertEqual(performance["eligible_pick_count"], 1)
        self.assertEqual(performance["pregame_record_count"], 2)
        self.assertEqual(performance["unresolved_pregame_count"], 1)
        self.assertEqual(performance["by_expert"]["Insider Mike"]["graded"], 1)
        self.assertEqual(sum(x["records"] for x in performance["by_market"].values()), 1)


if __name__ == "__main__":
    unittest.main()
