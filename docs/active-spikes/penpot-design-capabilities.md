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

**Live test, 2026-10-29.** Through the backend API alone, a temporary page was added, a 29-shape Workshop board was copied onto it, and the page was deleted again; the Workshop board was only read. Every copied shape matched its source in every field apart from its ID, with parents, frames and child order pointing at the copies. Re-running the executed plan was refused because the file's revision had moved on. A second run the same day, with the MCP plugin connected, showed that the user's open editor picks up the new page and copy without a reload, and an image export of the copy matched the source board. Eighteen synthetic tests cover the transformation, refusals, digest, configuration parsing and keeping the token out of `curl`'s arguments.

The backend API is internal to Penpot, and its data format can change between releases; the readback after each write is the guard against a silent mismatch.

## Manifest discovery and page order
Built on 2026-11-23 as `use-penpot/scripts/penpot_pages.py`, sharing the copier's token and `curl` transport, which moved into `scripts/penpot_backend.py`. The backend assumptions were rechecked that day against Penpot 2.19's published API description and its source.

- **Discovery reads only the named manifest.** `discover` reads `./design-files.json` or `--manifest`, never a parent folder, so it cannot pick up another project's file. It checks the manifest contract as Wireframe Workflows defines it, without adding to it: a single page name per role, a list of owned pages for owned roles, a single name for Archive, no page assigned to two roles, and a URL whose `file-id` agrees with `file_id`. Unknown roles and names with surrounding spaces are reported rather than refused, since the project owns its manifest; one real manifest has a page name with a trailing space. Files for other tools are listed and left alone.
- **Names match exactly.** `--resolve` matches each role's page name to the file's pages exactly. A near match such as different capitalization is offered as a hint and never used, and a name shared by several pages is reported as ambiguous. A live read-only run against the user's wireframe file resolved its four existing role pages, reported the two roles it does not have yet and listed the leftover test page as unmapped.
- **The token goes only where the caller points it.** The manifest is project data, so its URL never chooses where the access token is sent. A manifest on a different instance from `--base-url` is refused with the remedy.
- **Unlisted pages keep their positions.** The pages named in an order request take the positions they occupy now, in the requested order; every other page stays where it is. Only listed pages get `mov-page` changes: the plan keeps the largest set of pages already in their wanted relative order, which always includes the unlisted ones, and moves the rest. A first version that walked the list position by position reached the right order but also issued a transient move for an unlisted page, which misreported what moved.
- **`mov-page` semantics come from Penpot's source.** The index is a position in the list before the move (`insert-at-index`), which the plan simulates exactly; synthetic tests check every arrangement of a five-page file.
- **The revision check is not concurrency protection.** Penpot's `update-file` refuses only a newer revision or a restored version; changes sent against an older revision are applied on top of later ones. Execution therefore re-reads the file and refuses a changed plan, sends every move in one transactional call, counts other sessions' `lagged` changes in the response, and reads the complete page list back. A mismatch exits with status 2. A write whose outcome is unknown exits with status 3 and reports what the file shows, without retrying. A page order needs no private journal: it is fully visible in the file, a fresh preview shows whether a write landed, and the earlier digest no longer matches once it has. The preview's current order is the recovery input.
- **Live test pending.** A read-only preview against the user's file planned one move and wrote nothing. No hosted page-order write has been made; that needs a chosen file and the user's go-ahead.

## Promotion replacement (proposed, awaiting decisions)
Wireframe Workflows' promotion says a copy that replaces a Prototype board "takes its place and position, so links keep working", and also that boards are never deleted because superseded work stays restorable through version history. The copier only adds boards. This design covers what replacing needs; nothing destructive is built until the user settles the choices below.

**Matching.** Each replacement is an explicit pair of a source board and the Prototype board it replaces, given by ID. The preview suggests pairs from exact name matches, refuses an ambiguous name, and never turns a name match into a write target on its own.

**What happens to the existing board.** Recommended: keep its identity. In one `update-file` call, set the existing board's own properties from the source with `mod-obj`, delete its old children with `del-obj` (each deletes a whole subtree) and add copies of the source's children beneath it. Because the board's ID stays, links from other Prototype boards, flow starting points, comment threads pinned to the board, its place in the layer order, and direct prototype links recorded in the project's route record all keep working without retargeting. The old children are deleted, so this is a destructive write. The alternatives:

- Add the copy as a new board, point incoming links and flows at it, then delete the old board. Simpler to build, but the new ID breaks comment anchoring, route-record links and any shared prototype address.
- Add the copy and keep the old board on Prototype, renamed as superseded and moved aside. Nothing is deleted, but Prototype then holds boards that are not current design.
- Move the old board to Archive, as a copy there plus a deletion from Prototype. Whether superseded Prototype versions belong in Archive is a design-method question for Wireframe Workflows.

**Position.** Recommended: the replacement takes the source board's geometry exactly, as the copier does now, and the preview warns when it would overlap another Prototype board. Keeping the old board's position instead means translating every copied shape's position, selection rectangle, corner points, path data and text layout consistently, which is more code and more risk and would need its own live verification.

**Kept from the existing board.** Its ID, layer position, comments and, recommended, its lock and hidden state; promotion locks promoted boards again anyway. Everything else comes from the source.

**Refusals and reported changes.** Refuse an ambiguous match, a target that is not a top-level board on the Prototype page, a component main shape on either side, and a nested source board. Report, and require explicit acceptance in the reviewed plan for, links elsewhere on Prototype that point into the old board's children, such as an overlay positioned relative to one of them. Links from the source to boards outside the copied set are dropped and reported as now, unless an explicit source-to-Prototype mapping points them at existing Prototype boards.

**Preservation and recovery.**
1. Before writing, save the old board's complete subtree, with the plan, to an owner-only private journal outside the checkout, under `~/.agent-hands/penpot/`, and record intent, dispatch and the verified outcome there.
2. Also save a named version first with `create-file-snapshot`, labelled for the promotion, and lock it so collaborators cannot delete it.
3. Targeted undo re-applies the journaled subtree to the same board ID in one call, leaving collaborators' other work alone. Restoring the named version restores every page and discards everyone's later changes, so it is the last resort.
4. After an unknown outcome, read the board back: children matching the plan mean it landed, the old children mean it did not, anything else blocks. While a journal entry is unresolved, the tool refuses another replacement of that board. Completed journals are kept until their retirement is separately approved.

**Still to verify on disposable material before relying on it.** How `mod-obj` attribute names are spelled over the JSON API, and that the open editor shows a replaced board's new children without a reload.

**Decisions needed.**
1. What happens to the existing board: keep its identity and replace its contents (recommended), or one of the three alternatives.
2. Position: source geometry (recommended) or the old board's position.
3. A locked named version before every replacement (recommended), in addition to the private journal.
4. Keep the existing board's lock and hidden state (recommended).

Wireframe Workflows' promotion wording would need to say which of these it expects; that belongs to Wireframe Workflows, not this spike.

## Open questions
- Which file features does `update-file` require for this file, and how stable are they across Penpot releases? The list `get-file` returns grew between 2026-10-29 and 2026-11-23, so the tools pass the current list rather than a fixed one; whether every listed feature is accepted on a write is confirmed only by the next live write.
