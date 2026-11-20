---
attention: historical
---
# Planner Task chat tasks

Historical record. Closed 2026-11-17. Slug: `planner-task-chat`. Maintained operations, recovery and concurrency limits live in [Use Planner](../../use-planner/SKILL.md). The completed [label verification](lifeos-planner-labels-comments.todo.md) is recorded separately.

## To Do

## Ready for Human QA
No remaining visual link check. Separately authorized read-only browser QA passed on 2026-11-17. The user approved closure and the exact local commit wording grouping implementation with this archived pair on 2026-11-17. Publication remains outside this authorization.

## Done
- Confirm labeled links render and open correctly in current Planner after the authorized in-place repair. — Verified 2026-11-17: native readback returned the exact repaired message on its parent task; the current Planner UI displayed the labeled hyperlink, and following it opened the intended SharePoint folder. No message was posted or edited and no task fields were changed. The four Planner shell programs and ten content unit tests passed again. Live identities, URLs and browser snapshots remain outside public source.
- Inspected current implementation and official Task chat create/list/update contracts. Current writes target legacy group conversations.

- Implement current Task chat reads, creation and in-place editing, keeping explicit legacy reads. Implemented beta Task chat collection and message routes; legacy groups are read-only behind --legacy.
- Serialize safe inline links and rich text, and verify links survive readback. Markdown inline links serialize to escaped anchors; explicit allowlisted HTML is supported. Verification compares text, labels and destinations.
- Preserve preview/write gates, plan ownership, no ambiguous retries and recovery state. Separate ignored journals preserve uncertain create/edit state; own-message edits require the previewed source hash. Signal cleanup retains journals and releases locks.
- Generate current Planner task links. Current planner.cloud.microsoft URLs include a configured or existing-SDK tenant ID when available, without new grants.
- Add offline tests for association, pagination, legacy isolation, link safety and uncertain outcomes. Four Planner shell programs, ten content unit tests and the synthetic provider PowerShell program passed. Polling cursors, link stripping and uncertain outcomes have explicit checks.
- Update use-planner guidance and command help. Skill now defaults to concise labeled links and distinguishes API readback from browser rendering. Manual frontmatter/reference checks passed; quick_validate lacks PyYAML in available runtimes.
- Repair the already-authorized existing message in place after offline tests pass; do not create extra live messages. Applied the authorized repair with PATCH, retaining the original message ID. Independent CLI readback returned one message, the exact parent task and the labeled anchor. No extra live posts or browser use.
- Review scoped diffs, privacy and concurrent-work preservation. Do not commit or push. Reviewed selected implementation diffs and new files. No live identities, target IDs, personal paths or recognizable credentials in scoped public files. Existing unrelated work preserved; no commits or pushes.

## Closure — 2026-11-17
The successful browser check completes the selected Task chat acceptance scope. Keep the implementation, command help, skill guidance, new tests, private-state ignores and the small provider diagnostic change together in the archival commit. The synthetic provider PowerShell check passed again without account access. Maintained operation and recovery guidance lives in [Use Planner](../../use-planner/SKILL.md). The beta edit endpoint's lack of a documented conditional ETag remains an explicit concurrency limit, not a completed guarantee. The separate [label PATCH check](lifeos-planner-labels-comments.todo.md) remains open. No new live message, edit, permission or push is needed for closure.
