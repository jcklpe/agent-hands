#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../authorize-microsoft/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/temp"
export M365_CONFIG_DIR="$WORK" TMPDIR="$WORK/temp"
M365_PYTHON="${M365_PYTHON:-python3}"
cp "$SKILL/../authorize-microsoft/m365-powershell-accounts.example.json" "$WORK/m365-accounts.json"
expect_failure() { if "$@" > "$WORK/out" 2> "$WORK/error"; then printf 'Unexpected success\n' >&2; exit 1; fi; }
_m365_get() { [ "${FAIL_READ:-0}" = 0 ] || return 1; case "$2" in */me) printf '%s' '{"mail":"person@example.com"}' ;; */contacts/contact-1) jq '.value[0]' "$SKILL/tests/fixtures/contacts.json" ;; *) cat "$SKILL/tests/fixtures/contacts.json" ;; esac; }
_m365_write() { printf '%s' "$4" > "$WORK/written.json"; jq '. + {id:"contact-1"}' "$WORK/written.json"; }
_m365_contacts_find example ADA --json > "$WORK/found.json"
jq -e '.value[0].id == "contact-1"' "$WORK/found.json" >/dev/null
_m365_contacts_find example ADA > "$WORK/human.txt"
grep -F "contact_id: contact-1" "$WORK/human.txt" >/dev/null
_m365_contacts_create example --display-name 'Example Person' > "$WORK/out"
grep -F 'DRY RUN' "$WORK/out" >/dev/null
[ ! -e "$WORK/written.json" ]
_m365_contacts_update example --contact contact-1 --notes '' > "$WORK/out"
[ ! -e "$WORK/written.json" ]
_m365_contacts_update example --contact contact-1 --notes '' --execute > "$WORK/out"
jq -e '.personalNotes == "" and (keys | length) == 1' "$WORK/written.json" >/dev/null
expect_failure _m365_contacts_create example
jq '.accounts[0].contacts.enabled=false' "$WORK/m365-accounts.json" > "$WORK/disabled.json"
M365_ACCOUNTS_PATH=disabled.json expect_failure _m365_contacts_create example --display-name 'Blocked' --execute
_m365_contacts_export example --output "$WORK/contacts.md" > "$WORK/out"
grep -F 'Ada Lovelace' "$WORK/contacts.md" >/dev/null
cp "$WORK/contacts.md" "$WORK/previous.md"
FAIL_READ=1 expect_failure _m365_contacts_export example --output "$WORK/contacts.md"
cmp "$WORK/previous.md" "$WORK/contacts.md"
ln -s "$WORK/contacts.md" "$WORK/link.md"
expect_failure _m365_contacts_export example --output "$WORK/link.md"
for residual in "$WORK/temp"/microsoft-work.* "$WORK"/.microsoft-output-*; do [ ! -e "$residual" ] || exit 1; done
printf '%s\n' 'Outlook Contacts read, render, write gates, empty fields, export preservation, and cleanup passed with synthetic data'
