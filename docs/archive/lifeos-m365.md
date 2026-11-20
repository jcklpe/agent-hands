---
attention: historical
---
# LifeOS Microsoft 365

Privacy separation (2026-11-02): consumer-specific passages and actual account-validation chronology were preserved privately before removal from this public record. Portable requirements, recorded tooling evidence and stable slugs remain; historical instructions below are not current operating guidance.

Migration note (2026-10-30): moved from `configs/docs/archive/lifeos-m365.md` into Agent Hands as historical service-tooling context. Original body and task states are retained apart from navigation repairs. Old LifeOS commands, paths and account observations are not current Agent Hands instructions. The original Git history stays in the configs repository; stable slugs are unchanged. Current capabilities are documented in the [Agent Hands README](../../README.md).

Status: archived 2026-07-29. QA completed and the spike is closed.

This spike is now archived. The implementation and QA are complete, and the durable decision and implementation history live in this archive plus the decision record at `docs/policies/0004-lifeos-microsoft-365-access.md`.

Durable access and write-safety decision: `docs/policies/0004-lifeos-microsoft-365-access.md`.

## Purpose
Add bounded Microsoft Graph mail, calendar and Outlook contact capabilities for explicit caller-selected accounts, without prescribing which mailbox is canonical to a consumer.

The consumer needed one chosen mailbox as its canonical source. Its account forwarding arrangement is outside the reusable tool contract.

## Scope
- Mail is read-only: bounded Inbox snapshots, never send, reply, forward, move, mark read, archive, or delete.
- Calendar is read/write: list calendars, sync a bounded calendar view, find events, create events, and update events.
- Contacts are read/write for the signed-in user's default Outlook Contacts folder: list/find/sync contacts, create contacts, and update contacts.
- Authentication is delegated access as the signed-in user through Microsoft Graph PowerShell. There is no client secret or app-only access.

LifeOS asks for Microsoft Graph's `Mail.Read`, `Calendars.ReadWrite`, `Contacts.ReadWrite`, and `User.Read` delegated permissions. The narrower command surface—not the shared client's cumulative effective scope set—is the practical capability boundary for this account.

## Transport rationale
The historical implementation used Microsoft’s maintained Graph PowerShell public client when direct app registration was unavailable to the tested account. This is an account-specific constraint, not a tenant-wide guarantee. Effective delegated grants can be cumulative and broader than a narrow command’s requested scopes; the portable capability therefore documents its bounded command surface and verifies account identity. Actual registration, consent and client-install observations are retained privately.

## Safety Model
All calendar and contact writes are dry-run by default and require `--execute`. Neither surface exposes delete commands.

Calendar writes are restricted to configured writable calendar IDs. The default calendar may be represented by the stable `primary` alias. Creating or updating an event with attendees can send invitations or meeting updates; attendee-bearing writes therefore require an explicit `--notify` acknowledgement, and the plan must show every resolved address before execution.

Contact writes affect only the signed-in user's default Outlook Contacts folder, not the institutional directory. Contact identity resolution must never guess: updates require an exact Graph contact ID, while creates require explicit field values. There is no organization-directory write scope.

Mail, calendar, contact, and profile data are private. Real account configuration and token caches stay in ignored `lifeos-tools/secrets/` files. The public repo contains only fake examples and synthetic fixtures.

## Command Shape
The intended surface is an `m365` command group so Microsoft services remain distinct from the existing Google-specific commands:

```text
lifeos m365 accounts
lifeos m365 auth ALIAS [--no-browser]
lifeos m365 profile ALIAS
lifeos m365 mail sync ALIAS [--qa | --output FILE]
lifeos m365 calendar list-calendars ALIAS
lifeos m365 calendar find ALIAS QUERY [--from DATE] [--to DATE] [--calendar ID] [--json]
lifeos m365 calendar sync ALIAS [--qa | --output FILE]
lifeos m365 calendar create-event ALIAS ... [--notify] [--execute]
lifeos m365 calendar update-event ALIAS --event ID ... [--notify] [--execute]
lifeos m365 contacts list ALIAS [--json]
lifeos m365 contacts find ALIAS QUERY [--json]
lifeos m365 contacts sync ALIAS [--qa | --output FILE]
lifeos m365 contacts create ALIAS ... [--execute]
lifeos m365 contacts update ALIAS --contact ID ... [--execute]
```

Generated snapshots belong under `sources/m365/`, with an index that identifies the account alias and verified Graph profile. Initial sync stays explicit rather than silently expanding the aggregate `lifeos sync` command.

## Authentication And Portability
Use Microsoft's supported Graph PowerShell authentication module rather than maintaining a second hand-written OAuth implementation. The default path opens the system browser, while `--no-browser` uses device-code authentication. PowerShell owns its protected CurrentUser authentication cache; LifeOS does not print raw tokens.

The ignored account config makes the auth provider, tenant, service enablement, query bounds, and writable calendar IDs explicit. `lifeos doctor` reports provider readiness without reading or printing authentication contents. A custom-client MSAL provider remains available if a dedicated client ID is approved later.

## Bounded Data Model
Mail follows the existing Gmail limits unless live use demonstrates a reason to diverge: Inbox only, 30 days, at most 150 messages, and at most 8,000 body characters per message.

Calendar follows the existing LifeOS date window and uses Graph calendar views so recurring occurrences and exceptions appear in the requested range. Calendar descriptions are bounded and HTML is cleaned before Markdown rendering.

Contacts sync is capped and contains stable contact IDs plus selected personal fields needed for retrieval and update. It does not recurse through additional contact folders, ingest the managed tenant organization directory, infer people, or derive relationship data from communications.

## Non-Goals
- Sending or mutating mail.
- Deleting calendar events, calendars, contacts, or contact folders.
- Writing the managed tenant directory records or reading the full the managed tenant directory.
- Teams, SharePoint, OneDrive, tasks, or group calendars.
- Background daemons, webhooks, subscriptions, or unattended app-only access.
- Automatic cross-provider deduplication or merging M365 calendar events into the Google Calendar snapshot during this spike.

## Validation
Offline tests use synthetic Graph responses and pure rendering/body-building helpers. Live QA starts in `lifeos-tools/qa/`, verifies the signed-in profile before any write, tests read surfaces first, and uses disposable events/contacts for explicit user-approved write tests. No live snapshot or token is committed.

Historical bounded mail, calendar and default-contact read checks and create previews were recorded. Account-specific execution chronology is retained privately. Later approved write QA and closure are recorded in the companion; this original preview milestone does not establish present account health.

## Sources
- [Microsoft identity platform authentication flows](https://learn.microsoft.com/en-us/entra/identity-platform/authentication-flows-app-scenarios)
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)
- [List messages](https://learn.microsoft.com/en-us/graph/api/mailfolder-list-messages?view=graph-rest-1.0)
- [List a calendar view](https://learn.microsoft.com/en-us/graph/api/user-list-calendarview?view=graph-rest-1.0)
- [Create an event](https://learn.microsoft.com/en-us/graph/api/calendar-post-events?view=graph-rest-1.0)
- [Update an event](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0)
- [List contacts](https://learn.microsoft.com/en-us/graph/api/user-list-contacts?view=graph-rest-1.0)
- [Create a contact](https://learn.microsoft.com/en-us/graph/api/contactfolder-post-contacts?view=graph-rest-1.0)
- [Update a contact](https://learn.microsoft.com/en-us/graph/api/contact-update?view=graph-rest-1.0)
