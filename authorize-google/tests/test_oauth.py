"""Offline checks for sensitive token storage and trusted OAuth destinations."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('oauth', Path(__file__).parents[1] / 'scripts/oauth.py')
oauth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oauth)


class OAuthTests(unittest.TestCase):
    def test_atomic_private_token_and_failure_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'token.json'
            path.write_text('{"previous": true}')
            replace = os.replace
            def inspect(source, destination):
                self.assertEqual(stat.S_IMODE(os.stat(source).st_mode), 0o600)
                replace(source, destination)
            mask = os.umask(0)
            try:
                with patch.object(oauth.os, 'replace', side_effect=inspect):
                    oauth.write_token(path, {'access_token': 'synthetic-access'})
            finally:
                os.umask(mask)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            previous = path.read_bytes()
            with patch.object(oauth.os, 'replace', side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):
                    oauth.write_token(path, {'access_token': 'synthetic-replacement'})
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(Path(directory).glob('.google-token-*')), [])

    def test_refresh_retains_refresh_token(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'token.json'
            oauth.write_token(token, {'refresh_token': 'synthetic-refresh'})
            with patch.object(oauth, 'load_credentials', return_value={'client_id': 'synthetic-client', 'token_uri': 'https://oauth2.googleapis.com/token'}), patch.object(oauth, 'post_form', return_value={'access_token': 'synthetic-access', 'expires_in': 3600}):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    oauth.access_token('unused', token)
            self.assertEqual(output.getvalue(), 'synthetic-access\n')
            self.assertEqual(json.loads(token.read_text())['refresh_token'], 'synthetic-refresh')

    def test_non_google_token_endpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = Path(directory) / 'credentials.json'
            credentials.write_text(json.dumps({'client_id': 'synthetic-client', 'auth_uri': 'https://accounts.google.com/o/oauth2/auth', 'token_uri': 'https://example.com/collect'}))
            with self.assertRaisesRegex(ValueError, 'Unexpected Google token endpoint'):
                oauth.load_credentials(credentials)


if __name__ == '__main__':
    unittest.main()
