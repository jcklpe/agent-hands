---
name: setup-agent-hands
description: "Help a new user install selected external-service capabilities from Agent Hands. Use to choose available skills, inspect dependencies and platform support, bootstrap missing runtimes, configure only the requested providers, and offer service-selected global discovery for supported local clients."
---

# Setup Agent Hands
Start with the collection's [available capability list](../README.md). Match the user's requested service to an implemented skill, not a planned name. Currently Canvas reads/exports and bounded writes, Odoo, Penpot, Slack, Trello, GitHub, Google Docs/Contacts/Sheets/Drive/Gmail/Calendar, Microsoft Mail/Calendar/Contacts/Files/Excel/Planner, and Markdown-to-PDF rendering are extracted; do not route another service to an empty placeholder or install the entire collection's future dependencies.

## Setup dialogue
Begin by asking what the user wants to do. Resolve the selected service and capabilities, then ask which supported local agent clients they use and whether they want those skills linked for global discovery. Offer direct checkout use without links as an equal choice. Reuse choices already supplied; ask only what is missing, in short steps rather than a form with placeholders. Keep global skill discovery, runtime installation, account authorization and MCP registration as separate choices.

When global links are wanted, read [optional global skill links](references/global-skill-links.md), inspect the client's actual discovery directory, and invoke each selected service's `scripts/link-skills.py` with only its requested capabilities. Multi-capability services require `--skill`; never infer all services from the repository being present. Preview the exact destinations and apply with `--execute` within the user's stated installation scope. Preserve existing links, expose conflicts, and use the explicit recoverable repair procedure when an old checkout path is confirmed. The dialogue can optionally link itself with [its own entrypoint](scripts/link-skills.py); it is not automatically added to every service selection.

## Select and inspect
Read the chosen use skill and its provider's setup skill, including the linked account-access reference when configuration or authentication is involved. Identify the actual operating system, shell, required commands, existing installation, and whether configuration already exists. Source ownership, client skill installation, and permission for external writes remain separate. A downloaded repository can be used directly; do not assume the agent client discovers every nested skill automatically.

For MCP setup, use the actual service guide: [setup-penpot](../setup-penpot/SKILL.md), [setup-pencil](../setup-pencil/SKILL.md), or [setup-jasp](../setup-jasp/SKILL.md). Pencil and JASP record their verification evidence with explicit fresh-machine and live-verification gaps; they do not establish working design or analysis access. For client plugins, use the selected client’s own supported setup rather than assuming a similarly named standalone vendor server. Installing a plugin does not configure these CLI credentials.

For Odoo, use [setup-odoo](../setup-odoo/SKILL.md). It requires Bash/jq/curl and ordinary Unix tools, not uv/Python. Local macOS checks are recorded; fresh Linux/WSL installation and native Windows support are not established.

For Penpot, use [setup-penpot](../setup-penpot/SKILL.md). Its configuration is one server URL that embeds the user's MCP key. The [use-penpot](../use-penpot/SKILL.md) connector needs Bash and its own uv environment with the pinned MCP Python SDK, and design work needs a Penpot tab the user connects. Client registration is a separate, per-client choice.

For Slack, use [setup-slack](../setup-slack/SKILL.md). Select messaging, Lists, or both; each depends on setup-slack provider support and has its own uv manifest/lock. Their Python entrypoints use only the standard library.

For Canvas, use [setup-canvas](../setup-canvas/SKILL.md) with [use-canvas](../use-canvas/SKILL.md). The setup runtime uses Python 3.11+ with the standard library, and the use skill has its own locked conversion packages. The user creates and enters the initial token for their own development/testing connection; confirm identity and explicit course selection before course reads. Canvas requires OAuth for applications used by others; general-user OAuth onboarding is not implemented. Reads/exports/history and fifteen bounded write commands are implemented. Selected-course reads/exports and opt-in successor-token renewal passed a live smoke test; course-content writes require their own concrete preview approval and execution hash and remain unverified live.

For Trello, use [setup-trello](../setup-trello/SKILL.md). Bash/curl/jq support is separate from Python; mutation previews also require `shasum`. Writes require `--execute`, and no live mutation is part of a routine setup check.

For GitHub, use [setup-github](../setup-github/SKILL.md). Select only the needed domains and setup-github provider support. Bash/gh/jq handle requests; rendering uses the selected domain’s uv environment. No all-provider dependency is installed.

For Google Docs, Contacts, Sheets, Drive, Gmail, or Calendar, use [setup-google-services](../setup-google-services/SKILL.md). Select the requested use skill and setup-google-services provider support; provider mixing and private workflow routing remain outside the capabilities.

For Outlook Mail/Calendar/Contacts, Microsoft Files, Excel Workbooks, or Planner, use [setup-microsoft-services](../setup-microsoft-services/SKILL.md) and select only the requested capability plus setup-microsoft-services provider support. MSAL dependencies belong only to that provider environment, and PowerShell remains an optional alternative.

For local Markdown export, use [render-markdown-pdf](../render-markdown-pdf/SKILL.md). It has no authorization dependency; select only its own uv environment, Pandoc, native Pango, and fonts. The bundled plain theme is a general baseline, not an academic-style commitment.

## Missing runtime approach
When an implemented Python capability declares a pyproject.toml and lock, use that capability's environment only. Check for uv first. If absent, use an appropriate installation method from [uv's official installation guide](https://docs.astral.sh/uv/getting-started/installation/) within the user's setup authorization. Do not assume Python or a package manager is already present. uv can provision a compatible Python version; follow the capability's declared version rather than replacing system Python. See [Python provisioning](https://docs.astral.sh/uv/guides/install-python/). Never invent a manifest or claim a future capability is ready.

Inspect installer sources and side effects before running them, preserve existing toolchains, and distinguish local software setup from provider authorization. Record what was installed and tested. Do not disable security controls or force unsupported platforms to pass.

## Configure and verify
Use tailored provider examples and verify the owning repository's ignores before any real config is written. Keep credentials local and preserve existing profiles. Run help and relevant offline checks, then one authorized read when appropriate. Live writes need their own actual target and scope. Report local readiness separately from remote account access and client discovery. Do not add global skill links or MCP connections unless that installation is requested or already authorized.

For combined calendars, install [render-calendar-agenda](../render-calendar-agenda/SKILL.md) plus only the chosen provider skills and their setup/runtime dependencies. The renderer uses Python 3.11+ with timezone data and has no authorization dependency. Google Calendar Markdown export also needs this renderer; provider JSON exports do not.
