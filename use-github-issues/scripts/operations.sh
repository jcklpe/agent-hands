#!/usr/bin/env bash
##- Portable GitHub issues operations.
. "${GITHUB_AUTH_DIR}/scripts/items.sh"

_github_create_issue() { _github_collaboration create-issue "$@"; }
