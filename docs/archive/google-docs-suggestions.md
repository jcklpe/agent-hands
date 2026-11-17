---
attention: historical
closed: 2026-11-17
---
# Google Docs native suggestions
Historical record — closed 2026-11-17. Stable slug: `google-docs-suggestions`. The complete development record is retained below; use [maintained guidance](../../use-google-docs/SKILL.md#native-suggestions) for current behavior and limits. Closure and the exact archival wording were approved.
## Scope
Extend the existing exact-replacement CLI with an explicit `--suggest` option. Preserve unique matching, preview/execute, revision guards and existing direct-edit behavior. Scope is single-paragraph plain-text replacement; formatting suggestions, acceptance/rejection, and native range comments are excluded.

## Design and evidence
The [official API](https://developers.google.com/workspace/docs/api/how-tos/suggestions) exposes `writeControl.writeMode: SUGGEST`. Read with `SUGGESTIONS_INLINE`, reject overlaps with existing suggestions and structural gaps, and submit one guarded replacement. Require created IDs and `ALL_SAVED`, then verify rejection/acceptance projections without changing suggestion state. Ambiguous outcomes stop without retry or direct-edit fallback.

## Validation
On 2026-11-17, eleven synthetic suggestion tests, four write-guard tests and the three existing comment/inline/Markdown regression programs passed. One authorized live replacement returned a suggestion ID and passed independent pending-state readback. No private target identifiers or content are retained here. Broader document structures and platforms are not established by this one live example.

[Execution record](google-docs-suggestions.todo.md). [Original captured scope](../scratch/google-docs-suggest-mode.md).

## Closure preparation — 2026-11-17
The bounded plain-text suggestion capability is ready for closure. Eleven suggestion tests, four write-guard tests and the three comment/inline/Markdown regression programs passed again. Google's current [WriteControl reference](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate#WriteControl) confirms `writeMode: SUGGEST`; the implementation retains required-revision and independent pending-state checks. The earlier recorded authorized live result is retained; this review made no new document write. Current commands and limits belong to [Google Docs](../../use-google-docs/SKILL.md#native-suggestions). Formatting, accept/reject operations and native range comments remain excluded. The implementation is checkpointed locally and was outside the Microsoft-only publication. Its final delivery must include code, tests, maintained guidance, the archived pair and index updates together in one commit. A clean public-baseline assembly can preserve the existing local checkpoint and unrelated work. See the closure review (local preparation record); no archival is authorized yet.
