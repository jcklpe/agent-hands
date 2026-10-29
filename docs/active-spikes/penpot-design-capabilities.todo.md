---
attention: live
---
# Penpot design capabilities tasks
## To Do
- Reorder pages through `mov-page`, so setting up a file's page order needs no dragging.
- Decide how promotion replaces an existing board: a guarded replace option in the copier, or the user deleting the old board after the copy.
- Check with a connected editor whether backend writes appear live, and look at a copied board visually.
- Have `use-penpot` read a project's `design-files.json` to find its file and page roles, as defined in the Wireframe Workflows README.

## Done
- Mapped Wireframe Workflows' design-tool capabilities in `use-penpot` and tested them on the hosted server (2026-10-29): boards cannot be moved between pages through the Plugin API, links stay within a page, and locking and file metadata work. Test material was removed.
- Confirmed that the configured access token reads a board's full subtree through `get-page`, using `curl` with the token passed on standard input.
- Built `scripts/copy_boards.py` with preview, digest-guarded execution and readback, documented it in `use-penpot`, and described the access token's use in setup-penpot's example configuration. A live test on a temporary page copied a 29-shape board exactly and was cleaned up; a stale plan was refused. Eighteen synthetic tests pass, on Python 3.9 as well.
