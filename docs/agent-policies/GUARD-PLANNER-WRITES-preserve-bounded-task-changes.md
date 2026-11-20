---
id: GUARD-PLANNER-WRITES
type: operational
scope: "Agent use or maintenance of opted-in Planner tasks, labels, messages and moves."
status: adopted
authority: "User's explicit Agent Hands policy-pilot approval, 2026-11-02; explicit request to add task deletion and use a disposable task for live verification, 2026-11-18."
revised: "2026-11-18"
depends_on: ["BOUND-MICROSOFT-ACCESS"]
related_to: ["REJECT-GUESSES"]
---
# Guard Planner changes
Keep Planner opt-in per selected account and configured plan. Writes require write opt-in, preview by default and explicit execution; task updates retain their run-local ETag precondition, readback and ignored audit record. Preserve unrelated task fields. Reads/exports are bounded to selected configured plans and explicit output, not every accessible plan or an implicit cross-service refresh. Basic-plan support does not establish support for other plan types.

Respect [BOUND-MICROSOFT-ACCESS](BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md). Effective Tasks.ReadWrite/User.ReadBasic.All consent can be broader than the selected command surface. No missing permission authorizes grant expansion, new credentials, private endpoints or a browser-session fallback. Any requested-scope change belongs to separately approved setup, not migration verification.

Existing label changes require a unique case-insensitive exact label name, preservation of other categories/fields, the plan allowlist/write gate, ETag checks and readback. Reapplying a state is a no-op. Audit the attempt and recheck label names; do not imply that separate plan/task resources are guarded atomically. Label creation or renaming is not exposed.

Task-associated messages must use the actual supported native interface and exact task. Distinguish current Task chat from legacy group conversations: group-post/task-link readback does not establish current chat visibility. Never use a legacy group-write route as a permission workaround. Preserve bounds, full-read/duplicate checks, private recovery state and locks; do not blindly repeat an uncertain message write. Text/notification effects require the caller's actual authorization. Keep hashes/IDs in audit/recovery records rather than copying private message bodies. Retain journals/locks until uncertain outcomes are resolved, and report non-atomic concurrency limits rather than claiming guaranteed remote deduplication or UI rendering.

Experimental moves remain limited to allowlisted plans in one group and a verified destination bucket, refusing active labels, recurrence or externally sourced tasks. Use one conditional move and verify destination/preserved fields; do not clone/delete or retry an ambiguous write as a fallback. No task archive surface is granted. Report the limits of preservation checks, including unverified goals/custom columns/meeting notes and live checklist/reference/conversation cases, rather than declaring every field preserved.

Task deletion is a separate exact-target operation, requiring isolated explicit consent with the task itemized and a concise reason. Retain a reviewed account/task/details fingerprint, configured-plan and write gates, a fresh snapshot, the task ETag, a durable private dispatch receipt and complete readback. Stop on changed or unknown state. Never infer deletion from a failed read, repeat an uncertain DELETE or delete a task as a fallback for moving it. Reconciliation is read-only; preserve unresolved receipts and report the absence of an undo/restore command and the non-atomic task/details concurrency boundary. Adding the capability or authorizing another task operation does not authorize deletion of any task.

## Enforcement and procedures
[Planner use](../../use-planner/SKILL.md) and [Microsoft setup](../../setup-microsoft-services/SKILL.md) own commands and interface-specific guards. Concurrent Task chat implementation/visual QA remains with its existing owner; this policy migration neither changes that code nor certifies its uncommitted implementation or browser rendering.

## Identity history
This obligation continues the reviewed legacy record [0008](../archive/agent-policy-retirements/0008-lifeos-m365-planner.md), retired as an operative document during this authorized migration. Its source text and numeric identity remain reserved; the history link is not an override or automatic authority transfer.
