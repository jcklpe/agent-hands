"""Compute the bounded Microsoft calendar read window in UTC days."""
from datetime import datetime, timedelta, timezone
import sys


def window(back, ahead):
    back, ahead = int(back), int(ahead)
    if back < 0 or ahead < 0:
        raise ValueError("Calendar window days must be nonnegative")
    now = datetime.now(timezone.utc)
    for days in (-back, ahead + 1):
        print((now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z"))


def instant_bounds(start, end):
    lower = datetime.fromisoformat(start.replace("Z", "+00:00"))
    upper = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if lower.tzinfo is None or upper.tzinfo is None or lower >= upper:
        raise ValueError("Supply increasing ISO instants with offsets; --to is exclusive")
    print(lower.isoformat())
    print(upper.isoformat())


if __name__ == "__main__":
    if sys.argv[1:2] == ["instant-bounds"]:
        instant_bounds(*sys.argv[2:])
    else:
        window(*sys.argv[1:])
