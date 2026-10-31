---
attention: historical
---
# Canvas snapshot companion tasks
Historical record. Closed October 31, 2026. Stable slug: `canvas-snapshots`. Current behavior and limits belong to [Use Canvas Snapshots](../../use-canvas-snapshots/SKILL.md).
## Done
- Implement the standard-library-only compare, refresh and acknowledgment CLI with explicit inputs and no project-specific routing.
- Preserve native identity/coverage validation, stable field/body differences, pending finding IDs and acknowledgment receipts.
- Retain destination recognition, lock refusal, staged publication, rollback and interrupted-rename recovery.
- Pass 22 synthetic offline tests, including refused output writes and unchanged/failed refresh behavior.
- Document commands, dependencies, package schema, recovery and verification limits in the owning skill.
- Review the neutral implementation and synthetic fixtures for account/project coupling, private context, supported CLI boundaries and preservation of unresolved findings.
- Add the standalone packaged installer, linking only this companion; all 16 shared installer tests pass.
- Install the requested global links into the existing Codex and Claude discovery directories; a later preview reports each unchanged.
- Run two authorized live refresh passes on four existing selected course packages on macOS: all eight runs succeed, with identity/markers and existing acknowledgment receipts preserved, zero semantic changes and zero pending findings.
- Verify deterministic native export files remain unchanged apart from volatile run metadata, and no temporary publication directories or locks remain.

## Closure
- The user approved the implementation, local commits and extraction close-out on October 31, 2026. Archive this pair with the implementation.
- The mixed TODO index remains uncommitted at the user’s direction; its extraction links point to this archive. Other pending work is outside this closure.

## Verification limits
- Nonempty pending-state retention, rejection and failure recovery use synthetic offline evidence; the live packages had no pending findings.
- Fresh-session client discovery and fresh-machine/other-platform onboarding remain unverified. Existing filesystem links do not prove client catalogue loading.
- No course-content writes, finding acknowledgment, downstream task/calendar changes or push were performed. The local closure commit records this implementation and archive.
