# PowerPoint coauthoring probe
Historical fixture probe for [powerpoint-live-editing](../../docs/archive/powerpoint-live-editing.md). Use [PowerPoint Presentations](../../use-powerpoint-presentations/SKILL.md) for the maintained macOS capability; this experiment is retained for its original bounded checks. This is a disposable-fixture probe, not a general presentation-editing capability or a globally installed skill. Its live evidence and unresolved gates belong in the [task record](../../docs/archive/powerpoint-live-editing.todo.md).

## Scope and dependencies
Use the existing Node dependencies and provider setup of [Word Documents](../../use-word-documents/SKILL.md). The probe imports Word's owned-browser launcher, native cookie protection, exact account/document checks, private state helpers and per-account lock. It uses the existing tool-owned profile without copying cookies or accepting an arbitrary profile path. Normal Chrome is never inspected, closed or restored.

The separate PowerPoint bridge derives from Word's loopback server and uses a distinct add-in identity/path. It accepts only fixed read, guarded substring replacement and startup-setting commands. The generated manifest grants document read/write permission; headless setup uses the observed English PowerPoint add-in dialog. PowerPoint's API synchronizes changes into the editor; only independent cloud readback establishes persistence. No Graph file replacement or mutation retry is provided.

## Private fixture state
Check the `/state/` ignore before creating anything there, make the directory owner-only, and keep all actual identifiers, browser diagnostics, generated manifests, previews, receipts and downloaded packages inside it. Use an existing selected Graph account and its owned Word profile. No authentication files belong in this experiment directory.

`state/test.json` names the exact previously created disposable item, with this synthetic shape:
```json
{"alias":"example","drive":"synthetic-drive","item":"synthetic-item","name":"Agent Hands PowerPoint coauthoring test 2026-11-16.pptx"}
```

The fixture contains one slide with five ordinary text-bearing shapes named `Title`, `Description`, `ALPHA`, `BETA` and `Preservation`. Its title is `Disposable PowerPoint coauthoring test`; the preservation text is `Preservation check: Keep this bold text.`. ALPHA initially contains `Agent target ALPHA: Original text.` and BETA contains `Second editor target BETA: Original text.`. The probe refuses different file metadata, slide/shape counts, unsupported shape types or missing fixture markers. Grouped shapes, images, tables, charts, notes and general slide authoring are outside this test.

## Bounded sequence
Run from the checkout root. Metadata setup and the one previewed ALPHA edit require existing file-write opt-in and authorization for the selected disposable presentation.
```sh
node experiments/powerpoint-live-editing/probe.mjs prepare --execute
node experiments/powerpoint-live-editing/probe.mjs read
node experiments/powerpoint-live-editing/probe.mjs preview
node experiments/powerpoint-live-editing/probe.mjs apply --execute
node experiments/powerpoint-live-editing/download.mjs after-edit
```

`prepare` installs/opens only the generated add-in, enables its document-scoped startup setting and closes the owned browser. `read` and `preview` require startup already configured. The preview is written exclusively; `apply` verifies its hash and current target/shape text, records dispatch durably before delivering the command, and refuses replay. An interruption requires inspecting the private receipt and a fresh cloud download; a successful session result is not a cloud-save guarantee. Neither stale locks nor authentication failures are automatically bypassed.

`download.mjs LABEL` independently downloads the exact selected file through Microsoft Files, refusing an existing observation filename. `inspect_pptx.py FILE --reference BASELINE --alpha EXPECTED --beta EXPECTED` compares fixture text, shape identities/positions, selected explicit font properties and slide size. It does not certify every PowerPoint feature or effective theme inheritance. Omit an expected text option when that shape must remain unchanged. A second editor's visible result is separate evidence from Graph readback.

`inspect` and `inspect-catalog` are bounded development diagnostics in the same owned headless profile. They can save sensitive UI context privately; remove those observations when they are no longer needed. They never export cookies or evaluate document-supplied code.

## Offline checks
```sh
node --test experiments/powerpoint-live-editing/addin.test.mjs
python3 -m unittest discover -s experiments/powerpoint-live-editing -p '*_test.py'
```
The add-in tests exercise the actual browser script with a synthetic Office host, including stale/wrong-target rejection and uncertainty after dispatch. The comparison tests check expected two-editor text and rejection of changed controls. These checks do not prove live tenant access, save behavior or concurrent safety.
