"""Offline checks for literal configuration and isolation from the caller's cwd."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import slack_auth as support


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = self.root / '.env'
        environment = patch.dict(os.environ, {'SLACK_ENV_FILE': str(self.env)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_literal_values_precedence_and_relative_path(self):
        sentinel = self.root / 'must-not-exist'
        value = '$(touch ' + str(sentinel) + ')'
        self.env.write_text('SLACK_TOKEN_EXAMPLE="' + value + '"\nSLACK_ACCOUNTS_PATH=accounts.json\nSLACK_TOKEN_OVERRIDE=from-file\n')
        os.environ['SLACK_TOKEN_OVERRIDE'] = 'from-environment'
        support.load_env()
        self.assertEqual(os.environ['SLACK_TOKEN_EXAMPLE'], value)
        self.assertFalse(sentinel.exists())
        self.assertEqual(os.environ['SLACK_TOKEN_OVERRIDE'], 'from-environment')
        self.assertEqual(support.accounts_path(), str(self.root / 'accounts.json'))

    def test_missing_selected_file_is_an_error(self):
        with self.assertRaisesRegex(support.SlackError, 'does not exist'):
            support.load_env()

    def test_rejects_unrelated_keys_and_endpoint_override_without_echoing_values(self):
        for key in ('PATH', 'SLACK_API_BASE', 'SLACK_ENV_FILE'):
            self.env.write_text(key + '=sensitive-placeholder\n')
            with self.assertRaises(support.SlackError) as raised:
                support.load_env()
            self.assertNotIn('sensitive-placeholder', str(raised.exception))

    def test_duplicate_and_path_aliases_are_rejected(self):
        config = self.root / 'slack-accounts.json'
        for aliases in (['../outside'], ['example', 'example']):
            config.write_text(json.dumps({'accounts': [{'alias': alias} for alias in aliases]}))
            with self.assertRaises(support.SlackError):
                support.load_accounts()

    def test_local_check_does_not_call_network(self):
        self.env.write_text('SLACK_TOKEN_EXAMPLE=synthetic\n')
        (self.root / 'slack-accounts.json').write_text(json.dumps({'accounts': [{'alias': 'example', 'team_id': 'T1', 'user_id': 'U1', 'token_env': 'SLACK_TOKEN_EXAMPLE'}]}))
        with patch.object(support, 'call', side_effect=AssertionError('network forbidden')):
            self.assertEqual(support.main(['check', 'example']), 0)


if __name__ == '__main__':
    unittest.main()
