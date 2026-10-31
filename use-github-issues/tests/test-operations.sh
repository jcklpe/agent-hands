#!/usr/bin/env bash
# Offline native collaboration requests; the fixture supplies a synthetic gh executable.
set -eu
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"${GITHUB_TEST_PYTHON:-python3}" -B "$SKILL_DIR/../setup-github/tests/test_collaboration.py" --domain issues
