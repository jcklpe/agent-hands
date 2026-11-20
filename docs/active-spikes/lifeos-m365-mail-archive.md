# LifeOS Microsoft 365 Mail Archive

Privacy separation (2026-11-02): consumer-specific passages and actual account-validation chronology were preserved privately before removal from this public record. Portable requirements, recorded tooling evidence and stable slugs remain; historical instructions below are not current operating guidance.

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-m365-mail-archive.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-gmail](../../use-gmail/SKILL.md), [use-outlook-mail](../../use-outlook-mail/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

Status: active, opened 2026-09-29 at the user's request.

## Purpose
Provide reversible mail filing through bounded native commands, so callers can archive exact messages or threads and organize them with supported folders or labels.

the user's framing (2026-09-29): archiving is reversible, so it is low-stakes, and it removes work he currently has to do by hand.

**Scope widened the same day (2026-09-29, the user):** besides Microsoft 365 archive, (1) archive for every Gmail account, (2) Microsoft 365 folder listing and filing into folders, and (3) Gmail's equivalent, user labels that can skip the Inbox. Deletion stays out everywhere. The slug stays `lifeos-m365-mail-archive` so commit trailers remain continuous. The in/out lists below are the widened scope; the original design sketch is kept beneath them, with notes where the build departed from it.

## Current Policy and Historical Starting Point
The access rule before this spike kept mail strictly read-only. The implemented filing capability is now governed by [BOUND-MAIL-WRITES](../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md) and the current [BOUND-MICROSOFT-ACCESS](../agent-policies/BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md). As of 2026-10-14, those policies consolidate the current boundaries directly; later standing rules are governed by [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md). The implementation scope and design sketch below retain the starting point rather than limiting all later mail capabilities.

## Scope of the September 29 Implementation
In:
- Microsoft 365: `mail folders`, `mail list --folder`, `mail archive` (Inbox to Archive), `mail unarchive`, `mail move --folder`, `mail create-folder`.
- Gmail: `gmail labels`, `gmail list`, `gmail archive`, `gmail unarchive`, `gmail label [--skip-inbox]`, `gmail unlabel`, `gmail create-label`.
- Dry-run by default, `--execute` to act, exact IDs only, readback, per-call cap of 50, a local audit log, and a per-account opt-in flag.

Outside that initial implementation: send, reply, forward, delete, trash, spam, mark-read, flag, moves into Deleted Items / Junk / Drafts / Sent / Outbox (or their subfolders), Gmail system labels, folder or label rename and delete, and rules or filters.

## Design Sketch
- **Graph call:** `POST /me/messages/{id}/move` with `{"destinationId": "archive"}` (a well-known folder name). The move returns the message under a **new ID**; the command must print and log the new ID so `unarchive` can find it.
- **Targeting:** messages are chosen by exact Graph message ID obtained through a bounded read or explicit export. No search-based or "archive everything matching X" command in the first version, in the spirit of [REJECT-GUESSES](../agent-policies/REJECT-GUESSES-stop-writes-with-unknown-critical-values.md).
- **Guardrails:** only messages currently in the Inbox; a per-call cap (for example 50); refuse any ID not found, rather than skipping silently.
- **Audit log:** each executed move appends a line (timestamp, alias, old ID, new ID, sender, subject) to a gitignored local log beside its owning Gmail or Outlook Mail capability. Mail content never enters this public repo.
- **Export coverage:** an Inbox-only export omits archived mail. A caller needing other folders must select an appropriate supported read/export; filing does not define that caller’s retained context.

## As Built (2026-09-29)
- **Transport:** every Graph call through PowerShell costs about two seconds, so all per-message work (lookup, move, readback, child-folder listing) goes through Graph JSON `$batch`, 20 requests per call.
- **Folder resolution:** a well-known name, an exact ID, a full path like `Inbox/Receipts`, or a unique display name. Ambiguity fails. The folder tree is walked through `childFolders`. Hidden folders are not listed.
- **Refused targets:** Deleted Items, Junk, Drafts, Sent, Outbox, recoverable items, and everything under them, computed from well-known IDs plus parent links.
- **Source rules:** `archive` requires Inbox; `unarchive` requires Archive; `move` accepts any source. Messages already in the destination fail the call.
- **Gmail** uses `messages/batchModify` for message targets and `threads/{id}/modify` for threads; readback checks every affected message's labels.
- **Opt-in flags:** `mail.write_enabled` switches `Mail.Read` to `Mail.ReadWrite`; `gmail.write_enabled` adds `gmail.modify`. Dry runs and reads work without them.
- **Audit log:** the owning capability’s ignored `mail-writes.jsonl`, separate for Gmail and Outlook Mail, recording old and new IDs.
- **Maintained guidance:** [BOUND-MAIL-WRITES](../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md) owns mail filing; [BOUND-MICROSOFT-ACCESS](../agent-policies/BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md) owns the current access boundary.

## Auth
Moving mail needs the delegated `Mail.ReadWrite` scope instead of `Mail.Read`. Gmail filing requires `gmail.modify`. Verify the selected account’s effective access through its setup owner; recorded live checks do not establish another account’s consent.

## Where Judgment Lives
This repository owns filing mechanics and safeguards. Consumer workflows own relevance judgments, triage procedures, selected account policy and approval decisions. A tooling spike does not create or change those consumer policies.

## Related
- [BOUND-MICROSOFT-ACCESS](../agent-policies/BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md): current delegated access and capability boundaries.
- [REJECT-GUESSES](../agent-policies/REJECT-GUESSES-stop-writes-with-unknown-critical-values.md): writes fail rather than guess.
- `docs/archive/lifeos-m365.md`: the original M365 spike and the tenant authorization findings.
- `agent-hands/use-outlook-mail/` and `setup-microsoft-services/`: current command and transport owners.
