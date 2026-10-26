#!/usr/bin/env bash
set -eu
HANDS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
for owner in authorize-github use-github-discussions use-github-projects; do
    bash "$HANDS/skills/$owner/tests/test-render.sh"
done
