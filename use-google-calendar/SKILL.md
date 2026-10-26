---
name: use-google-calendar
description: "List Google calendars, find events, export a bounded agenda, or create and update events with explicit calendar and notification controls. Use for Google Calendar operations through a configured account."
---

# Use Google Calendar
Depends on [setup-google-services](../setup-google-services/SKILL.md); Markdown exports also use [render-calendar-agenda](../render-calendar-agenda/SKILL.md), a standard-library-only renderer. Data exports and API operations do not load the renderer. Start with [setup-google-services](../setup-google-services/SKILL.md) when needed. Requires Bash 3.2+, curl, jq, and uv or Python 3.11+ with timezone data; Python uses the standard library and a capability-local manifest/lock. There is no Microsoft, contact-lookup, or workspace dependency.

## Configuration
Enable `calendar.enabled` on the selected Google account. This requests calendar-list and event reads; `calendar.write_enabled` additionally requests event writes. Separate `calendar.writable_ids` restricts writable targets; an omitted list permits none. The example lists `primary` but leaves writes disabled. `calendar.read_ids` defaults to `["primary"]`. Account settings are ignored private JSON beside authorization; do not copy another user's calendars or tokens.

## Read and export
```sh
bash scripts/calendar list-calendars example
bash scripts/calendar find example 'Example meeting' --from 2030-01-01 --to 2030-01-31 --json
bash scripts/calendar export example --from 2030-01-01 --to 2030-01-31 --output /tmp/agenda.md
```
Run from this skill folder or use an absolute path. `find` returns update-ready IDs, up to 50 matching expanded events per calendar, with a warning if more exist. Date filters use UTC day boundaries. With no filters, the window defaults to 14 days back and 30 ahead (`calendar.days_back`, `calendar.days_ahead`). `--calendar ID` narrows the selected calendar; otherwise configured read IDs are used.

Export requires an explicit output, fetches every event page in the selected window, and stages retrieval/rendering before replacing it. Calendar lists and exports are capped at 40 pages per calendar (`calendar.max_pages`); a failed or capped read fails without replacing the previous export. The aggregate renderer labels calendars, retains multi-day/cross-midnight events, and merges shared-UID duplicates. `calendar.no_description` optionally omits descriptions for selected calendar summaries; it is not a general privacy filter. Exports contain private event details and need an appropriate destination.

For compact planning output, add `--compact --start-at INSTANT --tz IANA_ZONE`. The explicit instant is a lower boundary within the fetched window: timed events starting earlier are omitted, and all-day events on the boundary's local date remain excluded for compatibility with adjacent detailed agendas. Recurring series of three or more occurrences collapse into summaries, with moved occurrences retained separately. Compact output omits descriptions, links, and locations. Automatic near/long-horizon file splitting and combined-provider agendas belong to the caller.

### Provider data for composition
`calendar export-data ALIAS --from INSTANT --to INSTANT --output FILE [--calendar ID]` exports one complete schema-versioned JSON bundle in an existing directory. Bounds require explicit UTC offsets or `Z`; `--to` is exclusive, unlike the date-only Markdown export. It uses the same complete paging and failure-preservation controls. The bundle includes provider/source identity and the fetched window. No Microsoft account is discovered or loaded. Pass the bundle to `render-calendar-agenda` with the full expected source list; private workflows choose the calendars, windows, and destinations.

## Create and update
```sh
bash scripts/calendar create-event example --title 'Example meeting' --start 2030-01-02T09:00 --tz Etc/UTC --attendee person@example.com
bash scripts/calendar update-event example --event EVENT_ID --location 'Example room'
bash scripts/calendar update-event example --event INSTANCE_ID --series --transparency transparent --popup-minutes 0
```
These preview by default. `--execute` requires the configured write opt-in and a writable calendar; it does not substitute for the user's authorization. `--notify` changes `sendUpdates` from `none` to `all`, so use it only when attendee notifications are intended. No delete operation or generic API escape hatch is exposed.

Times accept `YYYY-MM-DD` for all-day events or `YYYY-MM-DDTHH:MM` for timed events. Missing end defaults to one day (exclusive all-day end) or one hour. Timed events use `--tz` or a successfully read target calendar zone; failed lookup stops rather than guessing. Attendees must be explicit email addresses. Resolve names separately and confirm the exact addresses; no private nickname map or automatic contact selection is loaded.

Update merges attendees by default. `--replace-attendees` replaces the array, including clearing it when no attendees are supplied. An instance ID edits that occurrence; `--series` retargets its recurring master. Recurrence edits require `--series`; creating recurrence accepts repeatable `--recurrence` rules. `--desc`, `--desc-file`, `--location`, `--title`, and time options supply the other supported fields; see script help.

`--transparency transparent|opaque` selects Free/Busy. `--popup-minutes 0..40320` replaces reminders with one popup override. Omission preserves the create default or existing update setting. Explicit transparency/reminder writes read back those settings; verification failure is reported as `PARTIAL` after an accepted write. Do not recreate an event automatically after an uncertain response. Other fields rely on the API response rather than full independent verification. Updates do not use an ETag precondition, so concurrent edits are not a transaction. A saved popup preference does not prove a device displayed it.

## Offline checks
`tests/test_settings.py` retains event-body, preview, recurrence-targeting, notification, and partial-readback checks. `tests/test-render.sh` retains synthetic rendering fixtures. `tests/test-routing.sh` checks provider scopes, paged calendar lists, failed-export preservation, writable IDs, explicit emails, missing timezone behavior, execution opt-in, and temporary cleanup. No live account, invitation, or event mutation is needed.
