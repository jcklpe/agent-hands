---
attention: live
---

# Canvas integration work and verification
Opened: 2026-10-27. Slug: `canvas-access`.

[Purpose and retrieval contract](canvas-access.md).

## Current state
Design. The candidate survey and access routes are recorded in the concept, and the user decided on 2026-10-28 to build `setup-canvas` and `use-canvas` here, with writes in the first version. The [setup-canvas contract](canvas-access.md#setup-canvas-contract--agent-proposal-2026-10-28), the [use-canvas contract](canvas-access.md#use-canvas-contract--agent-proposal-2026-10-28) and the [implementation plan](#implementation-plan--agent-proposal-2026-10-28) are agent proposals written 2026-10-28. On 2026-10-29 the user accepted the full write set and ruled out a fixed file-size cap; the remaining [choices](#choices-awaiting-the-user-g0) await their decision, and implementation waits for them. No credentials have been created, no account connected, no live API call made and no implementation code written. Change detection stays out of scope.

## To do
- [ ] Review the setup-canvas and use-canvas contracts and the implementation plan (user): trim the proposed write set, settle the open choices listed under gate G0, and approve or change the runtime and slices. Implementation waits for this. — Progress 2026-10-29: the user accepted all twelve proposed writes and rejected the 250 MiB upload cap, which is removed. Still open: the [choices awaiting the user](#choices-awaiting-the-user-g0).
- [ ] After the plan is approved, implement the selected smallest slice and add synthetic tests for multi-page retrieval, duplicate module references, unchanged reruns, changed dates, overrides, timezone edges, partial errors and external-tool gaps. — Plan 2026-10-28: three slices with stop points and the full synthetic case list are in the implementation plan below.
- [ ] Run the automated tests and inspect outputs for false deletions, partial exports published as complete, duplicates and missing provenance.
- [ ] With explicit authorization, run a read-only live smoke test. Keep real connection/configuration and private evidence outside the public tree; record generic coverage and limitations without claiming untested compatibility. — Scope change 2026-10-28: writes are in the first version, so gates G1 and G2 below split this into a read smoke test and a separately authorized write smoke test. Both also settle the concept's "to confirm in the live smoke test" list.
- [ ] Review the full staged diff, documentation, examples, test fixtures and logs for public suitability before any publication.
- [ ] Update maintained setup/use documentation and the target index after verified implementation; use the target's authorized closure process when the work is actually complete.

## Implementation plan — agent proposal, 2026-10-28
Not approved. It implements the [setup-canvas](canvas-access.md#setup-canvas-contract--agent-proposal-2026-10-28) and [use-canvas](canvas-access.md#use-canvas-contract--agent-proposal-2026-10-28) contracts in three slices, each ending in a stop for review.

### Runtime and dependencies
- Python 3.11 or later, standard library only (`urllib.request`, `json`, `html.parser`, `zoneinfo`, `hashlib`, `argparse`, `tempfile`). 3.11 is the repository's Python floor and the first release whose `datetime.fromisoformat` accepts Canvas's `Z` timestamps. Python parses integers without loss, which backs up the string-ID request header.
- Each skill folder gets its own `pyproject.toml` (`requires-python = ">=3.11"`, `dependencies = []`, `[tool.uv] package = false`) and `uv.lock`, as `setup-slack` and `use-slack-lists` do. Commands run as `uv run --project use-canvas python use-canvas/scripts/canvas.py …`, or directly with a compatible interpreter.
- No third-party packages. An HTTP library or Canvas SDK would put code outside this repository's review in the path of an unscoped token, against the build decision's first reason, and the client needs only the few dozen endpoints in the contract.
- Time-zone conversion uses the system time-zone database, as `render-calendar-agenda` does. macOS and Linux provide it; native Windows would need the `tzdata` package and is unverified.
- The transport disables automatic redirects and attaches the token with `add_unredirected_header`, so no redirect can carry it. Requests are sequential and time out after 60 seconds without data. API (JSON) responses over 16 MiB are refused; file uploads and downloads are not held in memory but stream to and from disk, with no fixed size cap.
- Estimated size including tests: 3,000–4,000 lines, more than Trello's ~2,000 because of the write set and the upload transport. This is an estimate, not a measurement.

### Files
| Path | Contents |
| --- | --- |
| `setup-canvas/SKILL.md` | The setup procedure from the contract. Frontmatter description: "Install the Canvas capability, establish or repair account access with a user-created personal access token, select courses, and diagnose configuration or authentication. Owns the shared provider runtime used by use-canvas." |
| `setup-canvas/references/account-access.md` | Configuration contract, precedence, failure states and reconnection. |
| `setup-canvas/.env.example`, `setup-canvas/canvas-accounts.example.json` | Synthetic values only. |
| `setup-canvas/.gitignore` | `canvas-accounts.json`, `canvas-accounts.*.json`, `!canvas-accounts.example.json`; the root ignore already covers `.env`. |
| `setup-canvas/pyproject.toml`, `setup-canvas/uv.lock` | As above. |
| `setup-canvas/scripts/canvas_auth.py` | Literal configuration loading, account routing, origin validation, transport, pagination, read back-off, error classification and identity check. CLI: `accounts`, `check`, `whoami`. |
| `setup-canvas/scripts/link-skills.py` | Optional global links for `use-canvas`, like the other setup owners. |
| `setup-canvas/tests/test_config.py`, `setup-canvas/tests/test_transport.py` | Offline configuration and transport checks. |
| `use-canvas/SKILL.md` | Reads, export, coverage meanings, the write gate and commands. Frontmatter description: "Read selected Canvas courses' modules, pages, files, assignments, announcements and events, export them as deterministic Markdown/JSON with coverage, or preview and execute supported page, assignment, module, announcement and file-upload changes." |
| `use-canvas/.gitignore` | `canvas-writes.jsonl`. |
| `use-canvas/pyproject.toml`, `use-canvas/uv.lock` | As above. |
| `use-canvas/scripts/canvas.py` | CLI entry and dispatch; `--help` needs no configuration. |
| `use-canvas/scripts/canvas_read.py` | Retrieval, normalisation, identity, deduplication and coverage. |
| `use-canvas/scripts/canvas_export.py` | Deterministic JSON and Markdown writers and temporary-directory publication. |
| `use-canvas/scripts/canvas_html.py` | HTML-to-Markdown conversion and external-content scanning. |
| `use-canvas/scripts/canvas_write.py` | Plan builders for each write command, preview hash, execute controller, readback and audit. |
| `use-canvas/tests/canvas_fixture.py` | A stateful synthetic Canvas behind an injected transport: `Link` pagination, roles, errors, throttling, a separate upload host and a request log. No network. |
| `use-canvas/tests/fixtures/*.json` | Synthetic `course-123` with modules, pages, files, assignments, overrides, announcements and external tools. |
| `use-canvas/tests/test_reads.py`, `test_export.py`, `test_html.py`, `test_writes.py` | The cases below. |

After implementation and verification, also update `README.md` (capability and setup tables), `setup-agent-hands/SKILL.md` (its list of implemented services) and `TODO.md`. Not before: the setup dialogue must not route to a capability that does not exist yet.

### Slices and stop conditions
1. `setup-canvas`: runtime, examples and offline tests. Stop when the tests pass, for review.
2. `use-canvas` reads, export and coverage, with `courses`, `verify` and `download-file`. Stop when the tests pass, for review; then the read smoke test if gate G1 is granted.
3. The approved write set. Stop when the tests pass, for review; then the write smoke test if gate G2 is granted.

Each slice is its own commit series with the `Spike: canvas-access` trailer. Stop and report instead of continuing when: an offline test cannot express a contract item (record the gap); a live check contradicts a "to confirm" item in a way that affects safety (token handling, `denied` versus `failed`, notifications); a slice runs past 1.5 times its share of the estimate; or setup finds token creation unavailable or forbidden by policy (no workaround).

### Synthetic test cases
Configuration and transport (`setup-canvas`):
1. Literal parsing: quoted values stay literal, command substitutions never run, exported values win, a missing selected env file fails, and unknown or self-redirecting keys are refused without echoing values.
2. `base_url`: `http`, paths, queries, fragments, user information and empty hosts are refused; host case and a trailing slash are normalised.
3. The synthetic token never appears in stdout, stderr, exceptions, the audit file or any export.
4. `Authorization` goes only to the configured origin: a cross-origin or non-`/api/v1/` `next` link is refused, a redirect off the instance is not followed, and a same-origin redirect is followed once.
5. `Link` parsing: any header-name case, several relations, missing `last`, a final page without `next`, a repeated `next` (cycle) and the 200-page cap each give the documented result.
6. Throttling: a read that gets `429` backs off a bounded number of times through an injected clock, then marks its collection `failed`; a write that gets `429` stops without retry.
7. Error classification: `401` with an authentication challenge or the invalid-token body is `token_rejected` and fatal; `401` "not authorized", `403` and `404` on a collection are `denied`; `5xx`, malformed JSON and non-JSON bodies are `failed`.
8. Identity: `whoami` with a mismatched `user_id` refuses, and so do exports and writes.
9. IDs: string IDs above 2^53 are preserved exactly, and integer IDs from a server that ignores the header become identical strings.

Reads and export (`use-canvas`):
10. Pagination: a three-page assignment listing exports the same as one page, whatever the page size.
11. Modules: inline items that are omitted, or fewer than `items_count`, trigger the items endpoint, which itself pages.
12. Duplicate module references: one assignment in two modules is exported once with both module item IDs in `referenced_by`; a Page item resolves through its slug to `page_id`; an unknown slug is an `unresolved_reference`; a page renamed during the run is not duplicated.
13. Overrides: a staff fixture with base dates and two section overrides; a learner fixture with effective dates and `all_dates`, where overrides are `not_visible_to_role`, never "none".
14. Time zones: course and user zones differ; a due date in the hour when clocks go back renders correctly; UTC values pass through unchanged; date input refuses a naive time, a nonexistent local time and an ambiguous one, and accepts an explicit offset.
15. Announcements: more than one page, including some older than 14 days, all exported.
16. Calendar events: requests carry `all_events=true`, and more than ten selected courses are split into batches of ten context codes.
17. Partial failures: one failed page body makes `page_bodies` `partial` with the missing identity; a refused files listing gives `denied` with `referenced_only` files; a failed assignments listing blocks publication and leaves the previous export byte-for-byte intact; `--allow-partial` publishes with coverage; an output directory that is not a previous export, and a symlinked output, are refused.
18. External content: an ExternalTool item, an external tab, an `external_tool` assignment, an iframe in a page and a media embed each appear once as gaps, in stable order.
19. Determinism: two runs with shuffled response order, different page sizes, a different clock and changed volatile fields (`read_state`, file `url`, thumbnail) produce byte-identical files apart from `run.json`.
20. HTML conversion: a fixed corpus converts to fixed Markdown, unsupported markup is marked, and nothing is fetched.
21. Provenance: every record has its identity, API path, web link and source timestamps where present; no export contains a token or a Canvas download URL.
22. File download: `download-file` streams to disk, a received size that differs from the metadata fails and leaves no partial output, `--max-bytes` stops early, and an existing output is refused without `--force`.

Writes (`use-canvas`):
23. Every write command previews with zero write requests in the fixture's request log.
24. `--execute` without `--expect`, or with a different hash, sends nothing.
25. Stale edits: a page body, an assignment's `updated_at` or a module changed after preview refuses with zero writes; a same-name resource created after preview blocks the create.
26. Readback: a matching readback reports `verified`; a scalar mismatch exits 3 as `PARTIAL or uncertain`; a sanitised HTML difference reports `verified_with_sanitizer_changes` with the difference.
27. Multi-step: `create-module --published` failing at the publish step reports the created module's ID, does not retry, and a fresh preview refuses the duplicate create.
28. `edit-assignment` never sends `assignment_overrides`, and warns when base dates change on an assignment with overrides.
29. Notifications: `notify_of_update=false` is always sent unless `--notify`; `create-announcement` without `--notify-course` is refused at execute; `edit-announcement` on a posted announcement is refused.
30. Upload: `on_duplicate` is always explicit; a name collision refuses by default; `--replace` with a different file ID refuses; the step-2 request carries no `Authorization` header and posts `upload_params` unchanged with the file last; a confirmation `Location` off the instance stops as uncertain without sending the token; a local file changed after preview refuses; a size mismatch on readback is uncertain; the upload body streams from disk rather than being read whole.
31. Gate conditions: an unselected course, `write: false`, a concluded course and a permission reported `false` each refuse in preview; an unreported permission shows as unknown, and a Canvas refusal is reported with no change made.
32. Uncertain transport and audit: a network error after sending exits 3 and the audit marks the step uncertain; an unwritable audit path refuses before sending; audit records contain no body or token.
33. `--help` for both skills runs without configuration or network.

### Rollback and recovery
- Code: each slice is committed separately, so reverting its commits removes it. Nothing private is in Git, so a code rollback never touches configuration.
- Local state: the token and account files stay untracked in `setup-canvas/`. To uninstall, the user deletes the token in Canvas; then the env value, the alias and any global links (which `link-skills.py` previews) are removed.
- Exports: a failed run leaves the previous export in place, and the swap keeps the old directory until the new one is in position.
- Remote changes have no automatic rollback. Page edits: `revert-page` to the revision ID recorded in the preview or audit. Assignment, module and module-item edits: run the edit again with the "before" values from the saved preview. Creations: unpublish with an edit, or the user removes the resource in Canvas; there is no delete command. Announcements: notifications cannot be recalled, though delayed posting leaves a window to edit. Overwritten files cannot be restored through this tool, which is why name collisions refuse by default.

### Choices awaiting the user (G0)
Agent proposals not yet accepted. Each says what it does, why it was proposed and what it costs.
- **Executing requires the preview's hash (`--expect`).** A preview prints a fingerprint of exactly what would be sent and of the Canvas state it was based on. Execution refuses unless it is handed that fingerprint and a fresh rebuild of the plan produces the same one. That blocks an unreviewed or out-of-date change: a page someone else edited after the preview, a local file that changed, a different command. Canvas has no "save only if unchanged" request, so this is the main protection against overwriting another editor's work. `use-excel-workbooks` already requires it; `use-trello` only recommends it. Cost: every write needs a preview first, which approval needs anyway.
- **Per-course write switch.** Each selected course carries `"write": false` until the user sets it to `true`, and writes to any other course are refused locally. The token can change anything the user can change on the whole instance, so this keeps a mistyped course ID, or instructions planted in course content, from aiming a write at the wrong course. Canvas does not enforce it; it is a local guard. Alternatives: one switch per account (simpler, coarser), or none (previews only).
- **Private write log.** `canvas-writes.jsonl`, ignored and owner-only beside the skill, records each write's command, target IDs, fingerprint and per-step outcome (sent, verified, uncertain), never content or the token. After an interrupted multi-step write it shows which steps landed and which IDs were created, so recovery does not create duplicates, and it keeps the revision IDs `revert-page` needs. If the log cannot be written, the write is refused before anything is sent. The Microsoft Files, Excel and Planner capabilities keep similar logs. Cost: a growing private file of course and item IDs.
- **The user's own grades left out of exports unless asked for.** Exports include the user's own submission status (submitted, late, missing) by default, but scores and grades only with `--include-grades`. Grades are the most sensitive data an export holds, and exports get copied elsewhere. The alternative is to include them by default.
- **HTML input only.** Canvas stores page, assignment and announcement content as HTML, and the write commands take an HTML file. A reliable Markdown-to-HTML converter is either a substantial amount of new code or a third-party package, which the runtime choice avoids; an agent can write HTML directly or convert Markdown beforehand with a separate tool. HTML files over 1 MiB are refused as a guard against passing the wrong file (a long page is typically tens of kilobytes); Canvas's own limits still apply.
- **Runtime: Python 3.11+ with only its standard library.** See [runtime and dependencies](#runtime-and-dependencies). The token can act as the user everywhere, so all code that handles it should live in this repository and change only through reviewed commits; third-party packages update on their own schedules. Python suits Canvas's nested JSON, HTML, time zones and multipart uploads better than the Bash that `use-trello` uses.
- **Three slices with a review stop after each.** See [slices and stop conditions](#slices-and-stop-conditions). Early review catches design problems before the larger write code is built on top of them. The alternative is one delivery with a single review at the end.

### Approval gates
| Gate | Needed before | The user decides |
| --- | --- | --- |
| G0 | Any implementation | Decided 2026-10-29: the full write set, and no fixed file-size cap. Still open: the [choices awaiting the user](#choices-awaiting-the-user-g0). Offline work needs no new access. |
| G1 | The first live call | The instance and alias, creating the token themselves, which courses and read commands the smoke test covers, and where its private output goes (outside this repository). |
| G2 | The first live write | An exact course where test writes are acceptable (preferably one with no other members), which write commands to exercise, and each reviewed preview. Announcements only where nobody else is notified, or skipped. |
| G3 | Global links or client registration | A separate installation choice, as for the other capabilities. |
| G4 | Publication | Reviewing the public diff. Pushing is the user's. |

Browser fallback for external content is not planned; it would need its own approval.

## Ready for human QA
None yet. After implementation, ask the user to verify account/course selection, consent clarity, export readability, write-preview clarity, and behavior when content is unavailable. Do not move implementation items here before their technical checks pass.

## Done
- [x] Select reuse, a small adapter, or a justified minimal API client; record reasons and unresolved gaps. Do not build a new server before this decision. — Progress 2026-10-27: access check and route comparison recorded in the concept's follow-up section; the agent proposal is now a small read-only REST client with the MCP as an optional companion. The user's choice is pending. — Update 2026-10-27: with change detection out of scope and writes later, the recommendation became building both skills here, with the MCP only as reference code. — Decided by the user 2026-10-28: build. See the concept's scope and build decisions.
- [x] Define the separate setup/use responsibilities and reuse-first research scope — captured in the conceptual document on 2026-10-27; candidate selection and live validation remain open.
- [x] Define public-safe examples and fixture boundaries — this pair contains no real connection, course or learner data, and the planned test suite uses synthetic material.
- [x] Read the target repository's current instructions, workflow configuration and capability conventions before choosing implementation paths. — Done 2026-10-27: read `AGENTS.md`, `TODO.md`, `project-workflows/workflow.toml` and the existing spike pairs. Native skills live at the repository root (`setup-canvas/`, `use-canvas/` would follow that), provider dependencies stay explicit, and spike pairs carry `attention: live` plus an Opened/Slug line, which this pair now follows. No existing Canvas spike or skill was present.
- [x] Find maintained Canvas MCP candidates through their original repositories. Record repository URLs, versions/commits, maintenance evidence, license, supported clients, setup requirements and API scope. — Done 2026-10-27 for the first pass: survey, metadata and fit notes are in the concept's candidate evaluation. Supported clients and setup requirements were taken from READMEs; nothing was installed. Instructure's own MCP is a partner pilot with no availability date.
- [x] Transfer this pair from temporary private staging into this repository — added 2026-10-27. Bodies were copied unchanged and compared by diff; the only deliberate edits were this repository's frontmatter (`attention: live` alone) and the Opened/Slug line. The private transfer coordinator was not copied.
- [x] ~~Compare each viable candidate against the conceptual document's retrieval contract. Verify pagination, stable IDs, duplicate handling and failure behavior in code/tests where documentation is insufficient.~~ — Progress 2026-10-27: pagination and the write-tool policy were read in code for `vishalsachdev/canvas-mcp`; stable IDs, duplicate module references and partial-failure output are not yet checked for either viable candidate. — Dropped 2026-10-29 at the user's direction: moot after the 2026-10-28 decision to build rather than reuse. The community MCP is reference code only; the same pagination, identity, duplicate and failure checks now apply to this repository's own client through the plan's synthetic tests.
- [x] Bring the concept's purpose, partial-failure row and snapshot paragraph in line with the build and scope decisions, and drop "baseline advancement" from the test-inspection item. — Added and done 2026-10-29.
- [x] Check the official API behavior for announcements, modules/items, pages, files, assignments, effective deadlines/overrides, timezone handling, throttling and external-tool limitations. Separate documented capabilities from behavior still requiring a live test. — Done 2026-10-28 from the Canvas API documentation (pagination, throttling, string IDs, courses, permissions, tabs, modules, pages, assignments and overrides, announcements, discussion topics, calendar events, files and uploads, personal-token settings). The findings shape the use-canvas contract; behavior still needing a live test is listed under its "to confirm in the live smoke test".
- [x] Specify `setup-canvas`: connection/account discovery, explicit course selection, consent boundaries, verification, reconnection and clear failure states. — Done 2026-10-28 as an agent proposal in the concept's setup-canvas contract: instance and account selection, the token-availability check without creating a token, storage in the setup folder's ignored configuration, verification, explicit course selection, reconnection and a failure-state table. Awaits the user's review.
- [x] Specify `use-canvas`: read inputs, resource identities, normalized output, provenance, per-resource coverage, snapshot/delta semantics, removal confirmation and last-successful baseline updates. — Scope change 2026-10-27: snapshot/delta, removal confirmation and baselines are out of scope here. This item now covers deterministic export (stable ordering, byte-identical reruns over unchanged content) and per-resource coverage reporting, plus the preview/execute contract for later writes. — Done 2026-10-28 as an agent proposal in the concept's use-canvas contract. Writes are in the first version (user decision 2026-10-28), so it also proposes twelve write commands, recommends all of them for the first version (`edit-announcement` only before posting), and lists what was left out. Awaits the user's review and trimming.
- [x] Write the bounded implementation plan with exact files, dependency versions, tests, recovery/rollback and approval gates for any new access. — Done 2026-10-28 as the agent proposal in this file's implementation plan: Python 3.11+ standard library with per-skill uv manifests and no third-party packages, exact file list, three slices with stop conditions, 32 synthetic test cases, rollback and gates G0–G4. Not approved.

## Research exit gate
Selection evidence, gap assessment, skill contracts and the bounded implementation plan are required. “An MCP exists” is not sufficient. If required capability cannot be verified without new access, name the exact dependency and wait for authorization rather than treating it as success.
