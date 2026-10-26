#!/usr/bin/env bash
# Offline synthetic requests; no remote or credential store.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$SKILL_DIR/../authorize-github/tests/operations-fixture.sh"
. "$SKILL_DIR/scripts/operations.sh"
GITHUB_USE_DIR="$SKILL_DIR"
DISCUSSION_FIXTURE="$SKILL_DIR/tests/fixtures/github-discussion-detail.json"
_github_config_ready
_github_export_discussions example-owner/example-project "$work/output" > /dev/null
grep -q 'Bounded view' "$work/output/discussions.md"
printf 'PASS: discussion export\n'
