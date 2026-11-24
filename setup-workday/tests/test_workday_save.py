"""The Workday save path against scripted stand-ins: no browser, network or real timesheets."""

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
from test_workday_browser import ACCOUNT, TARGET, build, calendar, review  # noqa: E402
from workday_core import preview  # noqa: E402

WEEK = date(2026, 10, 26)
ENTRY = {"date": "2026-10-28", "start": "09:30", "end": "11:30", "breaks": [], "time_type": "Hours Worked", "worktags": {}}
STEP1 = {"lines": ["Quick Add", "Worker", "Worker", "Synthetic Worker (abc123)", "Start Date", "Start Date", "10/26/2026", "End Date", "End Date", "11/01/2026", "Time Type", "Time Type", "Hours Worked"], "workers": ["selectedItem_000$000001"], "selected": ["Hours Worked"], "times": [], "days": [], "buttons": ["Next", "Cancel"]}


def step2(start="9:30 AM", end="11:30 AM", ticked=("Wednesday",), out_reason="Out"):
    lines = ["Quick Add", "Time Type", "Time Type", "Non-Exempts: Hours Worked (In/Out)", "In", "In", "Out", "Out", "Out Reason", "Out Reason", out_reason, f"{out_reason} selected"]
    return {"lines": lines, "workers": ["selectedItem_000$000001"], "selected": [out_reason], "times": [["In", start], ["Out", end]], "days": [[d, d in ticked] for d in WB.WEEKDAYS], "buttons": ["OK", "Back", "Cancel"]}


class ScriptedTab:
    """Answers the save path's page scripts from a script of states, recording what was clicked and typed."""

    def __init__(self, revision_calendar, second=None, done=True):
        self.calendar, self.second, self.done = revision_calendar, second or step2(), done
        self.clicked, self.typed, self.page = [], [], "calendar"

    def evaluate(self, script, arg=None, timeout=30):
        if script == WB.CALENDAR_JS:
            return copy.deepcopy(self.calendar)
        if script == WB.CLICK_JS:
            self.clicked.append(arg)
            return True
        if script == WB.QA_STATE_JS:
            return copy.deepcopy(STEP1 if self.page == "step1" else self.second)
        if script == WB.QA_BUTTON_JS:
            self.clicked.append(arg)
            self.page = {"Next": "step2", "OK": "sent", "Cancel": "cancelled"}.get(arg, self.page)
            return True
        if script in (WB.QA_FOCUS_JS, WB.QA_SET_JS, WB.QA_DAY_JS):
            return True
        if script == WB.QA_OPEN_JS:
            return self.page in ("step1", "step2")
        if script == WB.DISCARD_JS:
            return False
        raise AssertionError(script[:60])

    def wait_for(self, script, arg=None, timeout=30):
        if "Quick Add" in script and "Next" in script:
            self.page = "step1"
        if script == WB.QA_DONE_JS and not self.done:
            raise WB.BrowserError("still open")
        return True

    def insert_text(self, text):
        self.typed.append(text)


def session(tab):
    s = WB.Session.__new__(WB.Session)
    s.account, s.tab = ACCOUNT | {"save_safeguard": "reread"}, tab
    return s


class CreateDraftTests(unittest.TestCase):
    def setUp(self):
        for stub in (patch.object(WB.Session, "show_week", lambda self, week: None), patch.object(WB.time, "sleep", lambda seconds: None)):
            stub.start()
            self.addCleanup(stub.stop)
        self.calendar = calendar()
        self.revision = WB.calendar_revision(self.calendar)

    def test_a_checked_quick_add_is_sent_once(self):
        tab = ScriptedTab(self.calendar)
        session(tab).create_draft(TARGET, ENTRY, self.revision)
        self.assertEqual(tab.clicked.count("OK"), 1)
        self.assertEqual(tab.typed, ["9:30 AM", "11:30 AM"])
        self.assertNotIn("Cancel", tab.clicked)

    def test_a_changed_calendar_stops_before_anything_is_opened(self):
        tab = ScriptedTab(self.calendar)
        with self.assertRaises(WB.NotDispatched):
            session(tab).create_draft(TARGET, ENTRY, "calendar-sha256:other")
        self.assertEqual(tab.clicked, [])

    def test_any_mismatch_before_ok_cancels_cleanly(self):
        for second in (step2(start="1:00 PM"), step2(ticked=("Wednesday", "Thursday")), step2(ticked=("Tuesday",)), step2(out_reason="Meal")):
            tab = ScriptedTab(self.calendar, second=second)
            with self.assertRaises(WB.NotDispatched):
                session(tab).create_draft(TARGET, ENTRY, self.revision)
            self.assertNotIn("OK", tab.clicked)
            self.assertIn("Cancel", tab.clicked)

    def test_unsupported_entries_never_reach_workday(self):
        for change in ({"time_type": "WCI Day of Injury"}, {"breaks": [{"start": "10:00", "end": "10:30"}]}, {"worktags": {"grant": "x"}}, {"date": "2026-11-02"}):
            tab = ScriptedTab(self.calendar)
            with self.assertRaises(WB.NotDispatched):
                session(tab).create_draft(TARGET, ENTRY | change, self.revision)
            self.assertEqual(tab.clicked, [])

    def test_a_failure_after_ok_is_uncertain_not_a_clean_stop(self):
        tab = ScriptedTab(self.calendar, done=False)
        with self.assertRaises(RuntimeError):
            session(tab).create_draft(TARGET, ENTRY, self.revision)
        self.assertEqual(tab.clicked.count("OK"), 1)


class HelperTests(unittest.TestCase):
    def test_twelve_hour_and_field_values(self):
        self.assertEqual([WB.twelve_hour(t) for t in ("00:15", "09:05", "12:00", "13:30", "23:59")], ["12:15 AM", "9:05 AM", "12:00 PM", "1:30 PM", "11:59 PM"])
        self.assertEqual(WB.field_value(STEP1["lines"], "Start Date"), "10/26/2026")
        self.assertIsNone(WB.field_value(STEP1["lines"], "Missing"))

    def test_quick_add_must_start_on_the_week_worker_and_type(self):
        account = ACCOUNT
        WB.check_quick_add_start(STEP1, account, WEEK)
        for change, code in (({"workers": ["selectedItem_000$000009"]}, "WORKER_MISMATCH"), ({"selected": ["Hours Worked", "Absence"]}, "UNSUPPORTED_ENTRY"), ({"lines": [x.replace("11/01/2026", "11/08/2026") for x in STEP1["lines"]]}, "WEEK_MISMATCH")):
            with self.assertRaises(WB.Refusal) as caught:
                WB.check_quick_add_start(STEP1 | change, account, WEEK)
            self.assertEqual(caught.exception.code, code)

    def test_settling_an_uncertain_save(self):
        now = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
        intent = {"entry": ENTRY, "recorded_at": (now - timedelta(minutes=2)).isoformat()}
        empty = {"entries": []}
        landed = {"entries": [{"id": "1", "status": "draft", "entry": ENTRY}]}
        protected = {"entries": [{"id": "1", "status": "submitted", "entry": ENTRY}]}
        self.assertEqual(WB.settle_outcome(intent, landed, now), "landed")
        self.assertEqual(WB.settle_outcome(intent, protected, now), "present-not-draft")
        self.assertEqual(WB.settle_outcome(intent, empty, now), "wait")
        self.assertEqual(WB.settle_outcome(intent, empty, now + timedelta(minutes=9)), "not-applied")


class SaveCommandTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        env = patch.dict(os.environ, {WB.STATE_ENV: os.path.realpath(self.dir.name)})
        env.start()
        self.addCleanup(env.stop)

    def plan(self, entries):
        empty_week = dict(calendar=calendar(blocks=[], hours=("0",) * 7, total="0"), details=[])
        snapshot, _, _ = build(account=ACCOUNT | {"time_types": ["Hours Worked"], "save_safeguard": "reread"}, review=review(blocks=[]) | {"headers": []}, **empty_week)
        allocation = {"schema_version": 1, "target": TARGET, "entries": entries, "expected_total_minutes": sum(WB.minutes_between(e["start"], e["end"]) for e in entries)}
        return snapshot, preview(snapshot, allocation)

    def test_saves_need_the_accounts_choice_and_supported_entries_before_connecting(self):
        _, plan = self.plan([ENTRY])
        with patch.object(WB, "Session", side_effect=AssertionError("must not connect")):
            with self.assertRaises(WB.Refusal) as caught:
                WB.save(ACCOUNT, plan, plan["plan_fingerprint"])
            self.assertEqual(caught.exception.code, "SAVES_NOT_ENABLED")

    def test_the_engine_runs_with_the_reread_safeguard(self):
        snapshot, plan = self.plan([ENTRY])

        class FakeSession:
            save_safeguard, supports_conditional_create = "reread", False

            def __init__(self, account):
                self.state, self.closed = copy.deepcopy(snapshot), False

            def read(self, binding):
                return copy.deepcopy(self.state)

            def create_draft(self, binding, entry, expected_revision):
                assert expected_revision == self.state["revision"]
                self.state["entries"].append({"id": "5773$9", "status": "draft", "entry": entry})
                self.state["status"], self.state["service_total_minutes"], self.state["revision"] = "draft", 120, "calendar-sha256:after"

            def close(self):
                self.closed = True

        with patch.object(WB, "Session", FakeSession):
            result = WB.save(ACCOUNT | {"save_safeguard": "reread"}, plan, plan["plan_fingerprint"])
        self.assertEqual((result["status"], result["completed"], result["submitted"]), ("saved-draft", [ENTRY], False))
        self.assertEqual(os.stat(WB.journal_dir()).st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
