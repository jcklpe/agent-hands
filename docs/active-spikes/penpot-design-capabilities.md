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

## Proposed board-copy tool
Agent proposal, not yet adopted: a `use-penpot` script that copies boards between pages through the backend API, with the same preview and guarded execution as the token exporter.

1. Read each board's subtree with `get-page`.
2. Give every copied shape a new ID, and remap parents, frames, child lists and prototype links. Links to boards that are also being copied point at the copies; links to anything else are reported for relinking.
3. Keep component instances as instances, and never duplicate a component's main shape.
4. Preview the plan, then write the shapes with `update-file` `add-obj` changes against the file's current revision, with a fresh session ID.
5. Read the result back and compare it with the source.

Risks: the backend API is internal and its data format can change between Penpot versions; an open editor can move the file's revision on, so a write has to retry from a fresh read; and a wrong change writes bad data into a shared file, although the server validates changes. Whether an open browser tab shows API writes immediately is unknown.

## Open questions
- Does a browser tab with the file open pick up backend changes live, or only after a reload?
- Which file features does `update-file` require for this file, and how stable are they across Penpot releases?
