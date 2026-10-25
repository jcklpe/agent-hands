#!/usr/bin/env python3
"""Compute the default bounded UTC read window."""
import sys
from datetime import datetime, timedelta, timezone


def date_window(days_back, days_ahead):
    back, ahead = int(days_back), int(days_ahead)
    if back < 0 or ahead < 0:
        raise ValueError("Calendar window days must be nonnegative")
    now = datetime.now(timezone.utc)
    print((now - timedelta(days=back)).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    print((now + timedelta(days=ahead)).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    print(now.date().isoformat())
    return 0


def bounds(start, end):
    lower = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if last < lower:
        raise ValueError("--to must not be earlier than --from")
    print(lower.isoformat().replace("+00:00", "Z"))
    print((last + timedelta(days=1)).isoformat().replace("+00:00", "Z"))
    return 0


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["bounds"]:
            raise SystemExit(bounds(*sys.argv[2:]))
        raise SystemExit(date_window(*sys.argv[1:]))
    except (ValueError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
