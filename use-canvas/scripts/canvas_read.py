"""Bounded Canvas retrieval and deterministic, allowlisted resource normalization."""
import json
from urllib.parse import urlsplit

from canvas_auth import CanvasError, id_string, verify_identity
from canvas_html import analyse, public_link

FATAL = {"token_rejected", "identity_mismatch", "identity_unconfirmed", "config_invalid", "config_missing", "base_url_invalid", "token_missing", "token_expired_local"}
COURSE_PERMISSIONS = ("create_announcement", "create_discussion_topic")
PERMISSIONS = ("manage_wiki_create", "manage_wiki_update", "manage_assignments_add", "manage_assignments_edit", "manage_course_content_add", "manage_course_content_edit", "manage_files_add", "manage_files_edit", "create_forum", "moderate_forum", "post_to_forum")
FIELDS = {
    "course": "name course_code workflow_state time_zone start_at end_at",
    "tab": "label type position hidden visibility",
    "module": "name position unlock_at require_sequential_progress items_count published state completed_at requirement_type",
    "module_item": "title type position indent page_url external_url new_tab published",
    "page": "title url published front_page editing_roles publish_at locked_for_user lock_explanation",
    "file": "display_name filename size content-type modified_at unlock_at lock_at locked hidden locked_for_user hidden_for_user visibility_level",
    "folder": "name full_name position unlock_at lock_at locked hidden locked_for_user hidden_for_user",
    "assignment_group": "name position group_weight",
    "assignment": "name due_at unlock_at lock_at points_possible grading_type published has_overrides allowed_attempts locked_for_user lock_explanation submission_types",
    "announcement": "title posted_at delayed_post_at is_announcement locked position",
    "discussion": "title posted_at delayed_post_at discussion_type published locked allow_rating",
    "group": "name description course_id group_category_id",
    "calendar_event": "title start_at end_at all_day all_day_date location_name location_address context_code workflow_state",
}
ID_FIELDS = {"module_item": ("module_id", "content_id"), "file": ("folder_id",), "folder": ("parent_folder_id",), "assignment": ("assignment_group_id",), "group": ("course_id", "group_category_id")}
BODY_FIELDS = {"course": "syllabus_body", "page": "body", "assignment": "description", "announcement": "message", "discussion": "message", "calendar_event": "description"}
DATE_FIELDS = "due_at unlock_at lock_at"


def numeric(value):
    return (len(str(value)), str(value))


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def coverage(status="complete", count=0, pages=0, **more):
    return {"status": status, "count": count, "pages_read": pages, "http_status": None, "fallback": None, "notes": [], "missing": [], **more}


def error_coverage(error):
    if error.kind in FATAL:
        raise error
    return coverage("denied" if error.kind in {"denied", "not_found"} else "failed", pages=error.pages_read or 0, http_status=error.status, notes=[error.kind])


def permission_value(value):
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    return None


class Reader:
    def __init__(self, client, include_html=False):
        self.client = client
        self.origin = client.origin
        self.host = urlsplit(self.origin).netloc
        self.include_html = include_html
        self.private_files = {}
        self.user = None

    def identity(self):
        self.user = verify_identity(self.client)
        profile = self.client.get("/api/v1/users/self/profile")
        if not isinstance(profile, dict):
            raise CanvasError("malformed", "Canvas returned an invalid profile")
        self.user_zone = profile.get("time_zone") or "UTC"

    def object(self, path, params=None):
        result = self.client.get(path, params)
        if not isinstance(result, dict):
            raise CanvasError("malformed", "Canvas returned a non-object resource")
        return result

    def collection(self, path, params=None):
        try:
            result = self.client.paginate(path, params)
            return result.items, coverage(count=len(result.items), pages=result.pages)
        except CanvasError as error:
            return [], error_coverage(error)

    def normalize(self, raw, kind, course_id, context="courses", context_id=None):
        if not isinstance(raw, dict):
            raise CanvasError("malformed", "Canvas returned a non-object record")
        context_id = context_id or course_id
        rid = id_string(raw.get("page_id" if kind == "page" else "id")) if kind != "tab" else str(raw.get("id") or "")
        if not rid:
            raise CanvasError("malformed", "A navigation tab has no identity")
        prefix = "group_" if context == "groups" and kind not in {"file", "folder", "group"} else ""
        result = {key: raw.get(key) for key in FIELDS[kind].split()}
        for key in ("position", "indent", "items_count"):
            if key in result and result[key] is not None and (isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0):
                raise CanvasError("malformed", "Canvas returned an invalid position, indentation or item count")
        for key in ID_FIELDS.get(kind, ()):
            result[key] = id_string(raw[key]) if raw.get(key) is not None else None
        resource = {"module_item": "modules/items", "assignment_group": "assignment_groups", "announcement": "discussion_topics", "discussion": "discussion_topics", "page": "pages", "calendar_event": "calendar_events"}.get(kind, kind + "s")
        path = f"/api/v1/{context}/{context_id}/{resource}/{rid}"
        if kind == "course":
            path = f"/api/v1/courses/{rid}"
        elif kind == "group":
            path = f"/api/v1/groups/{rid}"
        elif kind == "calendar_event":
            path = f"/api/v1/calendar_events/{rid}"
        elif kind == "tab":
            path = f"/api/v1/courses/{course_id}/tabs"
        elif kind == "page":
            path = f"/api/v1/{context}/{context_id}/pages/page_id:{rid}"
        web = f"{self.origin}/{context}/{context_id}/{resource}/{rid}"
        if kind == "page":
            web = f"{self.origin}/{context}/{context_id}/pages/{raw.get('url') or 'page_id:' + rid}"
        elif kind == "course":
            web = f"{self.origin}/courses/{rid}"
        elif kind == "group":
            web = f"{self.origin}/groups/{rid}"
        elif kind == "calendar_event":
            web = f"{self.origin}/calendar?event_id={rid}"
        elif kind == "tab":
            web = f"{self.origin}/courses/{course_id}/{'pages' if rid == 'wiki' else rid}"
        if raw.get("html_url"):
            web = raw["html_url"]
        result.update(id=rid, identity=f"canvas:{self.host}:{prefix}{kind}:{rid}", course_id=course_id, group_id=context_id if context == "groups" else None, api_path=path, html_url=public_link(web, self.origin), created_at=raw.get("created_at"), updated_at=raw.get("updated_at"), referenced_by=[])
        if kind == "module_item":
            result["api_path"] = f"/api/v1/courses/{course_id}/modules/{result['module_id']}/items/{rid}"
            result["content_details"] = {k: (raw.get("content_details") or {}).get(k) for k in ("due_at", "unlock_at", "lock_at", "locked_for_user")}
            result["completion_requirement"] = {k: (raw.get("completion_requirement") or {}).get(k) for k in ("type", "min_score", "min_percentage", "completed")}
            if result["external_url"]:
                result["external_url"] = public_link(result["external_url"], self.origin)
        if kind == "course":
            result["term"] = {k: (raw.get("term") or {}).get(k) for k in ("id", "name", "start_at", "end_at")}
            if result["term"]["id"] is not None:
                result["term"]["id"] = id_string(result["term"]["id"])
            result["enrollments"] = []
            for enrollment in raw.get("enrollments") or []:
                if enrollment.get("user_id") is not None and id_string(enrollment["user_id"]) != self.client.account.user_id:
                    continue
                result["enrollments"].append({k: enrollment.get(k) for k in ("type", "enrollment_state", "computed_current_score", "computed_final_score", "computed_current_grade", "computed_final_grade")})
            result["enrollments"].sort(key=canonical)
        if kind == "assignment":
            result["submission_types"] = sorted(raw.get("submission_types") or [])
            result["all_dates"] = self.dates(raw.get("all_dates") or [])
            result["overrides"] = self.dates(raw.get("overrides") or [], overrides=True) if "overrides" in raw else None
            submission = raw.get("submission")
            if submission is not None and not isinstance(submission, dict):
                raise CanvasError("malformed", "An assignment submission is not an object")
            if submission and submission.get("user_id") is not None and id_string(submission["user_id"]) != self.client.account.user_id:
                raise CanvasError("malformed", "Canvas returned a submission for another user")
            result["submission"] = {k: submission.get(k) for k in ("id", "attempt", "workflow_state", "submitted_at", "submission_type", "score", "grade", "late", "missing", "excused")} if submission else None
            if result["submission"] and result["submission"]["id"] is not None:
                result["submission"]["id"] = id_string(result["submission"]["id"])
        if kind == "module":
            result["prerequisite_module_ids"] = sorted([id_string(x) for x in raw.get("prerequisite_module_ids") or []], key=numeric)
        if kind == "tab":
            result["html_url"] = public_link(raw.get("html_url") or web, self.origin)
        field = BODY_FIELDS.get(kind)
        if field:
            result["body"] = None
            if raw.get(field) is not None:
                body, gaps, images, refs = analyse(raw[field], self.origin, context, context_id, self.include_html)
                result["body"] = body
                result["body"]["images"] = images
                result["body"]["file_references"] = refs
                result["body"]["gaps"] = gaps
        return result

    def dates(self, entries, overrides=False):
        result = []
        for raw in entries:
            if not isinstance(raw, dict):
                raise CanvasError("malformed", "Assignment dates must be objects")
            fields = ("id", "title", *DATE_FIELDS.split(), "course_section_id", "group_id") if overrides else ("id", "title", "base", *DATE_FIELDS.split())
            row = {k: raw.get(k) for k in fields}
            for key in ("id", "course_section_id", "group_id"):
                if key in row and row[key] is not None:
                    row[key] = id_string(row[key])
            result.append(row)
        return sorted(result, key=lambda r: (not bool(r.get("base")), r.get("title") or "", numeric(r.get("id") or "0")))

    def records(self, raw, kind, course_id, cov, context="courses", context_id=None):
        found = {}
        for item in raw:
            try:
                row = self.normalize(item, kind, course_id, context, context_id)
            except CanvasError as error:
                cov.update(status="partial", notes=sorted(set(cov["notes"] + [error.kind])), missing=sorted(set(cov["missing"] + [str(item.get("id", "unknown")) if isinstance(item, dict) else "unknown"])))
                continue
            previous = found.get(row["id"])
            if previous is not None and previous != row:
                cov.update(status="partial", notes=sorted(set(cov["notes"] + ["conflicting_duplicate"])), missing=sorted(set(cov["missing"] + [row["identity"]])))
                row = min((row, previous), key=canonical)
            found[row["id"]] = row
        result = sorted(found.values(), key=lambda r: ((r.get("position") or 0), numeric(r["id"])) if kind in {"module", "module_item", "tab"} else numeric(r["id"]))
        cov["count"] = len(result)
        return result

    def courses(self, all_states=False):
        params = [("include[]", "term")]
        params += [("enrollment_state", "active")] if not all_states else [("state[]", x) for x in ("available", "completed", "unpublished")]
        raw, cov = self.collection("/api/v1/courses", params)
        rows = self.records(raw, "course", "", cov)
        for row in rows:
            row["course_id"] = row["id"]
            row.pop("body", None)
        return rows, cov

    def verify(self, course_id):
        base = f"/api/v1/courses/{course_id}"
        report = {"course_id": course_id, "local_readiness": True, "course": None, "tabs": [], "permissions": {k: None for k in (*PERMISSIONS, *COURSE_PERMISSIONS)}, "write_readiness": "unknown"}
        try:
            course = self.object(base, {"include[]": ["term", "permissions"]})
            if id_string(course.get("id")) != course_id:
                raise CanvasError("malformed", "Canvas returned the wrong course")
            report["course"] = self.normalize(course, "course", course_id)
            report["remote_read_access"] = "accessible"
        except CanvasError as error:
            report["coverage"] = {"course": error_coverage(error)}
            report["remote_read_access"] = "denied" if error.kind in {"denied", "not_found"} else "failed"
            return report
        tabs, tab_cov = self.collection(base + "/tabs")
        report["tabs"] = self.records(tabs, "tab", course_id, tab_cov)
        try:
            permissions = self.object(base + "/permissions", {"permissions[]": list(PERMISSIONS)})
            report["permissions"] = {k: permission_value(permissions.get(k)) for k in PERMISSIONS}
            reported = course.get("permissions") or {}
            report["permissions"].update({k: permission_value(reported.get(k)) for k in COURSE_PERMISSIONS})
            pcov = coverage(count=len(permissions))
        except CanvasError as error:
            pcov = error_coverage(error)
        report["coverage"] = {"course": coverage(count=1), "tabs": tab_cov, "permissions": pcov}
        concluded = course.get("workflow_state") == "completed"
        report["write_readiness"] = "course_concluded" if concluded else "permissions_reported" if pcov["status"] == "complete" else "unknown"
        report["write_families"] = {name: "refused" if concluded or value is False else "reported_allowed" if value is True else "unknown" for name, value in report["permissions"].items()}
        return report

    def context(self, course_id, context="courses", context_id=None):
        context_id = context_id or course_id
        base = f"/api/v1/{context}/{context_id}"
        data = {"course_id": course_id, "group_id": context_id if context == "groups" else None, "coverage": {}, "gaps": [], "groups": []}
        covs = data["coverage"]
        if context == "courses":
            report = self.verify(course_id)
            data.update({k: report[k] for k in ("course", "tabs", "permissions")})
            covs.update(report["coverage"])
            if data["course"] is None:
                for family in ("tabs", "permissions", "modules", "module_items", "pages", "page_bodies", "folders", "files", "assignment_groups", "assignments", "overrides", "announcements", "discussions", "groups"):
                    covs.setdefault(family, coverage("not_requested", notes=["course_unavailable"]))
                return data
            try:
                raw = self.object(base, {"include[]": ["term", "syllabus_body", "total_scores"]})
                data["course"] = self.normalize(raw, "course", course_id)
            except CanvasError as error:
                covs["course"] = error_coverage(error)
            kinds = [("module", "modules"), ("page", "pages"), ("folder", "folders"), ("file", "files"), ("assignment_group", "assignment_groups"), ("assignment", "assignments"), ("announcement", "announcements"), ("discussion", "discussions")]
        else:
            kinds = [("page", "pages"), ("folder", "folders"), ("file", "files"), ("discussion", "discussions")]
        for kind, family in kinds:
            path, params = base + "/" + family, []
            if family == "modules":
                params = [("include[]", ["items", "content_details"])]
            elif family == "pages":
                params = [("include[]", "body")]
            elif family == "assignments":
                params = [("include[]", ["all_dates", "submission"]), ("override_assignment_dates", True)]
                staff = any(e["type"] in {"teacher", "ta", "designer", "TeacherEnrollment", "TaEnrollment", "DesignerEnrollment"} for e in data["course"]["enrollments"])
                overrides_visible = staff and data["permissions"].get("manage_assignments_edit") is not False
                if overrides_visible:
                    params.append(("include[]", "overrides"))
            elif family in {"announcements", "discussions"}:
                path = base + "/discussion_topics"
                if family == "announcements":
                    params = [("only_announcements", True)]
            raw, covs[family] = self.collection(path, params)
            if family == "files":
                for entry in raw:
                    if isinstance(entry, dict) and entry.get("id") is not None:
                        self.private_files[(context, context_id, id_string(entry["id"]))] = entry
            data[family] = self.records(raw, kind, course_id, covs[family], context, context_id)
            if family == "modules":
                data["module_items"], covs["module_items"] = [], coverage()
                valid_ids = {m["id"] for m in data["modules"]}
                by_id = {str(x["id"]): x for x in raw if isinstance(x, dict) and str(x.get("id")) in valid_ids}
                for module in data["modules"]:
                    original = by_id[module["id"]]
                    items = original.get("items")
                    if not isinstance(items, list) or len(items) < (original.get("items_count") or 0):
                        items, icov = self.collection(base + f"/modules/{module['id']}/items", {"include[]": "content_details"})
                    else:
                        icov = coverage(count=len(items))
                    for item in items:
                        if isinstance(item, dict):
                            item["module_id"] = module["id"]
                    normalized = self.records(items, "module_item", course_id, icov)
                    if icov["status"] != "complete":
                        covs["module_items"].update(status="partial", missing=covs["module_items"]["missing"] + [module["identity"]])
                    covs["module_items"]["pages_read"] += icov["pages_read"]
                    data["module_items"].extend(normalized)
                covs["module_items"]["count"] = len(data["module_items"])
                if covs["modules"]["status"] != "complete":
                    covs["module_items"] = dict(covs["modules"])
                    covs["module_items"]["count"] = len(data["module_items"])
        covs["page_bodies"] = coverage()
        for page in data["pages"]:
            if page["body"] is None:
                try:
                    raw = self.object(page["api_path"])
                    if id_string(raw.get("page_id")) != page["id"]:
                        raise CanvasError("malformed", "Canvas returned the wrong page")
                    replacement = self.normalize(raw, "page", course_id, context, context_id)
                    if replacement["body"] is None:
                        raise CanvasError("malformed", "Canvas omitted a requested page body")
                    page.update(replacement)
                except CanvasError as error:
                    error_coverage(error)
                    covs["page_bodies"].update(status="partial", missing=covs["page_bodies"]["missing"] + [page["identity"]])
            if page["body"] is not None:
                covs["page_bodies"]["count"] += 1
        if covs["pages"]["status"] != "complete" and covs["page_bodies"]["status"] == "complete":
            covs["page_bodies"] = dict(covs["pages"])
            covs["page_bodies"]["count"] = sum(p["body"] is not None for p in data["pages"])
        if context == "courses":
            if not overrides_visible:
                for assignment in data["assignments"]:
                    assignment["overrides"] = None
            overrides = [a["overrides"] for a in data["assignments"]]
            covs["overrides"] = coverage("not_visible_to_role" if not overrides_visible else "complete", count=sum(len(x or []) for x in overrides))
            if overrides_visible and any(a["has_overrides"] and a["overrides"] is None for a in data["assignments"]):
                covs["overrides"].update(status="partial", notes=["overrides_omitted"])
            if covs["assignments"]["status"] in {"partial", "failed", "denied"} and overrides_visible:
                covs["overrides"] = dict(covs["assignments"])
        self.gaps_and_files(data, context, context_id)
        if context == "courses":
            self.references(data)
        data["gaps"] = sorted([json.loads(s) for s in {canonical(g) for g in data["gaps"]}], key=canonical)
        covs["images"] = coverage("not_requested")
        return data

    def references(self, data):
        lookup = {kind: {row["id"]: row for row in data.get(family, [])} for kind, family in (("Assignment", "assignments"), ("File", "files"), ("Discussion", "discussions"))}
        pages = {row["url"]: row for row in data["pages"]}
        for item in data["module_items"]:
            if item["type"] == "Page":
                target = pages.get(item["page_url"])
            else:
                target = lookup.get(item["type"], {}).get(item["content_id"])
            item["resource_identity"] = target["identity"] if target else None
            if target:
                target["referenced_by"].append(item["id"])
                target["referenced_by"].sort(key=numeric)
            elif item["type"] in {"Page", "Assignment", "File", "Discussion"}:
                data["gaps"].append({"kind": "unresolved_reference", "location": item["identity"], "url": item["html_url"]})
            if item["type"] in {"ExternalTool", "ExternalUrl", "Quiz"}:
                data["gaps"].append({"kind": item["type"], "location": item["identity"], "url": item["external_url"] or item["html_url"]})
        for tab in data["tabs"]:
            if tab["type"] == "external":
                data["gaps"].append({"kind": "external_tab", "location": tab["identity"], "url": tab["html_url"]})
        for assignment in data["assignments"]:
            if "external_tool" in assignment["submission_types"]:
                data["gaps"].append({"kind": "external_tool_assignment", "location": assignment["identity"], "url": assignment["html_url"]})

    def gaps_and_files(self, data, context, context_id):
        refs = {x["content_id"] for x in data.get("module_items", []) if x["type"] == "File" and x["content_id"]}
        rows = [data["course"]] if data.get("course") else []
        rows += [r for family in ("pages", "assignments", "announcements", "discussions", "calendar_events") for r in data.get(family, [])]
        for row in rows:
            body = row.get("body")
            if body:
                refs.update(body["file_references"])
                data["gaps"].extend({**gap, "location": row["identity"]} for gap in body["gaps"])
        cov = data["coverage"]["files"]
        if cov["status"] == "denied":
            cov["fallback"] = "referenced_only"
            known = {f["id"] for f in data["files"]}
            for fid in sorted(refs - known, key=numeric):
                try:
                    raw = self.object(f"/api/v1/{context}/{context_id}/files/{fid}")
                    if id_string(raw.get("id")) != fid:
                        raise CanvasError("malformed", "Canvas returned the wrong file")
                    self.private_files[(context, context_id, fid)] = raw
                    data["files"].append(self.normalize(raw, "file", data["course_id"], context, context_id))
                except CanvasError as error:
                    error_coverage(error)
                    cov["missing"].append(f"file:{fid}")
            data["files"].sort(key=lambda r: numeric(r["id"]))
            cov["count"] = len(data["files"])
        data["gaps"] = sorted([json.loads(s) for s in {canonical(g) for g in data["gaps"]}], key=canonical)

    def export_data(self, course_ids):
        groups, gcov = self.collection("/api/v1/users/self/groups")
        unique_groups = {}
        for group in groups:
            try:
                if not isinstance(group, dict):
                    raise CanvasError("malformed", "Invalid group record")
                gid = id_string(group.get("id"))
                if group.get("course_id") is not None:
                    id_string(group["course_id"])
                previous = unique_groups.get(gid)
                if previous is not None and previous != group:
                    gcov.update(status="partial", notes=["conflicting_duplicate"])
                    group = min((group, previous), key=canonical)
                unique_groups[gid] = group
            except CanvasError:
                gcov.update(status="partial", notes=["malformed_group"], missing=["unknown"])
        groups = list(unique_groups.values())
        result = []
        for cid in course_ids:
            data = self.context(cid)
            if data.get("course"):
                selected = [g for g in groups if isinstance(g, dict) and str(g.get("course_id")) == cid]
                data["coverage"]["groups"] = dict(gcov)
                data["coverage"]["groups"]["count"] = len(selected)
                for group in sorted(selected, key=lambda g: numeric(id_string(g["id"]))):
                    gid = id_string(group["id"])
                    content = self.context(cid, "groups", gid)
                    content["group"] = self.normalize(group, "group", cid, "groups", gid)
                    data["groups"].append(content)
            result.append(data)
        for offset in range(0, len(course_ids), 10):
            batch = course_ids[offset:offset + 10]
            events, ecov = self.collection("/api/v1/calendar_events", [("context_codes[]", ["course_" + c for c in batch]), ("type", "event"), ("all_events", True)])
            if any(not isinstance(e, dict) or e.get("context_code") not in ["course_" + c for c in batch] for e in events):
                ecov.update(status="partial", notes=["unassigned_calendar_event"])
            for data in result:
                if data["course_id"] in batch:
                    data["coverage"]["calendar_events"] = dict(ecov)
                    own = [e for e in events if isinstance(e, dict) and e.get("context_code") == "course_" + data["course_id"]]
                    data["calendar_events"] = self.records(own, "calendar_event", data["course_id"], data["coverage"]["calendar_events"])
                    for event in data["calendar_events"]:
                        if event.get("body"):
                            data["gaps"].extend({**gap, "location": event["identity"]} for gap in event["body"]["gaps"])
                    self.gaps_and_files(data, "courses", data["course_id"])
        return result
