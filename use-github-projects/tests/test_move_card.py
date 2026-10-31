"""Status-move regression cases retained on the guarded native Projects runtime."""
import copy
import unittest

from project_fixture import ProjectFixture


class MoveCardTests(ProjectFixture, unittest.TestCase):
    def preview(self, **kwargs):
        return self.call("move-card", "--issue", 1, "--status", "Ready", **kwargs)

    def fail_closed(self):
        for flags in ((), ("--execute", "--expect", "0" * 64, "--operation-id", "1" * 32)):
            self.call("move-card", "--issue", 1, "--status", "Ready", *flags, code=None)
            self.assert_no_writes()

    def test_preview_preserves_actual_status_and_never_mutates(self):
        for flags in ((), ("--dry-run",)):
            result = self.call("move-card", "--issue", 1, "--status", "Ready", *flags)
            self.assertEqual(result["plan"]["baseline"]["items"][0]["fieldValueByName"]["name"], "Waiting")
            self.assertEqual(result["writes_sent"], 0)
            self.assert_no_writes()

    def test_execute_uses_resolved_ids(self):
        self.assertEqual(self.apply("move-card", "--issue", 1, "--status", "Ready")["outcome"], "success")
        inputs = self.load()["mutations"][0]["variables"]["input"]
        self.assertEqual(inputs, {"projectId": "PROJECT_1", "itemId": "ITEM_1", "fieldId": "FIELD_STATUS", "value": {"singleSelectOptionId": "READY"}})

    def test_already_matching_status_is_noop_even_with_execute(self):
        self.project["items"][0]["fieldValueByName"] = {"optionId": "READY", "name": "Ready", "field": {"id": "FIELD_STATUS"}}
        self.save()
        self.assertTrue(self.apply("move-card", "--issue", 1, "--status", "Ready")["already_satisfied"])
        self.assert_no_writes()

    def test_explicit_null_status_is_legitimate(self):
        self.project["items"][0]["fieldValueByName"] = None
        self.save()
        result = self.preview()
        self.assertIsNone(result["plan"]["baseline"]["items"][0]["fieldValueByName"])
        self.assert_no_writes()

    def test_target_on_later_page(self):
        self.project["items"].insert(0, {"id": "OTHER_ITEM", "content": None, "fieldValueByName": None})
        self.state["page_size"] = 1
        self.save()
        self.assertEqual(self.apply("move-card", "--issue", 1, "--status", "Ready")["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_graphql_error_or_transport_failure_never_becomes_no_status(self):
        self.state["graphql_errors"] = [{"message": "Synthetic failure"}]
        self.save()
        self.fail_closed()

    def test_missing_duplicate_or_invalid_target(self):
        original = copy.deepcopy(self.project["items"][0])
        variants = [[], [original, original]]
        for key, value in (("id", None), ("id", ""), ("id", "null"), ("fieldValueByName", {}), ("fieldValueByName", {"optionId": "WAITING", "name": "Wrong", "field": {"id": "FIELD_STATUS"}}), ("fieldValueByName", {"optionId": None, "name": "Waiting", "field": {"id": "FIELD_STATUS"}})):
            item = copy.deepcopy(original)
            item[key] = value
            variants.append([item])
        missing = copy.deepcopy(original)
        del missing["fieldValueByName"]
        variants.append([missing])
        for items in variants:
            with self.subTest(items=items):
                self.project["items"] = items
                self.save()
                self.fail_closed()

    def test_invalid_or_incomplete_pages(self):
        self.state["malformed_family"] = "items"
        self.save()
        self.fail_closed()
        self.state.pop("malformed_family")
        self.state["incomplete_family"] = "items"
        self.save()
        self.call("move-card", "--issue", 1, "--status", "Ready", "--page-limit", 1, code=4)
        self.assert_no_writes()
        self.state.pop("incomplete_family")
        self.state["repeated_cursor"] = True
        self.save()
        self.fail_closed()

    def test_invalid_metadata_and_option(self):
        original = copy.deepcopy(self.project["fields"])
        variants = []
        for value in (None, "", "null"):
            fields = copy.deepcopy(original)
            fields[0]["options"][1]["id"] = value
            variants.append(fields)
        for kind in ("field-id", "duplicate-option", "missing-options"):
            fields = copy.deepcopy(original)
            if kind == "field-id":
                fields[0]["id"] = "null"
            elif kind == "duplicate-option":
                fields[0]["options"].append(copy.deepcopy(fields[0]["options"][0]))
            else:
                fields[0]["options"] = []
            variants.append(fields)
        for fields in variants:
            with self.subTest(fields=fields):
                self.project["fields"] = fields
                self.save()
                self.fail_closed()
        self.project["fields"] = original
        self.project["meta"]["id"] = None
        self.save()
        self.fail_closed()

    def test_invalid_issue_ids_and_failed_lookup(self):
        for value in ("", "null", "bad ID"):
            self.state["issue_node"] = value
            self.save()
            self.fail_closed()
        self.state.pop("issue_node")
        self.state["issue_denied"] = True
        self.save()
        self.fail_closed()

    def test_bad_mutation_response_is_uncertain_never_retried(self):
        for index, response in enumerate(({}, {"errors": [{"message": "Synthetic mutation error"}]}, {"data": {"result": {"resource": {"id": "WRONG_ITEM"}}}})):
            with self.subTest(response=response):
                self.state["mutation_result"] = response
                self.project["items"][0]["fieldValueByName"] = {"optionId": "WAITING", "name": "Waiting", "field": {"id": "FIELD_STATUS"}}
                self.save()
                result = self.apply("move-card", "--issue", 1, "--status", "Ready", code=3)
                self.assertEqual(result["outcome"], "uncertain")
                self.assertEqual(len(self.load()["mutations"]), index + 1)
                self.state.pop("mutation_result")
                self.save()
                self.assertEqual(self.call("recover", "--operation-id", result["operation_id"])["outcome"], "success")

    def test_malformed_error_envelope_fails_closed(self):
        self.state["malformed_errors"] = True
        self.save()
        self.fail_closed()

    def test_failed_mutation_transport_is_uncertain_never_retried(self):
        self.state["lose_response"] = True
        self.save()
        result = self.apply("move-card", "--issue", 1, "--status", "Ready", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.assertEqual(len(self.load()["mutations"]), 1)


if __name__ == "__main__":
    unittest.main()
