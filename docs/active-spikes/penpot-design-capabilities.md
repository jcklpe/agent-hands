---
attention: live
---
# Penpot design capabilities
Make `use-penpot` cover what design-workflow collections such as [Wireframe Workflows](https://github.com/jcklpe/wireframe-workflows) need from Penpot, beyond the MCP connector itself. Wireframe Workflows names the capabilities and stays tool-agnostic; `use-penpot` explains how Penpot provides each one, under the same names, and owns any tooling that fills a gap.

## Positions the user has adopted
- **Tool mechanics live here.** Connecting to Penpot, calling its APIs and working around its limits belong to Agent Hands; design method belongs to Wireframe Workflows.
- **Test before relying.** Capabilities a skill depends on are tested on the hosted server, with test material removed afterwards, before a skill relies on them.

## What the Plugin API can and cannot do
Tested on design.penpot.app on 2026-10-29 through the MCP plugin, on throwaway boards and a temporary page that were removed afterwards:

- The Plugin API changes only the page that is open, so it cannot move or copy a board to another page; `appendChild` across pages fails in both directions. It also cannot reorder pages.
- Prototype links stay within a page: an interaction aimed at a board on another page is stored with an empty destination.
- Locking a board (`blocked`) and shared plugin data on the file work. Plugin data keys cannot be deleted, only emptied.

`use-penpot` records the resulting capability map.

## The backend API route
The user asked whether Penpot's personal access token could do what the plugin cannot (2026-10-29). Penpot's backend RPC API, which its own web app uses and documents at `/api/main/doc`, offers:

- `get-page` with a page and object ID returns one board with all its children. A read-only call with the configured access token returned a full board on 2026-10-29.
- `update-file` takes a list of changes, including `add-obj` on any page, `mov-page` to reorder pages and `set-plugin-data`.

Python's default HTTP client is refused by Penpot's Cloudflare front end on its client signature (error 1010); `curl` is accepted. Requests pass the token to `curl` through a configuration read from standard input, so it never appears in arguments or output.

## Board-copy tool
Adopted by the user on 2026-10-29 and built as `use-penpot/scripts/copy_boards.py`, with the token exporter's preview and guarded execution.

1. Read each top-level board's subtree with `get-page`, and the file's revision, version and features with `get-file`.
2. Give every copied shape a new ID, derived from the file, target page, revision and source ID, so a preview and its execution produce the same plan. Remap parents and frames; child lists are rebuilt as the shapes are added in source order.
3. Point links between copied boards at the copies, and drop and report links to anything else. Refuse a component's main shape.
4. Execute only with the preview's `plan_sha256`, which covers the revision, so a file that changed since the preview is refused. Write all shapes in one `update-file` call with `add-obj` changes and a fresh session ID, then read the copies back.

**Live test, 2026-10-29.** Through the backend API alone, a temporary page was added, a 29-shape Workshop board was copied onto it, and the page was deleted again; the Workshop board was only read. Every copied shape matched its source in every field apart from its ID, with parents, frames and child order pointing at the copies. Re-running the executed plan was refused because the file's revision had moved on. Eighteen synthetic tests cover the transformation, refusals, digest, configuration parsing and keeping the token out of `curl`'s arguments.

The backend API is internal to Penpot, and its data format can change between releases; the readback after each write is the guard against a silent mismatch.

## Open questions
- Does a browser tab with the file open show backend writes live, or only after a reload? The MCP plugin was disconnected during the live test, so this is unchecked.
- Which file features does `update-file` require for this file, and how stable are they across Penpot releases?
