---
attention: live
status: selected
implementation: not-started
decision_date: 2026-10-31
reviewed: 2026-10-31
---
# Bitwarden capabilities — native decision and coding handoff
[Selected decision and scope](bitwarden-capabilities.md#selected-decision-and-finalized-scope). **User selected Secrets Manager Free plus the official `bws` CLI on 2026-10-31.** Native desktop interaction with no human terminal use is required. This is the finalized scratch-spike decision and coding handoff; implementation is not started or authorized by this documentation update.

## Sequencing decision - 2026-11-23
Revisit this scope after Penpot and Workday, beginning with a discussion of the remaining bootstrap, access and credential-lifecycle choices. The existing Secrets Manager/official `bws` selection remains the starting point. This sequencing update does not start implementation, installation, provisioning, login, billing changes or credential migration. Preserve working provider settings and sign-ins.

The provider-storage continuation has already established `~/.agent-hands/` defaults and corrected Odoo transport so bearer values and JSON bodies are not curl arguments. Inspect the maintained implementation before repeating those prerequisite repairs. Bitwarden credential delivery is still unimplemented; moving configuration files did not centralize secrets or encrypt retained document content.

## Current state
Selected scope: Secrets Manager Free plus the official `bws` CLI, with a thin optional Agent Hands integration for runtime service credentials. Use native/browser setup, OS-protected bootstrap, scoped injection into trusted named provider operations and sanitized results. An Agent Hands MCP interface is optional future work over the same backend; Password Manager `bw`, its vault MCP and `aac` are not runtime dependencies.

Official plans provide a Secrets Manager Free path; the actual current account's subscription/enablement is unknown. Do not penalize unknown cost or count separate provisioning as inherently undesirable. No live account/billing settings, credentials, tokens, process environments or private configuration were inspected.

Remaining implementation work concerns `bws` native bootstrap/access, the trusted named-operation adapter, output handling and provider transport checks. These details still need proof; the product/backend choice is settled. Password-vault hygiene is a separate scope and adds no work to this handoff. Public-safe source inspection is research evidence, not a passed desktop/native test.

## To Do — selected-scope handoff, implementation not started
- [ ] When coding is requested, hand off the selected Secrets Manager Free/official-`bws` plan and acceptance checks below. Do not code, install or create a thread from this decision-log update.
- [ ] Resolve the native bootstrap/helper, OS access-control and session/cache lifecycle details for the selected `bws` route using synthetic data first. The browser/native/no-human-terminal requirement is already settled.
- [ ] During later scoped setup, confirm an appropriate existing or new Free organization, account/region and exact test-secret/provider references from non-secret inputs. Do not change billing or treat private subscription history as portable project documentation.

## Selected coding handoff — ready when implementation is requested
### Common contract and one fake provider read
- [ ] Define optional `setup-bitwarden`/`use-bitwarden` ownership consistent with [setup/use contracts](../archive/setup-use-contracts.md). Setup owns native installation/account/bootstrap/reconnect; use owns bounded runtime operations. Existing providers remain usable without Bitwarden.
- [ ] Define exact account/region/profile/project-or-item/field bindings and fixed named provider operations. Keep non-secret aliases/settings separate. No agent-supplied arbitrary shell, executable/env-key mapping or generic plaintext-secret response.
- [ ] Integrate the official `bws` CLI behind a thin optional trusted adapter. Use scoped injection for fixed named provider operations and return sanitized results. A later MCP interface can call the same bounded logic without changing the backend or forwarding secrets into model context.
- [ ] Exercise a synthetic Odoo `projects list ALIAS` against a local fake transport. Preserve account/base-URL/database routing and environment precedence; include the selected provider's minimal transport correction so fake bearer values do not appear in subprocess argv.
- [ ] Use safe structured results/errors and synthetic password/session/provider-key markers to test success, missing scope, denial, cancellation, timeout, remote failure and cleanup failure. Do not return raw credential-bearing inner responses or vendor diagnostics.

### Selected bws integration with native machine-token bootstrap
- [ ] Verify a no-terminal native setup flow for capturing an already authorized machine token into a protected OS credential store. No token/password in chat, tool arguments, persistent config or shell startup. Document that native OS access authorization is distinct from Bitwarden master-password unlock.
- [ ] Verify the selected macOS native keychain policy/helper identity/access control, prompt behavior, cancellation and recovery from the desktop host using synthetic data first. Do not promise that generic Keychain storage automatically enforces per-use prompts or trustworthy process identity.
- [ ] Reuse official `bws` injection where the project's complete secret set is appropriate. Bind to a read-only minimal machine/project scope; evaluate exact-secret private retrieval if project-wide injection is too broad. Account for the Free tier's three-project/three-machine limits before claiming per-provider isolation scales.
- [ ] Keep the bootstrap token in trusted code/`bws` only, not the provider child. Verify `bws` version/environment inheritance, state caching/opt-out, native access frequency, expiry/revocation delay, rotation and outage recovery. Explicitly distinguish local OS lock from revoking issued machine sessions.

### Unselected Password Manager branch — retained comparison only
These tasks are outside the selected runtime-credential scope, not outstanding implementation work. Retain the earlier wording as proposal history; do not implement this branch or make it a prerequisite for `bws`. Password-vault hygiene is a separate question.

```markdown
### Branch B: private official MCP plus native account setup
- [ ] Reuse the vendor server as an adapter-owned private subprocess where practical; expose only the named Agent Hands operation to the desktop client. Do not additionally register secret-returning upstream tools as a purported safe boundary. If forking instead, document the update/maintenance cost.
- [ ] Reuse native `unlock`, consume exact-item `get` internally and deliver only the selected provider fields to trusted code. No raw secret-bearing inner MCP message, static config session or vault dump crosses the outer interface.
- [ ] Supply/verify initial account login and reconnect entirely through a supported native flow around official CLI auth. The current MCP tool catalog lacks login; an already logged-in web/desktop app must not be assumed to authenticate its CLI profile.
- [ ] Define owned server/profile lifetime, idle lock, cancel/exit lock, concurrency, crash/manual native recovery and account/region checks. Verify lock result and held session behavior for the chosen release; no claim that closing a process revokes copies of a session.

```

### Shared acceptance checks and desktop QA
| Check | Pass condition | Evidence |
| --- | --- | --- |
| Native flow | Setup, auth/bootstrap, unlock, cancel, reconnect and recovery require no user terminal; secrets enter only the approved native UI. | Synthetic/native proof from the selected desktop host; real credential QA only with exact setup authorization. |
| Product/auth clarity | UI accurately identifies Bitwarden master-password unlock versus native OS authorization for a machine token. | Reviewed prompt copy and cancellation/status outputs. |
| Exact scope | Account/server/profile and exact project/item/field match; unknown/mismatched/denied targets fail before provider launch. | Fake backend calls containing IDs/status only, with negative cases. |
| Fixed operation | Only the selected provider read and validated non-secret args launch; arbitrary shell/executable/env injection or mutation refuses. | Positive fixture and rejected argument/operation/mapping cases. |
| Internal credential delivery | Provider receives required fields only; no bootstrap token, `BW_SESSION`, password transport or unrelated project/vault secrets. | Child asserts locally and emits booleans, never an environment dump. |
| MCP/result boundary | Secret-bearing inner results and tested sensitive representations never appear in the desktop/model-visible tool inputs/results/errors/logs/previews. | Structured schema checks and marker scans on success/failure/echo fixtures; no universal-redaction claim. |
| Provider transport | Selected client's subprocess argv contains no fake credential marker. | Intercepted fake transport arguments and existing relevant provider tests. |
| Lifecycle | Denial/cancel starts no provider call; timeouts and cleanup failures report honestly; session/cache/revocation and crash recovery behavior match documented scope. | Fake ordering/exit-status checks and later separately approved native QA. |
| State and bootstrap | Protected storage/cache locations, permissions and ignore rules are verified before real data. No plaintext credential/session/export file or startup export. | Synthetic filesystem/state checks plus selected native-store policy evidence. |
| Provider semantics | Routing, operation bounds, preview/write controls and provider request behavior are preserved; vault-route failure does not silently fall back. | Synthetic request/result comparison. |
| Trust limit | Docs do not equate private MCP/injection or item mapping with isolation from unrestricted same-user shell access. | Contract/skill/handoff review. |

macOS is the proposed first native-host proof; other platforms remain unverified. No installer/client/account changes for unselected platforms. Native proof with fake data is not proof of real account access.

### Later real setup, read and migration — exact scope required
- [ ] Before installation, authentication, token storage, provisioning or a real read, obtain the exact authorized software/version/source, account/region, native flow, protected state location, project/item/fields and provider operation. Design agreement is not live setup authorization.
- [ ] After that scope is authorized, perform only its native setup/test and record non-secret verification, denials/uncertainty and recovery. Do not alter billing or start a paid trial without its own requested scope.
- [ ] After a verified real read, preview any separately requested one-provider migration, old-copy removal and rollback. Do not migrate all credentials, delete the prior route or write secrets back to a vault automatically.
- [ ] Treat OAuth as separate follow-on work: preserve consent, provider-owned access/refresh/cache state, atomic persistence, concurrency, rotation and reconnect. Start with synthetic expired/rotated tokens. Initial secret injection does not eliminate local OAuth caches.

## Ready for coding handoff / human QA
- The user has selected Secrets Manager Free plus official `bws`; native desktop setup/no human terminal, optional Agent Hands integration, OS-protected bootstrap and bounded results define the final scope.
- Implementation has not started. The selected coding plan is ready for a dedicated implementation request; no account setup or real-account QA is ready or claimed.
- Native helper behavior and real account enablement are unverified implementation/setup details. They do not reopen the backend decision; the public Free-tier path is documented in the concept.

## Done — selected decision and research history
- [x] Record the user's backend/authentication direction: scoped Secrets Manager machine credentials with native OS authorization, or Password Manager credentials with the official Bitwarden MCP native master-password unlock. Native/no-terminal interaction is already required; do not offer a terminal fallback. — 2026-10-31: the user selected Secrets Manager Free plus the official `bws` CLI and requested this final decision/scope in an Agent Hands scratch spike. Native desktop/no-terminal interaction remains required; no implementation or setup was started.
- [x] Compare the minimum missing native setup work for the selected route against the weighted criteria in the concept. Record uncertainties rather than inventing totals; weights are proposed, not user-adopted preferences. — Dropped/superseded 2026-10-31: the product direction is now selected. Remaining native-bootstrap and lifecycle work is listed in the selected implementation plan; the old agent-proposed weights were not adopted as user preferences.
- Logged the finalized scope and its boundary: runtime service credentials only, with password-vault hygiene separate; preserved historical research and unselected tasks without treating them as current prerequisites.
- Recorded the clarified native-dialog/no-human-terminal requirement and withdrew the terminal pilot; no terminal authentication or implementation took place.
- Reopened the premature direct-`bw` preference. The official server already wraps `bw`; direct CLI has no inherent vault/security advantage. Added private MCP composition as a valid implementation candidate and separated the agent-facing interface from the backend store.
- Verified public Secrets Manager plan/signup documentation: Free includes unlimited secrets with limits of two users, three projects and three machine accounts; actual user entitlement remains unknown. No account or billing settings were inspected or changed.
- Reviewed the official MCP source for native unlock/session handling, credential-returning `get`, lock and missing login tool. Reviewed `bws` native bootstrap needs, machine scope/state and official injection; documented rather than assumed the missing pieces.
- Added proposed weights, native gate, route-specific handoffs and shared acceptance checks. Retained provider transport and OAuth-cache findings from public-safe code; no provider/auth/config code was edited.
- Retained earlier migration and parked cleanup records below. This pass did not repeat the migration, archive LifeOS material, edit indexes, or claim those historical tasks completed.

## Superseded direct-bw handoff — historical proposal only
The following decision/stage checklist is retained verbatim as the withdrawn proposal, not current work. In particular, its request to accept a human-terminal pilot is resolved by the explicit native/no-terminal requirement. Do not execute these stages or ask that terminal question again. Use the current native handoff above. No checklist item below was implemented by the research pass.

```markdown
- [ ] Record the user's product decision: accept `bw` with the existing Password Manager vault, or explicitly select Secrets Manager/Agent Access/MCP-based delivery instead. The agent recommendation is not approval.
- [ ] Record the user's interaction decision: accept one human-started, private-terminal unlock per operation for the pilot, or require a native desktop dialog before implementation. No session-token copying or agent-recorded password entry.
- [ ] Once those decisions are settled and a coding thread is requested, carry the exact candidate plan and acceptance criteria into that handoff. Do not start a thread or code from this planning update alone.

## Candidate implementation stages — only after the decision
### Stage 1: offline contract and fake-source proof
- [ ] Define optional `setup-bitwarden` and `use-bitwarden` skills beside their implementation, following the [setup/use contracts](../archive/setup-use-contracts.md); no provider must gain a mandatory vault dependency. Keep installation and account repair in setup.
- [ ] Define a secret-free binding from provider/account alias to exact vault item ID and field, fixed allowed variable and named operation. No arbitrary env-key mapping, executable path or shell string supplied by the agent. Resolve paths safely and never source config as code.
- [ ] Implement the foreground operation lifecycle against a fake `bw` source first: distinguish login/locked/unlocked states, capture session output internally, pass only the provider credential onward, explicitly lock the owned profile, and produce bounded status/errors. No real vault access.
- [ ] Exercise the synthetic Odoo `projects list ALIAS` path against a fake local transport. Preserve base URL/database/account selection and environment precedence; include the minimal transport change needed to keep bearer values out of subprocess argv. Do not broaden into unrelated provider refactoring.
- [ ] Pass every applicable acceptance check below and record command/version/OS evidence, including failures. A passing synthetic test does not establish real account access.

### Stage 2: separately authorized installation and interactive setup
- [ ] Before any real install/login/unlock/read, obtain the user's explicit setup scope: approved software/version/source, account and server/region, profile-state destination, exact test item/fields and permitted provider read. Design approval alone is insufficient.
- [ ] Verify the chosen official CLI version's real prompts, login state, locked state, session output and explicit lock behavior in the approved human-controlled surface. Never ask for a password/token in chat or an agent tool argument. Keep the master password unstored and capture any returned session internally.
- [ ] Use the dedicated CLI profile and verify permissions, account identity and ignore/external-state placement before storing runtime state. No shared-shell export, static MCP `BW_SESSION`, persistent session cache or automatic credential migration.
- [ ] Human QA: verify unlock/cancel flow, bounded result and cleanup in the real desktop/terminal context. If the unlock frequency is unacceptable, stop rollout and decide session ergonomics explicitly rather than silently add a daemon, keychain cache or broad agent session.

### Stage 3: one real read, then a separately scoped migration
- [ ] Perform only the explicitly authorized provider read with the selected exact test item and operation; record non-secret evidence. No provider mutation or extra vault enumeration.
- [ ] Report what was verified and any residual exposure, platform gap or cleanup failure. Preserve the existing credential/config route as rollback; do not silently fall back to it when the vault route fails.
- [ ] If requested, preview migration of one provider's static credentials, including exact fields, private destination, removal of old copies and recovery. Execute only the approved migration scope; do not delete the prior route merely because a read succeeded.

### Stage 4: OAuth and further providers, separately scoped
- [ ] Inventory only public-safe examples and code for the next chosen provider. Distinguish static keys, OAuth client configuration, access tokens, refresh tokens, MSAL caches, aliases and operational settings.
- [ ] Preserve consent and provider-owned refresh/cache semantics. Design cache protection, atomic writes, concurrency, rotation/reconnect, failure and rollback before replacing any token store. Use synthetic expired/rotated tokens first; do not introduce vault writeback by default.
- [ ] Revisit Secrets Manager only for an actual unattended/machine-scope requirement; revisit `aac` only if preview acceptance and official injection are selected. Neither evaluation blocks the basic decision table or requires installing an alternative now.

```

## Earlier research checklist — historical proposal only
The earlier research checklist and its old status description are retained as quoted proposal history. Its terminal-interaction and default-backend assumptions are superseded by the current native decision above.

```markdown
The prior checklist is retained verbatim below to preserve planned work. Product comparison and public-safe code inventory are now documented above, but no execution task is completed by that research. The proposed pilot narrows the initial work; `bws`/`aac` execution is deferred unless that alternative is selected. Bootstrap/session persistence is replaced by the proposed no-persistent-session pilot, subject to the human interaction decision. Cleanup tasks remain parked.

- Select the actual product/account fit: personal Password Manager vault cleanup versus Secrets Manager provider credentials; compare Agent Access's early-preview support before adding a wrapper.
- Define proposed `setup-bitwarden` and `use-bitwarden` contracts around official executables, selected accounts/projects, narrow targets and explicit setup ownership. Do not implement custom authentication or expose a generic secret-dump route.
- For runtime credential delivery, evaluate official project-scoped `bws run` and `aac run` using only fake credentials and a trusted provider operation. Verify that tool inputs/outputs, errors, previews and logs contain no plaintext secret. Test failure and child-process behavior as well as success.
- Decide a protected bootstrap source outside the repo and model-visible text; document least-privilege access, rotation, authenticated-session revocation delay, outages and recovery.
- Inventory provider integration needs from public-safe examples and code only. Preserve OAuth consent, refresh/cache semantics and non-secret alias configuration; separately authorize any later credential migration.
- Revisit the earlier vault-cleanup checklist only when cleanup implementation is explicitly resumed. Verify current tool versions, unlock behavior, backup encryption and restore semantics before choosing a reversible cleanup plan.

```

## Earlier consumer cleanup scope
The original consumer-specific cleanup proposal and checklist were preserved in the private workspace’s historical records on 2026-10-31. This public pair retains the runtime credential-delivery decision and generic safeguards above. Cleanup remains a separate parked use case; no cleanup implementation or real vault operation is authorized by this record.
