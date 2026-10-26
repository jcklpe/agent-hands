#!/usr/bin/env bash
# Synthetic checks for literal credential configuration and provider isolation; no service calls.
set -eu
ODOO_AUTH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ODOO_USE_DIR="$(cd "${ODOO_AUTH_DIR}/../use-odoo-projects" && pwd)"
TEST_TEMP="$(mktemp -d)"
trap 'rm -rf "$TEST_TEMP"' EXIT
. "${ODOO_AUTH_DIR}/scripts/client.sh"
cp "${ODOO_AUTH_DIR}/odoo-accounts.example.json" "${TEST_TEMP}/odoo-accounts.json"

(
    unset ODOO_API_KEY ODOO_ENV_FILE ODOO_ACCOUNTS_PATH ODOO_REQUEST_STATE_PATH
    export ODOO_CONFIG_DIR="$TEST_TEMP"
    printf 'ODOO_API_KEY="$(touch %s/should-not-exist)"\nODOO_ACCOUNTS_PATH=odoo-accounts.json\n' "$TEST_TEMP" > "${TEST_TEMP}/.env"
    _odoo_load_env
    [ ! -e "${TEST_TEMP}/should-not-exist" ]
    [ "$ODOO_API_KEY" = "\$(touch $TEST_TEMP/should-not-exist)" ]
    [ "$(_odoo_accounts_path)" = "${TEST_TEMP}/odoo-accounts.json" ]
    [ "$(_odoo_request_state_path)" = "${TEST_TEMP}/odoo-last-request" ]
    (cd / && [ "$(_odoo_accounts_path)" = "${TEST_TEMP}/odoo-accounts.json" ])
)
(
    export ODOO_CONFIG_DIR="$TEST_TEMP" ODOO_API_KEY=exported-test-key
    unset ODOO_ENV_FILE
    _odoo_load_env
    [ "$ODOO_API_KEY" = exported-test-key ]
)
(
    export ODOO_CONFIG_DIR="$TEST_TEMP" ODOO_ENV_FILE=missing.env
    if _odoo_load_env >/dev/null 2>&1; then exit 1; fi
)
(
    export ODOO_CONFIG_DIR="$TEST_TEMP" ODOO_ENV_FILE=invalid.env
    printf '%s\n' 'PATH=/unexpected' > "${TEST_TEMP}/invalid.env"
    if _odoo_load_env >/dev/null 2>&1; then exit 1; fi
    printf '%s\n' 'ODOO_CONFIG_DIR=/unexpected' > "${TEST_TEMP}/invalid.env"
    if _odoo_load_env >/dev/null 2>&1; then exit 1; fi
    printf '%s\n' 'ODOO_API_KEY="unclosed' > "${TEST_TEMP}/invalid.env"
    if _odoo_load_env >/dev/null 2>&1; then exit 1; fi
)
(
    unset ODOO_API_KEY ODOO_ENV_FILE
    export ODOO_CONFIG_DIR="$TEST_TEMP"
    printf '%s\n' "ODOO_API_KEY='synthetic key with spaces'" > "${TEST_TEMP}/.env"
    _odoo_load_env
    [ "$ODOO_API_KEY" = 'synthetic key with spaces' ]
    output="$(bash "${ODOO_AUTH_DIR}/scripts/authorize" check example)"
    case "$output" in *'synthetic key'*) exit 1 ;; esac
)
(
    export ODOO_CONFIG_DIR="${TEST_TEMP}/unconfigured"
    unset ODOO_ENV_FILE ODOO_ACCOUNTS_PATH ODOO_API_KEY
    bash "${ODOO_USE_DIR}/scripts/odoo" --help >/dev/null
    bash "${ODOO_USE_DIR}/scripts/odoo" tasks update example 42 --name 'Offline preview' --json | jq -e '.task_id == 42 and .values.name == "Offline preview"' >/dev/null
)
printf '%s\n' 'Odoo literal env, override, missing-file, redaction, path, and credential-free preview checks passed'
