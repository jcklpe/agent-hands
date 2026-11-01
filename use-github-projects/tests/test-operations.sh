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
"${GITHUB_TEST_PYTHON:-${GITHUB_PYTHON:-python3.13}}" -B -m unittest discover -s "$SKILL_DIR/tests" -p 'test_*.py'
printf 'PASS: project export and guarded collaboration operations\n'
