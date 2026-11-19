"""Private crash journal and per-target process lock for future Unix adapters."""
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from workday_core import Refusal, digest, require


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                'PRIVATE_STORAGE_REQUIRED', 'Use an owned, non-symlink directory with mode 0700 outside version control.')
        self.path = None

    def _open(self, path, flags):
        fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if not (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1):
            os.close(fd)
            raise Refusal('PRIVATE_STORAGE_REQUIRED', 'Use owned, private regular journal files with mode 0600.')
        return fd

    @contextmanager
    def guard(self, target):
        import fcntl
        name = digest(target)
        fd = self._open(self.directory / (name + '.lock'), os.O_CREAT | os.O_RDWR)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refusal('TARGET_BUSY', 'Wait for the current target/week operation to finish.')
            self.path = self.directory / (name + '.json')
            yield
        finally:
            self.path = None
            os.close(fd)

    def pending(self):
        require(self.path is not None)
        return self.path.exists() or self.path.is_symlink()

    def intent(self, record):
        require(self.path is not None and not self.pending(), 'RECONCILE_REQUIRED', 'Reconcile the outstanding intent before saving again.')
        fd = self._open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w') as f:
            json.dump(record, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        self._sync()

    def _sync(self):
        fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def clear(self):
        require(self.path is not None)
        self.path.unlink()
        self._sync()
