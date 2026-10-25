"""Publish a completed private export/download without truncating an existing destination."""
import os
from pathlib import Path
import shutil
import sys
import tempfile


def publish(source, destination, mode):
    target = Path(destination)
    if mode not in {"create", "replace"}:
        raise ValueError("Unknown publication mode")
    if target.is_symlink():
        raise ValueError("Refusing to replace a symlink")
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".microsoft-output-", dir=target.parent)
        with os.fdopen(descriptor, "wb") as output, open(source, "rb") as incoming:
            shutil.copyfileobj(incoming, output)
        if mode == "replace":
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("Expected SOURCE DESTINATION create|replace")
        publish(*sys.argv[1:])
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
