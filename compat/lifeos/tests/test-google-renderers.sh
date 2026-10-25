#!/usr/bin/env bash
set -eu
HANDS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
bash "$HANDS/skills/use-gmail/tests/test-render.sh"
bash "$HANDS/skills/use-google-sheets/tests/test-read.sh"
