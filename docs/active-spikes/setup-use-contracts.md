---
attention: live
---
# Setup and use contracts
Opened: 2026-10-26. Slug: `setup-use-contracts`.

## Goal and adopted scope
Make setup the agent-facing owner for installation, account selection, initial authorization, reconnecting and credential repair. Keep normal service operations in use skills. Preserve one provider runtime for configuration, automatic refresh and bounded requests; the user-facing simplification must not duplicate or remove that runtime support.

Bring all 15 Trello mutation commands to concrete no-write previews by default and explicit `--execute` for mutation. Include compound checklist and successor-link operations, resolved targets, stale-state checks, readback, and honest partial-failure reporting. Existing user authorization for the exact target and change remains sufficient; a credential or execution flag is not that authorization.

Penpot's arbitrary MCP `execute_code` remains an immediate-write interface. Document the boundary and target checks; do not promise a generic dry run or implement an unrequested bounded design adapter.

## Boundaries
Work is local. No service writes, account changes, consent, credential generation, credential-content inspection, publication or history rewriting. Preserve existing private storage paths, access and metadata. If relocating provider code cannot retain those paths without a credential migration, stop that operation and describe the exact required change. Do not add obsolete command or skill aliases. Historical references remain historical; current callers, installation links and guidance must use their actual owners.

Consumer policies and domain choices stay in their consuming projects. Public notes record only reusable implementation reasoning and sanitized verification evidence. Preserve unrelated concurrent work and the existing workflow collection pin.

## Design checkpoints
Separate executable source roots from private configuration roots before relocating provider support. Compare private file metadata without reading or hashing secret content. Determine the precise configuration-root strategy from current code and metadata before the source move; do not silently choose a different account store.

For Trello, construct a bounded concrete operation plan from the supported command and existing resolvers. A preview must never invoke mutation transport, including nested operations. Execution must use the resolved plan, check relevant state, and verify results. Multi-request operations remain nontransactional; a failed request or failed readback may follow an applied change, so preserve completed IDs/steps and do not retry blindly.

## Captured starting point
Promoted from `docs/scratch/trello-write-previews.md`: Consider preview/dry-run output, re-reading card state before edits, and before/after readback for Trello writes. The [current skill](../../use-trello/SKILL.md) executes writes immediately and does not independently verify every ordinary write. This paragraph records the pre-change state; maintained behavior belongs in the use skill after implementation.

## Verification and recovery
Use synthetic request fixtures to test preview and executed paths, not live writes. Cover every mutation, compound ordering, stale state, ambiguity, transport failure and readback uncertainty. Run the existing provider/capability tests after consolidation, validate skill frontmatter/resources, inspect current caller references, and exercise help plus installer/client-link resolution. Distinguish these checks from fresh-client discovery and live-account access.

Scoped commits provide source recovery. Private material stays in place; it must not depend on Git rollback. Keep records active until implementation and remaining verification limits are accounted for; closure is a separate workflow decision.
