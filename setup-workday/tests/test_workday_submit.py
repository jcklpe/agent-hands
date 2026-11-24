"""Workday submission against synthetic panels and a stand-in session; no browser, network or real timesheets."""

import copy
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workday_browser as WB  # noqa: E402
from test_workday_browser import ACCOUNT, TARGET, build, calendar  # noqa: E402

CERT = "I certify this is an accurate record of hours worked and absent. Misrepresentation is subject to corrective action."


def panel(range_text="October 26 – November 1, 2026", hours="12", total="12", comment=""):
    lines = ["Submit Time", "Click the", "Submit", "button below to certify time for approval", CERT, "Following date range will be submitted for approval.", f"{range_text} : {hours} Hours", f"Total for {range_text}", "Example Time Entry: Example Hours", total, "Timesheet Total", total, "enter your comment", "Submit", "Cancel"]
    return {"lines": lines, "comments": [comment], "buttons": ["Submit", "Cancel"]}


def drafts():
    return build(calendar=calendar(style="saved", label="Not Submitted"))


class PanelTests(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(WB.parse_long_range("November 16 – 22, 2026"), (date(2026, 11, 16), date(2026, 11, 22)))
        self.assertEqual(WB.parse_long_range("October 26 – November 1, 2026"), (date(2026, 10, 26), date(2026, 11, 1)))
        self.assertEqual(WB.parse_long_range("December 28, 2026 – January 3, 2027"), (date(2026, 12, 28), date(2027, 1, 3)))
        with self.assertRaises(WB.Refusal):
            WB.parse_long_range("Someday")

    def test_the_panel_is_read_from_split_text(self):
        parsed = WB.parse_submit_panel(panel())
        self.assertEqual(parsed, {"certification": CERT, "range": ["2026-10-26", "2026-11-01"], "range_minutes": 720, "timesheet_total_minutes": 720, "comments": [""]})
        with self.assertRaisesRegex(WB.Refusal, "certification"):
            WB.parse_submit_panel({"lines": ["Submit Time", "Timesheet Total", "12"], "comments": []})


class PlanTests(unittest.TestCase):
    def plan(self, snapshot_parts=None, shown=None):
        snapshot, result, observations = snapshot_parts or drafts()
        return WB.submit_plan(TARGET, snapshot, result, observations, WB.parse_submit_panel(shown or panel()))

    def test_a_draft_week_makes_a_bound_plan(self):
        plan = self.plan()
        self.assertEqual((plan["total_minutes"], plan["certification"], plan["submittable_from"]), (720, CERT, "2026-11-01"))
        WB.check_submit_plan(plan, plan["plan_fingerprint"])
        tampered = copy.deepcopy(plan)
        tampered["total_minutes"] = 60
        for candidate, approved, code in ((tampered, plan["plan_fingerprint"], "PLAN_CHANGED"), (plan, "0" * 64, "APPROVAL_MISMATCH")):
            with self.assertRaises(WB.Refusal) as caught:
                WB.check_submit_plan(candidate, approved)
            self.assertEqual(caught.exception.code, code)

    def test_unsafe_weeks_and_panels_are_refused(self):
        cases = [
            (dict(snapshot_parts=build()), "NOT_SUBMITTABLE"),
            (dict(shown=panel(range_text="November 2 – 8, 2026")), "PANEL_MISMATCH"),
            (dict(shown=panel(hours="13", total="13")), "PANEL_MISMATCH"),
            (dict(shown=panel(comment="note")), "PANEL_MISMATCH"),
        ]
        for kwargs, code in cases:
            with self.assertRaises(WB.Refusal) as caught:
                self.plan(**kwargs)
            self.assertEqual(caught.exception.code, code)
        snapshot, result, observations = drafts()
        observations = observations | {"rounded_blocks": [{"date": "2026-10-26"}]}
        with self.assertRaises(WB.Refusal) as caught:
            self.plan(snapshot_parts=(snapshot, result, observations))
        self.assertEqual(caught.exception.code, "NOT_SUBMITTABLE")

    def test_weeks_submit_from_their_sunday(self):
        plan = self.plan()
        self.assertFalse(WB.week_over(ACCOUNT, plan, today=date(2026, 10, 31)))
        self.assertTrue(WB.week_over(ACCOUNT, plan, today=date(2026, 11, 1)))


class FakeSession:
    """Stands in for the browser session: a draft week that becomes submitted when Submit is pressed."""

    def __init__(self, plan, change=None, fail_press=False):
        self.plan, self.change, self.fail_press = plan, change, fail_press
        self.pressed, self.closed = 0, False
        self.state = drafts()

    def read(self, target):
        snapshot, result, observations = self.state
        self.result, self.observations = result, observations
        return snapshot

    def submit_week(self, plan):
        if self.change == "week":
            WB.refuse("STALE_PLAN", "changed")
        if self.change == "panel":
            WB.refuse("PANEL_CHANGED", "changed")
        return True

    def press_submit(self):
        self.pressed += 1
        snapshot, result, observations = copy.deepcopy(self.state)
        for record in snapshot["entries"]:
            record["status"] = "submitted"
        snapshot["status"] = "submitted"
        self.state = (snapshot, result, observations)
        if self.fail_press:
            raise WB.BrowserError("lost")

    def close(self):
        self.closed = True


class SubmitCommandTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir="/tmp")
        env = patch.dict(os.environ, {WB.STATE_ENV: os.path.realpath(self.dir)})
        env.start()
        self.addCleanup(env.stop)
        snapshot, result, observations = drafts()
        self.plan = WB.submit_plan(TARGET, snapshot, result, observations, WB.parse_submit_panel(panel()))

    def test_a_matching_week_is_submitted_once_and_read_back(self):
        fake = FakeSession(self.plan)
        result = WB.submit(ACCOUNT, self.plan, self.plan["plan_fingerprint"], fake)
        self.assertEqual((result["status"], fake.pressed), ("submitted", 1))
        journal = WB.Journal(WB.journal_dir())
        with journal.guard(TARGET):
            self.assertFalse(journal.pending())

    def test_a_changed_week_or_panel_submits_nothing(self):
        for change, code in (("week", "STALE_PLAN"), ("panel", "PANEL_CHANGED")):
            fake = FakeSession(self.plan, change=change)
            with self.assertRaises(WB.Refusal) as caught:
                WB.submit(ACCOUNT, self.plan, self.plan["plan_fingerprint"], fake)
            self.assertEqual((caught.exception.code, fake.pressed), (code, 0))

    def test_an_unfinished_week_is_refused_before_connecting(self):
        future = copy.deepcopy(self.plan)
        future["submittable_from"] = (date.today() + timedelta(days=3)).isoformat()
        future["plan_fingerprint"] = WB.fingerprint({k: v for k, v in future.items() if k != "plan_fingerprint"})
        with patch.object(WB, "Session", side_effect=AssertionError("must not connect")):
            with self.assertRaises(WB.Refusal) as caught:
                WB.submit(ACCOUNT, future, future["plan_fingerprint"])
        self.assertEqual(caught.exception.code, "WEEK_NOT_OVER")

    def test_a_lost_click_is_uncertain_and_reconcile_settles_it(self):
        fake = FakeSession(self.plan, fail_press=True)
        result = WB.submit(ACCOUNT, self.plan, self.plan["plan_fingerprint"], fake)
        self.assertEqual((result["status"], fake.pressed), ("uncertain", 1))
        with self.assertRaises(WB.Refusal) as caught:
            WB.submit(ACCOUNT, self.plan, self.plan["plan_fingerprint"], FakeSession(self.plan))
        self.assertEqual(caught.exception.code, "RECONCILE_REQUIRED")
        settled = WB.reconcile(ACCOUNT, TARGET, fake)
        self.assertEqual(settled["status"], "landed")

    def test_an_unsubmitted_week_settles_as_not_applied_only_after_waiting(self):
        intent = {"kind": "submit", "entries": drafts()[0]["entries"], "recorded_at": datetime.now(timezone.utc).isoformat()}
        snapshot = drafts()[0]
        now = datetime.now(timezone.utc)
        self.assertEqual(WB.settle_submission(intent, snapshot, now), "wait")
        self.assertEqual(WB.settle_submission(intent, snapshot, now + timedelta(minutes=11)), "not-applied")
        changed = copy.deepcopy(snapshot)
        changed["entries"][0]["entry"]["end"] = "15:00"
        self.assertEqual(WB.settle_submission(intent, changed, now), "present-not-draft")


if __name__ == "__main__":
    unittest.main()
