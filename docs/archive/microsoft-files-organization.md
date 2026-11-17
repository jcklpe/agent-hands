---
attention: historical
reviewed: 2026-11-17
---
# Microsoft Files organization
Opened: 2026-11-17. Slug: `microsoft-files-organization`. Closed: 2026-11-17.

Historical record. Current commands, safeguards and validation limits belong to [Microsoft Files](../../use-microsoft-files/SKILL.md). This pair records the bounded macOS scope accepted at closure.

## Authorized scope
Extend Microsoft Files with bounded continuation reads, caller-visible sharing/drive ownership and version inspection, same-drive identity-preserving move/rename and recycle-bin deletion. The user resumed this captured work on 2026-11-17. Preserve existing delegated account verification, opt-ins, preview/execute, concurrency and uncertain-outcome controls. Recycle-bin deletion requires separate explicit consent to an itemized list with a brief reason for every file. No permission mutation, cross-drive copy/move, lock bypass or permanent deletion.

The user subsequently authorized live acceptance using disposable files and an unsent reply draft, followed by closure if the tests pass. File deletion required a separate itemized approval, obtained before the two test-file recycle requests. Existing Graph PowerShell authentication and configured capability opt-ins were used without credential or scope changes. Publication remains separate.

## Implemented boundary
Bounded children/permissions/version continuation, drive-owner reporting and same-drive move/rename/recycle are implemented with stored previews, ETag/conflict guards, downloaded content hashes, version lineage, caller-visible sharing comparisons and durable single dispatch.

The authorized macOS disposable-file test passed rename, same-drive move, explicit pagination and readback, collision/stale-preview refusal, server-side stale-ETag rejection, replay refusal and separately approved recycle requests. Live testing exposed and corrected header-free Bash 3.2 transport and equivalent URL-encoding handling in Graph continuation links. Current commands, limits and recovery belong to [Microsoft Files](../../use-microsoft-files/SKILL.md).

Only ordinary files up to 50 MB; verification collections are capped at 2,000 entries/10 pages. Sharing can be caller-filtered, move visibility checks are non-atomic and recycle-bin restorability is unverified. Broader tenant/provider/platform validation and folder mutations remain outside the accepted scope.

## Starting context
The following capture is historical input; its future-work wording does not supersede the implementation authorization above.

# Microsoft Files organization capabilities
Fill the organization and verification gaps in [Microsoft Files](../../use-microsoft-files/SKILL.md): complete bounded folder enumeration with explicit continuation, effective sharing/ownership inspection, version-history inspection, identity-preserving move/rename, and recoverable deletion without purge. Current commands support search, metadata, download, upload, replacement and folder creation, so shared-folder cleanup still needs a connector fallback.

Preserve the configured account guard, explicit targets, preview/execute controls and concurrency checks. Verify moves and renames by cloud item identity, content, parent/name, sharing and version lineage; distinguish applied writes with failed readback from operations known not to have executed. This is a future capability idea, not approval to implement it, change credentials or broaden access.


Folder moves, renames and deletion are deferred: [Microsoft documents](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0) that folder ETags do not change for descendant-derived properties. A preflight empty check cannot guard newly added children, so this extension refuses folder mutations. Folder enumeration and existing folder creation remain available.
