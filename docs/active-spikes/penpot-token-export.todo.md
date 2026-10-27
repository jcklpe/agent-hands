---
attention: live
---
# Penpot token export tasks
## To Do
- Publish the reviewed implementation after unrelated outgoing history and the required workflow pin are resolved, then verify remote retrieval.
## Done
- Document setup, commands, manifest ownership and live-access limits; review all selected changes for privacy/security before committing. The skill, export guide, synthetic manifest, setup boundary and README are updated. Full selected content review, local resource/frontmatter checks and secret/path screening pass before the implementation commit; no credential stores or live services were read.
- Implement a bounded archive reader and project manifest with deterministic JSON outputs and token-reference validation. Implemented the observed version-1 archive format with explicit file identity and palette mapping; 97 real-archive tokens validate.
- Add preview, guarded execution, path checks and honest partial-failure reporting. Implemented digest-guarded writes, directory-relative no-follow file operations, per-file replacement/readback and completed-path reporting.
- Cover the contract with synthetic fixture tests and verify the existing consumer archive without changing its artifacts. Eighteen synthetic tests pass. A fresh-directory export from the existing consumer archive reproduces all six JSON files byte-for-byte; no-change execution writes nothing and all fourteen original consumer artifacts retain their hashes.

## Verification notes
The real archive first revealed numeric object-key ordering differences in two palettes. The exporter now uses the observed browser ordering for unsigned array-index keys, with a regression fixture; existing artifacts were never rewritten. Review also added collision-safe temporary-file cleanup and Unicode-normalized destination checks. MCP access and hosted-file freshness were not tested.
