---
status: captured
---
# Persistent runtime-state migration
Design migration of remaining legacy persistent stores outside checkouts, preserving ownership markers, all write journals and a single shared writer location. Current sign-ins and journals remain in their documented locations; no silent relocation or automatic expiration is implemented.

The [runtime-file inventory](../runtime-files.md) owns the actual locations and removal boundaries. A migration must coordinate all writers, preserve unresolved operations and account identity, verify recovery after the move, and avoid selecting an empty journal or creating independently writable copies. This is a separate implementation boundary from the completed disposable-temp and retained-file review; no migration is started by this capture.

Continues from: docs/archive/runtime-file-lifecycle.md
