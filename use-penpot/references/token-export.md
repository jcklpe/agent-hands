# Export design tokens from a Penpot archive
The reusable command is `use-penpot/scripts/export_tokens.py`. Each project owns a JSON manifest selecting its local archive, exact Penpot file ID and JSON output destinations. This command uses Python 3.9+ and the standard library on macOS or Linux; secure directory-relative file operations are required, and unsupported platforms fail before reading inputs. It does not require uv, the MCP SDK, an account key or setup-penpot configuration.

## Prepare the source and manifest
Download the intended file through Penpot's native export UI and put the `.penpot` archive in the project. Confirm that its content is appropriate for the output audience. The tool reads the existing `penpot/export-files` version-1 manifest and `files/<file-id>/tokens.json` entry; it never extracts archive members to disk. A native archive may contain other private material even when its tokens are safe, so review the archive separately before publishing it.

Start with [the synthetic example](../examples/token-export.example.json). All paths are relative to the manifest's own directory, which is the project boundary. Replace the source file ID with the intended exported file's ID and map the desired palette names to output files. The UUID must match exactly one file listed by the archive, including when the archive contains multiple files. The source is local: this command does not download a hosted design or verify that an archive is current.

```json
{
  "schema_version": 1,
  "source": {
    "kind": "penpot-archive",
    "path": "Wireframes.penpot",
    "file_id": "11111111-2222-3333-4444-555555555555"
  },
  "outputs": {
    "sets": {
      "color": "design-tokens/color.json",
      "type": "design-tokens/type.json"
    },
    "metadata": "design-tokens/$metadata.json",
    "themes": "design-tokens/$themes.json"
  }
}
```

`schema_version`, `source` and `outputs` are required. Unknown manifest fields are errors. `source.kind` currently supports only `penpot-archive`. `outputs.sets` maps existing palette names to distinct `.json` files; `metadata` and `themes` are optional. Export all palettes when requesting metadata or themes. A partial palette selection is allowed without them only when all selected token references resolve inside that selection. The manifest contains no code, shell commands, credentials or runtime paths to Agent Hands.

## Preview and apply
From the consuming project, with an Agent Hands checkout containing this command:

```sh
python3 /path/to/agent-hands/use-penpot/scripts/export_tokens.py --manifest penpot-export.json
```

The default is read-only, including when destination directories do not exist. The JSON report contains source and manifest SHA-256 digests, token count, each output's `create`, `update` or `unchanged` action and before/after hashes, plus a `plan_sha256`. It prints no token values or archive contents. Review those paths and actions before executing an authorized write:

```sh
python3 /path/to/agent-hands/use-penpot/scripts/export_tokens.py --manifest penpot-export.json --execute --expect-plan <plan_sha256>
```

Use the digest from the current preview. A change to the manifest, archive or destination bytes invalidates the plan. Writes require the digest; `--execute` alone is accepted only when all outputs are already unchanged. Inputs and destinations are checked again during execution. No unselected or stale output is deleted. Refresh images and the native source separately when the project's artifact policy requires them to describe the same design state.

New or changed files use UTF-8 JSON with two-space indentation and no trailing newline, preserving token aliases and source object order except that unsigned array-index keys sort first, matching the observed browser exports. Active-set membership is ordered by the source's `tokenSetOrder`. There are no generated timestamps. Repeating the same source and manifest produces the same bytes, and byte-identical outputs are not rewritten. Exporting does not resolve aliases into literal values, translate formats for CSS or modify the hosted file.

## Validation and file safety
The tool rejects duplicate JSON keys, non-finite values, missing or ambiguous file identities, duplicate ZIP member names, malformed token groups, missing types, ambiguous token names across selected palettes, unresolved aliases and cycles. Group-inherited `$type` values are supported. Values and types are preserved; this is structural/reference validation of the observed Penpot export format, not a full DTCG type checker or semantic assessment of a design.

Paths must be normalized relative paths. Absolute paths, parent traversal, hidden path components, symlinks, duplicate/case-colliding outputs, overlapping file/directory outputs and replacement of the manifest are refused. Source files must end in `.penpot`; output files must end in `.json`. Directory handles and no-follow opens keep symlink substitutions from redirecting reads or writes. Only regular files are read. New directories are created only during execution, and new/replaced files use owner-only permissions. The manifest is limited to 64 KiB, the archive to 128 MiB, each read/written JSON entry to 16 MiB and the ZIP directory to 10,000 members. Token nesting is limited to 64 levels and reference chains to 128 levels.

Each output replacement is atomic, but the whole export is not a filesystem transaction. Avoid concurrent writers. A failure returns a nonzero exit and a JSON report with `completed` output paths and `created_directories`; earlier successful replacements remain in place. Temporary files are cleaned up. Inspect the report and rerun preview before continuing. Detection between checks cannot replace a project-wide lock, and a readback failure may mean another writer changed an already replaced file.

## Verification
Run `python3 use-penpot/tests/test_export_tokens.py` from Agent Hands. Fixtures cover deterministic archive exports, selection, reference errors, malicious paths, symlinks/nonregular files, duplicate/malformed archives and JSON, size bounds, preview, guarded writes, stale/concurrent changes, idempotence and partial failure reporting. No test contacts a service or loads configuration. The consuming project's own archive should also produce a reviewed preview; a successful local export does not prove live MCP access or freshness of the hosted design.
