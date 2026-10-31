"""Synthetic offline snapshot contract checks; no service access."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("snapshots", Path(__file__).resolve().parents[1] / "scripts/snapshots.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "snapshots").mkdir()
        self.destination = self.root / "snapshots/sample"
        self.course = {"course_id": "12", "origin": "https://canvas.example", "account": "example"}
        self.data = {"course_id": "12", "course": {"identity": "canvas:canvas.example:course:12", "name": "Course"},
                     "coverage": {f: {"status": "complete", "count": 1} for f in {"course", *sync.FAMILIES, "page_bodies", "groups", "images", "overrides", "permissions"}},
                     "assignments": [{"identity": "canvas:canvas.example:assignment:7", "id": "7", "name": "Design", "due_at": "2026-11-04T17:00:00Z",
                                      "updated_at": "2026-10-01", "body": {"html_sha256": "old-body", "markdown": "Source"}}],
                     "pages": [{"identity": "canvas:canvas.example:page:9", "id": "9", "title": "Reading", "url": "old-slug"}], "groups": [], "gaps": []}
        self.before = self.export("before", self.data)

    def export(self, name, data, identity="user"):
        root = self.root / name
        (root / "courses/course-12").mkdir(parents=True)
        sync.write_json(root / "index.json", {"tool": "use-canvas", "format_version": 1, "origin": self.course["origin"], "course_ids": ["12"], "user_id": identity})
        sync.write_json(root / "run.json", {"finished_at": "2026-10-31T12:00:00Z", "requests_sent": 20})
        sync.write_json(root / "courses/course-12/course.json", data)
        return root

    def compare(self, data):
        after = self.export("after", data)
        return sync.make_report(sync.load_export(self.before, self.course), sync.load_export(after, self.course), self.course)

    def test_unchanged_ignores_run_timestamps_and_rendering_noise(self):
        data = copy.deepcopy(self.data)
        data["assignments"][0]["updated_at"] = "2026-10-31"
        data["assignments"][0]["body"]["markdown"] = "Converter whitespace changed"
        self.assertEqual(self.compare(data)["changes"], [])

    def test_deadline_uses_same_identity(self):
        data = copy.deepcopy(self.data)
        data["assignments"][0]["due_at"] = "2026-11-05T17:00:00Z"
        changes = self.compare(data)["changes"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["before"], "2026-11-04T17:00:00Z")
        self.assertEqual(changes[0]["identity"], "canvas:canvas.example:assignment:7")

    def test_title_or_slug_change_is_not_new_work(self):
        data = copy.deepcopy(self.data)
        data["pages"][0].update(title="Renamed", url="new-slug")
        self.assertTrue(all(f["kind"] == "changed" for f in self.compare(data)["changes"]))

    def test_body_hash_change_requires_source_inspection(self):
        data = copy.deepcopy(self.data)
        data["assignments"][0]["body"]["html_sha256"] = "new-body"
        data["assignments"][0]["body"]["markdown"] = "Revised requirement\n"
        finding = self.compare(data)["changes"][0]
        self.assertEqual(finding["field"], "body.html_sha256")
        self.assertIn("Revised requirement", finding["body_diffs"][0])
        self.assertIn("Source", finding["body_diffs"][0])

    def test_denied_listing_does_not_infer_removed_assignments(self):
        data = copy.deepcopy(self.data)
        data["assignments"] = []
        data["coverage"]["assignments"] = {"status": "denied", "count": 0}
        report = self.compare(data)
        self.assertFalse(any(f["kind"] == "no_longer_visible" for f in report["changes"]))
        self.assertTrue(any(f["kind"] == "coverage_changed" for f in report["changes"]))

    def test_complete_absence_is_visibility_review_not_cancellation(self):
        data = copy.deepcopy(self.data)
        data["assignments"] = []
        finding = self.compare(data)["changes"][0]
        self.assertEqual(finding["kind"], "no_longer_visible")
        self.assertEqual(finding["before"], "previously visible")

    def test_format_identity_and_partial_coverage_refused(self):
        data = copy.deepcopy(self.data)
        data["coverage"]["pages"]["status"] = "partial"
        partial = self.export("partial", data)
        with self.assertRaises(ValueError):
            sync.load_export(partial, self.course)
        other_user = self.export("other-user", self.data, identity="different-user")
        with self.assertRaises(ValueError):
            sync.compare(sync.load_export(self.before, self.course), sync.load_export(other_user, self.course))
        index = sync.read_json(other_user / "index.json")
        index["format_version"] = 2
        sync.write_json(other_user / "index.json", index)
        with self.assertRaises(ValueError):
            sync.load_export(other_user, self.course)

    def fake_export(self, command, **kwargs):
        self.assertEqual(command[3], "export")
        self.assertEqual(command[command.index("--course") + 1], "12")
        self.assertNotIn("--allow-partial", command)
        shutil.copytree(self.before, command[command.index("--output") + 1])
        return subprocess.CompletedProcess(command, 0, "{}", "")

    def test_refresh_unchanged_keeps_pending_and_other_course(self):
        other = self.root / "snapshots/other"
        other.mkdir(parents=True)
        (other / "evidence").write_text("untouched")
        with patch.object(sync.subprocess, "run", side_effect=self.fake_export):
            first = sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
            second = sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
        self.assertTrue(first["baseline"])
        self.assertEqual(second["changes"], [])
        self.assertEqual(second["pending"][0]["id"], "baseline-review")
        self.assertEqual((other / "evidence").read_text(), "untouched")
        sync.acknowledge(self.destination, self.course, "example-snapshot", ["baseline-review"], "Verified in course owner")
        self.assertEqual(sync.read_json(self.root / "snapshots/sample/changes.json")["pending"], [])

    def test_failed_export_preserves_entire_package(self):
        with patch.object(sync.subprocess, "run", side_effect=self.fake_export):
            sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
        destination = self.root / "snapshots/sample"
        before = {str(p.relative_to(destination)): p.read_bytes() for p in destination.rglob("*") if p.is_file()}
        with patch.object(sync.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "test failure")):
            with self.assertRaises(RuntimeError):
                sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
        self.assertEqual(before, {str(p.relative_to(destination)): p.read_bytes() for p in destination.rglob("*") if p.is_file()})

    def test_unrecognized_destination_and_symlink_refused(self):
        destination = self.root / "snapshots/sample"
        destination.mkdir(parents=True)
        (destination / "human-note.md").write_text("preserve")
        with self.assertRaises(OSError):
            sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
        (self.before / "unexpected").symlink_to(self.root / "elsewhere")
        with self.assertRaises(ValueError):
            sync.load_export(self.before, self.course)

    def test_pending_changed_deadline_survives_unchanged_rerun(self):
        data = copy.deepcopy(self.data)
        data["assignments"][0]["due_at"] = "2026-11-05T17:00:00Z"
        after = self.export("after", data)
        old, new = sync.load_export(self.before, self.course), sync.load_export(after, self.course)
        first = sync.make_report(old, new, self.course)
        second = sync.make_report(new, new, self.course, first)
        self.assertEqual(second["changes"], [])
        self.assertEqual(second["pending"], first["pending"])

    def test_missing_coverage_refused(self):
        data = copy.deepcopy(self.data)
        del data["coverage"]["assignments"]
        after = self.export("after", data)
        with self.assertRaises(ValueError):
            sync.load_export(after, self.course)

    def test_own_grade_change_is_a_field_difference(self):
        data = copy.deepcopy(self.data)
        data["assignments"][0]["submission"] = {"score": 10}
        finding = self.compare(data)["changes"][0]
        self.assertEqual(finding["field"], "submission")

    def test_interrupted_install_rolls_back(self):
        destination = self.root / "destination"
        stage = self.root / "stage"
        stage.mkdir()
        destination.mkdir()
        sync.write_json(destination / "consumer.json", {"consumer": "example-snapshot", "schema_version": 1, "course_id": "12"})
        (destination / "evidence").write_text("old")
        original = sync.os.replace

        def fail_install(source, target):
            if source == stage:
                raise OSError("interrupted install")
            return original(source, target)

        with patch.object(sync.os, "replace", side_effect=fail_install):
            with self.assertRaises(OSError):
                sync.publish(stage, destination, self.course, "example-snapshot")
        self.assertEqual((destination / "evidence").read_text(), "old")
        self.assertFalse((self.root / ".destination.previous").exists())


    def test_unknown_acknowledgment_preserves_snapshot(self):
        with patch.object(sync.subprocess, "run", side_effect=self.fake_export):
            sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
        before = (self.destination / "changes.json").read_bytes()
        with self.assertRaises(ValueError):
            sync.acknowledge(self.destination, self.course, "example-snapshot", ["unknown"], "Inspected")
        self.assertEqual((self.destination / "changes.json").read_bytes(), before)

    def test_existing_lock_prevents_export(self):
        lock = self.destination.parent / ".sample.lock"
        lock.write_text("123")
        with patch.object(sync.subprocess, "run") as run:
            with self.assertRaises(FileExistsError):
                sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
            run.assert_not_called()
        self.assertEqual(lock.read_text(), "123")

    def test_interrupted_rename_is_recovered_before_failed_export(self):
        with patch.object(sync.subprocess, "run", side_effect=self.fake_export):
            sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
        before = (self.destination / "changes.json").read_bytes()
        self.destination.rename(self.destination.with_name(".sample.previous"))
        with patch.object(sync.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "fixture failure")):
            with self.assertRaises(RuntimeError):
                sync.refresh(self.destination, self.course, "example-snapshot", self.root / "exporter.py", Path(sys.executable), self.root / "history")
        self.assertEqual((self.destination / "changes.json").read_bytes(), before)

    def test_new_change_reopens_acknowledged_field_and_preserves_receipts(self):
        changed = copy.deepcopy(self.data)
        changed["assignments"][0]["due_at"] = "2027-03-05T12:00:00Z"
        after = self.export("after", changed)
        old, new = sync.load_export(self.before, self.course), sync.load_export(after, self.course)
        report = sync.make_report(old, new, self.course)
        identity = report["pending"][0]["id"]
        report["pending"] = []
        report["acknowledged"] = [{"finding_ids": [identity], "note": "Inspected"}]
        changed["assignments"][0]["due_at"] = "2027-03-06T12:00:00Z"
        later = sync.load_export(self.export("later", changed), self.course)
        reopened = sync.make_report(new, later, self.course, report)
        self.assertEqual(reopened["pending"][0]["id"], identity)
        self.assertEqual(reopened["acknowledged"], report["acknowledged"])

    def test_cli_compare_refuses_existing_output_and_symlink(self):
        output = self.root / "result.json"
        output.write_text("preserve")
        command = [sys.executable, "-B", str(Path(sync.__file__)), "compare", "--origin", self.course["origin"], "--course-id", "12", "--before", str(self.before), "--after", str(self.before), "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(), "preserve")
        output.unlink()
        output.symlink_to(self.root / "target")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "target").exists())

    def test_cli_compare_refuses_output_inside_input_export(self):
        output = self.before / "unexpected.json"
        result = subprocess.run([sys.executable, "-B", str(Path(sync.__file__)), "compare", "--origin", self.course["origin"], "--course-id", "12", "--before", str(self.before), "--after", str(self.before), "--output", str(output)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_cli_compare_refuses_normalized_output_inside_input_export(self):
        (self.root / "elsewhere").mkdir()
        output = self.root / "elsewhere/../before/unexpected.json"
        result = subprocess.run([sys.executable, "-B", str(Path(sync.__file__)), "compare", "--origin", self.course["origin"], "--course-id", "12", "--before", str(self.before), "--after", str(self.before), "--output", str(output)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.before / "unexpected.json").exists())

    def test_group_visibility_loss_does_not_remove_child_resources(self):
        group = {"group_id": "5", "coverage": {f: {"status": "complete"} for f in ("pages", "page_bodies", "files", "folders", "discussions", "images")},
                 "pages": [{"identity": "canvas:canvas.example:page:30", "title": "Group source"}]}
        data = copy.deepcopy(self.data)
        data["groups"] = [group]
        old = sync.load_export(self.export("group-before", data), self.course)
        data["groups"] = []
        new = sync.load_export(self.export("group-after", data), self.course)
        self.assertFalse(any(f["kind"] == "no_longer_visible" for f in sync.compare(old, new)))


if __name__ == "__main__":
    unittest.main()
