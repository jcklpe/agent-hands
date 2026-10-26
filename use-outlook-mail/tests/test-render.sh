#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PYTHON="${M365_PYTHON:-python3}"
MAIL_OUT="$WORK/render.md"
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

"$PYTHON" "$SKILL/scripts/render.py" mail \
    --alias fixture \
    --email student@my.example.edu \
    --refreshed "2026-07-15 18:00:00 UTC" \
    --days 30 \
    --max-results 150 \
    --body-limit 8000 \
    --input "$SKILL/tests/fixtures/formatting.json" > "$MAIL_OUT"
assert_contains "$MAIL_OUT" "# Microsoft 365 Mail - fixture"
assert_contains "$MAIL_OUT" "### 2026-07-15T14:30:00Z - Orientation details"
assert_contains "$MAIL_OUT" "Example School <ischool@example.edu>"
assert_contains "$MAIL_OUT" "> Read the agenda (https://example.edu/orientation)"
assert_not_contains "$MAIL_OUT" "<p>"
printf "mail formatting checks passed\n"
