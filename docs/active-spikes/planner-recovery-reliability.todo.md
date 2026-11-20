---
attention: live
---
# Planner recovery reliability tasks
## Done
- Reproduced false deletion confirmation when an exact task lookup still succeeds or fails while the old plan no longer lists the task. Added a GET-only batch read requiring exact 404 plus the existing complete plan check; uncertain/denied reads remain unresolved.
- Task chat now rechecks its message view after taking the shared lock and refuses a stale pre-lock view.
- Task chat journals atomically replace owner-only files with file and directory fsync before transport. Sync failure preserves the prior receipt and stops subsequent dispatch; private path checks refuse symlink and exposed state.
- All 22 Planner Python checks and the synthetic Task chat command suite pass, including new moved-task, denied-read, sync-failure and pre-lock-change cases. No live Planner mutations were sent.
## Remaining
- Complete outgoing-history review and publication with the containing reconciliation. Keep the documented remote concurrency limitations and prior live-validation scope explicit.
