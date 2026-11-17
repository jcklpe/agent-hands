---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0002 policy history
Legacy identity: `0002`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [GUARD-CALENDAR-WRITES](../../agent-policies/GUARD-CALENDAR-WRITES-target-and-notify-explicitly.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0002-lifeos-calendar-writes.md`. Exact original SHA-256: `9d397f9923aa448f04acf3e55d95eeec5fccf410deed53e266d28306c7799e1c`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0002-google-calendar-writes-and-attendee-resolution"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="operating-notes"></a>
<a id="links"></a>

````text
# 0002 Google Calendar Writes And Attendee Resolution

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
The Google Calendar write surface is `bash use-google-calendar/scripts/calendar create-event ALIAS` and `update-event ALIAS`. Use `bash use-google-contacts/scripts/contacts resolve ALIAS NAME` for candidate lookup; the consuming workflow selects exact attendee addresses. Paths in this policy are relative to the Agent Hands root. The capability is real (guests and attendee-list edits included), but constrained by tool-enforced safety properties:

- **Dry-run by default; `--execute` to write.** Every write prints the full plan/diff and changes nothing without `--execute`. Execution remains separate from planning.
- **Writable-calendar allowlist.** Writes are rejected unless the target calendar is in the selected account’s `calendar.writable_ids`. Reads still span every configured read calendar; writes cannot touch a target absent from the writable list. There is no `delete-event`.
- **No attendee email-out by default.** `sendUpdates=none` unless `--notify` is passed. Adding an attendee with `--notify` sends a live invite — that is the real blast radius, so it is opt-in per write.
- **Recurring edits default to the single occurrence.** `update-event` edits only the passed instance; `--series` retargets the series master. Attendee edits merge into the existing list unless `--replace-attendees`.
- **Attendee resolution never guesses.** The native Calendar writer accepts explicit addresses. Consumers may resolve private nicknames or use Google Contacts candidate lookup, but must disambiguate before supplying attendee addresses. Nicknames and alias maintenance belong to the private workflow.

Calendar writes request `calendar.events`; separately selected Contacts lookup requests `contacts.readonly` and `contacts.other.readonly`. Use the provider’s `authorize` entrypoint for any separately approved reauthorization and enable the People API only if the Contacts capability is selected. Do not reauthorize merely for migration verification.

## Rationale
Creating and editing events, including invitations, is useful enough to justify a real write surface. Tool-enforced calendar limits, notification acknowledgement, exact attendee resolution, and explicit recurring-series targeting bound its effects. The allowlist supports the permitted calendars without requiring a separate reminders calendar.

## Operating Notes
- Callers can schedule and adjust events and invite people through the bounded native capability.
- Blast radius is now real but bounded: the worst unattended action is creating/editing an event on an allowlisted calendar without notifying anyone. Emailing real people requires an explicit `--notify`, and editing a whole recurring series requires an explicit `--series`.
- Contacts access is broader than strictly needed (the People API can read all contacts). Private workflow nicknames can avoid repeated ambiguous contact lookup, but the tool still receives explicit addresses.
- Private nickname preferences travel only with their consuming workspace; the public tool neither distributes nor edits a personal alias map.

## Links
- [Google Calendar skill](../../use-google-calendar/SKILL.md) — operational guidance and the disambiguation flow.
- [Agent Hands README](../../README.md)
- [Agent Hands secret handling](../../AGENTS.md#git-and-privacy) — ignored real files and synthetic examples.
- [lifeos-tools-v2 archive](../archive/lifeos-tools-v2.md) — superseded Calendar V2 ideas.
- Implementation: `use-google-calendar/scripts/`, `use-google-contacts/scripts/`, and `setup-google-services/scripts/`.
````
