---
attention: live
status: selected
implementation: not-started
decision_date: 2026-10-31
reviewed: 2026-10-31
---
# Bitwarden capabilities and credential delivery
[Decision tasks and coding handoff](bitwarden-capabilities.todo.md). **Decision selected on 2026-10-31: Secrets Manager Free plus the official `bws` CLI for runtime service credentials.** Keep this as an Agent Hands scratch spike and handoff. Implementation has not started; this decision-record update authorizes no coding, installation, authentication, provisioning or credential changes.

## Goal and requirements
Supply runtime service credentials to selected Agent Hands operations from **Bitwarden Secrets Manager Free through the official `bws` CLI**, reducing scattered local secret configuration. Keep non-secret aliases, targets and ordinary settings local. The user selected this store/tool scope; Password Manager, direct `bw` and its vault-management MCP are not dependencies of this runtime integration.

The human uses native desktop agent apps. **Native secure dialogs and no human terminal interaction are requirements**, including setup, login/bootstrap, unlock, cancellation, reconnect and recovery. Agents may invoke CLIs internally. Do not ask the human to paste a password/session into chat, export a shell variable, copy a session between terminals or accept a terminal pilot as a compromise.

A centralized hardened store is an intended improvement. The user accepts that credentials must reach trusted local code and that model-output disclosure is a general secret-use risk. Compare the actual default data flow and implementation work; do not treat use of Bitwarden, a machine token or MCP as uniquely disqualifying.

## Selected architecture layers
| Layer | Selected scope | Implementation boundary |
| --- | --- | --- |
| Secret store and authorization | Secrets Manager Free, with scoped machine/project access | Runtime service credentials are separate from password-vault hygiene. |
| Official runtime tool | Official `bws` CLI and scoped injection | Reuse official secret delivery; add only the thin optional Agent Hands operation integration. |
| Human setup and authentication | Browser/native desktop setup, secure dialogs and an OS-protected bootstrap token | No human terminal use; native OS authorization of the machine token is distinct from a Bitwarden vault master-password unlock. |
| Agent-facing interface | Existing CLI-based Agent Hands operations initially; MCP is an optional future interface | A later MCP surface can use the same `bws` backend without changing secret storage or exposing raw credentials. |

These layers can be combined. For example, an Agent Hands MCP tool can use `bws` as its backend, or privately consume the official Bitwarden MCP server. Choosing Secrets Manager does not require the human to use a terminal; choosing MCP does not require credentials to be returned to the model. MCP supports application-defined tools and structured results. [MCP tool specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

## Prior comparison: bw and the official MCP
For supported vault operations, the official server already invokes `bw`; direct CLI use offers no inherent vault capability or confidentiality advantage. The MCP adds an existing native unlock flow. Direct `bw` can reduce protocol/process dependencies for a CLI integration, but under the native-desktop requirement that benefit must be weighed against new prompt/login/session work. It is not enough to recommend `bw` because its backend is the same. [Official CLI invocation code](https://github.com/bitwarden/mcp-server/blob/main/src/utils/cli.ts)

The particular official server's `get` handler forwards CLI output into the tool result; registering that tool directly with the agent can expose the retrieved password/item. That is a property of those tools, not of MCP. A small Agent Hands adapter could call `unlock`, request an exact item privately, feed a trusted provider operation, and return only its bounded result. The secret-bearing inner response must stay inside trusted code, not be relayed to the desktop client/model. [Official handlers](https://github.com/bitwarden/mcp-server/blob/main/src/handlers/cli.ts)

This is a valid candidate. Composition avoids changing the vendor server: keep it as an adapter-owned private subprocess and expose only the bounded Agent Hands operation. A fork adding that operation is another option but creates update/maintenance work. Simply registering the official server next to a safe tool still leaves the original secret-returning tools available; client-side tool hiding is not the same as an enforced boundary.

## Product and route comparison — retained research
The Secrets Manager executable is `bws`, not `btws`. A is now selected. B, C and D below preserve the comparison, not pending implementation branches or prerequisites.

| Candidate | Official behavior available now | Work still needed for this goal |
| --- | --- | --- |
| A. Selected: Secrets Manager Free plus official `bws` injection; MCP interface optional later | Machine-account authentication, project access and official `bws run` environment injection. This is a distinct store from Password Manager, designed for application/runtime secrets. | Native bootstrap-token entry/storage/access, named-operation mapping, safe results, lifecycle/recovery and provider integration. A dedicated minimal project or private exact-secret retrieval is needed to limit delivery. [CLI](https://bitwarden.com/help/secrets-manager-cli/), [overview](https://bitwarden.com/help/secrets-manager-overview/) |
| B. Password Manager through a private official-MCP backend | Native unlock and `bw`-backed retrieval; reuse of the existing vault and official dialog. | Bounded adapter, non-terminal initial CLI account login, session ownership, safe internal credential consumption and provider delivery. [Server](https://github.com/bitwarden/mcp-server) |
| C. Direct `bw` plus native Agent Hands helper | Official vault authentication and retrieval; no official `bw run` equivalent is documented. | Native setup/unlock and session handling plus the same operation mapping/injection as B. Keep as a baseline/fallback, not a default winner. [Password Manager CLI](https://bitwarden.com/help/cli/) |
| D. Agent Access `aac` | Official `bw` provider, listener/pairing and field-to-environment `aac run`. Early preview with changing APIs/protocols. | Verify a completely native human flow, pairing approvals/state, requested provider fields and child execution. Its documented interactive `/unlock` is not evidence of the MCP native dialog. Optional research, not a required deployment. [Official project](https://github.com/bitwarden/agent-access) |

### Earlier proposed weighting — not an adopted scoring system
This pre-decision research aid is retained for rationale. The user has selected A; the weights were an agent proposal and were never adopted as user preferences. Native interaction remains a requirement. No numeric route scores or totals are claimed, and remaining implementation unknowns do not reopen the selected product direction.

| Criterion | Weight | A: bws | B: private official MCP | C: direct bw | D: aac |
| --- | ---: | --- | --- | --- | --- |
| Runtime injection and normal model-context exposure | 25 | Purpose-built injection; child/output boundary still needs checking. | Inner retrieval stays private only if adapter enforces it. | Same desired boundary needs implementing. | Official injection; verify supported fields and results. |
| Official functionality reused | 20 | Reuse secret delivery and machine auth. | Reuse native unlock, retrieval and existing vault. | Reuse vault/auth; more native plumbing locally. | Reuse agent-oriented delivery, accepting preview churn. |
| Authenticated-session lifecycle | 15 | Machine token and cached sessions; define OS prompt, expiry and revocation behavior. | Owned server/profile; explicit lock/reconnect; verify crashes and concurrency. | Same lifecycle responsibility without server mediation. | Listener, pairing/session expiry and revocation need evidence. |
| Scope of credentials accessible | 15 | Service credentials can be isolated from personal logins; machine access can be read-only. | Adapter can request one item, but underlying vault session is broader. | Same underlying vault scope. | Verify provider/pairing enforcement; do not infer item scope. |
| Incremental cost and entitlement | 10 | Free tier may cover the intended pilot; actual account status unknown. | Uses Password Manager; current subscription not verified. | Same as B. | Assess only if selected; no assumed subscription premium. |
| Missing implementation and maintenance | 15 | Native bootstrap plus trusted operation adapter/provider checks. | Native initial login plus private MCP client/process and delivery adapter. | Native login/unlock/session plus delivery adapter. | Native UX verification plus preview integration maintenance. |

The implementation-burden comparison concerns work not already supplied by the selected official route. Every candidate still needs the provider's own output/transport audit and account/target checks. Provisioning a project or machine account is not inherently bad: it can provide useful scope and separation. Evaluate the actual steps and permissions, not whether the product is called “separate.”

## Entitlement and cost: verified public facts, unknown account state
Secrets Manager has a Free plan with unlimited secret storage, up to two users, three projects and three machine accounts. That can support a small runtime-credential deployment without a paid upgrade. It is a separate product/organization configuration; it is not necessary to infer that a personal Premium subscription includes it. [Official plans](https://bitwarden.com/help/secrets-manager-plans/)

Bitwarden documents enabling Secrets Manager on a Free organization and, for Families users, creating a separate Free organization. The same Bitwarden identity can be used; this does not inherently mean a new personal account or extra subscription cost. Do not activate a paid trial or alter billing to evaluate the design. [Official signup paths](https://bitwarden.com/help/sign-up-for-secrets-manager/)

The user's current subscription, enabled organizations and Secrets Manager access remain unverified. No live account, credential or billing settings were inspected in this pass. Record only an appropriate non-secret entitlement conclusion if verified later; no receipt/history or account-specific details belong in portable Agent Hands docs. Public free-tier availability is sufficient to avoid treating unknown cost as a disadvantage now.

## Native feasibility and missing work
### Selected scope: bws with native bootstrap and OS authorization
The CLI authenticates with a machine access token, rather than performing an ordinary personal-vault password unlock. Its documented token inputs are environment/CLI options, not a built-in native master-password login dialog. Machine accounts can have read-only project access. [CLI authentication](https://bitwarden.com/help/secrets-manager-cli/#authentication), [machine permissions](https://bitwarden.com/help/machine-accounts/)

Planned native setup within the selected scope: the human uses Bitwarden's web UI to provision/select the service project, machine account and token; a local secure dialog accepts the token into an OS-protected credential store without the model receiving it. At runtime a trusted helper obtains that token under a native OS access policy and supplies it internally to `bws`. The OS authorization dialog protects local bootstrap access; it is not a Bitwarden master-password check. A machine token remains a secret that needs rotation/recovery, not a session magically derived from the existing vault password.

For macOS, Keychain Services with an appropriate access-control policy is a candidate rather than inventing encrypted storage. Apple's Security/LocalAuthentication frameworks support user-presence authentication for protected keychain items. Actual CLI-helper signing/access-control behavior, prompt reuse and cancellation must be demonstrated from the selected desktop host; storing a token in Keychain alone does not establish any of those properties. Other OSes require their own verified native path. [Apple native keychain access](https://developer.apple.com/documentation/localauthentication/accessing-keychain-items-with-face-id-or-touch-id)

Then a fixed trusted adapter invokes official injection for a minimal selected project. Keep the machine token out of the provider child's environment, avoid arbitrary agent-supplied shell/env names, and return only structured operation results. Verify the exact `bws` version's environment inheritance and state handling. Project injection supplies that project's secrets: three free projects cannot automatically provide one isolated project for every future provider. If grouping exposes too much, evaluate private exact-secret retrieval or another plan, with its actual added work.

The documented `bws` state files are encrypted and reused; token revocation can leave an already authenticated session usable until expiry, up to an hour. Choose cached-state policy, native authorization frequency, lock/revoke actions and outage recovery explicitly; do not claim OS-dialog dismissal revokes issued machine sessions. [CLI state](https://bitwarden.com/help/secrets-manager-cli/#config--state), [access-token lifecycle](https://bitwarden.com/help/access-tokens/)

### Unselected alternative: official MCP native unlock behind a bounded adapter
Retained comparison only. This Password Manager route is outside the selected runtime-service-credential scope and is not implementation work for this handoff.

Source inspection confirms a native OS dialog, internally captured session and sanitized unlock status. The password briefly travels through a randomized one-shot environment variable to `bw`; the returned session is held in server process state. Reuse this rather than building an equivalent prompt by default. [Official unlock implementation](https://github.com/bitwarden/mcp-server/blob/main/src/utils/unlock.ts)

Native unlock does not solve first-time account login. The current tool dispatch has no login tool, and the unlock implementation directs an unauthenticated profile to `bw login`. The adapter therefore still needs a no-terminal account-setup/reconnect route around official CLI authentication, or an officially supported alternative verified for that profile. A browser/web-vault or desktop-app login must not be assumed to authenticate the CLI profile. [Tool dispatch](https://github.com/bitwarden/mcp-server/blob/main/src/index.ts), [unlock implementation](https://github.com/bitwarden/mcp-server/blob/main/src/utils/unlock.ts)

For each request, select the exact account/server/profile/item/field, privately obtain the credential and invoke only the named provider operation. The server's lock handler clears its process session and invokes `bw lock`; define explicit idle/exit/cancel/reconnect ownership, concurrent requests and crash recovery. Check actual behavior instead of inferring automatic expiry from process lifetime. No static `BW_SESSION` in a tracked MCP config. [Lock handler](https://github.com/bitwarden/mcp-server/blob/main/src/handlers/cli.ts)

### Other unselected alternatives: direct bw and aac
Direct `bw` has no demonstrated advantage over B under this native-UX requirement unless implementation proves a much simpler supported native path. Personal `bw login` is normally interactive credentials/two-step login; browser login is the organization SSO route. API-key authentication normally still needs vault unlock. Keep those facts distinct from whatever secure native helper might wrap them. [CLI login](https://bitwarden.com/help/cli/)

`aac` deserves a small optional comparison because it already offers injection, but its preview status and documented terminal-oriented setup do not establish compliance with the required human flow. Research native integration/official progress before choosing it; do not add a remote listener/tunnel deployment to this local pilot by default.

## Selected decision and finalized scope
On 2026-10-31 the user selected **Secrets Manager Free plus the official `bws` CLI** as the scope for the runtime service credentials discussed here and asked that the final scope/decision be logged as an Agent Hands scratch spike. This resolves the backend/product decision; it is not merely an agent recommendation and does not authorize implementation in this documentation pass.

The scope is a thin, optional Agent Hands integration: browser/native desktop setup, an OS-protected bootstrap token with native access controls, scoped machine/project credential delivery into trusted named provider operations, and sanitized operation results. No human terminal interaction is part of setup or normal use. The exact native helper, access-control policy, prompt/session lifetime and minimal field/project mapping are implementation details to prove, not unresolved product choices.

Use the Free tier without assuming that an existing Password Manager subscription enables Secrets Manager or changing paid billing. Account/region, an existing or new Free organization, and exact test-secret/provider references are later setup inputs. Confirm them when setup is requested, without putting private account history or secret values in this portable spike.

A password-vault hygiene/cleanup workflow is a separate question, outside this scope. No Password Manager `bw`/vault MCP setup, vault export, vault audit, deduplication or vault writes are required here. An Agent Hands MCP interface may be added later over the same Secrets Manager backend if useful; the official password-vault MCP is not a runtime dependency.

The next coding handoff can implement the selected `bws` contract/native feasibility proof and one fake provider operation when the user requests implementation. Installation, authentication, token storage, provisioning, real reads and credential migration remain later explicitly scoped work. No further backend or terminal-UX approval is needed merely to preserve this settled decision.

## Shared proof scope and boundaries
Use a synthetic Odoo `projects list ALIAS` read against a local fake transport to prove the selected `bws` integration, not a real service mutation. The existing loader accepts injected `ODOO_API_KEY`; keep ordinary account/base-URL/database settings local. Odoo currently places a bearer value in `curl` arguments, and Trello similarly passes key/token values in transport arguments. Injection does not by itself repair those paths. Include only the selected provider's required transport correction and verify subprocess arguments using fake values. [Odoo client](../../setup-odoo/scripts/client.sh), [Trello client](../../setup-trello/scripts/client.sh), [Odoo operation](../../use-odoo-projects/SKILL.md)

Keep provider OAuth consent and persistence separate from static-key injection. [Google](../../setup-google-services/scripts/oauth.py) rewrites refreshed tokens and [Microsoft](../../setup-microsoft-services/scripts/auth.py) persists MSAL state. Preserve refresh/rotation, atomic writes and concurrency; initial secret storage does not make all local caches disappear. No automatic vault writeback or all-provider migration.

All candidates trust local credential-handling/provider code. A private MCP response or environment injection avoids normal model exposure only when the adapter does not forward secrets. It does not isolate them from unrestricted same-user shell access, editable adapter code, malicious children or every possible process inspection. Claim stronger protection only with a separately enforced boundary. Test known markers/representations and use safe result schemas; do not advertise universal redaction.

Proposed setup/use ownership remains aligned with [setup/use contracts](../archive/setup-use-contracts.md). Keep Bitwarden optional for every provider. Personal vault cleanup remains a separate parked use case with its original consumer-specific rationale preserved privately. No code, install, login, token/config access, provisioning, secret read, service call, commit or push occurred in this research.

## Decision history and non-goals
The initial research favored `bws`; a later proposal favored direct `bw` mainly because a vault already existed and added a human-terminal pilot. The user clarified that native dialogs/no terminal are required and challenged both assumptions. That direct-`bw` recommendation and terminal handoff are withdrawn; neither was approved or implemented. On 2026-10-31 the user selected Secrets Manager Free plus official `bws` for runtime service credentials. The task doc retains the superseded checklist as proposal history, not executable guidance.

This work does not cover vault cleanup/exports/deletion, a generic secret-return tool, a generic arbitrary-shell runner, mandatory vault dependencies, a new auth/crypto implementation, account/billing changes, implementation, publication or history rewriting. Sources and public-safe code were checked on 2026-10-30. Actual pinned versions and desktop behavior still require authorized verification.

## Earlier consumer cleanup scope
The original consumer-specific cleanup proposal and checklist were preserved in the private workspace’s historical records on 2026-10-31. This public pair retains the runtime credential-delivery decision and generic safeguards above. Cleanup remains a separate parked use case; no cleanup implementation or real vault operation is authorized by this record.
