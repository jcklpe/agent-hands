#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PYTHON="${M365_PYTHON:-python3}"
PLANNER_OUT="$WORK/render.md"
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

"$PYTHON" "$SKILL/scripts/render.py" planner \
    --alias fixture \
    --email student@my.example.edu \
    --me user-me \
    --refreshed "2026-10-02 18:00:00 UTC" \
    --description-limit 2000 \
    --input "$SKILL/tests/fixtures/formatting.json" > "$PLANNER_OUT"
grep -F -- "# Microsoft 365 Planner - fixture" "$PLANNER_OUT" >/dev/null
grep -F -- "Open tasks: 3 | Done: 1 | Open and assigned to you: 1" "$PLANNER_OUT" >/dev/null
grep -F -- "- Assignees: Test Student (you)" "$PLANNER_OUT" >/dev/null
grep -F -- "- Labels: LMS" "$PLANNER_OUT" >/dev/null
grep -F -- "- Priority: important" "$PLANNER_OUT" >/dev/null
grep -F -- "  - [x] Collect examples" "$PLANNER_OUT" >/dev/null
grep -F -- "### (no bucket)" "$PLANNER_OUT" >/dev/null
grep -F -- "Kickoff meeting | To Do | completed 2026-09-22 by Pat Example" "$PLANNER_OUT" >/dev/null
# Buckets follow Planner's ascending orderHint, so LMS Build (1000) precedes To Do (8585).
[ "$(grep -n '^### LMS Build' "$PLANNER_OUT" | cut -d: -f1)" -lt "$(grep -n '^### To Do' "$PLANNER_OUT" | cut -d: -f1)" ]


printf "planner formatting checks passed\n"
