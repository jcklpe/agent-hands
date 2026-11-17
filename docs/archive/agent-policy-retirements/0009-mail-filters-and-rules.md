---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0009 policy history
Legacy identity: `0009`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [BOUND-MAIL-RULES](../../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0009-mail-filters-and-rules.md`. Exact original SHA-256: `9ea58b64e4b7c4fb07074308ba5deb8d2b470b3ac662848f432b4648b169f769`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0009-mail-filters-and-inbox-rules"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="operating-notes"></a>
<a id="duplicate-mail-exception"></a>
<a id="links"></a>

````text
# 0009 Mail Filters And Inbox Rules

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
Run the documented native entrypoint in [use-gmail](../../use-gmail/SKILL.md) or [use-outlook-mail](../../use-outlook-mail/SKILL.md); command names below are relative to that entrypoint and take an explicit account alias.

Rule management covers filing actions on both mail surfaces, with the narrow Microsoft 365 duplicate-mail exception below.

- **Gmail filters:** `filters` lists them (read scope). `create-filter` matches on `--from`, `--to`, `--subject`, and `--query`, and may only add one user label and skip the Inbox. `delete-filter` removes a filter by ID. Changes need `gmail.filters_enabled`, which adds the `gmail.settings.basic` scope at the next `bash setup-google-services/scripts/authorize auth ALIAS`.
- **Microsoft 365 Inbox rules:** `rules` lists them. `create-rule` matches on `--from`, `--sender-contains`, `--subject-contains`, and `--recipient-contains`, and may assign an Outlook category, move to an allowed folder (the same refused targets as mail moves: Deleted Items, Junk, Drafts, Sent, Outbox and their subfolders), and stop processing further rules. The duplicate-mail exception below adds a bounded `--delete` action. `delete-rule` removes a rule by ID. Changes need `mail.rules_enabled`, which adds `MailboxSettings.ReadWrite` at the next `bash setup-microsoft-services/scripts/authorize auth ALIAS`.
- **No forward, redirect, permanent-delete, mark-read, or reply action** can be expressed. Listing still shows such actions on rules made elsewhere, so they stay visible.
- Creates and deletes are dry-run by default and need `--execute`. A Gmail dry run also searches recent mail with the equivalent query and shows what the filter would have caught. Every executed change is read back (a created rule must match its enabled state, sequence, complete conditions, exceptions, and complete actions; a deleted one must be gone) and appended to the mail audit log. Readback accepts Graph default empty/false fields and case-insensitive condition normalization, but refuses omitted or broadened predicates and unexpected actions.
- Deleting a rule is allowed, unlike deleting mail, because it removes only the rule and can be recreated; without it a mistaken filter would be stuck until someone found it in the web settings.

## Rationale
Standing rules reduce repeated filing work but act on future messages that nobody has reviewed. The command surface therefore restricts them to filing and the separately bounded duplicate-mail exception. Provider capabilities such as forwarding, permanent deletion, and marking read remain unavailable through this tool.

## Operating Notes
- The consuming workflow decides when to propose a standing rule. Each particular rule requires user authorization for its complete conditions and actions.
- Rules apply to new mail only. Neither provider applies them retroactively through this CLI, so existing mail is still filed with the label and move commands.
- Enabling either flag changes the requested scope set and needs one interactive sign-in. Verify the selected account’s effective permissions rather than assuming a tenant has pre-approved the requested grant.

## Duplicate-Mail Exception
The exception approved on 2026-10-07 permits a native rule to delete repeated mail delivered to one address while retaining copies delivered to another. Allow `--delete` only when both exact sender selectors (`--from`) and complete recipient-address strings (`--recipient-contains`) are supplied. Microsoft Graph's `delete` action moves messages to Deleted Items; `permanentDelete` remains unavailable. Deletion cannot be mixed with category or folder actions. This authorizes a bounded native-rule capability, not one-off message deletion or autonomous deletion decisions. Every particular standing rule still needs user authorization. Recipient matching covers To and Cc text, rather than resolving aliases to a canonical mailbox identity.

Source: [Microsoft Graph rule predicates](https://learn.microsoft.com/en-us/graph/api/resources/messagerulepredicates?view=graph-rest-1.0), [rule actions](https://learn.microsoft.com/en-us/graph/api/resources/messageruleactions?view=graph-rest-1.0).

## Links
- [0007 Mail Archive, Folders, And Labels](0007-mail-archive-and-labels.md)
- [0006 Writes Fail Rather Than Guess](0006-writes-fail-rather-than-guess.md)
- [Gmail skill](../../use-gmail/SKILL.md)
- [use-outlook-mail skill](../../use-outlook-mail/SKILL.md)
````
