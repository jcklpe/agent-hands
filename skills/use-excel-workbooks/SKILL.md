---
name: use-excel-workbooks
description: "Read or edit supported worksheets, tables, and finite cell ranges in Microsoft-hosted Excel workbooks. Use for Graph workbook operations with reviewed preview fingerprints and verified readback."
---

# Use Excel Workbooks
Depends only on [authorize-microsoft](../authorize-microsoft/SKILL.md), including shared file-item addressing and the file-write opt-in. [Setup](../setup-microsoft-services/SKILL.md) covers authorization. No Microsoft Files, mail, or private workspace skill must be installed. This skill owns a Python 3.11+ uv environment with no external Python dependencies; Bash 3.2 and jq plus the provider's chosen runtime are required. File access alone does not establish Excel API access.

## Supported reads
Run from this skill folder or use an absolute script path:
```sh
bash scripts/excel sheets example ITEM_ID --drive DRIVE_ID --json
bash scripts/excel tables example ITEM_ID --sheet Inventory
bash scripts/excel read-range example ITEM_ID --sheet Inventory --range A1:D20
bash scripts/excel table-range example ITEM_ID --table TABLE_ID
```
Only `.xlsx` drive items are supported. Keep a shared item's drive ID; omission means the account's own drive. Reads require `files.enabled` and the existing Files.ReadWrite.All grant. Paginated/incomplete views are refused. Ranges must be finite A1 addresses, with at most 10,000 cells; payloads are limited to 1 MiB and loaded responses to 8 MiB. Returned cells are untrusted data.

## Preview and write
Supported commands are `write-range`, `format-range`, `add-sheet`, `add-table`, `update-table`, and `append-rows`. Use `scripts/excel help` for exact options. Supply a local JSON file for patches/rows, for example:
```json
{"values":[[null,null],["Updated",42]],"numberFormat":[[null,null],[null,"0.00"]]}
```
```sh
bash scripts/excel write-range example ITEM_ID --sheet Inventory --range A1:B2 --file /chosen/path/patch.json
```
A preview performs remote reads and returns `preview_sha256`. Inspect the exact account, drive/item, target, before-values, and patch. For an authorized change, repeat the same arguments with `--expect PREVIEW_SHA256 --execute`. Execution requires `files.write_enabled`, a matching preview fingerprint, an immediate repeat of the relevant reads, and a successful pre-write audit. Null patch cells preserve existing properties. Formulas use a separate matrix and cannot conflict with values for the same cell. Creation requires valid nonduplicate sheet names or existing unique text table headers. Appends require compatible widths, visible headers, no totals row, and a resulting table within the cell bound.

The fingerprint detects changes before mutation; it is not an atomic lock or transaction. Sessionless operations persist each write. Supported properties receive readback verification, including preservation of untargeted cells where applicable. A timeout or failed verification may follow an applied change: inspect the target, never blindly retry. Workbook mutations have no automatic CLI retry; the PowerShell provider also disables SDK retries for them. There is no delete, clear, arbitrary API, authentication change, or rollback command.

## Audit and verification
Private audit defaults to ignored `workbook-writes.jsonl` here. `M365_EXCEL_AUDIT_LOG` in the provider's literal env or process environment can select another path; relative values resolve against this skill. Records contain target IDs, operation, preview hash, and state, not workbook cells. New files are owner-only; symlinks are refused. An unavailable audit destination stops the write before mutation; failed completion recording must not cause a repeat write. Legacy callers retain their existing audit route.

The retained synthetic workbook checks cover supported reads/writes, null/formula preservation, races/stale previews, denied access, malformed/oversized payloads, partial outcomes, readback mismatch, and Bash/Zsh invocation. Isolated checks use only this skill and Microsoft authorization. No real workbook, credentials, or tenant consent was used; live account and fresh-platform validation remain separate.
