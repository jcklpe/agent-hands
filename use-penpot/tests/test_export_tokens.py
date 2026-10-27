"""Synthetic Penpot archive fixtures; no credentials, network or live designs."""

from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export_tokens.py"
SPEC = importlib.util.spec_from_file_location("export_tokens", SCRIPT)
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)
FILE_ID = "11111111-2222-3333-4444-555555555555"
TOKENS = {
    "color": {"color": {"brand": {"$value": "#2563EB", "$type": "color"}}},
    "type": {"type": {"label": {"$value": "{color.brand}", "$type": "color", "$description": "Synthetic café label"}}},
    "$themes": [],
    "$metadata": {"tokenSetOrder": ["color", "type"], "activeThemes": [], "activeSets": ["type", "color"]},
}


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="penpot-token-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = self.root / "penpot-export.json"
        self.config = {
            "schema_version": 1,
            "source": {"kind": "penpot-archive", "path": "Wireframes.penpot", "file_id": FILE_ID},
            "outputs": {"sets": {"color": "out/color.json", "type": "out/type.json"},
                        "metadata": "out/$metadata.json", "themes": "out/$themes.json"},
        }
        self.save_manifest()
        self.archive()

    def save_manifest(self):
        self.manifest.write_text(json.dumps(self.config), encoding="utf-8")

    def archive(self, tokens=None, file_ids=None, duplicate=False, token_raw=None, reverse=False):
        members = [
            ("manifest.json", json.dumps({"type": "penpot/export-files", "version": 1,
                                         "files": [{"id": value, "name": "Example"} for value in (file_ids or [FILE_ID])]})),
            ("files/" + FILE_ID + "/tokens.json", token_raw if token_raw is not None else json.dumps(TOKENS if tokens is None else tokens)),
        ]
        if duplicate:
            members.append(members[-1])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.root / "Wireframes.penpot", "w", zipfile.ZIP_DEFLATED) as archive:
                for name, value in reversed(members) if reverse else members:
                    archive.writestr(name, value)

    def call(self, *args, ok=True):
        output = io.StringIO()
        with redirect_stdout(output):
            code = EXPORT.main(["--manifest", str(self.manifest), *args])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0 if ok else 1, report)
        self.assertEqual(report["status"], "ok" if ok else "error")
        return report

    def execute(self):
        preview = self.call()
        return self.call("--execute", "--expect-plan", preview["plan_sha256"])

    def test_preview_is_read_only_and_execute_is_idempotent(self):
        preview = self.call()
        self.assertFalse((self.root / "out").exists())
        self.assertEqual(preview["token_count"], 2)
        self.call("--execute", ok=False)
        self.assertFalse((self.root / "out").exists())
        result = self.call("--execute", "--expect-plan", preview["plan_sha256"])
        self.assertEqual(len(result["completed"]), 4)
        self.assertEqual(result["created_directories"], ["out"])
        expected = json.dumps(TOKENS["color"], indent=2, ensure_ascii=False).encode()
        self.assertEqual((self.root / "out/color.json").read_bytes(), expected)
        metadata = json.loads((self.root / "out/$metadata.json").read_bytes())
        self.assertEqual(metadata["activeSets"], ["color", "type"])
        self.assertEqual(self.call("--execute")["completed"], [])
        self.assertTrue(all(entry["action"] == "unchanged" for entry in self.call()["outputs"]))

    def test_deterministic_export_ignores_zip_entry_order(self):
        first = self.call()
        self.archive(reverse=True)
        second = self.call()
        self.assertEqual(first["outputs"], second["outputs"])

    def test_numeric_palette_keys_match_browser_export_order(self):
        tokens = copy.deepcopy(TOKENS)
        token = {"$type": "spacing", "$value": "4"}
        tokens["color"]["space"] = {key: token for key in ["default", "10", "2", "1", "0-5", "01", "4294967295"]}
        self.archive(tokens)
        self.execute()
        value = json.loads((self.root / "out/color.json").read_bytes())
        self.assertEqual(list(value["space"]), ["1", "2", "10", "default", "0-5", "01", "4294967295"])

    def test_cli_resolves_manifest_relative_paths_from_another_directory(self):
        run = subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(self.manifest)],
                             cwd=self.root.parent, text=True, capture_output=True, timeout=5)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["source"]["path"], "Wireframes.penpot")

    def test_partial_selection_and_cross_palette_dependency(self):
        self.config["outputs"] = {"sets": {"color": "out/color.json"}}
        self.save_manifest()
        self.assertEqual(self.call()["token_count"], 1)
        self.config["outputs"]["sets"] = {"type": "out/type.json"}
        self.save_manifest()
        self.call(ok=False)
        self.config["outputs"] = {"sets": {"color": "out/color.json"}, "themes": "out/themes.json"}
        self.save_manifest()
        self.call(ok=False)

    def test_unknown_fields_and_source_selection_fail(self):
        for mutate in [lambda c: c.update(command="do-not-run"),
                       lambda c: c["source"].update(kind="live-mcp"),
                       lambda c: c["source"].update(file_id="66666666-2222-3333-4444-555555555555"),
                       lambda c: c.update(schema_version=True)]:
            original = copy.deepcopy(self.config)
            mutate(self.config)
            self.save_manifest()
            self.call(ok=False)
            self.config = original
        self.assertFalse((self.root / "out").exists())

    def test_paths_cannot_escape_or_target_hidden_control_files(self):
        for value in ["../outside.json", "/tmp/outside.json", "out/../../outside.json", "out/./x.json",
                      "out//x.json", ".git/config.json", "out\\x.json", "out/x.json\n", "out/x.txt"]:
            with self.subTest(path=value):
                self.config["outputs"]["sets"]["color"] = value
                self.save_manifest()
                self.call(ok=False)
        self.config["source"]["path"] = "../outside.penpot"
        self.save_manifest()
        self.call(ok=False)
        self.assertFalse((self.root / "out").exists())

    def test_duplicate_overlapping_and_manifest_outputs_fail_before_writing(self):
        for first, second in [("out/a.json", "out/a.json"), ("out/A.json", "out/a.json"),
                              ("out/café.json", "out/cafe\u0301.json"),
                              ("out/a.json", "out/a.json/b.json"), ("penpot-export.json", "out/b.json")]:
            self.config["outputs"]["sets"] = {"color": first, "type": second}
            self.save_manifest()
            self.call(ok=False)
        self.assertFalse((self.root / "out").exists())

    def test_symlink_sources_parents_targets_and_manifests_fail(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "out").symlink_to(outside, target_is_directory=True)
        self.call(ok=False)
        (self.root / "out").unlink()
        (self.root / "out").mkdir()
        target = outside / "safe.json"
        target.write_text("preserve")
        (self.root / "out/color.json").symlink_to(target)
        self.call(ok=False)
        self.assertEqual(target.read_text(), "preserve")
        (self.root / "out/color.json").unlink()
        source = self.root / "Wireframes.penpot"
        source.rename(outside / "source.penpot")
        source.symlink_to(outside / "source.penpot")
        self.call(ok=False)
        source.unlink()
        self.archive()
        self.manifest.rename(outside / "manifest.json")
        self.manifest.symlink_to(outside / "manifest.json")
        self.call(ok=False)

    def test_nonregular_output_is_rejected_without_blocking(self):
        (self.root / "out").mkdir()
        os.mkfifo(self.root / "out/color.json")
        run = subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(self.manifest)],
                             text=True, capture_output=True, timeout=5)
        self.assertEqual(run.returncode, 1)

    def test_archive_duplicates_missing_members_and_invalid_file_identity_fail(self):
        self.archive(duplicate=True)
        self.call(ok=False)
        self.archive(file_ids=[FILE_ID, FILE_ID])
        self.call(ok=False)
        with zipfile.ZipFile(self.root / "Wireframes.penpot", "w") as archive:
            archive.writestr("irrelevant.txt", "example")
        self.call(ok=False)
        (self.root / "Wireframes.penpot").write_bytes(b"not a zip")
        self.call(ok=False)

    def test_json_duplicates_nonfinite_values_and_size_limits_fail(self):
        for raw in ['{"color":{},"color":{}}', '{"color":{"x":{"$value":NaN,"$type":"number"}}}', '{']:
            self.archive(token_raw=raw)
            self.call(ok=False)
        self.archive()
        with patch.object(EXPORT, "MAX_JSON", 32):
            self.call(ok=False)
        with patch.object(EXPORT, "MAX_ARCHIVE", 32):
            self.call(ok=False)
        with patch.object(EXPORT, "MAX_ENTRIES", 1):
            self.call(ok=False)
        self.manifest.write_text('{"schema_version":1,"schema_version":1}')
        self.call(ok=False)

    def test_missing_cyclic_duplicate_and_untyped_tokens_fail(self):
        cases = []
        missing = copy.deepcopy(TOKENS)
        missing["type"]["type"]["label"]["$value"] = "{color.missing}"
        cases.append(missing)
        cyclic = copy.deepcopy(TOKENS)
        cyclic["color"]["color"]["brand"]["$value"] = "{type.label}"
        cases.append(cyclic)
        duplicate = copy.deepcopy(TOKENS)
        duplicate["type"] = duplicate["color"]
        cases.append(duplicate)
        untyped = copy.deepcopy(TOKENS)
        del untyped["color"]["color"]["brand"]["$type"]
        cases.append(untyped)
        for tokens in cases:
            self.archive(tokens)
            self.call(ok=False)

    def test_inherited_types_are_supported(self):
        tokens = copy.deepcopy(TOKENS)
        tokens["color"]["color"]["$type"] = "color"
        del tokens["color"]["color"]["brand"]["$type"]
        self.archive(tokens)
        self.call()

    def test_stale_plan_detects_source_manifest_or_destination_changes(self):
        self.execute()
        preview = self.call()
        output = self.root / "out/color.json"
        output.write_text("someone else's work")
        self.call("--execute", "--expect-plan", preview["plan_sha256"], ok=False)
        self.assertEqual(output.read_text(), "someone else's work")
        preview = self.call()
        self.config["outputs"]["sets"]["color"] = "new/color.json"
        self.save_manifest()
        self.call("--execute", "--expect-plan", preview["plan_sha256"], ok=False)
        self.assertFalse((self.root / "new").exists())
        preview = self.call()
        changed = copy.deepcopy(TOKENS)
        changed["color"]["color"]["brand"]["$value"] = "#FFFFFF"
        self.archive(changed)
        self.call("--execute", "--expect-plan", preview["plan_sha256"], ok=False)

    def test_preflight_detects_output_change_after_plan(self):
        self.execute()
        root, manifest, plan, _hash, payloads = EXPORT.build_plan(self.manifest)
        target = self.root / "out/type.json"
        target.write_text("concurrent work")
        completed = []
        with self.assertRaises(EXPORT.ExportError):
            EXPORT.apply_plan(root, manifest, plan, payloads, completed, [])
        self.assertEqual(completed, [])
        self.assertEqual(target.read_text(), "concurrent work")

    def test_partial_failure_reports_completed_files_and_cleans_tempfiles(self):
        preview = self.call()
        replace = os.replace
        count = 0

        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("synthetic failure")
            return replace(*args, **kwargs)

        with patch.object(EXPORT.os, "replace", side_effect=fail_second):
            report = self.call("--execute", "--expect-plan", preview["plan_sha256"], ok=False)
        self.assertEqual(report["completed"], ["out/$metadata.json"])
        self.assertEqual(report["created_directories"], ["out"])
        self.assertEqual(list((self.root / "out").glob(".penpot-export-*")), [])
        self.assertFalse((self.root / "out/color.json").exists())

    def test_exclusive_tempfile_collision_preserves_other_work(self):
        (self.root / "out").mkdir()
        other = self.root / "out/.penpot-export-collision"
        other.write_text("preserve another writer's file")
        preview = self.call()
        with patch.object(EXPORT.uuid, "uuid4") as identifier:
            identifier.return_value.hex = "collision"
            report = self.call("--execute", "--expect-plan", preview["plan_sha256"], ok=False)
        self.assertEqual(report["completed"], [])
        self.assertEqual(other.read_text(), "preserve another writer's file")


if __name__ == "__main__":
    unittest.main()
