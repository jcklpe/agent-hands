#!/usr/bin/env python3
"""Find a project's Penpot files and page roles through its design-files.json, and reorder a file's pages through Penpot's backend API.

`discover` reads the manifest and, with `--resolve`, matches each role's page name to a page in the actual file, read-only. `order` previews a page order by default and prints a plan_sha256 digest; `--execute --expect-plan <digest>` writes it with `mov-page` changes, refusing if the file changed since the preview, then reads the complete page list back. Pages left out of the request keep their positions. The access token comes from setup-penpot's configuration and reaches curl on standard input, never in arguments or output.
"""
import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from penpot_backend import DEFAULT_BASE, BackendError, access_token, curl_rpc, page_names, page_order  # noqa: E402

# Roles defined by the Wireframe Workflows design-files.json contract. Others are reported, not refused, because the manifest belongs to the project.
KNOWN_ROLES = ("cover", "showroom", "prototype", "staging", "workshop", "scratchpad", "component_library", "archive")
SINGLE_ONLY_ROLES = {"archive"}


class PagesError(BackendError):
    pass


def is_uuid(value):
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def load_manifest(path):
    path = Path(path)
    if not path.is_file():
        raise PagesError(f"No design-files.json at {path}; pass --manifest with the project's manifest")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise PagesError(f"{path} is not valid JSON: {error}")
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise PagesError(f"{path} must be a design-files.json object with schema_version 1")
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise PagesError(f"{path} lists no files")
    return [parse_file(entry, index) for index, entry in enumerate(files)]


def parse_file(entry, index):
    where = f"files[{index}]"
    if not isinstance(entry, dict):
        raise PagesError(f"{where} must be an object")
    for key in ("name", "tool", "file_id"):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            raise PagesError(f"{where}.{key} must be a non-empty string")
    tool = entry["tool"].strip().lower()
    result = {"name": entry["name"], "tool": tool, "file_id": entry["file_id"], "url": entry.get("url"), "roles": {}, "notes": []}
    if tool != "penpot":
        result["notes"].append(f"Operated by the {tool} tool's skill, not use-penpot")
        return result
    if not is_uuid(entry["file_id"]):
        raise PagesError(f"{where}.file_id is not a Penpot file ID")
    url = entry.get("url")
    if url is not None:
        if not isinstance(url, str) or not url.startswith("https://"):
            raise PagesError(f"{where}.url must be an HTTPS address")
        # Penpot puts query parameters in the URL fragment, for example #/workspace?file-id=...
        parts = urlsplit(url)
        query = parse_qs(parts.query) | parse_qs(urlsplit(parts.fragment).query)
        named = query.get("file-id") or query.get("file_id")
        if named and named[0].lower() != entry["file_id"].lower():
            raise PagesError(f"{where}.url names file {named[0]}, but file_id is {entry['file_id']}; correct the manifest")
        result["origin"] = f"{parts.scheme}://{parts.netloc}"
    pages = entry.get("pages")
    if not isinstance(pages, dict) or not pages:
        raise PagesError(f"{where}.pages must map roles to page names")
    seen = {}
    for role, value in pages.items():
        if role not in KNOWN_ROLES:
            result["notes"].append(f"Role {role!r} is not one of the manifest contract's roles")
        if isinstance(value, str):
            assigned = [{"page": value}]
        elif isinstance(value, list) and role not in SINGLE_ONLY_ROLES:
            assigned = []
            for item_index, item in enumerate(value):
                if not isinstance(item, dict) or not isinstance(item.get("page"), str):
                    raise PagesError(f"{where}.pages.{role}[{item_index}] must be an object with a page name")
                owner = item.get("owner")
                if owner is not None and not isinstance(owner, str):
                    raise PagesError(f"{where}.pages.{role}[{item_index}].owner must be a string")
                assigned.append({"page": item["page"]} | ({"owner": owner} if owner is not None else {}))
        else:
            kind = "a single page name" if role in SINGLE_ONLY_ROLES else "a page name or a list of owned pages"
            raise PagesError(f"{where}.pages.{role} must be {kind}")
        for item in assigned:
            name = item["page"]
            if not name.strip():
                raise PagesError(f"{where}.pages.{role} has an empty page name")
            if name != name.strip():
                result["notes"].append(f"The {role} page name {name!r} has surrounding spaces; it must match the page name exactly")
            if name in seen:
                raise PagesError(f"{where}.pages maps {name!r} to both {seen[name]} and {role}")
            seen[name] = role
        result["roles"][role] = assigned
    return result


def select_files(files, selector):
    if not selector:
        return files
    chosen = [f for f in files if selector in (f["name"], f["file_id"])]
    if len(chosen) != 1:
        raise PagesError(f"{'No' if not chosen else 'More than one'} manifest file matches {selector!r}; use its exact name or file_id")
    return chosen


def check_origin(entry, base):
    origin = entry.get("origin")
    if origin and origin.rstrip("/") != base:
        raise PagesError(f"The manifest places {entry['name']!r} on {origin}, but requests go to {base}; after confirming the instance, pass --base-url {origin}")


def resolve(entry, info):
    """Match manifest page names to pages in the file, exactly; report what is missing, ambiguous or unmapped."""
    names, order = page_names(info), page_order(info)
    by_name = {}
    for pid in order:
        by_name.setdefault(names.get(pid), []).append(pid)
    roles, missing, ambiguous, mapped = {}, [], [], set()
    for role, assigned in entry["roles"].items():
        resolved = []
        for item in assigned:
            ids = by_name.get(item["page"], [])
            record = dict(item)
            if len(ids) == 1:
                record["page_id"] = ids[0]
                record["position"] = order.index(ids[0])
                mapped.add(ids[0])
            elif not ids:
                near = [n for n in by_name if n and n.strip().casefold() == item["page"].strip().casefold()]
                missing.append({"role": role, "page": item["page"]} | ({"similar_names": near} if near else {}))
            else:
                ambiguous.append({"role": role, "page": item["page"], "page_ids": ids})
            resolved.append(record)
        roles[role] = resolved
    unmapped = [{"page_id": pid, "name": names.get(pid), "position": i} for i, pid in enumerate(order) if pid not in mapped]
    notes = list(entry["notes"])
    if info.get("name") != entry["name"]:
        notes.append(f"The file is named {info.get('name')!r} in Penpot and {entry['name']!r} in the manifest")
    return {"file_name": info.get("name"), "revn": info.get("revn"), "roles": roles, "missing": missing, "ambiguous": ambiguous, "unmapped_pages": unmapped, "notes": notes}


def discover(files, rpc=None):
    report = []
    for entry in files:
        item = {k: entry[k] for k in ("name", "tool", "file_id", "url") if entry.get(k) is not None} | {"roles": entry["roles"], "notes": entry["notes"]}
        if rpc and entry["tool"] == "penpot":
            item |= resolve(entry, rpc("get-file", {"id": entry["file_id"]}))
        report.append(item)
    return report


def insert_at_index(elems, index, new):
    """Penpot's mov-page semantics (app.common.data/insert-at-index): split at index, drop the moved IDs from both sides, insert them between."""
    moved = set(new)
    return [e for e in elems[:index] if e not in moved] + list(new) + [e for e in elems[index:] if e not in moved]


def plan_order(current, requested):
    """Place the requested pages, in the requested order, in the positions they occupy now; every other page keeps its position."""
    if len(set(requested)) != len(requested):
        raise PagesError("A page is listed more than once")
    if len(set(current)) != len(current):
        raise PagesError("The file lists a page more than once; refusing to reorder it")
    absent = [p for p in requested if p not in current]
    if absent:
        raise PagesError(f"Not pages of this file: {', '.join(absent)}")
    slots = sorted(current.index(p) for p in requested)
    desired = list(current)
    for slot, pid in zip(slots, requested):
        desired[slot] = pid
    keep = pages_to_keep(current, desired, set(requested))
    working, changes = list(current), []
    for position, pid in enumerate(desired):
        if pid in keep:
            continue
        # Place the page straight after the page that precedes it in the wanted order.
        index = 0 if position == 0 else working.index(desired[position - 1]) + 1
        changes.append({"type": "mov-page", "id": pid, "index": index})
        working = insert_at_index(working, index, [pid])
    if working != desired:
        raise PagesError("Internal error: the planned moves do not produce the requested order")
    return desired, changes


def pages_to_keep(current, desired, listed):
    """The largest set of pages already in their wanted relative order, always including every unlisted page, so only the rest move."""
    target = {pid: i for i, pid in enumerate(desired)}
    sequence = [target[pid] for pid in current]
    weight = [1 if pid in listed else len(current) + 1 for pid in current]
    best, previous = list(weight), [-1] * len(current)
    for i in range(len(current)):
        for j in range(i):
            if sequence[j] < sequence[i] and best[j] + weight[i] > best[i]:
                best[i], previous[i] = best[j] + weight[i], j
    keep, i = set(), (max(range(len(current)), key=best.__getitem__) if current else -1)
    while i != -1:
        keep.add(current[i])
        i = previous[i]
    return keep


def resolve_pages(info, values):
    names, order = page_names(info), page_order(info)
    ids = []
    for value in values:
        if value in names:
            ids.append(value)
            continue
        matches = [pid for pid in order if names.get(pid) == value]
        if len(matches) == 1:
            ids.append(matches[0])
        elif matches:
            raise PagesError(f"{len(matches)} pages are named {value!r}; pass the page ID instead: {', '.join(matches)}")
        else:
            near = [names[pid] for pid in order if (names.get(pid) or "").strip().casefold() == value.strip().casefold()]
            raise PagesError(f"No page is named {value!r}" + (f"; similar: {near}" if near else ""))
    return ids


def build_order_plan(rpc, file_id, values):
    info = rpc("get-file", {"id": file_id})
    names, current = page_names(info), page_order(info)
    if set(current) != set(names):
        raise PagesError("The file's page list and page index disagree; refusing to reorder it")
    desired, changes = plan_order(current, resolve_pages(info, values))

    def describe(ids):
        return [{"page_id": pid, "name": names[pid]} for pid in ids]

    return {
        "file": {"id": file_id, "name": info.get("name"), "revn": info["revn"], "vern": info.get("vern", 0), "features": sorted(info.get("features") or [])},
        "current_order": describe(current),
        "proposed_order": describe(desired),
        "moved": [names[c["id"]] for c in changes],
        "changes": changes,
    }


def order_digest(plan):
    material = {"file": plan["file"], "current": plan["current_order"], "proposed": plan["proposed_order"], "changes": plan["changes"]}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def readback(rpc, plan):
    info = rpc("get-file", {"id": plan["file"]["id"]})
    names, actual = page_names(info), page_order(info)
    expected = [p["page_id"] for p in plan["proposed_order"]]
    previous = [p["page_id"] for p in plan["current_order"]]
    expected_names = {p["page_id"]: p["name"] for p in plan["proposed_order"]}
    state = "proposed" if actual == expected else "previous" if actual == previous else "other"
    return {"revn": info.get("revn"), "order": state, "names_unchanged": names == expected_names, "actual_order": [{"page_id": pid, "name": names.get(pid)} for pid in actual]}


def execute_order(rpc, plan, session_id=None):
    file = plan["file"]
    session_id = session_id or str(uuid.uuid4())
    try:
        response = rpc("update-file", {"id": file["id"], "sessionId": session_id, "revn": file["revn"], "vern": file["vern"], "features": file["features"], "changes": plan["changes"]})
    except BackendError as error:
        if error.outcome != "unknown":
            raise
        # The request may have been committed; report what the file shows now instead of retrying.
        try:
            state = readback(rpc, plan)
        except BackendError:
            state = None
        raise PagesError(f"{error}; the write may or may not have landed. Readback: {json.dumps(state) if state else 'unavailable'}. Preview again before deciding anything; do not repeat the execution blindly", "unknown")
    # Penpot applies an older revision's changes on top of newer ones; lagged changes from other sessions show that happened.
    lagged = [c for c in ((response or {}).get("lagged") or []) if c.get("sessionId") != session_id]
    result = readback(rpc, plan)
    result["concurrent_changes"] = len(lagged)
    result["verified"] = result["order"] == "proposed" and result["names_unchanged"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("discover", help="List the manifest's files and page roles; --resolve matches them to the actual file, read-only")
    find.add_argument("--manifest", default="design-files.json", help="Project manifest (default ./design-files.json)")
    find.add_argument("--file", help="Exact manifest file name or file_id")
    find.add_argument("--resolve", action="store_true", help="Read each Penpot file and match page names to pages")
    find.add_argument("--base-url", default=DEFAULT_BASE, help=f"Penpot instance (default {DEFAULT_BASE})")
    order = sub.add_parser("order", help="Preview or execute a page order")
    order.add_argument("--file-id", help="Penpot file ID; or select a manifest file with --manifest and --file")
    order.add_argument("--manifest", help="Project manifest to take the file ID from")
    order.add_argument("--file", help="Exact manifest file name or file_id")
    order.add_argument("--page", action="append", required=True, help="Page ID or exact unique page name, in the wanted order; repeat")
    order.add_argument("--base-url", default=DEFAULT_BASE, help=f"Penpot instance (default {DEFAULT_BASE})")
    order.add_argument("--execute", action="store_true", help="Write the reviewed order; default is a read-only preview")
    order.add_argument("--expect-plan", help="plan_sha256 from the preview; required with --execute")
    args = parser.parse_args(argv)
    try:
        base = args.base_url.rstrip("/")
        if not base.startswith("https://"):
            raise PagesError("--base-url must use HTTPS")
        if args.command == "discover":
            files = select_files(load_manifest(args.manifest), args.file)
            rpc = None
            if args.resolve:
                for entry in files:
                    if entry["tool"] == "penpot":
                        check_origin(entry, base)
                rpc = curl_rpc(base, access_token())
            print(json.dumps({"manifest": str(Path(args.manifest).resolve()), "files": discover(files, rpc)}, indent=2, ensure_ascii=False))
            return 0
        file_id = args.file_id
        if args.manifest:
            entry = select_files(load_manifest(args.manifest), args.file)
            if len(entry) != 1:
                raise PagesError("The manifest lists several files; select one with --file")
            if entry[0]["tool"] != "penpot":
                raise PagesError(f"{entry[0]['name']!r} is a {entry[0]['tool']} file; use-penpot operates only Penpot files")
            check_origin(entry[0], base)
            if file_id and file_id != entry[0]["file_id"]:
                raise PagesError("--file-id differs from the manifest's file_id")
            file_id = entry[0]["file_id"]
        if not file_id or not is_uuid(file_id):
            raise PagesError("Pass --file-id, or --manifest with --file")
        rpc = curl_rpc(base, access_token())
        plan = build_order_plan(rpc, file_id, args.page)
        digest = order_digest(plan)
        report = {k: plan[k] for k in ("file", "current_order", "proposed_order", "moved")} | {"change_count": len(plan["changes"]), "plan_sha256": digest, "mode": "execute" if args.execute else "preview"}
        if plan["changes"]:
            report["effect"] = "Changes the page order everyone with the file open sees, immediately. Pages and their content are unchanged, and nobody's open page switches."
        if args.execute:
            if args.expect_plan != digest:
                raise PagesError("The plan differs from the reviewed preview (the file may have changed); preview again")
            if not plan["changes"]:
                report["verified"] = True
                report["note"] = "Already in this order; nothing written"
            else:
                report["result"] = execute_order(rpc, plan)
                report["verified"] = report["result"]["verified"]
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.execute and not report.get("verified"):
            print("penpot_pages: the readback does not match the plan; see result.actual_order and preview again", file=sys.stderr)
            return 2
        return 0
    except BackendError as error:
        print(f"penpot_pages: {error}", file=sys.stderr)
        return 3 if error.outcome == "unknown" else 1


if __name__ == "__main__":
    sys.exit(main())
