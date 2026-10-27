---
attention: live
---

# GitHub Project Move Reliability — Tasks
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
