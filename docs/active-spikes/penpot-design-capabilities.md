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
- **Live test, 2026-11-23.** With the user's go-ahead, the leftover test page in their wireframe file was moved to the top and back to the end. Both writes read back exactly, with no concurrent changes, and the file ended in its original order; replaying the first plan after it had landed was refused. Nothing else in the file changed.

## Promotion replacement
Wireframe Workflows' promotion says a copy that replaces a Prototype board "takes its place and position, so links keep working", and also that boards are never deleted because superseded work stays restorable through version history. The copier only added boards. A concrete design with alternatives was proposed on 2026-11-23, and the user adopted its four recommendations the same day; it is built as `copy_boards.py --replace` with recovery in `board_journal.py`.

**Decisions adopted by the user (2026-11-23).**
1. The existing board keeps its identity and its contents are replaced. Because the board's ID stays, links from other Prototype boards, flow starting points, comment threads pinned to the board, its place in the layer order and direct prototype links recorded in the project's route record keep working without retargeting. The alternatives considered were a new board with retargeted links and the old one deleted, which breaks comment anchoring, route-record links and shared prototype addresses; keeping the old board on Prototype marked as superseded, which leaves non-current design there; and moving it to Archive, which is a design-method question for Wireframe Workflows.
2. The replacement takes the source board's geometry exactly, as the copier does. Keeping the old position would mean translating every copied shape's position, selection rectangle, corner points, path data and text layout consistently.
3. A locked named version is saved before every replacement, in addition to the private journal.
4. The board keeps its lock and hidden state; promotion locks promoted boards again anyway.

**Matching.** Each replacement is an explicit pair of board IDs. A plain copy whose name matches exactly one board on the target page gets a suggested pair in the preview; a name match never becomes a write target on its own.

**Mechanism.** The proposal set the board's properties with `mod-obj`, but how `mod-obj` attribute names are spelled over the JSON API is unverified. The build instead deletes the board with `del-obj`, which removes its whole subtree, and adds it again in the same call under the same ID, with `add-obj`'s `index` putting it back at its old layer position, followed by the source's contents with new IDs. This reuses the `add-obj` path the copier's live test proved, and the end state is the same: same ID and layer position, the source's properties, and the kept lock and hidden state. Penpot's source applies one call's changes in order, and the hosted server ran this sequence correctly on 2026-11-23.

**Refusals.** The preview refuses a target that is not a top-level board on the target page, a component main shape on either side, a board listed twice and a nested source board. The proposal would have let the reviewed plan accept references from elsewhere on the target page into the old board's contents; the build refuses them instead, because removing those links in the same write would need `mod-obj`. The user retargets or removes them first. Links from the source to boards outside the copied set are dropped and reported, unless `--link` points them at existing target-page boards.

**Preservation and recovery.**
1. Under a per-file OS lock, the plan is rebuilt and its digest, which also covers the old contents, is checked. A private record then holds the plan and every old shape, under `~/.agent-hands/penpot/replacements/` or the `AGENT_HANDS_STATE_DIR` equivalent, owner-only, with each stage flushed before the next step.
2. A named version is saved and locked. Penpot's version quotas can refuse it, in which case nothing is replaced. The file is read again and the replacement stops if it changed.
3. The dispatch is recorded before the single `update-file` call. Every written shape is compared field by field with the plan, with child order and the board's layer position.
4. A timeout or a readback mismatch is never retried, and it blocks another replacement of that board. `board_journal.py reconcile` settles it: the planned contents mean it landed, and unchanged old contents mean it did not, but only after a ten-minute settling time, because a lost request could still finish. `accept` records the user's decision to keep what is there.
5. `board_journal.py restore` undoes a verified replacement under the same ID and layer position, with the old shapes' original IDs, through the same record, locked version and readback. It refuses when the board changed after the replacement, since that would discard later work; restoring the locked version, which reverts the whole file, is the last resort. Records are kept until their retirement is separately approved.

**Checks.** 18 synthetic tests run against a page model that applies `add-obj` and `del-obj` as Penpot does, on Python 3.14 and macOS's 3.9. A read-only preview against the user's wireframe file planned a 29-shape replacement of the earlier test copy (one deletion and 29 additions) with no warnings and created no record. With the user's itemized approval, a hosted replacement and restore ran on 2026-11-23 against the earlier test copy on the temporary page. Both locked versions were saved first, both writes read back exactly, and the restored board matched a prior capture in every shape ID, order and field. Whether an open editor shows a replaced board's new contents without a reload is still unverified.

Wireframe Workflows' promotion wording does not yet say which replacement it expects; that belongs to Wireframe Workflows, not this spike.

## Open questions
- Which file features does `update-file` require for this file, and how stable are they across Penpot releases? The list `get-file` returns grew between 2026-10-29 and 2026-11-23, so the tools pass the current list rather than a fixed one; the page-order writes of 2026-11-23 were accepted with that day's list.
