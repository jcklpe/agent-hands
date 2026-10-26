"""Append validated JSON records to a private Gmail audit file."""
import json
import os
from pathlib import Path
import sys


def append(path, incoming):
    data = "".join(json.dumps(json.loads(line), separators=(",", ":")) + "\n" for line in incoming if line.strip())
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as output:
        output.write(data)


if __name__ == "__main__":
    try:
        append(sys.argv[1], sys.stdin)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
