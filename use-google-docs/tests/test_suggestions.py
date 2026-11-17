"""Offline native-suggestion write guards and independent model verification."""
import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('docs', Path(__file__).parents[1] / 'scripts/docs.py')
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def document(parts):
    elements = []
    index = 1
    for text, metadata in parts:
        end = index + docs.utf16_length(text)
        elements.append({'startIndex': index, 'endIndex': end, 'textRun': {'content': text, **metadata}})
        index = end
    return {'revisionId': 'rev1', 'tabs': [{'tabProperties': {'tabId': 't1'}, 'documentTab': {'body': {'content': [{'startIndex': 1, 'endIndex': index, 'paragraph': {'elements': elements}}]}}}]}

BEFORE = document([('Before old after\n', {})])
SAVED = document([('Before ', {}), ('old', {'suggestedDeletionIds': ['s1']}), ('new', {'suggestedInsertionIds': ['s1']}), (' after\n', {})])
RESPONSE = {'commentUpdateState': 'ALL_SAVED', 'suggestionResponses': [{'createdSuggestionIds': ['s1']}]}


class Suggestions(unittest.TestCase):
    def invoke(self, versions, extra=(), response=None, old='old', new='new'):
        args = docs.build_parser().parse_args(['replace-once', '--document-id', 'synthetic', '--old', old, '--new', new, '--suggest', *extra])
        with patch.object(docs, 'access_token', return_value='synthetic'), patch.object(docs, 'get_document', side_effect=versions), patch.object(docs, 'api_json', return_value=RESPONSE if response is None else response) as api, contextlib.redirect_stdout(io.StringIO()) as output:
            self.api = api
            try:
                result = args.func(args)
            finally:
                self.output = output.getvalue()
        return result

    def test_preview_does_not_post(self):
        self.assertEqual(self.invoke([BEFORE]), 0)
        self.api.assert_not_called()
        self.assertIn('Mode: SUGGEST', self.output)

    def test_native_mode_guard_and_readback(self):
        self.assertEqual(self.invoke([BEFORE, BEFORE, SAVED], ['--execute']), 0)
        payload = self.api.call_args.args[3]
        self.assertEqual(payload['writeControl'], {'requiredRevisionId': 'rev1', 'writeMode': 'SUGGEST'})
        self.assertEqual(payload['requests'][0]['replaceAllText']['tabsCriteria'], {'tabIds': ['t1']})
        self.assertIn('Verified pending suggestion', self.output)
        self.api.assert_called_once()

    def test_revision_drift_no_post(self):
        changed = copy.deepcopy(BEFORE); changed['revisionId'] = 'rev2'
        with self.assertRaisesRegex(ValueError, 'changed after'):
            self.invoke([BEFORE, changed], ['--execute'])
        self.api.assert_not_called()

    def test_overlap_no_post(self):
        pending = document([('Before old after\n', {'suggestedInsertionIds': ['existing']})])
        with self.assertRaisesRegex(ValueError, 'existing suggestion'):
            self.invoke([pending], ['--execute'])
        self.api.assert_not_called()

    def test_duplicate_no_post(self):
        with self.assertRaisesRegex(ValueError, 'found 2'):
            self.invoke([document([('old old\n', {})])], ['--execute'])
        self.api.assert_not_called()

    def test_partial_and_missing_ids_never_retry(self):
        for response in [{'commentUpdateState': 'ALL_FAILED_UNKNOWN_REASON'}, {'commentUpdateState': 'ALL_SAVED'}]:
            with self.assertRaisesRegex(RuntimeError, 'PARTIAL'):
                self.invoke([BEFORE, BEFORE], ['--execute'], response)
            self.api.assert_called_once()

    def test_direct_edit_readback_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'PARTIAL'):
            self.invoke([BEFORE, BEFORE, document([('Before new after\n', {})])], ['--execute'])
        self.api.assert_called_once()

    def test_wrong_text_and_read_failure_do_not_retry(self):
        for saved in [document([('Before ', {}), ('old', {'suggestedDeletionIds': ['s1']}), ('WRONG', {'suggestedInsertionIds': ['s1']}), (' after\n', {})]), RuntimeError('read failed')]:
            with self.assertRaisesRegex(RuntimeError, 'PARTIAL'):
                self.invoke([BEFORE, BEFORE, saved], ['--execute'])
            self.api.assert_called_once()

    def test_unsupported_format_and_multiline_no_post(self):
        for extra, new in [(['--markdown'], 'new'), (['--link', 'new=https://example.com'], 'new'), ([], 'new\nline'), ([], '')]:
            with self.assertRaisesRegex(ValueError, 'single-paragraph'):
                self.invoke([], extra + ['--execute'], new=new)
            self.api.assert_not_called()

    def test_non_bmp_and_existing_unrelated_suggestion(self):
        before = document([('😀 ', {'suggestedInsertionIds': ['other']}), ('old\n', {})])
        saved = document([('😀 ', {'suggestedInsertionIds': ['other']}), ('old', {'suggestedDeletionIds': ['s1']}), ('new', {'suggestedInsertionIds': ['s1']}), ('\n', {})])
        self.assertEqual(self.invoke([before, before, saved], ['--execute']), 0)

    def test_chip_gap_no_post(self):
        before = document([('ol', {}), ('d\n', {})])
        es = before['tabs'][0]['documentTab']['body']['content'][0]['paragraph']['elements']
        es[1]['startIndex'] += 1; es[1]['endIndex'] += 1
        with self.assertRaisesRegex(ValueError, 'native element'):
            self.invoke([before], ['--execute'])
        self.api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
