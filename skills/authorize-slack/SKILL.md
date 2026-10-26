---
name: authorize-slack
description: "Configure or diagnose Slack user-token accounts for the messaging and Lists tools. Use to locate provider settings, check local token presence, verify the acting identity, or investigate authorization errors."
---
# Authorize Slack
Owns shared account configuration, HTTP transport, bounded paging, identity checks, and small Slack message helpers. Requires Python 3.11+; no third-party Python libraries, other provider, or personal workspace. [setup-slack](../setup-slack/SKILL.md) guides first-time installation. This skill accepts an existing user OAuth token; it does not implement interactive OAuth or automatic token refresh.

## Configuration
Keep `.env` and `slack-accounts.json` beside this file, using the adjacent tailored examples. Both real files are ignored. Check ignores before saving real values; use owner-only permissions where supported. Never print, commit, or pass tokens as command arguments. Profiles carry an alias, expected team/user IDs, and the environment-variable name holding the token. Optional Lists metadata supplies explicit list IDs/names and verified discussion-channel IDs.

The parser reads literal `SLACK_*` assignments without shell expansion or evaluation. Exported values win. `SLACK_ENV_FILE` selects an alternate env file; a missing explicitly selected file fails. Relative `SLACK_ACCOUNTS_PATH` values resolve beside that env file, otherwise beside this skill. The public API endpoint is fixed; an env file cannot redirect credentials to another host. Profiles must have unique simple aliases. No account configuration is loaded at import time.

Run from the collection root (or use absolute paths):
```sh
uv run --project skills/authorize-slack python skills/authorize-slack/scripts/slack_auth.py check example
uv run --project skills/authorize-slack python skills/authorize-slack/scripts/slack_auth.py whoami example
```
`check` verifies local fields/token presence without network access. `whoami` calls `auth.test`, compares both team and user IDs, and rejects bot tokens. `accounts` lists profile metadata, never token values. A local check is not evidence of remote authorization.

## Errors and authority
Writes require a matching user identity. Missing scopes, inaccessible resources, and expired tokens must be reported; do not expand grants, disable token rotation, or acquire browser credentials automatically. The transport reports rate-limit delay and uncertain network outcomes without retrying writes. Inspect a possibly changed destination before any retry. Current scopes and app setup belong to the account owner; see [Slack token types](https://docs.slack.dev/authentication/tokens/) and [token rotation](https://docs.slack.dev/authentication/using-token-rotation/).

Run `python3 tests/test_request_helpers.py` from this skill folder for synthetic message-URL and pagination-bound checks.
