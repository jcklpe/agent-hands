#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../setup-google-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/temp"
export GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}" GOOGLE_CONFIG_DIR="$WORK" TMPDIR="$WORK/temp" GOOGLE_GMAIL_AUDIT_LOG="$WORK/audit.jsonl"
jq '.accounts[0].gmail.enabled=true | .accounts[0].gmail.filters_enabled=true' "$GOOGLE_AUTH_DIR/google-accounts.example.json" > "$WORK/google-accounts.json"
expect_failure() { if "$@" > "$WORK/failed" 2> "$WORK/error"; then printf 'Unexpected success\n' >&2; exit 1; fi; }
_gmail_get() {
    case "$2" in
        */messages) printf '%s' '{"messages":[{"id":"synthetic-message"}],"nextPageToken":"more"}' ;;
        */messages/*)
            [ "${FAIL_MESSAGE:-0}" = 0 ] || return 1
            if [ "${MALFORMED_MESSAGE:-0}" = 1 ]; then printf '%s' '{"error":{"message":"Synthetic failure"}}'; return; fi
            printf '%s' '{"id":"synthetic-message","payload":{"mimeType":"text/plain","headers":[{"name":"Subject","value":"Synthetic subject"}],"body":{"data":"SGVsbG8"}}}' ;;
    esac
}
printf '%s' previous > "$WORK/export.md"
FAIL_MESSAGE=1 expect_failure _gmail_export example --output "$WORK/export.md" --query in:inbox
[ "$(cat "$WORK/export.md")" = previous ]
MALFORMED_MESSAGE=1 expect_failure _gmail_export example --output "$WORK/export.md" --query in:inbox
[ "$(cat "$WORK/export.md")" = previous ]
expect_failure _gmail_export example --output "$WORK/export.md"
_gmail_export example --output "$WORK/export.md" --query in:inbox > /dev/null
grep -F 'Synthetic subject' "$WORK/export.md" >/dev/null
_gmail_labels_fetch() { printf '%s' '{"labels":[]}'; }
_google_get_url() { printf '%s' '{"id":"synthetic-filter","criteria":{"from":"news@example.com"},"action":{"removeLabelIds":["INBOX"]}}'; }
_gmail_send() { printf '%s\n' deleted >> "$WORK/deletes"; }
_gmail_filters_fetch() {
    [ "${FAIL_READBACK:-0}" = 0 ] || return 1
    if [ "${FILTER_REMAINS:-0}" = 1 ]; then printf '%s' '{"filter":[{"id":"synthetic-filter"}]}'
    else printf '%s' '{}'
    fi
}
FAIL_READBACK=1 expect_failure _gmail_delete_filter example --filter synthetic-filter --execute
grep -F 'verification failed' "$WORK/error" >/dev/null
[ ! -e "$WORK/audit.jsonl" ]
FILTER_REMAINS=1 expect_failure _gmail_delete_filter example --filter synthetic-filter --execute
[ ! -e "$WORK/audit.jsonl" ]
_gmail_delete_filter example --filter synthetic-filter --execute > /dev/null
jq -e '.verified == true and .action == "delete-filter"' "$WORK/audit.jsonl" >/dev/null
"$GOOGLE_PYTHON" - "$WORK/audit.jsonl" <<'PY'
import os, stat, sys
assert stat.S_IMODE(os.stat(sys.argv[1]).st_mode) == 0o600
PY
for residual in "$WORK/temp"/google-gmail.* "$WORK"/.google-output-*; do [ ! -e "$residual" ] || exit 1; done
printf '%s\n' 'Gmail export preservation, deletion verification, private audit, and cleanup passed'
