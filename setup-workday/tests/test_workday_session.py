"""The one-connection session over its owner-only socket, with a stand-in for Chrome; no browser, network or real timesheets."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workday_browser as WB  # noqa: E402
from test_workday_browser import ACCOUNT, TARGET, build  # noqa: E402


class FakeChrome:
    def __init__(self):
        self.up = True

    def call(self, method, params=None, session=None, timeout=30):
        if not self.up:
            raise WB.BrowserError("Chrome closed the DevTools connection")
        return {}


class FakeSession:
    instances = []

    def __init__(self, account):
        self.chrome, self.reads, self.closed = FakeChrome(), 0, False
        FakeSession.instances.append(self)

    def read(self, binding):
        self.reads += 1
        snapshot, result, observations = build()
        self.result, self.observations = result, observations
        return snapshot

    def close(self):
        self.closed = True


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir="/tmp")
        self.root = Path(os.path.realpath(self.dir))
        env = patch.dict(os.environ, {WB.STATE_ENV: str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.account = self.root / "account.json"
        self.account.write_text(json.dumps(ACCOUNT), encoding="utf-8")
        self.account.chmod(0o600)
        self.target = self.root / "target.json"
        self.target.write_text(json.dumps(TARGET), encoding="utf-8")
        FakeSession.instances = []
        no_direct = patch.object(WB, "Session", side_effect=AssertionError("must go through the running session"))
        no_direct.start()
        self.addCleanup(no_direct.stop)

    def tearDown(self):
        for path in sorted(self.root.rglob("*"), reverse=True):
            path.unlink() if not path.is_dir() else path.rmdir()
        self.root.rmdir()

    def start(self, idle=5):
        ready = threading.Event()
        self.ended = io.StringIO()

        def run():
            with redirect_stdout(self.ended):
                WB.serve(dict(ACCOUNT), str(self.account.resolve()), idle, make_session=FakeSession, ready=ready.set)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(5))
        return thread

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = WB.main([*args, "--account", str(self.account)])
        return code, out.getvalue(), err.getvalue()

    def test_commands_share_one_connection_until_stopped(self):
        thread = self.start()
        sock = WB.session_path()
        self.assertEqual(stat.S_IMODE(sock.lstat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(sock.parent.lstat().st_mode), 0o700)
        snap = self.root / "week.json"
        for _ in range(2):
            code, out, err = self.cli("read", "--target", str(self.target), "--out", str(snap))
            self.assertEqual(code, 0, err)
            self.assertNotIn("snapshot", json.loads(out))
        self.assertEqual(len(FakeSession.instances), 1)
        self.assertEqual(FakeSession.instances[0].reads, 2)
        self.assertEqual(json.loads(snap.read_text())["status"], "approved")
        self.assertEqual(json.loads(self.cli("session", "status")[1])["status"], "running")
        self.assertEqual(self.cli("session", "stop")[0], 0)
        thread.join(5)
        self.assertFalse(sock.exists())
        self.assertTrue(FakeSession.instances[0].closed)
        self.assertIn('"reason": "stopped"', self.ended.getvalue())

    def test_without_a_session_status_says_so(self):
        code, out, _ = self.cli("session", "status")
        self.assertEqual((code, json.loads(out)["status"]), (0, "not-running"))

    def test_another_account_file_is_refused(self):
        thread = self.start()
        other = self.root / "other.json"
        other.write_text(json.dumps(ACCOUNT), encoding="utf-8")
        other.chmod(0o600)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = WB.main(["read", "--target", str(self.target), "--account", str(other)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err.getvalue())["code"], "SESSION_ACCOUNT_MISMATCH")
        self.cli("session", "stop")
        thread.join(5)

    def test_idle_sessions_end_by_themselves(self):
        thread = self.start(idle=0.02)
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertFalse(WB.session_path().exists())
        self.assertIn('"reason": "idle"', self.ended.getvalue())

    def test_a_closed_chrome_ends_the_session(self):
        thread = self.start()
        FakeSession.instances[0].chrome.up = False
        self.cli("session", "status")
        thread.join(5)
        self.assertIn('"reason": "chrome-disconnected"', self.ended.getvalue())

    def test_one_session_at_a_time_and_stale_sockets_are_replaced(self):
        thread = self.start()
        with self.assertRaises(WB.Refusal) as caught:
            with redirect_stdout(io.StringIO()):
                WB.serve(dict(ACCOUNT), str(self.account.resolve()), 5, make_session=FakeSession)
        self.assertEqual(caught.exception.code, "SESSION_RUNNING")
        self.cli("session", "stop")
        thread.join(5)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(WB.session_path()))
        stale.close()
        thread = self.start()
        self.assertEqual(json.loads(self.cli("session", "status")[1])["status"], "running")
        self.cli("session", "stop")
        thread.join(5)


if __name__ == "__main__":
    unittest.main()
