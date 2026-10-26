#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PYTHON="${M365_PYTHON:-python3}"
CALENDAR_OUT="$WORK/render.md"
assert_contains() {
    file="$1"
    text="$2"
    if ! grep -F -- "$text" "$file" >/dev/null 2>&1; then
        printf 'Expected %s to contain:\n%s\n\nFull output:\n' "$file" "$text" >&2
        cat "$file" >&2
        exit 1
    fi
}

assert_not_contains() {
    file="$1"
    text="$2"
    if grep -F -- "$text" "$file" >/dev/null 2>&1; then
        printf 'Expected %s not to contain:\n%s\n\nFull output:\n' "$file" "$text" >&2
        cat "$file" >&2
        exit 1
    fi
}

"$PYTHON" "$SKILL/scripts/render.py" calendar \
    --alias fixture \
    --email student@my.example.edu \
    --refreshed "2026-07-15 18:00:00 UTC" \
    --start "2026-07-01T00:00:00Z" \
    --end "2026-09-01T00:00:00Z" \
    --timezone "Central Standard Time" \
    --description-limit 8000 \
    --input "$SKILL/tests/fixtures/formatting.json" > "$CALENDAR_OUT"
assert_contains "$CALENDAR_OUT" "# Microsoft 365 Calendar - fixture"
assert_contains "$CALENDAR_OUT" "### 2026-08-18T09:30:00.0000000 - Graduate orientation"
assert_contains "$CALENDAR_OUT" "Event ID: \`event-1\`"
assert_contains "$CALENDAR_OUT" "Location: Example Room"
printf "calendar formatting checks passed\n"
