---
attention: historical
reviewed: 2026-11-17
tags: [microsoft, powerpoint, coauthoring]
---
# Headless PowerPoint live editing tasks
Opened: 2026-11-16. Slug: `powerpoint-live-editing`. Closed: 2026-11-17.

Historical record. Current commands and safeguards belong to [PowerPoint Presentations](../../use-powerpoint-presentations/SKILL.md) and [provider setup](../../setup-microsoft-services/references/powerpoint-browser.md). Deferred validation is [tracked separately](../scratch/powerpoint-validation.md). [Scope](powerpoint-live-editing.md).

## Current state
The reusable [PowerPoint capability](../../use-powerpoint-presentations/SKILL.md) and [provider setup](../../setup-microsoft-services/references/powerpoint-browser.md) are implemented for macOS. Headless read/preview/apply, automatic per-presentation add-in setup, independent startup/text verification and cloud-only reconciliation reuse Word's owned-profile lifecycle and native credential protection. Word runtime source remains unchanged.

The packaged route passed on an exporter-built, two-slide synthetic presentation: automatic preparation, fresh headless read, two previews, one ALPHA replacement, cloud-only verification, replay refusal, stale-preview refusal before dispatch, fresh read and repeat preparation with `startupChanged: false`. Identical ALPHA text on the second slide stayed unchanged. Independent package comparison found no differences in the checked text, shape IDs, positions, explicit font properties or slide size beyond the intended replacement. The earlier prototype's user-confirmed two-way browser coauthoring result remains the concurrent-session evidence; this packaged test did not ask the user to open the new fixture.

Seventeen PowerPoint tests, nine unchanged Word unit/bridge regressions, seventeen skill-link checks and four skill validators pass. The scoped public source/metadata scan found no real account identifiers, private paths or credential material. Private state remains ignored and untracked. Transient test builders, renderings, page diagnostics, manifests and upload receipts were deleted; active operation journals and a small private reconciliation bundle remain. The disposable cloud presentations remain available; no deletion capability was invoked. No normal Chrome tabs were inspected or operated, no authentication cache was copied, and the user authorized closure and a scoped public push on 2026-11-17.

## Deferred work
- Sustained use, PowerPoint-specific lost-acknowledgment/MFA renewal, broader tenant acceptance and complex decks remain future validation in [the retained follow-up](../scratch/powerpoint-validation.md). Windows/Linux stay deferred. No required implementation work remains in this bounded macOS spike.

## Done
- [x] Package bounded multi-slide text reads and exact slide/shape substring edits, with Word-equivalent account, preview, cloud-baseline and single-dispatch guards.
- [x] Automate per-presentation add-in installation/startup and verify persistence without normal-browser access.
- [x] Add synthetic safety/OOXML/browser tests, skill/provider discovery and public-safe usage documentation.
- [x] Validate the packaged macOS route on an authorized disposable presentation, including fresh read, edit/save, stale-preview/replay refusal and cleanup; record remaining limits.
- [x] Decide whether to promote the fixture probe into a reusable PowerPoint capability, including its supported edits and setup/recovery contract. The user authorized this implementation on 2026-11-17, focused on macOS and the established safeguards.
- [x] Confirm the headless ALPHA edit is visible in the normal browser. Change BETA there to the requested synthetic sentence and wait for Saved; a fresh headless read and independent cloud comparison will verify the return path. On 2026-11-17 the user confirmed “ALPHA visible; new BETA saved.” Fresh headless read and independent cloud download verified both exact sentences, with the BETA formatting qualification in Observations below.
- [x] Generate, validate and upload a disposable synthetic presentation, preserving private cloud identifiers outside Git.
- [x] Build the narrow experimental PowerPoint bridge. Three synthetic checks cover guarded substring edits, another shape’s concurrent text, stale/wrong-target refusal and uncertain post-dispatch failure. Live behavior is a separate gate. A fourth check now covers allowed geometric shapes versus refused groups; the live evidence is recorded below.
- [x] Verify existing owned-profile authentication and headless add-in setup without accessing normal Chrome. Installation and cloud-persisted startup passed; a fresh headless process read all five shapes.
- [x] Read, edit and independently verify cloud persistence with another browser editor open. The ALPHA replacement passed through the owned headless Office.js session while the user-confirmed browser editor remained open; independent Graph download verified the exact replacement and unchanged fixture controls.
- [x] Verify reverse synchronization from the second editor, content/formatting preservation and a fresh headless restart. Both text changes survive. Agent-only formatting checks pass; the final comparison flags only the browser-edited BETA run metadata, as qualified above.
- [x] Record conclusions, operational limits and cleanup; checkpoint only this work. Findings and source stay in this spike; the production Word implementation and unrelated changes are excluded.
- [x] Start a distinct PowerPoint spike with the user's authorized test scope and current Microsoft API references.

## Observations — 2026-11-17
- PowerPoint’s catalog uses an `_xdm_` frame on the editor origin rather than Word’s separate catalog origin. Keyboard activation avoids a collapsed-ribbon click issue. The generated add-in was uploaded and reopened deterministically in the owned browser.
- The generated fixture uses ordinary text-bearing geometric shapes. The first strict text-box guard refused them before mutation; live inspection established the type, and a separate synthetic check now covers it while refusing groups.
- PowerPoint startup saved through document settings and autosave. Independent download contained the add-in reference/startup flag, without the bridge path secret or a private-key marker. No normal-browser state was read or copied.
- In the original coauthoring fixture, the browser’s BETA edit changed explicit font-run metadata, including theme-font properties and inherited formatting. Its effective visual equivalence was not established; all other checked controls were unchanged.

## Ready for human QA
None for the bounded fixture experiment.

## Remaining limits
- The prototype used one synthetic slide and a second browser editor; the packaged test used two slides with repeated text. Both used one existing account/profile on macOS and ordinary text-bearing shapes. Simultaneous keystrokes and same-shape conflict behavior remain untested for PowerPoint.
- No general slide creation/deletion, images, tables, charts, grouped shapes, notes, masters, animations, protected presentations, or whole-file replacement.
- English add-in dialog selectors are tested only in the observed tenant UI. Fresh-machine setup, PowerPoint-specific MFA recovery, crash recovery, sustained use and Windows/Linux remain untested.
- The presentation persists an add-in reference and startup setting. Browser credentials remain in the existing tool-owned profile; the experiment has no cookie export or arbitrary browser/profile control path.

## Packaged observations — 2026-11-17
- The first two-slide test package was assembled by copying slide XML and was not valid for the live PowerPoint slide API. Setup timed out; read-only reconciliation showed startup was not saved and no content edit was sent. The fixture was rebuilt with the presentation exporter and validated before a new conflict-refusing upload. No lock bypass or whole-file replacement was used.
- Repeat setup exposed a timing race: the ribbon could appear before the saved add-in connected. The prepared path now verifies cloud startup and waits for its add-in without touching the ribbon. A focused regression and live repeat returned `already_running` with no startup save.
- General authoring, placeholder/group/table/chart editing, supplementary-character offsets, same-shape atomicity and indefinite unattended operation are not established. The public skill states the concrete bounds; failed/stale operations never become automatic retries.
