#!/usr/bin/env bash
##- Test Microsoft 365 Inbox rules offline: scopes, required criteria and actions, refused folders, dry-run gates, opt-in flags, readback, and the audit log. Graph calls are stubbed.

set -eu

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../authorize-microsoft/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
M365_PYTHON="${M365_PYTHON:-python3}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/outlook-mail-filters-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
jq '(.accounts[] | .mail) = {enabled:true, write_enabled:false, rules_enabled:false}' "$SKILL/../authorize-microsoft/m365-accounts.example.json" > "$WORK/accounts.json"
M365_ACCOUNTS_PATH="$WORK/accounts.json"
export M365_ACCOUNTS_PATH

M365_MAIL_AUDIT_LOG="${WORK}/audit.jsonl"
export M365_MAIL_AUDIT_LOG

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
expect_fail() { if "$@" > "${WORK}/out.txt" 2> "${WORK}/err.txt"; then fail "expected failure: $*"; fi; }


##- Microsoft 365
jq '(.accounts[] | select(.alias == "example") | .mail.rules_enabled) = false' "${WORK}/accounts.json" > "${WORK}/m-off.json"
jq '(.accounts[] | select(.alias == "example") | .mail.rules_enabled) = true' "${WORK}/accounts.json" > "${WORK}/m-on.json"
M365_ACCOUNTS_PATH="${WORK}/m-off.json"
export M365_ACCOUNTS_PATH
if _m365_scopes example 2>/dev/null | grep -qx 'MailboxSettings.ReadWrite'; then fail "MailboxSettings requested without rules_enabled"; fi
M365_ACCOUNTS_PATH="${WORK}/m-on.json"
_m365_scopes example 2>/dev/null | grep -qx 'MailboxSettings.ReadWrite' || fail "MailboxSettings missing with rules_enabled"
M365_ACCOUNTS_PATH="${WORK}/m-off.json"

_m365_mail_folder_tree() {
    printf '%s\n' '[{"id":"f-inbox","displayName":"Inbox","path":"Inbox","wellKnown":"inbox","moveTarget":true},{"id":"f-arch","displayName":"Archive","path":"Archive","wellKnown":"archive","moveTarget":true},{"id":"f-del","displayName":"Deleted Items","path":"Deleted Items","wellKnown":"deleteditems","moveTarget":false}]' > "$2"
}
RULE_READBACK_PATCH='{}'
_m365_get() {
    case "$2" in
        */messageRules) printf '%s\n' '{"value":[{"id":"r-old","displayName":"Old","sequence":3,"isEnabled":true,"conditions":{"senderContains":["x"]},"actions":{"assignCategories":["work"]}}]}' ;;
        */messageRules/r-new) jq --argjson patch "$RULE_READBACK_PATCH" '. + {id:"r-new",hasError:false} + $patch' "${WORK}/created-rule.json" ;;
        *) return 1 ;;
    esac
}
_m365_write() { printf '%s %s %s\n' "$1" "$3" "$4" >> "${WORK}/m365-writes.log"; printf '%s\n' "$4" > "${WORK}/created-rule.json"; printf '%s\n' '{"id":"r-new"}'; }

out="$(_m365_mail_rules example)"
printf '%s\n' "$out" | grep -F -- "Old | rule_id: r-old | enabled | when: senderContains=x | then: category work" >/dev/null || fail "rule listing"

expect_fail _m365_mail_create_rule example --name X --category work
expect_fail _m365_mail_create_rule example --name X --sender-contains a
expect_fail _m365_mail_create_rule example --name Old --sender-contains a --category work
expect_fail _m365_mail_create_rule example --name X --sender-contains a --folder "Deleted Items"
expect_fail _m365_mail_create_rule example --name X --delete
expect_fail _m365_mail_create_rule example --name X --from newsletter@example.org --delete
expect_fail _m365_mail_create_rule example --name X --recipient-contains alias@example.org --delete
expect_fail _m365_mail_create_rule example --name X --from newsletter@example.org --recipient-contains example.org --delete
expect_fail _m365_mail_create_rule example --name X --from newsletter@example.org --recipient-contains alias@example.org --delete --folder archive
expect_fail _m365_mail_create_rule example --name X --from newsletter@example.org --recipient-contains alias@example.org --delete --category work
expect_fail _m365_mail_create_rule example --name X --from newsletter@example.org --recipient-contains alias@example.org --permanent-delete

out="$(_m365_mail_create_rule example --name Updates --sender-contains updates.example.org --category work --folder archive)"
printf '%s\n' "$out" | grep -F -- "DRY RUN: no rule was created" >/dev/null || fail "m365 dry run"
printf '%s\n' "$out" | grep -F -- "then: category work, move to Archive" >/dev/null || fail "m365 plan rendering"
[ ! -f "${WORK}/m365-writes.log" ] || fail "m365 dry run wrote"
expect_fail _m365_mail_create_rule example --name Updates --sender-contains updates.example.org --category work --folder archive --execute
[ ! -f "${WORK}/m365-writes.log" ] || fail "m365 write without rules_enabled"

M365_ACCOUNTS_PATH="${WORK}/m-on.json"
out="$(_m365_mail_create_rule example --name Updates --sender-contains updates.example.org --category work --folder archive --execute)"
printf '%s\n' "$out" | grep -F -- "Created rule (confirmed by readback): Updates | rule_id: r-new" >/dev/null || fail "m365 create"
grep -F -- '"sequence":4' "${WORK}/m365-writes.log" >/dev/null || fail "rule sequence"
jq -e 'select(.action == "create-rule") | .verified == true' "$M365_MAIL_AUDIT_LOG" >/dev/null || fail "m365 audit"

out="$(_m365_mail_create_rule example --name Duplicates --from newsletter@example.org --recipient-contains alias@example.org --delete --stop)"
printf '%s\n' "$out" | grep -F -- "recipientContains=alias@example.org" >/dev/null || fail "recipient plan rendering"
printf '%s\n' "$out" | grep -F -- "Delete means move to Outlook Deleted Items" >/dev/null || fail "delete semantics missing"
[ "$(wc -l < "${WORK}/m365-writes.log" | tr -d ' ')" = 1 ] || fail "delete dry run wrote"
out="$(_m365_mail_create_rule example --name Duplicates --from newsletter@example.org --recipient-contains alias@example.org --delete --stop --execute)"
jq -e '.conditions.fromAddresses == [{emailAddress:{address:"newsletter@example.org"}}] and .conditions.recipientContains == ["alias@example.org"] and .actions == {delete:true,stopProcessingRules:true}' "${WORK}/created-rule.json" >/dev/null || fail "duplicate rule scope or actions incorrect"

# A server response that drops or broadens a condition must never count as verified.
for RULE_READBACK_PATCH in \
    '{"conditions":{"fromAddresses":[{"emailAddress":{"address":"newsletter@example.org"}}]}}' \
    '{"conditions":{"fromAddresses":[{"emailAddress":{"address":"other@example.org"}}],"recipientContains":["alias@example.org"]}}' \
    '{"conditions":{"fromAddresses":[{"emailAddress":{"address":"newsletter@example.org"}}],"recipientContains":["other@example.org"]}}' \
    '{"actions":{"delete":true,"stopProcessingRules":true,"permanentDelete":true}}' \
    '{"actions":{"delete":true,"stopProcessingRules":true,"forwardAsAttachmentTo":[{"emailAddress":{"address":"other@example.org"}}]}}' \
    '{"actions":{"delete":false,"stopProcessingRules":true}}' \
    '{"actions":{"delete":true,"stopProcessingRules":false}}' \
    '{"exceptions":{"recipientContains":["alias@example.org"]}}' \
    '{"isEnabled":false}' \
    '{"hasError":true}'; do
    expect_fail _m365_mail_create_rule example --name Duplicates --from newsletter@example.org --recipient-contains alias@example.org --delete --stop --execute
done
RULE_READBACK_PATCH='{"conditions":{"fromAddresses":[{"emailAddress":{"name":"Newsletter","address":"NEWSLETTER@EXAMPLE.ORG"}}],"recipientContains":["ALIAS@EXAMPLE.ORG"],"sentToMe":false,"subjectContains":[]},"actions":{"delete":true,"stopProcessingRules":true,"permanentDelete":false,"forwardTo":[]}}'
out="$(_m365_mail_create_rule example --name Duplicates --from newsletter@example.org --recipient-contains alias@example.org --delete --stop --execute)"
printf '%s\n' "$out" | grep -F -- "Created rule (confirmed by readback): Duplicates" >/dev/null || fail "Graph default fields or case normalization rejected"

printf 'mail filter and rule tests passed\n'
