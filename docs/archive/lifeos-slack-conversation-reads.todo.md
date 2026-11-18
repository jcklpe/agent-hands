---
attention: historical
---
# LifeOS Slack Conversation Reads — Tasks

Historical record. Closed 2026-11-18. Slug: `lifeos-slack-conversation-reads`. Closure and the full archival wording were approved. Existing-conversation discovery, bounded history, threads, search and permalinks are verified with existing access. No grant expansion or Slack write was needed. Visibility, retention, indexing and paging limits remain. Current commands and safeguards belong to [use-slack-messages](../../use-slack-messages/SKILL.md).

The retained entries below record development and earlier review states; pending-approval language there is historical.

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-slack-conversation-reads.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-slack-messages](../../use-slack-messages/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

Opened 2026-10-21. Slug: `lifeos-slack-conversation-reads`. Conceptual context: [LifeOS Slack Conversation Reads](lifeos-slack-conversation-reads.md).

## Current State
Implementation and existing-access integration reads are verified, including native message search and independent exact-source/permalink readback on November 18. No OAuth changes, browser fallback or Slack writes occurred. The implementation needs no additional search command or grant change for the configured account.

## To Do
- Review and authorize spike closure before any historical transition or archival.

## Ready for Human QA
- None required for the terminal-verifiable existing-access reads. Search live verification is complete; full archival wording and closure approval remain.

## Done
- [x] If broader search is needed, obtain explicit approval for the exact `search:read` grant before changing authorization, then live-verify `search`. Otherwise keep the scope limitation documented; existing-access history reads do not depend on search access. Completed 2026-11-18: the user authorized enabling search if needed. The existing credential already supports native search; a synthetic no-match query and a one-result self-authored-message query passed. Independent exact-source readback matched text, author and timestamp, and a separate permalink lookup agreed. No grant change was needed and no message was sent.
- Add read-only conversation listing including existing DMs and group DMs. Implemented `conversations` with types, archived inclusion, participant filtering and bounded full pagination; live existing-DM/group discovery and membership checks succeeded.
- Add bounded conversation history sufficient to locate recent messages. Implemented `history` with limit, cursor, time bounds, explicit continuation/end marker and thread metadata; recent direct-message roots and relevant replies were read successfully using existing access.
- Add read-only message search. Implemented `search` with newest-first ordering, bounded result pages, totals and API permalinks. Offline verification passes; live `search.messages` returned `missing_scope` requiring `search:read` once, with no expansion or retry.
- Add message permalink lookup. Implemented `permalink`; live API-returned direct-message links succeeded.
- Preserve existing APIs and add tests/help/docs. Existing Slack tests pass; combined Python suite passes 29 tests including eight new read-command tests. Dispatcher syntax, help and whitespace checks pass. Updated only Slack implementation, its directly associated tests and tool guidance.
- Record this CLI work as a bounded spike in the owning repository. Added this pair with `attention: live` and a `TODO.md` index entry.

## Original verification commands (historical paths)
These commands record the original checkpoint; use the native skill for current validation.
```sh
PYTHONDONTWRITEBYTECODE=1 python3 agent-hands/compat/lifeos/tests/test-slack-comments.py
bash agent-hands/compat/lifeos/tests/test-slack.sh
bash -n agent-hands/compat/lifeos/lifeos.sh
git diff --check
```

## Closure preparation — 2026-11-17
Implementation and the recorded existing-access live reads are complete; all eight current conversation-operation tests passed again. Live message search remains unverified after the previously observed `search:read` denial; this review did not inspect or change credentials. A bounded closure is prepared only if the user accepts that outstanding permission-dependent search check as a retained limitation; otherwise keep the spike open. This is not a passing live-search result or permission to expand access. [Slack Messages](../../use-slack-messages/SKILL.md) owns the maintained command surface. The closure condition is tracked in the closure review (local preparation record).

## Live verification — 2026-11-18
The permission-dependent search gate is resolved for the existing configured user account. The native search path verified account identity before reading content; exact-message history/thread retrieval and `chat.getPermalink` independently confirmed the returned lead. Eight conversation-operation tests, the migrated native write guards and the shared URL/paging checks pass on macOS with Python 3.13. Private responses are held outside Git with owner-only permissions. This check did not inventory every scope, prove exhaustive search or test other workspaces/platforms. Closure is ready for the required full-message approval.
