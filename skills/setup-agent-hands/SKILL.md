---
name: setup-agent-hands
description: "Help a new user install selected external-service capabilities from Agent Hands. Use to choose available skills, inspect dependencies and platform support, bootstrap missing runtimes, and configure only the requested providers."
---

# Setup Agent Hands
Start with the collection's [available capability list](../../README.md). Match the user's requested service to an implemented skill, not a planned name. Currently Odoo, Slack, and Trello are extracted; do not route another service to an empty placeholder or install the entire collection's future dependencies.

## Select and inspect
Read the chosen use skill and its declared authorization dependency. Identify the actual operating system, shell, required commands, existing installation, and whether configuration already exists. Source ownership, client skill installation, and permission for external writes remain separate. A downloaded repository can be used directly; do not assume the agent client discovers every nested skill automatically.

For Odoo, use [setup-odoo](../setup-odoo/SKILL.md). It requires Bash/jq/curl and ordinary Unix tools, not uv/Python. Local macOS checks are recorded; fresh Linux/WSL installation and native Windows support are not established.

For Slack, use [setup-slack](../setup-slack/SKILL.md). Select messaging, Lists, or both; each depends on Slack authorization and has its own uv manifest/lock. Their Python entrypoints use only the standard library.

For Trello, use [setup-trello](../setup-trello/SKILL.md). Bash/curl/jq support is separate from Python; write commands act immediately, so no live mutation is part of a routine setup check.

## Missing runtime approach
When an implemented Python capability declares a pyproject.toml and lock, use that capability's environment only. Check for uv first. If absent, use an appropriate installation method from [uv's official installation guide](https://docs.astral.sh/uv/getting-started/installation/) within the user's setup authorization. Do not assume Python or a package manager is already present. uv can provision a compatible Python version; follow the capability's declared version rather than replacing system Python. See [Python provisioning](https://docs.astral.sh/uv/guides/install-python/). Never invent a manifest or claim a future capability is ready.

Inspect installer sources and side effects before running them, preserve existing toolchains, and distinguish local software setup from provider authorization. Record what was installed and tested. Do not disable security controls or force unsupported platforms to pass.

## Configure and verify
Use tailored provider examples and verify the owning repository's ignores before any real config is written. Keep credentials local and preserve existing profiles. Run help and relevant offline checks, then one authorized read when appropriate. Live writes need their own actual target and scope. Report local readiness separately from remote account access and client discovery. Do not add global skill links or MCP connections unless that installation is requested or already authorized.
