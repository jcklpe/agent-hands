#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../setup-google-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}" GOOGLE_GMAIL_AUDIT_LOG="$WORK/audit.jsonl"
jq '.accounts[0].gmail.enabled=true' "$GOOGLE_AUTH_DIR/google-accounts.example.json" > "$WORK/accounts.example.json"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
expect_fail() { if "$@" > "$WORK/out.txt" 2> "$WORK/err.txt"; then fail "expected failure: $*"; fi; }
##- Gmail
jq '.accounts |= map(.gmail.filters_enabled = false)' "$WORK/accounts.example.json" > "${WORK}/g-off.json"
jq '.accounts |= map(.gmail.filters_enabled = true)' "$WORK/accounts.example.json" > "${WORK}/g-on.json"
GOOGLE_ACCOUNTS_PATH="${WORK}/g-off.json"
export GOOGLE_ACCOUNTS_PATH
if _google_account_scopes example 2>/dev/null | grep -q 'gmail.settings.basic'; then fail "settings scope requested without filters_enabled"; fi
GOOGLE_ACCOUNTS_PATH="${WORK}/g-on.json"
_google_account_scopes example 2>/dev/null | grep -qx 'https://www.googleapis.com/auth/gmail.settings.basic' || fail "settings scope missing with filters_enabled"
GOOGLE_ACCOUNTS_PATH="${WORK}/g-off.json"

_gmail_labels_fetch() { printf '%s\n' '{"labels":[{"id":"INBOX","name":"INBOX","type":"system"},{"id":"Label_1","name":"delete-me","type":"user"}]}'; }
_gmail_list() { printf 'preview for: %s\n' "$3"; }
_google_get_url() {
    case "$2" in
        */settings/filters) printf '%s\n' '{"filter":[{"id":"f-old","criteria":{"from":"news@example.com"},"action":{"addLabelIds":["Label_1"],"removeLabelIds":["INBOX"]}}]}' ;;
        */settings/filters/f-new) printf '%s\n' '{"id":"f-new","criteria":{"from":"statements@bank.example.com","subject":"Your eStatement has arrived"},"action":{"addLabelIds":["Label_1"],"removeLabelIds":["INBOX"]}}' ;;
        *) return 1 ;;
    esac
}
_gmail_send() { printf '%s %s %s\n' "$1" "$3" "$4" >> "${WORK}/gmail-writes.log"; printf '%s\n' '{"id":"f-new"}'; }

out="$(_gmail_filters example)"
printf '%s\n' "$out" | grep -F -- "filter_id: f-old | when: from=news@example.com | then: label delete-me, skip inbox" >/dev/null || fail "filter listing"

expect_fail _gmail_create_filter example --label delete-me
expect_fail _gmail_create_filter example --from x@example.com
expect_fail _gmail_create_filter example --from x@example.com --label INBOX

out="$(_gmail_create_filter example --from statements@bank.example.com --subject "Your eStatement has arrived" --label delete-me --skip-inbox)"
printf '%s\n' "$out" | grep -F -- "DRY RUN: no filter was created" >/dev/null || fail "gmail dry run"
printf '%s\n' "$out" | grep -F -- 'preview for: from:(statements@bank.example.com) subject:(Your eStatement has arrived)' >/dev/null || fail "gmail preview search"
[ ! -f "${WORK}/gmail-writes.log" ] || fail "dry run wrote"
expect_fail _gmail_create_filter example --from statements@bank.example.com --subject "Your eStatement has arrived" --label delete-me --skip-inbox --execute
[ ! -f "${WORK}/gmail-writes.log" ] || fail "write without filters_enabled"

GOOGLE_ACCOUNTS_PATH="${WORK}/g-on.json"
out="$(_gmail_create_filter example --from statements@bank.example.com --subject "Your eStatement has arrived" --label delete-me --skip-inbox --execute)"
printf '%s\n' "$out" | grep -F -- "Created filter (confirmed by readback): filter_id: f-new" >/dev/null || fail "gmail create"
grep -F -- 'POST' "${WORK}/gmail-writes.log" | grep -F -- '"removeLabelIds":["INBOX"]' >/dev/null || fail "gmail body"
if grep -F -- 'forward' "${WORK}/gmail-writes.log" >/dev/null; then fail "forward in body"; fi
jq -e 'select(.action == "create-filter") | .verified == true' "$GOOGLE_GMAIL_AUDIT_LOG" >/dev/null || fail "gmail audit"

printf 'Gmail retained checks passed\n'
