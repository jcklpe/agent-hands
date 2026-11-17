---
attention: historical
closed: 2026-11-17
---
# Manifest-driven Penpot token export
Historical record — closed 2026-11-17. Stable slug: `penpot-token-export`. The complete development record is retained below; use [maintained guidance](../../use-penpot/references/token-export.md) for current behavior and limits. Closure and the exact archival wording were approved.
Provide reusable design-token extraction under `use-penpot`, with source identity and output destinations owned by each consuming project's JSON manifest. This is an offline archive reader: it consumes Penpot's existing `penpot/export-files` archive and `files/<file-id>/tokens.json` structure. It does not retrieve authentication tokens, read service configuration, contact a server or change a hosted design.

## Contract
Use Python 3.9+ and the standard library so archive extraction does not require the MCP connector's runtime. Resolve manifest paths relative to the manifest directory. Reject traversal, absolute paths, symlinks, duplicate destinations, invalid JSON, ambiguous source IDs and unresolved or cyclic token references. Preview all creates and updates before execution; report checksums and protect reviewed execution with a plan digest. Never delete unselected or stale outputs.

Preserve the existing two-space JSON representation without a trailing newline. Enumerate unsigned array-index keys first in numeric order, matching the observed browser exports, then retain other source keys in their existing order. Normalize active-set membership to token-set order, with no timestamp fields. This reproduces the existing consumer snapshot while keeping repeated exports stable. Metadata and themes require all source palettes, avoiding dangling set selections in partial exports.

## Boundaries and verification
Fixture tests cover deterministic output, manifest selection, invalid archives and token references, path safety, preview, guarded execution and partial-write reporting. Check the existing consumer archive and hashes without changing its artifacts. Live MCP retrieval remains outside this implementation and unverified; refresh the native archive using Penpot's own export UI before running this tool.

The implementation commit must not silently publish unrelated local history. Earlier unrelated local history and the required workflow pin initially blocked publication. Their remote availability must be rechecked before publishing this implementation; the task does not authorize silently including unreviewed unrelated changes.

## Delivery verification
The pre-existing history and workflow dependency became available before the implementation push. The scoped implementation was then published normally and retrieved through an anonymous recursive clone. All eighteen fixture tests passed from the published checkout. The published consumer manifest and archive produced six unchanged outputs, and the fourteen existing consumer artifacts retained their original hashes. GitHub reported no checks for the implementation commit. Live retrieval, hosted-file freshness and other-platform execution remain unverified.

## Closure preparation — 2026-11-17
The bounded offline exporter is ready for closure. All 18 exporter tests passed again; its implementation is already present in public main and matches the local source. The recorded fresh-clone and byte-preservation checks remain dated evidence, not new access to a consumer archive. No required implementation or selected acceptance item remains. Hosted retrieval/freshness and other-platform execution were outside this scope and are not claimed complete. Current guidance is [token export](../../use-penpot/references/token-export.md). The closure review (local preparation record) records the evidence and pending closure decision; this pair stays live until closure is authorized.
