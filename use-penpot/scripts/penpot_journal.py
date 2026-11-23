"""Private journal for use-penpot's board replacements: preimages, stages and a per-file lock.

Records live under `$AGENT_HANDS_STATE_DIR/penpot/replacements/<file-id>/`, defaulting to `~/.agent-hands`. The base must be absolute and cannot traverse a symlink or sit inside a Git checkout. Directories are owner-only (0700) and records owner-only (0600), written atomically and flushed. Records hold design content from the file, so they are private data; nothing here deletes them.
"""
import fcntl
import json
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATE_ENV = "AGENT_HANDS_STATE_DIR"
# A dispatched write whose outcome is not known yet. These block another replacement of the same board until reconciled or accepted.
BLOCKING = {"dispatched", "uncertain", "mismatch"}
# Interrupted before anything was sent; reconcile records them as aborted.
BEFORE_WRITE = {"intent", "version_locked"}
RESOLVED = {"aborted", "refused", "verified", "not_applied", "accepted", "restored"}


class JournalError(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def stamp(moment=None):
    return (moment or now()).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_stamp(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def root():
    base = Path(os.environ.get(STATE_ENV) or str(Path.home() / ".agent-hands"))
    if not base.is_absolute():
        raise JournalError(f"{STATE_ENV} must be an absolute path")
    path = base / "penpot" / "replacements"
    for part in (path, *path.parents):
        if part.is_symlink():
            raise JournalError("The private journal path cannot traverse a symlink")
        if (part / ".git").exists():
            raise JournalError("The private journal cannot live inside a Git checkout")
    return path


def ensure_private(path):
    missing = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        probe = probe.parent
    for part in reversed(missing):
        part.mkdir(mode=0o700)
    info = path.stat()
    if not path.is_dir() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise JournalError(f"{path} must be an owner-only directory (mode 0700)")


def write_json(path, value):
    pending = path.with_name(".write-" + uuid.uuid4().hex)
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(value, out, indent=1, ensure_ascii=False)
        out.flush()
        os.fsync(out.fileno())
    os.replace(pending, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class Record:
    def __init__(self, path, data):
        self.path, self.data = path, data

    @property
    def stage(self):
        return self.data["stage"]

    def targets(self):
        return {r["target_id"] for r in self.data.get("replacements", [])}

    def advance(self, stage, **fields):
        self.data.update(fields)
        self.data["stage"] = stage
        self.data.setdefault("history", []).append({"stage": stage, "at": stamp()} | ({"note": fields["note"]} if "note" in fields else {}))
        write_json(self.path, self.data)
        return self


class Journal:
    """One journal directory per Penpot file, serialized by an exclusive lock that the OS releases if the process dies."""

    def __init__(self, file_id):
        self.dir = root() / file_id
        self.lock = None

    def __enter__(self):
        ensure_private(self.dir.parent.parent)
        ensure_private(self.dir.parent)
        ensure_private(self.dir)
        fd = os.open(self.dir / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise JournalError("Another replacement or recovery for this file is running; wait for it to finish")
        self.lock = fd
        return self

    def __exit__(self, *exc):
        if self.lock is not None:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            os.close(self.lock)
            self.lock = None

    def records(self):
        found = []
        for path in sorted(self.dir.glob("*.json")):
            found.append(Record(path, json.loads(path.read_text(encoding="utf-8"))))
        return found

    def blocking(self, targets):
        return [r for r in self.records() if r.stage in BLOCKING and r.targets() & set(targets)]

    def create(self, content):
        moment = now()
        path = self.dir / f"{moment.strftime('%Y%m%dT%H%M%S%fZ')}-{content['plan_sha256'][:12]}.json"
        data = dict(content, created_at=stamp(moment), stage="intent", history=[{"stage": "intent", "at": stamp(moment)}])
        write_json(path, data)
        return Record(path, data)


def load(path):
    """Open a record by path for recovery, holding its file's lock."""
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    journal = Journal(data["file_id"])
    if path.parent != journal.dir.resolve():
        raise JournalError("The record is not in this file's private journal directory")
    return journal, path, data
