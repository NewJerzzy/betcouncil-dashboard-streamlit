import unittest

from scripts.audit_bettinginsider_props import _grade, _line, _resolve_event, _summarize


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


if __name__ == "__main__":
    unittest.main()
