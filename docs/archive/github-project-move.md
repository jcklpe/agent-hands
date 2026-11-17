---
attention: historical
closed: 2026-11-17
---

# GitHub Project Move Reliability
Historical record — closed 2026-11-17. Stable slug: `github-project-move`. The complete development record is retained below; use [maintained guidance](https://github.com/jcklpe/agent-hands/blob/aaf5f3f1d6c9c5c67095806d3b1e07fc9da85461/use-github-projects/references/collaboration.md) for current behavior and limits. Closure and the exact archival wording were approved.
Opened: 2026-10-27. Slug: `github-project-move`.

A project-card move reported an unset status despite the card having a status, then attempted execution with a null item identifier. The separately recovered live card must not be moved again as a test. This approved repair uses only synthetic responses and keeps repository choices and credentials outside public code.

The original item query had an unmatched selection brace and its command result was not checked. Nonempty error JSON could therefore be interpreted as an item. Repair the query and validate transport results, GraphQL errors, pagination completeness, unique item selection, node identifiers and status shapes before displaying a plan. Only an explicit null status means No Status. A request failure must never become a plan or a mutation.

Default preview and explicit execution remain separate. Confirm the mutation response identifies the selected item; failure after sending it is uncertain and must not trigger a blind retry. This does not promise an independent state readback or immunity to changes made concurrently by another actor. Keep the first configured organization project and Status-field scope; no new account setup, generic API route or broader board operations.

See the [task record](github-project-move.todo.md). Local commits are authorized; publication, history rewriting and later Windows installation remain separate work.

The native CLI regression reproduced the false No Status plan before the repair. The corrected query and validation now pass synthetic preview/execution tests and the existing GitHub regression programs. Publication remains a separate decision after reviewing historical compatibility material and the documented scan limits.

## Closure preparation — 2026-11-17
The published Projects collaboration runtime supersedes this original repair and retains its malformed-response, target-identity and explicit-null protections. All 13 move-card regressions passed against the public implementation during this review. Its stronger actor/fingerprint/journal/readback contract is maintained in the [published Projects guide](https://github.com/jcklpe/agent-hands/blob/aaf5f3f1d6c9c5c67095806d3b1e07fc9da85461/use-github-projects/references/collaboration.md); the selected API validation and provider closure are recorded in the [published collaboration archive](https://github.com/jcklpe/agent-hands/blob/aaf5f3f1d6c9c5c67095806d3b1e07fc9da85461/docs/archive/github-collaboration-operations.todo.md). The source checkout predates those changes, so its older implementation and publication-hold language must not overwrite the newer public runtime. This repair is ready for closure as superseded, without repeating the recovered live move. Windows/fresh-client validation remains unproved. See the closure review (local preparation record); no local archival has occurred.
