#!/usr/bin/env python3
"""Offline Slack checks; all account identifiers and content are synthetic."""
import contextlib
import io
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import slack_messages as slack
import slack_auth as support

class ConversationReadsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.responses = {}
        self.acct = {'alias': 'work', 'team_id': 'T1', 'user_id': 'U1'}
        for patcher in (patch.object(support, 'account', return_value=self.acct), patch.object(support, 'call', side_effect=self.call)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, acct, method, params=None, json_body=False):
        self.calls.append((method, params or {}))
        self.assertIn(method, ('auth.test', 'conversations.list', 'conversations.members', 'conversations.history', 'search.messages', 'chat.getPermalink'))
        response = self.responses.get(method, {'team_id': 'T1', 'user_id': 'U1'} if method == 'auth.test' else {})
        if isinstance(response, Exception):
            raise response
        return response(params or {}) if callable(response) else response

    def run_cli(self, command, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = slack.main([command, 'work', *args], load_config=False)
        return code, out.getvalue(), err.getvalue()

    def test_discovery_pages_and_filters_existing_dm_and_group(self):
        self.responses['conversations.list'] = lambda p: ({'channels': [{'id': 'D1', 'is_im': True, 'user': 'U2'}, {'id': 'D2', 'is_im': True, 'user': 'U3'}], 'response_metadata': {'next_cursor': 'next'}} if not p.get('cursor') else {'channels': [{'id': 'G1', 'is_mpim': True, 'name': 'group'}, {'id': 'C1', 'name': 'general'}]})
        self.responses['conversations.members'] = {'members': ['U1', 'U2']}
        code, out, err = self.run_cli('conversations', '--types', 'im,mpim', '--user', 'U2')
        self.assertEqual(code, 0, err)
        self.assertIn('DM with U2 | id: D1', out)
        self.assertIn('group DM group | id: G1', out)
        self.assertNotIn('D2', out)
        self.assertNotIn('#general', out)
        self.assertEqual(self.calls[1][1]['types'], 'im,mpim')
        self.assertEqual(self.calls[2][1]['cursor'], 'next')

    def test_discovery_refuses_partial_results(self):
        self.responses['conversations.list'] = {'channels': [], 'has_more': True}
        code, out, err = self.run_cli('conversations')
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertIn('without a cursor', err)

    def test_history_bounds_cursor_thread_metadata_and_end(self):
        self.responses['conversations.history'] = {'messages': [{'ts': '1700000001.000001', 'user': 'U2', 'text': 'hello', 'reply_count': 2}], 'has_more': True, 'response_metadata': {'next_cursor': 'older'}}
        code, out, err = self.run_cli('history', '--channel', 'D1', '--limit', '20', '--cursor', 'start', '--oldest', '1700000000', '--latest', '1800000000', '--inclusive')
        self.assertEqual(code, 0, err)
        self.assertIn('Next cursor: older', out)
        self.assertIn('replies: 2', out)
        self.assertEqual(self.calls[-1][1], {'channel': 'D1', 'limit': 20, 'cursor': 'start', 'oldest': '1700000000', 'latest': '1800000000', 'inclusive': 'true'})
        self.responses['conversations.history'] = {'messages': []}
        self.assertIn('End of accessible history', self.run_cli('history', '--channel', 'D1')[1])

    def test_history_refuses_missing_cursor(self):
        self.responses['conversations.history'] = {'messages': [{'text': 'hidden partial'}], 'has_more': True}
        code, out, err = self.run_cli('history', '--channel', 'D1')
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertIn('narrow the time range', err)

    def test_search_page_and_permalink(self):
        self.responses['search.messages'] = {'messages': {'total': 30, 'paging': {'pages': 3}, 'matches': [{'channel': {'id': 'D1', 'name': 'U2'}, 'ts': '1700000001.000001', 'user': 'U2', 'text': 'hello', 'permalink': 'https://example.slack.com/actual-link'}]}}
        code, out, err = self.run_cli('search', 'from:<@U2>', '--page', '2', '--limit', '10')
        self.assertEqual(code, 0, err)
        self.assertIn('page 2 of 3; total 30', out)
        self.assertIn('https://example.slack.com/actual-link', out)
        self.assertEqual(self.calls[-1][1], {'query': 'from:<@U2>', 'count': 10, 'page': 2, 'sort': 'timestamp', 'sort_dir': 'desc', 'highlight': 'false'})
        self.responses['chat.getPermalink'] = {'permalink': 'https://example.slack.com/actual-link'}
        self.assertEqual(self.run_cli('permalink', '--channel', 'D1', '--ts', '1700000001.000001')[1].strip(), 'https://example.slack.com/actual-link')

    def test_missing_scope_reported_once_without_writes(self):
        for command, method, args in [('search', 'search.messages', ['hello']), ('history', 'conversations.history', ['--channel', 'D1']), ('conversations', 'conversations.list', [])]:
            self.calls.clear()
            self.responses[method] = support.SlackError('missing_scope (needed: read-scope)')
            code, _, err = self.run_cli(command, *args)
            self.assertEqual(code, 1)
            self.assertIn('needed: read-scope', err)
            self.assertEqual(sum(m == method for m, _ in self.calls), 1)

    def test_identity_mismatch_blocks_content_reads(self):
        self.responses['auth.test'] = {'team_id': 'T2', 'user_id': 'U1'}
        self.assertEqual(self.run_cli('history', '--channel', 'D1')[0], 1)
        self.assertEqual([m for m, _ in self.calls], ['auth.test'])

    def test_argument_bounds_before_api_calls(self):
        for args in (['history', 'work', '--channel', 'D1', '--limit', '0'], ['search', 'work', 'hello', '--page', '101'], ['conversations', 'work', '--types', 'invalid']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                slack.main(args)
        self.assertEqual(self.calls, [])

if __name__ == "__main__":
    unittest.main()
