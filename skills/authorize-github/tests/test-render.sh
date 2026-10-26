#!/usr/bin/env bash
# Offline renderer assertions with synthetic fixtures.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${GITHUB_TEST_PYTHON:-python3}"
FIX="$SKILL_DIR/tests/fixtures"
render() { "$PY" "$SKILL_DIR/scripts/render_items.py" "$@"; }
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

out="$(render issue-index --owner o --repo r --kind issue --detail-dir issues < "$FIX/github-issues.json")"
check "index shows the repo"            "$out" "# Open Issues — o/r"
check "index counts items"              "$out" "**Count:** 2 open issues"
check "index groups by first label"     "$out" "## INFRASTRUCTURE"
check "index links to the detail file"  "$out" "(issues/42.md)"
check "index shows assignees"           "$out" "**Assigned:** alice"
check "unlabeled items get a section"   "$out" "## UNLABELED"
refute "index does not inline full body" "$out" "PARAGRAPH_THAT_SHOULD_BE_TRUNCATED"

out="$(render item-detail --owner o --repo r --kind issue < "$FIX/github-issue-detail.json")"
check "detail shows the title"          "$out" "# #42 — Fix the widget"
check "detail includes the full body"   "$out" "full body text here"
check "detail includes comments"        "$out" "## Comments (1)"
check "detail attributes the comment"   "$out" "### @bob —"

# A PR index must not be mislabeled as issues — the two share a renderer.
out="$(render issue-index --owner o --repo r --kind pr --detail-dir pull-requests < "$FIX/github-issues.json")"
check "pr index says pull requests"     "$out" "# Open Pull Requests"
check "pr index links to pr details"    "$out" "(pull-requests/42.md)"
refute "pr index is not called issues"  "$out" "open issues"

if [ "$fails" -ne 0 ]; then exit "$fails"; fi
printf "PASS: renderer assertions\n"
