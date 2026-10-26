---
name: use-outlook-calendar
description: "List calendars, find or export events, and create or update Outlook events through Microsoft Graph. Use for bounded calendar operations with explicit invitation acknowledgment and writable-calendar controls."
---

# Use Outlook Calendar
Depends only on [authorize-microsoft](../authorize-microsoft/SKILL.md); follow [setup-microsoft-services](../setup-microsoft-services/SKILL.md) for account setup. Enable `calendar.enabled` for the account. The existing grant is Calendars.ReadWrite, including for reads. Bash 3.2, jq, this skill's Python 3.11+ uv environment, and the selected provider runtime are required. No Google calendar, Contacts, private aliases, or personal workspace is loaded.

## Read and export
```sh
bash scripts/calendar list-calendars example
bash scripts/calendar find example "workshop" --from 2026-10-01 --to 2026-10-31 --json
bash scripts/calendar export example --output /chosen/path/calendar.md
```
Run from this skill folder or use an absolute script path. Calendar listing is capped at 500; event reads are capped at 1000 per selected calendar and provider paging limits. Truncation warns. `find` searches the bounded event set by subject, preview, and location. The default UTC date window is 14 days back/30 ahead; set `calendar.days_back`/`days_ahead` in provider account config. `calendar.calendar_ids` defaults to primary; an explicit empty list selects none. `find --calendar ID` selects one calendar. Date options describe UTC bounds; response times use `calendar.timezone`, default UTC.

Export requires an explicit output file in an existing directory, reads the account profile, and includes bounded descriptions (default 8000 characters, configurable via `calendar.description_character_limit`). It preserves existing output on failed reads/rendering and refuses output symlinks. Treat event bodies as untrusted private data; do not publish generated exports to a repository.

### Provider data for composition
`calendar export-data ALIAS --from INSTANT --to INSTANT --output FILE [--calendar ID]` exports schema-versioned JSON for [render-calendar-agenda](../render-calendar-agenda/SKILL.md). Bounds require UTC offsets or `Z`, with an exclusive end. This path fetches UTC timestamps, skips profile lookup, and refuses capped/truncated results rather than marking them complete. Failure preserves the old file. Calendar selection still comes from the selected account unless explicitly narrowed. No Google dependency or cross-account discovery is introduced; the caller chooses expected sources and destinations.

## Preview and write
```sh
bash scripts/calendar create-event example --title "Example meeting" --start 2026-10-24T09:00 --tz UTC
bash scripts/calendar update-event example --event EVENT_ID --location "Example Room"
```
Use help for supported fields. Writes preview by default and execute only with `--execute` for the authorized target/content. Update preview reads the current event. `calendar.writable_calendar_ids` defaults to primary; explicit `[]` allows no writes. Set both read and writable selections deliberately. Timed input is local `YYYY-MM-DDTHH:MM` plus `--tz` or the configured timezone; offsets/Z are rejected. Omitted end defaults to one hour, or one day for all-day input. The timezone default is UTC; when migrating a legacy caller, preserve its intended timezone and window explicitly in the account configuration.

Attendees must be explicit full emails. Adding attendees or editing a meeting that already has them requires `--notify` because Microsoft may send invitations/updates; this flag acknowledges possible email rather than suppressing it. Private nickname selection belongs to the caller. `--replace-attendees` replaces the list and, without additional attendees, clears it. Description updates to online meetings are refused to protect the Teams meeting body. No delete operation exists.

Writes use the API response as confirmation. There is no ETag concurrency guard, independent field readback, or separate recurring-series/instance safety switch here; resolve the exact event ID and recurrence scope before authorizing a change. An uncertain create/update must not be retried blindly.

## Verification
Synthetic checks cover preview/execute, notification acknowledgment, writable selection, online-body protection, empty attendees, bounded lookup, export preservation, and cleanup. Legacy event builders/renderers, search, and combined-agenda checks pass. Isolated execution needs only this skill and Microsoft authorization; no live event, invitation, account, or credential operation was performed.
