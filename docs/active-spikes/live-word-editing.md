---
attention: live
reviewed: 2026-10-28
tags: [microsoft, word, coauthoring, files]
---

# Cloud Word editing while a document is open
Opened: 2026-10-28. Slug: `live-word-editing`.

There is a plausible supported route to editing an open cloud Word document without replacing its complete file: an Office add-in that changes content inside the active Word session. Agent Hands does not currently provide that route. A separate, smaller improvement can make the existing file replacement route handle locks and stale source versions more clearly. Neither route has been implemented or validated here.

The user requested this investigation spike, not implementation, installation, authentication changes or publication. The options below are proposals. The [task record](live-word-editing.todo.md) separates completed evidence gathering from future validation.

## Problem and evidence
A live, authorized replacement of a cloud DOCX returned `Locked`; after the user reported closing the document, an authorized retry succeeded and the downloaded result matched the prepared file. This establishes an observed lock conflict and successful recovery for one operation, not a guarantee that closing one client releases every possible lock. The reusable issue is that whole-file replacement competes with Office editing sessions and requires careful preservation of edits made since download. No private document content, user identities, account aliases or service identifiers belong in this spike.

Current implementation inspected on 2026-10-28:
- [Microsoft Files](../../use-microsoft-files/SKILL.md) exposes download and whole-file replacement, with preview/execute gates; there is no paragraph-editing or live Word session interface.
- [`_m365_files_replace`](../../use-microsoft-files/scripts/operations.sh) reads current metadata, requires an ETag and supplies `If-Match` when uploading the complete file. This guards the interval between that metadata read and upload. It does not bind the upload to the version originally downloaded before local editing; callers currently have to compare that baseline separately.
- [The PowerShell transport](../../setup-microsoft-services/scripts/graph.ps1) disables SDK retries for non-GET requests and reports an exception message. Preserve the no-blind-replay behavior. A reusable lock policy would need structured status/error information rather than parsing localized messages.
- Successful replacement checks remote size. A same-size response is not proof that all intended bytes, styles or concurrent edits survived; a higher-level document workflow needs content and structure readback.

## Feasibility and alternatives

| Route | Evidence and practical assessment | Remaining uncertainty |
| --- | --- | --- |
| Live Word add-in with a bounded CLI bridge | Microsoft documents Word JavaScript paragraph operations inside Word on the web, Windows and Mac. This can edit through the document session rather than replace the cloud file. This is the strongest candidate for actual live editing. | A working host/add-in bridge, deployment policy, active-session identity, supported requirement sets, simultaneous-edit behavior and cloud-save confirmation all need validation. It is not an unattended Graph document-edit API. |
| Safer existing Graph file replacement | Practical incremental work: retain an explicit downloaded-version precondition; distinguish lock, stale version and uncertain failure; preserve the patch for later recovery. | It still cannot promise to write while an Office lock remains. Retrying a confirmed refusal requires a supported, bounded policy and unchanged baseline. |
| WOPI / CSPP Plus | Microsoft documents real-time coauthoring protocols for third-party storage hosts. Useful architectural context. | This is not evidence of a drop-in client route for editing an arbitrary existing SharePoint file. Program eligibility, host responsibilities and integration cost would need separate assessment. It is not the proposed small fix. |

Microsoft's [Word add-ins overview](https://learn.microsoft.com/en-us/office/dev/add-ins/word/word-add-ins-programming-overview) demonstrates reading paragraphs and inserting text. [Word events](https://learn.microsoft.com/en-us/office/dev/add-ins/word/word-add-ins-events) documents local versus remote event sources during coauthoring. These support the live-session direction, but do not establish atomic compare-and-replace semantics or cross-client success for this project. Check runtime requirement sets; do not depend on preview or desktop-only APIs merely because they appear in the reference. [Word troubleshooting](https://learn.microsoft.com/en-us/office/dev/add-ins/word/word-add-ins-troubleshooting) also records platform differences in tracked-change attribution and content-control support.

The [Graph content endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0) uploads the binary file. Changing to an upload session or setting conflict behavior is not evidence of paragraph coauthoring support. [Graph errors](https://learn.microsoft.com/en-us/graph/errors) distinguishes a failed precondition from a locked resource; [upload-session preconditions](https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession?view=graph-rest-1.0) document ETag checking. ETags protect versions; they do not remove active locks. The [WOPI extensions overview](https://learn.microsoft.com/en-us/microsoft-365/cloud-storage-partner-program/plus/coauthoring/coauthoring-protocol-about) explicitly addresses third-party hosts in CSPP Plus.

## Candidate design boundaries
For file replacement, consider an explicit expected source ETag and private patch/baseline fingerprint carried from download through preview and execution. Re-read before writing; if the version changed, fetch the latest document and regenerate only the authorized edit against a uniquely resolved target. Refuse an ambiguous anchor or substantive collision. Never silently overwrite a newer file by substituting its current ETag for the approved baseline.

A confirmed lock refusal may support a short, opt-in retry policy after the lock clears, retaining the original source precondition and respecting server timing guidance when present. Bound attempts and elapsed time; stop on a changed version, permission denial, uncertain dispatch or ambiguous result. A timeout after dispatch requires readback/reconciliation before another mutation. Do not force-unlock, discard checkouts, close a user's application, create a replacement identity or remove concurrency guards to obtain success.

For a live-session route, require an explicit document/session binding and a narrow allowlist of content operations. Preview exact target content and final copy, revalidate anchors immediately before mutation, and report conflicts honestly. Use operation identifiers or equivalent reconciliation to prevent duplicate insertions after a timeout; do not assume a document index remains stable during coauthoring. Preserve surrounding styles, lists, links, human notes, comments and tracked changes. Verify local document state separately from persisted cloud state. Closing the add-in, losing the host connection or failing to save must produce an explicit partial/uncertain result.

Any implementation stays beside its owning native capability. A new Word-specific capability may be more appropriate than stretching Microsoft Files; that boundary is unresolved. Do not add a generic API escape hatch or make a portable provider depend on a private workspace. Keep credentials in the existing provider owner and session secrets out of logs. No browser automation, add-in installation, new grant or live test is authorized by this spike alone.

## Small validation plan
1. Offline fixtures: unchanged source, changed ETag, confirmed lock refusal, permission denial, lock followed by version change, timeout after dispatch, and duplicate retry. Assert bounded requests and no unsafe replay.
2. A separately authorized disposable DOCX: same document identity and sharing; test the current replacement route while closed and while another client is open. Change content between download and preview to prove the baseline guard; verify complete content and relevant OOXML parts after success.
3. A separately approved minimal Word add-in/bridge experiment: read one uniquely identified paragraph, preview an insertion, edit it in the active session and verify cloud persistence. With a second client, test edits in a different paragraph and the same paragraph, followed by session loss and reconnect. Preserve both users' content or stop with a clear conflict; do not declare seamless coauthoring from a single-client demo.
4. Record a small Mac / Word web / Windows matrix. Only claim platforms, API requirement sets, deployment routes and recovery paths actually exercised. Decide whether to implement a narrow live capability, improve guarded file replacement only, or stop if deployment makes the live route impractical.
