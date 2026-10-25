---
name: setup-agent-hands
description: "Help a new user install selected external-service capabilities from Agent Hands. Use to choose available skills, inspect dependencies and platform support, bootstrap missing runtimes, and configure only the requested providers."
---

# Setup Agent Hands
Start with the collection's [available capability list](../../README.md). Match the user's requested service to an implemented skill, not a planned name. Currently Odoo, Slack, Trello, GitHub, Google Docs/Contacts/Sheets/Drive/Gmail/Calendar, Microsoft Mail/Calendar/Contacts/Files/Excel/Planner, and Markdown-to-PDF rendering are extracted; do not route another service to an empty placeholder or install the entire collection's future dependencies.

## Select and inspect
Read the chosen use skill and its declared authorization dependency. Identify the actual operating system, shell, required commands, existing installation, and whether configuration already exists. Source ownership, client skill installation, and permission for external writes remain separate. A downloaded repository can be used directly; do not assume the agent client discovers every nested skill automatically.

If the user wants an MCP or client plugin, consult the [optional integration catalog](../../mcp-integrations.md) for its vendor source, scope, and verification limits. Select only the requested route; CLI setup does not require adding an MCP connection, and installing a plugin does not configure these CLI credentials.

For Odoo, use [setup-odoo](../setup-odoo/SKILL.md). It requires Bash/jq/curl and ordinary Unix tools, not uv/Python. Local macOS checks are recorded; fresh Linux/WSL installation and native Windows support are not established.

For Slack, use [setup-slack](../setup-slack/SKILL.md). Select messaging, Lists, or both; each depends on Slack authorization and has its own uv manifest/lock. Their Python entrypoints use only the standard library.

For Trello, use [setup-trello](../setup-trello/SKILL.md). Bash/curl/jq support is separate from Python; write commands act immediately, so no live mutation is part of a routine setup check.

For GitHub, use [setup-github](../setup-github/SKILL.md). Select only the needed domains and their authorization sibling. Bash/gh/jq handle requests; rendering uses the selected domain’s uv environment. No all-provider dependency is installed.

For Google Docs, Contacts, Sheets, Drive, Gmail, or Calendar, use [setup-google-services](../setup-google-services/SKILL.md). Select the requested use skill and Google authorization; provider mixing and private workflow routing remain outside the capabilities.

For Outlook Mail/Calendar/Contacts, Microsoft Files, Excel Workbooks, or Planner, use [setup-microsoft-services](../setup-microsoft-services/SKILL.md) and select only the requested capability plus Microsoft authorization. MSAL dependencies belong only to that provider environment, and PowerShell remains an optional alternative.

For local Markdown export, use [render-markdown-pdf](../render-markdown-pdf/SKILL.md). It has no authorization dependency; select only its own uv environment, Pandoc, native Pango, and fonts. The bundled plain theme is a general baseline, not an academic-style commitment.

## Missing runtime approach
When an implemented Python capability declares a pyproject.toml and lock, use that capability's environment only. Check for uv first. If absent, use an appropriate installation method from [uv's official installation guide](https://docs.astral.sh/uv/getting-started/installation/) within the user's setup authorization. Do not assume Python or a package manager is already present. uv can provision a compatible Python version; follow the capability's declared version rather than replacing system Python. See [Python provisioning](https://docs.astral.sh/uv/guides/install-python/). Never invent a manifest or claim a future capability is ready.

Inspect installer sources and side effects before running them, preserve existing toolchains, and distinguish local software setup from provider authorization. Record what was installed and tested. Do not disable security controls or force unsupported platforms to pass.

## Configure and verify
Use tailored provider examples and verify the owning repository's ignores before any real config is written. Keep credentials local and preserve existing profiles. Run help and relevant offline checks, then one authorized read when appropriate. Live writes need their own actual target and scope. Report local readiness separately from remote account access and client discovery. Do not add global skill links or MCP connections unless that installation is requested or already authorized.
