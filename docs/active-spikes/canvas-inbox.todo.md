---
attention: live
status: ready-to-close
reviewed: 2026-11-25
---
# Canvas Inbox tasks
[Scope and choices](canvas-inbox.md). Opened 2026-11-25. Slug: `canvas-inbox`.

## To Do
- [ ] Read one unread conversation live and check that it stays unread in Canvas. On 2026-11-25 the authorized account had none.
  - 2026-11-25: the user chose to skip this and close without it; it is an open check in the Inbox guide, with a new spike if it fails.
- [ ] Reply live: one real reply the user wants to send, with its exact text and recipients approved, verified in Canvas.
  - 2026-11-25: left to the first real reply the user wants to send, under the same terms.
- [ ] Update the README's Canvas row at closure.

## Done
- [x] Check the current Conversations API. Reading marks messages read unless asked not to; an omitted recipient list means everyone; sending has no duplicate protection and can be queued; a completed course refuses replies.
- [x] List conversations with explicit scope, course and size, reporting `limited` unless the whole scope was listed.
- [x] Read one conversation without marking it read, refusing malformed or duplicated messages and reporting `partial` when messages are missing.
- [x] Preview and send one reply to named people already in the conversation, with a review hash, a journal before sending, one request, readback and recovery.
- [x] List and read live on an authorized account, 2026-11-25: a complete seven-conversation listing and three conversations, with nothing changed by reading. It showed that a group conversation's messages can reach only some of its people, so the preview now shows who received the latest message and names recipients who did not, and that Canvas's list dates can miss the newest message.
- [x] Sixteen synthetic tests cover bounds, read state, narrower audiences, changed conversations, refusals, queued messages, lost and altered replies, duplicates and unwritable history.
