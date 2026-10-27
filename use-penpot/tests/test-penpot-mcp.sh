#!/usr/bin/env bash
# Connector checks with synthetic keys: help without configuration, refusal without a URL, key redaction on failure, deterministic key-safe launch arguments, and a full relay through a loopback stand-in server in JSON and streaming reply modes.
# Set PENPOT_TEST_LOCAL_URL to a running keyless loopback Penpot MCP server (for example http://127.0.0.1:4401/mcp) to also relay through the real server.
set -euo pipefail
PENPOT_USE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONNECTOR="${PENPOT_USE_DIR}/scripts/penpot-mcp"
TEST_TEMP="$(mktemp -d)"
stand_in_pid=''
cleanup() {
    if [ -n "$stand_in_pid" ]; then
        kill "$stand_in_pid" 2>/dev/null || true
        wait "$stand_in_pid" 2>/dev/null || true
    fi
    rm -rf "$TEST_TEMP"
}
trap cleanup EXIT
SECRET='synthetic-penpot-key-456'
# Port 9 on loopback is expected to refuse connections, so the request fails quickly and offline.
FAILING_URL="https://127.0.0.1:9/mcp/stream?userToken=${SECRET}"
export PENPOT_CONFIG_DIR="${TEST_TEMP}/unconfigured"
unset PENPOT_MCP_SERVER_URL PENPOT_ENV_FILE

bash "$CONNECTOR" --help >/dev/null
if output="$(bash "$CONNECTOR" --list-tools 2>&1)"; then exit 1; fi
case "$output" in *'not configured'*) ;; *) exit 1 ;; esac
if bash "$CONNECTOR" --unexpected >/dev/null 2>&1; then exit 1; fi

# A failing connection reports an error without the key, in either mode.
if output="$(PENPOT_MCP_SERVER_URL="$FAILING_URL" bash "$CONNECTOR" --list-tools 2>&1)"; then exit 1; fi
case "$output" in *"$SECRET"*) exit 1 ;; *'connection ended with an error'*) ;; *) printf '%s\n' "$output" >&2; exit 1 ;; esac

# Deterministic launch-argument and test-harness checks use controlled executables only.
python3 "${PENPOT_USE_DIR}/tests/test_penpot_launch.py"
printf '%s\n' 'PASS help, configuration refusal, error redaction and deterministic launch checks'
printf '%s\n' 'SKIP OS process-argument inspection: separate opt-in check; unverified where process inspection is prohibited.'

# Full relay and tool listing through a recording stand-in server, in both reply modes Streamable HTTP allows.
probe() { uv run --project "$PENPOT_USE_DIR" --locked --quiet python "${PENPOT_USE_DIR}/tests/relay_probe.py" bash "$CONNECTOR"; }
for mode in sse json; do
    log="${TEST_TEMP}/requests-${mode}.jsonl"
    port_file="${TEST_TEMP}/port-${mode}"
    python3 -I "${PENPOT_USE_DIR}/tests/stand_in_server.py" "$port_file" "$log" "$mode" &
    stand_in_pid=$!
    for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$port_file" ] && break; sleep 0.5; done
    stand_in_url="http://127.0.0.1:$(cat "$port_file")/mcp"
    PENPOT_MCP_SERVER_URL="$stand_in_url" probe | grep -q '"exit": 0'
    PENPOT_MCP_SERVER_URL="$stand_in_url" bash "$CONNECTOR" --list-tools | grep -q 'execute_code'
    kill "$stand_in_pid"
    wait "$stand_in_pid" 2>/dev/null || true
    stand_in_pid=''
    sequence="$(python3 -I -c 'import json,sys; print(" ".join((json.loads(r["body"]).get("method") if r["body"] else r["method"]) + ("+session" if r["session"] else "") for r in map(json.loads, open(sys.argv[1]))))' "$log")"
    # The optional GET stream may come before or after the initialized notification; the session must start with initialize and end with DELETE.
    for expected in 'notifications/initialized+session' 'tools/list+session'; do
        case "$sequence" in *"$expected"*) ;; *) printf 'Missing %s in the %s request sequence: %s\n' "$expected" "$mode" "$sequence" >&2; exit 1 ;; esac
    done
    case "$sequence" in 'initialize '*'DELETE+session') ;; *) printf 'Unexpected %s request sequence: %s\n' "$mode" "$sequence" >&2; exit 1 ;; esac
    printf 'PASS stand-in relay and tool listing (%s)\n' "$mode"
done

if [ -n "${PENPOT_TEST_LOCAL_URL:-}" ]; then
    PENPOT_MCP_SERVER_URL="$PENPOT_TEST_LOCAL_URL" probe | grep -q '"execute_code"'
    PENPOT_MCP_SERVER_URL="$PENPOT_TEST_LOCAL_URL" bash "$CONNECTOR" --list-tools | grep -q 'execute_code'
    printf '%s\n' 'PASS optional real-server local relay and tool listing'
else
    printf '%s\n' 'SKIP optional real-server relay: PENPOT_TEST_LOCAL_URL is not set; real-server access remains unverified'
fi
printf '%s\n' 'PASS supported Penpot connector checks; OS inspection and real-server coverage are reported separately above'
