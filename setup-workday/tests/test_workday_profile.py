"""Workday's own Chrome profile and its sign-in step, with a stand-in for Chrome; no browser, network, credentials or real timesheets."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workday_browser as WB  # noqa: E402
from test_workday_browser import ACCOUNT, calendar  # noqa: E402

OWN = ACCOUNT | {"browser": "own"}
PAGE = ACCOUNT["origin"] + ACCOUNT["enter_time_path"]
LOGIN = "https://login.example.invalid/sign-in?state=synthetic"


class FakeTab:
    def __init__(self, chrome):
        self.chrome, self.closed, self.target = chrome, False, f"tab-{len(chrome.tabs)}"

    def wait_for(self, script, arg=None, timeout=30):
        if not self.chrome.signed_in:
            raise WB.BrowserError("not there")
        return True

    def url(self):
        return PAGE if self.chrome.signed_in else LOGIN

    def evaluate(self, script, arg=None, timeout=30):
        return calendar() | {"workers": [f"selectedItem_{self.chrome.worker}"]}

    def close(self):
        self.closed = True


class FakeChrome:
    """Shows the given addresses one poll at a time; signed_in and worker are what a confirming tab finds."""

    def __init__(self, polls, signed_in=True, worker=ACCOUNT["worker"]):
        self.polls, self.signed_in, self.worker, self.closed, self.tabs, self.launched, self.restored = list(polls), signed_in, worker, False, [], None, ["restored"]

    def launch(self, path, url="about:blank", visible=False):
        self.launched = (path, url, visible)
        return self

    def call(self, method, params=None, session=None, timeout=30):
        return {}

    def close_pages(self, keep=None):
        self.restored = []
        for tab in self.tabs:
            tab.closed = tab.closed or tab.target != keep

    def pages(self):
        now = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
        if now is None:
            raise WB.BrowserError("Chrome closed the DevTools connection")
        return [{"type": "page", "url": u, "targetId": "window"} for u in now] + [{"type": "page", "url": "about:blank", "targetId": t.target} for t in self.tabs if not t.closed]

    def open_tab(self, url, context_id=None):
        self.tabs.append(FakeTab(self))
        return self.tabs[-1]

    def close(self):
        self.closed = True


class ProfileTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(os.path.realpath(folder.name)) / "state"
        for stub in (patch.dict(os.environ, {WB.STATE_ENV: str(self.root)}), patch.object(WB, "SIGN_IN_POLL_S", 0), patch.object(WB, "SIGN_IN_STEADY_S", 0), patch.object(WB.time, "sleep", lambda seconds: None)):
            stub.start()
            self.addCleanup(stub.stop)

    def refusal(self, call, *args, **kwargs):
        with self.assertRaises(WB.Refusal) as caught:
            call(*args, **kwargs)
        return caught.exception

    def test_the_profile_is_owner_only_outside_checkouts_and_used_by_one_command_at_a_time(self):
        with WB.own_profile() as path:
            self.assertEqual(path, self.root / "workday" / "chrome-profile")
            self.assertEqual(stat.S_IMODE(path.lstat().st_mode), 0o700)
            self.assertEqual(self.refusal(WB.own_profile().__enter__).code, "PROFILE_IN_USE")
        with WB.own_profile():
            pass
        path.chmod(0o755)
        self.assertEqual(self.refusal(WB.own_profile().__enter__).code, "PRIVATE_STORAGE_REQUIRED")
        path.chmod(0o700)
        path.rmdir()
        path.symlink_to(self.root)
        self.assertEqual(self.refusal(WB.own_profile().__enter__).code, "PRIVATE_STORAGE_REQUIRED")
        (self.root / ".git").mkdir()
        self.assertEqual(self.refusal(WB.own_profile().__enter__).code, "PRIVATE_STORAGE_REQUIRED")

    def sign_in(self, chrome, minutes=10):
        with patch.object(WB.Chrome, "launch", side_effect=chrome.launch):
            return WB.sign_in(OWN, minutes)

    def session(self, chrome):
        with patch.object(WB.Chrome, "launch", side_effect=chrome.launch), patch.object(WB.Chrome, "connect", side_effect=AssertionError("must not connect to the everyday Chrome")):
            return WB.Session(OWN)

    def test_sign_in_waits_for_a_settled_workday_page_confirms_the_worker_and_closes(self):
        chrome = FakeChrome([[PAGE], [LOGIN], [LOGIN], [PAGE], [PAGE]])
        self.assertEqual(self.sign_in(chrome), {"status": "signed-in"})
        self.assertEqual(chrome.launched, (WB.profile_path(), PAGE, True))
        self.assertTrue(chrome.closed and all(t.closed for t in chrome.tabs))
        record = WB.sign_in_record()
        self.assertEqual(record["signed_in_at"], record["last_working_at"])
        self.assertEqual(stat.S_IMODE((self.root / "workday" / "sign-in.json").stat().st_mode), 0o600)
        with WB.own_profile():
            pass

    def test_nothing_is_attached_while_the_sign_in_page_shows(self):
        chrome = FakeChrome([[LOGIN]])
        self.assertEqual(self.refusal(self.sign_in, chrome, 0.001).code, "SIGN_IN_TIMED_OUT")
        self.assertEqual(chrome.tabs, [])
        self.assertTrue(chrome.closed)

    def test_a_workday_address_that_still_wants_a_sign_in_keeps_waiting(self):
        chrome = FakeChrome([[PAGE]], signed_in=False)
        self.assertEqual(self.refusal(self.sign_in, chrome, 0.001).code, "SIGN_IN_TIMED_OUT")
        self.assertTrue(chrome.tabs and all(t.closed for t in chrome.tabs))
        self.assertEqual(WB.sign_in_record(), {})

    def test_another_worker_a_closed_window_and_the_wrong_mode_are_refused(self):
        wrong = FakeChrome([[PAGE]], worker="000$000009")
        self.assertEqual(self.refusal(self.sign_in, wrong).code, "WORKER_MISMATCH")
        self.assertTrue(wrong.closed)
        for polls in ([[]], [[LOGIN], None]):
            gone = FakeChrome(polls)
            self.assertEqual(self.refusal(self.sign_in, gone).code, "SIGN_IN_CANCELLED")
            self.assertTrue(gone.closed)
        self.assertEqual(self.refusal(WB.sign_in, ACCOUNT).code, "OWN_PROFILE_NOT_CHOSEN")
        self.assertEqual(WB.sign_in_record(), {})

    def test_commands_run_without_a_window_close_restored_tabs_and_release_the_profile(self):
        chrome = FakeChrome([[PAGE]])
        session = self.session(chrome)
        self.assertEqual(chrome.launched, (WB.profile_path(), "about:blank", False))
        self.assertEqual((chrome.restored, session.tab.closed), ([], False))
        self.assertTrue(WB.alive(session))
        with patch.object(WB.Chrome, "launch", side_effect=AssertionError("one Chrome at a time")):
            self.assertEqual(self.refusal(WB.Session, OWN).code, "PROFILE_IN_USE")
        session.close()
        self.assertTrue(chrome.closed)
        with patch.object(WB.Chrome, "launch", side_effect=WB.BrowserError("no")):
            self.assertEqual(self.refusal(WB.Session, OWN).code, "BROWSER_NOT_STARTED")
        with WB.own_profile():
            pass

    def test_a_lost_tab_ends_the_session(self):
        chrome = FakeChrome([[PAGE]])
        session = self.session(chrome)
        chrome.tabs[-1].closed = True
        self.assertFalse(WB.alive(session))
        session.close()

    def test_the_record_measures_how_long_a_sign_in_lasted(self):
        self.root.mkdir(mode=0o700)
        (self.root / "workday").mkdir(mode=0o700)
        WB.note_sign_in(ACCOUNT, "signed_in_at")
        self.assertEqual(WB.sign_in_record(), {})
        for event in ("signed_in_at", "last_working_at", "signed_out_at"):
            WB.note_sign_in(OWN, event)
        first = WB.sign_in_record()
        self.assertTrue({"signed_in_at", "last_working_at", "signed_out_at"} <= set(first))
        WB.note_sign_in(OWN, "signed_out_at")
        self.assertEqual(WB.sign_in_record()["signed_out_at"], first["signed_out_at"])
        WB.note_sign_in(OWN, "signed_in_at")
        again = WB.sign_in_record()
        self.assertNotIn("signed_out_at", again)
        self.assertEqual(again["previous"]["signed_out_at"], first["signed_out_at"])
        self.assertNotIn("previous", again["previous"])

    def test_reading_records_whether_the_sign_in_still_worked(self):
        for signed_in, key in ((True, "last_working_at"), (False, "signed_out_at")):
            chrome = FakeChrome([[PAGE]], signed_in=signed_in)
            session = self.session(chrome)
            session.tab.navigate = lambda url: None
            # The first wait is for the freshly loaded document; only the calendar wait depends on the sign-in.
            waits, real = [], session.tab.wait_for
            session.tab.wait_for = lambda script, arg=None, timeout=30: waits.append(script) or (True if len(waits) == 1 else real(script, arg, timeout))
            with patch.object(WB, "go_to_week"):
                if signed_in:
                    session.show_week(None)
                else:
                    self.assertEqual(self.refusal(session.show_week, None).code, "SIGN_IN_REQUIRED")
            self.assertIn(key, WB.sign_in_record())
            session.close()

    def test_a_signed_out_profile_names_the_sign_in_command(self):
        error = self.refusal(WB.open_calendar, FakeTab(FakeChrome([[LOGIN]], signed_in=False)), OWN)
        self.assertEqual(error.code, "SIGN_IN_REQUIRED")
        self.assertIn("sign-in", error.remedy)

    def test_check_reports_the_profile_without_starting_chrome(self):
        account = self.root / "account.json"
        self.root.mkdir(mode=0o700)
        account.write_text(json.dumps(OWN), encoding="utf-8")
        account.chmod(0o600)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(WB.Chrome, "launch", side_effect=AssertionError("no launch")):
            code = WB.main(["check", "--account", str(account)])
        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertEqual(json.loads(out.getvalue()), {"status": "ok", "account": "valid", "browser": "own", "profile_exists": False, "sign_in": {}})


if __name__ == "__main__":
    unittest.main()
