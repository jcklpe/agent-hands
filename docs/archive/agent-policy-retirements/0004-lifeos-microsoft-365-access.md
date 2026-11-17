---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0004 policy history
Legacy identity: `0004`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [BOUND-MICROSOFT-ACCESS](../../agent-policies/BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0004-lifeos-microsoft-365-access.md`. Exact original SHA-256: `92e6cc40ad9f1b13a6ffd5be1967d7d7a4d9f211341340e7e0561e6924b9950e`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0004-microsoft-365-access"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="operating-notes"></a>
<a id="source-and-history"></a>
<a id="links"></a>

````text
# 0004 Microsoft 365 Access

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
Use the native Outlook Mail, Outlook Calendar, Outlook Contacts, Planner, Microsoft Files and Excel skills for delegated Microsoft Graph access through configured account aliases; `setup-microsoft-services` owns authentication.

The permission and capability boundary is:

- `User.Read` verifies the authenticated mailbox identity.
- `Mail.Read` supports bounded Inbox snapshots and on-demand folder listing, mailbox search, and full-message reads, including Archive and Sent Items. Mailbox-wide searches exclude Junk Email unless it is requested explicitly. Opt-in mail moves and categories use `Mail.ReadWrite`; [mail filing](0007-mail-archive-and-labels.md) owns those commands and spam/junk rescue. [Filters and Inbox rules](0009-mail-filters-and-rules.md) own standing automation and its narrow duplicate-mail exception. There is no one-off mail send, reply, forward, mark-read, or delete command.
- `Calendars.ReadWrite` supports bounded calendar views and event create/update. Writes are dry-run by default, require `--execute`, are restricted to configured writable calendar IDs, and expose no delete command.
- `Contacts.ReadWrite` supports the default Outlook Contacts folder plus contact create/update. Writes are dry-run by default, require `--execute`, require exact contact IDs for updates, and expose no delete command.
- [Planner access](0008-lifeos-m365-planner.md) and [file writes](0010-lifeos-m365-file-writes.md) have separate opt-in capability boundaries.

Use Microsoft's supported Graph PowerShell client as the default transport. Its effective context can contain a broader cumulative set of previously consented permissions than the scopes this command requests. The narrow command surface is a compensating control for potentially broader effective delegated grants; it is not a claim that a credential is least-privileged. Controls live in the narrow native capability surfaces: no generic Graph request or raw-token command, opt-in write capabilities, dry-run-gated execution, and bounded targets.

PowerShell owns its protected CurrentUser authentication cache. A dedicated public-client application through MSAL is an optional fallback when an application ID is approved. There is no client secret, unattended daemon, or app-only access. Real alias configuration and authentication caches are local-only; only fake examples and synthetic fixtures are tracked.

Microsoft 365 attendee-bearing event writes require `--notify` as acknowledgement that Microsoft may send invitations or meeting updates. This flag does not provide Google's server-side notification suppression. Bare attendee names resolve only through the deterministic local alias map; the tool does not search or guess from the institutional directory.

Service exports remain independent. Callers select aliases, domains, windows, and destinations explicitly; the legacy aggregate and combined-calendar sync commands are retired. Provider calendar data exports feed the neutral `render-calendar-agenda` skill. Private workspace procedures own combined agenda selection and snapshot destinations; the public tools do not decide which accounts matter for availability.

## Rationale
A consuming workspace selects its canonical mailbox and any forwarding/deduplication policy. The portable runtime supports delegated Microsoft Graph access without prescribing which personal or institutional account supplies planning context. The shared Graph PowerShell client provides a supported transport when direct application registration is unavailable.

## Operating Notes
- The consuming workspace owns mailbox selection, forwarding relationships and cross-provider deduplication.
- Calendar and contact write access is intentionally broader than read-only integration, but the CLI contains the blast radius through dry runs, explicit execution, allowlisted calendars, attendee acknowledgement, exact contact IDs, and the absence of delete commands.
- A shared Graph PowerShell client can have broader effective delegated grants than this command surface needs. The accepted mitigation is deliberately narrow, auditable native capability surfaces rather than abandoning the workable native CLI route.
- The initial contact surface covers only the default Outlook Contacts folder. Additional contact folders can be considered later if actual use demonstrates the need.
- The initial M365 calendar surface does not mutate recurring series as a unit and blocks description replacement on online meetings to avoid damaging embedded Teams meeting data.

## Source and History
[Microsoft 365 implementation](../archive/lifeos-m365.md) and [unified calendar implementation](../archive/unified-calendar.md) retain the development history. Current operational mechanics live in the [Microsoft 365 skill](../../setup-microsoft-services/SKILL.md) and [Outlook Calendar skill](../../use-outlook-calendar/SKILL.md).

## Links
- [setup-microsoft-services skill](../../setup-microsoft-services/SKILL.md)
- [Agent Hands README](../../README.md)
- [LifeOS Microsoft 365 spike](../archive/lifeos-m365.md)
- [Agent Hands secret handling](../../AGENTS.md#git-and-privacy)
- [0002 LifeOS Calendar Writes And Attendee Resolution](0002-lifeos-calendar-writes.md)
````
