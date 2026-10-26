---
name: setup-penpot
description: "Set up or diagnose the Penpot capability: enable Penpot's MCP server, store its server URL and key in ignored local configuration, check it without exposing the key, register the use-penpot connector with an MCP client, and verify tool discovery. Use for first-time Penpot setup, a missing or rejected key, or a client that cannot see Penpot tools."
---

# Setup Penpot
## Scope and dependencies
Own the Penpot configuration contract and onboarding. [use-penpot](../use-penpot/SKILL.md) owns the MCP connector and design work. Runtime for this skill: Bash 3.2+, sed and ordinary Unix file utilities. Verification and the connector also need use-penpot's Python environment through uv. No other provider, workspace skill, or global client installation is required.

## Configuration contract
The default configuration directory is this skill's folder. Its `.env` holds one literal assignment, `PENPOT_MCP_SERVER_URL`, copied from Penpot's **Your account → Integrations → MCP Server**. Penpot embeds the MCP key in that URL as `userToken`, so the URL itself is the credential. Start from [.env.example](.env.example).

An exported `PENPOT_CONFIG_DIR` selects another configuration directory, and `PENPOT_ENV_FILE` selects an explicit env file, resolved against the configuration directory when relative. A missing explicitly selected file fails. An exported `PENPOT_MCP_SERVER_URL` takes precedence over the file. Single or double outer quotes are stripped; no variable, tilde, escape or command expansion occurs. The file accepts only `PENPOT_*` keys and cannot redirect its own location or the Python runtime.

HTTPS URLs must carry a non-empty `userToken`. Plain HTTP is accepted only for a loopback server such as a self-run local Penpot MCP server, which needs no key.

The real `.env` is ignored by this folder's [.gitignore](.gitignore). Check ignores before creating it and keep it owner-only (`chmod 600`). Never print the URL or key, paste it into chat, put it in client configuration, or write it to logs, commit bodies or shell history. The user enters the value; do not ask for it.

## Onboarding
1. Check Bash and uv. Install uv with the user's package manager only within the authorized setup scope; do not install unrelated providers.
2. In Penpot, the user enables MCP under **Your account → Integrations → MCP Server** and creates an MCP key if none exists. Penpot shows the key once and allows one per user; generating a new one replaces the old. Follow [Penpot's MCP guide](https://help.penpot.app/mcp/) for current interface details.
3. From this folder, confirm `git check-ignore -q .env` succeeds. Copy `.env.example` to `.env` only when `.env` does not exist, run `chmod 600 .env`, and have the user paste the copied server URL after `PENPOT_MCP_SERVER_URL=`. Preserve an existing file.
4. Run `bash scripts/check`. It verifies presence, URL form and file permissions without a network request. It does not prove the key works.
5. When a service read is authorized, run `bash ../use-penpot/scripts/penpot-mcp --list-tools` from this folder. The first run builds use-penpot's pinned environment. It initializes an MCP session, prints tool names and closes the session; no design file needs to be open. Penpot's hosted server lists tools without checking the key, so this proves the connector and network path, not the key. The key is proven by the first read-only tool call against a file the user has connected.
6. Register the connector with the user's chosen MCP client using use-penpot's [client registration](../use-penpot/SKILL.md#client-registration). Registration stores only the connector's command path. Do not change client configuration without the user's agreement for that client.
7. Most clients load MCP servers when a session starts, so confirm discovery in a new session. Then the user opens a design file and chooses **MCP → Connect** in Penpot before any design work.

Report which pieces are installed, configured, discovered and verified as separate levels, without revealing the URL or key. Repeated setup must preserve existing configuration.

## Diagnose narrowly
`bash scripts/check` explains missing, malformed or overly permissive configuration. If tool calls keep reporting no connected session while the user's file shows MCP connected, suspect the key: the user regenerates it in Penpot's Integrations page and replaces the value in `.env`. How Penpot reports an invalid key has not been verified. When the client shows no Penpot tools, check its registration and start a new session before changing configuration. When tools appear but calls report no connected session, the Penpot tab is disconnected or asleep; see use-penpot.

Do not broaden account access, change Penpot sharing or team permissions, or route around a denied key through browser automation.
