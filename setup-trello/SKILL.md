---
name: setup-trello
description: "Install and configure the Trello capability with its own read/write credentials and explicit board selection. Use for first-time setup or local dependency diagnosis."
---
# Setup Trello
Read [use-trello](../use-trello/SKILL.md) and [authorize-trello](../authorize-trello/SKILL.md). Keep both folders as siblings. Inspect existing configuration and dependencies before changing anything. Bash 3.2+, curl, jq, and standard Unix tools are needed; Python and uv are not. macOS offline operation is verified; fresh Linux/WSL bootstrap is not yet verified, and native Windows without Bash is unsupported.

1. Install only missing dependencies through an appropriate OS package manager within the requested setup scope. Run `bash use-trello/scripts/trello --help` from the collection root; help needs no credentials.
2. Follow the [official authorization guide](https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/) to obtain the app API key and tokens. Request only the intended access and duration. Retain separate read and write tokens; no write token is necessary for read-only use. Do not authorize broader scopes or change existing credentials implicitly.
3. Verify `authorize-trello/.env` is ignored, then create it from `.env.example` if absent. Enter secrets privately, never in agent-visible command arguments or tracked examples. Set owner-only permissions where supported. Preserve existing account configuration.
4. Run the authorization skill's local `check read`. With permission to access the account, `list-boards` can identify desired boards; copy only the selected IDs into ignored `TRELLO_BOARD_IDS`. This does not restrict the token's service-side access.
5. If writes are intended, check the separate write token locally. Do not create or edit a card as a setup test: Trello write commands act immediately and have no preview flag. Report offline readiness separately from live read/write access.

Optional start-date list annotations are explicit consumer choices. This tool installs no scheduled automation, list taxonomy, personal task rules, or snapshot destination.
