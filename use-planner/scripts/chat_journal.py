"""Durably replace a private Task chat receipt before transport may run."""
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def write_journal(destination, state, operation, digest, message):
    target = Path(destination)
    if state not in ('pending', 'verified') or operation not in ('comment', 'edit-comment') or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid Task chat receipt')
    for parent in (target.parent, *target.parent.parents):
        if parent.is_symlink():
            raise ValueError('Task chat state cannot use symlinks')
    parent_stat = target.parent.stat()
    if parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) & 0o077:
        raise ValueError('Task chat state needs an owner-only directory')
    if target.is_symlink():
        raise ValueError('Task chat receipt cannot be a symlink')
    if target.exists():
        st = target.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
            raise ValueError('Task chat receipt needs an owner-only file')
    record = dict(route='task-chat', state=state, operation=operation, hash=digest, message_id=message)
    descriptor, temporary = tempfile.mkstemp(prefix='.chat-receipt-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w') as output:
            output.write(json.dumps(record, sort_keys=True) + '\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 6:
            raise ValueError('Expected destination, state, operation, hash and message ID')
        write_journal(*sys.argv[1:])
    except (ValueError, OSError):
        sys.exit('ERROR: Task chat recovery could not be durably recorded; no subsequent write is permitted')
