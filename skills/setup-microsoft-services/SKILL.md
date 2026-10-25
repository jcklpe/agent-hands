---
name: setup-microsoft-services
description: "Prepare selected Microsoft service capabilities and their delegated account authorization. Use for first-time setup, missing runtimes, or scoped account-readiness diagnosis without installing unrelated providers."
---

# Setup Microsoft Services
Start with [authorize-microsoft](../authorize-microsoft/SKILL.md) and the collection's [available capabilities](../../README.md). Provider support, [Outlook Contacts](../use-outlook-contacts/SKILL.md), [Microsoft Files](../use-microsoft-files/SKILL.md), [Excel Workbooks](../use-excel-workbooks/SKILL.md), [Outlook Calendar](../use-outlook-calendar/SKILL.md), [Planner](../use-planner/SKILL.md), and [Outlook Mail](../use-outlook-mail/SKILL.md) are extracted. Do not describe a planned capability as available or move a working legacy account merely because the provider package exists.

## Choose a route
Inspect the actual platform, installed Bash/curl/jq, and existing account configuration. Follow [setup-agent-hands](../setup-agent-hands/SKILL.md) for missing uv/Python. The MSAL route has a provider-local manifest/lock; `uv sync --locked` installs it without unrelated providers. An explicitly supplied `M365_PYTHON` must already include MSAL. Local macOS execution is checked; fresh Linux/WSL and native Windows onboarding remain unverified, and native Windows without Bash is unsupported by these entrypoints.

For MSAL, use the user's own Microsoft public-client application registration, tenant selector, and a separate cache path per alias. Microsoft's [MSAL token guide](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens) documents interactive/device flows and the localhost redirect used here. Follow the tenant's app-registration and consent controls; do not reuse someone else's client/account configuration or circumvent an administrator restriction.

For Graph PowerShell, install PowerShell and Microsoft.Graph.Authentication only when that route is selected. Microsoft's [authentication guide](https://learn.microsoft.com/en-us/powershell/microsoftgraph/authentication-commands) describes delegated consent and context scope. Use the tailored PowerShell accounts example and set the actual expected account in ignored configuration. Its SDK owns the cached context; it is not the MSAL token file. Preserve any existing installation and sign-ins.

## Configure and verify
Check the owning repository's ignores before copying real configuration. Enable only needed services, inspect `authorize scopes ALIAS`, and explain the actual scope breadth rather than promising read-only grants for every read. `authorize check` and help are offline. Run `authorize auth ALIAS` only for requested authorization, then a requested `profile` read to confirm identity. User consent, tenant approval, local readiness, and live service access are separate results.

No example contains working credentials. Never print caches or raw tokens in diagnostics. Do not enable additional services, move tokens, install global client links, or issue a live write as a setup test.
