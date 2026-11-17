---
id: GUARD-FILE-WRITES
type: operational
scope: "Agent use or maintenance of Microsoft Files transfers, folders and bounded organization."
status: adopted
authority: "User's Agent Hands policy-pilot approval, 2026-11-02; explicit approval of bounded organization and separate itemized recycle-bin consent, 2026-11-17."
revised: "2026-11-17"
depends_on: ["BOUND-MICROSOFT-ACCESS"]
related_to: ["REJECT-GUESSES"]
---
# Guard Microsoft file writes
Retain per-account file-write opt-in, dry-run plans by default and explicit execution for uploads, replacements and folder creation. The caller must authorize the selected destination/change and understand visibility to other people; the consuming workflow owns shared-record review and permission decisions.

Uploads and folder creation must refuse an existing name rather than overwrite. Replacements retain the current-run ETag condition so intervening changes are refused; version history is recovery, not permission to overwrite silently. Uploads remain within the simple-upload 250 MB cap. Read back name and size against the selected file and retain the ignored local file-write audit record; do not present these checks as stronger content verification than they perform.

Use the delegated access boundary in [BOUND-MICROSOFT-ACCESS](BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md). Files.ReadWrite.All is broader than the native commands, and access remains limited by the signed-in user and selected surface. Each selected account needs its own approved authorization; changing requested scopes is separate setup work.

Same-drive moves/renames and recycle-bin deletion require an exact stored preview, execution opt-in, current identity and ETag checks, conflict refusal and a durable single-dispatch record. Scope organization to ordinary files with bounded content, caller-visible sharing and version checks. Report an acknowledged write with failed readback as applied or uncertain, never as proof that nothing happened, and do not replay it automatically. Moving can change inherited visibility; expose the destination and available permissions before execution. A partial permission view is not proof of the full audience, and recycle-bin retention is not guaranteed recovery. Cross-drive moves, folder organization, lock bypass, permanent deletion, sharing and permission changes remain outside this file surface.

Recycle-bin deletion additionally requires explicit, isolated human consent after every proposed file is itemized with its exact identity, recognizable name/location and a concise explanation of why it should be deleted. Request deletion consent separately from moves, edits and other actions. General cleanup permission, implementation approval, write opt-in or approval of this policy does not authorize deletion. Consent covers only the reviewed files and reasons; changed targets require a fresh review.

Refuse OneNote notebooks and .one/.onetoc2 files rather than treating byte replacement as a supported OneNote edit. Preserve native byte-upload transport without introducing a generic request/raw-token interface.

## Enforcement and procedures
[Microsoft Files](../../use-microsoft-files/SKILL.md) and [Microsoft setup](../../setup-microsoft-services/SKILL.md) own transfer/folder/organization procedures, authentication and executable preconditions. Policy migration does not change those guards or grant a new operation.

## Identity history
This obligation continues the reviewed legacy record [0010](../archive/agent-policy-retirements/0010-lifeos-m365-file-writes.md), retired as an operative document during this authorized migration. Its source text and numeric identity remain reserved; the history link is not an override or automatic authority transfer.
