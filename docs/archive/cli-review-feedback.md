---
attention: historical
---

# CLI Review Feedback
Opened: 2026-10-25. Closed: 2026-11-18. Slug: `cli-review-feedback`.

Historical record of the completed spike. Current behavior and limits belong to the [Docs skill](../../use-google-docs/SKILL.md), [Drive skill](../../use-google-drive/SKILL.md) and [Google provider diagnostics](../../setup-google-services/references/account-access.md#runtime-diagnostics).

The reviewed CLI routes were useful: Drive reads, multi-tab Docs reads, comment listing, and GitHub reads succeeded during an authorized review on 2026-10-25. The strongest improvement candidates are a way to continue bounded Drive discovery and more explicit treatment of Docs references that are not ordinary text links. The observed runtime failures do not establish a refactor regression.

This spike records feedback and the selected Drive pagination implementation. Explicit search/list continuation was authorized on 2026-11-17 and is implemented; Docs reference rendering and runtime diagnostics were selected on 2026-11-17. Both are implemented and verified; closure and the complete archival wording were approved on 2026-11-18. See the [task record](cli-review-feedback.todo.md) for verification evidence and acceptance limits.

## Scope and boundaries
Keep this work in Agent Hands, which owns the portable capabilities behind the compatibility commands. Preserve bounded requests, provider isolation, account/target selection, and existing write guards. Successful reads establish that the exercised routes worked for that review; they do not establish write access, complete discovery, fresh-machine setup, or all-platform behavior.

Selected implementation scope includes bounded Drive search/list continuation, Docs reference rendering, runtime diagnostics, their synthetic checks and maintained guidance. Tool installation, credential/configuration changes, remote writes, browser use, broad audit and parent-repository pin updates remain outside scope. Do not copy interview content, participant identities, private document IDs, account aliases, exports, or private conversation links into this public repository. Command examples below use placeholders.

## Evidence and interpretation
The live observations in this section were supplied by the completed review; they were not replayed while writing the spike. Local checks inspected current skill instructions, entrypoint help, and only the relevant implementation paths.

| Observation | Interpretation and confidence |
| --- | --- |
| Drive, multi-tab Docs, comment listing, and GitHub reads worked. | Positive evidence for those exercised read paths. Preserve their useful behavior when improving discovery/rendering. |
| A `lifeos drive search ACCOUNT QUERY --json` attempt failed with `Failed to initialize cache at ~/.cache/uv` and `Operation not permitted`; the unchanged command succeeded with approved execution outside the task sandbox. | Execution-environment friction. The successful unchanged retry is evidence against treating this incident as a demonstrated refactor regression. |
| A temporary `GOOGLE_PYTHON` override selected system Python 3.9.6, below the documented 3.11 minimum, then encountered a DNS error. The override was abandoned. | This did not establish a supported-runtime failure or a code regression. The version mismatch and DNS failure are separate facts; neither establishes the cause of the other. |
| Drive search returned a bounded result page and a continuation token, but offered no way to submit that token. A narrower folder listing recovered the needed discovery. | Confirmed interface limitation. Folder narrowing is a useful workaround, but folder listing is itself bounded and is not proof of complete inventory. |
| `lifeos docs read ACCOUNT DOC --show-links` left resource references blank. | Suspected smart-chip/non-text rendering limitation. Code confirms that the reader ignores non-`textRun` paragraph elements; the exact representation of the missing live references was not established. |

## Drive: bounded discovery continuation
The [Drive skill](../../use-google-drive/SKILL.md) and [entrypoint help](../../use-google-drive/scripts/drive) expose `--page-token TOKEN` for search and list. In [operations.sh](../../use-google-drive/scripts/operations.sh), each invocation performs one request, retaining the explicit account, escaped query/folder predicate, configured page size and shared-drive flags. The caller supplies the exact opaque `nextPageToken` from the preceding response and retains the original request context.

The token is passed through curl's encoded parameter mechanism to the fixed files endpoint. Human output warns about further pages and incomplete search; JSON retains the response fields. Empty pages with a token remain continuable. Transport failures, error envelopes and malformed responses exit nonzero without publishing a verified page or restarting automatically. This supplies bounded continuation, not a stable snapshot or automatic crawl. The macOS live check confirmed continuation for both commands; full-text search pages overlapped by one file ID. Preserve the raw page and require combining callers to deduplicate by ID. Drive rejected explicit sorting for that full-text query, so the CLI retains its relevance ordering. The task record separates this live evidence from synthetic checks.

Implemented acceptance criteria:
- A synthetic two-page search and a synthetic two-page folder listing can retrieve their second page using the returned token; the default invocation still performs only one bounded request.
- Continuation preserves the account, query or folder, page size, and shared-drive request flags. Help explains that the caller must retain the original request context.
- Tokens reach the fixed Drive endpoint as encoded parameter data. Unknown options remain errors; no generic API route is introduced.
- Human output still states when more results exist; JSON preserves the continuation token and the established response shape. An empty page with a token is not described as the end of results.
- An invalid/expired token or failed continuation reports failure without presenting the collection as complete. Offline fixtures cover these cases; any later authorized live read is reported separately from fixture results.
- Command help and the owning skill document continuation together; examples use the native entrypoint without personal routing.

## Docs: make missing reference content visible
The [Docs reader](../../use-google-docs/scripts/docs.py) has a separate display traversal, leaving the mutation text-run/UTF-16 model intact. It renders API-supplied rich-link titles, person names or emails, date display text and dropdown values. `--show-links` lists supplied URIs, emails and internal heading/bookmark/tab/footnote identities per selected tab. It traverses tables, tables of contents and nested tabs. Missing properties produce unavailable markers; unknown elements and unrendered footnote content remain visible. It never infers a URL or retrieves a linked resource.

The response shapes come from Google's current [ParagraphElement](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#ParagraphElement), [RichLink](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#RichLink), [Person](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#Person) and [Link](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#Link) schemas. Synthetic fixtures establish supported rendering, not the identity of the originally omitted live references. Date/dropdown labels are used only when supplied; images, equations, footnote bodies, headers/footers and visual layout remain outside this reader's fidelity claim.

Display labels never enter replacement matching. The exact-range resolver also refuses noncontiguous API spans for plain, Markdown and suggestion replacements, preventing a flattened match from crossing an omitted chip or table boundary. Existing revision checks remain in place.

Implemented acceptance criteria:
- Establish the actual supported reference shape before claiming smart-chip coverage. Tests distinguish ordinary linked text, supported non-text references, and unknown or missing reference data.
- Supported labels remain in reading order; `--show-links` exposes supplied targets in the correct tab context. Unavailable targets and unsupported elements are distinguishable from genuinely empty content.
- Plain text, ordinary links, selected tabs, child tabs, tables, and tables of contents retain their current readable behavior. Fixtures cover each affected traversal path without private source material.
- Display improvements preserve the mutation model. `document_tabs` is shared with replacement/matching logic, and `structural_text_with_spans` supplies UTF-16 positions; adding display labels must not create synthetic replaceable text, shift API ranges, bridge omitted elements unsafely, or weaken revision and contiguous-range guards.
- Update read help/skill fidelity notes to describe supported content and remaining omissions. Do not imply visual/layout parity or that Markdown body replacement preserves native chips.

## Runtime: distinguish environment friction from service failure
The [Google provider helper](../../setup-google-services/scripts/client.sh) now checks an explicit `GOOGLE_PYTHON` against the documented 3.11 minimum before dispatching its Python operation. The credential-free `authorize runtime` command reports actual version and runner; it does not read account JSON, inspect tokens or call a Google service. Existing `uv run --project` selection is retained. Errors, stdout and failure status from the selected operation are preserved without automatic fallback or retry.

The [provider diagnostics](../../setup-google-services/references/account-access.md#runtime-diagnostics) distinguish unsupported/missing interpreters, cache/filesystem denial, DNS/transport failures, actual provider authorization/resource/policy/quota responses and command/validation errors. They retain the original error, require actual version evidence, preserve the selected operation and approval boundary, and avoid grant expansion, automatic reauthorization, cache deletion or broad permission changes. These are diagnoses and supported-runtime guards, not evidence that the original incidents were refactor regressions.

Implemented acceptance criteria:
- Guidance records the failed layer and actual runtime version, preserves the original error, and avoids reporting service or refactor failure before the evidence supports it.
- Any suggested Python override is checked against the documented minimum. Do not recommend the abandoned 3.9.6 workaround, automatic downgrade, credential changes, or broad filesystem permission changes.
- Diagnostic examples contain no tokens, account configuration, or private document data. Any supported-runtime or alternate-environment retry keeps the requested operation unchanged and follows the applicable authorization rules.

## Completion and limits
Drive continuation is implemented and verified with nine synthetic tests spanning both commands; the existing Drive operation regression program also passes. The bounded macOS live check confirmed both continuation routes and recorded overlapping full-text search results. Docs reference rendering is verified against synthetic fixtures matching the current API schemas, with separate read and mutation models. Runtime reporting and the explicit-interpreter minimum guard pass eight synthetic runtime tests, three OAuth tests and actual supported/unsupported interpreter checks. No required implementation remains. Fresh-machine/platform onboarding and the shape of the originally omitted live reference remain unproved and are outside this bounded acceptance.

## Completion — 2026-11-18
The user kept this spike open and selected Drive pagination for implementation. Drive pagination, Docs reference rendering and runtime diagnostics are complete. The user approved closure and the complete archival wording on 2026-11-18; the full pair is archived. Maintained command behavior belongs to [Google Drive](../../use-google-drive/SKILL.md) and [Google Docs](../../use-google-docs/SKILL.md). The [closure review](spike-closure-review.todo.md) tracks this closure alongside the other reviewed scopes.
