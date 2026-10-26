#!/usr/bin/env bash
# Offline synthetic requests; no remote or credential store.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$SKILL_DIR/../setup-github/tests/operations-fixture.sh"
. "$SKILL_DIR/scripts/operations.sh"
GITHUB_USE_DIR="$SKILL_DIR"
_github_config_ready
_github_export_projects example "$work/output" > /dev/null
[ -f "$work/output/board-example-board.md" ]
mode=project
_github_move_card --repo example --issue 1 --status Ready > "$work/out"
grep -q 'DRY RUN' "$work/out"
[ ! -e "$work/mutations" ]
_github_move_card --repo example --issue 1 --status Ready --execute > /dev/null
[ "$(cat "$work/mutations")" = mutation ]
printf 'PASS: project export and write gates\n'
