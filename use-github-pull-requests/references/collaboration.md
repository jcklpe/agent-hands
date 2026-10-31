# Pull-request collaboration
Read the setup-owned [collaboration runtime contract](../../setup-github/references/collaboration.md) before execution or recovery. It owns identity/target checks, fingerprint matching, project-owned ignored journals, outcomes and bounded coverage. This skill owns PR semantics, exact refs, review anchors and integration verification.

## Inspection and preparation
From the collection root:
```sh
bash use-github-pull-requests/scripts/github read-pr --repo example-owner/example-project --pr 42 --fields pr,files,checks,reviews,threads --json
bash use-github-pull-requests/scripts/github create-pr --repo example-owner/example-project --actor example-user --head feature --base main --expected-head FULL_SHA --title 'Contribution overview' --body-file /tmp/pr.md --json
```
Creation previews by default and starts as draft unless `--ready` is explicitly selected. Both branches must already exist remotely, and the head must match the full expected SHA. An open matching head/base PR refuses. `--head-repo OWNER/REPO` selects an explicit same-host fork; the tool verifies that repository and its branch before sending. No fork, push, local branch switch or implicit publication is performed. Maintainer editing is enabled only with `--maintainer-edit`.

| Command | Selected operation |
| --- | --- |
| `read-pr --pr NUMBER` | Exact open/closed/merged PR, head/base repository/ref/OIDs and selected evidence. `--fields` selects `pr,commits,files,comments,reviews,review_comments,threads,checks,statuses`; default is all. |
| `read-thread --pr NUMBER --thread-id NODE_ID` | Exact-parent thread and bounded replies. |
| `create-pr` | Explicit published head/base/title/body/draft state, optional repeated label/assignee/reviewer/team-reviewer selection and independently verified follow-up steps. |
| `edit-pr --pr NUMBER` | Title/body, repeated add/remove label/assignee/reviewer/team-reviewer changes, `--draft`/`--ready`, and explicit `--base` retargeting. Retargeting previews its changed review meaning. |
| `close-pr` / `reopen-pr --pr NUMBER` | Explicit PR state change with readback. |
| `comment-pr --pr NUMBER` | A conversation comment, separate from formal review. |
| `review-pr --pr NUMBER --expected-head SHA --event EVENT` | Exact body and explicit `COMMENT`, `APPROVE` or `REQUEST_CHANGES`; submit against that commit and verify review ID/state/commit independently. |
| `inline-comment --pr NUMBER --expected-head SHA --path FILE --line N` | Exact body and inspected diff anchor; optional `--side LEFT` (default RIGHT) and `--start-line N` for a same-side range. Unavailable or out-of-diff anchors refuse. |
| `reply-review-comment --pr NUMBER --expected-head SHA --comment ID` | Exact-parent reply to an original top-level inline comment. |
| `resolve-thread` / `unresolve-thread` | Explicit `--pr`, `--thread-id` and `--expected-head`; verify thread parent, current context and actor permission before sending, then read resolution back. Outdated or incompletely read context refuses. |
| `assess-merge --pr NUMBER` | Read mergeability, active rules/protection, current checks/statuses, reviews, original commits and integration blockers; never grants merge permission. |
| `merge-pr` | Separately discussed integration; exact guards and restrictions below. |
| `recover --operation-id ID` | Read/reconcile recorded results without resending or automatically finishing a compound action. |

Use nonempty UTF-8 `--body-file` or literal `--body` for comments and comment/request-changes reviews; an approval may omit its body. Approval is an explicit verdict; inspecting code or drafting feedback does not authorize submitting it. Reviews/inline comments are bound to a commit, but re-reading the head before/after a request cannot make GitHub's review submission an atomic compare-and-swap. A changed head after sending is reported as uncertain and needs inspection.

Inspect every `coverage` family and `revision_stable`. Returned patches may be absent for binary/large files or omitted at the selected byte limit; even present patches are only what GitHub returned. Incomplete evidence is never described as a complete code review. Metadata-only legacy exports remain available, with their original limits.

## Separate integration step
Human/agent discussion must assess the actual contribution, acceptance evidence, interactions with other changes, required review and the intended history before integration. The tool requires `--integration-discussed`, explicit `--method merge|squash|rebase`, the inspected `--expected-head`, then the usual matching preview/execution guards. The acknowledgment is not proof that a conversation occurred or permission beyond the user's actual scope.

For a project requiring original atomic commits and workflow documents, select `--preserve-history --method merge` and repeat `--require-path RELATIVE_FILE` for required tracked documents. The preview rejects incompatible linear-history requirements or unsupported methods; readback verifies original commit reachability and required files at the resulting merge commit. This history policy is supplied by the consuming project, not imposed on every GitHub consumer.

The selected route is `PUT /pulls/NUMBER/merge-async` with `merge_action=direct_merge`, `bypass_rules=false` and the expected head. Pending results receive up to five read-only polls; a still-pending request remains uncertain and can be checked with `recover`. No mutation is retried. Queue/auto-merge, stacked PRs, known automatic branch deletion, non-clean merge state, failed/missing required checks or approvals, incomplete evidence and unsupported rule types refuse. No protection/settings change, administrative bypass, strategy substitution, branch deletion or push is performed. Older servers without this schema/endpoint cannot use this integration route.

The server head guard protects the selected head. Independent readback also checks merge-commit parents against the discussed base/head and verifies that the source branch remains at the selected head; unexpected movement is uncertain even when integration occurred. Re-reading the base/rules cannot atomically exclude a base/settings change after the final read; this race is exposed in the preview. Linked issue closures and repository automation are visible effects. A merge response is not success until independent PR and requested history/document readback succeeds. Unexpected queued/enqueued outcomes remain uncertain rather than being represented as an immediate merge.

Branch update/push operations, review dismissal/deletion, pending-review batches, repository administration and arbitrary API calls are outside this command set. Each supported operation is separately invocable; creation, review, integration and issue/spike closure never run as an automatic lifecycle.
