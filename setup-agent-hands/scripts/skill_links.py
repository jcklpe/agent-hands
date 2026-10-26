"""Shared optional skill-link installer; service entrypoints own their selections."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

CLIENT_ROOTS = {"codex": ".agents/skills", "claude": ".claude/skills"}


def snapshot(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    target = os.readlink(path) if stat.S_ISLNK(info.st_mode) else None
    return (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, target)


def absolute(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Use an absolute path: " + str(path))
    return Path(os.path.normpath(str(path)))


def link_target(path, raw):
    return Path(os.path.normpath(str(path.parent / raw)))


def check_directory(path):
    # Do not redirect a selected discovery root through an existing directory link.
    if path.is_symlink():
        raise ValueError("Discovery directory is a symlink; select its verified real path with --skills-dir: " + str(path))
    for parent in (path, *path.parents):
        if parent.exists():
            if not parent.is_dir():
                raise ValueError("Discovery directory has a non-directory ancestor: " + str(parent))
            return


def build_plan(root, owner, selected, clients, override, previous):
    entries = []
    roots = []
    for client in clients:
        directory = override or Path.home() / CLIENT_ROOTS[client]
        check_directory(directory)
        if directory in roots:
            continue
        roots.append(directory)
        for skill in dict.fromkeys([owner, *selected]):
            source = root / skill
            if source.is_symlink() or not (source / "SKILL.md").is_file():
                raise ValueError("Missing ordinary source skill directory: " + str(source))
            destination = directory / skill
            state = snapshot(destination)
            entry = dict(client=client, skill=skill, source=str(source), destination=str(destination), action="create")
            if state is not None:
                raw = state[-1]
                if raw is not None and destination.resolve() == source:
                    entry["action"] = "unchanged"
                elif raw is not None and previous and link_target(destination, raw) == previous / skill:
                    entry.update(action="repair", previous_target=raw)
                else:
                    entry["action"] = "conflict"
                    entry["reason"] = "Existing file, directory or unrelated link is preserved."
            entries.append((entry, state))
    return entries


def apply_plan(entries, report):
    # Check the complete selection again before the first filesystem change.
    for entry, expected in entries:
        target = Path(entry["destination"])
        check_directory(target.parent)
        if snapshot(target) != expected:
            raise RuntimeError("Destination changed after preview: " + str(target))
    backups = {}
    try:
        for entry, expected in entries:
            if entry["action"] == "unchanged":
                continue
            target = Path(entry["destination"])
            check_directory(target.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            if snapshot(target) != expected:
                raise RuntimeError("Destination changed during installation: " + str(target))
            if entry["action"] == "repair":
                directory = backups.get(target.parent)
                if directory is None:
                    directory = Path(tempfile.mkdtemp(prefix=".agent-hands-link-recovery-", dir=target.parent.parent))
                    backups[target.parent] = directory
                    report["recovery"].append(str(directory / "recovery.json"))
                saved = directory / target.name
                # Unique recovery directory: never overwrite another saved link.
                os.rename(target, saved)
                recovery = dict(destination=str(target), saved=str(saved), previous_target=entry["previous_target"], replacement=entry["source"])
                report["saved_links"].append(recovery)
                if snapshot(saved) != expected:
                    raise RuntimeError("Destination changed during repair; preserved in " + str(saved))
            # Exclusive creation refuses even a racing directory; it cannot create a nested link.
            os.symlink(entry["source"], target, target_is_directory=True)
            report["completed"].append(str(target))
    finally:
        for directory in backups.values():
            records = [item for item in report["saved_links"] if Path(item["saved"]).parent == directory]
            (directory / "recovery.json").write_text(json.dumps(records, indent=2) + "\n")


def main(entrypoint, capabilities=(), dependencies=None, argv=None):
    owner_dir = Path(entrypoint).resolve().parents[1]
    root = owner_dir.parent
    owner = owner_dir.name
    parser = argparse.ArgumentParser(description="Preview optional global links for " + owner + "; no provider configuration is read.")
    parser.add_argument("--client", choices=tuple(CLIENT_ROOTS), action="append", required=True, help="Local agent client; repeat for both")
    if capabilities:
        parser.add_argument("--skill", choices=tuple(capabilities), action="append", help="Selected capability; repeat as needed; required when this service has multiple capabilities")
    parser.add_argument("--skills-dir", help="Absolute verified discovery directory; one client only")
    parser.add_argument("--repair-from", help="Absolute previous checkout; only links to its exact selected skill paths may be repaired, with recovery copies")
    parser.add_argument("--execute", action="store_true", help="Apply the shown link selection (default: preview only)")
    args = parser.parse_args(argv)
    clients = list(dict.fromkeys(args.client))
    if args.skills_dir and len(clients) != 1:
        parser.error("--skills-dir requires exactly one client")
    requested = getattr(args, "skill", None)
    if len(capabilities) > 1 and not requested:
        parser.error("Select at least one --skill; no all-service default is provided")
    selected = list(dict.fromkeys(requested or capabilities))
    for skill in list(selected):
        selected.extend((dependencies or {}).get(skill, ()))
    report = dict(mode="execute" if args.execute else "preview", links=[], completed=[], recovery=[], saved_links=[])
    try:
        override = absolute(args.skills_dir) if args.skills_dir else None
        previous = absolute(args.repair_from) if args.repair_from else None
        entries = build_plan(root, owner, selected, clients, override, previous)
        report["links"] = [entry for entry, _ in entries]
        if any(entry["action"] == "conflict" for entry, _ in entries):
            raise ValueError("Conflicts block the complete selection; no links were changed.")
        if args.execute:
            apply_plan(entries, report)
        report["status"] = "complete" if args.execute else "preview"
        code = 0
    except (OSError, ValueError, RuntimeError) as error:
        report.update(status="stopped", error=str(error))
        code = 1
    print(json.dumps(report, indent=2))
    return code
