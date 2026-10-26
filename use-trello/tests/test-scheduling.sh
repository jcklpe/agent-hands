#!/usr/bin/env bash
# Synthetic offline regression checks.
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
source "$SKILL/../authorize-trello/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
source "$SKILL/scripts/export.sh"
expect_failure() { if "$@" > "$WORK/out" 2> "$WORK/err"; then echo "unexpected success"; exit 1; fi; }
unset TRELLO_SNOOZE_DEFAULT_LIST TRELLO_SNOOZE_LISTS
_trello_write_ready() { return 0; }
_trello_resolve_list_id() { printf '%s\n' "$2" > "$WORK/chosen-list"; printf '%s' synthetic-list; }
_trello_write() { printf '%s\n' "$@" > "$WORK/write-args"; printf '%s' '{"id":"card-one","name":"Example"}'; }
expect_failure _trello_schedule_card --card card-one --until 2026-10-30
[ ! -e "$WORK/write-args" ]
grep -F 'requires --list' "$WORK/err" >/dev/null
_trello_schedule_card --card card-one --until 2026-10-30 --list 'Caller List' > /dev/null
[ "$(cat "$WORK/chosen-list")" = 'Caller List' ]
grep -F 'start=2026-10-30T12:00:00.000Z' "$WORK/write-args" >/dev/null
TRELLO_SNOOZE_DEFAULT_LIST='Configured List' _trello_schedule_card --card card-one --until 2026-10-30 > /dev/null
[ "$(cat "$WORK/chosen-list")" = 'Configured List' ]
[ -z "$(_trello_snooze_lists)" ]
[ "$(TRELLO_SNOOZE_LISTS='Caller List' _trello_snooze_lists)" = 'Caller List' ]
printf '%s\n' 'PASS: explicit scheduling and warning lists'
