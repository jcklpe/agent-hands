# Agent Hands policy index
This is the project-owned agent-policy set. The user authorized kernel adoption and migration of the eight inherited service policies in the Agent Hands pilot on 2026-11-02. Only adopted current-format records govern agents; human governance and actual service permissions remain separate. Kernel/operational types and kernel underscore filenames identify role/presentation, never precedence.

The [pilot task record](../archive/agent-policy-pilot.todo.md) records identity mapping, actual dependency reasons, semantic/privacy review and limits. Bundled Project Workflows candidates remain proposed and are not substituted automatically on update.

<!-- agent-policies:start -->
| ID | Policy | Type | Scope | Status | Revised |
| --- | --- | --- | --- | --- | --- |
| ADOPT-POLICIES | [Adopt agent policies explicitly](_ADOPT-POLICIES-require-explicit-adoption.md) | kernel | Agent treatment of policy obligations, skill procedures and local policy decisions. | adopted | 2026-11-02 |
| PRESERVE-IDENTITY | [Preserve obligation identity](_PRESERVE-IDENTITY-retain-meaning-and-history.md) | kernel | Agent continuity, dependency impact and retirement of policy identities. | adopted | 2026-11-02 |
| RESOLVE-DEPENDENCIES | [Resolve prerequisites before loading](_RESOLVE-DEPENDENCIES-load-prerequisites-once.md) | kernel | Agent discovery and loading of applicable adopted policy prerequisites. | adopted | 2026-11-02 |
| BOUND-MAIL-RULES | [Bound standing mail automation](BOUND-MAIL-RULES-limit-standing-automation.md) | operational | Agent use or maintenance of Gmail filters and Outlook Inbox rules. | adopted | 2026-11-02 |
| BOUND-MAIL-WRITES | [Bound one-off mail writes](BOUND-MAIL-WRITES-limit-reversible-filing.md) | operational | Agent use or maintenance of one-off mail filing/metadata changes, manual-send Gmail drafts, Outlook reply drafts and saved-draft body edits. | adopted | 2026-11-17 |
| BOUND-MICROSOFT-ACCESS | [Bound delegated Microsoft access](BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md) | operational | Agent use or maintenance of delegated Microsoft 365 service access. | adopted | 2026-11-17 |
| GUARD-CALENDAR-WRITES | [Guard Google Calendar writes](GUARD-CALENDAR-WRITES-target-and-notify-explicitly.md) | operational | Agent use or maintenance of Google Calendar writes and attendee resolution. | adopted | 2026-11-02 |
| GUARD-FILE-WRITES | [Guard Microsoft file writes](GUARD-FILE-WRITES-preserve-explicit-file-targets.md) | operational | Agent use or maintenance of Microsoft Files transfers, folders and bounded organization. | adopted | 2026-11-17 |
| GUARD-PLANNER-WRITES | [Guard Planner changes](GUARD-PLANNER-WRITES-preserve-bounded-task-changes.md) | operational | Agent use or maintenance of opted-in Planner tasks, labels, messages and moves. | adopted | 2026-11-18 |
| KEEP-DOCS-PORTABLE | [Keep document tooling portable](KEEP-DOCS-PORTABLE-separate-tools-from-domain-rules.md) | operational | Agent maintenance and use of general Google Docs capabilities. | adopted | 2026-11-02 |
| REJECT-GUESSES | [Reject correctness-critical guesses](REJECT-GUESSES-stop-writes-with-unknown-critical-values.md) | operational | Agent construction and implementation of correctness-critical native capability writes. | adopted | 2026-11-02 |
<!-- agent-policies:end -->

## Retired legacy identities
These literal numeric identities remain reserved in historical retirement records under `docs/archive/agent-policy-retirements/`; original source paths remain recorded as provenance. They are not current-format graph nodes or adopted prerequisites. Human review covers this retirement mapping/content; the checker verifies reachable links but does not claim to validate a legacy record's meaning or status.

| Legacy ID | Historical record | Scope | Status | Retired |
| --- | --- | --- | --- | --- |
| 0002 | [Retain 0002 history](../archive/agent-policy-retirements/0002-lifeos-calendar-writes.md) | Agent use or maintenance of Google Calendar writes and attendee resolution. | retired | 2026-11-02 |
| 0004 | [Retain 0004 history](../archive/agent-policy-retirements/0004-lifeos-microsoft-365-access.md) | Agent use or maintenance of delegated Microsoft 365 service access. | retired | 2026-11-02 |
| 0005 | [Retain 0005 history](../archive/agent-policy-retirements/0005-docs-editing-in-lifeos-tools.md) | Agent maintenance and use of general Google Docs capabilities. | retired | 2026-11-02 |
| 0006 | [Retain 0006 history](../archive/agent-policy-retirements/0006-writes-fail-rather-than-guess.md) | Agent construction and implementation of correctness-critical native capability writes. | retired | 2026-11-02 |
| 0007 | [Retain 0007 history](../archive/agent-policy-retirements/0007-mail-archive-and-labels.md) | Agent use or maintenance of one-off Gmail and Outlook filing/metadata changes. | retired | 2026-11-02 |
| 0008 | [Retain 0008 history](../archive/agent-policy-retirements/0008-lifeos-m365-planner.md) | Agent use or maintenance of opted-in Planner tasks, labels, messages and moves. | retired | 2026-11-02 |
| 0009 | [Retain 0009 history](../archive/agent-policy-retirements/0009-mail-filters-and-rules.md) | Agent use or maintenance of Gmail filters and Outlook Inbox rules. | retired | 2026-11-02 |
| 0010 | [Retain 0010 history](../archive/agent-policy-retirements/0010-lifeos-m365-file-writes.md) | Agent use or maintenance of Microsoft Files uploads, replacements and folders. | retired | 2026-11-02 |
