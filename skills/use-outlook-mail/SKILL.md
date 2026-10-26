---
name: use-outlook-mail
description: "Read, search, and export Outlook mail; save attachments or preview supported folder, category, and Inbox-rule changes. Use for bounded Microsoft mail operations with account opt-in and verification."
---

# Use Outlook Mail
Requires only [authorize-microsoft](../authorize-microsoft/SKILL.md), Bash 3.2+, jq, and this skill's Python 3.11+ environment. Follow [setup-microsoft-services](../setup-microsoft-services/SKILL.md) for onboarding. Run `uv sync --locked` here or supply a compatible `M365_PYTHON`. Gmail, other Microsoft capability skills, and a personal workspace are not dependencies.

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

There is no send, forward, reply, direct message deletion, or permanent-deletion command. Rule behavior below is a distinct supported capability.

## Inbox rules
`rules`, `create-rule`, and `delete-rule` operate on Inbox rules. Reads need mail enabled; executed rule changes separately require `mail.rules_enabled` and `--execute`, requesting MailboxSettings.ReadWrite. Rule creation supports sender addresses/fragments, subject fragments, recipient fragments, a category, an allowed destination folder, and stop-processing. Different condition types must all match; alternatives within a type are OR conditions. New rules affect future incoming mail, not existing messages.

The existing `--delete` rule action moves future matching messages to Deleted Items. It requires both complete sender and recipient addresses, forbids category/folder combination, and has no permanent-delete option. Recipient matching is still Graph's `recipientContains`, not exact recipient equality. Explain that distinction in the preview; complete input addresses do not turn a substring predicate into an exact-match guarantee.

Creation verifies returned conditions, actions, exceptions, enabled state, sequence, and error status. Duplicate names and incomplete rule lists are refused. `delete-rule` removes the selected rule only; confirmation requires a successful complete rules read showing it absent. A failed read never proves deletion. Do not automatically retry an uncertain create/delete.

## Private audit and validation
Audit defaults to ignored `mail-writes.jsonl` beside this skill. `M365_MAIL_AUDIT_LOG` in the provider env selects another private location; relative paths resolve here. Records include message IDs, senders, subjects, and rule criteria. Audit is best-effort after execution; a failed append does not undo a write. Never commit these records or treat them as a transaction log covering every failure.

Retained synthetic checks cover reads, moves, categories, rule gates/readback, export preservation, attachment safety, and failed deletion verification. Provider-only isolation and native command behavior are checked without real mail or consent. Live account behavior and fresh cross-platform installation remain unverified.
