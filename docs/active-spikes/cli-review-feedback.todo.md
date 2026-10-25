---
attention: live
---

# CLI Review Feedback — Tasks
Opened: 2026-10-25. Slug: `cli-review-feedback`.

## Background
Capture the user-requested CLI feedback in the current `run-project-spike` format. [Concept and proposed acceptance criteria](cli-review-feedback.md). Documentation is the authorized deliverable; implementation remains out of scope.

## Project Organization
The owning repository is Agent Hands. The current `run-project-spike`, `setup-project-workflows`, and `commit-work` procedures were read from the refactored Project Workflows collection in the containing checkout. Its `workflow.toml` describes the containing configs project, not Agent Hands; it does not relocate this spike into the parent repository.

Agent Hands had no existing spike docs, local workflow copy, or index. For this documentation-only request, use the minimal pair under `docs/active-spikes/` and root `TODO.md`. No workflow submodule adoption, scratch/archive scaffold, standing-rule edit, or parent pin update is part of the change.

## General Principles
Keep supplied live observations separate from local code evidence and proposals. Preserve useful successful-read evidence. Do not label environment friction or an abandoned unsupported-runtime attempt as a demonstrated refactor regression. Use synthetic examples and omit private review material.

## Current State Overview
Feedback and candidate acceptance criteria are recorded. Drive's missing continuation input is confirmed by help and source. Docs' omission of non-`textRun` paragraph content is confirmed by source; attribution of the reviewed blanks to smart chips remains unverified. No tool behavior changed and no live service operation was repeated for this spike.

## To Do
These are proposed follow-ups, not an implementation authorization:
- [ ] Select whether to scope explicit Drive search/list continuation, using the bounded-request acceptance criteria in the concept.
- [ ] Establish a representative Docs reference response shape using synthetic or separately authorized sanitized data, then choose rendering behavior without changing mutation ranges implicitly.
- [ ] Decide whether the cache/runtime/network incidents warrant a focused diagnostic-guidance change; retain the environment-friction classification unless new evidence changes it.

## Ready for Human QA
None. This checkpoint changes documentation only; no implementation is being presented as ready for runtime or visual QA. Scope selection for the proposals remains open.

## Done
- [x] Resolve the owning repository, current instructions, and spike workflow before choosing document locations. Agent Hands is an independent Git submodule; both it and the containing configs checkout were clean at discovery. Current Project Workflows procedures were read, and the globally exposed spike skill matched the refactored copy.
- [x] Capture the supplied review outcomes without private interview content or participant identity. Recorded successful reads, the unchanged command's approved retry after cache denial, the abandoned Python 3.9.6/DNS attempt, bounded Drive discovery, and suspected Docs reference omission.
- [x] Check minimal relevant CLI help and code before wording improvement proposals. Inspected `_drive_page_size`, `_drive_search`, `_drive_list`, Docs tab/text/link traversal and read parsing, and `_google_python`; confirmed the Python 3.11+ requirement in current skill guidance/manifests. This was a bounded inspection, not a general code audit.
- [x] Add the conceptual/task pair and the short index entry, with live attention markers and proposed acceptance criteria. Implementation, external actions, credentials, and parent-repository changes are excluded.

## Verification Record
On 2026-10-25, local credential-free help succeeded:

```sh
bash skills/use-google-drive/scripts/drive --help
bash skills/use-google-docs/scripts/docs --help
python3.13 skills/use-google-docs/scripts/docs.py read --help
```

The direct Python command checked the read parser using an existing compatible interpreter; it did not exercise the wrapper's uv setup, read provider configuration, or contact Google. Source review confirmed the classifications above. Document readback, relative-link checks, whitespace checks, and full selected-diff review passed; only the two spike documents and root index were added. The containing repository's tracked submodule pin remains unchanged. Runtime test suites and fresh live reads are unnecessary for these documentation-only changes and were not run.
