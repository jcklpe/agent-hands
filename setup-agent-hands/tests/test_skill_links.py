"""Offline integration tests: the real entrypoints write only temporary roots."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("skill_links", ROOT / "setup-agent-hands/scripts/skill_links.py")
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class SkillLinksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent hands links ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "checkout with spaces"
        self.dest = self.base / "client" / "skills"
        for source in ROOT.glob("*/SKILL.md"):
            target = self.repo / source.parent.name
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("synthetic skill\n")
        for source in ROOT.glob("*/scripts/link-skills.py"):
            target = self.repo / source.relative_to(ROOT)
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
        shutil.copyfile(ROOT / "setup-agent-hands/scripts/skill_links.py", self.repo / "setup-agent-hands/scripts/skill_links.py")

    def invoke(self, owner="setup-trello", *args, shell=None):
        command = [sys.executable, str(self.repo / owner / "scripts/link-skills.py"), "--client", "codex", "--skills-dir", str(self.dest), *args]
        if shell:
            command = [shell, "-c", 'exec "$@"', "skill-links", *command]
        result = subprocess.run(command, text=True, capture_output=True)
        return result, json.loads(result.stdout) if result.stdout else None

    def test_preview_creates_nothing_and_fresh_repeat_is_idempotent(self):
        result, plan = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p["skill"] for p in plan["links"]], ["setup-trello", "use-trello"])
        self.assertFalse(self.dest.parent.exists())
        self.assertFalse(list(self.repo.rglob("__pycache__")))
        result, done = self.invoke("setup-trello", "--execute")
        self.assertEqual(result.returncode, 0, done)
        before = {p.name: p.lstat().st_ino for p in self.dest.iterdir()}
        result, again = self.invoke("setup-trello", "--execute")
        self.assertEqual(result.returncode, 0, again)
        self.assertEqual(before, {p.name: p.lstat().st_ino for p in self.dest.iterdir()})
        self.assertTrue(all(x["action"] == "unchanged" for x in again["links"]))

    def test_multi_capability_requires_selection_and_only_links_selected(self):
        result, _ = self.invoke("setup-google-services", "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.dest.exists())
        result, done = self.invoke("setup-google-services", "--skill", "use-gmail", "--execute")
        self.assertEqual(result.returncode, 0, done)
        self.assertEqual({p.name for p in self.dest.iterdir()}, {"setup-google-services", "use-gmail"})

    def test_calendar_adds_only_declared_renderer_dependency(self):
        result, plan = self.invoke("setup-google-services", "--skill", "use-google-calendar")
        self.assertEqual(result.returncode, 0, plan)
        self.assertEqual({x["skill"] for x in plan["links"]}, {"setup-google-services", "use-google-calendar", "render-calendar-agenda"})

    def test_every_owner_selection_has_real_sources(self):
        choices = {"setup-google-services": "use-google-docs", "setup-microsoft-services": "use-planner", "setup-github": "use-github-issues", "setup-slack": "use-slack-lists"}
        entrypoints = list(self.repo.glob("*/scripts/link-skills.py"))
        self.assertEqual(len(entrypoints), 12)
        for entry in entrypoints:
            owner = entry.parents[1].name
            args = ["--skill", choices[owner]] if owner in choices else []
            with self.subTest(owner=owner):
                result, plan = self.invoke(owner, *args)
                self.assertEqual(result.returncode, 0, result.stderr or plan)
                self.assertTrue(all(Path(x["source"]).joinpath("SKILL.md").is_file() for x in plan["links"]))
        self.assertFalse(self.dest.exists())

    def test_files_directories_and_unrelated_links_block_all_writes(self):
        self.dest.mkdir(parents=True)
        blocked = self.dest / "use-trello"
        (self.base / "other").mkdir()
        for kind in ["file", "directory", "foreign-link", "dangling-link"]:
            with self.subTest(kind=kind):
                if kind == "file": blocked.write_text("user file")
                elif kind == "directory": blocked.mkdir()
                else: blocked.symlink_to(self.base / ("other" if kind == "foreign-link" else "missing"))
                before = links.snapshot(blocked)
                result, plan = self.invoke("setup-trello", "--execute", "--repair-from", str(self.base / "old"))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(links.snapshot(blocked), before)
                self.assertFalse((self.dest / "setup-trello").exists())
                self.assertEqual(plan["completed"], [])
                if blocked.is_symlink() or blocked.is_file(): blocked.unlink()
                else: blocked.rmdir()

    def test_exact_source_repair_is_explicit_and_recoverable(self):
        self.dest.mkdir(parents=True)
        old = self.base / "old checkout"
        for skill in ["setup-trello", "use-trello"]:
            (self.dest / skill).symlink_to(old / skill)
        result, _ = self.invoke("setup-trello", "--execute")
        self.assertNotEqual(result.returncode, 0)
        result, preview = self.invoke("setup-trello", "--repair-from", str(old))
        self.assertEqual(result.returncode, 0, preview)
        self.assertEqual(preview["recovery"], [])
        result, done = self.invoke("setup-trello", "--repair-from", str(old), "--execute")
        self.assertEqual(result.returncode, 0, done)
        records = json.loads(Path(done["recovery"][0]).read_text())
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(os.readlink(record["saved"]), record["previous_target"])
            self.assertEqual(Path(record["destination"]).resolve(), Path(record["replacement"]))

    def test_relative_correct_link_is_left_unchanged(self):
        self.dest.mkdir(parents=True)
        target = self.dest / "setup-trello"
        target.symlink_to(os.path.relpath(self.repo / "setup-trello", self.dest))
        before = links.snapshot(target)
        result, done = self.invoke("setup-trello", "--execute")
        self.assertEqual(result.returncode, 0, done)
        self.assertEqual(before, links.snapshot(target))

    def test_missing_source_stops_before_any_link(self):
        (self.repo / "use-trello/SKILL.md").unlink()
        result, plan = self.invoke("setup-trello", "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.dest.exists())
        self.assertEqual(plan["completed"], [])

    def test_two_clients_defaults_and_global_preflight(self):
        home = self.base / "user"
        args = ["--client", "codex", "--client", "claude", "--execute"]
        entry = self.repo / "setup-trello/scripts/link-skills.py"
        foreign = home / ".claude/skills/use-trello"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("existing")
        with patch.object(links.Path, "home", return_value=home), redirect_stdout(io.StringIO()):
            code = links.main(entry, ["use-trello"], argv=args)
        self.assertEqual(code, 1)
        self.assertFalse((home / ".agents").exists())
        foreign.unlink()
        with patch.object(links.Path, "home", return_value=home), redirect_stdout(io.StringIO()):
            code = links.main(entry, ["use-trello"], argv=args)
        self.assertEqual(code, 0)
        for subdir in links.CLIENT_ROOTS.values():
            self.assertEqual({p.name for p in (home / subdir).iterdir()}, {"setup-trello", "use-trello"})

    def test_symlinked_or_non_directory_destination_root_refused(self):
        self.dest.parent.mkdir()
        other = self.base / "elsewhere"
        other.mkdir()
        self.dest.symlink_to(other)
        result, _ = self.invoke("setup-trello", "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(other.iterdir()), [])
        self.dest.unlink()
        self.dest.write_text("not a directory")
        result, _ = self.invoke("setup-trello", "--execute")
        self.assertNotEqual(result.returncode, 0)

    def test_preflight_change_is_refused(self):
        entries = links.build_plan(self.repo, "setup-trello", ["use-trello"], ["codex"], self.dest, None)
        self.dest.mkdir(parents=True)
        (self.dest / "use-trello").write_text("arrived later")
        report = dict(completed=[], recovery=[], saved_links=[])
        with self.assertRaises(RuntimeError): links.apply_plan(entries, report)
        self.assertFalse((self.dest / "setup-trello").exists())

    def test_partial_failure_preserves_racing_destination_and_reports_completed(self):
        entries = links.build_plan(self.repo, "setup-trello", ["use-trello"], ["codex"], self.dest, None)
        real_symlink = os.symlink
        def racing(source, target, **kwargs):
            if Path(target).name == "use-trello": Path(target).mkdir()
            return real_symlink(source, target, **kwargs)
        report = dict(completed=[], recovery=[], saved_links=[])
        with patch.object(links.os, "symlink", side_effect=racing), self.assertRaises(FileExistsError):
            links.apply_plan(entries, report)
        self.assertEqual(report["completed"], [str(self.dest / "setup-trello")])
        self.assertEqual(list((self.dest / "use-trello").iterdir()), [])

    def test_failed_repair_keeps_recovery_and_preserves_racing_file(self):
        self.dest.mkdir(parents=True)
        old = self.base / "old checkout"
        target = self.dest / "setup-trello"
        target.symlink_to(old / "setup-trello")
        entries = links.build_plan(self.repo, "setup-trello", [], ["codex"], self.dest, old)
        real_symlink = os.symlink
        def racing(source, target, **kwargs):
            Path(target).write_text("new user file")
            return real_symlink(source, target, **kwargs)
        report = dict(completed=[], recovery=[], saved_links=[])
        with patch.object(links.os, "symlink", side_effect=racing), self.assertRaises(FileExistsError):
            links.apply_plan(entries, report)
        self.assertEqual(target.read_text(), "new user file")
        records = json.loads(Path(report["recovery"][0]).read_text())
        self.assertEqual(os.readlink(records[0]["saved"]), str(old / "setup-trello"))
        self.assertEqual(report["completed"], [])

    def test_owner_entrypoint_works_through_installed_symlink(self):
        result, done = self.invoke("setup-trello", "--execute")
        self.assertEqual(result.returncode, 0, done)
        command = [sys.executable, str(self.dest / "setup-trello/scripts/link-skills.py"), "--client", "codex", "--skills-dir", str(self.dest)]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(x["action"] == "unchanged" for x in json.loads(result.stdout)["links"]))

    def test_bash_and_zsh_invoke_same_entrypoint(self):
        for shell in ["/bin/bash", "/bin/zsh"]:
            if not Path(shell).exists(): continue
            with self.subTest(shell=shell):
                result, plan = self.invoke("setup-slack", "--skill", "use-slack-messages", shell=shell)
                self.assertEqual(result.returncode, 0, result.stderr or plan)
                self.assertEqual({x["skill"] for x in plan["links"]}, {"setup-slack", "use-slack-messages"})

    def test_unrelated_capability_and_relative_paths_are_rejected(self):
        result, _ = self.invoke("setup-trello", "--skill", "use-gmail", "--execute")
        self.assertNotEqual(result.returncode, 0)
        result, _ = self.invoke("setup-trello", "--repair-from", "relative", "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
