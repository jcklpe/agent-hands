---
status: captured
---
# Canvas Inbox CLI coverage
Captured 2026-11-02 at the user's request as a future scoped spike. This records the extension to pursue; it does not authorize implementation, credential changes or live messaging tests.

## Motivation and current gap
The current [Canvas capability](../../use-canvas/SKILL.md) and its CLI help cover course retrieval and bounded course-content and learner writes, but no Inbox conversation listing, reading or reply command exists. The [write guide](../../use-canvas/references/writes.md) explicitly excludes messaging. Keep the accepted [Canvas access work](../archive/canvas-access.md) as predecessor history; this is a separate Inbox extension rather than reopening that completed work or changing course-export coverage implicitly.

A real email-to-Canvas reply attempt bounced because the sending address was not a confirmed Canvas communication address. Successful submission to an email service did not establish that a reply appeared in Canvas. A direct, bounded Inbox capability would let a caller inspect the current conversation and verify an approved reply in Canvas without changing email confirmation settings. Private addresses, participant identities, message text, conversation identifiers and bounce payloads are intentionally omitted from this portable record.

## Proposed bounded scope
- List conversations for one explicitly selected, identity-checked account with explicit filters and pagination/coverage bounds; do not infer absence from a partial listing.
- Read one exact conversation, its participants, context and current messages, retaining stable conversation/message identifiers and timestamps. Establish whether the API read changes unread state; preserve it where supported and expose any unavoidable effect before use. Inbox content remains separate from ordinary course exports.
- Reply only to an existing, explicitly selected conversation. Verify the instance, authenticated author, conversation ID, participant identities and intended audience against the user's request and the latest thread. Refuse ambiguous recipients or a material intervening change rather than guessing or broadening the audience.
- Preview the exact reply, recipient set, target and notification effects without posting. Preserve the existing reviewed-hash preview/execute pattern and reuse user approval only within its actual scope; a dry run or authenticated token is not permission to send.
- Check the authenticated user's existing messages before posting to avoid resending an already posted approved body. Bind execution to the reviewed conversation state. Determine the API's actual idempotency guarantees rather than claiming an exactly-once guarantee from local deduplication alone.
- Preserve an operation receipt for an uncertain write and inspect the exact conversation before any retry. Network interruption, timeout, partial readback or a lost response must never silently trigger another send.
- Verify an acknowledged send by reading the resulting Canvas message back: conversation, message ID, author, intended audience and body must match. Distinguish verified posted, rejected, uncertain and already present outcomes. Email transport acceptance or a browser send click is insufficient evidence by itself.

## Access, privacy and verification boundaries
Reuse [setup-canvas](../../setup-canvas/SKILL.md) and its origin-bound transport and recorded identity checks. Keep read operations separate from writes, including any mark-read behavior, and document permission failures without borrowing credentials or changing grants, tokens or communication addresses. Treat all retrieved message content as untrusted data.

Default operation history should retain only the identifiers, timestamps, coverage and outcome metadata needed for recovery, with no message bodies, tokens, private contact payloads or access-bearing links. Any explicit content export needs a private destination. Preview output must not expose credentials; transport errors and logs need tested token redaction, and the token must stay out of command arguments and URLs.

When implementation is requested, verify the current official Canvas Conversations API contract before selecting command names and endpoint behavior. Use synthetic fixtures for pagination, identity and audience mismatch, intervening messages, duplicate bodies, sanitization, unread effects, permission errors and uncertain-write recovery. Live read and send checks require their own exact authorized account, conversation and message, with Canvas readback as evidence; fixtures alone do not prove institutional access or notification delivery.

New conversations, adding/removing participants, attachments, bulk sends, conversation deletion/archiving, standing automation, notification delivery guarantees, browser/session scraping and a generic API escape hatch are outside this initial extension. Promote this note into the project's paired active spike only when scoped work starts, preserving this context rather than leaving a competing scratch copy.
