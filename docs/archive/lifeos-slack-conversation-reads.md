---
attention: historical
---
# LifeOS Slack Conversation Reads

Historical record. Closed 2026-11-18. Slug: `lifeos-slack-conversation-reads`. Closure and the full archival wording were approved. Existing-conversation discovery, bounded history, threads, search and permalinks are verified with existing access. No grant expansion or Slack write was needed. Visibility, retention, indexing and paging limits remain. Current commands and safeguards belong to [use-slack-messages](../../use-slack-messages/SKILL.md).

The retained entries below record development and earlier review states; pending-approval language there is historical.

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-slack-conversation-reads.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-slack-messages](../../use-slack-messages/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

Opened 2026-10-21. Slug: `lifeos-slack-conversation-reads`.

## Problem and user direction
The Slack adapter could resolve people and read a known thread, but it could not discover an existing direct conversation or read its recent roots. General conversation lookup therefore required additional read-only CLI commands. This spike tracks those additions in the repository that owns the tools.

## Scope and ownership
This spike records the original configs implementation; Agent Hands now owns the native service capability. The optional compatibility command has been retired. Scope is Slack read implementation, offline tests, dispatcher help, tool README, tool-local Slack skill, this spike pair, and its `TODO.md` index entry. The existing Slack List Comments spike remains separate: it addresses item discussion targeting and first-comment writes, whereas this spike addresses general conversation reads.

## Read model and boundaries
Discovery lists existing public/private channels, DMs and group DMs; a verified user-ID filter narrows direct/group conversations. Group membership is checked through the existing read API. Listing never opens a DM or joins a conversation. History reads one newest-first page with explicit continuation and optional timestamp bounds. Thread bodies remain the existing `thread` command's responsibility. `permalink` returns Slack's actual message link. Search reads a single newest-first page with result totals and page selection.

The existing authenticated account and grants are the boundary. No OAuth expansion, credential installation, browser fallback, sends, reactions or other Slack changes are authorized by this implementation task. Search results are leads subject to Slack indexing and UI filters, not proof of a complete conversation. History is subject to retention and conversation visibility, and a root's timestamp does not establish when all its replies occurred.

## Verified result
Live integration checks covered existing DM/group discovery, group membership filtering, DM history, thread reads and API permalinks. This public repository contains only generic implementation evidence and synthetic test data; source messages, participant identifiers, private links, account configuration and surrounding private project context are excluded.

Native `search.messages` works with the existing configured user credential. The November 18 live check returned no matches for a synthetic probe, then retrieved one existing self-authored message through a bounded search. Independent exact-message readback matched its text, author and timestamp; an API permalink lookup matched the search result. No scope, app installation, token, browser session or Slack content changed. Successful API calls establish effective capability, not an exhaustive grant inventory or full-history coverage.

## Validation and next decision
The combined Python discussion/read test suite passes 29 tests, the existing Slack shell tests pass, `bash -n agent-hands/compat/lifeos/lifeos.sh` passes, and the diff has no whitespace errors. New tests cover identity mismatch before content reads, existing DM/group filtering, discovery pagination/incompleteness, bounded history and continuation, search page parameters, API permalinks, missing scopes without retries, and rejection of invalid bounds. Mock reads allow only the intended read methods.

The selected live search verification is complete. Search indexing, visibility, retention and bounded paging remain explicit limits; one verified result does not establish exhaustive coverage. The eight current conversation-operation tests and existing native write-guard/helper checks also pass. Keep this spike live until its complete archival wording and closure are approved.

## Maintained guidance
Current command behavior and examples belong to [use-slack-messages](../../use-slack-messages/SKILL.md).

## Closure preparation — 2026-11-17
Implementation and the recorded existing-access live reads are complete; all eight current conversation-operation tests passed again. Live message search remains unverified after the previously observed `search:read` denial; this review did not inspect or change credentials. A bounded closure is prepared only if the user accepts that outstanding permission-dependent search check as a retained limitation; otherwise keep the spike open. This is not a passing live-search result or permission to expand access. [Slack Messages](../../use-slack-messages/SKILL.md) owns the maintained command surface. The closure condition is tracked in the closure review (local preparation record).

## Live verification — 2026-11-18
The authorized follow-up checked current access before changing grants. Existing access passed native search and independent source/permalink verification, resolving the earlier permission-dependent acceptance gate without an OAuth change. Raw message evidence and identifiers remain private outside Git. The scope is ready for archival review; the dated November 17 preparation above records the earlier state.
