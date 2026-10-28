# Account access and provider support
The command examples below identify their working directory. Private configuration lives in this setup folder beside its examples; explicit configuration overrides keep their existing precedence. Preserve existing credentials; do not create a parallel profile or move tokens as part of routine setup.

Owns literal provider configuration and HTTP access. Requires Bash 3.2+, curl, jq, and ordinary Unix tools. No Python, uv, other provider, or personal workspace is required. See [setup-trello](../SKILL.md) for first-time setup.

Keep real `.env` in the selected configuration directory, copied from the tailored `.env.example` only when absent. The collection ignores real env files before use. `TRELLO_API_KEY` and `TRELLO_TOKEN` enable reads; `TRELLO_WRITE_TOKEN` is a separate write credential. Both tokens should belong to the intended account and app. `TRELLO_BOARD_IDS` selects export/default boards; it is not an authorization allowlist. No board is compiled into the tool.

Exported variables take precedence over literal env assignments. The parser never sources/evaluates a file. `TRELLO_ENV_FILE` selects an explicit file (relative to the caller's cwd); a missing selected file fails. Otherwise `TRELLO_CONFIG_DIR` can select a directory, otherwise using the selected configuration directory described above. Config cannot override its loader path through file assignments. Credentials go only to the fixed public Trello API endpoint; no custom server setting is exposed.

From the collection root:
```sh
bash setup-trello/scripts/authorize check read
bash setup-trello/scripts/authorize check write
```
These check local presence and required commands, without network requests or printing values. They do not verify token ownership, scopes, or live access. This client does not implement an OAuth browser callback, refresh, or automatic identity-matching gate. The use skill owns mutation previews and execution; this provider does not enforce Slack-style identity matching.

Follow [Trello's authorization documentation](https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/) for acquiring/revoking tokens with explicitly selected scopes and duration. Keep tokens private; avoid debug tracing and command dumps. HTTP errors are failures; a write interrupted in transit may have landed, so inspect the destination before retrying. No automatic write retry is implemented.
