"""Bind task deletion to a reviewed snapshot and retain private, non-replayable receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def text_id(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or any(c.isspace() or c in "/\\?#" for c in value):
        raise ValueError("An exact nonempty service identifier is required")
    return value


def prepare(alias, task_id, snapshot):
    if not isinstance(snapshot, dict) or not all(isinstance(snapshot.get(k), dict) for k in ("task", "details")):
        raise ValueError("Task and details must be valid service objects")
    task, details = snapshot["task"], snapshot["details"]
    if task.get("id") != task_id or details.get("id") != task_id:
        raise ValueError("Task/details identity mismatch; no deletion is permitted")
    plan = text_id(task.get("planId"))
    for value in (task.get("@odata.etag"), details.get("@odata.etag")):
        if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
            raise ValueError("Task and details ETags are required; reread before deletion")
    if not isinstance(task.get("title"), str) or not task["title"]:
        raise ValueError("Task title is unavailable; no deletion is permitted")
    fingerprint = hashlib.sha256(canonical({"alias": alias, "snapshot": snapshot}).encode()).hexdigest()
    return {"alias": alias, "task_id": task_id, "plan_id": plan, "title": task["title"], "etag": task["@odata.etag"], "fingerprint": fingerprint}


def private_directory(path):
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError("Deletion receipts require an owner-only real directory")


class Receipts:
    def __init__(self, root, alias, task_id):
        self.root = Path(root)
        private_directory(self.root)
        self.root /= alias
        private_directory(self.root)
        self.alias, self.task_id = alias, task_id
        key = hashlib.sha256(task_id.encode()).hexdigest()
        self.pending = self.root / (key + ".dispatched.json")
        self.confirmed = self.root / (key + ".confirmed.json")

    def read(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            st = os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise ValueError("Unsafe deletion receipt permissions")
            value = json.load(stream)
        if value.get("alias") != self.alias or value.get("task_id") != self.task_id:
            raise ValueError("Deletion receipt identity mismatch")
        text_id(value.get("plan_id"))
        return value

    def write(self, path, value):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def claim(self, prepared, expected):
        if not re.fullmatch(r"[0-9a-f]{64}", expected or "") or prepared["fingerprint"] != expected:
            raise ValueError("Deletion needs --expected-sha256 from the current preview; the task or details changed")
        try:
            self.write(self.pending, {**prepared, "state": "dispatched"})
        except FileExistsError as exc:
            raise ValueError("A deletion was already dispatched for this task; use --verify, never replay it") from exc
        return str(self.pending)

    def confirm(self, listing):
        receipt = self.read(self.pending)
        if not isinstance(listing, dict):
            raise ValueError("Deletion needs a valid complete plan-task listing")
        tasks = listing.get("value")
        if listing.get("error") is not None or listing.get("@odata.nextLink") or not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
            raise ValueError("Deletion needs a successful complete plan-task listing")
        ids = [text_id(t.get("id")) for t in tasks]
        if len(set(ids)) != len(ids) or any(t.get("planId") != receipt["plan_id"] for t in tasks):
            raise ValueError("Invalid or wrong-plan deletion readback")
        if self.task_id in ids:
            raise ValueError("Task remains present; deletion is unverified. Inspect the receipt before any recovery")
        value = {**receipt, "state": "confirmed-absent"}
        try:
            self.write(self.confirmed, value)
        except FileExistsError:
            if self.read(self.confirmed) != value:
                raise ValueError("Conflicting deletion receipt")
        return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "claim", "receipt", "confirm"))
    parser.add_argument("--alias", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--root")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.alias):
        raise ValueError("Invalid account alias")
    text_id(args.task)
    if args.command in ("prepare", "claim"):
        value = prepare(args.alias, args.task, json.load(sys.stdin))
        if args.command == "prepare":
            print(canonical(value))
            return
    if not args.root:
        raise ValueError("Private deletion receipt directory is required")
    store = Receipts(args.root, args.alias, args.task)
    if args.command == "claim":
        print(store.claim(value, args.expected_sha256))
    elif args.command == "receipt":
        print(canonical(store.read(store.pending)))
    else:
        print(canonical(store.confirm(json.load(sys.stdin))))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
