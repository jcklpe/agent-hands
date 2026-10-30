---
name: setup-canvas
description: "Install the Canvas capability, establish or repair account access with a user-created personal access token, select courses, and diagnose configuration or authentication. Owns the shared provider runtime used by use-canvas."
---
# Setup Canvas
Read this skill's [account-access reference](references/account-access.md) before configuring anything. This setup owns the Canvas configuration, the token's storage and the provider runtime (`scripts/canvas_auth.py`) that `use-canvas` loads. `use-canvas` is not implemented yet, so only the local check and the identity read below exist; course listing, `verify`, exports and writes arrive with it. Setup never writes to Canvas.

## Runtime
Python 3.11 or later with only its standard library; no Bash or third-party package is needed. If uv is missing, follow the [official installer](https://docs.astral.sh/uv/getting-started/installation/) within setup authorization; uv can provision a compatible Python for this folder's manifest. From the collection root:
```sh
uv run --project setup-canvas python setup-canvas/scripts/canvas_auth.py --help
```
A compatible `python3` can run the script directly. Time-zone handling uses the system time-zone database; native Windows needs the `tzdata` package and is unverified. macOS offline checks pass; fresh Linux and Windows bootstrap are not yet verified.

## Connect an account
1. Explain the trade-off first. A Canvas personal access token is password-equivalent, cannot be scoped without an administrator-configured developer key, and lets whoever holds the file act as the user across the whole instance. Agent Hands calls only the endpoints its Canvas skills document, but the token itself is not limited to them.
2. Ask the user to check their institution's published policy on personal tokens and third-party tools. Setup cannot determine policy, and a visible button is not permission. If policy forbids it, stop and say so; do not offer browser sessions or scraping as a workaround.
3. Ask the user to open `https://<their instance>/profile/settings` in their own browser and say whether **New Access Token** appears under Approved Integrations. Administrators can turn creation off (Canvas documents a *Limit Personal Access Token Creation* setting, and a separate student and observer restriction exists), so absence is a normal outcome: report `token_creation_unavailable` and stop. Look at that page yourself only with explicit browser approval, and never press the button.
4. If creation is available and permitted, the user creates the token themselves, with a purpose label and an expiry date, and pastes it into the ignored `.env` in their own editor. Never ask for the token in chat, in a command argument or in a tracked file. Never create, regenerate or delete tokens through the API.
5. In this setup folder, confirm `git check-ignore` reports `.env` and `canvas-accounts.json` as ignored, then copy `.env.example` and `canvas-accounts.example.json` only where the real files are absent. Preserve existing accounts. Set owner-only permissions on `.env` (`chmod 600`). Fill in the alias, the instance origin as `base_url`, `token_env`, and the expiry the user chose as `token_expires`; leave `user_id` empty.
6. Run `check ALIAS` (no network) and fix anything it reports.
7. With the user's permission for one read, run `whoami ALIAS`. It prints the Canvas user ID, display name and time zone, never email or login. When the user confirms it is their account, record the printed ID as `user_id`. From then on a different token identity stops every command.
8. Record course selection as the user directs. A course's ID is the number in its web address (`https://example.instructure.com/courses/123`). Selection decides what gets exported; it is not a write restriction and does not narrow the token.

Report local readiness, the identity read and anything still unverified separately. Do not perform a test write as part of setup.

## Reconnect, rotate or disconnect
A `token_rejected` error means Canvas refused the token: it expired, was revoked or was regenerated. The user creates or regenerates one in their profile settings (if still permitted), replaces the `.env` value and updates `token_expires`; `whoami` must then match the recorded `user_id`. A changed instance address updates `base_url` only after the user confirms it, followed by `whoami`. To disconnect, the user deletes the token in Canvas, then remove the `.env` value and the alias. Never move or rewrite another account's entry.

## Account access and shared runtime
This setup skill owns the provider runtime, examples and tests that `use-canvas` will load: configuration parsing, the token's origin-only transport, pagination, throttling back-off, error kinds and the identity check. Normal operations will not require rerunning setup. Keep credential establishment separate from permission for each Canvas action, and preserve existing user approval within its stated scope.

## Offline checks
From the collection root, `python3 setup-canvas/tests/test_config.py` and `python3 setup-canvas/tests/test_transport.py` check literal configuration, account validation, the local check, where the token goes, pagination, redirects, throttling, error kinds and identity with synthetic data, plus the real transport against a loopback server. They do not establish live access, institution policy or token availability.
