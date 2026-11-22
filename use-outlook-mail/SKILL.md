---
name: use-outlook-mail
description: "Read, search and export Outlook mail; create reply drafts, edit saved draft text, save attachments or make bounded folder/category/rule changes. Use for explicit mail targets with account opt-in and verification."
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

The generated quotation is retained while new paragraphs and the supplied account-specific signature are prefixed. Existing draft changes or missing ETags stop population and preserve the created draft for inspection. Independent readback checks unsent state, identity, sender, explicit recipients, conversation, subject, visible paragraph boundaries, signature and quote content/resource references. It does not certify every HTML style, visual rendering or recipient-side threading. A signature inside quoted history does not satisfy the new-reply signature requirement. Native signature settings are not read or changed.

A durable dispatch record prevents duplicate creation, including after failed acknowledgment or readback. Returned draft identity is saved before later work. `uncertain_after_dispatch` can leave a blank or partly populated reply draft; inspect status, the saved draft and Outlook Drafts before doing anything else. Never automatically recreate, overwrite user changes, delete or send it. Saved draft body edits have the separate bounded surface below. New-message creation, forwarding and new attachments remain unavailable.

Twelve stateful draft tests and four shared provider-boundary tests pass. An authorized macOS test with existing Graph PowerShell access created one native reply, verified its unsent state and preserved source, and confirmed that server-side stale-ETag rejection retained a newer draft edit. The temporary test edit was conditionally restored and independently verified. Stored paragraphs, Unicode, supplied synthetic signature and native quotation passed readback; the user confirmed the draft looked correct in Outlook. This establishes the tested plain-text reply case, not exact style fidelity, live reply-all behavior, recipient-side threading or broader tenant/platform acceptance. Nothing was sent.

## Edit a saved draft
```sh
bash scripts/mail edit-draft example --message DRAFT_ID --body-file /private/complete-body.txt
bash scripts/mail draft-apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-draft
bash scripts/mail draft-status example --plan OPERATION_ID
bash scripts/mail draft-verify example --plan OPERATION_ID
```
This replaces the entire body with supplied UTF-8 plain text, using the existing draft ID. Include every signature line and quotation to retain; this operation does not append or recover omitted text. Blank lines become paragraphs, single newlines become line breaks, and HTML characters are escaped. It refuses existing links, images, tables, blockquotes or inline attachments that need a formatting-preserving editor. Other styling is not preserved. Subject, To/CC/BCC, sender, reply metadata and attachments are not editable through this command.

Preview records the current body, metadata, attachment identities/sizes, verified mailbox and proposed body privately. Review that full replacement before applying the hash. Execution requires existing mail-write opt-in, `--execute`, `--allow-draft`, a still-unsent draft, unchanged preview state and a fresh ETag. It patches only the body with If-Match, then independently checks the body, preserved metadata and attachment inventory. New drafts with absent From/Sender fields are supported through the verified `/me` mailbox; an explicit alternate sender is refused. Incomplete attachment metadata stops execution. Attachment bytes and visual rendering are not certified.

The private `~/.agent-hands/microsoft/mail/.draft-state/ALIAS/` receipts also cover edits. A dispatched edit is never automatically replayed, including when its response or readback fails. Use `draft-status` and read-only `draft-verify` to reconcile it; retain intervening user changes. Do not create a new plan to bypass an uncertain outcome. Nine stateful edit tests and the bounded attachment-read transport test pass alongside the reply-draft tests. An authorized macOS live test edited a recipient-free disposable draft, passed independent readback and agent visual QA in Outlook web, and retained unsent state, metadata, paragraphs, Unicode and a synthetic signature. The fixture had no attachments; live preservation of nonempty attachments and rich-style fidelity remain unverified. [Microsoft's update-message API](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0) permits body updates only on drafts.

## Inbox rules
`rules`, `create-rule`, and `delete-rule` operate on Inbox rules. Reads need mail enabled; executed rule changes separately require `mail.rules_enabled` and `--execute`, requesting MailboxSettings.ReadWrite. Rule creation supports sender addresses/fragments, subject fragments, recipient fragments, a category, an allowed destination folder, and stop-processing. Different condition types must all match; alternatives within a type are OR conditions. New rules affect future incoming mail, not existing messages.

The existing `--delete` rule action moves future matching messages to Deleted Items. It requires both complete sender and recipient addresses, forbids category/folder combination, and has no permanent-delete option. Recipient matching is still Graph's `recipientContains`, not exact recipient equality. Explain that distinction in the preview; complete input addresses do not turn a substring predicate into an exact-match guarantee.

Creation verifies returned conditions, actions, exceptions, enabled state, sequence, and error status. Duplicate names and incomplete rule lists are refused. `delete-rule` removes the selected rule only; confirmation requires a successful complete rules read showing it absent. A failed read never proves deletion. Do not automatically retry an uncertain create/delete.

## Private audit and validation
Audit defaults to private `~/.agent-hands/microsoft/mail/mail-writes.jsonl`. `M365_MAIL_AUDIT_LOG` in the provider env selects another private location; relative paths resolve here. Records include message IDs, senders, subjects, and rule criteria. Audit is best-effort after execution; a failed append does not undo a write. Never commit these records or treat them as a transaction log covering every failure.

Retained synthetic checks cover reads, moves, categories, rule gates/readback, export preservation, attachment safety, failed deletion verification and provider-only isolation. Live reply-draft acceptance is bounded to the case above; it does not validate every mail command or fresh cross-platform installation.

Private Microsoft defaults use `AGENT_HANDS_STATE_DIR` when explicitly set. Preserve existing recovery when relocating; see [provider storage migration](../setup-microsoft-services/references/account-access.md#explicit-legacy-storage-migration).
