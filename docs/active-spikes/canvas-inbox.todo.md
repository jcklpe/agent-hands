---
attention: live
reviewed: 2026-11-25
---
# Canvas Inbox tasks
[Scope and choices](canvas-inbox.md). Opened 2026-11-25. Slug: `canvas-inbox`.

## To Do
- [ ] Read live: list a few conversations and read one unread conversation on an authorized account, checking that it stays unread in Canvas.
- [ ] Reply live: one real reply the user wants to send, with its exact text and recipients approved, verified in Canvas.
- [ ] Update the README's Canvas row at closure.

## Done
- [x] Check the current Conversations API. Reading marks messages read unless asked not to; an omitted recipient list means everyone; sending has no duplicate protection and can be queued; a completed course refuses replies.
- [x] List conversations with explicit scope, course and size, reporting `limited` unless the whole scope was listed.
- [x] Read one conversation without marking it read, refusing malformed or duplicated messages and reporting `partial` when messages are missing.
- [x] Preview and send one reply to named people already in the conversation, with a review hash, a journal before sending, one request, readback and recovery.
- [x] Fourteen synthetic tests cover bounds, read state, narrower audiences, changed conversations, refusals, queued messages, lost and altered replies, duplicates and unwritable history. Nothing has run against a live account.
