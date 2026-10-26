---
name: setup-google-services
description: "Install selected Google capabilities, establish or repair account access, choose existing profiles, and diagnose configuration or authentication. Owns the shared provider runtime used by the selected use skills."
---

# Setup Google Services
Currently [Google Docs](../use-google-docs/SKILL.md), [Google Contacts](../use-google-contacts/SKILL.md), [Google Sheets](../use-google-sheets/SKILL.md), [Google Drive](../use-google-drive/SKILL.md), [Gmail](../use-gmail/SKILL.md), and [Google Calendar](../use-google-calendar/SKILL.md) are extracted. Each depends only on this setup skill’s [provider runtime](references/account-access.md). Do not advertise planned capabilities as available.

## Prepare the selected capability
Check the actual platform and existing tools. The entrypoints require Bash 3.2+, curl, jq, and uv or Python 3.11+. Follow [setup-agent-hands](../setup-agent-hands/SKILL.md) for missing uv/Python rather than assuming a developer environment. From each selected Python skill folder, `uv sync --locked` prepares its own environment. There is no all-provider dependency installation. macOS offline execution is checked; fresh Linux/WSL and native Windows onboarding remain unverified. Native Windows without Bash is unsupported by this entry.

## Configure authorization
1. Read the provider configuration contract and preserve existing accounts. Check ignore rules before copying the tailored example files. Never copy someone else's live credentials or token.
2. Follow Google's [desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app): create/select the user's own Cloud project, enable the relevant APIs, configure its consent screen, and create a desktop OAuth client. Calendar uses the Google Calendar API. Gmail uses the Gmail API. Drive operations use the Drive API. Sheets reads use the Sheets API. Contact lookup uses the People API. Docs operations use the Docs API; listing/adding comments also uses the Drive API. Save the downloaded JSON at the configured credentials path. Review organization restrictions and any testing-user requirements in that account.
3. Set a simple alias and separate token path in the ignored accounts file. Enable only the chosen services. Start Docs with its read scope; add comment-listing or write scopes only for the requested capability. The [Docs scope reference](https://developers.google.com/workspace/docs/api/auth) explains the available grants. No credentials are supplied by this repository.
4. Run `authorize check`, then `authorize scopes ALIAS`. When authorization is requested, run `authorize auth ALIAS` with only the needed explicit write flags. Browser consent and the token are private account actions; software installation alone is not consent.
5. Run the selected capability’s help, then one authorized read of a known document, sheet range, contact query, bounded mail query, or event lookup. Verify the account/target and report what was actually tested. A successful local check does not establish live access or authorize a write.

If access fails, distinguish a missing API, insufficient scope, wrong account, or document permission. Do not broaden permissions automatically. Reuse working configuration rather than replacing tokens or forcing a new consent flow.

## Account access and shared runtime
Read [account access and provider support](references/account-access.md) for configuration, account selection, initial authorization, reconnection and diagnosis. This setup skill owns the provider scripts, examples and tests that the selected use skills load. Automatic refresh, where supported, stays in that runtime; normal operations do not require rerunning setup or granting broader access. Keep credential establishment separate from permission for each service action, and preserve existing user approval within its stated scope.

## Optional global discovery
Ask whether this selected capability should be available globally and which supported local clients (Codex, Claude Code, or both) should receive it. Preserve an already stated choice; do not re-ask for granted installation scope. Select only the requested capabilities with repeated `--skill`; omission is refused for this service. Read the [shared link procedure](../setup-agent-hands/references/global-skill-links.md), inspect existing destinations, and use this owner's entrypoint from the checkout root:
```sh
python3 setup-google-services/scripts/link-skills.py --client codex --skill use-gmail
```
This previews only; add `--execute` for the authorized selection. The optional linker requires Python 3.9+ without external packages and keeps provider runtimes separate. Correct links are unchanged; conflicting user files/links are preserved. An explicit previous checkout permits recoverable repair as described in the shared procedure. Verify filesystem targets and fresh client discovery separately; links do not grant account access or operation permission.
