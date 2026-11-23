#!/usr/bin/env python3
"""Copy top-level Penpot boards to another page of the same file, or replace boards there, through Penpot's backend API.

The Plugin API changes only the open page, so it cannot copy boards between pages; this command can. It previews by default: it reads the boards and the file's revision and prints the plan with a plan_sha256 digest. `--execute --expect-plan <digest>` writes the reviewed plan, refusing if the file changed since the preview, and then reads every written shape back. Copies get new IDs; links between copied boards point at the copies, `--link` points links at existing boards on the target page, and links to anything else are dropped and reported.

`--replace SOURCE=TARGET` replaces an existing top-level board on the target page with a copy of a source board. The target keeps its ID, its layer position and its lock and hidden state, so links, flows and comments aimed at it keep working; everything else, including position and size, comes from the source, and its old contents are deleted. Before writing, the command saves the old board to a private journal and saves a locked named version of the file. The access token comes from setup-penpot's configuration (PENPOT_ACCESS_TOKEN) and reaches curl on standard input, never in arguments or output.
"""
import argparse
import copy
import hashlib
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from penpot_backend import DEFAULT_BASE, ZERO, BackendError as CopyError, access_token, curl_rpc, page_names  # noqa: E402

ID_NAMESPACE = uuid.UUID("6f1d2c4e-8a5b-4f3e-9c7d-2b1a0e9f8c6d")
# A replaced board keeps these from the board it replaces; promotion locks promoted boards, and hiding is the file owner's choice.
KEPT_FROM_TARGET = ("blocked", "hidden")
EMPTY = (None, [], {})


def copy_id(file_id, page_id, revn, source_id):
    return str(uuid.uuid5(ID_NAMESPACE, f"{file_id}:{page_id}:{revn}:{source_id}"))


def subtree_order(objects, root_id):
    """A shape and its descendants, parents first, in drawing order."""
    order, stack = [], [root_id]
    while stack:
        sid = stack.pop(0)
        if sid not in objects:
            raise CopyError(f"Shape {sid} is missing from the page data")
        order.append(sid)
        stack = list(objects[sid].get("shapes") or []) + stack
    return order


def parse_pairs(values, option):
    pairs = []
    for value in values or []:
        if value.count("=") != 1:
            raise CopyError(f"--{option} takes SOURCE=TARGET board IDs")
        source, target = (part.strip() for part in value.split("="))
        if not source or not target:
            raise CopyError(f"--{option} takes SOURCE=TARGET board IDs")
        pairs.append((source, target))
    return pairs


def build_plan(rpc, file_id, from_page, to_page, board_ids, replace_pairs=(), link_pairs=()):
    info = rpc("get-file", {"id": file_id})
    names = page_names(info)
    for label, pid in (("source", from_page), ("target", to_page)):
        if pid not in names:
            raise CopyError(f"The {label} page is not in this file")
    if from_page == to_page:
        raise CopyError("Source and target pages must differ")
    sources = list(board_ids) + [source for source, _ in replace_pairs]
    if len(set(sources)) != len(sources):
        raise CopyError("A source board is listed more than once")
    targets = [target for _, target in replace_pairs]
    if len(set(targets)) != len(targets):
        raise CopyError("A target board is replaced more than once")
    revn, vern = info["revn"], info.get("vern", 0)
    subtrees = {}
    for board in sources:
        objects = (rpc("get-page", {"fileId": file_id, "pageId": from_page, "objectId": board}) or {}).get("objects") or {}
        root = objects.get(board)
        if not root or root.get("type") != "frame" or root.get("parentId") != ZERO:
            raise CopyError(f"{board} is not a top-level board on the source page")
        subtrees[board] = objects
    page = rpc("get-page", {"fileId": file_id, "pageId": to_page}) or {}
    target = page.get("objects") or {}
    replace, incoming = {}, {}
    if replace_pairs:
        replace = describe_targets(target, replace_pairs)
        incoming = check_references(page, replace)
    links = {}
    if link_pairs:
        source_page = (rpc("get-page", {"fileId": file_id, "pageId": from_page}) or {}).get("objects") or {}
        links = check_links(link_pairs, source_page, target, set(sources))
    plan = plan_changes(file_id, to_page, revn, subtrees, target, replace, links)
    for item in plan["replacements"]:
        item["incoming_links_kept"] = incoming.get(item["target_id"], 0)
    return plan | {
        "file": {"id": file_id, "name": info.get("name"), "revn": revn, "vern": vern, "features": sorted(info.get("features") or [])},
        "from_page": {"id": from_page, "name": names[from_page]},
        "to_page": {"id": to_page, "name": names[to_page]},
    }


def describe_targets(target, pairs):
    """Check each board to be replaced and capture its complete current subtree as the preimage."""
    root = target.get(ZERO)
    if not root:
        raise CopyError("The target page's root is missing from the page data")
    top = list(root.get("shapes") or [])
    found = {}
    for source, tid in pairs:
        board = target.get(tid)
        if not board or board.get("type") != "frame" or board.get("parentId") != ZERO or tid not in top:
            raise CopyError(f"{tid} is not a top-level board on the target page")
        order = subtree_order(target, tid)
        for sid in order:
            if target[sid].get("mainInstance"):
                raise CopyError(f"{target[sid].get('name')!r} in {board.get('name')!r} is a component's main shape; replacing the board would delete it")
        found[source] = {"target_id": tid, "index": top.index(tid), "old": [copy.deepcopy(target[sid]) for sid in order]}
    return found


def check_references(page, replace):
    """Refuse when anything outside the replaced boards points into their old contents; count the links aimed at the boards themselves, which keep working."""
    objects = page.get("objects") or {}
    inside, removed, roots = set(), set(), set()
    for item in replace.values():
        ids = [o["id"] for o in item["old"]]
        inside |= set(ids)
        roots.add(ids[0])
        removed |= set(ids[1:])
    problems, incoming = [], {}
    for oid, obj in objects.items():
        if oid in inside:
            continue
        for interaction in obj.get("interactions") or []:
            for key in ("destination", "positionRelativeTo"):
                ref = interaction.get(key)
                if ref in removed:
                    problems.append(f"{obj.get('name')!r} refers to {objects.get(ref, {}).get('name')!r} inside a board being replaced")
            if interaction.get("destination") in roots:
                incoming[interaction["destination"]] = incoming.get(interaction["destination"], 0) + 1
    flows = page.get("flows") or {}
    for flow in flows.values() if isinstance(flows, dict) else flows:
        if isinstance(flow, dict) and flow.get("startingFrame") in removed:
            problems.append(f"flow {flow.get('name')!r} starts inside a board being replaced")
    if problems:
        raise CopyError("Replacing would break references: " + "; ".join(problems[:10]) + ". Retarget or remove them first, then preview again")
    return incoming


def check_links(pairs, source_page, target, sources):
    links = {}
    for source, tid in pairs:
        if source in sources:
            raise CopyError(f"{source} is copied in this plan, so links to it already follow the copy")
        if source in links:
            raise CopyError(f"{source} is linked more than once")
        if (source_page.get(source) or {}).get("type") != "frame":
            raise CopyError(f"{source} is not a board on the source page")
        if (target.get(tid) or {}).get("type") != "frame":
            raise CopyError(f"{tid} is not a board on the target page")
        links[source] = tid
    return links


def plan_changes(file_id, to_page, revn, subtrees, target_objects, replace=None, links=None):
    """Pure transformation from source subtrees to update-file changes; separated so it can be tested offline."""
    replace, links = replace or {}, links or {}
    ids = {sid: copy_id(file_id, to_page, revn, sid) for objects in subtrees.values() for sid in objects}
    for board, item in replace.items():
        ids[board] = item["target_id"]
    replaced_targets = {item["target_id"] for item in replace.values()}
    changes, boards, replacements, dropped, warnings, suggestions = [], [], [], [], [], []
    top_level = [o for o in target_objects.values() if o.get("parentId") == ZERO and o.get("id") != ZERO and o.get("id") not in replaced_targets]
    for board, objects in subtrees.items():
        order = subtree_order(objects, board)
        item = replace.get(board)
        if item:
            # del-obj removes the old board and everything in it; the board is then added again under the same ID at the same layer position.
            changes.append({"type": "del-obj", "id": item["target_id"], "pageId": to_page, "ignoreTouched": True})
        for sid in order:
            source = objects[sid]
            if source.get("mainInstance"):
                raise CopyError(f"{source.get('name')} is a component's main shape; copy an instance instead")
            obj = copy.deepcopy(source)
            obj["id"] = ids[sid]
            obj["parentId"] = ids.get(source.get("parentId"), ZERO)
            obj["frameId"] = ids.get(source.get("frameId"), ZERO)
            if "shapes" in obj:
                obj["shapes"] = []
            if item and sid == board:
                old_root = item["old"][0]
                for key in KEPT_FROM_TARGET:
                    if key in old_root:
                        obj[key] = copy.deepcopy(old_root[key])
                    else:
                        obj.pop(key, None)
            kept = []
            for interaction in obj.get("interactions") or []:
                dest = interaction.get("destination")
                relative = interaction.get("positionRelativeTo")
                if dest and dest not in ids and dest not in links:
                    dropped.append({"shape": source.get("name"), "board": objects[board].get("name"), "destination": dest})
                    continue
                if dest:
                    interaction["destination"] = ids.get(dest) or links[dest]
                if relative:
                    interaction["positionRelativeTo"] = ids.get(relative, None)
                kept.append(interaction)
            if "interactions" in obj:
                obj["interactions"] = kept
            change = {"type": "add-obj", "id": obj["id"], "pageId": to_page, "frameId": obj["frameId"], "parentId": obj["parentId"], "obj": obj, "ignoreTouched": True}
            if item and sid == board:
                change["index"] = item["index"]
            changes.append(change)
        root = objects[board]
        for other in top_level:
            if not item and other.get("name") == root.get("name"):
                warnings.append(f"The target page already has a board named {root.get('name')!r}")
            if overlaps(root, other):
                warnings.append(f"{root.get('name')!r} overlaps {other.get('name')!r} on the target page")
        if item:
            old = item["old"][0]
            if old.get("name") != root.get("name"):
                warnings.append(f"{root.get('name')!r} replaces a board named {old.get('name')!r}")
            replacements.append({"source_id": board, "target_id": item["target_id"], "name": root.get("name"), "replaces": old.get("name"), "index": item["index"], "old_shapes": len(item["old"]), "new_shapes": len(order), "kept": {k: old[k] for k in KEPT_FROM_TARGET if k in old}})
        else:
            same = [o for o in top_level if o.get("name") == root.get("name")]
            if len(same) == 1:
                suggestions.append({"board": root.get("name"), "replace": f"{board}={same[0]['id']}"})
            boards.append({"source_id": board, "copy_id": ids[board], "name": root.get("name"), "shapes": len(order)})
    return {"boards": boards, "replacements": replacements, "copied_boards": sorted(subtrees), "dropped_links": dropped, "warnings": warnings, "suggestions": suggestions, "changes": changes, "preimages": {item["target_id"]: item["old"] for item in replace.values()}}


def overlaps(a, b):
    try:
        return a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]
    except (KeyError, TypeError):
        return False


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_digest(plan):
    material = {"file": plan["file"], "to_page": plan["to_page"]["id"], "changes": plan["changes"], "preimages": {tid: fingerprint(old) for tid, old in (plan.get("preimages") or {}).items()}}
    return fingerprint(material)


def summary(plan):
    report = {k: plan[k] for k in ("file", "from_page", "to_page", "boards", "dropped_links", "warnings")} | {"change_count": len(plan["changes"])}
    if plan.get("replacements"):
        report["replacements"] = plan["replacements"]
        report["effect"] = "Each replaced board keeps its ID, layer position, lock and hidden state; its old contents are deleted and the source's contents take their place, at the source's position and size. A locked named version and a private copy of the old board are saved first."
    if plan.get("suggestions"):
        report["suggestions"] = plan["suggestions"]
    return report


def planned_tree(changes):
    planned, children = {}, {}
    for change in changes:
        if change["type"] == "add-obj":
            planned[change["id"]] = change["obj"]
            children.setdefault(change["parentId"], []).append(change["id"])
    return planned, children


def planned_order(root_id, children):
    order, stack = [], [root_id]
    while stack:
        sid = stack.pop(0)
        order.append(sid)
        stack = list(children.get(sid, [])) + stack
    return order


def same(actual, expected):
    # Penpot may omit an empty list or map that a plan carries; both mean the same thing.
    return actual == expected or (actual in EMPTY and expected in EMPTY)


def verify(rpc, plan, page=None):
    """Read the target page and compare every written shape, field by field, with the plan, plus child order and replaced boards' layer positions."""
    if page is None:
        page = (rpc("get-page", {"fileId": plan["file"]["id"], "pageId": plan["to_page"]["id"]}) or {}).get("objects") or {}
    planned, children = planned_tree(plan["changes"])
    roots = [(b["name"], b["copy_id"], None) for b in plan.get("boards", [])] + [(r["name"], r["target_id"], r["index"]) for r in plan.get("replacements", [])]
    results = []
    for name, rid, index in roots:
        expected = planned_order(rid, children)
        problems = []
        try:
            actual = subtree_order(page, rid)
        except CopyError:
            actual = None
            problems.append("not found as planned")
        if actual is not None:
            if actual != expected:
                problems.append("its shapes or their order differ from the plan")
            for sid in expected:
                if sid in page:
                    diff = sorted(k for k, v in planned[sid].items() if k != "shapes" and not same(page[sid].get(k), v))
                    if diff:
                        problems.append(f"{planned[sid].get('name')!r} differs in {', '.join(diff[:6])}")
        if index is not None:
            top = list((page.get(ZERO) or {}).get("shapes") or [])
            if rid not in top or top.index(rid) != index:
                problems.append("its layer position differs from the plan")
        results.append({"name": name, "id": rid, "expected_shapes": len(expected), "found_shapes": len(actual or []), "matches": not problems} | ({"problems": problems[:10]} if problems else {}))
    return results


def execute(rpc, plan):
    """Write a plan that only adds copies; replacements go through guarded_execute."""
    file = plan["file"]
    rpc("update-file", {"id": file["id"], "sessionId": str(uuid.uuid4()), "revn": file["revn"], "vern": file["vern"], "features": file["features"], "changes": plan["changes"]})
    return verify(rpc, plan)


def save_locked_version(rpc, file_id, label):
    created = rpc("create-file-snapshot", {"fileId": file_id, "label": label}) or {}
    version_id = created.get("id") if isinstance(created, dict) else None
    if not version_id:
        raise CopyError("Penpot did not return the new version's ID")
    rpc("lock-file-snapshot", {"id": version_id})
    listing = rpc("get-file-snapshots", {"fileId": file_id}) or []
    entry = next((s for s in listing if isinstance(s, dict) and s.get("id") == version_id), None)
    if not entry:
        raise CopyError("The new version is not in the file's version list")
    if "lockedBy" in entry and not entry["lockedBy"]:
        raise CopyError("The new version is not locked")
    return {"id": version_id, "label": entry.get("label", label)}


def record_content(plan, digest, label, kind):
    _, children = planned_tree(plan["changes"])
    return {
        "kind": kind, "file_id": plan["file"]["id"], "to_page": plan["to_page"]["id"], "plan_sha256": digest, "revn": plan["file"]["revn"], "vern": plan["file"]["vern"], "version_label": label,
        "replacements": [{"source_id": r.get("source_id"), "target_id": r["target_id"], "name": r["name"], "index": r["index"], "old_objects": plan["preimages"][r["target_id"]], "new_ids": planned_order(r["target_id"], children)} for r in plan["replacements"]],
        "additions": [{"source_id": b["source_id"], "copy_id": b["copy_id"], "name": b["name"]} for b in plan.get("boards", [])],
        "changes": plan["changes"],
    }


def guarded_execute(rpc, journal, plan, digest, label, kind="replace", extra=None):
    """Journal the preimage, save a locked version, check the file again, send one update and read it back. Never retries."""
    targets = [r["target_id"] for r in plan["replacements"]]
    blocking = journal.blocking(targets)
    if blocking:
        raise CopyError("Earlier replacements of these boards have unresolved outcomes: " + ", ".join(str(r.path) for r in blocking) + ". Reconcile them with board_journal.py first")
    record = journal.create(record_content(plan, digest, label, kind) | (extra or {}))
    file = plan["file"]
    try:
        version = save_locked_version(rpc, file["id"], label)
    except CopyError as error:
        record.advance("aborted", note=f"version not saved: {error}")
        raise CopyError(f"{error}; nothing was replaced. Record: {record.path}")
    record.advance("version_locked", version=version)
    info = rpc("get-file", {"id": file["id"]})
    if info.get("revn") != file["revn"] or info.get("vern", 0) != file["vern"]:
        record.advance("aborted", note="the file changed after the preview")
        raise CopyError(f"The file changed after the preview; nothing was replaced. The saved version {version['label']!r} remains. Preview again")
    from penpot_journal import stamp
    session = str(uuid.uuid4())
    # Recorded and flushed before the request leaves, so an interruption after this point is treated as possibly applied.
    record.advance("dispatched", session_id=session, dispatched_at=stamp())
    try:
        response = rpc("update-file", {"id": file["id"], "sessionId": session, "revn": file["revn"], "vern": file["vern"], "features": file["features"], "changes": plan["changes"]})
    except CopyError as error:
        if error.outcome == "unknown":
            record.advance("uncertain", note=str(error))
            raise CopyError(f"{error}; the replacement may or may not have landed and will not be retried. Reconcile with board_journal.py reconcile --journal {record.path}", "unknown")
        record.advance("refused", note=str(error))
        raise CopyError(f"{error}; nothing was replaced. Record: {record.path}")
    lagged = [c for c in ((response or {}).get("lagged") or []) if c.get("sessionId") != session]
    try:
        verified = verify(rpc, plan)
    except CopyError as error:
        raise CopyError(f"The update was accepted but could not be read back ({error}); reconcile with board_journal.py reconcile --journal {record.path}", "unknown")
    matches = all(v["matches"] for v in verified)
    record.advance("verified" if matches else "mismatch", verified=verified, concurrent_changes=len(lagged))
    return {"verified": verified, "all_match": matches, "concurrent_changes": len(lagged), "version": version, "journal": str(record.path)}


def default_label(prefix, names):
    label = f"{prefix}: " + ", ".join(n or "unnamed" for n in names)
    return label if len(label) <= 120 else label[:117] + "..."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--from-page", required=True, help="Source page ID")
    parser.add_argument("--to-page", required=True, help="Target page ID")
    parser.add_argument("--board", action="append", default=[], help="Top-level board ID on the source page to copy; repeat for several")
    parser.add_argument("--replace", action="append", default=[], metavar="SOURCE=TARGET", help="Replace the top-level target-page board TARGET with a copy of source board SOURCE; repeat for several")
    parser.add_argument("--link", action="append", default=[], metavar="SOURCE=TARGET", help="Point links aimed at source-page board SOURCE, which is not copied, at target-page board TARGET")
    parser.add_argument("--version-label", help="Name of the locked version saved before a replacement")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help=f"Penpot instance (default {DEFAULT_BASE})")
    parser.add_argument("--execute", action="store_true", help="Write the reviewed plan; default is a read-only preview")
    parser.add_argument("--expect-plan", help="plan_sha256 from the preview; required with --execute")
    args = parser.parse_args(argv)
    try:
        if not args.base_url.startswith("https://"):
            raise CopyError("--base-url must use HTTPS")
        replace_pairs, link_pairs = parse_pairs(args.replace, "replace"), parse_pairs(args.link, "link")
        boards = list(dict.fromkeys(args.board))
        if not boards and not replace_pairs:
            raise CopyError("Pass --board or --replace")
        rpc = curl_rpc(args.base_url.rstrip("/"), access_token())

        def plan_and_digest():
            plan = build_plan(rpc, args.file_id, args.from_page, args.to_page, boards, replace_pairs, link_pairs)
            return plan, plan_digest(plan)

        if args.execute and replace_pairs:
            from penpot_journal import Journal, JournalError
            try:
                with Journal(args.file_id) as journal:
                    plan, digest = plan_and_digest()
                    if args.expect_plan != digest:
                        raise CopyError("The plan differs from the reviewed preview (the file may have changed); preview again")
                    label = args.version_label or default_label("Before replacing", [r["replaces"] for r in plan["replacements"]])
                    result = guarded_execute(rpc, journal, plan, digest, label)
            except JournalError as error:
                raise CopyError(str(error))
            report = summary(plan) | {"plan_sha256": digest, "mode": "execute"} | result
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0 if result["all_match"] else 2
        plan, digest = plan_and_digest()
        report = summary(plan) | {"plan_sha256": digest, "mode": "execute" if args.execute else "preview"}
        if args.execute:
            if args.expect_plan != digest:
                raise CopyError("The plan differs from the reviewed preview (the file may have changed); preview again")
            report["verified"] = execute(rpc, plan)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if all(v["matches"] for v in report.get("verified", [])) else 2
    except CopyError as error:
        print(f"copy_boards: {error}", file=sys.stderr)
        return 3 if error.outcome == "unknown" else 1


if __name__ == "__main__":
    sys.exit(main())
