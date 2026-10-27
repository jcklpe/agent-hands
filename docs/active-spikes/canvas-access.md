---
attention: live
---

# Canvas setup and repeatable retrieval
Opened: 2026-10-27. Slug: `canvas-access`.

## Purpose
Select a maintained Canvas integration and design a bounded implementation of `setup-canvas` and `use-canvas`. Prefer reusing a maintained MCP backed by the official Canvas API over building a new server, custom CLI, or scraper. Research and selection come first; this document does not claim that any candidate or institution-specific authentication has been tested.

[Work and verification](canvas-access.todo.md).

## Scope and ownership
- `setup-canvas` handles connection discovery, account selection, informed consent, connection verification and explicit course selection. It must not silently create credentials or expand access.
- `use-canvas` handles repeatable, read-oriented retrieval for the selected courses, stable resource identities, coverage reporting, provenance and changes since the last successful snapshot.
- The consuming agent interprets changes and decides what belongs in its private notes or task/calendar systems. This integration does not own those policies or write to downstream systems automatically.
- Initial implementation excludes submissions, grading, course edits, messaging and unattended write automation. Browser fallback is a separately approved action, not an automatic continuation after an API limitation.

## Selection before construction
Inventory maintained MCP candidates from their original repositories and documentation. Compare maintenance/release activity, license, client/runtime compatibility, installation and update burden, actual API coverage, pagination, error handling, testability, and the ability to restrict operations to the authorized scope. Read the code or tests where necessary; a tool name or README claim is not evidence of working behavior.

Use the [official Canvas API documentation](https://documentation.instructure.com/doc/api/index.html) as the capability baseline. Its current index points to the [Instructure developer portal](https://developerdocs.instructure.com). Confirm the relevant endpoint behavior there during research. If no maintained candidate is adequate, document the specific gaps and compare a small adapter to a direct API client before proposing custom infrastructure. Do not start a new MCP server by default.

## Retrieval contract to evaluate
| Area | Required behavior |
| --- | --- |
| Identity | Preserve stable course and item IDs; namespace by connection and resource type; avoid title-only identity and lossy numeric conversion. |
| Coverage | Explicitly cover or report gaps for announcements, modules and module items, pages, files and assignments. Follow pagination rather than treating the first page as complete. |
| Changes | Return a compact new/changed/removed-or-unavailable summary relative to the last successful baseline, with enough source detail for inspection. An unchanged result is distinct from an unperformed or partial check. |
| Provenance | Record source URL, resource ID/type, retrieved/last-checked time, source update time when available, and retrieval coverage. Preserve useful links without exposing connection secrets. |
| Deduplication | Recognize the same assignment, page or file referenced through multiple modules. Repeat runs must not emit duplicate items or downstream work. |
| Partial failure | Preserve the last good data. Authentication errors, rate limits, missing pages, denied items and incomplete pagination are not proof of deletion; do not advance a failed portion's successful baseline. Define when removal is actually confirmed. |
| Dates | Preserve original timestamps and timezone context. Distinguish due, availability and lock dates; verify effective dates and applicable overrides rather than assuming one course-wide deadline. |
| External content | Identify external-tool links or embedded content that cannot be retrieved through the chosen integration. Report the limitation and source link; request approval before any browser fallback. |

This is a target contract, not a claim that every endpoint exposes an incremental cursor or that one “updated since” query covers all resource types. Evaluate per-resource change detection and the cost of complete snapshots where necessary. Define a consistent snapshot/baseline boundary so partial runs cannot erase data or create false changes.

## Deliverables and decision gates
1. An evidence-linked comparison and selected approach, or an explicit no-fit result with the smallest justified alternative.
2. Separate setup and use skill contracts, including inputs, outputs, error/coverage semantics, consent boundaries and recovery behavior.
3. A bounded implementation plan with concrete files, dependency/version choices, test cases, rollback, and a stop condition. Get approval where the plan requires new access or materially expanded scope.
4. Synthetic fixtures and tests for pagination, duplicate references, changed deadlines, overrides, timezone edges, partial failures, unavailable external content, and reruns.
5. Later, an authorized read-only live smoke test and human QA. Keep live connection details and private test evidence outside the public repository; record only generic results and limitations publicly.

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
**User position:** the goal is retrieving information from Canvas; write permission would be acceptable but is not needed.

**Access is institution policy, not a Canvas constant.** On the first target instance the user's settings page offers **New Access Token**, and the institution's own help pages walk students through creating one for a third-party integration. No explicit rule on students using personal tokens with their own tools was found. Other institutions forbid it outright: [Texas A&M](https://lms.tamu.edu/support/canvas-api) limits API access to course staff, and the [University of Missouri System](https://tdx.umsystem.edu/TDClient/66/MOOnline/KB/ArticleDet?ID=2193) and [USNH](https://td.usnh.edu/TDClient/60/Portal/KB/Article/5520/Canvas-User-API-Token-Access-UNH-PSU) do not approve student tokens, citing MFA/SSO bypass and unvetted AI tools. So `setup-canvas` must check whether token creation exists, never assume it, and treat its later removal as a normal failure state. Nothing was created during this check.

**Three routes, in order of preference (agent proposal):**
1. **Official REST API with a personal token, read-only.** Deterministic, documented and paginated; the same JSON every run, which the snapshot/delta contract needs. Token stays in a private config outside the repository and can be scoped by expiry and revoked from the settings page.
2. **Official REST API through the signed-in browser session.** A same-origin `GET /api/v1/...` from a logged-in tab returns the same JSON without creating a token. Useful when tokens are unavailable or unwanted; needs explicit browser approval each run and is less suitable for unattended use.
3. **Page scraping.** Brittle against UI changes and only for content the API does not expose (some external-tool or embedded content). Last resort.

**MCP versus a small client.** The surveyed MCP's advantages are real: it already handles Link-header pagination, Canvas wire quirks (classic versus New Quizzes, external-tool assignments), prompt-injection fencing and a stream of security fixes, with a large test suite. It is the quickest way to ask ad-hoc questions of a course. It does not provide what this spike's contract centres on: deterministic snapshots, stable baselines and change summaries. An MCP is driven by an agent call by call, which is token-heavy, nondeterministic in coverage and hard to rerun identically. It is also far broader than needed (educator, grading, messaging and code-execution tools; writes on by default over stdio) and ships breaking releases every few weeks. A small read-only client over the handful of endpoints that matter (courses, modules and items, pages, files, assignments with overrides, announcements) matches the existing native capabilities here, which are deterministic CLIs with bounded exports. The hard parts it would own are pagination, throttling and partial-failure semantics, all documented by the official API.

**Revised proposal (still not a decision):** build `use-canvas` as a small read-only REST client with Markdown/JSON snapshots and deltas, behind `setup-canvas` token checks, and treat the community MCP as an optional companion for interactive questions rather than the retrieval backend. This supersedes the earlier MCP-first proposal in the candidate evaluation above.

## Public artifact boundary
Use generic examples such as `example.instructure.com`, `course-123`, and `assignment-456`, and synthetic fixtures only. Do not add real account identifiers, institution/course identifiers, student material, personal paths, private source links, tokens, authentication files, or private consumer-policy documents. Review documentation, fixtures, logs and the full staged diff before publication; ignore rules alone are not a publication review.

## Exit criteria
The research phase ends with a defensible selection and an implementable, bounded plan, not merely a list of repositories. Any later implementation is complete only after tests demonstrate the agreed retrieval contract, an authorized smoke test distinguishes verified coverage from unknowns, and human QA confirms setup clarity and useful change summaries. No institution-specific compatibility is assumed in advance.
