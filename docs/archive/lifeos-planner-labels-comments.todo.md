---
attention: historical
---
# LifeOS Planner Labels and Comments Tasks
Historical record. Closed 2026-11-18. Slug: `lifeos-planner-labels-comments`. Live label mutation, preservation, repeat no-op and separately approved disposable-task deletion passed on macOS. Maintained commands and limits live in [Use Planner](../../use-planner/SKILL.md) and [GUARD-PLANNER-WRITES](../agent-policies/GUARD-PLANNER-WRITES-preserve-bounded-task-changes.md). Current Task chat has its [separate accepted history](planner-task-chat.md).

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-planner-labels-comments.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-planner](../../use-planner/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

## Done
- Read repo instructions, local LifeOS skills, run-project-spike and commit-work; confirmed canonical tools and preserved the unrelated working-tree edit.
- Checked official task update and group conversation APIs. Configured scopes initially appeared to block comments; unchanged CLI auth metadata confirmed existing effective group read/write permission, so no OAuth expansion was needed.
- Implemented existing-label listing and dry-run-first label/unlabel with unique name resolution, preservation, ETag, attempt audit and readback.
- Implemented task-scoped comment list/add with existing-scope checks, complete bounded reads, text deduplication, private recovery journals, first-thread linkage and preserved-field verification.
- Updated CLI help, README, local M365 skill and policy 0008. Searched the vault skills for affected Planner assumptions; no matches needed updates.
- Offline Planner, comment, shell and renderer regressions pass. Syntax checks and fixture exercise cover bash and zsh.
- Initial live label listing and label command verified: target already had its label, so preview and execute were no-ops. The 2026-11-18 disposable test below verifies the real label PATCH.
- Live comment list, exact preview, first-thread creation, read-only recovery after initial 404, conditional linkage, and independent single-post/task-field verification passed. No duplicate POST occurred during recovery. Private execution evidence stays outside configs.
- Refreshed the canonical snapshot, inspected the final scoped diff and prepared the implementation checkpoint with `Spike: lifeos-planner-labels-comments`.
## Ready for Human QA
- Live label PATCH validation and separately approved deletion passed on an authorized disposable task on 2026-11-18; the already-correct real target was not toggled for testing. Closure and the full archival wording were approved on 2026-11-18.
- Existing-thread legacy reply has offline coverage only. Superseded by current Task chat and explicit read-only legacy retrieval; do not perform a legacy write to satisfy this historical check.
- Current Task chat visual QA passed on 2026-11-17, as recorded in [its archived task record](../archive/planner-task-chat.todo.md); the legacy group-route evidence alone does not prove current Task chat visibility.
## Blocked
None. Implementation, policy and live evidence are committed. Closure and the complete archival wording were approved on 2026-11-18.

## Remaining verification and ownership — 2026-10-31
- Current Task chat, rich links, current task links and in-place edit guidance live in [Use Planner](../../use-planner/SKILL.md). The [closed Task chat record](../archive/planner-task-chat.todo.md) preserves its implementation, synthetic checks, API-readback repair and successful 2026-11-17 browser QA.
- The 2026-11-18 disposable test below completes the live label PATCH check without toggling a correct real target.
- The original existing-thread legacy reply QA was not completed. It is superseded by the current Task chat scope and explicit read-only legacy retrieval; do not revive a legacy write to satisfy that earlier item.

## Disposable label test and explicit deletion — 2026-11-18
- [x] Verify existing account identity, enabled/configured plans and named labels without changing credentials or grants. The prior target still has its requested label; no existing real-task label was toggled.
- [x] Add native preview-first exact-task deletion under the user’s explicit request. Bind the task/details/account snapshot, enforce plan/write gates and task ETag, persist a private exclusive receipt before dispatch, and require complete readback with read-only recovery.
- [x] Verify nine synthetic deletion cases and the existing Planner regression program. Cover stale/missing fingerprints, wrong identity, missing ETags, disallowed plans, disabled writes, private storage, uncertain dispatch/readback and no replay. Bash syntax and the eleven-policy structural check pass.
- [x] Create the authorized unassigned disposable task without a due date or message. Apply one existing label with a real PATCH. Independent readback verifies the category, every unrelated task field except ETag, and unchanged complete details. Repeating the requested label state is a no-op; the private audit contains one label attempt and one verified result.
- [x] Obtain separate exact-task deletion approval after the test, delete once, and verify absence and private receipts. The reviewed fingerprint matched; one conditional DELETE succeeded. A separate read-only verification and independent complete listing confirmed absence and the original task set with unchanged returned task payloads. The private audit contains one deletion attempt; dispatch and confirmation receipts are owner-only.
- [x] Review final acceptance and archival wording; keep the pair active until closure is authorized. Closure and exact wording approved on 2026-11-18; preserve the complete pair as history.

The requested GUARD-PLANNER-WRITES amendment carries its 2026-11-18 decision authority. The user approved temporarily isolating and then restoring the two unrelated Outlook index entries so the Planner implementation, policy and evidence can be committed without other workstreams. Private copies and content checks protect that restoration. Already-approved CLI feedback and mail-triage closure tracking is a separate index checkpoint. This authorization covers local commits, not Planner archival or a push.
