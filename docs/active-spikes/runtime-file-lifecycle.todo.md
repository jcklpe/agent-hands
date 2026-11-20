---
attention: live
---
# Runtime file lifecycle tasks
## Done
- Documented current file purposes, locations/overrides, tracking and cleanup boundaries for the affected providers and recovery stores.
- Word and PowerPoint verification downloads now use private per-run system temporary directories. Source/Git checkouts, symlinked source roots, relative and missing overrides are refused. Existing `finally` cleanup covers success and failure. All ten Word and fourteen PowerPoint unit/bridge cases pass.
- Microsoft process scratch and PowerShell caches already use private temporary directories with cleanup; authentication is preserved separately.
## In progress
- Classify retained experiment/state files for the containing installation's separately approved retirement. Keep private identifiers and payloads out of tracked evidence.
## Follow-up
- Design migration of remaining legacy persistent stores outside checkouts, preserving ownership markers, all write journals and a single shared writer location. Current sign-ins and journals remain in their documented locations; no silent relocation or automatic expiration is implemented.
