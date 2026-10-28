---
attention: live
reviewed: 2026-10-28
tags: [microsoft, word, coauthoring, files]
---

# Cloud Word editing tasks
Opened: 2026-10-28. Slug: `live-word-editing`. [Concept and evidence](live-word-editing.md).

## Background and scope
The user requested a spike to reduce cloud Word editing conflicts when the file is open. Official documentation supports investigating a live Word add-in and improving baseline/lock handling in the existing file route. The current authorization is documentation and research only: no implementation, installation, grant changes, real-document experiments or push.

## Project organization
- `use-microsoft-files/SKILL.md`, `scripts/operations.sh` and `tests/test-files.sh`: current file replacement contract and checks.
- `setup-microsoft-services/scripts/graph.ps1` and `tests/test-powershell.sh`: SDK request/error/retry behavior.
- A new bounded Word-session capability remains a proposal; no destination or interface has been adopted.

## Current state
Feasible candidates are identified, but no live add-in route has been built or tested. Existing Graph replacement remains subject to locks. A downloaded-source ETag contract is a candidate improvement beyond the current metadata-read-to-upload guard. All future work below needs explicit implementation/test scope selection.

## To do
- [ ] Choose the smallest first experiment: guarded file replacement or an active Word-session add-in/bridge. Confirm the owning capability and supported host requirements before coding.
- [ ] Specify expected-source-version/fingerprint behavior across download, preview, edit and execution, with conflict recovery that never substitutes a new ETag without reevaluating the edit.
- [ ] Specify structured error outcomes for locked, stale, denied, unapplied, applied-but-unverified and uncertain requests. Define bounded retry conditions and stop conditions.
- [ ] Investigate the supported add-in bridge/deployment options and tenant restrictions without installing anything or changing grants. Check stable Word API requirement sets, session identity, anchors and persistence verification.
- [ ] Run the conceptual document's offline validation matrix after implementation is separately authorized. Reuse the existing file/provider tests; do not add tests that merely mirror code.
- [ ] Obtain explicit scope for a disposable cloud document and, separately, any add-in installation before the small live validation plan. Test concurrent edits, disconnection and recovery without private source material.
- [ ] Record verified host/platform results and select or reject a production route. Update owning help/skills only as part of an approved implementation.

## Ready for human QA
None. No live-edit implementation exists yet.

## Done
- [x] Inspect current Agent Hands file replacement and PowerShell retry/error paths. Confirmed whole-file upload, an ETag read within the replace invocation, non-GET SDK retries disabled, and size-only metadata verification.
- [x] Read Microsoft's primary documentation for Word add-ins, Word coauthoring events, Graph content replacement/preconditions/errors and WOPI coauthoring. Recorded supported options separately from unverified project integration.
- [x] Create a public-safe conceptual/task pair and index entry with a small validation plan. No private document text, account/tenant/file identifiers, credentials or private source links are included.
