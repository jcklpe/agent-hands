---
attention: historical
closed: 2026-11-17
---
# Google Docs native suggestions — execution
Historical record — closed 2026-11-17. Stable slug: `google-docs-suggestions`. The complete development record is retained below; use [maintained guidance](../../use-google-docs/SKILL.md#native-suggestions) for current behavior and limits. Closure and the exact archival wording were approved.
[Scope and evidence](google-docs-suggestions.md)
## Done
- [x] Add bounded `replace-once --suggest` with revision guards, pending-ID readback and explicit partial failures.
- [x] Test preview, concurrent revision, existing-suggestion overlap, duplicates, partial responses, incorrect readback, Unicode and native gaps; preserve direct-write regressions.
- [x] Verify one authorized live pending replacement and document supported scope.
## Remaining
- No required implementation work remains. Implementation, tests, maintained guidance and closure are delivered together in `94e4f6b`; additional formats remain outside this scope.

## Closure preparation — 2026-11-17
The bounded plain-text suggestion capability is ready for closure. Eleven suggestion tests, four write-guard tests and the three comment/inline/Markdown regression programs passed again. Google's current [WriteControl reference](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate#WriteControl) confirms `writeMode: SUGGEST`; the implementation retains required-revision and independent pending-state checks. The earlier recorded authorized live result is retained; this review made no new document write. Current commands and limits belong to [Google Docs](../../use-google-docs/SKILL.md#native-suggestions). Formatting, accept/reject operations and native range comments remain excluded. The implementation is checkpointed locally and was outside the Microsoft-only publication. Its final delivery must include code, tests, maintained guidance, the archived pair and index updates together in one commit. A clean public-baseline assembly can preserve the existing local checkpoint and unrelated work. See the closure review (local preparation record); no archival is authorized yet.
