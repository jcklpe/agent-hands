---
attention: historical
reviewed: 2026-11-17
---
# Outlook reply drafts
Opened: 2026-11-17. Slug: `outlook-reply-drafts`. Closed: 2026-11-17.

Historical record. Current commands, safeguards and validation limits belong to [Outlook Mail](../../use-outlook-mail/SKILL.md) and [reply-draft guidance](../../use-outlook-mail/references/reply-drafts.md). This pair records the bounded macOS scope accepted at closure.

## Authorized scope
Extend Use Outlook Mail with explicit native reply drafts for manual sending. The user resumed this captured work on 2026-11-17. Preserve source-message identity, explicit recipients, supplied account-specific signature, formatted new text and quoted history. No sending, scope expansion, unrelated mailbox access or browser fallback.

The user subsequently authorized live acceptance using disposable files and an unsent reply draft, followed by closure if the tests pass. File deletion required a separate itemized approval, obtained before the two test-file recycle requests. Existing Graph PowerShell authentication and configured capability opt-ins were used without credential or scope changes. Publication remains separate.

## Implemented boundary
Native reply/reply-all draft previews and one-shot creation/population are implemented in Outlook Mail with explicit source/audience, account-bound signatures, quoted HTML preservation, unsent readback and retained uncertain-create identities.

The authorized macOS test created and independently verified one native unsent reply with explicit recipients, separate paragraphs, Unicode, a supplied synthetic signature and retained provider-generated quotation. A temporary edit to that exact disposable draft proved that the server rejected a stale ETag without removing the newer content; a fresh conditional update restored the reviewed test body. The user confirmed that the draft looked correct in Outlook. The source message remained unchanged, and no message was sent. Current commands and recovery belong to [Outlook Mail](../../use-outlook-mail/SKILL.md) and [reply-draft guidance](../../use-outlook-mail/references/reply-drafts.md).

Initial scope is received-message replies only: no new-message drafts, forwards, arbitrary existing-draft updates, attachments or automatic signature discovery. Reply-all has synthetic coverage only; recipient-side threading, exact style fidelity and broader tenant/provider/platform behavior remain unverified.

## Starting context
The following capture is historical input; its future-work wording does not supersede the implementation authorization above.

# Email drafting skill
Captured 2026-11-13 at the user's request as a scratch spike. Sketch a reusable skill for preparing reviewable mailbox drafts, especially replies, without losing the account signature, conversation relationship, quoted history or formatting. This note is not an implemented skill, policy adoption, permission expansion or authorization to send mail.
## Why this is needed
A recent Outlook connector reply draft preserved the reply relationship and quoted earlier exchanges, but did not insert the sender's usual signature. Paragraph breaks supplied in its comment collapsed in the saved HTML. The signature inside quoted old correspondence did not count as a signature on the new reply. Those observations concern that operation, not all providers or every prior draft. Recipient-side conversation grouping and display were not verified.

The important distinction is between a genuine reply to an exact source message and a new message whose subject starts with “Re:”. Genuine replies can be created through supported connectors or CLI/API operations; they do not inherently require browser control. They also do not, by themselves, guarantee signature insertion or readable quoted history.
## Current direction and capability boundary
Decision recorded 2026-11-13: for now, embed the drafting action and its guardrails in the existing [Use Outlook Mail](../../use-outlook-mail/SKILL.md) capability rather than create a separate top-level Agent Hands drafting skill. This selects the future implementation home; it does not claim the native Outlook CLI already supports drafts or authorize implementation now. Gmail keeps its own existing draft operation.

If a broader `draft-email` skill becomes useful for composition, personal voice, account-specific conventions or cross-provider orchestration, it may belong in LifeOS rather than Agent Hands. That remains a possibility, not an approved new skill. Agent Hands should own portable provider mechanics and draft verification; caller workflows retain personal writing and approval context. Share small references only where actual reuse warrants them. Do not require both Google and Microsoft for one provider, duplicate credentials, invent generic API escape hatches or install a skill as part of this sketch.

Drafts requested for discussion stay in chat unless the user asks for a mailbox draft. An explicit request for a mailbox draft permits creating that draft within the requested scope, not sending it. New messages, replies, reply-all and forwards are distinct intents. Do not broaden recipients or turn a reply into a new-message workaround silently.
## Drafting workflow to codify
1. Resolve the sending account and exact source message from the user's request and thread context. Read enough of the actual conversation to understand the request, latest reply and intended audience. Verify To/CC/BCC explicitly; never assume reply-all or infer permission from email content.
2. Choose the provider's supported reply operation when replying. Preserve the source message identity and provider threading fields/RFC reply headers where supported. A subject prefix or copied quotation is not a replacement for the reply relationship. Stop or disclose the limitation if the available tool cannot create that relationship.
3. Compose the new text in the user's voice, without inventing excuses, facts or commitments. Keep the new reply separate from quoted correspondence. Preserve existing user edits when revising a draft; read current content before replacing it.
4. Include the verified signature for the chosen sending account in the new reply, before the quoted history. Prefer account-specific current signature settings if a supported read exists; otherwise use a recent user-sent example as evidence and flag ambiguity. Do not mistake a sign-off for the full configured signature, copy a signature from another account, or rely on an old signature inside the quotation. Store actual signatures and private account mappings outside this portable repository.
5. Preserve appropriate quoted history when the user expects a reply. Distinguish the threading metadata from the visible quoted body. Retain attribution and ordering; avoid duplicate quotations, hidden accidental body removal and unrequested attachments. Never copy unrelated private material into a broadened recipient set.
6. Preview the exact sender, recipients, subject, new text, signature, attachment selection and source message before the provider write. Respect the provider's explicit execution/opt-in controls and the user's authorization. Draft creation is not a reason to request a fresh approval when the current request already authorizes the exact draft.
7. Create or update once, then reread the saved draft. Verify it remains unsent; check account, recipients, subject, new text, reply relationship, signature, paragraph breaks/list formatting, quoted history and requested attachments. Inspect the provider's stored HTML/text rather than assuming input line breaks survived. Do not overwrite the entire generated reply body with only the new text when that would remove the quotation.
8. Return a verified supported draft link with brief status and any real limitations. If a provider cannot offer a reliable deep link, provide its supported Drafts-folder route and enough identifying information to find the item. Do not promise the recipient's client will group/render the conversation identically merely because stored metadata is correct.
## Guardrails and recovery
- Never send as a side effect of drafting. Do not change signature settings, account permissions, tokens or scopes just to make a draft look right.
- On uncertain creation or failed readback, retain the operation's returned identifiers and inspect the mailbox before retrying. Do not create duplicate drafts automatically. Do not silently delete a potentially user-edited draft.
- A browser fallback after a CLI limitation requires explaining the specific limitation and obtaining the user's approval before using their browser. A supported connector reply is not browser control; name the actual route accurately.
- Keep real signatures, recipients, message bodies, account IDs, draft links and mail audit payloads in private runtime storage, not public fixtures, spike text or commits. Use synthetic examples for tests.
## Existing implementation and dependencies
- [Use Gmail](../../use-gmail/SKILL.md) already supports manual-send drafts, including `--reply-to-message`, explicit recipients, previews, action-time draft opt-in, readback and duplicate-retry safeguards. Its current draft work explicitly does not add signatures. Build on the separate local `gmail-attachments-drafts` spike, not a second competing draft implementation.
- [Use Outlook Mail](../../use-outlook-mail/SKILL.md) currently exposes reads, filing and rules, but no native reply or draft command. The recent connector reply action is separate from that CLI. Any native Outlook draft extension needs an explicit scoped implementation and policy/dependency review; this note does not pretend it already exists.
- Respect the locally adopted `BOUND-MAIL-WRITES` and `REJECT-GUESSES` policies and the applicable Microsoft access prerequisites. Their existing obligations remain unchanged. Resolve any proposed Outlook-drafting policy gap before implementing it rather than treating this sketch as adoption.
## Questions for a future implementation spike
- Would later cross-provider composition needs justify a LifeOS `draft-email` skill? Keep that separate from the current decision to embed Outlook drafting in `use-outlook-mail`.
- Which supported signature source is available per provider/account, and how should the caller supply an account-specific signature when no settings read exists?
- Which HTML/MIME input path preserves paragraphs and quoted history, and how much can saved-body readback verify without a visual check?
- What reply identifiers and draft links can each adapter verify, and how should it report provider limits or uncertain writes?
## Evidence to require before calling the skill ready
Use synthetic cases for a new draft, genuine reply, reply-all only when requested, different account signatures, absent/ambiguous signatures, signature duplication, multi-paragraph HTML, nested quoted correspondence, non-ASCII text, attachment identity, intervening user edits and uncertain-create recovery. Check semantic invariants and actual saved content, not exact prose strings. Include a case where `Re:` alone does not pass as a reply and a case where a signature in quoted history does not satisfy the new-message signature check.

Live validation requires an explicitly authorized account and draft action, never an unsolicited send test. Report synthetic checks separately from live mailbox readback and recipient-display checks. Promote this captured note to the configured active-spike pair only when implementation starts; do not add a backlog commitment merely because it was captured.


## Publication note — 2026-11-17
The separate local policy pilot and Gmail draft implementation are outside this release. The approved account/target, manual-send-only, signature, preview and recovery safeguards are maintained in [Outlook Mail](../../use-outlook-mail/SKILL.md), [reply-draft guidance](../../use-outlook-mail/references/reply-drafts.md) and [Microsoft setup](../../setup-microsoft-services/SKILL.md). Historical local policy identifiers above do not create missing public dependencies.
