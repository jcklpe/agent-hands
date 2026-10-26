---
name: setup-microsoft-services
description: "Install selected Microsoft capabilities, establish or repair account access, choose existing profiles, and diagnose configuration or authentication. Owns the shared provider runtime used by the selected use skills."
---

# Setup Microsoft Services
Start with [account access and provider support](references/account-access.md) and the collection's [available capabilities](../README.md). Provider support, [Outlook Contacts](../use-outlook-contacts/SKILL.md), [Microsoft Files](../use-microsoft-files/SKILL.md), [Excel Workbooks](../use-excel-workbooks/SKILL.md), [Outlook Calendar](../use-outlook-calendar/SKILL.md), [Planner](../use-planner/SKILL.md), and [Outlook Mail](../use-outlook-mail/SKILL.md) are extracted. Do not describe a planned capability as available or move a working legacy account merely because the provider package exists.

## Choose a route
Inspect the actual platform, installed Bash/curl/jq, and existing account configuration. Follow [setup-agent-hands](../setup-agent-hands/SKILL.md) for missing uv/Python. The MSAL route has a provider-local manifest/lock; `uv sync --locked` installs it without unrelated providers. An explicitly supplied `M365_PYTHON` must already include MSAL. Local macOS execution is checked; fresh Linux/WSL and native Windows onboarding remain unverified, and native Windows without Bash is unsupported by these entrypoints.

For MSAL, use the user's own Microsoft public-client application registration, tenant selector, and a separate cache path per alias. Microsoft's [MSAL token guide](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens) documents interactive/device flows and the localhost redirect used here. Follow the tenant's app-registration and consent controls; do not reuse someone else's client/account configuration or circumvent an administrator restriction.

For Graph PowerShell, install PowerShell and Microsoft.Graph.Authentication only when that route is selected. Microsoft's [authentication guide](https://learn.microsoft.com/en-us/powershell/microsoftgraph/authentication-commands) describes delegated consent and context scope. Use the tailored PowerShell accounts example and set the actual expected account in ignored configuration. Its SDK owns the cached context; it is not the MSAL token file. Preserve any existing installation and sign-ins.

## Configure and verify
Check the owning repository's ignores before copying real configuration. Enable only needed services, inspect `authorize scopes ALIAS`, and explain the actual scope breadth rather than promising read-only grants for every read. `authorize check` and help are offline. Run `authorize auth ALIAS` only for requested authorization, then a requested `profile` read to confirm identity. User consent, tenant approval, local readiness, and live service access are separate results.

No example contains working credentials. Never print caches or raw tokens in diagnostics. Do not enable additional services, move tokens, install global client links, or issue a live write as a setup test.

## Account access and shared runtime
Read [account access and provider support](references/account-access.md) for configuration, account selection, initial authorization, reconnection and diagnosis. This setup skill owns the provider scripts, examples and tests that the selected use skills load. Automatic refresh, where supported, stays in that runtime; normal operations do not require rerunning setup or granting broader access. Keep credential establishment separate from permission for each service action, and preserve existing user approval within its stated scope.

## Optional global discovery
Ask whether this selected capability should be available globally and which supported local clients (Codex, Claude Code, or both) should receive it. Preserve an already stated choice; do not re-ask for granted installation scope. Select only the requested capabilities with repeated `--skill`; omission is refused for this service. Read the [shared link procedure](../setup-agent-hands/references/global-skill-links.md), inspect existing destinations, and use this owner's entrypoint from the checkout root:
```sh
python3 setup-microsoft-services/scripts/link-skills.py --client codex --skill use-outlook-mail
```
This previews only; add `--execute` for the authorized selection. The optional linker requires Python 3.9+ without external packages and keeps provider runtimes separate. Correct links are unchanged; conflicting user files/links are preserved. An explicit previous checkout permits recoverable repair as described in the shared procedure. Verify filesystem targets and fresh client discovery separately; links do not grant account access or operation permission.
