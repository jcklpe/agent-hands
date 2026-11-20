---
attention: historical
---
# LifeOS Google Docs Authorization To-Do

Migration note (2026-10-30): moved from `configs/docs/archive/lifeos-google-docs-auth.todo.md` into Agent Hands as historical service-tooling context. Original body and task states are retained apart from navigation repairs. Old LifeOS commands, paths and account observations are not current Agent Hands instructions. The original Git history stays in the configs repository; stable slugs are unchanged. Current capabilities are documented in the [Agent Hands README](../../README.md).

## To Do
- None.

## Done
- [x] Commit the verified change after the user explicitly approves the one unavoidable staging step for the two new spike files. The pre-commit audit found no credential material; personal and Open Austin OAuth tokens and `google-accounts.json` are ignored. — Dropped as written on 2026-07-29: the user directed atomic pathspec commits without a separate staging-approval gate; `commit-work` remains authoritative for the exact new-file exception.
- [x] Add an opt-in `--docs-write` scope to the normal `lifeos google auth` flow.
- [x] Document that permission setup does not authorize edits and does not add a generic existing-Doc writer to `lifeos drive`.
- [x] Reauthorize the `example` LifeOS Google account with `lifeos google auth example --docs-write` on 2026-07-29. The first callback failed only because the local listener had already exited; restarting the command and opening its fresh link while the listener remained active succeeded.
- [x] Confirm the reauthorized personal token works with the bounded org Google Docs tool by reading a native Doc owned by the selected account. Reading the Open Austin shared Doc with that token correctly returned `PERMISSION_DENIED` because the selected account does not have access; the normal Open Austin token remains the appropriate account for that shared record.
