#!/usr/bin/env python3
"""Export design tokens from a local Penpot archive using a project-owned manifest."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unicodedata
import uuid
import zipfile


MAX_MANIFEST = 64 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_JSON = 16 * 1024 * 1024
MAX_ENTRIES = 10000
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
REFERENCE = re.compile(r"\{([^{}]+)\}")


class ExportError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collision_key(path):
    return unicodedata.normalize("NFC", path).casefold()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExportError("Duplicate JSON object keys are unsupported")
        result[key] = value
    return result


def invalid_constant(_value):
    raise ExportError("Non-finite JSON numbers are unsupported")


def read_json(data, label):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs,
                          parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ExportError(label + " must be valid bounded UTF-8 JSON") from error


def fields(value, required, optional, label):
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise ExportError("Invalid fields in " + label)


def relative_path(value, suffix):
    if not isinstance(value, str) or not value or "\\" in value or any(ord(c) < 32 for c in value):
        raise ExportError("Paths must be nonempty portable relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p.startswith(".") for p in path.parts):
        raise ExportError("Absolute, hidden, traversal or non-normalized paths are forbidden")
    if any(c in value for c in ':<>|?*') or path.suffix != suffix:
        raise ExportError("Path has an unsupported extension or character")
    return value


def checked_path(root, relative):
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ExportError("Symlinks are forbidden in source and output paths")
        if path != root / relative and path.exists() and not path.is_dir():
            raise ExportError("A path parent is not a directory")
    return path


def bounded_at(directory, name, limit, allow_missing=False):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        if allow_missing:
            return None
        raise ExportError("A required input file is missing")
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ExportError("Expected a regular file within the documented size limit")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ExportError("A file exceeds the documented size limit")
    return data


def open_parent(root, relative, created=None):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root, flags)
    parts = PurePosixPath(relative).parts[:-1]
    try:
        for index, part in enumerate(parts):
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if created is None:
                    raise
                os.mkdir(part, dir_fd=fd)
                created.append(str(PurePosixPath(*parts[:index + 1])))
                child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def bounded_file(root, relative, limit, allow_missing=False):
    checked_path(root, relative)
    try:
        directory = open_parent(root, relative)
    except FileNotFoundError:
        if allow_missing:
            return None
        raise ExportError("A required input directory is missing")
    try:
        return bounded_at(directory, PurePosixPath(relative).name, limit, allow_missing)
    finally:
        os.close(directory)


def archive_json(archive, name):
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise ExportError("The selected archive member is missing") from error
    if info.file_size > MAX_JSON or info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
        raise ExportError("Oversized, encrypted or symlink archive members are unsupported")
    with archive.open(info) as stream:
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ExportError("An archive member exceeds the JSON size limit")
    return read_json(raw, "Archive member")


def source_tokens(raw, file_id):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > MAX_ENTRIES or len(set(names)) != len(names):
            raise ExportError("Too many or duplicate archive entries")
        manifest = archive_json(archive, "manifest.json")
        if not isinstance(manifest, dict) or manifest.get("type") != "penpot/export-files" or type(manifest.get("version")) is not int or manifest.get("version") != 1:
            raise ExportError("Unsupported Penpot archive manifest")
        files = manifest.get("files")
        if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
            raise ExportError("Invalid Penpot archive file list")
        if sum(item.get("id") == file_id for item in files) != 1:
            raise ExportError("The configured file ID must identify exactly one exported file")
        tokens = archive_json(archive, "files/" + file_id + "/tokens.json")
    if not isinstance(tokens, dict):
        raise ExportError("Penpot tokens must be an object")
    return tokens


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def validate_tokens(tokens, selected):
    definitions = {}

    def walk(value, parts, inherited=None):
        if not isinstance(value, dict) or len(parts) > 64:
            raise ExportError("Token groups must be objects nested at most 64 levels")
        token_type = value.get("$type", inherited)
        if "$type" in value and (not isinstance(token_type, str) or not token_type):
            raise ExportError("Token types must be nonempty strings")
        if "$value" in value:
            if not parts or not token_type or any(not k.startswith("$") for k in value):
                raise ExportError("Each token needs a name, value and type")
            name = ".".join(parts)
            if name in definitions:
                raise ExportError("Selected palettes contain ambiguous duplicate token names")
            definitions[name] = value["$value"]
        else:
            for name, child in value.items():
                if name.startswith("$"):
                    continue
                if not name or any(c in name for c in ".{}"):
                    raise ExportError("Token names must be nonempty and cannot contain dots or braces")
                walk(child, parts + [name], token_type)

    for palette in selected:
        count = len(definitions)
        walk(tokens[palette], [])
        if count == len(definitions):
            raise ExportError("A selected palette contains no tokens")
    graph = {name: {ref for text in strings(value) for ref in REFERENCE.findall(text)}
             for name, value in definitions.items()}
    defined_names = set(definitions)
    if any(not refs <= defined_names for refs in graph.values()):
        raise ExportError("A token reference is unresolved in the selected palettes")
    done = set()

    def visit(name, active):
        if name in active or len(active) > 128:
            raise ExportError("Token references are cyclic or exceed 128 levels")
        if name not in done:
            for ref in graph[name]:
                visit(ref, active | {name})
            done.add(name)

    for name in graph:
        visit(name, set())
    return len(definitions)


def string_list(value, allowed, label):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ExportError("Invalid " + label)
    if len(set(value)) != len(value) or not set(value) <= allowed:
        raise ExportError("Invalid " + label)
    return value


def serialized(value):
    def ordered(item):
        if isinstance(item, dict):
            # Browser JSON exports enumerate unsigned array-index keys before other object keys.
            indices = [key for key in item if re.fullmatch(r"0|[1-9][0-9]{0,9}", key) and int(key) < 4294967295]
            index_names = set(indices)
            keys = sorted(indices, key=int) + [key for key in item if key not in index_names]
            return {key: ordered(item[key]) for key in keys}
        if isinstance(item, list):
            return [ordered(child) for child in item]
        return item

    return json.dumps(ordered(value), indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")


def build_plan(manifest_path):
    manifest_path = Path(manifest_path).absolute()
    if manifest_path.is_symlink():
        raise ExportError("The project manifest cannot be a symlink")
    root = manifest_path.parent.resolve(strict=True)
    manifest_path = root / manifest_path.name
    manifest_raw = bounded_file(root, manifest_path.name, MAX_MANIFEST)
    manifest = read_json(manifest_raw, "Project manifest")
    fields(manifest, {"schema_version", "source", "outputs"}, set(), "project manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ExportError("Unsupported project manifest schema version")
    source = manifest["source"]
    fields(source, {"kind", "path", "file_id"}, set(), "source")
    if source["kind"] != "penpot-archive" or not isinstance(source["file_id"], str) or not UUID.fullmatch(source["file_id"]):
        raise ExportError("Source must select a Penpot archive and lowercase UUID file ID")
    source_path = relative_path(source["path"], ".penpot")
    source_raw = bounded_file(root, source_path, MAX_ARCHIVE)
    tokens = source_tokens(source_raw, source["file_id"])
    outputs = manifest["outputs"]
    fields(outputs, {"sets"}, {"metadata", "themes"}, "outputs")
    sets = outputs["sets"]
    available = {name for name in tokens if not name.startswith("$")}
    if not isinstance(sets, dict) or not sets or not set(sets) <= available:
        raise ExportError("Outputs must select one or more existing palettes")
    count = validate_tokens(tokens, sets)
    values = [(path, tokens[name]) for name, path in sets.items()]
    if ("metadata" in outputs or "themes" in outputs) and set(sets) != available:
        raise ExportError("Metadata or themes require exporting all source palettes")
    if "metadata" in outputs:
        metadata = tokens.get("$metadata")
        if not isinstance(metadata, dict):
            raise ExportError("Source token metadata is missing")
        metadata = dict(metadata)
        order = string_list(metadata.get("tokenSetOrder"), available, "token-set order")
        if set(order) != available:
            raise ExportError("Token-set order must include every palette")
        active = string_list(metadata.get("activeSets"), available, "active sets")
        metadata["activeSets"] = [name for name in order if name in active]
        values.append((outputs["metadata"], metadata))
    if "themes" in outputs:
        themes = tokens.get("$themes")
        if not isinstance(themes, list) or any(not isinstance(theme, dict) for theme in themes):
            raise ExportError("Source themes must be an array of objects")
        values.append((outputs["themes"], themes))
    paths = [relative_path(path, ".json") for path, _value in values]
    path_keys = {collision_key(path) for path in paths}
    if len(path_keys) != len(paths) or collision_key(manifest_path.name) in path_keys:
        raise ExportError("Outputs must be distinct and cannot replace the project manifest")
    for path in paths:
        if any(collision_key(parent.as_posix()) in path_keys for parent in PurePosixPath(path).parents):
            raise ExportError("An output cannot be another output's parent directory")
    changes = []
    payloads = {}
    for relative, value in sorted(values):
        before = bounded_file(root, relative, MAX_JSON, allow_missing=True)
        after = serialized(value)
        if len(after) > MAX_JSON:
            raise ExportError("Serialized output exceeds the JSON size limit")
        action = "create" if before is None else "unchanged" if before == after else "update"
        changes.append({"path": relative, "action": action, "before_sha256": None if before is None else digest(before), "after_sha256": digest(after)})
        payloads[relative] = after
    plan = {"manifest_sha256": digest(manifest_raw), "source": {"path": source_path, "file_id": source["file_id"], "sha256": digest(source_raw)}, "token_count": count, "outputs": changes}
    plan_hash = digest(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode())
    return root, manifest_path, plan, plan_hash, payloads


def apply_plan(root, manifest_path, plan, payloads, completed, created):
    def check_inputs():
        if digest(bounded_file(root, manifest_path.name, MAX_MANIFEST)) != plan["manifest_sha256"]:
            raise ExportError("Project manifest changed after planning")
        source = plan["source"]
        if digest(bounded_file(root, source["path"], MAX_ARCHIVE)) != source["sha256"]:
            raise ExportError("Source archive changed after planning")

    def check_output(entry):
        path = checked_path(root, entry["path"])
        raw = bounded_file(root, entry["path"], MAX_JSON, allow_missing=True)
        if (None if raw is None else digest(raw)) != entry["before_sha256"]:
            raise ExportError("An output changed after planning")
        return path

    check_inputs()
    for entry in plan["outputs"]:
        check_output(entry)
    for entry in plan["outputs"]:
        if entry["action"] == "unchanged":
            continue
        check_inputs()
        path = check_output(entry)
        directory = open_parent(root, entry["path"], created)
        temporary = None
        try:
            candidate = ".penpot-export-" + uuid.uuid4().hex
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            temporary = candidate
            with os.fdopen(fd, "wb") as stream:
                stream.write(payloads[entry["path"]])
                stream.flush()
                os.fsync(stream.fileno())
            check_output(entry)
            before = bounded_at(directory, path.name, MAX_JSON, allow_missing=True)
            if (None if before is None else digest(before)) != entry["before_sha256"]:
                raise ExportError("An output changed before replacement")
            os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
            temporary = None
            completed.append(entry["path"])
            if bounded_file(root, entry["path"], MAX_JSON) != payloads[entry["path"]]:
                raise ExportError("An output failed readback verification")
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Project-owned JSON manifest; paths are relative to its directory")
    parser.add_argument("--execute", action="store_true", help="Write the reviewed output plan; default is a read-only preview")
    parser.add_argument("--expect-plan", help="plan_sha256 from preview; required when execution would change files")
    args = parser.parse_args(argv)
    report = {"mode": "execute" if args.execute else "preview", "completed": [], "created_directories": []}
    try:
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY") or os.open not in os.supports_dir_fd:
            raise ExportError("This archive exporter requires macOS or Linux directory-relative file operations")
        root, manifest_path, plan, plan_hash, payloads = build_plan(args.manifest)
        report.update(plan, plan_sha256=plan_hash)
        if args.expect_plan and (not args.execute or args.expect_plan != plan_hash):
            raise ExportError("Expected plan does not match; preview the current files again")
        if args.execute:
            if any(entry["action"] != "unchanged" for entry in plan["outputs"]) and not args.expect_plan:
                raise ExportError("Changes require --expect-plan from a reviewed preview")
            apply_plan(root, manifest_path, plan, payloads, report["completed"], report["created_directories"])
        report["status"] = "ok"
    except (ExportError, OSError, ValueError, RecursionError, zipfile.BadZipFile, NotImplementedError) as error:
        # Do not echo JSON, archive content, OS paths or potentially sensitive parser diagnostics.
        report["status"] = "error"
        report["error"] = str(error) if isinstance(error, ExportError) else "Export failed (" + type(error).__name__ + "); check inputs, permissions and reported completed paths"
        print(json.dumps(report, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
