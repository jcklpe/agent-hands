---
attention: historical
closed: 2026-11-17
---

# GitHub Project Move Reliability — Tasks
Historical record — closed 2026-11-17. Stable slug: `github-project-move`. The complete development record is retained below; use [maintained guidance](https://github.com/jcklpe/agent-hands/blob/aaf5f3f1d6c9c5c67095806d3b1e07fc9da85461/use-github-projects/references/collaboration.md) for current behavior and limits. Closure and the exact archival wording were approved.
Opened: 2026-10-27. Slug: `github-project-move`. [Concept](github-project-move.md).

## To Do
No implementation items remain in this repair. Publication and broader history decisions remain on hold.

## Ready for Human QA
Windows fresh-install validation and live account/write verification are not performed by this repair. Do not repeat the already recovered live move.

## Done
- [x] Reproduce the misleading status/null-ID failure with synthetic CLI responses, repair query/response handling and fail closed before a plan or write. The original CLI reproduced a successful but false No Status plan on a synthetic malformed-query error. The corrected query checks every transport result and validates complete envelopes before interpreting state.
- [x] Verify valid/unset/already-matching statuses, precise IDs, later-page items, missing/duplicate/malformed responses, default zero writes and uncertain mutation outcomes; preserve existing GitHub export/operation assertions. Thirteen native CLI test methods pass, with multiple failure/flag variants; all eight pre-existing GitHub test programs also pass. The updated shared fixture returns complete GraphQL envelopes and valid mutation acknowledgements. Skill validation, shell syntax and diff checks pass.
- [x] Review the final tracked tree and relevant publishable history for secret/private material without reading credential stores; report coverage and unresolved limits before publication. A bounded current-tree and reachable-history pattern review found no known token/private-key signatures or non-example credential-store paths. Literal candidates were synthetic fixtures, placeholders, provider URLs, environment names or code expressions. Historical compatibility sources and domain-specific fixture naming remain; current feedback preserves two legacy command examples. Three supplied PNGs are binary coverage limits, including provenance metadata in the head image. This is not a guarantee of secret absence or publication approval.

## Recovery and privacy
Use ordinary Git recovery for the scoped local changes; do not rewrite or publish history as part of this task. All fixtures contain synthetic repositories and IDs. This repair does not read or write private credential/config files; no credential store is needed for these checks.

## Closure preparation — 2026-11-17
The published Projects collaboration runtime supersedes this original repair and retains its malformed-response, target-identity and explicit-null protections. All 13 move-card regressions passed against the public implementation during this review. Its stronger actor/fingerprint/journal/readback contract is maintained in the [published Projects guide](https://github.com/jcklpe/agent-hands/blob/aaf5f3f1d6c9c5c67095806d3b1e07fc9da85461/use-github-projects/references/collaboration.md); the selected API validation and provider closure are recorded in the [published collaboration archive](https://github.com/jcklpe/agent-hands/blob/aaf5f3f1d6c9c5c67095806d3b1e07fc9da85461/docs/archive/github-collaboration-operations.todo.md). The source checkout predates those changes, so its older implementation and publication-hold language must not overwrite the newer public runtime. This repair is ready for closure as superseded, without repeating the recovered live move. Windows/fresh-client validation remains unproved. See the closure review (local preparation record); no local archival has occurred.
