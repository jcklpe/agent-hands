#!/usr/bin/env bash
# Compatibility route to the portable Google Docs checks.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/skills/use-google-docs/tests/test-docs-comment.sh" "$@"
