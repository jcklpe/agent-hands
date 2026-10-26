#!/usr/bin/env bash
# Offline synthetic requests; no remote or credential store.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$SKILL_DIR/../authorize-github/tests/operations-fixture.sh"
. "$SKILL_DIR/scripts/operations.sh"
GITHUB_USE_DIR="$SKILL_DIR"
rm "$work/github-repos.json"
_github_create_issue --repo example-owner/example-project --title 'Example' --body 'Literal $() and `text`' > "$work/out"
grep -q 'DRY RUN' "$work/out"
[ ! -e "$work/write-args" ]
_github_create_issue --repo example-owner/example-project --title 'Example' --body 'Literal $() and `text`' --label 'literal\nlabel' --execute > /dev/null
grep -Fxq 'Literal $() and `text`' "$work/write-args"
grep -Fxq 'literal\nlabel' "$work/write-args"
printf 'PASS: issue preview, execution and literal inputs\n'
