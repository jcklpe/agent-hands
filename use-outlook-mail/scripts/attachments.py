"""Validate attachment destinations and stage all downloads before publishing files."""
import base64
import json
from pathlib import Path
import runpy
import sys

FILE_TYPE = "#microsoft.graph.fileAttachment"
publish = runpy.run_path(str(Path(__file__).resolve().parents[2] / "setup-microsoft-services/scripts/publish.py"))["publish"]


def destination(directory, name, force):
    if not isinstance(name, str) or not name or name.startswith("..") or name in {".", ".."} or any(character in "/\\" or ord(character) < 32 or ord(character) == 127 for character in name):
        raise ValueError("Unsafe attachment file name")
    target = directory / name
    if target.is_symlink() or (target.exists() and (not force or not target.is_file())):
        raise ValueError("Refusing an existing or unsafe attachment destination")
    return target


def plan(data, directory, force):
    if not isinstance(data.get("value"), list) or data.get("@odata.nextLink"):
        raise ValueError("Incomplete attachment list; refusing a partial save")
    if not directory.is_dir():
        raise ValueError("Save directory does not exist")
    names = set()
    selected = []
    for item in data["value"]:
        if item.get("@odata.type") != FILE_TYPE or item.get("isInline"):
            continue
        name = item.get("name")
        destination(directory, name, force)
        if name.casefold() in names:
            raise ValueError("Attachment file names collide")
        names.add(name.casefold())
        if not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("Attachment has no ID")
        selected.append({"id": item["id"], "name": name})
    return selected


def save(selected, staged, directory, force):
    ready = []
    for index, expected in enumerate(selected):
        item = json.loads((staged / f"{index}.json").read_text())
        if item.get("id") != expected["id"] or item.get("name") != expected["name"] or item.get("@odata.type") != FILE_TYPE or item.get("isInline"):
            raise ValueError("Attachment identity changed after listing; refusing the save")
        target = destination(directory, expected["name"], force)
        raw = base64.b64decode(item["contentBytes"], validate=True)
        content = staged / f"{index}.content"
        content.write_bytes(raw)
        ready.append((content, target))
    # Publication is atomic per file, not a transaction across multiple destinations.
    for content, target in ready:
        publish(content, target, "replace" if force else "create")
        print(f"Saved: {target} ({content.stat().st_size} bytes)")


if __name__ == "__main__":
    try:
        mode, source, *arguments = sys.argv[1:]
        data = json.loads(Path(source).read_text())
        if mode == "plan":
            directory, force = arguments
            print(json.dumps(plan(data, Path(directory), force == "1")))
        elif mode == "save":
            staged, directory, force = arguments
            save(data, Path(staged), Path(directory), force == "1")
        else:
            raise ValueError("Unknown attachment operation")
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
