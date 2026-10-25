# Agent Hands
Portable skills that let an agent act on external systems through bounded tools. Start with [setup-agent-hands](skills/setup-agent-hands/SKILL.md), choose a capability, and configure only its declared provider support. Source ownership, global installation, and permission to act are separate.

## Available now
| Capability | Required skill | Runtime | Entry |
| --- | --- | --- | --- |
| [use-odoo-projects](skills/use-odoo-projects/SKILL.md) | [authorize-odoo](skills/authorize-odoo/SKILL.md) | Bash 3.2+, jq, curl, ordinary Unix utilities | `bash skills/use-odoo-projects/scripts/odoo --help` |

[setup-odoo](skills/setup-odoo/SKILL.md) guides first-time configuration. Odoo project/stage/task reads, task creation/updates, and comments are implemented. Writes preview by default and require `--execute`; no delete/archive or generic model/method interface is exposed.

Slack has separate [messaging](skills/use-slack-messages/SKILL.md) and [Lists](skills/use-slack-lists/SKILL.md) skills with a shared [authorization](skills/authorize-slack/SKILL.md) dependency and [setup guide](skills/setup-slack/SKILL.md). Each Python capability has its own manifest/lock and requires only Python 3.11+ (standard library). Either use skill can be distributed with authorization alone. Existing Lists export accepts an explicit output directory.

Trello has [provider authorization](skills/authorize-trello/SKILL.md), [setup](skills/setup-trello/SKILL.md), and a bounded [use skill](skills/use-trello/SKILL.md). It preserves direct writes and neutral card linking; exports require an explicit output and keep the previous file when retrieval fails. No Python or uv is needed.

GitHub now has [Issues](skills/use-github-issues/SKILL.md), [Pull Requests](skills/use-github-pull-requests/SKILL.md), [Discussions](skills/use-github-discussions/SKILL.md), and [Projects](skills/use-github-projects/SKILL.md), each with only the [GitHub provider](skills/authorize-github/SKILL.md) dependency. [Setup](skills/setup-github/SKILL.md) retains gh authentication and capability-local uv rendering. Existing writes are issue creation and organization-board Status moves; Discussion writes remain deferred.

Google Docs now has a [use skill](skills/use-google-docs/SKILL.md), shared [Google authorization](skills/authorize-google/SKILL.md), and [setup guide](skills/setup-google-services/SKILL.md). Existing-document reads, exact replacements, whole-tab Markdown replacement, and comments retain preview/execute controls. Each Python skill has a local uv manifest/lock. Other Google services still use the legacy route.

This is a staged extraction. Remaining Google, Microsoft, and rendering capabilities remain in their previous owner until individually migrated and checked. No portable MCP catalog has been audited yet. Do not interpret planned names as installed capabilities.

## Configuration and dependencies
Real account routing and credentials stay ignored beside the authorization skill, with tailored examples. Never source `.env` as shell code. Odoo's entry parses literal `ODOO_*` values and preserves exported values; no unrelated provider or workspace is loaded. No Python or uv environment is needed for this Bash capability.

Slack provides the first capability-local Python environments and locks; there is no shared all-provider runtime. Setup must handle absent uv/Python for a selected Python capability rather than assuming a developer workstation. The initial shell route has local macOS verification; Linux/WSL and native Windows onboarding remain unverified. Native Windows without Bash is not supported by this entry.

## Validation and distribution
Run `bash skills/use-odoo-projects/tests/test-odoo-shell.sh` and `bash skills/authorize-odoo/tests/test-config.sh` for offline request/guardrail and configuration checks. These use synthetic fixtures; no live account or write is necessary. Help and dry runs work without credentials.

Slack offline checks: `python tests/test_slack_operations.py`, `python skills/use-slack-messages/tests/test_operations.py`, `python skills/use-slack-lists/tests/test_operations.py`, and `python skills/authorize-slack/tests/test_config.py`. The package-level smoke check exercises both domains; production entrypoints do not import one another. Local macOS isolation/uv execution passed; live Slack access and fresh Windows/Linux installation remain unverified.

The intended public origin is `https://github.com/jcklpe/agent-hands`. Local preparation does not publish it; remote creation and collaborator cloning remain pending. Licensed under [AGPL-3.0-only](LICENSE), with retained [source notices](NOTICE.md). No unrelated source-repository history is included.
