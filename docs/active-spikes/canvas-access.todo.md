---
attention: live
---

# Canvas integration work and verification
Opened: 2026-10-27. Slug: `canvas-access`.

[Purpose and retrieval contract](canvas-access.md).

## Current state
Research. The pair moved here from its temporary private staging location on 2026-10-27, and the first candidate survey is recorded in the concept's [candidate evaluation](canvas-access.md#candidate-evaluation--2026-10-27). No MCP has been selected or installed, no credentials created, no account connected, and no live API coverage verified. No custom server implementation is authorized by this document alone.

## To do
- [ ] Compare each viable candidate against the conceptual document's retrieval contract. Verify pagination, stable IDs, duplicate handling and failure behavior in code/tests where documentation is insufficient. — Progress 2026-10-27: pagination and the write-tool policy were read in code for `vishalsachdev/canvas-mcp`; stable IDs, duplicate module references and partial-failure output are not yet checked for either viable candidate.
- [ ] Check the official API behavior for announcements, modules/items, pages, files, assignments, effective deadlines/overrides, timezone handling, throttling and external-tool limitations. Separate documented capabilities from behavior still requiring a live test.
- [ ] Select reuse, a small adapter, or a justified minimal API client; record reasons and unresolved gaps. Do not build a new server before this decision.
- [ ] Specify `setup-canvas`: connection/account discovery, explicit course selection, consent boundaries, verification, reconnection and clear failure states.
- [ ] Specify `use-canvas`: read inputs, resource identities, normalized output, provenance, per-resource coverage, snapshot/delta semantics, removal confirmation and last-successful baseline updates.
- [ ] Write the bounded implementation plan with exact files, dependency versions, tests, recovery/rollback and approval gates for any new access.
- [ ] After the plan is approved, implement the selected smallest slice and add synthetic tests for multi-page retrieval, duplicate module references, unchanged reruns, changed dates, overrides, timezone edges, partial errors and external-tool gaps.
- [ ] Run the automated tests and inspect outputs for false deletions, baseline advancement after failures, duplicates and missing provenance.
- [ ] With explicit authorization, run a read-only live smoke test. Keep real connection/configuration and private evidence outside the public tree; record generic coverage and limitations without claiming untested compatibility.
- [ ] Review the full staged diff, documentation, examples, test fixtures and logs for public suitability before any publication.
- [ ] Update maintained setup/use documentation and the target index after verified implementation; use the target's authorized closure process when the work is actually complete.

## Ready for human QA
None yet. After implementation, ask the user to verify account/course selection, consent clarity, the readability of a change summary, and behavior when content is unavailable. Do not move implementation items here before their technical checks pass.

## Done
- [x] Define the separate setup/use responsibilities and reuse-first research scope — captured in the conceptual document on 2026-10-27; candidate selection and live validation remain open.
- [x] Define public-safe examples and fixture boundaries — this pair contains no real connection, course or learner data, and the planned test suite uses synthetic material.
- [x] Read the target repository's current instructions, workflow configuration and capability conventions before choosing implementation paths. — Done 2026-10-27: read `AGENTS.md`, `TODO.md`, `project-workflows/workflow.toml` and the existing spike pairs. Native skills live at the repository root (`setup-canvas/`, `use-canvas/` would follow that), provider dependencies stay explicit, and spike pairs carry `attention: live` plus an Opened/Slug line, which this pair now follows. No existing Canvas spike or skill was present.
- [x] Find maintained Canvas MCP candidates through their original repositories. Record repository URLs, versions/commits, maintenance evidence, license, supported clients, setup requirements and API scope. — Done 2026-10-27 for the first pass: survey, metadata and fit notes are in the concept's candidate evaluation. Supported clients and setup requirements were taken from READMEs; nothing was installed. Instructure's own MCP is a partner pilot with no availability date.
- [x] Transfer this pair from temporary private staging into this repository — added 2026-10-27. Bodies were copied unchanged and compared by diff; the only deliberate edits were this repository's frontmatter (`attention: live` alone) and the Opened/Slug line. The private transfer coordinator was not copied.

## Research exit gate
Selection evidence, gap assessment, skill contracts and the bounded implementation plan are required. “An MCP exists” is not sufficient. If required capability cannot be verified without new access, name the exact dependency and wait for authorization rather than treating it as success.
