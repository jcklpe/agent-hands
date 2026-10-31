#!/usr/bin/env python3
"""Read/export Canvas courses and preview or execute supported changes with private history."""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup-canvas" / "scripts"))
import canvas_auth as auth


def canvas_id(value):
    try:
        return auth.id_string(value)
    except auth.CanvasError:
        raise argparse.ArgumentTypeError("Expected a numeric Canvas ID") from None


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name, description in (("courses", "list this user's courses"), ("verify", "report selected courses' access, navigation and permissions"), ("export", "publish a deterministic course export with coverage"), ("download-file", "stream one explicitly selected course file to disk"), ("history", "query monthly private operation records without Canvas access"), ("history-prune", "preview or execute removal of whole history months"), ("history-resolve", "record the inspected outcome of an uncertain write")):
        command = commands.add_parser(name, help=description)
        command.add_argument("alias")
        command.add_argument("--history-dir", type=Path)
        command.add_argument("--json", action="store_true")
        if name in {"export", "verify"}:
            command.add_argument("--course", type=canvas_id, action="append")
        elif name in {"download-file", "history"}:
            command.add_argument("--course", type=canvas_id, required=name == "download-file")
        if name == "courses":
            command.add_argument("--all-states", action="store_true")
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--allow-partial", action="store_true")
            command.add_argument("--include-html", action="store_true")
        if name == "download-file":
            command.add_argument("--file", type=canvas_id, required=True)
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--max-bytes", type=int)
            command.add_argument("--force", action="store_true")
        if name == "history":
            command.add_argument("--kind", choices=["read", "export", "write", "resolution"])
            command.add_argument("--outcome")
            command.add_argument("--since")
            command.add_argument("--until")
        if name == "history-prune":
            command.add_argument("--before", required=True)
            command.add_argument("--execute", action="store_true")
        if name == "history-resolve":
            command.add_argument("record_id")
            outcome = command.add_mutually_exclusive_group(required=True)
            outcome.add_argument("--landed", action="store_true")
            outcome.add_argument("--not-landed", action="store_true")
    from canvas_write import add_commands
    add_commands(commands,canvas_id)
    from canvas_smoke import add_commands as smoke_commands
    smoke_commands(commands, canvas_id)
    return root


def emit(value, as_json=False):
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    elif isinstance(value, list):
        for row in value:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: " + (json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)))
    else:
        print(value)


def log_read(history, **fields):
    try:
        history.record(**fields)
    except (OSError, ValueError, auth.CanvasError):
        print("WARNING: Canvas operation history could not be recorded; the read result is still available.", file=sys.stderr)


def main(argv=None, transport=None, downloader=None, now=None, upload_sender=None):
    args = parser().parse_args(argv)
    acct, history = None, None
    try:
        from canvas_history import History
        auth.load_env()
        acct = auth.account(args.alias)
        history = History(args.history_dir, now=now)
        if args.command == "history":
            emit(list(history.rows(args.since, args.until, acct.alias, args.course, args.kind, args.outcome)), args.json)
            return 0
        if args.command == "history-prune":
            emit(history.prune(acct.alias, args.before, args.execute), args.json)
            return 0
        if args.command == "history-resolve":
            history.resolve(acct.alias, args.record_id, args.landed)
            emit({"resolved": args.record_id, "outcome": "landed" if args.landed else "not_landed"}, args.json)
            return 0
        auth.check_runtime()
        auth.check_env_permissions()
        auth.check_expiry(acct, (now or dt.datetime.now(dt.timezone.utc)).date())
        client = auth.Client(acct, transport=transport)
        from canvas_read import Reader, numeric
        from canvas_export import export, download
        reader = Reader(client, include_html=getattr(args, "include_html", False))
        reader.identity()
        from canvas_tokens import maintain
        renewed = maintain(client, now)
        if renewed:
            acct = client.account
            print("Canvas credential renewed and saved; the previous credential retains its original expiry.", file=sys.stderr)
        from canvas_write import COMMANDS,run_write
        if args.command in {'smoke-session', 'cleanup-smoke', 'verify-smoke-cleanup', 'verify-smoke-assignment', 'verify-smoke-file', 'verify-smoke-item-title', 'inspect-smoke-creation'}:
            from canvas_smoke import prepare, cleanup, verify_cleanup, verify_assignment, verify_file, verify_item_title, inspect_creation
            if args.command == 'smoke-session': value, code = prepare(reader, args, history)
            elif args.command == 'cleanup-smoke': value, code = cleanup(reader, args, history, downloader)
            elif args.command == 'verify-smoke-cleanup': value, code = verify_cleanup(reader, args, history, downloader)
            elif args.command == 'verify-smoke-assignment': value, code = verify_assignment(reader, args, history)
            elif args.command == 'verify-smoke-file': value, code = verify_file(reader, args, history, downloader)
            elif args.command == 'verify-smoke-item-title': value, code = verify_item_title(reader, args, history, downloader)
            else: value, code = inspect_creation(reader, args, history, downloader)
            emit(value, args.json)
            return code
        if args.command in COMMANDS:
            value,code=run_write(reader,args,history,now,upload_sender,downloader)
            emit(value,args.json)
            if value.get("mode")=="preview" and not args.json:
                print("No writes sent. To apply this reviewed plan, repeat with --execute --expect "+value["preview_hash"])
            return code
        ids = []
        if args.command in {"export", "verify"}:
            ids = sorted(set(args.course or acct.courses), key=numeric)
            if not ids:
                raise auth.CanvasError("config_invalid", "Select at least one course in this account's configuration")
            if set(ids) - set(acct.courses):
                raise auth.CanvasError("config_invalid", "Requested course is not in this account's explicit export selection")
        code, kind, outcome = 0, "read", "complete"
        if args.command == "courses":
            rows, cov = reader.courses(args.all_states)
            value = {"courses": rows, "coverage": cov}
            code = 0 if cov["status"] == "complete" else 1
        elif args.command == "verify":
            value = [reader.verify(cid) for cid in ids]
            code = int(any(c["status"] in {"denied", "failed", "partial"} for r in value for c in r["coverage"].values()))
        elif args.command == "download-file":
            ids = [args.course]
            meta = reader.object(f"/api/v1/courses/{args.course}/files/{args.file}")
            if auth.id_string(meta.get("id")) != args.file:
                raise auth.CanvasError("malformed", "Canvas returned the wrong file")
            value = (downloader or download)(client, meta, args.output, max_bytes=args.max_bytes, force=args.force)
        else:
            kind = "export"
            value = export(reader, ids, args.output, args.allow_partial, now=now, **({"downloader": downloader} if downloader else {}))
            code = 0 if value["published"] else 1
            outcome = "published" if value["published"] else "not_published"
        if code and kind != "export":
            outcome = "incomplete"
        fields = {"account": acct.alias, "command": args.command, "kind": kind, "course_ids": ids, "outcome": outcome}
        if args.command == "export":
            fields.update(output=str(args.output.absolute()), coverage=value["coverage"])
        elif args.command == "courses":
            fields.update(counts={"courses": len(value["courses"])}, coverage=value["coverage"])
        elif args.command == "verify":
            fields["coverage"] = [{"course_id": row["course_id"], "coverage": row["coverage"]} for row in value]
        elif args.command == "download-file":
            fields.update(target_ids=[args.file], counts={"bytes": value["bytes"]})
        log_read(history, **fields)
        emit(value, args.json)
        return code
    except (auth.CanvasError, OSError, ValueError) as error:
        if acct and history and not args.command.startswith("history"):
            log_read(history, account=acct.alias, command=args.command, kind="write" if hasattr(args,"expect") else "export" if args.command == "export" else "read", course_ids=[], outcome="refused" if hasattr(args,"expect") else "failed")
        if isinstance(error, auth.CanvasError):
            return auth.fail(error)
        print("ERROR: Canvas operation failed while processing local files or malformed data.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
