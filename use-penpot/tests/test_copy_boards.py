"""Synthetic Penpot page data for the board copier; no credentials, network or live designs."""

import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/copy_boards.py"
SPEC = importlib.util.spec_from_file_location("copy_boards", SCRIPT)
CB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CB)
ZERO = CB.ZERO
FILE_ID = "11111111-2222-3333-4444-555555555555"
SOURCE_PAGE = "22222222-0000-0000-0000-000000000001"
TARGET_PAGE = "22222222-0000-0000-0000-000000000002"


def shape(sid, name, parent, frame, kind="rect", **extra):
    return {"id": sid, "name": name, "type": kind, "parentId": parent, "frameId": frame, "x": 0, "y": 0, "width": 100, "height": 50} | extra


def subtree():
    """A board with a button linked to a second board, a label linked outside the copied set, and a group of two shapes."""
    return {
        "board-a": shape("board-a", "Orders · Detail", ZERO, ZERO, "frame", shapes=["button", "label", "group"], x=0, y=0, width=400, height=300),
        "button": shape("button", "Button", "board-a", "board-a", interactions=[{"eventType": "click", "actionType": "navigate", "destination": "board-b"}]),
        "label": shape("label", "Label", "board-a", "board-a", "text", interactions=[{"eventType": "click", "actionType": "navigate", "destination": "elsewhere"}]),
        "group": shape("group", "Group", "board-a", "board-a", "group", shapes=["dot-1", "dot-2"]),
        "dot-1": shape("dot-1", "Dot 1", "group", "board-a", "circle"),
        "dot-2": shape("dot-2", "Dot 2", "group", "board-a", "circle"),
    }


def second_board():
    return {"board-b": shape("board-b", "Orders · Done", ZERO, ZERO, "frame", shapes=[], x=500, y=0, width=400, height=300)}


class PlanTests(unittest.TestCase):
    def plan(self, subtrees=None, target=None, revn=7):
        subtrees = subtrees or {"board-a": subtree(), "board-b": second_board()}
        return CB.plan_changes(FILE_ID, TARGET_PAGE, revn, subtrees, target or {})

    def test_copies_get_new_ids_and_parents_point_at_copies(self):
        plan = self.plan()
        ids = {c["obj"]["name"]: c["id"] for c in plan["changes"]}
        by_name = {c["obj"]["name"]: c for c in plan["changes"]}
        self.assertTrue(all(c["id"] not in subtree() for c in plan["changes"]))
        self.assertEqual(by_name["Orders · Detail"]["parentId"], ZERO)
        self.assertEqual(by_name["Orders · Detail"]["frameId"], ZERO)
        self.assertEqual(by_name["Dot 1"]["parentId"], ids["Group"])
        self.assertEqual(by_name["Dot 1"]["frameId"], ids["Orders · Detail"])
        self.assertTrue(all(c["pageId"] == TARGET_PAGE and c["type"] == "add-obj" for c in plan["changes"]))

    def test_parents_come_before_children_in_source_order_with_empty_child_lists(self):
        names = [c["obj"]["name"] for c in self.plan()["changes"]]
        self.assertEqual(names, ["Orders · Detail", "Button", "Label", "Group", "Dot 1", "Dot 2", "Orders · Done"])
        self.assertTrue(all(c["obj"].get("shapes", []) == [] for c in self.plan()["changes"]))

    def test_links_inside_the_copied_set_follow_and_others_are_dropped(self):
        plan = self.plan()
        by_name = {c["obj"]["name"]: c for c in plan["changes"]}
        self.assertEqual(by_name["Button"]["obj"]["interactions"][0]["destination"], by_name["Orders · Done"]["id"])
        self.assertEqual(by_name["Label"]["obj"]["interactions"], [])
        self.assertEqual(plan["dropped_links"], [{"shape": "Label", "board": "Orders · Detail", "destination": "elsewhere"}])

    def test_overlay_position_relative_to_a_copied_shape_follows(self):
        tree = subtree()
        tree["button"]["interactions"] = [{"eventType": "click", "actionType": "open-overlay", "destination": "board-b", "positionRelativeTo": "group"}]
        plan = self.plan({"board-a": tree, "board-b": second_board()})
        by_name = {c["obj"]["name"]: c for c in plan["changes"]}
        self.assertEqual(by_name["Button"]["obj"]["interactions"][0]["positionRelativeTo"], by_name["Group"]["id"])

    def test_source_data_is_not_modified(self):
        tree, before = subtree(), subtree()
        self.plan({"board-a": tree})
        self.assertEqual(tree, before)

    def test_ids_are_deterministic_for_one_revision_and_change_with_it(self):
        first, again, later = self.plan(revn=7), self.plan(revn=7), self.plan(revn=8)
        self.assertEqual([c["id"] for c in first["changes"]], [c["id"] for c in again["changes"]])
        self.assertNotEqual(first["changes"][0]["id"], later["changes"][0]["id"])

    def test_component_main_shapes_are_refused(self):
        tree = subtree()
        tree["button"]["mainInstance"] = True
        with self.assertRaisesRegex(CB.CopyError, "main shape"):
            self.plan({"board-a": tree})

    def test_missing_child_data_is_refused(self):
        tree = subtree()
        del tree["dot-2"]
        with self.assertRaisesRegex(CB.CopyError, "missing"):
            self.plan({"board-a": tree})

    def test_same_name_and_overlap_on_the_target_page_are_warned(self):
        target = {"existing": shape("existing", "Orders · Detail", ZERO, ZERO, "frame", x=100, y=100, width=400, height=300)}
        warnings = self.plan({"board-a": subtree()}, target)["warnings"]
        self.assertEqual(len(warnings), 2)
        self.assertIn("already has a board named", warnings[0])
        self.assertIn("overlaps", warnings[1])

    def test_digest_covers_the_changes_and_revision(self):
        plan = self.plan()
        full = plan | {"file": {"id": FILE_ID, "revn": 7}, "to_page": {"id": TARGET_PAGE}}
        changed = copy.deepcopy(full)
        changed["changes"][0]["obj"]["name"] = "Something else"
        self.assertEqual(CB.plan_digest(full), CB.plan_digest(copy.deepcopy(full)))
        self.assertNotEqual(CB.plan_digest(full), CB.plan_digest(changed))
        self.assertNotEqual(CB.plan_digest(full), CB.plan_digest(full | {"file": {"id": FILE_ID, "revn": 8}}))


class FakeServer:
    def __init__(self, objects=None):
        self.calls = []
        self.objects = objects or subtree()

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "get-file":
            return {"name": "Synthetic", "revn": 7, "vern": 0, "features": ["components/v2"], "data": {"pagesIndex": {SOURCE_PAGE: {"name": "Workshop"}, TARGET_PAGE: {"name": "Prototype"}}}}
        if method == "get-page" and params.get("objectId"):
            return {"objects": self.objects if params["pageId"] == SOURCE_PAGE else {}}
        if method == "get-page":
            return {"objects": {}}
        return None


class BuildTests(unittest.TestCase):
    def test_build_plan_reads_only_and_names_pages(self):
        server = FakeServer()
        plan = CB.build_plan(server, FILE_ID, SOURCE_PAGE, TARGET_PAGE, ["board-a"])
        self.assertEqual([m for m, _ in server.calls], ["get-file", "get-page", "get-page"])
        self.assertEqual((plan["from_page"]["name"], plan["to_page"]["name"], plan["file"]["revn"]), ("Workshop", "Prototype", 7))

    def test_only_top_level_boards_on_other_pages_of_the_file_are_accepted(self):
        with self.assertRaisesRegex(CB.CopyError, "top-level board"):
            CB.build_plan(FakeServer(), FILE_ID, SOURCE_PAGE, TARGET_PAGE, ["button"])
        with self.assertRaisesRegex(CB.CopyError, "must differ"):
            CB.build_plan(FakeServer(), FILE_ID, SOURCE_PAGE, SOURCE_PAGE, ["board-a"])
        with self.assertRaisesRegex(CB.CopyError, "target page is not in this file"):
            CB.build_plan(FakeServer(), FILE_ID, SOURCE_PAGE, "33333333-0000-0000-0000-000000000000", ["board-a"])

    def test_execute_sends_one_update_against_the_previewed_revision(self):
        server = FakeServer()
        plan = CB.build_plan(server, FILE_ID, SOURCE_PAGE, TARGET_PAGE, ["board-a"])
        server.calls.clear()
        CB.execute(server, plan)
        method, params = server.calls[0]
        self.assertEqual(method, "update-file")
        self.assertEqual((params["revn"], params["vern"], params["features"]), (7, 0, ["components/v2"]))
        self.assertEqual(len(params["changes"]), 6)

    def test_cli_refuses_execution_without_the_reviewed_digest(self):
        with patch.object(CB, "access_token", return_value="synthetic"), patch.object(CB, "curl_rpc", return_value=FakeServer()):
            code = CB.main(["--file-id", FILE_ID, "--from-page", SOURCE_PAGE, "--to-page", TARGET_PAGE, "--board", "board-a", "--execute", "--expect-plan", "0" * 64])
        self.assertEqual(code, 1)


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.env = patch.dict(os.environ, {"PENPOT_SETUP_DIR": self.dir.name}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("PENPOT_ACCESS_TOKEN", None)
        os.environ.pop("PENPOT_ENV_FILE", None)
        os.environ.pop("PENPOT_CONFIG_DIR", None)

    def write(self, text):
        Path(self.dir.name, ".env").write_text(text, encoding="utf-8")

    def test_reads_a_quoted_token_from_the_setup_env_file(self):
        self.write('# synthetic\nPENPOT_MCP_SERVER_URL=https://example.invalid/mcp\nexport PENPOT_ACCESS_TOKEN="synthetic-token"\n')
        self.assertEqual(CB.access_token(), "synthetic-token")

    def test_exported_token_takes_precedence(self):
        self.write("PENPOT_ACCESS_TOKEN=from-file\n")
        with patch.dict(os.environ, {"PENPOT_ACCESS_TOKEN": "from-environment"}):
            self.assertEqual(CB.access_token(), "from-environment")

    def test_missing_invalid_or_unsafe_configuration_fails_without_the_value(self):
        for text, message in (("PENPOT_ACCESS_TOKEN=\n", "not configured"), ("OTHER=1\n", "Invalid Penpot env key"), ("PENPOT_ACCESS_TOKEN='open\n", "Unclosed quote"), ("PENPOT_ACCESS_TOKEN=has space\n", "not configured")):
            self.write(text)
            with self.assertRaisesRegex(CB.CopyError, message) as caught:
                CB.access_token()
            self.assertNotIn("has space", str(caught.exception))

    def test_token_reaches_curl_on_standard_input_only(self):
        seen = {}

        def fake_run(args, input, capture_output, text):
            seen["args"], seen["input"] = args, input
            return type("Result", (), {"returncode": 0, "stdout": '{"ok": true}\n200'})()

        with patch.object(CB.subprocess, "run", fake_run):
            CB.curl_rpc("https://example.invalid", "synthetic-secret")("get-file", {"id": FILE_ID})
        self.assertNotIn("synthetic-secret", " ".join(seen["args"]))
        self.assertIn("Authorization: Token synthetic-secret", seen["input"])


if __name__ == "__main__":
    unittest.main()
