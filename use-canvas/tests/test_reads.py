import copy
import unittest

from canvas_fixture import CanvasFixture, TOKEN
from canvas_auth import CanvasError
from canvas_read import canonical


class ReadsTest(unittest.TestCase):
    def test_paging_order_deduplication_and_module_references(self):
        first = CanvasFixture(page_size=1).reader().export_data(["123"])[0]
        second_fixture = CanvasFixture(reverse=True)
        second_fixture.data["assignments"] *= 2
        second = second_fixture.reader().export_data(["123"])[0]
        self.assertEqual(len(first["assignments"]), 1)
        self.assertEqual(first["assignments"][0]["referenced_by"], ["102", "103"])
        self.assertEqual(first["pages"][0]["referenced_by"], ["101"])
        self.assertEqual(first["module_items"][0]["resource_identity"], first["pages"][0]["identity"])
        for family in ("assignments", "modules", "module_items", "pages"):
            self.assertEqual(first[family], second[family])
        self.assertEqual(first["coverage"]["module_items"]["status"], "complete")

    def test_missing_page_body_uses_explicit_page_id(self):
        fixture = CanvasFixture()
        original = fixture.route
        def route(path, params):
            if path.endswith("/pages") and "/groups/" not in path:
                return [{k:v for k,v in p.items() if k != "body"} for p in fixture.data["pages"]]
            return original(path, params)
        fixture.route = route
        result = fixture.reader().export_data(["123"])[0]
        self.assertTrue(result["pages"][0]["body"])
        self.assertIn("/api/v1/courses/123/pages/page_id:789", [p for p, _ in fixture.sent])

    def test_renamed_page_has_one_id_and_old_slug_is_unresolved(self):
        fixture = CanvasFixture()
        fixture.data["pages"][0]["url"] = "renamed"
        result = fixture.reader().export_data(["123"])[0]
        self.assertEqual([p["id"] for p in result["pages"]], ["789"])
        self.assertTrue(any(g["kind"] == "unresolved_reference" for g in result["gaps"]))

    def test_student_and_staff_dates_have_distinct_coverage(self):
        student = CanvasFixture().reader().export_data(["123"])[0]
        fixture = CanvasFixture(staff=True)
        staff = fixture.reader().export_data(["123"])[0]
        self.assertEqual(student["coverage"]["overrides"]["status"], "not_visible_to_role")
        self.assertEqual(staff["coverage"]["overrides"]["count"], 2)
        self.assertEqual(len(staff["assignments"][0]["all_dates"]), 2)
        request = next(q for p,q in fixture.sent if p.endswith("/assignments"))
        self.assertIn("overrides", request["include[]"])
        self.assertEqual(request["override_assignment_dates"], ["true"])
        fixture.permissions["manage_assignments_edit"] = False
        limited = fixture.reader().export_data(["123"])[0]
        self.assertEqual(limited["coverage"]["overrides"]["status"], "not_visible_to_role")
        self.assertIsNone(limited["assignments"][0]["overrides"])

    def test_partial_page_and_denied_files_are_explicit(self):
        fixture = CanvasFixture()
        original = fixture.route
        fixture.route = lambda p,q: [{k:v for k,v in x.items() if k != "body"} for x in fixture.data["pages"]] if p == "/api/v1/courses/123/pages" else original(p,q)
        fixture.failures["/api/v1/courses/123/pages/page_id:789"] = (403, {})
        fixture.failures["/api/v1/courses/123/files"] = (403, {})
        fixture.data["items"].append({"id":"104","type":"File","content_id":"900","position":3})
        result = fixture.reader().export_data(["123"])[0]
        self.assertEqual(result["coverage"]["page_bodies"]["status"], "partial")
        self.assertEqual(result["coverage"]["files"]["status"], "denied")
        self.assertEqual(result["coverage"]["files"]["fallback"], "referenced_only")
        self.assertEqual([f["id"] for f in result["files"]], ["900"])

    def test_unknown_external_content_is_not_followed(self):
        fixture = CanvasFixture()
        fixture.data["items"].append({"id":"105","type":"ExternalTool","external_url":"https://tools.example.net/tool","position":3})
        fixture.data["assignments"][0]["submission_types"] = ["external_tool"]
        fixture.data["pages"][0]["body"] += '<video src="https://media.example.net/video"></video>'
        result = fixture.reader().export_data(["123"])[0]
        kinds = {x["kind"] for x in result["gaps"]}
        self.assertTrue({"ExternalTool", "external_tab", "external_tool_assignment", "iframe", "media"} <= kinds)
        self.assertNotIn("tools.example.net", str(fixture.sent))

    def test_old_announcements_and_only_own_groups(self):
        fixture = CanvasFixture(page_size=1)
        fixture.data["announcements"].append({"id":"112","title":"Older","posted_at":"2025-01-01T00:00:00Z","message":"old"})
        result = fixture.reader().export_data(["123"])[0]
        self.assertEqual(len(result["announcements"]), 2)
        self.assertEqual([g["group_id"] for g in result["groups"]], ["77"])
        self.assertEqual(result["groups"][0]["pages"][0]["id"], "790")
        self.assertFalse(any(p.endswith("/announcements") or "/replies" in p or "/entries" in p for p,_ in fixture.sent))

    def test_calendar_batches_have_explicit_unbounded_window(self):
        fixture = CanvasFixture()
        fixture.course_ids = [str(i) for i in range(120, 132)]
        fixture.reader().export_data(fixture.course_ids)
        requests = [q for p,q in fixture.sent if p == "/api/v1/calendar_events"]
        self.assertEqual([len(q["context_codes[]"]) for q in requests], [10,2])
        self.assertTrue(all(q["all_events"] == ["true"] for q in requests))

    def test_allowlist_provenance_and_grades(self):
        fixture = CanvasFixture()
        fixture.data["assignments"][0]["id"] = "90071992547409930001"
        fixture.data["course"]["enrollments"].append({"user_id":"9999","computed_current_score":1})
        result = fixture.reader().export_data(["123"])[0]
        text = canonical(result)
        self.assertIn("90071992547409930001", text)
        self.assertIn('"score":9', text)
        self.assertEqual(len(result["course"]["enrollments"]), 1)
        for forbidden in (TOKEN, "Not exported", "Other participants", "thumbnail_url", "?verifier=", "/download"):
            self.assertNotIn(forbidden, text)
        for family in ("pages", "files", "assignments", "announcements", "discussions", "calendar_events"):
            for row in result[family]:
                self.assertTrue(all(k in row for k in ("identity", "api_path", "html_url", "created_at", "updated_at")))

    def test_conflicting_duplicates_are_partial_and_order_independent(self):
        fixture = CanvasFixture()
        fixture.data["assignments"].append(dict(fixture.data["assignments"][0], name="Changed during paging"))
        first = fixture.reader().export_data(["123"])[0]
        fixture.reverse = True
        second = fixture.reader().export_data(["123"])[0]
        self.assertEqual(first["assignments"], second["assignments"])
        self.assertEqual(first["coverage"]["assignments"]["status"], "partial")

    def test_permissions_unknown_boolean_strings_and_concluded_course(self):
        fixture = CanvasFixture()
        fixture.permissions = {"manage_wiki_update":"false", "manage_assignments_edit":"true"}
        fixture.data["course"]["workflow_state"] = "completed"
        report = fixture.reader().verify("123")
        self.assertIs(report["permissions"]["manage_wiki_update"], False)
        self.assertIsNone(report["permissions"]["manage_files_add"])
        self.assertEqual(report["write_readiness"], "course_concluded")
        self.assertTrue(all(v == "refused" for v in report["write_families"].values()))

    def test_authentication_failure_is_fatal(self):
        fixture = CanvasFixture()
        fixture.failures["/api/v1/courses/123/assignments"] = (401, {"message":"Invalid access token"})
        with self.assertRaises(CanvasError) as error:
            fixture.reader().export_data(["123"])
        self.assertEqual(error.exception.kind, "token_rejected")

    def test_course_listing_active_default_and_all_states(self):
        fixture = CanvasFixture()
        reader = fixture.reader()
        courses, cov = reader.courses()
        self.assertEqual(courses[0]["course_code"], "EX-101")
        self.assertEqual(cov["status"], "complete")
        self.assertEqual(fixture.sent[-1][1]["enrollment_state"], ["active"])
        reader.courses(True)
        self.assertNotIn("enrollment_state", fixture.sent[-1][1])

    def test_failed_parent_listings_do_not_make_child_coverage_complete(self):
        fixture = CanvasFixture()
        fixture.failures['/api/v1/courses/123/pages'] = (500, {})
        fixture.failures['/api/v1/courses/123/modules'] = (403, {})
        data = fixture.reader().export_data(['123'])[0]
        self.assertEqual(data['coverage']['page_bodies']['status'], 'failed')
        self.assertEqual(data['coverage']['module_items']['status'], 'denied')

    def test_group_duplicates_and_malformed_events_are_not_silent(self):
        fixture = CanvasFixture()
        fixture.data['groups'] *= 2
        data = fixture.reader().export_data(['123'])[0]
        self.assertEqual(len(data['groups']), 1)
        fixture.data['groups'].append('malformed')
        original = fixture.route
        fixture.route = lambda p,q: [{'id':'999'}] if p == '/api/v1/calendar_events' else original(p,q)
        data = fixture.reader().export_data(['123'])[0]
        self.assertEqual(data['coverage']['groups']['status'], 'partial')
        self.assertEqual(data['coverage']['calendar_events']['status'], 'partial')


if __name__ == "__main__":
    unittest.main()
