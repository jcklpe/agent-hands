---
attention: historical
---
# Spike: LifeOS Google Docs Authorization

Migration note (2026-10-30): moved from `configs/docs/archive/lifeos-google-docs-auth.md` into Agent Hands as historical service-tooling context. Original body and task states are retained apart from navigation repairs. Old LifeOS commands, paths and account observations are not current Agent Hands instructions. The original Git history stays in the configs repository; stable slugs are unchanged. Current capabilities are documented in the [Agent Hands README](../../README.md).

## Purpose
Let the normal LifeOS Google account-token workflow request the Google Docs write scope when a bounded tool needs to edit an existing native Google Doc, without turning permission setup into blanket authorization for Drive writes.

## Boundary
The normal Gmail and Drive alias token remains the shared credential surface. `lifeos google auth ALIAS --docs-write` uses Google's incremental authorization to add the Docs scope. The flag grants capability only; actual document edits remain owned by narrow, dry-run-first tools and their workflow-specific approval rules.

This spike does not add a generic existing-Doc edit command to `lifeos drive`.

## Validation
- Parse the affected shell files with both Bash and Zsh.
- Confirm the help and tool skills explain the difference between OAuth capability and edit authorization.
- Reauthorize the intended account and exercise an authenticated Docs read through a bounded tool before considering the permission path proven.

## Outcome
Completed 2026-07-29. `lifeos google auth ALIAS --docs-write` now adds the Google Docs scope through incremental authorization without adding a generic existing-Doc editing surface to `lifeos drive`. The selected account was reauthorized successfully, the resulting token was exercised through the bounded Open Austin Docs tool, and durable usage and authority guidance now lives in the LifeOS CLI documentation and skills.
