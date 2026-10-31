#!/usr/bin/env bash
# Offline synthetic requests; no remote or credential store.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$SKILL_DIR/../setup-github/tests/operations-fixture.sh"
. "$SKILL_DIR/scripts/operations.sh"
GITHUB_USE_DIR="$SKILL_DIR"
_github_config_ready
_github_export_items example-owner/example-project pr "$work/output" > /dev/null
grep -q 'Open Pull Requests' "$work/output/pull-requests.md"
printf 'PASS: pull-request export\n'
"${GITHUB_TEST_PYTHON:-python3}" -B "$SKILL_DIR/../setup-github/tests/test_collaboration.py" --domain pull-requests
