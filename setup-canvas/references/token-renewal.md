# Canvas token renewal
Use only for an explicitly authorized personal-token development connection where institution rules permit it. This is not OAuth or general-user onboarding. Canvas documents [token creation and regeneration](https://developerdocs.instructure.com/services/canvas/resources/access_tokens); a documented endpoint does not prove the current account can use it. [Authentication guidance](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth) requires OAuth for applications used by others.

## Inspect and enable
From the collection root, after confirming and recording the user's identity:
```sh
uv run --project setup-canvas python setup-canvas/scripts/canvas_auth.py token-status example
uv run --project setup-canvas python setup-canvas/scripts/canvas_auth.py token-renew example --enable-auto --lifetime-days 90 --before-days 14
```
`token-status` identifies the configured credential by its visible hint and prints only that token's ID, state, creation/expiry timestamps and reported manual-regeneration flag. Hints, credential values and other tokens' metadata are omitted. Ambiguous matches refuse. A manual-regeneration flag does not establish successor-creation permission.

`token-renew` previews a successor for the confirmed user with identical scopes, its requested expiry, the old token's unchanged expiry and the optional automatic policy. The fingerprint also binds the private configuration. Present these concrete effects; never expose credentials. After approval covering this operation, repeat with `--execute --expect HASH`. Existing explicit authorization within scope counts. Changed inputs refuse before creation. Select an institution-permitted lifetime of 2–90 days; no unlimited expiry is requested. Canvas can deny creation or impose a shorter lifetime.

Execution creates a successor through `POST /api/v1/users/self/tokens`, saves its secret to a private pending file, verifies its user, state, scopes and expiry, then atomically replaces the selected env assignment and updates that alias's expiry. Other assignments and accounts are preserved. The old token is not regenerated, revoked or extended; it retains its expiry. Temporary overlap is expected. Password-manager copies retain the original token and its expiry; they are not updated. The ignored local `.env` becomes the current operational credential.

Renewal requires regular owner-only configuration files, exactly one selected token assignment, and a token variable used by exactly one account. Exported overrides, symlinks, additional hard links and changed contents refuse. Private state uses ignored `.env.canvas-renew-ALIAS.*` files in the selected configuration directory. `pending.json` can contain a replacement secret: never load it into chat. `last.json` contains outcome metadata only. POSIX advisory locking serializes renewal; native Windows renewal is unverified and refused.

## Automatic operation
Successful execution with `--enable-auto` records this private per-account policy:
```json
"token_renewal": {"enabled": true, "lifetime_days": 90, "before_days": 14}
```
Absence disables renewal. Normal `use-canvas` remote commands verify identity, then check expiry in Python. Within the renewal window they run the same successor procedure before continuing with the new credential. No model, background job or scheduler is involved. A course-write preview can renew credentials only under this separately authorized policy; it still changes no course content. Local checks, history queries and `token-status` never renew credentials.

An idle connection can expire; an expired or revoked credential cannot renew itself. Reconnect manually in that case. To disable renewal, set `token_renewal.enabled` to `false`; this changes neither credential nor expiry.

## Failure and recovery
Creation is sent once and never retried. A durable pending record precedes transmission. An explicit nontransient client refusal leaves configuration unchanged. Timeouts, transient responses, malformed success, verification failure and interrupted saves leave uncertainty and block further renewal. The old token is never revoked. With auto renewal enabled, unresolved pending work also stops normal remote commands.

If the pending record contains a saved replacement, resume under existing authorization:
```sh
uv run --project setup-canvas python setup-canvas/scripts/canvas_auth.py token-renew example --recover --execute
```
Recovery verifies that credential and completes the local switch without another creation. It accepts only original or already-written file fingerprints, covering interruption between env and account-file replacement while refusing unrelated edits. If no response was saved, inspect the recorded purpose in Canvas settings; an unused successor may exist until expiry. The user must reconcile that uncertainty and authorize removal of the pending marker before another attempt. Do not blindly delete it or retry creation.

Synthetic tests cover preview gating, scope preservation, stale files, due/not-due operation, refusal, lost responses and interrupted saves. Live successor creation, expiry, identity/scope checks, local persistence and subsequent normal use passed for one authorized account. Other institutions/roles, shorter server expiry clamping and a later time-triggered renewal remain unverified. OAuth refresh is a distinct workflow requiring a developer key and is not implemented here.
