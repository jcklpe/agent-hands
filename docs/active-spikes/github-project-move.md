---
attention: live
---

# GitHub Project Move Reliability
Opened: 2026-10-27. Slug: `github-project-move`.

A project-card move reported an unset status despite the card having a status, then attempted execution with a null item identifier. The separately recovered live card must not be moved again as a test. This approved repair uses only synthetic responses and keeps repository choices and credentials outside public code.

The original item query had an unmatched selection brace and its command result was not checked. Nonempty error JSON could therefore be interpreted as an item. Repair the query and validate transport results, GraphQL errors, pagination completeness, unique item selection, node identifiers and status shapes before displaying a plan. Only an explicit null status means No Status. A request failure must never become a plan or a mutation.

Default preview and explicit execution remain separate. Confirm the mutation response identifies the selected item; failure after sending it is uncertain and must not trigger a blind retry. This does not promise an independent state readback or immunity to changes made concurrently by another actor. Keep the first configured organization project and Status-field scope; no new account setup, generic API route or broader board operations.

See the [task record](github-project-move.todo.md). Local commits are authorized; publication, history rewriting and later Windows installation remain separate work.

The native CLI regression reproduced the false No Status plan before the repair. The corrected query and validation now pass synthetic preview/execution tests and the existing GitHub regression programs. Publication remains a separate decision after reviewing historical compatibility material and the documented scan limits.
