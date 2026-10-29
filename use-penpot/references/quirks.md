# Penpot quirks
Behavior observed on design.penpot.app between 2026-10-25 and 2026-10-29 that the documentation does not make obvious. Each item says what happens and what to do instead. Recheck an item before relying on it after a Penpot release.

## MCP connection
- **The file must be connected and awake.** MCP calls run inside the browser tab where the user chose **MCP → Connect**. When that tab sleeps or closes, every call fails with "No Penpot instance connected for user token"; ask the user to reconnect. In Chrome, adding the Penpot site under **Settings → Performance → Always keep these sites active** keeps the tab awake.
- **`high_level_overview` is meant to be read once per session.** Its own instructions say not to call it again.
- **`export_shape` returns an image to the agent, not a file.** The hosted server cannot write local files, and `import_image` is absent.
- **The plugin acts as the user.** Everything it changes appears live to collaborators, with no preview or undo for them.

## Plugin API
- **Only the open page can be changed.** Creating, moving or appending shapes on any other page fails with "Cannot modify a page that is not currently active". `penpot.openPage(page)` makes a page active, but it also switches the user's view, so say so before using it.
- **Shapes cannot move between pages.** `appendChild` across pages fails in both directions, and `clone()` copies only onto the shape's own page. Use `scripts/copy_boards.py`.
- **Pages cannot be reordered.** The Plugin API has no ordering method; the backend API's `mov-page` change can.
- **Links stay within a page.** An interaction aimed at a board on another page is stored, but its destination reads back empty, and reading it can raise "invalid string '' for uuid". Keep each page's prototype self-contained.
- **Fonts come from `penpot.fonts`.** Find one by name, for example `penpot.fonts.all.find(f => f.name === "Inter")`, before applying it to text.
- **Shared plugin data keys cannot be deleted.** Setting a value to an empty string is the closest equivalent, and the empty key remains on the file.
- **`currentFile.export()` fails.** Every form tried failed inside Penpot with "No matching clause", and exporting a page timed out. The user downloads the `.penpot` file from Penpot's file menu instead.
- **Version history mixes autosaves with named versions.** `findVersions()` returns entries labelled `internal/snapshot/<n>` alongside versions saved with `saveVersion(label)`.

## Design tokens
- **Typography tokens take `fontWeight` and references.** A typography value uses the key `fontWeight` and can reference other tokens, for example `{font.size.5xl}`.
- **Shadow tokens reject a negative spread.** Use a spread of 0 and note the difference from the source.
- **`resolvedValue` drops a color's alpha.** The applied token still renders with its opacity, so check transparency against the token's own value, not the resolved one.

## Backend API
- **Python's HTTP client is refused.** Penpot's Cloudflare front end answers Python's `urllib` with error 1010 because of its client signature; plain `curl` is accepted. Do not disguise requests as a browser. Pass the access token in a `curl` configuration read from standard input, never as an argument.
- **Authentication is `Authorization: Token <access token>`.** The token is a personal access token from Penpot's account settings, kept in setup-penpot's configuration; the MCP key is a different credential.
- **Writes need the file's current state.** `update-file` takes the file's `revn`, `vern` and `features` from `get-file`, plus a fresh random `sessionId`. Each successful write raises `revn` by one, so a plan built against an older revision has to be rebuilt.
- **`get-page` with an `objectId` returns a whole subtree.** That is the way to read one board with all its children.
- **Backend type names differ from the Plugin API's.** A board is `frame`, a rectangle `rect` and an ellipse `circle`. A page's root is a frame with the all-zero ID, which is also the parent and frame of every top-level board.
- **Child order follows insertion.** The first ID in a parent's `shapes` list is drawn at the bottom. Adding children in source order with empty `shapes` lists on their parents reproduces the source order exactly.
- **An open editor shows backend writes live.** A page and board added through the API appeared in the connected tab without a reload.
- **`export-binfile` streams.** It returns server-sent events ending in a temporary download address that expires after about an hour.
- **Webhooks cannot carry custom headers.** A receiver has to authenticate requests some other way.
