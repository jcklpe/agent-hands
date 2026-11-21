---
attention: historical
---
# Outlook saved-draft editing
Historical record. Closed 2026-11-21 after approval of closure and the complete archival wording. Slug: `outlook-saved-draft-editing`. Maintained commands and safeguards belong to [Use Outlook Mail](../../use-outlook-mail/SKILL.md). The macOS plain-text scope is verified; rich-style fidelity, nonempty attachment preservation and other platforms retain the limits below.

The retained development entries describe their dated checkpoints; pending statements below are historical.

The user requested saved-draft editing on November 17, 2026. Extend the existing Outlook draft engine with a body-only edit of one unsent message, using the current Microsoft account and existing grants. [Command guidance](../../use-outlook-mail/SKILL.md#edit-a-saved-draft) owns the procedure.

The first surface accepts a complete plain-text body and preserves the subject, audience, sender, conversation and attachment metadata. It refuses rich structures and inline attachments needing a formatting-preserving editor. Preview, account opt-in, explicit execution, ETag comparison, durable single dispatch and independent readback are reused. Full replacement makes signature/quote retention the caller's explicit responsibility. No sending, recipient editing, attachment changes, generic request CLI or credential change is included.

The authorized policy amendments retain BOUND-MAIL-WRITES and BOUND-MICROSOFT-ACCESS identities and existing prerequisite edges. The former adds guarded body edits; the latter routes those edits through the same delegated-access boundary. The kernel, mail-rule policy and other services are unchanged. The implementation request does not approve any particular mailbox edit.

Continues from: docs/archive/outlook-reply-drafts.md

## Validation limits
Stateful tests exercise preservation, changed previews, sent messages, ETag races and uncertain-write recovery. An authorized macOS test passed native preview/apply/independent readback and agent visual QA on one recipient-free, attachment-free disposable draft. Unsent state, subject, sender, conversation, text and paragraph boundaries were verified. Rich structures, nonempty attachment preservation and other platforms remain outside this live fixture. [Task record](outlook-saved-draft-editing.todo.md).
