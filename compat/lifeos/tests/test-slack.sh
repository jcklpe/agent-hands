#!/usr/bin/env bash
set -eu
HANDS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
python3 "$HANDS/skills/authorize-slack/tests/test_request_helpers.py"
for owner in use-slack-messages use-slack-lists; do
    python3 "$HANDS/skills/$owner/tests/test-write-guards.py"
done
