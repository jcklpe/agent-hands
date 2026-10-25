#!/usr/bin/env bash
set -eu
AUTH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$AUTH/scripts/client.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/temp"
export M365_CONFIG_DIR="$WORK" TMPDIR="$WORK/temp"
cp "$AUTH/m365-powershell-accounts.example.json" "$WORK/m365-accounts.json"
expect_failure() { if "$@" > "$WORK/out" 2> "$WORK/error"; then printf 'Unexpected success\n' >&2; exit 1; fi; }
_m365_accounts_ready
_m365_scopes example > "$WORK/scopes"
grep -Fx Contacts.ReadWrite "$WORK/scopes" >/dev/null
[ "$(wc -l < "$WORK/scopes" | tr -d ' ')" = 2 ]
printf '%s\n' 'M365_ACCOUNTS_PATH=$(touch SHOULD_NOT_EXIST)' > "$WORK/.env"
_m365_load_env
[ "$M365_ACCOUNTS_PATH" = '$(touch SHOULD_NOT_EXIST)' ]
[ ! -e SHOULD_NOT_EXIST ]
unset M365_ACCOUNTS_PATH
rm "$WORK/.env"
cd /
[ "$(_m365_accounts_path)" = "$WORK/m365-accounts.json" ]
M365_ENV_FILE="$WORK/missing" expect_failure _m365_load_env
jq '.accounts += [.accounts[0]]' "$WORK/m365-accounts.json" > "$WORK/duplicate.json"
M365_ACCOUNTS_PATH=duplicate.json expect_failure _m365_accounts_ready
_m365_prepare_powershell_request GET example 'https://graph.microsoft.com/v1.0/me' '' "$WORK/request.json" --data-urlencode '$select=id,displayName' -H 'Prefer: outlook.body-content-type="text"'
jq -e '.expected_account == "person@example.com" and (.uri | contains("%24select=id%2CdisplayName"))' "$WORK/request.json" >/dev/null
_m365_validate_url https://graph.microsoft.com/v1.0/me
expect_failure _m365_validate_url https://graph.microsoft.com.attacker.invalid/v1.0/me
expect_failure _m365_http GET example https://attacker.invalid/ ''
# Pagination transport is stubbed; validation of each real URL occurs before auth in _m365_http.
_m365_get() {
    [ "${FAIL_READ:-0}" = 0 ] || return 1
    case "$2" in *second*) printf '%s' '{"value":[{"id":"two"}]}' ;; *) printf '%s' '{"value":[{"id":"one"}],"@odata.nextLink":"second"}' ;; esac
}
_m365_get_paginated example 5 "$WORK/pages.json" first
[ "$(jq '.value | length' "$WORK/pages.json")" = 2 ]
printf previous > "$WORK/preserved.json"
FAIL_READ=1 expect_failure _m365_get_paginated example 5 "$WORK/preserved.json" first
[ "$(cat "$WORK/preserved.json")" = previous ]
_m365_get() { printf '%s' '{"value":[],"@odata.nextLink":"again"}'; }
jq '.accounts[0].max_pages=2' "$WORK/m365-accounts.json" > "$WORK/capped.json"
M365_ACCOUNTS_PATH=capped.json expect_failure _m365_get_paginated example 5 "$WORK/preserved.json" first
[ "$(cat "$WORK/preserved.json")" = previous ]
for residual in "$WORK/temp"/microsoft-work.*; do [ ! -e "$residual" ] || exit 1; done
printf '%s\n' 'Microsoft literal config, alias, request identity, endpoint, pagination, and cleanup checks passed'
