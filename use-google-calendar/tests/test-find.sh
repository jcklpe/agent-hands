#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
source "$SKILL/../setup-google-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
OUT="$WORK/find.md"
EVENTS="$WORK/events.json"
jq '.items |= map(. + {_calendar_id: "primary", _calendar_summary: "Test Calendar"})' \
    "$SKILL/tests/fixtures/events.json" > "$EVENTS"

_calendar_find_human < "$EVENTS" > "$OUT"

assert_contains() {
    if ! grep -F -- "$1" "$OUT" >/dev/null 2>&1; then
        printf 'Expected output to contain:\n%s\n\nFull output:\n' "$1" >&2
        cat "$OUT" >&2
        exit 1
    fi
}

assert_contains "- One Day All Day | calendar: Test Calendar | calendar_id: primary | event_id: one-day-all-day | start: 2026-06-23 | end: 2026-06-24 | https://calendar.test/one-day"
assert_contains "- Normal Timed Event | calendar: Test Calendar | calendar_id: primary | event_id: normal-timed | start: 2026-06-25T10:00:00-05:00 | end: 2026-06-25T11:00:00-05:00 | location: Library Room | https://calendar.test/normal"

printf 'calendar find formatter fixture passed\n'
