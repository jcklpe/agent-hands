#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PYTHON="${M365_PYTHON:-python3}"
EVENT_OUT="$WORK/event"; ALL_DAY_OUT="$WORK/allday"; CONTACT_OUT="$WORK/contact"
"$PYTHON" "$SKILL/scripts/write.py" event \
    --title "Coffee" \
    --start "2026-08-20T10:00" \
    --tz "Central Standard Time" \
    --location "Example Office" \
    --attendee "professor@example.edu" > "$EVENT_OUT"

"$PYTHON" "$SKILL/scripts/write.py" event \
    --title "Orientation" \
    --start "2026-08-18" > "$ALL_DAY_OUT"
jq -e '.subject == "Coffee" and .start.dateTime == "2026-08-20T10:00:00" and .end.dateTime == "2026-08-20T11:00:00" and .attendees[0].emailAddress.address == "professor@example.edu"' "$EVENT_OUT" >/dev/null
jq -e '.isAllDay == true and .start.dateTime == "2026-08-18T00:00:00" and .end.dateTime == "2026-08-19T00:00:00"' "$ALL_DAY_OUT" >/dev/null
