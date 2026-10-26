#!/usr/bin/env bash
set -eu
AUTH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
source "$AUTH/scripts/client.sh"
export GOOGLE_CONFIG_DIR="$WORK"
cp "$AUTH/google-accounts.example.json" "$WORK/google-accounts.json"
_google_accounts_ready
[ "$(_google_account_path example '.token_path')" = "$WORK/google-example-token.json" ]
[ "$(_google_account_scopes example)" = 'https://www.googleapis.com/auth/documents.readonly' ]
jq '.accounts[0].drive.enabled = true | .accounts[0].drive.rename_enabled = true' "$WORK/google-accounts.json" > "$WORK/rename.json"
GOOGLE_ACCOUNTS_PATH=rename.json _google_account_scopes example | grep -qx 'https://www.googleapis.com/auth/drive.metadata'
(cd / && bash "$AUTH/scripts/authorize" check >/dev/null)
printf '%s\n' 'GOOGLE_ACCOUNTS_PATH=$(touch MUST_NOT_EXIST)' > "$WORK/.env"
_google_load_env
[ "$GOOGLE_ACCOUNTS_PATH" = '$(touch MUST_NOT_EXIST)' ]
[ ! -e MUST_NOT_EXIST ]
export GOOGLE_ACCOUNTS_PATH=google-accounts.json
_google_load_env
[ "$GOOGLE_ACCOUNTS_PATH" = google-accounts.json ]
if GOOGLE_ENV_FILE="$WORK/absent" _google_load_env >/dev/null 2>&1; then exit 1; fi
jq '.accounts += .accounts' "$WORK/google-accounts.json" > "$WORK/duplicate.json"
if GOOGLE_ACCOUNTS_PATH=duplicate.json _google_accounts_ready >/dev/null 2>&1; then exit 1; fi
printf '%s\n' 'Google configuration checks passed'
