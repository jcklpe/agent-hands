---
attention: live
---
# Selective global skill installation
Opened: 2026-10-26. Slug: `selective-skill-installation`.

## Scope
Optional global discovery belongs to the selected capability's setup owner. The setup-agent-hands dialogue asks what the user needs, which supported local clients they use, and whether they want global links at all. A service setup selects its own setup/use skills; a shared primitive implements filesystem behavior without copying an installer into every service. This extends the completed [setup/use contract](setup-use-contracts.md), not provider access or account configuration.

## Design
Service-owned entrypoints declare their capability choices and required skill dependencies. Multi-capability providers require an explicit selection; single-capability services select their setup/use pair. Standalone renderers and the setup dialogue can link only themselves. The shared Python standard-library primitive previews destinations by default and applies only with `--execute`. Python 3.9+ is an optional link-installer prerequisite, not a new runtime requirement for Bash-only service commands.

Use documented local client roots for new installs: Codex's user `.agents/skills` and Claude Code's `.claude/skills`. An explicit single-client `--skills-dir` supports a verified existing/custom discovery root without silently moving existing installations. Inspect existing discovery locations before choosing a root; do not create duplicate copies merely because another directory is supported. Keep the checkout at a stable path and retain its shared installer support.

Preflight the entire selection. Existing correct links are unchanged; files, directories and unrelated links block the whole selection before writes. Repair requires the exact previous checkout supplied by `--repair-from`, preserves the replaced links in a unique local recovery directory, and stops on changed state or partial failure. There is no force overwrite, wildcard all-services install, credential access, plugin/MCP registration or automatic uninstall. Existing global links remain in place when configs stops owning service installation.

## Verification and boundaries
Test only temporary client roots: preview, exact selection, repeat, multiple clients, conflicts, missing sources, allowed repair, partial errors, paths with spaces and invocation from Bash/Zsh. Confirm the containing installer loses only Agent Hands calls while Project Workflows/general instructions remain intact. Preserve private metadata and all concurrent work. Fresh-client discovery and other operating systems require separate verification. No pushes.
