---
attention: live
status: parked
implementation: not-started
parked_date: 2026-10-31
created: 2026-10-31
reviewed: 2026-10-31
---
# Secret-safe vault inspection and cleanup planning
[Deferred exploration tasks](bitwarden-vault-inspection.todo.md). **Parked on 2026-10-31 at the user's request.** Preserve this existing reusable-tool scratch spike for later; do not start implementation, account access, vault inspection, exports or changes. The architecture below remains a hypothesis. Resume only when the user asks; this capture creates no reminder or scheduled follow-up.

## Who produces a safe summary
Ordinary trusted local code produces the findings. It reads the selected vault material inside its own processing boundary, compares fields deterministically and serializes an allowlisted result. An LLM does not read the raw items, redact them or summarize them first: that would already put their secrets into model context. The model may help explain or prioritize only the approved limited findings after processing.

Even the limited findings disclose information. A duplicate group or equality flag reveals a relationship between items; metadata such as names, usernames, domains and timestamps can reveal private activity. The permitted output must be deliberately selected, not called safe merely because a password field was removed. Default to fixed finding codes, coverage flags, equality/conflict booleans, bounded counts and run-scoped opaque references. No vault-supplied free text crosses that boundary by default.

## Proposed ownership
| Owner | What belongs there | What does not belong there |
| --- | --- | --- |
| Agent Hands | This generic exploration; potentially a reusable deterministic inspection/minimization component, synthetic fixtures, version/coverage rules, safe result contract and optional CLI/MCP adapter. | Real vault items, secret-bearing snapshots, personal account identities, private cleanup plans, consumer preferences or actual approval history. |
| Personal planning context | Non-secret project goals, process decisions and references. LifeOS may hold a sibling planning note only. | Password records, exports, item-level findings/manifests and secret-bearing processing/recovery artifacts. These stay in Bitwarden or the separately protected local tool boundary, outside LifeOS. Do not duplicate the reusable implementation tracker. |
| Human | Chooses actual cleanup actions and approves concrete mutations after reviewing exact scope through a private native surface. | The model must not infer that a finding or an old timestamp authorizes deletion. |

The Bitwarden password vault and the LifeOS document vault are distinct. LifeOS is a planning context, not a store for password-vault contents or tool working data. The proposed split is reusable tooling in Agent Hands and non-secret personal project planning in a private document context. The tool hypothesis remains unimplemented. An MCP interface alone does not determine ownership or make raw data safe.

This pair owns the reusable-tool exploration only. The requested private planning sibling is separate; it contains no password records, exports or secret-bearing data and is not linked from this public repository. Both cleanup planning workstreams are parked. A later implementation agent/thread may take up scoped tooling work only when the user resumes it; no personal details or private context are imported here.

## Relationship to the selected runtime-credentials spike
The [Bitwarden runtime-credentials spike](bitwarden-capabilities.md) records the selected Secrets Manager Free plus official `bws` scope for service credentials. This inspection work concerns the Password Manager vault and does not extend, delay or change that decision. It does not make `bw` or the official password-vault MCP a dependency of the `bws` integration.

The generic relationship is credential-handling discipline and optional interface reuse. Do not copy real vault material into the service-credential plan, move personal vault items into Secrets Manager as cleanup, or treat runtime integration approval as inspection/export/mutation approval. No private LifeOS links or filesystem paths belong in this public record.

## Architecture hypothesis
The proposed flow is: selected official vault source → trusted local reader/comparator → validated allowlisted findings → optional model explanation or human review. Raw responses, private manifests and recovery material remain inside the local private processing boundary. There is no raw-output fallback on unsupported data or failure.

The reader may invoke official `bw` internally or use an isolated client of the official Bitwarden MCP server. In the stock server, `list` and `get` forward CLI output into MCP results, including the requested sensitive fields; registering those tools directly with the model would defeat this boundary. A private client can consume their responses without forwarding them, but must also suppress raw logs and errors. [Official handler source](https://github.com/bitwarden/mcp-server/blob/main/src/handlers/cli.ts), [tool definitions](https://github.com/bitwarden/mcp-server/blob/main/src/tools/cli.ts).

MCP is optional. A future Agent Hands inspection tool could return the same safe schema through MCP or a CLI while the processor remains ordinary local code. Do not add a generic `get`, export, arbitrary filter expression, output template or shell escape hatch to that safe surface. In particular, do not expose a chosen-value comparison oracle that lets the model probe secret guesses through equality results.

For any future real use, preserve the established native-desktop interaction and no-human-terminal requirement. Native login/unlock and session ownership still need a separately scoped design. The existing official MCP native unlock is a reusable candidate, not proof that account setup, raw-output isolation or recovery are solved.

## Output contract to investigate
| Output | Default boundary |
| --- | --- |
| Fixed finding codes | Locally generated enumerations such as `POSSIBLE_DUPLICATE`, `CONFLICT_REQUIRES_REVIEW`, `INCOMPLETE_COVERAGE`; never vault text, source exceptions or model-written summaries of raw data. |
| Equality/conflict flags | Only approved comparisons over the selected set, computed locally; not a password, hash, fingerprint, prefix, length trace or guessed-value oracle. |
| Item/group references | Random/run-scoped opaque aliases. Keep the mapping to exact source IDs and observed revisions in a private local manifest; expire/invalidate plans when its scope or source changes. |
| Coverage/counts | Bounded, deliberately approved information that states what was inspected and what remains unknown. A partial read must not be reported as a complete vault audit. |
| Names, usernames, domains, dates and other metadata | Omitted by default. Add a field only after deciding its necessity and private exposure policy; it may itself contain a password, prompt injection or unrelated sensitive text. Approval of a field name alone does not establish safe contents: prefer locally derived categories and keep unconstrained strings in the private human view. |
| Native human detail view | If necessary, the human inspects exact records in a private native surface; do not relay those contents through screenshots, accessibility reads, logs or model-visible tool responses. |

Never return actual passwords, TOTP codes or seeds, recovery codes, secret keys, notes, custom-field values, passkey material, attachment contents, raw item JSON, raw credential hashes or unsanitized errors to the model. Excluding top-level password fields is insufficient: any free-text field can contain a secret. Permit only known safe output types and constant codes; refuse unknown fields or malformed responses rather than serialize them.

A local comparator may use internal fingerprints for grouping if justified, but does not output them. It must verify equality before an exact-duplicate finding and avoid declaring equality from a digest alone. Opaque aliases are identifiers, not a substitute for comparisons. No secret-derived persistent identifier should leak across reports by default.

## Exact duplicates, conflicts and preservation
Separate possible grouping from equality. Similar names, a shared domain or a matching username can propose a local comparison group; none proves the items are interchangeable. Different accounts, tenants, URI match modes or shared-vault ownership must not be collapsed. Do not trim, case-fold or otherwise normalize passwords/seeds to make them equal. Any metadata canonicalization must be explicit and non-destructive.

An exact-content candidate needs a documented complete semantic comparison with coverage known. Differences in passwords, TOTP configuration, notes, custom fields, URIs/match modes, ownership/collections, attachments, passkeys, SSH material, password history or unknown extension fields make it a conflict or an indeterminate case. Equivalent content still does not make deletion automatic: IDs, references and history can matter independently. If attachment bytes or other fields cannot be checked, report incomplete coverage and preserve both items.

A merge must preserve every original field and its provenance, attachment, passkey, history entry and ownership boundary. The first implementation proof should be inspection-only; do not build item replacement from a lossy normalized record. A later write design needs before/after validation, stale-source checks and a field-by-field preservation matrix. If the official interface cannot preserve a component, refuse that merge and leave the originals intact.

Age is not evidence of non-use. An old creation/change timestamp, an old password or lack of a recent field update does not prove a login is unused. Any retirement requires independent private human judgment; do not generate `UNUSED` or delete recommendations from age alone.

## Recovery and mutation boundary
Read/inspect, export/backup and mutate are distinct actions with distinct scope. This exploration authorizes none of them against a real vault. Before any later mutation, produce a concrete private plan tied to the exact account, item IDs, observed revisions, changed fields and recovery artifacts; obtain human approval for that plan. A safe finding, broad cleanup goal or successful read is not mutation permission.

Design recovery before writes: protected backup format/destination, key/password ownership, coverage of personal versus organization items, attachment bytes, passkeys and history, restoration semantics, retention and access. Verify recoverability with synthetic data instead of assuming that an export is a complete round-trip backup. Current documentation distinguishes export formats/coverage, including attachment-capable ZIP and JSON passkeys, and encrypted-export restrictions. Recheck chosen versions and formats before relying on them. [Export coverage](https://bitwarden.com/help/export-your-data/), [encrypted export types](https://bitwarden.com/help/encrypted-export/).

Do not default to a plaintext whole-vault export merely to inspect duplicates. Keep raw transient data out of repository, model transcript, command arguments, stdout/stderr, crash dumps and debug logs as far as the chosen process boundary can enforce; document limits rather than promise memory erasure. Permanent deletion and automated conflict resolution are outside the initial scope. A failed/uncertain mutation must stop, report a fixed status and require actual-state inspection before retry, preserving verified prior steps and the recovery record.

## Proof before implementation or real access
The hypothesis needs an offline synthetic test corpus and a native/UI feasibility review in a future authorized implementation. Tests must cover secret-bearing values hidden in every field, injection-looking names/notes, malformed/oversized input, unsupported fields/versions, exact duplicates versus conflicting accounts, attachments/passkeys/history, stale plans and transport errors. Use only fabricated records; never derive public fixtures from a real vault.

Leak tests should locally check secret markers and known encodings/hashes across every model-visible output, protocol frame, exception/log path and preview; report only test status. Positive fixtures must show useful safe findings, not just suppress everything. Offline success does not establish real account permissions, native prompt isolation, full vault coverage, recovery or a boundary against unrestricted same-user shell access. Trusted code and its execution permissions remain part of the design.

## Non-goals and current state
This is parked exploratory architecture and ownership planning. It selects no implementation language, new executable/skill name or MCP registration. No code, fixtures, vault reads, exports, passwords/tokens, installation, client changes, mutations, commits or pushes were performed. No actual cleanup target, item-level plan or vault data is present here or in the LifeOS planning sibling. Secrets Manager runtime delivery remains the separate selected workstream, unchanged by this capture.
