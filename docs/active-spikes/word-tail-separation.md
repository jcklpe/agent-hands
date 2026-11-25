---
attention: live
tags: [word, cli, coauthoring]
---
# Separate a reviewed Word document tail
The user requested moving draft material into its own document and leaving a link in the existing meeting note while it remains open. File replacement was refused by an active lock. Add a bounded coauthoring operation rather than bypassing the lock or asking the user to close Word.

The operation removes a uniquely headed tail from a paragraph-only body and inserts one reviewed HTTPS link. Up to five exact prefix paragraphs may be updated in the same reviewed operation. The separate document must already be saved. Compare the whole Word body against cloud text before preview and apply, refuse unsupported document structures, retain existing headers/footers, and use durable dispatch/readback. Source-specific content stays outside the public repository.

The November 25 extension supports bounded indexed paragraph edits, semantic formatting, same-origin link repair and explicit appended paragraphs through the same owned Office.js session. Untouched comments and tracked insertions remain part of saved verification. The user authorized this extension and its use on existing shared documents after disposable tests. It does not authorize generic document rewriting.

[Work log](word-tail-separation.todo.md).
