"""Read one selected assignment's own-submission feedback without marking it read."""
from canvas_auth import CanvasError, id_string


def records(value, label):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise CanvasError("malformed", f"Canvas returned invalid {label}")
    return value


def text_fields(raw, keys):
    result = {key: raw.get(key) for key in keys.split()}
    if any(value is not None and not isinstance(value, str) for value in result.values()):
        raise CanvasError("malformed", "Canvas returned invalid feedback text")
    return result


def feedback(reader, course_id, assignment_id):
    course_id, assignment_id = id_string(course_id), id_string(assignment_id)
    if course_id not in reader.client.account.courses:
        raise CanvasError("config_invalid", "Requested course is not in this account's explicit course selection")
    base = f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
    assignment = reader.object(base)
    if id_string(assignment.get("id")) != assignment_id or id_string(assignment.get("course_id")) != course_id:
        raise CanvasError("malformed", "Canvas returned the wrong assignment or course")
    # Do not request read_status: Canvas documents that including it marks the submission as read.
    submission = reader.object(base + "/submissions/self", {"include[]": ["submission_comments", "rubric_assessment"]})
    if id_string(submission.get("user_id")) != reader.client.account.user_id or id_string(submission.get("assignment_id")) != assignment_id:
        raise CanvasError("malformed", "Canvas returned feedback for another user or assignment")
    comments = []
    for raw in records(submission.get("submission_comments"), "submission comments"):
        comment = text_fields(raw, "author_name comment created_at edited_at")
        comment.update(id=id_string(raw.get("id")), author_id=id_string(raw["author_id"]) if raw.get("author_id") is not None else None)
        comment["attempt"] = raw.get("attempt")
        comment["attachments"] = []
        for item in records(raw.get("attachments"), "comment attachments"):
            attachment = text_fields(item, "display_name filename content-type")
            attachment["id"] = id_string(item.get("id"))
            attachment["html_url"] = f"{reader.origin}/courses/{course_id}/files/{attachment['id']}"
            comment["attachments"].append(attachment)
        media = raw.get("media_comment")
        if media is not None and not isinstance(media, dict):
            raise CanvasError("malformed", "Canvas returned an invalid media comment")
        comment["media_comment"] = text_fields(media, "display_name media_type content-type") if media is not None else None
        comments.append(comment)
    comments.sort(key=lambda row: (row["created_at"] or "", len(row["id"]), row["id"]))
    criteria = {}
    for row in records(assignment.get("rubric"), "rubric criteria"):
        criterion_id = row.get("id")
        if not isinstance(criterion_id, str) or not criterion_id or criterion_id in criteria:
            raise CanvasError("malformed", "Canvas returned an invalid or duplicate rubric criterion")
        criteria[criterion_id] = row
    assessment = submission.get("rubric_assessment")
    if assessment is not None and not isinstance(assessment, dict):
        raise CanvasError("malformed", "Canvas returned an invalid rubric assessment")
    rubric = []
    for criterion_id, raw in (assessment or {}).items():
        if not isinstance(raw, dict):
            raise CanvasError("malformed", "Canvas returned invalid rubric feedback")
        criterion = criteria.get(criterion_id, {})
        item = text_fields(raw, "comments rating_id")
        item.update(text_fields(criterion, "description long_description"))
        item.update(criterion_id=criterion_id, points=raw.get("points"), points_possible=criterion.get("points"))
        rubric.append(item)
    rubric.sort(key=lambda row: row["criterion_id"])
    details = {key: submission.get(key) for key in ("attempt", "workflow_state", "submission_type", "submitted_at", "graded_at", "posted_at", "score", "grade", "grade_matches_current_submission", "late", "missing", "excused")}
    details["user_id"] = reader.client.account.user_id
    return {
        "course_id": course_id,
        "assignment": {"id": assignment_id, "name": assignment.get("name"), "points_possible": assignment.get("points_possible")},
        "html_url": f"{reader.origin}/courses/{course_id}/assignments/{assignment_id}/submissions/{reader.client.account.user_id}",
        "submission": details,
        "comments": comments,
        "rubric": rubric,
        "coverage": {"comments": "returned" if isinstance(submission.get("submission_comments"), list) else "not_returned", "rubric_assessment": "returned" if assessment is not None else "not_returned"},
        "limits": [
            "Only feedback visible to this account is returned. Missing or null fields do not establish that no feedback exists.",
            "Attempt and grade describe the current submission; comments are not assigned to an attempt unless Canvas supplies one. Submission history is not requested.",
            "Comment attachments and media are metadata only; their contents are not retrieved. Links in comments are not followed.",
            "DocViewer annotations and feedback inside submitted files or external grading tools are not retrieved by this command.",
        ],
    }


def render(value):
    assignment, submission = value["assignment"], value["submission"]
    lines = [f"# Feedback: {assignment['name'] or assignment['id']}", value["html_url"], "", f"Attempt: {submission['attempt']} · State: {submission['workflow_state']}", f"Grade: {submission['grade']} · Score: {submission['score']} / {assignment['points_possible']}", f"Submitted: {submission['submitted_at']} · Graded: {submission['graded_at']}", f"Grade matches current submission: {submission['grade_matches_current_submission']}", "", "## Comments"]
    if not value["comments"]:
        lines.append("Canvas returned an empty comment list for this account." if value["coverage"]["comments"] == "returned" else "Canvas did not return a comment list; absence is unknown.")
    for row in value["comments"]:
        author = row["author_name"] or (f"User {row['author_id']}" if row["author_id"] is not None else "Unknown author")
        lines.extend([f"### {author} · {row['created_at'] or 'date not returned'} · Comment {row['id']}"])
        if row["edited_at"]:
            lines.append(f"Edited: {row['edited_at']}")
        if row["attempt"] is not None:
            lines.append(f"Comment attempt: {row['attempt']}")
        lines.extend([row["comment"] or "[No text comment returned]", ""])
        for item in row["attachments"]:
            lines.append(f"Attachment (not downloaded): {item['display_name'] or item['filename'] or item['id']} — {item['html_url']}")
        if row["media_comment"] is not None:
            lines.append(f"Media comment (not retrieved): {row['media_comment']['display_name'] or row['media_comment']['media_type'] or 'unnamed'}")
    lines.extend(["", "## Rubric"])
    if not value["rubric"]:
        lines.append("Canvas returned an empty rubric assessment." if value["coverage"]["rubric_assessment"] == "returned" else "Canvas did not return a rubric assessment; absence is unknown.")
    for row in value["rubric"]:
        lines.extend([f"### {row['description'] or row['criterion_id']} — {row['points']} / {row['points_possible']}", row["long_description"] or "", row["comments"] or "[No criterion comment returned]", ""])
    lines.extend(["", "## Coverage limits", *["- " + limit for limit in value["limits"]]])
    return "\n".join(lines).rstrip() + "\n"
