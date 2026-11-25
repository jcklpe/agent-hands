# Nextcloud Office spreadsheet engine probe
Tested locally on macOS with Nextcloud Office 9.3.8 (build 544). This is a disposable-engine experiment, not a production file-replacement route or a SharePoint coauthoring implementation.

The app bundles `libdoctrenderer.dylib` in `Contents/Resources/converter`, exposing Euro-Office's CDocBuilder interface. A small C++ harness linked this library using the public Euro-Office `docbuilder.h`, `common.h` and `base_export.h` headers. Headers remain in the disposable test directory; they were not vendored into Agent Hands. The installed app was not patched.

The runtime needs a temporary converter directory with links to the installed libraries, its own DoctRenderer.config using absolute script paths, and local copies of the converter's AllFonts.js and font_selection.bin. The editor's browser-oriented AllFonts.js uses numbered font paths and failed during native spreadsheet initialization. Using the converter's font data in the temporary runtime made the test work without opening desktop windows.

The probe opened the synthetic fixture, used ApiRange.SetValue and GetCharacters/GetFont/SetColor to create red original text and green proposed text, saved XLSX, reopened/resaved XLSX and exported PDF. Independent openpyxl reads confirmed run colors, the unchanged formula, table range, hyperlink and second sheet. The PDF was visually inspected and showed both colors and a calculated sum of 18.

A preservation difference matters: Nextcloud converted the fixture's legacy cell note into a threaded comment plus a compatibility note. The person's name and source text remain in the threaded-comment parts, but the legacy author field becomes a thread identifier and the compatibility text includes attribution. This is not exact comment preservation. Do not promote the engine to saving a shared workbook with required comment fidelity without a representative-file acceptance test and an explicit decision about this conversion.

GridCraft CLI 0.19.1 was separately tested against the same fixture. It retained the formula, table, comment and hyperlink but flattened mixed-color text runs on XLSX export. Its built-in round-trip check did not flag that loss. Nextcloud is the stronger local rich-text candidate; Office.js remains the route under development for live Excel files.

The retained `make-fixture.py`, `stage-runtime.py`, `probe.cpp`, `reopen.cpp` and `render.cpp` reproduce the synthetic scenario under `/private/tmp/spreadsheet-engines` on this Mac. Compile the C++ harness against the installed converter library with an rpath to that directory; obtain the matching public Euro-Office headers before compiling. `stage-runtime.py` refuses an existing destination so it cannot overwrite a previous test or app runtime.
