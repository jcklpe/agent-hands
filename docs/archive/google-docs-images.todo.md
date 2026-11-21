---
attention: historical
---
# Google Docs inline image repair tasks
Historical record. Closed 2026-11-20. Slug: `google-docs-images`. Maintained commands and safeguards belong to [Google Docs](../../use-google-docs/SKILL.md). The bounded image-repair capability is implemented, published and independently checked; document-specific visual acceptance, wider platforms and interrupted-upload recovery are not claimed.

The retained development entries describe their dated checkpoints; later pending or local-only statements are historical.

## Background
Implement the explicitly requested native capability expansion without broadening authentication or adding a general API escape hatch.
## Current State Overview
Implemented and exercised on an authorized live document. Independent export and pixel checks reconciled Google re-encoding after the initial strict-byte readback failed; the repair was not repeated. Pre-publication review added owner-only outside-Git outputs, atomic recovery records, restricted temporary-folder sharing, redirect checks and display-size verification. All 47 Python checks pass. The additional safeguards are covered by synthetic tests; the real document write was not repeated. Other platforms and interrupted-upload recovery remain untested.
## To Do
- [x] Inspect and identify existing inline images without printing signed content URIs.
- [x] Implement private local-image import, fingerprint preview, revision guards and bounded replacement.
- [x] Verify rejection cases, text preservation, unaffected images, source hashes and cleanup with synthetic fixtures.
- [x] Exercise the authorized live target and inspect an independent export.
- [x] Document actual behavior, limits and recovery.
## Acceptance and retained limits
The selected native capability is implemented, published and checked through an authorized live repair plus independent export/pixel inspection. No further implementation item remains in this scope. Acceptance of an individual document's appearance remains with its caller; closure does not claim broader visual acceptance, animation preservation, other-platform validation or interrupted-upload recovery. The added publication safeguards have synthetic coverage and were not established by repeating the real write.
## Done
- Scoped the operation and private temporary-import lifecycle.
- Reviewed the complete publication patch and added regression checks for private file modes, repository/symlink rejection, shared-folder refusal, safe redirects, preserved dispatch receipts, cleanup of only the created import and display-size mismatch. The private runtime inventory records recovery retention separately from disposable outputs.
