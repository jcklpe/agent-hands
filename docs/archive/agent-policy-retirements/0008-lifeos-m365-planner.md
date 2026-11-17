---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0008 policy history
Legacy identity: `0008`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [GUARD-PLANNER-WRITES](../../agent-policies/GUARD-PLANNER-WRITES-preserve-bounded-task-changes.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0008-lifeos-m365-planner.md`. Exact original SHA-256: `d73eb933747296939c6ca386e998575ab20b08d7cdb0e4ca7a4fba63d4920743`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0008-microsoft-365-planner"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="operating-notes"></a>
<a id="rationale-for-limits"></a>
<a id="experimental-move-extension"></a>
<a id="links"></a>
<a id="current-interface-limitation"></a>

````text
# 0008 Microsoft 365 Planner

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
Use `bash use-planner/scripts/planner` (path relative to Agent Hands) as an opt-in surface per account alias, configured with a `planner` block in `m365-accounts.json`.

- **Reads:** `plans`, `buckets`, `tasks` (filters `--bucket`, `--mine`, `--open`), `task` (with description and checklist), and `labels` (existing named plan labels).
- **Scopes:** the implementation requests `Tasks.ReadWrite` and `User.ReadBasic.All` when Planner is enabled. Effective consent is account-specific. The tool limits mutations through `planner.write_enabled`, configured plan allowlists, previews and explicit execution.
- **Snapshot:** `export ALIAS --output PATH` writes the plans listed in `planner.plans` to an explicit caller-selected path, open tasks grouped by bucket and completed tasks in a compact list. Export is limited to the configured plans rather than every accessible plan.
- **Refresh selection:** callers select each account and output explicitly. Aggregate `lifeos sync` is retired; the old `planner.sync` flag no longer triggers or suppresses an aggregate refresh. Workspace policy decides which snapshots to refresh.
- **Writes:** `create-task` and `update-task` (title, bucket, due date, progress, assign and unassign, description). They run only when the alias sets `planner.write_enabled`. Writes are dry-run by default, need `--execute`, and are limited to plans in `planner.plans`. Each update sends `If-Match` with the etag read at the start of that run, so a task someone changed in between is refused rather than overwritten. Every executed write is read back and appended to the audit log (ignored `task-writes.jsonl` beside the owning Planner skill, service `m365-planner`).
- **Labels:** `label` and `unlabel` resolve an existing label by unique case-insensitive exact name, merge its requested state with current categories, and preserve unrelated fields. They use the same allowlist, write gate, dry-run default, ETag and audit boundary. Reapplying a state is a no-op. Attempts are audited before the PATCH; readback compares active categories and all other task properties except the ETag. Plan label names are rechecked before writing, but the separate plan and task resources cannot be guarded atomically. No label creation or renaming is exposed.
- **Legacy group-comment route (historical mechanics):** the earlier `comments` and `comment` operations exposed only a known allowlisted task’s group conversation, not arbitrary group posting. Current Task chat behavior is owned by the use skill and separate runtime verification. The graph-powershell provider must already have the documented effective permission: [post listing](https://learn.microsoft.com/en-us/graph/api/conversationthread-list-posts?view=graph-rest-1.0) accepts `Group-Conversation.Read.All` or a documented higher permission; [thread reply](https://learn.microsoft.com/en-us/graph/api/conversationthread-reply?view=graph-rest-1.0) and [thread creation](https://learn.microsoft.com/en-us/graph/api/group-post-threads?view=graph-rest-1.0) require delegated `Group.ReadWrite.All`. Scope inspection reconnects with the unchanged configured scope request and examines only auth metadata. It never adds permissions, creates credentials, uses private endpoints or browser sessions. Missing permissions stop the operation for approval.
- **Legacy group-write mechanics (historical):** the earlier path had the same allowlist/write gate and dry-run default as task writes. Preview the exact file text and the possibility of Microsoft 365 group notifications. Read the full linked thread for text duplicates, bounded at 20 pages/1000 posts; reject partial reads. Compare whitespace-normalized visible text after HTML conversion. A first comment creates a group thread and conditionally links it through `conversationThreadId` using the original task ETag. Verify both the post and task link, plus unrelated task fields. Audit hashes and post/thread IDs rather than copying comment bodies into logs. A private per-task recovery journal and lock beside the audit log guard local retries. If creation has no known returned ID, stop for inspection; never blindly repeat. A known created thread can be linked after verifying its post, without reposting. An uncertain reply is retried only as a read: if the text is not visible, stop. Remote concurrent identical posts cannot be atomically deduplicated by the group API. Preserve journals/locks until outcomes are resolved.
- **No delete** is exposed.

## Rationale
Configured team plans need to be ordinary local context, with bounded task updates when authorized. The implementation targets basic Planner plans. The portable runtime cannot assume tenant-wide consent. CLI opt-in, plan allowlists, previews and ETag guards bound its supported write operations.

## Operating Notes
- Refresh a configured plan through its explicit service export; the calling workspace owns its destination and freshness requirements.
- Plan changes may be visible to other team members. The caller must authorize the selected task and change after reviewing its effects.
- The etag guard protects within one run; it cannot detect changes made between a dry run and a later `--execute`, which re-reads the task and shows its current state again.
- Enabling Planner adds `Tasks.ReadWrite` and `User.ReadBasic.All` to the requested scopes. Any change to the requested set needs one interactive `bash setup-microsoft-services/scripts/authorize auth ALIAS` (run in a real terminal; `--no-browser` uses a device code) before Planner calls work; until then they stall waiting for sign-in.

## Rationale for Limits
- **Read-only account intent:** supported command gates remain separate from the provider credential’s broader permission. Select and verify account access explicitly; narrower-scope transport work would be a separate change.
- **Snapshotting every plan from `/me/planner/plans`.** This exceeds the explicitly configured export selection.
- **Implicit cross-service refresh.** A request for one domain does not select every other enabled service; refresh composition belongs to the calling workspace.

## Experimental Move Extension
The experimental extension provides dry-run-first `move-task --task ID --plan ID --bucket ID` using the [documented Graph beta task update](https://learn.microsoft.com/en-us/graph/api/plannertask-update?view=graph-rest-beta). The current implementation limits moves to two allowlisted plans in the same Microsoft 365 group, validates bucket membership, refuses active labels, recurrence and externally sourced tasks, and uses one ETag-guarded PATCH. It audits the attempt and verifies the destination and supported preserved fields. It never clones or deletes tasks and never retries an ambiguous write. Goals, custom columns and linked meeting notes remain outside verification. Offline tests are available. Same-group moves were validated live on 2026-10-11 with readback confirming task IDs, descriptions, assignments, dates, progress, priority and destinations. Nonempty checklist/reference and conversation preservation remains unverified live.

## Links
- [use-planner skill](../../use-planner/SKILL.md)
- [0004 LifeOS Microsoft 365 Access](0004-lifeos-microsoft-365-access.md)
- [0006 Writes Fail Rather Than Guess](0006-writes-fail-rather-than-guess.md)
- [0007 Mail Archive, Folders, And Labels](0007-mail-archive-and-labels.md)

## Current interface limitation
Legacy Microsoft 365 group conversations and current Planner Task chat are distinct interfaces. Verification of a group post and task link does not establish visibility in Task chat. The current route is documented by the [use skill](../../use-planner/SKILL.md) and [Task chat scope](../active-spikes/planner-task-chat.md); visual link rendering remains human QA in that scope. The older [labels/comments record](../active-spikes/lifeos-planner-labels-comments.md) retains its historical group-route evidence and remaining live label check. This cleanup does not equate API readback with visual verification.
````
