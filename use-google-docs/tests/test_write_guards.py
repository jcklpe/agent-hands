"""Offline request-boundary checks, including a changed document before body replacement."""
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
DOCUMENT = {'title': 'Synthetic document', 'revisionId': 'revision-one', 'body': {'content': [
    {'startIndex': 1, 'endIndex': 15, 'paragraph': {'elements': [
        {'startIndex': 1, 'endIndex': 15, 'textRun': {'content': 'Original text\n'}}
    ]}}
]}}


class WriteTests(unittest.TestCase):
    def invoke(self, arguments, versions):
        args = docs.build_parser().parse_args(arguments)
        with patch.object(docs, 'access_token', return_value='synthetic-access'), patch.object(docs, 'get_document', side_effect=versions), patch.object(docs, 'api_json', return_value={'id': 'synthetic-comment'}) as api, contextlib.redirect_stdout(io.StringIO()):
            try:
                result = args.func(args)
            except Exception:
                api.assert_not_called()
                raise
        return result, api

    def test_all_writes_default_to_preview(self):
        for arguments in [
            ['replace-once', '--old', 'Original text', '--new', 'Changed text'],
            ['set-body', '--new', '# New body'],
            ['comment', '--quote', 'Original text', '--body', 'A comment'],
        ]:
            _, api = self.invoke(arguments + ['--document-id', 'synthetic-doc'], [DOCUMENT])
            api.assert_not_called()

    def test_body_refuses_concurrent_change(self):
        changed = copy.deepcopy(DOCUMENT)
        changed['revisionId'] = 'revision-two'
        with patch.object(docs, 'api_json') as api:
            with self.assertRaisesRegex(ValueError, 'changed after the body preview'):
                self.invoke(['set-body', '--document-id', 'synthetic-doc', '--new', '# New body', '--execute'], [DOCUMENT, changed])
            api.assert_not_called()

    def test_body_uses_required_revision(self):
        _, api = self.invoke(['set-body', '--document-id', 'synthetic-doc', '--new', '# New body', '--execute'], [DOCUMENT, DOCUMENT])
        self.assertEqual(api.call_args.args[3]['writeControl'], {'requiredRevisionId': 'revision-one'})

    def test_comment_rechecks_live_quote_before_posting(self):
        changed = copy.deepcopy(DOCUMENT)
        changed['body']['content'][0]['paragraph']['elements'][0]['textRun']['content'] = 'Different text\n'
        with self.assertRaisesRegex(ValueError, 'found 0'):
            self.invoke(['comment', '--document-id', 'synthetic-doc', '--quote', 'Original text', '--body', 'A comment', '--execute'], [DOCUMENT, changed])


if __name__ == '__main__':
    unittest.main()
