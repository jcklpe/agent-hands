---
name: authorize-trello
description: "Configure or diagnose the Trello API key, read token, and separate write token used by the bounded Trello capability."
---
# Authorize Trello
Owns literal provider configuration and HTTP access. Requires Bash 3.2+, curl, jq, and ordinary Unix tools. No Python, uv, other provider, or personal workspace is required. See [setup-trello](../setup-trello/SKILL.md) for first-time setup.

Keep real `.env` beside this file, copied from the tailored `.env.example` only when absent. The collection ignores real env files before use. `TRELLO_API_KEY` and `TRELLO_TOKEN` enable reads; `TRELLO_WRITE_TOKEN` is a separate write credential. Both tokens should belong to the intended account and app. `TRELLO_BOARD_IDS` selects export/default boards; it is not an authorization allowlist. No board is compiled into the tool.

Exported variables take precedence over literal env assignments. The parser never sources/evaluates a file. `TRELLO_ENV_FILE` selects an explicit file (relative to the caller's cwd); a missing selected file fails. Otherwise `TRELLO_CONFIG_DIR` can select a directory, defaulting to this skill. Config cannot override its loader path through file assignments. Credentials go only to the fixed public Trello API endpoint; no custom server setting is exposed.

From the collection root:
```sh
bash skills/authorize-trello/scripts/authorize check read
bash skills/authorize-trello/scripts/authorize check write
```
These check local presence and required commands, without network requests or printing values. They do not verify token ownership, scopes, or live access. This client does not implement an OAuth browser callback, refresh, or automatic identity-matching gate. Never infer a Slack-style identity check or dry run for Trello.

Follow [Trello's authorization documentation](https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/) for acquiring/revoking tokens with explicitly selected scopes and duration. Keep tokens private; avoid debug tracing and command dumps. HTTP errors are failures; a write interrupted in transit may have landed, so inspect the destination before retrying. No automatic write retry is implemented.
