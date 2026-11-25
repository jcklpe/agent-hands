"""Stateful organization tests: execute the actual engine against a synthetic drive."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

spec = importlib.util.spec_from_file_location("organization", Path(__file__).parents[1] / "scripts/organization.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class Drive:
    alias = "example"
    def __init__(self):
        self.items = {
            "source": {"id": "source", "name": "a.txt", "size": 7, "eTag": '"one"', "file": {}, "parentReference": {"driveId": "drive", "id": "old"}},
            "old": {"id": "old", "name": "Old", "eTag": '"old"', "folder": {}, "parentReference": {"driveId": "drive", "id": "root-id"}},
            "new": {"id": "new", "name": "New", "eTag": '"new"', "folder": {}, "parentReference": {"driveId": "drive", "id": "root-id"}},
        }
        self.writes = []; self.allow = True; self.lost = False; self.bad_readback = False; self.changed_sharing = False
        self.permission = [{"id": "p", "roles": ["write"], "shareId": "SECRET", "link": {"webUrl": "SECRET", "scope": "organization"}}]
        self.versions = [{"id": "1.0", "size": 7}]
        self.paging = None

    def identity(self): return {"id": "me", "mail": "me@example.com"}
    def require_write(self):
        if not self.allow: raise ValueError("not opted in")

    def request(self, method, path, body=None, headers=None, output=None):
        parts = unquote(urlsplit(path).path).split("/"); item = parts[4] if len(parts) > 4 else None
        if method != "GET":
            self.writes.append((method, path, body, headers))
            if headers != {"If-Match": self.items[item]["eTag"]}: raise ValueError("412")
            if method == "DELETE": del self.items[item]
            else:
                self.items[item]["name"] = body["name"]
                if "parentReference" in body: self.items[item]["parentReference"]["id"] = body["parentReference"]["id"]
                self.items[item]["eTag"] = '"two"'
            if self.lost: raise RuntimeError("lost acknowledgment")
            return {}
        if self.writes and self.bad_readback: raise RuntimeError("readback unavailable")
        if len(parts) == 3: return {"id": "drive", "owner": {"user": {"id": "me"}}}
        if len(parts) == 5: return copy.deepcopy(self.items[item])
        kind = parts[5]
        if kind == "content": Path(output).write_bytes(b"content"); return {}
        if kind == "children":
            if self.paging: return self.paging(path)
            return {"value": [copy.deepcopy(v) for v in self.items.values() if v["parentReference"].get("id") == item]}
        if kind == "permissions":
            values = copy.deepcopy(self.permission)
            if self.writes and self.changed_sharing: values[0]["roles"] = ["read"]
            return {"value": values}
        if kind == "versions": return {"value": copy.deepcopy(self.versions)}
        raise AssertionError(path)


class Organization(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = mod.Store(Path(self.tmp.name) / "state", "example"); self.client = Drive()

    def plan(self, action="move"):
        return mod.preview(self.client, self.store, action, "drive", "source", "b.txt", "new" if action == "move" else None, reason="Disposable test file is no longer needed." if action == "recycle" else None)

    def apply(self, plan): return mod.apply(self.client, self.store, plan["operation"], plan["hash"], True)

    def test_move_verifies_identity_content_history_and_visible_sharing(self):
        p = self.plan(); self.assertEqual(self.client.writes, [])
        r = self.apply(p); self.assertEqual(r["status"], "verified"); self.assertTrue(all(r["checks"].values()))
        self.assertEqual(self.client.items["source"]["parentReference"]["id"], "new")
        self.assertTrue(self.client.writes[0][1].endswith("?@microsoft.graph.conflictBehavior=fail"))
        self.assertNotIn("SECRET", mod.canonical(p))

    def test_rename_does_not_move_and_replay_is_refused(self):
        p = self.plan("rename"); self.assertEqual(self.apply(p)["status"], "verified")
        self.assertNotIn("parentReference", self.client.writes[0][2])
        with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(p)
        self.assertEqual(len(self.client.writes), 1)

    def test_recycle_is_delete_only_and_checks_parent_absence(self):
        p = self.plan("recycle")
        self.assertEqual(p["deletionReview"]["files"], [{"name": "a.txt", "drive": "drive", "item": "source", "parent": "old", "reason": "Disposable test file is no longer needed."}])
        self.assertEqual(mod.apply(self.client, self.store, p["operation"], p["hash"], True, True)["status"], "recycle_request_verified")
        self.assertEqual(self.client.writes[0][0], "DELETE"); self.assertNotIn("permanent", self.client.writes[0][1])
        self.assertEqual(self.client.writes[0][3], {"If-Match": '"one"'})

    def test_recycle_requires_reason_and_separate_consent_before_dispatch(self):
        for reason in (None, " ", "x" * 301, "first\nsecond"):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "--reason"):
                mod.preview(self.client, self.store, "recycle", "drive", "source", reason=reason)
        p = self.plan("recycle")
        with self.assertRaisesRegex(ValueError, "separate, explicit consent"): self.apply(p)
        self.assertFalse(self.store.dispatched(p["operation"])); self.assertEqual(self.client.writes, [])

    def test_old_recycle_plan_and_generic_consent_cannot_bypass_itemized_review(self):
        p = self.plan("recycle")
        old = {k: v for k, v in p.items() if k not in ("deletionReview", "operation", "hash", "status", "limits")}
        old = self.store.plan(old)
        with self.assertRaisesRegex(ValueError, "fresh itemized"): mod.apply(self.client, self.store, old["operation"], old["hash"], True, True)
        rename = self.plan("rename")
        with self.assertRaisesRegex(ValueError, "only to a separately approved recycle"): mod.apply(self.client, self.store, rename["operation"], rename["hash"], True, True)
        self.assertFalse(self.store.dispatched(old["operation"])); self.assertEqual(self.client.writes, [])

    def test_stale_source_or_destination_never_writes(self):
        p = self.plan(); self.client.items["source"]["eTag"] = '"new revision"'
        with self.assertRaisesRegex(ValueError, "changed"): self.apply(p)
        self.assertEqual(self.client.writes, []); self.assertFalse(self.store.dispatched(p["operation"]))

    def test_collision_special_item_and_nonempty_folder_refused(self):
        self.client.items["collision"] = {"id": "collision", "name": "B.TXT", "parentReference": {"id": "new"}}
        with self.assertRaisesRegex(ValueError, "already exists"): self.plan()
        self.client.items.pop("collision"); self.client.items["source"]["package"] = {"type": "oneNote"}
        with self.assertRaisesRegex(ValueError, "unsupported"): self.plan()
        for action in ("move", "recycle"):
            with self.assertRaisesRegex(ValueError, "rename only"): mod.preview(self.client, self.store, action, "drive", "old", "Renamed", "new", reason="Test cleanup" if action == "recycle" else None)
        self.assertEqual(self.client.writes, [])

    def folder_plan(self):
        self.client.items["root-id"] = {"id": "root-id", "name": "Root", "root": {}, "folder": {}, "eTag": '"root"', "parentReference": {"driveId": "drive"}}
        return mod.preview(self.client, self.store, "rename", "drive", "old", "renamed")

    def test_folder_rename_preserves_children_and_parent(self):
        p = self.folder_plan()
        r = self.apply(p)
        self.assertEqual(r["status"], "verified")
        self.assertEqual(self.client.writes[0][2], {"name": "renamed"})
        self.assertEqual(self.client.items["source"]["parentReference"]["id"], "old")
        with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(p)

    def test_folder_child_added_without_folder_etag_change_refuses_write(self):
        p = self.folder_plan()
        self.client.items["another"] = {**copy.deepcopy(self.client.items["source"]), "id": "another", "name": "new.txt"}
        with self.assertRaisesRegex(ValueError, "changed"): self.apply(p)
        self.assertEqual(self.client.writes, [])

    def test_folder_child_content_etag_change_refuses_write(self):
        p = self.folder_plan()
        self.client.items["source"]["eTag"] = '"edited"'
        with self.assertRaisesRegex(ValueError, "changed"): self.apply(p)
        self.assertEqual(self.client.writes, [])

    def test_folder_rename_refuses_parent_change_and_root(self):
        self.folder_plan()
        with self.assertRaisesRegex(ValueError, "retain"): mod.preview(self.client, self.store, "rename", "drive", "old", "renamed", "new")
        with self.assertRaisesRegex(ValueError, "root"): mod.preview(self.client, self.store, "rename", "drive", "root-id", "renamed")
        self.assertEqual(self.client.writes, [])

    def test_failed_readback_and_lost_ack_remain_uncertain_without_retry(self):
        for flag in ("lost", "bad_readback"):
            with self.subTest(flag=flag):
                self.client = Drive(); p = self.plan(); setattr(self.client, flag, True)
                self.assertEqual(self.apply(p)["status"], "uncertain_after_dispatch")
                self.assertEqual(len(self.client.writes), 1)
                with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(p)

    def test_sharing_changes_are_reported_as_applied_review(self):
        p = self.plan(); self.client.changed_sharing = True
        r = self.apply(p); self.assertEqual(r["status"], "applied_review_required"); self.assertFalse(r["checks"]["visibleSharing"])

    def test_preview_hash_execute_and_opt_in_are_required(self):
        p = self.plan()
        for execute, hash_value in ((False, p["hash"]), (True, "bad")):
            with self.assertRaises(ValueError): mod.apply(self.client, self.store, p["operation"], hash_value, execute)
        self.client.allow = False
        with self.assertRaisesRegex(ValueError, "opted"): self.apply(p)
        self.assertEqual(self.client.writes, [])

    def test_continuation_is_explicit_and_bound_to_exact_collection(self):
        endpoint = "/drives/drive/items/new/children"
        self.client.paging = lambda path: {"value": [{"id": "one"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0" + endpoint + "?$skiptoken=next"} if "$skiptoken" not in path else {"value": [{"id": "two"}]}
        p = mod.page(self.client, "drive", "new", "children"); self.assertFalse(p["complete"])
        self.assertTrue(mod.page(self.client, "drive", "new", "children", p["continuation"])["complete"])
        with self.assertRaises(ValueError): mod.page(self.client, "drive", "old", "children", p["continuation"])
        self.assertEqual([v["id"] for v in mod.complete(self.client, "drive", "new", "children")], ["one", "two"])

    def test_arbitrary_continuation_and_incomplete_verification_refused(self):
        self.client.paging = lambda path: {"value": [], "@odata.nextLink": "https://evil.example/steal"}
        with self.assertRaisesRegex(ValueError, "outside"): mod.complete(self.client, "drive", "new", "children")
        self.client.paging = lambda path: {"value": [], "@odata.nextLink": "https://graph.microsoft.com/v1.0/drives/drive/items/new/children?$skiptoken=loop"}
        with self.assertRaisesRegex(ValueError, "Repeated"): mod.complete(self.client, "drive", "new", "children")

    def test_equivalent_continuation_encoding_retains_canonical_resource(self):
        paths = []
        def paging(path):
            paths.append(path)
            return {"value": [{"id": "one"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/drives/drive!test/items/new/children?$skiptoken=next"} if "$skiptoken" not in path else {"value": [{"id": "two"}]}
        self.client.paging = paging
        first = mod.page(self.client, "drive!test", "new", "children")
        second = mod.page(self.client, "drive!test", "new", "children", first["continuation"])
        self.assertTrue(second["complete"])
        self.assertTrue(all(p.startswith("/drives/drive%21test/items/new/children?") for p in paths))
        endpoint = "/drives/drive%21test/items/new/children"
        for target in ("other", "new%2Fother", "new%252Fother"):
            with self.assertRaisesRegex(ValueError, "outside"):
                mod.continuation("https://graph.microsoft.com/v1.0/drives/drive!test/items/" + target + "/children?$skiptoken=next", endpoint)

    def test_private_store_refuses_links_and_world_readable_data(self):
        p = self.plan(); target = self.store.path(p["operation"], ".plan.json"); target.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "Unsafe"): self.store.load(p["operation"])
        target.unlink(); target.symlink_to(Path(self.tmp.name) / "outside")
        with self.assertRaises(OSError): self.store.load(p["operation"])


if __name__ == "__main__": unittest.main()
