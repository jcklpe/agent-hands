#!/usr/bin/env bash
set -eu
TRELLO_AUTH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$TRELLO_AUTH_DIR/scripts/client.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/trello-config-check.XXXXXX")"
trap 'rm -rf "$work"' EXIT
TRELLO_ENV_FILE="$work/.env"
printf '%s\n' 'TRELLO_API_KEY=from-file' 'TRELLO_TOKEN="$(touch should-not-exist)"' 'TRELLO_WRITE_TOKEN=synthetic' > "$TRELLO_ENV_FILE"
TRELLO_API_KEY=from-environment
export TRELLO_API_KEY
cd "$work"
_trello_load_env
[ "$TRELLO_API_KEY" = from-environment ]
[ "$TRELLO_TOKEN" = '$(touch should-not-exist)' ]
[ ! -e should-not-exist ]
_trello_ready
_trello_write_ready
TRELLO_ENV_FILE="$work/missing"
if _trello_load_env > "$work/out" 2>&1; then echo 'FAIL: missing explicit env was accepted'; exit 1; fi
TRELLO_ENV_FILE="$work/.env"
printf 'PATH=sensitive-placeholder\n' > "$TRELLO_ENV_FILE"
if _trello_load_env > "$work/out" 2>&1; then echo 'FAIL: unrelated env key accepted'; exit 1; fi
if grep -q 'sensitive-placeholder' "$work/out"; then echo 'FAIL: invalid assignment disclosed its value'; exit 1; fi
printf 'ok: Trello literal config, precedence, and error redaction\n'
