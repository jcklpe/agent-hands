---
attention: historical
---
# Planner Task chat

Historical record. Closed 2026-11-17. Slug: `planner-task-chat`. Maintained operations, recovery and concurrency limits live in [Use Planner](../../use-planner/SKILL.md). The completed [label verification](lifeos-planner-labels-comments.todo.md) is recorded separately.

Use the current task-associated chat API for new Planner comments. A group post linked through conversationThreadId is a legacy comment, not proof of current Task chat visibility. Keep legacy retrieval explicit and read-only.

The approved scope includes new-message and in-place edit commands, safe rich-text inline links, guarded recovery and current task URLs. Preserve plan/write gates, task fields, existing journals and unrelated work. Read-only browser QA was separately authorized and completed on 2026-11-17. The user approved closure and the exact local commit wording grouping implementation with this archived pair on 2026-11-17. No new permissions, extra live test posts or pushes are authorized. Fixtures and project documentation use synthetic identities only.

The beta Task chat API accepts content containing plain text or sanitized HTML; Markdown must be converted before sending. Human-readable labeled links should be preferred to bare URLs. Inspect modern API message identity and parentEntityId during readback; do not describe this as visual UI verification.

References: [message creation](https://learn.microsoft.com/en-us/graph/api/plannertask-post-messages?view=graph-rest-beta), [message editing](https://learn.microsoft.com/en-us/graph/api/plannertaskchatmessage-update?view=graph-rest-beta), [message listing](https://learn.microsoft.com/en-us/graph/api/plannertask-list-messages?view=graph-rest-beta), [modern and legacy comments](https://support.microsoft.com/en-us/planner/comment-on-tasks-in-microsoft-planner).

## Implementation and limits

Current creation and editing target Task chat directly. The CLI never writes legacy group threads or conversationThreadId. A small shared provider diagnostic exposes the Graph JSON error message without response headers, letting a specific uninitialized-chat response differ from a generic failure. The chat reader handles its empty terminal polling cursor instead of following it indefinitely.

The input defaults to a documented Markdown subset for paragraphs and labeled links; explicit safe HTML is available for emphasis and lists. Duplicate/readback fingerprints include link destinations. Edits require a raw source-content fingerprint and refuse other authors, deleted messages and existing mentions. The beta endpoint documents no ETag conditional edit, so post-read concurrency remains a limit.

Synthetic checks pass, and one specifically authorized existing message was edited in place and verified by API readback. Subsequent read-only QA confirmed the same message's labeled link renders in current Planner and opens its intended SharePoint folder. This verifies the exercised message and destination, not every rich-text style or client. The skill validator could not run without PyYAML; frontmatter and local references were checked manually. Maintained operation, limits and recovery guidance lives in [Use Planner](../../use-planner/SKILL.md). The separate [Planner labels](lifeos-planner-labels-comments.todo.md) record retains its live label PATCH check.
