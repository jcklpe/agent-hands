# Exact issue operations
Read the setup-owned [collaboration runtime contract](../../setup-github/references/collaboration.md) before executing writes or recovering an uncertain result. It owns actor/target checks, preview fingerprints, project-owned ignored journals, result/exit semantics and coverage limits.

From the collection root:
```sh
bash use-github-issues/scripts/github read-issue --repo example-owner/example-project --issue 42 --json
bash use-github-issues/scripts/github edit-issue --repo example-owner/example-project --actor example-user --issue 42 --body-file /tmp/replacement.md --json
```
The second command previews. Execute the exact authorized proposal by repeating its inputs with `--execute --expect FINGERPRINT --operation-id OPERATION_ID`. Select the matching checkout with `--project` or the explicit private recovery location with `--state-dir`. Refer to each command's `--help` for its actual flags.

| Command | Selected operation |
| --- | --- |
| `read-issue --issue NUMBER` | Exact open/closed issue, current fields and bounded comments. `--fields issue,comments,coverage` selects response families. A PR number refuses. |
| `create-issue --title TEXT` | Optional literal/file body, repeated `--label`/`--assignee`, and `--assign-me`; independent created-item readback. Identical existing issues refuse unless `--allow-duplicate` explicitly requests another. |
| `edit-issue --issue NUMBER` | Optional title/body replacement, repeated `--add-label`/`--remove-label` and `--add-assignee`/`--remove-assignee`, or `--assign-me`. Only selected fields enter the stale-state baseline. |
| `comment-issue --issue NUMBER` | Append the nonempty supplied literal/file body; independent comment-ID readback and retry reconciliation. |
| `close-issue --issue NUMBER` | Explicit closure with `--reason completed` (default) or `--reason not_planned`. |
| `reopen-issue --issue NUMBER` | Explicit reopening; never automatic rollback. |
| `recover --operation-id ID` | Reconcile recorded intent through fresh reads. `--result-id` selects an independently inspected issue number or comment ID when needed. |

Close/comment are separate operations: if both are requested, execute/read back each and preserve any partial result. Closing an issue does not mean project acceptance or spike closure. Labels/assignees are resolved before sending; selected sets preserve unrelated values and are checked against their observed baseline. All resulting changed fields are independently read back.

No comment editing/deletion, issue deletion/transfer, repository creation, milestone/Projects automation, arbitrary API calls or pushes are exposed. Bulk `export` retains its existing open-only behavior and legacy comment-coverage limits; use exact reads for collaboration verification.
