"""Offline contract checks for lookup precedence, deduplication, and incomplete pagination."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('contacts', Path(__file__).parents[1] / 'scripts/contacts.py')
contacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contacts)


def person(name, email):
    return {'names': [{'displayName': name}], 'emailAddresses': [{'value': email}]}


class LookupTests(unittest.TestCase):
    def test_saved_contacts_page_and_deduplicate_without_fallback(self):
        pages = [{'connections': [person('Taylor', 'taylor@example.com')], 'nextPageToken': 'page-two'},
                 {'connections': [person('Taylor Duplicate', 'TAYLOR@example.com'), person('Another Taylor', 'second@example.com')]}]
        with patch.object(contacts, 'api_get', side_effect=pages) as api, contextlib.redirect_stdout(io.StringIO()) as output:
            contacts.resolve('synthetic-access', 'taylor')
        self.assertEqual(len(json.loads(output.getvalue())), 2)
        self.assertTrue(all(call.args[0] == contacts.CONNECTIONS_URL for call in api.call_args_list))
        self.assertEqual(api.call_args_list[1].args[2]['pageToken'], 'page-two')

    def test_other_contacts_are_fallback_only(self):
        pages = [{'connections': [person('Someone Else', 'else@example.com')]},
                 {'results': [{'person': person('Taylor', 'taylor@example.com')}]}]
        with patch.object(contacts, 'api_get', side_effect=pages) as api, contextlib.redirect_stdout(io.StringIO()) as output:
            contacts.resolve('synthetic-access', 'Taylor')
        self.assertEqual(json.loads(output.getvalue()), [{'name': 'Taylor', 'email': 'taylor@example.com'}])
        self.assertEqual(api.call_args.args[0], contacts.OTHER_SEARCH_URL)
        self.assertEqual(api.call_args.args[2]['pageSize'], '20')

    def test_incomplete_retrieval_emits_no_candidates(self):
        for failure in [RuntimeError('synthetic retrieval failure'), {'connections': [], 'nextPageToken': 'same-page'}]:
            pages = [{'connections': [person('Taylor', 'taylor@example.com')], 'nextPageToken': 'same-page'}, failure]
            with patch.object(contacts, 'api_get', side_effect=pages), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(RuntimeError):
                    contacts.resolve('synthetic-access', 'Taylor')
            self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
