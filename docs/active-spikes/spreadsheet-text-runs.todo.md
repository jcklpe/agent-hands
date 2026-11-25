---
attention: live
---
# Spreadsheet text runs tasks
## Remaining validation
- Additional tenants, native desktop Excel acceptance and Windows/Linux remain outside the macOS web tests.
## Done
- [x] E1 Implement bounded Office.js text-run read/write with expected-content checks and actual host testing. Completed the experimental CLI and 16 adapter/bridge/readback checks. Actual ExcelApi 1.18 reads and one guarded write passed on a disposable cloud workbook. Independent downloaded inspection confirmed effective red/green colors and unchanged fixture cells, formula, table, comment author/text and hyperlink. Initial verification missed inherited cell-font color; fixed the reader, added a regression test and reconciled without repeating the write. A reopened Excel view showed the saved red/green wording, the formula result and no repair banner. New-workbook setup remains an explicit one-time add-in step; automatic startup is off.
- [x] N1 Test Nextcloud Office text-run editing and save/reopen preservation on a disposable workbook. Headless native library edit, save, reopen/resave and PDF rendering passed. Independent reads verified mixed colors, formula, table, hyperlink and second sheet. Legacy note converted to threaded comment plus compatibility note; exact comment storage was not preserved. See the [experiment](../../experiments/nextcloud-spreadsheet/README.md).
- [x] G1 Install matching GridCraft CLI and evaluate rich-text preservation. Official 0.19.1 checksum verified; existing ~/.local/bin PATH route used. Independent inspection found lost rich-text runs despite its own successful round-trip check. Do not use for redline saves.
- [x] C1 Post the requested current API documentation on OfficeDev/office-js#4623. Comment 7142966696 posted and independently read back; acknowledges the existing implementation announcement and distinguishes documentation from runtime testing.

- [x] E2 Extend native layout and reference commands after user approval. Disposable tests and saved checks passed; authorized shared reference repair passed for 75 cells with effective character formatting, formulas, tables, comments and unrelated cells preserved. Layout changes passed independent saved-file checks. Native visual review remains an explicit consumer acceptance step.
- [x] E3 Add regression coverage for explicit run-font toggle defaults and compact large-range preview snapshots. The combined Excel/Word suite passes 68 checks; four disposable browser checks pass.
