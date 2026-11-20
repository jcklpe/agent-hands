---
status: captured
---
# Canvas linked-reading discovery and handoff
Captured 2026-11-02 at the user's request as a future Canvas extension spike. The immediate reading was recovered from an existing local PDF; this note preserves the reusable discovery and handoff issue without starting implementation. The separate [Canvas Inbox capture](canvas-inbox.md) retains its own scope.

## Verified capability boundary
The [Canvas CLI](../../use-canvas/SKILL.md) successfully exported the course's assigned external reading link in a page body. Page and native-file metadata coverage were complete; the file listing contained no matching chapter. The chapter was hosted by a publisher through a library proxy. Publisher authentication and chapter download are separate from Canvas API access, and no publisher request was attempted. This was not a missing native Canvas-file download endpoint: `download-file` already handles an explicitly selected native course/file.

The current [reader](../../use-canvas/scripts/canvas_read.py) reports external module items as structured gaps, while ordinary external hyperlinks inside page bodies remain body links. In the observed export, the reading's publisher link survived in Markdown but was absent from the top-level structured gaps list. A complete Canvas export therefore establishes Canvas retrieval coverage; it does not establish that linked publisher content was retrieved.

## Possible bounded extension
Consider a reading/resource discovery and handoff view that associates a reading title and stable link with its source page or module and clearly distinguishes a native Canvas file, an external reference and verified local content. A structured inventory of ordinary page-body links could make this distinction visible without visiting those links. Preserve current export determinism and compatibility deliberately, and choose any command names only when the interface is actually designed.

For native files, reuse the existing metadata and download path. For a library or publisher reference, provide the exact stable link for user download or a separately authorized integration, and report that chapter content has not been retrieved. A retained link is not a downloaded reading. Do not infer publisher denial from an unattempted request or assume that a Canvas token grants publisher access.

An optional local-file handoff could accept a user-selected path, with title, author, chapter-heading and page checks before claiming reading access. Search only user-authorized locations. A matching filename does not prove that the PDF contains the assigned chapter or the complete textbook; distinguish PDF-page numbering from original book pagination.

## Boundaries for later work
No implementation, browser automation, generic external fetcher, publisher credential flow, grant changes, commits or publication is authorized by this capture. Keep Canvas credentials origin-bound and private source packages, account/course identifiers, personal paths and access-bearing links out of portable documentation and fixtures.

When scoped work starts, validate external module links, ordinary publisher links within pages, genuine native files, ambiguous local chapter matches, signed-link handling, partial/denied listings and unchanged-export compatibility. Synthetic fixtures cannot establish publisher access. Promote this context into the project's paired active spike when work actually begins, preserving the useful evidence without leaving a competing scratch copy.
