---
status: parked
---
# PowerPoint CLI expansion
Captured November 18, 2026 at the user's request. Preserve this as a scratch spike for future work on live presentation editing beyond text replacement. Implementation is parked; the immediate editing workflow moved to another presentation platform.

## Requested scope
Extend the CLI so an agent and a human can work on the same open presentation, including speaker notes, graphics and images, formatting and layout, slide order, and animation or embedded video. Changes should appear in the human's open editor without replacing the whole file or losing concurrent edits, review comments, or existing media.

## Current boundary and preliminary findings
The maintained [PowerPoint skill](../../use-powerpoint-presentations/SKILL.md) supports bounded ordinary shape-text replacements in commercial Microsoft 365 OneDrive or SharePoint through an owned headless Office.js session on macOS. It does not support notes, images, layout, animations, or slide reordering. A PPTX in a locally synchronized Google Drive folder is not a supported target for that cloud route. Writing new PPTX bytes on disk is not evidence of a live update in an already-open PowerPoint session.

Preliminary inspection found notes, shapes and timeline concepts in the macOS PowerPoint scripting dictionary. Their presence does not establish reliable live editing, preservation, or concurrency support. A native automation probe was stopped before a successful session read; no native read/write capability was verified and no implementation was added. Recheck current Office.js and native APIs before choosing an approach.

## Questions for a resumed spike
- Which requested operations can use the existing Office.js route, and which need a separate native route or remain unsupported?
- Can exact slide, shape and notes identities survive reads, edits and slide reordering, with stale-state refusal and independent persistence checks?
- How can each operation preserve concurrent human edits, comments, formatting, images, media and unrelated animation sequences?
- Can the tool work entirely in the background, without changing foreground applications, taking keyboard focus, opening full-screen video, or starting playback?
- How should a local-file route distinguish in-memory editor state, saved file state and sync-provider state?

Any resumed implementation should preserve the existing preview/apply/readback and no-replay safeguards, use operation-specific capabilities rather than arbitrary scripting, and state platform and authentication limits explicitly. Disposable presentations and bounded human QA would be needed to establish actual coauthoring and playback behavior. This capture authorizes no new authentication, installs, browser/native automation, or live tests.

## Related work
[PowerPoint live-editing history](../archive/powerpoint-live-editing.md) records the delivered text-only surface. [PowerPoint validation follow-up](powerpoint-validation.md) covers deferred validation of that existing surface; it is separate from this broader capability proposal. No private deck, account identifiers, course content or consumer workspace paths are included here.
