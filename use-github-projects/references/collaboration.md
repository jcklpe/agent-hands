# Projects operations
Use the sibling setup's [collaboration runtime contract](../../setup-github/references/collaboration.md) for actor/host checks, private project journals, fingerprints, result codes and read-only recovery. Every mutation previews by default. This capability requires only its own scripts and `setup-github`; unrelated services and Project Workflows are optional.

## Selection and bounded reads
Select `--repo [HOST/]OWNER/REPO`, then `--owner LOGIN` with `--project-number NUMBER`, or select `--project-id NODE_ID`. The owner defaults to the configured project owner or repository owner; an explicit project ID must belong to it. The owner is independently resolved as an organization or user, and project ID/number/owner/URL must agree. A configured alias retains its first-project default. `--project CHECKOUT` selects local recovery storage, not a GitHub board.

| Command | Scope |
| --- | --- |
| `read-project` | Metadata and selected `--fields project,fields,views,workflows,repositories,items`; items are opt-in. |
| `read-view --view-id ID` | Exact-project view metadata and separately bounded visible-field configuration. |
| `create-project --title TEXT [--link-repository]` | Create under the selected owner, optionally linking only the explicitly selected repository. Duplicate titles refuse; select the existing project ID for repeat setup. |
| `copy-project --title TEXT [--new-owner LOGIN]` | Copy the selected source to an explicitly resolved destination owner. Draft issues are excluded. |
| `link-repository` | Add only the selected repository; preserve other links; already linked is a verified no-op. |
| `ensure-field --name TEXT --data-type TEXT\|NUMBER\|DATE\|SINGLE_SELECT` | Create a missing field or provision the selected existing single-select options. Type replacement refuses. |
| `create-view --name TEXT --layout table\|board\|roadmap` | Create a selected layout; a matching existing view is a no-op. Use exact view ID for further changes. |
| `edit-view --view-id ID` | Selected `--name`, `--layout`, `--filter` or repeated `--visible-field FIELD_ID` changes; preserve unspecified properties. |
| `add-item --issue N` / `--pr N` | Explicitly add that repository's exact issue/PR; existing membership is a no-op. |
| `move-card --issue N` / `--pr N --status NAME` | Change only the selected item's single-select value; `--field-name` defaults to `Status`. Missing membership refuses. |
| `automation-config --mapping-file FILE` | Resolve semantic stage names to verified, nonsecret lifecycle-starter variables; no service writes. |
| `recover --operation-id ID [--result-id NODE_ID]` | Reconcile existing intent without resending; exact result selection can resolve ambiguous creation evidence. |

Project collections default to 20 pages/2,000 items, with explicit completeness and read revision stability. Incomplete/ambiguous relevant evidence refuses a mutation. A malformed API/error envelope never means an empty project or an unset status. Read results may retain useful families with explicit incomplete coverage elsewhere. Missing visible-field configuration is a reported gap; it does not authorize overwriting unknown settings. A new configuration write requires readable configuration evidence first.

## Ordered options and preservation
For a single-select field, `--options-file` accepts a UTF-8 JSON array of selected options:
```json
[
  {"name": "Backlog", "color": "BLUE"},
  {"name": "Active", "color": "GREEN"},
  {"name": "Done", "color": "PURPLE"}
]
```
Colors are `GRAY`, `BLUE`, `GREEN`, `YELLOW`, `ORANGE`, `RED`, `PINK` and `PURPLE`. New options default to gray and an empty description. Omitted color/description on an existing option are preserved. Select an unchanged option by its unique name; an explicit existing `id` can rename that option while keeping cards bound to the same ID. An ID from another field, a repeated ID or a colliding final name refuses.

Selected options are ordered first; unselected options remain afterward in their original order. Every existing option ID and its intended name/color/description mapping is independently checked after mutation. Unrelated fields and their observed shape remain intact. At most 50 merged options and 64 KiB of JSON input are accepted. Deleting options/fields and replacing field types are outside this capability. Exact repeat provisioning is a fresh verified no-op.

Visible-field changes similarly put selected fields first and retain unselected visible fields. Each field must belong to the actual project. An empty visible-field replacement is not exposed. Basic view creation and a later filter edit are separate operations, each with its own preview/readback. Grouping, vertical grouping, sorting and Insights configuration have no supported setter here.

## Creation, copy and automation limits
Creation/copy use GitHub's default visibility; readback reports the actual public/private result. Do not add content until that result matches the selected setup. No automatic visibility/settings change follows creation.

[GitHub's copy contract](https://docs.github.com/en/issues/planning-and-tracking-with-projects/creating-projects/copying-an-existing-project) includes views, custom fields, configured workflows except auto-add workflows, and Insights. Original items, collaborators and repository/team links are excluded; this adapter also explicitly excludes draft issues. The preview shows the source's enabled workflow metadata and warns about inherited configuration. Readback verifies the returned project identity, selected field/basic-view shape and absent items/repository links. Hidden native conditions, grouping/sorting, Insights and permissions are not claimed fully verified and require a manual check. No copied project receives items, collaborators, secrets or new repository links implicitly.

The [current official schema](https://docs.github.com/en/graphql/reference/projects) supports the named project, field, view and item mutations above. Introspection and bounded reference-board reads were checked on 2026-10-31. The new reader independently retrieved 13 fields, one view, seven native-workflow flags, one repository link, 22 items and the view's visible-field configuration from the selected public reference project, with complete coverage and stable revision evidence. Schema exposure and successful reads or fixtures do not establish a working live mutation. Native workflow reads establish identity/name/enabled flags, not trigger/status conditions, and this tool does not change those settings through undocumented routes.

`automation-config` accepts role-to-status-name JSON with required `entry`/`done` and optional `reopen`/`blocked`/`ready`. It resolves the actual project, single-select field and unique option IDs into `PW_PROJECT_ID`, `PW_STATUS_FIELD_ID`, `PW_STATUS_FIELD_NAME` and the corresponding `PW_*_OPTION_ID` variables. Its output always leaves `PW_AUTOMATION_ENABLED` and `PW_NATIVE_SETTINGS_VERIFIED` false.

Use that output with the consuming project's existing Project Workflows lifecycle starter. The consuming workflow owns stage meanings, label/dependency behavior, fresh-close/reopen policy, scheduling, credentials and hosted tests. Agent authentication and workflow-runner credentials are separate. Do not install a second lifecycle engine, set secrets/variables, dispatch workflows, enable schedules or infer manual verification from an API enabled flag. The consuming setup must inspect the saved native configuration and preserve one writer per transition before enabling automation.

## Manual setup evidence for the consuming workflow
1. Record the selected project URL/ID, ordered stage meanings and the proposed writer for each transition. Run `read-project` and `automation-config` against that actual project; preserve the disabled output until the remaining checks are accepted.
2. Open the project's Workflows settings and inspect each relevant workflow's saved trigger, target item type, selected field and option mapping. In particular, verify which terminal options cause Auto-close issue and whether other enabled workflows overlap with the consuming lifecycle starter. Record the observed values and their checked date in the consuming project's setup record. The API's identity/name/enabled list is supporting evidence, not a substitute for inspecting those settings.
3. Inspect each selected view's saved layout, filter, visible fields, grouping, vertical grouping and sorting. Compare the supported fields with `read-view`; record grouping/sorting and Insights separately where API setters or readback are unavailable. An API gap remains explicit until the corresponding required manual check is done.
4. Under a separately approved hosted test, verify issue entry, close/reopen, board-driven terminal/reopen behavior, fresh-close protection and competing blocked signals using the existing starter. Repeat setup must preserve unrelated configuration; failed or uncertain provider operations use read-only recovery before any retry. Record actual transitions and notification behavior rather than inferring them from configuration.
5. Only the consuming setup can attest `PW_NATIVE_SETTINGS_VERIFIED=true` after those required settings are checked and propose enabling `PW_AUTOMATION_ENABLED`. Choosing credentials, setting repository variables/secrets, publishing/dispatching the workflow and enabling schedules remain separately authorized actions.

## Execution, readback and recovery
Repeat the authorized preview command with `--actor LOGIN --execute --expect FINGERPRINT --operation-id ID`. Relevant project/schema/item state is refreshed under the shared project journal lock. Actor and repository identity are checked before each send. This is read-then-write protection, not an atomic remote compare-and-swap.

Each operation sends at most one mutation. A response identifier is durably retained, then independently read back through exact owner/project/resource membership and desired state. Lost responses, malformed/mismatched IDs, readback denial and changed configuration stay uncertain. Creation recovery requires complete bounded candidate coverage, a resource absent from the before-set and matching recorded digests; ambiguous results need an independently inspected `--result-id`. Journals keep IDs/digests/proofs, not complete project titles, field labels, filters, options or credential values. Never retry a mutation merely because its command failed.

The old bare `move-card --execute` form is no longer accepted. Its configured-alias selection remains, while actor/fingerprint/operation-ID guards and independent final-state readback replace the former weaker write path. Legacy exports retain their output and cap behavior.
