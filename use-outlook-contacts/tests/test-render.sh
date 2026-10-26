#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PYTHON="${M365_PYTHON:-python3}"
CONTACTS_OUT="$WORK/render.md"
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

"$PYTHON" "$SKILL/scripts/render.py" contacts \
    --alias fixture \
    --email student@my.example.edu \
    --refreshed "2026-07-15 18:00:00 UTC" \
    --max-results 500 \
    --notes-limit 4000 \
    --input "$SKILL/tests/fixtures/formatting.json" > "$CONTACTS_OUT"
assert_contains "$CONTACTS_OUT" "# Microsoft 365 Contacts - fixture"
assert_contains "$CONTACTS_OUT" "### Ada Lovelace"
assert_contains "$CONTACTS_OUT" "Contact ID: \`contact-1\`"
assert_contains "$CONTACTS_OUT" "Met through a research seminar."
printf "contacts formatting checks passed\n"
