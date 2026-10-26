---
name: setup-jasp
description: "Set up or diagnose JASP's MCP bridge for a local JASP application. Use when restoring the statistics integration on a new machine or when the agent client cannot discover JASP tools."
---

# Setup JASP
JASP's [MCP bridge](https://github.com/jasp-stats/jasp-mcp) exposes the running application's JSON-RPC methods as MCP tools. Agent Hands supplies setup guidance, not another server or an analysis workflow. Prerequisites are a JASP build with its remote RPC server, uv/uvx, network access for initial package retrieval, and Python 3.10+ as required by the inspected bridge. uv may provision Python; do not replace system Python to satisfy this guide.

## Prepare the application
Install the appropriate JASP build from [JASP](https://jasp-stats.org/) and enable its local RPC server using that build's instructions. The inspected bridge defaults to `http://127.0.0.1:48164/rpc`; `JASP_RPC_URL` or its `--jasp-url` argument can select an explicit endpoint. Keep the service local. This guide does not configure a remote host, authentication proxy, or credentials.

The required JASP release/build and exact RPC-enable interface have not been established from the inspected client configuration. Confirm those before calling fresh-machine setup complete; an ordinary JASP installation alone is insufficient evidence.

## Register the bridge
The following Codex stdio entry reproduces the observed package revision and SDK constraint without exporting personal configuration:

```toml
[mcp_servers.jasp]
command = "uvx"
args = ["--with", "mcp==1.30.0", "--from", "git+https://github.com/jasp-stats/jasp-mcp@72d9d7be9c003b9681b40871ee5850795108e5ab", "jasp-mcp"]
```

Use the same command/arguments in another stdio client's supported server configuration when that client is requested. Resolve uvx on the new machine; a GUI client may not inherit the shell's PATH. Preserve an existing entry and merge only this server. The source revision and MCP SDK are pinned here; the remaining transitive environment is not fully locked. Do not silently substitute latest when reproducing a failure.

## Startup and verification
Start JASP with its RPC server, then a fresh MCP client session. The inspected bridge serves stdio immediately and discovers methods lazily and in a background poller; an initially empty tool list can mean JASP is not reachable. Inspect the tool list and use the discovered `jasp_ping` and `jasp_rpc_discover` schemas for a bounded connectivity check. Do not load a dataset, create an analysis, or change an open workspace merely to verify setup.

Tools come from the running JASP version. Before analysis work, inspect its method schemas and analysis context; do not treat a saved list of tools as the current API. User authorization for an analysis is separate from registering this bridge. No dedicated use skill is supplied until an actual analysis workflow has been verified.

## Evidence and gaps
On 2026-10-26 the Codex entry above existed and a local checkout of that bridge revision was available. Its manifest and implementation confirmed the runtime, endpoint default, dynamic discovery, and polling. That check did not establish a running JASP application, RPC reachability, successful tool discovery, or any completed analysis. New-machine setup still needs the JASP build/RPC-enable step resolved and a successful read-only check.

## Optional global discovery
Ask whether this selected capability should be available globally and which supported local clients (Codex, Claude Code, or both) should receive it. Preserve an already stated choice; do not re-ask for granted installation scope. Read the [shared link procedure](../setup-agent-hands/references/global-skill-links.md), inspect existing destinations, and use this owner's entrypoint from the checkout root:
```sh
python3 setup-jasp/scripts/link-skills.py --client codex
```
This previews only; add `--execute` for the authorized selection. The optional linker requires Python 3.9+ without external packages and keeps provider runtimes separate. Correct links are unchanged; conflicting user files/links are preserved. An explicit previous checkout permits recoverable repair as described in the shared procedure. This links only the setup guide; it does not install or register the vendor MCP integration. Verify filesystem targets and fresh client discovery separately; links do not grant account access or operation permission.
