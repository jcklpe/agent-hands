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


if __name__ == "__main__":
    window(*sys.argv[1:])
