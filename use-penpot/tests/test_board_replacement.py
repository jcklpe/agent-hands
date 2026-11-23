"""Synthetic page data for board replacement, its private journal and recovery; no credentials, network or live designs."""

import copy
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import board_journal as BJ  # noqa: E402
import copy_boards as CB  # noqa: E402
import penpot_journal as PJ  # noqa: E402

ZERO = CB.ZERO
FILE_ID = "11111111-2222-3333-4444-555555555555"
SOURCE = "22222222-0000-0000-0000-000000000001"
TARGET = "22222222-0000-0000-0000-000000000002"


def shape(sid, name, parent, frame, kind="rect", **extra):
    return {"id": sid, "name": name, "type": kind, "parentId": parent, "frameId": frame, "x": 0, "y": 0, "width": 100, "height": 50} | extra


def source_page():
    return {"objects": {
        ZERO: shape(ZERO, "Root Frame", ZERO, ZERO, "frame", shapes=["s1", "s2", "w3"]),
        "s1": shape("s1", "Orders · Detail", ZERO, ZERO, "frame", shapes=["button", "label", "group"], width=400, height=300, hidden=False),
        "button": shape("button", "Button", "s1", "s1", interactions=[{"eventType": "click", "actionType": "navigate", "destination": "s2"}]),
        "label": shape("label", "Label", "s1", "s1", "text", interactions=[{"eventType": "click", "actionType": "navigate", "destination": "w3"}]),
        "group": shape("group", "Group", "s1", "s1", "group", shapes=["dot-1", "dot-2"]),
        "dot-1": shape("dot-1", "Dot 1", "group", "s1", "circle"),
        "dot-2": shape("dot-2", "Dot 2", "group", "s1", "circle"),
        "s2": shape("s2", "Orders · Done", ZERO, ZERO, "frame", shapes=[], x=500, width=400, height=300),
        "w3": shape("w3", "Help", ZERO, ZERO, "frame", shapes=[], x=1000, width=400, height=300),
    }}


def target_page():
    return {"objects": {
        ZERO: shape(ZERO, "Root Frame", ZERO, ZERO, "frame", shapes=["p0", "p1", "p2", "p3"]),
        "p0": shape("p0", "Home", ZERO, ZERO, "frame", shapes=["home-link"], x=-600, width=400, height=300),
        "home-link": shape("home-link", "Go to orders", "p0", "p0", interactions=[{"eventType": "click", "actionType": "navigate", "destination": "p1"}]),
        "p1": shape("p1", "Orders · Detail", ZERO, ZERO, "frame", shapes=["old-a", "old-b"], x=0, y=900, width=400, height=300, blocked=True),
        "old-a": shape("old-a", "Old heading", "p1", "p1", "text"),
        "old-b": shape("old-b", "Old card", "p1", "p1", "frame", shapes=[]),
        "p2": shape("p2", "Orders · Done", ZERO, ZERO, "frame", shapes=[], x=500, y=900, width=400, height=300),
        "p3": shape("p3", "Help", ZERO, ZERO, "frame", shapes=[], x=1000, y=900, width=400, height=300),
    }, "flows": {}}


def insert_at_index(elems, index, new):
    moved = set(new)
    return [e for e in elems[:index] if e not in moved] + list(new) + [e for e in elems[index:] if e not in moved]


class FakePenpot:
    """Applies add-obj and del-obj as Penpot does, keeps versions, and can fail or misbehave on request."""

    def __init__(self):
        self.revn, self.vern = 7, 0
        self.pages = {SOURCE: source_page(), TARGET: target_page()}
        self.snapshots, self.calls, self.hooks = [], [], {}

    def subtree(self, objects, root):
        return CB.subtree_order(objects, root)

    def __call__(self, method, params):
        self.calls.append(method)
        hook = self.hooks.get(method)
        if hook == "refused":
            raise CB.CopyError(f"{method}: HTTP 400 {{'type': 'validation'}}", "refused")
        if hook == "lost":
            raise CB.CopyError(f"{method}: curl failed (28)", "unknown")
        if callable(hook):
            hook(self, params)
        if method == "get-file":
            return {"name": "Synthetic", "revn": self.revn, "vern": self.vern, "features": ["components/v2"], "data": {"pages": [SOURCE, TARGET], "pagesIndex": {SOURCE: {"name": "Workshop"}, TARGET: {"name": "Prototype"}}}}
        if method == "get-page":
            page = self.pages[params["pageId"]]
            if params.get("objectId"):
                if params["objectId"] not in page["objects"]:
                    return {"objects": {}}
                return {"objects": {sid: copy.deepcopy(page["objects"][sid]) for sid in self.subtree(page["objects"], params["objectId"])}}
            return copy.deepcopy(page)
        if method == "create-file-snapshot":
            snap = {"id": str(uuid.uuid4()), "label": params.get("label"), "revn": self.revn, "lockedBy": None}
            self.snapshots.append(snap)
            return dict(snap)
        if method == "lock-file-snapshot":
            next(s for s in self.snapshots if s["id"] == params["id"])["lockedBy"] = "synthetic-profile"
            return None
        if method == "get-file-snapshots":
            return copy.deepcopy(self.snapshots)
        if method == "update-file":
            if params["vern"] != self.vern:
                raise CB.CopyError("update-file: HTTP 400 {'type': 'validation', 'code': 'vern-conflict'}", "refused")
            if hook == "lost-before":
                raise CB.CopyError("update-file: curl failed (28)", "unknown")
            for change in params["changes"]:
                objects = self.pages[change["pageId"]]["objects"]
                if change["type"] == "del-obj":
                    target = objects.get(change["id"])
                    if target:
                        for sid in self.subtree(objects, change["id"]):
                            objects.pop(sid)
                        parent = objects[target["parentId"]]
                        parent["shapes"] = [s for s in parent["shapes"] if s != change["id"]]
                elif change["type"] == "add-obj":
                    obj = copy.deepcopy(change["obj"])
                    if self.hooks.get("mangle") and obj["id"] != ZERO:
                        obj.pop("width", None)
                    objects[change["id"]] = obj
                    parent = objects[change["parentId"]]
                    shapes = list(parent.get("shapes") or [])
                    if change["id"] not in shapes:
                        shapes = shapes + [change["id"]] if change.get("index") is None else insert_at_index(shapes, change["index"], [change["id"]])
                    parent["shapes"] = shapes
            self.revn += 1
            if hook == "lost-after":
                raise CB.CopyError("update-file: curl failed (28)", "unknown")
            return {"revn": self.revn - 1, "lagged": [{"sessionId": params["sessionId"], "revn": self.revn}]}
        raise AssertionError(method)


class StateDir(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.TemporaryDirectory()
        self.addCleanup(self.state.cleanup)
        # macOS's temporary folder sits behind the /var symlink, which the journal refuses by design.
        env = patch.dict(os.environ, {PJ.STATE_ENV: os.path.realpath(self.state.name)})
        env.start()
        self.addCleanup(env.stop)
        self.server = FakePenpot()

    def copier(self, *args):
        return self.run_main(CB, ["--file-id", FILE_ID, "--from-page", SOURCE, "--to-page", TARGET, *args])

    def journal_cli(self, *args):
        return self.run_main(BJ, list(args))

    def run_main(self, module, argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(module, "access_token", return_value="synthetic"), patch.object(module, "curl_rpc", return_value=self.server), redirect_stdout(out), redirect_stderr(err):
            code = module.main(argv)
        return code, (json.loads(out.getvalue()) if out.getvalue().strip() else None), err.getvalue()

    def replace(self, *pairs, extra=()):
        args = [x for p in pairs for x in ("--replace", p)] + list(extra)
        code, preview, err = self.copier(*args)
        self.assertEqual(code, 0, err)
        code, done, err = self.copier(*args, "--execute", "--expect-plan", preview["plan_sha256"])
        return code, preview, done, err

    def records(self):
        return PJ.Journal(FILE_ID).records()


class PlanTests(StateDir):
    def plan(self, boards=(), replace=(), links=()):
        return CB.build_plan(self.server, FILE_ID, SOURCE, TARGET, list(boards), list(replace), list(links))

    def test_a_replaced_board_keeps_its_id_position_lock_and_hidden_state(self):
        plan = self.plan(replace=[("s1", "p1")])
        changes = plan["changes"]
        self.assertEqual(changes[0], {"type": "del-obj", "id": "p1", "pageId": TARGET, "ignoreTouched": True})
        root = changes[1]
        self.assertEqual((root["id"], root["index"], root["parentId"]), ("p1", 1, ZERO))
        self.assertTrue(root["obj"]["blocked"])
        self.assertNotIn("hidden", root["obj"])
        self.assertEqual((root["obj"]["x"], root["obj"]["y"]), (0, 0))
        children = [c for c in changes[2:] if c["parentId"] == "p1"]
        self.assertEqual([c["obj"]["name"] for c in children], ["Button", "Label", "Group"])
        self.assertTrue(all(c["id"] not in source_page()["objects"] for c in changes[2:]))
        self.assertEqual(plan["replacements"][0]["incoming_links_kept"], 1)
        self.assertEqual(plan["replacements"][0]["kept"], {"blocked": True})

    def test_links_follow_replacements_copies_and_explicit_mappings(self):
        plan = self.plan(replace=[("s1", "p1"), ("s2", "p2")], links=[("w3", "p3")])
        by_name = {c["obj"]["name"]: c["obj"] for c in plan["changes"] if c["type"] == "add-obj"}
        self.assertEqual(by_name["Button"]["interactions"][0]["destination"], "p2")
        self.assertEqual(by_name["Label"]["interactions"][0]["destination"], "p3")
        self.assertEqual(plan["dropped_links"], [])
        copied = self.plan(boards=["s2"], replace=[("s1", "p1")])
        button = next(c["obj"] for c in copied["changes"] if c.get("obj", {}).get("name") == "Button")
        self.assertEqual(button["interactions"][0]["destination"], copied["boards"][0]["copy_id"])
        self.assertEqual(copied["dropped_links"][0]["destination"], "w3")

    def test_same_named_copies_suggest_a_replacement(self):
        plan = self.plan(boards=["s1"])
        self.assertEqual(plan["suggestions"], [{"board": "Orders · Detail", "replace": "s1=p1"}])

    def test_unsafe_replacements_are_refused(self):
        cases = [
            ({"replace": [("s1", "old-a")]}, "not a top-level board on the target page"),
            ({"replace": [("s1", "p1"), ("s2", "p1")]}, "replaced more than once"),
            ({"boards": ["s1"], "replace": [("s1", "p1")]}, "listed more than once"),
            ({"replace": [("s1", "p1")], "links": [("s2", "p3"), ("s1", "p3")]}, "already follow the copy"),
        ]
        for kwargs, message in cases:
            with self.assertRaisesRegex(CB.CopyError, message):
                self.plan(**kwargs)
        self.server.pages[TARGET]["objects"]["old-a"]["mainInstance"] = True
        with self.assertRaisesRegex(CB.CopyError, "main shape"):
            self.plan(replace=[("s1", "p1")])

    def test_references_into_the_old_contents_are_refused(self):
        self.server.pages[TARGET]["objects"]["home-link"]["interactions"].append({"eventType": "click", "actionType": "open-overlay", "destination": "p2", "positionRelativeTo": "old-a"})
        with self.assertRaisesRegex(CB.CopyError, "inside a board being replaced"):
            self.plan(replace=[("s1", "p1")])
        self.server.pages[TARGET] = target_page() | {"flows": {"f1": {"name": "Checkout", "startingFrame": "old-b"}}}
        with self.assertRaisesRegex(CB.CopyError, "flow 'Checkout' starts inside"):
            self.plan(replace=[("s1", "p1")])

    def test_digest_covers_the_old_contents(self):
        first = CB.plan_digest(self.plan(replace=[("s1", "p1")]))
        self.server.pages[TARGET]["objects"]["old-a"]["name"] = "Edited heading"
        self.assertNotEqual(first, CB.plan_digest(self.plan(replace=[("s1", "p1")])))


class ExecuteTests(StateDir):
    def test_replacement_saves_a_locked_version_first_and_reads_everything_back(self):
        code, preview, done, err = self.replace("s1=p1")
        self.assertEqual(code, 0, err)
        calls = self.server.calls
        self.assertLess(calls.index("create-file-snapshot"), calls.index("update-file"))
        self.assertLess(calls.index("lock-file-snapshot"), calls.index("update-file"))
        self.assertEqual(self.server.snapshots[0]["label"], "Before replacing: Orders · Detail")
        self.assertEqual(self.server.snapshots[0]["lockedBy"], "synthetic-profile")
        self.assertTrue(done["all_match"])
        objects = self.server.pages[TARGET]["objects"]
        self.assertEqual(objects[ZERO]["shapes"], ["p0", "p1", "p2", "p3"])
        self.assertNotIn("old-a", objects)
        self.assertTrue(objects["p1"]["blocked"])
        self.assertEqual(objects["home-link"]["interactions"][0]["destination"], "p1")
        (record,) = self.records()
        self.assertEqual([h["stage"] for h in record.data["history"]], ["intent", "version_locked", "dispatched", "verified"])
        self.assertEqual([o["id"] for o in record.data["replacements"][0]["old_objects"]], ["p1", "old-a", "old-b"])
        self.assertEqual(stat.S_IMODE(record.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(record.path.parent.stat().st_mode), 0o700)

    def test_a_failed_version_save_stops_before_anything_is_deleted(self):
        self.server.hooks["create-file-snapshot"] = "refused"
        code, _, _, err = self.replace("s1=p1")
        self.assertEqual(code, 1)
        self.assertIn("nothing was replaced", err)
        self.assertNotIn("update-file", self.server.calls)
        self.assertEqual(self.records()[0].stage, "aborted")

    def test_a_change_after_the_version_stops_before_writing(self):
        def bump(server, params):
            server.revn += 1
        self.server.hooks["lock-file-snapshot"] = bump
        code, _, _, err = self.replace("s1=p1")
        self.assertEqual(code, 1)
        self.assertIn("changed after the preview", err)
        self.assertNotIn("update-file", self.server.calls)

    def test_a_refused_write_is_closed_without_changes(self):
        self.server.hooks["update-file"] = "refused"
        code, _, _, err = self.replace("s1=p1")
        self.assertEqual(code, 1)
        self.assertEqual(self.records()[0].stage, "refused")
        self.assertIn("old-a", self.server.pages[TARGET]["objects"])

    def test_an_unknown_outcome_blocks_that_board_until_reconciled(self):
        self.server.hooks["update-file"] = "lost-after"
        code, _, _, err = self.replace("s1=p1")
        self.assertEqual(code, 3)
        self.assertIn("will not be retried", err)
        self.assertEqual(self.server.calls.count("update-file"), 1)
        (record,) = self.records()
        self.assertEqual(record.stage, "uncertain")
        self.server.hooks.pop("update-file")
        code, preview, err = self.copier("--replace", "s1=p1")
        code, _, err = self.copier("--replace", "s1=p1", "--execute", "--expect-plan", preview["plan_sha256"])
        self.assertEqual(code, 1)
        self.assertIn("unresolved outcomes", err)
        code, result, _ = self.journal_cli("reconcile", "--journal", str(record.path))
        self.assertEqual((code, result["stage"]), (0, "verified"))
        code, _, _, err = self.replace("s2=p2")
        self.assertEqual(code, 0, err)

    def test_an_unchanged_board_counts_as_not_applied_only_after_settling(self):
        self.server.hooks["update-file"] = "lost-before"
        code, _, _, _ = self.replace("s1=p1")
        self.assertEqual(code, 3)
        (record,) = self.records()
        code, result, _ = self.journal_cli("reconcile", "--journal", str(record.path))
        self.assertEqual((code, result["stage"]), (2, "uncertain"))
        self.assertIn("reconcile again after", result["note"])
        later = PJ.now() + timedelta(minutes=11)
        with patch.object(PJ, "now", return_value=later):
            code, result, _ = self.journal_cli("reconcile", "--journal", str(record.path))
        self.assertEqual((code, result["stage"]), (0, "not_applied"))

    def test_a_readback_mismatch_blocks_until_the_user_accepts(self):
        self.server.hooks["mangle"] = True
        code, _, done, _ = self.replace("s1=p1")
        self.assertEqual(code, 2)
        self.assertFalse(done["all_match"])
        (record,) = self.records()
        self.assertEqual(record.stage, "mismatch")
        code, _, err = self.journal_cli("restore", "--journal", str(record.path))
        self.assertEqual(code, 1)
        self.assertIn("only a verified replacement", err)
        code, result, _ = self.journal_cli("accept", "--journal", str(record.path), "--note", "Kept after inspection")
        self.assertEqual((code, result["stage"]), (0, "accepted"))
        self.assertEqual(PJ.Journal(FILE_ID).blocking(["p1"]), [])

    def test_an_interrupted_record_is_closed_as_aborted(self):
        with PJ.Journal(FILE_ID) as journal:
            record = journal.create({"kind": "replace", "file_id": FILE_ID, "to_page": TARGET, "plan_sha256": "0" * 64, "replacements": [], "changes": []})
        code, result, _ = self.journal_cli("reconcile", "--journal", str(record.path))
        self.assertEqual((code, result["stage"]), (0, "aborted"))
        self.assertNotIn("get-page", self.server.calls)


class RestoreTests(StateDir):
    def test_restore_puts_the_old_contents_back_under_the_same_id(self):
        before = copy.deepcopy(self.server.pages[TARGET]["objects"])
        code, _, done, _ = self.replace("s1=p1")
        self.assertEqual(code, 0)
        path = done["journal"]
        code, preview, err = self.journal_cli("restore", "--journal", path)
        self.assertEqual(code, 0, err)
        code, result, err = self.journal_cli("restore", "--journal", path, "--execute", "--expect-plan", preview["plan_sha256"])
        self.assertEqual(code, 0, err)
        self.assertTrue(result["all_match"])
        after = self.server.pages[TARGET]["objects"]
        self.assertEqual({k: after[k] for k in before}, before)
        self.assertEqual(set(after), set(before))
        stages = {r.data["kind"]: r.stage for r in self.records()}
        self.assertEqual(stages, {"replace": "restored", "restore": "verified"})
        self.assertEqual(self.server.snapshots[-1]["label"], "Before restoring: Orders · Detail")

    def test_restore_refuses_a_board_changed_after_the_replacement(self):
        code, _, done, _ = self.replace("s1=p1")
        objects = self.server.pages[TARGET]["objects"]
        child = objects["p1"]["shapes"][0]
        objects[child]["name"] = "Edited later"
        code, _, err = self.journal_cli("restore", "--journal", done["journal"])
        self.assertEqual(code, 1)
        self.assertIn("changed after the replacement", err)


class JournalStorageTests(unittest.TestCase):
    def test_the_private_root_must_be_absolute_and_outside_checkouts(self):
        with patch.dict(os.environ, {PJ.STATE_ENV: "relative/state"}):
            with self.assertRaisesRegex(PJ.JournalError, "absolute"):
                PJ.root()
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, ".git").mkdir()
            with patch.dict(os.environ, {PJ.STATE_ENV: os.path.realpath(folder)}):
                with self.assertRaisesRegex(PJ.JournalError, "Git checkout"):
                    PJ.root()
        with tempfile.TemporaryDirectory() as folder:
            link = Path(os.path.realpath(folder), "linked")
            link.symlink_to(os.path.realpath(folder))
            with patch.dict(os.environ, {PJ.STATE_ENV: str(link)}):
                with self.assertRaisesRegex(PJ.JournalError, "symlink"):
                    PJ.root()

    def test_one_replacement_per_file_at_a_time(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {PJ.STATE_ENV: os.path.realpath(folder)}):
            with PJ.Journal(FILE_ID):
                with self.assertRaisesRegex(PJ.JournalError, "running"):
                    PJ.Journal(FILE_ID).__enter__()


if __name__ == "__main__":
    unittest.main()
