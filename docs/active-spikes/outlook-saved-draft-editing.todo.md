---
attention: live
---
# Outlook saved-draft editing tasks
[Scope](outlook-saved-draft-editing.md).

## Done
- Added `edit-draft` preview and routing through existing apply/status/verify commands; only the body is patched, with If-Match and no replay.
- Added complete attachment-metadata reads to the bounded provider without adding content downloads or attachment mutations.
- Passed 21 stateful draft tests and five provider-boundary tests, including nine new edit tests and one new transport test.
- Updated native skill, capability listing and the two applicable policy bodies under the explicit implementation request.
- Passed the existing mail shell checks, Bash syntax, policy graph/index and diff whitespace checks. Verified skill frontmatter and relative resources with Ruby/Psych; the optional Python skill validator could not run because PyYAML is absent. Existing Codex/Claude skill links resolve directly to the updated source.
- Tried a native read-only preview. Mailbox identity succeeded, but the previously selected draft ID was no longer found; the existing read command also returned not found and an exact subject search in Drafts returned no matches. No mutation was attempted. This does not establish what happened to that draft or validate live edit execution.

## Verification remaining
- Live edit execution and user visual review need a separately authorized actual edit; the implementation request alone does not select one.
