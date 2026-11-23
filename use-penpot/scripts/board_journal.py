#!/usr/bin/env python3
"""List, reconcile, accept or undo board replacements recorded in use-penpot's private journal.

`list` shows a file's records and which ones block another replacement. `reconcile` reads the file and settles a record whose outcome was unknown: the planned contents mean it landed, the old contents mean it did not once enough time has passed, and anything else stays unresolved. `accept` records the user's decision to keep a board as it now is. `restore` previews putting a verified replacement's old contents back under the same board ID and, with `--execute --expect-plan <digest>`, does it with the same journal, locked version and readback as a replacement. Nothing here deletes a record.
"""
import argparse
import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import copy_boards as cb  # noqa: E402
from penpot_backend import DEFAULT_BASE, ZERO, BackendError, access_token, curl_rpc  # noqa: E402
import penpot_journal as pj  # noqa: E402

# A request whose connection was lost could still be running on the server; Penpot's calls end well within this, so an unchanged board after it means the write did not land.
SETTLE = timedelta(minutes=10)


def plan_from_record(data):
    return {"file": {"id": data["file_id"]}, "to_page": {"id": data["to_page"]}, "changes": data["changes"], "boards": [{"name": a["name"], "copy_id": a["copy_id"]} for a in data.get("additions", [])], "replacements": [{"name": r["name"], "target_id": r["target_id"], "index": r["index"]} for r in data.get("replacements", [])]}


def read_page(rpc, data):
    return (rpc("get-page", {"fileId": data["file_id"], "pageId": data["to_page"]}) or {}).get("objects") or {}


def states(page, data):
    """For each replaced board: 'new' when it holds the planned shapes, 'old' when it still holds its previous ones, otherwise 'other'. Copies: 'present' or 'absent'."""
    result = {}
    for item in data.get("replacements", []):
        try:
            ids = cb.subtree_order(page, item["target_id"])
        except BackendError:
            ids = None
        old = [o["id"] for o in item["old_objects"]]
        result[item["target_id"]] = "new" if ids == item["new_ids"] else "old" if ids == old else "other"
    for item in data.get("additions", []):
        result[item["copy_id"]] = "present" if item["copy_id"] in page else "absent"
    return result


def reconcile(rpc, record):
    data = record.data
    if record.stage in pj.BEFORE_WRITE:
        record.advance("aborted", note="interrupted before the write was sent")
        return {"stage": "aborted", "note": "Nothing was sent; the record is closed"}
    if record.stage not in pj.BLOCKING:
        return {"stage": record.stage, "note": "Already resolved; nothing to do"}
    page = read_page(rpc, data)
    found = states(page, data)
    verified = cb.verify(rpc, plan_from_record(data), page)
    if all(v["matches"] for v in verified):
        record.advance("verified", verified=verified, note="reconciled: the planned contents are in place")
        return {"stage": "verified", "states": found, "verified": verified}
    nothing = all(state in ("old", "absent") for state in found.values())
    dispatched = pj.parse_stamp(data.get("dispatched_at") or data["created_at"])
    if nothing and pj.now() - dispatched >= SETTLE:
        record.advance("not_applied", note="reconciled: the old contents are unchanged after the settling time")
        return {"stage": "not_applied", "states": found}
    if nothing:
        wait = dispatched + SETTLE
        return {"stage": record.stage, "states": found, "note": f"The old contents are still in place, but the request could still finish; reconcile again after {pj.stamp(wait)}"}
    if record.stage != "mismatch":
        record.advance("mismatch", verified=verified, note="reconciled: the file matches neither the plan nor the old contents")
    return {"stage": "mismatch", "states": found, "verified": verified, "note": "Inspect the boards. Run accept once the user decides to keep them as they are, or restore the locked version by hand"}


def restore_plan(rpc, data):
    """Plan putting each replaced board's old contents back under the same ID, provided nobody has changed it since the replacement."""
    if data.get("kind") != "replace":
        raise BackendError("Only a replacement record can be restored")
    info = rpc("get-file", {"id": data["file_id"]})
    page = read_page(rpc, data)
    verified = cb.verify(rpc, plan_from_record(data) | {"boards": []}, page)
    changed = [v["name"] for v in verified if not v["matches"]]
    if changed:
        raise BackendError(f"{', '.join(map(repr, changed))} changed after the replacement; restoring would discard those changes. Use the locked version {data.get('version', {}).get('label')!r} or restore by hand")
    top = list((page.get(ZERO) or {}).get("shapes") or [])
    changes, replacements, preimages = [], [], {}
    for item in data["replacements"]:
        tid = item["target_id"]
        preimages[tid] = [copy.deepcopy(page[sid]) for sid in cb.subtree_order(page, tid)]
        changes.append({"type": "del-obj", "id": tid, "pageId": data["to_page"], "ignoreTouched": True})
        for index, original in enumerate(item["old_objects"]):
            obj = copy.deepcopy(original)
            if "shapes" in obj:
                obj["shapes"] = []
            change = {"type": "add-obj", "id": obj["id"], "pageId": data["to_page"], "frameId": obj.get("frameId", ZERO), "parentId": obj.get("parentId", ZERO), "obj": obj, "ignoreTouched": True}
            if index == 0:
                change["index"] = top.index(tid)
            changes.append(change)
        replacements.append({"source_id": None, "target_id": tid, "name": item["old_objects"][0].get("name"), "replaces": item["name"], "index": top.index(tid)})
    return {"file": {"id": data["file_id"], "name": info.get("name"), "revn": info["revn"], "vern": info.get("vern", 0), "features": sorted(info.get("features") or [])}, "to_page": {"id": data["to_page"]}, "changes": changes, "boards": [], "replacements": replacements, "preimages": preimages}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="List a file's replacement records")
    listing.add_argument("--file-id", required=True)
    for name, text in (("reconcile", "Settle a record whose outcome is unknown"), ("accept", "Record the user's decision to keep the boards as they are"), ("restore", "Preview or execute undoing a verified replacement")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--journal", required=True, help="Path of the record, from list or the replacement's output")
        if name == "accept":
            command.add_argument("--note", required=True, help="What the user decided and why")
        if name == "restore":
            command.add_argument("--execute", action="store_true")
            command.add_argument("--expect-plan")
            command.add_argument("--version-label")
        if name != "accept":
            command.add_argument("--base-url", default=DEFAULT_BASE)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            journal = pj.Journal(args.file_id)
            records = journal.records() if journal.dir.exists() else []
            print(json.dumps({"records": [{"path": str(r.path), "kind": r.data.get("kind"), "stage": r.stage, "blocks_replacement": r.stage in pj.BLOCKING, "created_at": r.data.get("created_at"), "boards": [x["name"] for x in r.data.get("replacements", [])], "version": (r.data.get("version") or {}).get("label")} for r in records]}, indent=2, ensure_ascii=False))
            return 0
        journal, path, _ = pj.load(args.journal)
        with journal:
            record = pj.Record(path, json.loads(path.read_text(encoding="utf-8")))
            if args.command == "accept":
                if record.stage not in pj.BLOCKING:
                    raise BackendError(f"The record is {record.stage}; only an unresolved outcome can be accepted")
                record.advance("accepted", note=args.note)
                print(json.dumps({"stage": "accepted", "journal": str(path)}, indent=2))
                return 0
            if not args.base_url.startswith("https://"):
                raise BackendError("--base-url must use HTTPS")
            rpc = curl_rpc(args.base_url.rstrip("/"), access_token())
            if args.command == "reconcile":
                result = reconcile(rpc, record)
                print(json.dumps(result | {"journal": str(path)}, indent=2, ensure_ascii=False))
                return 0 if result["stage"] in pj.RESOLVED else 2
            if record.stage != "verified":
                raise BackendError(f"The record is {record.stage}; only a verified replacement can be restored this way")
            plan = restore_plan(rpc, record.data)
            digest = cb.plan_digest(plan)
            report = {"journal": str(path), "replacements": plan["replacements"], "change_count": len(plan["changes"]), "plan_sha256": digest, "mode": "execute" if args.execute else "preview", "effect": "Each board keeps its ID and layer position and gets its old contents back; the contents the replacement added are deleted. A locked named version and a private copy are saved first."}
            if args.execute:
                if args.expect_plan != digest:
                    raise BackendError("The plan differs from the reviewed preview (the file may have changed); preview again")
                label = args.version_label or cb.default_label("Before restoring", [r["replaces"] for r in plan["replacements"]])
                result = cb.guarded_execute(rpc, journal, plan, digest, label, kind="restore", extra={"restores": str(path)})
                if result["all_match"]:
                    record.advance("restored", note=f"restored by {result['journal']}")
                report |= result
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0 if report.get("all_match", True) else 2
    except (BackendError, pj.JournalError) as error:
        print(f"board_journal: {error}", file=sys.stderr)
        return 3 if getattr(error, "outcome", None) == "unknown" else 1


if __name__ == "__main__":
    sys.exit(main())
