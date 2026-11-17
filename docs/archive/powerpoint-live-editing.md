---
attention: historical
reviewed: 2026-11-17
tags: [microsoft, powerpoint, coauthoring]
---
# Headless PowerPoint live editing
Opened: 2026-11-16. Slug: `powerpoint-live-editing`. Closed: 2026-11-17.

Historical record. Current commands and safeguards belong to [PowerPoint Presentations](../../use-powerpoint-presentations/SKILL.md) and [provider setup](../../setup-microsoft-services/references/powerpoint-browser.md). Deferred validation is [tracked separately](../scratch/powerpoint-validation.md).

## Goal and authorized scope
Test reading and changing a disposable cloud presentation through an owned headless browser while another browser session has the presentation open. Reuse the accepted Word approach where it fits, preserve ordinary Chrome and its tabs, and independently verify that edits reach OneDrive. The user authorized promoting the verified probe into a reusable macOS-focused PowerPoint tool with automatic add-in setup and Word-equivalent safeguards. Live validation remains limited to disposable synthetic presentations using existing delegated access. Broader consent, edits to real work presentations and a standing worker are outside this implementation task. Closure and a scoped public push were authorized on 2026-11-17.

## Approach
The [accepted Word implementation](../archive/live-word-editing.md) supplies owned-profile lifecycle, native browser credential protection, account checks, loopback HTTPS and authenticated single-dispatch commands. Reuse those components without copying normal browser state or weakening Word's operation bounds. A separate experimental PowerPoint add-in must check the host and exact presentation before reading slide/shape identities or replacing an exact text range.

PowerPoint exposes slide shapes and text ranges through its JavaScript API, including substring edits. Its Presentation API does not expose Word's document save method. Treat context synchronization as a session result, then verify autosave through an independent Graph download before claiming persistence. Add-in startup, tenant availability, cloud persistence and concurrent visibility each need live evidence.

## Acceptance
- Create a disposable PPTX with synthetic ALPHA/BETA text and formatting/preservation controls, using existing Microsoft Files access.
- Open only the tool-owned browser for setup and all agent operations; leave normal Chrome untouched.
- Read the exact presentation's slide and shape text headlessly, with account and target checks.
- Change ALPHA through Office.js while a second browser session has the presentation open; verify independently downloaded cloud content and unchanged controls.
- Confirm the second editor sees ALPHA, then change BETA there and verify that both changes survive in a fresh headless read and cloud download.
- Record real limitations and clean up transient processes and sensitive local experiment artifacts. Keep any reusable source and sanitized findings with this spike.

## Reusable capability
The macOS experiment established headless setup, startup, bounded text editing and cloud persistence using the existing owned profile while the second browser editor remained open. A fresh headless process and independent cloud download contained both the agent's ALPHA edit and the browser's BETA edit. The agent-only save preserved all checked controls; the browser edit changed BETA's explicit font-run metadata, so the final deck is not claimed to be formatting-equivalent in every respect.

[PowerPoint Presentations](../../use-powerpoint-presentations/SKILL.md) now owns the reusable macOS tool. It targets one exact slide and top-level text-bearing shape per operation, with stored before/after previews, cloud baseline checks and durable single-dispatch receipts. [Provider setup](../../setup-microsoft-services/references/powerpoint-browser.md) automates installation/startup in the shared owned Office profile and independently verifies the persisted setting. The CLI provides headless reads/edits and cloud-only reconciliation. A two-slide disposable test established automatic preparation, repeat reuse without another setting save, fresh reads, exact targeting despite duplicate text on another slide, cloud persistence, stale-preview refusal and replay refusal. Same-shape races remain non-atomic and must never trigger an automatic retry. Windows/Linux and sustained-use validation remain deferred.

## Bounds
The initial fixture uses ordinary editable text-bearing shapes. Grouped shapes, charts, tables, slide masters, animations, notes, protected decks, simultaneous same-shape writes and general presentation authoring are not established by this test. No whole-file replacement is an automatic fallback for a locked/open presentation. Local synthetic tests do not establish tenant access or live coauthoring.

## Primary references
- [PowerPoint Presentation API](https://learn.microsoft.com/en-us/javascript/api/powerpoint/powerpoint.presentation?view=powerpoint-js-preview).
- [PowerPoint TextRange API](https://learn.microsoft.com/en-us/javascript/api/powerpoint/powerpoint.textrange?view=powerpoint-js-preview).
- [Automatic task-pane startup](https://learn.microsoft.com/en-us/office/dev/add-ins/develop/automatically-open-a-task-pane-with-a-document).

[Tasks and evidence](powerpoint-live-editing.todo.md).
