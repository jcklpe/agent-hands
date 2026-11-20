---
attention: historical
---
# Gmail attachments and manually sent drafts

Historical record. Closed 2026-11-17. Slug: `gmail-attachments-drafts`. Maintained commands and safeguards live in [Use Gmail](../../use-gmail/SKILL.md) and the [mail-write policy](../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md).

The requested capability adds attachment listing/downloading and draft creation to the native Gmail CLI. The user reviews and manually sends drafts; sending remains outside the native surface. Private mailbox source material, account identifiers and document contents stay outside this repository.

Exact message/part selection, safe explicit output paths and verified binary sizes preserve attachment evidence. Drafts preview all recipients, body and attachments, require an action-time opt-in for the selected account, verify mailbox identity and read back the created content. They do not infer recipients, add signatures, accept agreements or automatically retry an uncertain creation.

Google offers no draft-only OAuth scope. Existing modify/compose grants can create drafts and authorize sending at the API level. This implementation exposes no send operation and rejects send endpoints in the mutation transport, but is not a security sandbox against direct use of credentials outside the CLI. No credentials, existing grants or persistent account flags are changed by this work.

The narrowly authorized BOUND-MAIL-WRITES amendment retains its identity and all existing filing/rule boundaries. Its incoming standing-rule dependent is unchanged; draft creation adds no standing reply/forward rule. Gmail's skill and README gain the new operations; Outlook remains unchanged. See [tasks and verification](gmail-attachments-drafts.todo.md).
