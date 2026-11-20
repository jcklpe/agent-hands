---
attention: live
---
# Google Docs inline image repair tasks
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
## Ready for human visual QA
Live repair and independent export inspected. Broader human acceptance remains with the caller.
## Done
- Scoped the operation and private temporary-import lifecycle.
- Reviewed the complete publication patch and added regression checks for private file modes, repository/symlink rejection, shared-folder refusal, safe redirects, preserved dispatch receipts, cleanup of only the created import and display-size mismatch. The private runtime inventory records recovery retention separately from disposable outputs.
