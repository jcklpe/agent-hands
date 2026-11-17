---
status: addressed
---
# Google Docs tracked suggestions in Agent Hands
Closed 2026-11-17 after checking the implementation, maintained guidance and execution record. [Use Google Docs](../../use-google-docs/SKILL.md#native-suggestions) supports `replace-once --suggest` for a uniquely matched, nonempty, single-paragraph plain-text replacement, with preview/execute, revision guards and independent pending-suggestion readback. Eleven suggestion tests and four existing write-guard tests passed again during closure. The [implementation spike](../archive/google-docs-suggestions.md) records one authorized live pending replacement; its [execution record](../archive/google-docs-suggestions.todo.md) reports no remaining implementation work. The implementation, tests, maintained guidance and archived spike are delivered together in `94e4f6b`.

This retires the original capability-gap capture. Formatting suggestions, accepting/rejecting suggestions and native range comments remain outside the implemented scope. Current API behavior is described by [Google's Suggest mode documentation](https://developers.google.com/workspace/docs/api/how-tos/suggestions#create_suggestions_using_suggest_mode); the capability does not fall back to direct editing after a suggestion failure.
