#!/usr/bin/env bash
# Offline renderer assertions with synthetic fixtures.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${GITHUB_TEST_PYTHON:-python3}"
FIX="$SKILL_DIR/tests/fixtures"
render() { "$PY" "$SKILL_DIR/scripts/render.py" "$@"; }
fails=0

check() { # check <description> <haystack> <needle>
    case "$2" in
        *"$3"*) printf 'ok   %s\n' "$1" ;;
        *) printf 'FAIL %s\n       expected to find: %s\n' "$1" "$3"; fails=$((fails+1)) ;;
    esac
}
refute() {
    case "$2" in
        *"$3"*) printf 'FAIL %s\n       expected NOT to find: %s\n' "$1" "$3"; fails=$((fails+1)) ;;
        *) printf 'ok   %s\n' "$1" ;;
    esac
}

out="$(render board --project-number 9 --project-name example-board < "$FIX/github-board.json")"
check "board names the project"         "$out" "# Project #9 — example-board"
check "board groups by status"          "$out" "## Blocked"
check "board counts per column"         "$out" "**Count:** 1"
check "board items with no status"      "$out" "## No Status"

if [ "$fails" -ne 0 ]; then exit "$fails"; fi
printf "PASS: renderer assertions\n"
