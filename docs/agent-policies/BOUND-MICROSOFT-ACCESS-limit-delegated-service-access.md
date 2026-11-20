---
id: BOUND-MICROSOFT-ACCESS
type: operational
scope: "Agent use or maintenance of delegated Microsoft 365 service access."
status: adopted
authority: "User's Agent Hands policy-pilot approval, 2026-11-02; explicit approval of bounded manual-send Outlook reply drafts and saved-draft editing without broader access, 2026-11-17."
revised: "2026-11-17"
depends_on: ["REJECT-GUESSES"]
related_to: ["BOUND-MAIL-WRITES", "BOUND-MAIL-RULES", "GUARD-PLANNER-WRITES", "GUARD-FILE-WRITES"]
---
# Bound delegated Microsoft access
Use selected delegated account aliases and native service capabilities, with authentication owned by Microsoft setup. Verify the authenticated identity. Do not introduce a generic Graph-request/raw-token escape hatch, client secret, app-only access or unattended daemon. Keep real account configuration and authentication caches local and ignored; publish synthetic examples only. Graph PowerShell is the default transport, with an approved public-client/MSAL alternative when selected.

Effective grants may be broader than the current scope request because consent accumulates. Describe the deliberately narrow command surface as a compensating control, not a least-privileged credential. Apply REJECT-GUESSES to identity and correctness-critical target ambiguity; a missing grant does not authorize expanding it.

Bound mail reads to the selected query/folder/window; mailbox-wide search excludes Junk unless explicitly selected. Sending messages/replies/forwards, marking read and deleting remain outside the native mail surface. Explicitly authorized manual-send reply drafts and saved-draft body edits are bounded by BOUND-MAIL-WRITES; they never send or expand consent. Filing and standing rules have their own opt-ins and limits in [BOUND-MAIL-WRITES](BOUND-MAIL-WRITES-limit-reversible-filing.md) and [BOUND-MAIL-RULES](BOUND-MAIL-RULES-limit-standing-automation.md).

Calendar and default-folder contact writes retain preview-by-default, explicit execution, writable-calendar allowlists or exact contact IDs, and no deletion. Attendee-bearing Microsoft event writes require acknowledgement of possible invitations/meeting updates; this is not Google's server-side notification suppression. Bare attendee names resolve only through an explicit local alias map, not a guessed institutional-directory match. Do not mutate recurring series as a unit or replace online-meeting descriptions through a surface that refuses those operations.

Exports remain independently selected by account, service, window and explicit destination. Do not revive aggregate cross-service refresh or choose a consumer's canonical mailbox, forwarding, deduplication, agenda composition or snapshot layout. Planner and file mutations retain their separate opt-in boundaries.

## Enforcement and procedures
[Microsoft setup](../../setup-microsoft-services/SKILL.md), [Outlook mail](../../use-outlook-mail/SKILL.md), [Calendar](../../use-outlook-calendar/SKILL.md), [Contacts](../../use-outlook-contacts/SKILL.md), [Planner](../../use-planner/SKILL.md), [Files](../../use-microsoft-files/SKILL.md) and [Excel](../../use-excel-workbooks/SKILL.md) own their native operation/permission mechanics. A policy edit changes neither those tools nor existing provider consent.

## Identity history
This obligation continues the reviewed legacy record [0004](../archive/agent-policy-retirements/0004-lifeos-microsoft-365-access.md), retired as an operative document during this authorized migration. Its source text and numeric identity remain reserved; the history link is not an override or automatic authority transfer.
