---
attention: live
status: parked
implementation: not-started
parked_date: 2026-10-31
created: 2026-10-31
reviewed: 2026-10-31
---
# Secret-safe vault inspection — exploration tasks
[Concept and ownership hypothesis](bitwarden-vault-inspection.md). **Parked on 2026-10-31 at the user's request.** Retain the existing exploration for later; all tasks below are deferred, not active work. Resume only when the user asks. No implementation, account access, reminder or scheduled follow-up is authorized by this capture.

## Current state and organization
Agent Hands holds the reusable deterministic inspection/minimization hypothesis. A separate private LifeOS sibling holds only non-secret personal project planning. The Bitwarden password vault and LifeOS document vault are distinct: password records, exports, item-level findings/manifests and secret-bearing processing/recovery artifacts do not belong in LifeOS. This pair stays parked in scratch; no skill is installed or implemented.

The [selected Bitwarden runtime plan](bitwarden-capabilities.md) remains Secrets Manager Free plus official `bws`. These tasks neither extend that scope nor require its runtime implementation to take on Password Manager access. The private planning sibling may reference this tooling work, but actual vault data stays in Bitwarden or the tool's separately protected local boundary, outside LifeOS.

## Deferred exploration — only when the user resumes
- [ ] Validate the proposed ownership: identify the genuinely reusable inspection contract and leave consumer-specific cleanup policy private. If a reusable component is unwarranted, record that conclusion rather than building a public framework.
- [ ] Define the minimum selected-item input/coverage model and strict output allowlist: constant finding codes, approved equality/conflict flags, bounded coverage/counts and run-scoped opaque aliases only. Default to no names, domains, usernames, dates or other source text.
- [ ] Define private alias-to-source-ID/revision manifest ownership and plan invalidation rules without placing actual IDs, paths, item values or private account history in these public docs.
- [ ] Decide the trusted reader boundary: internal official `bw` versus an isolated official-MCP client. Document that stock model-facing `list`/`get` forwards raw CLI output and cannot serve as the safe result surface. MCP transport is optional.
- [ ] Define native desktop login/unlock/session/cancel/recovery needs with no human terminal. Reuse supported official functionality where possible without treating it as proof that initial login or safe processing is solved.
- [ ] Specify complete semantic equality, possible grouping, conflict and incomplete-coverage rules. Do not infer exact duplicates from names/domains, a hash alone, or a normalized password; do not infer non-use from age.
- [ ] Define preservation requirements for every original field, URI/match mode, owner/collection, attachment byte, passkey, SSH material and history entry. Unknown or unreadable components must block equivalence/merge claims.
- [ ] Design the private human review and later approval contract for exact targets/fields/revisions and recovery. Separate permission to inspect, export and mutate. Do not treat a safe finding as action approval.
- [ ] Investigate version-specific backup/export/restore coverage with public documentation and future synthetic restore tests only. Include encryption/key ownership, attachments/passkeys/history, protected location/retention, organization boundaries and uncertain outcomes; no real export now.
- [ ] Decide whether to open a scoped implementation continuation once the architecture is reviewed. No code, native registration, credentials or real-vault operation from this scratch exploration alone.

## Future offline proof — acceptance criteria, not work performed
| Area | Required evidence before any real-vault trial |
| --- | --- |
| Deterministic producer | Trusted local code reads/compares fabricated records and produces fixed findings. No LLM prompt receives raw source data for summarization/redaction. |
| Output schema | Unknown keys/types/source strings cannot be emitted; fixed safe failures replace raw exceptions/vendor output. Metadata is omitted unless deliberately approved. |
| Secret leakage | Fabricated password/TOTP/seed/key/note/custom-field/passkey/attachment/history markers and tested encodings/hashes are absent from model-visible results, logs, protocol frames, stderr, previews and error paths. Scans emit pass/fail only. |
| Useful findings | Clearly exact synthetic pairs produce the intended flags; conflicting or incomplete pairs remain distinct and require review. Same domain with different usernames/secrets never becomes an automatic merge. |
| Identifier boundary | Output contains only run-scoped aliases and deliberately permitted relations; source IDs/revisions/private mapping and secret-derived hashes do not leak. No arbitrary guessed-value comparison oracle. |
| Preservation | Test records cover attachment bytes, multiple/custom fields, URI modes, passkeys, history, ownership and unknown future fields. Unsupported/lossy inputs cannot produce an exact/merge-safe finding. |
| Untrusted and malformed data | Injection-looking names/notes, secrets hidden in metadata, escaping/newlines, malformed/oversized data and raw transport errors remain local and produce bounded fixed statuses. |
| Scope and coverage | Partial/paginated/failed reads are marked incomplete. No permission expansion, whole-vault fallback, implicit export or live network read in offline tests. |
| Plans and stale state | Changed account/set/revision or expired manifest invalidates a later plan; no action is authorized solely by a finding. |
| Recovery proof | Synthetic backup/restore exercises show exactly what is recoverable and what is missing. No completeness claim from export existence; no irreversible/permanent-delete route. |
| Native UX and trust limits | Future synthetic native proof checks login/unlock/cancel/recovery without human terminal. Document the trusted-code boundary and limits against unrestricted same-user shell/process access. |

Use fabricated fixtures only, including secret-like strings in every source field. Positive/negative leakage assertions must not print the captured offending value on failure. A fixture test is not live vault access, a successful restore or proof of model isolation in every desktop host.

## Future live inspection and mutation boundaries
- Real inspection, if later requested: approve the account, selected item scope, metadata/result disclosure, native interaction and session/state handling; read only those targets. Keep raw results/manifests private and out of model context.
- Export/backup, if later requested: approve exact coverage, format/destination, key handling and retention separately; do not use a blanket export as the default inspection input.
- Mutation, if later requested: approve a concrete private plan after validated recovery, exact before/after preservation and stale-source checks. Initial tooling proof is inspection-only. No permanent deletion or autonomous conflict resolution.
- Uncertain execution: stop the affected action, preserve private evidence, emit a fixed safe status and verify actual state before retry. Do not blindly repeat a write or claim rollback without verification.

These are design boundaries for future work, not authorization to perform any listed live action. For this project, LifeOS holds non-secret planning/process decisions only; item-level vault records, findings/manifests, exports and secret-bearing recovery artifacts stay outside LifeOS and this public tracker.

## Parked — no active review or implementation
The reusable-tool hypothesis and its limited-output design are saved for later. The sibling private note concerns personal project planning, not storing password-vault contents in LifeOS. No implementation/native/account QA is ready or claimed; no follow-up date, reminder or external task has been created.

## Done — this documentation pass
- Checked the current Agent Hands instructions, pinned spike procedure, existing scratch pair and index; found no separate current vault-inspection spike to duplicate.
- Created this distinct exploratory concept/task pair; preserved the selected `bws` runtime plan and limited the relationship to a generic public link.
- Recorded the hypothesis that ordinary local code, not a model, produces allowed findings, with metadata limits, raw-output refusal and optional private MCP consumption.
- Captured equality/conflict/coverage rules, preservation, native UX, synthetic acceptance criteria and future approval/recovery boundaries. No code, fixtures, installs, vault reads, exports, credentials, mutations, commits or pushes.
- 2026-10-31: corrected the password-vault versus document-vault distinction and parked this existing pair at the user's request. The private sibling is project planning only; neither LifeOS nor this public pair receives password records or tool working data. No duplicate Agent Hands spike or reminder was created.
