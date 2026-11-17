---
id: BOUND-MAIL-RULES
type: operational
scope: "Agent use or maintenance of Gmail filters and Outlook Inbox rules."
status: adopted
authority: "User's explicit Agent Hands policy-pilot approval, 2026-11-02; recorded in agent-policy-pilot."
revised: "2026-11-02"
depends_on: ["BOUND-MAIL-WRITES"]
related_to: ["BOUND-MICROSOFT-ACCESS"]
---
# Bound standing mail automation
Every particular standing rule requires user authorization for its complete conditions and actions; enabling the capability is not autonomous permission over future mail. Retain separate per-account filters/rules opt-ins, preview by default, explicit execution, exact rule IDs for removal, readback and audit. Grant changes need approved interactive setup, not assumed tenant consent. Rules affect new mail only; do not silently apply them retroactively.

Gmail filter creation may match sender, recipient, subject and query, then add one user label and/or skip Inbox. A dry run shows recent matches for the equivalent query. Outlook rule creation may match the supported sender/subject/recipient selectors, assign a category, move to a folder permitted by [BOUND-MAIL-WRITES](BOUND-MAIL-WRITES-limit-reversible-filing.md), and stop further processing. Forwarding, redirect, permanent deletion, marking read and replying remain unavailable. Listing may reveal such actions on rules made elsewhere without authorizing their creation here.

Rule deletion is allowed because it removes a recreatable rule, not messages. Read back a created rule's enabled state, sequence, complete conditions/exceptions/actions, or verify a deleted rule is gone. Accept only documented default empty/false values and case normalization; reject omitted/broadened predicates or unexpected actions.

## Duplicate-mail exception
The existing narrow Microsoft duplicate-mail capability may move future matched duplicates to Deleted Items only with exact sender selectors and complete recipient-address conditions. It must not mix deletion with category/folder actions. Permanent deletion and one-off message deletion remain refused. Recipient matching is To/Cc text, not canonical mailbox/alias identity. The consuming workflow must authorize the exact rule and retained-copy intent; this exception grants neither autonomous deletion decisions nor a general delete command.

## Enforcement and procedures
[Gmail](../../use-gmail/SKILL.md), [Outlook mail](../../use-outlook-mail/SKILL.md) and their setup owners supply the actual command/permission/readback mechanics. The exception's historical approval/source is retained in legacy record 0009 rather than treated as a new consumer instruction.

## Identity history
This obligation continues the reviewed legacy record [0009](../archive/agent-policy-retirements/0009-mail-filters-and-rules.md), retired as an operative document during this authorized migration. Its source text and numeric identity remain reserved; the history link is not an override or automatic authority transfer.
