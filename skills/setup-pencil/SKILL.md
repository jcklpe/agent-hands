---
name: setup-pencil
description: "Set up or diagnose Pencil's MCP integration with VS Code and an agent client. Use when restoring Pencil on a new machine, registering its server, or troubleshooting missing design tools."
---

# Setup Pencil
This guide covers the VS Code extension's local MCP server. Pencil owns the server and design tools; Agent Hands supplies setup guidance only. It requires a supported VS Code installation, the Pencil extension, and the chosen MCP client. It does not use Agent Hands provider credentials.

## Install and register
1. Install the publisher's `highagency.pencildev` extension through VS Code's extension manager. The inspected version was 0.6.55, requiring VS Code 1.100.0 or newer. Consult [Pencil](https://pencil.dev) for current supported versions; this is not a promise about other editors or operating systems.
2. Activate Pencil by opening a design file or the **Pencil: New File** command. Complete any account/license prompts in Pencil itself. Fresh-account onboarding was not exercised; do not invent a token file or copy another machine's session.
3. Open **Pencil: Settings** and select only the desired agent integrations. The extension owns installation of its platform-specific MCP binary and client registration. Its inspected installer can rewrite registrations for several supported clients, so inspect the selected integrations and existing client settings before running setup. Do not invoke it just to audit an existing setup.
4. Inspect the resulting `pencil` entry in the selected client. For VS Code, the observed stdio configuration has the following shape; `<pencil-server>` means the executable installed by Pencil on this machine, not a copied absolute path from another computer:

```toml
[mcp_servers.pencil]
command = "<pencil-server>"
args = ["--app", "visual_studio_code", "--agent", "codexCLI"]
```

For Claude Code the same command uses `--agent claudeCodeCLI` in its `mcpServers.pencil` entry. Resolve the executable from Pencil's actual installation, including the platform architecture. If the extension already registered it, preserve that entry rather than creating a duplicate. Do not copy extension-version paths or manually disable platform security controls when startup fails.

## Verify and use
Keep VS Code and the intended Pencil document open. Restart the chosen client session, inspect the server's actual tool list, and perform a read-only document inspection using its returned schema. Confirm the document before any requested change. A configured entry or an executable file alone does not prove a connected design session. Follow the tools' current documentation for operations; no tested companion design workflow is supplied here yet.

## Evidence and gaps
On 2026-10-26, both Codex and Claude Code had this stdio registration, and its macOS ARM64 executable existed. The installed extension's package metadata, MCP configuration generator, and adapter confirmed the publisher ID, argument shape, and extension-managed registration. No server was started, no design file was read, and no fresh-machine or account setup was tested during that check. Report installation, discovery, and successful document access separately.
