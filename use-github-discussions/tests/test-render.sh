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

out="$(render discussions --owner o --repo r < "$FIX/github-discussions.json")"
check "discussions group by category"   "$out" "## GENERAL"
check "discussions show comment count"  "$out" "**Comments:** 4"
check "answered discussions are marked" "$out" "**Answered**"

out="$(render discussion-detail --owner o --repo r < "$FIX/github-discussion-detail.json")"
check "detail shows the category"       "$out" "**Category:** Group decision making thread"
check "detail marks answered"           "$out" "**Answered**"
check "detail includes opening post"    "$out" "opening post body"
check "detail counts comments"          "$out" "## Comments (2)"
check "detail marks the answer comment" "$out" "marked as answer"
check "nested reply is quoted"          "$out" "> **@example-reviewer"
check "multi-line reply stays quoted"   "$out" "> with two lines"

if [ "$fails" -ne 0 ]; then exit "$fails"; fi
printf "PASS: renderer assertions\n"
