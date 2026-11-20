---
attention: live
reviewed: 2026-11-20
tags: [microsoft, word, reliability]
---
# Sustained Word runtime reliability tasks
Opened: 2026-11-16. Slug: `word-runtime-reliability`. [Scope and baseline](word-runtime-reliability.md).

## Current state
The accepted macOS implementation is undergoing authorized runtime repair and a disposable edit/save check. A controlled startup test isolated a PowerShell JIT cache failure before Graph; fresh caches allowed existing authentication and bounded service reads. A separate Word read reached the owned browser but did not start the add-in, although downloaded startup metadata matched. These are separate diagnostic results; no migration cause is established. Operational guidance remains in [Word Documents](../../use-word-documents/SKILL.md) and [Word browser setup](../../setup-microsoft-services/references/word-browser.md).

## To do
- [ ] Diagnose owned-profile add-in loading, then verify a disposable read/edit/save and independent cloud readback. Preserve normal Chrome and existing operation journals.
- [ ] Observe repeated authorized macOS invocations across ordinary working days. Record bounded startup/read/edit/save outcomes and whether the owned browser shuts down cleanly; preserve normal Chrome isolation.
- [ ] Observe tenant-triggered session expiry and confirm that ordinary sign-in/MFA restores subsequent headless operation. The predecessor verified recovery after deliberately removing owned-profile cookies; actual expiry timing and tenant policy variations remain untested.
- [ ] Validate sustained unattended use, tenant-triggered session expiry and additional failure timings. Post-save lost acknowledgment is checked; arbitrary network loss and automatic stale-lock recovery are not. Add certificate renewal only as a separately checked setup operation; expiry currently stops clearly and has regression coverage. Transferred unchanged from `live-word-editing`; the preceding items make the observation work concrete without marking this broader item complete.
- [ ] When maintenance is needed, assess deliberate certificate renewal and stale-lock recovery without weakening profile ownership, native credential protection or single-dispatch journals. Do not implement automatic reclamation without verifying platform process ownership and failure behavior.
- [ ] Record setup UI or tenant-gate failures encountered during authorized use, with sanitized reproduction steps and a bounded remedy. Do not broaden consent or fall back to normal Chrome or whole-file replacement.

## Deferred
Windows/Linux onboarding is [parked](../scratch/word-windows-linux-validation.md), to resume when a concrete platform need and test environment exist. Different-user tenant deployment and complex Word structures remain outside the accepted macOS fixture coverage.

## Done
- [x] Isolate every PowerShell process startup/module cache in private OS temporary storage and require a positive readiness marker. Eight synthetic cases cover concurrent isolation, cleanup, crash/false-success diagnostics and unsafe temporary overrides. Four simultaneous real startups, synthetic Graph identity/endpoint/no-retry checks, and existing-account profile, Planner and Outlook reads passed on macOS with the original shared cache unchanged.
- [x] Separate sustained-use tracking from the accepted macOS implementation and preserve the known same-range conflict, manual recovery and authentication limits.
