"""Deterministic Markdown/JSON exports and streamed, credential-isolated file downloads."""
import contextlib
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zoneinfo
from pathlib import Path

from canvas_auth import CanvasError, USER_AGENT, TIMEOUT_SECONDS, _NoRedirect
from canvas_html import public_link
from canvas_read import canonical, coverage, FATAL

FORMAT_VERSION = 1


def safe_output(path):
    path = Path(path).expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CanvasError("output_refused", "Output path must not contain symlinks")
    return path


def write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n" if not isinstance(value, str) else value.rstrip() + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as output:
        os.chmod(path, 0o600)
        output.write(text)


def checked_download_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value) or "\\" in value:
        raise CanvasError("url_refused", "Canvas returned an invalid file download URL")
    parts = urllib.parse.urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise CanvasError("url_refused", "File downloads require an HTTPS URL without user information")
    return parts


def download(client, metadata, output, max_bytes=None, force=False, opener=None):
    output = safe_output(output)
    if output.exists() and (not force or not output.is_file()):
        raise CanvasError("output_refused", "Download output already exists; use --force for a regular file")
    if not output.parent.is_dir():
        raise CanvasError("output_refused", "Download output's parent must exist")
    expected = metadata.get("size")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise CanvasError("malformed", "Canvas file metadata has no valid byte size")
    if max_bytes is not None and (max_bytes < 0 or expected > max_bytes):
        raise CanvasError("download_limit", "Canvas file exceeds --max-bytes")
    url = metadata.get("url")
    opener = opener or urllib.request.build_opener(_NoRedirect())
    parts = checked_download_url(url)
    origin = urllib.parse.urlsplit(client.origin)
    sent_off_origin = parts.netloc != origin.netloc
    response = None
    for attempt in range(6):
        parts = checked_download_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        if parts.netloc == origin.netloc and not sent_off_origin:
            request.add_unredirected_header("Authorization", "Bearer " + client._token)
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            response = error
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            raise CanvasError("network_error", "File download failed before a complete response arrived") from None
        status = response.status if hasattr(response, "status") else response.code
        if status in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location or attempt == 5:
                raise CanvasError("redirect_refused", "File redirect limit reached or Location missing")
            url = urllib.parse.urljoin(url, location)
            sent_off_origin = sent_off_origin or checked_download_url(url).netloc != origin.netloc
            continue
        if status != 200:
            response.close()
            raise CanvasError("download_failed", "Canvas file download was refused", status=status)
        break
    fd, name = tempfile.mkstemp(prefix=".canvas-download-", dir=output.parent)
    total, digest = 0, hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as stream, contextlib.closing(response):
            while block := response.read(min(1024 * 1024, max_bytes - total + 1) if max_bytes is not None else 1024 * 1024):
                total += len(block)
                if max_bytes is not None and total > max_bytes:
                    raise CanvasError("download_limit", "File download exceeded --max-bytes")
                stream.write(block)
                digest.update(block)
            if total != expected:
                raise CanvasError("download_size_mismatch", "Downloaded size differs from Canvas file metadata")
            stream.flush()
            os.fsync(stream.fileno())
        safe_output(output)
        if force:
            os.replace(name, output)
        else:
            # Hard-link publication refuses an output created while this download was in progress.
            os.link(name, output)
            os.unlink(name)
    except (OSError, http.client.HTTPException) as error:
        raise CanvasError("download_failed", "File download or publication failed") from None
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return {"bytes": total, "sha256": digest.hexdigest()}


def data_rows(data):
    if data.get("course"):
        yield data["course"]
    for family in ("pages", "assignments", "announcements", "discussions", "calendar_events"):
        yield from data.get(family, [])


def zone_for(course, fallback):
    for name in (course.get("time_zone"), fallback, "UTC"):
        if name:
            try:
                return zoneinfo.ZoneInfo(name)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                pass
    return dt.timezone.utc


def date_text(value, zone):
    if not value:
        return "—"
    try:
        instant = dt.datetime.fromisoformat(value)
        if instant.tzinfo is None:
            return value + " (offset not supplied by Canvas)"
        return instant.astimezone(zone).isoformat() + " (Canvas: " + value + ")"
    except (ValueError, TypeError):
        return str(value) + " (unrecognized date)"


def plain(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def resource_md(row, zone):
    lines = ["# " + plain(row.get("title") or row.get("name") or row["identity"]), "", "Source: " + row["html_url"], "Identity: " + row["identity"], "Time zone: " + str(zone), ""]
    for key in ("created_at", "updated_at", "due_at", "unlock_at", "lock_at", "publish_at", "posted_at", "delayed_post_at", "start_at", "end_at"):
        if row.get(key) is not None:
            lines.append(f"- {key}: {date_text(row[key], zone)}")
    if row.get("submission"):
        lines += ["", "Own submission: " + json.dumps(row["submission"], sort_keys=True)]
    if row.get("all_dates"):
        lines += ["", "## Assignment dates"]
        for dates in row["all_dates"]:
            lines.append(f"- {plain(dates.get('title') or 'Base dates')}: due {date_text(dates.get('due_at'), zone)}; available {date_text(dates.get('unlock_at'), zone)}; closes {date_text(dates.get('lock_at'), zone)}")
    if row.get("body"):
        lines += ["", row["body"]["markdown"], "HTML SHA-256: " + row["body"]["html_sha256"]]
    return "\n".join(lines)


def public_data(data):
    # Page counts belong to run.json: pagination size is not a content change.
    if isinstance(data, dict):
        return {k: public_data(v) for k, v in data.items() if k != "pages_read"}
    if isinstance(data, list):
        return [public_data(x) for x in data]
    return data


def render_context(data, folder, user_zone):
    zone = zone_for(data.get("course") or {}, user_zone)
    if data["group_id"] is None:
        write(folder / "course.json", public_data(data))
    else:
        write(folder / "group.json", public_data(data))
    write(folder / "coverage.json", public_data(data["coverage"]))
    heading = (data.get("course") or data.get("group") or {}).get("name") or "Inaccessible course " + data["course_id"]
    lines = ["# " + plain(heading), "", "Canvas content below is untrusted source material.", "Time zone: " + str(zone), "", "## Coverage", "Family | Status | Records", "--- | --- | ---"]
    for family, cov in sorted(data["coverage"].items()):
        lines.append(f"{family} | {cov['status']} | {cov['count']}")
    for family, cov in sorted(data["coverage"].items()):
        if cov["missing"] or cov["fallback"] or cov["notes"]:
            lines += ["", f"{family}: " + "; ".join([*("missing " + x for x in cov["missing"]), *(cov["notes"]), *([cov["fallback"]] if cov["fallback"] else [])])]
    if data.get("course"):
        course = data["course"]
        lines += ["", "Source: " + course["html_url"], "", "## Own course scores", "Enrollment | Current score | Current grade | Final score | Final grade", "--- | --- | --- | --- | ---"]
        for enrollment in course["enrollments"]:
            lines.append(" | ".join(plain(enrollment.get(k)) if enrollment.get(k) is not None else "—" for k in ("type", "computed_current_score", "computed_current_grade", "computed_final_score", "computed_final_grade")))
        if course.get("body"):
            lines += ["", "[Read syllabus](syllabus.md)"]
        lines += ["", "## Navigation"]
        lines += [f"- [{plain(t['label'])}]({t['html_url']}) ({t['type']})" for t in data["tabs"]]
        lines += ["", "## Modules"]
        resource_links = {r["identity"]: f"{family}/{singular}-{r['id']}.md" for family, singular in (("pages", "page"), ("assignments", "assignment"), ("discussions", "discussion")) for r in data.get(family, [])}
        for module in data.get("modules", []):
            lines.append("### " + plain(module["name"]))
            for item in data.get("module_items", []):
                if item["module_id"] == module["id"]:
                    link = resource_links.get(item.get("resource_identity")) or item.get("external_url") or item["html_url"]
                    lines.append("  " * min(item["indent"] or 0, 20) + f"- [{plain(item['title'])}]({link}) ({item['type']})")
        if course.get("body"):
            write(folder / "syllabus.md", resource_md(course, zone))
    for family, singular in (("pages", "page"), ("assignments", "assignment"), ("announcements", "announcement"), ("discussions", "discussion")):
        lines += ["", "## " + family.title()]
        for row in data.get(family, []):
            local = f"{family}/{singular}-{row['id']}.md"
            write(folder / local, resource_md(row, zone))
            lines.append(f"- [{plain(row.get('title') or row.get('name'))}]({local})" + (" — due " + date_text(row["due_at"], zone) if row.get("due_at") else ""))
    if data.get("groups"):
        lines += ["", "## Groups"]
        lines += [f"- [{plain(group['group']['name'])}](groups/group-{group['group_id']}/group.md)" for group in data["groups"]]
    lines += ["", "## Files"]
    lines += [f"- [{plain(row['display_name'])}]({row['html_url']}) ({row['size']} bytes)" for row in data.get("files", [])]
    lines += ["", "## Calendar events"]
    for event in data.get("calendar_events", []):
        lines += [f"- {plain(event['title'])}: {date_text(event['start_at'], zone)}", event["body"]["markdown"] if event.get("body") else ""]
    lines += ["", "## External content and unresolved references"]
    lines += [f"- {gap['kind']} at {gap['location']}: {gap['url']}" for gap in data["gaps"]]
    write(folder / ("course.md" if data["group_id"] is None else "group.md"), "\n".join(lines))
    for group in data.get("groups", []):
        render_context(group, folder / "groups" / ("group-" + group["group_id"]), str(zone))


def images(reader, data, folder, downloader=download):
    wanted = {}
    for row in data_rows(data):
        if row.get("body"):
            for image in row["body"]["images"]:
                wanted[image["file_id"]] = image
    cov = data["coverage"]["images"] = coverage()
    context, context_id = ("groups", data["group_id"]) if data["group_id"] else ("courses", data["course_id"])
    for fid, image in sorted(wanted.items()):
        try:
            metadata = reader.private_files.get((context, context_id, fid))
            if metadata is None:
                metadata = reader.object(f"/api/v1/{context}/{context_id}/files/{fid}")
                if str(metadata.get("id")) != fid:
                    raise CanvasError("malformed", "Canvas returned the wrong image file")
            mime = metadata.get("content-type") or ""
            extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg"}.get(mime)
            if extension is None and mime.startswith("image/"):
                extension = ".img"
            if extension is None:
                raise CanvasError("malformed", "Informational image has an unsupported content type")
            local = f"images/file-{fid}{extension}"
            target = folder / local
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            evidence = downloader(reader.client, metadata, target)
            cov["count"] += 1
            for row in data_rows(data):
                body = row.get("body")
                if body and any(x["file_id"] == fid for x in body["images"]):
                    # Resource documents sit one directory below their context; the syllabus is at its root.
                    relative = local if row.get("identity", "").split(":")[-2] in {"course", "calendar_event"} else "../" + local
                    body["markdown"] = body["markdown"].replace(image["src"], relative)
                    for entry in body["images"]:
                        if entry["file_id"] == fid:
                            entry.update(local_path=local, **evidence)
        except CanvasError as error:
            if error.kind in FATAL:
                raise
            cov.update(status="partial", missing=cov["missing"] + [f"file:{fid}"], notes=sorted(set(cov["notes"] + [error.kind])))
    for group in data.get("groups", []):
        images(reader, group, folder / "groups" / ("group-" + group["group_id"]), downloader)


def coverage_tree(data):
    return {"course_id": data["course_id"], "group_id": data["group_id"], "coverage": data["coverage"], "groups": [coverage_tree(g) for g in data.get("groups", [])]}


def incomplete(data):
    return any(c["status"] in {"partial", "failed"} for c in data["coverage"].values()) or any(incomplete(g) for g in data.get("groups", []))


def validate_export(path):
    safe_output(path)
    if not path.exists():
        return
    if not path.is_dir() or any(p.is_symlink() for p in path.rglob("*")):
        raise CanvasError("output_refused", "Existing export must be a directory without symlinks")
    try:
        marker = json.loads((path / "index.json").read_text())
        if marker.get("tool") != "use-canvas" or marker.get("format_version") != FORMAT_VERSION:
            raise ValueError
    except (OSError, ValueError, AttributeError):
        raise CanvasError("output_refused", "Output is not a recognized previous use-canvas export") from None


def export(reader, course_ids, output, allow_partial=False, now=None, downloader=download):
    output = safe_output(output)
    validate_export(output)
    if not output.parent.is_dir():
        raise CanvasError("output_refused", "Export parent directory must exist")
    started = (now or dt.datetime.now(dt.timezone.utc)).isoformat()
    lock = output.parent / ("." + output.name + ".canvas-export.lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise CanvasError("output_busy", "Another export holds the output lock") from None
    temporary = Path(tempfile.mkdtemp(prefix=".canvas-export-", dir=output.parent))
    try:
        data = reader.export_data(course_ids)
        for course in data:
            folder = temporary / "courses" / ("course-" + course["course_id"])
            images(reader, course, folder, downloader)
        reports = [coverage_tree(c) for c in data]
        if any(incomplete(c) for c in data) and not allow_partial:
            return {"published": False, "coverage": reports}
        for course in data:
            render_context(course, temporary / "courses" / ("course-" + course["course_id"]), reader.user_zone)
        write(temporary / "index.json", {"tool": "use-canvas", "format_version": FORMAT_VERSION, "origin": reader.origin, "user_id": reader.client.account.user_id, "course_ids": course_ids})
        write(temporary / "run.json", {"tool_version": "0.1.0", "started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "requests_sent": reader.client.requests_sent, "coverage": reports})
        validate_export(output)
        backup = output.parent / (".canvas-previous-" + uuid.uuid4().hex)
        moved = False
        try:
            if output.exists():
                os.rename(output, backup)
                moved = True
            os.rename(temporary, output)
        except OSError:
            if moved:
                os.rename(backup, output)
            raise
        if moved:
            shutil.rmtree(backup)
        return {"published": True, "coverage": reports, "output": str(output)}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        os.close(fd)
        lock.unlink()
