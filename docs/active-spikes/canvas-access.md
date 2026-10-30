---
attention: live
---

# Canvas setup and repeatable retrieval
Opened: 2026-10-27. Slug: `canvas-access`.

## Purpose
Design and build `setup-canvas` and `use-canvas` in this repository: a small client of the official Canvas REST API that connects an account with a personal access token the user creates, exports selected courses deterministically with honest coverage, and makes gated writes. The [candidate evaluation](#candidate-evaluation--2026-10-27) and [access follow-up](#access-and-approach--follow-up-2026-10-27) record the survey of existing integrations that came before the [build decision](#scope-and-build-decisions). This document does not claim that any institution-specific authentication has been tested.

[Work and verification](canvas-access.todo.md).

## Scope and ownership
- `setup-canvas` handles connection discovery, account selection, informed consent, connection verification and explicit course selection. It must not silently create credentials or expand access.
- `use-canvas` handles repeatable retrieval and deterministic export for the selected courses, stable resource identities, coverage reporting and provenance. Detecting changes between runs is out of scope (see the scope decisions below).
- The consuming agent interprets changes and decides what belongs in its private notes or task/calendar systems. This integration does not own those policies or write to downstream systems automatically.
- The first version includes writes (see the scope decisions below), each behind this repository's preview/execute gate; unattended write automation stays out. Browser fallback is a separately approved action, not an automatic continuation after an API limitation.

## Selection before construction
Inventory maintained MCP candidates from their original repositories and documentation. Compare maintenance/release activity, license, client/runtime compatibility, installation and update burden, actual API coverage, pagination, error handling, testability, and the ability to restrict operations to the authorized scope. Read the code or tests where necessary; a tool name or README claim is not evidence of working behavior.

Use the [official Canvas API documentation](https://documentation.instructure.com/doc/api/index.html) as the capability baseline. Its current index points to the [Instructure developer portal](https://developerdocs.instructure.com). Confirm the relevant endpoint behavior there during research. If no maintained candidate is adequate, document the specific gaps and compare a small adapter to a direct API client before proposing custom infrastructure. Do not start a new MCP server by default.

## Retrieval contract to evaluate
| Area | Required behavior |
| --- | --- |
| Identity | Preserve stable course and item IDs; namespace by connection and resource type; avoid title-only identity and lossy numeric conversion. |
| Coverage | Explicitly cover or report gaps for announcements, modules and module items, pages, files and assignments. Follow pagination rather than treating the first page as complete. |
| Changes | Moved to the consumer (2026-10-27). Export with stable ordering and formatting so that two runs over unchanged content are byte-identical and a consumer can compare them. An unchanged result is distinct from an unperformed or partial check. |
| Provenance | Record source URL, resource ID/type, retrieved/last-checked time, source update time when available, and retrieval coverage. Preserve useful links without exposing connection secrets. |
| Deduplication | Recognize the same assignment, page or file referenced through multiple modules. Repeat runs must not emit duplicate items or downstream work. |
| Partial failure | Authentication errors, rate limits, missing pages, denied items and incomplete pagination are not proof of deletion. Report them per resource and never let a partial export replace a complete one unasked. Only complete coverage supports a consumer's conclusion that something was removed. |
| Dates | Preserve original timestamps and timezone context. Distinguish due, availability and lock dates; verify effective dates and applicable overrides rather than assuming one course-wide deadline. |
| External content | Identify external-tool links or embedded content that cannot be retrieved through the chosen integration. Report the limitation and source link; request approval before any browser fallback. |

Not every endpoint offers an incremental cursor, and no single “updated since” query covers every resource type, so `use-canvas` reads complete current state on every run. Its [coverage statuses](#coverage) and all-or-nothing publication keep a partial run from looking like deletions.

## Deliverables and decision gates
1. An evidence-linked comparison and selected approach, or an explicit no-fit result with the smallest justified alternative.
2. Separate setup and use skill contracts, including inputs, outputs, error/coverage semantics, consent boundaries and recovery behavior.
3. A bounded implementation plan with concrete files, dependency/version choices, test cases, rollback, and a stop condition. Get approval where the plan requires new access or materially expanded scope.
4. Synthetic fixtures and tests for pagination, duplicate references, changed deadlines, overrides, timezone edges, partial failures, unavailable external content, and reruns.
5. Later, authorized live smoke tests (reads first, then writes against an explicitly authorized target) and human QA. Keep live connection details and private test evidence outside the public repository; record only generic results and limitations publicly.

## Candidate evaluation — 2026-10-27
Agent research from public repositories, GitHub metadata and vendor pages. Nothing here was installed, authenticated or run against a live Canvas instance, and no candidate has been selected by the user.

**Vendor route.** Instructure's [October 2026 New & Next post](https://www.instructure.com/resources/blog/what-we-shared-october-2026-new-next-showcase) describes bi-directional MCP support as future work, with "experimentation … underway with an initial group of institutions and partners" and no availability date. Treat a vendor-hosted MCP as unavailable to an ordinary user until an institution actually enables it; revisit before building anything that would duplicate it.

**Community candidates checked** (metadata from `gh api` on 2026-10-27):

| Repository | State | Fit against this spike |
| --- | --- | --- |
| [vishalsachdev/canvas-mcp](https://github.com/vishalsachdev/canvas-mcp) | MIT, Python, about 309 stars, release v1.16.0 (2026-10-25) after a steady release cadence, published security advisories, CI and a large test suite. | Strongest maintained candidate. Read tools cover announcements, modules and module items, pages, files, assignments and a course-structure tree. `core/client.py` follows Canvas `Link` pagination with an origin/endpoint check and an explicit page ceiling, failing rather than looping. `core/tool_policy.py` gates side-effect tools through `ALLOWED_WRITE_TOOLS`: HTTP defaults to read-only, but **stdio registers every write tool unless the variable is set**; `none` removes them on both transports, and a set-but-empty value fails closed. Canvas text is fenced as untrusted data. Personal-token auth from a local `.env` or the OS keychain (desktop extension). Far broader than needed (educator, grading, messaging, code-execution tools), so the setup must pin a release and restrict it. |
| [boyuchengz/canvas-mcp](https://github.com/boyuchengz/canvas-mcp) | MIT, JavaScript, created 2026-10-25, no releases yet. | Read-only by construction (26 `GET`-only tools) with a good scope match, but two days old. Designed as a hosted HTTP connector behind a URL secret, which adds a deployment and secret to manage. Lists are capped at 500 items per call and long text at 20,000 characters, so truncation must be reported as partial coverage. Revisit once it has releases and history. |
| [DMontgomery40/mcp-canvas-lms](https://github.com/DMontgomery40/mcp-canvas-lms) | No license file detected, last push 2026-05. | Course-management and grading oriented; no license makes reuse unclear. Not pursued. |
| [r-huijts/canvas-mcp](https://github.com/r-huijts/canvas-mcp), [plyght/canvas-mcp](https://github.com/plyght/canvas-mcp), [ahnopologetic/canvas-lms-mcp](https://github.com/ahnopologetic/canvas-lms-mcp), [sweeden-ttu/canvas-lms-mcp](https://github.com/sweeden-ttu/canvas-lms-mcp) | Small or stale; one targets a single institution; plyght has no license. | Not viable as maintained dependencies. |

**Gap no candidate fills.** Every candidate answers interactive questions; none keeps a last-successful baseline, emits new/changed/removed summaries, or distinguishes an unperformed or partial check from "no change". That part of the retrieval contract belongs to `use-canvas` in any design.

**Agent proposal, not a decision.** Reuse `vishalsachdev/canvas-mcp` pinned to a reviewed release, run locally over stdio with `ALLOWED_WRITE_TOOLS=none`, and add no custom Canvas server or scraper. `setup-canvas` would own installing that pinned release, the token's storage outside this repository and the read-only configuration check (confirm no side-effect tool is listed). `use-canvas` would own the snapshot/baseline/delta layer over the MCP's read results. Whether that layer can stay an agent procedure over MCP reads or needs a small deterministic API client (for reproducible snapshots and cheap reruns) is the open design question; decide it with synthetic fixtures before writing code. Institutions may restrict personal access tokens, so the setup must report that case rather than work around it.

## Access and approach — follow-up, 2026-10-27
**Initial position (superseded by the scope decisions below):** retrieval first; write permission acceptable but not needed.

**Access is institution policy, not a Canvas constant.** On the first target instance the user's settings page offers **New Access Token**, and the institution's own help pages walk students through creating one for a third-party integration. No explicit rule on students using personal tokens with their own tools was found. Other institutions forbid it outright: [Texas A&M](https://lms.tamu.edu/support/canvas-api) limits API access to course staff, and the [University of Missouri System](https://tdx.umsystem.edu/TDClient/66/MOOnline/KB/ArticleDet?ID=2193) and [USNH](https://td.usnh.edu/TDClient/60/Portal/KB/Article/5520/Canvas-User-API-Token-Access-UNH-PSU) do not approve student tokens, citing MFA/SSO bypass and unvetted AI tools. So `setup-canvas` must check whether token creation exists, never assume it, and treat its later removal as a normal failure state. Nothing was created during this check.

**Three routes, in order of preference (agent proposal):**
1. **Official REST API with a personal token, read-only.** Deterministic, documented and paginated; the same JSON every run, which the snapshot/delta contract needs. Token stays in a private config outside the repository and can be scoped by expiry and revoked from the settings page.
2. **Official REST API through the signed-in browser session.** A same-origin `GET /api/v1/...` from a logged-in tab returns the same JSON without creating a token. Useful when tokens are unavailable or unwanted; needs explicit browser approval each run and is less suitable for unattended use.
3. **Page scraping.** Brittle against UI changes and only for content the API does not expose (some external-tool or embedded content). Last resort.

**MCP versus a small client.** The surveyed MCP's advantages are real: it already handles Link-header pagination, Canvas wire quirks (classic versus New Quizzes, external-tool assignments), prompt-injection fencing and a stream of security fixes, with a large test suite. It is the quickest way to ask ad-hoc questions of a course. It does not provide what this spike's contract centres on: deterministic snapshots, stable baselines and change summaries. An MCP is driven by an agent call by call, which is token-heavy, nondeterministic in coverage and hard to rerun identically. It is also far broader than needed (educator, grading, messaging and code-execution tools; writes on by default over stdio) and ships breaking releases every few weeks. A small read-only client over the handful of endpoints that matter (courses, modules and items, pages, files, assignments with overrides, announcements) matches the existing native capabilities here, which are deterministic CLIs with bounded exports. The hard parts it would own are pagination, throttling and partial-failure semantics, all documented by the official API.

**Revised proposal (still not a decision):** build `use-canvas` as a small read-only REST client with Markdown/JSON snapshots and deltas, behind `setup-canvas` token checks, and treat the community MCP as an optional companion for interactive questions rather than the retrieval backend. This supersedes the earlier MCP-first proposal in the candidate evaluation above.

## Scope and build decisions
- **Change detection is out of scope (2026-10-27).** `use-canvas` exports current state deterministically; comparing runs belongs to whatever consumes the export. No snapshot archive or delta engine lives here.
- **Writes are in scope (2026-10-27) and in the first version (2026-10-28),** each behind this repository's preview/execute gate. The first version may carry a broad write set rather than a minimal one; the proposed set and recommendations are in the [use-canvas contract](#proposed-writes).
- **Write set accepted, no file-size cap (2026-10-29).** All twelve commands in the [proposed writes](#proposed-writes) table are in the first version. Uploads and downloads have no fixed size cap: files stream to and from disk, and Canvas's own quota and size limits decide.
- **Safeguards, history and formats (2026-10-29).** Executing a write requires the reviewed preview's hash. There is no per-course write switch: writes may target any course the account can change, protected by the preview gate. `use-canvas` keeps a history of reads and writes whose location the consumer chooses; the tool does not decide where that history lives. Exports include the user's own scores and grades. Markdown is the reading and writing format, so bodies convert between HTML and Markdown in both directions. Well-known third-party packages are acceptable when pinned and when they save real work.
- **Learner writes, history format, images and build stages (2026-10-29).** The first version adds learner-role writes: submitting assignments (with comments on the user's own submission), discussion replies, group pages, group files and personal files. The history is a structured, machine-readable file set with a deterministic retention policy owned by the tool. Bodies whose images carry information also keep their HTML. Implementation proceeds in three stages with a review stop after each.
- **Community MCP re-examined before building (requested 2026-10-29).** The user asked for `vishalsachdev/canvas-mcp` to be judged on its specific merits rather than set aside; the [re-examination](#community-mcp-re-examined--2026-10-29) is below. After reading it the user confirmed building (2026-10-29), so the build decision and the decisions above stand.
- **Informational images are downloaded (2026-10-29).** Exports also save the images that carry information, so an agent can see them; decorative images are not downloaded. See the export rules below.
- **Build rather than reuse (decided 2026-10-28).** Build `setup-canvas` and `use-canvas` here, in the same shape as the other native capabilities, and do not run the community MCP with a real token. Reasons recorded with the decision:
  1. A Canvas personal access token cannot be narrowed for ordinary users (scopes need an administrator-configured developer key), so any code holding it can act as the user everywhere: submit work, post, message and, where the account also holds a course-staff role, read student data. That token should be used only by code that has been read, is small, and changes only through reviewed commits here. The community server is large (educator, grading, messaging and code-execution tools), releases every few weeks, and would need a fresh review for each upgrade.
  2. The cost is known. The Trello capability has the same shape (export, preview/execute writes, synthetic tests) and is about 2,000 lines including tests. A read-first Canvas client covering courses, modules and items, pages, files, assignments with overrides, and announcements is a similar size.
  3. Retrieval, normalization, conversion and deterministic export run as scripts without a model invocation or an agent-driven MCP session. Routine refreshes therefore need no model processing of the course contents; interpreting or acting on the output is a separate consumer step.
  4. Writes slot into the existing preview/execute gate, which also limits the damage prompt injection can do through course content written by other people (posts, announcements).
  5. The community MCP stays useful as MIT-licensed reference code for Canvas quirks such as New Quizzes and external-tool assignments; attribute anything adapted from it.

Revisit if Instructure ships its own MCP with institution-managed, scoped OAuth; that could replace the personal-token route. This supersedes the read-only and snapshot/delta parts of the revised proposal above.

## Community MCP re-examined — 2026-10-29
Agent reading of `vishalsachdev/canvas-mcp` at release v1.16.0 (`main` at `bbf53db`, 2026-10-28): source, changelog, lock file, configuration template and published security advisories. Nothing was installed or run.

**Provenance.** MIT-licensed. Maintained by Vishal Sachdev of the University of Illinois Urbana-Champaign (package metadata and GitHub profile); about 300 stars and 100 forks. In the 30 days to 2026-10-28 it took 402 commits: 230 by the maintainer, 98 under a Claude author and 54 by one other contributor, with 154 carrying a Claude co-author line; automated triage commits also land on `main`. There have been twelve releases since 2026-07-05, the last two (v1.15.0 and v1.16.0) two days apart, and the changelog flags breaking changes in several. Four security advisories were published on 2026-10-25 and fixed in v1.16.0: a prompt-injected assistant changing grades or disclosing course data through write tools (high), a sandbox escape in its TypeScript code-execution tool (high), the Canvas token being sent to a host chosen by the file-storage service during upload confirmation and to off-origin download URLs (medium), and owner-only file permissions not applying on Windows (low).

**Size and shape.** About 33,000 lines of Python in `src/`, a TypeScript code-execution API, 129 tools (about 51 in its student profile and 96 in its educator profile; all by default) and 46,000 lines of tests. Runtime dependencies include `fastmcp`, `mcp`, `httpx`, `pydantic`, `python-dateutil`, `python-dotenv` and `uvicorn`; the lock file has 107 package entries including development tools.

**Safety controls.** `ALLOWED_WRITE_TOOLS` decides which write tools exist at all (on stdio the default is all of them). `CANVAS_ROLE` selects the student or educator profile. Learner writes stay unregistered unless named in `STUDENT_WRITE_TOOLS`, and a per-course policy read from the syllabus then denies them unless the instructor opts in (`COURSE_AGENT_POLICY_ENABLED` defaults to on, `COURSE_AGENT_POLICY_DEFAULT` to deny); an operator can switch that off. Submissions and deletions are two-step, with a single-use token bound to the previewed content, which its own documentation notes the model can redeem itself. Whole-body edits accept optional drift guards (`expect_updated_at`, a body SHA-256) and read the result back. Untrusted Canvas text is fenced, and pagination checks origins under a page ceiling. Other writes, such as creating a page or posting a discussion entry, run on the first call; their human gate is the MCP client's tool-approval prompt, which shows the call's arguments rather than a computed change.

| Need | canvas-mcp v1.16.0 | Built here |
| --- | --- | --- |
| Deterministic export with per-resource coverage | Not offered; reads are agent tool calls | The core of `use-canvas` |
| The twelve course-content writes | All but page revision revert, plus deletes (which can be switched off) | All; no deletes |
| Submit an assignment, comment on the submission | Yes, two-step | Yes |
| Discussion replies | Yes, sent on the first call | Yes, previewed |
| Group pages, group file uploads, personal file uploads | Not offered (group files are read-only) | Yes |
| A computed preview before every write | Submissions and deletions only | Every write |
| History of reads and writes | Not offered | Yes |
| Code holding the token | ~33,000 lines and 107 locked packages, changing weekly | An estimated 4,000–5,000 lines and two converter packages, changing only through reviewed commits |

**Agent recommendation, which the user accepted on 2026-10-29: keep building, with the MCP as reference code.** The maintainer is identifiable and the project fixes and discloses security problems, so trust in its author is not the obstacle. The obstacles are specific. It does not provide the export, so most of `use-canvas` would be written anyway and two programs would hold the token. It lacks three of the five learner writes chosen on 2026-10-29. Most of its writes go out without a computed preview. At its size and release pace, no upgrade could be reviewed before it runs with an unscoped token, and pinning an old release forgoes its security fixes. A later middle route, running it beside `use-canvas` for interactive questions with its student profile and a short write allowlist, stays possible but adds a second token holder.

Findings from its code that the contracts below adopt: discussion topics and the syllabus have no `updated_at` (measured live by that project), so their edits are conflict-checked by body hash; Canvas can quietly create a plain discussion instead of an announcement when the token lacks permission, so announcement readback checks the announcements listing; and its upload-confirmation token leak is the case this design's upload transport refuses.

## setup-canvas contract — agent proposal, 2026-10-28
Implemented in slice 1 and approved by the user on 2026-10-30; live account verification remains pending. It follows the existing setup skills: setup owns installation, account selection, credentials, reconnection and the provider runtime that `use-canvas` loads, and it never writes to Canvas. The [implementation plan](canvas-access.todo.md#implementation-plan--agent-proposal-2026-10-28) turns it into files and tests.

### Configuration
Private configuration lives in the `setup-canvas/` folder beside its examples, in two ignored files:
- `.env`: literal `CANVAS_*` assignments: one token variable per account (`CANVAS_TOKEN_EXAMPLE=`) and, optionally, `CANVAS_HISTORY_DIR`, the location of the [history](#write-gate). It is parsed as data and never sourced. Exported variables take precedence; `CANVAS_ENV_FILE` or `CANVAS_CONFIG_DIR` selects another location, and a missing selected file fails. The file cannot redirect its own location or any account's host.
- `canvas-accounts.json`: an `accounts` array. Each entry has `alias`, `base_url`, `user_id` (empty until first verified), `token_env`, an optional `token_expires` (`YYYY-MM-DD`, the expiry the user chose when creating the token) and `courses`, the explicit selection of course IDs to export.

```json
{"accounts": [{"alias": "example", "base_url": "https://example.instructure.com", "user_id": "", "token_env": "CANVAS_TOKEN_EXAMPLE", "token_expires": "2027-01-31", "courses": ["123"]}]}
```

`base_url` is the instance origin only: `https`, a host and an optional port, with no path, query, fragment or user information. The host is lower-cased and a trailing slash dropped. Institutions often use their own domains, so the host is not restricted to `instructure.com`. The token goes only to that origin, in an `Authorization: Bearer` header (the API documentation recommends the header over the query parameter), and never into a URL, command argument, log or error message.

Course selection controls what `use-canvas` exports. It is not a write restriction, and it does not narrow the token, which can still act everywhere the user can.

### Connecting an account
1. Explain the trade-off first: a personal access token is password-equivalent, cannot be scoped without an administrator-configured developer key, and lets whoever holds the file act as the user across the whole instance. This capability calls only the endpoints in the `use-canvas` contract, but the token itself is not limited to them.
2. Ask the user to check their institution's published policy on personal tokens and third-party tools. Setup cannot determine policy, and a visible button is not permission. If policy forbids it, stop and say so. Do not offer the browser-session route or scraping as a workaround; each is a separate decision.
3. Ask the user to open `https://example.instructure.com/profile/settings` in their own browser and report whether **New Access Token** appears under Approved Integrations. Administrators can turn creation off (the Canvas permission documentation names a *Limit Personal Access Token Creation* account setting, and Canvas deploy notes describe a separate student and observer restriction), so absence is a normal outcome: report `token_creation_unavailable` and stop. The agent may look at that page itself only with explicit browser approval, and never presses the button.
4. If creation is available and permitted, the user creates the token themselves, with a purpose label and an expiry date, and pastes it into the ignored `.env` entry in their own editor. Setup never asks for the token in chat, in a command argument or in a tracked file, and never creates, regenerates or deletes tokens through the API.
5. Before writing either private file, confirm `git check-ignore` reports it ignored, create it from the example only if absent, preserve existing accounts, and set owner-only permissions where supported.

### Verification
- `check ALIAS` (offline): configuration parses, `base_url` is valid, the token variable is set (never printed), `token_expires` has not passed (warning within 14 days), course IDs are well-formed, the env file is not group- or world-readable, and Python and the time-zone database are usable. No network request.
- `whoami ALIAS` (one authorized read): `GET /api/v1/users/self` and `/api/v1/users/self/profile`. It prints the Canvas user ID, display name and time zone only, not email or login. With `user_id` empty it asks the user to confirm the identity before recording it; with `user_id` set, a mismatch is `identity_mismatch` and every later command refuses to run.
- `use-canvas courses ALIAS` lists the user's courses (`GET /api/v1/courses`; active enrollments by default, `--all-states` adds completed ones) with ID, name, code, term, course state, the user's enrollment types and the course time zone. The user picks courses and the agent records only their IDs.
- `use-canvas verify ALIAS` reads each selected course, its visible navigation tabs and the user's course permissions, and reports per course: accessible or not, enrollment types, concluded or active, visible internal and external tabs, and which write families the reported permissions allow. It reports local readiness, remote read access and write readiness separately, and never performs a test write.

### Reconnection and removal
An expired, revoked or regenerated token shows as `token_rejected` on the next request. The user creates or regenerates a token in their profile settings (if still permitted) and replaces the env value; `whoami` must then match the recorded `user_id`. A changed instance address updates `base_url` only after the user confirms it, followed by `whoami`. To disconnect, the user deletes the token in Canvas, and the env value and alias are then removed locally. Setup never moves or rewrites another account's entry.

### Failure states
| State | Detected by | Next step |
| --- | --- | --- |
| `config_missing`, `config_invalid` | `check` | Create from the examples, or fix the named field. Values are never echoed. |
| `base_url_invalid` | `check` | Use the `https://host` origin from the browser's address bar. |
| `token_missing` | `check` | The user fills the named env variable. |
| `token_expired_local` | `check`, from `token_expires` | The user creates or regenerates a token. |
| `token_creation_unavailable`, `policy_forbids` | The user's report in steps 2–3 | Stop. No workaround is offered. |
| `network_error` | Any live request | Check connectivity and the host. Only throttled reads are retried, a bounded number of times. |
| `token_rejected` | Canvas's invalid-token error, or a `401` with an authentication challenge and no permission message | Reconnect as above. A run stops before publishing any export. |
| `identity_mismatch` | `whoami`, and before every export or write | Check the alias and token; nothing proceeds. |
| `course_denied`, `course_not_found` | `verify` | Remove the course, or the user checks their enrollment. |
| `course_concluded` | `verify` | Reads continue; writes are refused. |
| `throttled` | `429` | Reads back off a bounded number of times; writes stop without retry. |
| `tz_data_missing` | `check` | Install time-zone data for the platform. |
| `config_insecure` | `check` | Restrict the env file to its owner (`chmod 600`). |

## use-canvas contract — agent proposal, 2026-10-28
The user settled every design choice by 2026-10-29 (see the scope and build decisions and the plan's [G0 choices](canvas-access.todo.md#g0-choices)). Reads, export, coverage, downloads and history were approved in slice 2 on 2026-10-30. All fifteen writes are implemented and tested offline in slice 3, awaiting user review and separately authorized live validation. `use-canvas` owns reads and deterministic export for selected courses, plus gated writes to explicitly selected course, group and personal contexts of a configured account. It loads the `setup-canvas` runtime and needs no other capability. Behaviour described as documented comes from the Canvas API documentation read on 2026-10-28; points that need a live check are listed at the end of this section.

### Reads
Requests are sequential (Canvas throttles parallel requests harder), send `Accept: application/json+canvas-string-ids` so every ID arrives as a string, ask for `per_page=100`, and follow the `Link` header's `rel="next"` URL as an opaque value. Header names are matched case-insensitively. A `next` URL on another origin or outside `/api/v1/` is refused. A repeated `next` URL, or more than 200 pages, marks that collection `failed`. `rel="last"` is optional in Canvas and never relied on.

| Resource | Request (under `/api/v1`) | Notes |
| --- | --- | --- |
| Course | `GET /courses/:id?include[]=term&include[]=syllabus_body&include[]=total_scores` | Name, code, state, `time_zone`, term, the user's enrollment types and current course score and grade, syllabus. |
| Navigation | `GET /courses/:id/tabs` | Which areas the user can see. External tabs become external-content gaps. |
| Permissions | `GET /courses/:id/permissions?permissions[]=…` | Role-dependent coverage and write preflight. Names used by the read report were checked against the official permission list on 2026-10-30; institution-specific responses remain unverified. |
| Modules and items | `GET /courses/:id/modules?include[]=items&include[]=content_details`, then `GET /courses/:id/modules/:module_id/items?include[]=content_details` | Canvas may omit inline items when there are many, so the items endpoint is used whenever `items` is missing or shorter than `items_count`. |
| Pages | `GET /courses/:id/pages?include[]=body` | A body missing from the listing is fetched by explicit `page_id:ID` addressing. |
| Files and folders | `GET /courses/:id/folders`, `GET /courses/:id/files` | Metadata only. If the listing is refused, files referenced from module items and HTML are fetched one by one (`GET /courses/:id/files/:file_id`), and coverage says so. |
| Assignment groups | `GET /courses/:id/assignment_groups` | Names, positions, weights. |
| Assignments | `GET /courses/:id/assignments?include[]=all_dates&include[]=submission&override_assignment_dates=true`, adding `include[]=overrides` where permissions allow | The user's effective dates, base and per-set dates where visible, and the user's own submission: status, attempt, score and grade. |
| Announcements | `GET /courses/:id/discussion_topics?only_announcements=true` | Not `GET /announcements`, whose default window runs from 14 days ago to 28 days after that. |
| Discussions | `GET /courses/:id/discussion_topics` | Topic prompts and settings. Replies are not read. |
| Groups | `GET /users/self/groups`, then for each of the user's groups in a selected course `GET /groups/:id/pages?include[]=body`, `/groups/:id/folders`, `/groups/:id/files` and `/groups/:id/discussion_topics` | Only the user's own groups, with the same normalisation and coverage as course content. |
| Calendar events | `GET /calendar_events?context_codes[]=course_123&type=event&all_events=true` | Without `all_events` Canvas returns only today's events. At most 10 context codes per request. |
| One file's content | `download-file ALIAS --course ID --file ID --output PATH` | Explicit output path; streams to disk; checks the received size against the file's metadata; optional `--max-bytes`; refuses to overwrite without `--force`. Not part of `export`. |

Recommended for the first version: every row above, including the user's own scores and grades. Left out: discussion replies (other participants' posts), rosters and other users' data, conversations, quiz question content and analytics.

A fatal error (`token_rejected`, `identity_mismatch`, invalid configuration) stops the whole run. Any other failure is recorded against its resource and the run continues.

### Identity
A resource's identity is `canvas:<host>:<type>:<id>`, with IDs kept as the strings Canvas returns, for example `canvas:example.instructure.com:assignment:456`. Nested records also carry their course ID. Pages are identified by `page_id`, because the `url` slug changes when the title changes; the slug is an attribute. Module items have their own IDs and point at the resource they reference: Page items resolve from `page_url` to `page_id` through the same run's page listing, and other types through `content_id`. A resource referenced from several modules is exported once, with a sorted `referenced_by` list of module item IDs. A Page item whose slug matches no listed page is an `unresolved_reference`, not a new page. A record repeated across pages of one listing is kept once; conflicting copies mark the collection `partial`.

### Export layout and determinism
`export ALIAS --output DIR [--course ID]... [--allow-partial]` writes:

```text
DIR/
  run.json                    # start and finish times, request counts, tool version; changes every run
  index.json                  # format version, instance origin, user ID, selected course IDs
  courses/course-123/
    course.json               # every normalized record for the course
    coverage.json             # per-resource coverage, no timestamps
    course.md                 # coverage, navigation, module tree, assignments, announcements, files, gaps
    syllabus.md
    pages/page-789.md
    assignments/assignment-456.md
    announcements/announcement-111.md
    discussions/discussion-222.md
    images/file-456.png       # informational images, named by Canvas file ID
    groups/group-77/          # the user's group: group.json, coverage.json, pages/, discussions/, images/
```

Every file except `run.json` is a pure function of the normalized data and the format version, so two runs over unchanged content are byte-identical:
- Each record type has an explicit field allowlist; anything else Canvas returns is dropped. Fields that change merely because someone looked (`read_state`, `unread_count`, `subscribed`, `needs_grading_count`) and short-lived or access-bearing links (file `url`, `preview_url`, `thumbnail_url`, avatars) are excluded. Files are linked as `https://<host>/courses/123/files/456`.
- Allowlisted fields are always present, `null` when Canvas omits them.
- Arrays are sorted after retrieval, so neither response order nor page size matters: records by numeric ID; modules and module items by position, then ID; tabs by position; `all_dates` with the base entry first, then by title and ID; enumerations such as `submission_types` alphabetically. Numeric-string IDs sort by length and then text, which is numeric order without conversion.
- JSON is UTF-8 with sorted keys, two-space indentation, LF line endings and a final newline. Timestamps are Canvas's UTC values as returned.
- Bodies (pages, syllabus, assignment descriptions, announcements, discussion prompts) are stored as Markdown, which is clearer and far cheaper for an agent to read than Canvas's HTML. Each body also records the SHA-256 of the original HTML, so a change that Markdown cannot show (styling, attributes) still changes the export. `--include-html` adds the raw HTML for every body.
- A body with an informational image keeps its raw HTML automatically, beside the Markdown, so layout, captions and sizing survive. An image counts as informational unless Canvas marks it decorative (empty `alt` or `role="presentation"`, which is what the editor's "decorative" option writes) or both its declared width and height are 32 pixels or less. The rule is fixed, so reruns stay identical. Markdown keeps every image as `![alt](link)` either way.
- Informational images that are Canvas files in the same course or group are also downloaded, once each, into that course's or group's `images/` folder, named by file ID, and the Markdown links to the local copy. Decorative and icon-sized images are not downloaded. Images hosted elsewhere are listed as external-content gaps with their links, not fetched. Downloads stream to disk with no size cap, and their results appear as an `images` family in coverage. The rule relies on Canvas's decorative marking: an unmarked banner stored as a course file counts as informational and is downloaded.
- HTML converts to Markdown through a pinned, widely used converter (see the plan's runtime and dependencies), so the same input and version always give the same output. Iframes, media embeds and anything else Markdown cannot represent become explicit markers that point at the external-content gaps, never silent omissions. Dates render in the course time zone, falling back to the user's and then UTC, with the zone named once per file and the UTC value alongside. No text depends on the current time ("due in 3 days"). Per-resource files are named by ID, never by title. A change to the system time-zone database can shift rendered local times for future dates.

Publication is all-or-nothing per run. The export is assembled in a sibling temporary directory and swapped in only when no resource is `partial` or `failed`. Otherwise the previous export stays in place, the new coverage is printed, and the command exits non-zero. `--allow-partial` publishes anyway, with coverage recording what is missing. The output must be absent or a previous `use-canvas` export (recognised by its `index.json`); symlinks and other directories are refused. Remote reads are not a transaction: content can change during a run, and paging through a changing collection can skip an item without any sign.

### Coverage
`coverage.json` gives every resource family for the course exactly one status:

| Status | Meaning for a consumer |
| --- | --- |
| `complete` | Every page was retrieved. Only this status supports "absent here means absent from this user's view of Canvas". |
| `denied` | Canvas refused the listing for this user, for example for a hidden navigation area. Stable for the role, and says nothing about what exists. |
| `not_visible_to_role` | Not requested because the role cannot see it, for example overrides for a learner. Not "none". |
| `not_requested` | Excluded by options. |
| `partial` | Some records retrieved and some not; the missing identities are listed. |
| `failed` | The family could not be read: network or server error, malformed data, throttling after retries, page cap or cursor cycle. |

Each entry carries the record count, HTTP status where relevant, any fallback used (`referenced_only` for files) and notes. Pages read and request counts live in `run.json` so page-size changes do not alter deterministic coverage. Classification follows the HTTP status and Canvas's documented error bodies. `use-canvas` never infers deletion; a consumer keeps its previous data for anything not `complete`.

### Provenance, dates and external content
Every record carries its identity, API path, `html_url` (or a constructed web link) and Canvas's `created_at` and `updated_at` where provided. `index.json` records the instance origin and the user whose view this is; `run.json` records when the run started and finished, which is the retrieved or last-checked time.

Dates keep Canvas's UTC timestamps and name their kind: due (`due_at`), available from (`unlock_at`), available until (`lock_at`), page `publish_at`, announcement `posted_at` and `delayed_post_at`, module `unlock_at`. Assignment dates are the requesting user's effective dates; `all_dates` and, for course staff, overrides are recorded beside them, with `has_overrides` where Canvas provides it. The course and user time zones are recorded.

External content is listed, not retrieved: ExternalTool and ExternalUrl module items, external navigation tabs, assignments whose submission types include `external_tool` (New Quizzes among them), and iframes, `/external_tools/` links and media embeds in page, syllabus, assignment and announcement HTML. Each gap names its location, kind and link. Fetching any of them in a browser is a separately approved action.

Remote text is untrusted data. Titles and bodies are exported as content and never followed as instructions.

### Write gate
Writes follow the Trello and Excel pattern:
- Every write command previews by default. Preview only reads: identity, course state, the user's permission booleans, the current target and everything the plan depends on. It prints the plan and a `preview_hash` and sends nothing.
- `--execute` requires `--expect HASH`, as `use-excel-workbooks` does. Execution rebuilds the plan from fresh reads; any difference in the plan or its dependency reads, including a target someone else edited after the preview, refuses with no writes sent. Canvas offers no conditional request (`If-Match`) for these resources, so a change landing between that re-read and the write is still possible; readback is what detects it.
- Each request is sent once, in order, and read back before the next. Nothing is retried. A refusal before any write exits 1 and says no writes were sent. A request that may have landed (network error, malformed response, failed readback) stops the sequence with exit 3, `PARTIAL or uncertain`, the verified prior steps and their IDs, and the uncertain step. A step that creates a resource passes its ID to later steps. Nothing is transactional and there is no rollback.
- Scalar fields are read back exactly. HTML fields are compared after whitespace and attribute-order normalisation; Canvas sanitises HTML on save, so a remaining difference is reported as `verified_with_sanitizer_changes` with the difference shown, never silently accepted.
- Create commands first look for an existing resource with the same name in the same place and refuse unless `--allow-duplicate`. That makes a fresh preview after an uncertain create safe: if the earlier create landed, it now blocks the duplicate.
- Previews say which writes can notify people. Page and assignment create/edit commands send `notify_of_update` explicitly, `false` unless `--notify` is given; other endpoints do not necessarily provide notification suppression. Announcements require `--notify-course` at execute time, like the calendar skills' invitation acknowledgements.
- Writes need a matching `user_id` and a course that has not concluded. They are not limited to the courses selected for export. A permission Canvas reports as `false` refuses in preview; one it does not report is shown as unknown, and Canvas decides.
- Every command adds a record to a private history, never including bodies or tokens. A read records the command, course, resource families, record counts and coverage outcome; an export also records its output path. A write records the command, target IDs, preview hash and each step's outcome (sent, verified, uncertain) before and after sending, so an interrupted write shows which steps landed and which IDs were created, and page edits keep the revision IDs `revert-page` needs. The Microsoft Files, Excel and Planner capabilities keep similar write logs.
- The history is a directory, `canvas.history/`, with one JSON Lines file per calendar month in UTC (`2026-10.jsonl`): one JSON object per line, sorted keys, a `schema_version`, a unique record ID and a UTC time. A program reads it line by line, and `history ALIAS [--course ID] [--kind read|export|write] [--outcome uncertain] [--since DATE] [--until DATE] [--json]` returns matching records while opening only the months in range, so no agent has to read the whole history. The consumer chooses where it lives: `--history-dir PATH`, else `CANVAS_HISTORY_DIR` from the setup `.env` or environment, else an ignored, owner-only `canvas.history/` beside the skill. A history that cannot be written refuses a write before anything is sent; for a read it is a warning.
- Retention is deterministic and belongs to the tool. The current month and the two before it stay plain (`CANVAS_HISTORY_PLAIN_MONTHS`, default 3); the first command run in a new month compresses older months to `.jsonl.gz` with a fixed gzip header, so the same month always compresses to the same bytes, and `history` reads both forms. Nothing is deleted automatically. `history-prune ALIAS --before YYYY-MM` previews which whole months would go and deletes them only with `--execute`; it refuses a month holding a write whose outcome is still uncertain until `history-resolve ALIAS RECORD_ID --landed|--not-landed` records what inspection found.
- Bodies come from a file (`--body-file`): `.md` is converted to HTML (CommonMark with tables) and `.html` is sent as is. The file must be valid UTF-8 text; there is no size limit beyond Canvas's own. The preview shows the converted HTML. When an edit would replace HTML that Markdown cannot represent (iframes, embedded media, inline styles), the preview lists what would be lost and refuses unless `--accept-loss` is given or the body is supplied as `.html`. Date inputs need an explicit offset or `--tz ZONE`; naive times, nonexistent local times and ambiguous ones (the repeated hour when clocks go back) are refused. Previews show both the local and the UTC value.
- New pages, assignments and modules are unpublished unless `--published` is given.
- No delete command. Unpublishing is an ordinary edit, and page edits can be undone with `revert-page`.

### Proposed writes
One command per row, all behind the gate above. Request paths are under `/api/v1/courses/:course_id` unless they start with `/groups` or `/users`. The user accepted the twelve course-content commands and the learner-role additions for the first version on 2026-10-29.

The first twelve rows are course-content writes. Canvas's default roles give them to teachers, TAs and designers; for a learner role it refuses almost all of them, the exception being edits to course pages whose editing roles include students. The learner-role rows and the group and personal contexts below cover what an enrolled learner can do.

| Command | Request | Preview shows and checks | Readback | In v1 |
| --- | --- | --- | --- | --- |
| `create-page` | `POST /pages` | Title, body digest and diff from empty, `published`, `editing_roles`, `front_page` (and the page it would replace). Refuses an existing page with the same title. | `GET /pages/:page_id`: title, body, published, slug. | Yes |
| `edit-page` | `PUT /pages/:page_id` | Before → after for each changed field, and a body diff. Conflict check on `updated_at`, body and latest revision ID. Warns that a title change changes the slug. | The same fields, and that the latest revision advanced. | Yes |
| `revert-page` | `POST /pages/:page_id/revisions/:revision_id` | The current body against the chosen revision's body. Conflict check on the latest revision ID. | The page body equals the revision body. | Yes, as the recovery path for page edits |
| `create-assignment` | `POST /assignments` | Name, description diff, dates in local time and UTC with their order checked (`unlock_at` ≤ `due_at` ≤ `lock_at`), points, submission types (not `external_tool`), assignment group, `published`. Refuses an existing assignment with the same name. | `GET /assignments/:id`: every sent field. | Yes |
| `edit-assignment` | `PUT /assignments/:id` | Before → after, with a conflict check on `updated_at` and the edited fields. Never sends `assignment_overrides`, which replaces existing overrides; warns when base dates change on an assignment whose overrides keep their own dates. | Every sent field. | Yes |
| `create-module` | `POST /modules`, then `PUT /modules/:id` to publish | Name, position and the resulting module order, `unlock_at`, sequential progress, prerequisites (which must come earlier). Refuses an existing module with the same name. | `GET /modules/:id`: sent fields and relative order. | Yes |
| `edit-module` | `PUT /modules/:id` | Before → after, including `published`, with a conflict check on the module's current fields. | Sent fields. | Yes |
| `add-module-item` | `POST /modules/:module_id/items` | Item type (Page, Assignment, File, Discussion, Quiz, ExternalUrl or SubHeader), the referenced resource resolved and confirmed in this course, title, position and resulting order, indent. Refuses content already in that module unless `--allow-duplicate`. | `GET /modules/:module_id/items/:id`: type, reference, title, position, indent. | Yes |
| `edit-module-item` | `PUT /modules/:module_id/items/:id` | Before → after for title, position, indent, `published`, completion requirement, or a move to another module in the course. | Sent fields and `module_id`. | Yes |
| `create-announcement` | `POST /discussion_topics` with `is_announcement` | Title, message diff, immediate or delayed posting time, and that course members can be notified. Requires `--notify-course`. Refuses an existing announcement with the same title and message. | Topic fields, and that it appears in the announcements listing (Canvas can quietly create a plain discussion instead when the token lacks permission). | Yes |
| `edit-announcement` | `PUT /discussion_topics/:id` | Before → after, with a conflict check on the message's SHA-256, because topics have no `updated_at`. Refused once the announcement has posted, because whether Canvas notifies again on edit is unconfirmed. | Sent fields. | Yes, before posting only |
| `upload-file` | `POST /files`, then the returned `upload_url`, then the confirmation `Location` | Local path, size, SHA-256, content type, destination folder and any file already holding that name. A name collision refuses unless `--replace FILE_ID` (that exact file, `on_duplicate=overwrite`) or `--rename-on-conflict` (`on_duplicate=rename`). `on_duplicate` is always sent, because Canvas defaults to overwrite. The local file's digest is part of the hash. No fixed size cap: the file streams from disk, and the preview shows its size against the course's remaining quota where Canvas reports it to this user. | `GET /files/:id`: name, size, folder, content type. `--verify-content` also downloads the file and compares digests. | Yes |
| `submit-assignment` | `POST /assignments/:id/submissions`; files are first uploaded through `POST /assignments/:id/submissions/self/files` with the same three-step transport | The assignment; due and availability dates in local time and UTC; whether the submission would be late, or the assignment is locked; the accepted submission types; attempts used and allowed; the current submission; and exactly what would be submitted (a text diff against the current submission, the URL, or file names, sizes and SHA-256). States that a submission uses an attempt, is visible to the instructor and cannot be withdrawn. Conflict check on the attempt count and submission state. Refuses a locked assignment or a type it does not accept. | `GET /assignments/:id/submissions/self`: attempt advanced, type, and the body, URL or attachment names and sizes. | Yes |
| `comment-submission` | `PUT /assignments/:id/submissions/self` with `comment[text_comment]` | The comment and the latest existing comments. Refuses if the same text is already the user's latest comment. | The comment appears in `submission_comments`. | Yes |
| `reply-discussion` | `POST /discussion_topics/:topic_id/entries`, or `POST /discussion_topics/:topic_id/entries/:entry_id/replies` to answer an entry; group discussions use `/groups/:group_id/discussion_topics/…` | The topic, the entry being answered, the message (converted from Markdown), who can see it, and that Canvas may notify participants. Refuses a message the user has already posted in that topic. | The new entry's ID and message. | Yes |

Group and personal contexts: `create-page`, `edit-page` and `revert-page` also take `--group GROUP_ID` for group pages (`/groups/:group_id/pages`), and `upload-file` takes `--group GROUP_ID` (`/groups/:group_id/files`) or `--personal` (`/users/self/files`). Previews, conflict checks and readback are the same as for course content.

Upload transport: step 1 goes to the instance with the token. Step 2 posts `upload_params` unchanged, with the file as the last multipart field, to `upload_url`, which may be another host, and **without** the token. Step 3 follows the returned `Location` only when it is on the instance origin, with the token; any other location stops as uncertain. Automatic redirects are disabled throughout, so the token can never follow a redirect off the instance.

Considered and left out of the first version: assignment overrides (useful for dates, but they need section and roster reads the first version does not make), editing or deleting the user's own discussion entries, personal calendar events and planner notes, marking module items done, file renames and moves, external-tool items, quizzes, grading, messaging, and any deletion.

### Example preview
`edit-page example --course 123 --page 789 --title 'Week 1 overview' --body-file week-1.html --json` prints:

```json
{
  "mode": "preview",
  "command": "edit-page",
  "account": {"alias": "example", "origin": "https://example.instructure.com", "user_id": "1001"},
  "course": {"id": "123", "name": "Example Course", "enrollment_types": ["teacher"], "state": "available"},
  "permissions": {"<page update permission>": true},
  "target": {"type": "page", "page_id": "789", "url": "week-1", "updated_at": "2026-10-20T15:04:05Z", "latest_revision_id": "12", "html_url": "https://example.instructure.com/courses/123/pages/week-1"},
  "changes": [
    {"field": "title", "before": "Week 1", "after": "Week 1 overview"},
    {"field": "body", "before_sha256": "<64 hex>", "after_sha256": "<64 hex>", "diff": "--- before\n+++ after\n@@ -1 +1 @@\n-<p>Read chapter 1.</p>\n+<p>Read chapters 1 and 2.</p>\n"}
  ],
  "effects": ["The page URL changes with the title; links that use the old URL may stop working.", "notify_of_update=false: no update notification is requested."],
  "steps": [{"step": 1, "method": "PUT", "path": "/api/v1/courses/123/pages/789", "fields": {"wiki_page[title]": "Week 1 overview", "wiki_page[body]": "<body: 41 bytes, sha256 <64 hex>>", "wiki_page[notify_of_update]": "false"}}],
  "readback": ["GET /api/v1/courses/123/pages/789: title, body, published; latest revision advanced"],
  "warnings": [],
  "preview_hash": "<64 hex>",
  "writes_sent": 0
}
```

Without `--json` the same content prints as text, ending with `No writes sent. To apply this reviewed plan, repeat with --execute --expect <hash>`. A verified execution prints `{"mode": "executed", "preview_hash": "<64 hex>", "verified_steps": [{"step": 1, "id": "789", "readback": "verified"}], "warnings": []}`.

### To confirm in the live smoke test
The status and body Canvas returns for hidden navigation areas and disabled features; whether `include[]=overrides` is ignored or refused for roles that cannot manage assignments; whether string IDs are honoured on every endpoint used; whether the pages listing returns full bodies with `include[]=body`; the current names of the permissions checked; how Canvas sanitises page and assignment HTML; whether a renamed page's old slug still resolves; how to confirm a topic is an announcement, since the topic object has no such field; the upload confirmation's status codes on the instance; which roles can read the course file quota; whether group pages, files and discussions behave like their course counterparts; which URL forms Canvas uses for course-file images embedded in pages; the submission response for each submission type; and the practical `per_page` maximum.

## Public artifact boundary
Use generic examples such as `example.instructure.com`, `course-123`, and `assignment-456`, and synthetic fixtures only. Do not add real account identifiers, institution/course identifiers, student material, personal paths, private source links, tokens, authentication files, or private consumer-policy documents. Review documentation, fixtures, logs and the full staged diff before publication; ignore rules alone are not a publication review.

## Exit criteria
The research phase ends with a defensible selection and an implementable, bounded plan, not merely a list of repositories. Any later implementation is complete only after tests demonstrate the agreed retrieval contract, an authorized smoke test distinguishes verified coverage from unknowns, and human QA confirms setup clarity, export readability and write-preview clarity. No institution-specific compatibility is assumed in advance.
