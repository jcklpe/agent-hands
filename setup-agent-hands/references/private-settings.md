# Private provider settings
Private settings live outside checkouts under `~/.agent-hands/`. `AGENT_HANDS_STATE_DIR` selects another absolute private base; checkout and symlink roots are refused. Provider wrappers declare their own file contract and use the dependency-free `scripts/private_settings.py` mechanics. Bash providers require Python 3.9+ for storage selection even when their service transport does not otherwise use Python. No unrelated service account or SDK is loaded.

| Setup owner | Default beneath the private base | Migrated inputs |
| --- | --- | --- |
| setup-google-services | `google/config/` | Literal `.env`, selected account JSON, its relative OAuth client/token files, and the legacy default Gmail audit |
| setup-github | `github-settings/config/` | Literal `.env` and selected repository configuration; gh owns authentication separately |
| setup-canvas | `canvas/config/` | Literal `.env`, account JSON, renewal pending/last records and lock files |
| setup-slack | `slack/config/` | Literal `.env` and selected account JSON |
| setup-trello | `trello/config/` | Literal `.env` with existing read/write credentials |
| setup-odoo | `odoo/config/` | Literal `.env`, selected account JSON and relative request-pacing timestamp |

Examples remain tracked beside each setup skill. Real settings, tokens, journals and ignored `.runtime-settings.json` migration pointers are never tracked. SDK authentication, explicit configuration overrides and externally selected stores remain with their existing owners. Relative configuration references resolve against the selected provider directory. Slack's existing explicit `SLACK_ENV_FILE` selection, and Canvas's env-file/config-directory precedence, are preserved.

## Migration and recovery
Stop all callers, including older installed copies and credential-renewal processes. From the owning setup folder, `python3 scripts/runtime_state.py migrate` previews the local move; add `--execute` for the authorized migration. No service request or sign-in occurs. Exported config/env/account/pacing overrides are refused by the bulk migrator rather than guessed; ordinary callers retain their override behavior. Absolute or escaping references in legacy configuration require a targeted migration. Update callers explicitly pinned to old paths as part of that targeted change.

The migrator renames complete selected inputs on the same filesystem and verifies byte/mode fingerprints. It refuses collisions, symlinks and overlapping inputs, holds the migration lock and existing Canvas renewal locks, and retains uncertain records unchanged. A partial move leaves `.settings-migration.json` in the provider's private root and blocks new default callers. Inspect its exact source/destination list and hashes before reconciliation; never clear it just to initialize a fresh sign-in or empty history. There is no automatic merge, copy fallback, replay or credential reset.

Ignored source routing pointers contain only the new directory, not credentials. A missing destination or mismatched pointer blocks use. Older binaries do not honor these gates: keep them stopped during migration and switch every caller together. Preserve the routing pointers after success; deleting them is not a cleanup method.

For a fresh installation, `python3 scripts/runtime_state.py path` selects/creates the owner-only default directory without authentication. Copy only the needed synthetic examples there, preserving any existing files. Persistent settings and unresolved recovery records do not expire as temporary files. Removal or sign-in retirement requires its own reviewed scope and deletion consent.
