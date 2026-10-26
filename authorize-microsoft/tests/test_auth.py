"""Offline token-cache and authority checks; MSAL itself is not invoked."""
import importlib.util
from pathlib import Path
import os
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

with patch.dict(sys.modules, msal=types.ModuleType("msal")):
    spec = importlib.util.spec_from_file_location("microsoft_auth", Path(__file__).resolve().parents[1] / "scripts/auth.py")
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)


class AuthTests(unittest.TestCase):
    def test_authority_rejects_untrusted_destinations(self):
        self.assertEqual(auth.authority_for("organizations"), "https://login.microsoftonline.com/organizations")
        self.assertEqual(auth.authority_for("https://login.microsoftonline.com/example.com"), "https://login.microsoftonline.com/example.com")
        for value in ("https://attacker.invalid", "../tenant", "tenant?next=elsewhere", "login.microsoftonline.com@evil/path"):
            with self.assertRaises(ValueError):
                auth.authority_for(value)

    def test_private_staging_and_failed_replace(self):
        cache = types.SimpleNamespace(has_state_changed=True, serialize=lambda: '{"synthetic":true}')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cache.json"
            target.write_text("previous")
            replace = os.replace
            def verify_mode(source, destination):
                self.assertEqual(stat.S_IMODE(os.stat(source).st_mode), 0o600)
                return replace(source, destination)
            with patch.object(auth.os, "replace", side_effect=verify_mode):
                auth.save_cache(str(target), cache)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with patch.object(auth.os, "replace", side_effect=OSError("synthetic failure")):
                with self.assertRaises(OSError):
                    auth.save_cache(str(target), cache)
            self.assertEqual(target.read_text(), '{"synthetic":true}\n')
            self.assertEqual(list(Path(directory).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
