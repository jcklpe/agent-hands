import json
import unittest

from canvas_fixture import CanvasFixture, ORIGIN
from canvas_history import History
from canvas_feedback import feedback
import test_cli


BASE = "/api/v1/courses/123/assignments/456"


class FeedbackFixture(CanvasFixture):
    def __init__(self):
        super().__init__()
        self.assignment = {"id": 456, "course_id": 123, "name": "Example presentation", "points_possible": 25, "rubric": [{"id": "_criterion", "description": "Clarity", "long_description": "Explain the example", "points": 5}]}
        self.submission = {
            "assignment_id": 456, "user_id": 1001, "attempt": 2, "workflow_state": "graded", "score": 24, "grade": "24", "grade_matches_current_submission": False,
            "submission_comments": [{"id": n, "author_id": 2002, "author_name": "Example Teacher", "created_at": "2026-11-01T12:00:00Z", "comment": f"Private feedback {n}"} for n in reversed(range(1, 8))],
            "rubric_assessment": {"_criterion": {"points": 4, "rating_id": "_rating", "comments": "Private criterion feedback"}},
            "body": "Excluded submission body", "preview_url": "https://example.com/?verifier=private-value",
        }

    def route(self, path, params):
        if path == BASE:
            return self.assignment
        if path == BASE + "/submissions/self":
            assert params == {"include[]": ["submission_comments", "rubric_assessment"]}
            return self.submission
        return super().route(path, params)


class FeedbackTest(unittest.TestCase):
    run_cli = test_cli.CliTest.run_cli

    def setUp(self):
        test_cli.CliTest.setUp(self)
        self.fixture = FeedbackFixture()

    def run_feedback(self, *args):
        return self.run_cli("feedback", "example", "--course", "123", "--assignment", "456", *args)

    def test_read_all_comments_rubric_and_current_attempt_without_mutation(self):
        code, output, error = self.run_feedback("--json")
        self.assertEqual(code, 0, error)
        value = json.loads(output)
        self.assertEqual([row["id"] for row in value["comments"]], [str(n) for n in range(1, 8)])
        self.assertEqual(value["comments"][0]["author_name"], "Example Teacher")
        self.assertIsNone(value["comments"][0]["attempt"])
        self.assertEqual(value["rubric"][0]["description"], "Clarity")
        self.assertEqual(value["rubric"][0]["comments"], "Private criterion feedback")
        self.assertEqual(value["submission"]["attempt"], 2)
        self.assertFalse(value["submission"]["grade_matches_current_submission"])
        self.assertEqual([path for path, _ in self.fixture.sent], ["/api/v1/users/self", "/api/v1/users/self/profile", BASE, BASE + "/submissions/self"])
        self.assertNotIn("Excluded submission body", output)
        self.assertNotIn("private-value", output)
        self.assertEqual(self.fixture.downloads, [])

    def test_history_contains_only_metadata(self):
        self.assertEqual(self.run_feedback()[0], 0)
        rows = list(History(self.root / "history").rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["course_ids"], ["123"])
        self.assertEqual(rows[0]["target_ids"], ["456"])
        self.assertEqual(rows[0]["counts"], {"comments": 7, "rubric_criteria": 1})
        self.assertNotIn("Private", json.dumps(rows))
        self.assertNotIn("Example Teacher", json.dumps(rows))

    def test_readable_output_preserves_attribution_and_limits(self):
        self.fixture.submission["submission_comments"][0].update(edited_at="2026-11-02T12:00:00Z", attempt=1)
        code, output, error = self.run_feedback()
        self.assertEqual(code, 0, error)
        for expected in ("Example Teacher", "Private feedback 7", "Edited: 2026-11-02", "Comment attempt: 1", "Clarity — 4 / 5", "Grade matches current submission: False", "DocViewer annotations"):
            self.assertIn(expected, output)

    def test_attachment_and_media_metadata_never_fetches_content(self):
        self.fixture.submission["submission_comments"][0].update(attachments=[{"id": 900, "display_name": "Review.pdf", "url": "https://files.example.com/file?verifier=secret"}], media_comment={"display_name": "Audio review", "media_type": "audio", "url": "https://files.example.com/audio"})
        code, output, error = self.run_feedback("--json")
        self.assertEqual(code, 0, error)
        self.assertIn(f"{ORIGIN}/courses/123/files/900", output)
        self.assertNotIn("files.example.com", output)
        self.assertNotIn("secret", output)
        self.assertEqual(self.fixture.downloads, [])
        code, output, _ = self.run_feedback()
        self.assertEqual(code, 0)
        self.assertIn("Attachment (not downloaded): Review.pdf", output)
        self.assertIn("Media comment (not retrieved): Audio review", output)

    def test_empty_and_unavailable_feedback_are_distinct(self):
        for comments, rubric, expected in (([], {}, "returned"), (None, None, "not_returned")):
            with self.subTest(expected=expected):
                self.fixture.submission.update(submission_comments=comments, rubric_assessment=rubric, score=None, grade=None, workflow_state="unsubmitted", attempt=None)
                code, output, error = self.run_feedback("--json")
                self.assertEqual(code, 0, error)
                value = json.loads(output)
                self.assertEqual(value["comments"], [])
                self.assertEqual(value["coverage"], {"comments": expected, "rubric_assessment": expected})
        del self.fixture.submission["submission_comments"]
        del self.fixture.submission["rubric_assessment"]
        self.assertIn("absence is unknown", self.run_feedback()[1])

    def test_unselected_course_refused_before_assignment_request(self):
        self.fixture.course_ids = ["999"]
        with self.assertRaisesRegex(Exception, "explicit course selection"):
            feedback(self.fixture.reader(), "123", "456")
        self.assertFalse(any("assignments" in path for path, _ in self.fixture.sent))
        code, _, error = self.run_cli("feedback", "example", "--course", "999", "--assignment", "456")
        self.assertEqual(code, 1)
        self.assertIn("config_invalid", error)

    def test_identity_gate_stops_before_feedback(self):
        config = json.loads(self.config.read_text())
        config["accounts"][0]["user_id"] = "2002"
        self.config.write_text(json.dumps(config))
        code, output, error = self.run_feedback()
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("identity_mismatch", error)
        self.assertEqual([path for path, _ in self.fixture.sent], ["/api/v1/users/self"])

    def test_wrong_or_missing_target_identity_fails_closed(self):
        for target, key in ((self.fixture.assignment, "id"), (self.fixture.assignment, "course_id"), (self.fixture.submission, "assignment_id"), (self.fixture.submission, "user_id")):
            original = target[key]
            for wrong in (999, None):
                with self.subTest(key=key, wrong=wrong):
                    target[key] = wrong
                    code, output, error = self.run_feedback()
                    self.assertEqual(code, 1)
                    self.assertEqual(output, "")
                    self.assertIn("malformed", error)
            target[key] = original

    def test_malformed_feedback_is_not_reported_as_empty(self):
        for key, wrong in (("submission_comments", {}), ("submission_comments", ["bad"]), ("submission_comments", [{"id": 1, "comment": {}}]), ("rubric_assessment", []), ("rubric_assessment", {"_criterion": "bad"})):
            original = self.fixture.submission[key]
            with self.subTest(key=key, wrong=wrong):
                self.fixture.submission[key] = wrong
                code, output, error = self.run_feedback()
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("malformed", error)
            self.fixture.submission[key] = original

    def test_denied_feedback_is_a_failed_read_not_an_empty_success(self):
        self.fixture.failures[BASE + "/submissions/self"] = (403, {})
        code, output, error = self.run_feedback()
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("denied", error)
        self.assertEqual(list(History(self.root / "history").rows())[-1]["outcome"], "failed")


if __name__ == "__main__":
    unittest.main()
