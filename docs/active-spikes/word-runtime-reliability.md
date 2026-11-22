---
attention: live
reviewed: 2026-11-22
tags: [microsoft, word, reliability]
---
# Sustained Word runtime reliability
Opened: 2026-11-16. Slug: `word-runtime-reliability`.

Continues from: docs/archive/live-word-editing.md

The user accepts the tested macOS route and wants sustained-use validation tracked separately from the completed implementation. This follow-up collects evidence during authorized use; it does not schedule a worker, keep Word open, expand account permissions or start a new live test campaign. [Tasks](word-runtime-reliability.todo.md).

## Maintained owners and baseline
[Word Documents](../../use-word-documents/SKILL.md) owns supported operations and limits. [Word browser setup](../../setup-microsoft-services/references/word-browser.md) owns account sign-in, private state, automatic document preparation and recovery. The accepted macOS baseline includes headless preparation/read/edit/save, different-paragraph two-way coauthoring, independent cloud verification, stale-preview refusal, reconciliation after lost save acknowledgment, and normal MFA recovery after simulated local session loss. Normal Chrome is independent.

The same-range race remains a known limitation: simultaneous replacements can mix text despite successful Word save returns. Verification detected the observed mixture; it is not atomic prevention or automatic repair. Abrupt process death can require deliberate stale-lock handling after the owned processes stop. The bridge certificate expires after one year. Setup provides explicit, lock-guarded validity renewal that preserves the existing key and authentication; key rotation and automatic stale-lock reclamation are not implemented.

## Follow-up boundaries
Track repeat startup and shutdown, tenant-triggered sign-in expiry, localized or changed setup controls, additional interruption timings and operational recovery. Any new live mutation still needs an authorized target and operation. Keep public evidence to versions, bounded scenarios and outcomes; private profiles, identifiers, document text and diagnostics retain their existing private owners. Do not copy or inspect normal browser state to diagnose an owned-profile failure.

Windows/Linux validation is [parked until relevant](../scratch/word-windows-linux-validation.md). Direct coauthoring-protocol clients, WordCraft cloud integration and broad document-structure editing are outside this follow-up unless separately selected.

## Closure disposition — 2026-11-22
The user authorized closure of the bounded macOS reliability work. Remaining sustained-use observations, actual tenant-triggered expiry and arbitrary live network failures are documented limitations, not unfinished implementation gates. Future concrete failures should open a focused spike with reproduction evidence. No recurring observation worker is scheduled. Windows/Linux remain parked, and manual stale-lock recovery and same-range coauthoring risks remain in the maintained setup/use guidance. Archival awaits review of the complete closing message.
