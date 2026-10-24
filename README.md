# Agent Hands
Portable skills that let an agent act on external systems through bounded tools. Start with [setup-agent-hands](skills/setup-agent-hands/SKILL.md), choose a capability, and configure only its declared provider support. Source ownership, global installation, and permission to act are separate.

## Available now
| Capability | Required skill | Runtime | Entry |
| --- | --- | --- | --- |
| [use-odoo-projects](skills/use-odoo-projects/SKILL.md) | [authorize-odoo](skills/authorize-odoo/SKILL.md) | Bash 3.2+, jq, curl, ordinary Unix utilities | `bash skills/use-odoo-projects/scripts/odoo --help` |

[setup-odoo](skills/setup-odoo/SKILL.md) guides first-time configuration. Odoo project/stage/task reads, task creation/updates, and comments are implemented. Writes preview by default and require `--execute`; no delete/archive or generic model/method interface is exposed.

This is a staged extraction. Other Google, Microsoft, Trello, Slack, GitHub, and rendering capabilities remain in their previous owner until individually migrated and checked. No portable MCP catalog has been audited yet. Do not interpret planned names as installed capabilities.

## Configuration and dependencies
Real account routing and credentials stay ignored beside the authorization skill, with tailored examples. Never source `.env` as shell code. Odoo's entry parses literal `ODOO_*` values and preserves exported values; no unrelated provider or workspace is loaded. No Python or uv environment is needed for this Bash capability.

Python-based capabilities will declare their own environments and locks when extracted; there is no shared all-provider runtime. Setup must handle absent uv/Python for a selected Python capability rather than assuming a developer workstation. The initial shell route has local macOS verification; Linux/WSL and native Windows onboarding remain unverified. Native Windows without Bash is not supported by this entry.

## Validation and distribution
Run `bash skills/use-odoo-projects/tests/test-odoo-shell.sh` and `bash skills/authorize-odoo/tests/test-config.sh` for offline request/guardrail and configuration checks. These use synthetic fixtures; no live account or write is necessary. Help and dry runs work without credentials.

The intended public origin is `https://github.com/jcklpe/agent-hands`. Local preparation does not publish it; remote creation and collaborator cloning remain pending. Licensed under [AGPL-3.0-only](LICENSE), with retained [source notices](NOTICE.md). No unrelated source-repository history is included.
