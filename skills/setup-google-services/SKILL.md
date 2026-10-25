---
name: setup-google-services
description: "Help a user install and configure selected Google service skills, obtain desktop OAuth credentials, and verify local readiness without changing unrelated Google integrations."
---

# Setup Google Services
Currently [Google Docs](../use-google-docs/SKILL.md) and [Google Contacts](../use-google-contacts/SKILL.md) are extracted. Each depends only on [authorize-google](../authorize-google/SKILL.md); Gmail, Drive, Sheets, and Calendar remain with their previous owner during migration. Do not advertise planned capabilities as available.

## Prepare the selected capability
Check the actual platform and existing tools. The entrypoints require Bash 3.2+, curl, jq, and uv or Python 3.11+. Follow [setup-agent-hands](../setup-agent-hands/SKILL.md) for missing uv/Python rather than assuming a developer environment. From each selected Python skill folder, `uv sync --locked` prepares its own environment. There is no all-provider dependency installation. macOS offline execution is checked; fresh Linux/WSL and native Windows onboarding remain unverified. Native Windows without Bash is unsupported by this entry.

## Configure authorization
1. Read the provider configuration contract and preserve existing accounts. Check ignore rules before copying the tailored example files. Never copy someone else's live credentials or token.
2. Follow Google's [desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app): create/select the user's own Cloud project, enable the relevant APIs, configure its consent screen, and create a desktop OAuth client. Contact lookup uses the People API. Docs operations use the Docs API; listing/adding comments also uses the Drive API. Save the downloaded JSON at the configured credentials path. Review organization restrictions and any testing-user requirements in that account.
3. Set a simple alias and separate token path in the ignored accounts file. Enable only the chosen services. Start Docs with its read scope; add comment-listing or write scopes only for the requested capability. The [Docs scope reference](https://developers.google.com/workspace/docs/api/auth) explains the available grants. No credentials are supplied by this repository.
4. Run `authorize check`, then `authorize scopes ALIAS`. When authorization is requested, run `authorize auth ALIAS` with only the needed explicit write flags. Browser consent and the token are private account actions; software installation alone is not consent.
5. Run the selected capability’s help, then one authorized read of a known document or contact query. Verify the account/target and report what was actually tested. A successful local check does not establish live access or authorize a write.

If access fails, distinguish a missing API, insufficient scope, wrong account, or document permission. Do not broaden permissions automatically. Reuse working configuration rather than replacing tokens or forcing a new consent flow.
