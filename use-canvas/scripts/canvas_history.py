"""Private monthly operation records, bounded queries and explicit retention."""
import contextlib
import datetime as dt
import gzip
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from canvas_auth import CanvasError, setting

UTC = dt.timezone.utc
MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
MONTH_FILE = re.compile(r"^(\d{4}-(?:0[1-9]|1[0-2]))\.jsonl(\.gz)?$")
FIELDS = {"command", "account", "kind", "course_ids", "families", "counts", "coverage", "outcome", "output", "target_ids", "preview_hash", "steps", "resolves"}


def json_line(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def safe_path(path):
    path = Path(path).expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CanvasError("history_invalid", "History paths must not contain symlinks")
    return path


class History:
    def __init__(self, directory=None, now=None, plain_months=None):
        self.path = safe_path(directory or setting("CANVAS_HISTORY_DIR") or Path(__file__).resolve().parents[1] / "canvas.history")
        self.now = now or dt.datetime.now(UTC)
        self.now = self.now.astimezone(UTC)
        try:
            self.plain = int(plain_months if plain_months is not None else setting("CANVAS_HISTORY_PLAIN_MONTHS") or 3)
            if not 1 <= self.plain <= 120:
                raise ValueError
        except ValueError:
            raise CanvasError("config_invalid", "CANVAS_HISTORY_PLAIN_MONTHS must be between 1 and 120") from None

    @contextlib.contextmanager
    def locked(self):
        safe_path(self.path)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt" and self.path.stat().st_mode & 0o077:
            raise CanvasError("history_invalid", "History directory must have owner-only permissions")
        lock = self.path / ".lock"
        fd = None
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            yield
        except FileExistsError:
            raise CanvasError("history_busy", "History is locked; inspect an interrupted operation before removing its lock") from None
        finally:
            if fd is not None:
                os.close(fd)
                lock.unlink()

    def files(self, since=None, until=None):
        if not self.path.exists():
            return []
        result, seen = [], set()
        for path in sorted(self.path.iterdir()):
            match = MONTH_FILE.fullmatch(path.name)
            if not match:
                continue
            month = match[1]
            if since and month < since[:7] or until and month > until[:7]:
                continue
            safe_path(path)
            if month in seen:
                raise CanvasError("history_invalid", "A history month has both plain and compressed files")
            seen.add(month)
            result.append(path)
        return result

    def rows(self, since=None, until=None, account=None, course=None, kind=None, outcome=None):
        for date in (since, until):
            if date:
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                        raise ValueError
                    dt.date.fromisoformat(date)
                except ValueError:
                    raise CanvasError("config_invalid", "History dates must use YYYY-MM-DD") from None
        if since and until and since > until:
            raise CanvasError("config_invalid", "History start date is after its end date")
        for path in self.files(since, until):
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line)
                    if since and row["time"][:10] < since or until and row["time"][:10] > until:
                        continue
                    if account and row.get("account") != account or course and course not in row.get("course_ids", []):
                        continue
                    if kind and row.get("kind") != kind or outcome and row.get("outcome") != outcome:
                        continue
                    yield row

    def compress(self):
        current = self.now.year * 12 + self.now.month - 1
        for path in self.files():
            year, month = map(int, path.name[:7].split("-"))
            if path.suffix != ".jsonl" or current - (year * 12 + month - 1) < self.plain:
                continue
            target = path.with_suffix(".jsonl.gz")
            fd, temporary = tempfile.mkstemp(prefix=".compress-", dir=self.path)
            try:
                with os.fdopen(fd, "wb") as output:
                    # Fix both timestamp and filename so the same month always has the same compressed bytes.
                    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as zipped, path.open("rb") as source:
                        while block := source.read(1024 * 1024):
                            zipped.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                os.link(temporary, target)
            finally:
                os.unlink(temporary)
            path.unlink()

    def _append(self, row):
        path = safe_path(self.path / (self.now.strftime("%Y-%m") + ".jsonl"))
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "ab") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(json_line(row))
            stream.flush()
            os.fsync(stream.fileno())

    def record(self, **fields):
        if set(fields) - FIELDS:
            raise CanvasError("history_invalid", "Unsupported history record fields")
        row = {"schema_version": 1, "record_id": uuid.uuid4().hex, "time": self.now.isoformat().replace("+00:00", "Z"), **fields}
        with self.locked():
            self.compress()
            self._append(row)
        return row

    def prune(self, account, before, execute=False):
        if not MONTH.fullmatch(before):
            raise CanvasError("config_invalid", "History cutoff must use YYYY-MM")
        with self.locked():
            rows = list(self.rows())
            resolved = {r.get("resolves") for r in rows if r.get("command") == "history-resolve"}
            uncertain = {r["record_id"] for r in rows if r.get("kind") == "write" and r.get("outcome") == "uncertain"}
            chosen = []
            for path in self.files():
                if path.name[:7] >= before:
                    continue
                month_rows = [r for r in rows if r["time"][:7] == path.name[:7]]
                if any(r.get("account") != account for r in month_rows):
                    raise CanvasError("history_invalid", "A month includes another account; refusing to prune shared history")
                if any(r["record_id"] in uncertain - resolved for r in month_rows):
                    raise CanvasError("history_uncertain", "Resolve uncertain writes before pruning their month")
                # Keep resolutions for uncertain writes retained in other months.
                if any(r.get("resolves") in uncertain and any(x["record_id"] == r.get("resolves") and x["time"][:7] >= before for x in rows) for r in month_rows):
                    raise CanvasError("history_uncertain", "This month resolves a retained uncertain write")
                chosen.append(path)
            if execute:
                for path in chosen:
                    path.unlink()
            return {"mode": "executed" if execute else "preview", "months": [p.name[:7] for p in chosen]}

    def resolve(self, account, record_id, landed):
        with self.locked():
            rows = list(self.rows())
            found = next((r for r in rows if r.get("record_id") == record_id and r.get("account") == account), None)
            if not found or found.get("kind") != "write" or found.get("outcome") != "uncertain":
                raise CanvasError("history_invalid", "No matching uncertain write was found")
            if any(r.get("resolves") == record_id for r in rows):
                raise CanvasError("history_invalid", "This write already has a resolution")
            self.compress()
            self._append({"schema_version": 1, "record_id": uuid.uuid4().hex, "time": self.now.isoformat().replace("+00:00", "Z"), "account": account, "kind": "resolution", "command": "history-resolve", "resolves": record_id, "outcome": "landed" if landed else "not_landed", "course_ids": found.get("course_ids", [])})
