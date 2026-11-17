---
attention: historical
reviewed: 2026-11-17
---
# Outlook reply drafts tasks
Opened: 2026-11-17. Slug: `outlook-reply-drafts`. Closed: 2026-11-17.

Historical record. Current commands, safeguards and validation limits belong to [Outlook Mail](../../use-outlook-mail/SKILL.md) and [reply-draft guidance](../../use-outlook-mail/references/reply-drafts.md). This pair records the bounded macOS scope accepted at closure. [Scope](outlook-reply-drafts.md).

## Done
- [x] Implement native reply/reply-all draft preview and one-shot execution with explicit recipients and signature choices.
- [x] Verify unsent state, account, recipients, conversation, new body, signature and retained quotation; preserve uncertain-create recovery.
- [x] Add synthetic refusal/partial-failure tests and portable guidance with explicit acceptance limits.
- [x] Create and independently verify one authorized native unsent reply on macOS, including a supplied synthetic signature and retained quotation.
- [x] Verify server-side stale-ETag rejection preserves a newer draft edit; restore the reviewed test body with a fresh ETag and verify it independently.
- [x] Obtain user visual review in Outlook and verify that the source message remains unchanged.

## Current state
Native reply/reply-all draft previews and one-shot creation/population are implemented in Outlook Mail with explicit source/audience, account-bound signatures, quoted HTML preservation, unsent readback and retained uncertain-create identities.

12 stateful draft tests, four actual provider-boundary tests and all six existing Outlook shell suites pass.

Initial scope is received-message replies only: no new-message drafts, forwards, arbitrary existing-draft updates, attachments or automatic signature discovery. Live acceptance passed for one account/provider on macOS. Reply-all has synthetic coverage only; recipient-side threading, exact style fidelity and broader tenant/provider/platform behavior remain unverified. No required implementation or live acceptance item remains in this bounded scope.

## Live validation
Authorized acceptance used an ordinary received announcement and a synthetic plain-text reply/signature, with existing Graph PowerShell access. Native reply creation and body population returned `draft_verified`; independent readback checked unsent state, sending account, explicit recipient, conversation, subject, paragraph boundaries, Unicode, signature and retained provider-generated quotation. No CC/BCC or reply-all audience was introduced.

A test-only conditional update added a synthetic marker to this exact disposable draft. An attempted update with the older ETag was rejected by the server and left the newer body/revision intact. A fresh conditional update restored the reviewed body; final independent verification passed, with the marker absent and the draft still unsent. The source announcement's body, subject, conversation and recipients were unchanged. A diagnostic first used the provider's lowercase content-type spelling and was refused locally before transport; normalizing the test request to the internal contract allowed the server-precondition check to complete. This did not require a production draft-code change or a broader editing surface.

The user opened the actual draft in Outlook and confirmed it looked correct. The intended presentation was plain text with separate paragraphs, readable Unicode, the synthetic signature above the original announcement and retained quoted history; no particular font or rich style was required. Nothing was sent, and the draft remains available. Recipient-client threading cannot be established by an unsent test.

The final 30 Python checks (14 organization, 12 draft, four shared transport) also passed in a private copy of committed dependencies with only the selected fixes overlaid. The scoped public-source review found no private account identifiers, source messages, personal paths or credential material in the 12 selected files. Runtime journals are ignored, untracked and owner-only; relative documentation links and workflow-root configuration checks passed. This is a review of this change, not a certification of the repository's entire history.

## Policy and publication
The user explicitly approved the file/mail/access policy amendments on 2026-11-17 and then authorized disposable live acceptance and closure on success. No OAuth scopes, account settings or browser sessions changed. Real source text, message IDs, recipients, draft links and authentication state remain outside committed evidence; public records use sanitized scenarios and synthetic fixtures. The test-only concurrency probe does not add a generic existing-draft update command. Implementation and acceptance fixes remain local; no additional push is authorized. The shared provider's unrelated error-detail changes and the README's unrelated workstream edits are excluded from these commits.
