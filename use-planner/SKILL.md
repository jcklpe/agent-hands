---
name: use-planner
description: "Read Microsoft Planner plans, buckets, tasks, labels, and comments; export configured plans or preview supported task changes. Use for bounded Planner operations, including conditional updates and comment recovery."
---

# Use Planner
Requires only [authorize-microsoft](../authorize-microsoft/SKILL.md), Bash 3.2+, jq, and this skill's Python 3.11+ environment. Follow [setup-microsoft-services](../setup-microsoft-services/SKILL.md) for onboarding. Run `uv sync --locked` here, or supply a compatible `M365_PYTHON`. No mail, files, personal workspace, or other task platform is required.

## Entry and configuration
Run `bash scripts/planner --help` from this folder for the exact arguments. Commands are `plans`, `buckets`, `tasks`, `task`, `export`, `labels`, `label`, `unlabel`, `create-task`, `update-task`, `move-task`, `comments`, and `comment`. Reads need `planner.enabled`. Configure plan IDs in the provider's ignored account JSON; writes are restricted to those plans and require both `planner.write_enabled` and `--execute`. A preview may read current remote state; it is not an offline simulation.

```sh
bash scripts/planner tasks example --plan PLAN_ID --mine --open
bash scripts/planner task example --task TASK_ID
bash scripts/planner export example --output /chosen/existing-directory/planner.md
bash scripts/planner update-task example --task TASK_ID --progress done
bash scripts/planner comment example --task TASK_ID --file /chosen/comment.txt
```

Exports cover configured plans, bounded tasks (default 500 per plan), descriptions/checklists, buckets, labels, and user names. They require an explicit output file, reject output symlinks, and preserve the previous file if retrieval or rendering fails. Failed task-detail requests fail the export; unavailable user names warn and retain IDs. Paging caps can produce a deliberately bounded view. Exports contain private task content: choose a private destination. Workspace snapshot locations and task conventions belong to the caller.

## Write behavior and limits
Task creation/updates support the fields shown in help, including title, bucket, due date, progress, assignees, and description. Date-only due values are sent at noon UTC and may display on a different local date in some timezones. Updates use ETags and read back supported changed fields. Creation followed by description assignment can partially succeed; preserve the created task ID rather than recreating it. Readback is field-specific, not a transaction guarantee.

Labels operate on an existing uniquely named category, recheck its binding, and preserve other active labels. `move-task` is experimental Graph beta support: only allowlisted plans in the same group, a destination bucket in that plan, an ETag, and tasks without active labels, recurrence, or creation-source metadata. It performs one conditional move and verifies preserved fields. There is no clone/delete fallback or automatic retry of uncertain mutations. No delete/archive command is exposed.

Comments use group conversation threads and can notify group members. They currently require the Graph PowerShell route and existing effective group-conversation permissions; the tool does not add those scopes to the configured grant. Checking the SDK context can invoke authentication. The text file is limited to 10,000 characters. Readback is capped at 20 pages/1,000 posts and refuses incomplete history. Duplicate checks normalize HTML and whitespace.

A comment may require both creating a thread and linking it to the task, which is not atomic. A per-task lock and private journal track attempts. A known created thread can be linked on recovery without reposting. An uncertain create/reply stays blocked until its outcome is reconciled; do not delete the journal to force a retry. Preserve thread/post/task IDs and inspect the reported partial state.

## Private state and verification
Audit defaults to ignored `task-writes.jsonl` beside this skill; `M365_PLANNER_AUDIT_LOG` in the provider env can select another private path. Relative paths resolve here. Comment recovery files live in `planner-comments/` beside that log and must remain private. Audit is best-effort; comment journaling must succeed before dispatch, but this is not a fail-closed audit guarantee for all task writes.

Offline command, comment-recovery, batch-response, and export checks use synthetic transport/data. They verify existing gates, conditional writes, readback failures, no blind retries, and output preservation without accessing a real account. Tenant permissions and live beta-move behavior remain unverified.
