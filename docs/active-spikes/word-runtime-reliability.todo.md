---
attention: live
reviewed: 2026-11-20
tags: [microsoft, word, reliability]
---
# Sustained Word runtime reliability tasks
Opened: 2026-11-16. Slug: `word-runtime-reliability`. [Scope and baseline](word-runtime-reliability.md).

## Current state
The authorized macOS runtime repair and disposable read/edit/save verification passed. PowerShell uses isolated process caches while retaining existing authentication. Word setup recognizes an authenticated pane opened by upload even when its ribbon command has not appeared. Preparation reused the cloud startup setting; a fresh read, one text edit, independent cloud verification and another fresh read preserved all other paragraphs. No normal browser session was operated. Ongoing reliability and tenant-expiry observations remain open. Operational guidance remains in [Word Documents](../../use-word-documents/SKILL.md) and [Word browser setup](../../setup-microsoft-services/references/word-browser.md).

## To do
- [ ] Observe repeated authorized macOS invocations across ordinary working days. Record bounded startup/read/edit/save outcomes and whether the owned browser shuts down cleanly; preserve normal Chrome isolation.
- [ ] Observe tenant-triggered session expiry and confirm that ordinary sign-in/MFA restores subsequent headless operation. The predecessor verified recovery after deliberately removing owned-profile cookies; actual expiry timing and tenant policy variations remain untested.
- [ ] Validate sustained unattended use, tenant-triggered session expiry and additional failure timings. Post-save lost acknowledgment is checked; arbitrary network loss and automatic stale-lock recovery are not. Add certificate renewal only as a separately checked setup operation; expiry currently stops clearly and has regression coverage. Transferred unchanged from `live-word-editing`; the preceding items make the observation work concrete without marking this broader item complete.
- [ ] When maintenance is needed, assess deliberate certificate renewal and stale-lock recovery without weakening profile ownership, native credential protection or single-dispatch journals. Do not implement automatic reclamation without verifying platform process ownership and failure behavior.
- [ ] Record setup UI or tenant-gate failures encountered during authorized use, with sanitized reproduction steps and a bounded remedy. Do not broaden consent or fall back to normal Chrome or whole-file replacement.

## Deferred
Windows/Linux onboarding is [parked](../scratch/word-windows-linux-validation.md), to resume when a concrete platform need and test environment exist. Different-user tenant deployment and complex Word structures remain outside the accepted macOS fixture coverage.

## Done
- [x] Repair the setup branch where upload opens the pane before Word exposes the ribbon command. Nine unit/bridge cases and four isolated browser cases pass, including automatic opening without a ribbon button and exact-target refusal. The authorized disposable macOS preparation/read/preview/apply/cloud-verify/fresh-read sequence passed with all other paragraphs preserved and normal Chrome untouched. Saved startup was reused without changing it; existing authentication and journals were retained.
- [x] Isolate every PowerShell process startup/module cache in private OS temporary storage and require a positive readiness marker. Eight synthetic cases cover concurrent isolation, cleanup, crash/false-success diagnostics and unsafe temporary overrides. Four simultaneous real startups, synthetic Graph identity/endpoint/no-retry checks, and existing-account profile, Planner and Outlook reads passed on macOS with the original shared cache unchanged.
- [x] Separate sustained-use tracking from the accepted macOS implementation and preserve the known same-range conflict, manual recovery and authentication limits.
