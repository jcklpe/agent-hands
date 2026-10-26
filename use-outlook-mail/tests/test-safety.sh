#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../authorize-microsoft/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
M365_PYTHON="${M365_PYTHON:-python3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
refute() { if "$@"; then printf 'Expected failure\n' >&2; exit 1; fi; }
_m365_require_enabled() { :; }
_m365_mail_require_rules() { :; }
_m365_graph_base() { printf https://graph.microsoft.com/v1.0; }
_m365_profile_email() { printf person@example.com; }
_m365_account_value() { case "$2" in *max_results*) printf 150 ;; *body_character_limit*) printf 8000 ;; *days*) printf 30 ;; *) return 1 ;; esac; }
FAIL_READ=1
_m365_get_paginated() { [ "$FAIL_READ" = 0 ] || return 1; printf '{"value":[]}' > "$3"; }
printf previous > "$WORK/export.md"
refute _m365_mail_export example --output "$WORK/export.md" >/dev/null 2>&1
[ "$(cat "$WORK/export.md")" = previous ]
FAIL_READ=0
_m365_mail_export example --output "$WORK/export.md" >/dev/null 2>&1
grep -F 'No messages matched' "$WORK/export.md" >/dev/null
# An attachment's returned identity and bytes are validated before old files are replaced.
mkdir "$WORK/saved"
printf previous > "$WORK/saved/report.txt"
MODE=good
_m365_get() {
    case "$2" in
        */attachments)
            printf '{"value":[{"@odata.type":"#microsoft.graph.fileAttachment","id":"a1","name":"report.txt","isInline":false}]}' ;;
        */attachments/a1)
            [ "$MODE" != failed ] || return 1
            jq -nc --arg mode "$MODE" '{"@odata.type":"#microsoft.graph.fileAttachment",id:"a1",name:(if $mode == "renamed" then "../escape.txt" else "report.txt" end),isInline:false,contentBytes:(if $mode == "bad-bytes" then "!!!!" else "bmV3" end)}' ;;
        *) return 1 ;;
    esac
}
for MODE in failed renamed bad-bytes; do
    refute _m365_mail_attachments example --message m1 --save "$WORK/saved" --force >/dev/null 2>&1
    [ "$(cat "$WORK/saved/report.txt")" = previous ]
    [ ! -e "$WORK/escape.txt" ]
done
MODE=good
refute _m365_mail_attachments example --message m1 --save "$WORK/saved" >/dev/null 2>&1
_m365_mail_attachments example --message m1 --save "$WORK/saved" --force >/dev/null
[ "$(cat "$WORK/saved/report.txt")" = new ]
rm "$WORK/saved/report.txt"
ln -s "$WORK/export.md" "$WORK/saved/report.txt"
refute _m365_mail_attachments example --message m1 --save "$WORK/saved" --force >/dev/null 2>&1
# Failure reading rules after DELETE cannot be presented as confirmed deletion.
MODE=failed
_m365_get() {
    case "$2" in
        */messageRules/r1) printf '{"id":"r1","displayName":"Example","isEnabled":true}' ;;
        */messageRules)
            case "$MODE" in
                failed) return 1 ;;
                paged) printf '{"value":[],"@odata.nextLink":"https://graph.microsoft.com/v1.0/more"}' ;;
                present) printf '{"value":[{"id":"r1"}]}' ;;
                gone) printf '{"value":[]}' ;;
            esac ;;
        *) return 1 ;;
    esac
}
_m365_write() { printf '%s\n' "$1" >> "$WORK/writes"; }
_m365_mail_audit_append() { cat >> "$WORK/audit.jsonl"; }
for MODE in failed paged present; do
    refute _m365_mail_delete_rule example --rule r1 --execute >/dev/null 2>&1
    [ ! -e "$WORK/audit.jsonl" ]
done
MODE=gone
_m365_mail_delete_rule example --rule r1 --execute > "$WORK/result"
grep -F 'Deleted rule (confirmed)' "$WORK/result" >/dev/null
jq -e '.verified == true' "$WORK/audit.jsonl" >/dev/null
# Protected-folder identity failures and paged child folders must not yield writable targets.
_m365_get_paginated() { printf '{"value":[{"id":"f1","displayName":"Example","childFolderCount":1}]}' > "$3"; }
_m365_write() {
    printf '%s' "$4" | jq --arg mode "$MODE" '{responses:[.requests[] | {id:.id} + (if (.url | contains("childFolders")) then {status:200,body:({value:[]} + (if $mode == "paged-child" then {"@odata.nextLink":"https://graph.microsoft.com/v1.0/more"} else {} end))} else {status:(if $mode == "identity-failed" then 503 else 404 end),body:{}} end)]}'
}
for MODE in paged-child identity-failed; do
    refute _m365_mail_folder_tree example "$WORK/tree" >/dev/null 2>&1
done
MODE=good
_m365_mail_folder_tree example "$WORK/tree"
jq -e 'length == 1 and .[0].id == "f1"' "$WORK/tree" >/dev/null
printf 'Mail export, attachment, and delete-verification checks passed\n'
