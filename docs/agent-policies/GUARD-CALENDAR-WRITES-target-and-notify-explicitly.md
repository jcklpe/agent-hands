---
id: GUARD-CALENDAR-WRITES
type: operational
scope: "Agent use or maintenance of Google Calendar writes and attendee resolution."
status: adopted
authority: "User's explicit Agent Hands policy-pilot approval, 2026-11-02; recorded in agent-policy-pilot."
revised: "2026-11-02"
depends_on: ["REJECT-GUESSES"]
related_to: ["BOUND-MICROSOFT-ACCESS"]
---
# Guard Google Calendar writes
Keep Google Calendar writes bounded by exact targets and effects. Preserve dry-run plans by default and require explicit execution. A write must target a configured writable calendar; reads may span configured read calendars. Do not expose or substitute event deletion.

Attendee addresses must be explicit and disambiguated; never guess an address from a nickname. Contacts can supply candidates, while private alias/nickname preferences stay with the consuming workspace. Apply REJECT-GUESSES to correctness-critical calendar, time-zone and attendee values.

Suppress attendee notifications by default (`sendUpdates=none`). Sending invitations or updates requires the explicit per-write notification option and actual caller authorization. An edit targets the selected occurrence unless series scope is explicitly chosen. Preserve existing attendees unless replacement is explicitly requested.

Keep Calendar event authorization separate from optional Contacts lookup. Select the Contacts capability before enabling its API/scopes, and use the setup owner only for separately approved reauthorization. Do not change grants merely to verify this policy migration. Contacts access can expose more than a single match; a bounded command is not proof of a narrow credential.

## Enforcement and procedures
[Calendar use](../../use-google-calendar/SKILL.md), [Contacts lookup](../../use-google-contacts/SKILL.md) and [Google setup](../../setup-google-services/SKILL.md) own commands and authorization mechanics. Their native scripts implement previews, allowlists, notification/series switches and exact addresses. The Microsoft notification model is separately bounded by [BOUND-MICROSOFT-ACCESS](BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md).

## Identity history
This obligation continues the reviewed legacy record [0002](../archive/agent-policy-retirements/0002-lifeos-calendar-writes.md), retired as an operative document during this authorized migration. Its source text and numeric identity remain reserved; the history link is not an override or automatic authority transfer.
