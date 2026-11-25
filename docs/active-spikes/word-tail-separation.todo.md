---
attention: live
tags: [word, cli, coauthoring, work-log]
---
# Word tail separation work log
[Concept](word-tail-separation.md).

- [x] W1 Implement exact tail/prefix validation, HTTPS link bounds and complete cloud paragraph extraction; refuse comments, revisions and unsupported body structures.
- [x] W2 Add a guarded Office.js tail operation and private preview/apply/verify entrypoint using existing account, target, write opt-in and browser ownership checks.
- [x] W3 Check the actual add-in operation against synthetic successful and stale-coauthor cases, plus input validation. Five focused tests pass. Existing local bridge test also passes outside sandbox socket restrictions.
- [x] W4 Diagnose Word/cloud spacing differences. Word converted ordinary double spaces after numbered labels to a nonbreaking space plus a normal space. Explicit normalization reconciles this while retaining wording checks.
- [x] W5 Verify the authorized live edit and independently render the saved document. November 24, 2026: the authorized coauthored edit saved while another editor could keep the file open. The session reported its result unverified; an independent complete cloud-body read matched the expected result. A subsequent download verified both hyperlink destinations and the absence of the separated questionnaire, and rendered as one clean page. This proves saved content for this case, not atomic protection against simultaneous edits or every formatting case.
- [x] W6 Review selected code, guards, tests and public-safe documentation; checkpoint locally. Combined Word/Forms suite passes all 39 checks. No push or global skill installation was performed.

- [x] W7 Preserve comments and tracked insertions in an untouched prefix during an authorized split; refuse edits that touch those records.
- [x] W8 Add bounded paragraph edits, semantic formatting, same-origin link repair and explicit appends. Disposable native tests preserved a comment, insertion and table. Saved verification passed on five existing shared documents, preserving review evidence and version lineage. Delayed cloud persistence was reconciled with read-only verification, without replay. All rendered pages of the four documents receiving substantive content/layout changes were inspected.
- [x] W9 Verify native manual-line-break search behavior and explicit comment anchors. The combined Excel/Word suite passes 68 checks; four disposable browser checks also pass. Other tenants/platforms and simultaneous same-paragraph editing remain separate limits.
