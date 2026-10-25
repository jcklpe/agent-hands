#!/usr/bin/env bash
# Preserve configured multi-domain export and honest partial failure without live GitHub access.
set -eu
TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB_DIR="$TOOL_DIR/lib"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
. "$LIB_DIR/github.sh"
cat > "$WORK/repos.json" <<'JSON'
{"repos":[{"alias":"first","owner":"example","repo":"first","issues":true,"prs":true,"discussions":true},{"alias":"second","owner":"example","repo":"second","issues":false,"prs":false,"discussions":false}]}
JSON
_github_repos_config() { printf '%s/repos.json\n' "$WORK"; }
_github_ready() { printf 'ready\n' >> "$WORK/readiness"; }
_github_export_items() { printf 'items %s %s\n' "$1" "$2" >> "$WORK/calls"; printf 'synthetic export\n' > "$3/$2.md"; }
_github_export_discussions() {
    printf 'discussions %s\n' "$1" >> "$WORK/calls"
    [ "${FAIL_DISCUSSIONS:-0}" = 0 ] || return 23
    printf 'synthetic discussion\n' > "$2/discussions.md"
}
_github_export_projects() { printf 'projects %s\n' "$1" >> "$WORK/calls"; }
# A missing destination fails before checking auth or attempting any export.
if _github_sync first > "$WORK/out" 2> "$WORK/err"; then exit 1; fi
[ ! -e "$WORK/readiness" ]
grep -F -- '--output' "$WORK/err" >/dev/null
_github_sync first --output "$WORK/export" > "$WORK/out"
[ -f "$WORK/export/example-first/issue.md" ]
[ -f "$WORK/export/example-first/pr.md" ]
[ -f "$WORK/export/example-first/discussions.md" ]
[ "$(wc -l < "$WORK/calls" | tr -d ' ')" = 4 ]
grep -Fx 'projects first' "$WORK/calls" >/dev/null
# Aggregate failure keeps prior failed-domain output and still checks the next repository.
printf 'retained discussion\n' > "$WORK/export/example-first/discussions.md"
: > "$WORK/calls"
FAIL_DISCUSSIONS=1
if _github_sync --all --output "$WORK/export" > "$WORK/out" 2> "$WORK/err"; then exit 1; fi
[ "$(cat "$WORK/export/example-first/discussions.md")" = 'retained discussion' ]
grep -Fx 'projects second' "$WORK/calls" >/dev/null
! grep -F 'items example/second' "$WORK/calls" >/dev/null
! grep -F 'discussions example/second' "$WORK/calls" >/dev/null
! grep -F "Updated $WORK/export/example-first" "$WORK/out" >/dev/null
grep -F "Updated $WORK/export/example-second" "$WORK/out" >/dev/null
printf 'PASS: aggregate selection, explicit destination, continuation, and partial failure\n'
