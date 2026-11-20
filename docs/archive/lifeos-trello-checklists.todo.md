---
attention: historical
---
# LifeOS Trello Checklists — To Do

Historical record. Closed and archived 2026-10-31 during the authorized documentation separation. Stable slug: `lifeos-trello-checklists`. Checklist rendering, creation, item insertion and check/uncheck were implemented and live-checked on 2026-10-05. The later setup/use contract superseded the original immediate-write decision with preview-first execution. No checklist-scope QA remains. Current behavior belongs to [use-trello](../../use-trello/SKILL.md). No service operation, code change or new live QA was performed for this closure.

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-trello-checklists.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-trello](../../use-trello/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

The original direct-write decision below was superseded by the [setup/use contract work](setup-use-contracts.md); current Trello mutations preview by default and require `--execute`.

Concept: [lifeos-trello-checklists.md](lifeos-trello-checklists.md).

## Current State
- 2026-10-05: commands, snapshot rendering, offline tests, and docs built; live round trip passed after one fix (below).

## Completed original checklist
- [x] Dry-run default: no. Checklist writes are direct, matching every other Trello write; approval belongs to the calling workflow (decided 2026-10-05 when the user said to proceed).
- [x] Render checklists in `trello sync`: each non-empty checklist lists its items under the card as `- [x]` / `- [ ]` in Trello position order; the existing `| checklists: Name 1/3` progress stays on the card line. The sync already fetched `checklists=all`, so no new API call.
- [x] `trello add-checklist --card CARD --name NAME [--item TEXT]...`
- [x] `trello add-checklist-item --card CARD --checklist NAME_OR_ID --text TEXT [--text TEXT]...`
- [x] `trello check-item` / `uncheck-item --card CARD --item NAME_OR_ID [--checklist NAME_OR_ID]`. Ambiguous or missing names fail, list candidates, and write nothing.
- [x] Offline tests: `tests/test-trello-checklists.sh` (stubbed API) and new cases in `tests/test-trello-renderers.sh`. Mutation-checked: removing the ambiguity check, forcing `complete` on uncheck, and hardcoding `Snoozed` each fail a test.
- [x] `lifeos help`, README, and the `lifeos-trello` skill.
- [x] 2026-10-05: live round trip on a real card: `add-checklist` with an item, `add-checklist-item`, `check-item`, `uncheck-item --checklist`, each confirmed in `sync` output (progress 1/2, then 0/2, items rendered with state). Left the checklist in place as real sub-tasks.

## Found in use (2026-10-05)
- [x] `add-checklist` failed live with a 400: `POST /checklists` rejects a card short link in `idCard`, though other card endpoints accept one. It now resolves the reference to the full card ID first (`_trello_card_id`), and the stubbed test asserts the full ID is sent.
- [x] The `start: MISSING` marker only checked a list literally named `Snoozed`, so a second board with a differently named snooze list got no warning. Added `TRELLO_SNOOZE_LISTS` (comma-separated, default `Snoozed`), documented in `.env.example` and the skill, with renderer tests.

## Ready For Human QA
- None yet.

## Done
- [x] Spike opened (2026-10-05).
