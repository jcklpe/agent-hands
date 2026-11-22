---
attention: live
reviewed: 2026-11-22
---
# Persistent runtime-state migration tasks
[Scope and boundaries](persistent-runtime-state-migration.md). User-authorized implementation began 2026-11-22.

## To do
- Reconcile Microsoft configuration, audit/recovery defaults and GitHub journals without losing existing explicit selection or unresolved writes.
- Expand the maintained writer inventory and close remaining undefined ephemeral/output lifecycles, keeping authored scratch separate and private payloads out of Git.
- Review public diffs and report platform, interruption and delivery limits before closure.

## Done
- Implement and fixture-test designated external Word/PowerPoint storage and explicit whole-account migration, preserving journals and refusing active/split state. Seventeen Word unit/bridge checks and four Word browser checks passed, plus fourteen PowerPoint unit checks and three PowerPoint browser checks. Migration cases cover root safety, byte/permission preservation, active controller/browser refusal, destination collisions and failures before/after rename. No cross-filesystem copy fallback exists.
- Verify the installed account migration with content hashes, a fresh headless read and unchanged sign-in/ownership; keep normal Chrome untouched. On macOS, the complete shared account fingerprint matched after relocation, including Word and PowerPoint journals. The credential-free legacy tombstone prevents old-client reuse. A fresh live read returned the unchanged synthetic document using existing authentication; no content write, MFA, profile copying or new service grant occurred.
- Read the shared generated-file procedure and maintained runtime inventory; the shared guidance already specifies disposable system temp, tracked synthetic verification, explicit private evidence and designated persistent state. Reviewed relevant private workflow concerns without copying them into public documentation. No shared procedure amendment is required at this checkpoint.
