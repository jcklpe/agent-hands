"""Exercise bounded Drive pagination through the real Bash operations, without credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOKEN = "opaque+/=&?% token '$()'"
HARNESS = r'''
set -eu
source "$TEST_ROOT/setup-google-services/scripts/client.sh"
source "$TEST_ROOT/use-google-drive/scripts/operations.sh"
_drive_page_size() { printf 7; }
_google_get_url() { "$TEST_PYTHON" "$TEST_FIXTURE" "$@"; }
"_drive_$1" "${@:2}"
'''
FIXTURE = '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['TEST_CALLS']).open('a') as log:
    log.write(json.dumps(args) + '\\n')
params = dict(value.split('=', 1) for value in args[3::2])
mode = os.environ.get('TEST_MODE', 'normal')
if mode == 'transport':
    print('partial response')
    sys.exit(22)
if mode == 'response':
    print(os.environ['TEST_RESPONSE'])
elif params.get('pageToken') == 'expired':
    print(json.dumps({'error': {'code': 400, 'message': 'Invalid page token'}}))
elif params.get('pageToken'):
    print(json.dumps({'files': [{'id': 'second', 'name': 'Second page'}]}))
else:
    print(json.dumps({'files': [{'id': 'first', 'name': 'First page'}], 'nextPageToken': os.environ['TEST_TOKEN']}))
'''


class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.path = Path(self.work.name)
        self.fixture = self.path / "fixture.py"
        self.fixture.write_text(FIXTURE)
        self.calls = self.path / "calls.jsonl"

    def run_page(self, command, *options, mode="normal", response="", target=None):
        self.calls.write_text("")
        env = dict(os.environ, TEST_ROOT=str(ROOT), TEST_PYTHON=sys.executable,
                   TEST_FIXTURE=str(self.fixture), TEST_CALLS=str(self.calls),
                   TEST_TOKEN=TOKEN, TEST_MODE=mode, TEST_RESPONSE=response,
                   TMPDIR=str(self.path))
        target = target or ("Project 'notes'\\archive" if command == "search" else "folder-one")
        result = subprocess.run(["/bin/bash", "-c", HARNESS, "test", command,
                                 "example", target, *options], env=env, text=True, capture_output=True)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(list(self.path.glob("google-drive.*")), "temporary response directory leaked")
        return result, calls

    def params(self, call):
        self.assertEqual(call[:2], ["example", "https://www.googleapis.com/drive/v3/files"])
        self.assertTrue(all(flag == "--data-urlencode" for flag in call[2::2]))
        return dict(value.split("=", 1) for value in call[3::2])

    def test_first_page_is_one_request_and_preserves_json(self):
        for command in ("search", "list"):
            with self.subTest(command=command):
                result, calls = self.run_page(command, "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(calls), 1)
                params = self.params(calls[0])
                self.assertNotIn("pageToken", params)
                self.assertEqual(params["pageSize"], "7")
                self.assertNotIn("orderBy", params, "fullText search does not support explicit sorting")
                self.assertEqual(params["supportsAllDrives"], "true")
                self.assertEqual(params["includeItemsFromAllDrives"], "true")
                self.assertIn("incompleteSearch", params["fields"])
                self.assertEqual(json.loads(result.stdout)["nextPageToken"], TOKEN)

    def test_second_page_changes_only_the_encoded_token_parameter(self):
        for command in ("search", "list"):
            with self.subTest(command=command):
                first, calls = self.run_page(command, "--json")
                baseline = self.params(calls[0])
                token = json.loads(first.stdout)["nextPageToken"]
                second, calls = self.run_page(command, "--page-token", token, "--json")
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(len(calls), 1)
                continued = self.params(calls[0])
                self.assertEqual(continued.pop("pageToken"), TOKEN)
                self.assertEqual(continued, baseline)
                self.assertEqual(json.loads(second.stdout), {"files": [{"id": "second", "name": "Second page"}]})

    def test_empty_page_with_token_is_not_the_end(self):
        response = json.dumps({"files": [], "nextPageToken": TOKEN})
        for command in ("search", "list"):
            result, calls = self.run_page(command, mode="response", response=response)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls), 1)
            self.assertIn("More results exist", result.stderr)
            self.assertIn("--page-token", result.stderr)
            result, _ = self.run_page(command, "--json", mode="response", response=response)
            self.assertEqual(json.loads(result.stdout), json.loads(response))

    def test_final_empty_page_has_no_continuation_warning(self):
        for command in ("search", "list"):
            result, calls = self.run_page(command, mode="response", response='{"files":[]}')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_incomplete_search_is_visible_without_a_token(self):
        response = '{"files":[],"incompleteSearch":true}'
        for command in ("search", "list"):
            result, _ = self.run_page(command, mode="response", response=response)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("incomplete search", result.stderr)
            result, _ = self.run_page(command, "--json", mode="response", response=response)
            self.assertTrue(json.loads(result.stdout)["incompleteSearch"])

    def test_expired_token_fails_without_output_or_restart(self):
        for command in ("search", "list"):
            result, calls = self.run_page(command, "--page-token", "expired", "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("page is not verified", result.stderr)

    def test_transport_failure_never_publishes_partial_output(self):
        for command in ("search", "list"):
            result, calls = self.run_page(command, "--page-token", TOKEN, "--json", mode="transport")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result.stdout, "")

    def test_malformed_responses_are_not_successful_empty_results(self):
        for response in ('not json', '{}', '[]', '{"files":{}}',
                         '{"files":[],"nextPageToken":42}', '{"files":[],"incompleteSearch":"false"}'):
            for command in ("search", "list"):
                with self.subTest(command=command, response=response):
                    result, calls = self.run_page(command, "--json", mode="response", response=response)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(result.stdout, "")

    def test_invalid_options_stop_before_request(self):
        for options in (("--page-token",), ("--page-token", ""), ("--unknown",),
                        ("--page-token", "one", "--page-token", "two")):
            for command in ("search", "list"):
                with self.subTest(command=command, options=options):
                    result, calls = self.run_page(command, *options)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
