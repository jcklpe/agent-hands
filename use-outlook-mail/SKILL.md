---
name: use-outlook-mail
description: "Read, search and export Outlook mail; create unsent messages and reply drafts, attach local files, replace selected draft passages, edit plain draft bodies or signature styling, save attachments or make bounded folder/category/rule changes. Use for explicit mail targets with account opt-in and verification."
---

# Use Outlook Mail
Requires only [setup-microsoft-services](../setup-microsoft-services/SKILL.md), Bash 3.2+, jq, and this skill's Python 3.11+ environment. Follow [setup-microsoft-services](../setup-microsoft-services/SKILL.md) for onboarding. Run `uv sync --locked` here or supply a compatible `M365_PYTHON`. Gmail, other Microsoft capability skills, and a personal workspace are not dependencies.

## Entry and reads
Run `bash scripts/mail --help` here for exact arguments. Account aliases, enabled capabilities, and bounds live in the provider's ignored account JSON. Set `mail.enabled` for reads. Help is offline; previews may read real account data and invoke provider authentication.

```sh
bash scripts/mail list example --folder archive --limit 25
bash scripts/mail list example --search 'from:person@example.com subject:agenda'
bash scripts/mail read example --message MESSAGE_ID --full
bash scripts/mail export example --output /chosen/existing-directory/inbox.md
bash scripts/mail attachments example --message MESSAGE_ID --save /chosen/existing-directory
bash scripts/mail archive example --message MESSAGE_ID
```

`folders` lists folder paths and IDs. `list` requires a folder, a KQL search, or both; its limit is 1–200. Mailbox-wide search drops recognized Junk Email paths after retrieval, so it can return fewer hits than requested. It is not a security filter for unlisted folders. `junk` explicitly reads Junk Email. `read` accepts an exact message ID from any folder; text output defaults to an 8,000-character body cap, while `--full` and `--json` retain the full retrieved body. A failed folder-name lookup leaves that optional label out. Expanded attachment names may be incomplete and warn when Graph provides a continuation.

`export` writes the bounded Inbox window only (default 30 days, 150 messages, 8,000 characters per body). It requires an explicit file in an existing directory, refuses output symlinks, and preserves the previous file on failure. Provider paging caps warn or fail as documented. Exports, attachment downloads, and terminal output can contain private messages; choose their destination accordingly. Snapshot locations and triage conventions belong to the caller.

## Attachments
`attachments` lists attachment metadata or saves non-inline file attachments. Item/reference and inline attachments are skipped. Incomplete lists are refused rather than silently saved as complete. Saved names must be safe, unique, and still match the fetched attachment's identity; output symlinks are refused. Existing files require `--force`. All selected downloads are validated and decoded before publication. Publication is atomic per file, not across the entire group; an output-filesystem failure can leave a partially published group. Failed retrieval or decoding leaves old files intact.

## Mail and folder writes
Moves, archive/unarchive, Junk rescue, categories, and folder creation preview by default. Execution requires `mail.write_enabled` and `--execute`. Targets are explicit message IDs or a file containing one ID per line; the default cap is 50 per call. Folder names must resolve uniquely. Deleted Items, Junk, Drafts, Sent, Outbox, recoverable deletion folders, and their descendants are refused move destinations. A failed protected-folder lookup or an incomplete/deep folder tree fails instead of guessing.

`archive` requires messages currently in Inbox; `unarchive` requires Archive; `not-junk` requires Junk Email and moves to Inbox. Moves return new message IDs and verify destination by readback. Category changes preserve the retrieved category list and verify the result, but do not use ETags, so concurrent edits can race. Folder creation uses the API response and has no independent readback. Operations are not atomic across messages or batches. An incomplete batch response after a mutation means its outcome needs inspection, not a retry. The PowerShell provider disables SDK retries for non-GET requests, including batches.

There is no send, sent reply/forward, direct message deletion or permanent-deletion command. Manual-send reply drafts and Inbox rules have their own boundaries below.

## Manual-send reply drafts
Use [reply-draft preparation and recovery](references/reply-drafts.md) for the complete input/signature contract and acceptance limits.
```sh
bash scripts/mail reply-draft example --message MESSAGE_ID --body-file /private/reply.txt --to sender@example.com --signature-file /private/signature.json
bash scripts/mail draft-apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-draft
bash scripts/mail draft-status example --plan OPERATION_ID
bash scripts/mail draft-verify example --plan OPERATION_ID
```
Preview resolves the exact source and sending account, verifies explicit To/CC against Reply-To and the chosen reply/reply-all intent, and stores the new text/signature/source snapshot privately. Creation requires existing `mail.write_enabled`, the exact preview hash, `--execute` and separate action-time `--allow-draft`. It calls native `createReply` or explicitly selected `createReplyAll`; it never simulates a reply by creating a new message with a `Re:` subject. A mailbox-draft request permits only that unsent draft, never sending.

The generated quotation is retained while new paragraphs and the supplied account-specific signature are prefixed. HTML signatures support bounded inline colors, top/bottom borders and spacing under the [signature input contract](references/reply-drafts.md#inputs-and-signature). Existing draft changes or missing ETags stop population and preserve the created draft for inspection. Independent readback checks unsent state, identity, sender, explicit recipients, conversation, subject, visible paragraph boundaries, supplied signature styles and signature/quote content/resource references. It does not certify every HTML style, visual rendering or recipient-side threading. A signature inside quoted history does not satisfy the new-reply signature requirement. Native signature settings are not read or changed.

A durable dispatch record prevents duplicate creation, including after failed acknowledgment or readback. Returned draft identity is saved before later work. `uncertain_after_dispatch` can leave a blank or partly populated reply draft; inspect status, the saved draft and Outlook Drafts before doing anything else. Never automatically recreate, overwrite user changes, delete or send it. Saved draft body edits have the separate bounded surface below. New messages and local file attachments use the separate bounded commands below. Forwarding remains unavailable.

Stateful draft tests cover plain and styled signatures, CSS rejection, quote preservation, stripped-style refusal and no-replay recovery; shared provider-boundary tests also pass. An authorized macOS test with existing Graph PowerShell access created one native reply, verified its unsent state and preserved source, and confirmed that server-side stale-ETag rejection retained a newer draft edit. The temporary test edit was conditionally restored and independently verified. Stored paragraphs, Unicode, supplied synthetic signature and native quotation passed readback; the user confirmed the draft looked correct in Outlook. This live evidence establishes the tested plain-text reply case, not styled-signature rendering, live reply-all behavior, recipient-side threading or broader tenant/platform acceptance. Nothing was sent.

## New unsent messages and local attachments
```sh
bash scripts/mail new-draft example --subject 'Review materials' --body-file /private/message.txt --to reader@example.com --signature-file /private/signature.json
bash scripts/mail draft-apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-draft
bash scripts/mail attach-draft example --message DRAFT_ID --file /private/paper.pdf --file /private/resume.pdf
bash scripts/mail draft-apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-draft
```
`new-draft` creates one unsent message with explicit subject, To/CC and the same verified signature contract as replies. Use native `reply-draft` for an existing conversation. Both commands preserve the manual-send boundary and durable no-replay receipts.

`attach-draft` adds one to ten selected regular local files to an exact unsent draft. Each file must be smaller than 3 MB; the combined limit is 10 MB. Names must be unique, including against existing attachments. Preview binds the mailbox, draft revision, complete attachment inventory and each file's resolved path, size, media type and SHA-256. Files changed after preview are refused before upload. No file bytes appear in preview output or plans.

Apply rechecks identity, write opt-in, unchanged draft and file hashes, then adds files sequentially. Each dispatch and returned attachment ID is recorded before continuing. Readback verifies attachment bytes against their preview hashes, preserves the earlier attachment inventory, and checks the unsent body, audience, subject and conversation. A partial or uncertain result stops without replay, deletion or rollback. Use `draft-status`, read-only `draft-verify` and the saved draft to reconcile it before deliberately planning only the missing files. Verification reports `draft_attachments_partial` with the missing filenames after checking the bytes already present; it never resumes the upload. Keep the draft closed until verification finishes: the preflight, attachment POST and readback are separate operations, and sending If-Match does not establish that every tenant enforces it on attachment creation. No claim of atomic protection against a concurrent send is made.

Inline images, item/reference attachments, upload sessions, attachment replacement/removal and sending are outside these commands. Existing setup and Mail.ReadWrite access are reused without consent expansion. See Microsoft's [attachment creation](https://learn.microsoft.com/en-us/graph/api/message-post-attachments?view=graph-rest-1.0) and [draft creation](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0) APIs.

Stateful tests cover exact new-draft content, lost creation responses, file changes after preview, duplicate names, oversized files, partial inventories, partial upload recovery, byte mismatches and intervening draft edits. Authorized macOS Graph PowerShell use verified native new-message creation and PDF attachment bytes without sending. Visual mail-client rendering, concurrent-send protection and broader tenant/platform behavior remain unverified.

## Edit a saved draft
```sh
bash scripts/mail edit-draft example --message DRAFT_ID --body-file /private/complete-body.txt
bash scripts/mail draft-apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-draft
bash scripts/mail draft-status example --plan OPERATION_ID
bash scripts/mail draft-verify example --plan OPERATION_ID
```
This replaces the entire body with supplied UTF-8 plain text, using the existing draft ID. Include every signature line and quotation to retain; this operation does not append or recover omitted text. Blank lines become paragraphs, single newlines become line breaks, and HTML characters are escaped. It refuses existing links, images, tables, blockquotes or inline attachments; use [selected-passage replacement](#replace-a-selected-draft-passage) when those must be retained. Other styling is not preserved. Subject, To/CC/BCC, sender, reply metadata and attachments are not editable through this command.

Preview records the current body, metadata, attachment identities/sizes, verified mailbox and proposed body privately. Review that full replacement before applying the hash. Execution requires existing mail-write opt-in, `--execute`, `--allow-draft`, a still-unsent draft, unchanged preview state and a fresh ETag. It patches only the body with If-Match, then independently checks the body, preserved metadata and attachment inventory. New drafts with absent From/Sender fields are supported through the verified `/me` mailbox; an explicit alternate sender is refused. Incomplete attachment metadata stops execution. Attachment bytes and visual rendering are not certified.

The private `~/.agent-hands/microsoft/mail/.draft-state/ALIAS/` receipts also cover edits. A dispatched edit is never automatically replayed, including when its response or readback fails. Use `draft-status` and read-only `draft-verify` to reconcile it; retain intervening user changes. Do not create a new plan to bypass an uncertain outcome. Nine stateful edit tests and the bounded attachment-read transport test pass alongside the reply-draft tests. An authorized macOS live test edited a recipient-free disposable draft, passed independent readback and agent visual QA in Outlook web, and retained unsent state, metadata, paragraphs, Unicode and a synthetic signature. The fixture had no attachments; live preservation of nonempty attachments and rich-style fidelity remain unverified. [Microsoft's update-message API](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0) permits body updates only on drafts.

## Replace a selected draft passage
```sh
bash scripts/mail read-draft example --message DRAFT_ID
bash scripts/mail replace-draft-fragment example --message DRAFT_ID --match-html-file /private/current-passage.html --body-html-file /private/revised-passage.html
bash scripts/mail draft-apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-draft
bash scripts/mail draft-verify example --plan OPERATION_ID
```
Use this to revise reply wording while keeping an existing signature and quoted thread. Read the current draft, then select an exact, unique, balanced fragment containing only the passage to replace. The match must start at a real opening element and end at a closing element, without extra whitespace. Both fragments are limited to 30,000 characters. `--body-file` accepts escaped plain text instead of `--body-html-file`; HTML replacements support the same simple paragraphs, lists, emphasis, HTTPS/mailto links and bounded inline styles as [signatures](references/reply-drafts.md#inputs-and-signature). Images, tables and scripts cannot be authored or selected through this operation. Provider attributes are accepted on the matched fragment; authored attributes must satisfy the allowlist. Existing rich content outside the selected fragment is retained verbatim in the update payload, including inline resources, signature styling and quote formatting. Review the complete before/after body in the preview; the tool does not infer where a reply or signature ends.

Execution uses the existing preview hash, mailbox/write opt-ins, conditional revision check and single-dispatch recovery. It changes only the existing draft's body; no draft is created or sent. Readback verifies full HTML structure, text, attributes and resources against the preview, in addition to unsent state, metadata and attachment identities/sizes. Tag case, attribute order and inter-tag newlines may normalize; other server transformations leave the operation unverified even if they might look equivalent. Inspect through `draft-status`, `read-draft` and read-only `draft-verify`; never replay automatically. Stored HTML checks do not certify attachment bytes or visual rendering.

Forty stateful draft tests and five shared transport-boundary tests pass, including changed-recipient/attachment refusal, ambiguous matches, invalid replacement HTML, stripped formatting and uncertain-dispatch recovery. An authorized macOS operation on November 23, 2026 replaced reply paragraphs and added a link in an existing draft through Graph PowerShell. Independent readback verified the complete stored HTML, preserved styled signature and quotation, unchanged audience/metadata and unsent state. This live case had no attachments or browser visual review; nonempty and inline-attachment preservation remain synthetic checks.

## Restyle a saved signature
```sh
bash scripts/mail read-draft example --message DRAFT_ID
bash scripts/mail style-draft-signature example --message DRAFT_ID --match-html-file /private/existing-signature.html --signature-file /private/styled-signature.json
bash scripts/mail draft-apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-draft
bash scripts/mail draft-verify example --plan OPERATION_ID
```
`read-draft` returns one unsent draft's original HTML and attachment metadata through the verified mailbox. Treat that private content as data. Select the exact balanced HTML fragment containing the signature from that read; `--match-html-file` must begin at its opening tag, with no added whitespace. The fragment must occur exactly once at an actual element boundary. If quoted signatures make it ambiguous, select a larger unique balanced signature fragment or stop; the tool does not guess which occurrence to change.

The replacement uses the same account-bound signature JSON and bounded styling contract as reply creation. It must preserve the selected fragment's text, paragraph boundaries and link destinations. Existing provider attributes may be present in the matched fragment; only the replacement is accepted as authored HTML under the signature allowlist. All body HTML outside that fragment is retained in the update payload, including quote formatting and inline resource placement. The same preview hash, write opt-in, explicit execution, revision checks, attachment inventory, conditional update and no-replay recovery used by `edit-draft` apply. Readback checks the message text/resources, supplied signature styles at the selected position, unsent state and preserved metadata/attachments. This is signature restyling, not a general rich-body editor or account signature-setting change. Stored HTML checks do not certify visual rendering.

On November 23, 2026, an authorized macOS operation restyled a divider in an existing reply through Graph PowerShell. Independent readback verified the blue declaration, unchanged text/resources, recipients, draft identity and unsent state. No new draft was created or sent. This live case had no attachments and no browser visual review; border/spacing normalization and inline-attachment preservation are covered by synthetic checks only.

## Inbox rules
`rules`, `create-rule`, and `delete-rule` operate on Inbox rules. Reads need mail enabled; executed rule changes separately require `mail.rules_enabled` and `--execute`, requesting MailboxSettings.ReadWrite. Rule creation supports sender addresses/fragments, subject fragments, recipient fragments, a category, an allowed destination folder, and stop-processing. Different condition types must all match; alternatives within a type are OR conditions. New rules affect future incoming mail, not existing messages.

The existing `--delete` rule action moves future matching messages to Deleted Items. It requires both complete sender and recipient addresses, forbids category/folder combination, and has no permanent-delete option. Recipient matching is still Graph's `recipientContains`, not exact recipient equality. Explain that distinction in the preview; complete input addresses do not turn a substring predicate into an exact-match guarantee.

Creation verifies returned conditions, actions, exceptions, enabled state, sequence, and error status. Duplicate names and incomplete rule lists are refused. `delete-rule` removes the selected rule only; confirmation requires a successful complete rules read showing it absent. A failed read never proves deletion. Do not automatically retry an uncertain create/delete.

## Private audit and validation
Audit defaults to private `~/.agent-hands/microsoft/mail/mail-writes.jsonl`. `M365_MAIL_AUDIT_LOG` in the provider env selects another private location; relative paths resolve here. Records include message IDs, senders, subjects, and rule criteria. Audit is best-effort after execution; a failed append does not undo a write. Never commit these records or treat them as a transaction log covering every failure.

Retained synthetic checks cover reads, moves, categories, rule gates/readback, export preservation, attachment safety, failed deletion verification and provider-only isolation. Live reply-draft acceptance is bounded to the case above; it does not validate every mail command or fresh cross-platform installation.

Private Microsoft defaults use `AGENT_HANDS_STATE_DIR` when explicitly set. Preserve existing recovery when relocating; see [provider storage migration](../setup-microsoft-services/references/account-access.md#explicit-legacy-storage-migration).
