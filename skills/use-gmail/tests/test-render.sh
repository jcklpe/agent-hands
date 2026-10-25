#!/usr/bin/env bash
##- Test Google Gmail and Sheets Markdown renderers

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
GMAIL_OUT="$WORK/gmail.md"

python3 "$SKILL/scripts/render.py" \
    example \
    morgan@example.com \
    "in:inbox newer_than:30d" \
    150 \
    8000 \
    "2026-06-01 18:00:00 UTC" \
    "$SKILL/tests/fixtures/gmail-messages.json" > "$GMAIL_OUT"


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

assert_contains "$GMAIL_OUT" "# Gmail - example"
assert_contains "$GMAIL_OUT" "Query: \`in:inbox newer_than:30d\`"
assert_contains "$GMAIL_OUT" "### 2026-06-01T17:00:00Z - Plain message"
assert_contains "$GMAIL_OUT" "> Hello from plain text."
assert_contains "$GMAIL_OUT" "Attachments: yes"
assert_contains "$GMAIL_OUT" "> Hello link (https://example.com)"
assert_not_contains "$GMAIL_OUT" "<p>"
assert_not_contains "$GMAIL_OUT" "agenda.pdf"

printf 'google render fixtures passed\n'
