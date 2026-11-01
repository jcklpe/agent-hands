"""Native Projects provisioning, preview, readback and recovery checks."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from project_fixture import CLI, ROOT, ProjectFixture, fixture


class ProjectsCollaborationTests(ProjectFixture, unittest.TestCase):
    def test_selected_project_read_has_complete_bounded_families(self):
        result = self.call("read-project", "--fields", "project,fields,views,workflows,repositories,items")
        self.assertTrue(result["coverage"]["revision_stable"])
        self.assertTrue(all(v["complete"] for v in result["coverage"].values() if isinstance(v, dict)))
        self.assertEqual(result["project"]["id"], "PROJECT_1")
        self.assert_no_writes()

    def test_owner_number_alias_and_personal_project_selection(self):
        result = self.call("read-project", "--project-number", 1, selector=False)
        self.assertEqual(result["project"]["id"], "PROJECT_1")
        self.assertEqual(self.call("read-project", repo="example", selector=False)["project"]["id"], "PROJECT_1")
        self.state["owners"]["example-owner"]["type"] = "User"
        self.project["meta"]["url"] = "https://github.com/users/example-owner/projects/1"
        self.save()
        self.assertEqual(self.call("read-project", "--project-number", 1, selector=False)["project"]["id"], "PROJECT_1")

    def test_target_owner_number_and_host_mismatches_refuse(self):
        for flags in (("--owner", "other-owner"), ("--project-number", 99), ("--host", "wrong.example")):
            with self.subTest(flags=flags):
                self.call("link-repository", *flags, code=None)
                self.assert_no_writes()

    def test_preview_never_creates_a_journal_or_sends_mutation(self):
        result = self.call("link-repository")
        self.assertEqual(result["writes_sent"], 0)
        self.assert_no_writes()
        self.assertFalse((self.checkout / ".github/project-collaboration").exists())

    def test_repository_link_is_independent_and_repeat_is_noop(self):
        self.project["repositories"] = [{"id": "REPO_OTHER", "nameWithOwner": "example-owner/other"}]
        self.save()
        self.assertEqual(self.apply("link-repository")["outcome"], "success")
        self.assertEqual({v["id"] for v in self.load()["projects"]["PROJECT_1"]["repositories"]}, {"REPO_1", "REPO_OTHER"})
        self.assertTrue(self.apply("link-repository")["already_satisfied"])
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_project_create_and_duplicate_title_refusal(self):
        result = self.apply("create-project", "--title", "New literal $() `title`", "--link-repository", selector=False)
        self.assertEqual(result["steps"][0]["proof"]["project_id"], "PROJECT_2")
        self.assertFalse(result["steps"][0]["proof"]["public"])
        state = self.load()
        self.assertEqual(state["projects"]["PROJECT_2"]["meta"]["title"], "New literal $() `title`")
        self.assertEqual(state["projects"]["PROJECT_2"]["repositories"][0]["id"], "REPO_1")
        self.call("create-project", "--title", "New literal $() `title`", selector=False, code=2)
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_copy_project_preserves_source_and_excludes_items_and_links(self):
        original = copy.deepcopy(self.project)
        result = self.apply("copy-project", "--title", "Copied project", "--new-owner", "other-owner")
        self.assertEqual(result["outcome"], "success")
        state = self.load()
        self.assertEqual(state["projects"]["PROJECT_1"], original)
        self.assertFalse(state["projects"]["PROJECT_2"]["items"])
        self.assertFalse(state["projects"]["PROJECT_2"]["repositories"])
        inputs = state["mutations"][0]["variables"]["input"]
        self.assertFalse(inputs["includeDraftIssues"])
        self.assertEqual(inputs["ownerId"], "OWNER_2")

    def test_create_recovers_lost_response_without_duplicate(self):
        self.state["lose_response"] = True
        self.save()
        result = self.apply("create-project", "--title", "Recovery project", selector=False, code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.load().pop("lose_response")
        self.save()
        recovered = self.call("recover", "--operation-id", result["operation_id"], selector=False)
        self.assertEqual(recovered["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_recovery_refuses_ambiguous_creation_until_exact_result_selected(self):
        self.state["lose_response"] = True
        self.save()
        result = self.apply("create-project", "--title", "Ambiguous project", selector=False, code=3)
        self.load().pop("lose_response")
        duplicate = copy.deepcopy(self.state["projects"]["PROJECT_2"])
        duplicate["meta"].update(id="PROJECT_3", number=3, url="https://github.com/orgs/example-owner/projects/3")
        self.state["projects"]["PROJECT_3"] = duplicate
        self.save()
        self.call("recover", "--operation-id", result["operation_id"], selector=False, code=3)
        self.assertEqual(self.call("recover", "--operation-id", result["operation_id"], "--result-id", "PROJECT_2", selector=False)["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_fields_preserve_existing_option_ids_and_unselected_options(self):
        options = self.json_file("options.json", [{"name": "Ready", "color": "BLUE"}, {"name": "New stage", "color": "YELLOW"}])
        result = self.apply("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", options)
        self.assertEqual(result["outcome"], "success")
        field = self.load()["projects"]["PROJECT_1"]["fields"][0]
        self.assertEqual([v["name"] for v in field["options"]], ["Ready", "New stage", "Waiting", "Done"])
        self.assertEqual({v["name"]: v["id"] for v in field["options"] if v["name"] != "New stage"}, {"Ready": "READY", "Waiting": "WAITING", "Done": "DONE"})
        self.assertEqual(self.project["fields"][1]["id"], "FIELD_NOTE")
        self.assertTrue(self.apply("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", options)["already_satisfied"])
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_option_id_swapping_is_uncertain_despite_matching_names(self):
        options = self.json_file("options.json", [{"name": "Ready", "color": "BLUE"}])
        self.state["swap_option_ids"] = True
        self.save()
        result = self.apply("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", options, code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_explicit_option_rename_preserves_card_ids_and_omitted_metadata(self):
        self.project["fields"][0]["options"][0]["description"] = "Retain this description"
        self.save()
        options = self.json_file("rename.json", [{"id": "WAITING", "name": "Backlog"}])
        result = self.apply("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", options)
        self.assertEqual(result["outcome"], "success")
        p = self.load()["projects"]["PROJECT_1"]
        self.assertEqual(p["fields"][0]["options"][0], {"id": "WAITING", "name": "Backlog", "color": "GRAY", "description": "Retain this description"})
        self.assertEqual(p["items"][0]["fieldValueByName"]["optionId"], "WAITING")

    def test_option_rename_collision_or_foreign_id_refuses(self):
        for value in ([{"id": "FOREIGN", "name": "New"}], [{"id": "WAITING", "name": "Done"}], [{"id": "WAITING", "name": "New"}, {"id": "WAITING", "name": "Other"}]):
            options = self.json_file("bad-rename.json", value)
            self.call("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", options, code=2)
            self.assert_no_writes()

    def test_unrelated_field_loss_is_uncertain(self):
        options = self.json_file("options.json", [{"name": "Ready", "color": "BLUE"}])
        self.state["drop_unrelated_field"] = True
        self.save()
        self.assertEqual(self.apply("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", options, code=3)["outcome"], "uncertain")

    def test_create_field_and_type_conflict_refusal(self):
        result = self.apply("ensure-field", "--name", "Estimate", "--data-type", "NUMBER")
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(self.apply("ensure-field", "--name", "Estimate", "--data-type", "NUMBER")["already_satisfied"])
        self.call("ensure-field", "--name", "Estimate", "--data-type", "DATE", code=2)

    def test_invalid_or_ambiguous_options_and_fields_never_send(self):
        for values in ([], [{"name": "Same"}, {"name": "Same"}], [{"name": "Stage", "color": "INVALID"}], [{"name": "Stage", "id": "INJECTED"}]):
            selected = self.json_file("bad.json", values)
            self.call("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", selected, code=2)
            self.assert_no_writes()
        self.project["fields"].append(copy.deepcopy(self.project["fields"][0]))
        self.save()
        self.call("ensure-field", "--name", "Status", "--data-type", "SINGLE_SELECT", "--options-file", selected, code=None)
        self.assert_no_writes()

    def test_view_create_edit_filter_and_visible_fields_preserve_others(self):
        self.assertEqual(self.apply("create-view", "--name", "Backlog", "--layout", "table")["outcome"], "success")
        self.assertTrue(self.apply("create-view", "--name", "Backlog", "--layout", "table")["already_satisfied"])
        old = copy.deepcopy(self.load()["projects"]["PROJECT_1"]["views"][1])
        result = self.apply("edit-view", "--view-id", "VIEW_1", "--filter", "label:blocked", "--visible-field", "FIELD_STATUS")
        self.assertEqual(result["outcome"], "success")
        views = self.load()["projects"]["PROJECT_1"]["views"]
        self.assertEqual(views[0]["filter"], "label:blocked")
        self.assertEqual(views[0]["visible"], ["FIELD_STATUS", "FIELD_NOTE"])
        self.assertEqual(views[1], old)
        self.assertTrue(self.apply("edit-view", "--view-id", "VIEW_1", "--filter", "label:blocked", "--visible-field", "FIELD_STATUS")["already_satisfied"])

    def test_wrong_or_missing_view_parent_and_fields_refuse(self):
        self.call("edit-view", "--view-id", "OTHER_VIEW", "--name", "New", code=2)
        self.call("edit-view", "--view-id", "VIEW_1", "--visible-field", "FOREIGN_FIELD", code=2)
        self.assert_no_writes()
        self.project["views"][0]["project"]["id"] = "FOREIGN_PROJECT"
        self.save()
        self.call("edit-view", "--view-id", "VIEW_1", "--name", "New", code=2)
        self.assert_no_writes()

    def test_view_configuration_create_and_repeat_noop(self):
        result = self.apply("create-view", "--name", "Table", "--layout", "table", "--visible-field", "FIELD_STATUS")
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(self.apply("create-view", "--name", "Table", "--layout", "table", "--visible-field", "FIELD_STATUS")["already_satisfied"])
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_unreadable_configuration_is_explicit_and_not_overwritten(self):
        self.state["visible_error"] = True
        self.save()
        read = self.call("read-view", "--view-id", "VIEW_1")
        self.assertFalse(read["coverage"]["visible_fields"]["complete"])
        self.call("edit-view", "--view-id", "VIEW_1", "--visible-field", "FIELD_STATUS", code=1)
        self.assert_no_writes()

    def test_add_issue_and_pr_is_separate_from_status_changes(self):
        self.assertTrue(self.apply("add-item", "--issue", 1)["already_satisfied"])
        result = self.apply("add-item", "--pr", 2)
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(self.load()["projects"]["PROJECT_1"]["items"][1]["content"]["id"], "PR_2")
        self.call("move-card", "--issue", 99, "--status", "Ready", code=2)
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_automation_mapping_outputs_only_verified_nonsecret_ids_disabled(self):
        mapping = self.json_file("mapping.json", {"entry": "Waiting", "done": "Done", "reopen": "Waiting", "ready": "Ready"})
        result = self.call("automation-config", "--mapping-file", mapping)
        self.assertEqual(result["variables"]["PW_ENTRY_OPTION_ID"], "WAITING")
        self.assertEqual(result["variables"]["PW_DONE_OPTION_ID"], "DONE")
        self.assertEqual(result["variables"]["PW_AUTOMATION_ENABLED"], "false")
        self.assertEqual(result["variables"]["PW_NATIVE_SETTINGS_VERIFIED"], "false")
        self.assert_no_writes()

    def test_unknown_lifecycle_role_or_status_refuses(self):
        for value in ({"entry": "Missing", "done": "Done"}, {"entry": "Waiting", "done": "Done", "secret": "not allowed"}):
            mapping = self.json_file("bad-mapping.json", value)
            self.call("automation-config", "--mapping-file", mapping, code=2)
            self.assert_no_writes()

    def test_stale_project_or_option_invalidates_preview(self):
        preview = self.call("move-card", "--issue", 1, "--status", "Ready")
        self.load()["projects"]["PROJECT_1"]["fields"][0]["options"][1]["name"] = "Changed stage"
        self.save()
        self.call("move-card", "--issue", 1, "--status", "Ready", "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", preview["operation_id"], code=2)
        self.assert_no_writes()

    def test_final_refresh_under_lock_refuses_concurrent_change(self):
        preview = self.call("link-repository")
        state = self.load()
        state["race_at_read"] = state["project_reads"] + 2
        self.save()
        self.call("link-repository", "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", preview["operation_id"], code=2)
        self.assert_no_writes()

    def test_actor_mismatch_and_missing_execution_guards_refuse(self):
        self.state["actor"]["login"] = "other-user"
        self.save()
        self.call("link-repository", code=2)
        self.assert_no_writes()
        self.state["actor"]["login"] = "example-user"
        self.save()
        self.call("link-repository", "--execute", code=2)
        self.assert_no_writes()

    def test_journal_must_be_ignored_and_never_contains_payload_text(self):
        (self.checkout / ".gitignore").write_text("")
        self.apply("create-project", "--title", "Private payload text", selector=False, code=2)
        self.assert_no_writes()
        (self.checkout / ".gitignore").write_text("/.github/project-collaboration/\n")
        result = self.apply("create-project", "--title", "Private payload text", selector=False)
        records = list((self.checkout / ".github/project-collaboration").rglob("*.json"))
        self.assertEqual(len(records), 1)
        value = records[0].read_text()
        self.assertNotIn("Private payload text", value)
        self.assertIn("PROJECT_2", value)
        self.assertEqual(records[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["outcome"], "success")

    def test_missing_or_limited_collection_blocks_provisioning(self):
        self.call("ensure-field", "--name", "New", "--data-type", "TEXT", "--item-limit", 1, code=4)
        self.assert_no_writes()
        self.state["incomplete_family"] = "fields"
        self.save()
        self.call("ensure-field", "--name", "New", "--data-type", "TEXT", "--page-limit", 1, code=4)
        self.assert_no_writes()

    def test_wrong_mutation_result_is_uncertain_and_recovery_reads_only(self):
        self.state["wrong_result_id"] = "WRONG_ID"
        self.save()
        result = self.apply("move-card", "--issue", 1, "--status", "Ready", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.load().pop("wrong_result_id")
        self.save()
        self.assertEqual(self.call("recover", "--operation-id", result["operation_id"])["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_denied_post_send_readback_retains_uncertainty_then_recovers(self):
        self.state["deny_readback"] = True
        self.save()
        result = self.apply("link-repository", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        record_path = next((self.checkout / ".github/project-collaboration").rglob("*.json"))
        record = json.loads(record_path.read_text())
        self.assertEqual(record["steps"][0]["returned"], {"node_id": "REPO_1"})
        self.assertEqual(record["steps"][0]["status"], "uncertain")
        state = self.load()
        state.pop("deny_readback")
        self.save()
        self.assertEqual(self.call("recover", "--operation-id", result["operation_id"])["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_known_mutation_refusal_is_failed_without_retry(self):
        self.state["refuse_mutation"] = True
        self.save()
        result = self.apply("link-repository", code=1)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["steps"][0]["status"], "refused")
        self.assertEqual(result["writes_sent"], 1)
        self.assert_no_writes()
        self.assertEqual(self.call("recover", "--operation-id", result["operation_id"], code=1)["outcome"], "failed")
        self.assertEqual(sum(call["route"] == "graphql" and call["payload"]["query"].startswith("mutation") for call in self.load()["calls"]), 1)

    def test_no_unrelated_skill_or_project_workflows_runtime_is_required(self):
        isolated = self.root / "isolated"
        for skill in ("setup-github", "use-github-projects"):
            shutil.copytree(ROOT / skill / "scripts", isolated / skill / "scripts")
        result = subprocess.run(["bash", str(isolated / "use-github-projects/scripts/github"), "read-project", "--repo", "example-owner/example-project", "--project-id", "PROJECT_1", "--json"], cwd=self.checkout, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "success")


if __name__ == "__main__":
    unittest.main()
