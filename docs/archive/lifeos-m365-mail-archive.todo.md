---
attention: historical
---
# LifeOS Microsoft 365 Mail Archive — To Do
Historical record. Closed 2026-11-21 after approval of closure and the complete archival wording. Slug: `lifeos-m365-mail-archive`. Maintained commands and safeguards belong to [Use Outlook Mail](../../use-outlook-mail/SKILL.md), [Use Gmail](../../use-gmail/SKILL.md) and the [adopted mail policy](../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md). Representative live round trips and delegated visual filing QA passed; optional Archive export, cap tuning and consumer triage remain separate.

The retained development entries describe their dated checkpoints; pending statements below are historical.


Privacy separation (2026-11-02): consumer-specific passages and actual account-validation chronology were preserved privately before removal from this public record. Portable requirements, recorded tooling evidence and stable slugs remain; historical instructions below are not current operating guidance.

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-m365-mail-archive.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-gmail](../../use-gmail/SKILL.md), [use-outlook-mail](../../use-outlook-mail/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.



Concept and design: [lifeos-m365-mail-archive.md](lifeos-m365-mail-archive.md). Scope widened 2026-09-29 to Gmail archive and labels plus M365 folders.

## Current State
- Implemented 2026-09-29: M365 folders, list, archive, unarchive, move, create-folder; Gmail labels, list, archive, unarchive, label (`--skip-inbox`), unlabel, create-label. Policy 0007 written, 0004 amended, skills and README updated, offline tests added.
- Representative Microsoft 365 and Gmail filing round trips have live readback evidence. Account identities, configuration decisions and consent chronology are retained privately; this is not a claim about every configured account.

## To Do
### Phase 0 — Feasibility
- [x] Verify effective delegated mail-write access before the approved live filing check. Recorded account-specific feasibility and consent evidence is retained privately.

### Phase 1 — Decision
- [x] `docs/policies/0007-mail-archive-and-labels.md` amends 0004 and covers Gmail; rejected alternatives recorded. 0004's mail bullet points to it.

### Phase 2 — Command
- [x] M365 `mail folders`, `mail list`, `mail archive`, `mail unarchive`, `mail move`, `mail create-folder`: dry-run default, exact IDs, source rules, refused targets, cap of 50, Graph `$batch`, readback under the new ID.
- [x] Gmail `labels`, `list`, `archive`, `unarchive`, `label [--skip-inbox]`, `unlabel`, `create-label`: user labels only, Trash/Spam refused, readback.
- [x] Shared ignored audit log `lifeos-tools/secrets/logs/mail-writes.jsonl`.
- [x] Opt-in flags `mail.write_enabled` / `gmail.write_enabled` in ignored account configuration; public examples default to false. Each account’s enablement and consent are separate setup decisions.
- [x] Offline tests: `lifeos-tools/tests/test-mail-triage.sh` (synthetic mailbox; mutation-checked against the refused-target list, `--skip-inbox`, and readback). Full suite green.

- [x] Spam and junk review (the user, 2026-09-29): `gmail spam` / `not-spam` and `m365 mail junk` / `not-junk`. Rescue runs only out of Spam or Junk, and there is no report-spam. Live listings and a not-spam dry run with refusals were verified on personal and the managed tenant. No live not-spam was executed, because the CLI cannot re-spam a message. Offline tests added; 0007 addendum.

- [x] Preserve per-account service opt-in; selecting Drive does not enable Gmail. Individual account decisions and their validation evidence are private consumer context.

### Phase 3 — Docs
- [x] `lifeos-m365`, `lifeos-gmail`, and `lifeos-cli` skills; README commands and prose; `lifeos help`.
- [x] Document Inbox-only export coverage: mail filed outside the Inbox is absent from that view. Workspace-specific assumptions and metadata conventions belong to the consumer.

### Phase 4 — QA
- [x] M365 live round trip, 2026-09-29: one selected Inbox message archived (confirmed by readback), then unarchived back to the Inbox under its new ID. Folder refusals and source rules exercised live.
- [x] Complete the approved Gmail filing authorization before live operations; exact account chronology is retained privately.
- [x] Representative Gmail filing round trip, 2026-09-29: archive, unarchive, label with skip-inbox, unlabel and restore. Each step was confirmed by readback and the original labels, including unread state, were preserved. Exact account execution context is retained privately.
- [x] Verify the selected Gmail account identity and required filing scope after authorization; account-specific evidence is retained privately.
- [x] Verify account identity after interactive authorization. Re-running authorization for the same alias replaces its token file, so verify the resulting profile against the selected account before using it. The account-specific execution chronology is retained privately.
- [x] Verify another approved Gmail archive/unarchive round trip with readback and preserved original labels. The account-specific authorization and timing are retained privately.
- [x] Human QA by the user: spot-check Outlook and Gmail after a real triage pass. Completed as delegated agent visual QA on 2026-11-20 under the user's request to perform the checks independently; this is not a claim of new user visual confirmation.

## Open Questions
- Optional Archive-folder export remains a caller-driven possibility, not an implemented extension or a requirement for this scope.
- Is the per-call cap right at 50?
- Consumer triage policy and its approval model are outside this tooling scope. Follow the consuming workspace’s maintained procedure.

## Ready For Human QA
- No UI filing check remains for the representative scope. Native readback and delegated visual QA agree; full archival wording review remains.

## Done
- [x] Spike sketched and promoted to active (2026-09-29).
- [x] Implementation, decision, docs, tests, M365 live QA (2026-09-29).

## Delegated visual filing QA — 2026-11-20
- Matched one earlier successful Outlook archive receipt to the current message in Archive. Its identifier, folder, category and read state agreed with fresh CLI metadata; Outlook web showed the archived conversation member and preserved category. The selected message was already read.
- Matched one earlier successful Gmail label-with-skip-inbox receipt to its current thread. Native readback showed the expected user label, no Inbox label and preserved unread state. Gmail search visually showed that label and the unread result; the message was not opened.
- These were read-only spot-checks of real prior filing operations. No new archive, label, read-state change, deletion or grant was performed for this QA. Actual message/account details, private audit rows and UI captures stay outside Git. Representative evidence does not establish every account or client.
