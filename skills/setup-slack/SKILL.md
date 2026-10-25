---
name: setup-slack
description: "Help install and configure the Slack messaging or Lists capability, including missing uv/Python, tailored account files, and user-token identity checks."
---
# Setup Slack
Start with [setup-agent-hands](../setup-agent-hands/SKILL.md) and select [use-slack-messages](../use-slack-messages/SKILL.md), [use-slack-lists](../use-slack-lists/SKILL.md), or both. Each use skill depends only on [authorize-slack](../authorize-slack/SKILL.md). Keep those selected folders as siblings; either use skill works without the other. No Bash or external Python package is required.

## Runtime
Inspect the OS and available tools. If uv is missing, follow the [official installer](https://docs.astral.sh/uv/getting-started/installation/) within setup authorization; do not assume Python, Bash, or a package manager is installed. uv can provision Python for the selected manifest. From the collection root, run the selected command with `--help`, for example:
```sh
uv run --project skills/use-slack-messages python skills/use-slack-messages/scripts/slack_messages.py --help
```
The manifest and lock belong to that capability, not an all-provider environment. With an already compatible Python, invoking the script directly also works. macOS offline execution is verified; fresh Windows/Linux bootstrap is not yet verified. The Python entrypoints do not require a Unix shell.

## Account
1. Preserve existing profiles and obtain a user OAuth token through the account's approved Slack app/OAuth process. This client acts as the user, so a bot token is deliberately unsupported. Follow [Slack's token guidance](https://docs.slack.dev/authentication/tokens/); do not change app grants or rotation settings without authorization. Automatic refresh is not implemented here.
2. Copy `authorize-slack/.env.example` to `.env` and `slack-accounts.example.json` to `slack-accounts.json` only if the real files do not exist. Verify ignores first. Set a simple alias, expected workspace/user IDs, and `token_env`; enter the token privately in that named env variable.
3. Select scopes for intended operations, checking the current official method documentation: conversation `*:read`/`*:history` for discovery/history, `users:read` for people lookup, `search:read` for search, `chat:write` for sending, `im:write` for opening a DM, and `lists:read`/`lists:write` for Lists. This is a capability map, not permission to grant every scope. [Lists method reference](https://docs.slack.dev/reference/methods/slackLists.items.list/).
4. Run `authorize-slack`'s local `check`, then authorized `whoami`. Report local readiness separately from live access. For Lists comments, configure a verified discussion conversation or supply a copied real comment permalink; no automatic List-to-conversation discovery is implemented.

Do not send a test message or change a List merely to verify installation. Offline checks use synthetic data; a live write needs its own requested destination and content.
