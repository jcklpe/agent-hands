"""Exercise the actual deletion dispatcher with synthetic service state and transport."""
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
PROVIDER = SKILL.parent / "setup-microsoft-services/scripts/client.sh"
spec = importlib.util.spec_from_file_location("task_delete", SKILL / "scripts/task_delete.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
SHELL = r'''
set -eu
source "$PROVIDER"
source "$OPERATIONS"
_m365_require_enabled() { :; }
_m365_planner_require_plan_allowed() { [ "$2" = plan-1 ]; }
_m365_planner_require_write() { [ "${WRITABLE:-1}" = 1 ]; }
_m365_planner_task() { cat "$CASE/snapshot.json"; }
_m365_planner_max_tasks() { printf '10'; }
_m365_graph_base() { printf 'https://graph.microsoft.com/v1.0'; }
_m365_http() {
  printf '%s\n' "$*" >> "$CASE/writes"
  [ "${DELETE_FAIL:-0}" = 0 ] || return 1
  touch "$CASE/deleted"
}
_m365_batch() {
  jq -e 'length==1 and .[0].method=="GET" and .[0].url=="/planner/tasks/task-1"' "$2" >/dev/null || return 1
  printf '[{"id":"0","status":%s,"body":{"error":{"code":"itemNotFound"}}}]' "${LOOKUP_STATUS:-404}" > "$3"
}
_m365_get_paginated() {
  [ "${M365_REQUIRE_COMPLETE:-0}" = 1 ] || return 1
  printf '%s\n' "$4" >> "$CASE/readbacks"
  [ "${READ_FAIL:-0}" = 0 ] || return 1
  if [ "${REMAINS:-0}" = 1 ] || [ ! -f "$CASE/deleted" ]; then
    printf '%s' '{"value":[{"id":"task-1","planId":"plan-1"}]}' > "$3"
  else
    printf '%s' '{"value":[{"id":"peer-task","planId":"plan-1"}]}' > "$3"
  fi
}
_m365_planner_dispatch "$@"
'''


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.snapshot = {"task": {"id": "task-1", "planId": "plan-1", "title": "Disposable fixture", "bucketId": "bucket-1", "@odata.etag": 'W/"task-etag"', "appliedCategories": {"category1": True}}, "details": {"id": "task-1", "@odata.etag": 'W/"details-etag"', "description": "Synthetic description", "checklist": {}, "references": {}}}
        self.save()

    def save(self):
        (self.root / "snapshot.json").write_text(json.dumps(self.snapshot))

    def run_cli(self, *args, **overrides):
        env = dict(os.environ, CASE=str(self.root), PROVIDER=str(PROVIDER), OPERATIONS=str(SKILL / "scripts/operations.sh"), M365_PYTHON=sys.executable, M365_PLANNER_AUDIT_LOG=str(self.root / "audit.jsonl"))
        env.update(overrides)
        return subprocess.run(["/bin/bash", "-c", SHELL, "delete-test", "delete-task", "example", "--task", "task-1", *args], text=True, capture_output=True, env=env)

    def preview(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        return re.search(r"Preview fingerprint: ([0-9a-f]{64})", result.stdout)[1]

    def writes(self):
        p = self.root / "writes"
        return p.read_text().splitlines() if p.exists() else []

    def execute(self, fingerprint, **overrides):
        return self.run_cli("--expected-sha256", fingerprint, "--execute", **overrides)

    def test_preview_no_write_and_exact_conditional_deletion(self):
        fingerprint = self.preview()
        self.assertFalse((self.root / "planner-task-delete").exists())
        self.assertEqual(self.writes(), [])
        result = self.execute(fingerprint)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.writes(), ['DELETE example https://graph.microsoft.com/v1.0/planner/tasks/task-1  -H If-Match: W/"task-etag"'])
        self.assertIn("complete plan readback", result.stdout)
        receipts = list((self.root / "planner-task-delete/example").glob("*.json"))
        self.assertEqual(len(receipts), 2)
        for path in receipts:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn("planner/plans/plan-1/tasks", (self.root / "readbacks").read_text())

    def test_missing_fingerprint_and_disabled_writes_refuse(self):
        fingerprint = self.preview()
        for result in (self.run_cli("--execute"), self.execute(fingerprint, WRITABLE="0")):
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.writes(), [])

    def test_changed_task_or_details_refuse_before_dispatch(self):
        fingerprint = self.preview()
        self.snapshot["details"]["description"] = "Another editor changed this"
        self.save()
        result = self.execute(fingerprint)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("changed", result.stderr)
        self.assertEqual(self.writes(), [])

    def test_wrong_identity_missing_etags_and_disallowed_plan_refuse(self):
        for obj, field, value in (("task", "id", "wrong"), ("details", "id", "wrong"), ("task", "@odata.etag", None), ("details", "@odata.etag", None), ("task", "planId", "not-allowed")):
            with self.subTest(obj=obj, field=field):
                prior = self.snapshot[obj][field]
                self.snapshot[obj][field] = value
                self.save()
                self.assertNotEqual(self.run_cli("--execute", "--expected-sha256", "0" * 64).returncode, 0)
                self.assertEqual(self.writes(), [])
                self.snapshot[obj][field] = prior

    def test_readback_failure_retains_receipt_and_blocks_replay(self):
        fingerprint = self.preview()
        first = self.execute(fingerprint, READ_FAIL="1")
        self.assertNotEqual(first.returncode, 0)
        self.assertIn("--verify", first.stderr)
        self.assertNotEqual(self.execute(fingerprint).returncode, 0)
        self.assertEqual(len(self.writes()), 1)
        recovery = self.run_cli("--verify")
        self.assertEqual(recovery.returncode, 0, recovery.stderr)
        self.assertEqual(len(self.writes()), 1)

    def test_failed_delete_and_task_still_present_never_claim_success(self):
        fingerprint = self.preview()
        first = self.execute(fingerprint, DELETE_FAIL="1")
        self.assertNotEqual(first.returncode, 0)
        self.assertNotEqual(self.run_cli("--verify").returncode, 0)
        self.assertNotEqual(self.execute(fingerprint).returncode, 0)
        self.assertEqual(len(self.writes()), 1)

    def test_successful_transport_with_present_task_is_unverified(self):
        result = self.execute(self.preview(), REMAINS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remains present", result.stderr)
        self.assertNotIn("deletion confirmed", result.stdout)
        self.assertEqual(len(self.writes()), 1)

    def test_absence_from_original_plan_does_not_prove_deletion(self):
        fingerprint = self.preview()
        for code in ('200', '403', '429', '500'):
            with self.subTest(status=code):
                if not self.writes():
                    result = self.execute(fingerprint, LOOKUP_STATUS=code)
                else:
                    result = self.run_cli('--verify', LOOKUP_STATUS=code)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('deletion confirmed', result.stdout)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.run_cli('--verify').returncode, 0)

    def test_verify_is_read_only_and_unknown_options_fail(self):
        for args in (("--verify", "--execute"), ("--verify", "--expected-sha256", "0" * 64), ("--force",), ("--verify",)):
            self.assertNotEqual(self.run_cli(*args).returncode, 0)
        self.assertEqual(self.writes(), [])

    def test_private_state_and_complete_listing_guards(self):
        root = self.root / "state"
        prepared = helper.prepare("example", "task-1", self.snapshot)
        store = helper.Receipts(root, "example", "task-1")
        store.claim(prepared, prepared["fingerprint"])
        with self.assertRaises(ValueError):
            store.claim(prepared, prepared["fingerprint"])
        for listing in (None, [], {"error": {}, "value": []}, {"value": [None]}, {"value": [], "@odata.nextLink": "next"}, {"value": [{"id": "peer", "planId": "wrong"}]}, {"value": [{"id": "peer", "planId": "plan-1"}] * 2}):
            with self.assertRaises((ValueError, KeyError, TypeError)):
                store.confirm(listing)
        store.pending.chmod(0o644)
        with self.assertRaises(ValueError):
            store.read(store.pending)
        symlink = self.root / "link"
        symlink.symlink_to(root, target_is_directory=True)
        with self.assertRaises(ValueError):
            helper.Receipts(symlink, "example", "task-1")


if __name__ == "__main__":
    unittest.main()
