---
attention: live
---

# CLI Review Feedback
Opened: 2026-10-25. Slug: `cli-review-feedback`.

The reviewed CLI routes were useful: Drive reads, multi-tab Docs reads, comment listing, and GitHub reads succeeded during an authorized review on 2026-10-25. The strongest improvement candidates are a way to continue bounded Drive discovery and more explicit treatment of Docs references that are not ordinary text links. The observed runtime failures do not establish a refactor regression.

This spike records feedback and proposed acceptance criteria. The user requested documentation, not implementation. Proposals below are agent recommendations, not adopted requirements or authorization to change tools. See the [task record](cli-review-feedback.todo.md) for evidence checks and remaining work.

## Scope and boundaries
Keep this work in Agent Hands, which owns the portable capabilities behind the compatibility commands. Preserve bounded requests, provider isolation, account/target selection, and existing write guards. Successful reads establish that the exercised routes worked for that review; they do not establish write access, complete discovery, fresh-machine setup, or all-platform behavior.

No code fixes, tool installation, credential/configuration changes, remote writes, browser use, broad audit, or parent-repository pin updates belong to this documentation task. Do not copy interview content, participant identities, private document IDs, account aliases, exports, or private conversation links into this public repository. Command examples below use placeholders.

## Evidence and interpretation
The live observations in this section were supplied by the completed review; they were not replayed while writing the spike. Local checks inspected current skill instructions, entrypoint help, and only the relevant implementation paths.

| Observation | Interpretation and confidence |
| --- | --- |
| Drive, multi-tab Docs, comment listing, and GitHub reads worked. | Positive evidence for those exercised read paths. Preserve their useful behavior when improving discovery/rendering. |
| A `lifeos drive search ACCOUNT QUERY --json` attempt failed with `Failed to initialize cache at ~/.cache/uv` and `Operation not permitted`; the unchanged command succeeded with approved execution outside the task sandbox. | Execution-environment friction. The successful unchanged retry is evidence against treating this incident as a demonstrated refactor regression. |
| A temporary `GOOGLE_PYTHON` override selected system Python 3.9.6, below the documented 3.11 minimum, then encountered a DNS error. The override was abandoned. | This did not establish a supported-runtime failure or a code regression. The version mismatch and DNS failure are separate facts; neither establishes the cause of the other. |
| Drive search returned a bounded result page and a continuation token, but offered no way to submit that token. A narrower folder listing recovered the needed discovery. | Confirmed interface limitation. Folder narrowing is a useful workaround, but folder listing is itself bounded and is not proof of complete inventory. |
| `lifeos docs read ACCOUNT DOC --show-links` left resource references blank. | Suspected smart-chip/non-text rendering limitation. Code confirms that the reader ignores non-`textRun` paragraph elements; the exact representation of the missing live references was not established. |

## Drive: make bounded discovery continuable
The [Drive skill](../../skills/use-google-drive/SKILL.md) already states the limitation accurately. The [entrypoint help](../../skills/use-google-drive/scripts/drive) exposes only `--json` for search/list. In [operations.sh](../../skills/use-google-drive/scripts/operations.sh), `_drive_search` and `_drive_list` accept no continuation option and issue a single request with a page size, defaulting to 20 via `_drive_page_size`. Both request `nextPageToken`; JSON preserves it and human output warns when it exists. This is incomplete retrieval with an honest bound, not a failure to warn.

Proposal: add an explicit caller-supplied page token to search and list while retaining one page per invocation. An illustrative `--page-token TOKEN` spelling is proposed, not available today. Do not silently turn discovery into an unbounded crawl or increase account-wide access. Repeated narrower queries can find useful files, but should not be described as enumerating all matches.

Proposed acceptance criteria:
- A synthetic two-page search and a synthetic two-page folder listing can retrieve their second page using the returned token; the default invocation still performs only one bounded request.
- Continuation preserves the account, query or folder, page size, and shared-drive request flags. Help explains that the caller must retain the original request context.
- Tokens reach the fixed Drive endpoint as encoded parameter data. Unknown options remain errors; no generic API route is introduced.
- Human output still states when more results exist; JSON preserves the continuation token and the established response shape. An empty page with a token is not described as the end of results.
- An invalid/expired token or failed continuation reports failure without presenting the collection as complete. Offline fixtures cover these cases; any later authorized live read is reported separately from fixture results.
- Update command help and the owning skill together if this proposal is implemented. Keep compatibility dispatch behavior aligned without importing personal routing into Agent Hands.

## Docs: make missing reference content visible
In [docs.py](../../skills/use-google-docs/scripts/docs.py), `get_document` requests `includeTabsContent=true`, `walk_tabs` recurses into child tabs, and `selected_tabs` supports explicit tab selection. `structural_text` and `structural_text_with_spans` extract paragraph text only from `textRun`; `structural_links` extracts only `textRun.textStyle.link.url`. Those helpers traverse tables and tables of contents, but other paragraph-element types contribute no text or links. `command_read` prints the resulting tab text and, with `--show-links`, the collected ordinary URL links.

This is direct evidence of an omission path, but not proof that the reviewed references were a particular chip type or that their target URLs were present in the API response. The [Docs skill](../../skills/use-google-docs/SKILL.md) already warns that reads flatten structure. The missing piece is a clearer fidelity signal and, where supported by the actual response, useful reference rendering.

Proposal: inspect a minimal synthetic fixture or separately authorized, sanitized response to identify relevant non-text reference shapes. Render labels/targets where the API supplies them; otherwise surface an explicit unsupported or unavailable reference marker rather than an unexplained blank. Do not invent a target URL from visible text or fetch linked resources automatically.

Proposed acceptance criteria:
- Establish the actual supported reference shape before claiming smart-chip coverage. Tests distinguish ordinary linked text, supported non-text references, and unknown or missing reference data.
- Supported labels remain in reading order; `--show-links` exposes supplied targets in the correct tab context. Unavailable targets and unsupported elements are distinguishable from genuinely empty content.
- Plain text, ordinary links, selected tabs, child tabs, tables, and tables of contents retain their current readable behavior. Fixtures cover each affected traversal path without private source material.
- Display improvements preserve the mutation model. `document_tabs` is shared with replacement/matching logic, and `structural_text_with_spans` supplies UTF-16 positions; adding display labels must not create synthetic replaceable text, shift API ranges, bridge omitted elements unsafely, or weaken revision and contiguous-range guards.
- Update read help/skill fidelity notes to describe supported content and remaining omissions. Do not imply visual/layout parity or that Markdown body replacement preserves native chips.

## Runtime: distinguish environment friction from service failure
The [Google provider helper](../../skills/authorize-google/scripts/client.sh), `_google_python`, invokes an explicit `GOOGLE_PYTHON` when set, otherwise uses `uv run --project`. The [provider instructions](../../skills/authorize-google/SKILL.md), [setup guide](../../skills/setup-google-services/SKILL.md), and Python manifests require Python 3.11+. These facts explain why cache access and runtime selection matter; they do not prove a new runtime defect.

Proposal: consider concise diagnostic guidance that separates cache/filesystem denial, unsupported runtime selection, DNS/network failure, and provider authorization failure. For sandbox denials, the agent should follow its execution environment's approval mechanism for the exact authorized operation, not treat tool installation or a successful read elsewhere as blanket permission.

Proposed acceptance criteria:
- Guidance records the failed layer and actual runtime version, preserves the original error, and avoids reporting service or refactor failure before the evidence supports it.
- Any suggested Python override is checked against the documented minimum. Do not recommend the abandoned 3.9.6 workaround, automatic downgrade, credential changes, or broad filesystem permission changes.
- Diagnostic examples contain no tokens, account configuration, or private document data. Any supported-runtime or alternate-environment retry keeps the requested operation unchanged and follows the applicable authorization rules.

## Open decisions
Choose which improvement to scope first before implementation. Explicit Drive continuation has the clearest confirmed interface gap. Docs reference rendering needs a representative response shape and a design that separates presentation from mutation ranges. Runtime guidance is a possible usability improvement, not an assertion that the reviewed migration broke the tools.
