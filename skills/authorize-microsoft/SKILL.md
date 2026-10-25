---
name: authorize-microsoft
description: "Configure Microsoft account aliases, inspect requested scopes, authorize delegated access, or diagnose account identity for Microsoft service skills. Use when their shared authentication or request support is needed."
---

# Authorize Microsoft
Owns literal account configuration, delegated authentication, bounded Graph request helpers, and private token-cache handling. This is a support skill, not a generic Graph command. Follow [setup-microsoft-services](../setup-microsoft-services/SKILL.md) for onboarding. No Google service or personal workspace is required.

## Configuration and runtimes
The default ignored `.env` and account JSON live beside this skill. `M365_CONFIG_DIR` selects another directory, and `M365_ENV_FILE` selects an explicit env file. Relative config/token paths resolve against that directory or this skill, not the working directory. Env values are literal, with no shell expansion; exported values win. An explicit missing env file fails. Copy only the relevant synthetic example after checking ignores, and preserve existing accounts.

MSAL is the default route: Bash 3.2+, curl, jq, and this skill's uv environment with Python 3.11+ and locked MSAL dependencies. `M365_PYTHON` may select an existing compatible environment. Each alias has its own public-client application ID, tenant selector, and private token cache. Client IDs are identifiers, not client secrets; this delegated public-client flow does not use a client secret. New cache files start owner-only and publish atomically. The internal access-token helper prints a token for its caller; never run it as a diagnostic or enable shell tracing.

The optional `graph-powershell` route uses PowerShell and Microsoft.Graph.Authentication, with SDK-managed CurrentUser context/cache rather than an adjacent MSAL JSON cache. Its portable account entry requires `expected_account`; the active SDK account must match before any service request. This route uses the SDK's application and may require tenant approval. It is not an independent SDK cache per alias. The legacy compatibility route retains its existing configuration and permits missing expected-account values; it does not gain the portable identity guarantee until configured.

## Commands
```sh
bash scripts/authorize check
bash scripts/authorize accounts
bash scripts/authorize scopes example
bash scripts/authorize auth example
bash scripts/authorize auth example --no-browser
bash scripts/authorize profile example --json
```
Run from this skill folder or use an absolute path. `check` validates account aliases/config shape offline; it does not verify credentials or access. `accounts` and `scopes` inspect configuration. `auth` performs real consent and caches tokens; `--no-browser` uses device authorization. `profile` is a real remote identity read. Do not perform either merely to check code extraction.

## Scopes and request boundaries
The existing service scope mapping is retained: User.Read; Mail.Read or Mail.ReadWrite for opted-in mail writes; MailboxSettings.ReadWrite for opted-in rules; Calendars.ReadWrite and Contacts.ReadWrite for enabled event/contact capabilities; Files.ReadWrite.All for enabled file access; Tasks.ReadWrite and User.ReadBasic.All for Planner. Some read operations therefore use broader grants than their individual method needs. Inspect the requested scopes and consent screen; service commands still enforce their own bounds and write gates. Changing config does not revoke an existing grant.

Only public Microsoft identity and Graph HTTPS destinations are supported. Arbitrary Graph hosts and sovereign-cloud endpoints are not supported. Paging is bounded by result count and `max_pages` (default 100); result truncation warns, while failed or excessive paging fails. Temporary request/response files are private and cleaned up. No generic HTTP, delete, or send command is exposed by this provider entry; enabled service flags do not authorize an agent action.

## Verification
Local config/endpoint/paging checks and token-staging checks use synthetic data. The PowerShell check substitutes an entirely synthetic module to verify identity mismatch and endpoint refusal. Locked MSAL installation/import is checked independently of authentication. No live account or tenant-consent behavior is established by these checks.
