---
id: BOUND-MAIL-WRITES
type: operational
scope: "Agent use or maintenance of one-off mail filing/metadata changes, manual-send Gmail drafts, Outlook reply drafts and saved-draft body edits."
status: adopted
authority: "User's Agent Hands policy-pilot approval, 2026-11-02, and explicit request for Gmail draft creation with manual sending and no send capability, 2026-11-06; explicit approval of bounded Outlook reply drafts and adding saved-draft editing, 2026-11-17."
revised: "2026-11-17"
depends_on: ["REJECT-GUESSES"]
related_to: ["BOUND-MICROSOFT-ACCESS", "BOUND-MAIL-RULES"]
---
# Bound one-off mail writes
Limit one-off mutations to reversible filing, supported metadata changes and explicitly authorized Gmail draft creation, Outlook reply-draft creation and saved Outlook draft body edits for manual sending. Sending, sent replies, sent forwards, marking read, reporting spam and one-off message deletion remain unavailable. Folder/label creation does not imply a corresponding deletion command. Standing automation is separately governed by [BOUND-MAIL-RULES](BOUND-MAIL-RULES-limit-standing-automation.md), not an exception for one-off deletion.

Retain per-account write opt-in, preview by default, explicit execution, exact message/thread IDs, source checks, a maximum 50 targets per call, readback after each executed change and the ignored local mail audit log or durable private draft-operation receipts. Apply REJECT-GUESSES to unknown/wrong-source IDs or ambiguous labels/folders; resolve searches to exact IDs rather than issuing unbounded search-based bulk writes. Provider write scopes permit more than these commands, so the boundary is the native surface, not the credential.

Gmail draft creation uses a separate action-time opt-in for one selected account, preview by default, explicit execution and content readback. It never sends, infers recipients or automatically retries creation; uncertain outcomes require inspection before retrying. Existing label/filter opt-ins do not authorize drafting. Preserve the user's manual-send boundary at the native command and transport surface. Google has no draft-only OAuth grant; disclose that limitation and obtain explicit setup approval before any scope expansion. Adding this capability neither changes existing grants nor authorizes sending through another route.

Outlook reply drafts use the native reply or explicitly requested reply-all operation on an exact source message, with explicit recipients, a verified account-specific supplied signature or explicit omission, preview hash, existing mail-write opt-in and separate action-time drafting opt-in. Preserve generated quoted history and intervening user edits; verify the unsent draft, account, audience, conversation, new paragraphs, signature and quotation. Persist dispatch and returned draft identity before later writes/readback, and never automatically recreate, delete or send an uncertain draft. Provider signature settings, attachment mutations, new-message drafts, forwards and arbitrary metadata updates remain outside this bounded extension. Draft support changes neither existing consent nor permission to send.

Saved Outlook draft body edits use one exact draft in the verified mailbox, a preview-bound complete replacement, the same write/execution/drafting opt-ins and conditional revision protection. Preserve the subject, recipients, sender, conversation and attachments; reject sent messages, unknown critical state, incomplete attachment inventories and intervening changes. Record dispatch before the body update and verify the unsent result and preserved fields afterward. Uncertain edits require read-only reconciliation, never automatic replay. Body replacement must make any signature/quotation replacement and formatting limits explicit; it does not infer omitted content. Implementing editing does not authorize editing an actual mailbox draft.

Outlook filing may archive/unarchive, move to allowed folders or create a folder. Deleted Items, Junk, Drafts, Sent, Outbox, recoverable items and their descendants remain refused move targets. Category changes affect exact messages; master category-list/color creation or edits remain outside the surface. Moves change message IDs: preserve readback/audit of the new ID and use it for later operations.

Gmail filing may archive/unarchive, apply/remove user labels, skip Inbox or create a user label. Do not mutate ordinary system labels (including Trash, Spam, unread, starred, importance or categories), or act on mail already in Trash/Spam through ordinary filing. The narrow rescue exception permits only Spam-to-Inbox or Junk-to-Inbox using the dedicated operation, never Trash rescue or moving mail into Spam/Junk. A mistaken rescue is corrected through the mail UI, not an invented reverse command.

The consuming workflow owns relevance, cadence and authorization for each action. Inbox-only exports omit filed mail; callers choose their query/folder coverage and destinations without a prescribed private snapshot schema. Grant changes require the actual setup authorization; no re-consent is performed for this migration.

## Enforcement and procedures
[Gmail](../../use-gmail/SKILL.md) and [Outlook mail](../../use-outlook-mail/SKILL.md) own command selection, opt-in configuration, readback and audit mechanics. [BOUND-MICROSOFT-ACCESS](BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md) explains the delegated Microsoft boundary.

## Identity history
This obligation continues the reviewed legacy record [0007](../archive/agent-policy-retirements/0007-mail-archive-and-labels.md), retired as an operative document during this authorized migration. Its source text and numeric identity remain reserved; the history link is not an override or automatic authority transfer.
