---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0010 policy history
Legacy identity: `0010`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [GUARD-FILE-WRITES](../../agent-policies/GUARD-FILE-WRITES-preserve-explicit-file-targets.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0010-lifeos-m365-file-writes.md`. Exact original SHA-256: `2df9cde07fb95bad08c453cd5484b22ebf3a835d8bedefda28a6e33fb5d139ad`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0010-microsoft-365-file-writes"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="operating-notes"></a>
<a id="links"></a>

````text
# 0010 Microsoft 365 File Writes

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
`bash use-microsoft-files/scripts/files` (path relative to Agent Hands) exposes three write commands behind a per-alias `files.write_enabled` flag:

- **`upload`** puts a new local file into a folder (item ID or `root`, with `--drive` for SharePoint or another user's drive). It refuses when the name already exists (`conflictBehavior=fail`), so it can never overwrite.
- **`replace`** changes an existing file's contents. It sends `If-Match` with the eTag read in the same run, so a file someone changed in between is refused rather than overwritten. OneDrive and SharePoint version history keeps the previous version restorable.
- **`create-folder`** makes a new folder, refusing an existing name.

Every command is dry-run by default and prints the destination path, its current state, and a reminder that others with access will see the change. Executed writes are read back (name and size must match the local file) and appended to the audit log (ignored `file-writes.jsonl` beside the owning Microsoft Files skill, service `m365-files`). Uploads use Graph's simple upload, capped at 250 MB.

Files mode requests `Files.ReadWrite.All`; the CLI’s supported operations are narrower than that delegated permission. Each selected account requires its own authorization.

**Not included:** delete, move, rename, and any sharing or permission change. **OneNote is refused:** notebooks and `.one`/`.onetoc2` files cannot be safely written by replacing files, and a separate OneNote API capability is outside this tool’s surface.

The PowerShell transport gains an `input_file` request field so uploads send raw bytes (`Invoke-MgGraphRequest -InputFilePath`); the MSAL path uses `curl --upload-file`. Neither adds a generic request or raw-token command.

## Rationale
Direct writes allow delivery into shared OneDrive or SharePoint folders that local sync may not contain. The runtime uses delegated `Files.ReadWrite.All`; access remains bounded by the signed-in user's permissions and by the CLI's narrow command surface. Refusing name conflicts and using ETag-guarded replacement avoid silent overwrite.

## Operating Notes
- Shared records may be visible to other people; the caller must authorize the selected destination and change.
- The consuming workflow owns shared-record permissions and any per-change review policy.
- Changing requested scopes requires an approved interactive authorization through `setup-microsoft-services`.

## Links
- [0004 LifeOS Microsoft 365 Access](0004-lifeos-microsoft-365-access.md)
- [0006 Writes Fail Rather Than Guess](0006-writes-fail-rather-than-guess.md)
- [0008 LifeOS Microsoft 365 Planner](0008-lifeos-m365-planner.md)
- [use-microsoft-files skill](../../use-microsoft-files/SKILL.md)
````
