#!/usr/bin/env bash
# Optional OS-level assertion. Never enable where process inspection is prohibited.
set -eu
if [ "${1:-}" != '--inspect-processes' ] || [ "$#" -ne 1 ]; then
    printf '%s\n' 'SKIP OS process-argument inspection: requires explicit --inspect-processes and permission to use ps; security assertion remains unverified.'
    exit 77
fi
PENPOT_USE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONNECTOR="${PENPOT_USE_DIR}/scripts/penpot-mcp"
TEST_TEMP="$(mktemp -d)"
relay_pid=''
cleanup() {
    exec 3>&-
    if [ -n "$relay_pid" ]; then
        kill "$relay_pid" 2>/dev/null || true
        wait "$relay_pid" 2>/dev/null || true
    fi
    rm -rf "$TEST_TEMP"
}
trap cleanup EXIT
SECRET='synthetic-penpot-key-456'
FAILING_URL="https://127.0.0.1:9/mcp/stream?userToken=${SECRET}"
export PENPOT_CONFIG_DIR="${TEST_TEMP}/unconfigured"
unset PENPOT_MCP_SERVER_URL PENPOT_ENV_FILE
mkfifo "${TEST_TEMP}/stdin"
PENPOT_MCP_SERVER_URL="$FAILING_URL" bash "$CONNECTOR" < "${TEST_TEMP}/stdin" > "${TEST_TEMP}/stdout" 2> "${TEST_TEMP}/stderr" &
relay_pid=$!
exec 3> "${TEST_TEMP}/stdin"
sleep 3
if ! kill -0 "$relay_pid" 2>/dev/null; then
    printf '%s\n' 'FAIL OS process-argument check: relay exited before it could be inspected.' >&2
    exit 1
fi
if listing="$(ps -axo args= 2> "${TEST_TEMP}/ps-error")"; then
    :
else
    inspection_status=$?
    printf 'SKIP OS process-argument inspection: ps unavailable or denied (exit %s); security assertion remains unverified.\n' "$inspection_status"
    exit 77
fi
exec 3>&-
wait "$relay_pid" || true
relay_pid=''
case "$listing" in *"$SECRET"*) printf '%s\n' 'FAIL Key found in a process argument list' >&2; exit 1 ;; esac
case "$(cat "${TEST_TEMP}/stdout" "${TEST_TEMP}/stderr")" in *"$SECRET"*) printf '%s\n' 'FAIL Key found in relay output' >&2; exit 1 ;; esac
printf '%s\n' 'PASS OS process-argument and relay-output assertions with a synthetic key'
