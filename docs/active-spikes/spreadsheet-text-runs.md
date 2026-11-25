---
attention: live
---
# Spreadsheet text runs
Implement a bounded Excel Office.js text-run capability and evaluate local spreadsheet engines on disposable fixtures. The user authorized this work on 2026-11-24, including installing GridCraft CLI and testing the installed Nextcloud Office. Strikethrough is optional; red original and green proposed text remain the review convention. The November 25 user-approved extension adds bounded layout and reference repair, tested on disposable workbooks before use on existing shared files. Consumer-specific inputs and results remain private.

ExcelApi 1.18 documents RangeTextRun, getCellProperties and setCellProperties. The existing Excel CLI is Graph-based; a working Excel Office.js transport must be established rather than claiming an existing bridge was extended. Reuse the owned Office browser's identity checks and single-dispatch recovery. Never clear the cell or replace the cloud package to implement rich text. Formula and non-text cells must refuse.

Nextcloud Office's bundled Document Builder passed a disposable local edit, save, reopen and render test. It preserved colored text, formulas, tables and links, but migrated legacy notes to threaded comments and compatibility notes. That comment-storage change requires acceptance before using it on shared review files. GridCraft CLI 0.19.1 was installed from the official matching release with its published SHA-256 verified. A synthetic XLSX round trip retained a formula, table, comment and hyperlink but flattened colored text runs. Its own check reported no round-trip differences; independent inspection is required. This version is not selected for saving rich-text review workbooks.

[Tasks](spreadsheet-text-runs.todo.md).

The extended native route supports explicit tab order/colors, frozen headers, existing table styles, finite cell formatting and same-origin reference repair. Compact per-range SHA-256 snapshots keep large read-only previews within the bridge response bound. Saved-file checks preserve values, formulas, tables, comments and unrelated cells; native visual acceptance remains separate. The character-font reader distinguishes a missing run-font element from explicit run properties whose omitted toggles default off. A regression rejects a genuinely introduced strikethrough while accepting Excel’s equivalent serialization.
