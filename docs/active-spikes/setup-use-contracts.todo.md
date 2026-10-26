---
attention: live
---
# Setup and use contracts — Tasks
Opened: 2026-10-26. Slug: `setup-use-contracts`. [Concept](setup-use-contracts.md).

## Current state
The scope is approved. The prior README robot CTA and security contact are separate completed patches. No runtime behavior or authentication storage has changed for this spike yet.

## To Do
- [ ] Inventory provider source/config coupling, current callers and private path metadata without reading or hashing credentials; settle a path-preserving source move.
- [ ] Implement concrete preview and explicit execution for all 15 Trello mutation commands, preserving bounded target resolution and compound semantics.
- [ ] Add synthetic coverage proving zero default mutations, stale-state refusal, verified execution and explicit partial/uncertain outcomes for every mutation family.
- [ ] Consolidate the six authorize skills into their existing setup owners, retaining one shared runtime and moving implementation/tests without obsolete wrappers or credential changes.
- [ ] Update capability dependencies, public guides and Penpot's immediate-write/permission documentation to match the final setup/use contract.
- [ ] Update installation references and installed client skill links, preserving unrelated integrations and authentication.
- [ ] Update affected consumer-owned instructions in their own repositories, preserving their private policy and other edits.
- [ ] Run final provider/capability, frontmatter/resource, fresh-shell/help, installer/link and active-reference checks; compare private metadata and record honest limits.
- [ ] Commit scoped changes and reconcile only the containing Agent Hands gitlink; preserve the canonical workflow pin and no-push hold.

## Ready for Human QA
None yet. Fresh-client discovery and live service behavior will remain distinct from offline checks.

## Done
- [x] Read the current project instructions and adopted spike/commit procedures; consult skill-authoring and relevant private workflow concerns without importing their narrative into this repository.
- [x] Promote the captured Trello preview topic into this approved setup/use workstream and add a paired plan plus index entry.

## Baseline evidence
The six authorize folders contain 68 tracked files in total, including provider code, examples, manifests and tests. Existing use entrypoints import/source them. Google refreshes expired access tokens; Microsoft MSAL uses cached-account silent acquisition, while the optional PowerShell route can connect during requests. Penpot already sources setup-owned configuration. These are source observations, not fresh authentication checks.

Before this spike, the synthetic Trello scheduling, checklist and failure/partial-link tests and GitHub issue preview/execute test passed. They establish the existing behavior only; new default-preview coverage is still required.
