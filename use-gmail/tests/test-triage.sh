#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../authorize-google/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}" GOOGLE_GMAIL_AUDIT_LOG="$WORK/audit.jsonl"
jq '.accounts[0].gmail.enabled=true' "$GOOGLE_AUTH_DIR/google-accounts.example.json" > "$WORK/accounts.example.json"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
expect_fail() { if "$@" > "$WORK/out.txt" 2> "$WORK/err.txt"; then fail "expected failure: $*"; fi; }
##- Gmail
jq '(.accounts[] | select(.alias == "example") | .gmail.write_enabled) = false' "$WORK/accounts.example.json" > "${WORK}/google-read.json"
jq '(.accounts[] | select(.alias == "example") | .gmail.write_enabled) = true' "$WORK/accounts.example.json" > "${WORK}/google-write.json"
GOOGLE_ACCOUNTS_PATH="${WORK}/google-read.json"
export GOOGLE_ACCOUNTS_PATH

_google_account_scopes example | grep -x 'https://www.googleapis.com/auth/gmail.modify' >/dev/null && fail "read-only alias should not request gmail.modify"
GOOGLE_ACCOUNTS_PATH="${WORK}/google-write.json" _google_account_scopes example | grep -x 'https://www.googleapis.com/auth/gmail.modify' >/dev/null || fail "write-enabled alias should request gmail.modify"

# Synthetic mailbox: m-inbox (INBOX), m-spam (SPAM), thread t-1 holding m-inbox. Label changes are recorded in a state file so readback sees them.
printf '{"m-inbox": ["INBOX", "UNREAD"], "m-spam": ["SPAM"]}\n' > "${WORK}/gmail-state.json"
_google_get_url() {
    local url="$2" id
    case "$url" in
        */labels) printf '%s\n' '{"labels":[{"id":"INBOX","name":"INBOX","type":"system"},{"id":"TRASH","name":"TRASH","type":"system"},{"id":"Label_1","name":"Receipts","type":"user"}]}' ;;
        */threads/t-1) jq -c '{id: "t-1", messages: [{id: "m-inbox", threadId: "t-1", labelIds: .["m-inbox"], payload: {headers: [{name: "Subject", value: "Invoice"}, {name: "From", value: "shop@example.com"}]}}]}' "${WORK}/gmail-state.json" ;;
        */messages/*)
            id="${url##*/}"
            jq -e --arg id "$id" 'has($id)' "${WORK}/gmail-state.json" >/dev/null || { printf 'curl: (22) The requested URL returned error: 404\n' >&2; return 22; }
            jq -c --arg id "$id" '{id: $id, threadId: "t-1", labelIds: .[$id], payload: {headers: [{name: "Subject", value: "Invoice"}, {name: "From", value: "shop@example.com"}]}}' "${WORK}/gmail-state.json" ;;
        *) return 1 ;;
    esac
}
_gmail_send() {
    printf '%s %s %s\n' "$1" "$3" "$4" >> "${WORK}/gmail-calls.log"
    local ids
    case "$3" in
        */messages/batchModify) ids="$(printf '%s' "$4" | jq -c '.ids')" ;;
        */threads/t-1/modify) ids='["m-inbox"]' ;;
        *) return 1 ;;
    esac
    jq --argjson ids "$ids" --argjson req "$4" 'reduce $ids[] as $i (.; .[$i] = ((.[$i] + ($req.addLabelIds // [])) - ($req.removeLabelIds // []) | unique))' "${WORK}/gmail-state.json" > "${WORK}/gmail-state.next" && mv "${WORK}/gmail-state.next" "${WORK}/gmail-state.json"
    printf '{}\n'
}
: > "${WORK}/gmail-calls.log"

_gmail_archive example --message m-inbox > "${WORK}/g-plan.txt"
grep -F "DRY RUN: nothing was changed" "${WORK}/g-plan.txt" >/dev/null || fail "gmail archive defaults to dry run"
[ -s "${WORK}/gmail-calls.log" ] && fail "gmail dry run must not write"
expect_fail _gmail_archive example --message m-inbox --execute
grep -F "not enabled for alias 'example'" "${WORK}/err.txt" >/dev/null || fail "gmail execute requires gmail.write_enabled"
expect_fail _gmail_archive example --message m-spam
grep -F "Trash or Spam" "${WORK}/err.txt" >/dev/null || fail "spam targets are refused"
expect_fail _gmail_archive example --message m-missing
grep -F "were not found" "${WORK}/err.txt" >/dev/null || fail "missing Gmail IDs fail"
expect_fail _gmail_label example --label TRASH --message m-inbox
grep -F "system label" "${WORK}/err.txt" >/dev/null || fail "system labels are refused"
expect_fail _gmail_label example --label Nope --message m-inbox
grep -F "No Gmail label matches" "${WORK}/err.txt" >/dev/null || fail "unknown labels fail"
expect_fail _gmail_unarchive example --message m-inbox
grep -F "Already in Inbox" "${WORK}/err.txt" >/dev/null || fail "unarchive refuses Inbox mail"

GOOGLE_ACCOUNTS_PATH="${WORK}/google-write.json"
_gmail_label example --label receipts --message m-inbox --skip-inbox --execute > "${WORK}/g-label.txt"
grep -F "confirmed by readback" "${WORK}/g-label.txt" >/dev/null || fail "gmail label is confirmed by readback"
jq -e '.["m-inbox"] == ["Label_1", "UNREAD"]' "${WORK}/gmail-state.json" >/dev/null || fail "label --skip-inbox adds the label and removes INBOX"
grep -F '"removeLabelIds":["INBOX"]' "${WORK}/gmail-calls.log" >/dev/null || fail "skip-inbox sends removeLabelIds INBOX"

_gmail_unarchive example --thread t-1 --execute > "${WORK}/g-unarchive.txt"
grep -F "/threads/t-1/modify" "${WORK}/gmail-calls.log" >/dev/null || fail "thread targets use threads.modify"
jq -e '.["m-inbox"] | index("INBOX")' "${WORK}/gmail-state.json" >/dev/null || fail "unarchive restores INBOX"

_gmail_archive example --thread t-1 --execute > /dev/null
_gmail_unlabel example --label Receipts --message m-inbox --execute > /dev/null
jq -e '.["m-inbox"] == ["UNREAD"]' "${WORK}/gmail-state.json" >/dev/null || fail "archive then unlabel leaves only UNREAD"
jq -e -s '[.[] | select(.service == "gmail")] | length == 4 and all(.verified)' "$GOOGLE_GMAIL_AUDIT_LOG" >/dev/null || fail "gmail changes are written to the audit log"
grep -E 'trash|delete' "${WORK}/gmail-calls.log" >/dev/null && fail "no Gmail call may trash or delete"

expect_fail _gmail_not_spam example --message m-inbox
grep -F "currently in Spam" "${WORK}/err.txt" >/dev/null || fail "not-spam requires Spam mail"
_gmail_not_spam example --message m-spam --execute > "${WORK}/g-notspam.txt"
jq -e '.["m-spam"] == ["INBOX"]' "${WORK}/gmail-state.json" >/dev/null || fail "not-spam removes SPAM and adds INBOX"
grep -F "confirmed by readback" "${WORK}/g-notspam.txt" >/dev/null || fail "not-spam is confirmed by readback"
jq -e -s '[.[] | select(.service == "gmail")] | length == 5 and .[-1].action == "not-spam"' "$GOOGLE_GMAIL_AUDIT_LOG" >/dev/null || fail "not-spam is written to the audit log"

expect_fail _gmail_create_label example --name receipts
grep -F "already exists" "${WORK}/err.txt" >/dev/null || fail "duplicate label fails"
_gmail_create_label example --name "Triage/Newsletters" | grep -F "DRY RUN" >/dev/null || fail "create-label dry run"

printf 'Gmail retained checks passed\n'
