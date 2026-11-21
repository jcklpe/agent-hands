---
attention: live
status: transport-blocked
implementation: offline-contract
reviewed: 2026-11-21
---
# Workday capabilities — investigation and implementation handoff
[Concept, decisions and boundaries](workday-capabilities.md). Promoted from scratch on 2026-11-16 for authorized reusable CLI implementation. Actual time entry remains outside this implementation scope; the separately authorized read-only browser probe is recorded below.

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
- The user explicitly authorized a read-only existing-session probe. Its first attempt failed before returning Workday headings; native connection setup and a selected signed-in Workday tab remain the next live gate. No timesheet write, cookie/profile export, security-setting change or normal-tab mutation was performed. Complete worker/week retrieval and production save semantics remain unproved.

## Earlier planning state (2026-11-02)
- The user wants an agent-directed deterministic tool to reduce the repeated model calls and page inspection involved in recurring Workday time entry. Existing signed-in browser reuse is preferred; browser fragility is accepted.
- No API, MCP, third-party integration or standalone browser runtime has been selected. Interactive browser execution is not proof that an Agent Hands script can attach to that session.
- Setup owns installation, authorization/session binding and reconnect; use owns bounded reads, previews, draft saves and explicitly approved submissions. Private consumer context is outside this repository.
- Actual tokens, cache usage and per-run charges were not exposed by the supported task metadata inspected for the motivating run. No numerical usage/cost or savings claim is established. Tenant-specific observations and execution history remain in the private consumer record.

## Remaining acceptance backlog (original item wording preserved)
### 1. Prove the transport and session boundary
- [ ] Inventory current supported Workday interfaces and maintained integrations against vendor documentation; record date/version, authorization prerequisites, relevant time-entry coverage and a reasoned reuse/custom decision. Verify official MCP availability and administrative prerequisites before stating them as facts.
- [ ] Inspect the selected desktop/browser host's documented integration surface and prove a read-only connection from the intended Agent Hands runtime. Test the existing-session preference first. Do not assume Playwright attachment, copy a browser profile, extract cookies or enable debugging as a shortcut.
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
- [ ] Implement `read-timesheet` and local `preview` first. Return compact normalized output and the human-review diff rather than a series of large accessibility snapshots.
- [ ] Implement `save-draft` with explicit saved/not-submitted verification and partial-save reconciliation. A save that submits or certifies must refuse this operation.
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
