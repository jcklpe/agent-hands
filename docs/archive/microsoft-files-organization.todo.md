---
attention: historical
reviewed: 2026-11-17
---
# Microsoft Files organization tasks
Opened: 2026-11-17. Slug: `microsoft-files-organization`. Closed: 2026-11-17.

Historical record. Current commands, safeguards and validation limits belong to [Microsoft Files](../../use-microsoft-files/SKILL.md). This pair records the bounded macOS scope accepted at closure. [Scope](microsoft-files-organization.md).

## Done
- [x] Implement explicit bounded collection continuation and honest sharing/ownership/version reads.
- [x] Implement preview-bound move/rename/recycle with identity, content, version and sharing readback and durable no-replay receipts.
- [x] Add synthetic behavior tests and portable guidance; record live-access limits.
- [x] Require itemized deletion reasons and a separate recycle consent acknowledgment; verify generic execution and old previews cannot bypass this gate.
- [x] Complete authorized macOS live acceptance on disposable files, including separately approved recycle requests and independent readback.
- [x] Correct header-free Bash 3.2 transport and equivalent percent-encoding in continuation paths; add focused regression coverage.

## Current state
Bounded children/permissions/version continuation, drive-owner reporting and same-drive move/rename/recycle are implemented with stored previews, ETag/conflict guards, downloaded content hashes, version lineage, caller-visible sharing comparisons and durable single dispatch.

14 stateful organization tests, four actual provider-boundary tests and both existing Files shell suites pass.

Only ordinary files up to 50 MB; verification collections are capped at 2,000 entries/10 pages. Sharing can be caller-filtered, move visibility checks are non-atomic and recycle-bin restorability is unverified. Broader tenant/provider/platform validation is deferred; no required implementation or live acceptance item remains in this bounded scope.

## Live validation
Authorized disposable-file acceptance passed on macOS using existing delegated Graph PowerShell access:
- Folder creation, two synthetic uploads and independent byte-checked download passed. Only synthetic test files were changed.
- Rename and same-drive move preserved item identity, downloaded content, version lineage and caller-visible sharing; independent verification passed.
- A forced one-item children page returned explicit continuation; following it retrieved the remaining item and marked the collection complete. Permissions, versions and drive-owner reads passed.
- Name collision and stale stored previews were refused before mutation. A direct conditional probe returned server precondition failure for a stale file ETag and left the current name/revision unchanged. Replaying a dispatched move was refused.
- Generic execution without the separate recycle acknowledgment was refused. After isolated consent naming both test files and their reasons, each recycle request was acknowledged and independently checked absent from its original parent. This does not prove recycle-bin retention or restoration. The test folder remains in place.

The first live read exposed Bash 3.2's empty-array behavior under nounset; the shared bridge now expands optional headers safely. Graph also normalized an encoded drive-ID character in its continuation URL. Validation now compares decoded path identity but sends the original canonical endpoint, preserving exact-resource and query guards. Regression tests cover both corrections and reject changed collection identities and encoded separators.

The final 30 Python checks (14 organization, 12 draft, four shared transport) also passed in a private copy of committed dependencies with only the selected fixes overlaid. The scoped public-source review found no private account identifiers, source messages, personal paths or credential material in the 12 selected files. Runtime journals are ignored, untracked and owner-only; relative documentation links and workflow-root configuration checks passed. This is a review of this change, not a certification of the repository's entire history.

## Policy and publication
The user explicitly approved the file/mail/access policy amendments on 2026-11-17 and then authorized disposable live acceptance and closure on success. Recycle-bin deletion received a separate itemized approval. No OAuth scopes, account settings or browser sessions changed. Public records contain sanitized scenarios and results; real account/item identifiers, URLs, downloaded fixtures and operation receipts remain in private ignored or external runtime storage. Implementation and acceptance fixes remain local; no additional push is authorized. The shared provider's unrelated error-detail changes and the README's unrelated workstream edits are excluded from these commits.

Folder moves, renames and deletion are deferred: [Microsoft documents](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0) that folder ETags do not change for descendant-derived properties. A preflight empty check cannot guard newly added children, so this extension refuses folder mutations. Folder enumeration and existing folder creation remain available.

## Review details
Final primary-document review required conflict refusal in the URL query and revealed that folder ETags do not protect descendant changes. The implementation uses the documented query and refuses all folder mutations, including currently empty folders. Regression tests cover both decisions. Folder mutation support needs a separately verified concurrency strategy.
