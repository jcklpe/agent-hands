"""Bounded folder inspection and preview-bound same-drive organization."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, urlsplit, parse_qsl, unquote

CAPABILITY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAPABILITY_ROOT.parent / "setup-microsoft-services/scripts"))
from runtime_state import location
from bounded_client import Client, Store, canonical, digest, identifier

META = "id,name,size,eTag,cTag,file,folder,package,remoteItem,root,deleted,parentReference,webUrl,createdBy,lastModifiedBy,lastModifiedDateTime"
LIMIT = 50_000_000


def item_path(drive, item):
    return "/drives/" + quote(identifier(drive), safe="") + ("/root" if item == "root" else "/items/" + quote(identifier(item), safe=""))


def safe_name(name):
    if not isinstance(name, str) or not name.strip() or len(name) > 200 or name != name.strip() or name.endswith(".") or re.search(r'[\x00-\x1f\x7f"*:<>?/\\|]', name) or name.lower().endswith((".one", ".onetoc2")):
        raise ValueError("Use a plain file/folder name without reserved characters or OneNote extensions")
    return name


def metadata(client, drive, item):
    value = client.request("GET", item_path(drive, item) + "?$select=" + META)
    if (item != "root" and value.get("id") != item) or value.get("parentReference", {}).get("driveId") != drive:
        raise ValueError("Cloud item identity/drive mismatch")
    identifier(value.get("id"))
    return value


def ordinary(value, folder=False):
    if value.get("remoteItem") or value.get("package") or value.get("deleted") or value.get("name", "").lower().endswith((".one", ".onetoc2")):
        raise ValueError("Remote shortcuts, packages, deleted items and OneNote are unsupported")
    if folder and "folder" not in value:
        raise ValueError("Select an actual folder")
    if not folder and value.get("root") is not None:
        raise ValueError("The drive root cannot be changed")


def continuation(url, endpoint):
    if not isinstance(url, str) or len(url) > 16000:
        raise ValueError("Invalid collection continuation")
    parsed = urlsplit(url)
    # Graph may normalize percent-encoding (for example a drive ID's !). Compare decoded identity, then reuse our exact canonical endpoint below.
    if parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com" or parsed.fragment or unquote(parsed.path, errors="strict") != unquote("/v1.0" + endpoint, errors="strict") or any(k.lower() not in ("$skiptoken", "$skip", "$top", "$select", "$orderby") for k, _ in parse_qsl(parsed.query)):
        raise ValueError("Continuation points outside the exact selected collection")
    return endpoint + ("?" + parsed.query if parsed.query else "")


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in ("shareId", "webUrl", "@microsoft.graph.downloadUrl", "invitation", "@odata.context")}
    return [redact(v) for v in value] if isinstance(value, list) else value


def page(client, drive, item, kind, cursor=None, limit=100):
    if kind not in ("children", "permissions", "versions") or not 1 <= limit <= 200:
        raise ValueError("Invalid bounded collection")
    endpoint = item_path(drive, item) + "/" + kind
    scope = {"alias": client.alias, "drive": drive, "item": item, "kind": kind}
    if cursor:
        try:
            if len(cursor) > 24000: raise ValueError()
            data = json.loads(base64.urlsafe_b64decode(cursor))
            if data["scope"] != scope: raise ValueError()
            path = continuation(data["url"], endpoint)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("Use the continuation returned for this exact account and collection") from exc
    else:
        path = endpoint + ("?$top=" + str(limit) + "&$select=" + META if kind == "children" else "")
    response = client.request("GET", path)
    values = response.get("value")
    if not isinstance(values, list) or len(values) > 2000 or any(not isinstance(v, dict) or not v.get("id") for v in values) or len({v["id"] for v in values}) != len(values):
        raise ValueError("Invalid or oversized collection page")
    next_url = response.get("@odata.nextLink")
    if next_url: continuation(next_url, endpoint)
    token = base64.urlsafe_b64encode(canonical({"scope": scope, "url": next_url}).encode()).decode() if next_url else None
    return {"value": redact(values), "continuation": token, "complete": not bool(token), "coverage": "One response page; follow continuation until complete. Concurrent collection edits are not a snapshot."}


def complete(client, drive, item, kind):
    values, cursor, seen, ids = [], None, set(), set()
    for _ in range(10):
        response = page(client, drive, item, kind, cursor)
        for value in response["value"]:
            if value["id"] in ids: raise ValueError("Collection changed or repeated an item; repeat the read before previewing")
            ids.add(value["id"]); values.append(value)
        if len(values) > 2000: raise ValueError("Collection exceeds the 2,000-item verification bound")
        cursor = response["continuation"]
        if not cursor: return sorted(values, key=lambda v: v["id"])
        if cursor in seen: raise ValueError("Repeated continuation; completeness is unverified")
        seen.add(cursor)
    raise ValueError("Collection exceeds the 10-page verification bound; use bounded reads to inspect it")


def sharing(client, drive, item):
    owner = client.request("GET", "/drives/" + quote(identifier(drive), safe="") + "?$select=id,driveType,owner")
    if owner.get("id") != drive: raise ValueError("Drive identity mismatch")
    return {"drive": redact(owner), "permissions": complete(client, drive, item, "permissions"), "coverage": "Caller-visible effective permissions only. Non-owners may see only their own grants; group membership and full audience are not established. Drive owner is not file authorship."}


def content_hash(client, drive, item, size):
    if type(size) is not int or not 0 <= size <= LIMIT: raise ValueError("Content verification supports ordinary files up to 50 MB")
    with tempfile.TemporaryDirectory(prefix="agent-hands-file-") as directory:
        os.chmod(directory, 0o700)
        file = Path(directory) / "content"
        client.request("GET", item_path(drive, item) + "/content", output=file)
        if file.stat().st_size != size: raise ValueError("Downloaded size changed; no stable content baseline")
        with file.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(client, drive, item):
    value = metadata(client, drive, item); ordinary(value)
    if not value.get("eTag") or "file" not in value and "folder" not in value:
        raise ValueError("Missing ETag or ordinary file/folder type; no unguarded write is permitted")
    if "folder" in value:
        # A folder ETag does not change for descendant-derived properties; an empty-folder check cannot safely guard recursive side effects.
        raise ValueError("Only ordinary files can be organized; folder ETags do not guard descendant changes. Select individual files.")
    content = content_hash(client, drive, item, value.get("size"))
    versions = complete(client, drive, item, "versions")
    permissions = complete(client, drive, item, "permissions")
    latest = metadata(client, drive, item)
    if latest.get("eTag") != value["eTag"]: raise ValueError("Item changed during verification; make a fresh preview")
    return {"meta": value, "sha256": content, "versions": versions, "permissions": permissions}


def destination(client, drive, parent, name, source):
    folder = metadata(client, drive, parent); ordinary(folder, True)
    if folder["id"] == source: raise ValueError("Cannot move an item into itself")
    for value in complete(client, drive, folder["id"], "children"):
        if value["id"] != source and value.get("name", "").casefold() == name.casefold():
            raise ValueError("Destination name already exists; conflict replacement is forbidden")
    return {"id": folder["id"], "name": folder.get("name"), "permissions": complete(client, drive, folder["id"], "permissions")}


def recycle_reason(reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300 or re.search(r"[\x00-\x1f\x7f]", reason):
        raise ValueError("Recycle preview requires --reason: a concise, single-line explanation (1–300 characters) for deleting this file")
    return reason.strip()


def preview(client, store, action, drive, item, name=None, parent=None, reason=None):
    if action not in ("move", "rename", "recycle"): raise ValueError("Unsupported organization action")
    reason = recycle_reason(reason) if action == "recycle" else None
    identity = client.identity(); before = snapshot(client, drive, item)
    current = before["meta"]
    name = safe_name(name if name is not None else current["name"])
    parent = parent or current.get("parentReference", {}).get("id")
    if not parent: raise ValueError("Missing parent identity")
    dest = destination(client, drive, parent, name, item) if action != "recycle" else None
    if action != "recycle" and dest["id"] == current["parentReference"]["id"] and name == current["name"]:
        raise ValueError("No name or parent change was selected")
    review = {"files": [{"name": current["name"], "drive": drive, "item": item, "parent": current["parentReference"]["id"], "reason": reason}], "consent": "Obtain explicit consent for this itemized deletion separately from other actions; general cleanup approval is insufficient."} if action == "recycle" else None
    plan = store.plan({"kind": "file-organization-v1", "alias": client.alias, "action": action, "drive": drive, "item": item, "identity": identity, "before": before, "destination": dest, "name": name, "deletionReview": review})
    return {"status": "preview", **plan, "limits": "Same-drive ordinary files only. Moving can change inherited access; visible permissions and version history are not a complete audience or recovery guarantee. Recycle uses Graph's recycle-bin deletion, never purge. Folder mutations are refused because their ETags do not guard descendant changes."}


def verify(client, plan):
    drive, item = plan["drive"], plan["item"]
    if plan["action"] == "recycle":
        parent = plan["before"]["meta"]["parentReference"]["id"]
        found = any(v["id"] == item for v in complete(client, drive, parent, "children"))
        return {"status": "still_in_parent" if found else "absent_from_original_parent", "recovery": "Recycle-bin retention/restorability was not independently verified; inspect the service recycle bin."}
    after = snapshot(client, drive, item)
    meta = after["meta"]
    versions = {v["id"] for v in after["versions"]}
    checks = {"identity": meta["id"] == item and meta["parentReference"]["driveId"] == drive, "name": meta["name"] == plan["name"], "parent": meta["parentReference"]["id"] == plan["destination"]["id"], "content": after["sha256"] == plan["before"]["sha256"], "versionLineage": all(v["id"] in versions for v in plan["before"]["versions"]), "visibleSharing": after["permissions"] == plan["before"]["permissions"]}
    return {"status": "verified" if all(checks.values()) else "applied_review_required", "checks": checks, "sharingAfter": after["permissions"], "coverage": "Compared caller-visible grants and retained version IDs; this does not prove all access or historical byte equivalence."}


def apply(client, store, operation, expected_hash, execute, allow_recycle=False):
    if not execute: raise ValueError("Execution requires --execute, the exact preview hash and authorization")
    plan = store.load(operation, expected_hash)
    if plan.get("kind") != "file-organization-v1" or plan.get("alias") != client.alias or plan.get("action") not in ("move", "rename", "recycle"):
        raise ValueError("Wrong operation/account")
    if plan["action"] == "recycle":
        review = plan.get("deletionReview") or {}
        files = review.get("files", [])
        if len(files) != 1 or files[0].get("item") != plan["item"] or files[0].get("drive") != plan["drive"] or files[0].get("name") != plan["before"]["meta"]["name"] or files[0].get("parent") != plan["before"]["meta"]["parentReference"]["id"]:
            raise ValueError("Make a fresh itemized recycle preview with a reason before requesting isolated deletion consent")
        recycle_reason(files[0].get("reason"))
        if not allow_recycle:
            raise ValueError("Recycle requires separate, explicit consent to the itemized deletion and --allow-recycle; general cleanup approval or --execute alone is insufficient")
    elif allow_recycle:
        raise ValueError("--allow-recycle applies only to a separately approved recycle preview")
    if store.dispatched(operation): raise ValueError("Already dispatched; use organization-status or organization-verify. Never replay.")
    client.require_write()
    if client.identity() != plan["identity"] or snapshot(client, plan["drive"], plan["item"]) != plan["before"]:
        raise ValueError("Account or source changed after preview; no write sent")
    if plan["destination"] and destination(client, plan["drive"], plan["destination"]["id"], plan["name"], plan["item"]) != plan["destination"]:
        raise ValueError("Destination sharing changed after preview; no write sent")
    path = item_path(plan["drive"], plan["item"])
    store.dispatch(operation, {"status": "uncertain_after_dispatch", "hash": plan["hash"], "action": plan["action"], "recycleConsentAcknowledged": allow_recycle})
    result = {"operation": operation, "status": "uncertain_after_dispatch", "replayAllowed": False}
    try:
        headers = {"If-Match": plan["before"]["meta"]["eTag"]}
        if plan["action"] == "recycle":
            client.request("DELETE", path, headers=headers)
        else:
            body = {"name": plan["name"]}
            if plan["action"] == "move": body["parentReference"] = {"id": plan["destination"]["id"]}
            client.request("PATCH", path + "?@microsoft.graph.conflictBehavior=fail", body, headers)
        result["requestAcknowledged"] = True
        result.update(verify(client, plan))
        if plan["action"] == "recycle" and result["status"] == "absent_from_original_parent": result["status"] = "recycle_request_verified"
    except Exception:
        result["detail"] = "The request may have applied. Inspect the saved operation and cloud state; never repeat it automatically."
    store.receipt(operation, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("children", "permissions", "versions", "ownership", "move", "rename", "recycle"):
        p = subs.add_parser(command); p.add_argument("alias"); p.add_argument("item"); p.add_argument("--drive", required=True)
        if command in ("children", "permissions", "versions"):
            p.add_argument("--cursor"); p.add_argument("--limit", type=int, default=100)
        if command in ("move", "rename"): p.add_argument("--name", required=command == "rename")
        if command == "move": p.add_argument("--parent", required=True)
        if command == "recycle": p.add_argument("--reason", required=True)
    for command in ("organization-apply", "organization-status", "organization-verify"):
        p = subs.add_parser(command); p.add_argument("alias"); p.add_argument("--plan", required=True)
        if command == "organization-apply": p.add_argument("--hash", required=True); p.add_argument("--execute", action="store_true"); p.add_argument("--allow-recycle", action="store_true")
    args = parser.parse_args(argv); client = Client(args.alias, "files")
    if args.command in ("children", "permissions", "versions", "ownership"):
        value = metadata(client, args.drive, args.item)
        if args.command == "children": ordinary(value, True)
        result = sharing(client, args.drive, value["id"]) if args.command == "ownership" else page(client, args.drive, args.item, args.command, args.cursor, args.limit)
        if args.command == "permissions": result["visibility"] = "Caller-visible grants only; no share links/secrets. Full effective audience may be unavailable."
    else:
        store = Store(location("files") / ".organization-state", args.alias)
        if args.command == "organization-apply": result = apply(client, store, args.plan, args.hash, args.execute, args.allow_recycle)
        elif args.command == "organization-status": result = store.status(args.plan)
        elif args.command == "organization-verify":
            plan = store.load(args.plan)
            if plan.get("alias") != args.alias or client.identity() != plan["identity"]: raise ValueError("Account mismatch")
            result = verify(client, plan)
        else: result = preview(client, store, args.command, args.drive, args.item, getattr(args, "name", None), getattr(args, "parent", None), getattr(args, "reason", None))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") in ("uncertain_after_dispatch", "applied_review_required", "still_in_parent") else 0


if __name__ == "__main__":
    try: sys.exit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"status": "refused_or_unverified", "detail": str(exc)})); sys.exit(1)
