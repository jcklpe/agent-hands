#!/usr/bin/env python3
"""Offline checks for literal configuration, account validation and the local check."""
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import canvas_auth as support

TOKEN = "synthetic-canvas-token-7f3a"
TODAY = datetime.date(2026, 10, 29)


def account_entry(**changes):
    entry = {"alias": "example", "base_url": "https://example.instructure.com", "user_id": "1001", "token_env": "CANVAS_TOKEN_EXAMPLE", "token_expires": "2027-01-31", "courses": ["123"]}
    entry.update(changes)
    return {key: value for key, value in entry.items() if value is not None}


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = self.root / ".env"
        environment = patch.dict(os.environ, {"CANVAS_CONFIG_DIR": str(self.root)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(support._file_settings.clear)

    def write_env(self, text, mode=0o600):
        self.env.write_text(text)
        self.env.chmod(mode)

    def write_accounts(self, *entries):
        (self.root / "canvas-accounts.json").write_text(json.dumps({"accounts": list(entries)}))

    def run_main(self, *argv, today=TODAY):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = support.main(list(argv), today=today)
        return code, out.getvalue(), err.getvalue()

    def assert_kind(self, kind, function, *args):
        with self.assertRaises(support.CanvasError) as raised:
            function(*args)
        self.assertEqual(raised.exception.kind, kind, str(raised.exception))
        return raised.exception

    def test_values_are_literal_and_exported_values_win(self):
        sentinel = self.root / "must-not-exist"
        self.write_env(f'CANVAS_TOKEN_EXAMPLE="$(touch {sentinel})"\nexport CANVAS_OTHER=\'quoted value\'\nCANVAS_OVERRIDE=from-file\nCANVAS_EMPTY=\n')
        os.environ["CANVAS_OVERRIDE"] = "from-environment"
        support.load_env()
        self.assertEqual(support.setting("CANVAS_TOKEN_EXAMPLE"), f"$(touch {sentinel})")
        self.assertFalse(sentinel.exists())
        self.assertEqual(support.setting("CANVAS_OTHER"), "quoted value")
        self.assertEqual(support.setting("CANVAS_OVERRIDE"), "from-environment")
        self.assertIsNone(support.setting("CANVAS_EMPTY"))

    def test_selected_locations_must_exist(self):
        os.environ["CANVAS_ENV_FILE"] = str(self.root / "missing.env")
        self.assert_kind("config_missing", support.load_env)
        del os.environ["CANVAS_ENV_FILE"]
        os.environ["CANVAS_CONFIG_DIR"] = str(self.root / "missing-dir")
        self.assert_kind("config_missing", support.load_env)

    def test_env_file_selects_its_own_directory_for_accounts(self):
        other = self.root / "elsewhere"
        other.mkdir()
        (other / "custom.env").write_text(f"CANVAS_TOKEN_EXAMPLE={TOKEN}\n")
        (other / "canvas-accounts.json").write_text(json.dumps({"accounts": [account_entry()]}))
        os.environ["CANVAS_ENV_FILE"] = str(other / "custom.env")
        support.load_env()
        self.assertEqual(support.account("example").base_url, "https://example.instructure.com")

    def test_env_file_cannot_redirect_itself_or_carry_other_keys(self):
        for line in ("PATH=sensitive-placeholder", "CANVAS_ENV_FILE=sensitive-placeholder", "CANVAS_CONFIG_DIR=sensitive-placeholder", "CANVAS_BASE_URL=sensitive-placeholder", "canvas_token=sensitive-placeholder", "CANVAS_TOKEN sensitive-placeholder", 'CANVAS_TOKEN="sensitive-placeholder'):
            with self.subTest(line=line):
                self.write_env(line + "\n")
                error = self.assert_kind("config_invalid", support.load_env)
                self.assertNotIn("sensitive-placeholder", str(error))

    def test_base_url_is_normalised_to_an_https_origin(self):
        for value, expected in (("https://Example.Instructure.com/", "https://example.instructure.com"), ("https://canvas.example.edu:8443", "https://canvas.example.edu:8443"), ("https://canvas.example.edu:443", "https://canvas.example.edu")):
            self.assertEqual(support.normalize_origin(value), expected)
        for value in ("http://example.instructure.com", "https://user@example.instructure.com", "https://user:pw@example.instructure.com", "https://example.instructure.com/courses", "https://example.instructure.com/?a=1", "https://example.instructure.com/#x", "https://", "ftp://example.instructure.com", " https://example.instructure.com", "https://exa mple.com", "https://example.com:0", "https://example.com:99999", "https://exämple.com", "https://example.com\\@evil.com", "https://-bad.example.com", None, 7):
            with self.subTest(value=value):
                self.assert_kind("base_url_invalid", support.normalize_origin, value)

    def test_accounts_are_validated_strictly(self):
        good = support.Account("example", "https://example.instructure.com", "1001", "CANVAS_TOKEN_EXAMPLE", datetime.date(2027, 1, 31), ("123", "456"))
        self.write_accounts(account_entry(courses=["123", 456]))
        self.assertEqual(support.load_accounts(), [good])
        cases = {
            "duplicate alias": [account_entry(), account_entry()],
            "path alias": [account_entry(alias="../outside")],
            "unknown field": [account_entry(write=True)],
            "bad token_env": [account_entry(token_env="TOKEN")],
            "reserved token_env": [account_entry(token_env="CANVAS_ENV_FILE")],
            "bad user_id": [account_entry(user_id="abc")],
            "impossible date": [account_entry(token_expires="2027-02-30")],
            "compact date": [account_entry(token_expires="20270131")],
            "non-numeric course": [account_entry(courses=["abc"])],
            "duplicate course": [account_entry(courses=["123", "123"])],
            "courses not a list": [account_entry(courses="123")],
        }
        for label, entries in cases.items():
            with self.subTest(case=label):
                self.write_accounts(*entries)
                self.assert_kind("config_invalid", support.load_accounts)
        self.write_accounts(account_entry(base_url="http://example.instructure.com"))
        self.assert_kind("base_url_invalid", support.load_accounts)
        (self.root / "canvas-accounts.json").write_text("{not json")
        self.assert_kind("config_invalid", support.load_accounts)
        (self.root / "canvas-accounts.json").unlink()
        self.assert_kind("config_missing", support.load_accounts)

    def test_empty_user_id_and_expiry_are_allowed(self):
        self.write_accounts(account_entry(user_id="", token_expires=""))
        parsed = support.account("example")
        self.assertEqual((parsed.user_id, parsed.token_expires), ("", None))

    def test_check_is_offline_and_never_prints_the_token(self):
        self.write_env(f"CANVAS_TOKEN_EXAMPLE={TOKEN}\n")
        self.write_accounts(account_entry())
        with patch.object(support.UrllibTransport, "send", side_effect=AssertionError("network forbidden")):
            code, out, err = self.run_main("check", "example")
            self.assertEqual(code, 0, err)
            self.assertIn("No network request was made", out)
            accounts_code, accounts_out, _ = self.run_main("accounts")
        self.assertEqual(accounts_code, 0)
        self.assertIn("CANVAS_TOKEN_EXAMPLE", accounts_out)
        for text in (out, err, accounts_out):
            self.assertNotIn(TOKEN, text)

    def test_check_reports_each_local_failure(self):
        self.write_accounts(account_entry())
        self.write_env("CANVAS_OTHER=1\n")
        code, _, err = self.run_main("check", "example")
        self.assertEqual(code, 1)
        self.assertIn("[token_missing]", err)
        self.write_env(f"CANVAS_TOKEN_EXAMPLE={TOKEN}\n")
        code, _, err = self.run_main("check", "example", today=datetime.date(2027, 2, 1))
        self.assertIn("[token_expired_local]", err)
        code, out, _ = self.run_main("check", "example", today=datetime.date(2027, 1, 20))
        self.assertEqual(code, 0)
        self.assertIn("WARNING", out)
        self.write_env(f"CANVAS_TOKEN_EXAMPLE={TOKEN}\n", mode=0o644)
        if os.name != "nt":
            code, _, err = self.run_main("check", "example")
            self.assertIn("[config_insecure]", err)
        self.write_env(f"CANVAS_TOKEN_EXAMPLE={TOKEN}\n")
        with patch.object(support.zoneinfo, "ZoneInfo", side_effect=support.zoneinfo.ZoneInfoNotFoundError("missing")):
            code, _, err = self.run_main("check", "example")
        self.assertIn("[tz_data_missing]", err)
        code, _, err = self.run_main("check", "nobody")
        self.assertIn("Unknown Canvas account alias", err)
        self.assertNotIn(TOKEN, err)

    def test_help_needs_no_configuration(self):
        os.environ["CANVAS_CONFIG_DIR"] = str(self.root / "missing-dir")
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            support.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("whoami", out.getvalue())


if __name__ == "__main__":
    unittest.main()
