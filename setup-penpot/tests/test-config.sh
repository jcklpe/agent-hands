#!/usr/bin/env bash
# Synthetic checks for literal Penpot configuration, URL rules, permissions and key redaction; no service calls.
set -eu
PENPOT_SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_TEMP="$(mktemp -d)"
trap 'rm -rf "$TEST_TEMP"' EXIT
. "${PENPOT_SETUP_DIR}/scripts/config.sh"
SECRET='synthetic-penpot-key-123'
GOOD_URL="https://penpot.example/mcp/stream?userToken=${SECRET}"
run_check() { PENPOT_CONFIG_DIR="$TEST_TEMP" bash "${PENPOT_SETUP_DIR}/scripts/check" 2>&1; }

# Literal parsing: no command expansion, quotes stripped, exported value wins.
(
    unset PENPOT_MCP_SERVER_URL PENPOT_ENV_FILE
    export PENPOT_CONFIG_DIR="$TEST_TEMP"
    printf 'PENPOT_MCP_SERVER_URL="$(touch %s/should-not-exist)"\n' "$TEST_TEMP" > "${TEST_TEMP}/.env"
    _penpot_load_env
    [ ! -e "${TEST_TEMP}/should-not-exist" ]
    [ "$PENPOT_MCP_SERVER_URL" = "\$(touch $TEST_TEMP/should-not-exist)" ]
)
(
    unset PENPOT_ENV_FILE
    export PENPOT_CONFIG_DIR="$TEST_TEMP" PENPOT_MCP_SERVER_URL=exported-value
    printf "PENPOT_MCP_SERVER_URL='%s'\n" "$GOOD_URL" > "${TEST_TEMP}/.env"
    _penpot_load_env
    [ "$PENPOT_MCP_SERVER_URL" = exported-value ]
)
# An explicitly selected missing file fails; invalid keys and quotes are rejected.
(
    export PENPOT_CONFIG_DIR="$TEST_TEMP" PENPOT_ENV_FILE=missing.env
    if _penpot_load_env >/dev/null 2>&1; then exit 1; fi
)
(
    export PENPOT_CONFIG_DIR="$TEST_TEMP" PENPOT_ENV_FILE=invalid.env
    for line in 'PATH=/unexpected' 'PENPOT_CONFIG_DIR=/unexpected' 'PENPOT_PYTHON=/unexpected' 'PENPOT_MCP_SERVER_URL="unclosed' 'not an assignment'; do
        printf '%s\n' "$line" > "${TEST_TEMP}/invalid.env"
        if _penpot_load_env >/dev/null 2>&1; then exit 1; fi
    done
)
# URL rules: HTTPS needs a userToken; plain HTTP only for loopback servers.
(
    for url in "$GOOD_URL" 'http://127.0.0.1:4401/mcp' 'http://localhost:4401/mcp'; do
        PENPOT_MCP_SERVER_URL="$url" _penpot_server_url >/dev/null
    done
    for url in '' 'https://penpot.example/mcp/stream' 'https://penpot.example/mcp/stream?userToken=' 'http://penpot.example/mcp/stream?userToken=x' 'ftp://penpot.example/mcp' "https://penpot.example/mcp stream?userToken=${SECRET}"; do
        if PENPOT_MCP_SERVER_URL="$url" _penpot_server_url >/dev/null 2>&1; then exit 1; fi
    done
    [ "$(_penpot_url_host "$GOOD_URL")" = penpot.example ]
    [ "$(_penpot_url_host 'http://127.0.0.1:4401/mcp')" = 127.0.0.1 ]
)
# The check refuses group- or world-accessible files and never prints the URL or key.
(
    unset PENPOT_MCP_SERVER_URL PENPOT_ENV_FILE
    printf 'PENPOT_MCP_SERVER_URL=%s\n' "$GOOD_URL" > "${TEST_TEMP}/.env"
    chmod 644 "${TEST_TEMP}/.env"
    if output="$(run_check)"; then exit 1; fi
    case "$output" in *"$SECRET"*) exit 1 ;; *'chmod 600'*) ;; *) exit 1 ;; esac
    chmod 600 "${TEST_TEMP}/.env"
    output="$(run_check)"
    case "$output" in *"$SECRET"*|*userToken*) exit 1 ;; *'penpot.example (key present, from an owner-only env file)'*) ;; *) exit 1 ;; esac
    printf 'PENPOT_MCP_SERVER_URL=https://penpot.example/mcp/stream\n' > "${TEST_TEMP}/.env"
    if output="$(run_check)"; then exit 1; fi
    case "$output" in *'no userToken'*) ;; *) exit 1 ;; esac
)
(
    export PENPOT_CONFIG_DIR="${TEST_TEMP}/unconfigured"
    unset PENPOT_MCP_SERVER_URL PENPOT_ENV_FILE
    if output="$(bash "${PENPOT_SETUP_DIR}/scripts/check" 2>&1)"; then exit 1; fi
    case "$output" in *'not configured'*) ;; *) exit 1 ;; esac
    bash "${PENPOT_SETUP_DIR}/scripts/check" --help >/dev/null
)
printf '%s\n' 'Penpot literal env, override, missing-file, URL, permission and redaction checks passed'
