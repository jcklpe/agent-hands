---
name: setup-trello
description: "Install selected Trello capabilities, establish or repair account access, choose existing profiles, and diagnose configuration or authentication. Owns the shared provider runtime used by the selected use skills."
---
# Setup Trello
Read [use-trello](../use-trello/SKILL.md) and this skill’s [account-access reference](references/account-access.md). Keep the setup and use folders as siblings. Inspect existing configuration and dependencies before changing anything. Bash 3.2+, curl, jq, `shasum` for mutation preview fingerprints, and standard Unix tools are needed; Python and uv are not. macOS offline operation is verified; fresh Linux/WSL bootstrap is not yet verified, and native Windows without Bash is unsupported.

1. Install only missing dependencies through an appropriate OS package manager within the requested setup scope. Run `bash use-trello/scripts/trello --help` from the collection root; help needs no credentials.
2. Follow the [official authorization guide](https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/) to obtain the app API key and tokens. Request only the intended access and duration. Retain separate read and write tokens; no write token is necessary for read-only use. Do not authorize broader scopes or change existing credentials implicitly.
3. Resolve the selected private configuration directory using the account-access reference and preserve existing storage. Verify its `.env` is ignored, then create it from this setup folder’s `.env.example` only if absent. Enter secrets privately, never in agent-visible command arguments or tracked examples. Set owner-only permissions where supported. Preserve existing account configuration.
4. From the collection root, run `bash setup-trello/scripts/authorize check read`. With permission to access the account, `list-boards` can identify desired boards; copy only the selected IDs into ignored `TRELLO_BOARD_IDS`. This does not restrict the token's service-side access.
5. If writes are intended, check the separate write token locally. Do not create or edit a card as a setup test. All mutation commands preview by default; `--execute` sends the reviewed changes. A preview can use the read token without a write token. Report offline readiness separately from live read/write access.

Optional start-date list annotations are explicit consumer choices. This tool installs no scheduled automation, list taxonomy, personal task rules, or snapshot destination.

## Account access and shared runtime
Read [account access and provider support](references/account-access.md) for configuration, account selection, initial authorization, reconnection and diagnosis. This setup skill owns the provider scripts, examples and tests that the selected use skills load. Automatic refresh, where supported, stays in that runtime; normal operations do not require rerunning setup or granting broader access. Keep credential establishment separate from permission for each service action, and preserve existing user approval within its stated scope.

## Optional global discovery
Ask whether this selected capability should be available globally and which supported local clients (Codex, Claude Code, or both) should receive it. Preserve an already stated choice; do not re-ask for granted installation scope. Read the [shared link procedure](../setup-agent-hands/references/global-skill-links.md), inspect existing destinations, and use this owner's entrypoint from the checkout root:
```sh
python3 setup-trello/scripts/link-skills.py --client codex
```
This previews only; add `--execute` for the authorized selection. The optional linker requires Python 3.9+ without external packages and keeps provider runtimes separate. Correct links are unchanged; conflicting user files/links are preserved. An explicit previous checkout permits recoverable repair as described in the shared procedure. Verify filesystem targets and fresh client discovery separately; links do not grant account access or operation permission.
