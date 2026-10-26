---
name: setup-slack
description: "Install selected Slack capabilities, establish or repair account access, choose existing profiles, and diagnose configuration or authentication. Owns the shared provider runtime used by the selected use skills."
---
# Setup Slack
Start with [setup-agent-hands](../setup-agent-hands/SKILL.md) and select [use-slack-messages](../use-slack-messages/SKILL.md), [use-slack-lists](../use-slack-lists/SKILL.md), or both. Each use skill depends only on this setup skill’s [provider runtime](references/account-access.md). Keep those selected folders as siblings; either use skill works without the other. No Bash or external Python package is required.

## Runtime
Inspect the OS and available tools. If uv is missing, follow the [official installer](https://docs.astral.sh/uv/getting-started/installation/) within setup authorization; do not assume Python, Bash, or a package manager is installed. uv can provision Python for the selected manifest. From the collection root, run the selected command with `--help`, for example:
```sh
uv run --project use-slack-messages python use-slack-messages/scripts/slack_messages.py --help
```
The manifest and lock belong to that capability, not an all-provider environment. With an already compatible Python, invoking the script directly also works. macOS offline execution is verified; fresh Windows/Linux bootstrap is not yet verified. The Python entrypoints do not require a Unix shell.

## Account
1. Preserve existing profiles and obtain a user OAuth token through the account's approved Slack app/OAuth process. This client acts as the user, so a bot token is deliberately unsupported. Follow [Slack's token guidance](https://docs.slack.dev/authentication/tokens/); do not change app grants or rotation settings without authorization. Automatic refresh is not implemented here.
2. Resolve the selected private configuration directory using the account-access reference; preserve existing storage. Copy this setup folder’s `.env.example` and `slack-accounts.example.json` into that directory only if the real files do not exist. Verify ignores first. Set a simple alias, expected workspace/user IDs, and `token_env`; enter the token privately in that named env variable.
3. Select scopes for intended operations, checking the current official method documentation: conversation `*:read`/`*:history` for discovery/history, `users:read` for people lookup, `search:read` for search, `chat:write` for sending, `im:write` for opening a DM, and `lists:read`/`lists:write` for Lists. This is a capability map, not permission to grant every scope. [Lists method reference](https://docs.slack.dev/reference/methods/slackLists.items.list/).
4. Run `setup-slack`'s local `check`, then authorized `whoami`. Report local readiness separately from live access. For Lists comments, configure a verified discussion conversation or supply a copied real comment permalink; no automatic List-to-conversation discovery is implemented.

Do not send a test message or change a List merely to verify installation. Offline checks use synthetic data; a live write needs its own requested destination and content.

## Account access and shared runtime
Read [account access and provider support](references/account-access.md) for configuration, account selection, initial authorization, reconnection and diagnosis. This setup skill owns the provider scripts, examples and tests that the selected use skills load. Automatic refresh, where supported, stays in that runtime; normal operations do not require rerunning setup or granting broader access. Keep credential establishment separate from permission for each service action, and preserve existing user approval within its stated scope.

## Optional global discovery
Ask whether this selected capability should be available globally and which supported local clients (Codex, Claude Code, or both) should receive it. Preserve an already stated choice; do not re-ask for granted installation scope. Select only the requested capabilities with repeated `--skill`; omission is refused for this service. Read the [shared link procedure](../setup-agent-hands/references/global-skill-links.md), inspect existing destinations, and use this owner's entrypoint from the checkout root:
```sh
python3 setup-slack/scripts/link-skills.py --client codex --skill use-slack-messages
```
This previews only; add `--execute` for the authorized selection. The optional linker requires Python 3.9+ without external packages and keeps provider runtimes separate. Correct links are unchanged; conflicting user files/links are preserved. An explicit previous checkout permits recoverable repair as described in the shared procedure. Verify filesystem targets and fresh client discovery separately; links do not grant account access or operation permission.
