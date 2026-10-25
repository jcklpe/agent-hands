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
jq '.accounts[0].calendar={enabled:true,timezone:"UTC",calendar_ids:["primary"],writable_calendar_ids:["primary"]}' "$SKILL/../authorize-microsoft/m365-powershell-accounts.example.json" > "$WORK/m365-accounts.json"
expect_failure() { if "$@" > "$WORK/out" 2> "$WORK/error"; then printf 'Unexpected success\n' >&2; exit 1; fi; }
_m365_get() {
    [ "${FAIL_READ:-0}" = 0 ] || return 1
    case "$2" in
        */me) printf '%s' '{"mail":"person@example.com"}' ;;
        */calendarView) jq '{value:.calendars[0].events}' "$SKILL/tests/fixtures/calendar.json" ;;
        */events/event-1) jq --argjson online "${ONLINE:-false}" '.calendars[0].events[0] + {isOnlineMeeting:$online}' "$SKILL/tests/fixtures/calendar.json" ;;
        */calendars) printf '%s' '{"value":[{"id":"calendar-1","name":"Calendar"}]}' ;;
        *) printf '%s' '{"id":"calendar-1","name":"Calendar"}' ;;
    esac
}
_m365_write() { printf '%s' "$4" > "$WORK/written.json"; printf '%s' '{"id":"event-1"}'; }
_m365_calendar_create example --title 'Example' --start 2026-10-24T09:00 > "$WORK/out"
grep -F 'DRY RUN' "$WORK/out" >/dev/null
[ ! -e "$WORK/written.json" ]
expect_failure _m365_calendar_create example --title Example --start 2026-10-24T09:00 --attendee person@example.com --execute
expect_failure _m365_calendar_create example --title Example --start 2026-10-24T09:00 --attendee nickname --notify
expect_failure _m365_calendar_update example --event event-1 --title Updated --execute
ONLINE=true expect_failure _m365_calendar_update example --event event-1 --desc replacement --notify --execute
jq '.accounts[0].calendar.writable_calendar_ids=[]' "$WORK/m365-accounts.json" > "$WORK/readonly.json"
M365_ACCOUNTS_PATH=readonly.json expect_failure _m365_calendar_create example --title Example --start 2026-10-24 --execute
[ ! -e "$WORK/written.json" ]
_m365_calendar_update example --event event-1 --replace-attendees --notify --execute > "$WORK/out"
jq -e '.attendees == [] and (keys | length) == 1' "$WORK/written.json" >/dev/null
_m365_calendar_find example workshop --json > "$WORK/found.json"
jq -e '.items[0].id == "event-1"' "$WORK/found.json" >/dev/null
_m365_calendar_export example --output "$WORK/calendar.md" > "$WORK/out"
grep -F 'Example workshop' "$WORK/calendar.md" >/dev/null
cp "$WORK/calendar.md" "$WORK/previous.md"
FAIL_READ=1 expect_failure _m365_calendar_export example --output "$WORK/calendar.md"
cmp "$WORK/calendar.md" "$WORK/previous.md"
_m365_calendar_export_data example --from 2030-01-01T00:00:00Z --to 2030-02-01T00:00:00Z --output "$WORK/microsoft.json" > /dev/null
jq -e '.schema_version == 1 and .provider == "microsoft" and .source == "example" and .complete == true and .timezone == "UTC"' "$WORK/microsoft.json" >/dev/null
cp "$WORK/microsoft.json" "$WORK/previous.json"
FAIL_READ=1 expect_failure _m365_calendar_export_data example --from 2030-01-01T00:00:00Z --to 2030-02-01T00:00:00Z --output "$WORK/microsoft.json"
cmp "$WORK/microsoft.json" "$WORK/previous.json"
# A full page with a next link is a failed complete export, not a fresh incomplete agenda.
_m365_get() {
    case "$2" in
        */calendarView) jq -n '{value: [range(1000) | {id:(tostring)}], "@odata.nextLink":"https://graph.microsoft.com/v1.0/me/calendar/calendarView?$skiptoken=example"}' ;;
        *) printf '%s' '{"id":"calendar-1","name":"Calendar"}' ;;
    esac
}
expect_failure _m365_calendar_export_data example --from 2030-01-01T00:00:00Z --to 2030-02-01T00:00:00Z --output "$WORK/microsoft.json"
cmp "$WORK/microsoft.json" "$WORK/previous.json"
grep -F 'complete export refused' "$WORK/error" >/dev/null
for residual in "$WORK/temp"/microsoft-work.* "$WORK"/.microsoft-output-*; do [ ! -e "$residual" ] || exit 1; done
printf '%s\n' 'Outlook Calendar preview, invitation, writable-calendar, Teams-body, empty-attendee, export, failure, and cleanup checks passed'
