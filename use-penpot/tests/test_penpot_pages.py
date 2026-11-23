"""Synthetic manifests and page lists for penpot_pages; no credentials, network or live designs."""

import copy
import importlib.util
import io
import itertools
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/penpot_pages.py"
SPEC = importlib.util.spec_from_file_location("penpot_pages", SCRIPT)
PP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PP)
FILE_ID = "11111111-2222-3333-4444-555555555555"
P = {name: f"22222222-0000-0000-0000-00000000000{i}" for i, name in enumerate(["Workshop", "Notes", "Cover", "Prototype", "Scratchpad", "Archive"], 1)}


def manifest(**pages):
    return {"schema_version": 1, "files": [{"name": "Wireframes", "tool": "penpot", "url": f"https://design.penpot.app/#/workspace?team-id=x&file-id={FILE_ID}", "file_id": FILE_ID, "pages": pages or {"cover": "Cover", "prototype": "Prototype", "workshop": "Workshop", "scratchpad": "Scratchpad"}}]}


def file_data(order, revn=7, names=None):
    names = names or {pid: name for name, pid in P.items()}
    return {"name": "Wireframes", "revn": revn, "vern": 0, "features": ["components/v2", "fdata/objects-map"], "data": {"pages": list(order), "pagesIndex": {pid: {"id": pid, "name": names[pid], "objects": {}} for pid in order}}}


class FakeServer:
    """Applies mov-page changes with Penpot's insert-at-index semantics and raises revn by one per write."""

    def __init__(self, order, names=None, concurrent=None, fail=None):
        self.state = file_data(order, names=names)
        self.calls, self.concurrent, self.fail = [], concurrent, fail

    def __call__(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == "get-file":
            return copy.deepcopy(self.state)
        if method == "update-file":
            if self.fail == "refused":
                raise PP.BackendError("update-file: HTTP 400 {'type': 'validation'}", "refused")
            lagged = []
            if self.concurrent:
                self.concurrent(self.state)
                lagged.append({"sessionId": "someone-else", "revn": self.state["revn"]})
            pages = self.state["data"]["pages"]
            for change in params["changes"]:
                pages[:] = PP.insert_at_index(pages, change["index"], [change["id"]])
            self.state["revn"] += 1
            lagged.append({"sessionId": params["sessionId"], "revn": self.state["revn"]})
            if self.fail == "unknown":
                raise PP.BackendError("update-file: curl failed (28)", "unknown")
            return {"revn": self.state["revn"] - 1, "lagged": lagged}
        raise AssertionError(method)


def ids(*names):
    return [P[n] for n in names]


class ManifestTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "design-files.json")
            path.write_text(json.dumps(data), encoding="utf-8")
            return PP.load_manifest(path)

    def test_reads_single_and_owned_roles(self):
        files = self.load(manifest(cover="Cover", workshop=[{"page": "Workshop · Sam", "owner": "Sam"}, {"page": "Workshop · Ana", "owner": "Ana"}], archive="Archive"))
        roles = files[0]["roles"]
        self.assertEqual(roles["cover"], [{"page": "Cover"}])
        self.assertEqual(roles["workshop"], [{"page": "Workshop · Sam", "owner": "Sam"}, {"page": "Workshop · Ana", "owner": "Ana"}])
        self.assertEqual(files[0]["origin"], "https://design.penpot.app")

    def test_other_tools_are_listed_but_not_parsed(self):
        data = manifest()
        data["files"].append({"name": "Elsewhere", "tool": "figma", "file_id": "abcDEF123", "url": "https://www.figma.com/design/abcDEF123", "pages": {"cover": "Cover"}})
        files = self.load(data)
        self.assertEqual(files[1]["tool"], "figma")
        self.assertIn("not use-penpot", files[1]["notes"][0])

    def test_contract_violations_are_refused(self):
        cases = [
            ({"schema_version": 2, "files": []}, "schema_version 1"),
            (manifest(archive=["Archive"]), "single page name"),
            (manifest(cover="Same", prototype="Same"), "both cover and prototype"),
            (manifest(cover=""), "empty page name"),
            (manifest(workshop=[{"owner": "Sam"}]), "page name"),
        ]
        bad_url = manifest()
        bad_url["files"][0]["url"] = "https://design.penpot.app/#/workspace?file-id=99999999-2222-3333-4444-555555555555"
        cases.append((bad_url, "names file"))
        bad_id = manifest()
        bad_id["files"][0]["file_id"] = "not-a-uuid"
        cases.append((bad_id, "not a Penpot file ID"))
        for data, message in cases:
            with self.assertRaisesRegex(PP.PagesError, message):
                self.load(data)

    def test_unknown_roles_and_surrounding_spaces_are_noted(self):
        notes = self.load(manifest(cover="Cover", sketches="Ideas", staging="Staging "))[0]["notes"]
        self.assertTrue(any("'sketches'" in n for n in notes))
        self.assertTrue(any("surrounding spaces" in n for n in notes))

    def test_missing_manifest_names_the_remedy(self):
        with self.assertRaisesRegex(PP.PagesError, "--manifest"):
            PP.load_manifest("/nonexistent/design-files.json")

    def test_a_manifest_on_another_instance_is_not_sent_the_token(self):
        entry = self.load(manifest())[0] | {"origin": "https://penpot.example.org"}
        with self.assertRaisesRegex(PP.PagesError, "--base-url https://penpot.example.org"):
            PP.check_origin(entry, "https://design.penpot.app")


class ResolveTests(unittest.TestCase):
    def test_matches_names_exactly_and_reports_gaps(self):
        entry = PP.parse_file(manifest(cover="Cover", prototype="prototype", workshop="Workshop", showroom="Showroom")["files"][0], 0)
        report = PP.resolve(entry, file_data(ids("Workshop", "Notes", "Cover", "Prototype")))
        self.assertEqual(report["roles"]["cover"][0]["page_id"], P["Cover"])
        self.assertEqual(report["roles"]["cover"][0]["position"], 2)
        self.assertEqual(report["missing"], [{"role": "prototype", "page": "prototype", "similar_names": ["Prototype"]}, {"role": "showroom", "page": "Showroom"}])
        self.assertEqual([p["name"] for p in report["unmapped_pages"]], ["Notes", "Prototype"])

    def test_duplicate_page_names_are_ambiguous(self):
        names = {P["Workshop"]: "Workshop", P["Notes"]: "Workshop"}
        entry = PP.parse_file(manifest(workshop="Workshop")["files"][0], 0)
        report = PP.resolve(entry, file_data(ids("Workshop", "Notes"), names=names))
        self.assertEqual(report["ambiguous"][0]["page_ids"], ids("Workshop", "Notes"))
        self.assertNotIn("page_id", report["roles"]["workshop"][0])

    def test_discover_reads_only(self):
        server = FakeServer(ids("Workshop", "Cover"))
        PP.discover([PP.parse_file(manifest()["files"][0], 0)], server)
        self.assertEqual([m for m, _ in server.calls], ["get-file"])


class OrderPlanTests(unittest.TestCase):
    def test_unlisted_pages_keep_their_positions(self):
        current = ids("Workshop", "Notes", "Cover", "Prototype")
        desired, changes = PP.plan_order(current, ids("Cover", "Prototype", "Workshop"))
        self.assertEqual(desired, ids("Cover", "Notes", "Prototype", "Workshop"))
        self.assertEqual(changes, [{"type": "mov-page", "id": P["Cover"], "index": 0}, {"type": "mov-page", "id": P["Workshop"], "index": 4}])

    def test_moves_reproduce_the_order_under_penpots_semantics(self):
        current = ids("Archive", "Scratchpad", "Prototype", "Workshop", "Notes", "Cover")
        wanted = ids("Cover", "Prototype", "Workshop", "Scratchpad", "Archive")
        desired, changes = PP.plan_order(current, wanted)
        working = list(current)
        for change in changes:
            working = PP.insert_at_index(working, change["index"], [change["id"]])
        self.assertEqual(working, desired)
        self.assertEqual(desired[4], P["Notes"])

    def test_only_listed_pages_are_moved_in_every_arrangement(self):
        pages = ids("Workshop", "Notes", "Cover", "Prototype", "Archive")
        for current in itertools.permutations(pages):
            for wanted in itertools.permutations(ids("Cover", "Prototype", "Workshop")):
                desired, changes = PP.plan_order(list(current), list(wanted))
                working = list(current)
                for change in changes:
                    working = PP.insert_at_index(working, change["index"], [change["id"]])
                self.assertEqual(working, desired)
                self.assertTrue({c["id"] for c in changes} <= set(wanted))
                for pid in (P["Notes"], P["Archive"]):
                    self.assertEqual(desired.index(pid), current.index(pid))

    def test_insert_at_index_matches_penpot(self):
        # (insert-at-index [a b c d] 2 [a]) is [b a c d]: the index counts positions before the page is removed.
        self.assertEqual(PP.insert_at_index(["a", "b", "c", "d"], 2, ["a"]), ["b", "a", "c", "d"])
        self.assertEqual(PP.insert_at_index(["a", "b", "c", "d"], 0, ["d"]), ["d", "a", "b", "c"])

    def test_an_order_already_in_place_needs_no_changes(self):
        current = ids("Cover", "Prototype")
        self.assertEqual(PP.plan_order(current, current), (current, []))

    def test_duplicates_and_foreign_pages_are_refused(self):
        with self.assertRaisesRegex(PP.PagesError, "more than once"):
            PP.plan_order(ids("Cover", "Workshop"), ids("Cover", "Cover"))
        with self.assertRaisesRegex(PP.PagesError, "Not pages of this file"):
            PP.plan_order(ids("Cover"), ["33333333-0000-0000-0000-000000000000"])

    def test_names_must_be_unique_and_exact(self):
        info = file_data(ids("Workshop", "Notes"), names={P["Workshop"]: "Workshop", P["Notes"]: "Workshop"})
        with self.assertRaisesRegex(PP.PagesError, "2 pages are named"):
            PP.resolve_pages(info, ["Workshop"])
        with self.assertRaisesRegex(PP.PagesError, "similar"):
            PP.resolve_pages(file_data(ids("Workshop")), ["workshop"])

    def test_digest_binds_the_revision(self):
        server = FakeServer(ids("Workshop", "Cover"))
        first = PP.order_digest(PP.build_order_plan(server, FILE_ID, ["Cover", "Workshop"]))
        server.state["revn"] = 8
        self.assertNotEqual(first, PP.order_digest(PP.build_order_plan(server, FILE_ID, ["Cover", "Workshop"])))


class ExecuteTests(unittest.TestCase):
    def run_cli(self, server, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(PP, "access_token", return_value="synthetic"), patch.object(PP, "curl_rpc", return_value=server), redirect_stdout(out), redirect_stderr(err):
            code = PP.main(list(args))
        return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()

    def preview(self, server, *pages):
        args = ["order", "--file-id", FILE_ID] + [x for p in pages for x in ("--page", p)]
        code, report, _ = self.run_cli(server, *args)
        self.assertEqual(code, 0)
        return args, report

    def test_preview_writes_nothing_and_execute_verifies_the_whole_order(self):
        server = FakeServer(ids("Workshop", "Notes", "Cover", "Prototype"))
        args, report = self.preview(server, "Cover", "Prototype", "Workshop")
        self.assertEqual([m for m, _ in server.calls], ["get-file"])
        self.assertEqual(report["moved"], ["Cover", "Workshop"])
        code, done, _ = self.run_cli(server, *args, "--execute", "--expect-plan", report["plan_sha256"])
        self.assertEqual(code, 0)
        self.assertTrue(done["verified"])
        self.assertEqual([p["name"] for p in done["result"]["actual_order"]], ["Cover", "Notes", "Prototype", "Workshop"])
        update = [p for m, p in server.calls if m == "update-file"]
        self.assertEqual(len(update), 1)
        self.assertEqual(update[0]["revn"], 7)

    def test_a_stale_or_missing_digest_is_refused_without_writing(self):
        server = FakeServer(ids("Workshop", "Cover"))
        args, report = self.preview(server, "Cover", "Workshop")
        server.state["revn"] = 8
        for expect in (report["plan_sha256"], "0" * 64):
            code, _, err = self.run_cli(server, *args, "--execute", "--expect-plan", expect)
            self.assertEqual(code, 1)
            self.assertIn("preview again", err)
        self.assertNotIn("update-file", [m for m, _ in server.calls])

    def test_an_order_already_in_place_writes_nothing(self):
        server = FakeServer(ids("Cover", "Workshop"))
        args, report = self.preview(server, "Cover", "Workshop")
        code, done, _ = self.run_cli(server, *args, "--execute", "--expect-plan", report["plan_sha256"])
        self.assertEqual((code, done["verified"]), (0, True))
        self.assertNotIn("update-file", [m for m, _ in server.calls])

    def test_a_concurrent_page_change_fails_the_readback_and_is_reported(self):
        def add_page(state):
            extra = "44444444-0000-0000-0000-000000000000"
            state["data"]["pages"].append(extra)
            state["data"]["pagesIndex"][extra] = {"id": extra, "name": "Someone's page", "objects": {}}
            state["revn"] += 1

        server = FakeServer(ids("Workshop", "Cover"), concurrent=add_page)
        args, report = self.preview(server, "Cover", "Workshop")
        code, done, err = self.run_cli(server, *args, "--execute", "--expect-plan", report["plan_sha256"])
        self.assertEqual(code, 2)
        self.assertFalse(done["verified"])
        self.assertEqual(done["result"]["concurrent_changes"], 1)
        self.assertIn("preview again", err)

    def test_an_unknown_outcome_reports_the_readback_and_does_not_retry(self):
        server = FakeServer(ids("Workshop", "Cover"), fail="unknown")
        args, report = self.preview(server, "Cover", "Workshop")
        code, _, err = self.run_cli(server, *args, "--execute", "--expect-plan", report["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn('"order": "proposed"', err)
        self.assertIn("do not repeat", err)
        self.assertEqual([m for m, _ in server.calls].count("update-file"), 1)

    def test_a_refused_write_is_a_plain_failure(self):
        server = FakeServer(ids("Workshop", "Cover"), fail="refused")
        args, report = self.preview(server, "Cover", "Workshop")
        code, _, err = self.run_cli(server, *args, "--execute", "--expect-plan", report["plan_sha256"])
        self.assertEqual(code, 1)
        self.assertIn("HTTP 400", err)

    def test_manifest_selection_supplies_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "design-files.json")
            path.write_text(json.dumps(manifest()), encoding="utf-8")
            server = FakeServer(ids("Workshop", "Cover"))
            code, report, _ = self.run_cli(server, "order", "--manifest", str(path), "--page", "Cover", "--page", "Workshop")
            self.assertEqual((code, report["file"]["id"]), (0, FILE_ID))
            code, _, err = self.run_cli(server, "order", "--manifest", str(path), "--file-id", "99999999-2222-3333-4444-555555555555", "--page", "Cover")
            self.assertEqual(code, 1)
            self.assertIn("differs", err)
            other = manifest()
            other["files"][0] |= {"tool": "figma", "file_id": "abcDEF123", "url": "https://www.figma.com/design/abcDEF123"}
            path.write_text(json.dumps(other), encoding="utf-8")
            code, _, err = self.run_cli(server, "order", "--manifest", str(path), "--page", "Cover")
            self.assertEqual(code, 1)
            self.assertIn("only Penpot files", err)


class TransportTests(unittest.TestCase):
    def result(self, code, stdout=""):
        return type("Result", (), {"returncode": code, "stdout": stdout})()

    def test_write_outcomes_are_classified(self):
        cases = [
            (self.result(7), "not_sent"),
            (self.result(28), "unknown"),
            (self.result(0, '{"type": "validation", "code": "revn-conflict"}\n400'), "refused"),
            (self.result(0, "<html>gateway timeout</html>\n524"), "unknown"),
        ]
        for result, outcome in cases:
            with patch("subprocess.run", return_value=result):
                with self.assertRaises(PP.BackendError) as caught:
                    PP.curl_rpc("https://example.invalid", "synthetic")("update-file", {})
            self.assertEqual(caught.exception.outcome, outcome)


if __name__ == "__main__":
    unittest.main()
