"""Exercise real Gmail command paths with synthetic curl responses and no account access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
API = "https://gmail.googleapis.com/gmail/v1/users/me"
LABELS = {"labels": [{"id": "INBOX", "name": "INBOX", "type": "system"}, {"id": "SPAM", "name": "SPAM", "type": "system"}, {"id": "Label_1", "name": "Receipts", "type": "user"}]}
MESSAGE = {"id": "m1", "threadId": "t1", "labelIds": ["INBOX"], "payload": {"headers": [{"name": "Subject", "value": "Synthetic message"}]}}


def reply(path, body, status=200, method="GET"):
    return {"path": path, "body": body, "status": status, "method": method}


def limited(path, status=403, reason="rateLimitExceeded"):
    return reply(path, {"error": {"message": "Synthetic quota exceeded", "errors": [{"reason": reason}]}}, status)


CURL = r'''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_WORK"])
args = iter(sys.argv[1:]); out = None; method = "GET"; query = []; url = None; body = None; fail_http = False
for arg in args:
    if arg == "-o": out = next(args)
    elif arg == "-fsS": fail_http = True
    elif arg == "-X": method = next(args)
    elif arg in ("-H", "-w"): next(args)
    elif arg == "--data-urlencode": query.append(next(args))
    elif arg == "--data-binary": body = next(args)
    elif arg.startswith("https://"): url = arg
calls = root / "calls"
previous = calls.read_text().splitlines()
with calls.open("a") as stream:
    stream.write(json.dumps({"method": method, "url": url, "query": query, "body": body}) + "\n")
sequence = json.loads((root / "responses.json").read_text())
if len(previous) >= len(sequence): raise SystemExit("Unexpected extra request")
response = sequence[len(previous)]
if url != "https://gmail.googleapis.com/gmail/v1/users/me" + response["path"] or method != response["method"]:
    raise SystemExit("Unexpected request target or method")
if response.get("exit"):
    print("Synthetic transport failure", file=sys.stderr); sys.exit(response["exit"])
payload = response["body"]
payload = payload if isinstance(payload, str) else json.dumps(payload)
if out:
    pathlib.Path(out).write_text(payload)
    print(response["status"], end="")
elif fail_http and response["status"] >= 400:
    print("curl: synthetic HTTP failure", file=sys.stderr); sys.exit(22)
else:
    print(payload, end="")
'''

RUNNER = r'''
set -eu
source "$TEST_SKILL/../setup-google-services/scripts/client.sh"
source "$TEST_SKILL/scripts/operations.sh"
_google_access_token() { printf '%s' synthetic-token-never-print; }
curl() { "$TEST_PYTHON" "$TEST_WORK/curl.py" "$@"; }
sleep() { printf '%s\n' "$1" >> "$TEST_WORK/sleeps"; }
command="$1"; shift
case "$command" in
    get) _gmail_get example "$@" ;;
    mutation) _gmail_send "$@" ;;
    *) "_gmail_${command//-/_}" example "$@" ;;
esac
'''


class ReadRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "curl.py").write_text(CURL)
        (self.root / "run.sh").write_text(RUNNER)
        config = json.loads((SKILL.parent / "setup-google-services/google-accounts.example.json").read_text())
        for account in config["accounts"]:
            account["gmail"].update(enabled=True, write_enabled=True, filters_enabled=True)
        (self.root / "accounts.json").write_text(json.dumps(config))

    def run_command(self, responses, *args, cap="2"):
        (self.root / "responses.json").write_text(json.dumps(responses))
        (self.root / "calls").write_text("")
        (self.root / "sleeps").write_text("")
        env = dict(os.environ, TEST_SKILL=str(SKILL), TEST_WORK=str(self.root), TEST_PYTHON=sys.executable,
                   GOOGLE_PYTHON=sys.executable, GOOGLE_ACCOUNTS_PATH=str(self.root / "accounts.json"),
                   GOOGLE_GMAIL_AUDIT_LOG=str(self.root / "audit.jsonl"), GOOGLE_GMAIL_MAX_RETRIES=cap)
        result = subprocess.run(["/bin/bash", str(self.root / "run.sh"), *args], env=env, capture_output=True, text=True)
        self.calls = [json.loads(line) for line in (self.root / "calls").read_text().splitlines()]
        self.sleeps = (self.root / "sleeps").read_text().splitlines()
        self.assertNotIn("synthetic-token-never-print", result.stdout + result.stderr)
        return result

    def test_nonexport_read_routes_recover_without_changing_requests(self):
        cases = [
            (("labels", "--json"), "/labels", LABELS, []),
            (("filters", "--json"), "/settings/filters", {"filter": []}, []),
            (("list", "--query", "in:inbox", "--limit", "1", "--json"), "/messages", {"messages": [{"id": "m1"}]}, [reply("/messages/m1", MESSAGE)]),
            (("spam", "--limit", "1", "--json"), "/labels", LABELS, [reply("/messages", {"messages": [{"id": "m1"}]}), reply("/messages/m1", MESSAGE)]),
            (("archive", "--thread", "t1"), "/threads/t1", {"id": "t1", "messages": [MESSAGE]}, []),
        ]
        for args, path, body, tail in cases:
            with self.subTest(command=args[0]):
                result = self.run_command([limited(path), reply(path, body), *tail], *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.calls[0], self.calls[1])
                self.assertEqual(self.sleeps, ["2"])
                self.assertTrue(all(call["method"] == "GET" for call in self.calls))

    def test_label_resolution_and_message_metadata_recover(self):
        result = self.run_command([limited("/labels"), reply("/labels", LABELS), reply("/messages", {"messages": [{"id": "m1"}]}), limited("/messages/m1", reason="userRateLimitExceeded"), reply("/messages/m1", MESSAGE)], "list", "--label", "Receipts", "--limit", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["id"], "m1")
        self.assertEqual(self.calls[3], self.calls[4])
        self.assertIn("labelIds=Label_1", self.calls[2]["query"])
        self.assertIn("maxResults=1", self.calls[2]["query"])
        self.assertIn("format=metadata", self.calls[3]["query"])

    def test_exhaustion_and_disabled_retries_are_bounded(self):
        for cap, attempts in [("2", 3), ("0", 1)]:
            with self.subTest(cap=cap):
                result = self.run_command([limited("/labels")] * attempts, "labels", "--json", cap=cap)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.calls), attempts)
                self.assertEqual(self.sleeps, ["2", "4"][:attempts - 1])
                self.assertEqual(result.stdout, "")
                self.assertIn("rateLimitExceeded", result.stderr)
                self.assertIn("Synthetic quota exceeded", result.stderr)

    def test_nonjson_429_retries_under_errexit(self):
        result = self.run_command([reply("/labels", "<html>Too many requests</html>", 429), reply("/labels", LABELS)], "get", API + "/labels")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sleeps, ["2"])

    def test_nonretryable_http_and_transport_failures_stop(self):
        for status in [401, 403, 404, 500]:
            with self.subTest(status=status):
                result = self.run_command([reply("/labels", {"error": {"message": "Synthetic denied", "errors": [{"reason": "forbidden"}]}}, status)], "labels", "--json")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(self.sleeps, [])
                self.assertEqual(result.stdout, "")
                self.assertIn("Synthetic denied", result.stderr)
        result = self.run_command([dict(reply("/labels", "", 0), exit=7)], "labels", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.sleeps, [])

    def test_failed_preview_preserves_cause_and_never_writes(self):
        for args, path in [(("archive", "--message", "m1", "--execute"), "/messages/m1"), (("delete-filter", "--filter", "f1", "--execute"), "/settings/filters/f1")]:
            with self.subTest(command=args[0]):
                result = self.run_command([limited(path)] * 3, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Synthetic quota exceeded", result.stderr)
                self.assertNotIn("were not found", result.stderr)
                self.assertNotIn("No Gmail filter", result.stderr)
                self.assertTrue(all(call["method"] == "GET" for call in self.calls))

    def test_readback_retries_do_not_repeat_mutation(self):
        before_write = [reply("/messages/m1", MESSAGE), reply("/messages/batchModify", {}, method="POST")]
        result = self.run_command([*before_write, limited("/messages/m1"), reply("/messages/m1", dict(MESSAGE, labelIds=[]))], "archive", "--message", "m1", "--execute")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("confirmed by readback", result.stdout)
        self.assertEqual([c["method"] for c in self.calls], ["GET", "POST", "GET", "GET"])
        self.assertEqual(json.loads(self.calls[1]["body"]), {"ids": ["m1"], "addLabelIds": [], "removeLabelIds": ["INBOX"]})
        result = self.run_command([*before_write, *([limited("/messages/m1")] * 3)], "archive", "--message", "m1", "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(c["method"] == "POST" for c in self.calls), 1)
        self.assertIn("verification failed", result.stderr)

    def test_rate_limited_writes_are_never_retried(self):
        for method, path in [("POST", "/drafts"), ("POST", "/settings/filters"), ("POST", "/messages/batchModify"), ("DELETE", "/settings/filters/f1")]:
            with self.subTest(method=method, path=path):
                response = dict(limited(path, 429), method=method)
                result = self.run_command([response], "mutation", method, "example", API + path, "{}")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(self.sleeps, [])


if __name__ == "__main__":
    unittest.main()
