---
attention: live
status: ready-to-close
implementation: browser-read-save-and-submit
reviewed: 2026-11-25
---
# Workday capabilities
[Investigation and implementation handoff](workday-capabilities.todo.md). This active spike was promoted from the existing scratch pair on 2026-11-16; the original investigation below was expanded on 2026-11-02. The user requested a plan for reducing the model overhead of recurring time entry through deterministic browser execution directed by an agent, and accepts the maintenance cost and fragility of a browser route. Reusable implementation is authorized. The offline contract is implemented; since 2026-11-23 a browser reader reads complete weeks from the user's signed-in Chrome, and since 2026-11-24 a Quick Add save path under the user's chosen re-read safeguard has saved a week of approved real work live. At the user's request on 2026-11-24, submission was added as its own preview-and-approve command. Before closing, the user also approved global skill links, starting a week from an earlier one, a multi-week overview and a separate Chrome with its own profile, all built by 2026-11-25. They decided on 2026-11-24 to close without waiting for a first submission through the tool, opening a new spike if that fails.

## Implemented boundary
The [use-workday CLI](../../use-workday/SKILL.md) validates week snapshots, proposes a week from an earlier one and previews exact allocations offline. [setup-workday](../../setup-workday/SKILL.md) owns the browser: it lists several weeks, reads complete weeks, saves approved unsubmitted blocks under the re-read safeguard, submits approved weeks and settles uncertain operations. The account file holds the user's choice between their everyday Chrome and a separate, windowless one that keeps their sign-in until Workday or the identity provider ends it.

Reads, the overview and saves are proven live on real work; submission is proven live only as a preview, and reconciliation, sign-out partway through a session and Workday's overlap refusal only offline. Saving and submission have not run through the separate Chrome. The [transport reference](../../setup-workday/references/transport.md) owns the current limits.

## Transport proof and dispositions — 2026-11-23
The [transport reference](../../setup-workday/references/transport.md#interface-inventory-and-save-guarantees--2026-11-23) records the rechecked interfaces. In short: Time Tracking REST v7, Agent-Ready MCP and the new beta Sana from Workday connector all need a client or agent registered and granted by the tenant's administrators, and the selected account had no such grant and no self-service registration. The REST block read omits incomplete blocks, time off and overtime requests, so it is not a complete week on its own. No documented interface offers a revision precondition on time-block writes; the REST service refuses in/out times that overlap existing entries, which guards one slot, not the week. The browser route is unchanged since 2026-11-21: it needs the user's current profile and tab selection and native connection approval, and the UI has no save precondition either. No read proof was possible this session without those, and no Workday data was retrieved.

Proposed dispositions, for the user's decision:

1. **Request access (recommended).** The user asks the employer's Workday integration or security team whether the account can be granted a REST API client with the Time Block domain and Time Tracking scope, or the Workday MCP or Sana connector, for self-service time entry. No code changes until a grant exists.
2. **Read-only browser proof (optional).** With the user's current selection of Chrome profile and Workday timesheet tab, Chrome's native remote-debugging setting enabled by the user, and the user's approval of the connection prompt, build and run a read-only probe from the standalone runtime that binds tenant, worker and one complete week. Browser writes stay blocked.
3. **Save-guarantee decision, before any write route.** Keep the revision precondition, which leaves writes blocked on every documented route, or explicitly redefine the guarantee for in/out blocks as the service's slot-conflict refusal plus authoritative readback and local single-writer locking. The second changes the current guard and would need live proof on real, separately authorized work.
4. **Keep the spike active and transport-blocked** until one of these changes the evidence. Offline tests do not justify closing it.

**User direction, 2026-11-23:** API or MCP access is unlikely to be granted soon, so the browser route is the practical path.

**User decision, 2026-11-23:** saves use the re-read safeguard rather than staying blocked. After the residual risk was explained (an edit to the same week in another tab at the moment of saving is detected by the readback afterwards, not prevented), the user chose: one writer at a time, a fresh full read before each block and a last check of the calendar, Workday's own refusal of overlapping times, and a full read after each save. The account file records the choice, and the engine accepts the weaker guard only with it.

## Goal and scope
Give an agent a small set of predictable operations for reading a timesheet, previewing exact entries, saving drafts, and submitting an explicitly approved plan. The agent handles intent, missing information, approvals and exceptions; deterministic code handles the known form sequence, calculations and readback. Avoid making the model inspect a full page and choose another field after every input.

Explore existing supported APIs, maintained MCP servers, and other integrations before choosing a custom CLI or browser adapter. Prefer an authorized supported interface when it covers the required operations. Investigate a supported persistent-browser route early: reusing a user's existing signed-in session is the preferred browser experience, but this has not been established for a standalone Agent Hands process.

Organization-specific worklogging conventions, tenant/account details, real schedules, submission history and private source evidence belong in the consuming workspace. This reusable capability must not depend on a personal vault, an employer, an institution, or another unrelated provider.

## Decisions and unresolved choices
**User direction:** pursue a reusable tool rather than repeating a long model-directed sequence of clicks. Prefer reuse of an existing signed-in browser session, and evaluate a browser solution despite accepted fragility. Keep draft saving and final submission separate. These are requirements for the investigation, not evidence that a particular attachment or execution mechanism works.

**Proposed structure:** optional `setup-workday` and `use-workday` capabilities consistent with the [setup/use contracts](../archive/setup-use-contracts.md). Setup owns selected software, account/tenant binding, supported authorization or browser connection, reconnect and recovery. Use owns the bounded operations below. A thin CLI or MCP facade should share the same operation logic; MCP alone does not imply an official Workday API or smaller model use.

**Open:** supported transport, browser runtime availability outside an interactive agent REPL, session ownership, platform support, required permissions, layout variation, and the minimum scopes for time entry. Do not treat an empty authorized-client list or missing search result as proof that an account or tenant has no integration entitlement. Confirm official interface prerequisites against current vendor documentation before adopting claims about licensing, administrative setup or availability.

## Transport discovery and first proof
| Candidate | First evidence required | Selection condition |
| --- | --- | --- |
| Supported Workday API or official MCP | Current vendor contract, a tenant-enabled and explicitly authorized client, permitted time-tracking operations/scopes, and a bounded read | Prefer it when authorized and sufficient; preserve preview and submission semantics. |
| Existing maintained integration | Source/version, operation bounds, session/auth model, dependency and maintenance review, and a synthetic or authorized read | Reuse when it covers the gap without adding unrelated access. |
| Supported persistent-browser adapter | Documented host/client interface, explicit browser/profile/tab binding, account/tenant verification, and repeatable read-only attachment | Choose only after proving attachment and execution from the intended Agent Hands host. |
| Dedicated persistent profile | Supported profile lifecycle and native sign-in, reconnect and cancellation | Evaluate only if existing-session reuse is unavailable and the user accepts the different session. |

An interactive browser-control session has demonstrated the workflow mechanics. It has not demonstrated that plain Playwright, a new process, or a public CLI can attach to that session. Do not infer attachment from an open Chrome window, extract cookies, read private browser databases, discover private debugging endpoints, or change debugging/security settings to make the proof succeed. An unavailable supported route is a concrete blocker to report, not permission to bypass it.

First deliverable when implementation is requested: a read-only proof from the intended runtime that binds one authorized tenant/account/week, reuses the intended session where supported, and returns a compact normalized timesheet. No writes or credential setup are necessary to validate offline parsing and contracts.

## Proposed operation contract
This table preserves the original proposed live surface. The implemented offline subset and exact command behavior are documented in [use-workday](../../use-workday/SKILL.md); `submit-approved` became `submit-preview` and `submit` in setup-workday.

| Operation | Inputs | Result and boundary |
| --- | --- | --- |
| `read-timesheet` | Configured non-secret account alias, exact worker, ISO week start and timezone | Normalized dates, entries, totals, classifications, submission state and a precondition fingerprint. No check-in/out action. |
| `preview` | Structured exact-date entries plus the current-state fingerprint | Local diff of additions/conflicts, daily/weekly totals, pay-period crossings and a plan fingerprint; no remote write. Missing actual hours or ambiguous dates fail. |
| `save-draft` | Reviewed plan and unchanged target/preconditions | Save only planned entries, then re-read totals, classification and explicit draft/not-submitted state. Never submit as a side effect. |
| `submit-approved` | Fresh readback, exact approved plan fingerprint and the user's explicit submission authorization | Submit only that range and those hours, with the expected standard certification; verify submitted/sent-for-approval and the next step. Never report manager approval without evidence. |

Use a versioned JSON input schema: tenant/account alias, worker binding, week start, timezone, and entries with exact date, local in/out time, time type, relevant worktags and explicitly supplied breaks. Reject overlaps, missing fields, unknown classifications, unsupported overnight/DST cases and inconsistent totals rather than guessing. A recurring schedule or a prior week is a proposal source only until the user confirms the intended dates and allocation. Preview the entire affected range, including days in a different payroll period.

Return allowlisted structured fields such as operation, target alias, week, status, totals, changed/unchanged/conflicting dates, plan fingerprint, next approval step and bounded error code. Return the necessary time-entry data for review, with account identifiers minimized. Do not return cookies, tokens, credentials, a whole page tree, unrelated personnel data or raw authentication diagnostics. Keep any screenshots or detailed evidence private and scoped to the operation.

## Correctness and recovery
- Preflight exact tenant, worker, week, timezone and current entry/submission state before every mutation. Serialize work against a target/week and stop if the user or another process changes it.
- Skip an existing exact match; stop on a conflicting or submitted/approved entry. Never overwrite or duplicate entries to reach a requested total. Recalculate totals from the individual blocks and compare the service's calculation and classification.
- Bind execution to the reviewed input and fresh service-state fingerprints. A changed total, pay-period range, certification, classification, account or layout invalidates the plan. A materially unexpected certification requires renewed review.
- Treat multi-entry saves as potentially partial. Record which entries were observed saved and which remain unknown. After timeout or a lost response, re-read the target before retrying; a local run ID is not a service idempotency guarantee.
- Separate draft persistence from submission. A save that would submit or attest is outside `save-draft`. A repeated submission request on already-submitted matching data reports the existing state without clicking Submit again.
- Fail closed on unknown UI, ambiguous controls, stale bindings, MFA/session expiry, validation warnings, permission denial or unavailable readback. Return the exact stage, target, known completed effects, pending/denied/uncertain outcome and supported next action. Do not silently switch transport or expand access.
- Recovery means reconcile and resume exact missing work under authorization. Do not auto-delete saved time, revoke access, alter approved time or change payroll classifications as rollback.

## Validation and efficiency measurement
Use synthetic fixtures for empty and populated weeks, exact duplicates, conflicting entries, mixed statuses, partial saves, lost submit responses, session expiry, account/week mismatch, changed certification, changed markup, overnight/DST boundaries and pay-period crossings. Demonstrate the complete read/preview/draft/submission state machine against a fake transport before any live write. Real writes require exact target/data authorization and their own readback; fixture success is not live account or cross-platform proof.

Measure equivalent workflows in separate phases: setup/reconnect, read and preview, draft entry, approved submission, and unrelated capability research. For each record runtime/version/model, model calls, tool calls, UI actions, retries, model-visible result bytes, available provider-reported input/cached-input/output/reasoning tokens, wall time and correctness. Keep unavailable metrics explicitly null. Do not access restricted session logs, infer tokens from elapsed time, or count character estimates as billed tokens.

Compare the existing model-directed browser loop with deterministic execution on the same synthetic workload and separately authorized live target. Batch predictable UI actions and expose compact readback; retain checkpoints at target selection, draft review, final authorization and uncertain effects. The goal is fewer model round trips and less page content in context without losing those checks. No percentage or cost saving is established yet.

If API-equivalent costing is useful and token usage is available, use the actual model and service tier's current [API rates](https://developers.openai.com/api/docs/pricing): `(uncached_input * input_rate + cached_input * cached_rate + output * output_rate) / 1_000_000`, plus applicable tool charges. Do not double-count cached input or reasoning already included in output. [OpenAI's reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning) describes output-token usage; [ChatGPT usage controls](https://learn.chatgpt.com/docs/enterprise/usage-limits) are distinct from API billing. An API-equivalent calculation is not a ChatGPT subscription charge or quota measurement.

## Handoff boundary
The maintained guidance is in the two skills and the transport reference; this pair keeps the reasoning and history. Nothing here authorizes recurring time entry: every save and submission needs approval of its exact plan for real work.
