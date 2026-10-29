---
attention: live
---
# Penpot design capabilities tasks
## To Do
- Prototype the board-copy tool on a throwaway board with the user's approval, then decide with the user whether to build it with a preview, guarded execution and synthetic tests.
- Reorder pages through `mov-page` in the same tool, if the copy prototype works.
- Have `use-penpot` read a project's `design-files.json` to find its file and page roles, as defined in the Wireframe Workflows README.
- Once a route is tested, update the capability map in `use-penpot` so copying no longer depends on the user pasting.

## Done
- Mapped Wireframe Workflows' design-tool capabilities in `use-penpot` and tested them on the hosted server (2026-10-29): boards cannot be moved between pages through the Plugin API, links stay within a page, and locking and file metadata work. Test material was removed.
- Confirmed that the configured access token reads a board's full subtree through `get-page`, using `curl` with the token passed on standard input.
