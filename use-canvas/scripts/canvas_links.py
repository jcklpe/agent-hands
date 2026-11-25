"""Offline inventory of the links in a published export: what is a Canvas file, and what is only a reference elsewhere."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

from canvas_auth import CanvasError, id_string, normalize_origin
from canvas_export import validate_export

FAMILIES = ("pages", "assignments", "announcements", "discussions", "calendar_events")
INTERNAL = {"pages": "canvas_page", "assignments": "canvas_assignment", "discussion_topics": "canvas_discussion", "modules": "canvas_module", "quizzes": "canvas_quiz", "external_tools": "external_tool"}
MODULE_ITEMS = {"File": "canvas_file", "Page": "canvas_page", "Assignment": "canvas_assignment", "Discussion": "canvas_discussion", "Quiz": "canvas_quiz", "ExternalUrl": "external", "ExternalTool": "external_tool"}
ELSEWHERE = {"external", "external_tool"}
NOTES = {
    "canvas_file": "Native Canvas file; the export holds its metadata. Use download-file for its contents.",
    "external": "Outside Canvas. Only the link was retrieved; nothing at the address was requested.",
    "external_tool": "Opens an external tool. Only the link was retrieved.",
}


def classify(url, origin):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return ("other", None)
    if parts.scheme != "https" or parts.netloc.lower() != urlsplit(origin).netloc:
        return ("external", None)
    found = re.match(r"^/(?:(?:courses|groups)/\d+/)?files/(\d+)(?:/|$)", parts.path)
    if found:
        return ("canvas_file", found[1])
    found = re.match(r"^/(?:courses|groups)/\d+/([a-z_]+)(?:/|$)", parts.path)
    return (INTERNAL.get(found[1], "canvas_other") if found else "canvas_other", None)


def body_links(markdown):
    """Each link's text and address, read with the converter's own Markdown parser."""
    found = []
    for block in MarkdownIt("commonmark").enable("table").parse(markdown):
        label = None
        for token in block.children or []:
            if token.type == "link_open":
                label, address = [], token.attrGet("href")
            elif token.type == "link_close" and label is not None:
                found.append((" ".join("".join(label).split()), address))
                label = None
            elif label is not None:
                label.append(token.content if token.type in {"text", "code_inline"} else " " if token.type in {"softbreak", "hardbreak"} else token.content if token.type == "image" else "")
    return found


def course_links(data, origin):
    files = {row["id"]: row for row in data.get("files", [])}
    modules = {row["id"]: row["name"] for row in data.get("modules", [])}
    placed = {}
    for item in data.get("module_items", []):
        if item.get("resource_identity"):
            placed.setdefault(item["resource_identity"], set()).add(modules.get(item["module_id"]) or item["module_id"])
    links = []

    def add(title, url, category, file_id, source):
        row = {"title": title, "url": url, "category": category, "source": source}
        if category == "canvas_file":
            found = files.get(file_id)
            row["file"] = {"id": file_id, "in_export": found is not None, **({k: found.get(k) for k in ("display_name", "size", "content-type")} if found else {})}
        links.append(row)

    syllabus = [("syllabus", data["course"])] if data.get("course") else []
    for family, record in syllabus + [(family, row) for family in FAMILIES for row in data.get(family, [])]:
        if not record.get("body"):
            continue
        source = {"kind": "syllabus" if family == "syllabus" else family.rstrip("s"), "identity": record["identity"], "title": record.get("title") or record.get("name"), "url": record["html_url"], "modules": sorted(placed.get(record["identity"], ()))}
        for title, url in body_links(record["body"]["markdown"]):
            # The export makes every address absolute, so a jump within a page points at the instance's root.
            if url and not url.startswith(("#", origin + "#", origin + "/#")):
                category, file_id = classify(url, origin)
                add(title or None, url, category, file_id, source)
    for item in data.get("module_items", []):
        category = MODULE_ITEMS.get(item["type"])
        if category:
            source = {"kind": "module_item", "identity": item["identity"], "title": item["title"], "url": item["html_url"], "modules": [modules.get(item["module_id"]) or item["module_id"]]}
            add(item["title"], item.get("external_url") or item["html_url"], category, item.get("content_id") if category == "canvas_file" else None, source)
    return links


def links(path, courses=None, elsewhere=False):
    path = Path(path).expanduser().absolute()
    if not path.is_dir():
        raise CanvasError("input_invalid", "--export must name a published use-canvas export")
    validate_export(path)
    index = json.loads((path / "index.json").read_text(encoding="utf-8"))
    origin, held = normalize_origin(index["origin"]), [id_string(c) for c in index["course_ids"]]
    chosen = courses or held
    if set(chosen) - set(held):
        raise CanvasError("input_invalid", "A requested course is not in this export")
    result = []
    for cid in chosen:
        data = json.loads((path / "courses" / f"course-{cid}" / "course.json").read_text(encoding="utf-8"))
        rows = []
        for part in (data, *data.get("groups", [])):
            rows += [{**row, "group_id": part.get("group_id")} for row in course_links(part, origin)]
        rows.sort(key=lambda r: json.dumps(r, sort_keys=True))
        shown = [r for r in rows if r["category"] in ELSEWHERE] if elsewhere else rows
        counts = {}
        for row in rows:
            counts[row["category"]] = counts.get(row["category"], 0) + 1
        families = ("pages", "assignments", "announcements", "discussions", "modules", "files")
        result.append({"course_id": cid, "name": (data.get("course") or {}).get("name"), "links": shown, "counts": counts, "coverage": {family: data["coverage"][family]["status"] for family in families if family in data.get("coverage", {})}})
    return {"export": str(path), "filter": "elsewhere" if elsewhere else "all", "courses": result, "notes": NOTES, "limits": ["Read from the export only; no address was opened and no file was downloaded.", "A link is not the reading it points to. Coverage shows which course areas the export holds.", "Quiz contents, embedded media and links inside files are not included."]}


def render(value):
    lines = []
    for course in value["courses"]:
        lines += [f"# Links: {course['name'] or course['course_id']}", "Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(course["counts"].items())), "Coverage: " + ", ".join(f"{k} {v}" for k, v in sorted(course["coverage"].items())), ""]
        for row in course["links"]:
            where = f"{row['source']['kind']} “{row['source']['title'] or row['source']['identity']}”" + (f" in {', '.join(row['source']['modules'])}" if row["source"]["modules"] else "")
            lines.append(f"- [{row['category']}] {row['title'] or '(no link text)'} — {row['url']} — {where}")
        lines.append("")
    return "\n".join([*lines, *["- " + limit for limit in value["limits"]]]) + "\n"
