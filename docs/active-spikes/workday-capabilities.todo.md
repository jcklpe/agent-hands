---
attention: live
status: saves-built
implementation: browser-read-and-save
reviewed: 2026-11-24
---
# Workday capabilities — investigation and implementation handoff
[Concept, decisions and boundaries](workday-capabilities.md). Promoted from scratch on 2026-11-16 for authorized reusable CLI implementation. Actual time entry remains outside this implementation scope; the separately authorized read-only browser probe is recorded below.

## Next implementation handoff - 2026-11-23
Workday follows the Penpot scope. The immediate deliverable is a transport decision supported by an exact read-only proof, not more fake executor features. Read `setup-workday/SKILL.md`, `use-workday/SKILL.md` and `setup-workday/references/transport.md` first; the existing thirty-test offline implementation remains useful and is not a production adapter.

1. Check whether the selected account has an approved API/MCP client. Otherwise prove the documented existing-session route against an explicitly selected Workday tab/profile, preserving normal tabs and native connection consent. Prior bounded probe approval is not a permanent browser-wide grant. Do not copy cookies, adopt another provider's profile or bypass MFA.
2. Bind tenant and worker, then retrieve a complete authorized week with timezone, statuses, classifications and totals. A heading read or an attached Chrome session alone is insufficient. Keep private target data and screenshots out of public fixtures and commits.
3. Only after access works, prove the required draft-only conditional-save semantics and a supported settled-outcome reconciliation route. Preserve uncertain writes; do not add retries or weaken the existing revision guard to make a demonstration pass. New tool-owned state must follow the maintained common private-root contract, with all callers sharing one journal/lock and existing explicit selections preserved.
4. Implement only the supported bounded adapter, with synthetic interruption/conflict/session tests first. Live payroll writes require separately approved actual work; no disposable time entries or submission tests. Submission remains a separate reviewed scope.
5. If access or save guarantees cannot be established, report the exact blocker and a proposed bounded disposition for human review. Do not call the end-to-end tool working or close the spike merely because the offline tests pass. If the selected scope does pass, prepare a plain-language closure summary and identify the remaining platform limits.

## Current implementation checkpoint — 2026-11-16
- Added `setup-workday` and `use-workday`, the offline read/preview CLI, guarded draft executor, durable private Unix journal and 30 synthetic tests. No production transport, live read/write, reconciliation command, submission command, installation or browser access is implemented or claimed.
- The existing scope below remains the broader acceptance backlog; partial implementation does not mark whole live-runtime items done.
- [Transport evidence, exact blockers and next gates](../../setup-workday/references/transport.md); [contract and commands](../../use-workday/SKILL.md).
- Validation: `python3 -m unittest discover -s use-workday/tests -v` passes on macOS/Python 3.9. CLI errors emit no stdout payload. Full selected source/document review, workflow TOML resolution, relative links, private-path ignores and unchanged child pin checked. Other platforms, fresh client discovery, live access and UI behavior are unverified.

## Transport investigation — 2026-11-20
- Retrieved the official indexed Markdown pages for external-agent MCP setup, tool discovery and REST authentication. MCP requires Extend Professional access, OAuth, registered-agent configuration and appropriate security domains; subscription/feature prerequisites are documented. Public catalog time-tracking tools do not prove tenant access or conditional draft persistence.
- No Workday connector is available in the current tool inventory, and no approved tenant client/agent registration has been established. The next concrete gate is an authorized read-only client and worker/week proof. Existing browser attachment and guarded save requirements remain unresolved; no credentials were extracted, grants changed or payroll data written.
- Updated the maintained transport reference with primary sources and the exact distinction between public interface availability, tenant authorization and save semantics. The first backlog item remains open for endpoint/concurrency coverage and a proven reuse/custom decision.

## Browser attachment investigation — 2026-11-21
- Verified official Chrome M144 native connection approval and current Playwright channel attachment/detachment documentation. The installed Chrome 157 and Playwright 1.65.1 support the documented surface; no runtime installation or dependency change was made.
- An isolated headless synthetic attach/read/disconnect check preserved the owner's original page and closed only the disposable browser on fixture cleanup. It did not use normal-profile data or credentials.
- The user explicitly authorized a read-only existing-session probe. After the initial connection failure, two attempts attached and disconnected but found no matching Workday tab; a bounded diagnostic retry could not establish the native connection. The next gate is exact target/profile selection and native approval-state clarification. No Workday headings or timesheet data were retrieved, and no timesheet write, cookie/profile export, automatic security-setting change or normal-tab mutation was performed. Complete worker/week retrieval and production save semantics remain unproved.

## Saving under the re-read safeguard — 2026-11-24
- The user chose the re-read safeguard (decision recorded in the concept doc). The engine now accepts a transport declaring `save_safeguard = "reread"` only with `allow_reread`, which the browser `save` command passes only when the account file records the choice. A transport that stops before sending raises `NotDispatched`, which clears the intent and stops cleanly; intents carry the time they were written. The existing atomic path is unchanged.
- Inspected Workday's entry route read-only, with each form cancelled or discarded and the week confirmed unchanged: Quick Add sets worker, week dates and time type, then In, Out, Out reason and a box per weekday. The time-type list offers a few time-entry codes and an Absence category; saving supports Hours Worked only. Cancel after touching a field raises a Discard Changes prompt.
- Built the browser `create_draft` on Quick Add with checks at each step and a cancel-and-discard on any problem before OK, a `save` command that refuses unsupported entries before connecting, and `reconcile`, which settles an uncertain save from a fresh read after a ten-minute settling time. Status now comes from each block's label, mapping Approved, Not Submitted and Submitted; the revision is a fingerprint of the calendar, and two live reads of an unchanged week produced identical snapshots.
- Tests: 10 save-path tests against scripted page states, 17 reader tests, 5 client tests and 33 engine tests pass on Python 3.14 and 3.9. A live read after the changes still matched.
- Not yet: any live save. It needs real hours the user wants entered; no disposable payroll entries. The Not Submitted label, the In/Out input handling and Workday's overlap refusal are confirmed only by that first save.

## Browser reader — 2026-11-23
- Built `setup-workday/scripts/workday_browser.py` and `chrome_session.py`: a standard-library DevTools client and a reader that produces the v1 snapshot from the Enter My Time calendar, Review Time by Week and each block's details, cross-checked and refusing on any disagreement. Playwright 1.63 was tried first and dropped: its attach to the user's everyday Chrome 157 timed out after the user clicked Allow, while a minimal connection was approved within a second. The reader opens, uses and closes only its own background tab and never attaches to the user's tabs.
- Live, with the user's approval at each connection: an approved week read completely (blocks, classification, the pay-period boundary and totals) and validated through `use-workday`; an empty week read as empty within one period. Two bugs found live and fixed with regression tests: the Details control is the magnifier, not the first element marked as a button, and a background tab ran the period marker's title and dates together, which had silently produced one pay period for the week. Workday repeats details labels, and an empty week's review drops the In, Out and Out Reason columns.
- 20 synthetic tests (15 reader, 5 client against a loopback stand-in) pass on Python 3.14 and 3.9; the 30 `use-workday` tests pass with an updated pointer from its no-live-read message to the reader.
- Not yet: saving, the entry dialog and the permitted time-type list (empty weeks use the account's confirmed list), statuses other than approved, concurrent-user and cancellation behaviour, Linux.

## Transport proof — 2026-11-23
- Rechecked public vendor sources: the Time Tracking REST v7 specification dated 2026-11-21, the Agent-Ready MCP authentication guide, the developer index and Workday's public Sana connector source. Claude's connector directory now lists the beta Sana from Workday connector; it is administrator-enabled, tenant-specific and agent-mediated. Findings are in the [transport reference](../../setup-workday/references/transport.md#interface-inventory-and-save-guarantees--2026-11-23).
- Every documented API/MCP route needs a client or agent that the tenant's administrators register and grant; the selected account's private 2026-11-02 record shows none and no self-service route. The REST block read omits incomplete blocks, time off and overtime requests. No interface documents a revision precondition on time-block writes; REST refuses overlapping in/out times (A758), which guards one slot only.
- Local browser prerequisites are unchanged: Chrome 157 and Playwright 1.65.1, the latter only inside the Word package. No browser, profile or tab was contacted, because the session had no current selection or native approval from the user.
- No Workday data was read or written, no client or connector was connected, and no message was sent. The 30 offline tests still pass. The step 1–5 handoff above stays open: access, a complete-week read and save guarantees are unestablished. Proposed dispositions are in the [concept doc](workday-capabilities.md#transport-proof-and-dispositions--2026-11-23) for the user's decision.

## Browser reader groundwork — 2026-11-23
The user asked to build the browser route fully and offered browser access. Groundwork only; no adapter code yet, and no time entries were changed.

- **Runtime.** Python Playwright 1.63.0, already in the local uv cache, documents `connect_over_cdp("chrome", no_defaults=True)` and contains Chrome-channel discovery, so the adapter can stay in Python beside `use-workday` with its own pinned uv environment in `setup-workday`. Chrome 144+ requires the user to turn on remote debugging at `chrome://inspect/#remote-debugging`, asks the user to Allow each connection, and shows an automation banner while connected.
- **Tab handling plan.** Find the user's open Workday tab to select the profile, open a separate working tab in that same context, read there, and close only that tab, so the user's tabs are untouched.
- **Page map, read-only through the user's signed-in Chrome.** The tenant's Enter My Time task opens a week calendar. `prevMonthButton` and `nextMonthButton` (labelled Previous/Next Week) move weeks; `dateRangeTitle` gives the range with its year; `hoursEntered_0..6` give per-day hours; `summarizedListItem` gives category totals, including Timesheet Total and the classification split. Each time block is a `calendarevent` with `data-automation-eventid` (an instance ID such as `5773$…`), `data-automation-appointment-style` (approval status, `approved` observed), and start and end as month-day-hour-minute without a year. All-day non-events carry no event ID: holidays, and "Time Period End START - END" markers, which give each pay period's exact range. A week without a marker lies inside one period. The worker prompt carries a stable instance ID in a `selectedItem_…` attribute next to the worker's name.
- **Actions → Review Time by Week** shows a table (Date, Status = payment status such as Paid, Type, In, Out, Out Reason, Quantity, Units, Worktags, Comment, Details) with the same totals. Its Details opens a read-only "View Time Block" popup with entry code, full in/out times, out reason, source and comment; its Calculated tab gives the classification ("Time Calculation Tag"). The time-zone text there is Workday's fixed zone label, such as "GMT-06:00 Central Time (Chicago)", shown even on daylight-time dates, so it must be matched to a user-confirmed IANA zone, never parsed as an offset.
- **Avoid:** Check In, Check Out and Run Calculations change records.
- **Still unknown:** status styles for not-submitted and submitted blocks (none exist now), the permitted time-type list (needs the entry dialog, opened and cancelled), and whether worktags ever appear for this account.
- **Next:** build `setup-workday` attach/select/read code that produces the v1 snapshot (content fingerprint as `revision`, `draft_save_supported: false`), with synthetic DOM-fixture tests; then one consented live read of a complete week; then the user's save-safeguard decision.

## Earlier planning state (2026-11-02)
- The user wants an agent-directed deterministic tool to reduce the repeated model calls and page inspection involved in recurring Workday time entry. Existing signed-in browser reuse is preferred; browser fragility is accepted.
- No API, MCP, third-party integration or standalone browser runtime has been selected. Interactive browser execution is not proof that an Agent Hands script can attach to that session.
- Setup owns installation, authorization/session binding and reconnect; use owns bounded reads, previews, draft saves and explicitly approved submissions. Private consumer context is outside this repository.
- Actual tokens, cache usage and per-run charges were not exposed by the supported task metadata inspected for the motivating run. No numerical usage/cost or savings claim is established. Tenant-specific observations and execution history remain in the private consumer record.

## Remaining acceptance backlog (original item wording preserved)
### 1. Prove the transport and session boundary
- [ ] Inventory current supported Workday interfaces and maintained integrations against vendor documentation; record date/version, authorization prerequisites, relevant time-entry coverage and a reasoned reuse/custom decision. Verify official MCP availability and administrative prerequisites before stating them as facts.
  - 2026-11-23: interfaces, prerequisites and coverage recorded with dates in the transport reference; reuse the official REST or MCP route if the tenant grants it, with no custom API wrapper. The decision stays open until the user chooses a disposition and the access gate changes.
- [x] Inspect the selected desktop/browser host's documented integration surface and prove a read-only connection from the intended Agent Hands runtime. Test the existing-session preference first. Do not assume Playwright attachment, copy a browser profile, extract cookies or enable debugging as a shortcut.
  - 2026-11-23: Chrome's own consent flow with the user turning on remote debugging and clicking Allow; a standard-library client after Playwright's attach stalled; complete weeks read live. No profile copy, cookie access or automatic setting change.
- [ ] Record who owns the session/profile/tab, exact tenant/account checks, concurrent-user behavior, native login/MFA handoff, expiry, cancellation, reconnect and supported platforms. If only an interactive REPL can execute, report that limit and evaluate whether a bounded batch adapter is supported.
- [ ] Choose and document the transport only after the proof. Keep a dedicated persistent profile as an explicit alternative; do not introduce it silently or make all providers depend on it.

### 2. Implement the common contract offline
- [ ] Define versioned structured inputs and allowlisted results for `read-timesheet`, `preview`, `save-draft` and `submit-approved`; names remain provisional. No arbitrary script, endpoint, selector, shell command or generic API escape hatch supplied by the agent.
- [ ] Validate exact target/date/timezone, time blocks, explicit breaks, types/worktags, overlaps, totals, pay-period crossings and supported overnight/DST behavior. Reject missing actual work data; never invent hours or infer final approval from a template.
- [ ] Normalize service statuses so blank/zero, saved draft, submitted, sent for approval, approved, denied and unknown remain distinguishable. Keep user authorization separate from manager approval.
- [ ] Add plan/service-state fingerprints, exact-match skips, conflicting-entry refusal, target/week serialization, preflight re-reads and postcondition readback. Make uncertain effects block retries until reconciliation.
- [ ] Design private, minimal recovery records with exact stage/completed effects/pending effects and redacted evidence. Keep credentials and full page trees out of returned values and project fixtures.

### 3. Build the bounded executor
- [ ] Implement known deterministic form sequences behind the chosen supported transport. Use semantic controls and explicit state checks; stop on layout drift, ambiguous targets, missing controls, authentication or validation warnings.
- [x] Implement `read-timesheet` and local `preview` first. Return compact normalized output and the human-review diff rather than a series of large accessibility snapshots.
  - 2026-11-23: the browser reader returns the validated v1 snapshot and compact observations; the existing offline `preview` consumes it.
- [ ] Implement `save-draft` with explicit saved/not-submitted verification and partial-save reconciliation. A save that submits or certifies must refuse this operation.
  - 2026-11-24: implemented through Quick Add under the user's re-read safeguard, with per-block readback as a draft, clean stops before sending and a `reconcile` command; offline-tested. Stays open until a live save on real work is verified.
- [ ] Implement `submit-approved` against exact reviewed data and a fresh explicit user authorization. Inspect the certification/range/total, refuse materially changed text or targets, and verify submitted/sent-for-approval. Already-submitted matching data must not be submitted again.
- [ ] Write the owning setup/use skill instructions, operation examples, native entrypoint, privacy/storage rules, supported runtime/platform matrix and recovery guidance. Keep employer policy in the private consumer skill.

### 4. Fixtures, measurement and later live QA
- [ ] Test synthetic empty/populated weeks, exact duplicates, conflicts, mixed statuses, rejected validation, stale plans, concurrent changes, wrong tenant/worker/week and cross-pay-period blocks.
- [ ] Test partial saves, uncertain save/submit responses, interrupted sessions, native/MFA cancellation, changed markup and unexpected certification. Verify read-before-retry and that no cleanup mutation occurs automatically.
- [ ] Benchmark the same synthetic workload under the model-directed loop and deterministic executor. Record phase boundaries, model/tool/UI calls, retries, result bytes, available token/cache/reasoning counters, runtime/model and correctness. Keep missing counters null; no private-log workaround or elapsed-time token estimate.
- [ ] Report measured changes with uncertainty and startup/reconnect cost separated. Use current exact-model API rates only for an explicitly labeled API-equivalent calculation; never equate it with subscription consumption.
- [ ] With separately authorized live scope, prove read and preview first, then exact draft persistence, and only then explicitly approved submission. Capture private readback/status evidence; do not create disposable payroll data merely to test.
- [ ] Obtain human QA for session reuse, native login/reconnect/cancel, readable previews and recovery on the selected desktop host. Record other platforms as unverified until tested.

## Ready for human review
- Offline contract/preview behavior is ready for review. Runtime attachment, authorized integration client, production draft execution and live QA remain blocked. Do not ask the user to test live saves with this build.

## Done
- [x] 2026-11-02: expanded the existing generic capture into this scratch concept/task pair at the user's request, preserving reuse-first discovery and the setup/use and public/private boundaries.
- [x] 2026-11-02: recorded the deterministic-browser motivation, existing-session preference, accepted fragility, bounded command proposal, correctness/recovery checks and measurement plan. Transport selection and implementation remain open.

## Added implementation work completed — 2026-11-16
- [x] Promote the existing scratch pair without losing the broader plan; preserve unrelated spikes and dirty files.
- [x] Implement a strict versioned offline snapshot read and complete-week preview with exact target, breaks, DST/overlap, classification, periods, totals, exact-match and protected/conflict checks.
- [x] Implement a fake-tested internal draft state machine with fresh preconditions, conditional-create requirement, Unix target locks, durable intent, per-entry readback and conservative partial/uncertain reporting. Production adapter and settled reconciliation remain open.
- [x] Document repository-relative setup/use commands, privacy, adapter prerequisites and explicit unavailable-live behavior; add synthetic tests without actual employer or time-entry data.
