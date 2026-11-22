---
attention: live
status: implementing
---
# Persistent runtime-state migration
Implement migration of remaining legacy persistent stores outside checkouts, preserving ownership markers, all write journals and a single shared writer location. Current sign-ins and journals remain in their documented locations; no silent relocation or automatic expiration is implemented.

The [runtime-file inventory](../runtime-files.md) owns the actual locations and removal boundaries. A migration must coordinate all writers, preserve unresolved operations and account identity, verify recovery after the move, and avoid selecting an empty journal or creating independently writable copies. The user authorized implementation on 2026-11-22, including an intentional file inventory, explicit storage selection and lifecycle handling. This is a separate implementation boundary from the completed disposable-temp and retained-file review.

Continues from: docs/archive/runtime-file-lifecycle.md


## Implementation sequence
1. Preserve the existing shared generated-file procedure and make each capability document its actual file contract. No new universal artifact folder or background cleanup worker is needed.
2. Migrate the Word/PowerPoint shared account as one unit to designated private user state, including authentication, manifests, plans and journals. Use explicit preview/execution, refuse active sessions or destination collisions, verify all moved bytes, and leave a noncredential tombstone that prevents old clients from initializing a second account at the old path. No browser session copying or sign-in reset.
3. Reconcile Microsoft provider configuration/audits and GitHub journals separately, preserving existing explicit overrides, selected identities and unresolved operations. Do not silently route existing installations into empty replacement journals.
4. Extend the inventory to uncovered writers and test unsafe paths, interrupted migration and lifecycle failures. Real private evidence is retained only for an explicit purpose; ordinary run data uses guarded system temp.

## Acceptance and privacy
Track source, synthetic fixtures and sanitized verification only. Private roots must reject checkout/symlink destinations and retain owner-only permissions. A migration must preserve complete bytes and one writer location, reject native browser singleton markers and keep crash recovery explicit. Cross-filesystem migration must refuse until a separately verified copy/switch procedure exists. macOS is the first live target; other platforms require their own validation. No service grants, remote writes, historical cleanup or publication are authorized by this work.


## Common root and cleanup decision — 2026-11-22
The user selected one home-directory private root, `~/.agent-hands/`, rather than platform-specific defaults. Real private configuration is untracked, with tracked synthetic examples; no secret-bearing project TOML is introduced. Office uses `office/ALIAS/` beneath that root, preserving the earlier whole-account migration and explicit override. Existing platform-specific Office state must be migrated as well, without copying ordinary browser sessions or resetting sign-ins.

The user requires intentional cleanup for ephemeral files rather than reliance on OS purging. Office readbacks now register controller/time/identity metadata and clean up in `finally`; the next readback or explicit cleanup can reclaim registered folders older than 24 hours only after the controller is confirmed absent. This bounds the cleanup trigger without a background worker. Hard termination still leaves private plaintext until a subsequent cleanup; no encryption or immediate-erasure guarantee is claimed. Other writers need their own equivalent lifecycle review.
