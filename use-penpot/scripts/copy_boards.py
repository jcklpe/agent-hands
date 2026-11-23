#!/usr/bin/env python3
"""Copy top-level Penpot boards to another page of the same file through Penpot's backend API.

The Plugin API changes only the open page, so it cannot copy boards between pages; this command can. It previews by default: it reads the boards and the file's revision and prints the plan with a plan_sha256 digest. `--execute --expect-plan <digest>` writes the reviewed copies, refusing if the file changed since the preview, and then reads them back. Copies get new IDs; links between copied boards point at the copies, and links to anything else are dropped and reported. The access token comes from setup-penpot's configuration (PENPOT_ACCESS_TOKEN) and reaches curl on standard input, never in arguments or output.
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


def copy_id(file_id, page_id, revn, source_id):
    return str(uuid.uuid5(ID_NAMESPACE, f"{file_id}:{page_id}:{revn}:{source_id}"))


def build_plan(rpc, file_id, from_page, to_page, board_ids):
    info = rpc("get-file", {"id": file_id})
    names = page_names(info)
    for label, pid in (("source", from_page), ("target", to_page)):
        if pid not in names:
            raise CopyError(f"The {label} page is not in this file")
    if from_page == to_page:
        raise CopyError("Source and target pages must differ")
    revn, vern = info["revn"], info.get("vern", 0)
    subtrees = {}
    for board in board_ids:
        objects = (rpc("get-page", {"fileId": file_id, "pageId": from_page, "objectId": board}) or {}).get("objects") or {}
        root = objects.get(board)
        if not root or root.get("type") != "frame" or root.get("parentId") != ZERO:
            raise CopyError(f"{board} is not a top-level board on the source page")
        subtrees[board] = objects
    target = (rpc("get-page", {"fileId": file_id, "pageId": to_page}) or {}).get("objects") or {}
    return plan_changes(file_id, to_page, revn, subtrees, target) | {
        "file": {"id": file_id, "name": info.get("name"), "revn": revn, "vern": vern, "features": sorted(info.get("features") or [])},
        "from_page": {"id": from_page, "name": names[from_page]},
        "to_page": {"id": to_page, "name": names[to_page]},
    }


def plan_changes(file_id, to_page, revn, subtrees, target_objects):
    """Pure transformation from source subtrees to add-obj changes; separated so it can be tested offline."""
    ids = {sid: copy_id(file_id, to_page, revn, sid) for objects in subtrees.values() for sid in objects}
    copied_boards = set(subtrees)
    changes, boards, dropped, warnings = [], [], [], []
    top_level = [o for o in target_objects.values() if o.get("parentId") == ZERO and o.get("id") != ZERO]
    for board, objects in subtrees.items():
        order, stack = [], [board]
        while stack:
            sid = stack.pop(0)
            if sid not in objects:
                raise CopyError(f"Shape {sid} is missing from the source data")
            order.append(sid)
            stack = list(objects[sid].get("shapes") or []) + stack
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
            kept = []
            for interaction in obj.get("interactions") or []:
                dest = interaction.get("destination")
                relative = interaction.get("positionRelativeTo")
                if dest and dest not in ids:
                    dropped.append({"shape": source.get("name"), "board": objects[board].get("name"), "destination": dest})
                    continue
                if dest:
                    interaction["destination"] = ids[dest]
                if relative:
                    interaction["positionRelativeTo"] = ids.get(relative, None)
                kept.append(interaction)
            if "interactions" in obj:
                obj["interactions"] = kept
            changes.append({"type": "add-obj", "id": obj["id"], "pageId": to_page, "frameId": obj["frameId"], "parentId": obj["parentId"], "obj": obj, "ignoreTouched": True})
        root = objects[board]
        for other in top_level:
            if other.get("name") == root.get("name"):
                warnings.append(f"The target page already has a board named {root.get('name')!r}")
            if overlaps(root, other):
                warnings.append(f"{root.get('name')!r} overlaps {other.get('name')!r} on the target page")
        boards.append({"source_id": board, "copy_id": ids[board], "name": root.get("name"), "shapes": len(order)})
    return {"boards": boards, "copied_boards": sorted(copied_boards), "dropped_links": dropped, "warnings": warnings, "changes": changes}


def overlaps(a, b):
    try:
        return a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]
    except (KeyError, TypeError):
        return False


def plan_digest(plan):
    material = {"file": plan["file"], "to_page": plan["to_page"]["id"], "changes": plan["changes"]}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def summary(plan):
    return {k: plan[k] for k in ("file", "from_page", "to_page", "boards", "dropped_links", "warnings")} | {"change_count": len(plan["changes"])}


def execute(rpc, plan):
    file = plan["file"]
    rpc("update-file", {"id": file["id"], "sessionId": str(uuid.uuid4()), "revn": file["revn"], "vern": file["vern"], "features": file["features"], "changes": plan["changes"]})
    verified = []
    for board in plan["boards"]:
        objects = (rpc("get-page", {"fileId": file["id"], "pageId": plan["to_page"]["id"], "objectId": board["copy_id"]}) or {}).get("objects") or {}
        verified.append({"name": board["name"], "copy_id": board["copy_id"], "expected_shapes": board["shapes"], "found_shapes": len(objects)})
    return verified


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--from-page", required=True, help="Source page ID")
    parser.add_argument("--to-page", required=True, help="Target page ID")
    parser.add_argument("--board", action="append", required=True, help="Top-level board ID on the source page; repeat for several")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help=f"Penpot instance (default {DEFAULT_BASE})")
    parser.add_argument("--execute", action="store_true", help="Write the reviewed plan; default is a read-only preview")
    parser.add_argument("--expect-plan", help="plan_sha256 from the preview; required with --execute")
    args = parser.parse_args(argv)
    try:
        if not args.base_url.startswith("https://"):
            raise CopyError("--base-url must use HTTPS")
        rpc = curl_rpc(args.base_url.rstrip("/"), access_token())
        plan = build_plan(rpc, args.file_id, args.from_page, args.to_page, list(dict.fromkeys(args.board)))
        digest = plan_digest(plan)
        report = summary(plan) | {"plan_sha256": digest, "mode": "execute" if args.execute else "preview"}
        if args.execute:
            if args.expect_plan != digest:
                raise CopyError("The plan differs from the reviewed preview (the file may have changed); preview again")
            report["verified"] = execute(rpc, plan)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except CopyError as error:
        print(f"copy_boards: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
