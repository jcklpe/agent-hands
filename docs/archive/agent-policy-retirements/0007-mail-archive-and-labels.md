---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0007 policy history
Legacy identity: `0007`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [BOUND-MAIL-WRITES](../../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0007-mail-archive-and-labels.md`. Exact original SHA-256: `5e97b98171514f9daeb4795fdff376dd9986571075782c779d9fe9c891b43830`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0007-mail-archive-folders-and-labels"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="operating-notes"></a>
<a id="spam-and-junk-rescue"></a>
<a id="outlook-categories"></a>
<a id="standing-rules-and-exceptions"></a>
<a id="rationale-for-limits"></a>
<a id="links"></a>

````text
# 0007 Mail Archive, Folders, And Labels

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
Run the documented native entrypoint in [use-gmail](../../use-gmail/SKILL.md) or [use-outlook-mail](../../use-outlook-mail/SKILL.md); command names below are relative to that entrypoint and take an explicit account alias.

Mail mutations are limited to **reversible filing and metadata changes**, the outbound spam/junk rescue commands below, and the standing rules governed by [0009](0009-mail-filters-and-rules.md). Sending, replying, forwarding, marking read, and one-off deletion remain unavailable. Concretely:

- **Microsoft 365:** `archive` (Inbox to Archive), `unarchive` (Archive to Inbox), `move` (to any allowed folder), and `create-folder`, plus the read-only `folders` and `list`. Deleted Items, Junk Email, Drafts, Sent Items, Outbox, recoverable items, and every folder beneath them are never move targets, because moving there amounts to deleting, spam-reporting, or sending.
- **Gmail:** `archive` and `unarchive` (remove or restore `INBOX`), `label` and `unlabel` for user labels only, `label --skip-inbox` as the folder equivalent, and `create-label`, plus the read-only `labels` and `list`. System labels (`TRASH`, `SPAM`, `UNREAD`, `STARRED`, `IMPORTANT`, categories) cannot be applied or removed, and mail already in Trash or Spam is refused.

Each write surface is **off unless the account opts in**: `mail.write_enabled` in `m365-accounts.json` (which switches the requested scope from `Mail.Read` to `Mail.ReadWrite`) and `gmail.write_enabled` in `google-accounts.json` (which adds `gmail.modify`). Both scopes technically permit more than the CLI exposes (`gmail.modify` can trash; `Mail.ReadWrite` can delete). As in 0004, the control is the deliberately narrow command surface, not the token.

All writes follow the existing write discipline: dry-run by default with `--execute` to apply; exact message or thread IDs only; unknown IDs, wrong-source messages, and ambiguous folder or label names fail the whole call ([0006](0006-writes-fail-rather-than-guess.md)); a per-call cap of 50; readback after every executed change; and a local audit log (`mail-writes.jsonl` beside the owning `use-gmail` or `use-outlook-mail` skill, ignored) of every executed change, including the new ID Microsoft assigns a moved message.

This repository supplies bounded mail capabilities. The consuming workflow owns relevance judgments and authorization for each filing action.

## Rationale
Reversible filing removes repeated manual work while keeping sending and deletion outside the one-off command surface. Per-account opt-in allows one account to stay read-only. Exact IDs, source checks, batch caps, readback, and a local audit log bound mistakes even though the granted provider scopes technically allow broader mutations.

## Operating Notes
- Archive, folder moves, and existing-label or category changes can be reversed from the CLI. Executed changes are traced in the audit log. Folder and label creation do not add deletion commands; a mistaken spam/junk rescue is undone in the mail UI.
- An Inbox-only export omits mail after archive or skip-inbox filing. Consumers must select the folder/query and account for that coverage limit; the capability does not prescribe a workspace snapshot layout or note schema.
- Microsoft moves change message IDs. The CLI prints and logs the new ID, and unarchive needs it.
- Enabling Gmail writes needs a browser re-consent per account. Until then, executed changes fail with a 403 and a pointer to `bash setup-google-services/scripts/authorize auth ALIAS`.

## Spam and Junk Rescue
`spam` and `junk` provide explicit reads of mail excluded from ordinary snapshots. `not-spam` removes `SPAM` and adds `INBOX`; its source must be in Spam, never Trash. `not-junk` moves a Junk message to the Inbox. This is the narrow exception to the system-label restriction, and it runs only out of Spam or Junk. Reporting spam and moving mail into Junk remain refused. A mistaken rescue is undone in the mail UI. The consuming workflow owns review cadence and authorization; Microsoft `reportMessage` is not part of this capability.

## Outlook Categories
`categorize` and `uncategorize` set or remove one Outlook category on exact messages, under the same opt-in, dry-run, exact-ID, readback, and audit gates as moves. Master category-list creation or editing, including colors, is outside this capability.

## Standing Rules and Exceptions
[0009](0009-mail-filters-and-rules.md) permits Gmail filters and Microsoft 365 Inbox rules for filing, with an explicitly authorized Microsoft 365 duplicate-mail rule exception that moves future matches to Deleted Items. That exception requires complete sender and recipient-address conditions and does not permit one-off message deletion.

## Rationale for Limits
- **Full read-write mail** (send, reply, forward, delete, mark-read): not asked for, and each is either irreversible or visible to other people.
- **Search-based bulk commands** ("archive everything from X"): a query that matches more than intended fails silently at scale. The caller resolves a search to exact IDs first, using the selected mail capability’s `list` command, and the dry-run plan shows every target.
- **Mark-read on archive:** would change additional message state outside the requested filing operation.
- **Moves to any folder, including Deleted Items:** equivalent to deletion by another name.
- **Unbounded standing automation:** future-mail rules have their own capability and approval boundaries in [0009](0009-mail-filters-and-rules.md).
- **One global switch:** per-account opt-in lets an account stay read-only, when another selected account has writes enabled.

## Links
- [0004 LifeOS Microsoft 365 Access](0004-lifeos-microsoft-365-access.md) — delegated access and transport boundary.
- [0006 Writes Fail Rather Than Guess](0006-writes-fail-rather-than-guess.md)
- [use-outlook-mail skill](../../use-outlook-mail/SKILL.md)
- [Gmail skill](../../use-gmail/SKILL.md)
- [LifeOS mail archive spike](../active-spikes/lifeos-m365-mail-archive.md)
````
