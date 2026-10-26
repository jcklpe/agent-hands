#!/usr/bin/env bash
set -eu
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SKILL/../setup-google-services/scripts/client.sh"
source "$SKILL/scripts/operations.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/temp"
export GOOGLE_PYTHON="${GOOGLE_PYTHON:-python3}" GOOGLE_CONFIG_DIR="$WORK" TMPDIR="$WORK/temp"
GOOGLE_CALENDAR_ALIAS=example
jq '.accounts[0].docs.enabled=false | .accounts[0].calendar.enabled=true | .accounts[0].calendar.max_pages=2' "$GOOGLE_AUTH_DIR/google-accounts.example.json" > "$WORK/google-accounts.json"
expect_failure() { if "$@" > "$WORK/out" 2> "$WORK/error"; then printf 'Unexpected success\n' >&2; exit 1; fi; }
_google_account_scopes example > "$WORK/scopes"
grep -Fx 'https://www.googleapis.com/auth/calendar.events.readonly' "$WORK/scopes" >/dev/null
[ "$(wc -l < "$WORK/scopes" | tr -d ' ')" = 2 ]
_calendar_get() {
    case "$1" in
        /users/me/calendarList)
            if [ "${FAIL_LIST:-0}" = 1 ]; then return 1; fi
            case "$*" in *pageToken=second*) printf '%s' '{"items":[{"id":"other","summary":"Other"}]}' ;; *) printf '%s' '{"items":[{"id":"primary","primary":true,"summary":"Example","timeZone":"Etc/UTC"}],"nextPageToken":"second"}' ;; esac ;;
        */events)
            [ "${FAIL_EVENTS:-0}" = 0 ] || return 1
            if [ "${RUNAWAY:-0}" = 1 ]; then printf '%s' '{"items":[],"nextPageToken":"again"}'
            elif [ "${INVALID_EVENTS:-0}" = 1 ]; then printf '%s' '{"error":{"message":"Synthetic error"}}'
            else printf '%s' '{"items":[{"id":"example-event","summary":"Example event","start":{"dateTime":"2030-01-02T09:00:00Z"},"end":{"dateTime":"2030-01-02T10:00:00Z"}}]}'
            fi ;;
        */events/*) printf '%s' '{"id":"example-event","summary":"Example event","start":{"date":"2030-01-02"},"end":{"date":"2030-01-03"}}' ;;
        *) return 1 ;;
    esac
}
_calendar_list_calendars > "$WORK/list"
grep -F 'Other' "$WORK/list" >/dev/null
printf 'previous' > "$WORK/calendar.md"
FAIL_EVENTS=1 expect_failure _calendar_export --output "$WORK/calendar.md"
[ "$(cat "$WORK/calendar.md")" = previous ]
INVALID_EVENTS=1 expect_failure _calendar_export --output "$WORK/calendar.md"
[ "$(cat "$WORK/calendar.md")" = previous ]
RUNAWAY=1 expect_failure _calendar_export --output "$WORK/calendar.md"
[ "$(cat "$WORK/calendar.md")" = previous ]
FAIL_LIST=1 expect_failure _calendar_export --output "$WORK/calendar.md"
[ "$(cat "$WORK/calendar.md")" = previous ]
_calendar_export --from 2030-01-01 --to 2030-01-03 --output "$WORK/calendar.md" > /dev/null
grep -F 'Example event' "$WORK/calendar.md" >/dev/null
expect_failure _calendar_export --from 2030-02-10 --to 2030-01-01 --output "$WORK/calendar.md"
expect_failure _calendar_create_event --calendar other --title Example --start 2030-01-02
expect_failure _calendar_create_event --title Example --start 2030-01-02 --attendee UnresolvedName
expect_failure _calendar_create_event --title Example --start 2030-01-02T09:00
# Failed metadata must not guess a time zone. A deliberate zone permits preview.
_calendar_create_event --title Example --start 2030-01-02T09:00 --tz Etc/UTC --attendee person@example.com > "$WORK/preview"
grep -F 'DRY RUN' "$WORK/preview" >/dev/null
_google_access_token() { printf synthetic-token; }
curl() { printf '%s\n' "$*" >> "$WORK/transport"; printf '%s' '{"id":"example-event"}'; }
expect_failure _calendar_create_event --title Example --start 2030-01-02 --execute
[ ! -e "$WORK/transport" ]
jq '.accounts[0].calendar.write_enabled=true' "$WORK/google-accounts.json" > "$WORK/enabled.json"
GOOGLE_ACCOUNTS_PATH=enabled.json _calendar_create_event --title Example --start 2030-01-02 --execute > /dev/null
grep -F 'sendUpdates=none' "$WORK/transport" >/dev/null
GOOGLE_ACCOUNTS_PATH=enabled.json _google_account_scopes example > "$WORK/scopes"
grep -Fx 'https://www.googleapis.com/auth/calendar.events' "$WORK/scopes" >/dev/null
_calendar_export --data --from 2030-01-01T00:00:00Z --to 2030-02-01T00:00:00Z --output "$WORK/google.json" > /dev/null
jq -e '.schema_version == 1 and .provider == "google" and .source == "example" and .complete == true and .calendars[0].events.items[0].id == "example-event"' "$WORK/google.json" >/dev/null
cp "$WORK/google.json" "$WORK/previous.json"
RUNAWAY=1 expect_failure _calendar_export --data --from 2030-01-01T00:00:00Z --to 2030-02-01T00:00:00Z --output "$WORK/google.json"
cmp "$WORK/google.json" "$WORK/previous.json"
expect_failure _calendar_export --data --from 2030-01-01 --to 2030-02-01 --output "$WORK/google.json"
for residual in "$WORK/temp"/google-calendar.* "$WORK"/.google-output-*; do [ ! -e "$residual" ] || exit 1; done
printf '%s\n' 'Calendar scopes, paging, export preservation, write gates, and cleanup passed'
