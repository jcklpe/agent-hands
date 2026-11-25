"""Workday's own Chrome profile and its sign-in wait, with a stand-in for Chrome; no browser, network, credentials or real timesheets."""

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
        self.polls, self.signed_in, self.worker, self.closed, self.tabs, self.launched, self.minimized = list(polls), signed_in, worker, False, [], None, False

    def launch(self, path, url="about:blank"):
        self.launched = (path, url)
        return self

    def call(self, method, params=None, session=None, timeout=30):
        return {}

    def minimize(self):
        self.minimized = True

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
        self.announced = []
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

    def start(self, chrome, minutes=10, account=OWN):
        with patch.object(WB.Chrome, "launch", side_effect=chrome.launch), patch.object(WB.Chrome, "connect", side_effect=AssertionError("must not connect to the everyday Chrome")):
            return WB.Session(account, minutes, self.announced.append)

    def test_a_session_waits_for_a_settled_workday_page_confirms_the_worker_and_keeps_that_chrome(self):
        chrome = FakeChrome([[PAGE], [LOGIN], [LOGIN], [PAGE], [PAGE]])
        session = self.start(chrome)
        self.assertEqual(chrome.launched, (WB.profile_path(), PAGE))
        self.assertEqual([v["status"] for v in self.announced], ["waiting-for-sign-in"])
        self.assertTrue(chrome.minimized and not chrome.closed)
        self.assertEqual([t.closed for t in chrome.tabs], [True, False])
        self.assertIs(session.tab, chrome.tabs[1])
        self.assertTrue(WB.alive(session))
        with patch.object(WB.Chrome, "launch", side_effect=AssertionError("one Chrome at a time")):
            self.assertEqual(self.refusal(WB.Session, OWN).code, "PROFILE_IN_USE")
        session.close()
        self.assertTrue(chrome.closed)
        with WB.own_profile():
            pass

    def test_a_closed_window_ends_the_session(self):
        chrome = FakeChrome([[PAGE]])
        session = self.start(chrome)
        chrome.tabs[-1].closed = True
        self.assertFalse(WB.alive(session))
        session.close()

    def test_nothing_is_attached_while_the_sign_in_page_shows(self):
        chrome = FakeChrome([[LOGIN]])
        self.assertEqual(self.refusal(self.start, chrome, 0.001).code, "SIGN_IN_TIMED_OUT")
        self.assertEqual(chrome.tabs, [])
        self.assertTrue(chrome.closed)

    def test_a_workday_address_that_still_wants_a_sign_in_keeps_waiting(self):
        chrome = FakeChrome([[PAGE]], signed_in=False)
        self.assertEqual(self.refusal(self.start, chrome, 0.001).code, "SIGN_IN_TIMED_OUT")
        self.assertTrue(chrome.tabs and all(t.closed for t in chrome.tabs))

    def test_another_worker_a_closed_window_or_a_failed_start_release_everything(self):
        wrong = FakeChrome([[PAGE]], worker="000$000009")
        self.assertEqual(self.refusal(self.start, wrong).code, "WORKER_MISMATCH")
        self.assertTrue(wrong.closed)
        for polls in ([[]], [[LOGIN], None]):
            gone = FakeChrome(polls)
            self.assertEqual(self.refusal(self.start, gone).code, "SIGN_IN_CANCELLED")
            self.assertTrue(gone.closed)
        with patch.object(WB.Chrome, "launch", side_effect=WB.BrowserError("no")):
            self.assertEqual(self.refusal(WB.Session, OWN).code, "BROWSER_NOT_STARTED")
        with WB.own_profile():
            pass

    def test_a_signed_out_session_says_to_start_again(self):
        error = self.refusal(WB.open_calendar, FakeTab(FakeChrome([[LOGIN]], signed_in=False)), OWN)
        self.assertEqual(error.code, "SIGN_IN_REQUIRED")
        self.assertIn("session start", error.remedy)

    def cli(self, *args):
        self.root.mkdir(mode=0o700, exist_ok=True)
        account = self.root / "account.json"
        account.write_text(json.dumps(OWN), encoding="utf-8")
        account.chmod(0o600)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(WB.Chrome, "launch", side_effect=AssertionError("no launch")), patch.object(WB.Chrome, "connect", side_effect=AssertionError("no connection")):
            code = WB.main([*args, "--account", str(account)])
        return code, out.getvalue(), err.getvalue()

    def test_commands_need_a_session_and_start_no_chrome_themselves(self):
        code, out, err = self.cli("overview", "--from", "2026-10-26", "--to", "2026-11-09")
        self.assertEqual((code, out, json.loads(err)["code"]), (2, "", "SESSION_REQUIRED"))

    def test_check_reports_the_profile_without_starting_chrome(self):
        code, out, err = self.cli("check")
        self.assertEqual((code, err, json.loads(out)), (0, "", {"status": "ok", "account": "valid", "browser": "own", "profile_exists": False}))

    def test_the_command_line_holds_longer_for_the_own_profile(self):
        seen = []
        with patch.object(WB, "serve", lambda account, file, idle, make_session=None: seen.append(idle) or 0):
            self.assertEqual(self.cli("session", "start")[0], 0)
            self.assertEqual(self.cli("session", "start", "--idle-minutes", "5")[0], 0)
            self.assertEqual(self.cli("session", "start", "--sign-in-minutes", "90")[0], 2)
        self.assertEqual(seen, [60, 5])


if __name__ == "__main__":
    unittest.main()
