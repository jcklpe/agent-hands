---
attention: historical
---
# Outlook saved-draft editing tasks
Historical record. Closed 2026-11-21 after approval of closure and the complete archival wording. Slug: `outlook-saved-draft-editing`. Maintained commands and safeguards belong to [Use Outlook Mail](../../use-outlook-mail/SKILL.md). The macOS plain-text scope is verified; rich-style fidelity, nonempty attachment preservation and other platforms retain the limits below.

The retained development entries describe their dated checkpoints; pending statements below are historical.

[Scope](outlook-saved-draft-editing.md).

## Done
- Added `edit-draft` preview and routing through existing apply/status/verify commands; only the body is patched, with If-Match and no replay.
- Added complete attachment-metadata reads to the bounded provider without adding content downloads or attachment mutations.
- Passed 21 stateful draft tests and five provider-boundary tests, including nine new edit tests and one new transport test.
- Updated native skill, capability listing and the two applicable policy bodies under the explicit implementation request.
- Passed the existing mail shell checks, Bash syntax, policy graph/index and diff whitespace checks. Verified skill frontmatter and relative resources with Ruby/Psych; the optional Python skill validator could not run because PyYAML is absent. Existing Codex/Claude skill links resolve directly to the updated source.
- Tried a native read-only preview. Mailbox identity succeeded, but the previously selected draft ID was no longer found; the existing read command also returned not found and an exact subject search in Drafts returned no matches. No mutation was attempted. This does not establish what happened to that draft or validate live edit execution.

## Verification remaining
- No implementation gate remains for the tested macOS plain-text saved-draft scope. Archival wording review remains; rich content and other platforms retain their documented limits.

## Live verification — 2026-11-20
- Live edit execution and user visual review need a separately authorized actual edit; the implementation request alone does not select one. Completed under the user's subsequent authorization to perform QA independently: created one recipient-free disposable draft in Outlook web, closed its composer, then ran the native edit preview, one conditional apply and independent read-only verify. The existing rich quoted-reply fixture was left unchanged.
- Readback verified the replacement paragraphs, Unicode and literal HTML-sensitive characters, synthetic signature, unsent state, unchanged subject/sender/conversation, empty To/CC/BCC and unchanged empty attachment metadata. Outlook web displayed the saved edited text with paragraph separation and the unsent notice. This was agent visual QA delegated by the user, not a new user visual confirmation.
- Nothing was sent or deleted. The disposable draft remains for user inspection/cleanup; its identifiers, exact account context, receipts and screenshot remain private. Live nonempty attachment preservation and exact rich-style fidelity are not established by this fixture.
