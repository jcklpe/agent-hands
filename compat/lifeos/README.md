# Compatibility command
The `lifeos` command preserves existing service command spellings while [native Agent Hands skills](../../README.md) own implementations, authorization, runtimes, audit records, and setup. This optional compatibility surface does not require a LifeOS vault or the containing configs repository. Add the collection’s `bin/` to PATH, or invoke `bin/lifeos` directly.

## Boundaries
The dispatcher and adapters retain command aliases, explicit-output exports, the configured GitHub multi-domain export, and legacy résumé output/theme behavior. Individual operations use the same provider-owned configuration and safeguards as native entrypoints. No shared environment, legacy secrets directory, or shared Python environment is loaded. Keep provider setup selective; do not provision an all-service runtime.

`sync`, `calendar sync`, `setup`, `doctor`, `open`, `context`, and private People alias management remain retired with actionable errors. Private account selection, snapshot destinations, indexes, combined agendas, and nickname preferences belong to consuming workflows. The optional `operate-lifeos` entry skill is owned by the consumer, not this collection.

GitHub `sync ALIAS --output DIRECTORY` preserves enabled issue/PR/discussion exports and configured projects under the owner/repository subdirectory. Omitting the alias iterates configured repositories. A failure returns nonzero; other repositories can still run. Multi-domain or multi-repository exports can partially succeed and are not a single transaction. Inspect actual output before retrying.

## Checks and guidance
Compatibility routing guides live under `skills/`; use the native capability guide for operational controls. Synthetic checks live under `tests/`, with provider/capability checks beside their owners. Real credentials, exports, browser state, and the former shared runtime are not part of this package. Original local recovery material remains with the installation owner.
