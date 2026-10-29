---
attention: live
---
# Penpot design capabilities tasks
## To Do
- Reorder pages through `mov-page`, so setting up a file's page order needs no dragging.
- Decide how promotion replaces an existing board: a guarded replace option in the copier, or the user deleting the old board after the copy.
- Have `use-penpot` read a project's `design-files.json` to find its file and page roles, as defined in the Wireframe Workflows README.

## Handoff notes (2026-10-29)
Claude Code built this spike's work and is handing it to Codex. Where things stand:

- **Live test page.** The user's wireframe file still has a page named "Copy test (temporary)" holding a copy of a Workshop board, left for the user to look at. Delete it once they have, through Penpot's page menu or an `update-file` `del-page` change.
- **Testing writes safely.** Test against a temporary page, never a working page: add it with an `update-file` `add-page` change, copy onto it, compare each copied shape with its source field by field, then delete the page with `del-page`. Only read the source pages. The helper scripts used for this, and the file's identifiers, are in the user's private handoff note, which their workspace's agent coordination index links to.
- **Quirks.** `use-penpot/references/quirks.md` collects everything observed about Penpot's MCP connection, Plugin API, tokens and backend API, with what to do instead; read it first and add to it.
- **MCP connection.** When the browser tab sleeps, MCP calls fail with "No Penpot instance connected"; the user reconnects with MCP → Connect in Penpot. `penpot.openPage` switches the user's view, so say so before using it.
- **Backend API calls.** Use `curl`; Penpot's Cloudflare front end refuses Python's HTTP client with error 1010. Pass the token in a `curl` configuration on standard input, as `copy_boards.py` does, and never print it.
- **Next.** The To Do list above, in this order unless the user says otherwise: how promotion replaces an existing board, which Wireframe Workflows' promotion needs; page reordering through `mov-page`; reading `design-files.json`.
- **Working agreements.** Commit by pathspec with this spike's trailer, without co-author trailers. The user approved pushing Agent Hands on 2026-10-29; ask again before later pushes.

## Done
- Checked with a connected editor that backend writes appear without a reload, and that a copied board's image export matches its source (2026-10-29).
- Mapped Wireframe Workflows' design-tool capabilities in `use-penpot` and tested them on the hosted server (2026-10-29): boards cannot be moved between pages through the Plugin API, links stay within a page, and locking and file metadata work. Test material was removed.
- Confirmed that the configured access token reads a board's full subtree through `get-page`, using `curl` with the token passed on standard input.
- Built `scripts/copy_boards.py` with preview, digest-guarded execution and readback, documented it in `use-penpot`, and described the access token's use in setup-penpot's example configuration. A live test on a temporary page copied a 29-shape board exactly and was cleaned up; a stale plan was refused. Eighteen synthetic tests pass, on Python 3.9 as well.
